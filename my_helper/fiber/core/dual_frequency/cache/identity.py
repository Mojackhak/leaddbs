"""Immutable scientific identities for reusable dual-frequency artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from ..contracts.identity import canonical_hash


class CacheIdentityError(ValueError):
    """Raised when a scientific cache identity is incomplete or malformed."""


def _token(value: str, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise CacheIdentityError(f"{field} must be nonempty")
    return token


def _sha256(value: str, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CacheIdentityError(f"{field} must be a 64-character SHA-256 digest")
    return digest


def _named_hashes(
    values: Iterable[tuple[str, str]],
    field: str,
) -> tuple[tuple[str, str], ...]:
    try:
        normalized = tuple(
            sorted(
                (
                    (_token(name, f"{field} name"), _sha256(digest, f"{field} hash"))
                    for name, digest in values
                ),
                key=lambda item: item[0],
            )
        )
    except (TypeError, ValueError) as exc:
        raise CacheIdentityError(f"{field} entries must be name/hash pairs") from exc
    if not normalized:
        raise CacheIdentityError(f"{field} must contain at least one named hash")
    names = tuple(name for name, _digest in normalized)
    if len(set(names)) != len(names):
        raise CacheIdentityError(f"{field} names must be unique")
    return normalized


@dataclass(frozen=True, order=True, slots=True)
class ScientificCacheKey:
    """Scientific identity that intentionally excludes execution and endpoint state.

    Aggregate hashes bind geometry, stimulation, component/frequency resolution,
    transforms, and connectome/feature content. Scientific parameter hashes are
    named so independent algorithms cannot accidentally exchange cache entries.
    Scale, endpoint, run, workers, retries, and task order are deliberately absent.
    """

    geometry_hash: str
    stimulation_hash: str
    component_frequency_hash: str
    transform_hash: str
    connectome_feature_hash: str
    backend_name: str
    backend_version: str
    scientific_parameter_hashes: tuple[tuple[str, str], ...]
    schema_version: str = "scientific_cache_key_v1"

    def __post_init__(self) -> None:
        for field in (
            "geometry_hash",
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
            "connectome_feature_hash",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        for field in ("backend_name", "backend_version", "schema_version"):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(
            self,
            "scientific_parameter_hashes",
            _named_hashes(self.scientific_parameter_hashes, "scientific_parameter_hashes"),
        )

    def as_dict(self) -> dict[str, object]:
        """Return the complete canonical scientific identity payload."""

        return asdict(self)

    @property
    def digest(self) -> str:
        """Return the content-addressed directory identity."""

        return canonical_hash(self.as_dict())

    @classmethod
    def from_dict(cls, value: object) -> "ScientificCacheKey":
        """Reconstruct and validate a key from a persisted manifest payload."""

        if not isinstance(value, dict):
            raise CacheIdentityError("scientific cache key payload must be an object")
        expected = {
            "geometry_hash",
            "stimulation_hash",
            "component_frequency_hash",
            "transform_hash",
            "connectome_feature_hash",
            "backend_name",
            "backend_version",
            "scientific_parameter_hashes",
            "schema_version",
        }
        if set(value) != expected:
            raise CacheIdentityError("scientific cache key payload has unexpected fields")
        named_hashes = value["scientific_parameter_hashes"]
        if not isinstance(named_hashes, (list, tuple)):
            raise CacheIdentityError("scientific_parameter_hashes must be an array")
        try:
            pairs = tuple((item[0], item[1]) for item in named_hashes)
        except (IndexError, TypeError) as exc:
            raise CacheIdentityError(
                "scientific_parameter_hashes entries must be name/hash pairs"
            ) from exc
        if any(not isinstance(item, (list, tuple)) or len(item) != 2 for item in named_hashes):
            raise CacheIdentityError("scientific_parameter_hashes entries must be name/hash pairs")
        return cls(
            geometry_hash=value["geometry_hash"],
            stimulation_hash=value["stimulation_hash"],
            component_frequency_hash=value["component_frequency_hash"],
            transform_hash=value["transform_hash"],
            connectome_feature_hash=value["connectome_feature_hash"],
            backend_name=value["backend_name"],
            backend_version=value["backend_version"],
            scientific_parameter_hashes=pairs,
            schema_version=value["schema_version"],
        )


def sha256_stream(handle: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    """Hash an open binary stream from its current position."""

    digest = hashlib.sha256()
    while True:
        chunk = handle.read(chunk_size)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest of one file."""

    with Path(path).open("rb") as handle:
        return sha256_stream(handle, chunk_size=chunk_size)
