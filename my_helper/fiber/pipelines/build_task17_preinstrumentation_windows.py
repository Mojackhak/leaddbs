#!/usr/bin/env python3
"""Build Task 17 maximum-row windows from terminal cache and guard evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from collections.abc import Sequence


PIPELINES_ROOT = Path(__file__).resolve().parent
if str(PIPELINES_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINES_ROOT))

from validate_task17_preinstrumentation_resources import (
    PreinstrumentationResourceError,
    _write_report,
    build_measurement_windows,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--guard-csv", required=True, type=Path)
    parser.add_argument(
        "--max-rss-bytes",
        type=int,
        default=64 * 1024**3,
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        document = build_measurement_windows(
            arguments.run_root,
            arguments.cache_root,
            arguments.guard_csv,
            max_rss_bytes=arguments.max_rss_bytes,
        )
        _write_report(arguments.output, document)
        print(json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except PreinstrumentationResourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
