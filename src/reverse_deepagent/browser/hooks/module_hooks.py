from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.collectors.scripts import ScriptCollector


JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


def _module_call_path(require_path: str, module_id: str) -> str:
    module_literal = module_id if re.fullmatch(r"\d+", module_id) else json.dumps(module_id, ensure_ascii=False)
    return f"{require_path}({module_literal})"


def _export_access_path(base_path: str, export_name: str) -> str:
    if JS_IDENTIFIER_RE.fullmatch(export_name):
        return f"{base_path}.{export_name}"
    return f"{base_path}[{json.dumps(export_name, ensure_ascii=False)}]"


def _module_export_hook_path(require_path: str, module_id: str, export_name: str) -> str:
    return _export_access_path(_module_call_path(require_path, module_id), export_name)


@dataclass(slots=True)
class ModuleHookSpec:
    """Runtime module export hook request for webpack-like module systems."""

    module_id: str
    export_name: str
    require_path: str = "window.__webpack_require__"
    function_name: str | None = None
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleHookSpec | None":
        context = context or {}
        module_id = (
            context.get("module_id")
            or context.get("moduleId")
            or context.get("webpack_module_id")
            or context.get("webpackModuleId")
        )
        export_name = (
            context.get("export_name")
            or context.get("exportName")
            or context.get("module_export")
            or context.get("moduleExport")
            or context.get("function_name")
            or context.get("functionName")
        )
        if module_id is None or export_name is None:
            return None
        normalized_module_id = str(module_id).strip()
        normalized_export = str(export_name).strip()
        if not normalized_module_id or not normalized_export:
            return None
        require_path = str(context.get("require_path", context.get("requirePath", "window.__webpack_require__")) or "window.__webpack_require__").strip()
        return cls(
            module_id=normalized_module_id,
            export_name=normalized_export,
            require_path=require_path,
            function_name=str(context.get("function_name", context.get("functionName"))) if context.get("function_name", context.get("functionName")) else normalized_export,
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )

    def hook_path(self) -> str:
        return _module_export_hook_path(self.require_path, self.module_id, self.export_name)


@dataclass(slots=True)
class ModuleHookResult:
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


@dataclass(slots=True)
class ModuleDiscoverySpec:
    """Runtime discovery request for webpack-like and custom module exports."""

    require_path: str = "window.__webpack_require__"
    module_runtime_paths: list[str] = field(default_factory=list)
    query: str | None = None
    max_candidates: int = 20
    max_preview_length: int = 240
    trigger_expression: str | None = None
    include_runtime_introspection: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleDiscoverySpec | None":
        context = context or {}
        discover_flag = context.get("discover_modules", context.get("discoverModules", context.get("module_discovery", context.get("moduleDiscovery"))))
        query = context.get("module_query", context.get("moduleQuery", context.get("query")))
        if not discover_flag and not query:
            return None
        require_path = str(context.get("require_path", context.get("requirePath", "window.__webpack_require__")) or "window.__webpack_require__").strip()
        module_runtime_paths = cls._coerce_paths(
            context.get(
                "module_runtime_paths",
                context.get(
                    "moduleRuntimePaths",
                    context.get(
                        "runtime_paths",
                        context.get("runtimePaths", context.get("federation_containers", context.get("federationContainers"))),
                    ),
                ),
            )
        )
        if require_path and require_path not in module_runtime_paths:
            module_runtime_paths.insert(0, require_path)
        return cls(
            require_path=require_path,
            module_runtime_paths=module_runtime_paths,
            query=str(query).strip() if query is not None and str(query).strip() else None,
            max_candidates=int(context.get("max_candidates", context.get("maxCandidates", 20)) or 20),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
            include_runtime_introspection=bool(
                context.get(
                    "include_runtime_introspection",
                    context.get("includeRuntimeIntrospection", context.get("runtime_module_introspection", context.get("runtimeModuleIntrospection", True))),
                )
            ),
        )

    @staticmethod
    def _coerce_paths(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            raw = [str(item).strip() for item in value if item is not None]
        else:
            raw = []
        paths: list[str] = []
        for item in raw:
            if item and item not in paths:
                paths.append(item)
        return paths


@dataclass(slots=True)
class ModuleDiscoveryResult:
    status: str
    scripts: list[dict[str, Any]] = field(default_factory=list)
    modules: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "script_count": len(self.scripts),
            "module_count": len(self.modules),
            "candidate_count": len(self.candidates),
            "scripts": self.scripts,
            "modules": self.modules,
            "candidates": self.candidates,
            "runtime": self.runtime,
            "trigger": self.trigger,
            "error": self.error,
            "reason": self.reason,
        }


