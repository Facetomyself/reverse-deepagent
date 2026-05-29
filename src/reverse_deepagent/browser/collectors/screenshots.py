from __future__ import annotations

from reverse_deepagent.browser.base import BrowserPage


class ScreenshotCollector:
    """Collect a screenshot through the provider-neutral page contract."""

    def collect(self, page: BrowserPage, path: str | None = None) -> dict[str, object]:
        data = page.screenshot(path=path)
        return {
            "path": path,
            "bytes": None if data is None else len(data),
            "in_memory": data is not None,
        }
