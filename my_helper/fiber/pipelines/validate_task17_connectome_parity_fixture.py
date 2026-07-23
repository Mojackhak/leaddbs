#!/usr/bin/env python3
"""Validate retained Task 17 connectome parity authority artifacts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.cache import (
    ContentAddressedCache,
    sha256_file,
)


_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONNECTOMES = frozenset(
    {
        "ppmi_85_ewert_2017",
        "mgh_usc_hcp_32_horn_2017",
        "dtor_985_full_elias_2024",
    }
)
_FREQUENCY_ROLES = frozenset(
    {"reference", "addon_primary", "addon_reference_condition"}
)
_MODEL_FAMILIES = frozenset({"reference_fiber", "addon_fiber"})


class ParityFixtureError(RuntimeError):
    """Raised when retained parity authority is incomplete or inconsistent."""


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ParityFixtureError(f"{label} must be an object")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ParityFixtureError(f"{label} must be an array")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ParityFixtureError(f"{label} fields do not match the fixture schema")


def _token(value: object, label: str, allowed: frozenset[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise ParityFixtureError(f"{label} must be a nonempty string")
    if allowed is not None and value not in allowed:
        raise ParityFixtureError(f"{label} is unsupported: {value}")
    return value


def _sha(value: object, label: str) -> str:
    token = _token(value, label)
    if _SHA256.fullmatch(token) is None:
        raise ParityFixtureError(f"{label} must be a lowercase SHA-256 digest")
    return token


def _shape(value: object, label: str) -> tuple[int, int]:
    values = _sequence(value, label)
    if (
        len(values) != 2
        or any(type(item) is not int or item < 1 for item in values)
    ):
        raise ParityFixtureError(f"{label} must contain two positive integers")
    return int(values[0]), int(values[1])


def _file_uri(uri: object, parent: Path) -> Path:
    parsed = urlparse(_token(uri, "artifact URI"))
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise ParityFixtureError("authority task artifacts must use local file URIs")
    path = Path(unquote(parsed.path)).resolve()
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ParityFixtureError(
            f"authority task artifact escapes the parent run: {path}"
        ) from exc
    if not path.is_file():
        raise ParityFixtureError(f"authority task artifact is missing: {path}")
    return path


def _load_fixture(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParityFixtureError(f"cannot read parity fixture: {path}") from exc
    fixture = _mapping(payload, "fixture")
    _exact_keys(
        fixture,
        {
            "schema_version",
            "authority_run_id",
            "authority_cache_root",
            "physical_fiber_exposures",
            "prepared_omega_max_exposures",
        },
        "fixture",
    )
    if fixture["schema_version"] != "dual_frequency_task17_connectome_parity_fixture_v1":
        raise ParityFixtureError("unsupported parity fixture schema")
    return fixture


def _validate_physical_entries(
    fixture: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    cache_root = Path(
        _token(fixture["authority_cache_root"], "authority_cache_root")
    ).resolve()
    cache = ContentAddressedCache(cache_root)
    rows = _sequence(fixture["physical_fiber_exposures"], "physical entries")
    expected_pairs = {
        (connectome, role)
        for connectome in _CONNECTOMES
        for role in _FREQUENCY_ROLES
    }
    seen: set[tuple[str, str]] = set()
    signatures: dict[str, tuple[str, str]] = {}
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"physical entry {index}")
        _exact_keys(
            row,
            {
                "connectome_id",
                "frequency_role",
                "semantic_sha256",
                "payload_sha256",
                "shape",
            },
            f"physical entry {index}",
        )
        connectome = _token(
            row["connectome_id"], "connectome_id", _CONNECTOMES
        )
        role = _token(row["frequency_role"], "frequency_role", _FREQUENCY_ROLES)
        pair = (connectome, role)
        if pair in seen:
            raise ParityFixtureError(f"duplicate physical fixture row: {pair}")
        seen.add(pair)
        semantic = _sha(row["semantic_sha256"], "semantic_sha256")
        payload_sha = _sha(row["payload_sha256"], "payload_sha256")
        shape = _shape(row["shape"], "physical shape")
        entry = cache.resolve_identity("fiber_exposures", semantic)
        if entry is None:
            raise ParityFixtureError(f"physical cache entry is missing: {semantic}")
        if len(entry.files) != 1 or entry.files[0].relative_path != "exposure.npy":
            raise ParityFixtureError("physical cache entry must contain only exposure.npy")
        cached = entry.files[0]
        if (
            cached.sha256 != payload_sha
            or cached.metadata.dtype != "float32"
            or cached.metadata.shape != shape
        ):
            raise ParityFixtureError(
                f"physical cache metadata differs from fixture: {semantic}"
            )
        signature = (
            entry.key.component_frequency_hash,
            entry.key.stimulation_hash,
        )
        previous = signatures.setdefault(role, signature)
        if previous != signature:
            raise ParityFixtureError(
                f"frequency role has inconsistent cache identity fields: {role}"
            )
        results.append(
            {
                "connectome_id": connectome,
                "frequency_role": role,
                "semantic_sha256": semantic,
                "payload_sha256": payload_sha,
                "shape": list(shape),
                "status": "validated",
            }
        )
    if seen != expected_pairs:
        raise ParityFixtureError("physical fixture does not cover the complete role matrix")
    if len(set(signatures.values())) != len(_FREQUENCY_ROLES):
        raise ParityFixtureError("frequency roles do not have distinct cache identities")
    return results, signatures


def _prepared_authority(parent: Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    tasks = parent / "tasks"
    if not tasks.is_dir():
        raise ParityFixtureError(f"authority parent lacks a tasks directory: {parent}")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path in sorted(tasks.glob("task_*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParityFixtureError(f"cannot read authority task: {path}") from exc
        result = task.get("result")
        if not isinstance(result, dict) or result.get("output_record_type") != (
            "PreparedExposureRecord"
        ):
            continue
        payload = _mapping(result.get("payload"), f"task payload {path.name}")
        endpoint = _mapping(payload.get("endpoint"), f"task endpoint {path.name}")
        family = endpoint.get("model_family")
        connectome = endpoint.get("connectome_id")
        if family not in _MODEL_FAMILIES or connectome not in _CONNECTOMES:
            continue
        grouped.setdefault((family, connectome), []).append(payload)
    return grouped


def _validate_prepared_entries(
    fixture: dict[str, Any],
    parent: Path,
) -> list[dict[str, Any]]:
    rows = _sequence(
        fixture["prepared_omega_max_exposures"], "prepared entries"
    )
    expected_pairs = {
        (family, connectome)
        for family in _MODEL_FAMILIES
        for connectome in _CONNECTOMES
    }
    grouped = _prepared_authority(parent)
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"prepared entry {index}")
        _exact_keys(
            row,
            {
                "model_family",
                "connectome_id",
                "exposure_sha256",
                "feature_ids_sha256",
                "feature_axis_sha256",
                "shape",
            },
            f"prepared entry {index}",
        )
        family = _token(row["model_family"], "model_family", _MODEL_FAMILIES)
        connectome = _token(row["connectome_id"], "connectome_id", _CONNECTOMES)
        pair = (family, connectome)
        if pair in seen:
            raise ParityFixtureError(f"duplicate prepared fixture row: {pair}")
        seen.add(pair)
        expected_exposure = _sha(row["exposure_sha256"], "exposure_sha256")
        expected_ids = _sha(row["feature_ids_sha256"], "feature_ids_sha256")
        expected_axis = _sha(row["feature_axis_sha256"], "feature_axis_sha256")
        expected_shape = _shape(row["shape"], "prepared shape")
        payloads = grouped.get(pair, [])
        if not payloads:
            raise ParityFixtureError(f"prepared authority is missing: {pair}")
        for payload in payloads:
            exposure = _mapping(payload.get("exposure"), "prepared exposure")
            feature_ids = _mapping(payload.get("feature_ids"), "prepared feature IDs")
            feature_axis = _mapping(payload.get("feature_axis"), "prepared feature axis")
            if (
                exposure.get("sha256") != expected_exposure
                or tuple(exposure.get("shape", ())) != expected_shape
                or exposure.get("dtype") != "float32"
                or feature_ids.get("sha256") != expected_ids
                or feature_axis.get("sha256") != expected_axis
            ):
                raise ParityFixtureError(
                    f"prepared authority metadata differs from fixture: {pair}"
                )
            exposure_path = _file_uri(exposure.get("uri"), parent)
            feature_ids_path = _file_uri(feature_ids.get("uri"), parent)
            if sha256_file(exposure_path) != expected_exposure:
                raise ParityFixtureError(
                    f"prepared exposure payload differs from fixture: {exposure_path}"
                )
            if sha256_file(feature_ids_path) != expected_ids:
                raise ParityFixtureError(
                    f"prepared feature IDs differ from fixture: {feature_ids_path}"
                )
        results.append(
            {
                "model_family": family,
                "connectome_id": connectome,
                "exposure_sha256": expected_exposure,
                "feature_ids_sha256": expected_ids,
                "feature_axis_sha256": expected_axis,
                "shape": list(expected_shape),
                "task_count": len(payloads),
                "status": "validated",
            }
        )
    if seen != expected_pairs or set(grouped) != expected_pairs:
        raise ParityFixtureError("prepared authority does not cover the exact model matrix")
    return results


def _write_report(path: Path, report: dict[str, Any]) -> None:
    serialized = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != serialized:
            raise ParityFixtureError(f"existing acceptance report differs: {path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate(fixture_path: Path, parent: Path) -> dict[str, Any]:
    fixture_path = fixture_path.expanduser().resolve()
    parent = parent.expanduser().resolve()
    fixture = _load_fixture(fixture_path)
    authority_run_id = _token(fixture["authority_run_id"], "authority_run_id")
    if parent.name != authority_run_id:
        raise ParityFixtureError("authority parent basename differs from fixture run ID")
    physical, signatures = _validate_physical_entries(fixture)
    prepared = _validate_prepared_entries(fixture, parent)
    return {
        "schema_version": "dual_frequency_task17_parity_authority_report_v1",
        "authority_run_id": authority_run_id,
        "fixture_sha256": sha256_file(fixture_path),
        "physical_fiber_exposures": physical,
        "prepared_omega_max_exposures": prepared,
        "frequency_role_signatures": {
            role: {
                "component_frequency_hash": signature[0],
                "stimulation_hash": signature[1],
            }
            for role, signature in sorted(signatures.items())
        },
        "status": "validated",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate retained Task 17 connectome parity authority artifacts."
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--parent-run", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = validate(arguments.fixture, arguments.parent_run)
        if arguments.output is not None:
            _write_report(arguments.output, report)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except ParityFixtureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
