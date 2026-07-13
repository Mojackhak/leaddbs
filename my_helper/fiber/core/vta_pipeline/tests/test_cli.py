from __future__ import annotations

import json
from pathlib import Path

import pytest

from my_helper.fiber.core.vta_pipeline.cli import main


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


def test_run_is_explicitly_unavailable_until_bridge_is_installed(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(common_args("run", study_path)) == 2

    assert "execution backend is not installed" in capsys.readouterr().err


def test_unknown_selector_returns_nonzero(
    study_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(common_args("plan", study_path) + ["--phase", "T9"]) == 2

    assert "Unknown phase selector" in capsys.readouterr().err
