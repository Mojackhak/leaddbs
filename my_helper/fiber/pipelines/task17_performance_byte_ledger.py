"""Validate and aggregate repository-owned Task 17 byte-counter fragments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path


class PerformanceByteLedgerError(RuntimeError):
    """Raised when byte-counter provenance is incomplete or contradictory."""


class LivePerformanceByteLedger:
    """Incrementally read new fragments and fully revalidate at runner exit."""

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path.expanduser().resolve()
        index = read_json(
            self.index_path,
            "performance byte-ledger index",
        )
        if set(index) != {"schema_version", "run_root"} or (
            index.get("schema_version")
            != "dual_frequency_performance_byte_ledger_index_v1"
        ):
            raise PerformanceByteLedgerError(
                "performance byte-ledger index fields differ"
            )
        self.run_root = Path(str(index["run_root"])).expanduser().resolve()
        if not self.run_root.is_dir():
            raise PerformanceByteLedgerError(
                "performance byte-ledger run root is missing"
            )
        self._fragments: dict[str, dict[str, object]] = {}
        self._source_bytes = 0
        self._scratch_bytes = 0

    def read(self, *, final: bool = False) -> tuple[int, int]:
        """Return accumulated totals, with one full final closure validation."""

        visible = {
            path.resolve()
            for path in (self.run_root / "work").glob(
                "task_*/attempt-*/performance_counter_fragment.json"
            )
        }
        known_paths = {
            (self.run_root / relative).resolve()
            for relative in self._fragments
        }
        if not known_paths.issubset(visible):
            raise PerformanceByteLedgerError(
                "an observed performance fragment disappeared"
            )
        for path in sorted(visible - known_paths):
            fragment = fragment_byte_counters(
                path,
                run_root=self.run_root,
            )
            relative = str(fragment["path"])
            if relative in self._fragments:
                raise PerformanceByteLedgerError(
                    "performance fragment path is duplicated"
                )
            self._fragments[relative] = fragment
            self._source_bytes += int(fragment["source_bytes"])
            self._scratch_bytes += int(fragment["scratch_bytes"])
        if final:
            complete = aggregate_live_index(self.index_path)
            complete_fragments = {
                str(item["path"]): item
                for item in complete["fragments"]
                if isinstance(item, Mapping)
            }
            if (
                len(complete_fragments) != len(complete["fragments"])
                or complete_fragments != self._fragments
                or int(complete["source_bytes"]) != self._source_bytes
                or int(complete["scratch_bytes"]) != self._scratch_bytes
            ):
                raise PerformanceByteLedgerError(
                    "terminal byte-ledger rescan differs from incremental state"
                )
        return self._source_bytes, self._scratch_bytes


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path, label: str) -> dict[str, object]:
    """Read one JSON object or fail with a provenance-specific error."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PerformanceByteLedgerError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise PerformanceByteLedgerError(f"{label} must contain an object")
    return value


def _digest(value: object, label: str) -> str:
    token = str(value).strip().lower()
    if len(token) != 64 or any(
        character not in "0123456789abcdef" for character in token
    ):
        raise PerformanceByteLedgerError(f"{label} must be a SHA-256 digest")
    return token


