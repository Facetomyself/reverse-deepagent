from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserPage


def _raw_page(page: BrowserPage) -> Any:
    return getattr(page, "raw_page", None)


class ConsoleCollector:
    """Collect console events from Playwright-like pages."""

    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []
        self._attached = False

    def attach(self, page: BrowserPage) -> bool:
        raw = _raw_page(page)
        on = getattr(raw, "on", None)
        if not callable(on):
            return False
        on("console", self._handle_console)
        self._attached = True
        return True

    def snapshot(self) -> dict[str, Any]:
        return {"attached": self._attached, "count": len(self._messages), "messages": list(self._messages)}

    def _handle_console(self, message: Any) -> None:
        text = None
        msg_type = None
        try:
            text_attr = getattr(message, "text", None)
            text = text_attr() if callable(text_attr) else text_attr
        except Exception:
            text = None
        try:
            type_attr = getattr(message, "type", None)
            msg_type = type_attr() if callable(type_attr) else type_attr
        except Exception:
            msg_type = None
        self._messages.append({"type": msg_type or "unknown", "text": text or str(message)})
