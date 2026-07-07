#!/usr/bin/env python3
"""Run provenance helpers for STN/SNr pipeline manifests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def git_provenance(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or default_repo_root()
    dirty_files = run_git(root, ["status", "--short"]).splitlines()
    return {
        "repo_root": str(root),
        "git_branch": run_git(root, ["branch", "--show-current"]),
        "git_commit": run_git(root, ["rev-parse", "HEAD"]),
        "git_short_commit": run_git(root, ["rev-parse", "--short", "HEAD"]),
        "git_dirty": bool(dirty_files),
        "git_dirty_files": dirty_files,
    }
