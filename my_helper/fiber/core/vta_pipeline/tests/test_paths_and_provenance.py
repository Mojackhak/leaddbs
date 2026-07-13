from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_helper.fiber.core.vta_pipeline.errors import ArtifactError
from my_helper.fiber.core.vta_pipeline.provenance import (
    LeafStatus,
    LeafStore,
    ProvenanceContext,
    compute_input_hash,
    file_sha256,
    read_leaf_status,
)


def context(input_hash: str = "input-hash") -> ProvenanceContext:
    return ProvenanceContext(
        run_id="20260713T120000Z",
        input_hash=input_hash,
        study_base_sha256="study-hash",
        vta_model_sha256="model-hash",
        code_commit=None,
    )


def write_efield(leaf: Path, content: bytes = b"efield") -> Path:
    leaf.mkdir(parents=True, exist_ok=True)
    path = leaf / "efield.nii.gz"
    path.write_bytes(content)
    return path


def test_completed_provenance_has_exact_order_and_status_last(
    tmp_path: Path,
) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")
    efield = write_efield(store.leaf)

    store.complete(context(), efield)

    pairs = json.loads(
        (store.leaf / "provenance.json").read_text(encoding="utf-8"),
        object_pairs_hook=list,
    )
    assert [key for key, _ in pairs] == [
        "schema_version",
        "run_id",
        "input_hash",
        "study_base_sha256",
        "vta_model_sha256",
        "code_commit",
        "efield_sha256",
        "final_status",
    ]
    assert pairs[-1] == ("final_status", "completed")
    assert dict(pairs)["efield_sha256"] == file_sha256(efield)


def test_failed_leaf_contains_only_failed_provenance(tmp_path: Path) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")
    write_efield(store.leaf, b"partial")
    (store.leaf / "partial.tmp").write_text("partial", encoding="utf-8")

    store.fail(context())

    assert [path.name for path in store.leaf.iterdir()] == ["provenance.json"]
    payload = json.loads((store.leaf / "provenance.json").read_text())
    assert payload["efield_sha256"] is None
    assert list(payload)[-1] == "final_status"
    assert payload["final_status"] == "failed"
    assert list((tmp_path / "Trash").rglob("efield.nii.gz"))


def test_force_moves_existing_leaf_to_trash(tmp_path: Path) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")
    store.leaf.mkdir(parents=True)
    (store.leaf / "old.txt").write_text("old", encoding="utf-8")

    result = store.prepare(context(), force=True, resume=False)

    assert result == "run"
    assert not (store.leaf / "old.txt").exists()
    assert list((tmp_path / "Trash").rglob("old.txt"))


def test_resume_reuses_matching_completed_leaf(tmp_path: Path) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")
    store.complete(context(), write_efield(store.leaf))

    assert store.prepare(context(), force=False, resume=True) == "reuse"


def test_resume_rejects_changed_or_corrupt_leaf(tmp_path: Path) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")
    efield = write_efield(store.leaf)
    store.complete(context(), efield)

    efield.write_bytes(b"changed")

    with pytest.raises(ArtifactError, match="stale"):
        store.prepare(context(), force=False, resume=True)
    assert read_leaf_status(store.leaf, context().input_hash) is LeafStatus.STALE


def test_prepare_rejects_force_and_resume_together(tmp_path: Path) -> None:
    store = LeafStore(tmp_path / "leaf", trash_root=tmp_path / "Trash")

    with pytest.raises(ArtifactError, match="mutually exclusive"):
        store.prepare(context(), force=True, resume=True)


def test_compute_input_hash_is_canonical() -> None:
    first = compute_input_hash(
        {"b": 2, "a": 1},
        study_base_sha256="study",
        vta_model_sha256="model",
        implementation_sha256="implementation",
        code_commit=None,
    )
    second = compute_input_hash(
        {"a": 1, "b": 2},
        study_base_sha256="study",
        vta_model_sha256="model",
        implementation_sha256="implementation",
        code_commit=None,
    )

    assert first == second
    assert len(first) == 64
