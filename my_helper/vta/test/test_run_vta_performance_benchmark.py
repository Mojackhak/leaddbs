"""Solver-free tests for the frozen VTA performance benchmark harness."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from my_helper.fiber.core.vta_pipeline.artifacts import expected_artifacts
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.telemetry import (
    ProcessObservation,
    StageTiming,
    TaskOutcome,
)


MODULE_PATH = Path(__file__).with_name("run_vta_performance_benchmark.py")
FIXTURE_PATH = Path(__file__).with_name("fixtures") / "vta_performance_benchmark_v1.json"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_vta_performance_benchmark", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def benchmark_module() -> ModuleType:
    return _load_module()


@pytest.fixture()
def fake_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    dataset = tmp_path / "source_dataset"
    dataset.mkdir()
    dataset.joinpath("dataset_description.json").write_text(
        json.dumps({"Name": "Benchmark fixture", "BIDSVersion": "1.6.0"})
        + "\n",
        encoding="utf-8",
    )
    subjects = [
        _subject(
            dataset,
            "SNr003",
            "Medtronic 3387",
            [
                _phase("T1", [_program(1, [_continuous("lead-R")])]),
                _phase("T2", [_program(2, [_alternating("lead-L")])]),
                _phase("T3", [_program(3, [_continuous("lead-R")])]),
            ],
        ),
        _subject(
            dataset,
            "SNr006",
            "SceneRay SR1200",
            [_phase("T2", [_program(2, [_alternating("lead-L")])])],
        ),
        _subject(
            dataset,
            "SNr011",
            "SceneRay SR1202",
            [_phase("T2", [_program(2, [_continuous("lead-L")])])],
        ),
    ]
    study_base = tmp_path / "input" / "study_base.json"
    study_base.parent.mkdir()
    study_base.write_text(
        json.dumps(
            {
                "schema_version": "dual_frequency_study_v1",
                "study": {"study_id": "benchmark-fixture", "subjects": subjects},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    vta_model = tmp_path / "input" / "vta_model.yaml"
    vta_model.write_text(
        """schema_version: vta_model_v1
profile_type: vta_model
fem:
  conductivity_s_per_m:
    gray_matter: 0.33
    white_matter: 0.14
  atlas_set: Custom_Ewert_Zhang_Middlebrooks
outputs:
  spaces:
    - native
    - MNI152NLin2009bAsym
  binary_vta:
    primary_threshold_v_per_mm: 0.20
    sensitivity_thresholds_v_per_mm:
      - 0.18
      - 0.22
