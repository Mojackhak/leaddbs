from __future__ import annotations

from pathlib import Path

from my_helper.fiber.core.vta_pipeline.artifacts import (
    LeafStatus,
    atomic_copy_missing,
    expected_artifacts,
    leaf_status,
    missing_artifacts,
    move_leaf_to_trash,
)


THRESHOLDS = (180.0, 200.0, 220.0)


def write_all_artifacts(leaf: Path) -> tuple[Path, ...]:
    artifacts = expected_artifacts(leaf, THRESHOLDS)
    leaf.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts:
        artifact.write_bytes(artifact.name.encode("ascii"))
    return artifacts


def test_leaf_is_complete_only_when_all_expected_paths_exist(
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "leaf"

    artifacts = write_all_artifacts(leaf)
    assert leaf_status(leaf, THRESHOLDS) is LeafStatus.COMPLETE

    artifacts[-1].unlink()
    assert leaf_status(leaf, THRESHOLDS) is LeafStatus.MISSING
    assert missing_artifacts(leaf, THRESHOLDS) == (artifacts[-1],)


def test_existing_files_are_completion_signals_without_provenance(
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "leaf"
    write_all_artifacts(leaf)

    assert leaf_status(leaf, THRESHOLDS) is LeafStatus.COMPLETE
    assert not (leaf / "provenance.json").exists()


def test_atomic_copy_missing_never_overwrites_existing_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.nii.gz"
    destination = tmp_path / "leaf" / "efield.nii.gz"
    source.write_bytes(b"donor")
    destination.parent.mkdir()
    destination.write_bytes(b"existing")

    assert atomic_copy_missing(source, destination) == "skipped_existing"
    assert destination.read_bytes() == b"existing"

    destination.unlink()
    assert atomic_copy_missing(source, destination) == "copied"
    assert destination.read_bytes() == b"donor"


def test_force_moves_leaf_to_trash_without_permanent_deletion(
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "leaf"
    trash = tmp_path / "Trash"
    leaf.mkdir()
    (leaf / "efield.nii.gz").write_bytes(b"old")

    moved = move_leaf_to_trash(leaf, trash_root=trash)

    assert not leaf.exists()
    assert moved.is_dir()
    assert (moved / "efield.nii.gz").read_bytes() == b"old"
