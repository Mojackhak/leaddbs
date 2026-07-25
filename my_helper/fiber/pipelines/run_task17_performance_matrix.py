#!/usr/bin/env python3
"""Prepare and validate the immutable Task 17 performance benchmark plan."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import unquote, urlparse

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
from dual_frequency.cache import ArtifactStore, ContentAddressedCache  # noqa: E402
from dual_frequency.catalog import CatalogStatus  # noqa: E402
from dual_frequency.config import WorkflowOverrides  # noqa: E402
from dual_frequency.contracts import (  # noqa: E402
    ArtifactRef,
    FinalSelectionRecord,
    OSSAxisEquivalenceGroupRecord,
    PreparedExposureRecord,
    SensitiveRecord,
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
    ExecutionContext,
    RunIdentity,
    RunStore,
    ServiceResult,
    SpawnWorkerSpec,
    TaskSpec,
    execute_plan,
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


class _TaskStateStore(Protocol):
    def write_task_state(
        self,
        task_id: str,
        payload: Mapping[str, object],
    ) -> None:
        """Persist one task state."""

    def read_task_state(self, task_id: str) -> dict[str, object] | None:
        """Read one task state."""


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


def _numerical_payload(value: object) -> object:
    """Remove only run-local locations from one scientific result payload."""

    if isinstance(value, Mapping):
        return {
            str(key): _numerical_payload(item)
            for key, item in value.items()
            if key not in {"uri", "generation_path"}
        }
    if isinstance(value, (list, tuple)):
        return [_numerical_payload(item) for item in value]
    return _plain(value)


def _selected_numerical_identity(
    store: _TaskStateStore,
    task_ids: Sequence[str],
) -> str:
    """Hash the normalized selected-task scientific result closure."""

    rows: list[dict[str, object]] = []
    for task_id in sorted(str(value) for value in task_ids):
        state = store.read_task_state(task_id)
        if (
            not isinstance(state, Mapping)
            or state.get("status") != "completed"
            or not isinstance(state.get("result"), Mapping)
        ):
            raise PerformanceMatrixHarnessError(
                "selected numerical task state is incomplete"
            )
        result = dict(state["result"])
        try:
            ServiceResult.from_dict(result).decode_record()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "selected numerical task result is invalid"
            ) from exc
        rows.append(
            {
                "task_id": task_id,
                "result": _numerical_payload(result),
            }
        )
    if not rows:
        raise PerformanceMatrixHarnessError(
            "selected numerical task closure is empty"
        )
    return _canonical_sha256(rows)


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


def _artifact_file(
    artifact: ArtifactRef,
    *,
    label: str,
) -> Path:
    """Resolve and verify one immutable local artifact reference."""

    if not isinstance(artifact, ArtifactRef):
        raise PerformanceMatrixHarnessError(f"{label} is not an artifact")
    parsed = urlparse(artifact.uri)
    if parsed.scheme != "file" or parsed.netloc:
        raise PerformanceMatrixHarnessError(
            f"{label} must use a local file URI"
        )
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_file() or _sha256_file(path) != artifact.sha256:
        raise PerformanceMatrixHarnessError(f"{label} SHA differs")
    return path


def _candidate_artifact_descriptor(
    artifact: ArtifactRef,
    *,
    feature_axis_sha256: str,
    label: str,
) -> dict[str, object]:
    """Convert one verified NPY artifact to candidate-parity evidence."""

    path = _artifact_file(artifact, label=label)
    if artifact.dtype is None or artifact.shape is None:
        raise PerformanceMatrixHarnessError(
            f"{label} lacks array metadata"
        )
    try:
        value = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            f"{label} is not a readable NPY array"
        ) from exc
    if (
        value.dtype.name != artifact.dtype
        or value.shape != artifact.shape
    ):
        raise PerformanceMatrixHarnessError(
            f"{label} array metadata differs"
        )
    return {
        "path": str(path),
        "sha256": artifact.sha256,
        "dtype": artifact.dtype,
        "shape": list(artifact.shape),
        "feature_axis_sha256": str(feature_axis_sha256),
    }


def _atomic_selected_ids(
    path: Path,
    values: np.ndarray,
) -> Path:
    """Publish one immutable benchmark-local ordered feature-ID array."""

    destination = path.expanduser().resolve()
    selected = np.asarray(values, dtype=np.int64)
    if (
        selected.ndim != 1
        or selected.size < 1
        or np.any(selected[1:] <= selected[:-1])
    ):
        raise PerformanceMatrixHarnessError(
            "candidate-parity selected feature IDs are invalid"
        )
    if destination.exists():
        try:
            existing = np.load(destination, allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "candidate-parity selected-ID artifact is unreadable"
            ) from exc
        if (
            existing.dtype != np.dtype(np.int64)
            or not np.array_equal(existing, selected)
        ):
            raise PerformanceMatrixHarnessError(
                "candidate-parity selected-ID artifact differs"
            )
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.save(handle, selected, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _completed_parent_records(
    parent_root: Path,
) -> tuple[
    dict[str, PreparedExposureRecord],
    dict[str, FinalSelectionRecord | SensitiveRecord],
]:
    """Decode the exact prepared and selected configured endpoint closure."""

    root = parent_root.expanduser().resolve()
    status_path = root / "task_status.csv"
    try:
        with status_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            expected_fields = (
                "task_id",
                "endpoint_id",
                "service_id",
                "status",
                "reason",
            )
            if tuple(reader.fieldnames or ()) != expected_fields:
                raise PerformanceMatrixHarnessError(
                    "accepted parent task-status fields differ"
                )
            rows = tuple(reader)
    except OSError as exc:
        raise PerformanceMatrixHarnessError(
            "accepted parent task-status table is unreadable"
        ) from exc
    prepare_services = {
        "prepare_reference_voxel_exposure",
        "prepare_addon_voxel_exposure",
        "prepare_reference_fiber_sidecar",
        "prepare_addon_fiber_sidecars",
    }
    selection_services = {
        "realize_reference_final",
        "realize_addon_final",
        "evaluate_sensitive_connectome_at_formal_source",
        "evaluate_sensitive_addon_at_formal_final",
    }
    prepared: dict[str, PreparedExposureRecord] = {}
    selected: dict[str, FinalSelectionRecord | SensitiveRecord] = {}
    for row in rows:
        service = str(row.get("service_id", ""))
        if service not in prepare_services | selection_services:
            continue
        if row.get("status") != "completed":
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent task is not completed"
            )
        task_id = str(row.get("task_id", ""))
        endpoint_id = str(row.get("endpoint_id", ""))
        if (
            not task_id.startswith("task_")
            or not endpoint_id.startswith("endpoint_")
        ):
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent task identity differs"
            )
        state = _read_json(
            root / "tasks" / f"{task_id}.json",
            "candidate-parity parent task state",
        )
        if state.get("task_id") != task_id or state.get("status") != "completed":
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent task state differs"
            )
        payload = state.get("result")
        if not isinstance(payload, Mapping):
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent task result is missing"
            )
        try:
            record = ServiceResult.from_dict(payload).decode_record()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent task record is invalid"
            ) from exc
        destination: dict[str, object]
        if service in prepare_services:
            if not isinstance(record, PreparedExposureRecord):
                raise PerformanceMatrixHarnessError(
                    "candidate-parity prepared record type differs"
                )
            destination = prepared
        else:
            if not isinstance(record, (FinalSelectionRecord, SensitiveRecord)):
                raise PerformanceMatrixHarnessError(
                    "candidate-parity selection record type differs"
                )
            destination = selected
        if endpoint_id in destination:
            raise PerformanceMatrixHarnessError(
                "candidate-parity endpoint task is duplicated"
            )
        destination[endpoint_id] = record
    if (
        len(prepared) != 224
        or len(selected) != 224
        or set(prepared) != set(selected)
    ):
        raise PerformanceMatrixHarnessError(
            "candidate-parity configured endpoint closure differs"
        )
    return prepared, selected


def _selected_source_evidence(
    selection: FinalSelectionRecord | SensitiveRecord,
) -> tuple[float, int, object, tuple[ArtifactRef, ...]]:
    """Return the selected threshold, feature axis, and source artifacts."""

    if isinstance(selection, FinalSelectionRecord):
        final = selection.final_model
        if final is None:
            raise PerformanceMatrixHarnessError(
                "candidate-parity final endpoint has no realized model"
            )
        source = final.selected_source
        if source is None and final.selected_branch is not None:
            source = final.selected_branch.source
        if (
            source is None
            or source.selected_tau is None
            or source.selected_coverage is None
        ):
            raise PerformanceMatrixHarnessError(
                "candidate-parity final source lacks a selected threshold"
            )
        return (
            float(source.selected_tau),
            int(source.selected_coverage),
            final.valid_feature_axis.axis,
            tuple(source.artifacts),
        )
    if (
        selection.input_status != "valid"
        or selection.feature_axis is None
    ):
        raise PerformanceMatrixHarnessError(
            "candidate-parity sensitive endpoint is not valid"
        )
    return (
        float(selection.evaluated_tau),
        int(selection.evaluated_coverage),
        selection.feature_axis.axis,
        tuple(selection.artifacts),
    )


def _candidate_parity_plan_document(
    *,
    parent_root: Path,
    benchmark_root: Path,
) -> dict[str, object]:
    """Build the exact 224-row configured parity plan and selected-ID inputs."""

    root = benchmark_root.expanduser().resolve() / "candidate_parity"
    prepared, selections = _completed_parent_records(parent_root)
    parent_id_cache: dict[str, np.ndarray] = {}
    rows: list[dict[str, object]] = []
    for endpoint_id in sorted(prepared):
        exposure = prepared[endpoint_id]
        selection = selections[endpoint_id]
        endpoint = exposure.endpoint
        if getattr(selection, "endpoint", None) != endpoint:
            raise PerformanceMatrixHarnessError(
                "candidate-parity prepared and selected endpoints differ"
            )
        if not isinstance(exposure.exposure, ArtifactRef):
            raise PerformanceMatrixHarnessError(
                "candidate-parity parent exposure is not a concrete artifact"
            )
        tau, coverage, selected_axis, artifacts = _selected_source_evidence(
            selection
        )
        if endpoint.model_family.endswith("voxel"):
            matches = tuple(
                item for item in artifacts if item.kind == "selected_feature_indices"
            )
            if len(matches) != 1:
                raise PerformanceMatrixHarnessError(
                    "candidate-parity voxel source index artifact differs"
                )
            index_path = _artifact_file(
                matches[0],
                label=f"{endpoint_id} selected feature indices",
            )
            indices = np.load(index_path, allow_pickle=False, mmap_mode="r")
            if (
                indices.dtype != np.dtype(np.int64)
                or indices.ndim != 1
                or indices.size != selected_axis.count
                or np.any(indices[1:] <= indices[:-1])
            ):
                raise PerformanceMatrixHarnessError(
                    "candidate-parity voxel selected indices are invalid"
                )
            parent_ids = parent_id_cache.get(exposure.feature_ids.sha256)
            if parent_ids is None:
                parent_id_path = _artifact_file(
                    exposure.feature_ids,
                    label=f"{endpoint_id} parent feature IDs",
                )
                parent_ids = np.load(
                    parent_id_path,
                    allow_pickle=False,
                    mmap_mode="r",
                )
                if (
                    parent_ids.dtype != np.dtype(np.int64)
                    or parent_ids.ndim != 1
                    or parent_ids.size != exposure.feature_axis.count
                    or np.any(parent_ids[1:] <= parent_ids[:-1])
                ):
                    raise PerformanceMatrixHarnessError(
                        "candidate-parity parent feature IDs are invalid"
                    )
                parent_id_cache[exposure.feature_ids.sha256] = parent_ids
            if (
                indices.size < 1
                or indices[0] < 0
                or indices[-1] >= parent_ids.size
            ):
                raise PerformanceMatrixHarnessError(
                    "candidate-parity voxel selected indices are out of bounds"
                )
            selected_path = _atomic_selected_ids(
                root / "selected_feature_ids" / f"{endpoint_id}.npy",
                np.asarray(parent_ids[indices], dtype=np.int64),
            )
            selected_descriptor = {
                "path": str(selected_path),
                "sha256": _sha256_file(selected_path),
                "dtype": "int64",
                "shape": [int(indices.size)],
                "feature_axis_sha256": selected_axis.sha256,
            }
        else:
            matches = tuple(
                item
                for item in artifacts
                if item.kind == "normative_fiber_valid_union_ids"
            )
            if len(matches) != 1:
                raise PerformanceMatrixHarnessError(
                    "candidate-parity fiber valid-union artifact differs"
                )
            selected_descriptor = _candidate_artifact_descriptor(
                matches[0],
                feature_axis_sha256=selected_axis.sha256,
                label=f"{endpoint_id} selected fiber IDs",
            )
        rows.append(
            {
                "row_id": endpoint_id,
                "model_family": endpoint.model_family,
                "tau": tau,
                "coverage": coverage,
                "parent_exposure": _candidate_artifact_descriptor(
                    exposure.exposure,
                    feature_axis_sha256=exposure.feature_axis.sha256,
                    label=f"{endpoint_id} parent exposure",
                ),
                "parent_feature_ids": _candidate_artifact_descriptor(
                    exposure.feature_ids,
                    feature_axis_sha256=exposure.feature_axis.sha256,
                    label=f"{endpoint_id} parent feature IDs",
                ),
                "selected_feature_ids": selected_descriptor,
            }
        )
    return {
        "schema_version": "dual_frequency_candidate_parity_plan_v2",
        "rows": rows,
    }


def _prepare_candidate_parity(
    *,
    parent_root: Path,
    benchmark_root: Path,
) -> dict[str, object]:
    """Generate and execute the immutable 224-row configured parity plan."""

    from my_helper.fiber.pipelines.run_task17_candidate_parity import (
        run as run_candidate_parity,
    )

    root = benchmark_root.expanduser().resolve() / "candidate_parity"
    plan = _candidate_parity_plan_document(
        parent_root=parent_root,
        benchmark_root=benchmark_root,
    )
    plan_path = root / "plan.json"
    report_path = root / "report.json"
    _atomic_json(plan_path, plan)
    run_candidate_parity(plan_path, report_path)
    report = _read_json(report_path, "configured candidate-parity report")
    if (
        report.get("row_count") != 224
        or report.get("candidate_false_negative_count") != 0
        or report.get("full_candidate_mismatch_count") != 0
        or report.get("fold_candidate_mismatch_count") != 0
    ):
        raise PerformanceMatrixHarnessError(
            "configured candidate parity did not pass"
        )
    return {
        "schema_version": "dual_frequency_task17_candidate_parity_binding_v1",
        "plan_path": str(plan_path),
        "plan_sha256": _sha256_file(plan_path),
        "report_path": str(report_path),
        "report_sha256": _sha256_file(report_path),
        "row_count": 224,
    }


def _candidate_parity_binding(
    benchmark_root: Path,
) -> dict[str, object]:
    """Reopen the immutable configured parity plan and passing report."""

    root = benchmark_root.expanduser().resolve()
    parity_root = root / "candidate_parity"
    plan_path = (parity_root / "plan.json").resolve()
    report_path = (parity_root / "report.json").resolve()
    if (
        root not in plan_path.parents
        or root not in report_path.parents
        or not plan_path.is_file()
        or not report_path.is_file()
    ):
        raise PerformanceMatrixHarnessError(
            "configured candidate-parity publication is missing"
        )
    plan = _read_json(plan_path, "configured candidate-parity plan")
    report = _read_json(report_path, "configured candidate-parity report")
    plan_rows = plan.get("rows")
    report_rows = report.get("rows")
    if (
        plan.get("schema_version")
        != "dual_frequency_candidate_parity_plan_v2"
        or not isinstance(plan_rows, list)
        or len(plan_rows) != 224
        or not isinstance(report_rows, list)
        or len(report_rows) != 224
        or report.get("schema_version")
        != "dual_frequency_candidate_parity_v1"
        or Path(str(report.get("plan_path", ""))).resolve() != plan_path
        or report.get("plan_sha256") != _sha256_file(plan_path)
        or report.get("row_count") != 224
        or report.get("candidate_false_negative_count") != 0
        or report.get("full_candidate_mismatch_count") != 0
        or report.get("fold_candidate_mismatch_count") != 0
    ):
        raise PerformanceMatrixHarnessError(
            "configured candidate-parity publication differs"
        )
    plan_ids = tuple(
        str(item.get("row_id", ""))
        for item in plan_rows
        if isinstance(item, Mapping)
    )
    report_ids = tuple(
        str(item.get("row_id", ""))
        for item in report_rows
        if isinstance(item, Mapping)
    )
    if (
        len(plan_ids) != 224
        or len(set(plan_ids)) != 224
        or sorted(plan_ids) != sorted(report_ids)
    ):
        raise PerformanceMatrixHarnessError(
            "configured candidate-parity row closure differs"
        )
    return {
        "schema_version": "dual_frequency_task17_candidate_parity_binding_v1",
        "plan_path": str(plan_path),
        "plan_sha256": _sha256_file(plan_path),
        "report_path": str(report_path),
        "report_sha256": _sha256_file(report_path),
        "row_count": 224,
    }


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
    environment = _safe_token(
        request["conda_environment"],
        "benchmark Conda environment",
    )
    request["conda_environment"] = environment
    if not Path(str(request["working_directory"])).expanduser().resolve().is_dir():
        raise PerformanceMatrixHarnessError(
            "benchmark working directory must be a directory"
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


def _empty_cache_proof(cache_root: Path) -> dict[str, object]:
    """Create or verify one empty row-local scientific cache root."""

    root = cache_root.expanduser().resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise PerformanceMatrixHarnessError(
            "benchmark cold cache root is not empty"
        )
    root.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": "dual_frequency_task17_empty_cache_v1",
        "cache_root": str(root),
        "entry_count": 0,
    }
    return {
        **document,
        "proof_sha256": _canonical_sha256(document),
    }


def _isolated_cache_entry_descriptors(
    cache_root: Path,
) -> tuple[dict[str, str], ...]:
    """Enumerate and fully validate one benchmark-local isolated cache."""

    cache = ContentAddressedCache(cache_root)
    shared = cache.root / "shared_exposure_v2"
    if not shared.is_dir():
        return ()
    descriptors: list[dict[str, str]] = []
    for kind_root in sorted(shared.iterdir(), key=lambda path: path.name):
        if not kind_root.is_dir() or kind_root.is_symlink():
            raise PerformanceMatrixHarnessError(
                "isolated cache contains an invalid kind entry"
            )
        kind = kind_root.name
        for entry_root in sorted(kind_root.iterdir(), key=lambda path: path.name):
            if not entry_root.is_dir() or entry_root.is_symlink():
                raise PerformanceMatrixHarnessError(
                    "isolated cache contains an invalid scientific entry"
                )
            identity = entry_root.name
            entry = cache.resolve_identity(kind, identity)
            if entry is None or entry.path != entry_root.resolve():
                raise PerformanceMatrixHarnessError(
                    "isolated cache entry failed full verification"
                )
            descriptors.append(
                {
                    "kind": kind,
                    "scientific_identity": identity,
                    "manifest_sha256": _sha256_file(entry.manifest_path),
                }
            )
    return tuple(descriptors)


def _publish_warm_seed_manifest(
    path: Path,
    *,
    cache_root: Path,
    slice_id: str,
) -> dict[str, object]:
    """Freeze one nonempty isolated cache as an unmeasured warm seed."""

    entries = _isolated_cache_entry_descriptors(cache_root)
    if not entries:
        raise PerformanceMatrixHarnessError(
            "benchmark warm seed cache contains no entries"
        )
    document = {
        "schema_version": "dual_frequency_task17_warm_seed_v1",
        "slice_id": str(slice_id),
        "cache_root": str(cache_root.expanduser().resolve()),
        "entries": list(entries),
    }
    document["seed_sha256"] = _canonical_sha256(document)
    _atomic_json(path.expanduser().resolve(), document)
    return document


def _copy_warm_seed(
    manifest_path: Path,
    *,
    destination_cache_root: Path,
    expected_slice_id: str,
) -> dict[str, object]:
    """Revalidate and copy one exact warm seed into a measured row cache."""

    manifest = _read_json(
        manifest_path.expanduser().resolve(),
        "benchmark warm seed manifest",
    )
    expected_fields = {
        "schema_version",
        "slice_id",
        "cache_root",
        "entries",
        "seed_sha256",
    }
    unsigned = {
        key: value for key, value in manifest.items() if key != "seed_sha256"
    }
    if (
        set(manifest) != expected_fields
        or manifest.get("schema_version")
        != "dual_frequency_task17_warm_seed_v1"
        or manifest.get("slice_id") != expected_slice_id
        or manifest.get("seed_sha256") != _canonical_sha256(unsigned)
        or not isinstance(manifest.get("entries"), list)
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark warm seed manifest identity differs"
        )
    source_root = Path(str(manifest["cache_root"])).expanduser().resolve()
    current = _isolated_cache_entry_descriptors(source_root)
    if list(current) != manifest["entries"]:
        raise PerformanceMatrixHarnessError(
            "benchmark warm seed cache closure differs"
        )
    return _copy_verified_cache_entries(
        source_cache_root=source_root,
        destination_cache_root=destination_cache_root,
        entries=current,
    )


def _prepare_row_cache_state(
    *,
    resolved: Mapping[str, object],
    row: Mapping[str, object],
    benchmark_root: Path,
    attempt_root: Path,
) -> dict[str, object]:
    """Prepare the exact cold, warm, injected, or real-cache-hit row state."""

    cache_state = row.get("cache_state")
    solver_mode = row.get("solver_mode")
    slice_id = row.get("slice_id")
    if (
        cache_state not in {"cold", "warm"}
        or solver_mode
        not in {"none", "injected", "real_cache_hit", "real_solver"}
        or type(slice_id) is not str
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark row cache condition is invalid"
        )
    accepted = resolved.get("accepted_oss_cache")
    if not isinstance(accepted, Mapping):
        raise PerformanceMatrixHarnessError(
            "resolved accepted OSS cache closure is missing"
        )
    root = attempt_root.expanduser().resolve()
    scientific_cache_root = root / "scientific_cache"
    fixture: dict[str, object] | None = None
    if solver_mode == "injected":
        fixture = _prepare_injected_oss_fixture(
            accepted_closure=accepted,
            destination_cache_root=root / "injected_fixture_cache",
        )
    if cache_state == "cold":
        if solver_mode == "real_cache_hit":
            raise PerformanceMatrixHarnessError(
                "real-cache-hit benchmark rows must be warm"
            )
        cache_evidence = _empty_cache_proof(scientific_cache_root)
        cache_source = "empty"
    elif solver_mode == "real_cache_hit":
        descriptors = _accepted_oss_cache_entry_descriptors(accepted)
        cache_evidence = _copy_verified_cache_entries(
            source_cache_root=Path(str(accepted["cache_root"])),
            destination_cache_root=scientific_cache_root,
            entries=descriptors,
        )
        cache_source = "accepted_independent_oss"
    else:
        seed_manifest = (
            benchmark_root.expanduser().resolve()
            / "warm_seeds"
            / slice_id
            / "warm_seed.json"
        )
        cache_evidence = _copy_warm_seed(
            seed_manifest,
            destination_cache_root=scientific_cache_root,
            expected_slice_id=slice_id,
        )
        cache_source = "unmeasured_warm_seed"
    document = {
        "schema_version": "dual_frequency_task17_row_cache_state_v1",
        "cache_state": cache_state,
        "solver_mode": solver_mode,
        "slice_id": slice_id,
        "scientific_cache_root": str(scientific_cache_root),
        "cache_source": cache_source,
        "cache_evidence": cache_evidence,
        "injected_fixture": fixture,
    }
    return {
        **document,
        "state_sha256": _canonical_sha256(document),
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


def _imported_checkpoint_states(
    descriptor: Mapping[str, object],
    *,
    parent_root: Path,
    oss_root: Path,
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Load and decode the exact parent/OSS checkpoint roots for one slice."""

    selected = descriptor.get("selected_task_ids")
    parent_ids = descriptor.get("imported_parent_task_ids")
    oss_ids = descriptor.get("imported_oss_task_ids")
    if not all(
        isinstance(value, list)
        for value in (selected, parent_ids, oss_ids)
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark slice import closure is invalid"
        )
    selected_set = {str(value) for value in selected}
    plan_payload = descriptor.get("execution_plan")
    plan = _execution_plan_from_payload(plan_payload)
    plan_index = {task.task_id: task for task in plan.tasks}
    sources = (
        ("parent", parent_root.expanduser().resolve(), parent_ids),
        ("oss", oss_root.expanduser().resolve(), oss_ids),
    )
    imported: list[dict[str, object]] = []
    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for role, root, task_ids in sources:
        for task_id in sorted(str(value) for value in task_ids):
            if task_id in selected_set or task_id in seen:
                raise PerformanceMatrixHarnessError(
                    "benchmark imported and selected task closures overlap"
                )
            seen.add(task_id)
            path = root / "tasks" / f"{task_id}.json"
            state = _read_json(path, f"imported {role} task state")
            result_payload = state.get("result")
            if (
                state.get("task_id") != task_id
                or state.get("status") != "completed"
                or not isinstance(result_payload, Mapping)
            ):
                raise PerformanceMatrixHarnessError(
                    "benchmark imported task is not a complete checkpoint"
                )
            try:
                result = ServiceResult.from_dict(result_payload)
                result.decode_record()
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                raise PerformanceMatrixHarnessError(
                    "benchmark imported task record is invalid"
                ) from exc
            expected_task = plan_index.get(task_id)
            if (
                expected_task is None
                or result.output_record_type
                != expected_task.output_record_type
            ):
                raise PerformanceMatrixHarnessError(
                    "benchmark imported task record type differs from its plan"
                )
            imported.append(state)
            evidence.append(
                {
                    "source": role,
                    "task_id": task_id,
                    "sha256": _sha256_file(path),
                }
            )
    expected = selected_set | seen
    if {task.task_id for task in plan.tasks} != expected:
        raise PerformanceMatrixHarnessError(
            "benchmark imported task closure differs from the executable plan"
        )
    closure = {
        "schema_version": (
            "dual_frequency_task17_imported_checkpoint_closure_v1"
        ),
        "entries": evidence,
    }
    return tuple(imported), {
        **closure,
        "closure_sha256": _canonical_sha256(closure),
    }


