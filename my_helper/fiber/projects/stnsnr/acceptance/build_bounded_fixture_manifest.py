"""Build a deterministic manifest from explicitly reviewed predecessor tasks."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping


class FixtureManifestError(ValueError):
    """Raised when frozen predecessor evidence violates the reviewed contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureManifestError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise FixtureManifestError(f"{label} must be a JSON object")
    return payload


def _load_csv(path: Path, label: str) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except OSError as exc:
        raise FixtureManifestError(f"cannot read {label}: {path}") from exc


def _unique_by(rows: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        if not value:
            raise FixtureManifestError(f"{label} row has no {key}")
        if value in result:
            raise FixtureManifestError(f"duplicate {key} in {label}: {value}")
        result[value] = row
    return result


def _inside_run(run_root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise FixtureManifestError(f"artifact path must be run-relative: {relative_path}")
    path = (run_root / relative_path).resolve()
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise FixtureManifestError(f"artifact path is outside the frozen run: {relative_path}") from exc
    return path


def _validate_artifact(
    run_root: Path,
    row: Mapping[str, str],
    *,
    task_id: str,
) -> dict[str, Any]:
    relative_path = str(row.get("relative_path", "")).strip()
    path = _inside_run(run_root, relative_path)
    if not path.is_file():
        raise FixtureManifestError(f"allowlisted artifact is missing: {relative_path}")
    expected_hash = str(row.get("sha256", "")).strip().lower()
    actual_hash = _sha256(path)
    if actual_hash != expected_hash:
        raise FixtureManifestError(
            f"artifact SHA-256 mismatch for {task_id}:{row.get('kind', '')}:{relative_path}"
        )
    try:
        expected_size = int(str(row.get("size_bytes", "")))
    except ValueError as exc:
        raise FixtureManifestError(f"invalid artifact size for {relative_path}") from exc
    if path.stat().st_size != expected_size:
        raise FixtureManifestError(f"artifact size mismatch for {relative_path}")
    return {
        "kind": str(row.get("kind", "")),
        "relative_path": relative_path,
        "path": str(path),
        "sha256": actual_hash,
        "size_bytes": expected_size,
    }


def _task_identity(spec: Mapping[str, Any]) -> dict[str, str]:
    endpoint = spec.get("endpoint")
    if not isinstance(endpoint, Mapping):
        raise FixtureManifestError(f"task {spec.get('task_id', '')} has no endpoint mapping")
    return {
        "execution_stage": str(spec.get("execution_stage", "")),
        "model_family": str(endpoint.get("model_family", "")),
        "scale_id": str(endpoint.get("scale_id", "")),
        "connectome": str(endpoint.get("connectome", "none")),
        "branch": str(spec.get("branch", "none")),
    }


def _validate_allowlist_identity(
    allowlist: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
) -> None:
    source = allowlist.get("source_run")
    if not isinstance(source, Mapping):
        raise FixtureManifestError("approved task allowlist source_run must be a mapping")
    expected = {
        "run_id": str(run_manifest.get("run_id", "")),
        "commit": str(
            (run_manifest.get("code_provenance") or {}).get("commit", "")
        ),
        "configuration_hash": str(run_manifest.get("configuration_hash", "")),
        "provenance_hash": str(run_manifest.get("provenance_hash", "")),
        "status": str(run_manifest.get("status", "")),
    }
    for key, value in expected.items():
        if str(source.get(key, "")) != value:
            raise FixtureManifestError(f"allowlist {key} does not match the frozen run")
    dirty = (run_manifest.get("code_provenance") or {}).get("dirty")
    if source.get("dirty") is not dirty:
        raise FixtureManifestError("allowlist dirty state does not match the frozen run")
    if dirty is not False:
        raise FixtureManifestError("bounded predecessor evidence requires a clean source run")


def _flatten_scopes(allowlist: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    scopes = allowlist.get("scopes")
    if not isinstance(scopes, list) or not scopes:
        raise FixtureManifestError("approved task allowlist must contain scopes")
    scope_by_id = _unique_by(scopes, "scope_id", "approved task allowlist scopes")
    allowed_by_id: dict[str, dict[str, Any]] = {}
    valid_source_roles = {"formal", "observed_robustness", "not_applicable"}
    valid_target_roles = {
        "primary_formal",
        "activation_sensitivity_enabled",
        "observed_robustness",
    }
    for scope_id in sorted(scope_by_id):
        scope = scope_by_id[scope_id]
        required = (
            "source_endpoints",
            "parent_scale_id",
            "model_family",
            "source_binding_role",
            "source_connectome_role",
            "target_connectome_roles",
        )
        missing = [key for key in required if key not in scope]
        if missing:
            raise FixtureManifestError(
                f"allowlist scope {scope_id} is missing fields: {', '.join(missing)}"
            )
        if scope["source_binding_role"] not in {"reference", "combined"}:
            raise FixtureManifestError(f"invalid source binding role in scope {scope_id}")
        if scope["source_connectome_role"] not in valid_source_roles:
            raise FixtureManifestError(f"invalid source connectome role in scope {scope_id}")
        source_endpoints = scope["source_endpoints"]
        if not isinstance(source_endpoints, list) or not source_endpoints:
            raise FixtureManifestError(f"allowlist scope {scope_id} has no source endpoints")
        source_endpoint_pairs: set[tuple[str, str]] = set()
        for endpoint in source_endpoints:
            if not isinstance(endpoint, dict) or set(endpoint) != {
                "source_endpoint_model_id",
                "connectome_id",
            }:
                raise FixtureManifestError(f"invalid source endpoint row in scope {scope_id}")
            pair = (
                str(endpoint["source_endpoint_model_id"]).strip(),
                str(endpoint["connectome_id"]).strip(),
            )
            if not all(pair) or pair in source_endpoint_pairs:
                raise FixtureManifestError(f"duplicate or empty source endpoint in scope {scope_id}")
            source_endpoint_pairs.add(pair)
        scope["_source_endpoint_pairs"] = source_endpoint_pairs
        target_roles = scope["target_connectome_roles"]
        if (
            not isinstance(target_roles, list)
            or len(target_roles) != len(set(target_roles))
            or any(role not in valid_target_roles for role in target_roles)
        ):
            raise FixtureManifestError(f"invalid target connectome roles in scope {scope_id}")
        tasks = scope.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise FixtureManifestError(f"allowlist scope {scope_id} has no tasks")
        for task in tasks:
            if not isinstance(task, dict):
                raise FixtureManifestError(f"allowlist scope {scope_id} task must be a mapping")
            task_id = str(task.get("task_id", "")).strip()
            if not task_id:
                raise FixtureManifestError(f"allowlist scope {scope_id} task has no task_id")
            if task_id in allowed_by_id:
                raise FixtureManifestError(f"duplicate task_id in approved task allowlist: {task_id}")
            allowed_by_id[task_id] = {**task, "_scope": scope}
    return allowed_by_id


def build_fixture_manifest(
    run_root: Path,
    allowlist_path: Path,
    output_root: Path,
) -> Path:
    """Validate and record only explicitly allowlisted immutable run artifacts."""
    run_root = Path(run_root).expanduser().resolve()
    allowlist_path = Path(allowlist_path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    run_manifest = _load_json(run_root / "run_manifest.json", "run manifest")
    execution_plan = _load_json(run_root / "execution_plan.json", "execution plan")
    allowlist = _load_json(allowlist_path, "approved task allowlist")
    if allowlist.get("schema_version") != "dual_frequency_approved_task_allowlist_v1":
        raise FixtureManifestError("unsupported approved task allowlist schema")
    _validate_allowlist_identity(allowlist, run_manifest)

    plan_rows = execution_plan.get("tasks")
    if not isinstance(plan_rows, list):
        raise FixtureManifestError("execution plan tasks must be a list")
    plan_by_id = _unique_by(plan_rows, "task_id", "execution plan")
    status_rows = _load_csv(run_root / "task_status.csv", "task status")
    status_by_id = _unique_by(status_rows, "task_id", "task status")
    artifact_rows = _load_csv(run_root / "artifact_index.csv", "artifact index")
    artifacts_by_task: dict[str, list[dict[str, str]]] = {}
    seen_artifacts: set[tuple[str, str, str]] = set()
    for row in artifact_rows:
        identity = (
            str(row.get("task_id", "")),
            str(row.get("kind", "")),
            str(row.get("relative_path", "")),
        )
        if identity in seen_artifacts:
            raise FixtureManifestError(f"duplicate artifact-index row: {identity}")
        seen_artifacts.add(identity)
        artifacts_by_task.setdefault(identity[0], []).append(row)

    allowed_by_id = _flatten_scopes(allowlist)
    unknown = sorted(set(allowed_by_id) - set(plan_by_id))
    if unknown:
        raise FixtureManifestError("unknown allowlisted task IDs: " + ", ".join(unknown))

    eligible: list[dict[str, Any]] = []
    for task_id in sorted(allowed_by_id):
        allowed = allowed_by_id[task_id]
        scope = allowed["_scope"]
        spec = plan_by_id[task_id]
        status = status_by_id.get(task_id)
        if status is None:
            raise FixtureManifestError(f"allowlisted task is not terminal: {task_id}")
        if status.get("status") != "completed":
            raise FixtureManifestError(
                f"allowlisted task is not completed: {task_id} ({status.get('status', '')})"
            )
        identity = _task_identity(spec)
        task_identity = {
            "execution_stage": identity["execution_stage"],
            "branch": identity["branch"],
        }
        for key, value in task_identity.items():
            if str(allowed.get(key, "")) != value:
                raise FixtureManifestError(
                    f"allowlisted {key} mismatch for {task_id}: {allowed.get(key)!r} != {value!r}"
                )
        endpoint_pair = (str(spec.get("endpoint_model_id", "")), identity["connectome"])
        if endpoint_pair not in scope["_source_endpoint_pairs"]:
            raise FixtureManifestError(
                f"allowlisted scope endpoint mismatch for {task_id}: {endpoint_pair}"
            )
        scope_identity = {
            "parent_scale_id": identity["scale_id"],
            "model_family": identity["model_family"],
        }
        for key, value in scope_identity.items():
            if str(scope.get(key, "")) != value:
                raise FixtureManifestError(
                    f"allowlisted scope {key} mismatch for {task_id}: "
                    f"{scope.get(key)!r} != {value!r}"
                )
        if allowed.get("expected_status") != "completed":
            raise FixtureManifestError(f"allowlisted expected status must be completed: {task_id}")
        plan_kinds = allowed.get("plan_expected_artifact_kinds")
        if plan_kinds != spec.get("expected_artifact_kinds"):
            raise FixtureManifestError(f"plan expected artifact kinds mismatch for {task_id}")
        indexed = artifacts_by_task.get(task_id, [])
        manifests = [row for row in indexed if row.get("kind") == "task_manifest"]
        if len(manifests) != 1:
            raise FixtureManifestError(
                f"allowlisted task must have one indexed task manifest: {task_id}"
            )
        manifest_artifact = _validate_artifact(run_root, manifests[0], task_id=task_id)
        task_manifest = _load_json(Path(manifest_artifact["path"]), "task manifest")
        if task_manifest.get("task_id") != task_id or task_manifest.get("status") != "completed":
            raise FixtureManifestError(f"task manifest identity/status mismatch for {task_id}")
        kinds = allowed.get("reviewed_artifact_kinds")
        if not isinstance(kinds, list) or not kinds or any(not str(kind).strip() for kind in kinds):
            raise FixtureManifestError(f"allowlisted artifact kinds are invalid for {task_id}")
        if len(set(str(kind) for kind in kinds)) != len(kinds):
            raise FixtureManifestError(f"duplicate allowlisted artifact kind for {task_id}")
        scientific_artifacts: list[dict[str, Any]] = []
        for kind in sorted(str(kind) for kind in kinds):
            matching = [row for row in indexed if row.get("kind") == kind]
            if not matching:
                raise FixtureManifestError(f"allowlisted artifact kind is missing: {task_id}:{kind}")
            scientific_artifacts.extend(
                _validate_artifact(run_root, row, task_id=task_id)
                for row in sorted(matching, key=lambda item: item.get("relative_path", ""))
            )
        conversions = allowed.get("artifact_kind_conversions", {})
        if not isinstance(conversions, dict) or any(
            key not in kinds or not isinstance(value, str) or not value
            for key, value in conversions.items()
        ):
            raise FixtureManifestError(f"invalid artifact kind conversions for {task_id}")
        eligible.append(
            {
                "task_id": task_id,
                "scope_id": str(scope["scope_id"]),
                "endpoint_model_id": str(spec.get("endpoint_model_id", "")),
                "parent_scale_id": identity["scale_id"],
                "model_family": identity["model_family"],
                "source_binding_role": str(scope["source_binding_role"]),
                "connectome_id": identity["connectome"],
                "source_connectome_role": str(scope["source_connectome_role"]),
                "target_connectome_roles": list(scope["target_connectome_roles"]),
                "execution_stage": identity["execution_stage"],
                "branch": identity["branch"],
                "status": "completed",
                "artifact_kind_conversions": dict(sorted(conversions.items())),
                "task_manifest": manifest_artifact,
                "artifacts": scientific_artifacts,
            }
        )

    excluded: dict[str, str] = {}
    for task_id in sorted(plan_by_id):
        if task_id in allowed_by_id:
            continue
        status = status_by_id.get(task_id)
        excluded[task_id] = (
            "not_terminal_unstarted"
            if status is None
            else f"not_in_approved_allowlist:{status.get('status', '')}"
        )
    payload = {
        "schema_version": "dual_frequency_bounded_fixture_v1",
        "source_run_id": str(run_manifest.get("run_id", "")),
        "source_run_commit": str(
            (run_manifest.get("code_provenance") or {}).get("commit", "")
        ),
        "source_run_status": str(run_manifest.get("status", "")),
        "source_run_dirty": bool(
            (run_manifest.get("code_provenance") or {}).get("dirty")
        ),
        "source_provenance_hash": str(run_manifest.get("provenance_hash", "")),
        "source_evidence_policy": "paused_partial_allowlist_only",
        "configuration_hash": str(run_manifest.get("configuration_hash", "")),
        "allowlist_path": str(allowlist_path),
        "allowlist_sha256": _sha256(allowlist_path),
        "eligible_tasks": eligible,
        "excluded_tasks": excluded,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / "bounded_fixture_manifest.json"
    temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination
