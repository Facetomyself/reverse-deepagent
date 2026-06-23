from __future__ import annotations

from typing import Any


"""Closure scope/wrapper request predicates for NativeWebRuntime."""

def _is_closure_scope_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if _is_closure_wrapper_assignment_safety_request(protection_name, context):
        return False
    if _is_closure_wrapper_event_harvest_request(protection_name, context):
        return False
    if _is_closure_wrapper_restore_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_replacement_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_replacement_plan_request(protection_name, context):
        return False
    if normalized in {
        "closure-scope",
        "closure-scope-discovery",
        "closure-function",
        "closure-function-discovery",
        "closure-functions",
        "discover-closure-functions",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_function_names",
            "closureFunctionNames",
            "closure_query",
            "closureQuery",
            "closure_scope_discovery",
            "closureScopeDiscovery",
        )
    )


def _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    names = {
        "closure-wrapper-continuation-next-iteration-execution",
        "execute-closure-wrapper-continuation-next-iteration",
        "reviewed-closure-wrapper-continuation-next-iteration-execution",
        "wrapper-continuation-next-iteration-execution",
        "closure-function-wrapper-continuation-next-iteration-execution",
    }
    if protection_name in names:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "closure_wrapper_continuation_next_iteration_execution",
            "closureWrapperContinuationNextIterationExecution",
            "closure-wrapper-continuation-next-iteration-execution",
            "execute_closure_wrapper_continuation_next_iteration",
            "executeClosureWrapperContinuationNextIteration",
            "wrapper_continuation_next_iteration_execution",
            "wrapperContinuationNextIterationExecution",
        )
    )


def _is_closure_wrapper_continuation_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-wrapper-continuation-execution-plan",
        "closure-wrapper-continuation-execution-review",
        "plan-closure-wrapper-continuation-execution",
        "wrapper-continuation-execution-plan",
        "closure-function-wrapper-continuation-execution-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_continuation_execution_plan",
            "closureWrapperContinuationExecutionPlan",
            "closure-wrapper-continuation-execution-plan",
            "plan_closure_wrapper_continuation_execution",
            "planClosureWrapperContinuationExecution",
            "wrapper_continuation_execution_plan",
            "wrapperContinuationExecutionPlan",
        )
    )


def _is_closure_wrapper_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-wrapper-continuation-execution",
        "execute-closure-wrapper-continuation",
        "reviewed-closure-wrapper-continuation-execution",
        "wrapper-continuation-execution",
        "closure-function-wrapper-continuation-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_continuation_execution",
            "closureWrapperContinuationExecution",
            "closure-wrapper-continuation-execution",
            "execute_closure_wrapper_continuation",
            "executeClosureWrapperContinuation",
            "wrapper_continuation_execution",
            "wrapperContinuationExecution",
        )
    )


def _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-wrapper-continuation-next-iteration-plan",
        "plan-closure-wrapper-continuation-next-iteration",
        "review-closure-wrapper-continuation-next-iteration",
        "wrapper-continuation-next-iteration-plan",
        "closure-function-wrapper-continuation-next-iteration-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_continuation_next_iteration_plan",
            "closureWrapperContinuationNextIterationPlan",
            "closure-wrapper-continuation-next-iteration-plan",
            "plan_closure_wrapper_continuation_next_iteration",
            "planClosureWrapperContinuationNextIteration",
            "wrapper_continuation_next_iteration_plan",
            "wrapperContinuationNextIterationPlan",
        )
    )


def _is_closure_wrapper_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-wrapper-continuation-checkpoint",
        "checkpoint-closure-wrapper-continuation",
        "review-closure-wrapper-continuation-checkpoint",
        "wrapper-continuation-checkpoint",
        "closure-function-wrapper-continuation-checkpoint",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_continuation_checkpoint",
            "closureWrapperContinuationCheckpoint",
            "closure-wrapper-continuation-checkpoint",
            "checkpoint_closure_wrapper_continuation",
            "checkpointClosureWrapperContinuation",
            "wrapper_continuation_checkpoint",
            "wrapperContinuationCheckpoint",
        )
    )


def _is_closure_wrapper_continuation_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-wrapper-continuation-readiness",
        "closure-wrapper-continuation-review",
        "review-closure-wrapper-continuation",
        "wrapper-continuation-readiness",
        "closure-function-wrapper-continuation-readiness",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_continuation_readiness",
            "closureWrapperContinuationReadiness",
            "closure-wrapper-continuation-readiness",
            "review_closure_wrapper_continuation",
            "reviewClosureWrapperContinuation",
            "wrapper_continuation_readiness",
            "wrapperContinuationReadiness",
        )
    )


def _is_closure_wrapper_replacement_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if _is_closure_wrapper_assignment_safety_request(protection_name, context):
        return False
    if _is_closure_wrapper_event_harvest_request(protection_name, context):
        return False
    if _is_closure_wrapper_restore_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_replacement_execution_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-replacement-plan",
        "closure-wrapper-preflight",
        "closure-function-wrapper-plan",
        "plan-closure-wrapper-replacement",
        "review-closure-wrapper-replacement",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_replacement_plan",
            "closureWrapperReplacementPlan",
            "closure_wrapper_preflight",
            "closureWrapperPreflight",
            "closure_function_candidates",
            "closureFunctionCandidates",
        )
    )


