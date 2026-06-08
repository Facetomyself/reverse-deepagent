from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read


DEBUGGER_ARTIFACT_REVIEW_VERSION = "2026-05-31.debugger-artifact-review-v1"
AUTOMATIC_LOOP_EXECUTOR_APPROVAL_RECORD_VERSION = "reverse-deepagent.paused-session-automatic-loop-executor-approval-record.v1"
AUTOMATIC_LOOP_TRANSACTION_PREFLIGHT_VERSION = "reverse-deepagent.paused-session-automatic-loop-transaction-preflight.v1"
AUTOMATIC_LOOP_TRANSACTION_JOURNAL_VERSION = "reverse-deepagent.paused-session-automatic-loop-transaction-journal.v1"
AUTOMATIC_LOOP_BOUNDED_EXECUTOR_GATE_VERSION = "reverse-deepagent.paused-session-automatic-loop-bounded-executor-gate.v1"
_LIVE_ACTIONS = {"resume", "step", "step_over", "step_into", "step_out", "evaluate", "evaluate_on_callframe"}


def make_review_debugger_artifacts_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only tool that reviews debugger / paused-session artifacts."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def review_debugger_artifacts(
        debugger_artifacts_json: str | None = None,
        debugger_artifacts_ref: str | None = None,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Review debugger artifact JSON without resuming, stepping, evaluating, or mutating runtime state."""

        payload, artifact_read = _loads_object_or_artifact(
            debugger_artifacts_json,
            artifact_ref=debugger_artifacts_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="debugger_artifacts_json",
            artifact_field_name="debugger_artifacts_ref",
        )
        session = _object_alias(payload, "debugger_session", "debugger-session", "debuggerSession")
        timeline = _object_alias(payload, "debugger_timeline", "debugger-timeline", "debuggerTimeline")
        paused = _object_alias(payload, "debugger_paused", "debugger-paused", "debuggerPaused", "paused")
        callframes = _records_alias(payload, "callframes", "callFrames")
        evaluations = _records_alias(payload, "callframe_evaluations", "callframe-evaluations", "callframeEvaluations")
        mutation_audit = _records_alias(payload, "mutation_audit", "mutation-audit", "mutationAudit")
        actions = _records_alias(payload, "debugger_actions", "debugger-actions", "debuggerActions")
        timeline_entries = _records_from(timeline.get("entries") or timeline.get("events") or timeline.get("timeline"))
        live_preflight = _object_alias(
            payload,
            "paused_session_live_continuation_preflight",
            "paused-session-live-continuation-preflight",
            "pausedSessionLiveContinuationPreflight",
            "live_continuation_preflight",
            "liveContinuationPreflight",
        )
        target_attach_readiness = _object_alias(
            payload,
            "paused_session_target_attach_readiness",
            "paused-session-target-attach-readiness",
            "pausedSessionTargetAttachReadiness",
            "target_attach_readiness",
            "targetAttachReadiness",
        )
        cross_process_execution_plan = _object_alias(
            payload,
            "paused_session_cross_process_execution_plan",
            "paused-session-cross-process-execution-plan",
            "pausedSessionCrossProcessExecutionPlan",
            "cross_process_execution_plan",
            "crossProcessExecutionPlan",
        )
        cross_process_session_lifecycle = _object_alias(
            payload,
            "paused_session_cross_process_session_lifecycle",
            "paused-session-cross-process-session-lifecycle",
            "pausedSessionCrossProcessSessionLifecycle",
            "cross_process_session_lifecycle",
            "crossProcessSessionLifecycle",
            "paused_session_lifecycle",
            "pausedSessionLifecycle",
        )
        cross_process_attach_probe = _object_alias(
            payload,
            "paused_session_cross_process_attach_probe",
            "paused-session-cross-process-attach-probe",
            "pausedSessionCrossProcessAttachProbe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        live_callframe_recovery = _object_alias(
            payload,
            "paused_session_live_callframe_recovery",
            "paused-session-live-callframe-recovery",
            "pausedSessionLiveCallframeRecovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        cross_process_one_action = _object_alias(
            payload,
            "paused_session_cross_process_one_action_execution",
            "paused-session-cross-process-one-action-execution",
            "pausedSessionCrossProcessOneActionExecution",
            "cross_process_one_action_execution",
            "crossProcessOneActionExecution",
            "cross_process_one_action",
            "crossProcessOneAction",
        )
        pre_action_subscribe_and_action = _object_alias(
            payload,
            "paused_session_pre_action_subscribe_and_action",
            "paused-session-pre-action-subscribe-and-action",
            "pausedSessionPreActionSubscribeAndAction",
            "pre_action_subscribe_and_action",
            "preActionSubscribeAndAction",
            "subscribe_and_action_orchestration",
            "subscribeAndActionOrchestration",
        )
        next_paused_event_capture_plan = _object_alias(
            payload,
            "paused_session_next_paused_event_capture_plan",
            "paused-session-next-paused-event-capture-plan",
            "pausedSessionNextPausedEventCapturePlan",
            "next_paused_event_capture_plan",
            "nextPausedEventCapturePlan",
        )
        next_paused_event_capture_execution = _object_alias(
            payload,
            "paused_session_next_paused_event_capture_execution",
            "paused-session-next-paused-event-capture-execution",
            "pausedSessionNextPausedEventCaptureExecution",
            "next_paused_event_capture_execution",
            "nextPausedEventCaptureExecution",
        )
        cross_process_continuation_checkpoint = _object_alias(
            payload,
            "paused_session_cross_process_continuation_checkpoint",
            "paused-session-cross-process-continuation-checkpoint",
            "pausedSessionCrossProcessContinuationCheckpoint",
            "cross_process_continuation_checkpoint",
            "crossProcessContinuationCheckpoint",
            "paused_session_continuation_checkpoint",
            "pausedSessionContinuationCheckpoint",
        )
        multi_step_continuation_workflow = _object_alias(
            payload,
            "paused_session_multi_step_continuation_workflow",
            "paused-session-multi-step-continuation-workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "multi_step_paused_session_continuation",
            "multiStepPausedSessionContinuation",
            "paused_session_continuation_workflow",
            "pausedSessionContinuationWorkflow",
            "cross_process_multi_step_continuation",
            "crossProcessMultiStepContinuation",
        )
        multi_step_continuation_execution = _object_alias(
            payload,
            "paused_session_multi_step_continuation_execution",
            "paused-session-multi-step-continuation-execution",
            "pausedSessionMultiStepContinuationExecution",
            "execute_paused_session_continuation_iteration",
            "executePausedSessionContinuationIteration",
            "cross_process_multi_step_continuation_execution",
            "crossProcessMultiStepContinuationExecution",
        )

        multi_step_loop_plan = _object_alias(
            payload,
            "paused_session_multi_step_loop_plan",
            "paused-session-multi-step-loop-plan",
            "pausedSessionMultiStepLoopPlan",
            "paused_session_continuation_loop_plan",
            "pausedSessionContinuationLoopPlan",
            "multi_step_continuation_loop_plan",
            "multiStepContinuationLoopPlan",
        )
        multi_step_loop_execution = _object_alias(
            payload,
            "paused_session_multi_step_loop_execution",
            "paused-session-multi-step-loop-execution",
            "pausedSessionMultiStepLoopExecution",
            "execute_paused_session_loop_iteration",
            "executePausedSessionLoopIteration",
            "execute_paused_session_continuation_loop",
            "executePausedSessionContinuationLoop",
        )
        automatic_loop_readiness = _object_alias(
            payload,
            "paused_session_automatic_loop_readiness",
            "paused-session-automatic-loop-readiness",
            "pausedSessionAutomaticLoopReadiness",
            "paused_session_multi_step_automatic_loop_readiness",
            "pausedSessionMultiStepAutomaticLoopReadiness",
            "automatic_loop_readiness",
            "automaticLoopReadiness",
        )
        automatic_loop_execution_plan = _object_alias(
            payload,
            "paused_session_automatic_loop_execution_plan",
            "paused-session-automatic-loop-execution-plan",
            "pausedSessionAutomaticLoopExecutionPlan",
            "plan_paused_session_automatic_loop_execution",
            "planPausedSessionAutomaticLoopExecution",
            "automatic_loop_execution_plan",
            "automaticLoopExecutionPlan",
        )
        automatic_loop_executor_preflight = _object_alias(
            payload,
            "paused_session_automatic_loop_executor_preflight",
            "paused-session-automatic-loop-executor-preflight",
            "pausedSessionAutomaticLoopExecutorPreflight",
            "preflight_paused_session_automatic_loop_executor",
            "preflightPausedSessionAutomaticLoopExecutor",
            "automatic_loop_executor_preflight",
            "automaticLoopExecutorPreflight",
        )
        automatic_loop_executor_approval_plan = _object_alias(
            payload,
            "paused_session_automatic_loop_executor_approval_plan",
            "paused-session-automatic-loop-executor-approval-plan",
            "pausedSessionAutomaticLoopExecutorApprovalPlan",
            "plan_paused_session_automatic_loop_executor_approval",
            "planPausedSessionAutomaticLoopExecutorApproval",
            "automatic_loop_executor_approval_plan",
            "automaticLoopExecutorApprovalPlan",
        )
        automatic_loop_execution_result = _object_alias(
            payload,
            "paused_session_automatic_loop_execution_result",
            "paused-session-automatic-loop-execution-result",
            "pausedSessionAutomaticLoopExecutionResult",
            "paused_session_automatic_loop_execution",
            "pausedSessionAutomaticLoopExecution",
            "execute_paused_session_automatic_loop",
            "executePausedSessionAutomaticLoop",
            "automatic_loop_execution_result",
            "automaticLoopExecutionResult",
        )
        automatic_loop_followup_checkpoint = _object_alias(
            payload,
            "paused_session_automatic_loop_followup_checkpoint",
            "paused-session-automatic-loop-followup-checkpoint",
            "pausedSessionAutomaticLoopFollowupCheckpoint",
            "paused_session_automatic_loop_execution_followup",
            "pausedSessionAutomaticLoopExecutionFollowup",
            "automatic_loop_followup_checkpoint",
            "automaticLoopFollowupCheckpoint",
        )
        automatic_loop_next_iteration_plan = _object_alias(
            payload,
            "paused_session_automatic_loop_next_iteration_plan",
            "paused-session-automatic-loop-next-iteration-plan",
            "pausedSessionAutomaticLoopNextIterationPlan",
            "plan_next_paused_session_automatic_loop_iteration",
            "planNextPausedSessionAutomaticLoopIteration",
            "review_next_paused_session_automatic_loop_iteration",
            "reviewNextPausedSessionAutomaticLoopIteration",
            "automatic_loop_next_iteration_plan",
            "automaticLoopNextIterationPlan",
        )
        automatic_loop_next_iteration_execution = _object_alias(
            payload,
            "paused_session_automatic_loop_next_iteration_execution",
            "paused-session-automatic-loop-next-iteration-execution",
            "pausedSessionAutomaticLoopNextIterationExecution",
            "execute_paused_session_automatic_loop_next_iteration",
            "executePausedSessionAutomaticLoopNextIteration",
            "execute_next_paused_session_automatic_loop_iteration",
            "executeNextPausedSessionAutomaticLoopIteration",
            "automatic_loop_next_iteration_execution",
            "automaticLoopNextIterationExecution",
        )
        automatic_loop_next_iteration_followup_checkpoint = _object_alias(
            payload,
            "paused_session_automatic_loop_next_iteration_followup_checkpoint",
            "paused-session-automatic-loop-next-iteration-followup-checkpoint",
            "pausedSessionAutomaticLoopNextIterationFollowupCheckpoint",
            "paused_session_automatic_loop_next_iteration_execution_followup",
            "pausedSessionAutomaticLoopNextIterationExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_next_iteration_execution",
            "checkpointPausedSessionAutomaticLoopNextIterationExecution",
            "automatic_loop_next_iteration_followup_checkpoint",
            "automaticLoopNextIterationFollowupCheckpoint",
        )
        automatic_loop_following_iteration_plan = _object_alias(
            payload,
            "paused_session_automatic_loop_following_iteration_plan",
            "paused-session-automatic-loop-following-iteration-plan",
            "pausedSessionAutomaticLoopFollowingIterationPlan",
            "plan_following_paused_session_automatic_loop_iteration",
            "planFollowingPausedSessionAutomaticLoopIteration",
            "review_following_paused_session_automatic_loop_iteration",
            "reviewFollowingPausedSessionAutomaticLoopIteration",
            "automatic_loop_following_iteration_plan",
            "automaticLoopFollowingIterationPlan",
        )

        preflight = _first_object(
            live_preflight.get("preflight"),
            live_preflight,
            session.get("continuation_preflight"),
            timeline.get("continuation_preflight"),
            paused.get("continuation_preflight"),
            payload.get("continuation_preflight"),
        )
        session_status = _string(session.get("status") or payload.get("status"))
        paused_status = _string(paused.get("status") or paused.get("reason") or paused.get("state"))
        preflight_status = _string(preflight.get("status"))
        preflight_source = _string(preflight.get("source"))
        requested_action = _string(preflight.get("requested_action") or session.get("requested_action") or payload.get("requested_action"))
        live_continuation_available = _boolish(preflight.get("live_continuation_available"))
        live_session_diagnostics = preflight.get("live_session_diagnostics") if isinstance(preflight.get("live_session_diagnostics"), dict) else {}
        target_diagnostics = preflight.get("target_diagnostics") if isinstance(preflight.get("target_diagnostics"), dict) else {}
        callframe_diagnostics = preflight.get("callframe_diagnostics") if isinstance(preflight.get("callframe_diagnostics"), dict) else {}
        action_capability = preflight.get("action_capability") if isinstance(preflight.get("action_capability"), dict) else {}
        readiness = _first_object(target_attach_readiness.get("readiness"), target_attach_readiness)
        target_correlation = readiness.get("target_correlation") if isinstance(readiness.get("target_correlation"), dict) else {}
        attachability = readiness.get("attachability") if isinstance(readiness.get("attachability"), dict) else {}
        callframe_recovery = readiness.get("callframe_recovery") if isinstance(readiness.get("callframe_recovery"), dict) else {}
        execution_plan = _first_object(cross_process_execution_plan.get("plan"), cross_process_execution_plan)
        session_lifecycle = _first_object(cross_process_session_lifecycle.get("lifecycle"), cross_process_session_lifecycle)
        attach_probe = _first_object(cross_process_attach_probe.get("probe"), cross_process_attach_probe)
        callframe_recovery_artifact = _first_object(live_callframe_recovery.get("recovery"), live_callframe_recovery)
        one_action_execution = _first_object(cross_process_one_action.get("execution"), cross_process_one_action)
        pre_action_orchestration = _first_object(pre_action_subscribe_and_action.get("orchestration"), pre_action_subscribe_and_action)
        next_capture_plan = _first_object(next_paused_event_capture_plan.get("plan"), next_paused_event_capture_plan)
        next_capture_execution = _first_object(next_paused_event_capture_execution.get("execution"), next_paused_event_capture_execution)
        continuation_checkpoint = _first_object(cross_process_continuation_checkpoint.get("checkpoint"), cross_process_continuation_checkpoint)
        multi_step_workflow = _first_object(multi_step_continuation_workflow.get("workflow"), multi_step_continuation_workflow)
        multi_step_execution = _first_object(multi_step_continuation_execution.get("execution"), multi_step_continuation_execution)
        multi_step_loop = _first_object(multi_step_loop_plan.get("loop_plan"), multi_step_loop_plan)
        multi_step_loop_exec = _first_object(multi_step_loop_execution.get("execution"), multi_step_loop_execution)
        automatic_loop_execution = _first_object(automatic_loop_execution_plan.get("plan"), automatic_loop_execution_plan)
        automatic_loop_preflight = _first_object(automatic_loop_executor_preflight.get("preflight"), automatic_loop_executor_preflight)
        automatic_loop_approval = _first_object(automatic_loop_executor_approval_plan.get("approval_plan"), automatic_loop_executor_approval_plan)
        automatic_loop_result = _first_object(automatic_loop_execution_result.get("execution"), automatic_loop_execution_result)
        automatic_loop_followup = _first_object(automatic_loop_followup_checkpoint.get("checkpoint"), automatic_loop_followup_checkpoint)
        automatic_loop_next_iteration = _first_object(automatic_loop_next_iteration_plan.get("plan"), automatic_loop_next_iteration_plan)
        automatic_loop_next_iteration_result = _first_object(automatic_loop_next_iteration_execution.get("execution"), automatic_loop_next_iteration_execution)
        automatic_loop_next_iteration_followup = _first_object(automatic_loop_next_iteration_followup_checkpoint.get("checkpoint"), automatic_loop_next_iteration_followup_checkpoint)
        automatic_loop_following_iteration = _first_object(automatic_loop_following_iteration_plan.get("plan"), automatic_loop_following_iteration_plan)
        execution_plan_target = execution_plan.get("target_attach_readiness_summary") if isinstance(execution_plan.get("target_attach_readiness_summary"), dict) else {}
        execution_plan_callframe = execution_plan.get("callframe_recovery_plan") if isinstance(execution_plan.get("callframe_recovery_plan"), dict) else {}
        execution_plan_gates = execution_plan.get("review_gates") if isinstance(execution_plan.get("review_gates"), dict) else {}

        artifact_count = sum(bool(item) for item in (session, timeline, paused, live_preflight, target_attach_readiness, cross_process_execution_plan, cross_process_session_lifecycle, cross_process_attach_probe, live_callframe_recovery, cross_process_one_action, pre_action_subscribe_and_action, next_paused_event_capture_plan, next_paused_event_capture_execution, cross_process_continuation_checkpoint, multi_step_continuation_workflow, multi_step_continuation_execution, multi_step_loop_plan, multi_step_loop_execution, automatic_loop_readiness, automatic_loop_execution_plan, automatic_loop_executor_preflight, automatic_loop_executor_approval_plan, automatic_loop_execution_result, automatic_loop_followup_checkpoint, automatic_loop_next_iteration_plan, automatic_loop_next_iteration_execution, automatic_loop_next_iteration_followup_checkpoint, automatic_loop_following_iteration_plan)) + sum(bool(items) for items in (callframes, evaluations, mutation_audit, actions, timeline_entries))
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_count:
            warnings.append("no_debugger_artifacts_provided")
        if preflight_status == "action_blocked":
            blockers.append("paused_session_action_blocked")
        if preflight_status == "blocked":
            blockers.append("paused_session_live_preflight_blocked")
        if session_status in {"failed", "failure", "error", "unsupported"}:
            blockers.append("debugger_artifact_reports_failure")
        if paused_status in {"failed", "failure", "error", "unsupported"}:
            blockers.append("debugger_pause_reports_failure")
        if preflight_status == "inspect_only":
            warnings.append("durable_snapshot_is_inspect_only")
        if preflight_status == "unavailable":
            warnings.append("paused_session_unavailable")
        if readiness.get("status") == "blocked":
            blockers.append("paused_session_target_attach_readiness_blocked")
        if readiness.get("target_attach_readiness_proven") and not execution_plan:
            warnings.append("target_attach_ready_but_execution_plan_not_observed")
        if execution_plan.get("status") == "blocked":
            blockers.append("paused_session_cross_process_execution_plan_blocked")
        if execution_plan.get("execution_plan_ready_for_review") and not attach_probe:
            warnings.append("cross_process_execution_plan_ready_but_attach_probe_not_observed")
        lifecycle_status = _string(session_lifecycle.get("status"))
        if lifecycle_status == "blocked":
            blockers.append("paused_session_cross_process_session_lifecycle_blocked")
        if lifecycle_status == "ready_for_review":
            warnings.append("cross_process_session_lifecycle_requires_review")
        attach_probe_status = _string(attach_probe.get("status"))
        if attach_probe_status == "blocked":
            blockers.append("paused_session_cross_process_attach_probe_blocked")
        if attach_probe_status == "failed":
            blockers.append("paused_session_cross_process_attach_probe_failed")
        if attach_probe_status == "ready_for_review":
            warnings.append("cross_process_attach_probe_requires_review_approval")
        if attach_probe_status == "review_required":
            warnings.append("cross_process_attach_probe_review_required")
        if attach_probe_status == "attached" and not _boolish(attach_probe.get("live_callframe_recovered")):
            warnings.append("attach_probe_ready_but_live_callframe_recovery_not_observed")
        recovery_status = _string(callframe_recovery_artifact.get("status"))
        one_action_status = _string(one_action_execution.get("status"))
        if recovery_status == "blocked":
            blockers.append("paused_session_live_callframe_recovery_blocked")
        if recovery_status == "recovered" and not one_action_execution:
            warnings.append("live_callframe_recovered_one_action_not_observed")
        if one_action_status in {"blocked", "failed"}:
            blockers.append("paused_session_cross_process_one_action_execution_blocked")
        if one_action_status == "ready_for_review":
            warnings.append("cross_process_one_action_requires_review_approval")
        if one_action_status == "review_required":
            warnings.append("cross_process_one_action_review_required")
        if one_action_status == "executed":
            warnings.append("cross_process_one_action_executed_review_result")
            method = _string(one_action_execution.get("method"))
            if method in {"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"} and not next_capture_plan and not pre_action_orchestration:
                warnings.append("cross_process_one_action_next_paused_event_capture_plan_not_observed")
        pre_action_status = _string(pre_action_orchestration.get("status"))
        if pre_action_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_pre_action_subscribe_and_action_blocked")
        if pre_action_status == "ready_for_review":
            warnings.append("pre_action_subscribe_and_action_requires_review")
        if pre_action_status == "review_required":
            warnings.append("pre_action_subscribe_and_action_review_required")
        if pre_action_status == "captured":
            if not continuation_checkpoint:
                warnings.append("pre_action_subscribe_and_action_captured_checkpoint_not_observed")
            else:
                warnings.append("pre_action_subscribe_and_action_captured_review_result")
        next_capture_status = _string(next_capture_plan.get("status"))
        if next_capture_status == "blocked":
            blockers.append("paused_session_next_paused_event_capture_plan_blocked")
        if next_capture_status == "ready_for_review" and not next_capture_execution:
            warnings.append("next_paused_event_capture_plan_requires_review")
        next_capture_execution_status = _string(next_capture_execution.get("status"))
        if next_capture_execution_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_next_paused_event_capture_execution_blocked")
        if next_capture_execution_status == "ready_for_review":
            warnings.append("next_paused_event_capture_execution_requires_review")
        if next_capture_execution_status == "review_required":
            warnings.append("next_paused_event_capture_execution_review_required")
        if next_capture_execution_status == "captured":
            if not continuation_checkpoint:
                warnings.append("next_paused_event_captured_continuation_checkpoint_not_observed")
            else:
                warnings.append("next_paused_event_captured_recover_live_callframe")
        continuation_checkpoint_status = _string(continuation_checkpoint.get("status"))
        if continuation_checkpoint_status == "blocked":
            blockers.append("paused_session_cross_process_continuation_checkpoint_blocked")
        if continuation_checkpoint_status == "ready_for_live_callframe_recovery":
            warnings.append("cross_process_continuation_checkpoint_requires_live_callframe_recovery")
        if continuation_checkpoint_status == "ready_for_next_action_review":
            warnings.append("cross_process_continuation_checkpoint_ready_for_next_action_review")
        multi_step_workflow_status = _string(multi_step_workflow.get("status"))
        if multi_step_workflow_status == "blocked":
            blockers.append("paused_session_multi_step_continuation_workflow_blocked")
        if multi_step_workflow_status == "ready_for_review":
            warnings.append("multi_step_continuation_workflow_requires_review")
        multi_step_execution_status = _string(multi_step_execution.get("status"))
        if multi_step_execution_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_multi_step_continuation_execution_blocked")
        if multi_step_execution_status == "ready_for_review":
            warnings.append("multi_step_continuation_execution_requires_review")
        if multi_step_execution_status == "review_required":
            warnings.append("multi_step_continuation_execution_review_required")
        if multi_step_execution_status == "executed":
            if _boolish(multi_step_execution.get("paused_event_captured")) and not continuation_checkpoint:
                warnings.append("multi_step_continuation_execution_checkpoint_not_observed")
            else:
                warnings.append("multi_step_continuation_execution_review_result")
        multi_step_loop_status = _string(multi_step_loop.get("status"))
        if multi_step_loop_status == "blocked":
            blockers.append("paused_session_multi_step_loop_plan_blocked")
        if multi_step_loop_status == "ready_for_review":
            warnings.append("multi_step_loop_plan_requires_review")
        multi_step_loop_execution_status = _string(multi_step_loop_exec.get("status"))
        if multi_step_loop_execution_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_multi_step_loop_execution_blocked")
        if multi_step_loop_execution_status == "ready_for_review":
            warnings.append("multi_step_loop_execution_requires_review")
        if multi_step_loop_execution_status == "review_required":
            warnings.append("multi_step_loop_execution_review_required")
        if multi_step_loop_execution_status == "executed":
            if _boolish(multi_step_loop_exec.get("paused_event_captured")) and not continuation_checkpoint:
                warnings.append("multi_step_loop_execution_checkpoint_not_observed")
            else:
                warnings.append("multi_step_loop_execution_review_result")
        automatic_loop_readiness_status = _string(automatic_loop_readiness.get("status"))
        if automatic_loop_readiness_status == "blocked":
            blockers.append("paused_session_automatic_loop_readiness_blocked")
        if automatic_loop_readiness_status == "ready_for_review":
            warnings.append("automatic_loop_readiness_requires_review")
        automatic_loop_execution_plan_status = _string(automatic_loop_execution.get("status"))
        if automatic_loop_execution_plan_status == "blocked":
            blockers.append("paused_session_automatic_loop_execution_plan_blocked")
        if automatic_loop_execution_plan_status == "ready_for_review":
            warnings.append("automatic_loop_execution_plan_requires_review")
        automatic_loop_executor_preflight_status = _string(automatic_loop_preflight.get("status"))
        if automatic_loop_executor_preflight_status == "blocked":
            blockers.append("paused_session_automatic_loop_executor_preflight_blocked")
        if automatic_loop_executor_preflight_status == "ready_for_review":
            warnings.append("automatic_loop_executor_preflight_requires_review")
        automatic_loop_executor_approval_plan_status = _string(automatic_loop_approval.get("status"))
        if automatic_loop_executor_approval_plan_status == "blocked":
            blockers.append("paused_session_automatic_loop_executor_approval_plan_blocked")
        if automatic_loop_executor_approval_plan_status == "ready_for_review":
            warnings.append("automatic_loop_executor_approval_plan_requires_review")
        automatic_loop_result_status = _string(automatic_loop_result.get("status"))
        if automatic_loop_result_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_automatic_loop_execution_result_blocked")
        if automatic_loop_result_status == "ready_for_review":
            warnings.append("automatic_loop_execution_requires_review")
        if automatic_loop_result_status == "review_required":
            warnings.append("automatic_loop_execution_review_required")
        if automatic_loop_result_status == "executed":
            if _boolish(automatic_loop_result.get("checkpoint_required")) and not continuation_checkpoint:
                warnings.append("automatic_loop_execution_checkpoint_required")
            else:
                warnings.append("automatic_loop_execution_review_result")
        automatic_loop_followup_status = _string(automatic_loop_followup.get("status"))
        if automatic_loop_followup_status == "blocked":
            blockers.append("paused_session_automatic_loop_followup_checkpoint_blocked")
        if automatic_loop_followup_status == "ready_for_review" and not automatic_loop_next_iteration:
            next_loop_review = automatic_loop_followup.get("next_loop_review") if isinstance(automatic_loop_followup.get("next_loop_review"), dict) else {}
            if _boolish(next_loop_review.get("next_loop_plan_ready")):
                warnings.append("automatic_loop_followup_checkpoint_ready_for_next_loop_review")
            else:
                warnings.append("automatic_loop_followup_checkpoint_requires_next_loop_plan")
        automatic_loop_next_iteration_status = _string(automatic_loop_next_iteration.get("status"))
        if automatic_loop_next_iteration_status == "blocked":
            blockers.append("paused_session_automatic_loop_next_iteration_plan_blocked")
        if automatic_loop_next_iteration_status == "ready_for_review" and not automatic_loop_next_iteration_result:
            warnings.append("automatic_loop_next_iteration_plan_requires_execution_review")
        automatic_loop_next_iteration_result_status = _string(automatic_loop_next_iteration_result.get("status"))
        if automatic_loop_next_iteration_result_status in {"blocked", "failed", "timed_out"}:
            blockers.append("paused_session_automatic_loop_next_iteration_execution_blocked")
        if automatic_loop_next_iteration_result_status == "ready_for_review":
            warnings.append("automatic_loop_next_iteration_execution_requires_review")
        if automatic_loop_next_iteration_result_status == "review_required":
            warnings.append("automatic_loop_next_iteration_execution_review_required")
        if automatic_loop_next_iteration_result_status == "executed":
            if _boolish(automatic_loop_next_iteration_result.get("checkpoint_required")) and not continuation_checkpoint:
                warnings.append("automatic_loop_next_iteration_execution_checkpoint_required")
            else:
                warnings.append("automatic_loop_next_iteration_execution_review_result")
        automatic_loop_next_iteration_followup_status = _string(automatic_loop_next_iteration_followup.get("status"))
        if automatic_loop_next_iteration_followup_status == "blocked":
            blockers.append("paused_session_automatic_loop_next_iteration_followup_checkpoint_blocked")
        if automatic_loop_next_iteration_followup_status == "ready_for_review":
            next_loop_review = automatic_loop_next_iteration_followup.get("next_loop_review") if isinstance(automatic_loop_next_iteration_followup.get("next_loop_review"), dict) else {}
            if _boolish(next_loop_review.get("next_loop_plan_ready")):
                warnings.append("automatic_loop_next_iteration_followup_checkpoint_ready_for_next_loop_review")
            else:
                warnings.append("automatic_loop_next_iteration_followup_checkpoint_requires_next_loop_plan")
        automatic_loop_following_iteration_status = _string(automatic_loop_following_iteration.get("status"))
        if automatic_loop_following_iteration_status == "blocked":
            blockers.append("paused_session_automatic_loop_following_iteration_plan_blocked")
        if automatic_loop_following_iteration_status == "ready_for_review":
            warnings.append("automatic_loop_following_iteration_plan_requires_execution_review")
        if _looks_paused(paused, session, timeline) and not callframes:
            warnings.append("paused_session_has_no_callframes")
        if requested_action in _LIVE_ACTIONS and not live_continuation_available:
            warnings.append("live_continuation_not_available_for_requested_action")

        status = "block" if blockers else "warn" if warnings else "pass"
        return {
            "version": DEBUGGER_ARTIFACT_REVIEW_VERSION,
            "status": status,
            "blocked": bool(blockers),
            "warnings_present": bool(warnings),
            "next_action": _next_action(status, blockers, warnings, requested_action, live_continuation_available),
            "artifact_input": summarize_workspace_artifact_read(artifact_read),
            "summary": {
                "artifact_count": artifact_count,
                "session_id": _string(session.get("session_id") or session.get("pause_session_id") or payload.get("session_id")),
                "session_status": session_status or "unknown",
                "paused_status": paused_status or "unknown",
                "preflight_status": preflight_status or "unknown",
                "preflight_source": preflight_source or "unknown",
                "preflight_reason": _string(preflight.get("reason") or preflight.get("blocked_reason")),
                "requested_action": requested_action or "unknown",
                "live_continuation_available": live_continuation_available,
                "callframe_count": len(callframes),
                "top_callframes": _top_callframes(callframes),
                "callframe_evaluation_count": len(evaluations),
                "mutation_audit_count": len(mutation_audit),
                "debugger_action_count": len(actions),
                "timeline_entry_count": _timeline_entry_count(timeline, timeline_entries),
                "timeline_event_counts": _timeline_event_counts(timeline_entries),
                "cross_process_live_continuation_supported": _boolish(preflight.get("cross_process_live_continuation_supported")),
                "preflight_blockers": preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else [],
                "live_session_diagnostics": {
                    "live_session_available": _boolish(live_session_diagnostics.get("live_session_available")),
                    "debugger_session_lifecycle": _string(live_session_diagnostics.get("debugger_session_lifecycle") or "unknown"),
                    "same_process_required_for_live_action": _boolish(live_session_diagnostics.get("same_process_required_for_live_action")),
                    "cross_process_resume_supported": _boolish(live_session_diagnostics.get("cross_process_resume_supported")),
                    "cross_process_step_supported": _boolish(live_session_diagnostics.get("cross_process_step_supported")),
                    "cross_process_evaluate_supported": _boolish(live_session_diagnostics.get("cross_process_evaluate_supported")),
                },
                "target_diagnostics": {
                    "target_attached": _boolish(target_diagnostics.get("target_attached")),
                    "cdp_target_available": _boolish(target_diagnostics.get("cdp_target_available")),
                    "target_attached_source": _string(target_diagnostics.get("target_attached_source") or "unknown"),
                    "cdp_target_available_source": _string(target_diagnostics.get("cdp_target_available_source") or "unknown"),
                },
                "callframe_diagnostics": {
                    "stable_callframe_required": _boolish(callframe_diagnostics.get("stable_callframe_required")),
                    "stable_callframe_available": _boolish(callframe_diagnostics.get("stable_callframe_available")),
                    "selected_callframe_has_id": _boolish(callframe_diagnostics.get("selected_callframe_has_id")),
                    "callframe_count": callframe_diagnostics.get("callframe_count", len(callframes)),
                },
                "action_capability": {
                    "requested_action": _string(action_capability.get("requested_action") or requested_action or "unknown"),
                    "is_live_action": _boolish(action_capability.get("is_live_action")),
                    "inspect_supported": _boolish(action_capability.get("inspect_supported")),
                    "evaluate_supported": _boolish(action_capability.get("evaluate_supported")),
                    "step_supported": _boolish(action_capability.get("step_supported")),
                    "resume_supported": _boolish(action_capability.get("resume_supported")),
                },
                "target_attach_readiness": {
                    "status": _string(readiness.get("status") or "unknown"),
                    "source": _string(readiness.get("source") or "unknown"),
                    "target_attach_readiness_proven": _boolish(readiness.get("target_attach_readiness_proven")),
                    "cross_process_live_continuation_supported": _boolish(readiness.get("cross_process_live_continuation_supported")),
                    "cross_process_execution_ready": _boolish(readiness.get("cross_process_execution_ready")),
                    "blockers": readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else [],
                    "expected_url": _string(target_correlation.get("expected_url")),
                    "candidate_count": target_correlation.get("candidate_count", 0),
                    "url_match": _boolish(target_correlation.get("url_match")),
                    "target_id_available": _boolish(attachability.get("target_id_available")),
                    "would_attach_cdp_target": _boolish(attachability.get("would_attach_cdp_target")),
                    "stable_live_callframe_available": _boolish(callframe_recovery.get("stable_live_callframe_available")),
                    "requires_new_paused_event_after_attach": _boolish(callframe_recovery.get("requires_new_paused_event_after_attach")),
                },
                "cross_process_execution_plan": {
                    "status": _string(execution_plan.get("status") or "unknown"),
                    "pause_session_id": _string(execution_plan.get("pause_session_id")),
                    "requested_action": _string(execution_plan.get("requested_action") or "unknown"),
                    "execution_plan_ready_for_review": _boolish(execution_plan.get("execution_plan_ready_for_review")),
                    "cross_process_execution_ready": _boolish(execution_plan.get("cross_process_execution_ready")),
                    "cross_process_executor_implemented": _boolish(execution_plan.get("cross_process_executor_implemented")),
                    "cross_process_action_supported": _boolish(execution_plan.get("cross_process_action_supported")),
                    "target_attach_readiness_proven": _boolish(execution_plan.get("target_attach_readiness_proven")),
                    "target_id_available": _boolish(execution_plan_target.get("target_id_available")),
                    "requires_new_paused_event_after_attach": _boolish(execution_plan_callframe.get("requires_new_paused_event_after_attach")),
                    "attach_probe_review_required": _boolish(execution_plan_gates.get("attach_probe_review_required")),
                    "action_execution_review_required": _boolish(execution_plan_gates.get("action_execution_review_required")),
                    "blockers": execution_plan.get("blockers") if isinstance(execution_plan.get("blockers"), list) else [],
                },
                "cross_process_session_lifecycle": {
                    "status": _string(session_lifecycle.get("status") or "unknown"),
                    "ready_for_review": _boolish(session_lifecycle.get("ready_for_review")),
                    "pause_session_id": _string(session_lifecycle.get("pause_session_id")),
                    "target_id": _string(session_lifecycle.get("target_id")),
                    "requested_action": _string(session_lifecycle.get("requested_action") or "unknown"),
                    "attached_session_retained": _boolish(_nested_get(session_lifecycle, "session_diagnostics", "attached_session_retained")),
                    "target_still_alive_proven": _boolish(_nested_get(session_lifecycle, "target_diagnostics", "target_still_alive_proven")),
                    "target_still_alive_proof_requires_cdp_probe": _boolish(_nested_get(session_lifecycle, "target_diagnostics", "target_still_alive_proof_requires_cdp_probe")),
                    "live_callframe_recovered": _boolish(_nested_get(session_lifecycle, "debugger_diagnostics", "live_callframe_recovered")),
                    "live_callframe_id_present": _boolish(_nested_get(session_lifecycle, "debugger_diagnostics", "live_callframe_id_present")),
                    "automatic_multi_step_loop_supported": _boolish(_nested_get(session_lifecycle, "continuation_diagnostics", "automatic_multi_step_loop_supported")),
                    "automatic_wrapper_continuation_supported": _boolish(_nested_get(session_lifecycle, "continuation_diagnostics", "automatic_wrapper_continuation_supported")),
                    "next_action": _string(session_lifecycle.get("next_action")),
                    "blockers": session_lifecycle.get("blockers") if isinstance(session_lifecycle.get("blockers"), list) else [],
                },
                "cross_process_attach_probe": {
                    "status": _string(attach_probe.get("status") or "unknown"),
                    "pause_session_id": _string(attach_probe.get("pause_session_id")),
                    "requested_action": _string(attach_probe.get("requested_action") or "unknown"),
                    "target_id": _string(attach_probe.get("target_id")),
                    "attach_attempted": _boolish(attach_probe.get("attach_attempted")),
                    "target_attached": _boolish(attach_probe.get("target_attached")),
                    "target_detached": _boolish(attach_probe.get("target_detached")),
                    "debugger_domain_enabled": _boolish(attach_probe.get("debugger_domain_enabled")),
                    "live_callframe_recovered": _boolish(attach_probe.get("live_callframe_recovered")),
                    "live_action_executed": _boolish(attach_probe.get("live_action_executed")),
                    "browser_resumed": _boolish(attach_probe.get("browser_resumed")),
                    "debugger_stepped": _boolish(attach_probe.get("debugger_stepped")),
                    "callframe_evaluated": _boolish(attach_probe.get("callframe_evaluated")),
                    "cdp_methods": attach_probe.get("cdp_methods") if isinstance(attach_probe.get("cdp_methods"), list) else [],
                    "blockers": attach_probe.get("blockers") if isinstance(attach_probe.get("blockers"), list) else [],
                },
                "live_callframe_recovery": {
                    "status": _string(callframe_recovery_artifact.get("status") or "unknown"),
                    "pause_session_id": _string(callframe_recovery_artifact.get("pause_session_id")),
                    "requested_action": _string(callframe_recovery_artifact.get("requested_action") or "unknown"),
                    "target_id": _string(callframe_recovery_artifact.get("target_id")),
                    "attach_probe_status": _string(callframe_recovery_artifact.get("attach_probe_status") or "unknown"),
                    "target_attached": _boolish(callframe_recovery_artifact.get("target_attached")),
                    "fresh_paused_event_after_attach": _boolish(callframe_recovery_artifact.get("fresh_paused_event_after_attach")),
                    "callframe_count": callframe_recovery_artifact.get("callframe_count", 0),
                    "selected_callframe_has_id": _boolish(callframe_recovery_artifact.get("selected_callframe_has_id")),
                    "live_callframe_recovered": _boolish(callframe_recovery_artifact.get("live_callframe_recovered")),
                    "one_action_executor_ready_for_review": _boolish(callframe_recovery_artifact.get("one_action_executor_ready_for_review")),
                    "debugger_domain_enabled": _boolish(callframe_recovery_artifact.get("debugger_domain_enabled")),
                    "live_action_executed": _boolish(callframe_recovery_artifact.get("live_action_executed")),
                    "browser_resumed": _boolish(callframe_recovery_artifact.get("browser_resumed")),
                    "debugger_stepped": _boolish(callframe_recovery_artifact.get("debugger_stepped")),
                    "callframe_evaluated": _boolish(callframe_recovery_artifact.get("callframe_evaluated")),
                    "blockers": callframe_recovery_artifact.get("blockers") if isinstance(callframe_recovery_artifact.get("blockers"), list) else [],
                },
                "cross_process_one_action_execution": {
                    "status": _string(one_action_execution.get("status") or "unknown"),
                    "pause_session_id": _string(one_action_execution.get("pause_session_id")),
                    "requested_action": _string(one_action_execution.get("requested_action") or "unknown"),
                    "method": _string(one_action_execution.get("method")),
                    "target_id": _string(one_action_execution.get("target_id")),
                    "attached_session_id_present": bool(one_action_execution.get("attached_session_id")),
                    "live_callframe_id_present": bool(one_action_execution.get("live_callframe_id")),
                    "live_callframe_recovered": _boolish(one_action_execution.get("live_callframe_recovered")),
                    "live_action_executed": _boolish(one_action_execution.get("live_action_executed")),
                    "browser_resumed": _boolish(one_action_execution.get("browser_resumed")),
                    "debugger_stepped": _boolish(one_action_execution.get("debugger_stepped")),
                    "callframe_evaluated": _boolish(one_action_execution.get("callframe_evaluated")),
                    "cdp_methods": one_action_execution.get("cdp_methods") if isinstance(one_action_execution.get("cdp_methods"), list) else [],
                    "blockers": one_action_execution.get("blockers") if isinstance(one_action_execution.get("blockers"), list) else [],
                },
                "pre_action_subscribe_and_action": {
                    "status": _string(pre_action_orchestration.get("status") or "unknown"),
                    "requested_action": _string(pre_action_orchestration.get("requested_action") or "unknown"),
                    "method": _string(pre_action_orchestration.get("method")),
                    "pre_action_event_subscribed": _boolish(pre_action_orchestration.get("pre_action_event_subscribed")),
                    "action_sent_after_subscription": _boolish(pre_action_orchestration.get("action_sent_after_subscription")),
                    "live_action_executed": _boolish(pre_action_orchestration.get("live_action_executed")),
                    "paused_event_captured": _boolish(pre_action_orchestration.get("paused_event_captured")),
                    "captured_event_count": pre_action_orchestration.get("captured_event_count", 0),
                    "callframe_count": pre_action_orchestration.get("callframe_count", 0),
                    "live_callframe_recovery_ready": _boolish(pre_action_orchestration.get("live_callframe_recovery_ready")),
                    "next_action": _string(pre_action_orchestration.get("next_action")),
                    "blockers": pre_action_orchestration.get("blockers") if isinstance(pre_action_orchestration.get("blockers"), list) else [],
                },
                "next_paused_event_capture_plan": {
                    "status": _string(next_capture_plan.get("status") or "unknown"),
                    "plan_ready_for_review": _boolish(next_capture_plan.get("plan_ready_for_review")),
                    "requires_next_paused_event_capture": _boolish(next_capture_plan.get("requires_next_paused_event_capture")),
                    "automatic_capture_supported": _boolish(next_capture_plan.get("automatic_capture_supported")),
                    "method": _string(next_capture_plan.get("method")),
                    "capture_window": _string(next_capture_plan.get("capture_window")),
                    "blockers": next_capture_plan.get("blockers") if isinstance(next_capture_plan.get("blockers"), list) else [],
                },
                "next_paused_event_capture_execution": {
                    "status": _string(next_capture_execution.get("status") or "unknown"),
                    "method": _string(next_capture_execution.get("method")),
                    "debugger_event_subscribed": _boolish(next_capture_execution.get("debugger_event_subscribed")),
                    "paused_event_captured": _boolish(next_capture_execution.get("paused_event_captured")),
                    "captured_event_count": next_capture_execution.get("captured_event_count", 0),
                    "callframe_count": next_capture_execution.get("callframe_count", 0),
                    "live_callframe_recovery_ready": _boolish(next_capture_execution.get("live_callframe_recovery_ready")),
                    "blockers": next_capture_execution.get("blockers") if isinstance(next_capture_execution.get("blockers"), list) else [],
                },
                "cross_process_continuation_checkpoint": {
                    "status": _string(continuation_checkpoint.get("status") or "unknown"),
                    "pause_session_id": _string(continuation_checkpoint.get("pause_session_id")),
                    "target_id": _string(continuation_checkpoint.get("target_id")),
                    "paused_event_captured": _boolish(continuation_checkpoint.get("paused_event_captured")),
                    "callframe_count": continuation_checkpoint.get("callframe_count", 0),
                    "selected_callframe_id_present": bool(continuation_checkpoint.get("selected_callframe_id")),
                    "live_callframe_recovered": _boolish(continuation_checkpoint.get("live_callframe_recovered")),
                    "continuation_ready_for_next_action": _boolish(continuation_checkpoint.get("continuation_ready_for_next_action")),
                    "continuation_ready_for_next_capture_plan": _boolish(continuation_checkpoint.get("continuation_ready_for_next_capture_plan")),
                    "manual_checkpoint_required": _boolish(continuation_checkpoint.get("manual_checkpoint_required")),
                    "next_action": _string(continuation_checkpoint.get("next_action")),
                    "blockers": continuation_checkpoint.get("blockers") if isinstance(continuation_checkpoint.get("blockers"), list) else [],
                },
                "multi_step_continuation_workflow": {
                    "status": _string(multi_step_workflow.get("status") or "unknown"),
                    "workflow_id": _string(multi_step_workflow.get("workflow_id")),
                    "planned_step_count": multi_step_workflow.get("planned_step_count", 0),
                    "max_planned_steps": multi_step_workflow.get("max_planned_steps", 0),
                    "execute_at_most_one_action_per_review": _boolish(multi_step_workflow.get("execute_at_most_one_action_per_review")),
                    "manual_checkpoint_required_after_each_step": _boolish(multi_step_workflow.get("manual_checkpoint_required_after_each_step")),
                    "automatic_loop": _boolish(multi_step_workflow.get("automatic_loop")),
                    "duplicate_fingerprints": multi_step_workflow.get("duplicate_fingerprints") if isinstance(multi_step_workflow.get("duplicate_fingerprints"), list) else [],
                    "blockers": multi_step_workflow.get("blockers") if isinstance(multi_step_workflow.get("blockers"), list) else [],
                },
                "multi_step_continuation_execution": {
                    "status": _string(multi_step_execution.get("status") or "unknown"),
                    "workflow_id": _string(multi_step_execution.get("workflow_id")),
                    "selected_step_index": multi_step_execution.get("selected_step_index"),
                    "selected_method": _string(multi_step_execution.get("selected_method")),
                    "executor_artifact": _string(multi_step_execution.get("executor_artifact")),
                    "paused_event_captured": _boolish(multi_step_execution.get("paused_event_captured")),
                    "manual_checkpoint_required_after_step": _boolish(multi_step_execution.get("manual_checkpoint_required_after_step")),
                    "multi_step_iteration_executed": _boolish(multi_step_execution.get("multi_step_iteration_executed")),
                    "automatic_loop": _boolish(multi_step_execution.get("automatic_loop")),
                    "blockers": multi_step_execution.get("blockers") if isinstance(multi_step_execution.get("blockers"), list) else [],
                },
                "multi_step_loop_plan": {
                    "status": _string(multi_step_loop.get("status") or "unknown"),
                    "loop_id": _string(multi_step_loop.get("loop_id")),
                    "workflow_id": _string(multi_step_loop.get("workflow_id")),
                    "completed_iteration_count": multi_step_loop.get("completed_iteration_count", 0),
                    "remaining_iteration_count": multi_step_loop.get("remaining_iteration_count", 0),
                    "planned_iteration_count": multi_step_loop.get("planned_iteration_count", 0),
                    "ready_for_review": _boolish(multi_step_loop.get("ready_for_review")),
                    "next_iteration_reviewable": _boolish(_nested_get(multi_step_loop, "readiness", "next_loop_iteration_reviewable")),
                    "automatic_multi_step_loop_supported": _boolish(_nested_get(multi_step_loop, "readiness", "automatic_multi_step_loop_supported")),
                    "next_action": _string(multi_step_loop.get("next_action")),
                    "blockers": multi_step_loop.get("blockers") if isinstance(multi_step_loop.get("blockers"), list) else [],
                },
                "multi_step_loop_execution": {
                    "status": _string(multi_step_loop_exec.get("status") or "unknown"),
                    "loop_id": _string(multi_step_loop_exec.get("loop_id")),
                    "workflow_id": _string(multi_step_loop_exec.get("workflow_id")),
                    "selected_step_index": multi_step_loop_exec.get("selected_step_index"),
                    "selected_method": _string(multi_step_loop_exec.get("selected_method")),
                    "executor_artifact": _string(multi_step_loop_exec.get("executor_artifact")),
                    "paused_event_captured": _boolish(multi_step_loop_exec.get("paused_event_captured")),
                    "manual_checkpoint_required_after_iteration": _boolish(multi_step_loop_exec.get("manual_checkpoint_required_after_iteration")),
                    "multi_step_loop_iteration_executed": _boolish(multi_step_loop_exec.get("multi_step_loop_iteration_executed")),
                    "loop_advanced": _boolish(multi_step_loop_exec.get("loop_advanced")),
                    "queue_advanced": _boolish(multi_step_loop_exec.get("queue_advanced")),
                    "automatic_multi_step_loop": _boolish(multi_step_loop_exec.get("automatic_multi_step_loop")),
                    "automatic_wrapper_continuation": _boolish(multi_step_loop_exec.get("automatic_wrapper_continuation")),
                    "blockers": multi_step_loop_exec.get("blockers") if isinstance(multi_step_loop_exec.get("blockers"), list) else [],
                },
                "automatic_loop_readiness": {
                    "status": _string(automatic_loop_readiness.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_readiness.get("ready_for_review")),
                    "automation_executor_implemented": _boolish(automatic_loop_readiness.get("automation_executor_implemented")),
                    "automatic_multi_step_loop_supported": _boolish(automatic_loop_readiness.get("automatic_multi_step_loop_supported")),
                    "candidate_iteration_count": automatic_loop_readiness.get("candidate_iteration_count", 0),
                    "max_automatic_iterations": automatic_loop_readiness.get("max_automatic_iterations", 0),
                    "next_action": _string(automatic_loop_readiness.get("next_action")),
                    "blockers": automatic_loop_readiness.get("blockers") if isinstance(automatic_loop_readiness.get("blockers"), list) else [],
                },
                "automatic_loop_execution_plan": {
                    "status": _string(automatic_loop_execution.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_execution.get("ready_for_review")),
                    "execution_plan_ready_for_review": _boolish(automatic_loop_execution.get("execution_plan_ready_for_review")),
                    "planned_iteration_count": automatic_loop_execution.get("planned_iteration_count", 0),
                    "max_planned_iterations": automatic_loop_execution.get("max_planned_iterations", 0),
                    "future_executor_implemented": _boolish(_nested_get(automatic_loop_execution, "future_executor_contract", "implemented")),
                    "next_action": _string(automatic_loop_execution.get("next_action")),
                    "blockers": automatic_loop_execution.get("blockers") if isinstance(automatic_loop_execution.get("blockers"), list) else [],
                },
                "automatic_loop_executor_preflight": {
                    "status": _string(automatic_loop_preflight.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_preflight.get("ready_for_review")),
                    "executor_preflight_ready_for_review": _boolish(automatic_loop_preflight.get("executor_preflight_ready_for_review")),
                    "ready_to_execute_now": _boolish(_nested_get(automatic_loop_preflight, "executor_input_gates", "ready_to_execute_now")),
                    "preflight_iteration_count": automatic_loop_preflight.get("preflight_iteration_count", 0),
                    "max_preflight_iterations": automatic_loop_preflight.get("max_preflight_iterations", 0),
                    "future_executor_implemented": _boolish(_nested_get(automatic_loop_preflight, "future_executor_contract", "implemented")),
                    "next_action": _string(automatic_loop_preflight.get("next_action")),
                    "blockers": automatic_loop_preflight.get("blockers") if isinstance(automatic_loop_preflight.get("blockers"), list) else [],
                },
                "automatic_loop_executor_approval_plan": {
                    "status": _string(automatic_loop_approval.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_approval.get("ready_for_review")),
                    "approval_plan_ready_for_review": _boolish(automatic_loop_approval.get("approval_plan_ready_for_review")),
                    "ready_to_execute_now": _boolish(_nested_get(automatic_loop_approval, "executor_input_gates", "ready_to_execute_now")),
                    "approval_recorded": _boolish(_nested_get(automatic_loop_approval, "executor_input_gates", "approval_recorded")),
                    "transaction_started": _boolish(_nested_get(automatic_loop_approval, "transaction_plan", "transaction_started")),
                    "journal_written": _boolish(_nested_get(automatic_loop_approval, "transaction_plan", "journal_written_now")),
                    "approved_iteration_count": automatic_loop_approval.get("approved_iteration_count", 0),
                    "max_approved_iterations": automatic_loop_approval.get("max_approved_iterations", 0),
                    "future_executor_implemented": _boolish(_nested_get(automatic_loop_approval, "future_executor_contract", "implemented")),
                    "next_action": _string(automatic_loop_approval.get("next_action")),
                    "blockers": automatic_loop_approval.get("blockers") if isinstance(automatic_loop_approval.get("blockers"), list) else [],
                },
                "automatic_loop_execution_result": {
                    "status": _string(automatic_loop_result.get("status") or "unknown"),
                    "transaction_id": _string(automatic_loop_result.get("transaction_id")),
                    "journal_id": _string(automatic_loop_result.get("journal_id")),
                    "executed_iteration_count": automatic_loop_result.get("executed_iteration_count", 0),
                    "checkpoint_required": _boolish(automatic_loop_result.get("checkpoint_required")),
                    "automatic_loop_executed": _boolish(automatic_loop_result.get("automatic_loop_executed")),
                    "automatic_loop_one_iteration_executed": _boolish(automatic_loop_result.get("automatic_loop_one_iteration_executed")),
                    "loop_advanced": _boolish(automatic_loop_result.get("loop_advanced")),
                    "queue_advanced": _boolish(automatic_loop_result.get("queue_advanced")),
                    "long_lived_session_managed": _boolish(automatic_loop_result.get("long_lived_session_managed")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_result, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_result, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_result.get("blockers") if isinstance(automatic_loop_result.get("blockers"), list) else [],
                },
                "automatic_loop_followup_checkpoint": {
                    "status": _string(automatic_loop_followup.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_followup.get("ready_for_review")),
                    "transaction_id": _string(automatic_loop_followup.get("transaction_id")),
                    "checkpoint_ready": _boolish(_nested_get(automatic_loop_followup, "checkpoint_review", "checkpoint_ready")),
                    "next_loop_plan_ready": _boolish(_nested_get(automatic_loop_followup, "next_loop_review", "next_loop_plan_ready")),
                    "next_iteration_reviewable": _boolish(_nested_get(automatic_loop_followup, "next_loop_review", "next_iteration_reviewable")),
                    "checkpoint_written": _boolish(_nested_get(automatic_loop_followup, "side_effect_policy", "checkpoint_written")),
                    "loop_advanced": _boolish(_nested_get(automatic_loop_followup, "side_effect_policy", "loop_advanced")),
                    "queue_advanced": _boolish(_nested_get(automatic_loop_followup, "side_effect_policy", "queue_advanced")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_followup, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_followup, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_followup.get("blockers") if isinstance(automatic_loop_followup.get("blockers"), list) else [],
                },
                "automatic_loop_next_iteration_plan": {
                    "status": _string(automatic_loop_next_iteration.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_next_iteration.get("ready_for_review")),
                    "transaction_id": _string(automatic_loop_next_iteration.get("transaction_id")),
                    "followup_checkpoint_ready": _boolish(_nested_get(automatic_loop_next_iteration, "checkpoint_review", "followup_checkpoint_ready")),
                    "continuation_checkpoint_ready": _boolish(_nested_get(automatic_loop_next_iteration, "checkpoint_review", "continuation_checkpoint_ready")),
                    "next_loop_plan_ready": _boolish(_nested_get(automatic_loop_next_iteration, "next_iteration", "next_loop_plan_ready")),
                    "next_iteration_reviewable": _boolish(_nested_get(automatic_loop_next_iteration, "next_iteration", "next_iteration_reviewable")),
                    "fresh_live_callframe_recovered": _boolish(_nested_get(automatic_loop_next_iteration, "next_iteration", "fresh_live_callframe_recovered")),
                    "would_execute_next_iteration": _boolish(_nested_get(automatic_loop_next_iteration, "side_effect_policy", "would_execute_next_iteration")),
                    "loop_advanced": _boolish(_nested_get(automatic_loop_next_iteration, "side_effect_policy", "loop_advanced")),
                    "queue_advanced": _boolish(_nested_get(automatic_loop_next_iteration, "side_effect_policy", "queue_advanced")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_next_iteration, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_next_iteration, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_next_iteration.get("blockers") if isinstance(automatic_loop_next_iteration.get("blockers"), list) else [],
                },
                "automatic_loop_next_iteration_execution": {
                    "status": _string(automatic_loop_next_iteration_result.get("status") or "unknown"),
                    "transaction_id": _string(automatic_loop_next_iteration_result.get("transaction_id")),
                    "automatic_loop_next_iteration_executed": _boolish(automatic_loop_next_iteration_result.get("automatic_loop_next_iteration_executed")),
                    "executed_iteration_count": automatic_loop_next_iteration_result.get("executed_iteration_count", 0),
                    "checkpoint_required": _boolish(automatic_loop_next_iteration_result.get("checkpoint_required")),
                    "loop_advanced": _boolish(automatic_loop_next_iteration_result.get("loop_advanced")),
                    "queue_advanced": _boolish(automatic_loop_next_iteration_result.get("queue_advanced")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_next_iteration_result, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_next_iteration_result, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_next_iteration_result.get("blockers") if isinstance(automatic_loop_next_iteration_result.get("blockers"), list) else [],
                },
                "automatic_loop_next_iteration_followup_checkpoint": {
                    "status": _string(automatic_loop_next_iteration_followup.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_next_iteration_followup.get("ready_for_review")),
                    "transaction_id": _string(automatic_loop_next_iteration_followup.get("transaction_id")),
                    "checkpoint_ready": _boolish(_nested_get(automatic_loop_next_iteration_followup, "checkpoint_review", "checkpoint_ready")),
                    "next_loop_plan_ready": _boolish(_nested_get(automatic_loop_next_iteration_followup, "next_loop_review", "next_loop_plan_ready")),
                    "next_iteration_reviewable": _boolish(_nested_get(automatic_loop_next_iteration_followup, "next_loop_review", "next_iteration_reviewable")),
                    "checkpoint_written": _boolish(_nested_get(automatic_loop_next_iteration_followup, "side_effect_policy", "checkpoint_written")),
                    "loop_advanced": _boolish(_nested_get(automatic_loop_next_iteration_followup, "side_effect_policy", "loop_advanced")),
                    "queue_advanced": _boolish(_nested_get(automatic_loop_next_iteration_followup, "side_effect_policy", "queue_advanced")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_next_iteration_followup, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_next_iteration_followup, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_next_iteration_followup.get("blockers") if isinstance(automatic_loop_next_iteration_followup.get("blockers"), list) else [],
                },
                "automatic_loop_following_iteration_plan": {
                    "status": _string(automatic_loop_following_iteration.get("status") or "unknown"),
                    "ready_for_review": _boolish(automatic_loop_following_iteration.get("ready_for_review")),
                    "transaction_id": _string(automatic_loop_following_iteration.get("transaction_id")),
                    "followup_checkpoint_ready": _boolish(_nested_get(automatic_loop_following_iteration, "checkpoint_review", "followup_checkpoint_ready")),
                    "continuation_checkpoint_ready": _boolish(_nested_get(automatic_loop_following_iteration, "checkpoint_review", "continuation_checkpoint_ready")),
                    "next_loop_plan_ready": _boolish(_nested_get(automatic_loop_following_iteration, "next_iteration", "next_loop_plan_ready")),
                    "next_iteration_reviewable": _boolish(_nested_get(automatic_loop_following_iteration, "next_iteration", "next_iteration_reviewable")),
                    "fresh_live_callframe_recovered": _boolish(_nested_get(automatic_loop_following_iteration, "next_iteration", "fresh_live_callframe_recovered")),
                    "would_execute_next_iteration": _boolish(_nested_get(automatic_loop_following_iteration, "side_effect_policy", "would_execute_next_iteration")),
                    "loop_advanced": _boolish(_nested_get(automatic_loop_following_iteration, "side_effect_policy", "loop_advanced")),
                    "queue_advanced": _boolish(_nested_get(automatic_loop_following_iteration, "side_effect_policy", "queue_advanced")),
                    "calls_mcp": _boolish(_nested_get(automatic_loop_following_iteration, "side_effect_policy", "calls_mcp")),
                    "mobile_runtime_used": _boolish(_nested_get(automatic_loop_following_iteration, "side_effect_policy", "mobile_runtime_used")),
                    "blockers": automatic_loop_following_iteration.get("blockers") if isinstance(automatic_loop_following_iteration.get("blockers"), list) else [],
                },
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(blockers, warnings, preflight, readiness, execution_plan, session_lifecycle, attach_probe, callframe_recovery_artifact, one_action_execution, pre_action_orchestration, next_capture_execution, continuation_checkpoint, multi_step_workflow, multi_step_execution, multi_step_loop, multi_step_loop_exec, automatic_loop_result, automatic_loop_followup, automatic_loop_next_iteration, automatic_loop_next_iteration_result, automatic_loop_next_iteration_followup, automatic_loop_following_iteration, session, paused),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "browser_resumed": False,
                "debugger_stepped": False,
                "callframe_evaluated": False,
                "runtime_mutated": False,
                "cdp_command_sent": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
                "delivery_executed": False,
            },
        }

    review_debugger_artifacts.__name__ = "review_debugger_artifacts"
    return review_debugger_artifacts


def make_record_paused_session_automatic_loop_executor_approval_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit approval-record writer for future automatic-loop execution.

    The tool only records reviewer approval metadata for a ready approval-plan
    descriptor. It never sends CDP commands, resumes debugger state, evaluates
    callframes, executes continuation steps, starts transactions, writes executor
    journals, calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_paused_session_automatic_loop_executor_approval(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        reviewer: str | None = None,
        decision: str = "approved",
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_approval_record: bool = False,
        expected_approval_plan_id: str | None = None,
        expected_preflight_id: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record reviewer approval for a ready automatic-loop executor approval plan."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_paused_session_automatic_loop_executor_approval_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            reviewer=reviewer,
            decision=decision,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_approval_record=approve_approval_record,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_preflight_id=expected_preflight_id,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_paused_session_automatic_loop_executor_approval.__name__ = "record_paused_session_automatic_loop_executor_approval"
    return record_paused_session_automatic_loop_executor_approval


def make_review_paused_session_automatic_loop_transaction_preflight_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only transaction / journal preflight reviewer for automatic loops.

    This tool verifies that a ready approval-plan descriptor and an explicit
    approval-record artifact can be used as input for a future transaction journal
    writer. It never writes journals, starts transactions, sends CDP commands,
    executes continuation steps, calls MCP, or touches mobile runtime chains.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def review_paused_session_automatic_loop_transaction_preflight(
        approval_plan_json: str | None = None,
        approval_plan_ref: str | None = None,
        approval_record_json: str | None = None,
        approval_record_ref: str | None = None,
        expected_approval_plan_id: str | None = None,
        expected_approval_record_id: str | None = None,
        expected_preflight_id: str | None = None,
        expected_plan_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Review automatic-loop transaction / journal writer readiness."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return review_paused_session_automatic_loop_transaction_preflight_payload(
            approval_plan_json=approval_plan_json,
            approval_plan_ref=approval_plan_ref,
            approval_record_json=approval_record_json,
            approval_record_ref=approval_record_ref,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_preflight_id=expected_preflight_id,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    review_paused_session_automatic_loop_transaction_preflight.__name__ = "review_paused_session_automatic_loop_transaction_preflight"
    return review_paused_session_automatic_loop_transaction_preflight


def make_record_paused_session_automatic_loop_transaction_journal_tool(default_artifact_root: str | Path | None = None):
    """Create an explicit transaction journal writer for automatic-loop execution.

    This writer only records a reviewed transaction journal for a future bounded
    executor. It does not send CDP commands, recover callFrames, execute loop
    iterations, start long-lived sessions, call MCP, or touch mobile runtimes.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def record_paused_session_automatic_loop_transaction_journal(
        transaction_preflight_json: str | None = None,
        transaction_preflight_ref: str | None = None,
        reviewer: str | None = None,
        reason: str | None = None,
        mode: str = "dry-run",
        write_result: bool = False,
        approve_transaction_journal: bool = False,
        expected_transaction_preflight_id: str | None = None,
        expected_approval_record_id: str | None = None,
        expected_transaction_id: str | None = None,
        expected_preflight_id: str | None = None,
        expected_preflight_digest_sha256: str | None = None,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Write a reviewed automatic-loop transaction journal record."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return record_paused_session_automatic_loop_transaction_journal_payload(
            transaction_preflight_json=transaction_preflight_json,
            transaction_preflight_ref=transaction_preflight_ref,
            reviewer=reviewer,
            reason=reason,
            mode=mode,
            write_result=write_result,
            approve_transaction_journal=approve_transaction_journal,
            expected_transaction_preflight_id=expected_transaction_preflight_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_transaction_id=expected_transaction_id,
            expected_preflight_id=expected_preflight_id,
            expected_preflight_digest_sha256=expected_preflight_digest_sha256,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    record_paused_session_automatic_loop_transaction_journal.__name__ = "record_paused_session_automatic_loop_transaction_journal"
    return record_paused_session_automatic_loop_transaction_journal


def make_review_paused_session_automatic_loop_bounded_executor_gate_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only final gate reviewer for a future bounded automatic-loop executor.

    The gate consumes a reviewed transaction journal and produces machine-readable
    executor input checks plus the future result contract. It deliberately does
    not execute loop iterations, send CDP commands, recover callFrames, manage
    long-lived sessions, call MCP, or touch mobile runtimes.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def review_paused_session_automatic_loop_bounded_executor_gate(
        transaction_journal_json: str | None = None,
        transaction_journal_ref: str | None = None,
        expected_journal_id: str | None = None,
        expected_transaction_id: str | None = None,
        expected_transaction_preflight_id: str | None = None,
        expected_approval_record_id: str | None = None,
        expected_journal_digest_sha256: str | None = None,
        max_iterations: int | None = None,
        require_fresh_live_callframe: bool = True,
        artifact_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Review final bounded-executor gates without executing the loop."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        return review_paused_session_automatic_loop_bounded_executor_gate_payload(
            transaction_journal_json=transaction_journal_json,
            transaction_journal_ref=transaction_journal_ref,
            expected_journal_id=expected_journal_id,
            expected_transaction_id=expected_transaction_id,
            expected_transaction_preflight_id=expected_transaction_preflight_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_journal_digest_sha256=expected_journal_digest_sha256,
            max_iterations=max_iterations,
            require_fresh_live_callframe=require_fresh_live_callframe,
            artifact_root=artifact_root,
            default_artifact_root=root,
            metadata=metadata,
        )

    review_paused_session_automatic_loop_bounded_executor_gate.__name__ = "review_paused_session_automatic_loop_bounded_executor_gate"
    return review_paused_session_automatic_loop_bounded_executor_gate


def record_paused_session_automatic_loop_executor_approval_payload(
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
    expected_preflight_id: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write the automatic-loop executor approval record payload."""

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
    plan_digest = _stable_json_digest(approval_plan) if approval_plan else None
    blockers = _automatic_loop_executor_approval_record_blockers(
        approval_plan=approval_plan,
        reviewer=reviewer,
        decision=decision,
        mode=mode,
        write_result=write_result,
        approve_approval_record=approve_approval_record,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_preflight_id=expected_preflight_id,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        plan_digest=plan_digest,
    )
    written = not blockers and mode == "apply" and write_result and approve_approval_record
    approved_for_execution = written and decision == "approved"
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    approval_plan_id = _string(approval_plan.get("approval_plan_id"))
    preflight_id = _string(approval_plan.get("preflight_id"))
    approval_record_id = _automatic_loop_executor_approval_record_id(
        approval_plan_id=approval_plan_id,
        preflight_id=preflight_id,
        decision=decision,
        reviewer=reviewer,
        created_at=created_at,
    )
    result_path = effective_root / "workspace" / "paused-session-automatic-loop-executor-approval-record.json"
    payload: dict[str, Any] = {
        "schema_version": AUTOMATIC_LOOP_EXECUTOR_APPROVAL_RECORD_VERSION,
        "status": status,
        "approval_recorded": written,
        "approved_for_execution": approved_for_execution,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "approval_record_id": approval_record_id,
        "approval_plan_id": approval_plan_id or None,
        "preflight_id": preflight_id or None,
        "plan_id": approval_plan.get("plan_id"),
        "loop_id": approval_plan.get("loop_id"),
        "workflow_id": approval_plan.get("workflow_id"),
        "pause_session_id": approval_plan.get("pause_session_id"),
        "target_id": approval_plan.get("target_id"),
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "approval_plan_digest_sha256": plan_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "source_approval_plan_summary": {
            "schema_version": approval_plan.get("schema_version"),
            "status": approval_plan.get("status"),
            "ready_for_review": _boolish(approval_plan.get("ready_for_review")),
            "approval_plan_ready_for_review": _boolish(approval_plan.get("approval_plan_ready_for_review")),
            "approved_iteration_count": approval_plan.get("approved_iteration_count", 0),
            "max_approved_iterations": approval_plan.get("max_approved_iterations", 0),
            "ready_to_execute_now": _boolish(_nested_get(approval_plan, "executor_input_gates", "ready_to_execute_now")),
            "future_executor_implemented": _boolish(_nested_get(approval_plan, "future_executor_contract", "implemented")),
            "transaction_started": _boolish(_nested_get(approval_plan, "transaction_plan", "transaction_started")),
            "journal_written_now": _boolish(_nested_get(approval_plan, "transaction_plan", "journal_written_now")),
            "next_action": approval_plan.get("next_action"),
        },
        "approved_iterations": [
            {
                "iteration_index": item.get("iteration_index"),
                "workflow_step_index": item.get("workflow_step_index"),
                "method": item.get("method"),
                "fingerprint": item.get("fingerprint"),
                "approval_status": "approved_by_record" if written and decision == "approved" else "review_record_planned",
                "executed_now": False,
                "requires_checkpoint_after_iteration": True,
            }
            for item in approval_plan.get("approved_iterations", [])
            if isinstance(item, dict)
        ],
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_recorded": approved_for_execution,
            "approved_for_execution": approved_for_execution,
            "transaction_started": False,
            "journal_written": False,
            "requires_ready_approval_plan": True,
            "requires_transaction_journal": True,
            "requires_fresh_live_callframe_per_iteration": True,
            "requires_checkpoint_after_each_iteration": True,
        },
        "checks": _automatic_loop_executor_approval_record_checks(
            approval_plan=approval_plan,
            reviewer=reviewer,
            decision=decision,
            mode=mode,
            write_result=write_result,
            approve_approval_record=approve_approval_record,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_preflight_id=expected_preflight_id,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            plan_digest=plan_digest,
        ),
        "blockers": blockers,
        "next_action": _automatic_loop_executor_approval_record_next_action(status=status, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_paused_session_automatic_loop_executor_approval",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/paused-session-automatic-loop-executor-approval-record.json",
            "future_path": "/workspace/debugger/paused-session-automatic-loop-executor-approval-record.json",
            "path": str(result_path),
        },
        "side_effect_policy": _automatic_loop_executor_approval_record_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def record_paused_session_automatic_loop_transaction_journal_payload(
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
    expected_transaction_id: str | None = None,
    expected_preflight_id: str | None = None,
    expected_preflight_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build or write an explicit automatic-loop transaction journal payload."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        transaction_preflight_json,
        artifact_ref=transaction_preflight_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="transaction_preflight_json",
        artifact_field_name="transaction_preflight_ref",
    )
    transaction_preflight = _first_object(loaded.get("transaction_preflight"), loaded)
    effective_root = Path(artifact_root) if artifact_root else root
    effective_root = effective_root.expanduser().resolve()
    transaction_plan = transaction_preflight.get("transaction_plan") if isinstance(transaction_preflight.get("transaction_plan"), dict) else {}
    transaction_id = _string(transaction_plan.get("transaction_id"))
    transaction_preflight_id = _string(transaction_preflight.get("transaction_preflight_id"))
    approval_record_id = _string(transaction_preflight.get("approval_record_id"))
    preflight_id = _string(transaction_preflight.get("preflight_id"))
    preflight_digest = _stable_json_digest(transaction_preflight) if transaction_preflight else None
    result_path = effective_root / "workspace" / "paused-session-automatic-loop-executor-journal.json"
    blockers = _automatic_loop_transaction_journal_blockers(
        transaction_preflight=transaction_preflight,
        reviewer=reviewer,
        mode=mode,
        write_result=write_result,
        approve_transaction_journal=approve_transaction_journal,
        expected_transaction_preflight_id=expected_transaction_preflight_id,
        expected_approval_record_id=expected_approval_record_id,
        expected_transaction_id=expected_transaction_id,
        expected_preflight_id=expected_preflight_id,
        expected_preflight_digest_sha256=expected_preflight_digest_sha256,
        preflight_digest=preflight_digest,
        result_path=result_path,
    )
    written = not blockers and mode == "apply" and write_result and approve_transaction_journal
    status = "blocked" if blockers else "written" if written else "planned"
    created_at = datetime.now(timezone.utc).isoformat()
    journal_id = _automatic_loop_transaction_journal_id(
        transaction_preflight_id=transaction_preflight_id,
        approval_record_id=approval_record_id,
        transaction_id=transaction_id,
        reviewer=reviewer,
        created_at=created_at,
    )
    planned_entries = transaction_preflight.get("planned_journal_entries") if isinstance(transaction_preflight.get("planned_journal_entries"), list) else []
    journal_entries = [
        {
            "entry_index": 0,
            "entry_kind": "transaction_started",
            "transaction_id": transaction_id or None,
            "transaction_preflight_id": transaction_preflight_id or None,
            "approval_record_id": approval_record_id or None,
            "reviewer": reviewer,
            "created_at": created_at,
            "automatic_loop_executed": False,
        }
    ]
    for index, item in enumerate(planned_entries, start=1):
        if not isinstance(item, dict):
            continue
        journal_entries.append(
            {
                "entry_index": index,
                "entry_kind": "planned_iteration_journaled",
                "iteration_index": item.get("iteration_index"),
                "workflow_step_index": item.get("workflow_step_index"),
                "method": item.get("method"),
                "fingerprint": item.get("fingerprint"),
                "executed_now": False,
                "requires_fresh_live_callframe_before_execution": True,
                "requires_checkpoint_after_iteration": True,
            }
        )
    payload: dict[str, Any] = {
        "schema_version": AUTOMATIC_LOOP_TRANSACTION_JOURNAL_VERSION,
        "status": status,
        "journal_written": written,
        "transaction_started": written,
        "dry_run": not written,
        "mode": mode,
        "write_result": write_result,
        "journal_id": journal_id,
        "transaction_preflight_id": transaction_preflight_id or None,
        "approval_record_id": approval_record_id or None,
        "approval_plan_id": transaction_preflight.get("approval_plan_id"),
        "preflight_id": preflight_id or None,
        "transaction_id": transaction_id or None,
        "plan_id": transaction_preflight.get("plan_id"),
        "loop_id": transaction_preflight.get("loop_id"),
        "workflow_id": transaction_preflight.get("workflow_id"),
        "pause_session_id": transaction_preflight.get("pause_session_id"),
        "target_id": transaction_preflight.get("target_id"),
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "transaction_preflight_digest_sha256": preflight_digest,
        "expected_preflight_digest_sha256": expected_preflight_digest_sha256,
        "source_transaction_preflight_summary": {
            "schema_version": transaction_preflight.get("schema_version"),
            "status": transaction_preflight.get("status"),
            "transaction_preflight_ready_for_review": _boolish(transaction_preflight.get("transaction_preflight_ready_for_review")),
            "approval_record_verified": _boolish(_nested_get(transaction_preflight, "journal_writer_input_gates", "approval_record_verified")),
            "ready_to_write_now": _boolish(_nested_get(transaction_preflight, "transaction_plan", "ready_to_write_now")),
            "transaction_started": _boolish(_nested_get(transaction_preflight, "transaction_plan", "transaction_started")),
            "journal_written_now": _boolish(_nested_get(transaction_preflight, "transaction_plan", "journal_written_now")),
        },
        "journal_entries": journal_entries,
        "journal_summary": {
            "entry_count": len(journal_entries) if written else 0,
            "planned_entry_count": len(journal_entries),
            "transaction_started": written,
            "journal_written": written,
            "automatic_loop_executed": False,
            "requires_bounded_executor_followup": True,
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_record_verified": _boolish(_nested_get(transaction_preflight, "journal_writer_input_gates", "approval_record_verified")),
            "transaction_started": written,
            "journal_written": written,
            "automatic_loop_executed": False,
            "requires_fresh_live_callframe_per_iteration": True,
            "requires_checkpoint_after_each_iteration": True,
            "requires_bounded_executor_review": True,
        },
        "checks": _automatic_loop_transaction_journal_checks(
            transaction_preflight=transaction_preflight,
            reviewer=reviewer,
            mode=mode,
            write_result=write_result,
            approve_transaction_journal=approve_transaction_journal,
            expected_transaction_preflight_id=expected_transaction_preflight_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_transaction_id=expected_transaction_id,
            expected_preflight_id=expected_preflight_id,
            expected_preflight_digest_sha256=expected_preflight_digest_sha256,
            preflight_digest=preflight_digest,
            result_path=result_path,
        ),
        "blockers": blockers,
        "next_action": _automatic_loop_transaction_journal_next_action(status=status, blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "record_paused_session_automatic_loop_transaction_journal",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/paused-session-automatic-loop-executor-journal.json",
            "future_path": "/workspace/debugger/paused-session-automatic-loop-executor-journal.json",
            "path": str(result_path),
        },
        "side_effect_policy": _automatic_loop_transaction_journal_side_effect_policy(written=written),
    }
    if written:
        _write_json(result_path, payload)
    return payload


def review_paused_session_automatic_loop_bounded_executor_gate_payload(
    *,
    transaction_journal_json: str | None = None,
    transaction_journal_ref: str | None = None,
    expected_journal_id: str | None = None,
    expected_transaction_id: str | None = None,
    expected_transaction_preflight_id: str | None = None,
    expected_approval_record_id: str | None = None,
    expected_journal_digest_sha256: str | None = None,
    max_iterations: int | None = None,
    require_fresh_live_callframe: bool = True,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only final gate descriptor for a future bounded executor."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded, artifact_read = _loads_object_or_artifact(
        transaction_journal_json,
        artifact_ref=transaction_journal_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="transaction_journal_json",
        artifact_field_name="transaction_journal_ref",
    )
    transaction_journal = _first_object(loaded.get("transaction_journal"), loaded)
    journal_digest = _stable_json_digest(transaction_journal) if transaction_journal else None
    journal_entries = transaction_journal.get("journal_entries") if isinstance(transaction_journal.get("journal_entries"), list) else []
    planned_iteration_entries = [item for item in journal_entries if isinstance(item, dict) and item.get("entry_kind") == "planned_iteration_journaled"]
    effective_max_iterations = max_iterations if isinstance(max_iterations, int) and max_iterations > 0 else len(planned_iteration_entries)
    checks = _automatic_loop_bounded_executor_gate_checks(
        transaction_journal=transaction_journal,
        expected_journal_id=expected_journal_id,
        expected_transaction_id=expected_transaction_id,
        expected_transaction_preflight_id=expected_transaction_preflight_id,
        expected_approval_record_id=expected_approval_record_id,
        expected_journal_digest_sha256=expected_journal_digest_sha256,
        journal_digest=journal_digest,
        max_iterations=max_iterations,
        planned_iteration_count=len(planned_iteration_entries),
    )
    blockers = [check["name"] for check in checks if not check["passed"]]
    ready_for_executor_review = not blockers
    status = "ready_for_review" if ready_for_executor_review else "blocked"
    result_contract = {
        "schema_version": "reverse-deepagent.paused-session-automatic-loop-execution-result.v1",
        "artifact": "workspace/paused-session-automatic-loop-execution-result.json",
        "future_path": "/workspace/debugger/paused-session-automatic-loop-execution-result.json",
        "required_fields": [
            "schema_version",
            "status",
            "transaction_id",
            "journal_id",
            "executed_iteration_count",
            "iteration_results",
            "checkpoint_required",
            "side_effect_policy",
        ],
        "per_iteration_required_fields": [
            "iteration_index",
            "workflow_step_index",
            "method",
            "reviewed_before_execution",
            "fresh_live_callframe_verified",
            "executed",
            "checkpoint_required",
        ],
        "allowed_terminal_statuses": ["not_run", "partial", "completed", "blocked", "failed"],
        "must_record_checkpoint_after_each_iteration": True,
        "must_not_auto_advance_queue_after_result": True,
    }
    payload: dict[str, Any] = {
        "schema_version": AUTOMATIC_LOOP_BOUNDED_EXECUTOR_GATE_VERSION,
        "status": status,
        "bounded_executor_gate_ready_for_review": ready_for_executor_review,
        "ready_to_execute_now": False,
        "automatic_loop_executed": False,
        "journal_id": transaction_journal.get("journal_id"),
        "transaction_id": transaction_journal.get("transaction_id"),
        "transaction_preflight_id": transaction_journal.get("transaction_preflight_id"),
        "approval_record_id": transaction_journal.get("approval_record_id"),
        "preflight_id": transaction_journal.get("preflight_id"),
        "plan_id": transaction_journal.get("plan_id"),
        "loop_id": transaction_journal.get("loop_id"),
        "workflow_id": transaction_journal.get("workflow_id"),
        "pause_session_id": transaction_journal.get("pause_session_id"),
        "target_id": transaction_journal.get("target_id"),
        "transaction_journal_digest_sha256": journal_digest,
        "expected_journal_digest_sha256": expected_journal_digest_sha256,
        "source_journal_summary": {
            "schema_version": transaction_journal.get("schema_version"),
            "status": transaction_journal.get("status"),
            "journal_written": _boolish(transaction_journal.get("journal_written")),
            "transaction_started": _boolish(transaction_journal.get("transaction_started")),
            "automatic_loop_executed": _boolish(transaction_journal.get("automatic_loop_executed") or _nested_get(transaction_journal, "journal_summary", "automatic_loop_executed")),
            "entry_count": _nested_get(transaction_journal, "journal_summary", "entry_count"),
            "planned_entry_count": _nested_get(transaction_journal, "journal_summary", "planned_entry_count"),
            "ready_to_execute_now": _boolish(_nested_get(transaction_journal, "executor_input_gates", "ready_to_execute_now")),
        },
        "bounded_executor_input": {
            "max_iterations": effective_max_iterations,
            "planned_iteration_count": len(planned_iteration_entries),
            "require_fresh_live_callframe": require_fresh_live_callframe,
            "requires_retained_attached_session": True,
            "requires_checkpoint_after_each_iteration": True,
            "requires_per_iteration_review": True,
            "automatic_queue_advance_allowed": False,
            "long_lived_session_management_allowed": False,
        },
        "planned_iterations": [
            {
                "iteration_index": item.get("iteration_index"),
                "workflow_step_index": item.get("workflow_step_index"),
                "method": item.get("method"),
                "fingerprint": item.get("fingerprint"),
                "ready_for_future_executor_review": ready_for_executor_review,
                "executed_now": False,
                "requires_fresh_live_callframe_before_execution": True,
                "requires_checkpoint_after_iteration": True,
            }
            for item in planned_iteration_entries
        ],
        "future_executor_contract": {
            "executor_name": "execute_paused_session_automatic_loop",
            "implemented": False,
            "contract_ready_for_review": ready_for_executor_review,
            "result_contract": result_contract,
        },
        "checks": checks,
        "blockers": blockers,
        "next_action": _automatic_loop_bounded_executor_gate_next_action(blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "review_paused_session_automatic_loop_bounded_executor_gate",
            "artifact_read": artifact_read,
            "legacy_path": "workspace/paused-session-automatic-loop-bounded-executor-gate.json",
            "future_path": "/workspace/debugger/paused-session-automatic-loop-bounded-executor-gate.json",
        },
        "side_effect_policy": _automatic_loop_bounded_executor_gate_side_effect_policy(),
    }
    return payload


def review_paused_session_automatic_loop_transaction_preflight_payload(
    *,
    approval_plan_json: str | None = None,
    approval_plan_ref: str | None = None,
    approval_record_json: str | None = None,
    approval_record_ref: str | None = None,
    expected_approval_plan_id: str | None = None,
    expected_approval_record_id: str | None = None,
    expected_preflight_id: str | None = None,
    expected_plan_digest_sha256: str | None = None,
    artifact_root: str | None = None,
    default_artifact_root: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only transaction / journal preflight descriptor.

    The returned descriptor is an input review for a future explicit transaction
    journal writer. It deliberately leaves `ready_to_write_now`,
    `transaction_started`, and `journal_written` false.
    """

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")
    loaded_plan, plan_read = _loads_object_or_artifact(
        approval_plan_json,
        artifact_ref=approval_plan_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_plan_json",
        artifact_field_name="approval_plan_ref",
    )
    loaded_record, record_read = _loads_object_or_artifact(
        approval_record_json,
        artifact_ref=approval_record_ref,
        artifact_root=artifact_root,
        default_artifact_root=root,
        field_name="approval_record_json",
        artifact_field_name="approval_record_ref",
    )
    approval_plan = _first_object(loaded_plan.get("approval_plan"), loaded_plan)
    approval_record = _first_object(loaded_record.get("approval_record"), loaded_record)
    plan_digest = _stable_json_digest(approval_plan) if approval_plan else None
    blockers = _automatic_loop_transaction_preflight_blockers(
        approval_plan=approval_plan,
        approval_record=approval_record,
        expected_approval_plan_id=expected_approval_plan_id,
        expected_approval_record_id=expected_approval_record_id,
        expected_preflight_id=expected_preflight_id,
        expected_plan_digest_sha256=expected_plan_digest_sha256,
        plan_digest=plan_digest,
    )
    ready = not blockers
    approval_plan_id = _string(approval_plan.get("approval_plan_id"))
    approval_record_id = _string(approval_record.get("approval_record_id"))
    preflight_id = _string(approval_plan.get("preflight_id") or approval_record.get("preflight_id"))
    transaction_plan = approval_plan.get("transaction_plan") if isinstance(approval_plan.get("transaction_plan"), dict) else {}
    transaction_id = _string(transaction_plan.get("transaction_id") or f"automatic-loop-executor-transaction:{preflight_id or 'unbound'}")
    preflight_id_for_id = preflight_id or "unbound"
    transaction_preflight_id = f"automatic-loop-transaction-preflight:{approval_record_id or approval_plan_id or preflight_id_for_id}"
    journal_artifact = transaction_plan.get("journal_artifact") or "workspace/paused-session-automatic-loop-executor-journal.json"
    result_artifact = transaction_plan.get("result_artifact") or "workspace/paused-session-automatic-loop-execution-result.json"
    payload: dict[str, Any] = {
        "schema_version": AUTOMATIC_LOOP_TRANSACTION_PREFLIGHT_VERSION,
        "status": "ready_for_review" if ready else "blocked",
        "ready_for_review": ready,
        "transaction_preflight_ready_for_review": ready,
        "transaction_preflight_id": transaction_preflight_id,
        "approval_record_id": approval_record_id or None,
        "approval_plan_id": approval_plan_id or None,
        "preflight_id": preflight_id or None,
        "plan_id": approval_plan.get("plan_id") or approval_record.get("plan_id"),
        "loop_id": approval_plan.get("loop_id") or approval_record.get("loop_id"),
        "workflow_id": approval_plan.get("workflow_id") or approval_record.get("workflow_id"),
        "pause_session_id": approval_plan.get("pause_session_id") or approval_record.get("pause_session_id"),
        "target_id": approval_plan.get("target_id") or approval_record.get("target_id"),
        "approval_plan_digest_sha256": plan_digest,
        "expected_plan_digest_sha256": expected_plan_digest_sha256,
        "source_approval_plan_summary": {
            "schema_version": approval_plan.get("schema_version"),
            "status": approval_plan.get("status"),
            "approval_plan_ready_for_review": _boolish(approval_plan.get("approval_plan_ready_for_review")),
            "approved_iteration_count": approval_plan.get("approved_iteration_count", 0),
            "future_executor_implemented": _boolish(_nested_get(approval_plan, "future_executor_contract", "implemented")),
            "transaction_id": transaction_id,
            "transaction_started": _boolish(transaction_plan.get("transaction_started")),
            "journal_written_now": _boolish(transaction_plan.get("journal_written_now")),
        },
        "source_approval_record_summary": {
            "schema_version": approval_record.get("schema_version"),
            "status": approval_record.get("status"),
            "approval_recorded": _boolish(approval_record.get("approval_recorded")),
            "approved_for_execution": _boolish(approval_record.get("approved_for_execution")),
            "decision": approval_record.get("decision"),
            "reviewer": approval_record.get("reviewer"),
            "transaction_started": _boolish(_nested_get(approval_record, "executor_input_gates", "transaction_started")),
            "journal_written": _boolish(_nested_get(approval_record, "executor_input_gates", "journal_written")),
            "automatic_loop_executed": _boolish(_nested_get(approval_record, "side_effect_policy", "automatic_loop_executed")),
        },
        "journal_writer_requirements": {
            "requires_explicit_review_approval": True,
            "requires_ready_transaction_preflight": True,
            "requires_matching_approval_plan_id": True,
            "requires_matching_approval_record_id": True,
            "requires_matching_preflight_id": True,
            "requires_matching_plan_digest": True,
            "requires_append_only_journal": True,
            "requires_idempotency_guard": True,
            "requires_checkpoint_after_each_iteration": True,
            "requires_fresh_live_callframe_per_iteration": True,
            "requires_stop_after_journal_write": True,
        },
        "transaction_plan": {
            "transaction_id": transaction_id,
            "idempotency_key": transaction_plan.get("idempotency_key") or transaction_id,
            "transaction_started": False,
            "journal_written_now": False,
            "journal_artifact": journal_artifact,
            "result_artifact": result_artifact,
            "ready_for_journal_writer_review": ready,
            "ready_to_write_now": False,
            "future_journal_writer_implemented": False,
        },
        "journal_writer_input_gates": {
            "approval_plan_verified": ready,
            "approval_record_verified": ready,
            "ready_for_review": ready,
            "ready_to_write_now": False,
            "transaction_started": False,
            "journal_written": False,
            "automatic_loop_executed": False,
        },
        "planned_journal_entries": [
            {
                "entry_index": index,
                "entry_kind": "planned_iteration",
                "iteration_index": item.get("iteration_index"),
                "workflow_step_index": item.get("workflow_step_index"),
                "method": item.get("method"),
                "fingerprint": item.get("fingerprint"),
                "would_write_now": False,
                "requires_checkpoint_after_iteration": True,
            }
            for index, item in enumerate(approval_record.get("approved_iterations", []))
            if isinstance(item, dict)
        ],
        "checks": _automatic_loop_transaction_preflight_checks(
            approval_plan=approval_plan,
            approval_record=approval_record,
            expected_approval_plan_id=expected_approval_plan_id,
            expected_approval_record_id=expected_approval_record_id,
            expected_preflight_id=expected_preflight_id,
            expected_plan_digest_sha256=expected_plan_digest_sha256,
            plan_digest=plan_digest,
        ),
        "blockers": blockers,
        "next_action": _automatic_loop_transaction_preflight_next_action(blockers=blockers),
        "metadata": {
            **(metadata or {}),
            "tool": "review_paused_session_automatic_loop_transaction_preflight",
            "approval_plan_read": plan_read,
            "approval_record_read": record_read,
            "legacy_path": "workspace/paused-session-automatic-loop-transaction-preflight.json",
            "future_path": "/workspace/debugger/paused-session-automatic-loop-transaction-preflight.json",
        },
        "side_effect_policy": _automatic_loop_transaction_preflight_side_effect_policy(),
    }
    return payload


def _automatic_loop_executor_approval_record_checks(
    *,
    approval_plan: dict[str, Any],
    reviewer: str | None,
    decision: str,
    mode: str,
    write_result: bool,
    approve_approval_record: bool,
    expected_approval_plan_id: str | None,
    expected_preflight_id: str | None,
    expected_plan_digest_sha256: str | None,
    plan_digest: str | None,
) -> list[dict[str, Any]]:
    plan_blockers = approval_plan.get("blockers") if isinstance(approval_plan.get("blockers"), list) else []
    return [
        {"name": "approval_plan_available", "passed": bool(approval_plan), "details": {"approval_plan_id": approval_plan.get("approval_plan_id")}},
        {"name": "approval_plan_ready_for_review", "passed": approval_plan.get("status") == "ready_for_review" and approval_plan.get("approval_plan_ready_for_review") is True, "details": {"status": approval_plan.get("status"), "approval_plan_ready_for_review": approval_plan.get("approval_plan_ready_for_review")}},
        {"name": "approval_plan_has_no_blockers", "passed": not plan_blockers, "details": {"blockers": plan_blockers}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "decision_supported", "passed": decision in {"approved", "rejected", "needs_changes"}, "details": {"decision": decision}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_approval_record", "passed": mode != "apply" or bool(approve_approval_record), "details": {"approve_approval_record": approve_approval_record}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or approval_plan.get("approval_plan_id") == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": approval_plan.get("approval_plan_id")}},
        {"name": "expected_preflight_id_matches", "passed": not expected_preflight_id or approval_plan.get("preflight_id") == expected_preflight_id, "details": {"expected_preflight_id": expected_preflight_id, "preflight_id": approval_plan.get("preflight_id")}},
        {"name": "expected_plan_digest_matches", "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest, "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest}},
        {"name": "approval_plan_does_not_claim_ready_to_execute", "passed": _nested_get(approval_plan, "executor_input_gates", "ready_to_execute_now") is not True, "details": {"ready_to_execute_now": _nested_get(approval_plan, "executor_input_gates", "ready_to_execute_now")}},
        {"name": "future_executor_not_implemented", "passed": _nested_get(approval_plan, "future_executor_contract", "implemented") is not True, "details": {"future_executor_implemented": _nested_get(approval_plan, "future_executor_contract", "implemented")}},
        {"name": "transaction_not_started", "passed": _nested_get(approval_plan, "transaction_plan", "transaction_started") is not True, "details": {"transaction_started": _nested_get(approval_plan, "transaction_plan", "transaction_started")}},
        {"name": "journal_not_written", "passed": _nested_get(approval_plan, "transaction_plan", "journal_written_now") is not True, "details": {"journal_written_now": _nested_get(approval_plan, "transaction_plan", "journal_written_now")}},
    ]


