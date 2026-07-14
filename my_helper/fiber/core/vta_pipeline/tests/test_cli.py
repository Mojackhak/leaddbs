from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_helper.fiber.core.vta_pipeline import cli as cli_module
from my_helper.fiber.core.vta_pipeline.artifacts import expected_artifacts
from my_helper.fiber.core.vta_pipeline.cli import main
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.telemetry import (
    ProcessObservation,
    TaskOutcome,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"
MODEL_PATH = REPO_ROOT / "my_helper" / "stnsnr" / "config" / "vta_model.yaml"


@pytest.fixture
def study_path(tmp_path: Path) -> Path:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    subject_dir = tmp_path / "subject"
    reconstruction = (
        subject_dir / "reconstruction" / "sub-SNr003_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    anchor = (
        subject_dir
        / "coregistration"
        / "anat"
        / "sub-SNr003_ses-preop_space-anchorNative_desc-preproc_acq-ax_T1w.nii"
    )
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(b"anchor")
    transform = (
        subject_dir
        / "normalization"
        / "transformations"
        / "sub-SNr003_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz"
    )
    transform.parent.mkdir(parents=True)
    transform.write_bytes(b"transform")
    patient_mask = (
        subject_dir
        / "atlases"
        / "Custom_Ewert_Zhang_Middlebrooks"
        / "gm_mask.nii.gz"
    )
    patient_mask.parent.mkdir(parents=True)
    patient_mask.write_bytes(b"mask")
    path = tmp_path / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


def common_args(command: str, study_path: Path) -> list[str]:
    return [
        command,
        "--study-base",
        str(study_path),
        "--vta-model",
        str(MODEL_PATH),
        "--subject",
        "SNr003",
    ]


def test_subject_selection_is_required(study_path: Path) -> None:
    result = main(
        [
            "plan",
            "--study-base",
            str(study_path),
            "--vta-model",
            str(MODEL_PATH),
        ]
    )

    assert result == 2


def test_validate_reports_subject_and_task_counts(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(common_args("validate", study_path)) == 0

    assert capsys.readouterr().out.strip() == "valid subjects=1 tasks=4"


def test_plan_is_deterministic_and_read_only(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = common_args("plan", study_path)
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    assert len(first.strip().splitlines()) == 4
    assert not (study_path.parent / "subject" / "stimulations").exists()


def test_plan_reports_identifiers_and_head_model_path_state(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = common_args("plan", study_path)
    assert main(args) == 0
    initial = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    required_identifiers = {
        "phase_id",
        "program_id",
        "electrode_id",
        "frequency_group_id",
        "delivery_mode",
    }
    assert all(required_identifiers <= row.keys() for row in initial)
    assert {row["head_model"]["status"] for row in initial} == {
        "build_required"
    }
    expected_names = {
        "L": "sub-SNr003_desc-headmodel2.mat",
        "R": "sub-SNr003_desc-headmodel1.mat",
    }
    assert all(
        Path(row["head_model"]["path"]).name == expected_names[row["hemisphere"]]
        for row in initial
    )

    right_path = Path(
        next(row for row in initial if row["hemisphere"] == "R")["head_model"][
            "path"
        ]
    )
    right_path.parent.mkdir(parents=True)
    right_path.write_bytes(b"head model")

    assert main(args) == 0
    updated = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {
        row["head_model"]["status"]
        for row in updated
        if row["hemisphere"] == "R"
    } == {"reuse_existing"}
    assert {
        row["head_model"]["status"]
        for row in updated
        if row["hemisphere"] == "L"
    } == {"build_required"}


def test_status_reports_every_space_leaf(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(common_args("status", study_path)) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert len(rows) == 8
    assert {row["status"] for row in rows} == {"missing"}
    assert {row["space"] for row in rows} == {
        "native",
        "MNI152NLin2009bAsym",
    }


def test_resume_and_force_are_mutually_exclusive(study_path: Path) -> None:
    result = main(
        common_args("run", study_path) + ["--resume", "--force"]
    )

    assert result == 2


def test_run_uses_matlab_bridge_and_reports_summary(
    study_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeBridge:
        def __init__(self, **kwargs):
            pass

        def run_subject_manifest(self, subject, run_id):
            outcomes = []
            for task in subject.tasks:
                for space in task.model.spaces:
                    for artifact in expected_artifacts(
                        leaf_directory(task, space),
                        task.model.thresholds_v_per_m,
                    ):
                        artifact.parent.mkdir(parents=True, exist_ok=True)
                        artifact.write_bytes(b"artifact")
                outcomes.append(TaskOutcome(task.task_id, "generated", 0, 8))
            return ProcessObservation(
                run_id,
                subject.subject_id,
                tuple(outcomes),
                (),
                True,
                0,
            )

    monkeypatch.setattr(cli_module, "MatlabBridge", FakeBridge, raising=False)

    assert main(common_args("run", study_path)) == 0

    summary = json.loads(capsys.readouterr().out)
    assert summary == {
        "copied": 0,
        "failed": 0,
        "generated": 4,
        "recovered_complete": 0,
        "skipped_existing": 0,
        "skipped_dependency": 0,
        "subject_process_failed": 0,
    }


def test_unknown_selector_returns_nonzero(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(common_args("plan", study_path) + ["--phase", "T9"]) == 2

    assert "Unknown phase selector" in capsys.readouterr().err


def test_validate_rejects_labelled_mask_as_native_anchor(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    subject_dir = study_path.parent / "subject"
    anchor = next(
        path
        for path in (subject_dir / "coregistration" / "anat").glob("*T1w.nii")
        if "_label-" not in path.name
    )
    labelled_mask = anchor.with_name(
        anchor.name.replace("desc-preproc_", "desc-preproc_label-Brain_")
    )
    anchor.rename(labelled_mask)

    assert main(common_args("validate", study_path)) == 2
    assert "Missing native T1w anchor" in capsys.readouterr().err
