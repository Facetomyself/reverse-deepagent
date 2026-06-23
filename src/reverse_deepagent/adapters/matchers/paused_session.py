from __future__ import annotations

from typing import Any


"""Paused session request predicates for NativeWebRuntime."""

from .closure import _is_closure_wrapper_continuation_checkpoint_request, _is_closure_wrapper_continuation_execution_plan_request, _is_closure_wrapper_continuation_execution_request, _is_closure_wrapper_continuation_next_iteration_execution_request, _is_closure_wrapper_continuation_next_iteration_plan_request, _is_closure_wrapper_continuation_readiness_request

def _is_breakpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"breakpoint", "set-breakpoint", "debugger-breakpoint"}:
        return True
    return any(key in context for key in ("url_pattern", "script_url", "line_number", "lineNumber"))


def _is_paused_session_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if _is_paused_session_automatic_loop_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_executor_approval_plan_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_executor_preflight_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_readiness_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_continuation_workflow_request(protection_name, context):
        return False
    if _is_paused_session_pre_action_subscribe_and_action_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_next_paused_event_capture_execution_request(protection_name, context):
        return False
    if _is_paused_session_next_paused_event_capture_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_one_action_request(protection_name, context):
        return False
    if _is_paused_session_live_callframe_recovery_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_attach_probe_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_execution_plan_request(protection_name, context):
        return False
    if _is_paused_session_live_continuation_preflight_request(protection_name, context):
        return False
    if _is_paused_session_target_attach_readiness_request(protection_name, context):
        return False
    if normalized in {
        "paused-session",
        "pause-session",
        "debugger-session",
        "resume-paused-session",
        "inspect-paused-session",
        "evaluate-paused-session",
        "step-paused-session",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_action",
            "pausedSessionAction",
            "debugger_session_action",
            "debuggerSessionAction",
            "session_action",
        )
    )


def _is_paused_session_automatic_loop_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_next_iteration_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-followup-checkpoint",
        "review-paused-session-automatic-loop-followup-checkpoint",
        "paused-session-automatic-loop-execution-followup",
        "checkpoint-paused-session-automatic-loop-execution",
        "paused-session-automatic-loop-checkpoint-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_followup_checkpoint",
            "pausedSessionAutomaticLoopFollowupCheckpoint",
            "paused-session-automatic-loop-followup-checkpoint",
            "paused_session_automatic_loop_execution_followup",
            "pausedSessionAutomaticLoopExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_execution",
            "checkpointPausedSessionAutomaticLoopExecution",
        )
    )


