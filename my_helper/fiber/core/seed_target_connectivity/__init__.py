"""Generic seed-target streamline connectivity statistics."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "BatchConnectivityConfig": ".models",
    "BatchConnectivityResult": ".models",
    "BatchValidationReport": ".models",
    "ConnectivityConfig": ".models",
    "ConnectivityRunResult": ".models",
    "ValidationReport": ".models",
    "compute_seed_target_batch": ".pipeline",
    "compute_seed_target_statistics": ".pipeline",
    "load_config": ".config",
    "resolve_config": ".config",
    "validate_batch": ".pipeline",
    "validate_inputs": ".pipeline",
}

__all__ = tuple(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    """Load the requested public symbol without importing unrelated pipelines."""

    try:
        module_name = _EXPORT_MODULES[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
