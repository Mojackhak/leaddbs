"""Exhaustive truth-table tests for the one-way fallback state machine."""

from __future__ import annotations

import dataclasses
import unittest

from dual_frequency.contracts import (
    ArtifactRef,
    AxisRef,
    BranchRecord,
    EndpointKey,
    FeatureAxisRef,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SourceRecord,
)
from dual_frequency.workflow.state import (
    ADJUSTED_BRANCH,
    NO_DELTA_BRANCH,
    BranchPlan,
    FinalDecision,
    StateError,
    derive_branch_plan,
    realize_final,
)


REFERENCE_ENDPOINT = EndpointKey("study", "scale", "reference", "reference_voxel")
ADDON_ENDPOINT = EndpointKey("study", "scale", "addon", "addon_voxel")
SENSITIVE_REFERENCE_ENDPOINT = EndpointKey(
    "study",
    "scale",
    "reference",
    "reference_fiber",
    "sensitive_connectome",
)
SENSITIVE_ADDON_ENDPOINT = EndpointKey(
    "study",
    "scale",
    "addon",
    "addon_fiber",
    "sensitive_connectome",
)
FORMAL_REFERENCE_ENDPOINT = EndpointKey(
    "study",
    "scale",
    "reference",
    "reference_fiber",
    "formal_connectome",
)
ACCEPTED_SOURCE_STATUSES = ("pre_specified_accepted", "scan_fallback_accepted")


