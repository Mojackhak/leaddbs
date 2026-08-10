"""Read-only canonical study-base loading tests."""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import yaml

from dual_frequency.config import (
    ConfigurationError,
    WorkflowOverrides,
    load_workflow,
    validate_study_compatibility,
)
from dual_frequency.contracts import StudyBaseError, load_study_base, validate_study_base


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONFIG_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"
REAL_STUDY_BASE = Path("/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json")


def _observation(subject: str, phase: str, program: int, scale: str, value: int) -> dict[str, object]:
    return {
        "observation_id": f"obs:{subject}:{phase}:{program}:{scale}:total",
        "scale_id": scale,
        "subscale_id": "total",
        "value": value,
        "status": "observed",
    }


def _source(source_id: str, component_id: str, frequency_hz: float) -> dict[str, object]:
    label = "STN" if component_id == "target_stn" else "SNr"
    return {
        "source_id": source_id,
        "source_label": label,
        "component_id": component_id,
        "frequency_hz": frequency_hz,
        "control_mode": "voltage",
        "amplitude": 2.0,
        "pulse_width_us": 60.0,
        "contacts": [
            {"contact": 4, "polarity": "cathode", "fraction": 1.0},
            {"contact": "case", "polarity": "anode", "fraction": 1.0},
        ],
    }


def _program(
    subject: str,
    phase: str,
    program_id: int,
    role: str,
    sources: list[dict[str, object]],
) -> dict[str, object]:
    electrode_programs: list[dict[str, object]] = []
    if sources:
        electrode_programs = [
            {
                "electrode_id": "lead-R",
                "frequency_groups": [
                    {
                        "frequency_group_id": f"group-{index}",
                        "delivery_mode": "continuous",
                        "sources": [source],
                    }
                    for index, source in enumerate(sources, start=1)
                ],
            }
        ]
    duration = "preoperative" if role == "none" else "3m"
    return {
        "program_id": program_id,
        "program_label": f"Program {program_id}",
        "condition_role": role,
        "stimulation_state": "none" if role == "none" else "active",
        "assessment_order": program_id,
        "exposure": {
            "duration_label": duration,
            "stimulation_start_date": None,
            "assessment_date": None,
            "exposure_days": None,
        },
        "clinical_observations": [
            _observation(subject, phase, program_id, "scale_a", 10 + program_id),
            _observation(subject, phase, program_id, "scale_b", 20 + program_id),
        ],
        "electrode_programs": electrode_programs,
    }


def _subject(subject_id: str) -> dict[str, object]:
    return {
        "subject_id": subject_id,
        "subject_label": f"Subject {subject_id}",
        "subject_sources": {
            "leaddbs_subject_dir": f"/tmp/{subject_id}",
            "electrode_reconstruction": {"path": f"/tmp/{subject_id}/reconstruction.mat"},
        },
        "contact_numbering": {
            "convention": "bilateral_contiguous_zero_based",
            "electrode_order": ["lead-L", "lead-R"],
        },
        "electrodes": [
            {
                "electrode_id": "lead-L",
                "hemisphere": "L",
                "electrode_model": "Synthetic",
                "contact_count": 4,
                "reconstruction_lead_id": 1,
            },
            {
                "electrode_id": "lead-R",
                "hemisphere": "R",
                "electrode_model": "Synthetic",
                "contact_count": 4,
                "reconstruction_lead_id": 2,
            },
        ],
        "phases": [
            {
                "phase_id": "T0",
                "phase_label": "Baseline",
                "date": {"window_start_date": None, "window_end_date": None},
                "programs": [_program(subject_id, "T0", 0, "none", [])],
            },
            {
                "phase_id": "T2",
                "phase_label": "Reference",
                "date": {"window_start_date": None, "window_end_date": None},
                "programs": [
                    _program(
                        subject_id,
                        "T2",
                        1,
                        "reference_only",
                        [_source("source-1", "target_stn", 130.0)],
                    )
                ],
            },
            {
                "phase_id": "T3",
                "phase_label": "Add-on",
                "date": {"window_start_date": None, "window_end_date": None},
                "programs": [
                    _program(
                        subject_id,
                        "T3",
                        2,
                        "combined",
                        [
                            _source("source-1", "target_stn", 130.0),
                            _source("source-2", "target_snr", 30.0),
                        ],
                    )
                ],
            },
        ],
    }


