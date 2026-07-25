#!/usr/bin/env python3
"""Prepare and validate the immutable Task 17 performance benchmark plan."""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np
import yaml


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.application.sensitivity import (  # noqa: E402
    SensitivityCheckpointError,
    compile_sensitivity_extension_plan,
    load_sensitivity_checkpoint,
    parent_manifest_sha256,
)
from dual_frequency.application.service import (  # noqa: E402
    ApplicationError,
    WorkflowRequest,
    WorkflowService,
)
from dual_frequency.backends.activation.ossdbs import (  # noqa: E402
    OSSRowMaterializer,
    OSSRowProduct,
)
from dual_frequency.backends.activation.ppam import (  # noqa: E402
    PPAM_LATTICE_ABSOLUTE_TOLERANCE,
)
from dual_frequency.cache import ContentAddressedCache  # noqa: E402
from dual_frequency.config import WorkflowOverrides  # noqa: E402
from dual_frequency.contracts import (  # noqa: E402
    OSSAxisEquivalenceGroupRecord,
    TaskKey,
)
from dual_frequency.runtime.oss_axis_equivalence import (  # noqa: E402
    OSS_AXIS_PROBABILITY_TOLERANCE,
    accepted_group_uses_stable_scientific_cache,
)
from dual_frequency.runtime.oss_toolchain import (  # noqa: E402
    OSSRowExecutionEvidence,
)
from dual_frequency.workflow import (  # noqa: E402
    ExecutionPlan,
    GateRequirement,
    ServiceResult,
    TaskSpec,
    plan_hash,
)


_REQUEST_SCHEMA = "dual_frequency_task17_performance_benchmark_plan_v1"
_RESOLVED_SCHEMA = "dual_frequency_task17_performance_benchmark_resolved_v1"
_MARKER_SCHEMA = "dual_frequency_task17_performance_benchmark_root_v1"
_RUNNER_READY_SCHEMA = "dual_frequency_task17_performance_runner_ready_v1"
_MEASUREMENT_START_SCHEMA = (
    "dual_frequency_task17_performance_measurement_start_v1"
)
_ROW_CONTRACT_SCHEMA = "dual_frequency_task17_performance_row_contract_v1"
_ROW_RESULT_SCHEMA = "dual_frequency_task17_performance_row_result_v1"
_NOT_RUN_PREFLIGHT_SCHEMA = (
    "dual_frequency_task17_performance_not_run_preflight_v1"
)
_WORKERS = (1, 3, 6, 12)
_REQUEST_FIELDS = {
    "schema_version",
    "plan_id",
    "accepted_parent_root",
    "accepted_independent_oss_root",
    "study_base",
    "direct_voxel_model",
    "normative_fiber_model",
    "workflow_profile",
    "conda_environment",
    "working_directory",
    "maximum_task_tree_rss_bytes",
    "real_cold_solver_authorization",
}
_MAIN_SLICE_SERVICES = {
    "direct_voxel": {
        "prepare_reference_voxel_exposure",
        "prepare_addon_voxel_exposure",
    },
    "fiber_connectome": {
        "prepare_reference_fiber_sidecar",
        "prepare_addon_fiber_sidecars",
    },
    "formal_permutation": {
        "prepare_formal_operator_workspace",
        "prepare_formal_permutation_schedule",
        "run_formal_permutation_block",
        "aggregate_formal_permutation",
    },
    "bootstrap": {
        "prepare_formal_operator_workspace",
        "prepare_formal_bootstrap_schedule",
        "run_formal_bootstrap_block",
        "aggregate_formal_bootstrap",
    },
}
_BASE_PREPARE_SERVICES = {
    "prepare_reference_voxel_exposure",
    "prepare_addon_voxel_exposure",
    "prepare_reference_fiber_sidecar",
    "prepare_addon_fiber_sidecars",
}
_JITTER_SERVICES = {
    "prepare_jitter_exposure_block",
    "run_reference_voxel_jitter",
    "run_addon_voxel_jitter",
    "run_reference_fiber_jitter",
    "run_addon_fiber_jitter",
}
_PPAM_SERVICES = {
    "establish_oss_axis_equivalence",
    "prepare_ppam_observed_workspace",
    "prepare_ppam_permutation_schedule",
    "run_ppam_permutation_block",
    "aggregate_ppam_activation",
}


class PerformanceMatrixHarnessError(RuntimeError):
    """Raised when benchmark preparation is incomplete or unsafe."""


class _PollableProcess(Protocol):
    def poll(self) -> int | None:
        """Return the child exit code or None while it remains alive."""


