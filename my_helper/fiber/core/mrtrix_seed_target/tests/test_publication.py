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
        mni_to_anchor_transform=dummy,
        anchor_to_dwi_transform=dummy,
        coregistration_method_log=dummy,
        coregistration_method="SPM (Friston 2007)",
        coregistration_method_token="spm",
        coregistration_approved=True,
    )


def _seed_result(tmp_path: Path) -> dict:
    streamlines = [np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)]
    mother = tmp_path / "stage" / "seedwide.tck"
    target = tmp_path / "stage" / "target.tck"
    write_selected_tck(streamlines, np.asarray([True]), mother)
    write_selected_tck(streamlines, np.asarray([True]), target)
    return {
        "status": "staged_complete",
        "seedwide_identity": "seed-identity",
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
                    "id": "Target",
                    "side": "lh",
                    "key": "lh/Target",
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
    )
    assert first["status"] == "complete"
    final = subject.output_root / "tractograms" / "lh" / "Seed" / "seedwide.tck"
    first_mtime = final.stat().st_mtime_ns
    sidecar = subject.output_root / "tractograms" / "lh" / "._Seed"
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
    final = subject.output_root / "tractograms" / "lh" / "Seed" / "seedwide.tck"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(b"unknown")
    with pytest.raises(PublicationError, match="non-tool-owned final path"):
        publish_subject(
            config=config,
            subject=subject,
            preparation={"preparation_identity": "prep"},
            seed_results={"lh/Seed": _seed_result(tmp_path)},
        )
    assert final.read_bytes() == b"unknown"
