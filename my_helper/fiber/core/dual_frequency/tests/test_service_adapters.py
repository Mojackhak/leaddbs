"""Focused tests for production service adapters and registry closure."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from dual_frequency.backends.activation import (
    MissingAcceptanceFixture,
    OSSRowProduct,
    OSSScientificSettings,
    PPAMActivationBackend,
)
from dual_frequency.cache import (
    ArtifactStore,
    ContentAddressedCache,
    RunScopedArtifactPublisher,
)
from dual_frequency.catalog import CatalogStatus, EndpointRecord, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides
from dual_frequency.contracts import (
    ActivationArtifact,
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    BranchRecord,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    HardComputabilityLimits,
    IndexedArrayView,
    NormativeFiberScoreSettings,
    ObservedResult,
    PreparedExposureRecord,
    PPAMObservedWorkspaceRecord,
    PPAMPermutationBlockRecord,
    ResamplingScheduleRecord,
    SourceRecord,
    SubjectExclusionRecord,
)
from dual_frequency.runtime import service_adapters
from dual_frequency.runtime.activation_provider import (
    CanonicalStimulationSource,
    OSSActivationProvider,
    OSSActivationRuntimeRequest,
    OSSProducerRequest,
)
from dual_frequency.backends.nuisance import NuisancePlanError
from dual_frequency.runtime.service_adapters import (
    PRODUCTION_SERVICE_HANDLERS,
    build_default_service_registry,
)
from dual_frequency.runtime.ppam_observed_workspace import (
    activation_request_from_ppam_workspace,
)
from dual_frequency.workflow import compile_execution_plan
from dual_frequency.workflow.executor import DependencyState, TaskExecutionRequest
from dual_frequency.workflow.planner import TaskSpec
from dual_frequency.workflow.registry import build_default_registry

try:
    from .test_catalog import make_workflow, synthetic_study
except ImportError:  # unittest discovery loads this module without a package name
    from test_catalog import make_workflow, synthetic_study


def _axis(name: str, count: int, token: str) -> AxisRef:
    return AxisRef(name, count, token * 64)


def _artifact(
    name: str,
    *,
    kind: str,
    axes: tuple[AxisRef, ...] = (),
    dtype: str | None = None,
    units: str | None = None,
    space: str | None = None,
) -> ArtifactRef:
    shape = tuple(axis.count for axis in axes) if axes else None
    return ArtifactRef(
        kind=kind,
        schema_version="test_v1",
        uri=f"file:///tmp/{name}",
        sha256="a" * 64,
        dtype=dtype,
        shape=shape,
        axis_refs=axes,
        axis_hashes=tuple(axis.sha256 for axis in axes),
        units=units,
        space=space,
        producer_id="test",
        producer_version="1",
    )


def _endpoint_record(key: EndpointKey, *, matched: str | None = None) -> EndpointRecord:
    return EndpointRecord(
        key=key,
        scale_label="Synthetic scale",
        scale_direction="lower",
        baseline_binding_id="baseline:phase-a_program-0",
        outcome_binding_id="reference:phase-b_program-1",
        matched_reference_endpoint_id=matched,
        connectome_role="none",
        final_eligible=True,
        requested=True,
        subject_ids=tuple(f"subject-{index:02d}" for index in range(12)),
        minimum_subjects=12,
        status=CatalogStatus.DATA_AVAILABLE,
    )


def _endpoint_input(endpoint: EndpointKey) -> EndpointInputRecord:
    subject_axis = _axis("subjects", 12, "1")
    subject_ids = tuple(f"subject-{index:02d}" for index in range(12))
    return EndpointInputRecord(
        endpoint=endpoint,
        readiness_status="ready",
        candidate_subject_ids=subject_ids,
        included_subject_ids=subject_ids,
        exclusions=(),
        minimum_subjects=12,
        subject_axis=subject_axis,
        baseline=_artifact(
            "baseline.npy",
            kind="endpoint_baseline",
            axes=(subject_axis,),
            dtype="float64",
            units="score",
        ),
        outcome=_artifact(
            "outcome.npy",
            kind="endpoint_outcome",
            axes=(subject_axis,),
            dtype="float64",
            units="score",
        ),
    )


def _prepared(endpoint_input: EndpointInputRecord) -> PreparedExposureRecord:
    assert endpoint_input.subject_axis is not None
    feature_axis = _axis("voxels", 20, "2")
    return PreparedExposureRecord(
        endpoint=endpoint_input.endpoint,
        subject_axis=endpoint_input.subject_axis,
        feature_axis=feature_axis,
        exposure=_artifact(
            "exposure.npy",
            kind="prepared_reference_exposure",
            axes=(endpoint_input.subject_axis, feature_axis),
            dtype="float32",
            units="V/m",
            space="canonical",
        ),
        feature_ids=_artifact(
            "feature_ids.npy",
            kind="canonical_brainmask_voxel_ids",
            axes=(feature_axis,),
            dtype="int64",
            space="canonical",
        ),
        delta_reference_input_status="not_applicable",
        delta_reference_reason_code="not_applicable",
        auxiliary_readiness=None,
        reference_condition_exposure=None,
        addon_reference_component_exposure=None,
        reference_overlap_mask=None,
        total_exposure=None,
    )


def _addon_prepared(endpoint_input: EndpointInputRecord) -> PreparedExposureRecord:
    assert endpoint_input.subject_axis is not None
    feature_axis = _axis("addon-voxels", 20, "4")
    axes = (endpoint_input.subject_axis, feature_axis)
    return PreparedExposureRecord(
        endpoint=endpoint_input.endpoint,
        subject_axis=endpoint_input.subject_axis,
        feature_axis=feature_axis,
        exposure=_artifact(
            "addon-exposure.npy",
            kind="prepared_addon_exposure",
            axes=axes,
            dtype="float32",
            units="V/m",
            space="canonical",
        ),
        feature_ids=_artifact(
            "addon-feature-ids.npy",
            kind="canonical_brainmask_voxel_ids",
            axes=(feature_axis,),
            dtype="int64",
            units="voxel_id",
            space="canonical",
        ),
        delta_reference_input_status="ready",
        delta_reference_reason_code="ready",
        auxiliary_readiness=_artifact(
            "addon-auxiliary-readiness.json",
            kind="synthetic_auxiliary_readiness",
        ),
        reference_condition_exposure=_artifact(
            "reference-condition-exposure.npy",
            kind="reference_condition_exposure",
            axes=axes,
            dtype="float32",
            units="V/m",
            space="canonical",
        ),
        addon_reference_component_exposure=_artifact(
            "addon-reference-component-exposure.npy",
            kind="addon_reference_component_exposure",
            axes=axes,
            dtype="float32",
            units="V/m",
            space="canonical",
        ),
        reference_overlap_mask=_artifact(
            "reference-overlap-mask.npy",
            kind="reference_overlap_mask",
            axes=axes,
            dtype="bool",
            units="binary",
            space="canonical",
        ),
        total_exposure=_artifact(
            "total-exposure.npy",
            kind="raw_addon_component_exposure",
            axes=axes,
            dtype="float32",
            units="V/m",
            space="canonical",
        ),
    )


def _source(endpoint: EndpointKey, *, prediction: str = "error_nonpredictive") -> SourceRecord:
    selected_axis = _axis(f"{endpoint.identifier}:selected", 20, "3")
    selected_artifact = _artifact(
        f"{endpoint.identifier}-selected.npy",
        kind="selected_feature_indices",
        axes=(selected_axis,),
        dtype="int64",
    )
    return SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status=prediction,
        threshold_source="pre_specified",
        selected_tau=200.0,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(selected_axis, "canonical_brainmask"),
        artifacts=(selected_artifact,),
    )


def _task(
    endpoint: EndpointKey,
    *,
    service_id: str,
    stage: str,
    output_type: str,
    dependencies: tuple[str, ...] = (),
    branch: str = "none",
    connectome_role: str = "none",
    phase: str = "observed",
    execution_parameters: tuple[tuple[str, str], ...] = (),
) -> TaskSpec:
    from dual_frequency.contracts import TaskKey

    return TaskSpec(
        key=TaskKey(endpoint.identifier, stage, branch, "f" * 64),
        endpoint_id=endpoint.identifier,
        model_family=endpoint.model_family,
        connectome_role=connectome_role,
        stage=stage,
        round_id="test",
        phase=phase,
        service_id=service_id,
        dependencies=dependencies,
        gates=(),
        output_record_type=output_type,
        execution_parameters=execution_parameters,
    )


def _activation_case():
    endpoint = EndpointKey(
        "synthetic-study",
        "synthetic-scale",
        "reference-binding",
        "reference_fiber",
        "formal-connectome",
    )
    endpoint_input = _endpoint_input(endpoint)
    assert endpoint_input.subject_axis is not None
    feature_axis = _axis("fibers", 24, "6")
    feature_ids = np.arange(1_000, 1_000 + feature_axis.count, dtype=np.int64)
    prepared = PreparedExposureRecord(
        endpoint=endpoint,
        subject_axis=endpoint_input.subject_axis,
        feature_axis=feature_axis,
        exposure=_artifact(
            "reference-fiber-exposure.npy",
            kind="prepared_reference_fiber_exposure",
            axes=(endpoint_input.subject_axis, feature_axis),
            dtype="float32",
            units="V/m",
            space="right_canonical",
        ),
        feature_ids=_artifact(
            "parent-fiber-ids.npy",
            kind="canonical_fiber_ids",
            axes=(feature_axis,),
            dtype="int64",
            units="fiber_id",
            space="right_canonical",
        ),
        delta_reference_input_status="not_applicable",
        delta_reference_reason_code="not_applicable",
        auxiliary_readiness=None,
        reference_condition_exposure=None,
        addon_reference_component_exposure=None,
        reference_overlap_mask=None,
        total_exposure=None,
    )
    selected_ids = _artifact(
        "selected-fiber-ids.npy",
        kind="normative_fiber_valid_union_ids",
        axes=(feature_axis,),
        dtype="int64",
        units="fiber_id",
        space="right_canonical",
    )
    source = SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status="pre_specified_accepted",
        prediction_status="error_nonpredictive",
        threshold_source="pre_specified",
        selected_tau=800.0,
        selected_coverage=5,
        adjacent_support=2,
        feature_axis=FeatureAxisRef(feature_axis, "right_canonical_fiber_ids"),
        artifacts=(selected_ids,),
    )
    final = FinalModelRecord(
        endpoint=endpoint,
        final_status="final_model_realized",
        realization_role="primary",
        final_key=FinalModelKey(
            endpoint.identifier,
            "reference",
            800.0,
            5,
            "continuous_dose_weighted_peak",
        ),
        selected_source=source,
        selected_branch=None,
    )
    selection = FinalSelectionRecord(
        endpoint=endpoint,
        selection_status="final_model_realized",
        final_model=final,
        reason_codes=("primary_model_realized",),
        causal_task_ids=("synthetic_final_task",),
    )
    sources = []
    for subject_index, subject_id in enumerate(endpoint_input.included_subject_ids):
        for side_index, side in enumerate(("L", "R")):
            seed = 100 + subject_index * 2 + side_index
            sources.append(
                CanonicalStimulationSource(
                    subject_id=subject_id,
                    side=side,
                    frequency_group_id=f"group-{side.lower()}",
                    delivery_mode="continuous",
                    source_id=f"source-{subject_index:02d}-{side.lower()}",
                    geometry=_activation_geometry(seed),
                    canonicalization=(
                        "left_to_right" if side == "L" else "identity"
                    ),
                    stimulation_hash=_digest(seed + 1_000),
                    component_frequency_hash=_digest(seed + 2_000),
                    transform_hash=_digest(seed + 3_000),
                )
            )
    return (
        endpoint_input,
        prepared,
        final,
        selection,
        feature_axis,
        feature_ids,
        tuple(sources),
    )


class _Provider:
    def __init__(self, endpoints: tuple[EndpointRecord, ...], endpoint_input: EndpointInputRecord):
        self._endpoints = {item.endpoint_id: item for item in endpoints}
        self.endpoint_input = endpoint_input
        self.observed_token = object()

    def endpoint(self, endpoint_id: str) -> EndpointRecord:
        return self._endpoints[endpoint_id]

    def publish_endpoint_input(self, endpoint_id: str, publisher):
        self.endpoint(endpoint_id)
        return self.endpoint_input

    def publish_prepared_exposure(self, endpoint_input, reference_dependency, publisher):
        return _prepared(endpoint_input)

    def observed_request(self, endpoint_input, prepared, *, branch, delta_reference=None):
        return self.observed_token


@dataclasses.dataclass(frozen=True)
class _FinalLinkedObservedStub:
    branch: str
    exposure: ArtifactRef
    feature_axis: AxisRef
    feature_ids: ArtifactRef | None


class _FinalLinkedProvider(_Provider):
    def __init__(
        self,
        endpoints: tuple[EndpointRecord, ...],
        endpoint_input: EndpointInputRecord,
    ) -> None:
        super().__init__(endpoints, endpoint_input)
        self.observed_prepared: PreparedExposureRecord | None = None
        self.selected_prepared: PreparedExposureRecord | None = None

    def observed_request(
        self,
        endpoint_input,
        prepared,
        *,
        branch,
        delta_reference=None,
    ):
        del endpoint_input, delta_reference
        self.observed_prepared = prepared
        return _FinalLinkedObservedStub(
            branch=branch,
            exposure=prepared.exposure,
            feature_axis=prepared.feature_axis,
            feature_ids=prepared.feature_ids,
        )

    def selected_exposure(self, final, prepared, publisher):
        del publisher
        self.selected_prepared = prepared
        selected_axis = final.valid_feature_axis.axis
        return (
            _artifact(
                "selected-final-exposure.npy",
                kind="selected_final_exposure",
                axes=(prepared.subject_axis, selected_axis),
                dtype="float32",
                units="V/m",
                space="canonical",
            ),
            None,
        )


def _digest(seed: int) -> str:
    return f"{seed:064x}"


def _activation_geometry(seed: int) -> ArtifactRef:
    return ArtifactRef(
        kind="synthetic_stimulation_geometry",
        schema_version="synthetic_v1",
        uri=f"memory://service-adapter/geometry-{seed}",
        sha256=_digest(seed),
        dtype=None,
        shape=None,
        axis_refs=(),
        axis_hashes=(),
        units=None,
        space="native",
        producer_id="synthetic",
        producer_version="1",
    )


class _ActivationToolchain:
    def __init__(self, subject_ids: tuple[str, ...]) -> None:
        self._subject_index = {
            subject_id: index for index, subject_id in enumerate(subject_ids)
        }
        self.calls: list[OSSProducerRequest] = []

    def produce(self, request: OSSProducerRequest) -> OSSRowProduct:
        self.calls.append(request)
        subject_index = self._subject_index[request.row.subject_id]
        side_index = 0 if request.row.side == "L" else 1
        feature_index = np.arange(request.row.feature_axis.count)
        active = (
            subject_index * 2 + feature_index + side_index
        ) % 5 < 2
        probability = np.where(active, 0.8, 0.2).astype(np.float32)
        return OSSRowProduct(request.row.feature_ids, probability)


class _ZeroActivationToolchain(_ActivationToolchain):
    def produce(self, request: OSSProducerRequest) -> OSSRowProduct:
        self.calls.append(request)
        return OSSRowProduct(
            request.row.feature_ids,
            np.full(request.row.feature_axis.count, 0.2, dtype=np.float32),
        )


class _ActivationProvider:
    def __init__(
        self,
        *,
        final_model: FinalModelRecord,
        subject_axis: AxisRef,
        subject_ids: tuple[str, ...],
        feature_axis: AxisRef,
        feature_ids: np.ndarray,
        sources: tuple[CanonicalStimulationSource, ...],
        toolchain: _ActivationToolchain,
    ) -> None:
        self.final_model = final_model
        self.subject_axis = subject_axis
        self.subject_ids = subject_ids
        self.feature_axis = feature_axis
        self.feature_ids = feature_ids
        self.sources = sources
        self.toolchain = toolchain
        self.fitting_calls = 0
        self.toolchain_resolution_calls = 0

    def activation_runtime_request(
        self,
        final_model,
        endpoint_input,
        prepared,
        publisher,
        *,
        workers,
        allow_expensive_producers,
    ) -> OSSActivationRuntimeRequest:
        del endpoint_input, prepared, publisher
        if final_model != self.final_model:
            raise AssertionError("service passed a different final model")
        return OSSActivationRuntimeRequest(
            final_model=final_model,
            connectome_role="formal",
            subject_axis=self.subject_axis,
            subject_ids=self.subject_ids,
            feature_axis=self.feature_axis,
            feature_ids=self.feature_ids,
            sources=self.sources,
            connectome_feature_hash="9" * 64,
            settings=OSSScientificSettings(backend_version="synthetic-oss-v1"),
            allow_expensive_producers=allow_expensive_producers,
            workers=workers,
        )

    def oss_producer_toolchain(self) -> _ActivationToolchain:
        self.toolchain_resolution_calls += 1
        return self.toolchain

    def activation_fitting_request(
        self,
        final_model,
        endpoint_input,
        prepared,
        materialized_rows,
        selected_overlap,
        publisher,
        *,
        delta_reference,
    ) -> ActivationRequest:
        del prepared, publisher
        if final_model != self.final_model:
            raise AssertionError("service passed a different final model")
        if selected_overlap is not None or delta_reference is not None:
            raise AssertionError("reference activation received add-on inputs")
        self.fitting_calls += 1
        subject_index = np.arange(self.subject_axis.count, dtype=np.float64)
        return ActivationRequest(
            final_model=final_model,
            activation_probability=materialized_rows.activation_probability,
            reference_overlap_mask=None,
            outcome=50.0 - 0.8 * subject_index + 0.15 * np.cos(subject_index),
            baseline=30.0 + np.sin(subject_index),
            peak_final_score=np.linspace(-1.5, 1.5, self.subject_axis.count),
            nuisance_inputs=(),
            subject_axis=endpoint_input.subject_axis,
            feature_axis=self.feature_axis,
            feature_ids=materialized_rows.feature_ids,
            activation_feature_ids=materialized_rows.feature_ids,
            outcome_direction="lower",
            hard_computability=HardComputabilityLimits(12, None, 5),
            connectome_role="formal",
            fiber_score_settings=NormativeFiberScoreSettings(
                sweet_fraction=0.1,
                sour_fraction=0.1,
                weighted_peak_fraction=0.2,
                sweet_selected_min_count=2,
                sour_selected_min_count=2,
                weighted_peak_min_count=1,
            ),
            fitting_probability_threshold=0.5,
            permutation_resamples=1,
            seed=7,
        )


def _request(
    task: TaskSpec,
    provider: _Provider,
    output_dir: Path,
    dependencies: dict[str, DependencyState] | None = None,
) -> TaskExecutionRequest:
    return TaskExecutionRequest(
        task=task,
        dependencies=dependencies or {},
        run_id="test-run",
        output_dir=output_dir,
        provider=provider,
        artifact_store=None,
        scientific_cache=None,
        allow_expensive_producers=False,
        workers=1,
    )


class ServiceAdapterTest(unittest.TestCase):
    def test_lazy_oss_toolchain_factory_resolves_once_on_first_producer_call(
        self,
    ) -> None:
        factory_calls: list[object] = []
        producer_calls: list[object] = []

        class Toolchain:
            @staticmethod
            def produce_with_evidence(request):
                producer_calls.append(request)
                return request

        def factory():
            factory_calls.append(object())
            return Toolchain()

        lazy = service_adapters._LazyOSSProducerToolchain(factory)
        self.assertEqual(factory_calls, [])
        first = object()
        second = object()
        self.assertIs(lazy.produce_with_evidence(first), first)
        self.assertIs(lazy.produce_with_evidence(second), second)
        self.assertEqual(len(factory_calls), 1)
        self.assertEqual(producer_calls, [first, second])

    def test_indexed_total_exposure_uses_bounded_selected_and_mean_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row_axis = _axis("subjects", 2, "1")
            parent_axis = _axis("parent-features", 5, "2")
            logical_axis = _axis("logical-features", 3, "3")
            publisher = RunScopedArtifactPublisher(
                root / "artifacts",
                "indexed-total",
                "1",
            )
            parent_values = np.arange(10, dtype=np.float32).reshape(2, 5)
            parent = publisher.array(
                "parent.npy",
                parent_values,
                kind="shared_physical_exposure",
                axes=(row_axis, parent_axis),
                units="V/m",
                space="MNI152NLin2009bAsym",
            )
            column_positions = publisher.array(
                "column_positions.npy",
                np.asarray((4, 1, 3), dtype=np.int64),
                kind="indexed_array_column_positions",
                axes=(logical_axis,),
                units="index",
                space=None,
            )
            view = IndexedArrayView(
                parent=parent,
                row_positions=None,
                column_positions=column_positions,
                axis_refs=(row_axis, logical_axis),
            )
            store = ArtifactStore((root,))
            request = SimpleNamespace(artifact_store=store)
            with patch.object(
                store,
                "materialize_indexed_array_view",
                side_effect=AssertionError(
                    "sensitivity helpers must not materialize the complete view"
                ),
            ):
                selected = service_adapters._selected_scientific_columns(
                    request,
                    view,
                    np.asarray((2, 0), dtype=np.int64),
                )
                means = service_adapters._scientific_row_mean(request, view)
            np.testing.assert_array_equal(
                selected,
                parent_values[:, (3, 4)],
            )
            np.testing.assert_allclose(
                means,
                np.mean(parent_values[:, (4, 1, 3)], axis=1),
                rtol=0.0,
                atol=1e-6,
            )

    @staticmethod
    def _activation_execution_request(
        *,
        root: Path,
        cache: ContentAddressedCache,
        provider: _ActivationProvider,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        selection: FinalSelectionRecord,
        allow_expensive_producers: bool,
    ) -> TaskExecutionRequest:
        task = _task(
            endpoint_input.endpoint,
            service_id="run_reference_fiber_activation",
            stage="activation_sensitivity",
            output_type="ActivationArtifact",
            dependencies=("input", "prepared", "final"),
            connectome_role="formal",
            phase="sensitivity",
        )
        return TaskExecutionRequest(
            task=task,
            dependencies={
                "input": DependencyState("completed", "none", endpoint_input),
                "prepared": DependencyState("completed", "none", prepared),
                "final": DependencyState("completed", "none", selection),
            },
            run_id="synthetic-activation-run",
            output_dir=root / "service-output",
            provider=provider,
            artifact_store=ArtifactStore((root,)),
            scientific_cache=cache,
            allow_expensive_producers=allow_expensive_producers,
            workers=2,
        )

    @staticmethod
    def _ppam_execution_request(
        *,
        root: Path,
        task: TaskSpec,
        provider: _ActivationProvider,
        cache: ContentAddressedCache,
        dependencies: dict[str, DependencyState],
    ) -> TaskExecutionRequest:
        return TaskExecutionRequest(
            task=task,
            dependencies=dependencies,
            run_id="synthetic-ppam-run",
            output_dir=(
                root
                / "work"
                / f"task_{task.stage}"
                / "attempt-0000000000000001"
            ),
            provider=provider,
            artifact_store=ArtifactStore((root,)),
            scientific_cache=cache,
            allow_expensive_producers=False,
            workers=2,
        )

    def test_default_registry_exactly_covers_planner_services(self) -> None:
        configuration = make_workflow(WorkflowOverrides(all_available=True))
        catalog = build_endpoint_catalog(configuration, synthetic_study())
        plan = compile_execution_plan(configuration, catalog)
        planned = {task.service_id for task in plan.tasks}
        declared = {service_id for service_id, _handler in PRODUCTION_SERVICE_HANDLERS}
        extension_only = {
            "establish_oss_axis_equivalence",
            "prepare_jitter_exposure_block",
            "run_addon_fiber_activation",
            "run_reference_fiber_activation",
            "run_addon_fiber_formal_permutation",
            "run_addon_voxel_formal_permutation",
            "run_reference_fiber_formal_permutation",
            "run_reference_voxel_formal_permutation",
            "run_addon_fiber_formal_bootstrap",
            "run_addon_voxel_formal_bootstrap",
            "run_reference_fiber_formal_bootstrap",
            "run_reference_voxel_formal_bootstrap",
        }
        registry = build_default_registry()
        application_registry = build_default_service_registry()
        self.assertEqual(declared, planned | extension_only)
        self.assertEqual(set(registry.service_ids), planned | extension_only)
        self.assertEqual(
            set(application_registry.service_ids),
            planned | extension_only,
        )
        self.assertEqual(len(registry.service_ids), len(declared))

    def test_readiness_observed_and_resolver_preserve_typed_records(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        endpoint_record = _endpoint_record(endpoint)
        endpoint_input = _endpoint_input(endpoint)
        provider = _Provider((endpoint_record,), endpoint_input)
        registry = build_default_registry()
        source = _source(endpoint)
        observed = ObservedResult(source=source, artifacts=source.artifacts)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            readiness_task = _task(
                endpoint,
                service_id="validate_reference_voxel_input",
                stage="input_readiness",
                output_type="EndpointInputRecord",
            )
            readiness_result = registry.resolve(readiness_task.service_id)(
                _request(readiness_task, provider, root / "readiness")
            )
            self.assertEqual(readiness_result.decode_record(), endpoint_input)
            self.assertTrue(readiness_result.fact_values["endpoint_input_ready"])

            prepared = _prepared(endpoint_input)
            observed_task = _task(
                endpoint,
                service_id="run_reference_voxel_observed_grid",
                stage="observed_grid",
                output_type="ObservedResult",
                dependencies=("readiness", "prepared"),
            )
            dependencies = {
                "readiness": DependencyState("completed", "none", endpoint_input),
                "prepared": DependencyState("completed", "none", prepared),
            }
            with patch(
                "dual_frequency.runtime.service_adapters.ReferenceDirectVoxelBackend"
            ) as backend:
                backend.return_value.run.return_value = observed
                observed_result = registry.resolve(observed_task.service_id)(
                    _request(observed_task, provider, root / "observed", dependencies)
                )
                backend.return_value.run.assert_called_once_with(provider.observed_token)
            self.assertEqual(observed_result.decode_record(), observed)

            resolver_task = _task(
                endpoint,
                service_id="resolve_reference_voxel_source",
                stage="source_resolver",
                output_type="SourceRecord",
                dependencies=("observed",),
            )
            resolver_result = registry.resolve(resolver_task.service_id)(
                _request(
                    resolver_task,
                    provider,
                    root / "resolver",
                    {"observed": DependencyState("completed", "none", observed)},
                )
            )
            self.assertEqual(resolver_result.decode_record(), source)
            self.assertTrue(resolver_result.fact_values["reference_source_accepted"])

    def test_dependency_and_addon_final_use_runtime_records_without_subject_rules(self) -> None:
        reference_endpoint = EndpointKey(
            "study", "scale", "reference", "reference_voxel"
        )
        addon_endpoint = EndpointKey("study", "scale", "addon", "addon_voxel")
        reference_record = _endpoint_record(reference_endpoint)
        addon_record = _endpoint_record(
            addon_endpoint,
            matched=reference_endpoint.identifier,
        )
        addon_input = _endpoint_input(addon_endpoint)
        provider = _Provider((reference_record, addon_record), addon_input)
        registry = build_default_registry()
        reference_source = _source(reference_endpoint, prediction="error_nonpredictive")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dependency_task = _task(
                addon_endpoint,
                service_id="bind_reference_dependency",
                stage="reference_dependency",
                output_type="ReferenceDependencyRecord",
                dependencies=("reference",),
            )
            dependency_result = registry.resolve(dependency_task.service_id)(
                _request(
                    dependency_task,
                    provider,
                    root / "dependency",
                    {
                        "reference": DependencyState(
                            "completed", "none", reference_source
                        )
                    },
                )
            )
            dependency = dependency_result.decode_record()
            self.assertEqual(dependency.reference_record, reference_source)
            self.assertTrue(dependency_result.fact_values["reference_dependency_ready"])

            addon_source = _source(addon_endpoint, prediction="error_nonpredictive")
            no_delta = BranchRecord(
                endpoint=addon_endpoint,
                branch="no_delta_reference",
                intended_role="primary",
                input_status="valid",
                nuisance_design_status="valid",
                source=addon_source,
                artifacts=addon_source.artifacts,
            )
            final_task = _task(
                addon_endpoint,
                service_id="realize_addon_final",
                stage="final_realization",
                output_type="FinalSelectionRecord",
                dependencies=("input", "dependency", "delta", "no_delta", "adjusted"),
            )
            final_dependencies = {
                "input": DependencyState("completed", "none", addon_input),
                "dependency": DependencyState("completed", "none", dependency),
                "delta": DependencyState("skipped", "not_run", None),
                "no_delta": DependencyState("completed", "none", no_delta),
                "adjusted": DependencyState("skipped", "not_run", None),
            }
            final_result = registry.resolve(final_task.service_id)(
                _request(final_task, provider, root / "final", final_dependencies)
            )
            selection = final_result.decode_record()
            self.assertEqual(selection.selection_status, "final_model_realized")
            self.assertEqual(
                selection.final_model.final_key.final_branch,
                "no_delta_reference",
            )
            self.assertTrue(final_result.fact_values["final_model_realized"])

    def test_final_linked_prepared_exposure_is_selected_by_endpoint(self) -> None:
        reference_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_voxel",
        )
        addon_endpoint = EndpointKey("study", "scale", "addon", "addon_voxel")
        addon_input = _endpoint_input(addon_endpoint)
        reference_input = _endpoint_input(reference_endpoint)
        addon_prepared = _addon_prepared(addon_input)
        reference_prepared = _prepared(reference_input)
        source = _source(addon_endpoint)
        branch = BranchRecord(
            endpoint=addon_endpoint,
            branch="no_delta_reference",
            intended_role="primary",
            input_status="valid",
            nuisance_design_status="valid",
            source=source,
        )
        final = FinalModelRecord(
            endpoint=addon_endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                addon_endpoint.identifier,
                branch.branch,
                source.selected_tau,
                source.selected_coverage,
                "loocv_linear",
            ),
            selected_source=None,
            selected_branch=branch,
        )
        selection = FinalSelectionRecord(
            endpoint=addon_endpoint,
            selection_status="final_model_realized",
            final_model=final,
            reason_codes=("primary_model_realized",),
            causal_task_ids=("synthetic_final_task",),
        )
        provider = _FinalLinkedProvider(
            (
                _endpoint_record(reference_endpoint),
                _endpoint_record(
                    addon_endpoint,
                    matched=reference_endpoint.identifier,
                ),
            ),
            addon_input,
        )
        task = _task(
            addon_endpoint,
            service_id="run_addon_voxel_jitter",
            stage="spatial_jitter",
            output_type="SensitivityResult",
            dependencies=(
                "addon_input",
                "reference_input",
                "addon_prepared",
                "reference_prepared",
                "final",
            ),
            phase="sensitivity",
        )
        with tempfile.TemporaryDirectory() as temporary:
            request = _request(
                task,
                provider,
                Path(temporary),
                {
                    "addon_input": DependencyState("completed", "none", addon_input),
                    "reference_input": DependencyState(
                        "completed",
                        "none",
                        reference_input,
                    ),
                    "addon_prepared": DependencyState(
                        "completed",
                        "none",
                        addon_prepared,
                    ),
                    "reference_prepared": DependencyState(
                        "completed",
                        "none",
                        reference_prepared,
                    ),
                    "final": DependencyState("completed", "none", selection),
                },
            )
            with patch.object(
                service_adapters,
                "_selected_overlap_for_final",
                return_value=None,
            ):
                observed_final, _, prepared, _, _ = (
                    service_adapters._observed_request_for_final(request)
                )

        self.assertEqual(observed_final, final)
        self.assertEqual(prepared, addon_prepared)
        self.assertEqual(provider.observed_prepared, addon_prepared)
        self.assertEqual(provider.selected_prepared, addon_prepared)

    def test_endpoint_local_prepared_exposure_missing_or_duplicate_fails_closed(
        self,
    ) -> None:
        target_endpoint = EndpointKey("study", "scale", "addon", "addon_voxel")
        other_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_voxel",
        )
        target_prepared = _addon_prepared(_endpoint_input(target_endpoint))
        other_prepared = _prepared(_endpoint_input(other_endpoint))
        provider = _Provider(
            (
                _endpoint_record(
                    target_endpoint,
                    matched=other_endpoint.identifier,
                ),
                _endpoint_record(other_endpoint),
            ),
            _endpoint_input(target_endpoint),
        )
        task = _task(
            target_endpoint,
            service_id="run_addon_voxel_jitter",
            stage="spatial_jitter",
            output_type="SensitivityResult",
        )
        cases = {
            "missing": {
                "other": DependencyState("completed", "none", other_prepared),
            },
            "duplicate": {
                "first": DependencyState("completed", "none", target_prepared),
                "second": DependencyState("completed", "none", target_prepared),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            for name, dependencies in cases.items():
                with self.subTest(name=name), self.assertRaisesRegex(
                    service_adapters.ServiceAdapterError,
                    "requires exactly one PreparedExposureRecord for endpoint",
                ):
                    service_adapters._prepared_exposure_record(
                        _request(task, provider, Path(temporary), dependencies),
                        target_endpoint.identifier,
                    )

    def test_activation_exact_cache_hit_skips_producer_and_returns_typed_artifact(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        service_toolchain = _ActivationToolchain(subject_ids)
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=service_toolchain,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            seed_toolchain = _ActivationToolchain(subject_ids)
            seed_request = provider.activation_runtime_request(
                final,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
                workers=2,
                allow_expensive_producers=True,
            )
            OSSActivationProvider(
                cache,
                producer_toolchain=seed_toolchain,
            ).materialize(
                seed_request,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
            )
            request = self._activation_execution_request(
                root=root,
                cache=cache,
                provider=provider,
                endpoint_input=endpoint_input,
                prepared=prepared,
                selection=selection,
                allow_expensive_producers=False,
            )
            result = build_default_registry().resolve(
                "run_reference_fiber_activation"
            )(request)
            record = result.decode_record()

        self.assertEqual(len(seed_toolchain.calls), len(subject_ids) * 2)
        self.assertEqual(service_toolchain.calls, [])
        self.assertEqual(provider.toolchain_resolution_calls, 0)
        self.assertEqual(provider.fitting_calls, 1)
        self.assertIsInstance(record, ActivationArtifact)
        self.assertEqual(record.final_model_id, final.identifier)
        self.assertEqual(record.feature_axis, feature_axis)

    def test_activation_ignores_cross_endpoint_prepared_exposure(self) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=_ActivationToolchain(subject_ids),
        )
        other_endpoint = EndpointKey(
            endpoint_input.endpoint.study_id,
            endpoint_input.endpoint.scale_id,
            "matched-reference-binding",
            "reference_voxel",
        )
        other_prepared = _prepared(_endpoint_input(other_endpoint))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            seed_request = provider.activation_runtime_request(
                final,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
                workers=2,
                allow_expensive_producers=True,
            )
            OSSActivationProvider(
                cache,
                producer_toolchain=_ActivationToolchain(subject_ids),
            ).materialize(
                seed_request,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
            )
            request = self._activation_execution_request(
                root=root,
                cache=cache,
                provider=provider,
                endpoint_input=endpoint_input,
                prepared=prepared,
                selection=selection,
                allow_expensive_producers=False,
            )
            request = dataclasses.replace(
                request,
                dependencies={
                    **request.dependencies,
                    "matched_reference_prepared": DependencyState(
                        "completed",
                        "none",
                        other_prepared,
                    ),
                },
            )
            activation_request = service_adapters._activation_fitting_request(
                request
            )

        self.assertEqual(activation_request.final_model, final)
        self.assertEqual(activation_request.feature_axis, feature_axis)
        self.assertEqual(provider.fitting_calls, 1)

    def test_ppam_services_reuse_one_observed_workspace_and_aggregate_blocks(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=_ActivationToolchain(subject_ids),
        )
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            seed_toolchain = _ActivationToolchain(subject_ids)
            seed_request = provider.activation_runtime_request(
                final,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
                workers=2,
                allow_expensive_producers=True,
            )
            OSSActivationProvider(
                cache,
                producer_toolchain=seed_toolchain,
            ).materialize(
                seed_request,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
            )
            observed_task = _task(
                endpoint_input.endpoint,
                service_id="prepare_ppam_observed_workspace",
                stage="ppam_observed_workspace",
                output_type="PPAMObservedWorkspaceRecord",
                dependencies=("input", "prepared", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            observed_result = registry.resolve(observed_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=observed_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "input": DependencyState(
                            "completed",
                            "none",
                            endpoint_input,
                        ),
                        "prepared": DependencyState(
                            "completed",
                            "none",
                            prepared,
                        ),
                        "final": DependencyState("completed", "none", selection),
                    },
                )
            )
            observed_record = observed_result.decode_record()
            self.assertIsInstance(observed_record, PPAMObservedWorkspaceRecord)
            self.assertEqual(observed_record.technical_status, "permutation_ready")
            self.assertTrue(observed_result.fact_values["ppam_permutation_ready"])

            schedule_task = _task(
                endpoint_input.endpoint,
                service_id="prepare_ppam_permutation_schedule",
                stage="ppam_permutation_schedule",
                output_type="ResamplingScheduleRecord",
                dependencies=("workspace", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            schedule_result = registry.resolve(schedule_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=schedule_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "workspace": DependencyState(
                            "completed",
                            "none",
                            observed_record,
                        ),
                        "final": DependencyState("completed", "none", selection),
                    },
                )
            )
            schedule_record = schedule_result.decode_record()
            self.assertIsInstance(schedule_record, ResamplingScheduleRecord)

            block_task = _task(
                endpoint_input.endpoint,
                service_id="run_ppam_permutation_block",
                stage="ppam_permutation_block_0000",
                output_type="PPAMPermutationBlockRecord",
                dependencies=("workspace", "final", "schedule"),
                connectome_role="formal",
                phase="sensitivity",
                execution_parameters=(("block_index", "0"),),
            )
            with patch(
                "dual_frequency.backends.activation.fitting._weight_operators",
                side_effect=AssertionError("block rebuilt pPAM operators"),
            ):
                block_result = registry.resolve(block_task.service_id)(
                    self._ppam_execution_request(
                        root=root,
                        task=block_task,
                        provider=provider,
                        cache=cache,
                        dependencies={
                            "workspace": DependencyState(
                                "completed",
                                "none",
                                observed_record,
                            ),
                            "final": DependencyState(
                                "completed",
                                "none",
                                selection,
                            ),
                            "schedule": DependencyState(
                                "completed",
                                "none",
                                schedule_record,
                            ),
                        },
                    )
                )
            block_record = block_result.decode_record()
            self.assertIsInstance(block_record, PPAMPermutationBlockRecord)

            aggregate_task = _task(
                endpoint_input.endpoint,
                service_id="aggregate_ppam_activation",
                stage="activation_sensitivity",
                output_type="ActivationArtifact",
                dependencies=("workspace", "final", "schedule", "block"),
                connectome_role="formal",
                phase="sensitivity",
            )
            aggregate_result = registry.resolve(aggregate_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=aggregate_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "workspace": DependencyState(
                            "completed",
                            "none",
                            observed_record,
                        ),
                        "final": DependencyState("completed", "none", selection),
                        "schedule": DependencyState(
                            "completed",
                            "none",
                            schedule_record,
                        ),
                        "block": DependencyState(
                            "completed",
                            "none",
                            block_record,
                        ),
                    },
                )
            )
            activation = aggregate_result.decode_record()
            status_ref = next(
                item
                for item in activation.artifacts
                if item.kind == "oss_sensitivity_status"
            )
            status = ArtifactStore((root,)).materialize_document(
                status_ref,
                expected_kind="oss_sensitivity_status",
            )
            legacy = PPAMActivationBackend(
                RunScopedArtifactPublisher(
                    root / "legacy",
                    "legacy_ppam_activation",
                    "1",
                ),
                artifact_store=ArtifactStore((root,)),
            ).run_activation(
                activation_request_from_ppam_workspace(
                    observed_record,
                    final,
                )
            )

        self.assertIsInstance(activation, ActivationArtifact)
        self.assertTrue(aggregate_result.fact_values["activation_complete"])
        self.assertEqual(status["status"], "completed")
        self.assertEqual(provider.fitting_calls, 1)
        self.assertEqual(provider.toolchain.calls, [])
        self.assertEqual(provider.toolchain_resolution_calls, 0)
        self.assertEqual(len(seed_toolchain.calls), len(subject_ids) * 2)
        self.assertEqual(
            tuple(item.kind for item in activation.artifacts),
            tuple(item.kind for item in legacy.artifacts),
        )
        self.assertEqual(
            {item.kind: item.sha256 for item in activation.artifacts},
            {item.kind: item.sha256 for item in legacy.artifacts},
        )
        self.assertEqual(
            activation.activation_probability.sha256,
            legacy.activation_probability.sha256,
        )
        self.assertEqual(
            activation.binary_exposure.sha256,
            legacy.binary_exposure.sha256,
        )

    def test_ppam_degenerate_observed_state_aggregates_without_null_tasks(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=_ActivationToolchain(subject_ids),
        )
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            seed_toolchain = _ZeroActivationToolchain(subject_ids)
            runtime_request = provider.activation_runtime_request(
                final,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
                workers=2,
                allow_expensive_producers=True,
            )
            OSSActivationProvider(
                cache,
                producer_toolchain=seed_toolchain,
            ).materialize(
                runtime_request,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
            )
            observed_task = _task(
                endpoint_input.endpoint,
                service_id="prepare_ppam_observed_workspace",
                stage="ppam_observed_workspace_degenerate",
                output_type="PPAMObservedWorkspaceRecord",
                dependencies=("input", "prepared", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            observed_result = registry.resolve(observed_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=observed_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "input": DependencyState(
                            "completed",
                            "none",
                            endpoint_input,
                        ),
                        "prepared": DependencyState(
                            "completed",
                            "none",
                            prepared,
                        ),
                        "final": DependencyState("completed", "none", selection),
                    },
                )
            )
            observed_record = observed_result.decode_record()
            self.assertEqual(
                observed_record.technical_status,
                "observed_not_permutation_ready",
            )
            self.assertFalse(observed_result.fact_values["ppam_permutation_ready"])
            aggregate_task = _task(
                endpoint_input.endpoint,
                service_id="aggregate_ppam_activation",
                stage="activation_sensitivity_degenerate",
                output_type="ActivationArtifact",
                dependencies=("workspace", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            aggregate_result = registry.resolve(aggregate_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=aggregate_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "workspace": DependencyState(
                            "completed",
                            "none",
                            observed_record,
                        ),
                        "final": DependencyState("completed", "none", selection),
                    },
                )
            )
            activation = aggregate_result.decode_record()
            null_ref = next(
                item
                for item in activation.artifacts
                if item.kind == "oss_permutation_null_statistics"
            )
            store = ArtifactStore((root,))
            null = store.materialize(
                null_ref,
                expected_dtype=null_ref.dtype,
                expected_shape=null_ref.shape,
                expected_axes=null_ref.axis_refs,
                expected_units=null_ref.units,
                expected_space=null_ref.space,
            )
            status_ref = next(
                item
                for item in activation.artifacts
                if item.kind == "oss_sensitivity_status"
            )
            status = store.materialize_document(
                status_ref,
                expected_kind="oss_sensitivity_status",
            )

        self.assertTrue(np.all(np.isnan(null)))
        self.assertEqual(status["oss_sensitivity_status"], "failed_activation_degenerate")
        self.assertEqual(provider.fitting_calls, 1)
        self.assertEqual(provider.toolchain.calls, [])

    def test_ppam_nuisance_failure_aggregates_without_schedule_or_scratch(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=_ActivationToolchain(subject_ids),
        )
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = ContentAddressedCache(root / "cache")
            seed_toolchain = _ActivationToolchain(subject_ids)
            runtime_request = provider.activation_runtime_request(
                final,
                endpoint_input,
                prepared,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
                workers=2,
                allow_expensive_producers=True,
            )
            OSSActivationProvider(
                cache,
                producer_toolchain=seed_toolchain,
            ).materialize(
                runtime_request,
                RunScopedArtifactPublisher(root / "seed", "seed", "1"),
            )
            observed_task = _task(
                endpoint_input.endpoint,
                service_id="prepare_ppam_observed_workspace",
                stage="ppam_observed_workspace_nuisance_failure",
                output_type="PPAMObservedWorkspaceRecord",
                dependencies=("input", "prepared", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            with patch(
                "dual_frequency.runtime.service_adapters.prepare_ppam_fit_workspace",
                side_effect=NuisancePlanError(
                    "invalid_nuisance_design",
                    "synthetic rank deficiency",
                ),
            ):
                observed_result = registry.resolve(observed_task.service_id)(
                    self._ppam_execution_request(
                        root=root,
                        task=observed_task,
                        provider=provider,
                        cache=cache,
                        dependencies={
                            "input": DependencyState(
                                "completed",
                                "none",
                                endpoint_input,
                            ),
                            "prepared": DependencyState(
                                "completed",
                                "none",
                                prepared,
                            ),
                            "final": DependencyState(
                                "completed",
                                "none",
                                selection,
                            ),
                        },
                    )
                )
            observed_record = observed_result.decode_record()
            self.assertEqual(
                observed_record.technical_status,
                "nuisance_not_estimable",
            )
            self.assertFalse(observed_result.fact_values["ppam_permutation_ready"])
            self.assertIsNone(observed_record.generation_path)
            self.assertFalse(observed_record.arrays)

            aggregate_task = _task(
                endpoint_input.endpoint,
                service_id="aggregate_ppam_activation",
                stage="activation_sensitivity_nuisance_failure",
                output_type="ActivationArtifact",
                dependencies=("workspace", "final"),
                connectome_role="formal",
                phase="sensitivity",
            )
            aggregate_result = registry.resolve(aggregate_task.service_id)(
                self._ppam_execution_request(
                    root=root,
                    task=aggregate_task,
                    provider=provider,
                    cache=cache,
                    dependencies={
                        "workspace": DependencyState(
                            "completed",
                            "none",
                            observed_record,
                        ),
                        "final": DependencyState(
                            "completed",
                            "none",
                            selection,
                        ),
                    },
                )
            )
            activation = aggregate_result.decode_record()
            self.assertEqual(len(activation.artifacts), 1)
            status = ArtifactStore((root,)).materialize_document(
                activation.artifacts[0],
                expected_kind="oss_sensitivity_status",
            )

        self.assertEqual(
            status["oss_sensitivity_status"],
            "failed_oss_design_or_prediction",
        )
        self.assertEqual(status["failure_reasons"], ["invalid_nuisance_design"])
        self.assertEqual(provider.fitting_calls, 1)
        self.assertEqual(provider.toolchain.calls, [])

    def test_activation_authorized_cache_miss_materializes_rows_before_fitting(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        toolchain = _ActivationToolchain(subject_ids)
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=toolchain,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._activation_execution_request(
                root=root,
                cache=ContentAddressedCache(root / "cache"),
                provider=provider,
                endpoint_input=endpoint_input,
                prepared=prepared,
                selection=selection,
                allow_expensive_producers=True,
            )
            result = build_default_registry().resolve(
                "run_reference_fiber_activation"
            )(request)
            record = result.decode_record()

        self.assertEqual(len(toolchain.calls), len(subject_ids) * 2)
        self.assertEqual(provider.toolchain_resolution_calls, 1)
        self.assertEqual(provider.fitting_calls, 1)
        self.assertIsInstance(record, ActivationArtifact)
        self.assertEqual(record.final_model_id, final.identifier)
        self.assertEqual(record.feature_axis, feature_axis)

    def test_activation_unauthorized_cache_miss_fails_before_producer(
        self,
    ) -> None:
        (
            endpoint_input,
            prepared,
            final,
            selection,
            feature_axis,
            feature_ids,
            sources,
        ) = _activation_case()
        subject_ids = endpoint_input.included_subject_ids
        toolchain = _ActivationToolchain(subject_ids)
        provider = _ActivationProvider(
            final_model=final,
            subject_axis=endpoint_input.subject_axis,
            subject_ids=subject_ids,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            sources=sources,
            toolchain=toolchain,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = self._activation_execution_request(
                root=root,
                cache=ContentAddressedCache(root / "cache"),
                provider=provider,
                endpoint_input=endpoint_input,
                prepared=prepared,
                selection=selection,
                allow_expensive_producers=False,
            )
            with self.assertRaisesRegex(
                MissingAcceptanceFixture,
                "missing_acceptance_fixture",
            ):
                build_default_registry().resolve(
                    "run_reference_fiber_activation"
                )(request)

        self.assertEqual(toolchain.calls, [])
        self.assertEqual(provider.toolchain_resolution_calls, 0)
        self.assertEqual(provider.fitting_calls, 0)

    def test_missing_upstream_source_is_a_typed_dependency_state(self) -> None:
        reference_endpoint = EndpointKey(
            "study", "scale", "reference", "reference_voxel"
        )
        addon_endpoint = EndpointKey("study", "scale", "addon", "addon_voxel")
        endpoint_input = _endpoint_input(addon_endpoint)
        provider = _Provider(
            (
                _endpoint_record(reference_endpoint),
                _endpoint_record(
                    addon_endpoint,
                    matched=reference_endpoint.identifier,
                ),
            ),
            endpoint_input,
        )
        registry = build_default_registry()
        task = _task(
            addon_endpoint,
            service_id="bind_reference_dependency",
            stage="reference_dependency",
            output_type="ReferenceDependencyRecord",
            dependencies=("reference",),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = registry.resolve(task.service_id)(
                _request(
                    task,
                    provider,
                    Path(temporary),
                    {
                        "reference": DependencyState(
                            "skipped",
                            "not_run_endpoint_input_not_ready",
                            None,
                        )
                    },
                )
            )
        dependency = result.decode_record()
        self.assertEqual(dependency.dependency_status, "input_failure")
        self.assertIsNone(dependency.reference_record)
        self.assertFalse(result.fact_values["reference_dependency_ready"])

    def test_reference_final_closes_when_endpoint_input_is_not_ready(self) -> None:
        endpoint = EndpointKey("study", "scale", "reference", "reference_voxel")
        ready = _endpoint_input(endpoint)
        subject_axis = _axis("subjects-not-ready", 11, "4")
        not_ready = EndpointInputRecord(
            endpoint=endpoint,
            readiness_status="insufficient_subjects",
            candidate_subject_ids=ready.candidate_subject_ids,
            included_subject_ids=ready.included_subject_ids[:11],
            exclusions=(
                SubjectExclusionRecord(
                    ready.candidate_subject_ids[-1],
                    "missing_required_exposure",
                ),
            ),
            minimum_subjects=12,
            subject_axis=subject_axis,
            baseline=_artifact(
                "baseline-not-ready.npy",
                kind="endpoint_baseline",
                axes=(subject_axis,),
                dtype="float64",
                units="score",
            ),
            outcome=_artifact(
                "outcome-not-ready.npy",
                kind="endpoint_outcome",
                axes=(subject_axis,),
                dtype="float64",
                units="score",
            ),
        )
        provider = _Provider((_endpoint_record(endpoint),), not_ready)
        registry = build_default_registry()
        task = _task(
            endpoint,
            service_id="realize_reference_final",
            stage="final_realization",
            output_type="FinalSelectionRecord",
            dependencies=("input", "source"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = registry.resolve(task.service_id)(
                _request(
                    task,
                    provider,
                    Path(temporary),
                    {
                        "input": DependencyState("completed", "none", not_ready),
                        "source": DependencyState("skipped", "not_run", None),
                    },
                )
            )
        selection = result.decode_record()
        self.assertEqual(selection.selection_status, "no_final_model")
        self.assertIsNone(selection.final_model)
        self.assertFalse(result.fact_values["final_model_realized"])


if __name__ == "__main__":
    unittest.main()
