"""module_hooks.custom_loader — split from monolithic module_hooks.py (B1 consolidation)."""

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
from reverse_deepagent.browser.hooks.module_hooks.async_chunk import (
    AsyncChunkModuleDiffManager, AsyncChunkModuleDiffSpec,
)


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
class CustomLoaderTraversalLoopExecutionSpec:
    """Review-gated executor for one bounded custom-loader traversal loop iteration."""

    loop_plan: dict[str, Any] = field(default_factory=dict)
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
    selected_iteration_index: int | None = None
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
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderTraversalLoopExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_traversal_loop_execution")
            or context.get("customLoaderTraversalLoopExecution")
            or context.get("custom-loader-traversal-loop-execution")
            or context.get("execute_custom_loader_traversal_loop")
            or context.get("executeCustomLoaderTraversalLoop")
        )
        loop_plan = (
            context.get("custom_loader_traversal_loop_plan")
            or context.get("customLoaderTraversalLoopPlan")
            or context.get("custom-loader-traversal-loop-plan")
            or context.get("loop_plan")
            or context.get("loopPlan")
        )
        if isinstance(loop_plan, dict) and isinstance(loop_plan.get("loop_plan"), dict):
            loop_plan = loop_plan["loop_plan"]
        if not isinstance(loop_plan, dict):
            return None if not requested else cls()
        workflow_plan = (
            context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
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
            loop_plan=dict(loop_plan),
            workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            traversal_plan=dict(traversal_plan) if isinstance(traversal_plan, dict) else {},
            continuation_workflow=dict(continuation_workflow) if isinstance(continuation_workflow, dict) else {},
            preflight=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_preflight", "custom-loader-execution-preflight", "customLoaderExecutionPreflight"),
            execution_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_result", "custom-loader-execution-result", "customLoaderExecutionResult"),
            module_diff=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_diff", "custom-loader-module-diff", "customLoaderModuleDiff"),
            module_hook_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_hook_result", "custom-loader-module-hook-result", "customLoaderModuleHookResult", "module_hooks", "module-hooks"),
            existing_journal=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_continuation_journal", "custom-loader-continuation-journal", "customLoaderContinuationJournal"),
            module_discovery=CustomLoaderContinuationJournalSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_iteration_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("selected_iteration_index", context.get("selectedIterationIndex", context.get("iteration_index", context.get("iterationIndex"))))),
            selected_step_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
            plan_continuation_workflow=bool(context.get("plan_continuation_workflow") or context.get("planContinuationWorkflow") or context.get("plan_custom_loader_continuation_workflow") or context.get("planCustomLoaderContinuationWorkflow")),
            run_preflight=bool(context.get("run_preflight") or context.get("runPreflight") or context.get("execute_preflight") or context.get("executePreflight")),
            execute_custom_loader=bool(context.get("execute_custom_loader") or context.get("executeCustomLoader")),
            run_module_diff=bool(context.get("run_module_diff") or context.get("runModuleDiff") or context.get("refresh_module_diff") or context.get("refreshModuleDiff")),
            install_module_hook=bool(context.get("install_module_hook") or context.get("installModuleHook") or context.get("hook_custom_loader_module") or context.get("hookCustomLoaderModule")),
            append_journal=bool(context.get("append_journal") or context.get("appendJournal") or context.get("append_custom_loader_continuation_journal") or context.get("appendCustomLoaderContinuationJournal")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            loader_arguments=loader_arguments,
        )

@dataclass(slots=True)
class CustomLoaderTraversalLoopExecutionResult:
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

