"""Run-store and executor tests using deterministic in-memory services only."""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    EndpointInputRecord,
    EndpointKey,
    FormalOperatorScratchRecord,
    ScratchArrayRecord,
    SourceRecord,
    SubjectExclusionRecord,
    TaskKey,
)
from dual_frequency.contracts.records import FinalSelectionRecord
from dual_frequency.workflow import ExecutionPlan, GateRequirement, TaskSpec
from dual_frequency.workflow.executor import (
    ExecutionContext,
    ExecutionError,
    _ResourceLedger,
    ServiceResult,
    TaskOutcome,
    execute_plan,
    plan_hash,
)
from dual_frequency.workflow.registry import RegisteredService, ServiceRegistry
from dual_frequency.workflow.run_store import (
    ConfigurationSource,
    RunIdentity,
    RunStore,
    RunStoreError,
)
from dual_frequency.runtime.formal_operator_workspace import (
    cleanup_formal_operator_scratch_record,
)


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
    checkpoint_only: bool = False,
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
        checkpoint_only=checkpoint_only,
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
    def test_prepare_exposure_grant_covers_bilateral_sampler_working_set(self) -> None:
        fiber_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        fiber_task = _task(
            fiber_endpoint,
            "prepare_exposure",
            "prepare_reference_fiber_sidecar",
        )
        fiber_grant = _ResourceLedger.request(fiber_task)
        self.assertEqual(fiber_grant.memory_bytes, 32 * 1024**3)
        self.assertEqual(fiber_grant.connectome_io, 1)

        voxel_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_voxel",
            "none",
        )
        voxel_task = _task(
            voxel_endpoint,
            "prepare_exposure",
            "prepare_reference_voxel_sidecar",
        )
        voxel_grant = _ResourceLedger.request(voxel_task)
        self.assertEqual(voxel_grant.memory_bytes, 16 * 1024**3)
        self.assertEqual(voxel_grant.connectome_io, 1)

    def test_ppam_resource_grants_isolate_solver_from_blocks_and_aggregate(
        self,
    ) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        observed = _ResourceLedger.request(
            _task(
                endpoint,
                "ppam_observed_workspace",
                "prepare_ppam_observed_workspace",
            )
        )
        schedule = _ResourceLedger.request(
            _task(
                endpoint,
                "ppam_permutation_schedule",
                "prepare_ppam_permutation_schedule",
            )
        )
        block = _ResourceLedger.request(
            _task(
                endpoint,
                "ppam_permutation_block_0000",
                "run_ppam_permutation_block",
            )
        )
        aggregate = _ResourceLedger.request(
            _task(
                endpoint,
                "activation_sensitivity",
                "aggregate_ppam_activation",
            )
        )
        self.assertEqual(
            (observed.memory_bytes, observed.connectome_io, observed.solver),
            (48 * 1024**3, 1, 1),
        )
        for grant in (schedule, block, aggregate):
            self.assertEqual(
                (grant.memory_bytes, grant.connectome_io, grant.solver),
                (2 * 1024**3, 0, 0),
            )

    def test_jitter_block_grants_charge_model_specific_working_sets(self) -> None:
        cases = (
            ("reference_voxel", "none", 12 * 1024**3, 0),
            ("addon_voxel", "none", 12 * 1024**3, 0),
            ("reference_fiber", "formal_connectome", 12 * 1024**3, 1),
        )
        for model_family, connectome_id, memory_bytes, connectome_io in cases:
            with self.subTest(model_family=model_family):
                endpoint = EndpointKey(
                    "study",
                    "scale",
                    "reference" if model_family.startswith("reference") else "addon",
                    model_family,
                    connectome_id,
                )
                task = _task(endpoint, "jitter_block_0000_0025", "jitter_block")
                grant = _ResourceLedger.request(task)
                self.assertEqual(grant.memory_bytes, memory_bytes)
                self.assertEqual(grant.connectome_io, connectome_io)

    def test_oss_axis_gate_owns_the_single_solver_token(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        gate = _task(
            endpoint,
            "oss_axis_equivalence_synthetic",
            "establish_oss_axis_equivalence",
        )
        grant = _ResourceLedger.request(gate)
        self.assertEqual(
            (grant.memory_bytes, grant.connectome_io, grant.solver),
            (48 * 1024**3, 1, 1),
        )

    def test_solver_grant_cannot_bypass_the_managed_memory_ceiling(self) -> None:
        ledger = _ResourceLedger(workers=12)
        ledger.available_memory = 128 * 1024**3
        ledger.reserve = 16 * 1024**3
        ledger.managed = 16 * 1024**3
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        grant = ledger.request(
            _task(
                endpoint,
                "oss_axis_equivalence_synthetic",
                "establish_oss_axis_equivalence",
            )
        )
        self.assertFalse(ledger.can_acquire(grant, 0))

    def test_jitter_block_admission_enforces_cumulative_managed_memory(self) -> None:
        ledger = _ResourceLedger(workers=12)
        ledger.available_memory = 128 * 1024**3
        ledger.reserve = 16 * 1024**3
        ledger.managed = 64 * 1024**3
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_voxel",
        )
        grant = ledger.request(
            _task(endpoint, "jitter_block_0000_0025", "jitter_block")
        )
        for running_count in range(5):
            self.assertTrue(ledger.can_acquire(grant, running_count))
            ledger.acquire(grant)
        self.assertFalse(ledger.can_acquire(grant, 5))

    def test_addon_and_fiber_jitter_admission_use_stricter_limits(self) -> None:
        addon_ledger = _ResourceLedger(workers=12)
        addon_ledger.available_memory = 128 * 1024**3
        addon_ledger.reserve = 16 * 1024**3
        addon_ledger.managed = 64 * 1024**3
        addon_endpoint = EndpointKey(
            "study",
            "scale",
            "addon",
            "addon_voxel",
        )
        addon_grant = addon_ledger.request(
            _task(addon_endpoint, "jitter_block_0000_0025", "jitter_block")
        )
        for running_count in range(5):
            self.assertTrue(addon_ledger.can_acquire(addon_grant, running_count))
            addon_ledger.acquire(addon_grant)
        self.assertFalse(addon_ledger.can_acquire(addon_grant, 5))

        fiber_ledger = _ResourceLedger(workers=12)
        fiber_ledger.available_memory = 128 * 1024**3
        fiber_ledger.reserve = 16 * 1024**3
        fiber_ledger.managed = 64 * 1024**3
        fiber_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        fiber_grant = fiber_ledger.request(
            _task(fiber_endpoint, "jitter_block_0000_0025", "jitter_block")
        )
        for running_count in range(2):
            self.assertTrue(fiber_ledger.can_acquire(fiber_grant, running_count))
            fiber_ledger.acquire(fiber_grant)
        self.assertFalse(fiber_ledger.can_acquire(fiber_grant, 2))

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

    def test_checkpoint_only_root_cannot_invoke_its_service(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        root = _task(
            endpoint,
            "checkpoint_root",
            "sentinel",
            checkpoint_only=True,
        )
        plan = self._plan((root,))
        calls: list[str] = []

        def sentinel(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            with self.assertRaisesRegex(
                ExecutionError,
                "checkpoint roots are missing completed outcomes",
            ):
                execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=store,
                        registry=ServiceRegistry(
                            (RegisteredService("sentinel", sentinel),)
                        ),
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=1,
                        resume=True,
                    ),
                )
        self.assertEqual(calls, [])

    def test_checkpoint_only_root_restores_without_invocation(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        root = _task(
            endpoint,
            "checkpoint_root",
            "sentinel",
            checkpoint_only=True,
        )
        plan = self._plan((root,))
        calls: list[str] = []

        def sentinel(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            seed = TaskOutcome(
                task_id=root.task_id,
                endpoint_id=root.endpoint_id,
                service_id=root.service_id,
                status="completed",
                reason="none",
                result=ServiceResult.from_record(_source(endpoint)),
            )
            store.write_task_state(root.task_id, seed.as_dict())
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry(
                        (RegisteredService("sentinel", sentinel),)
                    ),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                    resume=True,
                ),
            )
        self.assertEqual(calls, [])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.outcomes[0].reason, "restored_completed_result")

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
        self.assertEqual(document["restored_task_count"], 0)
        self.assertEqual(document["scheduled_task_count"], 2)
        self.assertEqual(document["terminal_task_count"], 2)
        self.assertEqual(document["peak_running_task_count"], 1)
        self.assertEqual(document["max_ready_queue_depth"], 1)
        self.assertEqual(
            set(document["admission_blocked_task_count_by_reason"].values()),
            {0},
        )
        self.assertEqual(
            set(document["admission_wait_seconds_by_reason"].values()),
            {0.0},
        )
        self.assertEqual(document["max_task_admission_wait_seconds"], 0.0)

    def test_segment_records_worker_slot_admission_wait(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        first = _task(endpoint, "first", "slow")
        second = _task(endpoint, "second", "ok")
        plan = self._plan((first, second))

        def slow(request):
            time.sleep(0.02)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=self._store(root, plan),
                    registry=ServiceRegistry(
                        (
                            RegisteredService("slow", slow),
                            RegisteredService("ok", _result),
                        )
                    ),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                ),
            )
            segment = next((root / "execution_segments").glob("segment_*.json"))
            document = json.loads(segment.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(document["max_ready_queue_depth"], 2)
        self.assertEqual(document["peak_running_task_count"], 1)
        self.assertEqual(
            document["admission_blocked_task_count_by_reason"]["worker_slots"],
            1,
        )
        self.assertGreater(
            document["admission_wait_seconds_by_reason"]["worker_slots"],
            0.0,
        )
        self.assertGreater(document["max_task_admission_wait_seconds"], 0.0)

    def test_segment_records_resource_token_admission_wait_and_peaks(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        first = _task(
            endpoint,
            "oss_axis_equivalence_first",
            "slow",
        )
        second = _task(
            endpoint,
            "oss_axis_equivalence_second",
            "ok",
        )
        plan = self._plan((first, second))

        def slow(request):
            time.sleep(0.02)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            with patch.object(
                _ResourceLedger,
                "_memory_state",
                return_value=(128 * 1024**3, 128 * 1024**3),
            ):
                result = execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=self._store(root, plan),
                        registry=ServiceRegistry(
                            (
                                RegisteredService("slow", slow),
                                RegisteredService("ok", _result),
                            )
                        ),
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=2,
                    ),
                )
            segment = next((root / "execution_segments").glob("segment_*.json"))
            document = json.loads(segment.read_text(encoding="utf-8"))

        blocked = document["admission_blocked_task_count_by_reason"]
        waited = document["admission_wait_seconds_by_reason"]
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(document["scheduled_task_count"], 2)
        self.assertEqual(document["terminal_task_count"], 2)
        self.assertEqual(document["peak_running_task_count"], 1)
        self.assertEqual(document["peak_reserved_cpu_slots"], 1)
        self.assertEqual(document["peak_reserved_memory_bytes"], 48 * 1024**3)
        self.assertEqual(document["peak_reserved_connectome_io_slots"], 1)
        self.assertEqual(document["peak_reserved_external_solver_slots"], 1)
        for reason in ("managed_memory", "external_solver"):
            self.assertEqual(blocked[reason], 1)
            self.assertGreater(waited[reason], 0.0)
        self.assertEqual(blocked["connectome_io"], 0)
        self.assertEqual(waited["connectome_io"], 0.0)

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

    def test_gate_uses_nearest_fact_owner_over_deeper_legacy_fact(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        legacy = _task(endpoint, "legacy", "legacy_false")
        owner = _task(
            endpoint,
            "owner",
            "owner_true",
            dependencies=(legacy.task_id,),
        )
        target = _task(
            endpoint,
            "target",
            "sentinel",
            dependencies=(owner.task_id,),
            gates=(GateRequirement("formal_source_available", "not_run_no_formal"),),
        )
        plan = self._plan((legacy, owner, target))
        calls: list[str] = []

        def with_fact(request, value: bool) -> ServiceResult:
            return ServiceResult.from_record(
                _source(request.provider.endpoints[request.task.endpoint_id]),
                facts={"formal_source_available": value},
            )

        def sentinel(request):
            calls.append(request.task.task_id)
            return _result(request)

        registry = ServiceRegistry(
            (
                RegisteredService("legacy_false", lambda request: with_fact(request, False)),
                RegisteredService("owner_true", lambda request: with_fact(request, True)),
                RegisteredService("sentinel", sentinel),
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
        self.assertEqual(calls, [target.task_id])
        self.assertEqual(result.outcomes[-1].status, "completed")

    def test_gate_rejects_conflicting_facts_at_the_same_nearest_layer(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        left = _task(endpoint, "left", "left_true")
        right = _task(endpoint, "right", "right_false")
        target = _task(
            endpoint,
            "target",
            "sentinel",
            dependencies=(left.task_id, right.task_id),
            gates=(GateRequirement("formal_source_available", "not_run_no_formal"),),
        )
        plan = self._plan((left, right, target))
        calls: list[str] = []

        def with_fact(request, value: bool) -> ServiceResult:
            return ServiceResult.from_record(
                _source(request.provider.endpoints[request.task.endpoint_id]),
                facts={"formal_source_available": value},
            )

        registry = ServiceRegistry(
            (
                RegisteredService("left_true", lambda request: with_fact(request, True)),
                RegisteredService("right_false", lambda request: with_fact(request, False)),
                RegisteredService(
                    "sentinel",
                    lambda request: calls.append(request.task.task_id) or _result(request),
                ),
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
                    workers=2,
                ),
            )

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(calls, [])
        self.assertEqual(result.outcomes[-1].status, "failed")
        self.assertIn("contradictory", result.outcomes[-1].reason)

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

    def test_resume_reruns_completed_json_with_undecodable_result(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(endpoint, "single", "count")
        plan = self._plan((task,))
        calls: list[str] = []

        def count(request):
            calls.append(request.task.task_id)
            (request.output_dir / "attempt_marker.txt").write_text(
                f"invocation-{len(calls)}\n",
                encoding="utf-8",
            )
            return _result(request)

        registry = ServiceRegistry((RegisteredService("count", count),))
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
            task_root = root / "work" / task.task_id
            first_attempts = tuple(sorted(task_root.glob("attempt-*")))
            self.assertEqual(len(first_attempts), 1)
            first_attempt_snapshot = {
                path.relative_to(first_attempts[0]).as_posix(): path.read_bytes()
                for path in first_attempts[0].rglob("*")
                if path.is_file()
            }
            payload = store.read_task_state(task.task_id)
            assert payload is not None and payload["result"] is not None
            payload["result"]["record_id"] = "source_tampered"
            store.write_task_state(task.task_id, payload)
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
            resumed_attempts = tuple(sorted(task_root.glob("attempt-*")))
            retained_attempt_snapshot = {
                path.relative_to(first_attempts[0]).as_posix(): path.read_bytes()
                for path in first_attempts[0].rglob("*")
                if path.is_file()
            }
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(resumed.exit_code, 0)
        self.assertEqual(calls, [task.task_id, task.task_id])
        self.assertEqual(len(first_attempts), 1)
        self.assertEqual(len(resumed_attempts), 2)
        self.assertEqual(first_attempt_snapshot, retained_attempt_snapshot)

    def test_resume_reruns_completed_json_with_incomplete_result(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "prepare",
            "write_artifact",
            output_record_type="ArtifactRef",
        )
        plan = self._plan((task,))

        calls: list[str] = []

        def write_artifact(request):
            calls.append(request.task.task_id)
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
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(resumed.exit_code, 0)
        self.assertEqual(calls, [task.task_id, task.task_id])

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
            payload = first_store.read_task_state(task.task_id)
            assert payload is not None
            payload["endpoint_id"] = "obsolete-endpoint"
            payload["service_id"] = "obsolete-service"
            first_store.write_task_state(task.task_id, payload)
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
            audit_only_mismatch = RunIdentity(
                study_id="synthetic",
                run_id="run-001",
                study_base_sha256="e" * 64,
                code_identity="synthetic-code-v2",
                configuration_hash="c" * 64,
                scientific_configuration_hash="d" * 64,
                plan_hash="f" * 64,
                parent_run_id="older-run",
            )
            changed_audit_store = RunStore.open(
                root,
                audit_only_mismatch,
                resolved_configuration={"profile": "changed-derived-snapshot"},
                configuration_sources=(),
                resume=True,
            )
            changed_audit_resume = execute_plan(
                plan,
                ExecutionContext(
                    run_store=changed_audit_store,
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
        self.assertEqual(resumed.exit_code, 0)
        self.assertEqual(changed_audit_resume.exit_code, 0)
        self.assertEqual(
            changed_audit_resume.outcomes[0].reason,
            "restored_completed_result",
        )
        self.assertEqual(calls, [task.task_id])

    def test_resume_reruns_only_missing_operator_scratch_workspace(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        task = _task(
            endpoint,
            "formal_operator_workspace",
            "write_scratch",
            output_record_type="FormalOperatorScratchRecord",
        )
        plan = self._plan((task,))
        calls: list[str] = []

        def write_scratch(request):
            calls.append(request.task.task_id)
            generation = request.output_dir / "operator-generation-test"
            generation.mkdir(parents=True, exist_ok=False)
            value = np.arange(4, dtype=np.float64).reshape(2, 2)
            path = generation / "00_score_operator.npy"
            np.save(path, value)
            array = ScratchArrayRecord(
                name="score_operator",
                filename=path.name,
                dtype=value.dtype.name,
                shape=value.shape,
                fortran_order=False,
                nbytes=value.nbytes,
            )
            run_root = next(
                parent.parent
                for parent in request.output_dir.parents
                if parent.name == "work"
            )
            record = FormalOperatorScratchRecord(
                target_id=request.task.endpoint_id,
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
            return ServiceResult.from_record(record)

        registry = ServiceRegistry(
            (RegisteredService("write_scratch", write_scratch),)
        )
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
            self.assertIsNotNone(first.outcomes[0].result, first.outcomes[0].reason)
            record = first.outcomes[0].result.decode_record()
            assert isinstance(record, FormalOperatorScratchRecord)

            retained_store = self._store(root, plan, resume=True)
            retained = execute_plan(
                plan,
                ExecutionContext(
                    run_store=retained_store,
                    registry=registry,
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=1,
                    resume=True,
                ),
            )
            self.assertEqual(
                retained.outcomes[0].reason,
                "restored_completed_result",
            )
            cleanup_formal_operator_scratch_record(record, root)

            missing_store = self._store(root, plan, resume=True)
            rerun = execute_plan(
                plan,
                ExecutionContext(
                    run_store=missing_store,
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
        self.assertEqual(retained.exit_code, 0)
        self.assertEqual(rerun.exit_code, 0)
        self.assertEqual(calls, [task.task_id, task.task_id])
        self.assertEqual(rerun.outcomes[0].reason, "none")

    def test_resume_runs_only_missing_jitter_blocks_and_their_consumer(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        first_block = _task(endpoint, "jitter_block_0000_0025", "count")
        second_block = _task(endpoint, "jitter_block_0025_0050", "count")
        consumer = _task(
            endpoint,
            "spatial_jitter",
            "count",
            dependencies=(first_block.task_id, second_block.task_id),
        )
        plan = self._plan((first_block, second_block, consumer))
        calls: list[str] = []

        def count(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            completed = TaskOutcome(
                task_id=first_block.task_id,
                endpoint_id=first_block.endpoint_id,
                service_id=first_block.service_id,
                status="completed",
                reason="none",
                result=ServiceResult.from_record(_source(endpoint)),
            )
            store.write_task_state(first_block.task_id, completed.as_dict())
            result = execute_plan(
                plan,
                ExecutionContext(
                    run_store=store,
                    registry=ServiceRegistry((RegisteredService("count", count),)),
                    provider=_Provider(endpoint),
                    endpoint_facts={},
                    allow_expensive_producers=False,
                    continue_on_endpoint_failure=True,
                    workers=2,
                    resume=True,
                ),
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls, [second_block.task_id, consumer.task_id])
        outcomes = {outcome.task_id: outcome for outcome in result.outcomes}
        self.assertEqual(
            outcomes[first_block.task_id].reason,
            "restored_completed_result",
        )

    def test_ppam_false_gate_skips_null_tasks_but_runs_aggregate(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        observed = _task(endpoint, "ppam_observed_workspace", "observed")
        ready_gate = GateRequirement(
            "ppam_permutation_ready",
            "not_run_ppam_permutation_not_ready",
        )
        schedule = _task(
            endpoint,
            "ppam_permutation_schedule",
            "must_not_run",
            dependencies=(observed.task_id,),
            gates=(ready_gate,),
        )
        block = _task(
            endpoint,
            "ppam_permutation_block_0000",
            "must_not_run",
            dependencies=(observed.task_id, schedule.task_id),
            gates=(ready_gate,),
        )
        aggregate = _task(
            endpoint,
            "activation_sensitivity",
            "aggregate_ppam_activation",
            dependencies=(observed.task_id, schedule.task_id, block.task_id),
        )
        plan = self._plan((observed, schedule, block, aggregate))
        calls: list[str] = []

        def observed_service(request):
            calls.append(request.task.task_id)
            return ServiceResult.from_record(
                _source(endpoint),
                facts={"ppam_permutation_ready": False},
            )

        def aggregate_service(request):
            calls.append(request.task.task_id)
            self.assertEqual(request.dependencies[schedule.task_id].status, "skipped")
            self.assertEqual(request.dependencies[block.task_id].status, "skipped")
            return _result(request)

        def must_not_run(request):
            raise AssertionError(f"unexpected pPAM null task {request.task.task_id}")

        registry = ServiceRegistry(
            (
                RegisteredService("observed", observed_service),
                RegisteredService("must_not_run", must_not_run),
                RegisteredService("aggregate_ppam_activation", aggregate_service),
            )
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(
                _ResourceLedger,
                "_memory_state",
                return_value=(128 * 1024**3, 128 * 1024**3),
            ):
                result = execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=self._store(
                            Path(temporary_directory) / "run",
                            plan,
                        ),
                        registry=registry,
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=2,
                    ),
                )
        outcomes = {outcome.task_id: outcome for outcome in result.outcomes}
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls, [observed.task_id, aggregate.task_id])
        self.assertEqual(outcomes[schedule.task_id].status, "skipped")
        self.assertEqual(outcomes[block.task_id].status, "skipped")
        self.assertEqual(outcomes[aggregate.task_id].status, "completed")

    def test_resume_runs_only_missing_ppam_block_and_aggregate(self) -> None:
        endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "formal_connectome",
        )
        observed = _task(endpoint, "ppam_observed_workspace", "count")
        ready_gate = GateRequirement(
            "ppam_permutation_ready",
            "not_run_ppam_permutation_not_ready",
        )
        schedule = _task(
            endpoint,
            "ppam_permutation_schedule",
            "count",
            dependencies=(observed.task_id,),
            gates=(ready_gate,),
        )
        first_block = _task(
            endpoint,
            "ppam_permutation_block_0000",
            "count",
            dependencies=(observed.task_id, schedule.task_id),
            gates=(ready_gate,),
        )
        second_block = _task(
            endpoint,
            "ppam_permutation_block_0001",
            "count",
            dependencies=(observed.task_id, schedule.task_id),
            gates=(ready_gate,),
        )
        aggregate = _task(
            endpoint,
            "activation_sensitivity",
            "count",
            dependencies=(
                observed.task_id,
                schedule.task_id,
                first_block.task_id,
                second_block.task_id,
            ),
        )
        plan = self._plan(
            (observed, schedule, first_block, second_block, aggregate)
        )
        calls: list[str] = []

        def count(request):
            calls.append(request.task.task_id)
            return _result(request)

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self._store(Path(temporary_directory) / "run", plan)
            completed_records = (
                (
                    observed,
                    ServiceResult.from_record(
                        _source(endpoint),
                        facts={"ppam_permutation_ready": True},
                    ),
                ),
                (schedule, ServiceResult.from_record(_source(endpoint))),
                (first_block, ServiceResult.from_record(_source(endpoint))),
            )
            for task, service_result in completed_records:
                store.write_task_state(
                    task.task_id,
                    TaskOutcome(
                        task_id=task.task_id,
                        endpoint_id=task.endpoint_id,
                        service_id=task.service_id,
                        status="completed",
                        reason="none",
                        result=service_result,
                    ).as_dict(),
                )
            with patch.object(
                _ResourceLedger,
                "_memory_state",
                return_value=(128 * 1024**3, 128 * 1024**3),
            ):
                result = execute_plan(
                    plan,
                    ExecutionContext(
                        run_store=store,
                        registry=ServiceRegistry(
                            (RegisteredService("count", count),)
                        ),
                        provider=_Provider(endpoint),
                        endpoint_facts={},
                        allow_expensive_producers=False,
                        continue_on_endpoint_failure=True,
                        workers=2,
                        resume=True,
                    ),
                )
        outcomes = {outcome.task_id: outcome for outcome in result.outcomes}
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(calls, [second_block.task_id, aggregate.task_id])
        for task in (observed, schedule, first_block):
            self.assertEqual(
                outcomes[task.task_id].reason,
                "restored_completed_result",
            )

    def test_resume_uses_only_json_yaml_and_completed_result_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "run"
            initial_identity = RunIdentity(
                study_id="synthetic",
                run_id="run-001",
                study_base_sha256="e" * 64,
                code_identity="synthetic-code-v1",
                configuration_hash="a" * 64,
                scientific_configuration_hash="b" * 64,
                plan_hash="c" * 64,
            )
            initial_sources = (
                ConfigurationSource("file:///machine-a/study.json", "e" * 64),
                ConfigurationSource("file:///machine-a/workflow.yaml", "1" * 64),
                ConfigurationSource("file:///machine-a/voxel.yaml", "2" * 64),
                ConfigurationSource("file:///machine-a/fiber.yaml", "3" * 64),
            )
            RunStore.open(
                root,
                initial_identity,
                resolved_configuration={"snapshot": "initial"},
                configuration_sources=initial_sources,
            )
            changed_audit_identity = RunIdentity(
                study_id="renamed-audit-study",
                run_id="run-001",
                study_base_sha256="e" * 64,
                code_identity="synthetic-code-v2",
                configuration_hash="4" * 64,
                scientific_configuration_hash="5" * 64,
                plan_hash="6" * 64,
                parent_run_id="different-parent",
            )
            copied_sources = (
                ConfigurationSource("file:///machine-b/study.json", "e" * 64),
                ConfigurationSource("file:///machine-b/workflow.yaml", "1" * 64),
                ConfigurationSource("file:///machine-b/voxel.yaml", "2" * 64),
                ConfigurationSource("file:///machine-b/fiber.yaml", "3" * 64),
            )
            RunStore.open(
                root,
                changed_audit_identity,
                resolved_configuration={"snapshot": "changed"},
                configuration_sources=copied_sources,
                resume=True,
            )

            changed_json_identity = replace(
                changed_audit_identity,
                study_base_sha256="7" * 64,
            )
            changed_json_sources = (
                replace(copied_sources[0], sha256="7" * 64),
                *copied_sources[1:],
            )
            with self.assertRaisesRegex(RunStoreError, "input JSON content"):
                RunStore.open(
                    root,
                    changed_json_identity,
                    resolved_configuration={},
                    configuration_sources=changed_json_sources,
                    resume=True,
                )

            changed_yaml_sources = (
                copied_sources[0],
                replace(copied_sources[1], sha256="8" * 64),
                *copied_sources[2:],
            )
            with self.assertRaisesRegex(RunStoreError, "input YAML content"):
                RunStore.open(
                    root,
                    changed_audit_identity,
                    resolved_configuration={},
                    configuration_sources=changed_yaml_sources,
                    resume=True,
                )


if __name__ == "__main__":
    unittest.main()
