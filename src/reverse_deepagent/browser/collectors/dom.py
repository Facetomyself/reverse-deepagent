from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserPage


class DOMCollector:
    """Collect a conservative DOM/content snapshot from a BrowserPage."""

    def collect(self, page: BrowserPage) -> dict[str, Any]:
        html = page.content()
        title = None
        try:
            title = page.title()
        except Exception:
            title = None
        return {
            "url": page.url,
            "title": title,
            "html_size": len(html),
            "html_preview": html[:1000],
        }
