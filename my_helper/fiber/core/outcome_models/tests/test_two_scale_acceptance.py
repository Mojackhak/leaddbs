"""Read-only acceptance tests for the committed STNSNr four-model profiles."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from outcome_models.catalog import CatalogStatus, build_endpoint_catalog
from outcome_models.config import WorkflowOverrides, load_resolved_workflow
from outcome_models.planner import compile_execution_plan


_REPO_ROOT = Path(__file__).resolve().parents[5]
_WORKFLOW = _REPO_ROOT / "my_helper/stnsnr/config/four_model_v1/workflow.yaml"
_CLINICAL = Path("/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx")


class TwoScaleProfileAcceptanceTests(unittest.TestCase):
    def test_profiles_cover_all_current_scales_without_scale_privilege(self) -> None:
        config = load_resolved_workflow(_WORKFLOW, WorkflowOverrides(all_available=True))
        workbook_scales = set(pd.read_excel(_CLINICAL, usecols=["Scale"])["Scale"].dropna().astype(str).unique())
        configured_scales = {scale.label for scale in config.scales}

        self.assertEqual(configured_scales, workbook_scales)
        self.assertEqual(len(config.scales), 28)
        self.assertTrue(all(scale.minimum_subjects == 12 for scale in config.scales))
        self.assertEqual(
            {scale.label for scale in config.scales if scale.direction == "higher"},
            {"SE-ADL score (%)"},
        )

        production_sources = [
            path
            for path in (_REPO_ROOT / "my_helper/fiber/core/outcome_models").glob("*.py")
            if path.name not in {"__init__.py"}
        ]
        production_text = "\n".join(path.read_text(encoding="utf-8") for path in production_sources)
        self.assertNotIn("MDS-UPDRS III score", production_text)
        self.assertNotIn("MDS-UPDRS IV", production_text)

    def test_two_scale_catalog_and_plan_have_complete_matched_families(self) -> None:
        config = load_resolved_workflow(_WORKFLOW, WorkflowOverrides())
        catalog = build_endpoint_catalog(config)
        plan = compile_execution_plan(config, catalog)

        self.assertEqual({scale.scale_id for scale in config.scales if scale.scale_id in config.workflow.selection.scales}, {"mds_updrs_iii_score", "mds_updrs_iv"})
        for scale_id in ("mds_updrs_iii_score", "mds_updrs_iv"):
            chronic = {
                row.key.model_family
                for row in catalog
                if row.key.scale_id == scale_id
                and row.key.endpoint_phase in {"reference", "chronic"}
                and row.status == CatalogStatus.DATA_AVAILABLE
            }
            self.assertEqual(chronic, {"hf_voxel", "hf_fiber", "ulf_voxel", "ulf_fiber"})

        iii_immediate = [
            row
            for row in catalog
            if row.key.scale_id == "mds_updrs_iii_score" and row.key.endpoint_phase == "immediate"
        ]
        iv_immediate = [
            row for row in catalog if row.key.scale_id == "mds_updrs_iv" and row.key.endpoint_phase == "immediate"
        ]
        self.assertEqual({row.key.model_family for row in iii_immediate}, {"ulf_voxel", "ulf_fiber"})
        self.assertTrue(all(row.status == CatalogStatus.DATA_AVAILABLE for row in iii_immediate))
        self.assertTrue(all(row.status == CatalogStatus.NOT_CONFIGURED for row in iv_immediate))
        self.assertFalse(
            any(task.endpoint.scale_id == "mds_updrs_iv" and task.endpoint.endpoint_phase == "immediate" for task in plan.tasks)
        )
        self.assertTrue(
            any(task.endpoint.scale_id == "mds_updrs_iii_score" and task.round_name == "Round 2b" for task in plan.tasks)
        )

    def test_model_profile_locks_round_parameters_and_connectome_roles(self) -> None:
        config = load_resolved_workflow(_WORKFLOW, WorkflowOverrides())
        direct = config.model.direct_voxel
        fiber = config.model.normative_fiber

        self.assertEqual(direct["tau_grid_v_per_m"], (100, 150, 180, 200, 220, 250, 300, 350, 400, 500))
        self.assertEqual(direct["coverage_grid"], (5, 6, 7, 8, 10, 12))
        self.assertEqual(fiber["tau_grid_v_per_m"], (400, 600, 800, 1000, 1200, 1500, 2000))
        self.assertEqual(fiber["coverage_grid"], (5, 6, 7, 8, 10, 12))
        self.assertEqual(config.model.formal["permutations"], 10000)
        self.assertEqual(config.model.formal["bootstraps"], 10000)
        self.assertEqual(config.model.formal["jitter_resamples"], 1000)
        self.assertEqual(config.model.formal["seed"], 42)
        self.assertEqual(config.model.sensitivity["selected_tau_multipliers"], (0.9, 1.1))
        self.assertEqual(
            dict(fiber["connectome_roles"]),
            {"ppmi": "observed_robustness", "mgh": "observed_robustness", "dtor": "formal"},
        )
        self.assertNotIn("candidate_threshold_v_per_m", direct)
        self.assertNotIn("smoke", config.model.formal)


if __name__ == "__main__":
    unittest.main()
