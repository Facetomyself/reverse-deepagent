from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reverse_deepagent.browser.base import BrowserPageRef, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.registry import BrowserProviderRegistration

FIXTURE_BROWSER_PROVIDER_ID = "fixture-browser"
FIXTURE_BROWSER_PROVIDER_ALIASES = ("fixture", "ci-browser-fixture")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class FixtureBrowserProviderConfig:
    """Non-secret config for the functional in-memory fixture provider."""

    default_url: str = "about:blank"
    title: str = "Fixture Browser"
    html: str = "<html><head><title>Fixture Browser</title></head><body>fixture-browser</body></html>"

    def summary(self) -> dict[str, Any]:
        return {
            "default_url": self.default_url,
            "title": self.title,
            "html_length": len(self.html),
            "runtime": "in-memory-fixture",
        }


class FixtureBrowserPage:
    """Provider-neutral synthetic page used by the fixture BrowserProvider."""

    def __init__(self, *, url: str, title: str, html: str) -> None:
        self._url = url
        self._title = title
        self._html = html
        self._evaluations: list[str] = []

    @property
    def url(self) -> str:
        return self._url

    def goto(self, url: str, timeout: float | None = None) -> None:
        self._url = url

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._html

    def evaluate(self, expression: str) -> Any:
        self._evaluations.append(expression)
        if expression in {"location.href", "window.location.href"}:
            return self._url
        if expression in {"document.title", "window.document.title"}:
            return self._title
        return {
            "provider_id": FIXTURE_BROWSER_PROVIDER_ID,
            "expression": expression,
            "evaluation_count": len(self._evaluations),
        }

    def screenshot(self, path: str | None = None) -> bytes | None:
        payload = b"fixture-browser-screenshot"
        if path:
            with open(path, "wb") as file:
                file.write(payload)
            return None
        return payload

    def cdp_session(self) -> None:
        return None


class FixtureBrowserSession:
    """Minimal in-memory BrowserSession for plugin and matrix smoke tests."""

    provider_id = FIXTURE_BROWSER_PROVIDER_ID

    def __init__(self, config: FixtureBrowserProviderConfig) -> None:
        self.config = config
        self.closed = False
        self._page = FixtureBrowserPage(url=config.default_url, title=config.title, html=config.html)

    def list_pages(self) -> list[BrowserPageRef]:
        return [
            BrowserPageRef(
                page_id="fixture-page-0",
                url=self._page.url,
                title=self._page.title(),
                selected=True,
                metadata={"provider_id": self.provider_id, "fixture": True},
            )
        ]

    def new_page(self, url: str | None = None) -> FixtureBrowserPage:
        self._page = FixtureBrowserPage(url=url or self.config.default_url, title=self.config.title, html=self.config.html)
        return self._page

    def get_active_page(self) -> FixtureBrowserPage:
        return self._page

    def close(self) -> None:
        self.closed = True


class FixtureBrowserProvider:
    """Functional external BrowserProvider plugin for CI / contract tests."""

    def __init__(self, config: FixtureBrowserProviderConfig | None = None) -> None:
        self.config = config or FixtureBrowserProviderConfig()
        self._sessions: list[FixtureBrowserSession] = []

    def describe(self) -> BrowserProviderCapabilities:
        return fixture_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        session = FixtureBrowserSession(self.config)
        self._sessions.append(session)
        return session

    def connect(self) -> BrowserSession:
        session = FixtureBrowserSession(self.config)
        self._sessions.append(session)
        return session

    def stop(self) -> None:
        for session in self._sessions:
            session.close()
        self._sessions.clear()

    def is_available(self) -> bool:
        return True


def fixture_browser_provider_capabilities(
    config: FixtureBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret provider metadata."""

    config = config or FixtureBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=FIXTURE_BROWSER_PROVIDER_ID,
        display_name="Fixture BrowserProvider",
        engine="synthetic",
        transport="in-memory-fixture",
        target_platforms=["web"],
        supports_launch=True,
        supports_connect=True,
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
        managed_browser=True,
        notes=[
            "functional in-memory provider for CI and plugin contract tests",
            "does not launch a real browser, expose CDP, or provide stealth/fingerprint behavior",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "fixture-only",
            "health_check_mode": "in-memory-contract-smoke",
            "profile_lifecycle": "ephemeral-in-memory",
            "proxy_policy": "not-supported",
            "extension_policy": "not-supported",
            "humanize_policy": "not-supported",
            "session_recovery": "new-in-memory-session",
            "intended_use": "ci-contract-fixture-only",
            "side_effect_boundary": "metadata-listing-does-not-call-factory; start-and-connect-are-explicit-in-memory-only",
        },
    )


def create_fixture_browser_provider(**kwargs: Any) -> FixtureBrowserProvider:
    """Factory used by BrowserProviderRegistry after explicit provider creation."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    config = FixtureBrowserProviderConfig(
        default_url=str(kwargs.get("default_url") or kwargs.get("browser_url") or "about:blank"),
        title=str(kwargs.get("title") or "Fixture Browser"),
        html=str(
            kwargs.get("html")
            or "<html><head><title>Fixture Browser</title></head><body>fixture-browser</body></html>"
        ),
    )
    return FixtureBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return the functional fixture BrowserProvider registration."""

    return BrowserProviderRegistration(
        provider_id=FIXTURE_BROWSER_PROVIDER_ID,
        aliases=FIXTURE_BROWSER_PROVIDER_ALIASES,
        capabilities=fixture_browser_provider_capabilities(),
        factory=create_fixture_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for plugin contract tests."""

    return _FACTORY_INVOCATION_COUNT
