from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage


@dataclass(slots=True)
class PageMutationAuditSpec:
    """Explicit page-level mutation audit request.

    This is intentionally separate from callframe evaluation mutation audit:
    it compares coarse page snapshots before and after an explicit trigger
    expression without running in the default recon path.
    """

    trigger_expression: str | None = None
    max_preview_length: int = 240
    global_names: list[str] = field(default_factory=list)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PageMutationAuditSpec | None":
        context = context or {}
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        global_names = cls._coerce_names(
            context.get(
                "global_names",
                context.get("globalNames", context.get("selected_globals", context.get("selectedGlobals"))),
            )
        )
        max_preview_length = int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)
        return cls(
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            max_preview_length=max_preview_length,
            global_names=global_names,
        )

    @staticmethod
    def _coerce_names(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            raw = [str(item).strip() for item in value if item is not None]
        else:
            raw = []
        names: list[str] = []
        for item in raw:
            if item and item not in names:
                names.append(item)
        return names


@dataclass(slots=True)
class PageMutationAuditResult:
    status: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "before": self.before,
            "after": self.after,
            "diff": self.diff,
            "changed": bool(self.diff.get("changed")),
            "change_count": int(self.diff.get("change_count") or 0),
            "trigger": self.trigger,
            "error": self.error,
            "reason": self.reason,
        }