def study_payload() -> dict[str, object]:
    return {
        "schema_version": "dual_frequency_study_v1",
        "study": {
            "study_id": "synthetic",
            "study_label": "Synthetic dual-frequency study",
            "data_version": "1",
            "stimulation_components": [
                {"component_id": "target_stn", "label": "STN"},
                {"component_id": "target_snr", "label": "SNr"},
            ],
            "scale_definitions": [
                {
                    "scale_id": "scale_a",
                    "label": "Scale A",
                    "value_type": "integer",
                    "unit": "score",
                    "direction": "lower",
                    "subscales": [{"subscale_id": "total", "label": "Total"}],
                },
                {
                    "scale_id": "scale_b",
                    "label": "Scale B",
                    "value_type": "integer",
                    "unit": "percent",
                    "direction": "higher",
                    "subscales": [{"subscale_id": "total", "label": "Total"}],
                },
            ],
            "spot_model_sources": {
                "canonical_space": "MNI152NLin2009bAsym",
                "hemisphere_mapping": {
                    "canonical_hemisphere": "R",
                    "left_to_right_transform": {"path": "/tmp/flip.mat"},
                },
                "reference_images": [
                    {"image_id": "t1", "modality": "T1w", "label": "T1", "path": "/tmp/t1.nii"},
                    {"image_id": "t2", "modality": "T2w", "label": "T2", "path": "/tmp/t2.nii"},
                ],
                "brainmask": {
                    "brainmask_id": "mask",
                    "space": "MNI152NLin2009bAsym",
                    "path": "/tmp/mask.nii.gz",
                },
                "connectomes": [
                    {
                        "connectome_id": "connectome_a",
                        "label": "Connectome A",
                        "space": "MNI152NLin2009bAsym",
                        "modality": "diffusion",
                        "representation": "streamlines",
                        "streamlines": {"format": "leaddbs_data_mat_v7_3", "path": "/tmp/data.mat"},
                        "metadata": {"path": None},
                    }
                ],
            },
            "subjects": [_subject("subject-2"), _subject("subject-1")],
            "provenance": {
                "created_at": "2026-07-15T00:00:00Z",
                "importer": {
                    "name": "build_stnsnr_study_base",
                    "version": "1",
                    "code_commit": None,
                },
                "source_files": [
                    {"role": "clinical", "path": "/tmp/clinical.xlsx"},
                    {"role": "programming", "path": "/tmp/programming.json"},
                ],
                "notes": None,
            },
        },
    }


