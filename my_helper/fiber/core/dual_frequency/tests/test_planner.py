"""Round-aware DAG compilation tests without scientific model execution."""

from __future__ import annotations

import dataclasses
import unittest

from dual_frequency.catalog import CatalogStatus, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides
from dual_frequency.contracts import RESAMPLING_REPLICATE_BLOCK_SIZE
from dual_frequency.workflow import PlanningError, compile_execution_plan

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

    def test_task_recovery_policy_is_non_scientific_and_explicit(self) -> None:
        _config, _catalog, plan = self._plan()
        task = plan.tasks[0]
        with_policy = dataclasses.replace(
            task,
            timeout_seconds=30,
            transient_safe=True,
            max_transient_retries=2,
        )

        self.assertEqual(task.task_id, with_policy.task_id)
        self.assertEqual(task.key, with_policy.key)
        self.assertIsNone(task.timeout_seconds)
        self.assertFalse(task.transient_safe)
        self.assertEqual(task.max_transient_retries, 0)
        self.assertEqual(with_policy.timeout_seconds, 30.0)
        self.assertTrue(with_policy.transient_safe)
        self.assertEqual(with_policy.max_transient_retries, 2)

    def test_task_recovery_policy_rejects_unsafe_values(self) -> None:
        _config, _catalog, plan = self._plan()
        task = plan.tasks[0]
        invalid = (
            ({"timeout_seconds": 0}, "finite and positive"),
            ({"timeout_seconds": float("inf")}, "finite and positive"),
            ({"timeout_seconds": True}, "finite and positive"),
            ({"transient_safe": "yes"}, "must be boolean"),
            ({"max_transient_retries": -1}, "nonnegative integer"),
            ({"max_transient_retries": 1}, "transient_safe"),
            (
                {"checkpoint_only": True, "timeout_seconds": 1},
                "checkpoint-only",
            ),
        )
        for changes, message in invalid:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(PlanningError, message):
                    dataclasses.replace(task, **changes)

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
            "formal_in_sample",
            "activation_sensitivity",
            "spatial_jitter",
        }
        for endpoint_id in sensitive_ids:
            stages = {task.stage for task in plan.for_endpoint(endpoint_id)}
            self.assertTrue(stages.isdisjoint(forbidden))
            if stages:
                self.assertIn("formal_source_evaluation", stages)

    def test_only_formal_fiber_finals_schedule_ppam_observed_as_expensive(self) -> None:
        _config, catalog, plan = self._plan()
        roles = {endpoint.endpoint_id: endpoint.connectome_role for endpoint in catalog}
        expensive = tuple(task for task in plan.tasks if task.expensive_producer)
        self.assertTrue(expensive)
        self.assertTrue(
            all(task.stage == "ppam_observed_workspace" for task in expensive)
        )
        self.assertTrue(
            all(
                task.service_id == "prepare_ppam_observed_workspace"
                for task in expensive
            )
        )
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
            aggregate = endpoint_tasks["activation_sensitivity"]
            self.assertEqual(aggregate.service_id, "aggregate_ppam_activation")
            self.assertFalse(aggregate.expensive_producer)

    def test_ppam_activation_uses_observed_schedule_block_aggregate_dag(self) -> None:
        config, catalog, plan = self._plan()
        serial_services = {
            "run_reference_fiber_activation",
            "run_addon_fiber_activation",
        }
        self.assertTrue(
            serial_services.isdisjoint(task.service_id for task in plan.tasks)
        )
        expected_count = (
            config.normative_fiber.oss.permutation_resamples
            + RESAMPLING_REPLICATE_BLOCK_SIZE
            - 1
        ) // RESAMPLING_REPLICATE_BLOCK_SIZE
        for endpoint in catalog:
            if (
                endpoint.status != CatalogStatus.DATA_AVAILABLE
                or endpoint.connectome_role != "formal"
                or not endpoint.key.model_family.endswith("fiber")
            ):
                continue
            tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            observed = tasks["ppam_observed_workspace"]
            schedule = tasks["ppam_permutation_schedule"]
            aggregate = tasks["activation_sensitivity"]
            blocks = tuple(
                task
                for task in tasks.values()
                if task.stage.startswith("ppam_permutation_block_")
            )
            self.assertEqual(
                observed.service_id,
                "prepare_ppam_observed_workspace",
            )
            self.assertEqual(
                observed.output_record_type,
                "PPAMObservedWorkspaceRecord",
            )
            self.assertTrue(observed.expensive_producer)
            self.assertTrue(observed.cache_first_expensive)
            self.assertEqual(
                {gate.fact for gate in observed.gates},
                {"final_model_realized", "formal_complete"},
            )
            self.assertEqual(
                schedule.service_id,
                "prepare_ppam_permutation_schedule",
            )
            self.assertEqual(schedule.output_record_type, "ResamplingScheduleRecord")
            self.assertIn(observed.task_id, schedule.dependencies)
            self.assertEqual(
                {gate.fact for gate in schedule.gates},
                {
                    "final_model_realized",
                    "formal_complete",
                    "ppam_permutation_ready",
                },
            )
            self.assertEqual(len(blocks), expected_count)
            for block_index, block in enumerate(
                sorted(blocks, key=lambda item: item.stage)
            ):
                self.assertEqual(block.service_id, "run_ppam_permutation_block")
                self.assertEqual(
                    block.output_record_type,
                    "PPAMPermutationBlockRecord",
                )
                self.assertEqual(
                    block.execution_parameters,
                    (("block_index", str(block_index)),),
                )
                self.assertTrue(
                    {observed.task_id, schedule.task_id}
                    <= set(block.dependencies)
                )
                self.assertEqual(
                    {gate.fact for gate in block.gates},
                    {
                        "final_model_realized",
                        "formal_complete",
                        "ppam_permutation_ready",
                    },
                )
            self.assertEqual(aggregate.service_id, "aggregate_ppam_activation")
            self.assertEqual(aggregate.output_record_type, "ActivationArtifact")
            self.assertTrue(
                {
                    observed.task_id,
                    schedule.task_id,
                    *(block.task_id for block in blocks),
                }
                <= set(aggregate.dependencies)
            )
            self.assertEqual(
                {gate.fact for gate in aggregate.gates},
                {"final_model_realized", "formal_complete"},
            )
            self.assertNotIn(
                "ppam_permutation_ready",
                {gate.fact for gate in aggregate.gates},
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

    def test_adjusted_bootstrap_closure_includes_matched_reference_inputs(self) -> None:
        _config, catalog, plan = self._plan()
        task_index = {task.task_id: task for task in plan.tasks}
        endpoint_index = {endpoint.endpoint_id: endpoint for endpoint in catalog}
        for endpoint in catalog:
            if (
                endpoint.status != CatalogStatus.DATA_AVAILABLE
                or not endpoint.key.model_family.startswith("addon_")
                or endpoint.connectome_role == "sensitive"
            ):
                continue
            endpoint_tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            bootstrap = endpoint_tasks["formal_bootstrap"]
            dependency = endpoint_tasks["reference_dependency"]
            reference = endpoint_index[endpoint.matched_reference_endpoint_id]
            reference_tasks = {
                task.stage: task for task in plan.for_endpoint(reference.endpoint_id)
            }
            required = {
                endpoint_tasks["input_readiness"].task_id,
                endpoint_tasks["prepare_exposure"].task_id,
                endpoint_tasks["delta_reference_input"].task_id,
                endpoint_tasks["final_realization"].task_id,
                dependency.task_id,
                reference_tasks["input_readiness"].task_id,
                reference_tasks["prepare_exposure"].task_id,
            }
            schedule = endpoint_tasks["formal_bootstrap_schedule"]
            blocks = tuple(
                task
                for task in endpoint_tasks.values()
                if task.stage.startswith("formal_bootstrap_block_")
            )
            self.assertEqual(set(schedule.dependencies), required)
            for block in blocks:
                self.assertEqual(
                    set(block.dependencies),
                    {*required, schedule.task_id},
                )
            self.assertEqual(
                set(bootstrap.dependencies),
                {
                    *required,
                    schedule.task_id,
                    *(block.task_id for block in blocks),
                },
            )
            self.assertEqual(
                task_index[dependency.dependencies[0]].endpoint_id,
                reference.endpoint_id,
            )

    def test_formal_in_sample_is_default_and_depends_on_endpoint_loocv(self) -> None:
        _config, catalog, plan = self._plan()
        for endpoint in catalog:
            tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if not tasks or endpoint.connectome_role == "sensitive":
                continue
            in_sample = tasks["formal_in_sample"]
            self.assertEqual(in_sample.phase, "formal")
            self.assertIn(tasks["formal_permutation"].task_id, in_sample.dependencies)
            self.assertIn(tasks["final_realization"].task_id, in_sample.dependencies)

    def test_formal_permutation_uses_fixed_schedule_workspace_block_dag(self) -> None:
        config, catalog, plan = self._plan()
        serial_services = {
            "run_addon_fiber_formal_permutation",
            "run_addon_voxel_formal_permutation",
            "run_reference_fiber_formal_permutation",
            "run_reference_voxel_formal_permutation",
        }
        self.assertTrue(
            serial_services.isdisjoint(task.service_id for task in plan.tasks)
        )
        for endpoint in catalog:
            if (
                endpoint.status != CatalogStatus.DATA_AVAILABLE
                or endpoint.connectome_role == "sensitive"
            ):
                continue
            tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if "formal_permutation" not in tasks:
                continue
            profile = (
                config.normative_fiber.formal_resampling
                if endpoint.key.model_family.endswith("fiber")
                else config.direct_voxel.formal_resampling
            )
            expected_count = (
                profile.permutation_resamples
                + RESAMPLING_REPLICATE_BLOCK_SIZE
                - 1
            ) // RESAMPLING_REPLICATE_BLOCK_SIZE
            schedule = tasks["formal_permutation_schedule"]
            workspace = tasks["formal_operator_workspace"]
            aggregate = tasks["formal_permutation"]
            blocks = tuple(
                task
                for task in tasks.values()
                if task.stage.startswith("formal_permutation_block_")
            )
            self.assertEqual(
                schedule.service_id,
                "prepare_formal_permutation_schedule",
            )
            self.assertEqual(schedule.output_record_type, "ResamplingScheduleRecord")
            self.assertEqual(
                workspace.service_id,
                "prepare_formal_operator_workspace",
            )
            self.assertEqual(
                workspace.output_record_type,
                "FormalOperatorScratchRecord",
            )
            self.assertEqual(len(blocks), expected_count)
            for block_index, block in enumerate(
                sorted(blocks, key=lambda item: item.stage)
            ):
                self.assertEqual(block.service_id, "run_formal_permutation_block")
                self.assertEqual(block.output_record_type, "ResamplingBlockRecord")
                self.assertEqual(
                    block.execution_parameters,
                    (("block_index", str(block_index)),),
                )
                self.assertTrue(
                    {schedule.task_id, workspace.task_id}
                    <= set(block.dependencies)
                )
                self.assertEqual(
                    set(schedule.dependencies),
                    set(block.dependencies) - {schedule.task_id, workspace.task_id},
                )
            self.assertEqual(aggregate.service_id, "aggregate_formal_permutation")
            self.assertEqual(aggregate.output_record_type, "FormalResult")
            self.assertTrue(
                {
                    schedule.task_id,
                    workspace.task_id,
                    *(block.task_id for block in blocks),
                }
                <= set(aggregate.dependencies)
            )
            self.assertEqual(
                set(schedule.dependencies),
                set(aggregate.dependencies)
                - {
                    schedule.task_id,
                    workspace.task_id,
                    *(block.task_id for block in blocks),
                },
            )

    def test_formal_bootstrap_uses_fixed_schedule_block_dag(self) -> None:
        config, catalog, plan = self._plan()
        serial_services = {
            "run_addon_fiber_formal_bootstrap",
            "run_addon_voxel_formal_bootstrap",
            "run_reference_fiber_formal_bootstrap",
            "run_reference_voxel_formal_bootstrap",
        }
        self.assertTrue(
            serial_services.isdisjoint(task.service_id for task in plan.tasks)
        )
        for endpoint in catalog:
            if (
                endpoint.status != CatalogStatus.DATA_AVAILABLE
                or endpoint.connectome_role == "sensitive"
            ):
                continue
            tasks = {
                task.stage: task for task in plan.for_endpoint(endpoint.endpoint_id)
            }
            if "formal_bootstrap" not in tasks:
                continue
            profile = (
                config.normative_fiber.formal_resampling
                if endpoint.key.model_family.endswith("fiber")
                else config.direct_voxel.formal_resampling
            )
            expected_count = (
                profile.bootstrap_resamples
                + RESAMPLING_REPLICATE_BLOCK_SIZE
                - 1
            ) // RESAMPLING_REPLICATE_BLOCK_SIZE
            schedule = tasks["formal_bootstrap_schedule"]
            aggregate = tasks["formal_bootstrap"]
            blocks = tuple(
                task
                for task in tasks.values()
                if task.stage.startswith("formal_bootstrap_block_")
            )
            self.assertEqual(
                schedule.service_id,
                "prepare_formal_bootstrap_schedule",
            )
            self.assertEqual(schedule.output_record_type, "ResamplingScheduleRecord")
            self.assertEqual(len(blocks), expected_count)
            for block_index, block in enumerate(
                sorted(blocks, key=lambda item: item.stage)
            ):
                self.assertEqual(block.service_id, "run_formal_bootstrap_block")
                self.assertEqual(block.output_record_type, "BootstrapBlockRecord")
                self.assertEqual(
                    block.execution_parameters,
                    (("block_index", str(block_index)),),
                )
                self.assertEqual(
                    set(block.dependencies),
                    {*schedule.dependencies, schedule.task_id},
                )
            self.assertEqual(
                aggregate.service_id,
                "aggregate_formal_bootstrap",
            )
            self.assertEqual(aggregate.output_record_type, "FormalResult")
            self.assertEqual(
                set(aggregate.dependencies),
                {
                    *schedule.dependencies,
                    schedule.task_id,
                    *(block.task_id for block in blocks),
                },
            )

    def test_downstream_scientific_tasks_receive_direct_typed_input_closure(self) -> None:
        _config, catalog, plan = self._plan()
        final_linked_stages = {
            "formal_permutation",
            "formal_bootstrap",
            "formal_in_sample",
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
