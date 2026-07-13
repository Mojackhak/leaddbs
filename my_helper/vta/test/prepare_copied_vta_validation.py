#!/usr/bin/env python3
"""Prepare an isolated single-subject study base for VTA validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any


_PRODUCTION_LEADDBS_ROOT = Path("/Volumes/VAL/STNSNr/derivatives/leaddbs")


def prepare_validation_copy(
    study_base_path: Path,
    subject_id: str,
    work_root: Path,
    run_id: str,
) -> Path:
    """Return the rewritten validation study-base path."""
    source_study_base = Path(study_base_path).expanduser().resolve()
    validation_root = Path(work_root).expanduser().resolve()
    production_root = _PRODUCTION_LEADDBS_ROOT.resolve()
    if _is_within(validation_root, production_root):
        raise ValueError(
            f"work_root must not be inside the production Lead-DBS tree: "
            f"{validation_root}"
        )
    raw = _read_study_base(source_study_base)
    subjects = raw["study"]["subjects"]
    matches = [subject for subject in subjects if subject.get("subject_id") == subject_id]
    if len(matches) != 1:
        raise ValueError(f"Unknown subject_id: {subject_id}")
    selected = matches[0]

    source_fields = selected["subject_sources"]
    source_subject_dir = _resolve_input_path(
        source_fields["leaddbs_subject_dir"], source_study_base.parent
    )
    source_reconstruction = _resolve_input_path(
        source_fields["electrode_reconstruction"]["path"],
        source_study_base.parent,
    )
    if not source_subject_dir.is_dir():
        raise ValueError(f"Lead-DBS subject directory does not exist: {source_subject_dir}")
    if not source_reconstruction.is_file():
        raise ValueError(f"Reconstruction does not exist: {source_reconstruction}")
    try:
        reconstruction_relative = source_reconstruction.relative_to(source_subject_dir)
    except ValueError as exc:
        raise ValueError(
            "Reconstruction path must be inside the selected Lead-DBS subject directory"
        ) from exc

    run_root = validation_root / f"vta_pipeline_e2e_{run_id}"
    if run_root.exists():
        raise FileExistsError(f"Validation run already exists: {run_root}")
    copied_subject_dir = run_root / "copied_subject" / source_subject_dir.name
    copied_subject_dir.parent.mkdir(parents=True)
    shutil.copytree(source_subject_dir, copied_subject_dir)

    copied_reconstruction = copied_subject_dir / reconstruction_relative
    source_fields["leaddbs_subject_dir"] = str(copied_subject_dir)
    source_fields["electrode_reconstruction"]["path"] = str(
        copied_reconstruction
    )
    raw["study"]["subjects"] = [selected]

    output = run_root / "study_base.json"
    output.write_text(
        json.dumps(raw, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return output.resolve()


def _read_study_base(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        subjects = raw["study"]["subjects"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid study base: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(subjects, list):
        raise ValueError(f"Invalid study base: {path}")
    return raw


def _resolve_input_path(value: Any, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an isolated copied-subject VTA validation input."
    )
    parser.add_argument("--study-base", type=Path, required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output = prepare_validation_copy(
        args.study_base,
        args.subject,
        args.work_root,
        args.run_id,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
