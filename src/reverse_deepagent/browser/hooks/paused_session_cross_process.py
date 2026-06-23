from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.hooks.breakpoints import (
    BreakpointSpec,
    BreakpointResult,
    _first_dict,
    _optional_bool,
)

from reverse_deepagent.browser.hooks.paused_session_live import PAUSED_SESSION_LIVE_ACTIONS

@dataclass(slots=True)
class PausedSessionCrossProcessExecutionPlanSpec:
    """Plan-only executor design review after target attach readiness proof."""

    target_attach_readiness: dict[str, Any] = field(default_factory=dict)
    requested_action: str = "inspect"
    pause_session_id: str | None = None
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionCrossProcessExecutionPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_cross_process_execution_plan")
            or context.get("pausedSessionCrossProcessExecutionPlan")
            or context.get("paused-session-cross-process-execution-plan")
            or context.get("cross_process_paused_session_execution_plan")
            or context.get("crossProcessPausedSessionExecutionPlan")
            or context.get("plan_cross_process_paused_session_execution")
            or context.get("planCrossProcessPausedSessionExecution")
        )
        readiness_container = _first_dict(
            context,
            "paused_session_target_attach_readiness",
            "pausedSessionTargetAttachReadiness",
            "paused-session-target-attach-readiness",
            "target_attach_readiness",
            "targetAttachReadiness",
        )
        if isinstance(readiness_container.get("readiness"), dict):
            readiness = dict(readiness_container["readiness"])
        else:
            readiness = readiness_container
        if not requested and not readiness:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", readiness.get("requested_action", "inspect")),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or readiness.get("pause_session_id")
            or readiness.get("session_id")
        )
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            target_attach_readiness=readiness,
            requested_action=action,
            pause_session_id=str(session_id) if session_id else None,
            reviewer=str(reviewer) if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionCrossProcessExecutionPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionCrossProcessExecutionPlanManager:
    """Build a read-only execution-plan descriptor after target attach readiness proof."""

    LIVE_ACTIONS = PAUSED_SESSION_LIVE_ACTIONS

    def plan(self, spec: PausedSessionCrossProcessExecutionPlanSpec | None) -> PausedSessionCrossProcessExecutionPlanResult:
        policy = self._side_effect_policy()
        blockers = self._blockers(spec)
        status = "ready_for_executor_review" if not blockers else "blocked"
        plan = self._plan_payload(spec, blockers=blockers)
        return PausedSessionCrossProcessExecutionPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionCrossProcessExecutionPlanSpec | None) -> list[str]:
        blockers: list[str] = []
        readiness = spec.target_attach_readiness if spec else {}
        if not spec:
            blockers.append("cross_process_execution_plan_request_missing")
        if not readiness:
            blockers.append("target_attach_readiness_required")
        if readiness and readiness.get("status") == "blocked":
            blockers.append("target_attach_readiness_blocked")
        if readiness and not readiness.get("target_attach_readiness_proven"):
            blockers.append("target_attach_readiness_not_proven")
        if readiness and not _first_dict(readiness, "target_correlation").get("selected_target") and not _first_dict(readiness, "attachability").get("target_id_available"):
            blockers.append("target_attach_candidate_not_selected")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _plan_payload(cls, spec: PausedSessionCrossProcessExecutionPlanSpec | None, *, blockers: list[str]) -> dict[str, Any]:
        readiness = spec.target_attach_readiness if spec else {}
        action = spec.requested_action if spec else "inspect"
        target_correlation = _first_dict(readiness, "target_correlation")
        attachability = _first_dict(readiness, "attachability")
        callframe_recovery = _first_dict(readiness, "callframe_recovery")
        paused_session_evidence = _first_dict(readiness, "paused_session_evidence")
        target_attach_ready = bool(readiness.get("target_attach_readiness_proven")) and not any(
            blocker in blockers
            for blocker in (
                "target_attach_readiness_required",
                "target_attach_readiness_blocked",
                "target_attach_readiness_not_proven",
                "target_attach_candidate_not_selected",
            )
        )
        action_is_live = action in cls.LIVE_ACTIONS
        return {
            "schema_version": "reverse-deepagent.paused-session-cross-process-execution-plan.v1",
            "status": "ready_for_executor_review" if not blockers else "blocked",
            "pause_session_id": spec.pause_session_id if spec else readiness.get("pause_session_id"),
            "requested_action": action,
            "reviewer": spec.reviewer if spec else None,
            "target_attach_readiness_proven": bool(readiness.get("target_attach_readiness_proven")),
            "target_attach_readiness_status": readiness.get("status"),
            "execution_plan_ready_for_review": target_attach_ready,
            "cross_process_execution_ready": False,
            "cross_process_executor_implemented": True,
            "cross_process_action_supported": action_is_live,
            "cross_process_execution_readiness_reason": "requires_reviewed_attach_probe_live_callframe_recovery_and_one_action_execution_evidence",
            "full_cross_process_continuation_supported": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "capability_boundaries": [
                "full_cross_process_continuation_not_implemented",
                "reviewed_attach_probe_required",
                "durable_callframe_id_not_reusable_for_live_actions",
            ],
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers),
            "target_attach_readiness_summary": {
                "source": readiness.get("source"),
                "expected_url": target_correlation.get("expected_url"),
                "candidate_count": target_correlation.get("candidate_count", 0),
                "selected_target": target_correlation.get("selected_target") if isinstance(target_correlation.get("selected_target"), dict) else {},
                "target_id_available": bool(attachability.get("target_id_available")),
                "target_type_supported": bool(attachability.get("target_type_supported")),
                "requires_explicit_future_attach_step": bool(attachability.get("requires_explicit_future_attach_step", True)),
            },
            "callframe_recovery_plan": {
                "stable_live_callframe_available": bool(callframe_recovery.get("stable_live_callframe_available")),
                "durable_callframe_id_reusable": False,
                "requires_new_paused_event_after_attach": bool(callframe_recovery.get("requires_new_paused_event_after_attach", True)),
                "selected_callframe_has_id": bool(callframe_recovery.get("selected_callframe_has_id")),
            },
            "planned_stages": cls._planned_stages(action=action, action_is_live=action_is_live),
            "review_gates": {
                "target_attach_readiness_review_required": True,
                "attach_probe_review_required": True,
                "live_callframe_recovery_review_required": action_is_live,
                "action_execution_review_required": action_is_live,
                "automatic_approval": False,
            },
            "paused_session_evidence": paused_session_evidence,
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "would_attach_cdp_target": False,
            "would_probe_cdp_target": False,
            "cdp_command_sent": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _planned_stages(*, action: str, action_is_live: bool) -> list[dict[str, Any]]:
        stages = [
            {
                "stage": "review_target_attach_readiness",
                "status": "planned",
                "side_effects": False,
                "description": "Reviewer confirms paused-session evidence and CDP target correlation.",
            },
            {
                "stage": "reviewed_attach_probe",
                "status": "review_gate_required",
                "side_effects": False,
                "description": "Reviewed attach-probe baseline may attach the correlated CDP target only after explicit review approval.",
            },
            {
                "stage": "live_callframe_recovery",
                "status": "required" if action_is_live else "not_required_for_inspect",
                "side_effects": False,
                "description": "Live callFrame recovery must observe a new paused event after attach; durable callFrameId is not reusable.",
            },
        ]
        if action_is_live:
            stages.append(
                {
                    "stage": f"reviewed_one_action_{action}_execution",
                    "status": "review_gate_required",
                    "side_effects": False,
                    "description": "One-action executor may run exactly one reviewed paused-session action after live callFrame recovery.",
                }
            )
        return stages

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "cross_process_execution_plan_request_missing": ("request", "No cross-process execution plan request was provided.", "request_cross_process_execution_plan"),
            "target_attach_readiness_required": ("readiness", "A paused-session target attach readiness artifact is required before planning executor follow-through.", "produce_paused_session_target_attach_readiness"),
            "target_attach_readiness_blocked": ("readiness", "The supplied target attach readiness artifact is blocked.", "resolve_target_attach_readiness_blockers"),
            "target_attach_readiness_not_proven": ("readiness", "Target attach readiness has not been proven.", "collect_target_candidates_and_reassess_readiness"),
            "target_attach_candidate_not_selected": ("cdp_target", "No selected target / target id is available for future attach.", "refresh_target_candidates_before_executor_review"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_execution_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_execution_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_execution_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if "target_attach_readiness_required" in blockers:
            return "produce_paused_session_target_attach_readiness"
        if any(blocker.startswith("target_attach_readiness") or blocker == "target_attach_candidate_not_selected" for blocker in blockers):
            return "resolve_target_attach_readiness_blockers"
        return "run_reviewed_cross_process_attach_probe_next"


@dataclass(slots=True)
class PausedSessionCrossProcessSessionLifecycleSpec:
    """Read-only lifecycle descriptor for cross-process paused-session continuation.

    This descriptor only normalizes existing evidence. It does not attach targets, probe CDP,
    enable Debugger, recover callFrames, subscribe to events, execute actions, or loop.
    """

    live_continuation_preflight: dict[str, Any] = field(default_factory=dict)
    target_attach_readiness: dict[str, Any] = field(default_factory=dict)
    cross_process_execution_plan: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    next_paused_event_capture_execution: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    multi_step_execution: dict[str, Any] = field(default_factory=dict)
    requested_action: str = "inspect"
    pause_session_id: str | None = None
    target_id: str | None = None
    requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionCrossProcessSessionLifecycleSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_cross_process_session_lifecycle")
            or context.get("pausedSessionCrossProcessSessionLifecycle")
            or context.get("paused-session-cross-process-session-lifecycle")
            or context.get("cross_process_session_lifecycle")
            or context.get("crossProcessSessionLifecycle")
            or context.get("review_paused_session_lifecycle")
            or context.get("reviewPausedSessionLifecycle")
            or context.get("paused_session_lifecycle")
            or context.get("pausedSessionLifecycle")
        )
        preflight = cls._nested(
            _first_dict(
                context,
                "paused_session_live_continuation_preflight",
                "pausedSessionLiveContinuationPreflight",
                "paused-session-live-continuation-preflight",
                "live_continuation_preflight",
                "liveContinuationPreflight",
            ),
            "preflight",
        )
        readiness = cls._nested(
            _first_dict(
                context,
                "paused_session_target_attach_readiness",
                "pausedSessionTargetAttachReadiness",
                "paused-session-target-attach-readiness",
                "target_attach_readiness",
                "targetAttachReadiness",
            ),
            "readiness",
        )
        plan = cls._nested(
            _first_dict(
                context,
                "paused_session_cross_process_execution_plan",
                "pausedSessionCrossProcessExecutionPlan",
                "paused-session-cross-process-execution-plan",
                "cross_process_execution_plan",
                "crossProcessExecutionPlan",
            ),
            "plan",
        )
        attach_probe = cls._nested(
            _first_dict(
                context,
                "paused_session_cross_process_attach_probe",
                "pausedSessionCrossProcessAttachProbe",
                "paused-session-cross-process-attach-probe",
                "cross_process_attach_probe",
                "crossProcessAttachProbe",
            ),
            "probe",
        )
        recovery = cls._nested(
            _first_dict(
                context,
                "paused_session_live_callframe_recovery",
                "pausedSessionLiveCallframeRecovery",
                "paused-session-live-callframe-recovery",
                "live_callframe_recovery",
                "liveCallframeRecovery",
            ),
            "recovery",
        )
        capture_execution = cls._nested(
            _first_dict(
                context,
                "paused_session_next_paused_event_capture_execution",
                "pausedSessionNextPausedEventCaptureExecution",
                "paused-session-next-paused-event-capture-execution",
                "next_paused_event_capture_execution",
                "nextPausedEventCaptureExecution",
            ),
            "execution",
        )
        checkpoint = cls._nested(
            _first_dict(
                context,
                "paused_session_cross_process_continuation_checkpoint",
                "pausedSessionCrossProcessContinuationCheckpoint",
                "paused-session-cross-process-continuation-checkpoint",
                "continuation_checkpoint",
                "continuationCheckpoint",
            ),
            "checkpoint",
        )
        workflow = cls._nested(
            _first_dict(
                context,
                "paused_session_multi_step_continuation_workflow",
                "pausedSessionMultiStepContinuationWorkflow",
                "paused-session-multi-step-continuation-workflow",
                "multi_step_continuation_workflow",
                "multiStepContinuationWorkflow",
            ),
            "workflow",
        )
        execution = cls._nested(
            _first_dict(
                context,
                "paused_session_multi_step_continuation_execution",
                "pausedSessionMultiStepContinuationExecution",
                "paused-session-multi-step-continuation-execution",
                "multi_step_continuation_execution",
                "multiStepContinuationExecution",
            ),
            "execution",
        )
        if not requested and not any((preflight, readiness, plan, attach_probe, recovery, capture_execution, checkpoint, workflow, execution)):
            return None
        action = str(
            context.get(
                "requested_action",
                context.get(
                    "requestedAction",
                    execution.get("selected_action")
                    or execution.get("requested_action")
                    or workflow.get("requested_action")
                    or checkpoint.get("requested_action")
                    or recovery.get("requested_action")
                    or plan.get("requested_action")
                    or preflight.get("requested_action")
                    or "inspect",
                ),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        pause_session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or execution.get("pause_session_id")
            or workflow.get("pause_session_id")
            or checkpoint.get("pause_session_id")
            or recovery.get("pause_session_id")
            or attach_probe.get("pause_session_id")
            or plan.get("pause_session_id")
            or readiness.get("pause_session_id")
            or preflight.get("pause_session_id")
            or preflight.get("session_id")
        )
        target_id = (
            context.get("target_id")
            or context.get("targetId")
            or recovery.get("target_id")
            or attach_probe.get("target_id")
            or cls._selected_target_id(readiness)
            or cls._selected_target_id(plan.get("target_attach_readiness_summary") if isinstance(plan.get("target_attach_readiness_summary"), dict) else {})
        )
        return cls(
            live_continuation_preflight=preflight,
            target_attach_readiness=readiness,
            cross_process_execution_plan=plan,
            cross_process_attach_probe=attach_probe,
            live_callframe_recovery=recovery,
            next_paused_event_capture_execution=capture_execution,
            continuation_checkpoint=checkpoint,
            multi_step_workflow=workflow,
            multi_step_execution=execution,
            requested_action=action,
            pause_session_id=str(pause_session_id) if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            requested=requested,
        )

    @staticmethod
    def _nested(value: dict[str, Any], key: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        nested = value.get(key)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(value)

    @staticmethod
    def _selected_target_id(value: dict[str, Any]) -> str:
        if not isinstance(value, dict):
            return ""
        selected = value.get("selected_target") if isinstance(value.get("selected_target"), dict) else {}
        if not selected:
            correlation = value.get("target_correlation") if isinstance(value.get("target_correlation"), dict) else {}
            selected = correlation.get("selected_target") if isinstance(correlation.get("selected_target"), dict) else {}
        if not selected:
            summary = value.get("target_attach_readiness_summary") if isinstance(value.get("target_attach_readiness_summary"), dict) else {}
            selected = summary.get("selected_target") if isinstance(summary.get("selected_target"), dict) else {}
        target_id = selected.get("target_id") or selected.get("targetId") or selected.get("id") or value.get("target_id") or value.get("targetId")
        return str(target_id).strip() if target_id is not None else ""


@dataclass(slots=True)
class PausedSessionCrossProcessSessionLifecycleResult:
    status: str
    lifecycle: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "lifecycle": self.lifecycle,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionCrossProcessSessionLifecycleManager:
    """Read-only lifecycle reviewer for cross-process paused-session continuation evidence."""

    def review(self, spec: PausedSessionCrossProcessSessionLifecycleSpec | None) -> PausedSessionCrossProcessSessionLifecycleResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionCrossProcessSessionLifecycleResult(
            status=status,
            lifecycle=payload,
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: PausedSessionCrossProcessSessionLifecycleSpec | None) -> list[str]:
        if spec is None:
            return ["paused_session_lifecycle_request_missing"]
        blockers: list[str] = []
        if not spec.pause_session_id:
            blockers.append("pause_session_id_required")
        if not spec.target_id:
            blockers.append("target_id_required")
        if not any((spec.live_continuation_preflight, spec.target_attach_readiness, spec.cross_process_execution_plan, spec.cross_process_attach_probe, spec.live_callframe_recovery, spec.continuation_checkpoint, spec.multi_step_workflow, spec.multi_step_execution)):
            blockers.append("paused_session_lifecycle_evidence_required")
        if spec.target_attach_readiness:
            readiness_status = str(spec.target_attach_readiness.get("status") or "")
            if readiness_status in {"blocked", "failed", "failure", "error", "unsupported"} or spec.target_attach_readiness.get("target_attach_readiness_proven") is False:
                blockers.append("target_attach_readiness_not_ready")
        if spec.cross_process_execution_plan:
            plan_status = str(spec.cross_process_execution_plan.get("status") or "")
            if plan_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("cross_process_execution_plan_not_ready")
        if spec.cross_process_attach_probe:
            probe_status = str(spec.cross_process_attach_probe.get("status") or "")
            if probe_status in {"failed", "failure", "error", "unsupported"}:
                blockers.append("attach_probe_failed")
        if spec.live_callframe_recovery:
            recovery_status = str(spec.live_callframe_recovery.get("status") or "")
            if recovery_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("live_callframe_recovery_not_ready")
        if spec.multi_step_execution:
            execution_status = str(spec.multi_step_execution.get("status") or "")
            if execution_status in {"failed", "failure", "error", "unsupported"}:
                blockers.append("multi_step_execution_failed")
        if spec.requested_action in PAUSED_SESSION_LIVE_ACTIONS and not cls._has_live_callframe_path(spec):
            blockers.append("live_callframe_recovery_or_checkpoint_required_for_live_action")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _has_live_callframe_path(cls, spec: PausedSessionCrossProcessSessionLifecycleSpec) -> bool:
        recovery = spec.live_callframe_recovery
        checkpoint = spec.continuation_checkpoint
        workflow = spec.multi_step_workflow
        execution = spec.multi_step_execution
        return bool(
            (recovery and recovery.get("status") == "recovered" and recovery.get("live_callframe_recovered") is True)
            or (checkpoint and (checkpoint.get("continuation_ready_for_next_action") is True or checkpoint.get("live_callframe_recovery_ready") is True or str(checkpoint.get("status") or "") in {"ready_for_next_action_review", "ready_for_live_callframe_recovery"}))
            or (workflow and str(workflow.get("status") or "") in {"ready_for_review", "planned"})
            or (execution and str(execution.get("status") or "") in {"executed", "captured", "ready_for_review"})
        )

    @classmethod
    def _payload(cls, spec: PausedSessionCrossProcessSessionLifecycleSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        preflight = spec.live_continuation_preflight if spec else {}
        readiness = spec.target_attach_readiness if spec else {}
        plan = spec.cross_process_execution_plan if spec else {}
        probe = spec.cross_process_attach_probe if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        capture = spec.next_paused_event_capture_execution if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        workflow = spec.multi_step_workflow if spec else {}
        execution = spec.multi_step_execution if spec else {}
        attached_session_id = probe.get("attached_session_id") or recovery.get("attached_session_id") or execution.get("attached_session_id")
        live_callframe_id = recovery.get("live_callframe_id") or execution.get("live_callframe_id") or checkpoint.get("live_callframe_id")
        target_attached = bool(probe.get("target_attached") or recovery.get("target_attached") or execution.get("target_attached"))
        target_detached = bool(probe.get("target_detached"))
        callframe_recovered = bool(recovery.get("live_callframe_recovered") or execution.get("live_callframe_recovered"))
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-cross-process-session-lifecycle.v1",
            "status": status,
            "ready_for_review": ready,
            "pause_session_id": spec.pause_session_id if spec else None,
            "target_id": spec.target_id if spec else None,
            "requested_action": spec.requested_action if spec else "inspect",
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "evidence_statuses": {
                "live_continuation_preflight": preflight.get("status"),
                "target_attach_readiness": readiness.get("status"),
                "cross_process_execution_plan": plan.get("status"),
                "cross_process_attach_probe": probe.get("status"),
                "live_callframe_recovery": recovery.get("status"),
                "next_paused_event_capture_execution": capture.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "multi_step_workflow": workflow.get("status"),
                "multi_step_execution": execution.get("status"),
            },
            "session_diagnostics": {
                "live_preflight_available": bool(preflight),
                "live_continuation_available": bool(preflight.get("live_continuation_available") or preflight.get("available")),
                "durable_snapshot_source": preflight.get("source") == "durable_snapshot" or preflight.get("source") == "artifact",
                "attached_session_id_present": bool(attached_session_id),
                "attached_session_retained": bool(attached_session_id and not target_detached),
                "target_attached": target_attached,
                "target_detached": target_detached,
                "target_lifecycle_observed": bool(probe or recovery or execution),
            },
            "target_diagnostics": {
                "target_attach_readiness_proven": bool(readiness.get("target_attach_readiness_proven") or plan.get("target_attach_readiness_proven")),
                "target_attach_candidate_selected": bool(spec and spec.target_id),
                "target_attach_probe_status": probe.get("status"),
                "target_attached": target_attached,
                "target_detached": target_detached,
                "target_still_attached_by_evidence": bool(target_attached and not target_detached),
                "target_still_alive_proven": False,
                "target_still_alive_proof_requires_cdp_probe": True,
            },
            "debugger_diagnostics": {
                "debugger_domain_enabled_by_lifecycle_manager": False,
                "live_callframe_recovered": callframe_recovered,
                "live_callframe_id_present": bool(live_callframe_id),
                "fresh_paused_event_after_attach": bool(recovery.get("fresh_paused_event_after_attach") or capture.get("paused_event_captured")),
                "next_paused_event_captured": bool(capture.get("paused_event_captured")),
                "continuation_ready_for_next_action": bool(checkpoint.get("continuation_ready_for_next_action")),
                "continuation_ready_for_live_callframe_recovery": bool(checkpoint.get("live_callframe_recovery_ready")),
            },
            "continuation_diagnostics": {
                "multi_step_workflow_ready": str(workflow.get("status") or "") in {"ready_for_review", "planned"},
                "multi_step_iteration_executed": bool(execution.get("multi_step_iteration_executed")),
                "automatic_multi_step_loop_supported": False,
                "automatic_live_callframe_recovery_supported": False,
                "automatic_wrapper_continuation_supported": False,
                "next_manual_checkpoint_required": True,
            },
            "readiness": {
                "can_review_next_action": ready,
                "can_review_live_callframe_recovery": bool(checkpoint.get("live_callframe_recovery_ready") or capture.get("live_callframe_recovery_ready")),
                "requires_manual_review": True,
                "requires_fresh_evidence_before_action": True,
            },
            "next_action": cls._next_action(status=status, blockers=blockers, spec=spec),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "cdp_target_detached": False,
            "cdp_target_probed": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "live_callframe_recovered": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "automatic_multi_step_loop": False,
            "automatic_wrapper_continuation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "paused_session_lifecycle_request_missing": ("request", "No paused-session lifecycle review request was provided.", "request_paused_session_lifecycle_review"),
            "pause_session_id_required": ("session", "A pause_session_id is required to correlate lifecycle evidence.", "provide_pause_session_id"),
            "target_id_required": ("target", "A target_id or selected target evidence is required for cross-process lifecycle review.", "provide_target_attach_readiness_or_attach_probe"),
            "paused_session_lifecycle_evidence_required": ("evidence", "At least one paused-session continuation artifact is required.", "provide_paused_session_continuation_evidence"),
            "target_attach_readiness_not_ready": ("target", "Target attach readiness evidence is blocked or not proven.", "resolve_target_attach_readiness_blockers"),
            "cross_process_execution_plan_not_ready": ("plan", "Cross-process execution plan evidence is blocked.", "resolve_cross_process_execution_plan_blockers"),
            "attach_probe_failed": ("target", "Attach probe evidence failed or is unsupported.", "rerun_reviewed_attach_probe_or_refresh_target"),
            "live_callframe_recovery_not_ready": ("debugger", "Live callFrame recovery evidence is blocked or failed.", "capture_fresh_paused_event_after_attach"),
            "multi_step_execution_failed": ("debugger", "Multi-step one-iteration execution failed or is unsupported.", "review_multi_step_execution_failure"),
            "live_callframe_recovery_or_checkpoint_required_for_live_action": ("debugger", "Live actions require recovered live callFrame evidence or a continuation checkpoint.", "recover_live_callframe_or_checkpoint_continuation"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "review_paused_session_lifecycle"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "review_paused_session_lifecycle"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "review_paused_session_lifecycle"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], spec: PausedSessionCrossProcessSessionLifecycleSpec | None) -> str:
        if status == "ready_for_review":
            return "review_paused_session_lifecycle_before_next_continuation_step"
        if "target_attach_readiness_not_ready" in blockers or "target_id_required" in blockers:
            return "produce_or_fix_target_attach_readiness"
        if "cross_process_execution_plan_not_ready" in blockers:
            return "resolve_cross_process_execution_plan_blockers"
        if "attach_probe_failed" in blockers:
            return "rerun_reviewed_attach_probe_or_refresh_target"
        if "live_callframe_recovery_not_ready" in blockers or "live_callframe_recovery_or_checkpoint_required_for_live_action" in blockers:
            return "recover_live_callframe_or_checkpoint_continuation"
        if "paused_session_lifecycle_evidence_required" in blockers:
            return "provide_paused_session_continuation_evidence"
        if "pause_session_id_required" in blockers:
            return "provide_pause_session_id"
        return "resolve_paused_session_lifecycle_blockers"


@dataclass(slots=True)
class PausedSessionCrossProcessAttachProbeSpec:
    """Explicit reviewed CDP target attach probe after cross-process execution planning."""

    cross_process_execution_plan: dict[str, Any] = field(default_factory=dict)
    target_attach_readiness: dict[str, Any] = field(default_factory=dict)
    execute_probe: bool = False
    review_approved: bool = False
    detach_after_probe: bool = True
    reviewer: str | None = None
    target_id: str | None = None
    pause_session_id: str | None = None
    requested_action: str = "inspect"

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionCrossProcessAttachProbeSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_cross_process_attach_probe")
            or context.get("pausedSessionCrossProcessAttachProbe")
            or context.get("paused-session-cross-process-attach-probe")
            or context.get("cross_process_paused_session_attach_probe")
            or context.get("crossProcessPausedSessionAttachProbe")
            or context.get("execute_cross_process_attach_probe")
            or context.get("executeCrossProcessAttachProbe")
        )
        plan_container = _first_dict(
            context,
            "paused_session_cross_process_execution_plan",
            "pausedSessionCrossProcessExecutionPlan",
            "paused-session-cross-process-execution-plan",
            "cross_process_execution_plan",
            "crossProcessExecutionPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        readiness_container = _first_dict(
            context,
            "paused_session_target_attach_readiness",
            "pausedSessionTargetAttachReadiness",
            "paused-session-target-attach-readiness",
            "target_attach_readiness",
            "targetAttachReadiness",
        )
        readiness = dict(readiness_container.get("readiness")) if isinstance(readiness_container.get("readiness"), dict) else readiness_container
        if not requested and not plan and not readiness:
            return None
        target_id = (
            context.get("target_id")
            or context.get("targetId")
            or cls._target_id_from_plan(plan)
            or cls._target_id_from_readiness(readiness)
        )
        session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or plan.get("pause_session_id")
            or readiness.get("pause_session_id")
        )
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", plan.get("requested_action", readiness.get("requested_action", "inspect"))),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        execute_raw = context.get("execute_cross_process_attach_probe", context.get("executeCrossProcessAttachProbe", context.get("execute_probe", context.get("executeProbe", False))))
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        detach_raw = context.get("detach_after_probe", context.get("detachAfterProbe", True))
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            cross_process_execution_plan=plan,
            target_attach_readiness=readiness,
            execute_probe=bool(execute_raw),
            review_approved=bool(approved_raw),
            detach_after_probe=bool(detach_raw),
            reviewer=str(reviewer) if reviewer else None,
            target_id=str(target_id).strip() if target_id else None,
            pause_session_id=str(session_id) if session_id else None,
            requested_action=action,
        )

    @staticmethod
    def _target_id_from_plan(plan: dict[str, Any]) -> str:
        summary = plan.get("target_attach_readiness_summary") if isinstance(plan.get("target_attach_readiness_summary"), dict) else {}
        selected = summary.get("selected_target") if isinstance(summary.get("selected_target"), dict) else {}
        value = selected.get("target_id") or selected.get("targetId") or selected.get("id")
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _target_id_from_readiness(readiness: dict[str, Any]) -> str:
        correlation = readiness.get("target_correlation") if isinstance(readiness.get("target_correlation"), dict) else {}
        selected = correlation.get("selected_target") if isinstance(correlation.get("selected_target"), dict) else {}
        value = selected.get("target_id") or selected.get("targetId") or selected.get("id")
        return str(value).strip() if value is not None else ""


