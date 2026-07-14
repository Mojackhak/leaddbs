from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_helper.vta.test.run_vta_three_worker_memory_gate import (
    DEFAULT_CASE_IDS,
    DEFAULT_FIXTURE,
    EXPECTED_SUBJECT_COUNT,
    SAMPLE_INTERVAL_SECONDS,
    _assert_safe_work_root,
    _cold_subject_ignore,
    _mark_manifest_failed,
    evaluate_gates,
    observe_matlab_processes,
    resolve_gate_cases,
)


def fixture() -> dict[str, object]:
    return json.loads(DEFAULT_FIXTURE.read_text(encoding="utf-8"))


def test_default_cases_are_distinct_and_share_runtime_selector() -> None:
    cases = resolve_gate_cases(fixture(), DEFAULT_CASE_IDS)

    assert len(cases) == EXPECTED_SUBJECT_COUNT
    assert len({case["selector"]["subject_id"] for case in cases}) == 3
    shared = {
        (
            case["selector"]["phase_id"],
            case["selector"]["program_id"],
            case["selector"]["electrode_id"],
            case["selector"]["frequency_group_id"],
        )
        for case in cases
    }
    assert len(shared) == 1


@pytest.mark.parametrize(
    "case_ids",
    (
        DEFAULT_CASE_IDS[:2],
        (DEFAULT_CASE_IDS[0], DEFAULT_CASE_IDS[0], DEFAULT_CASE_IDS[2]),
        (*DEFAULT_CASE_IDS[:2], "missing"),
    ),
)
def test_invalid_case_sets_are_rejected(case_ids: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        resolve_gate_cases(fixture(), case_ids)


def test_mismatched_non_subject_selector_is_rejected() -> None:
    changed = deepcopy(fixture())
    selected = next(
        case
        for case in changed["cases"]
        if case["case_id"] == DEFAULT_CASE_IDS[-1]
    )
    selected["selector"]["program_id"] = 999

    with pytest.raises(ValueError, match="share one non-subject selector"):
        resolve_gate_cases(changed, DEFAULT_CASE_IDS)


def test_script_contains_no_protocol_phase_literal() -> None:
    source = Path(__file__).with_name(
        "run_vta_three_worker_memory_gate.py"
    ).read_text(encoding="utf-8")
    assert '"T2"' not in source
    assert '"T3"' not in source


@pytest.mark.parametrize(
    "unsafe",
    (
        Path("/Volumes/VAL/STNSNr/derivatives"),
        Path("/Volumes/VAL/STNSNr/derivatives/leaddbs"),
        Path("/Volumes/VAL/STNSNr"),
        Path("/tmp"),
    ),
)
def test_work_root_must_be_inside_validation(unsafe: Path) -> None:
    with pytest.raises(ValueError, match="must be inside"):
        _assert_safe_work_root(unsafe, ())


def test_work_root_cannot_overlap_authoritative_input() -> None:
    root = Path("/Volumes/VAL/STNSNr/validation")
    with pytest.raises(ValueError, match="overlaps authoritative input"):
        _assert_safe_work_root(root, (root / "input.json",))


def test_cold_copy_excludes_only_output_and_headmodel_names() -> None:
    ignored = _cold_subject_ignore(
        "/unused",
        ["headmodel", "stimulations", "reconstruction", "atlases"],
    )
    assert ignored == {"headmodel", "stimulations"}


class FakeProcess:
    def __init__(
        self,
        pid: int,
        *,
        running: bool = True,
        name: str = "MATLAB_maca64",
        children: tuple["FakeProcess", ...] = (),
    ) -> None:
        self.pid = pid
        self._running = running
        self._name = name
        self._children = children

    def is_running(self) -> bool:
        return self._running

    def status(self) -> str:
        return "running" if self._running else "stopped"

    def name(self) -> str:
        return self._name

    def children(self, *, recursive: bool) -> list["FakeProcess"]:
        assert recursive
        return list(self._children)


def test_sampled_overlap_counts_only_live_matlab_roots() -> None:
    nested = FakeProcess(20)
    expected_helper = FakeProcess(21, name="matlab_helper")
    processes = {
        1: FakeProcess(1, children=(nested, expected_helper)),
        2: FakeProcess(2),
        3: FakeProcess(3, running=False),
    }

    live_roots, nested_roots = observe_matlab_processes(
        {"A": 1, "B": 2, "C": 3},
        process_provider=processes.__getitem__,
    )

    assert live_roots == 2
    assert nested_roots == 1


def test_gate_evaluator_enforces_memory_overlap_and_interval() -> None:
    run_summary = SimpleNamespace(
        failed=0,
        skipped_dependency=0,
        subject_process_failed=0,
    )
    memory = SimpleNamespace(
        physical_memory_bytes=1000,
        aggregate_peak_rss_bytes=750,
        subject_peak_rss_bytes={"A": 500, "B": 499, "C": 498},
        sample_count=1,
    )
    gates = evaluate_gates(
        observation_count=3,
        outcome_statuses=("generated",) * 7,
        fem_solve_count=5,
        run_summary=run_summary,
        memory=memory,
        sampled_live_roots=3,
        nested_matlab_descendants=0,
        sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
        artifacts_complete=True,
        no_failure_text=True,
    )
    assert all(gates.values())

    memory.aggregate_peak_rss_bytes = 751
    failed = evaluate_gates(
        observation_count=3,
        outcome_statuses=("generated",) * 7,
        fem_solve_count=5,
        run_summary=run_summary,
        memory=memory,
        sampled_live_roots=2,
        nested_matlab_descendants=0,
        sample_interval_seconds=0.2,
        artifacts_complete=True,
        no_failure_text=True,
    )
    assert not failed["aggregate_rss_within_limit"]
    assert not failed["three_live_roots_sampled"]
    assert not failed["sample_interval_is_100_ms"]


def test_failed_manifest_records_phase_and_error(tmp_path: Path) -> None:
    manifest = tmp_path / "gate_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": "v1", "status": "preparing"}),
        encoding="utf-8",
    )

    _mark_manifest_failed(tmp_path, RuntimeError("copy failed"), "preparation")

    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["status"] == "failed"
    assert recorded["failure_phase"] == "preparation"
    assert recorded["error_type"] == "RuntimeError"
