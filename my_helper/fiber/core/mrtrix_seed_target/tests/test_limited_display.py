"""Coverage-limited display must retain source identity without changing native data."""

from pathlib import Path
import csv
from types import SimpleNamespace

import nibabel as nib
import numpy as np
import pytest

from ..errors import ValidationError
from ..limited_display import (
    contiguous_intervals, export_seed, map_display_points,
    preservation_snapshot, verify_fragments,
    roundtrip_metrics, geometry_qc, run_selected,
    matrix_pair_qc,
)
from ..tck import iter_tck, write_generated_tck
from ..tractogram_space import PointField, apply_point_field


def field(shape=(7, 7, 7), displacement=(0, 0, 0), affine=None):
    affine = np.eye(4) if affine is None else affine
    vectors = np.zeros((*shape, 3), dtype=np.float32)
    vectors[:] = displacement
    image = nib.Nifti1Image(vectors[..., None, :], affine)
    return PointField(Path("synthetic.nii"), image, vectors, np.linalg.inv(affine))


@pytest.mark.parametrize("valid,expected,isolated", [
    ([1, 1, 0, 1, 1], [(0, 2), (3, 5)], 0),
    ([0, 1, 0, 1, 0], [], 2),
    ([0, 0], [], 0),
    ([1, 1], [(0, 2)], 0),
    ([1, 0, 1, 1, 0, 1], [(2, 4)], 2),
])
def test_runs_do_not_join_gaps(valid, expected, isolated):
    assert contiguous_intervals(np.asarray(valid, dtype=bool)) == (expected, isolated)


def test_direct_mapping_matches_existing_oblique_field():
    affine = np.array([[1, .2, 0, -3], [0, 1, .1, -2], [0, 0, 1, -1], [0, 0, 0, 1]])
    primary = field(displacement=(.1, .2, .3), affine=affine)
    reverse = field(shape=(20, 20, 20), affine=np.diag([1, 1, 1, 1]))
    points = nib.affines.apply_affine(affine, np.array([[4, 4, 4], [5, 5, 5]]))
    mapped, codes = map_display_points(points, primary, reverse)
    np.testing.assert_allclose(mapped, apply_point_field(points, primary))
    assert codes.tolist() == [0, 0]


def test_inverse_recovers_only_converged_points():
    primary = field(shape=(3, 7, 7), displacement=(2, 0, 0))
    reverse = field(shape=(10, 7, 7), displacement=(-2, 0, 0))
    mapped, codes = map_display_points(np.array([[1., 1, 1], [4., 1, 1], [20., 1, 1]]), primary, reverse)
    assert codes.tolist() == [0, 1, 2]
    np.testing.assert_allclose(mapped[:2], [[3, 1, 1], [6, 1, 1]])
    assert np.isnan(mapped[2]).all()


def test_direct_solution_outside_mni_fov_is_missing():
    mapped, codes = map_display_points(np.array([[1., 1, 1]]), field(displacement=(20, 0, 0)), field())
    assert codes.tolist() == [3]
    assert np.isnan(mapped).all()


def test_export_exhaustive_ids_and_preserves_source(tmp_path):
    source = tmp_path / "native.tck"
    xs = [[1, 2, 3], [1, 2, 20, 3, 4], [20, 21], [1, 20, 2]]
    native = [np.column_stack([x, np.ones(len(x)), np.ones(len(x))]).astype(np.float32) for x in xs]
    write_generated_tck(lambda: iter(native), source, len(native))
    before = preservation_snapshot([source], [source])
    dest = tmp_path / "display"
    counts, overview, detail = export_seed(
        source=source, destination=dest, subject_id="subject", seed_key="lh/seed",
        expected_count=4, matrix=np.eye(4), primary=field(), reverse=field(),
        preview_budget=4, point_budget=5,
    )
    assert (counts["intact"], counts["truncated"], counts["not_displayed"], counts["fragments"]) == (1, 1, 2, 3)
    assert counts["isolated_valid_points"] == 2
    actual = list(iter_tck(dest / "fragments.tck"))
    for a, b in zip(actual, [native[0], native[1][:2], native[1][3:]]):
        np.testing.assert_array_equal(a, b)
    with (dest / "fragment_map.csv").open() as handle:
        mapping = list(csv.DictReader(handle))
    assert [r["source_fiber_id"] for r in mapping] == ["subject:lh/seed:0", "subject:lh/seed:1", "subject:lh/seed:1"]
    assert [(r["point_start_inclusive"], r["point_stop_exclusive"]) for r in mapping] == [("0", "3"), ("0", "2"), ("3", "5")]
    assert verify_fragments(dest, counts, field())["id_intervals_verified"]
    assert before == preservation_snapshot([source], [source])
    assert len(overview) == 3 and len(detail) == 2
    with pytest.raises(FileExistsError):
        export_seed(source=source, destination=dest, subject_id="subject", seed_key="lh/seed",
                    expected_count=4, matrix=np.eye(4), primary=field(), reverse=field(), preview_budget=4)


def test_empty_display_is_a_valid_zero_fragment_tck(tmp_path):
    source = tmp_path / "native.tck"
    write_generated_tck(lambda: iter([np.array([[20., 1, 1], [21., 1, 1]])]), source, 1)
    counts, _, _ = export_seed(source=source, destination=tmp_path / "display",
                              subject_id="s", seed_key="rh/seed", expected_count=1,
                              matrix=np.eye(4), primary=field(), reverse=field(), preview_budget=1)
    assert counts["not_displayed"] == 1
    assert list(iter_tck(tmp_path / "display/fragments.tck")) == []
    assert verify_fragments(tmp_path / "display", counts, field())["fragment_count"] == 0


