"""module_hooks.federation — split from monolithic module_hooks.py (B1 consolidation)."""

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


@dataclass(slots=True)
class RecursiveContinuationReadinessSpec:
    """Normalize recursive traversal continuation evidence across custom-loader, async-chunk, and federation flows."""

    custom_loader_continuation_journal: dict[str, Any] = field(default_factory=dict)
    custom_loader_recursive_plan: dict[str, Any] = field(default_factory=dict)
    custom_loader_recursive_followup: dict[str, Any] = field(default_factory=dict)
    custom_loader_recursive_execution: dict[str, Any] = field(default_factory=dict)
    async_chunk_recursive_plan: dict[str, Any] = field(default_factory=dict)
    async_chunk_recursive_followup: dict[str, Any] = field(default_factory=dict)
    async_chunk_recursive_execution: dict[str, Any] = field(default_factory=dict)
    module_federation_recursive_continuation_journal: dict[str, Any] = field(default_factory=dict)
    module_federation_recursive_continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    module_federation_recursive_execution: dict[str, Any] = field(default_factory=dict)
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "RecursiveContinuationReadinessSpec | None":
        context = context or {}
        requested = bool(
            context.get("recursive_continuation_readiness")
            or context.get("recursiveContinuationReadiness")
            or context.get("recursive-continuation-readiness")
            or context.get("traversal_continuation_readiness")
            or context.get("traversalContinuationReadiness")
            or context.get("review_recursive_continuation_readiness")
            or context.get("reviewRecursiveContinuationReadiness")
        )
        custom_journal = cls._artifact_payload(
            context,
            "custom_loader_continuation_journal",
            "customLoaderContinuationJournal",
            "custom-loader-continuation-journal",
        )
        custom_plan = cls._artifact_payload(
            context,
            "custom_loader_recursive_traversal_plan",
            "customLoaderRecursiveTraversalPlan",
            "custom-loader-recursive-traversal-plan",
        )
        custom_followup = cls._artifact_payload(
            context,
            "custom_loader_recursive_traversal_followup",
            "customLoaderRecursiveTraversalFollowup",
            "custom-loader-recursive-traversal-followup",
        )
        custom_execution = cls._artifact_payload(
            context,
            "custom_loader_recursive_traversal_execution",
            "customLoaderRecursiveTraversalExecution",
            "custom-loader-recursive-traversal-execution",
        )
        async_plan = cls._artifact_payload(
            context,
            "async_chunk_recursive_traversal_plan",
            "asyncChunkRecursiveTraversalPlan",
            "async-chunk-recursive-traversal-plan",
        )
        async_followup = cls._artifact_payload(
            context,
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
            "async-chunk-recursive-traversal-followup",
        )
        async_execution = cls._artifact_payload(
            context,
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "async-chunk-recursive-traversal-execution",
        )
        federation_journal = cls._artifact_payload(
            context,
            "module_federation_recursive_continuation_journal",
            "moduleFederationRecursiveContinuationJournal",
            "module-federation-recursive-continuation-journal",
            "module_federation_recursive_traversal_continuation_journal",
            "moduleFederationRecursiveTraversalContinuationJournal",
            "module-federation-recursive-traversal-continuation-journal",
        )
        federation_checkpoint = cls._artifact_payload(
            context,
            "module_federation_recursive_continuation_checkpoint",
            "moduleFederationRecursiveContinuationCheckpoint",
            "module-federation-recursive-continuation-checkpoint",
            "module_federation_recursive_traversal_continuation_checkpoint",
            "moduleFederationRecursiveTraversalContinuationCheckpoint",
            "module-federation-recursive-traversal-continuation-checkpoint",
        )
        federation_execution = cls._artifact_payload(
            context,
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
        )
        if not requested and not any(
            (
                custom_journal,
                custom_plan,
                custom_followup,
                custom_execution,
                async_plan,
                async_followup,
                async_execution,
                federation_journal,
                federation_checkpoint,
                federation_execution,
            )
        ):
            return None
        return cls(
            custom_loader_continuation_journal=custom_journal,
            custom_loader_recursive_plan=custom_plan,
            custom_loader_recursive_followup=custom_followup,
            custom_loader_recursive_execution=custom_execution,
            async_chunk_recursive_plan=async_plan,
            async_chunk_recursive_followup=async_followup,
            async_chunk_recursive_execution=async_execution,
            module_federation_recursive_continuation_journal=federation_journal,
            module_federation_recursive_continuation_checkpoint=federation_checkpoint,
            module_federation_recursive_execution=federation_execution,
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

    @staticmethod
    def _artifact_payload(context: dict[str, Any], *keys: str) -> dict[str, Any]:
        value = _first_dict(context, *keys)
        for nested in ("journal", "recursive_plan", "followup", "execution", "checkpoint", "readiness"):
            if isinstance(value.get(nested), dict):
                return dict(value[nested])
        return value

@dataclass(slots=True)
class RecursiveContinuationReadinessResult:
    status: str
    readiness: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readiness": self.readiness,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }

class RecursiveContinuationReadinessManager:
    """Build a side-effect-free cross-system readiness descriptor for recursive traversal continuation."""

    def assess(self, spec: RecursiveContinuationReadinessSpec | None) -> RecursiveContinuationReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            readiness = self._payload([], blockers=["recursive_continuation_evidence_missing"], policy=policy)
            return RecursiveContinuationReadinessResult(status="unsupported", readiness=readiness, side_effect_policy=policy, reason="recursive_continuation_evidence_missing")

        systems = [
            self._custom_loader_system(spec),
            self._async_chunk_system(spec),
            self._module_federation_system(spec),
        ]
        present = [item for item in systems if item["artifact_count"] > 0]
        blockers: list[str] = []
        if not present:
            blockers.append("recursive_continuation_evidence_missing")
        for item in present:
            blockers.extend(item.get("blocking_reasons", []))
        status = "blocked" if blockers else "ready_for_review" if present else "unsupported"
        readiness = self._payload(present, blockers=blockers, policy=policy)
        return RecursiveContinuationReadinessResult(status=status, readiness=readiness, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _custom_loader_system(self, spec: RecursiveContinuationReadinessSpec) -> dict[str, Any]:
        journal = spec.custom_loader_continuation_journal
        plan = spec.custom_loader_recursive_plan
        followup = spec.custom_loader_recursive_followup
        execution = spec.custom_loader_recursive_execution
        artifacts = {
            "continuation_journal": journal,
            "recursive_plan": plan,
            "recursive_followup": followup,
            "recursive_execution": execution,
        }
        statuses = self._artifact_statuses(artifacts)
        blockers = self._status_blockers("custom_loader", statuses)
        latest = self._latest_payload(execution, followup, plan, journal)
        record_count = self._record_count(journal)
        return {
            "system": "custom_loader",
            "schema_family": "reverse-deepagent.custom-loader-recursive-continuation",
            "artifact_count": sum(bool(value) for value in artifacts.values()),
            "artifact_statuses": statuses,
            "journal_record_count": record_count,
            "stage_count": self._stage_count(latest),
            "latest_status": self._status(latest),
            "latest_next_action": self._next_action(latest),
            "continuation_ready": bool(record_count or self._status(latest) in {"ready_for_next_loop_review", "next_loop_plan_ready", "next_loop_module_diff_ready", "next_loop_execution_progressed", "next_loop_journal_appended"}),
            "manual_checkpoint_required": self._manual_checkpoint_required(latest),
            "bounded_recursion": self._bool_from(latest, "bounded_recursion", default=True),
            "blocking_reasons": blockers,
            "artifact_refs": {
                "continuation_journal": "workspace/custom-loader-continuation-journal.json" if journal else "",
                "recursive_plan": "workspace/custom-loader-recursive-traversal-plan.json" if plan else "",
                "recursive_followup": "workspace/custom-loader-recursive-traversal-followup.json" if followup else "",
                "recursive_execution": "workspace/custom-loader-recursive-traversal-execution.json" if execution else "",
            },
        }

    def _async_chunk_system(self, spec: RecursiveContinuationReadinessSpec) -> dict[str, Any]:
        plan = spec.async_chunk_recursive_plan
        followup = spec.async_chunk_recursive_followup
        execution = spec.async_chunk_recursive_execution
        artifacts = {
            "recursive_plan": plan,
            "recursive_followup": followup,
            "recursive_execution": execution,
        }
        statuses = self._artifact_statuses(artifacts)
        blockers = self._status_blockers("async_chunk", statuses)
        latest = self._latest_payload(execution, followup, plan)
        return {
            "system": "async_chunk",
            "schema_family": "reverse-deepagent.async-chunk-recursive-continuation",
            "artifact_count": sum(bool(value) for value in artifacts.values()),
            "artifact_statuses": statuses,
            "journal_record_count": 0,
            "stage_count": self._stage_count(latest),
            "latest_status": self._status(latest),
            "latest_next_action": self._next_action(latest),
            "continuation_ready": self._status(latest) in {"ready_for_next_loop_review", "next_loop_plan_ready", "next_loop_module_diff_ready", "next_loop_execution_progressed", "complete"},
            "manual_checkpoint_required": self._manual_checkpoint_required(latest),
            "bounded_recursion": self._bool_from(latest, "bounded_recursion", default=True),
            "blocking_reasons": blockers,
            "artifact_refs": {
                "recursive_plan": "workspace/async-chunk-recursive-traversal-plan.json" if plan else "",
                "recursive_followup": "workspace/async-chunk-recursive-traversal-followup.json" if followup else "",
                "recursive_execution": "workspace/async-chunk-recursive-traversal-execution.json" if execution else "",
            },
        }

    def _module_federation_system(self, spec: RecursiveContinuationReadinessSpec) -> dict[str, Any]:
        journal = spec.module_federation_recursive_continuation_journal
        checkpoint = spec.module_federation_recursive_continuation_checkpoint
        execution = spec.module_federation_recursive_execution
        artifacts = {
            "continuation_journal": journal,
            "continuation_checkpoint": checkpoint,
            "recursive_execution": execution,
        }
        statuses = self._artifact_statuses(artifacts)
        blockers = self._status_blockers("module_federation", statuses)
        latest = self._latest_payload(checkpoint, execution, journal)
        record_count = self._record_count(journal)
        return {
            "system": "module_federation",
            "schema_family": "reverse-deepagent.module-federation-recursive-continuation",
            "artifact_count": sum(bool(value) for value in artifacts.values()),
            "artifact_statuses": statuses,
            "journal_record_count": record_count,
            "stage_count": self._stage_count(latest),
            "latest_status": self._status(latest),
            "latest_next_action": self._next_action(latest),
            "continuation_ready": bool(record_count or self._status(latest) in {"ready_for_review", "next_execution_review_ready", "graph_rebuilt", "workflow_replanned", "complete"}),
            "manual_checkpoint_required": self._manual_checkpoint_required(latest),
            "bounded_recursion": self._bool_from(latest, "bounded_recursion", default=True),
            "blocking_reasons": blockers,
            "artifact_refs": {
                "continuation_journal": "workspace/module-federation-recursive-continuation-journal.json" if journal else "",
                "continuation_checkpoint": "workspace/module-federation-recursive-continuation-checkpoint.json" if checkpoint else "",
                "recursive_execution": "workspace/module-federation-recursive-traversal-execution.json" if execution else "",
            },
        }

    @classmethod
    def _payload(cls, systems: list[dict[str, Any]], *, blockers: list[str], policy: dict[str, Any]) -> dict[str, Any]:
        ready_systems = [item["system"] for item in systems if item.get("continuation_ready")]
        blocked_systems = [item["system"] for item in systems if item.get("blocking_reasons")]
        return {
            "schema_version": "reverse-deepagent.recursive-continuation-readiness.v1",
            "status": "blocked" if blockers else "ready_for_review" if systems else "unsupported",
            "system_count": len(systems),
            "ready_systems": ready_systems,
            "blocked_systems": blocked_systems,
            "blocking_reasons": list(dict.fromkeys(blockers)),
            "systems": systems,
            "review_required": True,
            "manual_checkpoint_required": True,
            "automatic_recursive_traversal": False,
            "deeper_recursion_executor_ready": False,
            "next_action": cls._readiness_next_action(systems, blockers),
            "side_effect_policy": policy,
        }

    @staticmethod
    def _artifact_statuses(artifacts: dict[str, dict[str, Any]]) -> dict[str, str]:
        return {name: RecursiveContinuationReadinessManager._status(payload) for name, payload in artifacts.items() if payload}

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        for key in ("status", "checkpoint_status", "execution_status", "plan_status", "followup_status"):
            value = payload.get(key)
            if value:
                return str(value)
        for nested in ("journal", "recursive_plan", "followup", "execution", "checkpoint"):
            value = payload.get(nested)
            if isinstance(value, dict) and value.get("status"):
                return str(value["status"])
        return "unknown"

    @staticmethod
    def _next_action(payload: dict[str, Any]) -> str:
        value = payload.get("next_action")
        return str(value) if value else ""

    @staticmethod
    def _latest_payload(*payloads: dict[str, Any]) -> dict[str, Any]:
        for payload in payloads:
            if payload:
                return payload
        return {}

    @staticmethod
    def _record_count(journal: dict[str, Any]) -> int:
        if not journal:
            return 0
        count = journal.get("record_count")
        try:
            return int(count)
        except (TypeError, ValueError):
            records = journal.get("records")
            return len(records) if isinstance(records, list) else 0

    @staticmethod
    def _stage_count(payload: dict[str, Any]) -> int:
        stages = payload.get("stages")
        return len(stages) if isinstance(stages, list) else 0

    @staticmethod
    def _manual_checkpoint_required(payload: dict[str, Any]) -> bool:
        policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
        return bool(payload.get("manual_checkpoint_required", policy.get("manual_checkpoint_required", True)))

    @staticmethod
    def _bool_from(payload: dict[str, Any], key: str, *, default: bool) -> bool:
        policy = payload.get("side_effect_policy") if isinstance(payload.get("side_effect_policy"), dict) else {}
        return bool(payload.get(key, policy.get(key, default)))

    @staticmethod
    def _status_blockers(prefix: str, statuses: dict[str, str]) -> list[str]:
        blockers: list[str] = []
        for name, status in statuses.items():
            if status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append(f"{prefix}_{name}_{status}")
        return blockers

    @staticmethod
    def _readiness_next_action(systems: list[dict[str, Any]], blockers: list[str]) -> str:
        if blockers:
            return "resolve_recursive_continuation_readiness_blockers"
        if not systems:
            return "provide_recursive_continuation_artifacts"
        if any(item.get("continuation_ready") for item in systems):
            return "review_recursive_continuation_checkpoint_before_next_step"
        return "collect_next_recursive_continuation_checkpoint_evidence"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "plan_only": True,
            "review_required": True,
            "manual_checkpoint_required": True,
            "files_mutated": False,
            "artifacts_written": False,
            "loader_invoked": False,
            "chunk_request_sent": False,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationTraversalGraphSpec:
    """Review-only Module Federation remote traversal graph request."""

    get_init_plan: dict[str, Any] = field(default_factory=dict)
    get_init_result: dict[str, Any] = field(default_factory=dict)
    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    previous_graph: dict[str, Any] = field(default_factory=dict)
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationTraversalGraphSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_traversal_graph")
            or context.get("moduleFederationTraversalGraph")
            or context.get("module-federation-traversal-graph")
            or context.get("federation_traversal_graph")
            or context.get("federationTraversalGraph")
            or context.get("remote_module_traversal_graph")
            or context.get("remoteModuleTraversalGraph")
        )
        get_init_plan = _first_dict(
            context,
            "module_federation_get_init_plan",
            "moduleFederationGetInitPlan",
            "module-federation-get-init-plan",
            "get_init_plan",
            "getInitPlan",
        )
        get_init_result = _first_dict(
            context,
            "module_federation_get_init_result",
            "moduleFederationGetInitResult",
            "module-federation-get-init-result",
            "get_init_result",
            "getInitResult",
        )
        factory_invoke_result = _first_dict(
            context,
            "module_federation_factory_invoke_result",
            "moduleFederationFactoryInvokeResult",
            "module-federation-factory-invoke-result",
            "factory_invoke_result",
            "factoryInvokeResult",
        )
        export_hook_plan = _first_dict(
            context,
            "module_federation_export_hook_plan",
            "moduleFederationExportHookPlan",
            "module-federation-export-hook-plan",
            "export_hook_plan",
            "exportHookPlan",
        )
        previous_graph = _first_dict(
            context,
            "previous_module_federation_traversal_graph",
            "previousModuleFederationTraversalGraph",
            "module_federation_traversal_graph_previous",
            "moduleFederationTraversalGraphPrevious",
        )
        if not any((get_init_plan, get_init_result, factory_invoke_result, export_hook_plan, previous_graph)) and not requested:
            return None
        return cls(
            get_init_plan=get_init_plan,
            get_init_result=get_init_result,
            factory_invoke_result=factory_invoke_result,
            export_hook_plan=export_hook_plan,
            previous_graph=previous_graph,
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

@dataclass(slots=True)
class ModuleFederationTraversalGraphResult:
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

class ModuleFederationTraversalGraphManager:
    """Build a review-only traversal graph for Module Federation remotes."""

    def build(self, spec: ModuleFederationTraversalGraphSpec | None) -> ModuleFederationTraversalGraphResult:
        policy = self._side_effect_policy()
        if spec is None:
            return ModuleFederationTraversalGraphResult(status="unsupported", reason="missing_module_federation_traversal_graph_request", side_effect_policy=policy)

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        queue: list[dict[str, Any]] = []
        seen: set[str] = set()

        for candidate in self._candidate_records(spec.get_init_plan):
            node = self._candidate_node(candidate, spec=spec)
            self._add_node(node, nodes=nodes, queue=queue, seen=seen, max_queue_size=spec.max_queue_size)

        factory_execution = self._factory_execution(spec.factory_invoke_result)
        if factory_execution:
            factory_node = self._factory_node(factory_execution, spec=spec)
            self._add_node(factory_node, nodes=nodes, queue=queue, seen=seen, max_queue_size=spec.max_queue_size)
            for export_node in self._export_nodes(factory_execution, spec=spec):
                self._add_node(export_node, nodes=nodes, queue=queue, seen=seen, max_queue_size=spec.max_queue_size)
                edges.append({"from": factory_node["node_id"], "to": export_node["node_id"], "edge_type": "remote-export"})

        export_plan = self._plan_payload(spec.export_hook_plan)
        for hook_candidate in _list_dicts(export_plan.get("candidates")):
            hook_node = self._hook_candidate_node(hook_candidate, spec=spec)
            self._add_node(hook_node, nodes=nodes, queue=queue, seen=seen, max_queue_size=spec.max_queue_size)

        if not nodes:
            graph = self._graph_payload(spec=spec, status="blocked", reason="missing_module_federation_traversal_inputs", nodes=[], edges=[], queue=[])
            return ModuleFederationTraversalGraphResult(status="blocked", graph=graph, side_effect_policy=policy, reason="missing_module_federation_traversal_inputs")

        queue = queue[: spec.max_queue_size]
        status = "ready_for_review" if queue else "complete"
        graph = self._graph_payload(spec=spec, status=status, reason=None, nodes=nodes, edges=edges, queue=queue)
        return ModuleFederationTraversalGraphResult(status=status, graph=graph, side_effect_policy=policy)

    @classmethod
    def _candidate_records(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        plan = cls._plan_payload(payload)
        return _list_dicts(plan.get("candidates"))

    @staticmethod
    def _plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("plan"), dict):
            return payload["plan"]
        if isinstance(payload.get("traversal_graph"), dict):
            return payload["traversal_graph"]
        if isinstance(payload.get("graph"), dict):
            return payload["graph"]
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _factory_execution(cls, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("factory_execution"), dict):
            return payload["factory_execution"]
        if isinstance(payload.get("factoryExecution"), dict):
            return payload["factoryExecution"]
        if payload.get("remoteFactoryInvoked") is not None or payload.get("exportNames") is not None:
            return payload
        return {}

    @classmethod
    def _candidate_node(cls, candidate: dict[str, Any], *, spec: ModuleFederationTraversalGraphSpec) -> dict[str, Any]:
        container_path = _clip(candidate.get("container_path") or candidate.get("containerPath") or candidate.get("runtime_path") or candidate.get("runtimePath"), spec.max_preview_length)
        exposed_name = _clip(candidate.get("exposed_name") or candidate.get("exposedName") or candidate.get("module_id") or candidate.get("moduleId"), spec.max_preview_length)
        node_id = cls._node_id("remote-module", container_path, exposed_name)
        candidate_status = str(candidate.get("status") or "ready_for_review")
        if candidate_status == "blocked":
            status = "blocked"
            next_action = "resolve_module_federation_candidate_blockers"
            blocking_reasons = _string_list(candidate.get("blocking_reasons") or candidate.get("blockingReasons")) or ["module_federation_candidate_blocked"]
        elif bool(candidate.get("function_path_candidate_available") or candidate.get("functionPathCandidateAvailable")):
            status = "function_path_available"
            next_action = "review_existing_function_path_candidate_before_remote_execution"
            blocking_reasons = ["prefer_existing_function_path_candidate"]
        else:
            status = "requires_factory_review"
            next_action = "review_module_federation_factory_invoke_before_deeper_traversal"
            blocking_reasons = ["remote_factory_execution_requires_review"]
        return {
            "node_id": node_id,
            "node_type": "remote-module-candidate",
            "status": status,
            "container_path": container_path,
            "exposed_name": exposed_name,
            "remote_name": _clip(candidate.get("remote_name") or candidate.get("remoteName"), spec.max_preview_length),
            "export_names": _string_list(candidate.get("export_names") or candidate.get("exportNames"))[:20],
            "hook_paths": _string_list(candidate.get("hook_paths") or candidate.get("hookPaths"))[:20],
            "discovery_source": str(candidate.get("discovery_source") or candidate.get("discoverySource") or "unknown"),
            "queueable": status in {"requires_factory_review", "function_path_available"},
            "next_action": next_action,
            "blocking_reasons": blocking_reasons,
            "review_required": True,
            "executes_remote_code_now": False,
            "automatic_traversal": False,
        }

    @classmethod
    def _factory_node(cls, execution: dict[str, Any], *, spec: ModuleFederationTraversalGraphSpec) -> dict[str, Any]:
        container_path = _clip(execution.get("containerPath") or execution.get("container_path"), spec.max_preview_length)
        exposed_name = _clip(execution.get("exposedName") or execution.get("exposed_name"), spec.max_preview_length)
        export_names = _string_list(execution.get("exportNames") or execution.get("export_names"))[:50]
        return {
            "node_id": cls._node_id("factory", container_path, exposed_name),
            "node_type": "remote-factory-result",
            "status": "factory_invoked" if execution.get("remoteFactoryInvoked") else "factory_not_invoked",
            "container_path": container_path,
            "exposed_name": exposed_name,
            "module_type": str(execution.get("moduleType") or execution.get("module_type") or ""),
            "export_names": export_names,
            "export_count": len(export_names),
            "queueable": False,
            "next_action": "plan_module_federation_export_hooks_or_nested_remote_candidates",
            "review_required": False,
            "executes_remote_code_now": False,
            "automatic_traversal": False,
        }

    @classmethod
    def _export_nodes(cls, execution: dict[str, Any], *, spec: ModuleFederationTraversalGraphSpec) -> list[dict[str, Any]]:
        container_path = _clip(execution.get("containerPath") or execution.get("container_path"), spec.max_preview_length)
        exposed_name = _clip(execution.get("exposedName") or execution.get("exposed_name"), spec.max_preview_length)
        previews = execution.get("exportPreviews") if isinstance(execution.get("exportPreviews"), dict) else {}
        nodes: list[dict[str, Any]] = []
        for export_name in _string_list(execution.get("exportNames") or execution.get("export_names"))[:50]:
            preview = previews.get(export_name) if isinstance(previews.get(export_name), dict) else {}
            keys = _string_list(preview.get("keys"))
            looks_like_container = {"get", "init"}.issubset(set(keys))
            status = "nested_container_candidate" if looks_like_container else "export_observed"
            next_action = "review_nested_module_federation_container_candidate" if looks_like_container else "review_remote_export_hook_or_manual_inspection"
            nodes.append(
                {
                    "node_id": cls._node_id("export", container_path, exposed_name, export_name),
                    "node_type": "remote-export",
                    "status": status,
                    "container_path": container_path,
                    "exposed_name": exposed_name,
                    "export_name": export_name,
                    "export_type": str(preview.get("type") or "unknown"),
                    "export_keys": keys[:20],
                    "queueable": looks_like_container,
                    "next_action": next_action,
                    "blocking_reasons": ["nested_container_requires_separate_get_init_review"] if looks_like_container else [],
                    "review_required": looks_like_container,
                    "executes_remote_code_now": False,
                    "automatic_traversal": False,
                }
            )
        return nodes

    @classmethod
    def _hook_candidate_node(cls, candidate: dict[str, Any], *, spec: ModuleFederationTraversalGraphSpec) -> dict[str, Any]:
        container_path = _clip(candidate.get("container_path") or candidate.get("containerPath"), spec.max_preview_length)
        exposed_name = _clip(candidate.get("exposed_name") or candidate.get("exposedName"), spec.max_preview_length)
        export_name = _clip(candidate.get("export_name") or candidate.get("exportName"), spec.max_preview_length)
        hookable = bool(candidate.get("hookable", False))
        return {
            "node_id": cls._node_id("hook", container_path, exposed_name, export_name),
            "node_type": "remote-export-hook-candidate",
            "status": "hook_review_ready" if hookable else "manual_inspection_required",
            "container_path": container_path,
            "exposed_name": exposed_name,
            "export_name": export_name,
            "hook_kind": str(candidate.get("hook_kind") or candidate.get("hookKind") or ""),
            "queueable": hookable,
            "next_action": "review_module_federation_export_hook_plan" if hookable else "inspect_remote_export_shape",
            "blocking_reasons": [] if hookable else _string_list(candidate.get("blocking_reasons") or candidate.get("blockingReasons")),
            "review_required": True,
            "executes_remote_code_now": False,
            "automatic_traversal": False,
        }

    @classmethod
    def _add_node(cls, node: dict[str, Any], *, nodes: list[dict[str, Any]], queue: list[dict[str, Any]], seen: set[str], max_queue_size: int) -> None:
        node_id = str(node.get("node_id") or "")
        if not node_id or node_id in seen:
            return
        seen.add(node_id)
        nodes.append(node)
        if node.get("queueable") and len(queue) < max_queue_size:
            queue.append(
                {
                    "queue_index": len(queue),
                    "node_id": node_id,
                    "node_type": node.get("node_type"),
                    "status": node.get("status"),
                    "next_action": node.get("next_action"),
                    "review_required": True,
                    "executes_remote_code_now": False,
                    "automatic_execution": False,
                }
            )

    @staticmethod
    def _node_id(*parts: str) -> str:
        cleaned = [str(part or "").strip() for part in parts]
        return ":".join(cleaned)

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "container_init_executed": False,
            "remote_get_called": False,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "shared_scope_mutated": False,
            "export_hook_installed": False,
            "recursive_federation_traversal": False,
            "automatic_queue_advance": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _graph_payload(cls, *, spec: ModuleFederationTraversalGraphSpec, status: str, reason: str | None, nodes: list[dict[str, Any]], edges: list[dict[str, Any]], queue: list[dict[str, Any]]) -> dict[str, Any]:
        policy = cls._side_effect_policy()
        return {
            "schema_version": "reverse-deepagent.module-federation-traversal-graph.v1",
            "status": status,
            "reason": reason,
            "review_required": True,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "queue_count": len(queue),
            "max_queue_size": spec.max_queue_size,
            "nodes": nodes,
            "edges": edges,
            "review_queue": queue,
            "side_effect_policy": policy,
            "next_action": "review_module_federation_traversal_workflow_plan" if queue else "module_federation_traversal_complete_or_provide_more_evidence",
        }

@dataclass(slots=True)
class ModuleFederationTraversalWorkflowPlanSpec:
    """Review-only workflow planner for one or more federation traversal graph queue entries."""

    traversal_graph: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 5

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationTraversalWorkflowPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_traversal_workflow_plan")
            or context.get("moduleFederationTraversalWorkflowPlan")
            or context.get("module-federation-traversal-workflow-plan")
            or context.get("federation_traversal_workflow_plan")
            or context.get("federationTraversalWorkflowPlan")
            or context.get("plan_module_federation_traversal_workflow")
            or context.get("planModuleFederationTraversalWorkflow")
        )
        graph = _first_dict(
            context,
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        if not graph and not requested:
            return None
        return cls(
            traversal_graph=graph,
            max_steps=max(1, int(context.get("max_steps", context.get("maxSteps", 5)) or 5)),
        )

@dataclass(slots=True)
class ModuleFederationTraversalWorkflowPlanResult:
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

class ModuleFederationTraversalWorkflowPlanManager:
    """Turn a federation traversal graph queue into review-only workflow steps."""

    def plan(self, spec: ModuleFederationTraversalWorkflowPlanSpec | None) -> ModuleFederationTraversalWorkflowPlanResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.traversal_graph:
            return ModuleFederationTraversalWorkflowPlanResult(status="unsupported", reason="missing_module_federation_traversal_graph", side_effect_policy=policy)
        queue = _list_dicts(spec.traversal_graph.get("review_queue"))[: spec.max_steps]
        nodes = {str(node.get("node_id")): node for node in _list_dicts(spec.traversal_graph.get("nodes"))}
        if not queue:
            workflow_plan = self._workflow_payload(spec=spec, status="complete", reason=None, steps=[], policy=policy)
            return ModuleFederationTraversalWorkflowPlanResult(status="complete", workflow_plan=workflow_plan, side_effect_policy=policy)
        steps = [self._step_for_queue_item(item, node=nodes.get(str(item.get("node_id")), {}), index=index) for index, item in enumerate(queue)]
        workflow_plan = self._workflow_payload(spec=spec, status="ready_for_review", reason=None, steps=steps, policy=policy)
        return ModuleFederationTraversalWorkflowPlanResult(status="ready_for_review", workflow_plan=workflow_plan, side_effect_policy=policy)

    @staticmethod
    def _step_for_queue_item(item: dict[str, Any], *, node: dict[str, Any], index: int) -> dict[str, Any]:
        node_type = str(node.get("node_type") or item.get("node_type") or "")
        node_status = str(node.get("status") or item.get("status") or "")
        action = "review_module_federation_traversal_node"
        required_artifact = "workspace/module-federation-traversal-graph.json"
        output_artifact = None
        if node_type == "remote-module-candidate" and node_status == "requires_factory_review":
            action = "review_module_federation_factory_invoke_for_traversal"
            output_artifact = "workspace/module-federation-factory-invoke-result.json"
        elif node_type == "remote-module-candidate" and node_status == "function_path_available":
            action = "review_existing_function_path_candidate_before_remote_execution"
            output_artifact = "workspace/function-candidates.json"
        elif node_type == "remote-export-hook-candidate":
            action = "review_module_federation_export_hook_plan_for_traversal"
            output_artifact = "workspace/function-hooks.json"
        elif node_type == "remote-export" and node_status == "nested_container_candidate":
            action = "review_nested_module_federation_container_candidate"
            output_artifact = "workspace/module-federation-get-init-plan.json"
        return {
            "step_index": index,
            "node_id": item.get("node_id"),
            "node_type": node_type,
            "node_status": node_status,
            "action": action,
            "input_artifact": required_artifact,
            "output_artifact": output_artifact,
            "container_path": node.get("container_path", ""),
            "exposed_name": node.get("exposed_name", ""),
            "export_name": node.get("export_name", ""),
            "hook_kind": node.get("hook_kind", ""),
            "node": dict(node),
            "review_required": True,
            "executes_remote_code_now": False,
            "automatic_execution": False,
            "blocking_reasons": _string_list(node.get("blocking_reasons") or item.get("blocking_reasons")),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "plan_only": True,
            "review_required": True,
            "container_init_executed": False,
            "remote_get_called": False,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "export_hook_installed": False,
            "workflow_executed": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _workflow_payload(cls, *, spec: ModuleFederationTraversalWorkflowPlanSpec, status: str, reason: str | None, steps: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.module-federation-traversal-workflow-plan.v1",
            "status": status,
            "reason": reason,
            "review_required": True,
            "planned_step_count": len(steps),
            "max_steps": spec.max_steps,
            "planned_steps": steps,
            "side_effect_policy": policy,
            "next_action": "review_module_federation_traversal_workflow_plan" if steps else "module_federation_traversal_complete_or_provide_more_evidence",
        }

@dataclass(slots=True)
class ModuleFederationTraversalWorkflowExecutionSpec:
    """Review-gated executor over one selected Module Federation traversal workflow step."""

    workflow_plan: dict[str, Any] = field(default_factory=dict)
    traversal_graph: dict[str, Any] = field(default_factory=dict)
    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    export_hook_result: dict[str, Any] = field(default_factory=dict)
    selected_step_index: int | None = None
    candidate_index: int | None = None
    invoke_remote_factory: bool = False
    plan_export_hook: bool = False
    install_export_hook: bool = False
    plan_nested_get_init: bool = False
    review_approved: bool = False
    share_scope_path: str = "window.__webpack_share_scopes__.default"
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationTraversalWorkflowExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_traversal_workflow_execution")
            or context.get("moduleFederationTraversalWorkflowExecution")
            or context.get("module-federation-traversal-workflow-execution")
            or context.get("execute_module_federation_traversal_workflow")
            or context.get("executeModuleFederationTraversalWorkflow")
            or context.get("execute_federation_traversal_workflow")
            or context.get("executeFederationTraversalWorkflow")
        )
        workflow_plan = _first_dict(
            context,
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "federation_traversal_workflow_plan",
            "federationTraversalWorkflowPlan",
            "traversal_workflow_plan",
            "traversalWorkflowPlan",
        )
        if isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = dict(workflow_plan["workflow_plan"])
        traversal_graph = _first_dict(
            context,
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(traversal_graph.get("graph"), dict):
            traversal_graph = dict(traversal_graph["graph"])
        if not workflow_plan and not requested:
            return None
        return cls(
            workflow_plan=workflow_plan,
            traversal_graph=traversal_graph,
            factory_invoke_result=_first_dict(context, "module_federation_factory_invoke_result", "moduleFederationFactoryInvokeResult", "module-federation-factory-invoke-result", "factory_invoke_result", "factoryInvokeResult"),
            export_hook_plan=_first_dict(context, "module_federation_export_hook_plan", "moduleFederationExportHookPlan", "module-federation-export-hook-plan", "export_hook_plan", "exportHookPlan"),
            export_hook_result=_first_dict(context, "module_federation_export_hook_result", "moduleFederationExportHookResult", "module-federation-export-hook-result", "remote_export_hook_result", "remoteExportHookResult"),
            selected_step_index=cls._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=cls._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
            invoke_remote_factory=bool(context.get("invoke_remote_factory") or context.get("invokeRemoteFactory") or context.get("execute_remote_factory") or context.get("executeRemoteFactory") or context.get("execute_module_federation_factory") or context.get("executeModuleFederationFactory") or context.get("invoke_module_federation_factory") or context.get("invokeModuleFederationFactory")),
            plan_export_hook=bool(context.get("plan_export_hook") or context.get("planExportHook") or context.get("plan_module_federation_export_hook") or context.get("planModuleFederationExportHook")),
            install_export_hook=bool(context.get("install_export_hook") or context.get("installExportHook") or context.get("install_module_federation_export_hook") or context.get("installModuleFederationExportHook") or context.get("hook_remote_export") or context.get("hookRemoteExport")),
            plan_nested_get_init=bool(context.get("plan_nested_get_init") or context.get("planNestedGetInit") or context.get("plan_nested_federation_get_init") or context.get("planNestedFederationGetInit")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            share_scope_path=str(context.get("share_scope_path", context.get("shareScopePath", "window.__webpack_share_scopes__.default")) or "window.__webpack_share_scopes__.default").strip(),
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
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
class ModuleFederationTraversalWorkflowExecutionResult:
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

class ModuleFederationTraversalWorkflowExecutionManager:
    """Execute at most one reviewed Module Federation traversal workflow step."""

    def execute(self, page: BrowserPage, spec: ModuleFederationTraversalWorkflowExecutionSpec | None) -> ModuleFederationTraversalWorkflowExecutionResult:
        if spec is None or not spec.workflow_plan:
            return ModuleFederationTraversalWorkflowExecutionResult(status="unsupported", reason="missing_module_federation_traversal_workflow_plan", side_effect_policy=self._side_effect_policy())
        selected_step = self._selected_step(spec)
        if not selected_step:
            execution = self._execution_payload(spec, {}, [], {}, {}, {}, {}, status="blocked", reason="missing_module_federation_traversal_workflow_step")
            return ModuleFederationTraversalWorkflowExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_module_federation_traversal_workflow_step")

        stages: list[dict[str, Any]] = [self._stage("select_module_federation_traversal_workflow_step", "selected", "", side_effect=False)]
        factory_payload = dict(spec.factory_invoke_result)
        export_plan_payload = dict(spec.export_hook_plan)
        export_hook_payload = dict(spec.export_hook_result)
        nested_get_init_plan: dict[str, Any] = {}

        action = str(selected_step.get("action") or "")
        if action == "review_existing_function_path_candidate_before_remote_execution":
            stages.append(self._stage("prefer_existing_function_path_candidate", "blocked", "prefer_hook_function_candidate_without_remote_execution", side_effect=False))
        elif action == "review_nested_module_federation_container_candidate":
            if spec.plan_nested_get_init:
                nested_candidate = self._nested_candidate(selected_step)
                if not nested_candidate:
                    stages.append(self._stage("plan_nested_module_federation_get_init", "blocked", "nested_container_runtime_path_required", side_effect=False))
                else:
                    plan_result = ModuleFederationGetInitPlanManager().plan(ModuleFederationGetInitPlanSpec(candidates=[nested_candidate], max_candidates=1, max_preview_length=spec.max_preview_length, review_approved=spec.review_approved))
                    nested_get_init_plan = plan_result.to_dict()
                    stages.append(self._stage("plan_nested_module_federation_get_init", plan_result.status, plan_result.reason, side_effect=False))
            else:
                stages.append(self._stage("plan_nested_module_federation_get_init", "pending", "nested_container_review_required", side_effect=False))
        else:
            if spec.invoke_remote_factory:
                factory_result = ModuleFederationFactoryInvokeManager().plan_or_invoke(page, self._factory_spec(spec, selected_step, execute=True))
                factory_payload = factory_result.to_dict()
                stages.append(self._stage("invoke_one_reviewed_module_federation_remote_factory", factory_result.status, factory_result.reason, side_effect=True))
            elif factory_payload:
                stages.append(self._stage("invoke_one_reviewed_module_federation_remote_factory", str(factory_payload.get("status") or "observed"), "", side_effect=False, observed=True))
            else:
                stages.append(self._stage("invoke_one_reviewed_module_federation_remote_factory", "pending", "reviewed_remote_factory_invocation_required", side_effect=True))

            if spec.plan_export_hook:
                if not factory_payload:
                    stages.append(self._stage("plan_module_federation_export_hook", "blocked", "module_federation_factory_invoke_result_required", side_effect=False))
                else:
                    plan_result = ModuleFederationExportHookPlanManager().plan(ModuleFederationExportHookPlanSpec(factory_invoke_result=factory_payload, max_candidates=30))
                    export_plan_payload = plan_result.to_dict()
                    stages.append(self._stage("plan_module_federation_export_hook", plan_result.status, plan_result.reason, side_effect=False))
            elif export_plan_payload:
                stages.append(self._stage("plan_module_federation_export_hook", str(export_plan_payload.get("status") or "observed"), "", side_effect=False, observed=True))
            else:
                stages.append(self._stage("plan_module_federation_export_hook", "pending", "factory_export_review_required", side_effect=False))

            if spec.install_export_hook:
                if not export_plan_payload:
                    stages.append(self._stage("install_reviewed_module_federation_export_hook", "blocked", "module_federation_export_hook_plan_required", side_effect=True))
                else:
                    hook_result = ModuleFederationExportHookInstallManager().install(
                        page,
                        ModuleFederationExportHookInstallSpec(
                            export_hook_plan=export_plan_payload,
                            review_approved=spec.review_approved,
                            candidate_index=spec.candidate_index,
                            share_scope_path=spec.share_scope_path,
                            capture_args=spec.capture_args,
                            capture_result=spec.capture_result,
                            max_preview_length=spec.max_preview_length,
                            trigger_expression=spec.trigger_expression,
                        ),
                    )
                    export_hook_payload = hook_result.to_dict()
                    stages.append(self._stage("install_reviewed_module_federation_export_hook", hook_result.status, hook_result.reason, side_effect=True))
            elif export_hook_payload:
                stages.append(self._stage("install_reviewed_module_federation_export_hook", str(export_hook_payload.get("status") or "observed"), "", side_effect=False, observed=True))
            else:
                stages.append(self._stage("install_reviewed_module_federation_export_hook", "pending", "export_hook_install_review_required", side_effect=True))

        stages.append(self._stage("stop_before_federation_graph_rebuild_or_queue_advance", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, factory_payload, export_plan_payload, export_hook_payload, nested_get_init_plan)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, selected_step, stages, factory_payload, export_plan_payload, export_hook_payload, nested_get_init_plan, status=status, reason=reason)
        return ModuleFederationTraversalWorkflowExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, factory_result=factory_payload, export_plan=export_plan_payload, export_hook=export_hook_payload), reason=reason)

    @staticmethod
    def _selected_step(spec: ModuleFederationTraversalWorkflowExecutionSpec) -> dict[str, Any]:
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
    def _candidate_from_step(selected_step: dict[str, Any]) -> dict[str, Any]:
        node = selected_step.get("node") if isinstance(selected_step.get("node"), dict) else {}
        return {
            "container_path": selected_step.get("container_path") or node.get("container_path"),
            "exposed_name": selected_step.get("exposed_name") or node.get("exposed_name"),
            "module_id": selected_step.get("exposed_name") or node.get("exposed_name"),
            "remote_name": node.get("remote_name", ""),
            "export_names": node.get("export_names", []),
            "hook_paths": node.get("hook_paths", []),
            "discovery_source": "module_federation_traversal_workflow_step",
        }

    @classmethod
    def _factory_spec(cls, spec: ModuleFederationTraversalWorkflowExecutionSpec, selected_step: dict[str, Any], *, execute: bool) -> ModuleFederationFactoryInvokeSpec | None:
        candidate = cls._candidate_from_step(selected_step)
        return ModuleFederationFactoryInvokeSpec(
            candidate=candidate,
            execute_factory=execute,
            review_approved=spec.review_approved,
            share_scope_path=spec.share_scope_path,
            max_preview_length=spec.max_preview_length,
        )

    @staticmethod
    def _nested_candidate(selected_step: dict[str, Any]) -> dict[str, Any]:
        node = selected_step.get("node") if isinstance(selected_step.get("node"), dict) else {}
        runtime_path = selected_step.get("nested_container_path") or node.get("nested_container_path") or node.get("runtime_path")
        exposed_name = selected_step.get("nested_exposed_name") or node.get("nested_exposed_name") or selected_step.get("exposed_name") or node.get("exposed_name")
        if not runtime_path:
            return {}
        return {
            "container_path": runtime_path,
            "runtime_path": runtime_path,
            "exposed_name": exposed_name,
            "module_id": exposed_name,
            "remote_name": node.get("export_name") or selected_step.get("export_name") or "nested_remote_candidate",
            "discovery_source": "module_federation_nested_container_candidate",
        }

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool, observed: bool = False) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect, "observed_input": observed}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], factory_result: dict[str, Any], export_plan: dict[str, Any], export_hook: dict[str, Any], nested_get_init_plan: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "failure", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        if export_hook.get("status") in {"success", "partial"}:
            return "export_hook_installed"
        plan_payload = export_plan.get("plan") if isinstance(export_plan.get("plan"), dict) else export_plan
        if str(export_plan.get("status") or plan_payload.get("status") or "") in {"planned", "ready_for_review"}:
            return "export_hook_plan_ready"
        if str(factory_result.get("status") or "") == "success":
            return "factory_invoke_success"
        if nested_get_init_plan:
            return "nested_get_init_plan_ready"
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
        spec: ModuleFederationTraversalWorkflowExecutionSpec,
        selected_step: dict[str, Any],
        stages: list[dict[str, Any]],
        factory_result: dict[str, Any],
        export_plan: dict[str, Any],
        export_hook: dict[str, Any],
        nested_get_init_plan: dict[str, Any],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.module-federation-traversal-workflow-execution.v1",
            "status": status,
            "reason": reason,
            "workflow_plan_id": spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.workflow_plan.get("source_graph_id"),
            "selected_step_index": selected_step.get("step_index"),
            "selected_node_id": selected_step.get("node_id"),
            "selected_action": selected_step.get("action"),
            "selected_step": selected_step,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "execute_at_most_one_remote_step_per_review": True,
            "stages": stages,
            "module_federation_factory_invoke_result": factory_result,
            "module_federation_export_hook_plan": export_plan,
            "module_federation_export_hook_result": export_hook,
            "nested_module_federation_get_init_plan": nested_get_init_plan,
            "artifact_refs": {
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json",
                "factory_invoke_result": "workspace/module-federation-factory-invoke-result.json" if factory_result else "",
                "export_hook_plan": "workspace/module-federation-export-hook-plan.json" if export_plan else "",
                "export_hook_result": "workspace/module-federation-export-hook-result.json" if export_hook else "",
                "nested_get_init_plan": "workspace/module-federation-get-init-plan.json" if nested_get_init_plan else "",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "factory_invoke_success":
            return "plan_module_federation_export_hook_after_reviewed_factory_invoke"
        if status == "export_hook_plan_ready":
            return "review_module_federation_export_hook_plan"
        if status == "export_hook_installed":
            return "rebuild_module_federation_traversal_graph_and_stop_before_next_review"
        if status == "nested_get_init_plan_ready":
            return "review_nested_module_federation_get_init_plan"
        if status == "blocked" and reason:
            return "resolve_module_federation_traversal_workflow_execution_blockers"
        if status == "failed":
            return "inspect_module_federation_traversal_workflow_execution_failure"
        return "review_module_federation_traversal_workflow_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: ModuleFederationTraversalWorkflowExecutionSpec | None = None,
        factory_result: dict[str, Any] | None = None,
        export_plan: dict[str, Any] | None = None,
        export_hook: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        factory_policy = factory_result.get("side_effect_policy") if isinstance(factory_result, dict) and isinstance(factory_result.get("side_effect_policy"), dict) else {}
        hook_policy = export_hook.get("side_effect_policy") if isinstance(export_hook, dict) and isinstance(export_hook.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and (spec.invoke_remote_factory or spec.plan_export_hook or spec.install_export_hook or spec.plan_nested_get_init)),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "container_init_executed": bool(factory_policy.get("container_init_executed") or hook_policy.get("container_init_executed")),
            "remote_get_called": bool(factory_policy.get("remote_get_called") or hook_policy.get("remote_get_called")),
            "remote_factory_invoked": bool(factory_policy.get("remote_factory_invoked") or hook_policy.get("remote_factory_invoked")),
            "remote_code_executed": bool(factory_policy.get("remote_code_executed") or hook_policy.get("remote_code_executed")),
            "export_hook_plan_created": bool(export_plan),
            "export_hook_installed": bool(hook_policy.get("installs_hooks") or (export_hook or {}).get("installed_count")),
            "traversal_graph_rebuilt": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "execute_at_most_one_remote_step_per_review": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalPlanSpec:
    """Review-only follow-up planner after one Module Federation traversal workflow execution."""

    workflow_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    max_recursive_iterations: int = 3

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationRecursiveTraversalPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_recursive_traversal_plan")
            or context.get("moduleFederationRecursiveTraversalPlan")
            or context.get("module-federation-recursive-traversal-plan")
            or context.get("module_federation_traversal_recursion_plan")
            or context.get("moduleFederationTraversalRecursionPlan")
            or context.get("plan_module_federation_recursive_traversal")
            or context.get("planModuleFederationRecursiveTraversal")
            or context.get("federation_recursive_traversal_plan")
            or context.get("federationRecursiveTraversalPlan")
        )
        workflow_execution = _first_dict(
            context,
            "module_federation_traversal_workflow_execution",
            "moduleFederationTraversalWorkflowExecution",
            "module-federation-traversal-workflow-execution",
            "latest_module_federation_traversal_workflow_execution",
            "latestModuleFederationTraversalWorkflowExecution",
            "workflow_execution",
            "workflowExecution",
        )
        if isinstance(workflow_execution.get("execution"), dict):
            workflow_execution = dict(workflow_execution["execution"])
        graph = _first_dict(
            context,
            "latest_module_federation_traversal_graph",
            "latestModuleFederationTraversalGraph",
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(graph.get("graph"), dict):
            graph = dict(graph["graph"])
        workflow_plan = _first_dict(
            context,
            "latest_module_federation_traversal_workflow_plan",
            "latestModuleFederationTraversalWorkflowPlan",
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "traversal_workflow_plan",
            "traversalWorkflowPlan",
        )
        if isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = dict(workflow_plan["workflow_plan"])
        if not workflow_execution and not requested:
            return None
        return cls(
            workflow_execution=workflow_execution,
            latest_traversal_graph=graph,
            latest_workflow_plan=workflow_plan,
            max_recursive_iterations=max(1, int(context.get("max_recursive_iterations", context.get("maxRecursiveIterations", 3)) or 3)),
        )

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalPlanResult:
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

class ModuleFederationRecursiveTraversalPlanManager:
    """Plan the next reviewed recursion checkpoint after one federation traversal step."""

    EXECUTED_STATUSES = {"factory_invoke_success", "export_hook_plan_ready", "export_hook_installed", "nested_get_init_plan_ready"}

    def plan(self, spec: ModuleFederationRecursiveTraversalPlanSpec | None) -> ModuleFederationRecursiveTraversalPlanResult:
        policy = self._side_effect_policy(max_recursive_iterations=spec.max_recursive_iterations if spec else 0)
        if spec is None or not spec.workflow_execution:
            return ModuleFederationRecursiveTraversalPlanResult(status="unsupported", reason="missing_module_federation_traversal_workflow_execution", side_effect_policy=policy)

        execution_status = self._execution_status(spec.workflow_execution)
        graph_status = str(spec.latest_traversal_graph.get("status") or "")
        workflow_status = str(spec.latest_workflow_plan.get("status") or "")
        graph_queue_count = self._count(spec.latest_traversal_graph.get("queue_count"), spec.latest_traversal_graph.get("review_queue"))
        workflow_step_count = self._count(spec.latest_workflow_plan.get("planned_step_count"), spec.latest_workflow_plan.get("planned_steps"))

        if execution_status not in self.EXECUTED_STATUSES:
            status = "blocked"
            reason = "module_federation_workflow_execution_not_ready_for_recursion"
        elif graph_status == "complete" or (spec.latest_traversal_graph and graph_queue_count == 0 and workflow_step_count == 0):
            status = "complete"
            reason = None
        elif spec.latest_traversal_graph and graph_queue_count > 0 and spec.latest_workflow_plan and workflow_step_count > 0:
            status = "ready_for_next_step_review"
            reason = None
        elif spec.latest_traversal_graph and graph_queue_count > 0:
            status = "ready_for_workflow_replan"
            reason = None
        else:
            status = "ready_for_graph_rebuild"
            reason = None

        recursive_plan = {
            "schema_version": "reverse-deepagent.module-federation-recursive-traversal-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "module-federation-recursive-traversal-plan",
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "max_recursive_iterations": spec.max_recursive_iterations,
            "latest_workflow_execution_status": execution_status,
            "latest_workflow_execution_next_action": spec.workflow_execution.get("next_action"),
            "latest_graph_status": graph_status,
            "latest_graph_queue_count": graph_queue_count,
            "latest_workflow_plan_status": workflow_status,
            "latest_workflow_planned_step_count": workflow_step_count,
            "follow_up_steps": self._follow_up_steps(status),
            "blocking_reasons": [reason] if reason else [],
            "artifact_refs": {
                "workflow_execution": "workspace/module-federation-traversal-workflow-execution.json",
                "traversal_graph": "workspace/module-federation-traversal-graph.json",
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json",
                "factory_invoke_result": "workspace/module-federation-factory-invoke-result.json",
                "export_hook_plan": "workspace/module-federation-export-hook-plan.json",
                "export_hook_result": "workspace/module-federation-export-hook-result.json",
                "nested_get_init_plan": "workspace/module-federation-get-init-plan.json",
            },
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason),
        }
        return ModuleFederationRecursiveTraversalPlanResult(status=status, recursive_plan=recursive_plan, side_effect_policy=policy, reason=reason)

    @staticmethod
    def _execution_status(workflow_execution: dict[str, Any]) -> str:
        nested = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else workflow_execution
        return str(nested.get("status") or workflow_execution.get("status") or "")

    @staticmethod
    def _count(explicit_count: Any, items: Any) -> int:
        try:
            return int(explicit_count)
        except (TypeError, ValueError):
            return len(items) if isinstance(items, list) else 0

    @staticmethod
    def _follow_up_steps(status: str) -> list[dict[str, Any]]:
        steps = [
            ("verify_reviewed_module_federation_workflow_execution_checkpoint", "workspace/module-federation-traversal-workflow-execution.json", None),
            ("rebuild_module_federation_traversal_graph_from_execution_evidence", "workspace/module-federation-traversal-workflow-execution.json", "workspace/module-federation-traversal-graph.json"),
            ("replan_module_federation_traversal_workflow_from_refreshed_graph", "workspace/module-federation-traversal-graph.json", "workspace/module-federation-traversal-workflow-plan.json"),
            ("stop_before_next_module_federation_traversal_step_review", "workspace/module-federation-traversal-workflow-plan.json", None),
        ]
        if status == "ready_for_workflow_replan":
            steps = steps[2:]
        elif status == "ready_for_next_step_review":
            steps = steps[3:]
        elif status == "complete":
            steps = [("record_module_federation_recursive_traversal_complete", "workspace/module-federation-traversal-graph.json", None)]
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
            return "resolve_module_federation_recursive_traversal_blockers"
        if status == "complete":
            return "module_federation_recursive_traversal_complete_or_provide_new_candidates"
        if status == "ready_for_next_step_review":
            return "review_next_module_federation_traversal_workflow_step"
        if status == "ready_for_workflow_replan":
            return "replan_module_federation_traversal_workflow_before_next_step"
        return "rebuild_module_federation_traversal_graph_before_next_recursive_step"

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
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "export_hook_installed": False,
            "nested_get_init_planned": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalFollowupSpec:
    """Review-gated follow-through for Module Federation recursive traversal checkpoints."""

    recursive_plan: dict[str, Any] = field(default_factory=dict)
    get_init_plan: dict[str, Any] = field(default_factory=dict)
    get_init_result: dict[str, Any] = field(default_factory=dict)
    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    workflow_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    rebuild_graph: bool = False
    replan_workflow: bool = False
    plan_next_step: bool = False
    review_approved: bool = False
    max_steps: int = 5
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationRecursiveTraversalFollowupSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_recursive_traversal_followup")
            or context.get("moduleFederationRecursiveTraversalFollowup")
            or context.get("module-federation-recursive-traversal-followup")
            or context.get("module_federation_recursive_traversal_checkpoint")
            or context.get("moduleFederationRecursiveTraversalCheckpoint")
            or context.get("module-federation-recursive-traversal-checkpoint")
            or context.get("execute_module_federation_recursive_traversal_followup")
            or context.get("executeModuleFederationRecursiveTraversalFollowup")
        )
        recursive_plan = _first_dict(
            context,
            "module_federation_recursive_traversal_plan",
            "moduleFederationRecursiveTraversalPlan",
            "module-federation-recursive-traversal-plan",
            "recursive_traversal_plan",
            "recursiveTraversalPlan",
        )
        if isinstance(recursive_plan.get("recursive_plan"), dict):
            recursive_plan = dict(recursive_plan["recursive_plan"])
        if not recursive_plan and not requested:
            return None
        graph = _first_dict(
            context,
            "latest_module_federation_traversal_graph",
            "latestModuleFederationTraversalGraph",
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(graph.get("graph"), dict):
            graph = dict(graph["graph"])
        workflow_plan = _first_dict(
            context,
            "latest_module_federation_traversal_workflow_plan",
            "latestModuleFederationTraversalWorkflowPlan",
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "traversal_workflow_plan",
            "traversalWorkflowPlan",
        )
        if isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = dict(workflow_plan["workflow_plan"])
        workflow_execution = _first_dict(
            context,
            "module_federation_traversal_workflow_execution",
            "moduleFederationTraversalWorkflowExecution",
            "module-federation-traversal-workflow-execution",
            "latest_module_federation_traversal_workflow_execution",
            "latestModuleFederationTraversalWorkflowExecution",
            "workflow_execution",
            "workflowExecution",
        )
        if isinstance(workflow_execution.get("execution"), dict):
            workflow_execution = dict(workflow_execution["execution"])
        return cls(
            recursive_plan=recursive_plan,
            get_init_plan=_first_dict(context, "module_federation_get_init_plan", "moduleFederationGetInitPlan", "module-federation-get-init-plan", "get_init_plan", "getInitPlan"),
            get_init_result=_first_dict(context, "module_federation_get_init_result", "moduleFederationGetInitResult", "module-federation-get-init-result", "get_init_result", "getInitResult"),
            factory_invoke_result=_first_dict(context, "module_federation_factory_invoke_result", "moduleFederationFactoryInvokeResult", "module-federation-factory-invoke-result", "factory_invoke_result", "factoryInvokeResult"),
            export_hook_plan=_first_dict(context, "module_federation_export_hook_plan", "moduleFederationExportHookPlan", "module-federation-export-hook-plan", "export_hook_plan", "exportHookPlan"),
            workflow_execution=workflow_execution,
            latest_traversal_graph=graph,
            latest_workflow_plan=workflow_plan,
            rebuild_graph=bool(context.get("rebuild_graph") or context.get("rebuildGraph") or context.get("rebuild_traversal_graph") or context.get("rebuildTraversalGraph")),
            replan_workflow=bool(context.get("replan_workflow") or context.get("replanWorkflow") or context.get("replan_traversal_workflow") or context.get("replanTraversalWorkflow")),
            plan_next_step=bool(context.get("plan_next_step") or context.get("planNextStep") or context.get("plan_next_traversal_step") or context.get("planNextTraversalStep")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            max_steps=max(1, int(context.get("max_steps", context.get("maxSteps", 5)) or 5)),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalFollowupResult:
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

class ModuleFederationRecursiveTraversalFollowupManager:
    """Advance one reviewed federation recursion checkpoint without executing remote code."""

    def follow_up(self, spec: ModuleFederationRecursiveTraversalFollowupSpec | None) -> ModuleFederationRecursiveTraversalFollowupResult:
        if spec is None or not spec.recursive_plan:
            return ModuleFederationRecursiveTraversalFollowupResult(status="unsupported", reason="missing_module_federation_recursive_traversal_plan", side_effect_policy=self._side_effect_policy())

        stages: list[dict[str, Any]] = [self._stage("select_module_federation_recursive_checkpoint", "selected", "", side_effect=False)]
        graph_result_payload: dict[str, Any] = {}
        workflow_result_payload: dict[str, Any] = {}
        next_step_review_payload: dict[str, Any] = {}
        graph = dict(spec.latest_traversal_graph)
        workflow_plan = dict(spec.latest_workflow_plan)

        if spec.rebuild_graph:
            if not spec.review_approved:
                stages.append(self._stage("rebuild_traversal_graph", "blocked", "review_approval_required", side_effect=False))
            elif not any((spec.get_init_plan, spec.get_init_result, spec.factory_invoke_result, spec.export_hook_plan, spec.latest_traversal_graph)):
                stages.append(self._stage("rebuild_traversal_graph", "blocked", "missing_module_federation_traversal_evidence", side_effect=False))
            else:
                graph_result = ModuleFederationTraversalGraphManager().build(
                    ModuleFederationTraversalGraphSpec(
                        get_init_plan=spec.get_init_plan,
                        get_init_result=spec.get_init_result,
                        factory_invoke_result=spec.factory_invoke_result,
                        export_hook_plan=spec.export_hook_plan,
                        previous_graph=spec.latest_traversal_graph,
                        max_queue_size=spec.max_queue_size,
                        max_preview_length=spec.max_preview_length,
                    )
                )
                graph_result_payload = graph_result.to_dict()
                graph = graph_result.graph
                stages.append(self._stage("rebuild_traversal_graph", graph_result.status, graph_result.reason, side_effect=False))
        else:
            stages.append(self._stage("rebuild_traversal_graph", "pending", "", side_effect=False))

        if spec.replan_workflow:
            if not spec.review_approved:
                stages.append(self._stage("replan_traversal_workflow", "blocked", "review_approval_required", side_effect=False))
            elif not graph:
                stages.append(self._stage("replan_traversal_workflow", "blocked", "module_federation_traversal_graph_required", side_effect=False))
            else:
                workflow_result = ModuleFederationTraversalWorkflowPlanManager().plan(
                    ModuleFederationTraversalWorkflowPlanSpec(traversal_graph=graph, max_steps=spec.max_steps)
                )
                workflow_result_payload = workflow_result.to_dict()
                workflow_plan = workflow_result.workflow_plan
                stages.append(self._stage("replan_traversal_workflow", workflow_result.status, workflow_result.reason, side_effect=False))
        else:
            stages.append(self._stage("replan_traversal_workflow", "pending", "", side_effect=False))

        if spec.plan_next_step:
            if not spec.review_approved:
                stages.append(self._stage("plan_next_traversal_step_review", "blocked", "review_approval_required", side_effect=False))
            elif not workflow_plan:
                stages.append(self._stage("plan_next_traversal_step_review", "blocked", "module_federation_traversal_workflow_plan_required", side_effect=False))
            else:
                next_step_review_payload = self._next_step_review_payload(workflow_plan=workflow_plan, workflow_execution=spec.workflow_execution)
                stages.append(self._stage("plan_next_traversal_step_review", next_step_review_payload["status"], next_step_review_payload.get("reason"), side_effect=False))
        else:
            stages.append(self._stage("plan_next_traversal_step_review", "pending", "", side_effect=False))

        stages.append(self._stage("stop_before_next_module_federation_traversal_workflow_execution", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, next_step_review_payload, workflow_result_payload, graph_result_payload)
        reason = self._reason(stages)
        followup = {
            "schema_version": "reverse-deepagent.module-federation-recursive-traversal-followup.v1",
            "status": status,
            "reason": reason,
            "recursive_plan_id": spec.recursive_plan.get("plan_id"),
            "review_approved": spec.review_approved,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "stages": stages,
            "module_federation_traversal_graph": graph_result_payload,
            "module_federation_traversal_workflow_plan": workflow_result_payload,
            "module_federation_next_step_review": next_step_review_payload,
            "artifact_refs": {
                "recursive_plan": "workspace/module-federation-recursive-traversal-plan.json",
                "traversal_graph": "workspace/module-federation-traversal-graph.json" if graph_result_payload else "",
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json" if workflow_result_payload else "",
                "next_step_execution": "workspace/module-federation-traversal-workflow-execution.json" if next_step_review_payload else "",
            },
            "next_action": self._next_action(status, reason),
        }
        return ModuleFederationRecursiveTraversalFollowupResult(status=status, followup=followup, side_effect_policy=self._side_effect_policy(spec=spec, stages=stages), reason=reason)

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @staticmethod
    def _next_step_review_payload(*, workflow_plan: dict[str, Any], workflow_execution: dict[str, Any]) -> dict[str, Any]:
        steps = _list_dicts(workflow_plan.get("planned_steps"))
        selected_step = steps[0] if steps else {}
        status = "ready_for_review" if selected_step else "complete"
        return {
            "schema_version": "reverse-deepagent.module-federation-next-step-review.v1",
            "status": status,
            "reason": None,
            "review_required": bool(selected_step),
            "manual_checkpoint_required": True,
            "planned_step_count": len(steps),
            "selected_step_index": selected_step.get("step_index") if selected_step else None,
            "selected_step": selected_step,
            "previous_workflow_execution_status": ModuleFederationRecursiveTraversalPlanManager._execution_status(workflow_execution) if workflow_execution else "",
            "side_effect_policy": {
                "plan_only": True,
                "review_required": True,
                "remote_factory_invoked": False,
                "remote_code_executed": False,
                "export_hook_installed": False,
                "automatic_queue_advance": False,
                "recursive_federation_traversal": False,
            },
            "next_action": "review_next_module_federation_traversal_workflow_execution" if selected_step else "module_federation_recursive_traversal_complete_or_provide_new_candidates",
        }

    @staticmethod
    def _status(
        stages: list[dict[str, Any]],
        next_step_review: dict[str, Any],
        workflow_result: dict[str, Any],
        graph_result: dict[str, Any],
    ) -> str:
        if any(stage["status"] in {"failed", "error"} for stage in stages):
            return "failed"
        if any(stage["status"] in {"blocked", "unsupported"} for stage in stages):
            return "blocked"
        if next_step_review:
            return "next_step_review_ready" if next_step_review.get("status") == "ready_for_review" else "complete"
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
        if status == "next_step_review_ready":
            return "review_next_module_federation_traversal_workflow_execution"
        if status == "workflow_replanned":
            return "plan_next_module_federation_traversal_step_review"
        if status == "graph_rebuilt":
            return "replan_module_federation_traversal_workflow_before_next_step"
        if status == "complete":
            return "module_federation_recursive_traversal_complete_or_provide_new_candidates"
        if status == "blocked" and reason:
            return "resolve_module_federation_recursive_traversal_followup_blockers"
        if status == "failed":
            return "inspect_module_federation_recursive_traversal_followup_failure"
        return "review_module_federation_recursive_traversal_followup_plan"

    @staticmethod
    def _side_effect_policy(
        spec: ModuleFederationRecursiveTraversalFollowupSpec | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stages = stages or []
        return {
            "plan_only_by_default": not bool(spec and any((spec.rebuild_graph, spec.replan_workflow, spec.plan_next_step))),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "traversal_graph_rebuilt": any(stage["stage"] == "rebuild_traversal_graph" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "workflow_replanned": any(stage["stage"] == "replan_traversal_workflow" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "next_step_review_planned": any(stage["stage"] == "plan_next_traversal_step_review" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "container_init_executed": False,
            "remote_get_called": False,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "export_hook_installed": False,
            "workflow_executed": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalExecutionSpec:
    """Review-gated execution of one next-step checkpoint from a federation recursion follow-up."""

    recursive_followup: dict[str, Any] = field(default_factory=dict)
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    traversal_graph: dict[str, Any] = field(default_factory=dict)
    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    export_hook_result: dict[str, Any] = field(default_factory=dict)
    selected_step_index: int | None = None
    candidate_index: int | None = None
    invoke_remote_factory: bool = False
    plan_export_hook: bool = False
    install_export_hook: bool = False
    plan_nested_get_init: bool = False
    review_approved: bool = False
    share_scope_path: str = "window.__webpack_share_scopes__.default"
    capture_args: bool = True
    capture_result: bool = True
    max_preview_length: int = 240
    trigger_expression: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationRecursiveTraversalExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_recursive_traversal_execution")
            or context.get("moduleFederationRecursiveTraversalExecution")
            or context.get("module-federation-recursive-traversal-execution")
            or context.get("execute_module_federation_recursive_traversal")
            or context.get("executeModuleFederationRecursiveTraversal")
            or context.get("execute_module_federation_recursive_traversal_next_step")
            or context.get("executeModuleFederationRecursiveTraversalNextStep")
        )
        followup = (
            context.get("module_federation_recursive_traversal_followup")
            or context.get("moduleFederationRecursiveTraversalFollowup")
            or context.get("module-federation-recursive-traversal-followup")
            or context.get("recursive_traversal_followup")
            or context.get("recursiveTraversalFollowup")
        )
        if isinstance(followup, dict) and isinstance(followup.get("followup"), dict):
            followup = followup["followup"]
        workflow_plan = _first_dict(
            context,
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "latest_module_federation_traversal_workflow_plan",
            "latestModuleFederationTraversalWorkflowPlan",
            "traversal_workflow_plan",
            "traversalWorkflowPlan",
        )
        if isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = dict(workflow_plan["workflow_plan"])
        if not workflow_plan and isinstance(followup, dict):
            workflow_result = followup.get("module_federation_traversal_workflow_plan")
            if isinstance(workflow_result, dict) and isinstance(workflow_result.get("workflow_plan"), dict):
                workflow_plan = dict(workflow_result["workflow_plan"])
            elif isinstance(followup.get("latest_workflow_plan"), dict):
                workflow_plan = dict(followup["latest_workflow_plan"])
        if not workflow_plan and not requested:
            return None
        traversal_graph = _first_dict(
            context,
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "latest_module_federation_traversal_graph",
            "latestModuleFederationTraversalGraph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(traversal_graph.get("graph"), dict):
            traversal_graph = dict(traversal_graph["graph"])
        if not traversal_graph and isinstance(followup, dict):
            graph_result = followup.get("module_federation_traversal_graph")
            if isinstance(graph_result, dict) and isinstance(graph_result.get("graph"), dict):
                traversal_graph = dict(graph_result["graph"])
        return cls(
            recursive_followup=dict(followup) if isinstance(followup, dict) else {},
            workflow_plan=workflow_plan,
            traversal_graph=traversal_graph,
            factory_invoke_result=_first_dict(context, "module_federation_factory_invoke_result", "moduleFederationFactoryInvokeResult", "module-federation-factory-invoke-result", "factory_invoke_result", "factoryInvokeResult"),
            export_hook_plan=_first_dict(context, "module_federation_export_hook_plan", "moduleFederationExportHookPlan", "module-federation-export-hook-plan", "export_hook_plan", "exportHookPlan"),
            export_hook_result=_first_dict(context, "module_federation_export_hook_result", "moduleFederationExportHookResult", "module-federation-export-hook-result", "remote_export_hook_result", "remoteExportHookResult"),
            selected_step_index=ModuleFederationTraversalWorkflowExecutionSpec._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=ModuleFederationTraversalWorkflowExecutionSpec._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
            invoke_remote_factory=bool(context.get("invoke_remote_factory") or context.get("invokeRemoteFactory") or context.get("execute_remote_factory") or context.get("executeRemoteFactory") or context.get("execute_module_federation_factory") or context.get("executeModuleFederationFactory") or context.get("invoke_module_federation_factory") or context.get("invokeModuleFederationFactory")),
            plan_export_hook=bool(context.get("plan_export_hook") or context.get("planExportHook") or context.get("plan_module_federation_export_hook") or context.get("planModuleFederationExportHook")),
            install_export_hook=bool(context.get("install_export_hook") or context.get("installExportHook") or context.get("install_module_federation_export_hook") or context.get("installModuleFederationExportHook") or context.get("hook_remote_export") or context.get("hookRemoteExport")),
            plan_nested_get_init=bool(context.get("plan_nested_get_init") or context.get("planNestedGetInit") or context.get("plan_nested_federation_get_init") or context.get("planNestedFederationGetInit")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            share_scope_path=str(context.get("share_scope_path", context.get("shareScopePath", "window.__webpack_share_scopes__.default")) or "window.__webpack_share_scopes__.default").strip(),
            capture_args=bool(context.get("capture_args", context.get("captureArgs", True))),
            capture_result=bool(context.get("capture_result", context.get("captureResult", True))),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
        )

@dataclass(slots=True)
class ModuleFederationRecursiveTraversalExecutionResult:
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

class ModuleFederationRecursiveTraversalExecutionManager:
    """Execute one reviewed federation next-step checkpoint and stop before deeper recursion."""

    def execute(self, page: BrowserPage, spec: ModuleFederationRecursiveTraversalExecutionSpec | None) -> ModuleFederationRecursiveTraversalExecutionResult:
        if spec is None or not spec.workflow_plan:
            return ModuleFederationRecursiveTraversalExecutionResult(status="unsupported", reason="missing_module_federation_traversal_workflow_plan", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = [self._stage("select_module_federation_recursive_next_step_checkpoint", "selected", "", side_effect=False)]
        workflow_execution_payload: dict[str, Any] = {}
        if self._has_execution_flags(spec) and not spec.review_approved:
            stages.append(self._stage("execute_next_module_federation_traversal_workflow_step", "blocked", "review_approval_required", side_effect=True))
        else:
            workflow_result = ModuleFederationTraversalWorkflowExecutionManager().execute(
                page,
                ModuleFederationTraversalWorkflowExecutionSpec(
                    workflow_plan=spec.workflow_plan,
                    traversal_graph=spec.traversal_graph,
                    factory_invoke_result=spec.factory_invoke_result,
                    export_hook_plan=spec.export_hook_plan,
                    export_hook_result=spec.export_hook_result,
                    selected_step_index=spec.selected_step_index,
                    candidate_index=spec.candidate_index,
                    invoke_remote_factory=spec.invoke_remote_factory,
                    plan_export_hook=spec.plan_export_hook,
                    install_export_hook=spec.install_export_hook,
                    plan_nested_get_init=spec.plan_nested_get_init,
                    review_approved=spec.review_approved,
                    share_scope_path=spec.share_scope_path,
                    capture_args=spec.capture_args,
                    capture_result=spec.capture_result,
                    max_preview_length=spec.max_preview_length,
                    trigger_expression=spec.trigger_expression,
                ),
            )
            workflow_execution_payload = workflow_result.to_dict()
            stages.append(self._stage("execute_next_module_federation_traversal_workflow_step", workflow_result.status, workflow_result.reason, side_effect=self._has_execution_flags(spec)))
        stages.append(self._stage("stop_before_next_module_federation_recursive_followup_checkpoint", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, workflow_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, workflow_execution_payload, stages, status=status, reason=reason)
        return ModuleFederationRecursiveTraversalExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, workflow_execution=workflow_execution_payload, stages=stages), reason=reason)

    @staticmethod
    def _has_execution_flags(spec: ModuleFederationRecursiveTraversalExecutionSpec) -> bool:
        return any((spec.invoke_remote_factory, spec.plan_export_hook, spec.install_export_hook, spec.plan_nested_get_init))

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], workflow_execution: dict[str, Any]) -> str:
        if any(stage["status"] in {"failed", "failure", "error"} for stage in stages):
            return "failed"
        if any(stage["status"] in {"blocked", "unsupported"} for stage in stages):
            return "blocked"
        nested_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        nested_status = str(workflow_execution.get("status") or nested_execution.get("status") or "")
        if nested_status == "export_hook_installed":
            return "next_step_export_hook_installed"
        if nested_status == "export_hook_plan_ready":
            return "next_step_export_hook_plan_ready"
        if nested_status in {"factory_invoke_success", "nested_get_init_plan_ready"}:
            return "next_step_execution_progressed"
        return "ready_for_review"

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for stage in stages:
            if stage["status"] in {"blocked", "failed", "failure", "error", "unsupported"} and stage.get("reason"):
                return str(stage["reason"])
        return None

    @classmethod
    def _execution_payload(
        cls,
        spec: ModuleFederationRecursiveTraversalExecutionSpec,
        workflow_execution: dict[str, Any],
        stages: list[dict[str, Any]],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        nested_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.module-federation-recursive-traversal-execution.v1",
            "status": status,
            "reason": reason,
            "source_recursive_followup_status": spec.recursive_followup.get("status"),
            "source_recursive_followup_next_action": spec.recursive_followup.get("next_action"),
            "workflow_plan_id": spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.workflow_plan.get("source_graph_id"),
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "execute_at_most_one_remote_step_per_review": True,
            "stages": stages,
            "module_federation_traversal_workflow_execution": workflow_execution,
            "workflow_execution_status": workflow_execution.get("status") or nested_execution.get("status"),
            "selected_step_index": nested_execution.get("selected_step_index"),
            "selected_node_id": nested_execution.get("selected_node_id"),
            "selected_action": nested_execution.get("selected_action"),
            "artifact_refs": {
                "recursive_followup": "workspace/module-federation-recursive-traversal-followup.json",
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json",
                "workflow_execution": "workspace/module-federation-traversal-workflow-execution.json" if workflow_execution else "",
                "next_recursive_plan": "workspace/module-federation-recursive-traversal-plan.json",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "next_step_export_hook_installed":
            return "plan_next_module_federation_recursive_traversal_checkpoint"
        if status in {"next_step_execution_progressed", "next_step_export_hook_plan_ready"}:
            return "continue_reviewed_module_federation_traversal_step_or_plan_next_checkpoint"
        if status == "blocked" and reason:
            return "resolve_module_federation_recursive_traversal_execution_blockers"
        if status == "failed":
            return "inspect_module_federation_recursive_traversal_execution_failure"
        return "review_module_federation_recursive_traversal_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: ModuleFederationRecursiveTraversalExecutionSpec | None = None,
        workflow_execution: dict[str, Any] | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stages = stages or []
        nested_policy = workflow_execution.get("side_effect_policy") if isinstance(workflow_execution, dict) and isinstance(workflow_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and ModuleFederationRecursiveTraversalExecutionManager._has_execution_flags(spec)),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "workflow_execution_planned": bool(workflow_execution),
            "workflow_execution_started": any(stage["stage"] == "execute_next_module_federation_traversal_workflow_step" and stage["side_effect"] and stage["status"] not in {"pending", "blocked"} for stage in stages),
            "container_init_executed": bool(nested_policy.get("container_init_executed", False)),
            "remote_get_called": bool(nested_policy.get("remote_get_called", False)),
            "remote_factory_invoked": bool(nested_policy.get("remote_factory_invoked", False)),
            "remote_code_executed": bool(nested_policy.get("remote_code_executed", False)),
            "export_hook_plan_created": bool(nested_policy.get("export_hook_plan_created", False)),
            "export_hook_installed": bool(nested_policy.get("export_hook_installed", False)),
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "execute_at_most_one_remote_step_per_review": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationRecursiveContinuationJournalSpec:
    """Review-gated continuation journal for recursive Module Federation traversal steps."""

    recursive_execution: dict[str, Any] = field(default_factory=dict)
    existing_journal: dict[str, Any] = field(default_factory=dict)
    recursive_followup: dict[str, Any] = field(default_factory=dict)
    recursive_plan: dict[str, Any] = field(default_factory=dict)
    traversal_graph: dict[str, Any] = field(default_factory=dict)
    workflow_plan: dict[str, Any] = field(default_factory=dict)
    review_approved: bool = False
    write_journal: bool = False
    reviewer: str = ""
    journal_id: str = "module-federation-recursive-continuation-journal"
    max_iterations: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationRecursiveContinuationJournalSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_recursive_continuation_journal")
            or context.get("moduleFederationRecursiveContinuationJournal")
            or context.get("module-federation-recursive-continuation-journal")
            or context.get("module_federation_recursive_traversal_continuation_journal")
            or context.get("moduleFederationRecursiveTraversalContinuationJournal")
            or context.get("module-federation-recursive-traversal-continuation-journal")
            or context.get("append_module_federation_recursive_continuation_journal")
            or context.get("appendModuleFederationRecursiveContinuationJournal")
        )
        recursive_execution = _first_dict(
            context,
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "latest_module_federation_recursive_traversal_execution",
            "latestModuleFederationRecursiveTraversalExecution",
            "recursive_traversal_execution",
            "recursiveTraversalExecution",
        )
        if not recursive_execution and not requested:
            return None
        existing_journal = _first_dict(
            context,
            "module_federation_recursive_continuation_journal",
            "moduleFederationRecursiveContinuationJournal",
            "module-federation-recursive-continuation-journal",
            "module_federation_recursive_traversal_continuation_journal",
            "moduleFederationRecursiveTraversalContinuationJournal",
            "module-federation-recursive-traversal-continuation-journal",
            "existing_module_federation_recursive_continuation_journal",
            "existingModuleFederationRecursiveContinuationJournal",
        )
        if isinstance(existing_journal.get("journal"), dict):
            existing_journal = dict(existing_journal["journal"])
        return cls(
            recursive_execution=recursive_execution,
            existing_journal=existing_journal,
            recursive_followup=_first_dict(context, "module_federation_recursive_traversal_followup", "moduleFederationRecursiveTraversalFollowup", "module-federation-recursive-traversal-followup"),
            recursive_plan=_first_dict(context, "module_federation_recursive_traversal_plan", "moduleFederationRecursiveTraversalPlan", "module-federation-recursive-traversal-plan"),
            traversal_graph=_first_dict(context, "module_federation_traversal_graph", "moduleFederationTraversalGraph", "module-federation-traversal-graph"),
            workflow_plan=_first_dict(context, "module_federation_traversal_workflow_plan", "moduleFederationTraversalWorkflowPlan", "module-federation-traversal-workflow-plan"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            write_journal=bool(
                context.get("write_journal")
                or context.get("writeJournal")
                or context.get("append_journal")
                or context.get("appendJournal")
                or context.get("append_module_federation_recursive_continuation_journal")
                or context.get("appendModuleFederationRecursiveContinuationJournal")
            ),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip(),
            journal_id=str(context.get("journal_id") or context.get("journalId") or "module-federation-recursive-continuation-journal").strip() or "module-federation-recursive-continuation-journal",
            max_iterations=max(1, int(context.get("max_iterations", context.get("maxIterations", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

@dataclass(slots=True)
class ModuleFederationRecursiveContinuationJournalResult:
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

class ModuleFederationRecursiveContinuationJournalManager:
    """Plan or append a reviewed federation recursion continuation journal without executing remotes."""

    JOURNALABLE_STATUSES = {"next_step_execution_progressed", "next_step_export_hook_plan_ready", "next_step_export_hook_installed"}

    def plan_or_append(self, spec: ModuleFederationRecursiveContinuationJournalSpec | None) -> ModuleFederationRecursiveContinuationJournalResult:
        policy = self._side_effect_policy(write_journal=False, review_approved=bool(spec and spec.review_approved))
        if spec is None or not spec.recursive_execution:
            return ModuleFederationRecursiveContinuationJournalResult(status="unsupported", reason="missing_module_federation_recursive_traversal_execution", side_effect_policy=policy)
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
        side_effect_policy = self._side_effect_policy(write_journal=status == "journal_appended", review_approved=spec.review_approved)
        journal = {
            "schema_version": "reverse-deepagent.module-federation-recursive-continuation-journal.v1",
            "journal_id": spec.journal_id,
            "status": status,
            "append_only": True,
            "review_required": True,
            "review_approved": bool(spec.review_approved),
            "write_requested": bool(spec.write_journal),
            "writes_journal_now": status == "journal_appended",
            "record_count": len(journal_records),
            "existing_record_count": len(existing_records),
            "max_iterations": spec.max_iterations,
            "remaining_iteration_budget": max(0, spec.max_iterations - len(journal_records)),
            "blocking_reasons": blockers,
            "pending_entry": entry if status != "journal_appended" else {},
            "records": journal_records,
            "next_checkpoint_plan": self._next_checkpoint_plan(status=status, spec=spec, entry=entry, record_count=len(journal_records)),
            "artifact_refs": {
                "recursive_execution": "workspace/module-federation-recursive-traversal-execution.json",
                "recursive_followup": "workspace/module-federation-recursive-traversal-followup.json" if spec.recursive_followup else "",
                "recursive_plan": "workspace/module-federation-recursive-traversal-plan.json" if spec.recursive_plan else "",
                "traversal_graph": "workspace/module-federation-traversal-graph.json" if spec.traversal_graph else "",
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json" if spec.workflow_plan else "",
                "continuation_journal": "workspace/module-federation-recursive-continuation-journal.json",
                "next_recursive_plan": "workspace/module-federation-recursive-traversal-plan.json",
                "next_recursive_followup": "workspace/module-federation-recursive-traversal-followup.json",
                "next_recursive_execution": "workspace/module-federation-recursive-traversal-execution.json",
            },
            "side_effect_policy": side_effect_policy,
            "next_action": self._next_action(status=status, blockers=blockers),
        }
        reason = blockers[0] if blockers else None
        return ModuleFederationRecursiveContinuationJournalResult(status=status, journal=journal, entry=entry, side_effect_policy=side_effect_policy, reason=reason)

    @classmethod
    def _entry(cls, spec: ModuleFederationRecursiveContinuationJournalSpec, *, existing_record_count: int) -> dict[str, Any]:
        recursive_execution = spec.recursive_execution
        execution = recursive_execution.get("execution") if isinstance(recursive_execution.get("execution"), dict) else recursive_execution
        workflow_execution = execution.get("module_federation_traversal_workflow_execution") if isinstance(execution.get("module_federation_traversal_workflow_execution"), dict) else {}
        workflow_nested = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        policy = recursive_execution.get("side_effect_policy") if isinstance(recursive_execution.get("side_effect_policy"), dict) else {}
        workflow_policy = workflow_execution.get("side_effect_policy") if isinstance(workflow_execution.get("side_effect_policy"), dict) else {}
        status = str(recursive_execution.get("status") or execution.get("status") or "")
        workflow_status = str(execution.get("workflow_execution_status") or workflow_execution.get("status") or workflow_nested.get("status") or "")
        selected_step_index = execution.get("selected_step_index", workflow_nested.get("selected_step_index"))
        selected_node_id = _clip(execution.get("selected_node_id", workflow_nested.get("selected_node_id")), spec.max_preview_length)
        selected_action = _clip(execution.get("selected_action", workflow_nested.get("selected_action")), spec.max_preview_length)
        workflow_plan_id = _clip(execution.get("workflow_plan_id", workflow_nested.get("workflow_plan_id")), spec.max_preview_length)
        fingerprint = "|".join(str(part) for part in (workflow_plan_id, selected_step_index, selected_node_id, selected_action, workflow_status) if part not in (None, ""))
        entry_id = f"{spec.journal_id}:{existing_record_count + 1}:{fingerprint or 'missing'}"
        return {
            "schema_version": "reverse-deepagent.module-federation-recursive-continuation-journal-entry.v1",
            "entry_id": entry_id,
            "sequence": existing_record_count + 1,
            "execution_fingerprint": fingerprint,
            "recursive_execution_status": status,
            "workflow_execution_status": workflow_status,
            "workflow_plan_id": workflow_plan_id,
            "selected_step_index": selected_step_index,
            "selected_node_id": selected_node_id,
            "selected_action": selected_action,
            "reviewer": spec.reviewer,
            "review_approved": bool(spec.review_approved),
            "artifact_status": {
                "recursive_execution_recorded": bool(spec.recursive_execution),
                "recursive_followup_recorded": bool(spec.recursive_followup),
                "recursive_plan_recorded": bool(spec.recursive_plan),
                "traversal_graph_recorded": bool(spec.traversal_graph),
                "workflow_plan_recorded": bool(spec.workflow_plan),
                "remote_factory_invoked_in_source_execution": bool(policy.get("remote_factory_invoked") or workflow_policy.get("remote_factory_invoked")),
                "remote_code_executed_in_source_execution": bool(policy.get("remote_code_executed") or workflow_policy.get("remote_code_executed")),
                "export_hook_installed_in_source_execution": bool(policy.get("export_hook_installed") or workflow_policy.get("export_hook_installed")),
            },
            "side_effect_policy": {
                "records_journal_entry": True,
                "container_init_executed_by_journal": False,
                "remote_get_called_by_journal": False,
                "remote_factory_invoked_by_journal": False,
                "remote_code_executed_by_journal": False,
                "export_hook_installed_by_journal": False,
                "traversal_graph_rebuilt_by_journal": False,
                "workflow_replanned_by_journal": False,
                "automatic_queue_advance": False,
                "recursive_federation_traversal": False,
            },
        }

    @staticmethod
    def _existing_records(journal: dict[str, Any]) -> list[dict[str, Any]]:
        records = journal.get("records") if isinstance(journal, dict) else []
        if isinstance(records, list):
            return [dict(item) for item in records if isinstance(item, dict)]
        return []

    @classmethod
    def _blocking_reasons(cls, spec: ModuleFederationRecursiveContinuationJournalSpec, entry: dict[str, Any], existing_records: list[dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        status = str(entry.get("recursive_execution_status") or "")
        if status not in cls.JOURNALABLE_STATUSES:
            blockers.append("module_federation_recursive_execution_not_journalable")
        if len(existing_records) >= spec.max_iterations:
            blockers.append("module_federation_recursive_continuation_iteration_budget_exhausted")
        if not spec.write_journal:
            return blockers
        if not spec.review_approved:
            blockers.append("review_approval_required")
        fingerprint = entry.get("execution_fingerprint")
        if fingerprint and any(record.get("execution_fingerprint") == fingerprint for record in existing_records):
            blockers.append("module_federation_recursive_continuation_duplicate_entry")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _next_checkpoint_plan(*, status: str, spec: ModuleFederationRecursiveContinuationJournalSpec, entry: dict[str, Any], record_count: int) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.module-federation-recursive-continuation-checkpoint-plan.v1",
            "status": "ready_for_review" if status in {"ready_for_review", "journal_appended"} else status,
            "review_required": True,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "current_iteration": record_count + (0 if status == "journal_appended" else 1),
            "max_iterations": spec.max_iterations,
            "selected_node_id": entry.get("selected_node_id"),
            "selected_action": entry.get("selected_action"),
            "steps": [
                {"step": "verify_latest_module_federation_recursive_execution", "input_artifact": "workspace/module-federation-recursive-traversal-execution.json", "side_effect": False},
                {"step": "append_reviewed_recursive_continuation_journal_entry", "input_artifact": "workspace/module-federation-recursive-continuation-journal.json", "output_artifact": "workspace/module-federation-recursive-continuation-journal.json", "side_effect": status == "journal_appended"},
                {"step": "rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence", "input_artifact": "workspace/module-federation-recursive-continuation-journal.json", "output_artifact": "workspace/module-federation-traversal-graph.json", "side_effect": False},
                {"step": "replan_module_federation_traversal_workflow_from_refreshed_graph", "input_artifact": "workspace/module-federation-traversal-graph.json", "output_artifact": "workspace/module-federation-traversal-workflow-plan.json", "side_effect": False},
                {"step": "review_next_module_federation_recursive_traversal_execution", "input_artifact": "workspace/module-federation-traversal-workflow-plan.json", "output_artifact": "workspace/module-federation-recursive-traversal-execution.json", "side_effect": False},
            ],
            "stops_before": ["automatic_graph_rebuild", "automatic_workflow_replan", "automatic_queue_advance", "recursive_remote_execution", "mcp_call", "mobile_runtime_chain"],
        }

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if status == "journal_appended":
            return "plan_next_module_federation_recursive_checkpoint_from_journal"
        if "review_approval_required" in blockers:
            return "approve_module_federation_recursive_continuation_journal_append"
        if blockers:
            return "revise_module_federation_recursive_continuation_journal_inputs"
        return "review_module_federation_recursive_continuation_journal_append"

    @staticmethod
    def _side_effect_policy(*, write_journal: bool, review_approved: bool) -> dict[str, Any]:
        return {
            "plan_only": not write_journal,
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": review_approved,
            "writes_journal": write_journal,
            "container_init_executed_by_journal": False,
            "remote_get_called_by_journal": False,
            "remote_factory_invoked_by_journal": False,
            "remote_code_executed_by_journal": False,
            "export_hook_installed_by_journal": False,
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class ModuleFederationRecursiveContinuationCheckpointSpec:
    """Review-gated checkpoint execution from a federation recursive continuation journal."""

    continuation_journal: dict[str, Any] = field(default_factory=dict)
    recursive_execution: dict[str, Any] = field(default_factory=dict)
    recursive_followup: dict[str, Any] = field(default_factory=dict)
    recursive_plan: dict[str, Any] = field(default_factory=dict)
    get_init_plan: dict[str, Any] = field(default_factory=dict)
    get_init_result: dict[str, Any] = field(default_factory=dict)
    factory_invoke_result: dict[str, Any] = field(default_factory=dict)
    export_hook_plan: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    verify_execution: bool = False
    rebuild_graph: bool = False
    replan_workflow: bool = False
    plan_next_execution_review: bool = False
    review_approved: bool = False
    max_steps: int = 5
    max_queue_size: int = 20
    max_preview_length: int = 240

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ModuleFederationRecursiveContinuationCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("module_federation_recursive_continuation_checkpoint")
            or context.get("moduleFederationRecursiveContinuationCheckpoint")
            or context.get("module-federation-recursive-continuation-checkpoint")
            or context.get("module_federation_recursive_traversal_continuation_checkpoint")
            or context.get("moduleFederationRecursiveTraversalContinuationCheckpoint")
            or context.get("module-federation-recursive-traversal-continuation-checkpoint")
            or context.get("execute_module_federation_recursive_continuation_checkpoint")
            or context.get("executeModuleFederationRecursiveContinuationCheckpoint")
            or context.get("reviewed_module_federation_recursive_continuation_checkpoint")
            or context.get("reviewedModuleFederationRecursiveContinuationCheckpoint")
        )
        continuation_journal = _first_dict(
            context,
            "module_federation_recursive_continuation_journal",
            "moduleFederationRecursiveContinuationJournal",
            "module-federation-recursive-continuation-journal",
            "module_federation_recursive_traversal_continuation_journal",
            "moduleFederationRecursiveTraversalContinuationJournal",
            "module-federation-recursive-traversal-continuation-journal",
            "existing_module_federation_recursive_continuation_journal",
            "existingModuleFederationRecursiveContinuationJournal",
        )
        if isinstance(continuation_journal.get("journal"), dict):
            continuation_journal = dict(continuation_journal["journal"])
        if not continuation_journal and not requested:
            return None
        recursive_execution = _first_dict(
            context,
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "latest_module_federation_recursive_traversal_execution",
            "latestModuleFederationRecursiveTraversalExecution",
            "recursive_traversal_execution",
            "recursiveTraversalExecution",
        )
        if isinstance(recursive_execution.get("execution"), dict):
            recursive_execution = dict(recursive_execution["execution"])
        graph = _first_dict(
            context,
            "latest_module_federation_traversal_graph",
            "latestModuleFederationTraversalGraph",
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "traversal_graph",
            "traversalGraph",
        )
        if isinstance(graph.get("graph"), dict):
            graph = dict(graph["graph"])
        workflow_plan = _first_dict(
            context,
            "latest_module_federation_traversal_workflow_plan",
            "latestModuleFederationTraversalWorkflowPlan",
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "traversal_workflow_plan",
            "traversalWorkflowPlan",
        )
        if isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = dict(workflow_plan["workflow_plan"])
        return cls(
            continuation_journal=continuation_journal,
            recursive_execution=recursive_execution,
            recursive_followup=_first_dict(context, "module_federation_recursive_traversal_followup", "moduleFederationRecursiveTraversalFollowup", "module-federation-recursive-traversal-followup"),
            recursive_plan=_first_dict(context, "module_federation_recursive_traversal_plan", "moduleFederationRecursiveTraversalPlan", "module-federation-recursive-traversal-plan"),
            get_init_plan=_first_dict(context, "module_federation_get_init_plan", "moduleFederationGetInitPlan", "module-federation-get-init-plan", "get_init_plan", "getInitPlan"),
            get_init_result=_first_dict(context, "module_federation_get_init_result", "moduleFederationGetInitResult", "module-federation-get-init-result", "get_init_result", "getInitResult"),
            factory_invoke_result=_first_dict(context, "module_federation_factory_invoke_result", "moduleFederationFactoryInvokeResult", "module-federation-factory-invoke-result", "factory_invoke_result", "factoryInvokeResult"),
            export_hook_plan=_first_dict(context, "module_federation_export_hook_plan", "moduleFederationExportHookPlan", "module-federation-export-hook-plan", "export_hook_plan", "exportHookPlan"),
            latest_traversal_graph=graph,
            latest_workflow_plan=workflow_plan,
            verify_execution=bool(context.get("verify_execution") or context.get("verifyExecution") or context.get("verify_latest_recursive_execution") or context.get("verifyLatestRecursiveExecution")),
            rebuild_graph=bool(context.get("rebuild_graph") or context.get("rebuildGraph") or context.get("rebuild_traversal_graph") or context.get("rebuildTraversalGraph")),
            replan_workflow=bool(context.get("replan_workflow") or context.get("replanWorkflow") or context.get("replan_traversal_workflow") or context.get("replanTraversalWorkflow")),
            plan_next_execution_review=bool(
                context.get("plan_next_execution_review")
                or context.get("planNextExecutionReview")
                or context.get("plan_next_recursive_execution_review")
                or context.get("planNextRecursiveExecutionReview")
                or context.get("plan_next_step")
                or context.get("planNextStep")
            ),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            max_steps=max(1, int(context.get("max_steps", context.get("maxSteps", 5)) or 5)),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
            max_preview_length=max(1, int(context.get("max_preview_length", context.get("maxPreviewLength", 240)) or 240)),
        )

@dataclass(slots=True)
class ModuleFederationRecursiveContinuationCheckpointResult:
    status: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checkpoint": self.checkpoint,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }

class ModuleFederationRecursiveContinuationCheckpointManager:
    """Advance one reviewed continuation checkpoint without remote execution or queue recursion."""

    def execute(self, spec: ModuleFederationRecursiveContinuationCheckpointSpec | None) -> ModuleFederationRecursiveContinuationCheckpointResult:
        if spec is None or not spec.continuation_journal:
            return ModuleFederationRecursiveContinuationCheckpointResult(
                status="unsupported",
                reason="missing_module_federation_recursive_continuation_journal",
                side_effect_policy=self._side_effect_policy(),
            )

        stages: list[dict[str, Any]] = []
        graph_result_payload: dict[str, Any] = {}
        workflow_result_payload: dict[str, Any] = {}
        next_execution_review_payload: dict[str, Any] = {}
        graph = dict(spec.latest_traversal_graph)
        workflow_plan = dict(spec.latest_workflow_plan)
        execution_ready = self._journal_has_reviewed_record(spec.continuation_journal)

        if spec.verify_execution:
            stages.append(self._stage("verify_latest_module_federation_recursive_execution", "verified" if self._has_latest_execution(spec) else "blocked", "" if self._has_latest_execution(spec) else "missing_latest_module_federation_recursive_execution", side_effect=False))
        else:
            stages.append(self._stage("verify_latest_module_federation_recursive_execution", "pending", "review_required", side_effect=False))

        wants_checkpoint_execution = any((spec.verify_execution, spec.rebuild_graph, spec.replan_workflow, spec.plan_next_execution_review))
        if wants_checkpoint_execution and not spec.review_approved:
            stages.append(self._stage("review_gate", "blocked", "review_approval_required", side_effect=False))
        elif wants_checkpoint_execution and not execution_ready:
            stages.append(self._stage("review_gate", "blocked", "module_federation_recursive_continuation_journal_append_required", side_effect=False))
        else:
            stages.append(self._stage("review_gate", "passed" if wants_checkpoint_execution else "pending", "" if wants_checkpoint_execution else "manual_checkpoint_required", side_effect=False))

        if spec.rebuild_graph:
            if self._is_blocked(stages):
                stages.append(self._stage("rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence", "blocked", self._reason(stages), side_effect=False))
            elif not any((spec.get_init_plan, spec.get_init_result, spec.factory_invoke_result, spec.export_hook_plan, spec.latest_traversal_graph)):
                stages.append(self._stage("rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence", "blocked", "missing_module_federation_traversal_evidence", side_effect=False))
            else:
                graph_result = ModuleFederationTraversalGraphManager().build(
                    ModuleFederationTraversalGraphSpec(
                        get_init_plan=spec.get_init_plan,
                        get_init_result=spec.get_init_result,
                        factory_invoke_result=spec.factory_invoke_result,
                        export_hook_plan=spec.export_hook_plan,
                        previous_graph=spec.latest_traversal_graph,
                        max_queue_size=spec.max_queue_size,
                        max_preview_length=spec.max_preview_length,
                    )
                )
                graph_result_payload = graph_result.to_dict()
                graph = graph_result.graph
                stages.append(self._stage("rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence", graph_result.status, graph_result.reason, side_effect=False))
        else:
            stages.append(self._stage("rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence", "pending", "", side_effect=False))

        if spec.replan_workflow:
            if self._is_blocked(stages):
                stages.append(self._stage("replan_module_federation_traversal_workflow_from_refreshed_graph", "blocked", self._reason(stages), side_effect=False))
            elif not graph:
                stages.append(self._stage("replan_module_federation_traversal_workflow_from_refreshed_graph", "blocked", "module_federation_traversal_graph_required", side_effect=False))
            else:
                workflow_result = ModuleFederationTraversalWorkflowPlanManager().plan(
                    ModuleFederationTraversalWorkflowPlanSpec(traversal_graph=graph, max_steps=spec.max_steps)
                )
                workflow_result_payload = workflow_result.to_dict()
                workflow_plan = workflow_result.workflow_plan
                stages.append(self._stage("replan_module_federation_traversal_workflow_from_refreshed_graph", workflow_result.status, workflow_result.reason, side_effect=False))
        else:
            stages.append(self._stage("replan_module_federation_traversal_workflow_from_refreshed_graph", "pending", "", side_effect=False))

        if spec.plan_next_execution_review:
            if self._is_blocked(stages):
                stages.append(self._stage("review_next_module_federation_recursive_traversal_execution", "blocked", self._reason(stages), side_effect=False))
            elif not workflow_plan:
                stages.append(self._stage("review_next_module_federation_recursive_traversal_execution", "blocked", "module_federation_traversal_workflow_plan_required", side_effect=False))
            else:
                next_execution_review_payload = ModuleFederationRecursiveTraversalFollowupManager._next_step_review_payload(workflow_plan=workflow_plan, workflow_execution=spec.recursive_execution)
                stages.append(self._stage("review_next_module_federation_recursive_traversal_execution", next_execution_review_payload["status"], next_execution_review_payload.get("reason"), side_effect=False))
        else:
            stages.append(self._stage("review_next_module_federation_recursive_traversal_execution", "pending", "", side_effect=False))

        stages.append(self._stage("stop_before_next_module_federation_remote_execution", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, graph_result_payload, workflow_result_payload, next_execution_review_payload)
        reason = self._reason(stages)
        side_effect_policy = self._side_effect_policy(spec=spec, stages=stages)
        checkpoint = {
            "schema_version": "reverse-deepagent.module-federation-recursive-continuation-checkpoint.v1",
            "status": status,
            "reason": reason,
            "review_required": True,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "journal_id": spec.continuation_journal.get("journal_id"),
            "source_journal_status": spec.continuation_journal.get("status"),
            "source_journal_record_count": self._record_count(spec.continuation_journal),
            "latest_entry": self._latest_entry(spec.continuation_journal),
            "stages": stages,
            "module_federation_traversal_graph": graph_result_payload,
            "module_federation_traversal_workflow_plan": workflow_result_payload,
            "module_federation_next_execution_review": next_execution_review_payload,
            "artifact_refs": {
                "continuation_journal": "workspace/module-federation-recursive-continuation-journal.json",
                "recursive_execution": "workspace/module-federation-recursive-traversal-execution.json" if spec.recursive_execution else "",
                "recursive_followup": "workspace/module-federation-recursive-traversal-followup.json" if spec.recursive_followup else "",
                "recursive_plan": "workspace/module-federation-recursive-traversal-plan.json" if spec.recursive_plan else "",
                "traversal_graph": "workspace/module-federation-traversal-graph.json" if graph_result_payload else "",
                "workflow_plan": "workspace/module-federation-traversal-workflow-plan.json" if workflow_result_payload else "",
                "next_recursive_execution": "workspace/module-federation-recursive-traversal-execution.json" if next_execution_review_payload else "",
            },
            "side_effect_policy": side_effect_policy,
            "next_action": self._next_action(status, reason),
        }
        return ModuleFederationRecursiveContinuationCheckpointResult(status=status, checkpoint=checkpoint, side_effect_policy=side_effect_policy, reason=reason)

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _journal_has_reviewed_record(cls, journal: dict[str, Any]) -> bool:
        return str(journal.get("status") or "") == "journal_appended" or cls._record_count(journal) > 0

    @staticmethod
    def _has_latest_execution(spec: ModuleFederationRecursiveContinuationCheckpointSpec) -> bool:
        latest_entry = ModuleFederationRecursiveContinuationCheckpointManager._latest_entry(spec.continuation_journal)
        return bool(spec.recursive_execution or latest_entry.get("recursive_execution_status"))

    @staticmethod
    def _latest_entry(journal: dict[str, Any]) -> dict[str, Any]:
        records = _list_dicts(journal.get("records"))
        if records:
            return records[-1]
        pending = journal.get("pending_entry")
        return dict(pending) if isinstance(pending, dict) else {}

    @staticmethod
    def _record_count(journal: dict[str, Any]) -> int:
        try:
            return int(journal.get("record_count"))
        except (TypeError, ValueError):
            return len(_list_dicts(journal.get("records")))

    @staticmethod
    def _is_blocked(stages: list[dict[str, Any]]) -> bool:
        return any(stage["status"] in {"blocked", "failed", "failure", "error", "unsupported"} for stage in stages)

    @staticmethod
    def _reason(stages: list[dict[str, Any]]) -> str | None:
        for stage in stages:
            if stage["status"] in {"blocked", "failed", "failure", "error", "unsupported"} and stage.get("reason"):
                return str(stage["reason"])
        return None

    @staticmethod
    def _status(
        stages: list[dict[str, Any]],
        graph_result: dict[str, Any],
        workflow_result: dict[str, Any],
        next_execution_review: dict[str, Any],
    ) -> str:
        if any(stage["status"] in {"failed", "failure", "error"} for stage in stages):
            return "failed"
        if any(stage["status"] in {"blocked", "unsupported"} for stage in stages):
            return "blocked"
        if next_execution_review:
            return "next_execution_review_ready" if next_execution_review.get("status") == "ready_for_review" else "complete"
        workflow_plan = workflow_result.get("workflow_plan") if isinstance(workflow_result.get("workflow_plan"), dict) else {}
        if workflow_result and str(workflow_result.get("status") or workflow_plan.get("status") or "") in {"ready_for_review", "complete"}:
            return "workflow_replanned"
        graph = graph_result.get("graph") if isinstance(graph_result.get("graph"), dict) else {}
        if graph_result and str(graph_result.get("status") or graph.get("status") or "") in {"ready_for_review", "complete"}:
            return "graph_rebuilt"
        return "ready_for_review"

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "next_execution_review_ready":
            return "review_next_module_federation_recursive_traversal_execution"
        if status == "workflow_replanned":
            return "plan_next_module_federation_recursive_execution_review"
        if status == "graph_rebuilt":
            return "replan_module_federation_traversal_workflow_before_next_recursive_execution"
        if status == "complete":
            return "module_federation_recursive_continuation_complete_or_provide_new_evidence"
        if status == "blocked" and reason:
            return "resolve_module_federation_recursive_continuation_checkpoint_blockers"
        if status == "failed":
            return "inspect_module_federation_recursive_continuation_checkpoint_failure"
        return "review_module_federation_recursive_continuation_checkpoint"

    @staticmethod
    def _side_effect_policy(
        spec: ModuleFederationRecursiveContinuationCheckpointSpec | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stages = stages or []
        return {
            "plan_only_by_default": not bool(spec and any((spec.verify_execution, spec.rebuild_graph, spec.replan_workflow, spec.plan_next_execution_review))),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "verifies_latest_recursive_execution": any(stage["stage"] == "verify_latest_module_federation_recursive_execution" and stage["status"] == "verified" for stage in stages),
            "traversal_graph_rebuilt": any(stage["stage"] == "rebuild_module_federation_traversal_graph_from_journal_and_execution_evidence" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "workflow_replanned": any(stage["stage"] == "replan_module_federation_traversal_workflow_from_refreshed_graph" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "next_execution_review_planned": any(stage["stage"] == "review_next_module_federation_recursive_traversal_execution" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "container_init_executed": False,
            "remote_get_called": False,
            "remote_factory_invoked": False,
            "remote_code_executed": False,
            "export_hook_installed": False,
            "workflow_executed": False,
            "automatic_queue_advance": False,
            "recursive_federation_traversal": False,
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
