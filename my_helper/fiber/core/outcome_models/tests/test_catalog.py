"""Tests for the profile-driven endpoint catalog."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from outcome_models.catalog import CatalogStatus, build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.tests.helpers import clinical_rows_for_scale, write_clinical_rows, write_profile_bundle


_REAL_CLINICAL_WORKBOOK = Path(
    "/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx"
)
_REAL_CLINICAL_SHA256 = "0ee0cc2e1be83ab497b3edc67f721c842bf6a6b1ac36f639ada9c04057c7e536"


class EndpointCatalogTests(unittest.TestCase):
    def _load(self, root: Path, *, mutate=None, rows=None):
        workflow_path = write_profile_bundle(root, mutate=mutate)
        write_clinical_rows(root, rows or clinical_rows_for_scale("Scale One"))
        return load_resolved_workflow(workflow_path, WorkflowOverrides())

    def test_chronic_all_models_expand_with_shared_hf_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self._load(Path(tmp))
            catalog = build_endpoint_catalog(config)

        self.assertEqual(len(catalog), 4)
        identities = {(row.key.model_family, row.key.endpoint_phase, row.key.connectome) for row in catalog}
        self.assertEqual(
            identities,
            {
                ("hf_voxel", "reference", "none"),
                ("hf_fiber", "reference", "dtor"),
                ("ulf_voxel", "chronic", "none"),
                ("ulf_fiber", "chronic", "dtor"),
            },
        )
        self.assertTrue(all(row.status == CatalogStatus.DATA_AVAILABLE for row in catalog))
        self.assertTrue(all(row.n_subjects == 12 for row in catalog))
        self.assertTrue(all(row.subject_ids == tuple(f"sub-{index:02d}" for index in range(1, 13)) for row in catalog))

    def test_immediate_binding_reuses_same_scale_hf_reference(self) -> None:
        def mutate(profiles):
            profiles["workflow"]["selection"]["phases"] = ["chronic", "immediate"]
            profiles["scales"]["scales"][0]["endpoint_bindings"]["frequency_2_addon_immediate"] = {
                "protocol": "STN+SNr",
                "phase": "immediate",
            }

        with tempfile.TemporaryDirectory() as tmp:
            rows = clinical_rows_for_scale("Scale One", include_immediate=True)
            catalog = build_endpoint_catalog(self._load(Path(tmp), mutate=mutate, rows=rows))

        self.assertEqual(len(catalog), 6)
        self.assertEqual(sum(row.key.model_family.startswith("hf_") for row in catalog), 2)
        immediate = [row for row in catalog if row.key.endpoint_phase == "immediate"]
        self.assertEqual({row.key.model_family for row in immediate}, {"ulf_voxel", "ulf_fiber"})
        self.assertTrue(all(row.hf_reference_phase == "3m" for row in immediate))
        self.assertTrue(all(row.status == CatalogStatus.DATA_AVAILABLE for row in immediate))

    def test_omitted_immediate_binding_has_explicit_nonfailure_terminal_rows(self) -> None:
        def mutate(profiles):
            profiles["workflow"]["selection"]["phases"] = ["chronic", "immediate"]

        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), mutate=mutate))

        immediate = [row for row in catalog if row.key.endpoint_phase == "immediate"]
        self.assertEqual(len(immediate), 2)
        self.assertTrue(all(row.status == CatalogStatus.NOT_CONFIGURED for row in immediate))
        self.assertTrue(all(row.n_subjects == 0 for row in immediate))

    def test_ulf_selection_automatically_includes_matched_hf_dependency(self) -> None:
        def mutate(profiles):
            profiles["workflow"]["selection"]["models"] = ["ulf-voxel"]

        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), mutate=mutate))

        self.assertEqual({row.key.model_family for row in catalog}, {"hf_voxel", "ulf_voxel"})

    def test_missing_values_and_minimum_subjects_fail_only_affected_endpoints(self) -> None:
        rows = clinical_rows_for_scale("Scale One")
        for row in rows:
            if row["Protocol"] == "STN+SNr" and row["ID"] == "sub-01":
                row["Value"] = None

        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), rows=rows))

        hf_rows = [row for row in catalog if row.key.model_family.startswith("hf_")]
        ulf_rows = [row for row in catalog if row.key.model_family.startswith("ulf_")]
        self.assertTrue(all(row.status == CatalogStatus.DATA_AVAILABLE for row in hf_rows))
        self.assertTrue(all(row.status == CatalogStatus.INPUT_FAILURE for row in ulf_rows))
        self.assertTrue(all("minimum_subjects" in " ".join(row.failure_reasons) for row in ulf_rows))

    def test_duplicate_subject_condition_rows_are_endpoint_local_failures(self) -> None:
        rows = clinical_rows_for_scale("Scale One")
        rows.append(dict(rows[0]))
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), rows=rows))

        hf_rows = [row for row in catalog if row.key.model_family.startswith("hf_")]
        ulf_rows = [row for row in catalog if row.key.model_family.startswith("ulf_")]
        self.assertTrue(all(row.status == CatalogStatus.INPUT_FAILURE for row in hf_rows))
        self.assertTrue(all(row.status == CatalogStatus.INPUT_FAILURE for row in ulf_rows))
        self.assertTrue(all("duplicate" in " ".join(row.failure_reasons) for row in hf_rows))
        self.assertTrue(all("duplicate" in " ".join(row.failure_reasons) for row in ulf_rows))

    def test_pairing_never_substitutes_another_scale(self) -> None:
        def mutate(profiles):
            second = dict(profiles["scales"]["scales"][0])
            second["scale_id"] = "scale_two"
            second["label"] = "Scale Two"
            second["endpoint_bindings"] = dict(second["endpoint_bindings"])
            profiles["scales"]["scales"].append(second)
            profiles["workflow"]["selection"]["scales"] = ["scale_one", "scale_two"]

        rows = clinical_rows_for_scale("Scale One")
        rows.extend(clinical_rows_for_scale("Scale Two", include_chronic=False, subject_prefix="other"))
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), mutate=mutate, rows=rows))

        scale_two_hf = [row for row in catalog if row.key.scale_id == "scale_two" and row.key.model_family.startswith("hf_")]
        scale_two_ulf = [row for row in catalog if row.key.scale_id == "scale_two" and row.key.model_family.startswith("ulf_")]
        self.assertTrue(all(row.status == CatalogStatus.DATA_AVAILABLE for row in scale_two_hf))
        self.assertTrue(all(row.status == CatalogStatus.INPUT_FAILURE for row in scale_two_ulf))
        self.assertTrue(all(row.n_subjects == 0 for row in scale_two_ulf))

    def test_missing_required_columns_create_input_failure_rows(self) -> None:
        rows = clinical_rows_for_scale("Scale One")
        for row in rows:
            row.pop("Baseline")
        with tempfile.TemporaryDirectory() as tmp:
            catalog = build_endpoint_catalog(self._load(Path(tmp), rows=rows))

        self.assertTrue(all(row.status == CatalogStatus.INPUT_FAILURE for row in catalog))
        self.assertTrue(all("missing_clinical_columns" in " ".join(row.failure_reasons) for row in catalog))

    @unittest.skipUnless(_REAL_CLINICAL_WORKBOOK.is_file(), "STNSNr clinical workbook is unavailable")
    def test_real_mds_updrs_iii_and_iv_catalog_counts_match_frozen_input(self) -> None:
        self.assertEqual(hashlib.sha256(_REAL_CLINICAL_WORKBOOK.read_bytes()).hexdigest(), _REAL_CLINICAL_SHA256)

        def mutate(profiles):
            profiles["study"]["paths"]["clinical_table"] = str(_REAL_CLINICAL_WORKBOOK)
            profiles["scales"]["scales"] = [
                {
                    "scale_id": "mds_updrs_iii",
                    "label": "MDS-UPDRS III score",
                    "direction": "lower",
                    "minimum_subjects": 12,
                    "endpoint_bindings": {
                        "frequency_1_reference": {"protocol": "STN", "phase": "3m"},
                        "frequency_2_addon_chronic": {"protocol": "STN+SNr", "phase": "3m"},
                        "frequency_2_addon_immediate": {
                            "protocol": "STN+SNr",
                            "phase": "immediate",
                        },
                    },
                },
                {
                    "scale_id": "mds_updrs_iv",
                    "label": "MDS-UPDRS IV",
                    "direction": "lower",
                    "minimum_subjects": 12,
                    "endpoint_bindings": {
                        "frequency_1_reference": {"protocol": "STN", "phase": "3m"},
                        "frequency_2_addon_chronic": {"protocol": "STN+SNr", "phase": "3m"},
                    },
                },
            ]
            profiles["workflow"]["selection"] = {
                "all_available": True,
                "phases": ["chronic", "immediate"],
                "models": ["all"],
                "connectomes": ["dtor"],
            }

        with tempfile.TemporaryDirectory() as tmp:
            workflow_path = write_profile_bundle(Path(tmp), mutate=mutate)
            config = load_resolved_workflow(workflow_path, WorkflowOverrides())
            catalog = build_endpoint_catalog(config)

        available = [row for row in catalog if row.status == CatalogStatus.DATA_AVAILABLE]
        self.assertEqual(len(available), 10)
        self.assertTrue(all(row.n_subjects == 16 for row in available))
        iv_immediate = [
            row
            for row in catalog
            if row.key.scale_id == "mds_updrs_iv" and row.key.endpoint_phase == "immediate"
        ]
        self.assertEqual(len(iv_immediate), 2)
        self.assertTrue(all(row.status == CatalogStatus.NOT_CONFIGURED for row in iv_immediate))


if __name__ == "__main__":
    unittest.main()
