from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.session import PlaywrightBrowserSessionAdapter
from reverse_deepagent.schemas.common import SchemaBaseModel


class CloakBrowserConfig(SchemaBaseModel):
    """Configuration for the CloakBrowser BrowserProvider."""

    headless: bool = Field(default=False, description="Launch CloakBrowser in headless mode.")
    humanize: bool = Field(default=True, description="Enable CloakBrowser humanized interaction when supported.")
    profile_dir: str | None = Field(default=None, description="Optional persistent profile directory.")
    browser_url: str | None = Field(default=None, description="Optional existing CloakBrowser/cloakserve CDP browser URL for connect mode.")
    proxy: str | None = Field(default=None, description="Optional proxy URL; do not include this in public metadata if it contains credentials.")
    geoip: bool = Field(default=False, description="Let CloakBrowser derive timezone/locale from proxy IP when supported.")
    locale: str | None = Field(default=None, description="Optional locale, such as zh-CN.")
    timezone: str | None = Field(default=None, description="Optional timezone id, such as Asia/Shanghai.")
    args: list[str] = Field(default_factory=list, description="Extra launch args.")
    launch_timeout: float = Field(default=45.0, description="Launch timeout in seconds.")

    def safe_summary(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        if payload.get("browser_url"):
            payload["browser_url"] = _redact_url(str(payload["browser_url"]))
        if payload.get("proxy"):
            payload["proxy"] = "<configured>"
        return payload


class CloakBrowserProvider:
    """BrowserProvider backed by CloakBrowser's Playwright-compatible API."""

    provider_id = "cloakbrowser"

    def __init__(self, config: CloakBrowserConfig | None = None) -> None:
        self.config = config or CloakBrowserConfig()
        self._session: PlaywrightBrowserSessionAdapter | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id=self.provider_id,
            display_name="CloakBrowser",
            engine="chromium",
            transport="cloakbrowser-playwright",
            supports_launch=True,
            supports_connect=True,
            supports_persistent_context=True,
            supports_cdp=True,
            supports_playwright_api=True,
            supports_proxy=True,
            supports_stealth=True,
            supports_humanize=True,
            supports_extensions=True,
            supports_mobile_emulation=True,
            supports_network_events=True,
            supports_response_body=True,
            supports_request_initiator=True,
            supports_script_source=True,
            supports_websocket_frames=True,
            supports_breakpoints=True,
            supports_runtime_eval=True,
            managed_browser=True,
            notes=[
                "optional stealth browser provider",
                "downloads and uses CloakBrowser-managed Chromium binary when installed",
                "connect mode expects an existing CloakBrowser/cloakserve-compatible CDP endpoint",
                "binary must not be committed or redistributed by this repository",
            ],
            config=self.config.safe_summary(),
        )

    def start(self) -> PlaywrightBrowserSessionAdapter:
        module = self._load_cloakbrowser()
        common_kwargs = self._launch_kwargs()
        if self.config.profile_dir:
            launch_persistent_context = getattr(module, "launch_persistent_context", None)
            if not callable(launch_persistent_context):
                raise BrowserProviderUnavailableError("cloakbrowser.launch_persistent_context is unavailable")
            context = launch_persistent_context(str(Path(self.config.profile_dir).expanduser()), **common_kwargs)
            session = PlaywrightBrowserSessionAdapter(provider_id=self.provider_id, context=context)
        else:
            launch = getattr(module, "launch", None)
            if not callable(launch):
                raise BrowserProviderUnavailableError("cloakbrowser.launch is unavailable")
            browser = launch(**common_kwargs)
            context = browser.new_context()
            session = PlaywrightBrowserSessionAdapter(provider_id=self.provider_id, context=context, browser=browser)
        self._session = session
        return session

    def connect(self) -> PlaywrightBrowserSessionAdapter:
        if not self.config.browser_url:
            raise BrowserProviderUnavailableError("CloakBrowser connect mode requires browser_url")
        sync_playwright = self._load_sync_playwright()
        manager = sync_playwright().start()
        try:
            browser = manager.chromium.connect_over_cdp(self.config.browser_url, timeout=self.config.launch_timeout * 1000)
            contexts = list(getattr(browser, "contexts", []) or [])
            context = contexts[0] if contexts else browser.new_context()
            session = PlaywrightBrowserSessionAdapter(provider_id=self.provider_id, context=context, browser=browser, playwright_manager=manager)
        except Exception:
            manager.stop()
            raise
        self._session = session
        return session

    def stop(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def is_available(self) -> bool:
        if self.config.browser_url:
            try:
                self._load_sync_playwright()
            except BrowserProviderUnavailableError:
                return False
            return True
        try:
            self._load_cloakbrowser()
        except BrowserProviderUnavailableError:
            return False
        return True

    def _launch_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": self.config.headless,
            "humanize": self.config.humanize,
        }
        if self.config.proxy:
            kwargs["proxy"] = self.config.proxy
        if self.config.geoip:
            kwargs["geoip"] = self.config.geoip
        if self.config.locale:
            kwargs["locale"] = self.config.locale
        if self.config.timezone:
            kwargs["timezone"] = self.config.timezone
        if self.config.args:
            kwargs["args"] = self.config.args
        return kwargs

    @staticmethod
    def _load_cloakbrowser() -> Any:
        try:
            import cloakbrowser
        except ModuleNotFoundError as exc:
            raise BrowserProviderUnavailableError(
                "cloakbrowser is not installed. Install the optional dependency, for example: "
                'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cloak]"'
            ) from exc
        return cloakbrowser

    @staticmethod
    def _load_sync_playwright() -> Any:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise BrowserProviderUnavailableError(
                "playwright is not installed. CloakBrowser connect mode needs Playwright CDP support; install the optional browser dependency, for example: "
                'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[browser]"'
            ) from exc
        return sync_playwright


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.username and not parts.password:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
