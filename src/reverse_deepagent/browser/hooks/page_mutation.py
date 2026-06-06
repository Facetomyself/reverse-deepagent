from __future__ import annotations

import json
import re
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
class ObjectRootMutationAuditSpec:
    """Explicit descriptor-safe JS object-root mutation audit request.

    The audit snapshots a strict dotted object root before and after an
    optional explicit trigger expression. It intentionally avoids prototype
    traversal and avoids invoking accessor getters while collecting snapshots.
    """

    root_path: str
    trigger_expression: str | None = None
    max_depth: int = 2
    max_keys: int = 80
    max_preview_length: int = 240
    include_descriptors: bool = True
    include_values: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ObjectRootMutationAuditSpec | None":
        context = context or {}
        root_path = cls._first_present(
            context,
            (
                "object_root",
                "objectRoot",
                "object_root_path",
                "objectRootPath",
                "root_path",
                "rootPath",
                "js_object_root",
                "jsObjectRoot",
            ),
        )
        if root_path is None:
            return None
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        return cls(
            root_path=str(root_path).strip(),
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            max_depth=max(0, int(context.get("max_depth", context.get("maxDepth", 2)) or 2)),
            max_keys=max(1, int(context.get("max_keys", context.get("maxKeys", 80)) or 80)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            include_descriptors=bool(context.get("include_descriptors", context.get("includeDescriptors", True))),
            include_values=bool(context.get("include_values", context.get("includeValues", False))),
        )

    @staticmethod
    def _first_present(context: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = context.get(key)
            if value is not None and str(value).strip():
                return value
        return None


@dataclass(slots=True)
class ObjectRootMutationAuditResult:
    status: str
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    diff: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
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
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class ObjectRootMutationAuditManager:
    """Descriptor-safe object-root snapshot diff around an explicit trigger."""

    _PATH_RE = re.compile(r"^(?:[A-Za-z_$][\w$]*)(?:\.[A-Za-z_$][\w$]*)*$")

    def audit(self, page: BrowserPage, spec: ObjectRootMutationAuditSpec | None) -> ObjectRootMutationAuditResult:
        policy = self._side_effect_policy(spec)
        if spec is None:
            return ObjectRootMutationAuditResult(status="unsupported", reason="missing_object_root_mutation_audit_spec", side_effect_policy=policy)
        if not self._is_safe_path(spec.root_path):
            return ObjectRootMutationAuditResult(
                status="blocked",
                reason="unsupported_object_root_path",
                side_effect_policy=policy,
            )
        before = self._snapshot(page, spec)
        trigger = self._run_trigger(page, spec)
        after = self._snapshot(page, spec)
        if before.get("ok") is False or after.get("ok") is False:
            return ObjectRootMutationAuditResult(
                status="failed",
                before=before,
                after=after,
                trigger=trigger,
                side_effect_policy=policy,
                error=str(before.get("error") or after.get("error") or before.get("reason") or after.get("reason") or "snapshot_failed"),
            )
        diff = self._diff_snapshots(before, after)
        status = "success" if diff.get("changed") else "partial"
        return ObjectRootMutationAuditResult(status=status, before=before, after=after, diff=diff, trigger=trigger, side_effect_policy=policy)

    @classmethod
    def _is_safe_path(cls, root_path: str) -> bool:
        return bool(root_path and cls._PATH_RE.fullmatch(root_path))

    @staticmethod
    def _snapshot(page: BrowserPage, spec: ObjectRootMutationAuditSpec) -> dict[str, Any]:
        try:
            payload = page.evaluate(ObjectRootMutationAuditManager._snapshot_expression(spec))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if isinstance(payload, dict):
            return payload
        return {"ok": False, "error": "non_object_snapshot_payload", "value_type": type(payload).__name__}

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: ObjectRootMutationAuditSpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        try:
            payload = page.evaluate(spec.trigger_expression)
            return {"attempted": True, "ok": True, "result": payload if isinstance(payload, dict) else {"value": payload}}
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}

    @staticmethod
    def _snapshot_expression(spec: ObjectRootMutationAuditSpec) -> str:
        config = {
            "rootPath": spec.root_path,
            "maxDepth": spec.max_depth,
            "maxKeys": spec.max_keys,
            "maxPreviewLength": spec.max_preview_length,
            "includeDescriptors": spec.include_descriptors,
            "includeValues": spec.include_values,
        }
        config_json = json.dumps(config, ensure_ascii=False)
        template = """(() => {
  const marker = "__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__";
  const config = __OBJECT_ROOT_MUTATION_AUDIT_CONFIG__;
  const identifierPattern = /^[A-Za-z_$][\\w$]*$/;
  const preview = (value) => {
    try {
      if (typeof value === "string") return value.slice(0, config.maxPreviewLength);
      if (typeof value === "function") return String(value).slice(0, config.maxPreviewLength);
      if (value === undefined) return "undefined";
      if (typeof value === "symbol") return String(value).slice(0, config.maxPreviewLength);
      if (typeof value === "bigint") return String(value).slice(0, config.maxPreviewLength);
      return JSON.stringify(value).slice(0, config.maxPreviewLength);
    } catch (_) {
      try { return Object.prototype.toString.call(value).slice(0, config.maxPreviewLength); } catch (__) { return "<unavailable>"; }
    }
  };
  const typeOf = (value) => {
    if (value === null) return "null";
    if (Array.isArray(value)) return "array";
    return typeof value;
  };
  const descriptorInfo = (descriptor) => {
    if (!descriptor) return { exists: false };
    const info = {
      exists: true,
      enumerable: !!descriptor.enumerable,
      configurable: !!descriptor.configurable,
      hasGetter: typeof descriptor.get === "function",
      hasSetter: typeof descriptor.set === "function",
      kind: Object.prototype.hasOwnProperty.call(descriptor, "value") ? "data" : "accessor"
    };
    if (Object.prototype.hasOwnProperty.call(descriptor, "writable")) info.writable = !!descriptor.writable;
    return info;
  };
  const ownDescriptor = (owner, key) => {
    try { return Object.getOwnPropertyDescriptor(owner, key); } catch (_) { return undefined; }
  };
  const resolveRoot = () => {
    const raw = String(config.rootPath || "");
    const parts = raw.split(".").filter(Boolean);
    if (!parts.length) return { ok: false, reason: "empty_root_path" };
    for (const part of parts) {
      if (!identifierPattern.test(part)) return { ok: false, reason: "unsupported_root_path", part };
    }
    let value = globalThis;
    let start = 0;
    if (["window", "globalThis", "self"].includes(parts[0])) {
      start = 1;
    }
    for (let index = start; index < parts.length; index += 1) {
      const part = parts[index];
      if (value == null || (typeof value !== "object" && typeof value !== "function")) {
        return { ok: false, reason: "root_path_parent_unavailable", path: parts.slice(0, index).join(".") };
      }
      const descriptor = ownDescriptor(value, part);
      if (!descriptor) return { ok: false, reason: "root_path_property_unavailable", path: parts.slice(0, index + 1).join(".") };
      if (!Object.prototype.hasOwnProperty.call(descriptor, "value")) {
        return { ok: false, reason: "root_path_accessor_not_invoked", path: parts.slice(0, index + 1).join(".") };
      }
      value = descriptor.value;
    }
    return { ok: true, value };
  };
  const seen = new WeakSet();
  const snapshotValue = (value, depth, path) => {
    const valueType = typeOf(value);
    const node = { path, type: valueType };
    if (valueType !== "object" && valueType !== "array" && valueType !== "function") {
      node.preview = preview(value);
      if (config.includeValues) node.value = value;
      return node;
    }
    if (typeof Window !== "undefined" && value === window) {
      node.summary = { host_object: "window" };
      return node;
    }
    if (typeof Node !== "undefined" && value instanceof Node) {
      node.summary = { host_object: "dom-node", node_name: value.nodeName || "", node_type: value.nodeType || 0 };
      return node;
    }
    if (valueType === "function") {
      node.name = value.name || "";
      node.preview = preview(value);
    }
    if (valueType === "array") node.length = value.length;
    if (seen.has(value)) {
      node.cycle = true;
      return node;
    }
    seen.add(value);
    if (depth >= config.maxDepth) {
      node.truncated = true;
      node.truncation_reason = "max_depth";
      return node;
    }
    let names = [];
    try { names = Object.getOwnPropertyNames(value); } catch (error) {
      node.truncated = true;
      node.truncation_reason = "own_property_names_unavailable";
      node.error = String(error && error.message || error);
      return node;
    }
    node.own_property_count = names.length;
    if (names.length > config.maxKeys) {
      node.truncated = true;
      node.truncation_reason = "max_keys";
    }
    node.children = {};
    for (const key of names.slice(0, config.maxKeys)) {
      const descriptor = ownDescriptor(value, key);
      const childPath = path + "." + key;
      const child = { path: childPath, key };
      if (config.includeDescriptors) child.descriptor = descriptorInfo(descriptor);
      if (!descriptor) {
        child.type = "unavailable";
      } else if (Object.prototype.hasOwnProperty.call(descriptor, "value")) {
        Object.assign(child, snapshotValue(descriptor.value, depth + 1, childPath));
        child.key = key;
        if (config.includeDescriptors) child.descriptor = descriptorInfo(descriptor);
      } else {
        child.type = "accessor";
        child.accessor = { hasGetter: typeof descriptor.get === "function", hasSetter: typeof descriptor.set === "function" };
      }
      node.children[key] = child;
    }
    return node;
  };
  try {
    const root = resolveRoot();
    if (!root.ok) return { marker, ok: false, status: "unsupported", root_path: config.rootPath, reason: root.reason, path: root.path || null, part: root.part || null };
    return {
      marker,
      ok: true,
      status: "success",
      root_path: config.rootPath,
      root: snapshotValue(root.value, 0, config.rootPath),
      side_effect_policy: {
        default_recon: false,
        trigger_required_for_mutation: true,
        getter_invocation: false,
        prototype_traversal: false,
        calls_mcp: false,
        mobile_runtime_used: false
      }
    };
  } catch (error) {
    return { marker, ok: false, status: "failed", root_path: config.rootPath, error: String(error && error.message || error) };
  }
})()"""
        return template.replace("__OBJECT_ROOT_MUTATION_AUDIT_CONFIG__", config_json)

    @classmethod
    def _diff_snapshots(cls, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        changes: list[dict[str, Any]] = []
        cls._compare_nodes(changes, before.get("root"), after.get("root"), before.get("root_path") or after.get("root_path") or "root")
        added_paths = [item["path"] for item in changes if item["category"] == "added"]
        removed_paths = [item["path"] for item in changes if item["category"] == "removed"]
        type_changed_paths = [item["path"] for item in changes if item["category"] == "type"]
        descriptor_changed_paths = [item["path"] for item in changes if item["category"] == "descriptor"]
        changed_paths = [item["path"] for item in changes if item["category"] in {"value", "summary", "structure", "truncation", "cycle"}]
        categories = sorted({item["category"] for item in changes})
        truncated = bool(cls._node_flag(before.get("root"), "truncated") or cls._node_flag(after.get("root"), "truncated"))
        cycles = bool(cls._node_flag(before.get("root"), "cycle") or cls._node_flag(after.get("root"), "cycle"))
        return {
            "changed": bool(changes),
            "change_count": len(changes),
            "categories": categories,
            "added_paths": added_paths,
            "removed_paths": removed_paths,
            "changed_paths": changed_paths,
            "type_changed_paths": type_changed_paths,
            "descriptor_changed_paths": descriptor_changed_paths,
            "truncated": truncated,
            "cycles": cycles,
            "changes": changes,
        }

    @classmethod
    def _compare_nodes(cls, changes: list[dict[str, Any]], before: Any, after: Any, path: str) -> None:
        if before is None and after is None:
            return
        if before is None:
            changes.append({"path": path, "category": "added", "after": cls._compact_node(after)})
            return
        if after is None:
            changes.append({"path": path, "category": "removed", "before": cls._compact_node(before)})
            return
        if not isinstance(before, dict) or not isinstance(after, dict):
            if before != after:
                changes.append({"path": path, "category": "value", "before": before, "after": after})
            return
        before_type = before.get("type")
        after_type = after.get("type")
        if before_type != after_type:
            changes.append({"path": path, "category": "type", "before": before_type, "after": after_type})
        for key in ("preview", "value", "length", "name"):
            if before.get(key) != after.get(key):
                changes.append({"path": path, "category": "value", "field": key, "before": before.get(key), "after": after.get(key)})
        if before.get("summary") != after.get("summary"):
            changes.append({"path": path, "category": "summary", "before": before.get("summary"), "after": after.get("summary")})
        if before.get("descriptor") != after.get("descriptor"):
            changes.append({"path": path, "category": "descriptor", "before": before.get("descriptor"), "after": after.get("descriptor")})
        for key in ("truncated", "truncation_reason", "own_property_count"):
            if before.get(key) != after.get(key):
                changes.append({"path": path, "category": "truncation" if key != "own_property_count" else "structure", "field": key, "before": before.get(key), "after": after.get(key)})
        if before.get("cycle") != after.get("cycle"):
            changes.append({"path": path, "category": "cycle", "before": before.get("cycle"), "after": after.get("cycle")})
        before_children = before.get("children") if isinstance(before.get("children"), dict) else {}
        after_children = after.get("children") if isinstance(after.get("children"), dict) else {}
        for key in sorted(set(before_children) | set(after_children)):
            cls._compare_nodes(changes, before_children.get(key), after_children.get(key), f"{path}.{key}")

    @staticmethod
    def _compact_node(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        return {key: node.get(key) for key in ("type", "preview", "length", "descriptor", "summary", "truncated", "cycle") if key in node}

    @classmethod
    def _node_flag(cls, node: Any, key: str) -> bool:
        if not isinstance(node, dict):
            return False
        if bool(node.get(key)):
            return True
        children = node.get("children") if isinstance(node.get("children"), dict) else {}
        return any(cls._node_flag(child, key) for child in children.values())

    @staticmethod
    def _side_effect_policy(spec: ObjectRootMutationAuditSpec | None) -> dict[str, Any]:
        return {
            "default_recon": False,
            "trigger_required_for_mutation": True,
            "getter_invocation": False,
            "prototype_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "root_path": spec.root_path if spec else None,
        }


@dataclass(slots=True)
class ObjectGraphDiffSpec:
    """Review-only JS object graph diff descriptor request.

    The manager consumes caller-provided before/after graph snapshots and never
    collects snapshots itself.  It is intentionally a descriptor layer beyond
    scoped object-root mutation audit, not a full heap snapshot engine.
    """

    before_snapshot: dict[str, Any] = field(default_factory=dict)
    after_snapshot: dict[str, Any] = field(default_factory=dict)
    graph_roots: list[str] = field(default_factory=list)
    max_depth: int = 4
    max_changes: int = 120
    max_preview_length: int = 240
    include_values: bool = False
    source: str = "caller_provided_snapshots"

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ObjectGraphDiffSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "object_graph_diff",
                "objectGraphDiff",
                "js_object_graph_diff",
                "jsObjectGraphDiff",
                "review_object_graph_diff",
                "reviewObjectGraphDiff",
            )
        )
        before = cls._coerce_snapshot(
            context.get(
                "before_snapshot",
                context.get("beforeSnapshot", context.get("before_graph", context.get("beforeGraph", context.get("before")))),
            )
        )
        after = cls._coerce_snapshot(
            context.get(
                "after_snapshot",
                context.get("afterSnapshot", context.get("after_graph", context.get("afterGraph", context.get("after")))),
            )
        )
        if not requested and not before and not after:
            return None
        return cls(
            before_snapshot=before,
            after_snapshot=after,
            graph_roots=cls._coerce_roots(context.get("graph_roots", context.get("graphRoots", context.get("root_paths", context.get("rootPaths"))))),
            max_depth=max(0, int(context.get("max_depth", context.get("maxDepth", 4)) or 4)),
            max_changes=max(1, int(context.get("max_changes", context.get("maxChanges", 120)) or 120)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            include_values=bool(context.get("include_values", context.get("includeValues", False))),
            source=str(context.get("snapshot_source", context.get("snapshotSource", "caller_provided_snapshots")) or "caller_provided_snapshots"),
        )

    @staticmethod
    def _coerce_snapshot(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _coerce_roots(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = [item.strip() for item in value.split(",")]
        elif isinstance(value, list):
            raw = [str(item).strip() for item in value if item is not None]
        else:
            raw = []
        roots: list[str] = []
        for item in raw:
            if item and item not in roots:
                roots.append(item)
        return roots


@dataclass(slots=True)
class ObjectGraphDiffResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ObjectGraphDiffManager:
    """Review-only diff over caller-provided JS object graph snapshots."""

    _SENSITIVE_RE = re.compile(r"token|secret|password|passwd|cookie|authorization|apikey|api_key|credential", re.IGNORECASE)
    _MISSING = object()

    def review(self, spec: ObjectGraphDiffSpec | None) -> ObjectGraphDiffResult:
        policy = self._side_effect_policy()
        if spec is None:
            return ObjectGraphDiffResult(status="unsupported", reason="missing_object_graph_diff_request", side_effect_policy=policy)
        if not spec.before_snapshot or not spec.after_snapshot:
            descriptor = self._base_descriptor(spec, status="blocked", reason="missing_before_or_after_snapshot")
            return ObjectGraphDiffResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_before_or_after_snapshot")
        try:
            descriptor = self._descriptor(spec)
            return ObjectGraphDiffResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(spec, status="failed", reason="object_graph_diff_failed")
            descriptor["error"] = str(exc)
            return ObjectGraphDiffResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="object_graph_diff_failed", error=str(exc))

    def _descriptor(self, spec: ObjectGraphDiffSpec) -> dict[str, Any]:
        diff = self._diff_graphs(spec)
        risk = self._risk_summary(diff)
        return {
            "schema_version": "reverse-deepagent.object-graph-diff.v1",
            "status": "ready_for_review",
            "review_only": True,
            "graph_request": {
                "graph_roots": spec.graph_roots,
                "snapshot_source": spec.source,
                "max_depth": spec.max_depth,
                "max_changes": spec.max_changes,
                "include_values": spec.include_values,
            },
            "snapshot_summary": {
                "before": self._snapshot_summary(spec.before_snapshot),
                "after": self._snapshot_summary(spec.after_snapshot),
            },
            "diff": diff,
            "changed": bool(diff.get("changed")),
            "change_count": int(diff.get("change_count") or 0),
            "risk_summary": risk,
            "hook_readiness": {
                "review_before_hook_or_replay": True,
                "object_root_followup_candidates": self._object_root_candidates(diff),
                "runtime_collection_required_for_full_heap": True,
                "automatic_heap_snapshot_supported": False,
                "automatic_runtime_hook_supported": False,
            },
            "blockers": [],
            "next_action": "review_object_graph_diff_before_hook_or_replay" if diff.get("changed") else "provide_broader_before_after_graph_snapshots",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, spec: ObjectGraphDiffSpec, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.object-graph-diff.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "graph_request": {
                "graph_roots": spec.graph_roots,
                "snapshot_source": spec.source,
                "max_depth": spec.max_depth,
                "max_changes": spec.max_changes,
                "include_values": spec.include_values,
            },
            "snapshot_summary": {
                "before": self._snapshot_summary(spec.before_snapshot),
                "after": self._snapshot_summary(spec.after_snapshot),
            },
            "diff": {"changed": False, "change_count": 0, "categories": [], "changes": []},
            "changed": False,
            "change_count": 0,
            "risk_summary": {"risk": "low", "reasons": []},
            "hook_readiness": {
                "review_before_hook_or_replay": False,
                "object_root_followup_candidates": [],
                "runtime_collection_required_for_full_heap": True,
                "automatic_heap_snapshot_supported": False,
                "automatic_runtime_hook_supported": False,
            },
            "blockers": [reason],
            "next_action": "provide_before_and_after_object_graph_snapshots",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _diff_graphs(self, spec: ObjectGraphDiffSpec) -> dict[str, Any]:
        before_root = spec.before_snapshot.get("root")
        after_root = spec.after_snapshot.get("root")
        if isinstance(before_root, dict) and isinstance(after_root, dict):
            diff = ObjectRootMutationAuditManager._diff_snapshots(spec.before_snapshot, spec.after_snapshot)
            return self._bounded_diff(diff, spec.max_changes)
        changes: list[dict[str, Any]] = []
        self._compare_json_values(changes, spec.before_snapshot, spec.after_snapshot, "graph", depth=0, spec=spec)
        categories = sorted({item["category"] for item in changes})
        return {
            "diff_engine": "json_graph_snapshot",
            "changed": bool(changes),
            "change_count": len(changes),
            "categories": categories,
            "added_paths": [item["path"] for item in changes if item["category"] == "added"],
            "removed_paths": [item["path"] for item in changes if item["category"] == "removed"],
            "changed_paths": [item["path"] for item in changes if item["category"] in {"value", "structure"}],
            "type_changed_paths": [item["path"] for item in changes if item["category"] == "type"],
            "descriptor_changed_paths": [],
            "truncated": any(bool(item.get("truncated")) for item in changes),
            "cycles": False,
            "changes": changes,
        }

    def _compare_json_values(self, changes: list[dict[str, Any]], before: Any, after: Any, path: str, *, depth: int, spec: ObjectGraphDiffSpec) -> None:
        if len(changes) >= spec.max_changes:
            return
        if before is self._MISSING and after is self._MISSING:
            return
        if before is self._MISSING:
            changes.append({"path": path, "category": "added", "after": self._preview(path, after, spec)})
            return
        if after is self._MISSING:
            changes.append({"path": path, "category": "removed", "before": self._preview(path, before, spec)})
            return
        if before is None and after is None:
            return
        if depth > spec.max_depth:
            if before != after:
                changes.append({"path": path, "category": "structure", "truncated": True, "reason": "max_depth"})
            return
            return
        before_type = self._json_type(before)
        after_type = self._json_type(after)
        if before_type != after_type:
            changes.append({"path": path, "category": "type", "before": before_type, "after": after_type})
            return
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after)):
                self._compare_json_values(changes, before.get(key, self._MISSING), after.get(key, self._MISSING), f"{path}.{key}", depth=depth + 1, spec=spec)
                if len(changes) >= spec.max_changes:
                    return
            return
        if isinstance(before, list) and isinstance(after, list):
            if len(before) != len(after):
                changes.append({"path": path, "category": "structure", "field": "length", "before": len(before), "after": len(after)})
            for index, (before_item, after_item) in enumerate(zip(before, after)):
                self._compare_json_values(changes, before_item, after_item, f"{path}[{index}]", depth=depth + 1, spec=spec)
                if len(changes) >= spec.max_changes:
                    return
            return
        if before != after:
            changes.append({"path": path, "category": "value", "before": self._preview(path, before, spec), "after": self._preview(path, after, spec)})

    @staticmethod
    def _json_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return type(value).__name__

    def _preview(self, path: str, value: Any, spec: ObjectGraphDiffSpec) -> Any:
        if value is self._MISSING:
            return "<missing>"
        if self._SENSITIVE_RE.search(path):
            return "<redacted>"
        if (spec.include_values and isinstance(value, (str, int, float, bool))) or value is None:
            return value
        text = str(value)
        return text[: spec.max_preview_length]

    def _bounded_diff(self, diff: dict[str, Any], max_changes: int) -> dict[str, Any]:
        bounded = dict(diff)
        changes = diff.get("changes") if isinstance(diff.get("changes"), list) else []
        bounded["diff_engine"] = "object_root_snapshot"
        bounded["changes"] = [self._redact_change(item) for item in changes[:max_changes] if isinstance(item, dict)]
        bounded["change_count"] = len(bounded["changes"])
        bounded["changed"] = bool(bounded["changes"])
        bounded["truncated_changes"] = max(0, len(changes) - len(bounded["changes"]))
        return bounded

    def _redact_change(self, change: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(change)
        path = str(redacted.get("path") or "")
        if not self._SENSITIVE_RE.search(path):
            return redacted
        if "before" in redacted:
            redacted["before"] = "<redacted>"
        if "after" in redacted:
            redacted["after"] = "<redacted>"
        redacted["redacted"] = True
        return redacted

    def _risk_summary(self, diff: dict[str, Any]) -> dict[str, Any]:
        categories = set(diff.get("categories") if isinstance(diff.get("categories"), list) else [])
        paths = [str(item.get("path") or "") for item in diff.get("changes", []) if isinstance(item, dict)]
        reasons: list[str] = []
        if categories.intersection({"descriptor", "type", "removed"}):
            reasons.append("shape_or_descriptor_changed")
        if any(self._SENSITIVE_RE.search(path) for path in paths):
            reasons.append("sensitive_like_path_changed")
        if diff.get("truncated") or diff.get("truncated_changes"):
            reasons.append("diff_truncated")
        risk = "high" if "sensitive_like_path_changed" in reasons else "medium" if reasons else "low"
        return {"risk": risk, "reasons": reasons, "category_count": len(categories)}

    @staticmethod
    def _object_root_candidates(diff: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        for key in ("added_paths", "removed_paths", "changed_paths", "type_changed_paths", "descriptor_changed_paths"):
            values = diff.get(key) if isinstance(diff.get(key), list) else []
            for path in values:
                text = str(path)
                parts = text.split(".")
                if len(parts) >= 2:
                    candidate = ".".join(parts[:2])
                    if candidate not in candidates:
                        candidates.append(candidate)
                if len(candidates) >= 10:
                    return candidates
        return candidates

    @classmethod
    def _snapshot_summary(cls, snapshot: dict[str, Any]) -> dict[str, Any]:
        root = snapshot.get("root") if isinstance(snapshot.get("root"), dict) else None
        return {
            "present": bool(snapshot),
            "format": "object_root_snapshot" if root else "json_graph_snapshot" if snapshot else "missing",
            "root_path": snapshot.get("root_path") or (root.get("path") if root else ""),
            "top_level_keys": sorted(str(key) for key in snapshot.keys())[:40],
            "node_count_estimate": cls._count_nodes(root if root else snapshot, limit=1000),
        }

    @classmethod
    def _count_nodes(cls, value: Any, *, limit: int) -> int:
        if limit <= 0:
            return 0
        if isinstance(value, dict):
            children = value.get("children") if isinstance(value.get("children"), dict) else value
            count = 1
            for child in children.values():
                count += cls._count_nodes(child, limit=limit - count)
                if count >= limit:
                    return limit
            return count
        if isinstance(value, list):
            count = 1
            for child in value:
                count += cls._count_nodes(child, limit=limit - count)
                if count >= limit:
                    return limit
            return count
        return 1

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "snapshots_collected_by_manager": False,
            "files_mutated": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "trigger_executed": False,
            "getter_invocation": False,
            "prototype_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "full_heap_snapshot": False,
        }


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