def _is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_following_iteration_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-next-iteration-followup-checkpoint",
        "review-paused-session-automatic-loop-next-iteration-followup-checkpoint",
        "paused-session-automatic-loop-next-iteration-execution-followup",
        "checkpoint-paused-session-automatic-loop-next-iteration-execution",
        "paused-session-automatic-loop-next-iteration-checkpoint-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_next_iteration_followup_checkpoint",
            "pausedSessionAutomaticLoopNextIterationFollowupCheckpoint",
            "paused-session-automatic-loop-next-iteration-followup-checkpoint",
            "paused_session_automatic_loop_next_iteration_execution_followup",
            "pausedSessionAutomaticLoopNextIterationExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_next_iteration_execution",
            "checkpointPausedSessionAutomaticLoopNextIterationExecution",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_executor_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-executor-approval-plan",
        "plan-paused-session-automatic-loop-multi-iteration-executor-approval",
        "review-paused-session-automatic-loop-multi-iteration-executor-approval-plan",
        "paused-session-automatic-loop-bounded-multi-iteration-executor-approval-plan",
        "automatic-loop-multi-iteration-executor-approval-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_executor_approval_plan",
            "pausedSessionAutomaticLoopMultiIterationExecutorApprovalPlan",
            "paused-session-automatic-loop-multi-iteration-executor-approval-plan",
            "plan_paused_session_automatic_loop_multi_iteration_executor_approval",
            "planPausedSessionAutomaticLoopMultiIterationExecutorApproval",
            "review_paused_session_automatic_loop_multi_iteration_executor_approval_plan",
            "reviewPausedSessionAutomaticLoopMultiIterationExecutorApprovalPlan",
            "automatic_loop_multi_iteration_executor_approval_plan",
            "automaticLoopMultiIterationExecutorApprovalPlan",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-execution",
        "execute-paused-session-automatic-loop-multi-iteration",
        "execute-bounded-paused-session-automatic-loop-multi-iteration",
        "reviewed-paused-session-automatic-loop-multi-iteration-execution",
        "paused-session-automatic-loop-multi-iteration-executor",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_execution",
            "pausedSessionAutomaticLoopMultiIterationExecution",
            "paused-session-automatic-loop-multi-iteration-execution",
            "execute_paused_session_automatic_loop_multi_iteration",
            "executePausedSessionAutomaticLoopMultiIteration",
            "execute_bounded_paused_session_automatic_loop_multi_iteration",
            "executeBoundedPausedSessionAutomaticLoopMultiIteration",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-followup-checkpoint",
        "review-paused-session-automatic-loop-multi-iteration-followup-checkpoint",
        "paused-session-automatic-loop-multi-iteration-execution-followup",
        "checkpoint-paused-session-automatic-loop-multi-iteration-execution",
        "paused-session-automatic-loop-multi-iteration-checkpoint-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_followup_checkpoint",
            "pausedSessionAutomaticLoopMultiIterationFollowupCheckpoint",
            "paused-session-automatic-loop-multi-iteration-followup-checkpoint",
            "paused_session_automatic_loop_multi_iteration_execution_followup",
            "pausedSessionAutomaticLoopMultiIterationExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_multi_iteration_execution",
            "checkpointPausedSessionAutomaticLoopMultiIterationExecution",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_executor_input_preflight_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-next-step-plan",
        "review-paused-session-automatic-loop-multi-iteration-next-step-plan",
        "plan-next-paused-session-automatic-loop-multi-iteration-step",
        "review-next-paused-session-automatic-loop-multi-iteration-step",
        "paused-session-automatic-loop-multi-iteration-next-step-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_next_step_plan",
            "pausedSessionAutomaticLoopMultiIterationNextStepPlan",
            "paused-session-automatic-loop-multi-iteration-next-step-plan",
            "plan_next_paused_session_automatic_loop_multi_iteration_step",
            "planNextPausedSessionAutomaticLoopMultiIterationStep",
            "review_next_paused_session_automatic_loop_multi_iteration_step",
            "reviewNextPausedSessionAutomaticLoopMultiIterationStep",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_executor_input_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-executor-input-preflight",
        "review-paused-session-automatic-loop-multi-iteration-executor-input-preflight",
        "preflight-paused-session-automatic-loop-multi-iteration-executor-input",
        "review-next-paused-session-automatic-loop-multi-iteration-executor-input",
        "paused-session-automatic-loop-multi-iteration-executor-input-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_executor_input_preflight",
            "pausedSessionAutomaticLoopMultiIterationExecutorInputPreflight",
            "paused-session-automatic-loop-multi-iteration-executor-input-preflight",
            "preflight_paused_session_automatic_loop_multi_iteration_executor_input",
            "preflightPausedSessionAutomaticLoopMultiIterationExecutorInput",
            "review_next_paused_session_automatic_loop_multi_iteration_executor_input",
            "reviewNextPausedSessionAutomaticLoopMultiIterationExecutorInput",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_executor_input_preflight_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_multi_iteration_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_multi_iteration_executor_approval_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-execution-plan",
        "plan-paused-session-automatic-loop-multi-iteration-execution",
        "review-paused-session-automatic-loop-multi-iteration-execution-plan",
        "paused-session-automatic-loop-bounded-multi-iteration-execution-plan",
        "automatic-loop-multi-iteration-execution-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_execution_plan",
            "pausedSessionAutomaticLoopMultiIterationExecutionPlan",
            "paused-session-automatic-loop-multi-iteration-execution-plan",
            "plan_paused_session_automatic_loop_multi_iteration_execution",
            "planPausedSessionAutomaticLoopMultiIterationExecution",
            "review_paused_session_automatic_loop_multi_iteration_execution_plan",
            "reviewPausedSessionAutomaticLoopMultiIterationExecutionPlan",
            "automatic_loop_multi_iteration_execution_plan",
            "automaticLoopMultiIterationExecutionPlan",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_execution_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-executor-preflight",
        "preflight-paused-session-automatic-loop-multi-iteration-executor",
        "review-paused-session-automatic-loop-multi-iteration-executor-preflight",
        "paused-session-automatic-loop-bounded-multi-iteration-executor-preflight",
        "automatic-loop-multi-iteration-executor-preflight",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_executor_preflight",
            "pausedSessionAutomaticLoopMultiIterationExecutorPreflight",
            "paused-session-automatic-loop-multi-iteration-executor-preflight",
            "preflight_paused_session_automatic_loop_multi_iteration_executor",
            "preflightPausedSessionAutomaticLoopMultiIterationExecutor",
            "review_paused_session_automatic_loop_multi_iteration_executor_preflight",
            "reviewPausedSessionAutomaticLoopMultiIterationExecutorPreflight",
            "automatic_loop_multi_iteration_executor_preflight",
            "automaticLoopMultiIterationExecutorPreflight",
        )
    )


