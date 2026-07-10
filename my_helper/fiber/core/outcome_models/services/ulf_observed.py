"""Immutable HF-derived requests for ULF direct-voxel and fiber branches."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ..catalog import EndpointRecord
from ..executor import RunContext
from ..planner import TaskSpec
from ..records import DeltaHFBundle, HFSourceRecord, NuisancePlan, RecordError


def validate_hf_source_for_ulf(
    source: HFSourceRecord,
    *,
    expected_subject_order: tuple[str, ...],
    expected_feature_sha: str,
) -> None:
    """Require exact subject and feature identity before reusing an accepted HF source."""
    if not source.accepted:
        return
    if source.subject_order != tuple(expected_subject_order):
        raise RecordError("matched HF source subject order does not match the ULF endpoint")
    if source.feature_axis is None or source.feature_axis.sha256 != expected_feature_sha:
        raise RecordError("matched HF source feature axis does not match the ULF model axis")


@dataclass(frozen=True)
class ULFObservedRequest:
    endpoint: EndpointRecord
    branch: str
    hf_source: HFSourceRecord
    delta_hf: DeltaHFBundle | None
    nuisance: NuisancePlan
    model_root: Path
    output_root: Path
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    hf_overlap_tau: float
    hf_overlap_coverage: int | None

    @classmethod
    def from_context(
        cls,
        endpoint: EndpointRecord,
        task: TaskSpec,
        context: RunContext,
        *,
        hf_source: HFSourceRecord,
        delta_hf: DeltaHFBundle | None,
    ) -> "ULFObservedRequest":
        if context.config is None:
            raise RecordError("configured ULF service requires resolved workflow context")
        branch = task.key.branch
        if branch not in {"no_delta_hf", "delta_hf_adjusted"}:
            raise RecordError(f"ULF branch request has unsupported branch {branch!r}")

        if branch == "delta_hf_adjusted":
            if not hf_source.accepted:
                raise RecordError("delta_hf_adjusted cannot run without an accepted matched HF source")
            if delta_hf is None or not delta_hf.valid:
                raise RecordError("delta_hf_adjusted requires a valid adequate-or-limited DeltaHF bundle")
            if (
                float(delta_hf.selected_hf_tau) != float(hf_source.selected_tau)
                or int(delta_hf.selected_hf_coverage) != int(hf_source.selected_coverage)
            ):
                raise RecordError("DeltaHF tau/Coverage must equal the immutable matched HF selected source")
        nuisance = NuisancePlan.for_branch(branch, delta_hf)

        if endpoint.key.model_family == "ulf_voxel":
            settings = context.config.model.direct_voxel
        elif endpoint.key.model_family == "ulf_fiber":
            settings = context.config.model.normative_fiber
        else:
            raise RecordError(f"unsupported ULF model family {endpoint.key.model_family!r}")

        model_root = context.store.run_root / "models" / endpoint.endpoint_model_id
        return cls(
            endpoint=endpoint,
            branch=branch,
            hf_source=hf_source,
            delta_hf=delta_hf,
            nuisance=nuisance,
            model_root=model_root,
            output_root=model_root / "tasks" / task.task_id,
            tau_grid=tuple(float(value) for value in settings["tau_grid_v_per_m"]),
            coverage_grid=tuple(int(value) for value in settings["coverage_grid"]),
            primary_tau=float(settings["pre_specified_tau_v_per_m"]),
            primary_coverage=int(settings["pre_specified_coverage"]),
            hf_overlap_tau=(float(hf_source.selected_tau) if hf_source.accepted else math.inf),
            hf_overlap_coverage=(int(hf_source.selected_coverage) if hf_source.accepted else None),
        )
