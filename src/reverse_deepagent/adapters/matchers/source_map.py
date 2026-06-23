from __future__ import annotations

from typing import Any


"""Source map request predicates for NativeWebRuntime."""

def _is_source_map_fetch_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"source-map-fetch", "fetch-source-map", "source-map-url"}:
        return True
    return any(
        key in context
        for key in (
            "source_map_url",
            "sourceMapUrl",
            "source_mapping_url",
            "sourceMappingURL",
            "fetch_source_map",
            "fetchSourceMap",
            "fetch_indexed_section_urls",
            "fetchIndexedSectionUrls",
        )
    )


def _is_source_map_lookup_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-lookup",
        "source-map-consumer",
        "source-map-generated-lookup",
        "generated-source-map-lookup",
        "original-source-map-lookup",
        "review-source-map-lookup",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_lookup",
            "sourceMapLookup",
            "source_map_consumer",
            "sourceMapConsumer",
            "source_map_generated_lookup",
            "sourceMapGeneratedLookup",
        )
    )


def _is_source_map_source_content_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-source-content",
        "source-map-sources-content",
        "source-map-content",
        "source-map-source",
        "review-source-map-source-content",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_source_content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "sourceMapSourcesContent",
            "review_source_map_source_content",
            "reviewSourceMapSourceContent",
        )
    )


def _is_source_map_typed_payload_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-typed-payload-preflight",
        "source-map-consumer-typed-payload-preflight",
        "source-map-followthrough-preflight",
        "source-map-follow-through-preflight",
        "review-source-map-typed-payload-preflight",
        "preflight-source-map-typed-payloads",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_typed_payload_preflight",
            "sourceMapTypedPayloadPreflight",
            "source_map_consumer_typed_payload_preflight",
            "sourceMapConsumerTypedPayloadPreflight",
            "source_map_followthrough_preflight",
            "sourceMapFollowthroughPreflight",
        )
    )


