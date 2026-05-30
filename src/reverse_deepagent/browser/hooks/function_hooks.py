from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage


@dataclass(slots=True)
class FunctionHookSpec:
    """Runtime function hook / logpoint request for globally reachable functions."""

    function_name: str
    function_paths: list[str] = field(default_factory=list)
    candidate_id: str | None = None
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "FunctionHookSpec | None":
        context = context or {}
        function_name = (
            context.get("function_name")
            or context.get("functionName")
            or context.get("target_function")
            or context.get("targetFunction")
            or context.get("hook_function")
            or context.get("hookFunction")
        )
        paths_raw = (
            context.get("function_paths")
            or context.get("functionPaths")
            or context.get("function_path")
            or context.get("functionPath")
            or context.get("hook_paths")
            or context.get("hookPaths")
        )
        function_paths = cls._coerce_paths(paths_raw)
        if not function_name and function_paths:
            function_name = function_paths[0].split(".")[-1]
        if not function_name:
            return None
        normalized_name = str(function_name).strip()
        if not normalized_name:
            return None
        if not function_paths:
            function_paths = [f"window.{normalized_name}", f"window.reverseFixture.{normalized_name}"]
        return cls(
            function_name=normalized_name,
            function_paths=function_paths,
            candidate_id=str(context.get("candidate_id", context.get("candidateId"))) if context.get("candidate_id", context.get("candidateId")) else None,
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )

    @staticmethod
    def _coerce_paths(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


@dataclass(slots=True)
class FunctionHookResult:
    status: str
    installed: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "installed_count": len(self.installed),
            "missing_count": len(self.missing),
            "event_count": len(self.events),
            "installed": self.installed,
            "missing": self.missing,
            "events": self.events,
            "trigger": self.trigger,
            "error": self.error,
        }