@dataclass(slots=True)
class PausedSessionCrossProcessAttachProbeResult:
    status: str
    probe: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "probe": self.probe,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionCrossProcessAttachProbeManager:
    """Run one explicit reviewed Target.attachToTarget probe without live debugger actions."""

    def probe(self, page: BrowserPage | None, spec: PausedSessionCrossProcessAttachProbeSpec | None) -> PausedSessionCrossProcessAttachProbeResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._probe_payload(spec, status="blocked", blockers=blockers)
            return PausedSessionCrossProcessAttachProbeResult(status="blocked", probe=payload, side_effect_policy=self._side_effect_policy(False), reason=blockers[0])
        if spec and not spec.execute_probe:
            payload = self._probe_payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionCrossProcessAttachProbeResult(status="ready_for_review", probe=payload, side_effect_policy=self._side_effect_policy(False))
        if spec and not spec.review_approved:
            payload = self._probe_payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionCrossProcessAttachProbeResult(status="review_required", probe=payload, side_effect_policy=self._side_effect_policy(False), reason="review_approval_required")
        if page is None:
            payload = self._probe_payload(spec, status="blocked", blockers=["browser_page_required"])
            return PausedSessionCrossProcessAttachProbeResult(status="blocked", probe=payload, side_effect_policy=self._side_effect_policy(False), reason="browser_page_required")
        session = page.cdp_session()
        if session is None:
            payload = self._probe_payload(spec, status="blocked", blockers=["cdp_session_required"])
            return PausedSessionCrossProcessAttachProbeResult(status="blocked", probe=payload, side_effect_policy=self._side_effect_policy(False), reason="cdp_session_required")
        methods: list[str] = []
        attach_payload: dict[str, Any] = {}
        detach_payload: dict[str, Any] = {}
        detach_completed = False
        error: str | None = None
        session_id = ""
        try:
            methods.append("Target.attachToTarget")
            attach_result = session.send("Target.attachToTarget", {"targetId": spec.target_id, "flatten": True})
            attach_payload = attach_result if isinstance(attach_result, dict) else {"result": attach_result}
            session_id = str(attach_payload.get("sessionId") or attach_payload.get("session_id") or "")
            if spec.detach_after_probe and session_id:
                methods.append("Target.detachFromTarget")
                detach_result = session.send("Target.detachFromTarget", {"sessionId": session_id})
                detach_payload = detach_result if isinstance(detach_result, dict) else {"result": detach_result}
                detach_completed = True
        except Exception as exc:
            error = str(exc)
        status = "attached" if session_id and not error else "failed"
        blockers_after = [] if status == "attached" else ["target_attach_probe_failed"]
        payload = self._probe_payload(
            spec,
            status=status,
            blockers=blockers_after,
            session_id=session_id,
            attach_payload=attach_payload,
            detach_payload={**detach_payload, "__detach_completed": True} if detach_completed else detach_payload,
            cdp_methods=methods,
            error=error,
        )
        return PausedSessionCrossProcessAttachProbeResult(
            status=status,
            probe=payload,
            side_effect_policy=self._side_effect_policy(True, target_attached=bool(session_id), target_detached=detach_completed),
            reason=blockers_after[0] if blockers_after else None,
            error=error,
        )

    @staticmethod
    def _blockers(spec: PausedSessionCrossProcessAttachProbeSpec | None) -> list[str]:
        blockers: list[str] = []
        if spec is None:
            blockers.append("cross_process_attach_probe_request_missing")
            return blockers
        plan = spec.cross_process_execution_plan
        readiness = spec.target_attach_readiness
        if not plan:
            blockers.append("cross_process_execution_plan_required")
        if plan and plan.get("status") == "blocked":
            blockers.append("cross_process_execution_plan_blocked")
        if plan and not plan.get("execution_plan_ready_for_review"):
            blockers.append("cross_process_execution_plan_not_ready")
        if not readiness and not plan.get("target_attach_readiness_proven"):
            blockers.append("target_attach_readiness_required")
        if not spec.target_id:
            blockers.append("target_id_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _probe_payload(
        cls,
        spec: PausedSessionCrossProcessAttachProbeSpec | None,
        *,
        status: str,
        blockers: list[str],
        session_id: str = "",
        attach_payload: dict[str, Any] | None = None,
        detach_payload: dict[str, Any] | None = None,
        cdp_methods: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        attach_payload = attach_payload or {}
        detach_payload = detach_payload or {}
        plan = spec.cross_process_execution_plan if spec else {}
        return {
            "schema_version": "reverse-deepagent.paused-session-cross-process-attach-probe.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": spec.requested_action if spec else None,
            "target_id": spec.target_id if spec else None,
            "reviewer": spec.reviewer if spec else None,
            "execute_probe_requested": bool(spec and spec.execute_probe),
            "review_approved": bool(spec and spec.review_approved),
            "detach_after_probe": bool(spec.detach_after_probe) if spec else True,
            "attach_attempted": bool(cdp_methods and "Target.attachToTarget" in cdp_methods),
            "target_attached": bool(session_id),
            "attached_session_id": session_id,
            "detach_attempted": bool(cdp_methods and "Target.detachFromTarget" in cdp_methods),
            "target_detached": bool(detach_payload.get("__detach_completed") or detach_payload),
            "debugger_domain_enabled": False,
            "live_callframe_recovered": False,
            "live_action_executed": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "cdp_methods": cdp_methods or [],
            "attach_result_summary": cls._redact_attach_payload(attach_payload or {}),
            "detach_result_summary": cls._redact_attach_payload({key: value for key, value in (detach_payload or {}).items() if key != "__detach_completed"}),
            "cross_process_execution_plan_summary": {
                "status": plan.get("status"),
                "execution_plan_ready_for_review": bool(plan.get("execution_plan_ready_for_review")),
                "cross_process_execution_ready": bool(plan.get("cross_process_execution_ready")),
                "cross_process_executor_implemented": bool(plan.get("cross_process_executor_implemented")),
            },
            "side_effect_policy": cls._side_effect_policy(bool(cdp_methods), target_attached=bool(session_id), target_detached=bool(detach_payload.get("__detach_completed") or detach_payload)),
            "error": error,
        }

    @staticmethod
    def _redact_attach_payload(payload: dict[str, Any]) -> dict[str, Any]:
        if not payload:
            return {}
        return {
            "session_id_present": bool(payload.get("sessionId") or payload.get("session_id")),
            "keys": sorted(str(key) for key in payload.keys()),
        }

    @staticmethod
    def _side_effect_policy(cdp_sent: bool, *, target_attached: bool = False, target_detached: bool = False) -> dict[str, Any]:
        return {
            "read_only": not cdp_sent,
            "files_mutated": False,
            "artifacts_written": False,
            "would_attach_cdp_target": False,
            "cdp_command_sent": cdp_sent,
            "cdp_target_attached": target_attached,
            "cdp_target_detached": target_detached,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "live_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "cross_process_attach_probe_request_missing": ("request", "No cross-process attach probe request was provided.", "request_cross_process_attach_probe"),
            "cross_process_execution_plan_required": ("plan", "A cross-process execution plan descriptor is required before attach probing.", "produce_cross_process_execution_plan"),
            "cross_process_execution_plan_blocked": ("plan", "The supplied cross-process execution plan is blocked.", "resolve_cross_process_execution_plan_blockers"),
            "cross_process_execution_plan_not_ready": ("plan", "The supplied cross-process execution plan is not ready for review.", "review_cross_process_execution_plan"),
            "target_attach_readiness_required": ("readiness", "Target attach readiness evidence is required before attach probing.", "produce_paused_session_target_attach_readiness"),
            "target_id_required": ("cdp_target", "A target id is required for Target.attachToTarget.", "collect_target_id_before_attach_probe"),
            "review_approval_required": ("review", "Executing Target.attachToTarget requires explicit review approval.", "approve_cross_process_attach_probe"),
            "browser_page_required": ("runtime", "A BrowserPage with CDP access is required for the attach probe.", "provide_browser_page_for_attach_probe"),
            "cdp_session_required": ("runtime", "The active page does not expose a CDP session.", "use_cdp_capable_browser_provider"),
            "target_attach_probe_failed": ("cdp_target", "Target.attachToTarget failed or did not return a session id.", "inspect_attach_probe_error"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_attach_probe"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_attach_probe"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_attach_probe"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if "review_approval_required" in blockers:
            return "approve_cross_process_attach_probe"
        if any(blocker in blockers for blocker in ("cross_process_execution_plan_required", "cross_process_execution_plan_blocked", "cross_process_execution_plan_not_ready")):
            return "resolve_cross_process_execution_plan_blockers"
        if "target_id_required" in blockers:
            return "collect_target_id_before_attach_probe"
        if status == "ready_for_review":
            return "approve_cross_process_attach_probe"
        if status == "attached":
            return "review_attach_probe_result_before_live_callframe_recovery"
        return "inspect_cross_process_attach_probe_blockers"


@dataclass(slots=True)
class PausedSessionCrossProcessOneActionSpec:
    """Execute exactly one reviewed live debugger action after callFrame recovery."""

    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_action: bool = False
    review_approved: bool = False
    requested_action: str = "resume"
    expression: str | None = None
    callframe_evaluation_policy: str = "read_only"
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionCrossProcessOneActionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_cross_process_one_action")
            or context.get("pausedSessionCrossProcessOneAction")
            or context.get("paused-session-cross-process-one-action")
            or context.get("cross_process_one_action")
            or context.get("crossProcessOneAction")
            or context.get("execute_cross_process_one_action")
            or context.get("executeCrossProcessOneAction")
            or context.get("cross_process_paused_session_action")
            or context.get("crossProcessPausedSessionAction")
        )
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
            "cross_process_live_callframe_recovery",
            "crossProcessLiveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        if not requested and not recovery:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", context.get("action", recovery.get("requested_action", "resume"))),
            )
            or "resume"
        ).strip().replace("-", "_").lower()
        execute_raw = context.get("execute_cross_process_one_action", context.get("executeCrossProcessOneAction", context.get("execute_action", context.get("executeAction", False))))
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        expression = context.get("expression") or context.get("callframe_expression") or context.get("callFrameExpression")
        policy = str(context.get("callframe_evaluation_policy", context.get("callFrameEvaluationPolicy", "read_only")) or "read_only").strip().replace("-", "_").lower()
        attached_session_id = (
            context.get("attached_session_id")
            or context.get("attachedSessionId")
            or recovery.get("attached_session_id")
            or attach_probe.get("attached_session_id")
        )
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or recovery.get("pause_session_id")
            or attach_probe.get("pause_session_id")
        )
        target_id = context.get("target_id") or context.get("targetId") or recovery.get("target_id") or attach_probe.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_action=bool(execute_raw),
            review_approved=bool(approved_raw),
            requested_action=action,
            expression=str(expression) if expression is not None else None,
            callframe_evaluation_policy=policy,
            pause_session_id=str(pause_session_id) if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            attached_session_id=str(attached_session_id).strip() if attached_session_id else None,
            live_callframe_id=str(live_callframe_id).strip() if live_callframe_id else None,
            reviewer=str(reviewer) if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionCrossProcessOneActionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionCrossProcessOneActionManager:
    """Run exactly one reviewed cross-process paused-session debugger action."""

    ACTION_METHODS = {
        "resume": "Debugger.resume",
        "step_over": "Debugger.stepOver",
        "stepover": "Debugger.stepOver",
        "over": "Debugger.stepOver",
        "step_into": "Debugger.stepInto",
        "stepinto": "Debugger.stepInto",
        "into": "Debugger.stepInto",
        "step_out": "Debugger.stepOut",
        "stepout": "Debugger.stepOut",
        "out": "Debugger.stepOut",
    }

    def execute(self, page: BrowserPage | None, spec: PausedSessionCrossProcessOneActionSpec | None) -> PausedSessionCrossProcessOneActionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionCrossProcessOneActionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False), reason=blockers[0])
        if spec and not spec.execute_action:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionCrossProcessOneActionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy(False))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionCrossProcessOneActionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy(False), reason="review_approval_required")
        if page is None:
            payload = self._payload(spec, status="blocked", blockers=["browser_page_required"])
            return PausedSessionCrossProcessOneActionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False), reason="browser_page_required")
        session = page.cdp_session()
        if session is None:
            payload = self._payload(spec, status="blocked", blockers=["cdp_session_required"])
            return PausedSessionCrossProcessOneActionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False), reason="cdp_session_required")

        assert spec is not None
        method = self._method_for_action(spec.requested_action)
        params = self._params_for_action(spec, method=method)
        methods = [method]
        error: str | None = None
        result_payload: Any = {}
        try:
            result_payload = session.send(method, params)
        except Exception as exc:
            error = str(exc)
        status = "executed" if error is None else "failed"
        blockers_after = [] if status == "executed" else ["cross_process_one_action_failed"]
        payload = self._payload(
            spec,
            status=status,
            blockers=blockers_after,
            cdp_methods=methods,
            cdp_params=params,
            action_result=result_payload,
            error=error,
        )
        policy = self._side_effect_policy(
            True,
            action=spec.requested_action,
            evaluation_sent=method == "Debugger.evaluateOnCallFrame",
        )
        return PausedSessionCrossProcessOneActionResult(status=status, execution=payload, side_effect_policy=policy, reason=blockers_after[0] if blockers_after else None, error=error)

    @classmethod
    def _blockers(cls, spec: PausedSessionCrossProcessOneActionSpec | None) -> list[str]:
        if spec is None:
            return ["cross_process_one_action_request_missing"]
        blockers: list[str] = []
        recovery = spec.live_callframe_recovery
        if not recovery:
            blockers.append("live_callframe_recovery_required")
        elif recovery.get("status") == "blocked" or not recovery.get("live_callframe_recovered"):
            blockers.append("live_callframe_recovery_blocked")
        if recovery.get("target_detached"):
            blockers.append("attached_session_retained_required")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required")
        if not spec.live_callframe_id:
            blockers.append("live_callframe_id_required")
        if not cls._method_for_action(spec.requested_action):
            blockers.append("unsupported_cross_process_action")
        if spec.requested_action in {"evaluate", "evaluate_on_callframe"}:
            if not spec.expression:
                blockers.append("callframe_expression_required")
            decision = cls._evaluation_policy_decision(spec.expression or "", spec.callframe_evaluation_policy)
            if decision["blocked"]:
                blockers.append("blocked_by_callframe_evaluation_policy")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionCrossProcessOneActionSpec | None,
        *,
        status: str,
        blockers: list[str],
        cdp_methods: list[str] | None = None,
        cdp_params: dict[str, Any] | None = None,
        action_result: Any = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
        recovery = spec.live_callframe_recovery if spec else {}
        action = spec.requested_action if spec else None
        method = cls._method_for_action(action or "")
        evaluation = {}
        if method == "Debugger.evaluateOnCallFrame" and cdp_methods:
            evaluation = BreakpointManager._normalize_callframe_evaluation(spec.expression or "", action_result, 0, spec.live_callframe_id or "") if spec else {}
            evaluation = BreakpointManager._with_evaluation_policy_metadata(evaluation, cls._evaluation_policy_decision(spec.expression or "", spec.callframe_evaluation_policy)) if spec else evaluation
        return {
            "schema_version": "reverse-deepagent.paused-session-cross-process-one-action-execution.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": action,
            "reviewer": spec.reviewer if spec else None,
            "target_id": spec.target_id if spec else None,
            "attached_session_id": spec.attached_session_id if spec else None,
            "live_callframe_id": spec.live_callframe_id if spec else None,
            "live_callframe_recovery_status": recovery.get("status"),
            "live_callframe_recovered": bool(recovery.get("live_callframe_recovered")),
            "execute_action_requested": bool(spec and spec.execute_action),
            "review_approved": bool(spec and spec.review_approved),
            "method": method,
            "expression": spec.expression if spec and method == "Debugger.evaluateOnCallFrame" else None,
            "callframe_evaluation_policy": spec.callframe_evaluation_policy if spec else None,
            "evaluation_policy_decision": cls._evaluation_policy_decision(spec.expression or "", spec.callframe_evaluation_policy) if spec and method == "Debugger.evaluateOnCallFrame" else {},
            "live_action_executed": status == "executed",
            "browser_resumed": status == "executed" and method == "Debugger.resume",
            "debugger_stepped": status == "executed" and method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"},
            "callframe_evaluated": status == "executed" and method == "Debugger.evaluateOnCallFrame",
            "cross_process_action_executed": status == "executed",
            "debugger_domain_enabled": False,
            "runtime_mutated": False,
            "cdp_methods": cdp_methods or [],
            "cdp_params_summary": cls._params_summary(cdp_params or {}),
            "action_result_summary": cls._result_summary(action_result),
            "evaluation": evaluation,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(bool(cdp_methods), action=action or "", evaluation_sent=method == "Debugger.evaluateOnCallFrame" and bool(cdp_methods)),
            "error": error,
        }

    @classmethod
    def _params_for_action(cls, spec: PausedSessionCrossProcessOneActionSpec, *, method: str) -> dict[str, Any]:
        params: dict[str, Any] = {"sessionId": spec.attached_session_id}
        if method == "Debugger.evaluateOnCallFrame":
            decision = cls._evaluation_policy_decision(spec.expression or "", spec.callframe_evaluation_policy)
            params.update(
                {
                    "callFrameId": spec.live_callframe_id,
                    "expression": spec.expression,
                    "returnByValue": True,
                    "silent": True,
                    "throwOnSideEffect": decision["throw_on_side_effect"],
                }
            )
        return params

    @classmethod
    def _method_for_action(cls, action: str) -> str:
        normalized = str(action or "").strip().replace("-", "_").lower()
        if normalized in {"evaluate", "evaluate_on_callframe", "eval"}:
            return "Debugger.evaluateOnCallFrame"
        return cls.ACTION_METHODS.get(normalized, "")

    @staticmethod
    def _evaluation_policy_decision(expression: str, policy: str) -> dict[str, Any]:
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
        return BreakpointManager._evaluation_policy_decision(expression, policy)

    @staticmethod
    def _side_effect_policy(cdp_sent: bool, *, action: str = "", evaluation_sent: bool = False) -> dict[str, Any]:
        method = PausedSessionCrossProcessOneActionManager._method_for_action(action)
        return {
            "read_only": not cdp_sent,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": cdp_sent,
            "cdp_target_attached": False,
            "cdp_target_detached": False,
            "debugger_domain_enabled": False,
            "browser_resumed": cdp_sent and method == "Debugger.resume",
            "debugger_stepped": cdp_sent and method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"},
            "callframe_evaluated": bool(evaluation_sent),
            "runtime_mutated": False,
            "live_action_executed": cdp_sent,
            "cross_process_action_executed": cdp_sent,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _params_summary(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "session_id_present": bool(params.get("sessionId")),
            "callframe_id_present": bool(params.get("callFrameId")),
            "expression_present": bool(params.get("expression")),
            "throw_on_side_effect": params.get("throwOnSideEffect"),
            "keys": sorted(str(key) for key in params.keys()),
        }

    @staticmethod
    def _result_summary(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {"type": type(result).__name__, "keys": []}
        payload = result.get("result") if isinstance(result.get("result"), dict) else result
        if not isinstance(payload, dict):
            return {"type": type(payload).__name__, "keys": sorted(str(key) for key in result.keys())}
        return {
            "type": str(payload.get("type") or type(payload).__name__),
            "subtype": payload.get("subtype"),
            "description": payload.get("description"),
            "has_value": "value" in payload,
            "keys": sorted(str(key) for key in payload.keys()),
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "cross_process_one_action_request_missing": ("request", "No cross-process one-action execution request was provided.", "request_cross_process_one_action_execution"),
            "live_callframe_recovery_required": ("live_callframe", "A read-only live callFrame recovery artifact is required before action execution.", "recover_live_callframe_after_attach"),
            "live_callframe_recovery_blocked": ("live_callframe", "The supplied live callFrame recovery artifact is blocked or did not recover a live callFrame.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_retained_required": ("cdp_session", "The attach probe has already detached the target session; rerun the reviewed attach probe with a retained session before execution.", "rerun_attach_probe_without_detach_for_one_action"),
            "attached_session_id_required": ("cdp_session", "An attached CDP session id is required for the flattened one-action command.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "A fresh live callFrameId is required for cross-process action execution.", "recover_live_callframe_after_attach"),
            "unsupported_cross_process_action": ("action", "Only resume, step_over, step_into, step_out, and evaluate are supported by the one-action executor baseline.", "select_supported_cross_process_action"),
            "callframe_expression_required": ("action", "A callframe expression is required for evaluate actions.", "provide_callframe_expression"),
            "blocked_by_callframe_evaluation_policy": ("review", "The requested expression is blocked by the callframe evaluation policy.", "review_or_lower_expression_risk"),
            "review_approval_required": ("review", "Executing a cross-process live debugger action requires explicit review approval.", "approve_cross_process_one_action_execution"),
            "browser_page_required": ("runtime", "A BrowserPage with CDP access is required for one-action execution.", "provide_browser_page_for_one_action_execution"),
            "cdp_session_required": ("runtime", "The active page does not expose a CDP session.", "use_cdp_capable_browser_provider"),
            "cross_process_one_action_failed": ("cdp", "The reviewed one-action CDP command failed.", "inspect_cross_process_one_action_error"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_one_action"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_one_action"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_cross_process_one_action"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if "review_approval_required" in blockers:
            return "approve_cross_process_one_action_execution"
        if "attached_session_retained_required" in blockers:
            return "rerun_attach_probe_without_detach_for_one_action"
        if any(item in blockers for item in ("live_callframe_recovery_required", "live_callframe_recovery_blocked", "live_callframe_id_required")):
            return "recover_live_callframe_after_attach"
        if "blocked_by_callframe_evaluation_policy" in blockers:
            return "review_or_lower_expression_risk"
        if status == "ready_for_review":
            return "approve_cross_process_one_action_execution"
        if status == "executed":
            return "review_cross_process_one_action_result"
        return "inspect_cross_process_one_action_blockers"


@dataclass(slots=True)
class PausedSessionNextPausedEventCapturePlanSpec:
    """Plan how to capture the next Debugger.paused event after a reviewed one-action execution."""

    cross_process_one_action_execution: dict[str, Any] = field(default_factory=dict)
    requested_action: str | None = None
    method: str | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    reviewer: str | None = None
    timeout_ms: int = 5000

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionNextPausedEventCapturePlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_next_paused_event_capture_plan")
            or context.get("pausedSessionNextPausedEventCapturePlan")
            or context.get("paused-session-next-paused-event-capture-plan")
            or context.get("next_paused_event_capture_plan")
            or context.get("nextPausedEventCapturePlan")
            or context.get("plan_next_paused_event_capture")
            or context.get("planNextPausedEventCapture")
        )
        one_action_container = _first_dict(
            context,
            "paused_session_cross_process_one_action_execution",
            "paused-session-cross-process-one-action-execution",
            "pausedSessionCrossProcessOneActionExecution",
            "cross_process_one_action_execution",
            "crossProcessOneActionExecution",
            "cross_process_one_action",
            "crossProcessOneAction",
        )
        execution = dict(one_action_container.get("execution")) if isinstance(one_action_container.get("execution"), dict) else one_action_container
        if not requested and not execution:
            return None
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", execution.get("timeout_ms", 5000)))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        return cls(
            cross_process_one_action_execution=execution,
            requested_action=str(context.get("requested_action") or context.get("requestedAction") or execution.get("requested_action") or "").strip().replace("-", "_").lower() or None,
            method=str(context.get("method") or execution.get("method") or "").strip() or None,
            pause_session_id=str(context.get("pause_session_id") or context.get("pauseSessionId") or execution.get("pause_session_id") or "").strip() or None,
            target_id=str(context.get("target_id") or context.get("targetId") or execution.get("target_id") or "").strip() or None,
            attached_session_id=str(context.get("attached_session_id") or context.get("attachedSessionId") or execution.get("attached_session_id") or "").strip() or None,
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
            timeout_ms=max(100, timeout_ms),
        )


@dataclass(slots=True)
class PausedSessionNextPausedEventCapturePlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionNextPausedEventCapturePlanManager:
    """Review-only plan for the next paused-event capture step after one live action."""

    STEP_METHODS = {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"}

    def plan(self, spec: PausedSessionNextPausedEventCapturePlanSpec | None) -> PausedSessionNextPausedEventCapturePlanResult:
        blockers = self._blockers(spec)
        plan = self._payload(spec, blockers=blockers)
        status = plan["status"]
        return PausedSessionNextPausedEventCapturePlanResult(status=status, plan=plan, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionNextPausedEventCapturePlanSpec | None) -> list[str]:
        if spec is None:
            return ["next_paused_event_capture_plan_request_missing"]
        blockers: list[str] = []
        execution = spec.cross_process_one_action_execution
        if not execution:
            blockers.append("cross_process_one_action_execution_required")
        elif execution.get("status") != "executed" or not execution.get("live_action_executed"):
            blockers.append("cross_process_one_action_not_executed")
        method = spec.method or str(execution.get("method") or "")
        if not method:
            blockers.append("debugger_action_method_required")
        if method == "Debugger.evaluateOnCallFrame":
            blockers.append("next_paused_event_not_required_for_evaluate")
        if method == "Debugger.resume" and not spec.attached_session_id:
            blockers.append("attached_session_id_required_for_resume_capture")
        if method in cls.STEP_METHODS and not spec.attached_session_id:
            blockers.append("attached_session_id_required_for_step_capture")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionNextPausedEventCapturePlanSpec | None, *, blockers: list[str]) -> dict[str, Any]:
        execution = spec.cross_process_one_action_execution if spec else {}
        method = spec.method or str(execution.get("method") or "") if spec else ""
        requested_action = spec.requested_action or str(execution.get("requested_action") or "") if spec else None
        requires_capture = method in cls.STEP_METHODS or method == "Debugger.resume"
        not_required = "next_paused_event_not_required_for_evaluate" in blockers
        effective_blockers = [item for item in blockers if item != "next_paused_event_not_required_for_evaluate"]
        status = "not_required" if not_required and not effective_blockers else "ready_for_review" if requires_capture and not blockers else "blocked" if blockers else "ready_for_review"
        capture_window = "after_step_until_next_debugger_paused" if method in cls.STEP_METHODS else "after_resume_until_next_debugger_paused_or_timeout" if method == "Debugger.resume" else "not_required_for_evaluate"
        return {
            "schema_version": "reverse-deepagent.paused-session-next-paused-event-capture-plan.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else execution.get("pause_session_id"),
            "requested_action": requested_action,
            "method": method or None,
            "reviewer": spec.reviewer if spec else None,
            "target_id": spec.target_id if spec else execution.get("target_id"),
            "attached_session_id_present": bool(spec and spec.attached_session_id),
            "timeout_ms": spec.timeout_ms if spec else 5000,
            "requires_next_paused_event_capture": requires_capture,
            "capture_window": capture_window,
            "automatic_capture_supported": False,
            "plan_ready_for_review": status == "ready_for_review",
            "one_action_execution_status": execution.get("status"),
            "one_action_live_action_executed": bool(execution.get("live_action_executed")),
            "planned_steps": cls._planned_steps(method=method, timeout_ms=spec.timeout_ms if spec else 5000, requires_capture=requires_capture),
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _planned_steps(*, method: str, timeout_ms: int, requires_capture: bool) -> list[dict[str, Any]]:
        if not requires_capture:
            return [
                {
                    "step": "review_one_action_result",
                    "status": "not_required_for_evaluate" if method == "Debugger.evaluateOnCallFrame" else "review_only",
                    "side_effects": False,
                    "description": "No automatic next Debugger.paused capture is required for this one-action method.",
                }
            ]
        return [
            {
                "step": "pre_subscribe_debugger_paused",
                "status": "future_review_gate_required",
                "side_effects": False,
                "description": "Future executor must register Debugger.paused handling before issuing the next reviewed live action.",
            },
            {
                "step": "capture_next_debugger_paused",
                "status": "future_review_gate_required",
                "side_effects": False,
                "timeout_ms": timeout_ms,
                "description": "Future executor may wait for one next Debugger.paused event and then stop without looping.",
            },
            {
                "step": "recover_live_callframe_from_next_pause",
                "status": "future_review_gate_required",
                "side_effects": False,
                "description": "Future recovery should feed the observed callFrames into the existing live callFrame recovery proof.",
            },
        ]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "next_paused_event_capture_plan_request_missing": ("request", "No next paused-event capture plan request was provided.", "request_next_paused_event_capture_plan"),
            "cross_process_one_action_execution_required": ("one_action", "A cross-process one-action execution artifact is required before planning the next paused-event capture.", "execute_or_provide_cross_process_one_action_result"),
            "cross_process_one_action_not_executed": ("one_action", "The supplied one-action artifact has not executed a live action.", "review_or_execute_cross_process_one_action"),
            "debugger_action_method_required": ("action", "The one-action method is missing.", "provide_one_action_method"),
            "next_paused_event_not_required_for_evaluate": ("action", "Evaluate-on-callframe does not itself require capturing a next paused event.", "review_evaluation_result"),
            "attached_session_id_required_for_resume_capture": ("cdp_session", "A retained attached session id is required before planning resume-event capture.", "retain_attached_session_before_resume_capture"),
            "attached_session_id_required_for_step_capture": ("cdp_session", "A retained attached session id is required before planning step-event capture.", "retain_attached_session_before_step_capture"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if status == "ready_for_review":
            return "review_next_paused_event_capture_plan"
        if status == "not_required":
            return "review_one_action_result"
        if "cross_process_one_action_execution_required" in blockers or "cross_process_one_action_not_executed" in blockers:
            return "execute_or_review_cross_process_one_action_first"
        if any(item.startswith("attached_session_id_required") for item in blockers):
            return "rerun_attach_probe_with_retained_session_before_capture_plan"
        return "inspect_next_paused_event_capture_plan_blockers"


@dataclass(slots=True)
class PausedSessionNextPausedEventCaptureExecutionSpec:
    """Capture at most one next Debugger.paused event after a reviewed one-action execution."""

    next_paused_event_capture_plan: dict[str, Any] = field(default_factory=dict)
    execute_capture: bool = False
    review_approved: bool = False
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    method: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionNextPausedEventCaptureExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_next_paused_event_capture_execution")
            or context.get("pausedSessionNextPausedEventCaptureExecution")
            or context.get("paused-session-next-paused-event-capture-execution")
            or context.get("next_paused_event_capture_execution")
            or context.get("nextPausedEventCaptureExecution")
            or context.get("execute_next_paused_event_capture")
            or context.get("executeNextPausedEventCapture")
        )
        plan_container = _first_dict(
            context,
            "paused_session_next_paused_event_capture_plan",
            "pausedSessionNextPausedEventCapturePlan",
            "paused-session-next-paused-event-capture-plan",
            "next_paused_event_capture_plan",
            "nextPausedEventCapturePlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        if not requested and not plan:
            return None
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", plan.get("timeout_ms", 5000)))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        event = _first_dict(
            context,
            "observed_paused_event",
            "observedPausedEvent",
            "debugger_paused_event",
            "debuggerPausedEvent",
            "paused_event",
            "pausedEvent",
        )
        execute_raw = context.get("execute_next_paused_event_capture", context.get("executeNextPausedEventCapture", context.get("execute_capture", context.get("executeCapture", False))))
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            next_paused_event_capture_plan=plan,
            execute_capture=bool(execute_raw),
            review_approved=bool(approved_raw),
            pause_session_id=str(context.get("pause_session_id") or context.get("pauseSessionId") or plan.get("pause_session_id") or "").strip() or None,
            target_id=str(context.get("target_id") or context.get("targetId") or plan.get("target_id") or "").strip() or None,
            attached_session_id=str(context.get("attached_session_id") or context.get("attachedSessionId") or plan.get("attached_session_id") or "").strip() or None,
            method=str(context.get("method") or plan.get("method") or "").strip() or None,
            timeout_ms=max(10, timeout_ms),
            observed_paused_event=event,
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
            require_matching_session_id=bool(match_raw),
        )


@dataclass(slots=True)
class PausedSessionNextPausedEventCaptureExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionNextPausedEventCaptureExecutionManager:
    """Review-gated single-event capture after a next paused-event capture plan."""

    CAPTURE_METHODS = {"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"}

    def capture(self, page: BrowserPage | None, spec: PausedSessionNextPausedEventCaptureExecutionSpec | None) -> PausedSessionNextPausedEventCaptureExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionNextPausedEventCaptureExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason=blockers[0])
        if spec and not spec.execute_capture:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionNextPausedEventCaptureExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy(False, False))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionNextPausedEventCaptureExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason="review_approval_required")
        if page is None:
            payload = self._payload(spec, status="blocked", blockers=["browser_page_required"])
            return PausedSessionNextPausedEventCaptureExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason="browser_page_required")
        session = page.cdp_session()
        if session is None:
            payload = self._payload(spec, status="blocked", blockers=["cdp_session_required"])
            return PausedSessionNextPausedEventCaptureExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason="cdp_session_required")
        on = getattr(session, "on", None)
        if not callable(on):
            payload = self._payload(spec, status="blocked", blockers=["cdp_event_subscription_unavailable"])
            return PausedSessionNextPausedEventCaptureExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason="cdp_event_subscription_unavailable")

        assert spec is not None
        captured_events: list[dict[str, Any]] = []
        ignored_events: list[dict[str, Any]] = []
        subscription_error: str | None = None

        def handle_paused(params: Any) -> None:
            normalized, event_session_id = self._normalize_debugger_paused_event(params)
            if spec.require_matching_session_id and event_session_id and spec.attached_session_id and event_session_id != spec.attached_session_id:
                ignored_events.append({"session_id": event_session_id, "reason": "session_id_mismatch"})
                return
            normalized["event_session_id"] = event_session_id
            captured_events.append(normalized)

        try:
            on("Debugger.paused", handle_paused)
        except Exception as exc:
            subscription_error = str(exc)
        if subscription_error:
            payload = self._payload(spec, status="failed", blockers=["debugger_paused_subscription_failed"], error=subscription_error)
            return PausedSessionNextPausedEventCaptureExecutionResult(status="failed", execution=payload, side_effect_policy=self._side_effect_policy(False, False), reason="debugger_paused_subscription_failed", error=subscription_error)

        if spec.observed_paused_event:
            handle_paused(spec.observed_paused_event)
        self._wait_for_capture(page, captured_events, timeout_ms=spec.timeout_ms)
        status = "captured" if captured_events else "timed_out"
        blockers_after = [] if captured_events else ["next_paused_event_capture_timed_out"]
        payload = self._payload(
            spec,
            status=status,
            blockers=blockers_after,
            captured_events=captured_events,
            ignored_events=ignored_events,
        )
        policy = self._side_effect_policy(True, bool(captured_events))
        return PausedSessionNextPausedEventCaptureExecutionResult(status=status, execution=payload, side_effect_policy=policy, reason=blockers_after[0] if blockers_after else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionNextPausedEventCaptureExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["next_paused_event_capture_execution_request_missing"]
        blockers: list[str] = []
        plan = spec.next_paused_event_capture_plan
        if not plan:
            blockers.append("next_paused_event_capture_plan_required")
        elif plan.get("status") != "ready_for_review" or not plan.get("plan_ready_for_review"):
            blockers.append("next_paused_event_capture_plan_not_ready")
        if plan and not plan.get("requires_next_paused_event_capture"):
            blockers.append("next_paused_event_capture_not_required")
        method = spec.method or str(plan.get("method") or "")
        if method not in cls.CAPTURE_METHODS:
            blockers.append("unsupported_next_paused_event_capture_method")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required_for_event_capture")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionNextPausedEventCaptureExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        captured_events: list[dict[str, Any]] | None = None,
        ignored_events: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        plan = spec.next_paused_event_capture_plan if spec else {}
        events = captured_events or []
        ignored = ignored_events or []
        first_event = events[0] if events else {}
        callframes = first_event.get("callFrames") if isinstance(first_event.get("callFrames"), list) else []
        selected_callframe = callframes[0] if callframes and isinstance(callframes[0], dict) else {}
        return {
            "schema_version": "reverse-deepagent.paused-session-next-paused-event-capture-execution.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else plan.get("pause_session_id"),
            "reviewer": spec.reviewer if spec else None,
            "target_id": spec.target_id if spec else plan.get("target_id"),
            "attached_session_id_present": bool(spec and spec.attached_session_id),
            "method": spec.method if spec else plan.get("method"),
            "timeout_ms": spec.timeout_ms if spec else plan.get("timeout_ms", 5000),
            "execute_capture_requested": bool(spec and spec.execute_capture),
            "review_approved": bool(spec and spec.review_approved),
            "plan_status": plan.get("status"),
            "plan_ready_for_review": bool(plan.get("plan_ready_for_review")),
            "requires_next_paused_event_capture": bool(plan.get("requires_next_paused_event_capture")),
            "debugger_event_subscribed": status in {"captured", "timed_out"},
            "paused_event_captured": bool(events),
            "captured_event_count": len(events),
            "ignored_event_count": len(ignored),
            "ignored_events": ignored,
            "captured_event": first_event,
            "captured_event_summary": cls._event_summary(first_event),
            "callframes": callframes,
            "callframe_count": len(callframes),
            "selected_callframe": selected_callframe,
            "live_callframe_recovery_ready": bool(selected_callframe.get("callFrameId")),
            "fresh_paused_event_after_capture": bool(events),
            "cdp_command_sent": False,
            "debugger_domain_enabled": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, captured=bool(events)),
            "side_effect_policy": cls._side_effect_policy(status in {"captured", "timed_out"}, bool(events)),
            "error": error,
        }

    @staticmethod
    def _normalize_debugger_paused_event(params: Any) -> tuple[dict[str, Any], str | None]:
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
        event_session_id: str | None = None
        payload = params
        if isinstance(params, dict):
            event_session_id = str(params.get("sessionId") or "").strip() or None
            if isinstance(params.get("params"), dict):
                payload = params["params"]
        normalized = BreakpointManager._normalize_paused(payload)
        return normalized, event_session_id

    @staticmethod
    def _wait_for_capture(page: BrowserPage, captured_events: list[dict[str, Any]], *, timeout_ms: int) -> None:
        if captured_events or timeout_ms <= 0:
            return
        raw_page = getattr(page, "raw_page", None)
        wait_for_timeout = getattr(raw_page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            wait_for_timeout(timeout_ms)
            return
        deadline = time.monotonic() + (timeout_ms / 1000)
        while not captured_events and time.monotonic() < deadline:
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    @staticmethod
    def _event_summary(event: dict[str, Any]) -> dict[str, Any]:
        if not event:
            return {}
        frames = event.get("callFrames") if isinstance(event.get("callFrames"), list) else []
        top = frames[0] if frames and isinstance(frames[0], dict) else {}
        return {
            "reason": event.get("reason"),
            "hitBreakpoints": event.get("hitBreakpoints", []),
            "event_session_id": event.get("event_session_id"),
            "callframe_count": len(frames),
            "top_function": top.get("functionName"),
            "top_url": top.get("url"),
            "top_location": top.get("location"),
            "top_callframe_id_present": bool(top.get("callFrameId")),
        }

    @staticmethod
    def _side_effect_policy(event_subscribed: bool, paused_event_captured: bool) -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": event_subscribed,
            "paused_event_captured": paused_event_captured,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "next_paused_event_capture_execution_request_missing": ("request", "No next paused-event capture execution request was provided.", "request_next_paused_event_capture_execution"),
            "next_paused_event_capture_plan_required": ("plan", "A ready next paused-event capture plan is required before execution.", "plan_next_paused_event_capture"),
            "next_paused_event_capture_plan_not_ready": ("plan", "The supplied next paused-event capture plan is not ready for review-gated execution.", "review_next_paused_event_capture_plan"),
            "next_paused_event_capture_not_required": ("action", "The supplied one-action method does not require a next paused-event capture.", "review_one_action_result"),
            "unsupported_next_paused_event_capture_method": ("action", "Only resume and step one-action methods can capture a next Debugger.paused event.", "select_supported_step_or_resume_action"),
            "attached_session_id_required_for_event_capture": ("cdp_session", "A retained attached session id is required before event capture execution.", "rerun_attach_probe_with_retained_session"),
            "review_approval_required": ("review", "Capturing the next paused event requires explicit review approval.", "approve_next_paused_event_capture_execution"),
            "browser_page_required": ("runtime", "A BrowserPage with CDP event subscription support is required.", "provide_browser_page_for_event_capture"),
            "cdp_session_required": ("runtime", "The active page does not expose a CDP session.", "use_cdp_capable_browser_provider"),
            "cdp_event_subscription_unavailable": ("runtime", "The active CDP session does not expose event subscription.", "use_cdp_event_capable_browser_provider"),
            "debugger_paused_subscription_failed": ("cdp", "Subscribing to Debugger.paused failed.", "inspect_debugger_paused_subscription_error"),
            "next_paused_event_capture_timed_out": ("runtime", "No matching Debugger.paused event was captured within the bounded wait window.", "rerun_capture_with_presubscription_or_reproduce_pause"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_execution"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_execution"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_next_paused_event_capture_execution"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], captured: bool) -> str:
        if "review_approval_required" in blockers:
            return "approve_next_paused_event_capture_execution"
        if captured:
            return "recover_live_callframe_from_captured_pause"
        if status == "ready_for_review":
            return "approve_next_paused_event_capture_execution"
        if status == "timed_out":
            return "rerun_capture_with_presubscription_or_reproduce_pause"
        if any(item in blockers for item in ("next_paused_event_capture_plan_required", "next_paused_event_capture_plan_not_ready")):
            return "plan_or_review_next_paused_event_capture_first"
        return "inspect_next_paused_event_capture_execution_blockers"


@dataclass(slots=True)
class PausedSessionPreActionSubscribeAndActionSpec:
    """Pre-subscribe to Debugger.paused, execute one reviewed action, and capture at most one pause."""

    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_orchestration: bool = False
    review_approved: bool = False
    requested_action: str = "step_over"
    expression: str | None = None
    callframe_evaluation_policy: str = "read_only"
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionPreActionSubscribeAndActionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_pre_action_subscribe_and_action")
            or context.get("pausedSessionPreActionSubscribeAndAction")
            or context.get("paused-session-pre-action-subscribe-and-action")
            or context.get("pre_action_subscribe_and_action")
            or context.get("preActionSubscribeAndAction")
            or context.get("subscribe_and_action_orchestration")
            or context.get("subscribeAndActionOrchestration")
            or context.get("pre_subscribe_cross_process_one_action")
            or context.get("preSubscribeCrossProcessOneAction")
        )
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
            "cross_process_live_callframe_recovery",
            "crossProcessLiveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        if not requested and not recovery:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", context.get("action", recovery.get("requested_action", "step_over"))),
            )
            or "step_over"
        ).strip().replace("-", "_").lower()
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        event = _first_dict(
            context,
            "observed_paused_event",
            "observedPausedEvent",
            "debugger_paused_event",
            "debuggerPausedEvent",
            "paused_event",
            "pausedEvent",
        )
        execute_raw = context.get(
            "execute_pre_action_subscribe_and_action",
            context.get("executePreActionSubscribeAndAction", context.get("execute_orchestration", context.get("executeOrchestration", False))),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        expression = context.get("expression") or context.get("callframe_expression") or context.get("callFrameExpression")
        policy = str(context.get("callframe_evaluation_policy", context.get("callFrameEvaluationPolicy", "read_only")) or "read_only").strip().replace("-", "_").lower()
        attached_session_id = (
            context.get("attached_session_id")
            or context.get("attachedSessionId")
            or recovery.get("attached_session_id")
            or attach_probe.get("attached_session_id")
        )
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or recovery.get("pause_session_id")
            or attach_probe.get("pause_session_id")
        )
        target_id = context.get("target_id") or context.get("targetId") or recovery.get("target_id") or attach_probe.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_orchestration=bool(execute_raw),
            review_approved=bool(approved_raw),
            requested_action=action,
            expression=str(expression) if expression is not None else None,
            callframe_evaluation_policy=policy,
            pause_session_id=str(pause_session_id) if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            attached_session_id=str(attached_session_id).strip() if attached_session_id else None,
            live_callframe_id=str(live_callframe_id).strip() if live_callframe_id else None,
            timeout_ms=max(10, timeout_ms),
            observed_paused_event=event,
            reviewer=str(reviewer) if reviewer else None,
            require_matching_session_id=bool(match_raw),
        )


