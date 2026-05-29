from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserPage


def _raw_page(page: BrowserPage) -> Any:
    return getattr(page, "raw_page", None)


def _safe_call(obj: Any, attr: str, default: Any = None) -> Any:
    value = getattr(obj, attr, None)
    if callable(value):
        try:
            return value()
        except Exception:
            return default
    return value if value is not None else default


class NetworkCollector:
    """Collect normalized request/response events from Playwright-like pages."""

    def __init__(self) -> None:
        self._requests: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._attached = False

    def attach(self, page: BrowserPage) -> bool:
        raw = _raw_page(page)
        on = getattr(raw, "on", None)
        if not callable(on):
            return False
        on("request", self.record_request)
        on("response", self.record_response)
        self._attached = True
        return True

    def record_request(self, request: Any) -> None:
        url = str(_safe_call(request, "url", ""))
        key = url or f"request-{len(self._order)}"
        if key not in self._requests:
            self._order.append(key)
        request_id = _safe_call(request, "request_id") or _safe_call(request, "requestId")
        self._requests[key] = {
            **self._requests.get(key, {}),
            "url": url,
            "method": str(_safe_call(request, "method", "GET")),
            "resource_type": _safe_call(request, "resource_type"),
            "headers": _safe_call(request, "headers", {}) or {},
        }
        if request_id:
            self._requests[key]["requestId"] = request_id

    def record_response(self, response: Any) -> None:
        request = _safe_call(response, "request")
        url = str(_safe_call(request, "url", _safe_call(response, "url", "")))
        key = url or f"response-{len(self._order)}"
        if key not in self._requests:
            self._order.append(key)
        self._requests[key] = {
            **self._requests.get(key, {}),
            "url": url,
            "status": _safe_call(response, "status"),
            "ok": _safe_call(response, "ok"),
            "response_headers": _safe_call(response, "headers", {}) or {},
        }

    def snapshot(self) -> dict[str, Any]:
        items = [self._requests[key] for key in self._order]
        return {"attached": self._attached, "count": len(items), "requests": items}