def _nonnegative(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PerformanceByteLedgerError(
            f"{label} must be a nonnegative integer"
        )
    return value


def _relative_fragment_path(path: Path, run_root: Path) -> tuple[str, str]:
    try:
        relative = path.relative_to(run_root)
    except ValueError as exc:
        raise PerformanceByteLedgerError(
            f"performance fragment lies outside the run root: {path}"
        ) from exc
    parts = relative.parts
    if (
        len(parts) != 4
        or parts[0] != "work"
        or not parts[1].startswith("task_")
        or not parts[2].startswith("attempt-")
        or parts[3] != "performance_counter_fragment.json"
    ):
        raise PerformanceByteLedgerError(
            f"performance fragment path differs from the attempt contract: {path}"
        )
    return relative.as_posix(), parts[1]


def fragment_byte_counters(
    path: Path,
    *,
    run_root: Path,
    expected_task_id: str | None = None,
    expected_process_identity: str | None = None,
    expected_sha256: str | None = None,
) -> dict[str, object]:
    """Validate one immutable task fragment and return its byte deltas."""

    path = path.expanduser().resolve()
    run_root = run_root.expanduser().resolve()
    relative, path_task_id = _relative_fragment_path(path, run_root)
    if not path.is_file():
        raise PerformanceByteLedgerError(
            f"performance fragment is missing: {path}"
        )
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != _digest(
        expected_sha256,
        "performance fragment SHA",
    ):
        raise PerformanceByteLedgerError(
            f"performance fragment SHA differs: {path}"
        )
    document = read_json(path, "performance fragment")
    process_identity = str(document.get("process_identity", "")).strip()
    task_id = str(document.get("task_id", "")).strip()
    events = document.get("events")
    if (
        document.get("schema_version")
        != "dual_frequency_performance_counter_fragment_v1"
        or not process_identity
        or not task_id
        or task_id != path_task_id
        or (expected_task_id is not None and task_id != expected_task_id)
        or (
            expected_process_identity is not None
            and process_identity != expected_process_identity
        )
        or not isinstance(events, Mapping)
        or events.get("process_identity") != process_identity
    ):
        raise PerformanceByteLedgerError(
            f"performance fragment identity differs: {path}"
        )
    scalars = events.get("scalars")
    if not isinstance(scalars, Mapping):
        raise PerformanceByteLedgerError(
            f"performance fragment scalar closure differs: {path}"
        )
    return {
        "task_id": task_id,
        "process_identity": process_identity,
        "path": relative,
        "sha256": digest,
        "source_bytes": _nonnegative(
            scalars.get("source_bytes"),
            "source bytes",
        ),
        "scratch_bytes": _nonnegative(
            scalars.get("scratch_bytes"),
            "scratch bytes",
        ),
    }


def aggregate_live_index(index_path: Path) -> dict[str, object]:
    """Derive current byte totals from all atomically visible attempts."""

    index_path = index_path.expanduser().resolve()
    index = read_json(index_path, "performance byte-ledger index")
    if set(index) != {"schema_version", "run_root"} or (
        index.get("schema_version")
        != "dual_frequency_performance_byte_ledger_index_v1"
    ):
        raise PerformanceByteLedgerError(
            "performance byte-ledger index fields differ"
        )
    run_root = Path(str(index["run_root"])).expanduser().resolve()
    if not run_root.is_dir():
        raise PerformanceByteLedgerError(
            "performance byte-ledger run root is missing"
        )
    fragments = [
        fragment_byte_counters(path, run_root=run_root)
        for path in sorted(
            (run_root / "work").glob(
                "task_*/attempt-*/performance_counter_fragment.json"
            )
        )
    ]
    identities: set[tuple[str, str, str]] = set()
    for fragment in fragments:
        identity = (
            str(fragment["process_identity"]),
            str(fragment["task_id"]),
            str(fragment["path"]),
        )
        if identity in identities:
            raise PerformanceByteLedgerError(
                "performance fragment identity is duplicated"
            )
        identities.add(identity)
    return {
        "run_root": str(run_root),
        "fragment_count": len(fragments),
        "source_bytes": sum(int(item["source_bytes"]) for item in fragments),
        "scratch_bytes": sum(int(item["scratch_bytes"]) for item in fragments),
        "fragments": fragments,
    }


def aggregate_terminal_report(
    report: Mapping[str, object],
    *,
    run_root: Path,
) -> dict[str, object]:
    """Derive terminal byte totals from an exact event-report closure."""

    if (
        report.get("schema_version")
        != "dual_frequency_performance_event_report_v1"
        or report.get("aggregation_status") != "complete"
        or report.get("missing_fragment_count") != 0
    ):
        raise PerformanceByteLedgerError(
            "performance event report is incomplete"
        )
    raw_fragments = report.get("fragments")
    if not isinstance(raw_fragments, Sequence) or isinstance(
        raw_fragments,
        (str, bytes),
    ):
        raise PerformanceByteLedgerError(
            "performance event-report fragment closure differs"
        )
    if report.get("fragment_count") != len(raw_fragments):
        raise PerformanceByteLedgerError(
            "performance event-report fragment count differs"
        )
    fragments: list[dict[str, object]] = []
    identities: set[tuple[str, str, str]] = set()
    for index, reference in enumerate(raw_fragments):
        if not isinstance(reference, Mapping) or set(reference) != {
            "task_id",
            "process_identity",
            "path",
            "sha256",
        }:
            raise PerformanceByteLedgerError(
                f"performance fragment reference differs: {index}"
            )
        path = Path(str(reference["path"])).expanduser().resolve()
        fragment = fragment_byte_counters(
            path,
            run_root=run_root,
            expected_task_id=str(reference["task_id"]),
            expected_process_identity=str(reference["process_identity"]),
            expected_sha256=str(reference["sha256"]),
        )
        identity = (
            str(fragment["process_identity"]),
            str(fragment["task_id"]),
            str(fragment["path"]),
        )
        if identity in identities:
            raise PerformanceByteLedgerError(
                "performance event-report fragment is duplicated"
            )
        identities.add(identity)
        fragments.append(fragment)
    return {
        "fragment_count": len(fragments),
        "source_bytes": sum(int(item["source_bytes"]) for item in fragments),
        "scratch_bytes": sum(int(item["scratch_bytes"]) for item in fragments),
        "fragments": fragments,
    }


__all__ = [
    "LivePerformanceByteLedger",
    "PerformanceByteLedgerError",
    "aggregate_live_index",
    "aggregate_terminal_report",
    "fragment_byte_counters",
    "read_json",
    "sha256_file",
]
