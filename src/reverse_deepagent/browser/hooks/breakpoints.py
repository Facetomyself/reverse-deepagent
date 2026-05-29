from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage


@dataclass(slots=True)
class BreakpointSpec:
    """Provider-neutral breakpoint request."""

    url_pattern: str
    line_number: int = 0
    column_number: int | None = None
    condition: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "BreakpointSpec | None":
        context = context or {}
        url_pattern = context.get("url_pattern") or context.get("url") or context.get("script_url")
        if not url_pattern:
            return None
        line_number = int(context.get("line_number", context.get("lineNumber", 0)) or 0)
        column_raw = context.get("column_number", context.get("columnNumber"))
        column_number = None if column_raw is None else int(column_raw)
        condition = context.get("condition")
        return cls(
            url_pattern=str(url_pattern),
            line_number=line_number,
            column_number=column_number,
            condition=str(condition) if condition else None,
        )

    def to_cdp_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "urlRegex": self.url_pattern,
            "lineNumber": self.line_number,
        }
        if self.column_number is not None:
            params["columnNumber"] = self.column_number
        if self.condition:
            params["condition"] = self.condition
        return params


@dataclass(slots=True)
class BreakpointResult:
    status: str
    supported: bool
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "count": len(self.breakpoints),
            "breakpoints": self.breakpoints,
            "error": self.error,
            "reason": self.reason,
        }


class BreakpointManager:
    """Set CDP breakpoints behind a provider-neutral capability gate."""

    def set_breakpoint(self, page: BrowserPage, spec: BreakpointSpec | None) -> BreakpointResult:
        if spec is None:
            return BreakpointResult(status="unsupported", supported=False, reason="missing_url_pattern")
        session = page.cdp_session()
        if session is None:
            return BreakpointResult(status="unsupported", supported=False, reason="cdp_session_unavailable")
        try:
            session.send("Debugger.enable", {})
            payload = session.send("Debugger.setBreakpointByUrl", spec.to_cdp_params())
        except Exception as exc:
            return BreakpointResult(status="failed", supported=True, error=str(exc))
        breakpoint_id = payload.get("breakpointId") if isinstance(payload, dict) else None
        locations = payload.get("locations", []) if isinstance(payload, dict) else []
        return BreakpointResult(
            status="success" if breakpoint_id else "partial",
            supported=True,
            breakpoints=[
                {
                    "breakpointId": breakpoint_id,
                    "urlPattern": spec.url_pattern,
                    "lineNumber": spec.line_number,
                    "columnNumber": spec.column_number,
                    "condition": spec.condition,
                    "locations": locations if isinstance(locations, list) else [],
                }
            ],
        )
