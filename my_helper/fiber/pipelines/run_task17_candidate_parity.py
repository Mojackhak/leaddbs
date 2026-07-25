#!/usr/bin/env python3
"""Validate configured full/fold candidate masks against parent exposures."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np


_ROW_FIELDS_V1 = frozenset(
    {
        "row_id",
        "model_family",
        "tau",
        "coverage",
        "parent_exposure",
        "parent_feature_ids",
        "optimized_exposure",
        "optimized_feature_ids",
    }
)
_ROW_FIELDS_V2 = frozenset(
    {
        "row_id",
        "model_family",
        "tau",
        "coverage",
        "parent_exposure",
        "parent_feature_ids",
        "selected_feature_ids",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {"path", "sha256", "dtype", "shape", "feature_axis_sha256"}
)


class CandidateParityError(RuntimeError):
    """Raised when configured candidate parity cannot be proven."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise CandidateParityError(f"{field} must be a SHA-256 digest")
    return digest


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateParityError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateParityError(f"{label} must contain an object")
    return value


def _artifact(
    raw: object,
    *,
    base: Path,
    label: str,
) -> tuple[np.ndarray, dict[str, object]]:
    if not isinstance(raw, Mapping) or set(raw) != _ARTIFACT_FIELDS:
        raise CandidateParityError(f"{label} fields differ")
    path = Path(str(raw["path"])).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    expected_sha = _digest(raw["sha256"], f"{label} SHA")
    if not path.is_file() or _sha256_file(path) != expected_sha:
        raise CandidateParityError(f"{label} SHA differs")
    try:
        value = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise CandidateParityError(f"{label} is not a readable NPY array") from exc
    shape = raw["shape"]
    if (
        not isinstance(shape, list)
        or any(type(item) is not int or item < 1 for item in shape)
        or tuple(shape) != value.shape
        or str(raw["dtype"]) != value.dtype.name
    ):
        raise CandidateParityError(f"{label} array metadata differs")
    axis_sha = _digest(raw["feature_axis_sha256"], f"{label} feature axis")
    return value, {
        "path": str(path),
        "sha256": expected_sha,
        "dtype": value.dtype.name,
        "shape": list(value.shape),
        "feature_axis_sha256": axis_sha,
    }


def _ordered_ids(value: np.ndarray, label: str) -> np.ndarray:
    ids = np.asarray(value)
    if (
        ids.ndim != 1
        or ids.dtype != np.dtype(np.int64)
        or ids.size < 1
        or np.any(ids[1:] <= ids[:-1])
    ):
        raise CandidateParityError(
            f"{label} must contain ordered unique int64 feature IDs"
        )
    return ids


def _coverage_counts(exposure: np.ndarray, tau: float) -> np.ndarray:
    counts = np.zeros(exposure.shape[1], dtype=np.int32)
    for subject in range(exposure.shape[0]):
        row = np.asarray(exposure[subject], dtype=np.float32)
        if not np.all(np.isfinite(row)) or np.any(row < 0.0):
            raise CandidateParityError(
                "configured exposure contains invalid values"
            )
        counts += row >= tau
    return counts


def _missing_count(
    candidate_parent_ids: np.ndarray,
    optimized_ids: np.ndarray,
) -> int:
    positions = np.searchsorted(optimized_ids, candidate_parent_ids)
    inside = positions < optimized_ids.size
    matched = np.zeros(candidate_parent_ids.size, dtype=bool)
    matched[inside] = (
        optimized_ids[positions[inside]] == candidate_parent_ids[inside]
    )
    return int(np.count_nonzero(~matched))


def _validate_optimized_exposure(
    parent: np.ndarray,
    parent_ids: np.ndarray,
    optimized: np.ndarray,
    optimized_ids: np.ndarray,
) -> np.ndarray:
    positions = np.searchsorted(parent_ids, optimized_ids)
    if (
        np.any(positions >= parent_ids.size)
        or not np.array_equal(parent_ids[positions], optimized_ids)
    ):
        raise CandidateParityError(
            "optimized feature IDs are not an exact parent subset"
        )
    if parent.shape[0] != optimized.shape[0]:
        raise CandidateParityError(
            "parent and optimized subject axes differ"
        )
    for start in range(0, optimized_ids.size, 65_536):
        stop = min(start + 65_536, optimized_ids.size)
        if not np.array_equal(
            np.asarray(parent[:, positions[start:stop]]),
            np.asarray(optimized[:, start:stop]),
        ):
            raise CandidateParityError(
                "optimized exposure differs from its parent columns"
            )
    return positions