def _is_paused_session_automatic_loop_multi_iteration_policy_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_executor_preflight_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-multi-iteration-policy",
        "review-paused-session-automatic-loop-multi-iteration-policy",
        "plan-paused-session-automatic-loop-multi-iteration-policy",
        "review-paused-session-automatic-loop-bounded-multi-iteration-policy",
        "paused-session-automatic-loop-budget-policy",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_multi_iteration_policy",
            "pausedSessionAutomaticLoopMultiIterationPolicy",
            "paused-session-automatic-loop-multi-iteration-policy",
            "plan_paused_session_automatic_loop_multi_iteration_policy",
            "planPausedSessionAutomaticLoopMultiIterationPolicy",
            "review_paused_session_automatic_loop_multi_iteration_policy",
            "reviewPausedSessionAutomaticLoopMultiIterationPolicy",
            "automatic_loop_multi_iteration_policy",
            "automaticLoopMultiIterationPolicy",
        )
    )


def _is_paused_session_automatic_loop_following_iteration_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_multi_iteration_policy_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-following-iteration-plan",
        "review-paused-session-automatic-loop-following-iteration-plan",
        "plan-following-paused-session-automatic-loop-iteration",
        "review-following-paused-session-automatic-loop-iteration",
        "paused-session-automatic-loop-following-iteration-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_following_iteration_plan",
            "pausedSessionAutomaticLoopFollowingIterationPlan",
            "paused-session-automatic-loop-following-iteration-plan",
            "plan_following_paused_session_automatic_loop_iteration",
            "planFollowingPausedSessionAutomaticLoopIteration",
            "review_following_paused_session_automatic_loop_iteration",
            "reviewFollowingPausedSessionAutomaticLoopIteration",
        )
    )


def _is_paused_session_automatic_loop_next_iteration_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-next-iteration-execution",
        "execute-paused-session-automatic-loop-next-iteration",
        "execute-next-paused-session-automatic-loop-iteration",
        "reviewed-paused-session-automatic-loop-next-iteration-execution",
        "paused-session-automatic-loop-next-iteration-executor",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_next_iteration_execution",
            "pausedSessionAutomaticLoopNextIterationExecution",
            "paused-session-automatic-loop-next-iteration-execution",
            "execute_paused_session_automatic_loop_next_iteration",
            "executePausedSessionAutomaticLoopNextIteration",
            "execute_next_paused_session_automatic_loop_iteration",
            "executeNextPausedSessionAutomaticLoopIteration",
        )
    )


def _is_paused_session_automatic_loop_next_iteration_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_following_iteration_plan_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-next-iteration-plan",
        "review-paused-session-automatic-loop-next-iteration-plan",
        "plan-next-paused-session-automatic-loop-iteration",
        "review-next-paused-session-automatic-loop-iteration",
        "paused-session-automatic-loop-next-iteration-review",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_next_iteration_plan",
            "pausedSessionAutomaticLoopNextIterationPlan",
            "paused-session-automatic-loop-next-iteration-plan",
            "plan_next_paused_session_automatic_loop_iteration",
            "planNextPausedSessionAutomaticLoopIteration",
            "review_next_paused_session_automatic_loop_iteration",
            "reviewNextPausedSessionAutomaticLoopIteration",
        )
    )


def _is_paused_session_automatic_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_next_iteration_plan_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_followup_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-execution",
        "execute-paused-session-automatic-loop",
        "execute-bounded-paused-session-automatic-loop",
        "paused-session-bounded-automatic-loop-execution",
        "reviewed-paused-session-automatic-loop-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_execution",
            "pausedSessionAutomaticLoopExecution",
            "paused-session-automatic-loop-execution",
            "execute_paused_session_automatic_loop",
            "executePausedSessionAutomaticLoop",
            "execute_bounded_paused_session_automatic_loop",
            "executeBoundedPausedSessionAutomaticLoop",
        )
    )


