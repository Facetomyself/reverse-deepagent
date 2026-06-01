from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider
from reverse_deepagent.browser.registry import BrowserProviderRegistration

HOSTED_CDP_REFERENCE_BROWSER_PROVIDER_ID = "hosted-cdp-reference"
HOSTED_CDP_REFERENCE_BROWSER_PROVIDER_ALIASES = (
    "hosted-cdp-ref",
    "browser-service-reference",
    "remote-browser-service-reference",
)
_SUPPORTED_ALLOCATION_MODES = {"explicit-endpoint", "in-memory-allocation"}
_FACTORY_INVOCATION_COUNT = 0
_ALLOCATION_EVENTS: list[dict[str, Any]] = []


@dataclass(frozen=True, slots=True)
class HostedCDPReferenceBrowserProviderConfig:
    """Non-secret config for the hosted CDP reference provider."""

    display_name: str = "Hosted CDP Reference BrowserProvider"
    browser_url: str | None = None
    allocated_browser_url: str | None = None
    service_base_url: str | None = None
    tenant_label: str | None = None
    session_id: str | None = None
    allocation_mode: str = "explicit-endpoint"
    release_on_stop: bool = True
    access_material_configured: bool = False
    connect_timeout: float = 5.0
    navigation_wait: float = 0.5

    def __post_init__(self) -> None:
        if self.allocation_mode not in _SUPPORTED_ALLOCATION_MODES:
            supported = ", ".join(sorted(_SUPPORTED_ALLOCATION_MODES))
            raise ValueError(f"Unsupported hosted CDP reference allocation_mode={self.allocation_mode!r}; expected one of: {supported}")

    def endpoint_for_connect(self) -> str | None:
        return self.browser_url or self.allocated_browser_url

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "browser_url": _redact_url(self.browser_url) if self.browser_url else None,
            "allocated_browser_url": _redact_url(self.allocated_browser_url) if self.allocated_browser_url else None,
            "service_base_url": _redact_url(self.service_base_url) if self.service_base_url else None,
            "tenant_label": self.tenant_label,
            "session_id": _redact_identifier(self.session_id) if self.session_id else None,
            "allocation_mode": self.allocation_mode,
            "release_on_stop": self.release_on_stop,
            "access_material_configured": self.access_material_configured,
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
        }


@dataclass(slots=True)
class _ReferenceAllocation:
    session_id: str
    browser_url: str
    owned: bool
    released: bool = False

    def safe_summary(self) -> dict[str, Any]:
        return {
            "session_id": _redact_identifier(self.session_id),
            "browser_url": _redact_url(self.browser_url),
            "owned": self.owned,
            "released": self.released,
        }


class HostedCDPReferenceBrowserProvider:
    """Reference hosted CDP BrowserProvider with allocation / attach / release semantics.

    The provider intentionally keeps the allocator local and deterministic. Real
    vendor integrations can replace `_allocate()` and `_release()` while keeping
    the BrowserProvider contract, metadata safety boundary, and idempotent stop
    behavior intact.
    """

    def __init__(self, config: HostedCDPReferenceBrowserProviderConfig | None = None) -> None:
        self.config = config or HostedCDPReferenceBrowserProviderConfig()
        self._delegate_provider: RemoteCDPProvider | None = None
        self._allocation: _ReferenceAllocation | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return hosted_cdp_reference_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        allocation = self._allocation or self._allocate()
        self._allocation = allocation
        return self._attach(allocation.browser_url, action="start")

    def connect(self) -> BrowserSession:
        if self._allocation is not None:
            return self._attach(self._allocation.browser_url, action="connect-owned-allocation")
        endpoint = self.config.endpoint_for_connect()
        if not endpoint:
            raise BrowserProviderUnavailableError(
                "Hosted CDP reference provider requires browser_url, cdp_browser_url, or allocated_browser_url. "
                "Use start() with allocation_mode='in-memory-allocation' and an explicit allocated_browser_url, "
                "or pass an already allocated hosted CDP endpoint for connect()."
            )
        _record_event(
            "attach_existing",
            session_id=self.config.session_id,
            browser_url=endpoint,
            owned=False,
            allocation_mode=self.config.allocation_mode,
        )
        return self._attach(endpoint, action="connect")

    def stop(self) -> None:
        if self._delegate_provider is not None:
            self._delegate_provider.stop()
            self._delegate_provider = None
        should_release_owned = (
            self._allocation is not None
            and self._allocation.owned
            and self.config.release_on_stop
            and not self._allocation.released
        )
        if should_release_owned:
            self._release(self._allocation)

    def is_available(self) -> bool:
        return bool(self.config.endpoint_for_connect())

    def allocation_summary(self) -> dict[str, Any] | None:
        if self._allocation is None:
            return None
        return self._allocation.safe_summary()

    def _allocate(self) -> _ReferenceAllocation:
        endpoint = self.config.endpoint_for_connect()
        if self.config.allocation_mode == "explicit-endpoint":
            if not endpoint:
                raise BrowserProviderUnavailableError(
                    "Hosted CDP reference explicit-endpoint mode requires browser_url / cdp_browser_url. "
                    "It does not allocate remote sessions during metadata or availability checks."
                )
            allocation = _ReferenceAllocation(
                session_id=self.config.session_id or "explicit-endpoint",
                browser_url=endpoint,
                owned=False,
            )
            _record_event(
                "allocate_reference",
                session_id=allocation.session_id,
                browser_url=allocation.browser_url,
                owned=allocation.owned,
                allocation_mode=self.config.allocation_mode,
            )
            return allocation

        endpoint = self.config.allocated_browser_url or self.config.browser_url
        if not endpoint:
            raise BrowserProviderUnavailableError(
                "Hosted CDP reference in-memory-allocation mode requires allocated_browser_url. "
                "Replace the reference allocator with a vendor allocator before production use."
            )
        allocation = _ReferenceAllocation(
            session_id=self.config.session_id or f"reference-session-{len(_ALLOCATION_EVENTS) + 1}",
            browser_url=endpoint,
            owned=True,
        )
        _record_event(
            "allocate_reference",
            session_id=allocation.session_id,
            browser_url=allocation.browser_url,
            owned=allocation.owned,
            allocation_mode=self.config.allocation_mode,
        )
        return allocation

    def _attach(self, browser_url: str, *, action: str) -> BrowserSession:
        provider = RemoteCDPProvider(
            RemoteCDPConfig(
                browser_url=browser_url,
                connect_timeout=self.config.connect_timeout,
                navigation_wait=self.config.navigation_wait,
            )
        )
        session = provider.connect()
        self._delegate_provider = provider
        _record_event(
            action,
            session_id=self._allocation.session_id if self._allocation else self.config.session_id,
            browser_url=browser_url,
            owned=bool(self._allocation and self._allocation.owned),
            allocation_mode=self.config.allocation_mode,
        )
        return session

    def _release(self, allocation: _ReferenceAllocation) -> None:
        allocation.released = True
        _record_event(
            "release_reference",
            session_id=allocation.session_id,
            browser_url=allocation.browser_url,
            owned=allocation.owned,
            allocation_mode=self.config.allocation_mode,
        )


