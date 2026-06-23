from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager, BreakpointSpec
from reverse_deepagent.browser.source_map_remapper import SourceMapRemapper


@dataclass(slots=True)
class SourceLogpointSpec:
    """Provider-neutral source logpoint request for script URL + offset based tracing."""

    url_pattern: str
    line_number: int = 0
    column_number: int | None = None
    log_expression: str = "undefined"
    label: str | None = None
    trigger_expression: str | None = None
    wait_after_trigger_ms: int = 0
    pause_on_hit: bool = False
    logpoint_id: str | None = None
    remap: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceLogpointSpec | None":
        context = context or {}
        url_pattern = context.get("url_pattern") or context.get("url") or context.get("script_url")
        if not url_pattern:
            return None
        line_number = int(context.get("line_number", context.get("lineNumber", 0)) or 0)
        column_raw = context.get("column_number", context.get("columnNumber"))
        column_number = None if column_raw is None else int(column_raw)
        requested_location = {"line_number": line_number, "column_number": column_number}
        remap = cls._resolve_remap(context, requested_location)
        generated_location = remap.get("generated") if remap.get("status") == "success" else None
        if isinstance(generated_location, dict):
            line_number = int(generated_location["line_number"])
            column_number = int(generated_location["column_number"])
        log_expression = context.get("log_expression", context.get("logExpression", context.get("expression", context.get("source_expression", "undefined"))))
        label = context.get("label")
        pause_on_hit_raw = context.get("pause_on_hit", context.get("pauseOnHit"))
        logpoint_id = context.get("logpoint_id", context.get("logpointId"))
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        return cls(
            url_pattern=str(url_pattern),
            line_number=line_number,
            column_number=column_number,
            log_expression=str(log_expression) if log_expression is not None else "undefined",
            label=str(label) if label else None,
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            wait_after_trigger_ms=int(context.get("wait_after_trigger_ms", context.get("waitAfterTriggerMs", 0)) or 0),
            pause_on_hit=bool(pause_on_hit_raw) if pause_on_hit_raw is not None else False,
            logpoint_id=str(logpoint_id) if logpoint_id else None,
            remap=remap,
        )

    @classmethod
    def _resolve_remap(cls, context: dict[str, Any], requested_location: dict[str, Any]) -> dict[str, Any]:
        if not cls._has_remap_context(context):
            return {}
        try:
            location = SourceMapRemapper.resolve_from_context(context)
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "requested": requested_location,
            }
        if location is None:
            return {
                "status": "unresolved",
                "reason": "no_matching_generated_location",
                "requested": requested_location,
            }
        return {
            "status": "success",
            "strategy": location.strategy,
            "requested": requested_location,
            "generated": location.to_dict(),
        }

    @staticmethod
    def _has_remap_context(context: dict[str, Any]) -> bool:
        return any(
            key in context
            for key in (
                "bundle_offset",
                "bundleOffset",
                "generated_offset",
                "generatedOffset",
                "source_map",
                "sourceMap",
                "original_source",
                "originalSource",
                "original_line",
                "originalLine",
                "original_line_number",
                "originalLineNumber",
            )
        )

    def effective_logpoint_id(self) -> str:
        if self.logpoint_id:
            return self.logpoint_id
        label = self.label or "source-logpoint"
        return f"{self.url_pattern}:{self.line_number}:{self.column_number or 0}:{label}"

    def to_breakpoint_spec(self) -> BreakpointSpec:
        return BreakpointSpec(
            url_pattern=self.url_pattern,
            line_number=self.line_number,
            column_number=self.column_number,
            condition=self._condition_expression(),
            trigger_expression=self.trigger_expression,
            wait_after_trigger_ms=self.wait_after_trigger_ms,
            auto_resume=not self.pause_on_hit,
        )

    def _condition_expression(self) -> str:
        payload = {
            "logpointId": self.effective_logpoint_id(),
            "urlPattern": self.url_pattern,
            "lineNumber": self.line_number,
            "columnNumber": self.column_number,
            "label": self.label,
            "pauseOnHit": self.pause_on_hit,
            "logExpression": self.log_expression,
            "remap": self.remap,
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        pause_literal = "true" if self.pause_on_hit else "false"
        template = """(() => {
  const root = window.__reverseDeepAgentSourceLogpoints = window.__reverseDeepAgentSourceLogpoints || {
    installedAt: Date.now(),
    events: [],
    installed: {},
    push(type, payload) {
      try {
        this.events.push({ type, ts: Date.now(), payload });
        if (this.events.length > 300) this.events.shift();
      } catch (_) {}
    },
    preview(value) {
      try {
        if (value === undefined) return { type: 'undefined', preview: 'undefined' };
        if (value === null) return { type: 'null', preview: 'null' };
        if (typeof value === 'string') return { type: 'string', size: value.length, preview: value.slice(0, 240) };
        if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return { type: typeof value, preview: String(value) };
        if (typeof value === 'function') return { type: 'function', name: value.name || '', preview: '<function>' };
        const text = JSON.stringify(value);
        return { type: Array.isArray(value) ? 'array' : typeof value, size: text ? text.length : 0, preview: String(text || value).slice(0, 240) };
      } catch (_) {
        return { type: typeof value, preview: '<unavailable>' };
      }
    }
  };
  const metadata = __LOGPOINT_METADATA__;
  try {
    let value;
    let ok = true;
    let error = null;
    try {
      value = (__LOGPOINT_EXPRESSION__);
    } catch (caught) {
      ok = false;
      error = String(caught && caught.message || caught);
    }
    root.push('source_logpoint', {
      logpointId: metadata.logpointId,
      urlPattern: metadata.urlPattern,
      lineNumber: metadata.lineNumber,
      columnNumber: metadata.columnNumber,
      label: metadata.label,
      pauseOnHit: metadata.pauseOnHit,
      remap: metadata.remap,
      ok,
      value: ok ? root.preview(value) : null,
      error
    });
  } catch (_) {}
  return __PAUSE_LITERAL__;
})()"""
        return (
            template.replace("__LOGPOINT_METADATA__", payload_json)
            .replace("__LOGPOINT_EXPRESSION__", self.log_expression)
            .replace("__PAUSE_LITERAL__", pause_literal)
        )


@dataclass(slots=True)
class SourceLogpointResult:
    status: str
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    remap: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "count": len(self.breakpoints),
            "breakpoints": self.breakpoints,
            "events": self.events,
            "event_count": len(self.events),
            "trigger": self.trigger,
            "remap": self.remap,
            "error": self.error,
            "reason": self.reason,
        }


