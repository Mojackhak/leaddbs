"""Tests for immutable endpoint, task, and final-model identities."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from outcome_models.identity import EndpointModelKey, FinalModelKey, TaskKey, canonical_hash


class IdentityTests(unittest.TestCase):
    def test_canonical_hash_ignores_mapping_key_order(self) -> None:
        first = canonical_hash({"scale": "s1", "nested": {"phase": "chronic", "model": "hf_voxel"}})
        second = canonical_hash({"nested": {"model": "hf_voxel", "phase": "chronic"}, "scale": "s1"})
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertEqual(canonical_hash({"a": 1}, length=12), canonical_hash({"a": 1})[:12])

    def test_endpoint_identity_uses_normalized_structural_fields(self) -> None:
        key = EndpointModelKey(
            study_id="study",
            scale_id="scale_one",
            endpoint_phase="chronic",
            model_family="hf_voxel",
        )
        self.assertEqual(key.connectome, "none")
        self.assertTrue(key.identifier.startswith("endpoint_"))
        self.assertEqual(key.identifier, EndpointModelKey(**key.as_dict()).identifier)

        immediate = EndpointModelKey(**{**key.as_dict(), "endpoint_phase": "immediate"})
        fiber = EndpointModelKey(**{**key.as_dict(), "model_family": "hf_fiber", "connectome": "dtor"})
        self.assertNotEqual(key.identifier, immediate.identifier)
        self.assertNotEqual(key.identifier, fiber.identifier)

    def test_display_label_cannot_change_endpoint_identity(self) -> None:
        fields = {
            "study_id": "study",
            "scale_id": "scale_one",
            "endpoint_phase": "chronic",
            "model_family": "hf_voxel",
        }
        key = EndpointModelKey(**fields)
        payload = key.as_dict()
        payload["display_label"] = "MDS-UPDRS III"
        self.assertNotIn("display_label", key.as_dict())
        with self.assertRaises(TypeError):
            EndpointModelKey(**payload)

    def test_task_identity_changes_with_stage_branch_and_source(self) -> None:
        endpoint_id = EndpointModelKey("study", "scale_one", "chronic", "ulf_voxel").identifier
        observed = TaskKey(endpoint_id, "observed", "no_delta_hf")
        adjusted = TaskKey(endpoint_id, "observed", "delta_hf_adjusted")
        formal = TaskKey(endpoint_id, "formal", "no_delta_hf", "tau200_cov5")

        self.assertTrue(observed.identifier.startswith("task_"))
        self.assertNotEqual(observed.identifier, adjusted.identifier)
        self.assertNotEqual(observed.identifier, formal.identifier)
        self.assertEqual(observed.source_reference, "none")
        self.assertEqual(observed.replicate, "none")

    def test_final_model_identity_normalizes_numeric_source(self) -> None:
        endpoint_id = EndpointModelKey("study", "scale_one", "chronic", "hf_voxel").identifier
        integer_tau = FinalModelKey(endpoint_id, "primary", 200, 5, "partial_spearman")
        float_tau = FinalModelKey(endpoint_id, "primary", 200.0, 5, "partial_spearman")
        changed = FinalModelKey(endpoint_id, "primary", 220.0, 5, "partial_spearman")

        self.assertEqual(integer_tau.identifier, float_tau.identifier)
        self.assertNotEqual(integer_tau.identifier, changed.identifier)
        self.assertTrue(integer_tau.identifier.startswith("final_"))

    def test_identity_records_are_frozen(self) -> None:
        key = EndpointModelKey("study", "scale_one", "chronic", "hf_voxel")
        with self.assertRaises(FrozenInstanceError):
            key.scale_id = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
