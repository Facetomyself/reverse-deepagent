from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime, RuntimeBackendCapabilities

RuntimeBackendFactory = Callable[..., ReverseRuntime]


@dataclass(frozen=True, slots=True)
class RuntimeBackendRegistration:
    """Factory registration for one runtime backend."""

    backend_id: str
    capabilities: RuntimeBackendCapabilities
    factory: RuntimeBackendFactory
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.backend_id, *self.aliases)


class RuntimeBackendRegistry:
    """Small runtime backend registry used by coordinator / CLI entrypoints."""

    def __init__(self) -> None:
        self._registrations: dict[str, RuntimeBackendRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: RuntimeBackendRegistration) -> None:
        canonical = registration.backend_id
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise ValueError(f"Runtime backend key already registered: {key}")
        self._registrations[canonical] = registration
        for alias in registration.aliases:
            self._aliases[alias] = canonical

    def resolve(self, backend_id: str) -> RuntimeBackendRegistration:
        canonical = backend_id if backend_id in self._registrations else self._aliases.get(backend_id)
        if canonical is None:
            known = ", ".join(self.backend_ids())
            raise ValueError(f"Unsupported runtime backend: {backend_id}. Known backends: {known}")
        return self._registrations[canonical]

    def create(self, backend_id: str, **kwargs: Any) -> ReverseRuntime:
        registration = self.resolve(backend_id)
        return registration.factory(**kwargs)

    def backend_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_capabilities(self) -> list[RuntimeBackendCapabilities]:
        return [self._registrations[key].capabilities for key in sorted(self._registrations)]

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.list_capabilities()]
