"""Post-publication cleanup tests for run-owned scratch only."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from dual_frequency.application.run_cache_cleanup import (
    CLEANUP_MARKER,
    RunCacheCleanupError,
    cleanup_run_cache_after_publication,
)
from dual_frequency.contracts import (
    AxisRef,
    EndpointKey,
    FormalOperatorScratchRecord,
    ScratchArrayRecord,
    SourceRecord,
)
from dual_frequency.workflow.executor import ServiceResult, TaskOutcome


def _resolved(enabled: bool) -> dict[str, object]:
    return {
        "study": {"selected_scales": ["scale-a"]},
        "storage": {"delete_run_cache_on_success": enabled},
    }


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _complete_run(root: Path, run_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "final_status": "completed"}),
        encoding="utf-8",
    )
    (root / "artifact_index.json").write_text(
        json.dumps({"artifacts": []}),
        encoding="utf-8",
    )


def _complete_publication(root: Path, run_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "model_manifest.json").write_text(
        json.dumps(
            {
                "final_status": "completed",
                "source_run_id": run_id,
                "scale_count": 1,
            }
        ),
        encoding="utf-8",
    )
    _write_csv(root / "artifact_index.csv", ({"status": "completed"},))
    _write_csv(
        root / "scale_status.csv",
        ({"scale_id": "scale-a", "overall_status": "completed"},),
    )


def _source_outcome() -> TaskOutcome:
    endpoint = EndpointKey("study", "scale-a", "reference", "reference_voxel")
    record = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="absent_no_stable_grid",
        prediction_status="not_applicable",
        threshold_source="none",
        selected_tau=None,
        selected_coverage=None,
        adjacent_support=0,
        feature_axis=None,
        artifacts=(),
    )
    return TaskOutcome(
        task_id="task_source",
        endpoint_id=endpoint.identifier,
        service_id="source",
        status="completed",
        reason="none",
        result=ServiceResult.from_record(record),
    )


def _formal_scratch_outcome(
    run_root: Path,
    *,
    unexpected: bool = False,
) -> tuple[TaskOutcome, Path]:
    generation = (
        run_root
        / "work"
        / "task_formal_operator_workspace"
        / "attempt-0000000000000001"
        / "operator-generation-test"
    )
    generation.mkdir(parents=True)
    value = np.arange(4, dtype=np.float64).reshape(2, 2)
    path = generation / "00_score_operator.npy"
    np.save(path, value)
    if unexpected:
        (generation / "unexpected.txt").write_text("retain\n", encoding="utf-8")
    array = ScratchArrayRecord(
        name="score_operator",
        filename=path.name,
        dtype=value.dtype.name,
        shape=value.shape,
        fortran_order=False,
        nbytes=value.nbytes,
    )
    record = FormalOperatorScratchRecord(
        target_id="formal-target",
        model_family="direct_voxel",
        subject_axis=AxisRef("subjects", 2, "1" * 64),
        feature_axis=AxisRef("features", 3, "2" * 64),
        input_identity="3" * 64,
        operator_schema="dual_frequency_formal_operator_scratch_v1",
        technical_status="completed",
        generation_path=generation.relative_to(run_root).as_posix(),
        arrays=(array,),
        total_nbytes=array.nbytes,
    )
    outcome = TaskOutcome(
        task_id="task_formal_operator_workspace",
        endpoint_id="endpoint-formal",
        service_id="prepare_formal_operator_workspace",
        status="completed",
        reason="none",
        result=ServiceResult.from_record(record),
    )
    return outcome, generation


class RunCacheCleanupTest(unittest.TestCase):
    def test_false_policy_returns_before_inspection_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runtime = root / "runtime_work"
            runtime.mkdir()
            retained = runtime / "retained.bin"
            retained.write_bytes(b"retained")
            result = cleanup_run_cache_after_publication(
                run_root=root,
                resolved_configuration=_resolved(False),
                outcomes=(),
                direct_voxel_publication=root / "missing-direct",
                normative_fiber_publication=root / "missing-fiber",
            )
            self.assertFalse(result.enabled)
            self.assertTrue(retained.is_file())
            self.assertFalse((root / CLEANUP_MARKER).exists())

    def test_incomplete_run_fails_before_touching_runtime_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runtime = root / "runtime_work"
            runtime.mkdir()
            retained = runtime / "retained.bin"
            retained.write_bytes(b"retained")
            (root / "run_manifest.json").write_text(
                json.dumps({"run_id": "run-a", "final_status": "failed"}),
                encoding="utf-8",
            )
            with self.assertRaises(RunCacheCleanupError):
                cleanup_run_cache_after_publication(
                    run_root=root,
                    resolved_configuration=_resolved(True),
                    outcomes=(_source_outcome(),),
                    direct_voxel_publication=root / "missing-direct",
                    normative_fiber_publication=root / "missing-fiber",
                )
            self.assertTrue(retained.is_file())
            self.assertFalse((root / CLEANUP_MARKER).exists())

    def test_complete_publication_cleans_only_run_owned_scratch_and_reuses_marker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "run"
            direct = base / "published-direct"
            fiber = base / "published-fiber"
            _complete_run(root, "run-a")
            _complete_publication(direct, "run-a")
            _complete_publication(fiber, "run-a")
            runtime = root / "runtime_work"
            runtime.mkdir()
            (runtime / "prepared.bin").write_bytes(b"temporary")
            task_artifact = root / "work" / "task-artifact.npy"
            task_artifact.parent.mkdir(parents=True)
            np.save(task_artifact, np.arange(3))
            shared_cache = base / "shared-cache" / "entry.bin"
            shared_cache.parent.mkdir()
            shared_cache.write_bytes(b"shared")
            scratch_outcome, generation = _formal_scratch_outcome(root)

            first = cleanup_run_cache_after_publication(
                run_root=root,
                resolved_configuration=_resolved(True),
                outcomes=(_source_outcome(), scratch_outcome),
                direct_voxel_publication=direct,
                normative_fiber_publication=fiber,
            )
            second = cleanup_run_cache_after_publication(
                run_root=root,
                resolved_configuration=_resolved(True),
                outcomes=(_source_outcome(), scratch_outcome),
                direct_voxel_publication=direct,
                normative_fiber_publication=fiber,
            )

            self.assertTrue(first.cleaned)
            self.assertFalse(generation.exists())
            self.assertFalse(runtime.exists())
            self.assertTrue(task_artifact.is_file())
            self.assertTrue(shared_cache.is_file())
            self.assertTrue((root / CLEANUP_MARKER).is_file())
            self.assertTrue(second.reused)
            self.assertFalse(second.cleaned)

    def test_untracked_scratch_fails_preflight_before_any_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "run"
            direct = base / "published-direct"
            fiber = base / "published-fiber"
            _complete_run(root, "run-a")
            _complete_publication(direct, "run-a")
            _complete_publication(fiber, "run-a")
            runtime = root / "runtime_work"
            runtime.mkdir()
            retained = runtime / "retained.bin"
            retained.write_bytes(b"retained")
            scratch_outcome, generation = _formal_scratch_outcome(
                root,
                unexpected=True,
            )

            with self.assertRaises(RunCacheCleanupError):
                cleanup_run_cache_after_publication(
                    run_root=root,
                    resolved_configuration=_resolved(True),
                    outcomes=(_source_outcome(), scratch_outcome),
                    direct_voxel_publication=direct,
                    normative_fiber_publication=fiber,
                )
            self.assertTrue(generation.is_dir())
            self.assertTrue(retained.is_file())
            self.assertFalse((root / CLEANUP_MARKER).exists())


if __name__ == "__main__":
    unittest.main()
