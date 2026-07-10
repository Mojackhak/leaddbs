"""Tests for run-local configured ULF component availability."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from outcome_models.services.component_availability import (
    build_run_local_component_availability,
)


class ComponentAvailabilityTests(unittest.TestCase):
    def test_builds_configured_protocol_and_phase_rows_inside_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            derivatives = root / "derivatives"
            stimulation = root / "stimulation.xlsx"
            rows = pd.DataFrame(
                [
                    {
                        "ID": "01",
                        "NameEn": "One",
                        "Phase": "late",
                        "Protocol": "Combined",
                        "Side": "R",
                        "Target": "STN",
                        "Contact": 1,
                        "Frequency": 130,
                        "StimulationPattern": "alternating",
                    },
                    {
                        "ID": "01",
                        "NameEn": "One",
                        "Phase": "late",
                        "Protocol": "Combined",
                        "Side": "R",
                        "Target": "SNr",
                        "Contact": 2,
                        "Frequency": 20,
                        "StimulationPattern": "alternating",
                    },
                    {
                        "ID": "01",
                        "NameEn": "One",
                        "Phase": "unselected",
                        "Protocol": "Combined",
                        "Side": "R",
                        "Target": "SNr",
                        "Contact": 2,
                        "Frequency": 20,
                        "StimulationPattern": "alternating",
                    },
                ]
            )
            rows.to_excel(stimulation, sheet_name="Contact Parameters", index=False)

            output = build_run_local_component_availability(
                stimulation_table=stimulation,
                derivatives_root=derivatives,
                run_root=root / "configured-run",
                addon_protocol="Combined",
                endpoint_phases=("late",),
            )

            configured_run = (root / "configured-run").resolve()
            self.assertTrue(output.csv_path.is_relative_to(configured_run))
            self.assertTrue(output.manifest_path.is_relative_to(configured_run))
            with output.csv_path.open(newline="", encoding="utf-8") as handle:
                observed = list(csv.DictReader(handle))
            self.assertEqual(len(observed), 2)
            self.assertEqual({row["frequency_class"] for row in observed}, {"HF", "ULF"})
            self.assertEqual({row["phase"] for row in observed}, {"late"})
            self.assertEqual({row["protocol"] for row in observed}, {"Combined"})
            self.assertEqual(output.row_count, 2)
            self.assertEqual(len(output.stimulation_table_sha256), 64)

    def test_rejects_duplicate_requested_phases_and_never_uses_legacy_latest_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stimulation = root / "stimulation.csv"
            pd.DataFrame(
                columns=[
                    "ID",
                    "NameEn",
                    "Phase",
                    "Protocol",
                    "Side",
                    "Target",
                    "Contact",
                    "Frequency",
                    "StimulationPattern",
                ]
            ).to_csv(stimulation, index=False)
            with self.assertRaisesRegex(ValueError, "endpoint phases"):
                build_run_local_component_availability(
                    stimulation_table=stimulation,
                    derivatives_root=root / "derivatives",
                    run_root=root / "configured-run",
                    addon_protocol="Combined",
                    endpoint_phases=("late", "late"),
                )


if __name__ == "__main__":
    unittest.main()