@dataclass(slots=True)
class PausedSessionPreActionSubscribeAndActionResult:
    status: str
    orchestration: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "orchestration": self.orchestration,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionPreActionSubscribeAndActionManager:
    """Review-gated pre-subscribe + one-action + one paused-event capture orchestration."""

    CAPTURE_METHODS = PausedSessionNextPausedEventCaptureExecutionManager.CAPTURE_METHODS

    def execute(self, page: BrowserPage | None, spec: PausedSessionPreActionSubscribeAndActionSpec | None) -> PausedSessionPreActionSubscribeAndActionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionPreActionSubscribeAndActionResult(status="blocked", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action if spec else ""), reason=blockers[0])
        if spec and not spec.execute_orchestration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionPreActionSubscribeAndActionResult(status="ready_for_review", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionPreActionSubscribeAndActionResult(status="review_required", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action), reason="review_approval_required")
        if page is None:
            payload = self._payload(spec, status="blocked", blockers=["browser_page_required"])
            return PausedSessionPreActionSubscribeAndActionResult(status="blocked", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action if spec else ""), reason="browser_page_required")
        session = page.cdp_session()
        if session is None:
            payload = self._payload(spec, status="blocked", blockers=["cdp_session_required"])
            return PausedSessionPreActionSubscribeAndActionResult(status="blocked", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action if spec else ""), reason="cdp_session_required")
        on = getattr(session, "on", None)
        if not callable(on):
            payload = self._payload(spec, status="blocked", blockers=["cdp_event_subscription_unavailable"])
            return PausedSessionPreActionSubscribeAndActionResult(status="blocked", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action if spec else ""), reason="cdp_event_subscription_unavailable")

        assert spec is not None
        captured_events: list[dict[str, Any]] = []
        ignored_events: list[dict[str, Any]] = []
        subscription_error: str | None = None

        def handle_paused(params: Any) -> None:
            normalized, event_session_id = PausedSessionNextPausedEventCaptureExecutionManager._normalize_debugger_paused_event(params)
            if spec.require_matching_session_id and event_session_id and spec.attached_session_id and event_session_id != spec.attached_session_id:
                ignored_events.append({"session_id": event_session_id, "reason": "session_id_mismatch"})
                return
            normalized["event_session_id"] = event_session_id
            captured_events.append(normalized)

        try:
            on("Debugger.paused", handle_paused)
        except Exception as exc:
            subscription_error = str(exc)
        if subscription_error:
            payload = self._payload(spec, status="failed", blockers=["debugger_paused_subscription_failed"], error=subscription_error)
            return PausedSessionPreActionSubscribeAndActionResult(status="failed", orchestration=payload, side_effect_policy=self._side_effect_policy(False, False, False, action=spec.requested_action), reason="debugger_paused_subscription_failed", error=subscription_error)

        method = PausedSessionCrossProcessOneActionManager._method_for_action(spec.requested_action)
        params = PausedSessionCrossProcessOneActionManager._params_for_action(
            PausedSessionCrossProcessOneActionSpec(
                live_callframe_recovery=spec.live_callframe_recovery,
                cross_process_attach_probe=spec.cross_process_attach_probe,
                execute_action=True,
                review_approved=True,
                requested_action=spec.requested_action,
                expression=spec.expression,
                callframe_evaluation_policy=spec.callframe_evaluation_policy,
                pause_session_id=spec.pause_session_id,
                target_id=spec.target_id,
                attached_session_id=spec.attached_session_id,
                live_callframe_id=spec.live_callframe_id,
                reviewer=spec.reviewer,
            ),
            method=method,
        )
        error: str | None = None
        action_result: Any = {}
        try:
            action_result = session.send(method, params)
        except Exception as exc:
            error = str(exc)

        if spec.observed_paused_event:
            handle_paused(spec.observed_paused_event)
        if error is None:
            PausedSessionNextPausedEventCaptureExecutionManager._wait_for_capture(page, captured_events, timeout_ms=spec.timeout_ms)
        if error is not None:
            status = "failed"
            blockers_after = ["cross_process_action_failed"]
        elif captured_events:
            status = "captured"
            blockers_after = []
        else:
            status = "timed_out"
            blockers_after = ["next_paused_event_capture_timed_out"]
        payload = self._payload(
            spec,
            status=status,
            blockers=blockers_after,
            cdp_methods=[method],
            cdp_params=params,
            action_result=action_result,
            captured_events=captured_events,
            ignored_events=ignored_events,
            error=error,
        )
        policy = self._side_effect_policy(True, True, bool(captured_events), action=spec.requested_action, evaluation_sent=method == "Debugger.evaluateOnCallFrame")
        return PausedSessionPreActionSubscribeAndActionResult(status=status, orchestration=payload, side_effect_policy=policy, reason=blockers_after[0] if blockers_after else None, error=error)

    @classmethod
    def _blockers(cls, spec: PausedSessionPreActionSubscribeAndActionSpec | None) -> list[str]:
        if spec is None:
            return ["pre_action_subscribe_and_action_request_missing"]
        blockers: list[str] = []
        recovery = spec.live_callframe_recovery
        if not recovery:
            blockers.append("live_callframe_recovery_required")
        elif recovery.get("status") == "blocked" or not recovery.get("live_callframe_recovered"):
            blockers.append("live_callframe_recovery_blocked")
        if recovery.get("target_detached"):
            blockers.append("attached_session_retained_required")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required")
        if not spec.live_callframe_id:
            blockers.append("live_callframe_id_required")
        method = PausedSessionCrossProcessOneActionManager._method_for_action(spec.requested_action)
        if not method:
            blockers.append("unsupported_cross_process_action")
        if method not in cls.CAPTURE_METHODS:
            blockers.append("unsupported_pre_action_capture_method")
        if method == "Debugger.evaluateOnCallFrame":
            blockers.append("evaluate_action_does_not_require_pre_action_capture")
        if spec.requested_action in {"evaluate", "evaluate_on_callframe"}:
            if not spec.expression:
                blockers.append("callframe_expression_required")
            decision = PausedSessionCrossProcessOneActionManager._evaluation_policy_decision(spec.expression or "", spec.callframe_evaluation_policy)
            if decision["blocked"]:
                blockers.append("blocked_by_callframe_evaluation_policy")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionPreActionSubscribeAndActionSpec | None,
        *,
        status: str,
        blockers: list[str],
        cdp_methods: list[str] | None = None,
        cdp_params: dict[str, Any] | None = None,
        action_result: Any = None,
        captured_events: list[dict[str, Any]] | None = None,
        ignored_events: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        recovery = spec.live_callframe_recovery if spec else {}
        method = PausedSessionCrossProcessOneActionManager._method_for_action(spec.requested_action if spec else "")
        events = captured_events or []
        ignored = ignored_events or []
        first_event = events[0] if events else {}
        callframes = first_event.get("callFrames") if isinstance(first_event.get("callFrames"), list) else []
        selected_callframe = callframes[0] if callframes and isinstance(callframes[0], dict) else {}
        cdp_sent = bool(cdp_methods)
        event_subscribed = bool(cdp_methods) and status in {"captured", "timed_out", "failed"}
        return {
            "schema_version": "reverse-deepagent.paused-session-pre-action-subscribe-and-action.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else None,
            "reviewer": spec.reviewer if spec else None,
            "target_id": spec.target_id if spec else None,
            "attached_session_id_present": bool(spec and spec.attached_session_id),
            "live_callframe_id_present": bool(spec and spec.live_callframe_id),
            "live_callframe_recovery_status": recovery.get("status"),
            "live_callframe_recovered": bool(recovery.get("live_callframe_recovered")),
            "requested_action": spec.requested_action if spec else None,
            "method": method or None,
            "timeout_ms": spec.timeout_ms if spec else 5000,
            "execute_orchestration_requested": bool(spec and spec.execute_orchestration),
            "review_approved": bool(spec and spec.review_approved),
            "pre_action_event_subscribed": event_subscribed,
            "action_sent_after_subscription": cdp_sent and event_subscribed,
            "live_action_executed": cdp_sent and error is None,
            "cross_process_action_executed": cdp_sent and error is None,
            "debugger_event_subscribed": event_subscribed,
            "paused_event_captured": bool(events),
            "captured_event_count": len(events),
            "ignored_event_count": len(ignored),
            "ignored_events": ignored,
            "captured_event": first_event,
            "captured_event_summary": PausedSessionNextPausedEventCaptureExecutionManager._event_summary(first_event),
            "callframes": callframes,
            "callframe_count": len(callframes),
            "selected_callframe": selected_callframe,
            "live_callframe_recovery_ready": bool(selected_callframe.get("callFrameId")),
            "fresh_paused_event_after_action": bool(events),
            "cdp_methods": cdp_methods or [],
            "cdp_params_summary": PausedSessionCrossProcessOneActionManager._params_summary(cdp_params or {}),
            "action_result_summary": PausedSessionCrossProcessOneActionManager._result_summary(action_result),
            "browser_resumed": cdp_sent and method == "Debugger.resume" and error is None,
            "debugger_stepped": cdp_sent and method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"} and error is None,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, captured=bool(events)),
            "side_effect_policy": cls._side_effect_policy(cdp_sent, event_subscribed, bool(events), action=spec.requested_action if spec else ""),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(cdp_sent: bool, event_subscribed: bool, paused_event_captured: bool, *, action: str = "", evaluation_sent: bool = False) -> dict[str, Any]:
        method = PausedSessionCrossProcessOneActionManager._method_for_action(action)
        return {
            "read_only": not cdp_sent and not event_subscribed,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": cdp_sent,
            "debugger_event_subscribed": event_subscribed,
            "paused_event_captured": paused_event_captured,
            "browser_resumed": cdp_sent and method == "Debugger.resume",
            "debugger_stepped": cdp_sent and method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"},
            "callframe_evaluated": bool(evaluation_sent),
            "runtime_mutated": False,
            "live_action_executed": cdp_sent,
            "cross_process_action_executed": cdp_sent,
            "orchestrated_pre_action_subscription": event_subscribed and cdp_sent,
            "bounded_one_action_only": True,
            "multi_step_continuation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "pre_action_subscribe_and_action_request_missing": ("request", "No pre-action subscribe-and-action request was provided.", "request_pre_action_subscribe_and_action"),
            "live_callframe_recovery_required": ("live_callframe", "A read-only live callFrame recovery artifact is required before orchestration.", "recover_live_callframe_after_attach"),
            "live_callframe_recovery_blocked": ("live_callframe", "The supplied live callFrame recovery artifact is blocked or did not recover a live callFrame.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_retained_required": ("cdp_session", "A retained attached session is required so the subscription can observe the next pause.", "rerun_attach_probe_without_detach"),
            "attached_session_id_required": ("cdp_session", "An attached CDP session id is required for flattened action orchestration.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "A fresh live callFrameId is required before sending the reviewed action.", "recover_live_callframe_after_attach"),
            "unsupported_cross_process_action": ("action", "Only resume, step_over, step_into, and step_out are supported by this orchestration baseline.", "select_supported_cross_process_action"),
            "unsupported_pre_action_capture_method": ("action", "Only resume and step methods can be orchestrated with next paused-event capture.", "select_step_or_resume_action"),
            "evaluate_action_does_not_require_pre_action_capture": ("action", "Evaluate-on-callframe does not require a pre-action paused-event capture orchestration.", "review_evaluation_result"),
            "callframe_expression_required": ("action", "A callframe expression is required for evaluate actions.", "provide_callframe_expression"),
            "blocked_by_callframe_evaluation_policy": ("review", "The requested expression is blocked by the callframe evaluation policy.", "review_or_lower_expression_risk"),
            "review_approval_required": ("review", "Pre-action subscribe-and-action orchestration requires explicit review approval.", "approve_pre_action_subscribe_and_action"),
            "browser_page_required": ("runtime", "A BrowserPage with CDP access is required for orchestration.", "provide_browser_page_for_orchestration"),
            "cdp_session_required": ("runtime", "The active page does not expose a CDP session.", "use_cdp_capable_browser_provider"),
            "cdp_event_subscription_unavailable": ("runtime", "The active CDP session does not expose event subscription.", "use_cdp_event_capable_browser_provider"),
            "debugger_paused_subscription_failed": ("cdp", "Subscribing to Debugger.paused failed before action execution.", "inspect_debugger_paused_subscription_error"),
            "cross_process_action_failed": ("cdp", "The reviewed action failed after pre-subscription.", "inspect_pre_action_orchestration_action_error"),
            "next_paused_event_capture_timed_out": ("runtime", "The reviewed action ran after pre-subscription but no matching Debugger.paused event was captured.", "review_or_rerun_pre_action_orchestration"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_pre_action_subscribe_and_action"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_pre_action_subscribe_and_action"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_pre_action_subscribe_and_action"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], captured: bool) -> str:
        if "review_approval_required" in blockers:
            return "approve_pre_action_subscribe_and_action"
        if captured:
            return "checkpoint_cross_process_continuation"
        if status == "ready_for_review":
            return "approve_pre_action_subscribe_and_action"
        if status == "timed_out":
            return "review_or_rerun_pre_action_orchestration"
        if any(item in blockers for item in ("live_callframe_recovery_required", "live_callframe_recovery_blocked", "live_callframe_id_required")):
            return "recover_live_callframe_after_attach"
        return "inspect_pre_action_subscribe_and_action_blockers"


@dataclass(slots=True)
class PausedSessionCrossProcessContinuationCheckpointSpec:
    """Review-only checkpoint after next paused-event capture execution."""

    next_paused_event_capture_execution: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_one_action_execution: dict[str, Any] = field(default_factory=dict)
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    checkpoint_index: int = 0
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionCrossProcessContinuationCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_cross_process_continuation_checkpoint")
            or context.get("pausedSessionCrossProcessContinuationCheckpoint")
            or context.get("paused-session-cross-process-continuation-checkpoint")
            or context.get("cross_process_continuation_checkpoint")
            or context.get("crossProcessContinuationCheckpoint")
            or context.get("paused_session_continuation_checkpoint")
            or context.get("pausedSessionContinuationCheckpoint")
        )
        capture_container = _first_dict(
            context,
            "paused_session_next_paused_event_capture_execution",
            "pausedSessionNextPausedEventCaptureExecution",
            "paused-session-next-paused-event-capture-execution",
            "next_paused_event_capture_execution",
            "nextPausedEventCaptureExecution",
        )
        capture = dict(capture_container.get("execution")) if isinstance(capture_container.get("execution"), dict) else capture_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        action_container = _first_dict(
            context,
            "paused_session_cross_process_one_action_execution",
            "pausedSessionCrossProcessOneActionExecution",
            "paused-session-cross-process-one-action-execution",
            "cross_process_one_action_execution",
            "crossProcessOneActionExecution",
        )
        action = dict(action_container.get("execution")) if isinstance(action_container.get("execution"), dict) else action_container
        if not requested and not capture:
            return None
        index_raw = context.get("checkpoint_index", context.get("checkpointIndex", capture.get("checkpoint_index", 0)))
        try:
            checkpoint_index = int(index_raw)
        except (TypeError, ValueError):
            checkpoint_index = 0
        return cls(
            next_paused_event_capture_execution=capture,
            live_callframe_recovery=recovery,
            cross_process_one_action_execution=action,
            pause_session_id=str(context.get("pause_session_id") or context.get("pauseSessionId") or capture.get("pause_session_id") or recovery.get("pause_session_id") or "").strip() or None,
            target_id=str(context.get("target_id") or context.get("targetId") or capture.get("target_id") or recovery.get("target_id") or "").strip() or None,
            attached_session_id=str(context.get("attached_session_id") or context.get("attachedSessionId") or capture.get("attached_session_id") or recovery.get("attached_session_id") or "").strip() or None,
            checkpoint_index=max(0, checkpoint_index),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
        )


@dataclass(slots=True)
class PausedSessionCrossProcessContinuationCheckpointResult:
    status: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checkpoint": self.checkpoint,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionCrossProcessContinuationCheckpointManager:
    """Read-only checkpoint that links captured pause evidence to the next reviewed step."""

    def checkpoint(self, spec: PausedSessionCrossProcessContinuationCheckpointSpec | None) -> PausedSessionCrossProcessContinuationCheckpointResult:
        blockers = self._blockers(spec)
        payload = self._payload(spec, blockers=blockers)
        status = payload["status"]
        return PausedSessionCrossProcessContinuationCheckpointResult(status=status, checkpoint=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionCrossProcessContinuationCheckpointSpec | None) -> list[str]:
        if spec is None:
            return ["continuation_checkpoint_request_missing"]
        blockers: list[str] = []
        capture = spec.next_paused_event_capture_execution
        recovery = spec.live_callframe_recovery
        if not capture:
            blockers.append("next_paused_event_capture_execution_required")
        elif capture.get("status") != "captured" or not capture.get("paused_event_captured"):
            blockers.append("next_paused_event_not_captured")
        if capture and not capture.get("live_callframe_recovery_ready"):
            blockers.append("captured_pause_missing_live_callframe")
        if recovery and (recovery.get("status") == "blocked" or recovery.get("live_callframe_recovered") is False):
            blockers.append("live_callframe_recovery_blocked")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionCrossProcessContinuationCheckpointSpec | None, *, blockers: list[str]) -> dict[str, Any]:
        capture = spec.next_paused_event_capture_execution if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        action = spec.cross_process_one_action_execution if spec else {}
        callframes = capture.get("callframes") if isinstance(capture.get("callframes"), list) else []
        selected_callframe = capture.get("selected_callframe") if isinstance(capture.get("selected_callframe"), dict) else (callframes[0] if callframes and isinstance(callframes[0], dict) else {})
        recovered = bool(recovery.get("live_callframe_recovered"))
        action_executed = bool(action.get("live_action_executed"))
        status = "blocked" if blockers else "ready_for_next_action_review" if recovered else "ready_for_live_callframe_recovery"
        return {
            "schema_version": "reverse-deepagent.paused-session-cross-process-continuation-checkpoint.v1",
            "status": status,
            "checkpoint_index": spec.checkpoint_index if spec else 0,
            "pause_session_id": spec.pause_session_id if spec else capture.get("pause_session_id"),
            "reviewer": spec.reviewer if spec else None,
            "target_id": spec.target_id if spec else capture.get("target_id"),
            "attached_session_id_present": bool(spec and spec.attached_session_id),
            "capture_execution_status": capture.get("status"),
            "paused_event_captured": bool(capture.get("paused_event_captured")),
            "captured_event_count": capture.get("captured_event_count", 0),
            "captured_method": capture.get("method"),
            "callframe_count": len(callframes),
            "selected_callframe": selected_callframe,
            "selected_callframe_id": selected_callframe.get("callFrameId"),
            "fresh_paused_event_after_capture": bool(capture.get("fresh_paused_event_after_capture")),
            "live_callframe_recovery_status": recovery.get("status"),
            "live_callframe_recovered": recovered,
            "live_callframe_id": recovery.get("live_callframe_id"),
            "one_action_execution_status": action.get("status"),
            "one_action_live_action_executed": action_executed,
            "continuation_ready_for_next_action": recovered,
            "continuation_ready_for_next_capture_plan": action_executed,
            "manual_checkpoint_required": True,
            "recommended_followups": cls._recommended_followups(status=status, recovered=recovered, action_executed=action_executed),
            "live_callframe_recovery_input": cls._live_callframe_recovery_input(spec, capture, callframes),
            "next_action_review_input": cls._next_action_review_input(spec, recovery),
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, recovered=recovered, action_executed=action_executed),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _live_callframe_recovery_input(spec: PausedSessionCrossProcessContinuationCheckpointSpec | None, capture: dict[str, Any], callframes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "paused_session_live_callframe_recovery": True,
            "pause_session_id": spec.pause_session_id if spec else capture.get("pause_session_id"),
            "target_id": spec.target_id if spec else capture.get("target_id"),
            "attached_session_id": spec.attached_session_id if spec else capture.get("attached_session_id"),
            "fresh_paused_event_after_attach": True,
            "callFrames": callframes,
            "source_artifact": "workspace/paused-session-next-paused-event-capture-execution.json",
        }

    @staticmethod
    def _next_action_review_input(spec: PausedSessionCrossProcessContinuationCheckpointSpec | None, recovery: dict[str, Any]) -> dict[str, Any]:
        return {
            "paused_session_cross_process_one_action": True,
            "pause_session_id": spec.pause_session_id if spec else recovery.get("pause_session_id"),
            "target_id": spec.target_id if spec else recovery.get("target_id"),
            "attached_session_id": spec.attached_session_id if spec else recovery.get("attached_session_id"),
            "live_callframe_id": recovery.get("live_callframe_id"),
            "source_artifact": "workspace/paused-session-live-callframe-recovery.json",
        }

    @staticmethod
    def _recommended_followups(*, status: str, recovered: bool, action_executed: bool) -> list[dict[str, Any]]:
        if status == "blocked":
            return [{"step": "resolve_checkpoint_blockers", "review_required": True, "side_effects": False}]
        if not recovered:
            return [{"step": "recover_live_callframe_from_captured_pause", "review_required": True, "side_effects": False}]
        if not action_executed:
            return [{"step": "plan_next_cross_process_one_action", "review_required": True, "side_effects": False}]
        return [{"step": "plan_next_paused_event_capture", "review_required": True, "side_effects": False}]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "continuation_checkpoint_request_missing": ("request", "No cross-process continuation checkpoint request was provided.", "request_continuation_checkpoint"),
            "next_paused_event_capture_execution_required": ("capture", "A next paused-event capture execution artifact is required.", "execute_next_paused_event_capture"),
            "next_paused_event_not_captured": ("capture", "The supplied next paused-event capture execution did not capture a paused event.", "rerun_capture_with_presubscription_or_reproduce_pause"),
            "captured_pause_missing_live_callframe": ("debugger", "The captured paused event does not contain a live callFrame candidate.", "capture_pause_with_callframes"),
            "live_callframe_recovery_blocked": ("debugger", "The supplied live callFrame recovery evidence is blocked.", "resolve_live_callframe_recovery_blockers"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_continuation_checkpoint"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_continuation_checkpoint"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_continuation_checkpoint"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], recovered: bool, action_executed: bool) -> str:
        if blockers:
            return "inspect_continuation_checkpoint_blockers"
        if not recovered:
            return "recover_live_callframe_from_captured_pause"
        if not action_executed:
            return "plan_next_cross_process_one_action"
        return "plan_next_paused_event_capture"


@dataclass(slots=True)
class PausedSessionMultiStepContinuationWorkflowSpec:
    """Review-only multi-step paused-session continuation workflow / journal plan."""

    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    planned_actions: list[dict[str, Any]] = field(default_factory=list)
    previous_journal: dict[str, Any] = field(default_factory=dict)
    workflow_id: str | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    max_planned_steps: int = 3
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionMultiStepContinuationWorkflowSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_multi_step_continuation_workflow")
            or context.get("pausedSessionMultiStepContinuationWorkflow")
            or context.get("paused-session-multi-step-continuation-workflow")
            or context.get("multi_step_paused_session_continuation")
            or context.get("multiStepPausedSessionContinuation")
            or context.get("paused_session_continuation_workflow")
            or context.get("pausedSessionContinuationWorkflow")
            or context.get("cross_process_multi_step_continuation")
            or context.get("crossProcessMultiStepContinuation")
        )
        checkpoint_container = _first_dict(
            context,
            "paused_session_cross_process_continuation_checkpoint",
            "pausedSessionCrossProcessContinuationCheckpoint",
            "paused-session-cross-process-continuation-checkpoint",
            "cross_process_continuation_checkpoint",
            "crossProcessContinuationCheckpoint",
            "continuation_checkpoint",
            "continuationCheckpoint",
        )
        checkpoint = dict(checkpoint_container.get("checkpoint")) if isinstance(checkpoint_container.get("checkpoint"), dict) else checkpoint_container
        raw_actions = (
            context.get("planned_actions")
            or context.get("plannedActions")
            or context.get("requested_actions")
            or context.get("requestedActions")
            or context.get("action_sequence")
            or context.get("actionSequence")
            or []
        )
        actions: list[dict[str, Any]] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if isinstance(item, dict):
                    actions.append(dict(item))
                elif isinstance(item, str) and item.strip():
                    actions.append({"requested_action": item.strip()})
        elif isinstance(raw_actions, str) and raw_actions.strip():
            actions.append({"requested_action": raw_actions.strip()})
        journal_container = _first_dict(
            context,
            "paused_session_multi_step_continuation_workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "paused-session-multi-step-continuation-workflow",
            "previous_journal",
            "previousJournal",
            "continuation_journal",
            "continuationJournal",
        )
        journal = dict(journal_container.get("workflow")) if isinstance(journal_container.get("workflow"), dict) else journal_container
        if not requested and not checkpoint and not actions:
            return None
        max_raw = context.get("max_planned_steps", context.get("maxPlannedSteps", len(actions) or 3))
        try:
            max_steps = int(max_raw)
        except (TypeError, ValueError):
            max_steps = 3
        return cls(
            continuation_checkpoint=checkpoint,
            planned_actions=actions,
            previous_journal=journal,
            workflow_id=str(context.get("workflow_id") or context.get("workflowId") or journal.get("workflow_id") or "").strip() or None,
            pause_session_id=str(context.get("pause_session_id") or context.get("pauseSessionId") or checkpoint.get("pause_session_id") or "").strip() or None,
            target_id=str(context.get("target_id") or context.get("targetId") or checkpoint.get("target_id") or "").strip() or None,
            attached_session_id=str(context.get("attached_session_id") or context.get("attachedSessionId") or checkpoint.get("attached_session_id") or "").strip() or None,
            max_planned_steps=max(1, min(max_steps, 10)),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
        )


@dataclass(slots=True)
class PausedSessionMultiStepContinuationWorkflowResult:
    status: str
    workflow: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "workflow": self.workflow,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionMultiStepContinuationWorkflowManager:
    """Read-only workflow / journal plan for bounded multi-step continuation."""

    SUPPORTED_ACTIONS = {"resume", "step_over", "step_into", "step_out", "evaluate", "Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut", "Debugger.evaluateOnCallFrame"}

    def plan(self, spec: PausedSessionMultiStepContinuationWorkflowSpec | None) -> PausedSessionMultiStepContinuationWorkflowResult:
        blockers = self._blockers(spec)
        workflow = self._payload(spec, blockers=blockers)
        return PausedSessionMultiStepContinuationWorkflowResult(status=workflow["status"], workflow=workflow, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionMultiStepContinuationWorkflowSpec | None) -> list[str]:
        if spec is None:
            return ["multi_step_workflow_request_missing"]
        blockers: list[str] = []
        checkpoint = spec.continuation_checkpoint
        if not checkpoint:
            blockers.append("continuation_checkpoint_required")
        elif checkpoint.get("status") == "blocked":
            blockers.append("continuation_checkpoint_blocked")
        elif not (checkpoint.get("continuation_ready_for_next_action") or checkpoint.get("live_callframe_recovered")):
            blockers.append("next_action_checkpoint_not_ready")
        if not spec.planned_actions:
            blockers.append("planned_actions_required")
        if len(spec.planned_actions) > spec.max_planned_steps:
            blockers.append("planned_actions_exceed_review_budget")
        for action in spec.planned_actions[: spec.max_planned_steps]:
            normalized = cls._normalize_action(action)
            if normalized["method"] not in {"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut", "Debugger.evaluateOnCallFrame"}:
                blockers.append("unsupported_planned_action")
            if normalized["method"] == "Debugger.evaluateOnCallFrame" and not normalized.get("expression"):
                blockers.append("evaluate_expression_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionMultiStepContinuationWorkflowSpec | None, *, blockers: list[str]) -> dict[str, Any]:
        checkpoint = spec.continuation_checkpoint if spec else {}
        planned_steps = cls._planned_steps(spec) if spec else []
        duplicate_fingerprints = cls._duplicate_fingerprints(planned_steps, spec.previous_journal if spec else {})
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-multi-step-continuation-workflow.v1",
            "status": status,
            "workflow_id": spec.workflow_id if spec and spec.workflow_id else "paused-session-continuation-workflow",
            "pause_session_id": spec.pause_session_id if spec else checkpoint.get("pause_session_id"),
            "target_id": spec.target_id if spec else checkpoint.get("target_id"),
            "attached_session_id_present": bool(spec and spec.attached_session_id),
            "reviewer": spec.reviewer if spec else None,
            "source_checkpoint_status": checkpoint.get("status"),
            "source_checkpoint_ready_for_next_action": bool(checkpoint.get("continuation_ready_for_next_action") or checkpoint.get("live_callframe_recovered")),
            "max_planned_steps": spec.max_planned_steps if spec else 0,
            "planned_step_count": len(planned_steps),
            "planned_steps": planned_steps,
            "journal_append_plan": cls._journal_append_plan(planned_steps, duplicate_fingerprints),
            "duplicate_fingerprints": duplicate_fingerprints,
            "manual_checkpoint_required_after_each_step": True,
            "execute_at_most_one_action_per_review": True,
            "bounded_workflow_only": True,
            "automatic_loop": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": "approve_multi_step_continuation_workflow" if not blockers else "inspect_multi_step_continuation_workflow_blockers",
            "side_effect_policy": cls._side_effect_policy(),
        }

    @classmethod
    def _planned_steps(cls, spec: PausedSessionMultiStepContinuationWorkflowSpec) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for index, action in enumerate(spec.planned_actions[: spec.max_planned_steps], start=1):
            normalized = cls._normalize_action(action)
            fingerprint = f"{index}:{normalized['method']}:{normalized.get('expression_digest') or ''}"
            steps.append({
                "step_index": index,
                "kind": "reviewed_debugger_action",
                "requested_action": normalized["requested_action"],
                "method": normalized["method"],
                "expression_present": bool(normalized.get("expression")),
                "expression_digest": normalized.get("expression_digest"),
                "requires_review_approval": True,
                "requires_fresh_live_callframe": True,
                "requires_retained_attached_session": True,
                "expected_executor_artifact": "workspace/paused-session-pre-action-subscribe-and-action.json" if normalized["method"] != "Debugger.evaluateOnCallFrame" else "workspace/paused-session-cross-process-one-action-execution.json",
                "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
                "stops_after_step": True,
                "fingerprint": fingerprint,
            })
        return steps

    @staticmethod
    def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
        requested = str(action.get("requested_action") or action.get("action") or action.get("method") or "").strip()
        mapping = {
            "resume": "Debugger.resume",
            "step_over": "Debugger.stepOver",
            "stepOver": "Debugger.stepOver",
            "step_into": "Debugger.stepInto",
            "stepInto": "Debugger.stepInto",
            "step_out": "Debugger.stepOut",
            "stepOut": "Debugger.stepOut",
            "evaluate": "Debugger.evaluateOnCallFrame",
            "evaluate_on_callframe": "Debugger.evaluateOnCallFrame",
            "evaluateOnCallFrame": "Debugger.evaluateOnCallFrame",
        }
        method = mapping.get(requested, requested)
        expression = str(action.get("expression") or action.get("callframe_expression") or action.get("callframeExpression") or "").strip()
        return {
            "requested_action": requested or method,
            "method": method,
            "expression": expression,
            "expression_digest": hashlib.sha256(expression.encode("utf-8")).hexdigest()[:16] if expression else None,
        }

    @staticmethod
    def _duplicate_fingerprints(planned_steps: list[dict[str, Any]], previous_journal: dict[str, Any]) -> list[str]:
        entries = previous_journal.get("journal_entries") if isinstance(previous_journal.get("journal_entries"), list) else previous_journal.get("entries") if isinstance(previous_journal.get("entries"), list) else []
        seen = {str(item.get("fingerprint")) for item in entries if isinstance(item, dict) and item.get("fingerprint")}
        return [step["fingerprint"] for step in planned_steps if step.get("fingerprint") in seen]

    @staticmethod
    def _journal_append_plan(planned_steps: list[dict[str, Any]], duplicate_fingerprints: list[str]) -> dict[str, Any]:
        return {
            "append_only": True,
            "writes_journal": False,
            "journal_artifact": "workspace/paused-session-multi-step-continuation-workflow.json",
            "planned_entry_count": len(planned_steps),
            "duplicate_guard_enabled": True,
            "duplicate_fingerprints": duplicate_fingerprints,
            "manual_append_after_reviewed_step": True,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "workflow_plan_only": True,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "multi_step_workflow_request_missing": ("request", "No multi-step continuation workflow request was provided.", "request_multi_step_continuation_workflow"),
            "continuation_checkpoint_required": ("checkpoint", "A ready continuation checkpoint is required before planning a multi-step workflow.", "create_continuation_checkpoint"),
            "continuation_checkpoint_blocked": ("checkpoint", "The supplied continuation checkpoint is blocked.", "resolve_continuation_checkpoint_blockers"),
            "next_action_checkpoint_not_ready": ("checkpoint", "The checkpoint is not ready for the next reviewed action.", "recover_live_callframe_before_planning_actions"),
            "planned_actions_required": ("workflow", "At least one planned debugger action is required.", "provide_planned_actions"),
            "planned_actions_exceed_review_budget": ("review", "The requested actions exceed the bounded review budget.", "reduce_planned_actions_or_raise_review_budget"),
            "unsupported_planned_action": ("action", "Only resume, step, and evaluate-on-callframe actions can be planned.", "select_supported_debugger_action"),
            "evaluate_expression_required": ("action", "Evaluate-on-callframe planning requires an expression.", "provide_evaluate_expression"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_workflow"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_workflow"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_workflow"))[2]}
            for blocker in blockers
        ]


@dataclass(slots=True)
class PausedSessionMultiStepContinuationExecutionSpec:
    """Review-gated one-iteration executor for a planned paused-session continuation workflow."""

    workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int = 1
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionMultiStepContinuationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_multi_step_continuation_execution")
            or context.get("pausedSessionMultiStepContinuationExecution")
            or context.get("paused-session-multi-step-continuation-execution")
            or context.get("execute_paused_session_continuation_iteration")
            or context.get("executePausedSessionContinuationIteration")
            or context.get("cross_process_multi_step_continuation_execution")
            or context.get("crossProcessMultiStepContinuationExecution")
        )
        workflow_container = _first_dict(
            context,
            "paused_session_multi_step_continuation_workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "paused-session-multi-step-continuation-workflow",
            "multi_step_continuation_workflow",
            "multiStepContinuationWorkflow",
            "continuation_workflow",
            "continuationWorkflow",
        )
        workflow = dict(workflow_container.get("workflow")) if isinstance(workflow_container.get("workflow"), dict) else workflow_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        if not requested and not workflow:
            return None
        index_raw = context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", 1))))
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            selected_step_index = int(index_raw)
        except (TypeError, ValueError):
            selected_step_index = 1
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get("execute_paused_session_continuation_iteration", context.get("executePausedSessionContinuationIteration", context.get("execute_iteration", context.get("executeIteration", False))))
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or workflow.get("pause_session_id") or recovery.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or workflow.get("target_id") or recovery.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index),
            pause_session_id=str(pause_session_id).strip() if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            attached_session_id=str(attached_session_id).strip() if attached_session_id else None,
            live_callframe_id=str(live_callframe_id).strip() if live_callframe_id else None,
            timeout_ms=max(10, timeout_ms),
            observed_paused_event=event,
            reviewer=str(reviewer).strip() if reviewer else None,
            require_matching_session_id=bool(match_raw),
        )


@dataclass(slots=True)
class PausedSessionMultiStepContinuationExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionMultiStepContinuationExecutionManager:
    """Execute at most one reviewed step from a multi-step continuation workflow."""

    def execute(self, page: BrowserPage | None, spec: PausedSessionMultiStepContinuationExecutionSpec | None) -> PausedSessionMultiStepContinuationExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionMultiStepContinuationExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_iteration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionMultiStepContinuationExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionMultiStepContinuationExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        step = self._selected_step(spec)
        method = str(step.get("method") or "")
        inner: dict[str, Any]
        inner_policy: dict[str, Any]
        error: str | None = None
        if method == "Debugger.evaluateOnCallFrame":
            result = PausedSessionCrossProcessOneActionManager().execute(
                page,
                PausedSessionCrossProcessOneActionSpec(
                    live_callframe_recovery=spec.live_callframe_recovery,
                    cross_process_attach_probe=spec.cross_process_attach_probe,
                    execute_action=True,
                    review_approved=True,
                    requested_action="evaluate",
                    expression=self._step_expression(step),
                    callframe_evaluation_policy="read_only",
                    pause_session_id=spec.pause_session_id,
                    target_id=spec.target_id,
                    attached_session_id=spec.attached_session_id,
                    live_callframe_id=spec.live_callframe_id,
                    reviewer=spec.reviewer,
                ),
            )
            inner = result.execution
            inner_policy = result.side_effect_policy
            error = result.error
            status = "executed" if result.status == "executed" else result.status
            blockers_after = [] if status == "executed" else [result.reason or "planned_step_execution_failed"]
            executor_artifact = "workspace/paused-session-cross-process-one-action-execution.json"
        else:
            result = PausedSessionPreActionSubscribeAndActionManager().execute(
                page,
                PausedSessionPreActionSubscribeAndActionSpec(
                    live_callframe_recovery=spec.live_callframe_recovery,
                    cross_process_attach_probe=spec.cross_process_attach_probe,
                    execute_orchestration=True,
                    review_approved=True,
                    requested_action=self._action_for_method(method),
                    pause_session_id=spec.pause_session_id,
                    target_id=spec.target_id,
                    attached_session_id=spec.attached_session_id,
                    live_callframe_id=spec.live_callframe_id,
                    timeout_ms=spec.timeout_ms,
                    observed_paused_event=spec.observed_paused_event,
                    reviewer=spec.reviewer,
                    require_matching_session_id=spec.require_matching_session_id,
                ),
            )
            inner = result.orchestration
            inner_policy = result.side_effect_policy
            error = result.error
            status = "executed" if result.status == "captured" else result.status
            blockers_after = [] if status == "executed" else [result.reason or "planned_step_execution_failed"]
            executor_artifact = "workspace/paused-session-pre-action-subscribe-and-action.json"
        payload = self._payload(spec, status=status, blockers=blockers_after, inner_result=inner, inner_policy=inner_policy, executor_artifact=executor_artifact, error=error)
        return PausedSessionMultiStepContinuationExecutionResult(status=status, execution=payload, side_effect_policy=self._side_effect_policy(inner_policy), reason=blockers_after[0] if blockers_after else None, error=error)

    @classmethod
    def _blockers(cls, spec: PausedSessionMultiStepContinuationExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["multi_step_execution_request_missing"]
        blockers: list[str] = []
        workflow = spec.workflow
        step = cls._selected_step(spec)
        recovery = spec.live_callframe_recovery
        if not workflow:
            blockers.append("multi_step_workflow_required")
        elif workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        if not step:
            blockers.append("planned_step_not_found")
        else:
            method = str(step.get("method") or "")
            if method not in {"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut", "Debugger.evaluateOnCallFrame"}:
                blockers.append("unsupported_planned_step_method")
            if method == "Debugger.evaluateOnCallFrame" and not cls._step_expression(step):
                blockers.append("evaluate_expression_required")
            if step.get("fingerprint") in set(workflow.get("duplicate_fingerprints") if isinstance(workflow.get("duplicate_fingerprints"), list) else []):
                blockers.append("duplicate_planned_step_fingerprint")
        if not recovery:
            blockers.append("live_callframe_recovery_required")
        elif recovery.get("status") == "blocked" or not recovery.get("live_callframe_recovered"):
            blockers.append("live_callframe_recovery_blocked")
        if recovery.get("target_detached"):
            blockers.append("attached_session_retained_required")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required")
        if not spec.live_callframe_id:
            blockers.append("live_callframe_id_required")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _selected_step(spec: PausedSessionMultiStepContinuationExecutionSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        steps = spec.workflow.get("planned_steps") if isinstance(spec.workflow.get("planned_steps"), list) else []
        for step in steps:
            if isinstance(step, dict) and int(step.get("step_index", 0) or 0) == spec.selected_step_index:
                return step
        return steps[spec.selected_step_index - 1] if 0 <= spec.selected_step_index - 1 < len(steps) and isinstance(steps[spec.selected_step_index - 1], dict) else {}

    @staticmethod
    def _step_expression(step: dict[str, Any]) -> str | None:
        value = step.get("expression") or step.get("callframe_expression") or step.get("callFrameExpression")
        return str(value) if value is not None else None

    @staticmethod
    def _action_for_method(method: str) -> str:
        return {
            "Debugger.resume": "resume",
            "Debugger.stepOver": "step_over",
            "Debugger.stepInto": "step_into",
            "Debugger.stepOut": "step_out",
        }.get(method, method)

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionMultiStepContinuationExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        executor_artifact: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        workflow = spec.workflow if spec else {}
        step = cls._selected_step(spec) if spec else {}
        policy = inner_policy or {}
        return {
            "schema_version": "reverse-deepagent.paused-session-multi-step-continuation-execution.v1",
            "status": status,
            "workflow_id": workflow.get("workflow_id"),
            "pause_session_id": spec.pause_session_id if spec else workflow.get("pause_session_id"),
            "target_id": spec.target_id if spec else workflow.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "selected_step_index": spec.selected_step_index if spec else None,
            "selected_step": step,
            "selected_method": step.get("method"),
            "execute_iteration_requested": bool(spec and spec.execute_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "executor_artifact": executor_artifact or step.get("expected_executor_artifact"),
            "executor_result": inner_result or {},
            "executor_status": (inner_result or {}).get("status"),
            "paused_event_captured": bool((inner_result or {}).get("paused_event_captured")),
            "live_callframe_recovery_ready": bool((inner_result or {}).get("live_callframe_recovery_ready")),
            "callframe_evaluated": bool(policy.get("callframe_evaluated")),
            "browser_resumed": bool(policy.get("browser_resumed")),
            "debugger_stepped": bool(policy.get("debugger_stepped")),
            "cdp_command_sent": bool(policy.get("cdp_command_sent")),
            "debugger_event_subscribed": bool(policy.get("debugger_event_subscribed")),
            "manual_checkpoint_required_after_step": True,
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "multi_step_iteration_executed": status == "executed",
            "automatic_loop": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, paused_captured=bool((inner_result or {}).get("paused_event_captured"))),
            "side_effect_policy": cls._side_effect_policy(policy),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        cdp_sent = bool(inner_policy.get("cdp_command_sent"))
        return {
            "read_only": not cdp_sent,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": cdp_sent,
            "debugger_event_subscribed": bool(inner_policy.get("debugger_event_subscribed")),
            "paused_event_captured": bool(inner_policy.get("paused_event_captured")),
            "browser_resumed": bool(inner_policy.get("browser_resumed")),
            "debugger_stepped": bool(inner_policy.get("debugger_stepped")),
            "callframe_evaluated": bool(inner_policy.get("callframe_evaluated")),
            "runtime_mutated": False,
            "cross_process_action_executed": bool(inner_policy.get("cross_process_action_executed") or cdp_sent),
            "multi_step_continuation_executed": cdp_sent,
            "bounded_one_iteration_only": True,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "multi_step_execution_request_missing": ("request", "No multi-step continuation execution request was provided.", "request_multi_step_continuation_execution"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step continuation workflow is required.", "plan_multi_step_continuation_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The supplied continuation workflow is not ready for review.", "review_or_replan_multi_step_continuation_workflow"),
            "planned_step_not_found": ("workflow", "The selected planned step does not exist.", "select_existing_planned_step"),
            "unsupported_planned_step_method": ("action", "The selected step method is not supported by the bounded executor.", "select_supported_debugger_action"),
            "evaluate_expression_required": ("action", "Evaluate-on-callframe execution requires an expression in the planned step.", "provide_evaluate_expression"),
            "duplicate_planned_step_fingerprint": ("journal", "The selected step fingerprint already exists in the workflow duplicate guard.", "review_duplicate_step_before_execution"),
            "live_callframe_recovery_required": ("debugger", "Fresh live callFrame recovery evidence is required before execution.", "recover_live_callframe_from_checkpoint"),
            "live_callframe_recovery_blocked": ("debugger", "The supplied live callFrame recovery evidence is blocked.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_retained_required": ("debugger", "A retained attached session is required for execution.", "rerun_attach_probe_without_detach_or_attach_again"),
            "attached_session_id_required": ("debugger", "The attached flattened CDP session id is required.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "The recovered live callFrame id is required.", "recover_live_callframe_from_checkpoint"),
            "review_approval_required": ("review", "Executing a planned continuation iteration requires explicit review approval.", "approve_multi_step_continuation_iteration"),
            "planned_step_execution_failed": ("runtime", "The selected planned step failed during execution.", "inspect_multi_step_continuation_execution"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_execution"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_execution"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_multi_step_continuation_execution"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], paused_captured: bool) -> str:
        if blockers:
            return "inspect_multi_step_continuation_execution_blockers"
        if status == "ready_for_review":
            return "approve_multi_step_continuation_iteration"
        if status == "review_required":
            return "approve_multi_step_continuation_iteration"
        if status == "executed" and paused_captured:
            return "checkpoint_cross_process_continuation"
        if status == "executed":
            return "review_multi_step_continuation_execution_result"
        if status == "timed_out":
            return "review_or_rerun_multi_step_continuation_iteration"
        return "inspect_multi_step_continuation_execution"