def _install_imported_checkpoint_states(
    store: _TaskStateStore,
    states: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Install exact completed checkpoints and verify their persisted form."""

    installed: list[str] = []
    for raw in states:
        state = dict(raw)
        task_id = state.get("task_id")
        if (
            type(task_id) is not str
            or task_id in installed
            or state.get("status") != "completed"
            or not isinstance(state.get("result"), Mapping)
        ):
            raise PerformanceMatrixHarnessError(
                "imported checkpoint installation input is invalid"
            )
        payload = {key: value for key, value in state.items() if key != "task_id"}
        store.write_task_state(task_id, payload)
        reopened = store.read_task_state(task_id)
        if reopened != state:
            raise PerformanceMatrixHarnessError(
                "imported checkpoint changed during row-local installation"
            )
        installed.append(task_id)
    return tuple(installed)


def _prepare_row_attempt(
    *,
    resolved: Mapping[str, object],
    row: Mapping[str, object],
    benchmark_root: Path,
) -> tuple[Path, dict[str, object]]:
    """Commit all immutable row inputs before a runner child starts."""

    row_id = row.get("row_id")
    if type(row_id) is not str or row.get("planned_status") != "planned":
        raise PerformanceMatrixHarnessError(
            "only planned benchmark rows can create execution attempts"
        )
    root = benchmark_root.expanduser().resolve()
    row_root = root / "rows" / row_id
    contract = _row_contract(resolved, row)
    _contract_path, contract_sha256 = _ensure_row_contract(
        row_root,
        contract,
    )
    if _validate_row_result(row_root, contract_sha256) is not None:
        raise PerformanceMatrixHarnessError(
            "terminal benchmark row cannot create another attempt"
        )
    descriptor, _plan = _resolved_slice(resolved, row)
    parent = resolved.get("accepted_parent")
    oss = resolved.get("accepted_independent_oss")
    if not isinstance(parent, Mapping) or not isinstance(oss, Mapping):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark accepted roots are invalid"
        )
    states, checkpoint_closure = _imported_checkpoint_states(
        descriptor,
        parent_root=Path(str(parent.get("root", ""))),
        oss_root=Path(str(oss.get("root", ""))),
    )
    attempt_root, attempt_number = _next_attempt(row_root)
    checkpoint_document = {
        "schema_version": (
            "dual_frequency_task17_attempt_checkpoint_inputs_v1"
        ),
        "source_closure": checkpoint_closure,
        "task_states": list(states),
    }
    checkpoint_document["document_sha256"] = _canonical_sha256(
        checkpoint_document
    )
    checkpoint_path = attempt_root / "checkpoint_closure.json"
    _atomic_json(checkpoint_path, checkpoint_document)
    cache_document = _prepare_row_cache_state(
        resolved=resolved,
        row=row,
        benchmark_root=root,
        attempt_root=attempt_root,
    )
    cache_path = attempt_root / "row_cache_state.json"
    _atomic_json(cache_path, cache_document)
    attempt_plan = {
        "schema_version": "dual_frequency_task17_row_attempt_v1",
        "row_id": row_id,
        "attempt": attempt_number,
        "row_contract_sha256": contract_sha256,
        "slice_id": row["slice_id"],
        "segment_plan_sha256": descriptor["plan_hash"],
        "selected_task_ids": descriptor["selected_task_ids"],
        "imported_parent_task_ids": descriptor[
            "imported_parent_task_ids"
        ],
        "imported_oss_task_ids": descriptor["imported_oss_task_ids"],
        "checkpoint_closure": {
            "relative_path": checkpoint_path.relative_to(attempt_root).as_posix(),
            "sha256": _sha256_file(checkpoint_path),
        },
        "row_cache_state": {
            "relative_path": cache_path.relative_to(attempt_root).as_posix(),
            "sha256": _sha256_file(cache_path),
        },
    }
    attempt_plan["attempt_plan_sha256"] = _canonical_sha256(attempt_plan)
    _atomic_json(attempt_root / "attempt_plan.json", attempt_plan)
    return attempt_root, attempt_plan


def _open_row_attempt_inputs(
    *,
    resolved: Mapping[str, object],
    row: Mapping[str, object],
    benchmark_root: Path,
    attempt_root: Path,
) -> tuple[
    dict[str, object],
    tuple[dict[str, object], ...],
    dict[str, object],
    dict[str, object],
    ExecutionPlan,
]:
    """Revalidate one committed attempt before opening its runner RunStore."""

    row_id = row.get("row_id")
    if type(row_id) is not str:
        raise PerformanceMatrixHarnessError(
            "benchmark attempt row identity is invalid"
        )
    expected_parent = (
        benchmark_root.expanduser().resolve()
        / "rows"
        / row_id
        / "attempts"
    )
    root = attempt_root.expanduser().resolve()
    if root.parent != expected_parent or root.is_symlink():
        raise PerformanceMatrixHarnessError(
            "benchmark attempt path differs from its row"
        )
    plan_path = root / "attempt_plan.json"
    attempt_plan = _read_json(plan_path, "benchmark attempt plan")
    expected_plan_fields = {
        "schema_version",
        "row_id",
        "attempt",
        "row_contract_sha256",
        "slice_id",
        "segment_plan_sha256",
        "selected_task_ids",
        "imported_parent_task_ids",
        "imported_oss_task_ids",
        "checkpoint_closure",
        "row_cache_state",
        "attempt_plan_sha256",
    }
    unsigned_plan = {
        key: value
        for key, value in attempt_plan.items()
        if key != "attempt_plan_sha256"
    }
    descriptor, execution_plan = _resolved_slice(resolved, row)
    contract_path = root.parents[1] / "row_contract.json"
    if (
        set(attempt_plan) != expected_plan_fields
        or attempt_plan.get("schema_version")
        != "dual_frequency_task17_row_attempt_v1"
        or attempt_plan.get("row_id") != row_id
        or type(attempt_plan.get("attempt")) is not int
        or attempt_plan["attempt"] < 1
        or root.name != f"attempt_{attempt_plan['attempt']:04d}"
        or attempt_plan.get("attempt_plan_sha256")
        != _canonical_sha256(unsigned_plan)
        or not contract_path.is_file()
        or attempt_plan.get("row_contract_sha256")
        != _sha256_file(contract_path)
        or attempt_plan.get("slice_id") != descriptor["slice_id"]
        or attempt_plan.get("segment_plan_sha256")
        != descriptor["plan_hash"]
        or attempt_plan.get("selected_task_ids")
        != descriptor["selected_task_ids"]
        or attempt_plan.get("imported_parent_task_ids")
        != descriptor["imported_parent_task_ids"]
        or attempt_plan.get("imported_oss_task_ids")
        != descriptor["imported_oss_task_ids"]
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark attempt plan identity differs"
        )

    def referenced_document(field: str, label: str) -> dict[str, object]:
        raw = attempt_plan.get(field)
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"relative_path", "sha256"}
        ):
            raise PerformanceMatrixHarnessError(
                f"{label} reference is invalid"
            )
        path = (root / str(raw["relative_path"])).resolve()
        if (
            root not in path.parents
            or not path.is_file()
            or _sha256_file(path) != raw["sha256"]
        ):
            raise PerformanceMatrixHarnessError(
                f"{label} reference SHA differs"
            )
        return _read_json(path, label)

    checkpoint = referenced_document(
        "checkpoint_closure",
        "benchmark checkpoint inputs",
    )
    if (
        set(checkpoint)
        != {
            "schema_version",
            "source_closure",
            "task_states",
            "document_sha256",
        }
        or checkpoint.get("schema_version")
        != "dual_frequency_task17_attempt_checkpoint_inputs_v1"
        or checkpoint.get("document_sha256")
        != _canonical_sha256(
            {
                key: value
                for key, value in checkpoint.items()
                if key != "document_sha256"
            }
        )
        or not isinstance(checkpoint.get("task_states"), list)
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark checkpoint input document differs"
        )
    states = tuple(dict(value) for value in checkpoint["task_states"])
    planned_types = {
        task.task_id: task.output_record_type
        for task in execution_plan.tasks
        if task.checkpoint_only
    }
    if {str(state.get("task_id")) for state in states} != set(planned_types):
        raise PerformanceMatrixHarnessError(
            "benchmark checkpoint task closure differs"
        )
    for state in states:
        result_payload = state.get("result")
        if (
            state.get("status") != "completed"
            or not isinstance(result_payload, Mapping)
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark checkpoint task state differs"
            )
        result = ServiceResult.from_dict(result_payload)
        result.decode_record()
        if result.output_record_type != planned_types[state["task_id"]]:
            raise PerformanceMatrixHarnessError(
                "benchmark checkpoint task result type differs"
            )

    cache_state = referenced_document(
        "row_cache_state",
        "benchmark row cache state",
    )
    if (
        set(cache_state)
        != {
            "schema_version",
            "cache_state",
            "solver_mode",
            "slice_id",
            "scientific_cache_root",
            "cache_source",
            "cache_evidence",
            "injected_fixture",
            "state_sha256",
        }
        or cache_state.get("schema_version")
        != "dual_frequency_task17_row_cache_state_v1"
        or cache_state.get("cache_state") != row.get("cache_state")
        or cache_state.get("solver_mode") != row.get("solver_mode")
        or cache_state.get("slice_id") != row.get("slice_id")
        or cache_state.get("state_sha256")
        != _canonical_sha256(
            {
                key: value
                for key, value in cache_state.items()
                if key != "state_sha256"
            }
        )
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark row cache state identity differs"
        )
    cache_root = Path(
        str(cache_state.get("scientific_cache_root", ""))
    ).expanduser().resolve()
    if root not in cache_root.parents or not cache_root.is_dir():
        raise PerformanceMatrixHarnessError(
            "benchmark row scientific cache path differs"
        )
    actual_entries = _isolated_cache_entry_descriptors(cache_root)
    if cache_state.get("cache_source") == "empty":
        expected_entries: list[dict[str, str]] = []
    else:
        cache_evidence = cache_state.get("cache_evidence")
        if (
            not isinstance(cache_evidence, Mapping)
            or not isinstance(cache_evidence.get("entries"), list)
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark row cache evidence is invalid"
            )
        expected_entries = cache_evidence["entries"]
    if list(actual_entries) != expected_entries:
        raise PerformanceMatrixHarnessError(
            "benchmark row cache entry closure differs"
        )
    fixture = cache_state.get("injected_fixture")
    if row.get("solver_mode") == "injected":
        accepted = resolved.get("accepted_oss_cache")
        expected_closure_sha = (
            accepted.get("closure_sha256")
            if isinstance(accepted, Mapping)
            else None
        )
        expected_fixture_fields = {
            "schema_version",
            "accepted_closure_sha256",
            "fixture_cache_root",
            "permitted_row_identities",
            "seed_sha256",
            "fixture_sha256",
        }
        if (
            not isinstance(fixture, Mapping)
            or set(fixture) != expected_fixture_fields
            or fixture.get("schema_version")
            != "dual_frequency_task17_injected_oss_fixture_v1"
            or fixture.get("accepted_closure_sha256")
            != expected_closure_sha
            or fixture.get("fixture_sha256")
            != _canonical_sha256(
                {
                    key: value
                    for key, value in fixture.items()
                    if key != "fixture_sha256"
                }
            )
            or not isinstance(fixture.get("permitted_row_identities"), list)
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark injected OSS fixture identity differs"
            )
        fixture_root = Path(
            str(fixture["fixture_cache_root"])
        ).expanduser().resolve()
        if root not in fixture_root.parents:
            raise PerformanceMatrixHarnessError(
                "benchmark injected OSS fixture path differs"
            )
        fixture_entries = _isolated_cache_entry_descriptors(fixture_root)
        if (
            any(item["kind"] != "oss_rows" for item in fixture_entries)
            or [item["scientific_identity"] for item in fixture_entries]
            != fixture["permitted_row_identities"]
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark injected OSS fixture row closure differs"
            )
    elif fixture is not None:
        raise PerformanceMatrixHarnessError(
            "non-injected benchmark row contains an OSS fixture"
        )
    return attempt_plan, states, cache_state, descriptor, execution_plan


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
        "execution_environment": {
            "conda_environment": request["conda_environment"],
            "working_directory": str(
                Path(str(request["working_directory"]))
                .expanduser()
                .resolve()
            ),
        },
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
        expected_marker = {
            **marker,
            "candidate_parity": _candidate_parity_binding(root),
        }
        stored_plan = _read_json(
            root / "benchmark_plan_resolved.json",
            "resolved benchmark plan",
        )
        stored_marker = _read_json(
            marker_path,
            "benchmark root marker",
        )
        if stored_plan != resolved or stored_marker != expected_marker:
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
    parent = resolved.get("accepted_parent")
    if not isinstance(parent, Mapping):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark parent binding is invalid"
        )
    candidate_parity = _prepare_candidate_parity(
        parent_root=Path(str(parent.get("root", ""))),
        benchmark_root=root,
    )
    if candidate_parity != _candidate_parity_binding(root):
        raise PerformanceMatrixHarnessError(
            "configured candidate-parity binding differs after publication"
        )
    committed_marker = {
        **marker,
        "candidate_parity": candidate_parity,
    }
    _atomic_json(marker_path, committed_marker)
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
        "candidate_parity",
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
        or marker.get("candidate_parity")
        != _candidate_parity_binding(root)
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


def _validate_child_execution_environment(
    resolved: Mapping[str, object],
    *,
    working_directory: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Require the child process to match its immutable execution environment."""

    raw = resolved.get("execution_environment")
    if (
        not isinstance(raw, Mapping)
        or set(raw) != {"conda_environment", "working_directory"}
    ):
        raise PerformanceMatrixHarnessError(
            "resolved child execution environment is invalid"
        )
    conda_environment = _safe_token(
        raw["conda_environment"],
        "resolved Conda environment",
    )
    expected_working_directory = Path(
        str(raw["working_directory"])
    ).expanduser().resolve()
    actual_working_directory = (
        Path.cwd().resolve()
        if working_directory is None
        else working_directory.expanduser().resolve()
    )
    values = os.environ if environment is None else environment
    active_environment = str(values.get("CONDA_DEFAULT_ENV", "")).strip()
    if not active_environment:
        prefix = str(values.get("CONDA_PREFIX", "")).strip()
        active_environment = Path(prefix).name if prefix else ""
    if (
        actual_working_directory != expected_working_directory
        or active_environment != conda_environment
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark child execution environment differs"
        )
    return {
        "conda_environment": conda_environment,
        "working_directory": str(expected_working_directory),
    }


def _workflow_bundle_from_resolved(
    resolved: Mapping[str, object],
) -> tuple[WorkflowService, object]:
    """Recompile the ordinary production workflow from bound source inputs."""

    sources = resolved.get("input_sources")
    parent = resolved.get("accepted_parent")
    expected_roles = {
        "study_base",
        "direct_voxel_model",
        "normative_fiber_model",
        "workflow_profile",
    }
    if (
        not isinstance(sources, Mapping)
        or set(sources) != expected_roles
        or not isinstance(parent, Mapping)
    ):
        raise PerformanceMatrixHarnessError(
            "resolved workflow source closure is invalid"
        )
    request: dict[str, object] = {}
    for role in sorted(expected_roles):
        raw = sources[role]
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"path", "sha256"}
        ):
            raise PerformanceMatrixHarnessError(
                "resolved workflow source descriptor is invalid"
            )
        path = Path(str(raw["path"])).expanduser().resolve()
        if not path.is_file() or _sha256_file(path) != raw["sha256"]:
            raise PerformanceMatrixHarnessError(
                "resolved workflow source SHA differs"
            )
        request[role] = path
    parent_root = Path(str(parent.get("root", ""))).expanduser().resolve()
    snapshot = _resolved_snapshot(parent_root)
    workflow_request = _workflow_request(request, snapshot)
    service = WorkflowService()
    try:
        bundle = service.plan(workflow_request)
    except (ApplicationError, OSError, RuntimeError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            "benchmark child cannot compile the production workflow"
        ) from exc
    if (
        bundle.validated.configuration.scientific_configuration_hash
        != resolved.get("scientific_configuration_hash")
        or plan_hash(bundle.plan) != resolved.get("full_plan_hash")
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark child production workflow identity differs"
        )
    return service, bundle


