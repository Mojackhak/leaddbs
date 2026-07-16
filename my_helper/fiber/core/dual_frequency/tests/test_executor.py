"""Run-store and executor tests using deterministic in-memory services only."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointInputRecord,
    EndpointKey,
    SourceRecord,
    SubjectExclusionRecord,
    TaskKey,
)
from dual_frequency.contracts.records import FinalSelectionRecord
from dual_frequency.workflow import ExecutionPlan, GateRequirement, TaskSpec
from dual_frequency.workflow.executor import (
    ExecutionContext,
    ExecutionError,
    ServiceResult,
    execute_plan,
    plan_hash,
)
from dual_frequency.workflow.registry import RegisteredService, ServiceRegistry
from dual_frequency.workflow.run_store import RunIdentity, RunStore, RunStoreError


CONFIGURATION_HASH = "a" * 64
SCIENTIFIC_HASH = "b" * 64


class _Provider:
    def __init__(self, *endpoints: EndpointKey) -> None:
        self.endpoints = {endpoint.identifier: endpoint for endpoint in endpoints}


def _source(endpoint: EndpointKey) -> SourceRecord:
    return SourceRecord(
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


def _task(
    endpoint: EndpointKey,
    stage: str,
    service_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    gates: tuple[GateRequirement, ...] = (),
    output_record_type: str = "SourceRecord",
    expensive: bool = False,
    cache_first_expensive: bool = False,
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
        cache_first_expensive=cache_first_expensive,
    )


def _result(request) -> ServiceResult:
    endpoint = request.provider.endpoints[request.task.endpoint_id]
    return ServiceResult.from_record(_source(endpoint))


def _artifact_result(request, filename: str = "exposure.npy") -> ArtifactRef:
    path = request.output_dir / filename
    np.save(path, np.arange(3, dtype=np.float64))
    axis = AxisRef("features", 3, "d" * 64)
    return ArtifactRef(
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
                    provider=_Provider(endpoint_a, endpoint_b),
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

    def test_fault_free_execution_records_one_closed_pool_generation(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        first = _task(endpoint, "first", "ok")
        second = _task(endpoint, "second", "ok", dependencies=(first.task_id,))
        plan = self._plan((first, second))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            store = self._store(root, plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry((RegisteredService("ok", _result),)),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=2,
                ),
            )
            segments = tuple((root / "execution_segments").glob("segment_*.json"))
            document = json.loads(segments[0].read_text(encoding="utf-8"))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(segments), 1)
        self.assertEqual(document["status"], "finished")
        self.assertEqual(document["pool_generation_count"], 1)
        self.assertEqual(document["workers"], 2)
        self.assertGreaterEqual(document["swap_delta_bytes"], 0)

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
                    provider=_Provider(endpoint),
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

    def test_endpoint_input_failure_skips_preparation_and_observed_work(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        readiness = _task(
            endpoint,
            "input_readiness",
            "readiness",
            output_record_type="EndpointInputRecord",
        )
        input_gate = GateRequirement(
            "endpoint_input_ready",
            "not_run_endpoint_input_not_ready",
        )
        prepare = _task(
            endpoint,
            "prepare_exposure",
            "must_not_run",
            dependencies=(readiness.task_id,),
            gates=(input_gate,),
        )
        observed = _task(
            endpoint,
            "observed_grid",
            "must_not_run",
            dependencies=(readiness.task_id, prepare.task_id),
            gates=(input_gate,),
        )
        plan = self._plan((readiness, prepare, observed))
        calls: list[str] = []

        def readiness_service(_request):
            record = EndpointInputRecord(
                endpoint=endpoint,
                readiness_status="input_failure",
                candidate_subject_ids=("subject_1", "subject_2"),
                included_subject_ids=(),
                exclusions=(
                    SubjectExclusionRecord("subject_1", "missing_primary_exposure"),
                    SubjectExclusionRecord("subject_2", "missing_primary_exposure"),
                ),
                minimum_subjects=2,
                subject_axis=None,
                baseline=None,
                outcome=None,
            )
            return ServiceResult.from_record(
                record,
                facts={"endpoint_input_ready": False},
            )

        def must_not_run(request):
            calls.append(request.task.task_id)
            return _result(request)

        registry = ServiceRegistry(
            (
                RegisteredService("readiness", readiness_service),
                RegisteredService("must_not_run", must_not_run),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.outcomes[0].status, "completed")
        self.assertEqual(
            [outcome.reason for outcome in result.outcomes[1:]],
            ["not_run_endpoint_input_not_ready"] * 2,
        )
        self.assertEqual(calls, [])

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
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(calls, [])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("ExpensiveProducerNotAuthorized", result.outcomes[0].reason)

    def test_cache_first_expensive_task_can_probe_cache_without_authorization(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal-connectome",
        )
        task = _task(
            endpoint,
            "activation",
            "cache_first",
            expensive=True,
            cache_first_expensive=True,
        )
        plan = self._plan((task,))
        calls: list[tuple[bool, int]] = []

        def cache_first(request):
            calls.append((request.allow_expensive_producers, request.workers))
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry(
                        (RegisteredService("cache_first", cache_first),)
                    ),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=3,
                    scientific_cache=object(),
                ),
            )
        self.assertEqual(calls, [(False, 1)])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.outcomes[0].status, "completed")

    def test_cache_first_requires_expensive_producer_flag(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal-connectome",
        )
        with self.assertRaisesRegex(ValueError, "requires expensive_producer"):
            _task(
                endpoint,
                "activation",
                "invalid",
                cache_first_expensive=True,
            )

    def test_provider_and_decoded_dependency_record_reach_service(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        first = _task(endpoint, "first", "first")
        second = _task(endpoint, "second", "second", dependencies=(first.task_id,))
        plan = self._plan((first, second))
        provider = _Provider(endpoint)
        seen: list[tuple[object, object | None]] = []

        def first_service(request):
            seen.append((request.provider, None))
            return _result(request)

        def second_service(request):
            dependency = request.dependencies[first.task_id]
            seen.append((request.provider, dependency.record))
            return _result(request)

        registry = ServiceRegistry(
            (
                RegisteredService("first", first_service),
                RegisteredService("second", second_service),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    provider=provider,
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(result.exit_code, 0)
        self.assertIs(seen[0][0], provider)
        self.assertIs(seen[1][0], provider)
        self.assertIsInstance(seen[1][1], SourceRecord)
        self.assertEqual(seen[1][1].endpoint, endpoint)

    def test_no_final_selection_completes_and_skips_final_linked_work(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        selection_task = _task(
            endpoint,
            "final_realization",
            "select",
            output_record_type="FinalSelectionRecord",
        )
        downstream = _task(
            endpoint,
            "formal_permutation",
            "must_not_run",
            dependencies=(selection_task.task_id,),
            gates=(GateRequirement("final_model_realized", "not_run_no_final_model"),),
        )
        plan = self._plan((selection_task, downstream))
        calls: list[str] = []

        def select(request):
            record = FinalSelectionRecord(
                endpoint=endpoint,
                selection_status="no_final_model",
                final_model=None,
                reason_codes=("no_accepted_source",),
                causal_task_ids=(request.task.task_id,),
            )
            return ServiceResult.from_record(
                record,
                facts={"final_model_realized": False},
            )

        def must_not_run(request):
            calls.append(request.task.task_id)
            return _result(request)

        registry = ServiceRegistry(
            (
                RegisteredService("select", select),
                RegisteredService("must_not_run", must_not_run),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.outcomes[0].status, "completed")
        self.assertEqual(
            result.outcomes[0].result.decode_record().selection_status,
            "no_final_model",
        )
        self.assertEqual(result.outcomes[1].status, "skipped")
        self.assertEqual(result.outcomes[1].reason, "not_run_no_final_model")
        self.assertEqual(calls, [])

    def test_initial_execution_rejects_record_metadata_and_endpoint_mismatches(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        other = EndpointKey("study", "other", "reference", "reference_voxel")

        def wrong_record_id(request):
            return replace(_result(request), record_id="source_wrong")

        def wrong_envelope_type(request):
            return replace(_result(request), output_record_type="ArtifactRef")

        def wrong_endpoint(_request):
            return ServiceResult.from_record(_source(other))

        cases = (
            ("wrong_record_id", wrong_record_id, "record"),
            ("wrong_envelope_type", wrong_envelope_type, "record"),
            ("wrong_endpoint", wrong_endpoint, "expected"),
        )
        for service_id, service, expected_reason in cases:
            with self.subTest(service_id=service_id):
                task = _task(endpoint, service_id, service_id)
                plan = self._plan((task,))
                with tempfile.TemporaryDirectory() as temporary_directory:
                    store = self._store(Path(temporary_directory) / "run", plan)
                    result = execute_plan(
                        plan,
                        ExecutionContext(
                            run_store=store,
                            registry=ServiceRegistry(
                                (RegisteredService(service_id, service),)
                            ),
                            provider=_Provider(endpoint, other),
                            endpoint_facts={},
                            allow_expensive_producers=False,
                            continue_on_endpoint_failure=True,
                            workers=1,
                        ),
                    )
                self.assertEqual(result.outcomes[0].status, "failed")
                self.assertIn(expected_reason, result.outcomes[0].reason)

    def test_codec_artifact_closure_cannot_be_omitted(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "prepare",
            "bad_artifact",
            output_record_type="ArtifactRef",
        )
        plan = self._plan((task,))

        def bad_artifact(request):
            result = ServiceResult.from_record(_artifact_result(request))
            return replace(result, artifacts=())

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry(
                        (RegisteredService("bad_artifact", bad_artifact),)
                    ),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
        self.assertEqual(result.exit_code, 1)
        self.assertIn("artifact closure", result.outcomes[0].reason)

    def test_completed_artifact_is_hash_checked_and_indexed(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(endpoint, "prepare", "write_artifact", output_record_type="ArtifactRef")
        plan = self._plan((task,))

        def write_artifact(request):
            return ServiceResult.from_record(_artifact_result(request))

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry(
                        (RegisteredService("write_artifact", write_artifact),)
                    ),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            artifact_index = json.loads(
                (store.root / "artifact_index.json").read_text(encoding="utf-8")
            )
            final_status = store.read_manifest()["final_status"]
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(artifact_index["artifacts"]), 1)
        self.assertEqual(final_status, "running")

    def test_resume_rejects_tampered_completed_record(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(endpoint, "single", "ok")
        plan = self._plan((task,))
        registry = ServiceRegistry((RegisteredService("ok", _result),))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            store = self._store(root, plan)
            first = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            payload = store.read_task_state(task.task_id)
            assert payload is not None and payload["result"] is not None
            payload["result"]["record_id"] = "source_tampered"
            store.write_task_state(task.task_id, payload)
            resumed_store = self._store(root, plan, resume=True)
            with self.assertRaisesRegex(ExecutionError, "record codec"):
                execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=resumed_store,
                        registry=registry,
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=1,
                        resume=True,
                    ),
                )
        self.assertEqual(first.exit_code, 0)

    def test_resume_rejects_tampered_artifact_closure(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "prepare",
            "write_artifact",
            output_record_type="ArtifactRef",
        )
        plan = self._plan((task,))

        def write_artifact(request):
            return ServiceResult.from_record(_artifact_result(request))

        registry = ServiceRegistry(
            (RegisteredService("write_artifact", write_artifact),)
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            store = self._store(root, plan)
            first = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=registry,
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            payload = store.read_task_state(task.task_id)
            assert payload is not None and payload["result"] is not None
            payload["result"]["artifacts"] = []
            store.write_task_state(task.task_id, payload)
            resumed_store = self._store(root, plan, resume=True)
            with self.assertRaisesRegex(ExecutionError, "artifact closure"):
                execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=resumed_store,
                        registry=registry,
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=1,
                        resume=True,
                    ),
                )
        self.assertEqual(first.exit_code, 0)

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
                    provider=_Provider(endpoint),
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
                    provider=_Provider(endpoint),
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