def _is_source_map_followthrough_dispatcher_result_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    names = {
        "source-map-followthrough-dispatcher-result",
        "source-map-followthrough-dispatcher-mvp",
        "source-map-followthrough-dispatch-next-action",
        "execute-source-map-followthrough-dispatcher-mvp",
        "review-source-map-followthrough-dispatcher-mvp",
    }
    selected_executor_apply_preflight_names = {
        "source-map-selected-executor-apply-preflight",
        "source-map-selected-executor-application-preflight",
        "source-map-followthrough-apply-preflight",
        "review-source-map-selected-executor-apply-preflight",
        "preflight-source-map-selected-executor-apply",
        "review-selected-source-map-executor-apply-preflight",
    }
    if normalized in selected_executor_apply_preflight_names:
        return False
    context_keys = (
        "source_map_followthrough_dispatcher_result",
        "sourceMapFollowthroughDispatcherResult",
        "source_map_followthrough_dispatcher_mvp",
        "sourceMapFollowthroughDispatcherMvp",
        "source_map_followthrough_dispatch_next_action",
        "sourceMapFollowthroughDispatchNextAction",
    )
    return normalized in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatcher_apply_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatcher-apply-preflight",
        "source-map-followthrough-dispatch-apply-preflight",
        "source-map-followthrough-dispatcher-preflight",
        "review-source-map-followthrough-dispatcher-apply-preflight",
        "preflight-source-map-followthrough-dispatcher",
    }
    context_keys = (
        "source_map_followthrough_dispatcher_apply_preflight",
        "sourceMapFollowthroughDispatcherApplyPreflight",
        "source_map_followthrough_dispatch_apply_preflight",
        "sourceMapFollowthroughDispatchApplyPreflight",
        "source_map_followthrough_dispatcher_preflight",
        "sourceMapFollowthroughDispatcherPreflight",
    )
    # Followthrough dispatcher result requests use the same context keys
    # but should not be intercepted here -- they are handled by gateway_e.
    if protection_name in {
        "source-map-followthrough-dispatcher-result",
        "source-map-followthrough-dispatcher-mvp",
        "source-map-followthrough-dispatch-next-action",
        "execute-source-map-followthrough-dispatcher-mvp",
        "review-source-map-followthrough-dispatcher-mvp",
    }:
        return False

    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatcher_handoff_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatcher-handoff",
        "source-map-followthrough-dispatch-handoff",
        "source-map-followthrough-next-action-handoff",
        "review-source-map-followthrough-dispatcher-handoff",
        "handoff-source-map-followthrough-dispatcher",
    }
    context_keys = (
        "source_map_followthrough_dispatcher_handoff",
        "sourceMapFollowthroughDispatcherHandoff",
        "source_map_followthrough_dispatch_handoff",
        "sourceMapFollowthroughDispatchHandoff",
        "source_map_followthrough_next_action_handoff",
        "sourceMapFollowthroughNextActionHandoff",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatch_bounded_executor_gate_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatch-bounded-executor-gate",
        "source-map-followthrough-dispatch-bounded-gate",
        "source-map-followthrough-dispatch-executor-gate",
        "review-source-map-followthrough-dispatch-bounded-executor-gate",
        "gate-source-map-followthrough-dispatch-executor",
    }
    context_keys = (
        "source_map_followthrough_dispatch_bounded_executor_gate",
        "sourceMapFollowthroughDispatchBoundedExecutorGate",
        "source_map_followthrough_dispatch_bounded_gate",
        "sourceMapFollowthroughDispatchBoundedGate",
        "source_map_followthrough_dispatch_executor_gate",
        "sourceMapFollowthroughDispatchExecutorGate",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatch_transaction_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatch-transaction-preflight",
        "source-map-followthrough-dispatch-journal-preflight",
        "source-map-followthrough-dispatch-transaction-gate",
        "review-source-map-followthrough-dispatch-transaction-preflight",
        "preflight-source-map-followthrough-dispatch-transaction",
    }
    context_keys = (
        "source_map_followthrough_dispatch_transaction_preflight",
        "sourceMapFollowthroughDispatchTransactionPreflight",
        "source_map_followthrough_dispatch_journal_preflight",
        "sourceMapFollowthroughDispatchJournalPreflight",
        "source_map_followthrough_dispatch_transaction_gate",
        "sourceMapFollowthroughDispatchTransactionGate",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatch_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatch-approval-plan",
        "source-map-followthrough-executor-approval-plan",
        "source-map-followthrough-dispatch-transaction-plan",
        "review-source-map-followthrough-dispatch-approval-plan",
        "plan-source-map-followthrough-dispatch-approval",
    }
    context_keys = (
        "source_map_followthrough_dispatch_approval_plan",
        "sourceMapFollowthroughDispatchApprovalPlan",
        "source_map_followthrough_executor_approval_plan",
        "sourceMapFollowthroughExecutorApprovalPlan",
        "source_map_followthrough_dispatch_transaction_plan",
        "sourceMapFollowthroughDispatchTransactionPlan",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_dispatch_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-dispatch-preflight",
        "source-map-followthrough-dispatch-review",
        "source-map-followthrough-executor-dispatch-preflight",
        "review-source-map-followthrough-dispatch-preflight",
        "preflight-source-map-followthrough-dispatch",
    }
    context_keys = (
        "source_map_followthrough_dispatch_preflight",
        "sourceMapFollowthroughDispatchPreflight",
        "source_map_followthrough_dispatch_review",
        "sourceMapFollowthroughDispatchReview",
        "source_map_followthrough_executor_dispatch_preflight",
        "sourceMapFollowthroughExecutorDispatchPreflight",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_one_step_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "source-map-followthrough-one-step-plan",
        "source-map-followthrough-orchestrator-plan",
        "source-map-followthrough-next-step-plan",
        "review-source-map-followthrough-one-step-plan",
        "plan-source-map-followthrough-next-step",
    }
    context_keys = (
        "source_map_followthrough_one_step_plan",
        "sourceMapFollowthroughOneStepPlan",
        "source_map_followthrough_orchestrator_plan",
        "sourceMapFollowthroughOrchestratorPlan",
        "source_map_followthrough_next_step_plan",
        "sourceMapFollowthroughNextStepPlan",
    )
    return protection_name in names or any(bool(context.get(key)) for key in context_keys)


def _is_source_map_followthrough_chain_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-followthrough-chain-readiness",
        "source-map-followthrough-chain-review",
        "source-map-followthrough-status",
        "source-map-chain-readiness",
        "review-source-map-followthrough-chain",
        "review-source-map-followthrough-chain-readiness",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_followthrough_chain_readiness",
            "sourceMapFollowthroughChainReadiness",
            "source_map_followthrough_chain_review",
            "sourceMapFollowthroughChainReview",
            "source_map_followthrough_status",
            "sourceMapFollowthroughStatus",
            "source_map_chain_readiness",
            "sourceMapChainReadiness",
        )
    )