def _row_parity(
    raw: object,
    *,
    base: Path,
    plan_schema: str,
    candidate_cache: dict[
        tuple[str, str, float, int],
        tuple[np.ndarray, tuple[np.ndarray, ...]],
    ],
) -> dict[str, object]:
    expected_fields = (
        _ROW_FIELDS_V1
        if plan_schema == "dual_frequency_candidate_parity_plan_v1"
        else _ROW_FIELDS_V2
    )
    if not isinstance(raw, Mapping) or set(raw) != expected_fields:
        raise CandidateParityError("candidate parity row fields differ")
    row_id = str(raw["row_id"]).strip()
    family = str(raw["model_family"]).strip()
    if (
        not row_id
        or family
        not in {
            "reference_voxel",
            "addon_voxel",
            "reference_fiber",
            "addon_fiber",
        }
    ):
        raise CandidateParityError("candidate parity row identity differs")
    tau = raw["tau"]
    coverage = raw["coverage"]
    if (
        not isinstance(tau, (int, float))
        or isinstance(tau, bool)
        or not math.isfinite(float(tau))
        or float(tau) <= 0.0
        or type(coverage) is not int
        or coverage < 1
    ):
        raise CandidateParityError("candidate parity threshold differs")
    parent, parent_evidence = _artifact(
        raw["parent_exposure"],
        base=base,
        label=f"{row_id} parent exposure",
    )
    parent_ids_raw, parent_ids_evidence = _artifact(
        raw["parent_feature_ids"],
        base=base,
        label=f"{row_id} parent feature IDs",
    )
    if parent.ndim != 2 or parent.dtype != np.dtype(np.float32):
        raise CandidateParityError(
            "candidate parity exposures must be float32 matrices"
        )
    parent_ids = _ordered_ids(parent_ids_raw, "parent feature IDs")
    if (
        parent.shape[1] != parent_ids.size
        or parent_evidence["feature_axis_sha256"]
        != parent_ids_evidence["feature_axis_sha256"]
    ):
        raise CandidateParityError(
            "candidate parity feature axes differ"
        )
    if plan_schema == "dual_frequency_candidate_parity_plan_v1":
        optimized, optimized_evidence = _artifact(
            raw["optimized_exposure"],
            base=base,
            label=f"{row_id} optimized exposure",
        )
        optimized_ids_raw, optimized_ids_evidence = _artifact(
            raw["optimized_feature_ids"],
            base=base,
            label=f"{row_id} optimized feature IDs",
        )
        if (
            optimized.ndim != 2
            or optimized.dtype != np.dtype(np.float32)
        ):
            raise CandidateParityError(
                "candidate parity exposures must be float32 matrices"
            )
        optimized_ids = _ordered_ids(
            optimized_ids_raw,
            "optimized feature IDs",
        )
        if (
            optimized.shape[1] != optimized_ids.size
            or optimized_evidence["feature_axis_sha256"]
            != optimized_ids_evidence["feature_axis_sha256"]
        ):
            raise CandidateParityError(
                "candidate parity feature axes differ"
            )
        positions = _validate_optimized_exposure(
            parent,
            parent_ids,
            optimized,
            optimized_ids,
        )
        optimized_counts = _coverage_counts(optimized, float(tau))
        optimized_artifacts = {
            "optimized_exposure": optimized_evidence,
            "optimized_feature_ids": optimized_ids_evidence,
        }
    else:
        optimized_ids_raw, optimized_ids_evidence = _artifact(
            raw["selected_feature_ids"],
            base=base,
            label=f"{row_id} selected feature IDs",
        )
        optimized_ids = _ordered_ids(
            optimized_ids_raw,
            "selected feature IDs",
        )
        positions = np.searchsorted(parent_ids, optimized_ids)
        if (
            np.any(positions >= parent_ids.size)
            or not np.array_equal(parent_ids[positions], optimized_ids)
        ):
            raise CandidateParityError(
                "selected feature IDs are not an exact parent subset"
            )
        optimized_counts = None
        optimized_artifacts = {
            "selected_feature_ids": optimized_ids_evidence,
        }
    cache_key = (
        str(parent_evidence["sha256"]),
        str(parent_ids_evidence["sha256"]),
        float(tau),
        int(coverage),
    )
    if optimized_counts is not None:
        parent_counts = _coverage_counts(parent, float(tau))
        full_parent = parent_counts >= coverage
        full_candidate_ids = np.asarray(parent_ids[full_parent])
        fold_candidate_ids = tuple(
            np.asarray(
                parent_ids[
                    (
                        parent_counts
                        - (np.asarray(parent[heldout]) >= float(tau))
                    )
                    >= coverage
                ]
            )
            for heldout in range(parent.shape[0])
        )
    else:
        cached_candidates = candidate_cache.get(cache_key)
        if cached_candidates is None:
            parent_counts = _coverage_counts(parent, float(tau))
            full_parent = parent_counts >= coverage
            full_candidate_ids = np.asarray(parent_ids[full_parent])
            fold_candidate_ids = tuple(
                np.asarray(
                    parent_ids[
                        (
                            parent_counts
                            - (
                                np.asarray(parent[heldout])
                                >= float(tau)
                            )
                        )
                        >= coverage
                    ]
                )
                for heldout in range(parent.shape[0])
            )
            candidate_cache[cache_key] = (
                full_candidate_ids,
                fold_candidate_ids,
            )
        else:
            full_candidate_ids, fold_candidate_ids = cached_candidates
            parent_counts = None
            full_parent = None
    full_mismatch = (
        int(
            np.count_nonzero(
                (optimized_counts >= coverage)
                != full_parent[positions]
            )
        )
        if optimized_counts is not None
        else 0
    )
    full_missing = _missing_count(full_candidate_ids, optimized_ids)
    fold_mismatch = 0
    fold_missing = 0
    fold_rows: list[dict[str, int]] = []
    for heldout in range(parent.shape[0]):
        mismatch = (
            int(
                np.count_nonzero(
                    (
                        (
                            optimized_counts
                            - (
                                np.asarray(optimized[heldout])
                                >= float(tau)
                            )
                        )
                        >= coverage
                    )
                    != (
                        (
                            parent_counts
                            - (
                                np.asarray(parent[heldout])
                                >= float(tau)
                            )
                        )
                        >= coverage
                    )[positions]
                )
            )
            if optimized_counts is not None
            else 0
        )
        missing = _missing_count(
            fold_candidate_ids[heldout],
            optimized_ids,
        )
        fold_mismatch += mismatch
        fold_missing += missing
        fold_rows.append(
            {
                "heldout_index": heldout,
                "candidate_mismatch_count": mismatch,
                "candidate_false_negative_count": missing,
            }
        )
    return {
        "row_id": row_id,
        "model_family": family,
        "tau": float(tau),
        "coverage": coverage,
        "subject_count": int(parent.shape[0]),
        "parent_feature_count": int(parent.shape[1]),
        "optimized_feature_count": int(optimized_ids.size),
        "full_candidate_mismatch_count": full_mismatch,
        "fold_candidate_mismatch_count": fold_mismatch,
        "candidate_false_negative_count": full_missing + fold_missing,
        "full_candidate_false_negative_count": full_missing,
        "fold_candidate_false_negative_count": fold_missing,
        "folds": fold_rows,
        "artifacts": {
            "parent_exposure": parent_evidence,
            "parent_feature_ids": parent_ids_evidence,
            **optimized_artifacts,
        },
    }


