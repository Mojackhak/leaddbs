"""Static contract tests for the preparation-only MATLAB backend."""

from pathlib import Path


def test_matlab_backend_only_prepares_inverse_normalized_rois() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "tracking"
        / "mh_fiber_prepare_mrtrix_seed_target_subject.m"
    )
    text = path.read_text(encoding="utf-8")
    assert "ea_apply_normalization_tofile" in text
    assert "'GenericLabel'" in text
    assert "tckgen" not in text
    assert "parpool" not in text


def test_roi_preparation_matlab_process_disables_all_figure_windows() -> None:
    path = Path(__file__).resolve().parents[1] / "roi.py"
    text = path.read_text(encoding="utf-8")
    command = text.split("run_command(", 1)[1].split("log_path=", 1)[0]
    assert '"-noFigureWindows"' in command
    assert '"-nosplash"' in command
    assert '"-batch"' in command