def _is_source_map_followthrough_review_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-followthrough-review",
        "source-map-typed-payload-followthrough-review",
        "source-map-consumer-followthrough-review",
        "review-source-map-followthrough",
        "review-source-map-typed-payload-followthrough",
        "source-map-followthrough-review-surface",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_followthrough_review",
            "sourceMapFollowthroughReview",
            "source_map_typed_payload_followthrough_review",
            "sourceMapTypedPayloadFollowthroughReview",
            "source_map_followthrough_review_surface",
            "sourceMapFollowthroughReviewSurface",
            "source_map_consumer_followthrough_review",
            "sourceMapConsumerFollowthroughReview",
        )
    )


def _is_source_map_selected_executor_input_review_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-selected-executor-input-review",
        "source-map-followthrough-executor-input-review",
        "source-map-selected-followthrough-review",
        "source-map-debugger-candidate-selected-input-review",
        "source-map-debugger-candidate-executor-input-review",
        "source-map-debugger-candidate-selected-executor-input-review",
        "review-source-map-debugger-candidate-selected-input",
        "source-map-hook-candidate-selected-input-review",
        "source-map-hook-candidate-executor-input-review",
        "source-map-hook-candidate-selected-executor-input-review",
        "review-source-map-hook-candidate-selected-input",
        "review-source-map-selected-executor-input",
        "review-selected-source-map-executor-input",
        "preflight-selected-source-map-followthrough-executor-input",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_selected_executor_input_review",
            "sourceMapSelectedExecutorInputReview",
            "source_map_followthrough_executor_input_review",
            "sourceMapFollowthroughExecutorInputReview",
            "source_map_selected_followthrough_review",
            "sourceMapSelectedFollowthroughReview",
            "source_map_debugger_candidate_selected_input_review",
            "sourceMapDebuggerCandidateSelectedInputReview",
            "source_map_debugger_candidate_executor_input_review",
            "sourceMapDebuggerCandidateExecutorInputReview",
        )
    )


def _is_source_map_selected_executor_apply_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-selected-executor-apply-preflight",
        "source-map-selected-executor-application-preflight",
        "source-map-followthrough-apply-preflight",
        "review-source-map-selected-executor-apply-preflight",
        "preflight-source-map-selected-executor-apply",
        "review-selected-source-map-executor-apply-preflight",
    }:
        return True
    # Explicit application branches in gateway_e use the same context keys but
    # should not be intercepted here -- they are handled by gateway_e instead.
    if normalized in {
        "source-map-debugger-application",
        "source-map-debugger-location-application",
        "source-map-debugger-execution-result",
        "source-map-selected-debugger-application",
        "source-map-selected-debugger-executor-application",
        "apply-source-map-debugger-location",
        "execute-reviewed-source-map-debugger-location-action",
        "source-map-hook-application",
        "source-map-hook-install",
        "source-map-hook-install-result",
        "source-map-selected-hook-application",
        "source-map-selected-hook-executor-application",
        "apply-source-map-hook",
        "install-reviewed-source-map-hook-symbol-scope",
        "source-map-rebuild-application",
        "source-map-rebuild-metadata-application",
        "source-map-rebuild-result",
        "source-map-selected-rebuild-application",
        "source-map-selected-rebuild-executor-application",
        "apply-source-map-rebuild-metadata",
        "run-reviewed-source-map-rebuild-metadata-generation",
        "source-map-rebuild-generation",
        "source-map-rebuild-bundle-generation",
        "source-map-rebuild-generation-result",
        "source-map-selected-rebuild-generation",
        "source-map-selected-rebuild-generation-executor",
        "generate-reviewed-source-map-rebuild-bundle",
        "run-reviewed-source-map-rebuild-generation",
        "source-map-source-logpoint-application",
        "source-map-source-logpoint-install",
        "source-map-selected-source-logpoint-application",
        "source-map-selected-source-logpoint-executor-application",
        "apply-source-map-source-logpoint",
        "install-reviewed-source-map-source-logpoint",
        "source-map-followthrough-dispatcher-result",
        "source-map-followthrough-dispatcher-mvp",
        "source-map-followthrough-dispatch-next-action",
        "execute-source-map-followthrough-dispatcher-mvp",
        "review-source-map-followthrough-dispatcher-mvp",
        "source-map-fetch",
        "fetch-source-map",
        "source-map-url",
    }:
        return False

    return any(
        key in context
        for key in (
            "source_map_selected_executor_apply_preflight",
            "sourceMapSelectedExecutorApplyPreflight",
            "source_map_selected_executor_application_preflight",
            "sourceMapSelectedExecutorApplicationPreflight",
            "source_map_followthrough_apply_preflight",
            "sourceMapFollowthroughApplyPreflight",
        )
    )


