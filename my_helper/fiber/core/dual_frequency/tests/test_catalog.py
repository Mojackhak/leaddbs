"""Generic endpoint catalog construction tests."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from dual_frequency.catalog import CatalogStatus, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides, load_workflow
from dual_frequency.contracts.study_base import (
    ClinicalObservation,
    ComponentDefinition,
    ConnectomeDefinition,
    ProgramRecord,
    ScaleDefinition,
    SpatialDefinition,
    StudyBaseRecord,
    SubjectRecord,
    SubscaleDefinition,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONFIG_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"
SCALE_IDS = ("mds_updrs_iii_score", "mds_updrs_iv")


def _observation(
    subject_id: str,
    phase_id: str,
    program_id: int,
    scale_id: str,
    observed: bool,
) -> ClinicalObservation:
    return ClinicalObservation(
        observation_id=f"obs:{subject_id}:{phase_id}:{program_id}:{scale_id}",
        subject_id=subject_id,
        phase_id=phase_id,
        program_id=program_id,
        scale_id=scale_id,
        subscale_id="total",
        value=10 + program_id if observed else None,
        status="observed" if observed else "not_assessed",
    )


def _program(
    subject_id: str,
    phase_id: str,
    program_id: int,
    role: str,
    iv_observed: bool,
) -> ProgramRecord:
    return ProgramRecord(
        subject_id=subject_id,
        phase_id=phase_id,
        phase_label=phase_id,
        program_id=program_id,
        program_label=f"Program {program_id}",
        condition_role=role,
        stimulation_state="none" if role == "none" else "active",
        assessment_order=program_id,
        duration_label="configured",
        stimulation_start_date=None,
        assessment_date=None,
        exposure_days=None,
        observations=(
            _observation(subject_id, phase_id, program_id, SCALE_IDS[0], True),
            _observation(subject_id, phase_id, program_id, SCALE_IDS[1], iv_observed),
        ),
        stimulation_sources=(),
    )


def synthetic_study(reverse_subjects: bool = False) -> StudyBaseRecord:
    subjects: list[SubjectRecord] = []
    for index in range(14):
        subject_id = f"subject-{index + 1:02d}"
        subjects.append(
            SubjectRecord(
                subject_id=subject_id,
                subject_label=subject_id,
                leaddbs_subject_dir=Path(f"/tmp/{subject_id}"),
                electrode_reconstruction=Path(f"/tmp/{subject_id}/reconstruction.mat"),
                electrodes=(),
                programs=(
                    _program(subject_id, "baseline_phase", 0, "none", True),
                    _program(subject_id, "reference_phase", 1, "reference_only", True),
                    _program(subject_id, "addon_phase", 2, "combined", index < 11),
                ),
            )
        )
    if reverse_subjects:
        subjects.reverse()
    return StudyBaseRecord(
        schema_version="dual_frequency_study_v1",
        study_id="synthetic",
        study_label="Synthetic",
        data_version="1",
        components=(
            ComponentDefinition("region_a", "Region A"),
            ComponentDefinition("region_b", "Region B"),
        ),
        scales=(
            ScaleDefinition(
                scale_id=SCALE_IDS[0],
                label="MDS-UPDRS III score",
                value_type="integer",
                unit="score",
                direction="lower",
                subscales=(SubscaleDefinition("total", "Total"),),
            ),
            ScaleDefinition(
                scale_id=SCALE_IDS[1],
                label="MDS-UPDRS IV",
                value_type="integer",
                unit="score",
                direction="lower",
                subscales=(SubscaleDefinition("total", "Total"),),
            ),
        ),
        spatial=SpatialDefinition(
            canonical_space="MNI152NLin2009bAsym",
            canonical_hemisphere="R",
            left_to_right_transform=Path("/tmp/flip.mat"),
            brainmask_id="mask",
            brainmask_path=Path("/tmp/mask.nii.gz"),
            connectomes=(
                ConnectomeDefinition(
                    connectome_id="ppmi_85_ewert_2017",
                    label="PPMI",
                    space="MNI152NLin2009bAsym",
                    streamlines_path=Path("/tmp/ppmi.mat"),
                    metadata_path=None,
                ),
                ConnectomeDefinition(
                    connectome_id="mgh_usc_hcp_32_horn_2017",
                    label="MGH",
                    space="MNI152NLin2009bAsym",
                    streamlines_path=Path("/tmp/mgh.mat"),
                    metadata_path=None,
                ),
            ),
        ),
        subjects=tuple(subjects),
        source_path=Path("/tmp/study_base.json"),
        source_sha256="a" * 64,
    )


def make_workflow(overrides: WorkflowOverrides):
    workflow = yaml.safe_load((CONFIG_ROOT / "workflow.yaml").read_text(encoding="utf-8"))
    workflow["selection"] = {"models": ["all"], "connectomes": ["all"]}
    direct = yaml.safe_load((CONFIG_ROOT / "direct_voxel_model_test.yaml").read_text(encoding="utf-8"))
    fiber = yaml.safe_load((CONFIG_ROOT / "normative_fiber_model_test.yaml").read_text(encoding="utf-8"))
    individualized = yaml.safe_load(
        (CONFIG_ROOT / "individualized_seed_target_model.yaml").read_text(
            encoding="utf-8"
        )
    )
    endpoint_pair = {
        "baseline": {"phase_id": "baseline_phase", "program_id": 0},
        "reference": {"phase_id": "reference_phase", "program_id": 1},
        "addon": {"phase_id": "addon_phase", "program_id": 2},
    }
    direct["endpoint_pair"] = endpoint_pair
    fiber["endpoint_pair"] = endpoint_pair
    individualized["endpoint_pair"] = endpoint_pair
    individualized["scales"] = direct["scales"]
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        direct_path = root / "direct.yaml"
        fiber_path = root / "fiber.yaml"
        individualized_path = root / "individualized.yaml"
        workflow_path = root / "workflow.yaml"
        direct_path.write_text(yaml.safe_dump(direct, sort_keys=False), encoding="utf-8")
        fiber_path.write_text(yaml.safe_dump(fiber, sort_keys=False), encoding="utf-8")
        individualized_path.write_text(
            yaml.safe_dump(individualized, sort_keys=False),
            encoding="utf-8",
        )
        workflow["model_profiles"] = {
            "direct_voxel": direct_path.name,
            "normative_fiber": fiber_path.name,
            "individualized_seed_target": individualized_path.name,
        }
        workflow_path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
        return load_workflow(workflow_path, overrides)


class CatalogTest(unittest.TestCase):
    def test_builds_all_six_families_with_connectome_roles(self) -> None:
        config = make_workflow(WorkflowOverrides(all_available=True))
        catalog = build_endpoint_catalog(config, synthetic_study())
        self.assertEqual(len(catalog), 16)
        self.assertEqual(
            tuple(item.key.model_family for item in catalog[:8]),
            (
                "reference_voxel",
                "reference_fiber",
                "reference_fiber",
                "reference_individualized",
                "addon_voxel",
                "addon_fiber",
                "addon_fiber",
                "addon_individualized",
            ),
        )
        sensitive = tuple(item for item in catalog if item.connectome_role == "sensitive")
        self.assertEqual(len(sensitive), 4)
        self.assertTrue(all(not item.final_eligible for item in sensitive))
        formal = tuple(item for item in catalog if item.connectome_role == "formal")
        self.assertEqual(len(formal), 4)
        self.assertTrue(all(item.final_eligible for item in formal))

    def test_subject_availability_is_endpoint_specific_not_scale_privilege(self) -> None:
        config = make_workflow(WorkflowOverrides(all_available=True))
        catalog = build_endpoint_catalog(config, synthetic_study())
        iii = tuple(item for item in catalog if item.key.scale_id == SCALE_IDS[0])
        iv = tuple(item for item in catalog if item.key.scale_id == SCALE_IDS[1])
        self.assertTrue(all(item.status == CatalogStatus.DATA_AVAILABLE for item in iii))
        self.assertTrue(
            all(
                item.status == CatalogStatus.DATA_AVAILABLE
                for item in iv
                if item.key.model_family.startswith("reference_")
            )
        )
        self.assertTrue(
            all(
                item.status == CatalogStatus.INSUFFICIENT_SUBJECTS
                for item in iv
                if item.key.model_family.startswith("addon_")
            )
        )
        self.assertEqual({len(item.subject_ids) for item in iii}, {14})

    def test_addon_selection_automatically_adds_exact_reference_dependency(self) -> None:
        config = make_workflow(
            WorkflowOverrides(
                scales=SCALE_IDS,
                models=("addon_voxel",),
            )
        )
        catalog = build_endpoint_catalog(config, synthetic_study())
        self.assertEqual(len(catalog), 4)
        for scale_id in SCALE_IDS:
            rows = tuple(item for item in catalog if item.key.scale_id == scale_id)
            reference = next(item for item in rows if item.key.model_family == "reference_voxel")
            addon = next(item for item in rows if item.key.model_family == "addon_voxel")
            self.assertFalse(reference.requested)
            self.assertTrue(addon.requested)
            self.assertEqual(addon.matched_reference_endpoint_id, reference.endpoint_id)

    def test_fiber_dependencies_match_connectome_exactly(self) -> None:
        config = make_workflow(
            WorkflowOverrides(
                scales=(SCALE_IDS[0],),
                models=("addon_fiber",),
                connectomes=("ppmi_85_ewert_2017", "mgh_usc_hcp_32_horn_2017"),
            )
        )
        catalog = build_endpoint_catalog(config, synthetic_study())
        references = {
            item.key.connectome_id: item
            for item in catalog
            if item.key.model_family == "reference_fiber"
        }
        for addon in (item for item in catalog if item.key.model_family == "addon_fiber"):
            self.assertEqual(
                addon.matched_reference_endpoint_id,
                references[addon.key.connectome_id].endpoint_id,
            )

    def test_endpoint_identity_is_stable_under_subject_reordering(self) -> None:
        config = make_workflow(WorkflowOverrides(all_available=True))
        first = build_endpoint_catalog(config, synthetic_study())
        second = build_endpoint_catalog(config, synthetic_study(reverse_subjects=True))
        self.assertEqual(
            tuple(item.endpoint_id for item in first),
            tuple(item.endpoint_id for item in second),
        )
        serialized = json.dumps([item.as_dict() for item in first], sort_keys=True)
        self.assertNotIn("frequency_1_reference", serialized)
        self.assertNotIn("frequency_2_addon", serialized)

    def test_not_configured_is_a_closed_catalog_status(self) -> None:
        self.assertEqual(CatalogStatus.NOT_CONFIGURED.value, "not_configured")


if __name__ == "__main__":
    unittest.main()