class _AcceptedOSSInjectedToolchain:
    """Return deterministic sample evidence from one accepted OSS row closure."""

    def __init__(
        self,
        *,
        cache_root: Path,
        accepted_row_identities: Sequence[str],
    ) -> None:
        identities = tuple(sorted(str(value) for value in accepted_row_identities))
        if not identities or len(set(identities)) != len(identities):
            raise PerformanceMatrixHarnessError(
                "injected OSS rows must be nonempty and unique"
            )
        self._cache = ContentAddressedCache(cache_root)
        self._accepted_row_identities = frozenset(identities)

    def produce_with_evidence(self, request: object) -> OSSRowExecutionEvidence:
        """Reconstruct one deterministic ten-sample row from accepted probabilities."""

        identity = getattr(request, "scientific_identity", None)
        row = getattr(request, "row", None)
        if (
            type(identity) is not str
            or identity not in self._accepted_row_identities
            or row is None
        ):
            raise PerformanceMatrixHarnessError(
                "injected OSS request is outside the accepted row closure"
            )
        entry = self._cache.resolve_identity("oss_rows", identity)
        if entry is None:
            raise PerformanceMatrixHarnessError(
                "accepted injected OSS row is unavailable"
            )
        try:
            product = OSSRowMaterializer._validated_row_product(entry, row)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "accepted injected OSS row differs from the runtime request"
            ) from exc
        counts_float = product.probabilities.astype(np.float64) * 10.0
        counts = np.rint(counts_float).astype(np.int64)
        if (
            np.any(counts < 0)
            or np.any(counts > 10)
            or not np.allclose(
                counts_float,
                counts,
                rtol=0.0,
                atol=PPAM_LATTICE_ABSOLUTE_TOLERANCE,
            )
        ):
            raise PerformanceMatrixHarnessError(
                "accepted OSS probabilities cannot reconstruct ten samples"
            )
        sample_numbers = np.arange(10, dtype=np.int64)[:, None]
        states = np.where(sample_numbers < counts[None, :], 1, 0).astype(
            np.int8
        )
        injected_product = OSSRowProduct(
            product.feature_ids,
            product.probabilities,
            producer_implementation_attestation=(
                "task17-performance-injected-oss-v1"
            ),
        )
        return OSSRowExecutionEvidence(injected_product, states)


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PerformanceMatrixHarnessError(
            f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(document, dict):
        raise PerformanceMatrixHarnessError(f"{label} must contain an object")
    return document


def _json_text(document: Mapping[str, object]) -> str:
    return json.dumps(
        dict(document),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _document_sha256(document: Mapping[str, object]) -> str:
    return hashlib.sha256(_json_text(document).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    text = _json_text(document)
    if path.exists():
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise PerformanceMatrixHarnessError(
                f"immutable benchmark document changed: {path}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _runner_ready(
    process: _PollableProcess,
    path: Path,
    *,
    row_id: str,
    timeout_seconds: float = 300.0,
    monotonic_reader: Any = time.monotonic,
    sleeper: Any = time.sleep,
) -> dict[str, object]:
    """Wait for one exact child readiness record before measurement starts."""

    if timeout_seconds <= 0:
        raise PerformanceMatrixHarnessError(
            "runner readiness timeout must be positive"
        )
    started = float(monotonic_reader())
    destination = path.expanduser().resolve()
    while True:
        if destination.is_file():
            document = _read_json(destination, "runner readiness")
            expected = {
                "schema_version",
                "row_id",
                "runner_pid",
                "run_root",
                "segment_plan_sha256",
                "imported_parent_task_ids",
                "imported_oss_task_ids",
            }
            if set(document) != expected:
                raise PerformanceMatrixHarnessError(
                    "runner readiness fields differ"
                )
            if (
                document["schema_version"] != _RUNNER_READY_SCHEMA
                or document["row_id"] != row_id
                or type(document["runner_pid"]) is not int
                or document["runner_pid"] < 2
                or not isinstance(document["imported_parent_task_ids"], list)
                or not isinstance(document["imported_oss_task_ids"], list)
            ):
                raise PerformanceMatrixHarnessError(
                    "runner readiness identity differs"
                )
            run_root = Path(str(document["run_root"])).expanduser().resolve()
            if not run_root.is_dir():
                raise PerformanceMatrixHarnessError(
                    "runner readiness run root is missing"
                )
            segment_plan = str(document["segment_plan_sha256"]).strip().lower()
            if len(segment_plan) != 64 or any(
                character not in "0123456789abcdef"
                for character in segment_plan
            ):
                raise PerformanceMatrixHarnessError(
                    "runner readiness plan SHA differs"
                )
            return document
        exit_code = process.poll()
        if exit_code is not None:
            raise PerformanceMatrixHarnessError(
                "runner exited before publishing readiness"
            )
        if float(monotonic_reader()) - started > timeout_seconds:
            raise PerformanceMatrixHarnessError(
                "runner readiness timed out"
            )
        sleeper(0.1)


def _measurement_start(
    path: Path,
    *,
    row_id: str,
    runner_pid: int,
    byte_ledger_index: Path,
) -> dict[str, object]:
    """Publish the immutable token that allows selected tasks to execute."""

    ledger = byte_ledger_index.expanduser().resolve()
    if not ledger.is_file():
        raise PerformanceMatrixHarnessError(
            "measurement byte-ledger index is missing"
        )
    document = {
        "schema_version": _MEASUREMENT_START_SCHEMA,
        "row_id": row_id,
        "runner_pid": runner_pid,
        "byte_ledger_index": str(ledger),
        "byte_ledger_index_sha256": _sha256_file(ledger),
    }
    _atomic_json(path.expanduser().resolve(), document)
    return document


def _wait_for_measurement_start(
    path: Path,
    *,
    row_id: str,
    runner_pid: int,
    timeout_seconds: float = 300.0,
    monotonic_reader: Any = time.monotonic,
    sleeper: Any = time.sleep,
) -> dict[str, object]:
    """Block one ready child until the parent has attached measurement."""

    if timeout_seconds <= 0:
        raise PerformanceMatrixHarnessError(
            "measurement-start timeout must be positive"
        )
    started = float(monotonic_reader())
    source = path.expanduser().resolve()
    while not source.is_file():
        if float(monotonic_reader()) - started > timeout_seconds:
            raise PerformanceMatrixHarnessError(
                "measurement-start token timed out"
            )
        sleeper(0.1)
    document = _read_json(source, "measurement-start token")
    expected = {
        "schema_version",
        "row_id",
        "runner_pid",
        "byte_ledger_index",
        "byte_ledger_index_sha256",
    }
    if (
        set(document) != expected
        or document["schema_version"] != _MEASUREMENT_START_SCHEMA
        or document["row_id"] != row_id
        or document["runner_pid"] != runner_pid
    ):
        raise PerformanceMatrixHarnessError(
            "measurement-start token identity differs"
        )
    ledger = Path(str(document["byte_ledger_index"])).expanduser().resolve()
    if (
        not ledger.is_file()
        or _sha256_file(ledger)
        != str(document["byte_ledger_index_sha256"]).strip().lower()
    ):
        raise PerformanceMatrixHarnessError(
            "measurement-start byte-ledger identity differs"
        )
    return document


def _path_token(value: object, label: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.exists():
        raise PerformanceMatrixHarnessError(f"{label} does not exist: {path}")
    return path


def _safe_token(value: object, label: str) -> str:
    token = str(value).strip()
    if (
        not token
        or token in {".", ".."}
        or "/" in token
        or "\\" in token
    ):
        raise PerformanceMatrixHarnessError(f"{label} must be path-safe")
    return token


def _load_request(path: Path) -> tuple[dict[str, Any], str]:
    request_path = path.expanduser().resolve()
    request = _read_json(request_path, "benchmark request")
    if set(request) != _REQUEST_FIELDS:
        raise PerformanceMatrixHarnessError(
            "benchmark request fields differ from the schema"
        )
    if request["schema_version"] != _REQUEST_SCHEMA:
        raise PerformanceMatrixHarnessError("benchmark request schema differs")
    _safe_token(request["plan_id"], "benchmark plan ID")
    for field in (
        "accepted_parent_root",
        "accepted_independent_oss_root",
        "study_base",
        "direct_voxel_model",
        "normative_fiber_model",
        "workflow_profile",
        "working_directory",
    ):
        _path_token(request[field], field)
    environment = str(request["conda_environment"]).strip()
    if not environment:
        raise PerformanceMatrixHarnessError(
            "benchmark Conda environment must be nonempty"
        )
    maximum_rss = request["maximum_task_tree_rss_bytes"]
    if type(maximum_rss) is not int or maximum_rss < 1:
        raise PerformanceMatrixHarnessError(
            "maximum task-tree RSS must be a positive integer"
        )
    authorization = request["real_cold_solver_authorization"]
    if authorization is not None:
        authorization_path = _path_token(
            authorization,
            "real cold solver authorization",
        )
        if not authorization_path.is_file():
            raise PerformanceMatrixHarnessError(
                "real cold solver authorization must be a file"
            )
    return request, _sha256_file(request_path)


def _terminal_run(root: Path, label: str) -> dict[str, Any]:
    if not root.is_dir():
        raise PerformanceMatrixHarnessError(f"{label} must be a directory")
    manifest = _read_json(root / "run_manifest.json", f"{label} manifest")
    if (
        manifest.get("schema_version") != "dual_frequency_run_v1"
        or manifest.get("final_status") != "completed"
        or not str(manifest.get("run_id", "")).strip()
    ):
        raise PerformanceMatrixHarnessError(f"{label} is not a completed run")
    return manifest


def _accepted_oss_gate_records(
    oss_root: Path,
) -> tuple[tuple[str, OSSAxisEquivalenceGroupRecord], ...]:
    """Decode the exact accepted OSS gate records from one terminal lineage."""

    tasks_root = oss_root / "tasks"
    records: list[tuple[str, OSSAxisEquivalenceGroupRecord]] = []
    for path in sorted(tasks_root.glob("task_*.json")):
        payload = _read_json(path, "accepted OSS task state")
        result_payload = payload.get("result")
        if (
            payload.get("status") != "completed"
            or payload.get("service_id") != "establish_oss_axis_equivalence"
            or not isinstance(result_payload, Mapping)
        ):
            continue
        try:
            record = ServiceResult.from_dict(result_payload).decode_record()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "accepted OSS gate result cannot be decoded"
            ) from exc
        if not isinstance(record, OSSAxisEquivalenceGroupRecord):
            raise PerformanceMatrixHarnessError(
                "accepted OSS gate task returned a different record type"
            )
        if record.gate_status != "accepted_omega_max":
            raise PerformanceMatrixHarnessError(
                "accepted OSS gate is not terminally accepted"
            )
        task_id = str(payload.get("task_id", path.stem))
        if task_id != path.stem:
            raise PerformanceMatrixHarnessError(
                "accepted OSS task path and task ID differ"
            )
        records.append((task_id, record))
    if (
        len(records) != 2
        or {record.model_family for _, record in records}
        != {"reference_fiber", "addon_fiber"}
        or len({record.group_id for _, record in records}) != len(records)
    ):
        raise PerformanceMatrixHarnessError(
            "accepted OSS lineage lacks the exact two fiber gate records"
        )
    return tuple(sorted(records, key=lambda item: item[1].group_id))


def _accepted_oss_cache_closure(
    records: Sequence[tuple[str, OSSAxisEquivalenceGroupRecord]],
    *,
    cache_root: Path,
) -> dict[str, object]:
    """Validate and bind all decision and row entries referenced by OSS gates."""

    cache = ContentAddressedCache(cache_root)
    groups: list[dict[str, object]] = []
    all_rows: dict[str, dict[str, object]] = {}
    expected_decision_fields = {
        "schema_version",
        "decision_id",
        "group_id",
        "status",
        "final_row_identity",
        "omega_row_identity",
        "state_mismatch_count",
        "activation_count_mismatch_count",
        "max_probability_difference",
        "probability_tolerance",
    }
    for task_id, record in records:
        try:
            stable = accepted_group_uses_stable_scientific_cache(record, cache)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "accepted OSS group cache closure is invalid"
            ) from exc
        if not stable:
            raise PerformanceMatrixHarnessError(
                "accepted OSS group still references historical cache keys"
            )
        decisions: list[dict[str, object]] = []
        for decision_id in record.row_decision_ids:
            decision_entry = cache.resolve_identity(
                "oss_axis_equivalence",
                decision_id,
            )
            if decision_entry is None:
                raise PerformanceMatrixHarnessError(
                    "accepted OSS decision cache is unavailable"
                )
            decision = _read_json(
                decision_entry.file_path("decision.json"),
                "accepted OSS decision",
            )
            if (
                set(decision) != expected_decision_fields
                or decision.get("decision_id") != decision_id
                or decision.get("group_id") != record.group_id
                or decision.get("status") != "pass"
                or type(decision.get("state_mismatch_count")) is not int
                or decision["state_mismatch_count"] > 0
                or type(decision.get("activation_count_mismatch_count"))
                is not int
                or decision["activation_count_mismatch_count"] > 0
                or not isinstance(
                    decision.get("max_probability_difference"),
                    (int, float),
                )
                or float(decision["max_probability_difference"])
                > OSS_AXIS_PROBABILITY_TOLERANCE
            ):
                raise PerformanceMatrixHarnessError(
                    "accepted OSS decision payload differs from a pass decision"
                )
            row_payloads: dict[str, dict[str, object]] = {}
            row_arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            for role in ("final", "omega"):
                identity = decision.get(f"{role}_row_identity")
                if type(identity) is not str:
                    raise PerformanceMatrixHarnessError(
                        "accepted OSS decision row identity is invalid"
                    )
                row_entry = cache.resolve_identity("oss_rows", identity)
                if row_entry is None:
                    raise PerformanceMatrixHarnessError(
                        "accepted OSS row cache is unavailable"
                    )
                try:
                    arrays = OSSRowMaterializer._load_entry(row_entry.path)
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    raise PerformanceMatrixHarnessError(
                        "accepted OSS row payload is invalid"
                    ) from exc
                row_payload = {
                    "scientific_identity": identity,
                    "manifest_sha256": _sha256_file(row_entry.manifest_path),
                    "feature_count": int(arrays[0].size),
                }
                previous = all_rows.get(identity)
                if previous is not None and previous != row_payload:
                    raise PerformanceMatrixHarnessError(
                        "accepted OSS row identity has conflicting evidence"
                    )
                all_rows[identity] = row_payload
                row_payloads[role] = row_payload
                row_arrays[role] = arrays
            final_ids, final_probabilities = row_arrays["final"]
            omega_ids, omega_probabilities = row_arrays["omega"]
            positions = np.searchsorted(omega_ids, final_ids)
            if (
                np.any(positions >= omega_ids.size)
                or not np.array_equal(omega_ids[positions], final_ids)
                or np.any(
                    np.abs(
                        final_probabilities.astype(np.float64)
                        - omega_probabilities[positions].astype(np.float64)
                    )
                    > OSS_AXIS_PROBABILITY_TOLERANCE
                )
            ):
                raise PerformanceMatrixHarnessError(
                    "accepted OSS final and Omega rows differ on the final axis"
                )
            decisions.append(
                {
                    "decision_id": decision_id,
                    "manifest_sha256": _sha256_file(
                        decision_entry.manifest_path
                    ),
                    "final_row": row_payloads["final"],
                    "omega_row": row_payloads["omega"],
                }
            )
        groups.append(
            {
                "task_id": task_id,
                "group_id": record.group_id,
                "model_family": record.model_family,
                "decision_ids": list(record.row_decision_ids),
                "decisions": decisions,
            }
        )
    closure = {
        "cache_root": str(cache.root),
        "groups": groups,
        "rows": [all_rows[key] for key in sorted(all_rows)],
    }
    return {
        **closure,
        "closure_sha256": _canonical_sha256(closure),
    }


def _accepted_oss_cache_entry_descriptors(
    closure: Mapping[str, object],
) -> tuple[dict[str, str], ...]:
    """Return the exact deduplicated decision and row entries in one closure."""

    groups = closure.get("groups")
    rows = closure.get("rows")
    if not isinstance(groups, list) or not isinstance(rows, list):
        raise PerformanceMatrixHarnessError(
            "accepted OSS cache closure is incomplete"
        )
    output: dict[tuple[str, str], dict[str, str]] = {}
    for item in rows:
        if not isinstance(item, Mapping):
            raise PerformanceMatrixHarnessError(
                "accepted OSS row descriptor is invalid"
            )
        descriptor = {
            "kind": "oss_rows",
            "scientific_identity": str(item.get("scientific_identity", "")),
            "manifest_sha256": str(item.get("manifest_sha256", "")),
        }
        output[
            (descriptor["kind"], descriptor["scientific_identity"])
        ] = descriptor
    for group in groups:
        decisions = group.get("decisions") if isinstance(group, Mapping) else None
        if not isinstance(decisions, list):
            raise PerformanceMatrixHarnessError(
                "accepted OSS decision descriptor is invalid"
            )
        for item in decisions:
            if not isinstance(item, Mapping):
                raise PerformanceMatrixHarnessError(
                    "accepted OSS decision descriptor is invalid"
                )
            descriptor = {
                "kind": "oss_axis_equivalence",
                "scientific_identity": str(item.get("decision_id", "")),
                "manifest_sha256": str(item.get("manifest_sha256", "")),
            }
            output[
                (descriptor["kind"], descriptor["scientific_identity"])
            ] = descriptor
    descriptors = tuple(output[key] for key in sorted(output))
    if not descriptors:
        raise PerformanceMatrixHarnessError(
            "accepted OSS cache closure contains no entries"
        )
    for descriptor in descriptors:
        for field in ("scientific_identity", "manifest_sha256"):
            value = descriptor[field]
            if (
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise PerformanceMatrixHarnessError(
                    "accepted OSS cache descriptor identity is invalid"
                )
    return descriptors


def _copy_verified_cache_entries(
    *,
    source_cache_root: Path,
    destination_cache_root: Path,
    entries: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    """Copy exact accepted entries into one empty cache and revalidate them."""

    source_root = source_cache_root.expanduser().resolve()
    destination_root = destination_cache_root.expanduser().resolve()
    if (
        source_root == destination_root
        or source_root in destination_root.parents
        or destination_root in source_root.parents
    ):
        raise PerformanceMatrixHarnessError(
            "cache seed source and destination overlap"
        )
    if destination_root.exists() and any(destination_root.iterdir()):
        raise PerformanceMatrixHarnessError(
            "cache seed destination must be empty"
        )
    destination_root.mkdir(parents=True, exist_ok=True)
    source = ContentAddressedCache(source_root)
    destination = ContentAddressedCache(destination_root)
    copied: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in entries:
        if set(raw) != {"kind", "scientific_identity", "manifest_sha256"}:
            raise PerformanceMatrixHarnessError(
                "cache seed entry fields differ"
            )
        kind = str(raw["kind"])
        identity = str(raw["scientific_identity"])
        manifest_sha256 = str(raw["manifest_sha256"])
        key = (kind, identity)
        if key in seen:
            raise PerformanceMatrixHarnessError(
                "cache seed entry identity is duplicated"
            )
        seen.add(key)
        entry = source.resolve_identity(kind, identity)
        if (
            entry is None
            or _sha256_file(entry.manifest_path) != manifest_sha256
        ):
            raise PerformanceMatrixHarnessError(
                "cache seed source entry differs from its accepted manifest"
            )
        destination_path = destination.entry_path(entry.key)
        if destination_path.exists():
            raise PerformanceMatrixHarnessError(
                "cache seed destination entry already exists"
            )
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            entry.path,
            destination_path,
            symlinks=False,
            copy_function=shutil.copy2,
        )
        copied_entry = destination.resolve_identity(kind, identity)
        if (
            copied_entry is None
            or _sha256_file(copied_entry.manifest_path) != manifest_sha256
        ):
            raise PerformanceMatrixHarnessError(
                "copied cache seed entry failed full verification"
            )
        copied.append(
            {
                "kind": kind,
                "scientific_identity": identity,
                "manifest_sha256": manifest_sha256,
            }
        )
    document = {
        "schema_version": "dual_frequency_task17_cache_seed_v1",
        "source_cache_root": str(source_root),
        "destination_cache_root": str(destination_root),
        "entries": copied,
    }
    return {
        **document,
        "seed_sha256": _canonical_sha256(document),
    }


def _prepare_injected_oss_fixture(
    *,
    accepted_closure: Mapping[str, object],
    destination_cache_root: Path,
) -> dict[str, object]:
    """Copy only accepted OSS rows into one benchmark-only fixture cache."""

    source = accepted_closure.get("cache_root")
    closure_sha256 = accepted_closure.get("closure_sha256")
    if type(source) is not str or type(closure_sha256) is not str:
        raise PerformanceMatrixHarnessError(
            "accepted OSS closure lacks its source or identity"
        )
    entries = tuple(
        descriptor
        for descriptor in _accepted_oss_cache_entry_descriptors(
            accepted_closure
        )
        if descriptor["kind"] == "oss_rows"
    )
    seed = _copy_verified_cache_entries(
        source_cache_root=Path(source),
        destination_cache_root=destination_cache_root,
        entries=entries,
    )
    fixture = {
        "schema_version": (
            "dual_frequency_task17_injected_oss_fixture_v1"
        ),
        "accepted_closure_sha256": closure_sha256,
        "fixture_cache_root": seed["destination_cache_root"],
        "permitted_row_identities": [
            item["scientific_identity"] for item in seed["entries"]
        ],
        "seed_sha256": seed["seed_sha256"],
    }
    return {
        **fixture,
        "fixture_sha256": _canonical_sha256(fixture),
    }


def _validate_oss_parent(
    parent_root: Path,
    parent_manifest: Mapping[str, object],
    oss_root: Path,
    oss_manifest: Mapping[str, object],
) -> dict[str, Any]:
    reference = _read_json(
        oss_root / "base_run_reference.json",
        "independent OSS base-run reference",
    )
    expected_fields = {
        "schema_version",
        "base_run_id",
        "base_run_path",
        "base_run_manifest_sha256",
        "scientific_configuration_hash",
        "checkpoint_endpoint_ids",
    }
    if (
        set(reference) != expected_fields
        or reference["schema_version"] != "dual_frequency_base_run_reference_v1"
        or reference["base_run_id"] != parent_manifest["run_id"]
        or reference["base_run_manifest_sha256"]
        != parent_manifest_sha256(parent_root)
        or reference["scientific_configuration_hash"]
        != parent_manifest["scientific_configuration_hash"]
        or oss_manifest.get("parent_run_id") != parent_manifest["run_id"]
        or oss_manifest.get("scientific_configuration_hash")
        != parent_manifest["scientific_configuration_hash"]
    ):
        raise PerformanceMatrixHarnessError(
            "independent OSS parent binding differs"
        )
    return reference


def _validate_input_bundle(
    parent_root: Path,
    request: Mapping[str, object],
) -> dict[str, dict[str, str]]:
    bundle = _read_json(
        parent_root / "inputs" / "input_bundle.json",
        "parent input bundle",
    )
    files = bundle.get("files")
    roles = {
        "study_base": request["study_base"],
        "direct_voxel_model": request["direct_voxel_model"],
        "normative_fiber_model": request["normative_fiber_model"],
        "workflow_profile": request["workflow_profile"],
    }
    if (
        bundle.get("schema_version") != "dual_frequency_input_bundle_v1"
        or not isinstance(files, Mapping)
        or set(files) != set(roles)
    ):
        raise PerformanceMatrixHarnessError("parent input bundle differs")
    output: dict[str, dict[str, str]] = {}
    for role, requested in roles.items():
        item = files[role]
        if not isinstance(item, Mapping) or set(item) != {
            "relative_path",
            "sha256",
        }:
            raise PerformanceMatrixHarnessError(
                f"parent input bundle row differs: {role}"
            )
        bundled = (parent_root / str(item["relative_path"])).resolve()
        if (
            parent_root not in bundled.parents
            or not bundled.is_file()
            or _sha256_file(bundled) != item["sha256"]
        ):
            raise PerformanceMatrixHarnessError(
                f"parent input bundle failed validation: {role}"
            )
        requested_path = Path(str(requested)).expanduser().resolve()
        requested_sha = _sha256_file(requested_path)
        if requested_sha != item["sha256"]:
            raise PerformanceMatrixHarnessError(
                f"requested input differs from parent: {role}"
            )
        output[role] = {
            "path": str(requested_path),
            "sha256": requested_sha,
        }
    return output


def _resolved_snapshot(parent_root: Path) -> dict[str, Any]:
    path = parent_root / "configuration_resolved.yaml"
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PerformanceMatrixHarnessError(
            "parent resolved configuration is unreadable"
        ) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version")
        != "dual_frequency_resolved_configuration_v1"
    ):
        raise PerformanceMatrixHarnessError(
            "parent resolved configuration schema differs"
        )
    return document


def _workflow_request(
    request: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> WorkflowRequest:
    try:
        selected_scales = tuple(snapshot["study"]["selected_scales"])
        selected_models = tuple(snapshot["selection"]["models"])
        selected_connectomes = tuple(snapshot["selection"]["connectomes"])
        execution = snapshot["execution"]
        through = str(execution["through"])
        allow_expensive = bool(execution["allow_expensive_producers"])
        workers = int(execution["workers"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            "parent resolved selection is incomplete"
        ) from exc
    return WorkflowRequest(
        study_base=Path(str(request["study_base"])),
        direct_voxel_model=Path(str(request["direct_voxel_model"])),
        normative_fiber_model=Path(str(request["normative_fiber_model"])),
        workflow_profile=Path(str(request["workflow_profile"])),
        overrides=WorkflowOverrides(
            scales=selected_scales,
            all_available=False,
            models=selected_models,
            connectomes=selected_connectomes,
            through=through,
            resume=False,
            force=False,
            allow_expensive_producers=allow_expensive,
            workers=workers,
        ),
    )


def _axis_count(base: Mapping[str, object], field: str) -> int:
    axis = base.get(field)
    if (
        not isinstance(axis, Mapping)
        or type(axis.get("count")) is not int
        or axis["count"] < 1
    ):
        raise PerformanceMatrixHarnessError(
            f"sensitivity base has an invalid {field}"
        )
    return int(axis["count"])


def _omega_count(base: Mapping[str, object]) -> int:
    omega = base.get("omega_max")
    if (
        not isinstance(omega, Mapping)
        or type(omega.get("axis_count")) is not int
        or omega["axis_count"] < 1
    ):
        raise PerformanceMatrixHarnessError(
            "fiber sensitivity base has an invalid Omega_max axis"
        )
    return int(omega["axis_count"])


def _maximum_base(
    bases: Sequence[Mapping[str, object]],
    *,
    kind: str,
    replicates_by_domain: Mapping[str, int],
) -> tuple[dict[str, object], dict[str, object]]:
    candidates: list[tuple[int, str, Mapping[str, object], dict[str, object]]] = []
    for base in bases:
        endpoint_id = str(base.get("endpoint_id", "")).strip()
        model_family = str(base.get("model_family", "")).strip()
        if not endpoint_id or not model_family:
            raise PerformanceMatrixHarnessError(
                "sensitivity base identity is incomplete"
            )
        subjects = _axis_count(base, "subject_axis")
        features = _axis_count(base, "feature_axis")
        if kind == "ppam":
            if not model_family.endswith("fiber"):
                continue
            support = _omega_count(base)
            domain = "normative_fiber"
        elif kind == "spatial_jitter":
            support = (
                _omega_count(base)
                if model_family.endswith("fiber")
                else features
            )
            domain = (
                "normative_fiber"
                if model_family.endswith("fiber")
                else "direct_voxel"
            )
        else:
            support = subjects * features
            domain = (
                "normative_fiber"
                if model_family.endswith("fiber")
                else "direct_voxel"
            )
        replicates = replicates_by_domain.get(domain)
        if type(replicates) is not int or replicates < 1:
            raise PerformanceMatrixHarnessError(
                f"replicate count is invalid for {domain}"
            )
        burden = support * replicates
        evidence = {
            "endpoint_id": endpoint_id,
            "model_family": model_family,
            "subject_count": subjects,
            "feature_count": features,
            "support_count": support,
            "replicates": replicates,
            "burden": burden,
        }
        candidates.append((burden, endpoint_id, base, evidence))
    if not candidates:
        raise PerformanceMatrixHarnessError(
            f"no realized final supports benchmark class {kind}"
        )
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _burden, _endpoint_id, selected, evidence = candidates[0]
    return dict(selected), {
        "selection_rule": "maximum_structural_burden_then_endpoint_id",
        "selected": evidence,
        "candidates": [
            item[3] for item in sorted(candidates, key=lambda item: item[1])
        ],
    }


def _selected_tasks(
    plan: ExecutionPlan,
    *,
    service_ids: set[str],
    endpoint_id: str | None = None,
    connectome_endpoint_ids: set[str] | None = None,
) -> tuple[TaskSpec, ...]:
    selected = tuple(
        task
        for task in plan.tasks
        if task.service_id in service_ids
        and (endpoint_id is None or task.endpoint_id == endpoint_id)
        and (
            connectome_endpoint_ids is None
            or task.endpoint_id in connectome_endpoint_ids
        )
        and not task.checkpoint_only
    )
    if not selected:
        raise PerformanceMatrixHarnessError(
            "benchmark measured task slice is empty"
        )
    return selected


def _execution_slice_plan(
    source_plan: ExecutionPlan,
    selected: Sequence[TaskSpec],
) -> ExecutionPlan:
    """Close one selected task set with checkpoint-only direct parents."""

    selected_by_id = {task.task_id: task for task in selected}
    if len(selected_by_id) != len(selected) or not selected_by_id:
        raise PerformanceMatrixHarnessError(
            "benchmark selected task identities differ"
        )
    source_by_id = {task.task_id: task for task in source_plan.tasks}
    if not set(selected_by_id) <= set(source_by_id):
        raise PerformanceMatrixHarnessError(
            "benchmark selected tasks escape the source plan"
        )
    imported_ids = {
        dependency
        for task in selected
        for dependency in task.dependencies
        if dependency not in selected_by_id
    }
    missing = sorted(imported_ids - set(source_by_id))
    if missing:
        raise PerformanceMatrixHarnessError(
            "benchmark task slice has unknown dependencies: "
            + ",".join(missing)
        )
    roots = tuple(
        replace(
            source_by_id[task_id],
            dependencies=(),
            gates=(),
            checkpoint_only=True,
        )
        for task_id in sorted(imported_ids)
    )
    ordered_selected = tuple(
        task
        for task in source_plan.tasks
        if task.task_id in selected_by_id
    )
    return ExecutionPlan(
        configuration_hash=source_plan.configuration_hash,
        scientific_configuration_hash=(
            source_plan.scientific_configuration_hash
        ),
        through=source_plan.through,
        tasks=(*roots, *ordered_selected),
    )


def _execution_plan_from_payload(raw: object) -> ExecutionPlan:
    """Decode one exact persisted execution slice without permissive defaults."""

    if not isinstance(raw, Mapping) or set(raw) != {
        "configuration_hash",
        "scientific_configuration_hash",
        "through",
        "tasks",
    }:
        raise PerformanceMatrixHarnessError(
            "persisted execution plan fields differ"
        )
    raw_tasks = raw["tasks"]
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise PerformanceMatrixHarnessError(
            "persisted execution task closure differs"
        )
    task_fields = {
        "key",
        "endpoint_id",
        "model_family",
        "connectome_role",
        "stage",
        "round_id",
        "phase",
        "service_id",
        "dependencies",
        "gates",
        "output_record_type",
        "execution_parameters",
        "expensive_producer",
        "cache_first_expensive",
        "checkpoint_only",
        "timeout_seconds",
        "transient_safe",
        "max_transient_retries",
    }
    tasks: list[TaskSpec] = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, Mapping) or set(item) != task_fields:
            raise PerformanceMatrixHarnessError(
                f"persisted execution task fields differ: {index}"
            )
        key = item["key"]
        if not isinstance(key, Mapping) or set(key) != {
            "endpoint_id",
            "stage",
            "branch",
            "parameter_identity",
        }:
            raise PerformanceMatrixHarnessError(
                f"persisted execution task key differs: {index}"
            )
        gates = item["gates"]
        dependencies = item["dependencies"]
        parameters = item["execution_parameters"]
        if (
            not isinstance(gates, list)
            or not isinstance(dependencies, list)
            or not isinstance(parameters, list)
        ):
            raise PerformanceMatrixHarnessError(
                f"persisted execution task collections differ: {index}"
            )
        decoded_gates: list[GateRequirement] = []
        for gate in gates:
            if not isinstance(gate, Mapping) or set(gate) != {
                "fact",
                "false_status",
            }:
                raise PerformanceMatrixHarnessError(
                    f"persisted execution gate differs: {index}"
                )
            decoded_gates.append(
                GateRequirement(
                    fact=str(gate["fact"]),
                    false_status=str(gate["false_status"]),
                )
            )
        decoded_parameters: list[tuple[str, str]] = []
        for parameter in parameters:
            if (
                not isinstance(parameter, list)
                or len(parameter) != 2
                or not all(isinstance(value, str) for value in parameter)
            ):
                raise PerformanceMatrixHarnessError(
                    f"persisted execution parameter differs: {index}"
                )
            decoded_parameters.append((parameter[0], parameter[1]))
        try:
            task = TaskSpec(
                key=TaskKey(
                    endpoint_id=str(key["endpoint_id"]),
                    stage=str(key["stage"]),
                    branch=str(key["branch"]),
                    parameter_identity=str(key["parameter_identity"]),
                ),
                endpoint_id=str(item["endpoint_id"]),
                model_family=str(item["model_family"]),
                connectome_role=str(item["connectome_role"]),
                stage=str(item["stage"]),
                round_id=str(item["round_id"]),
                phase=str(item["phase"]),
                service_id=str(item["service_id"]),
                dependencies=tuple(str(value) for value in dependencies),
                gates=tuple(decoded_gates),
                output_record_type=str(item["output_record_type"]),
                execution_parameters=tuple(decoded_parameters),
                expensive_producer=item["expensive_producer"],
                cache_first_expensive=item["cache_first_expensive"],
                checkpoint_only=item["checkpoint_only"],
                timeout_seconds=item["timeout_seconds"],
                transient_safe=item["transient_safe"],
                max_transient_retries=item["max_transient_retries"],
            )
        except (TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                f"persisted execution task is invalid: {index}"
            ) from exc
        tasks.append(task)
    try:
        plan = ExecutionPlan(
            configuration_hash=str(raw["configuration_hash"]),
            scientific_configuration_hash=str(
                raw["scientific_configuration_hash"]
            ),
            through=str(raw["through"]),
            tasks=tuple(tasks),
        )
    except (TypeError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            "persisted execution plan is invalid"
        ) from exc
    if _plain(plan) != dict(raw):
        raise PerformanceMatrixHarnessError(
            "persisted execution plan does not round-trip exactly"
        )
    return plan


def _combined_extension_slice_plan(
    full_plan: ExecutionPlan,
    extension_plan: ExecutionPlan,
    *,
    endpoint_id: str,
    extension_services: set[str],
) -> tuple[ExecutionPlan, tuple[TaskSpec, ...]]:
    """Combine one base producer with a selected extension task closure."""

    base_tasks = _selected_tasks(
        full_plan,
        service_ids=_BASE_PREPARE_SERVICES,
        endpoint_id=endpoint_id,
    )
    if len(base_tasks) != 1:
        raise PerformanceMatrixHarnessError(
            "benchmark endpoint must have one base prepare task"
        )
    extension_tasks = _selected_tasks(
        extension_plan,
        service_ids=extension_services,
        endpoint_id=endpoint_id,
    )
    selected_by_id = {
        task.task_id: task for task in (*base_tasks, *extension_tasks)
    }
    if len(selected_by_id) != len(base_tasks) + len(extension_tasks):
        raise PerformanceMatrixHarnessError(
            "benchmark base and extension task slices overlap"
        )
    source_by_id = {task.task_id: task for task in full_plan.tasks}
    source_by_id.update(
        {task.task_id: task for task in extension_plan.tasks}
    )
    source_by_id[base_tasks[0].task_id] = base_tasks[0]
    imported_ids = {
        dependency
        for task in selected_by_id.values()
        for dependency in task.dependencies
        if dependency not in selected_by_id
    }
    missing = sorted(imported_ids - set(source_by_id))
    if missing:
        raise PerformanceMatrixHarnessError(
            "benchmark extension slice has unknown dependencies: "
            + ",".join(missing)
        )
    roots = tuple(
        replace(
            source_by_id[task_id],
            dependencies=(),
            gates=(),
            checkpoint_only=True,
        )
        for task_id in sorted(imported_ids)
    )
    ordered_selected = tuple(
        task
        for task in (*full_plan.tasks, *extension_plan.tasks)
        if task.task_id in selected_by_id
        and selected_by_id[task.task_id] is task
    )
    if len(ordered_selected) != len(selected_by_id):
        ordered_selected = tuple(
            selected_by_id[task_id]
            for task_id in (
                base_tasks[0].task_id,
                *(task.task_id for task in extension_tasks),
            )
        )
    plan = ExecutionPlan(
        configuration_hash=full_plan.configuration_hash,
        scientific_configuration_hash=(
            full_plan.scientific_configuration_hash
        ),
        through="sensitivity",
        tasks=(*roots, *ordered_selected),
    )
    return plan, ordered_selected


def _completed_task_ids(root: Path) -> set[str]:
    completed: set[str] = set()
    tasks_root = root / "tasks"
    for path in sorted(tasks_root.glob("task_*.json")):
        document = _read_json(path, "task state")
        task_id = str(document.get("task_id", "")).strip()
        if (
            task_id
            and path.name == f"{task_id}.json"
            and document.get("status") == "completed"
            and isinstance(document.get("result"), Mapping)
        ):
            completed.add(task_id)
    return completed


def _slice_descriptor(
    plan: ExecutionPlan,
    selected: Sequence[TaskSpec],
    *,
    parent_completed: set[str],
    oss_completed: set[str],
    label: str,
) -> dict[str, object]:
    selected_ids = {task.task_id for task in selected}
    plan_index = {task.task_id: task for task in plan.tasks}
    parent_imports: set[str] = set()
    oss_imports: set[str] = set()
    for task in selected:
        for dependency in task.dependencies:
            if dependency in selected_ids:
                continue
            dependency_task = plan_index.get(dependency)
            if (
                dependency_task is not None
                and dependency_task.service_id == "establish_oss_axis_equivalence"
                and dependency in oss_completed
            ):
                oss_imports.add(dependency)
            elif dependency in parent_completed:
                parent_imports.add(dependency)
            elif dependency in oss_completed:
                oss_imports.add(dependency)
            else:
                raise PerformanceMatrixHarnessError(
                    f"{label} lacks completed imported dependency {dependency}"
                )
    ordered_selected = [
        task.task_id for task in plan.tasks if task.task_id in selected_ids
    ]
    if len(ordered_selected) != len(selected_ids):
        raise PerformanceMatrixHarnessError(
            f"{label} selected task closure differs from its plan"
        )
    return {
        "slice_id": _canonical_sha256(
            {
                "label": label,
                "plan_hash": plan_hash(plan),
                "selected_task_ids": ordered_selected,
                "imported_parent_task_ids": sorted(parent_imports),
                "imported_oss_task_ids": sorted(oss_imports),
            }
        ),
        "label": label,
        "plan_hash": plan_hash(plan),
        "execution_plan": _plain(plan),
        "selected_task_ids": ordered_selected,
        "selected_tasks": [
            {
                "task_id": task.task_id,
                "endpoint_id": task.endpoint_id,
                "service_id": task.service_id,
                "stage": task.stage,
                "dependencies": list(task.dependencies),
            }
            for task in plan.tasks
            if task.task_id in selected_ids
        ],
        "imported_parent_task_ids": sorted(parent_imports),
        "imported_oss_task_ids": sorted(oss_imports),
    }


def _row_keys(connectomes: Sequence[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    classes = [
        ("direct_voxel", None),
        *(("fiber_connectome", connectome) for connectome in connectomes),
        ("formal_permutation", None),
        ("bootstrap", None),
        ("spatial_jitter", None),
    ]
    for benchmark_class, connectome in classes:
        for cache_state in ("cold", "warm"):
            for workers in _WORKERS:
                rows.append(
                    {
                        "benchmark_class": benchmark_class,
                        "connectome_id": connectome,
                        "cache_state": cache_state,
                        "solver_mode": "none",
                        "workers": workers,
                    }
                )
    for cache_state in ("cold", "warm"):
        for workers in _WORKERS:
            rows.append(
                {
                    "benchmark_class": "ppam",
                    "connectome_id": None,
                    "cache_state": cache_state,
                    "solver_mode": "injected",
                    "workers": workers,
                }
            )
    for workers in _WORKERS:
        rows.append(
            {
                "benchmark_class": "ppam",
                "connectome_id": None,
                "cache_state": "warm",
                "solver_mode": "real_cache_hit",
                "workers": workers,
            }
        )
        rows.append(
            {
                "benchmark_class": "ppam",
                "connectome_id": None,
                "cache_state": "cold",
                "solver_mode": "real_solver",
                "workers": workers,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row["benchmark_class"]),
            str(row["connectome_id"]),
            str(row["cache_state"]),
            str(row["solver_mode"]),
            int(row["workers"]),
        ),
    )


def _row_key_payload(row: Mapping[str, object]) -> dict[str, object]:
    expected = {
        "benchmark_class",
        "connectome_id",
        "cache_state",
        "solver_mode",
        "workers",
    }
    if not expected <= set(row):
        raise PerformanceMatrixHarnessError(
            "benchmark row key fields are incomplete"
        )
    return {field: row[field] for field in sorted(expected)}


def _row_id(plan_identity_sha256: str, row: Mapping[str, object]) -> str:
    digest = str(plan_identity_sha256).strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark plan identity SHA differs"
        )
    return "row_" + _canonical_sha256(
        {
            "plan_identity_sha256": digest,
            "key": _row_key_payload(row),
        }
    )[:20]


def _row_contract(
    resolved_plan: Mapping[str, object],
    row: Mapping[str, object],
) -> dict[str, object]:
    row_id = str(row.get("row_id", "")).strip()
    if not row_id.startswith("row_") or "/" in row_id or "\\" in row_id:
        raise PerformanceMatrixHarnessError("benchmark row ID differs")
    resolved_sha = _canonical_sha256(resolved_plan)
    slice_id = str(row.get("slice_id", "")).strip().lower()
    if len(slice_id) != 64 or any(
        character not in "0123456789abcdef" for character in slice_id
    ):
        raise PerformanceMatrixHarnessError("benchmark row slice ID differs")
    maximum_rss = resolved_plan.get("maximum_task_tree_rss_bytes")
    if type(maximum_rss) is not int or maximum_rss < 1:
        raise PerformanceMatrixHarnessError(
            "resolved benchmark RSS ceiling differs"
        )
    cache_state = str(row["cache_state"])
    seed_key = (
        f"{row['benchmark_class']}:{row['connectome_id']}:{row['solver_mode']}"
        if cache_state == "warm"
        else None
    )
    return {
        "schema_version": _ROW_CONTRACT_SCHEMA,
        "row_id": row_id,
        "resolved_plan_sha256": resolved_sha,
        "key": _row_key_payload(row),
        "slice_id": slice_id,
        "cache_seed_key": seed_key,
        "maximum_task_tree_rss_bytes": maximum_rss,
        "planned_status": row["planned_status"],
        "expected_evidence": {
            "run_manifest": "run/run_manifest.json",
            "probe": "attempts/<attempt>/probe.csv",
            "counter": "run/execution_segments/performance_counters_<segment>.json",
            "row_result": "row_result.json",
        },
    }


def _ensure_row_contract(
    row_root: Path,
    contract: Mapping[str, object],
) -> tuple[Path, str]:
    root = row_root.expanduser().resolve()
    if root.exists() and root.is_symlink():
        raise PerformanceMatrixHarnessError("benchmark row root cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    path = root / "row_contract.json"
    _atomic_json(path, contract)
    return path, _sha256_file(path)


def _next_attempt(row_root: Path) -> tuple[Path, int]:
    attempts_root = row_root.expanduser().resolve() / "attempts"
    attempts_root.mkdir(parents=True, exist_ok=True)
    indexes: list[int] = []
    for path in attempts_root.glob("attempt_*"):
        suffix = path.name.removeprefix("attempt_")
        if path.is_dir() and len(suffix) == 4 and suffix.isdigit():
            indexes.append(int(suffix))
    index = max(indexes, default=0) + 1
    attempt = attempts_root / f"attempt_{index:04d}"
    attempt.mkdir()
    return attempt, index


def _relative_evidence(
    path: Path,
    *,
    row_root: Path,
) -> dict[str, str]:
    root = row_root.expanduser().resolve()
    source = path.expanduser().resolve()
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise PerformanceMatrixHarnessError(
            "row evidence lies outside its row root"
        ) from exc
    if not source.is_file():
        raise PerformanceMatrixHarnessError("row evidence file is missing")
    return {
        "relative_path": relative.as_posix(),
        "sha256": _sha256_file(source),
    }


def _validate_row_result(
    row_root: Path,
    contract_sha256: str,
) -> dict[str, object] | None:
    root = row_root.expanduser().resolve()
    path = root / "row_result.json"
    if not path.exists():
        return None
    document = _read_json(path, "terminal benchmark row")
    expected = {
        "schema_version",
        "row_id",
        "contract_sha256",
        "status",
        "attempt",
        "evidence",
        "not_run_reason",
    }
    if (
        set(document) != expected
        or document["schema_version"] != _ROW_RESULT_SCHEMA
        or document["contract_sha256"] != contract_sha256
        or document["status"] not in {"executed", "not_run"}
    ):
        raise PerformanceMatrixHarnessError(
            "terminal benchmark row identity differs"
        )
    evidence = document["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise PerformanceMatrixHarnessError(
            "terminal benchmark row evidence is incomplete"
        )
    seen: set[Path] = set()
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {
            "relative_path",
            "sha256",
        }:
            raise PerformanceMatrixHarnessError(
                "terminal benchmark row evidence fields differ"
            )
        relative = Path(str(item["relative_path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise PerformanceMatrixHarnessError(
                "terminal benchmark row evidence path is unsafe"
            )
        source = (root / relative).resolve()
        if (
            source in seen
            or root not in source.parents
            or not source.is_file()
            or _sha256_file(source) != item["sha256"]
        ):
            raise PerformanceMatrixHarnessError(
                "terminal benchmark row evidence SHA differs"
            )
        seen.add(source)
    if (
        document["status"] == "not_run"
        and document["not_run_reason"] != "real_cold_solver_not_authorized"
    ) or (
        document["status"] == "executed"
        and document["not_run_reason"] is not None
    ):
        raise PerformanceMatrixHarnessError(
            "terminal benchmark row status differs"
        )
    return document


def _publish_not_run_row(
    row_root: Path,
    *,
    contract_sha256: str,
    row: Mapping[str, object],
    authorization: Mapping[str, object],
) -> dict[str, object]:
    root = row_root.expanduser().resolve()
    key = _row_key_payload(row)
    if (
        key
        != {
            "benchmark_class": "ppam",
            "cache_state": "cold",
            "connectome_id": None,
            "solver_mode": "real_solver",
            "workers": row["workers"],
        }
        or row.get("planned_status") != "not_run"
        or authorization
        != {
            "authorized": False,
            "path": None,
            "sha256": None,
        }
    ):
        raise PerformanceMatrixHarnessError(
            "only an unauthorized real cold solver row may be not_run"
        )
    preflight = {
        "schema_version": _NOT_RUN_PREFLIGHT_SCHEMA,
        "row_id": row["row_id"],
        "key": key,
        "authorized": False,
        "reason": "real_cold_solver_not_authorized",
        "authorization_path": None,
        "authorization_sha256": None,
    }
    preflight_path = root / "real_cold_solver_preflight.json"
    _atomic_json(preflight_path, preflight)
    result = {
        "schema_version": _ROW_RESULT_SCHEMA,
        "row_id": row["row_id"],
        "contract_sha256": contract_sha256,
        "status": "not_run",
        "attempt": 0,
        "evidence": [
            _relative_evidence(
                preflight_path,
                row_root=root,
            )
        ],
        "not_run_reason": "real_cold_solver_not_authorized",
    }
    _atomic_json(root / "row_result.json", result)
    validated = _validate_row_result(root, contract_sha256)
    if validated != result:
        raise PerformanceMatrixHarnessError(
            "terminal not-run row differs after publication"
        )
    return result


def _row_contract_closure(
    resolved_plan: Mapping[str, object],
) -> list[dict[str, str]]:
    rows = resolved_plan.get("rows")
    if not isinstance(rows, list) or len(rows) != 72:
        raise PerformanceMatrixHarnessError(
            "resolved benchmark row closure differs"
        )
    closure: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise PerformanceMatrixHarnessError(
                "resolved benchmark row must be an object"
            )
        contract = _row_contract(resolved_plan, row)
        row_id = str(contract["row_id"])
        if row_id in seen:
            raise PerformanceMatrixHarnessError(
                "resolved benchmark row ID is duplicated"
            )
        seen.add(row_id)
        closure.append(
            {
                "row_id": row_id,
                "relative_path": f"rows/{row_id}/row_contract.json",
                "sha256": _document_sha256(contract),
            }
        )
    return sorted(closure, key=lambda item: item["row_id"])


def _publish_row_contracts(
    root: Path,
    resolved_plan: Mapping[str, object],
    closure: Sequence[Mapping[str, str]],
) -> None:
    root = root.expanduser().resolve()
    rows = resolved_plan["rows"]
    row_index = {str(row["row_id"]): row for row in rows}
    for item in closure:
        row_id = str(item["row_id"])
        contract = _row_contract(resolved_plan, row_index[row_id])
        path, digest = _ensure_row_contract(root / "rows" / row_id, contract)
        expected = root / str(item["relative_path"])
        if path != expected or digest != item["sha256"]:
            raise PerformanceMatrixHarnessError(
                "published benchmark row contract differs"
            )


def _validate_row_contracts(
    root: Path,
    resolved_plan: Mapping[str, object],
    closure: Sequence[Mapping[str, str]],
) -> None:
    root = root.expanduser().resolve()
    rows_root = root / "rows"
    expected_ids = {str(item["row_id"]) for item in closure}
    actual_ids = {
        path.name
        for path in rows_root.glob("row_*")
        if path.is_dir()
    }
    if actual_ids != expected_ids:
        raise PerformanceMatrixHarnessError(
            "prepared benchmark row-directory closure differs"
        )
    row_index = {
        str(row["row_id"]): row for row in resolved_plan["rows"]
    }
    for item in closure:
        row_id = str(item["row_id"])
        relative = Path(str(item["relative_path"]))
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative
            != Path("rows") / row_id / "row_contract.json"
        ):
            raise PerformanceMatrixHarnessError(
                "prepared benchmark row-contract path differs"
            )
        path = root / relative
        expected_contract = _row_contract(
            resolved_plan,
            row_index[row_id],
        )
        if (
            not path.is_file()
            or _sha256_file(path) != item["sha256"]
            or _read_json(path, "benchmark row contract")
            != expected_contract
        ):
            raise PerformanceMatrixHarnessError(
                "prepared benchmark row contract differs"
            )


def _resolved_row(
    resolved: Mapping[str, object],
    row_id: str,
) -> dict[str, object]:
    """Return one exact row from an immutable resolved benchmark plan."""

    rows = resolved.get("rows")
    if not isinstance(rows, list):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark rows are invalid"
        )
    matches = tuple(
        dict(row)
        for row in rows
        if isinstance(row, Mapping) and row.get("row_id") == row_id
    )
    if len(matches) != 1:
        raise PerformanceMatrixHarnessError(
            "benchmark row identity does not resolve exactly once"
        )
    return matches[0]


def _resolved_slice(
    resolved: Mapping[str, object],
    row: Mapping[str, object],
) -> tuple[dict[str, object], ExecutionPlan]:
    """Return and decode the exact executable slice bound to one row."""

    slice_id = row.get("slice_id")
    slices = resolved.get("slices")
    if type(slice_id) is not str or not isinstance(slices, list):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark slice binding is invalid"
        )
    matches = tuple(
        dict(item)
        for item in slices
        if isinstance(item, Mapping) and item.get("slice_id") == slice_id
    )
    if len(matches) != 1:
        raise PerformanceMatrixHarnessError(
            "benchmark slice identity does not resolve exactly once"
        )
    descriptor = matches[0]
    plan = _execution_plan_from_payload(descriptor.get("execution_plan"))
    selected_task_ids = descriptor.get("selected_task_ids")
    if (
        not isinstance(selected_task_ids, list)
        or sorted(
            task.task_id for task in plan.tasks if not task.checkpoint_only
        )
        != sorted(str(value) for value in selected_task_ids)
        or plan_hash(plan) != descriptor.get("plan_hash")
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark executable slice differs from its selected task closure"
        )
    return descriptor, plan


def _authorization(
    raw: object,
) -> dict[str, object]:
    if raw is None:
        return {
            "authorized": False,
            "path": None,
            "sha256": None,
        }
    path = Path(str(raw)).expanduser().resolve()
    document = _read_json(path, "real cold solver authorization")
    if document.get("authorized") is not True:
        raise PerformanceMatrixHarnessError(
            "real cold solver authorization does not authorize execution"
        )
    return {
        "authorized": True,
        "path": str(path),
        "sha256": _sha256_file(path),
    }


def _benchmark_root(
    root: Path,
    *,
    protected: Sequence[Path],
) -> Path:
    resolved = root.expanduser().resolve()
    for item in protected:
        if (
            resolved == item
            or item in resolved.parents
            or resolved in item.parents
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark root overlaps a protected production root"
            )
    if resolved.exists() and resolved.is_symlink():
        raise PerformanceMatrixHarnessError(
            "benchmark root cannot be a symlink"
        )
    return resolved


def _prepare_document(
    request_path: Path,
    benchmark_root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    request, request_sha = _load_request(request_path)
    parent_root = Path(str(request["accepted_parent_root"])).expanduser().resolve()
    oss_root = Path(
        str(request["accepted_independent_oss_root"])
    ).expanduser().resolve()
    parent_manifest = _terminal_run(parent_root, "accepted parent")
    oss_manifest = _terminal_run(oss_root, "accepted independent OSS")
    oss_reference = _validate_oss_parent(
        parent_root,
        parent_manifest,
        oss_root,
        oss_manifest,
    )
    oss_gate_records = _accepted_oss_gate_records(oss_root)
    input_sources = _validate_input_bundle(parent_root, request)
    snapshot = _resolved_snapshot(parent_root)
    workflow_request = _workflow_request(request, snapshot)
    try:
        bundle = WorkflowService().plan(workflow_request)
    except (ApplicationError, OSError, RuntimeError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            "cannot compile the accepted parent workflow"
        ) from exc
    if (
        bundle.validated.configuration.scientific_configuration_hash
        != parent_manifest.get("scientific_configuration_hash")
        or plan_hash(bundle.plan) != parent_manifest.get("plan_hash")
    ):
        raise PerformanceMatrixHarnessError(
            "compiled parent scientific configuration or plan differs"
        )
    configuration = bundle.validated.configuration
    cache_root = configuration.workflow.storage.cache_root.expanduser().resolve()
    accepted_oss_cache = _accepted_oss_cache_closure(
        oss_gate_records,
        cache_root=cache_root,
    )
    output_root = configuration.direct_voxel.output.root.expanduser().resolve()
    run_root = configuration.workflow.storage.run_root.expanduser().resolve()
    root = _benchmark_root(
        benchmark_root,
        protected=(
            parent_root,
            oss_root,
            cache_root,
            output_root,
            run_root,
        ),
    )
    try:
        checkpoint = load_sensitivity_checkpoint(
            parent_root,
            cache_root=cache_root,
            output_root=output_root,
        )
    except SensitivityCheckpointError as exc:
        raise PerformanceMatrixHarnessError(
            "accepted parent sensitivity checkpoint is invalid"
        ) from exc
    bases = tuple(dict(base) for base in checkpoint.bases)
    if set(checkpoint.endpoint_ids) != set(oss_reference["checkpoint_endpoint_ids"]):
        raise PerformanceMatrixHarnessError(
            "independent OSS endpoint closure differs from the parent"
        )
    parent_completed = _completed_task_ids(parent_root)
    oss_completed = _completed_task_ids(oss_root)
    if not set(checkpoint.seed_task_ids) <= parent_completed:
        raise PerformanceMatrixHarnessError(
            "parent seed task closure is not terminal"
        )

    direct_tasks = _selected_tasks(
        bundle.plan,
        service_ids=_MAIN_SLICE_SERVICES["direct_voxel"],
    )
    direct_slice_plan = _execution_slice_plan(
        bundle.plan,
        direct_tasks,
    )
    slices: dict[str, dict[str, object]] = {
        "direct_voxel": _slice_descriptor(
            direct_slice_plan,
            direct_tasks,
            parent_completed=parent_completed,
            oss_completed=oss_completed,
            label="direct_voxel",
        )
    }
    endpoint_catalog = {
        endpoint.endpoint_id: endpoint for endpoint in bundle.validated.catalog
    }
    connectomes = tuple(
        item.connectome_id
        for item in configuration.normative_fiber.connectomes
        if item.connectome_id in configuration.selected_connectomes
    )
    if len(connectomes) != 3 or len(set(connectomes)) != len(connectomes):
        raise PerformanceMatrixHarnessError(
            "configured benchmark requires exactly three connectomes"
        )
    for connectome in connectomes:
        endpoint_ids = {
            endpoint_id
            for endpoint_id, endpoint in endpoint_catalog.items()
            if endpoint.key.connectome_id == connectome
        }
        tasks = _selected_tasks(
            bundle.plan,
            service_ids=_MAIN_SLICE_SERVICES["fiber_connectome"],
            connectome_endpoint_ids=endpoint_ids,
        )
        slice_plan = _execution_slice_plan(bundle.plan, tasks)
        slices[f"fiber_connectome:{connectome}"] = _slice_descriptor(
            slice_plan,
            tasks,
            parent_completed=parent_completed,
            oss_completed=oss_completed,
            label=f"fiber_connectome:{connectome}",
        )

    formal_base, formal_burden = _maximum_base(
        bases,
        kind="formal_permutation",
        replicates_by_domain={
            "direct_voxel": int(
                configuration.direct_voxel.formal_resampling.permutation_resamples
            ),
            "normative_fiber": int(
                configuration.normative_fiber.formal_resampling.permutation_resamples
            ),
        },
    )
    bootstrap_base, bootstrap_burden = _maximum_base(
        bases,
        kind="bootstrap",
        replicates_by_domain={
            "direct_voxel": int(
                configuration.direct_voxel.formal_resampling.bootstrap_resamples
            ),
            "normative_fiber": int(
                configuration.normative_fiber.formal_resampling.bootstrap_resamples
            ),
        },
    )
    for kind, base in (
        ("formal_permutation", formal_base),
        ("bootstrap", bootstrap_base),
    ):
        tasks = _selected_tasks(
            bundle.plan,
            service_ids={
                *_MAIN_SLICE_SERVICES[kind],
                *_BASE_PREPARE_SERVICES,
            },
            endpoint_id=str(base["endpoint_id"]),
        )
        slice_plan = _execution_slice_plan(bundle.plan, tasks)
        slices[kind] = _slice_descriptor(
            slice_plan,
            tasks,
            parent_completed=parent_completed,
            oss_completed=oss_completed,
            label=kind,
        )

    jitter_base, jitter_burden = _maximum_base(
        bases,
        kind="spatial_jitter",
        replicates_by_domain={
            "direct_voxel": int(
                configuration.direct_voxel.formal_resampling.jitter_resamples
            ),
            "normative_fiber": int(
                configuration.normative_fiber.formal_resampling.jitter_resamples
            ),
        },
    )
    try:
        jitter_plan = compile_sensitivity_extension_plan(
            bundle.plan,
            endpoint_ids=(str(jitter_base["endpoint_id"]),),
            analyses=("jitter",),
            seed_task_ids=checkpoint.seed_task_ids,
            jitter_bases=bases,
        )
    except SensitivityCheckpointError as exc:
        raise PerformanceMatrixHarnessError(
            "cannot compile the jitter benchmark slice"
        ) from exc
    jitter_slice_plan, jitter_tasks = _combined_extension_slice_plan(
        bundle.plan,
        jitter_plan,
        endpoint_id=str(jitter_base["endpoint_id"]),
        extension_services=_JITTER_SERVICES,
    )
    slices["spatial_jitter"] = _slice_descriptor(
        jitter_slice_plan,
        jitter_tasks,
        parent_completed=parent_completed,
        oss_completed=oss_completed,
        label="spatial_jitter",
    )

    ppam_base, ppam_burden = _maximum_base(
        bases,
        kind="ppam",
        replicates_by_domain={
            "normative_fiber": int(
                configuration.normative_fiber.oss.permutation_resamples
            ),
        },
    )
    try:
        ppam_plan = compile_sensitivity_extension_plan(
            bundle.plan,
            endpoint_ids=(str(ppam_base["endpoint_id"]),),
            analyses=("oss",),
            seed_task_ids=checkpoint.seed_task_ids,
            sensitivity_bases=bases,
        )
    except SensitivityCheckpointError as exc:
        raise PerformanceMatrixHarnessError(
            "cannot compile the pPAM benchmark slice"
        ) from exc
    ppam_slice_plan, ppam_tasks = _combined_extension_slice_plan(
        bundle.plan,
        ppam_plan,
        endpoint_id=str(ppam_base["endpoint_id"]),
        extension_services=_PPAM_SERVICES,
    )
    for solver_mode in ("injected", "real_cache_hit", "real_solver"):
        label = f"ppam:{solver_mode}"
        slices[label] = _slice_descriptor(
            ppam_slice_plan,
            ppam_tasks,
            parent_completed=parent_completed,
            oss_completed=oss_completed,
            label=label,
        )

    authorization = _authorization(request["real_cold_solver_authorization"])
    burden_selections = {
        "formal_permutation": formal_burden,
        "bootstrap": bootstrap_burden,
        "spatial_jitter": jitter_burden,
        "ppam": ppam_burden,
    }
    plan_identity_sha256 = _canonical_sha256(
        {
            "request_sha256": request_sha,
            "accepted_parent_manifest_sha256": parent_manifest_sha256(
                parent_root
            ),
            "accepted_independent_oss_manifest_sha256": (
                parent_manifest_sha256(oss_root)
            ),
            "accepted_oss_cache_closure_sha256": accepted_oss_cache[
                "closure_sha256"
            ],
            "scientific_configuration_hash": (
                bundle.validated.configuration.scientific_configuration_hash
            ),
            "full_plan_hash": plan_hash(bundle.plan),
            "configured_connectomes": list(connectomes),
            "workers": list(_WORKERS),
            "maximum_task_tree_rss_bytes": request[
                "maximum_task_tree_rss_bytes"
            ],
            "real_cold_solver_authorization": authorization,
            "burden_selections": burden_selections,
            "slices": [slices[key] for key in sorted(slices)],
        }
    )
    rows = _row_keys(connectomes)
    for row in rows:
        benchmark_class = str(row["benchmark_class"])
        slice_key = (
            f"fiber_connectome:{row['connectome_id']}"
            if benchmark_class == "fiber_connectome"
            else (
                f"ppam:{row['solver_mode']}"
                if benchmark_class == "ppam"
                else benchmark_class
            )
        )
        row["slice_id"] = slices[slice_key]["slice_id"]
        row["planned_status"] = (
            "planned"
            if row["solver_mode"] != "real_solver"
            or authorization["authorized"]
            else "not_run"
        )
        row["row_id"] = _row_id(plan_identity_sha256, row)
    resolved = {
        "schema_version": _RESOLVED_SCHEMA,
        "plan_id": request["plan_id"],
        "request_sha256": request_sha,
        "plan_identity_sha256": plan_identity_sha256,
        "accepted_parent": {
            "root": str(parent_root),
            "run_id": parent_manifest["run_id"],
            "manifest_sha256": parent_manifest_sha256(parent_root),
        },
        "accepted_independent_oss": {
            "root": str(oss_root),
            "run_id": oss_manifest["run_id"],
            "manifest_sha256": parent_manifest_sha256(oss_root),
        },
        "accepted_oss_cache": accepted_oss_cache,
        "input_sources": input_sources,
        "scientific_configuration_hash": (
            bundle.validated.configuration.scientific_configuration_hash
        ),
        "full_plan_hash": plan_hash(bundle.plan),
        "configured_connectomes": list(connectomes),
        "workers": list(_WORKERS),
        "maximum_task_tree_rss_bytes": request[
            "maximum_task_tree_rss_bytes"
        ],
        "real_cold_solver_authorization": authorization,
        "burden_selections": burden_selections,
        "slices": [slices[key] for key in sorted(slices)],
        "rows": rows,
    }
    row_contracts = _row_contract_closure(resolved)
    marker = {
        "schema_version": _MARKER_SCHEMA,
        "plan_id": request["plan_id"],
        "request_sha256": request_sha,
        "resolved_plan_sha256": _canonical_sha256(resolved),
        "row_contracts": row_contracts,
        "benchmark_root": str(root),
    }
    return resolved, marker


def prepare(request_path: Path, benchmark_root: Path) -> dict[str, object]:
    """Validate authorities and publish one immutable resolved benchmark plan."""

    resolved, marker = _prepare_document(request_path, benchmark_root)
    root = Path(str(marker["benchmark_root"]))
    root.mkdir(parents=True, exist_ok=True)
    marker_path = root / "benchmark_root.json"
    if marker_path.exists():
        stored_plan = _read_json(
            root / "benchmark_plan_resolved.json",
            "resolved benchmark plan",
        )
        stored_marker = _read_json(
            marker_path,
            "benchmark root marker",
        )
        if stored_plan != resolved or stored_marker != marker:
            raise PerformanceMatrixHarnessError(
                "prepared benchmark plan differs from current authority"
            )
        _validate_row_contracts(
            root,
            resolved,
            marker["row_contracts"],
        )
        return {
            "status": "prepared",
            "benchmark_root": str(root),
            "resolved_plan_sha256": marker["resolved_plan_sha256"],
            "row_count": len(resolved["rows"]),
        }
    _atomic_json(root / "benchmark_plan_resolved.json", resolved)
    _publish_row_contracts(
        root,
        resolved,
        marker["row_contracts"],
    )
    _atomic_json(marker_path, marker)
    return {
        "status": "prepared",
        "benchmark_root": str(root),
        "resolved_plan_sha256": marker["resolved_plan_sha256"],
        "row_count": len(resolved["rows"]),
    }


def _open_prepared_benchmark(
    request_path: Path,
    benchmark_root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    """Open one marker-complete benchmark root without repairing it."""

    request, request_sha256 = _load_request(request_path)
    root = benchmark_root.expanduser().resolve()
    resolved = _read_json(
        root / "benchmark_plan_resolved.json",
        "resolved benchmark plan",
    )
    marker = _read_json(
        root / "benchmark_root.json",
        "benchmark root marker",
    )
    expected_marker_fields = {
        "schema_version",
        "plan_id",
        "request_sha256",
        "resolved_plan_sha256",
        "row_contracts",
        "benchmark_root",
    }
    if (
        resolved.get("schema_version") != _RESOLVED_SCHEMA
        or set(marker) != expected_marker_fields
        or marker.get("schema_version") != _MARKER_SCHEMA
        or marker.get("plan_id") != request["plan_id"]
        or marker.get("request_sha256") != request_sha256
        or marker.get("benchmark_root") != str(root)
        or marker.get("resolved_plan_sha256")
        != _canonical_sha256(resolved)
    ):
        raise PerformanceMatrixHarnessError(
            "prepared benchmark root identity differs"
        )
    row_contracts = marker.get("row_contracts")
    if not isinstance(row_contracts, list):
        raise PerformanceMatrixHarnessError(
            "prepared benchmark row-contract marker is invalid"
        )
    _validate_row_contracts(root, resolved, row_contracts)
    return resolved, marker


def validate_existing(
    request_path: Path,
    benchmark_root: Path,
) -> dict[str, object]:
    """Recompute and validate a prepared plan without changing the root."""

    resolved, marker = _prepare_document(request_path, benchmark_root)
    root = Path(str(marker["benchmark_root"]))
    stored_plan = _read_json(
        root / "benchmark_plan_resolved.json",
        "resolved benchmark plan",
    )
    stored_marker = _read_json(
        root / "benchmark_root.json",
        "benchmark root marker",
    )
    if stored_plan != resolved or stored_marker != marker:
        raise PerformanceMatrixHarnessError(
            "prepared benchmark plan differs from current authority"
        )
    _validate_row_contracts(
        root,
        resolved,
        marker["row_contracts"],
    )
    return {
        "status": "validated",
        "benchmark_root": str(root),
        "resolved_plan_sha256": marker["resolved_plan_sha256"],
        "row_count": len(resolved["rows"]),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "validate"))
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--benchmark-root", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.operation == "prepare":
            result = prepare(arguments.request, arguments.benchmark_root)
        else:
            result = validate_existing(
                arguments.request,
                arguments.benchmark_root,
            )
    except (
        ApplicationError,
        PerformanceMatrixHarnessError,
        SensitivityCheckpointError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
