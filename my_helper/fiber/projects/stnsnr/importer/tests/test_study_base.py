"""Behavioral tests for the STNSNr study-base importer."""

from __future__ import annotations

from datetime import datetime, timezone
import copy
import errno
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from scipy.io import savemat

from projects.stnsnr.importer.study_base import (
    StudyBaseImportError,
    build_study_base,
    extract_electrodes,
    main,
    program_to_vta_spec,
    sanitize_scale_id,
    serialize_study_base,
    validate_study_base,
    write_study_base_atomic,
)


FIXED_TIME = datetime(2026, 7, 11, 12, 30, tzinfo=timezone.utc)


class StudyBaseImporterTests(unittest.TestCase):
    @staticmethod
    def _first_source_context(payload: dict[str, object]):
        subject = payload["study"]["subjects"][0]
        program = subject["phases"][1]["programs"][0]
        electrode_program = program["electrode_programs"][0]
        group = electrode_program["frequency_groups"][0]
        source = group["sources"][0]
        electrode = next(
            row
            for row in subject["electrodes"]
            if row["electrode_id"] == electrode_program["electrode_id"]
        )
        return group, source, electrode

    def _write_reconstruction(
        self,
        root: Path,
        subject_id: str,
        *,
        model: str = "Medtronic 3387",
        contacts: int = 4,
        native_contacts: int | None = None,
    ) -> Path:
        reconstruction = root / f"sub-{subject_id}" / "reconstruction"
        reconstruction.mkdir(parents=True, exist_ok=True)
        path = reconstruction / f"sub-{subject_id}_desc-reconstruction.mat"
        native_count = contacts if native_contacts is None else native_contacts
        props = np.empty((2,), dtype=object)
        mni_coords = np.empty((2,), dtype=object)
        native_coords = np.empty((2,), dtype=object)
        for index in range(2):
            props[index] = {"elmodel": model}
            mni_coords[index] = np.zeros((contacts, 3), dtype=float)
            native_coords[index] = np.zeros((native_count, 3), dtype=float)
        savemat(
            path,
            {
                "reco": {
                    "props": props,
                    "mni": {"coords_mm": mni_coords},
                    "native": {"coords_mm": native_coords},
                }
            },
        )
        return path

    def _write_assets(self, root: Path) -> None:
        paths = (
            "templates/space/MNI152NLin2009bAsym/t1.nii",
            "templates/space/MNI152NLin2009bAsym/t2.nii",
            "templates/space/MNI152NLin2009bAsym/brainmask.nii.gz",
            "templates/space/MNI152NLin2009bAsym/fliplr/Composite.nii.gz",
            "connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat",
            "connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat",
            "connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat",
        )
        for relative in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def _write_workbooks(self, root: Path) -> tuple[Path, Path, Path]:
        clinical = root / "clinical.xlsx"
        stimulation = root / "stimulation.xlsx"
        reconstruction_root = root / "leaddbs"
        rows = []
        conditions = (
            ("Pre-op", "A"),
            ("STN (immediate)", "B"),
            ("STN+SNr (immediate)", "C"),
            ("STN (3 m)", "D"),
            ("STN+SNr (3 m)", "E"),
        )
        for subject_index, subject_id in enumerate(("001", "002"), start=1):
            for feature_index, feature in enumerate(("Scale One", "Scale Two"), start=1):
                for condition_index, (condition, group) in enumerate(conditions):
                    if feature == "Scale Two" and "immediate" in condition:
                        continue
                    rows.append(
                        {
                            "ID": subject_id,
                            "Feature": feature,
                            "Condition": condition,
                            "Value": subject_index * 10 + feature_index + condition_index,
                            "Group": group,
                        }
                    )
            self._write_reconstruction(reconstruction_root, subject_id)
        pd.DataFrame(rows).to_excel(clinical, index=False)

        stimulation_rows = []
        for subject_id in ("001", "002"):
            for phase, protocol in (
                ("immediate", "STN"),
                ("3m", "STN"),
                ("immediate", "STN+SNr"),
                ("3m", "STN+SNr"),
            ):
                targets = ("STN",) if protocol == "STN" else ("STN", "SNr")
                for side, contact in (("L", 0), ("R", 4)):
                    for target in targets:
                        stimulation_rows.append(
                            {
                                "ID": subject_id,
                                "NameEn": f"Subject {subject_id}",
                                "NameZh": "",
                                "Phase": phase,
                                "Protocol": protocol,
                                "Contact": contact,
                                "Target": target,
                                "Side": side,
                                "Voltage": 2.5,
                                "PulseWidth": 60,
                                "Frequency": 145 if target == "STN" else 10,
                                "ParameterSource": "fixture",
                                "StimulationPattern": "continuous",
                                "AlternatingGroup": np.nan,
                                "Notes": "",
                            }
                        )
        with pd.ExcelWriter(stimulation) as writer:
            pd.DataFrame(stimulation_rows).to_excel(
                writer, sheet_name="Contact Parameters", index=False
            )
        return clinical, stimulation, reconstruction_root

    def _build_fixture(self, root: Path) -> dict[str, object]:
        clinical, stimulation, reconstruction_root = self._write_workbooks(root)
        self._write_assets(root)
        return build_study_base(
            clinical_workbook=clinical,
            stimulation_workbook=stimulation,
            stimulation_sheet="Contact Parameters",
            leaddbs_root=reconstruction_root,
            asset_root=root,
            created_at=lambda: FIXED_TIME,
            code_commit="test-commit",
        )

    def test_scale_ids_are_nfkc_sanitized_and_collisions_are_rejected(self) -> None:
        self.assertEqual(sanitize_scale_id("ＭＤＳ UPDRS-IV"), "mds_updrs_iv")
        with self.assertRaisesRegex(StudyBaseImportError, "collision"):
            sanitize_scale_id("Scale-A", existing={"scale_a": "Scale A"})

    def test_import_builds_complete_program_scale_grid_without_scale_privilege(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        study = payload["study"]
        self.assertEqual([row["scale_id"] for row in study["scale_definitions"]], ["scale_one", "scale_two"])
        for subject in study["subjects"]:
            programs = [program for phase in subject["phases"] for program in phase["programs"]]
            self.assertEqual(len(programs), 5)
            self.assertTrue(all(len(program["clinical_observations"]) == 2 for program in programs))
            immediate = next(program for program in programs if program["program_label"] == "STN immediate")
            scale_two = next(row for row in immediate["clinical_observations"] if row["scale_id"] == "scale_two")
            self.assertEqual(scale_two, {
                "observation_id": f"{subject['subject_id']}__t1__program1__scale_two__total",
                "scale_id": "scale_two",
                "subscale_id": "total",
                "value": None,
                "status": "not_assessed",
            })

    def test_reconstruction_extracts_left_then_right_for_four_and_eight_contacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            four = self._write_reconstruction(root, "001")
            eight = self._write_reconstruction(root, "002", model="SceneRay SR1202", contacts=8)
            self.assertEqual([row["electrode_id"] for row in extract_electrodes(four)], ["lead-L", "lead-R"])
            self.assertEqual([row["contact_count"] for row in extract_electrodes(eight)], [8, 8])
            self.assertEqual([row["reconstruction_lead_id"] for row in extract_electrodes(eight)], [2, 1])

    def test_reconstruction_rejects_native_mni_contact_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_reconstruction(Path(tmp), "001", contacts=4, native_contacts=3)
            with self.assertRaisesRegex(StudyBaseImportError, "native.*MNI"):
                extract_electrodes(path)

    def test_reconstruction_rejects_unknown_electrode_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_reconstruction(Path(tmp), "001", model="Unknown Model")
            with self.assertRaisesRegex(StudyBaseImportError, "unsupported electrode model"):
                extract_electrodes(path)

    def test_alternating_sources_share_one_frequency_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            frame["AlternatingGroup"] = frame["AlternatingGroup"].astype(object)
            selected = (frame["ID"] == "001") & (frame["Phase"] == "immediate") & (frame["Protocol"] == "STN+SNr") & (frame["Side"] == "L")
            frame.loc[selected, "StimulationPattern"] = "alternating"
            frame.loc[selected, "AlternatingGroup"] = "A"
            frame.loc[selected, "Frequency"] = 145
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            payload = build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")
        subject = payload["study"]["subjects"][0]
        program = next(program for phase in subject["phases"] for program in phase["programs"] if phase["phase_id"] == "T2" and program["program_id"] == 2)
        left = next(row for row in program["electrode_programs"] if row["electrode_id"] == "lead-L")
        alternating = [row for row in left["frequency_groups"] if row["delivery_mode"] == "alternating"]
        self.assertEqual(len(alternating), 1)
        self.assertEqual(len(alternating[0]["sources"]), 2)

    def test_mixed_frequency_alternating_group_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            frame["AlternatingGroup"] = frame["AlternatingGroup"].astype(object)
            selected = (frame["ID"] == "001") & (frame["Phase"] == "immediate") & (frame["Protocol"] == "STN+SNr") & (frame["Side"] == "L")
            frame.loc[selected, "StimulationPattern"] = "alternating"
            frame.loc[selected, "AlternatingGroup"] = "A"
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            with self.assertRaisesRegex(StudyBaseImportError, "mixed frequencies"):
                build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")

    def test_unknown_programming_row_is_rejected_instead_of_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            extra = frame.iloc[[0]].copy()
            extra["Phase"] = "unknown-phase"
            frame = pd.concat([frame, extra], ignore_index=True)
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            with self.assertRaisesRegex(StudyBaseImportError, "unknown programming Phase/Protocol"):
                build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")

    def test_fractional_programming_contact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            frame["Contact"] = frame["Contact"].astype(float)
            frame.loc[0, "Contact"] = 0.5
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            with self.assertRaisesRegex(StudyBaseImportError, "Contact.*integer"):
                build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")

    def test_duplicate_programming_row_is_rejected_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            with self.assertRaisesRegex(StudyBaseImportError, "duplicate stimulation"):
                build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")

    def test_fixed_clock_serialization_is_byte_deterministic_and_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload_a = self._build_fixture(Path(tmp))
            payload_b = self._build_fixture(Path(tmp))
        self.assertEqual(serialize_study_base(payload_a), serialize_study_base(payload_b))
        self.assertEqual(payload_a["study"]["data_version"], "1")
        self.assertEqual(payload_a["study"]["stimulation_components"], [
            {"component_id": "target_stn", "label": "STN"},
            {"component_id": "target_snr", "label": "SNr"},
        ])
        self.assertEqual(payload_a["study"]["provenance"]["created_at"], "2026-07-11T12:30:00Z")
        validate_study_base(payload_a)

    def test_frequency_is_positive_finite_per_source_and_equal_within_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        combined = payload["study"]["subjects"][0]["phases"][2]["programs"][1]
        group = combined["electrode_programs"][0]["frequency_groups"][0]
        self.assertNotIn("frequency_hz", group)
        self.assertTrue(all(source["frequency_hz"] > 0 for source in group["sources"]))
        stn_sources = [
            source
            for electrode in combined["electrode_programs"]
            for frequency_group in electrode["frequency_groups"]
            for source in frequency_group["sources"]
            if source["component_id"] == "target_stn"
        ]
        self.assertTrue(stn_sources)
        self.assertTrue(all(source["frequency_hz"] == 145.0 for source in stn_sources))

        invalid = copy.deepcopy(payload)
        group = invalid["study"]["subjects"][0]["phases"][2]["programs"][1]["electrode_programs"][0]["frequency_groups"][0]
        group["sources"][0]["frequency_hz"] = float("inf")
        with self.assertRaisesRegex(StudyBaseImportError, "frequency_hz"):
            validate_study_base(invalid)

    def test_semantics_reject_mixed_source_frequencies_within_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            frame = pd.read_excel(stimulation, sheet_name="Contact Parameters", dtype={"ID": str})
            frame["AlternatingGroup"] = frame["AlternatingGroup"].astype(object)
            selected = (frame["ID"] == "001") & (frame["Phase"] == "immediate") & (frame["Protocol"] == "STN+SNr") & (frame["Side"] == "L")
            frame.loc[selected, "StimulationPattern"] = "alternating"
            frame.loc[selected, "AlternatingGroup"] = "A"
            frame.loc[selected, "Frequency"] = 145
            with pd.ExcelWriter(stimulation) as writer:
                frame.to_excel(writer, sheet_name="Contact Parameters", index=False)
            self._write_assets(root)
            payload = build_study_base(clinical, stimulation, "Contact Parameters", reconstruction_root, root, created_at=lambda: FIXED_TIME, code_commit="test")
        group = payload["study"]["subjects"][0]["phases"][2]["programs"][1]["electrode_programs"][0]["frequency_groups"][0]
        group["sources"][1]["frequency_hz"] = 10
        with self.assertRaisesRegex(StudyBaseImportError, "mixed frequencies"):
            validate_study_base(payload)

    def test_schema_rejects_legacy_frequency_role_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        payload["study"]["frequency_components"] = [
            {"component_id": "frequency_1_reference", "label": "HF"},
            {"component_id": "frequency_2_addon", "label": "ULF"},
        ]
        del payload["study"]["stimulation_components"]
        with self.assertRaisesRegex(StudyBaseImportError, "schema validation failed"):
            validate_study_base(payload)

    def test_semantics_rejects_swapped_stimulation_component_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        payload["study"]["stimulation_components"][0]["label"] = "SNr"
        with self.assertRaisesRegex(StudyBaseImportError, "stimulation component catalog"):
            validate_study_base(payload)

    def test_schema_and_semantics_accept_voltage_multi_contact_case_return(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        _, source, electrode = self._first_source_context(payload)
        used = source["contacts"][0]["contact"]
        extra = next(index for index in range(electrode["contact_count"]) if index != used)
        source["contacts"].insert(
            1,
            {"contact": extra, "polarity": "cathode", "fraction": 1.0},
        )
        validate_study_base(payload)

    def test_schema_and_semantics_accept_current_explicit_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        _, source, electrode = self._first_source_context(payload)
        used = source["contacts"][0]["contact"]
        extra = next(index for index in range(electrode["contact_count"]) if index != used)
        source["control_mode"] = "current"
        source["contacts"] = [
            {"contact": used, "polarity": "cathode", "fraction": 0.7},
            {"contact": extra, "polarity": "cathode", "fraction": 0.3},
            {"contact": "case", "polarity": "anode", "fraction": 1.0},
        ]
        validate_study_base(payload)

    def test_schema_and_semantics_accept_voltage_bipolar_return(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        _, source, electrode = self._first_source_context(payload)
        used = source["contacts"][0]["contact"]
        return_contact = next(
            index for index in range(electrode["contact_count"]) if index != used
        )
        source["contacts"] = [
            {"contact": used, "polarity": "cathode", "fraction": 1.0},
            {"contact": return_contact, "polarity": "anode", "fraction": 1.0},
        ]
        validate_study_base(payload)

    def test_continuous_allows_multiple_sources_and_alternating_requires_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        group, source, electrode = self._first_source_context(payload)
        second = copy.deepcopy(source)
        second["source_id"] = "source-2"
        used = source["contacts"][0]["contact"]
        second["contacts"][0]["contact"] = next(
            index for index in range(electrode["contact_count"]) if index != used
        )
        group["sources"].append(second)
        validate_study_base(payload)

        group["delivery_mode"] = "alternating"
        validate_study_base(payload)
        group["sources"] = group["sources"][:1]
        with self.assertRaises(StudyBaseImportError):
            validate_study_base(payload)

    def test_semantics_reject_invalid_contact_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))

        duplicate = copy.deepcopy(payload)
        _, source, _ = self._first_source_context(duplicate)
        source["contacts"].insert(1, copy.deepcopy(source["contacts"][0]))
        with self.assertRaises(StudyBaseImportError):
            validate_study_base(duplicate)

        missing_anode = copy.deepcopy(payload)
        _, source, _ = self._first_source_context(missing_anode)
        source["contacts"] = [source["contacts"][0]]
        with self.assertRaises(StudyBaseImportError):
            validate_study_base(missing_anode)

        invalid_voltage = copy.deepcopy(payload)
        _, source, _ = self._first_source_context(invalid_voltage)
        source["contacts"][0]["fraction"] = 0.5
        with self.assertRaises(StudyBaseImportError):
            validate_study_base(invalid_voltage)

        mixed_return = copy.deepcopy(payload)
        _, source, electrode = self._first_source_context(mixed_return)
        used = source["contacts"][0]["contact"]
        return_contact = next(
            index for index in range(electrode["contact_count"]) if index != used
        )
        source["contacts"].insert(
            1,
            {"contact": return_contact, "polarity": "anode", "fraction": 1.0},
        )
        with self.assertRaises(StudyBaseImportError):
            validate_study_base(mixed_return)

    def test_serialized_subjects_begin_with_id_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        serialized = serialize_study_base(payload)
        restored = json.loads(serialized, object_pairs_hook=dict)
        for subject in restored["study"]["subjects"]:
            self.assertEqual(list(subject)[:2], ["subject_id", "subject_label"])

    def test_schema_rejects_unknown_fields_and_invalid_none_program_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        unknown = copy.deepcopy(payload)
        unknown["study"]["unexpected"] = True
        with self.assertRaisesRegex(StudyBaseImportError, "schema validation failed"):
            validate_study_base(unknown)

        invalid_role = copy.deepcopy(payload)
        preoperative = invalid_role["study"]["subjects"][0]["phases"][0]["programs"][0]
        preoperative["stimulation_state"] = "active"
        with self.assertRaisesRegex(StudyBaseImportError, "schema validation failed"):
            validate_study_base(invalid_role)

    def test_semantics_reject_invalid_topology_and_source_component_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self._build_fixture(Path(tmp))
        invalid_topology = copy.deepcopy(payload)
        invalid_topology["study"]["subjects"][0]["phases"].pop()
        with self.assertRaisesRegex(StudyBaseImportError, "phase topology"):
            validate_study_base(invalid_topology)

        invalid_source = copy.deepcopy(payload)
        combined = invalid_source["study"]["subjects"][0]["phases"][2]["programs"][1]
        source = combined["electrode_programs"][0]["frequency_groups"][0]["sources"][0]
        source["source_label"] = "SNr" if source["component_id"] == "target_stn" else "STN"
        with self.assertRaisesRegex(StudyBaseImportError, "source label/component"):
            validate_study_base(invalid_source)

    def test_atomic_writer_requires_force_and_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._build_fixture(root)
            output = root / "study_base.json"
            output.write_text("existing", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "force"):
                write_study_base_atomic(output, payload)
            self.assertEqual(output.read_text(encoding="utf-8"), "existing")
            write_study_base_atomic(output, payload, force=True)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_atomic_writer_without_force_does_not_overwrite_concurrent_creator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._build_fixture(root)
            output = root / "study_base.json"

            def concurrent_create(_temporary: Path, destination: Path) -> None:
                destination.write_text("concurrent", encoding="utf-8")
                raise FileExistsError(destination)

            with mock.patch("projects.stnsnr.importer.study_base.os.link", side_effect=concurrent_create):
                with self.assertRaises(FileExistsError):
                    write_study_base_atomic(output, payload)
            self.assertEqual(output.read_text(encoding="utf-8"), "concurrent")

    def test_atomic_writer_falls_back_when_hard_links_are_not_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._build_fixture(root)
            output = root / "study_base.json"

            unsupported = OSError(errno.ENOTSUP, "Operation not supported")
            with mock.patch(
                "projects.stnsnr.importer.study_base.os.link",
                side_effect=unsupported,
            ):
                write_study_base_atomic(output, payload)

            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), payload)

    def test_atomic_writer_fallback_does_not_clobber_concurrent_creator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._build_fixture(root)
            output = root / "study_base.json"

            def concurrent_create(_temporary: Path, destination: Path) -> None:
                destination.write_text("concurrent", encoding="utf-8")
                raise OSError(errno.ENOTSUP, "Operation not supported")

            with mock.patch(
                "projects.stnsnr.importer.study_base.os.link",
                side_effect=concurrent_create,
            ):
                with self.assertRaisesRegex(FileExistsError, "force"):
                    write_study_base_atomic(output, payload)

            self.assertEqual(output.read_text(encoding="utf-8"), "concurrent")

    def test_atomic_writer_uses_explicit_schema_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._build_fixture(root)
            payload["study"]["extension"] = "allowed-by-override"
            schema = root / "override.schema.json"
            schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
            output = root / "study_base.json"
            write_study_base_atomic(output, payload, schema_path=schema)
            self.assertTrue(output.is_file())

    def test_vta_handoff_maps_global_contacts_to_local_one_based_contacts(self) -> None:
        electrodes = [
            {"electrode_id": "lead-L", "hemisphere": "L", "contact_count": 4},
            {"electrode_id": "lead-R", "hemisphere": "R", "contact_count": 4},
        ]
        program = {
            "condition_role": "combined",
            "electrode_programs": [
                {"electrode_id": "lead-L", "frequency_groups": [{"delivery_mode": "continuous", "sources": [{"component_id": "target_stn", "frequency_hz": 145, "contacts": [{"contact": 0, "polarity": "cathode", "fraction": 1.0}, {"contact": "case", "polarity": "anode", "fraction": 1.0}]}]}]},
                {"electrode_id": "lead-R", "frequency_groups": [{"delivery_mode": "continuous", "sources": [{"component_id": "target_snr", "frequency_hz": 10, "contacts": [{"contact": 7, "polarity": "cathode", "fraction": 1.0}, {"contact": "case", "polarity": "anode", "fraction": 1.0}]}]}]},
            ],
        }
        handoff = program_to_vta_spec(program, electrodes)
        self.assertEqual(handoff["lead-L"][0]["contacts"][0]["contact"], 1)
        self.assertEqual(handoff["lead-R"][0]["contacts"][0]["contact"], 4)
        self.assertEqual(handoff["lead-R"][0]["component_id"], "target_snr")
        self.assertEqual(handoff["lead-L"][0]["frequency_hz"], 145)
        reference = program_to_vta_spec(program, electrodes, component_id="target_stn")
        addon = program_to_vta_spec(program, electrodes, component_id="target_snr")
        self.assertEqual([row["component_id"] for row in reference["lead-L"]], ["target_stn"])
        self.assertEqual(reference["lead-R"], [])
        self.assertEqual(addon["lead-L"], [])
        self.assertEqual([row["component_id"] for row in addon["lead-R"]], ["target_snr"])

    def test_cli_validate_only_builds_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clinical, stimulation, reconstruction_root = self._write_workbooks(root)
            self._write_assets(root)
            output = root / "study_base.json"
            result = main([
                "--clinical-workbook", str(clinical),
                "--stimulation-workbook", str(stimulation),
                "--stimulation-sheet", "Contact Parameters",
                "--leaddbs-root", str(reconstruction_root),
                "--asset-root", str(root),
                "--output", str(output),
                "--validate-only",
            ])
            self.assertEqual(result, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
