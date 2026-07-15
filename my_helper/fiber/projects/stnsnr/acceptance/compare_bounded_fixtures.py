"""Read-only comparisons for bounded predecessor and generic-core fixtures."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import nibabel as nib
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ComparisonResult:
    """Structured bounded-fixture comparison outcome."""

    passed: bool
    differences: tuple[str, ...]


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"fixture manifest must be a mapping: {path}")
    return payload


def _task_map(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = payload.get("eligible_tasks", [])
    if not isinstance(rows, list):
        raise ValueError("eligible_tasks must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("eligible task row must be a mapping")
        task_id = str(row.get("task_id", ""))
        if not task_id or task_id in result:
            raise ValueError(f"invalid or duplicate fixture task ID: {task_id}")
        result[task_id] = row
    return result


def _artifact_map(task: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    conversions = task.get("artifact_kind_conversions", {})
    if not isinstance(conversions, Mapping) or any(
        not isinstance(source, str)
        or not source
        or not isinstance(target, str)
        or not target
        for source, target in conversions.items()
    ):
        raise ValueError("artifact_kind_conversions must map non-empty strings")
    rows = task.get("artifacts", [])
    if not isinstance(rows, list):
        raise ValueError("artifacts must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    source_kinds: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("artifact row must be a mapping")
        source_kind = str(row.get("kind", ""))
        source_kinds.add(source_kind)
        kind = str(conversions.get(source_kind, source_kind))
        if not kind or kind in result:
            raise ValueError(f"invalid or duplicate fixture artifact kind: {kind}")
        result[kind] = row
    unknown_conversions = sorted(set(conversions) - source_kinds)
    if unknown_conversions:
        raise ValueError(
            f"artifact kind conversions reference missing kinds: {unknown_conversions}"
        )
    return result


def _tolerances(kind: str, expected: Mapping[str, Any]) -> tuple[float, float]:
    if kind == "oss_activation_probabilities":
        return float(expected.get("rtol", 1e-6)), float(expected.get("atol", 1e-8))
    return float(expected.get("rtol", 1e-8)), float(expected.get("atol", 1e-10))


def _compare_values(
    expected_values: np.ndarray,
    observed_values: np.ndarray,
    *,
    kind: str,
    expected_artifact: Mapping[str, Any],
    differences: list[str],
    label: str,
) -> None:
    if expected_values.shape != observed_values.shape:
        differences.append(
            f"{label}: shape mismatch {expected_values.shape} != {observed_values.shape}"
        )
        return
    comparison = str(expected_artifact.get("comparison", "auto"))
    is_floating = np.issubdtype(expected_values.dtype, np.floating) or np.issubdtype(
        observed_values.dtype, np.floating
    )
    if comparison == "floating" or (comparison == "auto" and is_floating):
        rtol, atol = _tolerances(kind, expected_artifact)
        try:
            np.testing.assert_allclose(
                expected_values,
                observed_values,
                rtol=rtol,
                atol=atol,
                equal_nan=True,
            )
        except AssertionError:
            differences.append(f"{label}: floating array mismatch")
    else:
        try:
            np.testing.assert_array_equal(expected_values, observed_values)
        except AssertionError:
            differences.append(f"{label}: exact array mismatch")


def _compare_array(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    differences: list[str],
    label: str,
    kind: str,
) -> None:
    expected_path = Path(str(expected.get("path", "")))
    observed_path = Path(str(observed.get("path", "")))
    try:
        expected_loaded = np.load(expected_path, allow_pickle=False)
        observed_loaded = np.load(observed_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        differences.append(f"{label}: cannot load array ({exc})")
        return
    if isinstance(expected_loaded, np.lib.npyio.NpzFile) or isinstance(
        observed_loaded, np.lib.npyio.NpzFile
    ):
        if not isinstance(expected_loaded, np.lib.npyio.NpzFile) or not isinstance(
            observed_loaded, np.lib.npyio.NpzFile
        ):
            differences.append(f"{label}: array container mismatch")
            return
        try:
            if set(expected_loaded.files) != set(observed_loaded.files):
                differences.append(f"{label}: NPZ keys differ")
                return
            for key in sorted(expected_loaded.files):
                _compare_values(
                    expected_loaded[key],
                    observed_loaded[key],
                    kind=kind,
                    expected_artifact=expected,
                    differences=differences,
                    label=f"{label}:{key}",
                )
        finally:
            expected_loaded.close()
            observed_loaded.close()
        return
    _compare_values(
        np.asarray(expected_loaded),
        np.asarray(observed_loaded),
        kind=kind,
        expected_artifact=expected,
        differences=differences,
        label=label,
    )


def _compare_csv(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    differences: list[str],
    label: str,
    kind: str,
) -> None:
    try:
        expected_rows = pd.read_csv(Path(str(expected.get("path", ""))))
        observed_rows = pd.read_csv(Path(str(observed.get("path", ""))))
    except (OSError, pd.errors.ParserError) as exc:
        differences.append(f"{label}: cannot read CSV ({exc})")
        return
    if list(expected_rows.columns) != list(observed_rows.columns):
        differences.append(f"{label}: CSV columns differ")
        return
    if expected_rows.shape != observed_rows.shape:
        differences.append(f"{label}: CSV shape differs")
        return
    for column in expected_rows.columns:
        expected_column = expected_rows[column]
        observed_column = observed_rows[column]
        column_label = f"{label}:{column}"
        if pd.api.types.is_numeric_dtype(expected_column.dtype) and pd.api.types.is_numeric_dtype(
            observed_column.dtype
        ):
            _compare_values(
                expected_column.to_numpy(),
                observed_column.to_numpy(),
                kind=kind,
                expected_artifact=expected,
                differences=differences,
                label=column_label,
            )
            continue
        expected_missing = expected_column.isna().to_numpy()
        observed_missing = observed_column.isna().to_numpy()
        if not np.array_equal(expected_missing, observed_missing):
            differences.append(f"{column_label}: missing-value mask differs")
            continue
        try:
            np.testing.assert_array_equal(
                expected_column.to_numpy()[~expected_missing],
                observed_column.to_numpy()[~observed_missing],
            )
        except AssertionError:
            differences.append(f"{column_label}: exact array mismatch")


def _compare_json_value(
    expected: Any,
    observed: Any,
    *,
    differences: list[str],
    label: str,
    kind: str,
    artifact: Mapping[str, Any],
) -> None:
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(expected) != set(observed):
            differences.append(f"{label}: JSON object keys differ")
            return
        for key in sorted(expected):
            _compare_json_value(
                expected[key],
                observed[key],
                differences=differences,
                label=f"{label}.{key}",
                kind=kind,
                artifact=artifact,
            )
        return
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(observed):
            differences.append(f"{label}: JSON list length/type differs")
            return
        for index, (left, right) in enumerate(zip(expected, observed)):
            _compare_json_value(
                left,
                right,
                differences=differences,
                label=f"{label}[{index}]",
                kind=kind,
                artifact=artifact,
            )
        return
    if isinstance(expected, float) and isinstance(observed, (int, float)):
        rtol, atol = _tolerances(kind, artifact)
        try:
            np.testing.assert_allclose(
                expected,
                observed,
                rtol=rtol,
                atol=atol,
                equal_nan=True,
            )
        except AssertionError:
            differences.append(f"{label}: JSON floating value differs")
        return
    if type(expected) is not type(observed) or expected != observed:
        differences.append(f"{label}: JSON exact value differs")


def _compare_json(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    differences: list[str],
    label: str,
    kind: str,
) -> None:
    try:
        left = json.loads(Path(str(expected.get("path", ""))).read_text(encoding="utf-8"))
        right = json.loads(Path(str(observed.get("path", ""))).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        differences.append(f"{label}: cannot read JSON ({exc})")
        return
    _compare_json_value(
        left,
        right,
        differences=differences,
        label=label,
        kind=kind,
        artifact=expected,
    )


def _compare_nifti(
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
    differences: list[str],
    label: str,
    kind: str,
) -> None:
    try:
        left = nib.load(str(expected.get("path", "")))
        right = nib.load(str(observed.get("path", "")))
        left_values = np.asanyarray(left.dataobj)
        right_values = np.asanyarray(right.dataobj)
    except (OSError, ValueError) as exc:
        differences.append(f"{label}: cannot read NIfTI ({exc})")
        return
    _compare_values(
        left_values,
        right_values,
        kind=kind,
        expected_artifact=expected,
        differences=differences,
        label=label,
    )
    try:
        np.testing.assert_allclose(left.affine, right.affine, rtol=0.0, atol=1e-12)
    except AssertionError:
        differences.append(f"{label}: NIfTI affine differs")


def compare_fixture(expected: Path, observed: Path) -> ComparisonResult:
    """Compare two bounded manifests without modifying either fixture."""
    expected_payload = _load(expected)
    observed_payload = _load(observed)
    differences: list[str] = []
    if (
        "schema_version" in expected_payload
        and expected_payload.get("schema_version") != observed_payload.get("schema_version")
    ):
        differences.append(
            "schema_version mismatch "
            f"{expected_payload.get('schema_version')!r} != "
            f"{observed_payload.get('schema_version')!r}"
        )
    expected_tasks = _task_map(expected_payload)
    observed_tasks = _task_map(observed_payload)
    if set(expected_tasks) != set(observed_tasks):
        differences.append(
            "task IDs differ: "
            f"expected={sorted(expected_tasks)} observed={sorted(observed_tasks)}"
        )
        return ComparisonResult(False, tuple(differences))
    exact_task_fields = (
        "task_id",
        "scope_id",
        "endpoint_model_id",
        "parent_scale_id",
        "model_family",
        "source_binding_role",
        "connectome_id",
        "source_connectome_role",
        "target_connectome_roles",
        "branch",
        # Retained aliases keep the comparator useful for early synthetic drafts.
        "scale_id",
        "connectome",
        "execution_stage",
        "status",
    )
    for task_id in sorted(expected_tasks):
        expected_task = expected_tasks[task_id]
        observed_task = observed_tasks[task_id]
        for field in exact_task_fields:
            if field in expected_task and (
                field not in observed_task or expected_task.get(field) != observed_task.get(field)
            ):
                differences.append(
                    f"{task_id}: {field} mismatch "
                    f"{expected_task.get(field)!r} != {observed_task.get(field)!r}"
                )
        expected_artifacts = _artifact_map(expected_task)
        observed_artifacts = _artifact_map(observed_task)
        if set(expected_artifacts) != set(observed_artifacts):
            differences.append(f"{task_id}: artifact kinds differ")
            continue
        for kind in sorted(expected_artifacts):
            expected_artifact = expected_artifacts[kind]
            observed_artifact = observed_artifacts[kind]
            label = f"{task_id}:{kind}"
            expected_path = Path(str(expected_artifact.get("path", "")))
            observed_path = Path(str(observed_artifact.get("path", "")))
            if expected_path.suffix in {".npy", ".npz"}:
                _compare_array(expected_artifact, observed_artifact, differences, label, kind)
            elif expected_path.suffix == ".csv":
                _compare_csv(expected_artifact, observed_artifact, differences, label, kind)
            elif expected_path.suffix == ".json":
                _compare_json(expected_artifact, observed_artifact, differences, label, kind)
            elif expected_path.name.endswith((".nii", ".nii.gz")):
                _compare_nifti(expected_artifact, observed_artifact, differences, label, kind)
            else:
                try:
                    if expected_path.read_bytes() != observed_path.read_bytes():
                        differences.append(f"{label}: exact file mismatch")
                except OSError as exc:
                    differences.append(f"{label}: cannot read file ({exc})")
    return ComparisonResult(not differences, tuple(differences))
