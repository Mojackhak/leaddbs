"""Resolve and validate contact allocation within one stimulation source."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any


class ContactFractionError(ValueError):
    """Raised when contact allocation is incomplete or internally invalid."""


def _polarity_groups(contacts: Sequence[Mapping[str, Any]]) -> dict[str, list[int]]:
    if not contacts:
        raise ContactFractionError("contacts must not be empty")
    groups = {"cathode": [], "anode": []}
    for index, contact in enumerate(contacts):
        polarity = str(contact.get("polarity", "")).lower()
        if polarity not in groups:
            raise ContactFractionError(f"invalid contact polarity: {polarity!r}")
        groups[polarity].append(index)
    for polarity, indices in groups.items():
        if not indices:
            raise ContactFractionError(f"source must contain at least one {polarity}")
    return groups


def _allocation_values(
    values: Sequence[float | None] | None,
    size: int,
    label: str,
) -> tuple[float | None, ...]:
    if values is None:
        return (None,) * size
    if len(values) != size:
        raise ContactFractionError(f"{label} length does not match contacts")
    normalized: list[float | None] = []
    for value in values:
        if value is None:
            normalized.append(None)
            continue
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ContactFractionError(f"{label} values must be positive and finite")
        normalized.append(number)
    present = [value is not None for value in normalized]
    if any(present) and not all(present):
        raise ContactFractionError(f"partial {label} is invalid")
    return tuple(normalized)


def resolve_contact_fractions(
    contacts: Sequence[Mapping[str, Any]],
    control_mode: str,
    *,
    observed_fractions: Sequence[float | None] | None = None,
    observed_currents: Sequence[float | None] | None = None,
) -> tuple[float, ...]:
    """Resolve final fractions aligned with ``contacts`` for one source."""
    mode = str(control_mode).lower()
    if mode not in {"voltage", "current"}:
        raise ContactFractionError(f"unsupported control mode: {control_mode!r}")
    groups = _polarity_groups(contacts)
    if observed_fractions is not None and observed_currents is not None:
        raise ContactFractionError("cannot provide both fractions and absolute currents")

    fractions = _allocation_values(observed_fractions, len(contacts), "allocation")
    currents = _allocation_values(observed_currents, len(contacts), "current allocation")

    if mode == "voltage":
        if any(value is not None and abs(value - 1.0) > 1e-9 for value in fractions):
            raise ContactFractionError("voltage contact fractions must equal 1.0")
        if any(value is not None for value in currents):
            raise ContactFractionError("voltage sources cannot use current allocation")
        return (1.0,) * len(contacts)

    if any(value is not None for value in fractions):
        resolved = tuple(float(value) for value in fractions if value is not None)
        candidate = tuple(
            {**contact, "fraction": resolved[index]}
            for index, contact in enumerate(contacts)
        )
        validate_resolved_contact_fractions(candidate, mode)
        return resolved

    resolved_values = [0.0] * len(contacts)
    for indices in groups.values():
        if any(currents[index] is not None for index in indices):
            total = sum(float(currents[index]) for index in indices if currents[index] is not None)
            for index in indices:
                resolved_values[index] = float(currents[index]) / total
        else:
            equal = 1.0 / len(indices)
            for index in indices:
                resolved_values[index] = equal
    return tuple(resolved_values)


def validate_resolved_contact_fractions(
    contacts: Sequence[Mapping[str, Any]],
    control_mode: str,
    *,
    tolerance: float = 1e-9,
) -> None:
    """Validate already resolved fractions in one serialized source."""
    mode = str(control_mode).lower()
    if mode not in {"voltage", "current"}:
        raise ContactFractionError(f"unsupported control mode: {control_mode!r}")
    groups = _polarity_groups(contacts)
    values: list[float] = []
    for contact in contacts:
        try:
            value = float(contact["fraction"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContactFractionError("contact fraction is missing or invalid") from exc
        if not math.isfinite(value) or value <= 0 or value > 1:
            raise ContactFractionError("contact fraction must be in (0, 1]")
        values.append(value)

    if mode == "voltage":
        if any(abs(value - 1.0) > tolerance for value in values):
            raise ContactFractionError("voltage contact fractions must equal 1.0")
        return

    for polarity, indices in groups.items():
        total = sum(values[index] for index in indices)
        if abs(total - 1.0) > tolerance:
            raise ContactFractionError(
                f"current {polarity} contact fractions must sum to 1.0"
            )
