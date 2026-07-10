"""Canonical identities for configured endpoint-model workflow records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if value is None:
        return "none"
    return value


def canonical_hash(value: Mapping[str, Any], length: int | None = None) -> str:
    """Return a stable SHA-256 hash of a normalized mapping."""
    payload = json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if length is None:
        return digest
    if not 1 <= int(length) <= len(digest):
        raise ValueError("length must be between 1 and 64")
    return digest[: int(length)]


def _required_token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError(f"{field} must be nonempty")
    return token


@dataclass(frozen=True, order=True)
class EndpointModelKey:
    study_id: str
    scale_id: str
    endpoint_phase: str
    model_family: str
    connectome: str = "none"

    def __post_init__(self) -> None:
        for field in ("study_id", "scale_id", "endpoint_phase", "model_family", "connectome"):
            object.__setattr__(self, field, _required_token(getattr(self, field), field))

    def as_dict(self) -> dict[str, str]:
        return {
            "study_id": self.study_id,
            "scale_id": self.scale_id,
            "endpoint_phase": self.endpoint_phase,
            "model_family": self.model_family,
            "connectome": self.connectome,
        }

    @property
    def identifier(self) -> str:
        return f"endpoint_{canonical_hash(self.as_dict(), length=20)}"


@dataclass(frozen=True, order=True)
class TaskKey:
    endpoint_model_id: str
    execution_stage: str
    branch: str = "none"
    source_reference: str = "none"
    replicate: str = "none"

    def __post_init__(self) -> None:
        for field in ("endpoint_model_id", "execution_stage", "branch", "source_reference", "replicate"):
            object.__setattr__(self, field, _required_token(getattr(self, field), field))

    def as_dict(self) -> dict[str, str]:
        return {
            "endpoint_model_id": self.endpoint_model_id,
            "execution_stage": self.execution_stage,
            "branch": self.branch,
            "source_reference": self.source_reference,
            "replicate": self.replicate,
        }

    @property
    def identifier(self) -> str:
        return f"task_{canonical_hash(self.as_dict(), length=20)}"


@dataclass(frozen=True, order=True)
class FinalModelKey:
    endpoint_model_id: str
    final_branch: str
    selected_tau: float
    selected_coverage: int
    estimator: str

    def __post_init__(self) -> None:
        for field in ("endpoint_model_id", "final_branch", "estimator"):
            object.__setattr__(self, field, _required_token(getattr(self, field), field))
        object.__setattr__(self, "selected_tau", float(self.selected_tau))
        object.__setattr__(self, "selected_coverage", int(self.selected_coverage))
        if self.selected_tau <= 0:
            raise ValueError("selected_tau must be positive")
        if self.selected_coverage < 1:
            raise ValueError("selected_coverage must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "endpoint_model_id": self.endpoint_model_id,
            "final_branch": self.final_branch,
            "selected_tau": float(self.selected_tau),
            "selected_coverage": int(self.selected_coverage),
            "estimator": self.estimator,
        }

    @property
    def identifier(self) -> str:
        return f"final_{canonical_hash(self.as_dict(), length=20)}"
