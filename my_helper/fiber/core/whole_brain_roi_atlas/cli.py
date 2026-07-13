"""Command-line interface for whole-brain ROI atlas construction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .config import load_atlas_config
from .pipeline import build_whole_brain_roi_atlas, inspect_atlas_status, validate_atlas_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="whole-brain-roi-atlas")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build"):
        command = subcommands.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
    status = subcommands.add_parser("status")
    status.add_argument("--atlas-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CLI command and emit stable JSON."""

    arguments = _parser().parse_args(argv)
    if arguments.command == "validate":
        payload = validate_atlas_config(load_atlas_config(arguments.config))
    elif arguments.command == "build":
        result = build_whole_brain_roi_atlas(load_atlas_config(arguments.config))
        payload = {
            "status": "complete",
            "atlas_root": str(result.atlas_root),
            "build_fingerprint": result.build_fingerprint,
            "label_count": result.label_count,
            "main_roi_count": result.main_roi_count,
            "white_matter_roi_count": result.white_matter_roi_count,
            "n_fibers": result.n_fibers,
            "n_endpoints": result.n_endpoints,
            "reused": result.reused,
        }
    else:
        payload = inspect_atlas_status(arguments.atlas_root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