class PageMutationAuditManager:
    """Coarse page snapshot diff around an explicit trigger expression."""

    def audit(self, page: BrowserPage, spec: PageMutationAuditSpec | None) -> PageMutationAuditResult:
        if spec is None:
            return PageMutationAuditResult(status="unsupported", reason="missing_page_mutation_audit_spec")
        before = self._snapshot(page, spec)
        trigger = self._run_trigger(page, spec)
        after = self._snapshot(page, spec)
        if before.get("ok") is False or after.get("ok") is False:
            return PageMutationAuditResult(
                status="failed",
                before=before,
                after=after,
                trigger=trigger,
                error=str(before.get("error") or after.get("error") or "snapshot_failed"),
            )
        diff = self._diff_snapshots(before, after)
        status = "success" if diff.get("changed") else "partial"
        return PageMutationAuditResult(status=status, before=before, after=after, diff=diff, trigger=trigger)

    @staticmethod
    def _snapshot(page: BrowserPage, spec: PageMutationAuditSpec) -> dict[str, Any]:
        try:
            payload = page.evaluate(PageMutationAuditManager._snapshot_expression(spec))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if isinstance(payload, dict):
            return payload
        return {"ok": False, "error": "non_object_snapshot_payload", "value_type": type(payload).__name__}

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: PageMutationAuditSpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        try:
            payload = page.evaluate(spec.trigger_expression)
            return {"attempted": True, "ok": True, "result": payload if isinstance(payload, dict) else {"value": payload}}
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}

    @staticmethod
    def _snapshot_expression(spec: PageMutationAuditSpec) -> str:
        global_names = json.dumps(spec.global_names)
        max_preview_length = max(1, int(spec.max_preview_length))
        return f"""
(() => {{
  const marker = "__REVERSE_AGENT_PAGE_MUTATION_AUDIT__";
  const maxPreviewLength = {max_preview_length};
  const globalNames = {global_names};
  const preview = (value) => {{
    try {{
      if (typeof value === "string") return value.slice(0, maxPreviewLength);
      if (typeof value === "function") return String(value).slice(0, maxPreviewLength);
      if (value === undefined) return "undefined";
      return JSON.stringify(value).slice(0, maxPreviewLength);
    }} catch (_) {{
      return Object.prototype.toString.call(value).slice(0, maxPreviewLength);
    }}
  }};
  const storageSnapshot = (storage) => {{
    try {{
      const keys = [];
      for (let index = 0; index < storage.length; index += 1) {{
        const key = storage.key(index);
        if (key !== null) keys.push(key);
      }}
      keys.sort();
      return {{ available: true, count: keys.length, keys }};
    }} catch (error) {{
      return {{ available: false, count: 0, keys: [], error: String(error && error.message || error) }};
    }}
  }};
  const resolveGlobal = (path) => {{
    const parts = String(path || "").split(".").filter(Boolean);
    if (!parts.length) throw new Error("empty_global_name");
    let value = window;
    let index = 0;
    if (["window", "globalThis", "self"].includes(parts[0])) {{
      index = 1;
    }} else if (["document", "navigator", "location"].includes(parts[0])) {{
      value = window[parts[0]];
      index = 1;
    }}
    for (; index < parts.length; index += 1) {{
      const property = parts[index];
      if (!/^[A-Za-z_$][\\w$]*$/.test(property)) throw new Error("unsupported_global_path");
      value = value == null ? undefined : value[property];
    }}
    return value;
  }};
  try {{
    const body = document && document.body;
    const html = body ? body.innerHTML : "";
    const text = body ? body.innerText || body.textContent || "" : "";
    const cookies = String(document && document.cookie || "")
      .split(";")
      .map((item) => item.trim().split("=")[0])
      .filter(Boolean)
      .sort();
    const globals = {{}};
    for (const name of globalNames) {{
      try {{
        const value = resolveGlobal(name);
        globals[name] = {{ type: value === null ? "null" : Array.isArray(value) ? "array" : typeof value, preview: preview(value) }};
      }} catch (error) {{
        globals[name] = {{ type: "unavailable", error: String(error && error.message || error) }};
      }}
    }}
    return {{
      marker,
      ok: true,
      url: location && location.href,
      title: document && document.title || "",
      dom: {{
        html_length: html.length,
        text_length: text.length,
        body_child_count: body && body.children ? body.children.length : 0,
        html_preview: html.slice(0, maxPreviewLength),
        text_preview: text.slice(0, maxPreviewLength),
      }},
      storage: {{
        localStorage: storageSnapshot(window.localStorage),
        sessionStorage: storageSnapshot(window.sessionStorage),
      }},
      cookies: {{ count: cookies.length, names: cookies }},
      globals,
    }};
  }} catch (error) {{
    return {{ marker, ok: false, error: String(error && error.message || error) }};
  }}
}})()
"""

    @staticmethod
    def _diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        changes: list[dict[str, Any]] = []
        PageMutationAuditManager._compare_value(changes, "url", before.get("url"), after.get("url"))
        PageMutationAuditManager._compare_value(changes, "title", before.get("title"), after.get("title"))
        for path in (
            "dom.html_length",
            "dom.text_length",
            "dom.body_child_count",
            "dom.html_preview",
            "dom.text_preview",
            "storage.localStorage.keys",
            "storage.sessionStorage.keys",
            "cookies.names",
        ):
            PageMutationAuditManager._compare_value(
                changes,
                path,
                PageMutationAuditManager._get_path(before, path),
                PageMutationAuditManager._get_path(after, path),
            )
        before_globals = before.get("globals") if isinstance(before.get("globals"), dict) else {}
        after_globals = after.get("globals") if isinstance(after.get("globals"), dict) else {}
        for name in sorted(set(before_globals) | set(after_globals)):
            PageMutationAuditManager._compare_value(changes, f"globals.{name}", before_globals.get(name), after_globals.get(name))
        categories = sorted({change["category"] for change in changes})
        return {
            "changed": bool(changes),
            "change_count": len(changes),
            "categories": categories,
            "changes": changes,
        }

    @staticmethod
    def _compare_value(changes: list[dict[str, Any]], path: str, before: Any, after: Any) -> None:
        if before == after:
            return
        changes.append(
            {
                "path": path,
                "category": PageMutationAuditManager._category_for_path(path),
                "before": before,
                "after": after,
            }
        )

    @staticmethod
    def _category_for_path(path: str) -> str:
        if path.startswith("dom."):
            return "dom"
        if path.startswith("storage."):
            return "storage"
        if path.startswith("cookies."):
            return "cookie"
        if path.startswith("globals."):
            return "global"
        return "page"

    @staticmethod
    def _get_path(payload: dict[str, Any], path: str) -> Any:
        current: Any = payload
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


