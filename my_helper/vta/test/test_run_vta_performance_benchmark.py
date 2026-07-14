"""Solver-free tests for the frozen VTA performance benchmark harness."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from my_helper.fiber.core.vta_pipeline.artifacts import expected_artifacts
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory


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
    ("failed", "skipped_dependency", "expected_exit"),
    ((0, 0, 0), (1, 0, 1), (0, 1, 1)),
)
def test_case_runner_exit_reflects_failure_and_dependency_skip(
    benchmark_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failed: int,
    skipped_dependency: int,
    expected_exit: int,
) -> None:
    monkeypatch.setattr(
        benchmark_module,
        "_execute_case",
        lambda *args, **kwargs: {
            "failed": failed,
            "skipped_dependency": skipped_dependency,
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
