from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.browser.hooks import (
    BreakpointManager,
    BreakpointSpec,
    FunctionHookManager,
    FunctionHookSpec,
    ModuleHookManager,
    ModuleHookSpec,
    SourceLogpointManager,
    SourceLogpointSpec,
)
from reverse_deepagent.browser.source_map_fetch import SourceMapFetchManager, SourceMapFetchSpec
from reverse_deepagent.browser.source_map_readiness import SourceMapReadinessManager, SourceMapReadinessSpec
from reverse_deepagent.browser.source_maps import (
    BundlerSymbolScopeManager,
    BundlerSymbolScopeSpec,
    SourceMapConsumerActionPlanManager,
    SourceMapConsumerActionPlanSpec,
    SourceMapConsumerMaterializationManager,
    SourceMapConsumerMaterializationSpec,
    SourceMapDebuggerCandidateSelectionManager,
    SourceMapDebuggerCandidateSelectionSpec,
    SourceMapDebuggerCandidateReviewManager,
    SourceMapDebuggerCandidateReviewSpec,
    SourceMapFollowthroughChainReadinessManager,
    SourceMapFollowthroughChainReadinessSpec,
    SourceMapFollowthroughCompletionCheckpointManager,
    SourceMapFollowthroughCompletionCheckpointSpec,
    SourceMapFollowthroughDispatchPreflightManager,
    SourceMapFollowthroughDispatchPreflightSpec,
    SourceMapFollowthroughOneStepPlanManager,
    SourceMapFollowthroughOneStepPlanSpec,
    SourceMapFollowthroughReviewManager,
    SourceMapFollowthroughReviewSpec,
    SourceMapFollowthroughSurfaceSelectionManager,
    SourceMapFollowthroughSurfaceSelectionSpec,
    SourceMapHookCandidateRefinementManager,
    SourceMapHookCandidateRefinementSpec,
    SourceMapHookCandidateSelectionManager,
    SourceMapHookCandidateSelectionSpec,
    SourceMapLookupManager,
    SourceMapLookupSpec,
    SourceMapSelectedExecutorApplicationHandoffManager,
    SourceMapSelectedExecutorApplicationHandoffSpec,
    SourceMapSelectedExecutorApplyPreflightManager,
    SourceMapSelectedExecutorApplyPreflightSpec,
    SourceMapSelectedExecutorApprovalPlanManager,
    SourceMapSelectedExecutorApprovalPlanSpec,
    SourceMapSelectedExecutorInputReviewManager,
    SourceMapSelectedExecutorInputReviewSpec,
    SourceMapSelectedExecutorResultCheckpointManager,
    SourceMapSelectedExecutorResultCheckpointSpec,
    SourceMapSourceContentManager,
    SourceMapSourceContentSpec,
    SourceMapTerminalReviewClosureCheckpointManager,
    SourceMapTerminalReviewClosureCheckpointSpec,
    SourceMapTerminalReviewFinalAuditManager,
    SourceMapTerminalReviewFinalAuditSpec,
    SourceMapTerminalReviewPackageManager,
    SourceMapTerminalReviewPackageSpec,
    SourceMapTypedPayloadPreflightManager,
    SourceMapTypedPayloadPreflightSpec,
    SourceMapFollowthroughDispatcherApplyPreflightManager,
    SourceMapFollowthroughDispatcherApplyPreflightSpec,
    SourceMapFollowthroughDispatcherHandoffManager,
    SourceMapFollowthroughDispatcherHandoffSpec,
    SourceMapFollowthroughDispatchBoundedExecutorGateManager,
    SourceMapFollowthroughDispatchBoundedExecutorGateSpec,
    SourceMapFollowthroughDispatchTransactionPreflightManager,
    SourceMapFollowthroughDispatchTransactionPreflightSpec,
    SourceMapFollowthroughDispatchApprovalPlanManager,
    SourceMapFollowthroughDispatchApprovalPlanSpec,
    SourceMapFollowthroughDispatcherManager,
    SourceMapFollowthroughDispatcherResultSpec,
)
from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    ExecutionStatus,
    FinalResult,
    ProtectionResult,
    TaskCard,
)


