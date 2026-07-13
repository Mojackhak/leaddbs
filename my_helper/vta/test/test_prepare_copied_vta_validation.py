"""Tests for isolated copied-subject VTA validation preparation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PATH = Path(__file__).with_name("prepare_copied_vta_validation.py")
PRODUCTION_ROOT = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs")


def _load_module():
    assert MODULE_PATH.is_file(), "copied-subject preparation helper is missing"
    spec = importlib.util.spec_from_file_location(
        "prepare_copied_vta_validation", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_study_base(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    dataset_root = tmp_path / "source"
    dataset_root.mkdir()
    dataset_root.joinpath("dataset_description.json").write_text(
        json.dumps({"Name": "Fixture", "BIDSVersion": "1.6.0"}) + "\n",
        encoding="utf-8",
    )
    source_root = dataset_root / "derivatives" / "leaddbs"
    paths: dict[str, Path] = {}
    subjects = []
    for subject_id in ("SNr003", "SNr004"):
        subject_dir = source_root / f"sub-{subject_id}"
        reconstruction = (
            subject_dir
            / "reconstruction"
            / f"sub-{subject_id}_desc-reconstruction.mat"
        )
        reconstruction.parent.mkdir(parents=True)
        reconstruction.write_bytes(f"reconstruction:{subject_id}".encode())
        (subject_dir / "source-marker.txt").write_text(subject_id, encoding="utf-8")
        paths[subject_id] = subject_dir
        subjects.append(
            {
                "subject_id": subject_id,
                "subject_label": f"Label {subject_id}",
                "subject_sources": {
                    "leaddbs_subject_dir": str(subject_dir),
                    "electrode_reconstruction": {"path": str(reconstruction)},
                },
                "payload": {"must_be_preserved": True},
            }
        )

    study_base = tmp_path / "input" / "study_base.json"
    study_base.parent.mkdir()
    study_base.write_text(
        json.dumps(
            {
                "schema_version": "dual_frequency_study_v1",
                "study": {
                    "study_id": "fixture",
                    "subjects": subjects,
                    "other_study_data": {"must_be_preserved": True},
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return study_base, paths


def test_prepare_validation_copy_never_points_to_production(tmp_path: Path) -> None:
    module = _load_module()
    study_base, source_paths = _write_study_base(tmp_path)
    work_root = tmp_path / "validation"

    output = module.prepare_validation_copy(
        study_base, "SNr003", work_root, "test-run"
    )

    raw = json.loads(output.read_text(encoding="utf-8"))
    assert output == (work_root / "vta_pipeline_e2e_test-run" / "study_base.json")
    assert output.is_absolute()
    assert len(raw["study"]["subjects"]) == 1
    subject = raw["study"]["subjects"][0]
    assert subject["subject_id"] == "SNr003"
    assert subject["payload"] == {"must_be_preserved": True}
    assert raw["study"]["other_study_data"] == {"must_be_preserved": True}

    copied_subject = Path(subject["subject_sources"]["leaddbs_subject_dir"])
    copied_reconstruction = Path(
        subject["subject_sources"]["electrode_reconstruction"]["path"]
    )
    copied_dataset = output.parent / "copied_dataset"
    assert copied_subject == (
        copied_dataset / "derivatives" / "leaddbs" / "sub-SNr003"
    )
    assert json.loads(
        copied_dataset.joinpath("dataset_description.json").read_text()
    )["Name"] == "Fixture"
    assert copied_reconstruction == (
        copied_subject
        / "reconstruction"
        / "sub-SNr003_desc-reconstruction.mat"
    )
    assert copied_subject != source_paths["SNr003"]
    assert copied_subject.joinpath("source-marker.txt").read_text() == "SNr003"
    assert copied_reconstruction.read_bytes() == b"reconstruction:SNr003"
    assert not copied_dataset.joinpath(
        "derivatives", "leaddbs", "sub-SNr004"
    ).exists()
    assert not copied_subject.is_relative_to(PRODUCTION_ROOT)


@pytest.mark.parametrize(
    "work_root",
    [
        PRODUCTION_ROOT,
        PRODUCTION_ROOT / "validation",
    ],
)
def test_prepare_validation_copy_rejects_production_work_root(
    tmp_path: Path, work_root: Path
) -> None:
    module = _load_module()
    study_base, _ = _write_study_base(tmp_path)

    with pytest.raises(ValueError, match="production Lead-DBS tree"):
        module.prepare_validation_copy(
            study_base, "SNr003", work_root, "test-run"
        )


def test_prepare_validation_copy_rejects_unknown_subject(tmp_path: Path) -> None:
    module = _load_module()
    study_base, _ = _write_study_base(tmp_path)

    with pytest.raises(ValueError, match="Unknown subject_id"):
        module.prepare_validation_copy(
            study_base, "SNr999", tmp_path / "validation", "test-run"
        )


@pytest.mark.parametrize(
    "run_id",
    ["../escape", "nested/path", "/absolute", "", ".", ".."],
)
def test_prepare_validation_copy_rejects_unsafe_run_id(
    tmp_path: Path,
    run_id: str,
) -> None:
    module = _load_module()
    study_base, _ = _write_study_base(tmp_path)
    work_root = tmp_path / "validation"

    with pytest.raises(ValueError, match="safe path component"):
        module.prepare_validation_copy(
            study_base, "SNr003", work_root, run_id
        )

    assert not work_root.exists()


def test_prepare_validation_copy_does_not_overwrite_existing_run(
    tmp_path: Path,
) -> None:
    module = _load_module()
    study_base, _ = _write_study_base(tmp_path)
    work_root = tmp_path / "validation"
    module.prepare_validation_copy(study_base, "SNr003", work_root, "test-run")

    with pytest.raises(FileExistsError, match="already exists"):
        module.prepare_validation_copy(
            study_base, "SNr003", work_root, "test-run"
        )


def test_cli_prints_only_absolute_output_path(tmp_path: Path) -> None:
    _load_module()
    study_base, _ = _write_study_base(tmp_path)
    work_root = tmp_path / "validation"

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--study-base",
            str(study_base),
            "--subject",
            "SNr003",
            "--work-root",
            str(work_root),
            "--run-id",
            "cli-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    expected = work_root / "vta_pipeline_e2e_cli-run" / "study_base.json"
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == f"{expected.resolve()}\n"
