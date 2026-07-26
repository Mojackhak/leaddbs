"""Structural guards for the Task 17 three-plan acceptance ledger."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
STNSNR_ROOT = REPOSITORY_ROOT / "my_helper/stnsnr"
DUAL_FREQUENCY_PLAN = (
    STNSNR_ROOT / "dual_frequency_core_decoupling_implementation_plan.md"
)
FOUR_MODEL_PLAN = STNSNR_ROOT / "four_model_yaml_core_refactor_plan.md"
POSTPROCESS_PLAN = STNSNR_ROOT / "postprocess_visualization_implementation_plan.md"
ACCEPTANCE_AUDIT = STNSNR_ROOT / "task17_three_plan_acceptance_audit.md"

OPEN_CHECKBOX = re.compile(r"^\s*-\s+\[ \]\s+(.+)$", re.MULTILINE)
STEP_NUMBER = re.compile(r"(?:\*\*)?Step\s+(\d+)\b")
BACKTICKED_TEXT = re.compile(r"`([^`]+)`")
NON_REQUIREMENT_REFERENCES = frozenset({"ACTIVE", "PENDING"})


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _open_items(path: Path) -> tuple[str, ...]:
    return tuple(OPEN_CHECKBOX.findall(_read(path)))


def _section(document: str, start: str, end: str) -> str:
    before, separator, remainder = document.partition(start)
    if not separator:
        raise AssertionError(f"missing section heading: {start}")
    del before
    body, separator, _ = remainder.partition(end)
    if not separator:
        raise AssertionError(f"missing section heading: {end}")
    return body


def _table_rows(section: str, header_label: str) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    table_started = False
    for line in section.splitlines():
        if not line.startswith("|"):
            if table_started and rows:
                break
            continue
        cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        if not table_started:
            if cells and cells[0] == header_label:
                table_started = True
            continue
        if (
            not cells
            or set(cells[0]) <= {"-", ":", " "}
        ):
            continue
        rows.append(cells)
    if not table_started:
        raise AssertionError(f"missing table header: {header_label}")
    return tuple(rows)


class Task17PlanAuditTest(unittest.TestCase):
    """Keep every open plan item visible in the acceptance evidence ledger."""

    def setUp(self) -> None:
        document = _read(ACCEPTANCE_AUDIT)
        self.evidence_rows = _table_rows(
            _section(
                document,
                "## Evidence Matrix",
                "## Open Implementation-Step Mapping",
            ),
            "Requirement",
        )
        self.mapping_rows = _table_rows(
            _section(
                document,
                "## Open Implementation-Step Mapping",
                "## Repository Entrypoint Preflight",
            ),
            "Source-plan item",
        )

    def test_every_open_source_item_has_one_mapping_row(self) -> None:
        self.assertEqual(_open_items(FOUR_MODEL_PLAN), ())
        self.assertEqual(_open_items(POSTPROCESS_PLAN), ())

        source_items = _open_items(DUAL_FREQUENCY_PLAN)
        mapping_labels = tuple(row[0] for row in self.mapping_rows)
        self.assertEqual(len(mapping_labels), len(source_items))
        self.assertEqual(len(mapping_labels), len(set(mapping_labels)))

    def test_open_step_numbers_match_mapped_step_numbers(self) -> None:
        source_steps = tuple(
            int(match.group(1))
            for item in _open_items(DUAL_FREQUENCY_PLAN)
            if (match := STEP_NUMBER.search(item)) is not None
        )
        mapped_steps = tuple(
            int(match.group(1))
            for row in self.mapping_rows
            if (match := STEP_NUMBER.search(row[0])) is not None
        )
        self.assertEqual(mapped_steps, source_steps)

    def test_mapping_references_existing_evidence_rows(self) -> None:
        evidence_labels = tuple(row[0] for row in self.evidence_rows)
        self.assertEqual(len(evidence_labels), len(set(evidence_labels)))
        known_labels = set(evidence_labels)

        missing: list[str] = []
        for row in self.mapping_rows:
            self.assertGreaterEqual(len(row), 2)
            for reference in BACKTICKED_TEXT.findall(row[1]):
                if (
                    reference not in NON_REQUIREMENT_REFERENCES
                    and reference not in known_labels
                ):
                    missing.append(f"{row[0]} -> {reference}")

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
