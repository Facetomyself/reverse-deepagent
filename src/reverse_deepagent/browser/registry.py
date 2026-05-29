from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from reverse_deepagent.browser.base import BrowserProvider
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities, metadata_has_secret_like_keys

BrowserProviderFactory = Callable[..., BrowserProvider]


class BrowserProviderRegistryError(ValueError):
    """Raised when browser provider registry operations fail."""


@dataclass(frozen=True, slots=True)
class BrowserProviderRegistration:
    """Factory registration for one browser provider."""

    provider_id: str
    capabilities: BrowserProviderCapabilities
    factory: BrowserProviderFactory
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provider_id != self.capabilities.provider_id:
            raise BrowserProviderRegistryError(
                f"Provider id {self.provider_id!r} does not match capabilities id {self.capabilities.provider_id!r}"
            )
        if metadata_has_secret_like_keys(self.capabilities.model_dump(mode="json")):
            raise BrowserProviderRegistryError(f"Provider capabilities for {self.provider_id!r} contain secret-like metadata keys")

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.provider_id, *self.aliases)


class BrowserProviderRegistry:
    """Side-effect-free browser provider registry."""

    def __init__(self) -> None:
        self._registrations: dict[str, BrowserProviderRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: BrowserProviderRegistration) -> None:
        canonical = registration.provider_id
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise BrowserProviderRegistryError(f"Browser provider key already registered: {key}")
        self._registrations[canonical] = registration
        for alias in registration.aliases:
            self._aliases[alias] = canonical

    def resolve(self, provider_id: str) -> BrowserProviderRegistration:
        canonical = provider_id if provider_id in self._registrations else self._aliases.get(provider_id)
        if canonical is None:
            known = ", ".join(self.provider_ids())
            raise BrowserProviderRegistryError(f"Unsupported browser provider: {provider_id}. Known providers: {known}")
        return self._registrations[canonical]

    def create(self, provider_id: str, **kwargs: Any) -> BrowserProvider:
        registration = self.resolve(provider_id)
        return registration.factory(**kwargs)

    def provider_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_capabilities(self) -> list[BrowserProviderCapabilities]:
        return [self._registrations[key].capabilities for key in sorted(self._registrations)]

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.list_capabilities()]
