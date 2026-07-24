#!/usr/bin/env python3
"""Build a terminal SHA-bound Task 17 performance byte ledger."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Sequence

if __package__:
    from .task17_performance_byte_ledger import (
        PerformanceByteLedgerError,
        aggregate_terminal_report,
        read_json,
        sha256_file,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task17_performance_byte_ledger import (
        PerformanceByteLedgerError,
        aggregate_terminal_report,
        read_json,
        sha256_file,
    )


def _inside(path: Path, root: Path, label: str) -> Path:
    path = path.expanduser().resolve()
    root = root.expanduser().resolve()
    if path != root and root not in path.parents:
        raise PerformanceByteLedgerError(f"{label} lies outside the run root")
    return path


def _atomic_write(path: Path, document: dict[str, object]) -> Path:
    text = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise PerformanceByteLedgerError(
                "performance byte-ledger publication differs"
            )
        return path
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def build(
    *,
    run_root: Path,
    segment_id: str,
    output: Path,
) -> Path:
    """Validate terminal evidence and publish one deterministic ledger."""

    run_root = run_root.expanduser().resolve()
    segment_id = str(segment_id).strip()
    if not run_root.is_dir() or not segment_id.startswith("segment_"):
        raise PerformanceByteLedgerError("run root or segment ID is invalid")
    manifest = read_json(run_root / "run_manifest.json", "run manifest")
    if manifest.get("final_status") != "completed":
        raise PerformanceByteLedgerError("performance run is not completed")
    run_id = str(manifest.get("run_id", "")).strip()
    if not run_id:
        raise PerformanceByteLedgerError("performance run ID is missing")
    segment_path = (
        run_root / "execution_segments" / f"{segment_id}.json"
    ).resolve()
    segment = read_json(segment_path, "execution segment")
    if (
        segment.get("segment_id") != segment_id
        or segment.get("status") != "finished"
    ):
        raise PerformanceByteLedgerError(
            "performance execution segment is not finished"
        )
    raw_event_path = Path(str(segment.get("performance_events_path", "")))
    if raw_event_path.is_absolute():
        raise PerformanceByteLedgerError(
            "segment performance-event path must be relative"
        )
    raw_event_path = run_root / raw_event_path
    event_path = _inside(
        raw_event_path,
        run_root,
        "performance event report",
    )
    event_sha = sha256_file(event_path)
    if segment.get("performance_events_sha256") != event_sha:
        raise PerformanceByteLedgerError(
            "segment performance-event SHA differs"
        )
    report = read_json(event_path, "performance event report")
    if report.get("segment_id") != segment_id:
        raise PerformanceByteLedgerError(
            "performance event-report segment differs"
        )
    aggregate = aggregate_terminal_report(report, run_root=run_root)
    document = {
        "schema_version": "dual_frequency_performance_byte_ledger_v1",
        "run_id": run_id,
        "segment_id": segment_id,
        "segment_path": str(segment_path.relative_to(run_root)),
        "segment_sha256": sha256_file(segment_path),
        "event_report_path": str(event_path.relative_to(run_root)),
        "event_report_sha256": event_sha,
        **aggregate,
    }
    return _atomic_write(output, document)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--segment-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        path = build(
            run_root=arguments.run_root,
            segment_id=arguments.segment_id,
            output=arguments.output,
        )
    except PerformanceByteLedgerError as exc:
        print(f"error: {exc}")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