def _is_source_map_selected_executor_application_handoff_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-followthrough-completion-checkpoint",
        "source-map-followthrough-completion-review",
        "source-map-followthrough-next-action-checkpoint",
        "review-source-map-followthrough-completion-checkpoint",
        "checkpoint-source-map-followthrough-completion",
        "review-source-map-followthrough-next-action-checkpoint",
        "source-map-selected-executor-result-checkpoint",
        "source-map-selected-executor-application-result-checkpoint",
        "source-map-followthrough-result-checkpoint",
        "review-source-map-selected-executor-result-checkpoint",
        "checkpoint-source-map-selected-executor-result",
        "review-source-map-followthrough-result-checkpoint",
    } or any(
        bool(context.get(key))
        for key in (
            "source_map_followthrough_completion_checkpoint",
            "sourceMapFollowthroughCompletionCheckpoint",
            "source_map_followthrough_completion_review",
            "sourceMapFollowthroughCompletionReview",
            "source_map_followthrough_next_action_checkpoint",
            "sourceMapFollowthroughNextActionCheckpoint",
            "source_map_selected_executor_result_checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_selected_executor_application_result_checkpoint",
            "sourceMapSelectedExecutorApplicationResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
    ):
        return False
    if normalized in {
        "source-map-selected-executor-application-handoff",
        "source-map-selected-executor-application-review-input",
        "source-map-selected-executor-application-review-handoff",
        "source-map-followthrough-application-handoff",
        "review-source-map-selected-executor-application-handoff",
        "handoff-source-map-selected-executor-application",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_selected_executor_application_handoff",
            "sourceMapSelectedExecutorApplicationHandoff",
            "source_map_selected_executor_application_review_input",
            "sourceMapSelectedExecutorApplicationReviewInput",
            "source_map_followthrough_application_handoff",
            "sourceMapFollowthroughApplicationHandoff",
        )
    )


def _is_source_map_terminal_review_package_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_source_map_terminal_review_closure_checkpoint_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-terminal-review-package",
        "source-map-terminal-review-handoff",
        "source-map-followthrough-terminal-review-package",
        "source-map-followthrough-audit-handoff",
        "review-source-map-terminal-review-package",
        "package-source-map-terminal-review",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_terminal_review_package",
            "sourceMapTerminalReviewPackage",
            "source_map_followthrough_terminal_review_package",
            "sourceMapFollowthroughTerminalReviewPackage",
            "source_map_terminal_review_handoff",
            "sourceMapTerminalReviewHandoff",
            "source_map_followthrough_audit_handoff",
            "sourceMapFollowthroughAuditHandoff",
        )
    )


def _is_source_map_terminal_review_closure_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_source_map_terminal_review_final_audit_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-terminal-review-closure-checkpoint",
        "source-map-terminal-review-observed-result-checkpoint",
        "source-map-followthrough-closure-audit",
        "source-map-terminal-review-closure-audit",
        "review-source-map-terminal-review-closure-checkpoint",
        "checkpoint-source-map-terminal-review-closure",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_terminal_review_closure_checkpoint",
            "sourceMapTerminalReviewClosureCheckpoint",
            "source_map_terminal_review_observed_result_checkpoint",
            "sourceMapTerminalReviewObservedResultCheckpoint",
            "source_map_followthrough_closure_audit",
            "sourceMapFollowthroughClosureAudit",
            "source_map_terminal_review_closure_audit",
            "sourceMapTerminalReviewClosureAudit",
        )
    )