def _is_closure_wrapper_replacement_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if _is_closure_wrapper_assignment_safety_request(protection_name, context):
        return False
    if _is_closure_wrapper_event_harvest_request(protection_name, context):
        return False
    if _is_closure_wrapper_restore_execution_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-replacement-execution",
        "execute-closure-wrapper-replacement",
        "reviewed-closure-wrapper-replacement",
        "closure-function-wrapper-execution",
        "install-closure-wrapper",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_replacement_execution",
            "closureWrapperReplacementExecution",
            "execute_closure_wrapper_replacement",
            "executeClosureWrapperReplacement",
            "reviewed_closure_wrapper_replacement",
            "reviewedClosureWrapperReplacement",
        )
    )


def _is_closure_wrapper_restore_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if _is_closure_wrapper_assignment_safety_request(protection_name, context):
        return False
    if _is_closure_wrapper_event_harvest_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-restore-execution",
        "execute-closure-wrapper-restore",
        "reviewed-closure-wrapper-restore",
        "closure-function-wrapper-restore",
        "restore-closure-wrapper",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_restore_execution",
            "closureWrapperRestoreExecution",
            "execute_closure_wrapper_restore",
            "executeClosureWrapperRestore",
            "reviewed_closure_wrapper_restore",
            "reviewedClosureWrapperRestore",
        )
    )


def _is_closure_wrapper_event_harvest_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if _is_closure_wrapper_assignment_safety_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-events",
        "closure-wrapper-event-harvest",
        "harvest-closure-wrapper-events",
        "closure-function-wrapper-events",
        "inspect-closure-wrapper-events",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_events",
            "closureWrapperEvents",
            "closure_wrapper_event_harvest",
            "closureWrapperEventHarvest",
            "harvest_closure_wrapper_events",
            "harvestClosureWrapperEvents",
        )
    )


def _is_closure_wrapper_assignment_safety_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-assignment-safety",
        "closure-wrapper-assignment-safety-proof",
        "prove-closure-wrapper-assignment-safety",
        "review-closure-wrapper-assignment-safety",
        "closure-function-wrapper-assignment-safety",
    }:
        return True
    return any(
        key in context
        for key in (
            "prove_closure_wrapper_assignment_safety",
            "proveClosureWrapperAssignmentSafety",
            "closure_wrapper_assignment_safety_proof_request",
            "closureWrapperAssignmentSafetyProofRequest",
        )
    )


def _is_closure_wrapper_runtime_mutability_result_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "closure-scope",
        "closure-scope-discovery",
        "closure-function",
        "closure-function-discovery",
        "closure-functions",
        "discover-closure-functions",
        "closure-wrapper-replacement-plan",
        "closure-wrapper-preflight",
        "closure-function-wrapper-plan",
        "plan-closure-wrapper-replacement",
        "review-closure-wrapper-replacement",
        "closure-wrapper-assignment-safety",
        "closure-wrapper-assignment-safety-proof",
        "prove-closure-wrapper-assignment-safety",
        "review-closure-wrapper-assignment-safety",
        "closure-function-wrapper-assignment-safety",
        "closure-wrapper-runtime-mutability-preflight",
        "closure-wrapper-mutability-preflight",
        "preflight-closure-wrapper-runtime-mutability",
        "review-closure-wrapper-runtime-mutability",
        "closure-function-wrapper-runtime-mutability-preflight",
        "closure-wrapper-replacement-execution",
        "execute-closure-wrapper-replacement",
        "reviewed-closure-wrapper-replacement",
        "closure-function-wrapper-execution",
        "install-closure-wrapper",
        "closure-wrapper-restore-execution",
        "execute-closure-wrapper-restore",
        "reviewed-closure-wrapper-restore",
        "closure-function-wrapper-restore",
        "restore-closure-wrapper",
        "closure-wrapper-events",
        "closure-wrapper-event-harvest",
        "harvest-closure-wrapper-events",
        "closure-function-wrapper-events",
        "inspect-closure-wrapper-events",
    }:
        return False
    if normalized in {
        "closure-wrapper-runtime-mutability-result",
        "closure-wrapper-runtime-mutability-probe-result",
        "execute-closure-wrapper-runtime-mutability-probe",
        "reviewed-closure-wrapper-runtime-mutability-probe",
        "closure-function-wrapper-runtime-mutability-result",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_runtime_mutability_result",
            "closureWrapperRuntimeMutabilityResult",
            "execute_closure_wrapper_runtime_mutability_probe",
            "executeClosureWrapperRuntimeMutabilityProbe",
            "closure_wrapper_mutability_result",
            "closureWrapperMutabilityResult",
        )
    )


def _is_closure_wrapper_runtime_mutability_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
        return False
    if normalized in {
        "closure-wrapper-runtime-mutability-preflight",
        "closure-wrapper-mutability-preflight",
        "preflight-closure-wrapper-runtime-mutability",
        "review-closure-wrapper-runtime-mutability",
        "closure-function-wrapper-runtime-mutability-preflight",
    }:
        return True
    return any(
        key in context
        for key in (
            "closure_wrapper_runtime_mutability_preflight",
            "closureWrapperRuntimeMutabilityPreflight",
            "preflight_closure_wrapper_runtime_mutability",
            "preflightClosureWrapperRuntimeMutability",
            "closure_wrapper_mutability_preflight",
            "closureWrapperMutabilityPreflight",
        )
    )


