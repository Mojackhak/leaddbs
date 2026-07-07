#!/usr/bin/env python3
"""Shared lightweight IO helpers for STN/SNr analysis modules."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stnsnr_run_provenance import git_provenance


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not Path(path).is_file():
        return []
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_json(path: Path, data: dict[str, Any], *, add_code_provenance: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    if add_code_provenance and "code_provenance" not in payload:
        payload["code_provenance"] = git_provenance()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_stale_status(path_text: str, current_commit: str) -> str:
    if not path_text:
        return "not_applicable_no_manifest"
    path = Path(path_text)
    if not path.is_file():
        return "missing_manifest"
    data = read_json(path)
    commit = str(data.get("code_provenance", {}).get("git_commit", "") or "")
    if not commit:
        commit = str(data.get("git_provenance", {}).get("head_commit", "") or "")
    if not commit:
        return "missing_code_provenance"
    if not current_commit:
        return "unknown_current_head"
    if commit == current_commit:
        return "current_head"
    return "different_commit"