class ModuleDiscoveryManager:
    """Best-effort webpack-like module discovery from runtime and source text."""

    def discover(self, page: BrowserPage, spec: ModuleDiscoverySpec | None) -> ModuleDiscoveryResult:
        if spec is None:
            return ModuleDiscoveryResult(status="unsupported", reason="missing_discovery_request")
        trigger = self._run_trigger(page, spec)
        runtime = self._discover_modules_from_runtime(page, spec)
        try:
            inventory = ScriptCollector().collect(page)
            scripts = self._list_of_dicts(inventory.get("scripts"))
        except Exception as exc:
            runtime_modules = self._list_of_dicts(runtime.get("modules"))
            candidates = self._build_candidates(runtime_modules, spec.require_path, max_candidates=spec.max_candidates)
            status = "success" if candidates else "failed"
            return ModuleDiscoveryResult(status=status, modules=runtime_modules, candidates=candidates, runtime=runtime, error=str(exc), trigger=trigger)
        runtime_modules = self._list_of_dicts(runtime.get("modules"))
        source_modules = self._discover_modules_from_scripts(scripts, query=spec.query, max_preview_length=spec.max_preview_length, max_candidates=spec.max_candidates)
        modules = self._dedupe_modules([*runtime_modules, *source_modules], max_candidates=spec.max_candidates)
        candidates = self._build_candidates(modules, spec.require_path, max_candidates=spec.max_candidates)
        status = "success" if modules or candidates else "partial" if scripts else "failed"
        return ModuleDiscoveryResult(status=status, scripts=scripts, modules=modules, candidates=candidates, runtime=runtime, trigger=trigger)

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: ModuleDiscoverySpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        try:
            payload = page.evaluate(spec.trigger_expression)
            return {"attempted": True, "ok": True, "result": payload if isinstance(payload, dict) else {"value": payload}}
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}

    @classmethod
    def _discover_modules_from_scripts(
        cls,
        scripts: list[dict[str, Any]],
        *,
        query: str | None,
        max_preview_length: int,
        max_candidates: int,
    ) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        query_lower = query.lower() if query else None
        for script in scripts:
            source = str(script.get("source") or "")
            if not source:
                continue
            if query_lower and query_lower not in source.lower() and query_lower not in str(script.get("url") or "").lower():
                continue
            for module in cls._extract_module_exports(source, max_preview_length=max_preview_length):
                module_entry = {
                    "scriptId": script.get("scriptId"),
                    "url": script.get("url"),
                    "kind": script.get("kind"),
                    "discovery_source": "script_inventory",
                    **module,
                }
                modules.append(module_entry)
                if len(modules) >= max_candidates:
                    return modules
        return modules

    @classmethod
    def _discover_modules_from_runtime(cls, page: BrowserPage, spec: ModuleDiscoverySpec) -> dict[str, Any]:
        if not spec.include_runtime_introspection:
            return {"status": "disabled", "modules": [], "reason": "runtime_introspection_disabled"}
        try:
            payload = page.evaluate(cls._runtime_introspection_expression(spec))
        except Exception as exc:
            return {"status": "failed", "modules": [], "error": str(exc)}
        if not isinstance(payload, dict):
            return {"status": "unsupported", "modules": [], "reason": "non_object_runtime_payload"}
        modules: list[dict[str, Any]] = []
        query_lower = spec.query.lower() if spec.query else None
        runtime_payloads = cls._normalize_runtime_payloads(payload, spec)
        runtime_kinds: list[str] = []
        runtime_paths: list[str] = []
        cache_key_count = 0
        registry_key_count = 0
        custom_key_count = 0
        federation_key_count = 0
        for runtime_payload in runtime_payloads:
            runtime_path = str(runtime_payload.get("runtimePath") or runtime_payload.get("requirePath") or spec.require_path)
            runtime_kind = str(runtime_payload.get("runtimeKind") or "webpack-require")
            if runtime_path and runtime_path not in runtime_paths:
                runtime_paths.append(runtime_path)
            if runtime_kind and runtime_kind not in runtime_kinds:
                runtime_kinds.append(runtime_kind)
            cache_key_count += int(runtime_payload.get("cacheKeyCount") or 0)
            registry_key_count += int(runtime_payload.get("registryKeyCount") or 0)
            custom_key_count += int(runtime_payload.get("customKeyCount") or 0)
            federation_key_count += int(runtime_payload.get("federationKeyCount") or 0)
            modules.extend(cls._modules_from_require_cache(runtime_payload, runtime_path, query_lower, page))
            modules.extend(cls._modules_from_registry(runtime_payload, runtime_path, query_lower, page, spec.max_preview_length))
            modules.extend(cls._modules_from_custom_runtime(runtime_payload, runtime_path, query_lower, page, spec.max_preview_length))
            modules.extend(cls._modules_from_federation(runtime_payload, runtime_path, query_lower, page, spec.max_preview_length))
        status = str(payload.get("status") or ("success" if modules else "partial" if payload.get("ok") else "unsupported"))
        return {
            "status": status,
            "ok": bool(payload.get("ok")),
            "require_path": payload.get("requirePath", spec.require_path),
            "runtime_paths": runtime_paths,
            "runtime_kinds": runtime_kinds,
            "cache_key_count": cache_key_count,
            "registry_key_count": registry_key_count,
            "custom_key_count": custom_key_count,
            "federation_key_count": federation_key_count,
            "module_count": len(modules),
            "modules": modules,
            "error": payload.get("error"),
            "reason": payload.get("reason"),
        }

    @classmethod
    def _normalize_runtime_payloads(cls, payload: dict[str, Any], spec: ModuleDiscoverySpec) -> list[dict[str, Any]]:
        runtimes = cls._list_of_dicts(payload.get("runtimes"))
        if runtimes:
            return runtimes
        legacy = {
            "runtimePath": payload.get("requirePath", spec.require_path),
            "runtimeKind": payload.get("runtimeKind", "webpack-require"),
            "cacheKeyCount": payload.get("cacheKeyCount", 0),
            "registryKeyCount": payload.get("registryKeyCount", 0),
            "customKeyCount": payload.get("customKeyCount", 0),
            "federationKeyCount": payload.get("federationKeyCount", 0),
            "cacheModules": payload.get("cacheModules", []),
            "registryModules": payload.get("registryModules", []),
            "customRuntimeModules": payload.get("customRuntimeModules", []),
            "federationModules": payload.get("federationModules", []),
        }
        return [legacy]

    @classmethod
    def _modules_from_require_cache(cls, payload: dict[str, Any], runtime_path: str, query_lower: str | None, page: BrowserPage) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        for item in cls._list_of_dicts(payload.get("cacheModules")):
            module_id = str(item.get("moduleId") or "")
            export_names = cls._normalize_export_names(item.get("exportNames"))
            module = {
                "module_id": module_id,
                "export_names": export_names,
                "export_count": len(export_names),
                "hook_paths": [_module_export_hook_path(runtime_path, module_id, name) for name in export_names],
                "hook_kind": "module-export",
                "runtime_path": runtime_path,
                "source_preview": item.get("sourcePreview") or "",
                "export_types": item.get("exportTypes") if isinstance(item.get("exportTypes"), dict) else {},
                "kind": "runtime-cache",
                "url": getattr(page, "url", None),
                "discovery_source": "runtime_cache",
            }
            if cls._module_matches_query(module, query_lower):
                modules.append(module)
        return modules

    @classmethod
    def _modules_from_registry(cls, payload: dict[str, Any], runtime_path: str, query_lower: str | None, page: BrowserPage, max_preview_length: int) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        for item in cls._list_of_dicts(payload.get("registryModules")):
            module_id = str(item.get("moduleId") or "")
            source = str(item.get("source") or item.get("sourcePreview") or "")
            export_names = cls._extract_export_names(cls._extract_module_exports_object(source) or source)
            module = {
                "module_id": module_id,
                "export_names": export_names,
                "export_count": len(export_names),
                "hook_paths": [_module_export_hook_path(runtime_path, module_id, name) for name in export_names],
                "hook_kind": "module-export",
                "runtime_path": runtime_path,
                "source_preview": str(item.get("sourcePreview") or source)[:max_preview_length],
                "kind": "runtime-registry",
                "url": getattr(page, "url", None),
                "discovery_source": "runtime_registry",
            }
            if cls._module_matches_query(module, query_lower):
                modules.append(module)
        return modules

    @classmethod
    def _modules_from_custom_runtime(cls, payload: dict[str, Any], runtime_path: str, query_lower: str | None, page: BrowserPage, max_preview_length: int) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        for item in cls._list_of_dicts(payload.get("customRuntimeModules")):
            module_id = str(item.get("moduleId") or item.get("path") or "")
            export_names = cls._normalize_export_names(item.get("exportNames"))
            hook_paths = cls._normalize_hook_paths(item.get("hookPaths"))
            module = {
                "module_id": module_id,
                "export_names": export_names,
                "export_count": len(export_names),
                "hook_paths": hook_paths,
                "hook_kind": "function-path",
                "runtime_path": runtime_path,
                "source_preview": str(item.get("sourcePreview") or "")[:max_preview_length],
                "export_types": item.get("exportTypes") if isinstance(item.get("exportTypes"), dict) else {},
                "kind": "custom-runtime",
                "url": getattr(page, "url", None),
                "discovery_source": "custom_runtime",
            }
            if cls._module_matches_query(module, query_lower):
                modules.append(module)
        return modules

    @classmethod
    def _modules_from_federation(cls, payload: dict[str, Any], runtime_path: str, query_lower: str | None, page: BrowserPage, max_preview_length: int) -> list[dict[str, Any]]:
        modules: list[dict[str, Any]] = []
        for item in cls._list_of_dicts(payload.get("federationModules")):
            module_id = str(item.get("moduleId") or item.get("exposedName") or "")
            export_names = cls._normalize_export_names(item.get("exportNames"))
            hook_paths = cls._normalize_hook_paths(item.get("hookPaths"))
            hook_kind = "function-path" if hook_paths else "federation-exposed-module"
            module = {
                "module_id": module_id,
                "export_names": export_names,
                "export_count": len(export_names),
                "hook_paths": hook_paths,
                "hook_kind": hook_kind,
                "runtime_path": runtime_path,
                "source_preview": str(item.get("sourcePreview") or "")[:max_preview_length],
                "export_types": item.get("exportTypes") if isinstance(item.get("exportTypes"), dict) else {},
                "kind": "module-federation",
                "url": getattr(page, "url", None),
                "discovery_source": "module_federation",
            }
            if cls._module_matches_query(module, query_lower):
                modules.append(module)
        return modules

    @staticmethod
    def _runtime_introspection_expression(spec: ModuleDiscoverySpec) -> str:
        require_path = json.dumps(spec.require_path)
        runtime_paths = json.dumps(spec.module_runtime_paths or [spec.require_path], ensure_ascii=False)
        max_preview_length = max(1, int(spec.max_preview_length))
        source_limit = max(2_000, min(max_preview_length * 20, 20_000))
        return f"""
(() => {{
  const marker = "__REVERSE_AGENT_MODULE_DISCOVERY__";
  const requirePath = {require_path};
  const runtimePaths = {runtime_paths};
  const maxPreviewLength = {max_preview_length};
  const sourceLimit = {source_limit};
  const describeValue = (value) => {{
    if (value === null) return "null";
    if (Array.isArray(value)) return "array";
    return typeof value;
  }};
  const accessPath = (basePath, property) => /^[A-Za-z_$][\\w$]*$/.test(String(property || ""))
    ? `${{basePath}}.${{property}}`
    : `${{basePath}}[${{JSON.stringify(String(property || ""))}}]`;
  const resolveRuntime = (path) => {{
    try {{
      return {{ ok: true, value: Function("return (" + path + ")")() }};
    }} catch (error) {{
      return {{ ok: false, error: String(error && error.message || error) }};
    }}
  }};
  const inspectWebpackRequire = (path, req) => {{
    if (!req || typeof req !== "function") {{
      return {{ runtimePath: path, runtimeKind: "webpack-require", ok: false, status: "unsupported", reason: "require_not_function", cacheModules: [], registryModules: [], customRuntimeModules: [], federationModules: [], cacheKeyCount: 0, registryKeyCount: 0, customKeyCount: 0, federationKeyCount: 0 }};
    }}
    const cache = req.c && typeof req.c === "object" ? req.c : {{}};
    const registry = req.m && typeof req.m === "object" ? req.m : {{}};
    const cacheKeys = Object.keys(cache);
    const registryKeys = Object.keys(registry);
    const cacheModules = [];
    for (const moduleId of cacheKeys) {{
      const moduleRecord = cache[moduleId] || {{}};
      const exportsValue = moduleRecord.exports;
      const exportTypes = {{}};
      let exportNames = [];
      let sourcePreview = "";
      if (exportsValue && typeof exportsValue === "object") {{
        exportNames = Object.keys(exportsValue).filter((name) => {{
          const value = exportsValue[name];
          exportTypes[name] = describeValue(value);
          return typeof value === "function";
        }});
        sourcePreview = exportNames.map((name) => String(exportsValue[name]).slice(0, maxPreviewLength)).join("\\n");
      }} else if (typeof exportsValue === "function") {{
        exportNames = ["default"];
        exportTypes.default = "function";
        sourcePreview = String(exportsValue).slice(0, maxPreviewLength);
      }}
      if (exportNames.length) {{
        cacheModules.push({{ moduleId, exportNames, exportTypes, sourcePreview }});
      }}
    }}
    const registryModules = [];
    for (const moduleId of registryKeys) {{
      const factory = registry[moduleId];
      if (typeof factory !== "function") continue;
      const source = String(factory).slice(0, sourceLimit);
      registryModules.push({{ moduleId, source, sourcePreview: source.slice(0, maxPreviewLength) }});
    }}
    return {{
      runtimePath: path,
      runtimeKind: "webpack-require",
      ok: true,
      status: cacheModules.length || registryModules.length ? "success" : "partial",
      cacheKeyCount: cacheKeys.length,
      registryKeyCount: registryKeys.length,
      customKeyCount: 0,
      federationKeyCount: 0,
      cacheModules,
      registryModules,
      customRuntimeModules: [],
      federationModules: [],
    }};
  }};
  const inspectObjectRuntime = (path, runtime) => {{
    const keys = runtime && typeof runtime === "object" ? Object.keys(runtime) : [];
    const modules = [];
    for (const key of keys) {{
      const value = runtime[key];
      if (typeof value === "function") {{
        modules.push({{
          moduleId: key,
          exportNames: [key],
          exportTypes: {{ [key]: "function" }},
          hookPaths: [accessPath(path, key)],
          sourcePreview: String(value).slice(0, maxPreviewLength)
        }});
      }} else if (value && typeof value === "object") {{
        const exportTypes = {{}};
        const exportNames = Object.keys(value).filter((name) => {{
          exportTypes[name] = describeValue(value[name]);
          return typeof value[name] === "function";
        }});
        if (exportNames.length) {{
          modules.push({{
            moduleId: key,
            exportNames,
            exportTypes,
            hookPaths: exportNames.map((name) => accessPath(accessPath(path, key), name)),
            sourcePreview: exportNames.map((name) => String(value[name]).slice(0, maxPreviewLength)).join("\\n")
          }});
        }}
      }}
    }}
    return {{
      runtimePath: path,
      runtimeKind: "object-runtime",
      ok: true,
      status: modules.length ? "success" : "partial",
      cacheKeyCount: 0,
      registryKeyCount: 0,
      customKeyCount: keys.length,
      federationKeyCount: 0,
      cacheModules: [],
      registryModules: [],
      customRuntimeModules: modules,
      federationModules: [],
    }};
  }};
  const inspectFederationContainer = (path, container) => {{
    const modules = [];
    const exposes = container && typeof container === "object" && container.__reverseAgentExposes && typeof container.__reverseAgentExposes === "object"
      ? container.__reverseAgentExposes
      : {{}};
    for (const exposedName of Object.keys(exposes)) {{
      const value = exposes[exposedName];
      const exportTypes = {{}};
      let exportNames = [];
      let hookPaths = [];
      let sourcePreview = "";
      if (typeof value === "function") {{
        exportNames = [exposedName];
        exportTypes[exposedName] = "function";
        hookPaths = [accessPath(accessPath(path, "__reverseAgentExposes"), exposedName)];
        sourcePreview = String(value).slice(0, maxPreviewLength);
      }} else if (value && typeof value === "object") {{
        exportNames = Object.keys(value).filter((name) => {{
          exportTypes[name] = describeValue(value[name]);
          return typeof value[name] === "function";
        }});
        hookPaths = exportNames.map((name) => accessPath(accessPath(accessPath(path, "__reverseAgentExposes"), exposedName), name));
        sourcePreview = exportNames.map((name) => String(value[name]).slice(0, maxPreviewLength)).join("\\n");
      }}
      if (exportNames.length) {{
        modules.push({{ moduleId: exposedName, exposedName, exportNames, exportTypes, hookPaths, sourcePreview }});
      }}
    }}
    return {{
      runtimePath: path,
      runtimeKind: "module-federation",
      ok: true,
      status: modules.length ? "success" : "partial",
      cacheKeyCount: 0,
      registryKeyCount: 0,
      customKeyCount: 0,
      federationKeyCount: Object.keys(exposes).length,
      cacheModules: [],
      registryModules: [],
      customRuntimeModules: [],
      federationModules: modules,
    }};
  }};
  try {{
    const paths = Array.from(new Set((runtimePaths && runtimePaths.length ? runtimePaths : [requirePath]).filter(Boolean)));
    const runtimes = [];
    const unavailable = [];
    for (const path of paths) {{
      const resolved = resolveRuntime(path);
      if (!resolved.ok) {{
        unavailable.push({{ runtimePath: path, reason: "runtime_path_unavailable", error: resolved.error }});
        continue;
      }}
      const value = resolved.value;
      if (typeof value === "function") {{
        runtimes.push(inspectWebpackRequire(path, value));
      }} else if (value && typeof value === "object" && (typeof value.get === "function" || typeof value.init === "function")) {{
        runtimes.push(inspectFederationContainer(path, value));
      }} else if (value && typeof value === "object") {{
        runtimes.push(inspectObjectRuntime(path, value));
      }} else {{
        unavailable.push({{ runtimePath: path, reason: "unsupported_runtime_type", valueType: describeValue(value) }});
      }}
    }}
    const cacheModules = runtimes.flatMap((item) => item.cacheModules || []);
    const registryModules = runtimes.flatMap((item) => item.registryModules || []);
    const customRuntimeModules = runtimes.flatMap((item) => item.customRuntimeModules || []);
    const federationModules = runtimes.flatMap((item) => item.federationModules || []);
    const cacheKeyCount = runtimes.reduce((total, item) => total + (item.cacheKeyCount || 0), 0);
    const registryKeyCount = runtimes.reduce((total, item) => total + (item.registryKeyCount || 0), 0);
    const customKeyCount = runtimes.reduce((total, item) => total + (item.customKeyCount || 0), 0);
    const federationKeyCount = runtimes.reduce((total, item) => total + (item.federationKeyCount || 0), 0);
    return {{
      marker,
      ok: runtimes.length > 0,
      status: cacheModules.length || registryModules.length || customRuntimeModules.length || federationModules.length ? "success" : runtimes.length ? "partial" : "unsupported",
      requirePath,
      runtimePaths: paths,
      cacheKeyCount,
      registryKeyCount,
      customKeyCount,
      federationKeyCount,
      cacheModules,
      registryModules,
      customRuntimeModules,
      federationModules,
      runtimes,
      unavailable,
      reason: runtimes.length ? undefined : "runtime_path_unavailable",
    }};
  }} catch (error) {{
    return {{ marker, ok: false, status: "failed", requirePath, cacheModules: [], registryModules: [], customRuntimeModules: [], federationModules: [], runtimes: [], error: String(error && error.message || error) }};
  }}
}})()
"""

    @staticmethod
    def _extract_module_exports(source: str, *, max_preview_length: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        module_pattern = re.compile(
            r"(?m)(?P<module_id>\d+)\s*:\s*(?:\([^)]*\)\s*=>\s*{|function\s*\([^)]*\)\s*{)"
        )
        for match in module_pattern.finditer(source):
            body_start = source.find("{", match.start())
            if body_start < 0:
                continue
            body_end = ModuleDiscoveryManager._find_matching_brace(source, body_start)
            if body_end is None:
                continue
            body = source[body_start + 1 : body_end]
            exports = ModuleDiscoveryManager._extract_module_exports_object(body)
            export_names = ModuleDiscoveryManager._extract_export_names(exports or body)
            preview = body[:max_preview_length]
            module_id = match.group("module_id")
            results.append(
                {
                    "module_id": module_id,
                    "export_names": export_names,
                    "export_count": len(export_names),
                    "hook_paths": [_module_export_hook_path("window.__webpack_require__", module_id, name) for name in export_names],
                    "source_preview": preview,
                }
            )
        return results

    @staticmethod
    def _extract_module_exports_object(module_body: str) -> str:
        assignment = re.search(r"module\.exports\s*=\s*{", module_body)
        if not assignment:
            return ""
        object_start = module_body.find("{", assignment.start())
        object_end = ModuleDiscoveryManager._find_matching_brace(module_body, object_start)
        if object_end is None:
            return ""
        return module_body[object_start + 1 : object_end]

    @staticmethod
    def _find_matching_brace(source: str, start: int) -> int | None:
        if start < 0 or start >= len(source) or source[start] != "{":
            return None
        depth = 0
        index = start
        in_string: str | None = None
        in_line_comment = False
        in_block_comment = False
        escape = False
        while index < len(source):
            char = source[index]
            next_char = source[index + 1] if index + 1 < len(source) else ""
            if in_line_comment:
                if char in "\r\n":
                    in_line_comment = False
                index += 1
                continue
            if in_block_comment:
                if char == "*" and next_char == "/":
                    in_block_comment = False
                    index += 2
                    continue
                index += 1
                continue
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == in_string:
                    in_string = None
                index += 1
                continue
            if char == "/" and next_char == "/":
                in_line_comment = True
                index += 2
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                continue
            if char in {"'", '"', "`"}:
                in_string = char
                index += 1
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    @staticmethod
    def _extract_export_names(source: str) -> list[str]:
        names: list[str] = []
        for match in re.finditer(r"(?m)^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\(", source):
            name = match.group(1)
            if name not in names:
                names.append(name)
        for match in re.finditer(r"(?m)^\s*([A-Za-z_$][\w$]*)\s*:", source):
            name = match.group(1)
            if name not in names:
                names.append(name)
        return names

    @staticmethod
    def _build_candidates(modules: list[dict[str, Any]], require_path: str, *, max_candidates: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        seen_hook_paths: set[str] = set()
        for module in modules:
            module_id = str(module.get("module_id") or "")
            hook_kind = str(module.get("hook_kind") or "module-export")
            module_hook_paths = ModuleDiscoveryManager._normalize_hook_paths(module.get("hook_paths"))
            for export_name in module.get("export_names", []) or []:
                if hook_kind == "function-path":
                    hook_path = ModuleDiscoveryManager._select_function_hook_path(module_hook_paths, str(export_name))
                    if not hook_path:
                        continue
                else:
                    hook_path = _module_export_hook_path(str(module.get("runtime_path") or require_path), module_id, str(export_name))
                if hook_path in seen_hook_paths:
                    continue
                seen_hook_paths.add(hook_path)
                candidates.append(
                    {
                        "module_id": module_id,
                        "export_name": export_name,
                        "hook_path": hook_path,
                        "hook_kind": hook_kind,
                        "runtime_path": module.get("runtime_path") or require_path,
                        "discovery_source": module.get("discovery_source"),
                        "function_name": export_name,
                        "source_preview": module.get("source_preview"),
                        "scriptId": module.get("scriptId"),
                        "url": module.get("url"),
                    }
                )
                if len(candidates) >= max_candidates:
                    return candidates
        return candidates

    @staticmethod
    def _dedupe_modules(modules: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[str, ...], str]] = set()
        for module in modules:
            module_id = str(module.get("module_id") or "")
            export_names = tuple(ModuleDiscoveryManager._normalize_export_names(module.get("export_names")))
            if not module_id or not export_names:
                continue
            key = (module_id, export_names, str(module.get("discovery_source") or ""), str(module.get("runtime_path") or ""), str(module.get("hook_kind") or ""))
            if key in seen:
                continue
            seen.add(key)
            normalized = dict(module)
            normalized["export_names"] = list(export_names)
            normalized["export_count"] = len(export_names)
            deduped.append(normalized)
            if len(deduped) >= max_candidates:
                break
        return deduped

    @staticmethod
    def _normalize_export_names(value: Any) -> list[str]:
        names: list[str] = []
        if not isinstance(value, list):
            return names
        for item in value:
            name = str(item).strip()
            if name and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _normalize_hook_paths(value: Any) -> list[str]:
        paths: list[str] = []
        if not isinstance(value, list):
            return paths
        for item in value:
            path = str(item).strip()
            if path and path not in paths:
                paths.append(path)
        return paths

    @staticmethod
    def _select_function_hook_path(hook_paths: list[str], export_name: str) -> str | None:
        if not hook_paths:
            return None
        suffix = f".{export_name}"
        bracket_suffix = f"[{json.dumps(export_name, ensure_ascii=False)}]"
        for path in hook_paths:
            if path.endswith(suffix) or path.endswith(bracket_suffix):
                return path
        return hook_paths[0] if len(hook_paths) == 1 else None

    @staticmethod
    def _module_matches_query(module: dict[str, Any], query_lower: str | None) -> bool:
        if not query_lower:
            return True
        haystacks = [
            str(module.get("module_id") or ""),
            str(module.get("source_preview") or ""),
            str(module.get("url") or ""),
            " ".join(str(name) for name in module.get("export_names", []) or []),
        ]
        return any(query_lower in haystack.lower() for haystack in haystacks)

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class ModuleHookManager:
    """Install best-effort wrappers around webpack-like module exports."""

    def install(self, page: BrowserPage, spec: ModuleHookSpec | None) -> ModuleHookResult:
        if spec is None:
            return ModuleHookResult(status="unsupported", error="missing_module_id_or_export_name")
        try:
            install_payload = page.evaluate(self._install_expression(spec))
        except Exception as exc:
            return ModuleHookResult(status="failed", error=str(exc))
        trigger = self._run_trigger(page, spec)
        try:
            snapshot_payload = page.evaluate(self._snapshot_expression(spec))
        except Exception as exc:
            snapshot_payload = {"ok": False, "events": [], "error": str(exc)}

        installed = self._list_of_dicts(install_payload.get("installed") if isinstance(install_payload, dict) else [])
        missing = self._list_of_dicts(install_payload.get("missing") if isinstance(install_payload, dict) else [])
        events = self._list_of_dicts(snapshot_payload.get("events") if isinstance(snapshot_payload, dict) else [])
        status = "success" if installed else "partial" if missing else "failed"
        return ModuleHookResult(
            status=status,
            installed=installed,
            missing=missing,
            events=events,
            trigger=trigger,
            error=install_payload.get("error") if isinstance(install_payload, dict) else None,
        )

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: ModuleHookSpec) -> dict[str, Any]:
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
    def _install_expression(spec: ModuleHookSpec) -> str:
        config = {
            "moduleId": spec.module_id,
            "exportName": spec.export_name,
            "requirePath": spec.require_path,
            "functionName": spec.function_name,
            "hookPath": spec.hook_path(),
            "captureArgs": spec.capture_args,
            "captureResult": spec.capture_result,
            "maxPreviewLength": spec.max_preview_length,
        }
        config_json = json.dumps(config, ensure_ascii=False)
        template = """(() => {
  const config = __REVERSE_AGENT_MODULE_HOOK_CONFIG__;
  const root = window.__reverseDeepAgentHooks = window.__reverseDeepAgentHooks || {
    installedAt: Date.now(),
    events: [],
    installed: {},
    push(type, payload) {
      try {
        this.events.push({ type, ts: Date.now(), payload });
        if (this.events.length > 300) this.events.shift();
      } catch (_) {}
    }
  };
  root.installed.module_hooks = root.installed.module_hooks || {};
  const preview = (value) => {
    try {
      if (value === undefined) return { type: 'undefined', preview: 'undefined' };
      if (value === null) return { type: 'null', preview: 'null' };
      if (typeof value === 'string') return { type: 'string', size: value.length, preview: value.slice(0, config.maxPreviewLength) };
      if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return { type: typeof value, preview: String(value) };
      if (typeof value === 'function') return { type: 'function', name: value.name || '', preview: '<function>' };
      const text = JSON.stringify(value);
      return { type: Array.isArray(value) ? 'array' : typeof value, size: text ? text.length : 0, preview: String(text || value).slice(0, config.maxPreviewLength) };
    } catch (_) {
      return { type: typeof value, preview: '<unavailable>' };
    }
  };
  const resolvePath = (path) => {
    const parts = String(path || '').split('.').filter(Boolean);
    if (!parts.length) return null;
    let owner = window;
    let index = 0;
    if (parts[0] === 'window') index = 1;
    for (; index < parts.length - 1; index++) {
      owner = owner && owner[parts[index]];
      if (!owner) return null;
    }
    const property = parts[parts.length - 1];
    return { owner, property, value: owner && owner[property] };
  };
  const moduleIdValue = /^\\d+$/.test(String(config.moduleId)) ? Number(config.moduleId) : config.moduleId;
  const installed = [];
  const missing = [];
  try {
    const resolvedRequire = resolvePath(config.requirePath);
    if (!resolvedRequire || typeof resolvedRequire.value !== 'function') {
      missing.push({ moduleId: config.moduleId, exportName: config.exportName, requirePath: config.requirePath, reason: 'require_function_not_found' });
      return { ok: false, installed, missing, eventCount: root.events.length };
    }
    const moduleExports = resolvedRequire.value.call(window, moduleIdValue);
    if (!moduleExports || typeof moduleExports !== 'object') {
      missing.push({ moduleId: config.moduleId, exportName: config.exportName, requirePath: config.requirePath, reason: 'module_exports_unavailable' });
      return { ok: false, installed, missing, eventCount: root.events.length };
    }
    const exportName = config.exportName;
    const original = moduleExports[exportName];
    if (typeof original !== 'function') {
      missing.push({ moduleId: config.moduleId, exportName, requirePath: config.requirePath, reason: 'export_function_not_found' });
      return { ok: false, installed, missing, eventCount: root.events.length };
    }
    if (original.__reverseAgentModuleHooked) {
      installed.push({ moduleId: config.moduleId, exportName, requirePath: config.requirePath, hookPath: config.hookPath, alreadyInstalled: true });
      return { ok: true, installed, missing, eventCount: root.events.length };
    }
    const wrapped = function reverseAgentModuleExportHookWrapper(...args) {
      const callId = `${config.moduleId}:${exportName}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
      root.push('module_export_call', {
        callId,
        moduleId: config.moduleId,
        exportName,
        functionName: config.functionName || exportName,
        requirePath: config.requirePath,
        hookPath: config.hookPath,
        argCount: args.length,
        args: config.captureArgs ? args.map(preview) : []
      });
      try {
        const result = original.apply(this, args);
        const recordReturn = (value) => {
          root.push('module_export_return', {
            callId,
            moduleId: config.moduleId,
            exportName,
            functionName: config.functionName || exportName,
            requirePath: config.requirePath,
            hookPath: config.hookPath,
            result: config.captureResult ? preview(value) : { preview: '<disabled>' }
          });
          return value;
        };
        if (result && typeof result.then === 'function') {
          return result.then(recordReturn, (error) => {
            root.push('module_export_throw', { callId, moduleId: config.moduleId, exportName, functionName: config.functionName || exportName, requirePath: config.requirePath, hookPath: config.hookPath, error: String(error && error.message || error) });
            throw error;
          });
        }
        return recordReturn(result);
      } catch (error) {
        root.push('module_export_throw', { callId, moduleId: config.moduleId, exportName, functionName: config.functionName || exportName, requirePath: config.requirePath, hookPath: config.hookPath, error: String(error && error.message || error) });
        throw error;
      }
    };
    try { Object.defineProperty(wrapped, 'name', { value: original.name || config.functionName || 'reverseAgentModuleExportHookWrapper' }); } catch (_) {}
    wrapped.__reverseAgentOriginal = original;
    wrapped.__reverseAgentModuleHooked = true;
    moduleExports[exportName] = wrapped;
    root.installed.module_hooks[config.hookPath] = true;
    installed.push({ moduleId: config.moduleId, exportName, functionName: config.functionName || exportName, requirePath: config.requirePath, hookPath: config.hookPath });
  } catch (error) {
    missing.push({ moduleId: config.moduleId, exportName: config.exportName, requirePath: config.requirePath, reason: 'install_error', error: String(error && error.message || error) });
  }
  return { ok: installed.length > 0, installed, missing, eventCount: root.events.length };
})()"""
        return template.replace("__REVERSE_AGENT_MODULE_HOOK_CONFIG__", config_json)

    @staticmethod
    def _snapshot_expression(spec: ModuleHookSpec) -> str:
        config_json = json.dumps({"moduleId": spec.module_id, "exportName": spec.export_name, "hookPath": spec.hook_path()}, ensure_ascii=False)
        template = """(() => {
  const root = window.__reverseDeepAgentHooks;
  if (!root) return { ok: false, events: [], eventCount: 0, reason: 'not_installed' };
  const config = __REVERSE_AGENT_MODULE_HOOK_SNAPSHOT_CONFIG__;
  const events = (root.events || []).filter((event) => event && event.payload && event.payload.moduleId === config.moduleId && event.payload.exportName === config.exportName && /^module_export_/.test(event.type));
  return { ok: true, events, eventCount: events.length, installed: Object.assign({}, (root.installed && root.installed.module_hooks) || {}) };
})()"""
        return template.replace("__REVERSE_AGENT_MODULE_HOOK_SNAPSHOT_CONFIG__", config_json)