def _is_paused_session_automatic_loop_executor_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-executor-approval-plan",
        "plan-paused-session-automatic-loop-executor-approval",
        "review-paused-session-automatic-loop-executor-approval-plan",
        "automatic-paused-session-loop-executor-approval-plan",
        "paused-session-bounded-automatic-loop-executor-approval-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_executor_approval_plan",
            "pausedSessionAutomaticLoopExecutorApprovalPlan",
            "paused-session-automatic-loop-executor-approval-plan",
            "plan_paused_session_automatic_loop_executor_approval",
            "planPausedSessionAutomaticLoopExecutorApproval",
            "automatic_loop_executor_approval_plan",
            "automaticLoopExecutorApprovalPlan",
        )
    )


def _is_paused_session_automatic_loop_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_executor_approval_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-executor-preflight",
        "preflight-paused-session-automatic-loop-executor",
        "review-paused-session-automatic-loop-executor-preflight",
        "automatic-paused-session-loop-executor-preflight",
        "paused-session-bounded-automatic-loop-executor-preflight",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_executor_preflight",
            "pausedSessionAutomaticLoopExecutorPreflight",
            "paused-session-automatic-loop-executor-preflight",
            "preflight_paused_session_automatic_loop_executor",
            "preflightPausedSessionAutomaticLoopExecutor",
            "automatic_loop_executor_preflight",
            "automaticLoopExecutorPreflight",
        )
    )


def _is_paused_session_automatic_loop_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_executor_preflight_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-execution-plan",
        "plan-paused-session-automatic-loop-execution",
        "paused-session-bounded-automatic-loop-execution-plan",
        "review-paused-session-automatic-loop-execution-plan",
        "automatic-paused-session-loop-execution-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_execution_plan",
            "pausedSessionAutomaticLoopExecutionPlan",
            "paused-session-automatic-loop-execution-plan",
            "plan_paused_session_automatic_loop_execution",
            "planPausedSessionAutomaticLoopExecution",
            "automatic_loop_execution_plan",
            "automaticLoopExecutionPlan",
        )
    )


def _is_paused_session_automatic_loop_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-automatic-loop-readiness",
        "paused-session-multi-step-automatic-loop-readiness",
        "review-paused-session-automatic-loop-readiness",
        "paused-session-automatic-continuation-loop-readiness",
        "automatic-paused-session-loop-readiness",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_automatic_loop_readiness",
            "pausedSessionAutomaticLoopReadiness",
            "paused-session-automatic-loop-readiness",
            "paused_session_multi_step_automatic_loop_readiness",
            "pausedSessionMultiStepAutomaticLoopReadiness",
            "review_paused_session_automatic_loop_readiness",
            "reviewPausedSessionAutomaticLoopReadiness",
        )
    )


def _is_paused_session_multi_step_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_readiness_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-multi-step-loop-execution",
        "pause-session-multi-step-loop-execution",
        "debugger-paused-session-multi-step-loop-execution",
        "execute-paused-session-loop-iteration",
        "execute-paused-session-continuation-loop",
        "execute-paused-session-continuation-loop-iteration",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_multi_step_loop_execution",
            "pausedSessionMultiStepLoopExecution",
            "paused-session-multi-step-loop-execution",
            "execute_paused_session_loop_iteration",
            "executePausedSessionLoopIteration",
            "execute_paused_session_continuation_loop",
            "executePausedSessionContinuationLoop",
        )
    )


def _is_paused_session_multi_step_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_execution_request(protection_name, context):
        return False
    if _is_paused_session_automatic_loop_readiness_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-multi-step-loop-plan",
        "pause-session-multi-step-loop-plan",
        "debugger-paused-session-multi-step-loop-plan",
        "paused-session-continuation-loop-plan",
        "multi-step-continuation-loop-plan",
        "plan-paused-session-continuation-loop",
        "review-paused-session-continuation-loop",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "paused_session_continuation_loop_plan",
            "pausedSessionContinuationLoopPlan",
            "multi_step_continuation_loop_plan",
            "multiStepContinuationLoopPlan",
            "plan_paused_session_continuation_loop",
            "planPausedSessionContinuationLoop",
        )
    )