def _benchmark_resolved_snapshot(
    service: WorkflowService,
    validated: object,
    *,
    workers: int,
) -> dict[str, object]:
    """Record the actual row worker ceiling in the isolated run snapshot."""

    snapshot = service._resolved_snapshot(validated)
    execution = snapshot.get("execution")
    if (
        not isinstance(execution, Mapping)
        or workers not in _WORKERS
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark resolved execution snapshot differs"
        )
    snapshot["execution"] = {
        **dict(execution),
        "workers": workers,
    }
    return snapshot


def _warm_seed_rows(
    resolved: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    """Select one canonical unmeasured producer row for every warm seed."""

    raw_rows = resolved.get("rows")
    if not isinstance(raw_rows, list):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark rows are missing"
        )
    selected: dict[str, dict[str, object]] = {}
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise PerformanceMatrixHarnessError(
                "resolved benchmark row is invalid"
            )
        if (
            raw.get("cache_state") != "warm"
            or raw.get("solver_mode") == "real_cache_hit"
        ):
            continue
        slice_id = str(raw.get("slice_id", ""))
        if len(slice_id) != 64:
            raise PerformanceMatrixHarnessError(
                "warm-seed slice identity differs"
            )
        current = selected.get(slice_id)
        candidate = dict(raw)
        if current is None or (
            int(candidate["workers"]),
            str(candidate["row_id"]),
        ) < (
            int(current["workers"]),
            str(current["row_id"]),
        ):
            selected[slice_id] = candidate
    rows = tuple(selected[key] for key in sorted(selected))
    if (
        len(rows) != 8
        or sum(row.get("solver_mode") == "injected" for row in rows) != 1
        or any(row.get("planned_status") != "planned" for row in rows)
    ):
        raise PerformanceMatrixHarnessError(
            "warm-seed row closure differs"
        )
    return rows


