from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.registry import BrowserProviderRegistration

TEMPLATE_BROWSER_PROVIDER_ID = "template-browser"
TEMPLATE_BROWSER_PROVIDER_ALIASES = ("browser-template", "custom-browser-template")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class TemplateBrowserProviderConfig:
    """Non-secret config summary for a copied BrowserProvider template."""

    display_name: str = "Template BrowserProvider"
    engine: str = "chromium-compatible"
    transport: str = "template"
    launch_mode: str = "replace-me"

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "engine": self.engine,
            "transport": self.transport,
            "launch_mode": self.launch_mode,
        }


class TemplateBrowserProvider:
    """Copy-and-replace BrowserProvider skeleton.

    The template is metadata-complete but runtime-unavailable by design. Real
    plugins should replace `start()` / `connect()` with SDK-specific lifecycle
    code and return a provider-neutral BrowserSession adapter.
    """

    def __init__(self, config: TemplateBrowserProviderConfig | None = None) -> None:
        self.config = config or TemplateBrowserProviderConfig()

    def describe(self) -> BrowserProviderCapabilities:
        return template_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        raise BrowserProviderUnavailableError(
            "TemplateBrowserProvider.start() is a scaffold; replace it with real browser launch code."
        )

    def connect(self) -> BrowserSession:
        raise BrowserProviderUnavailableError(
            "TemplateBrowserProvider.connect() is a scaffold; replace it with real browser attach code."
        )

    def stop(self) -> None:
        return None

    def is_available(self) -> bool:
        return False


def template_browser_provider_capabilities(
    config: TemplateBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret provider metadata."""

    config = config or TemplateBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=TEMPLATE_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine=config.engine,
        transport=config.transport,
        target_platforms=["web"],
        supports_launch=False,
        supports_connect=False,
        supports_persistent_context=False,
        supports_cdp=False,
        supports_playwright_api=False,
        supports_proxy=False,
        supports_stealth=False,
        supports_humanize=False,
        supports_extensions=False,
        supports_mobile_emulation=False,
        supports_network_events=False,
        supports_response_body=False,
        supports_request_initiator=False,
        supports_script_source=False,
        supports_websocket_frames=False,
        supports_breakpoints=False,
        supports_runtime_eval=False,
        managed_browser=False,
        notes=[
            "template package only; replace lifecycle methods before using in production",
            "metadata loading must not invoke provider factory or start a browser",
        ],
        config=config.summary(),
    )


def create_template_browser_provider(**kwargs: Any) -> TemplateBrowserProvider:
    """Factory used by the BrowserProviderRegistry.

    Registry metadata listing must not call this function. Tests intentionally
    track invocations so template authors can see the side-effect boundary.
    """

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    config = TemplateBrowserProviderConfig(
        display_name=kwargs.get("display_name", "Template BrowserProvider"),
        engine=kwargs.get("engine", "chromium-compatible"),
        transport=kwargs.get("transport", "template"),
        launch_mode=kwargs.get("launch_mode", "replace-me"),
    )
    return TemplateBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return the template BrowserProvider registration without side effects."""

    return BrowserProviderRegistration(
        provider_id=TEMPLATE_BROWSER_PROVIDER_ID,
        aliases=TEMPLATE_BROWSER_PROVIDER_ALIASES,
        capabilities=template_browser_provider_capabilities(),
        factory=create_template_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for template contract tests."""

    return _FACTORY_INVOCATION_COUNT
