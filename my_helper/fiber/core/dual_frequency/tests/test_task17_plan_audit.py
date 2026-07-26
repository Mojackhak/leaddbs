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
BACKTICKED_TEXT = re.compile(r"`([^`\n]+)`")
NON_REQUIREMENT_REFERENCES = frozenset({"ACTIVE", "PENDING"})
EVIDENCE_STATUSES = frozenset({"ACCEPTED", "ACTIVE", "PENDING", "BLOCKED"})
FINAL_AUDIT_LABEL = "Final three-plan requirement audit"
PLAN_PATH_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".m", ".csv")
MOVED_PRODUCTION_ENTRYPOINT = Path(
    "my_helper/fiber/pipelines/run_configured_outcome_models.py"
)
LEGACY_CONFIGURED_ENTRYPOINT = Path(
    "my_helper/fiber/projects/stnsnr/legacy/run_configured_outcome_models.py"
)
WORKTREE_LOCAL_REFERENCES = frozenset(
    {
        Path(
            "my_helper/fiber/projects/stnsnr/acceptance/"
            "approved_task_allowlist.json"
        )
    }
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _primary_checkout_root() -> Path:
    git_marker = REPOSITORY_ROOT / ".git"
    if git_marker.is_dir():
        return REPOSITORY_ROOT
    if not git_marker.is_file():
        raise AssertionError(f"missing Git metadata: {git_marker}")
    marker = git_marker.read_text(encoding="utf-8").strip()
    prefix = "gitdir: "
    if not marker.startswith(prefix):
        raise AssertionError(f"invalid Git worktree marker: {git_marker}")
    git_directory = Path(marker.removeprefix(prefix))
    if not git_directory.is_absolute():
        git_directory = (REPOSITORY_ROOT / git_directory).resolve()
    for candidate in (git_directory, *git_directory.parents):
        if candidate.name == ".git":
            return candidate.parent
    raise AssertionError(f"cannot resolve primary checkout from {git_directory}")


def _reference_exists(reference: Path) -> bool:
    if (REPOSITORY_ROOT / reference).exists():
        return True
    if reference not in WORKTREE_LOCAL_REFERENCES:
        return False
    primary_root = _primary_checkout_root()
    return primary_root != REPOSITORY_ROOT and (primary_root / reference).is_file()


def _open_items(path: Path) -> tuple[str, ...]:
    return tuple(OPEN_CHECKBOX.findall(_read(path)))


def _repository_file_references(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    repository_prefix = f"{REPOSITORY_ROOT}/"
    references: set[Path] = set()
    for path in paths:
        for candidate in BACKTICKED_TEXT.findall(_read(path)):
            candidate = candidate.strip()
            if candidate.startswith(repository_prefix):
                candidate = candidate.removeprefix(repository_prefix)
            if (
                "\n" in candidate
                or not candidate.startswith("my_helper/")
                or any(character.isspace() for character in candidate)
                or any(character in candidate for character in "*?[]")
                or not candidate.endswith(PLAN_PATH_SUFFIXES)
            ):
                continue
            reference = Path(candidate)
            if reference.is_absolute() or ".." in reference.parts:
                raise AssertionError(f"unsafe repository path reference: {candidate}")
            references.add(reference)
    return tuple(sorted(references))


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

    def test_evidence_matrix_status_and_final_closure_are_consistent(self) -> None:
        self.assertEqual(len(self.evidence_rows), 24)
        self.assertTrue(all(len(row) == 4 for row in self.evidence_rows))
        statuses = {row[0]: row[1] for row in self.evidence_rows}
        self.assertEqual(len(statuses), len(self.evidence_rows))
        self.assertTrue(set(statuses.values()) <= EVIDENCE_STATUSES)
        self.assertIn(FINAL_AUDIT_LABEL, statuses)

        other_rows_are_open = any(
            status != "ACCEPTED"
            for label, status in statuses.items()
            if label != FINAL_AUDIT_LABEL
        )
        if other_rows_are_open:
            self.assertNotEqual(statuses[FINAL_AUDIT_LABEL], "ACCEPTED")
        else:
            self.assertEqual(statuses[FINAL_AUDIT_LABEL], "ACCEPTED")

    def test_source_plan_file_references_remain_resolvable(self) -> None:
        references = _repository_file_references(
            (FOUR_MODEL_PLAN, DUAL_FREQUENCY_PLAN, POSTPROCESS_PLAN)
        )
        self.assertEqual(len(references), 123)
        missing = tuple(
            reference
            for reference in references
            if not _reference_exists(reference)
        )
        self.assertEqual(missing, (MOVED_PRODUCTION_ENTRYPOINT,))
        self.assertFalse((REPOSITORY_ROOT / MOVED_PRODUCTION_ENTRYPOINT).exists())
        self.assertTrue((REPOSITORY_ROOT / LEGACY_CONFIGURED_ENTRYPOINT).is_file())


if __name__ == "__main__":
    unittest.main()