def _execute_unmeasured_warm_seed(
    *,
    resolved: Mapping[str, object],
    row: Mapping[str, object],
    benchmark_root: Path,
) -> dict[str, object]:
    """Execute one ordinary slice in an empty cache and freeze its seed."""

    slice_id = str(row.get("slice_id", ""))
    if (
        row.get("cache_state") != "warm"
        or row.get("solver_mode") not in {"none", "injected"}
        or len(slice_id) != 64
    ):
        raise PerformanceMatrixHarnessError(
            "unmeasured warm-seed row identity differs"
        )
    if row.get("solver_mode") == "injected":
        raise PerformanceMatrixHarnessError(
            "spawned injected OSS warm-seed mode is not installed"
        )
    root = (
        benchmark_root.expanduser().resolve()
        / "warm_seeds"
        / slice_id
    )
    manifest_path = root / "warm_seed.json"
    if manifest_path.is_file():
        manifest = _read_json(
            manifest_path,
            "benchmark warm seed manifest",
        )
        cache_root = Path(
            str(manifest.get("cache_root", ""))
        ).expanduser().resolve()
        if root not in cache_root.parents:
            raise PerformanceMatrixHarnessError(
                "benchmark warm seed cache path differs"
            )
        return _publish_warm_seed_manifest(
            manifest_path,
            cache_root=cache_root,
            slice_id=slice_id,
        )
    descriptor, execution_plan = _resolved_slice(resolved, row)
    parent = resolved.get("accepted_parent")
    oss = resolved.get("accepted_independent_oss")
    if not isinstance(parent, Mapping) or not isinstance(oss, Mapping):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark accepted roots are invalid"
        )
    parent_root = Path(str(parent.get("root", ""))).expanduser().resolve()
    oss_root = Path(str(oss.get("root", ""))).expanduser().resolve()
    states, checkpoint_closure = _imported_checkpoint_states(
        descriptor,
        parent_root=parent_root,
        oss_root=oss_root,
    )
    attempt_root, attempt_number = _next_attempt(root)
    cache_root = attempt_root / "scientific_cache"
    empty_cache = _empty_cache_proof(cache_root)
    seed_plan = {
        "schema_version": "dual_frequency_task17_warm_seed_attempt_v1",
        "slice_id": slice_id,
        "attempt": attempt_number,
        "resolved_plan_sha256": _canonical_sha256(resolved),
        "segment_plan_sha256": descriptor["plan_hash"],
        "selected_task_ids": descriptor["selected_task_ids"],
        "imported_parent_task_ids": descriptor[
            "imported_parent_task_ids"
        ],
        "imported_oss_task_ids": descriptor["imported_oss_task_ids"],
        "checkpoint_closure": checkpoint_closure,
        "empty_cache_proof": empty_cache,
        "workers": int(row["workers"]),
    }
    seed_plan["seed_plan_sha256"] = _canonical_sha256(seed_plan)
    _atomic_json(attempt_root / "seed_attempt_plan.json", seed_plan)
    service, bundle = _workflow_bundle_from_resolved(resolved)
    validated = bundle.validated
    configuration = validated.configuration
    output_root = configuration.direct_voxel.output.root.expanduser().resolve()
    run_root = attempt_root / "run"
    run_id = (
        f"task17-warm-seed-{slice_id[:20]}-"
        f"attempt-{attempt_number:04d}"
    )
    identity = RunIdentity(
        study_id=validated.study.study_id,
        run_id=run_id,
        study_base_sha256=validated.study.source_sha256,
        code_identity=service._code_identity(),
        configuration_hash=configuration.configuration_hash,
        scientific_configuration_hash=(
            configuration.scientific_configuration_hash
        ),
        plan_hash=plan_hash(execution_plan),
        parent_run_id=str(parent["run_id"]),
    )
    store = RunStore.open(
        run_root,
        identity,
        resolved_configuration=_benchmark_resolved_snapshot(
            service,
            validated,
            workers=int(row["workers"]),
        ),
        configuration_sources=service._configuration_sources(validated),
        allowed_artifact_roots=(
            parent_root,
            oss_root,
            output_root,
            cache_root,
        ),
        resume=False,
    )
    store.annotate_manifest(
        {
            "run_type": "task17_performance_warm_seed",
            "benchmark_slice_id": slice_id,
            "benchmark_seed_attempt": attempt_number,
            "resource_settings": {"workers": int(row["workers"])},
        }
    )
    service._publish_input_bundle(store.root, validated)
    installed = _install_imported_checkpoint_states(store, states)
    if set(installed) != {
        *descriptor["imported_parent_task_ids"],
        *descriptor["imported_oss_task_ids"],
    }:
        raise PerformanceMatrixHarnessError(
            "warm-seed installed checkpoint closure differs"
        )
    artifact_roots = (
        store.root,
        parent_root,
        oss_root,
        output_root,
        cache_root,
    )
    artifact_store = ArtifactStore(artifact_roots)
    scientific_cache = ContentAddressedCache(cache_root)
    provider = service._default_provider(
        validated,
        work_root=store.root / "runtime_work",
        artifact_store=artifact_store,
        scientific_cache=scientific_cache,
    )
    endpoint_facts = {
        endpoint.endpoint_id: {
            "catalog_data_available": endpoint.status
            == CatalogStatus.DATA_AVAILABLE,
        }
        for endpoint in validated.catalog
    }
    context = ExecutionContext(
        run_store=store,
        registry=service._default_registry(),
        provider=provider,
        endpoint_facts=endpoint_facts,
        allow_expensive_producers=True,
        continue_on_endpoint_failure=(
            configuration.workflow.execution.continue_on_endpoint_failure
        ),
        workers=int(row["workers"]),
        artifact_store=artifact_store,
        scientific_cache=scientific_cache,
        resume=True,
        spawn_worker_spec=SpawnWorkerSpec(
            study=validated.study,
            configuration=configuration,
            catalog=validated.catalog,
            work_root=store.root / "runtime_work",
            artifact_roots=artifact_roots,
            cache_root=cache_root,
        ),
    )
    result = None
    failure: BaseException | None = None
    final_status = "failed"
    try:
        result = execute_plan(execution_plan, context)
        final_status = "completed" if result.exit_code == 0 else "failed"
    except BaseException as exc:
        failure = exc
    try:
        store.finalize(final_status)
    except BaseException as exc:
        if failure is None:
            failure = exc
    if failure is not None:
        raise failure
    if result is None or result.exit_code != 0:
        raise PerformanceMatrixHarnessError(
            "benchmark warm-seed execution did not complete"
        )
    outcomes = {outcome.task_id: outcome for outcome in result.outcomes}
    selected_ids = tuple(str(value) for value in descriptor["selected_task_ids"])
    if any(
        task_id not in outcomes
        or outcomes[task_id].status != "completed"
        or outcomes[task_id].reason == "restored_completed_result"
        for task_id in selected_ids
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark warm-seed selected task closure differs"
        )
    execution_result = {
        "schema_version": "dual_frequency_task17_warm_seed_result_v1",
        "slice_id": slice_id,
        "attempt": attempt_number,
        "run_root": str(store.root),
        "run_manifest_sha256": _sha256_file(
            store.root / "run_manifest.json"
        ),
        "selected_task_ids": list(selected_ids),
        "restored_task_ids": sorted(installed),
        "numerical_identity_sha256": _selected_numerical_identity(
            store,
            selected_ids,
        ),
    }
    execution_result["result_sha256"] = _canonical_sha256(execution_result)
    _atomic_json(
        attempt_root / "seed_attempt_result.json",
        execution_result,
    )
    return _publish_warm_seed_manifest(
        manifest_path,
        cache_root=cache_root,
        slice_id=slice_id,
    )