def _accepted_source(
    endpoint: EndpointKey,
    *,
    source_status: str = "pre_specified_accepted",
    prediction_status: str = "error_predictive",
) -> SourceRecord:
    axis = AxisRef("features", 3, "a" * 64)
    artifact = ArtifactRef(
        kind="feature_weights",
        schema_version="array_v1",
        uri="file:///tmp/feature_weights.npy",
        sha256="b" * 64,
        dtype="float64",
        shape=(axis.count,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="synthetic",
        producer_id="state_test",
        producer_version="1",
    )
    return SourceRecord(
        endpoint=endpoint,
        input_status="valid",
        source_status=source_status,
        prediction_status=prediction_status,
        threshold_source="pre_specified",
        selected_tau=200,
        selected_coverage=2,
        adjacent_support=1,
        feature_axis=FeatureAxisRef(axis, "synthetic_features"),
        artifacts=(artifact,),
    )


def _absent_source(endpoint: EndpointKey, *, input_status: str = "valid") -> SourceRecord:
    return SourceRecord(
        endpoint=endpoint,
        input_status=input_status,
        source_status="absent_no_stable_grid",
        prediction_status="not_applicable",
        threshold_source="none",
        selected_tau=None,
        selected_coverage=None,
        adjacent_support=None,
        feature_axis=None,
    )


def _dependency(
    dependency_status: str = "ready",
    reference_source: SourceRecord | None = None,
) -> ReferenceDependencyRecord:
    return ReferenceDependencyRecord(
        addon_endpoint=ADDON_ENDPOINT,
        matched_reference_endpoint_id=REFERENCE_ENDPOINT.identifier,
        dependency_status=dependency_status,
        reference_source=reference_source,
        delta_reference=None,
    )


def _sensitive_dependency(
    *,
    computability_status: str,
    prediction_status: str,
) -> ReferenceDependencyRecord:
    axis = AxisRef("features", 3, "c" * 64)
    feature_axis = (
        FeatureAxisRef(axis, "synthetic_sensitive_features")
        if computability_status == "computable"
        else None
    )
    evidence = SensitiveRecord(
        endpoint=SENSITIVE_REFERENCE_ENDPOINT,
        formal_endpoint_id=FORMAL_REFERENCE_ENDPOINT.identifier,
        evaluated_tau=200,
        evaluated_coverage=2,
        input_status="valid",
        cell_computability_status=computability_status,
        prediction_status=prediction_status,
        feature_axis=feature_axis,
    )
    return ReferenceDependencyRecord(
        addon_endpoint=SENSITIVE_ADDON_ENDPOINT,
        matched_reference_endpoint_id=SENSITIVE_REFERENCE_ENDPOINT.identifier,
        dependency_status="ready",
        reference_record=evidence,
        delta_reference=None,
    )


def _branch(
    name: str,
    *,
    input_status: str = "valid",
    design_status: str = "valid",
    source_status: str | None = "pre_specified_accepted",
    source_input_status: str = "valid",
    prediction_status: str = "error_predictive",
    failure_stage: str = "none",
    endpoint: EndpointKey = ADDON_ENDPOINT,
) -> BranchRecord:
    if source_status is None:
        source = None
    elif source_status == "absent_no_stable_grid":
        source = _absent_source(endpoint, input_status=source_input_status)
    else:
        source = _accepted_source(
            endpoint,
            source_status=source_status,
            prediction_status=prediction_status,
        )
    return BranchRecord(
        endpoint=endpoint,
        branch=name,
        intended_role="primary",
        input_status=input_status,
        nuisance_design_status=design_status,
        source=source,
        failure_stage=failure_stage,
        failure_detail="synthetic_failure" if failure_stage != "none" else "none",
    )


def _ready_plan(prediction_status: str, delta_status: str = "valid") -> BranchPlan:
    reference = _accepted_source(REFERENCE_ENDPOINT, prediction_status=prediction_status)
    return derive_branch_plan(_dependency(reference_source=reference), delta_status)


class BranchPlanTruthTableTest(unittest.TestCase):
    def test_every_nonready_reference_dependency_is_terminal(self) -> None:
        for dependency_status in (
            "not_configured",
            "input_failure",
            "design_failure",
            "execution_failure",
        ):
            with self.subTest(dependency_status=dependency_status):
                plan = derive_branch_plan(_dependency(dependency_status), "valid")
                self.assertEqual(plan.status, "dependency_failure")
                self.assertIsNone(plan.intended_branch)
                self.assertEqual(plan.attempted_branches, ())
                self.assertEqual(plan.intended_status, "dependency_failure")
                self.assertFalse(plan.fallback_eligible)

                final = realize_final(plan, {})
                self.assertEqual(final.final_status, "dependency_failure")
                self.assertEqual(final.final_role, "no_final_model")
                self.assertIsNone(final.final_branch)

    def test_missing_ready_reference_record_is_dependency_failure(self) -> None:
        plan = derive_branch_plan(_dependency("ready", None), "valid")
        self.assertEqual(plan.status, "dependency_failure")
        self.assertIsNone(plan.intended_branch)
        self.assertEqual(plan.attempted_branches, ())

    def test_ready_absent_reference_runs_no_delta_only(self) -> None:
        for delta_status in ("valid", "invalid"):
            with self.subTest(delta_status=delta_status):
                plan = derive_branch_plan(
                    _dependency(reference_source=_absent_source(REFERENCE_ENDPOINT)),
                    delta_status,
                )
                self.assertEqual(plan.status, "ready")
                self.assertEqual(plan.intended_branch, NO_DELTA_BRANCH)
                self.assertEqual(plan.attempted_branches, (NO_DELTA_BRANCH,))
                self.assertEqual(plan.intended_status, "pending")
                self.assertFalse(plan.fallback_eligible)

    def test_accepted_reference_truth_table_is_exhaustive_and_deterministic(self) -> None:
        cases = (
            (
                "error_predictive",
                "valid",
                ADJUSTED_BRANCH,
                (NO_DELTA_BRANCH, ADJUSTED_BRANCH),
                "pending",
                True,
            ),
            (
                "error_predictive",
                "invalid",
                ADJUSTED_BRANCH,
                (NO_DELTA_BRANCH,),
                "input_failure",
                True,
            ),
            (
                "error_nonpredictive",
                "valid",
                NO_DELTA_BRANCH,
                (NO_DELTA_BRANCH, ADJUSTED_BRANCH),
                "pending",
                False,
            ),
            (
                "error_nonpredictive",
                "invalid",
                NO_DELTA_BRANCH,
                (NO_DELTA_BRANCH,),
                "pending",
                False,
            ),
        )
        for source_status in ACCEPTED_SOURCE_STATUSES:
            for (
                prediction_status,
                delta_status,
                intended_branch,
                attempted_branches,
                intended_status,
                fallback_eligible,
            ) in cases:
                with self.subTest(
                    source_status=source_status,
                    prediction_status=prediction_status,
                    delta_status=delta_status,
                ):
                    reference = _accepted_source(
                        REFERENCE_ENDPOINT,
                        source_status=source_status,
                        prediction_status=prediction_status,
                    )
                    dependency = _dependency(reference_source=reference)
                    first = derive_branch_plan(dependency, delta_status)
                    second = derive_branch_plan(dependency, delta_status)
                    self.assertEqual(first, second)
                    self.assertEqual(first.status, "ready")
                    self.assertEqual(first.intended_branch, intended_branch)
                    self.assertEqual(first.attempted_branches, attempted_branches)
                    self.assertEqual(first.intended_status, intended_status)
                    self.assertEqual(first.fallback_eligible, fallback_eligible)

    def test_computable_sensitive_reference_uses_prediction_status(self) -> None:
        predictive = derive_branch_plan(
            _sensitive_dependency(
                computability_status="computable",
                prediction_status="error_predictive",
            ),
            "valid",
        )
        self.assertEqual(predictive.intended_branch, ADJUSTED_BRANCH)
        self.assertEqual(predictive.attempted_branches, (NO_DELTA_BRANCH, ADJUSTED_BRANCH))

        nonpredictive = derive_branch_plan(
            _sensitive_dependency(
                computability_status="computable",
                prediction_status="error_nonpredictive",
            ),
            "valid",
        )
        self.assertEqual(nonpredictive.intended_branch, NO_DELTA_BRANCH)
        self.assertEqual(nonpredictive.attempted_branches, (NO_DELTA_BRANCH, ADJUSTED_BRANCH))

    def test_noncomputable_sensitive_reference_runs_no_delta_only(self) -> None:
        plan = derive_branch_plan(
            _sensitive_dependency(
                computability_status="not_computable",
                prediction_status="not_applicable",
            ),
            "valid",
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual(plan.intended_branch, NO_DELTA_BRANCH)
        self.assertEqual(plan.attempted_branches, (NO_DELTA_BRANCH,))
        self.assertEqual(plan.intended_status, "pending")
        self.assertFalse(plan.fallback_eligible)

    def test_blank_delta_status_is_rejected(self) -> None:
        reference = _accepted_source(REFERENCE_ENDPOINT)
        with self.assertRaisesRegex(StateError, "delta_status"):
            derive_branch_plan(_dependency(reference_source=reference), "  ")

    def test_plan_is_immutable(self) -> None:
        plan = _ready_plan("error_predictive")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            plan.status = "changed"


class FinalDecisionTruthTableTest(unittest.TestCase):
    def test_adjusted_input_design_and_source_failures_use_accepted_no_delta_fallback(self) -> None:
        failures = (
            ("missing", None),
            ("input", _branch(ADJUSTED_BRANCH, input_status="input_failure", source_status=None)),
            ("design", _branch(ADJUSTED_BRANCH, design_status="design_failure")),
            (
                "source_input",
                _branch(
                    ADJUSTED_BRANCH,
                    source_status="absent_no_stable_grid",
                    source_input_status="input_failure",
                ),
            ),
            ("source_absent", _branch(ADJUSTED_BRANCH, source_status="absent_no_stable_grid")),
        )
        plan = _ready_plan("error_predictive")
        for failure_name, intended in failures:
            for source_status in ACCEPTED_SOURCE_STATUSES:
                with self.subTest(failure=failure_name, fallback_source=source_status):
                    fallback = _branch(NO_DELTA_BRANCH, source_status=source_status)
                    branches = {NO_DELTA_BRANCH: fallback}
                    if intended is not None:
                        branches[ADJUSTED_BRANCH] = intended
                    final = realize_final(plan, branches)
                    self.assertEqual(final.intended_branch, ADJUSTED_BRANCH)
                    self.assertEqual(final.final_branch, NO_DELTA_BRANCH)
                    self.assertEqual(final.final_role, "fallback_final")
                    self.assertEqual(final.final_status, "fallback_final_realized")
                    self.assertIs(final.selected_branch, fallback)
                    self.assertTrue(final.failure_reasons)

    def test_invalid_delta_preflight_uses_no_delta_fallback_without_adjusted_attempt(self) -> None:
        plan = _ready_plan("error_predictive", "invalid")
        fallback = _branch(NO_DELTA_BRANCH)
        unplanned_adjusted = _branch(ADJUSTED_BRANCH, source_status="scan_fallback_accepted")
        final = realize_final(
            plan,
            {
                ADJUSTED_BRANCH: unplanned_adjusted,
                NO_DELTA_BRANCH: fallback,
            },
        )
        self.assertEqual(plan.attempted_branches, (NO_DELTA_BRANCH,))
        self.assertEqual(final.final_branch, NO_DELTA_BRANCH)
        self.assertEqual(final.final_role, "fallback_final")
        self.assertIs(final.selected_branch, fallback)

    def test_failed_intended_no_delta_never_promotes_adjusted(self) -> None:
        failures = (
            ("missing", None),
            ("input", _branch(NO_DELTA_BRANCH, input_status="input_failure", source_status=None)),
            ("design", _branch(NO_DELTA_BRANCH, design_status="design_failure")),
            ("source_absent", _branch(NO_DELTA_BRANCH, source_status="absent_no_stable_grid")),
        )
        plan = _ready_plan("error_nonpredictive")
        adjusted = _branch(ADJUSTED_BRANCH, source_status="scan_fallback_accepted")
        for failure_name, intended in failures:
            with self.subTest(failure=failure_name):
                branches = {ADJUSTED_BRANCH: adjusted}
                if intended is not None:
                    branches[NO_DELTA_BRANCH] = intended
                final = realize_final(plan, branches)
                self.assertEqual(final.intended_branch, NO_DELTA_BRANCH)
                self.assertIsNone(final.final_branch)
                self.assertEqual(final.final_role, "no_final_model")
                self.assertEqual(final.final_status, "no_final_model")
                self.assertIsNone(final.selected_branch)
                self.assertNotEqual(final.final_branch, ADJUSTED_BRANCH)

    def test_intended_technical_failure_never_triggers_fallback(self) -> None:
        technical_failures = (
            ("input", {"input_status": "execution_failure", "source_status": None}),
            ("design", {"design_status": "execution_failure"}),
            (
                "source",
                {
                    "source_status": "absent_no_stable_grid",
                    "source_input_status": "execution_failure",
                },
            ),
            ("stage", {"failure_stage": "execution"}),
        )
        cases = (
            ("error_predictive", ADJUSTED_BRANCH, NO_DELTA_BRANCH),
            ("error_nonpredictive", NO_DELTA_BRANCH, ADJUSTED_BRANCH),
        )
        for prediction_status, intended_name, alternate_name in cases:
            for failure_name, kwargs in technical_failures:
                with self.subTest(prediction=prediction_status, failure=failure_name):
                    plan = _ready_plan(prediction_status)
                    final = realize_final(
                        plan,
                        {
                            intended_name: _branch(intended_name, **kwargs),
                            alternate_name: _branch(alternate_name),
                        },
                    )
                    self.assertIsNone(final.final_branch)
                    self.assertEqual(final.final_role, "no_final_model")
                    self.assertEqual(final.final_status, "execution_failure")

    def test_accepted_intended_branch_wins_when_alternate_has_technical_failure(self) -> None:
        cases = (
            ("error_predictive", ADJUSTED_BRANCH, NO_DELTA_BRANCH),
            ("error_nonpredictive", NO_DELTA_BRANCH, ADJUSTED_BRANCH),
        )
        for prediction_status, intended_name, alternate_name in cases:
            with self.subTest(prediction_status=prediction_status):
                plan = _ready_plan(prediction_status)
                intended = _branch(intended_name, source_status="scan_fallback_accepted")
                final = realize_final(
                    plan,
                    {
                        alternate_name: _branch(
                            alternate_name,
                            input_status="execution_failure",
                            source_status=None,
                        ),
                        intended_name: intended,
                    },
                )
                self.assertEqual(final.final_branch, intended_name)
                self.assertEqual(final.final_role, "primary")
                self.assertEqual(final.final_status, "final_model_realized")
                self.assertIs(final.selected_branch, intended)
                self.assertEqual(final.failure_reasons, ())

    def test_adjusted_failure_with_unavailable_fallback_has_no_final(self) -> None:
        plan = _ready_plan("error_predictive")
        final = realize_final(
            plan,
            {
                ADJUSTED_BRANCH: _branch(ADJUSTED_BRANCH, design_status="design_failure"),
                NO_DELTA_BRANCH: _branch(NO_DELTA_BRANCH, source_status="absent_no_stable_grid"),
            },
        )
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_status, "no_final_model")
        self.assertEqual(len(final.failure_reasons), 2)

    def test_adjusted_failure_with_fallback_execution_failure_is_execution_failure(self) -> None:
        plan = _ready_plan("error_predictive")
        final = realize_final(
            plan,
            {
                ADJUSTED_BRANCH: _branch(ADJUSTED_BRANCH, input_status="input_failure", source_status=None),
                NO_DELTA_BRANCH: _branch(
                    NO_DELTA_BRANCH,
                    input_status="execution_failure",
                    source_status=None,
                ),
            },
        )
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_status, "execution_failure")

    def test_dependency_failure_cannot_realize_a_present_branch(self) -> None:
        plan = derive_branch_plan(_dependency("execution_failure"), "valid")
        final = realize_final(plan, {NO_DELTA_BRANCH: _branch(NO_DELTA_BRANCH)})
        self.assertIsNone(final.final_branch)
        self.assertEqual(final.final_status, "dependency_failure")

    def test_realization_is_independent_of_mapping_insertion_order(self) -> None:
        plan = _ready_plan("error_predictive")
        intended = _branch(ADJUSTED_BRANCH)
        alternate = _branch(NO_DELTA_BRANCH)
        forward = realize_final(
            plan,
            {NO_DELTA_BRANCH: alternate, ADJUSTED_BRANCH: intended},
        )
        reverse = realize_final(
            plan,
            {ADJUSTED_BRANCH: intended, NO_DELTA_BRANCH: alternate},
        )
        self.assertEqual(forward, reverse)

    def test_invalid_branch_mapping_is_rejected(self) -> None:
        plan = _ready_plan("error_predictive")
        with self.assertRaisesRegex(StateError, "mapping key"):
            realize_final(plan, {NO_DELTA_BRANCH: _branch(ADJUSTED_BRANCH)})

        other_endpoint = dataclasses.replace(ADDON_ENDPOINT, scale_id="other_scale")
        with self.assertRaisesRegex(StateError, "endpoint"):
            realize_final(plan, {NO_DELTA_BRANCH: _branch(NO_DELTA_BRANCH, endpoint=other_endpoint)})

    def test_decision_is_immutable_and_api_is_exported(self) -> None:
        import dual_frequency.workflow as workflow

        plan = _ready_plan("error_predictive")
        final = realize_final(plan, {ADJUSTED_BRANCH: _branch(ADJUSTED_BRANCH)})
        self.assertIs(workflow.BranchPlan, BranchPlan)
        self.assertIs(workflow.FinalDecision, FinalDecision)
        self.assertIs(workflow.derive_branch_plan, derive_branch_plan)
        self.assertIs(workflow.realize_final, realize_final)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            final.final_status = "changed"


if __name__ == "__main__":
    unittest.main()
