"""Canonical identities for the generic dual-frequency model runtime."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


MODEL_FAMILIES = frozenset(
    {
        "reference_voxel",
        "reference_fiber",
        "addon_voxel",
        "addon_fiber",
    }
)


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("canonical identities cannot contain nonfinite values")
    return value


def canonical_hash(value: Mapping[str, Any], length: int | None = None) -> str:
    """Return a deterministic SHA-256 digest for a normalized mapping."""
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


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise ValueError(f"{field} must be nonempty")
    return token


@dataclass(frozen=True, order=True)
class EndpointKey:
    """Stable identity for one scale, endpoint binding, and model family."""

    study_id: str
    scale_id: str
    endpoint_binding_id: str
    model_family: str
    connectome_id: str = "none"

    def __post_init__(self) -> None:
        for field in (
            "study_id",
            "scale_id",
            "endpoint_binding_id",
            "model_family",
            "connectome_id",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        if self.model_family not in MODEL_FAMILIES:
            raise ValueError(f"unsupported model_family {self.model_family!r}")
        if self.model_family.endswith("voxel") and self.connectome_id != "none":
            raise ValueError("direct-voxel endpoint identities cannot declare a connectome")
        if self.model_family.endswith("fiber") and self.connectome_id == "none":
            raise ValueError("normative-fiber endpoint identities require a connectome")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def identifier(self) -> str:
        return f"endpoint_{canonical_hash(self.as_dict(), length=20)}"


@dataclass(frozen=True, order=True)
class TaskKey:
    """Stable identity for one execution stage of an endpoint model."""

    endpoint_id: str
    stage: str
    branch: str = "none"
    parameter_identity: str = "none"

    def __post_init__(self) -> None:
        for field in ("endpoint_id", "stage", "branch", "parameter_identity"):
            object.__setattr__(self, field, _token(getattr(self, field), field))

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def identifier(self) -> str:
        return f"task_{canonical_hash(self.as_dict(), length=20)}"


@dataclass(frozen=True, order=True)
class FinalModelKey:
    """Stable identity for the unique realized final model of an endpoint."""

    endpoint_id: str
    final_branch: str
    selected_tau: float
    selected_coverage: int
    estimator: str

    def __post_init__(self) -> None:
        for field in ("endpoint_id", "final_branch", "estimator"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(self, "selected_tau", float(self.selected_tau))
        object.__setattr__(self, "selected_coverage", int(self.selected_coverage))
        if not math.isfinite(self.selected_tau) or self.selected_tau <= 0:
            raise ValueError("selected_tau must be finite and positive")
        if self.selected_coverage < 1:
            raise ValueError("selected_coverage must be positive")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def identifier(self) -> str:
        return f"final_{canonical_hash(self.as_dict(), length=20)}"
