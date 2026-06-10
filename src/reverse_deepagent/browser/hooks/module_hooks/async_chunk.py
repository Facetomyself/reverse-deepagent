"""module_hooks.async_chunk — split from monolithic module_hooks.py (B1 consolidation)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.collectors.scripts import ScriptCollector

from reverse_deepagent.browser.hooks.module_hooks.base import (
    JS_IDENTIFIER_RE, JS_DOTTED_PATH_RE,
    _module_call_path, _export_access_path, _module_export_hook_path,
    _first_dict, _list_dicts, _string_list, _clip,
)
from reverse_deepagent.browser.hooks.module_hooks.module_io import (
    ModuleHookSpec, ModuleHookResult, ModuleDiscoveryManager, ModuleHookManager,
)


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
class AsyncChunkTraversalLoopPlanSpec:
    """Review-only bounded loop planner over async chunk traversal workflow steps."""

    workflow_plan: dict[str, Any] = field(default_factory=dict)
    latest_workflow_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_loop_iterations: int = 3
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkTraversalLoopPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_traversal_loop_plan")
            or context.get("asyncChunkTraversalLoopPlan")
            or context.get("async-chunk-traversal-loop-plan")
            or context.get("async_chunk_deep_traversal_loop")
            or context.get("asyncChunkDeepTraversalLoop")
            or context.get("plan_async_chunk_traversal_loop")
            or context.get("planAsyncChunkTraversalLoop")
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
        latest_execution = (
            context.get("async_chunk_traversal_workflow_execution")
            or context.get("asyncChunkTraversalWorkflowExecution")
            or context.get("async-chunk-traversal-workflow-execution")
            or context.get("latest_async_chunk_traversal_workflow_execution")
            or context.get("latestAsyncChunkTraversalWorkflowExecution")
        )
        if isinstance(latest_execution, dict) and isinstance(latest_execution.get("execution"), dict):
            latest_execution = latest_execution["execution"]
        latest_graph = (
            context.get("latest_async_chunk_traversal_graph")
            or context.get("latestAsyncChunkTraversalGraph")
            or context.get("async_chunk_traversal_graph")
            or context.get("asyncChunkTraversalGraph")
            or context.get("async-chunk-traversal-graph")
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
class AsyncChunkTraversalLoopPlanResult:
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

class AsyncChunkTraversalLoopPlanManager:
    """Plan bounded async chunk traversal loop checkpoints without executing them."""

    def plan(self, spec: AsyncChunkTraversalLoopPlanSpec | None) -> AsyncChunkTraversalLoopPlanResult:
        policy = self._side_effect_policy(max_loop_iterations=spec.max_loop_iterations if spec else 0)
        if spec is None or not spec.workflow_plan:
            return AsyncChunkTraversalLoopPlanResult(status="unsupported", reason="missing_async_chunk_traversal_workflow_plan", side_effect_policy=policy)
        workflow_status = str(spec.workflow_plan.get("status") or "").strip()
        planned_steps = self._planned_steps(spec.workflow_plan)
        if workflow_status == "complete":
            status = "complete"
            reason = None
            selected_steps: list[dict[str, Any]] = []
        elif not planned_steps:
            status = "blocked"
            reason = "no_async_chunk_traversal_workflow_steps"
            selected_steps = []
        else:
            status = "ready_for_review"
            reason = None
            selected_steps = planned_steps[: spec.max_loop_iterations]
        latest_execution_status = self._latest_execution_status(spec.latest_workflow_execution)
        iterations = [self._iteration(step, iteration_index=index, spec=spec) for index, step in enumerate(selected_steps)]
        loop_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-loop-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "async-chunk-traversal-loop-plan",
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
                "execute_at_most_one_chunk_load_per_review": True,
                "refresh_module_diff_before_hook_review": True,
                "rebuild_graph_before_next_iteration": True,
                "replan_workflow_before_next_iteration": True,
                "stop_after_each_iteration_for_manual_review": True,
                "automatic_queue_advance": False,
            },
            "blocking_reasons": [reason] if reason else [],
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason, latest_execution_status=latest_execution_status),
        }
        return AsyncChunkTraversalLoopPlanResult(status=status, loop_plan=loop_plan, side_effect_policy=policy, reason=reason)

    @classmethod
    def _planned_steps(cls, workflow_plan: dict[str, Any]) -> list[dict[str, Any]]:
        steps = workflow_plan.get("planned_steps")
        if isinstance(steps, list):
            return [dict(item) for item in steps if isinstance(item, dict)]
        return []

    @classmethod
    def _iteration(cls, step: dict[str, Any], *, iteration_index: int, spec: AsyncChunkTraversalLoopPlanSpec) -> dict[str, Any]:
        chunk_id = str(step.get("chunk_id") or step.get("chunkId") or step.get("target") or "")[: spec.max_preview_length]
        target = str(step.get("target") or "")[: spec.max_preview_length]
        runtime_path = str(step.get("runtime_path") or step.get("runtimePath") or "")[: spec.max_preview_length]
        return {
            "iteration_index": iteration_index,
            "iteration_id": f"async-chunk-traversal-loop-iteration-{iteration_index}",
            "source_step_index": step.get("step_index", iteration_index),
            "candidate_index": step.get("candidate_index"),
            "chunk_id": chunk_id,
            "target": target,
            "loader_kind": step.get("loader_kind"),
            "edge_type": step.get("edge_type"),
            "runtime_path": runtime_path,
            "review_required": True,
            "manual_checkpoint_required": True,
            "automatic_execution": False,
            "automatic_queue_advance": False,
            "execute_at_most_one_chunk_load_per_review": True,
            "required_artifacts_before_next_iteration": [
                "workspace/async-chunk-traversal-workflow-execution.json",
                "workspace/async-chunk-load-result.json",
                "workspace/async-chunk-module-diff.json",
                "workspace/async-chunk-traversal-graph.json",
                "workspace/async-chunk-traversal-workflow-plan.json",
            ],
            "planned_actions": cls._loop_sequence(),
            "next_action": "review_async_chunk_traversal_loop_iteration",
        }

    @staticmethod
    def _loop_sequence() -> list[dict[str, Any]]:
        return [
            {
                "order": 1,
                "action": "select_one_planned_async_chunk_traversal_workflow_step",
                "input_artifact": "workspace/async-chunk-traversal-workflow-plan.json",
                "output_artifact": None,
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 2,
                "action": "execute_selected_async_chunk_traversal_workflow_step_with_explicit_stage_flags",
                "input_artifact": "workspace/async-chunk-traversal-workflow-plan.json",
                "output_artifact": "workspace/async-chunk-traversal-workflow-execution.json",
                "executes_runtime": True,
                "review_required": True,
                "requires_review_approved": True,
            },
            {
                "order": 3,
                "action": "refresh_async_chunk_module_diff_after_reviewed_load",
                "input_artifact": "workspace/async-chunk-load-result.json",
                "output_artifact": "workspace/async-chunk-module-diff.json",
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 4,
                "action": "optionally_install_reviewed_async_chunk_module_hook",
                "input_artifact": "workspace/async-chunk-module-diff.json",
                "output_artifact": "workspace/module-hooks.json",
                "executes_runtime": True,
                "review_required": True,
                "requires_review_approved": True,
            },
            {
                "order": 5,
                "action": "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph",
                "input_artifact": "workspace/async-chunk-traversal-workflow-execution.json",
                "output_artifact": "workspace/async-chunk-traversal-graph.json",
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 6,
                "action": "replan_async_chunk_traversal_workflow_from_refreshed_graph",
                "input_artifact": "workspace/async-chunk-traversal-graph.json",
                "output_artifact": "workspace/async-chunk-traversal-workflow-plan.json",
                "executes_runtime": False,
                "review_required": True,
            },
            {
                "order": 7,
                "action": "stop_before_next_loop_iteration_review",
                "input_artifact": "workspace/async-chunk-traversal-workflow-plan.json",
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
            if latest_execution_status in {"module_hook_recorded", "module_diff_ready", "async_chunk_load_success"}:
                return "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph_before_next_loop_iteration"
            return "review_async_chunk_traversal_loop_plan"
        if status == "complete":
            return "async_chunk_traversal_loop_complete_or_provide_new_candidates"
        if reason:
            return "revise_async_chunk_traversal_loop_inputs"
        return "inspect_async_chunk_traversal_loop_plan"

    @staticmethod
    def _side_effect_policy(*, max_loop_iterations: int) -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "max_loop_iterations": max_loop_iterations,
            "execute_at_most_one_chunk_load_per_review": True,
            "automatic_loop_execution": False,
            "automatic_recursive_traversal": False,
            "automatic_queue_advance": False,
            "traversal_graph_rebuilt": False,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "module_factory_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class AsyncChunkTraversalLoopExecutionSpec:
    """Review-gated executor for one bounded async chunk traversal loop iteration."""

    loop_plan: dict[str, Any] = field(default_factory=dict)
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    selected_iteration_index: int | None = None
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
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkTraversalLoopExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_traversal_loop_execution")
            or context.get("asyncChunkTraversalLoopExecution")
            or context.get("async-chunk-traversal-loop-execution")
            or context.get("execute_async_chunk_traversal_loop")
            or context.get("executeAsyncChunkTraversalLoop")
        )
        loop_plan = (
            context.get("async_chunk_traversal_loop_plan")
            or context.get("asyncChunkTraversalLoopPlan")
            or context.get("async-chunk-traversal-loop-plan")
            or context.get("loop_plan")
            or context.get("loopPlan")
        )
        if isinstance(loop_plan, dict) and isinstance(loop_plan.get("loop_plan"), dict):
            loop_plan = loop_plan["loop_plan"]
        if not isinstance(loop_plan, dict):
            return None if not requested else cls()
        workflow_plan = (
            context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        return cls(
            loop_plan=dict(loop_plan),
            workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            async_chunk_load_plan=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_load_plan", "async-chunk-load-plan", "asyncChunkLoadPlan"),
            async_chunk_load_result=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult"),
            async_chunk_module_diff=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff"),
            module_hook_result=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_module_hook_result", "async-chunk-module-hook-result", "asyncChunkModuleHookResult", "module_hooks", "module-hooks"),
            module_discovery=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_iteration_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("selected_iteration_index", context.get("selectedIterationIndex", context.get("iteration_index", context.get("iterationIndex"))))),
            selected_step_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
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

@dataclass(slots=True)
class AsyncChunkTraversalLoopExecutionResult:
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

class AsyncChunkTraversalLoopExecutionManager:
    """Execute one reviewed async chunk traversal loop iteration and stop."""

    def execute(self, page: BrowserPage, spec: AsyncChunkTraversalLoopExecutionSpec | None) -> AsyncChunkTraversalLoopExecutionResult:
        if spec is None or not spec.loop_plan:
            return AsyncChunkTraversalLoopExecutionResult(status="unsupported", reason="missing_async_chunk_traversal_loop_plan", side_effect_policy=self._side_effect_policy())
        selected_iteration = self._selected_iteration(spec)
        if not selected_iteration:
            execution = self._execution_payload(spec, {}, {}, [], status="blocked", reason="missing_async_chunk_traversal_loop_iteration")
            return AsyncChunkTraversalLoopExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_async_chunk_traversal_loop_iteration")
        workflow_plan = self._workflow_plan(spec, selected_iteration)
        if not workflow_plan:
            execution = self._execution_payload(spec, selected_iteration, {}, [], status="blocked", reason="missing_async_chunk_traversal_workflow_plan")
            return AsyncChunkTraversalLoopExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_async_chunk_traversal_workflow_plan")

        stages: list[dict[str, Any]] = [
            self._stage("select_async_chunk_traversal_loop_iteration", "selected", "", side_effect=False),
        ]
        workflow_execution_payload: dict[str, Any] = {}
        if self._has_workflow_execution_flags(spec):
            workflow_result = AsyncChunkTraversalWorkflowExecutionManager().execute(
                page,
                AsyncChunkTraversalWorkflowExecutionSpec(
                    workflow_plan=workflow_plan,
                    async_chunk_load_plan=spec.async_chunk_load_plan,
                    async_chunk_load_result=spec.async_chunk_load_result,
                    async_chunk_module_diff=spec.async_chunk_module_diff,
                    module_hook_result=spec.module_hook_result,
                    module_discovery=spec.module_discovery,
                    modules=spec.modules,
                    selected_step_index=self._selected_step_index(spec, selected_iteration),
                    candidate_index=self._candidate_index(spec, selected_iteration),
                    plan_async_chunk_load=spec.plan_async_chunk_load,
                    execute_async_chunk_load=spec.execute_async_chunk_load,
                    run_module_diff=spec.run_module_diff,
                    install_module_hook=spec.install_module_hook,
                    review_approved=spec.review_approved,
                    capture_args=spec.capture_args,
                    capture_result=spec.capture_result,
                    max_preview_length=spec.max_preview_length,
                    trigger_expression=spec.trigger_expression,
                ),
            )
            workflow_execution_payload = workflow_result.to_dict()
            stages.append(self._stage("execute_one_async_chunk_traversal_workflow_iteration", workflow_result.status, workflow_result.reason, side_effect=True))
        else:
            stages.append(self._stage("execute_one_async_chunk_traversal_workflow_iteration", "pending", "explicit_stage_flag_required", side_effect=True))
        stages.append(self._stage("stop_before_graph_rebuild_and_next_loop_iteration", "stopped", "manual_checkpoint_required", side_effect=False))

        status = self._status(stages, workflow_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, selected_iteration, workflow_execution_payload, stages, status=status, reason=reason)
        return AsyncChunkTraversalLoopExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, workflow_execution=workflow_execution_payload), reason=reason)

    @staticmethod
    def _selected_iteration(spec: AsyncChunkTraversalLoopExecutionSpec) -> dict[str, Any]:
        iterations = spec.loop_plan.get("iterations") if isinstance(spec.loop_plan.get("iterations"), list) else []
        normalized_iterations = [dict(item) for item in iterations if isinstance(item, dict)]
        if not normalized_iterations:
            return {}
        selected_index = spec.selected_iteration_index if spec.selected_iteration_index is not None else 0
        for iteration in normalized_iterations:
            try:
                if int(iteration.get("iteration_index", -1)) == selected_index:
                    return iteration
            except (TypeError, ValueError):
                continue
        if 0 <= selected_index < len(normalized_iterations):
            return normalized_iterations[selected_index]
        return {}

    @staticmethod
    def _selected_step_index(spec: AsyncChunkTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> int | None:
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        raw = iteration.get("source_step_index", iteration.get("step_index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _candidate_index(spec: AsyncChunkTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> int | None:
        if spec.candidate_index is not None:
            return spec.candidate_index
        raw = iteration.get("candidate_index", iteration.get("index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _workflow_plan(spec: AsyncChunkTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> dict[str, Any]:
        if spec.workflow_plan:
            return dict(spec.workflow_plan)
        selected_step = {
            "step_index": iteration.get("source_step_index", 0),
            "candidate_index": iteration.get("candidate_index"),
            "chunk_id": iteration.get("chunk_id"),
            "target": iteration.get("target"),
            "loader_kind": iteration.get("loader_kind"),
            "edge_type": iteration.get("edge_type"),
            "runtime_path": iteration.get("runtime_path"),
        }
        return {
            "plan_id": spec.loop_plan.get("source_workflow_plan_id") or "async-chunk-traversal-workflow-plan",
            "source_graph_id": spec.loop_plan.get("source_graph_id"),
            "status": "ready_for_review",
            "planned_steps": [selected_step],
        }

    @staticmethod
    def _has_workflow_execution_flags(spec: AsyncChunkTraversalLoopExecutionSpec) -> bool:
        return any((spec.plan_async_chunk_load, spec.execute_async_chunk_load, spec.run_module_diff, spec.install_module_hook))

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], workflow_execution: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "failure", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        nested_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        workflow_status = str(workflow_execution.get("status") or nested_execution.get("status") or "")
        if workflow_status in {"module_hook_recorded", "module_diff_ready", "async_chunk_load_success", "async_chunk_load_planned"}:
            return workflow_status
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
        spec: AsyncChunkTraversalLoopExecutionSpec,
        selected_iteration: dict[str, Any],
        workflow_execution: dict[str, Any],
        stages: list[dict[str, Any]],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        nested_workflow_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.async-chunk-traversal-loop-execution.v1",
            "status": status,
            "reason": reason,
            "loop_plan_id": spec.loop_plan.get("plan_id"),
            "source_workflow_plan_id": spec.loop_plan.get("source_workflow_plan_id"),
            "source_graph_id": spec.loop_plan.get("source_graph_id"),
            "selected_iteration_index": selected_iteration.get("iteration_index"),
            "selected_step_index": cls._selected_step_index(spec, selected_iteration) if selected_iteration else None,
            "selected_candidate_index": cls._candidate_index(spec, selected_iteration) if selected_iteration else None,
            "selected_iteration": selected_iteration,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "stages": stages,
            "async_chunk_traversal_workflow_execution": workflow_execution,
            "workflow_execution_status": workflow_execution.get("status") or nested_workflow_execution.get("status"),
            "artifact_refs": {
                "loop_plan": "workspace/async-chunk-traversal-loop-plan.json",
                "workflow_plan": "workspace/async-chunk-traversal-workflow-plan.json",
                "workflow_execution": "workspace/async-chunk-traversal-workflow-execution.json" if workflow_execution else "",
                "async_chunk_load_result": "workspace/async-chunk-load-result.json" if nested_workflow_execution.get("async_chunk_load_result") else "",
                "async_chunk_module_diff": "workspace/async-chunk-module-diff.json" if nested_workflow_execution.get("async_chunk_module_diff") else "",
                "module_hooks": "workspace/module-hooks.json" if nested_workflow_execution.get("module_hook_result") else "",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "async_chunk_load_planned":
            return "approve_execute_async_chunk_load_for_loop_iteration"
        if status == "async_chunk_load_success":
            return "run_async_chunk_module_diff_after_loop_iteration_load"
        if status == "module_diff_ready":
            return "review_async_chunk_module_diff_then_rebuild_graph"
        if status == "module_hook_recorded":
            return "rerun_module_discovery_and_rebuild_async_chunk_traversal_graph_before_next_loop_iteration"
        if status == "blocked" and reason:
            return "resolve_async_chunk_traversal_loop_execution_blockers"
        if status == "failed":
            return "inspect_async_chunk_traversal_loop_execution_failure"
        return "review_async_chunk_traversal_loop_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: AsyncChunkTraversalLoopExecutionSpec | None = None,
        workflow_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nested_policy = workflow_execution.get("side_effect_policy") if isinstance(workflow_execution, dict) and isinstance(workflow_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and (spec.plan_async_chunk_load or spec.execute_async_chunk_load or spec.run_module_diff or spec.install_module_hook)),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "execute_at_most_one_chunk_load_per_review": True,
            "async_chunk_load_planned": bool(nested_policy.get("async_chunk_load_planned", False)),
            "runtime_loader_executed": bool(nested_policy.get("runtime_loader_executed", False)),
            "chunk_request_sent": bool(nested_policy.get("chunk_request_sent", False)),
            "module_diff_executed": bool(nested_policy.get("module_diff_executed", False)),
            "module_hook_installed": bool(nested_policy.get("module_hook_installed", False)),
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "module_factory_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalPlanSpec:
    """Review-only follow-up planner after a bounded async-chunk loop execution."""

    loop_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    max_recursive_iterations: int = 3

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkRecursiveTraversalPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_recursive_traversal_plan")
            or context.get("asyncChunkRecursiveTraversalPlan")
            or context.get("async-chunk-recursive-traversal-plan")
            or context.get("async_chunk_traversal_recursion_plan")
            or context.get("asyncChunkTraversalRecursionPlan")
            or context.get("plan_async_chunk_recursive_traversal")
            or context.get("planAsyncChunkRecursiveTraversal")
        )
        loop_execution = (
            context.get("async_chunk_traversal_loop_execution")
            or context.get("asyncChunkTraversalLoopExecution")
            or context.get("async-chunk-traversal-loop-execution")
            or context.get("latest_async_chunk_traversal_loop_execution")
            or context.get("latestAsyncChunkTraversalLoopExecution")
            or context.get("loop_execution")
            or context.get("loopExecution")
        )
        if isinstance(loop_execution, dict) and isinstance(loop_execution.get("execution"), dict):
            loop_execution = loop_execution["execution"]
        graph = (
            context.get("latest_async_chunk_traversal_graph")
            or context.get("latestAsyncChunkTraversalGraph")
            or context.get("async_chunk_traversal_graph")
            or context.get("asyncChunkTraversalGraph")
            or context.get("async-chunk-traversal-graph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        workflow_plan = (
            context.get("latest_async_chunk_traversal_workflow_plan")
            or context.get("latestAsyncChunkTraversalWorkflowPlan")
            or context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(loop_execution, dict):
            return None if not requested else cls()
        return cls(
            loop_execution=dict(loop_execution),
            latest_traversal_graph=dict(graph) if isinstance(graph, dict) else {},
            latest_workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            max_recursive_iterations=max(1, int(context.get("max_recursive_iterations", context.get("maxRecursiveIterations", 3)) or 3)),
        )

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalPlanResult:
    status: str
    recursive_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recursive_plan": self.recursive_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }

class AsyncChunkRecursiveTraversalPlanManager:
    """Plan the next reviewed recursion checkpoint after one bounded async loop iteration."""

    EXECUTED_STATUSES = {"module_hook_recorded", "module_diff_ready", "async_chunk_load_success"}

    def plan(self, spec: AsyncChunkRecursiveTraversalPlanSpec | None) -> AsyncChunkRecursiveTraversalPlanResult:
        policy = self._side_effect_policy(max_recursive_iterations=spec.max_recursive_iterations if spec else 0)
        if spec is None or not spec.loop_execution:
            return AsyncChunkRecursiveTraversalPlanResult(status="unsupported", reason="missing_async_chunk_traversal_loop_execution", side_effect_policy=policy)

        loop_status = self._loop_status(spec.loop_execution)
        graph_status = str(spec.latest_traversal_graph.get("status") or "")
        workflow_status = str(spec.latest_workflow_plan.get("status") or "")
        graph_queue_count = self._count(spec.latest_traversal_graph.get("queue_count"), spec.latest_traversal_graph.get("review_queue"))
        workflow_step_count = self._count(spec.latest_workflow_plan.get("planned_step_count"), spec.latest_workflow_plan.get("planned_steps"))

        if loop_status not in self.EXECUTED_STATUSES:
            status = "blocked"
            reason = "async_chunk_loop_execution_not_ready_for_recursion"
        elif graph_status == "complete" or (spec.latest_traversal_graph and graph_queue_count == 0 and workflow_step_count == 0):
            status = "complete"
            reason = None
        elif spec.latest_traversal_graph and graph_queue_count > 0 and spec.latest_workflow_plan and workflow_step_count > 0:
            status = "ready_for_next_loop_review"
            reason = None
        elif spec.latest_traversal_graph and graph_queue_count > 0:
            status = "ready_for_workflow_replan"
            reason = None
        else:
            status = "ready_for_graph_rebuild"
            reason = None

        recursive_plan = {
            "schema_version": "reverse-deepagent.async-chunk-recursive-traversal-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "async-chunk-recursive-traversal-plan",
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "max_recursive_iterations": spec.max_recursive_iterations,
            "latest_loop_execution_status": loop_status,
            "latest_loop_execution_next_action": spec.loop_execution.get("next_action"),
            "latest_graph_status": graph_status,
            "latest_graph_queue_count": graph_queue_count,
            "latest_workflow_plan_status": workflow_status,
            "latest_workflow_planned_step_count": workflow_step_count,
            "follow_up_steps": self._follow_up_steps(status),
            "blocking_reasons": [reason] if reason else [],
            "artifact_refs": {
                "loop_execution": "workspace/async-chunk-traversal-loop-execution.json",
                "traversal_graph": "workspace/async-chunk-traversal-graph.json",
                "workflow_plan": "workspace/async-chunk-traversal-workflow-plan.json",
                "loop_plan": "workspace/async-chunk-traversal-loop-plan.json",
            },
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason),
        }
        return AsyncChunkRecursiveTraversalPlanResult(status=status, recursive_plan=recursive_plan, side_effect_policy=policy, reason=reason)

    @staticmethod
    def _loop_status(loop_execution: dict[str, Any]) -> str:
        nested = loop_execution.get("execution") if isinstance(loop_execution.get("execution"), dict) else loop_execution
        return str(nested.get("status") or loop_execution.get("status") or "")

    @staticmethod
    def _count(explicit_count: Any, items: Any) -> int:
        try:
            return int(explicit_count)
        except (TypeError, ValueError):
            return len(items) if isinstance(items, list) else 0

    @staticmethod
    def _follow_up_steps(status: str) -> list[dict[str, Any]]:
        steps = [
            ("verify_reviewed_async_chunk_loop_execution_checkpoint", "workspace/async-chunk-traversal-loop-execution.json", None),
            ("rebuild_async_chunk_traversal_graph_from_module_discovery_and_load_evidence", "workspace/async-chunk-load-result.json", "workspace/async-chunk-traversal-graph.json"),
            ("replan_async_chunk_traversal_workflow_from_refreshed_graph", "workspace/async-chunk-traversal-graph.json", "workspace/async-chunk-traversal-workflow-plan.json"),
            ("plan_next_bounded_async_chunk_traversal_loop", "workspace/async-chunk-traversal-workflow-plan.json", "workspace/async-chunk-traversal-loop-plan.json"),
            ("stop_before_next_recursive_async_loop_execution_review", "workspace/async-chunk-traversal-loop-plan.json", None),
        ]
        if status == "ready_for_workflow_replan":
            steps = steps[2:]
        elif status == "ready_for_next_loop_review":
            steps = steps[3:]
        elif status == "complete":
            steps = [("record_async_chunk_recursive_traversal_complete", "workspace/async-chunk-traversal-graph.json", None)]
        return [
            {
                "order": index + 1,
                "action": action,
                "input_artifact": input_artifact,
                "output_artifact": output_artifact,
                "review_required": True,
                "executes_runtime": False,
                "automatic_execution": False,
            }
            for index, (action, input_artifact, output_artifact) in enumerate(steps)
        ]

    @staticmethod
    def _next_action(*, status: str, reason: str | None) -> str:
        if status == "blocked" and reason:
            return "resolve_async_chunk_recursive_traversal_blockers"
        if status == "complete":
            return "async_chunk_recursive_traversal_complete_or_provide_new_candidates"
        if status == "ready_for_next_loop_review":
            return "review_next_async_chunk_traversal_loop_plan"
        if status == "ready_for_workflow_replan":
            return "replan_async_chunk_traversal_workflow_before_next_loop"
        return "rebuild_async_chunk_traversal_graph_before_next_recursive_loop"

    @staticmethod
    def _side_effect_policy(*, max_recursive_iterations: int) -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "max_recursive_iterations": max_recursive_iterations,
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "loop_plan_created": False,
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "module_factory_invoked": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalFollowupSpec:
    """Review-gated follow-through for async-chunk recursive traversal checkpoints."""

    recursive_plan: dict[str, Any] = field(default_factory=dict)
    chunk_graph: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    loop_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    rebuild_graph: bool = False
    replan_workflow: bool = False
    plan_next_loop: bool = False
    review_approved: bool = False
    max_loop_iterations: int = 3
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkRecursiveTraversalFollowupSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_recursive_traversal_followup")
            or context.get("asyncChunkRecursiveTraversalFollowup")
            or context.get("async-chunk-recursive-traversal-followup")
            or context.get("async_chunk_recursive_traversal_checkpoint")
            or context.get("asyncChunkRecursiveTraversalCheckpoint")
            or context.get("async-chunk-recursive-traversal-checkpoint")
            or context.get("execute_async_chunk_recursive_traversal_followup")
            or context.get("executeAsyncChunkRecursiveTraversalFollowup")
        )
        recursive_plan = (
            context.get("async_chunk_recursive_traversal_plan")
            or context.get("asyncChunkRecursiveTraversalPlan")
            or context.get("async-chunk-recursive-traversal-plan")
            or context.get("recursive_traversal_plan")
            or context.get("recursiveTraversalPlan")
        )
        if isinstance(recursive_plan, dict) and isinstance(recursive_plan.get("recursive_plan"), dict):
            recursive_plan = recursive_plan["recursive_plan"]
        if not isinstance(recursive_plan, dict):
            return None if not requested else cls()
        module_discovery = context.get("module_discovery") or context.get("moduleDiscovery")
        chunk_graph = context.get("chunk_graph") or context.get("chunkGraph") or context.get("async_chunk_graph") or context.get("asyncChunkGraph")
        if not isinstance(chunk_graph, dict) and isinstance(module_discovery, dict):
            chunk_graph = module_discovery.get("chunk_graph") or module_discovery.get("chunkGraph")
        if isinstance(chunk_graph, dict) and isinstance(chunk_graph.get("chunk_graph"), dict):
            chunk_graph = chunk_graph["chunk_graph"]
        graph = (
            context.get("latest_async_chunk_traversal_graph")
            or context.get("latestAsyncChunkTraversalGraph")
            or context.get("async_chunk_traversal_graph")
            or context.get("asyncChunkTraversalGraph")
            or context.get("async-chunk-traversal-graph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        workflow_plan = (
            context.get("latest_async_chunk_traversal_workflow_plan")
            or context.get("latestAsyncChunkTraversalWorkflowPlan")
            or context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        loop_execution = (
            context.get("async_chunk_traversal_loop_execution")
            or context.get("asyncChunkTraversalLoopExecution")
            or context.get("async-chunk-traversal-loop-execution")
            or context.get("loop_execution")
            or context.get("loopExecution")
        )
        if isinstance(loop_execution, dict) and isinstance(loop_execution.get("execution"), dict):
            loop_execution = loop_execution["execution"]
        return cls(
            recursive_plan=dict(recursive_plan),
            chunk_graph=dict(chunk_graph) if isinstance(chunk_graph, dict) else {},
            async_chunk_load_result=AsyncChunkTraversalGraphSpec._object_alias(context, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult"),
            async_chunk_module_diff=AsyncChunkTraversalGraphSpec._object_alias(context, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff"),
            loop_execution=dict(loop_execution) if isinstance(loop_execution, dict) else {},
            latest_traversal_graph=dict(graph) if isinstance(graph, dict) else {},
            latest_workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            rebuild_graph=bool(context.get("rebuild_graph") or context.get("rebuildGraph") or context.get("rebuild_traversal_graph") or context.get("rebuildTraversalGraph")),
            replan_workflow=bool(context.get("replan_workflow") or context.get("replanWorkflow") or context.get("replan_traversal_workflow") or context.get("replanTraversalWorkflow")),
            plan_next_loop=bool(context.get("plan_next_loop") or context.get("planNextLoop") or context.get("plan_next_traversal_loop") or context.get("planNextTraversalLoop")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            max_loop_iterations=max(1, int(context.get("max_loop_iterations", context.get("maxLoopIterations", 3)) or 3)),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalFollowupResult:
    status: str
    followup: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "followup": self.followup,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }

class AsyncChunkRecursiveTraversalFollowupManager:
    """Advance one reviewed async-chunk recursive checkpoint without loading chunks."""

    def follow_up(self, spec: AsyncChunkRecursiveTraversalFollowupSpec | None) -> AsyncChunkRecursiveTraversalFollowupResult:
        if spec is None or not spec.recursive_plan:
            return AsyncChunkRecursiveTraversalFollowupResult(status="unsupported", reason="missing_async_chunk_recursive_traversal_plan", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = [self._stage("select_async_chunk_recursive_checkpoint", "selected", "", side_effect=False)]
        graph_result_payload: dict[str, Any] = {}
        workflow_result_payload: dict[str, Any] = {}
        loop_plan_result_payload: dict[str, Any] = {}
        graph = dict(spec.latest_traversal_graph)
        workflow_plan = dict(spec.latest_workflow_plan)

        if spec.rebuild_graph:
            if not spec.review_approved:
                stages.append(self._stage("rebuild_async_chunk_traversal_graph", "blocked", "review_approval_required", side_effect=False))
            elif not spec.chunk_graph:
                stages.append(self._stage("rebuild_async_chunk_traversal_graph", "blocked", "missing_async_chunk_graph", side_effect=False))
            else:
                graph_result = AsyncChunkTraversalGraphManager().plan(
                    AsyncChunkTraversalGraphSpec(
                        chunk_graph=spec.chunk_graph,
                        async_chunk_load_result=spec.async_chunk_load_result,
                        async_chunk_module_diff=spec.async_chunk_module_diff,
                        previous_traversal_graph=spec.latest_traversal_graph,
                        max_queue_size=spec.max_queue_size,
                        max_preview_length=spec.max_preview_length,
                    )
                )
                graph_result_payload = graph_result.to_dict()
                graph = graph_result.graph
                stages.append(self._stage("rebuild_async_chunk_traversal_graph", graph_result.status, graph_result.reason, side_effect=False))
        else:
            stages.append(self._stage("rebuild_async_chunk_traversal_graph", "pending", "", side_effect=False))

        if spec.replan_workflow:
            if not spec.review_approved:
                stages.append(self._stage("replan_async_chunk_traversal_workflow", "blocked", "review_approval_required", side_effect=False))
            elif not graph:
                stages.append(self._stage("replan_async_chunk_traversal_workflow", "blocked", "async_chunk_traversal_graph_required", side_effect=False))
            else:
                workflow_result = AsyncChunkTraversalWorkflowPlanManager().plan(AsyncChunkTraversalWorkflowPlanSpec(traversal_graph=graph))
                workflow_result_payload = workflow_result.to_dict()
                workflow_plan = workflow_result.workflow_plan
                stages.append(self._stage("replan_async_chunk_traversal_workflow", workflow_result.status, workflow_result.reason, side_effect=False))
        else:
            stages.append(self._stage("replan_async_chunk_traversal_workflow", "pending", "", side_effect=False))

        if spec.plan_next_loop:
            if not spec.review_approved:
                stages.append(self._stage("plan_next_async_chunk_traversal_loop", "blocked", "review_approval_required", side_effect=False))
            elif not workflow_plan:
                stages.append(self._stage("plan_next_async_chunk_traversal_loop", "blocked", "async_chunk_traversal_workflow_plan_required", side_effect=False))
            else:
                loop_result = AsyncChunkTraversalLoopPlanManager().plan(
                    AsyncChunkTraversalLoopPlanSpec(
                        workflow_plan=workflow_plan,
                        latest_workflow_execution=spec.loop_execution,
                        latest_traversal_graph=graph,
                        max_loop_iterations=spec.max_loop_iterations,
                        max_preview_length=spec.max_preview_length,
                    )
                )
                loop_plan_result_payload = loop_result.to_dict()
                stages.append(self._stage("plan_next_async_chunk_traversal_loop", loop_result.status, loop_result.reason, side_effect=False))
        else:
            stages.append(self._stage("plan_next_async_chunk_traversal_loop", "pending", "", side_effect=False))

        stages.append(self._stage("stop_before_next_recursive_async_loop_execution", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, loop_plan_result_payload, workflow_result_payload, graph_result_payload)
        reason = self._reason(stages)
        followup = {
            "schema_version": "reverse-deepagent.async-chunk-recursive-traversal-followup.v1",
            "status": status,
            "reason": reason,
            "recursive_plan_id": spec.recursive_plan.get("plan_id"),
            "review_approved": spec.review_approved,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "stages": stages,
            "async_chunk_traversal_graph": graph_result_payload,
            "async_chunk_traversal_workflow_plan": workflow_result_payload,
            "async_chunk_traversal_loop_plan": loop_plan_result_payload,
            "artifact_refs": {
                "recursive_plan": "workspace/async-chunk-recursive-traversal-plan.json",
                "traversal_graph": "workspace/async-chunk-traversal-graph.json" if graph_result_payload else "",
                "workflow_plan": "workspace/async-chunk-traversal-workflow-plan.json" if workflow_result_payload else "",
                "loop_plan": "workspace/async-chunk-traversal-loop-plan.json" if loop_plan_result_payload else "",
            },
            "next_action": self._next_action(status, reason),
        }
        return AsyncChunkRecursiveTraversalFollowupResult(status=status, followup=followup, side_effect_policy=self._side_effect_policy(spec=spec, stages=stages), reason=reason)

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @staticmethod
    def _status(stages: list[dict[str, Any]], loop_plan_result: dict[str, Any], workflow_result: dict[str, Any], graph_result: dict[str, Any]) -> str:
        if any(stage["status"] in {"failed", "error"} for stage in stages):
            return "failed"
        if any(stage["status"] in {"blocked", "unsupported"} for stage in stages):
            return "blocked"
        loop_plan = loop_plan_result.get("loop_plan") if isinstance(loop_plan_result.get("loop_plan"), dict) else {}
        if loop_plan_result and str(loop_plan_result.get("status") or loop_plan.get("status") or "") in {"ready_for_review", "complete"}:
            return "next_loop_plan_ready"
        workflow_plan = workflow_result.get("workflow_plan") if isinstance(workflow_result.get("workflow_plan"), dict) else {}
        if workflow_result and str(workflow_result.get("status") or workflow_plan.get("status") or "") in {"ready_for_review", "complete"}:
            return "workflow_replanned"
        graph = graph_result.get("graph") if isinstance(graph_result.get("graph"), dict) else {}
        if graph_result and str(graph_result.get("status") or graph.get("status") or "") in {"ready_for_review", "complete"}:
            return "graph_rebuilt"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for stage in stages:
            if stage["status"] in {"blocked", "failed", "error", "unsupported"} and stage.get("reason"):
                return str(stage["reason"])
        return None

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "next_loop_plan_ready":
            return "review_next_async_chunk_traversal_loop_plan_before_execution"
        if status == "workflow_replanned":
            return "plan_next_async_chunk_traversal_loop"
        if status == "graph_rebuilt":
            return "replan_async_chunk_traversal_workflow_before_next_loop"
        if status == "blocked" and reason:
            return "resolve_async_chunk_recursive_traversal_followup_blockers"
        if status == "failed":
            return "inspect_async_chunk_recursive_traversal_followup_failure"
        return "review_async_chunk_recursive_traversal_followup_plan"

    @staticmethod
    def _side_effect_policy(spec: AsyncChunkRecursiveTraversalFollowupSpec | None = None, stages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        stages = stages or []
        return {
            "plan_only_by_default": not bool(spec and any((spec.rebuild_graph, spec.replan_workflow, spec.plan_next_loop))),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "traversal_graph_rebuilt": any(stage["stage"] == "rebuild_async_chunk_traversal_graph" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "workflow_replanned": any(stage["stage"] == "replan_async_chunk_traversal_workflow" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "loop_plan_created": any(stage["stage"] == "plan_next_async_chunk_traversal_loop" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "runtime_loader_executed": False,
            "chunk_request_sent": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "module_factory_invoked": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalExecutionSpec:
    """Review-gated execution of one next-loop step from an async recursion checkpoint."""

    recursive_followup: dict[str, Any] = field(default_factory=dict)
    loop_plan: dict[str, Any] = field(default_factory=dict)
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_load_result: dict[str, Any] = field(default_factory=dict)
    async_chunk_module_diff: dict[str, Any] = field(default_factory=dict)
    module_hook_result: dict[str, Any] = field(default_factory=dict)
    module_discovery: dict[str, Any] = field(default_factory=dict)
    modules: list[dict[str, Any]] = field(default_factory=list)
    selected_iteration_index: int | None = None
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
    def from_context(cls, context: dict[str, Any] | None = None) -> "AsyncChunkRecursiveTraversalExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("async_chunk_recursive_traversal_execution")
            or context.get("asyncChunkRecursiveTraversalExecution")
            or context.get("async-chunk-recursive-traversal-execution")
            or context.get("execute_async_chunk_recursive_traversal")
            or context.get("executeAsyncChunkRecursiveTraversal")
            or context.get("execute_async_chunk_recursive_traversal_next_loop")
            or context.get("executeAsyncChunkRecursiveTraversalNextLoop")
        )
        followup = (
            context.get("async_chunk_recursive_traversal_followup")
            or context.get("asyncChunkRecursiveTraversalFollowup")
            or context.get("async-chunk-recursive-traversal-followup")
            or context.get("recursive_traversal_followup")
            or context.get("recursiveTraversalFollowup")
        )
        if isinstance(followup, dict) and isinstance(followup.get("followup"), dict):
            followup = followup["followup"]
        loop_plan = (
            context.get("async_chunk_traversal_loop_plan")
            or context.get("asyncChunkTraversalLoopPlan")
            or context.get("async-chunk-traversal-loop-plan")
            or context.get("next_async_chunk_traversal_loop_plan")
            or context.get("nextAsyncChunkTraversalLoopPlan")
            or context.get("loop_plan")
            or context.get("loopPlan")
        )
        if isinstance(loop_plan, dict) and isinstance(loop_plan.get("loop_plan"), dict):
            loop_plan = loop_plan["loop_plan"]
        if not isinstance(loop_plan, dict) and isinstance(followup, dict):
            loop_result = followup.get("async_chunk_traversal_loop_plan")
            if isinstance(loop_result, dict) and isinstance(loop_result.get("loop_plan"), dict):
                loop_plan = loop_result["loop_plan"]
        if not isinstance(loop_plan, dict):
            return None if not requested else cls(recursive_followup=dict(followup) if isinstance(followup, dict) else {})
        workflow_plan = (
            context.get("async_chunk_traversal_workflow_plan")
            or context.get("asyncChunkTraversalWorkflowPlan")
            or context.get("async-chunk-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(workflow_plan, dict) and isinstance(followup, dict):
            workflow_result = followup.get("async_chunk_traversal_workflow_plan")
            if isinstance(workflow_result, dict) and isinstance(workflow_result.get("workflow_plan"), dict):
                workflow_plan = workflow_result["workflow_plan"]
        modules = context.get("modules", context.get("module_candidates", context.get("moduleCandidates", [])))
        return cls(
            recursive_followup=dict(followup) if isinstance(followup, dict) else {},
            loop_plan=dict(loop_plan),
            workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            async_chunk_load_plan=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_load_plan", "async-chunk-load-plan", "asyncChunkLoadPlan"),
            async_chunk_load_result=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult"),
            async_chunk_module_diff=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff"),
            module_hook_result=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "async_chunk_module_hook_result", "async-chunk-module-hook-result", "asyncChunkModuleHookResult", "module_hooks", "module-hooks"),
            module_discovery=AsyncChunkTraversalWorkflowExecutionSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_iteration_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("selected_iteration_index", context.get("selectedIterationIndex", context.get("iteration_index", context.get("iterationIndex"))))),
            selected_step_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=AsyncChunkTraversalWorkflowExecutionSpec._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
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

@dataclass(slots=True)
class AsyncChunkRecursiveTraversalExecutionResult:
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

class AsyncChunkRecursiveTraversalExecutionManager:
    """Execute one reviewed async next-loop checkpoint and stop before deeper recursion."""

    def execute(self, page: BrowserPage, spec: AsyncChunkRecursiveTraversalExecutionSpec | None) -> AsyncChunkRecursiveTraversalExecutionResult:
        if spec is None or not spec.loop_plan:
            return AsyncChunkRecursiveTraversalExecutionResult(status="unsupported", reason="missing_async_chunk_traversal_loop_plan", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = [self._stage("select_async_chunk_recursive_next_loop_checkpoint", "selected", "", side_effect=False)]
        loop_execution_payload: dict[str, Any] = {}
        if self._has_loop_execution_flags(spec):
            if not spec.review_approved:
                stages.append(self._stage("execute_next_bounded_async_chunk_loop", "blocked", "review_approval_required", side_effect=True))
            else:
                loop_result = AsyncChunkTraversalLoopExecutionManager().execute(
                    page,
                    AsyncChunkTraversalLoopExecutionSpec(
                        loop_plan=spec.loop_plan,
                        workflow_plan=spec.workflow_plan,
                        async_chunk_load_plan=spec.async_chunk_load_plan,
                        async_chunk_load_result=spec.async_chunk_load_result,
                        async_chunk_module_diff=spec.async_chunk_module_diff,
                        module_hook_result=spec.module_hook_result,
                        module_discovery=spec.module_discovery,
                        modules=spec.modules,
                        selected_iteration_index=spec.selected_iteration_index,
                        selected_step_index=spec.selected_step_index,
                        candidate_index=spec.candidate_index,
                        plan_async_chunk_load=spec.plan_async_chunk_load,
                        execute_async_chunk_load=spec.execute_async_chunk_load,
                        run_module_diff=spec.run_module_diff,
                        install_module_hook=spec.install_module_hook,
                        review_approved=spec.review_approved,
                        capture_args=spec.capture_args,
                        capture_result=spec.capture_result,
                        max_preview_length=spec.max_preview_length,
                        trigger_expression=spec.trigger_expression,
                    ),
                )
                loop_execution_payload = loop_result.to_dict()
                stages.append(self._stage("execute_next_bounded_async_chunk_loop", loop_result.status, loop_result.reason, side_effect=True))
        else:
            stages.append(self._stage("execute_next_bounded_async_chunk_loop", "pending", "explicit_stage_flag_required", side_effect=True))
        stages.append(self._stage("stop_before_next_async_recursive_followup_checkpoint", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, loop_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, loop_execution_payload, stages, status=status, reason=reason)
        return AsyncChunkRecursiveTraversalExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, loop_execution=loop_execution_payload, stages=stages), reason=reason)

    @staticmethod
    def _has_loop_execution_flags(spec: AsyncChunkRecursiveTraversalExecutionSpec) -> bool:
        return any((spec.plan_async_chunk_load, spec.execute_async_chunk_load, spec.run_module_diff, spec.install_module_hook))

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], loop_execution: dict[str, Any]) -> str:
        if any(stage["status"] in {"failed", "failure", "error"} for stage in stages):
            return "failed"
        if any(stage["status"] in {"blocked", "unsupported"} for stage in stages):
            return "blocked"
        nested = loop_execution.get("execution") if isinstance(loop_execution.get("execution"), dict) else {}
        loop_status = str(loop_execution.get("status") or nested.get("status") or "")
        if loop_status == "module_hook_recorded":
            return "next_loop_module_hook_recorded"
        if loop_status == "module_diff_ready":
            return "next_loop_module_diff_ready"
        if loop_status == "async_chunk_load_success":
            return "next_loop_execution_progressed"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for stage in stages:
            if stage["status"] in {"blocked", "failed", "failure", "error", "unsupported"} and stage.get("reason"):
                return str(stage["reason"])
        return None

    @classmethod
    def _execution_payload(cls, spec: AsyncChunkRecursiveTraversalExecutionSpec, loop_execution: dict[str, Any], stages: list[dict[str, Any]], *, status: str, reason: str | None) -> dict[str, Any]:
        nested_loop_execution = loop_execution.get("execution") if isinstance(loop_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.async-chunk-recursive-traversal-execution.v1",
            "status": status,
            "reason": reason,
            "recursive_followup_id": spec.recursive_followup.get("recursive_plan_id") or spec.recursive_followup.get("plan_id"),
            "loop_plan_id": spec.loop_plan.get("plan_id"),
            "source_workflow_plan_id": spec.loop_plan.get("source_workflow_plan_id"),
            "source_graph_id": spec.loop_plan.get("source_graph_id"),
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "stages": stages,
            "async_chunk_traversal_loop_execution": loop_execution,
            "loop_execution_status": loop_execution.get("status") or nested_loop_execution.get("status"),
            "artifact_refs": {
                "recursive_followup": "workspace/async-chunk-recursive-traversal-followup.json",
                "loop_plan": "workspace/async-chunk-traversal-loop-plan.json",
                "loop_execution": "workspace/async-chunk-traversal-loop-execution.json" if loop_execution else "",
                "next_recursive_plan": "workspace/async-chunk-recursive-traversal-plan.json",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status in {"next_loop_module_hook_recorded", "next_loop_module_diff_ready", "next_loop_execution_progressed"}:
            return "plan_next_async_chunk_recursive_traversal_checkpoint"
        if status == "blocked" and reason:
            return "resolve_async_chunk_recursive_traversal_execution_blockers"
        if status == "failed":
            return "inspect_async_chunk_recursive_traversal_execution_failure"
        return "review_async_chunk_recursive_traversal_execution_plan"

    @staticmethod
    def _side_effect_policy(spec: AsyncChunkRecursiveTraversalExecutionSpec | None = None, loop_execution: dict[str, Any] | None = None, stages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        stages = stages or []
        nested_policy = loop_execution.get("side_effect_policy") if isinstance(loop_execution, dict) and isinstance(loop_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and any((spec.plan_async_chunk_load, spec.execute_async_chunk_load, spec.run_module_diff, spec.install_module_hook))),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "loop_execution_started": any(stage["stage"] == "execute_next_bounded_async_chunk_loop" and stage["status"] not in {"pending", "blocked"} for stage in stages),
            "async_chunk_load_planned": bool(nested_policy.get("async_chunk_load_planned", False)),
            "runtime_loader_executed": bool(nested_policy.get("runtime_loader_executed", False)),
            "chunk_request_sent": bool(nested_policy.get("chunk_request_sent", False)),
            "module_diff_executed": bool(nested_policy.get("module_diff_executed", False)),
            "module_hook_installed": bool(nested_policy.get("module_hook_installed", False)),
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "module_factory_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
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