class FunctionHookManager:
    """Install best-effort function wrappers for target-specific runtime tracing."""

    def install(self, page: BrowserPage, spec: FunctionHookSpec | None) -> FunctionHookResult:
        if spec is None:
            return FunctionHookResult(status="unsupported", error="missing_function_name")
        try:
            install_payload = page.evaluate(self._install_expression(spec))
        except Exception as exc:
            return FunctionHookResult(status="failed", error=str(exc))
        trigger = self._run_trigger(page, spec)
        try:
            snapshot_payload = page.evaluate(self._snapshot_expression(spec))
        except Exception as exc:
            snapshot_payload = {"ok": False, "events": [], "error": str(exc)}

        installed = self._list_of_dicts(install_payload.get("installed") if isinstance(install_payload, dict) else [])
        missing = self._list_of_dicts(install_payload.get("missing") if isinstance(install_payload, dict) else [])
        events = self._list_of_dicts(snapshot_payload.get("events") if isinstance(snapshot_payload, dict) else [])
        status = "success" if installed else "partial" if missing else "failed"
        return FunctionHookResult(
            status=status,
            installed=installed,
            missing=missing,
            events=events,
            trigger=trigger,
            error=install_payload.get("error") if isinstance(install_payload, dict) else None,
        )

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: FunctionHookSpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        try:
            payload = page.evaluate(spec.trigger_expression)
            return {"attempted": True, "ok": True, "result": payload if isinstance(payload, dict) else {"value": payload}}
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _install_expression(spec: FunctionHookSpec) -> str:
        config = {
            "functionName": spec.function_name,
            "functionPaths": spec.function_paths,
            "candidateId": spec.candidate_id,
            "captureArgs": spec.capture_args,
            "captureResult": spec.capture_result,
            "maxPreviewLength": spec.max_preview_length,
        }
        config_json = json.dumps(config, ensure_ascii=False)
        template = """(() => {
  const config = __REVERSE_AGENT_FUNCTION_HOOK_CONFIG__;
  const root = window.__reverseDeepAgentHooks = window.__reverseDeepAgentHooks || {{
    installedAt: Date.now(),
    events: [],
    installed: {{}},
    push(type, payload) {{
      try {{
        this.events.push({{ type, ts: Date.now(), payload }});
        if (this.events.length > 300) this.events.shift();
      }} catch (_) {{}}
    }}
  }};
  root.installed.function_hooks = root.installed.function_hooks || {{}};
  const preview = (value) => {{
    try {{
      if (value === undefined) return {{ type: 'undefined', preview: 'undefined' }};
      if (value === null) return {{ type: 'null', preview: 'null' }};
      if (typeof value === 'string') return {{ type: 'string', size: value.length, preview: value.slice(0, config.maxPreviewLength) }};
      if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return {{ type: typeof value, preview: String(value) }};
      if (typeof value === 'function') return {{ type: 'function', name: value.name || '', preview: '<function>' }};
      const text = JSON.stringify(value);
      return {{ type: Array.isArray(value) ? 'array' : typeof value, size: text ? text.length : 0, preview: String(text || value).slice(0, config.maxPreviewLength) }};
    }} catch (_) {{
      return {{ type: typeof value, preview: '<unavailable>' }};
    }}
  }};
  const resolvePath = (path) => {{
    const parts = String(path || '').split('.').filter(Boolean);
    if (!parts.length) return null;
    let owner = window;
    let index = 0;
    if (parts[0] === 'window') index = 1;
    for (; index < parts.length - 1; index++) {{
      owner = owner && owner[parts[index]];
      if (!owner) return null;
    }}
    const property = parts[parts.length - 1];
    return {{ owner, property, value: owner && owner[property] }};
  }};
  const installed = [];
  const missing = [];
  for (const path of config.functionPaths || []) {{
    try {{
      const resolved = resolvePath(path);
      if (!resolved || typeof resolved.value !== 'function') {{
        missing.push({{ path, reason: 'function_not_found' }});
        continue;
      }}
      if (resolved.value.__reverseAgentFunctionHooked) {{
        installed.push({{ path, functionName: config.functionName, alreadyInstalled: true }});
        continue;
      }}
      const original = resolved.value;
      const wrapped = function reverseAgentFunctionHookWrapper(...args) {{
        const callId = `${{config.functionName || path}}:${{Date.now()}}:${{Math.random().toString(16).slice(2)}}`;
        root.push('function_call', {{
          callId,
          functionName: config.functionName,
          path,
          candidateId: config.candidateId || null,
          argCount: args.length,
          args: config.captureArgs ? args.map(preview) : []
        }});
        try {{
          const result = original.apply(this, args);
          const recordReturn = (value) => {{
            root.push('function_return', {{
              callId,
              functionName: config.functionName,
              path,
              candidateId: config.candidateId || null,
              result: config.captureResult ? preview(value) : {{ preview: '<disabled>' }}
            }});
            return value;
          }};
          if (result && typeof result.then === 'function') {{
            return result.then(recordReturn, (error) => {{
              root.push('function_throw', {{ callId, functionName: config.functionName, path, candidateId: config.candidateId || null, error: String(error && error.message || error) }});
              throw error;
            }});
          }}
          return recordReturn(result);
        }} catch (error) {{
          root.push('function_throw', {{ callId, functionName: config.functionName, path, candidateId: config.candidateId || null, error: String(error && error.message || error) }});
          throw error;
        }}
      }};
      try {{ Object.defineProperty(wrapped, 'name', {{ value: original.name || config.functionName || 'reverseAgentFunctionHookWrapper' }}); }} catch (_) {{}}
      wrapped.__reverseAgentOriginal = original;
      wrapped.__reverseAgentFunctionHooked = true;
      resolved.owner[resolved.property] = wrapped;
      root.installed.function_hooks[path] = true;
      installed.push({{ path, functionName: config.functionName, candidateId: config.candidateId || null }});
    }} catch (error) {{
      missing.push({{ path, reason: 'install_error', error: String(error && error.message || error) }});
    }}
  }}
  return {{ ok: installed.length > 0, installed, missing, eventCount: root.events.length }};
})()"""
        return (
            template.replace("__REVERSE_AGENT_FUNCTION_HOOK_CONFIG__", config_json)
            .replace("{{", "{")
            .replace("}}", "}")
        )

    @staticmethod
    def _snapshot_expression(spec: FunctionHookSpec) -> str:
        paths_json = json.dumps(spec.function_paths, ensure_ascii=False)
        template = """(() => {
  const root = window.__reverseDeepAgentHooks;
  if (!root) return {{ ok: false, events: [], eventCount: 0, reason: 'not_installed' }};
  const paths = new Set(__REVERSE_AGENT_FUNCTION_HOOK_PATHS__);
  const events = (root.events || []).filter((event) => event && event.payload && paths.has(event.payload.path) && /^function_/.test(event.type));
  return {{ ok: true, events, eventCount: events.length, installed: Object.assign({{}}, (root.installed && root.installed.function_hooks) || {{}}) }};
})()"""
        return (
            template.replace("__REVERSE_AGENT_FUNCTION_HOOK_PATHS__", paths_json)
            .replace("{{", "{")
            .replace("}}", "}")
        )
