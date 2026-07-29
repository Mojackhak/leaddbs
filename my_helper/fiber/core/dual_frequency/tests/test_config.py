"""Strict public-profile validation tests."""

from __future__ import annotations

import copy
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import yaml

from dual_frequency.config import ConfigurationError, WorkflowOverrides, load_workflow


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONFIG_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"


class ConfigTest(unittest.TestCase):
    def test_loads_approved_production_profiles(self) -> None:
        resolved = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True),
        )
        self.assertEqual(len(resolved.selected_scales), 28)
        self.assertEqual(resolved.direct_voxel.direct_candidate_threshold_v_per_m, 150.0)
        self.assertEqual(resolved.normative_fiber.formal_connectome.role, "formal")
        self.assertEqual(
            resolved.normative_fiber.formal_connectome.connectome_id,
            "ppmi_85_ewert_2017",
        )
        self.assertTrue(
            all(item.fold_candidate_fibers_min == 1 for item in resolved.normative_fiber.connectomes)
        )
        self.assertEqual(resolved.normative_fiber.hard_computability.n_subjects_min, 12)
        self.assertEqual(resolved.workflow.execution.workers, 3)
        self.assertFalse(resolved.workflow.storage.delete_run_cache_on_success)
        self.assertEqual(len(resolved.configuration_hash), 64)
        self.assertEqual(len(resolved.scientific_configuration_hash), 64)
        with self.assertRaises(FrozenInstanceError):
            resolved.selected_scales = ()

    def test_production_source_profiles_have_required_semantics(self) -> None:
        workflow = self._workflow_document()
        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        self.assertEqual(
            workflow["model_profiles"],
            {
                "direct_voxel": "direct_voxel_model.yaml",
                "normative_fiber": "normative_fiber_model.yaml",
            },
        )
        self.assertFalse(workflow["storage"]["delete_run_cache_on_success"])

        direct_source = direct["shared"]["source"]
        self.assertEqual(
            direct_source["pre_specified"],
            {"tau_v_per_m": 200, "coverage_subjects_min": 5},
        )
        self.assertEqual(
            direct_source["scan"]["tau_v_per_m"],
            [150, 180, 200, 220, 250, 300],
        )
        self.assertEqual(
            direct_source["scan"]["coverage_subjects_min"],
            [5, 6, 7, 8, 10, 12],
        )
        self.assertEqual(
            direct["shared"]["hard_computability"]["n_subjects_min"],
            12,
        )

        fiber_source = fiber["source"]
        self.assertEqual(
            fiber_source["pre_specified"],
            {"tau_v_per_m": 400, "coverage_subjects_min": 5},
        )
        self.assertEqual(
            fiber_source["scan"]["tau_v_per_m"],
            [200, 350, 400, 450, 600, 800],
        )
        self.assertEqual(
            fiber_source["scan"]["coverage_subjects_min"],
            [5, 6, 7, 8, 10, 12],
        )
        self.assertEqual(fiber["hard_computability"]["n_subjects_min"], 12)
        self.assertEqual(
            [
                entry["fold_candidate_fibers_min"]
                for entry in fiber["connectomes"]["entries"]
            ],
            [1, 1, 1],
        )

    def test_requires_explicit_scale_selection(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "--scale or --all-available"):
            load_workflow(CONFIG_ROOT / "workflow.yaml")
        with self.assertRaisesRegex(ConfigurationError, "mutually exclusive"):
            load_workflow(
                CONFIG_ROOT / "workflow.yaml",
                WorkflowOverrides(scales=("mds_updrs_iii_score",), all_available=True),
            )

    def test_scale_override_is_validated_and_ordered(self) -> None:
        resolved = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(scales=("mds_updrs_iv", "mds_updrs_iii_score")),
        )
        self.assertEqual(resolved.selected_scales, ("mds_updrs_iv", "mds_updrs_iii_score"))
        with self.assertRaisesRegex(ConfigurationError, "unknown selected scale"):
            load_workflow(
                CONFIG_ROOT / "workflow.yaml",
                WorkflowOverrides(scales=("missing_scale",)),
            )

    def test_workers_override_is_validated(self) -> None:
        resolved = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True, workers=2),
        )
        self.assertEqual(resolved.workflow.execution.workers, 2)
        with self.assertRaisesRegex(ConfigurationError, "workers must be positive"):
            load_workflow(
                CONFIG_ROOT / "workflow.yaml",
                WorkflowOverrides(all_available=True, workers=0),
            )

    def test_cache_cleanup_policy_is_explicit_and_nonscientific(self) -> None:
        original = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True),
        )
        omitted_workflow = self._workflow_document()
        del omitted_workflow["storage"]["delete_run_cache_on_success"]
        cleanup_default = self._load_modified_profiles(workflow=omitted_workflow)
        workflow = self._workflow_document()
        workflow["storage"]["delete_run_cache_on_success"] = True
        cleanup_enabled = self._load_modified_profiles(workflow=workflow)
        self.assertFalse(original.workflow.storage.delete_run_cache_on_success)
        self.assertTrue(cleanup_default.workflow.storage.delete_run_cache_on_success)
        self.assertTrue(cleanup_enabled.workflow.storage.delete_run_cache_on_success)
        self.assertNotEqual(
            original.configuration_hash,
            cleanup_enabled.configuration_hash,
        )
        self.assertEqual(
            original.scientific_configuration_hash,
            cleanup_enabled.scientific_configuration_hash,
        )

    def test_override_types_and_selector_uniqueness_are_strict(self) -> None:
        invalid_overrides = (
            (WorkflowOverrides(all_available=True, through="bogus"), "override through"),
            (WorkflowOverrides(all_available=True, resume="false"), "resume must be boolean"),
            (WorkflowOverrides(all_available=True, workers=1.9), "workers must be an integer"),
            (
                WorkflowOverrides(
                    all_available=True,
                    models=("reference_voxel", "reference_voxel"),
                ),
                "models values must be unique",
            ),
        )
        for overrides, message in invalid_overrides:
            with self.subTest(message=message), self.assertRaisesRegex(ConfigurationError, message):
                load_workflow(CONFIG_ROOT / "workflow.yaml", overrides)

    def test_fiber_selection_requires_the_formal_connectome(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "must include the configured formal"):
            load_workflow(
                CONFIG_ROOT / "workflow.yaml",
                WorkflowOverrides(
                    all_available=True,
                    models=("reference_fiber",),
                    connectomes=("dtor_985_full_elias_2024",),
                ),
            )
        voxel_only = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(
                all_available=True,
                models=("reference_voxel",),
                connectomes=("ppmi_85_ewert_2017",),
            ),
        )
        self.assertEqual(voxel_only.selected_connectomes, ("ppmi_85_ewert_2017",))

    def test_test_profiles_share_the_same_cross_profile_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workflow = self._workflow_document()
            workflow["model_profiles"] = {
                "direct_voxel": str(CONFIG_ROOT / "direct_voxel_model_test.yaml"),
                "normative_fiber": str(CONFIG_ROOT / "normative_fiber_model_test.yaml"),
            }
            path = Path(temporary_directory) / "workflow.yaml"
            path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
            resolved = load_workflow(path, WorkflowOverrides(all_available=True))
        self.assertEqual(resolved.selected_scales, ("mds_updrs_iii_score", "mds_updrs_iv"))
        self.assertEqual(resolved.normative_fiber.formal_connectome.connectome_id, "ppmi_85_ewert_2017")

    def test_rejects_hidden_and_unknown_model_fields(self) -> None:
        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        direct["shared"]["source"]["candidate_threshold_v_per_m"] = 100
        with self.assertRaisesRegex(ConfigurationError, "candidate_threshold_v_per_m"):
            self._load_modified_profiles(direct=direct)

        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        direct["shared"]["formal_resampling"]["smoke_permutations"] = 5
        with self.assertRaisesRegex(ConfigurationError, "smoke_permutations"):
            self._load_modified_profiles(direct=direct)

    def test_rejects_changes_to_fixed_v1_oss_scientific_contract(self) -> None:
        mutations = (
            (("oss", "model"), "other"),
            (("oss", "activation_model"), "deterministic"),
            (("oss", "fiber_diameter_um", "minimum"), 1.5),
            (("oss", "fiber_diameter_um", "maximum"), 5.0),
            (("oss", "fiber_diameter_um", "samples"), 11),
            (("oss", "fitting_probability_threshold"), 0.6),
        )
        for keys, replacement in mutations:
            fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
            target = fiber
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = replacement
            with self.subTest(keys=keys), self.assertRaises(ConfigurationError):
                self._load_modified_profiles(fiber=fiber)

    def test_rejects_legacy_schema_and_project_role_aliases(self) -> None:
        workflow = self._workflow_document()
        workflow["schema_version"] = "four_model_v1"
        with self.assertRaisesRegex(ConfigurationError, "dual_frequency_workflow_v1"):
            self._load_modified_profiles(workflow=workflow)

        workflow = self._workflow_document()
        workflow["selection"]["models"] = ["frequency_1_reference"]
        with self.assertRaisesRegex(ConfigurationError, "frequency_1_reference"):
            self._load_modified_profiles(workflow=workflow)

    def test_rejects_duplicate_yaml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "workflow.yaml"
            path.write_text(
                "schema_version: dual_frequency_workflow_v1\n"
                "schema_version: dual_frequency_workflow_v1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConfigurationError, "duplicate YAML key"):
                load_workflow(path, WorkflowOverrides(all_available=True))

    def test_rejects_nonfinite_public_values(self) -> None:
        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        direct["shared"]["formal_resampling"]["jitter_translation_fwhm_mm"] = float("nan")
        with self.assertRaisesRegex(ConfigurationError, "nonfinite"):
            self._load_modified_profiles(direct=direct)

    def test_rejects_cross_profile_drift(self) -> None:
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        fiber["scales"] = list(reversed(fiber["scales"]))
        with self.assertRaisesRegex(ConfigurationError, "scale order"):
            self._load_modified_profiles(fiber=fiber)

        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        fiber["connectomes"]["entries"][1]["role"] = "formal"
        with self.assertRaisesRegex(ConfigurationError, "exactly one formal"):
            self._load_modified_profiles(fiber=fiber)

    def test_domain_specific_resampling_values_are_independent(self) -> None:
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        fiber["formal_resampling"]["permutation_resamples"] = 9000
        fiber["sensitivity"]["selected_source_tau_multipliers"] = [0.8, 1.2]
        self._load_modified_profiles(fiber=fiber)

    def test_configuration_hash_uses_normalized_typed_values(self) -> None:
        original = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True),
        )
        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        direct["shared"]["source"]["scan"]["tau_v_per_m"][0] = 150.0
        equivalent = self._load_modified_profiles(direct=direct)
        self.assertEqual(original.configuration_hash, equivalent.configuration_hash)
        self.assertEqual(
            original.scientific_configuration_hash,
            equivalent.scientific_configuration_hash,
        )

    def test_run_and_scientific_configuration_hashes_have_distinct_boundaries(self) -> None:
        original = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True),
        )
        different_workers = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True, workers=2),
        )
        self.assertNotEqual(original.configuration_hash, different_workers.configuration_hash)
        self.assertEqual(
            original.scientific_configuration_hash,
            different_workers.scientific_configuration_hash,
        )

        resume_only = load_workflow(
            CONFIG_ROOT / "workflow.yaml",
            WorkflowOverrides(all_available=True, resume=True),
        )
        self.assertEqual(original.configuration_hash, resume_only.configuration_hash)
        self.assertEqual(
            original.scientific_configuration_hash,
            resume_only.scientific_configuration_hash,
        )

        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        direct["output"]["root"] = "/tmp/alternate-output"
        fiber["output"]["root"] = "/tmp/alternate-output"
        different_output = self._load_modified_profiles(direct=direct, fiber=fiber)
        self.assertNotEqual(original.configuration_hash, different_output.configuration_hash)
        self.assertEqual(
            original.scientific_configuration_hash,
            different_output.scientific_configuration_hash,
        )

    def test_rejects_overlapping_frequency_boundary_and_reused_binding(self) -> None:
        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        for document in (direct, fiber):
            document["frequency_classes"]["addon"]["upper"] = 100
            document["frequency_classes"]["addon"]["upper_inclusive"] = True
            document["frequency_classes"]["reference"]["lower_inclusive"] = True
        with self.assertRaisesRegex(ConfigurationError, "cannot overlap"):
            self._load_modified_profiles(direct=direct, fiber=fiber)

        direct = self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml")
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        for document in (direct, fiber):
            document["endpoint_pair"]["addon"] = copy.deepcopy(document["endpoint_pair"]["reference"])
        with self.assertRaisesRegex(ConfigurationError, "must be distinct"):
            self._load_modified_profiles(direct=direct, fiber=fiber)

    def test_high_threshold_sensitivity_is_independent_of_resolver_scan(self) -> None:
        fiber = self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml")
        fiber["sensitivity"]["high_threshold"]["tau_v_per_m"] = 1750
        self._load_modified_profiles(fiber=fiber)

    @staticmethod
    def _yaml_document(path: Path) -> dict[str, object]:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def _workflow_document(self) -> dict[str, object]:
        return self._yaml_document(CONFIG_ROOT / "workflow.yaml")

    def _load_modified_profiles(
        self,
        *,
        direct: dict[str, object] | None = None,
        fiber: dict[str, object] | None = None,
        workflow: dict[str, object] | None = None,
    ):
        direct_document = copy.deepcopy(direct or self._yaml_document(CONFIG_ROOT / "direct_voxel_model.yaml"))
        fiber_document = copy.deepcopy(fiber or self._yaml_document(CONFIG_ROOT / "normative_fiber_model.yaml"))
        workflow_document = copy.deepcopy(workflow or self._workflow_document())
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            direct_path = root / "direct.yaml"
            fiber_path = root / "fiber.yaml"
            workflow_path = root / "workflow.yaml"
            direct_path.write_text(yaml.safe_dump(direct_document, sort_keys=False), encoding="utf-8")
            fiber_path.write_text(yaml.safe_dump(fiber_document, sort_keys=False), encoding="utf-8")
            workflow_document["model_profiles"] = {
                "direct_voxel": direct_path.name,
                "normative_fiber": fiber_path.name,
            }
            workflow_path.write_text(yaml.safe_dump(workflow_document, sort_keys=False), encoding="utf-8")
            return load_workflow(workflow_path, WorkflowOverrides(all_available=True))


if __name__ == "__main__":
    unittest.main()
