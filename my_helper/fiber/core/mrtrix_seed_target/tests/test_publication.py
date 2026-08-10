"""Transactional publication ownership and reuse tests."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
import pytest

from ..config import resolve_config
from ..errors import PublicationError
from ..identity import file_sha256
from ..models import ResolvedSubjectInputs
from .. import publication as publication_module
from ..publication import publish_subject
from ..tck import write_selected_tck
from .helpers import minimal_document


RUN_PROVENANCE = {
    "lead_dbs_git_commit": "0" * 40,
    "code_hash": "code",
    "preparation_code_hash": "preparation",
    "tracking_code_hash": "tracking",
    "publication_code_hash": "publication",
}


def _resolved_subject(subject_dir: Path) -> ResolvedSubjectInputs:
    dummy = subject_dir / "dummy"
    return ResolvedSubjectInputs(
        subject_id="sub-001",
        subject_dir=subject_dir,
        dwi=dummy,
        bvec=dummy,
        bval=dummy,
        b0=dummy,
        brain_mask=dummy,
        tracking_mask=dummy,
        anchor_native_reference=dummy,
        b0_to_anchor_transform=dummy,
        anchor_to_b0_transform=dummy,
        target_to_anchor_image_deformation=dummy,
        anchor_to_target_image_deformation=dummy,
        coregistration_method_log=dummy,
        coregistration_method="SPM (Friston 2007)",
        coregistration_method_token="spm",
        coregistration_approved=True,
        normalization_method_log=dummy,
        normalization_method="EasyReg (Iglesias 2023)",
        normalization_approval=1.0,
        target_space="MNI152NLin2009bAsym",
    )


def _seed_result(tmp_path: Path, *, target_id: str = "Target") -> dict:
    streamlines = [np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)]
    mother = tmp_path / "stage" / "seedwide.tck"
    target = tmp_path / "stage" / "target.tck"
    write_selected_tck(streamlines, np.asarray([True]), mother)
    write_selected_tck(streamlines, np.asarray([True]), target)
    return {
        "status": "staged_complete",
        "seedwide_identity": "seed-identity",
        "identity_document": {
            "identity_version": 2,
            "preparation_artifact_set_hash": "artifact-set",
        },
        "total_streamlines": 1,
        "target_hit_counts": [1],
        "minimum_target_streamlines": 1,
        "outputs": {
            "mother": {
                "path": str(mother),
                "sha256": file_sha256(mother),
                "streamline_count": 1,
            },
            "targets": [
                {
                    "id": target_id,
                    "side": "lh",
                    "key": f"lh/{target_id}",
                    "path": str(target),
                    "sha256": file_sha256(target),
                    "streamline_count": 1,
                    "hit_fraction": 1.0,
                }
            ],
        },
    }


def test_fresh_publication_and_unchanged_reuse_preserve_tck_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    result = _seed_result(tmp_path)
    first = publish_subject(
        config=config,
        subject=subject,
        preparation={"preparation_identity": "prep"},
        seed_results={"lh/Seed": result},
        run_provenance=RUN_PROVENANCE,
    )
    assert first["status"] == "native_complete"
    state = publication_module.read_json(
        subject.output_root / "work" / "state.json"
    )
    assert (
        state["seed_results"]["lh/Seed"]["preparation_artifact_set_hash"]
        == "artifact-set"
    )
    assert state["seed_results"]["lh/Seed"]["targets"] == [
        {"key": "lh/Target", "streamline_count": 1, "hit_fraction": 1.0}
    ]
    final = (
        subject.output_root
        / "tractograms"
        / "native"
        / "lh"
        / "Seed"
        / "seedwide.tck"
    )
    first_mtime = final.stat().st_mtime_ns
    sidecar = subject.output_root / "tractograms" / "native" / "lh" / "._Seed"
    sidecar.write_bytes(b"appledouble")
    trashed: list[str] = []

    def fake_trash(path: str) -> None:
        trashed.append(path)
        Path(path).unlink()

    monkeypatch.setattr(publication_module, "send2trash", fake_trash)
    time.sleep(0.001)
    second = publish_subject(
        config=config,
        subject=subject,
        preparation={"preparation_identity": "prep"},
        seed_results={"lh/Seed": result},
        run_provenance=RUN_PROVENANCE,
    )
    assert second["generated_artifacts"] == 0
    assert second["reused_artifacts"] == 2
    assert final.stat().st_mtime_ns == first_mtime
    assert trashed == [str(sidecar)]
    assert not sidecar.exists()
    assert all(
        path.suffix == ".tck" and not path.name.startswith("._")
        for path in (subject.output_root / "tractograms").rglob("*")
        if path.is_file()
    )


def test_unknown_final_collision_is_never_overwritten(tmp_path: Path) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    final = (
        subject.output_root
        / "tractograms"
        / "native"
        / "lh"
        / "Seed"
        / "seedwide.tck"
    )
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"unknown")
    with pytest.raises(PublicationError, match="non-tool-owned final path"):
        publish_subject(
            config=config,
            subject=subject,
            preparation={"preparation_identity": "prep"},
            seed_results={"lh/Seed": _seed_result(tmp_path)},
            run_provenance=RUN_PROVENANCE,
        )
    assert final.read_bytes() == b"unknown"


def test_unknown_extra_public_file_blocks_publication(tmp_path: Path) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    unknown = subject.output_root / "tractograms" / "native" / "unknown.tck"
    unknown.parent.mkdir(parents=True, exist_ok=True)
    unknown.write_bytes(b"unknown")
    with pytest.raises(PublicationError, match="non-tool-owned stale path"):
        publish_subject(
            config=config,
            subject=subject,
            preparation={"preparation_identity": "prep"},
            seed_results={"lh/Seed": _seed_result(tmp_path)},
            run_provenance=RUN_PROVENANCE,
        )
    assert unknown.read_bytes() == b"unknown"


def test_stale_tool_owned_target_is_transactionally_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    first_config = resolve_config(document, source_path=tmp_path / "first.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    first = publish_subject(
        config=first_config,
        subject=subject,
        preparation={"preparation_identity": "prep"},
        seed_results={"lh/Seed": _seed_result(tmp_path / "first")},
        run_provenance=RUN_PROVENANCE,
    )
    assert first["retired_artifacts"] == 0
    stale = (
        subject.output_root
        / "tractograms"
        / "native"
        / "lh"
        / "Seed"
        / "targets"
        / "lh"
        / "Target.tck"
    )
    assert stale.is_file()

    second_document = minimal_document(tmp_path)
    second_document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    second_document["atlas"]["seeds"][0]["targets"][0]["id"] = "Other"
    second_config = resolve_config(
        second_document, source_path=tmp_path / "second.yaml"
    )
    trashed: list[str] = []

    def fake_trash(path: str) -> None:
        trashed.append(path)
        Path(path).unlink()

    monkeypatch.setattr(publication_module, "send2trash", fake_trash)
    second = publish_subject(
        config=second_config,
        subject=subject,
        preparation={"preparation_identity": "prep"},
        seed_results={
            "lh/Seed": _seed_result(tmp_path / "second", target_id="Other")
        },
        run_provenance=RUN_PROVENANCE,
    )
    replacement = stale.with_name("Other.tck")
    assert second["retired_artifacts"] == 1
    assert not stale.exists()
    assert replacement.is_file()
    assert len(trashed) == 1
    assert "rollback" in trashed[0]


def test_stale_target_is_restored_when_new_publication_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    first_config = resolve_config(document, source_path=tmp_path / "first.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    publish_subject(
        config=first_config,
        subject=subject,
        preparation={"preparation_identity": "prep"},
        seed_results={"lh/Seed": _seed_result(tmp_path / "first")},
        run_provenance=RUN_PROVENANCE,
    )
    stale = (
        subject.output_root
        / "tractograms"
        / "native"
        / "lh"
        / "Seed"
        / "targets"
        / "lh"
        / "Target.tck"
    )
    stale_hash = file_sha256(stale)

    second_document = minimal_document(tmp_path)
    second_document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    second_document["atlas"]["seeds"][0]["targets"][0]["id"] = "Other"
    second_config = resolve_config(
        second_document, source_path=tmp_path / "second.yaml"
    )
    replacement = stale.with_name("Other.tck")
    real_sha256 = publication_module.file_sha256

    def fail_final_validation(path: Path | str) -> str:
        if Path(path) == replacement:
            raise OSError("injected final validation failure")
        return real_sha256(path)

    monkeypatch.setattr(publication_module, "file_sha256", fail_final_validation)
    with pytest.raises(PublicationError, match="publication failed"):
        publish_subject(
            config=second_config,
            subject=subject,
            preparation={"preparation_identity": "prep"},
            seed_results={
                "lh/Seed": _seed_result(tmp_path / "second", target_id="Other")
            },
            run_provenance=RUN_PROVENANCE,
        )
    assert stale.is_file()
    assert file_sha256(stale) == stale_hash
    assert not replacement.exists()