def _is_source_map_terminal_review_final_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-terminal-review-final-audit",
        "source-map-terminal-review-final-audit-rollup",
        "source-map-followthrough-final-audit",
        "source-map-terminal-review-closure-summary",
        "review-source-map-terminal-review-final-audit",
        "rollup-source-map-terminal-review-final-audit",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_terminal_review_final_audit",
            "sourceMapTerminalReviewFinalAudit",
            "source_map_terminal_review_final_audit_rollup",
            "sourceMapTerminalReviewFinalAuditRollup",
            "source_map_followthrough_final_audit",
            "sourceMapFollowthroughFinalAudit",
            "source_map_terminal_review_closure_summary",
            "sourceMapTerminalReviewClosureSummary",
        )
    )


def _is_source_map_followthrough_completion_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_source_map_terminal_review_package_request(protection_name, context):
        return False
    if normalized in {
        "source-map-followthrough-completion-checkpoint",
        "source-map-followthrough-completion-review",
        "source-map-followthrough-next-action-checkpoint",
        "review-source-map-followthrough-completion-checkpoint",
        "checkpoint-source-map-followthrough-completion",
        "review-source-map-followthrough-next-action-checkpoint",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_followthrough_completion_checkpoint",
            "sourceMapFollowthroughCompletionCheckpoint",
            "source_map_followthrough_completion_review",
            "sourceMapFollowthroughCompletionReview",
            "source_map_followthrough_next_action_checkpoint",
            "sourceMapFollowthroughNextActionCheckpoint",
        )
    )


def _is_source_map_selected_executor_result_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_source_map_followthrough_completion_checkpoint_request(protection_name, context):
        return False
    if normalized in {
        "source-map-selected-executor-result-checkpoint",
        "source-map-selected-executor-application-result-checkpoint",
        "source-map-followthrough-result-checkpoint",
        "review-source-map-selected-executor-result-checkpoint",
        "checkpoint-source-map-selected-executor-result",
        "review-source-map-followthrough-result-checkpoint",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "source_map_selected_executor_result_checkpoint",
            "sourceMapSelectedExecutorResultCheckpoint",
            "source_map_selected_executor_application_result_checkpoint",
            "sourceMapSelectedExecutorApplicationResultCheckpoint",
            "source_map_followthrough_result_checkpoint",
            "sourceMapFollowthroughResultCheckpoint",
        )
    )


def _is_source_map_debugger_application_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-debugger-application",
        "source-map-debugger-location-application",
        "source-map-debugger-execution-result",
        "source-map-selected-debugger-application",
        "source-map-selected-debugger-executor-application",
        "apply-source-map-debugger-location",
        "execute-reviewed-source-map-debugger-location-action",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_debugger_application",
            "sourceMapDebuggerApplication",
            "source_map_debugger_location_application",
            "sourceMapDebuggerLocationApplication",
            "source_map_selected_debugger_application",
            "sourceMapSelectedDebuggerApplication",
        )
    )


def _is_source_map_source_logpoint_application_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-source-logpoint-application",
        "source-map-source-logpoint-install",
        "source-map-selected-source-logpoint-application",
        "source-map-selected-source-logpoint-executor-application",
        "apply-source-map-source-logpoint",
        "install-reviewed-source-map-source-logpoint",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_source_logpoint_application",
            "sourceMapSourceLogpointApplication",
            "source_map_source_logpoint_install",
            "sourceMapSourceLogpointInstall",
            "source_map_selected_source_logpoint_application",
            "sourceMapSelectedSourceLogpointApplication",
        )
    )


def _is_source_map_rebuild_metadata_application_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-rebuild-application",
        "source-map-rebuild-metadata-application",
        "source-map-rebuild-result",
        "source-map-selected-rebuild-application",
        "source-map-selected-rebuild-executor-application",
        "apply-source-map-rebuild-metadata",
        "run-reviewed-source-map-rebuild-metadata-generation",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_rebuild_application",
            "sourceMapRebuildApplication",
            "source_map_rebuild_metadata_application",
            "sourceMapRebuildMetadataApplication",
            "source_map_selected_rebuild_application",
            "sourceMapSelectedRebuildApplication",
        )
    )


