from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Any, Callable

from reverse_deepagent.browser.base import BrowserProvider
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities, metadata_has_secret_like_keys

BrowserProviderFactory = Callable[..., BrowserProvider]
BROWSER_PROVIDER_ENTRY_POINT_GROUP = "reverse_deepagent.browser_providers"


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
    """Side-effect-light browser provider registry.

    Loading entry points may import plugin Python modules, but must not start a
    browser, connect to CDP, download binaries, or invoke provider factories.
    """

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

    def load_entry_points(self, group: str = BROWSER_PROVIDER_ENTRY_POINT_GROUP) -> list[str]:
        """Load BrowserProvider registrations from Python package entry points."""

        loaded_provider_ids: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                plugin_value = entry_point.load()
            except Exception as exc:
                raise RuntimeError(f"Failed to load browser provider entry point {entry_point.name!r}: {exc}") from exc
            registrations = self._coerce_plugin_registrations(entry_point.name, plugin_value)
            for registration in registrations:
                self.register(registration)
                loaded_provider_ids.append(registration.provider_id)
        return loaded_provider_ids

    def resolve(self, provider_id: str) -> BrowserProviderRegistration:
        canonical = provider_id if provider_id in self._registrations else self._aliases.get(provider_id)
        if canonical is None:
            known = ", ".join(self.provider_ids())
            raise BrowserProviderRegistryError(f"Unsupported browser provider: {provider_id}. Known providers: {known}")
        return self._registrations[canonical]

    def is_registered(self, provider_id: str) -> bool:
        return provider_id in self._registrations or provider_id in self._aliases

    def create(self, provider_id: str, **kwargs: Any) -> BrowserProvider:
        registration = self.resolve(provider_id)
        return registration.factory(**kwargs)

    def provider_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_capabilities(self) -> list[BrowserProviderCapabilities]:
        return [self._registrations[key].capabilities for key in sorted(self._registrations)]

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self.list_capabilities()]

    def list_registration_metadata(self) -> list[dict[str, Any]]:
        """Return canonical provider metadata plus aliases without creating providers."""

        payloads: list[dict[str, Any]] = []
        for provider_id in sorted(self._registrations):
            registration = self._registrations[provider_id]
            payload = registration.capabilities.model_dump(mode="json")
            payload["aliases"] = list(registration.aliases)
            payload["keys"] = list(registration.keys)
            payloads.append(payload)
        return payloads

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[BrowserProviderRegistration]:
        if isinstance(value, BrowserProviderRegistration):
            return [value]
        if callable(value):
            return BrowserProviderRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, BrowserProviderRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "Browser provider entry point "
            f"{entry_point_name!r} must return a BrowserProviderRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


def playwright_chromium_browser_provider_registration() -> BrowserProviderRegistration:
    from reverse_deepagent.browser.providers import PlaywrightChromiumConfig, PlaywrightChromiumProvider

    default_provider = PlaywrightChromiumProvider()
    return BrowserProviderRegistration(
        provider_id="playwright-chromium",
        aliases=("playwright", "chromium"),
        capabilities=default_provider.describe(),
        factory=lambda **kwargs: PlaywrightChromiumProvider(config=_playwright_chromium_config(PlaywrightChromiumConfig, kwargs)),
    )


def cloakbrowser_browser_provider_registration() -> BrowserProviderRegistration:
    from reverse_deepagent.browser.providers import CloakBrowserConfig, CloakBrowserProvider

    default_provider = CloakBrowserProvider()
    return BrowserProviderRegistration(
        provider_id="cloakbrowser",
        aliases=("cloak", "cloak-browser"),
        capabilities=default_provider.describe(),
        factory=lambda **kwargs: CloakBrowserProvider(config=_cloakbrowser_config(CloakBrowserConfig, kwargs)),
    )


def remote_cdp_browser_provider_registration() -> BrowserProviderRegistration:
    from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider

    default_provider = RemoteCDPProvider()
    return BrowserProviderRegistration(
        provider_id="remote-cdp",
        aliases=("chrome-cdp-provider", "cdp-provider"),
        capabilities=default_provider.describe(),
        factory=lambda **kwargs: RemoteCDPProvider(config=_remote_cdp_config(RemoteCDPConfig, kwargs)),
    )


def build_default_browser_provider_registry(*, load_entry_points: bool = True) -> BrowserProviderRegistry:
    registry = BrowserProviderRegistry()
    registry.register(cloakbrowser_browser_provider_registration())
    registry.register(playwright_chromium_browser_provider_registration())
    registry.register(remote_cdp_browser_provider_registration())
    if load_entry_points:
        registry.load_entry_points()
    return registry


def _playwright_chromium_config(config_cls: type[Any], kwargs: dict[str, Any]) -> Any:
    browser_headless = kwargs.get("browser_headless")
    return config_cls(
        headless=True if browser_headless is None else bool(browser_headless),
        profile_dir=kwargs.get("browser_profile_dir"),
        browser_url=kwargs.get("browser_url"),
        executable_path=kwargs.get("browser_executable_path"),
        args=kwargs.get("browser_args") or [],
        launch_timeout=float(kwargs.get("browser_launch_timeout") or 30.0),
        navigation_timeout=float(kwargs.get("browser_navigation_timeout") or 30.0),
    )


def _cloakbrowser_config(config_cls: type[Any], kwargs: dict[str, Any]) -> Any:
    browser_headless = kwargs.get("browser_headless")
    browser_humanize = kwargs.get("browser_humanize")
    return config_cls(
        headless=False if browser_headless is None else bool(browser_headless),
        humanize=True if browser_humanize is None else bool(browser_humanize),
        profile_dir=kwargs.get("browser_profile_dir"),
        browser_url=kwargs.get("browser_url") or kwargs.get("cdp_browser_url"),
        proxy=kwargs.get("browser_proxy"),
        geoip=bool(kwargs.get("browser_geoip", False)),
        locale=kwargs.get("browser_locale"),
        timezone=kwargs.get("browser_timezone"),
        args=kwargs.get("browser_args") or [],
        launch_timeout=float(kwargs.get("browser_launch_timeout") or 45.0),
    )


def _remote_cdp_config(config_cls: type[Any], kwargs: dict[str, Any]) -> Any:
    return config_cls(
        browser_url=kwargs.get("browser_url") or kwargs.get("cdp_browser_url") or "http://127.0.0.1:9222",
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") or 0.5),
    )


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=group)
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        selected = entry_points.get(group, [])
    return list(selected)
