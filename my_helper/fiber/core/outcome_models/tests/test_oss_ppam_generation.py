"""Probabilistic PAM generation contract tests for normative OSS rows.

The production contract is fixed at ten samples. Each sample must execute the
complete OSS command chain, retain the source stimulation frequency, and
contribute one internally consistent local-fiber activation state. Aggregation
is performed only after all ten samples are present and exactly mapped back to
the right-canonical candidate-fiber axis.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np


ANALYSIS_ROOT = Path(__file__).resolve().parents[2] / "analysis"
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))

ACTIVATION = importlib.import_module("stnsnr_normative_fiber_oss_activation_rows")
PREFLIGHT = importlib.import_module("stnsnr_normative_fiber_oss_parameter_preflight")


def _write_axon_state(path: Path, statuses: dict[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["x,y,z,fiber_id,status"]
    lines.extend(f"0,0,0,{local_id},{status}" for local_id, status in statuses.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class OSSProbabilisticPAMGenerationTests(unittest.TestCase):
    def test_preflight_rejects_noncanonical_side_modes(self) -> None:
        self.assertTrue(
            PREFLIGHT._transform_left_to_right_for_row(
                {"side": "L", "canonicalization_mode": "left_geometry_to_right"}
            )
        )
        self.assertFalse(
            PREFLIGHT._transform_left_to_right_for_row(
                {"side": "R", "canonicalization_mode": "native_right"}
            )
        )
        with self.assertRaisesRegex(ValueError, "canonicalization"):
            PREFLIGHT._transform_left_to_right_for_row(
                {"side": "L", "canonicalization_mode": "native_left"}
            )
        self.assertEqual(
            PREFLIGHT._canonical_oss_hemi_side(
                {"side": "L", "canonicalization_mode": "left_geometry_to_right"}
            ),
            0,
        )
        self.assertEqual(
            PREFLIGHT._canonical_oss_hemi_side(
                {"side": "R", "canonicalization_mode": "native_right"}
            ),
            0,
        )

    def test_preflight_uses_internal_ten_samples_after_geometry_canonicalization(self) -> None:
        script = PREFLIGHT._matlab_script(
            repo_root=Path("/repo"),
            source_mat=Path("/subject/stim.mat"),
            patient_dir=Path("/subject"),
            row_dir=Path("/run/left"),
            matlab_side_index=2,
            transform_left_to_right=True,
        )

        self.assertEqual(PREFLIGHT.PAM_N_SAMPLES, 10)
        self.assertIn("for sample_i = 1:10", script)
        self.assertIn(
            "butenko_probabilistic_parameter = 'Fiber Diameter'",
            script,
        )
        self.assertIn("butenko_parameter_limits = [1, 4]", script)
        self.assertIn("butenko_sampling_distribution = 'Equidistant'", script)
        self.assertIn("butenko_tensorData = 0", script)
        self.assertIn("ea_updatePAM_parameter(options, settings, outputPaths, sample_i)", script)
        self.assertIn(
            "settings.contactLocation{1} = settings.contactLocation{requested_side_idx}",
            script,
        )
        self.assertIn("settings.Phi_vector(1,:) = settings.Phi_vector(2,:)", script)
        self.assertIn("settings.current_control(1,:) = settings.current_control(2,:)", script)
        self.assertEqual(script.count("SAMPLE_PARAMETER_FILE="), 1)
        self.assertLess(
            script.index("LEFT_TO_RIGHT_TRANSFORM=ea_flip_lr_nonlinear"),
            script.index("ea_updatePAM_parameter(options, settings, outputPaths, sample_i)"),
        )
        parser_dests = {action.dest for action in PREFLIGHT.build_arg_parser()._actions}
        self.assertNotIn("n_samples", parser_dests)

    def test_mocked_commands_run_complete_chain_for_all_ten_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parameter_files = []
            stimulation_folders = []
            for sample_index in range(1, 11):
                parameter_file = root / "parameters" / f"sample_{sample_index:02d}" / "oss-dbs_parameters.mat"
                parameter_file.parent.mkdir(parents=True, exist_ok=True)
                parameter_file.write_bytes(b"sample")
                parameter_files.append(parameter_file)
                stimulation_folders.append(root / "runtime" / f"sample_{sample_index:02d}")

            invocations: list[list[str]] = []

            def fake_runner(**kwargs: object) -> dict[str, object]:
                cmd = list(kwargs["cmd"])
                invocations.append(cmd)
                executable = Path(cmd[0]).name
                if executable == "prepareaxonmodel":
                    hemi_folder = Path(cmd[1]) / "OSS_sim_files_rh"
                    hemi_folder.mkdir(parents=True, exist_ok=True)
                    (hemi_folder / "Allocated_axons.h5").write_bytes(b"h5")
                    (hemi_folder / "Allocated_axons_parameters.json").write_text("{}\n", encoding="utf-8")
                elif executable == "leaddbs2ossdbs":
                    output_path = Path(cmd[cmd.index("--output_path") + 1])
                    parameter_file = Path(cmd[3])
                    output_path.mkdir(parents=True, exist_ok=True)
                    (output_path / f"{parameter_file.stem}.json").write_text(
                        json.dumps(
                            {
                                "StimulationSignal": {"Frequency[Hz]": 999.0},
                                "PointModel": {"Pathway": {}},
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif executable == "ossdbs":
                    settings = json.loads(Path(cmd[1]).read_text(encoding="utf-8"))
                    output_path = Path(settings["OutputPath"])
                    output_path.mkdir(parents=True, exist_ok=True)
                    (output_path / "oss_time_result_PAM.h5").write_bytes(b"h5")
                    (Path(cmd[1]).parent / "success_rh.txt").write_text("ok\n", encoding="utf-8")
                elif executable == "run_pathway_activation":
                    settings = json.loads(Path(cmd[1]).read_text(encoding="utf-8"))
                    sample_index = int(cmd[cmd.index("--scaling_index") + 1])
                    output_path = Path(settings["OutputPath"])
                    (output_path / f"Pathway_status_default_{sample_index}.json").write_text("{}\n", encoding="utf-8")
                    _write_axon_state(
                        output_path / f"Axon_state_default_{sample_index}.csv",
                        {1: 0, 2: 1},
                    )
                else:
                    self.fail(f"unexpected executable: {executable}")
                return {"cmd": cmd, "returncode": 0, "timed_out": False}

            records = ACTIVATION._execute_probabilistic_sample_chain(
                sample_parameter_files=parameter_files,
                sample_stimulation_folders=stimulation_folders,
                source_frequency_hz=130.000000000123,
                prepareaxonmodel_bin=Path("/mock/prepareaxonmodel"),
                converter_bin=Path("/mock/leaddbs2ossdbs"),
                ossdbs_bin=Path("/mock/ossdbs"),
                pathway_activation_bin=Path("/mock/run_pathway_activation"),
                prepareaxon_timeout_s=None,
                converter_timeout_s=None,
                ossdbs_timeout_s=None,
                pathway_timeout_s=None,
                command_runner=fake_runner,
            )

            self.assertEqual(len(records), 10)
            self.assertEqual(len(invocations), 40)
            for executable in (
                "prepareaxonmodel",
                "leaddbs2ossdbs",
                "ossdbs",
                "run_pathway_activation",
            ):
                self.assertEqual(sum(Path(cmd[0]).name == executable for cmd in invocations), 10)
            pathway_commands = [
                cmd for cmd in invocations if Path(cmd[0]).name == "run_pathway_activation"
            ]
            self.assertEqual(
                [int(cmd[cmd.index("--scaling_index") + 1]) for cmd in pathway_commands],
                list(range(1, 11)),
            )
            self.assertTrue(all(cmd[cmd.index("--hemi_side") + 1] == "0" for cmd in invocations if "--hemi_side" in cmd))
            for record in records:
                settings = json.loads(Path(record["converter_json"]).read_text(encoding="utf-8"))
                self.assertEqual(settings["StimulationSignal"]["Frequency[Hz]"], 130.000000000123)

    def test_aggregation_preserves_candidate_order_and_zero_half_one_probabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_paths = []
            for sample_index in range(1, 11):
                path = root / f"Axon_state_default_{sample_index}.csv"
                _write_axon_state(
                    path,
                    {
                        1: 1,
                        2: 1 if sample_index <= 5 else 0,
                        3: 0,
                    },
                )
                sample_paths.append(path)

            candidate_ids = np.asarray([503, 101, 907], dtype=np.int64)
            mapping_rows = [
                {
                    "filtered_local_fiber_id": "3",
                    "candidate_column_index": "1",
                    "selected_candidate_fiber_id": "101",
                },
                {
                    "filtered_local_fiber_id": "1",
                    "candidate_column_index": "2",
                    "selected_candidate_fiber_id": "907",
                },
                {
                    "filtered_local_fiber_id": "2",
                    "candidate_column_index": "0",
                    "selected_candidate_fiber_id": "503",
                },
            ]

            aggregation = ACTIVATION._aggregate_local_activation_probabilities(
                sample_state_paths=sample_paths,
                mapping_rows=mapping_rows,
                candidate_fiber_ids=candidate_ids,
            )

            np.testing.assert_array_equal(aggregation["candidate_fiber_ids"], candidate_ids)
            np.testing.assert_array_equal(aggregation["activated_counts"], np.asarray([5, 0, 10]))
            np.testing.assert_allclose(
                aggregation["activation_probabilities"],
                np.asarray([0.5, 0.0, 1.0], dtype=np.float32),
            )
            self.assertEqual(aggregation["activation_probabilities"].dtype, np.float32)

    def test_incomplete_samples_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_paths = []
            for sample_index in range(1, 10):
                path = root / f"Axon_state_default_{sample_index}.csv"
                _write_axon_state(path, {1: 0})
                sample_paths.append(path)

            with self.assertRaisesRegex(ValueError, "exactly 10"):
                ACTIVATION._aggregate_local_activation_probabilities(
                    sample_state_paths=sample_paths,
                    mapping_rows=[
                        {
                            "filtered_local_fiber_id": "1",
                            "candidate_column_index": "0",
                            "selected_candidate_fiber_id": "101",
                        }
                    ],
                    candidate_fiber_ids=np.asarray([101], dtype=np.int64),
                )

    def test_inconsistent_local_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_paths = []
            for sample_index in range(1, 11):
                path = root / f"Axon_state_default_{sample_index}.csv"
                _write_axon_state(path, {1: 0, **({2: 1} if sample_index != 7 else {})})
                sample_paths.append(path)

            with self.assertRaisesRegex(ValueError, "local fiber IDs"):
                ACTIVATION._aggregate_local_activation_probabilities(
                    sample_state_paths=sample_paths,
                    mapping_rows=[
                        {
                            "filtered_local_fiber_id": "1",
                            "candidate_column_index": "0",
                            "selected_candidate_fiber_id": "101",
                        },
                        {
                            "filtered_local_fiber_id": "2",
                            "candidate_column_index": "1",
                            "selected_candidate_fiber_id": "205",
                        },
                    ],
                    candidate_fiber_ids=np.asarray([101, 205], dtype=np.int64),
                )

    def test_candidate_id_mapping_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_paths = []
            for sample_index in range(1, 11):
                path = root / f"Axon_state_default_{sample_index}.csv"
                _write_axon_state(path, {1: 1})
                sample_paths.append(path)

            with self.assertRaisesRegex(ValueError, "candidate mapping"):
                ACTIVATION._aggregate_local_activation_probabilities(
                    sample_state_paths=sample_paths,
                    mapping_rows=[
                        {
                            "filtered_local_fiber_id": "1",
                            "candidate_column_index": "0",
                            "selected_candidate_fiber_id": "999",
                        }
                    ],
                    candidate_fiber_ids=np.asarray([101], dtype=np.int64),
                )

    def test_row_artifacts_identify_continuous_ten_sample_probabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            row_dir = Path(tmp)
            aggregation = {
                "candidate_fiber_ids": np.asarray([503, 101, 907], dtype=np.int64),
                "activated_counts": np.asarray([5, 0, 10], dtype=np.int64),
                "activation_probabilities": np.asarray([0.5, 0.0, 1.0], dtype=np.float32),
            }
            mapping_rows = [
                {
                    "filtered_local_fiber_id": "2",
                    "candidate_column_index": "0",
                    "selected_candidate_fiber_id": "503",
                },
                {
                    "filtered_local_fiber_id": "3",
                    "candidate_column_index": "1",
                    "selected_candidate_fiber_id": "101",
                },
                {
                    "filtered_local_fiber_id": "1",
                    "candidate_column_index": "2",
                    "selected_candidate_fiber_id": "907",
                },
            ]

            artifacts = ACTIVATION._write_probability_artifacts(
                row={
                    "model_id": "B_DTOR",
                    "subject_id": "sub-01",
                    "side": "L",
                    "canonicalization_mode": "left_geometry_to_right",
                },
                row_index=0,
                row_dir=row_dir,
                aggregation=aggregation,
                mapping_rows=mapping_rows,
                sample_records=[{"sample_index": index} for index in range(1, 11)],
            )

            np.testing.assert_allclose(
                np.load(artifacts["right_canonical_probability_path"]),
                np.asarray([0.5, 0.0, 1.0], dtype=np.float32),
            )
            manifest = json.loads(Path(artifacts["probability_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["pam_n_samples"], 10)
            self.assertEqual(manifest["activation_value_type"], "pPAM_activation_probability")
            self.assertEqual(
                manifest["activation_value_subtype"],
                "empirical_activated_count_over_10_samples",
            )
            self.assertNotIn("deterministic", json.dumps(manifest).lower())

    def test_row_runner_persists_only_complete_probabilistic_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            template_folder = root / "filtered_template"
            template_folder.mkdir()
            converter_json = root / "preflight_parameters.json"
            converter_json.write_text(
                json.dumps(
                    {
                        "StimulationFolder": str(template_folder),
                        "OutputPath": str(template_folder / "OSS_sim_files_rh" / "Results"),
                        "PathwayFile": str(template_folder / "OSS_sim_files_rh" / "Allocated_axons_parameters.json"),
                        "PointModel": {
                            "Pathway": {
                                "FileName": str(template_folder / "OSS_sim_files_rh" / "Allocated_axons.h5")
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            baseline_parameter = root / "oss-dbs_parameters.mat"
            baseline_parameter.write_bytes(b"baseline")
            candidate_ids_path = root / "candidate_ids.npy"
            np.save(candidate_ids_path, np.asarray([503, 101], dtype=np.int64))
            mapping_path = root / "mapping.csv"
            mapping_path.write_text(
                "filtered_local_fiber_id,candidate_column_index,selected_candidate_fiber_id\n"
                "1,0,503\n"
                "2,1,101\n",
                encoding="utf-8",
            )
            sample_parameters = []
            sample_manifest_entries = []
            sample_records = []
            for sample_index in range(1, 11):
                parameter_file = root / "parameters" / f"sample_{sample_index:02d}" / "oss-dbs_parameters.mat"
                parameter_file.parent.mkdir(parents=True, exist_ok=True)
                parameter_file.write_bytes(b"sample")
                sample_parameters.append(parameter_file)
                sample_manifest_entries.append(
                    {"sample_index": sample_index, "parameter_file": str(parameter_file)}
                )
                state_path = root / "states" / f"Axon_state_default_{sample_index}.csv"
                _write_axon_state(
                    state_path,
                    {1: 1 if sample_index <= 5 else 0, 2: 0},
                )
                sample_records.append(
                    {"sample_index": sample_index, "axon_state_path": str(state_path)}
                )
            sample_manifest = root / "sample_manifest.json"
            sample_manifest.write_text(
                json.dumps({"pam_n_samples": 10, "samples": sample_manifest_entries}) + "\n",
                encoding="utf-8",
            )
            row = {
                "model_id": "B_DTOR",
                "subject_id": "sub-01",
                "side": "L",
                "canonicalization_mode": "left_geometry_to_right",
                "converter_json": str(converter_json),
                "parameter_file": str(baseline_parameter),
                "sample_parameter_manifest": str(sample_manifest),
                "source_frequency_hz": "130.0",
                "oss_fiber_ids_path": str(candidate_ids_path),
            }
            filter_metadata = {
                "filter_status": "prepared_filtered_stimulation_folder",
                "local_to_candidate_mapping_path": str(mapping_path),
                "local_to_candidate_mapping_exists": True,
                "local_to_candidate_mapping_n_rows": 2,
                "local_to_candidate_mapping_invalid_candidate_column_count": 0,
                "filtered_stimulation_folder": str(template_folder),
            }
            args = SimpleNamespace(
                prepareaxonmodel_bin="/mock/prepareaxonmodel",
                oss_converter_bin="/mock/leaddbs2ossdbs",
                ossdbs_bin="/mock/ossdbs",
                run_pathway_activation_bin="/mock/run_pathway_activation",
                prepareaxon_timeout_s=0,
                converter_timeout_s=0,
                ossdbs_timeout_s=0,
                pathway_timeout_s=0,
                disable_candidate_filter=False,
            )

            with mock.patch.object(
                ACTIVATION,
                "_prepare_filtered_runtime",
                return_value=(
                    template_folder,
                    baseline_parameter,
                    converter_json,
                    json.loads(converter_json.read_text(encoding="utf-8")),
                    filter_metadata,
                ),
            ), mock.patch.object(
                ACTIVATION,
                "_execute_probabilistic_sample_chain",
                return_value=sample_records,
            ) as execute:
                result = ACTIVATION._run_activation_row(
                    row=row,
                    row_index=0,
                    output_dir=root / "output",
                    args=args,
                )

            self.assertEqual(result["row_status"], "probabilistic_activation_complete")
            self.assertEqual(result["pam_n_samples"], 10)
            self.assertEqual(
                result["activation_value_subtype"],
                "empirical_activated_count_over_10_samples",
            )
            np.testing.assert_allclose(
                np.load(result["right_canonical_probability_path"]),
                np.asarray([0.5, 0.0], dtype=np.float32),
            )
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(len(execute.call_args.kwargs["sample_parameter_files"]), 10)


if __name__ == "__main__":
    unittest.main()
