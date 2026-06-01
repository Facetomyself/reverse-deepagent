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
    previous_traversal_plan: dict[str, Any] = field(default_factory=dict)
    previous_execution_results: list[dict[str, Any]] = field(default_factory=list)
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
            or context.get("previous_custom_loader_traversal_plan")
            or context.get("previousCustomLoaderTraversalPlan")
            or context.get("custom_loader_traversal_plan")
            or context.get("customLoaderTraversalPlan")
            or context.get("custom_loader_execution_result")
            or context.get("customLoaderExecutionResult")
            or context.get("previous_custom_loader_execution_results")
            or context.get("previousCustomLoaderExecutionResults")
        )
        if not candidates and not traversal_requested:
            return None
        previous_plan = (
            context.get("previous_custom_loader_traversal_plan")
            or context.get("previousCustomLoaderTraversalPlan")
            or context.get("custom_loader_traversal_plan")
            or context.get("customLoaderTraversalPlan")
        )
        return cls(
            candidates=cls._dedupe_candidates(candidates, max_candidates=int(context.get("max_candidates", context.get("maxCandidates", 20)) or 20)),
            previous_traversal_plan=dict(previous_plan) if isinstance(previous_plan, dict) else {},
            previous_execution_results=cls._execution_result_records(context),
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
            "next_custom_loader_candidates",
            "nextCustomLoaderCandidates",
            "discovered_custom_loader_candidates",
            "discoveredCustomLoaderCandidates",
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

    @classmethod
    def _execution_result_records(cls, context: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for key in (
            "custom_loader_execution_result",
            "custom-loader-execution-result",
            "customLoaderExecutionResult",
            "previous_custom_loader_execution_result",
            "previousCustomLoaderExecutionResult",
        ):
            value = context.get(key)
            if isinstance(value, dict):
                records.append(value)
        for key in (
            "custom_loader_execution_results",
            "customLoaderExecutionResults",
            "previous_custom_loader_execution_results",
            "previousCustomLoaderExecutionResults",
        ):
            records.extend(cls._list_of_dicts(context.get(key)))
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
        executed_fingerprints = self._executed_candidate_fingerprints(spec.previous_execution_results)
        planned_candidates = [
            self._candidate_plan(item, index=index, spec=spec, executed_fingerprints=executed_fingerprints)
            for index, item in enumerate(spec.candidates)
        ]
        summary = self._summary(planned_candidates)
        continuation = self._continuation_summary(spec, planned_candidates, executed_fingerprints)
        plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-plan.v1",
            "status": "ready_for_review" if planned_candidates else "blocked",
            "review_required": True,
            "review_approved_input_ignored": bool(spec.review_approved),
            "traversal_depth": spec.traversal_depth,
            "max_traversal_depth": spec.traversal_depth,
            "candidate_count": len(planned_candidates),
            "custom_candidate_count": summary["custom_candidate_count"],
            "blocked_execution_count": summary["blocked_execution_count"],
            "ready_for_review_count": summary["ready_for_review_count"],
            "ready_continuation_count": summary["ready_continuation_count"],
            "already_executed_count": summary["already_executed_count"],
            "max_depth_blocked_count": summary["max_depth_blocked_count"],
            "previous_execution_count": len(spec.previous_execution_results),
            "candidates": planned_candidates,
            "continuation": continuation,
            "approval_requirements": [
                "confirm_loader_candidate_origin",
                "classify_loader_side_effects",
                "review_network_request_scope",
                "review_module_factory_execution_risk",
                "prefer_webpack_async_chunk_load_when_loader_kind_is_supported",
                "review_each_continuation_step_individually",
            ],
            "side_effect_policy": policy,
            "next_action": continuation["next_action"] if planned_candidates else "provide_custom_loader_candidates_from_chunk_graph",
        }
        return CustomLoaderTraversalPlanResult(status="planned" if planned_candidates else "blocked", plan=plan, side_effect_policy=policy, reason=None if planned_candidates else "no_custom_loader_candidates")

    @classmethod
    def _candidate_plan(
        cls,
        candidate: dict[str, Any],
        *,
        index: int,
        spec: CustomLoaderTraversalPlanSpec,
        executed_fingerprints: set[tuple[str, str, str]],
    ) -> dict[str, Any]:
        loader_kind = str(candidate.get("loader_kind") or candidate.get("loaderKind") or "custom-loader") or "custom-loader"
        edge_type = str(candidate.get("edge_type") or candidate.get("edgeType") or "custom-loader-candidate") or "custom-loader-candidate"
        chunk_id = str(candidate.get("chunk_id") or candidate.get("chunkId") or candidate.get("target") or "")[: spec.max_preview_length]
        target = str(candidate.get("target") or candidate.get("url") or candidate.get("href") or chunk_id)[: spec.max_preview_length]
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or target)[: spec.max_preview_length]
        runtime_path = str(candidate.get("runtime_path") or candidate.get("runtimePath") or "")[: spec.max_preview_length]
        depth = cls._candidate_depth(candidate, default=1)
        parent_loader_path = str(candidate.get("parent_loader_path") or candidate.get("parentLoaderPath") or "")[: spec.max_preview_length]
        classification = cls._classify(loader_kind, edge_type=edge_type)
        fingerprint = cls._candidate_fingerprint({"loader_path": loader_path, "target": target, "chunk_id": chunk_id})
        fingerprint_variants = {
            fingerprint,
            cls._candidate_fingerprint({"loader_path": loader_path, "target": loader_path}),
            cls._candidate_fingerprint({"loader_path": loader_path}),
        }
        already_executed = bool(executed_fingerprints & fingerprint_variants)
        max_depth_exceeded = depth > spec.traversal_depth
        blocking_reasons = list(classification["blocking_reasons"])
        review_requirements = list(classification["review_requirements"])
        status = classification["status"]
        recommended_follow_up = classification["recommended_follow_up"]
        if already_executed:
            status = "already_executed"
            recommended_follow_up = "select_unexecuted_continuation_candidate"
            blocking_reasons.append("custom_loader_candidate_already_executed")
            review_requirements.append("inspect_previous_custom_loader_execution_result")
        if max_depth_exceeded:
            status = "blocked"
            recommended_follow_up = "reduce_candidate_depth_or_increase_reviewed_traversal_depth"
            blocking_reasons.append("max_traversal_depth_exceeded")
            review_requirements.append("review_bounded_traversal_depth_before_continuing")
        continuation_context_present = bool(parent_loader_path or executed_fingerprints or spec.previous_traversal_plan)
        continuation_supported = (
            status == "ready_for_review"
            and classification["classification"] == "arbitrary_custom_loader"
            and not already_executed
            and not max_depth_exceeded
            and continuation_context_present
        )
        return {
            "index": index,
            "candidate_id": f"custom-loader-candidate-{index}",
            "status": status,
            "risk_level": classification["risk_level"],
            "classification": classification["classification"],
            "depth": depth,
            "parent_loader_path": parent_loader_path,
            "chunk_id": chunk_id,
            "target": target,
            "loader_path": loader_path,
            "loader_kind": loader_kind,
            "edge_type": edge_type,
            "runtime_path": runtime_path,
            "fingerprint": "|".join(fingerprint),
            "already_executed": already_executed,
            "max_traversal_depth_exceeded": max_depth_exceeded,
            "discovery_source": str(candidate.get("discovery_source") or candidate.get("discoverySource") or "unknown"),
            "execution_supported": False,
            "traversal_supported": continuation_supported,
            "continuation_supported": continuation_supported,
            "automatic_execution": False,
            "recommended_follow_up": recommended_follow_up,
            "blocking_reasons": blocking_reasons,
            "review_requirements": review_requirements,
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
            "ready_continuation_count": sum(1 for item in candidates if item.get("continuation_supported")),
            "already_executed_count": sum(1 for item in candidates if item.get("already_executed")),
            "max_depth_blocked_count": sum(1 for item in candidates if item.get("max_traversal_depth_exceeded")),
        }

    @classmethod
    def _continuation_summary(
        cls,
        spec: CustomLoaderTraversalPlanSpec,
        candidates: list[dict[str, Any]],
        executed_fingerprints: set[tuple[str, str, str]],
    ) -> dict[str, Any]:
        ready = [item for item in candidates if item.get("continuation_supported")]
        already = [item for item in candidates if item.get("already_executed")]
        max_depth_blocked = [item for item in candidates if item.get("max_traversal_depth_exceeded")]
        continuation_observed = bool(spec.previous_execution_results or spec.previous_traversal_plan or any(item.get("parent_loader_path") for item in candidates))
        if ready:
            next_action = "review_next_custom_loader_continuation_candidate"
        elif max_depth_blocked:
            next_action = "review_bounded_custom_loader_traversal_depth"
        elif already:
            next_action = "provide_unexecuted_custom_loader_continuation_candidates"
        else:
            next_action = "review_custom_loader_traversal_plan"
        return {
            "schema_version": "reverse-deepagent.custom-loader-traversal-continuation.v1",
            "status": "ready_for_review" if ready else "blocked" if max_depth_blocked or already else "not_observed",
            "continuation_observed": continuation_observed,
            "previous_execution_count": len(spec.previous_execution_results),
            "previous_fingerprint_count": len(executed_fingerprints),
            "previous_plan_present": bool(spec.previous_traversal_plan),
            "max_traversal_depth": spec.traversal_depth,
            "ready_continuation_count": len(ready),
            "already_executed_count": len(already),
            "max_depth_blocked_count": len(max_depth_blocked),
            "automatic_recursive_execution": False,
            "requires_review_approval_per_step": True,
            "next_action": next_action,
        }

    @classmethod
    def _executed_candidate_fingerprints(cls, execution_results: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
        fingerprints: set[tuple[str, str, str]] = set()
        for item in execution_results:
            payload = item.get("execution") if isinstance(item.get("execution"), dict) else item
            candidate = item.get("selected_candidate") or item.get("selectedCandidate") or payload.get("selected_candidate") or payload.get("selectedCandidate")
            if isinstance(candidate, dict):
                fingerprints.add(cls._candidate_fingerprint(candidate))
            loader_path = payload.get("loaderPath") or payload.get("loader_path") or item.get("loader_path") or item.get("loaderPath")
            if loader_path:
                fingerprints.add(cls._candidate_fingerprint({"loader_path": loader_path, "target": loader_path}))
        return {item for item in fingerprints if any(item)}

    @staticmethod
    def _candidate_fingerprint(candidate: dict[str, Any]) -> tuple[str, str, str]:
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or "").strip()
        target = str(candidate.get("target") or candidate.get("url") or candidate.get("href") or "").strip()
        chunk_id = str(candidate.get("chunk_id") or candidate.get("chunkId") or "").strip()
        if not loader_path and target:
            loader_path = target
        if not target and loader_path:
            target = loader_path
        return (loader_path, target, chunk_id)

    @staticmethod
    def _candidate_depth(candidate: dict[str, Any], *, default: int) -> int:
        value = candidate.get("depth", candidate.get("traversal_depth", candidate.get("traversalDepth", default)))
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return max(1, default)

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
            "automatic_recursive_traversal": False,
            "requires_review_approval_per_step": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderContinuationWorkflowSpec:
    """Plan-only workflow for one reviewed custom-loader continuation step."""

    traversal_plan: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    candidate_index: int | None = None
    workflow_id: str = "custom-loader-continuation-workflow-1"
    review_approved: bool = False
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderContinuationWorkflowSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_continuation_workflow")
            or context.get("customLoaderContinuationWorkflow")
            or context.get("custom-loader-continuation-workflow")
            or context.get("plan_custom_loader_continuation_workflow")
            or context.get("planCustomLoaderContinuationWorkflow")
        )
        plan = (
            context.get("custom_loader_traversal_plan")
            or context.get("custom-loader-traversal-plan")
            or context.get("customLoaderTraversalPlan")
            or context.get("loader_traversal_plan")
            or context.get("loaderTraversalPlan")
        )
        if not isinstance(plan, dict):
            return None if not requested else cls()
        index_value = context.get("candidate_index", context.get("candidateIndex"))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        selected = (
            context.get("selected_custom_loader_candidate")
            or context.get("selectedCustomLoaderCandidate")
            or context.get("selected_loader_candidate")
            or context.get("selectedLoaderCandidate")
            or context.get("selected_candidate")
            or context.get("selectedCandidate")
        )
        workflow_id = str(
            context.get("workflow_id")
            or context.get("workflowId")
            or context.get("continuation_workflow_id")
            or context.get("continuationWorkflowId")
            or "custom-loader-continuation-workflow-1"
        ).strip() or "custom-loader-continuation-workflow-1"
        return cls(
            traversal_plan=dict(plan),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            candidate_index=candidate_index,
            workflow_id=workflow_id,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderContinuationWorkflowResult:
    status: str
    workflow: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "workflow": self.workflow,
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderContinuationWorkflowManager:
    """Compose one custom-loader continuation step without executing it."""

    def plan(self, spec: CustomLoaderContinuationWorkflowSpec | None) -> CustomLoaderContinuationWorkflowResult:
        policy = self._side_effect_policy(review_approved=bool(spec and spec.review_approved))
        if spec is None or not spec.traversal_plan:
            return CustomLoaderContinuationWorkflowResult(status="unsupported", reason="missing_custom_loader_traversal_plan", side_effect_policy=policy)
        candidate = self._select_candidate(spec)
        blockers = self._blocking_reasons(candidate)
        status = "approved_for_preflight" if spec.review_approved and candidate and not blockers else "ready_for_review" if candidate and not blockers else "blocked"
        reason = None if status != "blocked" else blockers[0] if blockers else "no_ready_custom_loader_continuation_candidate"
        candidate_index = candidate.get("index") if candidate else spec.candidate_index
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "")[: spec.max_preview_length] if candidate else ""
        preflight_input = {
            "custom_loader_traversal_plan": spec.traversal_plan,
            "candidate_index": candidate_index,
            "expected_loader_path": loader_path,
            "review_approved": bool(spec.review_approved),
        }
        workflow = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-workflow.v1",
            "workflow_id": spec.workflow_id,
            "status": status,
            "review_required": True,
            "review_approved": bool(spec.review_approved),
            "selected_candidate_index": candidate_index,
            "selected_candidate": candidate,
            "blocking_reasons": blockers,
            "continuation": dict(spec.traversal_plan.get("continuation", {})) if isinstance(spec.traversal_plan.get("continuation"), dict) else {},
            "preflight_input": preflight_input,
            "workflow_steps": self._workflow_steps(status=status, review_approved=spec.review_approved),
            "journal_plan": {
                "schema_version": "reverse-deepagent.custom-loader-continuation-journal-plan.v1",
                "journal_artifact": "workspace/custom-loader-continuation-journal.json",
                "virtual_journal_artifact": "virtual://workspace/custom-loader-continuation-journal.json",
                "writes_journal_now": False,
                "append_only": True,
                "records_planned_step": True,
                "records_preflight_result": True,
                "records_execution_result": True,
                "records_module_diff_result": True,
                "records_module_hook_result": True,
            },
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status),
        }
        return CustomLoaderContinuationWorkflowResult(status=status, workflow=workflow, selected_candidate=candidate, side_effect_policy=policy, reason=reason)

    @classmethod
    def _select_candidate(cls, spec: CustomLoaderContinuationWorkflowSpec) -> dict[str, Any]:
        if spec.selected_candidate:
            return dict(spec.selected_candidate)
        candidates = [item for item in spec.traversal_plan.get("candidates", []) if isinstance(item, dict)]
        if spec.candidate_index is not None:
            for item in candidates:
                if int(item.get("index", -1)) == spec.candidate_index:
                    return dict(item)
            if 0 <= spec.candidate_index < len(candidates):
                return dict(candidates[spec.candidate_index])
            return {}
        for item in candidates:
            if item.get("continuation_supported"):
                return dict(item)
        for item in candidates:
            if item.get("status") == "ready_for_review" and item.get("classification") == "arbitrary_custom_loader":
                return dict(item)
        return {}

    @staticmethod
    def _blocking_reasons(candidate: dict[str, Any]) -> list[str]:
        if not candidate:
            return ["no_ready_custom_loader_continuation_candidate"]
        blockers: list[str] = []
        if candidate.get("already_executed") or candidate.get("status") == "already_executed":
            blockers.append("custom_loader_candidate_already_executed")
        if candidate.get("max_traversal_depth_exceeded"):
            blockers.append("max_traversal_depth_exceeded")
        if candidate.get("classification") != "arbitrary_custom_loader":
            blockers.append("unsupported_custom_loader_continuation_candidate")
        if candidate.get("status") not in {"ready_for_review"}:
            blockers.append(f"candidate_status_not_ready:{candidate.get('status', 'unknown')}")
        if not candidate.get("continuation_supported"):
            blockers.append("candidate_not_marked_continuation_supported")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _workflow_steps(*, status: str, review_approved: bool) -> list[dict[str, Any]]:
        return [
            {
                "step": "review_custom_loader_continuation_candidate",
                "status": "approved" if review_approved else "pending_review",
                "artifact": "workspace/custom-loader-continuation-workflow.json",
                "side_effect": False,
            },
            {
                "step": "run_custom_loader_execution_preflight",
                "status": "ready" if status == "approved_for_preflight" else "blocked_until_review",
                "artifact": "workspace/custom-loader-execution-preflight.json",
                "side_effect": False,
            },
            {
                "step": "execute_reviewed_custom_loader_candidate",
                "status": "requires_separate_execution_approval",
                "artifact": "workspace/custom-loader-execution-result.json",
                "side_effect": True,
            },
            {
                "step": "refresh_custom_loader_module_diff",
                "status": "pending_successful_execution",
                "artifact": "workspace/custom-loader-module-diff.json",
                "side_effect": False,
            },
            {
                "step": "review_and_install_custom_loader_module_hook",
                "status": "pending_module_diff_review",
                "artifact": "workspace/module-hooks.json",
                "side_effect": True,
            },
            {
                "step": "plan_next_custom_loader_continuation",
                "status": "pending_follow_up_candidates",
                "artifact": "workspace/custom-loader-traversal-plan.json",
                "side_effect": False,
            },
        ]

    @staticmethod
    def _next_action(*, status: str) -> str:
        if status == "approved_for_preflight":
            return "run_custom_loader_execution_preflight_for_continuation"
        if status == "ready_for_review":
            return "review_custom_loader_continuation_workflow"
        return "revise_custom_loader_continuation_workflow_inputs"

    @staticmethod
    def _side_effect_policy(*, review_approved: bool) -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_approved": review_approved,
            "writes_journal": False,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "preflight_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "automatic_recursive_traversal": False,
            "requires_review_approval_per_step": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderContinuationJournalSpec:
    """Review-gated append-only journal record for one custom-loader continuation step."""

    workflow: dict[str, Any] = field(default_factory=dict)
    existing_journal: dict[str, Any] = field(default_factory=dict)
    preflight: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    next_traversal_plan: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    write_journal: bool = False
    reviewer: str = ""
    journal_id: str = "custom-loader-continuation-journal"
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderContinuationJournalSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_continuation_journal")
            or context.get("customLoaderContinuationJournal")
            or context.get("custom-loader-continuation-journal")
            or context.get("append_custom_loader_continuation_journal")
            or context.get("appendCustomLoaderContinuationJournal")
        )
        workflow = (
            context.get("custom_loader_continuation_workflow")
            or context.get("custom-loader-continuation-workflow")
            or context.get("customLoaderContinuationWorkflow")
            or context.get("continuation_workflow")
            or context.get("continuationWorkflow")
        )
        if isinstance(workflow, dict) and isinstance(workflow.get("workflow"), dict):
            workflow = workflow["workflow"]
        if not isinstance(workflow, dict):
            return None if not requested else cls()
        existing = (
            context.get("custom_loader_continuation_journal")
            or context.get("custom-loader-continuation-journal")
            or context.get("customLoaderContinuationJournal")
            or context.get("existing_custom_loader_continuation_journal")
            or context.get("existingCustomLoaderContinuationJournal")
            or {}
        )
        return cls(
            workflow=dict(workflow),
            existing_journal=dict(existing) if isinstance(existing, dict) else {},
            preflight=cls._object_alias(context, "custom_loader_execution_preflight", "custom-loader-execution-preflight", "customLoaderExecutionPreflight"),
            execution_result=cls._object_alias(context, "custom_loader_execution_result", "custom-loader-execution-result", "customLoaderExecutionResult"),
            module_diff=cls._object_alias(context, "custom_loader_module_diff", "custom-loader-module-diff", "customLoaderModuleDiff"),
            module_hook_result=cls._object_alias(context, "custom_loader_module_hook_result", "custom-loader-module-hook-result", "customLoaderModuleHookResult", "module_hooks", "module-hooks"),
            next_traversal_plan=cls._object_alias(context, "next_custom_loader_traversal_plan", "next-custom-loader-traversal-plan", "nextCustomLoaderTraversalPlan", "custom_loader_traversal_plan", "custom-loader-traversal-plan"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            write_journal=bool(
                context.get("write_journal")
                or context.get("writeJournal")
                or context.get("append_journal")
                or context.get("appendJournal")
                or context.get("append_custom_loader_continuation_journal")
                or context.get("appendCustomLoaderContinuationJournal")
            ),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip(),
            journal_id=str(context.get("journal_id") or context.get("journalId") or "custom-loader-continuation-journal").strip() or "custom-loader-continuation-journal",
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

    @staticmethod
    def _object_alias(context: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = context.get(key)
            if isinstance(value, dict):
                return dict(value)
        return {}


@dataclass(slots=True)
class CustomLoaderContinuationJournalResult:
    status: str
    journal: dict[str, Any] = field(default_factory=dict)
    entry: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "journal": self.journal,
            "entry": self.entry,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderContinuationJournalManager:
    """Append a reviewed custom-loader continuation journal payload without executing loaders."""

    def plan_or_append(self, spec: CustomLoaderContinuationJournalSpec | None) -> CustomLoaderContinuationJournalResult:
        policy = self._side_effect_policy(write_journal=bool(spec and spec.write_journal), review_approved=bool(spec and spec.review_approved))
        if spec is None or not spec.workflow:
            return CustomLoaderContinuationJournalResult(status="unsupported", reason="missing_custom_loader_continuation_workflow", side_effect_policy=policy)
        existing_records = self._existing_records(spec.existing_journal)
        entry = self._entry(spec, existing_record_count=len(existing_records))
        blockers = self._blocking_reasons(spec, entry, existing_records)
        if blockers:
            status = "blocked"
        elif spec.write_journal:
            status = "journal_appended"
        else:
            status = "ready_for_review"
        journal_records = existing_records + ([entry] if status == "journal_appended" else [])
        journal = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-journal.v1",
            "journal_id": spec.journal_id,
            "status": status,
            "append_only": True,
            "review_required": True,
            "review_approved": bool(spec.review_approved),
            "write_requested": bool(spec.write_journal),
            "writes_journal_now": status == "journal_appended",
            "record_count": len(journal_records),
            "existing_record_count": len(existing_records),
            "blocking_reasons": blockers,
            "pending_entry": entry if status != "journal_appended" else {},
            "records": journal_records,
            "side_effect_policy": self._side_effect_policy(write_journal=status == "journal_appended", review_approved=spec.review_approved),
            "next_action": self._next_action(status=status, blockers=blockers),
        }
        reason = blockers[0] if blockers else None
        return CustomLoaderContinuationJournalResult(
            status=status,
            journal=journal,
            entry=entry,
            side_effect_policy=journal["side_effect_policy"],
            reason=reason,
        )

    @classmethod
    def _entry(cls, spec: CustomLoaderContinuationJournalSpec, *, existing_record_count: int) -> dict[str, Any]:
        workflow = spec.workflow
        candidate = workflow.get("selected_candidate") if isinstance(workflow.get("selected_candidate"), dict) else {}
        fingerprint = str(candidate.get("fingerprint") or cls._candidate_fingerprint(candidate))
        workflow_id = str(workflow.get("workflow_id") or "custom-loader-continuation-workflow-1")[: spec.max_preview_length]
        selected_index = workflow.get("selected_candidate_index")
        entry_id = f"{spec.journal_id}:{workflow_id}:{selected_index}:{fingerprint or 'missing'}"
        execution = spec.execution_result.get("execution") if isinstance(spec.execution_result.get("execution"), dict) else spec.execution_result
        stage_status = cls._stage_status(spec)
        return {
            "schema_version": "reverse-deepagent.custom-loader-continuation-journal-entry.v1",
            "entry_id": entry_id,
            "sequence": existing_record_count + 1,
            "workflow_id": workflow_id,
            "workflow_status": workflow.get("status"),
            "selected_candidate_index": selected_index,
            "candidate_fingerprint": fingerprint,
            "loader_path": str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "")[: spec.max_preview_length],
            "selected_candidate": candidate,
            "reviewer": spec.reviewer,
            "review_approved": bool(spec.review_approved),
            "stage_status": stage_status,
            "artifact_status": {
                "workflow_recorded": bool(workflow),
                "preflight_recorded": bool(spec.preflight),
                "execution_result_recorded": bool(spec.execution_result),
                "execution_success": bool(spec.execution_result.get("status") == "success" or execution.get("ok") is True),
                "module_diff_recorded": bool(spec.module_diff),
                "module_hook_result_recorded": bool(spec.module_hook_result),
                "next_traversal_plan_recorded": bool(spec.next_traversal_plan),
            },
            "artifact_refs": {
                "workflow": "workspace/custom-loader-continuation-workflow.json",
                "preflight": "workspace/custom-loader-execution-preflight.json" if spec.preflight else "",
                "execution_result": "workspace/custom-loader-execution-result.json" if spec.execution_result else "",
                "module_diff": "workspace/custom-loader-module-diff.json" if spec.module_diff else "",
                "module_hooks": "workspace/module-hooks.json" if spec.module_hook_result else "",
                "next_traversal_plan": "workspace/custom-loader-traversal-plan.json" if spec.next_traversal_plan else "",
            },
            "side_effect_policy": {
                "records_journal_entry": True,
                "loader_invoked_by_journal": False,
                "custom_loader_executed_by_journal": False,
                "preflight_executed_by_journal": False,
                "module_diff_executed_by_journal": False,
                "module_hook_installed_by_journal": False,
                "automatic_recursive_traversal": False,
            },
        }

    @staticmethod
    def _stage_status(spec: CustomLoaderContinuationJournalSpec) -> str:
        execution = spec.execution_result.get("execution") if isinstance(spec.execution_result.get("execution"), dict) else spec.execution_result
        if spec.module_hook_result:
            return "module_hook_result_recorded"
        if spec.module_diff:
            return "module_diff_recorded"
        if spec.execution_result and (spec.execution_result.get("status") == "success" or execution.get("ok") is True):
            return "execution_result_recorded"
        if spec.preflight:
            return "preflight_recorded"
        return "planned_continuation_recorded"

    @staticmethod
    def _candidate_fingerprint(candidate: dict[str, Any]) -> str:
        return "|".join(CustomLoaderTraversalPlanManager._candidate_fingerprint(candidate))

    @staticmethod
    def _existing_records(journal: dict[str, Any]) -> list[dict[str, Any]]:
        records = journal.get("records") if isinstance(journal, dict) else []
        if isinstance(records, list):
            return [dict(item) for item in records if isinstance(item, dict)]
        return []

    @staticmethod
    def _blocking_reasons(spec: CustomLoaderContinuationJournalSpec, entry: dict[str, Any], existing_records: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        if spec.workflow.get("status") in {"blocked", "failed", "unsupported"}:
            blockers.append("custom_loader_continuation_workflow_not_journalable")
        if not spec.write_journal:
            return blockers
        if not spec.review_approved:
            blockers.append("review_approval_required")
        fingerprint = entry.get("candidate_fingerprint")
        workflow_id = entry.get("workflow_id")
        if fingerprint and any(record.get("candidate_fingerprint") == fingerprint and record.get("workflow_id") == workflow_id for record in existing_records):
            blockers.append("custom_loader_continuation_journal_duplicate_entry")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if status == "journal_appended":
            return "run_or_review_next_custom_loader_continuation_step"
        if "review_approval_required" in blockers:
            return "approve_custom_loader_continuation_journal_append"
        if blockers:
            return "revise_custom_loader_continuation_journal_inputs"
        return "review_custom_loader_continuation_journal_append"

    @staticmethod
    def _side_effect_policy(*, write_journal: bool, review_approved: bool) -> dict[str, Any]:
        return {
            "plan_only": not write_journal,
            "review_approved": review_approved,
            "writes_journal": write_journal,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "preflight_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderContinuationExecutionSpec:
    """Explicit one-step orchestration over continuation workflow evidence."""

    workflow: dict[str, Any] = field(default_factory=dict)
    preflight: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    existing_journal: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    run_preflight: bool = False
    execute_custom_loader: bool = False
    run_module_diff: bool = False
    install_module_hook: bool = False
    append_journal: bool = False
    review_approved: bool = False
    candidate_index: int | None = None
    loader_arguments: list[Any] = field(default_factory=list)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderContinuationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_continuation_execution")
            or context.get("customLoaderContinuationExecution")
            or context.get("custom-loader-continuation-execution")
            or context.get("execute_custom_loader_continuation_step")
            or context.get("executeCustomLoaderContinuationStep")
        )
        workflow = (
            context.get("custom_loader_continuation_workflow")
            or context.get("custom-loader-continuation-workflow")
            or context.get("customLoaderContinuationWorkflow")
            or context.get("continuation_workflow")
            or context.get("continuationWorkflow")
        )
        if isinstance(workflow, dict) and isinstance(workflow.get("workflow"), dict):
            workflow = workflow["workflow"]
        if not isinstance(workflow, dict):
            return None if not requested else cls()
        index_value = context.get("candidate_index", context.get("candidateIndex", workflow.get("selected_candidate_index")))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        loader_arguments_value = context.get("loader_arguments", context.get("loaderArguments"))
        loader_argument_value = context.get("loader_argument", context.get("loaderArgument"))
        if isinstance(loader_arguments_value, list):
            loader_arguments = list(loader_arguments_value)
        elif loader_arguments_value is not None:
            loader_arguments = [loader_arguments_value]
        elif loader_argument_value is not None:
            loader_arguments = [loader_argument_value]
        else:
            loader_arguments = []
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        return cls(
            workflow=dict(workflow),
            preflight=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_preflight", "custom-loader-execution-preflight", "customLoaderExecutionPreflight"),
            execution_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_result", "custom-loader-execution-result", "customLoaderExecutionResult"),
            module_diff=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_diff", "custom-loader-module-diff", "customLoaderModuleDiff"),
            module_hook_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_hook_result", "custom-loader-module-hook-result", "customLoaderModuleHookResult", "module_hooks", "module-hooks"),
            existing_journal=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_continuation_journal", "custom-loader-continuation-journal", "customLoaderContinuationJournal"),
            module_discovery=CustomLoaderContinuationJournalSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            run_preflight=bool(context.get("run_preflight") or context.get("runPreflight") or context.get("execute_preflight") or context.get("executePreflight")),
            execute_custom_loader=bool(context.get("execute_custom_loader") or context.get("executeCustomLoader")),
            run_module_diff=bool(context.get("run_module_diff") or context.get("runModuleDiff") or context.get("refresh_module_diff") or context.get("refreshModuleDiff")),
            install_module_hook=bool(context.get("install_module_hook") or context.get("installModuleHook") or context.get("hook_custom_loader_module") or context.get("hookCustomLoaderModule")),
            append_journal=bool(context.get("append_journal") or context.get("appendJournal") or context.get("append_custom_loader_continuation_journal") or context.get("appendCustomLoaderContinuationJournal")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            candidate_index=candidate_index,
            loader_arguments=loader_arguments,
        )


@dataclass(slots=True)
class CustomLoaderContinuationExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderContinuationExecutionManager:
    """Run at most one explicitly reviewed custom-loader continuation workflow step."""

    def execute(self, page: BrowserPage, spec: CustomLoaderContinuationExecutionSpec | None) -> CustomLoaderContinuationExecutionResult:
        if spec is None or not spec.workflow:
            return CustomLoaderContinuationExecutionResult(status="unsupported", reason="missing_custom_loader_continuation_workflow", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = []
        preflight_payload = dict(spec.preflight)
        execution_payload = dict(spec.execution_result)
        diff_payload = dict(spec.module_diff)
        hook_payload = dict(spec.module_hook_result)
        journal_payload: dict[str, Any] = {}
        if spec.run_preflight:
            preflight_context = dict(spec.workflow.get("preflight_input") if isinstance(spec.workflow.get("preflight_input"), dict) else {})
            preflight_context["review_approved"] = spec.review_approved
            if spec.candidate_index is not None:
                preflight_context["candidate_index"] = spec.candidate_index
            preflight_result = CustomLoaderExecutionPreflightManager().preflight(CustomLoaderExecutionPreflightSpec.from_context(preflight_context))
            preflight_payload = preflight_result.to_dict()
            stages.append(self._stage("preflight", preflight_result.status, preflight_result.reason, side_effect=False))
        elif preflight_payload:
            stages.append(self._stage("preflight", str(preflight_payload.get("status") or "observed"), None, side_effect=False, observed=True))
        else:
            stages.append(self._stage("preflight", "pending", None, side_effect=False))
        if spec.execute_custom_loader:
            if not self._preflight_ready(preflight_payload):
                stages.append(self._stage("custom_loader_execution", "blocked", "custom_loader_preflight_not_ready", side_effect=True))
            else:
                execution_result = CustomLoaderExecutionManager().execute(
                    page,
                    CustomLoaderExecutionSpec.from_context(
                        {
                            "custom_loader_execution_preflight": preflight_payload,
                            "review_approved": spec.review_approved,
                            "loader_arguments": spec.loader_arguments,
                        }
                    ),
                )
                execution_payload = execution_result.to_dict()
                stages.append(self._stage("custom_loader_execution", execution_result.status, execution_result.reason, side_effect=True))
        elif execution_payload:
            stages.append(self._stage("custom_loader_execution", str(execution_payload.get("status") or "observed"), None, side_effect=False, observed=True))
        else:
            stages.append(self._stage("custom_loader_execution", "pending", None, side_effect=True))
        if spec.run_module_diff:
            if not self._execution_success(execution_payload):
                stages.append(self._stage("custom_loader_module_diff", "blocked", "successful_custom_loader_execution_required", side_effect=False))
            else:
                diff_result = CustomLoaderModuleDiffManager().plan(
                    CustomLoaderModuleDiffSpec.from_context(
                        {
                            "custom_loader_execution_result": execution_payload,
                            "module_discovery": spec.module_discovery,
                            "modules": spec.modules,
                        }
                    )
                )
                diff_payload = diff_result.to_dict()
                stages.append(self._stage("custom_loader_module_diff", diff_result.status, diff_result.reason, side_effect=False))
        elif diff_payload:
            stages.append(self._stage("custom_loader_module_diff", str(diff_payload.get("status") or "observed"), None, side_effect=False, observed=True))
        else:
            stages.append(self._stage("custom_loader_module_diff", "pending", None, side_effect=False))
        if spec.install_module_hook:
            if not self._diff_ready(diff_payload):
                stages.append(self._stage("custom_loader_module_hook", "blocked", "custom_loader_module_diff_not_ready", side_effect=True))
            else:
                hook_result = CustomLoaderModuleHookManager().install(
                    page,
                    CustomLoaderModuleHookSpec.from_context(
                        {
                            "custom_loader_module_diff": diff_payload,
                            "candidate_index": spec.candidate_index,
                            "review_approved": spec.review_approved,
                        }
                    ),
                )
                hook_payload = hook_result.to_dict()
                stages.append(self._stage("custom_loader_module_hook", hook_result.status, hook_result.reason, side_effect=True))
        elif hook_payload:
            stages.append(self._stage("custom_loader_module_hook", str(hook_payload.get("status") or "observed"), None, side_effect=False, observed=True))
        else:
            stages.append(self._stage("custom_loader_module_hook", "pending", None, side_effect=True))
        if spec.append_journal:
            journal_result = CustomLoaderContinuationJournalManager().plan_or_append(
                CustomLoaderContinuationJournalSpec(
                    workflow=spec.workflow,
                    existing_journal=spec.existing_journal,
                    preflight=preflight_payload,
                    execution_result=execution_payload,
                    module_diff=diff_payload,
                    module_hook_result=hook_payload,
                    review_approved=spec.review_approved,
                    write_journal=True,
                )
            )
            journal_payload = journal_result.to_dict()
            stages.append(self._stage("continuation_journal", journal_result.status, journal_result.reason, side_effect=False))
        status = self._status(stages, preflight_payload, execution_payload, diff_payload, hook_payload, journal_payload)
        execution = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-execution.v1",
            "status": status,
            "workflow_id": spec.workflow.get("workflow_id"),
            "selected_candidate_index": spec.workflow.get("selected_candidate_index"),
            "review_approved": bool(spec.review_approved),
            "stages": stages,
            "preflight": preflight_payload,
            "custom_loader_execution_result": execution_payload,
            "custom_loader_module_diff": diff_payload,
            "custom_loader_module_hook_result": hook_payload,
            "custom_loader_continuation_journal": journal_payload,
            "next_action": self._next_action(status),
        }
        return CustomLoaderContinuationExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, stages=stages), reason=self._reason(stages))

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool, observed: bool = False) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect, "observed_input": observed}

    @staticmethod
    def _preflight_ready(payload: dict[str, Any]) -> bool:
        preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else payload
        return str(preflight.get("status") or "") == "ready_for_execution_review"

    @staticmethod
    def _execution_success(payload: dict[str, Any]) -> bool:
        execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else payload
        return payload.get("status") == "success" or execution.get("ok") is True

    @staticmethod
    def _diff_ready(payload: dict[str, Any]) -> bool:
        diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else payload
        return str(diff.get("status") or payload.get("status") or "") in {"ready_for_review", "planned"}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], preflight: dict[str, Any], execution: dict[str, Any], diff: dict[str, Any], hook: dict[str, Any], journal: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        if journal and (journal.get("status") == "journal_appended" or journal.get("journal", {}).get("status") == "journal_appended"):
            return "journal_appended"
        if hook:
            return "module_hook_recorded"
        if cls._diff_ready(diff):
            return "module_diff_ready"
        if cls._execution_success(execution):
            return "execution_complete"
        if cls._preflight_ready(preflight):
            return "preflight_ready"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for item in stages:
            if item["status"] in {"blocked", "failed", "error", "unsupported"} and item.get("reason"):
                return str(item["reason"])
        return None

    @staticmethod
    def _next_action(status: str) -> str:
        return {
            "preflight_ready": "execute_custom_loader_with_review_approval",
            "execution_complete": "run_custom_loader_module_diff_after_reviewed_execution",
            "module_diff_ready": "review_custom_loader_module_diff_hook_candidates",
            "module_hook_recorded": "append_custom_loader_continuation_journal",
            "journal_appended": "plan_next_custom_loader_continuation",
            "blocked": "resolve_custom_loader_continuation_execution_blockers",
            "failed": "inspect_custom_loader_continuation_execution_failure",
        }.get(status, "review_custom_loader_continuation_execution_plan")

    @staticmethod
    def _side_effect_policy(spec: CustomLoaderContinuationExecutionSpec | None = None, stages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        stages = stages or []
        return {
            "plan_only": not any(item["status"] not in {"pending", "observed"} and (item["stage"] != "preflight" or item["status"] != "ready_for_execution_review") for item in stages),
            "review_approved": bool(spec and spec.review_approved),
            "preflight_executed": bool(spec and spec.run_preflight),
            "loader_invoked": bool(spec and spec.execute_custom_loader and any(item["stage"] == "custom_loader_execution" and item["status"] == "success" for item in stages)),
            "custom_loader_executed": bool(spec and spec.execute_custom_loader and any(item["stage"] == "custom_loader_execution" and item["status"] == "success" for item in stages)),
            "module_diff_executed": bool(spec and spec.run_module_diff),
            "module_hook_installed": bool(spec and spec.install_module_hook and any(item["stage"] == "custom_loader_module_hook" and item["status"] == "success" for item in stages)),
            "writes_journal": bool(spec and spec.append_journal and any(item["stage"] == "continuation_journal" and item["status"] == "journal_appended" for item in stages)),
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderTraversalGraphSpec:
    """Review-only graph / queue planner for deeper custom-loader traversal."""

    traversal_plan: dict[str, Any] = field(default_factory=dict)
    continuation_journal: dict[str, Any] = field(default_factory=dict)
    continuation_execution: dict[str, Any] = field(default_factory=dict)
    previous_execution_results: list[dict[str, Any]] = field(default_factory=list)
    max_traversal_depth: int = 3
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalGraphSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_traversal_graph")
            or context.get("customLoaderTraversalGraph")
            or context.get("custom-loader-traversal-graph")
            or context.get("custom_loader_continuation_queue")
            or context.get("customLoaderContinuationQueue")
            or context.get("plan_custom_loader_deep_traversal")
            or context.get("planCustomLoaderDeepTraversal")
        )
        traversal_plan = (
            context.get("custom_loader_traversal_plan")
            or context.get("custom-loader-traversal-plan")
            or context.get("customLoaderTraversalPlan")
            or context.get("loader_traversal_plan")
            or context.get("loaderTraversalPlan")
        )
        if isinstance(traversal_plan, dict) and isinstance(traversal_plan.get("plan"), dict):
            traversal_plan = traversal_plan["plan"]
        continuation_journal = CustomLoaderContinuationJournalSpec._object_alias(
            context,
            "custom_loader_continuation_journal",
            "custom-loader-continuation-journal",
            "customLoaderContinuationJournal",
            "continuation_journal",
            "continuationJournal",
        )
        continuation_execution = CustomLoaderContinuationJournalSpec._object_alias(
            context,
            "custom_loader_continuation_execution",
            "custom-loader-continuation-execution",
            "customLoaderContinuationExecution",
            "continuation_execution",
            "continuationExecution",
        )
        execution_results: list[dict[str, Any]] = []
        for key in (
            "custom_loader_execution_result",
            "custom-loader-execution-result",
            "customLoaderExecutionResult",
            "previous_custom_loader_execution_result",
            "previousCustomLoaderExecutionResult",
        ):
            value = context.get(key)
            if isinstance(value, dict):
                execution_results.append(dict(value))
        for key in (
            "custom_loader_execution_results",
            "customLoaderExecutionResults",
            "previous_custom_loader_execution_results",
            "previousCustomLoaderExecutionResults",
        ):
            value = context.get(key)
            if isinstance(value, list):
                execution_results.extend(dict(item) for item in value if isinstance(item, dict))
        if isinstance(continuation_execution.get("execution"), dict):
            nested_execution = continuation_execution["execution"].get("custom_loader_execution_result")
            if isinstance(nested_execution, dict):
                execution_results.append(dict(nested_execution))
        if not isinstance(traversal_plan, dict):
            return None if not requested and not continuation_journal and not continuation_execution else cls(
                continuation_journal=continuation_journal,
                continuation_execution=continuation_execution,
                previous_execution_results=execution_results,
            )
        return cls(
            traversal_plan=dict(traversal_plan),
            continuation_journal=continuation_journal,
            continuation_execution=continuation_execution,
            previous_execution_results=execution_results,
            max_traversal_depth=max(1, int(context.get("max_traversal_depth", context.get("maxTraversalDepth", context.get("traversal_depth", 3))) or 3)),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderTraversalGraphResult:
    status: str
    graph: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "graph": self.graph,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderTraversalGraphManager:
    """Build a review-only traversal graph and queue for deeper custom-loader continuation."""

    def plan(self, spec: CustomLoaderTraversalGraphSpec | None) -> CustomLoaderTraversalGraphResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.traversal_plan:
            return CustomLoaderTraversalGraphResult(status="unsupported", reason="missing_custom_loader_traversal_plan", side_effect_policy=policy)
        candidates = self._candidate_records(spec.traversal_plan)
        journal_records = self._journal_records(spec.continuation_journal)
        executed_fingerprints = self._executed_fingerprints(spec, journal_records)
        nodes = [self._node(candidate, index=index, spec=spec, executed_fingerprints=executed_fingerprints) for index, candidate in enumerate(candidates)]
        edges = self._edges(nodes, journal_records)
        queue = [node for node in nodes if node.get("queue_status") == "ready_for_review"][: spec.max_queue_size]
        depth_blocked_count = sum(1 for node in nodes if node.get("queue_status") == "max_depth_blocked")
        duplicate_count = sum(1 for node in nodes if node.get("already_executed"))
        if queue:
            status = "ready_for_review"
            reason = None
        elif depth_blocked_count:
            status = "blocked"
            reason = "max_traversal_depth_exceeded"
        elif candidates:
            status = "complete"
            reason = None
        else:
            status = "blocked"
            reason = "no_custom_loader_candidates"
        graph = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-graph.v1",
            "status": status,
            "review_required": True,
            "graph_id": "custom-loader-traversal-graph",
            "max_traversal_depth": spec.max_traversal_depth,
            "candidate_count": len(candidates),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "journal_record_count": len(journal_records),
            "executed_fingerprint_count": len(executed_fingerprints),
            "queue_count": len(queue),
            "duplicate_executed_count": duplicate_count,
            "depth_blocked_count": depth_blocked_count,
            "nodes": nodes,
            "edges": edges,
            "review_queue": queue,
            "review_sequence": [
                "inspect_traversal_graph_nodes",
                "select_one_review_queue_candidate",
                "plan_custom_loader_continuation_workflow",
                "run_custom_loader_execution_preflight",
                "execute_one_reviewed_custom_loader_continuation_step",
                "append_custom_loader_continuation_journal",
                "rerun_traversal_graph_after_new_candidates",
            ],
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, queue=queue, depth_blocked_count=depth_blocked_count),
        }
        return CustomLoaderTraversalGraphResult(status=status, graph=graph, side_effect_policy=policy, reason=reason)

    @classmethod
    def _candidate_records(cls, traversal_plan: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = traversal_plan.get("candidates")
        if isinstance(candidates, list):
            return [dict(item) for item in candidates if isinstance(item, dict)]
        return []

    @classmethod
    def _journal_records(cls, journal: dict[str, Any]) -> list[dict[str, Any]]:
        nested = journal.get("journal") if isinstance(journal.get("journal"), dict) else journal
        records = nested.get("records") if isinstance(nested, dict) else []
        if isinstance(records, list):
            return [dict(item) for item in records if isinstance(item, dict)]
        return []

    @classmethod
    def _executed_fingerprints(cls, spec: CustomLoaderTraversalGraphSpec, records: list[dict[str, Any]]) -> set[str]:
        fingerprints = {str(record.get("candidate_fingerprint") or "").strip() for record in records if str(record.get("candidate_fingerprint") or "").strip()}
        fingerprints.update(
            "|".join(item)
            for item in CustomLoaderTraversalPlanManager._executed_candidate_fingerprints(spec.previous_execution_results)
        )
        execution = spec.continuation_execution.get("execution") if isinstance(spec.continuation_execution.get("execution"), dict) else {}
        execution_result = execution.get("custom_loader_execution_result") if isinstance(execution.get("custom_loader_execution_result"), dict) else {}
        selected = execution_result.get("selected_candidate") if isinstance(execution_result.get("selected_candidate"), dict) else {}
        if selected:
            fingerprints.add(cls._candidate_fingerprint(selected))
        return {item for item in fingerprints if item}

    @classmethod
    def _node(
        cls,
        candidate: dict[str, Any],
        *,
        index: int,
        spec: CustomLoaderTraversalGraphSpec,
        executed_fingerprints: set[str],
    ) -> dict[str, Any]:
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "")[: spec.max_preview_length]
        target = str(candidate.get("target") or loader_path)[: spec.max_preview_length]
        chunk_id = str(candidate.get("chunk_id") or candidate.get("chunkId") or target)[: spec.max_preview_length]
        parent_loader_path = str(candidate.get("parent_loader_path") or candidate.get("parentLoaderPath") or "")[: spec.max_preview_length]
        depth = CustomLoaderTraversalPlanManager._candidate_depth(candidate, default=1)
        fingerprint = str(candidate.get("fingerprint") or cls._candidate_fingerprint(candidate))
        already_executed = bool(candidate.get("already_executed") or candidate.get("alreadyExecuted") or fingerprint in executed_fingerprints)
        max_depth_exceeded = depth > spec.max_traversal_depth or bool(candidate.get("max_traversal_depth_exceeded") or candidate.get("maxTraversalDepthExceeded"))
        classification = str(candidate.get("classification") or "").strip() or "arbitrary_custom_loader"
        blocked_reasons = [str(item) for item in candidate.get("blocking_reasons", []) if str(item)] if isinstance(candidate.get("blocking_reasons"), list) else []
        continuation_supported = bool(candidate.get("continuation_supported") or candidate.get("continuationSupported") or candidate.get("traversal_supported"))
        if already_executed:
            queue_status = "already_executed"
        elif max_depth_exceeded:
            queue_status = "max_depth_blocked"
        elif classification == "arbitrary_custom_loader" and continuation_supported and not blocked_reasons:
            queue_status = "ready_for_review"
        elif classification == "arbitrary_custom_loader" and not blocked_reasons:
            queue_status = "candidate_review_required"
        else:
            queue_status = "blocked"
        return {
            "node_id": f"custom-loader-node-{index}",
            "candidate_index": candidate.get("index", index),
            "loader_path": loader_path,
            "target": target,
            "chunk_id": chunk_id,
            "parent_loader_path": parent_loader_path,
            "depth": depth,
            "fingerprint": fingerprint,
            "classification": classification,
            "candidate_status": candidate.get("status", ""),
            "queue_status": queue_status,
            "already_executed": already_executed,
            "max_traversal_depth_exceeded": max_depth_exceeded,
            "continuation_supported": continuation_supported,
            "blocking_reasons": blocked_reasons,
            "review_requirements": [
                "review_this_candidate_before_preflight",
                "execute_at_most_one_loader_step",
                "append_journal_before_replanning_deeper_traversal",
            ],
            "automatic_execution": False,
        }

    @classmethod
    def _edges(cls, nodes: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_loader = {str(node.get("loader_path")): node for node in nodes if node.get("loader_path")}
        edges: list[dict[str, Any]] = []
        for node in nodes:
            parent = str(node.get("parent_loader_path") or "")
            if parent and parent in by_loader:
                edges.append(
                    {
                        "from": by_loader[parent]["node_id"],
                        "to": node["node_id"],
                        "edge_type": "parent_loader_path",
                        "review_required": True,
                    }
                )
        for record in records:
            loader_path = str(record.get("loader_path") or "")
            if loader_path in by_loader:
                edges.append(
                    {
                        "from": "journal",
                        "to": by_loader[loader_path]["node_id"],
                        "edge_type": "journal_recorded_execution",
                        "review_required": False,
                    }
                )
        return edges

    @staticmethod
    def _candidate_fingerprint(candidate: dict[str, Any]) -> str:
        loader_path, target, chunk_id = CustomLoaderTraversalPlanManager._candidate_fingerprint(candidate)
        return "|".join((loader_path, target, chunk_id))

    @staticmethod
    def _next_action(*, status: str, queue: list[dict[str, Any]], depth_blocked_count: int) -> str:
        if status == "ready_for_review" and queue:
            return "review_custom_loader_traversal_graph_queue"
        if depth_blocked_count:
            return "review_custom_loader_traversal_depth_before_continuing"
        if status == "complete":
            return "custom_loader_traversal_graph_complete_or_provide_new_candidates"
        return "provide_custom_loader_traversal_plan_and_journal"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "preflight_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "writes_journal": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderTraversalWorkflowPlanSpec:
    """Review-only multi-step workflow planner over a custom-loader traversal graph."""

    traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_planned_steps: int = 3
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalWorkflowPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
            or context.get("custom_loader_deep_traversal_workflow")
            or context.get("customLoaderDeepTraversalWorkflow")
            or context.get("plan_custom_loader_traversal_workflow")
            or context.get("planCustomLoaderTraversalWorkflow")
        )
        graph = (
            context.get("custom_loader_traversal_graph")
            or context.get("customLoaderTraversalGraph")
            or context.get("custom-loader-traversal-graph")
            or context.get("traversal_graph")
            or context.get("traversalGraph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        if not isinstance(graph, dict):
            return None if not requested else cls()
        return cls(
            traversal_graph=dict(graph),
            max_planned_steps=max(1, int(context.get("max_planned_steps", context.get("maxPlannedSteps", 3)) or 3)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderTraversalWorkflowPlanResult:
    status: str
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "workflow_plan": self.workflow_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderTraversalWorkflowPlanManager:
    """Compose bounded review-only workflow steps from a traversal graph queue."""

    def plan(self, spec: CustomLoaderTraversalWorkflowPlanSpec | None) -> CustomLoaderTraversalWorkflowPlanResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.traversal_graph:
            return CustomLoaderTraversalWorkflowPlanResult(status="unsupported", reason="missing_custom_loader_traversal_graph", side_effect_policy=policy)
        graph = spec.traversal_graph
        graph_status = str(graph.get("status") or "").strip()
        queue = self._review_queue(graph)
        if graph_status == "complete":
            status = "complete"
            reason = None
            selected_queue: list[dict[str, Any]] = []
        elif not queue:
            status = "blocked"
            reason = self._blocked_reason(graph)
            selected_queue = []
        else:
            status = "ready_for_review"
            reason = None
            selected_queue = queue[: spec.max_planned_steps]
        planned_steps = [self._planned_step(item, step_index=index, spec=spec) for index, item in enumerate(selected_queue)]
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "custom-loader-traversal-workflow-plan",
            "review_required": True,
            "manual_checkpoint_required": True,
            "execute_at_most_one_loader_step_per_review": True,
            "source_graph_id": graph.get("graph_id", "custom-loader-traversal-graph"),
            "source_graph_status": graph_status,
            "source_graph_queue_count": int(graph.get("queue_count") or len(queue)),
            "source_graph_depth_blocked_count": int(graph.get("depth_blocked_count") or 0),
            "max_planned_steps": spec.max_planned_steps,
            "planned_step_count": len(planned_steps),
            "planned_steps": planned_steps,
            "workflow_sequence": self._workflow_sequence(),
            "blocking_reasons": [reason] if reason else [],
            "next_action": self._next_action(status=status, reason=reason),
            "side_effect_policy": policy,
        }
        return CustomLoaderTraversalWorkflowPlanResult(status=status, workflow_plan=workflow_plan, side_effect_policy=policy, reason=reason)

    @classmethod
    def _review_queue(cls, graph: dict[str, Any]) -> list[dict[str, Any]]:
        queue = graph.get("review_queue")
        if isinstance(queue, list):
            return [dict(item) for item in queue if isinstance(item, dict)]
        return []

    @staticmethod
    def _blocked_reason(graph: dict[str, Any]) -> str:
        graph_status = str(graph.get("status") or "").strip()
        if graph_status in {"blocked", "unsupported", "failed", "failure", "error"}:
            return "custom_loader_traversal_graph_blocked"
        if int(graph.get("depth_blocked_count") or 0):
            return "custom_loader_traversal_depth_review_required"
        return "no_custom_loader_traversal_queue"

    @classmethod
    def _planned_step(cls, queue_item: dict[str, Any], *, step_index: int, spec: CustomLoaderTraversalWorkflowPlanSpec) -> dict[str, Any]:
        loader_path = str(queue_item.get("loader_path") or queue_item.get("loaderPath") or queue_item.get("target") or "")[: spec.max_preview_length]
        target = str(queue_item.get("target") or loader_path)[: spec.max_preview_length]
        chunk_id = str(queue_item.get("chunk_id") or queue_item.get("chunkId") or target)[: spec.max_preview_length]
        return {
            "step_index": step_index,
            "step_id": f"custom-loader-traversal-step-{step_index}",
            "queue_node_id": queue_item.get("node_id"),
            "candidate_index": queue_item.get("candidate_index", queue_item.get("index", step_index)),
            "candidate_fingerprint": queue_item.get("fingerprint"),
            "loader_path": loader_path,
            "target": target,
            "chunk_id": chunk_id,
            "depth": queue_item.get("depth"),
            "queue_status": queue_item.get("queue_status"),
            "review_required": True,
            "manual_checkpoint_required": True,
            "automatic_execution": False,
            "execute_at_most_one_loader_step_per_review": True,
            "references": {
                "traversal_graph_artifact": "workspace/custom-loader-traversal-graph.json",
                "continuation_workflow_artifact": "workspace/custom-loader-continuation-workflow.json",
                "execution_preflight_artifact": "workspace/custom-loader-execution-preflight.json",
                "continuation_execution_artifact": "workspace/custom-loader-continuation-execution.json",
                "module_diff_artifact": "workspace/custom-loader-module-diff.json",
                "module_hook_artifact": "workspace/module-hooks.json",
                "continuation_journal_artifact": "workspace/custom-loader-continuation-journal.json",
            },
            "review_sequence": cls._workflow_sequence(),
            "next_action": "review_custom_loader_traversal_workflow_step",
        }

    @staticmethod
    def _workflow_sequence() -> list[dict[str, Any]]:
        return [
            {
                "order": 1,
                "action": "select_one_review_queue_candidate",
                "input_artifact": "workspace/custom-loader-traversal-graph.json",
                "output_artifact": None,
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 2,
                "action": "plan_custom_loader_continuation_workflow",
                "input_artifact": "workspace/custom-loader-traversal-plan.json",
                "output_artifact": "workspace/custom-loader-continuation-workflow.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 3,
                "action": "run_custom_loader_execution_preflight",
                "input_artifact": "workspace/custom-loader-continuation-workflow.json",
                "output_artifact": "workspace/custom-loader-execution-preflight.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 4,
                "action": "execute_one_reviewed_custom_loader_continuation_step",
                "input_artifact": "workspace/custom-loader-execution-preflight.json",
                "output_artifact": "workspace/custom-loader-continuation-execution.json",
                "review_required": True,
                "executes_runtime": True,
                "requires_review_approved": True,
            },
            {
                "order": 5,
                "action": "run_custom_loader_module_diff_after_reviewed_execution",
                "input_artifact": "workspace/custom-loader-continuation-execution.json",
                "output_artifact": "workspace/custom-loader-module-diff.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 6,
                "action": "optionally_install_reviewed_custom_loader_module_hook",
                "input_artifact": "workspace/custom-loader-module-diff.json",
                "output_artifact": "workspace/module-hooks.json",
                "review_required": True,
                "executes_runtime": True,
                "requires_review_approved": True,
            },
            {
                "order": 7,
                "action": "append_custom_loader_continuation_journal",
                "input_artifact": "workspace/custom-loader-continuation-execution.json",
                "output_artifact": "workspace/custom-loader-continuation-journal.json",
                "review_required": True,
                "executes_runtime": False,
                "requires_review_approved": True,
            },
            {
                "order": 8,
                "action": "rebuild_custom_loader_traversal_graph_after_new_evidence",
                "input_artifact": "workspace/custom-loader-continuation-journal.json",
                "output_artifact": "workspace/custom-loader-traversal-graph.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 9,
                "action": "stop_before_recursive_execution_and_request_next_review",
                "input_artifact": "workspace/custom-loader-traversal-graph.json",
                "output_artifact": None,
                "review_required": True,
                "executes_runtime": False,
            },
        ]

    @staticmethod
    def _next_action(*, status: str, reason: str | None) -> str:
        if status == "ready_for_review":
            return "review_custom_loader_traversal_workflow_plan"
        if status == "complete":
            return "custom_loader_traversal_graph_complete_or_provide_new_candidates"
        if reason == "custom_loader_traversal_depth_review_required":
            return "review_custom_loader_traversal_depth_before_continuing"
        if reason == "custom_loader_traversal_graph_blocked":
            return "revise_custom_loader_traversal_graph_inputs"
        return "provide_custom_loader_traversal_graph_with_queue"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "execute_at_most_one_loader_step_per_review": True,
            "preflight_executed": False,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "writes_journal": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderTraversalWorkflowExecutionSpec:
    """Review-gated executor over one selected custom-loader traversal workflow step."""

    workflow_plan: dict[str, Any] = field(default_factory=dict)
    traversal_plan: dict[str, Any] = field(default_factory=dict)
    continuation_workflow: dict[str, Any] = field(default_factory=dict)
    preflight: dict[str, Any] = field(default_factory=dict)
    execution_result: dict[str, Any] = field(default_factory=dict)
    module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    existing_journal: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    selected_step_index: int | None = None
    candidate_index: int | None = None
    plan_continuation_workflow: bool = False
    run_preflight: bool = False
    execute_custom_loader: bool = False
    run_module_diff: bool = False
    install_module_hook: bool = False
    append_journal: bool = False
    review_approved: bool = False
    loader_arguments: list[Any] = field(default_factory=list)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalWorkflowExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_traversal_workflow_execution")
            or context.get("customLoaderTraversalWorkflowExecution")
            or context.get("custom-loader-traversal-workflow-execution")
            or context.get("execute_custom_loader_traversal_workflow")
            or context.get("executeCustomLoaderTraversalWorkflow")
        )
        workflow_plan = (
            context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(workflow_plan, dict):
            return None if not requested else cls()
        traversal_plan = (
            context.get("custom_loader_traversal_plan")
            or context.get("custom-loader-traversal-plan")
            or context.get("customLoaderTraversalPlan")
            or context.get("loader_traversal_plan")
            or context.get("loaderTraversalPlan")
        )
        if isinstance(traversal_plan, dict) and isinstance(traversal_plan.get("plan"), dict):
            traversal_plan = traversal_plan["plan"]
        continuation_workflow = (
            context.get("custom_loader_continuation_workflow")
            or context.get("custom-loader-continuation-workflow")
            or context.get("customLoaderContinuationWorkflow")
            or context.get("continuation_workflow")
            or context.get("continuationWorkflow")
        )
        if isinstance(continuation_workflow, dict) and isinstance(continuation_workflow.get("workflow"), dict):
            continuation_workflow = continuation_workflow["workflow"]
        selected_step_index = cls._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex")))))
        candidate_index = cls._optional_int(context.get("candidate_index", context.get("candidateIndex")))
        loader_arguments_value = context.get("loader_arguments", context.get("loaderArguments"))
        loader_argument_value = context.get("loader_argument", context.get("loaderArgument"))
        if isinstance(loader_arguments_value, list):
            loader_arguments = list(loader_arguments_value)
        elif loader_arguments_value is not None:
            loader_arguments = [loader_arguments_value]
        elif loader_argument_value is not None:
            loader_arguments = [loader_argument_value]
        else:
            loader_arguments = []
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        return cls(
            workflow_plan=dict(workflow_plan),
            traversal_plan=dict(traversal_plan) if isinstance(traversal_plan, dict) else {},
            continuation_workflow=dict(continuation_workflow) if isinstance(continuation_workflow, dict) else {},
            preflight=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_preflight", "custom-loader-execution-preflight", "customLoaderExecutionPreflight"),
            execution_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_result", "custom-loader-execution-result", "customLoaderExecutionResult"),
            module_diff=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_diff", "custom-loader-module-diff", "customLoaderModuleDiff"),
            module_hook_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_hook_result", "custom-loader-module-hook-result", "customLoaderModuleHookResult", "module_hooks", "module-hooks"),
            existing_journal=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_continuation_journal", "custom-loader-continuation-journal", "customLoaderContinuationJournal"),
            module_discovery=CustomLoaderContinuationJournalSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_step_index=selected_step_index,
            candidate_index=candidate_index,
            plan_continuation_workflow=bool(context.get("plan_continuation_workflow") or context.get("planContinuationWorkflow") or context.get("plan_custom_loader_continuation_workflow") or context.get("planCustomLoaderContinuationWorkflow")),
            run_preflight=bool(context.get("run_preflight") or context.get("runPreflight") or context.get("execute_preflight") or context.get("executePreflight")),
            execute_custom_loader=bool(context.get("execute_custom_loader") or context.get("executeCustomLoader")),
            run_module_diff=bool(context.get("run_module_diff") or context.get("runModuleDiff") or context.get("refresh_module_diff") or context.get("refreshModuleDiff")),
            install_module_hook=bool(context.get("install_module_hook") or context.get("installModuleHook") or context.get("hook_custom_loader_module") or context.get("hookCustomLoaderModule")),
            append_journal=bool(context.get("append_journal") or context.get("appendJournal") or context.get("append_custom_loader_continuation_journal") or context.get("appendCustomLoaderContinuationJournal")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            loader_arguments=loader_arguments,
        )

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


@dataclass(slots=True)
class CustomLoaderTraversalWorkflowExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderTraversalWorkflowExecutionManager:
    """Execute at most one reviewed step from a traversal workflow plan."""

    def execute(self, page: BrowserPage, spec: CustomLoaderTraversalWorkflowExecutionSpec | None) -> CustomLoaderTraversalWorkflowExecutionResult:
        if spec is None or not spec.workflow_plan:
            return CustomLoaderTraversalWorkflowExecutionResult(status="unsupported", reason="missing_custom_loader_traversal_workflow_plan", side_effect_policy=self._side_effect_policy())
        selected_step = self._selected_step(spec)
        if not selected_step:
            execution = self._execution_payload(spec, {}, [], {}, {}, status="blocked", reason="missing_custom_loader_traversal_workflow_step")
            return CustomLoaderTraversalWorkflowExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_custom_loader_traversal_workflow_step")
        stages: list[dict[str, Any]] = [self._stage("select_traversal_workflow_step", "selected", "", side_effect=False)]
        continuation_workflow = dict(spec.continuation_workflow)
        continuation_execution_payload: dict[str, Any] = {}
        if spec.plan_continuation_workflow:
            if not spec.traversal_plan:
                stages.append(self._stage("plan_continuation_workflow", "blocked", "missing_custom_loader_traversal_plan", side_effect=False))
            else:
                workflow_result = CustomLoaderContinuationWorkflowManager().plan(
                    CustomLoaderContinuationWorkflowSpec.from_context(
                        {
                            "custom_loader_traversal_plan": spec.traversal_plan,
                            "candidate_index": self._candidate_index(spec, selected_step),
                            "review_approved": spec.review_approved,
                        }
                    )
                )
                continuation_workflow = workflow_result.workflow
                stages.append(self._stage("plan_continuation_workflow", workflow_result.status, workflow_result.reason, side_effect=False))
        elif continuation_workflow:
            stages.append(self._stage("plan_continuation_workflow", str(continuation_workflow.get("status") or "observed"), "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("plan_continuation_workflow", "pending", "", side_effect=False))
        if self._has_continuation_execution_flags(spec):
            if not continuation_workflow:
                stages.append(self._stage("execute_one_traversal_workflow_step", "blocked", "custom_loader_continuation_workflow_required", side_effect=True))
            else:
                continuation_execution = CustomLoaderContinuationExecutionManager().execute(
                    page,
                    CustomLoaderContinuationExecutionSpec(
                        workflow=continuation_workflow,
                        preflight=spec.preflight,
                        execution_result=spec.execution_result,
                        module_diff=spec.module_diff,
                        module_hook_result=spec.module_hook_result,
                        existing_journal=spec.existing_journal,
                        module_discovery=spec.module_discovery,
                        modules=spec.modules,
                        run_preflight=spec.run_preflight,
                        execute_custom_loader=spec.execute_custom_loader,
                        run_module_diff=spec.run_module_diff,
                        install_module_hook=spec.install_module_hook,
                        append_journal=spec.append_journal,
                        review_approved=spec.review_approved,
                        candidate_index=self._candidate_index(spec, selected_step),
                        loader_arguments=spec.loader_arguments,
                    ),
                )
                continuation_execution_payload = continuation_execution.to_dict()
                stages.append(self._stage("execute_one_traversal_workflow_step", continuation_execution.status, continuation_execution.reason, side_effect=True))
        elif any((spec.preflight, spec.execution_result, spec.module_diff, spec.module_hook_result, spec.existing_journal)):
            stages.append(self._stage("execute_one_traversal_workflow_step", "observed", "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("execute_one_traversal_workflow_step", "pending", "", side_effect=True))
        stages.append(self._stage("stop_before_recursive_traversal", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, continuation_workflow, continuation_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, selected_step, stages, continuation_workflow, continuation_execution_payload, status=status, reason=reason)
        return CustomLoaderTraversalWorkflowExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, continuation_execution=continuation_execution_payload), reason=reason)

    @staticmethod
    def _selected_step(spec: CustomLoaderTraversalWorkflowExecutionSpec) -> dict[str, Any]:
        steps = spec.workflow_plan.get("planned_steps") if isinstance(spec.workflow_plan.get("planned_steps"), list) else []
        normalized_steps = [dict(item) for item in steps if isinstance(item, dict)]
        if not normalized_steps:
            return {}
        selected_index = spec.selected_step_index if spec.selected_step_index is not None else 0
        for step in normalized_steps:
            if int(step.get("step_index", -1)) == selected_index:
                return step
        if 0 <= selected_index < len(normalized_steps):
            return normalized_steps[selected_index]
        return {}

    @staticmethod
    def _candidate_index(spec: CustomLoaderTraversalWorkflowExecutionSpec, selected_step: dict[str, Any]) -> int | None:
        if spec.candidate_index is not None:
            return spec.candidate_index
        raw = selected_step.get("candidate_index", selected_step.get("index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _has_continuation_execution_flags(spec: CustomLoaderTraversalWorkflowExecutionSpec) -> bool:
        return any((spec.run_preflight, spec.execute_custom_loader, spec.run_module_diff, spec.install_module_hook, spec.append_journal))

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool, observed: bool = False) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect, "observed_input": observed}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], continuation_workflow: dict[str, Any], continuation_execution: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        nested_execution = continuation_execution.get("execution") if isinstance(continuation_execution.get("execution"), dict) else {}
        nested_status = str(continuation_execution.get("status") or nested_execution.get("status") or "")
        if nested_status in {"journal_appended", "module_hook_recorded", "module_diff_ready", "execution_complete", "preflight_ready"}:
            return nested_status
        if continuation_workflow:
            workflow_status = str(continuation_workflow.get("status") or "")
            if workflow_status == "approved_for_preflight":
                return "continuation_workflow_approved"
            if workflow_status in {"ready_for_review", "planned"}:
                return "continuation_workflow_ready"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for item in stages:
            if item["status"] in {"blocked", "failed", "error", "unsupported"} and item.get("reason"):
                return str(item["reason"])
        return None

    @classmethod
    def _execution_payload(
        cls,
        spec: CustomLoaderTraversalWorkflowExecutionSpec,
        selected_step: dict[str, Any],
        stages: list[dict[str, Any]],
        continuation_workflow: dict[str, Any],
        continuation_execution: dict[str, Any],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        nested_execution = continuation_execution.get("execution") if isinstance(continuation_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-execution.v1",
            "status": status,
            "reason": reason,
            "workflow_plan_id": spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.workflow_plan.get("source_graph_id"),
            "selected_step_index": selected_step.get("step_index"),
            "selected_candidate_index": cls._candidate_index(spec, selected_step),
            "selected_step": selected_step,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "execute_at_most_one_loader_step_per_review": True,
            "stages": stages,
            "custom_loader_continuation_workflow": continuation_workflow,
            "custom_loader_continuation_execution": continuation_execution,
            "continuation_execution_status": continuation_execution.get("status") or nested_execution.get("status"),
            "artifact_refs": {
                "workflow_plan": "workspace/custom-loader-traversal-workflow-plan.json",
                "continuation_workflow": "workspace/custom-loader-continuation-workflow.json" if continuation_workflow else "",
                "continuation_execution": "workspace/custom-loader-continuation-execution.json" if continuation_execution else "",
                "continuation_journal": "workspace/custom-loader-continuation-journal.json" if nested_execution.get("custom_loader_continuation_journal") else "",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "continuation_workflow_ready":
            return "review_custom_loader_continuation_workflow_before_preflight"
        if status == "continuation_workflow_approved":
            return "run_custom_loader_execution_preflight_for_selected_traversal_step"
        if status == "preflight_ready":
            return "execute_custom_loader_with_review_approval"
        if status == "execution_complete":
            return "run_custom_loader_module_diff_after_reviewed_execution"
        if status == "module_diff_ready":
            return "review_custom_loader_module_diff_hook_candidates"
        if status == "module_hook_recorded":
            return "append_custom_loader_continuation_journal"
        if status == "journal_appended":
            return "rebuild_custom_loader_traversal_graph_and_stop_before_next_review"
        if status == "blocked" and reason:
            return "resolve_custom_loader_traversal_workflow_execution_blockers"
        if status == "failed":
            return "inspect_custom_loader_traversal_workflow_execution_failure"
        return "review_custom_loader_traversal_workflow_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: CustomLoaderTraversalWorkflowExecutionSpec | None = None,
        continuation_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nested_policy = continuation_execution.get("side_effect_policy") if isinstance(continuation_execution, dict) and isinstance(continuation_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only": not bool(spec and (spec.plan_continuation_workflow or spec.run_preflight or spec.execute_custom_loader or spec.run_module_diff or spec.install_module_hook or spec.append_journal)),
            "review_required": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "execute_at_most_one_loader_step_per_review": True,
            "continuation_workflow_planned": bool(spec and spec.plan_continuation_workflow),
            "preflight_executed": bool(nested_policy.get("preflight_executed", False)),
            "loader_invoked": bool(nested_policy.get("loader_invoked", False)),
            "custom_loader_executed": bool(nested_policy.get("custom_loader_executed", False)),
            "module_diff_executed": bool(nested_policy.get("module_diff_executed", False)),
            "module_hook_installed": bool(nested_policy.get("module_hook_installed", False)),
            "writes_journal": bool(nested_policy.get("writes_journal", False)),
            "traversal_graph_rebuilt": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderTraversalLoopPlanSpec:
    """Review-only bounded loop planner over custom-loader traversal workflow steps."""

    workflow_plan: dict[str, Any] = field(default_factory=dict)
    latest_workflow_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_loop_iterations: int = 3
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalLoopPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_traversal_loop_plan")
            or context.get("customLoaderTraversalLoopPlan")
            or context.get("custom-loader-traversal-loop-plan")
            or context.get("custom_loader_deep_traversal_loop")
            or context.get("customLoaderDeepTraversalLoop")
            or context.get("plan_custom_loader_traversal_loop")
            or context.get("planCustomLoaderTraversalLoop")
        )
        workflow_plan = (
            context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(workflow_plan, dict):
            return None if not requested else cls()
        latest_execution = (
            context.get("custom_loader_traversal_workflow_execution")
            or context.get("customLoaderTraversalWorkflowExecution")
            or context.get("custom-loader-traversal-workflow-execution")
            or context.get("latest_custom_loader_traversal_workflow_execution")
            or context.get("latestCustomLoaderTraversalWorkflowExecution")
        )
        if isinstance(latest_execution, dict) and isinstance(latest_execution.get("execution"), dict):
            latest_execution = latest_execution["execution"]
        latest_graph = (
            context.get("latest_custom_loader_traversal_graph")
            or context.get("latestCustomLoaderTraversalGraph")
            or context.get("custom_loader_traversal_graph")
            or context.get("customLoaderTraversalGraph")
            or context.get("custom-loader-traversal-graph")
        )
        if isinstance(latest_graph, dict) and isinstance(latest_graph.get("graph"), dict):
            latest_graph = latest_graph["graph"]
        return cls(
            workflow_plan=dict(workflow_plan),
            latest_workflow_execution=dict(latest_execution) if isinstance(latest_execution, dict) else {},
            latest_traversal_graph=dict(latest_graph) if isinstance(latest_graph, dict) else {},
            max_loop_iterations=max(1, int(context.get("max_loop_iterations", context.get("maxLoopIterations", context.get("max_iterations", 3))) or 3)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderTraversalLoopPlanResult:
    status: str
    loop_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "loop_plan": self.loop_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderTraversalLoopPlanManager:
    """Plan bounded custom-loader traversal loop checkpoints without executing them."""

    def plan(self, spec: CustomLoaderTraversalLoopPlanSpec | None) -> CustomLoaderTraversalLoopPlanResult:
        policy = self._side_effect_policy(max_loop_iterations=spec.max_loop_iterations if spec else 0)
        if spec is None or not spec.workflow_plan:
            return CustomLoaderTraversalLoopPlanResult(status="unsupported", reason="missing_custom_loader_traversal_workflow_plan", side_effect_policy=policy)
        workflow_status = str(spec.workflow_plan.get("status") or "").strip()
        planned_steps = self._planned_steps(spec.workflow_plan)
        if workflow_status == "complete":
            status = "complete"
            reason = None
            selected_steps: list[dict[str, Any]] = []
        elif not planned_steps:
            status = "blocked"
            reason = "no_custom_loader_traversal_workflow_steps"
            selected_steps = []
        else:
            status = "ready_for_review"
            reason = None
            selected_steps = planned_steps[: spec.max_loop_iterations]
        latest_execution_status = self._latest_execution_status(spec.latest_workflow_execution)
        iterations = [self._iteration(step, iteration_index=index, spec=spec) for index, step in enumerate(selected_steps)]
        loop_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-loop-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "custom-loader-traversal-loop-plan",
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "max_loop_iterations": spec.max_loop_iterations,
            "planned_iteration_count": len(iterations),
            "source_workflow_plan_id": spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.workflow_plan.get("source_graph_id"),
            "source_workflow_status": workflow_status,
            "source_planned_step_count": len(planned_steps),
            "latest_workflow_execution_status": latest_execution_status,
            "latest_graph_status": str(spec.latest_traversal_graph.get("status") or ""),
            "iterations": iterations,
            "loop_sequence": self._loop_sequence(),
            "loop_checkpoint_policy": {
                "execute_at_most_one_loader_step_per_review": True,
                "append_journal_before_next_iteration": True,
                "rebuild_graph_before_next_iteration": True,
                "stop_after_each_iteration_for_manual_review": True,
                "automatic_queue_advance": False,
            },
            "blocking_reasons": [reason] if reason else [],
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason, latest_execution_status=latest_execution_status),
        }
        return CustomLoaderTraversalLoopPlanResult(status=status, loop_plan=loop_plan, side_effect_policy=policy, reason=reason)

    @classmethod
    def _planned_steps(cls, workflow_plan: dict[str, Any]) -> list[dict[str, Any]]:
        steps = workflow_plan.get("planned_steps")
        if isinstance(steps, list):
            return [dict(item) for item in steps if isinstance(item, dict)]
        return []

    @classmethod
    def _iteration(cls, step: dict[str, Any], *, iteration_index: int, spec: CustomLoaderTraversalLoopPlanSpec) -> dict[str, Any]:
        loader_path = str(step.get("loader_path") or step.get("loaderPath") or step.get("target") or "")[: spec.max_preview_length]
        return {
            "iteration_index": iteration_index,
            "iteration_id": f"custom-loader-traversal-loop-iteration-{iteration_index}",
            "source_step_index": step.get("step_index", iteration_index),
            "candidate_index": step.get("candidate_index"),
            "candidate_fingerprint": step.get("candidate_fingerprint"),
            "loader_path": loader_path,
            "depth": step.get("depth"),
            "review_required": True,
            "manual_checkpoint_required": True,
            "automatic_execution": False,
            "automatic_queue_advance": False,
            "execute_at_most_one_loader_step_per_review": True,
            "required_artifacts_before_next_iteration": [
                "workspace/custom-loader-traversal-workflow-execution.json",
                "workspace/custom-loader-continuation-journal.json",
                "workspace/custom-loader-traversal-graph.json",
                "workspace/custom-loader-traversal-workflow-plan.json",
            ],
            "planned_actions": cls._loop_sequence(),
            "next_action": "review_custom_loader_traversal_loop_iteration",
        }

    @staticmethod
    def _loop_sequence() -> list[dict[str, Any]]:
        return [
            {
                "order": 1,
                "action": "select_one_planned_traversal_workflow_step",
                "input_artifact": "workspace/custom-loader-traversal-workflow-plan.json",
                "output_artifact": None,
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 2,
                "action": "execute_selected_traversal_workflow_step_with_explicit_stage_flags",
                "input_artifact": "workspace/custom-loader-traversal-workflow-plan.json",
                "output_artifact": "workspace/custom-loader-traversal-workflow-execution.json",
                "executes_runtime": True,
                "review_required": True,
                "requires_review_approved": True,
            },
            {
                "order": 3,
                "action": "append_continuation_journal_if_step_succeeds",
                "input_artifact": "workspace/custom-loader-traversal-workflow-execution.json",
                "output_artifact": "workspace/custom-loader-continuation-journal.json",
                "executes_runtime": False,
                "review_required": True,
                "requires_review_approved": True,
            },
            {
                "order": 4,
                "action": "rebuild_traversal_graph_from_journal_and_new_candidates",
                "input_artifact": "workspace/custom-loader-continuation-journal.json",
                "output_artifact": "workspace/custom-loader-traversal-graph.json",
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 5,
                "action": "replan_traversal_workflow_from_refreshed_graph",
                "input_artifact": "workspace/custom-loader-traversal-graph.json",
                "output_artifact": "workspace/custom-loader-traversal-workflow-plan.json",
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 6,
                "action": "stop_before_next_loop_iteration_review",
                "input_artifact": "workspace/custom-loader-traversal-workflow-plan.json",
                "output_artifact": None,
                "executes_runtime": False,
                "review_required": True,
            },
        ]

    @staticmethod
    def _latest_execution_status(execution: dict[str, Any]) -> str:
        if not execution:
            return ""
        nested = execution.get("execution") if isinstance(execution.get("execution"), dict) else execution
        return str(nested.get("status") or execution.get("status") or "")

    @staticmethod
    def _next_action(*, status: str, reason: str | None, latest_execution_status: str) -> str:
        if status == "ready_for_review":
            if latest_execution_status == "journal_appended":
                return "rebuild_custom_loader_traversal_graph_before_next_loop_iteration"
            return "review_custom_loader_traversal_loop_plan"
        if status == "complete":
            return "custom_loader_traversal_loop_complete_or_provide_new_candidates"
        if reason:
            return "revise_custom_loader_traversal_loop_inputs"
        return "inspect_custom_loader_traversal_loop_plan"

    @staticmethod
    def _side_effect_policy(*, max_loop_iterations: int) -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "max_loop_iterations": max_loop_iterations,
            "execute_at_most_one_loader_step_per_review": True,
            "automatic_loop_execution": False,
            "automatic_recursive_traversal": False,
            "automatic_queue_advance": False,
            "traversal_graph_rebuilt": False,
            "preflight_executed": False,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "writes_journal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderExecutionPreflightSpec:
    """Side-effect-free preflight for a reviewed custom loader execution candidate."""

    traversal_plan: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    candidate_index: int | None = None
    review_approved: bool = False
    expected_loader_path: str | None = None
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderExecutionPreflightSpec | None":
        context = context or {}
        plan = (
            context.get("custom_loader_traversal_plan")
            or context.get("custom-loader-traversal-plan")
            or context.get("customLoaderTraversalPlan")
            or context.get("loader_traversal_plan")
            or context.get("loaderTraversalPlan")
        )
        if not isinstance(plan, dict):
            return None
        index_value = context.get("candidate_index", context.get("candidateIndex"))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        selected = (
            context.get("selected_custom_loader_candidate")
            or context.get("selectedCustomLoaderCandidate")
            or context.get("selected_loader_candidate")
            or context.get("selectedLoaderCandidate")
            or context.get("selected_candidate")
            or context.get("selectedCandidate")
            or context.get("loader_candidate")
            or context.get("loaderCandidate")
        )
        expected_loader_path = context.get("expected_loader_path", context.get("expectedLoaderPath"))
        return cls(
            traversal_plan=dict(plan),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            candidate_index=candidate_index,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            expected_loader_path=str(expected_loader_path).strip() if expected_loader_path is not None else None,
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderExecutionPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "preflight": self.preflight,
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderExecutionPreflightManager:
    """Validate a selected custom-loader candidate before any reviewed execution."""

    def preflight(self, spec: CustomLoaderExecutionPreflightSpec | None) -> CustomLoaderExecutionPreflightResult:
        policy = self._side_effect_policy(review_approved=bool(spec and spec.review_approved))
        if spec is None:
            return CustomLoaderExecutionPreflightResult(status="unsupported", reason="missing_custom_loader_traversal_plan", side_effect_policy=policy)
        candidate = self._select_candidate(spec)
        checks = self._checks(candidate, spec)
        blocking_reasons = [item["reason"] for item in checks if not item.get("passed")]
        if not candidate:
            blocking_reasons.insert(0, "review_custom_loader_traversal_plan")
        if not spec.review_approved:
            blocking_reasons.insert(0, "review_approval_required")
        status = "ready_for_execution_review" if not blocking_reasons else "blocked"
        reason = None if status != "blocked" else blocking_reasons[0]
        preflight = {
            "schema_version": "reverse-deepagent.custom-loader-execution-preflight.v1",
            "status": status,
            "review_required": True,
            "review_approved": bool(spec.review_approved),
            "candidate_index": candidate.get("index") if candidate else spec.candidate_index,
            "selected_candidate": candidate,
            "checks": checks,
            "blocking_reasons": blocking_reasons,
            "execution_contract": {
                "single_step_only": True,
                "requires_review_approval": True,
                "requires_strict_dotted_loader_path": True,
                "requires_expected_loader_path_match": bool(spec.expected_loader_path),
                "execute_dynamic_import": False,
                "execute_module_federation_get_init": False,
                "execute_webpack_loader": False,
                "automatic_recursive_traversal": False,
            },
            "side_effect_policy": policy,
            "next_action": "execute_custom_loader_with_review_approval" if status == "ready_for_execution_review" else "resolve_custom_loader_preflight_blockers",
        }
        return CustomLoaderExecutionPreflightResult(status=status, preflight=preflight, selected_candidate=candidate, side_effect_policy=policy, reason=reason)

    @classmethod
    def _select_candidate(cls, spec: CustomLoaderExecutionPreflightSpec) -> dict[str, Any]:
        if spec.selected_candidate:
            return dict(spec.selected_candidate)
        candidates = spec.traversal_plan.get("candidates") if isinstance(spec.traversal_plan, dict) else None
        if not isinstance(candidates, list):
            return {}
        index = 0 if spec.candidate_index is None else spec.candidate_index
        if index < 0 or index >= len(candidates):
            return {}
        candidate = candidates[index]
        return dict(candidate) if isinstance(candidate, dict) else {}

    @classmethod
    def _checks(cls, candidate: dict[str, Any], spec: CustomLoaderExecutionPreflightSpec) -> list[dict[str, Any]]:
        if not candidate:
            return [{"name": "candidate_selected", "passed": False, "reason": "missing_selected_custom_loader_candidate"}]
        loader_kind = str(candidate.get("loader_kind") or candidate.get("loaderKind") or "custom-loader").strip().lower()
        classification = str(candidate.get("classification") or "").strip().lower()
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "").strip()
        edge_type = str(candidate.get("edge_type") or candidate.get("edgeType") or "").strip().lower()
        status = str(candidate.get("status") or "").strip().lower()
        already_executed = bool(candidate.get("already_executed") or candidate.get("alreadyExecuted") or status == "already_executed")
        max_depth_exceeded = bool(candidate.get("max_traversal_depth_exceeded") or candidate.get("maxTraversalDepthExceeded"))
        is_custom_loader = loader_kind not in CustomLoaderTraversalPlanManager.WEBPACK_KINDS | CustomLoaderTraversalPlanManager.DYNAMIC_IMPORT_KINDS | CustomLoaderTraversalPlanManager.FEDERATION_KINDS and classification in {"arbitrary_custom_loader", "", "custom_loader"}
        expected_match = True if not spec.expected_loader_path else loader_path == spec.expected_loader_path
        return [
            {"name": "candidate_selected", "passed": True, "details": {"index": candidate.get("index")}},
            {"name": "review_approved", "passed": bool(spec.review_approved), "reason": "review_approval_required" if not spec.review_approved else ""},
            {"name": "not_already_executed", "passed": not already_executed, "reason": "custom_loader_candidate_already_executed" if already_executed else ""},
            {"name": "within_traversal_depth", "passed": not max_depth_exceeded, "reason": "max_traversal_depth_exceeded" if max_depth_exceeded else ""},
            {"name": "custom_loader_candidate", "passed": bool(is_custom_loader), "reason": "unsupported_loader_kind_for_custom_execution_preflight" if not is_custom_loader else "", "details": {"loader_kind": loader_kind, "classification": classification, "edge_type": edge_type}},
            {"name": "strict_dotted_loader_path", "passed": bool(JS_DOTTED_PATH_RE.fullmatch(loader_path)), "reason": "strict_dotted_loader_path_required" if not JS_DOTTED_PATH_RE.fullmatch(loader_path) else "", "details": {"loader_path": loader_path[: spec.max_preview_length]}},
            {"name": "expected_loader_path_match", "passed": bool(expected_match), "reason": "expected_loader_path_mismatch" if not expected_match else "", "details": {"expected_loader_path": spec.expected_loader_path or "", "loader_path": loader_path[: spec.max_preview_length]}},
            {"name": "dynamic_import_blocked", "passed": loader_kind not in CustomLoaderTraversalPlanManager.DYNAMIC_IMPORT_KINDS and edge_type != "dynamic-import", "reason": "dynamic_import_requires_dedicated_gate" if loader_kind in CustomLoaderTraversalPlanManager.DYNAMIC_IMPORT_KINDS or edge_type == "dynamic-import" else ""},
            {"name": "module_federation_blocked", "passed": loader_kind not in CustomLoaderTraversalPlanManager.FEDERATION_KINDS and "federation" not in edge_type, "reason": "module_federation_requires_dedicated_gate" if loader_kind in CustomLoaderTraversalPlanManager.FEDERATION_KINDS or "federation" in edge_type else ""},
            {"name": "webpack_loader_redirect", "passed": loader_kind not in CustomLoaderTraversalPlanManager.WEBPACK_KINDS, "reason": "use_async_chunk_load_for_webpack_loader" if loader_kind in CustomLoaderTraversalPlanManager.WEBPACK_KINDS else ""},
        ]

    @staticmethod
    def _side_effect_policy(*, review_approved: bool) -> dict[str, Any]:
        return {
            "preflight_only": True,
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": review_approved,
            "loader_invoked": False,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "dynamic_import_executed": False,
            "custom_loader_executed": False,
            "module_factory_invoked": False,
            "module_federation_get_init_executed": False,
            "browser_state_mutated": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderExecutionSpec:
    """Review-approved single custom loader execution request from a preflight payload."""

    preflight: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    loader_arguments: list[Any] = field(default_factory=list)
    capture_result: bool = True
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderExecutionSpec | None":
        context = context or {}
        preflight = (
            context.get("custom_loader_execution_preflight")
            or context.get("custom-loader-execution-preflight")
            or context.get("customLoaderExecutionPreflight")
            or context.get("custom_loader_preflight")
            or context.get("customLoaderPreflight")
            or context.get("preflight")
        )
        if not isinstance(preflight, dict):
            return None
        selected = (
            context.get("selected_custom_loader_candidate")
            or context.get("selectedCustomLoaderCandidate")
            or context.get("selected_loader_candidate")
            or context.get("selectedLoaderCandidate")
            or context.get("selected_candidate")
            or context.get("selectedCandidate")
            or context.get("loader_candidate")
            or context.get("loaderCandidate")
        )
        loader_arguments_value = context.get("loader_arguments", context.get("loaderArguments"))
        loader_argument_value = context.get("loader_argument", context.get("loaderArgument"))
        if isinstance(loader_arguments_value, list):
            loader_arguments = list(loader_arguments_value)
        elif loader_arguments_value is not None:
            loader_arguments = [loader_arguments_value]
        elif loader_argument_value is not None:
            loader_arguments = [loader_argument_value]
        else:
            loader_arguments = []
        return cls(
            preflight=dict(preflight),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
            loader_arguments=loader_arguments,
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class CustomLoaderExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class CustomLoaderExecutionManager:
    """Execute exactly one reviewed arbitrary custom loader and record registry/cache diffs."""

    def execute(self, page: BrowserPage, spec: CustomLoaderExecutionSpec | None) -> CustomLoaderExecutionResult:
        if spec is None:
            return CustomLoaderExecutionResult(status="unsupported", reason="missing_custom_loader_execution_preflight", side_effect_policy=self._blocked_side_effect_policy())
        if not spec.review_approved:
            return CustomLoaderExecutionResult(status="blocked", reason="review_approval_required", side_effect_policy=self._blocked_side_effect_policy())
        preflight = self._preflight_payload(spec.preflight)
        if not preflight:
            return CustomLoaderExecutionResult(status="blocked", reason="missing_custom_loader_execution_preflight", side_effect_policy=self._blocked_side_effect_policy(review_approved=spec.review_approved))
        if str(preflight.get("status") or "") != "ready_for_execution_review":
            return CustomLoaderExecutionResult(status="blocked", reason="custom_loader_preflight_not_ready", side_effect_policy=self._blocked_side_effect_policy(review_approved=spec.review_approved))
        candidate = self._selected_candidate(spec, preflight)
        readiness_error = self._execution_readiness_error(candidate)
        if readiness_error:
            return CustomLoaderExecutionResult(status="blocked", selected_candidate=candidate, reason=readiness_error, side_effect_policy=self._blocked_side_effect_policy(review_approved=spec.review_approved))
        try:
            payload = page.evaluate(self._execution_expression(candidate, spec))
        except Exception as exc:
            return CustomLoaderExecutionResult(
                status="failed",
                selected_candidate=candidate,
                execution={"attempted": True, "ok": False, "error": str(exc)},
                side_effect_policy=self._executed_side_effect_policy(loader_invoked=True),
                error=str(exc),
            )
        execution = payload if isinstance(payload, dict) else {"attempted": True, "ok": False, "result": payload}
        status = "success" if execution.get("ok") else "failed"
        return CustomLoaderExecutionResult(
            status=status,
            execution=execution,
            selected_candidate=candidate,
            side_effect_policy=self._executed_side_effect_policy(loader_invoked=bool(execution.get("loaderInvoked", execution.get("attempted", False)))),
            reason=str(execution.get("reason")) if execution.get("reason") else None,
            error=str(execution.get("error")) if execution.get("error") else None,
        )

    @staticmethod
    def _preflight_payload(payload: dict[str, Any]) -> dict[str, Any]:
        nested = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else None
        return dict(nested or payload)

    @staticmethod
    def _selected_candidate(spec: CustomLoaderExecutionSpec, preflight: dict[str, Any]) -> dict[str, Any]:
        if spec.selected_candidate:
            return dict(spec.selected_candidate)
        candidate = preflight.get("selected_candidate") or preflight.get("selectedCandidate")
        return dict(candidate) if isinstance(candidate, dict) else {}

    @staticmethod
    def _execution_readiness_error(candidate: dict[str, Any]) -> str | None:
        if not candidate:
            return "missing_selected_custom_loader_candidate"
        loader_kind = str(candidate.get("loader_kind") or candidate.get("loaderKind") or "custom-loader").strip().lower()
        classification = str(candidate.get("classification") or "").strip().lower()
        edge_type = str(candidate.get("edge_type") or candidate.get("edgeType") or "").strip().lower()
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "").strip()
        if loader_kind in CustomLoaderTraversalPlanManager.DYNAMIC_IMPORT_KINDS or edge_type == "dynamic-import":
            return "dynamic_import_requires_dedicated_gate"
        if loader_kind in CustomLoaderTraversalPlanManager.FEDERATION_KINDS or "federation" in edge_type:
            return "module_federation_requires_dedicated_gate"
        if loader_kind in CustomLoaderTraversalPlanManager.WEBPACK_KINDS:
            return "use_async_chunk_load_for_webpack_loader"
        if classification not in {"arbitrary_custom_loader", "", "custom_loader"}:
            return "unsupported_custom_loader_candidate"
        if not loader_path or not JS_DOTTED_PATH_RE.fullmatch(loader_path):
            return "strict_dotted_loader_path_required"
        return None

    @staticmethod
    def _path_parts(path: str) -> list[str]:
        parts = [item for item in str(path or "").split(".") if item]
        if parts and parts[0] == "window":
            parts = parts[1:]
        return parts

    @staticmethod
    def _blocked_side_effect_policy(*, review_approved: bool = False) -> dict[str, Any]:
        return {
            "requires_review_approval": True,
            "review_approved": review_approved,
            "loader_invoked": False,
            "custom_loader_executed": False,
            "runtime_loader_executed": False,
            "chunk_request_may_be_sent": False,
            "dynamic_import_executed": False,
            "module_factory_invoked": False,
            "module_federation_get_init_executed": False,
            "browser_state_mutated": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _executed_side_effect_policy(*, loader_invoked: bool) -> dict[str, Any]:
        return {
            "requires_review_approval": True,
            "review_approved": True,
            "loader_invoked": loader_invoked,
            "custom_loader_executed": loader_invoked,
            "runtime_loader_executed": loader_invoked,
            "chunk_request_may_be_sent": loader_invoked,
            "dynamic_import_executed": False,
            "module_factory_invoked": False,
            "module_federation_get_init_executed": False,
            "browser_state_mutated": loader_invoked,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _execution_expression(cls, candidate: dict[str, Any], spec: CustomLoaderExecutionSpec) -> str:
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or candidate.get("target") or "").strip()
        loader_path_json = json.dumps(loader_path, ensure_ascii=False)
        loader_parts_json = json.dumps(cls._path_parts(loader_path), ensure_ascii=False)
        loader_args_json = json.dumps(spec.loader_arguments, ensure_ascii=False, default=str)
        capture_result = "true" if spec.capture_result else "false"
        max_preview_length = max(1, int(spec.max_preview_length))
        return f"""
(async () => {{
  const marker = "__REVERSE_AGENT_CUSTOM_LOADER_EXECUTION__";
  const loaderPath = {loader_path_json};
  const loaderPathParts = {loader_parts_json};
  const loaderArguments = {loader_args_json};
  const captureResult = {capture_result};
  const maxPreviewLength = {max_preview_length};
  const describeError = (error) => String(error && (error.stack || error.message) || error).slice(0, maxPreviewLength);
  const previewValue = (value) => {{
    const type = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
    const preview = (() => {{
      try {{
        if (type === "function") return String(value).slice(0, maxPreviewLength);
        if (type === "object" || type === "array") return JSON.stringify(value).slice(0, maxPreviewLength);
        return String(value).slice(0, maxPreviewLength);
      }} catch (error) {{
        return describeError(error);
      }}
    }})();
    const keys = value && typeof value === "object" ? Object.keys(value).map(String).sort().slice(0, 30) : [];
    return {{
      type,
      constructorName: value && value.constructor && value.constructor.name || "",
      name: type === "function" ? value.name || "" : "",
      keys,
      preview
    }};
  }};
  const resolvePath = (parts) => {{
    try {{
      let value = window;
      for (const part of parts) {{
        if (!part || !/^[A-Za-z_$][\\w$]*$/.test(part)) return {{ ok: false, error: "unsafe_loader_path_segment" }};
        value = value && value[part];
      }}
      return {{ ok: true, value }};
    }} catch (error) {{
      return {{ ok: false, error: describeError(error) }};
    }}
  }};
  const sortedKeys = (value) => value && typeof value === "object" ? Object.keys(value).map(String).sort() : [];
  const snapshotRuntime = () => {{
    const req = window && window.__webpack_require__;
    return {{
      registryKeys: req && req.m && typeof req.m === "object" ? sortedKeys(req.m) : [],
      cacheKeys: req && req.c && typeof req.c === "object" ? sortedKeys(req.c) : []
    }};
  }};
  const diffAdded = (before, after) => after.filter((item) => !before.includes(item)).slice(0, 100);
  const diffRemoved = (before, after) => before.filter((item) => !after.includes(item)).slice(0, 100);
  const finish = (ok, reason, value, error) => {{
    const after = snapshotRuntime();
    return {{
      marker,
      attempted: true,
      ok,
      status: ok ? "success" : "failed",
      reason,
      error: error || "",
      loaderPath,
      loaderInvoked: reason !== "custom_loader_not_function" && reason !== "loader_path_unavailable",
      beforeRegistryCount: before.registryKeys.length,
      afterRegistryCount: after.registryKeys.length,
      addedRegistryKeys: diffAdded(before.registryKeys, after.registryKeys),
      removedRegistryKeys: diffRemoved(before.registryKeys, after.registryKeys),
      changedRegistryKeys: [],
      beforeCacheCount: before.cacheKeys.length,
      afterCacheCount: after.cacheKeys.length,
      addedCacheKeys: diffAdded(before.cacheKeys, after.cacheKeys),
      removedCacheKeys: diffRemoved(before.cacheKeys, after.cacheKeys),
      changedCacheKeys: [],
      before,
      after,
      result: captureResult && ok ? previewValue(value) : {{}}
    }};
  }};
  const before = snapshotRuntime();
  const resolved = resolvePath(loaderPathParts);
  if (!resolved.ok) return finish(false, "loader_path_unavailable", undefined, resolved.error);
  const loader = resolved.value;
  if (typeof loader !== "function") return finish(false, "custom_loader_not_function", loader, "");
  try {{
    const result = loader.apply(null, loaderArguments);
    if (result && typeof result.then === "function") {{
      try {{
        return finish(true, "", await result, "");
      }} catch (error) {{
        return finish(false, "custom_loader_threw", undefined, describeError(error));
      }}
    }}
    return finish(true, "", result, "");
  }} catch (error) {{
    return finish(false, "custom_loader_threw", undefined, describeError(error));
  }}
}})()
"""


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
class ModuleFederationFactoryInvokeSpec:
    """Review-gated remote factory invocation request derived from a federation candidate."""

    candidate: dict[str, Any] = field(default_factory=dict)
    execute_factory: bool = False
    review_approved: bool = False
    share_scope_path: str = "window.__webpack_share_scopes__.default"
    max_preview_length: int = 240
    export_preview_limit: int = 30

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationFactoryInvokeSpec | None":
        context = context or {}
        execute_factory = bool(
            context.get("execute_module_federation_factory")
            or context.get("executeModuleFederationFactory")
            or context.get("invoke_module_federation_factory")
            or context.get("invokeModuleFederationFactory")
            or context.get("execute_remote_factory")
            or context.get("executeRemoteFactory")
            or context.get("invoke_remote_factory")
            or context.get("invokeRemoteFactory")
        )
        plan_spec = ModuleFederationGetInitPlanSpec.from_context(context)
        if plan_spec is None and not execute_factory:
            return None
        candidate = plan_spec.candidates[0] if plan_spec and plan_spec.candidates else {}
        return cls(
            candidate=dict(candidate),
            execute_factory=execute_factory,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))),
            share_scope_path=str(context.get("share_scope_path", context.get("shareScopePath", "window.__webpack_share_scopes__.default")) or "window.__webpack_share_scopes__.default"),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            export_preview_limit=max(1, int(context.get("export_preview_limit", context.get("exportPreviewLimit", 30)) or 30)),
        )

    def to_probe_spec(self) -> ModuleFederationGetInitProbeSpec:
        return ModuleFederationGetInitProbeSpec(
            candidate=dict(self.candidate),
            execute_get_init=self.execute_factory,
            review_approved=self.review_approved,
            share_scope_path=self.share_scope_path,
            max_preview_length=self.max_preview_length,
        )


@dataclass(slots=True)
class ModuleFederationFactoryInvokeResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    get_init_execution: dict[str, Any] = field(default_factory=dict)
    factory_execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "get_init_execution": self.get_init_execution,
            "factory_execution": self.factory_execution,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class ModuleFederationFactoryInvokeManager:
    """Explicitly invoke a reviewed Module Federation remote factory and summarize exports."""

    def plan_or_invoke(self, page: BrowserPage, spec: ModuleFederationFactoryInvokeSpec | None) -> ModuleFederationFactoryInvokeResult:
        if spec is None:
            return ModuleFederationFactoryInvokeResult(status="unsupported", reason="missing_module_federation_factory_request")
        probe_result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec.to_probe_spec())
        if not spec.execute_factory:
            return ModuleFederationFactoryInvokeResult(
                status="planned",
                plan=probe_result.plan,
                get_init_execution=probe_result.execution,
                factory_execution={"attempted": False, "reason": "execute_module_federation_factory_not_requested"},
                side_effect_policy=probe_result.side_effect_policy,
            )
        if probe_result.status != "success":
            return ModuleFederationFactoryInvokeResult(
                status=probe_result.status,
                plan=probe_result.plan,
                get_init_execution=probe_result.execution,
                factory_execution={"attempted": False, "reason": probe_result.reason or probe_result.error or "get_init_probe_not_successful"},
                side_effect_policy=probe_result.side_effect_policy,
                error=probe_result.error,
                reason=probe_result.reason,
            )
        candidates = probe_result.plan.get("candidates") if isinstance(probe_result.plan.get("candidates"), list) else []
        candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        readiness_error = self._execution_readiness_error(candidate, spec, probe_result.execution)
        if readiness_error:
            return ModuleFederationFactoryInvokeResult(
                status="blocked",
                plan=probe_result.plan,
                get_init_execution=probe_result.execution,
                factory_execution={"attempted": False, "reason": readiness_error},
                side_effect_policy=probe_result.side_effect_policy,
                reason=readiness_error,
            )
        try:
            payload = page.evaluate(self._factory_expression(candidate, spec))
        except Exception as exc:
            return ModuleFederationFactoryInvokeResult(
                status="failed",
                plan=probe_result.plan,
                get_init_execution=probe_result.execution,
                factory_execution={"attempted": True, "ok": False, "error": str(exc)},
                side_effect_policy=self._executed_side_effect_policy(),
                error=str(exc),
            )
        factory_execution = payload if isinstance(payload, dict) else {"attempted": True, "ok": False, "result": payload}
        status = "success" if factory_execution.get("ok") else "failed"
        return ModuleFederationFactoryInvokeResult(
            status=status,
            plan=probe_result.plan,
            get_init_execution=probe_result.execution,
            factory_execution=factory_execution,
            side_effect_policy=self._executed_side_effect_policy(),
        )

    @staticmethod
    def _execution_readiness_error(candidate: dict[str, Any], spec: ModuleFederationFactoryInvokeSpec, get_init_execution: dict[str, Any]) -> str | None:
        if not spec.review_approved:
            return "review_approval_required"
        if not candidate:
            return "no_module_federation_candidate"
        if candidate.get("function_path_candidate_available"):
            return "prefer_existing_function_path_candidate"
        if not get_init_execution.get("remoteGetCalled"):
            return "remote_get_not_called"
        if get_init_execution.get("remoteFactoryInvoked"):
            return "factory_already_invoked_by_probe_unexpected"
        if not JS_DOTTED_PATH_RE.fullmatch(str(candidate.get("container_path") or "")):
            return "strict_dotted_container_path_required"
        if not str(candidate.get("exposed_name") or ""):
            return "exposed_module_name_required"
        if not JS_DOTTED_PATH_RE.fullmatch(spec.share_scope_path):
            return "strict_dotted_share_scope_path_required"
        return None

    @staticmethod
    def _executed_side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only_by_default": False,
            "requires_execute_module_federation_factory": True,
            "requires_review_approval": True,
            "container_init_executed": True,
            "remote_get_called": True,
            "remote_factory_invoked": True,
            "remote_code_executed": True,
            "shared_scope_may_mutate": True,
            "network_request_may_be_sent": True,
            "browser_state_mutated": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _factory_expression(cls, candidate: dict[str, Any], spec: ModuleFederationFactoryInvokeSpec) -> str:
        container_path = json.dumps(str(candidate.get("container_path") or ""), ensure_ascii=False)
        exposed_name = json.dumps(str(candidate.get("exposed_name") or ""), ensure_ascii=False)
        share_scope_path = json.dumps(spec.share_scope_path, ensure_ascii=False)
        container_parts = json.dumps(ModuleFederationGetInitProbeManager._path_parts(str(candidate.get("container_path") or "")), ensure_ascii=False)
        share_scope_parts = json.dumps(ModuleFederationGetInitProbeManager._path_parts(spec.share_scope_path), ensure_ascii=False)
        max_preview_length = max(1, int(spec.max_preview_length))
        export_preview_limit = max(1, int(spec.export_preview_limit))
        return f"""
(async () => {{
  const marker = "__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__";
  const containerPath = {container_path};
  const exposedName = {exposed_name};
  const shareScopePath = {share_scope_path};
  const containerParts = {container_parts};
  const shareScopeParts = {share_scope_parts};
  const maxPreviewLength = {max_preview_length};
  const exportPreviewLimit = {export_preview_limit};
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
  const keys = (value) => value && (typeof value === "object" || typeof value === "function") ? Object.keys(value).map(String).sort() : [];
  const diffKeys = (before, after) => after.filter((item) => !before.includes(item));
  const previewValue = (value) => {{
    const type = typeof value;
    if (value === null) return {{ type: "null", preview: "null" }};
    if (type === "string" || type === "number" || type === "boolean" || type === "undefined" || type === "bigint") {{
      return {{ type, preview: String(value).slice(0, maxPreviewLength) }};
    }}
    if (type === "function") {{
      return {{ type, name: String(value.name || ""), preview: String(value).slice(0, maxPreviewLength) }};
    }}
    return {{ type, constructorName: value && value.constructor && value.constructor.name || "", keys: keys(value).slice(0, exportPreviewLimit) }};
  }};
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
  let remoteFactoryInvoked = false;
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
    const factoryType = typeof factory;
    if (factoryType !== "function") {{
      return {{
        marker,
        attempted: true,
        ok: false,
        status: "failed",
        reason: "remote_factory_not_function",
        containerPath,
        exposedName,
        containerInitCalled,
        remoteGetCalled,
        remoteFactoryInvoked: false,
        factoryType,
        beforeSharedScopeKeys,
        afterSharedScopeKeys: keys(shareScope),
        addedSharedScopeKeys: diffKeys(beforeSharedScopeKeys, keys(shareScope)),
        beforeContainerKeys,
        afterContainerKeys: keys(container)
      }};
    }}
    remoteFactoryInvoked = true;
    const moduleValue = factory();
    const moduleType = moduleValue === null ? "null" : typeof moduleValue;
    const exportNames = keys(moduleValue).slice(0, exportPreviewLimit);
    const exportPreviews = {{}};
    for (const name of exportNames) {{
      try {{
        exportPreviews[name] = previewValue(moduleValue[name]);
      }} catch (error) {{
        exportPreviews[name] = {{ type: "error", preview: describeError(error) }};
      }}
    }}
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
      remoteFactoryInvoked,
      remoteCodeExecuted: true,
      factoryType,
      moduleType,
      exportNames,
      exportCount: exportNames.length,
      exportPreviews,
      beforeSharedScopeKeys,
      afterSharedScopeKeys,
      addedSharedScopeKeys: diffKeys(beforeSharedScopeKeys, afterSharedScopeKeys),
      beforeContainerKeys,
      afterContainerKeys,
      addedContainerKeys: diffKeys(beforeContainerKeys, afterContainerKeys)
    }};
  }} catch (error) {{
    return {{
      marker,
      attempted: true,
      ok: false,
      status: "failed",
      reason: "module_federation_factory_invoke_error",
      containerPath,
      exposedName,
      containerInitCalled,
      remoteGetCalled,
      remoteFactoryInvoked,
      remoteCodeExecuted: remoteFactoryInvoked,
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
class ModuleFederationExportHookPlanSpec:
    """Review-only hook selection request derived from a remote factory invocation result."""

    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    max_candidates: int = 30

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationExportHookPlanSpec | None":
        context = context or {}
        payload = (
            context.get("module_federation_factory_invoke_result")
            or context.get("module-federation-factory-invoke-result")
            or context.get("moduleFederationFactoryInvokeResult")
            or context.get("factory_invoke_result")
            or context.get("factoryInvokeResult")
        )
        if not isinstance(payload, dict):
            return None
        return cls(
            factory_invoke_result=dict(payload),
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 30)) or 30)),
        )


@dataclass(slots=True)
class ModuleFederationExportHookPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ModuleFederationExportHookPlanManager:
    """Build a review-only hook recommendation plan for reviewed remote exports."""

    def plan(self, spec: ModuleFederationExportHookPlanSpec | None) -> ModuleFederationExportHookPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return ModuleFederationExportHookPlanResult(status="unsupported", reason="missing_factory_invoke_result", side_effect_policy=policy)
        factory_execution = self._factory_execution(spec.factory_invoke_result)
        if not factory_execution:
            return ModuleFederationExportHookPlanResult(status="blocked", reason="missing_factory_execution", side_effect_policy=policy)
        if not factory_execution.get("remoteFactoryInvoked") or not factory_execution.get("remoteCodeExecuted"):
            return ModuleFederationExportHookPlanResult(status="blocked", reason="remote_factory_execution_required", side_effect_policy=policy)
        export_names = [str(item) for item in factory_execution.get("exportNames") or [] if str(item)]
        export_previews = factory_execution.get("exportPreviews") if isinstance(factory_execution.get("exportPreviews"), dict) else {}
        candidates = [
            self._candidate_for_export(factory_execution, export_name, export_previews.get(export_name) if isinstance(export_previews.get(export_name), dict) else {})
            for export_name in export_names[: spec.max_candidates]
        ]
        hookable_count = sum(1 for candidate in candidates if candidate.get("hookable"))
        plan = {
            "schema_version": "reverse-deepagent.module-federation-export-hook-plan.v1",
            "status": "ready_for_review" if hookable_count else "blocked",
            "source": "module_federation_factory_invoke_result",
            "container_path": factory_execution.get("containerPath", ""),
            "exposed_name": factory_execution.get("exposedName", ""),
            "module_type": factory_execution.get("moduleType", ""),
            "export_count": len(export_names),
            "candidate_count": len(candidates),
            "hookable_candidate_count": hookable_count,
            "candidates": candidates,
            "review_required": True,
            "automatic_hook_installation": False,
            "recursive_federation_traversal": False,
            "next_action": "review_module_federation_export_hook_plan" if hookable_count else "inspect_remote_export_shapes_before_hooking",
        }
        return ModuleFederationExportHookPlanResult(
            status="planned" if hookable_count else "blocked",
            plan=plan,
            side_effect_policy=policy,
            reason=None if hookable_count else "no_hookable_remote_exports",
        )

    @staticmethod
    def _factory_execution(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("factory_execution"), dict):
            return payload["factory_execution"]
        if isinstance(payload.get("factoryExecution"), dict):
            return payload["factoryExecution"]
        if payload.get("remoteFactoryInvoked") is not None or payload.get("exportNames") is not None:
            return payload
        return {}

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "installs_hooks": False,
            "invokes_remote_factory": False,
            "executes_remote_code": False,
            "recursive_federation_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _candidate_for_export(cls, execution: dict[str, Any], export_name: str, preview: dict[str, Any]) -> dict[str, Any]:
        export_type = str(preview.get("type") or "unknown")
        container_path = str(execution.get("containerPath") or "")
        exposed_name = str(execution.get("exposedName") or "")
        hook_kind = "remote-export-wrapper" if export_type == "function" else "manual-inspection"
        hookable = export_type == "function"
        blocking_reasons = [] if hookable else [f"unsupported_remote_export_type:{export_type}"]
        return {
            "kind": "module-federation-remote-export",
            "export_name": export_name,
            "export_type": export_type,
            "function_name": str(preview.get("name") or export_name),
            "container_path": container_path,
            "exposed_name": exposed_name,
            "hook_kind": hook_kind,
            "hookable": hookable,
            "recommended_follow_up": "hook_module_federation_remote_export" if hookable else "inspect_remote_export_shape",
            "requires_review_approval": True,
            "automatic_hook_installation": False,
            "recursive_federation_traversal": False,
            "blocking_reasons": blocking_reasons,
            "preview": {key: preview[key] for key in ("type", "name", "constructorName", "keys", "preview") if key in preview},
        }


@dataclass(slots=True)
class ModuleFederationExportHookInstallSpec:
    """Review-approved remote export hook install request from an export hook plan."""

    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    candidate_index: int | None = None
    share_scope_path: str = "window.__webpack_share_scopes__.default"
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationExportHookInstallSpec | None":
        context = context or {}
        plan = (
            context.get("module_federation_export_hook_plan")
            or context.get("module-federation-export-hook-plan")
            or context.get("moduleFederationExportHookPlan")
            or context.get("remote_export_hook_plan")
            or context.get("remoteExportHookPlan")
        )
        if not isinstance(plan, dict):
            return None
        index_value = context.get("candidate_index", context.get("candidateIndex"))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        selected = (
            context.get("selected_export_hook_candidate")
            or context.get("selectedExportHookCandidate")
            or context.get("selected_hook_candidate")
            or context.get("selectedHookCandidate")
            or context.get("hook_candidate")
            or context.get("hookCandidate")
        )
        return cls(
            export_hook_plan=dict(plan),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            candidate_index=candidate_index,
            share_scope_path=str(context.get("share_scope_path", context.get("shareScopePath", "window.__webpack_share_scopes__.default")) or "window.__webpack_share_scopes__.default").strip(),
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )


@dataclass(slots=True)
class ModuleFederationExportHookInstallResult:
    status: str
    installed: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

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
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "error": self.error,
            "reason": self.reason,
        }


class ModuleFederationExportHookInstallManager:
    """Install reviewed wrappers around function exports returned by Module Federation remotes."""

    def install(self, page: BrowserPage, spec: ModuleFederationExportHookInstallSpec | None) -> ModuleFederationExportHookInstallResult:
        policy = self._side_effect_policy(review_approved=bool(spec and spec.review_approved))
        if spec is None:
            return ModuleFederationExportHookInstallResult(status="unsupported", reason="missing_module_federation_export_hook_plan", side_effect_policy=policy)
        candidate = self._select_candidate(spec)
        if not candidate:
            return ModuleFederationExportHookInstallResult(status="blocked", reason="review_module_federation_export_hook_plan", side_effect_policy=policy)
        if not spec.review_approved:
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="review_approval_required", side_effect_policy=policy)
        if str(candidate.get("kind") or "") != "module-federation-remote-export":
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="candidate_not_module_federation_remote_export", side_effect_policy=policy)
        if str(candidate.get("hook_kind") or candidate.get("hookKind") or "") != "remote-export-wrapper":
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="unsupported_remote_export_hook_kind", side_effect_policy=policy)
        if not bool(candidate.get("hookable", False)):
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="remote_export_candidate_not_hookable", side_effect_policy=policy)
        if not JS_DOTTED_PATH_RE.fullmatch(str(candidate.get("container_path") or candidate.get("containerPath") or "")):
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="strict_dotted_container_path_required", side_effect_policy=policy)
        if not JS_DOTTED_PATH_RE.fullmatch(spec.share_scope_path):
            return ModuleFederationExportHookInstallResult(status="blocked", selected_candidate=candidate, reason="strict_dotted_share_scope_path_required", side_effect_policy=policy)
        try:
            install_payload = page.evaluate(self._install_expression(candidate, spec))
        except Exception as exc:
            return ModuleFederationExportHookInstallResult(status="failed", selected_candidate=candidate, side_effect_policy=policy, error=str(exc))
        trigger = self._run_trigger(page, spec)
        try:
            snapshot_payload = page.evaluate(self._snapshot_expression(candidate))
        except Exception as exc:
            snapshot_payload = {"ok": False, "events": [], "error": str(exc)}
        installed = self._list_of_dicts(install_payload.get("installed") if isinstance(install_payload, dict) else [])
        missing = self._list_of_dicts(install_payload.get("missing") if isinstance(install_payload, dict) else [])
        events = self._list_of_dicts(snapshot_payload.get("events") if isinstance(snapshot_payload, dict) else [])
        status = "success" if installed else "partial" if missing else "failed"
        return ModuleFederationExportHookInstallResult(
            status=status,
            installed=installed,
            missing=missing,
            events=events,
            trigger=trigger,
            selected_candidate=candidate,
            side_effect_policy=policy,
            error=install_payload.get("error") if isinstance(install_payload, dict) else None,
        )

    @staticmethod
    def _run_trigger(page: BrowserPage, spec: ModuleFederationExportHookInstallSpec) -> dict[str, Any]:
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

    @classmethod
    def _select_candidate(cls, spec: ModuleFederationExportHookInstallSpec) -> dict[str, Any]:
        candidates = cls._candidates(spec.export_hook_plan)
        if spec.candidate_index is not None and 0 <= spec.candidate_index < len(candidates):
            return dict(candidates[spec.candidate_index])
        if spec.selected_candidate:
            selected_export = str(spec.selected_candidate.get("export_name") or spec.selected_candidate.get("exportName") or "")
            selected_container = str(spec.selected_candidate.get("container_path") or spec.selected_candidate.get("containerPath") or "")
            selected_exposed = str(spec.selected_candidate.get("exposed_name") or spec.selected_candidate.get("exposedName") or "")
            for candidate in candidates:
                export_name = str(candidate.get("export_name") or candidate.get("exportName") or "")
                container_path = str(candidate.get("container_path") or candidate.get("containerPath") or "")
                exposed_name = str(candidate.get("exposed_name") or candidate.get("exposedName") or "")
                if selected_export and export_name == selected_export and (not selected_container or selected_container == container_path) and (not selected_exposed or selected_exposed == exposed_name):
                    return dict(candidate)
            merged = dict(spec.selected_candidate)
            merged.setdefault("kind", "selected_remote_export_candidate")
            return merged
        if len(candidates) == 1:
            return dict(candidates[0])
        return {}

    @staticmethod
    def _candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("plan"), dict):
            payload = payload["plan"]
        value = payload.get("candidates") or []
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _side_effect_policy(*, review_approved: bool) -> dict[str, Any]:
        return {
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": review_approved,
            "container_init_executed": review_approved,
            "remote_get_called": review_approved,
            "remote_factory_invoked": review_approved,
            "remote_code_executed": review_approved,
            "installs_hooks": review_approved,
            "automatic_hook_installation": False,
            "recursive_federation_traversal": False,
            "shared_scope_may_mutate": review_approved,
            "network_request_may_be_sent": review_approved,
            "browser_state_mutated": review_approved,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _install_expression(candidate: dict[str, Any], spec: ModuleFederationExportHookInstallSpec) -> str:
        config = {
            "containerPath": candidate.get("container_path") or candidate.get("containerPath"),
            "exposedName": candidate.get("exposed_name") or candidate.get("exposedName"),
            "exportName": candidate.get("export_name") or candidate.get("exportName"),
            "functionName": candidate.get("function_name") or candidate.get("functionName") or candidate.get("export_name") or candidate.get("exportName"),
            "shareScopePath": spec.share_scope_path,
            "containerParts": ModuleFederationGetInitProbeManager._path_parts(str(candidate.get("container_path") or candidate.get("containerPath") or "")),
            "shareScopeParts": ModuleFederationGetInitProbeManager._path_parts(spec.share_scope_path),
            "captureArgs": spec.capture_args,
            "captureResult": spec.capture_result,
            "maxPreviewLength": spec.max_preview_length,
        }
        config_json = json.dumps(config, ensure_ascii=False)
        return """
(async () => {
  const config = __REVERSE_AGENT_REMOTE_EXPORT_HOOK_CONFIG__;
  const root = window.__reverseDeepAgentHooks = window.__reverseDeepAgentHooks || { installedAt: Date.now(), events: [], installed: {}, push(type, payload) { try { this.events.push({ type, ts: Date.now(), payload }); if (this.events.length > 300) this.events.shift(); } catch (_) {} } };
  root.installed.remote_export_hooks = root.installed.remote_export_hooks || {};
  const hookPath = `${config.containerPath}:${config.exposedName}:${config.exportName}`;
  const preview = (value) => { try { if (value === undefined) return { type: 'undefined', preview: 'undefined' }; if (value === null) return { type: 'null', preview: 'null' }; if (typeof value === 'string') return { type: 'string', size: value.length, preview: value.slice(0, config.maxPreviewLength) }; if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return { type: typeof value, preview: String(value) }; if (typeof value === 'function') return { type: 'function', name: value.name || '', preview: '<function>' }; const text = JSON.stringify(value); return { type: Array.isArray(value) ? 'array' : typeof value, size: text ? text.length : 0, preview: String(text || value).slice(0, config.maxPreviewLength) }; } catch (_) { return { type: typeof value, preview: '<unavailable>' }; } };
  const resolvePath = (parts) => { let value = window; for (const part of parts || []) { if (!part || !/^[A-Za-z_$][\w$]*$/.test(part)) return { ok: false, error: 'unsafe_path_segment' }; value = value && value[part]; } return { ok: true, value }; };
  const installed = [];
  const missing = [];
  try {
    const containerResolved = resolvePath(config.containerParts);
    if (!containerResolved.ok || !containerResolved.value) { missing.push({ hookPath, reason: 'container_unavailable', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName }); return { ok: false, installed, missing, eventCount: root.events.length }; }
    const container = containerResolved.value;
    const shareScopeResolved = resolvePath(config.shareScopeParts);
    const shareScope = shareScopeResolved.ok && shareScopeResolved.value && typeof shareScopeResolved.value === 'object' ? shareScopeResolved.value : {};
    if (typeof container.init === 'function') await container.init(shareScope);
    if (typeof container.get !== 'function') { missing.push({ hookPath, reason: 'container_get_missing', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName }); return { ok: false, installed, missing, eventCount: root.events.length }; }
    const factory = await container.get(config.exposedName);
    if (typeof factory !== 'function') { missing.push({ hookPath, reason: 'remote_factory_not_function', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName }); return { ok: false, installed, missing, eventCount: root.events.length }; }
    const moduleExports = factory();
    if (!moduleExports || (typeof moduleExports !== 'object' && typeof moduleExports !== 'function')) { missing.push({ hookPath, reason: 'module_exports_unavailable', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName }); return { ok: false, installed, missing, eventCount: root.events.length }; }
    const original = moduleExports[config.exportName];
    if (typeof original !== 'function') { missing.push({ hookPath, reason: 'remote_export_function_not_found', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName }); return { ok: false, installed, missing, eventCount: root.events.length }; }
    if (original.__reverseAgentRemoteExportHooked) { installed.push({ hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, alreadyInstalled: true }); return { ok: true, installed, missing, eventCount: root.events.length }; }
    const wrapped = function reverseAgentRemoteExportHookWrapper(...args) {
      const callId = `${hookPath}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
      root.push('remote_export_call', { callId, hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, functionName: config.functionName || config.exportName, argCount: args.length, args: config.captureArgs ? args.map(preview) : [] });
      try {
        const result = original.apply(this, args);
        const recordReturn = (value) => { root.push('remote_export_return', { callId, hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, functionName: config.functionName || config.exportName, result: config.captureResult ? preview(value) : { preview: '<disabled>' } }); return value; };
        if (result && typeof result.then === 'function') return result.then(recordReturn, (error) => { root.push('remote_export_throw', { callId, hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, error: String(error && error.message || error) }); throw error; });
        return recordReturn(result);
      } catch (error) { root.push('remote_export_throw', { callId, hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, error: String(error && error.message || error) }); throw error; }
    };
    try { Object.defineProperty(wrapped, 'name', { value: original.name || config.functionName || 'reverseAgentRemoteExportHookWrapper' }); } catch (_) {}
    wrapped.__reverseAgentOriginal = original;
    wrapped.__reverseAgentRemoteExportHooked = true;
    moduleExports[config.exportName] = wrapped;
    root.installed.remote_export_hooks[hookPath] = true;
    installed.push({ hookPath, containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, functionName: config.functionName || config.exportName });
  } catch (error) {
    missing.push({ hookPath, reason: 'install_error', containerPath: config.containerPath, exposedName: config.exposedName, exportName: config.exportName, error: String(error && error.message || error) });
  }
  return { ok: installed.length > 0, installed, missing, eventCount: root.events.length };
})()
""".replace("__REVERSE_AGENT_REMOTE_EXPORT_HOOK_CONFIG__", config_json)

    @staticmethod
    def _snapshot_expression(candidate: dict[str, Any]) -> str:
        hook_path = f"{candidate.get('container_path') or candidate.get('containerPath')}:{candidate.get('exposed_name') or candidate.get('exposedName')}:{candidate.get('export_name') or candidate.get('exportName')}"
        hook_json = json.dumps(hook_path, ensure_ascii=False)
        return """
(() => {
  const root = window.__reverseDeepAgentHooks;
  if (!root) return { ok: false, events: [], eventCount: 0, reason: 'not_installed' };
  const hookPath = __REVERSE_AGENT_REMOTE_EXPORT_HOOK_PATH__;
  const events = (root.events || []).filter((event) => event && event.payload && event.payload.hookPath === hookPath && /^remote_export_/.test(event.type));
  return { ok: true, events, eventCount: events.length, installed: Object.assign({}, (root.installed && root.installed.remote_export_hooks) || {}) };
})()
""".replace("__REVERSE_AGENT_REMOTE_EXPORT_HOOK_PATH__", hook_json)


@dataclass(slots=True)
class AsyncChunkTraversalGraphSpec:
    """Review-only graph / queue planner for deeper webpack async-chunk traversal."""

    chunk_graph: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    previous_traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkTraversalGraphSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_traversal_graph")
            or context.get("asyncChunkTraversalGraph")
            or context.get("async-chunk-traversal-graph")
            or context.get("async_chunk_graph_queue")
            or context.get("asyncChunkGraphQueue")
            or context.get("plan_async_chunk_deep_traversal")
            or context.get("planAsyncChunkDeepTraversal")
        )
        chunk_graph = (
            context.get("chunk_graph")
            or context.get("chunkGraph")
            or context.get("async_chunk_graph")
            or context.get("asyncChunkGraph")
        )
        module_discovery = context.get("module_discovery") or context.get("moduleDiscovery")
        if not isinstance(chunk_graph, dict) and isinstance(module_discovery, dict):
            chunk_graph = module_discovery.get("chunk_graph") or module_discovery.get("chunkGraph")
        if isinstance(chunk_graph, dict) and isinstance(chunk_graph.get("chunk_graph"), dict):
            chunk_graph = chunk_graph["chunk_graph"]
        if not isinstance(chunk_graph, dict):
            return None if not requested else cls()
        return cls(
            chunk_graph=dict(chunk_graph),
            async_chunk_load_result=cls._object_alias(
                context,
                "async_chunk_load_result",
                "async-chunk-load-result",
                "asyncChunkLoadResult",
            ),
            async_chunk_module_diff=cls._object_alias(
                context,
                "async_chunk_module_diff",
                "async-chunk-module-diff",
                "asyncChunkModuleDiff",
            ),
            previous_traversal_graph=cls._object_alias(
                context,
                "previous_async_chunk_traversal_graph",
                "previousAsyncChunkTraversalGraph",
                "async_chunk_traversal_graph_previous",
                "asyncChunkTraversalGraphPrevious",
            ),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

    @staticmethod
    def _object_alias(context: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = context.get(key)
            if isinstance(value, dict):
                return dict(value)
        return {}


@dataclass(slots=True)
class AsyncChunkTraversalGraphResult:
    status: str
    graph: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "graph": self.graph,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class AsyncChunkTraversalGraphManager:
    """Build a review-only async chunk traversal graph and bounded queue."""

    SUPPORTED_LOADER_KINDS = {"webpack-runtime", "webpack-require"}
    DYNAMIC_IMPORT_KINDS = {"es-dynamic-import", "worker-importscripts", "import-meta-url"}

    def plan(self, spec: AsyncChunkTraversalGraphSpec | None) -> AsyncChunkTraversalGraphResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.chunk_graph:
            return AsyncChunkTraversalGraphResult(status="unsupported", reason="missing_async_chunk_graph", side_effect_policy=policy)
        candidates = self._candidate_records(spec.chunk_graph)
        loaded_chunks = self._loaded_chunk_ids(spec)
        nodes = [self._node(candidate, index=index, spec=spec, loaded_chunks=loaded_chunks) for index, candidate in enumerate(candidates)]
        edges = self._edges(nodes)
        queue = [node for node in nodes if node.get("queue_status") == "ready_for_review"][: spec.max_queue_size]
        loaded_count = sum(1 for node in nodes if node.get("already_loaded"))
        supported_count = sum(1 for node in nodes if node.get("execution_supported"))
        blocked_count = sum(1 for node in nodes if node.get("queue_status") == "blocked")
        redirect_count = sum(1 for node in nodes if node.get("queue_status") == "redirect_to_dedicated_gate")
        if queue:
            status = "ready_for_review"
            reason = None
        elif not candidates:
            status = "blocked"
            reason = "no_async_chunk_candidates"
        elif supported_count and loaded_count >= supported_count:
            status = "complete"
            reason = None
        else:
            status = "blocked"
            reason = "no_supported_unloaded_async_chunk_candidates"
        graph = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-graph.v1",
            "status": status,
            "reason": reason,
            "review_required": True,
            "graph_id": "async-chunk-traversal-graph",
            "source_chunk_graph_status": spec.chunk_graph.get("status", ""),
            "candidate_count": len(candidates),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "queue_count": len(queue),
            "loaded_chunk_count": loaded_count,
            "supported_candidate_count": supported_count,
            "blocked_count": blocked_count,
            "redirect_count": redirect_count,
            "nodes": nodes,
            "edges": edges,
            "review_queue": queue,
            "review_sequence": [
                "inspect_async_chunk_traversal_graph",
                "select_one_async_chunk_candidate",
                "plan_async_chunk_load",
                "execute_one_reviewed_async_chunk_load",
                "refresh_async_chunk_module_diff",
                "optionally_install_reviewed_async_chunk_module_hook",
                "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph",
                "stop_before_recursive_async_chunk_traversal",
            ],
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason, queue=queue),
        }
        return AsyncChunkTraversalGraphResult(status=status, graph=graph, side_effect_policy=policy, reason=reason)

    @classmethod
    def _candidate_records(cls, graph: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = graph.get("candidates")
        if isinstance(candidates, list):
            return [dict(item) for item in candidates if isinstance(item, dict)]
        return []

    @classmethod
    def _loaded_chunk_ids(cls, spec: AsyncChunkTraversalGraphSpec) -> set[str]:
        loaded: set[str] = set()
        for payload in (spec.async_chunk_load_result, spec.async_chunk_module_diff):
            nested = payload.get("execution") if isinstance(payload.get("execution"), dict) else payload
            for key in ("chunkId", "chunk_id", "chunk", "target"):
                value = nested.get(key)
                if value is not None and str(value).strip():
                    loaded.add(str(value).strip())
            for key in ("addedRegistryKeys", "added_registry_keys", "addedCacheKeys", "added_cache_keys"):
                values = nested.get(key)
                if isinstance(values, list):
                    loaded.update(str(item).strip() for item in values if str(item).strip())
        previous = spec.previous_traversal_graph.get("nodes")
        if isinstance(previous, list):
            for node in previous:
                if isinstance(node, dict) and node.get("already_loaded"):
                    value = node.get("chunk_id") or node.get("target")
                    if value is not None and str(value).strip():
                        loaded.add(str(value).strip())
        return loaded

    @classmethod
    def _node(cls, candidate: dict[str, Any], *, index: int, spec: AsyncChunkTraversalGraphSpec, loaded_chunks: set[str]) -> dict[str, Any]:
        chunk_id = str(candidate.get("chunk_id") or candidate.get("chunkId") or candidate.get("target") or "")[: spec.max_preview_length]
        target = str(candidate.get("target") or chunk_id)[: spec.max_preview_length]
        loader_kind = str(candidate.get("loader_kind") or candidate.get("loaderKind") or "webpack-runtime").strip()
        edge_type = str(candidate.get("edge_type") or candidate.get("edgeType") or "runtime-async-chunk").strip()
        runtime_path = str(candidate.get("runtime_path") or candidate.get("runtimePath") or "window.__webpack_require__")[: spec.max_preview_length]
        loader_path = str(candidate.get("loader_path") or candidate.get("loaderPath") or runtime_path)[: spec.max_preview_length]
        normalized_kind = loader_kind.lower()
        normalized_edge = edge_type.lower()
        execution_supported = normalized_kind in cls.SUPPORTED_LOADER_KINDS
        already_loaded = chunk_id in loaded_chunks or target in loaded_chunks
        if already_loaded:
            queue_status = "already_loaded"
        elif execution_supported:
            queue_status = "ready_for_review"
        elif normalized_kind in cls.DYNAMIC_IMPORT_KINDS or normalized_edge in {"dynamic-import", "worker-importscripts", "asset-url"}:
            queue_status = "redirect_to_dedicated_gate"
        else:
            queue_status = "blocked"
        blocking_reasons = cls._blocking_reasons(loader_kind=normalized_kind, edge_type=normalized_edge, execution_supported=execution_supported, queue_status=queue_status)
        return {
            "node_id": f"async-chunk-node-{index}",
            "candidate_index": candidate.get("index", index),
            "chunk_id": chunk_id,
            "target": target,
            "loader_kind": loader_kind,
            "edge_type": edge_type,
            "runtime_path": runtime_path,
            "loader_path": loader_path,
            "discovery_source": candidate.get("discovery_source", candidate.get("discoverySource", "")),
            "review_action": candidate.get("review_action", candidate.get("reviewAction", "review_async_chunk_before_loading")),
            "execution_supported": execution_supported,
            "queue_status": queue_status,
            "already_loaded": already_loaded,
            "blocking_reasons": blocking_reasons,
            "review_requirements": [
                "review_this_chunk_candidate_before_load",
                "execute_at_most_one_async_chunk_load",
                "inspect_module_registry_diff_after_reviewed_load",
                "stop_before_recursive_async_chunk_traversal",
            ],
            "automatic_execution": False,
        }

    @staticmethod
    def _blocking_reasons(*, loader_kind: str, edge_type: str, execution_supported: bool, queue_status: str) -> list[str]:
        if queue_status in {"ready_for_review", "already_loaded"}:
            return []
        if loader_kind in AsyncChunkTraversalGraphManager.DYNAMIC_IMPORT_KINDS or edge_type in {"dynamic-import", "worker-importscripts", "asset-url"}:
            return ["dynamic_import_requires_dedicated_gate"]
        if "federation" in loader_kind or "federation" in edge_type:
            return ["module_federation_requires_dedicated_gate"]
        if not execution_supported:
            return ["unsupported_loader_kind_for_async_chunk_traversal"]
        return []

    @staticmethod
    def _edges(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for node in nodes:
            runtime_path = str(node.get("runtime_path") or "")
            if runtime_path:
                edges.append(
                    {
                        "from": runtime_path,
                        "to": node["node_id"],
                        "edge_type": "runtime_loader_candidate",
                        "review_required": True,
                    }
                )
        return edges

    @staticmethod
    def _next_action(*, status: str, reason: str | None, queue: list[dict[str, Any]]) -> str:
        if status == "ready_for_review" and queue:
            return "review_async_chunk_traversal_graph_queue"
        if status == "complete":
            return "async_chunk_traversal_graph_complete_or_provide_new_candidates"
        if reason == "no_supported_unloaded_async_chunk_candidates":
            return "provide_supported_webpack_async_chunk_candidates_or_use_dedicated_gates"
        return "provide_async_chunk_graph_with_candidates"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "loader_invoked": False,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "module_factory_invoked": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "automatic_recursive_traversal": False,
            "automatic_queue_advance": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class AsyncChunkTraversalWorkflowPlanSpec:
    """Review-only multi-step workflow planner over an async chunk traversal queue."""

    traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_planned_steps: int = 3
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkTraversalWorkflowPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
            or context.get("async_chunk_deep_traversal_workflow")
            or context.get("asyncChunkDeepTraversalWorkflow")
            or context.get("plan_async_chunk_traversal_workflow")
            or context.get("planAsyncChunkTraversalWorkflow")
        )
        graph = (
            context.get("async_chunk_traversal_graph")
            or context.get("asyncChunkTraversalGraph")
            or context.get("async-chunk-traversal-graph")
            or context.get("traversal_graph")
            or context.get("traversalGraph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        if not isinstance(graph, dict):
            return None if not requested else cls()
        return cls(
            traversal_graph=dict(graph),
            max_planned_steps=max(1, int(context.get("max_planned_steps", context.get("maxPlannedSteps", 3)) or 3)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )


@dataclass(slots=True)
class AsyncChunkTraversalWorkflowPlanResult:
    status: str
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "workflow_plan": self.workflow_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class AsyncChunkTraversalWorkflowPlanManager:
    """Compose bounded review-only workflow steps from an async chunk traversal graph."""

    def plan(self, spec: AsyncChunkTraversalWorkflowPlanSpec | None) -> AsyncChunkTraversalWorkflowPlanResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.traversal_graph:
            return AsyncChunkTraversalWorkflowPlanResult(status="unsupported", reason="missing_async_chunk_traversal_graph", side_effect_policy=policy)
        graph = spec.traversal_graph
        graph_status = str(graph.get("status") or "").strip()
        queue = self._review_queue(graph)
        if graph_status == "complete":
            status = "complete"
            reason = None
            selected_queue: list[dict[str, Any]] = []
        elif not queue:
            status = "blocked"
            reason = self._blocked_reason(graph)
            selected_queue = []
        else:
            status = "ready_for_review"
            reason = None
            selected_queue = queue[: spec.max_planned_steps]
        planned_steps = [self._planned_step(item, step_index=index, spec=spec) for index, item in enumerate(selected_queue)]
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "async-chunk-traversal-workflow-plan",
            "review_required": True,
            "manual_checkpoint_required": True,
            "execute_at_most_one_chunk_load_per_review": True,
            "source_graph_id": graph.get("graph_id", "async-chunk-traversal-graph"),
            "source_graph_status": graph_status,
            "source_graph_queue_count": int(graph.get("queue_count") or len(queue)),
            "source_graph_loaded_chunk_count": int(graph.get("loaded_chunk_count") or 0),
            "max_planned_steps": spec.max_planned_steps,
            "planned_step_count": len(planned_steps),
            "planned_steps": planned_steps,
            "workflow_sequence": self._workflow_sequence(),
            "blocking_reasons": [reason] if reason else [],
            "next_action": self._next_action(status=status, reason=reason),
            "side_effect_policy": policy,
        }
        return AsyncChunkTraversalWorkflowPlanResult(status=status, workflow_plan=workflow_plan, side_effect_policy=policy, reason=reason)

    @staticmethod
    def _review_queue(graph: dict[str, Any]) -> list[dict[str, Any]]:
        queue = graph.get("review_queue")
        if isinstance(queue, list):
            return [dict(item) for item in queue if isinstance(item, dict)]
        return []

    @staticmethod
    def _blocked_reason(graph: dict[str, Any]) -> str:
        graph_status = str(graph.get("status") or "").strip()
        if graph_status in {"blocked", "unsupported", "failed", "failure", "error"}:
            return "async_chunk_traversal_graph_blocked"
        return "no_async_chunk_traversal_queue"

    @classmethod
    def _planned_step(cls, queue_item: dict[str, Any], *, step_index: int, spec: AsyncChunkTraversalWorkflowPlanSpec) -> dict[str, Any]:
        chunk_id = str(queue_item.get("chunk_id") or queue_item.get("chunkId") or queue_item.get("target") or "")[: spec.max_preview_length]
        target = str(queue_item.get("target") or chunk_id)[: spec.max_preview_length]
        runtime_path = str(queue_item.get("runtime_path") or queue_item.get("runtimePath") or "window.__webpack_require__")[: spec.max_preview_length]
        return {
            "step_index": step_index,
            "step_id": f"async-chunk-traversal-step-{step_index}",
            "queue_node_id": queue_item.get("node_id"),
            "candidate_index": queue_item.get("candidate_index", queue_item.get("index", step_index)),
            "chunk_id": chunk_id,
            "target": target,
            "loader_kind": queue_item.get("loader_kind"),
            "edge_type": queue_item.get("edge_type"),
            "runtime_path": runtime_path,
            "queue_status": queue_item.get("queue_status"),
            "review_required": True,
            "manual_checkpoint_required": True,
            "automatic_execution": False,
            "execute_at_most_one_chunk_load_per_review": True,
            "references": {
                "traversal_graph_artifact": "workspace/async-chunk-traversal-graph.json",
                "async_chunk_load_plan_artifact": "workspace/async-chunk-load-plan.json",
                "async_chunk_load_result_artifact": "workspace/async-chunk-load-result.json",
                "module_diff_artifact": "workspace/async-chunk-module-diff.json",
                "module_hook_artifact": "workspace/module-hooks.json",
            },
            "review_sequence": cls._workflow_sequence(),
            "next_action": "review_async_chunk_traversal_workflow_step",
        }

    @staticmethod
    def _workflow_sequence() -> list[dict[str, Any]]:
        return [
            {
                "order": 1,
                "action": "select_one_async_chunk_review_queue_candidate",
                "input_artifact": "workspace/async-chunk-traversal-graph.json",
                "output_artifact": None,
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 2,
                "action": "plan_async_chunk_load",
                "input_artifact": "workspace/async-chunk-traversal-graph.json",
                "output_artifact": "workspace/async-chunk-load-plan.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 3,
                "action": "execute_one_reviewed_async_chunk_load",
                "input_artifact": "workspace/async-chunk-load-plan.json",
                "output_artifact": "workspace/async-chunk-load-result.json",
                "review_required": True,
                "executes_runtime": True,
                "requires_review_approved": True,
            },
            {
                "order": 4,
                "action": "run_async_chunk_module_diff_after_reviewed_load",
                "input_artifact": "workspace/async-chunk-load-result.json",
                "output_artifact": "workspace/async-chunk-module-diff.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 5,
                "action": "optionally_install_reviewed_async_chunk_module_hook",
                "input_artifact": "workspace/async-chunk-module-diff.json",
                "output_artifact": "workspace/module-hooks.json",
                "review_required": True,
                "executes_runtime": True,
                "requires_review_approved": True,
            },
            {
                "order": 6,
                "action": "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph",
                "input_artifact": "workspace/async-chunk-load-result.json",
                "output_artifact": "workspace/async-chunk-traversal-graph.json",
                "review_required": True,
                "executes_runtime": False,
            },
            {
                "order": 7,
                "action": "stop_before_recursive_async_chunk_traversal",
                "input_artifact": "workspace/async-chunk-traversal-graph.json",
                "output_artifact": None,
                "review_required": True,
                "executes_runtime": False,
            },
        ]

    @staticmethod
    def _next_action(*, status: str, reason: str | None) -> str:
        if status == "ready_for_review":
            return "review_async_chunk_traversal_workflow_plan"
        if status == "complete":
            return "async_chunk_traversal_graph_complete_or_provide_new_candidates"
        if reason == "async_chunk_traversal_graph_blocked":
            return "revise_async_chunk_traversal_graph_inputs"
        return "provide_async_chunk_traversal_graph_with_queue"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "execute_at_most_one_chunk_load_per_review": True,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "module_factory_invoked": False,
            "automatic_recursive_traversal": False,
            "automatic_queue_advance": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class AsyncChunkTraversalWorkflowExecutionSpec:
    """Review-gated executor over one selected async chunk traversal workflow step."""

    workflow_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    selected_step_index: int | None = None
    candidate_index: int | None = None
    plan_async_chunk_load: bool = False
    execute_async_chunk_load: bool = False
    run_module_diff: bool = False
    install_module_hook: bool = False
    review_approved: bool = False
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkTraversalWorkflowExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_traversal_workflow_execution")
            or context.get("asyncChunkTraversalWorkflowExecution")
            or context.get("async-chunk-traversal-workflow-execution")
            or context.get("execute_async_chunk_traversal_workflow")
            or context.get("executeAsyncChunkTraversalWorkflow")
        )
        workflow_plan = (
            context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(workflow_plan, dict):
            return None if not requested else cls()
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        return cls(
            workflow_plan=dict(workflow_plan),
            async_chunk_load_plan=cls._object_alias(context, "async_chunk_load_plan", "async-chunk-load-plan", "asyncChunkLoadPlan"),
            async_chunk_load_result=cls._object_alias(context, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult"),
            async_chunk_module_diff=cls._object_alias(context, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff"),
            module_hook_result=cls._object_alias(context, "async_chunk_module_hook_result", "async-chunk-module-hook-result", "asyncChunkModuleHookResult", "module_hooks", "module-hooks"),
            module_discovery=cls._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_step_index=cls._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=cls._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
            plan_async_chunk_load=bool(context.get("plan_async_chunk_load") or context.get("planAsyncChunkLoad") or context.get("plan_chunk_load") or context.get("planChunkLoad")),
            execute_async_chunk_load=bool(context.get("execute_async_chunk_load") or context.get("executeAsyncChunkLoad") or context.get("execute_chunk_load") or context.get("executeChunkLoad")),
            run_module_diff=bool(context.get("run_module_diff") or context.get("runModuleDiff") or context.get("refresh_module_diff") or context.get("refreshModuleDiff")),
            install_module_hook=bool(context.get("install_module_hook") or context.get("installModuleHook") or context.get("hook_async_chunk_module") or context.get("hookAsyncChunkModule")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )

    @staticmethod
    def _object_alias(context: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = context.get(key)
            if isinstance(value, dict):
                return dict(value)
        return {}

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


@dataclass(slots=True)
class AsyncChunkTraversalWorkflowExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class AsyncChunkTraversalWorkflowExecutionManager:
    """Execute at most one reviewed async chunk traversal workflow step."""

    def execute(self, page: BrowserPage, spec: AsyncChunkTraversalWorkflowExecutionSpec | None) -> AsyncChunkTraversalWorkflowExecutionResult:
        if spec is None or not spec.workflow_plan:
            return AsyncChunkTraversalWorkflowExecutionResult(status="unsupported", reason="missing_async_chunk_traversal_workflow_plan", side_effect_policy=self._side_effect_policy())
        selected_step = self._selected_step(spec)
        if not selected_step:
            execution = self._execution_payload(spec, {}, [], {}, {}, {}, {}, status="blocked", reason="missing_async_chunk_traversal_workflow_step")
            return AsyncChunkTraversalWorkflowExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_async_chunk_traversal_workflow_step")

        stages: list[dict[str, Any]] = [self._stage("select_async_chunk_traversal_workflow_step", "selected", "", side_effect=False)]
        async_chunk_load_plan = dict(spec.async_chunk_load_plan)
        async_chunk_load_payload = dict(spec.async_chunk_load_result)
        module_diff_payload = dict(spec.async_chunk_module_diff)
        module_hook_payload = dict(spec.module_hook_result)

        if spec.plan_async_chunk_load:
            load_result = AsyncChunkLoadManager().plan_or_execute(page, self._load_spec(spec, selected_step, execute=False))
            async_chunk_load_plan = load_result.plan
            stages.append(self._stage("plan_async_chunk_load", load_result.status, load_result.reason, side_effect=False))
        elif async_chunk_load_plan:
            stages.append(self._stage("plan_async_chunk_load", str(async_chunk_load_plan.get("status") or "observed"), "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("plan_async_chunk_load", "pending", "", side_effect=False))

        if spec.execute_async_chunk_load:
            load_result = AsyncChunkLoadManager().plan_or_execute(page, self._load_spec(spec, selected_step, execute=True))
            if not async_chunk_load_plan:
                async_chunk_load_plan = load_result.plan
            async_chunk_load_payload = load_result.to_dict()
            stages.append(self._stage("execute_one_reviewed_async_chunk_load", load_result.status, load_result.reason, side_effect=True))
        elif async_chunk_load_payload:
            stages.append(self._stage("execute_one_reviewed_async_chunk_load", str(async_chunk_load_payload.get("status") or "observed"), "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("execute_one_reviewed_async_chunk_load", "pending", "", side_effect=True))

        if spec.run_module_diff:
            if not async_chunk_load_payload:
                stages.append(self._stage("run_async_chunk_module_diff", "blocked", "async_chunk_load_result_required", side_effect=False))
            else:
                diff_result = AsyncChunkModuleDiffManager().plan(
                    AsyncChunkModuleDiffSpec(
                        async_chunk_load_result=async_chunk_load_payload,
                        module_discovery=spec.module_discovery,
                        modules=spec.modules,
                    )
                )
                module_diff_payload = diff_result.to_dict()
                stages.append(self._stage("run_async_chunk_module_diff", diff_result.status, diff_result.reason, side_effect=False))
        elif module_diff_payload:
            stages.append(self._stage("run_async_chunk_module_diff", str(module_diff_payload.get("status") or "observed"), "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("run_async_chunk_module_diff", "pending", "", side_effect=False))

        if spec.install_module_hook:
            if not module_diff_payload:
                stages.append(self._stage("install_reviewed_async_chunk_module_hook", "blocked", "async_chunk_module_diff_required", side_effect=True))
            else:
                hook_result = AsyncChunkModuleHookManager().install(
                    page,
                    AsyncChunkModuleHookSpec(
                        async_chunk_module_diff=module_diff_payload,
                        review_approved=spec.review_approved,
                        candidate_index=spec.candidate_index,
                        capture_args=spec.capture_args,
                        capture_result=spec.capture_result,
                        max_preview_length=spec.max_preview_length,
                        trigger_expression=spec.trigger_expression,
                    ),
                )
                module_hook_payload = hook_result.to_dict()
                stages.append(self._stage("install_reviewed_async_chunk_module_hook", hook_result.status, hook_result.reason, side_effect=True))
        elif module_hook_payload:
            stages.append(self._stage("install_reviewed_async_chunk_module_hook", str(module_hook_payload.get("status") or "observed"), "", side_effect=False, observed=True))
        else:
            stages.append(self._stage("install_reviewed_async_chunk_module_hook", "pending", "", side_effect=True))

        stages.append(self._stage("stop_before_recursive_async_chunk_traversal", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, async_chunk_load_payload, module_diff_payload, module_hook_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(
            spec,
            selected_step,
            stages,
            async_chunk_load_plan,
            async_chunk_load_payload,
            module_diff_payload,
            module_hook_payload,
            status=status,
            reason=reason,
        )
        return AsyncChunkTraversalWorkflowExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, load_result=async_chunk_load_payload, module_diff=module_diff_payload, module_hook=module_hook_payload), reason=reason)

    @staticmethod
    def _selected_step(spec: AsyncChunkTraversalWorkflowExecutionSpec) -> dict[str, Any]:
        steps = spec.workflow_plan.get("planned_steps") if isinstance(spec.workflow_plan.get("planned_steps"), list) else []
        normalized_steps = [dict(item) for item in steps if isinstance(item, dict)]
        if not normalized_steps:
            return {}
        selected_index = spec.selected_step_index if spec.selected_step_index is not None else 0
        for step in normalized_steps:
            try:
                if int(step.get("step_index", -1)) == selected_index:
                    return step
            except (TypeError, ValueError):
                continue
        if 0 <= selected_index < len(normalized_steps):
            return normalized_steps[selected_index]
        return {}

    @staticmethod
    def _candidate_index(spec: AsyncChunkTraversalWorkflowExecutionSpec, selected_step: dict[str, Any]) -> int | None:
        if spec.candidate_index is not None:
            return spec.candidate_index
        raw = selected_step.get("candidate_index", selected_step.get("index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _load_spec(cls, spec: AsyncChunkTraversalWorkflowExecutionSpec, selected_step: dict[str, Any], *, execute: bool) -> AsyncChunkLoadSpec | None:
        return AsyncChunkLoadSpec.from_context(
            {
                "chunk_candidate": selected_step,
                "chunk_id": selected_step.get("chunk_id") or selected_step.get("chunkId") or selected_step.get("target"),
                "chunk_target": selected_step.get("target"),
                "loader_kind": selected_step.get("loader_kind") or selected_step.get("loaderKind") or "webpack-runtime",
                "edge_type": selected_step.get("edge_type") or selected_step.get("edgeType") or "runtime-async-chunk",
                "runtime_path": selected_step.get("runtime_path") or selected_step.get("runtimePath") or "window.__webpack_require__",
                "loader_path": selected_step.get("loader_path") or selected_step.get("loaderPath"),
                "execute_chunk_load": execute,
                "review_approved": spec.review_approved,
                "max_preview_length": spec.max_preview_length,
            }
        )

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool, observed: bool = False) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect, "observed_input": observed}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], load_result: dict[str, Any], module_diff: dict[str, Any], module_hook: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "failure", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        hook_status = str(module_hook.get("status") or "")
        if hook_status in {"success", "partial"}:
            return "module_hook_recorded"
        nested_diff = module_diff.get("diff") if isinstance(module_diff.get("diff"), dict) else {}
        diff_status = str(module_diff.get("status") or nested_diff.get("status") or "")
        if diff_status in {"planned", "ready_for_review"}:
            return "module_diff_ready"
        nested_load_execution = load_result.get("execution") if isinstance(load_result.get("execution"), dict) else {}
        load_status = str(load_result.get("status") or nested_load_execution.get("status") or "")
        if load_status == "success":
            return "async_chunk_load_success"
        if load_status == "planned":
            return "async_chunk_load_planned"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for item in stages:
            if item["status"] in {"blocked", "failed", "failure", "error", "unsupported"} and item.get("reason"):
                return str(item["reason"])
        return None

    @classmethod
    def _execution_payload(
        cls,
        spec: AsyncChunkTraversalWorkflowExecutionSpec,
        selected_step: dict[str, Any],
        stages: list[dict[str, Any]],
        async_chunk_load_plan: dict[str, Any],
        async_chunk_load_result: dict[str, Any],
        async_chunk_module_diff: dict[str, Any],
        module_hook_result: dict[str, Any],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-execution.v1",
            "status": status,
            "reason": reason,
            "workflow_plan_id": spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.workflow_plan.get("source_graph_id"),
            "selected_step_index": selected_step.get("step_index"),
            "selected_candidate_index": cls._candidate_index(spec, selected_step),
            "selected_step": selected_step,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "execute_at_most_one_chunk_load_per_review": True,
            "stages": stages,
            "async_chunk_load_plan": async_chunk_load_plan,
            "async_chunk_load_result": async_chunk_load_result,
            "async_chunk_module_diff": async_chunk_module_diff,
            "module_hook_result": module_hook_result,
            "artifact_refs": {
                "workflow_plan": "workspace/async-chunk-traversal-workflow-plan.json",
                "async_chunk_load_plan": "workspace/async-chunk-load-plan.json" if async_chunk_load_plan else "",
                "async_chunk_load_result": "workspace/async-chunk-load-result.json" if async_chunk_load_result else "",
                "async_chunk_module_diff": "workspace/async-chunk-module-diff.json" if async_chunk_module_diff else "",
                "module_hooks": "workspace/module-hooks.json" if module_hook_result else "",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "async_chunk_load_planned":
            return "approve_execute_async_chunk_load_for_selected_traversal_step"
        if status == "async_chunk_load_success":
            return "run_async_chunk_module_diff_after_reviewed_load"
        if status == "module_diff_ready":
            return "review_async_chunk_module_diff_hook_candidates"
        if status == "module_hook_recorded":
            return "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph"
        if status == "blocked" and reason:
            return "resolve_async_chunk_traversal_workflow_execution_blockers"
        if status == "failed":
            return "inspect_async_chunk_traversal_workflow_execution_failure"
        return "review_async_chunk_traversal_workflow_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: AsyncChunkTraversalWorkflowExecutionSpec | None = None,
        load_result: dict[str, Any] | None = None,
        module_diff: dict[str, Any] | None = None,
        module_hook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        load_result = load_result or {}
        load_policy = load_result.get("side_effect_policy") if isinstance(load_result.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": True,
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "async_chunk_load_planned": bool(spec and spec.plan_async_chunk_load),
            "runtime_loader_executed": bool(load_policy.get("runtime_loader_executed")),
            "chunk_request_sent": bool(load_policy.get("chunk_request_sent")),
            "module_diff_executed": bool(spec and spec.run_module_diff and module_diff),
            "module_hook_installed": bool((module_hook or {}).get("module_hook_result")),
            "module_factory_invoked": False,
            "automatic_recursive_traversal": False,
            "automatic_queue_advance": False,
            "traversal_graph_rebuilt": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "execute_at_most_one_chunk_load_per_review": True,
        }


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


@dataclass(slots=True)
class AsyncChunkModuleDiffSpec:
    """Review-only module diff and hook candidate refresh after a reviewed async chunk load."""

    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    max_candidates: int = 30

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkModuleDiffSpec | None":
        context = context or {}
        load_result = (
            context.get("async_chunk_load_result")
            or context.get("async-chunk-load-result")
            or context.get("asyncChunkLoadResult")
        )
        discovery = (
            context.get("module_discovery")
            or context.get("moduleDiscovery")
            or context.get("module_registry")
            or context.get("moduleRegistry")
        )
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        if not isinstance(load_result, dict):
            return None
        return cls(
            async_chunk_load_result=dict(load_result),
            module_discovery=dict(discovery) if isinstance(discovery, dict) else {},
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 30)) or 30)),
        )


@dataclass(slots=True)
class AsyncChunkModuleDiffResult:
    status: str
    diff: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "diff": self.diff,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class AsyncChunkModuleDiffManager:
    """Build a side-effect-free module diff and hook candidate refresh after chunk load."""

    def plan(self, spec: AsyncChunkModuleDiffSpec | None) -> AsyncChunkModuleDiffResult:
        policy = self._side_effect_policy()
        if spec is None:
            return AsyncChunkModuleDiffResult(status="unsupported", reason="missing_async_chunk_load_result", side_effect_policy=policy)
        execution = self._execution_payload(spec.async_chunk_load_result)
        if not execution.get("attempted") or not execution.get("ok"):
            return AsyncChunkModuleDiffResult(status="blocked", reason="successful_async_chunk_load_required", side_effect_policy=policy)
        added_registry_keys = [str(item) for item in execution.get("addedRegistryKeys") or execution.get("added_registry_keys") or [] if str(item)]
        added_cache_keys = [str(item) for item in execution.get("addedCacheKeys") or execution.get("added_cache_keys") or [] if str(item)]
        modules = self._module_records(spec)
        matched_modules = [module for module in modules if str(module.get("module_id") or module.get("moduleId") or "") in set(added_registry_keys + added_cache_keys)]
        candidates = self._hook_candidates(matched_modules, max_candidates=spec.max_candidates)
        status = "planned" if candidates or matched_modules or added_registry_keys or added_cache_keys else "blocked"
        diff = {
            "schema_version": "reverse-deepagent.async-chunk-module-diff.v1",
            "status": "ready_for_review" if status == "planned" else "blocked",
            "source": "async_chunk_load_result",
            "chunk_id": execution.get("chunkId") or execution.get("chunk_id") or spec.async_chunk_load_result.get("chunk_id", ""),
            "runtime_path": execution.get("runtimePath") or execution.get("runtime_path") or "",
            "added_registry_keys": added_registry_keys,
            "added_cache_keys": added_cache_keys,
            "matched_module_count": len(matched_modules),
            "candidate_count": len(candidates),
            "matched_modules": matched_modules[: spec.max_candidates],
            "hook_candidates": candidates,
            "review_required": True,
            "automatic_hook_installation": False,
            "module_factory_invoked": False,
            "next_action": "review_async_chunk_module_diff_hook_candidates" if candidates else "rerun_module_discovery_after_chunk_load",
        }
        return AsyncChunkModuleDiffResult(
            status=status,
            diff=diff,
            side_effect_policy=policy,
            reason=None if status == "planned" else "no_added_module_diff_or_candidates",
        )

    @staticmethod
    def _execution_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("execution"), dict):
            return payload["execution"]
        return payload

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "loads_chunk": False,
            "installs_hooks": False,
            "evaluates_javascript": False,
            "module_factory_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _module_records(cls, spec: AsyncChunkModuleDiffSpec) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        records.extend(spec.modules)
        discovery = spec.module_discovery
        for key in ("modules", "module_candidates", "moduleCandidates", "candidates"):
            value = discovery.get(key)
            if isinstance(value, list):
                records.extend(dict(item) for item in value if isinstance(item, dict))
        runtime = discovery.get("runtime")
        if isinstance(runtime, dict) and isinstance(runtime.get("modules"), list):
            records.extend(dict(item) for item in runtime["modules"] if isinstance(item, dict))
        return cls._dedupe_records(records)

    @staticmethod
    def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        result: list[dict[str, Any]] = []
        for record in records:
            module_id = str(record.get("module_id") or record.get("moduleId") or "")
            runtime_path = str(record.get("runtime_path") or record.get("runtimePath") or "")
            key = (runtime_path, module_id)
            if key in seen:
                continue
            seen.add(key)
            normalized = dict(record)
            if module_id:
                normalized["module_id"] = module_id
            if runtime_path:
                normalized["runtime_path"] = runtime_path
            result.append(normalized)
        return result

    @classmethod
    def _hook_candidates(cls, modules: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for module in modules:
            module_id = str(module.get("module_id") or module.get("moduleId") or "")
            runtime_path = str(module.get("runtime_path") or module.get("runtimePath") or "window.__webpack_require__")
            export_names = ModuleDiscoveryManager._normalize_export_names(module.get("export_names") or module.get("exportNames"))
            export_types = module.get("export_types") if isinstance(module.get("export_types"), dict) else module.get("exportTypes") if isinstance(module.get("exportTypes"), dict) else {}
            for export_name in export_names:
                candidate = {
                    "kind": "async-chunk-module-export",
                    "hook_kind": "module-export",
                    "module_id": module_id,
                    "export_name": export_name,
                    "export_type": str(export_types.get(export_name) or "unknown"),
                    "runtime_path": runtime_path,
                    "hook_path": _module_export_hook_path(runtime_path, module_id, export_name),
                    "recommended_follow_up": "hook_module_export_after_chunk_review",
                    "requires_review_approval": True,
                    "automatic_hook_installation": False,
                    "source": "async_chunk_module_diff",
                }
                candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    return candidates
        return candidates


@dataclass(slots=True)
class CustomLoaderModuleDiffSpec:
    """Review-only module diff and hook candidate refresh after reviewed custom loader execution."""

    custom_loader_execution_result: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    max_candidates: int = 30

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderModuleDiffSpec | None":
        context = context or {}
        execution_result = (
            context.get("custom_loader_execution_result")
            or context.get("custom-loader-execution-result")
            or context.get("customLoaderExecutionResult")
        )
        discovery = (
            context.get("module_discovery")
            or context.get("moduleDiscovery")
            or context.get("module_registry")
            or context.get("moduleRegistry")
        )
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        if not isinstance(execution_result, dict):
            return None
        return cls(
            custom_loader_execution_result=dict(execution_result),
            module_discovery=dict(discovery) if isinstance(discovery, dict) else {},
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 30)) or 30)),
        )


@dataclass(slots=True)
class CustomLoaderModuleDiffResult:
    status: str
    diff: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "diff": self.diff,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class CustomLoaderModuleDiffManager:
    """Build a side-effect-free module diff and hook candidate refresh after custom loader execution."""

    def plan(self, spec: CustomLoaderModuleDiffSpec | None) -> CustomLoaderModuleDiffResult:
        policy = self._side_effect_policy()
        if spec is None:
            return CustomLoaderModuleDiffResult(status="unsupported", reason="missing_custom_loader_execution_result", side_effect_policy=policy)
        execution = self._execution_payload(spec.custom_loader_execution_result)
        if not execution.get("attempted") or not execution.get("ok"):
            return CustomLoaderModuleDiffResult(status="blocked", reason="successful_custom_loader_execution_required", side_effect_policy=policy)
        if execution.get("loaderInvoked") is False or execution.get("loader_invoked") is False:
            return CustomLoaderModuleDiffResult(status="blocked", reason="custom_loader_invocation_required", side_effect_policy=policy)
        added_registry_keys = [str(item) for item in execution.get("addedRegistryKeys") or execution.get("added_registry_keys") or [] if str(item)]
        added_cache_keys = [str(item) for item in execution.get("addedCacheKeys") or execution.get("added_cache_keys") or [] if str(item)]
        modules = AsyncChunkModuleDiffManager._module_records(
            AsyncChunkModuleDiffSpec(
                async_chunk_load_result={},
                module_discovery=spec.module_discovery,
                modules=spec.modules,
                max_candidates=spec.max_candidates,
            )
        )
        matched_modules = [module for module in modules if str(module.get("module_id") or module.get("moduleId") or "") in set(added_registry_keys + added_cache_keys)]
        candidates = self._hook_candidates(matched_modules, max_candidates=spec.max_candidates)
        status = "planned" if candidates or matched_modules or added_registry_keys or added_cache_keys else "blocked"
        diff = {
            "schema_version": "reverse-deepagent.custom-loader-module-diff.v1",
            "status": "ready_for_review" if status == "planned" else "blocked",
            "source": "custom_loader_execution_result",
            "loader_path": execution.get("loaderPath") or execution.get("loader_path") or spec.custom_loader_execution_result.get("loader_path", ""),
            "added_registry_keys": added_registry_keys,
            "added_cache_keys": added_cache_keys,
            "matched_module_count": len(matched_modules),
            "candidate_count": len(candidates),
            "matched_modules": matched_modules[: spec.max_candidates],
            "hook_candidates": candidates,
            "review_required": True,
            "automatic_hook_installation": False,
            "module_factory_invoked": False,
            "next_action": "review_custom_loader_module_diff_hook_candidates" if candidates else "rerun_module_discovery_after_custom_loader_execution",
        }
        return CustomLoaderModuleDiffResult(
            status=status,
            diff=diff,
            side_effect_policy=policy,
            reason=None if status == "planned" else "no_added_module_diff_or_candidates",
        )

    @staticmethod
    def _execution_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("execution"), dict):
            return payload["execution"]
        return payload

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "requires_prior_reviewed_custom_loader_execution": True,
            "executes_custom_loader": False,
            "loads_chunk": False,
            "installs_hooks": False,
            "evaluates_javascript": False,
            "module_factory_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _hook_candidates(cls, modules: list[dict[str, Any]], *, max_candidates: int) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for module in modules:
            module_id = str(module.get("module_id") or module.get("moduleId") or "")
            runtime_path = str(module.get("runtime_path") or module.get("runtimePath") or "window.__webpack_require__")
            export_names = ModuleDiscoveryManager._normalize_export_names(module.get("export_names") or module.get("exportNames"))
            export_types = module.get("export_types") if isinstance(module.get("export_types"), dict) else module.get("exportTypes") if isinstance(module.get("exportTypes"), dict) else {}
            for export_name in export_names:
                candidate = {
                    "kind": "custom-loader-module-export",
                    "hook_kind": "module-export",
                    "module_id": module_id,
                    "export_name": export_name,
                    "export_type": str(export_types.get(export_name) or "unknown"),
                    "runtime_path": runtime_path,
                    "hook_path": _module_export_hook_path(runtime_path, module_id, export_name),
                    "recommended_follow_up": "hook_module_export_after_custom_loader_review",
                    "requires_review_approval": True,
                    "automatic_hook_installation": False,
                    "source": "custom_loader_module_diff",
                }
                candidates.append(candidate)
                if len(candidates) >= max_candidates:
                    return candidates
        return candidates


@dataclass(slots=True)
class AsyncChunkModuleHookSpec:
    """Review-approved hook install request derived from async chunk module diff candidates."""

    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    candidate_index: int | None = None
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkModuleHookSpec | None":
        context = context or {}
        diff = (
            context.get("async_chunk_module_diff")
            or context.get("async-chunk-module-diff")
            or context.get("asyncChunkModuleDiff")
        )
        if not isinstance(diff, dict):
            return None
        index_value = context.get("candidate_index", context.get("candidateIndex"))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        selected = (
            context.get("selected_hook_candidate")
            or context.get("selectedHookCandidate")
            or context.get("hook_candidate")
            or context.get("hookCandidate")
        )
        return cls(
            async_chunk_module_diff=dict(diff),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            candidate_index=candidate_index,
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )


@dataclass(slots=True)
class AsyncChunkModuleHookResult:
    status: str
    module_hook_result: ModuleHookResult | None = None
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "module_hook_result": self.module_hook_result.to_dict() if self.module_hook_result else {},
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class AsyncChunkModuleHookManager:
    """Install reviewed hooks from async chunk module diff candidates by delegating to ModuleHookManager."""

    def install(self, page: BrowserPage, spec: AsyncChunkModuleHookSpec | None) -> AsyncChunkModuleHookResult:
        policy = self._side_effect_policy(review_approved=bool(spec and spec.review_approved))
        if spec is None:
            return AsyncChunkModuleHookResult(status="unsupported", reason="missing_async_chunk_module_diff", side_effect_policy=policy)
        candidate = self._select_candidate(spec)
        if not candidate:
            return AsyncChunkModuleHookResult(status="blocked", reason="review_async_chunk_module_diff_hook_candidates", side_effect_policy=policy)
        if not spec.review_approved:
            return AsyncChunkModuleHookResult(status="blocked", selected_candidate=candidate, reason="review_approval_required", side_effect_policy=policy)
        if str(candidate.get("source") or "") != "async_chunk_module_diff":
            return AsyncChunkModuleHookResult(status="blocked", selected_candidate=candidate, reason="candidate_not_from_async_chunk_module_diff", side_effect_policy=policy)
        if str(candidate.get("hook_kind") or candidate.get("hookKind") or "") != "module-export":
            return AsyncChunkModuleHookResult(status="blocked", selected_candidate=candidate, reason="unsupported_async_chunk_hook_kind", side_effect_policy=policy)
        module_spec = ModuleHookSpec.from_context(
            {
                "module_id": candidate.get("module_id") or candidate.get("moduleId"),
                "export_name": candidate.get("export_name") or candidate.get("exportName"),
                "require_path": candidate.get("runtime_path") or candidate.get("runtimePath") or "window.__webpack_require__",
                "function_name": candidate.get("function_name") or candidate.get("functionName") or candidate.get("export_name") or candidate.get("exportName"),
                "capture_args": spec.capture_args,
                "capture_result": spec.capture_result,
                "max_preview_length": spec.max_preview_length,
                "trigger_expression": spec.trigger_expression,
            }
        )
        if module_spec is None:
            return AsyncChunkModuleHookResult(status="blocked", selected_candidate=candidate, reason="candidate_missing_module_or_export", side_effect_policy=policy)
        result = ModuleHookManager().install(page, module_spec)
        status = "success" if result.status == "success" else "partial" if result.status == "partial" else "failed"
        return AsyncChunkModuleHookResult(status=status, module_hook_result=result, selected_candidate=candidate, side_effect_policy=policy)

    @classmethod
    def _select_candidate(cls, spec: AsyncChunkModuleHookSpec) -> dict[str, Any]:
        candidates = cls._candidates(spec.async_chunk_module_diff)
        if spec.candidate_index is not None and 0 <= spec.candidate_index < len(candidates):
            return dict(candidates[spec.candidate_index])
        if spec.selected_candidate:
            selected_module = str(spec.selected_candidate.get("module_id") or spec.selected_candidate.get("moduleId") or "")
            selected_export = str(spec.selected_candidate.get("export_name") or spec.selected_candidate.get("exportName") or "")
            selected_hook_path = str(spec.selected_candidate.get("hook_path") or spec.selected_candidate.get("hookPath") or "")
            for candidate in candidates:
                module_id = str(candidate.get("module_id") or candidate.get("moduleId") or "")
                export_name = str(candidate.get("export_name") or candidate.get("exportName") or "")
                hook_path = str(candidate.get("hook_path") or candidate.get("hookPath") or "")
                if selected_hook_path and hook_path == selected_hook_path:
                    return dict(candidate)
                if selected_module and selected_export and module_id == selected_module and export_name == selected_export:
                    return dict(candidate)
            merged = dict(spec.selected_candidate)
            merged.setdefault("source", "selected_hook_candidate")
            return merged
        if len(candidates) == 1:
            return dict(candidates[0])
        return {}

    @staticmethod
    def _candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("diff"), dict):
            payload = payload["diff"]
        value = payload.get("hook_candidates") or payload.get("hookCandidates") or []
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _side_effect_policy(*, review_approved: bool) -> dict[str, Any]:
        return {
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": review_approved,
            "loads_chunk": False,
            "installs_hooks": review_approved,
            "delegates_to_module_hook_manager": True,
            "evaluates_javascript": review_approved,
            "module_factory_invoked": False,
            "automatic_hook_installation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class CustomLoaderModuleHookSpec:
    """Review-approved hook install request derived from custom-loader module diff candidates."""

    custom_loader_module_diff: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    candidate_index: int | None = None
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderModuleHookSpec | None":
        context = context or {}
        diff = (
            context.get("custom_loader_module_diff")
            or context.get("custom-loader-module-diff")
            or context.get("customLoaderModuleDiff")
        )
        if not isinstance(diff, dict):
            return None
        index_value = context.get("candidate_index", context.get("candidateIndex"))
        candidate_index: int | None = None
        if index_value is not None:
            try:
                candidate_index = int(index_value)
            except (TypeError, ValueError):
                candidate_index = None
        selected = (
            context.get("selected_hook_candidate")
            or context.get("selectedHookCandidate")
            or context.get("hook_candidate")
            or context.get("hookCandidate")
        )
        return cls(
            custom_loader_module_diff=dict(diff),
            selected_candidate=dict(selected) if isinstance(selected, dict) else {},
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            candidate_index=candidate_index,
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )


@dataclass(slots=True)
class CustomLoaderModuleHookResult:
    status: str
    module_hook_result: ModuleHookResult | None = None
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "module_hook_result": self.module_hook_result.to_dict() if self.module_hook_result else {},
            "selected_candidate": self.selected_candidate,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class CustomLoaderModuleHookManager:
    """Install reviewed hooks from custom-loader module diff candidates by delegating to ModuleHookManager."""

    def install(self, page: BrowserPage, spec: CustomLoaderModuleHookSpec | None) -> CustomLoaderModuleHookResult:
        policy = self._side_effect_policy(review_approved=bool(spec and spec.review_approved))
        if spec is None:
            return CustomLoaderModuleHookResult(status="unsupported", reason="missing_custom_loader_module_diff", side_effect_policy=policy)
        candidate = self._select_candidate(spec)
        if not candidate:
            return CustomLoaderModuleHookResult(status="blocked", reason="review_custom_loader_module_diff_hook_candidates", side_effect_policy=policy)
        if not spec.review_approved:
            return CustomLoaderModuleHookResult(status="blocked", selected_candidate=candidate, reason="review_approval_required", side_effect_policy=policy)
        if str(candidate.get("source") or "") != "custom_loader_module_diff":
            return CustomLoaderModuleHookResult(status="blocked", selected_candidate=candidate, reason="candidate_not_from_custom_loader_module_diff", side_effect_policy=policy)
        if str(candidate.get("hook_kind") or candidate.get("hookKind") or "") != "module-export":
            return CustomLoaderModuleHookResult(status="blocked", selected_candidate=candidate, reason="unsupported_custom_loader_hook_kind", side_effect_policy=policy)
        module_spec = ModuleHookSpec.from_context(
            {
                "module_id": candidate.get("module_id") or candidate.get("moduleId"),
                "export_name": candidate.get("export_name") or candidate.get("exportName"),
                "require_path": candidate.get("runtime_path") or candidate.get("runtimePath") or "window.__webpack_require__",
                "function_name": candidate.get("function_name") or candidate.get("functionName") or candidate.get("export_name") or candidate.get("exportName"),
                "capture_args": spec.capture_args,
                "capture_result": spec.capture_result,
                "max_preview_length": spec.max_preview_length,
                "trigger_expression": spec.trigger_expression,
            }
        )
        if module_spec is None:
            return CustomLoaderModuleHookResult(status="blocked", selected_candidate=candidate, reason="candidate_missing_module_or_export", side_effect_policy=policy)
        result = ModuleHookManager().install(page, module_spec)
        status = "success" if result.status == "success" else "partial" if result.status == "partial" else "failed"
        return CustomLoaderModuleHookResult(status=status, module_hook_result=result, selected_candidate=candidate, side_effect_policy=policy)

    @classmethod
    def _select_candidate(cls, spec: CustomLoaderModuleHookSpec) -> dict[str, Any]:
        candidates = cls._candidates(spec.custom_loader_module_diff)
        if spec.candidate_index is not None and 0 <= spec.candidate_index < len(candidates):
            return dict(candidates[spec.candidate_index])
        if spec.selected_candidate:
            selected_module = str(spec.selected_candidate.get("module_id") or spec.selected_candidate.get("moduleId") or "")
            selected_export = str(spec.selected_candidate.get("export_name") or spec.selected_candidate.get("exportName") or "")
            selected_hook_path = str(spec.selected_candidate.get("hook_path") or spec.selected_candidate.get("hookPath") or "")
            for candidate in candidates:
                module_id = str(candidate.get("module_id") or candidate.get("moduleId") or "")
                export_name = str(candidate.get("export_name") or candidate.get("exportName") or "")
                hook_path = str(candidate.get("hook_path") or candidate.get("hookPath") or "")
                if selected_hook_path and hook_path == selected_hook_path:
                    return dict(candidate)
                if selected_module and selected_export and module_id == selected_module and export_name == selected_export:
                    return dict(candidate)
            merged = dict(spec.selected_candidate)
            merged.setdefault("source", "selected_hook_candidate")
            return merged
        if len(candidates) == 1:
            return dict(candidates[0])
        return {}

    @staticmethod
    def _candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(payload.get("diff"), dict):
            payload = payload["diff"]
        value = payload.get("hook_candidates") or payload.get("hookCandidates") or []
        return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _side_effect_policy(*, review_approved: bool) -> dict[str, Any]:
        return {
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": review_approved,
            "loads_chunk": False,
            "executes_custom_loader": False,
            "installs_hooks": review_approved,
            "delegates_to_module_hook_manager": True,
            "evaluates_javascript": review_approved,
            "module_factory_invoked": False,
            "automatic_hook_installation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
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
