"""Atomic immutable run artifacts and auditable provenance."""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml
from send2trash import send2trash

from .errors import ArtifactError
from .identity import canonical_hash, sha256_file
from .models import (
    ConnectomeMetadata,
    BatchConnectivityConfig,
    ConnectivityConfig,
    MembershipResult,
    ResolvedAtlas,
    ResolvedMask,
    RunArtifacts,
    StagedRunArtifacts,
    TargetStatistic,
)
from .traversal import TRAVERSAL_ALGORITHM, TRAVERSAL_VERSION


LEGACY_REQUIRED_ARTIFACTS = (
    "config_resolved.yaml",
    "target_catalog.csv",
    "target_connectivity.csv",
    "target_ranking.csv",
    "seed_connected_fiber_ids.npy",
    "target_fiber_membership.npz",
    "input_resolution_qc.csv",
    "analysis_manifest.json",
    "artifact_index.csv",
)

CURRENT_REQUIRED_ARTIFACTS = (
    "config_resolved.yaml",
    "target_catalog.csv",
    "target_connectivity.csv",
    "target_ranking.csv",
    "seed_connected_fiber_ids.npy",
    "target_fiber_membership.npz",
    "input_resolution_qc.csv",
    "provenance.json",
    "artifact_index.csv",
)

REQUIRED_ARTIFACTS = LEGACY_REQUIRED_ARTIFACTS

_CONNECTIVITY_FIELDS = (
    "target_id",
    "target_group",
    "relative_path",
    "source_value_type",
    "probability_threshold",
    "threshold_source",
    "target_status",
    "n_all_fibers",
    "n_seed_fibers",
    "n_target_fibers",
    "n_seed_target_fibers",
    "raw_fiber_count",
    "seed_normalized_fraction",
    "target_background_prevalence",
    "connectivity_lift",
    "connectivity_pmi",
    "connectivity_pmi_status",
    "rank",
)

_CATALOG_FIELDS = (
    "target_id",
    "target_group",
    "relative_path",
    "source_path",
    "source_hash",
    "source_value_type",
    "probability_threshold",
    "threshold_source",
    "status",
    "resolved_voxel_count",
    "resolved_physical_volume_mm3",
    "resolved_mask_hash",
    "shape",
    "affine",
)

