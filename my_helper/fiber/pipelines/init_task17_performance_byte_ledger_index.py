#!/usr/bin/env python3
"""Initialize a static live Task 17 performance byte-ledger index."""

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
        read_json,
    )
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from task17_performance_byte_ledger import (
        PerformanceByteLedgerError,
        read_json,
    )


def initialize(*, run_root: Path, output: Path) -> Path:
    """Validate one run root and atomically publish its immutable live index."""

    run_root = run_root.expanduser().resolve()
    output = output.expanduser().resolve()
    if not run_root.is_dir():
        raise PerformanceByteLedgerError("performance run root is missing")
    manifest = read_json(run_root / "run_manifest.json", "run manifest")
    if (
        manifest.get("schema_version") != "dual_frequency_run_v1"
        or not str(manifest.get("run_id", "")).strip()
        or manifest.get("final_status") not in {"running", "completed", "failed"}
    ):
        raise PerformanceByteLedgerError("performance run manifest differs")
    if output == run_root or run_root in output.parents:
        raise PerformanceByteLedgerError(
            "performance byte-ledger index must be stored outside the run root"
        )
    document = {
        "schema_version": "dual_frequency_performance_byte_ledger_index_v1",
        "run_root": str(run_root),
    }
    text = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8") != text:
            raise PerformanceByteLedgerError(
                "performance byte-ledger index differs"
            )
        return output
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        path = initialize(
            run_root=arguments.run_root,
            output=arguments.output,
        )
    except PerformanceByteLedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