def hosted_cdp_reference_browser_provider_capabilities(
    config: HostedCDPReferenceBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret hosted CDP reference metadata."""

    config = config or HostedCDPReferenceBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=HOSTED_CDP_REFERENCE_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine="chromium-compatible",
        transport="hosted-cdp-reference",
        target_platforms=["web"],
        supports_launch=True,
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
        managed_browser=True,
        notes=[
            "reference hosted CDP provider package for allocation, attach, and release lifecycle tests",
            "metadata loading does not allocate hosted sessions, probe endpoints, or call provider factories",
            "start mode models hosted session allocation before delegating to RemoteCDPProvider",
            "connect mode attaches to an explicitly supplied endpoint or session",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "review-required",
            "health_check_mode": "explicit-reference-allocation-and-cdp-contract-smoke",
            "profile_lifecycle": "external-service-session-owned",
            "proxy_policy": "external-service-owned-redacted",
            "extension_policy": "external-service-owned",
            "humanize_policy": "provider-specific-not-declared",
            "session_recovery": "session-id-reattach-or-endpoint-connect",
            "intended_use": "reference-implementation-for-hosted-cdp-provider-packages",
            "side_effect_boundary": "metadata-listing-does-not-allocate; start-and-connect-are-explicit; stop-releases-owned-allocation",
        },
    )


def create_hosted_cdp_reference_browser_provider(**kwargs: Any) -> HostedCDPReferenceBrowserProvider:
    """Factory used only after explicit BrowserProviderRegistry.create(...)."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    config = HostedCDPReferenceBrowserProviderConfig(
        display_name=str(kwargs.get("display_name") or "Hosted CDP Reference BrowserProvider"),
        browser_url=kwargs.get("browser_url") or kwargs.get("cdp_browser_url"),
        allocated_browser_url=kwargs.get("allocated_browser_url"),
        service_base_url=kwargs.get("service_base_url"),
        tenant_label=kwargs.get("tenant_label"),
        session_id=kwargs.get("session_id"),
        allocation_mode=str(kwargs.get("allocation_mode") or "explicit-endpoint"),
        release_on_stop=bool(kwargs.get("release_on_stop", True)),
        access_material_configured=bool(kwargs.get("access_material_configured", False)),
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") or 0.5),
    )
    return HostedCDPReferenceBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return hosted CDP reference BrowserProvider registration without runtime side effects."""

    return BrowserProviderRegistration(
        provider_id=HOSTED_CDP_REFERENCE_BROWSER_PROVIDER_ID,
        aliases=HOSTED_CDP_REFERENCE_BROWSER_PROVIDER_ALIASES,
        capabilities=hosted_cdp_reference_browser_provider_capabilities(),
        factory=create_hosted_cdp_reference_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for plugin contract tests."""

    return _FACTORY_INVOCATION_COUNT


def allocation_event_log() -> list[dict[str, Any]]:
    """Return a copy of reference allocation / attach / release events for tests."""

    return [dict(item) for item in _ALLOCATION_EVENTS]


def reset_reference_state() -> None:
    """Reset test-observable module state."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT = 0
    _ALLOCATION_EVENTS.clear()


def _record_event(
    event: str,
    *,
    session_id: str | None,
    browser_url: str,
    owned: bool,
    allocation_mode: str,
) -> None:
    _ALLOCATION_EVENTS.append(
        {
            "event": event,
            "session_id": _redact_identifier(session_id) if session_id else None,
            "browser_url": _redact_url(browser_url),
            "owned": owned,
            "allocation_mode": allocation_mode,
        }
    )


def _redact_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _redact_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    safe_query = urlencode({"query": "<redacted>"}) if parsed.query else ""
    return urlunsplit((parsed.scheme, netloc, parsed.path, safe_query, ""))
