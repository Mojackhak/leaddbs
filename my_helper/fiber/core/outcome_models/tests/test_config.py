"""Tests for strict four-model YAML configuration loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from outcome_models.config import ConfigurationError, WorkflowOverrides, load_resolved_workflow
from outcome_models.tests.helpers import write_profile_bundle


class ConfigLoadingTests(unittest.TestCase):
    def test_valid_bundle_loads_typed_profiles_and_stable_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_path = write_profile_bundle(root)
            first = load_resolved_workflow(workflow_path, WorkflowOverrides())
            second = load_resolved_workflow(workflow_path, WorkflowOverrides())

            self.assertEqual(first.study.study_id, "synthetic_study")
            self.assertEqual(first.scales[0].scale_id, "scale_one")
            self.assertEqual(first.model.profile_id, "four_model_v1")
            self.assertEqual(first.model.direct_candidate_threshold_v_per_m, 100.0)
            self.assertEqual(
                first.model.normative_fiber["cheap_observed_sensitivity"],
                {
                    "high_tau_v_per_m": 1500,
                    "coverage": 5,
                    "sweet_top_count": 1500,
                    "sour_top_count": 500,
                },
            )
            self.assertEqual(first.workflow.selection.scales, ("scale_one",))
            self.assertEqual(first.configuration_hash, second.configuration_hash)
            self.assertEqual(len(first.configuration_hash), 64)

    def test_unknown_nested_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["study"]["paths"].update({"roi": "/tmp/roi.nii"}),
            )
            with self.assertRaisesRegex(ConfigurationError, "roi"):
                load_resolved_workflow(path, WorkflowOverrides())

    def test_duplicate_yaml_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_profile_bundle(root)
            text = (root / "workflow.yaml").read_text(encoding="utf-8")
            (root / "workflow.yaml").write_text(text + "schema_version: four_model_v1\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "duplicate key.*schema_version"):
                load_resolved_workflow(path, WorkflowOverrides())

    def test_scale_selection_is_required_and_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["workflow"]["selection"].pop("scales"),
            )
            with self.assertRaisesRegex(ConfigurationError, "scales|all_available"):
                load_resolved_workflow(missing, WorkflowOverrides())

        with tempfile.TemporaryDirectory() as tmp:
            conflict = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["workflow"]["selection"].update({"all_available": True}),
            )
            with self.assertRaisesRegex(ConfigurationError, "mutually exclusive"):
                load_resolved_workflow(conflict, WorkflowOverrides())

    def test_scale_contract_rejects_unknown_direction_and_threshold_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            direction = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["scales"]["scales"][0].update({"direction": "unknown"}),
            )
            with self.assertRaisesRegex(ConfigurationError, "direction"):
                load_resolved_workflow(direction, WorkflowOverrides())

        with tempfile.TemporaryDirectory() as tmp:
            minimum = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["scales"]["scales"][0].update({"minimum_subjects": 11}),
            )
            with self.assertRaisesRegex(ConfigurationError, "minimum_subjects"):
                load_resolved_workflow(minimum, WorkflowOverrides())

    def test_hidden_public_fields_are_rejected(self) -> None:
        hidden_fields = [
            "candidate_threshold_v_per_m",
            "smoke",
            "smoke_iterations",
            "primary_scale",
            "first_pass_scale",
            "axial_special",
            "atlas",
            "roi",
            "postprocessing",
        ]
        for hidden in hidden_fields:
            with self.subTest(hidden=hidden), tempfile.TemporaryDirectory() as tmp:
                path = write_profile_bundle(
                    Path(tmp),
                    mutate=lambda profiles, field=hidden: profiles["model"].update({field: True}),
                )
                with self.assertRaisesRegex(ConfigurationError, hidden):
                    load_resolved_workflow(path, WorkflowOverrides())

    def test_cli_overrides_cannot_select_scales_and_all_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile_bundle(Path(tmp))
            with self.assertRaisesRegex(ConfigurationError, "mutually exclusive"):
                load_resolved_workflow(
                    path,
                    WorkflowOverrides(scales=("scale_one",), all_available=True),
                )

    def test_pre_specified_cells_must_belong_to_declared_grids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["model"]["direct_voxel"].update(
                    {"pre_specified_tau_v_per_m": 175}
                ),
            )
            with self.assertRaisesRegex(ConfigurationError, "pre_specified_tau_v_per_m.*tau_grid"):
                load_resolved_workflow(path, WorkflowOverrides())

    def test_selected_connectomes_must_exist_in_study_and_model_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["workflow"]["selection"].update(
                    {"connectomes": ["missing_connectome"]}
                ),
            )
            with self.assertRaisesRegex(ConfigurationError, "unknown selected connectome"):
                load_resolved_workflow(path, WorkflowOverrides())

    def test_all_model_selector_cannot_be_combined_with_specific_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile_bundle(
                Path(tmp),
                mutate=lambda profiles: profiles["workflow"]["selection"].update(
                    {"models": ["all", "hf-voxel"]}
                ),
            )
            with self.assertRaisesRegex(ConfigurationError, "model selector.*all"):
                load_resolved_workflow(path, WorkflowOverrides())


if __name__ == "__main__":
    unittest.main()
