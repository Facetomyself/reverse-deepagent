from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read


DEBUGGER_ARTIFACT_REVIEW_VERSION = "2026-05-31.debugger-artifact-review-v1"
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
        execution_plan_target = execution_plan.get("target_attach_readiness_summary") if isinstance(execution_plan.get("target_attach_readiness_summary"), dict) else {}
        execution_plan_callframe = execution_plan.get("callframe_recovery_plan") if isinstance(execution_plan.get("callframe_recovery_plan"), dict) else {}
        execution_plan_gates = execution_plan.get("review_gates") if isinstance(execution_plan.get("review_gates"), dict) else {}

        artifact_count = sum(bool(item) for item in (session, timeline, paused, live_preflight, target_attach_readiness, cross_process_execution_plan, cross_process_session_lifecycle, cross_process_attach_probe, live_callframe_recovery, cross_process_one_action, pre_action_subscribe_and_action, next_paused_event_capture_plan, next_paused_event_capture_execution, cross_process_continuation_checkpoint, multi_step_continuation_workflow, multi_step_continuation_execution, multi_step_loop_plan, multi_step_loop_execution, automatic_loop_readiness)) + sum(bool(items) for items in (callframes, evaluations, mutation_audit, actions, timeline_entries))
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
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(blockers, warnings, preflight, readiness, execution_plan, session_lifecycle, attach_probe, callframe_recovery_artifact, one_action_execution, pre_action_orchestration, next_capture_execution, continuation_checkpoint, multi_step_workflow, multi_step_execution, multi_step_loop, multi_step_loop_exec, session, paused),
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
