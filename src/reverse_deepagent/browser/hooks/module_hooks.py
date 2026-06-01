from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.collectors.scripts import ScriptCollector


JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
JS_DOTTED_PATH_RE = re.compile(r"^(?:window\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$")


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
    chunk_graph: dict[str, Any] = field(default_factory=dict)
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
            "chunk_graph_status": self.chunk_graph.get("status") if self.chunk_graph else "not_attempted",
            "chunk_graph_candidate_count": int(self.chunk_graph.get("candidate_count") or 0) if self.chunk_graph else 0,
            "scripts": self.scripts,
            "modules": self.modules,
            "candidates": self.candidates,
            "chunk_graph": self.chunk_graph,
            "runtime": self.runtime,
            "trigger": self.trigger,
            "error": self.error,
            "reason": self.reason,
        }


@dataclass(slots=True)
class CustomLoaderTraversalPlanSpec:
    """Plan-only custom loader / non-webpack async traversal request."""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    traversal_depth: int = 1
    max_candidates: int = 20
    max_preview_length: int = 240
    review_approved: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalPlanSpec | None":
        context = context or {}
        candidates = cls._candidate_records(context)
        if not candidates:
            candidate = cls._single_candidate_from_context(context)
            if candidate:
                candidates.append(candidate)
        traversal_requested = bool(
            context.get("custom_loader_traversal")
            or context.get("customLoaderTraversal")
            or context.get("loader_traversal_plan")
            or context.get("loaderTraversalPlan")
        )
        if not candidates and not traversal_requested:
            return None
        return cls(
            candidates=cls._dedupe_candidates(candidates, max_candidates=int(context.get("max_candidates", context.get("maxCandidates", 20)) or 20)),
            traversal_depth=max(0, int(context.get("traversal_depth", context.get("traversalDepth", 1)) or 1)),
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
        )

    @classmethod
    def _candidate_records(cls, context: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for key in (
            "custom_loader_candidate",
            "customLoaderCandidate",
            "custom_loader_candidates",
            "customLoaderCandidates",
            "loader_candidates",
            "loaderCandidates",
            "chunk_candidates",
            "chunkCandidates",
        ):
            records.extend(cls._list_of_dicts(context.get(key)))
            value = context.get(key)
            if isinstance(value, dict):
                records.append(value)
        chunk_graph = context.get("chunk_graph", context.get("chunkGraph"))
        if isinstance(chunk_graph, dict):
            records.extend(cls._list_of_dicts(chunk_graph.get("candidates")))
            records.extend(cls._list_of_dicts(chunk_graph.get("customLoaderCandidates")))
            records.extend(cls._list_of_dicts(chunk_graph.get("loaderCandidates")))
        return [dict(item) for item in records]

    @staticmethod
    def _single_candidate_from_context(context: dict[str, Any]) -> dict[str, Any] | None:
        chunk_id = context.get("chunk_id", context.get("chunkId"))
        target = context.get("target", context.get("chunk_target", context.get("chunkTarget")))
        loader_path = context.get("loader_path", context.get("loaderPath"))
        loader_kind = context.get("loader_kind", context.get("loaderKind"))
        if chunk_id is None and target is None and loader_path is None and loader_kind is None:
            return None
        return {
            "chunk_id": str(chunk_id or target or loader_path or "").strip(),
            "target": str(target or loader_path or chunk_id or "").strip(),
            "loader_path": str(loader_path or target or "").strip(),
            "loader_kind": str(loader_kind or "custom-loader").strip() or "custom-loader",
            "edge_type": str(context.get("edge_type", context.get("edgeType", "custom-loader-candidate")) or "custom-loader-candidate"),
            "runtime_path": str(context.get("runtime_path", context.get("runtimePath", "")) or ""),
            "discovery_source": str(context.get("discovery_source", context.get("discoverySource", "explicit_context")) or "explicit_context"),
        }

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _dedupe_candidates(candidates: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            key = (
                str(candidate.get("edge_type") or candidate.get("edgeType") or ""),
                str(candidate.get("loader_kind") or candidate.get("loaderKind") or ""),
                str(candidate.get("target") or candidate.get("chunk_id") or candidate.get("chunkId") or ""),
                str(candidate.get("runtime_path") or candidate.get("runtimePath") or candidate.get("loader_path") or candidate.get("loaderPath") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
            if len(deduped) >= max_candidates:
                break
        return deduped


@dataclass(slots=True)
class CustomLoaderTraversalPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class CustomLoaderTraversalPlanManager:
    """Build a reviewable traversal plan without executing arbitrary loaders."""

    WEBPACK_KINDS = {"webpack-runtime", "webpack-require"}
    DYNAMIC_IMPORT_KINDS = {"es-dynamic-import", "dynamic-import"}
    FEDERATION_KINDS = {"module-federation", "federation-container", "federation-remote"}

    def plan(self, spec: CustomLoaderTraversalPlanSpec | None) -> CustomLoaderTraversalPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return CustomLoaderTraversalPlanResult(status="unsupported", reason="missing_custom_loader_traversal_request", side_effect_policy=policy)
        planned_candidates = [self._candidate_plan(item, index=index, spec=spec) for index, item in enumerate(spec.candidates)]
        summary = self._summary(planned_candidates)
        plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-plan.v1",
            "status": "ready_for_review" if planned_candidates else "blocked",
            "review_required": True,
            "review_approved_input_ignored": bool(spec.review_approved),
            "traversal_depth": spec.traversal_depth,
            "candidate_count": len(planned_candidates),
            "custom_candidate_count": summary["custom_candidate_count"],
            "blocked_execution_count": summary["blocked_execution_count"],
            "ready_for_review_count": summary["ready_for_review_count"],
            "candidates": planned_candidates,
            "approval_requirements": [
                "confirm_loader_candidate_origin",
                "classify_loader_side_effects",
                "review_network_request_scope",
                "review_module_factory_execution_risk",
                "prefer_webpack_async_chunk_load_when_loader_kind_is_supported",
            ],
            "side_effect_policy": policy,
            "next_action": "review_custom_loader_traversal_plan" if planned_candidates else "provide_custom_loader_candidates_from_chunk_graph",
        }
        return CustomLoaderTraversalPlanResult(status="planned" if planned_candidates else "blocked", plan=plan, side_effect_policy=policy, reason=None if planned_candidates else "no_custom_loader_candidates")

    @classmethod
    def _candidate_plan(cls, candidate: dict[str, Any], *, index: int, spec: CustomLoaderTraversalPlanSpec) -> dict[str, Any]:
        loader_kind = str(candidate.get("loader_kind") or candidate.get("loaderKind") or "custom-loader") or "custom-loader"
        edge_type = str(candidate.get("edge_type") or candidate.get("edgeType") or "custom-loader-candidate") or "custom-loader-candidate"
        chunk_id = str(candidate.get("chunk_id") or candidate.get("chunkId") or candidate.get("target") or "")[: spec.max_preview_length]
        target = str(candidate.get("target") or candidate.get("url") or candidate.get("href") or chunk_id)[: spec.max_preview_length]
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or target)[: spec.max_preview_length]
        runtime_path = str(candidate.get("runtime_path") or candidate.get("runtimePath") or "")[: spec.max_preview_length]
        classification = cls._classify(loader_kind, edge_type=edge_type)
        return {
            "index": index,
            "status": classification["status"],
            "risk_level": classification["risk_level"],
            "classification": classification["classification"],
            "chunk_id": chunk_id,
            "target": target,
            "loader_path": loader_path,
            "loader_kind": loader_kind,
            "edge_type": edge_type,
            "runtime_path": runtime_path,
            "discovery_source": str(candidate.get("discovery_source") or candidate.get("discoverySource") or "unknown"),
            "execution_supported": False,
            "traversal_supported": False,
            "automatic_execution": False,
            "recommended_follow_up": classification["recommended_follow_up"],
            "blocking_reasons": classification["blocking_reasons"],
            "review_requirements": classification["review_requirements"],
            "side_effect_policy": {
                "would_call_loader_if_executed": True,
                "would_request_chunk_if_executed": classification["would_request_chunk"],
                "would_execute_dynamic_import_if_executed": classification["dynamic_import"],
                "would_execute_module_federation_get_init_if_executed": classification["federation"],
                "module_factory_may_execute_if_followed": True,
                "executed_now": False,
                "chunk_request_sent_now": False,
                "module_factory_invoked_now": False,
            },
        }

    @classmethod
    def _classify(cls, loader_kind: str, *, edge_type: str) -> dict[str, Any]:
        normalized = loader_kind.strip().lower()
        edge = edge_type.strip().lower()
        if normalized in cls.WEBPACK_KINDS:
            return {
                "status": "redirect_to_async_chunk_load_baseline",
                "risk_level": "medium",
                "classification": "webpack_loader_supported_elsewhere",
                "recommended_follow_up": "use_async_chunk_load_with_review_approval",
                "blocking_reasons": ["custom_traversal_not_needed_for_supported_webpack_loader"],
                "review_requirements": ["use_existing_async_chunk_load_plan", "inspect_registry_diff_after_reviewed_load"],
                "would_request_chunk": True,
                "dynamic_import": False,
                "federation": False,
            }
        if normalized in cls.DYNAMIC_IMPORT_KINDS or edge == "dynamic-import":
            return {
                "status": "blocked",
                "risk_level": "high",
                "classification": "dynamic_import_execution_required",
                "recommended_follow_up": "inspect_static_chunk_url_or_source_map_before_runtime_import",
                "blocking_reasons": ["dynamic_import_executes_module_body"],
                "review_requirements": ["prove_module_body_side_effects_are_safe", "prefer_source_inventory_or_network_metadata"],
                "would_request_chunk": True,
                "dynamic_import": True,
                "federation": False,
            }
        if normalized in cls.FEDERATION_KINDS or "federation" in edge:
            return {
                "status": "blocked",
                "risk_level": "high",
                "classification": "module_federation_get_init_required",
                "recommended_follow_up": "plan_module_federation_get_init_analysis",
                "blocking_reasons": ["module_federation_get_init_may_execute_remote_code"],
                "review_requirements": ["review_shared_scope", "review_remote_container_origin", "avoid_get_init_without_dedicated_gate"],
                "would_request_chunk": True,
                "dynamic_import": False,
                "federation": True,
            }
        return {
            "status": "ready_for_review",
            "risk_level": "high",
            "classification": "arbitrary_custom_loader",
            "recommended_follow_up": "review_loader_contract_before_any_execution",
            "blocking_reasons": ["arbitrary_loader_execution_not_supported"],
            "review_requirements": ["identify_loader_contract", "prove_chunk_url_without_calling_loader", "review_network_and_module_factory_side_effects"],
            "would_request_chunk": True,
            "dynamic_import": False,
            "federation": False,
        }

    @staticmethod
    def _summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "custom_candidate_count": sum(1 for item in candidates if item.get("classification") == "arbitrary_custom_loader"),
            "blocked_execution_count": sum(1 for item in candidates if item.get("blocking_reasons")),
            "ready_for_review_count": sum(1 for item in candidates if item.get("status") == "ready_for_review"),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "loader_invoked": False,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "dynamic_import_executed": False,
            "custom_loader_executed": False,
            "module_factory_invoked": False,
            "module_federation_get_init_executed": False,
            "browser_state_mutated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ModuleFederationGetInitPlanSpec:
    """Plan-only Module Federation container init/get analysis request."""

    candidates: list[dict[str, Any]] = field(default_factory=list)
    max_candidates: int = 20
    max_preview_length: int = 240
    review_approved: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationGetInitPlanSpec | None":
        context = context or {}
        max_candidates = max(1, int(context.get("max_candidates", context.get("maxCandidates", 20)) or 20))
        candidates = cls._candidate_records(context)
        if not candidates:
            candidate = cls._single_candidate_from_context(context)
            if candidate:
                candidates.append(candidate)
        requested = bool(
            context.get("module_federation_get_init")
            or context.get("moduleFederationGetInit")
            or context.get("federation_get_init_plan")
            or context.get("federationGetInitPlan")
            or context.get("module_federation_plan")
            or context.get("moduleFederationPlan")
        )
        if not candidates and not requested:
            return None
        return cls(
            candidates=cls._dedupe_candidates(candidates, max_candidates=max_candidates),
            max_candidates=max_candidates,
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
        )

    @classmethod
    def _candidate_records(cls, context: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for key in (
            "module_federation_candidate",
            "moduleFederationCandidate",
            "module_federation_candidates",
            "moduleFederationCandidates",
            "federation_candidate",
            "federationCandidate",
            "federation_candidates",
            "federationCandidates",
            "federation_modules",
            "federationModules",
            "module_federation_modules",
            "moduleFederationModules",
            "exposed_modules",
            "exposedModules",
        ):
            value = context.get(key)
            records.extend(cls._list_of_dicts(value))
            if isinstance(value, dict):
                records.append(value)
        records.extend(cls._federation_records_from_module_candidates(context.get("module_candidates", context.get("moduleCandidates"))))
        records.extend(cls._federation_records_from_runtime(context.get("runtime")))
        records.extend(cls._federation_records_from_runtime(context.get("module_discovery_runtime", context.get("moduleDiscoveryRuntime"))))
        module_discovery = context.get("module_discovery", context.get("moduleDiscovery"))
        if isinstance(module_discovery, dict):
            records.extend(cls._federation_records_from_module_candidates(module_discovery.get("modules")))
            records.extend(cls._federation_records_from_runtime(module_discovery.get("runtime")))
        return [dict(item) for item in records]

    @staticmethod
    def _single_candidate_from_context(context: dict[str, Any]) -> dict[str, Any] | None:
        container_path = context.get("container_path", context.get("containerPath", context.get("runtime_path", context.get("runtimePath"))))
        exposed_name = context.get("exposed_name", context.get("exposedName", context.get("module_id", context.get("moduleId"))))
        remote_name = context.get("remote_name", context.get("remoteName"))
        if container_path is None and exposed_name is None and remote_name is None:
            return None
        return {
            "container_path": str(container_path or "").strip(),
            "runtime_path": str(container_path or "").strip(),
            "exposed_name": str(exposed_name or "").strip(),
            "module_id": str(exposed_name or "").strip(),
            "remote_name": str(remote_name or "").strip(),
            "export_names": context.get("export_names", context.get("exportNames", [])),
            "hook_paths": context.get("hook_paths", context.get("hookPaths", [])),
            "discovery_source": str(context.get("discovery_source", context.get("discoverySource", "explicit_context")) or "explicit_context"),
        }

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _federation_records_from_module_candidates(cls, value: Any) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in cls._list_of_dicts(value):
            if (
                str(item.get("kind") or "").lower() == "module-federation"
                or str(item.get("discovery_source") or item.get("discoverySource") or "").lower() == "module_federation"
                or str(item.get("hook_kind") or item.get("hookKind") or "").lower() == "federation-exposed-module"
            ):
                records.append(item)
        return records

    @classmethod
    def _federation_records_from_runtime(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        records: list[dict[str, Any]] = []
        records.extend(cls._list_of_dicts(value.get("federationModules")))
        for runtime in cls._list_of_dicts(value.get("runtimes")):
            runtime_path = runtime.get("runtimePath") or runtime.get("runtime_path") or value.get("runtimePath") or value.get("runtime_path")
            for item in cls._list_of_dicts(runtime.get("federationModules")):
                record = dict(item)
                if runtime_path and not (record.get("runtime_path") or record.get("runtimePath") or record.get("container_path") or record.get("containerPath")):
                    record["runtime_path"] = runtime_path
                records.append(record)
        return records

    @staticmethod
    def _dedupe_candidates(candidates: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for candidate in candidates:
            container_path = str(candidate.get("container_path") or candidate.get("containerPath") or candidate.get("runtime_path") or candidate.get("runtimePath") or "")
            exposed_name = str(candidate.get("exposed_name") or candidate.get("exposedName") or candidate.get("module_id") or candidate.get("moduleId") or "")
            remote_name = str(candidate.get("remote_name") or candidate.get("remoteName") or "")
            key = (container_path, exposed_name, remote_name)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
            if len(deduped) >= max_candidates:
                break
        return deduped


@dataclass(slots=True)
class ModuleFederationGetInitPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class ModuleFederationGetInitPlanManager:
    """Build a reviewable Module Federation init/get plan without executing remote code."""

    def plan(self, spec: ModuleFederationGetInitPlanSpec | None) -> ModuleFederationGetInitPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return ModuleFederationGetInitPlanResult(status="unsupported", reason="missing_module_federation_get_init_request", side_effect_policy=policy)
        candidates = [self._candidate_plan(candidate, index=index, spec=spec) for index, candidate in enumerate(spec.candidates)]
        summary = self._summary(candidates)
        plan = {
            "schema_version": "reverse-deepagent.module-federation-get-init-plan.v1",
            "status": "ready_for_review" if candidates else "blocked",
            "review_required": True,
            "review_approved_input_ignored": bool(spec.review_approved),
            "candidate_count": len(candidates),
            "container_count": summary["container_count"],
            "exposed_module_count": summary["exposed_module_count"],
            "function_path_candidate_count": summary["function_path_candidate_count"],
            "ready_for_review_count": summary["ready_for_review_count"],
            "blocked_execution_count": summary["blocked_execution_count"],
            "candidates": candidates,
            "approval_requirements": [
                "confirm_remote_container_origin",
                "review_shared_scope_mutation_risk",
                "review_container_init_side_effects",
                "review_remote_get_side_effects",
                "review_remote_factory_execution_risk",
                "prefer_existing_function_path_candidate_when_available",
            ],
            "side_effect_policy": policy,
            "next_action": "review_module_federation_get_init_plan" if candidates else "provide_module_federation_candidates_from_module_discovery",
        }
        return ModuleFederationGetInitPlanResult(status="planned" if candidates else "blocked", plan=plan, side_effect_policy=policy, reason=None if candidates else "no_module_federation_candidates")

    @classmethod
    def _candidate_plan(cls, candidate: dict[str, Any], *, index: int, spec: ModuleFederationGetInitPlanSpec) -> dict[str, Any]:
        container_path = str(candidate.get("container_path") or candidate.get("containerPath") or candidate.get("runtime_path") or candidate.get("runtimePath") or "")[: spec.max_preview_length]
        exposed_name = str(candidate.get("exposed_name") or candidate.get("exposedName") or candidate.get("module_id") or candidate.get("moduleId") or "")[: spec.max_preview_length]
        remote_name = str(candidate.get("remote_name") or candidate.get("remoteName") or "")[: spec.max_preview_length]
        export_names = cls._string_list(candidate.get("export_names") or candidate.get("exportNames"))[:20]
        hook_paths = cls._string_list(candidate.get("hook_paths") or candidate.get("hookPaths"))[:20]
        classification = cls._classify(container_path=container_path, exposed_name=exposed_name, hook_paths=hook_paths)
        return {
            "index": index,
            "status": classification["status"],
            "risk_level": classification["risk_level"],
            "classification": classification["classification"],
            "container_path": container_path,
            "remote_name": remote_name,
            "exposed_name": exposed_name,
            "module_id": exposed_name,
            "export_names": export_names,
            "export_count": len(export_names),
            "hook_paths": hook_paths,
            "function_path_candidate_available": bool(hook_paths),
            "discovery_source": str(candidate.get("discovery_source") or candidate.get("discoverySource") or "unknown"),
            "execution_supported": False,
            "automatic_execution": False,
            "recommended_follow_up": classification["recommended_follow_up"],
            "blocking_reasons": classification["blocking_reasons"],
            "review_requirements": classification["review_requirements"],
            "side_effect_policy": {
                "would_execute_container_init_if_followed": True,
                "would_call_remote_get_if_followed": bool(exposed_name),
                "would_invoke_remote_factory_if_followed": bool(exposed_name),
                "would_mutate_shared_scope_if_followed": True,
                "executed_now": False,
                "container_init_executed_now": False,
                "remote_get_called_now": False,
                "remote_factory_invoked_now": False,
                "shared_scope_mutated_now": False,
            },
        }

    @classmethod
    def _classify(cls, *, container_path: str, exposed_name: str, hook_paths: list[str]) -> dict[str, Any]:
        if not container_path:
            return {
                "status": "blocked",
                "risk_level": "high",
                "classification": "missing_container_path",
                "recommended_follow_up": "provide_federation_container_path_from_module_discovery",
                "blocking_reasons": ["module_federation_container_path_required"],
                "review_requirements": ["identify_container_global_or_runtime_path"],
            }
        if not JS_DOTTED_PATH_RE.fullmatch(container_path):
            return {
                "status": "blocked",
                "risk_level": "high",
                "classification": "unsupported_container_path",
                "recommended_follow_up": "provide_strict_dotted_container_path",
                "blocking_reasons": ["dynamic_container_path_execution_not_supported"],
                "review_requirements": ["replace_expression_with_strict_dotted_runtime_path"],
            }
        if hook_paths:
            return {
                "status": "ready_for_review",
                "risk_level": "medium",
                "classification": "function_path_candidate_available",
                "recommended_follow_up": "prefer_hook_function_candidate_without_get_init_execution",
                "blocking_reasons": ["module_federation_get_init_execution_not_supported"],
                "review_requirements": ["review_existing_function_path_candidate", "avoid_container_get_init_when_function_path_is_available"],
            }
        if exposed_name:
            return {
                "status": "ready_for_review",
                "risk_level": "high",
                "classification": "remote_exposed_module_get_init_required",
                "recommended_follow_up": "review_module_federation_get_init_before_any_execution",
                "blocking_reasons": ["container_init_may_mutate_shared_scope", "container_get_may_return_remote_factory", "remote_factory_executes_remote_module_body"],
                "review_requirements": ["review_remote_container_origin", "review_shared_scope", "prove_remote_factory_side_effects_are_safe"],
            }
        return {
            "status": "ready_for_review",
            "risk_level": "high",
            "classification": "container_init_only_candidate",
            "recommended_follow_up": "review_container_init_side_effects_before_any_execution",
            "blocking_reasons": ["container_init_may_mutate_shared_scope"],
            "review_requirements": ["review_shared_scope", "review_container_origin"],
        }

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return []

    @staticmethod
    def _summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "container_count": len({item.get("container_path") for item in candidates if item.get("container_path")}),
            "exposed_module_count": sum(1 for item in candidates if item.get("exposed_name")),
            "function_path_candidate_count": sum(1 for item in candidates if item.get("function_path_candidate_available")),
            "ready_for_review_count": sum(1 for item in candidates if item.get("status") == "ready_for_review"),
            "blocked_execution_count": sum(1 for item in candidates if item.get("blocking_reasons")),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, bool]:
        return {
            "plan_only": True,
            "container_init_executed": False,
            "remote_get_called": False,
            "remote_factory_invoked": False,
            "shared_scope_mutated": False,
            "remote_code_executed": False,
            "network_request_sent": False,
            "browser_state_mutated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ModuleFederationGetInitProbeSpec:
    """Review-gated single Module Federation init/get probe request."""

    candidate: dict[str, Any] = field(default_factory=dict)
    execute_get_init: bool = False
    review_approved: bool = False
    share_scope_path: str = "window.__webpack_share_scopes__.default"
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationGetInitProbeSpec | None":
        context = context or {}
        execute_get_init = bool(
            context.get("execute_module_federation_get_init")
            or context.get("executeModuleFederationGetInit")
            or context.get("probe_module_federation_get_init")
            or context.get("probeModuleFederationGetInit")
            or context.get("execute_get_init")
            or context.get("executeGetInit")
        )
        plan_spec = ModuleFederationGetInitPlanSpec.from_context(context)
        if plan_spec is None and not execute_get_init:
            return None
        candidate = plan_spec.candidates[0] if plan_spec and plan_spec.candidates else {}
        return cls(
            candidate=dict(candidate),
            execute_get_init=execute_get_init,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
            share_scope_path=str(context.get("share_scope_path", context.get("shareScopePath", "window.__webpack_share_scopes__.default")) or "window.__webpack_share_scopes__.default"),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

    def to_plan_spec(self) -> ModuleFederationGetInitPlanSpec:
        return ModuleFederationGetInitPlanSpec(
            candidates=[dict(self.candidate)] if self.candidate else [],
            max_candidates=1,
            max_preview_length=self.max_preview_length,
            review_approved=self.review_approved,
        )


@dataclass(slots=True)
class ModuleFederationGetInitProbeResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class ModuleFederationGetInitProbeManager:
    """Plan and explicitly run a reviewed single container.init/container.get probe."""

    def plan_or_probe(self, page: BrowserPage, spec: ModuleFederationGetInitProbeSpec | None) -> ModuleFederationGetInitProbeResult:
        if spec is None:
            return ModuleFederationGetInitProbeResult(status="unsupported", reason="missing_module_federation_get_init_request")
        plan_result = ModuleFederationGetInitPlanManager().plan(spec.to_plan_spec())
        plan = plan_result.plan
        if not spec.execute_get_init:
            return ModuleFederationGetInitProbeResult(
                status="planned",
                plan=plan,
                execution={"attempted": False, "reason": "execute_module_federation_get_init_not_requested"},
                side_effect_policy=plan_result.side_effect_policy,
            )
        if not spec.review_approved:
            return ModuleFederationGetInitProbeResult(
                status="blocked",
                plan=plan,
                execution={"attempted": False, "reason": "review_approval_required"},
                side_effect_policy=plan_result.side_effect_policy,
                reason="review_approval_required",
            )
        candidates = plan.get("candidates") if isinstance(plan.get("candidates"), list) else []
        candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        readiness_error = self._execution_readiness_error(candidate, spec)
        if readiness_error:
            return ModuleFederationGetInitProbeResult(
                status="blocked",
                plan=plan,
                execution={"attempted": False, "reason": readiness_error},
                side_effect_policy=plan_result.side_effect_policy,
                reason=readiness_error,
            )
        try:
            payload = page.evaluate(self._probe_expression(candidate, spec))
        except Exception as exc:
            return ModuleFederationGetInitProbeResult(
                status="failed",
                plan=plan,
                execution={"attempted": True, "ok": False, "error": str(exc)},
                side_effect_policy=self._executed_side_effect_policy(),
                error=str(exc),
            )
        execution = payload if isinstance(payload, dict) else {"attempted": True, "ok": False, "result": payload}
        status = "success" if execution.get("ok") else "failed"
        return ModuleFederationGetInitProbeResult(status=status, plan=plan, execution=execution, side_effect_policy=self._executed_side_effect_policy())

    @staticmethod
    def _execution_readiness_error(candidate: dict[str, Any], spec: ModuleFederationGetInitProbeSpec) -> str | None:
        if not candidate:
            return "no_module_federation_candidate"
        if candidate.get("status") == "blocked":
            return str(candidate.get("classification") or "candidate_blocked")
        container_path = str(candidate.get("container_path") or "")
        exposed_name = str(candidate.get("exposed_name") or "")
        if not container_path or not JS_DOTTED_PATH_RE.fullmatch(container_path):
            return "strict_dotted_container_path_required"
        if not exposed_name:
            return "exposed_module_name_required"
        if candidate.get("function_path_candidate_available"):
            return "prefer_existing_function_path_candidate"
        if not JS_DOTTED_PATH_RE.fullmatch(spec.share_scope_path):
            return "strict_dotted_share_scope_path_required"
        return None

    @staticmethod
    def _executed_side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only_by_default": False,
            "requires_execute_module_federation_get_init": True,
            "requires_review_approval": True,
            "container_init_executed": True,
            "remote_get_called": True,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "shared_scope_may_mutate": True,
            "network_request_may_be_sent": True,
            "browser_state_mutated": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _path_parts(path: str) -> list[str]:
        parts = [item for item in str(path or "").split(".") if item]
        if parts and parts[0] == "window":
            parts = parts[1:]
        return parts

    @classmethod
    def _probe_expression(cls, candidate: dict[str, Any], spec: ModuleFederationGetInitProbeSpec) -> str:
        container_path = json.dumps(str(candidate.get("container_path") or ""), ensure_ascii=False)
        exposed_name = json.dumps(str(candidate.get("exposed_name") or ""), ensure_ascii=False)
        share_scope_path = json.dumps(spec.share_scope_path, ensure_ascii=False)
        container_parts = json.dumps(cls._path_parts(str(candidate.get("container_path") or "")), ensure_ascii=False)
        share_scope_parts = json.dumps(cls._path_parts(spec.share_scope_path), ensure_ascii=False)
        max_preview_length = max(1, int(spec.max_preview_length))
        return f"""
(async () => {{
  const marker = "__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__";
  const containerPath = {container_path};
  const exposedName = {exposed_name};
  const shareScopePath = {share_scope_path};
  const containerParts = {container_parts};
  const shareScopeParts = {share_scope_parts};
  const maxPreviewLength = {max_preview_length};
  const describeError = (error) => String(error && (error.stack || error.message) || error).slice(0, maxPreviewLength);
  const resolvePath = (parts) => {{
    try {{
      let value = window;
      for (const part of parts) {{
        if (!part || !/^[A-Za-z_$][\\w$]*$/.test(part)) return {{ ok: false, error: "unsafe_path_segment" }};
        value = value && value[part];
      }}
      return {{ ok: true, value }};
    }} catch (error) {{
      return {{ ok: false, error: describeError(error) }};
    }}
  }};
  const keys = (value) => value && typeof value === "object" ? Object.keys(value).map(String).sort() : [];
  const diffKeys = (before, after) => after.filter((item) => !before.includes(item));
  const containerResolved = resolvePath(containerParts);
  if (!containerResolved.ok || !containerResolved.value) {{
    return {{ marker, attempted: true, ok: false, status: "failed", reason: "container_unavailable", containerPath, exposedName, error: containerResolved.error }};
  }}
  const container = containerResolved.value;
  const shareScopeResolved = resolvePath(shareScopeParts);
  const shareScope = shareScopeResolved.ok && shareScopeResolved.value && typeof shareScopeResolved.value === "object" ? shareScopeResolved.value : {{}};
  const beforeSharedScopeKeys = keys(shareScope);
  const beforeContainerKeys = keys(container);
  let containerInitCalled = false;
  let remoteGetCalled = false;
  let factoryType = "";
  try {{
    if (typeof container.init === "function") {{
      containerInitCalled = true;
      await container.init(shareScope);
    }}
    if (typeof container.get !== "function") {{
      return {{
        marker,
        attempted: true,
        ok: false,
        status: "failed",
        reason: "container_get_missing",
        containerPath,
        exposedName,
        containerInitCalled,
        remoteGetCalled: false,
        remoteFactoryInvoked: false,
        beforeSharedScopeKeys,
        afterSharedScopeKeys: keys(shareScope),
        addedSharedScopeKeys: diffKeys(beforeSharedScopeKeys, keys(shareScope)),
        beforeContainerKeys,
        afterContainerKeys: keys(container)
      }};
    }}
    remoteGetCalled = true;
    const factory = await container.get(exposedName);
    factoryType = typeof factory;
    const afterSharedScopeKeys = keys(shareScope);
    const afterContainerKeys = keys(container);
    return {{
      marker,
      attempted: true,
      ok: true,
      status: "success",
      containerPath,
      exposedName,
      shareScopePath,
      containerInitCalled,
      remoteGetCalled,
      remoteFactoryInvoked: false,
      remoteCodeExecuted: false,
      factoryType,
      beforeSharedScopeKeys,
      afterSharedScopeKeys,
      addedSharedScopeKeys: diffKeys(beforeSharedScopeKeys, afterSharedScopeKeys),
      beforeContainerKeys,
      afterContainerKeys,
      addedContainerKeys: diffKeys(beforeContainerKeys, afterContainerKeys),
      reviewRequiredBeforeFactoryInvocation: true
    }};
  }} catch (error) {{
    return {{
      marker,
      attempted: true,
      ok: false,
      status: "failed",
      reason: "module_federation_get_init_probe_error",
      containerPath,
      exposedName,
      containerInitCalled,
      remoteGetCalled,
      remoteFactoryInvoked: false,
      error: describeError(error),
      beforeSharedScopeKeys,
      afterSharedScopeKeys: keys(shareScope),
      addedSharedScopeKeys: diffKeys(beforeSharedScopeKeys, keys(shareScope)),
      beforeContainerKeys,
      afterContainerKeys: keys(container)
    }};
  }}
}})()
"""


@dataclass(slots=True)
class AsyncChunkLoadSpec:
    """Review-gated async chunk load request derived from chunk graph candidates."""

    chunk_id: str
    target: str = ""
    loader_kind: str = "webpack-runtime"
    edge_type: str = "runtime-async-chunk"
    runtime_path: str = "window.__webpack_require__"
    loader_path: str | None = None
    execute_chunk_load: bool = False
    review_approved: bool = False
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkLoadSpec | None":
        context = context or {}
        candidate = context.get("chunk_candidate", context.get("chunkCandidate"))
        candidate_payload = candidate if isinstance(candidate, dict) else {}
        chunk_id = (
            context.get("chunk_id")
            or context.get("chunkId")
            or candidate_payload.get("chunk_id")
            or candidate_payload.get("chunkId")
            or candidate_payload.get("target")
        )
        target = str(context.get("chunk_target", context.get("chunkTarget", candidate_payload.get("target", ""))) or "")
        if chunk_id is None and not target:
            return None
        normalized_chunk_id = str(chunk_id or target).strip()
        if not normalized_chunk_id:
            return None
        loader_kind = str(context.get("loader_kind", context.get("loaderKind", candidate_payload.get("loader_kind", candidate_payload.get("loaderKind", "webpack-runtime")))) or "webpack-runtime").strip()
        edge_type = str(context.get("edge_type", context.get("edgeType", candidate_payload.get("edge_type", candidate_payload.get("edgeType", "runtime-async-chunk")))) or "runtime-async-chunk").strip()
        runtime_path = str(context.get("runtime_path", context.get("runtimePath", candidate_payload.get("runtime_path", candidate_payload.get("runtimePath", "window.__webpack_require__")))) or "window.__webpack_require__").strip()
        loader_path_value = context.get("loader_path", context.get("loaderPath", candidate_payload.get("loader_path", candidate_payload.get("loaderPath"))))
        return cls(
            chunk_id=normalized_chunk_id,
            target=target,
            loader_kind=loader_kind,
            edge_type=edge_type,
            runtime_path=runtime_path,
            loader_path=str(loader_path_value).strip() if loader_path_value else None,
            execute_chunk_load=bool(context.get("execute_chunk_load", context.get("executeChunkLoad", False))),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
        )


@dataclass(slots=True)
class AsyncChunkLoadResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class AsyncChunkLoadManager:
    """Plan and explicitly execute reviewed async chunk loading without module factory invocation."""

    SUPPORTED_EXECUTION_LOADER_KINDS = {"webpack-runtime", "webpack-require"}

    def plan_or_execute(self, page: BrowserPage, spec: AsyncChunkLoadSpec | None) -> AsyncChunkLoadResult:
        if spec is None:
            return AsyncChunkLoadResult(status="unsupported", reason="missing_async_chunk_load_request")
        plan = self._build_plan(spec)
        if not spec.execute_chunk_load:
            return AsyncChunkLoadResult(
                status="planned",
                plan=plan,
                execution={"attempted": False, "reason": "execute_chunk_load_not_requested"},
                side_effect_policy=plan["side_effect_policy"],
            )
        if not spec.review_approved:
            return AsyncChunkLoadResult(
                status="blocked",
                plan=plan,
                execution={"attempted": False, "reason": "review_approval_required"},
                side_effect_policy=plan["side_effect_policy"],
                reason="review_approval_required",
            )
        if spec.loader_kind not in self.SUPPORTED_EXECUTION_LOADER_KINDS:
            return AsyncChunkLoadResult(
                status="blocked",
                plan=plan,
                execution={"attempted": False, "reason": "unsupported_loader_kind_for_execution", "loader_kind": spec.loader_kind},
                side_effect_policy=plan["side_effect_policy"],
                reason="unsupported_loader_kind_for_execution",
            )
        runtime_path_parts = self._runtime_path_parts(spec.runtime_path)
        if runtime_path_parts is None:
            return AsyncChunkLoadResult(
                status="blocked",
                plan=plan,
                execution={"attempted": False, "reason": "unsupported_runtime_path_for_execution", "runtime_path": spec.runtime_path},
                side_effect_policy=plan["side_effect_policy"],
                reason="unsupported_runtime_path_for_execution",
            )
        try:
            payload = page.evaluate(self._execution_expression(spec, runtime_path_parts=runtime_path_parts))
        except Exception as exc:
            return AsyncChunkLoadResult(
                status="failed",
                plan=plan,
                execution={"attempted": True, "ok": False, "error": str(exc)},
                side_effect_policy=self._executed_side_effect_policy(),
                error=str(exc),
            )
        execution = payload if isinstance(payload, dict) else {"attempted": True, "ok": False, "result": payload}
        status = "success" if execution.get("ok") else "failed"
        return AsyncChunkLoadResult(status=status, plan=plan, execution=execution, side_effect_policy=self._executed_side_effect_policy())

    @staticmethod
    def _build_plan(spec: AsyncChunkLoadSpec) -> dict[str, Any]:
        supported = spec.loader_kind in AsyncChunkLoadManager.SUPPORTED_EXECUTION_LOADER_KINDS
        return {
            "schema_version": "reverse-deepagent.async-chunk-load-plan.v1",
            "status": "ready_for_review" if supported else "blocked",
            "chunk_id": spec.chunk_id,
            "target": spec.target,
            "loader_kind": spec.loader_kind,
            "edge_type": spec.edge_type,
            "runtime_path": spec.runtime_path,
            "loader_path": spec.loader_path,
            "review_required": True,
            "execution_supported": supported,
            "approval_requirements": [
                "confirm_chunk_candidate_origin",
                "approve_runtime_loader_execution",
                "inspect_module_registry_diff_after_load",
            ],
            "side_effect_policy": {
                "plan_only_by_default": True,
                "requires_execute_chunk_load": True,
                "requires_review_approval": True,
                "would_execute_runtime_loader": supported,
                "would_request_chunk": supported,
                "dynamic_import_executed": False,
                "custom_loader_executed": False,
                "module_factory_invoked": False,
                "module_federation_get_init_executed": False,
                "calls_mcp": False,
            },
            "next_action": "approve_execute_async_chunk_load" if supported else "choose_supported_webpack_runtime_chunk_candidate",
        }

    @staticmethod
    def _executed_side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only_by_default": False,
            "requires_execute_chunk_load": True,
            "requires_review_approval": True,
            "runtime_loader_executed": True,
            "chunk_request_sent": True,
            "dynamic_import_executed": False,
            "custom_loader_executed": False,
            "module_factory_invoked": False,
            "module_federation_get_init_executed": False,
            "calls_mcp": False,
        }

    @staticmethod
    def _runtime_path_parts(runtime_path: str) -> list[str] | None:
        normalized = str(runtime_path or "").strip()
        if not normalized or not JS_DOTTED_PATH_RE.fullmatch(normalized):
            return None
        parts = [item for item in normalized.split(".") if item]
        if parts and parts[0] == "window":
            parts = parts[1:]
        return parts or None

    @staticmethod
    def _execution_expression(spec: AsyncChunkLoadSpec, *, runtime_path_parts: list[str]) -> str:
        chunk_id = json.dumps(spec.chunk_id, ensure_ascii=False)
        runtime_path = json.dumps(spec.runtime_path, ensure_ascii=False)
        runtime_parts = json.dumps(runtime_path_parts, ensure_ascii=False)
        max_preview_length = max(1, int(spec.max_preview_length))
        return f"""
(async () => {{
  const marker = "__REVERSE_AGENT_ASYNC_CHUNK_LOAD__";
  const chunkId = {chunk_id};
  const runtimePath = {runtime_path};
  const runtimePathParts = {runtime_parts};
  const maxPreviewLength = {max_preview_length};
  const describeError = (error) => String(error && (error.stack || error.message) || error).slice(0, maxPreviewLength);
  const resolveRuntime = (parts) => {{
    try {{
      let value = window;
      for (const part of parts) {{
        if (!part || !/^[A-Za-z_$][\w$]*$/.test(part)) return {{ ok: false, error: 'unsafe_runtime_path_segment' }};
        value = value && value[part];
      }}
      return {{ ok: true, value }};
    }} catch (error) {{
      return {{ ok: false, error: describeError(error) }};
    }}
  }};
  const registryKeys = (req) => req && req.m && typeof req.m === "object" ? Object.keys(req.m).map(String).sort() : [];
  const cacheKeys = (req) => req && req.c && typeof req.c === "object" ? Object.keys(req.c).map(String).sort() : [];
  const diffKeys = (before, after) => after.filter((item) => !before.includes(item));
  const resolved = resolveRuntime(runtimePathParts);
  if (!resolved.ok) {{
    return {{ marker, attempted: true, ok: false, status: "failed", reason: "runtime_path_unavailable", runtimePath, chunkId, error: resolved.error }};
  }}
  const req = resolved.value;
  if (!req || typeof req.e !== "function") {{
    return {{ marker, attempted: true, ok: false, status: "failed", reason: "ensure_chunk_loader_missing", runtimePath, chunkId }};
  }}
  const beforeRegistry = registryKeys(req);
  const beforeCache = cacheKeys(req);
  try {{
    await req.e(chunkId);
  }} catch (error) {{
    return {{
      marker,
      attempted: true,
      ok: false,
      status: "failed",
      reason: "ensure_chunk_loader_failed",
      runtimePath,
      chunkId,
      beforeRegistryCount: beforeRegistry.length,
      beforeCacheCount: beforeCache.length,
      error: describeError(error)
    }};
  }}
  const afterRegistry = registryKeys(req);
  const afterCache = cacheKeys(req);
  return {{
    marker,
    attempted: true,
    ok: true,
    status: "success",
    runtimePath,
    chunkId,
    beforeRegistryCount: beforeRegistry.length,
    afterRegistryCount: afterRegistry.length,
    addedRegistryKeys: diffKeys(beforeRegistry, afterRegistry).slice(0, 50),
    beforeCacheCount: beforeCache.length,
    afterCacheCount: afterCache.length,
    addedCacheKeys: diffKeys(beforeCache, afterCache).slice(0, 50),
    moduleFactoryInvoked: false
  }};
}})()
"""


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
            chunk_graph = self._build_chunk_graph([], runtime, query=spec.query, max_candidates=spec.max_candidates)
            status = "success" if candidates or int(chunk_graph.get("candidate_count") or 0) else "failed"
            return ModuleDiscoveryResult(status=status, modules=runtime_modules, candidates=candidates, chunk_graph=chunk_graph, runtime=runtime, error=str(exc), trigger=trigger)
        runtime_modules = self._list_of_dicts(runtime.get("modules"))
        source_modules = self._discover_modules_from_scripts(scripts, query=spec.query, max_preview_length=spec.max_preview_length, max_candidates=spec.max_candidates)
        modules = self._dedupe_modules([*runtime_modules, *source_modules], max_candidates=spec.max_candidates)
        candidates = self._build_candidates(modules, spec.require_path, max_candidates=spec.max_candidates)
        chunk_graph = self._build_chunk_graph(scripts, runtime, query=spec.query, max_candidates=spec.max_candidates)
        chunk_candidate_count = int(chunk_graph.get("candidate_count") or 0)
        status = "success" if modules or candidates or chunk_candidate_count else "partial" if scripts or chunk_graph.get("script_edge_count") else "failed"
        return ModuleDiscoveryResult(status=status, scripts=scripts, modules=modules, candidates=candidates, chunk_graph=chunk_graph, runtime=runtime, trigger=trigger)

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
        runtime_chunk_graphs: list[dict[str, Any]] = []
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
            runtime_chunk_graphs.append(cls._normalize_runtime_chunk_graph(runtime_payload, runtime_path=runtime_path, runtime_kind=runtime_kind))
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
            "chunk_graph": cls._merge_runtime_chunk_graphs(runtime_chunk_graphs),
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
            "chunkGraph": payload.get("chunkGraph", {}),
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

    @classmethod
    def _build_chunk_graph(
        cls,
        scripts: list[dict[str, Any]],
        runtime: dict[str, Any],
        *,
        query: str | None,
        max_candidates: int,
    ) -> dict[str, Any]:
        query_lower = query.lower() if query else None
        script_edges = cls._discover_chunk_edges_from_scripts(scripts, query_lower=query_lower, max_candidates=max_candidates)
        runtime_graph = runtime.get("chunk_graph") if isinstance(runtime.get("chunk_graph"), dict) else {}
        runtime_loaders = cls._list_of_dicts(runtime_graph.get("runtime_loaders")) if runtime_graph else []
        runtime_candidates = cls._list_of_dicts(runtime_graph.get("candidates")) if runtime_graph else []
        candidates = cls._dedupe_chunk_candidates([*script_edges, *runtime_candidates], max_candidates=max_candidates)
        status = "success" if candidates or runtime_loaders else "partial" if script_edges else "not_found"
        return {
            "status": status,
            "script_edge_count": len(script_edges),
            "runtime_loader_count": len(runtime_loaders),
            "candidate_count": len(candidates),
            "script_edges": script_edges,
            "runtime_loaders": runtime_loaders,
            "candidates": candidates,
            "side_effect_policy": {
                "source_inventory_only": True,
                "runtime_metadata_only": True,
                "runtime_loader_executed": False,
                "chunk_request_sent": False,
                "module_factory_executed": False,
            },
        }

    @classmethod
    def _discover_chunk_edges_from_scripts(
        cls,
        scripts: list[dict[str, Any]],
        *,
        query_lower: str | None,
        max_candidates: int,
    ) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for script in scripts:
            source = str(script.get("source") or "")
            if not source:
                continue
            for edge in cls._extract_chunk_edges(source):
                edge.update(
                    {
                        "scriptId": script.get("scriptId"),
                        "url": script.get("url"),
                        "kind": script.get("kind"),
                        "discovery_source": "script_inventory",
                    }
                )
                if query_lower and not cls._chunk_edge_matches_query(edge, query_lower):
                    continue
                edges.append(edge)
                if len(edges) >= max_candidates:
                    return edges
        return edges

    @staticmethod
    def _extract_chunk_edges(source: str) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        patterns: tuple[tuple[str, str, str], ...] = (
            ("dynamic-import", "es-dynamic-import", r"\bimport\s*\(\s*(['\"])(?P<target>[^'\"]+)\1\s*\)"),
            ("worker-importScripts", "worker-importScripts", r"\bimportScripts\s*\(\s*(['\"])(?P<target>[^'\"]+)\1\s*\)"),
            ("asset-url", "import-meta-url", r"\bnew\s+URL\s*\(\s*(['\"])(?P<target>[^'\"]+)\1\s*,\s*import\.meta\.url\s*\)"),
        )
        for edge_type, loader_kind, pattern in patterns:
            for match in re.finditer(pattern, source):
                target = str(match.group("target"))
                edges.append(
                    {
                        "edge_type": edge_type,
                        "loader_kind": loader_kind,
                        "target": target,
                        "chunk_id": target,
                        "offset": match.start(),
                        "review_action": "review_async_chunk_target_before_runtime_loading",
                    }
                )
        webpack_pattern = re.compile(
            r"(?P<loader>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|(?:\[[^\]]+\]))*)\.e\s*\(\s*(?P<quote>['\"]?)(?P<chunk_id>[A-Za-z0-9_./:-]+)(?P=quote)\s*\)"
        )
        for match in webpack_pattern.finditer(source):
            chunk_id = str(match.group("chunk_id"))
            loader = str(match.group("loader"))
            edges.append(
                {
                    "edge_type": "webpack-ensure-chunk",
                    "loader_kind": "webpack-runtime",
                    "target": chunk_id,
                    "chunk_id": chunk_id,
                    "loader_path": loader,
                    "offset": match.start(),
                    "review_action": "review_webpack_chunk_before_runtime_loading",
                }
            )
        return sorted(edges, key=lambda item: int(item.get("offset") or 0))

    @staticmethod
    def _chunk_edge_matches_query(edge: dict[str, Any], query_lower: str) -> bool:
        haystacks = [
            str(edge.get("target") or ""),
            str(edge.get("chunk_id") or ""),
            str(edge.get("url") or ""),
            str(edge.get("loader_path") or ""),
        ]
        return any(query_lower in item.lower() for item in haystacks)

    @classmethod
    def _normalize_runtime_chunk_graph(cls, payload: dict[str, Any], *, runtime_path: str, runtime_kind: str) -> dict[str, Any]:
        raw_graph = payload.get("chunkGraph") if isinstance(payload.get("chunkGraph"), dict) else {}
        loader_capabilities = raw_graph.get("loaderCapabilities") if isinstance(raw_graph.get("loaderCapabilities"), dict) else {}
        async_chunks = cls._list_of_dicts(raw_graph.get("asyncChunks")) or cls._list_of_dicts(raw_graph.get("chunks"))
        custom_loader_candidates = cls._list_of_dicts(raw_graph.get("customLoaderCandidates")) or cls._list_of_dicts(raw_graph.get("loaderCandidates"))
        runtime_loader = {
            "runtime_path": runtime_path,
            "runtime_kind": runtime_kind,
            "has_async_chunk_loader": bool(loader_capabilities.get("hasEnsureChunk") or loader_capabilities.get("hasAsyncChunkLoader")),
            "has_chunk_filename_resolver": bool(loader_capabilities.get("hasChunkFilenameResolver")),
            "loader_registry_keys": [str(item) for item in loader_capabilities.get("loaderRegistryKeys", []) if item is not None]
            if isinstance(loader_capabilities.get("loaderRegistryKeys"), list)
            else [],
            "public_path": str(loader_capabilities.get("publicPath") or ""),
            "side_effect_policy": {
                "loader_metadata_only": True,
                "runtime_loader_executed": False,
                "chunk_request_sent": False,
            },
        }
        candidates: list[dict[str, Any]] = []
        for item in async_chunks:
            chunk_id = str(item.get("chunkId") or item.get("chunk_id") or item.get("id") or item.get("target") or "")
            target = str(item.get("target") or item.get("url") or item.get("href") or chunk_id)
            if not chunk_id and not target:
                continue
            candidates.append(
                {
                    "edge_type": str(item.get("edgeType") or item.get("edge_type") or "runtime-async-chunk"),
                    "loader_kind": str(item.get("loaderKind") or item.get("loader_kind") or runtime_kind),
                    "chunk_id": chunk_id or target,
                    "target": target,
                    "runtime_path": runtime_path,
                    "discovery_source": "runtime_chunk_graph",
                    "review_action": "review_runtime_chunk_metadata_before_loading",
                }
            )
        for item in custom_loader_candidates:
            target = str(item.get("target") or item.get("path") or item.get("loaderPath") or item.get("loader_path") or "")
            if not target:
                continue
            candidates.append(
                {
                    "edge_type": str(item.get("edgeType") or item.get("edge_type") or "custom-loader-candidate"),
                    "loader_kind": str(item.get("loaderKind") or item.get("loader_kind") or "custom-loader"),
                    "chunk_id": str(item.get("chunkId") or item.get("chunk_id") or target),
                    "target": target,
                    "runtime_path": runtime_path,
                    "discovery_source": "runtime_chunk_graph",
                    "review_action": "review_custom_loader_candidate_before_execution",
                }
            )
        return {
            "runtime_loader": runtime_loader,
            "candidates": candidates,
        }

    @classmethod
    def _merge_runtime_chunk_graphs(cls, graphs: list[dict[str, Any]]) -> dict[str, Any]:
        runtime_loaders: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for graph in graphs:
            runtime_loader = graph.get("runtime_loader") if isinstance(graph.get("runtime_loader"), dict) else {}
            if runtime_loader:
                runtime_loaders.append(runtime_loader)
            candidates.extend(cls._list_of_dicts(graph.get("candidates")))
        return {
            "status": "success" if candidates or any(item.get("has_async_chunk_loader") for item in runtime_loaders) else "not_found",
            "runtime_loader_count": len(runtime_loaders),
            "candidate_count": len(candidates),
            "runtime_loaders": runtime_loaders,
            "candidates": candidates,
        }

    @staticmethod
    def _dedupe_chunk_candidates(candidates: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for candidate in candidates:
            key = (
                str(candidate.get("edge_type") or ""),
                str(candidate.get("loader_kind") or ""),
                str(candidate.get("target") or ""),
                str(candidate.get("runtime_path") or candidate.get("url") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
            if len(deduped) >= max_candidates:
                break
        return deduped

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
    const loaderRegistryKeys = req.f && typeof req.f === "object" ? Object.keys(req.f) : [];
    const chunkGraph = {{
      loaderCapabilities: {{
        hasEnsureChunk: typeof req.e === "function",
        hasChunkFilenameResolver: typeof req.u === "function",
        loaderRegistryKeys,
        publicPath: typeof req.p === "string" ? req.p.slice(0, maxPreviewLength) : ""
      }},
      asyncChunks: [],
      customLoaderCandidates: []
    }};
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
      chunkGraph,
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
      chunkGraph: {{ loaderCapabilities: {{ hasAsyncChunkLoader: false, hasChunkFilenameResolver: false, loaderRegistryKeys: [], publicPath: "" }}, asyncChunks: [], customLoaderCandidates: [] }},
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
      chunkGraph: {{ loaderCapabilities: {{ hasAsyncChunkLoader: typeof container.get === "function", hasChunkFilenameResolver: false, loaderRegistryKeys: [], publicPath: "" }}, asyncChunks: [], customLoaderCandidates: [] }},
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
