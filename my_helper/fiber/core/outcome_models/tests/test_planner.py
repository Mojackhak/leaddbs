"""Tests for the endpoint-aware, round-complete execution planner."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.identity import EndpointModelKey, TaskKey
from outcome_models.planner import (
    DependencyRequirement,
    DependencySpec,
    ExecutionPlan,
    GatePredicate,
    PlanError,
    TaskGate,
    TaskSpec,
    compile_execution_plan,
)
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


_PHASE_ORDER = {"observed": 0, "formal": 1, "sensitivity": 2, "report": 3}


class ExecutionPlannerTests(unittest.TestCase):
    def _build(self, *, through: str = "report", mutate=None, rows=None):
        def combined(profiles):
            profiles["workflow"]["execution"]["through"] = through
            if mutate is not None:
                mutate(profiles)

        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        workflow_path = write_profile_bundle(root, mutate=combined)
        write_clinical_rows(root, rows or clinical_rows_for_scale("Scale One"))
        config = load_resolved_workflow(workflow_path, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)
        return temporary, config, catalog, plan

    def test_all_four_model_round_inventories_are_present(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)
        by_family: dict[str, set[str]] = {}
        for task in plan.tasks:
            by_family.setdefault(task.endpoint.model_family, set()).add(task.round_name)

        self.assertEqual(by_family["hf_voxel"], {f"Round {value}" for value in range(9)})
        self.assertEqual(
            by_family["hf_fiber"],
            {"Round 0", "Round 1", "Round 2", "Round 3", "Round 4", "Round 5", "Round 5.5", "Round 6", "Round 7", "Round 8", "Round 9"},
        )
        self.assertEqual(by_family["ulf_voxel"], {f"Round {value}" for value in range(10)})
        self.assertEqual(by_family["ulf_fiber"], {f"Round {value}" for value in range(11)})
        self.assertTrue(all(task.expected_artifact_kinds for task in plan.tasks))

    def test_immediate_uses_round_2b_and_omitted_iv_immediate_has_no_tasks(self) -> None:
        def mutate(profiles):
            first = profiles["scales"]["scales"][0]
            first.update({"scale_id": "mds_updrs_iii", "label": "MDS-UPDRS III score"})
            first["endpoint_bindings"]["frequency_2_addon_immediate"] = {
                "protocol": "STN+SNr",
                "phase": "immediate",
            }
            second = {
                **first,
                "scale_id": "mds_updrs_iv",
                "label": "MDS-UPDRS IV",
                "endpoint_bindings": {
                    key: value
                    for key, value in first["endpoint_bindings"].items()
                    if key != "frequency_2_addon_immediate"
                },
            }
            profiles["scales"]["scales"] = [first, second]
            profiles["workflow"]["selection"]["scales"] = ["mds_updrs_iii", "mds_updrs_iv"]
            profiles["workflow"]["selection"]["phases"] = ["chronic", "immediate"]

        rows = clinical_rows_for_scale("MDS-UPDRS III score", include_immediate=True)
        rows.extend(clinical_rows_for_scale("MDS-UPDRS IV", subject_prefix="iv"))
        temporary, _, catalog, plan = self._build(mutate=mutate, rows=rows)
        self.addCleanup(temporary.cleanup)

        iii_immediate = [
            task
            for task in plan.tasks
            if task.endpoint.scale_id == "mds_updrs_iii" and task.endpoint.endpoint_phase == "immediate"
        ]
        iv_immediate = [
            task
            for task in plan.tasks
            if task.endpoint.scale_id == "mds_updrs_iv" and task.endpoint.endpoint_phase == "immediate"
        ]
        self.assertTrue(any(task.round_name == "Round 2b" for task in iii_immediate))
        self.assertFalse(any(task.round_name == "Round 2" for task in iii_immediate))
        self.assertEqual(iv_immediate, [])
        self.assertTrue(any(row.key.scale_id == "mds_updrs_iv" and row.key.endpoint_phase == "immediate" for row in catalog))

    def test_ulf_dependencies_match_same_scale_model_and_connectome(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)
        tasks = {task.task_id: task for task in plan.tasks}

        c_lock = next(task for task in plan.tasks if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "input_hf_lock")
        c_upstream = tasks[c_lock.dependencies[0].task_id]
        self.assertEqual(c_lock.dependencies[0].requirement, DependencyRequirement.TERMINAL)
        self.assertEqual(c_upstream.endpoint.model_family, "hf_voxel")
        self.assertEqual(c_upstream.endpoint.scale_id, c_lock.endpoint.scale_id)

        d_lock = next(task for task in plan.tasks if task.endpoint.model_family == "ulf_fiber" and task.key.execution_stage == "input_hf_lock")
        d_upstream = tasks[d_lock.dependencies[0].task_id]
        self.assertEqual(d_upstream.endpoint.model_family, "hf_fiber")
        self.assertEqual(d_upstream.endpoint.scale_id, d_lock.endpoint.scale_id)
        self.assertEqual(d_upstream.endpoint.connectome, d_lock.endpoint.connectome)

    def test_missing_matched_hf_catalog_dependency_is_rejected(self) -> None:
        temporary, config, catalog, _ = self._build()
        self.addCleanup(temporary.cleanup)
        without_hf_voxel = tuple(row for row in catalog if row.key.model_family != "hf_voxel")
        with self.assertRaises(PlanError):
            compile_execution_plan(config, without_hf_voxel)

    def test_conditional_branches_and_final_linked_tasks_have_typed_gates(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)

        adjusted = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel"
            and task.key.execution_stage == "observed_branch_resolver"
            and task.key.branch == "delta_hf_adjusted"
        )
        no_delta = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel"
            and task.key.execution_stage == "observed_branch_resolver"
            and task.key.branch == "no_delta_hf"
        )
        final = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "final_model_realization"
        )
        formal = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "formal_permutation"
        )
        jitter = next(
            task
            for task in plan.tasks
            if task.endpoint.model_family == "ulf_voxel" and task.key.execution_stage == "spatial_jitter"
        )

        self.assertEqual(adjusted.gate.predicate, GatePredicate.DELTA_HFSCORE_INPUTS_VALID)
        self.assertEqual(no_delta.gate.predicate, GatePredicate.BRANCH_INTENDED_OR_COMPARISON)
        self.assertTrue(all(item.requirement == DependencyRequirement.TERMINAL for item in final.dependencies))
        self.assertIn(DependencySpec(final.task_id, DependencyRequirement.ACCEPTED_FINAL), formal.dependencies)
        self.assertTrue(any(item.requirement == DependencyRequirement.FORMAL_COMPLETE for item in jitter.dependencies))

    def test_round_8_ulf_voxel_sensitivity_and_summary_are_distinct_tasks(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)
        round_eight = [
            task for task in plan.tasks if task.endpoint.model_family == "ulf_voxel" and task.round_name == "Round 8"
        ]
        self.assertEqual({task.workflow_phase for task in round_eight}, {"sensitivity", "report"})
        self.assertEqual(len({task.task_id for task in round_eight}), len(round_eight))

    def test_through_stages_are_nested_and_dependency_complete(self) -> None:
        plans = {}
        temporary_directories = []
        for phase in _PHASE_ORDER:
            temporary, _, _, plan = self._build(through=phase)
            temporary_directories.append(temporary)
            plans[phase] = plan
        for temporary in temporary_directories:
            self.addCleanup(temporary.cleanup)

        task_ids = {phase: {task.task_id for task in plan.tasks} for phase, plan in plans.items()}
        self.assertLess(task_ids["observed"], task_ids["formal"])
        self.assertLess(task_ids["formal"], task_ids["sensitivity"])
        self.assertLess(task_ids["sensitivity"], task_ids["report"])
        for phase, plan in plans.items():
            present = {task.task_id for task in plan.tasks}
            self.assertTrue(all(_PHASE_ORDER[task.workflow_phase] <= _PHASE_ORDER[phase] for task in plan.tasks))
            self.assertTrue(all(dependency.task_id in present for task in plan.tasks for dependency in task.dependencies))

    def test_report_waits_for_terminal_results_without_success_requirement(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)
        reports = [task for task in plan.tasks if task.workflow_phase == "report"]
        self.assertTrue(reports)
        self.assertTrue(all(task.dependencies for task in reports))
        self.assertTrue(
            all(dependency.requirement == DependencyRequirement.TERMINAL for task in reports for dependency in task.dependencies)
        )

    def test_operation_specific_stages_prevent_formal_task_identity_collision(self) -> None:
        temporary, _, _, plan = self._build()
        self.addCleanup(temporary.cleanup)
        formal = [task for task in plan.tasks if task.endpoint.model_family == "hf_voxel" and task.workflow_phase == "formal"]
        stages = {task.key.execution_stage for task in formal}
        self.assertIn("formal_permutation", stages)
        self.assertIn("formal_bootstrap", stages)
        self.assertEqual(len({task.task_id for task in formal}), len(formal))

    def test_recompilation_is_byte_stable_and_all_task_ids_are_unique(self) -> None:
        temporary, config, catalog, plan = self._build()
        self.addCleanup(temporary.cleanup)
        repeated = compile_execution_plan(config, catalog)
        self.assertEqual(plan.as_dict(), repeated.as_dict())
        self.assertEqual(len({task.task_id for task in plan.tasks}), len(plan.tasks))

    def test_nonformal_connectome_has_no_formal_oss_or_jitter_tasks(self) -> None:
        def mutate(profiles):
            profiles["study"]["connectomes"]["mgh"] = {
                "label": "MGH",
                "path": str(Path(profiles["study"]["paths"]["asset_root"]) / "mgh.mat"),
                "fiber_identity_source": "mgh.mat:idx",
            }
            profiles["model"]["normative_fiber"]["connectome_roles"]["mgh"] = "observed_robustness"
            profiles["workflow"]["selection"]["connectomes"] = ["dtor", "mgh"]

        temporary, _, _, plan = self._build(mutate=mutate)
        self.addCleanup(temporary.cleanup)
        mgh = [task for task in plan.tasks if task.endpoint.connectome == "mgh"]
        forbidden = {"formal_permutation_bootstrap", "oss_sensitivity", "spatial_jitter"}
        self.assertFalse(any(task.key.execution_stage in forbidden for task in mgh))
        self.assertTrue(any(task.workflow_phase == "report" for task in mgh))

    def test_missing_dependency_and_cycle_are_rejected(self) -> None:
        endpoint = EndpointModelKey(
            study_id="synthetic_study",
            scale_id="scale_one",
            endpoint_phase="reference",
            model_family="hf_voxel",
        )
        first_key = TaskKey(endpoint_model_id=endpoint.identifier, execution_stage="first")
        second_key = TaskKey(endpoint_model_id=endpoint.identifier, execution_stage="second")
        missing = TaskSpec(
            task_id=first_key.identifier,
            key=first_key,
            endpoint=endpoint,
            round_name="Round 0",
            workflow_phase="observed",
            dependencies=(DependencySpec("task_missing", DependencyRequirement.SUCCESS),),
            gate=TaskGate(GatePredicate.ALWAYS),
            expected_artifact_kinds=("task_manifest",),
        )
        with self.assertRaises(PlanError):
            ExecutionPlan.from_tasks((missing,), through="observed")

        first = TaskSpec(
            task_id=first_key.identifier,
            key=first_key,
            endpoint=endpoint,
            round_name="Round 0",
            workflow_phase="observed",
            dependencies=(DependencySpec(second_key.identifier, DependencyRequirement.SUCCESS),),
            gate=TaskGate(GatePredicate.ALWAYS),
            expected_artifact_kinds=("task_manifest",),
        )
        second = TaskSpec(
            task_id=second_key.identifier,
            key=second_key,
            endpoint=endpoint,
            round_name="Round 1",
            workflow_phase="observed",
            dependencies=(DependencySpec(first_key.identifier, DependencyRequirement.SUCCESS),),
            gate=TaskGate(GatePredicate.ALWAYS),
            expected_artifact_kinds=("task_manifest",),
        )
        with self.assertRaises(PlanError):
            ExecutionPlan.from_tasks((first, second), through="observed")

        report_key = TaskKey(endpoint_model_id=endpoint.identifier, execution_stage="report")
        report = TaskSpec(
            task_id=report_key.identifier,
            key=report_key,
            endpoint=endpoint,
            round_name="Round 8",
            workflow_phase="report",
            dependencies=(),
            gate=TaskGate(GatePredicate.ALWAYS),
            expected_artifact_kinds=("task_manifest",),
        )
        with self.assertRaises(PlanError):
            ExecutionPlan.from_tasks((report,), through="observed")


if __name__ == "__main__":
    unittest.main()
