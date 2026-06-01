from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read


HOOK_ARTIFACT_REVIEW_VERSION = "2026-06-01.hook-artifact-review-v2"


def make_review_hook_artifacts_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only tool that reviews hook inventory and timeline artifacts."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def review_hook_artifacts(
        hook_artifacts_json: str | None = None,
        hook_artifacts_ref: str | None = None,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Review hook artifacts without installing hooks, evaluating JavaScript, or triggering targets."""

        payload, artifact_read = _loads_object_or_artifact(
            hook_artifacts_json,
            artifact_ref=hook_artifacts_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="hook_artifacts_json",
            artifact_field_name="hook_artifacts_ref",
        )
        function_hooks = _object_alias(payload, "function_hooks", "function-hooks", "functionHooks")
        function_timeline = _object_alias(payload, "function_hook_timeline", "function-hook-timeline", "functionHookTimeline")
        module_hooks = _object_alias(payload, "module_hooks", "module-hooks", "moduleHooks")
        module_timeline = _object_alias(payload, "module_hook_timeline", "module-hook-timeline", "moduleHookTimeline")
        generic_timeline = _object_alias(payload, "hook_timeline", "hook-timeline", "hookTimeline")
        source_logpoints = _object_alias(payload, "source_logpoints", "source-logpoints", "sourceLogpoints")
        async_chunk_plan = _object_alias(payload, "async_chunk_load_plan", "async-chunk-load-plan", "asyncChunkLoadPlan")
        async_chunk_result = _object_alias(payload, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult")
        async_chunk_module_diff = _object_alias(payload, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff")
        async_chunk_traversal_graph = _object_alias(payload, "async_chunk_traversal_graph", "async-chunk-traversal-graph", "asyncChunkTraversalGraph")
        async_chunk_traversal_workflow_plan = _object_alias(payload, "async_chunk_traversal_workflow_plan", "async-chunk-traversal-workflow-plan", "asyncChunkTraversalWorkflowPlan")
        async_chunk_traversal_workflow_execution = _object_alias(payload, "async_chunk_traversal_workflow_execution", "async-chunk-traversal-workflow-execution", "asyncChunkTraversalWorkflowExecution")
        async_chunk_traversal_loop_plan = _object_alias(payload, "async_chunk_traversal_loop_plan", "async-chunk-traversal-loop-plan", "asyncChunkTraversalLoopPlan")
        async_chunk_traversal_loop_execution = _object_alias(payload, "async_chunk_traversal_loop_execution", "async-chunk-traversal-loop-execution", "asyncChunkTraversalLoopExecution")
        custom_loader_traversal_plan = _object_alias(
            payload,
            "custom_loader_traversal_plan",
            "custom-loader-traversal-plan",
            "customLoaderTraversalPlan",
        )
        custom_loader_traversal_graph = _object_alias(
            payload,
            "custom_loader_traversal_graph",
            "custom-loader-traversal-graph",
            "customLoaderTraversalGraph",
        )
        custom_loader_traversal_workflow_plan = _object_alias(
            payload,
            "custom_loader_traversal_workflow_plan",
            "custom-loader-traversal-workflow-plan",
            "customLoaderTraversalWorkflowPlan",
        )
        custom_loader_traversal_workflow_execution = _object_alias(
            payload,
            "custom_loader_traversal_workflow_execution",
            "custom-loader-traversal-workflow-execution",
            "customLoaderTraversalWorkflowExecution",
        )
        custom_loader_traversal_loop_plan = _object_alias(
            payload,
            "custom_loader_traversal_loop_plan",
            "custom-loader-traversal-loop-plan",
            "customLoaderTraversalLoopPlan",
        )
        custom_loader_execution_preflight = _object_alias(
            payload,
            "custom_loader_execution_preflight",
            "custom-loader-execution-preflight",
            "customLoaderExecutionPreflight",
        )
        custom_loader_execution_result = _object_alias(
            payload,
            "custom_loader_execution_result",
            "custom-loader-execution-result",
            "customLoaderExecutionResult",
        )
        custom_loader_module_diff = _object_alias(
            payload,
            "custom_loader_module_diff",
            "custom-loader-module-diff",
            "customLoaderModuleDiff",
        )
        custom_loader_continuation_workflow = _object_alias(
            payload,
            "custom_loader_continuation_workflow",
            "custom-loader-continuation-workflow",
            "customLoaderContinuationWorkflow",
        )
        custom_loader_continuation_journal = _object_alias(
            payload,
            "custom_loader_continuation_journal",
            "custom-loader-continuation-journal",
            "customLoaderContinuationJournal",
        )
        custom_loader_continuation_execution = _object_alias(
            payload,
            "custom_loader_continuation_execution",
            "custom-loader-continuation-execution",
            "customLoaderContinuationExecution",
        )
        module_federation_get_init_plan = _object_alias(
            payload,
            "module_federation_get_init_plan",
            "module-federation-get-init-plan",
            "moduleFederationGetInitPlan",
        )
        module_federation_get_init_result = _object_alias(
            payload,
            "module_federation_get_init_result",
            "module-federation-get-init-result",
            "moduleFederationGetInitResult",
        )
        module_federation_factory_invoke_result = _object_alias(
            payload,
            "module_federation_factory_invoke_result",
            "module-federation-factory-invoke-result",
            "moduleFederationFactoryInvokeResult",
        )
        module_federation_export_hook_plan = _object_alias(
            payload,
            "module_federation_export_hook_plan",
            "module-federation-export-hook-plan",
            "moduleFederationExportHookPlan",
        )
        module_candidates = _records_alias(payload, "module_candidates", "module-candidates", "moduleCandidates")
        function_candidates = _records_alias(payload, "function_candidates", "function-candidates", "functionCandidates")

        function_events = _records_from(function_timeline.get("events") or function_timeline.get("entries"))
        module_events = _records_from(module_timeline.get("events") or module_timeline.get("entries"))
        generic_snapshot = generic_timeline.get("snapshot") if isinstance(generic_timeline.get("snapshot"), dict) else {}
        generic_events = _records_from(generic_timeline.get("events") or generic_timeline.get("entries") or generic_snapshot.get("events"))
        installed_function_count = _count_hooks(function_hooks)
        installed_module_count = _count_hooks(module_hooks)
        source_logpoint_count = _intish(source_logpoints.get("count") or source_logpoints.get("installed_count") or len(_records_from(source_logpoints)))
        timeline_event_count = _event_count(function_timeline, function_events) + _event_count(module_timeline, module_events) + _event_count(generic_timeline, generic_events)
        missing_count = _intish(function_hooks.get("missing_count")) + _intish(module_hooks.get("missing_count")) + _intish(source_logpoints.get("missing_count"))
        candidate_count = len(module_candidates) + len(function_candidates)

        blockers: list[str] = []
        warnings: list[str] = []
        artifact_count = sum(
            bool(item)
            for item in (
                function_hooks,
                function_timeline,
                module_hooks,
                module_timeline,
                generic_timeline,
                source_logpoints,
                async_chunk_plan,
                async_chunk_result,
                async_chunk_module_diff,
                async_chunk_traversal_graph,
                async_chunk_traversal_workflow_plan,
                async_chunk_traversal_workflow_execution,
                async_chunk_traversal_loop_plan,
                async_chunk_traversal_loop_execution,
                custom_loader_traversal_plan,
                custom_loader_traversal_graph,
                custom_loader_traversal_workflow_plan,
                custom_loader_traversal_workflow_execution,
                custom_loader_traversal_loop_plan,
                custom_loader_continuation_workflow,
                custom_loader_continuation_journal,
                custom_loader_continuation_execution,
                custom_loader_execution_preflight,
                custom_loader_execution_result,
                custom_loader_module_diff,
                module_federation_get_init_plan,
                module_federation_get_init_result,
                module_federation_factory_invoke_result,
                module_federation_export_hook_plan,
            )
        ) + sum(bool(items) for items in (module_candidates, function_candidates))
        if not artifact_count:
            warnings.append("no_hook_artifacts_provided")
        if any(_status(item) in {"failed", "failure", "error", "unsupported"} for item in (function_hooks, module_hooks, source_logpoints, generic_timeline)):
            blockers.append("hook_artifact_reports_failure")
        if _status(async_chunk_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_load_plan_blocked")
        if _status(async_chunk_result) in {"failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_load_failed")
        if _status(async_chunk_module_diff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_module_diff_blocked")
        if _status(async_chunk_traversal_graph) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_traversal_graph_blocked")
        if _status(async_chunk_traversal_workflow_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_traversal_workflow_plan_blocked")
        if _status(async_chunk_traversal_workflow_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_traversal_workflow_execution_blocked")
        if _status(async_chunk_traversal_loop_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_traversal_loop_plan_blocked")
        if _status(async_chunk_traversal_loop_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_traversal_loop_execution_blocked")
        if _status(custom_loader_traversal_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_plan_blocked")
        if _status(custom_loader_traversal_graph) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_graph_blocked")
        if _status(custom_loader_traversal_workflow_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_workflow_plan_blocked")
        if _status(custom_loader_traversal_workflow_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_workflow_execution_blocked")
        if _status(custom_loader_traversal_loop_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_loop_plan_blocked")
        if _status(custom_loader_continuation_workflow) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_continuation_workflow_blocked")
        if _status(custom_loader_continuation_journal) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_continuation_journal_blocked")
        if _status(custom_loader_continuation_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_continuation_execution_blocked")
        if _status(custom_loader_execution_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_execution_preflight_blocked")
        if _status(custom_loader_execution_result) in {"failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_execution_failed")
        if _status(custom_loader_module_diff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_module_diff_blocked")
        async_chunk_traversal_graph_status = _nested_status(async_chunk_traversal_graph, "graph")
        async_chunk_traversal_workflow_plan_status = _nested_status(async_chunk_traversal_workflow_plan, "workflow_plan")
        async_chunk_traversal_workflow_execution_status = _nested_status(async_chunk_traversal_workflow_execution, "execution")
        async_chunk_traversal_loop_plan_status = _nested_status(async_chunk_traversal_loop_plan, "loop_plan")
        async_chunk_traversal_loop_execution_status = _nested_status(async_chunk_traversal_loop_execution, "execution")
        custom_loader_plan_status = _nested_status(custom_loader_traversal_plan, "plan")
        custom_loader_graph_status = _nested_status(custom_loader_traversal_graph, "graph")
        custom_loader_traversal_workflow_plan_status = _nested_status(custom_loader_traversal_workflow_plan, "workflow_plan")
        custom_loader_traversal_workflow_execution_status = _nested_status(custom_loader_traversal_workflow_execution, "execution")
        custom_loader_traversal_loop_plan_status = _nested_status(custom_loader_traversal_loop_plan, "loop_plan")
        custom_loader_continuation_workflow_status = _nested_status(custom_loader_continuation_workflow, "workflow")
        custom_loader_continuation_journal_status = _nested_status(custom_loader_continuation_journal, "journal")
        custom_loader_continuation_execution_status = _nested_status(custom_loader_continuation_execution, "execution")
        custom_loader_preflight_status = _nested_status(custom_loader_execution_preflight, "preflight")
        custom_loader_module_diff_status = _nested_status(custom_loader_module_diff, "diff")
        ready_continuation_count = _intish(custom_loader_traversal_plan.get("ready_continuation_count") or _nested_get(custom_loader_traversal_plan, "plan", "ready_continuation_count"))
        if ready_continuation_count and not custom_loader_continuation_workflow and not custom_loader_execution_preflight:
            warnings.append("custom_loader_continuation_workflow_required")
        if custom_loader_traversal_graph and not custom_loader_traversal_workflow_plan and (
            _status(custom_loader_traversal_graph) == "ready_for_review"
            or custom_loader_graph_status == "ready_for_review"
        ):
            warnings.append("custom_loader_traversal_graph_requires_review")
        if custom_loader_traversal_workflow_plan and not custom_loader_traversal_workflow_execution and (
            _status(custom_loader_traversal_workflow_plan) == "ready_for_review"
            or custom_loader_traversal_workflow_plan_status == "ready_for_review"
        ):
            warnings.append("custom_loader_traversal_workflow_plan_requires_review")
        if custom_loader_traversal_workflow_execution and (
            _status(custom_loader_traversal_workflow_execution) == "ready_for_review"
            or custom_loader_traversal_workflow_execution_status == "ready_for_review"
        ):
            warnings.append("custom_loader_traversal_workflow_execution_requires_review")
        if custom_loader_traversal_loop_plan and (
            _status(custom_loader_traversal_loop_plan) == "ready_for_review"
            or custom_loader_traversal_loop_plan_status == "ready_for_review"
        ):
            warnings.append("custom_loader_traversal_loop_plan_requires_review")
        if custom_loader_continuation_workflow and not custom_loader_continuation_journal and not custom_loader_execution_preflight and (
            _status(custom_loader_continuation_workflow) in {"ready_for_review", "approved_for_preflight"}
            or custom_loader_continuation_workflow_status in {"ready_for_review", "approved_for_preflight"}
        ):
            warnings.append("custom_loader_continuation_workflow_requires_review")
        if custom_loader_continuation_journal and not custom_loader_execution_preflight and (
            _status(custom_loader_continuation_journal) == "ready_for_review"
            or custom_loader_continuation_journal_status == "ready_for_review"
        ):
            warnings.append("custom_loader_continuation_journal_requires_review")
        if custom_loader_continuation_execution and (
            _status(custom_loader_continuation_execution) == "ready_for_review"
            or custom_loader_continuation_execution_status == "ready_for_review"
        ):
            warnings.append("custom_loader_continuation_execution_requires_review")
        if custom_loader_continuation_workflow and not custom_loader_continuation_execution and not custom_loader_execution_preflight and (
            _status(custom_loader_continuation_workflow) == "approved_for_preflight"
            or custom_loader_continuation_workflow_status == "approved_for_preflight"
        ):
            warnings.append("custom_loader_continuation_execution_required")
        if custom_loader_traversal_plan and (
            _status(custom_loader_traversal_plan) in {"ready_for_review", "planned"}
            or custom_loader_plan_status == "ready_for_review"
        ) and not custom_loader_continuation_workflow and not custom_loader_execution_preflight and not custom_loader_execution_result:
            warnings.append("custom_loader_traversal_requires_review")
        if custom_loader_execution_preflight and not custom_loader_execution_result and (
            _status(custom_loader_execution_preflight) == "ready_for_execution_review"
            or custom_loader_preflight_status == "ready_for_execution_review"
        ):
            warnings.append("custom_loader_execution_requires_review")
        if _status(custom_loader_execution_result) == "success" and not custom_loader_module_diff:
            warnings.append("custom_loader_module_diff_required")
        if custom_loader_module_diff and installed_module_count == 0 and (
            _status(custom_loader_module_diff) in {"ready_for_review", "planned"}
            or custom_loader_module_diff_status == "ready_for_review"
        ):
            warnings.append("custom_loader_module_diff_requires_review")
        if _status(module_federation_get_init_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_get_init_plan_blocked")
        if _status(module_federation_get_init_result) in {"failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_get_init_probe_failed")
        if _status(module_federation_factory_invoke_result) in {"failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_factory_invoke_failed")
        if _status(module_federation_export_hook_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_export_hook_plan_blocked")
        federation_plan_status = _nested_status(module_federation_get_init_plan, "plan")
        if module_federation_get_init_plan and (
            _status(module_federation_get_init_plan) in {"ready_for_review", "planned"}
            or federation_plan_status == "ready_for_review"
        ) and not module_federation_get_init_result and not module_federation_factory_invoke_result:
            warnings.append("module_federation_get_init_requires_review")
        federation_execution = module_federation_get_init_result.get("execution") if isinstance(module_federation_get_init_result.get("execution"), dict) else {}
        if _status(module_federation_get_init_result) == "success" and not federation_execution.get("remoteFactoryInvoked", False):
            warnings.append("module_federation_get_init_probe_requires_factory_review")
        federation_factory_execution = module_federation_factory_invoke_result.get("factory_execution") if isinstance(module_federation_factory_invoke_result.get("factory_execution"), dict) else {}
        export_hook_plan_status = _nested_status(module_federation_export_hook_plan, "plan")
        if _status(module_federation_factory_invoke_result) == "success" and federation_factory_execution.get("remoteFactoryInvoked", False) and not module_federation_export_hook_plan:
            warnings.append("module_federation_factory_exports_require_review")
        if module_federation_export_hook_plan and installed_function_count == 0 and (
            _status(module_federation_export_hook_plan) in {"ready_for_review", "planned"}
            or export_hook_plan_status == "ready_for_review"
        ):
            warnings.append("module_federation_export_hook_plan_requires_review")
        if async_chunk_plan and not async_chunk_result and _status(async_chunk_plan) in {"ready_for_review", "planned"}:
            warnings.append("async_chunk_load_requires_review")
        async_chunk_diff_status = _nested_status(async_chunk_module_diff, "diff")
        if _status(async_chunk_result) == "success" and not async_chunk_module_diff:
            warnings.append("async_chunk_module_diff_required")
        if async_chunk_module_diff and installed_module_count == 0 and (
            _status(async_chunk_module_diff) in {"ready_for_review", "planned"}
            or async_chunk_diff_status == "ready_for_review"
        ):
            warnings.append("async_chunk_module_diff_requires_review")
        if async_chunk_traversal_graph and not async_chunk_traversal_workflow_plan and (
            _status(async_chunk_traversal_graph) == "ready_for_review"
            or async_chunk_traversal_graph_status == "ready_for_review"
        ):
            warnings.append("async_chunk_traversal_graph_requires_review")
        if async_chunk_traversal_workflow_plan and not async_chunk_traversal_workflow_execution and (
            _status(async_chunk_traversal_workflow_plan) == "ready_for_review"
            or async_chunk_traversal_workflow_plan_status == "ready_for_review"
        ):
            warnings.append("async_chunk_traversal_workflow_plan_requires_review")
        if async_chunk_traversal_workflow_execution and (
            _status(async_chunk_traversal_workflow_execution) in {"ready_for_review", "async_chunk_load_planned"}
            or async_chunk_traversal_workflow_execution_status in {"ready_for_review", "async_chunk_load_planned"}
        ):
            warnings.append("async_chunk_traversal_workflow_execution_requires_review")
        if async_chunk_traversal_loop_plan and (
            _status(async_chunk_traversal_loop_plan) == "ready_for_review"
            or async_chunk_traversal_loop_plan_status == "ready_for_review"
        ):
            warnings.append("async_chunk_traversal_loop_plan_requires_review")
        if async_chunk_traversal_loop_execution and (
            _status(async_chunk_traversal_loop_execution) in {"ready_for_review", "async_chunk_load_planned"}
            or async_chunk_traversal_loop_execution_status in {"ready_for_review", "async_chunk_load_planned"}
        ):
            warnings.append("async_chunk_traversal_loop_execution_requires_review")
        if missing_count:
            warnings.append("hook_targets_missing")
        if installed_function_count + installed_module_count + source_logpoint_count > 0 and timeline_event_count == 0:
            warnings.append("installed_hooks_without_timeline_events")
        if candidate_count and installed_function_count + installed_module_count == 0:
            warnings.append("candidates_without_installed_hooks")

        status = "block" if blockers else "warn" if warnings else "pass"
        return {
            "version": HOOK_ARTIFACT_REVIEW_VERSION,
            "status": status,
            "blocked": bool(blockers),
            "warnings_present": bool(warnings),
            "next_action": _next_action(blockers, warnings),
            "artifact_input": summarize_workspace_artifact_read(artifact_read),
            "summary": {
                "artifact_count": artifact_count,
                "installed_function_hook_count": installed_function_count,
                "installed_module_hook_count": installed_module_count,
                "source_logpoint_count": source_logpoint_count,
                "missing_hook_target_count": missing_count,
                "candidate_count": candidate_count,
                "function_hook_event_count": _event_count(function_timeline, function_events),
                "module_hook_event_count": _event_count(module_timeline, module_events),
                "generic_hook_event_count": _event_count(generic_timeline, generic_events),
                "async_chunk_load_plan_status": _status(async_chunk_plan),
                "async_chunk_load_result_status": _status(async_chunk_result),
                "async_chunk_module_diff_status": _status(async_chunk_module_diff) or async_chunk_diff_status,
                "async_chunk_traversal_graph_status": _status(async_chunk_traversal_graph) or async_chunk_traversal_graph_status,
                "async_chunk_traversal_graph_queue_count": _intish(async_chunk_traversal_graph.get("queue_count") or _nested_get(async_chunk_traversal_graph, "graph", "queue_count")),
                "async_chunk_traversal_graph_loaded_chunk_count": _intish(async_chunk_traversal_graph.get("loaded_chunk_count") or _nested_get(async_chunk_traversal_graph, "graph", "loaded_chunk_count")),
                "async_chunk_traversal_workflow_plan_status": _status(async_chunk_traversal_workflow_plan) or async_chunk_traversal_workflow_plan_status,
                "async_chunk_traversal_workflow_planned_step_count": _intish(async_chunk_traversal_workflow_plan.get("planned_step_count") or _nested_get(async_chunk_traversal_workflow_plan, "workflow_plan", "planned_step_count")),
                "async_chunk_traversal_workflow_next_action": _nested_get(async_chunk_traversal_workflow_plan, "workflow_plan", "next_action") or async_chunk_traversal_workflow_plan.get("next_action"),
                "async_chunk_traversal_workflow_execution_status": _status(async_chunk_traversal_workflow_execution) or async_chunk_traversal_workflow_execution_status,
                "async_chunk_traversal_workflow_execution_stage_count": len(_listish(_nested_get(async_chunk_traversal_workflow_execution, "execution", "stages") or async_chunk_traversal_workflow_execution.get("stages"))),
                "async_chunk_traversal_workflow_execution_next_action": _nested_get(async_chunk_traversal_workflow_execution, "execution", "next_action") or async_chunk_traversal_workflow_execution.get("next_action"),
                "async_chunk_traversal_loop_plan_status": _status(async_chunk_traversal_loop_plan) or async_chunk_traversal_loop_plan_status,
                "async_chunk_traversal_loop_plan_iteration_count": _intish(async_chunk_traversal_loop_plan.get("planned_iteration_count") or _nested_get(async_chunk_traversal_loop_plan, "loop_plan", "planned_iteration_count")),
                "async_chunk_traversal_loop_plan_next_action": _nested_get(async_chunk_traversal_loop_plan, "loop_plan", "next_action") or async_chunk_traversal_loop_plan.get("next_action"),
                "async_chunk_traversal_loop_execution_status": _status(async_chunk_traversal_loop_execution) or async_chunk_traversal_loop_execution_status,
                "async_chunk_traversal_loop_execution_stage_count": len(_listish(_nested_get(async_chunk_traversal_loop_execution, "execution", "stages") or async_chunk_traversal_loop_execution.get("stages"))),
                "async_chunk_traversal_loop_execution_next_action": _nested_get(async_chunk_traversal_loop_execution, "execution", "next_action") or async_chunk_traversal_loop_execution.get("next_action"),
                "custom_loader_traversal_plan_status": _status(custom_loader_traversal_plan) or custom_loader_plan_status,
                "custom_loader_traversal_graph_status": _status(custom_loader_traversal_graph) or custom_loader_graph_status,
                "custom_loader_traversal_graph_queue_count": _intish(custom_loader_traversal_graph.get("queue_count") or _nested_get(custom_loader_traversal_graph, "graph", "queue_count")),
                "custom_loader_traversal_graph_depth_blocked_count": _intish(custom_loader_traversal_graph.get("depth_blocked_count") or _nested_get(custom_loader_traversal_graph, "graph", "depth_blocked_count")),
                "custom_loader_traversal_workflow_plan_status": _status(custom_loader_traversal_workflow_plan) or custom_loader_traversal_workflow_plan_status,
                "custom_loader_traversal_workflow_planned_step_count": _intish(custom_loader_traversal_workflow_plan.get("planned_step_count") or _nested_get(custom_loader_traversal_workflow_plan, "workflow_plan", "planned_step_count")),
                "custom_loader_traversal_workflow_next_action": _nested_get(custom_loader_traversal_workflow_plan, "workflow_plan", "next_action") or custom_loader_traversal_workflow_plan.get("next_action"),
                "custom_loader_traversal_workflow_execution_status": _status(custom_loader_traversal_workflow_execution) or custom_loader_traversal_workflow_execution_status,
                "custom_loader_traversal_workflow_execution_stage_count": len(_listish(_nested_get(custom_loader_traversal_workflow_execution, "execution", "stages") or custom_loader_traversal_workflow_execution.get("stages"))),
                "custom_loader_traversal_workflow_execution_next_action": _nested_get(custom_loader_traversal_workflow_execution, "execution", "next_action") or custom_loader_traversal_workflow_execution.get("next_action"),
                "custom_loader_traversal_loop_plan_status": _status(custom_loader_traversal_loop_plan) or custom_loader_traversal_loop_plan_status,
                "custom_loader_traversal_loop_plan_iteration_count": _intish(custom_loader_traversal_loop_plan.get("planned_iteration_count") or _nested_get(custom_loader_traversal_loop_plan, "loop_plan", "planned_iteration_count")),
                "custom_loader_traversal_loop_plan_next_action": _nested_get(custom_loader_traversal_loop_plan, "loop_plan", "next_action") or custom_loader_traversal_loop_plan.get("next_action"),
                "custom_loader_continuation_workflow_status": _status(custom_loader_continuation_workflow) or custom_loader_continuation_workflow_status,
                "custom_loader_continuation_journal_status": _status(custom_loader_continuation_journal) or custom_loader_continuation_journal_status,
                "custom_loader_continuation_execution_status": _status(custom_loader_continuation_execution) or custom_loader_continuation_execution_status,
                "custom_loader_continuation_execution_stage_count": len(_listish(_nested_get(custom_loader_continuation_execution, "execution", "stages") or custom_loader_continuation_execution.get("stages"))),
                "custom_loader_continuation_execution_next_action": _nested_get(custom_loader_continuation_execution, "execution", "next_action") or custom_loader_continuation_execution.get("next_action"),
                "custom_loader_continuation_journal_record_count": _intish(custom_loader_continuation_journal.get("record_count") or _nested_get(custom_loader_continuation_journal, "journal", "record_count")),
                "custom_loader_execution_preflight_status": _status(custom_loader_execution_preflight) or custom_loader_preflight_status,
                "custom_loader_execution_result_status": _status(custom_loader_execution_result),
                "custom_loader_module_diff_status": _status(custom_loader_module_diff) or custom_loader_module_diff_status,
                "custom_loader_traversal_candidate_count": _intish(custom_loader_traversal_plan.get("candidate_count") or _nested_get(custom_loader_traversal_plan, "plan", "candidate_count")),
                "custom_loader_traversal_ready_for_review_count": _intish(custom_loader_traversal_plan.get("ready_for_review_count") or _nested_get(custom_loader_traversal_plan, "plan", "ready_for_review_count")),
                "custom_loader_traversal_blocked_execution_count": _intish(custom_loader_traversal_plan.get("blocked_execution_count") or _nested_get(custom_loader_traversal_plan, "plan", "blocked_execution_count")),
                "custom_loader_traversal_ready_continuation_count": ready_continuation_count,
                "custom_loader_traversal_already_executed_count": _intish(custom_loader_traversal_plan.get("already_executed_count") or _nested_get(custom_loader_traversal_plan, "plan", "already_executed_count")),
                "custom_loader_traversal_previous_execution_count": _intish(custom_loader_traversal_plan.get("previous_execution_count") or _nested_get(custom_loader_traversal_plan, "plan", "previous_execution_count")),
                "custom_loader_continuation_workflow_selected_candidate_index": _nested_get(custom_loader_continuation_workflow, "workflow", "selected_candidate_index") if custom_loader_continuation_workflow else None,
                "custom_loader_continuation_workflow_review_approved": bool(custom_loader_continuation_workflow.get("review_approved") or _nested_get(custom_loader_continuation_workflow, "workflow", "review_approved")),
                "custom_loader_continuation_journal_writes_journal": bool(custom_loader_continuation_journal.get("writes_journal_now") or _nested_get(custom_loader_continuation_journal, "journal", "writes_journal_now")),
                "custom_loader_execution_attempted": bool(custom_loader_execution_result.get("execution", {}).get("attempted") if isinstance(custom_loader_execution_result.get("execution"), dict) else custom_loader_execution_result.get("execution_attempted", False)),
                "custom_loader_execution_loader_invoked": bool(custom_loader_execution_result.get("execution", {}).get("loaderInvoked") if isinstance(custom_loader_execution_result.get("execution"), dict) else custom_loader_execution_result.get("loader_invoked", False)),
                "custom_loader_execution_added_registry_key_count": len(_listish(custom_loader_execution_result.get("addedRegistryKeys") or custom_loader_execution_result.get("added_registry_keys") or _nested_get(custom_loader_execution_result, "execution", "addedRegistryKeys"))),
                "custom_loader_module_diff_matched_module_count": _intish(custom_loader_module_diff.get("matched_module_count") or _nested_get(custom_loader_module_diff, "diff", "matched_module_count")),
                "custom_loader_module_diff_hook_candidate_count": _intish(custom_loader_module_diff.get("candidate_count") or _nested_get(custom_loader_module_diff, "diff", "candidate_count")),
                "module_federation_get_init_plan_status": _status(module_federation_get_init_plan) or federation_plan_status,
                "module_federation_get_init_result_status": _status(module_federation_get_init_result),
                "module_federation_factory_invoke_result_status": _status(module_federation_factory_invoke_result),
                "module_federation_export_hook_plan_status": _status(module_federation_export_hook_plan) or export_hook_plan_status,
                "module_federation_get_init_candidate_count": _intish(module_federation_get_init_plan.get("candidate_count") or _nested_get(module_federation_get_init_plan, "plan", "candidate_count")),
                "module_federation_get_init_container_count": _intish(module_federation_get_init_plan.get("container_count") or _nested_get(module_federation_get_init_plan, "plan", "container_count")),
                "module_federation_get_init_exposed_module_count": _intish(module_federation_get_init_plan.get("exposed_module_count") or _nested_get(module_federation_get_init_plan, "plan", "exposed_module_count")),
                "module_federation_get_init_blocked_execution_count": _intish(module_federation_get_init_plan.get("blocked_execution_count") or _nested_get(module_federation_get_init_plan, "plan", "blocked_execution_count")),
                "module_federation_get_init_execution_attempted": bool(federation_execution.get("attempted") or module_federation_get_init_result.get("execution_attempted", False)),
                "module_federation_get_init_container_init_called": bool(federation_execution.get("containerInitCalled") or module_federation_get_init_result.get("container_init_called", False)),
                "module_federation_get_init_remote_get_called": bool(federation_execution.get("remoteGetCalled") or module_federation_get_init_result.get("remote_get_called", False)),
                "module_federation_get_init_remote_factory_invoked": bool(federation_execution.get("remoteFactoryInvoked") or module_federation_get_init_result.get("remote_factory_invoked", False)),
                "module_federation_get_init_added_shared_scope_key_count": len(_listish(federation_execution.get("addedSharedScopeKeys") or module_federation_get_init_result.get("added_shared_scope_keys"))),
                "module_federation_factory_execution_attempted": bool(federation_factory_execution.get("attempted") or module_federation_factory_invoke_result.get("factory_attempted", False)),
                "module_federation_factory_remote_factory_invoked": bool(federation_factory_execution.get("remoteFactoryInvoked") or module_federation_factory_invoke_result.get("remote_factory_invoked", False)),
                "module_federation_factory_remote_code_executed": bool(federation_factory_execution.get("remoteCodeExecuted") or module_federation_factory_invoke_result.get("remote_code_executed", False)),
                "module_federation_factory_export_count": len(_listish(federation_factory_execution.get("exportNames") or module_federation_factory_invoke_result.get("export_names"))),
                "module_federation_export_hook_candidate_count": _intish(module_federation_export_hook_plan.get("candidate_count") or _nested_get(module_federation_export_hook_plan, "plan", "candidate_count")),
                "module_federation_export_hook_hookable_candidate_count": _intish(module_federation_export_hook_plan.get("hookable_candidate_count") or _nested_get(module_federation_export_hook_plan, "plan", "hookable_candidate_count")),
                "async_chunk_load_execution_attempted": bool(async_chunk_result.get("execution", {}).get("attempted") if isinstance(async_chunk_result.get("execution"), dict) else async_chunk_result.get("execution_attempted", False)),
                "async_chunk_load_added_registry_key_count": len(_listish(async_chunk_result.get("addedRegistryKeys") or async_chunk_result.get("added_registry_keys"))),
                "async_chunk_module_diff_matched_module_count": _intish(async_chunk_module_diff.get("matched_module_count") or _nested_get(async_chunk_module_diff, "diff", "matched_module_count")),
                "async_chunk_module_diff_hook_candidate_count": _intish(async_chunk_module_diff.get("candidate_count") or _nested_get(async_chunk_module_diff, "diff", "candidate_count")),
                "timeline_event_count": timeline_event_count,
                "function_hook_event_type_counts": _event_type_counts(function_events),
                "module_hook_event_type_counts": _event_type_counts(module_events),
                "installed_function_targets": _installed_targets(function_hooks),
                "installed_module_targets": _installed_targets(module_hooks),
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(
                blockers,
                warnings,
                function_hooks,
                module_hooks,
                source_logpoints,
                async_chunk_plan,
                async_chunk_result,
                async_chunk_module_diff,
                async_chunk_traversal_graph,
                async_chunk_traversal_workflow_plan,
                async_chunk_traversal_workflow_execution,
                async_chunk_traversal_loop_plan,
                async_chunk_traversal_loop_execution,
                custom_loader_traversal_plan,
                custom_loader_traversal_graph,
                custom_loader_traversal_workflow_plan,
                custom_loader_traversal_workflow_execution,
                custom_loader_traversal_loop_plan,
                custom_loader_continuation_workflow,
                custom_loader_continuation_journal,
                custom_loader_continuation_execution,
                custom_loader_execution_preflight,
                custom_loader_execution_result,
                custom_loader_module_diff,
                module_federation_get_init_plan,
                module_federation_get_init_result,
                module_federation_factory_invoke_result,
                module_federation_export_hook_plan,
            ),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "hook_installed": False,
                "breakpoint_installed": False,
                "javascript_evaluated": False,
                "target_invoked": False,
                "runtime_mutated": False,
                "delivery_executed": False,
            },
        }

    review_hook_artifacts.__name__ = "review_hook_artifacts"
    return review_hook_artifacts


def _loads_object_or_artifact(
    payload: str | None,
    *,
    artifact_ref: str | None,
    artifact_root: str | None,
    default_artifact_root: Path,
    field_name: str,
    artifact_field_name: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if artifact_ref:
        value, read_result = load_workspace_artifact_json_object(
            artifact_ref=artifact_ref,
            default_artifact_root=default_artifact_root,
            artifact_root=artifact_root,
            field_name=artifact_field_name,
        )
        return value, read_result
    if payload is None:
        raise ValueError(f"{field_name} or {artifact_field_name} is required")
    return _loads_object(payload, field_name=field_name), None


def _loads_object(payload: str, *, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON object text: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must decode to a JSON object")
    return value


def _object_alias(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _records_alias(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        records = _records_from(payload.get(key))
        if records:
            return records
    return []


def _records_from(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "entries", "events", "records", "candidates", "hooks", "logpoints"):
            records = _records_from(value.get(key))
            if records:
                return records
    return []


def _status(item: dict[str, Any]) -> str:
    value = item.get("status") or item.get("result") or item.get("state")
    return value.lower() if isinstance(value, str) else ""


def _nested_status(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    return _status(value) if isinstance(value, dict) else ""


def _nested_get(item: dict[str, Any], key: str, nested_key: str) -> Any:
    value = item.get(key)
    return value.get(nested_key) if isinstance(value, dict) else None


def _listish(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _intish(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _count_hooks(payload: dict[str, Any]) -> int:
    for key in ("installed_count", "count"):
        count = _intish(payload.get(key))
        if count:
            return count
    installed = payload.get("installed")
    if isinstance(installed, dict):
        return sum(1 for value in installed.values() if bool(value))
    hooks = _records_from(payload)
    if hooks:
        return len(hooks)
    return 0


def _event_count(payload: dict[str, Any], events: list[dict[str, Any]]) -> int:
    return _intish(payload.get("event_count") or payload.get("eventCount") or payload.get("entry_count") or payload.get("count")) or len(events)


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("type") or item.get("event") or item.get("kind") or "unknown") for item in events)
    return dict(sorted(counter.items()))


def _installed_targets(payload: dict[str, Any]) -> list[str]:
    installed = payload.get("installed")
    if isinstance(installed, dict):
        return sorted(str(key) for key, value in installed.items() if bool(value))
    targets = payload.get("installed_targets") or payload.get("targets")
    if isinstance(targets, list):
        return [str(item) for item in targets if item is not None]
    return []


def _next_action(blockers: list[str], warnings: list[str]) -> str:
    if "hook_artifact_reports_failure" in blockers:
        return "inspect_hook_failure_and_adjust_target_paths"
    if "module_federation_get_init_plan_blocked" in blockers:
        return "provide_module_federation_candidates_from_module_discovery"
    if "module_federation_get_init_probe_failed" in blockers:
        return "inspect_module_federation_get_init_probe_failure"
    if "module_federation_factory_invoke_failed" in blockers:
        return "inspect_module_federation_factory_invoke_failure"
    if "module_federation_export_hook_plan_blocked" in blockers:
        return "inspect_remote_export_shapes_before_hooking"
    if "custom_loader_execution_failed" in blockers:
        return "inspect_custom_loader_execution_failure"
    if "custom_loader_traversal_loop_plan_blocked" in blockers:
        return "revise_custom_loader_traversal_loop_inputs"
    if "async_chunk_traversal_loop_execution_blocked" in blockers:
        return "resolve_async_chunk_traversal_loop_execution_blockers"
    if "async_chunk_traversal_loop_plan_blocked" in blockers:
        return "revise_async_chunk_traversal_loop_inputs"
    if "custom_loader_traversal_workflow_execution_blocked" in blockers:
        return "resolve_custom_loader_traversal_workflow_execution_blockers"
    if "custom_loader_traversal_workflow_plan_blocked" in blockers:
        return "revise_custom_loader_traversal_workflow_plan_inputs"
    if "custom_loader_continuation_workflow_blocked" in blockers:
        return "revise_custom_loader_continuation_workflow_inputs"
    if "custom_loader_continuation_journal_blocked" in blockers:
        return "revise_custom_loader_continuation_journal_inputs"
    if "custom_loader_continuation_execution_blocked" in blockers:
        return "resolve_custom_loader_continuation_execution_blockers"
    if "custom_loader_execution_preflight_blocked" in blockers:
        return "resolve_custom_loader_preflight_blockers"
    if "custom_loader_traversal_graph_blocked" in blockers:
        return "revise_custom_loader_traversal_graph_inputs"
    if "custom_loader_traversal_plan_blocked" in blockers:
        return "choose_supported_async_chunk_or_static_source_path"
    if "async_chunk_traversal_workflow_execution_blocked" in blockers:
        return "resolve_async_chunk_traversal_workflow_execution_blockers"
    if "async_chunk_traversal_workflow_plan_blocked" in blockers:
        return "revise_async_chunk_traversal_workflow_plan_inputs"
    if "async_chunk_traversal_graph_blocked" in blockers:
        return "revise_async_chunk_traversal_graph_inputs"
    if "async_chunk_load_plan_blocked" in blockers:
        return "choose_supported_async_chunk_candidate"
    if "async_chunk_load_failed" in blockers:
        return "inspect_async_chunk_load_failure"
    if "async_chunk_module_diff_blocked" in blockers:
        return "rerun_module_discovery_after_chunk_load"
    if "custom_loader_module_diff_blocked" in blockers:
        return "rerun_module_discovery_after_custom_loader_execution"
    if "no_hook_artifacts_provided" in warnings:
        return "collect_hook_artifacts_before_review"
    if "module_federation_get_init_requires_review" in warnings:
        return "review_module_federation_get_init_plan"
    if "module_federation_get_init_probe_requires_factory_review" in warnings:
        return "review_module_federation_get_init_probe_before_factory_invocation"
    if "module_federation_factory_exports_require_review" in warnings:
        return "review_module_federation_factory_exports_before_hooking"
    if "module_federation_export_hook_plan_requires_review" in warnings:
        return "review_module_federation_export_hook_plan"
    if "custom_loader_traversal_requires_review" in warnings:
        return "review_custom_loader_traversal_plan"
    if "custom_loader_traversal_loop_plan_requires_review" in warnings:
        return "review_custom_loader_traversal_loop_plan"
    if "custom_loader_traversal_workflow_execution_requires_review" in warnings:
        return "review_custom_loader_traversal_workflow_execution_plan"
    if "custom_loader_traversal_workflow_plan_requires_review" in warnings:
        return "review_custom_loader_traversal_workflow_plan"
    if "custom_loader_traversal_graph_requires_review" in warnings:
        return "review_custom_loader_traversal_graph_queue"
    if "async_chunk_traversal_workflow_execution_requires_review" in warnings:
        return "review_async_chunk_traversal_workflow_execution_plan"
    if "async_chunk_traversal_loop_execution_requires_review" in warnings:
        return "review_async_chunk_traversal_loop_execution_plan"
    if "async_chunk_traversal_loop_plan_requires_review" in warnings:
        return "review_async_chunk_traversal_loop_plan"
    if "async_chunk_traversal_workflow_plan_requires_review" in warnings:
        return "review_async_chunk_traversal_workflow_plan"
    if "async_chunk_traversal_graph_requires_review" in warnings:
        return "review_async_chunk_traversal_graph_queue"
    if "custom_loader_continuation_workflow_required" in warnings:
        return "plan_custom_loader_continuation_workflow"
    if "custom_loader_continuation_workflow_requires_review" in warnings:
        return "review_custom_loader_continuation_workflow"
    if "custom_loader_continuation_journal_requires_review" in warnings:
        return "review_custom_loader_continuation_journal_append"
    if "custom_loader_continuation_execution_required" in warnings:
        return "execute_custom_loader_continuation_step"
    if "custom_loader_continuation_execution_requires_review" in warnings:
        return "review_custom_loader_continuation_execution_plan"
    if "custom_loader_execution_requires_review" in warnings:
        return "execute_custom_loader_with_review_approval"
    if "custom_loader_module_diff_required" in warnings:
        return "run_custom_loader_module_diff_after_reviewed_execution"
    if "custom_loader_module_diff_requires_review" in warnings:
        return "review_custom_loader_module_diff_hook_candidates"
    if "async_chunk_load_requires_review" in warnings:
        return "review_async_chunk_load_plan_before_execution"
    if "async_chunk_module_diff_required" in warnings:
        return "run_async_chunk_module_diff_after_reviewed_load"
    if "async_chunk_module_diff_requires_review" in warnings:
        return "review_async_chunk_module_diff_hook_candidates"
    if "hook_targets_missing" in warnings:
        return "adjust_missing_hook_paths_or_module_exports"
    if "installed_hooks_without_timeline_events" in warnings:
        return "invoke_hooked_targets_or_wait_for_runtime_events"
    if "candidates_without_installed_hooks" in warnings:
        return "install_reviewed_hook_from_candidate_before_capture"
    if warnings:
        return "inspect_hook_warnings"
    return "hook_review_passed"


def _review_required_items(
    blockers: list[str],
    warnings: list[str],
    function_hooks: dict[str, Any],
    module_hooks: dict[str, Any],
    source_logpoints: dict[str, Any],
    async_chunk_plan: dict[str, Any],
    async_chunk_result: dict[str, Any],
    async_chunk_module_diff: dict[str, Any],
    async_chunk_traversal_graph: dict[str, Any],
    async_chunk_traversal_workflow_plan: dict[str, Any],
    async_chunk_traversal_workflow_execution: dict[str, Any],
    async_chunk_traversal_loop_plan: dict[str, Any],
    async_chunk_traversal_loop_execution: dict[str, Any],
    custom_loader_traversal_plan: dict[str, Any],
    custom_loader_traversal_graph: dict[str, Any],
    custom_loader_traversal_workflow_plan: dict[str, Any],
    custom_loader_traversal_workflow_execution: dict[str, Any],
    custom_loader_traversal_loop_plan: dict[str, Any],
    custom_loader_continuation_workflow: dict[str, Any],
    custom_loader_continuation_journal: dict[str, Any],
    custom_loader_continuation_execution: dict[str, Any],
    custom_loader_execution_preflight: dict[str, Any],
    custom_loader_execution_result: dict[str, Any],
    custom_loader_module_diff: dict[str, Any],
    module_federation_get_init_plan: dict[str, Any],
    module_federation_get_init_result: dict[str, Any],
    module_federation_factory_invoke_result: dict[str, Any],
    module_federation_export_hook_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in blockers + warnings:
        if code == "no_hook_artifacts_provided":
            continue
        items.append(
            {
                "code": code,
                "function_hook_status": _status(function_hooks),
                "module_hook_status": _status(module_hooks),
                "source_logpoint_status": _status(source_logpoints),
                "async_chunk_load_plan_status": _status(async_chunk_plan),
                "async_chunk_load_result_status": _status(async_chunk_result),
                "async_chunk_module_diff_status": _status(async_chunk_module_diff) or _nested_status(async_chunk_module_diff, "diff"),
                "async_chunk_traversal_graph_status": _status(async_chunk_traversal_graph) or _nested_status(async_chunk_traversal_graph, "graph"),
                "async_chunk_traversal_workflow_plan_status": _status(async_chunk_traversal_workflow_plan) or _nested_status(async_chunk_traversal_workflow_plan, "workflow_plan"),
                "async_chunk_traversal_workflow_execution_status": _status(async_chunk_traversal_workflow_execution) or _nested_status(async_chunk_traversal_workflow_execution, "execution"),
                "async_chunk_traversal_loop_plan_status": _status(async_chunk_traversal_loop_plan) or _nested_status(async_chunk_traversal_loop_plan, "loop_plan"),
                "async_chunk_traversal_loop_execution_status": _status(async_chunk_traversal_loop_execution) or _nested_status(async_chunk_traversal_loop_execution, "execution"),
                "custom_loader_traversal_plan_status": _status(custom_loader_traversal_plan) or _nested_status(custom_loader_traversal_plan, "plan"),
                "custom_loader_traversal_graph_status": _status(custom_loader_traversal_graph) or _nested_status(custom_loader_traversal_graph, "graph"),
                "custom_loader_traversal_workflow_plan_status": _status(custom_loader_traversal_workflow_plan) or _nested_status(custom_loader_traversal_workflow_plan, "workflow_plan"),
                "custom_loader_traversal_workflow_execution_status": _status(custom_loader_traversal_workflow_execution) or _nested_status(custom_loader_traversal_workflow_execution, "execution"),
                "custom_loader_traversal_loop_plan_status": _status(custom_loader_traversal_loop_plan) or _nested_status(custom_loader_traversal_loop_plan, "loop_plan"),
                "custom_loader_continuation_workflow_status": _status(custom_loader_continuation_workflow) or _nested_status(custom_loader_continuation_workflow, "workflow"),
                "custom_loader_continuation_journal_status": _status(custom_loader_continuation_journal) or _nested_status(custom_loader_continuation_journal, "journal"),
                "custom_loader_continuation_execution_status": _status(custom_loader_continuation_execution) or _nested_status(custom_loader_continuation_execution, "execution"),
                "custom_loader_execution_preflight_status": _status(custom_loader_execution_preflight) or _nested_status(custom_loader_execution_preflight, "preflight"),
                "custom_loader_execution_result_status": _status(custom_loader_execution_result),
                "custom_loader_module_diff_status": _status(custom_loader_module_diff) or _nested_status(custom_loader_module_diff, "diff"),
                "module_federation_get_init_plan_status": _status(module_federation_get_init_plan) or _nested_status(module_federation_get_init_plan, "plan"),
                "module_federation_get_init_result_status": _status(module_federation_get_init_result),
                "module_federation_factory_invoke_result_status": _status(module_federation_factory_invoke_result),
                "module_federation_export_hook_plan_status": _status(module_federation_export_hook_plan) or _nested_status(module_federation_export_hook_plan, "plan"),
                "function_hook_error": str(function_hooks.get("error") or ""),
                "module_hook_error": str(module_hooks.get("error") or ""),
                "source_logpoint_error": str(source_logpoints.get("error") or ""),
                "async_chunk_load_error": str(async_chunk_result.get("error") or async_chunk_plan.get("error") or ""),
                "async_chunk_module_diff_error": str(async_chunk_module_diff.get("error") or ""),
                "async_chunk_traversal_graph_error": str(async_chunk_traversal_graph.get("error") or ""),
                "async_chunk_traversal_workflow_plan_error": str(async_chunk_traversal_workflow_plan.get("error") or ""),
                "async_chunk_traversal_workflow_execution_error": str(async_chunk_traversal_workflow_execution.get("error") or ""),
                "async_chunk_traversal_loop_plan_error": str(async_chunk_traversal_loop_plan.get("error") or ""),
                "async_chunk_traversal_loop_execution_error": str(async_chunk_traversal_loop_execution.get("error") or ""),
                "custom_loader_traversal_error": str(custom_loader_traversal_plan.get("error") or ""),
                "custom_loader_traversal_graph_error": str(custom_loader_traversal_graph.get("error") or ""),
                "custom_loader_traversal_workflow_plan_error": str(custom_loader_traversal_workflow_plan.get("error") or ""),
                "custom_loader_traversal_workflow_execution_error": str(custom_loader_traversal_workflow_execution.get("error") or ""),
                "custom_loader_traversal_loop_plan_error": str(custom_loader_traversal_loop_plan.get("error") or ""),
                "custom_loader_continuation_workflow_error": str(custom_loader_continuation_workflow.get("error") or ""),
                "custom_loader_continuation_journal_error": str(custom_loader_continuation_journal.get("error") or ""),
                "custom_loader_continuation_execution_error": str(custom_loader_continuation_execution.get("error") or ""),
                "custom_loader_execution_error": str(custom_loader_execution_result.get("error") or custom_loader_execution_preflight.get("error") or ""),
                "custom_loader_module_diff_error": str(custom_loader_module_diff.get("error") or ""),
                "module_federation_get_init_error": str(module_federation_get_init_result.get("error") or module_federation_get_init_plan.get("error") or ""),
                "module_federation_factory_error": str(module_federation_factory_invoke_result.get("error") or ""),
                "module_federation_export_hook_error": str(module_federation_export_hook_plan.get("error") or ""),
            }
        )
    return items