def _is_paused_session_cross_process_session_lifecycle_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-cross-process-session-lifecycle",
        "pause-session-cross-process-session-lifecycle",
        "debugger-paused-session-cross-process-session-lifecycle",
        "cross-process-paused-session-lifecycle",
        "cross-process-session-lifecycle",
        "paused-session-lifecycle",
        "review-paused-session-lifecycle",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_cross_process_session_lifecycle",
            "pausedSessionCrossProcessSessionLifecycle",
            "paused-session-cross-process-session-lifecycle",
            "cross_process_session_lifecycle",
            "crossProcessSessionLifecycle",
            "review_paused_session_lifecycle",
            "reviewPausedSessionLifecycle",
            "paused_session_lifecycle",
            "pausedSessionLifecycle",
        )
    )


def _is_paused_session_multi_step_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-multi-step-continuation-execution",
        "pause-session-multi-step-continuation-execution",
        "debugger-paused-session-multi-step-continuation-execution",
        "execute-paused-session-continuation-iteration",
        "cross-process-multi-step-continuation-execution",
        "execute-multi-step-continuation-iteration",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_multi_step_continuation_execution",
            "pausedSessionMultiStepContinuationExecution",
            "paused-session-multi-step-continuation-execution",
            "execute_paused_session_continuation_iteration",
            "executePausedSessionContinuationIteration",
            "cross_process_multi_step_continuation_execution",
            "crossProcessMultiStepContinuationExecution",
        )
    )


def _is_paused_session_multi_step_continuation_workflow_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_continuation_execution_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-multi-step-continuation-workflow",
        "pause-session-multi-step-continuation-workflow",
        "debugger-paused-session-multi-step-continuation-workflow",
        "multi-step-paused-session-continuation",
        "cross-process-multi-step-continuation",
        "paused-session-continuation-workflow",
        "plan-paused-session-continuation-workflow",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_multi_step_continuation_workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "paused-session-multi-step-continuation-workflow",
            "multi_step_paused_session_continuation",
            "multiStepPausedSessionContinuation",
            "paused_session_continuation_workflow",
            "pausedSessionContinuationWorkflow",
            "cross_process_multi_step_continuation",
            "crossProcessMultiStepContinuation",
        )
    )


def _is_paused_session_pre_action_subscribe_and_action_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-pre-action-subscribe-and-action",
        "pause-session-pre-action-subscribe-and-action",
        "debugger-paused-session-pre-action-subscribe-and-action",
        "cross-process-pre-action-subscribe-and-action",
        "pre-action-subscribe-and-action",
        "subscribe-and-action-orchestration",
        "pre-subscribe-cross-process-one-action",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_pre_action_subscribe_and_action",
            "pausedSessionPreActionSubscribeAndAction",
            "paused-session-pre-action-subscribe-and-action",
            "pre_action_subscribe_and_action",
            "preActionSubscribeAndAction",
            "subscribe_and_action_orchestration",
            "subscribeAndActionOrchestration",
            "pre_subscribe_cross_process_one_action",
            "preSubscribeCrossProcessOneAction",
        )
    )


def _is_paused_session_cross_process_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-cross-process-continuation-checkpoint",
        "pause-session-cross-process-continuation-checkpoint",
        "debugger-paused-session-cross-process-continuation-checkpoint",
        "cross-process-continuation-checkpoint",
        "paused-session-continuation-checkpoint",
        "review-cross-process-continuation-checkpoint",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_cross_process_continuation_checkpoint",
            "pausedSessionCrossProcessContinuationCheckpoint",
            "paused-session-cross-process-continuation-checkpoint",
            "cross_process_continuation_checkpoint",
            "crossProcessContinuationCheckpoint",
            "paused_session_continuation_checkpoint",
            "pausedSessionContinuationCheckpoint",
        )
    )


def _is_paused_session_next_paused_event_capture_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-next-paused-event-capture-execution",
        "pause-session-next-paused-event-capture-execution",
        "debugger-paused-session-next-paused-event-capture-execution",
        "cross-process-next-paused-event-capture-execution",
        "next-paused-event-capture-execution",
        "execute-next-paused-event-capture",
        "reviewed-next-paused-event-capture-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_next_paused_event_capture_execution",
            "pausedSessionNextPausedEventCaptureExecution",
            "paused-session-next-paused-event-capture-execution",
            "next_paused_event_capture_execution",
            "nextPausedEventCaptureExecution",
            "execute_next_paused_event_capture",
            "executeNextPausedEventCapture",
        )
    )


