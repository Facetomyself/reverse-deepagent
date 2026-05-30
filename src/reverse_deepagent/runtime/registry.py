from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Any, Callable

from reverse_deepagent.runtime.base import ReverseRuntime, RuntimeBackendCapabilities

RuntimeBackendFactory = Callable[..., ReverseRuntime]
RUNTIME_BACKEND_ENTRY_POINT_GROUP = "reverse_deepagent.runtime_backends"


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
        if registration.capabilities.backend_id != canonical:
            raise ValueError(
                "Runtime backend capability id mismatch: "
                f"registration={canonical!r}, capabilities={registration.capabilities.backend_id!r}"
            )
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise ValueError(f"Runtime backend key already registered: {key}")
        self._registrations[canonical] = registration
        for alias in registration.aliases:
            self._aliases[alias] = canonical

    def load_entry_points(self, group: str = RUNTIME_BACKEND_ENTRY_POINT_GROUP) -> list[str]:
        """Load runtime backend registrations from Python package entry points.

        Entry-point plugins are the migration seam for moving optional backends
        such as legacy MCP out of the core package. Loading an entry point may
        import plugin Python code, but it must only return registration metadata
        and factories; factories are not invoked here, so listing metadata stays
        free of browser / MCP / device side effects.
        """

        loaded_backend_ids: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                plugin_value = entry_point.load()
            except Exception as exc:
                raise RuntimeError(f"Failed to load runtime backend entry point {entry_point.name!r}: {exc}") from exc
            registrations = self._coerce_plugin_registrations(entry_point.name, plugin_value)
            for registration in registrations:
                self.register(registration)
                loaded_backend_ids.append(registration.backend_id)
        return loaded_backend_ids

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

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[RuntimeBackendRegistration]:
        if isinstance(value, RuntimeBackendRegistration):
            return [value]
        if callable(value):
            return RuntimeBackendRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, RuntimeBackendRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "Runtime backend entry point "
            f"{entry_point_name!r} must return a RuntimeBackendRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=group)
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        selected = entry_points.get(group, [])
    return list(selected)
