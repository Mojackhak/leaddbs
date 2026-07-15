"""Project-neutral service registry for planned workflow tasks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .executor import ServiceResult, TaskExecutionRequest


class RegistryError(ValueError):
    """Raised when service registration or lookup is invalid."""


ServiceCallable = Callable[["TaskExecutionRequest"], "ServiceResult"]


@dataclass(frozen=True)
class RegisteredService:
    """One named workflow service and its callable implementation."""

    service_id: str
    callable: ServiceCallable

    def __post_init__(self) -> None:
        if not str(self.service_id).strip():
            raise RegistryError("service_id must be nonempty")
        if not callable(self.callable):
            raise RegistryError("registered service must be callable")


class ServiceRegistry:
    """Thread-safe registry with explicit, immutable service identifiers."""

    def __init__(self, services: Iterable[RegisteredService] = ()) -> None:
        self._lock = RLock()
        self._services: dict[str, ServiceCallable] = {}
        for service in services:
            self.register(service.service_id, service.callable)

    def register(self, service_id: str, service: ServiceCallable) -> None:
        registration = RegisteredService(service_id, service)
        with self._lock:
            if registration.service_id in self._services:
                raise RegistryError(f"service {registration.service_id!r} is already registered")
            self._services[registration.service_id] = registration.callable

    def resolve(self, service_id: str) -> ServiceCallable:
        with self._lock:
            try:
                return self._services[service_id]
            except KeyError as exc:
                raise RegistryError(f"service {service_id!r} is not registered") from exc

    def require(self, service_ids: Iterable[str]) -> None:
        missing = sorted(set(service_ids) - set(self.service_ids))
        if missing:
            raise RegistryError(f"missing required workflow services: {missing}")

    @property
    def service_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._services))
