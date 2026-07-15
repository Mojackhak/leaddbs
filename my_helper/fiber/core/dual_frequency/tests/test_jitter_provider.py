"""Production-path spatial-jitter replicate-provider integration tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

import nibabel as nib
import numpy as np

from dual_frequency.backends.sensitivity import (
    FinalSensitivityTarget,
    SpatialJitterSettings,
)
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.catalog import build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides, load_workflow
from dual_frequency.contracts import (
    AxisRef,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    PreparedExposureRecord,
    ReferenceDependencyRecord,
    SourceRecord,
    SubjectRecord,
)
from dual_frequency.contracts.identity import canonical_hash
from dual_frequency.contracts.study_base import (
    ClinicalObservation,
    ComponentDefinition,
    ContactRecord,
    ElectrodeDefinition,
    ProgramRecord,
    ScaleDefinition,
    SpatialDefinition,
    StimulationSource,
    StudyBaseRecord,
    SubscaleDefinition,
)
from dual_frequency.runtime.input_provider import StudyRuntimeInputProvider
from dual_frequency.runtime.jitter_provider import StudyJitterReplicateProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
WORKFLOW_PATH = (
    REPOSITORY_ROOT
    / "my_helper"
    / "stnsnr"
    / "config"
    / "four_model_v1"
    / "workflow.yaml"
)
SCALE_ID = "mds_updrs_iii_score"


class _CopyTransformer:
    def transform(
        self,
        source: Path,
        destination: Path,
        configured_transform: Path,
    ) -> Path:
        if not source.is_file() or not configured_transform.is_file():
            raise AssertionError("test transformer received a missing input")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination


def _observation(subject_id: str, phase_id: str, program_id: int, value: int) -> ClinicalObservation:
    return ClinicalObservation(
        observation_id=f"obs:{subject_id}:{phase_id}:{program_id}:{SCALE_ID}",
        subject_id=subject_id,
        phase_id=phase_id,
        program_id=program_id,
        scale_id=SCALE_ID,
        subscale_id="total",
        value=value,
        status="observed",
    )


def _source(
    subject_id: str,
    phase_id: str,
    program_id: int,
    electrode_id: str,
    group_id: str,
    delivery_mode: str,
    frequency_hz: float,
) -> StimulationSource:
    return StimulationSource(
        subject_id=subject_id,
        phase_id=phase_id,
        program_id=program_id,
        electrode_id=electrode_id,
        frequency_group_id=group_id,
        delivery_mode=delivery_mode,
        source_id=f"{group_id}-source",
        source_label="Component",
        component_id="component",
        frequency_hz=frequency_hz,
        control_mode="voltage",
        amplitude=2.0,
        pulse_width_us=60.0,
        contacts=(ContactRecord("case", "anode", 1.0), ContactRecord(0, "cathode", 1.0)),
    )


def _leaf(
    subject_dir: Path,
    phase_id: str,
    program_id: int,
    electrode_id: str,
    group_id: str,
    delivery_mode: str,
) -> Path:
    root = (
        subject_dir
        / "stimulations"
        / "MNI152NLin2009bAsym"
        / f"phase-{phase_id}"
        / f"program-{program_id}"
        / f"electrode-{electrode_id}"
        / f"frequency-group-{group_id}"
    )
    if delivery_mode == "continuous":
        return root / "delivery-continuous" / "joint" / "efield.nii.gz"
    return root / "delivery-alternating" / "derived" / "group-peak" / "efield.nii.gz"


def _write_field(path: Path, value: float, affine: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(np.full((4, 4, 2), value, dtype=np.float32), affine),
        str(path),
    )


def _write_field_array(path: Path, value: np.ndarray, affine: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(np.asarray(value, dtype=np.float32), affine),
        str(path),
    )


def _materialize(store: ArtifactStore, artifact) -> np.ndarray:
    return store.materialize(
        artifact,
        expected_dtype=artifact.dtype,
        expected_shape=artifact.shape,
        expected_axes=artifact.axis_refs,
        expected_units=artifact.units,
        expected_space=artifact.space,
    )


def _program(
    subject_id: str,
    phase_id: str,
    program_id: int,
    sources: tuple[StimulationSource, ...],
    value: int,
) -> ProgramRecord:
    return ProgramRecord(
        subject_id=subject_id,
        phase_id=phase_id,
        phase_label=phase_id,
        program_id=program_id,
        program_label=f"Program {program_id}",
        condition_role="configured",
        stimulation_state="active" if sources else "none",
        assessment_order=program_id,
        duration_label="configured",
        stimulation_start_date=None,
        assessment_date=None,
        exposure_days=None,
        observations=(_observation(subject_id, phase_id, program_id, value),),
        stimulation_sources=sources,
    )


class StudyJitterReplicateProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.affine = np.eye(4, dtype=np.float64)
        self.brainmask = self.root / "brainmask.nii.gz"
        nib.save(
            nib.Nifti1Image(np.ones((4, 4, 2), dtype=np.uint8), self.affine),
            str(self.brainmask),
        )
        self.transform = self.root / "Composite.nii.gz"
        self.transform.write_bytes(b"synthetic-transform")
        self.configuration = load_workflow(
            WORKFLOW_PATH,
            WorkflowOverrides(
                scales=(SCALE_ID,),
                models=("reference_voxel", "addon_voxel"),
                through="observed",
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _study(
        self,
        *,
        missing_addon_subject_indices: tuple[int, ...] = (),
        missing_addon_reference_subject_indices: tuple[int, ...] = (),
        reference_value: float = 100.0,
        addon_reference_value: float = 250.0,
        addon_value: float = 80.0,
    ) -> StudyBaseRecord:
        missing_addon = set(missing_addon_subject_indices)
        missing_addon_reference = set(missing_addon_reference_subject_indices)
        subjects: list[SubjectRecord] = []
        for index in range(12):
            subject_id = f"participant-{index + 1:02d}"
            subject_dir = self.root / subject_id
            electrodes = (
                ElectrodeDefinition("lead-L", "L", "Synthetic", 4, 1),
                ElectrodeDefinition("lead-R", "R", "Synthetic", 4, 2),
            )
            reference_sources: list[StimulationSource] = []
            addon_sources: list[StimulationSource] = []
            for electrode_id in ("lead-L", "lead-R"):
                reference_source = _source(
                    subject_id,
                    "T2",
                    1,
                    electrode_id,
                    "reference-group",
                    "continuous",
                    130.0,
                )
                reference_sources.append(reference_source)
                _write_field(
                    _leaf(subject_dir, "T2", 1, electrode_id, "reference-group", "continuous"),
                    reference_value,
                    self.affine,
                )
                addon_reference = _source(
                    subject_id,
                    "T3",
                    2,
                    electrode_id,
                    "reference-group",
                    "continuous",
                    130.0,
                )
                if index not in missing_addon_reference:
                    addon_sources.append(addon_reference)
                    _write_field(
                        _leaf(
                            subject_dir,
                            "T3",
                            2,
                            electrode_id,
                            "reference-group",
                            "continuous",
                        ),
                        addon_reference_value,
                        self.affine,
                    )
                if index not in missing_addon:
                    delivery = "alternating" if index == 0 else "continuous"
                    addon_source = _source(
                        subject_id,
                        "T3",
                        2,
                        electrode_id,
                        "addon-group",
                        delivery,
                        30.0,
                    )
                    addon_sources.append(addon_source)
                    _write_field(
                        _leaf(subject_dir, "T3", 2, electrode_id, "addon-group", delivery),
                        addon_value,
                        self.affine,
                    )
            subjects.append(
                SubjectRecord(
                    subject_id=subject_id,
                    subject_label=subject_id,
                    leaddbs_subject_dir=subject_dir,
                    electrode_reconstruction=subject_dir / "reconstruction.mat",
                    electrodes=electrodes,
                    programs=(
                        _program(subject_id, "T0", 0, (), 40),
                        _program(subject_id, "T2", 1, tuple(reference_sources), 30),
                        _program(subject_id, "T3", 2, tuple(addon_sources), 20),
                    ),
                )
            )
        return StudyBaseRecord(
            schema_version="dual_frequency_study_v1",
            study_id="synthetic-study",
            study_label="Synthetic Study",
            data_version="1",
            components=(ComponentDefinition("component", "Component"),),
            scales=(
                ScaleDefinition(
                    SCALE_ID,
                    "Motor score",
                    "integer",
                    "score",
                    "lower",
                    (SubscaleDefinition("total", "Total"),),
                ),
            ),
            spatial=SpatialDefinition(
                canonical_space="MNI152NLin2009bAsym",
                canonical_hemisphere="R",
                left_to_right_transform=self.transform,
                brainmask_id="synthetic-mask",
                brainmask_path=self.brainmask,
                connectomes=(),
            ),
            subjects=tuple(subjects),
            source_path=self.root / "study_base.json",
            source_sha256="a" * 64,
        )

    def _provider(self, study: StudyBaseRecord):
        catalog = build_endpoint_catalog(self.configuration, study)
        artifact_root = self.root / "artifacts"
        artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_store = ArtifactStore((artifact_root,))
        provider = StudyRuntimeInputProvider(
            study,
            self.configuration,
            catalog,
            work_root=self.root / "provider-work",
            artifact_store=artifact_store,
            left_transformer=_CopyTransformer(),
        )
        return provider, catalog, artifact_store, artifact_root

    @staticmethod
    def _endpoint(catalog, family: str):
        return next(item for item in catalog if item.key.model_family == family)

    @staticmethod
    def _selected_axis(
        prepared: PreparedExposureRecord,
        indices: np.ndarray,
        *,
        tau: float,
        coverage: int,
        branch: str | None = None,
    ) -> AxisRef:
        payload: dict[str, object] = {
            "parent_axis_sha256": prepared.feature_axis.sha256,
            "selected_indices": indices.astype(np.int64).tolist(),
            "tau": tau,
            "coverage": coverage,
        }
        if branch is not None:
            payload["branch"] = branch
        return AxisRef(
            "selected-direct",
            int(indices.size),
            canonical_hash(payload),
        )

    def _reference_source(
        self,
        endpoint,
        reference_input,
        prepared: PreparedExposureRecord,
        artifact_root: Path,
        *,
        indices: np.ndarray,
        full_weights: np.ndarray,
        fold_weights: np.ndarray,
        tau: float = 200.0,
        coverage: int = 5,
    ) -> SourceRecord:
        selected_axis = self._selected_axis(
            prepared,
            np.asarray(indices, dtype=np.int64),
            tau=tau,
            coverage=coverage,
        )
        publisher = RunScopedArtifactPublisher(
            artifact_root / f"reference-source-{endpoint.endpoint_id}",
            f"reference-source-{endpoint.endpoint_id}",
            "1",
        )
        index_artifact = publisher.array(
            "selected_feature_indices.npy",
            np.asarray(indices, dtype=np.int64),
            kind="selected_feature_indices",
            axes=(selected_axis,),
            units=None,
            space=None,
        )
        full_artifact = publisher.array(
            "full_weights.npy",
            np.asarray(full_weights, dtype=np.float64),
            kind="benefit_oriented_feature_weights",
            axes=(selected_axis,),
            units="coefficient",
            space=None,
        )
        assert reference_input.subject_axis is not None
        fold_artifact = publisher.array(
            "fold_weights.npy",
            np.asarray(fold_weights, dtype=np.float64),
            kind="loocv_benefit_oriented_feature_weights",
            axes=(reference_input.subject_axis, selected_axis),
            units="coefficient",
            space=None,
        )
        return SourceRecord(
            endpoint=endpoint.key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=tau,
            selected_coverage=coverage,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(
                selected_axis,
                "selected_direct_voxel_feature_union",
            ),
            artifacts=(index_artifact, full_artifact, fold_artifact),
        )

    def _direct_final(
        self,
        endpoint,
        prepared: PreparedExposureRecord,
        artifact_root: Path,
        indices: np.ndarray,
        *,
        branch: str,
        tau: float = 200.0,
        coverage: int = 5,
    ) -> FinalModelRecord:
        selected_axis = self._selected_axis(
            prepared,
            np.asarray(indices, dtype=np.int64),
            tau=tau,
            coverage=coverage,
            branch=branch if endpoint.key.model_family.startswith("addon_") else None,
        )
        publisher = RunScopedArtifactPublisher(
            artifact_root / f"final-{endpoint.endpoint_id}-{branch}",
            f"final-{endpoint.endpoint_id}-{branch}",
            "1",
        )
        index_artifact = publisher.array(
            "selected_feature_indices.npy",
            np.asarray(indices, dtype=np.int64),
            kind="selected_feature_indices",
            axes=(selected_axis,),
            units="index",
            space=None,
        )
        identity_source = (
            "selected_addon_direct_voxel_feature_union"
            if endpoint.key.model_family.startswith("addon_")
            else "selected_direct_voxel_feature_union"
        )
        source = SourceRecord(
            endpoint=endpoint.key,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=tau,
            selected_coverage=coverage,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(selected_axis, identity_source),
            artifacts=(index_artifact,),
        )
        selected_branch = None
        selected_source = source
        if endpoint.key.model_family.startswith("addon_"):
            selected_branch = BranchRecord(
                endpoint=endpoint.key,
                branch=branch,
                intended_role="primary",
                input_status="valid",
                nuisance_design_status="valid",
                source=source,
            )
            selected_source = None
        return FinalModelRecord(
            endpoint=endpoint.key,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                endpoint.endpoint_id,
                branch,
                tau,
                coverage,
                "loocv_linear",
            ),
            selected_source=selected_source,
            selected_branch=selected_branch,
        )

    @staticmethod
    def _dependency(reference_endpoint, addon_endpoint, source: SourceRecord) -> ReferenceDependencyRecord:
        return ReferenceDependencyRecord(
            addon_endpoint=addon_endpoint.key,
            matched_reference_endpoint_id=reference_endpoint.endpoint_id,
            dependency_status="ready",
            reference_record=source,
            delta_reference=None,
        )

    @staticmethod
    def _valid_delta(subject_axis: AxisRef, artifact_root: Path) -> DeltaReferenceBundle:
        publisher = RunScopedArtifactPublisher(
            artifact_root / f"delta-{subject_axis.count}",
            f"delta-{subject_axis.count}",
            "1",
        )
        full = publisher.array(
            "full.npy",
            np.linspace(-1.0, 1.0, subject_axis.count, dtype=np.float64),
            kind="delta_reference_full_scores",
            axes=(subject_axis,),
            units="V/m",
            space=None,
        )
        folds = publisher.array(
            "folds.npy",
            np.tile(
                np.linspace(-1.0, 1.0, subject_axis.count, dtype=np.float64),
                (subject_axis.count, 1),
            ),
            kind="delta_reference_fold_scores",
            axes=(subject_axis, subject_axis),
            units="V/m",
            space=None,
        )
        support_rows = publisher.array(
            "support.npy",
            np.ones((subject_axis.count, 4), dtype=np.float64),
            kind="delta_reference_support_rows",
            axes=(
                subject_axis,
                AxisRef(
                    "support-fields",
                    4,
                    canonical_hash({"subject_axis_sha256": subject_axis.sha256, "count": 4}),
                ),
            ),
            units=None,
            space=None,
        )
        support_qc = publisher.document(
            "support_qc.json",
            {"schema_version": "synthetic_delta_support_v1"},
            kind="delta_reference_support_qc",
        )
        return DeltaReferenceBundle(
            input_status="valid",
            support_status="adequate",
            selected_reference_tau=200.0,
            selected_reference_coverage=5,
            full_scores=full,
            fold_scores=folds,
            support_rows=support_rows,
            support_qc=support_qc,
        )

    def _target(
        self,
        provider: StudyRuntimeInputProvider,
        endpoint_input,
        prepared: PreparedExposureRecord,
        final_model: FinalModelRecord,
        artifact_root: Path,
        *,
        branch: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> FinalSensitivityTarget:
        base = provider.observed_request(
            endpoint_input,
            prepared,
            branch=branch,
            delta_reference=delta_reference,
        )
        selected_exposure, _ = provider.selected_exposure(
            final_model,
            prepared,
            RunScopedArtifactPublisher(
                artifact_root / f"target-{final_model.endpoint.identifier}-{branch}",
                f"target-{final_model.endpoint.identifier}-{branch}",
                "1",
            ),
        )
        return FinalSensitivityTarget(
            final_model=final_model,
            observed_request=replace(
                base,
                exposure=selected_exposure,
                feature_axis=final_model.valid_feature_axis.axis,
            ),
        )

    def test_reference_replicate_uses_locked_selected_axis_and_deterministic_translation(self) -> None:
        study = self._study()
        for subject_index in range(12):
            subject_dir = self.root / f"participant-{subject_index + 1:02d}"
            for electrode_id, side_shift in (("lead-L", -0.5), ("lead-R", 0.5)):
                gradient = (
                    100.0
                    + 5.0 * np.indices((4, 4, 2), dtype=np.float32)[0]
                    + side_shift
                )
                _write_field_array(
                    _leaf(subject_dir, "T2", 1, electrode_id, "reference-group", "continuous"),
                    gradient,
                    self.affine,
                )
        provider, catalog, store, artifact_root = self._provider(study)
        endpoint = self._endpoint(catalog, "reference_voxel")
        endpoint_input = provider.publish_endpoint_input(
            endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "reference-input",
                "reference-input",
                "1",
            ),
        )
        prepared = provider.publish_prepared_exposure(
            endpoint_input,
            None,
            RunScopedArtifactPublisher(
                artifact_root / "reference-prepared",
                "reference-prepared",
                "1",
            ),
        )
        final_model = self._direct_final(
            endpoint,
            prepared,
            artifact_root,
            np.asarray([0, 7, 15], dtype=np.int64),
            branch="reference",
        )
        target = self._target(
            provider,
            endpoint_input,
            prepared,
            final_model,
            artifact_root,
            branch="reference",
        )
        settings = SpatialJitterSettings(2, 17, 2.354820045)
        replicate_provider = StudyJitterReplicateProvider(
            provider=provider,
            endpoint_input=endpoint_input,
            reference_input=None,
            reference_dependency=None,
            final_model=final_model,
            original_delta=None,
            publisher=RunScopedArtifactPublisher(
                artifact_root / "reference-jitter",
                "reference-jitter",
                "1",
            ),
            artifact_store=store,
            settings=settings,
        )

        first = replicate_provider.build_replicate(
            target,
            replicate_index=1,
            replicate_seed=23,
        )
        second = replicate_provider.build_replicate(
            target,
            replicate_index=1,
            replicate_seed=23,
        )

        self.assertEqual(first.rebuild_identity, second.rebuild_identity)
        self.assertEqual(first.observed_request.feature_axis, final_model.valid_feature_axis.axis)
        self.assertEqual(
            first.observed_request.exposure.axis_refs,
            (endpoint_input.subject_axis, final_model.valid_feature_axis.axis),
        )
        np.testing.assert_allclose(
            _materialize(store, first.observed_request.exposure),
            _materialize(store, second.observed_request.exposure),
        )
        self.assertFalse(
            np.allclose(
                _materialize(store, first.observed_request.exposure),
                _materialize(store, target.observed_request.exposure),
            )
        )

    def test_addon_no_delta_replicate_remains_evaluable_without_usable_delta_support(self) -> None:
        cases = (
            {
                "label": "not_applicable",
                "study": self._study(
                    missing_addon_reference_subject_indices=(11,),
                ),
                "expected_status": "not_applicable",
                "expected_reason": "missing_addon_reference_component_exposure",
            },
            {
                "label": "invalid_support",
                "study": self._study(addon_reference_value=150.0),
                "expected_status": "invalid_no_reference_component_coverage",
                "expected_reason": None,
            },
        )
        for case in cases:
            with self.subTest(case=case["label"]):
                provider, catalog, store, artifact_root = self._provider(case["study"])
                reference_endpoint = self._endpoint(catalog, "reference_voxel")
                addon_endpoint = self._endpoint(catalog, "addon_voxel")
                reference_input = provider.publish_endpoint_input(
                    reference_endpoint.endpoint_id,
                    RunScopedArtifactPublisher(
                        artifact_root / f"{case['label']}-reference-input",
                        f"{case['label']}-reference-input",
                        "1",
                    ),
                )
                reference_prepared = provider.publish_prepared_exposure(
                    reference_input,
                    None,
                    RunScopedArtifactPublisher(
                        artifact_root / f"{case['label']}-reference-prepared",
                        f"{case['label']}-reference-prepared",
                        "1",
                    ),
                )
                addon_input = provider.publish_endpoint_input(
                    addon_endpoint.endpoint_id,
                    RunScopedArtifactPublisher(
                        artifact_root / f"{case['label']}-addon-input",
                        f"{case['label']}-addon-input",
                        "1",
                    ),
                )
                if (
                    case["label"] == "invalid_support"
                    and addon_input.readiness_status != "ready"
                ):
                    addon_input = replace(
                        addon_input,
                        readiness_status="ready",
                        minimum_subjects=len(addon_input.included_subject_ids),
                    )
                dependency_source = self._reference_source(
                    reference_endpoint,
                    reference_input,
                    reference_prepared,
                    artifact_root,
                    indices=np.asarray([0, 1, 2], dtype=np.int64),
                    full_weights=np.ones(3, dtype=np.float64),
                    fold_weights=np.ones((reference_input.subject_axis.count, 3), dtype=np.float64),
                )
                dependency = self._dependency(
                    reference_endpoint,
                    addon_endpoint,
                    dependency_source,
                )
                prepared = provider.publish_prepared_exposure(
                    addon_input,
                    dependency,
                    RunScopedArtifactPublisher(
                        artifact_root / f"{case['label']}-addon-prepared",
                        f"{case['label']}-addon-prepared",
                        "1",
                    ),
                )
                final_model = self._direct_final(
                    addon_endpoint,
                    prepared,
                    artifact_root,
                    np.asarray([0, 1, 2], dtype=np.int64),
                    branch="no_delta_reference",
                )
                target = self._target(
                    provider,
                    addon_input,
                    prepared,
                    final_model,
                    artifact_root,
                    branch="no_delta_reference",
                )
                replicate_provider = StudyJitterReplicateProvider(
                    provider=provider,
                    endpoint_input=addon_input,
                    reference_input=reference_input,
                    reference_dependency=dependency,
                    final_model=final_model,
                    original_delta=None,
                    publisher=RunScopedArtifactPublisher(
                        artifact_root / f"{case['label']}-jitter",
                        f"{case['label']}-jitter",
                        "1",
                    ),
                    artifact_store=store,
                    settings=SpatialJitterSettings(1, 5, 2.354820045),
                )

                evidence = replicate_provider.build_replicate(
                    target,
                    replicate_index=0,
                    replicate_seed=31,
                )

                self.assertEqual(evidence.support_status, case["expected_status"])
                self.assertEqual(evidence.delta_rebuild_identity, None)
                self.assertEqual(evidence.observed_request.branch, "no_delta_reference")
                self.assertEqual(evidence.observed_request.nuisance_inputs, ())
                self.assertEqual(
                    evidence.observed_request.feature_axis,
                    final_model.valid_feature_axis.axis,
                )
                self.assertTrue(np.all(np.isfinite(_materialize(store, evidence.observed_request.exposure))))
                if case["expected_reason"] is not None:
                    qc = dict(evidence.support_qc)
                    self.assertEqual(qc["delta_reason_code"], case["expected_reason"])

    def test_adjusted_addon_replicate_preserves_subject_identity_with_larger_reference_cohort(self) -> None:
        study = self._study(
            missing_addon_subject_indices=(5,),
            addon_reference_value=500.0,
        )
        provider, catalog, store, artifact_root = self._provider(study)
        reference_endpoint = self._endpoint(catalog, "reference_voxel")
        addon_endpoint = self._endpoint(catalog, "addon_voxel")
        reference_input = provider.publish_endpoint_input(
            reference_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "aligned-reference-input",
                "aligned-reference-input",
                "1",
            ),
        )
        reference_prepared = provider.publish_prepared_exposure(
            reference_input,
            None,
            RunScopedArtifactPublisher(
                artifact_root / "aligned-reference-prepared",
                "aligned-reference-prepared",
                "1",
            ),
        )
        addon_input = provider.publish_endpoint_input(
            addon_endpoint.endpoint_id,
            RunScopedArtifactPublisher(
                artifact_root / "aligned-addon-input",
                "aligned-addon-input",
                "1",
            ),
        )
        addon_input = replace(
            addon_input,
            readiness_status="ready",
            minimum_subjects=len(addon_input.included_subject_ids),
        )
        self.assertGreater(reference_input.subject_axis.count, addon_input.subject_axis.count)
        selected_indices = np.arange(reference_prepared.feature_axis.count, dtype=np.int64)
        fold_weights = np.vstack(
            [
                np.full(selected_indices.size, float(index + 1), dtype=np.float64)
                for index in range(reference_input.subject_axis.count)
            ]
        )
        dependency_source = self._reference_source(
            reference_endpoint,
            reference_input,
            reference_prepared,
            artifact_root,
            indices=selected_indices,
            full_weights=np.ones(selected_indices.size, dtype=np.float64),
            fold_weights=fold_weights,
        )
        dependency = self._dependency(reference_endpoint, addon_endpoint, dependency_source)
        prepared = provider.publish_prepared_exposure(
            addon_input,
            dependency,
            RunScopedArtifactPublisher(
                artifact_root / "aligned-addon-prepared",
                "aligned-addon-prepared",
                "1",
            ),
        )
        final_model = self._direct_final(
            addon_endpoint,
            prepared,
            artifact_root,
            selected_indices,
            branch="delta_reference_adjusted",
        )
        original_delta = self._valid_delta(addon_input.subject_axis, artifact_root)
        target = self._target(
            provider,
            addon_input,
            prepared,
            final_model,
            artifact_root,
            branch="delta_reference_adjusted",
            delta_reference=original_delta,
        )
        replicate_provider = StudyJitterReplicateProvider(
            provider=provider,
            endpoint_input=addon_input,
            reference_input=reference_input,
            reference_dependency=dependency,
            final_model=final_model,
            original_delta=original_delta,
            publisher=RunScopedArtifactPublisher(
                artifact_root / "aligned-jitter",
                "aligned-jitter",
                "1",
            ),
            artifact_store=store,
            settings=SpatialJitterSettings(1, 9, 0.01),
        )

        evidence = replicate_provider.build_replicate(
            target,
            replicate_index=0,
            replicate_seed=41,
        )

        self.assertEqual(evidence.support_status, "adequate")
        self.assertIsNotNone(evidence.delta_rebuild_identity)
        self.assertEqual(len(evidence.observed_request.nuisance_inputs), 2)
        full_scores = _materialize(store, evidence.observed_request.nuisance_inputs[0])
        fold_scores = _materialize(store, evidence.observed_request.nuisance_inputs[1])
        expected_subject_ids = addon_input.included_subject_ids
        self.assertEqual(
            expected_subject_ids,
            (
                "participant-01",
                "participant-02",
                "participant-03",
                "participant-04",
                "participant-05",
                "participant-07",
                "participant-08",
                "participant-09",
                "participant-10",
                "participant-11",
                "participant-12",
            ),
        )
        expected_factors = np.asarray((1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12), dtype=np.float64)
        np.testing.assert_allclose(
            fold_scores,
            expected_factors[:, None] * full_scores[None, :],
        )


if __name__ == "__main__":
    unittest.main()
