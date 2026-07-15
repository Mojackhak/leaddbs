"""Round-aware DAG compilation tests without scientific model execution."""

from __future__ import annotations

import dataclasses
import unittest

from dual_frequency.catalog import CatalogStatus, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides
from dual_frequency.workflow import compile_execution_plan

from test_catalog import SCALE_IDS, make_workflow, synthetic_study


class PlannerTest(unittest.TestCase):
    def _plan(self, **override_values):
        overrides = WorkflowOverrides(all_available=True, **override_values)
        config = make_workflow(overrides)
        catalog = build_endpoint_catalog(config, synthetic_study())
        return config, catalog, compile_execution_plan(config, catalog)

    def test_compiles_unique_topological_tasks_for_all_four_families(self) -> None:
        config, _catalog, plan = self._plan()
        self.assertEqual(plan.configuration_hash, config.configuration_hash)
        self.assertEqual(
            plan.scientific_configuration_hash,
            config.scientific_configuration_hash,
        )
        self.assertEqual(
            {task.model_family for task in plan.tasks},
            {"reference_voxel", "reference_fiber", "addon_voxel", "addon_fiber"},
        )
        self.assertEqual(len({task.task_id for task in plan.tasks}), len(plan.tasks))
        task_ids: set[str] = set()
        for task in plan.tasks:
            self.assertTrue(set(task.dependencies) <= task_ids)
            self.assertEqual(task.key.parameter_identity, config.scientific_configuration_hash)
            task_ids.add(task.task_id)

    def test_sensitive_connectomes_never_schedule_final_or_final_linked_work(self) -> None:
        _config, catalog, plan = self._plan()
        sensitive_ids = {
            endpoint.endpoint_id
            for endpoint in catalog
            if endpoint.connectome_role == "sensitive"
        }
        forbidden = {
            "source_resolver",
            "final_realization",
            "formal_permutation",
            "formal_bootstrap",
            "activation_sensitivity",
            "spatial_jitter",
        }
        for endpoint_id in sensitive_ids:
            stages = {task.stage for task in plan.for_endpoint(endpoint_id)}
            self.assertTrue(stages.isdisjoint(forbidden))
            if "catalog_terminal" not in stages:
                self.assertIn("formal_source_evaluation", stages)

    def test_only_formal_fiber_finals_schedule_activation_as_expensive(self) -> None:
        _config, catalog, plan = self._plan()
        roles = {endpoint.endpoint_id: endpoint.connectome_role for endpoint in catalog}
        expensive = tuple(task for task in plan.tasks if task.expensive_producer)
        self.assertTrue(expensive)
        self.assertTrue(all(task.stage == "activation_sensitivity" for task in expensive))
        self.assertTrue(all(task.model_family.endswith("fiber") for task in expensive))
        self.assertTrue(all(roles[task.endpoint_id] == "formal" for task in expensive))

    def test_unavailable_endpoint_is_closed_without_blocking_other_scales(self) -> None:
        _config, catalog, plan = self._plan()
        unavailable = {
            endpoint.endpoint_id
            for endpoint in catalog
            if endpoint.status != CatalogStatus.DATA_AVAILABLE
        }
        self.assertTrue(unavailable)
        for endpoint_id in unavailable:
            self.assertEqual(
                {task.stage for task in plan.for_endpoint(endpoint_id)},
                {"catalog_terminal", "terminal_report"},
            )
        available_scale_tasks = {
            task.stage
            for endpoint in catalog
            if endpoint.key.scale_id == SCALE_IDS[0]
            for task in plan.for_endpoint(endpoint.endpoint_id)
        }
        self.assertIn("formal_permutation", available_scale_tasks)

    def test_observed_cutoff_plans_resolvers_and_finals_but_no_downstream_phase(self) -> None:
        config, _catalog, plan = self._plan(through="observed")
        self.assertEqual(config.workflow.execution.through, "observed")
        self.assertTrue(all(task.phase == "observed" for task in plan.tasks))
        self.assertTrue(any(task.stage == "source_resolver" for task in plan.tasks))
        self.assertTrue(any(task.stage == "final_realization" for task in plan.tasks))
        self.assertFalse(any(task.stage == "formal_permutation" for task in plan.tasks))

    def test_addon_dependency_uses_the_exact_catalog_reference(self) -> None:
        _config, catalog, plan = self._plan()
        task_index = {task.task_id: task for task in plan.tasks}
        for endpoint in catalog:
            if not endpoint.key.model_family.startswith("addon_"):
                continue
            if endpoint.status != CatalogStatus.DATA_AVAILABLE:
                continue
            dependency_tasks = tuple(
                task
                for task in plan.for_endpoint(endpoint.endpoint_id)
                if task.stage == "reference_dependency"
            )
            self.assertEqual(len(dependency_tasks), 1)
            dependency = dependency_tasks[0]
            self.assertEqual(len(dependency.dependencies), 1)
            upstream = task_index[dependency.dependencies[0]]
            self.assertEqual(upstream.endpoint_id, endpoint.matched_reference_endpoint_id)
            self.assertIn(upstream.stage, {"source_resolver", "formal_source_evaluation"})

    def test_missing_formal_source_closes_sensitive_endpoint_instead_of_raising(self) -> None:
        config = make_workflow(
            WorkflowOverrides(
                scales=(SCALE_IDS[0],),
                models=("reference_fiber",),
            )
        )
        catalog = build_endpoint_catalog(config, synthetic_study())
        formal = next(endpoint for endpoint in catalog if endpoint.connectome_role == "formal")
        sensitive = next(endpoint for endpoint in catalog if endpoint.connectome_role == "sensitive")
        modified = tuple(
            dataclasses.replace(
                endpoint,
                subject_ids=endpoint.subject_ids[:1],
                status=CatalogStatus.INSUFFICIENT_SUBJECTS,
            )
            if endpoint.endpoint_id == formal.endpoint_id
            else endpoint
            for endpoint in catalog
        )
        plan = compile_execution_plan(config, modified)
        self.assertEqual(
            {task.stage for task in plan.for_endpoint(sensitive.endpoint_id)},
            {"catalog_terminal", "terminal_report"},
        )

    def test_reference_scale_rows_receive_identical_stage_classes(self) -> None:
        _config, catalog, plan = self._plan()
        stages_by_scale: dict[str, set[tuple[str, str]]] = {}
        for scale_id in SCALE_IDS:
            stages_by_scale[scale_id] = {
                (task.model_family, task.stage)
                for endpoint in catalog
                if endpoint.key.scale_id == scale_id
                and endpoint.key.model_family.startswith("reference_")
                for task in plan.for_endpoint(endpoint.endpoint_id)
            }
        self.assertEqual(stages_by_scale[SCALE_IDS[0]], stages_by_scale[SCALE_IDS[1]])


if __name__ == "__main__":
    unittest.main()