def _execute_row_child(
    *,
    request_path: Path,
    benchmark_root: Path,
    row_id: str,
    attempt_root: Path,
) -> dict[str, object]:
    """Execute one already-prepared row after the parent measurement handshake."""

    resolved, _marker = _open_prepared_benchmark(
        request_path,
        benchmark_root,
    )
    _validate_child_execution_environment(resolved)
    row = _resolved_row(resolved, row_id)
    (
        attempt_plan,
        checkpoint_states,
        cache_state,
        descriptor,
        execution_plan,
    ) = _open_row_attempt_inputs(
        resolved=resolved,
        row=row,
        benchmark_root=benchmark_root,
        attempt_root=attempt_root,
    )
    if row.get("solver_mode") == "injected":
        raise PerformanceMatrixHarnessError(
            "spawned injected OSS benchmark mode is not installed"
        )
    service, bundle = _workflow_bundle_from_resolved(resolved)
    validated = bundle.validated
    configuration = validated.configuration
    parent = resolved["accepted_parent"]
    oss = resolved["accepted_independent_oss"]
    parent_root = Path(str(parent["root"])).expanduser().resolve()
    oss_root = Path(str(oss["root"])).expanduser().resolve()
    cache_root = Path(
        str(cache_state["scientific_cache_root"])
    ).expanduser().resolve()
    output_root = configuration.direct_voxel.output.root.expanduser().resolve()
    run_root = attempt_root.expanduser().resolve() / "run"
    run_id = (
        f"task17-perf-{row_id.removeprefix('row_')}-"
        f"attempt-{int(attempt_plan['attempt']):04d}"
    )
    identity = RunIdentity(
        study_id=validated.study.study_id,
        run_id=run_id,
        study_base_sha256=validated.study.source_sha256,
        code_identity=service._code_identity(),
        configuration_hash=configuration.configuration_hash,
        scientific_configuration_hash=(
            configuration.scientific_configuration_hash
        ),
        plan_hash=plan_hash(execution_plan),
        parent_run_id=str(parent["run_id"]),
    )
    snapshot = _benchmark_resolved_snapshot(
        service,
        validated,
        workers=int(row["workers"]),
    )
    sources = service._configuration_sources(validated)
    store = RunStore.open(
        run_root,
        identity,
        resolved_configuration=snapshot,
        configuration_sources=sources,
        allowed_artifact_roots=(
            parent_root,
            oss_root,
            output_root,
            cache_root,
        ),
        resume=False,
    )
    store.annotate_manifest(
        {
            "run_type": "task17_performance_benchmark_row",
            "benchmark_row_id": row_id,
            "benchmark_attempt": int(attempt_plan["attempt"]),
            "benchmark_slice_id": descriptor["slice_id"],
            "resource_settings": {"workers": int(row["workers"])},
        }
    )
    service._publish_input_bundle(store.root, validated)
    installed = _install_imported_checkpoint_states(
        store,
        checkpoint_states,
    )
    if set(installed) != {
        *descriptor["imported_parent_task_ids"],
        *descriptor["imported_oss_task_ids"],
    }:
        raise PerformanceMatrixHarnessError(
            "row-local installed checkpoint closure differs"
        )
    artifact_roots = (
        store.root,
        parent_root,
        oss_root,
        output_root,
        cache_root,
    )
    artifact_store = ArtifactStore(artifact_roots)
    scientific_cache = ContentAddressedCache(cache_root)
    provider = service._default_provider(
        validated,
        work_root=store.root / "runtime_work",
        artifact_store=artifact_store,
        scientific_cache=scientific_cache,
    )
    endpoint_facts = {
        endpoint.endpoint_id: {
            "catalog_data_available": endpoint.status
            == CatalogStatus.DATA_AVAILABLE,
        }
        for endpoint in validated.catalog
    }
    context = ExecutionContext(
        run_store=store,
        registry=service._default_registry(),
        provider=provider,
        endpoint_facts=endpoint_facts,
        allow_expensive_producers=(
            row.get("solver_mode") != "real_cache_hit"
        ),
        continue_on_endpoint_failure=(
            configuration.workflow.execution.continue_on_endpoint_failure
        ),
        workers=int(row["workers"]),
        artifact_store=artifact_store,
        scientific_cache=scientific_cache,
        resume=True,
        spawn_worker_spec=SpawnWorkerSpec(
            study=validated.study,
            configuration=configuration,
            catalog=validated.catalog,
            work_root=store.root / "runtime_work",
            artifact_roots=artifact_roots,
            cache_root=cache_root,
        ),
    )
    ready = {
        "schema_version": _RUNNER_READY_SCHEMA,
        "row_id": row_id,
        "runner_pid": os.getpid(),
        "run_root": str(store.root),
        "segment_plan_sha256": descriptor["plan_hash"],
        "imported_parent_task_ids": descriptor["imported_parent_task_ids"],
        "imported_oss_task_ids": descriptor["imported_oss_task_ids"],
    }
    _atomic_json(
        attempt_root.expanduser().resolve() / "runner_ready.json",
        ready,
    )
    _wait_for_measurement_start(
        attempt_root.expanduser().resolve() / "measurement_start.json",
        row_id=row_id,
        runner_pid=os.getpid(),
    )
    result = None
    failure: BaseException | None = None
    final_status = "failed"
    try:
        result = execute_plan(execution_plan, context)
        final_status = "completed" if result.exit_code == 0 else "failed"
    except BaseException as exc:
        failure = exc
    try:
        store.finalize(final_status)
    except BaseException as exc:
        if failure is None:
            failure = exc
    if failure is not None:
        raise failure
    if result is None or result.exit_code != 0:
        raise PerformanceMatrixHarnessError(
            "benchmark row execution did not complete"
        )
    outcomes = {outcome.task_id: outcome for outcome in result.outcomes}
    selected_ids = tuple(str(value) for value in descriptor["selected_task_ids"])
    if any(
        task_id not in outcomes
        or outcomes[task_id].status != "completed"
        or outcomes[task_id].reason == "restored_completed_result"
        for task_id in selected_ids
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark selected task execution closure differs"
        )
    result_document = {
        "schema_version": "dual_frequency_task17_row_child_result_v1",
        "row_id": row_id,
        "attempt": int(attempt_plan["attempt"]),
        "run_root": str(store.root),
        "run_manifest_sha256": _sha256_file(
            store.root / "run_manifest.json"
        ),
        "segment_plan_sha256": descriptor["plan_hash"],
        "selected_task_ids": list(selected_ids),
        "restored_task_ids": sorted(installed),
        "numerical_identity_sha256": _selected_numerical_identity(
            store,
            selected_ids,
        ),
        "task_statuses": {
            task_id: outcomes[task_id].status for task_id in sorted(outcomes)
        },
    }
    result_document["result_sha256"] = _canonical_sha256(result_document)
    _atomic_json(
        attempt_root.expanduser().resolve() / "attempt_result.json",
        result_document,
    )
    return result_document