def _is_paused_session_next_paused_event_capture_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if _is_paused_session_cross_process_continuation_checkpoint_request(protection_name, context):
        return False
    if _is_paused_session_next_paused_event_capture_execution_request(protection_name, context):
        return False
    if normalized in {
        "paused-session-next-paused-event-capture-plan",
        "pause-session-next-paused-event-capture-plan",
        "debugger-paused-session-next-paused-event-capture-plan",
        "cross-process-next-paused-event-capture-plan",
        "next-paused-event-capture-plan",
        "plan-next-paused-event-capture",
        "review-next-paused-event-capture-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_next_paused_event_capture_plan",
            "pausedSessionNextPausedEventCapturePlan",
            "paused-session-next-paused-event-capture-plan",
            "next_paused_event_capture_plan",
            "nextPausedEventCapturePlan",
            "plan_next_paused_event_capture",
            "planNextPausedEventCapture",
        )
    )


def _is_paused_session_cross_process_one_action_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-cross-process-one-action",
        "pause-session-cross-process-one-action",
        "debugger-paused-session-cross-process-one-action",
        "cross-process-paused-session-one-action",
        "cross-process-one-action",
        "execute-cross-process-one-action",
        "execute-cross-process-paused-session-action",
        "reviewed-cross-process-one-action",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_cross_process_one_action",
            "pausedSessionCrossProcessOneAction",
            "paused-session-cross-process-one-action",
            "cross_process_one_action",
            "crossProcessOneAction",
            "execute_cross_process_one_action",
            "executeCrossProcessOneAction",
            "cross_process_paused_session_action",
            "crossProcessPausedSessionAction",
        )
    )


def _is_paused_session_live_callframe_recovery_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_readiness_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-live-callframe-recovery",
        "pause-session-live-callframe-recovery",
        "debugger-paused-session-live-callframe-recovery",
        "cross-process-live-callframe-recovery",
        "recover-live-callframe-after-attach",
        "review-live-callframe-recovery",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "cross_process_live_callframe_recovery",
            "crossProcessLiveCallframeRecovery",
            "recover_live_callframe_after_attach",
            "recoverLiveCallframeAfterAttach",
        )
    )


def _is_paused_session_cross_process_attach_probe_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-cross-process-attach-probe",
        "pause-session-cross-process-attach-probe",
        "debugger-paused-session-cross-process-attach-probe",
        "cross-process-paused-session-attach-probe",
        "probe-cross-process-paused-session-attach",
        "execute-cross-process-attach-probe",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_paused_session_attach_probe",
            "crossProcessPausedSessionAttachProbe",
            "execute_cross_process_attach_probe",
            "executeCrossProcessAttachProbe",
        )
    )


def _is_paused_session_cross_process_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-cross-process-execution-plan",
        "pause-session-cross-process-execution-plan",
        "debugger-paused-session-cross-process-execution-plan",
        "cross-process-paused-session-execution-plan",
        "plan-cross-process-paused-session-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_cross_process_execution_plan",
            "pausedSessionCrossProcessExecutionPlan",
            "paused-session-cross-process-execution-plan",
            "cross_process_paused_session_execution_plan",
            "crossProcessPausedSessionExecutionPlan",
            "plan_cross_process_paused_session_execution",
            "planCrossProcessPausedSessionExecution",
        )
    )


def _is_paused_session_live_continuation_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-live-continuation-preflight",
        "pause-session-live-continuation-preflight",
        "debugger-paused-session-live-preflight",
        "cross-process-paused-session-live-preflight",
        "preflight-paused-session-live-continuation",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_live_continuation_preflight",
            "pausedSessionLiveContinuationPreflight",
            "paused-session-live-continuation-preflight",
            "cross_process_paused_session_live_preflight",
            "crossProcessPausedSessionLivePreflight",
            "preflight_paused_session_live_continuation",
            "preflightPausedSessionLiveContinuation",
        )
    )


def _is_paused_session_target_attach_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
        return False
    if _is_closure_wrapper_continuation_execution_request(protection_name, context):
        return False
    if _is_paused_session_multi_step_loop_plan_request(protection_name, context):
        return False
    if _is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "paused-session-target-attach-readiness",
        "pause-session-target-attach-readiness",
        "debugger-paused-session-target-attach-readiness",
        "cross-process-paused-session-target-attach-readiness",
        "cross-process-target-attach-readiness",
    }:
        return True
    return any(
        key in context
        for key in (
            "paused_session_target_attach_readiness",
            "pausedSessionTargetAttachReadiness",
            "paused-session-target-attach-readiness",
            "cross_process_target_attach_readiness",
            "crossProcessTargetAttachReadiness",
            "cross_process_paused_session_target_attach_readiness",
            "crossProcessPausedSessionTargetAttachReadiness",
        )
    )


