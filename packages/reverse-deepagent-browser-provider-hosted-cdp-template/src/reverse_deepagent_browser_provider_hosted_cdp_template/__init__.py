from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider
from reverse_deepagent.browser.registry import BrowserProviderRegistration

HOSTED_CDP_BROWSER_PROVIDER_ID = "hosted-cdp-template"
HOSTED_CDP_BROWSER_PROVIDER_ALIASES = ("hosted-cdp", "browser-service-template", "remote-browser-service")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class HostedCDPBrowserProviderConfig:
    """Non-secret config for a hosted CDP BrowserProvider template."""

    display_name: str = "Hosted CDP BrowserProvider Template"
    browser_url: str | None = None
    service_base_url: str | None = None
    tenant_label: str | None = None
    access_material_configured: bool = False
    connect_timeout: float = 5.0
    navigation_wait: float = 0.5

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "browser_url": _redact_url(self.browser_url) if self.browser_url else None,
            "service_base_url": _redact_url(self.service_base_url) if self.service_base_url else None,
            "tenant_label": self.tenant_label,
            "access_material_configured": self.access_material_configured,
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
        }


class HostedCDPBrowserProvider:
    """Hosted CDP provider scaffold backed by the core RemoteCDP adapter.

    The template proves the plugin seam for hosted browser services while keeping
    vendor allocation, account management, and access material out of core.
    """

    def __init__(self, config: HostedCDPBrowserProviderConfig | None = None) -> None:
        self.config = config or HostedCDPBrowserProviderConfig()
        self._delegate_provider: RemoteCDPProvider | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return hosted_cdp_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        return self.connect()

    def connect(self) -> BrowserSession:
        provider = self._delegate()
        session = provider.connect()
        self._delegate_provider = provider
        return session

    def stop(self) -> None:
        if self._delegate_provider is not None:
            self._delegate_provider.stop()
            self._delegate_provider = None

    def is_available(self) -> bool:
        if not self.config.browser_url:
            return False
        return self._delegate().is_available()

    def _delegate(self) -> RemoteCDPProvider:
        if not self.config.browser_url:
            raise BrowserProviderUnavailableError(
                "Hosted CDP template requires browser_url / cdp_browser_url. Allocate a hosted browser session "
                "with your vendor first, then pass its redacted-safe CDP endpoint at runtime."
            )
        return RemoteCDPProvider(
            RemoteCDPConfig(
                browser_url=self.config.browser_url,
                connect_timeout=self.config.connect_timeout,
                navigation_wait=self.config.navigation_wait,
            )
        )


def hosted_cdp_browser_provider_capabilities(
    config: HostedCDPBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret hosted CDP provider metadata."""

    config = config or HostedCDPBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=HOSTED_CDP_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine="chromium-compatible",
        transport="hosted-cdp",
        target_platforms=["web"],
        supports_launch=False,
        supports_connect=True,
        supports_persistent_context=True,
        supports_cdp=True,
        supports_playwright_api=False,
        supports_proxy=True,
        supports_stealth=True,
        supports_humanize=False,
        supports_extensions=True,
        supports_mobile_emulation=True,
        supports_network_events=False,
        supports_response_body=True,
        supports_request_initiator=True,
        supports_script_source=True,
        supports_websocket_frames=True,
        supports_breakpoints=True,
        supports_runtime_eval=True,
        managed_browser=False,
        notes=[
            "hosted CDP provider template for vendor browser services",
            "metadata loading does not allocate hosted sessions or probe endpoints",
            "connect mode delegates to RemoteCDPProvider when browser_url is explicitly configured",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "review-required",
            "health_check_mode": "explicit-endpoint-probe-after-vendor-session-allocation",
            "profile_lifecycle": "hosted-service-owned",
            "proxy_policy": "hosted-service-owned-redacted",
            "extension_policy": "hosted-service-owned",
            "humanize_policy": "vendor-specific-not-declared",
            "session_recovery": "connect-existing-hosted-cdp-endpoint",
            "intended_use": "hosted-browser-service-plugin-template",
            "side_effect_boundary": "registration-and-metadata-matrix-are-side-effect-free; endpoint-probe-and-connect-are-explicit",
        },
    )


def create_hosted_cdp_browser_provider(**kwargs: Any) -> HostedCDPBrowserProvider:
    """Factory used only after explicit BrowserProviderRegistry.create(...)."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    config = HostedCDPBrowserProviderConfig(
        display_name=str(kwargs.get("display_name") or "Hosted CDP BrowserProvider Template"),
        browser_url=kwargs.get("browser_url") or kwargs.get("cdp_browser_url"),
        service_base_url=kwargs.get("service_base_url"),
        tenant_label=kwargs.get("tenant_label"),
        access_material_configured=bool(kwargs.get("access_material_configured", False)),
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") or 0.5),
    )
    return HostedCDPBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return hosted CDP BrowserProvider registration without runtime side effects."""

    return BrowserProviderRegistration(
        provider_id=HOSTED_CDP_BROWSER_PROVIDER_ID,
        aliases=HOSTED_CDP_BROWSER_PROVIDER_ALIASES,
        capabilities=hosted_cdp_browser_provider_capabilities(),
        factory=create_hosted_cdp_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for plugin contract tests."""

    return _FACTORY_INVOCATION_COUNT


def _redact_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