class StudyBaseTest(unittest.TestCase):
    def test_loads_without_writing_and_preserves_explicit_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "study_base.json"
            path.write_text(json.dumps(study_payload()), encoding="utf-8")
            before = tuple(root.iterdir())
            first = load_study_base(path)
            second = load_study_base(path)
            after = tuple(root.iterdir())
        self.assertEqual(first.subject_ids, ("subject-2", "subject-1"))
        self.assertEqual(first.scale_ids, ("scale_a", "scale_b"))
        self.assertEqual(first.source_sha256, second.source_sha256)
        self.assertEqual(
            first.subjects[0].contact_numbering_convention,
            "bilateral_contiguous_zero_based",
        )
        self.assertEqual(first.subjects[0].electrode_order, ("lead-L", "lead-R"))
        self.assertEqual(before, after)
        self.assertEqual(len({item.identifier for item in first.stimulation_sources}), 6)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first.study_id = "changed"

    def test_rejects_duplicate_ids_and_invalid_direction(self) -> None:
        payload = study_payload()
        payload["study"]["subjects"][1]["subject_id"] = "subject-2"
        with self.assertRaisesRegex(StudyBaseError, "duplicate subject_id"):
            validate_study_base(payload)

        payload = study_payload()
        payload["study"]["scale_definitions"][0]["direction"] = "unknown"
        with self.assertRaisesRegex(StudyBaseError, "direction"):
            validate_study_base(payload)

    def test_rejects_invalid_electrode_order(self) -> None:
        payload = study_payload()
        payload["study"]["subjects"][0]["contact_numbering"]["electrode_order"] = [
            "lead-L",
            "lead-L",
        ]
        with self.assertRaisesRegex(StudyBaseError, "electrode_order"):
            validate_study_base(payload)

        payload = study_payload()
        payload["study"]["subjects"][0]["contact_numbering"]["electrode_order"] = [
            "lead-L"
        ]
        with self.assertRaisesRegex(StudyBaseError, "every declared electrode exactly once"):
            validate_study_base(payload)

    def test_rejects_out_of_range_and_duplicate_contacts(self) -> None:
        payload = study_payload()
        source = payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]["sources"][0]
        source["contacts"][0]["contact"] = 999
        with self.assertRaisesRegex(StudyBaseError, "outside.*lead-R.*range"):
            validate_study_base(payload)

        payload = study_payload()
        source = payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]["sources"][0]
        source["contacts"].append(copy.deepcopy(source["contacts"][0]))
        with self.assertRaisesRegex(StudyBaseError, "duplicate contacts"):
            validate_study_base(payload)

    def test_rejects_missing_polarity_and_fraction_closure(self) -> None:
        payload = study_payload()
        source = payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]["sources"][0]
        source["contacts"][1]["polarity"] = "cathode"
        with self.assertRaisesRegex(StudyBaseError, "at least one anode and cathode"):
            validate_study_base(payload)

        payload = study_payload()
        source = payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]["sources"][0]
        source["contacts"][0]["fraction"] = 0.5
        with self.assertRaisesRegex(StudyBaseError, "cathode fractions must sum to 1"):
            validate_study_base(payload)

    def test_relative_paths_resolve_from_study_parent_not_cwd(self) -> None:
        payload = study_payload()
        spot = payload["study"]["spot_model_sources"]
        spot["hemisphere_mapping"]["left_to_right_transform"]["path"] = "assets/flip.mat"
        spot["brainmask"]["path"] = "assets/mask.nii.gz"
        spot["connectomes"][0]["streamlines"]["path"] = "connectomes/data.mat"
        spot["connectomes"][0]["metadata"]["path"] = "connectomes/metadata.json"
        for subject in payload["study"]["subjects"]:
            subject_id = subject["subject_id"]
            subject["subject_sources"]["leaddbs_subject_dir"] = f"subjects/{subject_id}"
            subject["subject_sources"]["electrode_reconstruction"][
                "path"
            ] = f"subjects/{subject_id}/reconstruction.mat"

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            study_directory = root / "study"
            other_directory = root / "other"
            study_directory.mkdir()
            other_directory.mkdir()
            path = study_directory / "study_base.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            original_cwd = Path.cwd()
            try:
                os.chdir(other_directory)
                study = load_study_base(path)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(
            study.spatial.left_to_right_transform,
            (study_directory / "assets/flip.mat").resolve(),
        )
        self.assertEqual(
            study.spatial.brainmask_path,
            (study_directory / "assets/mask.nii.gz").resolve(),
        )
        self.assertEqual(
            study.spatial.connectomes[0].streamlines_path,
            (study_directory / "connectomes/data.mat").resolve(),
        )
        self.assertEqual(
            study.spatial.connectomes[0].metadata_path,
            (study_directory / "connectomes/metadata.json").resolve(),
        )
        self.assertEqual(
            study.subjects[0].leaddbs_subject_dir,
            (study_directory / "subjects/subject-2").resolve(),
        )

    def test_rejects_nonfinite_values_and_group_inconsistency(self) -> None:
        payload = study_payload()
        payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "clinical_observations"
        ][0]["value"] = float("nan")
        with self.assertRaises(StudyBaseError):
            validate_study_base(payload)

        payload = study_payload()
        group = payload["study"]["subjects"][0]["phases"][2]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]
        extra_source = copy.deepcopy(group["sources"][0])
        extra_source["source_id"] = "source-current"
        extra_source["control_mode"] = "current"
        group["sources"].append(extra_source)
        with self.assertRaisesRegex(StudyBaseError, "cannot mix control modes"):
            validate_study_base(payload)

    def test_rejects_program_observation_order_drift(self) -> None:
        payload = study_payload()
        observations = payload["study"]["subjects"][0]["phases"][0]["programs"][0][
            "clinical_observations"
        ]
        observations.reverse()
        with self.assertRaisesRegex(StudyBaseError, "observation order differs"):
            validate_study_base(payload)

    def test_phase_ids_are_generic_but_invalid_program_and_frequency_fail(self) -> None:
        payload = study_payload()
        payload["study"]["subjects"][0]["phases"][0]["phase_id"] = "T9"
        validate_study_base(payload)

        payload = study_payload()
        payload["study"]["subjects"][0]["phases"][0]["programs"][0]["program_id"] = -1
        with self.assertRaises(StudyBaseError):
            validate_study_base(payload)

        payload = study_payload()
        payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]["sources"][0]["frequency_hz"] = 0
        with self.assertRaises(StudyBaseError):
            validate_study_base(payload)

    def test_component_ids_are_generic_and_source_ids_are_group_scoped(self) -> None:
        payload = study_payload()
        replacements = {
            "target_stn": ("region_reference", "Reference region"),
            "target_snr": ("region_addon", "Add-on region"),
        }
        for component in payload["study"]["stimulation_components"]:
            component["component_id"], component["label"] = replacements[component["component_id"]]
        for subject in payload["study"]["subjects"]:
            for phase in subject["phases"]:
                for program in phase["programs"]:
                    for electrode in program["electrode_programs"]:
                        for group in electrode["frequency_groups"]:
                            for source in group["sources"]:
                                source["component_id"], source["source_label"] = replacements[
                                    source["component_id"]
                                ]
        validate_study_base(payload)

        payload = study_payload()
        group = payload["study"]["subjects"][0]["phases"][1]["programs"][0][
            "electrode_programs"
        ][0]["frequency_groups"][0]
        group["sources"].append(copy.deepcopy(group["sources"][0]))
        with self.assertRaisesRegex(StudyBaseError, "duplicate source_id"):
            validate_study_base(payload)

    @unittest.skipUnless(REAL_STUDY_BASE.is_file(), "real study base is not mounted")
    def test_real_study_base_and_profiles_are_compatible(self) -> None:
        study = load_study_base(REAL_STUDY_BASE)
        workflow = load_workflow(CONFIG_ROOT / "workflow.yaml", WorkflowOverrides(all_available=True))
        validate_study_compatibility(study, workflow)
        self.assertEqual(len(study.subjects), 16)
        self.assertEqual(len(study.scales), 28)
        self.assertEqual(len(study.observations), 2240)
        self.assertEqual(len(study.stimulation_sources), 194)
        frequency_counts = Counter(
            workflow.direct_voxel.frequency_classes.classify(source.frequency_hz)
            for source in study.stimulation_sources
        )
        self.assertEqual(
            frequency_counts,
            {"reference": 142, "addon": 52},
        )

        workflow_payload = yaml.safe_load((CONFIG_ROOT / "workflow.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            direct_test = yaml.safe_load(
                (CONFIG_ROOT / "direct_voxel_model_test.yaml").read_text(
                    encoding="utf-8"
                )
            )
            individualized_test = yaml.safe_load(
                (CONFIG_ROOT / "individualized_seed_target_model.yaml").read_text(
                    encoding="utf-8"
                )
            )
            individualized_test["scales"] = direct_test["scales"]
            individualized_test["endpoint_pair"] = direct_test["endpoint_pair"]
            individualized_test_path = temporary_root / "individualized.yaml"
            individualized_test_path.write_text(
                yaml.safe_dump(individualized_test, sort_keys=False),
                encoding="utf-8",
            )
            workflow_payload["model_profiles"] = {
                "direct_voxel": str(CONFIG_ROOT / "direct_voxel_model_test.yaml"),
                "normative_fiber": str(CONFIG_ROOT / "normative_fiber_model_test.yaml"),
                "individualized_seed_target": str(individualized_test_path),
            }
            test_workflow_path = temporary_root / "workflow.yaml"
            test_workflow_path.write_text(
                yaml.safe_dump(workflow_payload, sort_keys=False),
                encoding="utf-8",
            )
            test_workflow = load_workflow(
                test_workflow_path,
                WorkflowOverrides(all_available=True),
            )
        validate_study_compatibility(study, test_workflow)

    @unittest.skipUnless(REAL_STUDY_BASE.is_file(), "real study base is not mounted")
    def test_configured_scale_and_endpoint_drift_is_rejected(self) -> None:
        study = load_study_base(REAL_STUDY_BASE)
        workflow = load_workflow(CONFIG_ROOT / "workflow.yaml", WorkflowOverrides(all_available=True))
        missing_scale_workflow = dataclasses.replace(
            workflow,
            direct_voxel=dataclasses.replace(
                workflow.direct_voxel,
                scales=workflow.direct_voxel.scales + ("missing_scale",),
            ),
        )
        with self.assertRaisesRegex(ConfigurationError, "missing from study base"):
            validate_study_compatibility(study, missing_scale_workflow)

        invalid_binding = dataclasses.replace(
            workflow.direct_voxel.endpoint_pair,
            reference=dataclasses.replace(workflow.direct_voxel.endpoint_pair.reference, program_id=99),
        )
        invalid_workflow = dataclasses.replace(
            workflow,
            direct_voxel=dataclasses.replace(workflow.direct_voxel, endpoint_pair=invalid_binding),
        )
        with self.assertRaisesRegex(ConfigurationError, "is absent"):
            validate_study_compatibility(study, invalid_workflow)


if __name__ == "__main__":
    unittest.main()
