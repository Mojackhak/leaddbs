"""Strict typed persistence tests for dual-frequency scientific records."""

from __future__ import annotations

import copy
import dataclasses
import json
import unittest

from dual_frequency.contracts import (
    ActivationArtifact,
    ArtifactRef,
    AxisRef,
    BranchRecord,
    DeltaReferenceBundle,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalDecisionRecord,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    FormalOperatorScratchRecord,
    FormalResult,
    ObservedResult,
    PreparedExposureRecord,
    RecordError,
    ReferenceDependencyRecord,
    RESAMPLING_REPLICATE_BLOCK_SIZE,
    ResamplingBlockRecord,
    ResamplingScheduleRecord,
    ScratchArrayRecord,
    SensitiveRecord,
    SensitivityResult,
    SourceRecord,
    SubjectExclusionRecord,
    resampling_block_axis,
)
from dual_frequency.runtime import (
    RecordCodecError,
    decode_record,
    encode_record,
    record_artifacts,
    record_identifier,
)


class RecordCodecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.subjects = AxisRef("subjects", 2, "a" * 64)
        self.features = AxisRef("voxels", 3, "b" * 64)
        self.reference_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_voxel",
        )
        self.addon_endpoint = EndpointKey(
            "study",
            "scale",
            "addon",
            "addon_voxel",
        )

        self.baseline = self._artifact("baseline", (self.subjects,), digest="1")
        self.outcome = self._artifact("outcome", (self.subjects,), digest="2")
        self.exposure = self._artifact(
            "prepared_exposure",
            (self.subjects, self.features),
            digest="3",
            units="V/m",
        )
        self.weights = self._artifact(
            "feature_weights",
            (self.features,),
            digest="4",
            units="coefficient",
        )
        self.feature_ids = self._artifact(
            "canonical_feature_ids",
            (self.features,),
            digest="0",
            units="feature_id",
            dtype="int64",
        )
        self.source = SourceRecord(
            endpoint=self.reference_endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_predictive",
            threshold_source="pre_specified",
            selected_tau=200,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(self.features, "canonical_brainmask"),
            artifacts=(self.weights,),
        )
        self.branch_source = dataclasses.replace(
            self.source,
            endpoint=self.addon_endpoint,
        )
        self.branch = BranchRecord(
            endpoint=self.addon_endpoint,
            branch="no_delta_reference",
            intended_role="primary",
            input_status="valid",
            nuisance_design_status="valid",
            source=self.branch_source,
            artifacts=(self.exposure,),
        )
        self.final = FinalModelRecord(
            endpoint=self.addon_endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                self.addon_endpoint.identifier,
                "no_delta_reference",
                200,
                5,
                "loocv_weighted_map",
            ),
            selected_source=None,
            selected_branch=self.branch,
            artifacts=(self.exposure,),
        )

    def _artifact(
        self,
        kind: str,
        axes: tuple[AxisRef, ...],
        *,
        digest: str,
        units: str = "score",
        dtype: str = "float64",
    ) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            schema_version="array_v1",
            uri=f"file:///tmp/{kind}.npy",
            sha256=digest * 64,
            dtype=dtype,
            shape=tuple(axis.count for axis in axes),
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space="synthetic",
            producer_id="record_codec_test",
            producer_version="1",
        )

    @staticmethod
    def _document(kind: str, *, digest: str) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            schema_version="document_v1",
            uri=f"file:///tmp/{kind}.json",
            sha256=digest * 64,
            dtype=None,
            shape=None,
            axis_refs=(),
            axis_hashes=(),
            units=None,
            space=None,
            producer_id="record_codec_test",
            producer_version="1",
        )

    def _round_trip(self, record: object) -> object:
        payload = encode_record(record)
        json.dumps(payload, allow_nan=False)
        return decode_record(
            type(record).__name__,
            payload,
            record_id=record_identifier(record),
            artifacts=record_artifacts(record),
        )

    def _resampling_records(
        self,
    ) -> tuple[ResamplingScheduleRecord, ResamplingBlockRecord]:
        replicates = AxisRef("formal_permutation_replicates", 500, "e" * 64)
        schedule_artifact = self._artifact(
            "formal_resampling_schedule",
            (replicates, self.subjects),
            digest="f",
            units="subject_index",
            dtype="int32",
        )
        schedule = ResamplingScheduleRecord(
            target_id=self.final.identifier,
            resampling_kind="permutation",
            subject_axis=self.subjects,
            replicate_axis=replicates,
            seed=42,
            replicate_count=replicates.count,
            block_size=RESAMPLING_REPLICATE_BLOCK_SIZE,
            schedule_schema="dual_frequency_resampling_schedule_v1",
            generator_class="numpy.random._generator.Generator",
            bit_generator_class="numpy.random._pcg64.PCG64",
            numpy_version="2.4.6",
            environment_fingerprint="8" * 64,
            schedule_sha256="9" * 64,
            schedule=schedule_artifact,
        )
        block_axis = resampling_block_axis(replicates, 250, 500)
        null = self._artifact(
            "formal_permutation_null_statistics_block",
            (block_axis,),
            digest="a",
            units="spearman_rho",
        )
        block = ResamplingBlockRecord(
            target_id=self.final.identifier,
            resampling_kind="permutation",
            schedule_id=schedule.identifier,
            replicate_axis=replicates,
            block_axis=block_axis,
            block_index=1,
            start=250,
            stop=500,
            total=500,
            schedule_sha256=schedule.schedule_sha256,
            technical_status="completed",
            artifacts=(null,),
        )
        return schedule, block

    def _operator_scratch_record(self) -> FormalOperatorScratchRecord:
        array = ScratchArrayRecord(
            name="score_operator",
            filename="00_score_operator.npy",
            dtype="float64",
            shape=(2, 2),
            fortran_order=False,
            nbytes=32,
        )
        return FormalOperatorScratchRecord(
            target_id=self.final.identifier,
            model_family="direct_voxel",
            subject_axis=self.subjects,
            feature_axis=self.features,
            input_identity="7" * 64,
            operator_schema="dual_frequency_formal_operator_scratch_v1",
            technical_status="completed",
            generation_path=(
                "work/task_fixture/operator-generation-0123456789abcdef"
            ),
            arrays=(array,),
            total_nbytes=array.nbytes,
        )

    def test_operator_scratch_record_is_path_safe_and_has_no_artifact_closure(self) -> None:
        record = self._operator_scratch_record()
        self.assertEqual(self._round_trip(record), record)
        self.assertEqual(record_artifacts(record), ())
        with self.assertRaisesRegex(RecordError, "generation path"):
            dataclasses.replace(record, generation_path="/tmp/operator-generation-x")
        attempt_record = dataclasses.replace(
            record,
            generation_path=(
                "work/task_fixture/attempt-0123456789abcdef/"
                "operator-generation-0123456789abcdef"
            ),
        )
        self.assertEqual(
            attempt_record.generation_path,
            (
                "work/task_fixture/attempt-0123456789abcdef/"
                "operator-generation-0123456789abcdef"
            ),
        )
        with self.assertRaisesRegex(RecordError, "total bytes"):
            dataclasses.replace(record, total_nbytes=record.total_nbytes + 1)
        with self.assertRaisesRegex(RecordError, "filename"):
            dataclasses.replace(
                record.arrays[0],
                filename="../score_operator.npy",
            )

    def test_resampling_records_bind_canonical_schedule_and_block_axes(self) -> None:
        schedule, block = self._resampling_records()
        self.assertEqual(self._round_trip(schedule), schedule)
        self.assertEqual(self._round_trip(block), block)
        self.assertEqual(record_artifacts(schedule), (schedule.schedule,))
        self.assertEqual(record_artifacts(block), block.artifacts)

        with self.assertRaisesRegex(RecordError, "block size"):
            dataclasses.replace(schedule, block_size=249)
        wrong_schedule_artifact = self._artifact(
            "formal_resampling_schedule",
            (self.subjects, schedule.replicate_axis),
            digest="b",
            units="subject_index",
            dtype="int32",
        )
        with self.assertRaisesRegex(RecordError, "artifact"):
            dataclasses.replace(schedule, schedule=wrong_schedule_artifact)
        with self.assertRaisesRegex(RecordError, "interval"):
            dataclasses.replace(block, start=249)
        with self.assertRaisesRegex(RecordError, "block axis"):
            dataclasses.replace(block, block_axis=self.subjects)

        payload = encode_record(schedule)
        payload["unexpected"] = True
        with self.assertRaisesRegex(RecordCodecError, "fields do not match"):
            decode_record(
                "ResamplingScheduleRecord",
                payload,
                record_id=schedule.identifier,
                artifacts=record_artifacts(schedule),
            )

    def test_endpoint_input_record_separates_candidates_and_ready_subjects(self) -> None:
        record = EndpointInputRecord(
            endpoint=self.reference_endpoint,
            readiness_status="ready",
            candidate_subject_ids=("subject_1", "subject_2", "subject_3"),
            included_subject_ids=("subject_1", "subject_3"),
            exclusions=(
                SubjectExclusionRecord(
                    subject_id="subject_2",
                    reason_code="missing_frequency_class_exposure",
                ),
            ),
            minimum_subjects=2,
            subject_axis=self.subjects,
            baseline=self.baseline,
            outcome=self.outcome,
        )
        self.assertEqual(self._round_trip(record), record)
        self.assertEqual(record_artifacts(record), (self.baseline, self.outcome))
        with self.assertRaisesRegex(RecordError, "excluded subjects"):
            dataclasses.replace(record, exclusions=())
        with self.assertRaisesRegex(RecordError, "minimum_subjects"):
            dataclasses.replace(record, minimum_subjects=3)

    def test_prepared_exposure_binds_exact_axes_and_complete_auxiliary_inputs(self) -> None:
        reference_condition = self._artifact(
            "reference_condition_exposure",
            (self.subjects, self.features),
            digest="5",
            units="V/m",
        )
        addon_reference = self._artifact(
            "addon_reference_component_exposure",
            (self.subjects, self.features),
            digest="6",
            units="V/m",
        )
        overlap = self._artifact(
            "reference_overlap_mask",
            (self.subjects, self.features),
            digest="7",
            units="binary",
            dtype="bool",
        )
        total = self._artifact(
            "total_exposure",
            (self.subjects, self.features),
            digest="8",
            units="V/m",
        )
        readiness = self._document("delta_reference_input_readiness", digest="f")
        record = PreparedExposureRecord(
            endpoint=self.addon_endpoint,
            subject_axis=self.subjects,
            feature_axis=self.features,
            exposure=self.exposure,
            feature_ids=self.feature_ids,
            delta_reference_input_status="ready",
            delta_reference_reason_code="ready",
            auxiliary_readiness=readiness,
            reference_condition_exposure=reference_condition,
            addon_reference_component_exposure=addon_reference,
            reference_overlap_mask=overlap,
            total_exposure=total,
        )
        self.assertEqual(self._round_trip(record), record)
        self.assertEqual(
            record_artifacts(record),
            (
                self.exposure,
                self.feature_ids,
                readiness,
                reference_condition,
                addon_reference,
                overlap,
                total,
            ),
        )
        with self.assertRaisesRegex(RecordError, "exact subject and feature axes"):
            dataclasses.replace(record, exposure=self.weights)
        with self.assertRaisesRegex(RecordError, "feature_ids"):
            dataclasses.replace(record, feature_ids=None)
        delta_ready_without_sensitivity_auxiliaries = dataclasses.replace(
            record,
            reference_overlap_mask=None,
            total_exposure=None,
        )
        self.assertEqual(
            self._round_trip(delta_ready_without_sensitivity_auxiliaries),
            delta_ready_without_sensitivity_auxiliaries,
        )

        unavailable = dataclasses.replace(
            record,
            delta_reference_input_status="input_failure",
            delta_reference_reason_code="missing_reference_condition_exposure",
            reference_condition_exposure=None,
            addon_reference_component_exposure=None,
            reference_overlap_mask=None,
            total_exposure=None,
        )
        self.assertEqual(unavailable.exposure, self.exposure)
        self.assertEqual(self._round_trip(unavailable), unavailable)

    def test_reference_dependency_accepts_source_or_sensitive_record(self) -> None:
        source_dependency = ReferenceDependencyRecord(
            addon_endpoint=self.addon_endpoint,
            matched_reference_endpoint_id=self.reference_endpoint.identifier,
            dependency_status="ready",
            reference_record=self.source,
            delta_reference=None,
        )
        self.assertEqual(self._round_trip(source_dependency), source_dependency)

        sensitive_endpoint = EndpointKey(
            "study",
            "scale",
            "reference",
            "reference_fiber",
            "sensitive_connectome",
        )
        sensitive_addon = EndpointKey(
            "study",
            "scale",
            "addon",
            "addon_fiber",
            "sensitive_connectome",
        )
        sensitive = SensitiveRecord(
            endpoint=sensitive_endpoint,
            formal_endpoint_id="formal_endpoint",
            evaluated_tau=800,
            evaluated_coverage=5,
            input_status="valid",
            cell_computability_status="not_computable",
            prediction_status="not_applicable",
            feature_axis=None,
        )
        sensitive_dependency = ReferenceDependencyRecord(
            addon_endpoint=sensitive_addon,
            matched_reference_endpoint_id=sensitive_endpoint.identifier,
            dependency_status="ready",
            reference_record=sensitive,
            delta_reference=None,
        )
        self.assertEqual(self._round_trip(sensitive_dependency), sensitive_dependency)

    def test_final_decision_validates_realization_and_is_aggregate_only(self) -> None:
        decision = FinalDecisionRecord(
            endpoint=self.addon_endpoint,
            decision_status="realized_primary",
            final_model=self.final,
            reason_code="primary_model_realized",
            causal_task_ids=("task_b", "task_a"),
        )
        self.assertEqual(decision.causal_task_ids, ("task_a", "task_b"))
        self.assertEqual(record_identifier(decision), decision.identifier)
        self.assertEqual(
            record_artifacts(decision),
            (self.weights, self.exposure),
        )
        with self.assertRaises(RecordCodecError):
            encode_record(decision)
        with self.assertRaisesRegex(RecordError, "forbid"):
            dataclasses.replace(
                decision,
                decision_status="no_final_model",
            )

    def test_final_selection_is_typed_scientific_output_for_realized_and_empty_states(self) -> None:
        realized = FinalSelectionRecord(
            endpoint=self.addon_endpoint,
            selection_status="final_model_realized",
            final_model=self.final,
            reason_codes=("primary_model_realized",),
            causal_task_ids=("task_branch",),
        )
        self.assertEqual(self._round_trip(realized), realized)
        empty = FinalSelectionRecord(
            endpoint=self.addon_endpoint,
            selection_status="no_final_model",
            final_model=None,
            reason_codes=("no_accepted_branch",),
            causal_task_ids=("task_branch",),
        )
        self.assertEqual(self._round_trip(empty), empty)
        with self.assertRaisesRegex(RecordError, "requires a final_model"):
            dataclasses.replace(realized, final_model=None)
        with self.assertRaisesRegex(RecordError, "forbids a final_model"):
            dataclasses.replace(empty, final_model=self.final)

    def test_every_allowlisted_root_round_trips_with_stable_identifier(self) -> None:
        endpoint_input = EndpointInputRecord(
            endpoint=self.reference_endpoint,
            readiness_status="ready",
            candidate_subject_ids=("subject_1", "subject_2"),
            included_subject_ids=("subject_1", "subject_2"),
            exclusions=(),
            minimum_subjects=2,
            subject_axis=self.subjects,
            baseline=self.baseline,
            outcome=self.outcome,
        )
        prepared = PreparedExposureRecord(
            endpoint=self.reference_endpoint,
            subject_axis=self.subjects,
            feature_axis=self.features,
            exposure=self.exposure,
            feature_ids=self.feature_ids,
            delta_reference_input_status="not_applicable",
            delta_reference_reason_code="reference_endpoint",
            auxiliary_readiness=None,
            reference_condition_exposure=None,
            addon_reference_component_exposure=None,
            reference_overlap_mask=None,
            total_exposure=None,
        )
        observed_artifact = self._artifact(
            "observed_summary",
            (self.subjects,),
            digest="9",
        )
        observed = ObservedResult(self.source, (observed_artifact,))
        dependency = ReferenceDependencyRecord(
            addon_endpoint=self.addon_endpoint,
            matched_reference_endpoint_id=self.reference_endpoint.identifier,
            dependency_status="ready",
            reference_record=self.source,
            delta_reference=None,
        )
        delta = DeltaReferenceBundle(
            input_status="input_failure",
            support_status="not_applicable",
            selected_reference_tau=None,
            selected_reference_coverage=None,
            full_scores=None,
            fold_scores=None,
            support_rows=None,
        )
        sensitive = SensitiveRecord(
            endpoint=EndpointKey(
                "study",
                "scale",
                "reference",
                "reference_fiber",
                "sensitive_connectome",
            ),
            formal_endpoint_id="formal_endpoint",
            evaluated_tau=800,
            evaluated_coverage=5,
            input_status="input_failure",
            cell_computability_status="not_computable",
            prediction_status="not_applicable",
            feature_axis=None,
        )
        formal = FormalResult(
            final_model_id=self.final.identifier,
            resampling_kind="permutation",
            technical_status="completed",
            artifacts=(observed_artifact,),
        )
        sensitivity = SensitivityResult(
            target_id=self.final.identifier,
            sensitivity_kind="tau_neighborhood",
            artifacts=(observed_artifact,),
        )
        probability = self._artifact(
            "activation_probability",
            (self.subjects, self.features),
            digest="c",
            units="probability",
        )
        binary = self._artifact(
            "binary_exposure",
            (self.subjects, self.features),
            digest="d",
            units="binary",
            dtype="bool",
        )
        activation = ActivationArtifact(
            final_model_id=self.final.identifier,
            feature_axis=self.features,
            activation_probability=probability,
            binary_exposure=binary,
            artifacts=(observed_artifact,),
        )
        schedule, block = self._resampling_records()
        operator_scratch = self._operator_scratch_record()
        records = (
            endpoint_input,
            prepared,
            observed_artifact,
            observed,
            self.source,
            dependency,
            delta,
            self.branch,
            self.final,
            FinalSelectionRecord(
                endpoint=self.addon_endpoint,
                selection_status="final_model_realized",
                final_model=self.final,
                reason_codes=("primary_model_realized",),
                causal_task_ids=("task_final",),
            ),
            sensitive,
            formal,
            schedule,
            block,
            operator_scratch,
            sensitivity,
            activation,
        )
        self.assertEqual(
            {type(record).__name__ for record in records},
            {
                "EndpointInputRecord",
                "PreparedExposureRecord",
                "ArtifactRef",
                "ObservedResult",
                "SourceRecord",
                "ReferenceDependencyRecord",
                "DeltaReferenceBundle",
                "BranchRecord",
                "FinalModelRecord",
                "FinalSelectionRecord",
                "SensitiveRecord",
                "FormalResult",
                "ResamplingScheduleRecord",
                "ResamplingBlockRecord",
                "FormalOperatorScratchRecord",
                "SensitivityResult",
                "ActivationArtifact",
            },
        )
        for record in records:
            with self.subTest(record_type=type(record).__name__):
                decoded = self._round_trip(record)
                self.assertEqual(decoded, record)
                self.assertEqual(record_identifier(decoded), record_identifier(record))

    def test_codec_rejects_unknown_roots_type_mismatch_and_identifier_mismatch(self) -> None:
        with self.assertRaisesRegex(RecordCodecError, "not an allowlisted root"):
            encode_record(self.subjects)
        with self.assertRaisesRegex(RecordCodecError, "unknown record type"):
            decode_record(
                "UnknownRecord",
                {},
                record_id="unknown",
                artifacts=(),
            )
        payload = encode_record(self.source)
        with self.assertRaisesRegex(RecordCodecError, "fields do not match"):
            decode_record(
                "SensitiveRecord",
                payload,
                record_id=self.source.identifier,
                artifacts=record_artifacts(self.source),
            )
        with self.assertRaisesRegex(RecordCodecError, "identifier mismatch"):
            decode_record(
                "SourceRecord",
                payload,
                record_id="source_wrong",
                artifacts=record_artifacts(self.source),
            )

    def test_codec_rejects_extra_missing_and_malformed_nested_fields(self) -> None:
        observed = ObservedResult(self.source, (self.exposure,))
        payload = encode_record(observed)
        extra = copy.deepcopy(payload)
        extra["unexpected"] = True
        missing = copy.deepcopy(payload)
        del missing["artifacts"]
        malformed_axis = copy.deepcopy(payload)
        malformed_axis["artifacts"][0]["axis_refs"][0]["sha256"] = "f" * 64
        noncanonical_number = copy.deepcopy(payload)
        noncanonical_number["source"]["selected_tau"] = 200
        noncanonical_text = copy.deepcopy(payload)
        noncanonical_text["source"]["endpoint"]["scale_id"] = " scale "
        for invalid in (
            extra,
            missing,
            malformed_axis,
            noncanonical_number,
            noncanonical_text,
        ):
            with self.subTest(payload=invalid):
                with self.assertRaises(RecordCodecError):
                    decode_record(
                        "ObservedResult",
                        invalid,
                        record_id=observed.identifier,
                        artifacts=record_artifacts(observed),
                    )

    def test_codec_rejects_incomplete_reordered_or_extra_artifact_closure(self) -> None:
        observed = ObservedResult(self.source, (self.exposure,))
        payload = encode_record(observed)
        closure = record_artifacts(observed)
        self.assertEqual(closure, (self.weights, self.exposure))
        extra = self._artifact("extra", (self.subjects,), digest="e")
        for artifacts in (closure[1:], tuple(reversed(closure)), closure + (extra,)):
            with self.subTest(artifacts=artifacts):
                with self.assertRaisesRegex(RecordCodecError, "artifact closure mismatch"):
                    decode_record(
                        "ObservedResult",
                        payload,
                        record_id=observed.identifier,
                        artifacts=artifacts,
                    )


if __name__ == "__main__":
    unittest.main()
