"""Immutable scientific records linking sources, nuisances, and final artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .identity import canonical_hash
from .state import ACCEPTED_SOURCE_STATUSES, PREDICTION_STATUSES


class RecordError(ValueError):
    """Raised when a scientific record is incomplete or internally inconsistent."""


def _sha256(value: str, field: str) -> str:
    token = str(value).lower()
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise RecordError(f"{field} must be a 64-character SHA-256 digest")
    return token


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise RecordError(f"{field} must be nonempty")
    return token


@dataclass(frozen=True)
class FeatureAxisRef:
    ids_path: Path
    count: int
    sha256: str
    identity_source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ids_path", Path(self.ids_path))
        object.__setattr__(self, "count", int(self.count))
        object.__setattr__(self, "sha256", _sha256(self.sha256, "feature axis sha256"))
        object.__setattr__(self, "identity_source", _token(self.identity_source, "identity_source"))
        if self.count < 1:
            raise RecordError("feature axis count must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "ids_path": str(self.ids_path),
            "count": self.count,
            "sha256": self.sha256,
            "identity_source": self.identity_source,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FeatureAxisRef":
        return cls(
            ids_path=Path(str(value["ids_path"])),
            count=int(value["count"]),
            sha256=str(value["sha256"]),
            identity_source=str(value["identity_source"]),
        )


@dataclass(frozen=True)
class ArtifactRef:
    task_id: str
    kind: str
    relative_path: str
    sha256: str
    shape: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _token(self.task_id, "task_id"))
        object.__setattr__(self, "kind", _token(self.kind, "kind"))
        path = PurePosixPath(_token(self.relative_path, "relative_path"))
        if path.is_absolute() or ".." in path.parts:
            raise RecordError("artifact relative_path must remain inside the run root")
        object.__setattr__(self, "relative_path", path.as_posix())
        object.__setattr__(self, "sha256", _sha256(self.sha256, "artifact sha256"))
        shape = tuple(int(value) for value in self.shape)
        if any(value < 0 for value in shape):
            raise RecordError("artifact shape dimensions must be nonnegative")
        object.__setattr__(self, "shape", shape)

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "shape": list(self.shape),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ArtifactRef":
        return cls(
            task_id=str(value["task_id"]),
            kind=str(value["kind"]),
            relative_path=str(value["relative_path"]),
            sha256=str(value["sha256"]),
            shape=tuple(int(item) for item in value.get("shape", ())),
        )


@dataclass(frozen=True)
class HFSourceRecord:
    resolver_task_id: str
    endpoint_model_id: str
    input_status: str
    source_status: str
    prediction_status: str
    threshold_source: str
    selected_tau: float | None
    selected_coverage: int | None
    subject_order: tuple[str, ...]
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[ArtifactRef, ...]
    record_hash: str

    @classmethod
    def create(
        cls,
        *,
        resolver_task_id: str,
        endpoint_model_id: str,
        input_status: str,
        source_status: str,
        prediction_status: str,
        threshold_source: str,
        selected_tau: float | None,
        selected_coverage: int | None,
        subject_order: tuple[str, ...],
        feature_axis: FeatureAxisRef | None,
        artifacts: tuple[ArtifactRef, ...],
    ) -> "HFSourceRecord":
        payload = {
            "resolver_task_id": _token(resolver_task_id, "resolver_task_id"),
            "endpoint_model_id": _token(endpoint_model_id, "endpoint_model_id"),
            "input_status": _token(input_status, "input_status"),
            "source_status": _token(source_status, "source_status"),
            "prediction_status": _token(prediction_status, "prediction_status"),
            "threshold_source": _token(threshold_source, "threshold_source"),
            "selected_tau": float(selected_tau) if selected_tau is not None else None,
            "selected_coverage": int(selected_coverage) if selected_coverage is not None else None,
            "subject_order": tuple(_token(value, "subject_id") for value in subject_order),
            "feature_axis": feature_axis,
            "artifacts": tuple(artifacts),
        }
        if payload["source_status"] in ACCEPTED_SOURCE_STATUSES:
            if payload["input_status"] != "valid":
                raise RecordError("accepted HF source requires valid input")
            if payload["prediction_status"] not in PREDICTION_STATUSES:
                raise RecordError("accepted HF source requires a prediction status")
            if payload["selected_tau"] is None or payload["selected_coverage"] is None:
                raise RecordError("accepted HF source requires selected tau and coverage")
            if not payload["subject_order"] or feature_axis is None or not artifacts:
                raise RecordError("accepted HF source requires subject order, feature axis, and artifacts")
        record_hash = canonical_hash(payload)
        return cls(**payload, record_hash=record_hash)

    @property
    def accepted(self) -> bool:
        return self.input_status == "valid" and self.source_status in ACCEPTED_SOURCE_STATUSES

    def as_dict(self) -> dict[str, object]:
        return {
            "resolver_task_id": self.resolver_task_id,
            "endpoint_model_id": self.endpoint_model_id,
            "input_status": self.input_status,
            "source_status": self.source_status,
            "prediction_status": self.prediction_status,
            "threshold_source": self.threshold_source,
            "selected_tau": self.selected_tau,
            "selected_coverage": self.selected_coverage,
            "subject_order": list(self.subject_order),
            "feature_axis": self.feature_axis.as_dict() if self.feature_axis is not None else None,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "HFSourceRecord":
        axis_value = value.get("feature_axis")
        record = cls.create(
            resolver_task_id=str(value["resolver_task_id"]),
            endpoint_model_id=str(value["endpoint_model_id"]),
            input_status=str(value["input_status"]),
            source_status=str(value["source_status"]),
            prediction_status=str(value["prediction_status"]),
            threshold_source=str(value["threshold_source"]),
            selected_tau=float(value["selected_tau"]) if value.get("selected_tau") is not None else None,
            selected_coverage=(
                int(value["selected_coverage"]) if value.get("selected_coverage") is not None else None
            ),
            subject_order=tuple(str(item) for item in value.get("subject_order", ())),
            feature_axis=(FeatureAxisRef.from_dict(dict(axis_value)) if isinstance(axis_value, dict) else None),
            artifacts=tuple(ArtifactRef.from_dict(dict(item)) for item in value.get("artifacts", ())),
        )
        if record.record_hash != value.get("record_hash"):
            raise RecordError("HF source record hash mismatch")
        return record


@dataclass(frozen=True)
class DeltaHFBundle:
    input_status: str
    support_status: str
    selected_hf_tau: float | None
    selected_hf_coverage: int | None
    full_scores: ArtifactRef | None
    fold_scores: ArtifactRef | None
    support_rows: ArtifactRef | None
    failure_stage: str = ""
    failure_detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_status", _token(self.input_status, "input_status"))
        object.__setattr__(self, "support_status", _token(self.support_status, "support_status"))
        object.__setattr__(
            self,
            "selected_hf_tau",
            float(self.selected_hf_tau) if self.selected_hf_tau is not None else None,
        )
        object.__setattr__(
            self,
            "selected_hf_coverage",
            int(self.selected_hf_coverage) if self.selected_hf_coverage is not None else None,
        )

    @property
    def valid(self) -> bool:
        if self.input_status != "valid" or self.support_status not in {"adequate", "limited"}:
            return False
        if self.selected_hf_tau is None or self.selected_hf_coverage is None:
            return False
        if self.full_scores is None or self.fold_scores is None or self.support_rows is None:
            return False
        if len(self.full_scores.shape) != 1 or len(self.fold_scores.shape) != 2:
            return False
        n_subjects = self.full_scores.shape[0]
        return self.fold_scores.shape == (n_subjects, n_subjects)

    @property
    def record_hash(self) -> str:
        return canonical_hash(
            {
                "input_status": self.input_status,
                "support_status": self.support_status,
                "selected_hf_tau": self.selected_hf_tau,
                "selected_hf_coverage": self.selected_hf_coverage,
                "full_scores": self.full_scores,
                "fold_scores": self.fold_scores,
                "support_rows": self.support_rows,
                "failure_stage": self.failure_stage,
                "failure_detail": self.failure_detail,
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "input_status": self.input_status,
            "support_status": self.support_status,
            "selected_hf_tau": self.selected_hf_tau,
            "selected_hf_coverage": self.selected_hf_coverage,
            "full_scores": self.full_scores.as_dict() if self.full_scores is not None else None,
            "fold_scores": self.fold_scores.as_dict() if self.fold_scores is not None else None,
            "support_rows": self.support_rows.as_dict() if self.support_rows is not None else None,
            "failure_stage": self.failure_stage,
            "failure_detail": self.failure_detail,
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DeltaHFBundle":
        def artifact(name: str) -> ArtifactRef | None:
            item = value.get(name)
            return ArtifactRef.from_dict(dict(item)) if isinstance(item, dict) else None

        bundle = cls(
            input_status=str(value["input_status"]),
            support_status=str(value["support_status"]),
            selected_hf_tau=(
                float(value["selected_hf_tau"]) if value.get("selected_hf_tau") is not None else None
            ),
            selected_hf_coverage=(
                int(value["selected_hf_coverage"])
                if value.get("selected_hf_coverage") is not None
                else None
            ),
            full_scores=artifact("full_scores"),
            fold_scores=artifact("fold_scores"),
            support_rows=artifact("support_rows"),
            failure_stage=str(value.get("failure_stage", "")),
            failure_detail=str(value.get("failure_detail", "")),
        )
        if bundle.record_hash != value.get("record_hash"):
            raise RecordError("DeltaHF bundle hash mismatch")
        return bundle


@dataclass(frozen=True)
class NuisancePlan:
    branch: str
    columns: tuple[str, ...]
    delta_hf_record_hash: str | None

    @classmethod
    def for_branch(cls, branch: str, delta_hf: DeltaHFBundle | None) -> "NuisancePlan":
        if branch == "no_delta_hf":
            return cls(branch=branch, columns=("Y_HF_ref",), delta_hf_record_hash=None)
        if branch == "delta_hf_adjusted":
            if delta_hf is None or not delta_hf.valid:
                raise RecordError("delta_hf_adjusted nuisance requires a valid DeltaHF bundle")
            return cls(
                branch=branch,
                columns=("Y_HF_ref", "DeltaHFScore"),
                delta_hf_record_hash=delta_hf.record_hash,
            )
        if branch == "hf_source":
            return cls(branch=branch, columns=("Y_base",), delta_hf_record_hash=None)
        raise RecordError(f"unsupported nuisance branch {branch!r}")

    def as_dict(self) -> dict[str, object]:
        return {
            "branch": self.branch,
            "columns": list(self.columns),
            "delta_hf_record_hash": self.delta_hf_record_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "NuisancePlan":
        return cls(
            branch=str(value["branch"]),
            columns=tuple(str(item) for item in value["columns"]),
            delta_hf_record_hash=(
                str(value["delta_hf_record_hash"])
                if value.get("delta_hf_record_hash") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class FinalArtifactRecord:
    final_model_id: str
    endpoint_model_id: str
    final_branch: str
    final_role: str
    selected_tau: float
    selected_coverage: int
    estimator: str
    nuisance: NuisancePlan
    manifest: ArtifactRef
    exposure: ArtifactRef
    scores: ArtifactRef
    feature_axis: FeatureAxisRef
    record_hash: str

    @classmethod
    def create(
        cls,
        *,
        final_model_id: str,
        endpoint_model_id: str,
        final_branch: str,
        final_role: str,
        selected_tau: float,
        selected_coverage: int,
        estimator: str,
        nuisance: NuisancePlan,
        manifest: ArtifactRef,
        exposure: ArtifactRef,
        scores: ArtifactRef,
        feature_axis: FeatureAxisRef,
    ) -> "FinalArtifactRecord":
        if nuisance.branch != final_branch and not (final_branch == "hf_source" and nuisance.branch == "hf_source"):
            raise RecordError("final branch and nuisance plan do not match")
        payload = {
            "final_model_id": _token(final_model_id, "final_model_id"),
            "endpoint_model_id": _token(endpoint_model_id, "endpoint_model_id"),
            "final_branch": _token(final_branch, "final_branch"),
            "final_role": _token(final_role, "final_role"),
            "selected_tau": float(selected_tau),
            "selected_coverage": int(selected_coverage),
            "estimator": _token(estimator, "estimator"),
            "nuisance": nuisance,
            "manifest": manifest,
            "exposure": exposure,
            "scores": scores,
            "feature_axis": feature_axis,
        }
        if payload["selected_tau"] <= 0 or payload["selected_coverage"] < 1:
            raise RecordError("final selected tau and coverage must be positive")
        return cls(**payload, record_hash=canonical_hash(payload))

    def as_dict(self) -> dict[str, object]:
        return {
            "final_model_id": self.final_model_id,
            "endpoint_model_id": self.endpoint_model_id,
            "final_branch": self.final_branch,
            "final_role": self.final_role,
            "selected_tau": self.selected_tau,
            "selected_coverage": self.selected_coverage,
            "estimator": self.estimator,
            "nuisance": self.nuisance.as_dict(),
            "manifest": self.manifest.as_dict(),
            "exposure": self.exposure.as_dict(),
            "scores": self.scores.as_dict(),
            "feature_axis": self.feature_axis.as_dict(),
            "record_hash": self.record_hash,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FinalArtifactRecord":
        record = cls.create(
            final_model_id=str(value["final_model_id"]),
            endpoint_model_id=str(value["endpoint_model_id"]),
            final_branch=str(value["final_branch"]),
            final_role=str(value["final_role"]),
            selected_tau=float(value["selected_tau"]),
            selected_coverage=int(value["selected_coverage"]),
            estimator=str(value["estimator"]),
            nuisance=NuisancePlan.from_dict(dict(value["nuisance"])),
            manifest=ArtifactRef.from_dict(dict(value["manifest"])),
            exposure=ArtifactRef.from_dict(dict(value["exposure"])),
            scores=ArtifactRef.from_dict(dict(value["scores"])),
            feature_axis=FeatureAxisRef.from_dict(dict(value["feature_axis"])),
        )
        if record.record_hash != value.get("record_hash"):
            raise RecordError("final artifact record hash mismatch")
        return record
