from __future__ import annotations

from typing import Any


class _NativeWebRequestMatchers:
    """Mixin: route-classification predicates for NativeWebRuntime.

    All methods are pure @staticmethod predicates that inspect only
    ``protection_name`` and ``context``. Extracted from NativeWebRuntime
    (B2 refactor) to keep the main class focused on business logic.
    """

    @staticmethod
    def _is_breakpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"breakpoint", "set-breakpoint", "debugger-breakpoint"}:
            return True
        return any(key in context for key in ("url_pattern", "script_url", "line_number", "lineNumber"))
    @staticmethod
    def _is_paused_session_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_executor_approval_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_executor_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_continuation_workflow_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_pre_action_subscribe_and_action_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_next_paused_event_capture_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_next_paused_event_capture_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_one_action_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_live_callframe_recovery_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_attach_probe_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_live_continuation_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_target_attach_readiness_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_following_iteration_plan_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_executor_input_preflight_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_executor_input_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_next_step_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_followup_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_executor_approval_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_execution_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_multi_iteration_policy_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_executor_preflight_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_following_iteration_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_multi_iteration_policy_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_paused_session_automatic_loop_next_iteration_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_following_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_followup_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_next_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_followup_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_paused_session_automatic_loop_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_executor_approval_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_executor_preflight_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_automatic_loop_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_execution_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_multi_step_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_readiness_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_multi_step_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_automatic_loop_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_cross_process_session_lifecycle_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_multi_step_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_multi_step_continuation_workflow_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_continuation_execution_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_pre_action_subscribe_and_action_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_cross_process_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_next_paused_event_capture_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_next_paused_event_capture_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_paused_session_cross_process_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_next_paused_event_capture_execution_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_cross_process_one_action_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_live_callframe_recovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_cross_process_attach_probe_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_cross_process_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_live_continuation_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_paused_session_target_attach_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_multi_step_loop_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_paused_session_cross_process_session_lifecycle_request(protection_name, context):
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
    @staticmethod
    def _is_heap_snapshot_automatic_followup_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        proof_plan_names = {
            "heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-retained-size-proof-planner",
            "plan-heap-snapshot-retained-size-proof",
            "review-heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }
        proof_plan_keys = (
            "heap_snapshot_retained_size_proof_plan",
            "heapSnapshotRetainedSizeProofPlan",
            "heap_snapshot_retained_size_proof_planner",
            "heapSnapshotRetainedSizeProofPlanner",
            "plan_heap_snapshot_retained_size_proof",
            "planHeapSnapshotRetainedSizeProof",
            "review_heap_snapshot_retained_size_proof_plan",
            "reviewHeapSnapshotRetainedSizeProofPlan",
            "heap_snapshot_path_to_root_proof_plan",
            "heapSnapshotPathToRootProofPlan",
            "heap_snapshot_path_to_root_proof_planner",
            "heapSnapshotPathToRootProofPlanner",
            "plan_heap_snapshot_path_to_root_proof",
            "planHeapSnapshotPathToRootProof",
            "review_heap_snapshot_path_to_root_proof_plan",
            "reviewHeapSnapshotPathToRootProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "heapSnapshotRawHeapConstructorDrilldownProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
            "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
            "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
            "planHeapSnapshotRawHeapConstructorDrilldownProof",
            "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
        )
        if normalized in proof_plan_names or any(key in context for key in proof_plan_keys):
            return False
        if normalized in {
            "heap-snapshot-automatic-followup-plan",
            "heap-snapshot-automatic-followup-planner",
            "heap-snapshot-followup-plan",
            "plan-heap-snapshot-automatic-followup",
            "review-heap-snapshot-automatic-followup-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_automatic_followup_plan",
                "heapSnapshotAutomaticFollowupPlan",
                "heap_snapshot_automatic_followup_planner",
                "heapSnapshotAutomaticFollowupPlanner",
                "heap_snapshot_followup_plan",
                "heapSnapshotFollowupPlan",
                "plan_heap_snapshot_automatic_followup",
                "planHeapSnapshotAutomaticFollowup",
                "review_heap_snapshot_automatic_followup_plan",
                "reviewHeapSnapshotAutomaticFollowupPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        path_proof_names = {
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }
        path_proof_keys = (
            "heap_snapshot_path_to_root_proof_plan",
            "heapSnapshotPathToRootProofPlan",
            "heap_snapshot_path_to_root_proof_planner",
            "heapSnapshotPathToRootProofPlanner",
            "plan_heap_snapshot_path_to_root_proof",
            "planHeapSnapshotPathToRootProof",
            "review_heap_snapshot_path_to_root_proof_plan",
            "reviewHeapSnapshotPathToRootProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "heapSnapshotRawHeapConstructorDrilldownProofPlan",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
            "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
            "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
            "planHeapSnapshotRawHeapConstructorDrilldownProof",
            "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
        )
        if normalized in path_proof_names or any(key in context for key in path_proof_keys):
            return False
        if normalized in {
            "heap-snapshot-retained-size-proof-plan",
            "heap-snapshot-retained-size-proof-planner",
            "plan-heap-snapshot-retained-size-proof",
            "review-heap-snapshot-retained-size-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_proof_plan",
                "heapSnapshotRetainedSizeProofPlan",
                "heap_snapshot_retained_size_proof_planner",
                "heapSnapshotRetainedSizeProofPlanner",
                "plan_heap_snapshot_retained_size_proof",
                "planHeapSnapshotRetainedSizeProof",
                "review_heap_snapshot_retained_size_proof_plan",
                "reviewHeapSnapshotRetainedSizeProofPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_path_to_root_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-path-to-root-proof-plan",
            "heap-snapshot-path-to-root-proof-planner",
            "plan-heap-snapshot-path-to-root-proof",
            "review-heap-snapshot-path-to-root-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_path_to_root_proof_plan",
                "heapSnapshotPathToRootProofPlan",
                "heap_snapshot_path_to_root_proof_planner",
                "heapSnapshotPathToRootProofPlanner",
                "plan_heap_snapshot_path_to_root_proof",
                "planHeapSnapshotPathToRootProof",
                "review_heap_snapshot_path_to_root_proof_plan",
                "reviewHeapSnapshotPathToRootProofPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            "heap-snapshot-raw-heap-constructor-drilldown-proof-planner",
            "plan-heap-snapshot-raw-heap-constructor-drilldown-proof",
            "review-heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "heapSnapshotRawHeapConstructorDrilldownProofPlan",
                "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
                "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
                "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
                "planHeapSnapshotRawHeapConstructorDrilldownProof",
                "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_path_to_root_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-path-to-root-analysis",
            "heap-snapshot-path-to-root-analysis",
            "heap-snapshot-path-to-root-executor-result",
            "heap-snapshot-path-to-root-executor-mvp",
            "path-to-root-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_path_to_root_analysis",
                "executeHeapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_analysis",
                "heapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_executor_result",
                "heapSnapshotPathToRootExecutorResult",
                "heap_snapshot_path_to_root_executor_mvp",
                "heapSnapshotPathToRootExecutorMvp",
                "path_to_root_heap_snapshot_executor",
                "pathToRootHeapSnapshotExecutor",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-retained-size-analysis",
            "heap-snapshot-retained-size-analysis",
            "heap-snapshot-retained-size-executor-result",
            "heap-snapshot-retained-size-executor-mvp",
            "retained-size-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_retained_size_analysis",
                "executeHeapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_analysis",
                "heapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_executor_result",
                "heapSnapshotRetainedSizeExecutorResult",
                "heap_snapshot_retained_size_executor_mvp",
                "heapSnapshotRetainedSizeExecutorMvp",
                "retained_size_heap_snapshot_executor",
                "retainedSizeHeapSnapshotExecutor",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_transaction_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-approval-plan",
            "heap-snapshot-retained-size-executor-approval-plan",
            "heap-snapshot-retained-size-transaction-plan",
            "review-heap-snapshot-retained-size-approval-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_approval_plan",
                "heapSnapshotRetainedSizeApprovalPlan",
                "heap_snapshot_retained_size_executor_approval_plan",
                "heapSnapshotRetainedSizeExecutorApprovalPlan",
                "heap_snapshot_retained_size_transaction_plan",
                "heapSnapshotRetainedSizeTransactionPlan",
                "review_heap_snapshot_retained_size_approval_plan",
                "reviewHeapSnapshotRetainedSizeApprovalPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_bounded_gate_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-bounded-gate",
            "heap-snapshot-retained-size-bounded-executor-gate",
            "heap-snapshot-retained-size-executor-bounded-gate",
            "review-heap-snapshot-retained-size-bounded-gate",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_bounded_gate",
                "heapSnapshotRetainedSizeBoundedGate",
                "heap_snapshot_retained_size_bounded_executor_gate",
                "heapSnapshotRetainedSizeBoundedExecutorGate",
                "heap_snapshot_retained_size_executor_bounded_gate",
                "heapSnapshotRetainedSizeExecutorBoundedGate",
                "review_heap_snapshot_retained_size_bounded_gate",
                "reviewHeapSnapshotRetainedSizeBoundedGate",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_transaction_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_bounded_gate_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-transaction-preflight",
            "heap-snapshot-retained-size-executor-transaction-preflight",
            "review-heap-snapshot-retained-size-transaction-preflight",
            "preflight-heap-snapshot-retained-size-transaction",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_transaction_preflight",
                "heapSnapshotRetainedSizeTransactionPreflight",
                "heap_snapshot_retained_size_executor_transaction_preflight",
                "heapSnapshotRetainedSizeExecutorTransactionPreflight",
                "review_heap_snapshot_retained_size_transaction_preflight",
                "reviewHeapSnapshotRetainedSizeTransactionPreflight",
                "preflight_heap_snapshot_retained_size_transaction",
                "preflightHeapSnapshotRetainedSizeTransaction",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_size_input_review_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_approval_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-size-input-review",
            "heap-snapshot-retained-size-executor-input-review",
            "heap-snapshot-retained-size-approval-gate",
            "review-heap-snapshot-retained-size-input",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_size_input_review",
                "heapSnapshotRetainedSizeInputReview",
                "heap_snapshot_retained_size_executor_input_review",
                "heapSnapshotRetainedSizeExecutorInputReview",
                "heap_snapshot_retained_size_approval_gate",
                "heapSnapshotRetainedSizeApprovalGate",
                "review_heap_snapshot_retained_size_input",
                "reviewHeapSnapshotRetainedSizeInput",
            )
        )
    @staticmethod
    def _is_heap_snapshot_retained_path_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_input_review_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-retained-path-preflight",
            "heap-snapshot-constructor-growth-retained-path-preflight",
            "heap-snapshot-retained-size-path-to-root-preflight",
            "review-heap-snapshot-retained-path-preflight",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_retained_path_preflight",
                "heapSnapshotRetainedPathPreflight",
                "heap_snapshot_constructor_growth_retained_path_preflight",
                "heapSnapshotConstructorGrowthRetainedPathPreflight",
                "heap_snapshot_retained_size_path_to_root_preflight",
                "heapSnapshotRetainedSizePathToRootPreflight",
                "review_heap_snapshot_retained_path_preflight",
                "reviewHeapSnapshotRetainedPathPreflight",
            )
        )
    @staticmethod
    def _is_heap_snapshot_constructor_growth_drilldown_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_automatic_followup_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_size_proof_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_path_to_root_proof_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-constructor-growth-drilldown",
            "execute-heap-snapshot-constructor-growth-drilldown-analysis",
            "heap-snapshot-constructor-growth-drilldown-analysis",
            "heap-snapshot-constructor-growth-drilldown-executor-result",
            "heap-snapshot-constructor-growth-drilldown-executor-mvp",
            "constructor-growth-heap-snapshot-executor",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_constructor_growth_drilldown",
                "executeHeapSnapshotConstructorGrowthDrilldown",
                "execute_heap_snapshot_constructor_growth_drilldown_analysis",
                "executeHeapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_analysis",
                "heapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_executor_result",
                "heapSnapshotConstructorGrowthDrilldownExecutorResult",
                "heap_snapshot_constructor_growth_drilldown_executor_mvp",
                "heapSnapshotConstructorGrowthDrilldownExecutorMvp",
                "constructor_growth_heap_snapshot_executor",
                "constructorGrowthHeapSnapshotExecutor",
            )
        )
    @staticmethod
    def _is_heap_snapshot_constructor_growth_drilldown_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_constructor_growth_drilldown_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_retained_path_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-constructor-growth-drilldown",
            "heap-snapshot-diff-constructor-growth-drilldown",
            "review-heap-snapshot-constructor-growth-drilldown",
            "review-heap-snapshot-diff-constructor-growth",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_constructor_growth_drilldown",
                "heapSnapshotConstructorGrowthDrilldown",
                "heap_snapshot_diff_constructor_growth_drilldown",
                "heapSnapshotDiffConstructorGrowthDrilldown",
                "review_heap_snapshot_constructor_growth_drilldown",
                "reviewHeapSnapshotConstructorGrowthDrilldown",
                "review_heap_snapshot_diff_constructor_growth",
                "reviewHeapSnapshotDiffConstructorGrowth",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_selected_analysis_input_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_constructor_growth_drilldown_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-selected-analysis-input-preflight",
            "heap-snapshot-diff-followup-selected-analysis-preflight",
            "heap-snapshot-diff-selected-followup-preflight",
            "review-heap-snapshot-diff-selected-analysis-input",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_selected_analysis_input_preflight",
                "heapSnapshotDiffSelectedAnalysisInputPreflight",
                "heap_snapshot_diff_followup_selected_analysis_preflight",
                "heapSnapshotDiffFollowupSelectedAnalysisPreflight",
                "heap_snapshot_diff_selected_followup_preflight",
                "heapSnapshotDiffSelectedFollowupPreflight",
                "review_heap_snapshot_diff_selected_analysis_input",
                "reviewHeapSnapshotDiffSelectedAnalysisInput",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_followup_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_selected_analysis_input_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-followup-checkpoint",
            "heap-snapshot-diff-analysis-plan",
            "review-heap-snapshot-diff-followup-checkpoint",
            "review-heap-snapshot-diff-executor-result-followup",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_followup_checkpoint",
                "heapSnapshotDiffFollowupCheckpoint",
                "heap_snapshot_diff_analysis_plan",
                "heapSnapshotDiffAnalysisPlan",
                "review_heap_snapshot_diff_followup_checkpoint",
                "reviewHeapSnapshotDiffFollowupCheckpoint",
                "review_heap_snapshot_diff_executor_result_followup",
                "reviewHeapSnapshotDiffExecutorResultFollowup",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_executor_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_followup_checkpoint_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "execute-heap-snapshot-diff-executor",
            "heap-snapshot-diff-executor-result",
            "heap-snapshot-diff-executor-mvp",
            "raw-heap-diff-executor",
            "review-heap-snapshot-diff-executor-raw-heap-parser-or-executor-mvp",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_heap_snapshot_diff_executor",
                "executeHeapSnapshotDiffExecutor",
                "heap_snapshot_diff_executor_result",
                "heapSnapshotDiffExecutorResult",
                "heap_snapshot_diff_executor_mvp",
                "heapSnapshotDiffExecutorMvp",
                "raw_heap_diff_executor",
                "rawHeapDiffExecutor",
                "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp",
                "reviewHeapSnapshotDiffExecutorRawHeapParserOrExecutorMvp",
            )
        )
    @staticmethod
    def _is_heap_snapshot_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_collect_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_readiness_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-readiness",
            "cdp-heap-snapshot-readiness",
            "heap-profiler-readiness",
            "review-heap-snapshot-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_readiness",
                "heapSnapshotReadiness",
                "cdp_heap_snapshot_readiness",
                "cdpHeapSnapshotReadiness",
                "heap_profiler_readiness",
                "heapProfilerReadiness",
                "review_heap_snapshot_readiness",
                "reviewHeapSnapshotReadiness",
            )
        )
    @staticmethod
    def _is_heap_snapshot_collect_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_readiness_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-collect",
            "cdp-heap-snapshot-collect",
            "collect-heap-snapshot",
            "reviewed-heap-snapshot-collect",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_collect",
                "heapSnapshotCollect",
                "cdp_heap_snapshot_collect",
                "cdpHeapSnapshotCollect",
                "collect_heap_snapshot",
                "collectHeapSnapshot",
                "reviewed_heap_snapshot_collect",
                "reviewedHeapSnapshotCollect",
                "execute_heap_snapshot_collect",
                "executeHeapSnapshotCollect",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-readiness",
            "heap-snapshot-diff-review",
            "review-heap-snapshot-diff",
            "heap-diff-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_readiness",
                "heapSnapshotDiffReadiness",
                "heap_snapshot_diff_review",
                "heapSnapshotDiffReview",
                "review_heap_snapshot_diff",
                "reviewHeapSnapshotDiff",
                "heap_diff_readiness",
                "heapDiffReadiness",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_executor_bounded_gate_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-bounded-gate",
            "heap-snapshot-diff-executor-bounded-executor-gate",
            "heap-snapshot-diff-bounded-gate",
            "heap-diff-executor-bounded-gate",
            "raw-heap-diff-bounded-gate",
            "review-heap-snapshot-diff-executor-bounded-gate",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_bounded_gate",
                "heapSnapshotDiffExecutorBoundedGate",
                "heap_snapshot_diff_executor_bounded_executor_gate",
                "heapSnapshotDiffExecutorBoundedExecutorGate",
                "heap_snapshot_diff_bounded_gate",
                "heapSnapshotDiffBoundedGate",
                "heap_diff_executor_bounded_gate",
                "heapDiffExecutorBoundedGate",
                "raw_heap_diff_bounded_gate",
                "rawHeapDiffBoundedGate",
                "review_heap_snapshot_diff_executor_bounded_gate",
                "reviewHeapSnapshotDiffExecutorBoundedGate",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-transaction-preflight",
            "heap-snapshot-diff-transaction-preflight",
            "heap-diff-executor-transaction-preflight",
            "raw-heap-diff-transaction-preflight",
            "review-heap-snapshot-diff-executor-transaction-preflight",
            "preflight-heap-snapshot-diff-executor-transaction",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_transaction_preflight",
                "heapSnapshotDiffExecutorTransactionPreflight",
                "heap_snapshot_diff_transaction_preflight",
                "heapSnapshotDiffTransactionPreflight",
                "heap_diff_executor_transaction_preflight",
                "heapDiffExecutorTransactionPreflight",
                "raw_heap_diff_transaction_preflight",
                "rawHeapDiffTransactionPreflight",
                "review_heap_snapshot_diff_executor_transaction_preflight",
                "reviewHeapSnapshotDiffExecutorTransactionPreflight",
                "preflight_heap_snapshot_diff_executor_transaction",
                "preflightHeapSnapshotDiffExecutorTransaction",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_executor_approval_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-approval-plan",
            "heap-snapshot-diff-approval-plan",
            "heap-diff-executor-approval-plan",
            "review-heap-snapshot-diff-executor-approval",
            "raw-heap-diff-approval-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_approval_plan",
                "heapSnapshotDiffExecutorApprovalPlan",
                "heap_snapshot_diff_approval_plan",
                "heapSnapshotDiffApprovalPlan",
                "heap_diff_executor_approval_plan",
                "heapDiffExecutorApprovalPlan",
                "review_heap_snapshot_diff_executor_approval",
                "reviewHeapSnapshotDiffExecutorApproval",
                "raw_heap_diff_approval_plan",
                "rawHeapDiffApprovalPlan",
            )
        )
    @staticmethod
    def _is_heap_snapshot_diff_executor_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_bounded_gate_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_transaction_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_heap_snapshot_diff_executor_approval_plan_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "heap-snapshot-diff-executor-preflight",
            "heap-snapshot-diff-preflight",
            "heap-diff-executor-preflight",
            "review-heap-snapshot-diff-executor",
            "raw-heap-diff-preflight",
        }:
            return True
        return any(
            key in context
            for key in (
                "heap_snapshot_diff_executor_preflight",
                "heapSnapshotDiffExecutorPreflight",
                "heap_snapshot_diff_preflight",
                "heapSnapshotDiffPreflight",
                "heap_diff_executor_preflight",
                "heapDiffExecutorPreflight",
                "review_heap_snapshot_diff_executor",
                "reviewHeapSnapshotDiffExecutor",
                "raw_heap_diff_preflight",
                "rawHeapDiffPreflight",
            )
        )
    @staticmethod
    def _is_object_graph_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "object-graph-diff",
            "js-object-graph-diff",
            "review-object-graph-diff",
            "heap-object-graph-diff",
        }:
            return True
        return any(
            key in context
            for key in (
                "object_graph_diff",
                "objectGraphDiff",
                "js_object_graph_diff",
                "jsObjectGraphDiff",
                "review_object_graph_diff",
                "reviewObjectGraphDiff",
            )
        )
    @staticmethod
    def _is_runtime_object_graph_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "runtime-object-graph-diff",
            "runtime-collected-object-graph-diff",
            "js-runtime-object-graph-diff",
            "collect-runtime-object-graph-diff",
            "scoped-runtime-object-graph-diff",
        }:
            return True
        return any(
            key in context
            for key in (
                "runtime_object_graph_diff",
                "runtimeObjectGraphDiff",
                "runtime_collected_object_graph_diff",
                "runtimeCollectedObjectGraphDiff",
                "js_runtime_object_graph_diff",
                "jsRuntimeObjectGraphDiff",
            )
        )
    @staticmethod
    def _is_object_root_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_runtime_object_graph_diff_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if normalized in {
            "object-root-mutation-audit",
            "object-mutation-audit",
            "js-object-mutation-audit",
        }:
            return True
        return any(
            key in context
            for key in (
                "object_root_mutation_audit",
                "objectRootMutationAudit",
                "object_mutation_audit",
                "objectMutationAudit",
                "object_root",
                "objectRoot",
                "object_root_path",
                "objectRootPath",
                "root_path",
                "rootPath",
                "js_object_root",
                "jsObjectRoot",
            )
        )
    @staticmethod
    def _is_page_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "page-mutation-audit",
            "page-mutation",
            "audit-page-mutation",
            "mutation-audit-page",
            "dom-mutation-audit",
        }:
            return True
        return any(
            key in context
            for key in (
                "page_mutation_audit",
                "pageMutationAudit",
                "audit_page_mutation",
                "auditPageMutation",
                "selected_globals",
                "selectedGlobals",
                "global_names",
                "globalNames",
            )
        )
    @staticmethod
    def _is_flow_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "flow-timeline",
            "cross-request-timeline",
            "request-flow-timeline",
            "continue-flow-timeline",
            "timeline-continuation",
        }:
            return True
        return any(
            key in context
            for key in (
                "flow_timeline",
                "flowTimeline",
                "previous_flow_timeline",
                "previousFlowTimeline",
                "flow_events",
                "flowEvents",
                "timeline_inputs",
                "timelineInputs",
            )
        )
    @staticmethod
    def _is_mutation_observer_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "mutation-observer",
            "mutation-observer-timeline",
            "mutation-timeline",
            "page-mutation-timeline",
            "dom-mutation-timeline",
        }:
            return True
        return any(
            key in context
            for key in (
                "mutation_observer_timeline",
                "mutationObserverTimeline",
                "mutation_timeline",
                "mutationTimeline",
                "observer_wait_ms",
                "observerWaitMs",
                "mutation_record_limit",
                "mutationRecordLimit",
            )
        )
    @staticmethod
    def _is_closure_scope_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_event_harvest_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_restore_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_replacement_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_replacement_plan_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_closure_wrapper_continuation_execution_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_closure_wrapper_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_continuation_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_next_iteration_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_replacement_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_event_harvest_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_restore_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_replacement_execution_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_replacement_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_event_harvest_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_restore_execution_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_restore_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_event_harvest_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_event_harvest_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_checkpoint_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
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
    @staticmethod
    def _is_closure_wrapper_assignment_safety_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_execution_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_continuation_readiness_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_closure_wrapper_runtime_mutability_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_result_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
    def _is_source_map_terminal_review_package_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_source_map_terminal_review_closure_checkpoint_request(protection_name, context):
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
    @staticmethod
    def _is_source_map_terminal_review_closure_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        if _NativeWebRequestMatchers._is_source_map_terminal_review_final_audit_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
    def _is_source_map_followthrough_completion_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_source_map_terminal_review_package_request(protection_name, context):
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
    @staticmethod
    def _is_source_map_selected_executor_result_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_source_map_followthrough_completion_checkpoint_request(protection_name, context):
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
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
    @staticmethod
    def _is_module_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"}:
            return True
        return any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        )
    @staticmethod
    def _is_module_federation_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-recursive-traversal-plan",
            "module-federation-traversal-recursion-plan",
            "plan-module-federation-recursive-traversal",
            "federation-recursive-traversal-plan",
            "remote-module-recursive-traversal-plan",
            "module-federation-recursive-traversal-followup",
            "execute-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-checkpoint",
            "reviewed-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-execution",
            "execute-module-federation-recursive-traversal-next-step",
            "reviewed-module-federation-recursive-traversal-execution",
        } or any(
            key in context
            for key in (
                "module_federation_recursive_traversal_plan",
                "moduleFederationRecursiveTraversalPlan",
                "module-federation-recursive-traversal-plan",
                "module_federation_traversal_recursion_plan",
                "moduleFederationTraversalRecursionPlan",
                "plan_module_federation_recursive_traversal",
                "planModuleFederationRecursiveTraversal",
                "federation_recursive_traversal_plan",
                "federationRecursiveTraversalPlan",
                "module_federation_recursive_traversal_followup",
                "moduleFederationRecursiveTraversalFollowup",
                "module-federation-recursive-traversal-followup",
                "execute_module_federation_recursive_traversal_followup",
                "executeModuleFederationRecursiveTraversalFollowup",
                "module_federation_recursive_traversal_execution",
                "moduleFederationRecursiveTraversalExecution",
                "module-federation-recursive-traversal-execution",
                "execute_module_federation_recursive_traversal_next_step",
                "executeModuleFederationRecursiveTraversalNextStep",
            )
        ):
            return False
        if normalized in {
            "module-federation-traversal-workflow-execution",
            "module-federation-remote-traversal-workflow-execution",
            "federation-traversal-workflow-execution",
            "remote-module-traversal-workflow-execution",
            "execute-module-federation-traversal-workflow",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_traversal_workflow_execution",
                "moduleFederationTraversalWorkflowExecution",
                "module-federation-traversal-workflow-execution",
                "federation_traversal_workflow_execution",
                "federationTraversalWorkflowExecution",
                "execute_module_federation_traversal_workflow",
                "executeModuleFederationTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_module_federation_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-recursive-traversal-followup",
            "execute-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-checkpoint",
            "reviewed-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-execution",
            "execute-module-federation-recursive-traversal-next-step",
            "reviewed-module-federation-recursive-traversal-execution",
        } or any(
            key in context
            for key in (
                "module_federation_recursive_traversal_followup",
                "moduleFederationRecursiveTraversalFollowup",
                "module-federation-recursive-traversal-followup",
                "execute_module_federation_recursive_traversal_followup",
                "executeModuleFederationRecursiveTraversalFollowup",
                "module_federation_recursive_traversal_execution",
                "moduleFederationRecursiveTraversalExecution",
                "module-federation-recursive-traversal-execution",
                "execute_module_federation_recursive_traversal_next_step",
                "executeModuleFederationRecursiveTraversalNextStep",
            )
        ):
            return False
        if normalized in {
            "module-federation-recursive-traversal-plan",
            "module-federation-traversal-recursion-plan",
            "plan-module-federation-recursive-traversal",
            "federation-recursive-traversal-plan",
            "remote-module-recursive-traversal-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_recursive_traversal_plan",
                "moduleFederationRecursiveTraversalPlan",
                "module-federation-recursive-traversal-plan",
                "module_federation_traversal_recursion_plan",
                "moduleFederationTraversalRecursionPlan",
                "plan_module_federation_recursive_traversal",
                "planModuleFederationRecursiveTraversal",
                "federation_recursive_traversal_plan",
                "federationRecursiveTraversalPlan",
            )
        )
    @staticmethod
    def _is_module_federation_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-recursive-traversal-execution",
            "execute-module-federation-recursive-traversal-next-step",
            "reviewed-module-federation-recursive-traversal-execution",
        } or any(
            key in context
            for key in (
                "module_federation_recursive_traversal_execution",
                "moduleFederationRecursiveTraversalExecution",
                "module-federation-recursive-traversal-execution",
                "execute_module_federation_recursive_traversal_next_step",
                "executeModuleFederationRecursiveTraversalNextStep",
            )
        ):
            return False
        if normalized in {
            "module-federation-recursive-traversal-followup",
            "execute-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-checkpoint",
            "reviewed-module-federation-recursive-traversal-followup",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_recursive_traversal_followup",
                "moduleFederationRecursiveTraversalFollowup",
                "module-federation-recursive-traversal-followup",
                "execute_module_federation_recursive_traversal_followup",
                "executeModuleFederationRecursiveTraversalFollowup",
            )
        )
    @staticmethod
    def _is_module_federation_recursive_continuation_journal_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_module_federation_recursive_continuation_checkpoint_request(protection_name, context):
            return False
        if normalized in {
            "module-federation-recursive-continuation-journal",
            "module-federation-recursive-traversal-continuation-journal",
            "plan-module-federation-recursive-continuation",
            "append-module-federation-recursive-continuation-journal",
            "reviewed-module-federation-recursive-continuation-journal",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_recursive_continuation_journal",
                "moduleFederationRecursiveContinuationJournal",
                "module-federation-recursive-continuation-journal",
                "module_federation_recursive_traversal_continuation_journal",
                "moduleFederationRecursiveTraversalContinuationJournal",
                "module-federation-recursive-traversal-continuation-journal",
                "append_module_federation_recursive_continuation_journal",
                "appendModuleFederationRecursiveContinuationJournal",
            )
        )
    @staticmethod
    def _is_recursive_continuation_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "recursive-continuation-readiness",
            "traversal-continuation-readiness",
            "review-recursive-continuation-readiness",
            "review-traversal-continuation-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "recursive_continuation_readiness",
                "recursiveContinuationReadiness",
                "recursive-continuation-readiness",
                "traversal_continuation_readiness",
                "traversalContinuationReadiness",
                "review_recursive_continuation_readiness",
                "reviewRecursiveContinuationReadiness",
            )
        )
    @staticmethod
    def _is_module_federation_recursive_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-recursive-continuation-checkpoint",
            "module-federation-recursive-traversal-continuation-checkpoint",
            "execute-module-federation-recursive-continuation-checkpoint",
            "execute-module-federation-recursive-traversal-continuation-checkpoint",
            "reviewed-module-federation-recursive-continuation-checkpoint",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_recursive_continuation_checkpoint",
                "moduleFederationRecursiveContinuationCheckpoint",
                "module-federation-recursive-continuation-checkpoint",
                "module_federation_recursive_traversal_continuation_checkpoint",
                "moduleFederationRecursiveTraversalContinuationCheckpoint",
                "module-federation-recursive-traversal-continuation-checkpoint",
                "execute_module_federation_recursive_continuation_checkpoint",
                "executeModuleFederationRecursiveContinuationCheckpoint",
                "reviewed_module_federation_recursive_continuation_checkpoint",
                "reviewedModuleFederationRecursiveContinuationCheckpoint",
            )
        )
    @staticmethod
    def _is_module_federation_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-recursive-traversal-execution",
            "execute-module-federation-recursive-traversal-next-step",
            "reviewed-module-federation-recursive-traversal-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_recursive_traversal_execution",
                "moduleFederationRecursiveTraversalExecution",
                "module-federation-recursive-traversal-execution",
                "execute_module_federation_recursive_traversal",
                "executeModuleFederationRecursiveTraversal",
                "execute_module_federation_recursive_traversal_next_step",
                "executeModuleFederationRecursiveTraversalNextStep",
            )
        )
    @staticmethod
    def _is_module_federation_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-traversal-workflow-plan",
            "module-federation-remote-traversal-workflow-plan",
            "federation-traversal-workflow-plan",
            "remote-module-traversal-workflow-plan",
            "plan-module-federation-traversal-workflow",
            "module-federation-traversal-workflow-execution",
            "execute-module-federation-traversal-workflow",
            "module-federation-recursive-traversal-plan",
            "module-federation-traversal-recursion-plan",
            "plan-module-federation-recursive-traversal",
            "module-federation-recursive-traversal-followup",
            "execute-module-federation-recursive-traversal-followup",
            "module-federation-recursive-traversal-checkpoint",
            "module-federation-recursive-traversal-execution",
            "execute-module-federation-recursive-traversal-next-step",
            "reviewed-module-federation-recursive-traversal-execution",
        } or any(key in context for key in (
            "module_federation_traversal_workflow_execution",
            "moduleFederationTraversalWorkflowExecution",
            "module-federation-traversal-workflow-execution",
            "execute_module_federation_traversal_workflow",
            "executeModuleFederationTraversalWorkflow",
            "module_federation_recursive_traversal_plan",
            "moduleFederationRecursiveTraversalPlan",
            "module-federation-recursive-traversal-plan",
            "module_federation_traversal_recursion_plan",
            "moduleFederationTraversalRecursionPlan",
            "plan_module_federation_recursive_traversal",
            "planModuleFederationRecursiveTraversal",
            "module_federation_recursive_traversal_followup",
            "moduleFederationRecursiveTraversalFollowup",
            "module-federation-recursive-traversal-followup",
            "execute_module_federation_recursive_traversal_followup",
            "executeModuleFederationRecursiveTraversalFollowup",
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "execute_module_federation_recursive_traversal_next_step",
            "executeModuleFederationRecursiveTraversalNextStep",
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "federation_traversal_workflow_plan",
            "federationTraversalWorkflowPlan",
            "plan_module_federation_traversal_workflow",
            "planModuleFederationTraversalWorkflow",
        )):
            return False
        if normalized in {
            "module-federation-traversal-graph",
            "module-federation-remote-traversal-graph",
            "federation-traversal-graph",
            "remote-module-traversal-graph",
            "plan-module-federation-traversal-graph",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_traversal_graph",
                "moduleFederationTraversalGraph",
                "module-federation-traversal-graph",
                "federation_traversal_graph",
                "federationTraversalGraph",
                "remote_module_traversal_graph",
                "remoteModuleTraversalGraph",
            )
        )
    @staticmethod
    def _is_module_federation_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-traversal-workflow-plan",
            "module-federation-remote-traversal-workflow-plan",
            "federation-traversal-workflow-plan",
            "remote-module-traversal-workflow-plan",
            "plan-module-federation-traversal-workflow",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_traversal_workflow_plan",
                "moduleFederationTraversalWorkflowPlan",
                "module-federation-traversal-workflow-plan",
                "federation_traversal_workflow_plan",
                "federationTraversalWorkflowPlan",
                "plan_module_federation_traversal_workflow",
                "planModuleFederationTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_module_federation_get_init_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-get-init",
            "module-federation-get-init-plan",
            "federation-get-init",
            "federation-get-init-plan",
            "module-federation-plan",
            "federation-analysis-plan",
            "module-federation-export-hook-plan",
            "module-federation-export-hooks",
            "remote-export-hook-plan",
            "remote-export-hooks",
            "module-federation-export-hook-install",
            "module-federation-remote-export-hook",
            "remote-export-hook-install",
            "hook-module-federation-remote-export",
            "reviewed-remote-export-hook",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_get_init",
                "moduleFederationGetInit",
                "federation_get_init_plan",
                "federationGetInitPlan",
                "module_federation_plan",
                "moduleFederationPlan",
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
                "exposed_modules",
                "exposedModules",
                "execute_module_federation_export_hook",
                "executeModuleFederationExportHook",
                "hook_module_federation_remote_export",
                "hookModuleFederationRemoteExport",
                "install_remote_export_hook",
                "installRemoteExportHook",
                "reviewed_remote_export_hook",
                "reviewedRemoteExportHook",
            )
        )
    @staticmethod
    def _is_module_federation_get_init_probe_request(context: dict[str, Any]) -> bool:
        return any(
            bool(context.get(key))
            for key in (
                "execute_module_federation_get_init",
                "executeModuleFederationGetInit",
                "probe_module_federation_get_init",
                "probeModuleFederationGetInit",
                "execute_get_init",
                "executeGetInit",
            )
        )
    @staticmethod
    def _is_module_federation_factory_invoke_request(context: dict[str, Any]) -> bool:
        return any(
            bool(context.get(key))
            for key in (
                "execute_module_federation_factory",
                "executeModuleFederationFactory",
                "invoke_module_federation_factory",
                "invokeModuleFederationFactory",
                "execute_remote_factory",
                "executeRemoteFactory",
                "invoke_remote_factory",
                "invokeRemoteFactory",
            )
        )
    @staticmethod
    def _is_module_federation_export_hook_install_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-export-hook-install",
            "module-federation-remote-export-hook",
            "remote-export-hook-install",
            "hook-module-federation-remote-export",
            "reviewed-remote-export-hook",
        }:
            return True
        return any(
            bool(context.get(key))
            for key in (
                "execute_module_federation_export_hook",
                "executeModuleFederationExportHook",
                "hook_module_federation_remote_export",
                "hookModuleFederationRemoteExport",
                "install_remote_export_hook",
                "installRemoteExportHook",
                "reviewed_remote_export_hook",
                "reviewedRemoteExportHook",
            )
        )
    @staticmethod
    def _is_module_federation_export_hook_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-export-hook-plan",
            "module-federation-export-hooks",
            "remote-export-hook-plan",
            "remote-export-hooks",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_export_hook_plan",
                "moduleFederationExportHookPlan",
                "remote_export_hook_plan",
                "remoteExportHookPlan",
                "module_federation_factory_invoke_result",
                "moduleFederationFactoryInvokeResult",
                "module-federation-factory-invoke-result",
            )
        )
    @staticmethod
    def _is_custom_loader_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-execution",
            "execute-custom-loader",
            "reviewed-custom-loader-execution",
            "custom-loader-execute",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_execution",
                "customLoaderExecution",
                "execute_custom_loader",
                "executeCustomLoader",
                "reviewed_custom_loader_execution",
                "reviewedCustomLoaderExecution",
            )
        ) and any(
            key in context
            for key in (
                "custom_loader_execution_preflight",
                "customLoaderExecutionPreflight",
                "custom-loader-execution-preflight",
                "custom_loader_preflight",
                "customLoaderPreflight",
            )
        )
    @staticmethod
    def _is_custom_loader_continuation_workflow_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-continuation-workflow",
            "custom-loader-continuation-plan",
            "plan-custom-loader-continuation",
            "review-custom-loader-continuation-workflow",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_continuation_workflow",
                "customLoaderContinuationWorkflow",
                "custom-loader-continuation-workflow",
                "plan_custom_loader_continuation_workflow",
                "planCustomLoaderContinuationWorkflow",
            )
        )
    @staticmethod
    def _is_custom_loader_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-continuation-execution",
            "execute-custom-loader-continuation-step",
            "custom-loader-continuation-step",
            "reviewed-custom-loader-continuation-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_continuation_execution",
                "customLoaderContinuationExecution",
                "custom-loader-continuation-execution",
                "execute_custom_loader_continuation_step",
                "executeCustomLoaderContinuationStep",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal-workflow-execution",
            "execute-custom-loader-traversal-workflow",
            "custom-loader-traversal-workflow-step",
            "reviewed-custom-loader-traversal-workflow-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal_workflow_execution",
                "customLoaderTraversalWorkflowExecution",
                "custom-loader-traversal-workflow-execution",
                "execute_custom_loader_traversal_workflow",
                "executeCustomLoaderTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal-loop-execution",
            "execute-custom-loader-traversal-loop",
            "custom-loader-bounded-loop-execution",
            "reviewed-custom-loader-traversal-loop-execution",
            "custom-loader-recursive-traversal-plan",
            "custom-loader-traversal-recursion-plan",
            "plan-custom-loader-recursive-traversal",
        } or any(
            key in context
            for key in (
                "custom_loader_traversal_loop_execution",
                "customLoaderTraversalLoopExecution",
                "custom-loader-traversal-loop-execution",
                "execute_custom_loader_traversal_loop",
                "executeCustomLoaderTraversalLoop",
                "custom_loader_recursive_traversal_plan",
                "customLoaderRecursiveTraversalPlan",
                "custom-loader-recursive-traversal-plan",
                "custom_loader_traversal_recursion_plan",
                "customLoaderTraversalRecursionPlan",
                "plan_custom_loader_recursive_traversal",
                "planCustomLoaderRecursiveTraversal",
            )
        ):
            return False
        if normalized in {
            "custom-loader-traversal-loop-plan",
            "custom-loader-deep-traversal-loop",
            "plan-custom-loader-traversal-loop",
            "custom-loader-bounded-traversal-loop",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal_loop_plan",
                "customLoaderTraversalLoopPlan",
                "custom-loader-traversal-loop-plan",
                "custom_loader_deep_traversal_loop",
                "customLoaderDeepTraversalLoop",
                "plan_custom_loader_traversal_loop",
                "planCustomLoaderTraversalLoop",
            )
        )
    @staticmethod
    def _is_custom_loader_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-recursive-traversal-execution",
            "execute-custom-loader-recursive-traversal",
            "execute-custom-loader-recursive-traversal-next-loop",
            "reviewed-custom-loader-recursive-traversal-execution",
            "custom-loader-recursive-traversal-followup",
            "execute-custom-loader-recursive-traversal-followup",
            "custom-loader-recursive-traversal-checkpoint",
            "reviewed-custom-loader-recursive-traversal-followup",
        } or any(
            key in context
            for key in (
                "custom_loader_recursive_traversal_execution",
                "customLoaderRecursiveTraversalExecution",
                "custom-loader-recursive-traversal-execution",
                "execute_custom_loader_recursive_traversal",
                "executeCustomLoaderRecursiveTraversal",
                "custom_loader_recursive_traversal_followup",
                "customLoaderRecursiveTraversalFollowup",
                "custom-loader-recursive-traversal-followup",
                "execute_custom_loader_recursive_traversal_followup",
                "executeCustomLoaderRecursiveTraversalFollowup",
            )
        ):
            return False
        if normalized in {
            "custom-loader-recursive-traversal-plan",
            "custom-loader-traversal-recursion-plan",
            "plan-custom-loader-recursive-traversal",
            "custom-loader-deeper-recursive-traversal",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_recursive_traversal_plan",
                "customLoaderRecursiveTraversalPlan",
                "custom-loader-recursive-traversal-plan",
                "custom_loader_traversal_recursion_plan",
                "customLoaderTraversalRecursionPlan",
                "plan_custom_loader_recursive_traversal",
                "planCustomLoaderRecursiveTraversal",
            )
        )
    @staticmethod
    def _is_custom_loader_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-recursive-traversal-execution",
            "execute-custom-loader-recursive-traversal",
            "execute-custom-loader-recursive-traversal-next-loop",
            "reviewed-custom-loader-recursive-traversal-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_recursive_traversal_execution",
                "customLoaderRecursiveTraversalExecution",
                "custom-loader-recursive-traversal-execution",
                "execute_custom_loader_recursive_traversal",
                "executeCustomLoaderRecursiveTraversal",
                "execute_custom_loader_recursive_traversal_next_loop",
                "executeCustomLoaderRecursiveTraversalNextLoop",
            )
        )
    @staticmethod
    def _is_custom_loader_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-recursive-traversal-execution",
            "execute-custom-loader-recursive-traversal",
            "execute-custom-loader-recursive-traversal-next-loop",
            "reviewed-custom-loader-recursive-traversal-execution",
        } or any(
            key in context
            for key in (
                "custom_loader_recursive_traversal_execution",
                "customLoaderRecursiveTraversalExecution",
                "custom-loader-recursive-traversal-execution",
                "execute_custom_loader_recursive_traversal",
                "executeCustomLoaderRecursiveTraversal",
            )
        ):
            return False
        if normalized in {
            "custom-loader-recursive-traversal-followup",
            "execute-custom-loader-recursive-traversal-followup",
            "custom-loader-recursive-traversal-checkpoint",
            "reviewed-custom-loader-recursive-traversal-followup",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_recursive_traversal_followup",
                "customLoaderRecursiveTraversalFollowup",
                "custom-loader-recursive-traversal-followup",
                "execute_custom_loader_recursive_traversal_followup",
                "executeCustomLoaderRecursiveTraversalFollowup",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal-loop-execution",
            "execute-custom-loader-traversal-loop",
            "custom-loader-bounded-loop-execution",
            "reviewed-custom-loader-traversal-loop-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal_loop_execution",
                "customLoaderTraversalLoopExecution",
                "custom-loader-traversal-loop-execution",
                "execute_custom_loader_traversal_loop",
                "executeCustomLoaderTraversalLoop",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal-workflow-plan",
            "custom-loader-deep-traversal-workflow",
            "plan-custom-loader-traversal-workflow",
            "custom-loader-multi-step-traversal-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal_workflow_plan",
                "customLoaderTraversalWorkflowPlan",
                "custom-loader-traversal-workflow-plan",
                "custom_loader_deep_traversal_workflow",
                "customLoaderDeepTraversalWorkflow",
                "plan_custom_loader_traversal_workflow",
                "planCustomLoaderTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal-graph",
            "custom-loader-continuation-queue",
            "plan-custom-loader-deep-traversal",
            "custom-loader-deep-traversal-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal_graph",
                "customLoaderTraversalGraph",
                "custom-loader-traversal-graph",
                "custom_loader_continuation_queue",
                "customLoaderContinuationQueue",
                "plan_custom_loader_deep_traversal",
                "planCustomLoaderDeepTraversal",
            )
        )
    @staticmethod
    def _is_custom_loader_continuation_journal_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-continuation-journal",
            "append-custom-loader-continuation-journal",
            "custom-loader-continuation-journal-append",
            "review-custom-loader-continuation-journal",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_continuation_journal",
                "customLoaderContinuationJournal",
                "custom-loader-continuation-journal",
                "append_custom_loader_continuation_journal",
                "appendCustomLoaderContinuationJournal",
            )
        )
    @staticmethod
    def _is_custom_loader_execution_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-execution-preflight",
            "custom-loader-preflight",
            "preflight-custom-loader-execution",
            "review-custom-loader-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_execution_preflight",
                "customLoaderExecutionPreflight",
                "execute_custom_loader",
                "executeCustomLoader",
                "custom_loader_traversal_plan",
                "customLoaderTraversalPlan",
                "custom-loader-traversal-plan",
            )
        ) and any(
            key in context
            for key in (
                "selected_custom_loader_candidate",
                "selectedCustomLoaderCandidate",
                "selected_loader_candidate",
                "selectedLoaderCandidate",
                "selected_candidate",
                "selectedCandidate",
                "candidate_index",
                "candidateIndex",
            )
        )
    @staticmethod
    def _is_custom_loader_traversal_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if (
            normalized.startswith("async-chunk-")
            or "async-chunk-recursive-traversal" in normalized
            or normalized in {"deep-async-chunk-traversal", "plan-async-chunk-deep-traversal"}
            or any(key in context for key in (
                "async_chunk_recursive_traversal_plan",
                "asyncChunkRecursiveTraversalPlan",
                "async_chunk_recursive_traversal_followup",
                "asyncChunkRecursiveTraversalFollowup",
                "async_chunk_recursive_traversal_execution",
                "asyncChunkRecursiveTraversalExecution",
                "execute_async_chunk_recursive_traversal",
                "executeAsyncChunkRecursiveTraversal",
            ))
        ):
            return False
        if normalized in {
            "custom-loader-traversal",
            "custom-loader-traversal-plan",
            "loader-traversal-plan",
            "custom-loader-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal",
                "customLoaderTraversal",
                "loader_traversal_plan",
                "loaderTraversalPlan",
                "custom_loader_candidate",
                "customLoaderCandidate",
                "custom_loader_candidates",
                "customLoaderCandidates",
                "loader_candidates",
                "loaderCandidates",
                "chunk_graph",
                "chunkGraph",
            )
        )
    @staticmethod
    def _is_async_chunk_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-traversal-graph",
            "async-chunk-graph-queue",
            "plan-async-chunk-deep-traversal",
            "async-chunk-deep-traversal-graph",
            "deep-async-chunk-traversal",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_traversal_graph",
                "asyncChunkTraversalGraph",
                "async-chunk-traversal-graph",
                "async_chunk_graph_queue",
                "asyncChunkGraphQueue",
                "plan_async_chunk_deep_traversal",
                "planAsyncChunkDeepTraversal",
            )
        )
    @staticmethod
    def _is_async_chunk_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-recursive-traversal-execution",
            "execute-async-chunk-recursive-traversal",
            "execute-async-chunk-recursive-traversal-next-loop",
            "reviewed-async-chunk-recursive-traversal-execution",
            "async-chunk-recursive-traversal-followup",
            "execute-async-chunk-recursive-traversal-followup",
            "async-chunk-recursive-traversal-checkpoint",
            "reviewed-async-chunk-recursive-traversal-followup",
        } or any(
            key in context
            for key in (
                "async_chunk_recursive_traversal_execution",
                "asyncChunkRecursiveTraversalExecution",
                "async-chunk-recursive-traversal-execution",
                "execute_async_chunk_recursive_traversal",
                "executeAsyncChunkRecursiveTraversal",
                "async_chunk_recursive_traversal_followup",
                "asyncChunkRecursiveTraversalFollowup",
                "async-chunk-recursive-traversal-followup",
                "execute_async_chunk_recursive_traversal_followup",
                "executeAsyncChunkRecursiveTraversalFollowup",
            )
        ):
            return False
        if normalized in {
            "async-chunk-recursive-traversal-plan",
            "async-chunk-traversal-recursion-plan",
            "plan-async-chunk-recursive-traversal",
            "async-chunk-deeper-recursive-traversal",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_recursive_traversal_plan",
                "asyncChunkRecursiveTraversalPlan",
                "async-chunk-recursive-traversal-plan",
                "async_chunk_traversal_recursion_plan",
                "asyncChunkTraversalRecursionPlan",
                "plan_async_chunk_recursive_traversal",
                "planAsyncChunkRecursiveTraversal",
            )
        )
    @staticmethod
    def _is_async_chunk_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-recursive-traversal-execution",
            "execute-async-chunk-recursive-traversal",
            "execute-async-chunk-recursive-traversal-next-loop",
            "reviewed-async-chunk-recursive-traversal-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_recursive_traversal_execution",
                "asyncChunkRecursiveTraversalExecution",
                "async-chunk-recursive-traversal-execution",
                "execute_async_chunk_recursive_traversal",
                "executeAsyncChunkRecursiveTraversal",
                "execute_async_chunk_recursive_traversal_next_loop",
                "executeAsyncChunkRecursiveTraversalNextLoop",
            )
        )
    @staticmethod
    def _is_async_chunk_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-recursive-traversal-execution",
            "execute-async-chunk-recursive-traversal",
            "execute-async-chunk-recursive-traversal-next-loop",
            "reviewed-async-chunk-recursive-traversal-execution",
        } or any(
            key in context
            for key in (
                "async_chunk_recursive_traversal_execution",
                "asyncChunkRecursiveTraversalExecution",
                "async-chunk-recursive-traversal-execution",
                "execute_async_chunk_recursive_traversal",
                "executeAsyncChunkRecursiveTraversal",
            )
        ):
            return False
        if normalized in {
            "async-chunk-recursive-traversal-followup",
            "execute-async-chunk-recursive-traversal-followup",
            "async-chunk-recursive-traversal-checkpoint",
            "reviewed-async-chunk-recursive-traversal-followup",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_recursive_traversal_followup",
                "asyncChunkRecursiveTraversalFollowup",
                "async-chunk-recursive-traversal-followup",
                "execute_async_chunk_recursive_traversal_followup",
                "executeAsyncChunkRecursiveTraversalFollowup",
            )
        )
    @staticmethod
    def _is_async_chunk_traversal_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-recursive-traversal-plan",
            "async-chunk-traversal-recursion-plan",
            "plan-async-chunk-recursive-traversal",
            "async-chunk-recursive-traversal-followup",
            "execute-async-chunk-recursive-traversal-followup",
            "async-chunk-recursive-traversal-checkpoint",
            "async-chunk-recursive-traversal-execution",
            "execute-async-chunk-recursive-traversal",
            "execute-async-chunk-recursive-traversal-next-loop",
        } or any(key in context for key in (
            "async_chunk_recursive_traversal_plan",
            "asyncChunkRecursiveTraversalPlan",
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
        )):
            return False
        if normalized in {
            "async-chunk-traversal-loop-plan",
            "async-chunk-deep-traversal-loop",
            "plan-async-chunk-traversal-loop",
            "async-chunk-bounded-traversal-loop",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_traversal_loop_plan",
                "asyncChunkTraversalLoopPlan",
                "async-chunk-traversal-loop-plan",
                "async_chunk_deep_traversal_loop",
                "asyncChunkDeepTraversalLoop",
                "plan_async_chunk_traversal_loop",
                "planAsyncChunkTraversalLoop",
            )
        )
    @staticmethod
    def _is_async_chunk_traversal_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-recursive-traversal-execution",
            "execute-async-chunk-recursive-traversal",
            "execute-async-chunk-recursive-traversal-next-loop",
            "async-chunk-recursive-traversal-followup",
            "execute-async-chunk-recursive-traversal-followup",
        } or any(key in context for key in (
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
        )):
            return False
        if normalized in {
            "async-chunk-traversal-loop-execution",
            "execute-async-chunk-traversal-loop",
            "async-chunk-bounded-loop-execution",
            "reviewed-async-chunk-traversal-loop-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_traversal_loop_execution",
                "asyncChunkTraversalLoopExecution",
                "async-chunk-traversal-loop-execution",
                "execute_async_chunk_traversal_loop",
                "executeAsyncChunkTraversalLoop",
            )
        )
    @staticmethod
    def _is_async_chunk_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-traversal-workflow-execution",
            "execute-async-chunk-traversal-workflow",
            "async-chunk-traversal-workflow-step",
            "reviewed-async-chunk-traversal-workflow-execution",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_traversal_workflow_execution",
                "asyncChunkTraversalWorkflowExecution",
                "async-chunk-traversal-workflow-execution",
                "execute_async_chunk_traversal_workflow",
                "executeAsyncChunkTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_async_chunk_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-traversal-workflow-plan",
            "async-chunk-deep-traversal-workflow",
            "plan-async-chunk-traversal-workflow",
            "async-chunk-multi-step-traversal-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_traversal_workflow_plan",
                "asyncChunkTraversalWorkflowPlan",
                "async-chunk-traversal-workflow-plan",
                "async_chunk_deep_traversal_workflow",
                "asyncChunkDeepTraversalWorkflow",
                "plan_async_chunk_traversal_workflow",
                "planAsyncChunkTraversalWorkflow",
            )
        )
    @staticmethod
    def _is_async_chunk_load_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"async-chunk-load", "load-async-chunk", "chunk-load", "webpack-chunk-load"}:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_load",
                "asyncChunkLoad",
                "execute_chunk_load",
                "executeChunkLoad",
                "chunk_candidate",
                "chunkCandidate",
                "chunk_id",
                "chunkId",
            )
        )
    @staticmethod
    def _is_async_chunk_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-module-hook",
            "async-chunk-hook-module",
            "hook-async-chunk-module",
            "reviewed-async-chunk-module-hook",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_async_chunk_module_hook",
                "executeAsyncChunkModuleHook",
                "hook_async_chunk_module",
                "hookAsyncChunkModule",
                "reviewed_async_chunk_module_hook",
                "reviewedAsyncChunkModuleHook",
            )
        )
    @staticmethod
    def _is_custom_loader_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-module-hook",
            "custom-loader-hook-module",
            "hook-custom-loader-module",
            "reviewed-custom-loader-module-hook",
        }:
            return True
        return any(
            key in context
            for key in (
                "execute_custom_loader_module_hook",
                "executeCustomLoaderModuleHook",
                "hook_custom_loader_module",
                "hookCustomLoaderModule",
                "reviewed_custom_loader_module_hook",
                "reviewedCustomLoaderModuleHook",
            )
        )
    @staticmethod
    def _is_async_chunk_module_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "async-chunk-module-diff",
            "async-chunk-hook-candidates",
            "chunk-module-diff",
            "chunk-hook-candidates",
        }:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_module_diff",
                "asyncChunkModuleDiff",
                "async_chunk_hook_candidates",
                "asyncChunkHookCandidates",
            )
        )
    @staticmethod
    def _is_custom_loader_module_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-module-diff",
            "custom-loader-hook-candidates",
            "custom-loader-execution-module-diff",
            "custom-loader-execution-diff",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_module_diff",
                "customLoaderModuleDiff",
                "custom_loader_hook_candidates",
                "customLoaderHookCandidates",
            )
        )
    @staticmethod
    def _is_function_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _NativeWebRequestMatchers._is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_event_harvest_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_restore_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_replacement_execution_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_wrapper_replacement_plan_request(protection_name, context):
            return False
        if _NativeWebRequestMatchers._is_closure_scope_discovery_request(protection_name, context):
            return False
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"} or any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        ):
            return False
        if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"} or any(
            key in context
            for key in (
                "module_id",
                "moduleId",
                "webpack_module_id",
                "webpackModuleId",
                "export_name",
                "exportName",
            )
        ):
            return False
        if normalized in {"hook-function", "function-hook", "target-function-hook"}:
            return True
        return any(
            key in context
            for key in (
                "function_name",
                "functionName",
                "function_path",
                "functionPath",
                "function_paths",
                "functionPaths",
                "hook_paths",
                "hookPaths",
                "candidate_id",
                "candidateId",
            )
        )
    @staticmethod
    def _is_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"}:
            return True
        return any(
            key in context
            for key in (
                "module_id",
                "moduleId",
                "webpack_module_id",
                "webpackModuleId",
                "export_name",
                "exportName",
            )
        )
