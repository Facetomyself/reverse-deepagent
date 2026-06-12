from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read


HOOK_ARTIFACT_REVIEW_VERSION = "2026-06-01.hook-artifact-review-v2"
SOURCE_MAP_SELECTED_EXECUTOR_APPROVAL_RECORD_VERSION = "reverse-deepagent.source-map-selected-executor-approval-record.v1"
SOURCE_MAP_FOLLOWTHROUGH_DISPATCH_APPROVAL_RECORD_VERSION = "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1"
SOURCE_MAP_FOLLOWTHROUGH_DISPATCH_TRANSACTION_JOURNAL_VERSION = "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1"
HEAP_SNAPSHOT_DIFF_EXECUTOR_APPROVAL_RECORD_VERSION = "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1"
HEAP_SNAPSHOT_DIFF_EXECUTOR_TRANSACTION_JOURNAL_VERSION = "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1"
HEAP_SNAPSHOT_RETAINED_SIZE_APPROVAL_RECORD_VERSION = "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1"
HEAP_SNAPSHOT_RETAINED_SIZE_TRANSACTION_JOURNAL_VERSION = "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1"


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
        source_map_source_logpoint_install_result = _object_alias(
            payload,
            "source_map_source_logpoint_install_result",
            "source-map-source-logpoint-install-result",
            "sourceMapSourceLogpointInstallResult",
            "source_map_selected_source_logpoint_install_result",
            "sourceMapSelectedSourceLogpointInstallResult",
        )
        source_map_hook_install_result = _object_alias(
            payload,
            "source_map_hook_install_result",
            "source-map-hook-install-result",
            "sourceMapHookInstallResult",
            "source_map_selected_hook_install_result",
            "sourceMapSelectedHookInstallResult",
        )
        source_map_hook_candidates = _object_alias(
            payload,
            "source_map_hook_candidates",
            "source-map-hook-candidates",
            "sourceMapHookCandidates",
            "source_map_hook_candidate_refinement",
            "sourceMapHookCandidateRefinement",
        )
        source_map_hook_candidate_selection = _object_alias(
            payload,
            "source_map_hook_candidate_selection",
            "source-map-hook-candidate-selection",
            "sourceMapHookCandidateSelection",
            "source_map_hook_candidate_handoff",
            "sourceMapHookCandidateHandoff",
            "source_map_selected_hook_candidate",
            "sourceMapSelectedHookCandidate",
        )
        source_map_rebuild_result = _object_alias(
            payload,
            "source_map_rebuild_result",
            "source-map-rebuild-result",
            "sourceMapRebuildResult",
            "source_map_selected_rebuild_result",
            "sourceMapSelectedRebuildResult",
            "source_map_rebuild_metadata_result",
            "sourceMapRebuildMetadataResult",
        )
        source_map_rebuild_generation_result = _object_alias(
            payload,
            "source_map_rebuild_generation_result",
            "source-map-rebuild-generation-result",
            "sourceMapRebuildGenerationResult",
            "source_map_selected_rebuild_generation_result",
            "sourceMapSelectedRebuildGenerationResult",
        )
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
        source_map_followthrough_chain_readiness = _object_alias(
            payload,
            "source_map_followthrough_chain_readiness",
            "source-map-followthrough-chain-readiness",
            "sourceMapFollowthroughChainReadiness",
            "source_map_followthrough_chain_review",
            "source-map-followthrough-chain-review",
            "sourceMapFollowthroughChainReview",
            "source_map_followthrough_status",
            "source-map-followthrough-status",
            "sourceMapFollowthroughStatus",
        )
        source_map_followthrough_one_step_plan = _object_alias(
            payload,
            "source_map_followthrough_one_step_plan",
            "source-map-followthrough-one-step-plan",
            "sourceMapFollowthroughOneStepPlan",
            "source_map_followthrough_orchestrator_plan",
            "source-map-followthrough-orchestrator-plan",
            "sourceMapFollowthroughOrchestratorPlan",
            "source_map_followthrough_next_step_plan",
            "source-map-followthrough-next-step-plan",
            "sourceMapFollowthroughNextStepPlan",
        )
        source_map_followthrough_dispatch_preflight = _object_alias(
            payload,
            "source_map_followthrough_dispatch_preflight",
            "source-map-followthrough-dispatch-preflight",
            "sourceMapFollowthroughDispatchPreflight",
            "source_map_followthrough_dispatch_review",
            "source-map-followthrough-dispatch-review",
            "sourceMapFollowthroughDispatchReview",
            "source_map_followthrough_executor_dispatch_preflight",
            "source-map-followthrough-executor-dispatch-preflight",
            "sourceMapFollowthroughExecutorDispatchPreflight",
        )
        source_map_followthrough_dispatch_approval_plan = _object_alias(
            payload,
            "source_map_followthrough_dispatch_approval_plan",
            "source-map-followthrough-dispatch-approval-plan",
            "sourceMapFollowthroughDispatchApprovalPlan",
            "source_map_followthrough_executor_approval_plan",
            "source-map-followthrough-executor-approval-plan",
            "sourceMapFollowthroughExecutorApprovalPlan",
            "source_map_followthrough_dispatch_transaction_plan",
            "source-map-followthrough-dispatch-transaction-plan",
            "sourceMapFollowthroughDispatchTransactionPlan",
        )
        source_map_followthrough_dispatch_approval_record = _object_alias(
            payload,
            "source_map_followthrough_dispatch_approval_record",
            "source-map-followthrough-dispatch-approval-record",
            "sourceMapFollowthroughDispatchApprovalRecord",
            "source_map_followthrough_executor_approval_record",
            "source-map-followthrough-executor-approval-record",
            "sourceMapFollowthroughExecutorApprovalRecord",
            "source_map_followthrough_dispatch_review_record",
            "source-map-followthrough-dispatch-review-record",
            "sourceMapFollowthroughDispatchReviewRecord",
        )
        source_map_followthrough_dispatch_transaction_preflight = _object_alias(
            payload,
            "source_map_followthrough_dispatch_transaction_preflight",
            "source-map-followthrough-dispatch-transaction-preflight",
            "sourceMapFollowthroughDispatchTransactionPreflight",
            "source_map_followthrough_dispatch_journal_preflight",
            "source-map-followthrough-dispatch-journal-preflight",
            "sourceMapFollowthroughDispatchJournalPreflight",
            "source_map_followthrough_dispatch_transaction_gate",
            "source-map-followthrough-dispatch-transaction-gate",
            "sourceMapFollowthroughDispatchTransactionGate",
        )
        source_map_followthrough_dispatch_transaction_journal = _object_alias(
            payload,
            "source_map_followthrough_dispatch_transaction_journal",
            "source-map-followthrough-dispatch-transaction-journal",
            "sourceMapFollowthroughDispatchTransactionJournal",
            "source_map_followthrough_dispatch_journal",
            "source-map-followthrough-dispatch-journal",
            "sourceMapFollowthroughDispatchJournal",
        )
        source_map_followthrough_dispatch_bounded_executor_gate = _object_alias(
            payload,
            "source_map_followthrough_dispatch_bounded_executor_gate",
            "source-map-followthrough-dispatch-bounded-executor-gate",
            "sourceMapFollowthroughDispatchBoundedExecutorGate",
            "source_map_followthrough_dispatch_bounded_gate",
            "source-map-followthrough-dispatch-bounded-gate",
            "sourceMapFollowthroughDispatchBoundedGate",
            "source_map_followthrough_dispatch_executor_gate",
            "source-map-followthrough-dispatch-executor-gate",
            "sourceMapFollowthroughDispatchExecutorGate",
        )
        source_map_followthrough_dispatcher_handoff = _object_alias(
            payload,
            "source_map_followthrough_dispatcher_handoff",
            "source-map-followthrough-dispatcher-handoff",
            "sourceMapFollowthroughDispatcherHandoff",
            "source_map_followthrough_dispatch_handoff",
            "source-map-followthrough-dispatch-handoff",
            "sourceMapFollowthroughDispatchHandoff",
            "source_map_followthrough_next_action_handoff",
            "source-map-followthrough-next-action-handoff",
            "sourceMapFollowthroughNextActionHandoff",
        )
        source_map_followthrough_dispatcher_apply_preflight = _object_alias(
            payload,
            "source_map_followthrough_dispatcher_apply_preflight",
            "source-map-followthrough-dispatcher-apply-preflight",
            "sourceMapFollowthroughDispatcherApplyPreflight",
            "source_map_followthrough_dispatch_apply_preflight",
            "source-map-followthrough-dispatch-apply-preflight",
            "sourceMapFollowthroughDispatchApplyPreflight",
            "source_map_followthrough_dispatcher_preflight",
            "source-map-followthrough-dispatcher-preflight",
            "sourceMapFollowthroughDispatcherPreflight",
        )
        source_map_followthrough_dispatcher_result = _object_alias(
            payload,
            "source_map_followthrough_dispatcher_result",
            "source-map-followthrough-dispatcher-result",
            "sourceMapFollowthroughDispatcherResult",
            "source_map_followthrough_dispatcher_mvp",
            "source-map-followthrough-dispatcher-mvp",
            "sourceMapFollowthroughDispatcherMvp",
            "source_map_followthrough_dispatch_next_action",
            "source-map-followthrough-dispatch-next-action",
            "sourceMapFollowthroughDispatchNextAction",
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
        source_map_selected_executor_approval_plan = _object_alias(
            payload,
            "source_map_selected_executor_approval_plan",
            "source-map-selected-executor-approval-plan",
            "sourceMapSelectedExecutorApprovalPlan",
            "source_map_selected_executor_apply_plan",
            "source-map-selected-executor-apply-plan",
            "sourceMapSelectedExecutorApplyPlan",
            "source_map_followthrough_approval_plan",
            "source-map-followthrough-approval-plan",
            "sourceMapFollowthroughApprovalPlan",
        )
        source_map_selected_executor_approval_record = _object_alias(
            payload,
            "source_map_selected_executor_approval_record",
            "source-map-selected-executor-approval-record",
            "sourceMapSelectedExecutorApprovalRecord",
            "source_map_selected_executor_apply_approval_record",
            "source-map-selected-executor-apply-approval-record",
            "sourceMapSelectedExecutorApplyApprovalRecord",
        )
        heap_snapshot_diff_executor_approval_record = _object_alias(
            payload,
            "heap_snapshot_diff_executor_approval_record",
            "heap-snapshot-diff-executor-approval-record",
            "heapSnapshotDiffExecutorApprovalRecord",
            "record_heap_snapshot_diff_executor_approval",
            "recordHeapSnapshotDiffExecutorApproval",
            "heap_diff_executor_approval_record",
            "heap-diff-executor-approval-record",
            "heapDiffExecutorApprovalRecord",
            "raw_heap_diff_approval_record",
            "raw-heap-diff-approval-record",
            "rawHeapDiffApprovalRecord",
        )
        heap_snapshot_diff_executor_transaction_preflight = _object_alias(
            payload,
            "heap_snapshot_diff_executor_transaction_preflight",
            "heap-snapshot-diff-executor-transaction-preflight",
            "heapSnapshotDiffExecutorTransactionPreflight",
            "heap_snapshot_diff_transaction_preflight",
            "heap-snapshot-diff-transaction-preflight",
            "heapSnapshotDiffTransactionPreflight",
            "heap_diff_executor_transaction_preflight",
            "heap-diff-executor-transaction-preflight",
            "heapDiffExecutorTransactionPreflight",
            "raw_heap_diff_transaction_preflight",
            "raw-heap-diff-transaction-preflight",
            "rawHeapDiffTransactionPreflight",
            "review_heap_snapshot_diff_executor_transaction_preflight",
            "review-heap-snapshot-diff-executor-transaction-preflight",
            "reviewHeapSnapshotDiffExecutorTransactionPreflight",
        )
        heap_snapshot_diff_executor_transaction_journal = _object_alias(
            payload,
            "heap_snapshot_diff_executor_transaction_journal",
            "heap-snapshot-diff-executor-transaction-journal",
            "heapSnapshotDiffExecutorTransactionJournal",
            "heap_snapshot_diff_executor_journal",
            "heap-snapshot-diff-executor-journal",
            "heapSnapshotDiffExecutorJournal",
            "record_heap_snapshot_diff_executor_transaction_journal",
            "recordHeapSnapshotDiffExecutorTransactionJournal",
            "raw_heap_diff_transaction_journal",
            "raw-heap-diff-transaction-journal",
            "rawHeapDiffTransactionJournal",
        )
        heap_snapshot_diff_executor_bounded_gate = _object_alias(
            payload,
            "heap_snapshot_diff_executor_bounded_gate",
            "heap-snapshot-diff-executor-bounded-gate",
            "heapSnapshotDiffExecutorBoundedGate",
            "heap_snapshot_diff_executor_bounded_executor_gate",
            "heap-snapshot-diff-executor-bounded-executor-gate",
            "heapSnapshotDiffExecutorBoundedExecutorGate",
            "heap_snapshot_diff_bounded_gate",
            "heap-snapshot-diff-bounded-gate",
            "heapSnapshotDiffBoundedGate",
            "heap_diff_executor_bounded_gate",
            "heap-diff-executor-bounded-gate",
            "heapDiffExecutorBoundedGate",
            "raw_heap_diff_bounded_gate",
            "raw-heap-diff-bounded-gate",
            "rawHeapDiffBoundedGate",
        )
        heap_snapshot_diff_executor_result = _object_alias(
            payload,
            "heap_snapshot_diff_executor_result",
            "heap-snapshot-diff-executor-result",
            "heapSnapshotDiffExecutorResult",
            "execute_heap_snapshot_diff_executor",
            "executeHeapSnapshotDiffExecutor",
            "heap_snapshot_diff_executor_mvp",
            "heap-snapshot-diff-executor-mvp",
            "heapSnapshotDiffExecutorMvp",
            "raw_heap_diff_executor",
            "raw-heap-diff-executor",
            "rawHeapDiffExecutor",
        )
        heap_snapshot_diff_followup_checkpoint = _object_alias(
            payload,
            "heap_snapshot_diff_followup_checkpoint",
            "heap-snapshot-diff-followup-checkpoint",
            "heapSnapshotDiffFollowupCheckpoint",
            "heap_snapshot_diff_analysis_plan",
            "heap-snapshot-diff-analysis-plan",
            "heapSnapshotDiffAnalysisPlan",
            "review_heap_snapshot_diff_followup_checkpoint",
            "reviewHeapSnapshotDiffFollowupCheckpoint",
            "review_heap_snapshot_diff_executor_result_followup",
            "reviewHeapSnapshotDiffExecutorResultFollowup",
        )
        heap_snapshot_diff_selected_analysis_input_preflight = _object_alias(
            payload,
            "heap_snapshot_diff_selected_analysis_input_preflight",
            "heap-snapshot-diff-selected-analysis-input-preflight",
            "heapSnapshotDiffSelectedAnalysisInputPreflight",
            "heap_snapshot_diff_followup_selected_analysis_preflight",
            "heap-snapshot-diff-followup-selected-analysis-preflight",
            "heapSnapshotDiffFollowupSelectedAnalysisPreflight",
            "heap_snapshot_diff_selected_followup_preflight",
            "heap-snapshot-diff-selected-followup-preflight",
            "heapSnapshotDiffSelectedFollowupPreflight",
            "review_heap_snapshot_diff_selected_analysis_input",
            "reviewHeapSnapshotDiffSelectedAnalysisInput",
        )
        heap_snapshot_constructor_growth_drilldown = _object_alias(
            payload,
            "heap_snapshot_constructor_growth_drilldown",
            "heap-snapshot-constructor-growth-drilldown",
            "heapSnapshotConstructorGrowthDrilldown",
            "heap_snapshot_diff_constructor_growth_drilldown",
            "heap-snapshot-diff-constructor-growth-drilldown",
            "heapSnapshotDiffConstructorGrowthDrilldown",
            "review_heap_snapshot_constructor_growth_drilldown",
            "reviewHeapSnapshotConstructorGrowthDrilldown",
            "review_heap_snapshot_diff_constructor_growth",
            "reviewHeapSnapshotDiffConstructorGrowth",
        )
        heap_snapshot_constructor_growth_drilldown_analysis = _object_alias(
            payload,
            "heap_snapshot_constructor_growth_drilldown_analysis",
            "heap-snapshot-constructor-growth-drilldown-analysis",
            "heapSnapshotConstructorGrowthDrilldownAnalysis",
            "heap_snapshot_constructor_growth_drilldown_executor_result",
            "heap-snapshot-constructor-growth-drilldown-executor-result",
            "heapSnapshotConstructorGrowthDrilldownExecutorResult",
            "execute_heap_snapshot_constructor_growth_drilldown",
            "executeHeapSnapshotConstructorGrowthDrilldown",
            "execute_heap_snapshot_constructor_growth_drilldown_analysis",
            "executeHeapSnapshotConstructorGrowthDrilldownAnalysis",
        )
        heap_snapshot_automatic_followup_plan = _object_alias(
            payload,
            "heap_snapshot_automatic_followup_plan",
            "heap-snapshot-automatic-followup-plan",
            "heapSnapshotAutomaticFollowupPlan",
            "heap_snapshot_automatic_followup_planner",
            "heap-snapshot-automatic-followup-planner",
            "heapSnapshotAutomaticFollowupPlanner",
            "heap_snapshot_followup_plan",
            "heap-snapshot-followup-plan",
            "heapSnapshotFollowupPlan",
            "review_heap_snapshot_automatic_followup_plan",
            "reviewHeapSnapshotAutomaticFollowupPlan",
        )
        heap_snapshot_retained_size_proof_plan = _object_alias(
            payload,
            "heap_snapshot_retained_size_proof_plan",
            "heap-snapshot-retained-size-proof-plan",
            "heapSnapshotRetainedSizeProofPlan",
            "heap_snapshot_retained_size_proof_planner",
            "heap-snapshot-retained-size-proof-planner",
            "heapSnapshotRetainedSizeProofPlanner",
            "plan_heap_snapshot_retained_size_proof",
            "planHeapSnapshotRetainedSizeProof",
            "review_heap_snapshot_retained_size_proof_plan",
            "reviewHeapSnapshotRetainedSizeProofPlan",
        )
        heap_snapshot_path_to_root_proof_plan = _object_alias(
            payload,
            "heap_snapshot_path_to_root_proof_plan",
            "heap-snapshot-path-to-root-proof-plan",
            "heapSnapshotPathToRootProofPlan",
            "heap_snapshot_path_to_root_proof_planner",
            "heap-snapshot-path-to-root-proof-planner",
            "heapSnapshotPathToRootProofPlanner",
            "plan_heap_snapshot_path_to_root_proof",
            "planHeapSnapshotPathToRootProof",
            "review_heap_snapshot_path_to_root_proof_plan",
            "reviewHeapSnapshotPathToRootProofPlan",
        )
        heap_snapshot_raw_heap_constructor_drilldown_proof_plan = _object_alias(
            payload,
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heapSnapshotRawHeapConstructorDrilldownProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
            "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
            "planHeapSnapshotRawHeapConstructorDrilldownProof",
            "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
        )
        heap_snapshot_retained_path_preflight = _object_alias(
            payload,
            "heap_snapshot_retained_path_preflight",
            "heap-snapshot-retained-path-preflight",
            "heapSnapshotRetainedPathPreflight",
            "heap_snapshot_constructor_growth_retained_path_preflight",
            "heap-snapshot-constructor-growth-retained-path-preflight",
            "heapSnapshotConstructorGrowthRetainedPathPreflight",
            "heap_snapshot_retained_size_path_to_root_preflight",
            "heap-snapshot-retained-size-path-to-root-preflight",
            "heapSnapshotRetainedSizePathToRootPreflight",
            "review_heap_snapshot_retained_path_preflight",
            "reviewHeapSnapshotRetainedPathPreflight",
        )
        heap_snapshot_retained_size_input_review = _object_alias(
            payload,
            "heap_snapshot_retained_size_input_review",
            "heap-snapshot-retained-size-input-review",
            "heapSnapshotRetainedSizeInputReview",
            "heap_snapshot_retained_size_executor_input_review",
            "heap-snapshot-retained-size-executor-input-review",
            "heapSnapshotRetainedSizeExecutorInputReview",
            "heap_snapshot_retained_size_approval_gate",
            "heap-snapshot-retained-size-approval-gate",
            "heapSnapshotRetainedSizeApprovalGate",
            "review_heap_snapshot_retained_size_input",
            "reviewHeapSnapshotRetainedSizeInput",
        )
        heap_snapshot_retained_size_approval_plan = _object_alias(
            payload,
            "heap_snapshot_retained_size_approval_plan",
            "heap-snapshot-retained-size-approval-plan",
            "heapSnapshotRetainedSizeApprovalPlan",
            "heap_snapshot_retained_size_executor_approval_plan",
            "heap-snapshot-retained-size-executor-approval-plan",
            "heapSnapshotRetainedSizeExecutorApprovalPlan",
            "heap_snapshot_retained_size_transaction_plan",
            "heap-snapshot-retained-size-transaction-plan",
            "heapSnapshotRetainedSizeTransactionPlan",
            "review_heap_snapshot_retained_size_approval_plan",
            "reviewHeapSnapshotRetainedSizeApprovalPlan",
        )
        heap_snapshot_retained_size_approval_record = _object_alias(
            payload,
            "heap_snapshot_retained_size_approval_record",
            "heap-snapshot-retained-size-approval-record",
            "heapSnapshotRetainedSizeApprovalRecord",
            "record_heap_snapshot_retained_size_approval",
            "recordHeapSnapshotRetainedSizeApproval",
            "heap_snapshot_retained_size_executor_approval_record",
            "heap-snapshot-retained-size-executor-approval-record",
            "heapSnapshotRetainedSizeExecutorApprovalRecord",
        )
        heap_snapshot_retained_size_transaction_preflight = _object_alias(
            payload,
            "heap_snapshot_retained_size_transaction_preflight",
            "heap-snapshot-retained-size-transaction-preflight",
            "heapSnapshotRetainedSizeTransactionPreflight",
            "heap_snapshot_retained_size_executor_transaction_preflight",
            "heap-snapshot-retained-size-executor-transaction-preflight",
            "heapSnapshotRetainedSizeExecutorTransactionPreflight",
            "review_heap_snapshot_retained_size_transaction_preflight",
            "reviewHeapSnapshotRetainedSizeTransactionPreflight",
        )
        heap_snapshot_retained_size_transaction_journal = _object_alias(
            payload,
            "heap_snapshot_retained_size_transaction_journal",
            "heap-snapshot-retained-size-transaction-journal",
            "heapSnapshotRetainedSizeTransactionJournal",
            "heap_snapshot_retained_size_executor_journal",
            "heap-snapshot-retained-size-executor-journal",
            "heapSnapshotRetainedSizeExecutorJournal",
            "record_heap_snapshot_retained_size_transaction_journal",
            "recordHeapSnapshotRetainedSizeTransactionJournal",
        )
        heap_snapshot_retained_size_bounded_gate = _object_alias(
            payload,
            "heap_snapshot_retained_size_bounded_gate",
            "heap-snapshot-retained-size-bounded-gate",
            "heapSnapshotRetainedSizeBoundedGate",
            "heap_snapshot_retained_size_bounded_executor_gate",
            "heap-snapshot-retained-size-bounded-executor-gate",
            "heapSnapshotRetainedSizeBoundedExecutorGate",
            "heap_snapshot_retained_size_executor_bounded_gate",
            "heap-snapshot-retained-size-executor-bounded-gate",
            "heapSnapshotRetainedSizeExecutorBoundedGate",
            "review_heap_snapshot_retained_size_bounded_gate",
            "reviewHeapSnapshotRetainedSizeBoundedGate",
        )
        heap_snapshot_retained_size_analysis = _object_alias(
            payload,
            "heap_snapshot_retained_size_analysis",
            "heap-snapshot-retained-size-analysis",
            "heapSnapshotRetainedSizeAnalysis",
            "heap_snapshot_retained_size_executor_result",
            "heap-snapshot-retained-size-executor-result",
            "heapSnapshotRetainedSizeExecutorResult",
            "execute_heap_snapshot_retained_size_analysis",
            "executeHeapSnapshotRetainedSizeAnalysis",
        )
        heap_snapshot_path_to_root_analysis = _object_alias(
            payload,
            "heap_snapshot_path_to_root_analysis",
            "heap-snapshot-path-to-root-analysis",
            "heapSnapshotPathToRootAnalysis",
            "heap_snapshot_path_to_root_executor_result",
            "heap-snapshot-path-to-root-executor-result",
            "heapSnapshotPathToRootExecutorResult",
            "execute_heap_snapshot_path_to_root_analysis",
            "executeHeapSnapshotPathToRootAnalysis",
        )
        source_map_selected_executor_apply_preflight = _object_alias(
            payload,
            "source_map_selected_executor_apply_preflight",
            "source-map-selected-executor-apply-preflight",
            "sourceMapSelectedExecutorApplyPreflight",
            "source_map_selected_executor_application_preflight",
            "source-map-selected-executor-application-preflight",
            "sourceMapSelectedExecutorApplicationPreflight",
            "source_map_followthrough_apply_preflight",
            "source-map-followthrough-apply-preflight",
            "sourceMapFollowthroughApplyPreflight",
        )
        source_map_selected_executor_application_handoff = _object_alias(
            payload,
            "source_map_selected_executor_application_handoff",
            "source-map-selected-executor-application-handoff",
            "sourceMapSelectedExecutorApplicationHandoff",
            "source_map_selected_executor_application_review_input",
            "source-map-selected-executor-application-review-input",
            "sourceMapSelectedExecutorApplicationReviewInput",
            "source_map_followthrough_application_handoff",
            "source-map-followthrough-application-handoff",
            "sourceMapFollowthroughApplicationHandoff",
        )
        source_map_selected_executor_result_checkpoint = _object_alias(
            payload,
            "source_map_selected_executor_result_checkpoint",
            "source-map-selected-executor-result-checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_selected_executor_application_result_checkpoint",
            "source-map-selected-executor-application-result-checkpoint",
            "sourceMapSelectedExecutorApplicationResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "source-map-followthrough-result-checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
        source_map_followthrough_completion_checkpoint = _object_alias(
            payload,
            "source_map_followthrough_completion_checkpoint",
            "source-map-followthrough-completion-checkpoint",
            "sourceMapFollowthroughCompletionCheckpoint",
            "source_map_followthrough_completion_review",
            "source-map-followthrough-completion-review",
            "sourceMapFollowthroughCompletionReview",
            "source_map_followthrough_next_action_checkpoint",
            "source-map-followthrough-next-action-checkpoint",
            "sourceMapFollowthroughNextActionCheckpoint",
        )
        source_map_terminal_review_package = _object_alias(
            payload,
            "source_map_terminal_review_package",
            "source-map-terminal-review-package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "source-map-followthrough-terminal-review-package",
            "sourceMapFollowthroughTerminalReviewPackage",
            "source_map_terminal_review_handoff",
            "source-map-terminal-review-handoff",
            "sourceMapTerminalReviewHandoff",
            "source_map_followthrough_audit_handoff",
            "source-map-followthrough-audit-handoff",
            "sourceMapFollowthroughAuditHandoff",
        )
        source_map_terminal_review_closure_checkpoint = _object_alias(
            payload,
            "source_map_terminal_review_closure_checkpoint",
            "source-map-terminal-review-closure-checkpoint",
            "sourceMapTerminalReviewClosureCheckpoint",
            "source_map_terminal_review_observed_result_checkpoint",
            "source-map-terminal-review-observed-result-checkpoint",
            "sourceMapTerminalReviewObservedResultCheckpoint",
            "source_map_followthrough_closure_audit",
            "source-map-followthrough-closure-audit",
            "sourceMapFollowthroughClosureAudit",
            "source_map_terminal_review_closure_audit",
            "source-map-terminal-review-closure-audit",
            "sourceMapTerminalReviewClosureAudit",
        )
        source_map_terminal_review_final_audit = _object_alias(
            payload,
            "source_map_terminal_review_final_audit",
            "source-map-terminal-review-final-audit",
            "sourceMapTerminalReviewFinalAudit",
            "source_map_terminal_review_final_audit_rollup",
            "source-map-terminal-review-final-audit-rollup",
            "sourceMapTerminalReviewFinalAuditRollup",
            "source_map_followthrough_final_audit",
            "source-map-followthrough-final-audit",
            "sourceMapFollowthroughFinalAudit",
            "source_map_terminal_review_closure_summary",
            "source-map-terminal-review-closure-summary",
            "sourceMapTerminalReviewClosureSummary",
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
        runtime_object_graph_diff = _object_alias(
            payload,
            "runtime_object_graph_diff",
            "runtime-object-graph-diff",
            "runtimeObjectGraphDiff",
            "runtime_collected_object_graph_diff",
            "runtime-collected-object-graph-diff",
            "runtimeCollectedObjectGraphDiff",
            "js_runtime_object_graph_diff",
            "js-runtime-object-graph-diff",
            "jsRuntimeObjectGraphDiff",
        )
        heap_snapshot_readiness = _object_alias(
            payload,
            "heap_snapshot_readiness",
            "heap-snapshot-readiness",
            "heapSnapshotReadiness",
            "cdp_heap_snapshot_readiness",
            "cdp-heap-snapshot-readiness",
            "cdpHeapSnapshotReadiness",
            "heap_profiler_readiness",
            "heap-profiler-readiness",
            "heapProfilerReadiness",
        )
        heap_snapshot_collect = _object_alias(
            payload,
            "heap_snapshot_collect",
            "heap-snapshot-collect",
            "heapSnapshotCollect",
            "cdp_heap_snapshot_collect",
            "cdp-heap-snapshot-collect",
            "cdpHeapSnapshotCollect",
            "reviewed_heap_snapshot_collect",
            "reviewed-heap-snapshot-collect",
            "reviewedHeapSnapshotCollect",
        )
        heap_snapshot_diff_readiness = _object_alias(
            payload,
            "heap_snapshot_diff_readiness",
            "heap-snapshot-diff-readiness",
            "heapSnapshotDiffReadiness",
            "heap_snapshot_diff_review",
            "heap-snapshot-diff-review",
            "heapSnapshotDiffReview",
            "review_heap_snapshot_diff",
            "review-heap-snapshot-diff",
            "reviewHeapSnapshotDiff",
            "heap_diff_readiness",
            "heap-diff-readiness",
            "heapDiffReadiness",
        )
        heap_snapshot_diff_executor_preflight = _object_alias(
            payload,
            "heap_snapshot_diff_executor_preflight",
            "heap-snapshot-diff-executor-preflight",
            "heapSnapshotDiffExecutorPreflight",
            "heap_snapshot_diff_preflight",
            "heap-snapshot-diff-preflight",
            "heapSnapshotDiffPreflight",
            "heap_diff_executor_preflight",
            "heap-diff-executor-preflight",
            "heapDiffExecutorPreflight",
            "review_heap_snapshot_diff_executor",
            "review-heap-snapshot-diff-executor",
            "reviewHeapSnapshotDiffExecutor",
            "raw_heap_diff_preflight",
            "raw-heap-diff-preflight",
            "rawHeapDiffPreflight",
        )
        heap_snapshot_diff_executor_approval_plan = _object_alias(
            payload,
            "heap_snapshot_diff_executor_approval_plan",
            "heap-snapshot-diff-executor-approval-plan",
            "heapSnapshotDiffExecutorApprovalPlan",
            "heap_snapshot_diff_approval_plan",
            "heap-snapshot-diff-approval-plan",
            "heapSnapshotDiffApprovalPlan",
            "heap_diff_executor_approval_plan",
            "heap-diff-executor-approval-plan",
            "heapDiffExecutorApprovalPlan",
            "review_heap_snapshot_diff_executor_approval",
            "review-heap-snapshot-diff-executor-approval",
            "reviewHeapSnapshotDiffExecutorApproval",
            "raw_heap_diff_approval_plan",
            "raw-heap-diff-approval-plan",
            "rawHeapDiffApprovalPlan",
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
                source_map_followthrough_chain_readiness,
                source_map_followthrough_one_step_plan,
                source_map_followthrough_dispatch_preflight,
                source_map_followthrough_dispatch_approval_plan,
                source_map_followthrough_dispatch_approval_record,
                source_map_followthrough_dispatch_transaction_preflight,
                source_map_followthrough_dispatch_transaction_journal,
                source_map_followthrough_dispatch_bounded_executor_gate,
                source_map_followthrough_surface_selection,
                source_map_selected_executor_input_review,
                source_map_selected_executor_approval_plan,
                source_map_selected_executor_approval_record,
                source_map_selected_executor_apply_preflight,
                source_map_selected_executor_application_handoff,
                source_map_selected_executor_result_checkpoint,
                source_map_followthrough_completion_checkpoint,
                source_map_terminal_review_package,
                source_map_source_logpoint_install_result,
                source_map_hook_candidates,
                source_map_hook_candidate_selection,
                source_map_hook_install_result,
                source_map_rebuild_result,
                source_map_rebuild_generation_result,
                object_graph_diff,
                runtime_object_graph_diff,
                heap_snapshot_readiness,
                heap_snapshot_collect,
                heap_snapshot_diff_readiness,
                heap_snapshot_diff_executor_preflight,
                heap_snapshot_diff_executor_approval_plan,
                heap_snapshot_diff_executor_approval_record,
                heap_snapshot_diff_executor_transaction_preflight,
                heap_snapshot_diff_executor_transaction_journal,
                heap_snapshot_retained_size_approval_record,
                heap_snapshot_retained_size_transaction_preflight,
                heap_snapshot_retained_size_transaction_journal,
                heap_snapshot_retained_size_bounded_gate,
                heap_snapshot_automatic_followup_plan,
                heap_snapshot_retained_size_proof_plan,
                heap_snapshot_path_to_root_proof_plan,
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
        if _status(source_map_followthrough_chain_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_chain_readiness_blocked")
        if _status(source_map_followthrough_one_step_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_one_step_plan_blocked")
        if _status(source_map_followthrough_dispatch_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_preflight_blocked")
        if _status(source_map_followthrough_dispatch_approval_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_approval_plan_blocked")
        if _status(source_map_followthrough_dispatch_approval_record) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_approval_record_blocked")
        if _status(source_map_followthrough_dispatch_transaction_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_transaction_preflight_blocked")
        if _status(source_map_followthrough_dispatch_transaction_journal) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_transaction_journal_blocked")
        if _status(source_map_followthrough_dispatch_bounded_executor_gate) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatch_bounded_executor_gate_blocked")
        if _status(source_map_followthrough_surface_selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_surface_selection_blocked")
        if _status(source_map_selected_executor_input_review) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_input_review_blocked")
        if _status(source_map_selected_executor_approval_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_approval_plan_blocked")
        if _status(source_map_selected_executor_approval_record) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_approval_record_blocked")
        if _status(source_map_selected_executor_apply_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_apply_preflight_blocked")
        if _status(heap_snapshot_diff_executor_approval_record) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_approval_record_blocked")
        if _status(heap_snapshot_diff_executor_transaction_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_transaction_preflight_blocked")
        if _status(heap_snapshot_diff_executor_transaction_journal) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_transaction_journal_blocked")
        if _status(heap_snapshot_diff_executor_bounded_gate) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_bounded_gate_blocked")
        if _status(heap_snapshot_diff_executor_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_result_blocked")
        if _status(heap_snapshot_diff_followup_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_followup_checkpoint_blocked")
        if _status(heap_snapshot_diff_selected_analysis_input_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_blocked")
        if _status(heap_snapshot_constructor_growth_drilldown) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_constructor_growth_drilldown_blocked")
        if _status(heap_snapshot_constructor_growth_drilldown_analysis) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_blocked")
        if _status(heap_snapshot_automatic_followup_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_automatic_followup_plan_blocked")
        if _status(heap_snapshot_retained_size_proof_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_proof_plan_blocked")
        if _status(heap_snapshot_path_to_root_proof_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_path_to_root_proof_plan_blocked")
        if _status(heap_snapshot_raw_heap_constructor_drilldown_proof_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blocked")
        if _status(heap_snapshot_retained_path_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_path_preflight_blocked")
        if _status(heap_snapshot_retained_size_input_review) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_input_review_blocked")
        if _status(heap_snapshot_retained_size_approval_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_approval_plan_blocked")
        if _status(heap_snapshot_retained_size_approval_record) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_approval_record_blocked")
        if _status(heap_snapshot_retained_size_transaction_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_transaction_preflight_blocked")
        if _status(heap_snapshot_retained_size_transaction_journal) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_transaction_journal_blocked")
        if _status(heap_snapshot_retained_size_bounded_gate) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_bounded_gate_blocked")
        if _status(heap_snapshot_retained_size_analysis) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_retained_size_analysis_blocked")
        if _status(heap_snapshot_path_to_root_analysis) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_path_to_root_analysis_blocked")
        if _status(source_map_source_logpoint_install_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_source_logpoint_install_result_blocked")
        if _status(source_map_hook_candidates) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_hook_candidates_blocked")
        if _status(source_map_hook_candidate_selection) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_hook_candidate_selection_blocked")
        source_map_hook_candidate_selection_policy = (
            source_map_hook_candidate_selection.get("side_effect_policy")
            if isinstance(source_map_hook_candidate_selection.get("side_effect_policy"), dict)
            else {}
        )
        if (
            bool(source_map_hook_candidate_selection.get("hook_installed"))
            or bool(source_map_hook_candidate_selection.get("automatic_hook_installation"))
            or bool(source_map_hook_candidate_selection_policy.get("hook_installed"))
            or bool(source_map_hook_candidate_selection_policy.get("automatic_hook_installation"))
            or bool(source_map_hook_candidate_selection_policy.get("runtime_evaluated"))
            or bool(source_map_hook_candidate_selection_policy.get("cdp_command_sent"))
        ):
            blockers.append("source_map_hook_candidate_selection_unexpected_side_effect")
        if _status(source_map_hook_install_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_hook_install_result_blocked")
        if _status(source_map_rebuild_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_rebuild_result_blocked")
        if _status(source_map_rebuild_generation_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_rebuild_generation_result_blocked")
        if _status(object_graph_diff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("object_graph_diff_blocked")
        if _status(runtime_object_graph_diff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("runtime_object_graph_diff_blocked")
        if _status(heap_snapshot_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_readiness_blocked")
        if _status(heap_snapshot_collect) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_collect_blocked")
        if _status(heap_snapshot_diff_readiness) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_readiness_blocked")
        if _status(heap_snapshot_diff_executor_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_preflight_blocked")
        if _status(heap_snapshot_diff_executor_approval_plan) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("heap_snapshot_diff_executor_approval_plan_blocked")
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
        if source_map_followthrough_chain_readiness and _status(source_map_followthrough_chain_readiness) == "ready_for_review":
            warnings.append("source_map_followthrough_chain_readiness_requires_next_review")
        if source_map_followthrough_one_step_plan and _status(source_map_followthrough_one_step_plan) == "ready_for_review":
            warnings.append("source_map_followthrough_one_step_plan_requires_review")
        if source_map_followthrough_dispatch_preflight and _status(source_map_followthrough_dispatch_preflight) == "ready_for_review":
            warnings.append("source_map_followthrough_dispatch_preflight_requires_review")
        if source_map_followthrough_dispatch_approval_plan and _status(source_map_followthrough_dispatch_approval_plan) == "ready_for_review":
            warnings.append("source_map_followthrough_dispatch_approval_plan_requires_review")
        if source_map_followthrough_dispatch_approval_record and _status(source_map_followthrough_dispatch_approval_record) == "written" and source_map_followthrough_dispatch_approval_record.get("approved_for_dispatch") is True:
            warnings.append("source_map_followthrough_dispatch_approval_record_ready_for_transaction_preflight")
        if source_map_followthrough_dispatch_transaction_preflight and _status(source_map_followthrough_dispatch_transaction_preflight) == "ready_for_review":
            warnings.append("source_map_followthrough_dispatch_transaction_preflight_ready_for_journal_writer")
        if source_map_followthrough_dispatch_transaction_journal and _status(source_map_followthrough_dispatch_transaction_journal) == "written" and source_map_followthrough_dispatch_transaction_journal.get("journal_written") is True:
            warnings.append("source_map_followthrough_dispatch_transaction_journal_ready_for_bounded_gate")
        if source_map_followthrough_dispatch_bounded_executor_gate and _status(source_map_followthrough_dispatch_bounded_executor_gate) == "ready_for_review" and source_map_followthrough_dispatch_bounded_executor_gate.get("bounded_executor_gate_ready_for_review") is True:
            warnings.append("source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff")
        if source_map_followthrough_dispatcher_handoff and _status(source_map_followthrough_dispatcher_handoff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatcher_handoff_blocked")
        if source_map_followthrough_dispatcher_handoff and _status(source_map_followthrough_dispatcher_handoff) == "ready_for_review" and source_map_followthrough_dispatcher_handoff.get("dispatcher_handoff_ready_for_review") is True:
            warnings.append("source_map_followthrough_dispatcher_handoff_ready_for_apply_preflight_review")
        if source_map_followthrough_dispatcher_apply_preflight and _status(source_map_followthrough_dispatcher_apply_preflight) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatcher_apply_preflight_blocked")
        if source_map_followthrough_dispatcher_apply_preflight and _status(source_map_followthrough_dispatcher_apply_preflight) == "ready_for_review" and source_map_followthrough_dispatcher_apply_preflight.get("dispatcher_apply_preflight_ready_for_review") is True:
            warnings.append("source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp")
        if source_map_followthrough_dispatcher_result and _status(source_map_followthrough_dispatcher_result) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_dispatcher_result_blocked")
        if source_map_followthrough_dispatcher_result and _status(source_map_followthrough_dispatcher_result) == "review_required":
            warnings.append("source_map_followthrough_dispatcher_result_requires_review_approval")
        if source_map_followthrough_dispatcher_result and _status(source_map_followthrough_dispatcher_result) == "dispatched" and source_map_followthrough_dispatcher_result.get("dispatcher_decision_recorded") is True:
            warnings.append("source_map_followthrough_dispatcher_result_ready_for_selected_executor_apply_preflight")
        if source_map_followthrough_surface_selection and _status(source_map_followthrough_surface_selection) == "ready_for_review":
            warnings.append("source_map_followthrough_surface_selection_requires_review")
        if source_map_selected_executor_input_review and _status(source_map_selected_executor_input_review) == "ready_for_review":
            warnings.append("source_map_selected_executor_input_review_requires_review")
        if source_map_selected_executor_approval_plan and _status(source_map_selected_executor_approval_plan) == "ready_for_review":
            warnings.append("source_map_selected_executor_approval_plan_requires_review")
        if source_map_selected_executor_approval_record and _status(source_map_selected_executor_approval_record) == "written" and source_map_selected_executor_approval_record.get("approved_for_apply") is True:
            warnings.append("source_map_selected_executor_approval_record_ready_for_apply_preflight")
        if source_map_selected_executor_apply_preflight and _status(source_map_selected_executor_apply_preflight) == "ready_for_review":
            warnings.append("source_map_selected_executor_apply_preflight_ready_for_executor_review")
        if source_map_selected_executor_application_handoff and _status(source_map_selected_executor_application_handoff) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_application_handoff_blocked")
        if source_map_selected_executor_application_handoff and _status(source_map_selected_executor_application_handoff) == "ready_for_review" and source_map_selected_executor_application_handoff.get("ready_for_application_review") is True:
            warnings.append("source_map_selected_executor_application_handoff_ready_for_application_review")
        if source_map_selected_executor_result_checkpoint and _status(source_map_selected_executor_result_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_selected_executor_result_checkpoint_blocked")
        if source_map_selected_executor_result_checkpoint and _status(source_map_selected_executor_result_checkpoint) == "ready_for_review" and source_map_selected_executor_result_checkpoint.get("ready_for_next_explicit_review") is True:
            warnings.append("source_map_selected_executor_result_checkpoint_ready_for_followthrough_review")
        if source_map_followthrough_completion_checkpoint and _status(source_map_followthrough_completion_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_followthrough_completion_checkpoint_blocked")
        if source_map_followthrough_completion_checkpoint and _status(source_map_followthrough_completion_checkpoint) == "ready_for_review" and source_map_followthrough_completion_checkpoint.get("ready_for_completion_review") is True:
            warnings.append("source_map_followthrough_completion_checkpoint_ready_for_completion_review")
        if source_map_terminal_review_package and _status(source_map_terminal_review_package) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_terminal_review_package_blocked")
        if source_map_terminal_review_package and _status(source_map_terminal_review_package) == "ready_for_review" and source_map_terminal_review_package.get("ready_for_terminal_review") is True:
            warnings.append("source_map_terminal_review_package_ready_for_review")
        if source_map_terminal_review_closure_checkpoint and _status(source_map_terminal_review_closure_checkpoint) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_terminal_review_closure_checkpoint_blocked")
        if source_map_terminal_review_closure_checkpoint and _status(source_map_terminal_review_closure_checkpoint) == "ready_for_review" and source_map_terminal_review_closure_checkpoint.get("ready_for_closure_audit_review") is True:
            warnings.append("source_map_terminal_review_closure_checkpoint_ready_for_closure_review")
        if source_map_terminal_review_final_audit and _status(source_map_terminal_review_final_audit) in {"blocked", "failed", "failure", "error", "unsupported"}:
            blockers.append("source_map_terminal_review_final_audit_blocked")
        if source_map_terminal_review_final_audit and _status(source_map_terminal_review_final_audit) == "ready_for_review" and source_map_terminal_review_final_audit.get("ready_for_final_audit_review") is True:
            warnings.append("source_map_terminal_review_final_audit_ready_for_review")
        if source_map_source_logpoint_install_result and _status(source_map_source_logpoint_install_result) in {"success", "applied", "installed"}:
            warnings.append("source_map_source_logpoint_install_result_requires_timeline_review")
        if source_map_hook_candidates and _status(source_map_hook_candidates) in {"ready_for_review", "success", "generated"}:
            warnings.append("source_map_hook_candidates_require_review")
        if source_map_hook_candidate_selection and _status(source_map_hook_candidate_selection) in {"ready_for_review", "success", "generated"}:
            warnings.append("source_map_hook_candidate_selection_requires_input_review")
        if source_map_hook_install_result and _status(source_map_hook_install_result) in {"success", "applied", "installed"}:
            warnings.append("source_map_hook_install_result_requires_timeline_review")
        if source_map_rebuild_result and _status(source_map_rebuild_result) in {"success", "applied", "ready_for_rebuild_review"}:
            warnings.append("source_map_rebuild_result_requires_rebuild_review")
        if source_map_rebuild_generation_result and _status(source_map_rebuild_generation_result) in {"success", "generated", "applied"}:
            warnings.append("source_map_rebuild_generation_result_requires_rebuild_artifact_review")
        if object_graph_diff and _status(object_graph_diff) == "ready_for_review":
            warnings.append("object_graph_diff_requires_review")
        if runtime_object_graph_diff and _status(runtime_object_graph_diff) == "ready_for_review":
            warnings.append("runtime_object_graph_diff_requires_review")
        if heap_snapshot_readiness and _status(heap_snapshot_readiness) == "ready_for_review":
            warnings.append("heap_snapshot_readiness_requires_review")
        if heap_snapshot_collect and _status(heap_snapshot_collect) == "collected":
            warnings.append("heap_snapshot_collect_requires_review")
        if heap_snapshot_diff_readiness and _status(heap_snapshot_diff_readiness) == "ready_for_review":
            warnings.append("heap_snapshot_diff_readiness_requires_review")
        if heap_snapshot_diff_executor_preflight and _status(heap_snapshot_diff_executor_preflight) == "ready_for_review":
            warnings.append("heap_snapshot_diff_executor_preflight_requires_review")
        if heap_snapshot_diff_executor_approval_plan and _status(heap_snapshot_diff_executor_approval_plan) == "ready_for_review":
            warnings.append("heap_snapshot_diff_executor_approval_plan_requires_review")
        if heap_snapshot_diff_executor_approval_record and _status(heap_snapshot_diff_executor_approval_record) == "written" and heap_snapshot_diff_executor_approval_record.get("approved_for_execution") is True:
            warnings.append("heap_snapshot_diff_executor_approval_record_ready_for_transaction_preflight")
        if heap_snapshot_diff_executor_transaction_preflight and _status(heap_snapshot_diff_executor_transaction_preflight) == "ready_for_review":
            warnings.append("heap_snapshot_diff_executor_transaction_preflight_ready_for_journal_writer")
        if heap_snapshot_diff_executor_transaction_journal and _status(heap_snapshot_diff_executor_transaction_journal) == "written" and heap_snapshot_diff_executor_transaction_journal.get("journal_written") is True:
            warnings.append("heap_snapshot_diff_executor_transaction_journal_ready_for_bounded_gate")
        if heap_snapshot_diff_executor_bounded_gate and _status(heap_snapshot_diff_executor_bounded_gate) == "ready_for_review" and heap_snapshot_diff_executor_bounded_gate.get("bounded_executor_gate_ready_for_review") is True:
            warnings.append("heap_snapshot_diff_executor_bounded_gate_ready_for_executor_review")
        if heap_snapshot_diff_executor_result and _status(heap_snapshot_diff_executor_result) == "executed" and heap_snapshot_diff_executor_result.get("heap_diff_computed") is True:
            warnings.append("heap_snapshot_diff_executor_result_requires_review")
        if heap_snapshot_diff_followup_checkpoint and _status(heap_snapshot_diff_followup_checkpoint) == "ready_for_review":
            warnings.append("heap_snapshot_diff_followup_checkpoint_requires_review")
        if heap_snapshot_diff_selected_analysis_input_preflight and _status(heap_snapshot_diff_selected_analysis_input_preflight) == "ready_for_review":
            warnings.append("heap_snapshot_diff_selected_analysis_input_preflight_requires_review")
        if heap_snapshot_constructor_growth_drilldown and _status(heap_snapshot_constructor_growth_drilldown) == "ready_for_review":
            warnings.append("heap_snapshot_constructor_growth_drilldown_requires_review")
        if heap_snapshot_constructor_growth_drilldown_analysis and _status(heap_snapshot_constructor_growth_drilldown_analysis) == "executed" and heap_snapshot_constructor_growth_drilldown_analysis.get("constructor_drilldown_computed") is True:
            warnings.append("heap_snapshot_constructor_growth_drilldown_analysis_ready_for_retained_size_path_or_second_pass_review")
        if heap_snapshot_automatic_followup_plan and _status(heap_snapshot_automatic_followup_plan) == "ready_for_review":
            warnings.append("heap_snapshot_automatic_followup_plan_ready_for_proof_or_second_pass_review")
        if heap_snapshot_retained_size_proof_plan and _status(heap_snapshot_retained_size_proof_plan) == "ready_for_review":
            warnings.append("heap_snapshot_retained_size_proof_plan_ready_for_raw_heap_ingestion_review")
        if heap_snapshot_path_to_root_proof_plan and _status(heap_snapshot_path_to_root_proof_plan) == "ready_for_review":
            warnings.append("heap_snapshot_path_to_root_proof_plan_ready_for_raw_heap_ingestion_review")
        if heap_snapshot_raw_heap_constructor_drilldown_proof_plan and _status(heap_snapshot_raw_heap_constructor_drilldown_proof_plan) == "ready_for_review":
            warnings.append("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_for_raw_heap_ingestion_review")
        if heap_snapshot_retained_path_preflight and _status(heap_snapshot_retained_path_preflight) == "ready_for_review":
            warnings.append("heap_snapshot_retained_path_preflight_requires_review")
        if heap_snapshot_retained_size_input_review and _status(heap_snapshot_retained_size_input_review) == "ready_for_review":
            warnings.append("heap_snapshot_retained_size_input_review_requires_review")
        if heap_snapshot_retained_size_approval_plan and _status(heap_snapshot_retained_size_approval_plan) == "ready_for_review":
            warnings.append("heap_snapshot_retained_size_approval_plan_requires_review")
        if heap_snapshot_retained_size_approval_record and _status(heap_snapshot_retained_size_approval_record) == "written" and heap_snapshot_retained_size_approval_record.get("approved_for_execution") is True:
            warnings.append("heap_snapshot_retained_size_approval_record_ready_for_transaction_preflight")
        if heap_snapshot_retained_size_transaction_preflight and _status(heap_snapshot_retained_size_transaction_preflight) == "ready_for_review":
            warnings.append("heap_snapshot_retained_size_transaction_preflight_ready_for_journal_writer")
        if heap_snapshot_retained_size_transaction_journal and _status(heap_snapshot_retained_size_transaction_journal) == "written" and heap_snapshot_retained_size_transaction_journal.get("journal_written") is True:
            warnings.append("heap_snapshot_retained_size_transaction_journal_ready_for_bounded_gate")
        if heap_snapshot_retained_size_bounded_gate and _status(heap_snapshot_retained_size_bounded_gate) == "ready_for_review" and heap_snapshot_retained_size_bounded_gate.get("bounded_executor_gate_ready_for_review") is True:
            warnings.append("heap_snapshot_retained_size_bounded_gate_ready_for_executor_review")
        if heap_snapshot_retained_size_analysis and _status(heap_snapshot_retained_size_analysis) == "executed" and heap_snapshot_retained_size_analysis.get("retained_size_estimated") is True:
            warnings.append("heap_snapshot_retained_size_analysis_ready_for_path_to_root_or_second_pass_review")
        if heap_snapshot_path_to_root_analysis and _status(heap_snapshot_path_to_root_analysis) == "executed" and (heap_snapshot_path_to_root_analysis.get("path_to_root_estimated") is True or _nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "path_to_root_estimated") is True):
            warnings.append("heap_snapshot_path_to_root_analysis_ready_for_second_pass_or_constructor_drilldown_review")
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
                "source_map_followthrough_chain_readiness_status": _status(source_map_followthrough_chain_readiness),
                "source_map_followthrough_chain_readiness_selected_consumer": source_map_followthrough_chain_readiness.get("selected_consumer"),
                "source_map_followthrough_chain_readiness_completed_stage": source_map_followthrough_chain_readiness.get("completed_stage"),
                "source_map_followthrough_chain_readiness_next_stage": source_map_followthrough_chain_readiness.get("next_stage"),
                "source_map_followthrough_chain_readiness_next_action": source_map_followthrough_chain_readiness.get("next_action"),
                "source_map_followthrough_one_step_plan_status": _status(source_map_followthrough_one_step_plan),
                "source_map_followthrough_one_step_plan_selected_consumer": source_map_followthrough_one_step_plan.get("selected_consumer"),
                "source_map_followthrough_one_step_plan_source_chain_completed_stage": source_map_followthrough_one_step_plan.get("source_chain_completed_stage"),
                "source_map_followthrough_one_step_plan_source_chain_next_stage": source_map_followthrough_one_step_plan.get("source_chain_next_stage"),
                "source_map_followthrough_one_step_plan_source_chain_next_action": source_map_followthrough_one_step_plan.get("source_chain_next_action"),
                "source_map_followthrough_one_step_plan_planned_step_ready_for_review": bool(source_map_followthrough_one_step_plan.get("planned_step_ready_for_review")),
                "source_map_followthrough_dispatch_preflight_status": _status(source_map_followthrough_dispatch_preflight),
                "source_map_followthrough_dispatch_preflight_selected_consumer": source_map_followthrough_dispatch_preflight.get("selected_consumer"),
                "source_map_followthrough_dispatch_preflight_planned_next_action": source_map_followthrough_dispatch_preflight.get("planned_next_action"),
                "source_map_followthrough_dispatch_preflight_dispatch_surface": (source_map_followthrough_dispatch_preflight.get("dispatch_target") or {}).get("dispatch_surface") if isinstance(source_map_followthrough_dispatch_preflight.get("dispatch_target"), dict) else None,
                "source_map_followthrough_dispatch_preflight_dispatcher_input_ready_for_review": bool(source_map_followthrough_dispatch_preflight.get("dispatcher_input_ready_for_review")),
                "source_map_followthrough_dispatch_approval_plan_status": _status(source_map_followthrough_dispatch_approval_plan),
                "source_map_followthrough_dispatch_approval_plan_selected_consumer": source_map_followthrough_dispatch_approval_plan.get("selected_consumer"),
                "source_map_followthrough_dispatch_approval_plan_dispatch_surface": source_map_followthrough_dispatch_approval_plan.get("dispatch_surface"),
                "source_map_followthrough_dispatch_approval_plan_ready_for_review": bool(source_map_followthrough_dispatch_approval_plan.get("approval_plan_ready_for_review")),
                "source_map_followthrough_dispatch_approval_plan_ready_to_dispatch_now": bool(source_map_followthrough_dispatch_approval_plan.get("ready_to_dispatch_now")),
                "source_map_followthrough_dispatch_approval_record_status": _status(source_map_followthrough_dispatch_approval_record),
                "source_map_followthrough_dispatch_approval_record_selected_consumer": source_map_followthrough_dispatch_approval_record.get("selected_consumer"),
                "source_map_followthrough_dispatch_approval_record_dispatch_surface": source_map_followthrough_dispatch_approval_record.get("dispatch_surface"),
                "source_map_followthrough_dispatch_approval_record_approved_for_dispatch": bool(source_map_followthrough_dispatch_approval_record.get("approved_for_dispatch")),
                "source_map_followthrough_dispatch_approval_record_next_action": source_map_followthrough_dispatch_approval_record.get("next_action"),
                "source_map_followthrough_dispatch_transaction_preflight_status": _status(source_map_followthrough_dispatch_transaction_preflight),
                "source_map_followthrough_dispatch_transaction_preflight_selected_consumer": source_map_followthrough_dispatch_transaction_preflight.get("selected_consumer"),
                "source_map_followthrough_dispatch_transaction_preflight_dispatch_surface": source_map_followthrough_dispatch_transaction_preflight.get("dispatch_surface"),
                "source_map_followthrough_dispatch_transaction_preflight_ready_for_review": bool(source_map_followthrough_dispatch_transaction_preflight.get("transaction_preflight_ready_for_review")),
                "source_map_followthrough_dispatch_transaction_preflight_journal_writer_gate_ready": bool(source_map_followthrough_dispatch_transaction_preflight.get("journal_writer_gate_ready_for_review")),
                "source_map_followthrough_dispatch_transaction_preflight_next_action": source_map_followthrough_dispatch_transaction_preflight.get("next_action"),
                "source_map_followthrough_dispatch_transaction_journal_status": _status(source_map_followthrough_dispatch_transaction_journal),
                "source_map_followthrough_dispatch_transaction_journal_selected_consumer": source_map_followthrough_dispatch_transaction_journal.get("selected_consumer"),
                "source_map_followthrough_dispatch_transaction_journal_dispatch_surface": source_map_followthrough_dispatch_transaction_journal.get("dispatch_surface"),
                "source_map_followthrough_dispatch_transaction_journal_written": bool(source_map_followthrough_dispatch_transaction_journal.get("journal_written")),
                "source_map_followthrough_dispatch_transaction_journal_started": bool(source_map_followthrough_dispatch_transaction_journal.get("transaction_started")),
                "source_map_followthrough_dispatch_transaction_journal_next_action": source_map_followthrough_dispatch_transaction_journal.get("next_action"),
                "source_map_followthrough_dispatch_bounded_executor_gate_status": _status(source_map_followthrough_dispatch_bounded_executor_gate),
                "source_map_followthrough_dispatch_bounded_executor_gate_selected_consumer": source_map_followthrough_dispatch_bounded_executor_gate.get("selected_consumer"),
                "source_map_followthrough_dispatch_bounded_executor_gate_dispatch_surface": source_map_followthrough_dispatch_bounded_executor_gate.get("dispatch_surface"),
                "source_map_followthrough_dispatch_bounded_executor_gate_ready_for_review": bool(source_map_followthrough_dispatch_bounded_executor_gate.get("bounded_executor_gate_ready_for_review")),
                "source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff": bool(source_map_followthrough_dispatch_bounded_executor_gate.get("ready_for_dispatcher_handoff_review")),
                "source_map_followthrough_dispatch_bounded_executor_gate_next_action": source_map_followthrough_dispatch_bounded_executor_gate.get("next_action"),
                "source_map_followthrough_dispatcher_handoff_status": _status(source_map_followthrough_dispatcher_handoff),
                "source_map_followthrough_dispatcher_handoff_selected_consumer": source_map_followthrough_dispatcher_handoff.get("selected_consumer"),
                "source_map_followthrough_dispatcher_handoff_dispatch_surface": source_map_followthrough_dispatcher_handoff.get("dispatch_surface"),
                "source_map_followthrough_dispatcher_handoff_ready_for_review": bool(source_map_followthrough_dispatcher_handoff.get("dispatcher_handoff_ready_for_review")),
                "source_map_followthrough_dispatcher_handoff_ready_for_explicit_dispatch_review": bool(source_map_followthrough_dispatcher_handoff.get("ready_for_explicit_dispatch_review")),
                "source_map_followthrough_dispatcher_handoff_next_action": source_map_followthrough_dispatcher_handoff.get("next_action"),
                "source_map_followthrough_dispatcher_apply_preflight_status": _status(source_map_followthrough_dispatcher_apply_preflight),
                "source_map_followthrough_dispatcher_apply_preflight_selected_consumer": source_map_followthrough_dispatcher_apply_preflight.get("selected_consumer"),
                "source_map_followthrough_dispatcher_apply_preflight_dispatch_surface": source_map_followthrough_dispatcher_apply_preflight.get("dispatch_surface"),
                "source_map_followthrough_dispatcher_apply_preflight_ready_for_review": bool(source_map_followthrough_dispatcher_apply_preflight.get("dispatcher_apply_preflight_ready_for_review")),
                "source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp": bool(source_map_followthrough_dispatcher_apply_preflight.get("ready_for_explicit_dispatcher_mvp_review")),
                "source_map_followthrough_dispatcher_apply_preflight_next_action": source_map_followthrough_dispatcher_apply_preflight.get("next_action"),
                "source_map_followthrough_dispatcher_result_status": _status(source_map_followthrough_dispatcher_result),
                "source_map_followthrough_dispatcher_result_selected_consumer": source_map_followthrough_dispatcher_result.get("selected_consumer"),
                "source_map_followthrough_dispatcher_result_dispatch_surface": source_map_followthrough_dispatcher_result.get("dispatch_surface"),
                "source_map_followthrough_dispatcher_result_decision_recorded": bool(source_map_followthrough_dispatcher_result.get("dispatcher_decision_recorded")),
                "source_map_followthrough_dispatcher_result_dispatch_target_invoked": bool(source_map_followthrough_dispatcher_result.get("dispatch_target_invoked")),
                "source_map_followthrough_dispatcher_result_selected_executor_invoked": bool(source_map_followthrough_dispatcher_result.get("selected_executor_invoked")),
                "source_map_followthrough_dispatcher_result_selected_executor_apply_preflight_invoked": bool(source_map_followthrough_dispatcher_result.get("selected_executor_apply_preflight_invoked")),
                "source_map_followthrough_dispatcher_result_next_action": source_map_followthrough_dispatcher_result.get("next_action"),
                "source_map_followthrough_surface_selection_status": _status(source_map_followthrough_surface_selection),
                "source_map_followthrough_surface_selection_selected_consumer": source_map_followthrough_surface_selection.get("selected_consumer"),
                "source_map_followthrough_surface_selection_next_action": source_map_followthrough_surface_selection.get("next_action"),
                "source_map_selected_executor_input_review_status": _status(source_map_selected_executor_input_review),
                "source_map_selected_executor_input_review_selected_consumer": source_map_selected_executor_input_review.get("selected_consumer"),
                "source_map_selected_executor_input_review_next_action": source_map_selected_executor_input_review.get("next_action"),
                "source_map_selected_executor_approval_plan_status": _status(source_map_selected_executor_approval_plan),
                "source_map_selected_executor_approval_plan_selected_consumer": source_map_selected_executor_approval_plan.get("selected_consumer"),
                "source_map_selected_executor_approval_plan_next_action": source_map_selected_executor_approval_plan.get("next_action"),
                "source_map_selected_executor_approval_record_status": _status(source_map_selected_executor_approval_record),
                "source_map_selected_executor_approval_record_selected_consumer": source_map_selected_executor_approval_record.get("selected_consumer"),
                "source_map_selected_executor_approval_record_approved_for_apply": bool(source_map_selected_executor_approval_record.get("approved_for_apply")),
                "source_map_selected_executor_approval_record_next_action": source_map_selected_executor_approval_record.get("next_action"),
                "source_map_selected_executor_apply_preflight_status": _status(source_map_selected_executor_apply_preflight),
                "source_map_selected_executor_apply_preflight_selected_consumer": source_map_selected_executor_apply_preflight.get("selected_consumer"),
                "source_map_selected_executor_apply_preflight_ready_for_selected_executor_review": bool(source_map_selected_executor_apply_preflight.get("ready_for_selected_executor_review")),
                "source_map_selected_executor_apply_preflight_next_action": source_map_selected_executor_apply_preflight.get("next_action"),
                "source_map_selected_executor_application_handoff_status": _status(source_map_selected_executor_application_handoff),
                "source_map_selected_executor_application_handoff_selected_consumer": source_map_selected_executor_application_handoff.get("selected_consumer"),
                "source_map_selected_executor_application_handoff_application_surface": source_map_selected_executor_application_handoff.get("application_surface"),
                "source_map_selected_executor_application_handoff_ready_for_application_review": bool(source_map_selected_executor_application_handoff.get("ready_for_application_review")),
                "source_map_selected_executor_application_handoff_next_action": source_map_selected_executor_application_handoff.get("next_action"),
                "source_map_selected_executor_result_checkpoint_status": _status(source_map_selected_executor_result_checkpoint),
                "source_map_selected_executor_result_checkpoint_selected_consumer": source_map_selected_executor_result_checkpoint.get("selected_consumer"),
                "source_map_selected_executor_result_checkpoint_application_surface": source_map_selected_executor_result_checkpoint.get("application_surface"),
                "source_map_selected_executor_result_checkpoint_ready_for_next_explicit_review": bool(source_map_selected_executor_result_checkpoint.get("ready_for_next_explicit_review")),
                "source_map_selected_executor_result_checkpoint_next_action": source_map_selected_executor_result_checkpoint.get("next_action"),
                "source_map_followthrough_completion_checkpoint_status": _status(source_map_followthrough_completion_checkpoint),
                "source_map_followthrough_completion_checkpoint_selected_consumer": source_map_followthrough_completion_checkpoint.get("selected_consumer"),
                "source_map_followthrough_completion_checkpoint_completion_status": source_map_followthrough_completion_checkpoint.get("completion_status"),
                "source_map_followthrough_completion_checkpoint_terminal_review_candidate": bool(source_map_followthrough_completion_checkpoint.get("terminal_review_candidate")),
                "source_map_followthrough_completion_checkpoint_followup_required": bool(source_map_followthrough_completion_checkpoint.get("followup_required")),
                "source_map_followthrough_completion_checkpoint_next_action": source_map_followthrough_completion_checkpoint.get("next_action"),
                "source_map_terminal_review_package_status": _status(source_map_terminal_review_package),
                "source_map_terminal_review_package_selected_consumer": source_map_terminal_review_package.get("selected_consumer"),
                "source_map_terminal_review_package_completion_status": source_map_terminal_review_package.get("completion_status"),
                "source_map_terminal_review_package_package_kind": (source_map_terminal_review_package.get("terminal_review_package") or {}).get("package_kind") if isinstance(source_map_terminal_review_package.get("terminal_review_package"), dict) else None,
                "source_map_terminal_review_package_ready_for_terminal_review": bool(source_map_terminal_review_package.get("ready_for_terminal_review")),
                "source_map_terminal_review_package_next_action": source_map_terminal_review_package.get("next_action"),
                "source_map_terminal_review_closure_checkpoint_status": _status(source_map_terminal_review_closure_checkpoint),
                "source_map_terminal_review_closure_checkpoint_selected_consumer": source_map_terminal_review_closure_checkpoint.get("selected_consumer"),
                "source_map_terminal_review_closure_checkpoint_closure_status": source_map_terminal_review_closure_checkpoint.get("closure_status"),
                "source_map_terminal_review_closure_checkpoint_ready_for_closure_audit_review": bool(source_map_terminal_review_closure_checkpoint.get("ready_for_closure_audit_review")),
                "source_map_terminal_review_closure_checkpoint_next_action": source_map_terminal_review_closure_checkpoint.get("next_action"),
                "source_map_terminal_review_final_audit_status": _status(source_map_terminal_review_final_audit),
                "source_map_terminal_review_final_audit_selected_consumer": source_map_terminal_review_final_audit.get("selected_consumer"),
                "source_map_terminal_review_final_audit_final_audit_status": source_map_terminal_review_final_audit.get("final_audit_status"),
                "source_map_terminal_review_final_audit_ready_for_final_audit_review": bool(source_map_terminal_review_final_audit.get("ready_for_final_audit_review")),
                "source_map_terminal_review_final_audit_next_action": source_map_terminal_review_final_audit.get("next_action"),
                "source_map_source_logpoint_install_result_status": _status(source_map_source_logpoint_install_result),
                "source_map_source_logpoint_install_result_breakpoint_count": _intish(source_map_source_logpoint_install_result.get("breakpoint_count")),
                "source_map_source_logpoint_install_result_event_count": _intish(source_map_source_logpoint_install_result.get("event_count")),
                "source_map_source_logpoint_install_result_logpoint_installed": bool(source_map_source_logpoint_install_result.get("logpoint_installed")),
                "source_map_hook_candidates_status": _status(source_map_hook_candidates),
                "source_map_hook_candidates_candidate_count": _intish(source_map_hook_candidates.get("candidate_count")),
                "source_map_hook_candidates_ready_for_install_review_count": _intish(source_map_hook_candidates.get("ready_for_hook_install_review_count")),
                "source_map_hook_candidates_bundler_kind": source_map_hook_candidates.get("bundler_kind"),
                "source_map_hook_candidates_candidate_ids": source_map_hook_candidates.get("candidate_ids") or [
                    str(item.get("candidate_id"))
                    for item in (source_map_hook_candidates.get("candidates") if isinstance(source_map_hook_candidates.get("candidates"), list) else [])
                    if isinstance(item, dict) and item.get("candidate_id")
                ],
                "source_map_hook_candidate_selection_status": _status(source_map_hook_candidate_selection),
                "source_map_hook_candidate_selection_candidate_count": _intish(source_map_hook_candidate_selection.get("candidate_count")),
                "source_map_hook_candidate_selection_selected_candidate_id": source_map_hook_candidate_selection.get("selected_candidate_id"),
                "source_map_hook_candidate_selection_selected_action_id": source_map_hook_candidate_selection.get("selected_action_id"),
                "source_map_hook_candidate_selection_selected_consumer": source_map_hook_candidate_selection.get("selected_consumer"),
                "source_map_hook_candidate_selection_ready_for_selected_executor_input_review": bool(source_map_hook_candidate_selection.get("ready_for_selected_executor_input_review")),
                "source_map_hook_candidate_selection_hook_installed": bool(source_map_hook_candidate_selection.get("hook_installed")) or bool(source_map_hook_candidate_selection_policy.get("hook_installed")),
                "source_map_hook_candidate_selection_automatic_hook_installation": bool(source_map_hook_candidate_selection.get("automatic_hook_installation")) or bool(source_map_hook_candidate_selection_policy.get("automatic_hook_installation")),
                "source_map_hook_candidate_selection_calls_mcp": bool(source_map_hook_candidate_selection.get("calls_mcp")) or bool(source_map_hook_candidate_selection_policy.get("calls_mcp")),
                "source_map_hook_candidate_selection_mobile_runtime_used": bool(source_map_hook_candidate_selection.get("mobile_runtime_used")) or bool(source_map_hook_candidate_selection_policy.get("mobile_runtime_used")),
                "source_map_hook_install_result_status": _status(source_map_hook_install_result),
                "source_map_hook_install_result_hook_kind": source_map_hook_install_result.get("hook_kind"),
                "source_map_hook_install_result_installed_count": _intish(source_map_hook_install_result.get("installed_count")),
                "source_map_hook_install_result_event_count": _intish(source_map_hook_install_result.get("event_count")),
                "source_map_hook_install_result_hook_installed": bool(source_map_hook_install_result.get("hook_installed")),
                "source_map_rebuild_result_status": _status(source_map_rebuild_result),
                "source_map_rebuild_result_digest": source_map_rebuild_result.get("source_content_digest"),
                "source_map_rebuild_result_metadata_only": bool(source_map_rebuild_result.get("metadata_only")),
                "source_map_rebuild_result_rebuild_metadata_applied": bool(source_map_rebuild_result.get("rebuild_metadata_applied")),
                "source_map_rebuild_result_rebuild_executed": bool(source_map_rebuild_result.get("rebuild_executed")),
                "source_map_rebuild_generation_result_status": _status(source_map_rebuild_generation_result),
                "source_map_rebuild_generation_result_ready": bool(source_map_rebuild_generation_result.get("rebuild_ready")),
                "source_map_rebuild_generation_result_generated_file_count": _intish(source_map_rebuild_generation_result.get("generated_file_count")),
                "source_map_rebuild_generation_result_rebuild_bundle_generated": bool(source_map_rebuild_generation_result.get("rebuild_bundle_generated")),
                "source_map_rebuild_generation_result_rebuild_executed": bool(source_map_rebuild_generation_result.get("rebuild_executed")),
                "source_map_rebuild_generation_result_algorithm_strategy_id": source_map_rebuild_generation_result.get("algorithm_strategy_id"),
                "object_graph_diff_status": _status(object_graph_diff),
                "object_graph_diff_change_count": _intish(object_graph_diff.get("change_count") or _nested_get(object_graph_diff, "diff", "change_count")),
                "object_graph_diff_risk": _nested_get(object_graph_diff, "risk_summary", "risk"),
                "object_graph_diff_next_action": object_graph_diff.get("next_action"),
                "runtime_object_graph_diff_status": _status(runtime_object_graph_diff),
                "runtime_object_graph_diff_root_path": _nested_get(runtime_object_graph_diff, "runtime_collection", "root_path"),
                "runtime_object_graph_diff_change_count": _intish(runtime_object_graph_diff.get("change_count") or _nested_get(runtime_object_graph_diff, "diff", "change_count")),
                "runtime_object_graph_diff_risk": _nested_get(runtime_object_graph_diff, "risk_summary", "risk"),
                "runtime_object_graph_diff_runtime_evaluated": bool(_nested_get(runtime_object_graph_diff, "side_effect_policy", "runtime_evaluated")),
                "runtime_object_graph_diff_full_heap_snapshot": bool(_nested_get(runtime_object_graph_diff, "side_effect_policy", "full_heap_snapshot")),
                "runtime_object_graph_diff_next_action": runtime_object_graph_diff.get("next_action"),
                "heap_snapshot_readiness_status": _status(heap_snapshot_readiness),
                "heap_snapshot_readiness_provider_id": _nested_get(heap_snapshot_readiness, "capability_evidence", "browser_provider_id"),
                "heap_snapshot_readiness_cdp_available": _nested_get(heap_snapshot_readiness, "capability_evidence", "cdp_available"),
                "heap_snapshot_readiness_heap_profiler_capability": _nested_get(heap_snapshot_readiness, "capability_evidence", "heap_profiler_capability"),
                "heap_snapshot_readiness_heap_snapshot_collected": bool(heap_snapshot_readiness.get("heap_snapshot_collected")),
                "heap_snapshot_readiness_cdp_command_sent": bool(_nested_get(heap_snapshot_readiness, "side_effect_policy", "cdp_command_sent")),
                "heap_snapshot_readiness_browser_started": bool(_nested_get(heap_snapshot_readiness, "side_effect_policy", "browser_started")),
                "heap_snapshot_readiness_raw_heap_export_allowed": bool(_nested_get(heap_snapshot_readiness, "safety_gates", "raw_heap_export_allowed")),
                "heap_snapshot_readiness_next_action": heap_snapshot_readiness.get("next_action"),
                "heap_snapshot_collect_status": _status(heap_snapshot_collect),
                "heap_snapshot_collect_review_approved": bool(heap_snapshot_collect.get("review_approved")),
                "heap_snapshot_collect_explicit_collection": bool(heap_snapshot_collect.get("explicit_collection")),
                "heap_snapshot_collect_heap_snapshot_collected": bool(heap_snapshot_collect.get("heap_snapshot_collected")),
                "heap_snapshot_collect_digest": _nested_get(heap_snapshot_collect, "snapshot_metadata", "snapshot_digest"),
                "heap_snapshot_collect_byte_count": _intish(_nested_get(heap_snapshot_collect, "snapshot_metadata", "snapshot_byte_count")),
                "heap_snapshot_collect_chunk_count": _intish(_nested_get(heap_snapshot_collect, "snapshot_metadata", "chunk_count")),
                "heap_snapshot_collect_cdp_command_sent": bool(_nested_get(heap_snapshot_collect, "side_effect_policy", "cdp_command_sent")),
                "heap_snapshot_collect_heap_profiler_enabled": bool(_nested_get(heap_snapshot_collect, "side_effect_policy", "heap_profiler_enabled")),
                "heap_snapshot_collect_heap_diff_computed": bool(heap_snapshot_collect.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_collect, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_collect_raw_heap_exported": bool(heap_snapshot_collect.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_collect, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_collect_complete_heap_traversal": bool(_nested_get(heap_snapshot_collect, "side_effect_policy", "complete_heap_traversal")),
                "heap_snapshot_collect_next_action": heap_snapshot_collect.get("next_action"),
                "heap_snapshot_diff_readiness_status": _status(heap_snapshot_diff_readiness),
                "heap_snapshot_diff_readiness_before_digest": _nested_get(heap_snapshot_diff_readiness, "pair_summary", "before_digest"),
                "heap_snapshot_diff_readiness_after_digest": _nested_get(heap_snapshot_diff_readiness, "pair_summary", "after_digest"),
                "heap_snapshot_diff_readiness_digest_equal": bool(_nested_get(heap_snapshot_diff_readiness, "pair_summary", "digest_equal")),
                "heap_snapshot_diff_readiness_byte_delta": _intish(_nested_get(heap_snapshot_diff_readiness, "pair_summary", "byte_delta")),
                "heap_snapshot_diff_readiness_heap_diff_computed": bool(heap_snapshot_diff_readiness.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_readiness, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_readiness_raw_heap_loaded": bool(heap_snapshot_diff_readiness.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_readiness, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_readiness_raw_heap_exported": bool(heap_snapshot_diff_readiness.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_readiness, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_readiness_complete_heap_traversal": bool(_nested_get(heap_snapshot_diff_readiness, "side_effect_policy", "complete_heap_traversal")),
                "heap_snapshot_diff_readiness_next_action": heap_snapshot_diff_readiness.get("next_action"),
                "heap_snapshot_diff_executor_preflight_status": _status(heap_snapshot_diff_executor_preflight),
                "heap_snapshot_diff_executor_preflight_before_digest": _nested_get(heap_snapshot_diff_executor_preflight, "readiness_summary", "before_digest"),
                "heap_snapshot_diff_executor_preflight_after_digest": _nested_get(heap_snapshot_diff_executor_preflight, "readiness_summary", "after_digest"),
                "heap_snapshot_diff_executor_preflight_raw_heap_ingestion_policy": _nested_get(heap_snapshot_diff_executor_preflight, "ingestion_policy", "raw_heap_ingestion_policy"),
                "heap_snapshot_diff_executor_preflight_future_diff_executor_implemented": bool(_nested_get(heap_snapshot_diff_executor_preflight, "safety_gates", "future_diff_executor_implemented")),
                "heap_snapshot_diff_executor_preflight_raw_heap_loaded": bool(heap_snapshot_diff_executor_preflight.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_executor_preflight, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_executor_preflight_raw_heap_parsed": bool(heap_snapshot_diff_executor_preflight.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_diff_executor_preflight, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_diff_executor_preflight_raw_heap_exported": bool(heap_snapshot_diff_executor_preflight.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_executor_preflight, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_executor_preflight_heap_diff_computed": bool(heap_snapshot_diff_executor_preflight.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_executor_preflight, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_executor_preflight_complete_heap_traversal": bool(_nested_get(heap_snapshot_diff_executor_preflight, "side_effect_policy", "complete_heap_traversal")),
                "heap_snapshot_diff_executor_preflight_next_action": heap_snapshot_diff_executor_preflight.get("next_action"),
                "heap_snapshot_diff_executor_approval_plan_status": _status(heap_snapshot_diff_executor_approval_plan),
                "heap_snapshot_diff_executor_approval_plan_before_digest": _nested_get(heap_snapshot_diff_executor_approval_plan, "preflight_summary", "before_digest"),
                "heap_snapshot_diff_executor_approval_plan_after_digest": _nested_get(heap_snapshot_diff_executor_approval_plan, "preflight_summary", "after_digest"),
                "heap_snapshot_diff_executor_approval_plan_approval_scope": _nested_get(heap_snapshot_diff_executor_approval_plan, "approval_plan", "approval_scope"),
                "heap_snapshot_diff_executor_approval_plan_approval_recorded": bool(heap_snapshot_diff_executor_approval_plan.get("approval_recorded")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "approval_recorded")),
                "heap_snapshot_diff_executor_approval_plan_transaction_started": bool(heap_snapshot_diff_executor_approval_plan.get("transaction_started")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "transaction_started")),
                "heap_snapshot_diff_executor_approval_plan_journal_written_now": bool(heap_snapshot_diff_executor_approval_plan.get("journal_written_now")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "journal_written_now")),
                "heap_snapshot_diff_executor_approval_plan_future_executor_implemented": bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "future_executor_contract", "implemented")),
                "heap_snapshot_diff_executor_approval_plan_executor_invoked": bool(heap_snapshot_diff_executor_approval_plan.get("executor_invoked")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "executor_invoked")),
                "heap_snapshot_diff_executor_approval_plan_raw_heap_loaded": bool(heap_snapshot_diff_executor_approval_plan.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_executor_approval_plan_raw_heap_exported": bool(heap_snapshot_diff_executor_approval_plan.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_executor_approval_plan_heap_diff_computed": bool(heap_snapshot_diff_executor_approval_plan.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_executor_approval_plan_complete_heap_traversal": bool(_nested_get(heap_snapshot_diff_executor_approval_plan, "side_effect_policy", "complete_heap_traversal")),
                "heap_snapshot_diff_executor_approval_plan_next_action": heap_snapshot_diff_executor_approval_plan.get("next_action"),
                "heap_snapshot_diff_executor_approval_record_status": _status(heap_snapshot_diff_executor_approval_record),
                "heap_snapshot_diff_executor_approval_record_approval_scope": heap_snapshot_diff_executor_approval_record.get("approval_scope"),
                "heap_snapshot_diff_executor_approval_record_approval_recorded": bool(heap_snapshot_diff_executor_approval_record.get("approval_recorded")),
                "heap_snapshot_diff_executor_approval_record_approved_for_execution": bool(heap_snapshot_diff_executor_approval_record.get("approved_for_execution")),
                "heap_snapshot_diff_executor_approval_record_transaction_started": bool(_nested_get(heap_snapshot_diff_executor_approval_record, "executor_input_gates", "transaction_started")),
                "heap_snapshot_diff_executor_approval_record_journal_written": bool(_nested_get(heap_snapshot_diff_executor_approval_record, "executor_input_gates", "journal_written")),
                "heap_snapshot_diff_executor_approval_record_executor_invoked": bool(_nested_get(heap_snapshot_diff_executor_approval_record, "executor_input_gates", "executor_invoked")) or bool(heap_snapshot_diff_executor_approval_record.get("executor_invoked")),
                "heap_snapshot_diff_executor_approval_record_raw_heap_loaded": bool(heap_snapshot_diff_executor_approval_record.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_executor_approval_record, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_executor_approval_record_raw_heap_parsed": bool(heap_snapshot_diff_executor_approval_record.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_diff_executor_approval_record, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_diff_executor_approval_record_raw_heap_exported": bool(heap_snapshot_diff_executor_approval_record.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_executor_approval_record, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_executor_approval_record_heap_diff_computed": bool(heap_snapshot_diff_executor_approval_record.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_executor_approval_record, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_executor_approval_record_next_action": heap_snapshot_diff_executor_approval_record.get("next_action"),
                "heap_snapshot_diff_executor_transaction_preflight_status": _status(heap_snapshot_diff_executor_transaction_preflight),
                "heap_snapshot_diff_executor_transaction_preflight_approval_scope": _nested_get(heap_snapshot_diff_executor_transaction_preflight, "approval_summary", "approval_scope"),
                "heap_snapshot_diff_executor_transaction_preflight_approval_recorded": bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "approval_summary", "approval_recorded")),
                "heap_snapshot_diff_executor_transaction_preflight_approved_for_execution": bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "approval_summary", "approved_for_execution")),
                "heap_snapshot_diff_executor_transaction_preflight_transaction_id": _nested_get(heap_snapshot_diff_executor_transaction_preflight, "transaction_summary", "transaction_id"),
                "heap_snapshot_diff_executor_transaction_preflight_idempotency_key": _nested_get(heap_snapshot_diff_executor_transaction_preflight, "transaction_summary", "idempotency_key"),
                "heap_snapshot_diff_executor_transaction_preflight_ready_to_write_journal": bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "journal_writer_contract", "ready_for_journal_review")),
                "heap_snapshot_diff_executor_transaction_preflight_transaction_started": bool(heap_snapshot_diff_executor_transaction_preflight.get("transaction_started")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "transaction_started")),
                "heap_snapshot_diff_executor_transaction_preflight_journal_written": bool(heap_snapshot_diff_executor_transaction_preflight.get("journal_written")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "journal_written")),
                "heap_snapshot_diff_executor_transaction_preflight_bounded_executor_gate_written": bool(heap_snapshot_diff_executor_transaction_preflight.get("bounded_executor_gate_written")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "bounded_executor_gate_written")),
                "heap_snapshot_diff_executor_transaction_preflight_executor_invoked": bool(heap_snapshot_diff_executor_transaction_preflight.get("executor_invoked")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "executor_invoked")),
                "heap_snapshot_diff_executor_transaction_preflight_raw_heap_loaded": bool(heap_snapshot_diff_executor_transaction_preflight.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_executor_transaction_preflight_raw_heap_parsed": bool(heap_snapshot_diff_executor_transaction_preflight.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_diff_executor_transaction_preflight_raw_heap_exported": bool(heap_snapshot_diff_executor_transaction_preflight.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_executor_transaction_preflight_heap_diff_computed": bool(heap_snapshot_diff_executor_transaction_preflight.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_preflight, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_executor_transaction_preflight_next_action": heap_snapshot_diff_executor_transaction_preflight.get("next_action"),
                "heap_snapshot_diff_executor_transaction_journal_status": _status(heap_snapshot_diff_executor_transaction_journal),
                "heap_snapshot_diff_executor_transaction_journal_written": bool(heap_snapshot_diff_executor_transaction_journal.get("journal_written")),
                "heap_snapshot_diff_executor_transaction_journal_started": bool(heap_snapshot_diff_executor_transaction_journal.get("transaction_started")),
                "heap_snapshot_diff_executor_transaction_journal_transaction_id": heap_snapshot_diff_executor_transaction_journal.get("transaction_id"),
                "heap_snapshot_diff_executor_transaction_journal_bounded_gate_written": bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "executor_input_gates", "bounded_executor_gate_written")),
                "heap_snapshot_diff_executor_transaction_journal_executor_invoked": bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "executor_input_gates", "executor_invoked")) or bool(heap_snapshot_diff_executor_transaction_journal.get("executor_invoked")),
                "heap_snapshot_diff_executor_transaction_journal_raw_heap_loaded": bool(heap_snapshot_diff_executor_transaction_journal.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_diff_executor_transaction_journal_raw_heap_parsed": bool(heap_snapshot_diff_executor_transaction_journal.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_diff_executor_transaction_journal_raw_heap_exported": bool(heap_snapshot_diff_executor_transaction_journal.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_diff_executor_transaction_journal_heap_diff_computed": bool(heap_snapshot_diff_executor_transaction_journal.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_diff_executor_transaction_journal, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_diff_executor_transaction_journal_next_action": heap_snapshot_diff_executor_transaction_journal.get("next_action"),
                "heap_snapshot_diff_executor_bounded_gate_status": _status(heap_snapshot_diff_executor_bounded_gate),
                "heap_snapshot_diff_executor_bounded_gate_journal_id": heap_snapshot_diff_executor_bounded_gate.get("journal_id"),
                "heap_snapshot_diff_executor_bounded_gate_transaction_id": heap_snapshot_diff_executor_bounded_gate.get("transaction_id"),
                "heap_snapshot_diff_executor_bounded_gate_ready_for_review": bool(heap_snapshot_diff_executor_bounded_gate.get("bounded_executor_gate_ready_for_review")),
                "heap_snapshot_diff_executor_bounded_gate_ready_to_execute_now": bool(heap_snapshot_diff_executor_bounded_gate.get("ready_to_execute_now")),
                "heap_snapshot_diff_executor_bounded_gate_future_executor_implemented": bool((heap_snapshot_diff_executor_bounded_gate.get("future_executor_contract") or {}).get("implemented")) if isinstance(heap_snapshot_diff_executor_bounded_gate.get("future_executor_contract"), dict) else False,
                "heap_snapshot_diff_executor_bounded_gate_executor_invoked": bool(heap_snapshot_diff_executor_bounded_gate.get("executor_invoked")),
                "heap_snapshot_diff_executor_bounded_gate_raw_heap_loaded": bool(heap_snapshot_diff_executor_bounded_gate.get("raw_heap_loaded")),
                "heap_snapshot_diff_executor_bounded_gate_raw_heap_parsed": bool(heap_snapshot_diff_executor_bounded_gate.get("raw_heap_parsed")),
                "heap_snapshot_diff_executor_bounded_gate_raw_heap_exported": bool(heap_snapshot_diff_executor_bounded_gate.get("raw_heap_exported")),
                "heap_snapshot_diff_executor_bounded_gate_heap_diff_computed": bool(heap_snapshot_diff_executor_bounded_gate.get("heap_diff_computed")),
                "heap_snapshot_diff_executor_bounded_gate_next_action": heap_snapshot_diff_executor_bounded_gate.get("next_action"),
                "heap_snapshot_diff_executor_result_status": _status(heap_snapshot_diff_executor_result),
                "heap_snapshot_diff_executor_result_executor_mvp": bool(heap_snapshot_diff_executor_result.get("executor_mvp")),
                "heap_snapshot_diff_executor_result_raw_heap_loaded": bool(heap_snapshot_diff_executor_result.get("raw_heap_loaded")),
                "heap_snapshot_diff_executor_result_raw_heap_parsed": bool(heap_snapshot_diff_executor_result.get("raw_heap_parsed")),
                "heap_snapshot_diff_executor_result_raw_heap_exported": bool(heap_snapshot_diff_executor_result.get("raw_heap_exported")),
                "heap_snapshot_diff_executor_result_heap_diff_computed": bool(heap_snapshot_diff_executor_result.get("heap_diff_computed")),
                "heap_snapshot_diff_executor_result_complete_heap_traversal_claimed": bool(heap_snapshot_diff_executor_result.get("complete_heap_traversal_claimed")),
                "heap_snapshot_diff_executor_result_next_action": heap_snapshot_diff_executor_result.get("next_action"),
                "heap_snapshot_diff_followup_checkpoint_status": _status(heap_snapshot_diff_followup_checkpoint),
                "heap_snapshot_diff_followup_checkpoint_review_only": bool(heap_snapshot_diff_followup_checkpoint.get("review_only")),
                "heap_snapshot_diff_followup_checkpoint_checkpoint_only": bool(heap_snapshot_diff_followup_checkpoint.get("checkpoint_only")),
                "heap_snapshot_diff_followup_checkpoint_node_delta": ((heap_snapshot_diff_followup_checkpoint.get("executor_result_summary") or {}).get("node_count_delta") if isinstance(heap_snapshot_diff_followup_checkpoint.get("executor_result_summary"), dict) else None),
                "heap_snapshot_diff_followup_checkpoint_recommendation_count": len(((heap_snapshot_diff_followup_checkpoint.get("analysis_plan") or {}).get("recommendations") or []) if isinstance(heap_snapshot_diff_followup_checkpoint.get("analysis_plan"), dict) else []),
                "heap_snapshot_diff_followup_checkpoint_raw_heap_loaded": bool(heap_snapshot_diff_followup_checkpoint.get("raw_heap_loaded")),
                "heap_snapshot_diff_followup_checkpoint_raw_heap_parsed": bool(heap_snapshot_diff_followup_checkpoint.get("raw_heap_parsed")),
                "heap_snapshot_diff_followup_checkpoint_raw_heap_exported": bool(heap_snapshot_diff_followup_checkpoint.get("raw_heap_exported")),
                "heap_snapshot_diff_followup_checkpoint_heap_diff_computed": bool(heap_snapshot_diff_followup_checkpoint.get("heap_diff_computed")),
                "heap_snapshot_diff_followup_checkpoint_complete_heap_traversal_claimed": bool(heap_snapshot_diff_followup_checkpoint.get("complete_heap_traversal_claimed")),
                "heap_snapshot_diff_followup_checkpoint_retained_size_proven": bool(heap_snapshot_diff_followup_checkpoint.get("retained_size_proven")),
                "heap_snapshot_diff_followup_checkpoint_path_to_root_computed": bool(heap_snapshot_diff_followup_checkpoint.get("path_to_root_computed")),
                "heap_snapshot_diff_followup_checkpoint_next_action": heap_snapshot_diff_followup_checkpoint.get("next_action"),
                "heap_snapshot_diff_selected_analysis_input_preflight_status": _status(heap_snapshot_diff_selected_analysis_input_preflight),
                "heap_snapshot_diff_selected_analysis_input_preflight_review_only": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("review_only")),
                "heap_snapshot_diff_selected_analysis_input_preflight_preflight_only": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("preflight_only")),
                "heap_snapshot_diff_selected_analysis_input_preflight_selection_only": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("selection_only")),
                "heap_snapshot_diff_selected_analysis_input_preflight_selected_action": ((heap_snapshot_diff_selected_analysis_input_preflight.get("selected_analysis_input") or {}).get("selected_action") if isinstance(heap_snapshot_diff_selected_analysis_input_preflight.get("selected_analysis_input"), dict) else None),
                "heap_snapshot_diff_selected_analysis_input_preflight_candidate_count": ((heap_snapshot_diff_selected_analysis_input_preflight.get("selected_analysis_input") or {}).get("candidate_count") if isinstance(heap_snapshot_diff_selected_analysis_input_preflight.get("selected_analysis_input"), dict) else None),
                "heap_snapshot_diff_selected_analysis_input_preflight_future_executor_implemented": bool((heap_snapshot_diff_selected_analysis_input_preflight.get("future_executor_contract") or {}).get("implemented")) if isinstance(heap_snapshot_diff_selected_analysis_input_preflight.get("future_executor_contract"), dict) else False,
                "heap_snapshot_diff_selected_analysis_input_preflight_requires_raw_heap": bool((heap_snapshot_diff_selected_analysis_input_preflight.get("future_executor_contract") or {}).get("requires_raw_heap")) if isinstance(heap_snapshot_diff_selected_analysis_input_preflight.get("future_executor_contract"), dict) else False,
                "heap_snapshot_diff_selected_analysis_input_preflight_raw_heap_loaded": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("raw_heap_loaded")),
                "heap_snapshot_diff_selected_analysis_input_preflight_raw_heap_parsed": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("raw_heap_parsed")),
                "heap_snapshot_diff_selected_analysis_input_preflight_heap_diff_computed": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("heap_diff_computed")),
                "heap_snapshot_diff_selected_analysis_input_preflight_retained_size_proven": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("retained_size_proven")),
                "heap_snapshot_diff_selected_analysis_input_preflight_path_to_root_computed": bool(heap_snapshot_diff_selected_analysis_input_preflight.get("path_to_root_computed")),
                "heap_snapshot_diff_selected_analysis_input_preflight_next_action": heap_snapshot_diff_selected_analysis_input_preflight.get("next_action"),
                "heap_snapshot_constructor_growth_drilldown_status": _status(heap_snapshot_constructor_growth_drilldown),
                "heap_snapshot_constructor_growth_drilldown_review_only": bool(heap_snapshot_constructor_growth_drilldown.get("review_only")),
                "heap_snapshot_constructor_growth_drilldown_drilldown_only": bool(heap_snapshot_constructor_growth_drilldown.get("drilldown_only")),
                "heap_snapshot_constructor_growth_drilldown_summary_only": bool(heap_snapshot_constructor_growth_drilldown.get("summary_only")),
                "heap_snapshot_constructor_growth_drilldown_selected_action": heap_snapshot_constructor_growth_drilldown.get("selected_action"),
                "heap_snapshot_constructor_growth_drilldown_candidate_count": ((heap_snapshot_constructor_growth_drilldown.get("constructor_growth_summary") or {}).get("candidate_count") if isinstance(heap_snapshot_constructor_growth_drilldown.get("constructor_growth_summary"), dict) else None),
                "heap_snapshot_constructor_growth_drilldown_top_candidate": (((heap_snapshot_constructor_growth_drilldown.get("constructor_growth_summary") or {}).get("top_candidate") or {}).get("name") if isinstance((heap_snapshot_constructor_growth_drilldown.get("constructor_growth_summary") or {}).get("top_candidate"), dict) else None),
                "heap_snapshot_constructor_growth_drilldown_retained_size_implemented": bool(((heap_snapshot_constructor_growth_drilldown.get("future_analysis_contracts") or {}).get("retained_size_analysis") or {}).get("implemented")) if isinstance(heap_snapshot_constructor_growth_drilldown.get("future_analysis_contracts"), dict) else False,
                "heap_snapshot_constructor_growth_drilldown_path_to_root_implemented": bool(((heap_snapshot_constructor_growth_drilldown.get("future_analysis_contracts") or {}).get("path_to_root_analysis") or {}).get("implemented")) if isinstance(heap_snapshot_constructor_growth_drilldown.get("future_analysis_contracts"), dict) else False,
                "heap_snapshot_constructor_growth_drilldown_raw_heap_loaded": bool(heap_snapshot_constructor_growth_drilldown.get("raw_heap_loaded")),
                "heap_snapshot_constructor_growth_drilldown_raw_heap_parsed": bool(heap_snapshot_constructor_growth_drilldown.get("raw_heap_parsed")),
                "heap_snapshot_constructor_growth_drilldown_heap_diff_computed": bool(heap_snapshot_constructor_growth_drilldown.get("heap_diff_computed")),
                "heap_snapshot_constructor_growth_drilldown_constructor_drilldown_computed": bool(heap_snapshot_constructor_growth_drilldown.get("constructor_drilldown_computed")),
                "heap_snapshot_constructor_growth_drilldown_retained_size_proven": bool(heap_snapshot_constructor_growth_drilldown.get("retained_size_proven")),
                "heap_snapshot_constructor_growth_drilldown_path_to_root_computed": bool(heap_snapshot_constructor_growth_drilldown.get("path_to_root_computed")),
                "heap_snapshot_constructor_growth_drilldown_next_action": heap_snapshot_constructor_growth_drilldown.get("next_action"),
                "heap_snapshot_constructor_growth_drilldown_analysis_status": _status(heap_snapshot_constructor_growth_drilldown_analysis),
                "heap_snapshot_constructor_growth_drilldown_analysis_candidate_count": len(heap_snapshot_constructor_growth_drilldown_analysis.get("constructor_drilldown_rows", [])) if isinstance(heap_snapshot_constructor_growth_drilldown_analysis.get("constructor_drilldown_rows"), list) else 0,
                "heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_computed": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("constructor_drilldown_computed")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "constructor_drilldown_computed")),
                "heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_proven": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("constructor_drilldown_proven")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "constructor_drilldown_proven")),
                "heap_snapshot_constructor_growth_drilldown_analysis_raw_heap_loaded": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_constructor_growth_drilldown_analysis_raw_heap_exported": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_constructor_growth_drilldown_analysis_heap_diff_computed": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_constructor_growth_drilldown_analysis_retained_size_proven": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_constructor_growth_drilldown_analysis_path_to_root_computed": bool(heap_snapshot_constructor_growth_drilldown_analysis.get("path_to_root_computed")) or bool(_nested_get(heap_snapshot_constructor_growth_drilldown_analysis, "side_effect_policy", "path_to_root_computed")),
                "heap_snapshot_constructor_growth_drilldown_analysis_next_action": heap_snapshot_constructor_growth_drilldown_analysis.get("next_action"),
                "heap_snapshot_automatic_followup_plan_status": _status(heap_snapshot_automatic_followup_plan),
                "heap_snapshot_automatic_followup_plan_review_only": bool(heap_snapshot_automatic_followup_plan.get("review_only")),
                "heap_snapshot_automatic_followup_plan_plan_only": bool(heap_snapshot_automatic_followup_plan.get("plan_only")),
                "heap_snapshot_automatic_followup_plan_recommended_action_count": heap_snapshot_automatic_followup_plan.get("recommended_action_count"),
                "heap_snapshot_automatic_followup_plan_top_action": ((heap_snapshot_automatic_followup_plan.get("top_recommended_action") or {}).get("action") if isinstance(heap_snapshot_automatic_followup_plan.get("top_recommended_action"), dict) else None),
                "heap_snapshot_automatic_followup_plan_raw_heap_loaded": bool(heap_snapshot_automatic_followup_plan.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_automatic_followup_plan, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_automatic_followup_plan_heap_diff_computed": bool(heap_snapshot_automatic_followup_plan.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_automatic_followup_plan, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_automatic_followup_plan_retained_size_proven": bool(heap_snapshot_automatic_followup_plan.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_automatic_followup_plan, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_automatic_followup_plan_path_to_root_proven": bool(heap_snapshot_automatic_followup_plan.get("path_to_root_proven")) or bool(_nested_get(heap_snapshot_automatic_followup_plan, "side_effect_policy", "path_to_root_proven")),
                "heap_snapshot_automatic_followup_plan_automatic_execution_allowed": bool(heap_snapshot_automatic_followup_plan.get("automatic_execution_allowed")) or bool(_nested_get(heap_snapshot_automatic_followup_plan, "side_effect_policy", "automatic_execution_allowed")),
                "heap_snapshot_automatic_followup_plan_next_action": heap_snapshot_automatic_followup_plan.get("next_action"),
                "heap_snapshot_retained_size_proof_plan_status": _status(heap_snapshot_retained_size_proof_plan),
                "heap_snapshot_retained_size_proof_plan_review_only": bool(heap_snapshot_retained_size_proof_plan.get("review_only")),
                "heap_snapshot_retained_size_proof_plan_plan_only": bool(heap_snapshot_retained_size_proof_plan.get("plan_only")),
                "heap_snapshot_retained_size_proof_plan_proof_plan_only": bool(heap_snapshot_retained_size_proof_plan.get("proof_plan_only")),
                "heap_snapshot_retained_size_proof_plan_candidate_count": heap_snapshot_retained_size_proof_plan.get("candidate_count"),
                "heap_snapshot_retained_size_proof_plan_requires_raw_heap": bool(((heap_snapshot_retained_size_proof_plan.get("proof_requirements") or {}).get("requires_raw_heap"))) if isinstance(heap_snapshot_retained_size_proof_plan.get("proof_requirements"), dict) else False,
                "heap_snapshot_retained_size_proof_plan_future_executor_implemented": bool(((heap_snapshot_retained_size_proof_plan.get("future_executor_contract") or {}).get("implemented"))) if isinstance(heap_snapshot_retained_size_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_retained_size_proof_plan_ready_to_execute_now": bool(((heap_snapshot_retained_size_proof_plan.get("future_executor_contract") or {}).get("ready_to_execute_now"))) if isinstance(heap_snapshot_retained_size_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_retained_size_proof_plan_raw_heap_loaded": bool(heap_snapshot_retained_size_proof_plan.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_retained_size_proof_plan, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_retained_size_proof_plan_heap_diff_computed": bool(heap_snapshot_retained_size_proof_plan.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_retained_size_proof_plan, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_retained_size_proof_plan_retained_size_proven": bool(heap_snapshot_retained_size_proof_plan.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_retained_size_proof_plan, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_retained_size_proof_plan_automatic_execution_allowed": bool(heap_snapshot_retained_size_proof_plan.get("automatic_execution_allowed")) or bool(_nested_get(heap_snapshot_retained_size_proof_plan, "side_effect_policy", "automatic_execution_allowed")),
                "heap_snapshot_retained_size_proof_plan_next_action": heap_snapshot_retained_size_proof_plan.get("next_action"),
                "heap_snapshot_path_to_root_proof_plan_status": _status(heap_snapshot_path_to_root_proof_plan),
                "heap_snapshot_path_to_root_proof_plan_review_only": bool(heap_snapshot_path_to_root_proof_plan.get("review_only")),
                "heap_snapshot_path_to_root_proof_plan_plan_only": bool(heap_snapshot_path_to_root_proof_plan.get("plan_only")),
                "heap_snapshot_path_to_root_proof_plan_proof_plan_only": bool(heap_snapshot_path_to_root_proof_plan.get("proof_plan_only")),
                "heap_snapshot_path_to_root_proof_plan_candidate_count": heap_snapshot_path_to_root_proof_plan.get("candidate_count"),
                "heap_snapshot_path_to_root_proof_plan_requires_raw_heap": bool(((heap_snapshot_path_to_root_proof_plan.get("proof_requirements") or {}).get("requires_raw_heap"))) if isinstance(heap_snapshot_path_to_root_proof_plan.get("proof_requirements"), dict) else False,
                "heap_snapshot_path_to_root_proof_plan_future_executor_implemented": bool(((heap_snapshot_path_to_root_proof_plan.get("future_executor_contract") or {}).get("implemented"))) if isinstance(heap_snapshot_path_to_root_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_path_to_root_proof_plan_ready_to_execute_now": bool(((heap_snapshot_path_to_root_proof_plan.get("future_executor_contract") or {}).get("ready_to_execute_now"))) if isinstance(heap_snapshot_path_to_root_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_path_to_root_proof_plan_raw_heap_loaded": bool(heap_snapshot_path_to_root_proof_plan.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_path_to_root_proof_plan, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_path_to_root_proof_plan_heap_diff_computed": bool(heap_snapshot_path_to_root_proof_plan.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_path_to_root_proof_plan, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_path_to_root_proof_plan_path_to_root_proven": bool(heap_snapshot_path_to_root_proof_plan.get("path_to_root_proven")) or bool(_nested_get(heap_snapshot_path_to_root_proof_plan, "side_effect_policy", "path_to_root_proven")),
                "heap_snapshot_path_to_root_proof_plan_automatic_execution_allowed": bool(heap_snapshot_path_to_root_proof_plan.get("automatic_execution_allowed")) or bool(_nested_get(heap_snapshot_path_to_root_proof_plan, "side_effect_policy", "automatic_execution_allowed")),
                "heap_snapshot_path_to_root_proof_plan_next_action": heap_snapshot_path_to_root_proof_plan.get("next_action"),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_status": _status(heap_snapshot_raw_heap_constructor_drilldown_proof_plan),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_review_only": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("review_only")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_plan_only": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("plan_only")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_proof_plan_only": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("proof_plan_only")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_candidate_count": heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("candidate_count"),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_raw_heap": bool(((heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("proof_requirements") or {}).get("requires_raw_heap"))) if isinstance(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("proof_requirements"), dict) else False,
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_constructor_reachability_graph": bool(((heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("proof_requirements") or {}).get("requires_constructor_reachability_graph"))) if isinstance(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("proof_requirements"), dict) else False,
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_future_executor_implemented": bool(((heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("future_executor_contract") or {}).get("implemented"))) if isinstance(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_to_execute_now": bool(((heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("future_executor_contract") or {}).get("ready_to_execute_now"))) if isinstance(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("future_executor_contract"), dict) else False,
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_raw_heap_loaded": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_raw_heap_constructor_drilldown_proof_plan, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_heap_diff_computed": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("heap_diff_computed")) or bool(_nested_get(heap_snapshot_raw_heap_constructor_drilldown_proof_plan, "side_effect_policy", "heap_diff_computed")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_constructor_drilldown_proven": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("constructor_drilldown_proven")) or bool(_nested_get(heap_snapshot_raw_heap_constructor_drilldown_proof_plan, "side_effect_policy", "constructor_drilldown_proven")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_automatic_execution_allowed": bool(heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("automatic_execution_allowed")) or bool(_nested_get(heap_snapshot_raw_heap_constructor_drilldown_proof_plan, "side_effect_policy", "automatic_execution_allowed")),
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_next_action": heap_snapshot_raw_heap_constructor_drilldown_proof_plan.get("next_action"),
                "heap_snapshot_retained_path_preflight_status": _status(heap_snapshot_retained_path_preflight),
                "heap_snapshot_retained_path_preflight_review_only": bool(heap_snapshot_retained_path_preflight.get("review_only")),
                "heap_snapshot_retained_path_preflight_preflight_only": bool(heap_snapshot_retained_path_preflight.get("preflight_only")),
                "heap_snapshot_retained_path_preflight_handoff_only": bool(heap_snapshot_retained_path_preflight.get("handoff_only")),
                "heap_snapshot_retained_path_preflight_requested_analysis": heap_snapshot_retained_path_preflight.get("requested_analysis"),
                "heap_snapshot_retained_path_preflight_candidate_count": heap_snapshot_retained_path_preflight.get("candidate_count"),
                "heap_snapshot_retained_path_preflight_top_candidate": ((heap_snapshot_retained_path_preflight.get("candidate_inputs") or [{}])[0].get("name") if isinstance(heap_snapshot_retained_path_preflight.get("candidate_inputs"), list) and heap_snapshot_retained_path_preflight.get("candidate_inputs") else None),
                "heap_snapshot_retained_path_preflight_requires_raw_heap": bool(((heap_snapshot_retained_path_preflight.get("raw_heap_requirements") or {}).get("requires_raw_heap"))) if isinstance(heap_snapshot_retained_path_preflight.get("raw_heap_requirements"), dict) else False,
                "heap_snapshot_retained_path_preflight_raw_heap_loaded": bool(heap_snapshot_retained_path_preflight.get("raw_heap_loaded")),
                "heap_snapshot_retained_path_preflight_raw_heap_parsed": bool(heap_snapshot_retained_path_preflight.get("raw_heap_parsed")),
                "heap_snapshot_retained_path_preflight_heap_diff_computed": bool(heap_snapshot_retained_path_preflight.get("heap_diff_computed")),
                "heap_snapshot_retained_path_preflight_retained_size_proven": bool(heap_snapshot_retained_path_preflight.get("retained_size_proven")),
                "heap_snapshot_retained_path_preflight_path_to_root_computed": bool(heap_snapshot_retained_path_preflight.get("path_to_root_computed")),
                "heap_snapshot_retained_path_preflight_next_action": heap_snapshot_retained_path_preflight.get("next_action"),
                "heap_snapshot_retained_size_input_review_status": _status(heap_snapshot_retained_size_input_review),
                "heap_snapshot_retained_size_input_review_review_only": bool(heap_snapshot_retained_size_input_review.get("review_only")),
                "heap_snapshot_retained_size_input_review_input_review_only": bool(heap_snapshot_retained_size_input_review.get("input_review_only")),
                "heap_snapshot_retained_size_input_review_approval_gate_only": bool(heap_snapshot_retained_size_input_review.get("approval_gate_only")),
                "heap_snapshot_retained_size_input_review_candidate_count": heap_snapshot_retained_size_input_review.get("candidate_count"),
                "heap_snapshot_retained_size_input_review_top_candidate": ((heap_snapshot_retained_size_input_review.get("candidate_inputs") or [{}])[0].get("name") if isinstance(heap_snapshot_retained_size_input_review.get("candidate_inputs"), list) and heap_snapshot_retained_size_input_review.get("candidate_inputs") else None),
                "heap_snapshot_retained_size_input_review_requires_raw_heap": bool(((heap_snapshot_retained_size_input_review.get("raw_heap_requirements") or {}).get("requires_raw_heap"))) if isinstance(heap_snapshot_retained_size_input_review.get("raw_heap_requirements"), dict) else False,
                "heap_snapshot_retained_size_input_review_executor_implemented": bool(((heap_snapshot_retained_size_input_review.get("executor_input_contract") or {}).get("implemented"))) if isinstance(heap_snapshot_retained_size_input_review.get("executor_input_contract"), dict) else False,
                "heap_snapshot_retained_size_input_review_approval_required": bool(((heap_snapshot_retained_size_input_review.get("approval_gate") or {}).get("approval_required"))) if isinstance(heap_snapshot_retained_size_input_review.get("approval_gate"), dict) else False,
                "heap_snapshot_retained_size_input_review_ready_to_execute_now": bool(((heap_snapshot_retained_size_input_review.get("approval_gate") or {}).get("ready_to_execute_now"))) if isinstance(heap_snapshot_retained_size_input_review.get("approval_gate"), dict) else False,
                "heap_snapshot_retained_size_input_review_raw_heap_loaded": bool(heap_snapshot_retained_size_input_review.get("raw_heap_loaded")),
                "heap_snapshot_retained_size_input_review_raw_heap_parsed": bool(heap_snapshot_retained_size_input_review.get("raw_heap_parsed")),
                "heap_snapshot_retained_size_input_review_heap_diff_computed": bool(heap_snapshot_retained_size_input_review.get("heap_diff_computed")),
                "heap_snapshot_retained_size_input_review_retained_size_proven": bool(heap_snapshot_retained_size_input_review.get("retained_size_proven")),
                "heap_snapshot_retained_size_input_review_path_to_root_computed": bool(heap_snapshot_retained_size_input_review.get("path_to_root_computed")),
                "heap_snapshot_retained_size_input_review_next_action": heap_snapshot_retained_size_input_review.get("next_action"),
                "heap_snapshot_retained_size_approval_plan_status": _status(heap_snapshot_retained_size_approval_plan),
                "heap_snapshot_retained_size_approval_plan_review_only": bool(heap_snapshot_retained_size_approval_plan.get("review_only")),
                "heap_snapshot_retained_size_approval_plan_approval_plan_only": bool(heap_snapshot_retained_size_approval_plan.get("approval_plan_only")),
                "heap_snapshot_retained_size_approval_plan_transaction_plan_only": bool(heap_snapshot_retained_size_approval_plan.get("transaction_plan_only")),
                "heap_snapshot_retained_size_approval_plan_candidate_count": heap_snapshot_retained_size_approval_plan.get("candidate_count"),
                "heap_snapshot_retained_size_approval_plan_top_candidate": ((heap_snapshot_retained_size_approval_plan.get("candidate_inputs") or [{}])[0].get("name") if isinstance(heap_snapshot_retained_size_approval_plan.get("candidate_inputs"), list) and heap_snapshot_retained_size_approval_plan.get("candidate_inputs") else None),
                "heap_snapshot_retained_size_approval_plan_executor_implemented": bool(((heap_snapshot_retained_size_approval_plan.get("executor_input_contract") or {}).get("implemented"))) if isinstance(heap_snapshot_retained_size_approval_plan.get("executor_input_contract"), dict) else False,
                "heap_snapshot_retained_size_approval_plan_approval_recorded": bool(heap_snapshot_retained_size_approval_plan.get("approval_recorded")),
                "heap_snapshot_retained_size_approval_plan_transaction_started": bool(heap_snapshot_retained_size_approval_plan.get("transaction_started")),
                "heap_snapshot_retained_size_approval_plan_journal_written_now": bool(heap_snapshot_retained_size_approval_plan.get("journal_written_now")),
                "heap_snapshot_retained_size_approval_plan_executor_invoked": bool(heap_snapshot_retained_size_approval_plan.get("executor_invoked")),
                "heap_snapshot_retained_size_approval_plan_raw_heap_loaded": bool(heap_snapshot_retained_size_approval_plan.get("raw_heap_loaded")),
                "heap_snapshot_retained_size_approval_plan_raw_heap_parsed": bool(heap_snapshot_retained_size_approval_plan.get("raw_heap_parsed")),
                "heap_snapshot_retained_size_approval_plan_heap_diff_computed": bool(heap_snapshot_retained_size_approval_plan.get("heap_diff_computed")),
                "heap_snapshot_retained_size_approval_plan_retained_size_proven": bool(heap_snapshot_retained_size_approval_plan.get("retained_size_proven")),
                "heap_snapshot_retained_size_approval_plan_path_to_root_computed": bool(heap_snapshot_retained_size_approval_plan.get("path_to_root_computed")),
                "heap_snapshot_retained_size_approval_plan_next_action": heap_snapshot_retained_size_approval_plan.get("next_action"),
                "heap_snapshot_retained_size_approval_record_status": _status(heap_snapshot_retained_size_approval_record),
                "heap_snapshot_retained_size_approval_record_approval_recorded": bool(heap_snapshot_retained_size_approval_record.get("approval_recorded")),
                "heap_snapshot_retained_size_approval_record_approved_for_execution": bool(heap_snapshot_retained_size_approval_record.get("approved_for_execution")),
                "heap_snapshot_retained_size_approval_record_candidate_digest": heap_snapshot_retained_size_approval_record.get("candidate_digest"),
                "heap_snapshot_retained_size_approval_record_transaction_plan_id": heap_snapshot_retained_size_approval_record.get("transaction_plan_id"),
                "heap_snapshot_retained_size_approval_record_transaction_started": bool(heap_snapshot_retained_size_approval_record.get("transaction_started") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "transaction_started")),
                "heap_snapshot_retained_size_approval_record_journal_written": bool(heap_snapshot_retained_size_approval_record.get("journal_written") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "journal_written")),
                "heap_snapshot_retained_size_approval_record_bounded_executor_gate_written": bool(heap_snapshot_retained_size_approval_record.get("bounded_executor_gate_written") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "bounded_executor_gate_written")),
                "heap_snapshot_retained_size_approval_record_executor_invoked": bool(heap_snapshot_retained_size_approval_record.get("executor_invoked") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "executor_invoked")),
                "heap_snapshot_retained_size_approval_record_raw_heap_loaded": bool(heap_snapshot_retained_size_approval_record.get("raw_heap_loaded") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "raw_heap_loaded")),
                "heap_snapshot_retained_size_approval_record_raw_heap_parsed": bool(heap_snapshot_retained_size_approval_record.get("raw_heap_parsed") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "raw_heap_parsed")),
                "heap_snapshot_retained_size_approval_record_raw_heap_exported": bool(heap_snapshot_retained_size_approval_record.get("raw_heap_exported") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "raw_heap_exported")),
                "heap_snapshot_retained_size_approval_record_heap_diff_computed": bool(heap_snapshot_retained_size_approval_record.get("heap_diff_computed") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "heap_diff_computed")),
                "heap_snapshot_retained_size_approval_record_retained_size_proven": bool(heap_snapshot_retained_size_approval_record.get("retained_size_proven") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "retained_size_proven")),
                "heap_snapshot_retained_size_approval_record_path_to_root_computed": bool(heap_snapshot_retained_size_approval_record.get("path_to_root_computed") or _nested_get(heap_snapshot_retained_size_approval_record, "executor_input_gates", "path_to_root_computed")),
                "heap_snapshot_retained_size_approval_record_next_action": heap_snapshot_retained_size_approval_record.get("next_action"),
                "heap_snapshot_retained_size_transaction_preflight_status": _status(heap_snapshot_retained_size_transaction_preflight),
                "heap_snapshot_retained_size_transaction_preflight_approval_recorded": bool(_nested_get(heap_snapshot_retained_size_transaction_preflight, "approval_summary", "approval_recorded")),
                "heap_snapshot_retained_size_transaction_preflight_approved_for_execution": bool(_nested_get(heap_snapshot_retained_size_transaction_preflight, "approval_summary", "approved_for_execution")),
                "heap_snapshot_retained_size_transaction_preflight_approval_plan_id": _nested_get(heap_snapshot_retained_size_transaction_preflight, "approval_summary", "approval_plan_id"),
                "heap_snapshot_retained_size_transaction_preflight_transaction_plan_id": _nested_get(heap_snapshot_retained_size_transaction_preflight, "transaction_summary", "transaction_plan_id"),
                "heap_snapshot_retained_size_transaction_preflight_candidate_digest": _nested_get(heap_snapshot_retained_size_transaction_preflight, "candidate_summary", "candidate_digest"),
                "heap_snapshot_retained_size_transaction_preflight_ready_to_write_journal": bool(_nested_get(heap_snapshot_retained_size_transaction_preflight, "journal_writer_contract", "ready_for_journal_review")),
                "heap_snapshot_retained_size_transaction_preflight_transaction_started": bool(heap_snapshot_retained_size_transaction_preflight.get("transaction_started") or _nested_get(heap_snapshot_retained_size_transaction_preflight, "transaction_summary", "transaction_started")),
                "heap_snapshot_retained_size_transaction_preflight_journal_written": bool(heap_snapshot_retained_size_transaction_preflight.get("journal_written") or _nested_get(heap_snapshot_retained_size_transaction_preflight, "transaction_summary", "journal_written")),
                "heap_snapshot_retained_size_transaction_preflight_bounded_executor_gate_written": bool(heap_snapshot_retained_size_transaction_preflight.get("bounded_executor_gate_written") or _nested_get(heap_snapshot_retained_size_transaction_preflight, "transaction_summary", "bounded_executor_gate_written")),
                "heap_snapshot_retained_size_transaction_preflight_executor_invoked": bool(heap_snapshot_retained_size_transaction_preflight.get("executor_invoked") or _nested_get(heap_snapshot_retained_size_transaction_preflight, "transaction_summary", "executor_invoked")),
                "heap_snapshot_retained_size_transaction_preflight_raw_heap_loaded": bool(heap_snapshot_retained_size_transaction_preflight.get("raw_heap_loaded")),
                "heap_snapshot_retained_size_transaction_preflight_raw_heap_parsed": bool(heap_snapshot_retained_size_transaction_preflight.get("raw_heap_parsed")),
                "heap_snapshot_retained_size_transaction_preflight_heap_diff_computed": bool(heap_snapshot_retained_size_transaction_preflight.get("heap_diff_computed")),
                "heap_snapshot_retained_size_transaction_preflight_retained_size_proven": bool(heap_snapshot_retained_size_transaction_preflight.get("retained_size_proven")),
                "heap_snapshot_retained_size_transaction_preflight_path_to_root_computed": bool(heap_snapshot_retained_size_transaction_preflight.get("path_to_root_computed")),
                "heap_snapshot_retained_size_transaction_preflight_next_action": heap_snapshot_retained_size_transaction_preflight.get("next_action"),
                "heap_snapshot_retained_size_transaction_journal_status": _status(heap_snapshot_retained_size_transaction_journal),
                "heap_snapshot_retained_size_transaction_journal_written": bool(heap_snapshot_retained_size_transaction_journal.get("journal_written")),
                "heap_snapshot_retained_size_transaction_journal_started": bool(heap_snapshot_retained_size_transaction_journal.get("transaction_started")),
                "heap_snapshot_retained_size_transaction_journal_transaction_plan_id": heap_snapshot_retained_size_transaction_journal.get("transaction_plan_id"),
                "heap_snapshot_retained_size_transaction_journal_candidate_digest": heap_snapshot_retained_size_transaction_journal.get("candidate_digest"),
                "heap_snapshot_retained_size_transaction_journal_bounded_gate_written": bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "executor_input_gates", "bounded_executor_gate_written")),
                "heap_snapshot_retained_size_transaction_journal_executor_invoked": bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "executor_input_gates", "executor_invoked")) or bool(heap_snapshot_retained_size_transaction_journal.get("executor_invoked")),
                "heap_snapshot_retained_size_transaction_journal_raw_heap_loaded": bool(heap_snapshot_retained_size_transaction_journal.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_retained_size_transaction_journal_raw_heap_parsed": bool(heap_snapshot_retained_size_transaction_journal.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_retained_size_transaction_journal_raw_heap_exported": bool(heap_snapshot_retained_size_transaction_journal.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_retained_size_transaction_journal_retained_size_proven": bool(heap_snapshot_retained_size_transaction_journal.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_retained_size_transaction_journal_path_to_root_computed": bool(heap_snapshot_retained_size_transaction_journal.get("path_to_root_computed")) or bool(_nested_get(heap_snapshot_retained_size_transaction_journal, "side_effect_policy", "path_to_root_computed")),
                "heap_snapshot_retained_size_transaction_journal_next_action": heap_snapshot_retained_size_transaction_journal.get("next_action"),
                "heap_snapshot_retained_size_bounded_gate_status": _status(heap_snapshot_retained_size_bounded_gate),
                "heap_snapshot_retained_size_bounded_gate_journal_id": heap_snapshot_retained_size_bounded_gate.get("journal_id"),
                "heap_snapshot_retained_size_bounded_gate_transaction_plan_id": heap_snapshot_retained_size_bounded_gate.get("transaction_plan_id"),
                "heap_snapshot_retained_size_bounded_gate_approval_plan_id": heap_snapshot_retained_size_bounded_gate.get("approval_plan_id"),
                "heap_snapshot_retained_size_bounded_gate_candidate_digest": heap_snapshot_retained_size_bounded_gate.get("candidate_digest"),
                "heap_snapshot_retained_size_bounded_gate_ready_for_review": bool(heap_snapshot_retained_size_bounded_gate.get("bounded_executor_gate_ready_for_review")),
                "heap_snapshot_retained_size_bounded_gate_ready_to_execute_now": bool(heap_snapshot_retained_size_bounded_gate.get("ready_to_execute_now")),
                "heap_snapshot_retained_size_bounded_gate_future_executor_implemented": bool((heap_snapshot_retained_size_bounded_gate.get("future_executor_contract") or {}).get("implemented")) if isinstance(heap_snapshot_retained_size_bounded_gate.get("future_executor_contract"), dict) else False,
                "heap_snapshot_retained_size_bounded_gate_executor_invoked": bool(heap_snapshot_retained_size_bounded_gate.get("executor_invoked")),
                "heap_snapshot_retained_size_bounded_gate_raw_heap_loaded": bool(heap_snapshot_retained_size_bounded_gate.get("raw_heap_loaded")),
                "heap_snapshot_retained_size_bounded_gate_raw_heap_parsed": bool(heap_snapshot_retained_size_bounded_gate.get("raw_heap_parsed")),
                "heap_snapshot_retained_size_bounded_gate_raw_heap_exported": bool(heap_snapshot_retained_size_bounded_gate.get("raw_heap_exported")),
                "heap_snapshot_retained_size_bounded_gate_retained_size_proven": bool(heap_snapshot_retained_size_bounded_gate.get("retained_size_proven")),
                "heap_snapshot_retained_size_bounded_gate_path_to_root_computed": bool(heap_snapshot_retained_size_bounded_gate.get("path_to_root_computed")),
                "heap_snapshot_retained_size_bounded_gate_next_action": heap_snapshot_retained_size_bounded_gate.get("next_action"),
                "heap_snapshot_retained_size_analysis_status": _status(heap_snapshot_retained_size_analysis),
                "heap_snapshot_retained_size_analysis_candidate_count": len(heap_snapshot_retained_size_analysis.get("candidate_estimates", [])) if isinstance(heap_snapshot_retained_size_analysis.get("candidate_estimates"), list) else 0,
                "heap_snapshot_retained_size_analysis_raw_heap_loaded": bool(heap_snapshot_retained_size_analysis.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_retained_size_analysis_raw_heap_parsed": bool(heap_snapshot_retained_size_analysis.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_retained_size_analysis_raw_heap_exported": bool(heap_snapshot_retained_size_analysis.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_retained_size_analysis_raw_strings_exported": bool(heap_snapshot_retained_size_analysis.get("raw_strings_exported")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "raw_strings_exported")),
                "heap_snapshot_retained_size_analysis_retained_size_estimated": bool(heap_snapshot_retained_size_analysis.get("retained_size_estimated")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "retained_size_estimated")),
                "heap_snapshot_retained_size_analysis_retained_size_proven": bool(heap_snapshot_retained_size_analysis.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_retained_size_analysis_path_to_root_computed": bool(heap_snapshot_retained_size_analysis.get("path_to_root_computed")) or bool(_nested_get(heap_snapshot_retained_size_analysis, "side_effect_policy", "path_to_root_computed")),
                "heap_snapshot_retained_size_analysis_next_action": heap_snapshot_retained_size_analysis.get("next_action"),
                "heap_snapshot_path_to_root_analysis_status": _status(heap_snapshot_path_to_root_analysis),
                "heap_snapshot_path_to_root_analysis_candidate_count": len(heap_snapshot_path_to_root_analysis.get("candidate_paths", [])) if isinstance(heap_snapshot_path_to_root_analysis.get("candidate_paths"), list) else 0,
                "heap_snapshot_path_to_root_analysis_raw_heap_loaded": bool(heap_snapshot_path_to_root_analysis.get("raw_heap_loaded")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "raw_heap_loaded")),
                "heap_snapshot_path_to_root_analysis_raw_heap_parsed": bool(heap_snapshot_path_to_root_analysis.get("raw_heap_parsed")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "raw_heap_parsed")),
                "heap_snapshot_path_to_root_analysis_raw_heap_exported": bool(heap_snapshot_path_to_root_analysis.get("raw_heap_exported")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "raw_heap_exported")),
                "heap_snapshot_path_to_root_analysis_raw_strings_exported": bool(heap_snapshot_path_to_root_analysis.get("raw_strings_exported")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "raw_strings_exported")),
                "heap_snapshot_path_to_root_analysis_path_to_root_estimated": bool(heap_snapshot_path_to_root_analysis.get("path_to_root_estimated")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "path_to_root_estimated")),
                "heap_snapshot_path_to_root_analysis_path_to_root_proven": bool(heap_snapshot_path_to_root_analysis.get("path_to_root_proven")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "path_to_root_proven")),
                "heap_snapshot_path_to_root_analysis_retained_size_proven": bool(heap_snapshot_path_to_root_analysis.get("retained_size_proven")) or bool(_nested_get(heap_snapshot_path_to_root_analysis, "side_effect_policy", "retained_size_proven")),
                "heap_snapshot_path_to_root_analysis_next_action": heap_snapshot_path_to_root_analysis.get("next_action"),
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


def make_record_source_map_selected_executor_approval_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit Source Map selected-executor approval-record writer.

    The tool records reviewer approval metadata for a ready
    source-map-selected-executor approval/apply plan. It does not apply the
    selected executor, send CDP commands, install source-logpoints or hooks,
    run rebuilds, fetch Source Maps, start browsers, call MCP, or touch mobile
    runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_source_map_selected_executor_approval(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        reviewer: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_approval_record: bool = False,
        expected_action_id: str | None = None,
        expected_consumer: str | None = None,
        expected_gate: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record reviewer approval for a ready Source Map selected executor plan."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_source_map_selected_executor_approval_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            reviewer=reviewer,
            decision=decision,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_approval_record=approve_approval_record,
            expected_action_id=expected_action_id,
            expected_consumer=expected_consumer,
            expected_gate=expected_gate,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_source_map_selected_executor_approval.__name__ = "record_source_map_selected_executor_approval"
    return record_source_map_selected_executor_approval


def record_source_map_selected_executor_approval_payload(
    *,
    approval_plan_json: str | None = None,
    approval_plan_ref: str | None = None,
    reviewer: str | None = None,
    decision: str = "approved",
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_approval_record: bool = False,
    expected_action_id: str | None = None,
    expected_consumer: str | None = None,
    expected_gate: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the Source Map selected-executor approval record payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        approval_plan_json,
        artifact_ref=approval_plan_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_plan_json",
        artifact_field_name="approval_plan_ref",
    )
    approval_plan = _first_object(loaded.get("approval_plan"), loaded)
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "source-map-selected-executor-approval-record.json"
    plan_digest = _stable_json_digest(approval_plan) if approval_plan else None
    checks = _source_map_selected_executor_approval_record_checks(
        approval_plan=approval_plan,
        reviewer=reviewer,
        decision=decision,
        mode=mode,
        write_result=write_result,
        approve_approval_record=approve_approval_record,
        expected_action_id=expected_action_id,
        expected_consumer=expected_consumer,
        expected_gate=expected_gate,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        plan_digest=plan_digest,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_approval_record
    approved_for_apply = written and decision == "approved"
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    selected_action_id = str(approval_plan.get("selected_action_id") or "")
    selected_consumer = str(approval_plan.get("selected_consumer") or "")
    selected_gate = str(approval_plan.get("selected_review_gate") or "")
    approval_requirements = approval_plan.get("approval_requirements") if isinstance(approval_plan.get("approval_requirements"), dict) else {}
    apply_plan = approval_plan.get("apply_plan") if isinstance(approval_plan.get("apply_plan"), dict) else {}
    approval_record_id = _source_map_selected_executor_approval_record_id(
        selected_action_id=selected_action_id,
        selected_consumer=selected_consumer,
        selected_gate=selected_gate,
        decision=decision,
        reviewer=reviewer,
        created_at=created_at,
    )
    payload: dict[str, Any] = {
        "schema_version": SOURCE_MAP_SELECTED_EXECUTOR_APPROVAL_RECORD_VERSION,
        "status": status,
        "approval_recorded": written,
        "approved_for_apply": approved_for_apply,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "approval_record_id": approval_record_id,
        "selected_action_id": selected_action_id or None,
        "selected_consumer": selected_consumer or None,
        "selected_review_gate": selected_gate or None,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "approval_plan_digest_sha256": plan_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "source_approval_plan_summary": {
            "schema_version": approval_plan.get("schema_version"),
            "status": approval_plan.get("status"),
            "approval_plan_ready": _boolish(approval_plan.get("approval_plan_ready")),
            "apply_plan_ready_for_review": _boolish(approval_plan.get("apply_plan_ready_for_review")),
            "approval_recorded": _boolish(approval_plan.get("approval_recorded")),
            "ready_to_apply_now": _boolish(approval_plan.get("ready_to_apply_now")),
            "surface_executor_invoked": _boolish(approval_plan.get("surface_executor_invoked")),
            "next_action": approval_plan.get("next_action"),
        },
        "approval_scope": {
            **(_object_alias(approval_requirements, "approval_scope") if approval_requirements else {}),
            "action_id": selected_action_id or None,
            "consumer": selected_consumer or None,
            "review_gate": selected_gate or None,
        },
        "apply_plan_summary": {
            "schema_version": apply_plan.get("apply_plan_schema_version"),
            "consumer": apply_plan.get("consumer"),
            "future_action": apply_plan.get("future_action"),
            "future_result_artifact": apply_plan.get("future_result_artifact"),
            "requires_approval_record": _boolish(apply_plan.get("requires_approval_record")),
            "mode_required": apply_plan.get("mode_required"),
            "write_result_required": _boolish(apply_plan.get("write_result_required")),
            "ready_to_apply_now": _boolish(apply_plan.get("ready_to_apply_now")),
            "executor_implemented_now": _boolish(apply_plan.get("executor_implemented_now")),
            "surface_executor_invoked": _boolish(apply_plan.get("surface_executor_invoked")),
        },
        "executor_input_gates": {
            "approval_recorded": written,
            "approved_for_apply": approved_for_apply,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "requires_apply_preflight_followup": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _source_map_selected_executor_approval_record_next_action(status=status, decision=decision, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_source_map_selected_executor_approval",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/source-map-selected-executor-approval-record.json",
            "future_path": "/workspace/debugger/source-map-selected-executor-approval-record.json",
            "path": str(result_path),
        },
        "side_effect_policy": _source_map_selected_executor_approval_record_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def make_record_source_map_followthrough_dispatch_approval_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit Source Map follow-through dispatch approval-record writer.

    The tool records reviewer approval for a ready
    source-map-followthrough-dispatch-approval-plan descriptor. It writes only
    the approval record artifact under explicit apply gates; it never starts a
    transaction, writes a dispatch journal, invokes the dispatch target, executes
    debugger / source-logpoint / hook / rebuild surfaces, starts browsers, sends
    CDP commands, calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_source_map_followthrough_dispatch_approval(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        reviewer: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_approval_record: bool = False,
        expected_approval_plan_id: str | None = None,
        expected_consumer: str | None = None,
        expected_dispatch_surface: str | None = None,
        expected_required_artifact: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record reviewer approval for a ready Source Map follow-through dispatch plan."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_source_map_followthrough_dispatch_approval_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            reviewer=reviewer,
            decision=decision,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_approval_record=approve_approval_record,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_consumer=expected_consumer,
            expected_dispatch_surface=expected_dispatch_surface,
            expected_required_artifact=expected_required_artifact,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_source_map_followthrough_dispatch_approval.__name__ = "record_source_map_followthrough_dispatch_approval"
    return record_source_map_followthrough_dispatch_approval


def record_source_map_followthrough_dispatch_approval_payload(
    *,
    approval_plan_json: str | None = None,
    approval_plan_ref: str | None = None,
    reviewer: str | None = None,
    decision: str = "approved",
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_approval_record: bool = False,
    expected_approval_plan_id: str | None = None,
    expected_consumer: str | None = None,
    expected_dispatch_surface: str | None = None,
    expected_required_artifact: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the Source Map follow-through dispatch approval record payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        approval_plan_json,
        artifact_ref=approval_plan_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_plan_json",
        artifact_field_name="approval_plan_ref",
    )
    descriptor = _first_object(loaded.get("descriptor"), loaded)
    approval_plan = descriptor.get("approval_plan") if isinstance(descriptor.get("approval_plan"), dict) else {}
    transaction_plan = descriptor.get("transaction_plan") if isinstance(descriptor.get("transaction_plan"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "source-map-followthrough-dispatch-approval-record.json"
    plan_digest = _stable_json_digest(descriptor) if descriptor else None
    checks = _source_map_followthrough_dispatch_approval_record_checks(
        descriptor=descriptor,
        approval_plan=approval_plan,
        transaction_plan=transaction_plan,
        reviewer=reviewer,
        decision=decision,
        mode=mode,
        write_result=write_result,
        approve_approval_record=approve_approval_record,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_consumer=expected_consumer,
        expected_dispatch_surface=expected_dispatch_surface,
        expected_required_artifact=expected_required_artifact,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        plan_digest=plan_digest,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_approval_record
    approved_for_dispatch = written and decision == "approved"
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    approval_plan_id = str(approval_plan.get("approval_plan_id") or "")
    selected_consumer = str(descriptor.get("selected_consumer") or approval_plan.get("selected_consumer") or "")
    dispatch_surface = str(descriptor.get("dispatch_surface") or approval_plan.get("dispatch_surface") or "")
    required_artifact = str(descriptor.get("planned_required_artifact") or approval_plan.get("required_result_artifact") or "")
    approval_record_id = _source_map_followthrough_dispatch_approval_record_id(
        approval_plan_id=approval_plan_id,
        selected_consumer=selected_consumer,
        dispatch_surface=dispatch_surface,
        decision=decision,
        reviewer=reviewer,
        created_at=created_at,
    )
    payload: dict[str, Any] = {
        "schema_version": SOURCE_MAP_FOLLOWTHROUGH_DISPATCH_APPROVAL_RECORD_VERSION,
        "status": status,
        "approval_recorded": written,
        "approved_for_dispatch": approved_for_dispatch,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "approval_record_id": approval_record_id,
        "approval_plan_id": approval_plan_id or None,
        "transaction_plan_id": transaction_plan.get("transaction_plan_id"),
        "selected_consumer": selected_consumer or None,
        "dispatch_surface": dispatch_surface or None,
        "required_result_artifact": required_artifact or None,
        "next_action_under_review": approval_plan.get("next_action"),
        "review_gate": approval_plan.get("review_gate"),
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "approval_plan_digest_sha256": plan_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "source_approval_plan_summary": {
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "approval_plan_ready_for_review": _boolish(descriptor.get("approval_plan_ready_for_review")),
            "transaction_plan_ready_for_review": _boolish(descriptor.get("transaction_plan_ready_for_review")),
            "ready_to_dispatch_now": _boolish(descriptor.get("ready_to_dispatch_now")),
            "approval_recorded": _boolish(descriptor.get("approval_recorded")),
            "transaction_started": _boolish(descriptor.get("transaction_started")),
            "journal_written": _boolish(descriptor.get("journal_written")),
            "will_invoke_dispatch_target": _boolish(descriptor.get("will_invoke_dispatch_target")),
            "next_action": descriptor.get("next_action"),
        },
        "transaction_plan_summary": {
            "schema_version": transaction_plan.get("schema_version"),
            "transaction_plan_id": transaction_plan.get("transaction_plan_id"),
            "journal_required_before_dispatch": _boolish(transaction_plan.get("journal_required_before_dispatch")),
            "transaction_started": _boolish(transaction_plan.get("transaction_started")),
            "journal_written_now": _boolish(transaction_plan.get("journal_written_now")),
            "ready_to_dispatch_now": _boolish(transaction_plan.get("ready_to_dispatch_now")),
        },
        "dispatch_input_gates": {
            "approval_recorded": written,
            "approved_for_dispatch": approved_for_dispatch,
            "ready_to_dispatch_now": False,
            "transaction_started": False,
            "journal_written": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "requires_transaction_preflight_followup": True,
            "requires_transaction_journal_before_dispatch": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _source_map_followthrough_dispatch_approval_record_next_action(status=status, decision=decision, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_source_map_followthrough_dispatch_approval",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/source-map-followthrough-dispatch-approval-record.json",
            "future_path": "/workspace/debugger/source-map-followthrough-dispatch-approval-record.json",
            "path": str(result_path),
        },
        "side_effect_policy": _source_map_followthrough_dispatch_approval_record_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload



def make_record_heap_snapshot_diff_executor_approval_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit heap snapshot diff executor approval-record writer.

    The tool records reviewer approval for a ready
    heap-snapshot-diff-executor-approval-plan descriptor. It writes only the
    approval record artifact under explicit apply gates; it never starts a
    transaction, writes a journal or bounded gate, invokes a heap diff executor,
    loads / parses / exports raw heap data, starts browsers, sends CDP commands,
    calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_heap_snapshot_diff_executor_approval(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        reviewer: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_heap_snapshot_diff_executor: bool = False,
        expected_approval_scope: str | None = None,
        expected_transaction_id: str | None = None,
        expected_idempotency_key: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        expected_preflight_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record reviewer approval for a future heap snapshot diff executor."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_heap_snapshot_diff_executor_approval_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            reviewer=reviewer,
            decision=decision,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_heap_snapshot_diff_executor=approve_heap_snapshot_diff_executor,
            expected_approval_scope=expected_approval_scope,
            expected_transaction_id=expected_transaction_id,
            expected_idempotency_key=expected_idempotency_key,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            expected_preflight_digest_sha256=expected_preflight_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_heap_snapshot_diff_executor_approval.__name__ = "record_heap_snapshot_diff_executor_approval"
    return record_heap_snapshot_diff_executor_approval


def record_heap_snapshot_diff_executor_approval_payload(
    *,
    approval_plan_json: str | None = None,
    approval_plan_ref: str | None = None,
    reviewer: str | None = None,
    decision: str = "approved",
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_heap_snapshot_diff_executor: bool = False,
    expected_approval_scope: str | None = None,
    expected_transaction_id: str | None = None,
    expected_idempotency_key: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    expected_preflight_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the heap snapshot diff executor approval record payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        approval_plan_json,
        artifact_ref=approval_plan_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_plan_json",
        artifact_field_name="approval_plan_ref",
    )
    descriptor = _first_object(loaded.get("descriptor"), loaded)
    approval_plan = descriptor.get("approval_plan") if isinstance(descriptor.get("approval_plan"), dict) else {}
    transaction_plan = descriptor.get("transaction_plan") if isinstance(descriptor.get("transaction_plan"), dict) else {}
    preflight_summary = descriptor.get("preflight_summary") if isinstance(descriptor.get("preflight_summary"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "heap-snapshot-diff-executor-approval-record.json"
    plan_digest = _stable_json_digest(descriptor) if descriptor else None
    preflight_digest = _stable_json_digest(preflight_summary) if preflight_summary else None
    checks = _heap_snapshot_diff_executor_approval_record_checks(
        descriptor=descriptor,
        approval_plan=approval_plan,
        transaction_plan=transaction_plan,
        reviewer=reviewer,
        decision=decision,
        mode=mode,
        write_result=write_result,
        approve_heap_snapshot_diff_executor=approve_heap_snapshot_diff_executor,
        expected_approval_scope=expected_approval_scope,
        expected_transaction_id=expected_transaction_id,
        expected_idempotency_key=expected_idempotency_key,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        expected_preflight_digest_sha256=expected_preflight_digest_sha256,
        plan_digest=plan_digest,
        preflight_digest=preflight_digest,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_heap_snapshot_diff_executor
    approved_for_execution = written and decision == "approved"
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    approval_scope = str(approval_plan.get("approval_scope") or "heap-snapshot-diff-executor")
    transaction_id = str(transaction_plan.get("transaction_id") or "")
    idempotency_key = str(transaction_plan.get("idempotency_key") or "")
    approval_record_id = _heap_snapshot_diff_executor_approval_record_id(
        approval_scope=approval_scope,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        decision=decision,
        reviewer=reviewer,
        created_at=created_at,
    )
    payload: dict[str, Any] = {
        "schema_version": HEAP_SNAPSHOT_DIFF_EXECUTOR_APPROVAL_RECORD_VERSION,
        "status": status,
        "approval_recorded": written,
        "approved_for_execution": approved_for_execution,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "approval_record_id": approval_record_id,
        "approval_scope": approval_scope,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "approval_plan_digest_sha256": plan_digest,
        "preflight_summary_digest_sha256": preflight_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "expected_preflight_digest_sha256": expected_preflight_digest_sha256,
        "transaction_id": transaction_id or None,
        "idempotency_key": idempotency_key or None,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "complete_heap_traversal_claimed": False,
        "diff_executor_implemented": False,
        "source_approval_plan_summary": {
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "approval_plan_only": _boolish(descriptor.get("approval_plan_only")),
            "transaction_plan_only": _boolish(descriptor.get("transaction_plan_only")),
            "approval_recorded": _boolish(descriptor.get("approval_recorded")),
            "transaction_started": _boolish(descriptor.get("transaction_started")),
            "journal_written_now": _boolish(descriptor.get("journal_written_now")),
            "bounded_executor_gate_written": _boolish(descriptor.get("bounded_executor_gate_written")),
            "executor_invoked": _boolish(descriptor.get("executor_invoked")),
            "future_executor_implemented": _boolish(_nested_get(descriptor, "future_executor_contract", "implemented")),
            "next_action": descriptor.get("next_action"),
        },
        "preflight_summary": {
            "before_digest": preflight_summary.get("before_digest"),
            "after_digest": preflight_summary.get("after_digest"),
            "raw_heap_ingestion_policy": preflight_summary.get("raw_heap_ingestion_policy"),
            "parser_sandbox": preflight_summary.get("parser_sandbox"),
            "redaction_plan": preflight_summary.get("redaction_plan"),
            "max_raw_heap_bytes": preflight_summary.get("max_raw_heap_bytes"),
            "diff_executor_implemented": _boolish(preflight_summary.get("diff_executor_implemented")),
        },
        "approval_plan_summary": {
            "approval_scope": approval_scope,
            "approval_record_artifact": approval_plan.get("approval_record_artifact"),
            "required_approval_flag": approval_plan.get("required_approval_flag"),
            "required_write_flag": approval_plan.get("required_write_flag"),
            "required_mode": approval_plan.get("required_mode"),
            "approval_recorded": _boolish(approval_plan.get("approval_recorded")),
        },
        "transaction_plan_summary": {
            "transaction_id": transaction_id or None,
            "idempotency_key": idempotency_key or None,
            "transaction_journal_artifact": transaction_plan.get("transaction_journal_artifact"),
            "bounded_gate_artifact": transaction_plan.get("bounded_gate_artifact"),
            "result_artifact": transaction_plan.get("result_artifact"),
            "transaction_started": _boolish(transaction_plan.get("transaction_started")),
            "journal_written_now": _boolish(transaction_plan.get("journal_written_now")),
            "bounded_executor_gate_required": _boolish(transaction_plan.get("bounded_executor_gate_required")),
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_recorded": approved_for_execution,
            "approved_for_execution": approved_for_execution,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "requires_ready_approval_plan": True,
            "requires_transaction_preflight_followup": True,
            "requires_transaction_journal": True,
            "requires_bounded_executor_gate": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _heap_snapshot_diff_executor_approval_record_next_action(status=status, decision=decision, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_heap_snapshot_diff_executor_approval",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/heap-snapshot-diff-executor-approval-record.json",
            "future_path": "/workspace/browser/heap-snapshot-diff-executor-approval-record.json",
            "path": str(result_path),
        },
        "side_effect_policy": _heap_snapshot_diff_executor_approval_record_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def make_record_heap_snapshot_retained_size_approval_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit heap snapshot retained-size approval-record writer.

    The tool records reviewer approval for a ready
    heap-snapshot-retained-size-approval-plan descriptor. It writes only the
    approval record artifact under explicit apply gates; it never starts a
    transaction, writes a journal or bounded gate, invokes retained-size /
    path-to-root executors, loads / parses / exports raw heap data, computes
    retained size or path-to-root data, starts browsers, sends CDP commands,
    calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_heap_snapshot_retained_size_approval(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        reviewer: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_heap_snapshot_retained_size: bool = False,
        expected_approval_plan_id: str | None = None,
        expected_transaction_plan_id: str | None = None,
        expected_candidate_digest: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record reviewer approval for a future retained-size executor."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_heap_snapshot_retained_size_approval_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            reviewer=reviewer,
            decision=decision,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_heap_snapshot_retained_size=approve_heap_snapshot_retained_size,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_transaction_plan_id=expected_transaction_plan_id,
            expected_candidate_digest=expected_candidate_digest,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_heap_snapshot_retained_size_approval.__name__ = "record_heap_snapshot_retained_size_approval"
    return record_heap_snapshot_retained_size_approval


def record_heap_snapshot_retained_size_approval_payload(
    *,
    approval_plan_json: str | None = None,
    approval_plan_ref: str | None = None,
    reviewer: str | None = None,
    decision: str = "approved",
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_heap_snapshot_retained_size: bool = False,
    expected_approval_plan_id: str | None = None,
    expected_transaction_plan_id: str | None = None,
    expected_candidate_digest: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the retained-size approval record payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        approval_plan_json,
        artifact_ref=approval_plan_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_plan_json",
        artifact_field_name="approval_plan_ref",
    )
    descriptor = _first_object(loaded.get("descriptor"), loaded)
    approval_plan = descriptor.get("approval_plan") if isinstance(descriptor.get("approval_plan"), dict) else {}
    transaction_plan = descriptor.get("transaction_plan") if isinstance(descriptor.get("transaction_plan"), dict) else {}
    executor_contract = descriptor.get("executor_input_contract") if isinstance(descriptor.get("executor_input_contract"), dict) else {}
    source_review = descriptor.get("source_retained_size_input_review") if isinstance(descriptor.get("source_retained_size_input_review"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "heap-snapshot-retained-size-approval-record.json"
    plan_digest = _stable_json_digest(descriptor) if descriptor else None
    approval_plan_id = str(approval_plan.get("approval_plan_id") or "")
    transaction_plan_id = str(transaction_plan.get("transaction_plan_id") or "")
    candidate_digest = str(descriptor.get("candidate_digest") or "")
    checks = _heap_snapshot_retained_size_approval_record_checks(
        descriptor=descriptor,
        approval_plan=approval_plan,
        transaction_plan=transaction_plan,
        executor_contract=executor_contract,
        reviewer=reviewer,
        decision=decision,
        mode=mode,
        write_result=write_result,
        approve_heap_snapshot_retained_size=approve_heap_snapshot_retained_size,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_transaction_plan_id=expected_transaction_plan_id,
        expected_candidate_digest=expected_candidate_digest,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        plan_digest=plan_digest,
        approval_plan_id=approval_plan_id,
        transaction_plan_id=transaction_plan_id,
        candidate_digest=candidate_digest,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_heap_snapshot_retained_size
    approved_for_execution = written and decision == "approved"
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    approval_record_id = _heap_snapshot_retained_size_approval_record_id(
        approval_plan_id=approval_plan_id,
        transaction_plan_id=transaction_plan_id,
        candidate_digest=candidate_digest,
        decision=decision,
        reviewer=reviewer,
        created_at=created_at,
    )
    payload: dict[str, Any] = {
        "schema_version": HEAP_SNAPSHOT_RETAINED_SIZE_APPROVAL_RECORD_VERSION,
        "status": status,
        "approval_recorded": written,
        "approved_for_execution": approved_for_execution,
        "approved_for_retained_size": approved_for_execution,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "approval_record_id": approval_record_id,
        "approval_plan_id": approval_plan_id or None,
        "transaction_plan_id": transaction_plan_id or None,
        "candidate_digest": candidate_digest or None,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "approval_plan_digest_sha256": plan_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "transaction_started": False,
        "journal_written": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "complete_heap_traversal_claimed": False,
        "retained_size_executor_implemented": False,
        "source_approval_plan_summary": {
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "review_only": _boolish(descriptor.get("review_only")),
            "approval_plan_only": _boolish(descriptor.get("approval_plan_only")),
            "transaction_plan_only": _boolish(descriptor.get("transaction_plan_only")),
            "retained_size_only": _boolish(descriptor.get("retained_size_only")),
            "candidate_count": descriptor.get("candidate_count"),
            "candidate_digest": candidate_digest or None,
            "approval_recorded": _boolish(descriptor.get("approval_recorded")),
            "transaction_started": _boolish(descriptor.get("transaction_started")),
            "journal_written_now": _boolish(descriptor.get("journal_written_now")),
            "bounded_executor_gate_written": _boolish(descriptor.get("bounded_executor_gate_written")),
            "executor_invoked": _boolish(descriptor.get("executor_invoked")),
            "executor_implemented": _boolish(executor_contract.get("implemented")),
            "ready_to_execute_now": _boolish(executor_contract.get("ready_to_execute_now")),
            "next_action": descriptor.get("next_action"),
        },
        "source_retained_size_input_review_summary": {
            "schema_version": source_review.get("schema_version"),
            "status": source_review.get("status"),
            "candidate_count": source_review.get("candidate_count"),
            "approval_required": _boolish(source_review.get("approval_required") or _nested_get(source_review, "approval_gate", "approval_required")),
            "ready_to_execute_now": _boolish(source_review.get("ready_to_execute_now") or _nested_get(source_review, "approval_gate", "ready_to_execute_now")),
        },
        "approval_plan_summary": {
            "approval_plan_id": approval_plan_id or None,
            "approval_required": _boolish(approval_plan.get("approval_required")),
            "approval_record_writer": approval_plan.get("approval_record_writer"),
            "approval_record_artifact": approval_plan.get("approval_record_artifact"),
            "approval_recorded": _boolish(approval_plan.get("approval_recorded")),
            "requires_reviewer": _boolish(approval_plan.get("requires_reviewer")),
            "requires_candidate_digest_match": _boolish(approval_plan.get("requires_candidate_digest_match")),
            "would_write_now": _boolish(approval_plan.get("would_write_now")),
        },
        "transaction_plan_summary": {
            "transaction_plan_id": transaction_plan_id or None,
            "transaction_journal_writer": transaction_plan.get("transaction_journal_writer"),
            "transaction_journal_artifact": transaction_plan.get("transaction_journal_artifact"),
            "bounded_gate_artifact": transaction_plan.get("bounded_gate_artifact"),
            "result_artifact": transaction_plan.get("result_artifact"),
            "transaction_started": _boolish(transaction_plan.get("transaction_started")),
            "journal_written": _boolish(transaction_plan.get("journal_written")),
            "would_start_transaction_now": _boolish(transaction_plan.get("would_start_transaction_now")),
            "would_write_journal_now": _boolish(transaction_plan.get("would_write_journal_now")),
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_recorded": approved_for_execution,
            "approved_for_execution": approved_for_execution,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_executor_implemented": False,
            "requires_ready_approval_plan": True,
            "requires_transaction_preflight_followup": True,
            "requires_transaction_journal": True,
            "requires_bounded_executor_gate": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _heap_snapshot_retained_size_approval_record_next_action(status=status, decision=decision, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_heap_snapshot_retained_size_approval",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/heap-snapshot-retained-size-approval-record.json",
            "future_path": "/workspace/browser/heap-snapshot-retained-size-approval-record.json",
            "path": str(result_path),
        },
        "side_effect_policy": _heap_snapshot_retained_size_approval_record_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def make_record_heap_snapshot_retained_size_transaction_journal_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit retained-size transaction journal writer.

    The writer consumes a ready heap-snapshot-retained-size-transaction-preflight
    descriptor and writes only the retained-size transaction journal audit artifact
    under explicit apply gates. It never writes a bounded gate, invokes retained-size
    or path-to-root executors, loads / parses / exports raw heap data, computes
    retained size or path-to-root, starts browsers, sends CDP, calls MCP, or touches
    mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_heap_snapshot_retained_size_transaction_journal(
        transaction_preflight_json: str | None = None,
        transaction_preflight_ref: str | None = None,
        reviewer: str | None = None,
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_transaction_journal: bool = False,
        expected_approval_plan_id: str | None = None,
        expected_transaction_plan_id: str | None = None,
        expected_candidate_digest: str | None = None,
        expected_transaction_preflight_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Write a reviewed retained-size transaction journal."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_heap_snapshot_retained_size_transaction_journal_payload(
            transaction_preflight_json=transaction_preflight_json,
            transaction_preflight_ref=transaction_preflight_ref,
            reviewer=reviewer,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_transaction_journal=approve_transaction_journal,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_transaction_plan_id=expected_transaction_plan_id,
            expected_candidate_digest=expected_candidate_digest,
            expected_transaction_preflight_digest_sha256=expected_transaction_preflight_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_heap_snapshot_retained_size_transaction_journal.__name__ = "record_heap_snapshot_retained_size_transaction_journal"
    return record_heap_snapshot_retained_size_transaction_journal


def record_heap_snapshot_retained_size_transaction_journal_payload(
    *,
    transaction_preflight_json: str | None = None,
    transaction_preflight_ref: str | None = None,
    reviewer: str | None = None,
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_transaction_journal: bool = False,
    expected_approval_plan_id: str | None = None,
    expected_transaction_plan_id: str | None = None,
    expected_candidate_digest: str | None = None,
    expected_transaction_preflight_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the retained-size transaction journal payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        transaction_preflight_json,
        artifact_ref=transaction_preflight_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="transaction_preflight_json",
        artifact_field_name="transaction_preflight_ref",
    )
    preflight = _first_object(loaded.get("descriptor"), loaded.get("transaction_preflight_descriptor"), loaded)
    approval_summary = preflight.get("approval_summary") if isinstance(preflight.get("approval_summary"), dict) else {}
    transaction_summary = preflight.get("transaction_summary") if isinstance(preflight.get("transaction_summary"), dict) else {}
    candidate_summary = preflight.get("candidate_summary") if isinstance(preflight.get("candidate_summary"), dict) else {}
    journal_contract = preflight.get("journal_writer_contract") if isinstance(preflight.get("journal_writer_contract"), dict) else {}
    safety_gates = preflight.get("safety_gates") if isinstance(preflight.get("safety_gates"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "heap-snapshot-retained-size-executor-journal.json"
    preflight_digest = _stable_json_digest(preflight) if preflight else None
    transaction_preflight_id = _heap_snapshot_retained_size_transaction_preflight_id(preflight_digest or "") if preflight else ""
    approval_plan_id = str(approval_summary.get("approval_plan_id") or "")
    transaction_plan_id = str(transaction_summary.get("transaction_plan_id") or "")
    candidate_digest = str(candidate_summary.get("candidate_digest") or "")
    checks = _heap_snapshot_retained_size_transaction_journal_checks(
        preflight=preflight,
        approval_summary=approval_summary,
        transaction_summary=transaction_summary,
        candidate_summary=candidate_summary,
        journal_contract=journal_contract,
        safety_gates=safety_gates,
        reviewer=reviewer,
        mode=mode,
        write_result=write_result,
        approve_transaction_journal=approve_transaction_journal,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_transaction_plan_id=expected_transaction_plan_id,
        expected_candidate_digest=expected_candidate_digest,
        expected_transaction_preflight_digest_sha256=expected_transaction_preflight_digest_sha256,
        preflight_digest=preflight_digest,
        transaction_preflight_id=transaction_preflight_id,
        approval_plan_id=approval_plan_id,
        transaction_plan_id=transaction_plan_id,
        candidate_digest=candidate_digest,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_transaction_journal
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    journal_id = _heap_snapshot_retained_size_transaction_journal_id(
        transaction_preflight_id=transaction_preflight_id,
        transaction_plan_id=transaction_plan_id,
        candidate_digest=candidate_digest,
        reviewer=reviewer,
        created_at=created_at,
    )
    journal_entries = [
        {
            "entry_index": 0,
            "entry_kind": "transaction_started",
            "transaction_preflight_id": transaction_preflight_id or None,
            "transaction_plan_id": transaction_plan_id or None,
            "candidate_digest": candidate_digest or None,
            "reviewer": reviewer,
            "created_at": created_at,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
        },
        {
            "entry_index": 1,
            "entry_kind": "retained_size_journal_gate_recorded",
            "approval_plan_id": approval_plan_id or None,
            "requires_bounded_executor_gate": True,
            "requires_raw_heap": True,
            "executed_now": False,
        },
    ]
    payload: dict[str, Any] = {
        "schema_version": HEAP_SNAPSHOT_RETAINED_SIZE_TRANSACTION_JOURNAL_VERSION,
        "status": status,
        "journal_written": written,
        "transaction_started": written,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "journal_id": journal_id,
        "transaction_preflight_id": transaction_preflight_id or None,
        "transaction_plan_id": transaction_plan_id or None,
        "approval_plan_id": approval_plan_id or None,
        "candidate_digest": candidate_digest or None,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "transaction_preflight_digest_sha256": preflight_digest,
        "expected_transaction_preflight_digest_sha256": expected_transaction_preflight_digest_sha256,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "complete_heap_traversal_claimed": False,
        "retained_size_executor_implemented": False,
        "source_transaction_preflight_summary": {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "transaction_preflight_only": _boolish(preflight.get("transaction_preflight_only")),
            "retained_size_only": _boolish(preflight.get("retained_size_only")),
            "approval_recorded": _boolish(approval_summary.get("approval_recorded")),
            "approved_for_execution": _boolish(approval_summary.get("approved_for_execution")),
            "ready_to_write_journal": _boolish(safety_gates.get("ready_to_write_journal")) or _boolish(journal_contract.get("ready_for_journal_review")),
            "ready_to_execute_now": _boolish(safety_gates.get("ready_to_execute_now")),
            "transaction_started": _boolish(preflight.get("transaction_started")) or _boolish(transaction_summary.get("transaction_started")),
            "journal_written": _boolish(preflight.get("journal_written")) or _boolish(transaction_summary.get("journal_written")),
            "bounded_executor_gate_written": _boolish(preflight.get("bounded_executor_gate_written")) or _boolish(transaction_summary.get("bounded_executor_gate_written")),
            "executor_invoked": _boolish(preflight.get("executor_invoked")) or _boolish(transaction_summary.get("executor_invoked")),
            "next_action": preflight.get("next_action"),
        },
        "candidate_summary": candidate_summary,
        "journal_entries": journal_entries,
        "journal_summary": {
            "entry_count": len(journal_entries) if written else 0,
            "planned_entry_count": len(journal_entries),
            "transaction_started": written,
            "journal_written": written,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "requires_bounded_executor_gate_followup": True,
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_record_verified": _boolish(safety_gates.get("approval_record_verified")) or (_boolish(approval_summary.get("approval_recorded")) and _boolish(approval_summary.get("approved_for_execution"))),
            "transaction_started": written,
            "journal_written": written,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_executor_implemented": False,
            "requires_bounded_executor_gate": True,
            "requires_explicit_executor_review": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _heap_snapshot_retained_size_transaction_journal_next_action(status=status, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_heap_snapshot_retained_size_transaction_journal",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/heap-snapshot-retained-size-executor-journal.json",
            "future_path": "/workspace/browser/heap-snapshot-retained-size-executor-journal.json",
            "path": str(result_path),
        },
        "side_effect_policy": _heap_snapshot_retained_size_transaction_journal_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def make_record_heap_snapshot_diff_executor_transaction_journal_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit heap snapshot diff executor transaction journal writer.

    The writer consumes a ready heap-snapshot-diff-executor-transaction-preflight
    descriptor and writes only the transaction journal audit artifact under explicit
    apply gates. It never writes a bounded gate, invokes a heap diff executor,
    loads / parses / exports raw heap data, computes heap diffs, starts browsers,
    sends CDP, calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_heap_snapshot_diff_executor_transaction_journal(
        transaction_preflight_json: str | None = None,
        transaction_preflight_ref: str | None = None,
        reviewer: str | None = None,
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_transaction_journal: bool = False,
        expected_approval_scope: str | None = None,
        expected_transaction_id: str | None = None,
        expected_idempotency_key: str | None = None,
        expected_transaction_preflight_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Write a reviewed heap snapshot diff executor transaction journal."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_heap_snapshot_diff_executor_transaction_journal_payload(
            transaction_preflight_json=transaction_preflight_json,
            transaction_preflight_ref=transaction_preflight_ref,
            reviewer=reviewer,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_transaction_journal=approve_transaction_journal,
            expected_approval_scope=expected_approval_scope,
            expected_transaction_id=expected_transaction_id,
            expected_idempotency_key=expected_idempotency_key,
            expected_transaction_preflight_digest_sha256=expected_transaction_preflight_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_heap_snapshot_diff_executor_transaction_journal.__name__ = "record_heap_snapshot_diff_executor_transaction_journal"
    return record_heap_snapshot_diff_executor_transaction_journal


def record_heap_snapshot_diff_executor_transaction_journal_payload(
    *,
    transaction_preflight_json: str | None = None,
    transaction_preflight_ref: str | None = None,
    reviewer: str | None = None,
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_transaction_journal: bool = False,
    expected_approval_scope: str | None = None,
    expected_transaction_id: str | None = None,
    expected_idempotency_key: str | None = None,
    expected_transaction_preflight_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the heap snapshot diff executor transaction journal payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        transaction_preflight_json,
        artifact_ref=transaction_preflight_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="transaction_preflight_json",
        artifact_field_name="transaction_preflight_ref",
    )
    preflight = _first_object(loaded.get("descriptor"), loaded.get("transaction_preflight_descriptor"), loaded)
    approval_summary = preflight.get("approval_summary") if isinstance(preflight.get("approval_summary"), dict) else {}
    transaction_summary = preflight.get("transaction_summary") if isinstance(preflight.get("transaction_summary"), dict) else {}
    preflight_summary = preflight.get("preflight_summary") if isinstance(preflight.get("preflight_summary"), dict) else {}
    journal_contract = preflight.get("journal_writer_contract") if isinstance(preflight.get("journal_writer_contract"), dict) else {}
    safety_gates = preflight.get("safety_gates") if isinstance(preflight.get("safety_gates"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "heap-snapshot-diff-executor-journal.json"
    preflight_digest = _stable_json_digest(preflight) if preflight else None
    transaction_preflight_id = _heap_snapshot_diff_executor_transaction_preflight_id(preflight_digest or "") if preflight else ""
    approval_scope = str(approval_summary.get("approval_scope") or "")
    transaction_id = str(transaction_summary.get("transaction_id") or "")
    idempotency_key = str(transaction_summary.get("idempotency_key") or "")
    checks = _heap_snapshot_diff_executor_transaction_journal_checks(
        preflight=preflight,
        approval_summary=approval_summary,
        transaction_summary=transaction_summary,
        journal_contract=journal_contract,
        safety_gates=safety_gates,
        reviewer=reviewer,
        mode=mode,
        write_result=write_result,
        approve_transaction_journal=approve_transaction_journal,
        expected_approval_scope=expected_approval_scope,
        expected_transaction_id=expected_transaction_id,
        expected_idempotency_key=expected_idempotency_key,
        expected_transaction_preflight_digest_sha256=expected_transaction_preflight_digest_sha256,
        preflight_digest=preflight_digest,
        transaction_preflight_id=transaction_preflight_id,
        approval_scope=approval_scope,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_transaction_journal
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    journal_id = _heap_snapshot_diff_executor_transaction_journal_id(
        transaction_preflight_id=transaction_preflight_id,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        reviewer=reviewer,
        created_at=created_at,
    )
    journal_entries = [
        {
            "entry_index": 0,
            "entry_kind": "transaction_started",
            "transaction_preflight_id": transaction_preflight_id or None,
            "transaction_id": transaction_id or None,
            "idempotency_key": idempotency_key or None,
            "reviewer": reviewer,
            "created_at": created_at,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "heap_diff_computed": False,
        },
        {
            "entry_index": 1,
            "entry_kind": "heap_diff_executor_journal_gate_recorded",
            "approval_scope": approval_scope or None,
            "requires_bounded_executor_gate": True,
            "requires_safe_raw_heap_parser": True,
            "executed_now": False,
        },
    ]
    payload: dict[str, Any] = {
        "schema_version": HEAP_SNAPSHOT_DIFF_EXECUTOR_TRANSACTION_JOURNAL_VERSION,
        "status": status,
        "journal_written": written,
        "transaction_started": written,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "journal_id": journal_id,
        "transaction_preflight_id": transaction_preflight_id or None,
        "transaction_id": transaction_id or None,
        "idempotency_key": idempotency_key or None,
        "approval_scope": approval_scope or None,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "transaction_preflight_digest_sha256": preflight_digest,
        "expected_transaction_preflight_digest_sha256": expected_transaction_preflight_digest_sha256,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "complete_heap_traversal_claimed": False,
        "diff_executor_implemented": False,
        "source_transaction_preflight_summary": {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "transaction_preflight_only": _boolish(preflight.get("transaction_preflight_only")),
            "approval_recorded": _boolish(approval_summary.get("approval_recorded")),
            "approved_for_execution": _boolish(approval_summary.get("approved_for_execution")),
            "ready_to_write_journal": _boolish(safety_gates.get("ready_to_write_journal")) or _boolish(journal_contract.get("ready_for_journal_review")),
            "ready_to_execute_now": _boolish(safety_gates.get("ready_to_execute_now")),
            "transaction_started": _boolish(preflight.get("transaction_started")) or _boolish(transaction_summary.get("transaction_started")),
            "journal_written": _boolish(preflight.get("journal_written")) or _boolish(transaction_summary.get("journal_written")),
            "bounded_executor_gate_written": _boolish(preflight.get("bounded_executor_gate_written")) or _boolish(transaction_summary.get("bounded_executor_gate_written")),
            "executor_invoked": _boolish(preflight.get("executor_invoked")) or _boolish(transaction_summary.get("executor_invoked")),
            "next_action": preflight.get("next_action"),
        },
        "preflight_summary": {
            "before_digest": preflight_summary.get("before_digest"),
            "after_digest": preflight_summary.get("after_digest"),
            "raw_heap_ingestion_policy": preflight_summary.get("raw_heap_ingestion_policy"),
            "parser_sandbox": preflight_summary.get("parser_sandbox"),
            "redaction_plan": preflight_summary.get("redaction_plan"),
            "max_raw_heap_bytes": preflight_summary.get("max_raw_heap_bytes"),
        },
        "journal_entries": journal_entries,
        "journal_summary": {
            "entry_count": len(journal_entries) if written else 0,
            "planned_entry_count": len(journal_entries),
            "transaction_started": written,
            "journal_written": written,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "requires_bounded_executor_gate_followup": True,
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_record_verified": _boolish(safety_gates.get("approval_record_verified")) or (_boolish(approval_summary.get("approval_recorded")) and _boolish(approval_summary.get("approved_for_execution"))),
            "transaction_started": written,
            "journal_written": written,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "requires_bounded_executor_gate": True,
            "requires_explicit_executor_review": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _heap_snapshot_diff_executor_transaction_journal_next_action(status=status, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_heap_snapshot_diff_executor_transaction_journal",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/heap-snapshot-diff-executor-journal.json",
            "future_path": "/workspace/browser/heap-snapshot-diff-executor-journal.json",
            "path": str(result_path),
        },
        "side_effect_policy": _heap_snapshot_diff_executor_transaction_journal_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def make_record_source_map_followthrough_dispatch_transaction_journal_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit Source Map follow-through dispatch transaction journal writer.

    The writer consumes a ready source-map-followthrough-dispatch-transaction-preflight
    descriptor and writes only the transaction journal audit artifact under explicit
    apply gates. It never dispatches, invokes a selected executor, starts browsers,
    sends CDP, evaluates JavaScript, calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_source_map_followthrough_dispatch_transaction_journal(
        transaction_preflight_json: str | None = None,
        transaction_preflight_ref: str | None = None,
        reviewer: str | None = None,
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_transaction_journal: bool = False,
        expected_transaction_preflight_id: str | None = None,
        expected_approval_record_id: str | None = None,
        expected_transaction_plan_id: str | None = None,
        expected_approval_plan_id: str | None = None,
        expected_consumer: str | None = None,
        expected_dispatch_surface: str | None = None,
        expected_required_artifact: str | None = None,
        expected_preflight_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Write a reviewed Source Map follow-through dispatch transaction journal."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_source_map_followthrough_dispatch_transaction_journal_payload(
            transaction_preflight_json=transaction_preflight_json,
            transaction_preflight_ref=transaction_preflight_ref,
            reviewer=reviewer,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_transaction_journal=approve_transaction_journal,
            expected_transaction_preflight_id=expected_transaction_preflight_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_transaction_plan_id=expected_transaction_plan_id,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_consumer=expected_consumer,
            expected_dispatch_surface=expected_dispatch_surface,
            expected_required_artifact=expected_required_artifact,
            expected_preflight_digest_sha256=expected_preflight_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_source_map_followthrough_dispatch_transaction_journal.__name__ = "record_source_map_followthrough_dispatch_transaction_journal"
    return record_source_map_followthrough_dispatch_transaction_journal


def record_source_map_followthrough_dispatch_transaction_journal_payload(
    *,
    transaction_preflight_json: str | None = None,
    transaction_preflight_ref: str | None = None,
    reviewer: str | None = None,
    reason: str | None = None,
    mode: str = "dry-run",
    write_result: bool = False,
    approve_transaction_journal: bool = False,
    expected_transaction_preflight_id: str | None = None,
    expected_approval_record_id: str | None = None,
    expected_transaction_plan_id: str | None = None,
    expected_approval_plan_id: str | None = None,
    expected_consumer: str | None = None,
    expected_dispatch_surface: str | None = None,
    expected_required_artifact: str | None = None,
    expected_preflight_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the Source Map follow-through dispatch transaction journal."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        transaction_preflight_json,
        artifact_ref=transaction_preflight_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="transaction_preflight_json",
        artifact_field_name="transaction_preflight_ref",
    )
    preflight = _first_object(loaded.get("descriptor"), loaded.get("transaction_preflight_descriptor"), loaded)
    transaction_preflight_gate = preflight.get("transaction_preflight") if isinstance(preflight.get("transaction_preflight"), dict) else {}
    journal_writer_gate = preflight.get("journal_writer_gate") if isinstance(preflight.get("journal_writer_gate"), dict) else {}
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    result_path = effective_root / "workspace" / "source-map-followthrough-dispatch-transaction-journal.json"
    preflight_digest = _stable_json_digest(preflight) if preflight else None
    transaction_preflight_id = _source_map_followthrough_dispatch_transaction_preflight_id(preflight_digest or "") if preflight else ""
    approval_record_id = str(preflight.get("approval_record_id") or transaction_preflight_gate.get("approval_record_id") or journal_writer_gate.get("approval_record_id") or "")
    approval_plan_id = str(preflight.get("approval_plan_id") or transaction_preflight_gate.get("approval_plan_id") or "")
    transaction_plan_id = str(preflight.get("transaction_plan_id") or transaction_preflight_gate.get("transaction_plan_id") or journal_writer_gate.get("transaction_plan_id") or "")
    selected_consumer = str(preflight.get("selected_consumer") or transaction_preflight_gate.get("selected_consumer") or "")
    dispatch_surface = str(preflight.get("dispatch_surface") or transaction_preflight_gate.get("dispatch_surface") or "")
    required_artifact = str(preflight.get("planned_required_artifact") or transaction_preflight_gate.get("required_result_artifact") or "")
    checks = _source_map_followthrough_dispatch_transaction_journal_checks(
        preflight=preflight,
        transaction_preflight_gate=transaction_preflight_gate,
        journal_writer_gate=journal_writer_gate,
        reviewer=reviewer,
        mode=mode,
        write_result=write_result,
        approve_transaction_journal=approve_transaction_journal,
        expected_transaction_preflight_id=expected_transaction_preflight_id,
        expected_approval_record_id=expected_approval_record_id,
        expected_transaction_plan_id=expected_transaction_plan_id,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_consumer=expected_consumer,
        expected_dispatch_surface=expected_dispatch_surface,
        expected_required_artifact=expected_required_artifact,
        expected_preflight_digest_sha256=expected_preflight_digest_sha256,
        preflight_digest=preflight_digest,
        transaction_preflight_id=transaction_preflight_id,
        approval_record_id=approval_record_id,
        transaction_plan_id=transaction_plan_id,
        approval_plan_id=approval_plan_id,
        selected_consumer=selected_consumer,
        dispatch_surface=dispatch_surface,
        required_artifact=required_artifact,
        result_path=result_path,
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    written = not blockers and mode == "apply" and write_result and approve_transaction_journal
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    journal_id = _source_map_followthrough_dispatch_transaction_journal_id(
        transaction_preflight_id=transaction_preflight_id,
        approval_record_id=approval_record_id,
        transaction_plan_id=transaction_plan_id,
        reviewer=reviewer,
        created_at=created_at,
    )
    journal_entries = [
        {
            "entry_index": 0,
            "entry_kind": "transaction_started",
            "transaction_preflight_id": transaction_preflight_id or None,
            "approval_record_id": approval_record_id or None,
            "transaction_plan_id": transaction_plan_id or None,
            "reviewer": reviewer,
            "created_at": created_at,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
        },
        {
            "entry_index": 1,
            "entry_kind": "dispatch_journal_gate_recorded",
            "selected_consumer": selected_consumer or None,
            "dispatch_surface": dispatch_surface or None,
            "required_result_artifact": required_artifact or None,
            "requires_bounded_dispatch_gate": True,
            "executed_now": False,
        },
    ]
    payload: dict[str, Any] = {
        "schema_version": SOURCE_MAP_FOLLOWTHROUGH_DISPATCH_TRANSACTION_JOURNAL_VERSION,
        "status": status,
        "journal_written": written,
        "transaction_started": written,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "journal_id": journal_id,
        "transaction_preflight_id": transaction_preflight_id or None,
        "approval_record_id": approval_record_id or None,
        "approval_plan_id": approval_plan_id or None,
        "transaction_plan_id": transaction_plan_id or None,
        "selected_consumer": selected_consumer or None,
        "dispatch_surface": dispatch_surface or None,
        "required_result_artifact": required_artifact or None,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "transaction_preflight_digest_sha256": preflight_digest,
        "expected_preflight_digest_sha256": expected_preflight_digest_sha256,
        "source_transaction_preflight_summary": {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "transaction_preflight_ready_for_review": _boolish(preflight.get("transaction_preflight_ready_for_review")),
            "journal_writer_gate_ready_for_review": _boolish(preflight.get("journal_writer_gate_ready_for_review")),
            "approval_record_verified": _boolish(preflight.get("approval_record_verified")),
            "transaction_plan_verified": _boolish(preflight.get("transaction_plan_verified")),
            "ready_to_write_now": _boolish(preflight.get("ready_to_write_now")),
            "ready_to_dispatch_now": _boolish(preflight.get("ready_to_dispatch_now")),
            "transaction_started": _boolish(preflight.get("transaction_started")),
            "journal_written": _boolish(preflight.get("journal_written")),
            "will_write_transaction_journal": _boolish(preflight.get("will_write_transaction_journal")),
            "will_invoke_dispatch_target": _boolish(preflight.get("will_invoke_dispatch_target")),
            "next_action": preflight.get("next_action"),
        },
        "transaction_preflight_gate_summary": {
            "schema_version": transaction_preflight_gate.get("schema_version"),
            "approval_record_verified": _boolish(transaction_preflight_gate.get("approval_record_verified")),
            "ready_to_write_now": _boolish(transaction_preflight_gate.get("ready_to_write_now")),
            "transaction_started": _boolish(transaction_preflight_gate.get("transaction_started")),
            "journal_written": _boolish(transaction_preflight_gate.get("journal_written")),
            "dispatch_target_invoked": _boolish(transaction_preflight_gate.get("dispatch_target_invoked")),
            "executor_invoked": _boolish(transaction_preflight_gate.get("executor_invoked")),
        },
        "journal_writer_gate_summary": {
            "schema_version": journal_writer_gate.get("schema_version"),
            "journal_artifact": journal_writer_gate.get("journal_artifact"),
            "requires_explicit_journal_write_approval": _boolish(journal_writer_gate.get("requires_explicit_journal_write_approval")),
            "journal_required_before_dispatch": _boolish(journal_writer_gate.get("journal_required_before_dispatch")),
            "approval_recorded": _boolish(journal_writer_gate.get("approval_recorded")),
            "approved_for_dispatch": _boolish(journal_writer_gate.get("approved_for_dispatch")),
            "ready_to_write_now": _boolish(journal_writer_gate.get("ready_to_write_now")),
            "journal_written_now": _boolish(journal_writer_gate.get("journal_written_now")),
        },
        "journal_entries": journal_entries,
        "journal_summary": {
            "entry_count": len(journal_entries) if written else 0,
            "planned_entry_count": len(journal_entries),
            "transaction_started": written,
            "journal_written": written,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "requires_bounded_dispatch_gate_followup": True,
        },
        "dispatch_input_gates": {
            "ready_to_dispatch_now": False,
            "approval_record_verified": _boolish(preflight.get("approval_record_verified")),
            "transaction_plan_verified": _boolish(preflight.get("transaction_plan_verified")),
            "transaction_started": written,
            "journal_written": written,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "debugger_executed": False,
            "source_logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "requires_bounded_dispatch_gate": True,
            "requires_explicit_dispatch_review": True,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _source_map_followthrough_dispatch_transaction_journal_next_action(status=status, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_source_map_followthrough_dispatch_transaction_journal",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/source-map-followthrough-dispatch-transaction-journal.json",
            "future_path": "/workspace/debugger/source-map-followthrough-dispatch-transaction-journal.json",
            "path": str(result_path),
        },
        "side_effect_policy": _source_map_followthrough_dispatch_transaction_journal_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


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


def _loads_optional_object(payload: str | None, *, field_name: str) -> dict[str, Any]:
    if payload is None or payload == "":
        return {}
    return _loads_object(payload, field_name=field_name)


def _first_object(*items: Any) -> dict[str, Any]:
    for item in items:
        if isinstance(item, dict):
            return item
    return {}


def _object_alias(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _stable_json_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)



def _heap_snapshot_diff_executor_approval_record_checks(
    *,
    descriptor: dict[str, Any],
    approval_plan: dict[str, Any],
    transaction_plan: dict[str, Any],
    reviewer: str | None,
    decision: str,
    mode: str,
    write_result: bool,
    approve_heap_snapshot_diff_executor: bool,
    expected_approval_scope: str | None,
    expected_transaction_id: str | None,
    expected_idempotency_key: str | None,
    expected_plan_digest_sha256: str | None,
    expected_preflight_digest_sha256: str | None,
    plan_digest: str | None,
    preflight_digest: str | None,
    result_path: Path,
) -> list[dict[str, Any]]:
    policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
    gates = descriptor.get("safety_gates") if isinstance(descriptor.get("safety_gates"), dict) else {}
    future_contract = descriptor.get("future_executor_contract") if isinstance(descriptor.get("future_executor_contract"), dict) else {}
    approval_scope = str(approval_plan.get("approval_scope") or "")
    transaction_id = str(transaction_plan.get("transaction_id") or "")
    idempotency_key = str(transaction_plan.get("idempotency_key") or "")
    return [
        {"name": "approval_plan_available", "passed": bool(descriptor), "details": {"schema_version": descriptor.get("schema_version")}},
        {"name": "approval_plan_schema_matches", "passed": descriptor.get("schema_version") == "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1", "details": {"schema_version": descriptor.get("schema_version")}},
        {"name": "approval_plan_ready_for_review", "passed": descriptor.get("status") == "ready_for_review", "details": {"status": descriptor.get("status")}},
        {"name": "approval_plan_is_plan_only", "passed": descriptor.get("approval_plan_only") is True and descriptor.get("transaction_plan_only") is True, "details": {"approval_plan_only": descriptor.get("approval_plan_only"), "transaction_plan_only": descriptor.get("transaction_plan_only")}},
        {"name": "approval_scope_present", "passed": bool(approval_scope), "details": {"approval_scope": approval_scope}},
        {"name": "approval_scope_supported", "passed": approval_scope == "heap-snapshot-diff-executor", "details": {"approval_scope": approval_scope}},
        {"name": "approval_record_target_matches", "passed": approval_plan.get("approval_record_artifact") in {None, "", "workspace/heap-snapshot-diff-executor-approval-record.json"}, "details": {"approval_record_artifact": approval_plan.get("approval_record_artifact")}},
        {"name": "required_approval_flag_matches", "passed": approval_plan.get("required_approval_flag") in {None, "", "approve_heap_snapshot_diff_executor"}, "details": {"required_approval_flag": approval_plan.get("required_approval_flag")}},
        {"name": "transaction_plan_present", "passed": bool(transaction_plan), "details": {"transaction_id": transaction_id, "idempotency_key": idempotency_key}},
        {"name": "transaction_id_present", "passed": bool(transaction_id), "details": {"transaction_id": transaction_id}},
        {"name": "idempotency_key_present", "passed": bool(idempotency_key), "details": {"idempotency_key": idempotency_key}},
        {"name": "transaction_journal_target_present", "passed": bool(transaction_plan.get("transaction_journal_artifact")), "details": {"transaction_journal_artifact": transaction_plan.get("transaction_journal_artifact")}},
        {"name": "bounded_gate_target_present", "passed": bool(transaction_plan.get("bounded_gate_artifact")), "details": {"bounded_gate_artifact": transaction_plan.get("bounded_gate_artifact")}},
        {"name": "result_artifact_present", "passed": bool(transaction_plan.get("result_artifact")), "details": {"result_artifact": transaction_plan.get("result_artifact")}},
        {"name": "bounded_executor_gate_required", "passed": transaction_plan.get("bounded_executor_gate_required") is True and future_contract.get("requires_bounded_executor_gate") is True, "details": {"transaction_plan_gate_required": transaction_plan.get("bounded_executor_gate_required"), "contract_gate_required": future_contract.get("requires_bounded_executor_gate")}},
        {"name": "approval_not_already_recorded", "passed": descriptor.get("approval_recorded") is not True and approval_plan.get("approval_recorded") is not True and policy.get("approval_recorded") is not True, "details": {"descriptor_approval_recorded": descriptor.get("approval_recorded"), "approval_plan_recorded": approval_plan.get("approval_recorded"), "policy_recorded": policy.get("approval_recorded")}},
        {"name": "transaction_not_started", "passed": descriptor.get("transaction_started") is not True and transaction_plan.get("transaction_started") is not True and policy.get("transaction_started") is not True, "details": {"descriptor_transaction_started": descriptor.get("transaction_started"), "transaction_started": transaction_plan.get("transaction_started"), "policy_transaction_started": policy.get("transaction_started")}},
        {"name": "journal_not_written", "passed": descriptor.get("journal_written_now") is not True and transaction_plan.get("journal_written_now") is not True and policy.get("journal_written_now") is not True and policy.get("journal_written") is not True, "details": {"descriptor_journal_written_now": descriptor.get("journal_written_now"), "transaction_journal_written_now": transaction_plan.get("journal_written_now"), "policy_journal_written_now": policy.get("journal_written_now")}},
        {"name": "bounded_gate_not_written", "passed": descriptor.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"descriptor_bounded_gate_written": descriptor.get("bounded_executor_gate_written"), "policy_bounded_gate_written": policy.get("bounded_executor_gate_written")}},
        {"name": "executor_not_invoked", "passed": descriptor.get("executor_invoked") is not True and policy.get("executor_invoked") is not True, "details": {"descriptor_executor_invoked": descriptor.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked")}},
        {"name": "future_executor_not_implemented", "passed": future_contract.get("implemented") is not True and descriptor.get("diff_executor_implemented") is not True and gates.get("future_diff_executor_implemented") is not True, "details": {"future_executor_implemented": future_contract.get("implemented"), "diff_executor_implemented": descriptor.get("diff_executor_implemented"), "future_diff_executor_implemented": gates.get("future_diff_executor_implemented")}},
        {"name": "raw_heap_not_loaded", "passed": descriptor.get("raw_heap_loaded") is not True and policy.get("raw_heap_loaded") is not True, "details": {"descriptor_raw_heap_loaded": descriptor.get("raw_heap_loaded"), "policy_raw_heap_loaded": policy.get("raw_heap_loaded")}},
        {"name": "raw_heap_not_parsed", "passed": descriptor.get("raw_heap_parsed") is not True and policy.get("raw_heap_parsed") is not True, "details": {"descriptor_raw_heap_parsed": descriptor.get("raw_heap_parsed"), "policy_raw_heap_parsed": policy.get("raw_heap_parsed")}},
        {"name": "raw_heap_not_exported", "passed": descriptor.get("raw_heap_exported") is not True and policy.get("raw_heap_exported") is not True, "details": {"descriptor_raw_heap_exported": descriptor.get("raw_heap_exported"), "policy_raw_heap_exported": policy.get("raw_heap_exported")}},
        {"name": "heap_diff_not_computed", "passed": descriptor.get("heap_diff_computed") is not True and descriptor.get("heap_snapshot_diff_computed") is not True and policy.get("heap_diff_computed") is not True and policy.get("heap_snapshot_diff_computed") is not True, "details": {"descriptor_heap_diff_computed": descriptor.get("heap_diff_computed"), "policy_heap_diff_computed": policy.get("heap_diff_computed")}},
        {"name": "complete_traversal_not_claimed", "passed": descriptor.get("complete_heap_traversal_claimed") is not True and policy.get("complete_heap_traversal") is not True, "details": {"descriptor_complete_heap_traversal_claimed": descriptor.get("complete_heap_traversal_claimed"), "policy_complete_heap_traversal": policy.get("complete_heap_traversal")}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "decision_supported", "passed": decision in {"approved", "rejected", "needs_changes"}, "details": {"decision": decision}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_heap_snapshot_diff_executor_approval", "passed": mode != "apply" or bool(approve_heap_snapshot_diff_executor), "details": {"approve_heap_snapshot_diff_executor": approve_heap_snapshot_diff_executor}},
        {"name": "expected_approval_scope_matches", "passed": not expected_approval_scope or approval_scope == expected_approval_scope, "details": {"expected_approval_scope": expected_approval_scope, "approval_scope": approval_scope}},
        {"name": "expected_transaction_id_matches", "passed": not expected_transaction_id or transaction_id == expected_transaction_id, "details": {"expected_transaction_id": expected_transaction_id, "transaction_id": transaction_id}},
        {"name": "expected_idempotency_key_matches", "passed": not expected_idempotency_key or idempotency_key == expected_idempotency_key, "details": {"expected_idempotency_key": expected_idempotency_key, "idempotency_key": idempotency_key}},
        {"name": "expected_plan_digest_matches", "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest, "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest}},
        {"name": "expected_preflight_digest_matches", "passed": not expected_preflight_digest_sha256 or expected_preflight_digest_sha256 == preflight_digest, "details": {"expected_preflight_digest_sha256": expected_preflight_digest_sha256, "preflight_summary_digest_sha256": preflight_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "approval_plan_no_heap_diff_side_effects", "passed": _heap_snapshot_diff_executor_approval_no_side_effects(policy), "details": policy},
    ]


def _heap_snapshot_diff_executor_approval_no_side_effects(policy: dict[str, Any]) -> bool:
    return not any(
        _boolish(policy.get(key))
        for key in (
            "files_mutated",
            "artifacts_written",
            "approval_artifact_written",
            "transaction_started",
            "journal_written",
            "journal_written_now",
            "bounded_executor_gate_written",
            "executor_invoked",
            "browser_started",
            "provider_factory_invoked",
            "provider_availability_checked",
            "cdp_command_sent",
            "heap_profiler_enabled",
            "heap_snapshot_collected",
            "heap_snapshot_diff_computed",
            "heap_diff_computed",
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "complete_heap_traversal",
            "runtime_evaluated",
            "javascript_evaluated",
            "calls_mcp",
            "mobile_runtime_used",
        )
    )


def _heap_snapshot_diff_executor_approval_record_next_action(*, status: str, decision: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_heap_snapshot_diff_executor_approval_record_blockers"
    if status == "planned":
        return "review_heap_snapshot_diff_executor_approval_record_before_apply_write"
    if decision == "approved":
        return "review_heap_snapshot_diff_executor_transaction_preflight"
    return "revise_heap_snapshot_diff_executor_approval_before_transaction"


def _heap_snapshot_diff_executor_approval_record_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "approval_record_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_approval_record": written,
        "approval_recorded": written,
        "ready_to_execute_now": False,
        "transaction_started": False,
        "journal_written": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "complete_heap_traversal": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _heap_snapshot_diff_executor_approval_record_id(
    *,
    approval_scope: str,
    transaction_id: str,
    idempotency_key: str,
    decision: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{approval_scope}\0{transaction_id}\0{idempotency_key}\0{decision}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"heap-snapshot-diff-executor-approval-record:{digest}"


def _heap_snapshot_retained_size_approval_record_checks(
    *,
    descriptor: dict[str, Any],
    approval_plan: dict[str, Any],
    transaction_plan: dict[str, Any],
    executor_contract: dict[str, Any],
    reviewer: str | None,
    decision: str,
    mode: str,
    write_result: bool,
    approve_heap_snapshot_retained_size: bool,
    expected_approval_plan_id: str | None,
    expected_transaction_plan_id: str | None,
    expected_candidate_digest: str | None,
    expected_plan_digest_sha256: str | None,
    plan_digest: str | None,
    approval_plan_id: str,
    transaction_plan_id: str,
    candidate_digest: str,
    result_path: Path,
) -> list[dict[str, Any]]:
    policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
    return [
        {"name": "approval_plan_available", "passed": bool(descriptor), "details": {"schema_version": descriptor.get("schema_version")}},
        {"name": "approval_plan_schema_matches", "passed": descriptor.get("schema_version") == "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1", "details": {"schema_version": descriptor.get("schema_version")}},
        {"name": "approval_plan_ready_for_review", "passed": descriptor.get("status") == "ready_for_review", "details": {"status": descriptor.get("status")}},
        {"name": "approval_plan_is_plan_only", "passed": descriptor.get("approval_plan_only") is True and descriptor.get("transaction_plan_only") is True, "details": {"approval_plan_only": descriptor.get("approval_plan_only"), "transaction_plan_only": descriptor.get("transaction_plan_only")}},
        {"name": "approval_plan_is_retained_size_only", "passed": descriptor.get("retained_size_only") is True, "details": {"retained_size_only": descriptor.get("retained_size_only")}},
        {"name": "approval_plan_id_present", "passed": bool(approval_plan_id), "details": {"approval_plan_id": approval_plan_id}},
        {"name": "candidate_digest_present", "passed": bool(candidate_digest), "details": {"candidate_digest": candidate_digest}},
        {"name": "approval_record_target_matches", "passed": approval_plan.get("approval_record_artifact") in {None, "", "workspace/heap-snapshot-retained-size-approval-record.json"}, "details": {"approval_record_artifact": approval_plan.get("approval_record_artifact")}},
        {"name": "approval_record_writer_matches", "passed": approval_plan.get("approval_record_writer") in {None, "", "record_heap_snapshot_retained_size_approval"}, "details": {"approval_record_writer": approval_plan.get("approval_record_writer")}},
        {"name": "transaction_plan_present", "passed": bool(transaction_plan), "details": {"transaction_plan_id": transaction_plan_id}},
        {"name": "transaction_plan_id_present", "passed": bool(transaction_plan_id), "details": {"transaction_plan_id": transaction_plan_id}},
        {"name": "transaction_journal_target_present", "passed": bool(transaction_plan.get("transaction_journal_artifact")), "details": {"transaction_journal_artifact": transaction_plan.get("transaction_journal_artifact")}},
        {"name": "bounded_gate_target_present", "passed": bool(transaction_plan.get("bounded_gate_artifact")), "details": {"bounded_gate_artifact": transaction_plan.get("bounded_gate_artifact")}},
        {"name": "result_artifact_present", "passed": bool(transaction_plan.get("result_artifact")), "details": {"result_artifact": transaction_plan.get("result_artifact")}},
        {"name": "approval_not_already_recorded", "passed": descriptor.get("approval_recorded") is not True and approval_plan.get("approval_recorded") is not True and policy.get("approval_recorded") is not True, "details": {"descriptor_approval_recorded": descriptor.get("approval_recorded"), "approval_plan_recorded": approval_plan.get("approval_recorded"), "policy_recorded": policy.get("approval_recorded")}},
        {"name": "transaction_not_started", "passed": descriptor.get("transaction_started") is not True and transaction_plan.get("transaction_started") is not True and policy.get("transaction_started") is not True, "details": {"descriptor_transaction_started": descriptor.get("transaction_started"), "transaction_started": transaction_plan.get("transaction_started"), "policy_transaction_started": policy.get("transaction_started")}},
        {"name": "journal_not_written", "passed": descriptor.get("journal_written_now") is not True and transaction_plan.get("journal_written") is not True and policy.get("journal_written_now") is not True and policy.get("journal_written") is not True, "details": {"descriptor_journal_written_now": descriptor.get("journal_written_now"), "transaction_journal_written": transaction_plan.get("journal_written"), "policy_journal_written": policy.get("journal_written")}},
        {"name": "bounded_gate_not_written", "passed": descriptor.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"descriptor_bounded_gate_written": descriptor.get("bounded_executor_gate_written"), "policy_bounded_gate_written": policy.get("bounded_executor_gate_written")}},
        {"name": "executor_not_invoked", "passed": descriptor.get("executor_invoked") is not True and policy.get("executor_invoked") is not True and policy.get("future_executor_invoked") is not True, "details": {"descriptor_executor_invoked": descriptor.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked"), "policy_future_executor_invoked": policy.get("future_executor_invoked")}},
        {"name": "future_executor_not_implemented", "passed": executor_contract.get("implemented") is not True and executor_contract.get("ready_to_execute_now") is not True, "details": {"implemented": executor_contract.get("implemented"), "ready_to_execute_now": executor_contract.get("ready_to_execute_now")}},
        {"name": "raw_heap_not_loaded", "passed": descriptor.get("raw_heap_loaded") is not True and policy.get("raw_heap_loaded") is not True, "details": {"descriptor_raw_heap_loaded": descriptor.get("raw_heap_loaded"), "policy_raw_heap_loaded": policy.get("raw_heap_loaded")}},
        {"name": "raw_heap_not_parsed", "passed": descriptor.get("raw_heap_parsed") is not True and policy.get("raw_heap_parsed") is not True, "details": {"descriptor_raw_heap_parsed": descriptor.get("raw_heap_parsed"), "policy_raw_heap_parsed": policy.get("raw_heap_parsed")}},
        {"name": "raw_heap_not_exported", "passed": descriptor.get("raw_heap_exported") is not True and descriptor.get("raw_strings_exported") is not True and policy.get("raw_heap_exported") is not True and policy.get("raw_strings_exported") is not True, "details": {"descriptor_raw_heap_exported": descriptor.get("raw_heap_exported"), "descriptor_raw_strings_exported": descriptor.get("raw_strings_exported"), "policy_raw_heap_exported": policy.get("raw_heap_exported"), "policy_raw_strings_exported": policy.get("raw_strings_exported")}},
        {"name": "heap_diff_not_computed", "passed": descriptor.get("heap_diff_computed") is not True and descriptor.get("heap_snapshot_diff_computed") is not True and policy.get("heap_diff_computed") is not True and policy.get("heap_snapshot_diff_computed") is not True, "details": {"descriptor_heap_diff_computed": descriptor.get("heap_diff_computed"), "policy_heap_diff_computed": policy.get("heap_diff_computed")}},
        {"name": "retained_size_not_proven", "passed": descriptor.get("retained_size_proven") is not True and policy.get("retained_size_proven") is not True, "details": {"descriptor_retained_size_proven": descriptor.get("retained_size_proven"), "policy_retained_size_proven": policy.get("retained_size_proven")}},
        {"name": "path_to_root_not_computed", "passed": descriptor.get("path_to_root_computed") is not True and policy.get("path_to_root_computed") is not True, "details": {"descriptor_path_to_root_computed": descriptor.get("path_to_root_computed"), "policy_path_to_root_computed": policy.get("path_to_root_computed")}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "decision_supported", "passed": decision in {"approved", "rejected", "needs_changes"}, "details": {"decision": decision}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_heap_snapshot_retained_size_approval", "passed": mode != "apply" or bool(approve_heap_snapshot_retained_size), "details": {"approve_heap_snapshot_retained_size": approve_heap_snapshot_retained_size}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or approval_plan_id == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": approval_plan_id}},
        {"name": "expected_transaction_plan_id_matches", "passed": not expected_transaction_plan_id or transaction_plan_id == expected_transaction_plan_id, "details": {"expected_transaction_plan_id": expected_transaction_plan_id, "transaction_plan_id": transaction_plan_id}},
        {"name": "expected_candidate_digest_matches", "passed": not expected_candidate_digest or candidate_digest == expected_candidate_digest, "details": {"expected_candidate_digest": expected_candidate_digest, "candidate_digest": candidate_digest}},
        {"name": "expected_plan_digest_matches", "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest, "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "approval_plan_no_retained_size_side_effects", "passed": _heap_snapshot_retained_size_approval_no_side_effects(policy), "details": policy},
    ]


def _heap_snapshot_retained_size_approval_no_side_effects(policy: dict[str, Any]) -> bool:
    return not any(
        _boolish(policy.get(key))
        for key in (
            "files_mutated",
            "artifacts_written",
            "approval_artifact_written",
            "transaction_started",
            "journal_written",
            "journal_written_now",
            "bounded_executor_gate_written",
            "executor_invoked",
            "future_executor_invoked",
            "browser_started",
            "provider_factory_invoked",
            "provider_availability_checked",
            "cdp_command_sent",
            "heap_profiler_enabled",
            "heap_snapshot_collected",
            "heap_snapshot_diff_computed",
            "heap_diff_computed",
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "complete_heap_traversal",
            "constructor_drilldown_computed",
            "retained_size_proven",
            "path_to_root_computed",
            "runtime_evaluated",
            "javascript_evaluated",
            "calls_mcp",
            "mobile_runtime_used",
        )
    )


def _heap_snapshot_retained_size_approval_record_next_action(*, status: str, decision: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_heap_snapshot_retained_size_approval_record_blockers"
    if status == "planned":
        return "review_heap_snapshot_retained_size_approval_record_before_apply_write"
    if decision == "approved":
        return "review_heap_snapshot_retained_size_transaction_preflight"
    return "revise_heap_snapshot_retained_size_approval_before_transaction"


def _heap_snapshot_retained_size_approval_record_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "approval_record_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_approval_record": written,
        "approval_recorded": written,
        "ready_to_execute_now": False,
        "transaction_started": False,
        "journal_written": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "future_executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "complete_heap_traversal": False,
        "constructor_drilldown_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _heap_snapshot_retained_size_approval_record_id(
    *,
    approval_plan_id: str,
    transaction_plan_id: str,
    candidate_digest: str,
    decision: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{approval_plan_id}\0{transaction_plan_id}\0{candidate_digest}\0{decision}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"heap-snapshot-retained-size-approval-record:{digest}"

def _source_map_selected_executor_approval_record_checks(
    *,
    approval_plan: dict[str, Any],
    reviewer: str | None,
    decision: str,
    mode: str,
    write_result: bool,
    approve_approval_record: bool,
    expected_action_id: str | None,
    expected_consumer: str | None,
    expected_gate: str | None,
    expected_plan_digest_sha256: str | None,
    plan_digest: str | None,
    result_path: Path,
) -> list[dict[str, Any]]:
    plan_blockers = approval_plan.get("blockers") if isinstance(approval_plan.get("blockers"), list) else []
    plan_policy = approval_plan.get("side_effect_policy") if isinstance(approval_plan.get("side_effect_policy"), dict) else {}
    apply_plan = approval_plan.get("apply_plan") if isinstance(approval_plan.get("apply_plan"), dict) else {}
    approval_requirements = approval_plan.get("approval_requirements") if isinstance(approval_plan.get("approval_requirements"), dict) else {}
    return [
        {"name": "approval_plan_available", "passed": bool(approval_plan), "details": {"selected_action_id": approval_plan.get("selected_action_id")}},
        {
            "name": "approval_plan_schema_matches",
            "passed": approval_plan.get("schema_version") == "reverse-deepagent.source-map-selected-executor-approval-plan.v1",
            "details": {"schema_version": approval_plan.get("schema_version")},
        },
        {
            "name": "approval_plan_ready_for_review",
            "passed": approval_plan.get("status") == "ready_for_review" and approval_plan.get("approval_plan_ready") is True and approval_plan.get("apply_plan_ready_for_review") is True,
            "details": {
                "status": approval_plan.get("status"),
                "approval_plan_ready": approval_plan.get("approval_plan_ready"),
                "apply_plan_ready_for_review": approval_plan.get("apply_plan_ready_for_review"),
            },
        },
        {"name": "approval_plan_has_no_blockers", "passed": not plan_blockers, "details": {"blockers": plan_blockers}},
        {"name": "approval_not_already_recorded", "passed": approval_plan.get("approval_recorded") is not True, "details": {"approval_recorded": approval_plan.get("approval_recorded")}},
        {"name": "approval_plan_not_ready_to_apply_now", "passed": approval_plan.get("ready_to_apply_now") is not True, "details": {"ready_to_apply_now": approval_plan.get("ready_to_apply_now")}},
        {"name": "surface_executor_not_invoked", "passed": approval_plan.get("surface_executor_invoked") is not True, "details": {"surface_executor_invoked": approval_plan.get("surface_executor_invoked")}},
        {
            "name": "selected_consumer_supported",
            "passed": approval_plan.get("selected_consumer") in {"debugger", "source-logpoint", "rebuild", "hook"},
            "details": {"selected_consumer": approval_plan.get("selected_consumer")},
        },
        {
            "name": "approval_record_artifact_matches",
            "passed": approval_requirements.get("approval_record_artifact") in {None, "", "workspace/source-map-selected-executor-approval-record.json"},
            "details": {"approval_record_artifact": approval_requirements.get("approval_record_artifact")},
        },
        {
            "name": "apply_plan_requires_approval_record",
            "passed": apply_plan.get("requires_approval_record") is True and apply_plan.get("expected_approval_record_artifact") in {None, "", "workspace/source-map-selected-executor-approval-record.json"},
            "details": {
                "requires_approval_record": apply_plan.get("requires_approval_record"),
                "expected_approval_record_artifact": apply_plan.get("expected_approval_record_artifact"),
            },
        },
        {
            "name": "apply_plan_is_not_execution",
            "passed": apply_plan.get("ready_to_apply_now") is not True and apply_plan.get("surface_executor_invoked") is not True and apply_plan.get("executor_implemented_now") is not True,
            "details": {
                "ready_to_apply_now": apply_plan.get("ready_to_apply_now"),
                "surface_executor_invoked": apply_plan.get("surface_executor_invoked"),
                "executor_implemented_now": apply_plan.get("executor_implemented_now"),
            },
        },
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "decision_supported", "passed": decision in {"approved", "rejected", "needs_changes"}, "details": {"decision": decision}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_approval_record", "passed": mode != "apply" or bool(approve_approval_record), "details": {"approve_approval_record": approve_approval_record}},
        {
            "name": "expected_action_id_matches",
            "passed": not expected_action_id or approval_plan.get("selected_action_id") == expected_action_id,
            "details": {"expected_action_id": expected_action_id, "selected_action_id": approval_plan.get("selected_action_id")},
        },
        {
            "name": "expected_consumer_matches",
            "passed": not expected_consumer or approval_plan.get("selected_consumer") == expected_consumer,
            "details": {"expected_consumer": expected_consumer, "selected_consumer": approval_plan.get("selected_consumer")},
        },
        {
            "name": "expected_gate_matches",
            "passed": not expected_gate or approval_plan.get("selected_review_gate") == expected_gate,
            "details": {"expected_gate": expected_gate, "selected_review_gate": approval_plan.get("selected_review_gate")},
        },
        {
            "name": "expected_plan_digest_matches",
            "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest,
            "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest},
        },
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "approval_plan_no_cdp", "passed": plan_policy.get("cdp_command_sent") is not True, "details": {"cdp_command_sent": plan_policy.get("cdp_command_sent")}},
        {"name": "approval_plan_no_runtime_eval", "passed": plan_policy.get("runtime_evaluated") is not True, "details": {"runtime_evaluated": plan_policy.get("runtime_evaluated")}},
        {"name": "approval_plan_no_surface_execution", "passed": plan_policy.get("surface_executor_invoked") is not True, "details": {"surface_executor_invoked": plan_policy.get("surface_executor_invoked")}},
        {"name": "approval_plan_no_mcp", "passed": plan_policy.get("calls_mcp") is not True, "details": {"calls_mcp": plan_policy.get("calls_mcp")}},
        {"name": "approval_plan_no_mobile_runtime", "passed": plan_policy.get("mobile_runtime_used") is not True, "details": {"mobile_runtime_used": plan_policy.get("mobile_runtime_used")}},
    ]


def _source_map_selected_executor_approval_record_next_action(*, status: str, decision: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_source_map_selected_executor_approval_record_blockers"
    if status == "planned":
        return "review_source_map_selected_executor_approval_record_before_apply_write"
    if decision == "approved":
        return "review_source_map_selected_executor_apply_preflight"
    return "revise_source_map_selected_executor_review_before_apply"


def _source_map_followthrough_dispatch_approval_record_checks(
    *,
    descriptor: dict[str, Any],
    approval_plan: dict[str, Any],
    transaction_plan: dict[str, Any],
    reviewer: str | None,
    decision: str,
    mode: str,
    write_result: bool,
    approve_approval_record: bool,
    expected_approval_plan_id: str | None,
    expected_consumer: str | None,
    expected_dispatch_surface: str | None,
    expected_required_artifact: str | None,
    expected_plan_digest_sha256: str | None,
    plan_digest: str | None,
    result_path: Path,
) -> list[dict[str, Any]]:
    descriptor_blockers = descriptor.get("blockers") if isinstance(descriptor.get("blockers"), list) else []
    descriptor_policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
    approval_policy = approval_plan.get("side_effect_policy") if isinstance(approval_plan.get("side_effect_policy"), dict) else {}
    transaction_policy = transaction_plan.get("side_effect_policy") if isinstance(transaction_plan.get("side_effect_policy"), dict) else {}
    selected_consumer = str(descriptor.get("selected_consumer") or approval_plan.get("selected_consumer") or "")
    dispatch_surface = str(descriptor.get("dispatch_surface") or approval_plan.get("dispatch_surface") or "")
    required_artifact = str(descriptor.get("planned_required_artifact") or approval_plan.get("required_result_artifact") or "")
    approval_plan_id = str(approval_plan.get("approval_plan_id") or "")
    return [
        {"name": "dispatch_approval_plan_available", "passed": bool(descriptor), "details": {"approval_plan_id": approval_plan_id}},
        {
            "name": "dispatch_approval_plan_schema_matches",
            "passed": descriptor.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1",
            "details": {"schema_version": descriptor.get("schema_version")},
        },
        {
            "name": "dispatch_approval_plan_ready_for_review",
            "passed": descriptor.get("status") == "ready_for_review"
            and descriptor.get("approval_plan_ready_for_review") is True
            and descriptor.get("transaction_plan_ready_for_review") is True,
            "details": {
                "status": descriptor.get("status"),
                "approval_plan_ready_for_review": descriptor.get("approval_plan_ready_for_review"),
                "transaction_plan_ready_for_review": descriptor.get("transaction_plan_ready_for_review"),
            },
        },
        {"name": "dispatch_approval_plan_has_no_blockers", "passed": not descriptor_blockers, "details": {"blockers": descriptor_blockers}},
        {"name": "nested_dispatch_approval_plan_available", "passed": bool(approval_plan), "details": {"approval_plan_id": approval_plan_id}},
        {
            "name": "nested_dispatch_approval_schema_matches",
            "passed": approval_plan.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-approval.v1",
            "details": {"schema_version": approval_plan.get("schema_version")},
        },
        {
            "name": "nested_dispatch_transaction_plan_schema_matches",
            "passed": transaction_plan.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-transaction-plan.v1",
            "details": {"schema_version": transaction_plan.get("schema_version")},
        },
        {
            "name": "dispatch_requires_explicit_review",
            "passed": approval_plan.get("requires_explicit_review") is True,
            "details": {"requires_explicit_review": approval_plan.get("requires_explicit_review")},
        },
        {
            "name": "dispatch_requires_approval_record",
            "passed": approval_plan.get("requires_approval_record") is True,
            "details": {"requires_approval_record": approval_plan.get("requires_approval_record")},
        },
        {
            "name": "dispatch_requires_transaction_journal",
            "passed": approval_plan.get("requires_transaction_journal") is True and transaction_plan.get("journal_required_before_dispatch") is True,
            "details": {
                "approval_requires_transaction_journal": approval_plan.get("requires_transaction_journal"),
                "journal_required_before_dispatch": transaction_plan.get("journal_required_before_dispatch"),
            },
        },
        {"name": "dispatch_approval_not_already_recorded", "passed": descriptor.get("approval_recorded") is not True and approval_plan.get("approval_recorded") is not True, "details": {"descriptor_approval_recorded": descriptor.get("approval_recorded"), "approval_plan_recorded": approval_plan.get("approval_recorded")}},
        {"name": "dispatch_transaction_not_started", "passed": descriptor.get("transaction_started") is not True and transaction_plan.get("transaction_started") is not True, "details": {"descriptor_transaction_started": descriptor.get("transaction_started"), "transaction_started": transaction_plan.get("transaction_started")}},
        {"name": "dispatch_journal_not_written", "passed": descriptor.get("journal_written") is not True and transaction_plan.get("journal_written_now") is not True, "details": {"descriptor_journal_written": descriptor.get("journal_written"), "journal_written_now": transaction_plan.get("journal_written_now")}},
        {"name": "dispatch_not_ready_now", "passed": descriptor.get("ready_to_dispatch_now") is not True and approval_plan.get("ready_to_dispatch_now") is not True and transaction_plan.get("ready_to_dispatch_now") is not True, "details": {"descriptor_ready_to_dispatch_now": descriptor.get("ready_to_dispatch_now"), "approval_ready_to_dispatch_now": approval_plan.get("ready_to_dispatch_now"), "transaction_ready_to_dispatch_now": transaction_plan.get("ready_to_dispatch_now")}},
        {"name": "dispatch_target_not_invoked", "passed": descriptor.get("will_invoke_dispatch_target") is not True and descriptor.get("will_invoke_next_action") is not True, "details": {"will_invoke_dispatch_target": descriptor.get("will_invoke_dispatch_target"), "will_invoke_next_action": descriptor.get("will_invoke_next_action")}},
        {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
        {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
        {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "decision_supported", "passed": decision in {"approved", "rejected", "needs_changes"}, "details": {"decision": decision}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_approval_record", "passed": mode != "apply" or bool(approve_approval_record), "details": {"approve_approval_record": approve_approval_record}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or approval_plan_id == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": approval_plan_id}},
        {"name": "expected_consumer_matches", "passed": not expected_consumer or selected_consumer == expected_consumer, "details": {"expected_consumer": expected_consumer, "selected_consumer": selected_consumer}},
        {"name": "expected_dispatch_surface_matches", "passed": not expected_dispatch_surface or dispatch_surface == expected_dispatch_surface, "details": {"expected_dispatch_surface": expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
        {"name": "expected_required_artifact_matches", "passed": not expected_required_artifact or required_artifact == expected_required_artifact, "details": {"expected_required_artifact": expected_required_artifact, "required_result_artifact": required_artifact}},
        {"name": "expected_plan_digest_matches", "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest, "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "descriptor_no_dispatch_side_effects", "passed": _source_map_followthrough_dispatch_no_side_effects(descriptor_policy), "details": descriptor_policy},
        {"name": "approval_plan_no_dispatch_side_effects", "passed": _source_map_followthrough_dispatch_no_side_effects(approval_policy), "details": approval_policy},
        {"name": "transaction_plan_no_dispatch_side_effects", "passed": _source_map_followthrough_dispatch_no_side_effects(transaction_policy), "details": transaction_policy},
    ]


def _source_map_followthrough_dispatch_no_side_effects(policy: dict[str, Any]) -> bool:
    return not any(
        _boolish(policy.get(key))
        for key in (
            "files_mutated",
            "artifacts_written_by_manager",
            "approval_artifact_written",
            "transaction_started",
            "journal_written",
            "apply_preflight_invoked",
            "fetch_source_map",
            "source_map_fetched",
            "browser_started",
            "cdp_command_sent",
            "debugger_execution_performed",
            "runtime_evaluated",
            "logpoint_installed",
            "hook_installed",
            "rebuild_executed",
            "surface_executor_invoked",
            "dispatch_target_invoked",
            "executor_invoked",
            "calls_mcp",
            "mobile_runtime_used",
        )
    )


def _source_map_followthrough_dispatch_approval_record_next_action(*, status: str, decision: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_source_map_followthrough_dispatch_approval_record_blockers"
    if status == "planned":
        return "review_source_map_followthrough_dispatch_approval_record_before_apply_write"
    if decision == "approved":
        return "review_source_map_followthrough_dispatch_transaction_preflight"
    return "revise_source_map_followthrough_dispatch_review_before_transaction"


def _source_map_selected_executor_approval_record_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "approval_record_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_approval_record": written,
        "approval_recorded": written,
        "ready_to_apply_now": False,
        "surface_executor_invoked": False,
        "debugger_execution_performed": False,
        "runtime_evaluated": False,
        "logpoint_installed": False,
        "hook_installed": False,
        "rebuild_executed": False,
        "fetch_source_map": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _source_map_followthrough_dispatch_approval_record_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "approval_record_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_approval_record": written,
        "approval_recorded": written,
        "ready_to_dispatch_now": False,
        "transaction_started": False,
        "journal_written": False,
        "dispatch_target_invoked": False,
        "executor_invoked": False,
        "debugger_execution_performed": False,
        "runtime_evaluated": False,
        "logpoint_installed": False,
        "hook_installed": False,
        "rebuild_executed": False,
        "fetch_source_map": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _source_map_selected_executor_approval_record_id(
    *,
    selected_action_id: str,
    selected_consumer: str,
    selected_gate: str,
    decision: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{selected_action_id}\0{selected_consumer}\0{selected_gate}\0{decision}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"source-map-selected-executor-approval-record:{digest}"


def _source_map_followthrough_dispatch_approval_record_id(
    *,
    approval_plan_id: str,
    selected_consumer: str,
    dispatch_surface: str,
    decision: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{approval_plan_id}\0{selected_consumer}\0{dispatch_surface}\0{decision}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"source-map-followthrough-dispatch-approval-record:{digest}"



def _heap_snapshot_retained_size_transaction_journal_checks(
    *,
    preflight: dict[str, Any],
    approval_summary: dict[str, Any],
    transaction_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    journal_contract: dict[str, Any],
    safety_gates: dict[str, Any],
    reviewer: str | None,
    mode: str,
    write_result: bool,
    approve_transaction_journal: bool,
    expected_approval_plan_id: str | None,
    expected_transaction_plan_id: str | None,
    expected_candidate_digest: str | None,
    expected_transaction_preflight_digest_sha256: str | None,
    preflight_digest: str | None,
    transaction_preflight_id: str,
    approval_plan_id: str,
    transaction_plan_id: str,
    candidate_digest: str,
    result_path: Path,
) -> list[dict[str, Any]]:
    blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
    policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
    return [
        {"name": "transaction_preflight_available", "passed": bool(preflight), "details": {"transaction_preflight_id": transaction_preflight_id}},
        {"name": "transaction_preflight_schema_matches", "passed": preflight.get("schema_version") == "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1", "details": {"schema_version": preflight.get("schema_version")}},
        {"name": "transaction_preflight_ready_for_review", "passed": preflight.get("status") == "ready_for_review", "details": {"status": preflight.get("status")}},
        {"name": "transaction_preflight_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
        {"name": "transaction_preflight_only", "passed": preflight.get("transaction_preflight_only") is True, "details": {"transaction_preflight_only": preflight.get("transaction_preflight_only")}},
        {"name": "retained_size_only", "passed": preflight.get("retained_size_only") is True, "details": {"retained_size_only": preflight.get("retained_size_only")}},
        {"name": "approval_record_verified", "passed": approval_summary.get("approval_recorded") is True and approval_summary.get("approved_for_execution") is True and safety_gates.get("approval_record_verified") is True, "details": {"approval_recorded": approval_summary.get("approval_recorded"), "approved_for_execution": approval_summary.get("approved_for_execution"), "gate": safety_gates.get("approval_record_verified")}},
        {"name": "approval_plan_id_present", "passed": bool(approval_plan_id), "details": {"approval_plan_id": approval_plan_id}},
        {"name": "transaction_plan_id_present", "passed": bool(transaction_plan_id), "details": {"transaction_plan_id": transaction_plan_id}},
        {"name": "candidate_digest_present", "passed": bool(candidate_digest), "details": {"candidate_digest": candidate_digest}},
        {"name": "journal_writer_contract_ready", "passed": journal_contract.get("ready_for_journal_review") is True or safety_gates.get("ready_to_write_journal") is True, "details": {"ready_for_journal_review": journal_contract.get("ready_for_journal_review"), "ready_to_write_journal": safety_gates.get("ready_to_write_journal")}},
        {"name": "journal_writer_contract_targets_expected_artifact", "passed": journal_contract.get("transaction_journal_artifact") in {None, "", "workspace/heap-snapshot-retained-size-executor-journal.json"}, "details": {"transaction_journal_artifact": journal_contract.get("transaction_journal_artifact")}},
        {"name": "transaction_not_already_started", "passed": preflight.get("transaction_started") is not True and transaction_summary.get("transaction_started") is not True and policy.get("transaction_started") is not True, "details": {"transaction_started": preflight.get("transaction_started"), "summary_transaction_started": transaction_summary.get("transaction_started"), "policy_transaction_started": policy.get("transaction_started")}},
        {"name": "journal_not_already_written", "passed": preflight.get("journal_written") is not True and transaction_summary.get("journal_written") is not True and policy.get("journal_written") is not True and policy.get("journal_written_now") is not True, "details": {"journal_written": preflight.get("journal_written"), "summary_journal_written": transaction_summary.get("journal_written"), "policy_journal_written": policy.get("journal_written")}},
        {"name": "bounded_gate_not_written", "passed": preflight.get("bounded_executor_gate_written") is not True and transaction_summary.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"bounded_executor_gate_written": preflight.get("bounded_executor_gate_written"), "summary_bounded_executor_gate_written": transaction_summary.get("bounded_executor_gate_written"), "policy_bounded_executor_gate_written": policy.get("bounded_executor_gate_written")}},
        {"name": "executor_not_invoked", "passed": preflight.get("executor_invoked") is not True and transaction_summary.get("executor_invoked") is not True and policy.get("executor_invoked") is not True and policy.get("future_executor_invoked") is not True, "details": {"executor_invoked": preflight.get("executor_invoked"), "summary_executor_invoked": transaction_summary.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked")}},
        {"name": "retained_transaction_preflight_no_heap_side_effects", "passed": _heap_snapshot_retained_size_transaction_preflight_no_side_effects(preflight, policy), "details": policy},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_transaction_journal", "passed": mode != "apply" or bool(approve_transaction_journal), "details": {"approve_transaction_journal": approve_transaction_journal}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or approval_plan_id == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": approval_plan_id}},
        {"name": "expected_transaction_plan_id_matches", "passed": not expected_transaction_plan_id or transaction_plan_id == expected_transaction_plan_id, "details": {"expected_transaction_plan_id": expected_transaction_plan_id, "transaction_plan_id": transaction_plan_id}},
        {"name": "expected_candidate_digest_matches", "passed": not expected_candidate_digest or candidate_digest == expected_candidate_digest, "details": {"expected_candidate_digest": expected_candidate_digest, "candidate_digest": candidate_digest}},
        {"name": "expected_transaction_preflight_digest_matches", "passed": not expected_transaction_preflight_digest_sha256 or expected_transaction_preflight_digest_sha256 == preflight_digest, "details": {"expected_transaction_preflight_digest_sha256": expected_transaction_preflight_digest_sha256, "transaction_preflight_digest_sha256": preflight_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
    ]


def _heap_snapshot_retained_size_transaction_preflight_no_side_effects(preflight: dict[str, Any], policy: dict[str, Any]) -> bool:
    return not any(
        _boolish(preflight.get(key)) or _boolish(policy.get(key))
        for key in (
            "files_mutated",
            "transaction_started",
            "journal_written",
            "journal_written_now",
            "bounded_executor_gate_written",
            "executor_invoked",
            "future_executor_invoked",
            "browser_started",
            "provider_factory_invoked",
            "provider_availability_checked",
            "cdp_command_sent",
            "heap_profiler_enabled",
            "heap_snapshot_collected",
            "heap_snapshot_diff_computed",
            "heap_diff_computed",
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "retained_size_proven",
            "path_to_root_computed",
            "complete_heap_traversal",
            "runtime_evaluated",
            "javascript_evaluated",
            "calls_mcp",
            "mobile_runtime_used",
        )
    )


def _heap_snapshot_retained_size_transaction_journal_next_action(*, status: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_heap_snapshot_retained_size_transaction_journal_blockers"
    if status == "planned":
        return "review_heap_snapshot_retained_size_transaction_journal_before_apply_write"
    return "review_heap_snapshot_retained_size_bounded_gate"


def _heap_snapshot_retained_size_transaction_journal_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "transaction_journal_writer": True,
        "retained_size_only": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_transaction_journal": written,
        "transaction_started": written,
        "journal_written": written,
        "bounded_executor_gate_written": False,
        "ready_to_execute_now": False,
        "executor_invoked": False,
        "future_executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "complete_heap_traversal": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _heap_snapshot_retained_size_transaction_preflight_id(preflight_digest: str) -> str:
    return f"heap-snapshot-retained-size-transaction-preflight:{preflight_digest[:16]}" if preflight_digest else ""


def _heap_snapshot_retained_size_transaction_journal_id(
    *,
    transaction_preflight_id: str,
    transaction_plan_id: str,
    candidate_digest: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{transaction_preflight_id}\0{transaction_plan_id}\0{candidate_digest}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"heap-snapshot-retained-size-transaction-journal:{digest}"


def _heap_snapshot_diff_executor_transaction_journal_checks(
    *,
    preflight: dict[str, Any],
    approval_summary: dict[str, Any],
    transaction_summary: dict[str, Any],
    journal_contract: dict[str, Any],
    safety_gates: dict[str, Any],
    reviewer: str | None,
    mode: str,
    write_result: bool,
    approve_transaction_journal: bool,
    expected_approval_scope: str | None,
    expected_transaction_id: str | None,
    expected_idempotency_key: str | None,
    expected_transaction_preflight_digest_sha256: str | None,
    preflight_digest: str | None,
    transaction_preflight_id: str,
    approval_scope: str,
    transaction_id: str,
    idempotency_key: str,
    result_path: Path,
) -> list[dict[str, Any]]:
    blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
    policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
    return [
        {"name": "transaction_preflight_available", "passed": bool(preflight), "details": {"transaction_preflight_id": transaction_preflight_id}},
        {"name": "transaction_preflight_schema_matches", "passed": preflight.get("schema_version") == "reverse-deepagent.heap-snapshot-diff-executor-transaction-preflight.v1", "details": {"schema_version": preflight.get("schema_version")}},
        {"name": "transaction_preflight_ready_for_review", "passed": preflight.get("status") == "ready_for_review", "details": {"status": preflight.get("status")}},
        {"name": "transaction_preflight_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
        {"name": "transaction_preflight_only", "passed": preflight.get("transaction_preflight_only") is True, "details": {"transaction_preflight_only": preflight.get("transaction_preflight_only")}},
        {"name": "approval_record_verified", "passed": approval_summary.get("approval_recorded") is True and approval_summary.get("approved_for_execution") is True and safety_gates.get("approval_record_verified") is True, "details": {"approval_recorded": approval_summary.get("approval_recorded"), "approved_for_execution": approval_summary.get("approved_for_execution"), "gate": safety_gates.get("approval_record_verified")}},
        {"name": "approval_scope_supported", "passed": approval_scope == "heap-snapshot-diff-executor", "details": {"approval_scope": approval_scope}},
        {"name": "transaction_id_present", "passed": bool(transaction_id), "details": {"transaction_id": transaction_id}},
        {"name": "idempotency_key_present", "passed": bool(idempotency_key), "details": {"idempotency_key": idempotency_key}},
        {"name": "journal_writer_contract_ready", "passed": journal_contract.get("ready_for_journal_review") is True or safety_gates.get("ready_to_write_journal") is True, "details": {"ready_for_journal_review": journal_contract.get("ready_for_journal_review"), "ready_to_write_journal": safety_gates.get("ready_to_write_journal")}},
        {"name": "journal_writer_contract_targets_expected_artifact", "passed": journal_contract.get("transaction_journal_artifact") in {None, "", "workspace/heap-snapshot-diff-executor-journal.json"}, "details": {"transaction_journal_artifact": journal_contract.get("transaction_journal_artifact")}},
        {"name": "transaction_not_already_started", "passed": preflight.get("transaction_started") is not True and transaction_summary.get("transaction_started") is not True and policy.get("transaction_started") is not True, "details": {"transaction_started": preflight.get("transaction_started"), "summary_transaction_started": transaction_summary.get("transaction_started"), "policy_transaction_started": policy.get("transaction_started")}},
        {"name": "journal_not_already_written", "passed": preflight.get("journal_written") is not True and transaction_summary.get("journal_written") is not True and policy.get("journal_written") is not True and policy.get("journal_written_now") is not True, "details": {"journal_written": preflight.get("journal_written"), "summary_journal_written": transaction_summary.get("journal_written"), "policy_journal_written": policy.get("journal_written"), "policy_journal_written_now": policy.get("journal_written_now")}},
        {"name": "bounded_gate_not_written", "passed": preflight.get("bounded_executor_gate_written") is not True and transaction_summary.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"bounded_executor_gate_written": preflight.get("bounded_executor_gate_written"), "summary_bounded_executor_gate_written": transaction_summary.get("bounded_executor_gate_written"), "policy_bounded_executor_gate_written": policy.get("bounded_executor_gate_written")}},
        {"name": "executor_not_invoked", "passed": preflight.get("executor_invoked") is not True and transaction_summary.get("executor_invoked") is not True and policy.get("executor_invoked") is not True, "details": {"executor_invoked": preflight.get("executor_invoked"), "summary_executor_invoked": transaction_summary.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked")}},
        {"name": "raw_heap_not_loaded", "passed": preflight.get("raw_heap_loaded") is not True and policy.get("raw_heap_loaded") is not True, "details": {"raw_heap_loaded": preflight.get("raw_heap_loaded"), "policy_raw_heap_loaded": policy.get("raw_heap_loaded")}},
        {"name": "raw_heap_not_parsed", "passed": preflight.get("raw_heap_parsed") is not True and policy.get("raw_heap_parsed") is not True, "details": {"raw_heap_parsed": preflight.get("raw_heap_parsed"), "policy_raw_heap_parsed": policy.get("raw_heap_parsed")}},
        {"name": "raw_heap_not_exported", "passed": preflight.get("raw_heap_exported") is not True and policy.get("raw_heap_exported") is not True, "details": {"raw_heap_exported": preflight.get("raw_heap_exported"), "policy_raw_heap_exported": policy.get("raw_heap_exported")}},
        {"name": "heap_diff_not_computed", "passed": preflight.get("heap_diff_computed") is not True and preflight.get("heap_snapshot_diff_computed") is not True and policy.get("heap_diff_computed") is not True and policy.get("heap_snapshot_diff_computed") is not True, "details": {"heap_diff_computed": preflight.get("heap_diff_computed"), "heap_snapshot_diff_computed": preflight.get("heap_snapshot_diff_computed"), "policy_heap_diff_computed": policy.get("heap_diff_computed")}},
        {"name": "complete_heap_traversal_not_claimed", "passed": preflight.get("complete_heap_traversal_claimed") is not True and policy.get("complete_heap_traversal") is not True, "details": {"complete_heap_traversal_claimed": preflight.get("complete_heap_traversal_claimed"), "policy_complete_heap_traversal": policy.get("complete_heap_traversal")}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_transaction_journal", "passed": mode != "apply" or bool(approve_transaction_journal), "details": {"approve_transaction_journal": approve_transaction_journal}},
        {"name": "expected_approval_scope_matches", "passed": not expected_approval_scope or approval_scope == expected_approval_scope, "details": {"expected_approval_scope": expected_approval_scope, "approval_scope": approval_scope}},
        {"name": "expected_transaction_id_matches", "passed": not expected_transaction_id or transaction_id == expected_transaction_id, "details": {"expected_transaction_id": expected_transaction_id, "transaction_id": transaction_id}},
        {"name": "expected_idempotency_key_matches", "passed": not expected_idempotency_key or idempotency_key == expected_idempotency_key, "details": {"expected_idempotency_key": expected_idempotency_key, "idempotency_key": idempotency_key}},
        {"name": "expected_transaction_preflight_digest_matches", "passed": not expected_transaction_preflight_digest_sha256 or expected_transaction_preflight_digest_sha256 == preflight_digest, "details": {"expected_transaction_preflight_digest_sha256": expected_transaction_preflight_digest_sha256, "transaction_preflight_digest_sha256": preflight_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "transaction_preflight_no_heap_side_effects", "passed": _heap_snapshot_diff_executor_transaction_preflight_no_side_effects(policy), "details": policy},
    ]


def _heap_snapshot_diff_executor_transaction_preflight_no_side_effects(policy: dict[str, Any]) -> bool:
    return not any(
        _boolish(policy.get(key))
        for key in (
            "files_mutated",
            "transaction_started",
            "journal_written",
            "journal_written_now",
            "bounded_executor_gate_written",
            "executor_invoked",
            "browser_started",
            "provider_factory_invoked",
            "provider_availability_checked",
            "cdp_command_sent",
            "heap_profiler_enabled",
            "heap_snapshot_collected",
            "heap_snapshot_diff_computed",
            "heap_diff_computed",
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "complete_heap_traversal",
            "runtime_evaluated",
            "javascript_evaluated",
            "calls_mcp",
            "mobile_runtime_used",
        )
    )


def _heap_snapshot_diff_executor_transaction_journal_next_action(*, status: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_heap_snapshot_diff_executor_transaction_journal_blockers"
    if status == "planned":
        return "review_heap_snapshot_diff_executor_transaction_journal_before_apply_write"
    return "review_heap_snapshot_diff_executor_bounded_gate"


def _heap_snapshot_diff_executor_transaction_journal_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "transaction_journal_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_transaction_journal": written,
        "transaction_started": written,
        "journal_written": written,
        "bounded_executor_gate_written": False,
        "ready_to_execute_now": False,
        "executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "complete_heap_traversal": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _heap_snapshot_diff_executor_transaction_preflight_id(preflight_digest: str) -> str:
    return f"heap-snapshot-diff-executor-transaction-preflight:{preflight_digest[:16]}" if preflight_digest else ""


def _heap_snapshot_diff_executor_transaction_journal_id(
    *,
    transaction_preflight_id: str,
    transaction_id: str,
    idempotency_key: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{transaction_preflight_id}\0{transaction_id}\0{idempotency_key}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"heap-snapshot-diff-executor-transaction-journal:{digest}"


def _source_map_followthrough_dispatch_transaction_journal_checks(
    *,
    preflight: dict[str, Any],
    transaction_preflight_gate: dict[str, Any],
    journal_writer_gate: dict[str, Any],
    reviewer: str | None,
    mode: str,
    write_result: bool,
    approve_transaction_journal: bool,
    expected_transaction_preflight_id: str | None,
    expected_approval_record_id: str | None,
    expected_transaction_plan_id: str | None,
    expected_approval_plan_id: str | None,
    expected_consumer: str | None,
    expected_dispatch_surface: str | None,
    expected_required_artifact: str | None,
    expected_preflight_digest_sha256: str | None,
    preflight_digest: str | None,
    transaction_preflight_id: str,
    approval_record_id: str,
    transaction_plan_id: str,
    approval_plan_id: str,
    selected_consumer: str,
    dispatch_surface: str,
    required_artifact: str,
    result_path: Path,
) -> list[dict[str, Any]]:
    blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
    policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
    gate_policy = transaction_preflight_gate.get("side_effect_policy") if isinstance(transaction_preflight_gate.get("side_effect_policy"), dict) else {}
    return [
        {"name": "transaction_preflight_available", "passed": bool(preflight), "details": {"transaction_preflight_id": transaction_preflight_id}},
        {"name": "transaction_preflight_schema_matches", "passed": preflight.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1", "details": {"schema_version": preflight.get("schema_version")}},
        {"name": "transaction_preflight_ready_for_review", "passed": preflight.get("status") == "ready_for_review" and preflight.get("transaction_preflight_ready_for_review") is True and preflight.get("journal_writer_gate_ready_for_review") is True, "details": {"status": preflight.get("status"), "transaction_preflight_ready_for_review": preflight.get("transaction_preflight_ready_for_review"), "journal_writer_gate_ready_for_review": preflight.get("journal_writer_gate_ready_for_review")}},
        {"name": "transaction_preflight_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
        {"name": "transaction_preflight_gate_schema_matches", "passed": transaction_preflight_gate.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight-gate.v1", "details": {"schema_version": transaction_preflight_gate.get("schema_version")}},
        {"name": "journal_writer_gate_schema_matches", "passed": journal_writer_gate.get("schema_version") == "reverse-deepagent.source-map-followthrough-dispatch-journal-writer-gate.v1", "details": {"schema_version": journal_writer_gate.get("schema_version")}},
        {"name": "approval_record_verified", "passed": preflight.get("approval_record_verified") is True and transaction_preflight_gate.get("approval_record_verified") is True, "details": {"approval_record_verified": preflight.get("approval_record_verified"), "gate_approval_record_verified": transaction_preflight_gate.get("approval_record_verified")}},
        {"name": "transaction_plan_verified", "passed": preflight.get("transaction_plan_verified") is True, "details": {"transaction_plan_verified": preflight.get("transaction_plan_verified")}},
        {"name": "journal_writer_gate_targets_expected_artifact", "passed": journal_writer_gate.get("journal_artifact") in {None, "", "workspace/source-map-followthrough-dispatch-transaction-journal.json"}, "details": {"journal_artifact": journal_writer_gate.get("journal_artifact")}},
        {"name": "journal_writer_gate_requires_explicit_approval", "passed": journal_writer_gate.get("requires_explicit_journal_write_approval") is True, "details": {"requires_explicit_journal_write_approval": journal_writer_gate.get("requires_explicit_journal_write_approval")}},
        {"name": "journal_required_before_dispatch", "passed": journal_writer_gate.get("journal_required_before_dispatch") is True, "details": {"journal_required_before_dispatch": journal_writer_gate.get("journal_required_before_dispatch")}},
        {"name": "approval_record_approved_for_dispatch", "passed": journal_writer_gate.get("approval_recorded") is True and journal_writer_gate.get("approved_for_dispatch") is True, "details": {"approval_recorded": journal_writer_gate.get("approval_recorded"), "approved_for_dispatch": journal_writer_gate.get("approved_for_dispatch")}},
        {"name": "transaction_not_already_started", "passed": preflight.get("transaction_started") is not True and transaction_preflight_gate.get("transaction_started") is not True, "details": {"transaction_started": preflight.get("transaction_started"), "gate_transaction_started": transaction_preflight_gate.get("transaction_started")}},
        {"name": "journal_not_already_written", "passed": preflight.get("journal_written") is not True and transaction_preflight_gate.get("journal_written") is not True and journal_writer_gate.get("journal_written_now") is not True, "details": {"journal_written": preflight.get("journal_written"), "gate_journal_written": transaction_preflight_gate.get("journal_written"), "journal_written_now": journal_writer_gate.get("journal_written_now")}},
        {"name": "dispatch_not_ready_now", "passed": preflight.get("ready_to_dispatch_now") is not True, "details": {"ready_to_dispatch_now": preflight.get("ready_to_dispatch_now")}},
        {"name": "dispatch_target_not_invoked", "passed": preflight.get("will_invoke_dispatch_target") is not True and transaction_preflight_gate.get("dispatch_target_invoked") is not True and journal_writer_gate.get("dispatch_target_invoked") is not True, "details": {"will_invoke_dispatch_target": preflight.get("will_invoke_dispatch_target"), "gate_dispatch_target_invoked": transaction_preflight_gate.get("dispatch_target_invoked"), "journal_dispatch_target_invoked": journal_writer_gate.get("dispatch_target_invoked")}},
        {"name": "executor_not_invoked", "passed": preflight.get("will_invoke_next_action") is not True and transaction_preflight_gate.get("executor_invoked") is not True and journal_writer_gate.get("executor_invoked") is not True, "details": {"will_invoke_next_action": preflight.get("will_invoke_next_action"), "gate_executor_invoked": transaction_preflight_gate.get("executor_invoked"), "journal_executor_invoked": journal_writer_gate.get("executor_invoked")}},
        {"name": "selected_consumer_supported", "passed": selected_consumer in {"debugger", "source-logpoint", "rebuild", "hook"}, "details": {"selected_consumer": selected_consumer}},
        {"name": "dispatch_surface_present", "passed": bool(dispatch_surface), "details": {"dispatch_surface": dispatch_surface}},
        {"name": "required_result_artifact_present", "passed": bool(required_artifact), "details": {"required_result_artifact": required_artifact}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_transaction_journal", "passed": mode != "apply" or bool(approve_transaction_journal), "details": {"approve_transaction_journal": approve_transaction_journal}},
        {"name": "expected_transaction_preflight_id_matches", "passed": not expected_transaction_preflight_id or transaction_preflight_id == expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": expected_transaction_preflight_id, "transaction_preflight_id": transaction_preflight_id}},
        {"name": "expected_approval_record_id_matches", "passed": not expected_approval_record_id or approval_record_id == expected_approval_record_id, "details": {"expected_approval_record_id": expected_approval_record_id, "approval_record_id": approval_record_id}},
        {"name": "expected_transaction_plan_id_matches", "passed": not expected_transaction_plan_id or transaction_plan_id == expected_transaction_plan_id, "details": {"expected_transaction_plan_id": expected_transaction_plan_id, "transaction_plan_id": transaction_plan_id}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or approval_plan_id == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": approval_plan_id}},
        {"name": "expected_consumer_matches", "passed": not expected_consumer or selected_consumer == expected_consumer, "details": {"expected_consumer": expected_consumer, "selected_consumer": selected_consumer}},
        {"name": "expected_dispatch_surface_matches", "passed": not expected_dispatch_surface or dispatch_surface == expected_dispatch_surface, "details": {"expected_dispatch_surface": expected_dispatch_surface, "dispatch_surface": dispatch_surface}},
        {"name": "expected_required_artifact_matches", "passed": not expected_required_artifact or required_artifact == expected_required_artifact, "details": {"expected_required_artifact": expected_required_artifact, "required_result_artifact": required_artifact}},
        {"name": "expected_preflight_digest_matches", "passed": not expected_preflight_digest_sha256 or expected_preflight_digest_sha256 == preflight_digest, "details": {"expected_preflight_digest_sha256": expected_preflight_digest_sha256, "transaction_preflight_digest_sha256": preflight_digest}},
        {"name": "result_path_not_already_written", "passed": mode != "apply" or not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
        {"name": "transaction_preflight_no_dispatch_side_effects", "passed": _source_map_followthrough_dispatch_no_side_effects(policy), "details": policy},
        {"name": "transaction_preflight_gate_no_dispatch_side_effects", "passed": _source_map_followthrough_dispatch_no_side_effects(gate_policy), "details": gate_policy},
    ]


def _source_map_followthrough_dispatch_transaction_journal_next_action(*, status: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_source_map_followthrough_dispatch_transaction_journal_blockers"
    if status == "planned":
        return "review_source_map_followthrough_dispatch_transaction_journal_before_apply_write"
    return "review_source_map_followthrough_dispatch_bounded_executor_gate"


def _source_map_followthrough_dispatch_transaction_journal_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "transaction_journal_writer": True,
        "dry_run_is_read_only": True,
        "files_mutated": written,
        "artifacts_written": written,
        "writes_transaction_journal": written,
        "transaction_started": written,
        "journal_written": written,
        "ready_to_dispatch_now": False,
        "dispatch_target_invoked": False,
        "executor_invoked": False,
        "debugger_execution_performed": False,
        "runtime_evaluated": False,
        "logpoint_installed": False,
        "hook_installed": False,
        "rebuild_executed": False,
        "fetch_source_map": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _source_map_followthrough_dispatch_transaction_preflight_id(preflight_digest: str) -> str:
    return f"source-map-followthrough-dispatch-transaction-preflight:{preflight_digest[:16]}" if preflight_digest else ""


def _source_map_followthrough_dispatch_transaction_journal_id(
    *,
    transaction_preflight_id: str,
    approval_record_id: str,
    transaction_plan_id: str,
    reviewer: str | None,
    created_at: str,
) -> str:
    digest = hashlib.sha256(f"{transaction_preflight_id}\0{approval_record_id}\0{transaction_plan_id}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"source-map-followthrough-dispatch-transaction-journal:{digest}"


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
    if "source_map_followthrough_chain_readiness_blocked" in blockers:
        return "inspect_source_map_followthrough_chain_readiness_failure"
    if "source_map_followthrough_one_step_plan_blocked" in blockers:
        return "inspect_source_map_followthrough_one_step_plan_failure"
    if "source_map_followthrough_dispatch_preflight_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatch_preflight_failure"
    if "source_map_followthrough_dispatch_approval_plan_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatch_approval_plan_failure"
    if "source_map_followthrough_dispatch_approval_record_blocked" in blockers:
        return "provide_ready_source_map_followthrough_dispatch_approval_plan_descriptor"
    if "source_map_followthrough_dispatch_transaction_preflight_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatch_transaction_preflight_failure"
    if "source_map_followthrough_dispatch_transaction_journal_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatch_transaction_journal_failure"
    if "source_map_followthrough_dispatch_bounded_executor_gate_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatch_bounded_executor_gate_failure"
    if "source_map_followthrough_dispatcher_handoff_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatcher_handoff_failure"
    if "source_map_followthrough_dispatcher_apply_preflight_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatcher_apply_preflight_failure"
    if "source_map_followthrough_dispatcher_result_blocked" in blockers:
        return "inspect_source_map_followthrough_dispatcher_result_failure"
    if "source_map_followthrough_surface_selection_blocked" in blockers:
        return "provide_ready_source_map_followthrough_review_descriptor"
    if "source_map_selected_executor_input_review_blocked" in blockers:
        return "provide_ready_source_map_followthrough_surface_selection_descriptor"
    if "source_map_selected_executor_approval_plan_blocked" in blockers:
        return "provide_ready_source_map_selected_executor_input_review_descriptor"
    if "source_map_selected_executor_approval_record_blocked" in blockers:
        return "provide_ready_source_map_selected_executor_approval_plan_descriptor"
    if "source_map_selected_executor_apply_preflight_blocked" in blockers:
        return "provide_matching_source_map_selected_executor_approval_plan_and_record"
    if "source_map_selected_executor_application_handoff_blocked" in blockers:
        return "inspect_source_map_selected_executor_application_handoff_failure"
    if "source_map_selected_executor_result_checkpoint_blocked" in blockers:
        return "inspect_source_map_selected_executor_result_checkpoint_failure"
    if "source_map_followthrough_completion_checkpoint_blocked" in blockers:
        return "inspect_source_map_followthrough_completion_checkpoint_failure"
    if "source_map_terminal_review_package_blocked" in blockers:
        return "inspect_source_map_terminal_review_package_failure"
    if "source_map_terminal_review_closure_checkpoint_blocked" in blockers:
        return "inspect_source_map_terminal_review_closure_checkpoint_failure"
    if "source_map_terminal_review_final_audit_blocked" in blockers:
        return "inspect_source_map_terminal_review_final_audit_failure"
    if "source_map_source_logpoint_install_result_blocked" in blockers:
        return "inspect_source_map_source_logpoint_install_failure"
    if "source_map_hook_candidates_blocked" in blockers:
        return "inspect_source_map_hook_candidate_refinement_failure"
    if "source_map_hook_candidate_selection_blocked" in blockers:
        return "inspect_source_map_hook_candidate_selection_failure"
    if "source_map_hook_candidate_selection_unexpected_side_effect" in blockers:
        return "inspect_source_map_hook_candidate_selection_side_effects"
    if "source_map_hook_install_result_blocked" in blockers:
        return "inspect_source_map_hook_install_failure"
    if "source_map_rebuild_result_blocked" in blockers:
        return "inspect_source_map_rebuild_metadata_application_failure"
    if "source_map_rebuild_generation_result_blocked" in blockers:
        return "inspect_source_map_rebuild_generation_failure"
    if "object_graph_diff_blocked" in blockers:
        return "provide_before_and_after_object_graph_snapshots"
    if "runtime_object_graph_diff_blocked" in blockers:
        return "provide_supported_runtime_object_root_path"
    if "heap_snapshot_readiness_blocked" in blockers:
        return "provide_cdp_heap_profiler_capability_evidence"
    if "heap_snapshot_collect_blocked" in blockers:
        return "resolve_heap_snapshot_collect_blockers"
    if "heap_snapshot_diff_readiness_blocked" in blockers:
        return "provide_two_reviewed_heap_snapshot_collect_descriptors"
    if "heap_snapshot_diff_executor_preflight_blocked" in blockers:
        return "resolve_heap_snapshot_diff_executor_preflight_blockers"
    if "heap_snapshot_diff_executor_approval_plan_blocked" in blockers:
        return "resolve_heap_snapshot_diff_executor_approval_plan_blockers"
    if "heap_snapshot_diff_executor_approval_record_blocked" in blockers:
        return "provide_ready_heap_snapshot_diff_executor_approval_plan_descriptor"
    if "heap_snapshot_diff_executor_transaction_preflight_blocked" in blockers:
        return "resolve_heap_snapshot_diff_executor_transaction_preflight_blockers"
    if "heap_snapshot_diff_executor_transaction_journal_blocked" in blockers:
        return "inspect_heap_snapshot_diff_executor_transaction_journal_failure"
    if "heap_snapshot_diff_executor_bounded_gate_blocked" in blockers:
        return "provide_written_heap_snapshot_diff_executor_transaction_journal"
    if "heap_snapshot_diff_executor_result_blocked" in blockers:
        return "resolve_heap_snapshot_diff_executor_result_blockers"
    if "heap_snapshot_diff_followup_checkpoint_blocked" in blockers:
        return "resolve_heap_snapshot_diff_followup_checkpoint_blockers"
    if "heap_snapshot_diff_selected_analysis_input_preflight_blocked" in blockers:
        return "resolve_heap_snapshot_diff_selected_analysis_input_preflight_blockers"
    if "heap_snapshot_constructor_growth_drilldown_blocked" in blockers:
        return "resolve_heap_snapshot_constructor_growth_drilldown_blockers"
    if "heap_snapshot_constructor_growth_drilldown_analysis_blocked" in blockers:
        return "resolve_heap_snapshot_constructor_growth_drilldown_analysis_blockers"
    if "heap_snapshot_automatic_followup_plan_blocked" in blockers:
        return "resolve_heap_snapshot_automatic_followup_plan_blockers"
    if "heap_snapshot_retained_size_proof_plan_blocked" in blockers:
        return "resolve_heap_snapshot_retained_size_proof_plan_blockers"
    if "heap_snapshot_path_to_root_proof_plan_blocked" in blockers:
        return "resolve_heap_snapshot_path_to_root_proof_plan_blockers"
    if "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blocked" in blockers:
        return "resolve_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blockers"
    if "heap_snapshot_retained_path_preflight_blocked" in blockers:
        return "resolve_heap_snapshot_retained_path_preflight_blockers"
    if "heap_snapshot_retained_size_input_review_blocked" in blockers:
        return "resolve_heap_snapshot_retained_size_input_review_blockers"
    if "heap_snapshot_retained_size_approval_plan_blocked" in blockers:
        return "resolve_heap_snapshot_retained_size_approval_plan_blockers"
    if "heap_snapshot_retained_size_approval_record_blocked" in blockers:
        return "provide_ready_heap_snapshot_retained_size_approval_plan_descriptor"
    if "heap_snapshot_retained_size_transaction_preflight_blocked" in blockers:
        return "resolve_heap_snapshot_retained_size_transaction_preflight_blockers"
    if "heap_snapshot_retained_size_transaction_journal_blocked" in blockers:
        return "inspect_heap_snapshot_retained_size_transaction_journal_failure"
    if "heap_snapshot_retained_size_bounded_gate_blocked" in blockers:
        return "provide_written_heap_snapshot_retained_size_transaction_journal"
    if "heap_snapshot_retained_size_analysis_blocked" in blockers:
        return "resolve_heap_snapshot_retained_size_analysis_blockers"
    if "heap_snapshot_path_to_root_analysis_blocked" in blockers:
        return "resolve_heap_snapshot_path_to_root_analysis_blockers"
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
    if "source_map_followthrough_dispatch_approval_plan_requires_review" in warnings:
        return "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval"
    if "source_map_followthrough_dispatch_approval_record_ready_for_transaction_preflight" in warnings:
        return "review_source_map_followthrough_dispatch_transaction_preflight"
    if "source_map_followthrough_dispatch_transaction_preflight_ready_for_journal_writer" in warnings:
        return "review_source_map_followthrough_dispatch_transaction_journal_writer"
    if "source_map_followthrough_dispatch_transaction_journal_ready_for_bounded_gate" in warnings:
        return "review_source_map_followthrough_dispatch_bounded_executor_gate"
    if "source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff" in warnings:
        return "review_source_map_followthrough_dispatcher_handoff"
    if "source_map_followthrough_dispatcher_handoff_ready_for_apply_preflight_review" in warnings:
        return "review_source_map_followthrough_dispatcher_apply_preflight"
    if "source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp" in warnings:
        return "review_source_map_followthrough_dispatcher_mvp"
    if "source_map_followthrough_dispatcher_result_requires_review_approval" in warnings:
        return "approve_source_map_followthrough_dispatcher_mvp"
    if "source_map_followthrough_dispatcher_result_ready_for_selected_executor_apply_preflight" in warnings:
        return "review_source_map_selected_executor_apply_preflight"
    if "source_map_followthrough_dispatch_preflight_requires_review" in warnings:
        return "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call"
    if "source_map_followthrough_one_step_plan_requires_review" in warnings:
        return "review_source_map_followthrough_one_step_plan_before_next_action"
    if "source_map_followthrough_chain_readiness_requires_next_review" in warnings:
        return "review_source_map_followthrough_chain_readiness_next_action"
    if "source_map_followthrough_surface_selection_requires_review" in warnings:
        return "review_selected_source_map_followthrough_surface_before_execution"
    if "source_map_selected_executor_input_review_requires_review" in warnings:
        return "review_source_map_selected_executor_input_before_surface_execution"
    if "source_map_selected_executor_approval_plan_requires_review" in warnings:
        return "review_source_map_selected_executor_approval_plan_before_apply"
    if "source_map_selected_executor_approval_record_ready_for_apply_preflight" in warnings:
        return "review_source_map_selected_executor_apply_preflight"
    if "source_map_selected_executor_application_handoff_ready_for_application_review" in warnings:
        return "review_source_map_selected_executor_application"
    if "source_map_selected_executor_result_checkpoint_ready_for_followthrough_review" in warnings:
        return "review_source_map_selected_executor_result_checkpoint"
    if "source_map_followthrough_completion_checkpoint_ready_for_completion_review" in warnings:
        return "review_source_map_followthrough_completion_checkpoint"
    if "source_map_terminal_review_package_ready_for_review" in warnings:
        return "review_source_map_terminal_review_package"
    if "source_map_terminal_review_closure_checkpoint_ready_for_closure_review" in warnings:
        return "review_source_map_terminal_review_closure_checkpoint"
    if "source_map_terminal_review_final_audit_ready_for_review" in warnings:
        return "review_source_map_terminal_review_final_audit"
    if "source_map_selected_executor_apply_preflight_ready_for_executor_review" in warnings:
        return "review_source_map_selected_executor_application_handoff"
    if "source_map_source_logpoint_install_result_requires_timeline_review" in warnings:
        return "inspect_source_map_source_logpoint_events"
    if "source_map_hook_candidates_require_review" in warnings:
        return "review_source_map_hook_candidates_before_selected_hook_install"
    if "source_map_hook_candidate_selection_requires_input_review" in warnings:
        return "review_selected_source_map_hook_candidate_input"
    if "source_map_hook_install_result_requires_timeline_review" in warnings:
        return "inspect_source_map_hook_events"
    if "source_map_rebuild_generation_result_requires_rebuild_artifact_review" in warnings:
        return "review_generated_rebuild_bundle_before_delivery"
    if "source_map_rebuild_result_requires_rebuild_review" in warnings:
        return "review_source_map_rebuild_metadata_before_rebuild_generation"
    if "object_graph_diff_requires_review" in warnings:
        return "review_object_graph_diff_before_hook_or_replay"
    if "runtime_object_graph_diff_requires_review" in warnings:
        return "review_runtime_object_graph_diff_before_hook_or_replay"
    if "heap_snapshot_readiness_requires_review" in warnings:
        return "review_heap_snapshot_readiness_before_collection"
    if "heap_snapshot_collect_requires_review" in warnings:
        return "review_heap_snapshot_collect_before_heap_diff"
    if "heap_snapshot_diff_readiness_requires_review" in warnings:
        return "review_heap_snapshot_diff_readiness_before_diff_executor"
    if "heap_snapshot_diff_executor_preflight_requires_review" in warnings:
        return "review_heap_snapshot_diff_executor_preflight_before_implementation"
    if "heap_snapshot_diff_executor_approval_plan_requires_review" in warnings:
        return "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval"
    if "heap_snapshot_diff_executor_approval_record_ready_for_transaction_preflight" in warnings:
        return "review_heap_snapshot_diff_executor_transaction_preflight"
    if "heap_snapshot_diff_executor_transaction_preflight_ready_for_journal_writer" in warnings:
        return "review_heap_snapshot_diff_executor_transaction_journal_writer"
    if "heap_snapshot_diff_executor_transaction_journal_ready_for_bounded_gate" in warnings:
        return "review_heap_snapshot_diff_executor_bounded_gate"
    if "heap_snapshot_diff_executor_bounded_gate_ready_for_executor_review" in warnings:
        return "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp"
    if "heap_snapshot_diff_executor_result_requires_review" in warnings:
        return "review_heap_snapshot_diff_executor_result_before_followup"
    if "heap_snapshot_diff_followup_checkpoint_requires_review" in warnings:
        return "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work"
    if "heap_snapshot_diff_selected_analysis_input_preflight_requires_review" in warnings:
        return "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work"
    if "heap_snapshot_constructor_growth_drilldown_requires_review" in warnings:
        return "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight"
    if "heap_snapshot_constructor_growth_drilldown_analysis_ready_for_retained_size_path_or_second_pass_review" in warnings:
        return "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass"
    if "heap_snapshot_automatic_followup_plan_ready_for_proof_or_second_pass_review" in warnings:
        return "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass"
    if "heap_snapshot_retained_size_proof_plan_ready_for_raw_heap_ingestion_review" in warnings:
        return "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor"
    if "heap_snapshot_path_to_root_proof_plan_ready_for_raw_heap_ingestion_review" in warnings:
        return "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor"
    if "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_for_raw_heap_ingestion_review" in warnings:
        return "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor"
    if "heap_snapshot_retained_path_preflight_requires_review" in warnings:
        return "review_heap_snapshot_retained_path_executor_inputs"
    if "heap_snapshot_retained_size_input_review_requires_review" in warnings:
        return "review_heap_snapshot_retained_size_approval_plan"
    if "heap_snapshot_retained_size_approval_plan_requires_review" in warnings:
        return "record_heap_snapshot_retained_size_approval"
    if "heap_snapshot_retained_size_approval_record_ready_for_transaction_preflight" in warnings:
        return "review_heap_snapshot_retained_size_transaction_preflight"
    if "heap_snapshot_retained_size_transaction_preflight_ready_for_journal_writer" in warnings:
        return "review_heap_snapshot_retained_size_transaction_journal_writer"
    if "heap_snapshot_retained_size_transaction_journal_ready_for_bounded_gate" in warnings:
        return "review_heap_snapshot_retained_size_bounded_gate"
    if "heap_snapshot_retained_size_bounded_gate_ready_for_executor_review" in warnings:
        return "review_heap_snapshot_retained_size_executor_mvp"
    if "heap_snapshot_retained_size_analysis_ready_for_path_to_root_or_second_pass_review" in warnings:
        return "review_heap_snapshot_retained_size_analysis_before_path_to_root_or_second_pass"
    if "heap_snapshot_path_to_root_analysis_ready_for_second_pass_or_constructor_drilldown_review" in warnings:
        return "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown"
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
