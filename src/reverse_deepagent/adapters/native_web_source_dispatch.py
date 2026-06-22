from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.source_maps import (
    BundlerSymbolScopeManager,
    BundlerSymbolScopeSpec,
    SourceMapConsumerActionPlanManager,
    SourceMapConsumerActionPlanSpec,
    SourceMapConsumerMaterializationManager,
    SourceMapConsumerMaterializationSpec,
    SourceMapFollowthroughChainReadinessManager,
    SourceMapFollowthroughChainReadinessSpec,
    SourceMapFollowthroughDispatchPreflightManager,
    SourceMapFollowthroughDispatchPreflightSpec,
    SourceMapFollowthroughOneStepPlanManager,
    SourceMapFollowthroughOneStepPlanSpec,
    SourceMapFollowthroughReviewManager,
    SourceMapFollowthroughReviewSpec,
    SourceMapFollowthroughSurfaceSelectionManager,
    SourceMapFollowthroughSurfaceSelectionSpec,
    SourceMapLookupManager,
    SourceMapLookupSpec,
    SourceMapReadinessManager,
    SourceMapReadinessSpec,
    SourceMapSourceContentManager,
    SourceMapSourceContentSpec,
    SourceMapTerminalReviewPackageManager,
    SourceMapTerminalReviewPackageSpec,
    SourceMapTypedPayloadPreflightManager,
    SourceMapTypedPayloadPreflightSpec,
)
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    ExecutionStatus,
    ProtectionResult,
)


