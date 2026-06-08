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
        closure_wrapper_replacement_plan = _object_alias(
            payload,
            "closure_wrapper_replacement_plan",
            "closure-wrapper-replacement-plan",
            "closureWrapperReplacementPlan",
            "closure_wrapper_preflight",
            "closureWrapperPreflight",
        )
        closure_wrapper_assignment_safety = _object_alias(
            payload,
            "closure_wrapper_assignment_safety",
            "closure-wrapper-assignment-safety",
            "closureWrapperAssignmentSafety",
            "closure_wrapper_assignment_safety_proof",
            "closureWrapperAssignmentSafetyProof",
        )
        closure_wrapper_runtime_mutability_preflight = _object_alias(
            payload,
            "closure_wrapper_runtime_mutability_preflight",
            "closure-wrapper-runtime-mutability-preflight",
            "closureWrapperRuntimeMutabilityPreflight",
            "closure_wrapper_mutability_preflight",
            "closureWrapperMutabilityPreflight",
        )
        closure_wrapper_runtime_mutability_result = _object_alias(
            payload,
            "closure_wrapper_runtime_mutability_result",
            "closure-wrapper-runtime-mutability-result",
            "closureWrapperRuntimeMutabilityResult",
            "closure_wrapper_runtime_mutability_probe_result",
            "closure-wrapper-runtime-mutability-probe-result",
            "closureWrapperRuntimeMutabilityProbeResult",
            "closure_wrapper_mutability_result",
            "closureWrapperMutabilityResult",
        )
        closure_wrapper_replacement_execution = _object_alias(
            payload,
            "closure_wrapper_replacement_execution",
            "closure-wrapper-replacement-execution",
            "closureWrapperReplacementExecution",
            "reviewed_closure_wrapper_replacement",
            "reviewedClosureWrapperReplacement",
        )
        closure_wrapper_restore_execution = _object_alias(
            payload,
            "closure_wrapper_restore_execution",
            "closure-wrapper-restore-execution",
            "closureWrapperRestoreExecution",
            "reviewed_closure_wrapper_restore",
            "reviewedClosureWrapperRestore",
        )
        closure_wrapper_events = _object_alias(
            payload,
            "closure_wrapper_events",
            "closure-wrapper-events",
            "closureWrapperEvents",
            "closure_wrapper_event_harvest",
            "closureWrapperEventHarvest",
        )
        closure_wrapper_continuation_readiness = _object_alias(
            payload,
            "closure_wrapper_continuation_readiness",
            "closure-wrapper-continuation-readiness",
            "closureWrapperContinuationReadiness",
            "wrapper_continuation_readiness",
            "wrapperContinuationReadiness",
            "review_closure_wrapper_continuation",
            "reviewClosureWrapperContinuation",
        )
        closure_wrapper_continuation_execution_plan = _object_alias(
            payload,
            "closure_wrapper_continuation_execution_plan",
            "closure-wrapper-continuation-execution-plan",
            "closureWrapperContinuationExecutionPlan",
            "wrapper_continuation_execution_plan",
            "wrapperContinuationExecutionPlan",
            "plan_closure_wrapper_continuation_execution",
            "planClosureWrapperContinuationExecution",
        )
        closure_wrapper_continuation_execution = _object_alias(
            payload,
            "closure_wrapper_continuation_execution",
            "closure-wrapper-continuation-execution",
            "closureWrapperContinuationExecution",
            "execute_closure_wrapper_continuation",
            "executeClosureWrapperContinuation",
            "wrapper_continuation_execution",
            "wrapperContinuationExecution",
        )
        closure_wrapper_continuation_checkpoint = _object_alias(
            payload,
            "closure_wrapper_continuation_checkpoint",
            "closure-wrapper-continuation-checkpoint",
            "closureWrapperContinuationCheckpoint",
            "checkpoint_closure_wrapper_continuation",
            "checkpointClosureWrapperContinuation",
            "wrapper_continuation_checkpoint",
            "wrapperContinuationCheckpoint",
        )
        closure_wrapper_continuation_next_iteration_plan = _object_alias(
            payload,
            "closure_wrapper_continuation_next_iteration_plan",
            "closure-wrapper-continuation-next-iteration-plan",
            "closureWrapperContinuationNextIterationPlan",
            "plan_closure_wrapper_continuation_next_iteration",
            "planClosureWrapperContinuationNextIteration",
            "wrapper_continuation_next_iteration_plan",
            "wrapperContinuationNextIterationPlan",
        )
        closure_wrapper_continuation_next_iteration_execution = _object_alias(
            payload,
            "closure_wrapper_continuation_next_iteration_execution",
            "closure-wrapper-continuation-next-iteration-execution",
            "closureWrapperContinuationNextIterationExecution",
            "execute_closure_wrapper_continuation_next_iteration",
            "executeClosureWrapperContinuationNextIteration",
            "wrapper_continuation_next_iteration_execution",
            "wrapperContinuationNextIterationExecution",
        )
        async_chunk_plan = _object_alias(payload, "async_chunk_load_plan", "async-chunk-load-plan", "asyncChunkLoadPlan")
        async_chunk_result = _object_alias(payload, "async_chunk_load_result", "async-chunk-load-result", "asyncChunkLoadResult")
        async_chunk_module_diff = _object_alias(payload, "async_chunk_module_diff", "async-chunk-module-diff", "asyncChunkModuleDiff")
        async_chunk_traversal_graph = _object_alias(payload, "async_chunk_traversal_graph", "async-chunk-traversal-graph", "asyncChunkTraversalGraph")
        async_chunk_traversal_workflow_plan = _object_alias(payload, "async_chunk_traversal_workflow_plan", "async-chunk-traversal-workflow-plan", "asyncChunkTraversalWorkflowPlan")
        async_chunk_traversal_workflow_execution = _object_alias(payload, "async_chunk_traversal_workflow_execution", "async-chunk-traversal-workflow-execution", "asyncChunkTraversalWorkflowExecution")
        async_chunk_traversal_loop_plan = _object_alias(payload, "async_chunk_traversal_loop_plan", "async-chunk-traversal-loop-plan", "asyncChunkTraversalLoopPlan")
        async_chunk_traversal_loop_execution = _object_alias(payload, "async_chunk_traversal_loop_execution", "async-chunk-traversal-loop-execution", "asyncChunkTraversalLoopExecution")
        async_chunk_recursive_traversal_plan = _object_alias(payload, "async_chunk_recursive_traversal_plan", "async-chunk-recursive-traversal-plan", "asyncChunkRecursiveTraversalPlan")
        async_chunk_recursive_traversal_followup = _object_alias(payload, "async_chunk_recursive_traversal_followup", "async-chunk-recursive-traversal-followup", "asyncChunkRecursiveTraversalFollowup")
        async_chunk_recursive_traversal_execution = _object_alias(payload, "async_chunk_recursive_traversal_execution", "async-chunk-recursive-traversal-execution", "asyncChunkRecursiveTraversalExecution")
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
        custom_loader_traversal_loop_execution = _object_alias(
            payload,
            "custom_loader_traversal_loop_execution",
            "custom-loader-traversal-loop-execution",
            "customLoaderTraversalLoopExecution",
        )
        custom_loader_recursive_traversal_plan = _object_alias(
            payload,
            "custom_loader_recursive_traversal_plan",
            "custom-loader-recursive-traversal-plan",
            "customLoaderRecursiveTraversalPlan",
        )
        custom_loader_recursive_traversal_followup = _object_alias(
            payload,
            "custom_loader_recursive_traversal_followup",
            "custom-loader-recursive-traversal-followup",
            "customLoaderRecursiveTraversalFollowup",
        )
        custom_loader_recursive_traversal_execution = _object_alias(
            payload,
            "custom_loader_recursive_traversal_execution",
            "custom-loader-recursive-traversal-execution",
            "customLoaderRecursiveTraversalExecution",
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
        module_federation_traversal_graph = _object_alias(
            payload,
            "module_federation_traversal_graph",
            "module-federation-traversal-graph",
            "moduleFederationTraversalGraph",
        )
        module_federation_traversal_workflow_plan = _object_alias(
            payload,
            "module_federation_traversal_workflow_plan",
            "module-federation-traversal-workflow-plan",
            "moduleFederationTraversalWorkflowPlan",
        )
        module_federation_traversal_workflow_execution = _object_alias(
            payload,
            "module_federation_traversal_workflow_execution",
            "module-federation-traversal-workflow-execution",
            "moduleFederationTraversalWorkflowExecution",
        )
        module_federation_recursive_traversal_plan = _object_alias(
            payload,
            "module_federation_recursive_traversal_plan",
            "module-federation-recursive-traversal-plan",
            "moduleFederationRecursiveTraversalPlan",
        )
        module_federation_recursive_traversal_followup = _object_alias(
            payload,
            "module_federation_recursive_traversal_followup",
            "module-federation-recursive-traversal-followup",
            "moduleFederationRecursiveTraversalFollowup",
        )
        module_federation_recursive_traversal_execution = _object_alias(
            payload,
            "module_federation_recursive_traversal_execution",
            "module-federation-recursive-traversal-execution",
            "moduleFederationRecursiveTraversalExecution",
        )
        module_federation_recursive_continuation_journal = _object_alias(
            payload,
            "module_federation_recursive_continuation_journal",
            "module-federation-recursive-continuation-journal",
            "moduleFederationRecursiveContinuationJournal",
            "module_federation_recursive_traversal_continuation_journal",
            "module-federation-recursive-traversal-continuation-journal",
            "moduleFederationRecursiveTraversalContinuationJournal",
        )
        module_federation_recursive_continuation_checkpoint = _object_alias(
            payload,
            "module_federation_recursive_continuation_checkpoint",
            "module-federation-recursive-continuation-checkpoint",
            "moduleFederationRecursiveContinuationCheckpoint",
            "module_federation_recursive_traversal_continuation_checkpoint",
            "module-federation-recursive-traversal-continuation-checkpoint",
            "moduleFederationRecursiveTraversalContinuationCheckpoint",
        )
        recursive_continuation_readiness = _object_alias(
            payload,
            "recursive_continuation_readiness",
            "recursive-continuation-readiness",
            "recursiveContinuationReadiness",
            "traversal_continuation_readiness",
            "traversal-continuation-readiness",
            "traversalContinuationReadiness",
        )
        if not recursive_continuation_readiness and payload.get("schema_version") == "reverse-deepagent.recursive-continuation-readiness.v1":
            recursive_continuation_readiness = dict(payload)
        if isinstance(recursive_continuation_readiness.get("readiness"), dict):
            nested_readiness = dict(recursive_continuation_readiness["readiness"])
            if "status" not in nested_readiness and recursive_continuation_readiness.get("status"):
                nested_readiness["status"] = recursive_continuation_readiness.get("status")
            recursive_continuation_readiness = nested_readiness
        bundler_symbol_scope = _object_alias(
            payload,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "source-map-symbol-scope",
            "sourceMapSymbolScope",
        )
        source_map_lookup = _object_alias(
            payload,
            "source_map_lookup",
            "source-map-lookup",
            "sourceMapLookup",
            "source_map_consumer",
            "source-map-consumer",
            "sourceMapConsumer",
        )
        source_map_source_content = _object_alias(
            payload,
            "source_map_source_content",
            "source-map-source-content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "source-map-sources-content",
            "sourceMapSourcesContent",
        )
        source_map_readiness = _object_alias(
            payload,
            "source_map_readiness",
            "source-map-readiness",
            "sourceMapReadiness",
            "source_map_debugger_readiness",
            "source-map-debugger-readiness",
            "sourceMapDebuggerReadiness",
        )
        source_map_consumer_action_plan = _object_alias(
            payload,
            "source_map_consumer_action_plan",
            "source-map-consumer-action-plan",
            "sourceMapConsumerActionPlan",
            "source_map_action_plan",
            "source-map-action-plan",
            "sourceMapActionPlan",
        )
        source_map_consumer_materialization = _object_alias(
            payload,
            "source_map_consumer_materialization",
            "source-map-consumer-materialization",
            "sourceMapConsumerMaterialization",
            "source_map_materialization",
            "source-map-materialization",
            "sourceMapMaterialization",
            "source_map_action_materialization",
            "source-map-action-materialization",
            "sourceMapActionMaterialization",
        )
        source_map_typed_payload_preflight = _object_alias(
            payload,
            "source_map_typed_payload_preflight",
            "source-map-typed-payload-preflight",
            "sourceMapTypedPayloadPreflight",
            "source_map_consumer_typed_payload_preflight",
            "source-map-consumer-typed-payload-preflight",
            "sourceMapConsumerTypedPayloadPreflight",
            "source_map_followthrough_preflight",
            "source-map-followthrough-preflight",
            "sourceMapFollowthroughPreflight",
        )
        source_map_followthrough_review = _object_alias(
            payload,
            "source_map_followthrough_review",
            "source-map-followthrough-review",
            "sourceMapFollowthroughReview",
            "source_map_typed_payload_followthrough_review",
            "source-map-typed-payload-followthrough-review",
            "sourceMapTypedPayloadFollowthroughReview",
            "source_map_consumer_followthrough_review",
            "source-map-consumer-followthrough-review",
            "sourceMapConsumerFollowthroughReview",
        )
        source_map_followthrough_surface_selection = _object_alias(
            payload,
            "source_map_followthrough_surface_selection",
            "source-map-followthrough-surface-selection",
            "sourceMapFollowthroughSurfaceSelection",
            "source_map_followthrough_surface_review",
            "source-map-followthrough-surface-review",
            "sourceMapFollowthroughSurfaceReview",
            "source_map_followthrough_surface_selector",
            "source-map-followthrough-surface-selector",
            "sourceMapFollowthroughSurfaceSelector",
        )
        source_map_selected_executor_input_review = _object_alias(
            payload,
            "source_map_selected_executor_input_review",
            "source-map-selected-executor-input-review",
            "sourceMapSelectedExecutorInputReview",
            "source_map_followthrough_executor_input_review",
            "source-map-followthrough-executor-input-review",
            "sourceMapFollowthroughExecutorInputReview",
            "source_map_selected_followthrough_review",
            "source-map-selected-followthrough-review",
            "sourceMapSelectedFollowthroughReview",
        )
        object_graph_diff = _object_alias(
            payload,
            "object_graph_diff",
            "object-graph-diff",
            "objectGraphDiff",
            "js_object_graph_diff",
            "js-object-graph-diff",
            "jsObjectGraphDiff",
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
                closure_wrapper_replacement_plan,
                closure_wrapper_assignment_safety,
                closure_wrapper_runtime_mutability_preflight,
                closure_wrapper_runtime_mutability_result,
                closure_wrapper_replacement_execution,
                closure_wrapper_restore_execution,
                closure_wrapper_events,
                closure_wrapper_continuation_readiness,
                closure_wrapper_continuation_execution_plan,
                closure_wrapper_continuation_execution,
                closure_wrapper_continuation_checkpoint,
                closure_wrapper_continuation_next_iteration_plan,
                closure_wrapper_continuation_next_iteration_execution,
                async_chunk_plan,
                async_chunk_result,
                async_chunk_module_diff,
                async_chunk_traversal_graph,
                async_chunk_traversal_workflow_plan,
                async_chunk_traversal_workflow_execution,
                async_chunk_traversal_loop_plan,
                async_chunk_traversal_loop_execution,
                async_chunk_recursive_traversal_plan,
                async_chunk_recursive_traversal_followup,
                async_chunk_recursive_traversal_execution,
                custom_loader_traversal_plan,
                custom_loader_traversal_graph,
                custom_loader_traversal_workflow_plan,
                custom_loader_traversal_workflow_execution,
                custom_loader_traversal_loop_plan,
                custom_loader_traversal_loop_execution,
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
                module_federation_traversal_graph,
                module_federation_traversal_workflow_plan,
                module_federation_traversal_workflow_execution,
                module_federation_recursive_traversal_plan,
                module_federation_recursive_traversal_followup,
                module_federation_recursive_traversal_execution,
                module_federation_recursive_continuation_journal,
                module_federation_recursive_continuation_checkpoint,
                recursive_continuation_readiness,
                bundler_symbol_scope,
                source_map_lookup,
                source_map_source_content,
                source_map_readiness,
                source_map_consumer_action_plan,
                source_map_consumer_materialization,
                source_map_typed_payload_preflight,
                source_map_followthrough_review,
                source_map_followthrough_surface_selection,
                source_map_selected_executor_input_review,
                object_graph_diff,
                closure_wrapper_continuation_readiness,
                closure_wrapper_continuation_execution_plan,
                closure_wrapper_continuation_execution,
                closure_wrapper_continuation_checkpoint,
                closure_wrapper_continuation_next_iteration_plan,
                closure_wrapper_continuation_next_iteration_execution,
            )
        ) + sum(bool(items) for items in (module_candidates, function_candidates))
        if not artifact_count:
            warnings.append("no_hook_artifacts_provided")
        if any(_status(item) in {"failed", "failure", "error", "unsupported"} for item in (function_hooks, module_hooks, source_logpoints, generic_timeline)):
            blockers.append("hook_artifact_reports_failure")
        if _status(async_chunk_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_load_plan_blocked")
        if _status(bundler_symbol_scope) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("bundler_symbol_scope_blocked")
        if _status(source_map_lookup) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_lookup_blocked")
        if _status(source_map_source_content) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_source_content_blocked")
        if _status(source_map_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_readiness_blocked")
        if _status(source_map_consumer_action_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_consumer_action_plan_blocked")
        if _status(source_map_consumer_materialization) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_consumer_materialization_blocked")
        if _status(source_map_typed_payload_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_typed_payload_preflight_blocked")
        if _status(source_map_followthrough_review) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_review_blocked")
        if _status(source_map_followthrough_surface_selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_surface_selection_blocked")
        if _status(source_map_selected_executor_input_review) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_input_review_blocked")
        if _status(object_graph_diff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("object_graph_diff_blocked")
        if _status(closure_wrapper_replacement_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_replacement_plan_blocked")
        if _status(closure_wrapper_assignment_safety) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_assignment_safety_blocked")
        if _status(closure_wrapper_runtime_mutability_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_runtime_mutability_preflight_blocked")
        if _status(closure_wrapper_runtime_mutability_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_runtime_mutability_result_blocked")
        if _status(closure_wrapper_replacement_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_replacement_execution_blocked")
        if _status(closure_wrapper_restore_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_restore_execution_blocked")
        if _status(closure_wrapper_continuation_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_readiness_blocked")
        if _status(closure_wrapper_continuation_execution_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_execution_plan_blocked")
        if _status(closure_wrapper_continuation_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_execution_blocked")
        if _status(closure_wrapper_continuation_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_checkpoint_blocked")
        if _status(closure_wrapper_continuation_next_iteration_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_next_iteration_plan_blocked")
        if _status(closure_wrapper_continuation_next_iteration_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("closure_wrapper_continuation_next_iteration_execution_blocked")
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
        if _status(async_chunk_recursive_traversal_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_recursive_traversal_plan_blocked")
        if _status(async_chunk_recursive_traversal_followup) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_recursive_traversal_followup_blocked")
        if _status(async_chunk_recursive_traversal_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("async_chunk_recursive_traversal_execution_blocked")
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
        if _status(custom_loader_traversal_loop_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_traversal_loop_execution_blocked")
        if _status(custom_loader_recursive_traversal_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_recursive_traversal_plan_blocked")
        if _status(custom_loader_recursive_traversal_followup) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_recursive_traversal_followup_blocked")
        if _status(custom_loader_recursive_traversal_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("custom_loader_recursive_traversal_execution_blocked")
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
        async_chunk_recursive_traversal_plan_status = _nested_status(async_chunk_recursive_traversal_plan, "recursive_plan")
        async_chunk_recursive_traversal_followup_status = _nested_status(async_chunk_recursive_traversal_followup, "followup")
        async_chunk_recursive_traversal_execution_status = _nested_status(async_chunk_recursive_traversal_execution, "execution")
        custom_loader_plan_status = _nested_status(custom_loader_traversal_plan, "plan")
        custom_loader_graph_status = _nested_status(custom_loader_traversal_graph, "graph")
        custom_loader_traversal_workflow_plan_status = _nested_status(custom_loader_traversal_workflow_plan, "workflow_plan")
        custom_loader_traversal_workflow_execution_status = _nested_status(custom_loader_traversal_workflow_execution, "execution")
        custom_loader_traversal_loop_plan_status = _nested_status(custom_loader_traversal_loop_plan, "loop_plan")
        custom_loader_traversal_loop_execution_status = _nested_status(custom_loader_traversal_loop_execution, "execution")
        custom_loader_recursive_traversal_plan_status = _nested_status(custom_loader_recursive_traversal_plan, "recursive_plan")
        custom_loader_recursive_traversal_followup_status = _nested_status(custom_loader_recursive_traversal_followup, "followup")
        custom_loader_recursive_traversal_execution_status = _nested_status(custom_loader_recursive_traversal_execution, "execution")
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
        if custom_loader_traversal_loop_execution and (
            _status(custom_loader_traversal_loop_execution) in {"ready_for_review", "continuation_workflow_ready", "continuation_workflow_approved"}
            or custom_loader_traversal_loop_execution_status in {"ready_for_review", "continuation_workflow_ready", "continuation_workflow_approved"}
        ):
            warnings.append("custom_loader_traversal_loop_execution_requires_review")
        if custom_loader_recursive_traversal_plan and (
            _status(custom_loader_recursive_traversal_plan) in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_loop_review"}
            or custom_loader_recursive_traversal_plan_status in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_loop_review"}
        ):
            warnings.append("custom_loader_recursive_traversal_plan_requires_review")
        if custom_loader_recursive_traversal_followup and (
            _status(custom_loader_recursive_traversal_followup) in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_loop_plan_ready"}
            or custom_loader_recursive_traversal_followup_status in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_loop_plan_ready"}
        ):
            warnings.append("custom_loader_recursive_traversal_followup_requires_review")
        if custom_loader_recursive_traversal_execution and (
            _status(custom_loader_recursive_traversal_execution) in {"ready_for_review", "next_loop_execution_progressed", "next_loop_journal_appended"}
            or custom_loader_recursive_traversal_execution_status in {"ready_for_review", "next_loop_execution_progressed", "next_loop_journal_appended"}
        ):
            warnings.append("custom_loader_recursive_traversal_execution_requires_review")
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
        if _status(module_federation_traversal_graph) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_traversal_graph_blocked")
        if _status(module_federation_traversal_workflow_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_traversal_workflow_plan_blocked")
        if _status(module_federation_traversal_workflow_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_traversal_workflow_execution_blocked")
        if _status(module_federation_recursive_traversal_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_recursive_traversal_plan_blocked")
        if _status(module_federation_recursive_traversal_followup) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_recursive_traversal_followup_blocked")
        if _status(module_federation_recursive_traversal_execution) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_recursive_traversal_execution_blocked")
        if _status(module_federation_recursive_continuation_journal) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_recursive_continuation_journal_blocked")
        if _status(module_federation_recursive_continuation_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("module_federation_recursive_continuation_checkpoint_blocked")
        if _status(recursive_continuation_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("recursive_continuation_readiness_blocked")
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
        federation_traversal_graph_status = _nested_status(module_federation_traversal_graph, "graph")
        if module_federation_traversal_graph and not module_federation_traversal_workflow_plan and (
            _status(module_federation_traversal_graph) == "ready_for_review"
            or federation_traversal_graph_status == "ready_for_review"
        ):
            warnings.append("module_federation_traversal_graph_requires_review")
        federation_traversal_workflow_status = _nested_status(module_federation_traversal_workflow_plan, "workflow_plan")
        if module_federation_traversal_workflow_plan and not module_federation_traversal_workflow_execution and (
            _status(module_federation_traversal_workflow_plan) == "ready_for_review"
            or federation_traversal_workflow_status == "ready_for_review"
        ):
            warnings.append("module_federation_traversal_workflow_plan_requires_review")
        federation_traversal_execution_status = _nested_status(module_federation_traversal_workflow_execution, "execution")
        if module_federation_traversal_workflow_execution and (
            _status(module_federation_traversal_workflow_execution) == "ready_for_review"
            or federation_traversal_execution_status == "ready_for_review"
        ):
            warnings.append("module_federation_traversal_workflow_execution_requires_review")
        if module_federation_traversal_workflow_execution and federation_traversal_execution_status in {"factory_invoke_success", "export_hook_plan_ready"}:
            warnings.append("module_federation_traversal_workflow_execution_next_stage_requires_review")
        federation_recursive_plan_status = _nested_status(module_federation_recursive_traversal_plan, "recursive_plan")
        if module_federation_recursive_traversal_plan and (
            _status(module_federation_recursive_traversal_plan) in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_step_review"}
            or federation_recursive_plan_status in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_step_review"}
        ):
            warnings.append("module_federation_recursive_traversal_plan_requires_review")
        federation_recursive_followup_status = _nested_status(module_federation_recursive_traversal_followup, "followup")
        if module_federation_recursive_traversal_followup and (
            _status(module_federation_recursive_traversal_followup) in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_step_review_ready"}
            or federation_recursive_followup_status in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_step_review_ready"}
        ):
            warnings.append("module_federation_recursive_traversal_followup_requires_review")
        federation_recursive_execution_status = _nested_status(module_federation_recursive_traversal_execution, "execution")
        federation_recursive_continuation_journal_status = _nested_status(module_federation_recursive_continuation_journal, "journal")
        federation_recursive_continuation_checkpoint_status = _nested_status(module_federation_recursive_continuation_checkpoint, "checkpoint")
        if module_federation_recursive_traversal_execution and (
            _status(module_federation_recursive_traversal_execution) in {"ready_for_review", "next_step_execution_progressed", "next_step_export_hook_plan_ready", "next_step_export_hook_installed"}
            or federation_recursive_execution_status in {"ready_for_review", "next_step_execution_progressed", "next_step_export_hook_plan_ready", "next_step_export_hook_installed"}
        ):
            warnings.append("module_federation_recursive_traversal_execution_requires_review")
        if module_federation_recursive_continuation_journal and (
            _status(module_federation_recursive_continuation_journal) in {"ready_for_review", "journal_appended"}
            or federation_recursive_continuation_journal_status in {"ready_for_review", "journal_appended"}
        ):
            warnings.append("module_federation_recursive_continuation_journal_requires_review")
        if module_federation_recursive_continuation_checkpoint and (
            _status(module_federation_recursive_continuation_checkpoint) in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_execution_review_ready", "complete"}
            or federation_recursive_continuation_checkpoint_status in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_execution_review_ready", "complete"}
        ):
            warnings.append("module_federation_recursive_continuation_checkpoint_requires_review")
        if recursive_continuation_readiness and _status(recursive_continuation_readiness) == "ready_for_review":
            warnings.append("recursive_continuation_readiness_requires_review")
        if closure_wrapper_continuation_readiness and (
            _status(closure_wrapper_continuation_readiness) == "ready_for_review"
            or _nested_status(closure_wrapper_continuation_readiness, "readiness") == "ready_for_review"
        ):
            warnings.append("closure_wrapper_continuation_readiness_requires_review")
        if closure_wrapper_continuation_execution_plan and (
            _status(closure_wrapper_continuation_execution_plan) == "ready_for_review"
            or _nested_status(closure_wrapper_continuation_execution_plan, "plan") == "ready_for_review"
        ):
            warnings.append("closure_wrapper_continuation_execution_plan_requires_review")
        if closure_wrapper_continuation_execution and _status(closure_wrapper_continuation_execution) in {"ready_for_review", "review_required"}:
            warnings.append("closure_wrapper_continuation_execution_requires_review")
        if closure_wrapper_continuation_execution and _status(closure_wrapper_continuation_execution) == "executed" and not closure_wrapper_continuation_checkpoint:
            warnings.append("closure_wrapper_continuation_execution_requires_event_harvest_and_checkpoint")
        if closure_wrapper_continuation_checkpoint and (
            _status(closure_wrapper_continuation_checkpoint) == "ready_for_review"
            or _nested_status(closure_wrapper_continuation_checkpoint, "checkpoint") == "ready_for_review"
        ):
            warnings.append("closure_wrapper_continuation_checkpoint_requires_review")
        if closure_wrapper_continuation_next_iteration_plan and (
            _status(closure_wrapper_continuation_next_iteration_plan) == "ready_for_review"
            or _nested_status(closure_wrapper_continuation_next_iteration_plan, "plan") == "ready_for_review"
        ):
            warnings.append("closure_wrapper_continuation_next_iteration_plan_requires_review")
        if closure_wrapper_continuation_next_iteration_execution and _status(closure_wrapper_continuation_next_iteration_execution) in {"ready_for_review", "review_required"}:
            warnings.append("closure_wrapper_continuation_next_iteration_execution_requires_review")
        if (
            closure_wrapper_continuation_next_iteration_execution
            and _status(closure_wrapper_continuation_next_iteration_execution) == "executed"
            and not closure_wrapper_continuation_checkpoint
        ):
            warnings.append("closure_wrapper_continuation_next_iteration_execution_requires_event_harvest_and_checkpoint")
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
        if async_chunk_recursive_traversal_plan and (
            _status(async_chunk_recursive_traversal_plan) in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_loop_review"}
            or async_chunk_recursive_traversal_plan_status in {"ready_for_graph_rebuild", "ready_for_workflow_replan", "ready_for_next_loop_review"}
        ):
            warnings.append("async_chunk_recursive_traversal_plan_requires_review")
        if async_chunk_recursive_traversal_followup and (
            _status(async_chunk_recursive_traversal_followup) in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_loop_plan_ready"}
            or async_chunk_recursive_traversal_followup_status in {"ready_for_review", "graph_rebuilt", "workflow_replanned", "next_loop_plan_ready"}
        ):
            warnings.append("async_chunk_recursive_traversal_followup_requires_review")
        if async_chunk_recursive_traversal_execution and (
            _status(async_chunk_recursive_traversal_execution) in {"ready_for_review", "next_loop_execution_progressed", "next_loop_module_diff_ready", "next_loop_module_hook_recorded"}
            or async_chunk_recursive_traversal_execution_status in {"ready_for_review", "next_loop_execution_progressed", "next_loop_module_diff_ready", "next_loop_module_hook_recorded"}
        ):
            warnings.append("async_chunk_recursive_traversal_execution_requires_review")
        if bundler_symbol_scope and _status(bundler_symbol_scope) == "ready_for_review":
            warnings.append("bundler_symbol_scope_requires_review")
        if source_map_lookup and _status(source_map_lookup) == "ready_for_review":
            warnings.append("source_map_lookup_requires_review")
        if source_map_source_content and _status(source_map_source_content) == "ready_for_review":
            warnings.append("source_map_source_content_requires_review")
        if source_map_readiness and _status(source_map_readiness) == "ready_for_review":
            warnings.append("source_map_readiness_requires_review")
        if source_map_consumer_action_plan and _status(source_map_consumer_action_plan) == "ready_for_review":
            warnings.append("source_map_consumer_action_plan_requires_review")
        if source_map_consumer_materialization and _status(source_map_consumer_materialization) == "ready_for_review":
            warnings.append("source_map_consumer_materialization_requires_review")
        if source_map_typed_payload_preflight and _status(source_map_typed_payload_preflight) == "ready_for_review":
            warnings.append("source_map_typed_payload_preflight_requires_review")
        if source_map_followthrough_review and _status(source_map_followthrough_review) == "ready_for_review":
            warnings.append("source_map_followthrough_review_requires_review")
        if source_map_followthrough_surface_selection and _status(source_map_followthrough_surface_selection) == "ready_for_review":
            warnings.append("source_map_followthrough_surface_selection_requires_review")
        if source_map_selected_executor_input_review and _status(source_map_selected_executor_input_review) == "ready_for_review":
            warnings.append("source_map_selected_executor_input_review_requires_review")
        if object_graph_diff and _status(object_graph_diff) == "ready_for_review":
            warnings.append("object_graph_diff_requires_review")
        if missing_count:
            warnings.append("hook_targets_missing")
        if installed_function_count + installed_module_count + source_logpoint_count > 0 and timeline_event_count == 0:
            warnings.append("installed_hooks_without_timeline_events")
        if candidate_count and installed_function_count + installed_module_count == 0:
            warnings.append("candidates_without_installed_hooks")
        closure_wrapper_plan_status = _nested_status(closure_wrapper_replacement_plan, "plan")
        closure_wrapper_assignment_safety_status = _status(closure_wrapper_assignment_safety) or _nested_status(closure_wrapper_assignment_safety, "assignment_safety")
        closure_wrapper_assignment_safety_proven = bool(_nested_get(closure_wrapper_assignment_safety, "assignment_safety", "assignment_safety_proven") or closure_wrapper_assignment_safety.get("assignment_safety_proven"))
        if closure_wrapper_replacement_plan and (
            _status(closure_wrapper_replacement_plan) == "ready_for_review"
            or closure_wrapper_plan_status == "ready_for_review"
        ) and not closure_wrapper_assignment_safety_proven:
            warnings.append("closure_wrapper_replacement_plan_requires_review")
        if closure_wrapper_assignment_safety and closure_wrapper_assignment_safety_status == "ready_for_review":
            warnings.append("closure_wrapper_assignment_safety_requires_execution_review")
        closure_wrapper_runtime_mutability_preflight_status = _status(closure_wrapper_runtime_mutability_preflight) or _nested_status(closure_wrapper_runtime_mutability_preflight, "preflight")
        if closure_wrapper_runtime_mutability_preflight and closure_wrapper_runtime_mutability_preflight_status == "ready_for_review" and not closure_wrapper_runtime_mutability_result:
            warnings.append("closure_wrapper_runtime_mutability_preflight_requires_probe_review")
        closure_wrapper_runtime_mutability_result_status = _status(closure_wrapper_runtime_mutability_result) or _nested_status(closure_wrapper_runtime_mutability_result, "result")
        if closure_wrapper_runtime_mutability_result_status == "proven":
            warnings.append("closure_wrapper_runtime_mutability_result_requires_replacement_review")
        closure_wrapper_execution_status = _status(closure_wrapper_replacement_execution) or _nested_status(closure_wrapper_replacement_execution, "execution")
        if closure_wrapper_execution_status == "applied":
            warnings.append("closure_wrapper_replacement_execution_restore_review_required")
        closure_wrapper_restore_execution_status = _status(closure_wrapper_restore_execution) or _nested_status(closure_wrapper_restore_execution, "execution")
        if closure_wrapper_restore_execution_status == "restored":
            warnings.append("closure_wrapper_restore_execution_result_review_required")
        closure_wrapper_strategy_descriptor = _closure_wrapper_strategy_descriptor(
            closure_wrapper_replacement_plan,
            closure_wrapper_assignment_safety,
            closure_wrapper_runtime_mutability_preflight,
            closure_wrapper_runtime_mutability_result,
            closure_wrapper_replacement_execution,
            closure_wrapper_restore_execution,
        )
        if closure_wrapper_strategy_descriptor and (
            closure_wrapper_strategy_descriptor.get("strategy_plan_only") is True
            or closure_wrapper_strategy_descriptor.get("supported_for_install") is False
        ):
            warnings.append("closure_wrapper_strategy_descriptor_plan_only_requires_review")
        closure_wrapper_event_count = _intish(closure_wrapper_events.get("event_count") or closure_wrapper_events.get("eventCount") or _nested_get(closure_wrapper_events, "snapshot", "eventCount"))
        if closure_wrapper_events and closure_wrapper_event_count == 0:
            warnings.append("closure_wrapper_events_empty")

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
                "bundler_symbol_scope_status": _status(bundler_symbol_scope),
                "bundler_symbol_scope_candidate_count": _intish(bundler_symbol_scope.get("scope_candidate_count")),
                "bundler_symbol_scope_next_action": bundler_symbol_scope.get("next_action"),
                "source_map_lookup_status": _status(source_map_lookup),
                "source_map_lookup_mapping_found": bool(source_map_lookup.get("mapping_found", False)),
                "source_map_lookup_next_action": source_map_lookup.get("next_action"),
                "source_map_source_content_status": _status(source_map_source_content),
                "source_map_source_content_available": bool(source_map_source_content.get("source_content_available", False)),
                "source_map_source_content_next_action": source_map_source_content.get("next_action"),
                "source_map_readiness_status": _status(source_map_readiness),
                "source_map_readiness_debugger_location_ready": bool(_nested_get(source_map_readiness, "readiness", "debugger_location_ready")),
                "source_map_readiness_rebuild_source_metadata_ready": bool(_nested_get(source_map_readiness, "readiness", "rebuild_source_metadata_ready")),
                "source_map_readiness_next_action": source_map_readiness.get("next_action"),
                "source_map_consumer_action_plan_status": _status(source_map_consumer_action_plan),
                "source_map_consumer_action_plan_count": _intish(source_map_consumer_action_plan.get("action_plan_count")),
                "source_map_consumer_action_plan_next_action": source_map_consumer_action_plan.get("next_action"),
                "source_map_consumer_materialization_status": _status(source_map_consumer_materialization),
                "source_map_consumer_materialization_count": _intish(source_map_consumer_materialization.get("materialization_count")),
                "source_map_consumer_materialization_next_action": source_map_consumer_materialization.get("next_action"),
                "source_map_typed_payload_preflight_status": _status(source_map_typed_payload_preflight),
                "source_map_typed_payload_preflight_count": _intish(source_map_typed_payload_preflight.get("preflight_payload_count")),
                "source_map_typed_payload_preflight_next_action": source_map_typed_payload_preflight.get("next_action"),
                "source_map_followthrough_review_status": _status(source_map_followthrough_review),
                "source_map_followthrough_review_count": _intish(source_map_followthrough_review.get("followthrough_review_count")),
                "source_map_followthrough_review_next_action": source_map_followthrough_review.get("next_action"),
                "source_map_followthrough_surface_selection_status": _status(source_map_followthrough_surface_selection),
                "source_map_followthrough_surface_selection_selected_consumer": source_map_followthrough_surface_selection.get("selected_consumer"),
                "source_map_followthrough_surface_selection_next_action": source_map_followthrough_surface_selection.get("next_action"),
                "source_map_selected_executor_input_review_status": _status(source_map_selected_executor_input_review),
                "source_map_selected_executor_input_review_selected_consumer": source_map_selected_executor_input_review.get("selected_consumer"),
                "source_map_selected_executor_input_review_next_action": source_map_selected_executor_input_review.get("next_action"),
                "object_graph_diff_status": _status(object_graph_diff),
                "object_graph_diff_change_count": _intish(object_graph_diff.get("change_count") or _nested_get(object_graph_diff, "diff", "change_count")),
                "object_graph_diff_risk": _nested_get(object_graph_diff, "risk_summary", "risk"),
                "object_graph_diff_next_action": object_graph_diff.get("next_action"),
                "missing_hook_target_count": missing_count,
                "candidate_count": candidate_count,
                "closure_wrapper_replacement_plan_status": _status(closure_wrapper_replacement_plan) or closure_wrapper_plan_status,
                "closure_wrapper_replacement_plan_next_action": _nested_get(closure_wrapper_replacement_plan, "plan", "next_action") or closure_wrapper_replacement_plan.get("next_action"),
                "closure_wrapper_strategy": closure_wrapper_strategy_descriptor.get("strategy"),
                "closure_wrapper_strategy_supported_for_install": closure_wrapper_strategy_descriptor.get("supported_for_install"),
                "closure_wrapper_strategy_plan_only": closure_wrapper_strategy_descriptor.get("strategy_plan_only"),
                "closure_wrapper_assignment_safety_status": closure_wrapper_assignment_safety_status,
                "closure_wrapper_assignment_safety_proven": closure_wrapper_assignment_safety_proven,
                "closure_wrapper_assignment_safety_next_action": _nested_get(closure_wrapper_assignment_safety, "assignment_safety", "next_action") or closure_wrapper_assignment_safety.get("next_action"),
                "closure_wrapper_runtime_mutability_preflight_status": closure_wrapper_runtime_mutability_preflight_status,
                "closure_wrapper_runtime_mutability_probe_ready_for_review": bool(_nested_get(closure_wrapper_runtime_mutability_preflight, "preflight", "runtime_mutability_probe_ready_for_review") or closure_wrapper_runtime_mutability_preflight.get("runtime_mutability_probe_ready_for_review")),
                "closure_wrapper_runtime_mutability_preflight_next_action": _nested_get(closure_wrapper_runtime_mutability_preflight, "preflight", "next_action") or closure_wrapper_runtime_mutability_preflight.get("next_action"),
                "closure_wrapper_runtime_mutability_result_status": closure_wrapper_runtime_mutability_result_status,
                "closure_wrapper_runtime_mutability_result_proven": bool(_nested_get(closure_wrapper_runtime_mutability_result, "result", "runtime_mutability_proven") or closure_wrapper_runtime_mutability_result.get("runtime_mutability_proven")),
                "closure_wrapper_runtime_mutability_result_original_restored": bool(_nested_get(closure_wrapper_runtime_mutability_result, "result", "original_restored") or closure_wrapper_runtime_mutability_result.get("original_restored")),
                "closure_wrapper_runtime_mutability_result_next_action": _nested_get(closure_wrapper_runtime_mutability_result, "result", "next_action") or closure_wrapper_runtime_mutability_result.get("next_action"),
                "closure_wrapper_replacement_execution_status": closure_wrapper_execution_status,
                "closure_wrapper_replacement_execution_next_action": _nested_get(closure_wrapper_replacement_execution, "execution", "next_action") or closure_wrapper_replacement_execution.get("next_action"),
                "closure_wrapper_replacement_execution_runtime_mutated": bool(_nested_get(closure_wrapper_replacement_execution, "execution", "runtime_mutated") or closure_wrapper_replacement_execution.get("runtime_mutated")),
                "closure_wrapper_replacement_execution_wrapper_installed": bool(_nested_get(closure_wrapper_replacement_execution, "execution", "wrapper_installed") or closure_wrapper_replacement_execution.get("wrapper_installed")),
                "closure_wrapper_restore_execution_status": closure_wrapper_restore_execution_status,
                "closure_wrapper_restore_execution_next_action": _nested_get(closure_wrapper_restore_execution, "execution", "next_action") or closure_wrapper_restore_execution.get("next_action"),
                "closure_wrapper_restore_execution_runtime_mutated": bool(_nested_get(closure_wrapper_restore_execution, "execution", "runtime_mutated") or closure_wrapper_restore_execution.get("runtime_mutated")),
                "closure_wrapper_restore_execution_wrapper_restored": bool(_nested_get(closure_wrapper_restore_execution, "execution", "wrapper_restored") or closure_wrapper_restore_execution.get("wrapper_restored")),
                "closure_wrapper_event_count": closure_wrapper_event_count,
                "closure_wrapper_continuation_readiness_status": _status(closure_wrapper_continuation_readiness) or _nested_status(closure_wrapper_continuation_readiness, "readiness"),
                "closure_wrapper_continuation_ready": bool(_nested_get(closure_wrapper_continuation_readiness, "readiness", "continuation_ready") or closure_wrapper_continuation_readiness.get("continuation_ready")),
                "closure_wrapper_continuation_automatic_wrapper_continuation": bool(_nested_get(closure_wrapper_continuation_readiness, "readiness", "automatic_wrapper_continuation") or closure_wrapper_continuation_readiness.get("automatic_wrapper_continuation")),
                "closure_wrapper_continuation_next_action": _nested_get(closure_wrapper_continuation_readiness, "readiness", "next_action") or closure_wrapper_continuation_readiness.get("next_action"),
                "closure_wrapper_continuation_execution_plan_status": _status(closure_wrapper_continuation_execution_plan) or _nested_status(closure_wrapper_continuation_execution_plan, "plan"),
                "closure_wrapper_continuation_execution_plan_ready": bool(_nested_get(closure_wrapper_continuation_execution_plan, "plan", "ready_for_review") or closure_wrapper_continuation_execution_plan.get("ready_for_review")),
                "closure_wrapper_continuation_execution_plan_automatic_wrapper_continuation": bool(
                    ((_nested_get(closure_wrapper_continuation_execution_plan, "plan", "execution_strategy") or {}).get("automatic_wrapper_continuation_supported"))
                    or _nested_get(closure_wrapper_continuation_execution_plan, "plan", "automatic_wrapper_continuation")
                ),
                "closure_wrapper_continuation_execution_plan_next_action": _nested_get(closure_wrapper_continuation_execution_plan, "plan", "next_action") or closure_wrapper_continuation_execution_plan.get("next_action"),
                "closure_wrapper_continuation_execution_status": _status(closure_wrapper_continuation_execution) or _nested_status(closure_wrapper_continuation_execution, "execution"),
                "closure_wrapper_continuation_execution_iteration_executed": bool(
                    _nested_get(closure_wrapper_continuation_execution, "execution", "wrapper_continuation_iteration_executed")
                    or closure_wrapper_continuation_execution.get("wrapper_continuation_iteration_executed")
                ),
                "closure_wrapper_continuation_execution_paused_event_captured": bool(
                    _nested_get(closure_wrapper_continuation_execution, "execution", "paused_event_captured")
                    or closure_wrapper_continuation_execution.get("paused_event_captured")
                ),
                "closure_wrapper_continuation_execution_next_action": _nested_get(closure_wrapper_continuation_execution, "execution", "next_action") or closure_wrapper_continuation_execution.get("next_action"),
                "closure_wrapper_continuation_checkpoint_status": _status(closure_wrapper_continuation_checkpoint) or _nested_status(closure_wrapper_continuation_checkpoint, "checkpoint"),
                "closure_wrapper_continuation_checkpoint_ready": bool(
                    _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "ready_for_review")
                    or closure_wrapper_continuation_checkpoint.get("ready_for_review")
                ),
                "closure_wrapper_continuation_checkpoint_event_count": _intish(
                    _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "post_execution_event_count")
                    or closure_wrapper_continuation_checkpoint.get("post_execution_event_count")
                ),
                "closure_wrapper_continuation_checkpoint_next_action": _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "next_action") or closure_wrapper_continuation_checkpoint.get("next_action"),
                "closure_wrapper_continuation_next_iteration_plan_status": _status(closure_wrapper_continuation_next_iteration_plan) or _nested_status(closure_wrapper_continuation_next_iteration_plan, "plan"),
                "closure_wrapper_continuation_next_iteration_plan_ready": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "ready_for_review")
                    or closure_wrapper_continuation_next_iteration_plan.get("ready_for_review")
                ),
                "closure_wrapper_continuation_next_iteration_plan_step_index": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_iteration_step_index")
                or closure_wrapper_continuation_next_iteration_plan.get("next_iteration_step_index"),
                "closure_wrapper_continuation_next_iteration_plan_method": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_iteration_method")
                or closure_wrapper_continuation_next_iteration_plan.get("next_iteration_method"),
                "closure_wrapper_continuation_next_iteration_plan_next_action": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_action")
                or closure_wrapper_continuation_next_iteration_plan.get("next_action"),
                "closure_wrapper_continuation_next_iteration_execution_status": _status(closure_wrapper_continuation_next_iteration_execution)
                or _nested_status(closure_wrapper_continuation_next_iteration_execution, "execution"),
                "closure_wrapper_continuation_next_iteration_execution_executed": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_execution, "execution", "wrapper_next_iteration_executed")
                    or closure_wrapper_continuation_next_iteration_execution.get("wrapper_next_iteration_executed")
                ),
                "closure_wrapper_continuation_next_iteration_execution_paused_event_captured": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_execution, "execution", "paused_event_captured")
                    or closure_wrapper_continuation_next_iteration_execution.get("paused_event_captured")
                ),
                "closure_wrapper_continuation_next_iteration_execution_next_action": _nested_get(
                    closure_wrapper_continuation_next_iteration_execution, "execution", "next_action"
                )
                or closure_wrapper_continuation_next_iteration_execution.get("next_action"),
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
                "async_chunk_recursive_traversal_plan_status": _status(async_chunk_recursive_traversal_plan) or async_chunk_recursive_traversal_plan_status,
                "async_chunk_recursive_traversal_plan_next_action": _nested_get(async_chunk_recursive_traversal_plan, "recursive_plan", "next_action") or async_chunk_recursive_traversal_plan.get("next_action"),
                "async_chunk_recursive_traversal_followup_status": _status(async_chunk_recursive_traversal_followup) or async_chunk_recursive_traversal_followup_status,
                "async_chunk_recursive_traversal_followup_stage_count": len(_listish(_nested_get(async_chunk_recursive_traversal_followup, "followup", "stages") or async_chunk_recursive_traversal_followup.get("stages"))),
                "async_chunk_recursive_traversal_followup_next_action": _nested_get(async_chunk_recursive_traversal_followup, "followup", "next_action") or async_chunk_recursive_traversal_followup.get("next_action"),
                "async_chunk_recursive_traversal_execution_status": _status(async_chunk_recursive_traversal_execution) or async_chunk_recursive_traversal_execution_status,
                "async_chunk_recursive_traversal_execution_stage_count": len(_listish(_nested_get(async_chunk_recursive_traversal_execution, "execution", "stages") or async_chunk_recursive_traversal_execution.get("stages"))),
                "async_chunk_recursive_traversal_execution_next_action": _nested_get(async_chunk_recursive_traversal_execution, "execution", "next_action") or async_chunk_recursive_traversal_execution.get("next_action"),
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
                "custom_loader_traversal_loop_execution_status": _status(custom_loader_traversal_loop_execution) or custom_loader_traversal_loop_execution_status,
                "custom_loader_traversal_loop_execution_stage_count": len(_listish(_nested_get(custom_loader_traversal_loop_execution, "execution", "stages") or custom_loader_traversal_loop_execution.get("stages"))),
                "custom_loader_traversal_loop_execution_next_action": _nested_get(custom_loader_traversal_loop_execution, "execution", "next_action") or custom_loader_traversal_loop_execution.get("next_action"),
                "custom_loader_recursive_traversal_plan_status": _status(custom_loader_recursive_traversal_plan) or custom_loader_recursive_traversal_plan_status,
                "custom_loader_recursive_traversal_plan_next_action": _nested_get(custom_loader_recursive_traversal_plan, "recursive_plan", "next_action") or custom_loader_recursive_traversal_plan.get("next_action"),
                "custom_loader_recursive_traversal_followup_status": _status(custom_loader_recursive_traversal_followup) or custom_loader_recursive_traversal_followup_status,
                "custom_loader_recursive_traversal_followup_stage_count": len(_listish(_nested_get(custom_loader_recursive_traversal_followup, "followup", "stages") or custom_loader_recursive_traversal_followup.get("stages"))),
                "custom_loader_recursive_traversal_followup_next_action": _nested_get(custom_loader_recursive_traversal_followup, "followup", "next_action") or custom_loader_recursive_traversal_followup.get("next_action"),
                "custom_loader_recursive_traversal_execution_status": _status(custom_loader_recursive_traversal_execution) or custom_loader_recursive_traversal_execution_status,
                "custom_loader_recursive_traversal_execution_stage_count": len(_listish(_nested_get(custom_loader_recursive_traversal_execution, "execution", "stages") or custom_loader_recursive_traversal_execution.get("stages"))),
                "custom_loader_recursive_traversal_execution_next_action": _nested_get(custom_loader_recursive_traversal_execution, "execution", "next_action") or custom_loader_recursive_traversal_execution.get("next_action"),
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
                "module_federation_traversal_graph_status": _status(module_federation_traversal_graph) or _nested_status(module_federation_traversal_graph, "graph"),
                "module_federation_traversal_graph_queue_count": _intish(module_federation_traversal_graph.get("queue_count") or _nested_get(module_federation_traversal_graph, "graph", "queue_count")),
                "module_federation_traversal_workflow_plan_status": _status(module_federation_traversal_workflow_plan) or _nested_status(module_federation_traversal_workflow_plan, "workflow_plan"),
                "module_federation_traversal_workflow_planned_step_count": _intish(module_federation_traversal_workflow_plan.get("planned_step_count") or _nested_get(module_federation_traversal_workflow_plan, "workflow_plan", "planned_step_count")),
                "module_federation_traversal_workflow_execution_status": _status(module_federation_traversal_workflow_execution) or _nested_status(module_federation_traversal_workflow_execution, "execution"),
                "module_federation_traversal_workflow_execution_stage_count": len(_listish(_nested_get(module_federation_traversal_workflow_execution, "execution", "stages") or module_federation_traversal_workflow_execution.get("stages"))),
                "module_federation_traversal_workflow_execution_remote_factory_invoked": bool(_nested_get(module_federation_traversal_workflow_execution, "side_effect_policy", "remote_factory_invoked") or (((_nested_get(module_federation_traversal_workflow_execution, "execution", "module_federation_factory_invoke_result") or {}).get("factory_execution") or {}).get("remoteFactoryInvoked"))),
                "module_federation_traversal_workflow_execution_export_hook_installed": bool(_nested_get(module_federation_traversal_workflow_execution, "side_effect_policy", "export_hook_installed") or ((_nested_get(module_federation_traversal_workflow_execution, "execution", "module_federation_export_hook_result") or {}).get("installed_count"))),
                "module_federation_recursive_traversal_plan_status": _status(module_federation_recursive_traversal_plan) or federation_recursive_plan_status,
                "module_federation_recursive_traversal_plan_next_action": _nested_get(module_federation_recursive_traversal_plan, "recursive_plan", "next_action") or module_federation_recursive_traversal_plan.get("next_action"),
                "module_federation_recursive_traversal_followup_status": _status(module_federation_recursive_traversal_followup) or federation_recursive_followup_status,
                "module_federation_recursive_traversal_followup_stage_count": len(_listish(_nested_get(module_federation_recursive_traversal_followup, "followup", "stages") or module_federation_recursive_traversal_followup.get("stages"))),
                "module_federation_recursive_traversal_followup_next_action": _nested_get(module_federation_recursive_traversal_followup, "followup", "next_action") or module_federation_recursive_traversal_followup.get("next_action"),
                "module_federation_recursive_traversal_execution_status": _status(module_federation_recursive_traversal_execution) or federation_recursive_execution_status,
                "module_federation_recursive_traversal_execution_stage_count": len(_listish(_nested_get(module_federation_recursive_traversal_execution, "execution", "stages") or module_federation_recursive_traversal_execution.get("stages"))),
                "module_federation_recursive_traversal_execution_next_action": _nested_get(module_federation_recursive_traversal_execution, "execution", "next_action") or module_federation_recursive_traversal_execution.get("next_action"),
                "module_federation_recursive_continuation_journal_status": _status(module_federation_recursive_continuation_journal) or federation_recursive_continuation_journal_status,
                "module_federation_recursive_continuation_journal_record_count": _intish(module_federation_recursive_continuation_journal.get("record_count") or _nested_get(module_federation_recursive_continuation_journal, "journal", "record_count")),
                "module_federation_recursive_continuation_journal_writes_journal": bool(module_federation_recursive_continuation_journal.get("writes_journal_now") or _nested_get(module_federation_recursive_continuation_journal, "journal", "writes_journal_now")),
                "module_federation_recursive_continuation_journal_next_action": _nested_get(module_federation_recursive_continuation_journal, "journal", "next_action") or module_federation_recursive_continuation_journal.get("next_action"),
                "module_federation_recursive_continuation_checkpoint_status": _status(module_federation_recursive_continuation_checkpoint) or federation_recursive_continuation_checkpoint_status,
                "module_federation_recursive_continuation_checkpoint_stage_count": len(_listish(_nested_get(module_federation_recursive_continuation_checkpoint, "checkpoint", "stages") or module_federation_recursive_continuation_checkpoint.get("stages"))),
                "module_federation_recursive_continuation_checkpoint_next_action": _nested_get(module_federation_recursive_continuation_checkpoint, "checkpoint", "next_action") or module_federation_recursive_continuation_checkpoint.get("next_action"),
                "recursive_continuation_readiness_status": _status(recursive_continuation_readiness),
                "recursive_continuation_readiness_system_count": _intish(recursive_continuation_readiness.get("system_count")),
                "recursive_continuation_readiness_ready_systems": _listish(recursive_continuation_readiness.get("ready_systems")),
                "recursive_continuation_readiness_blocked_systems": _listish(recursive_continuation_readiness.get("blocked_systems")),
                "recursive_continuation_readiness_deeper_recursion_executor_ready": bool(recursive_continuation_readiness.get("deeper_recursion_executor_ready")),
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
                closure_wrapper_replacement_plan,
                closure_wrapper_assignment_safety,
                closure_wrapper_runtime_mutability_preflight,
                closure_wrapper_runtime_mutability_result,
                closure_wrapper_replacement_execution,
                closure_wrapper_restore_execution,
                closure_wrapper_events,
                closure_wrapper_continuation_readiness,
                closure_wrapper_continuation_execution_plan,
                closure_wrapper_continuation_execution,
                closure_wrapper_continuation_checkpoint,
                closure_wrapper_continuation_next_iteration_plan,
                closure_wrapper_continuation_next_iteration_execution,
                async_chunk_plan,
                async_chunk_result,
                async_chunk_module_diff,
                async_chunk_traversal_graph,
                async_chunk_traversal_workflow_plan,
                async_chunk_traversal_workflow_execution,
                async_chunk_traversal_loop_plan,
                async_chunk_traversal_loop_execution,
                async_chunk_recursive_traversal_plan,
                async_chunk_recursive_traversal_followup,
                async_chunk_recursive_traversal_execution,
                custom_loader_traversal_plan,
                custom_loader_traversal_graph,
                custom_loader_traversal_workflow_plan,
                custom_loader_traversal_workflow_execution,
                custom_loader_traversal_loop_plan,
                custom_loader_traversal_loop_execution,
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
                module_federation_traversal_graph,
                module_federation_traversal_workflow_plan,
                module_federation_traversal_workflow_execution,
                module_federation_recursive_traversal_plan,
                module_federation_recursive_traversal_followup,
                module_federation_recursive_traversal_execution,
                module_federation_recursive_continuation_journal,
                module_federation_recursive_continuation_checkpoint,
                recursive_continuation_readiness,
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


def _closure_wrapper_strategy_descriptor(*items: dict[str, Any]) -> dict[str, Any]:
    for item in items:
        if not isinstance(item, dict):
            continue
        direct = item.get("wrapper_strategy_descriptor")
        if isinstance(direct, dict):
            return direct
        for key in ("plan", "assignment_safety", "preflight", "result", "execution"):
            nested = _nested_get(item, key, "wrapper_strategy_descriptor")
            if isinstance(nested, dict):
                return nested
    return {}


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
    if "closure_wrapper_replacement_plan_blocked" in blockers:
        return "resolve_closure_wrapper_replacement_plan_blockers"
    if "closure_wrapper_assignment_safety_blocked" in blockers:
        return "resolve_closure_wrapper_assignment_safety_blockers"
    if "closure_wrapper_runtime_mutability_preflight_blocked" in blockers:
        return "resolve_closure_wrapper_runtime_mutability_preflight_blockers"
    if "closure_wrapper_runtime_mutability_result_blocked" in blockers:
        return "resolve_closure_wrapper_runtime_mutability_result_blockers"
    if "closure_wrapper_replacement_execution_blocked" in blockers:
        return "resolve_closure_wrapper_replacement_execution_blockers"
    if "closure_wrapper_restore_execution_blocked" in blockers:
        return "resolve_closure_wrapper_restore_execution_blockers"
    if "closure_wrapper_continuation_readiness_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_readiness_blockers"
    if "closure_wrapper_continuation_execution_plan_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_execution_plan_blockers"
    if "closure_wrapper_continuation_execution_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_execution_blockers"
    if "closure_wrapper_continuation_checkpoint_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_checkpoint_blockers"
    if "closure_wrapper_continuation_next_iteration_plan_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_next_iteration_plan_blockers"
    if "closure_wrapper_continuation_next_iteration_execution_blocked" in blockers:
        return "resolve_closure_wrapper_continuation_next_iteration_execution_blockers"
    if "module_federation_get_init_plan_blocked" in blockers:
        return "provide_module_federation_candidates_from_module_discovery"
    if "module_federation_get_init_probe_failed" in blockers:
        return "inspect_module_federation_get_init_probe_failure"
    if "module_federation_factory_invoke_failed" in blockers:
        return "inspect_module_federation_factory_invoke_failure"
    if "module_federation_export_hook_plan_blocked" in blockers:
        return "inspect_remote_export_shapes_before_hooking"
    if "module_federation_traversal_graph_blocked" in blockers:
        return "provide_module_federation_traversal_inputs"
    if "module_federation_traversal_workflow_plan_blocked" in blockers:
        return "revise_module_federation_traversal_workflow_plan_inputs"
    if "module_federation_traversal_workflow_execution_blocked" in blockers:
        return "resolve_module_federation_traversal_workflow_execution_blockers"
    if "module_federation_recursive_traversal_plan_blocked" in blockers:
        return "resolve_module_federation_recursive_traversal_blockers"
    if "module_federation_recursive_traversal_followup_blocked" in blockers:
        return "resolve_module_federation_recursive_traversal_followup_blockers"
    if "module_federation_recursive_traversal_execution_blocked" in blockers:
        return "resolve_module_federation_recursive_traversal_execution_blockers"
    if "module_federation_recursive_continuation_journal_blocked" in blockers:
        return "revise_module_federation_recursive_continuation_journal_inputs"
    if "module_federation_recursive_continuation_checkpoint_blocked" in blockers:
        return "resolve_module_federation_recursive_continuation_checkpoint_blockers"
    if "recursive_continuation_readiness_blocked" in blockers:
        return "resolve_recursive_continuation_readiness_blockers"
    if "custom_loader_execution_failed" in blockers:
        return "inspect_custom_loader_execution_failure"
    if "custom_loader_traversal_loop_execution_blocked" in blockers:
        return "resolve_custom_loader_traversal_loop_execution_blockers"
    if "custom_loader_recursive_traversal_followup_blocked" in blockers:
        return "resolve_custom_loader_recursive_traversal_followup_blockers"
    if "custom_loader_recursive_traversal_execution_blocked" in blockers:
        return "resolve_custom_loader_recursive_traversal_execution_blockers"
    if "custom_loader_recursive_traversal_plan_blocked" in blockers:
        return "resolve_custom_loader_recursive_traversal_blockers"
    if "custom_loader_traversal_loop_plan_blocked" in blockers:
        return "revise_custom_loader_traversal_loop_inputs"
    if "async_chunk_traversal_loop_execution_blocked" in blockers:
        return "resolve_async_chunk_traversal_loop_execution_blockers"
    if "async_chunk_recursive_traversal_followup_blocked" in blockers:
        return "resolve_async_chunk_recursive_traversal_followup_blockers"
    if "async_chunk_recursive_traversal_execution_blocked" in blockers:
        return "resolve_async_chunk_recursive_traversal_execution_blockers"
    if "async_chunk_recursive_traversal_plan_blocked" in blockers:
        return "resolve_async_chunk_recursive_traversal_blockers"
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
    if "bundler_symbol_scope_blocked" in blockers:
        return "provide_source_map_symbol_and_original_source"
    if "source_map_lookup_blocked" in blockers:
        return "provide_source_map_payload_and_lookup_position"
    if "source_map_source_content_blocked" in blockers:
        return "provide_source_map_with_sources_content"
    if "source_map_readiness_blocked" in blockers:
        return "provide_source_map_lookup_and_source_content_descriptors"
    if "source_map_consumer_action_plan_blocked" in blockers:
        return "provide_ready_source_map_readiness_descriptor"
    if "source_map_consumer_materialization_blocked" in blockers:
        return "provide_ready_source_map_consumer_action_plan_descriptor"
    if "source_map_typed_payload_preflight_blocked" in blockers:
        return "provide_source_map_consumer_materialization_with_typed_payloads"
    if "source_map_followthrough_review_blocked" in blockers:
        return "provide_ready_source_map_typed_payload_preflight_descriptor"
    if "source_map_followthrough_surface_selection_blocked" in blockers:
        return "provide_ready_source_map_followthrough_review_descriptor"
    if "source_map_selected_executor_input_review_blocked" in blockers:
        return "provide_ready_source_map_followthrough_surface_selection_descriptor"
    if "object_graph_diff_blocked" in blockers:
        return "provide_before_and_after_object_graph_snapshots"
    if "async_chunk_load_failed" in blockers:
        return "inspect_async_chunk_load_failure"
    if "async_chunk_module_diff_blocked" in blockers:
        return "rerun_module_discovery_after_chunk_load"
    if "custom_loader_module_diff_blocked" in blockers:
        return "rerun_module_discovery_after_custom_loader_execution"
    if "module_federation_get_init_requires_review" in warnings:
        return "review_module_federation_get_init_plan"
    if "bundler_symbol_scope_requires_review" in warnings:
        return "review_symbol_scope_before_source_logpoint_or_hook"
    if "source_map_lookup_requires_review" in warnings:
        return "review_source_map_lookup_before_debugger_or_hook_use"
    if "source_map_source_content_requires_review" in warnings:
        return "review_source_content_availability_before_debugger_or_rebuild"
    if "source_map_readiness_requires_review" in warnings:
        return "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning"
    if "source_map_consumer_action_plan_requires_review" in warnings:
        return "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution"
    if "source_map_consumer_materialization_requires_review" in warnings:
        return "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution"
    if "source_map_typed_payload_preflight_requires_review" in warnings:
        return "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution"
    if "source_map_followthrough_review_requires_review" in warnings:
        return "choose_explicit_source_map_followthrough_review_surface"
    if "source_map_followthrough_surface_selection_requires_review" in warnings:
        return "review_selected_source_map_followthrough_surface_before_execution"
    if "source_map_selected_executor_input_review_requires_review" in warnings:
        return "review_source_map_selected_executor_input_before_surface_execution"
    if "object_graph_diff_requires_review" in warnings:
        return "review_object_graph_diff_before_hook_or_replay"
    if "closure_wrapper_strategy_descriptor_plan_only_requires_review" in warnings:
        return "review_closure_wrapper_strategy_descriptor_before_execution"
    if "closure_wrapper_replacement_plan_requires_review" in warnings:
        return "review_closure_wrapper_replacement_plan_before_execution"
    if "closure_wrapper_assignment_safety_requires_execution_review" in warnings:
        return "approve_reviewed_closure_wrapper_replacement_execution_with_assignment_safety_proof"
    if "closure_wrapper_runtime_mutability_preflight_requires_probe_review" in warnings:
        return "review_closure_wrapper_runtime_mutability_probe_before_execution"
    if "closure_wrapper_runtime_mutability_result_requires_replacement_review" in warnings:
        return "review_runtime_mutability_result_then_optionally_execute_closure_wrapper_replacement"
    if "closure_wrapper_replacement_execution_restore_review_required" in warnings:
        return "review_closure_wrapper_restore_plan_or_invoke_target_flow"
    if "closure_wrapper_restore_execution_result_review_required" in warnings:
        return "review_closure_wrapper_restore_execution_result_or_continue_target_flow"
    if "closure_wrapper_events_empty" in warnings:
        return "invoke_target_flow_then_harvest_closure_wrapper_events"
    if "closure_wrapper_continuation_readiness_requires_review" in warnings:
        return "review_wrapper_continuation_readiness"
    if "closure_wrapper_continuation_execution_plan_requires_review" in warnings:
        return "review_closure_wrapper_continuation_execution_plan"
    if "closure_wrapper_continuation_execution_requires_review" in warnings:
        return "approve_closure_wrapper_continuation_iteration"
    if "closure_wrapper_continuation_execution_requires_event_harvest_and_checkpoint" in warnings:
        return "harvest_wrapper_events_and_checkpoint_continuation"
    if "closure_wrapper_continuation_checkpoint_requires_review" in warnings:
        return "review_closure_wrapper_continuation_checkpoint"
    if "closure_wrapper_continuation_next_iteration_plan_requires_review" in warnings:
        return "review_closure_wrapper_continuation_next_iteration_plan"
    if "closure_wrapper_continuation_next_iteration_execution_requires_review" in warnings:
        return "approve_closure_wrapper_next_iteration_execution"
    if "closure_wrapper_continuation_next_iteration_execution_requires_event_harvest_and_checkpoint" in warnings:
        return "harvest_wrapper_events_and_checkpoint_next_iteration"
    if "module_federation_get_init_probe_requires_factory_review" in warnings:
        return "review_module_federation_get_init_probe_before_factory_invocation"
    if "module_federation_factory_exports_require_review" in warnings:
        return "review_module_federation_factory_exports_before_hooking"
    if "module_federation_export_hook_plan_requires_review" in warnings:
        return "review_module_federation_export_hook_plan"
    if "module_federation_traversal_graph_requires_review" in warnings:
        return "review_module_federation_traversal_graph"
    if "module_federation_traversal_workflow_plan_requires_review" in warnings:
        return "review_module_federation_traversal_workflow_plan"
    if "module_federation_traversal_workflow_execution_next_stage_requires_review" in warnings:
        return "review_module_federation_traversal_workflow_execution_next_stage"
    if "module_federation_traversal_workflow_execution_requires_review" in warnings:
        return "review_module_federation_traversal_workflow_execution_plan"
    if "module_federation_recursive_traversal_plan_requires_review" in warnings:
        return "review_module_federation_recursive_traversal_plan"
    if "module_federation_recursive_traversal_followup_requires_review" in warnings:
        return "review_module_federation_recursive_traversal_followup"
    if "module_federation_recursive_traversal_execution_requires_review" in warnings:
        return "review_module_federation_recursive_traversal_execution"
    if "module_federation_recursive_continuation_journal_requires_review" in warnings:
        return "review_module_federation_recursive_continuation_journal_append"
    if "module_federation_recursive_continuation_checkpoint_requires_review" in warnings:
        return "review_module_federation_recursive_continuation_checkpoint"
    if "recursive_continuation_readiness_requires_review" in warnings:
        return "review_recursive_continuation_readiness"
    if "custom_loader_traversal_requires_review" in warnings:
        return "review_custom_loader_traversal_plan"
    if "custom_loader_traversal_loop_plan_requires_review" in warnings:
        return "review_custom_loader_traversal_loop_plan"
    if "custom_loader_traversal_loop_execution_requires_review" in warnings:
        return "review_custom_loader_traversal_loop_execution_plan"
    if "custom_loader_recursive_traversal_followup_requires_review" in warnings:
        return "review_custom_loader_recursive_traversal_followup"
    if "custom_loader_recursive_traversal_execution_requires_review" in warnings:
        return "review_custom_loader_recursive_traversal_execution"
    if "custom_loader_recursive_traversal_plan_requires_review" in warnings:
        return "review_custom_loader_recursive_traversal_plan"
    if "no_hook_artifacts_provided" in warnings:
        return "collect_hook_artifacts_before_review"
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
    if "async_chunk_recursive_traversal_followup_requires_review" in warnings:
        return "review_async_chunk_recursive_traversal_followup"
    if "async_chunk_recursive_traversal_execution_requires_review" in warnings:
        return "review_async_chunk_recursive_traversal_execution"
    if "async_chunk_recursive_traversal_plan_requires_review" in warnings:
        return "review_async_chunk_recursive_traversal_plan"
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
    closure_wrapper_replacement_plan: dict[str, Any],
    closure_wrapper_assignment_safety: dict[str, Any],
    closure_wrapper_runtime_mutability_preflight: dict[str, Any],
    closure_wrapper_runtime_mutability_result: dict[str, Any],
    closure_wrapper_replacement_execution: dict[str, Any],
    closure_wrapper_restore_execution: dict[str, Any],
    closure_wrapper_events: dict[str, Any],
    closure_wrapper_continuation_readiness: dict[str, Any],
    closure_wrapper_continuation_execution_plan: dict[str, Any],
    closure_wrapper_continuation_execution: dict[str, Any],
    closure_wrapper_continuation_checkpoint: dict[str, Any],
    closure_wrapper_continuation_next_iteration_plan: dict[str, Any],
    closure_wrapper_continuation_next_iteration_execution: dict[str, Any],
    async_chunk_plan: dict[str, Any],
    async_chunk_result: dict[str, Any],
    async_chunk_module_diff: dict[str, Any],
    async_chunk_traversal_graph: dict[str, Any],
    async_chunk_traversal_workflow_plan: dict[str, Any],
    async_chunk_traversal_workflow_execution: dict[str, Any],
    async_chunk_traversal_loop_plan: dict[str, Any],
    async_chunk_traversal_loop_execution: dict[str, Any],
    async_chunk_recursive_traversal_plan: dict[str, Any],
    async_chunk_recursive_traversal_followup: dict[str, Any],
    async_chunk_recursive_traversal_execution: dict[str, Any],
    custom_loader_traversal_plan: dict[str, Any],
    custom_loader_traversal_graph: dict[str, Any],
    custom_loader_traversal_workflow_plan: dict[str, Any],
    custom_loader_traversal_workflow_execution: dict[str, Any],
    custom_loader_traversal_loop_plan: dict[str, Any],
    custom_loader_traversal_loop_execution: dict[str, Any],
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
    module_federation_traversal_graph: dict[str, Any],
    module_federation_traversal_workflow_plan: dict[str, Any],
    module_federation_traversal_workflow_execution: dict[str, Any],
    module_federation_recursive_traversal_plan: dict[str, Any],
    module_federation_recursive_traversal_followup: dict[str, Any],
    module_federation_recursive_traversal_execution: dict[str, Any],
    module_federation_recursive_continuation_journal: dict[str, Any],
    module_federation_recursive_continuation_checkpoint: dict[str, Any],
    recursive_continuation_readiness: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    closure_wrapper_strategy_descriptor = _closure_wrapper_strategy_descriptor(
        closure_wrapper_replacement_plan,
        closure_wrapper_assignment_safety,
        closure_wrapper_runtime_mutability_preflight,
        closure_wrapper_runtime_mutability_result,
        closure_wrapper_replacement_execution,
        closure_wrapper_restore_execution,
    )
    for code in blockers + warnings:
        if code == "no_hook_artifacts_provided":
            continue
        items.append(
            {
                "code": code,
                "function_hook_status": _status(function_hooks),
                "module_hook_status": _status(module_hooks),
                "source_logpoint_status": _status(source_logpoints),
                "closure_wrapper_replacement_plan_status": _status(closure_wrapper_replacement_plan) or _nested_status(closure_wrapper_replacement_plan, "plan"),
                "closure_wrapper_strategy": closure_wrapper_strategy_descriptor.get("strategy"),
                "closure_wrapper_strategy_supported_for_install": closure_wrapper_strategy_descriptor.get("supported_for_install"),
                "closure_wrapper_strategy_plan_only": closure_wrapper_strategy_descriptor.get("strategy_plan_only"),
                "closure_wrapper_assignment_safety_status": _status(closure_wrapper_assignment_safety) or _nested_status(closure_wrapper_assignment_safety, "assignment_safety"),
                "closure_wrapper_assignment_safety_proven": bool(_nested_get(closure_wrapper_assignment_safety, "assignment_safety", "assignment_safety_proven") or closure_wrapper_assignment_safety.get("assignment_safety_proven")),
                "closure_wrapper_runtime_mutability_preflight_status": _status(closure_wrapper_runtime_mutability_preflight) or _nested_status(closure_wrapper_runtime_mutability_preflight, "preflight"),
                "closure_wrapper_runtime_mutability_probe_ready_for_review": bool(_nested_get(closure_wrapper_runtime_mutability_preflight, "preflight", "runtime_mutability_probe_ready_for_review") or closure_wrapper_runtime_mutability_preflight.get("runtime_mutability_probe_ready_for_review")),
                "closure_wrapper_runtime_mutability_result_status": _status(closure_wrapper_runtime_mutability_result) or _nested_status(closure_wrapper_runtime_mutability_result, "result"),
                "closure_wrapper_runtime_mutability_result_proven": bool(_nested_get(closure_wrapper_runtime_mutability_result, "result", "runtime_mutability_proven") or closure_wrapper_runtime_mutability_result.get("runtime_mutability_proven")),
                "closure_wrapper_runtime_mutability_result_original_restored": bool(_nested_get(closure_wrapper_runtime_mutability_result, "result", "original_restored") or closure_wrapper_runtime_mutability_result.get("original_restored")),
                "closure_wrapper_replacement_execution_status": _status(closure_wrapper_replacement_execution) or _nested_status(closure_wrapper_replacement_execution, "execution"),
                "closure_wrapper_restore_execution_status": _status(closure_wrapper_restore_execution) or _nested_status(closure_wrapper_restore_execution, "execution"),
                "closure_wrapper_event_count": _intish(closure_wrapper_events.get("event_count") or closure_wrapper_events.get("eventCount") or _nested_get(closure_wrapper_events, "snapshot", "eventCount")),
                "closure_wrapper_continuation_readiness_status": _status(closure_wrapper_continuation_readiness) or _nested_status(closure_wrapper_continuation_readiness, "readiness"),
                "closure_wrapper_continuation_ready": bool(_nested_get(closure_wrapper_continuation_readiness, "readiness", "continuation_ready") or closure_wrapper_continuation_readiness.get("continuation_ready")),
                "closure_wrapper_continuation_automatic_wrapper_continuation": bool(_nested_get(closure_wrapper_continuation_readiness, "readiness", "automatic_wrapper_continuation") or closure_wrapper_continuation_readiness.get("automatic_wrapper_continuation")),
                "closure_wrapper_continuation_execution_plan_status": _status(closure_wrapper_continuation_execution_plan) or _nested_status(closure_wrapper_continuation_execution_plan, "plan"),
                "closure_wrapper_continuation_execution_plan_ready": bool(_nested_get(closure_wrapper_continuation_execution_plan, "plan", "ready_for_review") or closure_wrapper_continuation_execution_plan.get("ready_for_review")),
                "closure_wrapper_continuation_execution_plan_automatic_wrapper_continuation": bool(
                    ((_nested_get(closure_wrapper_continuation_execution_plan, "plan", "execution_strategy") or {}).get("automatic_wrapper_continuation_supported"))
                    or _nested_get(closure_wrapper_continuation_execution_plan, "plan", "automatic_wrapper_continuation")
                ),
                "closure_wrapper_continuation_execution_plan_next_action": _nested_get(closure_wrapper_continuation_execution_plan, "plan", "next_action") or closure_wrapper_continuation_execution_plan.get("next_action"),
                "closure_wrapper_continuation_execution_status": _status(closure_wrapper_continuation_execution) or _nested_status(closure_wrapper_continuation_execution, "execution"),
                "closure_wrapper_continuation_execution_iteration_executed": bool(
                    _nested_get(closure_wrapper_continuation_execution, "execution", "wrapper_continuation_iteration_executed")
                    or closure_wrapper_continuation_execution.get("wrapper_continuation_iteration_executed")
                ),
                "closure_wrapper_continuation_execution_paused_event_captured": bool(
                    _nested_get(closure_wrapper_continuation_execution, "execution", "paused_event_captured")
                    or closure_wrapper_continuation_execution.get("paused_event_captured")
                ),
                "closure_wrapper_continuation_execution_next_action": _nested_get(closure_wrapper_continuation_execution, "execution", "next_action") or closure_wrapper_continuation_execution.get("next_action"),
                "closure_wrapper_continuation_checkpoint_status": _status(closure_wrapper_continuation_checkpoint) or _nested_status(closure_wrapper_continuation_checkpoint, "checkpoint"),
                "closure_wrapper_continuation_checkpoint_ready": bool(
                    _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "ready_for_review")
                    or closure_wrapper_continuation_checkpoint.get("ready_for_review")
                ),
                "closure_wrapper_continuation_checkpoint_event_count": _intish(
                    _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "post_execution_event_count")
                    or closure_wrapper_continuation_checkpoint.get("post_execution_event_count")
                ),
                "closure_wrapper_continuation_checkpoint_next_action": _nested_get(closure_wrapper_continuation_checkpoint, "checkpoint", "next_action") or closure_wrapper_continuation_checkpoint.get("next_action"),
                "closure_wrapper_continuation_next_iteration_plan_status": _status(closure_wrapper_continuation_next_iteration_plan) or _nested_status(closure_wrapper_continuation_next_iteration_plan, "plan"),
                "closure_wrapper_continuation_next_iteration_plan_ready": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "ready_for_review")
                    or closure_wrapper_continuation_next_iteration_plan.get("ready_for_review")
                ),
                "closure_wrapper_continuation_next_iteration_plan_step_index": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_iteration_step_index")
                or closure_wrapper_continuation_next_iteration_plan.get("next_iteration_step_index"),
                "closure_wrapper_continuation_next_iteration_plan_method": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_iteration_method")
                or closure_wrapper_continuation_next_iteration_plan.get("next_iteration_method"),
                "closure_wrapper_continuation_next_iteration_plan_next_action": _nested_get(closure_wrapper_continuation_next_iteration_plan, "plan", "next_action")
                or closure_wrapper_continuation_next_iteration_plan.get("next_action"),
                "closure_wrapper_continuation_next_iteration_execution_status": _status(closure_wrapper_continuation_next_iteration_execution)
                or _nested_status(closure_wrapper_continuation_next_iteration_execution, "execution"),
                "closure_wrapper_continuation_next_iteration_execution_executed": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_execution, "execution", "wrapper_next_iteration_executed")
                    or closure_wrapper_continuation_next_iteration_execution.get("wrapper_next_iteration_executed")
                ),
                "closure_wrapper_continuation_next_iteration_execution_paused_event_captured": bool(
                    _nested_get(closure_wrapper_continuation_next_iteration_execution, "execution", "paused_event_captured")
                    or closure_wrapper_continuation_next_iteration_execution.get("paused_event_captured")
                ),
                "closure_wrapper_continuation_next_iteration_execution_next_action": _nested_get(
                    closure_wrapper_continuation_next_iteration_execution, "execution", "next_action"
                )
                or closure_wrapper_continuation_next_iteration_execution.get("next_action"),
                "async_chunk_load_plan_status": _status(async_chunk_plan),
                "async_chunk_load_result_status": _status(async_chunk_result),
                "async_chunk_module_diff_status": _status(async_chunk_module_diff) or _nested_status(async_chunk_module_diff, "diff"),
                "async_chunk_traversal_graph_status": _status(async_chunk_traversal_graph) or _nested_status(async_chunk_traversal_graph, "graph"),
                "async_chunk_traversal_workflow_plan_status": _status(async_chunk_traversal_workflow_plan) or _nested_status(async_chunk_traversal_workflow_plan, "workflow_plan"),
                "async_chunk_traversal_workflow_execution_status": _status(async_chunk_traversal_workflow_execution) or _nested_status(async_chunk_traversal_workflow_execution, "execution"),
                "async_chunk_traversal_loop_plan_status": _status(async_chunk_traversal_loop_plan) or _nested_status(async_chunk_traversal_loop_plan, "loop_plan"),
                "async_chunk_traversal_loop_execution_status": _status(async_chunk_traversal_loop_execution) or _nested_status(async_chunk_traversal_loop_execution, "execution"),
                "async_chunk_recursive_traversal_plan_status": _status(async_chunk_recursive_traversal_plan) or _nested_status(async_chunk_recursive_traversal_plan, "recursive_plan"),
                "async_chunk_recursive_traversal_followup_status": _status(async_chunk_recursive_traversal_followup) or _nested_status(async_chunk_recursive_traversal_followup, "followup"),
                "async_chunk_recursive_traversal_execution_status": _status(async_chunk_recursive_traversal_execution) or _nested_status(async_chunk_recursive_traversal_execution, "execution"),
                "custom_loader_traversal_plan_status": _status(custom_loader_traversal_plan) or _nested_status(custom_loader_traversal_plan, "plan"),
                "custom_loader_traversal_graph_status": _status(custom_loader_traversal_graph) or _nested_status(custom_loader_traversal_graph, "graph"),
                "custom_loader_traversal_workflow_plan_status": _status(custom_loader_traversal_workflow_plan) or _nested_status(custom_loader_traversal_workflow_plan, "workflow_plan"),
                "custom_loader_traversal_workflow_execution_status": _status(custom_loader_traversal_workflow_execution) or _nested_status(custom_loader_traversal_workflow_execution, "execution"),
                "custom_loader_traversal_loop_plan_status": _status(custom_loader_traversal_loop_plan) or _nested_status(custom_loader_traversal_loop_plan, "loop_plan"),
                "custom_loader_traversal_loop_execution_status": _status(custom_loader_traversal_loop_execution) or _nested_status(custom_loader_traversal_loop_execution, "execution"),
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
                "module_federation_traversal_graph_status": _status(module_federation_traversal_graph) or _nested_status(module_federation_traversal_graph, "graph"),
                "module_federation_traversal_workflow_plan_status": _status(module_federation_traversal_workflow_plan) or _nested_status(module_federation_traversal_workflow_plan, "workflow_plan"),
                "module_federation_traversal_workflow_execution_status": _status(module_federation_traversal_workflow_execution) or _nested_status(module_federation_traversal_workflow_execution, "execution"),
                "module_federation_recursive_traversal_plan_status": _status(module_federation_recursive_traversal_plan) or _nested_status(module_federation_recursive_traversal_plan, "recursive_plan"),
                "module_federation_recursive_traversal_followup_status": _status(module_federation_recursive_traversal_followup) or _nested_status(module_federation_recursive_traversal_followup, "followup"),
                "module_federation_recursive_traversal_execution_status": _status(module_federation_recursive_traversal_execution) or _nested_status(module_federation_recursive_traversal_execution, "execution"),
                "module_federation_recursive_continuation_journal_status": _status(module_federation_recursive_continuation_journal) or _nested_status(module_federation_recursive_continuation_journal, "journal"),
                "module_federation_recursive_continuation_checkpoint_status": _status(module_federation_recursive_continuation_checkpoint) or _nested_status(module_federation_recursive_continuation_checkpoint, "checkpoint"),
                "recursive_continuation_readiness_status": _status(recursive_continuation_readiness),
                "recursive_continuation_readiness_system_count": _intish(recursive_continuation_readiness.get("system_count")),
                "recursive_continuation_readiness_ready_systems": _listish(recursive_continuation_readiness.get("ready_systems")),
                "recursive_continuation_readiness_blocked_systems": _listish(recursive_continuation_readiness.get("blocked_systems")),
                "recursive_continuation_readiness_deeper_recursion_executor_ready": bool(recursive_continuation_readiness.get("deeper_recursion_executor_ready")),
                "function_hook_error": str(function_hooks.get("error") or ""),
                "module_hook_error": str(module_hooks.get("error") or ""),
                "source_logpoint_error": str(source_logpoints.get("error") or ""),
                "closure_wrapper_replacement_plan_error": str(closure_wrapper_replacement_plan.get("error") or ""),
                "closure_wrapper_replacement_execution_error": str(closure_wrapper_replacement_execution.get("error") or ""),
                "closure_wrapper_restore_execution_error": str(closure_wrapper_restore_execution.get("error") or ""),
                "async_chunk_load_error": str(async_chunk_result.get("error") or async_chunk_plan.get("error") or ""),
                "async_chunk_module_diff_error": str(async_chunk_module_diff.get("error") or ""),
                "async_chunk_traversal_graph_error": str(async_chunk_traversal_graph.get("error") or ""),
                "async_chunk_traversal_workflow_plan_error": str(async_chunk_traversal_workflow_plan.get("error") or ""),
                "async_chunk_traversal_workflow_execution_error": str(async_chunk_traversal_workflow_execution.get("error") or ""),
                "async_chunk_traversal_loop_plan_error": str(async_chunk_traversal_loop_plan.get("error") or ""),
                "async_chunk_traversal_loop_execution_error": str(async_chunk_traversal_loop_execution.get("error") or ""),
                "async_chunk_recursive_traversal_plan_error": str(async_chunk_recursive_traversal_plan.get("error") or ""),
                "async_chunk_recursive_traversal_followup_error": str(async_chunk_recursive_traversal_followup.get("error") or ""),
                "async_chunk_recursive_traversal_execution_error": str(async_chunk_recursive_traversal_execution.get("error") or ""),
                "custom_loader_traversal_error": str(custom_loader_traversal_plan.get("error") or ""),
                "custom_loader_traversal_graph_error": str(custom_loader_traversal_graph.get("error") or ""),
                "custom_loader_traversal_workflow_plan_error": str(custom_loader_traversal_workflow_plan.get("error") or ""),
                "custom_loader_traversal_workflow_execution_error": str(custom_loader_traversal_workflow_execution.get("error") or ""),
                "custom_loader_traversal_loop_plan_error": str(custom_loader_traversal_loop_plan.get("error") or ""),
                "custom_loader_traversal_loop_execution_error": str(custom_loader_traversal_loop_execution.get("error") or ""),
                "custom_loader_continuation_workflow_error": str(custom_loader_continuation_workflow.get("error") or ""),
                "custom_loader_continuation_journal_error": str(custom_loader_continuation_journal.get("error") or ""),
                "custom_loader_continuation_execution_error": str(custom_loader_continuation_execution.get("error") or ""),
                "custom_loader_execution_error": str(custom_loader_execution_result.get("error") or custom_loader_execution_preflight.get("error") or ""),
                "custom_loader_module_diff_error": str(custom_loader_module_diff.get("error") or ""),
                "module_federation_get_init_error": str(module_federation_get_init_result.get("error") or module_federation_get_init_plan.get("error") or ""),
                "module_federation_factory_error": str(module_federation_factory_invoke_result.get("error") or ""),
                "module_federation_export_hook_error": str(module_federation_export_hook_plan.get("error") or ""),
                "module_federation_traversal_graph_error": str(module_federation_traversal_graph.get("error") or ""),
                "module_federation_traversal_workflow_plan_error": str(module_federation_traversal_workflow_plan.get("error") or ""),
                "module_federation_traversal_workflow_execution_error": str(module_federation_traversal_workflow_execution.get("error") or ""),
                "module_federation_recursive_traversal_plan_error": str(module_federation_recursive_traversal_plan.get("error") or ""),
                "module_federation_recursive_traversal_followup_error": str(module_federation_recursive_traversal_followup.get("error") or ""),
                "module_federation_recursive_traversal_execution_error": str(module_federation_recursive_traversal_execution.get("error") or ""),
                "module_federation_recursive_continuation_journal_error": str(module_federation_recursive_continuation_journal.get("error") or ""),
                "module_federation_recursive_continuation_checkpoint_error": str(module_federation_recursive_continuation_checkpoint.get("error") or ""),
            }
        )
    return items
