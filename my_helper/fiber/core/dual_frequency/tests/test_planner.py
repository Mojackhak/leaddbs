"""Round-aware DAG compilation tests without scientific model execution."""

from __future__ import annotations

import dataclasses
import unittest

from dual_frequency.catalog import CatalogStatus, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides
from dual_frequency.workflow import compile_execution_plan

try:
    from .test_catalog import SCALE_IDS, make_workflow, synthetic_study
except ImportError:  # unittest discovery loads this module without a package name
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
            if stages:
                self.assertIn("formal_source_evaluation", stages)

    def test_only_formal_fiber_finals_schedule_activation_as_expensive(self) -> None:
        _config, catalog, plan = self._plan()
        roles = {endpoint.endpoint_id: endpoint.connectome_role for endpoint in catalog}
        expensive = tuple(task for task in plan.tasks if task.expensive_producer)
        self.assertTrue(expensive)
        self.assertTrue(all(task.stage == "activation_sensitivity" for task in expensive))
        self.assertTrue(all(task.model_family.endswith("fiber") for task in expensive))
        self.assertTrue(all(roles[task.endpoint_id] == "formal" for task in expensive))
        self.assertTrue(all(task.cache_first_expensive for task in expensive))
        for task in expensive:
            endpoint_tasks = {
                candidate.stage: candidate
                for candidate in plan.for_endpoint(task.endpoint_id)
            }
            self.assertIn(
                endpoint_tasks["final_realization"].task_id,
                task.dependencies,
            )

    def test_unavailable_endpoint_has_no_tasks_without_blocking_other_scales(self) -> None:
        _config, catalog, plan = self._plan()
        unavailable = {
            endpoint.endpoint_id
            for endpoint in catalog
            if endpoint.status != CatalogStatus.DATA_AVAILABLE
        }
        self.assertTrue(unavailable)
        for endpoint_id in unavailable:
            self.assertEqual(plan.for_endpoint(endpoint_id), ())
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

    def test_scientific_tasks_use_explicit_input_and_prepared_exposure_records(self) -> None:
        _config, catalog, plan = self._plan()
        for endpoint in catalog:
            endpoint_tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if not endpoint_tasks:
                continue
            readiness = endpoint_tasks["input_readiness"]
            prepare = endpoint_tasks["prepare_exposure"]
            self.assertEqual(readiness.output_record_type, "EndpointInputRecord")
            self.assertEqual(prepare.output_record_type, "PreparedExposureRecord")
            self.assertIn("endpoint_input_ready", {gate.fact for gate in prepare.gates})
            for task in endpoint_tasks.values():
                if task.stage == "observed_grid" or task.stage.startswith("branch_"):
                    self.assertIn(readiness.task_id, task.dependencies)
                    self.assertIn(
                        "endpoint_input_ready",
                        {gate.fact for gate in task.gates},
                    )
                if task.stage == "branch_no_delta_observed":
                    gate_facts = {gate.fact for gate in task.gates}
                    self.assertEqual(
                        gate_facts,
                        {"endpoint_input_ready", "reference_dependency_ready"},
                    )

            if endpoint.key.model_family.startswith("addon_"):
                delta = endpoint_tasks["delta_reference_input"]
                no_delta = endpoint_tasks["branch_no_delta_observed"]
                self.assertNotIn(delta.task_id, no_delta.dependencies)
                self.assertTrue(
                    {
                        readiness.task_id,
                        endpoint_tasks["reference_dependency"].task_id,
                        prepare.task_id,
                    }
                    <= set(delta.dependencies)
                )
                self.assertEqual(
                    {gate.fact for gate in delta.gates},
                    {
                        "endpoint_input_ready",
                        "reference_dependency_ready",
                        "reference_source_accepted",
                    },
                )

    def test_addon_final_receives_reference_delta_and_both_branch_states(self) -> None:
        _config, catalog, plan = self._plan()
        for endpoint in catalog:
            if endpoint.connectome_role == "sensitive":
                continue
            endpoint_tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if "final_realization" not in endpoint_tasks or not endpoint.key.model_family.startswith(
                "addon_"
            ):
                continue
            final = endpoint_tasks["final_realization"]
            self.assertEqual(final.output_record_type, "FinalSelectionRecord")
            self.assertEqual(final.gates, ())
            required_stages = {
                "input_readiness",
                "reference_dependency",
                "delta_reference_input",
                "branch_no_delta_observed",
                "branch_delta_adjusted_observed",
            }
            self.assertEqual(
                set(final.dependencies),
                {endpoint_tasks[stage].task_id for stage in required_stages},
            )

    def test_downstream_scientific_tasks_receive_direct_typed_input_closure(self) -> None:
        _config, catalog, plan = self._plan()
        final_linked_stages = {
            "formal_permutation",
            "formal_bootstrap",
            "spatial_jitter",
            "selected_source_neighborhood",
            "activation_sensitivity",
        }
        for endpoint in catalog:
            endpoint_tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if not endpoint_tasks:
                continue
            readiness = endpoint_tasks["input_readiness"]
            prepare = endpoint_tasks["prepare_exposure"]
            downstream = tuple(
                task
                for task in endpoint_tasks.values()
                if task.phase in {"formal", "sensitivity"}
                or task.stage == "formal_source_evaluation"
            )
            self.assertTrue(downstream)
            for task in downstream:
                with self.subTest(endpoint=endpoint.endpoint_id, stage=task.stage):
                    self.assertTrue(
                        {readiness.task_id, prepare.task_id}
                        <= set(task.dependencies)
                    )
                    if endpoint.key.model_family.startswith("addon_"):
                        self.assertIn(
                            endpoint_tasks["delta_reference_input"].task_id,
                            task.dependencies,
                        )
                    if task.stage in final_linked_stages:
                        self.assertIn(
                            endpoint_tasks["final_realization"].task_id,
                            task.dependencies,
                        )
                    if (
                        endpoint.key.model_family.startswith("addon_")
                        and task.stage
                        in {
                            "cheap_observed_sensitivity",
                            "additional_sensitivities",
                        }
                    ):
                        self.assertIn(
                            endpoint_tasks["final_realization"].task_id,
                            task.dependencies,
                        )

    def test_all_final_realization_tasks_return_typed_selection_records(self) -> None:
        _config, _catalog, plan = self._plan()
        finals = tuple(task for task in plan.tasks if task.stage == "final_realization")
        self.assertTrue(finals)
        self.assertTrue(
            all(task.output_record_type == "FinalSelectionRecord" for task in finals)
        )
        self.assertTrue(all(not task.gates for task in finals))
        self.assertFalse(
            any(task.output_record_type == "FinalModelRecord" for task in plan.tasks)
        )

    def test_report_cutoff_schedules_no_report_or_catalog_terminal_tasks(self) -> None:
        _config, _catalog, plan = self._plan(through="report")
        self.assertTrue(plan.tasks)
        self.assertFalse(any(task.phase == "report" for task in plan.tasks))
        self.assertFalse(
            any(task.stage in {"report", "terminal_report", "catalog_terminal"} for task in plan.tasks)
        )
        self.assertFalse(
            any(task.output_record_type in {"ReportArtifact", "EndpointTerminalRecord"} for task in plan.tasks)
        )

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
        self.assertEqual(plan.for_endpoint(sensitive.endpoint_id), ())

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

    def test_every_non_deferred_round_is_represented_without_implicit_round_2b(self) -> None:
        _config, catalog, plan = self._plan()
        expected = {
            "reference_voxel": {
                "round_0", "round_1", "round_2", "round_4",
                "round_5", "round_6", "round_7",
            },
            "addon_voxel": {
                "round_0", "round_1", "round_2", "round_4",
                "round_5", "round_6", "round_7", "round_8",
            },
            "reference_fiber": {
                "round_0", "round_1", "round_2", "round_3",
                "round_5", "round_5_5", "round_6", "round_7", "round_8",
            },
            "addon_fiber": {
                "round_0", "round_1", "round_2", "round_3",
                "round_5", "round_6", "round_7", "round_8", "round_9",
            },
        }
        for family, expected_rounds in expected.items():
            endpoint = next(
                item
                for item in catalog
                if item.key.scale_id == SCALE_IDS[0]
                and item.key.model_family == family
                and item.connectome_role in {"none", "formal"}
            )
            actual = {task.round_id for task in plan.for_endpoint(endpoint.endpoint_id)}
            self.assertEqual(actual, expected_rounds)
        self.assertFalse(any(task.round_id == "round_2b" for task in plan.tasks))
        self.assertFalse(any("optional" in task.round_id for task in plan.tasks))
        self.assertFalse(
            any(
                "equivalence" in task.service_id or "smoke_resampling" in task.service_id
                for task in plan.tasks
            )
        )


if __name__ == "__main__":
    unittest.main()