def _is_source_map_rebuild_generation_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-rebuild-generation",
        "source-map-rebuild-bundle-generation",
        "source-map-rebuild-generation-result",
        "source-map-selected-rebuild-generation",
        "source-map-selected-rebuild-generation-executor",
        "generate-reviewed-source-map-rebuild-bundle",
        "run-reviewed-source-map-rebuild-generation",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_rebuild_generation",
            "sourceMapRebuildGeneration",
            "source_map_rebuild_bundle_generation",
            "sourceMapRebuildBundleGeneration",
            "source_map_selected_rebuild_generation",
            "sourceMapSelectedRebuildGeneration",
        )
    )


def _is_source_map_hook_application_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-hook-application",
        "source-map-hook-install",
        "source-map-hook-install-result",
        "source-map-selected-hook-application",
        "source-map-selected-hook-executor-application",
        "apply-source-map-hook",
        "install-reviewed-source-map-hook-symbol-scope",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_hook_application",
            "sourceMapHookApplication",
            "source_map_hook_install",
            "sourceMapHookInstall",
            "source_map_selected_hook_application",
            "sourceMapSelectedHookApplication",
        )
    )


def _is_source_map_hook_candidate_selection_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-selected-executor-input-review",
        "source-map-followthrough-executor-input-review",
        "source-map-selected-followthrough-review",
        "source-map-hook-candidate-selected-input-review",
        "source-map-hook-candidate-executor-input-review",
        "source-map-hook-candidate-selected-executor-input-review",
        "review-source-map-hook-candidate-selected-input",
        "review-source-map-selected-executor-input",
        "review-selected-source-map-executor-input",
        "preflight-selected-source-map-followthrough-executor-input",
    }:
        return False
    if normalized in {
        "source-map-hook-candidate-selection",
        "source-map-hook-candidate-handoff",
        "source-map-hook-candidate-executor-input",
        "source-map-selected-hook-candidate",
        "select-source-map-hook-candidate",
        "handoff-source-map-hook-candidate",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_hook_candidate_selection",
            "sourceMapHookCandidateSelection",
            "source_map_hook_candidate_handoff",
            "sourceMapHookCandidateHandoff",
            "source_map_hook_candidate_executor_input",
            "sourceMapHookCandidateExecutorInput",
            "select_source_map_hook_candidate",
            "selectSourceMapHookCandidate",
        )
    )


def _is_source_map_hook_candidate_refinement_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-hook-candidate-selection",
        "source-map-hook-candidate-handoff",
        "source-map-hook-candidate-executor-input",
        "source-map-selected-hook-candidate",
        "select-source-map-hook-candidate",
        "handoff-source-map-hook-candidate",
        "source-map-hook-candidate-selected-input-review",
        "source-map-hook-candidate-executor-input-review",
        "source-map-hook-candidate-selected-executor-input-review",
        "review-source-map-hook-candidate-selected-input",
    }:
        return False
    if normalized in {
        "source-map-hook-candidates",
        "source-map-hook-candidate-refinement",
        "source-map-hook-candidate-review",
        "source-map-selected-hook-candidates",
        "refine-source-map-hook-candidates",
        "review-source-map-hook-candidates",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_hook_candidates",
            "sourceMapHookCandidates",
            "source_map_hook_candidate_refinement",
            "sourceMapHookCandidateRefinement",
            "source_map_hook_candidate_review",
            "sourceMapHookCandidateReview",
            "refine_source_map_hook_candidates",
            "refineSourceMapHookCandidates",
        )
    )


def _is_source_map_debugger_candidate_review_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-debugger-candidates",
        "source-map-debugger-candidate-review",
        "source-map-debugger-candidate-refinement",
        "source-map-selected-debugger-candidates",
        "rank-source-map-debugger-candidates",
        "review-source-map-debugger-candidates",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_debugger_candidates",
            "sourceMapDebuggerCandidates",
            "source_map_debugger_candidate_review",
            "sourceMapDebuggerCandidateReview",
            "source_map_debugger_candidate_refinement",
            "sourceMapDebuggerCandidateRefinement",
            "rank_source_map_debugger_candidates",
            "rankSourceMapDebuggerCandidates",
        )
    )