@dataclass(slots=True)
class MutationObserverTimelineSpec:
    """Explicit MutationObserver timeline request around a trigger expression."""

    trigger_expression: str | None = None
    wait_after_trigger_ms: int = 50
    max_records: int = 100
    max_preview_length: int = 240
    observe_child_list: bool = True
    observe_attributes: bool = True
    observe_character_data: bool = True
    subtree: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "MutationObserverTimelineSpec | None":
        context = context or {}
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        wait_raw = context.get(
            "wait_after_trigger_ms",
            context.get("waitAfterTriggerMs", context.get("observer_wait_ms", context.get("observerWaitMs", 50))),
        )
        max_records = int(context.get("max_records", context.get("maxRecords", context.get("mutation_record_limit", context.get("mutationRecordLimit", 100)))) or 100)
        max_preview_length = int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)
        return cls(
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            wait_after_trigger_ms=int(wait_raw or 0),
            max_records=max(1, max_records),
            max_preview_length=max(1, max_preview_length),
            observe_child_list=bool(context.get("observe_child_list", context.get("observeChildList", True))),
            observe_attributes=bool(context.get("observe_attributes", context.get("observeAttributes", True))),
            observe_character_data=bool(context.get("observe_character_data", context.get("observeCharacterData", True))),
            subtree=bool(context.get("subtree", True)),
        )


@dataclass(slots=True)
class MutationObserverTimelineResult:
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    observer: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "record_count": len(self.records),
            "records": self.records,
            "trigger": self.trigger,
            "observer": self.observer,
            "summary": self.summary,
            "error": self.error,
            "reason": self.reason,
        }