""",
        encoding="utf-8",
    )

    module = _load_module()
    fixture = module.load_fixture(FIXTURE_PATH)
    complete_case = next(
        case
        for case in fixture["cases"]
        if case["case_id"] == "snr003_t1_p1_r_complete_resume"
    )
    task = module.resolve_case_tasks(study_base, vta_model, complete_case)[0]
    for space in fixture["spaces"]:
        for index, artifact in enumerate(
            expected_artifacts(
                leaf_directory(task, space), task.model.thresholds_v_per_m
            )
        ):
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_bytes(f"{space}:{index}".encode("ascii"))
    return study_base, vta_model, dataset


def test_fixture_freezes_payloads_and_pair_order(benchmark_module: ModuleType) -> None:
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)

    assert fixture["payloads"]["current_single_cathode_case_return"] == {
        "case_id": "R_single_cathode_case_return",
        "hemisphere": "R",
        "design": "single_cathode_case_return",
        "control_mode": "current",
        "unit": "mA",
        "amplitude_mA": 4.7761121690289734,
        "pulse_width_us": 90,
        "frequency_hz": 130,
        "contacts": [
            {"contact": 4, "polarity": "cathode", "fraction": 1.0},
            {"contact": "case", "polarity": "anode", "fraction": 1.0},
        ],
    }
    synthetic = fixture["payloads"]["synthetic_continuous_multi_source"]
    assert [source["source_id"] for source in synthetic["sources"]] == [
        "source-1",
        "source-2",
    ]
    assert [source["contacts"][0]["contact"] for source in synthetic["sources"]] == [
        1,
        2,
    ]
    assert all(
        source["frequency_hz"] == 130
        and source["amplitude_v"] == 2.0
        and source["pulse_width_us"] == 60
        for source in synthetic["sources"]
    )
    assert benchmark_module.paired_order_schedule(fixture) == (
        ("baseline", "candidate"),
        ("candidate", "baseline"),
        ("baseline", "candidate"),
        ("candidate", "baseline"),
        ("baseline", "candidate"),
    )


def test_every_fixture_selector_resolves_uniquely(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
) -> None:
    study_base, vta_model, _ = fake_inputs

    result = benchmark_module.validate_benchmark_inputs(study_base, vta_model)

    assert len(result["semantic_tasks"]) == 9
    assert sum(len(tasks) for tasks in result["semantic_tasks"].values()) == 13


def test_selector_validation_rejects_missing_match(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)
    fixture["cases"][0]["selector"]["subject_id"] = "SNr999"
    invalid_fixture = tmp_path / "invalid_fixture.json"
    invalid_fixture.write_text(json.dumps(fixture), encoding="utf-8")

    with pytest.raises(ValueError, match="resolve exactly once"):
        benchmark_module.validate_benchmark_inputs(
            study_base, vta_model, fixture_path=invalid_fixture
        )


def test_prepare_materializes_threshold_repair_and_complete_resume(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, tzinfo=timezone.utc),
        trash_root=tmp_path / "Trash",
    )
    resolved_fixture = json.loads(root.joinpath("fixture.json").read_text())

    assert root.name == "vta_performance_benchmark_20260714T000000000000Z"
    assert (root / "working" / "baseline").is_dir()
    assert (root / "working" / "candidate").is_dir()
    assert (root / "runs").is_dir()
    assert all("resolved_task_ids" in case for case in resolved_fixture["cases"])

    threshold_case = _case(resolved_fixture, "snr003_t1_p1_r_threshold_repair")
    threshold_snapshot = root / threshold_case["snapshot"]
    threshold_task = benchmark_module.resolve_case_tasks(
        threshold_snapshot / "study_base.json",
        threshold_snapshot / "vta_model.yaml",
        threshold_case,
    )[0]
    for space in resolved_fixture["spaces"]:
        artifacts = expected_artifacts(
            leaf_directory(threshold_task, space),
            threshold_task.model.thresholds_v_per_m,
        )
        assert artifacts[0].is_file()
        assert all(not path.exists() for path in artifacts[1:])

    complete_case = _case(resolved_fixture, "snr003_t1_p1_r_complete_resume")
    complete_snapshot = root / complete_case["snapshot"]
    complete_task = benchmark_module.resolve_case_tasks(
        complete_snapshot / "study_base.json",
        complete_snapshot / "vta_model.yaml",
        complete_case,
    )[0]
    for space in resolved_fixture["spaces"]:
        assert all(
            path.is_file()
            for path in expected_artifacts(
                leaf_directory(complete_task, space),
                complete_task.model.thresholds_v_per_m,
            )
        )

    continuous_case = _case(
        resolved_fixture,
        "snr003_t1_p1_r_continuous_warm",
    )
    continuous_manifest = json.loads(
        (root / continuous_case["snapshot"] / "snapshot_manifest.json").read_text()
    )
    assert continuous_manifest["donor_artifacts"]
    assert all(
        not item["present"] for item in continuous_manifest["donor_artifacts"]
    )
    frozen_continuous = root / continuous_case["snapshot"]
    working_continuous = tmp_path / "working-continuous"
    benchmark_module.restore_snapshot(
        frozen_continuous,
        working_continuous,
        trash_root=tmp_path / "Trash",
    )
    donor_relative = Path(continuous_manifest["donor_artifacts"][0]["path"])
    stale_donor = working_continuous / donor_relative
    stale_donor.parent.mkdir(parents=True, exist_ok=True)
    stale_donor.write_bytes(b"stale donor")
    benchmark_module.restore_snapshot(
        frozen_continuous,
        working_continuous,
        trash_root=tmp_path / "Trash",
    )
    assert not (working_continuous / donor_relative).exists()


def test_prepare_filters_case_and_installs_context_matched_warm_donor(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, dataset = fake_inputs
    source_subject = dataset / "derivatives" / "leaddbs" / "sub-SNr003"
    source_headmodel = (
        source_subject
        / "headmodel"
        / "native"
        / "sub-SNr003_desc-headmodel2.mat"
    )
    source_headmodel.unlink()
    source_mask = (
        source_subject
        / "atlases"
        / "Custom_Ewert_Zhang_Middlebrooks"
        / "gm_mask.nii.gz"
    )
    source_mask.parent.mkdir(parents=True)
    source_mask.write_bytes(b"matched patient mask")
    source_reconstruction = (
        source_subject
        / "reconstruction"
        / "sub-SNr003_desc-reconstruction.mat"
    )

    donor_subject = (
        tmp_path / "donor" / "derivatives" / "leaddbs" / "sub-SNr003"
    )
    donor_reconstruction = (
        donor_subject
        / "reconstruction"
        / "sub-SNr003_desc-reconstruction.mat"
    )
    donor_reconstruction.parent.mkdir(parents=True)
    donor_reconstruction.write_bytes(source_reconstruction.read_bytes())
    donor_mask = (
        donor_subject
        / "atlases"
        / "Custom_Ewert_Zhang_Middlebrooks"
        / "gm_mask.nii.gz"
    )
    donor_mask.parent.mkdir(parents=True)
    donor_mask.write_bytes(source_mask.read_bytes())
    donor_headmodel = (
        donor_subject
        / "headmodel"
        / "native"
        / "sub-SNr003_desc-headmodel2.mat"
    )
    donor_headmodel.parent.mkdir(parents=True)
    donor_headmodel.write_bytes(b"validated warm headmodel")

    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        case_ids=(benchmark_module.REPRESENTATIVE_CASE_ID,),
        warm_headmodel_donor=donor_headmodel,
        now=lambda: datetime(2026, 7, 14, 0, 30, tzinfo=timezone.utc),
        trash_root=tmp_path / "Trash",
    )
    resolved = json.loads(root.joinpath("fixture.json").read_text())
    assert resolved["prepared_case_ids"] == [
        benchmark_module.REPRESENTATIVE_CASE_ID
    ]
    assert [case["case_id"] for case in resolved["cases"]] == [
        benchmark_module.REPRESENTATIVE_CASE_ID
    ]
    assert len(list(root.joinpath("frozen_input").iterdir())) == 1
    snapshot = root / resolved["cases"][0]["snapshot"]
    manifest = json.loads(
        snapshot.joinpath("snapshot_manifest.json").read_text()
    )
    source = manifest["warm_headmodel_source"]
    assert source["mode"] == "explicit_validated_donor"
    assert source["donor_path"] == str(donor_headmodel)
    headmodel_entry = next(
        item for item in source["snapshot_files"] if item["role"] == "headmodel"
    )
    frozen_headmodel = snapshot / headmodel_entry["path"]
    assert frozen_headmodel.read_bytes() == b"validated warm headmodel"
    assert source["reconstruction_sha256"] == benchmark_module._sha256_file(
        source_reconstruction
    )
    assert source["patient_gm_mask_sha256"] == benchmark_module._sha256_file(
        source_mask
    )

    frozen_headmodel.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="headmodel hash changed"):
        benchmark_module.restore_snapshot(
            snapshot,
            tmp_path / "tampered-restore",
            trash_root=tmp_path / "Trash",
        )


def test_prepare_rejects_warm_donor_context_mismatch(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, dataset = fake_inputs
    source_subject = dataset / "derivatives" / "leaddbs" / "sub-SNr003"
    source_headmodel = (
        source_subject
        / "headmodel"
        / "native"
        / "sub-SNr003_desc-headmodel2.mat"
    )
    source_headmodel.unlink()
    source_mask = (
        source_subject
        / "atlases"
        / "Custom_Ewert_Zhang_Middlebrooks"
        / "gm_mask.nii.gz"
    )
    source_mask.parent.mkdir(parents=True)
    source_mask.write_bytes(b"source mask")
    donor_subject = tmp_path / "donor" / "sub-SNr003"
    donor_reconstruction = (
        donor_subject
        / "reconstruction"
        / "sub-SNr003_desc-reconstruction.mat"
    )
    donor_reconstruction.parent.mkdir(parents=True)
    donor_reconstruction.write_bytes(
        source_subject.joinpath(
            "reconstruction", "sub-SNr003_desc-reconstruction.mat"
        ).read_bytes()
    )
    donor_mask = (
        donor_subject
        / "atlases"
        / "Custom_Ewert_Zhang_Middlebrooks"
        / "gm_mask.nii.gz"
    )
    donor_mask.parent.mkdir(parents=True)
    donor_mask.write_bytes(b"different mask")
    donor_headmodel = (
        donor_subject
        / "headmodel"
        / "native"
        / "sub-SNr003_desc-headmodel2.mat"
    )
    donor_headmodel.parent.mkdir(parents=True)
    donor_headmodel.write_bytes(b"headmodel")

    with pytest.raises(ValueError, match="patient_gm_mask context differs"):
        benchmark_module.prepare_benchmark(
            study_base,
            vta_model,
            tmp_path / "validation",
            case_ids=(benchmark_module.REPRESENTATIVE_CASE_ID,),
            warm_headmodel_donor=donor_headmodel,
            now=lambda: datetime(2026, 7, 14, 0, 45, tzinfo=timezone.utc),
            trash_root=tmp_path / "Trash",
        )


def test_prepare_case_selectors_reject_duplicates_and_unknown(
    benchmark_module: ModuleType,
) -> None:
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)
    with pytest.raises(ValueError, match="must be unique"):
        benchmark_module._select_prepare_cases(fixture, ("x", "x"))
    with pytest.raises(ValueError, match="Unknown prepare case"):
        benchmark_module._select_prepare_cases(fixture, ("unknown",))


def test_restore_snapshot_moves_stale_tree_to_trash(
    benchmark_module: ModuleType,
    tmp_path: Path,
) -> None:
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    frozen.joinpath("selected.txt").write_text("frozen", encoding="utf-8")
    frozen.joinpath("donor.txt").write_text("donor", encoding="utf-8")
    working = tmp_path / "working"
    working.mkdir()
    working.joinpath("selected.txt").write_text("changed", encoding="utf-8")
    working.joinpath("untracked-output.txt").write_text("stale", encoding="utf-8")
    trash = tmp_path / "Trash"

    benchmark_module.restore_snapshot(frozen, working, trash_root=trash)

    assert working.joinpath("selected.txt").read_text() == "frozen"
    assert working.joinpath("donor.txt").read_text() == "donor"
    assert not working.joinpath("untracked-output.txt").exists()
    moved = list(trash.iterdir())
    assert len(moved) == 1
    assert moved[0].joinpath("untracked-output.txt").read_text() == "stale"


def test_restore_rejects_overlapping_source_and_destination(
    benchmark_module: ModuleType,
    tmp_path: Path,
) -> None:
    frozen = tmp_path / "frozen"
    frozen.mkdir()

    with pytest.raises(ValueError, match="must be disjoint"):
        benchmark_module.restore_snapshot(frozen, frozen)
    with pytest.raises(ValueError, match="must be disjoint"):
        benchmark_module.restore_snapshot(frozen, frozen / "working")


def test_run_baseline_restores_every_case_and_uses_three_workers(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    trash = tmp_path / "Trash"
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 1, tzinfo=timezone.utc),
        trash_root=trash,
    )
    fixture = json.loads(root.joinpath("fixture.json").read_text())
    expected_by_case = {case["case_id"]: case for case in fixture["cases"]}
    seen: set[str] = set()
    commands: list[tuple[str, ...]] = []

    def fake_runner(command: tuple[str, ...]) -> dict[str, Any]:
        commands.append(command)
        assert command[command.index("--workers") + 1] == "3"
        study_path = Path(command[command.index("--study-base") + 1])
        case_id = study_path.parent.name
        marker = study_path.parent / "stale-between-runs.txt"
        if case_id in seen:
            assert not marker.exists()
        marker.write_text("must be reset", encoding="utf-8")
        seen.add(case_id)
        counts = expected_by_case[case_id]["expected_counts"]["baseline"]
        summary = {
            "generated": counts["matlab_process_count"],
            "copied": counts["copy_count"],
            "skipped_existing": counts["skip_count"],
            "failed": 0,
            "skipped_dependency": 0,
            "benchmark_counts": counts,
        }
        return {"returncode": 0, "stdout": json.dumps(summary) + "\n"}

    summary = benchmark_module.run_baseline(
        root,
        command_runner=fake_runner,
        trash_root=trash,
    )

    assert len(commands) == 9 * 6
    assert summary["status"] == "baseline_complete"
    assert summary["case_run_count"] == 9 * 6
    assert [run["repetition_index"] for run in summary["measured"]] == [1, 2, 3, 4, 5]
    assert summary["workers_requested"] == 3
    assert summary["concurrency_measurement"] == "not_measured_single_subject_cases"
    assert summary["future_paired_order_status"] == (
        "not_executed_candidate_deferred"
    )
    assert json.loads(root.joinpath("benchmark_summary.json").read_text())[
        "candidate_binding"
    ] == "deferred"


def test_rejects_work_root_under_authoritative_derivatives(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
) -> None:
    study_base, vta_model, dataset = fake_inputs
    authoritative = dataset / "derivatives" / "leaddbs"

    with pytest.raises(ValueError, match="authoritative derivatives"):
        benchmark_module.prepare_benchmark(
            study_base,
            vta_model,
            authoritative / "benchmark",
        )


def test_count_assertion_rejects_any_mismatch(benchmark_module: ModuleType) -> None:
    expected = {
        "matlab_process_count": 1,
        "fem_solve_count": 1,
        "derived_task_count": 0,
        "copy_count": 0,
        "skip_count": 0,
    }
    actual = deepcopy(expected)
    actual["fem_solve_count"] = 2

    with pytest.raises(ValueError, match="fem_solve_count"):
        benchmark_module.assert_expected_counts(actual, expected)


def test_run_baseline_rejects_missing_observed_counts(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 2, tzinfo=timezone.utc),
        trash_root=tmp_path / "Trash",
    )

    def fake_runner(command: tuple[str, ...]) -> dict[str, Any]:
        return {
            "returncode": 0,
            "stdout": json.dumps(
                {
                    "generated": 1,
                    "copied": 0,
                    "skipped_existing": 0,
                    "failed": 0,
                    "skipped_dependency": 0,
                }
            ),
        }

    with pytest.raises(ValueError, match="no observed execution counts"):
        benchmark_module.run_baseline(
            root,
            command_runner=fake_runner,
            trash_root=tmp_path / "Trash",
        )


def test_restore_rejects_authoritative_destination(
    benchmark_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authoritative = tmp_path / "dataset" / "derivatives" / "leaddbs"
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    monkeypatch.setattr(
        benchmark_module,
        "AUTHORITATIVE_LEADDBS_ROOT",
        authoritative,
    )

    with pytest.raises(ValueError, match="authoritative derivatives"):
        benchmark_module.restore_snapshot(
            frozen,
            authoritative / "sub-SNr003" / "benchmark",
        )


def test_run_baseline_rejects_root_under_recorded_authoritative_path(
    benchmark_module: ModuleType,
    tmp_path: Path,
) -> None:
    authoritative = tmp_path / "dataset" / "derivatives" / "leaddbs"
    root = authoritative / "benchmark"
    root.mkdir(parents=True)
    root.joinpath("fixture.json").write_text(
        json.dumps(
            {
                "schema_version": "vta_performance_benchmark_v1",
                "protected_roots": [str(authoritative)],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="authoritative derivatives"):
        benchmark_module.run_baseline(root)


def test_run_baseline_aborts_on_nonzero_case_process(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 3, tzinfo=timezone.utc),
        trash_root=tmp_path / "Trash",
    )

    with pytest.raises(RuntimeError, match="return code 1"):
        benchmark_module.run_baseline(
            root,
            command_runner=lambda command: {
                "returncode": 1,
                "stdout": "",
                "stderr": "synthetic failure",
            },
            trash_root=tmp_path / "Trash",
        )

    summary = json.loads((root / "benchmark_summary.json").read_text())
    assert summary["status"] == "prepared"


def test_public_main_returns_nonzero_when_baseline_fails(
    benchmark_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "prepared"
    monkeypatch.setattr(
        benchmark_module,
        "prepare_benchmark",
        lambda *args, **kwargs: root,
    )
    monkeypatch.setattr(
        benchmark_module,
        "run_baseline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("synthetic failure")
        ),
    )

    exit_code = benchmark_module.main(
        [
            "run-baseline",
            "--study-base",
            str(tmp_path / "study_base.json"),
            "--vta-model",
            str(tmp_path / "vta_model.yaml"),
            "--work-root",
            str(tmp_path / "validation"),
        ]
    )

    assert exit_code == 2


@pytest.mark.parametrize(
    ("failed", "skipped_dependency", "subject_process_failed", "expected_exit"),
    ((0, 0, 0, 0), (1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)),
)
def test_case_runner_exit_reflects_failure_and_dependency_skip(
    benchmark_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failed: int,
    skipped_dependency: int,
    subject_process_failed: int,
    expected_exit: int,
) -> None:
    monkeypatch.setattr(
        benchmark_module,
        "_execute_case",
        lambda *args, **kwargs: {
            "failed": failed,
            "skipped_dependency": skipped_dependency,
            "subject_process_failed": subject_process_failed,
        },
    )

    exit_code = benchmark_module._case_runner_main(
        [
            "--study-base",
            "/tmp/study_base.json",
            "--vta-model",
            "/tmp/vta_model.yaml",
            "--subject",
            "SNr003",
            "--phase",
            "T1",
            "--program",
            "1",
            "--electrode",
            "lead-R",
            "--frequency-group",
            "group-1",
            "--workers",
            "3",
        ]
    )

    assert exit_code == expected_exit


def test_compatibility_executor_runs_planner_order_and_blocks_failed_dependency(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
) -> None:
    study_base, vta_model, _ = fake_inputs
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)
    case = _case(fixture, "snr003_t2_p2_l_alternating")
    subject = benchmark_module._resolve_case_subject_plan(
        study_base, vta_model, case
    )

    class Bridge:
        def __init__(self, fail_first: bool = False) -> None:
            self.fail_first = fail_first
            self.calls: list[str] = []

        def run_task(self, task: Any, context: Any) -> Any:
            self.calls.append(task.task_id)
            if self.fail_first and len(self.calls) == 1:
                raise RuntimeError("synthetic source failure")
            for leaf in context.output_leaves.values():
                for path in expected_artifacts(
                    leaf, task.model.thresholds_v_per_m
                ):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"artifact")
            timings = (
                StageTiming(
                    scope="task",
                    task_id=task.task_id,
                    stage="fem_pcg_solve",
                    stage_status="executed",
                    cache_status=None,
                    duration_seconds=1.0,
                ),
            ) if task.kind is benchmark_module.TaskKind.ALTERNATING_SOURCE else ()
            return ProcessObservation(
                run_id="run",
                subject_id=task.subject_id,
                outcomes=(TaskOutcome(task.task_id, "generated", 0, 1),),
                timings=timings,
                protocol_complete=True,
                returncode=0,
            )

    passing_delegate = Bridge()
    passing_bridge = benchmark_module._RecordingBridge(passing_delegate)
    passing = benchmark_module._CompatibilityPerTaskService(
        passing_bridge, run_id="run"
    ).run((subject,), workers=3, resume=False, force=False)
    assert passing.generated == 3
    assert passing.failed == 0
    assert passing.skipped_dependency == 0
    assert passing_delegate.calls == [task.task_id for task in subject.tasks]
    assert len(passing_bridge.observations) == 3
    assert sum(
        timing.stage == "fem_pcg_solve"
        for observation in passing_bridge.observations
        for timing in observation.timings
    ) == 2

    for task in subject.tasks:
        for space in task.model.spaces:
            leaf = benchmark_module.leaf_directory(task, space)
            if leaf.exists():
                import shutil

                shutil.rmtree(leaf)
    failing_delegate = Bridge(fail_first=True)
    failing_bridge = benchmark_module._RecordingBridge(failing_delegate)
    failing = benchmark_module._CompatibilityPerTaskService(
        failing_bridge, run_id="run"
    ).run((subject,), workers=3, resume=False, force=False)
    assert failing.generated == 1
    assert failing.failed == 1
    assert failing.skipped_dependency == 1
    assert failing_delegate.calls == [
        subject.tasks[0].task_id,
        subject.tasks[1].task_id,
    ]


def test_persistent_executor_records_one_process_for_same_three_task_dag(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
) -> None:
    study_base, vta_model, _ = fake_inputs
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)
    case = _case(fixture, benchmark_module.REPRESENTATIVE_CASE_ID)
    subject = benchmark_module._resolve_case_subject_plan(
        study_base, vta_model, case
    )

    class Delegate:
        def run_subject_manifest(self, selected_subject: Any, run_id: str) -> Any:
            for task in selected_subject.tasks:
                for space in task.model.spaces:
                    leaf = benchmark_module.leaf_directory(task, space)
                    for path in expected_artifacts(
                        leaf, task.model.thresholds_v_per_m
                    ):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b"artifact")
            timings = tuple(
                StageTiming(
                    scope="task",
                    task_id=task.task_id,
                    stage="fem_pcg_solve",
                    stage_status="executed",
                    cache_status=None,
                    duration_seconds=1.0,
                )
                for task in selected_subject.tasks
                if task.kind is benchmark_module.TaskKind.ALTERNATING_SOURCE
            )
            outcomes = tuple(
                TaskOutcome(task.task_id, "generated", 0, 1)
                for task in selected_subject.tasks
            )
            return ProcessObservation(
                run_id=run_id,
                subject_id=selected_subject.subject_id,
                outcomes=outcomes,
                timings=timings,
                protocol_complete=True,
                returncode=0,
            )

    bridge = benchmark_module._RecordingBridge(Delegate())
    summary = benchmark_module.RunService(bridge, run_id="run").run(
        (subject,), workers=3, resume=False, force=False
    )
    assert summary.generated == 3
    assert len(bridge.observations) == 1
    assert sum(
        timing.stage == "fem_pcg_solve"
        for timing in bridge.observations[0].timings
    ) == 2


def test_recording_bridge_retains_partial_observation(
    benchmark_module: ModuleType,
) -> None:
    partial = SimpleNamespace(outcomes=(), timings=())

    class Delegate:
        def run_task(self, task: Any, context: Any) -> Any:
            error = RuntimeError("interrupted")
            error.partial_observation = partial
            raise error

    bridge = benchmark_module._RecordingBridge(Delegate())
    with pytest.raises(RuntimeError, match="interrupted"):
        bridge.run_task(SimpleNamespace(), SimpleNamespace())
    assert bridge.bridge_call_count == 1
    assert bridge.observations == (partial,)


def test_run_paired_uses_fixed_schedule_and_exact_fem_bound(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    trash = tmp_path / "Trash"
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 4, tzinfo=timezone.utc),
        trash_root=trash,
    )
    fixture = json.loads(root.joinpath("fixture.json").read_text())
    case = _case(fixture, "snr003_t2_p2_l_alternating")
    paths: list[str] = []
    compared: list[tuple[Path, Path]] = []

    def fake_runner(command: tuple[str, ...]) -> dict[str, Any]:
        path = command[command.index("--execution-path") + 1]
        paths.append(path)
        expected_key = "baseline" if path == "compatibility_per_task" else "candidate"
        counts = case["expected_counts"][expected_key]
        return {
            "returncode": 0,
            "stdout": json.dumps(
                {
                    "generated": 3,
                    "copied": 0,
                    "skipped_existing": 0,
                    "failed": 0,
                    "skipped_dependency": 0,
                    "benchmark_counts": counts,
                }
            ),
        }

    def fake_compare(
        reference: Path,
        candidate: Path,
        selected_case: dict[str, Any],
        spaces: tuple[str, ...],
    ) -> dict[str, Any]:
        assert reference != candidate
        assert selected_case["case_id"] == benchmark_module.REPRESENTATIVE_CASE_ID
        assert spaces == ("native", "MNI152NLin2009bAsym")
        compared.append((reference, candidate))
        return {"pass": True}

    summary = benchmark_module.run_paired(
        root,
        benchmark_module.REPRESENTATIVE_CASE_ID,
        command_runner=fake_runner,
        artifact_comparator=fake_compare,
        trash_root=trash,
    )

    assert paths == [
        "compatibility_per_task",
        "persistent_subject",
        "compatibility_per_task",
        "persistent_subject",
        "persistent_subject",
        "compatibility_per_task",
        "compatibility_per_task",
        "persistent_subject",
    ]
    assert len(compared) == 3
    assert summary["completed_fem_solve_count"] == 16
    assert summary["completed_fem_solve_limit"] == 16
    assert summary["status"] == "paired_complete"
    assert summary["three_worker_memory_gate"] == "not_measured"
    with pytest.raises(ValueError, match="single-use"):
        benchmark_module.run_paired(
            root,
            benchmark_module.REPRESENTATIVE_CASE_ID,
            command_runner=fake_runner,
            artifact_comparator=fake_compare,
            trash_root=trash,
        )


def test_run_paired_rejects_nonrepresentative_case(
    benchmark_module: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "prepared"
    root.mkdir()
    root.joinpath("fixture.json").write_text(
        json.dumps({"schema_version": "vta_performance_benchmark_v1"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="only permits"):
        benchmark_module.run_paired(root, "snr011_t2_p2_l_continuous")


def test_paired_path_records_failed_process_before_raising(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    trash = tmp_path / "Trash"
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 5, tzinfo=timezone.utc),
        trash_root=trash,
    )
    fixture = json.loads(root.joinpath("fixture.json").read_text())
    case = _case(fixture, benchmark_module.REPRESENTATIVE_CASE_ID)

    with pytest.raises(RuntimeError, match="return code 7"):
        benchmark_module._run_paired_path(
            root,
            fixture,
            case,
            execution_path="persistent_subject",
            run_label="synthetic-failure",
            repetition_index=1,
            command_runner=lambda command: {
                "returncode": 7,
                "stdout": "partial telemetry",
                "stderr": "synthetic failure",
            },
            trash_root=trash,
        )

    record = json.loads(
        root.joinpath(
            "runs",
            "synthetic-failure",
            f"{benchmark_module.REPRESENTATIVE_CASE_ID}.json",
        ).read_text()
    )
    assert record["status"] == "failed"
    assert record["returncode"] == 7
    assert record["stdout"] == "partial telemetry"


def test_run_paired_charges_nonzero_process_fem_before_failure(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    trash = tmp_path / "Trash"
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 6, tzinfo=timezone.utc),
        trash_root=trash,
    )
    fixture = json.loads(root.joinpath("fixture.json").read_text())
    case = _case(fixture, benchmark_module.REPRESENTATIVE_CASE_ID)
    counts = case["expected_counts"]["baseline"]

    with pytest.raises(RuntimeError, match="return code 9"):
        benchmark_module.run_paired(
            root,
            benchmark_module.REPRESENTATIVE_CASE_ID,
            command_runner=lambda command: {
                "returncode": 9,
                "stdout": json.dumps(
                    {
                        "generated": 2,
                        "copied": 0,
                        "skipped_existing": 0,
                        "failed": 1,
                        "skipped_dependency": 0,
                        "benchmark_counts": counts,
                    }
                ),
                "stderr": "late process failure",
            },
            artifact_comparator=lambda *args: {"pass": True},
            trash_root=trash,
        )

    summary = json.loads(root.joinpath("benchmark_summary.json").read_text())
    assert summary["status"] == "paired_failed"
    assert summary["completed_fem_solve_count"] == 2
    assert summary["execution_records"][0]["counts"]["fem_solve_count"] == 2


def test_run_paired_conservatively_charges_malformed_failed_fem_count(
    benchmark_module: ModuleType,
    fake_inputs: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    study_base, vta_model, _ = fake_inputs
    trash = tmp_path / "Trash"
    root = benchmark_module.prepare_benchmark(
        study_base,
        vta_model,
        tmp_path / "validation",
        now=lambda: datetime(2026, 7, 14, 7, tzinfo=timezone.utc),
        trash_root=trash,
    )
    malformed = {
        "matlab_process_count": 3,
        "fem_solve_count": "invalid",
        "derived_task_count": 0,
        "copy_count": 0,
        "skip_count": 0,
    }
    with pytest.raises(RuntimeError, match="return code 9"):
        benchmark_module.run_paired(
            root,
            benchmark_module.REPRESENTATIVE_CASE_ID,
            command_runner=lambda command: {
                "returncode": 9,
                "stdout": json.dumps(
                    {
                        "generated": 1,
                        "failed": 1,
                        "skipped_dependency": 1,
                        "benchmark_counts": malformed,
                    }
                ),
                "stderr": "malformed failure",
            },
            artifact_comparator=lambda *args: {"pass": True},
            trash_root=trash,
        )
    summary = json.loads(root.joinpath("benchmark_summary.json").read_text())
    assert summary["status"] == "paired_failed"
    assert summary["completed_fem_solve_count"] == 2
    assert summary["execution_records"][0]["fem_count_accounting"].startswith(
        "conservative_expected"
    )


def test_paired_root_claim_is_atomic_and_persistent(
    benchmark_module: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "prepared"
    root.mkdir()
    root.joinpath("benchmark_summary.json").write_text(
        json.dumps({"status": "prepared"}), encoding="utf-8"
    )
    benchmark_module._claim_paired_root(root)
    assert root.joinpath(".paired_gate_claim", "claim.json").is_file()
    with pytest.raises(ValueError, match="already claimed"):
        benchmark_module._claim_paired_root(root)


def test_run_paired_rejects_protected_root_before_claim(
    benchmark_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authoritative = tmp_path / "authoritative"
    root = authoritative / "benchmark"
    root.mkdir(parents=True)
    fixture = benchmark_module.load_fixture(FIXTURE_PATH)
    fixture["protected_roots"] = [str(authoritative)]
    root.joinpath("fixture.json").write_text(
        json.dumps(fixture), encoding="utf-8"
    )
    root.joinpath("benchmark_summary.json").write_text(
        json.dumps({"status": "prepared"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        benchmark_module, "AUTHORITATIVE_LEADDBS_ROOT", authoritative
    )
    with pytest.raises(ValueError, match="authoritative derivatives"):
        benchmark_module.run_paired(
            root, benchmark_module.REPRESENTATIVE_CASE_ID
        )
    assert not root.joinpath(".paired_gate_claim").exists()


def test_representative_fem_bound_rejects_excess(
    benchmark_module: ModuleType,
) -> None:
    benchmark_module._assert_representative_fem_bound(16)
    with pytest.raises(ValueError, match="exceeded"):
        benchmark_module._assert_representative_fem_bound(17)


def test_compare_case_outputs_accepts_equal_arrays_and_rejects_drift(
    benchmark_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nib = pytest.importorskip("nibabel")
    np = pytest.importorskip("numpy")
    reference_root = tmp_path / "compatibility"
    candidate_root = tmp_path / "persistent"
    reference_leaf = reference_root / "leaf"
    candidate_leaf = candidate_root / "leaf"
    values = np.asarray([0, 179, 181, 199, 201, 219, 221, 300], dtype=np.float32)
    values = values.reshape((2, 2, 2))
    affine = np.eye(4)

    def write_leaf(leaf: Path, data: Any) -> None:
        leaf.mkdir(parents=True, exist_ok=True)
        nib.save(nib.Nifti1Image(data, affine), leaf / "efield.nii.gz")
        for threshold in (180.0, 200.0, 220.0):
            mask = (data >= threshold).astype(np.uint8)
            nib.save(
                nib.Nifti1Image(mask, affine),
                leaf / benchmark_module.threshold_filename(threshold),
            )

    write_leaf(reference_leaf, values)
    write_leaf(candidate_leaf, values.copy())
    model = SimpleNamespace(thresholds_v_per_m=(180.0, 200.0, 220.0))
    source = SimpleNamespace(source_id="source-1")
    reference_task = SimpleNamespace(
        kind=benchmark_module.TaskKind.ALTERNATING_SOURCE,
        sources=(source,),
        model=model,
        leaf=reference_leaf,
    )
    candidate_task = SimpleNamespace(
        kind=benchmark_module.TaskKind.ALTERNATING_SOURCE,
        sources=(source,),
        model=model,
        leaf=candidate_leaf,
    )
    monkeypatch.setattr(
        benchmark_module,
        "resolve_case_tasks",
        lambda study, model_path, case: (
            (reference_task,) if reference_root in study.parents else (candidate_task,)
        ),
    )
    monkeypatch.setattr(
        benchmark_module,
        "leaf_directory",
        lambda task, space: task.leaf,
    )

    result = benchmark_module.compare_case_outputs(
        reference_root, candidate_root, {}, ("native",)
    )
    assert result["pass"] is True
    assert result["rows"][0]["exact_values"] is True

    drifted = values.copy()
    drifted.flat[-1] += 0.002
    write_leaf(candidate_leaf, drifted)
    with pytest.raises(ValueError, match="1e-3 V/m"):
        benchmark_module.compare_case_outputs(
            reference_root, candidate_root, {}, ("native",)
        )


def _subject(
    dataset: Path,
    subject_id: str,
    electrode_model: str,
    phases: list[dict[str, Any]],
) -> dict[str, Any]:
    subject_dir = dataset / "derivatives" / "leaddbs" / f"sub-{subject_id}"
    reconstruction = (
        subject_dir
        / "reconstruction"
        / f"sub-{subject_id}_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(subject_id.encode("ascii"))
    for side in (1, 2):
        headmodel = (
            subject_dir
            / "headmodel"
            / "native"
            / f"sub-{subject_id}_desc-headmodel{side}.mat"
        )
        headmodel.parent.mkdir(parents=True, exist_ok=True)
        headmodel.write_bytes(f"headmodel:{side}".encode("ascii"))
    return {
        "subject_id": subject_id,
        "subject_label": subject_id,
        "subject_sources": {
            "leaddbs_subject_dir": str(subject_dir),
            "electrode_reconstruction": {"path": str(reconstruction)},
        },
        "contact_numbering": {
            "convention": "bilateral_contiguous_zero_based",
            "electrode_order": ["lead-L", "lead-R"],
        },
        "electrodes": [
            {
                "electrode_id": "lead-L",
                "hemisphere": "L",
                "electrode_model": electrode_model,
                "contact_count": 4,
                "reconstruction_lead_id": 2,
            },
            {
                "electrode_id": "lead-R",
                "hemisphere": "R",
                "electrode_model": electrode_model,
                "contact_count": 4,
                "reconstruction_lead_id": 1,
            },
        ],
        "phases": phases,
    }


def _phase(phase_id: str, programs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"phase_id": phase_id, "phase_label": phase_id, "programs": programs}


def _program(
    program_id: int,
    electrode_programs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "program_id": program_id,
        "program_label": str(program_id),
        "condition_role": "benchmark",
        "stimulation_state": "active",
        "electrode_programs": electrode_programs,
    }


def _continuous(electrode_id: str) -> dict[str, Any]:
    contact = 4 if electrode_id == "lead-R" else 0
    return {
        "electrode_id": electrode_id,
        "frequency_groups": [
            {
                "frequency_group_id": "group-1",
                "delivery_mode": "continuous",
                "sources": [_source("source-1", contact)],
            }
        ],
    }


def _alternating(electrode_id: str) -> dict[str, Any]:
    offset = 4 if electrode_id == "lead-R" else 0
    return {
        "electrode_id": electrode_id,
        "frequency_groups": [
            {
                "frequency_group_id": "group-1",
                "delivery_mode": "alternating",
                "sources": [
                    _source("source-1", offset),
                    _source("source-2", offset + 1),
                ],
            }
        ],
    }


def _source(source_id: str, contact: int) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_label": source_id,
        "component_id": source_id,
        "frequency_hz": 130,
        "control_mode": "voltage",
        "amplitude": 2.0,
        "pulse_width_us": 60,
        "contacts": [
            {"contact": contact, "polarity": "cathode", "fraction": 1.0},
            {"contact": "case", "polarity": "anode", "fraction": 1.0},
        ],
    }


def _case(fixture: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in fixture["cases"] if case["case_id"] == case_id)