def _finished_execution_segment(run_root: Path) -> tuple[str, Path, dict[str, object]]:
    """Return the sole finished execution segment for one isolated row run."""

    root = run_root.expanduser().resolve()
    manifest_path = root / "run_manifest.json"
    manifest = _read_json(manifest_path, "benchmark row run manifest")
    if manifest.get("final_status") != "completed":
        raise PerformanceMatrixHarnessError(
            "benchmark row run is not terminal completed"
        )
    segment_root = root / "execution_segments"
    paths = tuple(sorted(segment_root.glob("segment_*.json")))
    if len(paths) != 1:
        raise PerformanceMatrixHarnessError(
            "benchmark row must contain exactly one execution segment"
        )
    path = paths[0].resolve()
    segment = _read_json(path, "benchmark row execution segment")
    segment_id = path.stem
    if (
        segment.get("segment_id") != segment_id
        or segment.get("status") != "finished"
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark row execution segment is not finished"
        )
    return segment_id, path, segment


def _terminal_probe_summary(path: Path) -> dict[str, object]:
    """Validate one complete probe CSV and return its terminal counters."""

    source = path.expanduser().resolve()
    expected_fields = (
        "timestamp_utc",
        "elapsed_monotonic_seconds",
        "process_count",
        "tree_rss_bytes",
        "aggregate_cpu_seconds",
        "swap_used_bytes",
        "source_bytes",
        "scratch_bytes",
        "event",
    )
    try:
        with source.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != expected_fields:
                raise PerformanceMatrixHarnessError(
                    "benchmark probe CSV fields differ"
                )
            rows = list(reader)
    except OSError as exc:
        raise PerformanceMatrixHarnessError(
            "benchmark probe CSV is unreadable"
        ) from exc
    if len(rows) < 2:
        raise PerformanceMatrixHarnessError(
            "benchmark probe CSV has no measured process envelope"
        )
    prior_timestamp: datetime | None = None
    prior_elapsed = -1.0
    prior_cpu = -1.0
    prior_source = -1
    prior_scratch = -1
    peak_rss = 0
    swap_values: list[int] = []
    for index, row in enumerate(rows):
        try:
            timestamp = datetime.fromisoformat(row["timestamp_utc"])
            elapsed = float(row["elapsed_monotonic_seconds"])
            process_count = int(row["process_count"])
            rss = int(row["tree_rss_bytes"])
            cpu = float(row["aggregate_cpu_seconds"])
            swap = int(row["swap_used_bytes"])
            source_bytes = int(row["source_bytes"])
            scratch_bytes = int(row["scratch_bytes"])
        except (TypeError, ValueError) as exc:
            raise PerformanceMatrixHarnessError(
                "benchmark probe CSV contains an invalid scalar"
            ) from exc
        if (
            timestamp.tzinfo is None
            or not math.isfinite(elapsed)
            or not math.isfinite(cpu)
            or min(
                elapsed,
                process_count,
                rss,
                cpu,
                swap,
                source_bytes,
                scratch_bytes,
            )
            < 0
            or (prior_timestamp is not None and timestamp <= prior_timestamp)
            or elapsed <= prior_elapsed
            or cpu < prior_cpu
            or source_bytes < prior_source
            or scratch_bytes < prior_scratch
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark probe CSV is not monotonic"
            )
        expected_event = "runner_exit" if index == len(rows) - 1 else "sample"
        if row["event"] != expected_event:
            raise PerformanceMatrixHarnessError(
                "benchmark probe CSV terminal event differs"
            )
        if (
            expected_event == "sample"
            and process_count < 1
        ) or (
            expected_event == "runner_exit"
            and process_count != 0
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark probe process envelope differs"
            )
        prior_timestamp = timestamp
        prior_elapsed = elapsed
        prior_cpu = cpu
        prior_source = source_bytes
        prior_scratch = scratch_bytes
        peak_rss = max(peak_rss, rss)
        swap_values.append(swap)
    return {
        "row_count": len(rows),
        "wall_seconds": prior_elapsed,
        "aggregate_cpu_seconds": prior_cpu,
        "peak_rss_bytes": peak_rss,
        "swap_delta_bytes": max(swap_values) - swap_values[0],
        "source_bytes": prior_source,
        "scratch_bytes": prior_scratch,
        "probe_sha256": _sha256_file(source),
    }