class MutationObserverTimelineManager:
    """Capture MutationObserver records around an explicit trigger expression."""

    def observe(self, page: BrowserPage, spec: MutationObserverTimelineSpec | None) -> MutationObserverTimelineResult:
        if spec is None:
            return MutationObserverTimelineResult(status="unsupported", reason="missing_mutation_observer_timeline_spec")
        try:
            payload = page.evaluate(self._timeline_expression(spec))
        except Exception as exc:
            return MutationObserverTimelineResult(status="failed", error=str(exc))
        if not isinstance(payload, dict):
            return MutationObserverTimelineResult(status="failed", error="non_object_timeline_payload")
        records = PageMutationAuditManager._list_of_dicts(payload.get("records"))
        trigger = payload.get("trigger") if isinstance(payload.get("trigger"), dict) else {"attempted": False}
        observer = payload.get("observer") if isinstance(payload.get("observer"), dict) else {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else self._summary(records)
        error = payload.get("error")
        reason = payload.get("reason")
        if payload.get("ok") is False:
            return MutationObserverTimelineResult(
                status="failed",
                records=records,
                trigger=trigger,
                observer=observer,
                summary=summary,
                error=str(error or "mutation_observer_timeline_failed"),
                reason=str(reason) if reason else None,
            )
        status = "success" if records else "partial"
        return MutationObserverTimelineResult(status=status, records=records, trigger=trigger, observer=observer, summary=summary, reason=str(reason) if reason else None)

    @classmethod
    def _timeline_expression(cls, spec: MutationObserverTimelineSpec) -> str:
        config = {
            "triggerExpression": spec.trigger_expression,
            "waitAfterTriggerMs": spec.wait_after_trigger_ms,
            "maxRecords": spec.max_records,
            "maxPreviewLength": spec.max_preview_length,
            "options": {
                "childList": spec.observe_child_list,
                "attributes": spec.observe_attributes,
                "characterData": spec.observe_character_data,
                "subtree": spec.subtree,
                "attributeOldValue": spec.observe_attributes,
                "characterDataOldValue": spec.observe_character_data,
            },
        }
        config_json = json.dumps(config, ensure_ascii=False)
        template = """(async () => {
  const marker = "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__";
  const config = __MUTATION_OBSERVER_TIMELINE_CONFIG__;
  const startedAt = Date.now();
  const records = [];
  const preview = (node) => {
    try {
      if (!node) return null;
      if (node.nodeType === Node.TEXT_NODE) return { nodeType: "text", text: String(node.textContent || "").slice(0, config.maxPreviewLength) };
      if (node.nodeType !== Node.ELEMENT_NODE) return { nodeType: node.nodeType, name: node.nodeName };
      return {
        nodeType: "element",
        tag: String(node.tagName || "").toLowerCase(),
        id: node.id || "",
        className: String(node.className || "").slice(0, config.maxPreviewLength),
        text: String(node.textContent || "").slice(0, config.maxPreviewLength)
      };
    } catch (error) {
      return { nodeType: "unavailable", error: String(error && error.message || error) };
    }
  };
  const pushRecord = (mutation) => {
    const item = {
      index: records.length,
      ts: Date.now(),
      type: mutation.type,
      target: preview(mutation.target),
      attributeName: mutation.attributeName || null,
      oldValue: mutation.oldValue == null ? null : String(mutation.oldValue).slice(0, config.maxPreviewLength),
      addedNodes: Array.from(mutation.addedNodes || []).map(preview),
      removedNodes: Array.from(mutation.removedNodes || []).map(preview)
    };
    records.push(item);
    if (records.length > config.maxRecords) records.shift();
  };
  const summary = () => {
    const byType = {};
    for (const record of records) byType[record.type] = (byType[record.type] || 0) + 1;
    return { record_count: records.length, types: Object.keys(byType).sort(), by_type: byType };
  };
  if (typeof MutationObserver === "undefined") {
    return { marker, ok: false, status: "unsupported", reason: "mutation_observer_unavailable", records, summary: summary(), trigger: { attempted: false } };
  }
  const target = document && (document.body || document.documentElement);
  if (!target) {
    return { marker, ok: false, status: "unsupported", reason: "mutation_observer_target_unavailable", records, summary: summary(), trigger: { attempted: false } };
  }
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) pushRecord(mutation);
  });
  const observerInfo = { target: target === document.body ? "document.body" : "document.documentElement", options: config.options, started_at_ms: startedAt };
  let trigger = { attempted: false };
  try {
    observer.observe(target, config.options);
    if (config.triggerExpression) {
      trigger = { attempted: true };
      try {
        let value;
        try {
          value = Function("return (" + config.triggerExpression + ")")();
        } catch (_) {
          value = Function(config.triggerExpression)();
        }
        if (value && typeof value.then === "function") value = await value;
        trigger.ok = true;
        trigger.result = typeof value === "object" && value !== null ? value : { value };
      } catch (error) {
        trigger.ok = false;
        trigger.error = String(error && error.message || error);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, Math.max(0, config.waitAfterTriggerMs || 0)));
    observer.takeRecords().forEach(pushRecord);
    observer.disconnect();
    observerInfo.stopped_at_ms = Date.now();
    return { marker, ok: true, status: records.length ? "success" : "partial", records, summary: summary(), trigger, observer: observerInfo };
  } catch (error) {
    try { observer.disconnect(); } catch (_) {}
    return { marker, ok: false, status: "failed", error: String(error && error.message || error), records, summary: summary(), trigger, observer: observerInfo };
  }
})()"""
        return template.replace("__MUTATION_OBSERVER_TIMELINE_CONFIG__", config_json)

    @staticmethod
    def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for record in records:
            record_type = str(record.get("type") or "unknown")
            by_type[record_type] = by_type.get(record_type, 0) + 1
        return {"record_count": len(records), "types": sorted(by_type), "by_type": by_type}
