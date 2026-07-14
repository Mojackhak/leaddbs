"""Stable content and configuration identities for the MRtrix pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping


def file_sha256(path: Path | str, block_size: int = 8 * 1024 * 1024) -> str:
    """Return the SHA-256 content hash of one file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Mapping[str, Any] | list[Any]) -> str:
    """Hash one JSON-compatible value with canonical serialization."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def implementation_hash(paths: Iterable[Path]) -> str:
    """Hash relative names and contents for the implementation file set."""

    normalized = sorted(Path(path).resolve() for path in paths)
    digest = hashlib.sha256()
    common = Path(__file__).resolve().parents[5]
    for path in normalized:
        try:
            name = path.relative_to(common).as_posix()
        except ValueError:
            name = path.as_posix()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def git_head_commit(repo_root: Path | str) -> str:
    """Return the exact current Git HEAD commit for provenance reporting."""

    root = Path(repo_root).resolve()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"cannot resolve Git HEAD under {root}: {exc}") from exc
    commit = result.stdout.strip().lower()
    if result.returncode != 0 or len(commit) != 40 or any(
        character not in "0123456789abcdef" for character in commit
    ):
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"cannot resolve Git HEAD under {root}: {detail}")
    return commit