class SourceLogpointManager:
    """Install source-level logpoints behind a provider-neutral breakpoint wrapper."""

    def install(self, page: BrowserPage, spec: SourceLogpointSpec | None) -> SourceLogpointResult:
        if spec is None:
            return SourceLogpointResult(status="unsupported", error="missing_url_pattern")
        try:
            page.evaluate(self._install_expression(spec))
        except Exception as exc:
            return SourceLogpointResult(status="failed", remap=spec.remap, error=str(exc))
        breakpoint_result = BreakpointManager().set_breakpoint(page, spec.to_breakpoint_spec())
        try:
            snapshot_payload = page.evaluate(self._snapshot_expression(spec))
        except Exception as exc:
            snapshot_payload = {"ok": False, "events": [], "error": str(exc)}
        events = self._list_of_dicts(snapshot_payload.get("events") if isinstance(snapshot_payload, dict) else [])
        breakpoints = breakpoint_result.breakpoints if breakpoint_result.breakpoints else []
        status = "success" if breakpoint_result.supported and breakpoint_result.status in {"success", "partial"} else "failed"
        return SourceLogpointResult(
            status=status,
            breakpoints=breakpoints,
            events=events,
            trigger=breakpoint_result.trigger,
            remap=spec.remap,
            error=breakpoint_result.error,
            reason=breakpoint_result.reason,
        )

    @staticmethod
    def _install_expression(spec: SourceLogpointSpec) -> str:
        payload = {
            "logpointId": spec.effective_logpoint_id(),
            "urlPattern": spec.url_pattern,
            "lineNumber": spec.line_number,
            "columnNumber": spec.column_number,
            "label": spec.label,
            "pauseOnHit": spec.pause_on_hit,
            "remap": spec.remap,
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        template = """(() => {
  const root = window.__reverseDeepAgentSourceLogpoints = window.__reverseDeepAgentSourceLogpoints || {
    installedAt: Date.now(),
    events: [],
    installed: {},
    push(type, payload) {
      try {
        this.events.push({ type, ts: Date.now(), payload });
        if (this.events.length > 300) this.events.shift();
      } catch (_) {}
    },
    preview(value) {
      try {
        if (value === undefined) return { type: 'undefined', preview: 'undefined' };
        if (value === null) return { type: 'null', preview: 'null' };
        if (typeof value === 'string') return { type: 'string', size: value.length, preview: value.slice(0, 240) };
        if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return { type: typeof value, preview: String(value) };
        if (typeof value === 'function') return { type: 'function', name: value.name || '', preview: '<function>' };
        const text = JSON.stringify(value);
        return { type: Array.isArray(value) ? 'array' : typeof value, size: text ? text.length : 0, preview: String(text || value).slice(0, 240) };
      } catch (_) {
        return { type: typeof value, preview: '<unavailable>' };
      }
    }
  };
  const metadata = __LOGPOINT_METADATA__;
  root.installed.source_logpoints = root.installed.source_logpoints || {};
  root.installed.source_logpoints[metadata.logpointId] = true;
  return { ok: true, installed: [{ logpointId: metadata.logpointId, urlPattern: metadata.urlPattern, lineNumber: metadata.lineNumber, columnNumber: metadata.columnNumber, label: metadata.label, pauseOnHit: metadata.pauseOnHit, remap: metadata.remap }], missing: [], eventCount: root.events.length };
})()"""
        return template.replace("__LOGPOINT_METADATA__", payload_json)

    @staticmethod
    def _snapshot_expression(spec: SourceLogpointSpec) -> str:
        payload_json = json.dumps({"logpointId": spec.effective_logpoint_id()}, ensure_ascii=False)
        template = """(() => {
  const root = window.__reverseDeepAgentSourceLogpoints;
  if (!root) return { ok: false, events: [], eventCount: 0, reason: 'not_installed' };
  const metadata = __LOGPOINT_METADATA__;
  const events = (root.events || []).filter((event) => event && event.payload && event.payload.logpointId === metadata.logpointId);
  return { ok: true, events, eventCount: events.length, installed: Object.assign({}, (root.installed && root.installed.source_logpoints) || {}) };
})()"""
        return template.replace("__LOGPOINT_METADATA__", payload_json)

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
