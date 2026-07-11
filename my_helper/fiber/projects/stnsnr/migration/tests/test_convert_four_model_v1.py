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


def _forbidden_target_keys(value: object) -> set[str]:
    forbidden: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            token = str(key).lower()
            if any(part in token for part in ("chronic", "immediate", "phase")):
                forbidden.add(str(key))
            forbidden.update(_forbidden_target_keys(item))
    elif isinstance(value, list):
        for item in value:
            forbidden.update(_forbidden_target_keys(item))
    return forbidden


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

    def test_conversion_creates_one_combined_condition_and_multiple_child_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow, mapping = self._fixture(root)
            report_path = convert_profiles(workflow, mapping, root / "converted")
            target_study = yaml.safe_load((root / "converted" / "study.yaml").read_text())
            target_scales = yaml.safe_load((root / "converted" / "scales.yaml").read_text())
            target_workflow = yaml.safe_load((root / "converted" / "workflow.yaml").read_text())
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(set(target_study["conditions"]), {"reference_only", "combined"})
        bindings = target_scales["scales"][0]["endpoint_bindings"]
        self.assertEqual(len(bindings), 3)
        reference = next(row for row in bindings if row["condition_id"] == "reference_only")
        combined = [row for row in bindings if row["condition_id"] == "combined"]
        self.assertEqual(len(combined), 2)
        self.assertEqual({row["matched_reference_binding_id"] for row in combined}, {reference["endpoint_binding_id"]})
        self.assertEqual(target_workflow["selection"]["subscales"], ["combined_a", "combined_b"])
        self.assertFalse(_forbidden_target_keys(target_study))
        self.assertFalse(_forbidden_target_keys(target_scales))
        self.assertFalse(_forbidden_target_keys(target_workflow))
        self.assertEqual(report["status"], "draft_requires_review")

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


if __name__ == "__main__":
    unittest.main()
