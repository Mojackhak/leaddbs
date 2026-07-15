"""Tests for explicit four-model profile conversion."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import yaml

from projects.stnsnr.migration.convert_four_model_v1 import (
    MigrationError,
    convert_profiles,
)


def _write_yaml(path: Path, payload: object) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _serialized_yaml(payload: object) -> str:
    return yaml.safe_dump(payload, sort_keys=True)


class FourModelMigrationTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        workflow = {
            "schema_version": "four_model_v1",
            "profile_type": "workflow",
            "study_profile": "study.yaml",
            "scale_profile": "scales.yaml",
            "model_profile": "model.yaml",
            "selection": {
                "scales": ["scale_a"],
                "phases": ["legacy_period_a", "legacy_period_b"],
                "models": ["all"],
                "connectomes": ["robust", "formal_x"],
            },
            "execution": {
                "through": "report",
                "resume": False,
                "force": False,
                "continue_on_endpoint_failure": True,
            },
        }
        study = {
            "schema_version": "four_model_v1",
            "profile_type": "study_profile",
            "study_id": "study_a",
            "paths": {
                "clinical_table": "/configured/clinical.xlsx",
                "stimulation_table": "/configured/stimulation.xlsx",
                "leaddbs_derivatives": "/configured/derivatives",
                "asset_root": "/configured/assets",
                "output_root": "/configured/output",
            },
            "clinical_columns": {
                "subject_id": "ID",
                "scale": "Scale",
                "protocol": "Protocol",
                "phase": "Visit",
                "value": "Value",
                "baseline": "Baseline",
            },
            "space": {
                "name": "space_a",
                "reference_image": "/configured/reference.nii.gz",
                "brainmask": "/configured/mask.nii.gz",
                "canonical_hemisphere": "right",
                "left_to_right_transform": "configured_transform",
            },
            "components": {
                "legacy_reference_component": {"alias": "component_a"},
                "legacy_addon_component": {"alias": "component_b"},
            },
            "conditions": {
                "legacy_reference": {"protocol": "protocol_a", "visit": "reference_visit"},
                "legacy_addon_a": {"protocol": "protocol_b", "visit": "visit_a"},
                "legacy_addon_b": {"protocol": "protocol_b", "visit": "visit_b"},
            },
            "efield_resolvers": {
                "legacy_reference_exposure": "resolver_a",
                "legacy_combined_reference_exposure": "resolver_b",
                "legacy_combined_addon_exposure": "resolver_c",
            },
            "connectomes": {
                "robust": {"label": "robust", "path": "/configured/robust.mat"},
                "formal_x": {"label": "formal", "path": "/configured/formal.mat"},
            },
        }
        scales = {
            "schema_version": "four_model_v1",
            "profile_type": "scale_profile",
            "scales": [
                {
                    "scale_id": "scale_a",
                    "label": "Scale A",
                    "direction": "lower",
                    "minimum_subjects": 12,
                    "endpoint_bindings": {
                        "legacy_reference": {"protocol": "protocol_a", "phase": "reference_visit"},
                        "legacy_addon_a": {"protocol": "protocol_b", "phase": "visit_a"},
                        "legacy_addon_b": {"protocol": "protocol_b", "phase": "visit_b"},
                    },
                }
            ],
        }
        model = {
            "schema_version": "four_model_v1",
            "profile_type": "model_profile",
            "profile_id": "four_model_v1",
            "direct_voxel": {"tau_grid_v_per_m": [100, 200]},
            "normative_fiber": {
                "tau_grid_v_per_m": [400, 800],
                "connectome_roles": {"robust": "observed_robustness", "formal_x": "formal"},
            },
            "resolver": {"minimum_adjacent_passing_cells": 2},
            "formal": {"permutations": 10, "bootstraps": 10, "jitter_resamples": 5, "seed": 42},
            "sensitivity": {
                "ulf_gain": True,
                "ulf_total_exposure": True,
            },
            "oss": {"deterministic_activation_threshold": 0.5, "final_dtor_only": True},
            "reporting": {"numeric_first": True},
        }
        for name, payload in (
            ("workflow.yaml", workflow),
            ("study.yaml", study),
            ("scales.yaml", scales),
            ("model.yaml", model),
        ):
            _write_yaml(root / name, payload)
        mapping = {
            "schema_version": "dual_frequency_migration_mapping_v1",
            "target_model_set_id": "dual_frequency_test",
            "target_endpoint_pair": {
                "baseline": {"phase_id": "T0", "program_id": 0},
                "reference": {
                    "source_condition_id": "legacy_reference",
                    "phase_id": "T2",
                    "program_id": 1,
                },
                "addon": {
                    "source_condition_id": "legacy_addon_a",
                    "phase_id": "T3",
                    "program_id": 2,
                },
            },
            "target_frequency_classes": {
                "reference": {
                    "lower": 100,
                    "lower_inclusive": False,
                    "upper": None,
                    "upper_inclusive": False,
                },
                "addon": {
                    "lower": 0,
                    "lower_inclusive": False,
                    "upper": 50,
                    "upper_inclusive": False,
                },
            },
            "source_subscale_field": "visit",
            "source_subscale_selection_field": "phases",
            "component_roles": {
                "legacy_reference_component": "reference_component",
                "legacy_addon_component": "addon_component",
            },
            "condition_roles": {
                "legacy_reference": "reference_only",
                "legacy_addon_a": "combined",
                "legacy_addon_b": "combined",
            },
            "exposure_bindings": {
                "legacy_reference_exposure": {
                    "condition_role": "reference_only",
                    "component_role": "reference_component",
                },
                "legacy_combined_reference_exposure": {
                    "condition_role": "combined",
                    "component_role": "reference_component",
                },
                "legacy_combined_addon_exposure": {
                    "condition_role": "combined",
                    "component_role": "addon_component",
                },
            },
            "subscale_bindings": {
                "legacy_reference": {
                    "endpoint_binding_suffix": "reference",
                    "condition_role": "reference_only",
                },
                "legacy_addon_a": {
                    "endpoint_binding_suffix": "combined_a",
                    "condition_role": "combined",
                },
                "legacy_addon_b": {
                    "endpoint_binding_suffix": "combined_b",
                    "condition_role": "combined",
                },
            },
            "workflow_subscale_values": {
                "legacy_period_a": "combined_a",
                "legacy_period_b": "combined_b",
            },
            "model_section_map": {"oss": "activation"},
            "model_field_map": {
                "sensitivity": {
                    "ulf_gain": "addon_gain",
                    "ulf_total_exposure": "addon_total_exposure",
                }
            },
            "drop_model_fields": ["activation.final_dtor_only"],
        }
        mapping_path = root / "mapping.yaml"
        _write_yaml(mapping_path, mapping)
        return root / "workflow.yaml", mapping_path

    def test_conversion_writes_three_review_drafts_without_a_study_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow, mapping = self._fixture(root)
            output_dir = root / "converted"
            report_path = convert_profiles(workflow, mapping, output_dir)
            target_direct = yaml.safe_load(
                (output_dir / "direct_voxel_model.yaml").read_text(encoding="utf-8")
            )
            target_normative = yaml.safe_load(
                (output_dir / "normative_fiber_model.yaml").read_text(encoding="utf-8")
            )
            target_workflow = yaml.safe_load(
                (output_dir / "workflow.yaml").read_text(encoding="utf-8")
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            output_names = {path.name for path in output_dir.iterdir()}

        self.assertEqual(
            output_names,
            {
                "conversion_report.json",
                "direct_voxel_model.yaml",
                "normative_fiber_model.yaml",
                "workflow.yaml",
            },
        )
        self.assertEqual(target_direct["profile_type"], "direct_voxel_model")
        self.assertEqual(target_normative["profile_type"], "normative_fiber_model")
        self.assertEqual(target_direct["scales"], ["scale_a"])
        self.assertEqual(target_normative["endpoint_pair"], target_direct["endpoint_pair"])
        self.assertEqual(
            [row["role"] for row in target_normative["connectomes"]["entries"]],
            ["sensitive", "formal"],
        )
        self.assertNotIn("scales", target_workflow["selection"])
        self.assertNotIn("subscales", target_workflow["selection"])
        self.assertEqual(target_workflow["direct_voxel_profile"], "direct_voxel_model.yaml")
        self.assertEqual(
            target_workflow["normative_fiber_profile"],
            "normative_fiber_model.yaml",
        )
        for payload in (target_direct, target_normative, target_workflow):
            serialized = _serialized_yaml(payload)
            self.assertNotIn("legacy_", serialized)
        self.assertEqual(report["status"], "draft_requires_review")
        self.assertFalse(report["production_loader_imported"])
        self.assertEqual(
            report["study_base"],
            {
                "required_external_input": True,
                "generated": False,
                "source_study_id": "study_a",
            },
        )
        self.assertEqual(
            report["target_profiles"],
            ["direct_voxel_model.yaml", "normative_fiber_model.yaml", "workflow.yaml"],
        )
        self.assertEqual(
            report["source_selection_evidence"]["unrepresented_source_subscale_values"],
            ["legacy_period_b"],
        )
        self.assertEqual(set(report["target_condition_evidence"]), {"reference_only", "combined"})
        bindings = report["binding_conversions"]
        reference = next(row for row in bindings if row["target_condition_id"] == "reference_only")
        combined = [row for row in bindings if row["target_condition_id"] == "combined"]
        self.assertEqual(len(combined), 2)
        self.assertEqual(
            {row["target_endpoint_binding_id"] for row in combined},
            {"scale_a__combined_a", "scale_a__combined_b"},
        )
        self.assertEqual(reference["target_endpoint_binding_id"], "scale_a__reference")

    def test_unknown_source_field_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow, mapping = self._fixture(root)
            payload = yaml.safe_load(workflow.read_text())
            payload["unexpected"] = True
            _write_yaml(workflow, payload)
            with self.assertRaisesRegex(MigrationError, "unknown.*workflow"):
                convert_profiles(workflow, mapping, root / "converted")

    def test_conflicting_combined_stimulation_definitions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow, mapping = self._fixture(root)
            study_path = root / "study.yaml"
            payload = yaml.safe_load(study_path.read_text())
            payload["conditions"]["legacy_addon_b"]["protocol"] = "conflicting_protocol"
            _write_yaml(study_path, payload)
            with self.assertRaisesRegex(MigrationError, "combined.*conflict"):
                convert_profiles(workflow, mapping, root / "converted")

    def test_conversion_refuses_to_replace_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow, mapping = self._fixture(root)
            output_dir = root / "converted"
            report_path = convert_profiles(workflow, mapping, output_dir)
            original = report_path.read_bytes()

            with self.assertRaisesRegex(MigrationError, "replace"):
                convert_profiles(workflow, mapping, output_dir)

            self.assertEqual(report_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