def dispatch_source_map_review_evidence(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Route the lowest-side-effect Source Map review-evidence requests."""
    if owner._is_source_map_lookup_request(protection_name, context):
        spec = SourceMapLookupSpec.from_context(context)
        result = SourceMapLookupManager().lookup(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        request = descriptor.get("lookup_request") if isinstance(descriptor.get("lookup_request"), dict) else {}
        location = descriptor.get("location") if isinstance(descriptor.get("location"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_lookup_status={result.status}",
            f"source_map_lookup_direction={request.get('lookup_direction', '')}",
            f"source_map_lookup_mapping_found={descriptor.get('mapping_found', False)}",
            f"source_map_lookup_strategy={location.get('strategy', '')}",
            "source_map_lookup_review_only=True",
            f"source_map_lookup_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_lookup_browser_started={policy.get('browser_started', False)}",
            f"source_map_lookup_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_lookup_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_lookup_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_lookup_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_lookup_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_lookup_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-lookup.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map lookup descriptor.",
            metadata={"status": result.status, "lookup_direction": request.get("lookup_direction", ""), "mapping_found": bool(descriptor.get("mapping_found", False)), "strategy": location.get("strategy", ""), "review_only": True, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False},
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_lookup_before_debugger_or_hook_use"
            actions = ["review_source_map_lookup"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_payload_and_lookup_position"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_lookup_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_source_content_request(protection_name, context):
        spec = SourceMapSourceContentSpec.from_context(context)
        result = SourceMapSourceContentManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        request = descriptor.get("source_request") if isinstance(descriptor.get("source_request"), dict) else {}
        content_summary = descriptor.get("content_summary") if isinstance(descriptor.get("content_summary"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_source_content_status={result.status}",
            f"source_map_source_content_available={descriptor.get('source_content_available', False)}",
            f"source_map_source_content_original_source={request.get('original_source', '')}",
            f"source_map_source_content_source_index={request.get('source_index')}",
            f"source_map_source_content_sha256={content_summary.get('sha256', '')}",
            "source_map_source_content_review_only=True",
            f"source_map_source_content_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_source_content_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_source_content_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_source_content_browser_started={policy.get('browser_started', False)}",
            f"source_map_source_content_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_source_content_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_source_content_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_source_content_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_source_content_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_source_content_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-source-content.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map sourcesContent availability descriptor.",
            metadata={"status": result.status, "source_content_available": bool(descriptor.get("source_content_available", False)), "original_source": request.get("original_source", ""), "source_index": request.get("source_index"), "sha256": content_summary.get("sha256", ""), "review_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False},
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_content_availability_before_debugger_or_rebuild"
            actions = ["review_source_map_source_content"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_with_sources_content"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_source_content_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_bundler_symbol_scope_request(protection_name, context):
        spec = BundlerSymbolScopeSpec.from_context(context)
        result = BundlerSymbolScopeManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        classification = descriptor.get("bundler_classification") if isinstance(descriptor.get("bundler_classification"), dict) else {}
        request = descriptor.get("symbol_request") if isinstance(descriptor.get("symbol_request"), dict) else {}
        verification = [
            f"bundler_symbol_scope_status={result.status}",
            f"bundler_symbol_scope_bundler={classification.get('bundler_kind', 'unknown')}",
            f"bundler_symbol_scope_candidate_count={descriptor.get('scope_candidate_count', 0)}",
            f"bundler_symbol_scope_symbol={request.get('symbol_name', '')}",
            "bundler_symbol_scope_review_only=True",
            "bundler_symbol_scope_fetch_source_map=False",
            "bundler_symbol_scope_logpoint_installed=False",
            "bundler_symbol_scope_cdp_command_sent=False",
            "bundler_symbol_scope_calls_mcp=False",
            "bundler_symbol_scope_mobile_runtime_used=False",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"bundler_symbol_scope_reason={result.reason}")
        if result.error:
            verification.append(f"bundler_symbol_scope_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/bundler-symbol-scope.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only bundler symbol scope descriptor.",
            metadata={"status": result.status, "bundler_kind": classification.get("bundler_kind", "unknown"), "confidence": classification.get("confidence", "low"), "symbol_name": request.get("symbol_name", ""), "scope_candidate_count": descriptor.get("scope_candidate_count", 0), "review_only": True, "fetch_source_map": False, "logpoint_installed": False},
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = "review_symbol_scope_before_source_logpoint_or_hook"
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = "provide_source_map_symbol_and_original_source"
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_bundler_symbol_scope_descriptor"
        return ProtectionResult(protection_name=protection_name, applied_actions=["review_bundler_symbol_scope"] if result.status in {"ready_for_review", "blocked"} else [], verification=verification, status=status, artifacts=[artifact], next_action=next_action, confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    return None


def dispatch_source_map_gateway_a(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Group A: branches before executor chain (dispatch_preflight, one_step_plan, chain_readiness)."""
    if owner._is_source_map_followthrough_dispatch_preflight_request(protection_name, context):
        spec = SourceMapFollowthroughDispatchPreflightSpec.from_context(context)
        result = SourceMapFollowthroughDispatchPreflightManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        dispatcher_input = descriptor.get("dispatcher_input") if isinstance(descriptor.get("dispatcher_input"), dict) else {}
        dispatch_target = descriptor.get("dispatch_target") if isinstance(descriptor.get("dispatch_target"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_dispatch_preflight_status={result.status}",
            f"source_map_followthrough_dispatch_preflight_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatch_preflight_planned_next_action={descriptor.get('planned_next_action', '')}",
            f"source_map_followthrough_dispatch_preflight_planned_required_artifact={descriptor.get('planned_required_artifact', '')}",
            f"source_map_followthrough_dispatch_preflight_dispatch_surface={dispatch_target.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatch_preflight_dispatcher_input_ready_for_review={descriptor.get('dispatcher_input_ready_for_review', False)}",
            f"source_map_followthrough_dispatch_preflight_dispatcher_invoked={dispatcher_input.get('dispatcher_invoked', False)}",
            "source_map_followthrough_dispatch_preflight_review_only=True",
            "source_map_followthrough_dispatch_preflight_preflight_only=True",
            "source_map_followthrough_dispatch_preflight_plan_only=True",
            "source_map_followthrough_dispatch_preflight_orchestration_only=True",
            "source_map_followthrough_dispatch_preflight_handoff_only=True",
            f"source_map_followthrough_dispatch_preflight_will_invoke_dispatch_target={descriptor.get('will_invoke_dispatch_target', False)}",
            f"source_map_followthrough_dispatch_preflight_will_invoke_next_action={descriptor.get('will_invoke_next_action', False)}",
            f"source_map_followthrough_dispatch_preflight_will_record_approval={descriptor.get('will_record_approval', False)}",
            f"source_map_followthrough_dispatch_preflight_will_run_apply_preflight={descriptor.get('will_run_apply_preflight', False)}",
            f"source_map_followthrough_dispatch_preflight_will_execute_debugger={descriptor.get('will_execute_debugger', False)}",
            f"source_map_followthrough_dispatch_preflight_will_install_hook={descriptor.get('will_install_hook', False)}",
            f"source_map_followthrough_dispatch_preflight_will_run_rebuild={descriptor.get('will_run_rebuild', False)}",
            f"source_map_followthrough_dispatch_preflight_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatch_preflight_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatch_preflight_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatch_preflight_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_dispatch_preflight_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatch_preflight_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatch_preflight_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatch_preflight_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatch_preflight_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatch_preflight_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatch-preflight.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through dispatch preflight descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "planned_next_action": descriptor.get("planned_next_action", ""), "planned_required_artifact": descriptor.get("planned_required_artifact", ""), "dispatch_surface": dispatch_target.get("dispatch_surface", ""), "dispatcher_input_ready_for_review": bool(descriptor.get("dispatcher_input_ready_for_review", False)), "review_only": True, "preflight_only": True, "plan_only": True, "dispatch_preflight_only": True, "orchestration_only": True, "handoff_only": True, "will_invoke_dispatch_target": False, "will_invoke_next_action": False, "will_record_approval": False, "will_run_apply_preflight": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call"
            actions = ["review_source_map_followthrough_dispatch_preflight"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatch_preflight_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatch_preflight_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_one_step_plan_request(protection_name, context):
        spec = SourceMapFollowthroughOneStepPlanSpec.from_context(context)
        result = SourceMapFollowthroughOneStepPlanManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        planned_step = descriptor.get("planned_step") if isinstance(descriptor.get("planned_step"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_one_step_plan_status={result.status}",
            f"source_map_followthrough_one_step_plan_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_one_step_plan_source_chain_completed_stage={descriptor.get('source_chain_completed_stage', '')}",
            f"source_map_followthrough_one_step_plan_source_chain_next_stage={descriptor.get('source_chain_next_stage', '')}",
            f"source_map_followthrough_one_step_plan_source_chain_next_action={descriptor.get('source_chain_next_action', '')}",
            f"source_map_followthrough_one_step_plan_next_required_artifact={descriptor.get('source_chain_next_required_artifact', '')}",
            f"source_map_followthrough_one_step_plan_planned_step_ready_for_review={descriptor.get('planned_step_ready_for_review', False)}",
            f"source_map_followthrough_one_step_plan_step_id={planned_step.get('step_id', '')}",
            "source_map_followthrough_one_step_plan_review_only=True",
            "source_map_followthrough_one_step_plan_plan_only=True",
            "source_map_followthrough_one_step_plan_orchestration_only=True",
            "source_map_followthrough_one_step_plan_handoff_only=True",
            f"source_map_followthrough_one_step_plan_will_invoke_next_action={descriptor.get('will_invoke_next_action', False)}",
            f"source_map_followthrough_one_step_plan_will_record_approval={descriptor.get('will_record_approval', False)}",
            f"source_map_followthrough_one_step_plan_will_run_apply_preflight={descriptor.get('will_run_apply_preflight', False)}",
            f"source_map_followthrough_one_step_plan_will_execute_debugger={descriptor.get('will_execute_debugger', False)}",
            f"source_map_followthrough_one_step_plan_will_install_hook={descriptor.get('will_install_hook', False)}",
            f"source_map_followthrough_one_step_plan_will_run_rebuild={descriptor.get('will_run_rebuild', False)}",
            f"source_map_followthrough_one_step_plan_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_one_step_plan_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_one_step_plan_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_one_step_plan_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_one_step_plan_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_one_step_plan_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_one_step_plan_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_one_step_plan_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_one_step_plan_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_one_step_plan_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-one-step-plan.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map follow-through one-step orchestration plan.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "source_chain_completed_stage": descriptor.get("source_chain_completed_stage", ""), "source_chain_next_stage": descriptor.get("source_chain_next_stage", ""), "source_chain_next_action": descriptor.get("source_chain_next_action", ""), "source_chain_next_required_artifact": descriptor.get("source_chain_next_required_artifact", ""), "planned_step_ready_for_review": bool(descriptor.get("planned_step_ready_for_review", False)), "step_id": planned_step.get("step_id", ""), "review_only": True, "plan_only": True, "one_step_plan_only": True, "orchestration_only": True, "handoff_only": True, "will_invoke_next_action": False, "will_record_approval": False, "will_run_apply_preflight": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_one_step_plan_before_next_action"
            actions = ["review_source_map_followthrough_one_step_plan"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_one_step_plan_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_one_step_plan_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_chain_readiness_request(protection_name, context):
        spec = SourceMapFollowthroughChainReadinessSpec.from_context(context)
        result = SourceMapFollowthroughChainReadinessManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_chain_readiness_status={result.status}",
            f"source_map_followthrough_chain_readiness_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_chain_readiness_completed_stage={descriptor.get('completed_stage', '')}",
            f"source_map_followthrough_chain_readiness_next_stage={descriptor.get('next_stage', '')}",
            f"source_map_followthrough_chain_readiness_next_required_artifact={descriptor.get('next_required_artifact', '')}",
            f"source_map_followthrough_chain_readiness_selected_executor_result_ready={descriptor.get('selected_executor_result_ready', False)}",
            f"source_map_followthrough_chain_readiness_ready_for_selected_executor_review={descriptor.get('ready_for_selected_executor_review', False)}",
            "source_map_followthrough_chain_readiness_review_only=True",
            "source_map_followthrough_chain_readiness_plan_only=True",
            "source_map_followthrough_chain_readiness_orchestration_only=True",
            "source_map_followthrough_chain_readiness_handoff_only=True",
            f"source_map_followthrough_chain_readiness_automatic_followthrough_supported={descriptor.get('automatic_followthrough_supported', False)}",
            f"source_map_followthrough_chain_readiness_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_chain_readiness_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_chain_readiness_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_chain_readiness_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_chain_readiness_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_chain_readiness_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_chain_readiness_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_chain_readiness_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_chain_readiness_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_chain_readiness_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-chain-readiness.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through chain readiness descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "completed_stage": descriptor.get("completed_stage", ""), "next_stage": descriptor.get("next_stage", ""), "next_required_artifact": descriptor.get("next_required_artifact", ""), "next_required_action": descriptor.get("next_required_action", ""), "selected_executor_result_ready": bool(descriptor.get("selected_executor_result_ready", False)), "ready_for_selected_executor_review": bool(descriptor.get("ready_for_selected_executor_review", False)), "review_only": True, "plan_only": True, "readiness_descriptor_only": True, "orchestration_only": True, "handoff_only": True, "automatic_followthrough_supported": False, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_chain_readiness"
            actions = ["review_source_map_followthrough_chain_readiness"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_followthrough_chain_evidence"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_chain_readiness_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    return None


def dispatch_source_map_gateway_b(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Group B: branches after executor chain (terminal_review_package through readiness)."""
    if owner._is_source_map_terminal_review_package_request(protection_name, context):
        spec = SourceMapTerminalReviewPackageSpec.from_context(context)
        result = SourceMapTerminalReviewPackageManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        package = descriptor.get("terminal_review_package") if isinstance(descriptor.get("terminal_review_package"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_terminal_review_package_status={result.status}",
            f"source_map_terminal_review_package_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_terminal_review_package_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_terminal_review_package_completion_status={descriptor.get('completion_status', '')}",
            f"source_map_terminal_review_package_terminal_review_candidate={descriptor.get('terminal_review_candidate', False)}",
            f"source_map_terminal_review_package_followup_required={descriptor.get('followup_required', False)}",
            f"source_map_terminal_review_package_ready_for_terminal_review={descriptor.get('ready_for_terminal_review', False)}",
            f"source_map_terminal_review_package_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_terminal_review_package_recommended_review_action={package.get('recommended_review_action', '')}",
            f"source_map_terminal_review_package_package_kind={package.get('package_kind', '')}",
            f"source_map_terminal_review_package_source_completion_checkpoint_digest={descriptor.get('source_completion_checkpoint_digest_sha256', '')}",
            "source_map_terminal_review_package_review_only=True",
            "source_map_terminal_review_package_audit_handoff_only=True",
            "source_map_terminal_review_package_terminal_review_package_only=True",
            f"source_map_terminal_review_package_recommended_action_executed={descriptor.get('recommended_action_executed', False)}",
            f"source_map_terminal_review_package_browser_started_by_package={policy.get('browser_started', False)}",
            f"source_map_terminal_review_package_cdp_command_sent_by_package={policy.get('cdp_command_sent', False)}",
            f"source_map_terminal_review_package_runtime_evaluated_by_package={policy.get('runtime_evaluated', False)}",
            f"source_map_terminal_review_package_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_terminal_review_package_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_terminal_review_package_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_terminal_review_package_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-terminal-review-package.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map terminal review package / audit handoff.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "completion_status": descriptor.get("completion_status", ""), "terminal_review_candidate": bool(descriptor.get("terminal_review_candidate", False)), "followup_required": bool(descriptor.get("followup_required", False)), "package_kind": package.get("package_kind", ""), "recommended_review_action": package.get("recommended_review_action", ""), "source_completion_checkpoint_digest_sha256": descriptor.get("source_completion_checkpoint_digest_sha256", ""), "ready_for_terminal_review": bool(descriptor.get("ready_for_terminal_review", False)), "ready_for_audit_handoff_review": bool(descriptor.get("ready_for_audit_handoff_review", False)), "ready_to_execute_now": False, "execute_next_automatically": False, "automatic_followthrough_supported": False, "recommended_action_executed": False, "review_only": True, "audit_handoff_only": True, "terminal_review_package_only": True, "browser_started_by_package": False, "cdp_command_sent_by_package": False, "runtime_evaluated_by_package": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_terminal_review_package"
            actions = ["review_source_map_terminal_review_package"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_followthrough_completion_checkpoint"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_terminal_review_package_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_surface_selection_request(protection_name, context):
        spec = SourceMapFollowthroughSurfaceSelectionSpec.from_context(context)
        result = SourceMapFollowthroughSurfaceSelectionManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        selected_review = descriptor.get("selected_review") if isinstance(descriptor.get("selected_review"), dict) else {}
        verification = [
            f"source_map_followthrough_surface_selection_status={result.status}",
            f"source_map_followthrough_surface_selection_candidate_count={descriptor.get('candidate_review_count', 0)}",
            f"source_map_followthrough_surface_selection_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_followthrough_surface_selection_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_surface_selection_selected_surface={descriptor.get('selected_followthrough_review_surface', '')}",
            f"source_map_followthrough_surface_selection_ready_for_surface_review={descriptor.get('ready_for_surface_review', False)}",
            "source_map_followthrough_surface_selection_review_only=True",
            "source_map_followthrough_surface_selection_plan_only=True",
            "source_map_followthrough_surface_selection_selection_only=True",
            "source_map_followthrough_surface_selection_handoff_only=True",
            f"source_map_followthrough_surface_selection_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_followthrough_surface_selection_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_followthrough_surface_selection_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_followthrough_surface_selection_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_surface_selection_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_surface_selection_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_followthrough_surface_selection_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_surface_selection_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_surface_selection_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_surface_selection_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_surface_selection_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_surface_selection_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_surface_selection_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_surface_selection_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-surface-selection.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map follow-through single-surface selection descriptor.", metadata={"status": result.status, "candidate_review_count": descriptor.get("candidate_review_count", 0), "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "selected_payload_kind": selected_review.get("payload_kind", ""), "ready_for_surface_review": bool(descriptor.get("ready_for_surface_review", False)), "review_only": True, "plan_only": True, "selection_only": True, "handoff_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_selected_source_map_followthrough_surface_before_execution"
            actions = ["select_source_map_followthrough_surface"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_followthrough_review_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_surface_selection_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_review_request(protection_name, context):
        spec = SourceMapFollowthroughReviewSpec.from_context(context)
        result = SourceMapFollowthroughReviewManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        reviews = descriptor.get("followthrough_reviews") if isinstance(descriptor.get("followthrough_reviews"), list) else []
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        consumers = sorted({str(item.get("consumer")) for item in reviews if isinstance(item, dict) and item.get("consumer")})
        surfaces = sorted({str(item.get("followthrough_review_surface")) for item in reviews if isinstance(item, dict) and item.get("followthrough_review_surface")})
        verification = [
            f"source_map_followthrough_review_status={result.status}",
            f"source_map_followthrough_review_count={len(reviews)}",
            f"source_map_followthrough_review_ready_count={descriptor.get('ready_followthrough_review_count', 0)}",
            f"source_map_followthrough_review_consumers={','.join(consumers)}",
            f"source_map_followthrough_review_surfaces={','.join(surfaces)}",
            f"source_map_followthrough_review_schema_version={descriptor.get('typed_payload_schema_version', '')}",
            f"source_map_followthrough_review_ready_for_explicit_review={descriptor.get('ready_for_explicit_review', False)}",
            "source_map_followthrough_review_review_only=True",
            "source_map_followthrough_review_plan_only=True",
            "source_map_followthrough_review_handoff_only=True",
            f"source_map_followthrough_review_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_followthrough_review_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_followthrough_review_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_followthrough_review_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_review_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_review_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_followthrough_review_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_review_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_review_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_review_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_review_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_review_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_review_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_review_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-review.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map follow-through review surface descriptor.", metadata={"status": result.status, "typed_payload_schema_version": descriptor.get("typed_payload_schema_version", ""), "followthrough_review_count": len(reviews), "ready_followthrough_review_count": descriptor.get("ready_followthrough_review_count", 0), "consumers": consumers, "followthrough_review_surfaces": surfaces, "ready_for_explicit_review": bool(descriptor.get("ready_for_explicit_review", False)), "review_only": True, "plan_only": True, "handoff_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "choose_explicit_source_map_followthrough_review_surface"
            actions = ["review_source_map_followthrough_review"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_typed_payload_preflight_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_review_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_typed_payload_preflight_request(protection_name, context):
        spec = SourceMapTypedPayloadPreflightSpec.from_context(context)
        result = SourceMapTypedPayloadPreflightManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        preflights = descriptor.get("preflight_payloads") if isinstance(descriptor.get("preflight_payloads"), list) else []
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        consumers = sorted({str(item.get("consumer")) for item in preflights if isinstance(item, dict) and item.get("consumer")})
        surfaces = sorted({str(item.get("followthrough_review_surface")) for item in preflights if isinstance(item, dict) and item.get("followthrough_review_surface")})
        verification = [
            f"source_map_typed_payload_preflight_status={result.status}",
            f"source_map_typed_payload_preflight_count={len(preflights)}",
            f"source_map_typed_payload_preflight_consumers={','.join(consumers)}",
            f"source_map_typed_payload_preflight_surfaces={','.join(surfaces)}",
            f"source_map_typed_payload_preflight_schema_version={descriptor.get('typed_payload_schema_version', '')}",
            f"source_map_typed_payload_preflight_ready_for_followthrough_review={descriptor.get('ready_for_followthrough_review', False)}",
            "source_map_typed_payload_preflight_review_only=True",
            "source_map_typed_payload_preflight_plan_only=True",
            "source_map_typed_payload_preflight_preflight_only=True",
            f"source_map_typed_payload_preflight_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_typed_payload_preflight_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_typed_payload_preflight_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_typed_payload_preflight_browser_started={policy.get('browser_started', False)}",
            f"source_map_typed_payload_preflight_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_typed_payload_preflight_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_typed_payload_preflight_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_typed_payload_preflight_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_typed_payload_preflight_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_typed_payload_preflight_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_typed_payload_preflight_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_typed_payload_preflight_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_typed_payload_preflight_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_typed_payload_preflight_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-typed-payload-preflight.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map typed payload follow-through preflight descriptor.", metadata={"status": result.status, "typed_payload_schema_version": descriptor.get("typed_payload_schema_version", ""), "preflight_payload_count": len(preflights), "consumers": consumers, "followthrough_review_surfaces": surfaces, "ready_for_followthrough_review": bool(descriptor.get("ready_for_followthrough_review", False)), "review_only": True, "plan_only": True, "preflight_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution"
            actions = ["review_source_map_typed_payload_preflight"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_consumer_materialization_with_typed_payloads"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_typed_payload_preflight_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_consumer_materialization_request(protection_name, context):
        spec = SourceMapConsumerMaterializationSpec.from_context(context)
        result = SourceMapConsumerMaterializationManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        materializations = descriptor.get("materializations") if isinstance(descriptor.get("materializations"), list) else []
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        consumers = sorted({str(item.get("consumer")) for item in materializations if isinstance(item, dict) and item.get("consumer")})
        kinds = sorted({str(item.get("materialization_kind")) for item in materializations if isinstance(item, dict) and item.get("materialization_kind")})
        typed_payloads = descriptor.get("typed_review_payloads")
        if not isinstance(typed_payloads, list):
            typed_payloads = []
        typed_payload_count = len([item for item in typed_payloads if isinstance(item, dict)])
        typed_payload_consumers = sorted({str(item.get("consumer")) for item in typed_payloads if isinstance(item, dict) and item.get("consumer")})
        typed_payload_schema_version = str(descriptor.get("typed_payload_schema_version") or "")
        verification = [
            f"source_map_consumer_materialization_status={result.status}",
            f"source_map_consumer_materialization_count={len(materializations)}",
            f"source_map_consumer_materialization_consumers={','.join(consumers)}",
            f"source_map_consumer_materialization_kinds={','.join(kinds)}",
            f"source_map_consumer_materialization_typed_payload_schema_version={typed_payload_schema_version}",
            f"source_map_consumer_materialization_typed_payload_count={typed_payload_count}",
            f"source_map_consumer_materialization_typed_payload_consumers={','.join(typed_payload_consumers)}",
            "source_map_consumer_materialization_review_only=True",
            "source_map_consumer_materialization_plan_only=True",
            f"source_map_consumer_materialization_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_consumer_materialization_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_consumer_materialization_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_consumer_materialization_browser_started={policy.get('browser_started', False)}",
            f"source_map_consumer_materialization_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_consumer_materialization_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_consumer_materialization_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_consumer_materialization_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_consumer_materialization_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_consumer_materialization_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_consumer_materialization_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_consumer_materialization_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_consumer_materialization_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_consumer_materialization_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-consumer-materialization.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map consumer materialization descriptor.", metadata={"status": result.status, "materialization_count": len(materializations), "consumers": consumers, "materialization_kinds": kinds, "typed_payload_schema_version": typed_payload_schema_version, "typed_review_payload_count": typed_payload_count, "typed_review_payload_consumers": typed_payload_consumers, "review_only": True, "plan_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution"
            actions = ["review_source_map_consumer_materialization"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_consumer_action_plan_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_consumer_materialization_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_consumer_action_plan_request(protection_name, context):
        spec = SourceMapConsumerActionPlanSpec.from_context(context)
        result = SourceMapConsumerActionPlanManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        evidence_status = descriptor.get("evidence_status") if isinstance(descriptor.get("evidence_status"), dict) else {}
        readiness = evidence_status.get("readiness") if isinstance(evidence_status.get("readiness"), dict) else {}
        action_plans = descriptor.get("action_plans") if isinstance(descriptor.get("action_plans"), list) else []
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        consumers = sorted({str(item.get("consumer")) for item in action_plans if isinstance(item, dict) and item.get("consumer")})
        verification = [
            f"source_map_consumer_action_plan_status={result.status}",
            f"source_map_consumer_action_plan_count={len(action_plans)}",
            f"source_map_consumer_action_plan_consumers={','.join(consumers)}",
            f"source_map_consumer_action_plan_debugger_location_ready={readiness.get('debugger_location_ready', False)}",
            f"source_map_consumer_action_plan_rebuild_source_metadata_ready={readiness.get('rebuild_source_metadata_ready', False)}",
            f"source_map_consumer_action_plan_source_logpoint_planning_ready={readiness.get('source_logpoint_planning_ready', False)}",
            "source_map_consumer_action_plan_review_only=True",
            "source_map_consumer_action_plan_plan_only=True",
            f"source_map_consumer_action_plan_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_consumer_action_plan_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_consumer_action_plan_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_consumer_action_plan_browser_started={policy.get('browser_started', False)}",
            f"source_map_consumer_action_plan_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_consumer_action_plan_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_consumer_action_plan_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_consumer_action_plan_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_consumer_action_plan_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_consumer_action_plan_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_consumer_action_plan_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_consumer_action_plan_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_consumer_action_plan_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-consumer-action-plan.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map consumer action plan descriptor.", metadata={"status": result.status, "action_plan_count": len(action_plans), "consumers": consumers, "review_only": True, "plan_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution"
            actions = ["review_source_map_consumer_action_plan"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_readiness_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_consumer_action_plan_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_readiness_request(protection_name, context):
        spec = SourceMapReadinessSpec.from_context(context)
        result = SourceMapReadinessManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        readiness = descriptor.get("readiness") if isinstance(descriptor.get("readiness"), dict) else {}
        evidence_status = descriptor.get("evidence_status") if isinstance(descriptor.get("evidence_status"), dict) else {}
        source_content = evidence_status.get("source_content") if isinstance(evidence_status.get("source_content"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_readiness_status={result.status}",
            f"source_map_readiness_debugger_location_ready={readiness.get('debugger_location_ready', False)}",
            f"source_map_readiness_source_content_metadata_ready={readiness.get('source_content_metadata_ready', False)}",
            f"source_map_readiness_rebuild_source_metadata_ready={readiness.get('rebuild_source_metadata_ready', False)}",
            f"source_map_readiness_source_logpoint_planning_ready={readiness.get('source_logpoint_planning_ready', False)}",
            f"source_map_readiness_bundler_scope_review_ready={readiness.get('bundler_scope_review_ready', False)}",
            f"source_map_readiness_source_content_sha256={source_content.get('sha256', '')}",
            "source_map_readiness_review_only=True",
            f"source_map_readiness_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_readiness_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_readiness_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_readiness_browser_started={policy.get('browser_started', False)}",
            f"source_map_readiness_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_readiness_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_readiness_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_readiness_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_readiness_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_readiness_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_readiness_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-readiness.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map readiness descriptor.", metadata={"status": result.status, "debugger_location_ready": bool(readiness.get("debugger_location_ready", False)), "source_content_metadata_ready": bool(readiness.get("source_content_metadata_ready", False)), "rebuild_source_metadata_ready": bool(readiness.get("rebuild_source_metadata_ready", False)), "source_logpoint_planning_ready": bool(readiness.get("source_logpoint_planning_ready", False)), "bundler_scope_review_ready": bool(readiness.get("bundler_scope_review_ready", False)), "sha256": source_content.get("sha256", ""), "review_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning"
            actions = ["review_source_map_readiness"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_lookup_and_source_content_descriptors"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_readiness_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    return None


def dispatch_source_map_gateway_c(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Group C: read-only branches from the first half (hook/debugger candidate review) and second half (selected-executor / terminal-review)."""
    if owner._is_source_map_hook_candidate_selection_request(protection_name, context):
        spec = SourceMapHookCandidateSelectionSpec.from_context(context)
        result = SourceMapHookCandidateSelectionManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_hook_candidate_selection_status={result.status}",
            f"source_map_hook_candidate_selection_source_status={descriptor.get('source_candidates_status', '')}",
            f"source_map_hook_candidate_selection_candidate_count={descriptor.get('candidate_count', 0)}",
            f"source_map_hook_candidate_selection_selected_candidate_id={descriptor.get('selected_candidate_id', '')}",
            f"source_map_hook_candidate_selection_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_hook_candidate_selection_ready_for_input_review={descriptor.get('ready_for_selected_executor_input_review', False)}",
            "source_map_hook_candidate_selection_review_only=True",
            "source_map_hook_candidate_selection_plan_only=True",
            "source_map_hook_candidate_selection_handoff_only=True",
            f"source_map_hook_candidate_selection_browser_started={policy.get('browser_started', False)}",
            f"source_map_hook_candidate_selection_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_hook_candidate_selection_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_hook_candidate_selection_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_hook_candidate_selection_automatic_hook_installation={policy.get('automatic_hook_installation', False)}",
            f"source_map_hook_candidate_selection_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_hook_candidate_selection_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_hook_candidate_selection_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_hook_candidate_selection_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-hook-candidate-selection.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map hook candidate selection handoff descriptor.", metadata={"schema_version": "reverse-deepagent.source-map-hook-candidate-selection.v1", "status": result.status, "review_only": True, "plan_only": True, "selection_only": True, "handoff_only": True, "candidate_count": descriptor.get("candidate_count", 0), "selected_candidate_id": descriptor.get("selected_candidate_id", ""), "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "ready_for_selected_executor_input_review": bool(descriptor.get("ready_for_selected_executor_input_review", False)), "blockers": descriptor.get("blockers", []), "warnings": descriptor.get("warnings", []), "browser_started": False, "runtime_evaluated": False, "cdp_command_sent": False, "hook_installed": False, "automatic_hook_installation": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "run_source_map_selected_executor_input_review_for_selected_hook_candidate"
            actions = ["select_source_map_hook_candidate"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_hook_candidate_selection_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_hook_candidate_selection_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_hook_candidate_refinement_request(protection_name, context):
        spec = SourceMapHookCandidateRefinementSpec.from_context(context)
        result = SourceMapHookCandidateRefinementManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        candidates = descriptor.get("candidates") if isinstance(descriptor.get("candidates"), list) else []
        source_status = descriptor.get("source_status") if isinstance(descriptor.get("source_status"), dict) else {}
        verification = [
            f"source_map_hook_candidates_status={result.status}",
            f"source_map_hook_candidates_bundler={descriptor.get('bundler_kind', 'unknown')}",
            f"source_map_hook_candidates_symbol={descriptor.get('requested_symbol', '')}",
            f"source_map_hook_candidates_source_scope_candidate_count={descriptor.get('source_scope_candidate_count', 0)}",
            f"source_map_hook_candidates_candidate_count={descriptor.get('candidate_count', 0)}",
            f"source_map_hook_candidates_ready_for_install_review_count={descriptor.get('ready_for_hook_install_review_count', 0)}",
            f"source_map_hook_candidates_typed_hook_payload_ready={source_status.get('typed_hook_payload_ready', False)}",
            "source_map_hook_candidates_review_only=True",
            "source_map_hook_candidates_plan_only=True",
            f"source_map_hook_candidates_browser_started={policy.get('browser_started', False)}",
            f"source_map_hook_candidates_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_hook_candidates_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_hook_candidates_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_hook_candidates_automatic_hook_installation={policy.get('automatic_hook_installation', False)}",
            f"source_map_hook_candidates_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_hook_candidates_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_hook_candidates_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_hook_candidates_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-hook-candidates.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map hook candidate refinement descriptor.", metadata={"schema_version": "reverse-deepagent.source-map-hook-candidates.v1", "status": result.status, "review_only": True, "plan_only": True, "candidate_refinement_only": True, "requested_symbol": descriptor.get("requested_symbol", ""), "bundler_kind": descriptor.get("bundler_kind", "unknown"), "source_scope_candidate_count": descriptor.get("source_scope_candidate_count", 0), "module_candidate_count": descriptor.get("module_candidate_count", 0), "candidate_count": descriptor.get("candidate_count", 0), "ready_for_hook_install_review_count": descriptor.get("ready_for_hook_install_review_count", 0), "candidate_ids": [str(item.get("candidate_id")) for item in candidates if isinstance(item, dict) and item.get("candidate_id")], "blockers": descriptor.get("blockers", []), "warnings": descriptor.get("warnings", []), "browser_started": False, "runtime_evaluated": False, "cdp_command_sent": False, "hook_installed": False, "automatic_hook_installation": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_hook_candidates_before_selected_hook_install"
            actions = ["refine_source_map_hook_candidates"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_hook_candidate_refinement_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_hook_candidate_refinement_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_debugger_candidate_selection_request(protection_name, context):
        spec = SourceMapDebuggerCandidateSelectionSpec.from_context(context)
        result = SourceMapDebuggerCandidateSelectionManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_debugger_candidate_selection_status={result.status}",
            f"source_map_debugger_candidate_selection_source_status={descriptor.get('source_candidates_status', '')}",
            f"source_map_debugger_candidate_selection_candidate_count={descriptor.get('candidate_count', 0)}",
            f"source_map_debugger_candidate_selection_selected_candidate_id={descriptor.get('selected_candidate_id', '')}",
            f"source_map_debugger_candidate_selection_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_debugger_candidate_selection_ready_for_input_review={descriptor.get('ready_for_selected_executor_input_review', False)}",
            "source_map_debugger_candidate_selection_review_only=True",
            "source_map_debugger_candidate_selection_plan_only=True",
            "source_map_debugger_candidate_selection_handoff_only=True",
            f"source_map_debugger_candidate_selection_browser_started={policy.get('browser_started', False)}",
            f"source_map_debugger_candidate_selection_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_debugger_candidate_selection_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_debugger_candidate_selection_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_debugger_candidate_selection_breakpoint_installed={policy.get('breakpoint_installed', False)}",
            f"source_map_debugger_candidate_selection_automatic_debugger_continuation={policy.get('automatic_debugger_continuation', False)}",
            f"source_map_debugger_candidate_selection_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_debugger_candidate_selection_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_debugger_candidate_selection_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_debugger_candidate_selection_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-debugger-candidate-selection.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map debugger candidate selection handoff descriptor.", metadata={"schema_version": "reverse-deepagent.source-map-debugger-candidate-selection.v1", "status": result.status, "review_only": True, "plan_only": True, "selection_only": True, "handoff_only": True, "candidate_count": descriptor.get("candidate_count", 0), "selected_candidate_id": descriptor.get("selected_candidate_id", ""), "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "ready_for_selected_executor_input_review": bool(descriptor.get("ready_for_selected_executor_input_review", False)), "blockers": descriptor.get("blockers", []), "warnings": descriptor.get("warnings", []), "browser_started": False, "runtime_evaluated": False, "cdp_command_sent": False, "debugger_execution_performed": False, "breakpoint_installed": False, "automatic_debugger_continuation": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "run_source_map_selected_executor_input_review_for_selected_debugger_candidate"
            actions = ["select_source_map_debugger_candidate"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_debugger_candidate_selection_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_debugger_candidate_selection_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_debugger_candidate_review_request(protection_name, context):
        spec = SourceMapDebuggerCandidateReviewSpec.from_context(context)
        result = SourceMapDebuggerCandidateReviewManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        candidates = descriptor.get("candidates") if isinstance(descriptor.get("candidates"), list) else []
        source_status = descriptor.get("source_status") if isinstance(descriptor.get("source_status"), dict) else {}
        verification = [
            f"source_map_debugger_candidates_status={result.status}",
            f"source_map_debugger_candidates_bundler={descriptor.get('bundler_kind', 'unknown')}",
            f"source_map_debugger_candidates_symbol={descriptor.get('requested_symbol', '')}",
            f"source_map_debugger_candidates_source_scope_candidate_count={descriptor.get('source_scope_candidate_count', 0)}",
            f"source_map_debugger_candidates_lookup_candidate_count={descriptor.get('lookup_candidate_count', 0)}",
            f"source_map_debugger_candidates_candidate_count={descriptor.get('candidate_count', 0)}",
            f"source_map_debugger_candidates_ready_for_location_review_count={descriptor.get('ready_for_debugger_location_review_count', 0)}",
            f"source_map_debugger_candidates_typed_debugger_payload_ready={source_status.get('typed_debugger_payload_ready', False)}",
            "source_map_debugger_candidates_review_only=True",
            "source_map_debugger_candidates_plan_only=True",
            f"source_map_debugger_candidates_browser_started={policy.get('browser_started', False)}",
            f"source_map_debugger_candidates_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_debugger_candidates_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_debugger_candidates_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_debugger_candidates_breakpoint_installed={policy.get('breakpoint_installed', False)}",
            f"source_map_debugger_candidates_automatic_debugger_continuation={policy.get('automatic_debugger_continuation', False)}",
            f"source_map_debugger_candidates_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_debugger_candidates_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_debugger_candidates_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_debugger_candidates_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-debugger-candidates.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map debugger location candidate descriptor.", metadata={"schema_version": "reverse-deepagent.source-map-debugger-candidates.v1", "status": result.status, "review_only": True, "plan_only": True, "candidate_review_only": True, "requested_symbol": descriptor.get("requested_symbol", ""), "bundler_kind": descriptor.get("bundler_kind", "unknown"), "source_scope_candidate_count": descriptor.get("source_scope_candidate_count", 0), "lookup_candidate_count": descriptor.get("lookup_candidate_count", 0), "candidate_count": descriptor.get("candidate_count", 0), "ready_for_debugger_location_review_count": descriptor.get("ready_for_debugger_location_review_count", 0), "candidate_ids": [str(item.get("candidate_id")) for item in candidates if isinstance(item, dict) and item.get("candidate_id")], "blockers": descriptor.get("blockers", []), "warnings": descriptor.get("warnings", []), "browser_started": False, "runtime_evaluated": False, "cdp_command_sent": False, "debugger_execution_performed": False, "breakpoint_installed": False, "automatic_debugger_continuation": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_debugger_candidates_before_selected_debugger_apply"
            actions = ["review_source_map_debugger_candidates"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_debugger_candidate_review_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_debugger_candidate_review_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_selected_executor_application_handoff_request(protection_name, context):
        spec = SourceMapSelectedExecutorApplicationHandoffSpec.from_context(context)
        result = SourceMapSelectedExecutorApplicationHandoffManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        review_input = descriptor.get("application_review_input") if isinstance(descriptor.get("application_review_input"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_selected_executor_application_handoff_status={result.status}",
            f"source_map_selected_executor_application_handoff_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_selected_executor_application_handoff_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_selected_executor_application_handoff_selected_gate={descriptor.get('selected_review_gate', '')}",
            f"source_map_selected_executor_application_handoff_application_surface={descriptor.get('application_surface', '')}",
            f"source_map_selected_executor_application_handoff_application_input_key={descriptor.get('application_input_key', '')}",
            f"source_map_selected_executor_application_handoff_ready_for_application_review={descriptor.get('ready_for_application_review', False)}",
            f"source_map_selected_executor_application_handoff_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_selected_executor_application_handoff_approval_record_verified={descriptor.get('approval_record_verified', False)}",
            f"source_map_selected_executor_application_handoff_executor_input_ready={descriptor.get('executor_input_ready', False)}",
            f"source_map_selected_executor_application_handoff_source_digest={descriptor.get('source_apply_preflight_digest_sha256', '')}",
            f"source_map_selected_executor_application_handoff_future_result_artifact={descriptor.get('future_result_artifact', '')}",
            "source_map_selected_executor_application_handoff_review_only=True",
            "source_map_selected_executor_application_handoff_plan_only=True",
            "source_map_selected_executor_application_handoff_handoff_only=True",
            f"source_map_selected_executor_application_handoff_browser_started={policy.get('browser_started', False)}",
            f"source_map_selected_executor_application_handoff_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_application_handoff_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_application_handoff_logpoint_installed={policy.get('logpoint_installed', policy.get('source_logpoint_installed', False))}",
            f"source_map_selected_executor_application_handoff_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_selected_executor_application_handoff_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_selected_executor_application_handoff_surface_executor_invoked={policy.get('surface_executor_invoked', False)}",
            f"source_map_selected_executor_application_handoff_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_selected_executor_application_handoff_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_selected_executor_application_handoff_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_selected_executor_application_handoff_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-selected-executor-application-handoff.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map selected executor application handoff descriptor.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_review_gate": descriptor.get("selected_review_gate", ""), "application_surface": descriptor.get("application_surface", ""), "application_review_action": descriptor.get("application_review_action", ""), "application_input_key": descriptor.get("application_input_key", ""), "required_approval_flags": descriptor.get("required_approval_flags", []), "future_action": descriptor.get("future_action", ""), "future_result_artifact": descriptor.get("future_result_artifact", ""), "source_apply_preflight_digest_sha256": descriptor.get("source_apply_preflight_digest_sha256", ""), "application_review_input_schema_version": review_input.get("schema_version", ""), "approval_record_verified": bool(descriptor.get("approval_record_verified", False)), "executor_input_ready": bool(descriptor.get("executor_input_ready", False)), "ready_for_application_review": bool(descriptor.get("ready_for_application_review", False)), "ready_to_execute_now": False, "review_only": True, "plan_only": True, "handoff_only": True, "application_handoff_only": True, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "surface_executor_invoked": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or descriptor.get("application_review_action") or "review_source_map_selected_executor_application"
            actions = ["review_source_map_selected_executor_application_handoff"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_selected_executor_apply_preflight"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_selected_executor_application_handoff_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_selected_executor_result_checkpoint_request(protection_name, context):
        spec = SourceMapSelectedExecutorResultCheckpointSpec.from_context(context)
        result = SourceMapSelectedExecutorResultCheckpointManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        checkpoint_review = descriptor.get("checkpoint_review") if isinstance(descriptor.get("checkpoint_review"), dict) else {}
        observed = descriptor.get("observed_application_side_effects") if isinstance(descriptor.get("observed_application_side_effects"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_selected_executor_result_checkpoint_status={result.status}",
            f"source_map_selected_executor_result_checkpoint_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_selected_executor_result_checkpoint_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_selected_executor_result_checkpoint_selected_gate={descriptor.get('selected_review_gate', '')}",
            f"source_map_selected_executor_result_checkpoint_application_surface={descriptor.get('application_surface', '')}",
            f"source_map_selected_executor_result_checkpoint_application_result_status={descriptor.get('application_result_status', '')}",
            f"source_map_selected_executor_result_checkpoint_application_result_verified={descriptor.get('application_result_verified', False)}",
            f"source_map_selected_executor_result_checkpoint_ready_for_next_explicit_review={descriptor.get('ready_for_next_explicit_review', False)}",
            f"source_map_selected_executor_result_checkpoint_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_selected_executor_result_checkpoint_result_success_key={descriptor.get('result_success_key', '')}",
            f"source_map_selected_executor_result_checkpoint_result_success={descriptor.get('result_success', False)}",
            f"source_map_selected_executor_result_checkpoint_result_digest={descriptor.get('application_result_digest_sha256', '')}",
            f"source_map_selected_executor_result_checkpoint_handoff_verified={descriptor.get('application_handoff_verified', False)}",
            f"source_map_selected_executor_result_checkpoint_review_kind={checkpoint_review.get('result_kind', '')}",
            f"source_map_selected_executor_result_checkpoint_terminal_candidate={checkpoint_review.get('terminal_checkpoint_candidate', False)}",
            "source_map_selected_executor_result_checkpoint_review_only=True",
            "source_map_selected_executor_result_checkpoint_checkpoint_only=True",
            f"source_map_selected_executor_result_checkpoint_observed_browser_started={observed.get('browser_started', False)}",
            f"source_map_selected_executor_result_checkpoint_observed_cdp_command_sent={observed.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_result_checkpoint_observed_runtime_evaluated={observed.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_result_checkpoint_browser_started_by_checkpoint={policy.get('browser_started', False)}",
            f"source_map_selected_executor_result_checkpoint_cdp_command_sent_by_checkpoint={policy.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_result_checkpoint_runtime_evaluated_by_checkpoint={policy.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_result_checkpoint_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_selected_executor_result_checkpoint_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_selected_executor_result_checkpoint_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_selected_executor_result_checkpoint_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-selected-executor-result-checkpoint.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map selected executor application result checkpoint.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_review_gate": descriptor.get("selected_review_gate", ""), "application_surface": descriptor.get("application_surface", ""), "application_result_artifact": descriptor.get("application_result_artifact", ""), "application_result_status": descriptor.get("application_result_status", ""), "application_result_digest_sha256": descriptor.get("application_result_digest_sha256", ""), "application_result_verified": bool(descriptor.get("application_result_verified", False)), "application_handoff_verified": bool(descriptor.get("application_handoff_verified", False)), "result_success_key": descriptor.get("result_success_key", ""), "result_success": bool(descriptor.get("result_success", False)), "ready_for_followthrough_checkpoint_review": bool(descriptor.get("ready_for_followthrough_checkpoint_review", False)), "ready_for_next_explicit_review": bool(descriptor.get("ready_for_next_explicit_review", False)), "ready_to_execute_now": False, "execute_next_automatically": False, "automatic_followthrough_supported": False, "review_only": True, "checkpoint_only": True, "browser_started_by_checkpoint": False, "cdp_command_sent_by_checkpoint": False, "runtime_evaluated_by_checkpoint": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_selected_executor_result_checkpoint"
            actions = ["review_source_map_selected_executor_result_checkpoint"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_selected_executor_application_result"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_selected_executor_result_checkpoint_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_completion_checkpoint_request(protection_name, context):
        spec = SourceMapFollowthroughCompletionCheckpointSpec.from_context(context)
        result = SourceMapFollowthroughCompletionCheckpointManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        completion_review = descriptor.get("completion_review") if isinstance(descriptor.get("completion_review"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_completion_checkpoint_status={result.status}",
            f"source_map_followthrough_completion_checkpoint_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_followthrough_completion_checkpoint_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_completion_checkpoint_selected_gate={descriptor.get('selected_review_gate', '')}",
            f"source_map_followthrough_completion_checkpoint_application_surface={descriptor.get('application_surface', '')}",
            f"source_map_followthrough_completion_checkpoint_completion_status={descriptor.get('completion_status', '')}",
            f"source_map_followthrough_completion_checkpoint_terminal_review_candidate={descriptor.get('terminal_review_candidate', False)}",
            f"source_map_followthrough_completion_checkpoint_followup_required={descriptor.get('followup_required', False)}",
            f"source_map_followthrough_completion_checkpoint_ready_for_completion_review={descriptor.get('ready_for_completion_review', False)}",
            f"source_map_followthrough_completion_checkpoint_ready_for_next_explicit_review={descriptor.get('ready_for_next_explicit_review', False)}",
            f"source_map_followthrough_completion_checkpoint_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_followthrough_completion_checkpoint_recommended_review_action={completion_review.get('recommended_review_action', '')}",
            f"source_map_followthrough_completion_checkpoint_source_result_checkpoint_digest={descriptor.get('source_result_checkpoint_digest_sha256', '')}",
            f"source_map_followthrough_completion_checkpoint_source_chain_readiness_digest={descriptor.get('source_chain_readiness_digest_sha256', '')}",
            "source_map_followthrough_completion_checkpoint_review_only=True",
            "source_map_followthrough_completion_checkpoint_checkpoint_only=True",
            "source_map_followthrough_completion_checkpoint_completion_checkpoint_only=True",
            f"source_map_followthrough_completion_checkpoint_browser_started_by_completion={policy.get('browser_started', False)}",
            f"source_map_followthrough_completion_checkpoint_cdp_command_sent_by_completion={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_completion_checkpoint_runtime_evaluated_by_completion={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_completion_checkpoint_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_completion_checkpoint_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_completion_checkpoint_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_completion_checkpoint_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-completion-checkpoint.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through completion / next-action checkpoint.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_review_gate": descriptor.get("selected_review_gate", ""), "application_surface": descriptor.get("application_surface", ""), "completion_status": descriptor.get("completion_status", ""), "terminal_review_candidate": bool(descriptor.get("terminal_review_candidate", False)), "followup_required": bool(descriptor.get("followup_required", False)), "recommended_review_action": completion_review.get("recommended_review_action", ""), "source_result_checkpoint_digest_sha256": descriptor.get("source_result_checkpoint_digest_sha256", ""), "source_chain_readiness_digest_sha256": descriptor.get("source_chain_readiness_digest_sha256", ""), "ready_for_completion_review": bool(descriptor.get("ready_for_completion_review", False)), "ready_for_next_explicit_review": bool(descriptor.get("ready_for_next_explicit_review", False)), "ready_to_execute_now": False, "execute_next_automatically": False, "automatic_followthrough_supported": False, "review_only": True, "checkpoint_only": True, "completion_checkpoint_only": True, "browser_started_by_completion": False, "cdp_command_sent_by_completion": False, "runtime_evaluated_by_completion": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or completion_review.get("recommended_review_action") or "review_source_map_followthrough_completion_checkpoint"
            actions = ["review_source_map_followthrough_completion_checkpoint"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_selected_executor_result_checkpoint"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_completion_checkpoint_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_terminal_review_final_audit_request(protection_name, context):
        spec = SourceMapTerminalReviewFinalAuditSpec.from_context(context)
        result = SourceMapTerminalReviewFinalAuditManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        rollup = descriptor.get("final_audit_rollup") if isinstance(descriptor.get("final_audit_rollup"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_terminal_review_final_audit_status={result.status}",
            f"source_map_terminal_review_final_audit_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_terminal_review_final_audit_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_terminal_review_final_audit_closure_status={descriptor.get('closure_status', '')}",
            f"source_map_terminal_review_final_audit_final_audit_status={descriptor.get('final_audit_status', '')}",
            f"source_map_terminal_review_final_audit_terminal_review_candidate={descriptor.get('terminal_review_candidate', False)}",
            f"source_map_terminal_review_final_audit_followup_required={descriptor.get('followup_required', False)}",
            f"source_map_terminal_review_final_audit_ready_for_final_audit_review={descriptor.get('ready_for_final_audit_review', False)}",
            f"source_map_terminal_review_final_audit_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_terminal_review_final_audit_recommended_review_action={descriptor.get('recommended_review_action', '')}",
            f"source_map_terminal_review_final_audit_observed_review_action={descriptor.get('observed_review_action', '')}",
            f"source_map_terminal_review_final_audit_source_closure_digest={descriptor.get('source_closure_checkpoint_digest_sha256', '')}",
            f"source_map_terminal_review_final_audit_source_package_digest={descriptor.get('source_terminal_review_package_digest_sha256', '')}",
            "source_map_terminal_review_final_audit_review_only=True",
            "source_map_terminal_review_final_audit_audit_rollup_only=True",
            "source_map_terminal_review_final_audit_final_audit_only=True",
            f"source_map_terminal_review_final_audit_recommended_action_executed_by_rollup={descriptor.get('recommended_action_executed_by_rollup', False)}",
            f"source_map_terminal_review_final_audit_browser_started_by_rollup={policy.get('browser_started', False)}",
            f"source_map_terminal_review_final_audit_cdp_command_sent_by_rollup={policy.get('cdp_command_sent', False)}",
            f"source_map_terminal_review_final_audit_runtime_evaluated_by_rollup={policy.get('runtime_evaluated', False)}",
            f"source_map_terminal_review_final_audit_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_terminal_review_final_audit_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_terminal_review_final_audit_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_terminal_review_final_audit_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-terminal-review-final-audit.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map terminal review closure summary / final audit rollup.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "closure_status": descriptor.get("closure_status", ""), "final_audit_status": descriptor.get("final_audit_status", ""), "terminal_review_candidate": bool(descriptor.get("terminal_review_candidate", False)), "followup_required": bool(descriptor.get("followup_required", False)), "recommended_review_action": descriptor.get("recommended_review_action", ""), "observed_review_action": descriptor.get("observed_review_action", ""), "source_closure_checkpoint_digest_sha256": descriptor.get("source_closure_checkpoint_digest_sha256", ""), "source_terminal_review_package_digest_sha256": descriptor.get("source_terminal_review_package_digest_sha256", ""), "final_audit_rollup_schema_version": rollup.get("schema_version", ""), "ready_for_final_audit_review": bool(descriptor.get("ready_for_final_audit_review", False)), "ready_to_execute_now": False, "execute_next_automatically": False, "automatic_followthrough_supported": False, "recommended_action_executed_by_rollup": False, "review_only": True, "audit_rollup_only": True, "final_audit_only": True, "browser_started_by_rollup": False, "cdp_command_sent_by_rollup": False, "runtime_evaluated_by_rollup": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_terminal_review_final_audit"
            actions = ["review_source_map_terminal_review_final_audit"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_terminal_review_closure_checkpoint"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_terminal_review_final_audit_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_terminal_review_closure_checkpoint_request(protection_name, context):
        spec = SourceMapTerminalReviewClosureCheckpointSpec.from_context(context)
        result = SourceMapTerminalReviewClosureCheckpointManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        closure_audit = descriptor.get("closure_audit") if isinstance(descriptor.get("closure_audit"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_terminal_review_closure_checkpoint_status={result.status}",
            f"source_map_terminal_review_closure_checkpoint_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_terminal_review_closure_checkpoint_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_terminal_review_closure_checkpoint_completion_status={descriptor.get('completion_status', '')}",
            f"source_map_terminal_review_closure_checkpoint_closure_status={descriptor.get('closure_status', '')}",
            f"source_map_terminal_review_closure_checkpoint_terminal_review_candidate={descriptor.get('terminal_review_candidate', False)}",
            f"source_map_terminal_review_closure_checkpoint_followup_required={descriptor.get('followup_required', False)}",
            f"source_map_terminal_review_closure_checkpoint_ready_for_closure_audit_review={descriptor.get('ready_for_closure_audit_review', False)}",
            f"source_map_terminal_review_closure_checkpoint_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_terminal_review_closure_checkpoint_recommended_review_action={descriptor.get('recommended_review_action', '')}",
            f"source_map_terminal_review_closure_checkpoint_observed_review_action={descriptor.get('observed_review_action', '')}",
            f"source_map_terminal_review_closure_checkpoint_source_package_digest={descriptor.get('source_terminal_review_package_digest_sha256', '')}",
            f"source_map_terminal_review_closure_checkpoint_observed_result_digest={descriptor.get('source_observed_result_digest_sha256', '')}",
            "source_map_terminal_review_closure_checkpoint_review_only=True",
            "source_map_terminal_review_closure_checkpoint_audit_checkpoint_only=True",
            "source_map_terminal_review_closure_checkpoint_closure_checkpoint_only=True",
            f"source_map_terminal_review_closure_checkpoint_recommended_action_executed_by_checkpoint={descriptor.get('recommended_action_executed_by_checkpoint', False)}",
            f"source_map_terminal_review_closure_checkpoint_browser_started_by_checkpoint={policy.get('browser_started', False)}",
            f"source_map_terminal_review_closure_checkpoint_cdp_command_sent_by_checkpoint={policy.get('cdp_command_sent', False)}",
            f"source_map_terminal_review_closure_checkpoint_runtime_evaluated_by_checkpoint={policy.get('runtime_evaluated', False)}",
            f"source_map_terminal_review_closure_checkpoint_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_terminal_review_closure_checkpoint_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_terminal_review_closure_checkpoint_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_terminal_review_closure_checkpoint_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-terminal-review-closure-checkpoint.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map terminal review observed-result / closure audit checkpoint.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "completion_status": descriptor.get("completion_status", ""), "closure_status": descriptor.get("closure_status", ""), "terminal_review_candidate": bool(descriptor.get("terminal_review_candidate", False)), "followup_required": bool(descriptor.get("followup_required", False)), "recommended_review_action": descriptor.get("recommended_review_action", ""), "observed_review_action": descriptor.get("observed_review_action", ""), "source_terminal_review_package_digest_sha256": descriptor.get("source_terminal_review_package_digest_sha256", ""), "source_observed_result_digest_sha256": descriptor.get("source_observed_result_digest_sha256", ""), "closure_audit_schema_version": closure_audit.get("schema_version", ""), "ready_for_closure_audit_review": bool(descriptor.get("ready_for_closure_audit_review", False)), "ready_to_execute_now": False, "execute_next_automatically": False, "automatic_followthrough_supported": False, "recommended_action_executed_by_checkpoint": False, "review_only": True, "audit_checkpoint_only": True, "closure_checkpoint_only": True, "browser_started_by_checkpoint": False, "cdp_command_sent_by_checkpoint": False, "runtime_evaluated_by_checkpoint": False, "calls_mcp": False, "mobile_runtime_used": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_terminal_review_closure_checkpoint"
            actions = ["review_source_map_terminal_review_closure_checkpoint"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "record_source_map_terminal_review_observed_result"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_terminal_review_closure_checkpoint_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_selected_executor_apply_preflight_request(protection_name, context):
        spec = SourceMapSelectedExecutorApplyPreflightSpec.from_context(context)
        result = SourceMapSelectedExecutorApplyPreflightManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        apply_plan = descriptor.get("apply_plan") if isinstance(descriptor.get("apply_plan"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_selected_executor_apply_preflight_status={result.status}",
            f"source_map_selected_executor_apply_preflight_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_selected_executor_apply_preflight_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_selected_executor_apply_preflight_selected_gate={descriptor.get('selected_review_gate', '')}",
            f"source_map_selected_executor_apply_preflight_approval_record_verified={descriptor.get('approval_record_verified', False)}",
            f"source_map_selected_executor_apply_preflight_executor_input_ready={descriptor.get('executor_input_ready', False)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_verified={descriptor.get('dispatcher_result_verified', False)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_decision_recorded={descriptor.get('dispatcher_decision_recorded', False)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_id={descriptor.get('dispatcher_result_id', '')}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_optional={descriptor.get('dispatcher_result_optional', True)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_handoff_only={descriptor.get('dispatcher_result_handoff_only', True)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_selected_executor_invoked={descriptor.get('dispatcher_result_selected_executor_invoked', False)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_selected_executor_apply_preflight_invoked={descriptor.get('dispatcher_result_selected_executor_apply_preflight_invoked', False)}",
            f"source_map_selected_executor_apply_preflight_dispatcher_result_dispatch_target_invoked={descriptor.get('dispatcher_result_dispatch_target_invoked', False)}",
            f"source_map_selected_executor_apply_preflight_ready_for_selected_executor_review={descriptor.get('ready_for_selected_executor_review', False)}",
            f"source_map_selected_executor_apply_preflight_ready_to_apply_now={descriptor.get('ready_to_apply_now', False)}",
            "source_map_selected_executor_apply_preflight_review_only=True",
            "source_map_selected_executor_apply_preflight_preflight_only=True",
            "source_map_selected_executor_apply_preflight_apply_preflight_only=True",
            "source_map_selected_executor_apply_preflight_handoff_only=True",
            f"source_map_selected_executor_apply_preflight_future_executor_implemented={bool((descriptor.get('future_executor_contract') if isinstance(descriptor.get('future_executor_contract'), dict) else {}).get('implemented', False))}",
            f"source_map_selected_executor_apply_preflight_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_selected_executor_apply_preflight_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_selected_executor_apply_preflight_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_selected_executor_apply_preflight_browser_started={policy.get('browser_started', False)}",
            f"source_map_selected_executor_apply_preflight_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_apply_preflight_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_selected_executor_apply_preflight_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_apply_preflight_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_selected_executor_apply_preflight_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_selected_executor_apply_preflight_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_selected_executor_apply_preflight_surface_executor_invoked={policy.get('surface_executor_invoked', False)}",
            f"source_map_selected_executor_apply_preflight_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_selected_executor_apply_preflight_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_selected_executor_apply_preflight_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_selected_executor_apply_preflight_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-selected-executor-apply-preflight.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map selected executor apply preflight descriptor.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "selected_review_gate": descriptor.get("selected_review_gate", ""), "approval_record_verified": bool(descriptor.get("approval_record_verified", False)), "executor_input_ready": bool(descriptor.get("executor_input_ready", False)), "dispatcher_result_verified": bool(descriptor.get("dispatcher_result_verified", False)), "dispatcher_decision_recorded": bool(descriptor.get("dispatcher_decision_recorded", False)), "dispatcher_result_id": descriptor.get("dispatcher_result_id", ""), "dispatcher_result_optional": bool(descriptor.get("dispatcher_result_optional", True)), "dispatcher_result_handoff_only": bool(descriptor.get("dispatcher_result_handoff_only", True)), "dispatcher_result_selected_executor_invoked": False, "dispatcher_result_selected_executor_apply_preflight_invoked": False, "dispatcher_result_dispatch_target_invoked": False, "ready_for_selected_executor_review": bool(descriptor.get("ready_for_selected_executor_review", False)), "ready_to_apply_now": False, "future_action": descriptor.get("future_action", apply_plan.get("future_action", "")), "future_result_artifact": descriptor.get("future_result_artifact", apply_plan.get("future_result_artifact", "")), "review_only": True, "preflight_only": True, "apply_preflight_only": True, "handoff_only": True, "future_executor_implemented": False, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "surface_executor_invoked": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_selected_executor_application"
            actions = ["review_source_map_selected_executor_apply_preflight"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_selected_executor_approval_plan_and_record"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_selected_executor_apply_preflight_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_selected_executor_approval_plan_request(protection_name, context):
        spec = SourceMapSelectedExecutorApprovalPlanSpec.from_context(context)
        result = SourceMapSelectedExecutorApprovalPlanManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        package = descriptor.get("executor_review_package") if isinstance(descriptor.get("executor_review_package"), dict) else {}
        approval = descriptor.get("approval_requirements") if isinstance(descriptor.get("approval_requirements"), dict) else {}
        apply_plan = descriptor.get("apply_plan") if isinstance(descriptor.get("apply_plan"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_selected_executor_approval_plan_status={result.status}",
            f"source_map_selected_executor_approval_plan_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_selected_executor_approval_plan_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_selected_executor_approval_plan_selected_gate={descriptor.get('selected_review_gate', '')}",
            f"source_map_selected_executor_approval_plan_approval_ready={descriptor.get('approval_plan_ready', False)}",
            f"source_map_selected_executor_approval_plan_apply_ready_for_review={descriptor.get('apply_plan_ready_for_review', False)}",
            f"source_map_selected_executor_approval_plan_ready_to_apply_now={descriptor.get('ready_to_apply_now', False)}",
            f"source_map_selected_executor_approval_plan_approval_recorded={descriptor.get('approval_recorded', False)}",
            "source_map_selected_executor_approval_plan_review_only=True",
            "source_map_selected_executor_approval_plan_plan_only=True",
            "source_map_selected_executor_approval_plan_approval_plan_only=True",
            "source_map_selected_executor_approval_plan_apply_plan_only=True",
            "source_map_selected_executor_approval_plan_handoff_only=True",
            f"source_map_selected_executor_approval_plan_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_selected_executor_approval_plan_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_selected_executor_approval_plan_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_selected_executor_approval_plan_browser_started={policy.get('browser_started', False)}",
            f"source_map_selected_executor_approval_plan_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_approval_plan_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_selected_executor_approval_plan_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_approval_plan_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_selected_executor_approval_plan_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_selected_executor_approval_plan_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_selected_executor_approval_plan_surface_executor_invoked={policy.get('surface_executor_invoked', False)}",
            f"source_map_selected_executor_approval_plan_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_selected_executor_approval_plan_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_selected_executor_approval_plan_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_selected_executor_approval_plan_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-selected-executor-approval-plan.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map selected executor approval/apply-plan descriptor.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "selected_review_gate": descriptor.get("selected_review_gate", ""), "approval_plan_ready": bool(descriptor.get("approval_plan_ready", False)), "apply_plan_ready_for_review": bool(descriptor.get("apply_plan_ready_for_review", False)), "approval_recorded": False, "ready_to_apply_now": False, "future_action": apply_plan.get("future_action", ""), "approval_record_artifact": approval.get("approval_record_artifact", ""), "review_only": True, "plan_only": True, "approval_plan_only": True, "apply_plan_only": True, "handoff_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False, "surface_executor_invoked": False, "executor_review_package_consumer": package.get("consumer", "")})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "record_review_approval_for_source_map_selected_executor"
            actions = ["review_source_map_selected_executor_approval_plan"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_selected_executor_input_review_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_selected_executor_approval_plan_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_selected_executor_input_review_request(protection_name, context):
        spec = SourceMapSelectedExecutorInputReviewSpec.from_context(context)
        result = SourceMapSelectedExecutorInputReviewManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        package = descriptor.get("executor_review_package") if isinstance(descriptor.get("executor_review_package"), dict) else {}
        gate = package.get("review_gate") if isinstance(package.get("review_gate"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_selected_executor_input_review_status={result.status}",
            f"source_map_selected_executor_input_review_selected_action_id={descriptor.get('selected_action_id', '')}",
            f"source_map_selected_executor_input_review_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_selected_executor_input_review_selected_surface={descriptor.get('selected_followthrough_review_surface', '')}",
            f"source_map_selected_executor_input_review_source_debugger_candidate_selection_id={descriptor.get('source_debugger_candidate_selection_id', '')}",
            f"source_map_selected_executor_input_review_source_debugger_candidate_selection_ready={descriptor.get('source_debugger_candidate_selection_ready', False)}",
            f"source_map_selected_executor_input_review_source_hook_candidate_selection_id={descriptor.get('source_hook_candidate_selection_id', '')}",
            f"source_map_selected_executor_input_review_source_hook_candidate_selection_ready={descriptor.get('source_hook_candidate_selection_ready', False)}",
            f"source_map_selected_executor_input_review_package_ready={descriptor.get('executor_review_package_ready', False)}",
            f"source_map_selected_executor_input_review_ready_for_executor_review={descriptor.get('ready_for_executor_review', False)}",
            f"source_map_selected_executor_input_review_gate={gate.get('gate', '')}",
            "source_map_selected_executor_input_review_review_only=True",
            "source_map_selected_executor_input_review_plan_only=True",
            "source_map_selected_executor_input_review_preflight_only=True",
            "source_map_selected_executor_input_review_handoff_only=True",
            f"source_map_selected_executor_input_review_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_selected_executor_input_review_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_selected_executor_input_review_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_selected_executor_input_review_browser_started={policy.get('browser_started', False)}",
            f"source_map_selected_executor_input_review_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_selected_executor_input_review_debugger_execution_performed={policy.get('debugger_execution_performed', False)}",
            f"source_map_selected_executor_input_review_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_selected_executor_input_review_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_selected_executor_input_review_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_selected_executor_input_review_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_selected_executor_input_review_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_selected_executor_input_review_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_selected_executor_input_review_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_selected_executor_input_review_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-selected-executor-input-review.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map selected executor-input review descriptor.", metadata={"status": result.status, "selected_action_id": descriptor.get("selected_action_id", ""), "selected_consumer": descriptor.get("selected_consumer", ""), "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""), "source_debugger_candidate_selection_id": descriptor.get("source_debugger_candidate_selection_id", ""), "source_debugger_candidate_selection_ready": bool(descriptor.get("source_debugger_candidate_selection_ready", False)), "source_hook_candidate_selection_id": descriptor.get("source_hook_candidate_selection_id", ""), "source_hook_candidate_selection_ready": bool(descriptor.get("source_hook_candidate_selection_ready", False)), "executor_review_package_ready": bool(descriptor.get("executor_review_package_ready", False)), "ready_for_executor_review": bool(descriptor.get("ready_for_executor_review", False)), "review_gate": gate.get("gate", ""), "review_only": True, "plan_only": True, "preflight_only": True, "handoff_only": True, "raw_source_content_exported": False, "preview_exported": False, "fetch_source_map": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "logpoint_installed": False, "hook_installed": False, "rebuild_executed": False})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_selected_source_map_executor_input_before_execution"
            actions = ["review_source_map_selected_executor_input"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_ready_source_map_followthrough_surface_selection_descriptor"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_selected_executor_input_review_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    return None

def dispatch_source_map_gateway_d(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Group D: read-only dispatcher review/preflight/plan/handoff descriptors (followthrough dispatcher branches)."""
    if owner._is_source_map_followthrough_dispatcher_apply_preflight_request(protection_name, context):
        spec = SourceMapFollowthroughDispatcherApplyPreflightSpec.from_context(context)
        result = SourceMapFollowthroughDispatcherApplyPreflightManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        apply_preflight = descriptor.get("dispatcher_apply_preflight") if isinstance(descriptor.get("dispatcher_apply_preflight"), dict) else {}
        future_contract = descriptor.get("future_dispatcher_mvp_contract") if isinstance(descriptor.get("future_dispatcher_mvp_contract"), dict) else {}
        verification = [
            f"source_map_followthrough_dispatcher_apply_preflight_status={result.status}",
            f"source_map_followthrough_dispatcher_apply_preflight_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_required_artifact={descriptor.get('required_result_artifact', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_journal_id={descriptor.get('journal_id', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_transaction_preflight_id={descriptor.get('transaction_preflight_id', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_approval_record_id={descriptor.get('approval_record_id', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_transaction_plan_id={descriptor.get('transaction_plan_id', '')}",
            f"source_map_followthrough_dispatcher_apply_preflight_handoff_verified={descriptor.get('handoff_verified', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_ready_for_review={descriptor.get('dispatcher_apply_preflight_ready_for_review', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp_review={descriptor.get('ready_for_explicit_dispatcher_mvp_review', False)}",
            "source_map_followthrough_dispatcher_apply_preflight_read_only=True",
            "source_map_followthrough_dispatcher_apply_preflight_preflight_only=True",
            f"source_map_followthrough_dispatcher_apply_preflight_ready_to_dispatch_now={descriptor.get('ready_to_dispatch_now', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_dispatcher_invoked={descriptor.get('dispatcher_invoked', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_dispatch_target_invoked={descriptor.get('dispatch_target_invoked', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_executor_invoked={descriptor.get('executor_invoked', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_selected_executor_apply_preflight_invoked={descriptor.get('selected_executor_apply_preflight_invoked', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_future_dispatcher_mvp_implemented={future_contract.get('implemented', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatcher_apply_preflight_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatcher_apply_preflight_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatcher_apply_preflight_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatcher-apply-preflight.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through dispatcher apply-preflight descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "dispatch_surface": descriptor.get("dispatch_surface", ""), "required_result_artifact": descriptor.get("required_result_artifact", ""), "journal_id": descriptor.get("journal_id", ""), "transaction_preflight_id": descriptor.get("transaction_preflight_id", ""), "approval_record_id": descriptor.get("approval_record_id", ""), "transaction_plan_id": descriptor.get("transaction_plan_id", ""), "handoff_verified": bool(descriptor.get("handoff_verified", False)), "dispatcher_apply_preflight_ready_for_review": bool(descriptor.get("dispatcher_apply_preflight_ready_for_review", False)), "ready_for_explicit_dispatcher_mvp_review": bool(descriptor.get("ready_for_explicit_dispatcher_mvp_review", False)), "review_only": True, "read_only": True, "preflight_only": True, "dispatcher_apply_preflight_only": True, "ready_to_dispatch_now": False, "ready_to_execute_now": False, "dispatcher_invoked": False, "dispatch_target_invoked": False, "executor_invoked": False, "selected_executor_invoked": False, "selected_executor_apply_preflight_invoked": False, "runtime_apply_preflight_invoked": False, "will_invoke_dispatcher": False, "will_invoke_dispatch_target": False, "will_invoke_selected_executor": False, "will_run_selected_executor_apply_preflight": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "dispatcher_apply_preflight": apply_preflight, "future_dispatcher_mvp_contract": future_contract, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatcher_mvp"
            actions = ["review_source_map_followthrough_dispatcher_apply_preflight"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatcher_apply_preflight_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatcher_apply_preflight_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_dispatcher_handoff_request(protection_name, context):
        spec = SourceMapFollowthroughDispatcherHandoffSpec.from_context(context)
        result = SourceMapFollowthroughDispatcherHandoffManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        handoff_payload = descriptor.get("dispatcher_handoff") if isinstance(descriptor.get("dispatcher_handoff"), dict) else {}
        executor_contract = descriptor.get("selected_executor_review_contract") if isinstance(descriptor.get("selected_executor_review_contract"), dict) else {}
        verification = [
            f"source_map_followthrough_dispatcher_handoff_status={result.status}",
            f"source_map_followthrough_dispatcher_handoff_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatcher_handoff_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatcher_handoff_required_artifact={descriptor.get('required_result_artifact', '')}",
            f"source_map_followthrough_dispatcher_handoff_journal_id={descriptor.get('journal_id', '')}",
            f"source_map_followthrough_dispatcher_handoff_transaction_preflight_id={descriptor.get('transaction_preflight_id', '')}",
            f"source_map_followthrough_dispatcher_handoff_approval_record_id={descriptor.get('approval_record_id', '')}",
            f"source_map_followthrough_dispatcher_handoff_transaction_plan_id={descriptor.get('transaction_plan_id', '')}",
            f"source_map_followthrough_dispatcher_handoff_bounded_gate_verified={descriptor.get('bounded_gate_verified', False)}",
            f"source_map_followthrough_dispatcher_handoff_ready_for_review={descriptor.get('dispatcher_handoff_ready_for_review', False)}",
            f"source_map_followthrough_dispatcher_handoff_ready_for_explicit_dispatch_review={descriptor.get('ready_for_explicit_dispatch_review', False)}",
            "source_map_followthrough_dispatcher_handoff_read_only=True",
            "source_map_followthrough_dispatcher_handoff_handoff_only=True",
            f"source_map_followthrough_dispatcher_handoff_ready_to_dispatch_now={descriptor.get('ready_to_dispatch_now', False)}",
            f"source_map_followthrough_dispatcher_handoff_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_followthrough_dispatcher_handoff_dispatcher_invoked={descriptor.get('dispatcher_invoked', False)}",
            f"source_map_followthrough_dispatcher_handoff_dispatch_target_invoked={descriptor.get('dispatch_target_invoked', False)}",
            f"source_map_followthrough_dispatcher_handoff_executor_invoked={descriptor.get('executor_invoked', False)}",
            f"source_map_followthrough_dispatcher_handoff_apply_preflight_invoked={descriptor.get('apply_preflight_invoked', False)}",
            f"source_map_followthrough_dispatcher_handoff_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatcher_handoff_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatcher_handoff_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatcher_handoff_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatcher_handoff_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatcher_handoff_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatcher_handoff_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatcher_handoff_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatcher_handoff_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatcher-handoff.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through dispatcher handoff descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "dispatch_surface": descriptor.get("dispatch_surface", ""), "required_result_artifact": descriptor.get("required_result_artifact", ""), "journal_id": descriptor.get("journal_id", ""), "transaction_preflight_id": descriptor.get("transaction_preflight_id", ""), "approval_record_id": descriptor.get("approval_record_id", ""), "transaction_plan_id": descriptor.get("transaction_plan_id", ""), "bounded_gate_verified": bool(descriptor.get("bounded_gate_verified", False)), "dispatcher_handoff_ready_for_review": bool(descriptor.get("dispatcher_handoff_ready_for_review", False)), "ready_for_explicit_dispatch_review": bool(descriptor.get("ready_for_explicit_dispatch_review", False)), "review_only": True, "read_only": True, "dispatcher_handoff_only": True, "ready_to_dispatch_now": False, "ready_to_execute_now": False, "dispatcher_invoked": False, "dispatch_target_invoked": False, "executor_invoked": False, "selected_executor_invoked": False, "apply_preflight_invoked": False, "will_invoke_dispatcher": False, "will_invoke_dispatch_target": False, "will_invoke_selected_executor": False, "will_run_apply_preflight": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "dispatcher_handoff": handoff_payload, "selected_executor_review_contract": executor_contract, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatcher_apply_preflight"
            actions = ["review_source_map_followthrough_dispatcher_handoff"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatcher_handoff_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatcher_handoff_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_dispatch_bounded_executor_gate_request(protection_name, context):
        spec = SourceMapFollowthroughDispatchBoundedExecutorGateSpec.from_context(context)
        result = SourceMapFollowthroughDispatchBoundedExecutorGateManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        bounded_input = descriptor.get("bounded_dispatch_input") if isinstance(descriptor.get("bounded_dispatch_input"), dict) else {}
        future_contract = descriptor.get("future_dispatcher_contract") if isinstance(descriptor.get("future_dispatcher_contract"), dict) else {}
        verification = [
            f"source_map_followthrough_dispatch_bounded_executor_gate_status={result.status}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_required_artifact={descriptor.get('required_result_artifact', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_journal_id={descriptor.get('journal_id', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_transaction_preflight_id={descriptor.get('transaction_preflight_id', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_approval_record_id={descriptor.get('approval_record_id', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_transaction_plan_id={descriptor.get('transaction_plan_id', '')}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_transaction_journal_verified={descriptor.get('transaction_journal_verified', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_ready_for_review={descriptor.get('bounded_executor_gate_ready_for_review', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff_review={descriptor.get('ready_for_dispatcher_handoff_review', False)}",
            "source_map_followthrough_dispatch_bounded_executor_gate_read_only=True",
            "source_map_followthrough_dispatch_bounded_executor_gate_gate_only=True",
            f"source_map_followthrough_dispatch_bounded_executor_gate_ready_to_dispatch_now={descriptor.get('ready_to_dispatch_now', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_ready_to_execute_now={descriptor.get('ready_to_execute_now', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_dispatch_target_invoked={descriptor.get('dispatch_target_invoked', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_executor_invoked={descriptor.get('executor_invoked', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_future_dispatcher_implemented={future_contract.get('implemented', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatch_bounded_executor_gate_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatch_bounded_executor_gate_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatch_bounded_executor_gate_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatch-bounded-executor-gate.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through dispatch bounded executor gate descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "dispatch_surface": descriptor.get("dispatch_surface", ""), "required_result_artifact": descriptor.get("required_result_artifact", ""), "journal_id": descriptor.get("journal_id", ""), "transaction_preflight_id": descriptor.get("transaction_preflight_id", ""), "approval_record_id": descriptor.get("approval_record_id", ""), "transaction_plan_id": descriptor.get("transaction_plan_id", ""), "transaction_journal_verified": bool(descriptor.get("transaction_journal_verified", False)), "bounded_executor_gate_ready_for_review": bool(descriptor.get("bounded_executor_gate_ready_for_review", False)), "ready_for_dispatcher_handoff_review": bool(descriptor.get("ready_for_dispatcher_handoff_review", False)), "review_only": True, "read_only": True, "bounded_executor_gate_only": True, "ready_to_dispatch_now": False, "ready_to_execute_now": False, "dispatch_target_invoked": False, "executor_invoked": False, "will_invoke_dispatch_target": False, "will_invoke_next_action": False, "will_run_apply_preflight": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "future_dispatcher_contract": future_contract, "bounded_dispatch_input": bounded_input, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatcher_handoff"
            actions = ["review_source_map_followthrough_dispatch_bounded_executor_gate"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatch_bounded_executor_gate_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatch_bounded_executor_gate_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_dispatch_transaction_preflight_request(protection_name, context):
        spec = SourceMapFollowthroughDispatchTransactionPreflightSpec.from_context(context)
        result = SourceMapFollowthroughDispatchTransactionPreflightManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        transaction_preflight = descriptor.get("transaction_preflight") if isinstance(descriptor.get("transaction_preflight"), dict) else {}
        journal_writer_gate = descriptor.get("journal_writer_gate") if isinstance(descriptor.get("journal_writer_gate"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_dispatch_transaction_preflight_status={result.status}",
            f"source_map_followthrough_dispatch_transaction_preflight_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_required_artifact={descriptor.get('planned_required_artifact', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_approval_plan_id={descriptor.get('approval_plan_id', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_approval_record_id={descriptor.get('approval_record_id', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_transaction_plan_id={descriptor.get('transaction_plan_id', '')}",
            f"source_map_followthrough_dispatch_transaction_preflight_approval_record_verified={descriptor.get('approval_record_verified', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_transaction_plan_verified={descriptor.get('transaction_plan_verified', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_ready_for_review={descriptor.get('transaction_preflight_ready_for_review', False)}",
            f"source_map_followthrough_dispatch_journal_writer_gate_ready_for_review={descriptor.get('journal_writer_gate_ready_for_review', False)}",
            "source_map_followthrough_dispatch_transaction_preflight_read_only=True",
            "source_map_followthrough_dispatch_transaction_preflight_preflight_only=True",
            "source_map_followthrough_dispatch_transaction_preflight_journal_writer_gate_only=True",
            f"source_map_followthrough_dispatch_transaction_preflight_ready_to_write_now={descriptor.get('ready_to_write_now', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_ready_to_dispatch_now={descriptor.get('ready_to_dispatch_now', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_transaction_started={descriptor.get('transaction_started', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_journal_written={descriptor.get('journal_written', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_will_write_transaction_journal={descriptor.get('will_write_transaction_journal', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_will_invoke_dispatch_target={descriptor.get('will_invoke_dispatch_target', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatch_transaction_preflight_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatch_transaction_preflight_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatch_transaction_preflight_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatch-transaction-preflight.json", kind=ArtifactKind.JSON, description="Native Web runtime read-only Source Map follow-through dispatch transaction preflight descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "dispatch_surface": descriptor.get("dispatch_surface", ""), "planned_required_artifact": descriptor.get("planned_required_artifact", ""), "approval_plan_id": descriptor.get("approval_plan_id", ""), "approval_record_id": descriptor.get("approval_record_id", ""), "transaction_plan_id": descriptor.get("transaction_plan_id", ""), "approval_record_verified": bool(descriptor.get("approval_record_verified", False)), "transaction_plan_verified": bool(descriptor.get("transaction_plan_verified", False)), "transaction_preflight_ready_for_review": bool(descriptor.get("transaction_preflight_ready_for_review", False)), "journal_writer_gate_ready_for_review": bool(descriptor.get("journal_writer_gate_ready_for_review", False)), "review_only": True, "read_only": True, "preflight_only": True, "transaction_preflight_only": True, "journal_writer_gate_only": True, "ready_to_write_now": False, "ready_to_dispatch_now": False, "transaction_started": False, "journal_written": False, "will_write_transaction_journal": False, "will_start_transaction": False, "will_invoke_dispatch_target": False, "will_invoke_next_action": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "transaction_preflight": transaction_preflight, "journal_writer_gate": journal_writer_gate, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatch_transaction_journal_writer"
            actions = ["review_source_map_followthrough_dispatch_transaction_preflight"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatch_transaction_preflight_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatch_transaction_preflight_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    if owner._is_source_map_followthrough_dispatch_approval_plan_request(protection_name, context):
        spec = SourceMapFollowthroughDispatchApprovalPlanSpec.from_context(context)
        result = SourceMapFollowthroughDispatchApprovalPlanManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        approval_plan = descriptor.get("approval_plan") if isinstance(descriptor.get("approval_plan"), dict) else {}
        transaction_plan = descriptor.get("transaction_plan") if isinstance(descriptor.get("transaction_plan"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_followthrough_dispatch_approval_plan_status={result.status}",
            f"source_map_followthrough_dispatch_approval_plan_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatch_approval_plan_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatch_approval_plan_required_artifact={descriptor.get('planned_required_artifact', '')}",
            f"source_map_followthrough_dispatch_approval_plan_ready_for_review={descriptor.get('approval_plan_ready_for_review', False)}",
            f"source_map_followthrough_dispatch_transaction_plan_ready_for_review={descriptor.get('transaction_plan_ready_for_review', False)}",
            f"source_map_followthrough_dispatch_approval_plan_id={approval_plan.get('approval_plan_id', '')}",
            f"source_map_followthrough_dispatch_transaction_plan_id={transaction_plan.get('transaction_plan_id', '')}",
            "source_map_followthrough_dispatch_approval_plan_review_only=True",
            "source_map_followthrough_dispatch_approval_plan_approval_plan_only=True",
            "source_map_followthrough_dispatch_approval_plan_transaction_plan_only=True",
            "source_map_followthrough_dispatch_approval_plan_plan_only=True",
            f"source_map_followthrough_dispatch_approval_plan_ready_to_dispatch_now={descriptor.get('ready_to_dispatch_now', False)}",
            f"source_map_followthrough_dispatch_approval_plan_approval_recorded={descriptor.get('approval_recorded', False)}",
            f"source_map_followthrough_dispatch_approval_plan_transaction_started={descriptor.get('transaction_started', False)}",
            f"source_map_followthrough_dispatch_approval_plan_journal_written={descriptor.get('journal_written', False)}",
            f"source_map_followthrough_dispatch_approval_plan_will_write_approval_record={descriptor.get('will_write_approval_record', False)}",
            f"source_map_followthrough_dispatch_approval_plan_will_start_transaction={descriptor.get('will_start_transaction', False)}",
            f"source_map_followthrough_dispatch_approval_plan_will_invoke_dispatch_target={descriptor.get('will_invoke_dispatch_target', False)}",
            f"source_map_followthrough_dispatch_approval_plan_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatch_approval_plan_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatch_approval_plan_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatch_approval_plan_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatch_approval_plan_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatch_approval_plan_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatch_approval_plan_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatch_approval_plan_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatch_approval_plan_error={result.error}")
        artifact = ArtifactRef(path="virtual://workspace/source-map-followthrough-dispatch-approval-plan.json", kind=ArtifactKind.JSON, description="Native Web runtime review-only Source Map follow-through dispatch approval and transaction plan descriptor.", metadata={"status": result.status, "selected_consumer": descriptor.get("selected_consumer", ""), "dispatch_surface": descriptor.get("dispatch_surface", ""), "planned_required_artifact": descriptor.get("planned_required_artifact", ""), "approval_plan_ready_for_review": bool(descriptor.get("approval_plan_ready_for_review", False)), "transaction_plan_ready_for_review": bool(descriptor.get("transaction_plan_ready_for_review", False)), "approval_plan_id": approval_plan.get("approval_plan_id", ""), "transaction_plan_id": transaction_plan.get("transaction_plan_id", ""), "review_only": True, "approval_plan_only": True, "transaction_plan_only": True, "plan_only": True, "ready_to_dispatch_now": False, "approval_recorded": False, "transaction_started": False, "journal_written": False, "will_write_approval_record": False, "will_start_transaction": False, "will_invoke_dispatch_target": False, "will_invoke_next_action": False, "will_execute_debugger": False, "will_install_source_logpoint": False, "will_install_hook": False, "will_run_rebuild": False, "automatic_dispatch_supported": False, "automatic_followthrough_supported": False, "automatic_execution_supported": False, "browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "hook_installed": False, "rebuild_executed": False, "calls_mcp": False, "mobile_runtime_used": False, "side_effect_policy": policy, "descriptor": descriptor})
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval"
            actions = ["review_source_map_followthrough_dispatch_approval_plan"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "resolve_source_map_followthrough_dispatch_approval_plan_blockers"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatch_approval_plan_descriptor"
            actions = []
        return ProtectionResult(protection_name=protection_name, applied_actions=actions, verification=verification, status=status, artifacts=[artifact], next_action=str(next_action), confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW)
    return None


def dispatch_source_map_gateway_e(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Group E: explicit application branches (debugger, hook, rebuild, logpoint, dispatcher result, fetch)."""
    if owner._is_source_map_debugger_application_request(protection_name, context):
        apply_preflight = owner._source_map_debugger_apply_preflight(context)
        debugger_input = owner._source_map_debugger_location_input(context, apply_preflight)
        breakpoint_context = owner._source_map_debugger_breakpoint_context(debugger_input)
        blockers = owner._source_map_debugger_application_blockers(context, apply_preflight, debugger_input, breakpoint_context)
        spec = BreakpointSpec.from_context(breakpoint_context)
        approved = bool(
            context.get(
                "approve_source_map_debugger_action",
                context.get(
                    "approveSourceMapDebuggerAction",
                    context.get(
                        "approve_source_map_debugger_location_action",
                        context.get(
                            "approveSourceMapDebuggerLocationAction",
                            context.get("approve_debugger_location_action", context.get("approveDebuggerLocationAction", False)),
                        ),
                    ),
                ),
            )
        )
        location = debugger_input.get("location") if isinstance(debugger_input.get("location"), dict) else {}
        verification = [
            f"source_map_debugger_application_preflight_status={apply_preflight.get('status', '')}",
            f"source_map_debugger_application_selected_action_id={apply_preflight.get('selected_action_id', '')}",
            f"source_map_debugger_application_selected_consumer={apply_preflight.get('selected_consumer', '')}",
            f"source_map_debugger_application_selected_gate={apply_preflight.get('selected_review_gate', '')}",
            f"source_map_debugger_application_review_approved={bool(context.get('review_approved', context.get('reviewApproved', False)))}",
            f"source_map_debugger_application_action_approved={approved}",
            f"source_map_debugger_application_mode={context.get('mode', '')}",
            f"source_map_debugger_application_url_pattern={breakpoint_context.get('url_pattern', '')}",
            f"source_map_debugger_application_line_number={breakpoint_context.get('line_number', '')}",
            f"source_map_debugger_application_column_number={breakpoint_context.get('column_number', '')}",
            f"source_map_debugger_application_source={location.get('source', '')}",
            f"source_map_debugger_application_mapping_strategy={location.get('mapping_strategy', location.get('strategy', ''))}",
            f"source_map_debugger_application_blockers={','.join(blockers)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if blockers:
            verification.extend(
                [
                    "source_map_debugger_application_browser_started=False",
                    "source_map_debugger_application_cdp_command_sent=False",
                    "source_map_debugger_application_runtime_evaluated=False",
                    "source_map_debugger_application_debugger_location_applied=False",
                    "source_map_debugger_application_surface_executor_invoked=False",
                    "source_map_debugger_application_calls_mcp=False",
                    "source_map_debugger_application_mobile_runtime_used=False",
                    "source_map_debugger_application_automatic_continuation=False",
                    "source_map_debugger_application_automatic_loop=False",
                ]
            )
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-debugger-execution-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime blocked Source Map selected debugger application result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-debugger-execution-result.v1",
                    "status": "blocked",
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "review_approved": bool(context.get("review_approved", context.get("reviewApproved", False))),
                    "approve_source_map_debugger_action": approved,
                    "mode": context.get("mode", ""),
                    "reviewer": str(context.get("reviewer") or ""),
                    "url_pattern": breakpoint_context.get("url_pattern", ""),
                    "line_number": breakpoint_context.get("line_number"),
                    "column_number": breakpoint_context.get("column_number"),
                    "location": dict(location),
                    "blockers": blockers,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "debugger_location_applied": False,
                    "breakpoint_set": False,
                    "breakpoint_count": 0,
                    "paused_status": "not_attempted",
                    "callframe_count": 0,
                    "debugger_action_count": 0,
                    "surface_executor_invoked": False,
                    "automatic_continuation": False,
                    "automatic_loop": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.PARTIAL,
                artifacts=[artifact],
                next_action=owner._source_map_debugger_application_next_action(blockers),
                confidence=ConfidenceLevel.LOW,
            )
        try:
            session = owner._ensure_session()
            page = session.get_active_page() or session.new_page()
        except Exception as exc:
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=[f"Native Web browser provider unavailable: {exc}", *verification],
                status=ExecutionStatus.FAILED,
                artifacts=[],
                next_action="ensure_browser_provider",
                confidence=ConfidenceLevel.LOW,
            )
        result = BreakpointManager().set_breakpoint(page, spec)
        breakpoint_count = len(result.breakpoints)
        paused_status = result.paused.get("status") if isinstance(result.paused, dict) else "unknown"
        callframe_count = len(result.callframes)
        debugger_action_count = len(result.debugger_actions)
        runtime_evaluated = bool(breakpoint_context.get("trigger_expression") or result.trigger)
        cdp_command_sent = bool(result.supported and breakpoint_count)
        debugger_location_applied = result.status in {"success", "partial"} and bool(breakpoint_count)
        verification.extend(
            [
                f"source_map_debugger_application_status={result.status}",
                f"source_map_debugger_application_breakpoint_count={breakpoint_count}",
                f"source_map_debugger_application_paused_status={paused_status or 'unknown'}",
                f"source_map_debugger_application_callframe_count={callframe_count}",
                f"source_map_debugger_application_debugger_action_count={debugger_action_count}",
                "source_map_debugger_application_browser_started=True",
                f"source_map_debugger_application_runtime_evaluated={runtime_evaluated}",
                f"source_map_debugger_application_cdp_command_sent={cdp_command_sent}",
                f"source_map_debugger_application_debugger_location_applied={debugger_location_applied}",
                "source_map_debugger_application_surface_executor_invoked=True",
                "source_map_debugger_application_automatic_continuation=False",
                "source_map_debugger_application_automatic_loop=False",
                "source_map_debugger_application_calls_mcp=False",
                "source_map_debugger_application_mobile_runtime_used=False",
            ]
        )
        if result.trigger:
            verification.append(f"source_map_debugger_application_trigger_attempted={result.trigger.get('attempted', False)}")
            if result.trigger.get("error"):
                verification.append(f"source_map_debugger_application_trigger_error={result.trigger['error']}")
        if result.reason:
            verification.append(f"source_map_debugger_application_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_debugger_application_error={result.error}")
        artifacts = [
            ArtifactRef(
                path="virtual://workspace/source-map-debugger-execution-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime explicit-review Source Map selected debugger application result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-debugger-execution-result.v1",
                    "status": "success" if debugger_location_applied else result.status,
                    "breakpoint_status": result.status,
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "approval_record_id": apply_preflight.get("approval_record_id", ""),
                    "reviewer": str(context.get("reviewer") or ""),
                    "review_approved": True,
                    "approve_source_map_debugger_action": True,
                    "mode": "apply",
                    "url_pattern": spec.url_pattern if spec else "<missing>",
                    "line_number": spec.line_number if spec else 0,
                    "column_number": spec.column_number if spec else None,
                    "location": dict(location),
                    "breakpoint_count": breakpoint_count,
                    "breakpoint_set": bool(breakpoint_count),
                    "paused_status": paused_status or "unknown",
                    "callframe_count": callframe_count,
                    "debugger_action_count": debugger_action_count,
                    "browser_started": True,
                    "runtime_evaluated": runtime_evaluated,
                    "cdp_command_sent": cdp_command_sent,
                    "debugger_location_applied": debugger_location_applied,
                    "debugger_execution_performed": True,
                    "surface_executor_invoked": True,
                    "automatic_continuation": False,
                    "automatic_loop": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            ),
            ArtifactRef(
                path="virtual://workspace/breakpoints.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime Source Map debugger breakpoint result.",
                metadata={
                    "status": result.status,
                    "supported": result.supported,
                    "count": breakpoint_count,
                    "url_pattern": spec.url_pattern if spec else "<missing>",
                    "line_number": spec.line_number if spec else 0,
                    "column_number": spec.column_number if spec else None,
                    "source": location.get("source", ""),
                },
            ),
            ArtifactRef(
                path="virtual://workspace/debugger-paused.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime Source Map debugger paused snapshot.",
                metadata={
                    "status": paused_status or "unknown",
                    "count": result.paused.get("count", 0) if isinstance(result.paused, dict) else 0,
                    "callframe_count": callframe_count,
                },
            ),
            ArtifactRef(
                path="virtual://workspace/callframes.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime Source Map debugger callframe snapshot.",
                metadata={
                    "count": callframe_count,
                    "paused_status": paused_status or "unknown",
                },
            ),
        ]
        if result.debugger_actions:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/debugger-actions.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime Source Map debugger control action snapshot.",
                    metadata={"count": debugger_action_count, "paused_status": paused_status or "unknown"},
                )
            )
        if result.debugger_session:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/debugger-session.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime Source Map debugger paused-session snapshot.",
                    metadata={
                        "status": result.debugger_session.get("status", "unknown"),
                        "lifecycle": result.debugger_session.get("lifecycle", "unknown"),
                        "paused_event_count": result.debugger_session.get("paused_event_count", 0),
                    },
                )
            )
        if result.debugger_timeline:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/debugger-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime Source Map debugger event timeline.",
                    metadata={
                        "status": result.debugger_timeline.get("status", "unknown"),
                        "lifecycle": result.debugger_timeline.get("lifecycle", "unknown"),
                        "entry_count": result.debugger_timeline.get("entry_count", 0),
                        "paused_event_count": result.debugger_timeline.get("paused_event_count", 0),
                    },
                )
            )
        status = ExecutionStatus.SUCCESS if debugger_location_applied else ExecutionStatus.PARTIAL if result.status == "partial" else ExecutionStatus.FAILED
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=(
                [f"apply_source_map_debugger_location:{spec.url_pattern}:{spec.line_number}"]
                + (["capture_debugger_paused"] if paused_status == "success" else [])
                if spec and result.supported
                else []
            ),
            verification=verification,
            status=status,
            artifacts=artifacts,
            next_action="inspect_source_map_debugger_execution_artifacts" if debugger_location_applied else "inspect_source_map_debugger_execution_failure",
            confidence=ConfidenceLevel.MEDIUM if debugger_location_applied else ConfidenceLevel.LOW,
        )

    if owner._is_source_map_hook_application_request(protection_name, context):
        apply_preflight = owner._source_map_hook_apply_preflight(context)
        hook_input = owner._source_map_hook_install_input(context, apply_preflight)
        hook_kind, hook_spec = owner._source_map_hook_install_spec(hook_input)
        blockers = owner._source_map_hook_application_blockers(context, apply_preflight, hook_input, hook_kind, hook_spec)
        approve_hook = bool(
            context.get(
                "approve_source_map_hook_install",
                context.get("approveSourceMapHookInstall", context.get("approve_hook_install", context.get("approveHookInstall", False))),
            )
        )
        verification = [
            f"source_map_hook_application_preflight_status={apply_preflight.get('status', '')}",
            f"source_map_hook_application_selected_action_id={apply_preflight.get('selected_action_id', '')}",
            f"source_map_hook_application_selected_consumer={apply_preflight.get('selected_consumer', '')}",
            f"source_map_hook_application_selected_gate={apply_preflight.get('selected_review_gate', '')}",
            f"source_map_hook_application_review_approved={bool(context.get('review_approved', context.get('reviewApproved', False)))}",
            f"source_map_hook_application_install_approved={approve_hook}",
            f"source_map_hook_application_mode={context.get('mode', '')}",
            f"source_map_hook_application_hook_kind={hook_kind or 'unknown'}",
            f"source_map_hook_application_blockers={','.join(blockers)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if blockers:
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-hook-install-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime blocked Source Map selected hook application result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-hook-install-result.v1",
                    "status": "blocked",
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "review_approved": bool(context.get("review_approved", context.get("reviewApproved", False))),
                    "approve_source_map_hook_install": approve_hook,
                    "mode": context.get("mode", ""),
                    "hook_kind": hook_kind or "unknown",
                    "function_name": getattr(hook_spec, "function_name", None) if hook_spec else None,
                    "module_id": getattr(hook_spec, "module_id", None) if hook_spec else None,
                    "export_name": getattr(hook_spec, "export_name", None) if hook_spec else None,
                    "blockers": blockers,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "hook_installed": False,
                    "function_hook_installed": False,
                    "module_hook_installed": False,
                    "surface_executor_invoked": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.PARTIAL,
                artifacts=[artifact],
                next_action=owner._source_map_hook_application_next_action(blockers),
                confidence=ConfidenceLevel.LOW,
            )
        try:
            session = owner._ensure_session()
            page = session.get_active_page() or session.new_page()
        except Exception as exc:
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=[f"Native Web browser provider unavailable: {exc}", *verification],
                status=ExecutionStatus.FAILED,
                artifacts=[],
                next_action="ensure_browser_provider",
                confidence=ConfidenceLevel.LOW,
            )
        if hook_kind == "module":
            result = ModuleHookManager().install(page, hook_spec if isinstance(hook_spec, ModuleHookSpec) else None)
            primary_path = "virtual://workspace/module-hooks.json"
            timeline_path = "virtual://workspace/module-hook-timeline.json"
            primary_description = "Native Web runtime Source Map reviewed module hook install result."
            timeline_description = "Native Web runtime Source Map reviewed module hook timeline."
            install_action = f"install_source_map_module_hook:{hook_spec.module_id}:{hook_spec.export_name}" if isinstance(hook_spec, ModuleHookSpec) else "install_source_map_module_hook:<missing>"
            hook_target = hook_spec.hook_path() if isinstance(hook_spec, ModuleHookSpec) else "<missing>"
        else:
            result = FunctionHookManager().install(page, hook_spec if isinstance(hook_spec, FunctionHookSpec) else None)
            primary_path = "virtual://workspace/function-hooks.json"
            timeline_path = "virtual://workspace/function-hook-timeline.json"
            primary_description = "Native Web runtime Source Map reviewed function hook install result."
            timeline_description = "Native Web runtime Source Map reviewed function hook timeline."
            install_action = f"install_source_map_function_hook:{hook_spec.function_name}" if isinstance(hook_spec, FunctionHookSpec) else "install_source_map_function_hook:<missing>"
            hook_target = getattr(hook_spec, "function_name", "<missing>") if hook_spec else "<missing>"
        installed_count = len(result.installed)
        missing_count = len(result.missing)
        event_count = len(result.events)
        installed = bool(installed_count and result.status == "success")
        verification.extend(
            [
                f"source_map_hook_application_status={result.status}",
                f"source_map_hook_application_installed_count={installed_count}",
                f"source_map_hook_application_missing_count={missing_count}",
                f"source_map_hook_application_event_count={event_count}",
                "source_map_hook_application_browser_started=True",
                "source_map_hook_application_runtime_evaluated=True",
                "source_map_hook_application_cdp_command_sent=False",
                f"source_map_hook_application_hook_installed={installed}",
                f"source_map_hook_application_function_hook_installed={installed and hook_kind == 'function'}",
                f"source_map_hook_application_module_hook_installed={installed and hook_kind == 'module'}",
                "source_map_hook_application_surface_executor_invoked=True",
                "source_map_hook_application_calls_mcp=False",
                "source_map_hook_application_mobile_runtime_used=False",
            ]
        )
        if result.trigger:
            verification.append(f"source_map_hook_application_trigger_attempted={result.trigger.get('attempted', False)}")
            if result.trigger.get("error"):
                verification.append(f"source_map_hook_application_trigger_error={result.trigger['error']}")
        if result.error:
            verification.append(f"source_map_hook_application_error={result.error}")
        artifacts = [
            ArtifactRef(
                path="virtual://workspace/source-map-hook-install-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime explicit-review Source Map selected hook application result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-hook-install-result.v1",
                    "status": "success" if installed else "failed",
                    "hook_status": result.status,
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "approval_record_id": apply_preflight.get("approval_record_id", ""),
                    "reviewer": str(context.get("reviewer") or ""),
                    "review_approved": True,
                    "approve_source_map_hook_install": True,
                    "mode": "apply",
                    "hook_kind": hook_kind,
                    "hook_target": hook_target,
                    "function_name": getattr(hook_spec, "function_name", None) if hook_spec else None,
                    "function_paths": getattr(hook_spec, "function_paths", []) if isinstance(hook_spec, FunctionHookSpec) else [],
                    "module_id": getattr(hook_spec, "module_id", None) if hook_spec else None,
                    "export_name": getattr(hook_spec, "export_name", None) if hook_spec else None,
                    "require_path": getattr(hook_spec, "require_path", None) if hook_spec else None,
                    "installed_count": installed_count,
                    "missing_count": missing_count,
                    "event_count": event_count,
                    "browser_started": True,
                    "runtime_evaluated": True,
                    "cdp_command_sent": False,
                    "debugger_execution_performed": False,
                    "logpoint_installed": False,
                    "hook_installed": installed,
                    "function_hook_installed": installed and hook_kind == "function",
                    "module_hook_installed": installed and hook_kind == "module",
                    "rebuild_executed": False,
                    "surface_executor_invoked": True,
                    "automatic_hook_installation": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            ),
            ArtifactRef(
                path=primary_path,
                kind=ArtifactKind.JSON,
                description=primary_description,
                metadata={
                    "status": result.status,
                    "installed_count": installed_count,
                    "missing_count": missing_count,
                    "hook_kind": hook_kind,
                    "hook_target": hook_target,
                },
            ),
            ArtifactRef(
                path=timeline_path,
                kind=ArtifactKind.JSON,
                description=timeline_description,
                metadata={
                    "status": "success" if event_count else "not_observed",
                    "event_count": event_count,
                    "hook_kind": hook_kind,
                    "hook_target": hook_target,
                },
            ),
        ]
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=[install_action] if installed else [],
            verification=verification,
            status=ExecutionStatus.SUCCESS if installed else ExecutionStatus.PARTIAL if missing_count else ExecutionStatus.FAILED,
            artifacts=artifacts,
            next_action="inspect_source_map_hook_events" if event_count else "trigger_code_path_or_adjust_source_map_hook_input",
            confidence=ConfidenceLevel.MEDIUM if installed else ConfidenceLevel.LOW,
        )

    if owner._is_source_map_rebuild_metadata_application_request(protection_name, context):
        apply_preflight = owner._source_map_rebuild_metadata_apply_preflight(context)
        metadata_input = owner._source_map_rebuild_metadata_input(context, apply_preflight)
        blockers = owner._source_map_rebuild_metadata_application_blockers(context, apply_preflight, metadata_input)
        digest = str(metadata_input.get("source_content_digest") or metadata_input.get("sha256") or "")
        source_content_available = bool(metadata_input.get("source_content_available", metadata_input.get("sourceContentAvailable", False)))
        verification = [
            f"source_map_rebuild_metadata_application_preflight_status={apply_preflight.get('status', '')}",
            f"source_map_rebuild_metadata_application_selected_action_id={apply_preflight.get('selected_action_id', '')}",
            f"source_map_rebuild_metadata_application_selected_consumer={apply_preflight.get('selected_consumer', '')}",
            f"source_map_rebuild_metadata_application_selected_gate={apply_preflight.get('selected_review_gate', '')}",
            f"source_map_rebuild_metadata_application_review_approved={bool(context.get('review_approved', context.get('reviewApproved', False)))}",
            f"source_map_rebuild_metadata_application_approved={bool(context.get('approve_source_map_rebuild_metadata', context.get('approveSourceMapRebuildMetadata', context.get('approve_rebuild_source_metadata', context.get('approveRebuildSourceMetadata', False)))))}",
            f"source_map_rebuild_metadata_application_mode={context.get('mode', '')}",
            f"source_map_rebuild_metadata_application_digest={digest}",
            f"source_map_rebuild_metadata_application_blockers={','.join(blockers)}",
            "source_map_rebuild_metadata_application_browser_started=False",
            "source_map_rebuild_metadata_application_cdp_command_sent=False",
            "source_map_rebuild_metadata_application_runtime_evaluated=False",
            "source_map_rebuild_metadata_application_raw_exported=False",
            "source_map_rebuild_metadata_application_preview_exported=False",
            "source_map_rebuild_metadata_application_rebuild_bundle_generated=False",
            "source_map_rebuild_metadata_application_calls_mcp=False",
            "source_map_rebuild_metadata_application_mobile_runtime_used=False",
            f"context_keys={sorted(context.keys())}",
        ]
        if blockers:
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-rebuild-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime blocked Source Map selected rebuild metadata application result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-rebuild-result.v1",
                    "status": "blocked",
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "review_approved": bool(context.get("review_approved", context.get("reviewApproved", False))),
                    "approve_source_map_rebuild_metadata": bool(
                        context.get(
                            "approve_source_map_rebuild_metadata",
                            context.get("approveSourceMapRebuildMetadata", context.get("approve_rebuild_source_metadata", context.get("approveRebuildSourceMetadata", False))),
                        )
                    ),
                    "mode": context.get("mode", ""),
                    "source_content_digest": digest,
                    "source_content_available": source_content_available,
                    "blockers": blockers,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "raw_source_content_exported": False,
                    "preview_exported": False,
                    "rebuild_metadata_applied": False,
                    "rebuild_bundle_generated": False,
                    "rebuild_executed": False,
                    "surface_executor_invoked": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.PARTIAL,
                artifacts=[artifact],
                next_action=owner._source_map_rebuild_metadata_application_next_action(blockers),
                confidence=ConfidenceLevel.LOW,
            )
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-rebuild-result.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime explicit-review Source Map selected rebuild metadata application result.",
            metadata={
                "schema_version": "reverse-deepagent.source-map-rebuild-result.v1",
                "status": "success",
                "selected_action_id": apply_preflight.get("selected_action_id", ""),
                "selected_consumer": apply_preflight.get("selected_consumer", ""),
                "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                "approval_record_id": apply_preflight.get("approval_record_id", ""),
                "reviewer": str(context.get("reviewer") or ""),
                "review_approved": True,
                "approve_source_map_rebuild_metadata": True,
                "mode": "apply",
                "source_content_digest": digest,
                "source_content_available": source_content_available,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "raw_source_content_included": False,
                "metadata_only": True,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_metadata_applied": True,
                "rebuild_bundle_generated": False,
                "rebuild_executed": False,
                "surface_executor_invoked": True,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        )
        verification.extend(
            [
                "source_map_rebuild_metadata_application_status=success",
                "source_map_rebuild_metadata_application_metadata_only=True",
                "source_map_rebuild_metadata_application_rebuild_metadata_applied=True",
                "source_map_rebuild_metadata_application_surface_executor_invoked=True",
            ]
        )
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=[f"apply_source_map_rebuild_metadata:{digest}"],
            verification=verification,
            status=ExecutionStatus.SUCCESS,
            artifacts=[artifact],
            next_action="review_source_map_rebuild_metadata_result_before_rebuild_generation",
            confidence=ConfidenceLevel.MEDIUM,
        )

    if owner._is_source_map_rebuild_generation_request(protection_name, context):
        metadata_result = owner._source_map_rebuild_generation_metadata_result(context)
        task_card_payload, task_card_error = owner._source_map_rebuild_generation_object_input(
            context,
            "task_card",
            "taskCard",
            "task_card_json",
            "taskCardJson",
            "reviewed_task_card",
            "reviewedTaskCard",
        )
        final_result_payload, final_result_error = owner._source_map_rebuild_generation_object_input(
            context,
            "final_result",
            "finalResult",
            "final_result_json",
            "finalResultJson",
            "reviewed_final_result",
            "reviewedFinalResult",
        )
        artifact_root = str(context.get("artifact_root") or context.get("artifactRoot") or "").strip()
        blockers = owner._source_map_rebuild_generation_blockers(
            context,
            metadata_result,
            artifact_root,
            task_card_payload,
            final_result_payload,
            task_card_error,
            final_result_error,
        )
        digest = str(
            metadata_result.get("source_content_digest")
            or metadata_result.get("sourceContentDigest")
            or metadata_result.get("sha256")
            or ""
        )
        approve_generation = bool(
            context.get(
                "approve_source_map_rebuild_generation",
                context.get("approveSourceMapRebuildGeneration", context.get("approve_rebuild_generation", context.get("approveRebuildGeneration", False))),
            )
        )
        verification = [
            f"source_map_rebuild_generation_metadata_status={metadata_result.get('status', '')}",
            f"source_map_rebuild_generation_metadata_digest={digest}",
            f"source_map_rebuild_generation_review_approved={bool(context.get('review_approved', context.get('reviewApproved', False)))}",
            f"source_map_rebuild_generation_approved={approve_generation}",
            f"source_map_rebuild_generation_mode={context.get('mode', '')}",
            f"source_map_rebuild_generation_artifact_root={artifact_root}",
            f"source_map_rebuild_generation_blockers={','.join(blockers)}",
            "source_map_rebuild_generation_browser_started=False",
            "source_map_rebuild_generation_cdp_command_sent=False",
            "source_map_rebuild_generation_runtime_evaluated=False",
            "source_map_rebuild_generation_source_map_fetched=False",
            "source_map_rebuild_generation_raw_exported=False",
            "source_map_rebuild_generation_preview_exported=False",
            "source_map_rebuild_generation_calls_mcp=False",
            "source_map_rebuild_generation_mobile_runtime_used=False",
            f"context_keys={sorted(context.keys())}",
        ]
        if blockers:
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-rebuild-generation-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime blocked Source Map reviewed rebuild bundle generation result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-rebuild-generation-result.v1",
                    "status": "blocked",
                    "metadata_result_status": metadata_result.get("status", "missing") if metadata_result else "missing",
                    "metadata_result_verified": False,
                    "source_content_digest": digest,
                    "review_approved": bool(context.get("review_approved", context.get("reviewApproved", False))),
                    "approve_source_map_rebuild_generation": approve_generation,
                    "mode": context.get("mode", ""),
                    "artifact_root": artifact_root,
                    "task_card_input_error": task_card_error,
                    "final_result_input_error": final_result_error,
                    "blockers": blockers,
                    "rebuild_metadata_applied": bool(metadata_result.get("rebuild_metadata_applied")) if metadata_result else False,
                    "rebuild_bundle_generated": False,
                    "rebuild_executed": False,
                    "replay_executed": False,
                    "scrapy_executed": False,
                    "delivery_executed": False,
                    "external_delivery_performed": False,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "source_map_fetched": False,
                    "raw_source_content_exported": False,
                    "preview_exported": False,
                    "raw_source_content_included": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.PARTIAL,
                artifacts=[artifact],
                next_action=owner._source_map_rebuild_generation_next_action(blockers),
                confidence=ConfidenceLevel.LOW,
            )
        try:
            task_card = TaskCard.model_validate(task_card_payload)
            final_result = FinalResult.model_validate(final_result_payload)
            rebuild_result = write_rebuild_bundle(Path(artifact_root), task_card, final_result)
        except Exception as exc:
            verification.extend(
                [
                    f"source_map_rebuild_generation_status=failed",
                    f"source_map_rebuild_generation_error={exc}",
                    "source_map_rebuild_generation_rebuild_bundle_generated=False",
                ]
            )
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-rebuild-generation-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime failed Source Map reviewed rebuild bundle generation result.",
                metadata={
                    "schema_version": "reverse-deepagent.source-map-rebuild-generation-result.v1",
                    "status": "failed",
                    "metadata_result_status": metadata_result.get("status", ""),
                    "metadata_result_verified": True,
                    "source_content_digest": digest,
                    "reviewer": str(context.get("reviewer") or ""),
                    "review_approved": True,
                    "approve_source_map_rebuild_generation": True,
                    "mode": "apply",
                    "artifact_root": artifact_root,
                    "error": str(exc),
                    "rebuild_bundle_generated": False,
                    "rebuild_executed": False,
                    "replay_executed": False,
                    "scrapy_executed": False,
                    "delivery_executed": False,
                    "external_delivery_performed": False,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "source_map_fetched": False,
                    "raw_source_content_exported": False,
                    "preview_exported": False,
                    "raw_source_content_included": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.FAILED,
                artifacts=[artifact],
                next_action="inspect_source_map_rebuild_generation_failure",
                confidence=ConfidenceLevel.LOW,
            )
        generated_files = dict(rebuild_result.generated_files or {})
        rebuild_plan = rebuild_result.rebuild_plan or {}
        ready = bool(rebuild_plan.get("ready"))
        strategy = rebuild_plan.get("algorithm_strategy") if isinstance(rebuild_plan.get("algorithm_strategy"), dict) else {}
        verification.extend(
            [
                "source_map_rebuild_generation_status=success",
                f"source_map_rebuild_generation_ready={ready}",
                f"source_map_rebuild_generation_rebuild_status={rebuild_result.status.value if hasattr(rebuild_result.status, 'value') else rebuild_result.status}",
                f"source_map_rebuild_generation_generated_file_count={len(generated_files)}",
                f"source_map_rebuild_generation_artifact_count={len(rebuild_result.artifacts)}",
                f"source_map_rebuild_generation_algorithm_strategy_id={strategy.get('id', '')}",
                f"source_map_rebuild_generation_rebuild_bundle_generated={bool(generated_files)}",
                "source_map_rebuild_generation_rebuild_executed=True",
                "source_map_rebuild_generation_replay_executed=False",
                "source_map_rebuild_generation_scrapy_executed=False",
                "source_map_rebuild_generation_delivery_executed=False",
                "source_map_rebuild_generation_external_delivery_performed=False",
            ]
        )
        result_artifact = ArtifactRef(
            path="virtual://workspace/source-map-rebuild-generation-result.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime explicit-review Source Map rebuild bundle generation result.",
            metadata={
                "schema_version": "reverse-deepagent.source-map-rebuild-generation-result.v1",
                "status": "success",
                "metadata_result_status": metadata_result.get("status", ""),
                "metadata_result_verified": True,
                "selected_consumer": "rebuild",
                "selected_review_gate": "explicit_rebuild_source_metadata_review",
                "source_content_digest": digest,
                "reviewer": str(context.get("reviewer") or ""),
                "review_approved": True,
                "approve_source_map_rebuild_generation": True,
                "mode": "apply",
                "artifact_root": artifact_root,
                "rebuild_metadata_applied": True,
                "metadata_only": False,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "raw_source_content_included": False,
                "source_map_fetched": False,
                "rebuild_bundle_generated": bool(generated_files),
                "rebuild_executed": True,
                "replay_executed": False,
                "scrapy_executed": False,
                "delivery_executed": False,
                "external_delivery_performed": False,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
                "generated_file_keys": sorted(generated_files),
                "generated_file_count": len(generated_files),
                "artifact_count": len(rebuild_result.artifacts),
                "rebuild_status": rebuild_result.status.value if hasattr(rebuild_result.status, "value") else str(rebuild_result.status),
                "rebuild_ready": ready,
                "algorithm_strategy_id": strategy.get("id"),
                "generated_files": generated_files,
                "rebuild_next_action": rebuild_result.next_action,
            },
        )
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=[f"generate_source_map_rebuild_bundle:{digest or 'reviewed-input'}"],
            verification=verification,
            status=ExecutionStatus.SUCCESS if generated_files else ExecutionStatus.PARTIAL,
            artifacts=[result_artifact, *rebuild_result.artifacts],
            next_action="review_generated_rebuild_bundle_before_delivery" if ready else "manual_port_or_expand_source_context",
            confidence=ConfidenceLevel.MEDIUM if ready else ConfidenceLevel.LOW,
        )

    if owner._is_source_map_source_logpoint_application_request(protection_name, context):
        apply_preflight = owner._source_map_source_logpoint_apply_preflight(context)
        install_input = owner._source_map_source_logpoint_install_input(context)
        blockers = owner._source_map_source_logpoint_application_blockers(context, apply_preflight, install_input)
        spec = SourceLogpointSpec.from_context(install_input)
        verification = [
            f"source_map_source_logpoint_application_preflight_status={apply_preflight.get('status', '')}",
            f"source_map_source_logpoint_application_selected_action_id={apply_preflight.get('selected_action_id', '')}",
            f"source_map_source_logpoint_application_selected_consumer={apply_preflight.get('selected_consumer', '')}",
            f"source_map_source_logpoint_application_selected_gate={apply_preflight.get('selected_review_gate', '')}",
            f"source_map_source_logpoint_application_review_approved={bool(context.get('review_approved', context.get('reviewApproved', False)))}",
            f"source_map_source_logpoint_application_install_approved={bool(context.get('approve_source_logpoint_install', context.get('approveSourceLogpointInstall', False)))}",
            f"source_map_source_logpoint_application_mode={context.get('mode', '')}",
            f"source_map_source_logpoint_application_blockers={','.join(blockers)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if blockers:
            artifact = ArtifactRef(
                path="virtual://workspace/source-map-source-logpoint-install-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime blocked Source Map selected source-logpoint application result.",
                metadata={
                    "status": "blocked",
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "review_approved": bool(context.get("review_approved", context.get("reviewApproved", False))),
                    "approve_source_logpoint_install": bool(context.get("approve_source_logpoint_install", context.get("approveSourceLogpointInstall", False))),
                    "mode": context.get("mode", ""),
                    "blockers": blockers,
                    "browser_started": False,
                    "runtime_evaluated": False,
                    "cdp_command_sent": False,
                    "logpoint_installed": False,
                    "surface_executor_invoked": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=verification,
                status=ExecutionStatus.PARTIAL,
                artifacts=[artifact],
                next_action=owner._source_map_source_logpoint_application_next_action(blockers),
                confidence=ConfidenceLevel.LOW,
            )
        try:
            session = owner._ensure_session()
            page = session.get_active_page() or session.new_page()
        except Exception as exc:
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=[f"Native Web browser provider unavailable: {exc}", *verification],
                status=ExecutionStatus.FAILED,
                artifacts=[],
                next_action="ensure_browser_provider",
                confidence=ConfidenceLevel.LOW,
            )
        result = SourceLogpointManager().install(page, spec)
        breakpoint_count = len(result.breakpoints)
        event_count = len(result.events)
        installed = bool(breakpoint_count and result.status == "success")
        verification.extend(
            [
                f"source_map_source_logpoint_application_status={result.status}",
                f"source_map_source_logpoint_application_breakpoint_count={breakpoint_count}",
                f"source_map_source_logpoint_application_event_count={event_count}",
                f"source_map_source_logpoint_application_browser_started=True",
                f"source_map_source_logpoint_application_runtime_evaluated=True",
                f"source_map_source_logpoint_application_cdp_command_sent={bool(breakpoint_count)}",
                f"source_map_source_logpoint_application_logpoint_installed={installed}",
                "source_map_source_logpoint_application_surface_executor_invoked=True",
            ]
        )
        if spec and spec.remap:
            verification.append(f"source_map_source_logpoint_application_remap_status={spec.remap.get('status')}")
            if spec.remap.get("strategy"):
                verification.append(f"source_map_source_logpoint_application_remap_strategy={spec.remap['strategy']}")
        if result.trigger:
            verification.append(f"source_map_source_logpoint_application_trigger_attempted={result.trigger.get('attempted', False)}")
            if result.trigger.get("error"):
                verification.append(f"source_map_source_logpoint_application_trigger_error={result.trigger['error']}")
        if result.reason:
            verification.append(f"source_map_source_logpoint_application_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_source_logpoint_application_error={result.error}")
        artifacts = [
            ArtifactRef(
                path="virtual://workspace/source-map-source-logpoint-install-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime explicit-review Source Map selected source-logpoint application result.",
                metadata={
                    "status": "success" if installed else "failed",
                    "source_logpoint_status": result.status,
                    "selected_action_id": apply_preflight.get("selected_action_id", ""),
                    "selected_consumer": apply_preflight.get("selected_consumer", ""),
                    "selected_review_gate": apply_preflight.get("selected_review_gate", ""),
                    "approval_record_id": apply_preflight.get("approval_record_id", ""),
                    "reviewer": str(context.get("reviewer") or ""),
                    "review_approved": True,
                    "approve_source_logpoint_install": True,
                    "mode": "apply",
                    "breakpoint_count": breakpoint_count,
                    "event_count": event_count,
                    "url_pattern": spec.url_pattern if spec else "<missing>",
                    "line_number": spec.line_number if spec else 0,
                    "column_number": spec.column_number if spec else None,
                    "label": spec.label if spec else None,
                    "remap": spec.remap if spec else {},
                    "browser_started": True,
                    "runtime_evaluated": True,
                    "cdp_command_sent": bool(breakpoint_count),
                    "logpoint_installed": installed,
                    "hook_installed": False,
                    "rebuild_executed": False,
                    "surface_executor_invoked": True,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            ),
            ArtifactRef(
                path="virtual://workspace/source-logpoints.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime source logpoint install result.",
                metadata={
                    "status": result.status,
                    "breakpoint_count": breakpoint_count,
                    "url_pattern": spec.url_pattern if spec else "<missing>",
                    "line_number": spec.line_number if spec else 0,
                    "column_number": spec.column_number if spec else None,
                    "remap": spec.remap if spec else {},
                },
            ),
            ArtifactRef(
                path="virtual://workspace/source-logpoint-timeline.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime source logpoint timeline.",
                metadata={
                    "status": "success" if event_count else "not_observed",
                    "event_count": event_count,
                    "url_pattern": spec.url_pattern if spec else "<missing>",
                    "line_number": spec.line_number if spec else 0,
                    "column_number": spec.column_number if spec else None,
                    "remap": spec.remap if spec else {},
                },
            ),
        ]
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=([f"install_source_map_source_logpoint:{spec.url_pattern}:{spec.line_number}"] if spec and installed else []),
            verification=verification,
            status=ExecutionStatus.SUCCESS if installed else ExecutionStatus.FAILED,
            artifacts=artifacts,
            next_action="inspect_source_map_source_logpoint_events" if event_count else "trigger_code_path_or_adjust_source_map_source_logpoint",
            confidence=ConfidenceLevel.MEDIUM if installed else ConfidenceLevel.LOW,
        )

    if owner._is_source_map_followthrough_dispatcher_result_request(protection_name, context):
        spec = SourceMapFollowthroughDispatcherResultSpec.from_context(context)
        result = SourceMapFollowthroughDispatcherManager().dispatch(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        dispatch_decision = descriptor.get("dispatch_decision") if isinstance(descriptor.get("dispatch_decision"), dict) else {}
        verification = [
            f"source_map_followthrough_dispatcher_result_status={result.status}",
            f"source_map_followthrough_dispatcher_result_id={descriptor.get('dispatcher_result_id', '')}",
            f"source_map_followthrough_dispatcher_result_selected_consumer={descriptor.get('selected_consumer', '')}",
            f"source_map_followthrough_dispatcher_result_dispatch_surface={descriptor.get('dispatch_surface', '')}",
            f"source_map_followthrough_dispatcher_result_required_artifact={descriptor.get('required_result_artifact', '')}",
            f"source_map_followthrough_dispatcher_result_journal_id={descriptor.get('journal_id', '')}",
            f"source_map_followthrough_dispatcher_result_transaction_preflight_id={descriptor.get('transaction_preflight_id', '')}",
            f"source_map_followthrough_dispatcher_result_approval_record_id={descriptor.get('approval_record_id', '')}",
            f"source_map_followthrough_dispatcher_result_transaction_plan_id={descriptor.get('transaction_plan_id', '')}",
            f"source_map_followthrough_dispatcher_result_apply_preflight_verified={descriptor.get('apply_preflight_verified', False)}",
            f"source_map_followthrough_dispatcher_result_decision_recorded={descriptor.get('dispatcher_decision_recorded', False)}",
            f"source_map_followthrough_dispatcher_result_dispatcher_mvp_invoked={descriptor.get('dispatcher_mvp_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_dispatcher_invoked={descriptor.get('dispatcher_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_dispatch_target_invoked={descriptor.get('dispatch_target_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_executor_invoked={descriptor.get('executor_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_selected_executor_invoked={descriptor.get('selected_executor_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_selected_executor_apply_preflight_invoked={descriptor.get('selected_executor_apply_preflight_invoked', False)}",
            f"source_map_followthrough_dispatcher_result_requires_selected_executor_apply_preflight={descriptor.get('requires_selected_executor_apply_preflight', False)}",
            f"source_map_followthrough_dispatcher_result_ready_to_execute_selected_executor_now={descriptor.get('ready_to_execute_selected_executor_now', False)}",
            f"source_map_followthrough_dispatcher_result_browser_started={policy.get('browser_started', False)}",
            f"source_map_followthrough_dispatcher_result_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_followthrough_dispatcher_result_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_followthrough_dispatcher_result_logpoint_installed={policy.get('logpoint_installed', False)}",
            f"source_map_followthrough_dispatcher_result_hook_installed={policy.get('hook_installed', False)}",
            f"source_map_followthrough_dispatcher_result_rebuild_executed={policy.get('rebuild_executed', False)}",
            f"source_map_followthrough_dispatcher_result_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_followthrough_dispatcher_result_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_followthrough_dispatcher_result_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_followthrough_dispatcher_result_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-dispatcher-result.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime explicit-review-only Source Map follow-through dispatcher MVP result.",
            metadata={
                "status": result.status,
                "dispatcher_result_id": descriptor.get("dispatcher_result_id", ""),
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "dispatch_surface": descriptor.get("dispatch_surface", ""),
                "required_result_artifact": descriptor.get("required_result_artifact", ""),
                "selected_executor_apply_preflight_artifact": descriptor.get("selected_executor_apply_preflight_artifact", ""),
                "journal_id": descriptor.get("journal_id", ""),
                "transaction_preflight_id": descriptor.get("transaction_preflight_id", ""),
                "approval_record_id": descriptor.get("approval_record_id", ""),
                "transaction_plan_id": descriptor.get("transaction_plan_id", ""),
                "apply_preflight_verified": bool(descriptor.get("apply_preflight_verified", False)),
                "dispatcher_decision_recorded": bool(descriptor.get("dispatcher_decision_recorded", False)),
                "dispatcher_mvp_invoked": bool(descriptor.get("dispatcher_mvp_invoked", False)),
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "selected_executor_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
                "runtime_apply_preflight_invoked": False,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "ready_to_execute_selected_executor_now": False,
                "requires_selected_executor_apply_preflight": True,
                "requires_separate_selected_executor_apply_preflight": True,
                "requires_separate_selected_executor_execution": True,
                "will_invoke_dispatch_target": False,
                "will_invoke_selected_executor": False,
                "will_run_selected_executor_apply_preflight": False,
                "will_execute_debugger": False,
                "will_install_source_logpoint": False,
                "will_install_hook": False,
                "will_run_rebuild": False,
                "automatic_dispatch_supported": False,
                "automatic_followthrough_supported": False,
                "automatic_execution_supported": False,
                "dispatch_decision": dispatch_decision,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
                "side_effect_policy": policy,
                "descriptor": descriptor,
            },
        )
        if result.status == "dispatched":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_selected_executor_apply_preflight"
            actions = ["record_source_map_followthrough_dispatcher_result"]
        elif result.status in {"ready_for_review", "review_required", "blocked"}:
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "review_source_map_followthrough_dispatcher_mvp"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_followthrough_dispatcher_result"
            actions = []
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "dispatched" else ConfidenceLevel.LOW,
        )

    if owner._is_source_map_fetch_request(protection_name, context):
        spec = SourceMapFetchSpec.from_context(context)
        result = SourceMapFetchManager().plan_or_fetch(spec)
        plan = result.plan if isinstance(result.plan, dict) else {}
        fetch_result = result.result if isinstance(result.result, dict) else {}
        verification = [
            f"source_map_fetch_status={result.status}",
            f"source_map_fetch_plan_status={plan.get('status', 'missing')}",
            f"source_map_fetch_detected={plan.get('source_mapping_url_detected', False)}",
            f"source_map_fetch_allowed={plan.get('fetch_allowed', False)}",
            f"source_map_fetch_attempted={fetch_result.get('attempted', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if plan.get("blocking_reason"):
            verification.append(f"source_map_fetch_blocking_reason={plan['blocking_reason']}")
        if fetch_result.get("byte_count") is not None:
            verification.append(f"source_map_fetch_byte_count={fetch_result['byte_count']}")
        if fetch_result.get("indexed_section_url_count") is not None:
            verification.append(f"source_map_indexed_section_url_count={fetch_result['indexed_section_url_count']}")
        if result.reason:
            verification.append(f"source_map_fetch_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_fetch_error={result.error}")
        artifacts = [
            ArtifactRef(
                path="virtual://workspace/source-map-fetch-plan.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime external Source Map fetch plan.",
                metadata={
                    "status": result.status,
                    "plan_status": plan.get("status"),
                    "source_map_url_redacted": plan.get("source_map_url_redacted"),
                    "fetch_allowed": plan.get("fetch_allowed", False),
                    "review_required": plan.get("review_required", True),
                },
            ),
            ArtifactRef(
                path="virtual://workspace/source-map-fetch-result.json",
                kind=ArtifactKind.JSON,
                description="Native Web runtime external Source Map fetch result metadata.",
                metadata={
                    "status": result.status,
                    "fetch_attempted": fetch_result.get("attempted", False),
                    "fetch_ok": fetch_result.get("ok", False),
                    "byte_count": fetch_result.get("byte_count", 0),
                    "sources_count": fetch_result.get("sources_count", 0),
                    "indexed_section_url_count": fetch_result.get("indexed_section_url_count", 0),
                },
            ),
        ]
        if result.status == "success":
            status = ExecutionStatus.SUCCESS
            next_action = "review_fetched_source_map_metadata_before_remap"
            actions = ["fetch_source_map"]
        elif result.status == "planned":
            status = ExecutionStatus.SUCCESS
            next_action = "review_source_map_fetch_plan_before_execution"
            actions = ["plan_source_map_fetch"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = "approve_source_map_fetch_or_adjust_url_policy"
            actions = ["plan_source_map_fetch"]
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_fetch_failure"
            actions = []
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=artifacts,
            next_action=next_action,
            confidence=ConfidenceLevel.MEDIUM if result.status in {"planned", "success"} else ConfidenceLevel.LOW,
        )
    return None