def _wait_for_probe_attachment(
    process: subprocess.Popen[bytes],
    path: Path,
    *,
    timeout_seconds: float = 60.0,
) -> None:
    """Require one live probe sample before releasing the runner."""

    started = time.monotonic()
    source = path.expanduser().resolve()
    while True:
        if source.is_file():
            try:
                with source.open("r", encoding="utf-8", newline="") as handle:
                    rows = list(csv.reader(handle))
            except OSError:
                rows = []
            if len(rows) > 1:
                if process.poll() is not None:
                    raise PerformanceMatrixHarnessError(
                        "benchmark probe exited during attachment"
                    )
                return
        if process.poll() is not None:
            raise PerformanceMatrixHarnessError(
                "benchmark probe exited before attachment"
            )
        if time.monotonic() - started > timeout_seconds:
            raise PerformanceMatrixHarnessError(
                "benchmark probe attachment timed out"
            )
        time.sleep(0.1)


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Stop one harness-owned process group without touching other runs."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10.0)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait(timeout=10.0)


def _run_row_attempt(
    *,
    request_path: Path,
    benchmark_root: Path,
    resolved: Mapping[str, object],
    row: Mapping[str, object],
    candidate_parity_path: Path,
) -> dict[str, object]:
    """Run one prepared row through the measured child/probe transaction."""

    from my_helper.fiber.pipelines.build_task17_performance_byte_ledger import (
        build as build_byte_ledger,
    )
    from my_helper.fiber.pipelines.build_task17_performance_counters import (
        build as build_counters,
    )
    from my_helper.fiber.pipelines.init_task17_performance_byte_ledger_index import (
        initialize as initialize_byte_ledger,
    )
    from my_helper.fiber.pipelines.run_task17_artifact_static_audit import (
        audit as run_artifact_static_audit,
    )

    root = benchmark_root.expanduser().resolve()
    row_id = str(row.get("row_id", ""))
    row_root = root / "rows" / row_id
    contract_path = row_root / "row_contract.json"
    contract_sha256 = _sha256_file(contract_path)
    existing = _validate_row_result(row_root, contract_sha256)
    if existing is not None:
        return existing
    attempt_root, attempt_plan = _prepare_row_attempt(
        resolved=resolved,
        row=row,
        benchmark_root=root,
    )
    environment = _validate_child_execution_environment(resolved)
    script = Path(__file__).resolve()
    child_command = (
        sys.executable,
        str(script),
        "_run-child",
        "--request",
        str(request_path.expanduser().resolve()),
        "--benchmark-root",
        str(root),
        "--row-id",
        row_id,
        "--attempt-root",
        str(attempt_root),
    )
    runner_stdout_path = attempt_root / "runner.stdout.log"
    runner_stderr_path = attempt_root / "runner.stderr.log"
    probe_stdout_path = attempt_root / "probe.stdout.log"
    probe_stderr_path = attempt_root / "probe.stderr.log"
    probe_path = attempt_root / "probe.csv"
    byte_index_path = attempt_root / "live_byte_ledger_index.json"
    runner: subprocess.Popen[bytes] | None = None
    probe: subprocess.Popen[bytes] | None = None
    try:
        with (
            runner_stdout_path.open("wb") as runner_stdout,
            runner_stderr_path.open("wb") as runner_stderr,
            probe_stdout_path.open("wb") as probe_stdout,
            probe_stderr_path.open("wb") as probe_stderr,
        ):
            child_environment = os.environ.copy()
            child_environment["CONDA_DEFAULT_ENV"] = environment[
                "conda_environment"
            ]
            runner = subprocess.Popen(
                child_command,
                cwd=environment["working_directory"],
                env=child_environment,
                stdout=runner_stdout,
                stderr=runner_stderr,
                start_new_session=True,
            )
            ready = _runner_ready(
                runner,
                attempt_root / "runner_ready.json",
                row_id=row_id,
            )
            if (
                ready["runner_pid"] != runner.pid
                or ready["segment_plan_sha256"]
                != attempt_plan["segment_plan_sha256"]
            ):
                raise PerformanceMatrixHarnessError(
                    "benchmark runner readiness differs from the parent process"
                )
            run_root = Path(str(ready["run_root"])).expanduser().resolve()
            initialize_byte_ledger(
                run_root=run_root,
                output=byte_index_path,
            )
            protected = (
                Path(str(resolved["accepted_parent"]["root"])),
                Path(str(resolved["accepted_independent_oss"]["root"])),
                Path(str(resolved["accepted_oss_cache"]["cache_root"])),
                run_root,
            )
            probe_command: list[str] = [
                sys.executable,
                str(script.with_name("run_task17_performance_probe.py")),
                "--runner-pid",
                str(runner.pid),
                "--output",
                str(probe_path),
                "--byte-counter",
                str(byte_index_path),
            ]
            for protected_root in protected:
                probe_command.extend(
                    ("--guarded-root", str(protected_root.resolve()))
                )
            probe = subprocess.Popen(
                tuple(probe_command),
                cwd=environment["working_directory"],
                env=child_environment,
                stdout=probe_stdout,
                stderr=probe_stderr,
                start_new_session=True,
            )
            _wait_for_probe_attachment(probe, probe_path)
            _measurement_start(
                attempt_root / "measurement_start.json",
                row_id=row_id,
                runner_pid=runner.pid,
                byte_ledger_index=byte_index_path,
            )
            runner_code = runner.wait()
            probe_code = probe.wait(timeout=60.0)
        if runner_code != 0 or probe_code != 0:
            raise PerformanceMatrixHarnessError(
                "benchmark runner or probe did not complete"
            )
        probe_summary = _terminal_probe_summary(probe_path)
        child_result_path = attempt_root / "attempt_result.json"
        child_result = _read_json(
            child_result_path,
            "benchmark row child result",
        )
        if (
            child_result.get("row_id") != row_id
            or child_result.get("attempt") != attempt_plan["attempt"]
            or child_result.get("segment_plan_sha256")
            != attempt_plan["segment_plan_sha256"]
            or child_result.get("result_sha256")
            != _canonical_sha256(
                {
                    key: value
                    for key, value in child_result.items()
                    if key != "result_sha256"
                }
            )
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark row child result identity differs"
            )
        run_root = Path(str(child_result["run_root"])).expanduser().resolve()
        manifest_path = run_root / "run_manifest.json"
        if (
            not manifest_path.is_file()
            or _sha256_file(manifest_path)
            != child_result["run_manifest_sha256"]
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark row child manifest SHA differs"
            )
        segment_id, segment_path, segment = _finished_execution_segment(
            run_root
        )
        byte_ledger_path = attempt_root / "performance_byte_ledger.json"
        build_byte_ledger(
            run_root=run_root,
            segment_id=segment_id,
            output=byte_ledger_path,
        )
        byte_ledger = _read_json(
            byte_ledger_path,
            "benchmark terminal byte ledger",
        )
        if (
            byte_ledger.get("source_bytes") != probe_summary["source_bytes"]
            or byte_ledger.get("scratch_bytes")
            != probe_summary["scratch_bytes"]
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark probe and terminal byte ledger differ"
            )
        audit_path = run_artifact_static_audit(
            run_root=run_root,
            segment_id=segment_id,
            source_root=CORE_ROOT / "dual_frequency",
        )
        parity = candidate_parity_path.expanduser().resolve()
        if not parity.is_file():
            raise PerformanceMatrixHarnessError(
                "configured candidate parity report is missing"
            )
        event_path = (run_root / str(segment["performance_events_path"])).resolve()
        counter_inputs = {
            "schema_version": (
                "dual_frequency_performance_counter_inputs_v1"
            ),
            "run_root": str(run_root),
            "run_id": _read_json(
                manifest_path,
                "benchmark row run manifest",
            )["run_id"],
            "segment_id": segment_id,
            "segment_sha256": _sha256_file(segment_path),
            "event_report_path": str(event_path),
            "event_report_sha256": _sha256_file(event_path),
            "byte_ledger_path": str(byte_ledger_path),
            "byte_ledger_sha256": _sha256_file(byte_ledger_path),
            "candidate_parity_path": str(parity),
            "candidate_parity_sha256": _sha256_file(parity),
            "artifact_static_audit_path": str(audit_path),
            "artifact_static_audit_sha256": _sha256_file(audit_path),
            "benchmark_class": str(row["benchmark_class"]),
            "cache_state": str(row["cache_state"]),
        }
        counter_inputs_path = attempt_root / "performance_counter_inputs.json"
        _atomic_json(counter_inputs_path, counter_inputs)
        counter_path = build_counters(counter_inputs_path)
        evidence_paths = (
            attempt_root / "attempt_plan.json",
            attempt_root / "runner_ready.json",
            attempt_root / "measurement_start.json",
            child_result_path,
            runner_stdout_path,
            runner_stderr_path,
            probe_path,
            probe_stdout_path,
            probe_stderr_path,
            byte_index_path,
            byte_ledger_path,
            counter_inputs_path,
            manifest_path,
            segment_path,
            event_path,
            audit_path,
            counter_path,
        )
        result = {
            "schema_version": _ROW_RESULT_SCHEMA,
            "row_id": row_id,
            "contract_sha256": contract_sha256,
            "status": "executed",
            "attempt": attempt_plan["attempt"],
            "evidence": [
                _relative_evidence(path, row_root=row_root)
                for path in evidence_paths
            ],
            "not_run_reason": None,
        }
        _atomic_json(row_root / "row_result.json", result)
        validated = _validate_row_result(row_root, contract_sha256)
        if validated != result:
            raise PerformanceMatrixHarnessError(
                "terminal executed benchmark row differs after publication"
            )
        return result
    finally:
        if runner is not None:
            _stop_process_group(runner)
        if probe is not None:
            _stop_process_group(probe)