def _automatic_loop_executor_approval_record_blockers(**kwargs: Any) -> list[str]:
    return [check["name"] for check in _automatic_loop_executor_approval_record_checks(**kwargs) if not check["passed"]]


def _automatic_loop_executor_approval_record_next_action(*, status: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_paused_session_automatic_loop_executor_approval_record_blockers"
    if status == "planned":
        return "review_then_write_paused_session_automatic_loop_executor_approval_record"
    return "use_approval_record_for_future_bounded_automatic_loop_executor_transaction_preflight"


def _automatic_loop_executor_approval_record_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "dry_run_is_read_only": True,
        "writes_approval_record": written,
        "review_decision_recorded": written,
        "writes_transaction_journal": False,
        "transaction_started": False,
        "automatic_loop_executed": False,
        "multi_step_continuation_executed": False,
        "browser_resumed": False,
        "debugger_stepped": False,
        "callframe_evaluated": False,
        "runtime_mutated": False,
        "cdp_command_sent": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _automatic_loop_executor_approval_record_id(*, approval_plan_id: str, preflight_id: str, decision: str, reviewer: str | None, created_at: str) -> str:
    digest = hashlib.sha256(f"{approval_plan_id}\0{preflight_id}\0{decision}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"automatic-loop-executor-approval-record:{digest}"


def _automatic_loop_transaction_preflight_checks(
    *,
    approval_plan: dict[str, Any],
    approval_record: dict[str, Any],
    expected_approval_plan_id: str | None,
    expected_approval_record_id: str | None,
    expected_preflight_id: str | None,
    expected_plan_digest_sha256: str | None,
    plan_digest: str | None,
) -> list[dict[str, Any]]:
    plan_blockers = approval_plan.get("blockers") if isinstance(approval_plan.get("blockers"), list) else []
    record_blockers = approval_record.get("blockers") if isinstance(approval_record.get("blockers"), list) else []
    plan_id = approval_plan.get("approval_plan_id")
    record_plan_id = approval_record.get("approval_plan_id")
    preflight_id = approval_plan.get("preflight_id")
    record_preflight_id = approval_record.get("preflight_id")
    return [
        {"name": "approval_plan_available", "passed": bool(approval_plan), "details": {"approval_plan_id": plan_id}},
        {"name": "approval_record_available", "passed": bool(approval_record), "details": {"approval_record_id": approval_record.get("approval_record_id")}},
        {"name": "approval_plan_ready_for_review", "passed": approval_plan.get("status") == "ready_for_review" and approval_plan.get("approval_plan_ready_for_review") is True, "details": {"status": approval_plan.get("status"), "approval_plan_ready_for_review": approval_plan.get("approval_plan_ready_for_review")}},
        {"name": "approval_plan_has_no_blockers", "passed": not plan_blockers, "details": {"blockers": plan_blockers}},
        {"name": "approval_record_written", "passed": approval_record.get("status") == "written" and approval_record.get("approval_recorded") is True, "details": {"status": approval_record.get("status"), "approval_recorded": approval_record.get("approval_recorded")}},
        {"name": "approval_record_approved_for_execution", "passed": approval_record.get("approved_for_execution") is True and approval_record.get("decision") == "approved", "details": {"approved_for_execution": approval_record.get("approved_for_execution"), "decision": approval_record.get("decision")}},
        {"name": "approval_record_has_no_blockers", "passed": not record_blockers, "details": {"blockers": record_blockers}},
        {"name": "approval_record_matches_approval_plan_id", "passed": bool(plan_id) and plan_id == record_plan_id, "details": {"approval_plan_id": plan_id, "record_approval_plan_id": record_plan_id}},
        {"name": "approval_record_matches_preflight_id", "passed": bool(preflight_id) and preflight_id == record_preflight_id, "details": {"preflight_id": preflight_id, "record_preflight_id": record_preflight_id}},
        {"name": "approval_record_matches_plan_digest", "passed": not approval_record.get("approval_plan_digest_sha256") or approval_record.get("approval_plan_digest_sha256") == plan_digest, "details": {"record_digest": approval_record.get("approval_plan_digest_sha256"), "current_digest": plan_digest}},
        {"name": "expected_approval_plan_id_matches", "passed": not expected_approval_plan_id or plan_id == expected_approval_plan_id, "details": {"expected_approval_plan_id": expected_approval_plan_id, "approval_plan_id": plan_id}},
        {"name": "expected_approval_record_id_matches", "passed": not expected_approval_record_id or approval_record.get("approval_record_id") == expected_approval_record_id, "details": {"expected_approval_record_id": expected_approval_record_id, "approval_record_id": approval_record.get("approval_record_id")}},
        {"name": "expected_preflight_id_matches", "passed": not expected_preflight_id or preflight_id == expected_preflight_id, "details": {"expected_preflight_id": expected_preflight_id, "preflight_id": preflight_id}},
        {"name": "expected_plan_digest_matches", "passed": not expected_plan_digest_sha256 or expected_plan_digest_sha256 == plan_digest, "details": {"expected_plan_digest_sha256": expected_plan_digest_sha256, "approval_plan_digest_sha256": plan_digest}},
        {"name": "approval_plan_transaction_not_started", "passed": _nested_get(approval_plan, "transaction_plan", "transaction_started") is not True, "details": {"transaction_started": _nested_get(approval_plan, "transaction_plan", "transaction_started")}},
        {"name": "approval_plan_journal_not_written", "passed": _nested_get(approval_plan, "transaction_plan", "journal_written_now") is not True, "details": {"journal_written_now": _nested_get(approval_plan, "transaction_plan", "journal_written_now")}},
        {"name": "approval_record_transaction_not_started", "passed": _nested_get(approval_record, "executor_input_gates", "transaction_started") is not True, "details": {"transaction_started": _nested_get(approval_record, "executor_input_gates", "transaction_started")}},
        {"name": "approval_record_journal_not_written", "passed": _nested_get(approval_record, "executor_input_gates", "journal_written") is not True, "details": {"journal_written": _nested_get(approval_record, "executor_input_gates", "journal_written")}},
        {"name": "approval_record_did_not_execute_loop", "passed": _nested_get(approval_record, "side_effect_policy", "automatic_loop_executed") is not True, "details": {"automatic_loop_executed": _nested_get(approval_record, "side_effect_policy", "automatic_loop_executed")}},
        {"name": "future_executor_not_implemented", "passed": _nested_get(approval_plan, "future_executor_contract", "implemented") is not True, "details": {"future_executor_implemented": _nested_get(approval_plan, "future_executor_contract", "implemented")}},
    ]


def _automatic_loop_transaction_preflight_blockers(**kwargs: Any) -> list[str]:
    return [check["name"] for check in _automatic_loop_transaction_preflight_checks(**kwargs) if not check["passed"]]


def _automatic_loop_transaction_preflight_next_action(*, blockers: list[str]) -> str:
    if blockers:
        return "fix_paused_session_automatic_loop_transaction_preflight_blockers"
    return "review_explicit_paused_session_automatic_loop_transaction_journal_writer"


def _automatic_loop_transaction_preflight_side_effect_policy() -> dict[str, Any]:
    return {
        "read_only": True,
        "review_only": True,
        "preflight_only": True,
        "transaction_preflight_only": True,
        "files_mutated": False,
        "artifacts_written_by_tool": False,
        "writes_approval_record": False,
        "writes_transaction_journal": False,
        "transaction_started": False,
        "journal_written": False,
        "automatic_loop_executed": False,
        "multi_step_continuation_executed": False,
        "browser_resumed": False,
        "debugger_stepped": False,
        "callframe_evaluated": False,
        "runtime_mutated": False,
        "cdp_command_sent": False,
        "cdp_target_attached": False,
        "debugger_domain_enabled": False,
        "debugger_event_subscribed": False,
        "paused_event_captured": False,
        "automatic_live_callframe_recovery": False,
        "automatic_queue_advance": False,
        "long_lived_cross_process_session_managed": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _automatic_loop_transaction_journal_checks(
    *,
    transaction_preflight: dict[str, Any],
    reviewer: str | None,
    mode: str,
    write_result: bool,
    approve_transaction_journal: bool,
    expected_transaction_preflight_id: str | None,
    expected_approval_record_id: str | None,
    expected_transaction_id: str | None,
    expected_preflight_id: str | None,
    expected_preflight_digest_sha256: str | None,
    preflight_digest: str | None,
    result_path: Path,
) -> list[dict[str, Any]]:
    blockers = transaction_preflight.get("blockers") if isinstance(transaction_preflight.get("blockers"), list) else []
    transaction_plan = transaction_preflight.get("transaction_plan") if isinstance(transaction_preflight.get("transaction_plan"), dict) else {}
    gates = transaction_preflight.get("journal_writer_input_gates") if isinstance(transaction_preflight.get("journal_writer_input_gates"), dict) else {}
    policy = transaction_preflight.get("side_effect_policy") if isinstance(transaction_preflight.get("side_effect_policy"), dict) else {}
    return [
        {"name": "transaction_preflight_available", "passed": bool(transaction_preflight), "details": {"transaction_preflight_id": transaction_preflight.get("transaction_preflight_id")}},
        {"name": "transaction_preflight_ready_for_review", "passed": transaction_preflight.get("status") == "ready_for_review" and transaction_preflight.get("transaction_preflight_ready_for_review") is True, "details": {"status": transaction_preflight.get("status"), "transaction_preflight_ready_for_review": transaction_preflight.get("transaction_preflight_ready_for_review")}},
        {"name": "transaction_preflight_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
        {"name": "reviewer_present", "passed": bool((reviewer or "").strip()), "details": {"reviewer": reviewer}},
        {"name": "mode_supported", "passed": mode in {"dry-run", "apply"}, "details": {"mode": mode}},
        {"name": "apply_requires_write_result", "passed": mode != "apply" or bool(write_result), "details": {"write_result": write_result}},
        {"name": "apply_requires_explicit_transaction_journal", "passed": mode != "apply" or bool(approve_transaction_journal), "details": {"approve_transaction_journal": approve_transaction_journal}},
        {"name": "approval_record_verified", "passed": gates.get("approval_record_verified") is True, "details": {"approval_record_verified": gates.get("approval_record_verified")}},
        {"name": "expected_transaction_preflight_id_matches", "passed": not expected_transaction_preflight_id or transaction_preflight.get("transaction_preflight_id") == expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": expected_transaction_preflight_id, "transaction_preflight_id": transaction_preflight.get("transaction_preflight_id")}},
        {"name": "expected_approval_record_id_matches", "passed": not expected_approval_record_id or transaction_preflight.get("approval_record_id") == expected_approval_record_id, "details": {"expected_approval_record_id": expected_approval_record_id, "approval_record_id": transaction_preflight.get("approval_record_id")}},
        {"name": "expected_transaction_id_matches", "passed": not expected_transaction_id or transaction_plan.get("transaction_id") == expected_transaction_id, "details": {"expected_transaction_id": expected_transaction_id, "transaction_id": transaction_plan.get("transaction_id")}},
        {"name": "expected_preflight_id_matches", "passed": not expected_preflight_id or transaction_preflight.get("preflight_id") == expected_preflight_id, "details": {"expected_preflight_id": expected_preflight_id, "preflight_id": transaction_preflight.get("preflight_id")}},
        {"name": "expected_preflight_digest_matches", "passed": not expected_preflight_digest_sha256 or expected_preflight_digest_sha256 == preflight_digest, "details": {"expected_preflight_digest_sha256": expected_preflight_digest_sha256, "transaction_preflight_digest_sha256": preflight_digest}},
        {"name": "preflight_does_not_claim_ready_to_write_now", "passed": transaction_plan.get("ready_to_write_now") is not True and gates.get("ready_to_write_now") is not True, "details": {"transaction_plan_ready_to_write_now": transaction_plan.get("ready_to_write_now"), "gate_ready_to_write_now": gates.get("ready_to_write_now")}},
        {"name": "transaction_not_already_started", "passed": transaction_plan.get("transaction_started") is not True and gates.get("transaction_started") is not True, "details": {"transaction_started": transaction_plan.get("transaction_started"), "gate_transaction_started": gates.get("transaction_started")}},
        {"name": "journal_not_already_written", "passed": transaction_plan.get("journal_written_now") is not True and gates.get("journal_written") is not True, "details": {"journal_written_now": transaction_plan.get("journal_written_now"), "gate_journal_written": gates.get("journal_written")}},
        {"name": "automatic_loop_not_executed", "passed": gates.get("automatic_loop_executed") is not True and policy.get("automatic_loop_executed") is not True, "details": {"gate_automatic_loop_executed": gates.get("automatic_loop_executed"), "policy_automatic_loop_executed": policy.get("automatic_loop_executed")}},
        {"name": "preflight_did_not_send_cdp", "passed": policy.get("cdp_command_sent") is not True and policy.get("cdp_target_attached") is not True, "details": {"cdp_command_sent": policy.get("cdp_command_sent"), "cdp_target_attached": policy.get("cdp_target_attached")}},
        {"name": "preflight_did_not_call_mcp_or_mobile", "passed": policy.get("calls_mcp") is not True and policy.get("mobile_runtime_used") is not True, "details": {"calls_mcp": policy.get("calls_mcp"), "mobile_runtime_used": policy.get("mobile_runtime_used")}},
        {"name": "journal_file_not_already_present", "passed": not result_path.exists(), "details": {"path": str(result_path), "exists": result_path.exists()}},
    ]


def _automatic_loop_transaction_journal_blockers(**kwargs: Any) -> list[str]:
    return [check["name"] for check in _automatic_loop_transaction_journal_checks(**kwargs) if not check["passed"]]


def _automatic_loop_transaction_journal_next_action(*, status: str, blockers: list[str]) -> str:
    if blockers:
        return "fix_paused_session_automatic_loop_transaction_journal_blockers"
    if status == "planned":
        return "review_then_write_paused_session_automatic_loop_transaction_journal"
    return "review_future_bounded_paused_session_automatic_loop_executor"


def _automatic_loop_transaction_journal_id(*, transaction_preflight_id: str, approval_record_id: str, transaction_id: str, reviewer: str | None, created_at: str) -> str:
    digest = hashlib.sha256(f"{transaction_preflight_id}\0{approval_record_id}\0{transaction_id}\0{reviewer or ''}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"automatic-loop-transaction-journal:{digest}"


def _automatic_loop_transaction_journal_side_effect_policy(*, written: bool) -> dict[str, Any]:
    return {
        "dry_run_is_read_only": True,
        "writes_transaction_journal": written,
        "transaction_started": written,
        "journal_written": written,
        "files_mutated": written,
        "artifacts_written_by_tool": written,
        "writes_approval_record": False,
        "automatic_loop_executed": False,
        "multi_step_continuation_executed": False,
        "browser_resumed": False,
        "debugger_stepped": False,
        "callframe_evaluated": False,
        "runtime_mutated": False,
        "cdp_command_sent": False,
        "cdp_target_attached": False,
        "debugger_domain_enabled": False,
        "debugger_event_subscribed": False,
        "paused_event_captured": False,
        "automatic_live_callframe_recovery": False,
        "automatic_queue_advance": False,
        "long_lived_cross_process_session_managed": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


def _automatic_loop_bounded_executor_gate_checks(
    *,
    transaction_journal: dict[str, Any],
    expected_journal_id: str | None,
    expected_transaction_id: str | None,
    expected_transaction_preflight_id: str | None,
    expected_approval_record_id: str | None,
    expected_journal_digest_sha256: str | None,
    journal_digest: str | None,
    max_iterations: int | None,
    planned_iteration_count: int,
) -> list[dict[str, Any]]:
    gates = transaction_journal.get("executor_input_gates") if isinstance(transaction_journal.get("executor_input_gates"), dict) else {}
    summary = transaction_journal.get("journal_summary") if isinstance(transaction_journal.get("journal_summary"), dict) else {}
    policy = transaction_journal.get("side_effect_policy") if isinstance(transaction_journal.get("side_effect_policy"), dict) else {}
    blockers = transaction_journal.get("blockers") if isinstance(transaction_journal.get("blockers"), list) else []
    return [
        {"name": "transaction_journal_available", "passed": bool(transaction_journal), "details": {"journal_id": transaction_journal.get("journal_id")}},
        {"name": "transaction_journal_written", "passed": transaction_journal.get("status") == "written" and transaction_journal.get("journal_written") is True, "details": {"status": transaction_journal.get("status"), "journal_written": transaction_journal.get("journal_written")}},
        {"name": "transaction_started", "passed": transaction_journal.get("transaction_started") is True and summary.get("transaction_started") is True, "details": {"transaction_started": transaction_journal.get("transaction_started"), "summary_transaction_started": summary.get("transaction_started")}},
        {"name": "journal_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
        {"name": "expected_journal_id_matches", "passed": not expected_journal_id or transaction_journal.get("journal_id") == expected_journal_id, "details": {"expected_journal_id": expected_journal_id, "journal_id": transaction_journal.get("journal_id")}},
        {"name": "expected_transaction_id_matches", "passed": not expected_transaction_id or transaction_journal.get("transaction_id") == expected_transaction_id, "details": {"expected_transaction_id": expected_transaction_id, "transaction_id": transaction_journal.get("transaction_id")}},
        {"name": "expected_transaction_preflight_id_matches", "passed": not expected_transaction_preflight_id or transaction_journal.get("transaction_preflight_id") == expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": expected_transaction_preflight_id, "transaction_preflight_id": transaction_journal.get("transaction_preflight_id")}},
        {"name": "expected_approval_record_id_matches", "passed": not expected_approval_record_id or transaction_journal.get("approval_record_id") == expected_approval_record_id, "details": {"expected_approval_record_id": expected_approval_record_id, "approval_record_id": transaction_journal.get("approval_record_id")}},
        {"name": "expected_journal_digest_matches", "passed": not expected_journal_digest_sha256 or expected_journal_digest_sha256 == journal_digest, "details": {"expected_journal_digest_sha256": expected_journal_digest_sha256, "transaction_journal_digest_sha256": journal_digest}},
        {"name": "journal_not_already_executed", "passed": summary.get("automatic_loop_executed") is not True and gates.get("automatic_loop_executed") is not True and policy.get("automatic_loop_executed") is not True, "details": {"summary_automatic_loop_executed": summary.get("automatic_loop_executed"), "gate_automatic_loop_executed": gates.get("automatic_loop_executed"), "policy_automatic_loop_executed": policy.get("automatic_loop_executed")}},
        {"name": "journal_does_not_claim_ready_to_execute_now", "passed": gates.get("ready_to_execute_now") is not True, "details": {"ready_to_execute_now": gates.get("ready_to_execute_now")}},
        {"name": "journal_has_planned_iterations", "passed": planned_iteration_count > 0, "details": {"planned_iteration_count": planned_iteration_count}},
        {"name": "max_iterations_positive_if_provided", "passed": max_iterations is None or max_iterations > 0, "details": {"max_iterations": max_iterations}},
        {"name": "max_iterations_within_planned_entries", "passed": max_iterations is None or planned_iteration_count == 0 or max_iterations <= planned_iteration_count, "details": {"max_iterations": max_iterations, "planned_iteration_count": planned_iteration_count}},
        {"name": "journal_did_not_send_cdp", "passed": policy.get("cdp_command_sent") is not True and policy.get("cdp_target_attached") is not True and policy.get("debugger_event_subscribed") is not True, "details": {"cdp_command_sent": policy.get("cdp_command_sent"), "cdp_target_attached": policy.get("cdp_target_attached"), "debugger_event_subscribed": policy.get("debugger_event_subscribed")}},
        {"name": "journal_did_not_call_mcp_or_mobile", "passed": policy.get("calls_mcp") is not True and policy.get("mobile_runtime_used") is not True, "details": {"calls_mcp": policy.get("calls_mcp"), "mobile_runtime_used": policy.get("mobile_runtime_used")}},
    ]


def _automatic_loop_bounded_executor_gate_next_action(*, blockers: list[str]) -> str:
    if blockers:
        return "fix_paused_session_automatic_loop_bounded_executor_gate_blockers"
    return "review_future_bounded_paused_session_automatic_loop_executor_mvp"


def _automatic_loop_bounded_executor_gate_side_effect_policy() -> dict[str, Any]:
    return {
        "read_only": True,
        "review_only": True,
        "plan_only": True,
        "writes_artifact": False,
        "writes_transaction_journal": False,
        "transaction_started": False,
        "journal_written": False,
        "automatic_loop_executed": False,
        "multi_step_continuation_executed": False,
        "browser_resumed": False,
        "debugger_stepped": False,
        "callframe_evaluated": False,
        "runtime_mutated": False,
        "cdp_command_sent": False,
        "cdp_target_attached": False,
        "debugger_domain_enabled": False,
        "debugger_event_subscribed": False,
        "paused_event_captured": False,
        "automatic_live_callframe_recovery": False,
        "automatic_queue_advance": False,
        "long_lived_cross_process_session_managed": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }


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
    if payload is None or not str(payload).strip():
        return {}
    return _loads_object(payload, field_name=field_name)


def _stable_json_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _object_alias(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _records_alias(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        records = _records_from(value)
        if records:
            return records
    return []


def _records_from(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "entries", "events", "records", "callframes", "callFrames", "evaluations", "actions", "audits"):
            records = _records_from(value.get(key))
            if records:
                return records
    return []


def _first_object(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return value
    return {}


def _string(value: Any) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "available", "live_available"}
    return bool(value)


def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _looks_paused(paused: dict[str, Any], session: dict[str, Any], timeline: dict[str, Any]) -> bool:
    text = " ".join(
        _string(value).lower()
        for value in (
            paused.get("status"),
            paused.get("state"),
            paused.get("reason"),
            session.get("lifecycle"),
            timeline.get("lifecycle"),
        )
    )
    return "paused" in text or "retained" in text


def _top_callframes(callframes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for frame in callframes[:5]:
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        result.append(
            {
                "function_name": _string(frame.get("functionName") or frame.get("function_name") or frame.get("name")) or "anonymous",
                "url": _string(frame.get("url") or location.get("url")),
                "line_number": location.get("lineNumber", location.get("line_number")),
                "column_number": location.get("columnNumber", location.get("column_number")),
            }
        )
    return result


def _timeline_entry_count(timeline: dict[str, Any], entries: list[dict[str, Any]]) -> int:
    count = timeline.get("entry_count") or timeline.get("event_count")
    if isinstance(count, int):
        return count
    return len(entries)


def _timeline_event_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for entry in entries:
        kind = entry.get("event") or entry.get("type") or entry.get("action") or entry.get("status") or "unknown"
        counter[str(kind)] += 1
    return dict(sorted(counter.items()))


def _next_action(status: str, blockers: list[str], warnings: list[str], requested_action: str, live_available: bool) -> str:
    if "paused_session_action_blocked" in blockers:
        return "use_live_same_process_paused_session_before_resume_step_or_evaluate"
    if "paused_session_live_preflight_blocked" in blockers:
        return "reproduce_pause_in_current_process_before_live_action"
    if "paused_session_target_attach_readiness_blocked" in blockers:
        return "collect_target_candidates_or_match_paused_url_before_attach_review"
    if "paused_session_cross_process_execution_plan_blocked" in blockers:
        return "resolve_cross_process_execution_plan_blockers"
    if "paused_session_cross_process_session_lifecycle_blocked" in blockers:
        return "resolve_paused_session_lifecycle_blockers"
    if "paused_session_cross_process_attach_probe_blocked" in blockers:
        return "resolve_cross_process_attach_probe_blockers"
    if "paused_session_cross_process_attach_probe_failed" in blockers:
        return "inspect_cross_process_attach_probe_error"
    if "paused_session_live_callframe_recovery_blocked" in blockers:
        return "capture_new_paused_event_after_attach"
    if "paused_session_cross_process_one_action_execution_blocked" in blockers:
        return "inspect_cross_process_one_action_error"
    if "paused_session_next_paused_event_capture_plan_blocked" in blockers:
        return "inspect_next_paused_event_capture_plan_blockers"
    if "paused_session_next_paused_event_capture_execution_blocked" in blockers:
        return "inspect_next_paused_event_capture_execution_blockers"
    if "paused_session_pre_action_subscribe_and_action_blocked" in blockers:
        return "inspect_pre_action_subscribe_and_action_blockers"
    if "paused_session_cross_process_continuation_checkpoint_blocked" in blockers:
        return "inspect_continuation_checkpoint_blockers"
    if "paused_session_multi_step_continuation_workflow_blocked" in blockers:
        return "inspect_multi_step_continuation_workflow_blockers"
    if "paused_session_multi_step_continuation_execution_blocked" in blockers:
        return "inspect_multi_step_continuation_execution_blockers"
    if "paused_session_multi_step_loop_plan_blocked" in blockers:
        return "inspect_multi_step_loop_plan_blockers"
    if "paused_session_multi_step_loop_execution_blocked" in blockers:
        return "inspect_multi_step_loop_execution_blockers"
    if "paused_session_automatic_loop_readiness_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_readiness_blockers"
    if "paused_session_automatic_loop_execution_plan_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_execution_plan_blockers"
    if "paused_session_automatic_loop_executor_preflight_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_executor_preflight_blockers"
    if "paused_session_automatic_loop_executor_approval_plan_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_executor_approval_plan_blockers"
    if "paused_session_automatic_loop_execution_result_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_execution_result_blockers"
    if "paused_session_automatic_loop_followup_checkpoint_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_followup_checkpoint_blockers"
    if "paused_session_automatic_loop_next_iteration_plan_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_next_iteration_plan_blockers"
    if "paused_session_automatic_loop_next_iteration_execution_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_next_iteration_execution_blockers"
    if "paused_session_automatic_loop_next_iteration_followup_checkpoint_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint_blockers"
    if "paused_session_automatic_loop_following_iteration_plan_blocked" in blockers:
        return "inspect_paused_session_automatic_loop_following_iteration_plan_blockers"
    if "debugger_artifact_reports_failure" in blockers or "debugger_pause_reports_failure" in blockers:
        return "inspect_debugger_failure_and_collect_fresh_pause_artifacts"
    if "no_debugger_artifacts_provided" in warnings:
        return "collect_debugger_pause_artifacts_before_review"
    if "target_attach_ready_but_execution_plan_not_observed" in warnings:
        return "plan_cross_process_execution_after_target_attach_readiness"
    if "cross_process_attach_probe_requires_review_approval" in warnings:
        return "approve_cross_process_attach_probe"
    if "cross_process_attach_probe_review_required" in warnings:
        return "approve_cross_process_attach_probe"
    if "live_callframe_recovered_one_action_not_observed" in warnings:
        return "plan_cross_process_one_action_executor"
    if "cross_process_one_action_requires_review_approval" in warnings or "cross_process_one_action_review_required" in warnings:
        return "approve_cross_process_one_action_execution"
    if "cross_process_one_action_next_paused_event_capture_plan_not_observed" in warnings:
        return "plan_next_paused_event_capture"
    if "pre_action_subscribe_and_action_requires_review" in warnings or "pre_action_subscribe_and_action_review_required" in warnings:
        return "approve_pre_action_subscribe_and_action"
    if "pre_action_subscribe_and_action_captured_checkpoint_not_observed" in warnings:
        return "checkpoint_cross_process_continuation"
    if "pre_action_subscribe_and_action_captured_review_result" in warnings:
        return "review_pre_action_orchestration_result"
    if "next_paused_event_capture_plan_requires_review" in warnings:
        return "review_next_paused_event_capture_plan"
    if "next_paused_event_capture_execution_requires_review" in warnings or "next_paused_event_capture_execution_review_required" in warnings:
        return "approve_next_paused_event_capture_execution"
    if "next_paused_event_captured_continuation_checkpoint_not_observed" in warnings:
        return "checkpoint_cross_process_continuation"
    if "cross_process_continuation_checkpoint_requires_live_callframe_recovery" in warnings:
        return "recover_live_callframe_from_captured_pause"
    if "multi_step_continuation_execution_requires_review" in warnings or "multi_step_continuation_execution_review_required" in warnings:
        return "approve_multi_step_continuation_iteration"
    if "multi_step_continuation_execution_checkpoint_not_observed" in warnings:
        return "checkpoint_cross_process_continuation"
    if "multi_step_continuation_execution_review_result" in warnings:
        return "review_multi_step_continuation_execution_result"
    if "multi_step_loop_plan_requires_review" in warnings:
        return "review_next_paused_session_loop_iteration"
    if "multi_step_loop_execution_requires_review" in warnings or "multi_step_loop_execution_review_required" in warnings:
        return "approve_paused_session_loop_iteration"
    if "multi_step_loop_execution_checkpoint_not_observed" in warnings:
        return "checkpoint_loop_iteration_captured_pause"
    if "multi_step_loop_execution_review_result" in warnings:
        return "review_paused_session_loop_execution_result"
    if "automatic_loop_readiness_requires_review" in warnings:
        return "review_future_bounded_automatic_loop_executor_contract"
    if "automatic_loop_execution_plan_requires_review" in warnings:
        return "review_future_bounded_automatic_loop_executor_plan"
    if "automatic_loop_executor_preflight_requires_review" in warnings:
        return "review_future_bounded_automatic_loop_executor_preflight"
    if "automatic_loop_executor_approval_plan_requires_review" in warnings:
        return "review_future_bounded_automatic_loop_executor_approval_transaction"
    if "automatic_loop_execution_requires_review" in warnings or "automatic_loop_execution_review_required" in warnings:
        return "approve_paused_session_automatic_loop_execution"
    if "automatic_loop_execution_checkpoint_required" in warnings:
        return "checkpoint_paused_session_automatic_loop_execution"
    if "automatic_loop_execution_review_result" in warnings:
        return "review_paused_session_automatic_loop_execution_result"
    if "automatic_loop_followup_checkpoint_requires_next_loop_plan" in warnings:
        return "plan_next_paused_session_loop_iteration_after_checkpoint"
    if "automatic_loop_followup_checkpoint_ready_for_next_loop_review" in warnings:
        return "review_next_paused_session_automatic_loop_iteration"
    if "automatic_loop_next_iteration_execution_requires_review" in warnings or "automatic_loop_next_iteration_execution_review_required" in warnings:
        return "approve_paused_session_automatic_loop_next_iteration_execution"
    if "automatic_loop_next_iteration_execution_checkpoint_required" in warnings:
        return "checkpoint_paused_session_automatic_loop_next_iteration_execution"
    if "automatic_loop_next_iteration_execution_review_result" in warnings:
        return "review_paused_session_automatic_loop_next_iteration_execution_result"
    if "automatic_loop_next_iteration_followup_checkpoint_requires_next_loop_plan" in warnings:
        return "plan_next_paused_session_loop_iteration_after_next_iteration"
    if "automatic_loop_next_iteration_followup_checkpoint_ready_for_next_loop_review" in warnings:
        return "review_following_paused_session_automatic_loop_iteration"
    if "automatic_loop_following_iteration_plan_requires_execution_review" in warnings:
        return "review_paused_session_automatic_loop_next_iteration_execution"
    if "automatic_loop_next_iteration_plan_requires_execution_review" in warnings:
        return "review_paused_session_automatic_loop_next_iteration_execution"
    if "multi_step_continuation_workflow_requires_review" in warnings:
        return "approve_multi_step_continuation_workflow"
    if "cross_process_continuation_checkpoint_ready_for_next_action_review" in warnings:
        return "plan_multi_step_continuation_workflow"
    if "next_paused_event_captured_recover_live_callframe" in warnings:
        return "recover_live_callframe_from_captured_pause"
    if "cross_process_one_action_executed_review_result" in warnings:
        return "review_cross_process_one_action_result"
    if "attach_probe_ready_but_live_callframe_recovery_not_observed" in warnings:
        return "review_attach_probe_result_before_live_callframe_recovery"
    if "cross_process_execution_plan_ready_but_attach_probe_not_observed" in warnings:
        return "run_reviewed_cross_process_attach_probe_next"
    if "cross_process_session_lifecycle_requires_review" in warnings:
        return "review_paused_session_lifecycle_before_next_continuation_step"
    if requested_action in _LIVE_ACTIONS and not live_available:
        return "attach_live_paused_session_or_limit_to_inspect_only_review"
    if "paused_session_has_no_callframes" in warnings:
        return "capture_callframes_before_debugger_decision"
    if "durable_snapshot_is_inspect_only" in warnings:
        return "inspect_snapshot_or_reproduce_pause_for_live_actions"
    if status == "warn":
        return "inspect_debugger_warnings"
    return "debugger_review_passed"


def _review_required_items(
    blockers: list[str],
    warnings: list[str],
    preflight: dict[str, Any],
    readiness: dict[str, Any],
    execution_plan: dict[str, Any],
    session_lifecycle: dict[str, Any],
    attach_probe: dict[str, Any],
    live_callframe_recovery: dict[str, Any],
    one_action_execution: dict[str, Any],
    pre_action_orchestration: dict[str, Any],
    next_capture_execution: dict[str, Any],
    continuation_checkpoint: dict[str, Any],
    multi_step_workflow: dict[str, Any],
    multi_step_execution: dict[str, Any],
    multi_step_loop: dict[str, Any],
    multi_step_loop_execution: dict[str, Any],
    automatic_loop_execution_result: dict[str, Any],
    automatic_loop_followup_checkpoint: dict[str, Any],
    automatic_loop_next_iteration_plan: dict[str, Any],
    automatic_loop_next_iteration_execution: dict[str, Any],
    automatic_loop_next_iteration_followup_checkpoint: dict[str, Any],
    automatic_loop_following_iteration_plan: dict[str, Any],
    session: dict[str, Any],
    paused: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    diagnostics = _preflight_diagnostics_for_review(preflight)
    attach_diagnostics = _attach_readiness_diagnostics_for_review(readiness)
    execution_plan_diagnostics = _cross_process_execution_plan_diagnostics_for_review(execution_plan)
    session_lifecycle_diagnostics = _cross_process_session_lifecycle_diagnostics_for_review(session_lifecycle)
    attach_probe_diagnostics = _cross_process_attach_probe_diagnostics_for_review(attach_probe)
    live_callframe_recovery_diagnostics = _live_callframe_recovery_diagnostics_for_review(live_callframe_recovery)
    one_action_diagnostics = _cross_process_one_action_diagnostics_for_review(one_action_execution)
    pre_action_diagnostics = _pre_action_subscribe_and_action_diagnostics_for_review(pre_action_orchestration)
    next_capture_diagnostics = _next_paused_event_capture_execution_diagnostics_for_review(next_capture_execution)
    continuation_checkpoint_diagnostics = _continuation_checkpoint_diagnostics_for_review(continuation_checkpoint)
    multi_step_workflow_diagnostics = _multi_step_continuation_workflow_diagnostics_for_review(multi_step_workflow)
    multi_step_execution_diagnostics = _multi_step_continuation_execution_diagnostics_for_review(multi_step_execution)
    multi_step_loop_diagnostics = _multi_step_loop_plan_diagnostics_for_review(multi_step_loop)
    multi_step_loop_execution_diagnostics = _multi_step_loop_execution_diagnostics_for_review(multi_step_loop_execution)
    automatic_loop_execution_diagnostics = _automatic_loop_execution_result_diagnostics_for_review(automatic_loop_execution_result)
    automatic_loop_followup_diagnostics = _automatic_loop_followup_checkpoint_diagnostics_for_review(automatic_loop_followup_checkpoint)
    automatic_loop_next_iteration_diagnostics = _automatic_loop_next_iteration_plan_diagnostics_for_review(automatic_loop_next_iteration_plan)
    automatic_loop_next_iteration_execution_diagnostics = _automatic_loop_next_iteration_execution_diagnostics_for_review(automatic_loop_next_iteration_execution)
    automatic_loop_next_iteration_followup_diagnostics = _automatic_loop_next_iteration_followup_checkpoint_diagnostics_for_review(automatic_loop_next_iteration_followup_checkpoint)
    automatic_loop_following_iteration_diagnostics = _automatic_loop_next_iteration_plan_diagnostics_for_review(automatic_loop_following_iteration_plan)
    for code in blockers:
        items.append(
            {
                "code": code,
                "session_id": _string(session.get("session_id") or session.get("pause_session_id")),
                "preflight_status": _string(preflight.get("status")),
                "preflight_source": _string(preflight.get("source")),
                "reason": _string(preflight.get("reason") or preflight.get("blocked_reason") or session.get("reason") or paused.get("reason")),
                "diagnostics": diagnostics,
                "attach_readiness_diagnostics": attach_diagnostics,
                "cross_process_execution_plan_diagnostics": execution_plan_diagnostics,
                "cross_process_session_lifecycle_diagnostics": session_lifecycle_diagnostics,
                "cross_process_attach_probe_diagnostics": attach_probe_diagnostics,
                "live_callframe_recovery_diagnostics": live_callframe_recovery_diagnostics,
                "cross_process_one_action_diagnostics": one_action_diagnostics,
                "pre_action_subscribe_and_action_diagnostics": pre_action_diagnostics,
                "next_paused_event_capture_execution_diagnostics": next_capture_diagnostics,
                "continuation_checkpoint_diagnostics": continuation_checkpoint_diagnostics,
                "multi_step_continuation_workflow_diagnostics": multi_step_workflow_diagnostics,
                "multi_step_continuation_execution_diagnostics": multi_step_execution_diagnostics,
                "multi_step_loop_plan_diagnostics": multi_step_loop_diagnostics,
                "multi_step_loop_execution_diagnostics": multi_step_loop_execution_diagnostics,
                "automatic_loop_execution_result_diagnostics": automatic_loop_execution_diagnostics,
                "automatic_loop_followup_checkpoint_diagnostics": automatic_loop_followup_diagnostics,
                "automatic_loop_next_iteration_plan_diagnostics": automatic_loop_next_iteration_diagnostics,
                "automatic_loop_next_iteration_execution_diagnostics": automatic_loop_next_iteration_execution_diagnostics,
                "automatic_loop_next_iteration_followup_checkpoint_diagnostics": automatic_loop_next_iteration_followup_diagnostics,
                "automatic_loop_following_iteration_plan_diagnostics": automatic_loop_following_iteration_diagnostics,
            }
        )
    for code in warnings:
        if code in {
            "durable_snapshot_is_inspect_only",
            "paused_session_unavailable",
            "paused_session_has_no_callframes",
            "target_attach_ready_but_execution_plan_not_observed",
            "cross_process_execution_plan_ready_but_attach_probe_not_observed",
            "cross_process_attach_probe_requires_review_approval",
            "cross_process_attach_probe_review_required",
            "attach_probe_ready_but_live_callframe_recovery_not_observed",
            "live_callframe_recovered_one_action_not_observed",
            "cross_process_one_action_requires_review_approval",
            "cross_process_one_action_review_required",
            "cross_process_one_action_executed_review_result",
            "cross_process_one_action_next_paused_event_capture_plan_not_observed",
            "pre_action_subscribe_and_action_requires_review",
            "pre_action_subscribe_and_action_review_required",
            "pre_action_subscribe_and_action_captured_checkpoint_not_observed",
            "pre_action_subscribe_and_action_captured_review_result",
            "next_paused_event_capture_plan_requires_review",
            "next_paused_event_capture_execution_requires_review",
            "next_paused_event_capture_execution_review_required",
            "next_paused_event_captured_recover_live_callframe",
            "next_paused_event_captured_continuation_checkpoint_not_observed",
            "cross_process_continuation_checkpoint_requires_live_callframe_recovery",
            "cross_process_continuation_checkpoint_ready_for_next_action_review",
            "multi_step_continuation_workflow_requires_review",
            "multi_step_continuation_execution_requires_review",
            "multi_step_continuation_execution_review_required",
            "multi_step_continuation_execution_checkpoint_not_observed",
            "multi_step_continuation_execution_review_result",
            "multi_step_loop_plan_requires_review",
            "multi_step_loop_execution_requires_review",
            "multi_step_loop_execution_review_required",
            "multi_step_loop_execution_checkpoint_not_observed",
            "multi_step_loop_execution_review_result",
            "cross_process_session_lifecycle_requires_review",
            "automatic_loop_execution_requires_review",
            "automatic_loop_execution_review_required",
            "automatic_loop_execution_checkpoint_required",
            "automatic_loop_execution_review_result",
            "automatic_loop_followup_checkpoint_requires_next_loop_plan",
            "automatic_loop_followup_checkpoint_ready_for_next_loop_review",
            "automatic_loop_next_iteration_plan_requires_execution_review",
            "automatic_loop_next_iteration_execution_requires_review",
            "automatic_loop_next_iteration_execution_review_required",
            "automatic_loop_next_iteration_execution_checkpoint_required",
            "automatic_loop_next_iteration_execution_review_result",
            "automatic_loop_next_iteration_followup_checkpoint_requires_next_loop_plan",
            "automatic_loop_next_iteration_followup_checkpoint_ready_for_next_loop_review",
            "automatic_loop_following_iteration_plan_requires_execution_review",
        }:
            items.append(
                {
                    "code": code,
                    "session_id": _string(session.get("session_id") or session.get("pause_session_id")),
                    "preflight_status": _string(preflight.get("status")),
                    "preflight_source": _string(preflight.get("source")),
                    "reason": _string(preflight.get("reason") or preflight.get("blocked_reason") or paused.get("reason")),
                    "diagnostics": diagnostics,
                    "attach_readiness_diagnostics": attach_diagnostics,
                    "cross_process_execution_plan_diagnostics": execution_plan_diagnostics,
                    "cross_process_session_lifecycle_diagnostics": session_lifecycle_diagnostics,
                    "cross_process_attach_probe_diagnostics": attach_probe_diagnostics,
                    "live_callframe_recovery_diagnostics": live_callframe_recovery_diagnostics,
                    "cross_process_one_action_diagnostics": one_action_diagnostics,
                    "next_paused_event_capture_execution_diagnostics": next_capture_diagnostics,
                    "continuation_checkpoint_diagnostics": continuation_checkpoint_diagnostics,
                    "multi_step_continuation_workflow_diagnostics": multi_step_workflow_diagnostics,
                    "multi_step_continuation_execution_diagnostics": multi_step_execution_diagnostics,
                    "multi_step_loop_plan_diagnostics": multi_step_loop_diagnostics,
                    "multi_step_loop_execution_diagnostics": multi_step_loop_execution_diagnostics,
                    "automatic_loop_execution_result_diagnostics": automatic_loop_execution_diagnostics,
                    "automatic_loop_followup_checkpoint_diagnostics": automatic_loop_followup_diagnostics,
                    "automatic_loop_next_iteration_plan_diagnostics": automatic_loop_next_iteration_diagnostics,
                    "automatic_loop_next_iteration_execution_diagnostics": automatic_loop_next_iteration_execution_diagnostics,
                    "automatic_loop_next_iteration_followup_checkpoint_diagnostics": automatic_loop_next_iteration_followup_diagnostics,
                    "automatic_loop_following_iteration_plan_diagnostics": automatic_loop_following_iteration_diagnostics,
                }
            )
    return items


def _preflight_diagnostics_for_review(preflight: dict[str, Any]) -> dict[str, Any]:
    live_session = preflight.get("live_session_diagnostics") if isinstance(preflight.get("live_session_diagnostics"), dict) else {}
    target = preflight.get("target_diagnostics") if isinstance(preflight.get("target_diagnostics"), dict) else {}
    callframe = preflight.get("callframe_diagnostics") if isinstance(preflight.get("callframe_diagnostics"), dict) else {}
    return {
        "live_session_available": _boolish(live_session.get("live_session_available")),
        "debugger_session_lifecycle": _string(live_session.get("debugger_session_lifecycle") or "unknown"),
        "same_process_required_for_live_action": _boolish(live_session.get("same_process_required_for_live_action")),
        "target_attached": _boolish(target.get("target_attached")),
        "cdp_target_available": _boolish(target.get("cdp_target_available")),
        "stable_callframe_required": _boolish(callframe.get("stable_callframe_required")),
        "stable_callframe_available": _boolish(callframe.get("stable_callframe_available")),
    }


def _attach_readiness_diagnostics_for_review(readiness: dict[str, Any]) -> dict[str, Any]:
    target_correlation = readiness.get("target_correlation") if isinstance(readiness.get("target_correlation"), dict) else {}
    attachability = readiness.get("attachability") if isinstance(readiness.get("attachability"), dict) else {}
    callframe_recovery = readiness.get("callframe_recovery") if isinstance(readiness.get("callframe_recovery"), dict) else {}
    return {
        "target_attach_readiness_proven": _boolish(readiness.get("target_attach_readiness_proven")),
        "cross_process_execution_ready": _boolish(readiness.get("cross_process_execution_ready")),
        "cross_process_live_continuation_supported": _boolish(readiness.get("cross_process_live_continuation_supported")),
        "expected_url": _string(target_correlation.get("expected_url")),
        "candidate_count": target_correlation.get("candidate_count", 0),
        "url_match": _boolish(target_correlation.get("url_match")),
        "target_id_available": _boolish(attachability.get("target_id_available")),
        "would_attach_cdp_target": _boolish(attachability.get("would_attach_cdp_target")),
        "stable_live_callframe_available": _boolish(callframe_recovery.get("stable_live_callframe_available")),
        "requires_new_paused_event_after_attach": _boolish(callframe_recovery.get("requires_new_paused_event_after_attach")),
    }


def _cross_process_execution_plan_diagnostics_for_review(plan: dict[str, Any]) -> dict[str, Any]:
    target = plan.get("target_attach_readiness_summary") if isinstance(plan.get("target_attach_readiness_summary"), dict) else {}
    callframe = plan.get("callframe_recovery_plan") if isinstance(plan.get("callframe_recovery_plan"), dict) else {}
    gates = plan.get("review_gates") if isinstance(plan.get("review_gates"), dict) else {}
    return {
        "execution_plan_ready_for_review": _boolish(plan.get("execution_plan_ready_for_review")),
        "cross_process_execution_ready": _boolish(plan.get("cross_process_execution_ready")),
        "cross_process_executor_implemented": _boolish(plan.get("cross_process_executor_implemented")),
        "cross_process_action_supported": _boolish(plan.get("cross_process_action_supported")),
        "target_attach_readiness_proven": _boolish(plan.get("target_attach_readiness_proven")),
        "target_id_available": _boolish(target.get("target_id_available")),
        "requires_new_paused_event_after_attach": _boolish(callframe.get("requires_new_paused_event_after_attach")),
        "attach_probe_review_required": _boolish(gates.get("attach_probe_review_required")),
        "action_execution_review_required": _boolish(gates.get("action_execution_review_required")),
    }


def _cross_process_session_lifecycle_diagnostics_for_review(lifecycle: dict[str, Any]) -> dict[str, Any]:
    session = lifecycle.get("session_diagnostics") if isinstance(lifecycle.get("session_diagnostics"), dict) else {}
    target = lifecycle.get("target_diagnostics") if isinstance(lifecycle.get("target_diagnostics"), dict) else {}
    debugger = lifecycle.get("debugger_diagnostics") if isinstance(lifecycle.get("debugger_diagnostics"), dict) else {}
    continuation = lifecycle.get("continuation_diagnostics") if isinstance(lifecycle.get("continuation_diagnostics"), dict) else {}
    return {
        "status": _string(lifecycle.get("status") or "unknown"),
        "ready_for_review": _boolish(lifecycle.get("ready_for_review")),
        "pause_session_id": _string(lifecycle.get("pause_session_id")),
        "target_id": _string(lifecycle.get("target_id")),
        "attached_session_retained": _boolish(session.get("attached_session_retained")),
        "target_lifecycle_observed": _boolish(session.get("target_lifecycle_observed")),
        "target_still_alive_proven": _boolish(target.get("target_still_alive_proven")),
        "target_still_alive_proof_requires_cdp_probe": _boolish(target.get("target_still_alive_proof_requires_cdp_probe")),
        "live_callframe_recovered": _boolish(debugger.get("live_callframe_recovered")),
        "live_callframe_id_present": _boolish(debugger.get("live_callframe_id_present")),
        "next_paused_event_captured": _boolish(debugger.get("next_paused_event_captured")),
        "automatic_multi_step_loop_supported": _boolish(continuation.get("automatic_multi_step_loop_supported")),
        "automatic_live_callframe_recovery_supported": _boolish(continuation.get("automatic_live_callframe_recovery_supported")),
        "automatic_wrapper_continuation_supported": _boolish(continuation.get("automatic_wrapper_continuation_supported")),
        "blockers": lifecycle.get("blockers") if isinstance(lifecycle.get("blockers"), list) else [],
    }


def _cross_process_attach_probe_diagnostics_for_review(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(probe.get("status") or "unknown"),
        "target_id": _string(probe.get("target_id")),
        "attach_attempted": _boolish(probe.get("attach_attempted")),
        "target_attached": _boolish(probe.get("target_attached")),
        "target_detached": _boolish(probe.get("target_detached")),
        "debugger_domain_enabled": _boolish(probe.get("debugger_domain_enabled")),
        "live_callframe_recovered": _boolish(probe.get("live_callframe_recovered")),
        "live_action_executed": _boolish(probe.get("live_action_executed")),
        "browser_resumed": _boolish(probe.get("browser_resumed")),
        "debugger_stepped": _boolish(probe.get("debugger_stepped")),
        "callframe_evaluated": _boolish(probe.get("callframe_evaluated")),
        "cdp_methods": probe.get("cdp_methods") if isinstance(probe.get("cdp_methods"), list) else [],
        "blockers": probe.get("blockers") if isinstance(probe.get("blockers"), list) else [],
    }


def _live_callframe_recovery_diagnostics_for_review(recovery: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(recovery.get("status") or "unknown"),
        "target_id": _string(recovery.get("target_id")),
        "attach_probe_status": _string(recovery.get("attach_probe_status") or "unknown"),
        "target_attached": _boolish(recovery.get("target_attached")),
        "fresh_paused_event_after_attach": _boolish(recovery.get("fresh_paused_event_after_attach")),
        "callframe_count": recovery.get("callframe_count", 0),
        "selected_callframe_has_id": _boolish(recovery.get("selected_callframe_has_id")),
        "live_callframe_recovered": _boolish(recovery.get("live_callframe_recovered")),
        "one_action_executor_ready_for_review": _boolish(recovery.get("one_action_executor_ready_for_review")),
        "debugger_domain_enabled": _boolish(recovery.get("debugger_domain_enabled")),
        "live_action_executed": _boolish(recovery.get("live_action_executed")),
        "browser_resumed": _boolish(recovery.get("browser_resumed")),
        "debugger_stepped": _boolish(recovery.get("debugger_stepped")),
        "callframe_evaluated": _boolish(recovery.get("callframe_evaluated")),
        "blockers": recovery.get("blockers") if isinstance(recovery.get("blockers"), list) else [],
    }


def _cross_process_one_action_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(execution.get("status") or "unknown"),
        "requested_action": _string(execution.get("requested_action") or "unknown"),
        "method": _string(execution.get("method")),
        "target_id": _string(execution.get("target_id")),
        "attached_session_id_present": bool(execution.get("attached_session_id")),
        "live_callframe_id_present": bool(execution.get("live_callframe_id")),
        "live_callframe_recovered": _boolish(execution.get("live_callframe_recovered")),
        "execute_action_requested": _boolish(execution.get("execute_action_requested")),
        "review_approved": _boolish(execution.get("review_approved")),
        "live_action_executed": _boolish(execution.get("live_action_executed")),
        "browser_resumed": _boolish(execution.get("browser_resumed")),
        "debugger_stepped": _boolish(execution.get("debugger_stepped")),
        "callframe_evaluated": _boolish(execution.get("callframe_evaluated")),
        "cdp_methods": execution.get("cdp_methods") if isinstance(execution.get("cdp_methods"), list) else [],
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }



def _pre_action_subscribe_and_action_diagnostics_for_review(orchestration: dict[str, Any]) -> dict[str, Any]:
    if not orchestration:
        return {}
    return {
        "status": _string(orchestration.get("status") or "unknown"),
        "method": _string(orchestration.get("method")),
        "pre_action_event_subscribed": _boolish(orchestration.get("pre_action_event_subscribed")),
        "action_sent_after_subscription": _boolish(orchestration.get("action_sent_after_subscription")),
        "live_action_executed": _boolish(orchestration.get("live_action_executed")),
        "paused_event_captured": _boolish(orchestration.get("paused_event_captured")),
        "captured_event_count": orchestration.get("captured_event_count", 0),
        "callframe_count": orchestration.get("callframe_count", 0),
        "live_callframe_recovery_ready": _boolish(orchestration.get("live_callframe_recovery_ready")),
        "next_action": _string(orchestration.get("next_action")),
        "blockers": orchestration.get("blockers") if isinstance(orchestration.get("blockers"), list) else [],
    }


def _continuation_checkpoint_diagnostics_for_review(checkpoint: dict[str, Any]) -> dict[str, Any]:
    if not checkpoint:
        return {}
    return {
        "status": _string(checkpoint.get("status") or "unknown"),
        "paused_event_captured": _boolish(checkpoint.get("paused_event_captured")),
        "callframe_count": checkpoint.get("callframe_count", 0),
        "selected_callframe_id_present": bool(checkpoint.get("selected_callframe_id")),
        "live_callframe_recovered": _boolish(checkpoint.get("live_callframe_recovered")),
        "continuation_ready_for_next_action": _boolish(checkpoint.get("continuation_ready_for_next_action")),
        "continuation_ready_for_next_capture_plan": _boolish(checkpoint.get("continuation_ready_for_next_capture_plan")),
        "manual_checkpoint_required": _boolish(checkpoint.get("manual_checkpoint_required")),
        "next_action": _string(checkpoint.get("next_action")),
        "blockers": checkpoint.get("blockers") if isinstance(checkpoint.get("blockers"), list) else [],
    }

def _multi_step_continuation_workflow_diagnostics_for_review(workflow: dict[str, Any]) -> dict[str, Any]:
    if not workflow:
        return {}
    return {
        "status": _string(workflow.get("status") or "unknown"),
        "workflow_id": _string(workflow.get("workflow_id")),
        "planned_step_count": workflow.get("planned_step_count", 0),
        "max_planned_steps": workflow.get("max_planned_steps", 0),
        "execute_at_most_one_action_per_review": _boolish(workflow.get("execute_at_most_one_action_per_review")),
        "manual_checkpoint_required_after_each_step": _boolish(workflow.get("manual_checkpoint_required_after_each_step")),
        "automatic_loop": _boolish(workflow.get("automatic_loop")),
        "duplicate_fingerprints": workflow.get("duplicate_fingerprints") if isinstance(workflow.get("duplicate_fingerprints"), list) else [],
        "blockers": workflow.get("blockers") if isinstance(workflow.get("blockers"), list) else [],
    }


def _multi_step_continuation_execution_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    if not execution:
        return {}
    return {
        "status": _string(execution.get("status") or "unknown"),
        "workflow_id": _string(execution.get("workflow_id")),
        "selected_step_index": execution.get("selected_step_index"),
        "selected_method": _string(execution.get("selected_method")),
        "executor_artifact": _string(execution.get("executor_artifact")),
        "paused_event_captured": _boolish(execution.get("paused_event_captured")),
        "manual_checkpoint_required_after_step": _boolish(execution.get("manual_checkpoint_required_after_step")),
        "multi_step_iteration_executed": _boolish(execution.get("multi_step_iteration_executed")),
        "automatic_loop": _boolish(execution.get("automatic_loop")),
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }


def _multi_step_loop_plan_diagnostics_for_review(loop_plan: dict[str, Any]) -> dict[str, Any]:
    if not loop_plan:
        return {}
    return {
        "status": _string(loop_plan.get("status") or "unknown"),
        "loop_id": _string(loop_plan.get("loop_id")),
        "workflow_id": _string(loop_plan.get("workflow_id")),
        "completed_iteration_count": loop_plan.get("completed_iteration_count", 0),
        "remaining_iteration_count": loop_plan.get("remaining_iteration_count", 0),
        "planned_iteration_count": loop_plan.get("planned_iteration_count", 0),
        "ready_for_review": _boolish(loop_plan.get("ready_for_review")),
        "next_iteration_reviewable": _boolish(_nested_get(loop_plan, "readiness", "next_loop_iteration_reviewable")),
        "automatic_multi_step_loop_supported": _boolish(_nested_get(loop_plan, "readiness", "automatic_multi_step_loop_supported")),
        "automatic_queue_advance_supported": _boolish(_nested_get(loop_plan, "readiness", "automatic_queue_advance_supported")),
        "next_action": _string(loop_plan.get("next_action")),
        "blockers": loop_plan.get("blockers") if isinstance(loop_plan.get("blockers"), list) else [],
    }


def _multi_step_loop_execution_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    if not execution:
        return {}
    return {
        "status": _string(execution.get("status") or "unknown"),
        "loop_id": _string(execution.get("loop_id")),
        "workflow_id": _string(execution.get("workflow_id")),
        "selected_step_index": execution.get("selected_step_index"),
        "selected_method": _string(execution.get("selected_method")),
        "executor_artifact": _string(execution.get("executor_artifact")),
        "paused_event_captured": _boolish(execution.get("paused_event_captured")),
        "manual_checkpoint_required_after_iteration": _boolish(execution.get("manual_checkpoint_required_after_iteration")),
        "multi_step_loop_iteration_executed": _boolish(execution.get("multi_step_loop_iteration_executed")),
        "loop_advanced": _boolish(execution.get("loop_advanced")),
        "queue_advanced": _boolish(execution.get("queue_advanced")),
        "automatic_multi_step_loop": _boolish(execution.get("automatic_multi_step_loop")),
        "automatic_wrapper_continuation": _boolish(execution.get("automatic_wrapper_continuation")),
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }


def _automatic_loop_execution_result_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    policy = execution.get("side_effect_policy") if isinstance(execution.get("side_effect_policy"), dict) else {}
    return {
        "status": _string(execution.get("status") or "unknown"),
        "transaction_id": _string(execution.get("transaction_id")),
        "journal_id": _string(execution.get("journal_id")),
        "automatic_loop_executed": _boolish(execution.get("automatic_loop_executed")),
        "automatic_loop_one_iteration_executed": _boolish(execution.get("automatic_loop_one_iteration_executed")),
        "executed_iteration_count": execution.get("executed_iteration_count", 0),
        "checkpoint_required": _boolish(execution.get("checkpoint_required")),
        "loop_advanced": _boolish(execution.get("loop_advanced")),
        "queue_advanced": _boolish(execution.get("queue_advanced")),
        "long_lived_session_managed": _boolish(execution.get("long_lived_session_managed")),
        "calls_mcp": _boolish(policy.get("calls_mcp")),
        "mobile_runtime_used": _boolish(policy.get("mobile_runtime_used")),
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }


def _automatic_loop_followup_checkpoint_diagnostics_for_review(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(checkpoint.get("status") or "unknown"),
        "ready_for_review": _boolish(checkpoint.get("ready_for_review")),
        "transaction_id": _string(checkpoint.get("transaction_id")),
        "checkpoint_ready": _boolish(_nested_get(checkpoint, "checkpoint_review", "checkpoint_ready")),
        "next_loop_plan_ready": _boolish(_nested_get(checkpoint, "next_loop_review", "next_loop_plan_ready")),
        "next_iteration_reviewable": _boolish(_nested_get(checkpoint, "next_loop_review", "next_iteration_reviewable")),
        "checkpoint_written": _boolish(_nested_get(checkpoint, "side_effect_policy", "checkpoint_written")),
        "loop_advanced": _boolish(_nested_get(checkpoint, "side_effect_policy", "loop_advanced")),
        "queue_advanced": _boolish(_nested_get(checkpoint, "side_effect_policy", "queue_advanced")),
        "calls_mcp": _boolish(_nested_get(checkpoint, "side_effect_policy", "calls_mcp")),
        "mobile_runtime_used": _boolish(_nested_get(checkpoint, "side_effect_policy", "mobile_runtime_used")),
        "blockers": checkpoint.get("blockers") if isinstance(checkpoint.get("blockers"), list) else [],
    }


def _automatic_loop_next_iteration_plan_diagnostics_for_review(plan: dict[str, Any]) -> dict[str, Any]:
    policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
    return {
        "status": _string(plan.get("status") or "unknown"),
        "ready_for_review": _boolish(plan.get("ready_for_review")),
        "transaction_id": _string(plan.get("transaction_id")),
        "followup_checkpoint_ready": _boolish(_nested_get(plan, "checkpoint_review", "followup_checkpoint_ready")),
        "continuation_checkpoint_ready": _boolish(_nested_get(plan, "checkpoint_review", "continuation_checkpoint_ready")),
        "next_loop_plan_ready": _boolish(_nested_get(plan, "next_iteration", "next_loop_plan_ready")),
        "next_iteration_reviewable": _boolish(_nested_get(plan, "next_iteration", "next_iteration_reviewable")),
        "fresh_live_callframe_recovered": _boolish(_nested_get(plan, "next_iteration", "fresh_live_callframe_recovered")),
        "requires_explicit_execution_approval": _boolish(_nested_get(plan, "execution_review_gates", "requires_explicit_execution_approval")),
        "would_execute_next_iteration": _boolish(policy.get("would_execute_next_iteration")),
        "loop_advanced": _boolish(policy.get("loop_advanced")),
        "queue_advanced": _boolish(policy.get("queue_advanced")),
        "calls_mcp": _boolish(policy.get("calls_mcp")),
        "mobile_runtime_used": _boolish(policy.get("mobile_runtime_used")),
        "blockers": plan.get("blockers") if isinstance(plan.get("blockers"), list) else [],
    }


def _automatic_loop_next_iteration_execution_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    policy = execution.get("side_effect_policy") if isinstance(execution.get("side_effect_policy"), dict) else {}
    return {
        "status": _string(execution.get("status") or "unknown"),
        "transaction_id": _string(execution.get("transaction_id")),
        "journal_id": _string(execution.get("journal_id")),
        "automatic_loop_next_iteration_executed": _boolish(execution.get("automatic_loop_next_iteration_executed")),
        "executed_iteration_count": execution.get("executed_iteration_count", 0),
        "checkpoint_required": _boolish(execution.get("checkpoint_required")),
        "loop_advanced": _boolish(execution.get("loop_advanced")),
        "queue_advanced": _boolish(execution.get("queue_advanced")),
        "long_lived_session_managed": _boolish(execution.get("long_lived_session_managed")),
        "calls_mcp": _boolish(policy.get("calls_mcp")),
        "mobile_runtime_used": _boolish(policy.get("mobile_runtime_used")),
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }


def _automatic_loop_next_iteration_followup_checkpoint_diagnostics_for_review(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(checkpoint.get("status") or "unknown"),
        "ready_for_review": _boolish(checkpoint.get("ready_for_review")),
        "transaction_id": _string(checkpoint.get("transaction_id")),
        "checkpoint_ready": _boolish(_nested_get(checkpoint, "checkpoint_review", "checkpoint_ready")),
        "next_loop_plan_ready": _boolish(_nested_get(checkpoint, "next_loop_review", "next_loop_plan_ready")),
        "next_iteration_reviewable": _boolish(_nested_get(checkpoint, "next_loop_review", "next_iteration_reviewable")),
        "checkpoint_written": _boolish(_nested_get(checkpoint, "side_effect_policy", "checkpoint_written")),
        "loop_advanced": _boolish(_nested_get(checkpoint, "side_effect_policy", "loop_advanced")),
        "queue_advanced": _boolish(_nested_get(checkpoint, "side_effect_policy", "queue_advanced")),
        "calls_mcp": _boolish(_nested_get(checkpoint, "side_effect_policy", "calls_mcp")),
        "mobile_runtime_used": _boolish(_nested_get(checkpoint, "side_effect_policy", "mobile_runtime_used")),
        "blockers": checkpoint.get("blockers") if isinstance(checkpoint.get("blockers"), list) else [],
    }


def _next_paused_event_capture_execution_diagnostics_for_review(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _string(execution.get("status") or "unknown"),
        "method": _string(execution.get("method")),
        "debugger_event_subscribed": _boolish(execution.get("debugger_event_subscribed")),
        "paused_event_captured": _boolish(execution.get("paused_event_captured")),
        "captured_event_count": execution.get("captured_event_count", 0),
        "ignored_event_count": execution.get("ignored_event_count", 0),
        "callframe_count": execution.get("callframe_count", 0),
        "live_callframe_recovery_ready": _boolish(execution.get("live_callframe_recovery_ready")),
        "blockers": execution.get("blockers") if isinstance(execution.get("blockers"), list) else [],
    }