_QC_FIELDS = ("role", "roi_id") + _CATALOG_FIELDS[1:]
_INDEX_FIELDS = (
    "artifact_name",
    "relative_path",
    "sha256",
    "size_bytes",
    "configuration_hash",
    "batch_configuration_hash",
    "effective_configuration_hash",
    "run_fingerprint",
    "source_file_hashes_json",
    "connectome_identity",
    "ordered_fiber_id_hash",
    "algorithm_version",
    "fiber_chunk_size",
    "resolved_mask_hashes_json",
    "code_provenance_json",
    "created_at",
)


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ArtifactError("artifact creation timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def collect_code_provenance(repo_root: Path | str | None = None) -> dict[str, str]:
    """Collect Git and package-tree identities without mutating the repository."""
    package_root = Path(__file__).resolve().parent
    root = Path(repo_root).resolve() if repo_root is not None else package_root.parents[3]
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        git_commit = "unavailable"
    file_rows: list[dict[str, str]] = []
    for path in sorted(
        candidate
        for candidate in package_root.rglob("*")
        if candidate.is_file() and candidate.suffix in {".py", ".json"} and "__pycache__" not in candidate.parts
    ):
        file_rows.append(
            {
                "relative_path": path.relative_to(package_root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return {"git_commit": git_commit, "package_sha256": canonical_hash(file_rows)}


def build_run_fingerprint(
    *,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    connectome_metadata: ConnectomeMetadata,
    code_provenance: Mapping[str, Any],
) -> str:
    """Return a stable immutable-run identity."""
    return canonical_hash(
        {
            "configuration_hash": config.configuration_hash,
            "seed_source_hash": seed.source_hash,
            "seed_resolved_mask_hash": seed.resolved_mask_hash,
            "target_atlas_resolved_mask_hash": atlas.atlas_hash,
            "connectome_identity": connectome_metadata.connectome_identity,
            "intersection_algorithm": TRAVERSAL_ALGORITHM,
            "intersection_algorithm_version": TRAVERSAL_VERSION,
            "code_provenance": dict(code_provenance),
        }
    )


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_text(path: Path, payload: str) -> None:
    _write_bytes(path, payload.encode("utf-8"))


def _artifact_names(directory: Path) -> set[str]:
    """Return pipeline artifact names while excluding AppleDouble metadata."""

    return {
        path.name
        for path in directory.iterdir()
        if not path.name.startswith("._")
    }


def _csv_payload(rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({field: "" if row.get(field) is None else row.get(field, "") for field in fieldnames})
    return output.getvalue()


def _mask_row(mask: ResolvedMask) -> dict[str, Any]:
    return {
        "target_id": mask.roi_id,
        "target_group": mask.target_group,
        "relative_path": mask.relative_path,
        "source_path": str(mask.source_path),
        "source_hash": mask.source_hash,
        "source_value_type": mask.source_value_type,
        "probability_threshold": mask.probability_threshold,
        "threshold_source": mask.threshold_source,
        "status": mask.status,
        "resolved_voxel_count": mask.voxel_count,
        "resolved_physical_volume_mm3": mask.physical_volume_mm3,
        "resolved_mask_hash": mask.resolved_mask_hash,
        "shape": json.dumps(mask.shape, separators=(",", ":")),
        "affine": json.dumps(np.asarray(mask.affine).tolist(), separators=(",", ":"), allow_nan=False),
    }


def _write_primary_artifacts(
    staging: Path,
    *,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    membership: MembershipResult,
    statistics: Sequence[TargetStatistic],
    resolved_mapping: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    config_payload = yaml.safe_dump(
        _thaw(config.resolved_mapping if resolved_mapping is None else resolved_mapping),
        sort_keys=False,
        allow_unicode=False,
    )
    _write_text(staging / "config_resolved.yaml", config_payload)

    catalog_rows = [_mask_row(target) for target in atlas.targets]
    _write_text(staging / "target_catalog.csv", _csv_payload(catalog_rows, _CATALOG_FIELDS))

    connectivity_rows = [row.as_serializable_mapping() for row in statistics]
    _write_text(
        staging / "target_connectivity.csv",
        _csv_payload(connectivity_rows, _CONNECTIVITY_FIELDS),
    )
    ranking_rows = sorted(
        (row for row in connectivity_rows if row["rank"] is not None),
        key=lambda row: int(row["rank"]),
    )
    _write_text(staging / "target_ranking.csv", _csv_payload(ranking_rows, _CONNECTIVITY_FIELDS))

    seed_output = io.BytesIO()
    np.save(seed_output, membership.seed_fiber_ids, allow_pickle=False)
    _write_bytes(staging / "seed_connected_fiber_ids.npy", seed_output.getvalue())

    target_output = io.BytesIO()
    maximum_length = max((len(value) for value in membership.target_membership.target_ids), default=1)
    np.savez_compressed(
        target_output,
        target_ids=np.asarray(membership.target_membership.target_ids, dtype=f"<U{maximum_length}"),
        indptr=membership.target_membership.indptr,
        fiber_ids=membership.target_membership.fiber_ids,
    )
    _write_bytes(staging / "target_fiber_membership.npz", target_output.getvalue())

    seed_qc = _mask_row(seed)
    seed_qc["role"] = "seed"
    seed_qc["roi_id"] = seed.roi_id
    target_qc: list[dict[str, Any]] = []
    for target in atlas.targets:
        row = _mask_row(target)
        row["role"] = "target"
        row["roi_id"] = target.roi_id
        target_qc.append(row)
    _write_text(staging / "input_resolution_qc.csv", _csv_payload([seed_qc, *target_qc], _QC_FIELDS))

    names = REQUIRED_ARTIFACTS[:7]
    return {name: sha256_file(staging / name) for name in names}


def _manifest(
    *,
    fingerprint: str,
    created_at: str,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    connectome_metadata: ConnectomeMetadata,
    membership: MembershipResult,
    code_provenance: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_fingerprint": fingerprint,
        "created_at": created_at,
        "configuration_hash": config.configuration_hash,
        "seed": {
            "source_path": str(seed.source_path),
            "source_hash": seed.source_hash,
            "resolved_mask_hash": seed.resolved_mask_hash,
        },
        "target_atlas": {
            "root": str(atlas.root),
            "resolved_mask_hash": atlas.atlas_hash,
            "target_count": len(atlas.targets),
            "target_source_hashes": {
                target.roi_id: target.source_hash for target in atlas.targets
            },
            "target_resolved_mask_hashes": {
                target.roi_id: target.resolved_mask_hash for target in atlas.targets
            },
        },
        "connectome": {
            "connectome_id": connectome_metadata.connectome_id,
            "source_path": str(connectome_metadata.source_path),
            "source_hash": connectome_metadata.source_hash,
            "geometry_hash": connectome_metadata.geometry_hash,
            "ordered_fiber_id_hash": connectome_metadata.ordered_fiber_id_hash,
            "connectome_identity": connectome_metadata.connectome_identity,
            "identity_source": connectome_metadata.identity_source,
            "n_fibers": connectome_metadata.n_fibers,
            "n_points": connectome_metadata.n_points,
        },
        "algorithm": {
            "intersection_method": TRAVERSAL_ALGORITHM,
            "intersection_version": TRAVERSAL_VERSION,
            "fiber_chunk_size": config.execution.fiber_chunk_size,
        },
        "membership_cache": {
            "seed_cache_key": membership.seed_cache_key,
            "target_cache_key": membership.target_cache_key,
            "seed_cache_hit": membership.seed_cache_hit,
            "target_cache_hit": membership.target_cache_hit,
        },
        "code_provenance": dict(code_provenance),
        "artifact_hashes": dict(artifact_hashes),
    }


def _write_index(
    staging: Path,
    hashes: Mapping[str, str],
    provenance: Mapping[str, Any],
) -> None:
    rows = [
        {
            "artifact_name": name,
            "relative_path": name,
            "sha256": digest,
            "size_bytes": (staging / name).stat().st_size,
            **dict(provenance),
        }
        for name, digest in hashes.items()
    ]
    _write_text(staging / "artifact_index.csv", _csv_payload(rows, _INDEX_FIELDS))


def verify_artifact_index(run_dir: Path | str) -> dict[str, str]:
    """Verify every indexed artifact and return its recorded hashes."""
    root = Path(run_dir)
    index_path = root / "artifact_index.csv"
    if not index_path.is_file():
        raise ArtifactError(f"artifact index is missing from incomplete run {root}")
    try:
        with index_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except Exception as exc:
        raise ArtifactError(f"failed to read artifact index {index_path}: {exc}") from exc
    current = (root / "provenance.json").is_file()
    provenance_name = "provenance.json" if current else "analysis_manifest.json"
    required = CURRENT_REQUIRED_ARTIFACTS if current else LEGACY_REQUIRED_ARTIFACTS
    expected_names = set(required) - {"artifact_index.csv"}
    names = [str(row.get("artifact_name", "")) for row in rows]
    if len(names) != len(set(names)) or set(names) != expected_names:
        raise ArtifactError(f"artifact index contents do not match required run artifacts: {root}")
    hashes: dict[str, str] = {}
    for row in rows:
        name = str(row["artifact_name"])
        if row.get("relative_path") != name or Path(name).name != name:
            raise ArtifactError(f"artifact index contains unsafe relative path: {row.get('relative_path')!r}")
        path = root / name
        if not path.is_file():
            raise ArtifactError(f"indexed artifact is missing: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != row.get("sha256"):
            raise ArtifactError(f"artifact hash mismatch for {path}")
        if int(row.get("size_bytes", -1)) != path.stat().st_size:
            raise ArtifactError(f"artifact size mismatch for {path}")
        hashes[name] = actual_hash
    try:
        manifest = json.loads((root / provenance_name).read_text(encoding="utf-8"))
        expected_source_hashes = {
            "seed": manifest["seed"]["source_hash"],
            "targets": manifest["target_atlas"]["target_source_hashes"],
            "connectome": manifest["connectome"]["source_hash"],
        }
        expected_resolved_hashes = {
            "seed": manifest["seed"]["resolved_mask_hash"],
            "target_atlas": manifest["target_atlas"]["resolved_mask_hash"],
            "targets": manifest["target_atlas"]["target_resolved_mask_hashes"],
        }
        for row in rows:
            scalar_expected = {
                "configuration_hash": (
                    manifest["effective_configuration_hash"]
                    if current
                    else manifest["configuration_hash"]
                ),
                "connectome_identity": manifest["connectome"]["connectome_identity"],
                "ordered_fiber_id_hash": manifest["connectome"]["ordered_fiber_id_hash"],
                "algorithm_version": str(manifest["algorithm"]["intersection_version"]),
                "fiber_chunk_size": str(manifest["algorithm"]["fiber_chunk_size"]),
                "created_at": manifest["created_at"],
            }
            if current:
                scalar_expected.update(
                    {
                        "batch_configuration_hash": manifest["batch_configuration_hash"],
                        "effective_configuration_hash": manifest["effective_configuration_hash"],
                        "run_fingerprint": manifest["run_fingerprint"],
                    }
                )
            if any(row.get(field) != value for field, value in scalar_expected.items()):
                raise ArtifactError("artifact index provenance does not match analysis manifest")
            if json.loads(row["source_file_hashes_json"]) != expected_source_hashes:
                raise ArtifactError("artifact index source-file provenance does not match analysis manifest")
            if json.loads(row["resolved_mask_hashes_json"]) != expected_resolved_hashes:
                raise ArtifactError("artifact index resolved-mask provenance does not match analysis manifest")
            if json.loads(row["code_provenance_json"]) != manifest["code_provenance"]:
                raise ArtifactError("artifact index code provenance does not match analysis manifest")
        if manifest.get("artifact_hashes") != {
            name: digest for name, digest in hashes.items() if name != provenance_name
        }:
            raise ArtifactError("run provenance artifact hashes do not match artifact index")
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError(f"failed to validate artifact index provenance for {root}: {exc}") from exc
    return hashes


def artifact_hashes(run_dir: Path | str) -> dict[str, str]:
    """Return verified hashes for one immutable run."""
    return verify_artifact_index(run_dir)


def write_run_atomic(
    *,
    output_root: Path | str,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    connectome_metadata: ConnectomeMetadata,
    membership: MembershipResult,
    statistics: Sequence[TargetStatistic],
    code_provenance: Mapping[str, Any],
    now: datetime | None = None,
) -> RunArtifacts:
    """Write or verify one content-addressed immutable run directory."""
    if tuple(row.target_id for row in statistics) != tuple(target.roi_id for target in atlas.targets):
        raise ArtifactError("statistics order does not match resolved target atlas")
    fingerprint = build_run_fingerprint(
        config=config,
        seed=seed,
        atlas=atlas,
        connectome_metadata=connectome_metadata,
        code_provenance=code_provenance,
    )
    output = Path(output_root).expanduser().resolve()
    runs_root = output / "runs"
    final = runs_root / fingerprint
    if final.exists():
        if not final.is_dir() or _artifact_names(final) != set(REQUIRED_ARTIFACTS):
            raise ArtifactError(f"existing immutable run is incomplete: {final}")
        hashes = verify_artifact_index(final)
        try:
            manifest = json.loads((final / "analysis_manifest.json").read_text(encoding="utf-8"))
        except Exception as exc:
            raise ArtifactError(f"failed to read existing run manifest {final}: {exc}") from exc
        if manifest.get("run_fingerprint") != fingerprint:
            raise ArtifactError(f"existing immutable run fingerprint mismatch: {final}")
        return RunArtifacts(
            run_dir=final,
            run_fingerprint=fingerprint,
            artifact_hashes=hashes,
            reused=True,
        )

    runs_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", suffix=".staging", dir=runs_root))
    try:
        primary_hashes = _write_primary_artifacts(
            staging,
            config=config,
            seed=seed,
            atlas=atlas,
            membership=membership,
            statistics=statistics,
        )
        created_at = _utc_text(now or datetime.now(timezone.utc))
        manifest = _manifest(
            fingerprint=fingerprint,
            created_at=created_at,
            config=config,
            seed=seed,
            atlas=atlas,
            connectome_metadata=connectome_metadata,
            membership=membership,
            code_provenance=code_provenance,
            artifact_hashes=primary_hashes,
        )
        manifest_payload = json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ) + "\n"
        _write_text(staging / "analysis_manifest.json", manifest_payload)
        indexed_hashes = {
            **primary_hashes,
            "analysis_manifest.json": sha256_file(staging / "analysis_manifest.json"),
        }
        index_provenance = {
            "configuration_hash": config.configuration_hash,
            "source_file_hashes_json": json.dumps(
                {
                    "seed": seed.source_hash,
                    "targets": {target.roi_id: target.source_hash for target in atlas.targets},
                    "connectome": connectome_metadata.source_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            "connectome_identity": connectome_metadata.connectome_identity,
            "ordered_fiber_id_hash": connectome_metadata.ordered_fiber_id_hash,
            "algorithm_version": TRAVERSAL_VERSION,
            "fiber_chunk_size": config.execution.fiber_chunk_size,
            "resolved_mask_hashes_json": json.dumps(
                {
                    "seed": seed.resolved_mask_hash,
                    "target_atlas": atlas.atlas_hash,
                    "targets": {
                        target.roi_id: target.resolved_mask_hash for target in atlas.targets
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            "code_provenance_json": json.dumps(
                dict(code_provenance),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            "created_at": created_at,
        }
        _write_index(staging, indexed_hashes, index_provenance)
        if _artifact_names(staging) != set(REQUIRED_ARTIFACTS):
            raise ArtifactError("staged run does not contain the exact required artifact set")
        os.replace(staging, final)
        hashes = verify_artifact_index(final)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return RunArtifacts(
        run_dir=final,
        run_fingerprint=fingerprint,
        artifact_hashes=hashes,
        reused=False,
    )


def _current_provenance(
    *,
    fingerprint: str,
    created_at: str,
    batch: BatchConnectivityConfig,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    connectome_metadata: ConnectomeMetadata,
    membership: MembershipResult,
    code_provenance: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    provenance = _manifest(
        fingerprint=fingerprint,
        created_at=created_at,
        config=config,
        seed=seed,
        atlas=atlas,
        connectome_metadata=connectome_metadata,
        membership=membership,
        code_provenance=code_provenance,
        artifact_hashes=artifact_hashes,
    )
    provenance["schema_version"] = 2
    provenance["seed_name"] = config.seed_name
    provenance["batch_configuration_hash"] = batch.batch_configuration_hash
    provenance["effective_configuration_hash"] = config.configuration_hash
    provenance.pop("configuration_hash", None)
    return provenance


def stage_run_artifacts(
    *,
    batch: BatchConnectivityConfig,
    config: ConnectivityConfig,
    seed: ResolvedMask,
    atlas: ResolvedAtlas,
    connectome_metadata: ConnectomeMetadata,
    membership: MembershipResult,
    statistics: Sequence[TargetStatistic],
    code_provenance: Mapping[str, Any],
    now: datetime | None = None,
) -> StagedRunArtifacts:
    """Write and verify one side without publishing its semantic directory."""

    if tuple(row.target_id for row in statistics) != tuple(target.roi_id for target in atlas.targets):
        raise ArtifactError("statistics order does not match resolved target atlas")
    fingerprint = build_run_fingerprint(
        config=config,
        seed=seed,
        atlas=atlas,
        connectome_metadata=connectome_metadata,
        code_provenance=code_provenance,
    )
    final = batch.output.output_root / config.seed_name / batch.output.run_name
    if final.exists():
        if not final.is_dir() or not (final / "provenance.json").is_file():
            raise ArtifactError(f"existing semantic result is not tool-owned: {final}")
        hashes = verify_artifact_index(final)
        provenance = json.loads((final / "provenance.json").read_text(encoding="utf-8"))
        if (
            provenance.get("run_fingerprint") == fingerprint
            and provenance.get("batch_configuration_hash") == batch.batch_configuration_hash
        ):
            return StagedRunArtifacts(
                seed_name=config.seed_name,
                staging_dir=None,
                final_dir=final,
                run_fingerprint=fingerprint,
                artifact_hashes=hashes,
                reused=True,
            )

    final.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{batch.output.run_name}.",
            suffix=".staging",
            dir=final.parent,
        )
    )
    try:
        primary_hashes = _write_primary_artifacts(
            staging,
            config=config,
            seed=seed,
            atlas=atlas,
            membership=membership,
            statistics=statistics,
            resolved_mapping=batch.resolved_mapping,
        )
        created_at = _utc_text(now or datetime.now(timezone.utc))
        provenance = _current_provenance(
            fingerprint=fingerprint,
            created_at=created_at,
            batch=batch,
            config=config,
            seed=seed,
            atlas=atlas,
            connectome_metadata=connectome_metadata,
            membership=membership,
            code_provenance=code_provenance,
            artifact_hashes=primary_hashes,
        )
        _write_text(
            staging / "provenance.json",
            json.dumps(provenance, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        )
        indexed_hashes = {
            **primary_hashes,
            "provenance.json": sha256_file(staging / "provenance.json"),
        }
        _write_index(
            staging,
            indexed_hashes,
            {
                "configuration_hash": config.configuration_hash,
                "batch_configuration_hash": batch.batch_configuration_hash,
                "effective_configuration_hash": config.configuration_hash,
                "run_fingerprint": fingerprint,
                "source_file_hashes_json": json.dumps(
                    {
                        "seed": seed.source_hash,
                        "targets": {target.roi_id: target.source_hash for target in atlas.targets},
                        "connectome": connectome_metadata.source_hash,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "connectome_identity": connectome_metadata.connectome_identity,
                "ordered_fiber_id_hash": connectome_metadata.ordered_fiber_id_hash,
                "algorithm_version": TRAVERSAL_VERSION,
                "fiber_chunk_size": config.execution.fiber_chunk_size,
                "resolved_mask_hashes_json": json.dumps(
                    {
                        "seed": seed.resolved_mask_hash,
                        "target_atlas": atlas.atlas_hash,
                        "targets": {
                            target.roi_id: target.resolved_mask_hash for target in atlas.targets
                        },
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "code_provenance_json": json.dumps(
                    dict(code_provenance),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "created_at": created_at,
            },
        )
        if _artifact_names(staging) != set(CURRENT_REQUIRED_ARTIFACTS):
            raise ArtifactError("staged result does not contain the exact required artifact set")
        hashes = verify_artifact_index(staging)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return StagedRunArtifacts(
        seed_name=config.seed_name,
        staging_dir=staging,
        final_dir=final,
        run_fingerprint=fingerprint,
        artifact_hashes=hashes,
        reused=False,
    )


def publish_staged_batch(
    staged_runs: Mapping[str, StagedRunArtifacts],
    *,
    trash=lambda path: send2trash(str(path)),
    replace=os.replace,
) -> Mapping[str, RunArtifacts]:
    """Publish all changed sides with rollback before sending prior results to Trash."""

    ordered = [(name, staged_runs[name]) for name in sorted(staged_runs)]
    for name, staged in ordered:
        if name != staged.seed_name:
            raise ArtifactError("staged seed key does not match artifact seed name")
        if staged.staging_dir is not None:
            verify_artifact_index(staged.staging_dir)
    rollbacks: dict[str, Path] = {}
    published: list[tuple[str, StagedRunArtifacts]] = []
    try:
        for name, staged in ordered:
            if staged.reused:
                continue
            if staged.staging_dir is None:
                raise ArtifactError(f"changed seed {name} has no staging directory")
            if staged.final_dir.exists():
                if not (staged.final_dir / "provenance.json").is_file():
                    raise ArtifactError(f"existing semantic result is not tool-owned: {staged.final_dir}")
                rollback = staged.final_dir.parent / f".{staged.final_dir.name}.{uuid.uuid4().hex}.rollback"
                replace(staged.final_dir, rollback)
                rollbacks[name] = rollback
        for name, staged in ordered:
            if staged.reused:
                continue
            replace(staged.staging_dir, staged.final_dir)
            published.append((name, staged))
        for _, staged in published:
            verify_artifact_index(staged.final_dir)
    except Exception as exc:
        for _, staged in reversed(published):
            if staged.final_dir.exists() and staged.staging_dir is not None:
                replace(staged.final_dir, staged.staging_dir)
        for name, rollback in reversed(tuple(rollbacks.items())):
            final = staged_runs[name].final_dir
            if rollback.exists():
                replace(rollback, final)
        raise ArtifactError(str(exc)) from exc

    for rollback in rollbacks.values():
        trash(rollback)

    results: dict[str, RunArtifacts] = {}
    for name, staged in ordered:
        hashes = verify_artifact_index(staged.final_dir)
        results[name] = RunArtifacts(
            run_dir=staged.final_dir,
            run_fingerprint=staged.run_fingerprint,
            artifact_hashes=hashes,
            reused=staged.reused,
        )
    return results