def dispatch_source_map_review_evidence(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Route the lowest-side-effect Source Map review-evidence requests.

    This helper is intentionally small: predicates stay on ``owner`` so
    ``_dispatch_source(...)`` order remains mechanically auditable, while
    manager business rules and payload construction stay equivalent to the
    original NativeWebRuntime branches.
    """
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
            metadata={
                "status": result.status,
                "lookup_direction": request.get("lookup_direction", ""),
                "mapping_found": bool(descriptor.get("mapping_found", False)),
                "strategy": location.get("strategy", ""),
                "review_only": True,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
            },
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
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
            metadata={
                "status": result.status,
                "source_content_available": bool(descriptor.get("source_content_available", False)),
                "original_source": request.get("original_source", ""),
                "source_index": request.get("source_index"),
                "sha256": content_summary.get("sha256", ""),
                "review_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
            },
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
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
            metadata={
                "status": result.status,
                "bundler_kind": classification.get("bundler_kind", "unknown"),
                "confidence": classification.get("confidence", "low"),
                "symbol_name": request.get("symbol_name", ""),
                "scope_candidate_count": descriptor.get("scope_candidate_count", 0),
                "review_only": True,
                "fetch_source_map": False,
                "logpoint_installed": False,
            },
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=["review_bundler_symbol_scope"] if result.status in {"ready_for_review", "blocked"} else [],
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=next_action,
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    return None


def dispatch_source_map_descriptor_evidence(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Route the next tier of Source Map read-only descriptor / review-plan evidence
    requests (S2 extraction).

    These 10 predicates are all review-only branches with NO side effects
    (no browser started, no CDP command, no debugger attach, no hook install,
    no rebuild, no logpoint apply).  Order matches ``_dispatch_source``.
    """
    # ------------------------------------------------------------------ #
    # Branch 9: source_map_followthrough_dispatch_preflight
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-dispatch-preflight.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime read-only Source Map follow-through dispatch preflight descriptor.",
            metadata={
                "status": result.status,
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "planned_next_action": descriptor.get("planned_next_action", ""),
                "planned_required_artifact": descriptor.get("planned_required_artifact", ""),
                "dispatch_surface": dispatch_target.get("dispatch_surface", ""),
                "dispatcher_input_ready_for_review": bool(descriptor.get("dispatcher_input_ready_for_review", False)),
                "review_only": True,
                "preflight_only": True,
                "plan_only": True,
                "dispatch_preflight_only": True,
                "orchestration_only": True,
                "handoff_only": True,
                "will_invoke_dispatch_target": False,
                "will_invoke_next_action": False,
                "will_record_approval": False,
                "will_run_apply_preflight": False,
                "will_execute_debugger": False,
                "will_install_source_logpoint": False,
                "will_install_hook": False,
                "will_run_rebuild": False,
                "automatic_dispatch_supported": False,
                "automatic_followthrough_supported": False,
                "automatic_execution_supported": False,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 8: source_map_followthrough_one_step_plan
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-one-step-plan.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map follow-through one-step orchestration plan.",
            metadata={
                "status": result.status,
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "source_chain_completed_stage": descriptor.get("source_chain_completed_stage", ""),
                "source_chain_next_stage": descriptor.get("source_chain_next_stage", ""),
                "source_chain_next_action": descriptor.get("source_chain_next_action", ""),
                "source_chain_next_required_artifact": descriptor.get("source_chain_next_required_artifact", ""),
                "planned_step_ready_for_review": bool(descriptor.get("planned_step_ready_for_review", False)),
                "step_id": planned_step.get("step_id", ""),
                "review_only": True,
                "plan_only": True,
                "one_step_plan_only": True,
                "orchestration_only": True,
                "handoff_only": True,
                "will_invoke_next_action": False,
                "will_record_approval": False,
                "will_run_apply_preflight": False,
                "will_execute_debugger": False,
                "will_install_source_logpoint": False,
                "will_install_hook": False,
                "will_run_rebuild": False,
                "automatic_followthrough_supported": False,
                "automatic_execution_supported": False,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 7: source_map_followthrough_chain_readiness
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-chain-readiness.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime read-only Source Map follow-through chain readiness descriptor.",
            metadata={
                "status": result.status,
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "completed_stage": descriptor.get("completed_stage", ""),
                "next_stage": descriptor.get("next_stage", ""),
                "next_required_artifact": descriptor.get("next_required_artifact", ""),
                "next_required_action": descriptor.get("next_required_action", ""),
                "selected_executor_result_ready": bool(descriptor.get("selected_executor_result_ready", False)),
                "ready_for_selected_executor_review": bool(descriptor.get("ready_for_selected_executor_review", False)),
                "review_only": True,
                "plan_only": True,
                "readiness_descriptor_only": True,
                "orchestration_only": True,
                "handoff_only": True,
                "automatic_followthrough_supported": False,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 10: source_map_terminal_review_package
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-terminal-review-package.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime read-only Source Map terminal review package / audit handoff.",
            metadata={
                "status": result.status,
                "selected_action_id": descriptor.get("selected_action_id", ""),
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "completion_status": descriptor.get("completion_status", ""),
                "terminal_review_candidate": bool(descriptor.get("terminal_review_candidate", False)),
                "followup_required": bool(descriptor.get("followup_required", False)),
                "package_kind": package.get("package_kind", ""),
                "recommended_review_action": package.get("recommended_review_action", ""),
                "source_completion_checkpoint_digest_sha256": descriptor.get("source_completion_checkpoint_digest_sha256", ""),
                "ready_for_terminal_review": bool(descriptor.get("ready_for_terminal_review", False)),
                "ready_for_audit_handoff_review": bool(descriptor.get("ready_for_audit_handoff_review", False)),
                "ready_to_execute_now": False,
                "execute_next_automatically": False,
                "automatic_followthrough_supported": False,
                "recommended_action_executed": False,
                "review_only": True,
                "audit_handoff_only": True,
                "terminal_review_package_only": True,
                "browser_started_by_package": False,
                "cdp_command_sent_by_package": False,
                "runtime_evaluated_by_package": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 6: source_map_followthrough_surface_selection
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-surface-selection.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map follow-through single-surface selection descriptor.",
            metadata={
                "status": result.status,
                "candidate_review_count": descriptor.get("candidate_review_count", 0),
                "selected_action_id": descriptor.get("selected_action_id", ""),
                "selected_consumer": descriptor.get("selected_consumer", ""),
                "selected_followthrough_review_surface": descriptor.get("selected_followthrough_review_surface", ""),
                "selected_payload_kind": selected_review.get("payload_kind", ""),
                "ready_for_surface_review": bool(descriptor.get("ready_for_surface_review", False)),
                "review_only": True,
                "plan_only": True,
                "selection_only": True,
                "handoff_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 5: source_map_followthrough_review
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-followthrough-review.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map follow-through review surface descriptor.",
            metadata={
                "status": result.status,
                "typed_payload_schema_version": descriptor.get("typed_payload_schema_version", ""),
                "followthrough_review_count": len(reviews),
                "ready_followthrough_review_count": descriptor.get("ready_followthrough_review_count", 0),
                "consumers": consumers,
                "followthrough_review_surfaces": surfaces,
                "ready_for_explicit_review": bool(descriptor.get("ready_for_explicit_review", False)),
                "review_only": True,
                "plan_only": True,
                "handoff_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 4: source_map_typed_payload_preflight
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-typed-payload-preflight.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map typed payload follow-through preflight descriptor.",
            metadata={
                "status": result.status,
                "typed_payload_schema_version": descriptor.get("typed_payload_schema_version", ""),
                "preflight_payload_count": len(preflights),
                "consumers": consumers,
                "followthrough_review_surfaces": surfaces,
                "ready_for_followthrough_review": bool(descriptor.get("ready_for_followthrough_review", False)),
                "review_only": True,
                "plan_only": True,
                "preflight_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 3: source_map_consumer_materialization
    # ------------------------------------------------------------------ #
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
        typed_payload_consumers = sorted(
            {
                str(item.get("consumer"))
                for item in typed_payloads
                if isinstance(item, dict) and item.get("consumer")
            }
        )
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-consumer-materialization.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map consumer materialization descriptor.",
            metadata={
                "status": result.status,
                "materialization_count": len(materializations),
                "consumers": consumers,
                "materialization_kinds": kinds,
                "typed_payload_schema_version": typed_payload_schema_version,
                "typed_review_payload_count": typed_payload_count,
                "typed_review_payload_consumers": typed_payload_consumers,
                "review_only": True,
                "plan_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 2: source_map_consumer_action_plan
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-consumer-action-plan.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map consumer action plan descriptor.",
            metadata={
                "status": result.status,
                "action_plan_count": len(action_plans),
                "consumers": consumers,
                "review_only": True,
                "plan_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    # ------------------------------------------------------------------ #
    # Branch 1: source_map_readiness
    # ------------------------------------------------------------------ #
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
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-readiness.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map readiness descriptor.",
            metadata={
                "status": result.status,
                "debugger_location_ready": bool(readiness.get("debugger_location_ready", False)),
                "source_content_metadata_ready": bool(readiness.get("source_content_metadata_ready", False)),
                "rebuild_source_metadata_ready": bool(readiness.get("rebuild_source_metadata_ready", False)),
                "source_logpoint_planning_ready": bool(readiness.get("source_logpoint_planning_ready", False)),
                "bundler_scope_review_ready": bool(readiness.get("bundler_scope_review_ready", False)),
                "sha256": source_content.get("sha256", ""),
                "review_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
            },
        )
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
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    return None