def _atomic_publish(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(
        dict(payload),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise CandidateParityError(
                "candidate parity report differs from existing publication"
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(plan_path: Path, output: Path | None = None) -> Path:
    """Execute one configured candidate-parity plan."""

    plan_path = plan_path.expanduser().resolve()
    plan = _read_json(plan_path, "candidate parity plan")
    if set(plan) != {"schema_version", "rows"}:
        raise CandidateParityError("candidate parity plan fields differ")
    plan_schema = str(plan.get("schema_version", ""))
    if plan_schema not in {
        "dual_frequency_candidate_parity_plan_v1",
        "dual_frequency_candidate_parity_plan_v2",
    }:
        raise CandidateParityError("candidate parity plan schema differs")
    raw_rows = plan.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise CandidateParityError("candidate parity plan rows differ")
    candidate_cache: dict[
        tuple[str, str, float, int],
        tuple[np.ndarray, tuple[np.ndarray, ...]],
    ] = {}
    rows = [
        _row_parity(
            row,
            base=plan_path.parent,
            plan_schema=plan_schema,
            candidate_cache=candidate_cache,
        )
        for row in raw_rows
    ]
    row_ids = [str(row["row_id"]) for row in rows]
    if len(set(row_ids)) != len(row_ids):
        raise CandidateParityError("candidate parity row IDs are duplicated")
    rows.sort(key=lambda row: str(row["row_id"]))
    report = {
        "schema_version": "dual_frequency_candidate_parity_v1",
        "plan_path": str(plan_path),
        "plan_sha256": _sha256_file(plan_path),
        "row_count": len(rows),
        "full_candidate_mismatch_count": sum(
            int(row["full_candidate_mismatch_count"]) for row in rows
        ),
        "fold_candidate_mismatch_count": sum(
            int(row["fold_candidate_mismatch_count"]) for row in rows
        ),
        "candidate_false_negative_count": sum(
            int(row["candidate_false_negative_count"]) for row in rows
        ),
        "rows": rows,
    }
    destination = (
        plan_path.with_name(f"{plan_path.stem}.report.json")
        if output is None
        else output.expanduser().resolve()
    )
    _atomic_publish(destination, report)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    output = run(arguments.plan, arguments.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
