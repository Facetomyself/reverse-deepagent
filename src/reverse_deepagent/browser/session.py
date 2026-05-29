from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserCDPSession, BrowserPageRef


class PlaywrightCDPSessionAdapter:
    """Small adapter around a Playwright CDP session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return self._session.send(method, params or {})

    def on(self, event_name: str, handler: Any) -> None:
        on = getattr(self._session, "on", None)
        if not callable(on):
            raise RuntimeError("CDP session does not support event subscription")
        on(event_name, handler)


class PlaywrightBrowserPageAdapter:
    """BrowserPage adapter for Playwright-compatible page objects."""

    def __init__(self, page: Any) -> None:
        self._page = page

    @property
    def raw_page(self) -> Any:
        return self._page

    @property
    def url(self) -> str:
        return str(getattr(self._page, "url", ""))

    def goto(self, url: str, timeout: float | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout * 1000
        self._page.goto(url, **kwargs)

    def title(self) -> str:
        return str(self._page.title())

    def content(self) -> str:
        return str(self._page.content())

    def evaluate(self, expression: str) -> Any:
        return self._page.evaluate(expression)

    def screenshot(self, path: str | None = None) -> bytes | None:
        if path:
            self._page.screenshot(path=path)
            return None
        return self._page.screenshot()

    def cdp_session(self) -> BrowserCDPSession | None:
        context = getattr(self._page, "context", None)
        new_cdp_session = getattr(context, "new_cdp_session", None)
        if not callable(new_cdp_session):
            return None
        try:
            return PlaywrightCDPSessionAdapter(new_cdp_session(self._page))
        except Exception:
            return None


class PlaywrightBrowserSessionAdapter:
    """BrowserSession adapter for Playwright-compatible browser contexts."""

    def __init__(
        self,
        *,
        provider_id: str,
        context: Any,
        browser: Any | None = None,
        playwright_manager: Any | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._context = context
        self._browser = browser
        self._playwright_manager = playwright_manager

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def raw_context(self) -> Any:
        return self._context

    @property
    def raw_browser(self) -> Any | None:
        return self._browser

    def list_pages(self) -> list[BrowserPageRef]:
        pages = list(getattr(self._context, "pages", []) or [])
        refs: list[BrowserPageRef] = []
        for index, page in enumerate(pages):
            title = None
            try:
                title = str(page.title())
            except Exception:
                title = None
            refs.append(
                BrowserPageRef(
                    page_id=str(index),
                    url=str(getattr(page, "url", "") or ""),
                    title=title,
                    selected=index == 0,
                )
            )
        return refs

    def new_page(self, url: str | None = None) -> PlaywrightBrowserPageAdapter:
        page = self._context.new_page()
        adapter = PlaywrightBrowserPageAdapter(page)
        if url:
            adapter.goto(url)
        return adapter

    def get_active_page(self) -> PlaywrightBrowserPageAdapter | None:
        pages = list(getattr(self._context, "pages", []) or [])
        if not pages:
            return None
        return PlaywrightBrowserPageAdapter(pages[0])

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            try:
                if self._browser is not None:
                    self._browser.close()
            finally:
                stop = getattr(self._playwright_manager, "stop", None)
                if callable(stop):
                    stop()