def test_existing_roundtrip_thresholds_and_empty_sample():
    assert roundtrip_metrics([]) == {"count": 0, "thresholds_met": None}
    assert roundtrip_metrics([.05] * 100)["thresholds_met"]
    assert not roundtrip_metrics([.050001] * 100)["thresholds_met"]
    assert not roundtrip_metrics([0.] * 94 + [.200001] * 6)["thresholds_met"]
    assert not roundtrip_metrics([0.] * 999 + [.500001])["thresholds_met"]


def test_selected_subjects_do_not_run_pilot(monkeypatch, tmp_path):
    from .. import limited_display as module
    specs = [SimpleNamespace(subject_id=s) for s in ["sub-Meige001", "sub-Meige002", "sub-Dys022"]]
    monkeypatch.setattr(module, "load_config", lambda _: SimpleNamespace(subjects=specs, configuration_hash="fixed"))
    called = []
    allowed = []
    def run(config, spec, **kwargs):
        called.append(spec.subject_id)
        allowed.append(kwargs["allow_matrix_qc_warning"])
        return {"subject_id": spec.subject_id, "seeds": {"lh/seed": {"source_fibers": 3}},
                "warnings": ["unchanged QC warning"], "output_directory": str(tmp_path)}
    monkeypatch.setattr(module, "run_subject", run)
    result = run_selected(tmp_path / "config", ["sub-Meige002", "sub-Dys022"], tmp_path / "summary",
                          matrix_qc_warning_subjects=["sub-Dys022"])
    assert called == ["sub-Meige002", "sub-Dys022"]
    assert allowed == [False, True]
    assert result["completed_subjects"] == 2
    assert result["subjects"][0]["warnings"] == ["unchanged QC warning"]
    with pytest.raises(ValidationError):
        run_selected(tmp_path / "config", ["sub-missing"], tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_interrupted_receipt_resumes_only_remaining_subject(monkeypatch, tmp_path):
    from .. import limited_display as module
    specs = [SimpleNamespace(subject_id=s) for s in ["sub-Meige002", "sub-Meige003"]]
    monkeypatch.setattr(module, "load_config", lambda _: SimpleNamespace(subjects=specs, configuration_hash="fixed"))
    calls = []
    def run(config, spec, **kwargs):
        calls.append(spec.subject_id)
        if len(calls) == 2:
            raise InterruptedError("simulated execution interruption")
        return {"subject_id": spec.subject_id, "seeds": {"lh/seed": {"source_fibers": 3}},
                "warnings": [], "output_directory": str(tmp_path)}
    monkeypatch.setattr(module, "run_subject", run)
    ids = [s.subject_id for s in specs]
    with pytest.raises(InterruptedError):
        run_selected(tmp_path / "config", ids, tmp_path / "summary")
    result = run_selected(tmp_path / "config", ids, tmp_path / "summary", resume=True)
    assert calls == [ids[0], ids[1], ids[1]]
    assert result["completed_subjects"] == 2


def test_matrix_failure_requires_explicit_opt_in_without_changing_threshold():
    matrix, inverse = np.eye(4), np.eye(4)
    inverse[0, 3] = 2.9648774579893455e-6
    before = inverse.copy()
    with pytest.raises(ValidationError):
        matrix_pair_qc(matrix, inverse)
    result = matrix_pair_qc(matrix, inverse, allow_failure=True)
    assert not result["threshold_met"] and result["threshold"] == 1e-8
    assert result["display_warning_authorized"]
    np.testing.assert_array_equal(inverse, before)


@pytest.mark.parametrize("coordinates,warning", [([1., 2.], "expanded_roundtrip_threshold_failed"),
                                                ([20., 21.], "expanded_roundtrip_no_valid_sample")])
def test_geometry_qc_keeps_warning_and_source_ids(monkeypatch, tmp_path, coordinates, warning):
    from .. import limited_display as module
    primary, reverse = field(), field(displacement=(.6, 0, 0))
    native = np.column_stack([coordinates, np.ones(2), np.ones(2)])
    source, dest = tmp_path / "native.tck", tmp_path / "display"
    write_generated_tck(lambda: iter([native]), source, 1)
    export_seed(source=source, destination=dest, subject_id="s", seed_key="lh/seed",
                expected_count=1, matrix=np.eye(4), primary=primary, reverse=reverse, preview_budget=1)
    monkeypatch.setattr(module, "ants_reference_transform", lambda p, **_: p)
    result = geometry_qc(source=source, destination=dest, subject_id="s", seed_key="lh/seed",
                         expected_count=1, matrix=np.eye(4), inverse=np.eye(4),
                         primary=primary, reverse=reverse, ants=Path("unused"))
    assert warning in result["warnings"]
    assert result["source_coordinate_max_abs_difference_mm"] == 0
    if coordinates[0] == 1:
        assert result["expanded_sample_points_over_0_5_mm"][0]["source_fiber_id"] == "s:lh/seed:0"
        assert len(list(iter_tck(dest / "fragments.tck"))) == 1
    else:
        assert result["missing_sampled_midpoints"] == 1