class CustomLoaderTraversalLoopExecutionManager:
    """Execute one reviewed custom-loader loop iteration and stop before recursion."""

    def execute(self, page: BrowserPage, spec: CustomLoaderTraversalLoopExecutionSpec | None) -> CustomLoaderTraversalLoopExecutionResult:
        if spec is None or not spec.loop_plan:
            return CustomLoaderTraversalLoopExecutionResult(status="unsupported", reason="missing_custom_loader_traversal_loop_plan", side_effect_policy=self._side_effect_policy())
        selected_iteration = self._selected_iteration(spec)
        if not selected_iteration:
            execution = self._execution_payload(spec, {}, {}, [], status="blocked", reason="missing_custom_loader_traversal_loop_iteration")
            return CustomLoaderTraversalLoopExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_custom_loader_traversal_loop_iteration")
        workflow_plan = self._workflow_plan(spec, selected_iteration)
        if not workflow_plan:
            execution = self._execution_payload(spec, selected_iteration, {}, [], status="blocked", reason="missing_custom_loader_traversal_workflow_plan")
            return CustomLoaderTraversalLoopExecutionResult(status="blocked", execution=execution, side_effect_policy=self._side_effect_policy(spec=spec), reason="missing_custom_loader_traversal_workflow_plan")
        stages: list[dict[str, Any]] = [self._stage("select_custom_loader_traversal_loop_iteration", "selected", "", side_effect=False)]
        workflow_execution_payload: dict[str, Any] = {}
        if self._has_workflow_execution_flags(spec):
            workflow_result = CustomLoaderTraversalWorkflowExecutionManager().execute(
                page,
                CustomLoaderTraversalWorkflowExecutionSpec(
                    workflow_plan=workflow_plan,
                    traversal_plan=spec.traversal_plan,
                    continuation_workflow=spec.continuation_workflow,
                    preflight=spec.preflight,
                    execution_result=spec.execution_result,
                    module_diff=spec.module_diff,
                    module_hook_result=spec.module_hook_result,
                    existing_journal=spec.existing_journal,
                    module_discovery=spec.module_discovery,
                    modules=spec.modules,
                    selected_step_index=self._selected_step_index(spec, selected_iteration),
                    candidate_index=self._candidate_index(spec, selected_iteration),
                    plan_continuation_workflow=spec.plan_continuation_workflow,
                    run_preflight=spec.run_preflight,
                    execute_custom_loader=spec.execute_custom_loader,
                    run_module_diff=spec.run_module_diff,
                    install_module_hook=spec.install_module_hook,
                    append_journal=spec.append_journal,
                    review_approved=spec.review_approved,
                    loader_arguments=spec.loader_arguments,
                ),
            )
            workflow_execution_payload = workflow_result.to_dict()
            stages.append(self._stage("execute_one_custom_loader_traversal_workflow_step", workflow_result.status, workflow_result.reason, side_effect=True))
        else:
            stages.append(self._stage("execute_one_custom_loader_traversal_workflow_step", "pending", "", side_effect=True))
        stages.append(self._stage("stop_before_graph_rebuild_workflow_replan_and_next_loop_iteration", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, workflow_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, selected_iteration, workflow_execution_payload, stages, status=status, reason=reason)
        return CustomLoaderTraversalLoopExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, workflow_execution=workflow_execution_payload), reason=reason)

    @staticmethod
    def _selected_iteration(spec: CustomLoaderTraversalLoopExecutionSpec) -> dict[str, Any]:
        iterations = spec.loop_plan.get("iterations") if isinstance(spec.loop_plan.get("iterations"), list) else []
        normalized = [dict(item) for item in iterations if isinstance(item, dict)]
        if not normalized:
            return {}
        selected_index = spec.selected_iteration_index if spec.selected_iteration_index is not None else 0
        for iteration in normalized:
            if int(iteration.get("iteration_index", -1)) == selected_index:
                return iteration
        if 0 <= selected_index < len(normalized):
            return normalized[selected_index]
        return {}

    @staticmethod
    def _selected_step_index(spec: CustomLoaderTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> int | None:
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        raw = iteration.get("source_step_index", iteration.get("step_index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _candidate_index(spec: CustomLoaderTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> int | None:
        if spec.candidate_index is not None:
            return spec.candidate_index
        raw = iteration.get("candidate_index", iteration.get("index"))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _workflow_plan(spec: CustomLoaderTraversalLoopExecutionSpec, iteration: dict[str, Any]) -> dict[str, Any]:
        if spec.workflow_plan:
            return dict(spec.workflow_plan)
        step = {
            "step_index": iteration.get("source_step_index", iteration.get("iteration_index", 0)),
            "candidate_index": iteration.get("candidate_index"),
            "candidate_fingerprint": iteration.get("candidate_fingerprint"),
            "loader_path": iteration.get("loader_path"),
            "target": iteration.get("loader_path"),
            "depth": iteration.get("depth"),
        }
        return {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": spec.loop_plan.get("source_workflow_plan_id") or "custom-loader-traversal-workflow-plan",
            "source_graph_id": spec.loop_plan.get("source_graph_id"),
            "planned_steps": [step],
        }

    @staticmethod
    def _has_workflow_execution_flags(spec: CustomLoaderTraversalLoopExecutionSpec) -> bool:
        return any(
            (
                spec.plan_continuation_workflow,
                spec.run_preflight,
                spec.execute_custom_loader,
                spec.run_module_diff,
                spec.install_module_hook,
                spec.append_journal,
            )
        )

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], workflow_execution: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        nested_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        nested_status = str(workflow_execution.get("status") or nested_execution.get("status") or "")
        if nested_status in {"journal_appended", "module_hook_recorded", "module_diff_ready", "execution_complete", "preflight_ready", "continuation_workflow_approved", "continuation_workflow_ready"}:
            return nested_status
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
        spec: CustomLoaderTraversalLoopExecutionSpec,
        selected_iteration: dict[str, Any],
        workflow_execution: dict[str, Any],
        stages: list[dict[str, Any]],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        nested_execution = workflow_execution.get("execution") if isinstance(workflow_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.custom-loader-traversal-loop-execution.v1",
            "status": status,
            "reason": reason,
            "loop_plan_id": spec.loop_plan.get("plan_id"),
            "source_workflow_plan_id": spec.loop_plan.get("source_workflow_plan_id") or spec.workflow_plan.get("plan_id"),
            "source_graph_id": spec.loop_plan.get("source_graph_id") or spec.workflow_plan.get("source_graph_id"),
            "selected_iteration_index": selected_iteration.get("iteration_index"),
            "selected_step_index": cls._selected_step_index(spec, selected_iteration) if selected_iteration else None,
            "selected_candidate_index": cls._candidate_index(spec, selected_iteration) if selected_iteration else None,
            "selected_iteration": selected_iteration,
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "execute_at_most_one_loader_step_per_review": True,
            "stages": stages,
            "custom_loader_traversal_workflow_execution": workflow_execution,
            "workflow_execution_status": workflow_execution.get("status") or nested_execution.get("status"),
            "artifact_refs": {
                "loop_plan": "workspace/custom-loader-traversal-loop-plan.json",
                "workflow_plan": "workspace/custom-loader-traversal-workflow-plan.json",
                "workflow_execution": "workspace/custom-loader-traversal-workflow-execution.json" if workflow_execution else "",
                "continuation_journal": "workspace/custom-loader-continuation-journal.json" if nested_execution.get("custom_loader_continuation_execution") else "",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "continuation_workflow_ready":
            return "review_custom_loader_continuation_workflow_before_preflight"
        if status == "continuation_workflow_approved":
            return "run_custom_loader_execution_preflight_for_selected_loop_iteration"
        if status == "preflight_ready":
            return "execute_custom_loader_with_review_approval"
        if status == "execution_complete":
            return "run_custom_loader_module_diff_after_reviewed_execution"
        if status == "module_diff_ready":
            return "review_custom_loader_module_diff_hook_candidates"
        if status == "module_hook_recorded":
            return "append_custom_loader_continuation_journal"
        if status == "journal_appended":
            return "rebuild_custom_loader_traversal_graph_and_replan_workflow_before_next_loop_iteration"
        if status == "blocked" and reason:
            return "resolve_custom_loader_traversal_loop_execution_blockers"
        if status == "failed":
            return "inspect_custom_loader_traversal_loop_execution_failure"
        return "review_custom_loader_traversal_loop_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: CustomLoaderTraversalLoopExecutionSpec | None = None,
        workflow_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nested_policy = workflow_execution.get("side_effect_policy") if isinstance(workflow_execution, dict) and isinstance(workflow_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and CustomLoaderTraversalLoopExecutionManager._has_workflow_execution_flags(spec)),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_loop": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "execute_at_most_one_loader_step_per_review": True,
            "continuation_workflow_planned": bool(nested_policy.get("continuation_workflow_planned", False)),
            "preflight_executed": bool(nested_policy.get("preflight_executed", False)),
            "loader_invoked": bool(nested_policy.get("loader_invoked", False)),
            "custom_loader_executed": bool(nested_policy.get("custom_loader_executed", False)),
            "module_diff_executed": bool(nested_policy.get("module_diff_executed", False)),
            "module_hook_installed": bool(nested_policy.get("module_hook_installed", False)),
            "writes_journal": bool(nested_policy.get("writes_journal", False)),
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalPlanSpec:
    """Review-only follow-up planner after a bounded custom-loader loop execution."""

    loop_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    continuation_journal: dict[str, Any] = field(default_factory=dict)
    max_recursive_iterations: int = 3

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderRecursiveTraversalPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_recursive_traversal_plan")
            or context.get("customLoaderRecursiveTraversalPlan")
            or context.get("custom-loader-recursive-traversal-plan")
            or context.get("custom_loader_traversal_recursion_plan")
            or context.get("customLoaderTraversalRecursionPlan")
            or context.get("plan_custom_loader_recursive_traversal")
            or context.get("planCustomLoaderRecursiveTraversal")
        )
        loop_execution = (
            context.get("custom_loader_traversal_loop_execution")
            or context.get("customLoaderTraversalLoopExecution")
            or context.get("custom-loader-traversal-loop-execution")
            or context.get("latest_custom_loader_traversal_loop_execution")
            or context.get("latestCustomLoaderTraversalLoopExecution")
            or context.get("loop_execution")
            or context.get("loopExecution")
        )
        if isinstance(loop_execution, dict) and isinstance(loop_execution.get("execution"), dict):
            loop_execution = loop_execution["execution"]
        graph = (
            context.get("latest_custom_loader_traversal_graph")
            or context.get("latestCustomLoaderTraversalGraph")
            or context.get("custom_loader_traversal_graph")
            or context.get("customLoaderTraversalGraph")
            or context.get("custom-loader-traversal-graph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        workflow_plan = (
            context.get("latest_custom_loader_traversal_workflow_plan")
            or context.get("latestCustomLoaderTraversalWorkflowPlan")
            or context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        journal = CustomLoaderContinuationJournalSpec._object_alias(
            context,
            "custom_loader_continuation_journal",
            "custom-loader-continuation-journal",
            "customLoaderContinuationJournal",
            "continuation_journal",
            "continuationJournal",
        )
        if not isinstance(loop_execution, dict):
            return None if not requested else cls()
        return cls(
            loop_execution=dict(loop_execution),
            latest_traversal_graph=dict(graph) if isinstance(graph, dict) else {},
            latest_workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            continuation_journal=journal,
            max_recursive_iterations=max(1, int(context.get("max_recursive_iterations", context.get("maxRecursiveIterations", 3)) or 3)),
        )

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalPlanResult:
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

class CustomLoaderRecursiveTraversalPlanManager:
    """Plan the next reviewed recursion checkpoint after one bounded loop iteration."""

    EXECUTED_STATUSES = {
        "journal_appended",
        "module_hook_recorded",
        "module_diff_ready",
        "execution_complete",
        "preflight_ready",
    }

    def plan(self, spec: CustomLoaderRecursiveTraversalPlanSpec | None) -> CustomLoaderRecursiveTraversalPlanResult:
        policy = self._side_effect_policy(max_recursive_iterations=spec.max_recursive_iterations if spec else 0)
        if spec is None or not spec.loop_execution:
            return CustomLoaderRecursiveTraversalPlanResult(status="unsupported", reason="missing_custom_loader_traversal_loop_execution", side_effect_policy=policy)

        loop_status = self._loop_status(spec.loop_execution)
        graph_status = str(spec.latest_traversal_graph.get("status") or "")
        workflow_status = str(spec.latest_workflow_plan.get("status") or "")
        graph_queue_count = self._count(spec.latest_traversal_graph.get("queue_count"), spec.latest_traversal_graph.get("review_queue"))
        workflow_step_count = self._count(spec.latest_workflow_plan.get("planned_step_count"), spec.latest_workflow_plan.get("planned_steps"))

        if loop_status not in self.EXECUTED_STATUSES:
            status = "blocked"
            reason = "custom_loader_loop_execution_not_ready_for_recursion"
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
            "schema_version": "reverse-deepagent.custom-loader-recursive-traversal-plan.v1",
            "status": status,
            "reason": reason,
            "plan_id": "custom-loader-recursive-traversal-plan",
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
            "journal_record_count": len(CustomLoaderTraversalGraphManager._journal_records(spec.continuation_journal)),
            "follow_up_steps": self._follow_up_steps(status),
            "blocking_reasons": [reason] if reason else [],
            "artifact_refs": {
                "loop_execution": "workspace/custom-loader-traversal-loop-execution.json",
                "continuation_journal": "workspace/custom-loader-continuation-journal.json",
                "traversal_graph": "workspace/custom-loader-traversal-graph.json",
                "workflow_plan": "workspace/custom-loader-traversal-workflow-plan.json",
                "loop_plan": "workspace/custom-loader-traversal-loop-plan.json",
            },
            "side_effect_policy": policy,
            "next_action": self._next_action(status=status, reason=reason),
        }
        return CustomLoaderRecursiveTraversalPlanResult(status=status, recursive_plan=recursive_plan, side_effect_policy=policy, reason=reason)

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
            ("verify_reviewed_loop_execution_checkpoint", "workspace/custom-loader-traversal-loop-execution.json", None),
            ("rebuild_custom_loader_traversal_graph_from_journal_and_new_candidates", "workspace/custom-loader-continuation-journal.json", "workspace/custom-loader-traversal-graph.json"),
            ("replan_custom_loader_traversal_workflow_from_refreshed_graph", "workspace/custom-loader-traversal-graph.json", "workspace/custom-loader-traversal-workflow-plan.json"),
            ("plan_next_bounded_custom_loader_traversal_loop", "workspace/custom-loader-traversal-workflow-plan.json", "workspace/custom-loader-traversal-loop-plan.json"),
            ("stop_before_next_recursive_loop_execution_review", "workspace/custom-loader-traversal-loop-plan.json", None),
        ]
        if status == "ready_for_workflow_replan":
            steps = steps[2:]
        elif status == "ready_for_next_loop_review":
            steps = steps[3:]
        elif status == "complete":
            steps = [("record_custom_loader_recursive_traversal_complete", "workspace/custom-loader-traversal-graph.json", None)]
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
            return "resolve_custom_loader_recursive_traversal_blockers"
        if status == "complete":
            return "custom_loader_recursive_traversal_complete_or_provide_new_candidates"
        if status == "ready_for_next_loop_review":
            return "review_next_custom_loader_traversal_loop_plan"
        if status == "ready_for_workflow_replan":
            return "replan_custom_loader_traversal_workflow_before_next_loop"
        return "rebuild_custom_loader_traversal_graph_before_next_recursive_loop"

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
            "loader_invoked": False,
            "custom_loader_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "writes_journal": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalFollowupSpec:
    """Review-gated follow-through for custom-loader recursive traversal checkpoints."""

    recursive_plan: dict[str, Any] = field(default_factory=dict)
    traversal_plan: dict[str, Any] = field(default_factory=dict)
    continuation_journal: dict[str, Any] = field(default_factory=dict)
    loop_execution: dict[str, Any] = field(default_factory=dict)
    latest_traversal_graph: dict[str, Any] = field(default_factory=dict)
    latest_workflow_plan: dict[str, Any] = field(default_factory=dict)
    rebuild_graph: bool = False
    replan_workflow: bool = False
    plan_next_loop: bool = False
    review_approved: bool = False
    max_loop_iterations: int = 3
    max_traversal_depth: int = 3
    max_queue_size: int = 20

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderRecursiveTraversalFollowupSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_recursive_traversal_followup")
            or context.get("customLoaderRecursiveTraversalFollowup")
            or context.get("custom-loader-recursive-traversal-followup")
            or context.get("custom_loader_recursive_traversal_checkpoint")
            or context.get("customLoaderRecursiveTraversalCheckpoint")
            or context.get("custom-loader-recursive-traversal-checkpoint")
            or context.get("execute_custom_loader_recursive_traversal_followup")
            or context.get("executeCustomLoaderRecursiveTraversalFollowup")
        )
        recursive_plan = (
            context.get("custom_loader_recursive_traversal_plan")
            or context.get("customLoaderRecursiveTraversalPlan")
            or context.get("custom-loader-recursive-traversal-plan")
            or context.get("recursive_traversal_plan")
            or context.get("recursiveTraversalPlan")
        )
        if isinstance(recursive_plan, dict) and isinstance(recursive_plan.get("recursive_plan"), dict):
            recursive_plan = recursive_plan["recursive_plan"]
        if not isinstance(recursive_plan, dict):
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
        graph = (
            context.get("latest_custom_loader_traversal_graph")
            or context.get("latestCustomLoaderTraversalGraph")
            or context.get("custom_loader_traversal_graph")
            or context.get("customLoaderTraversalGraph")
            or context.get("custom-loader-traversal-graph")
        )
        if isinstance(graph, dict) and isinstance(graph.get("graph"), dict):
            graph = graph["graph"]
        workflow_plan = (
            context.get("latest_custom_loader_traversal_workflow_plan")
            or context.get("latestCustomLoaderTraversalWorkflowPlan")
            or context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        loop_execution = (
            context.get("custom_loader_traversal_loop_execution")
            or context.get("customLoaderTraversalLoopExecution")
            or context.get("custom-loader-traversal-loop-execution")
            or context.get("loop_execution")
            or context.get("loopExecution")
        )
        if isinstance(loop_execution, dict) and isinstance(loop_execution.get("execution"), dict):
            loop_execution = loop_execution["execution"]
        return cls(
            recursive_plan=dict(recursive_plan),
            traversal_plan=dict(traversal_plan) if isinstance(traversal_plan, dict) else {},
            continuation_journal=CustomLoaderContinuationJournalSpec._object_alias(
                context,
                "custom_loader_continuation_journal",
                "custom-loader-continuation-journal",
                "customLoaderContinuationJournal",
                "continuation_journal",
                "continuationJournal",
            ),
            loop_execution=dict(loop_execution) if isinstance(loop_execution, dict) else {},
            latest_traversal_graph=dict(graph) if isinstance(graph, dict) else {},
            latest_workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            rebuild_graph=bool(context.get("rebuild_graph") or context.get("rebuildGraph") or context.get("rebuild_traversal_graph") or context.get("rebuildTraversalGraph")),
            replan_workflow=bool(context.get("replan_workflow") or context.get("replanWorkflow") or context.get("replan_traversal_workflow") or context.get("replanTraversalWorkflow")),
            plan_next_loop=bool(context.get("plan_next_loop") or context.get("planNextLoop") or context.get("plan_next_traversal_loop") or context.get("planNextTraversalLoop")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            max_loop_iterations=max(1, int(context.get("max_loop_iterations", context.get("maxLoopIterations", 3)) or 3)),
            max_traversal_depth=max(1, int(context.get("max_traversal_depth", context.get("maxTraversalDepth", 3)) or 3)),
            max_queue_size=max(1, int(context.get("max_queue_size", context.get("maxQueueSize", 20)) or 20)),
        )

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalFollowupResult:
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

class CustomLoaderRecursiveTraversalFollowupManager:
    """Advance one reviewed recursive-traversal checkpoint without executing loaders."""

    def follow_up(self, spec: CustomLoaderRecursiveTraversalFollowupSpec | None) -> CustomLoaderRecursiveTraversalFollowupResult:
        if spec is None or not spec.recursive_plan:
            return CustomLoaderRecursiveTraversalFollowupResult(status="unsupported", reason="missing_custom_loader_recursive_traversal_plan", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = [self._stage("select_custom_loader_recursive_checkpoint", "selected", "", side_effect=False)]
        graph_result_payload: dict[str, Any] = {}
        workflow_result_payload: dict[str, Any] = {}
        loop_plan_result_payload: dict[str, Any] = {}
        graph = dict(spec.latest_traversal_graph)
        workflow_plan = dict(spec.latest_workflow_plan)

        if spec.rebuild_graph:
            if not spec.review_approved:
                stages.append(self._stage("rebuild_traversal_graph", "blocked", "review_approval_required", side_effect=False))
            elif not spec.traversal_plan:
                stages.append(self._stage("rebuild_traversal_graph", "blocked", "missing_custom_loader_traversal_plan", side_effect=False))
            else:
                graph_result = CustomLoaderTraversalGraphManager().plan(
                    CustomLoaderTraversalGraphSpec(
                        traversal_plan=spec.traversal_plan,
                        continuation_journal=spec.continuation_journal,
                        continuation_execution=spec.loop_execution,
                        max_traversal_depth=spec.max_traversal_depth,
                        max_queue_size=spec.max_queue_size,
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
                stages.append(self._stage("replan_traversal_workflow", "blocked", "custom_loader_traversal_graph_required", side_effect=False))
            else:
                workflow_result = CustomLoaderTraversalWorkflowPlanManager().plan(
                    CustomLoaderTraversalWorkflowPlanSpec(traversal_graph=graph)
                )
                workflow_result_payload = workflow_result.to_dict()
                workflow_plan = workflow_result.workflow_plan
                stages.append(self._stage("replan_traversal_workflow", workflow_result.status, workflow_result.reason, side_effect=False))
        else:
            stages.append(self._stage("replan_traversal_workflow", "pending", "", side_effect=False))

        if spec.plan_next_loop:
            if not spec.review_approved:
                stages.append(self._stage("plan_next_traversal_loop", "blocked", "review_approval_required", side_effect=False))
            elif not workflow_plan:
                stages.append(self._stage("plan_next_traversal_loop", "blocked", "custom_loader_traversal_workflow_plan_required", side_effect=False))
            else:
                loop_result = CustomLoaderTraversalLoopPlanManager().plan(
                    CustomLoaderTraversalLoopPlanSpec(
                        workflow_plan=workflow_plan,
                        latest_workflow_execution=spec.loop_execution,
                        latest_traversal_graph=graph,
                        max_loop_iterations=spec.max_loop_iterations,
                    )
                )
                loop_plan_result_payload = loop_result.to_dict()
                stages.append(self._stage("plan_next_traversal_loop", loop_result.status, loop_result.reason, side_effect=False))
        else:
            stages.append(self._stage("plan_next_traversal_loop", "pending", "", side_effect=False))

        stages.append(self._stage("stop_before_next_recursive_loop_execution", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, loop_plan_result_payload, workflow_result_payload, graph_result_payload)
        reason = self._reason(stages)
        followup = {
            "schema_version": "reverse-deepagent.custom-loader-recursive-traversal-followup.v1",
            "status": status,
            "reason": reason,
            "recursive_plan_id": spec.recursive_plan.get("plan_id"),
            "review_approved": spec.review_approved,
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "stages": stages,
            "custom_loader_traversal_graph": graph_result_payload,
            "custom_loader_traversal_workflow_plan": workflow_result_payload,
            "custom_loader_traversal_loop_plan": loop_plan_result_payload,
            "artifact_refs": {
                "recursive_plan": "workspace/custom-loader-recursive-traversal-plan.json",
                "traversal_graph": "workspace/custom-loader-traversal-graph.json" if graph_result_payload else "",
                "workflow_plan": "workspace/custom-loader-traversal-workflow-plan.json" if workflow_result_payload else "",
                "loop_plan": "workspace/custom-loader-traversal-loop-plan.json" if loop_plan_result_payload else "",
            },
            "next_action": self._next_action(status, reason),
        }
        return CustomLoaderRecursiveTraversalFollowupResult(status=status, followup=followup, side_effect_policy=self._side_effect_policy(spec=spec, stages=stages), reason=reason)

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @staticmethod
    def _status(
        stages: list[dict[str, Any]],
        loop_plan_result: dict[str, Any],
        workflow_result: dict[str, Any],
        graph_result: dict[str, Any],
    ) -> str:
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
            return "review_next_custom_loader_traversal_loop_plan_before_execution"
        if status == "workflow_replanned":
            return "plan_next_custom_loader_traversal_loop"
        if status == "graph_rebuilt":
            return "replan_custom_loader_traversal_workflow_before_next_loop"
        if status == "blocked" and reason:
            return "resolve_custom_loader_recursive_traversal_followup_blockers"
        if status == "failed":
            return "inspect_custom_loader_recursive_traversal_followup_failure"
        return "review_custom_loader_recursive_traversal_followup_plan"

    @staticmethod
    def _side_effect_policy(
        spec: CustomLoaderRecursiveTraversalFollowupSpec | None = None,
        stages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stages = stages or []
        return {
            "plan_only_by_default": not bool(spec and any((spec.rebuild_graph, spec.replan_workflow, spec.plan_next_loop))),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "traversal_graph_rebuilt": any(stage["stage"] == "rebuild_traversal_graph" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "workflow_replanned": any(stage["stage"] == "replan_traversal_workflow" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "loop_plan_created": any(stage["stage"] == "plan_next_traversal_loop" and stage["status"] in {"ready_for_review", "complete"} for stage in stages),
            "loader_invoked": False,
            "custom_loader_executed": False,
            "module_diff_executed": False,
            "module_hook_installed": False,
            "writes_journal": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalExecutionSpec:
    """Review-gated execution of one next-loop step from a recursive traversal checkpoint."""

    recursive_followup: dict[str, Any] = field(default_factory=dict)
    loop_plan: dict[str, Any] = field(default_factory=dict)
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
    selected_iteration_index: int | None = None
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
    def from_context(cls, context: dict[str, Any] | None = None) -> "CustomLoaderRecursiveTraversalExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("custom_loader_recursive_traversal_execution")
            or context.get("customLoaderRecursiveTraversalExecution")
            or context.get("custom-loader-recursive-traversal-execution")
            or context.get("execute_custom_loader_recursive_traversal")
            or context.get("executeCustomLoaderRecursiveTraversal")
            or context.get("execute_custom_loader_recursive_traversal_next_loop")
            or context.get("executeCustomLoaderRecursiveTraversalNextLoop")
        )
        followup = (
            context.get("custom_loader_recursive_traversal_followup")
            or context.get("customLoaderRecursiveTraversalFollowup")
            or context.get("custom-loader-recursive-traversal-followup")
            or context.get("recursive_traversal_followup")
            or context.get("recursiveTraversalFollowup")
        )
        if isinstance(followup, dict) and isinstance(followup.get("followup"), dict):
            followup = followup["followup"]
        loop_plan = (
            context.get("custom_loader_traversal_loop_plan")
            or context.get("customLoaderTraversalLoopPlan")
            or context.get("custom-loader-traversal-loop-plan")
            or context.get("next_custom_loader_traversal_loop_plan")
            or context.get("nextCustomLoaderTraversalLoopPlan")
            or context.get("loop_plan")
            or context.get("loopPlan")
        )
        if isinstance(loop_plan, dict) and isinstance(loop_plan.get("loop_plan"), dict):
            loop_plan = loop_plan["loop_plan"]
        if not isinstance(loop_plan, dict) and isinstance(followup, dict):
            loop_result = followup.get("custom_loader_traversal_loop_plan")
            if isinstance(loop_result, dict) and isinstance(loop_result.get("loop_plan"), dict):
                loop_plan = loop_result["loop_plan"]
        if not isinstance(loop_plan, dict):
            return None if not requested else cls(recursive_followup=dict(followup) if isinstance(followup, dict) else {})
        workflow_plan = (
            context.get("custom_loader_traversal_workflow_plan")
            or context.get("customLoaderTraversalWorkflowPlan")
            or context.get("custom-loader-traversal-workflow-plan")
            or context.get("traversal_workflow_plan")
            or context.get("traversalWorkflowPlan")
        )
        if isinstance(workflow_plan, dict) and isinstance(workflow_plan.get("workflow_plan"), dict):
            workflow_plan = workflow_plan["workflow_plan"]
        if not isinstance(workflow_plan, dict) and isinstance(followup, dict):
            workflow_result = followup.get("custom_loader_traversal_workflow_plan")
            if isinstance(workflow_result, dict) and isinstance(workflow_result.get("workflow_plan"), dict):
                workflow_plan = workflow_result["workflow_plan"]
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
            recursive_followup=dict(followup) if isinstance(followup, dict) else {},
            loop_plan=dict(loop_plan),
            workflow_plan=dict(workflow_plan) if isinstance(workflow_plan, dict) else {},
            traversal_plan=dict(traversal_plan) if isinstance(traversal_plan, dict) else {},
            continuation_workflow=dict(continuation_workflow) if isinstance(continuation_workflow, dict) else {},
            preflight=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_preflight", "custom-loader-execution-preflight", "customLoaderExecutionPreflight"),
            execution_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_execution_result", "custom-loader-execution-result", "customLoaderExecutionResult"),
            module_diff=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_diff", "custom-loader-module-diff", "customLoaderModuleDiff"),
            module_hook_result=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_module_hook_result", "custom-loader-module-hook-result", "customLoaderModuleHookResult", "module_hooks", "module-hooks"),
            existing_journal=CustomLoaderContinuationJournalSpec._object_alias(context, "custom_loader_continuation_journal", "custom-loader-continuation-journal", "customLoaderContinuationJournal"),
            module_discovery=CustomLoaderContinuationJournalSpec._object_alias(context, "module_discovery", "moduleDiscovery", "module_registry", "moduleRegistry"),
            modules=[dict(item) for item in modules if isinstance(item, dict)] if isinstance(modules, list) else [],
            selected_iteration_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("selected_iteration_index", context.get("selectedIterationIndex", context.get("iteration_index", context.get("iterationIndex"))))),
            selected_step_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex"))))),
            candidate_index=CustomLoaderTraversalWorkflowExecutionSpec._optional_int(context.get("candidate_index", context.get("candidateIndex"))),
            plan_continuation_workflow=bool(context.get("plan_continuation_workflow") or context.get("planContinuationWorkflow") or context.get("plan_custom_loader_continuation_workflow") or context.get("planCustomLoaderContinuationWorkflow")),
            run_preflight=bool(context.get("run_preflight") or context.get("runPreflight") or context.get("execute_preflight") or context.get("executePreflight")),
            execute_custom_loader=bool(context.get("execute_custom_loader") or context.get("executeCustomLoader")),
            run_module_diff=bool(context.get("run_module_diff") or context.get("runModuleDiff") or context.get("refresh_module_diff") or context.get("refreshModuleDiff")),
            install_module_hook=bool(context.get("install_module_hook") or context.get("installModuleHook") or context.get("hook_custom_loader_module") or context.get("hookCustomLoaderModule")),
            append_journal=bool(context.get("append_journal") or context.get("appendJournal") or context.get("append_custom_loader_continuation_journal") or context.get("appendCustomLoaderContinuationJournal")),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            loader_arguments=loader_arguments,
        )

@dataclass(slots=True)
class CustomLoaderRecursiveTraversalExecutionResult:
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

class CustomLoaderRecursiveTraversalExecutionManager:
    """Execute one reviewed next-loop checkpoint and stop before deeper recursion."""

    def execute(self, page: BrowserPage, spec: CustomLoaderRecursiveTraversalExecutionSpec | None) -> CustomLoaderRecursiveTraversalExecutionResult:
        if spec is None or not spec.loop_plan:
            return CustomLoaderRecursiveTraversalExecutionResult(status="unsupported", reason="missing_custom_loader_traversal_loop_plan", side_effect_policy=self._side_effect_policy())
        stages: list[dict[str, Any]] = [self._stage("select_custom_loader_recursive_next_loop_checkpoint", "selected", "", side_effect=False)]
        loop_execution_payload: dict[str, Any] = {}
        if self._has_loop_execution_flags(spec):
            if not spec.review_approved:
                stages.append(self._stage("execute_next_bounded_custom_loader_loop", "blocked", "review_approval_required", side_effect=True))
            else:
                loop_result = CustomLoaderTraversalLoopExecutionManager().execute(
                    page,
                    CustomLoaderTraversalLoopExecutionSpec(
                        loop_plan=spec.loop_plan,
                        workflow_plan=spec.workflow_plan,
                        traversal_plan=spec.traversal_plan,
                        continuation_workflow=spec.continuation_workflow,
                        preflight=spec.preflight,
                        execution_result=spec.execution_result,
                        module_diff=spec.module_diff,
                        module_hook_result=spec.module_hook_result,
                        existing_journal=spec.existing_journal,
                        module_discovery=spec.module_discovery,
                        modules=spec.modules,
                        selected_iteration_index=spec.selected_iteration_index,
                        selected_step_index=spec.selected_step_index,
                        candidate_index=spec.candidate_index,
                        plan_continuation_workflow=spec.plan_continuation_workflow,
                        run_preflight=spec.run_preflight,
                        execute_custom_loader=spec.execute_custom_loader,
                        run_module_diff=spec.run_module_diff,
                        install_module_hook=spec.install_module_hook,
                        append_journal=spec.append_journal,
                        review_approved=spec.review_approved,
                        loader_arguments=spec.loader_arguments,
                    ),
                )
                loop_execution_payload = loop_result.to_dict()
                stages.append(self._stage("execute_next_bounded_custom_loader_loop", loop_result.status, loop_result.reason, side_effect=True))
        else:
            stages.append(self._stage("execute_next_bounded_custom_loader_loop", "pending", "", side_effect=True))
        stages.append(self._stage("stop_before_recursive_followup_checkpoint", "stopped", "manual_checkpoint_required", side_effect=False))
        status = self._status(stages, loop_execution_payload)
        reason = self._reason(stages)
        execution = self._execution_payload(spec, loop_execution_payload, stages, status=status, reason=reason)
        return CustomLoaderRecursiveTraversalExecutionResult(status=status, execution=execution, side_effect_policy=self._side_effect_policy(spec=spec, loop_execution=loop_execution_payload), reason=reason)

    @staticmethod
    def _has_loop_execution_flags(spec: CustomLoaderRecursiveTraversalExecutionSpec) -> bool:
        return any(
            (
                spec.plan_continuation_workflow,
                spec.run_preflight,
                spec.execute_custom_loader,
                spec.run_module_diff,
                spec.install_module_hook,
                spec.append_journal,
            )
        )

    @staticmethod
    def _stage(name: str, status: str, reason: str | None, *, side_effect: bool) -> dict[str, Any]:
        return {"stage": name, "status": status, "reason": reason or "", "side_effect": side_effect}

    @classmethod
    def _status(cls, stages: list[dict[str, Any]], loop_execution: dict[str, Any]) -> str:
        if any(item["status"] in {"failed", "error"} for item in stages):
            return "failed"
        if any(item["status"] in {"blocked", "unsupported"} for item in stages):
            return "blocked"
        nested_execution = loop_execution.get("execution") if isinstance(loop_execution.get("execution"), dict) else {}
        nested_status = str(loop_execution.get("status") or nested_execution.get("status") or "")
        if nested_status == "journal_appended":
            return "next_loop_journal_appended"
        if nested_status in {"module_hook_recorded", "module_diff_ready", "execution_complete", "preflight_ready", "continuation_workflow_approved", "continuation_workflow_ready"}:
            return "next_loop_execution_progressed"
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
        spec: CustomLoaderRecursiveTraversalExecutionSpec,
        loop_execution: dict[str, Any],
        stages: list[dict[str, Any]],
        *,
        status: str,
        reason: str | None,
    ) -> dict[str, Any]:
        nested_execution = loop_execution.get("execution") if isinstance(loop_execution.get("execution"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.custom-loader-recursive-traversal-execution.v1",
            "status": status,
            "reason": reason,
            "source_recursive_followup_status": spec.recursive_followup.get("status"),
            "source_recursive_followup_next_action": spec.recursive_followup.get("next_action"),
            "loop_plan_id": spec.loop_plan.get("plan_id"),
            "review_approved": bool(spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "execute_at_most_one_loader_step_per_review": True,
            "stages": stages,
            "custom_loader_traversal_loop_execution": loop_execution,
            "loop_execution_status": loop_execution.get("status") or nested_execution.get("status"),
            "artifact_refs": {
                "recursive_followup": "workspace/custom-loader-recursive-traversal-followup.json",
                "loop_plan": "workspace/custom-loader-traversal-loop-plan.json",
                "loop_execution": "workspace/custom-loader-traversal-loop-execution.json" if loop_execution else "",
                "next_recursive_plan": "workspace/custom-loader-recursive-traversal-plan.json",
            },
            "next_action": cls._next_action(status, reason),
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "next_loop_journal_appended":
            return "plan_next_custom_loader_recursive_traversal_checkpoint"
        if status == "next_loop_execution_progressed":
            return "continue_reviewed_next_loop_stage_or_append_journal"
        if status == "blocked" and reason:
            return "resolve_custom_loader_recursive_traversal_execution_blockers"
        if status == "failed":
            return "inspect_custom_loader_recursive_traversal_execution_failure"
        return "review_custom_loader_recursive_traversal_execution_plan"

    @staticmethod
    def _side_effect_policy(
        spec: CustomLoaderRecursiveTraversalExecutionSpec | None = None,
        loop_execution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nested_policy = loop_execution.get("side_effect_policy") if isinstance(loop_execution, dict) and isinstance(loop_execution.get("side_effect_policy"), dict) else {}
        return {
            "plan_only_by_default": not bool(spec and CustomLoaderRecursiveTraversalExecutionManager._has_loop_execution_flags(spec)),
            "review_required": True,
            "requires_review_approval": True,
            "review_approved": bool(spec and spec.review_approved),
            "manual_checkpoint_required": True,
            "bounded_recursion": True,
            "execute_at_most_one_loop_iteration_per_review": True,
            "execute_at_most_one_loader_step_per_review": True,
            "loop_execution_started": bool(loop_execution),
            "continuation_workflow_planned": bool(nested_policy.get("continuation_workflow_planned", False)),
            "preflight_executed": bool(nested_policy.get("preflight_executed", False)),
            "loader_invoked": bool(nested_policy.get("loader_invoked", False)),
            "custom_loader_executed": bool(nested_policy.get("custom_loader_executed", False)),
            "module_diff_executed": bool(nested_policy.get("module_diff_executed", False)),
            "module_hook_installed": bool(nested_policy.get("module_hook_installed", False)),
            "writes_journal": bool(nested_policy.get("writes_journal", False)),
            "traversal_graph_rebuilt": False,
            "workflow_replanned": False,
            "loop_plan_created": False,
            "automatic_loop_execution": False,
            "automatic_queue_advance": False,
            "automatic_recursive_traversal": False,
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