def _row_io_classification(
    run_root: Path,
    segment: Mapping[str, object],
) -> str:
    """Classify one row only from its run-owned scheduler windows."""

    root = run_root.expanduser().resolve()
    relative = Path(str(segment.get("scheduler_windows_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise PerformanceMatrixHarnessError(
            "benchmark scheduler-window path is unsafe"
        )
    path = (root / relative).resolve()
    if (
        root not in path.parents
        or not path.is_file()
        or _sha256_file(path)
        != segment.get("scheduler_windows_sha256")
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark scheduler-window SHA differs"
        )
    document = _read_json(path, "benchmark scheduler windows")
    rows = document.get("rows")
    if (
        document.get("schema_version")
        != "dual_frequency_scheduler_windows_v1"
        or document.get("segment_id") != segment.get("segment_id")
        or not isinstance(rows, list)
        or not rows
        or segment.get("scheduler_window_count") != len(rows)
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark scheduler-window closure differs"
        )
    storage_limited: list[bool] = []
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or type(row.get("storage_limited")) is not bool
        ):
            raise PerformanceMatrixHarnessError(
                "benchmark scheduler storage classification differs"
            )
        storage_limited.append(bool(row["storage_limited"]))
    return "storage_limited" if any(storage_limited) else "compute_bound"


def _matrix_row_entry(
    *,
    benchmark_root: Path,
    row: Mapping[str, object],
) -> dict[str, object]:
    """Convert one SHA-validated terminal row transaction to matrix input."""

    root = benchmark_root.expanduser().resolve()
    row_id = str(row.get("row_id", ""))
    row_root = root / "rows" / row_id
    contract_path = row_root / "row_contract.json"
    result = _validate_row_result(
        row_root,
        _sha256_file(contract_path),
    )
    if result is None:
        raise PerformanceMatrixHarnessError(
            "benchmark matrix row is not terminal"
        )
    base = {
        **_row_key_payload(row),
        "status": result["status"],
        "not_run_reason": result["not_run_reason"],
    }
    if result["status"] == "not_run":
        preflight = row_root / "real_cold_solver_preflight.json"
        return {
            **base,
            "preflight_path": str(preflight),
            "preflight_sha256": _sha256_file(preflight),
            "run_root": None,
            "segment_id": None,
            "probe_csv": None,
            "probe_sha256": None,
            "configuration_sha256": None,
            "numerical_identity_sha256": None,
            "io_classification": None,
            "counter_path": None,
            "counter_sha256": None,
        }
    attempt = int(result["attempt"])
    attempt_root = row_root / "attempts" / f"attempt_{attempt:04d}"
    child_path = attempt_root / "attempt_result.json"
    child = _read_json(child_path, "benchmark row child result")
    unsigned_child = {
        key: value for key, value in child.items() if key != "result_sha256"
    }
    numerical_identity = str(
        child.get("numerical_identity_sha256", "")
    ).lower()
    if (
        child.get("row_id") != row_id
        or child.get("attempt") != attempt
        or child.get("result_sha256") != _canonical_sha256(unsigned_child)
        or len(numerical_identity) != 64
        or any(
            character not in "0123456789abcdef"
            for character in numerical_identity
        )
    ):
        raise PerformanceMatrixHarnessError(
            "benchmark row child numerical identity differs"
        )
    run_root = Path(str(child["run_root"])).expanduser().resolve()
    segment_id, _segment_path, segment = _finished_execution_segment(
        run_root
    )
    probe = attempt_root / "probe.csv"
    _terminal_probe_summary(probe)
    counter = (
        run_root
        / "execution_segments"
        / f"performance_counters_{segment_id}.json"
    )
    configuration = run_root / "configuration_resolved.yaml"
    if not counter.is_file() or not configuration.is_file():
        raise PerformanceMatrixHarnessError(
            "benchmark matrix row terminal evidence is missing"
        )
    return {
        **base,
        "preflight_path": None,
        "preflight_sha256": None,
        "run_root": str(run_root),
        "segment_id": segment_id,
        "probe_csv": str(probe),
        "probe_sha256": _sha256_file(probe),
        "configuration_sha256": _sha256_file(configuration),
        "numerical_identity_sha256": numerical_identity,
        "io_classification": _row_io_classification(
            run_root,
            segment,
        ),
        "counter_path": str(counter),
        "counter_sha256": _sha256_file(counter),
    }


def _publish_matrix_manifest(
    *,
    benchmark_root: Path,
    resolved: Mapping[str, object],
) -> dict[str, object]:
    """Commit the exact terminal 72-row matrix and acceptance report."""

    from my_helper.fiber.pipelines.validate_task17_performance_acceptance import (
        validate as validate_performance,
    )

    root = benchmark_root.expanduser().resolve()
    raw_rows = resolved.get("rows")
    connectomes = resolved.get("configured_connectomes")
    maximum_rss = resolved.get("maximum_task_tree_rss_bytes")
    if (
        not isinstance(raw_rows, list)
        or len(raw_rows) != 72
        or not isinstance(connectomes, list)
        or type(maximum_rss) is not int
    ):
        raise PerformanceMatrixHarnessError(
            "resolved performance matrix closure differs"
        )
    rows = [
        _matrix_row_entry(
            benchmark_root=root,
            row=row,
        )
        for row in raw_rows
        if isinstance(row, Mapping)
    ]
    if len(rows) != 72:
        raise PerformanceMatrixHarnessError(
            "terminal performance matrix row closure differs"
        )
    manifest = {
        "schema_version": "dual_frequency_task17_performance_matrix_v1",
        "configured_connectomes": list(connectomes),
        "chosen_default_workers": 3,
        "max_rss_bytes": maximum_rss,
        "rows": rows,
    }
    manifest_path = root / "performance_matrix.json"
    _atomic_json(manifest_path, manifest)
    try:
        acceptance = validate_performance(manifest_path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PerformanceMatrixHarnessError(
            "terminal performance matrix acceptance failed"
        ) from exc
    acceptance_path = root / "performance_acceptance.json"
    _atomic_json(acceptance_path, acceptance)
    return {
        "status": "completed",
        "matrix_path": str(manifest_path),
        "matrix_sha256": _sha256_file(manifest_path),
        "acceptance_path": str(acceptance_path),
        "acceptance_sha256": _sha256_file(acceptance_path),
        "row_count": 72,
    }


def _run_matrix(
    request_path: Path,
    benchmark_root: Path,
) -> dict[str, object]:
    """Resume all missing seeds and rows, then publish terminal acceptance."""

    resolved, marker = _open_prepared_benchmark(
        request_path,
        benchmark_root,
    )
    root = benchmark_root.expanduser().resolve()
    for seed_row in _warm_seed_rows(resolved):
        _execute_unmeasured_warm_seed(
            resolved=resolved,
            row=seed_row,
            benchmark_root=root,
        )
    authorization = resolved.get("real_cold_solver_authorization")
    rows = resolved.get("rows")
    if not isinstance(authorization, Mapping) or not isinstance(rows, list):
        raise PerformanceMatrixHarnessError(
            "resolved benchmark execution closure differs"
        )
    parity = marker.get("candidate_parity")
    if not isinstance(parity, Mapping):
        raise PerformanceMatrixHarnessError(
            "configured candidate-parity binding is missing"
        )
    candidate_parity_path = Path(
        str(parity.get("report_path", ""))
    ).expanduser().resolve()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise PerformanceMatrixHarnessError(
                "resolved benchmark row is invalid"
            )
        row = dict(raw)
        row_root = root / "rows" / str(row["row_id"])
        _contract_path, contract_sha256 = _ensure_row_contract(
            row_root,
            _row_contract(resolved, row),
        )
        if _validate_row_result(row_root, contract_sha256) is not None:
            continue
        if row.get("planned_status") == "not_run":
            _publish_not_run_row(
                row_root,
                contract_sha256=contract_sha256,
                row=row,
                authorization=authorization,
            )
            continue
        _run_row_attempt(
            request_path=request_path,
            benchmark_root=root,
            resolved=resolved,
            row=row,
            candidate_parity_path=candidate_parity_path,
        )
    return _publish_matrix_manifest(
        benchmark_root=root,
        resolved=resolved,
    )


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
    expected_marker = {
        **marker,
        "candidate_parity": _candidate_parity_binding(root),
    }
    if stored_plan != resolved or stored_marker != expected_marker:
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
    parser.add_argument(
        "operation",
        choices=("prepare", "validate", "_run-child"),
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--benchmark-root", required=True, type=Path)
    parser.add_argument("--row-id")
    parser.add_argument("--attempt-root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.operation == "prepare":
            result = prepare(arguments.request, arguments.benchmark_root)
        elif arguments.operation == "validate":
            result = validate_existing(
                arguments.request,
                arguments.benchmark_root,
            )
        else:
            if not arguments.row_id or arguments.attempt_root is None:
                raise PerformanceMatrixHarnessError(
                    "benchmark child row ID and attempt root are required"
                )
            result = _execute_row_child(
                request_path=arguments.request,
                benchmark_root=arguments.benchmark_root,
                row_id=arguments.row_id,
                attempt_root=arguments.attempt_root,
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
