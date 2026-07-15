"""Run-store and executor tests using deterministic in-memory services only."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from dual_frequency.contracts import ArtifactRef, AxisRef, EndpointKey, TaskKey
from dual_frequency.workflow import ExecutionPlan, GateRequirement, TaskSpec
from dual_frequency.workflow.executor import (
    ExecutionContext,
    ServiceResult,
    execute_plan,
    plan_hash,
)
from dual_frequency.workflow.registry import RegisteredService, ServiceRegistry
from dual_frequency.workflow.run_store import RunIdentity, RunStore, RunStoreError


CONFIGURATION_HASH = "a" * 64
SCIENTIFIC_HASH = "b" * 64


def _task(
    endpoint: EndpointKey,
    stage: str,
    service_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    gates: tuple[GateRequirement, ...] = (),
    output_record_type: str = "EndpointInputRecord",
    expensive: bool = False,
) -> TaskSpec:
    key = TaskKey(endpoint.identifier, stage, parameter_identity=SCIENTIFIC_HASH)
    return TaskSpec(
        key=key,
        endpoint_id=endpoint.identifier,
        model_family=endpoint.model_family,
        connectome_role="none",
        stage=stage,
        round_id="test",
        phase="observed",
        service_id=service_id,
        dependencies=dependencies,
        gates=gates,
        output_record_type=output_record_type,
        expensive_producer=expensive,
    )


def _result(request) -> ServiceResult:
    return ServiceResult.create(
        request.task.output_record_type,
        f"record:{request.task.task_id}",
        {"stage": request.task.stage},
    )


class ExecutorTest(unittest.TestCase):
    def _store(self, root: Path, plan: ExecutionPlan, *, resume: bool = False) -> RunStore:
        identity = RunIdentity(
            study_id="synthetic",
            run_id="run-001",
            study_base_sha256="e" * 64,
            code_identity="synthetic-code-v1",
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            plan_hash=plan_hash(plan),
        )
        return RunStore.open(
            root,
            identity,
            resolved_configuration={"profile": "synthetic"},
            configuration_sources=(),
            resume=resume,
        )

    @staticmethod
    def _plan(tasks: tuple[TaskSpec, ...]) -> ExecutionPlan:
        return ExecutionPlan(
            configuration_hash=CONFIGURATION_HASH,
            scientific_configuration_hash=SCIENTIFIC_HASH,
            through="observed",
            tasks=tasks,
        )

    def test_failure_is_local_and_independent_endpoint_completes(self) -> None:
        endpoint_a = EndpointKey("study", "scale-a", "reference", "reference_voxel")
        endpoint_b = EndpointKey("study", "scale-b", "reference", "reference_voxel")
        a_first = _task(endpoint_a, "first", "fail")
        a_second = _task(endpoint_a, "second", "ok", dependencies=(a_first.task_id,))
        b_first = _task(endpoint_b, "first", "ok")
        plan = self._plan((a_first, b_first, a_second))

        def fail(_request):
            raise RuntimeError("synthetic failure")

        registry = ServiceRegistry(
            (
                RegisteredService("fail", fail),
                RegisteredService("ok", _result),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=2,
                ),
            )
        by_id = {outcome.task_id: outcome for outcome in result.outcomes}
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(by_id[a_first.task_id].status, "failed")
        self.assertEqual(by_id[a_second.task_id].status, "skipped")
        self.assertTrue(by_id[a_second.task_id].reason.startswith("dependency_failure"))
        self.assertEqual(by_id[b_first.task_id].status, "completed")

    def test_false_gate_skips_without_invoking_service(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "gated",
            "sentinel",
            gates=(GateRequirement("ready", "not_run_not_ready"),),
        )
        plan = self._plan((task,))
        calls: list[str] = []

        def sentinel(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry((RegisteredService("sentinel", sentinel),)),
                    endpoint_facts={endpoint.identifier: {"ready": False}},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(calls, [])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.outcomes[0].status, "skipped")
        self.assertEqual(result.outcomes[0].reason, "not_run_not_ready")

    def test_expensive_task_is_rejected_before_service_invocation(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal-connectome",
        )
        task = _task(endpoint, "activation", "expensive", expensive=True)
        plan = self._plan((task,))
        calls: list[str] = []

        def expensive(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry((RegisteredService("expensive", expensive),)),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(calls, [])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ExpensiveProducerNotAuthorized", result.outcomes[0].reason)

    def test_declared_artifact_output_cannot_complete_without_artifact(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "prepare",
            "bad_artifact",
            output_record_type="ArtifactRef",
        )
        plan = self._plan((task,))
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry((RegisteredService("bad_artifact", _result),)),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("requires at least one declared artifact", result.outcomes[0].reason)

    def test_completed_artifact_is_hash_checked_and_indexed(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(endpoint, "prepare", "write_artifact", output_record_type="ArtifactRef")
        plan = self._plan((task,))

        def write_artifact(request):
            path = request.output_dir / "exposure.npy"
            np.save(path, np.arange(3, dtype=np.float64))
            axis = AxisRef("features", 3, "d" * 64)
            artifact = ArtifactRef(
                kind="exposure",
                schema_version="array_v1",
                uri=path.resolve().as_uri(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                dtype="float64",
                shape=(3,),
                axis_refs=(axis,),
                axis_hashes=(axis.sha256,),
                units="V/m",
                space="synthetic",
                producer_id="executor_test",
                producer_version="1",
            )
            return ServiceResult.create(
                request.task.output_record_type,
                "artifact-record",
                {"artifact_id": artifact.identifier},
                artifacts=(artifact,),
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry(
                        (RegisteredService("write_artifact", write_artifact),)
                    ),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            artifact_index = json.loads(
                (store.root / "artifact_index.json").read_text(encoding="utf-8")
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(artifact_index["artifacts"]), 1)

    def test_exact_resume_restores_completed_result_without_reinvocation(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(endpoint, "single", "count")
        plan = self._plan((task,))
        calls: list[str] = []

        def count(request):
            calls.append(request.task.task_id)
            return _result(request)

        registry = ServiceRegistry((RegisteredService("count", count),))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            first_store = self._store(root, plan)
            first = execute_plan(
                plan,
                ExecutionContext(
                    run_store=first_store,
                    registry=registry,
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            resumed_store = self._store(root, plan, resume=True)
            resumed = execute_plan(
                plan,
                ExecutionContext(
                    run_store=resumed_store,
                    registry=registry,
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                    resume=True,
                ),
            )
            mismatch = RunIdentity(
                study_id="synthetic",
                run_id="run-001",
                study_base_sha256="e" * 64,
                code_identity="synthetic-code-v1",
                configuration_hash="c" * 64,
                scientific_configuration_hash=SCIENTIFIC_HASH,
                plan_hash=plan_hash(plan),
            )
            with self.assertRaisesRegex(RunStoreError, "configuration_hash"):
                RunStore.open(
                    root,
                    mismatch,
                    resolved_configuration={"profile": "synthetic"},
                    configuration_sources=(),
                    resume=True,
                )
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(resumed.exit_code, 0)
        self.assertEqual(calls, [task.task_id])


if __name__ == "__main__":
    unittest.main()
