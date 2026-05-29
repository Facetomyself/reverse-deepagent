from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.session import PlaywrightBrowserSessionAdapter
from reverse_deepagent.schemas.common import SchemaBaseModel


class PlaywrightChromiumConfig(SchemaBaseModel):
    """Configuration for the Playwright Chromium BrowserProvider."""

    headless: bool = Field(default=True, description="Launch Chromium in headless mode.")
    profile_dir: str | None = Field(default=None, description="Optional persistent profile directory.")
    browser_url: str | None = Field(default=None, description="Optional existing CDP browser URL for connect mode.")
    executable_path: str | None = Field(default=None, description="Optional Chromium/Chrome executable path.")
    args: list[str] = Field(default_factory=list, description="Extra Chromium launch args.")
    launch_timeout: float = Field(default=30.0, description="Launch timeout in seconds.")
    navigation_timeout: float = Field(default=30.0, description="Default navigation timeout in seconds.")

    def safe_summary(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PlaywrightChromiumProvider:
    """BrowserProvider backed by Playwright's Chromium implementation."""

    provider_id = "playwright-chromium"

    def __init__(self, config: PlaywrightChromiumConfig | None = None) -> None:
        self.config = config or PlaywrightChromiumConfig()
        self._session: PlaywrightBrowserSessionAdapter | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Playwright Chromium",
            engine="chromium",
            transport="playwright",
            supports_launch=True,
            supports_connect=True,
            supports_persistent_context=True,
            supports_cdp=True,
            supports_playwright_api=True,
            supports_proxy=False,
            supports_stealth=False,
            supports_humanize=False,
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
                "portable native browser provider baseline",
                "requires optional playwright dependency and browser installation",
            ],
            config=self.config.safe_summary(),
        )

    def start(self) -> PlaywrightBrowserSessionAdapter:
        sync_playwright = self._load_sync_playwright()
        manager = sync_playwright().start()
        try:
            if self.config.profile_dir:
                context = manager.chromium.launch_persistent_context(
                    user_data_dir=str(Path(self.config.profile_dir).expanduser()),
                    headless=self.config.headless,
                    executable_path=self.config.executable_path,
                    args=self.config.args,
                    timeout=self.config.launch_timeout * 1000,
                )
                session = PlaywrightBrowserSessionAdapter(provider_id=self.provider_id, context=context, playwright_manager=manager)
            else:
                browser = manager.chromium.launch(
                    headless=self.config.headless,
                    executable_path=self.config.executable_path,
                    args=self.config.args,
                    timeout=self.config.launch_timeout * 1000,
                )
                context = browser.new_context()
                session = PlaywrightBrowserSessionAdapter(provider_id=self.provider_id, context=context, browser=browser, playwright_manager=manager)
        except Exception:
            manager.stop()
            raise
        self._session = session
        return session

    def connect(self) -> PlaywrightBrowserSessionAdapter:
        if not self.config.browser_url:
            raise BrowserProviderUnavailableError("Playwright Chromium connect mode requires browser_url")
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
        try:
            self._load_sync_playwright()
        except BrowserProviderUnavailableError:
            return False
        return True

    @staticmethod
    def _load_sync_playwright() -> Any:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise BrowserProviderUnavailableError(
                "playwright is not installed. Install the optional browser dependency, for example: "
                'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[browser]"'
            ) from exc
        return sync_playwright