def _is_source_map_debugger_candidate_selection_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-selected-executor-input-review",
        "source-map-followthrough-executor-input-review",
        "source-map-selected-followthrough-review",
        "source-map-debugger-candidate-selected-input-review",
        "source-map-debugger-candidate-executor-input-review",
        "source-map-debugger-candidate-selected-executor-input-review",
        "review-source-map-debugger-candidate-selected-input",
        "source-map-hook-candidate-selected-input-review",
        "source-map-hook-candidate-executor-input-review",
        "source-map-hook-candidate-selected-executor-input-review",
        "review-source-map-hook-candidate-selected-input",
        "review-source-map-selected-executor-input",
        "review-selected-source-map-executor-input",
        "preflight-selected-source-map-followthrough-executor-input",
    }:
        return False
    if normalized in {
        "source-map-debugger-candidate-selection",
        "source-map-debugger-candidate-handoff",
        "source-map-debugger-candidate-executor-input",
        "source-map-selected-debugger-candidate",
        "select-source-map-debugger-candidate",
        "handoff-source-map-debugger-candidate",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_debugger_candidate_selection",
            "sourceMapDebuggerCandidateSelection",
            "source_map_debugger_candidate_handoff",
            "sourceMapDebuggerCandidateHandoff",
            "source_map_debugger_candidate_executor_input",
            "sourceMapDebuggerCandidateExecutorInput",
            "select_source_map_debugger_candidate",
            "selectSourceMapDebuggerCandidate",
        )
    )


def _is_source_map_selected_executor_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-selected-executor-approval-plan",
        "source-map-selected-executor-apply-plan",
        "source-map-followthrough-approval-plan",
        "review-source-map-selected-executor-approval-plan",
        "plan-source-map-selected-executor-apply",
        "review-selected-source-map-executor-approval",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_selected_executor_approval_plan",
            "sourceMapSelectedExecutorApprovalPlan",
            "source_map_selected_executor_apply_plan",
            "sourceMapSelectedExecutorApplyPlan",
            "source_map_followthrough_approval_plan",
            "sourceMapFollowthroughApprovalPlan",
        )
    )


def _is_source_map_followthrough_surface_selection_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-followthrough-surface-selection",
        "source-map-followthrough-surface-review",
        "source-map-followthrough-surface-selector",
        "select-source-map-followthrough-surface",
        "review-source-map-followthrough-surface-selection",
        "review-selected-source-map-followthrough-surface",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_followthrough_surface_selection",
            "sourceMapFollowthroughSurfaceSelection",
            "source_map_followthrough_surface_review",
            "sourceMapFollowthroughSurfaceReview",
            "source_map_followthrough_surface_selector",
            "sourceMapFollowthroughSurfaceSelector",
        )
    )


def _is_source_map_consumer_materialization_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-consumer-materialization",
        "source-map-materialization",
        "source-map-action-materialization",
        "review-source-map-consumer-materialization",
        "materialize-source-map-consumers",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_consumer_materialization",
            "sourceMapConsumerMaterialization",
            "source_map_materialization",
            "sourceMapMaterialization",
            "source_map_action_materialization",
            "sourceMapActionMaterialization",
        )
    )


def _is_source_map_consumer_action_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-consumer-action-plan",
        "source-map-action-plan",
        "source-map-followup-plan",
        "review-source-map-consumer-action-plan",
        "plan-source-map-consumers",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_consumer_action_plan",
            "sourceMapConsumerActionPlan",
            "source_map_action_plan",
            "sourceMapActionPlan",
            "source_map_followup_plan",
            "sourceMapFollowupPlan",
        )
    )


def _is_source_map_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "source-map-readiness",
        "source-map-review-readiness",
        "source-map-debugger-readiness",
        "review-source-map-readiness",
    }:
        return True
    return any(
        key in context
        for key in (
            "source_map_readiness",
            "sourceMapReadiness",
            "review_source_map_readiness",
            "reviewSourceMapReadiness",
            "source_map_debugger_readiness",
            "sourceMapDebuggerReadiness",
        )
    )


def _is_bundler_symbol_scope_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"bundler-symbol-scope", "source-map-symbol-scope", "review-bundler-symbol-scope", "plan-source-symbol-scope"}:
        return True
    return any(
        key in context
        for key in (
            "bundler_symbol_scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
            "review_bundler_symbol_scope",
            "reviewBundlerSymbolScope",
        )
    )


def _is_source_logpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"source-logpoint", "logpoint"}:
        return True
    return any(
        key in context
        for key in (
            "log_expression",
            "logExpression",
            "source_expression",
            "sourceExpression",
            "logpoint_id",
            "logpointId",
        )
    )


