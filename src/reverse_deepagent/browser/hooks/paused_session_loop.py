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

from reverse_deepagent.browser.hooks.paused_session_cross_process import (
    PausedSessionMultiStepContinuationExecutionSpec,
    PausedSessionMultiStepContinuationExecutionManager,
)

@dataclass(slots=True)
class PausedSessionMultiStepLoopPlanSpec:
    """Review-only loop plan after one or more multi-step continuation iterations.

    This descriptor composes existing lifecycle / workflow / execution / checkpoint evidence into
    the next reviewed loop checkpoint. It does not send CDP commands, recover callFrames,
    subscribe to debugger events, execute actions, or advance the loop automatically.
    """

    session_lifecycle: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    latest_execution: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    previous_loop_plan: dict[str, Any] = field(default_factory=dict)
    loop_id: str | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    max_loop_iterations: int = 3
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionMultiStepLoopPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_multi_step_loop_plan")
            or context.get("pausedSessionMultiStepLoopPlan")
            or context.get("paused-session-multi-step-loop-plan")
            or context.get("paused_session_continuation_loop_plan")
            or context.get("pausedSessionContinuationLoopPlan")
            or context.get("multi_step_continuation_loop_plan")
            or context.get("multiStepContinuationLoopPlan")
            or context.get("plan_paused_session_continuation_loop")
            or context.get("planPausedSessionContinuationLoop")
        )
        lifecycle = cls._nested(
            _first_dict(
                context,
                "paused_session_cross_process_session_lifecycle",
                "pausedSessionCrossProcessSessionLifecycle",
                "paused-session-cross-process-session-lifecycle",
                "cross_process_session_lifecycle",
                "crossProcessSessionLifecycle",
                "paused_session_lifecycle",
                "pausedSessionLifecycle",
            ),
            "lifecycle",
        )
        workflow = cls._nested(
            _first_dict(
                context,
                "paused_session_multi_step_continuation_workflow",
                "pausedSessionMultiStepContinuationWorkflow",
                "paused-session-multi-step-continuation-workflow",
                "multi_step_continuation_workflow",
                "multiStepContinuationWorkflow",
                "continuation_workflow",
                "continuationWorkflow",
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
                "latest_execution",
                "latestExecution",
            ),
            "execution",
        )
        checkpoint = cls._nested(
            _first_dict(
                context,
                "paused_session_cross_process_continuation_checkpoint",
                "pausedSessionCrossProcessContinuationCheckpoint",
                "paused-session-cross-process-continuation-checkpoint",
                "cross_process_continuation_checkpoint",
                "crossProcessContinuationCheckpoint",
                "continuation_checkpoint",
                "continuationCheckpoint",
            ),
            "checkpoint",
        )
        previous_loop = cls._nested(
            _first_dict(
                context,
                "paused_session_multi_step_loop_plan",
                "pausedSessionMultiStepLoopPlan",
                "paused-session-multi-step-loop-plan",
                "previous_loop_plan",
                "previousLoopPlan",
                "loop_plan",
                "loopPlan",
            ),
            "loop_plan",
        )
        if not requested and not any((lifecycle, workflow, execution, checkpoint, previous_loop)):
            return None
        max_raw = context.get("max_loop_iterations", context.get("maxLoopIterations", previous_loop.get("max_loop_iterations", 3)))
        try:
            max_loop_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_loop_iterations = 3
        pause_session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or execution.get("pause_session_id")
            or workflow.get("pause_session_id")
            or lifecycle.get("pause_session_id")
            or checkpoint.get("pause_session_id")
        )
        target_id = context.get("target_id") or context.get("targetId") or execution.get("target_id") or workflow.get("target_id") or lifecycle.get("target_id") or checkpoint.get("target_id")
        loop_id = context.get("loop_id") or context.get("loopId") or previous_loop.get("loop_id") or workflow.get("workflow_id") or "paused-session-continuation-loop"
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or previous_loop.get("reviewer")
        return cls(
            session_lifecycle=lifecycle,
            multi_step_workflow=workflow,
            latest_execution=execution,
            continuation_checkpoint=checkpoint,
            previous_loop_plan=previous_loop,
            loop_id=str(loop_id).strip() if loop_id else None,
            pause_session_id=str(pause_session_id).strip() if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            max_loop_iterations=max(1, min(max_loop_iterations, 10)),
            reviewer=str(reviewer).strip() if reviewer else None,
        )

    @staticmethod
    def _nested(value: dict[str, Any], key: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        nested = value.get(key)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(value)


@dataclass(slots=True)
class PausedSessionMultiStepLoopPlanResult:
    status: str
    loop_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "loop_plan": self.loop_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionMultiStepLoopPlanManager:
    """Review-only bounded loop planner for paused-session continuation iterations."""

    def plan(self, spec: PausedSessionMultiStepLoopPlanSpec | None) -> PausedSessionMultiStepLoopPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionMultiStepLoopPlanResult(status=status, loop_plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionMultiStepLoopPlanSpec | None) -> list[str]:
        if spec is None:
            return ["multi_step_loop_plan_request_missing"]
        blockers: list[str] = []
        workflow = spec.multi_step_workflow
        lifecycle = spec.session_lifecycle
        execution = spec.latest_execution
        checkpoint = spec.continuation_checkpoint
        if not spec.pause_session_id:
            blockers.append("pause_session_id_required")
        if not workflow:
            blockers.append("multi_step_workflow_required")
        elif workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        elif not cls._workflow_steps(workflow):
            blockers.append("planned_steps_required")
        if lifecycle:
            lifecycle_status = str(lifecycle.get("status") or "")
            if lifecycle_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("session_lifecycle_blocked")
        if execution:
            execution_status = str(execution.get("status") or "")
            if execution_status in {"blocked", "failed", "failure", "error", "unsupported", "timed_out"}:
                blockers.append("latest_iteration_not_ready")
            if execution_status == "executed" and not checkpoint:
                blockers.append("followup_checkpoint_required")
            elif execution_status == "executed" and checkpoint and not cls._checkpoint_ready(checkpoint):
                blockers.append("followup_checkpoint_not_ready")
        if cls._completed_iteration_count(spec) >= spec.max_loop_iterations:
            blockers.append("max_loop_iterations_reached")
        if workflow and cls._next_step(spec) is None:
            blockers.append("no_remaining_planned_steps")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _workflow_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
        steps = workflow.get("planned_steps") if isinstance(workflow.get("planned_steps"), list) else []
        return [dict(step) for step in steps if isinstance(step, dict)]

    @staticmethod
    def _checkpoint_ready(checkpoint: dict[str, Any]) -> bool:
        return bool(
            checkpoint.get("continuation_ready_for_next_action")
            or checkpoint.get("live_callframe_recovery_ready")
            or checkpoint.get("live_callframe_recovered")
            or str(checkpoint.get("status") or "") in {"ready_for_next_action_review", "ready_for_live_callframe_recovery", "ready_for_review"}
        )

    @classmethod
    def _completed_iteration_count(cls, spec: PausedSessionMultiStepLoopPlanSpec | None) -> int:
        if spec is None:
            return 0
        previous = spec.previous_loop_plan
        previous_count = 0
        for key in ("completed_iteration_count", "observed_iteration_count", "planned_iteration_count"):
            try:
                previous_count = max(previous_count, int(previous.get(key) or 0))
            except (TypeError, ValueError):
                pass
        latest_status = str(spec.latest_execution.get("status") or "")
        latest_executed = latest_status == "executed" or spec.latest_execution.get("multi_step_iteration_executed") is True
        latest_index = 0
        try:
            latest_index = int(spec.latest_execution.get("selected_step_index") or 0)
        except (TypeError, ValueError):
            latest_index = 0
        return max(previous_count, latest_index if latest_executed else 0)

    @classmethod
    def _next_step(cls, spec: PausedSessionMultiStepLoopPlanSpec | None) -> dict[str, Any] | None:
        if spec is None:
            return None
        steps = cls._workflow_steps(spec.multi_step_workflow)
        completed = cls._completed_iteration_count(spec)
        for step in steps:
            try:
                index = int(step.get("step_index") or 0)
            except (TypeError, ValueError):
                index = 0
            if index > completed:
                return step
        return None

    @classmethod
    def _payload(cls, spec: PausedSessionMultiStepLoopPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        workflow = spec.multi_step_workflow if spec else {}
        lifecycle = spec.session_lifecycle if spec else {}
        execution = spec.latest_execution if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        steps = cls._workflow_steps(workflow)
        completed_count = cls._completed_iteration_count(spec)
        next_step = cls._next_step(spec)
        iterations = cls._iteration_plan(steps, completed_count=completed_count, max_loop_iterations=spec.max_loop_iterations if spec else 0)
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-multi-step-loop-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "loop_id": spec.loop_id if spec else None,
            "workflow_id": workflow.get("workflow_id"),
            "pause_session_id": spec.pause_session_id if spec else workflow.get("pause_session_id"),
            "target_id": spec.target_id if spec else workflow.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "max_loop_iterations": spec.max_loop_iterations if spec else 0,
            "planned_iteration_count": len(iterations),
            "completed_iteration_count": completed_count,
            "remaining_iteration_count": max(0, len(steps) - completed_count),
            "source_statuses": {
                "session_lifecycle": lifecycle.get("status"),
                "multi_step_workflow": workflow.get("status"),
                "latest_execution": execution.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
            },
            "next_iteration": cls._next_iteration(next_step, completed_count=completed_count, ready=ready),
            "iteration_plan": iterations,
            "checkpoint_sequence": cls._checkpoint_sequence(next_step, checkpoint),
            "readiness": {
                "next_loop_iteration_reviewable": bool(ready and next_step),
                "requires_review_approval_per_iteration": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_followup_checkpoint_after_iteration": True,
                "requires_lifecycle_review_before_loop": bool(lifecycle),
                "automatic_live_callframe_recovery_supported": False,
                "automatic_multi_step_loop_supported": False,
                "automatic_queue_advance_supported": False,
                "automatic_wrapper_continuation_supported": False,
                "next_manual_checkpoint_required": True,
            },
            "journal_plan": {
                "append_only": True,
                "writes_journal": False,
                "journal_artifact": "workspace/paused-session-multi-step-loop-plan.json",
                "records_latest_execution": bool(execution),
                "records_followup_checkpoint": bool(checkpoint),
                "manual_append_after_each_reviewed_iteration": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers=blockers, next_step=next_step),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _iteration_plan(steps: list[dict[str, Any]], *, completed_count: int, max_loop_iterations: int) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        for step in steps:
            try:
                index = int(step.get("step_index") or 0)
            except (TypeError, ValueError):
                index = 0
            if index <= completed_count:
                continue
            if len(plan) >= max_loop_iterations:
                break
            plan.append({
                "iteration_index": len(plan) + 1,
                "workflow_step_index": index,
                "method": step.get("method"),
                "fingerprint": step.get("fingerprint"),
                "expected_executor_artifact": step.get("expected_executor_artifact"),
                "expected_followup_checkpoint": step.get("expected_followup_checkpoint") or "workspace/paused-session-cross-process-continuation-checkpoint.json",
                "requires_review_approval": True,
                "requires_lifecycle_recheck": True,
                "requires_fresh_live_callframe": True,
                "stops_after_iteration": True,
                "would_execute": False,
            })
        return plan

    @staticmethod
    def _next_iteration(next_step: dict[str, Any] | None, *, completed_count: int, ready: bool) -> dict[str, Any]:
        if not next_step:
            return {"available": False, "ready_for_review": False, "reason": "no_remaining_planned_steps"}
        return {
            "available": True,
            "ready_for_review": ready,
            "completed_iteration_count": completed_count,
            "workflow_step_index": next_step.get("step_index"),
            "method": next_step.get("method"),
            "fingerprint": next_step.get("fingerprint"),
            "review_action": "approve_paused_session_loop_iteration",
            "execution_artifact": "workspace/paused-session-multi-step-continuation-execution.json",
            "would_execute": False,
        }

    @staticmethod
    def _checkpoint_sequence(next_step: dict[str, Any] | None, checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"order": 1, "action": "review_session_lifecycle", "artifact": "workspace/paused-session-cross-process-session-lifecycle.json", "automatic": False},
            {"order": 2, "action": "recover_fresh_live_callframe", "artifact": "workspace/paused-session-live-callframe-recovery.json", "automatic": False},
            {"order": 3, "action": "execute_one_reviewed_iteration", "artifact": "workspace/paused-session-multi-step-continuation-execution.json", "automatic": False, "workflow_step_index": next_step.get("step_index") if next_step else None},
            {"order": 4, "action": "checkpoint_captured_pause", "artifact": "workspace/paused-session-cross-process-continuation-checkpoint.json", "automatic": False, "current_checkpoint_status": checkpoint.get("status")},
            {"order": 5, "action": "replan_loop_before_next_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False},
        ]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "multi_step_loop_plan_request_missing": ("request", "No paused-session loop plan request was provided.", "request_paused_session_loop_plan"),
            "pause_session_id_required": ("session", "A pause session id is required to plan loop continuation.", "provide_pause_session_id"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step continuation workflow is required.", "plan_multi_step_continuation_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The supplied multi-step workflow is not ready for review.", "review_or_replan_multi_step_workflow"),
            "planned_steps_required": ("workflow", "The supplied workflow has no planned steps.", "provide_planned_steps"),
            "session_lifecycle_blocked": ("lifecycle", "The supplied session lifecycle descriptor is blocked.", "resolve_paused_session_lifecycle_blockers"),
            "latest_iteration_not_ready": ("execution", "The latest one-iteration execution is blocked, failed, or timed out.", "review_latest_iteration_result"),
            "followup_checkpoint_required": ("checkpoint", "Executed iterations require a continuation checkpoint before loop planning can continue.", "checkpoint_cross_process_continuation"),
            "followup_checkpoint_not_ready": ("checkpoint", "The supplied continuation checkpoint is not ready for the next action.", "recover_or_refresh_continuation_checkpoint"),
            "max_loop_iterations_reached": ("review", "The bounded loop iteration budget has been reached.", "increase_loop_budget_after_review_or_stop"),
            "no_remaining_planned_steps": ("workflow", "All planned workflow steps have already been accounted for.", "review_loop_completion_or_replan_workflow"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, blockers: list[str], next_step: dict[str, Any] | None) -> str:
        if blockers:
            return "inspect_paused_session_loop_plan_blockers"
        if next_step:
            return "review_next_paused_session_loop_iteration"
        return "review_paused_session_loop_completion"


@dataclass(slots=True)
class PausedSessionAutomaticLoopReadinessSpec:
    """Review-only readiness gate for future automatic paused-session loop execution.

    This descriptor consumes existing multi-step loop evidence and answers whether a later
    bounded automatic loop executor could even be reviewed. It never executes actions,
    recovers callFrames, subscribes to debugger events, advances queues, or keeps a
    long-lived cross-process session alive.
    """

    loop_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    session_lifecycle: dict[str, Any] = field(default_factory=dict)
    latest_loop_execution: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    max_automatic_iterations: int = 2
    require_review_per_iteration: bool = True
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopReadinessSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_readiness")
            or context.get("pausedSessionAutomaticLoopReadiness")
            or context.get("paused-session-automatic-loop-readiness")
            or context.get("paused_session_multi_step_automatic_loop_readiness")
            or context.get("pausedSessionMultiStepAutomaticLoopReadiness")
            or context.get("review_paused_session_automatic_loop_readiness")
            or context.get("reviewPausedSessionAutomaticLoopReadiness")
        )
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
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
        lifecycle_container = _first_dict(
            context,
            "paused_session_cross_process_session_lifecycle",
            "pausedSessionCrossProcessSessionLifecycle",
            "paused-session-cross-process-session-lifecycle",
            "cross_process_session_lifecycle",
            "crossProcessSessionLifecycle",
            "paused_session_lifecycle",
            "pausedSessionLifecycle",
        )
        lifecycle = dict(lifecycle_container.get("lifecycle")) if isinstance(lifecycle_container.get("lifecycle"), dict) else lifecycle_container
        execution_container = _first_dict(
            context,
            "paused_session_multi_step_loop_execution",
            "pausedSessionMultiStepLoopExecution",
            "paused-session-multi-step-loop-execution",
            "latest_loop_execution",
            "latestLoopExecution",
        )
        execution = dict(execution_container.get("execution")) if isinstance(execution_container.get("execution"), dict) else execution_container
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
        if not requested and not any((loop_plan, workflow, lifecycle, execution, checkpoint)):
            return None
        max_raw = context.get("max_automatic_iterations", context.get("maxAutomaticIterations", 2))
        try:
            max_automatic_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_automatic_iterations = 2
        return cls(
            loop_plan=loop_plan,
            multi_step_workflow=workflow,
            session_lifecycle=lifecycle,
            latest_loop_execution=execution,
            continuation_checkpoint=checkpoint,
            max_automatic_iterations=max(1, min(max_automatic_iterations, 5)),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopReadinessResult:
    status: str
    readiness: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readiness": self.readiness,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionAutomaticLoopReadinessManager:
    """Read-only readiness descriptor before any future automatic paused-session loop executor."""

    def review(self, spec: PausedSessionAutomaticLoopReadinessSpec | None) -> PausedSessionAutomaticLoopReadinessResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopReadinessResult(status=status, readiness=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopReadinessSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_readiness_request_missing"]
        blockers: list[str] = []
        loop_plan = spec.loop_plan
        workflow = spec.multi_step_workflow
        lifecycle = spec.session_lifecycle
        execution = spec.latest_loop_execution
        checkpoint = spec.continuation_checkpoint
        readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
        if not loop_plan:
            blockers.append("multi_step_loop_plan_required")
        elif loop_plan.get("status") != "ready_for_review":
            blockers.append("multi_step_loop_plan_not_ready")
        elif readiness.get("next_loop_iteration_reviewable") is not True:
            blockers.append("next_loop_iteration_not_reviewable")
        if not workflow:
            blockers.append("multi_step_workflow_required")
        elif workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        if lifecycle:
            lifecycle_status = str(lifecycle.get("status") or "")
            if lifecycle_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("session_lifecycle_blocked")
        else:
            blockers.append("session_lifecycle_required_for_automatic_loop_review")
        if execution:
            if execution.get("automatic_multi_step_loop") is not False:
                blockers.append("previous_execution_claims_automatic_loop")
            if execution.get("loop_advanced") is True or execution.get("queue_advanced") is True:
                blockers.append("previous_execution_already_advanced_loop_or_queue")
            if execution.get("status") in {"blocked", "failed", "failure", "error", "timed_out"}:
                blockers.append("latest_loop_execution_not_reviewable")
            if execution.get("multi_step_loop_iteration_executed") is True and not checkpoint:
                blockers.append("post_iteration_checkpoint_required")
        if checkpoint:
            checkpoint_status = str(checkpoint.get("status") or "")
            checkpoint_ready = bool(
                checkpoint.get("continuation_ready_for_next_action")
                or checkpoint.get("live_callframe_recovery_ready")
                or checkpoint.get("live_callframe_recovered")
                or checkpoint_status in {"ready_for_next_action_review", "ready_for_live_callframe_recovery", "ready_for_review"}
            )
            if not checkpoint_ready:
                blockers.append("continuation_checkpoint_not_ready")
        if spec.require_review_per_iteration is not True:
            blockers.append("review_per_iteration_required")
        if spec.max_automatic_iterations < 1:
            blockers.append("automatic_loop_iteration_budget_required")
        # This readiness can become ready for review, but it still does not enable a real automatic executor.
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopReadinessSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        loop_plan = spec.loop_plan if spec else {}
        workflow = spec.multi_step_workflow if spec else {}
        lifecycle = spec.session_lifecycle if spec else {}
        execution = spec.latest_loop_execution if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
        iteration_plan = loop_plan.get("iteration_plan") if isinstance(loop_plan.get("iteration_plan"), list) else []
        ready = status == "ready_for_review"
        candidate_iterations = [dict(item) for item in iteration_plan if isinstance(item, dict)][: spec.max_automatic_iterations if spec else 0]
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-readiness.v1",
            "status": status,
            "ready_for_review": ready,
            "automation_executor_implemented": False,
            "automatic_multi_step_loop_supported": False,
            "loop_id": loop_plan.get("loop_id"),
            "workflow_id": loop_plan.get("workflow_id") or workflow.get("workflow_id"),
            "pause_session_id": loop_plan.get("pause_session_id") or workflow.get("pause_session_id") or lifecycle.get("pause_session_id"),
            "target_id": loop_plan.get("target_id") or workflow.get("target_id") or lifecycle.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "max_automatic_iterations": spec.max_automatic_iterations if spec else 0,
            "candidate_iteration_count": len(candidate_iterations),
            "candidate_iterations": [
                {
                    "iteration_index": item.get("iteration_index"),
                    "workflow_step_index": item.get("workflow_step_index"),
                    "method": item.get("method"),
                    "fingerprint": item.get("fingerprint"),
                    "requires_review_approval": True,
                    "requires_fresh_live_callframe": True,
                    "requires_checkpoint_after_iteration": True,
                    "would_execute_in_this_descriptor": False,
                }
                for item in candidate_iterations
            ],
            "source_statuses": {
                "multi_step_loop_plan": loop_plan.get("status"),
                "multi_step_workflow": workflow.get("status"),
                "session_lifecycle": lifecycle.get("status"),
                "latest_loop_execution": execution.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
            },
            "readiness_checks": {
                "loop_plan_ready": loop_plan.get("status") == "ready_for_review",
                "next_iteration_reviewable": readiness.get("next_loop_iteration_reviewable") is True,
                "workflow_ready": workflow.get("status") == "ready_for_review",
                "session_lifecycle_present": bool(lifecycle),
                "review_required_per_iteration": spec.require_review_per_iteration if spec else True,
                "fresh_live_callframe_required_per_iteration": True,
                "retained_attached_session_required_per_iteration": True,
                "checkpoint_required_after_each_iteration": True,
                "automation_executor_implemented": False,
                "automatic_loop_may_run_without_review": False,
            },
            "future_executor_contract": {
                "executor_name": "execute_paused_session_automatic_loop",
                "implemented": False,
                "would_require_review_approval": True,
                "would_require_ready_readiness_descriptor": True,
                "would_execute_bounded_iterations_only": True,
                "would_stop_after_each_checkpoint": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_readiness_request_missing": ("request", "No automatic loop readiness request was provided.", "request_paused_session_automatic_loop_readiness"),
            "multi_step_loop_plan_required": ("loop", "A ready paused-session multi-step loop plan is required.", "plan_paused_session_multi_step_loop"),
            "multi_step_loop_plan_not_ready": ("loop", "The paused-session multi-step loop plan is not ready.", "review_paused_session_multi_step_loop_plan"),
            "next_loop_iteration_not_reviewable": ("loop", "The next loop iteration is not reviewable.", "replan_loop_or_checkpoint_continuation"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step continuation workflow is required.", "plan_multi_step_continuation_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The multi-step workflow is not ready.", "review_or_replan_multi_step_workflow"),
            "session_lifecycle_required_for_automatic_loop_review": ("session", "A session lifecycle descriptor is required before automatic loop readiness review.", "review_cross_process_session_lifecycle"),
            "session_lifecycle_blocked": ("session", "The session lifecycle descriptor is blocked.", "resolve_session_lifecycle_blockers"),
            "previous_execution_claims_automatic_loop": ("safety", "Previous execution claims automatic loop behavior and must be audited first.", "audit_previous_loop_execution"),
            "previous_execution_already_advanced_loop_or_queue": ("safety", "Previous execution advanced loop or queue state automatically.", "audit_loop_queue_state"),
            "latest_loop_execution_not_reviewable": ("execution", "Latest loop execution is blocked, failed, or timed out.", "review_latest_loop_execution"),
            "post_iteration_checkpoint_required": ("checkpoint", "A post-iteration checkpoint is required after executed loop iteration.", "checkpoint_cross_process_continuation"),
            "continuation_checkpoint_not_ready": ("checkpoint", "The continuation checkpoint is not ready.", "refresh_continuation_checkpoint"),
            "review_per_iteration_required": ("review", "Automatic loop readiness still requires review per iteration.", "restore_review_per_iteration_gate"),
            "automatic_loop_iteration_budget_required": ("budget", "A bounded automatic iteration budget is required.", "set_automatic_loop_iteration_budget"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_readiness"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_readiness"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_readiness"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_readiness_blockers"
        if status == "ready_for_review":
            return "review_future_bounded_automatic_loop_executor_contract"
        return "inspect_paused_session_automatic_loop_readiness"


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutionPlanSpec:
    """Plan-only descriptor for a future bounded paused-session automatic loop executor.

    This consumes the automatic-loop readiness descriptor and materializes the next
    executor contract review input. It does not execute iterations, send CDP commands,
    recover callFrames, subscribe to debugger events, advance queues, or manage a
    long-lived cross-process session.
    """

    automatic_loop_readiness: dict[str, Any] = field(default_factory=dict)
    max_planned_iterations: int = 2
    require_review_per_iteration: bool = True
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopExecutionPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_execution_plan")
            or context.get("pausedSessionAutomaticLoopExecutionPlan")
            or context.get("paused-session-automatic-loop-execution-plan")
            or context.get("plan_paused_session_automatic_loop_execution")
            or context.get("planPausedSessionAutomaticLoopExecution")
            or context.get("automatic_loop_execution_plan")
            or context.get("automaticLoopExecutionPlan")
        )
        readiness_container = _first_dict(
            context,
            "paused_session_automatic_loop_readiness",
            "pausedSessionAutomaticLoopReadiness",
            "paused-session-automatic-loop-readiness",
            "paused_session_multi_step_automatic_loop_readiness",
            "pausedSessionMultiStepAutomaticLoopReadiness",
            "automatic_loop_readiness",
            "automaticLoopReadiness",
        )
        readiness = dict(readiness_container.get("readiness")) if isinstance(readiness_container.get("readiness"), dict) else readiness_container
        if not requested and not readiness:
            return None
        default_budget = readiness.get("max_automatic_iterations") or readiness.get("candidate_iteration_count") or 2
        max_raw = context.get("max_planned_iterations", context.get("maxPlannedIterations", default_budget))
        try:
            max_planned_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_planned_iterations = 2
        return cls(
            automatic_loop_readiness=readiness,
            max_planned_iterations=max(1, min(max_planned_iterations, 5)),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutionPlanResult:
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


class PausedSessionAutomaticLoopExecutionPlanManager:
    """Review-only execution plan descriptor for a future bounded automatic loop executor."""

    def plan(self, spec: PausedSessionAutomaticLoopExecutionPlanSpec | None) -> PausedSessionAutomaticLoopExecutionPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopExecutionPlanResult(status=status, plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopExecutionPlanSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_execution_plan_request_missing"]
        readiness = spec.automatic_loop_readiness
        blockers: list[str] = []
        if not readiness:
            blockers.append("automatic_loop_readiness_required")
        elif readiness.get("status") != "ready_for_review" or readiness.get("ready_for_review") is not True:
            blockers.append("automatic_loop_readiness_not_ready")
        if readiness.get("automation_executor_implemented") is True:
            blockers.append("unexpected_existing_automatic_loop_executor")
        if readiness.get("automatic_multi_step_loop_supported") is True:
            blockers.append("readiness_claims_automatic_loop_supported")
        readiness_blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
        if readiness_blockers:
            blockers.append("automatic_loop_readiness_has_blockers")
        candidate_iterations = readiness.get("candidate_iterations") if isinstance(readiness.get("candidate_iterations"), list) else []
        if not candidate_iterations:
            blockers.append("automatic_loop_candidate_iterations_required")
        if spec.require_review_per_iteration is not True:
            blockers.append("review_per_iteration_required")
        if spec.max_planned_iterations < 1:
            blockers.append("automatic_loop_plan_iteration_budget_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopExecutionPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        readiness = spec.automatic_loop_readiness if spec else {}
        candidate_iterations = readiness.get("candidate_iterations") if isinstance(readiness.get("candidate_iterations"), list) else []
        planned_iterations = [dict(item) for item in candidate_iterations if isinstance(item, dict)][: spec.max_planned_iterations if spec else 0]
        ready = status == "ready_for_review"
        plan_id = f"automatic-loop-plan:{readiness.get('loop_id') or readiness.get('workflow_id') or 'unbound'}"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-execution-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "execution_plan_ready_for_review": ready,
            "plan_id": plan_id,
            "loop_id": readiness.get("loop_id"),
            "workflow_id": readiness.get("workflow_id"),
            "pause_session_id": readiness.get("pause_session_id"),
            "target_id": readiness.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_readiness": {
                "schema_version": readiness.get("schema_version"),
                "status": readiness.get("status"),
                "ready_for_review": bool(readiness.get("ready_for_review")),
                "automation_executor_implemented": bool(readiness.get("automation_executor_implemented")),
                "automatic_multi_step_loop_supported": bool(readiness.get("automatic_multi_step_loop_supported")),
                "candidate_iteration_count": readiness.get("candidate_iteration_count", len(candidate_iterations)),
                "next_action": readiness.get("next_action"),
            },
            "planned_iteration_count": len(planned_iterations),
            "max_planned_iterations": spec.max_planned_iterations if spec else 0,
            "planned_iterations": [
                {
                    "iteration_index": item.get("iteration_index"),
                    "workflow_step_index": item.get("workflow_step_index"),
                    "method": item.get("method"),
                    "fingerprint": item.get("fingerprint"),
                    "plan_status": "requires_explicit_review",
                    "requires_review_approval": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "would_execute_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                }
                for item in planned_iterations
            ],
            "review_gates": {
                "requires_ready_automatic_loop_readiness": True,
                "requires_review_approval_before_any_iteration": True,
                "requires_review_per_iteration": spec.require_review_per_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "requires_bounded_iteration_budget": True,
            },
            "future_executor_contract": {
                "executor_name": "execute_paused_session_automatic_loop",
                "implemented": False,
                "executor_artifact": "workspace/paused-session-automatic-loop-execution.json",
                "plan_artifact": "workspace/paused-session-automatic-loop-execution-plan.json",
                "would_require_matching_plan_id": True,
                "would_execute_at_most_planned_iterations": True,
                "would_not_run_as_daemon": True,
                "would_not_manage_long_lived_session": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_execution_plan_request_missing": ("request", "No automatic loop execution plan request was provided.", "request_paused_session_automatic_loop_execution_plan"),
            "automatic_loop_readiness_required": ("readiness", "A ready automatic-loop readiness descriptor is required.", "review_paused_session_automatic_loop_readiness"),
            "automatic_loop_readiness_not_ready": ("readiness", "The automatic-loop readiness descriptor is not ready.", "resolve_automatic_loop_readiness_blockers"),
            "unexpected_existing_automatic_loop_executor": ("safety", "The readiness descriptor claims an executor is already implemented and needs separate audit.", "audit_existing_automatic_loop_executor_claim"),
            "readiness_claims_automatic_loop_supported": ("safety", "The readiness descriptor claims automatic loop support, which this project has not enabled.", "audit_automatic_loop_support_claim"),
            "automatic_loop_readiness_has_blockers": ("readiness", "The readiness descriptor still has blockers.", "resolve_automatic_loop_readiness_blockers"),
            "automatic_loop_candidate_iterations_required": ("plan", "Candidate iterations are required for a bounded execution plan.", "provide_ready_readiness_with_candidate_iterations"),
            "review_per_iteration_required": ("review", "The plan must preserve review per iteration.", "restore_review_per_iteration_gate"),
            "automatic_loop_plan_iteration_budget_required": ("budget", "A bounded planned iteration budget is required.", "set_automatic_loop_plan_iteration_budget"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_execution_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_execution_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_execution_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_execution_plan_blockers"
        if status == "ready_for_review":
            return "review_future_bounded_automatic_loop_executor_plan"
        return "inspect_paused_session_automatic_loop_execution_plan"


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutorPreflightSpec:
    """Read-only preflight descriptor for a future bounded automatic-loop executor.

    This consumes the automatic-loop execution plan descriptor and verifies that the
    future executor input can move to manual review. It never executes iterations,
    sends CDP commands, recovers callFrames, subscribes to paused events, advances
    queues, or manages a long-lived cross-process session.
    """

    automatic_loop_execution_plan: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_review_per_iteration: bool = True
    require_checkpoint_after_each_iteration: bool = True
    max_preflight_iterations: int = 2

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopExecutorPreflightSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_executor_preflight")
            or context.get("pausedSessionAutomaticLoopExecutorPreflight")
            or context.get("paused-session-automatic-loop-executor-preflight")
            or context.get("preflight_paused_session_automatic_loop_executor")
            or context.get("preflightPausedSessionAutomaticLoopExecutor")
            or context.get("automatic_loop_executor_preflight")
            or context.get("automaticLoopExecutorPreflight")
        )
        plan_container = _first_dict(
            context,
            "paused_session_automatic_loop_execution_plan",
            "pausedSessionAutomaticLoopExecutionPlan",
            "paused-session-automatic-loop-execution-plan",
            "plan_paused_session_automatic_loop_execution",
            "planPausedSessionAutomaticLoopExecution",
            "automatic_loop_execution_plan",
            "automaticLoopExecutionPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        if not requested and not plan:
            return None
        default_budget = plan.get("planned_iteration_count") or plan.get("max_planned_iterations") or 2
        max_raw = context.get("max_preflight_iterations", context.get("maxPreflightIterations", default_budget))
        try:
            max_preflight_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_preflight_iterations = 2
        return cls(
            automatic_loop_execution_plan=plan,
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            require_checkpoint_after_each_iteration=bool(context.get("require_checkpoint_after_each_iteration", context.get("requireCheckpointAfterEachIteration", True))),
            max_preflight_iterations=max(1, min(max_preflight_iterations, 5)),
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutorPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "preflight": self.preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionAutomaticLoopExecutorPreflightManager:
    """Review-only executor preflight descriptor for a future bounded automatic loop."""

    def review(self, spec: PausedSessionAutomaticLoopExecutorPreflightSpec | None) -> PausedSessionAutomaticLoopExecutorPreflightResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopExecutorPreflightResult(status=status, preflight=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopExecutorPreflightSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_executor_preflight_request_missing"]
        plan = spec.automatic_loop_execution_plan
        blockers: list[str] = []
        if not plan:
            blockers.append("automatic_loop_execution_plan_required")
        elif plan.get("status") != "ready_for_review" or plan.get("execution_plan_ready_for_review") is not True:
            blockers.append("automatic_loop_execution_plan_not_ready")
        plan_blockers = plan.get("blockers") if isinstance(plan.get("blockers"), list) else []
        if plan_blockers:
            blockers.append("automatic_loop_execution_plan_has_blockers")
        future_contract = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        if not future_contract:
            blockers.append("future_executor_contract_required")
        elif future_contract.get("implemented") is True:
            blockers.append("unexpected_existing_automatic_loop_executor")
        planned_iterations = plan.get("planned_iterations") if isinstance(plan.get("planned_iterations"), list) else []
        if not planned_iterations:
            blockers.append("planned_iterations_required")
        gates = plan.get("review_gates") if isinstance(plan.get("review_gates"), dict) else {}
        if spec.require_review_per_iteration is not True or gates.get("requires_review_per_iteration") is not True:
            blockers.append("review_per_iteration_required")
        if spec.require_checkpoint_after_each_iteration is not True or gates.get("requires_checkpoint_after_each_iteration") is not True:
            blockers.append("checkpoint_after_each_iteration_required")
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        if any(
            policy.get(key) is True
            for key in (
                "cdp_command_sent",
                "debugger_event_subscribed",
                "paused_event_captured",
                "callframe_evaluated",
                "multi_step_continuation_executed",
                "automatic_multi_step_loop",
                "automatic_queue_advance",
                "long_lived_cross_process_session_managed",
                "calls_mcp",
                "mobile_runtime_used",
            )
        ):
            blockers.append("execution_plan_side_effect_claim_detected")
        if spec.max_preflight_iterations < 1:
            blockers.append("executor_preflight_iteration_budget_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopExecutorPreflightSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        plan = spec.automatic_loop_execution_plan if spec else {}
        planned_iterations = plan.get("planned_iterations") if isinstance(plan.get("planned_iterations"), list) else []
        preflight_iterations = [dict(item) for item in planned_iterations if isinstance(item, dict)][: spec.max_preflight_iterations if spec else 0]
        gates = plan.get("review_gates") if isinstance(plan.get("review_gates"), dict) else {}
        future_contract = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-executor-preflight.v1",
            "status": status,
            "ready_for_review": ready,
            "executor_preflight_ready_for_review": ready,
            "preflight_id": f"automatic-loop-executor-preflight:{plan.get('plan_id') or plan.get('loop_id') or 'unbound'}",
            "plan_id": plan.get("plan_id"),
            "loop_id": plan.get("loop_id"),
            "workflow_id": plan.get("workflow_id"),
            "pause_session_id": plan.get("pause_session_id"),
            "target_id": plan.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_execution_plan": {
                "schema_version": plan.get("schema_version"),
                "status": plan.get("status"),
                "execution_plan_ready_for_review": bool(plan.get("execution_plan_ready_for_review")),
                "planned_iteration_count": plan.get("planned_iteration_count", len(planned_iterations)),
                "max_planned_iterations": plan.get("max_planned_iterations"),
                "future_executor_implemented": bool(future_contract.get("implemented")),
                "next_action": plan.get("next_action"),
            },
            "preflight_iteration_count": len(preflight_iterations),
            "max_preflight_iterations": spec.max_preflight_iterations if spec else 0,
            "preflight_iterations": [
                {
                    "iteration_index": item.get("iteration_index"),
                    "workflow_step_index": item.get("workflow_step_index"),
                    "method": item.get("method"),
                    "fingerprint": item.get("fingerprint"),
                    "preflight_status": "requires_explicit_review",
                    "would_execute_in_this_preflight": False,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_review_approval": True,
                    "requires_checkpoint_after_iteration": True,
                }
                for item in preflight_iterations
            ],
            "executor_input_gates": {
                "requires_ready_execution_plan": True,
                "requires_matching_plan_id": True,
                "requires_review_approval_before_any_iteration": True,
                "requires_review_per_iteration": spec.require_review_per_iteration if spec else True,
                "requires_checkpoint_after_each_iteration": spec.require_checkpoint_after_each_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_bounded_iteration_budget": True,
                "requires_stop_after_each_checkpoint": True,
                "ready_to_execute_now": False,
                "executor_implemented": False,
            },
            "future_executor_contract": {
                "executor_name": future_contract.get("executor_name") or "execute_paused_session_automatic_loop",
                "implemented": False,
                "executor_artifact": future_contract.get("executor_artifact") or "workspace/paused-session-automatic-loop-execution.json",
                "preflight_artifact": "workspace/paused-session-automatic-loop-executor-preflight.json",
                "plan_artifact": future_contract.get("plan_artifact") or "workspace/paused-session-automatic-loop-execution-plan.json",
                "would_require_matching_plan_id": True,
                "would_execute_at_most_preflight_iterations": True,
                "would_not_run_as_daemon": True,
                "would_not_manage_long_lived_session": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_executor_preflight_request_missing": ("request", "No automatic loop executor preflight request was provided.", "request_paused_session_automatic_loop_executor_preflight"),
            "automatic_loop_execution_plan_required": ("plan", "A ready automatic-loop execution plan descriptor is required.", "plan_paused_session_automatic_loop_execution"),
            "automatic_loop_execution_plan_not_ready": ("plan", "The automatic-loop execution plan descriptor is not ready.", "resolve_automatic_loop_execution_plan_blockers"),
            "automatic_loop_execution_plan_has_blockers": ("plan", "The automatic-loop execution plan still has blockers.", "resolve_automatic_loop_execution_plan_blockers"),
            "future_executor_contract_required": ("contract", "The future executor contract metadata is required.", "regenerate_automatic_loop_execution_plan"),
            "unexpected_existing_automatic_loop_executor": ("safety", "The plan claims an executor is already implemented and needs separate audit.", "audit_existing_automatic_loop_executor_claim"),
            "planned_iterations_required": ("plan", "Preflight needs bounded planned iterations.", "provide_execution_plan_with_bounded_iterations"),
            "review_per_iteration_required": ("review", "The executor preflight must preserve review per iteration.", "restore_review_per_iteration_gate"),
            "checkpoint_after_each_iteration_required": ("checkpoint", "The executor preflight must require checkpoint after each iteration.", "restore_checkpoint_after_each_iteration_gate"),
            "execution_plan_side_effect_claim_detected": ("safety", "The execution plan claims side effects and must be audited first.", "audit_execution_plan_side_effect_claim"),
            "executor_preflight_iteration_budget_required": ("budget", "A bounded preflight iteration budget is required.", "set_automatic_loop_executor_preflight_budget"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_preflight"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_preflight"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_preflight"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_executor_preflight_blockers"
        if status == "ready_for_review":
            return "review_future_bounded_automatic_loop_executor_preflight"
        return "inspect_paused_session_automatic_loop_executor_preflight"


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutorApprovalPlanSpec:
    """Review-only approval and transaction plan for a future automatic-loop executor.

    This consumes the executor preflight descriptor and prepares the manual approval,
    idempotency, and transaction-journal requirements for a future bounded executor.
    It does not record approval, write journals, execute iterations, send CDP commands,
    recover callFrames, subscribe to paused events, advance queues, or manage sessions.
    """

    automatic_loop_executor_preflight: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    expected_preflight_id: str | None = None
    max_approved_iterations: int = 2

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopExecutorApprovalPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_executor_approval_plan")
            or context.get("pausedSessionAutomaticLoopExecutorApprovalPlan")
            or context.get("paused-session-automatic-loop-executor-approval-plan")
            or context.get("plan_paused_session_automatic_loop_executor_approval")
            or context.get("planPausedSessionAutomaticLoopExecutorApproval")
            or context.get("automatic_loop_executor_approval_plan")
            or context.get("automaticLoopExecutorApprovalPlan")
        )
        preflight_container = _first_dict(
            context,
            "paused_session_automatic_loop_executor_preflight",
            "pausedSessionAutomaticLoopExecutorPreflight",
            "paused-session-automatic-loop-executor-preflight",
            "preflight_paused_session_automatic_loop_executor",
            "preflightPausedSessionAutomaticLoopExecutor",
            "automatic_loop_executor_preflight",
            "automaticLoopExecutorPreflight",
        )
        preflight = dict(preflight_container.get("preflight")) if isinstance(preflight_container.get("preflight"), dict) else preflight_container
        if not requested and not preflight:
            return None
        default_budget = preflight.get("preflight_iteration_count") or preflight.get("max_preflight_iterations") or 2
        max_raw = context.get("max_approved_iterations", context.get("maxApprovedIterations", default_budget))
        try:
            max_approved_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_approved_iterations = 2
        expected_preflight_id = str(context.get("expected_preflight_id") or context.get("expectedPreflightId") or "").strip() or None
        return cls(
            automatic_loop_executor_preflight=preflight,
            reviewer=str(context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or "").strip() or None,
            expected_preflight_id=expected_preflight_id,
            max_approved_iterations=max(1, min(max_approved_iterations, 5)),
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutorApprovalPlanResult:
    status: str
    approval_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "approval_plan": self.approval_plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionAutomaticLoopExecutorApprovalPlanManager:
    """Review-only approval / transaction plan before any automatic-loop executor."""

    def plan(self, spec: PausedSessionAutomaticLoopExecutorApprovalPlanSpec | None) -> PausedSessionAutomaticLoopExecutorApprovalPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopExecutorApprovalPlanResult(status=status, approval_plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopExecutorApprovalPlanSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_executor_approval_plan_request_missing"]
        preflight = spec.automatic_loop_executor_preflight
        blockers: list[str] = []
        if not preflight:
            blockers.append("automatic_loop_executor_preflight_required")
        elif preflight.get("status") != "ready_for_review" or preflight.get("executor_preflight_ready_for_review") is not True:
            blockers.append("automatic_loop_executor_preflight_not_ready")
        if spec.expected_preflight_id and preflight.get("preflight_id") != spec.expected_preflight_id:
            blockers.append("automatic_loop_executor_preflight_id_mismatch")
        preflight_blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
        if preflight_blockers:
            blockers.append("automatic_loop_executor_preflight_has_blockers")
        gates = preflight.get("executor_input_gates") if isinstance(preflight.get("executor_input_gates"), dict) else {}
        if gates.get("ready_to_execute_now") is True:
            blockers.append("preflight_ready_to_execute_claim_detected")
        if gates.get("requires_review_per_iteration") is not True:
            blockers.append("review_per_iteration_required")
        if gates.get("requires_checkpoint_after_each_iteration") is not True:
            blockers.append("checkpoint_after_each_iteration_required")
        future_contract = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        if not future_contract:
            blockers.append("future_executor_contract_required")
        elif future_contract.get("implemented") is True or gates.get("executor_implemented") is True:
            blockers.append("unexpected_existing_automatic_loop_executor")
        preflight_iterations = preflight.get("preflight_iterations") if isinstance(preflight.get("preflight_iterations"), list) else []
        if not preflight_iterations:
            blockers.append("preflight_iterations_required")
        policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        if any(
            policy.get(key) is True
            for key in (
                "cdp_command_sent",
                "cdp_target_attached",
                "debugger_domain_enabled",
                "debugger_event_subscribed",
                "paused_event_captured",
                "callframe_evaluated",
                "runtime_mutated",
                "multi_step_continuation_executed",
                "automatic_multi_step_loop",
                "automatic_queue_advance",
                "long_lived_cross_process_session_managed",
                "calls_mcp",
                "mobile_runtime_used",
            )
        ):
            blockers.append("executor_preflight_side_effect_claim_detected")
        if spec.max_approved_iterations < 1:
            blockers.append("executor_approval_iteration_budget_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopExecutorApprovalPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        preflight = spec.automatic_loop_executor_preflight if spec else {}
        future_contract = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        gates = preflight.get("executor_input_gates") if isinstance(preflight.get("executor_input_gates"), dict) else {}
        preflight_iterations = preflight.get("preflight_iterations") if isinstance(preflight.get("preflight_iterations"), list) else []
        planned_iterations = [dict(item) for item in preflight_iterations if isinstance(item, dict)][: spec.max_approved_iterations if spec else 0]
        preflight_id = preflight.get("preflight_id") or "unbound"
        ready = status == "ready_for_review"
        transaction_id = f"automatic-loop-executor-transaction:{preflight_id}"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-executor-approval-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "approval_plan_ready_for_review": ready,
            "approval_plan_id": f"automatic-loop-executor-approval-plan:{preflight_id}",
            "preflight_id": preflight.get("preflight_id"),
            "plan_id": preflight.get("plan_id"),
            "loop_id": preflight.get("loop_id"),
            "workflow_id": preflight.get("workflow_id"),
            "pause_session_id": preflight.get("pause_session_id"),
            "target_id": preflight.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_executor_preflight": {
                "schema_version": preflight.get("schema_version"),
                "status": preflight.get("status"),
                "executor_preflight_ready_for_review": bool(preflight.get("executor_preflight_ready_for_review")),
                "preflight_iteration_count": preflight.get("preflight_iteration_count", len(preflight_iterations)),
                "max_preflight_iterations": preflight.get("max_preflight_iterations"),
                "ready_to_execute_now": bool(gates.get("ready_to_execute_now")),
                "future_executor_implemented": bool(future_contract.get("implemented")),
                "next_action": preflight.get("next_action"),
            },
            "approval_requirements": {
                "requires_explicit_review_approval": True,
                "requires_non_empty_reviewer_before_recording": True,
                "requires_matching_preflight_id": True,
                "requires_matching_plan_id": True,
                "requires_review_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_retained_attached_session_per_iteration": True,
                "approval_recorded_now": False,
                "approval_record_writer_implemented": False,
                "approval_record_artifact": "workspace/paused-session-automatic-loop-executor-approval-record.json",
            },
            "transaction_plan": {
                "transaction_id": transaction_id,
                "idempotency_key": transaction_id,
                "transaction_started": False,
                "journal_written_now": False,
                "journal_artifact": "workspace/paused-session-automatic-loop-executor-journal.json",
                "result_artifact": "workspace/paused-session-automatic-loop-execution-result.json",
                "requires_append_only_journal": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "requires_manual_resume_after_failure": True,
            },
            "approved_iteration_count": len(planned_iterations),
            "max_approved_iterations": spec.max_approved_iterations if spec else 0,
            "approved_iterations": [
                {
                    "iteration_index": item.get("iteration_index"),
                    "workflow_step_index": item.get("workflow_step_index"),
                    "method": item.get("method"),
                    "fingerprint": item.get("fingerprint"),
                    "approval_status": "requires_explicit_approval_record",
                    "would_execute_in_this_plan": False,
                    "requires_checkpoint_after_iteration": True,
                }
                for item in planned_iterations
            ],
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "executor_implemented": False,
                "approval_recorded": False,
                "transaction_started": False,
                "journal_written": False,
                "requires_ready_executor_preflight": True,
                "requires_approval_record": True,
                "requires_transaction_journal": True,
            },
            "future_executor_contract": {
                "executor_name": future_contract.get("executor_name") or "execute_paused_session_automatic_loop",
                "implemented": False,
                "executor_artifact": future_contract.get("executor_artifact") or "workspace/paused-session-automatic-loop-execution.json",
                "preflight_artifact": future_contract.get("preflight_artifact") or "workspace/paused-session-automatic-loop-executor-preflight.json",
                "approval_plan_artifact": "workspace/paused-session-automatic-loop-executor-approval-plan.json",
                "approval_record_artifact": "workspace/paused-session-automatic-loop-executor-approval-record.json",
                "transaction_journal_artifact": "workspace/paused-session-automatic-loop-executor-journal.json",
                "would_require_matching_preflight_id": True,
                "would_not_run_as_daemon": True,
                "would_not_manage_long_lived_session": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_executor_approval_plan_request_missing": ("request", "No automatic loop executor approval-plan request was provided.", "request_paused_session_automatic_loop_executor_approval_plan"),
            "automatic_loop_executor_preflight_required": ("preflight", "A ready automatic-loop executor preflight descriptor is required.", "review_paused_session_automatic_loop_executor_preflight"),
            "automatic_loop_executor_preflight_not_ready": ("preflight", "The automatic-loop executor preflight descriptor is not ready.", "resolve_automatic_loop_executor_preflight_blockers"),
            "automatic_loop_executor_preflight_id_mismatch": ("preflight", "The provided preflight id does not match the expected preflight id.", "refresh_matching_automatic_loop_executor_preflight"),
            "automatic_loop_executor_preflight_has_blockers": ("preflight", "The automatic-loop executor preflight still has blockers.", "resolve_automatic_loop_executor_preflight_blockers"),
            "preflight_ready_to_execute_claim_detected": ("safety", "The preflight claims execution is ready now; executor approval planning must stay non-executing.", "audit_executor_preflight_ready_to_execute_claim"),
            "future_executor_contract_required": ("contract", "The future executor contract metadata is required.", "regenerate_automatic_loop_executor_preflight"),
            "unexpected_existing_automatic_loop_executor": ("safety", "The preflight claims an executor is already implemented and needs separate audit.", "audit_existing_automatic_loop_executor_claim"),
            "preflight_iterations_required": ("preflight", "Approval planning needs bounded preflight iterations.", "provide_executor_preflight_with_bounded_iterations"),
            "review_per_iteration_required": ("review", "The approval plan must preserve review per iteration.", "restore_review_per_iteration_gate"),
            "checkpoint_after_each_iteration_required": ("checkpoint", "The approval plan must require checkpoint after each iteration.", "restore_checkpoint_after_each_iteration_gate"),
            "executor_preflight_side_effect_claim_detected": ("safety", "The executor preflight claims side effects and must be audited first.", "audit_executor_preflight_side_effect_claim"),
            "executor_approval_iteration_budget_required": ("budget", "A bounded approval iteration budget is required.", "set_automatic_loop_executor_approval_budget"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_approval_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_approval_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_executor_approval_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_executor_approval_plan_blockers"
        if status == "ready_for_review":
            return "review_future_bounded_automatic_loop_executor_approval_transaction"
        return "inspect_paused_session_automatic_loop_executor_approval_plan"


@dataclass(slots=True)
class PausedSessionMultiStepLoopExecutionSpec:
    """Review-gated one-iteration executor for a reviewed paused-session loop plan.

    This bridges the review-only loop plan to the existing one-iteration continuation
    executor. It deliberately executes at most one selected workflow step and then
    requires another checkpoint / loop-plan review before any further action.
    """

    loop_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_loop_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionMultiStepLoopExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_multi_step_loop_execution")
            or context.get("pausedSessionMultiStepLoopExecution")
            or context.get("paused-session-multi-step-loop-execution")
            or context.get("execute_paused_session_loop_iteration")
            or context.get("executePausedSessionLoopIteration")
            or context.get("execute_paused_session_continuation_loop")
            or context.get("executePausedSessionContinuationLoop")
        )
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
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
        if not requested and not loop_plan:
            return None
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_raw = context.get(
            "selected_step_index",
            context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", next_iteration.get("workflow_step_index")))),
        )
        selected_step_index: int | None
        try:
            selected_step_index = int(selected_raw) if selected_raw is not None else None
        except (TypeError, ValueError):
            selected_step_index = None
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_paused_session_loop_iteration",
            context.get("executePausedSessionLoopIteration", context.get("execute_paused_session_continuation_loop", context.get("execute_loop_iteration", context.get("executeLoopIteration", False)))),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or loop_plan.get("pause_session_id") or workflow.get("pause_session_id") or recovery.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or loop_plan.get("target_id") or workflow.get("target_id") or recovery.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or loop_plan.get("reviewer")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            loop_plan=loop_plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_loop_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index) if selected_step_index is not None else None,
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
class PausedSessionMultiStepLoopExecutionResult:
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


class PausedSessionMultiStepLoopExecutionManager:
    """Execute exactly one reviewed loop iteration through the existing continuation executor."""

    def execute(self, page: BrowserPage | None, spec: PausedSessionMultiStepLoopExecutionSpec | None) -> PausedSessionMultiStepLoopExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionMultiStepLoopExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_loop_iteration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionMultiStepLoopExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionMultiStepLoopExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        selected_index = self._selected_step_index(spec)
        inner_spec = PausedSessionMultiStepContinuationExecutionSpec(
            workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_iteration=True,
            review_approved=True,
            selected_step_index=selected_index,
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )
        result = PausedSessionMultiStepContinuationExecutionManager().execute(page, inner_spec)
        inner = result.execution if isinstance(result.execution, dict) else {}
        inner_policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else {}
        status = "executed" if result.status == "executed" else result.status
        blockers_after = [] if status == "executed" else [result.reason or "loop_iteration_execution_failed"]
        payload = self._payload(spec, status=status, blockers=blockers_after, inner_result=inner, inner_policy=inner_policy, error=result.error)
        return PausedSessionMultiStepLoopExecutionResult(
            status=status,
            execution=payload,
            side_effect_policy=self._side_effect_policy(inner_policy),
            reason=blockers_after[0] if blockers_after else None,
            error=result.error,
        )

    @classmethod
    def _blockers(cls, spec: PausedSessionMultiStepLoopExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["multi_step_loop_execution_request_missing"]
        blockers: list[str] = []
        loop_plan = spec.loop_plan
        workflow = spec.multi_step_workflow
        recovery = spec.live_callframe_recovery
        next_iteration = cls._next_iteration(spec)
        if not loop_plan:
            blockers.append("multi_step_loop_plan_required")
        elif loop_plan.get("status") != "ready_for_review" or not loop_plan.get("ready_for_review"):
            blockers.append("multi_step_loop_plan_not_ready")
        elif not next_iteration.get("available"):
            blockers.append("next_loop_iteration_required")
        elif not next_iteration.get("ready_for_review"):
            blockers.append("next_loop_iteration_not_reviewable")
        if loop_plan and cls._auto_flag_enabled(loop_plan):
            blockers.append("automatic_loop_must_remain_disabled")
        if not workflow:
            blockers.append("multi_step_workflow_required")
        elif workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        if cls._selected_step_index(spec) < 1:
            blockers.append("selected_step_index_required")
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
    def _auto_flag_enabled(loop_plan: dict[str, Any]) -> bool:
        readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
        policy = loop_plan.get("side_effect_policy") if isinstance(loop_plan.get("side_effect_policy"), dict) else {}
        return bool(
            readiness.get("automatic_multi_step_loop_supported")
            or readiness.get("automatic_queue_advance_supported")
            or readiness.get("automatic_live_callframe_recovery_supported")
            or readiness.get("automatic_wrapper_continuation_supported")
            or policy.get("automatic_multi_step_loop")
            or policy.get("automatic_queue_advance")
            or policy.get("automatic_live_callframe_recovery")
            or policy.get("automatic_wrapper_continuation")
        )

    @staticmethod
    def _next_iteration(spec: PausedSessionMultiStepLoopExecutionSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        value = spec.loop_plan.get("next_iteration")
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def _selected_step_index(cls, spec: PausedSessionMultiStepLoopExecutionSpec | None) -> int:
        if spec is None:
            return 0
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        next_iteration = cls._next_iteration(spec)
        try:
            return int(next_iteration.get("workflow_step_index") or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionMultiStepLoopExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        loop_plan = spec.loop_plan if spec else {}
        workflow = spec.multi_step_workflow if spec else {}
        next_iteration = cls._next_iteration(spec)
        policy = inner_policy or {}
        inner = inner_result or {}
        selected_index = cls._selected_step_index(spec)
        return {
            "schema_version": "reverse-deepagent.paused-session-multi-step-loop-execution.v1",
            "status": status,
            "loop_id": loop_plan.get("loop_id"),
            "workflow_id": workflow.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": spec.pause_session_id if spec else loop_plan.get("pause_session_id"),
            "target_id": spec.target_id if spec else loop_plan.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "selected_step_index": selected_index or None,
            "selected_method": next_iteration.get("method") or inner.get("selected_method"),
            "source_loop_plan_status": loop_plan.get("status"),
            "source_next_iteration": next_iteration,
            "execute_loop_iteration_requested": bool(spec and spec.execute_loop_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "executor_artifact": "workspace/paused-session-multi-step-continuation-execution.json",
            "executor_result": inner,
            "executor_status": inner.get("status"),
            "paused_event_captured": bool(inner.get("paused_event_captured")),
            "callframe_evaluated": bool(policy.get("callframe_evaluated")),
            "cdp_command_sent": bool(policy.get("cdp_command_sent")),
            "debugger_event_subscribed": bool(policy.get("debugger_event_subscribed")),
            "manual_checkpoint_required_after_iteration": True,
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_loop_plan": "workspace/paused-session-multi-step-loop-plan.json",
            "multi_step_loop_iteration_executed": status == "executed",
            "loop_advanced": False,
            "queue_advanced": False,
            "automatic_multi_step_loop": False,
            "automatic_wrapper_continuation": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, paused_captured=bool(inner.get("paused_event_captured"))),
            "side_effect_policy": cls._side_effect_policy(policy),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        cdp_sent = bool(inner_policy.get("cdp_command_sent"))
        return {
            "read_only": not cdp_sent,
            "review_only": False,
            "plan_only": False,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_sent,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": bool(inner_policy.get("debugger_event_subscribed")),
            "paused_event_captured": bool(inner_policy.get("paused_event_captured")),
            "browser_resumed": bool(inner_policy.get("browser_resumed")),
            "debugger_stepped": bool(inner_policy.get("debugger_stepped")),
            "callframe_evaluated": bool(inner_policy.get("callframe_evaluated")),
            "runtime_mutated": False,
            "cross_process_action_executed": bool(inner_policy.get("cross_process_action_executed") or cdp_sent),
            "multi_step_continuation_executed": bool(inner_policy.get("multi_step_continuation_executed") or cdp_sent),
            "multi_step_loop_iteration_executed": cdp_sent,
            "bounded_one_iteration_only": True,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "multi_step_loop_execution_request_missing": ("request", "No paused-session loop execution request was provided.", "request_paused_session_loop_execution"),
            "multi_step_loop_plan_required": ("loop_plan", "A ready paused-session loop plan is required.", "plan_paused_session_continuation_loop"),
            "multi_step_loop_plan_not_ready": ("loop_plan", "The supplied loop plan is not ready for review.", "review_or_replan_paused_session_loop"),
            "next_loop_iteration_required": ("loop_plan", "The supplied loop plan has no next iteration.", "review_loop_completion_or_replan_workflow"),
            "next_loop_iteration_not_reviewable": ("loop_plan", "The next loop iteration is not reviewable.", "review_loop_plan_readiness"),
            "automatic_loop_must_remain_disabled": ("safety", "Automatic loop / queue / callFrame recovery flags must remain disabled for this executor.", "disable_automatic_looping"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step continuation workflow is required.", "plan_multi_step_continuation_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The supplied continuation workflow is not ready for review.", "review_or_replan_multi_step_workflow"),
            "selected_step_index_required": ("workflow", "The loop execution could not resolve a workflow step index.", "select_reviewed_loop_iteration"),
            "live_callframe_recovery_required": ("debugger", "Fresh live callFrame recovery evidence is required before execution.", "recover_live_callframe_from_checkpoint"),
            "live_callframe_recovery_blocked": ("debugger", "The supplied live callFrame recovery evidence is blocked.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_retained_required": ("debugger", "The attached CDP session must still be retained.", "reattach_and_recover_live_callframe"),
            "attached_session_id_required": ("debugger", "A retained attached session id is required.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "A fresh live callFrame id is required.", "provide_live_callframe_id"),
            "review_approval_required": ("review", "Executing a loop iteration requires explicit review approval.", "approve_paused_session_loop_iteration"),
            "loop_iteration_execution_failed": ("runtime", "The delegated one-iteration executor failed.", "inspect_paused_session_loop_execution"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_execution"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_execution"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_loop_execution"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], paused_captured: bool) -> str:
        if blockers:
            return "inspect_paused_session_loop_execution_blockers"
        if status in {"ready_for_review", "review_required"}:
            return "approve_paused_session_loop_iteration"
        if status == "executed" and paused_captured:
            return "checkpoint_loop_iteration_captured_pause"
        if status == "executed":
            return "review_loop_iteration_execution_result"
        return "inspect_paused_session_loop_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopExecutionSpec:
    """Explicit-review-only bounded automatic-loop executor MVP.

    This is the first executable layer after the automatic-loop transaction journal
    and bounded executor gate descriptors. The MVP deliberately delegates at most
    one reviewed iteration to ``PausedSessionMultiStepLoopExecutionManager`` and
    then requires the existing checkpoint / loop-plan review chain before any
    further iteration. It is not a daemon, queue advancer, live callFrame recovery
    loop, long-lived session manager, MCP bridge, or mobile runtime chain.
    """

    bounded_executor_gate: dict[str, Any] = field(default_factory=dict)
    transaction_journal: dict[str, Any] = field(default_factory=dict)
    loop_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_automatic_loop: bool = False
    review_approved: bool = False
    selected_step_index: int | None = None
    max_iterations: int = 1
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_execution")
            or context.get("pausedSessionAutomaticLoopExecution")
            or context.get("paused-session-automatic-loop-execution")
            or context.get("execute_paused_session_automatic_loop")
            or context.get("executePausedSessionAutomaticLoop")
            or context.get("execute_bounded_paused_session_automatic_loop")
            or context.get("executeBoundedPausedSessionAutomaticLoop")
        )
        gate_container = _first_dict(
            context,
            "paused_session_automatic_loop_bounded_executor_gate",
            "pausedSessionAutomaticLoopBoundedExecutorGate",
            "paused-session-automatic-loop-bounded-executor-gate",
            "automatic_loop_bounded_executor_gate",
            "automaticLoopBoundedExecutorGate",
            "bounded_executor_gate",
            "boundedExecutorGate",
        )
        gate = dict(gate_container.get("gate")) if isinstance(gate_container.get("gate"), dict) else gate_container
        journal_container = _first_dict(
            context,
            "paused_session_automatic_loop_transaction_journal",
            "pausedSessionAutomaticLoopTransactionJournal",
            "paused-session-automatic-loop-transaction-journal",
            "paused_session_automatic_loop_executor_journal",
            "pausedSessionAutomaticLoopExecutorJournal",
            "automatic_loop_transaction_journal",
            "automaticLoopTransactionJournal",
            "transaction_journal",
            "transactionJournal",
        )
        journal = dict(journal_container.get("journal")) if isinstance(journal_container.get("journal"), dict) else journal_container
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
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
        if not requested and not any((gate, journal, loop_plan)):
            return None
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_raw = context.get(
            "selected_step_index",
            context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", next_iteration.get("workflow_step_index")))),
        )
        try:
            selected_step_index = int(selected_raw) if selected_raw is not None else None
        except (TypeError, ValueError):
            selected_step_index = None
        max_raw = context.get("max_iterations", context.get("maxIterations", context.get("max_automatic_iterations", context.get("maxAutomaticIterations", 1))))
        try:
            max_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_iterations = 1
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_paused_session_automatic_loop",
            context.get(
                "executePausedSessionAutomaticLoop",
                context.get("execute_bounded_paused_session_automatic_loop", context.get("execute_automatic_loop", context.get("executeAutomaticLoop", False))),
            ),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or loop_plan.get("pause_session_id") or workflow.get("pause_session_id") or recovery.get("pause_session_id") or gate.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or loop_plan.get("target_id") or workflow.get("target_id") or recovery.get("target_id") or gate.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or loop_plan.get("reviewer") or gate.get("reviewer")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            bounded_executor_gate=gate,
            transaction_journal=journal,
            loop_plan=loop_plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_automatic_loop=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index) if selected_step_index is not None else None,
            max_iterations=max(1, min(max_iterations, 1)),
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
class PausedSessionAutomaticLoopExecutionResult:
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


class PausedSessionAutomaticLoopExecutionManager:
    """Execute at most one reviewed automatic-loop iteration through the loop executor."""

    def execute(self, page: BrowserPage | None, spec: PausedSessionAutomaticLoopExecutionSpec | None) -> PausedSessionAutomaticLoopExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionAutomaticLoopExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_automatic_loop:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionAutomaticLoopExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionAutomaticLoopExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        loop_spec = PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=True,
            review_approved=True,
            selected_step_index=self._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )
        result = PausedSessionMultiStepLoopExecutionManager().execute(page, loop_spec)
        inner = result.execution if isinstance(result.execution, dict) else {}
        inner_policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else {}
        status = "executed" if result.status == "executed" else result.status
        blockers_after = [] if status == "executed" else [result.reason or "automatic_loop_iteration_execution_failed"]
        payload = self._payload(spec, status=status, blockers=blockers_after, inner_result=inner, inner_policy=inner_policy, error=result.error)
        return PausedSessionAutomaticLoopExecutionResult(
            status=status,
            execution=payload,
            side_effect_policy=self._side_effect_policy(inner_policy),
            reason=blockers_after[0] if blockers_after else None,
            error=result.error,
        )

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_execution_request_missing"]
        blockers: list[str] = []
        gate = spec.bounded_executor_gate
        journal = spec.transaction_journal
        if not gate:
            blockers.append("bounded_executor_gate_required")
        elif gate.get("status") != "ready_for_review" or gate.get("bounded_executor_gate_ready_for_review") is not True:
            blockers.append("bounded_executor_gate_not_ready")
        if gate and gate.get("automatic_loop_executed") is True:
            blockers.append("bounded_executor_gate_already_executed")
        if gate and gate.get("ready_to_execute_now") is True:
            blockers.append("bounded_executor_gate_ready_to_execute_claim_detected")
        if not journal:
            blockers.append("transaction_journal_required")
        elif journal.get("status") != "written" or journal.get("journal_written") is not True:
            blockers.append("transaction_journal_not_written")
        journal_summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
        if journal and (journal.get("automatic_loop_executed") is True or journal_summary.get("automatic_loop_executed") is True):
            blockers.append("transaction_journal_already_executed")
        if gate and journal and gate.get("transaction_id") and journal.get("transaction_id") and gate.get("transaction_id") != journal.get("transaction_id"):
            blockers.append("transaction_id_mismatch")
        if gate and journal and gate.get("journal_id") and journal.get("journal_id") and gate.get("journal_id") != journal.get("journal_id"):
            blockers.append("journal_id_mismatch")
        if spec.max_iterations != 1:
            blockers.append("automatic_loop_mvp_allows_one_iteration_only")
        blockers.extend(PausedSessionMultiStepLoopExecutionManager._blockers(cls._loop_spec(spec)))
        return list(dict.fromkeys(blockers))

    @classmethod
    def _loop_spec(cls, spec: PausedSessionAutomaticLoopExecutionSpec | None) -> PausedSessionMultiStepLoopExecutionSpec | None:
        if spec is None:
            return None
        return PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=False,
            review_approved=False,
            selected_step_index=cls._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )

    @classmethod
    def _selected_step_index(cls, spec: PausedSessionAutomaticLoopExecutionSpec | None) -> int:
        if spec is None:
            return 0
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        loop_spec = cls._loop_spec_without_selected(spec)
        return PausedSessionMultiStepLoopExecutionManager._selected_step_index(loop_spec)

    @staticmethod
    def _loop_spec_without_selected(spec: PausedSessionAutomaticLoopExecutionSpec) -> PausedSessionMultiStepLoopExecutionSpec:
        return PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
        )

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionAutomaticLoopExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        gate = spec.bounded_executor_gate if spec else {}
        journal = spec.transaction_journal if spec else {}
        inner = inner_result or {}
        policy = inner_policy or {}
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-execution-result.v1",
            "status": status,
            "transaction_id": journal.get("transaction_id") or gate.get("transaction_id"),
            "journal_id": journal.get("journal_id") or gate.get("journal_id"),
            "gate_status": gate.get("status"),
            "loop_id": gate.get("loop_id") or (spec.loop_plan.get("loop_id") if spec else None),
            "workflow_id": gate.get("workflow_id") or (spec.multi_step_workflow.get("workflow_id") if spec else None),
            "pause_session_id": spec.pause_session_id if spec else gate.get("pause_session_id"),
            "target_id": spec.target_id if spec else gate.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "execute_automatic_loop_requested": bool(spec and spec.execute_automatic_loop),
            "review_approved": bool(spec and spec.review_approved),
            "bounded_one_iteration_only": True,
            "max_iterations": spec.max_iterations if spec else 1,
            "selected_step_index": cls._selected_step_index(spec),
            "executed_iteration_count": 1 if status == "executed" else 0,
            "iteration_results": [inner] if inner else [],
            "delegated_executor_artifact": "workspace/paused-session-multi-step-loop-execution.json",
            "delegated_executor_status": inner.get("status"),
            "checkpoint_required": status == "executed",
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_loop_plan": "workspace/paused-session-multi-step-loop-plan.json",
            "automatic_loop_executed": status == "executed",
            "automatic_loop_one_iteration_executed": status == "executed",
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_session_managed": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, inner=inner),
            "side_effect_policy": cls._side_effect_policy(policy),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        policy = PausedSessionMultiStepLoopExecutionManager._side_effect_policy(inner_policy)
        policy.update(
            {
                "automatic_loop_executor": True,
                "automatic_loop_one_iteration_executed": bool(policy.get("multi_step_loop_iteration_executed")),
                "automatic_multi_step_loop": False,
                "bounded_one_iteration_only": True,
                "automatic_queue_advance": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            }
        )
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_execution_request_missing": ("request", "No automatic-loop execution request was provided.", "request_paused_session_automatic_loop_execution"),
            "bounded_executor_gate_required": ("gate", "A ready bounded executor gate descriptor is required.", "review_paused_session_automatic_loop_bounded_executor_gate"),
            "bounded_executor_gate_not_ready": ("gate", "The bounded executor gate is not ready for review.", "resolve_bounded_executor_gate_blockers"),
            "bounded_executor_gate_already_executed": ("gate", "The bounded executor gate claims the automatic loop already executed.", "audit_automatic_loop_execution_state"),
            "bounded_executor_gate_ready_to_execute_claim_detected": ("safety", "The gate unexpectedly claims ready_to_execute_now; execution must stay explicit.", "audit_bounded_executor_gate_ready_claim"),
            "transaction_journal_required": ("journal", "A written automatic-loop transaction journal is required.", "record_paused_session_automatic_loop_transaction_journal"),
            "transaction_journal_not_written": ("journal", "The automatic-loop transaction journal has not been written.", "write_reviewed_transaction_journal"),
            "transaction_journal_already_executed": ("journal", "The transaction journal claims the automatic loop already executed.", "audit_automatic_loop_transaction_journal"),
            "transaction_id_mismatch": ("transaction", "Gate and journal transaction ids do not match.", "refresh_matching_gate_and_journal"),
            "journal_id_mismatch": ("journal", "Gate and journal ids do not match.", "refresh_matching_gate_and_journal"),
            "automatic_loop_mvp_allows_one_iteration_only": ("budget", "The current automatic-loop executor MVP allows exactly one iteration.", "reduce_automatic_loop_iteration_budget_to_one"),
            "review_approval_required": ("review", "Executing automatic-loop iteration requires explicit review approval.", "approve_paused_session_automatic_loop_execution"),
            "automatic_loop_iteration_execution_failed": ("runtime", "The delegated one-iteration loop executor failed.", "inspect_automatic_loop_execution_result"),
        }
        fallback = PausedSessionMultiStepLoopExecutionManager._blocker_details(blockers)
        mapped: list[dict[str, Any]] = []
        fallback_by_code = {item.get("code"): item for item in fallback}
        for blocker in blockers:
            if blocker in catalog:
                category, explanation, next_action = catalog[blocker]
                mapped.append({"code": blocker, "category": category, "explanation": explanation, "next_action": next_action})
            else:
                mapped.append(fallback_by_code.get(blocker, {"code": blocker, "category": "unknown", "explanation": blocker, "next_action": "inspect_automatic_loop_execution_result"}))
        return mapped

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], inner: dict[str, Any]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_execution_blockers"
        if status in {"ready_for_review", "review_required"}:
            return "approve_paused_session_automatic_loop_execution"
        if status == "executed" and inner.get("paused_event_captured"):
            return "checkpoint_automatic_loop_iteration_captured_pause"
        if status == "executed":
            return "review_paused_session_automatic_loop_execution_result"
        return "inspect_paused_session_automatic_loop_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopFollowupCheckpointSpec:
    """Read-only descriptor for the checkpoint required after automatic-loop execution.

    This descriptor consumes the Step 250 automatic-loop execution result and optional
    continuation checkpoint / next loop plan evidence. It never creates checkpoints,
    recovers live callFrames, sends CDP commands, advances queues, or starts another
    loop iteration.
    """

    automatic_loop_execution_result: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopFollowupCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_followup_checkpoint")
            or context.get("pausedSessionAutomaticLoopFollowupCheckpoint")
            or context.get("paused-session-automatic-loop-followup-checkpoint")
            or context.get("paused_session_automatic_loop_execution_followup")
            or context.get("pausedSessionAutomaticLoopExecutionFollowup")
            or context.get("checkpoint_paused_session_automatic_loop_execution")
            or context.get("checkpointPausedSessionAutomaticLoopExecution")
        )
        execution_container = _first_dict(
            context,
            "paused_session_automatic_loop_execution_result",
            "pausedSessionAutomaticLoopExecutionResult",
            "paused-session-automatic-loop-execution-result",
            "automatic_loop_execution_result",
            "automaticLoopExecutionResult",
            "automatic_loop_execution",
            "automaticLoopExecution",
        )
        execution = dict(execution_container.get("execution")) if isinstance(execution_container.get("execution"), dict) else execution_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        if not requested and not execution:
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or execution.get("reviewer") or loop_plan.get("reviewer")
        return cls(
            automatic_loop_execution_result=execution,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopFollowupCheckpointResult:
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


class PausedSessionAutomaticLoopFollowupCheckpointManager:
    """Review-only descriptor after a bounded automatic-loop execution result."""

    def review(self, spec: PausedSessionAutomaticLoopFollowupCheckpointSpec | None) -> PausedSessionAutomaticLoopFollowupCheckpointResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopFollowupCheckpointResult(status=status, checkpoint=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopFollowupCheckpointSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_followup_checkpoint_request_missing"]
        blockers: list[str] = []
        execution = spec.automatic_loop_execution_result
        checkpoint = spec.continuation_checkpoint
        if not execution:
            blockers.append("automatic_loop_execution_result_required")
            return blockers
        execution_status = str(execution.get("status") or "")
        policy = execution.get("side_effect_policy") if isinstance(execution.get("side_effect_policy"), dict) else {}
        if execution_status in {"blocked", "failed", "failure", "error", "timed_out", "unsupported"}:
            blockers.append("automatic_loop_execution_result_blocked")
        elif execution_status != "executed" or execution.get("automatic_loop_executed") is not True:
            blockers.append("automatic_loop_execution_not_executed")
        if execution.get("checkpoint_required") is True:
            if not checkpoint:
                blockers.append("automatic_loop_followup_checkpoint_required")
            elif not cls._checkpoint_ready(checkpoint):
                blockers.append("automatic_loop_followup_checkpoint_not_ready")
        if execution.get("loop_advanced") is True or policy.get("loop_advanced") is True:
            blockers.append("loop_advance_claim_detected")
        if execution.get("queue_advanced") is True or policy.get("queue_advanced") is True:
            blockers.append("queue_advance_claim_detected")
        if execution.get("long_lived_session_managed") is True or policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("long_lived_session_claim_detected")
        if policy.get("calls_mcp") is True:
            blockers.append("mcp_call_claim_detected")
        if policy.get("mobile_runtime_used") is True:
            blockers.append("mobile_runtime_claim_detected")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _checkpoint_ready(checkpoint: dict[str, Any]) -> bool:
        return bool(
            checkpoint.get("continuation_ready_for_next_action")
            or checkpoint.get("live_callframe_recovery_ready")
            or checkpoint.get("live_callframe_recovered")
            or str(checkpoint.get("status") or "") in {"ready_for_next_action_review", "ready_for_live_callframe_recovery", "ready_for_review"}
        )

    @staticmethod
    def _loop_plan_ready(loop_plan: dict[str, Any]) -> bool:
        return bool(loop_plan.get("ready_for_review") or loop_plan.get("status") == "ready_for_review")

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopFollowupCheckpointSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        execution = spec.automatic_loop_execution_result if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        loop_plan = spec.next_loop_plan if spec else {}
        checkpoint_ready = cls._checkpoint_ready(checkpoint)
        loop_plan_ready = cls._loop_plan_ready(loop_plan)
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-followup-checkpoint.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "transaction_id": execution.get("transaction_id"),
            "journal_id": execution.get("journal_id"),
            "loop_id": execution.get("loop_id") or loop_plan.get("loop_id"),
            "workflow_id": execution.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": execution.get("pause_session_id") or checkpoint.get("pause_session_id") or loop_plan.get("pause_session_id"),
            "target_id": execution.get("target_id") or checkpoint.get("target_id") or loop_plan.get("target_id"),
            "source_statuses": {
                "automatic_loop_execution_result": execution.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "next_loop_plan": loop_plan.get("status"),
            },
            "execution_summary": {
                "automatic_loop_executed": bool(execution.get("automatic_loop_executed")),
                "automatic_loop_one_iteration_executed": bool(execution.get("automatic_loop_one_iteration_executed")),
                "executed_iteration_count": execution.get("executed_iteration_count", 0),
                "checkpoint_required": bool(execution.get("checkpoint_required")),
                "loop_advanced": bool(execution.get("loop_advanced")),
                "queue_advanced": bool(execution.get("queue_advanced")),
                "long_lived_session_managed": bool(execution.get("long_lived_session_managed")),
            },
            "checkpoint_review": {
                "checkpoint_present": bool(checkpoint),
                "checkpoint_ready": checkpoint_ready,
                "checkpoint_status": checkpoint.get("status"),
                "callframe_count": checkpoint.get("callframe_count", 0),
                "continuation_ready_for_next_action": bool(checkpoint.get("continuation_ready_for_next_action")),
                "continuation_ready_for_next_capture_plan": bool(checkpoint.get("continuation_ready_for_next_capture_plan")),
                "live_callframe_recovery_ready": bool(checkpoint.get("live_callframe_recovery_ready")),
                "manual_checkpoint_required": bool(checkpoint.get("manual_checkpoint_required")),
            },
            "next_loop_review": {
                "next_loop_plan_present": bool(loop_plan),
                "next_loop_plan_ready": loop_plan_ready,
                "next_iteration_reviewable": bool(cls._dict_value(loop_plan, "readiness").get("next_loop_iteration_reviewable")) if loop_plan else False,
                "next_iteration_available": bool(cls._dict_value(loop_plan, "next_iteration").get("available")) if loop_plan else False,
                "requires_review_approval": True,
                "requires_fresh_live_callframe": True,
                "would_execute_next_iteration": False,
            },
            "required_followups": cls._required_followups(checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers=blockers, checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _required_followups(*, checkpoint_ready: bool, loop_plan_ready: bool) -> list[dict[str, Any]]:
        if not checkpoint_ready:
            return [{"order": 1, "action": "checkpoint_paused_session_automatic_loop_execution", "artifact": "workspace/paused-session-cross-process-continuation-checkpoint.json", "automatic": False}]
        if not loop_plan_ready:
            return [{"order": 1, "action": "plan_next_paused_session_loop_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False}]
        return [{"order": 1, "action": "review_next_paused_session_loop_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False}]

    @staticmethod
    def _dict_value(container: dict[str, Any], key: str) -> dict[str, Any]:
        value = container.get(key) if isinstance(container, dict) else None
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "checkpoint_written": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "automatic_live_callframe_recovery": False,
            "automatic_multi_step_loop": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_followup_checkpoint_request_missing": ("request", "No automatic-loop follow-up checkpoint review request was provided.", "request_paused_session_automatic_loop_followup_checkpoint"),
            "automatic_loop_execution_result_required": ("execution", "The Step 250 automatic-loop execution result is required.", "provide_paused_session_automatic_loop_execution_result"),
            "automatic_loop_execution_result_blocked": ("execution", "The automatic-loop execution result is blocked, failed, unsupported, or timed out.", "inspect_paused_session_automatic_loop_execution_result"),
            "automatic_loop_execution_not_executed": ("execution", "The automatic-loop execution result has not executed a reviewed iteration yet.", "approve_paused_session_automatic_loop_execution"),
            "automatic_loop_followup_checkpoint_required": ("checkpoint", "Executed automatic-loop iterations require a continuation checkpoint before next loop review.", "checkpoint_paused_session_automatic_loop_execution"),
            "automatic_loop_followup_checkpoint_not_ready": ("checkpoint", "The supplied continuation checkpoint is not ready for next action review.", "recover_or_refresh_continuation_checkpoint"),
            "loop_advance_claim_detected": ("safety", "The execution result claims loop advancement, which is outside the MVP boundary.", "audit_automatic_loop_execution_side_effects"),
            "queue_advance_claim_detected": ("safety", "The execution result claims queue advancement, which is outside the MVP boundary.", "audit_automatic_loop_execution_side_effects"),
            "long_lived_session_claim_detected": ("safety", "The execution result claims long-lived session management, which is outside the MVP boundary.", "audit_automatic_loop_execution_side_effects"),
            "mcp_call_claim_detected": ("safety", "The execution result claims MCP calls, which are disallowed for native automatic-loop follow-up.", "audit_automatic_loop_execution_side_effects"),
            "mobile_runtime_claim_detected": ("safety", "The execution result claims mobile runtime use, which is deferred.", "audit_automatic_loop_execution_side_effects"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_followup_checkpoint"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_followup_checkpoint"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_followup_checkpoint"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, blockers: list[str], checkpoint_ready: bool, loop_plan_ready: bool) -> str:
        if "automatic_loop_followup_checkpoint_required" in blockers:
            return "checkpoint_paused_session_automatic_loop_execution"
        if "automatic_loop_followup_checkpoint_not_ready" in blockers:
            return "recover_or_refresh_continuation_checkpoint"
        if blockers:
            return "inspect_paused_session_automatic_loop_followup_checkpoint_blockers"
        if checkpoint_ready and not loop_plan_ready:
            return "plan_next_paused_session_loop_iteration_after_checkpoint"
        if checkpoint_ready and loop_plan_ready:
            return "review_next_paused_session_automatic_loop_iteration"
        return "inspect_paused_session_automatic_loop_followup_checkpoint"


@dataclass(slots=True)
class PausedSessionAutomaticLoopNextIterationPlanSpec:
    """Read-only plan descriptor before the next reviewed automatic-loop iteration.

    This descriptor consumes the follow-up checkpoint review produced after a bounded
    automatic-loop iteration plus the latest continuation checkpoint and next loop
    plan. It does not recover live callFrames, send CDP commands, execute another
    iteration, advance queues, or manage long-lived sessions.
    """

    followup_checkpoint: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopNextIterationPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_next_iteration_plan")
            or context.get("pausedSessionAutomaticLoopNextIterationPlan")
            or context.get("paused-session-automatic-loop-next-iteration-plan")
            or context.get("plan_next_paused_session_automatic_loop_iteration")
            or context.get("planNextPausedSessionAutomaticLoopIteration")
            or context.get("review_next_paused_session_automatic_loop_iteration")
            or context.get("reviewNextPausedSessionAutomaticLoopIteration")
        )
        followup_container = _first_dict(
            context,
            "paused_session_automatic_loop_next_iteration_followup_checkpoint",
            "pausedSessionAutomaticLoopNextIterationFollowupCheckpoint",
            "paused-session-automatic-loop-next-iteration-followup-checkpoint",
            "paused_session_automatic_loop_next_iteration_execution_followup",
            "pausedSessionAutomaticLoopNextIterationExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_next_iteration_execution",
            "checkpointPausedSessionAutomaticLoopNextIterationExecution",
            "paused_session_automatic_loop_followup_checkpoint",
            "pausedSessionAutomaticLoopFollowupCheckpoint",
            "paused-session-automatic-loop-followup-checkpoint",
            "automatic_loop_followup_checkpoint",
            "automaticLoopFollowupCheckpoint",
            "automatic_loop_checkpoint_review",
            "automaticLoopCheckpointReview",
        )
        followup = dict(followup_container.get("checkpoint")) if isinstance(followup_container.get("checkpoint"), dict) else followup_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        if not requested and not followup:
            return None
        reviewer = (
            context.get("reviewer")
            or context.get("reviewer_id")
            or context.get("reviewerId")
            or followup.get("reviewer")
            or loop_plan.get("reviewer")
        )
        return cls(
            followup_checkpoint=followup,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            live_callframe_recovery=recovery,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopNextIterationPlanResult:
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


class PausedSessionAutomaticLoopNextIterationPlanManager:
    """Review-only handoff descriptor for the next automatic-loop iteration."""

    def plan(self, spec: PausedSessionAutomaticLoopNextIterationPlanSpec | None) -> PausedSessionAutomaticLoopNextIterationPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopNextIterationPlanResult(status=status, plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopNextIterationPlanSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_next_iteration_plan_request_missing"]
        blockers: list[str] = []
        followup = spec.followup_checkpoint
        checkpoint = spec.continuation_checkpoint
        loop_plan = spec.next_loop_plan
        recovery = spec.live_callframe_recovery
        if not followup:
            blockers.append("automatic_loop_followup_checkpoint_required")
            return blockers
        followup_status = str(followup.get("status") or "")
        followup_policy = followup.get("side_effect_policy") if isinstance(followup.get("side_effect_policy"), dict) else {}
        if followup_status in {"blocked", "failed", "failure", "error", "timed_out", "unsupported"}:
            blockers.append("automatic_loop_followup_checkpoint_blocked")
        elif followup_status != "ready_for_review" or followup.get("ready_for_review") is not True:
            blockers.append("automatic_loop_followup_checkpoint_not_ready")
        if not cls._followup_checkpoint_ready(followup):
            blockers.append("automatic_loop_followup_checkpoint_not_ready_for_next_iteration")
        if not checkpoint:
            blockers.append("continuation_checkpoint_required")
        elif not PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint):
            blockers.append("continuation_checkpoint_not_ready")
        if not loop_plan:
            blockers.append("next_loop_plan_required")
        elif not PausedSessionAutomaticLoopFollowupCheckpointManager._loop_plan_ready(loop_plan):
            blockers.append("next_loop_plan_not_ready")
        elif not cls._next_iteration_reviewable(loop_plan):
            blockers.append("next_loop_iteration_not_reviewable")
        if cls._requires_live_callframe(loop_plan) and not cls._live_callframe_recovered(recovery):
            blockers.append("fresh_live_callframe_recovery_required")
        if followup_policy.get("checkpoint_written") is True:
            blockers.append("followup_checkpoint_wrote_checkpoint")
        if followup_policy.get("cdp_command_sent") is True or followup_policy.get("cdp_target_attached") is True:
            blockers.append("followup_checkpoint_sent_cdp")
        if followup_policy.get("debugger_event_subscribed") is True or followup_policy.get("paused_event_captured") is True:
            blockers.append("followup_checkpoint_captured_event")
        if followup_policy.get("loop_advanced") is True or followup_policy.get("queue_advanced") is True:
            blockers.append("followup_checkpoint_advanced_loop_or_queue")
        if followup_policy.get("calls_mcp") is True:
            blockers.append("mcp_call_claim_detected")
        if followup_policy.get("mobile_runtime_used") is True:
            blockers.append("mobile_runtime_claim_detected")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _followup_checkpoint_ready(followup: dict[str, Any]) -> bool:
        review = followup.get("checkpoint_review") if isinstance(followup.get("checkpoint_review"), dict) else {}
        next_loop = followup.get("next_loop_review") if isinstance(followup.get("next_loop_review"), dict) else {}
        return bool(
            followup.get("ready_for_review")
            and review.get("checkpoint_ready")
            and next_loop.get("next_loop_plan_ready")
            and next_loop.get("next_iteration_reviewable")
        )

    @staticmethod
    def _next_iteration_reviewable(loop_plan: dict[str, Any]) -> bool:
        readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        return bool(readiness.get("next_loop_iteration_reviewable") or next_iteration.get("available"))

    @staticmethod
    def _requires_live_callframe(loop_plan: dict[str, Any]) -> bool:
        review_gates = loop_plan.get("review_gates") if isinstance(loop_plan.get("review_gates"), dict) else {}
        return bool(review_gates.get("requires_fresh_live_callframe") or True)

    @staticmethod
    def _live_callframe_recovered(recovery: dict[str, Any]) -> bool:
        return bool(
            recovery.get("live_callframe_recovered")
            or recovery.get("live_callframe_id")
            or str(recovery.get("status") or "") in {"ready_for_review", "recovered", "success"}
        )

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopNextIterationPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        followup = spec.followup_checkpoint if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        loop_plan = spec.next_loop_plan if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_step = next_iteration.get("selected_step") if isinstance(next_iteration.get("selected_step"), dict) else {}
        recovery_ready = cls._live_callframe_recovered(recovery)
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-next-iteration-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "transaction_id": followup.get("transaction_id"),
            "journal_id": followup.get("journal_id"),
            "loop_id": followup.get("loop_id") or loop_plan.get("loop_id"),
            "workflow_id": followup.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": followup.get("pause_session_id") or checkpoint.get("pause_session_id") or loop_plan.get("pause_session_id"),
            "target_id": followup.get("target_id") or checkpoint.get("target_id") or loop_plan.get("target_id"),
            "source_statuses": {
                "automatic_loop_followup_checkpoint": followup.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "next_loop_plan": loop_plan.get("status"),
                "live_callframe_recovery": recovery.get("status"),
            },
            "checkpoint_review": {
                "followup_checkpoint_ready": cls._followup_checkpoint_ready(followup),
                "continuation_checkpoint_ready": PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint),
                "checkpoint_status": checkpoint.get("status"),
                "callframe_count": checkpoint.get("callframe_count", 0),
            },
            "next_iteration": {
                "next_loop_plan_ready": PausedSessionAutomaticLoopFollowupCheckpointManager._loop_plan_ready(loop_plan),
                "next_iteration_reviewable": cls._next_iteration_reviewable(loop_plan),
                "selected_step_index": next_iteration.get("selected_step_index", loop_plan.get("selected_step_index")),
                "selected_method": selected_step.get("method") or next_iteration.get("selected_method"),
                "selected_action": selected_step.get("action") or next_iteration.get("selected_action"),
                "requires_review_approval": True,
                "requires_fresh_live_callframe": True,
                "fresh_live_callframe_recovered": recovery_ready,
                "would_execute_next_iteration": False,
            },
            "execution_review_gates": {
                "requires_explicit_execution_approval": True,
                "requires_ready_followup_checkpoint": True,
                "requires_ready_continuation_checkpoint": True,
                "requires_ready_next_loop_plan": True,
                "requires_fresh_live_callframe": True,
                "bounded_one_iteration_only": True,
                "automatic_multi_iteration_loop": False,
                "automatic_queue_advance": False,
                "long_lived_cross_process_session": False,
            },
            "expected_executor": {
                "name": "execute_paused_session_automatic_loop_next_iteration",
                "implemented": False,
                "future_artifact": "workspace/paused-session-automatic-loop-next-iteration-execution.json",
                "delegates_to": "workspace/paused-session-multi-step-loop-execution.json",
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        policy = PausedSessionAutomaticLoopFollowupCheckpointManager._side_effect_policy()
        policy.update(
            {
                "next_iteration_plan_only": True,
                "would_execute_next_iteration": False,
                "automatic_loop_executed": False,
                "automatic_loop_next_iteration_executed": False,
            }
        )
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_next_iteration_plan_request_missing": ("request", "No automatic-loop next-iteration plan request was provided.", "request_paused_session_automatic_loop_next_iteration_plan"),
            "automatic_loop_followup_checkpoint_required": ("checkpoint", "A ready follow-up checkpoint descriptor is required before planning the next automatic-loop iteration.", "review_paused_session_automatic_loop_followup_checkpoint"),
            "automatic_loop_followup_checkpoint_blocked": ("checkpoint", "The follow-up checkpoint descriptor is blocked or failed.", "inspect_paused_session_automatic_loop_followup_checkpoint_blockers"),
            "automatic_loop_followup_checkpoint_not_ready": ("checkpoint", "The follow-up checkpoint descriptor is not ready for review.", "refresh_paused_session_automatic_loop_followup_checkpoint"),
            "automatic_loop_followup_checkpoint_not_ready_for_next_iteration": ("checkpoint", "The follow-up descriptor has not proven checkpoint and next-loop readiness.", "provide_ready_checkpoint_and_loop_plan"),
            "continuation_checkpoint_required": ("checkpoint", "A continuation checkpoint is required before the next iteration review.", "checkpoint_paused_session_automatic_loop_execution"),
            "continuation_checkpoint_not_ready": ("checkpoint", "The continuation checkpoint is not ready for next action review.", "recover_or_refresh_continuation_checkpoint"),
            "next_loop_plan_required": ("loop_plan", "A next loop plan is required before the next automatic-loop iteration review.", "plan_next_paused_session_loop_iteration_after_checkpoint"),
            "next_loop_plan_not_ready": ("loop_plan", "The next loop plan is not ready for review.", "refresh_next_paused_session_loop_plan"),
            "next_loop_iteration_not_reviewable": ("loop_plan", "The next loop plan does not expose a reviewable next iteration.", "refresh_loop_plan_with_reviewable_next_iteration"),
            "fresh_live_callframe_recovery_required": ("callframe", "A fresh live callFrame recovery proof is required before execution review.", "recover_live_callframe_from_captured_pause"),
            "followup_checkpoint_wrote_checkpoint": ("safety", "The follow-up descriptor unexpectedly claims checkpoint writes.", "audit_followup_checkpoint_side_effects"),
            "followup_checkpoint_sent_cdp": ("safety", "The follow-up descriptor unexpectedly claims CDP commands.", "audit_followup_checkpoint_side_effects"),
            "followup_checkpoint_captured_event": ("safety", "The follow-up descriptor unexpectedly claims paused-event capture.", "audit_followup_checkpoint_side_effects"),
            "followup_checkpoint_advanced_loop_or_queue": ("safety", "The follow-up descriptor unexpectedly claims loop or queue advancement.", "audit_followup_checkpoint_side_effects"),
            "mcp_call_claim_detected": ("safety", "The follow-up descriptor claims MCP calls, which are disallowed.", "audit_followup_checkpoint_side_effects"),
            "mobile_runtime_claim_detected": ("safety", "The follow-up descriptor claims mobile runtime use, which is deferred.", "audit_followup_checkpoint_side_effects"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_plan"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_plan"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_plan"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if "automatic_loop_followup_checkpoint_required" in blockers or "automatic_loop_followup_checkpoint_not_ready" in blockers:
            return "review_paused_session_automatic_loop_followup_checkpoint"
        if "continuation_checkpoint_required" in blockers or "continuation_checkpoint_not_ready" in blockers:
            return "checkpoint_paused_session_automatic_loop_execution"
        if "next_loop_plan_required" in blockers or "next_loop_plan_not_ready" in blockers or "next_loop_iteration_not_reviewable" in blockers:
            return "plan_next_paused_session_loop_iteration_after_checkpoint"
        if "fresh_live_callframe_recovery_required" in blockers:
            return "recover_live_callframe_from_captured_pause"
        if blockers:
            return "inspect_paused_session_automatic_loop_next_iteration_plan_blockers"
        return "review_paused_session_automatic_loop_next_iteration_execution"

@dataclass(slots=True)
class PausedSessionAutomaticLoopFollowingIterationPlanSpec:
    """Read-only plan descriptor after a next-iteration follow-up checkpoint.

    This descriptor consumes the Step 254 follow-up checkpoint plus continuation
    checkpoint, loop plan, and optional fresh live callFrame recovery evidence. It
    only prepares another explicit execution review input and never executes a loop.
    """

    followup_checkpoint: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopFollowingIterationPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_following_iteration_plan")
            or context.get("pausedSessionAutomaticLoopFollowingIterationPlan")
            or context.get("paused-session-automatic-loop-following-iteration-plan")
            or context.get("plan_following_paused_session_automatic_loop_iteration")
            or context.get("planFollowingPausedSessionAutomaticLoopIteration")
            or context.get("review_following_paused_session_automatic_loop_iteration")
            or context.get("reviewFollowingPausedSessionAutomaticLoopIteration")
        )
        followup_container = _first_dict(
            context,
            "paused_session_automatic_loop_next_iteration_followup_checkpoint",
            "pausedSessionAutomaticLoopNextIterationFollowupCheckpoint",
            "paused-session-automatic-loop-next-iteration-followup-checkpoint",
            "paused_session_automatic_loop_next_iteration_execution_followup",
            "pausedSessionAutomaticLoopNextIterationExecutionFollowup",
            "automatic_loop_next_iteration_followup_checkpoint",
            "automaticLoopNextIterationFollowupCheckpoint",
        )
        followup = dict(followup_container.get("checkpoint")) if isinstance(followup_container.get("checkpoint"), dict) else followup_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        if not requested and not followup:
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or followup.get("reviewer") or loop_plan.get("reviewer")
        return cls(
            followup_checkpoint=followup,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            live_callframe_recovery=recovery,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopFollowingIterationPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "plan": self.plan, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopFollowingIterationPlanManager:
    """Review-only plan descriptor for the iteration after Step 254 handoff."""

    def plan(self, spec: PausedSessionAutomaticLoopFollowingIterationPlanSpec | None) -> PausedSessionAutomaticLoopFollowingIterationPlanResult:
        if spec is None:
            payload = {
                "schema_version": "reverse-deepagent.paused-session-automatic-loop-following-iteration-plan.v1",
                "status": "blocked",
                "ready_for_review": False,
                "blockers": ["automatic_loop_following_iteration_plan_request_missing"],
                "blocker_details": [{"code": "automatic_loop_following_iteration_plan_request_missing", "category": "request", "explanation": "No automatic-loop following-iteration plan request was provided.", "next_action": "request_paused_session_automatic_loop_following_iteration_plan"}],
                "next_action": "request_paused_session_automatic_loop_following_iteration_plan",
                "side_effect_policy": self._side_effect_policy(PausedSessionAutomaticLoopNextIterationPlanManager._side_effect_policy()),
            }
            return PausedSessionAutomaticLoopFollowingIterationPlanResult(status="blocked", plan=payload, side_effect_policy=payload["side_effect_policy"], reason="automatic_loop_following_iteration_plan_request_missing")
        base_spec = PausedSessionAutomaticLoopNextIterationPlanSpec(
            followup_checkpoint=spec.followup_checkpoint,
            continuation_checkpoint=spec.continuation_checkpoint,
            next_loop_plan=spec.next_loop_plan,
            live_callframe_recovery=spec.live_callframe_recovery,
            reviewer=spec.reviewer,
        )
        base = PausedSessionAutomaticLoopNextIterationPlanManager().plan(base_spec)
        payload = dict(base.plan)
        policy = self._side_effect_policy(base.side_effect_policy)
        payload.update(
            {
                "schema_version": "reverse-deepagent.paused-session-automatic-loop-following-iteration-plan.v1",
                "following_iteration_plan": True,
                "source_followup_artifact": "workspace/paused-session-automatic-loop-next-iteration-followup-checkpoint.json",
                "target_execution_artifact": "workspace/paused-session-automatic-loop-next-iteration-execution.json",
                "side_effect_policy": policy,
            }
        )
        statuses = payload.get("source_statuses") if isinstance(payload.get("source_statuses"), dict) else {}
        statuses["automatic_loop_next_iteration_followup_checkpoint"] = statuses.pop("automatic_loop_followup_checkpoint", spec.followup_checkpoint.get("status"))
        payload["source_statuses"] = statuses
        expected = payload.get("expected_executor") if isinstance(payload.get("expected_executor"), dict) else {}
        expected.update({"name": "execute_paused_session_automatic_loop_next_iteration", "implemented": True, "reused_for_following_iterations": True})
        payload["expected_executor"] = expected
        if base.status == "ready_for_review":
            payload["next_action"] = "review_paused_session_automatic_loop_next_iteration_execution"
        return PausedSessionAutomaticLoopFollowingIterationPlanResult(status=base.status, plan=payload, side_effect_policy=policy, reason=base.reason)

    @staticmethod
    def _side_effect_policy(base_policy: dict[str, Any]) -> dict[str, Any]:
        policy = dict(base_policy)
        policy.update(
            {
                "following_iteration_plan_only": True,
                "next_iteration_plan_only": True,
                "would_execute_next_iteration": False,
                "automatic_loop_executed": False,
                "automatic_loop_next_iteration_executed": False,
                "automatic_multi_iteration_loop": False,
                "automatic_queue_advance": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            }
        )
        return policy


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationPolicySpec:
    """Read-only bounded multi-iteration policy descriptor after following-iteration planning.

    This descriptor is a policy / budget review layer only. It does not execute
    iterations, recover callFrames, write checkpoints, advance queues, or manage
    long-lived cross-process sessions.
    """

    following_iteration_plan: dict[str, Any] = field(default_factory=dict)
    max_policy_iterations: int = 2
    require_review_per_iteration: bool = True
    require_checkpoint_after_each_iteration: bool = True
    require_fresh_live_callframe_per_iteration: bool = True
    stop_after_each_checkpoint: bool = True
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationPolicySpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_policy")
            or context.get("pausedSessionAutomaticLoopMultiIterationPolicy")
            or context.get("paused-session-automatic-loop-multi-iteration-policy")
            or context.get("plan_paused_session_automatic_loop_multi_iteration_policy")
            or context.get("planPausedSessionAutomaticLoopMultiIterationPolicy")
            or context.get("review_paused_session_automatic_loop_multi_iteration_policy")
            or context.get("reviewPausedSessionAutomaticLoopMultiIterationPolicy")
            or context.get("automatic_loop_multi_iteration_policy")
            or context.get("automaticLoopMultiIterationPolicy")
        )
        plan_container = _first_dict(
            context,
            "paused_session_automatic_loop_following_iteration_plan",
            "pausedSessionAutomaticLoopFollowingIterationPlan",
            "paused-session-automatic-loop-following-iteration-plan",
            "plan_following_paused_session_automatic_loop_iteration",
            "planFollowingPausedSessionAutomaticLoopIteration",
            "review_following_paused_session_automatic_loop_iteration",
            "reviewFollowingPausedSessionAutomaticLoopIteration",
            "automatic_loop_following_iteration_plan",
            "automaticLoopFollowingIterationPlan",
        )
        following_plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        if not requested and not following_plan:
            return None
        budget_raw = context.get("max_policy_iterations", context.get("maxPolicyIterations", context.get("max_multi_iteration_budget", context.get("maxMultiIterationBudget", 2))))
        try:
            max_policy_iterations = int(budget_raw)
        except (TypeError, ValueError):
            max_policy_iterations = 2
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or following_plan.get("reviewer")
        return cls(
            following_iteration_plan=following_plan,
            max_policy_iterations=max(0, min(max_policy_iterations, 10)),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            require_checkpoint_after_each_iteration=bool(context.get("require_checkpoint_after_each_iteration", context.get("requireCheckpointAfterEachIteration", True))),
            require_fresh_live_callframe_per_iteration=bool(context.get("require_fresh_live_callframe_per_iteration", context.get("requireFreshLiveCallframePerIteration", True))),
            stop_after_each_checkpoint=bool(context.get("stop_after_each_checkpoint", context.get("stopAfterEachCheckpoint", True))),
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationPolicyResult:
    status: str
    policy: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "policy": self.policy, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationPolicyManager:
    """Read-only policy / budget descriptor for future bounded automatic-loop automation."""

    def review(self, spec: PausedSessionAutomaticLoopMultiIterationPolicySpec | None) -> PausedSessionAutomaticLoopMultiIterationPolicyResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopMultiIterationPolicyResult(status=status, policy=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationPolicySpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_policy_request_missing"]
        plan = spec.following_iteration_plan
        blockers: list[str] = []
        if not plan:
            blockers.append("following_iteration_plan_required")
        elif plan.get("status") != "ready_for_review" or plan.get("ready_for_review") is not True:
            blockers.append("following_iteration_plan_not_ready")
        plan_blockers = plan.get("blockers") if isinstance(plan.get("blockers"), list) else []
        if plan_blockers:
            blockers.append("following_iteration_plan_has_blockers")
        checkpoint = plan.get("checkpoint_review") if isinstance(plan.get("checkpoint_review"), dict) else {}
        next_iteration = plan.get("next_iteration") if isinstance(plan.get("next_iteration"), dict) else {}
        if checkpoint and checkpoint.get("followup_checkpoint_ready") is not True:
            blockers.append("following_iteration_followup_checkpoint_not_ready")
        if checkpoint and checkpoint.get("continuation_checkpoint_ready") is not True:
            blockers.append("following_iteration_continuation_checkpoint_not_ready")
        if next_iteration and next_iteration.get("next_iteration_reviewable") is not True:
            blockers.append("following_iteration_not_reviewable")
        if next_iteration and next_iteration.get("fresh_live_callframe_recovered") is not True:
            blockers.append("fresh_live_callframe_required_for_policy")
        if spec.max_policy_iterations < 2:
            blockers.append("multi_iteration_policy_budget_requires_at_least_two")
        if spec.require_review_per_iteration is not True:
            blockers.append("review_per_iteration_required")
        if spec.require_checkpoint_after_each_iteration is not True:
            blockers.append("checkpoint_after_each_iteration_required")
        if spec.require_fresh_live_callframe_per_iteration is not True:
            blockers.append("fresh_live_callframe_per_iteration_required")
        if spec.stop_after_each_checkpoint is not True:
            blockers.append("stop_after_each_checkpoint_required")
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        if policy.get("cdp_command_sent") is True or policy.get("would_execute_next_iteration") is True:
            blockers.append("following_iteration_plan_has_execution_side_effects")
        if policy.get("loop_advanced") is True or policy.get("queue_advanced") is True:
            blockers.append("following_iteration_plan_advanced_loop_or_queue")
        if policy.get("calls_mcp") is True:
            blockers.append("following_iteration_plan_called_mcp")
        if policy.get("mobile_runtime_used") is True:
            blockers.append("following_iteration_plan_used_mobile_runtime")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopMultiIterationPolicySpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        plan = spec.following_iteration_plan if spec else {}
        checkpoint = plan.get("checkpoint_review") if isinstance(plan.get("checkpoint_review"), dict) else {}
        next_iteration = plan.get("next_iteration") if isinstance(plan.get("next_iteration"), dict) else {}
        ready = status == "ready_for_review"
        budget = spec.max_policy_iterations if spec else 0
        policy_id = f"automatic-loop-policy:{plan.get('transaction_id') or plan.get('loop_id') or plan.get('workflow_id') or 'unbound'}"
        per_iteration_gates = [
            {
                "iteration_number": index + 1,
                "requires_explicit_review": True,
                "requires_ready_following_or_next_iteration_plan": True,
                "requires_fresh_live_callframe": True,
                "requires_retained_attached_session": True,
                "requires_checkpoint_after_iteration": True,
                "requires_stop_for_review_after_checkpoint": True,
                "would_execute_in_this_descriptor": False,
                "would_advance_queue_in_this_descriptor": False,
            }
            for index in range(max(0, budget))
        ]
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-policy.v1",
            "status": status,
            "ready_for_review": ready,
            "policy_id": policy_id,
            "transaction_id": plan.get("transaction_id"),
            "loop_id": plan.get("loop_id"),
            "workflow_id": plan.get("workflow_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_following_iteration_plan": {
                "schema_version": plan.get("schema_version"),
                "status": plan.get("status"),
                "ready_for_review": bool(plan.get("ready_for_review")),
                "next_action": plan.get("next_action"),
                "target_execution_artifact": plan.get("target_execution_artifact"),
                "followup_checkpoint_ready": bool(checkpoint.get("followup_checkpoint_ready")),
                "continuation_checkpoint_ready": bool(checkpoint.get("continuation_checkpoint_ready")),
                "next_loop_plan_ready": bool(next_iteration.get("next_loop_plan_ready")),
                "next_iteration_reviewable": bool(next_iteration.get("next_iteration_reviewable")),
                "fresh_live_callframe_recovered": bool(next_iteration.get("fresh_live_callframe_recovered")),
            },
            "budget_policy": {
                "max_policy_iterations": budget,
                "minimum_budget_for_multi_iteration_policy": 2,
                "bounded_multi_iteration_policy_ready": ready,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_review_per_iteration": spec.require_review_per_iteration if spec else True,
                "requires_checkpoint_after_each_iteration": spec.require_checkpoint_after_each_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": spec.require_fresh_live_callframe_per_iteration if spec else True,
                "stop_after_each_checkpoint": spec.stop_after_each_checkpoint if spec else True,
            },
            "per_iteration_gates": per_iteration_gates,
            "stop_conditions": {
                "stop_after_each_checkpoint": spec.stop_after_each_checkpoint if spec else True,
                "stop_on_missing_fresh_live_callframe": True,
                "stop_on_missing_review_approval": True,
                "stop_on_checkpoint_not_ready": True,
                "stop_on_any_cdp_error": True,
                "stop_on_loop_or_queue_advance_claim": True,
                "stop_on_mcp_or_mobile_runtime_signal": True,
            },
            "future_executor_contract": {
                "executor_name": "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": False,
                "expected_policy_artifact": "workspace/paused-session-automatic-loop-multi-iteration-policy.json",
                "would_require_matching_policy_id": True,
                "would_require_explicit_review_approval": True,
                "would_require_transaction_journal": True,
                "would_execute_bounded_iterations_only": True,
                "would_checkpoint_between_iterations": True,
                "would_not_run_as_daemon": True,
                "would_not_auto_recover_live_callframe": True,
                "would_not_advance_queue_without_review": True,
                "would_not_manage_long_lived_session": True,
                "would_not_call_mcp": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "policy_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_loop_executed": False,
            "automatic_multi_iteration_loop": False,
            "automatic_live_callframe_recovery": False,
            "automatic_queue_advance": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_policy_request_missing": ("request", "No automatic-loop multi-iteration policy request was provided.", "request_paused_session_automatic_loop_multi_iteration_policy"),
            "following_iteration_plan_required": ("plan", "A ready following-iteration plan is required.", "review_following_paused_session_automatic_loop_iteration"),
            "following_iteration_plan_not_ready": ("plan", "The following-iteration plan is not ready for review.", "resolve_following_iteration_plan_blockers"),
            "following_iteration_plan_has_blockers": ("plan", "The following-iteration plan still contains blockers.", "resolve_following_iteration_plan_blockers"),
            "following_iteration_followup_checkpoint_not_ready": ("checkpoint", "The next-iteration follow-up checkpoint is not ready.", "checkpoint_paused_session_automatic_loop_next_iteration_execution"),
            "following_iteration_continuation_checkpoint_not_ready": ("checkpoint", "The continuation checkpoint is not ready.", "refresh_continuation_checkpoint"),
            "following_iteration_not_reviewable": ("review", "The next iteration is not reviewable.", "replan_following_iteration"),
            "fresh_live_callframe_required_for_policy": ("callframe", "Fresh live callFrame evidence is required before policy review.", "recover_live_callframe_from_captured_pause"),
            "multi_iteration_policy_budget_requires_at_least_two": ("budget", "A multi-iteration policy requires a budget of at least two iterations.", "raise_multi_iteration_policy_budget_or_use_single_iteration_review"),
            "review_per_iteration_required": ("review", "Review must remain required for every iteration.", "restore_review_per_iteration_gate"),
            "checkpoint_after_each_iteration_required": ("checkpoint", "A checkpoint must be required after every iteration.", "restore_checkpoint_after_each_iteration_gate"),
            "fresh_live_callframe_per_iteration_required": ("callframe", "Fresh live callFrame evidence must be required for every iteration.", "restore_fresh_live_callframe_gate"),
            "stop_after_each_checkpoint_required": ("policy", "The policy must stop for review after each checkpoint.", "restore_stop_after_each_checkpoint_policy"),
            "following_iteration_plan_has_execution_side_effects": ("safety", "The following-iteration plan reports execution side effects.", "audit_following_iteration_side_effects"),
            "following_iteration_plan_advanced_loop_or_queue": ("safety", "The following-iteration plan reports loop or queue advancement.", "audit_following_iteration_loop_state"),
            "following_iteration_plan_called_mcp": ("safety", "The following-iteration plan reports MCP usage.", "remove_mcp_from_policy_inputs"),
            "following_iteration_plan_used_mobile_runtime": ("safety", "The following-iteration plan reports mobile runtime usage.", "remove_mobile_runtime_from_policy_inputs"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_policy"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_policy"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_policy"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_policy_blockers"
        if status == "ready_for_review":
            return "review_future_paused_session_automatic_loop_multi_iteration_executor_contract"
        return "inspect_paused_session_automatic_loop_multi_iteration_policy"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorPreflightSpec:
    """Read-only preflight descriptor for a future bounded multi-iteration executor.

    This consumes the bounded multi-iteration policy descriptor and normalizes the
    executor input gates for a future explicit-review-only executor. It never
    executes iterations, writes checkpoints, recovers callFrames, subscribes to
    debugger events, advances loop / queue state, manages long-lived sessions,
    calls MCP, or touches mobile runtime chains.
    """

    multi_iteration_policy: dict[str, Any] = field(default_factory=dict)
    expected_policy_id: str | None = None
    reviewer: str | None = None
    max_preflight_iterations: int = 2
    require_transaction_journal: bool = True
    require_review_per_iteration: bool = True
    require_checkpoint_after_each_iteration: bool = True
    require_fresh_live_callframe_per_iteration: bool = True
    require_stop_after_each_checkpoint: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationExecutorPreflightSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_executor_preflight")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecutorPreflight")
            or context.get("paused-session-automatic-loop-multi-iteration-executor-preflight")
            or context.get("preflight_paused_session_automatic_loop_multi_iteration_executor")
            or context.get("preflightPausedSessionAutomaticLoopMultiIterationExecutor")
            or context.get("review_paused_session_automatic_loop_multi_iteration_executor_preflight")
            or context.get("reviewPausedSessionAutomaticLoopMultiIterationExecutorPreflight")
            or context.get("automatic_loop_multi_iteration_executor_preflight")
            or context.get("automaticLoopMultiIterationExecutorPreflight")
        )
        policy_container = _first_dict(
            context,
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
        policy = dict(policy_container.get("policy")) if isinstance(policy_container.get("policy"), dict) else policy_container
        if not requested and not policy:
            return None
        budget_policy = policy.get("budget_policy") if isinstance(policy.get("budget_policy"), dict) else {}
        default_budget = budget_policy.get("max_policy_iterations") or len(policy.get("per_iteration_gates") or []) or 2
        max_raw = context.get("max_preflight_iterations", context.get("maxPreflightIterations", default_budget))
        try:
            max_preflight_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_preflight_iterations = 2
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or policy.get("reviewer")
        expected_policy_id = context.get("expected_policy_id") or context.get("expectedPolicyId") or policy.get("policy_id")
        return cls(
            multi_iteration_policy=policy,
            expected_policy_id=str(expected_policy_id).strip() if expected_policy_id else None,
            reviewer=str(reviewer).strip() if reviewer else None,
            max_preflight_iterations=max(0, min(max_preflight_iterations, 10)),
            require_transaction_journal=bool(context.get("require_transaction_journal", context.get("requireTransactionJournal", True))),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            require_checkpoint_after_each_iteration=bool(context.get("require_checkpoint_after_each_iteration", context.get("requireCheckpointAfterEachIteration", True))),
            require_fresh_live_callframe_per_iteration=bool(context.get("require_fresh_live_callframe_per_iteration", context.get("requireFreshLiveCallframePerIteration", True))),
            require_stop_after_each_checkpoint=bool(context.get("require_stop_after_each_checkpoint", context.get("requireStopAfterEachCheckpoint", True))),
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "preflight": self.preflight, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationExecutorPreflightManager:
    """Review-only input preflight for future bounded multi-iteration execution."""

    def review(self, spec: PausedSessionAutomaticLoopMultiIterationExecutorPreflightSpec | None) -> PausedSessionAutomaticLoopMultiIterationExecutorPreflightResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopMultiIterationExecutorPreflightResult(status=status, preflight=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutorPreflightSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_executor_preflight_request_missing"]
        policy = spec.multi_iteration_policy
        blockers: list[str] = []
        if not policy:
            blockers.append("multi_iteration_policy_required")
        elif policy.get("status") != "ready_for_review" or policy.get("ready_for_review") is not True:
            blockers.append("multi_iteration_policy_not_ready")
        policy_blockers = policy.get("blockers") if isinstance(policy.get("blockers"), list) else []
        if policy_blockers:
            blockers.append("multi_iteration_policy_has_blockers")
        policy_id = policy.get("policy_id")
        if spec.expected_policy_id and policy_id != spec.expected_policy_id:
            blockers.append("multi_iteration_policy_id_mismatch")
        budget = policy.get("budget_policy") if isinstance(policy.get("budget_policy"), dict) else {}
        if budget.get("automatic_multi_iteration_executor_implemented") is True:
            blockers.append("multi_iteration_policy_executor_already_implemented_claim")
        if budget.get("automatic_multi_iteration_execution_allowed_now") is True:
            blockers.append("multi_iteration_policy_execution_allowed_now_claim")
        max_policy_iterations = budget.get("max_policy_iterations")
        try:
            policy_budget = int(max_policy_iterations)
        except (TypeError, ValueError):
            policy_budget = 0
        if policy_budget < 2:
            blockers.append("multi_iteration_policy_budget_invalid")
        if spec.max_preflight_iterations < 2:
            blockers.append("executor_preflight_budget_requires_at_least_two")
        if spec.max_preflight_iterations > policy_budget and policy_budget:
            blockers.append("executor_preflight_budget_exceeds_policy")
        if spec.require_transaction_journal is not True:
            blockers.append("transaction_journal_required")
        if spec.require_review_per_iteration is not True or budget.get("requires_review_per_iteration") is not True:
            blockers.append("multi_iteration_policy_review_gate_missing")
        if spec.require_checkpoint_after_each_iteration is not True or budget.get("requires_checkpoint_after_each_iteration") is not True:
            blockers.append("multi_iteration_policy_checkpoint_gate_missing")
        if spec.require_fresh_live_callframe_per_iteration is not True or budget.get("requires_fresh_live_callframe_per_iteration") is not True:
            blockers.append("multi_iteration_policy_fresh_callframe_gate_missing")
        if spec.require_stop_after_each_checkpoint is not True or budget.get("stop_after_each_checkpoint") is not True:
            blockers.append("multi_iteration_policy_stop_after_checkpoint_missing")
        future_contract = policy.get("future_executor_contract") if isinstance(policy.get("future_executor_contract"), dict) else {}
        if not future_contract:
            blockers.append("future_multi_iteration_executor_contract_required")
        elif future_contract.get("implemented") is True:
            blockers.append("future_multi_iteration_executor_already_implemented_claim")
        if future_contract and future_contract.get("executor_name") not in {None, "execute_paused_session_automatic_loop_multi_iteration"}:
            blockers.append("future_multi_iteration_executor_name_mismatch")
        per_iteration_gates = policy.get("per_iteration_gates") if isinstance(policy.get("per_iteration_gates"), list) else []
        if not per_iteration_gates:
            blockers.append("multi_iteration_policy_per_iteration_gates_required")
        elif len(per_iteration_gates) < policy_budget:
            blockers.append("multi_iteration_policy_per_iteration_gates_incomplete")
        if per_iteration_gates:
            for gate in per_iteration_gates[: max(spec.max_preflight_iterations, 0)]:
                if not isinstance(gate, dict):
                    blockers.append("multi_iteration_policy_per_iteration_gate_invalid")
                    break
                if gate.get("requires_explicit_review") is not True:
                    blockers.append("multi_iteration_policy_review_gate_missing")
                if gate.get("requires_checkpoint_after_iteration") is not True:
                    blockers.append("multi_iteration_policy_checkpoint_gate_missing")
                if gate.get("requires_fresh_live_callframe") is not True:
                    blockers.append("multi_iteration_policy_fresh_callframe_gate_missing")
                if gate.get("requires_stop_for_review_after_checkpoint") is not True:
                    blockers.append("multi_iteration_policy_stop_after_checkpoint_missing")
                if gate.get("would_execute_in_this_descriptor") is True:
                    blockers.append("multi_iteration_policy_has_execution_side_effects")
                if gate.get("would_advance_queue_in_this_descriptor") is True:
                    blockers.append("multi_iteration_policy_advanced_loop_or_queue")
        side_effect_policy = policy.get("side_effect_policy") if isinstance(policy.get("side_effect_policy"), dict) else {}
        if any(
            side_effect_policy.get(key) is True
            for key in (
                "cdp_command_sent",
                "debugger_event_subscribed",
                "paused_event_captured",
                "callframe_evaluated",
                "cross_process_action_executed",
                "multi_step_continuation_executed",
                "multi_step_loop_iteration_executed",
                "automatic_loop_executed",
                "automatic_multi_iteration_loop",
            )
        ):
            blockers.append("multi_iteration_policy_has_execution_side_effects")
        if side_effect_policy.get("loop_advanced") is True or side_effect_policy.get("queue_advanced") is True:
            blockers.append("multi_iteration_policy_advanced_loop_or_queue")
        if side_effect_policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("multi_iteration_policy_managed_long_lived_session")
        if side_effect_policy.get("calls_mcp") is True:
            blockers.append("multi_iteration_policy_called_mcp")
        if side_effect_policy.get("mobile_runtime_used") is True:
            blockers.append("multi_iteration_policy_used_mobile_runtime")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutorPreflightSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        policy = spec.multi_iteration_policy if spec else {}
        budget = policy.get("budget_policy") if isinstance(policy.get("budget_policy"), dict) else {}
        future_contract = policy.get("future_executor_contract") if isinstance(policy.get("future_executor_contract"), dict) else {}
        per_iteration_gates = policy.get("per_iteration_gates") if isinstance(policy.get("per_iteration_gates"), list) else []
        policy_budget_raw = budget.get("max_policy_iterations")
        try:
            policy_budget = int(policy_budget_raw)
        except (TypeError, ValueError):
            policy_budget = len(per_iteration_gates)
        max_preflight = spec.max_preflight_iterations if spec else 0
        ready = status == "ready_for_review"
        policy_id = policy.get("policy_id")
        preflight_id = f"automatic-loop-multi-iteration-preflight:{policy_id or 'unbound'}"
        preflight_iterations = []
        for index, gate in enumerate(per_iteration_gates[:max_preflight], start=1):
            item = gate if isinstance(gate, dict) else {}
            preflight_iterations.append(
                {
                    "iteration_number": item.get("iteration_number", index),
                    "policy_gate_ready": bool(
                        item.get("requires_explicit_review") is True
                        and item.get("requires_checkpoint_after_iteration") is True
                        and item.get("requires_fresh_live_callframe") is True
                        and item.get("requires_stop_for_review_after_checkpoint") is True
                    ),
                    "would_execute_in_this_descriptor": False,
                    "would_write_checkpoint_in_this_descriptor": False,
                    "would_recover_live_callframe_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                    "requires_explicit_review": True,
                    "requires_transaction_journal": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_stop_for_review_after_checkpoint": True,
                }
            )
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-executor-preflight.v1",
            "status": status,
            "ready_for_review": ready,
            "executor_preflight_ready_for_review": ready,
            "policy_id": policy_id,
            "expected_policy_id": spec.expected_policy_id if spec else None,
            "transaction_id": policy.get("transaction_id"),
            "loop_id": policy.get("loop_id"),
            "workflow_id": policy.get("workflow_id"),
            "preflight_id": preflight_id,
            "reviewer": spec.reviewer if spec else None,
            "source_policy": {
                "schema_version": policy.get("schema_version"),
                "status": policy.get("status"),
                "ready_for_review": bool(policy.get("ready_for_review")),
                "policy_id": policy_id,
                "max_policy_iterations": policy_budget,
                "automatic_multi_iteration_executor_implemented": bool(budget.get("automatic_multi_iteration_executor_implemented")),
                "automatic_multi_iteration_execution_allowed_now": bool(budget.get("automatic_multi_iteration_execution_allowed_now")),
                "next_action": policy.get("next_action"),
            },
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_ready_policy": True,
                "requires_matching_policy_id": True,
                "requires_explicit_review_approval": True,
                "requires_transaction_journal": spec.require_transaction_journal if spec else True,
                "requires_per_iteration_review_gate": spec.require_review_per_iteration if spec else True,
                "requires_per_iteration_checkpoint_gate": spec.require_checkpoint_after_each_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": spec.require_fresh_live_callframe_per_iteration if spec else True,
                "requires_stop_after_each_checkpoint": spec.require_stop_after_each_checkpoint if spec else True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_non_daemon_execution": True,
                "requires_bounded_iteration_budget": True,
            },
            "preflight_iteration_count": len(preflight_iterations),
            "max_preflight_iterations": max_preflight,
            "policy_iteration_budget": policy_budget,
            "preflight_iterations": preflight_iterations,
            "future_executor_contract": {
                "executor_name": future_contract.get("executor_name") or "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": False,
                "expected_preflight_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-preflight.json",
                "expected_policy_artifact": future_contract.get("expected_policy_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-policy.json",
                "would_require_matching_policy_id": True,
                "would_require_explicit_review_approval": True,
                "would_require_transaction_journal": True,
                "would_execute_bounded_iterations_only": True,
                "would_checkpoint_between_iterations": True,
                "would_stop_after_each_checkpoint": True,
                "would_not_run_as_daemon": True,
                "would_not_auto_recover_live_callframe": True,
                "would_not_advance_queue_without_review": True,
                "would_not_manage_long_lived_session": True,
                "would_not_call_mcp": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "checkpoint_written": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_loop_executed": False,
            "automatic_multi_iteration_loop": False,
            "automatic_live_callframe_recovery": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_executor_preflight_request_missing": ("request", "No automatic-loop multi-iteration executor preflight request was provided.", "request_paused_session_automatic_loop_multi_iteration_executor_preflight"),
            "multi_iteration_policy_required": ("policy", "A ready bounded multi-iteration policy descriptor is required.", "review_paused_session_automatic_loop_multi_iteration_policy"),
            "multi_iteration_policy_not_ready": ("policy", "The bounded multi-iteration policy descriptor is not ready.", "resolve_multi_iteration_policy_blockers"),
            "multi_iteration_policy_has_blockers": ("policy", "The bounded multi-iteration policy still contains blockers.", "resolve_multi_iteration_policy_blockers"),
            "multi_iteration_policy_id_mismatch": ("policy", "The provided policy id does not match the expected policy id.", "refresh_matching_multi_iteration_policy"),
            "multi_iteration_policy_executor_already_implemented_claim": ("safety", "The policy claims a multi-iteration executor is already implemented.", "audit_multi_iteration_executor_claim"),
            "multi_iteration_policy_execution_allowed_now_claim": ("safety", "The policy claims multi-iteration execution is allowed now.", "audit_multi_iteration_execution_allowance"),
            "multi_iteration_policy_budget_invalid": ("budget", "The bounded multi-iteration policy must allow at least two iterations.", "refresh_multi_iteration_policy_budget"),
            "executor_preflight_budget_requires_at_least_two": ("budget", "The multi-iteration executor preflight budget must cover at least two iterations.", "raise_multi_iteration_preflight_budget"),
            "executor_preflight_budget_exceeds_policy": ("budget", "The preflight budget cannot exceed the policy budget.", "lower_multi_iteration_preflight_budget"),
            "transaction_journal_required": ("journal", "A transaction journal must be required before future execution.", "restore_multi_iteration_transaction_journal_gate"),
            "multi_iteration_policy_review_gate_missing": ("review", "Every preflight iteration must preserve explicit review gates.", "restore_multi_iteration_review_gate"),
            "multi_iteration_policy_checkpoint_gate_missing": ("checkpoint", "Every preflight iteration must preserve checkpoint gates.", "restore_multi_iteration_checkpoint_gate"),
            "multi_iteration_policy_fresh_callframe_gate_missing": ("callframe", "Every preflight iteration must require fresh live callFrame evidence.", "restore_multi_iteration_fresh_callframe_gate"),
            "multi_iteration_policy_stop_after_checkpoint_missing": ("policy", "The policy must stop for review after every checkpoint.", "restore_stop_after_each_checkpoint_policy"),
            "future_multi_iteration_executor_contract_required": ("contract", "The future multi-iteration executor contract is required.", "refresh_multi_iteration_policy_contract"),
            "future_multi_iteration_executor_already_implemented_claim": ("safety", "The future executor contract claims implementation and needs audit.", "audit_multi_iteration_executor_claim"),
            "future_multi_iteration_executor_name_mismatch": ("contract", "The future executor contract name does not match execute_paused_session_automatic_loop_multi_iteration.", "refresh_multi_iteration_executor_contract_name"),
            "multi_iteration_policy_per_iteration_gates_required": ("policy", "Per-iteration gates are required for multi-iteration executor preflight.", "refresh_multi_iteration_policy_gates"),
            "multi_iteration_policy_per_iteration_gates_incomplete": ("policy", "Per-iteration gates do not cover the policy budget.", "refresh_multi_iteration_policy_gates"),
            "multi_iteration_policy_per_iteration_gate_invalid": ("policy", "A per-iteration gate is malformed.", "refresh_multi_iteration_policy_gates"),
            "multi_iteration_policy_has_execution_side_effects": ("safety", "The policy claims execution side effects and must be audited first.", "audit_multi_iteration_policy_side_effects"),
            "multi_iteration_policy_advanced_loop_or_queue": ("safety", "The policy claims loop or queue advancement.", "audit_multi_iteration_policy_loop_state"),
            "multi_iteration_policy_managed_long_lived_session": ("safety", "The policy claims long-lived session management.", "remove_long_lived_session_from_multi_iteration_preflight"),
            "multi_iteration_policy_called_mcp": ("safety", "The policy claims MCP usage.", "remove_mcp_from_multi_iteration_preflight"),
            "multi_iteration_policy_used_mobile_runtime": ("safety", "The policy claims mobile runtime usage.", "remove_mobile_runtime_from_multi_iteration_preflight"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_preflight"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_preflight"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_preflight"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_executor_preflight_blockers"
        if status == "ready_for_review":
            return "review_future_paused_session_automatic_loop_multi_iteration_executor_preflight"
        return "inspect_paused_session_automatic_loop_multi_iteration_executor_preflight"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutionPlanSpec:
    """Review-only execution plan for a future bounded multi-iteration executor.

    This descriptor consumes the Step 257 multi-iteration executor preflight and
    materializes the final review input for a future explicit-review-only
    executor. It is deliberately not the executor: it does not execute iterations,
    write checkpoints, recover live callFrames, subscribe to debugger events,
    advance loop / queue state, manage long-lived sessions, call MCP, or touch
    mobile runtime chains.
    """

    executor_preflight: dict[str, Any] = field(default_factory=dict)
    expected_preflight_id: str | None = None
    expected_policy_id: str | None = None
    reviewer: str | None = None
    max_planned_iterations: int = 2
    require_transaction_journal: bool = True
    require_review_per_iteration: bool = True
    require_checkpoint_after_each_iteration: bool = True
    require_fresh_live_callframe_per_iteration: bool = True
    require_stop_after_each_checkpoint: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationExecutionPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_execution_plan")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecutionPlan")
            or context.get("paused-session-automatic-loop-multi-iteration-execution-plan")
            or context.get("plan_paused_session_automatic_loop_multi_iteration_execution")
            or context.get("planPausedSessionAutomaticLoopMultiIterationExecution")
            or context.get("review_paused_session_automatic_loop_multi_iteration_execution_plan")
            or context.get("reviewPausedSessionAutomaticLoopMultiIterationExecutionPlan")
            or context.get("automatic_loop_multi_iteration_execution_plan")
            or context.get("automaticLoopMultiIterationExecutionPlan")
        )
        preflight_container = _first_dict(
            context,
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
        preflight = dict(preflight_container.get("preflight")) if isinstance(preflight_container.get("preflight"), dict) else preflight_container
        if not requested and not preflight:
            return None
        default_budget = preflight.get("preflight_iteration_count") or preflight.get("policy_iteration_budget") or len(preflight.get("preflight_iterations") or []) or 2
        max_raw = context.get("max_planned_iterations", context.get("maxPlannedIterations", default_budget))
        try:
            max_planned_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_planned_iterations = 2
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or preflight.get("reviewer")
        expected_preflight_id = context.get("expected_preflight_id") or context.get("expectedPreflightId") or preflight.get("preflight_id")
        expected_policy_id = context.get("expected_policy_id") or context.get("expectedPolicyId") or preflight.get("policy_id")
        return cls(
            executor_preflight=preflight,
            expected_preflight_id=str(expected_preflight_id).strip() if expected_preflight_id else None,
            expected_policy_id=str(expected_policy_id).strip() if expected_policy_id else None,
            reviewer=str(reviewer).strip() if reviewer else None,
            max_planned_iterations=max(0, min(max_planned_iterations, 10)),
            require_transaction_journal=bool(context.get("require_transaction_journal", context.get("requireTransactionJournal", True))),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            require_checkpoint_after_each_iteration=bool(context.get("require_checkpoint_after_each_iteration", context.get("requireCheckpointAfterEachIteration", True))),
            require_fresh_live_callframe_per_iteration=bool(context.get("require_fresh_live_callframe_per_iteration", context.get("requireFreshLiveCallframePerIteration", True))),
            require_stop_after_each_checkpoint=bool(context.get("require_stop_after_each_checkpoint", context.get("requireStopAfterEachCheckpoint", True))),
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutionPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "plan": self.plan, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationExecutionPlanManager:
    """Review-only execution-plan descriptor for a future multi-iteration executor."""

    def plan(self, spec: PausedSessionAutomaticLoopMultiIterationExecutionPlanSpec | None) -> PausedSessionAutomaticLoopMultiIterationExecutionPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopMultiIterationExecutionPlanResult(status=status, plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutionPlanSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_execution_plan_request_missing"]
        preflight = spec.executor_preflight
        blockers: list[str] = []
        if not preflight:
            blockers.append("multi_iteration_executor_preflight_required")
        elif preflight.get("status") != "ready_for_review" or preflight.get("ready_for_review") is not True:
            blockers.append("multi_iteration_executor_preflight_not_ready")
        preflight_blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
        if preflight_blockers:
            blockers.append("multi_iteration_executor_preflight_has_blockers")
        preflight_id = preflight.get("preflight_id")
        policy_id = preflight.get("policy_id")
        if spec.expected_preflight_id and preflight_id != spec.expected_preflight_id:
            blockers.append("multi_iteration_preflight_id_mismatch")
        if spec.expected_policy_id and policy_id != spec.expected_policy_id:
            blockers.append("multi_iteration_policy_id_mismatch")
        gates = preflight.get("executor_input_gates") if isinstance(preflight.get("executor_input_gates"), dict) else {}
        if gates.get("ready_to_execute_now") is True:
            blockers.append("executor_preflight_ready_to_execute_now_claim")
        if gates.get("automatic_multi_iteration_executor_implemented") is True:
            blockers.append("executor_preflight_executor_already_implemented_claim")
        if gates.get("automatic_multi_iteration_execution_allowed_now") is True:
            blockers.append("executor_preflight_execution_allowed_now_claim")
        if spec.require_transaction_journal is not True or gates.get("requires_transaction_journal") is not True:
            blockers.append("transaction_journal_required")
        if spec.require_review_per_iteration is not True or gates.get("requires_per_iteration_review_gate") is not True:
            blockers.append("per_iteration_review_gate_required")
        if spec.require_checkpoint_after_each_iteration is not True or gates.get("requires_per_iteration_checkpoint_gate") is not True:
            blockers.append("per_iteration_checkpoint_gate_required")
        if spec.require_fresh_live_callframe_per_iteration is not True or gates.get("requires_fresh_live_callframe_per_iteration") is not True:
            blockers.append("fresh_live_callframe_per_iteration_required")
        if spec.require_stop_after_each_checkpoint is not True or gates.get("requires_stop_after_each_checkpoint") is not True:
            blockers.append("stop_after_each_checkpoint_required")
        if gates.get("requires_retained_attached_session_per_iteration") is not True:
            blockers.append("retained_attached_session_per_iteration_required")
        if gates.get("requires_non_daemon_execution") is not True:
            blockers.append("non_daemon_execution_required")
        if gates.get("requires_bounded_iteration_budget") is not True:
            blockers.append("bounded_iteration_budget_required")
        policy_budget_raw = preflight.get("policy_iteration_budget")
        try:
            policy_budget = int(policy_budget_raw)
        except (TypeError, ValueError):
            policy_budget = 0
        iteration_count_raw = preflight.get("preflight_iteration_count")
        try:
            iteration_count = int(iteration_count_raw)
        except (TypeError, ValueError):
            iteration_count = 0
        if policy_budget < 2:
            blockers.append("multi_iteration_policy_budget_invalid")
        if iteration_count < 2:
            blockers.append("multi_iteration_preflight_iteration_count_invalid")
        if spec.max_planned_iterations < 2:
            blockers.append("execution_plan_budget_requires_at_least_two")
        if policy_budget and spec.max_planned_iterations > policy_budget:
            blockers.append("execution_plan_budget_exceeds_policy")
        if iteration_count and spec.max_planned_iterations > iteration_count:
            blockers.append("execution_plan_budget_exceeds_preflight")
        future_contract = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        if not future_contract:
            blockers.append("future_multi_iteration_executor_contract_required")
        elif future_contract.get("implemented") is True:
            blockers.append("future_multi_iteration_executor_already_implemented_claim")
        if future_contract and future_contract.get("executor_name") not in {None, "execute_paused_session_automatic_loop_multi_iteration"}:
            blockers.append("future_multi_iteration_executor_name_mismatch")
        iterations = preflight.get("preflight_iterations") if isinstance(preflight.get("preflight_iterations"), list) else []
        if not iterations:
            blockers.append("multi_iteration_preflight_iterations_required")
        for item in iterations[: max(spec.max_planned_iterations, 0)]:
            if not isinstance(item, dict):
                blockers.append("multi_iteration_preflight_iteration_invalid")
                break
            if item.get("policy_gate_ready") is not True:
                blockers.append("multi_iteration_preflight_iteration_gate_not_ready")
            if item.get("requires_explicit_review") is not True:
                blockers.append("per_iteration_review_gate_required")
            if item.get("requires_transaction_journal") is not True:
                blockers.append("transaction_journal_required")
            if item.get("requires_fresh_live_callframe") is not True:
                blockers.append("fresh_live_callframe_per_iteration_required")
            if item.get("requires_retained_attached_session") is not True:
                blockers.append("retained_attached_session_per_iteration_required")
            if item.get("requires_checkpoint_after_iteration") is not True:
                blockers.append("per_iteration_checkpoint_gate_required")
            if item.get("requires_stop_for_review_after_checkpoint") is not True:
                blockers.append("stop_after_each_checkpoint_required")
            if item.get("would_execute_in_this_descriptor") is True:
                blockers.append("executor_preflight_has_execution_side_effects")
            if item.get("would_write_checkpoint_in_this_descriptor") is True:
                blockers.append("executor_preflight_wrote_checkpoint")
            if item.get("would_recover_live_callframe_in_this_descriptor") is True:
                blockers.append("executor_preflight_recovered_live_callframe")
            if item.get("would_advance_queue_in_this_descriptor") is True:
                blockers.append("executor_preflight_advanced_loop_or_queue")
        side_effect_policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        if any(
            side_effect_policy.get(key) is True
            for key in (
                "cdp_command_sent",
                "debugger_event_subscribed",
                "paused_event_captured",
                "callframe_evaluated",
                "checkpoint_written",
                "cross_process_action_executed",
                "multi_step_continuation_executed",
                "multi_step_loop_iteration_executed",
                "automatic_loop_executed",
                "automatic_multi_iteration_loop",
                "automatic_live_callframe_recovery",
            )
        ):
            blockers.append("executor_preflight_has_execution_side_effects")
        if side_effect_policy.get("loop_advanced") is True or side_effect_policy.get("queue_advanced") is True:
            blockers.append("executor_preflight_advanced_loop_or_queue")
        if side_effect_policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("executor_preflight_managed_long_lived_session")
        if side_effect_policy.get("calls_mcp") is True:
            blockers.append("executor_preflight_called_mcp")
        if side_effect_policy.get("mobile_runtime_used") is True:
            blockers.append("executor_preflight_used_mobile_runtime")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutionPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        preflight = spec.executor_preflight if spec else {}
        gates = preflight.get("executor_input_gates") if isinstance(preflight.get("executor_input_gates"), dict) else {}
        future_contract = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        iterations = preflight.get("preflight_iterations") if isinstance(preflight.get("preflight_iterations"), list) else []
        ready = status == "ready_for_review"
        preflight_id = preflight.get("preflight_id")
        policy_id = preflight.get("policy_id")
        planned_budget = spec.max_planned_iterations if spec else 0
        execution_plan_id = f"automatic-loop-multi-iteration-execution-plan:{preflight_id or policy_id or 'unbound'}"
        planned_iterations = []
        for index, item in enumerate(iterations[:planned_budget], start=1):
            gate = item if isinstance(item, dict) else {}
            planned_iterations.append(
                {
                    "iteration_number": gate.get("iteration_number", index),
                    "plan_iteration_index": index - 1,
                    "source_policy_gate_ready": bool(gate.get("policy_gate_ready")),
                    "requires_explicit_review": True,
                    "requires_transaction_journal": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_stop_for_review_after_checkpoint": True,
                    "would_execute_in_this_descriptor": False,
                    "would_delegate_to_future_executor_now": False,
                    "would_write_checkpoint_in_this_descriptor": False,
                    "would_recover_live_callframe_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                }
            )
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-execution-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "execution_plan_ready_for_review": ready,
            "execution_plan_id": execution_plan_id,
            "preflight_id": preflight_id,
            "expected_preflight_id": spec.expected_preflight_id if spec else None,
            "policy_id": policy_id,
            "expected_policy_id": spec.expected_policy_id if spec else None,
            "transaction_id": preflight.get("transaction_id"),
            "loop_id": preflight.get("loop_id"),
            "workflow_id": preflight.get("workflow_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_preflight": {
                "schema_version": preflight.get("schema_version"),
                "status": preflight.get("status"),
                "ready_for_review": bool(preflight.get("ready_for_review")),
                "executor_preflight_ready_for_review": bool(preflight.get("executor_preflight_ready_for_review")),
                "preflight_id": preflight_id,
                "policy_id": policy_id,
                "preflight_iteration_count": preflight.get("preflight_iteration_count", 0),
                "policy_iteration_budget": preflight.get("policy_iteration_budget", 0),
                "next_action": preflight.get("next_action"),
            },
            "execution_review_gates": {
                "ready_to_execute_now": False,
                "execution_plan_only": True,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_ready_preflight": True,
                "requires_matching_preflight_id": True,
                "requires_matching_policy_id": True,
                "requires_explicit_review_approval": True,
                "requires_transaction_journal": spec.require_transaction_journal if spec else True,
                "requires_per_iteration_review_gate": spec.require_review_per_iteration if spec else True,
                "requires_per_iteration_checkpoint_gate": spec.require_checkpoint_after_each_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": spec.require_fresh_live_callframe_per_iteration if spec else True,
                "requires_stop_after_each_checkpoint": spec.require_stop_after_each_checkpoint if spec else True,
                "requires_retained_attached_session_per_iteration": bool(gates.get("requires_retained_attached_session_per_iteration", True)),
                "requires_non_daemon_execution": bool(gates.get("requires_non_daemon_execution", True)),
                "requires_bounded_iteration_budget": bool(gates.get("requires_bounded_iteration_budget", True)),
            },
            "planned_iteration_count": len(planned_iterations),
            "max_planned_iterations": planned_budget,
            "planned_iterations": planned_iterations,
            "future_executor_contract": {
                "executor_name": future_contract.get("executor_name") or "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": False,
                "expected_execution_plan_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-plan.json",
                "expected_preflight_artifact": future_contract.get("expected_preflight_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-executor-preflight.json",
                "expected_policy_artifact": future_contract.get("expected_policy_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-policy.json",
                "expected_result_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
                "would_require_matching_preflight_id": True,
                "would_require_matching_policy_id": True,
                "would_require_explicit_review_approval": True,
                "would_require_transaction_journal": True,
                "would_execute_bounded_iterations_only": True,
                "would_checkpoint_between_iterations": True,
                "would_stop_after_each_checkpoint": True,
                "would_not_run_as_daemon": True,
                "would_not_auto_recover_live_callframe": True,
                "would_not_advance_queue_without_review": True,
                "would_not_manage_long_lived_session": True,
                "would_not_call_mcp": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "execution_plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "checkpoint_written": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_loop_executed": False,
            "automatic_multi_iteration_loop": False,
            "automatic_live_callframe_recovery": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_execution_plan_request_missing": ("request", "No automatic-loop multi-iteration execution plan request was provided.", "request_paused_session_automatic_loop_multi_iteration_execution_plan"),
            "multi_iteration_executor_preflight_required": ("preflight", "A ready multi-iteration executor preflight descriptor is required.", "review_paused_session_automatic_loop_multi_iteration_executor_preflight"),
            "multi_iteration_executor_preflight_not_ready": ("preflight", "The multi-iteration executor preflight descriptor is not ready.", "resolve_multi_iteration_executor_preflight_blockers"),
            "multi_iteration_executor_preflight_has_blockers": ("preflight", "The multi-iteration executor preflight still contains blockers.", "resolve_multi_iteration_executor_preflight_blockers"),
            "multi_iteration_preflight_id_mismatch": ("preflight", "The preflight id does not match the expected preflight id.", "refresh_matching_multi_iteration_executor_preflight"),
            "multi_iteration_policy_id_mismatch": ("policy", "The policy id does not match the expected policy id.", "refresh_matching_multi_iteration_policy"),
            "executor_preflight_ready_to_execute_now_claim": ("safety", "The preflight claims it is ready to execute now.", "audit_multi_iteration_preflight_execution_claim"),
            "executor_preflight_executor_already_implemented_claim": ("safety", "The preflight claims the future executor is already implemented.", "audit_multi_iteration_executor_claim"),
            "executor_preflight_execution_allowed_now_claim": ("safety", "The preflight claims multi-iteration execution is already allowed.", "audit_multi_iteration_execution_allowance"),
            "transaction_journal_required": ("journal", "A transaction journal gate is required before any future execution.", "restore_multi_iteration_transaction_journal_gate"),
            "per_iteration_review_gate_required": ("review", "Every planned iteration must preserve explicit review gates.", "restore_multi_iteration_review_gate"),
            "per_iteration_checkpoint_gate_required": ("checkpoint", "Every planned iteration must preserve checkpoint gates.", "restore_multi_iteration_checkpoint_gate"),
            "fresh_live_callframe_per_iteration_required": ("callframe", "Every planned iteration must require fresh live callFrame evidence.", "restore_multi_iteration_fresh_callframe_gate"),
            "stop_after_each_checkpoint_required": ("policy", "The plan must stop for review after every checkpoint.", "restore_stop_after_each_checkpoint_policy"),
            "retained_attached_session_per_iteration_required": ("session", "Every planned iteration must require a retained attached session.", "restore_retained_session_gate"),
            "non_daemon_execution_required": ("safety", "The future executor must not run as a daemon.", "restore_non_daemon_execution_gate"),
            "bounded_iteration_budget_required": ("budget", "The future executor must use a bounded iteration budget.", "restore_bounded_iteration_budget_gate"),
            "multi_iteration_policy_budget_invalid": ("budget", "The policy budget must allow at least two iterations.", "refresh_multi_iteration_policy_budget"),
            "multi_iteration_preflight_iteration_count_invalid": ("budget", "The preflight must cover at least two iterations.", "refresh_multi_iteration_executor_preflight"),
            "execution_plan_budget_requires_at_least_two": ("budget", "The execution plan budget must cover at least two iterations.", "raise_multi_iteration_execution_plan_budget"),
            "execution_plan_budget_exceeds_policy": ("budget", "The execution plan budget cannot exceed the policy budget.", "lower_multi_iteration_execution_plan_budget"),
            "execution_plan_budget_exceeds_preflight": ("budget", "The execution plan budget cannot exceed the preflight iteration count.", "lower_multi_iteration_execution_plan_budget"),
            "future_multi_iteration_executor_contract_required": ("contract", "The future multi-iteration executor contract is required.", "refresh_multi_iteration_executor_contract"),
            "future_multi_iteration_executor_already_implemented_claim": ("safety", "The future executor contract claims implementation and needs audit.", "audit_multi_iteration_executor_claim"),
            "future_multi_iteration_executor_name_mismatch": ("contract", "The future executor contract name does not match execute_paused_session_automatic_loop_multi_iteration.", "refresh_multi_iteration_executor_contract_name"),
            "multi_iteration_preflight_iterations_required": ("preflight", "Preflight iteration gates are required.", "refresh_multi_iteration_preflight_iterations"),
            "multi_iteration_preflight_iteration_invalid": ("preflight", "A preflight iteration gate is malformed.", "refresh_multi_iteration_preflight_iterations"),
            "multi_iteration_preflight_iteration_gate_not_ready": ("preflight", "A preflight iteration gate is not ready.", "refresh_multi_iteration_preflight_iterations"),
            "executor_preflight_has_execution_side_effects": ("safety", "The preflight reports execution side effects and must be audited.", "audit_multi_iteration_preflight_side_effects"),
            "executor_preflight_wrote_checkpoint": ("safety", "The preflight reports checkpoint writes.", "audit_multi_iteration_preflight_checkpoint_claim"),
            "executor_preflight_recovered_live_callframe": ("safety", "The preflight reports live callFrame recovery.", "audit_multi_iteration_preflight_callframe_claim"),
            "executor_preflight_advanced_loop_or_queue": ("safety", "The preflight reports loop or queue advancement.", "audit_multi_iteration_preflight_loop_state"),
            "executor_preflight_managed_long_lived_session": ("safety", "The preflight reports long-lived session management.", "remove_long_lived_session_from_execution_plan"),
            "executor_preflight_called_mcp": ("safety", "The preflight reports MCP usage.", "remove_mcp_from_multi_iteration_execution_plan"),
            "executor_preflight_used_mobile_runtime": ("safety", "The preflight reports mobile runtime usage.", "remove_mobile_runtime_from_multi_iteration_execution_plan"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_execution_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_execution_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_execution_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_execution_plan_blockers"
        if status == "ready_for_review":
            return "review_future_paused_session_automatic_loop_multi_iteration_executor_execution"
        return "inspect_paused_session_automatic_loop_multi_iteration_execution_plan"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanSpec:
    """Review-only approval / transaction plan for a future multi-iteration executor.

    This consumes the Step 258 multi-iteration execution-plan descriptor and
    prepares manual approval, idempotency, and transaction requirements for a
    future bounded multi-iteration executor. It is not the executor: it records
    no approval, writes no journal, executes no iteration, sends no CDP command,
    recovers no live callFrame, subscribes to no debugger event, advances no
    queue / loop, manages no long-lived session, calls no MCP, and touches no
    mobile runtime chain.
    """

    execution_plan: dict[str, Any] = field(default_factory=dict)
    expected_execution_plan_id: str | None = None
    expected_preflight_id: str | None = None
    expected_policy_id: str | None = None
    reviewer: str | None = None
    max_approved_iterations: int = 2
    require_transaction_journal: bool = True
    require_review_per_iteration: bool = True
    require_checkpoint_after_each_iteration: bool = True
    require_fresh_live_callframe_per_iteration: bool = True
    require_stop_after_each_checkpoint: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_executor_approval_plan")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecutorApprovalPlan")
            or context.get("paused-session-automatic-loop-multi-iteration-executor-approval-plan")
            or context.get("plan_paused_session_automatic_loop_multi_iteration_executor_approval")
            or context.get("planPausedSessionAutomaticLoopMultiIterationExecutorApproval")
            or context.get("review_paused_session_automatic_loop_multi_iteration_executor_approval_plan")
            or context.get("reviewPausedSessionAutomaticLoopMultiIterationExecutorApprovalPlan")
            or context.get("automatic_loop_multi_iteration_executor_approval_plan")
            or context.get("automaticLoopMultiIterationExecutorApprovalPlan")
        )
        plan_container = _first_dict(
            context,
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
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        if not requested and not plan:
            return None
        default_budget = plan.get("planned_iteration_count") or plan.get("max_planned_iterations") or len(plan.get("planned_iterations") or []) or 2
        max_raw = context.get("max_approved_iterations", context.get("maxApprovedIterations", default_budget))
        try:
            max_approved_iterations = int(max_raw)
        except (TypeError, ValueError):
            max_approved_iterations = 2
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or plan.get("reviewer")
        expected_execution_plan_id = context.get("expected_execution_plan_id") or context.get("expectedExecutionPlanId") or plan.get("execution_plan_id")
        expected_preflight_id = context.get("expected_preflight_id") or context.get("expectedPreflightId") or plan.get("preflight_id")
        expected_policy_id = context.get("expected_policy_id") or context.get("expectedPolicyId") or plan.get("policy_id")
        return cls(
            execution_plan=plan,
            expected_execution_plan_id=str(expected_execution_plan_id).strip() if expected_execution_plan_id else None,
            expected_preflight_id=str(expected_preflight_id).strip() if expected_preflight_id else None,
            expected_policy_id=str(expected_policy_id).strip() if expected_policy_id else None,
            reviewer=str(reviewer).strip() if reviewer else None,
            max_approved_iterations=max(0, min(max_approved_iterations, 10)),
            require_transaction_journal=bool(context.get("require_transaction_journal", context.get("requireTransactionJournal", True))),
            require_review_per_iteration=bool(context.get("require_review_per_iteration", context.get("requireReviewPerIteration", True))),
            require_checkpoint_after_each_iteration=bool(context.get("require_checkpoint_after_each_iteration", context.get("requireCheckpointAfterEachIteration", True))),
            require_fresh_live_callframe_per_iteration=bool(context.get("require_fresh_live_callframe_per_iteration", context.get("requireFreshLiveCallframePerIteration", True))),
            require_stop_after_each_checkpoint=bool(context.get("require_stop_after_each_checkpoint", context.get("requireStopAfterEachCheckpoint", True))),
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanResult:
    status: str
    approval_plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "approval_plan": self.approval_plan, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanManager:
    """Review-only approval / transaction plan before any multi-iteration executor."""

    def plan(self, spec: PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanSpec | None) -> PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanResult(status=status, approval_plan=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_executor_approval_plan_request_missing"]
        plan = spec.execution_plan
        blockers: list[str] = []
        if not plan:
            blockers.append("multi_iteration_execution_plan_required")
        elif plan.get("status") != "ready_for_review" or plan.get("ready_for_review") is not True or plan.get("execution_plan_ready_for_review") is not True:
            blockers.append("multi_iteration_execution_plan_not_ready")
        plan_blockers = plan.get("blockers") if isinstance(plan.get("blockers"), list) else []
        if plan_blockers:
            blockers.append("multi_iteration_execution_plan_has_blockers")
        execution_plan_id = plan.get("execution_plan_id")
        preflight_id = plan.get("preflight_id")
        policy_id = plan.get("policy_id")
        if spec.expected_execution_plan_id and execution_plan_id != spec.expected_execution_plan_id:
            blockers.append("multi_iteration_execution_plan_id_mismatch")
        if spec.expected_preflight_id and preflight_id != spec.expected_preflight_id:
            blockers.append("multi_iteration_preflight_id_mismatch")
        if spec.expected_policy_id and policy_id != spec.expected_policy_id:
            blockers.append("multi_iteration_policy_id_mismatch")
        gates = plan.get("execution_review_gates") if isinstance(plan.get("execution_review_gates"), dict) else {}
        if gates.get("ready_to_execute_now") is True:
            blockers.append("execution_plan_ready_to_execute_now_claim")
        if gates.get("execution_plan_only") is not True:
            blockers.append("execution_plan_only_gate_required")
        if gates.get("automatic_multi_iteration_executor_implemented") is True:
            blockers.append("execution_plan_executor_already_implemented_claim")
        if gates.get("automatic_multi_iteration_execution_allowed_now") is True:
            blockers.append("execution_plan_execution_allowed_now_claim")
        if spec.require_transaction_journal is not True or gates.get("requires_transaction_journal") is not True:
            blockers.append("transaction_journal_required")
        if spec.require_review_per_iteration is not True or gates.get("requires_per_iteration_review_gate") is not True:
            blockers.append("per_iteration_review_gate_required")
        if spec.require_checkpoint_after_each_iteration is not True or gates.get("requires_per_iteration_checkpoint_gate") is not True:
            blockers.append("per_iteration_checkpoint_gate_required")
        if spec.require_fresh_live_callframe_per_iteration is not True or gates.get("requires_fresh_live_callframe_per_iteration") is not True:
            blockers.append("fresh_live_callframe_per_iteration_required")
        if spec.require_stop_after_each_checkpoint is not True or gates.get("requires_stop_after_each_checkpoint") is not True:
            blockers.append("stop_after_each_checkpoint_required")
        if gates.get("requires_retained_attached_session_per_iteration") is not True:
            blockers.append("retained_attached_session_per_iteration_required")
        if gates.get("requires_non_daemon_execution") is not True:
            blockers.append("non_daemon_execution_required")
        if gates.get("requires_bounded_iteration_budget") is not True:
            blockers.append("bounded_iteration_budget_required")
        planned_count_raw = plan.get("planned_iteration_count")
        try:
            planned_count = int(planned_count_raw)
        except (TypeError, ValueError):
            planned_count = 0
        if planned_count < 2:
            blockers.append("multi_iteration_execution_plan_iteration_count_invalid")
        if spec.max_approved_iterations < 2:
            blockers.append("approval_plan_budget_requires_at_least_two")
        if planned_count and spec.max_approved_iterations > planned_count:
            blockers.append("approval_plan_budget_exceeds_execution_plan")
        future_contract = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        if not future_contract:
            blockers.append("future_multi_iteration_executor_contract_required")
        elif future_contract.get("implemented") is True:
            blockers.append("future_multi_iteration_executor_already_implemented_claim")
        if future_contract and future_contract.get("executor_name") not in {None, "execute_paused_session_automatic_loop_multi_iteration"}:
            blockers.append("future_multi_iteration_executor_name_mismatch")
        iterations = plan.get("planned_iterations") if isinstance(plan.get("planned_iterations"), list) else []
        if not iterations:
            blockers.append("multi_iteration_execution_plan_iterations_required")
        for item in iterations[: max(spec.max_approved_iterations, 0)]:
            if not isinstance(item, dict):
                blockers.append("multi_iteration_execution_plan_iteration_invalid")
                break
            if item.get("source_policy_gate_ready") is not True:
                blockers.append("multi_iteration_execution_plan_iteration_gate_not_ready")
            if item.get("requires_explicit_review") is not True:
                blockers.append("per_iteration_review_gate_required")
            if item.get("requires_transaction_journal") is not True:
                blockers.append("transaction_journal_required")
            if item.get("requires_fresh_live_callframe") is not True:
                blockers.append("fresh_live_callframe_per_iteration_required")
            if item.get("requires_retained_attached_session") is not True:
                blockers.append("retained_attached_session_per_iteration_required")
            if item.get("requires_checkpoint_after_iteration") is not True:
                blockers.append("per_iteration_checkpoint_gate_required")
            if item.get("requires_stop_for_review_after_checkpoint") is not True:
                blockers.append("stop_after_each_checkpoint_required")
            if item.get("would_execute_in_this_descriptor") is True or item.get("would_delegate_to_future_executor_now") is True:
                blockers.append("execution_plan_has_execution_side_effects")
            if item.get("would_write_checkpoint_in_this_descriptor") is True:
                blockers.append("execution_plan_wrote_checkpoint")
            if item.get("would_recover_live_callframe_in_this_descriptor") is True:
                blockers.append("execution_plan_recovered_live_callframe")
            if item.get("would_advance_queue_in_this_descriptor") is True:
                blockers.append("execution_plan_advanced_loop_or_queue")
        side_effect_policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        if any(
            side_effect_policy.get(key) is True
            for key in (
                "cdp_command_sent",
                "debugger_event_subscribed",
                "paused_event_captured",
                "callframe_evaluated",
                "checkpoint_written",
                "cross_process_action_executed",
                "multi_step_continuation_executed",
                "multi_step_loop_iteration_executed",
                "automatic_loop_executed",
                "automatic_multi_iteration_loop",
                "automatic_live_callframe_recovery",
            )
        ):
            blockers.append("execution_plan_has_execution_side_effects")
        if side_effect_policy.get("loop_advanced") is True or side_effect_policy.get("queue_advanced") is True:
            blockers.append("execution_plan_advanced_loop_or_queue")
        if side_effect_policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("execution_plan_managed_long_lived_session")
        if side_effect_policy.get("calls_mcp") is True:
            blockers.append("execution_plan_called_mcp")
        if side_effect_policy.get("mobile_runtime_used") is True:
            blockers.append("execution_plan_used_mobile_runtime")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutorApprovalPlanSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        plan = spec.execution_plan if spec else {}
        gates = plan.get("execution_review_gates") if isinstance(plan.get("execution_review_gates"), dict) else {}
        future_contract = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        iterations = plan.get("planned_iterations") if isinstance(plan.get("planned_iterations"), list) else []
        ready = status == "ready_for_review"
        execution_plan_id = plan.get("execution_plan_id")
        preflight_id = plan.get("preflight_id")
        policy_id = plan.get("policy_id")
        transaction_id = plan.get("transaction_id") or f"automatic-loop-multi-iteration-executor-transaction:{execution_plan_id or preflight_id or policy_id or 'unbound'}"
        approved_budget = spec.max_approved_iterations if spec else 0
        approved_iterations = []
        for index, item in enumerate(iterations[:approved_budget], start=1):
            gate = item if isinstance(item, dict) else {}
            approved_iterations.append(
                {
                    "iteration_number": gate.get("iteration_number", index),
                    "plan_iteration_index": gate.get("plan_iteration_index", index - 1),
                    "approval_status": "requires_explicit_approval_record",
                    "requires_explicit_review": True,
                    "requires_transaction_journal": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_stop_for_review_after_checkpoint": True,
                    "would_execute_in_this_plan": False,
                    "would_delegate_to_future_executor_now": False,
                    "would_write_checkpoint_in_this_plan": False,
                    "would_recover_live_callframe_in_this_plan": False,
                    "would_advance_queue_in_this_plan": False,
                }
            )
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-executor-approval-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "approval_plan_ready_for_review": ready,
            "approval_plan_id": f"automatic-loop-multi-iteration-executor-approval-plan:{execution_plan_id or preflight_id or policy_id or 'unbound'}",
            "execution_plan_id": execution_plan_id,
            "expected_execution_plan_id": spec.expected_execution_plan_id if spec else None,
            "preflight_id": preflight_id,
            "expected_preflight_id": spec.expected_preflight_id if spec else None,
            "policy_id": policy_id,
            "expected_policy_id": spec.expected_policy_id if spec else None,
            "transaction_id": transaction_id,
            "loop_id": plan.get("loop_id"),
            "workflow_id": plan.get("workflow_id"),
            "reviewer": spec.reviewer if spec else None,
            "source_execution_plan": {
                "schema_version": plan.get("schema_version"),
                "status": plan.get("status"),
                "ready_for_review": bool(plan.get("ready_for_review")),
                "execution_plan_ready_for_review": bool(plan.get("execution_plan_ready_for_review")),
                "execution_plan_id": execution_plan_id,
                "preflight_id": preflight_id,
                "policy_id": policy_id,
                "planned_iteration_count": plan.get("planned_iteration_count", 0),
                "max_planned_iterations": plan.get("max_planned_iterations", 0),
                "ready_to_execute_now": bool(gates.get("ready_to_execute_now")),
                "automatic_multi_iteration_executor_implemented": bool(gates.get("automatic_multi_iteration_executor_implemented")),
                "automatic_multi_iteration_execution_allowed_now": bool(gates.get("automatic_multi_iteration_execution_allowed_now")),
                "future_executor_implemented": bool(future_contract.get("implemented")),
                "next_action": plan.get("next_action"),
            },
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "approval_plan_only": True,
                "transaction_plan_only": True,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "approval_recorded": False,
                "transaction_started": False,
                "journal_written": False,
                "requires_ready_execution_plan": True,
                "requires_matching_execution_plan_id": True,
                "requires_matching_preflight_id": True,
                "requires_matching_policy_id": True,
                "requires_approval_record": True,
                "requires_transaction_journal": spec.require_transaction_journal if spec else True,
                "requires_per_iteration_review_gate": spec.require_review_per_iteration if spec else True,
                "requires_per_iteration_checkpoint_gate": spec.require_checkpoint_after_each_iteration if spec else True,
                "requires_fresh_live_callframe_per_iteration": spec.require_fresh_live_callframe_per_iteration if spec else True,
                "requires_stop_after_each_checkpoint": spec.require_stop_after_each_checkpoint if spec else True,
                "requires_retained_attached_session_per_iteration": bool(gates.get("requires_retained_attached_session_per_iteration", True)),
                "requires_non_daemon_execution": bool(gates.get("requires_non_daemon_execution", True)),
                "requires_bounded_iteration_budget": bool(gates.get("requires_bounded_iteration_budget", True)),
            },
            "approval_requirements": {
                "requires_explicit_review_approval": True,
                "requires_non_empty_reviewer_before_recording": True,
                "requires_matching_execution_plan_id": True,
                "requires_matching_preflight_id": True,
                "requires_matching_policy_id": True,
                "requires_review_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "approval_recorded_now": False,
                "approval_record_writer_implemented": False,
                "approval_record_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-approval-record.json",
            },
            "approved_iteration_count": len(approved_iterations),
            "max_approved_iterations": approved_budget,
            "approved_iterations": approved_iterations,
            "transaction_plan": {
                "transaction_id": transaction_id,
                "idempotency_key": transaction_id,
                "transaction_started": False,
                "journal_written_now": False,
                "journal_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-journal.json",
                "result_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
                "requires_append_only_journal": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "requires_manual_resume_after_failure": True,
                "requires_no_daemon": True,
            },
            "future_executor_contract": {
                "executor_name": future_contract.get("executor_name") or "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": False,
                "expected_execution_plan_artifact": future_contract.get("expected_execution_plan_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-execution-plan.json",
                "expected_preflight_artifact": future_contract.get("expected_preflight_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-executor-preflight.json",
                "expected_policy_artifact": future_contract.get("expected_policy_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-policy.json",
                "approval_plan_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-approval-plan.json",
                "approval_record_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-approval-record.json",
                "transaction_journal_artifact": "workspace/paused-session-automatic-loop-multi-iteration-executor-journal.json",
                "expected_result_artifact": future_contract.get("expected_result_artifact") or "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
                "would_require_matching_execution_plan_id": True,
                "would_require_matching_preflight_id": True,
                "would_require_matching_policy_id": True,
                "would_require_explicit_review_approval": True,
                "would_require_transaction_journal": True,
                "would_execute_bounded_iterations_only": True,
                "would_checkpoint_between_iterations": True,
                "would_stop_after_each_checkpoint": True,
                "would_not_run_as_daemon": True,
                "would_not_auto_recover_live_callframe": True,
                "would_not_advance_queue_without_review": True,
                "would_not_manage_long_lived_session": True,
                "would_not_call_mcp": True,
                "would_not_touch_mobile_runtime_chains": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_domain_enabled": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "checkpoint_written": False,
            "cross_process_action_executed": False,
            "multi_step_continuation_executed": False,
            "multi_step_loop_iteration_executed": False,
            "automatic_loop_executed": False,
            "automatic_multi_iteration_loop": False,
            "automatic_live_callframe_recovery": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "automatic_queue_advance": False,
            "automatic_wrapper_continuation": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_executor_approval_plan_request_missing": ("request", "No automatic-loop multi-iteration executor approval-plan request was provided.", "request_paused_session_automatic_loop_multi_iteration_executor_approval_plan"),
            "multi_iteration_execution_plan_required": ("execution_plan", "A ready multi-iteration execution-plan descriptor is required.", "review_paused_session_automatic_loop_multi_iteration_execution_plan"),
            "multi_iteration_execution_plan_not_ready": ("execution_plan", "The multi-iteration execution-plan descriptor is not ready.", "resolve_multi_iteration_execution_plan_blockers"),
            "multi_iteration_execution_plan_has_blockers": ("execution_plan", "The multi-iteration execution plan still contains blockers.", "resolve_multi_iteration_execution_plan_blockers"),
            "multi_iteration_execution_plan_id_mismatch": ("execution_plan", "The execution plan id does not match the expected execution plan id.", "refresh_matching_multi_iteration_execution_plan"),
            "multi_iteration_preflight_id_mismatch": ("preflight", "The preflight id does not match the expected preflight id.", "refresh_matching_multi_iteration_executor_preflight"),
            "multi_iteration_policy_id_mismatch": ("policy", "The policy id does not match the expected policy id.", "refresh_matching_multi_iteration_policy"),
            "execution_plan_ready_to_execute_now_claim": ("safety", "The execution plan claims execution is ready now.", "audit_multi_iteration_execution_plan_execution_claim"),
            "execution_plan_only_gate_required": ("safety", "The execution plan must remain plan-only.", "regenerate_multi_iteration_execution_plan_as_plan_only"),
            "execution_plan_executor_already_implemented_claim": ("safety", "The execution plan claims the future executor is already implemented.", "audit_multi_iteration_executor_claim"),
            "execution_plan_execution_allowed_now_claim": ("safety", "The execution plan claims multi-iteration execution is already allowed.", "audit_multi_iteration_execution_allowance"),
            "transaction_journal_required": ("journal", "A transaction journal gate is required before any future execution.", "restore_multi_iteration_transaction_journal_gate"),
            "per_iteration_review_gate_required": ("review", "Every approved iteration must preserve explicit review gates.", "restore_multi_iteration_review_gate"),
            "per_iteration_checkpoint_gate_required": ("checkpoint", "Every approved iteration must preserve checkpoint gates.", "restore_multi_iteration_checkpoint_gate"),
            "fresh_live_callframe_per_iteration_required": ("callframe", "Every approved iteration must require fresh live callFrame evidence.", "restore_multi_iteration_fresh_callframe_gate"),
            "stop_after_each_checkpoint_required": ("policy", "The plan must stop for review after every checkpoint.", "restore_stop_after_each_checkpoint_policy"),
            "retained_attached_session_per_iteration_required": ("session", "Every approved iteration must require a retained attached session.", "restore_retained_session_gate"),
            "non_daemon_execution_required": ("safety", "The future executor must not run as a daemon.", "restore_non_daemon_execution_gate"),
            "bounded_iteration_budget_required": ("budget", "The future executor must use a bounded iteration budget.", "restore_bounded_iteration_budget_gate"),
            "multi_iteration_execution_plan_iteration_count_invalid": ("budget", "The execution plan must cover at least two iterations.", "refresh_multi_iteration_execution_plan"),
            "approval_plan_budget_requires_at_least_two": ("budget", "The approval plan budget must cover at least two iterations.", "raise_multi_iteration_approval_plan_budget"),
            "approval_plan_budget_exceeds_execution_plan": ("budget", "The approval plan budget cannot exceed the execution plan budget.", "lower_multi_iteration_approval_plan_budget"),
            "future_multi_iteration_executor_contract_required": ("contract", "The future multi-iteration executor contract is required.", "refresh_multi_iteration_executor_contract"),
            "future_multi_iteration_executor_already_implemented_claim": ("safety", "The future executor contract claims implementation and needs audit.", "audit_multi_iteration_executor_claim"),
            "future_multi_iteration_executor_name_mismatch": ("contract", "The future executor contract name does not match execute_paused_session_automatic_loop_multi_iteration.", "refresh_multi_iteration_executor_contract_name"),
            "multi_iteration_execution_plan_iterations_required": ("execution_plan", "Planned iteration gates are required.", "refresh_multi_iteration_execution_plan_iterations"),
            "multi_iteration_execution_plan_iteration_invalid": ("execution_plan", "A planned iteration gate is malformed.", "refresh_multi_iteration_execution_plan_iterations"),
            "multi_iteration_execution_plan_iteration_gate_not_ready": ("execution_plan", "A planned iteration gate is not ready.", "refresh_multi_iteration_execution_plan_iterations"),
            "execution_plan_has_execution_side_effects": ("safety", "The execution plan reports execution side effects and must be audited.", "audit_multi_iteration_execution_plan_side_effects"),
            "execution_plan_wrote_checkpoint": ("safety", "The execution plan reports checkpoint writes.", "audit_multi_iteration_execution_plan_checkpoint_claim"),
            "execution_plan_recovered_live_callframe": ("safety", "The execution plan reports live callFrame recovery.", "audit_multi_iteration_execution_plan_callframe_claim"),
            "execution_plan_advanced_loop_or_queue": ("safety", "The execution plan reports loop or queue advancement.", "audit_multi_iteration_execution_plan_loop_state"),
            "execution_plan_managed_long_lived_session": ("safety", "The execution plan reports long-lived session management.", "remove_long_lived_session_from_execution_plan"),
            "execution_plan_called_mcp": ("safety", "The execution plan reports MCP usage.", "remove_mcp_from_multi_iteration_execution_plan"),
            "execution_plan_used_mobile_runtime": ("safety", "The execution plan reports mobile runtime usage.", "remove_mobile_runtime_from_multi_iteration_execution_plan"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_approval_plan"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_approval_plan"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_executor_approval_plan"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_executor_approval_plan_blockers"
        if status == "ready_for_review":
            return "review_future_paused_session_automatic_loop_multi_iteration_executor_approval_transaction"
        return "inspect_paused_session_automatic_loop_multi_iteration_executor_approval_plan"



@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutionSpec:
    """Explicit-review-only bounded multi-iteration executor MVP.

    The Step 264 MVP consumes the Step 263 bounded multi-iteration gate plus
    the written transaction journal, delegates at most one reviewed iteration to
    the existing one-iteration loop executor, and then stops for checkpoint
    review. It is intentionally not an automatic multi-iteration daemon, queue
    advancer, live callFrame recovery loop, MCP bridge, or mobile runtime chain.
    """

    bounded_executor_gate: dict[str, Any] = field(default_factory=dict)
    transaction_journal: dict[str, Any] = field(default_factory=dict)
    loop_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_multi_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int | None = None
    requested_iteration_budget: int = 1
    max_iterations: int = 1
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_execution")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecution")
            or context.get("paused-session-automatic-loop-multi-iteration-execution")
            or context.get("execute_paused_session_automatic_loop_multi_iteration")
            or context.get("executePausedSessionAutomaticLoopMultiIteration")
            or context.get("execute_bounded_paused_session_automatic_loop_multi_iteration")
            or context.get("executeBoundedPausedSessionAutomaticLoopMultiIteration")
        )
        gate_container = _first_dict(
            context,
            "paused_session_automatic_loop_multi_iteration_bounded_executor_gate",
            "pausedSessionAutomaticLoopMultiIterationBoundedExecutorGate",
            "paused-session-automatic-loop-multi-iteration-bounded-executor-gate",
            "automatic_loop_multi_iteration_bounded_executor_gate",
            "automaticLoopMultiIterationBoundedExecutorGate",
            "bounded_multi_iteration_executor_gate",
            "boundedMultiIterationExecutorGate",
            "bounded_executor_gate",
            "boundedExecutorGate",
        )
        gate = dict(gate_container.get("gate")) if isinstance(gate_container.get("gate"), dict) else gate_container
        journal_container = _first_dict(
            context,
            "paused_session_automatic_loop_multi_iteration_transaction_journal",
            "pausedSessionAutomaticLoopMultiIterationTransactionJournal",
            "paused-session-automatic-loop-multi-iteration-transaction-journal",
            "paused_session_automatic_loop_multi_iteration_executor_journal",
            "pausedSessionAutomaticLoopMultiIterationExecutorJournal",
            "automatic_loop_multi_iteration_transaction_journal",
            "automaticLoopMultiIterationTransactionJournal",
            "transaction_journal",
            "transactionJournal",
        )
        journal = dict(journal_container.get("journal")) if isinstance(journal_container.get("journal"), dict) else journal_container
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
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
        if not requested and not any((gate, journal, loop_plan)):
            return None
        planned_iterations = gate.get("planned_iterations") if isinstance(gate.get("planned_iterations"), list) else []
        first_planned = next((item for item in planned_iterations if isinstance(item, dict)), {})
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_raw = context.get(
            "selected_step_index",
            context.get(
                "selectedStepIndex",
                context.get("step_index", context.get("stepIndex", first_planned.get("workflow_step_index") or next_iteration.get("workflow_step_index"))),
            ),
        )
        try:
            selected_step_index = int(selected_raw) if selected_raw is not None else None
        except (TypeError, ValueError):
            selected_step_index = None
        budget_source = gate.get("bounded_executor_input") if isinstance(gate.get("bounded_executor_input"), dict) else {}
        max_raw = context.get(
            "max_iterations",
            context.get("maxIterations", context.get("max_automatic_iterations", context.get("maxAutomaticIterations", budget_source.get("max_iterations") or len(planned_iterations) or 1))),
        )
        try:
            requested_budget = int(max_raw)
        except (TypeError, ValueError):
            requested_budget = 1
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_paused_session_automatic_loop_multi_iteration",
            context.get(
                "executePausedSessionAutomaticLoopMultiIteration",
                context.get(
                    "execute_bounded_paused_session_automatic_loop_multi_iteration",
                    context.get("executeBoundedPausedSessionAutomaticLoopMultiIteration", context.get("execute_multi_iteration", context.get("executeMultiIteration", False))),
                ),
            ),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or loop_plan.get("pause_session_id") or workflow.get("pause_session_id") or recovery.get("pause_session_id") or gate.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or loop_plan.get("target_id") or workflow.get("target_id") or recovery.get("target_id") or gate.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or loop_plan.get("reviewer") or gate.get("reviewer")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            bounded_executor_gate=gate,
            transaction_journal=journal,
            loop_plan=loop_plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_multi_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index) if selected_step_index is not None else None,
            requested_iteration_budget=max(1, requested_budget),
            max_iterations=1,
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
class PausedSessionAutomaticLoopMultiIterationExecutionResult:
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


class PausedSessionAutomaticLoopMultiIterationExecutionManager:
    """Execute one reviewed iteration through the multi-iteration gate envelope."""

    def execute(self, page: BrowserPage | None, spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec | None) -> PausedSessionAutomaticLoopMultiIterationExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionAutomaticLoopMultiIterationExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_multi_iteration:
            payload = self._payload(spec, status="not_run", blockers=[])
            return PausedSessionAutomaticLoopMultiIterationExecutionResult(status="not_run", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="not_run", blockers=["review_approval_required"])
            return PausedSessionAutomaticLoopMultiIterationExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        loop_spec = PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=True,
            review_approved=True,
            selected_step_index=self._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )
        result = PausedSessionMultiStepLoopExecutionManager().execute(page, loop_spec)
        inner = result.execution if isinstance(result.execution, dict) else {}
        inner_policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else {}
        if result.status == "executed":
            status = "completed" if spec.requested_iteration_budget <= 1 else "partial"
            blockers_after: list[str] = []
        else:
            status = "failed" if result.status not in {"blocked", "review_required", "ready_for_review"} else result.status
            blockers_after = [result.reason or "automatic_loop_multi_iteration_execution_failed"]
        payload = self._payload(spec, status=status, blockers=blockers_after, inner_result=inner, inner_policy=inner_policy, error=result.error)
        return PausedSessionAutomaticLoopMultiIterationExecutionResult(
            status=status,
            execution=payload,
            side_effect_policy=self._side_effect_policy(inner_policy),
            reason=blockers_after[0] if blockers_after else None,
            error=result.error,
        )

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_execution_request_missing"]
        blockers: list[str] = []
        gate = spec.bounded_executor_gate
        journal = spec.transaction_journal
        if not gate:
            blockers.append("bounded_executor_gate_required")
        elif gate.get("status") != "ready_for_review" or gate.get("bounded_executor_gate_ready_for_review") is not True or gate.get("multi_iteration_bounded_executor_gate_ready_for_review") is not True:
            blockers.append("bounded_executor_gate_not_ready")
        if gate and gate.get("ready_to_execute_now") is True:
            blockers.append("bounded_executor_gate_ready_to_execute_claim_detected")
        if gate and gate.get("automatic_loop_executed") is True:
            blockers.append("bounded_executor_gate_already_executed")
        if gate and gate.get("automatic_multi_iteration_loop") is True:
            blockers.append("bounded_executor_gate_multi_iteration_loop_claim_detected")
        if gate and gate.get("automatic_multi_iteration_execution_allowed_now") is True:
            blockers.append("bounded_executor_gate_execution_allowed_claim_detected")
        if not journal:
            blockers.append("transaction_journal_required")
        elif journal.get("status") != "written" or journal.get("journal_written") is not True:
            blockers.append("transaction_journal_not_written")
        journal_summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
        if journal and (journal.get("automatic_loop_executed") is True or journal.get("automatic_multi_iteration_loop") is True or journal_summary.get("automatic_loop_executed") is True or journal_summary.get("automatic_multi_iteration_loop") is True):
            blockers.append("transaction_journal_already_executed")
        if journal and journal.get("transaction_started") is not True:
            blockers.append("transaction_journal_not_started")
        cls._append_matching_id_blockers(blockers, gate, journal)
        planned_iterations = gate.get("planned_iterations") if isinstance(gate.get("planned_iterations"), list) else []
        if not planned_iterations:
            blockers.append("planned_iterations_required")
        selected_step = cls._selected_step_index(spec)
        matching_planned = [item for item in planned_iterations if isinstance(item, dict) and int(item.get("workflow_step_index") or 0) == selected_step]
        if selected_step < 1:
            blockers.append("selected_step_index_required")
        elif planned_iterations and not matching_planned:
            blockers.append("selected_iteration_not_in_gate")
        for item in matching_planned[:1]:
            if item.get("ready_for_future_executor_review") is not True:
                blockers.append("selected_iteration_not_ready_for_executor_review")
            if item.get("requires_per_iteration_review_gate") is not True:
                blockers.append("per_iteration_review_gate_required")
            if item.get("requires_fresh_live_callframe_before_execution") is not True:
                blockers.append("fresh_live_callframe_per_iteration_required")
            if item.get("requires_checkpoint_after_iteration") is not True:
                blockers.append("per_iteration_checkpoint_gate_required")
            if item.get("requires_stop_after_checkpoint") is not True:
                blockers.append("stop_after_each_checkpoint_required")
        bounded_input = gate.get("bounded_executor_input") if isinstance(gate.get("bounded_executor_input"), dict) else {}
        if bounded_input and bounded_input.get("requires_per_iteration_review") is not True:
            blockers.append("per_iteration_review_gate_required")
        if bounded_input and bounded_input.get("requires_checkpoint_after_each_iteration") is not True:
            blockers.append("per_iteration_checkpoint_gate_required")
        if bounded_input and bounded_input.get("requires_stop_after_each_checkpoint") is not True:
            blockers.append("stop_after_each_checkpoint_required")
        if bounded_input and bounded_input.get("require_fresh_live_callframe") is not True:
            blockers.append("fresh_live_callframe_per_iteration_required")
        if bounded_input and bounded_input.get("requires_retained_attached_session") is not True:
            blockers.append("retained_attached_session_per_iteration_required")
        for key, blocker in (
            ("automatic_queue_advance_allowed", "automatic_queue_advance_claim_detected"),
            ("automatic_loop_advance_allowed", "automatic_loop_advance_claim_detected"),
            ("automatic_live_callframe_recovery_allowed", "automatic_live_callframe_recovery_claim_detected"),
            ("long_lived_session_management_allowed", "long_lived_session_claim_detected"),
        ):
            if bounded_input.get(key) is True:
                blockers.append(blocker)
        if spec.max_iterations != 1:
            blockers.append("multi_iteration_mvp_allows_one_iteration_per_apply")
        blockers.extend(PausedSessionMultiStepLoopExecutionManager._blockers(cls._loop_spec(spec)))
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _append_matching_id_blockers(blockers: list[str], gate: dict[str, Any], journal: dict[str, Any]) -> None:
        for field, blocker in (
            ("transaction_id", "transaction_id_mismatch"),
            ("journal_id", "journal_id_mismatch"),
            ("transaction_preflight_id", "transaction_preflight_id_mismatch"),
            ("approval_record_id", "approval_record_id_mismatch"),
            ("execution_plan_id", "execution_plan_id_mismatch"),
            ("preflight_id", "preflight_id_mismatch"),
            ("policy_id", "policy_id_mismatch"),
        ):
            if gate and journal and gate.get(field) and journal.get(field) and gate.get(field) != journal.get(field):
                blockers.append(blocker)

    @classmethod
    def _loop_spec(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec | None) -> PausedSessionMultiStepLoopExecutionSpec | None:
        if spec is None:
            return None
        return PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=False,
            review_approved=False,
            selected_step_index=cls._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )

    @classmethod
    def _selected_step_index(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec | None) -> int:
        if spec is None:
            return 0
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        loop_spec = cls._loop_spec_without_selected(spec)
        return PausedSessionMultiStepLoopExecutionManager._selected_step_index(loop_spec)

    @staticmethod
    def _loop_spec_without_selected(spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec) -> PausedSessionMultiStepLoopExecutionSpec:
        return PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
        )

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        gate = spec.bounded_executor_gate if spec else {}
        journal = spec.transaction_journal if spec else {}
        inner = inner_result or {}
        policy = inner_policy or {}
        selected_step = cls._selected_step_index(spec)
        requested_budget = spec.requested_iteration_budget if spec else 1
        executed = status in {"partial", "completed"}
        planned_iterations = gate.get("planned_iterations") if isinstance(gate.get("planned_iterations"), list) else []
        selected_planned = next((item for item in planned_iterations if isinstance(item, dict) and int(item.get("workflow_step_index") or 0) == selected_step), {})
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-execution-result.v1",
            "status": status,
            "transaction_id": journal.get("transaction_id") or gate.get("transaction_id"),
            "journal_id": journal.get("journal_id") or gate.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id") or gate.get("transaction_preflight_id"),
            "approval_record_id": journal.get("approval_record_id") or gate.get("approval_record_id"),
            "execution_plan_id": journal.get("execution_plan_id") or gate.get("execution_plan_id"),
            "preflight_id": journal.get("preflight_id") or gate.get("preflight_id"),
            "policy_id": journal.get("policy_id") or gate.get("policy_id"),
            "gate_status": gate.get("status"),
            "loop_id": gate.get("loop_id") or (spec.loop_plan.get("loop_id") if spec else None),
            "workflow_id": gate.get("workflow_id") or (spec.multi_step_workflow.get("workflow_id") if spec else None),
            "pause_session_id": spec.pause_session_id if spec else gate.get("pause_session_id"),
            "target_id": spec.target_id if spec else gate.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "execute_multi_iteration_requested": bool(spec and spec.execute_multi_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "requested_iteration_budget": requested_budget,
            "max_iterations_per_apply": 1,
            "selected_step_index": selected_step or None,
            "executed_iteration_count": 1 if executed else 0,
            "iteration_results": [
                {
                    "iteration_index": selected_planned.get("iteration_index") or 1,
                    "source_iteration_index": selected_planned.get("source_iteration_index"),
                    "workflow_step_index": selected_step or selected_planned.get("workflow_step_index"),
                    "method": selected_planned.get("method") or inner.get("selected_method"),
                    "fingerprint": selected_planned.get("fingerprint"),
                    "reviewed_before_execution": bool(spec and spec.review_approved),
                    "fresh_live_callframe_verified": bool(spec and spec.live_callframe_recovery.get("live_callframe_recovered")),
                    "executed": executed,
                    "checkpoint_required": executed,
                    "stop_after_checkpoint": True,
                    "delegated_executor_result": inner,
                }
            ] if inner or executed else [],
            "delegated_executor_artifact": "workspace/paused-session-multi-step-loop-execution.json",
            "delegated_executor_status": inner.get("status"),
            "checkpoint_required": executed,
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_loop_plan": "workspace/paused-session-multi-step-loop-plan.json",
            "expected_followup_multi_iteration_gate": "workspace/paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json",
            "automatic_multi_iteration_execution_mvp": True,
            "automatic_multi_iteration_executor_implemented": True,
            "automatic_multi_iteration_loop": False,
            "automatic_loop_executed": executed,
            "automatic_loop_one_iteration_executed": executed,
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_session_managed": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, inner=inner, requested_budget=requested_budget),
            "side_effect_policy": cls._side_effect_policy(policy),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        policy = PausedSessionAutomaticLoopExecutionManager._side_effect_policy(inner_policy)
        policy.update(
            {
                "automatic_loop_multi_iteration_executor": True,
                "automatic_multi_iteration_execution_mvp": True,
                "automatic_multi_iteration_executor_implemented": True,
                "automatic_multi_iteration_loop": False,
                "automatic_loop_one_iteration_executed": bool(policy.get("multi_step_loop_iteration_executed")),
                "bounded_one_iteration_only": True,
                "checkpoint_required_after_iteration": bool(policy.get("multi_step_loop_iteration_executed")),
                "automatic_live_callframe_recovery": False,
                "automatic_queue_advance": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            }
        )
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_execution_request_missing": ("request", "No automatic-loop multi-iteration execution request was provided.", "request_paused_session_automatic_loop_multi_iteration_execution"),
            "bounded_executor_gate_required": ("gate", "A ready multi-iteration bounded executor gate descriptor is required.", "review_paused_session_automatic_loop_multi_iteration_bounded_executor_gate"),
            "bounded_executor_gate_not_ready": ("gate", "The multi-iteration bounded executor gate is not ready for review.", "resolve_multi_iteration_bounded_executor_gate_blockers"),
            "bounded_executor_gate_ready_to_execute_claim_detected": ("safety", "The gate unexpectedly claims ready_to_execute_now; execution must stay explicit.", "audit_multi_iteration_bounded_gate_ready_claim"),
            "bounded_executor_gate_already_executed": ("gate", "The gate claims an automatic loop already executed.", "audit_multi_iteration_execution_state"),
            "bounded_executor_gate_multi_iteration_loop_claim_detected": ("safety", "The gate claims automatic multi-iteration looping, which remains disabled.", "audit_multi_iteration_loop_claim"),
            "bounded_executor_gate_execution_allowed_claim_detected": ("safety", "The gate claims automatic multi-iteration execution is already allowed.", "audit_multi_iteration_execution_allowance"),
            "transaction_journal_required": ("journal", "A written multi-iteration transaction journal is required.", "record_paused_session_automatic_loop_multi_iteration_transaction_journal"),
            "transaction_journal_not_written": ("journal", "The multi-iteration transaction journal has not been written.", "write_reviewed_multi_iteration_transaction_journal"),
            "transaction_journal_not_started": ("journal", "The multi-iteration transaction journal has not started the audit transaction.", "refresh_multi_iteration_transaction_journal"),
            "transaction_journal_already_executed": ("journal", "The transaction journal claims automatic loop execution already happened.", "audit_multi_iteration_transaction_journal"),
            "transaction_id_mismatch": ("transaction", "Gate and journal transaction ids do not match.", "refresh_matching_multi_iteration_gate_and_journal"),
            "journal_id_mismatch": ("journal", "Gate and journal ids do not match.", "refresh_matching_multi_iteration_gate_and_journal"),
            "transaction_preflight_id_mismatch": ("transaction", "Gate and journal transaction preflight ids do not match.", "refresh_matching_multi_iteration_transaction_preflight"),
            "approval_record_id_mismatch": ("approval", "Gate and journal approval record ids do not match.", "refresh_matching_multi_iteration_approval_record"),
            "execution_plan_id_mismatch": ("execution_plan", "Gate and journal execution plan ids do not match.", "refresh_matching_multi_iteration_execution_plan"),
            "preflight_id_mismatch": ("preflight", "Gate and journal executor preflight ids do not match.", "refresh_matching_multi_iteration_executor_preflight"),
            "policy_id_mismatch": ("policy", "Gate and journal policy ids do not match.", "refresh_matching_multi_iteration_policy"),
            "planned_iterations_required": ("gate", "The bounded gate must include planned iteration entries.", "refresh_multi_iteration_bounded_gate_planned_iterations"),
            "selected_step_index_required": ("selection", "A selected workflow step index is required.", "select_reviewed_multi_iteration_step"),
            "selected_iteration_not_in_gate": ("selection", "The selected workflow step is not present in the bounded gate planned iterations.", "select_gate_planned_iteration"),
            "selected_iteration_not_ready_for_executor_review": ("review", "The selected iteration is not ready for executor review.", "refresh_selected_iteration_review_gate"),
            "per_iteration_review_gate_required": ("review", "Every executed iteration must preserve explicit review gates.", "restore_per_iteration_review_gate"),
            "fresh_live_callframe_per_iteration_required": ("callframe", "Every executed iteration must require fresh live callFrame evidence.", "recover_fresh_live_callframe_before_iteration"),
            "per_iteration_checkpoint_gate_required": ("checkpoint", "Every executed iteration must require a checkpoint afterward.", "restore_per_iteration_checkpoint_gate"),
            "stop_after_each_checkpoint_required": ("policy", "The executor must stop after each checkpoint.", "restore_stop_after_checkpoint_policy"),
            "retained_attached_session_per_iteration_required": ("session", "Every executed iteration requires a retained attached session.", "retain_attached_session_before_execution"),
            "automatic_queue_advance_claim_detected": ("safety", "Automatic queue advance is outside the MVP boundary.", "disable_automatic_queue_advance"),
            "automatic_loop_advance_claim_detected": ("safety", "Automatic loop advance is outside the MVP boundary.", "disable_automatic_loop_advance"),
            "automatic_live_callframe_recovery_claim_detected": ("safety", "Automatic live callFrame recovery is outside the MVP boundary.", "disable_automatic_live_callframe_recovery"),
            "long_lived_session_claim_detected": ("safety", "Long-lived session management is outside the MVP boundary.", "disable_long_lived_session_management"),
            "multi_iteration_mvp_allows_one_iteration_per_apply": ("budget", "The Step 264 MVP executes at most one reviewed iteration per apply.", "run_next_iteration_after_checkpoint_review"),
            "review_approval_required": ("review", "Executing a bounded multi-iteration step requires explicit review approval.", "approve_paused_session_automatic_loop_multi_iteration_execution"),
            "automatic_loop_multi_iteration_execution_failed": ("runtime", "The delegated one-iteration loop executor failed.", "inspect_paused_session_automatic_loop_multi_iteration_execution"),
        }
        fallback = PausedSessionMultiStepLoopExecutionManager._blocker_details(blockers)
        fallback_by_code = {item.get("code"): item for item in fallback}
        mapped: list[dict[str, Any]] = []
        for blocker in blockers:
            if blocker in catalog:
                category, explanation, next_action = catalog[blocker]
                mapped.append({"code": blocker, "category": category, "explanation": explanation, "next_action": next_action})
            else:
                mapped.append(fallback_by_code.get(blocker, {"code": blocker, "category": "unknown", "explanation": blocker, "next_action": "inspect_paused_session_automatic_loop_multi_iteration_execution"}))
        return mapped

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], inner: dict[str, Any], requested_budget: int) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_execution_blockers"
        if status in {"not_run", "review_required"}:
            return "approve_paused_session_automatic_loop_multi_iteration_execution"
        if status == "partial" and inner.get("paused_event_captured"):
            return "checkpoint_multi_iteration_step_before_next_review"
        if status == "partial":
            return "review_next_paused_session_automatic_loop_multi_iteration_step"
        if status == "completed" and inner.get("paused_event_captured"):
            return "checkpoint_completed_multi_iteration_execution"
        if status == "completed":
            return "review_paused_session_automatic_loop_multi_iteration_execution_result"
        return "inspect_paused_session_automatic_loop_multi_iteration_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationFollowupCheckpointSpec:
    """Read-only handoff after the bounded multi-iteration executor MVP.

    This descriptor consumes the Step 264 execution result plus optional
    continuation checkpoint / next loop plan evidence. It never writes
    checkpoints, recovers live callFrames, sends CDP commands, advances queues,
    executes another iteration, manages long-lived sessions, calls MCP, or
    touches mobile runtime chains.
    """

    automatic_loop_multi_iteration_execution_result: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationFollowupCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_followup_checkpoint")
            or context.get("pausedSessionAutomaticLoopMultiIterationFollowupCheckpoint")
            or context.get("paused-session-automatic-loop-multi-iteration-followup-checkpoint")
            or context.get("paused_session_automatic_loop_multi_iteration_execution_followup")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecutionFollowup")
            or context.get("checkpoint_paused_session_automatic_loop_multi_iteration_execution")
            or context.get("checkpointPausedSessionAutomaticLoopMultiIterationExecution")
        )
        execution_container = _first_dict(
            context,
            "paused_session_automatic_loop_multi_iteration_execution_result",
            "pausedSessionAutomaticLoopMultiIterationExecutionResult",
            "paused-session-automatic-loop-multi-iteration-execution-result",
            "paused_session_automatic_loop_multi_iteration_execution",
            "pausedSessionAutomaticLoopMultiIterationExecution",
            "paused-session-automatic-loop-multi-iteration-execution",
            "automatic_loop_multi_iteration_execution_result",
            "automaticLoopMultiIterationExecutionResult",
            "automatic_loop_multi_iteration_execution",
            "automaticLoopMultiIterationExecution",
            "execute_paused_session_automatic_loop_multi_iteration",
            "executePausedSessionAutomaticLoopMultiIteration",
        )
        execution = dict(execution_container.get("execution")) if isinstance(execution_container.get("execution"), dict) else execution_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        if not requested and not execution:
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or execution.get("reviewer") or loop_plan.get("reviewer")
        return cls(
            automatic_loop_multi_iteration_execution_result=execution,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationFollowupCheckpointResult:
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


class PausedSessionAutomaticLoopMultiIterationFollowupCheckpointManager:
    """Review-only handoff descriptor after Step 264 multi-iteration MVP execution."""

    def review(self, spec: PausedSessionAutomaticLoopMultiIterationFollowupCheckpointSpec | None) -> PausedSessionAutomaticLoopMultiIterationFollowupCheckpointResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopMultiIterationFollowupCheckpointResult(status=status, checkpoint=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationFollowupCheckpointSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_multi_iteration_followup_checkpoint_request_missing"]
        blockers: list[str] = []
        execution = spec.automatic_loop_multi_iteration_execution_result
        checkpoint = spec.continuation_checkpoint
        if not execution:
            blockers.append("automatic_loop_multi_iteration_execution_result_required")
            return blockers
        execution_status = str(execution.get("status") or "")
        policy = execution.get("side_effect_policy") if isinstance(execution.get("side_effect_policy"), dict) else {}
        if execution_status in {"blocked", "failed", "failure", "error", "timed_out", "unsupported"}:
            blockers.append("automatic_loop_multi_iteration_execution_result_blocked")
        elif execution_status not in {"partial", "completed"} or execution.get("automatic_loop_executed") is not True:
            blockers.append("automatic_loop_multi_iteration_execution_not_executed")
        if int(execution.get("executed_iteration_count") or 0) < 1:
            blockers.append("automatic_loop_multi_iteration_execution_not_executed")
        if int(execution.get("executed_iteration_count") or 0) > int(execution.get("max_iterations_per_apply") or 1):
            blockers.append("multi_iteration_executor_exceeded_one_iteration")
        if execution.get("checkpoint_required") is True:
            if not checkpoint:
                blockers.append("automatic_loop_multi_iteration_followup_checkpoint_required")
            elif not PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint):
                blockers.append("automatic_loop_multi_iteration_followup_checkpoint_not_ready")
        if execution.get("automatic_multi_iteration_loop") is True or policy.get("automatic_multi_iteration_loop") is True:
            blockers.append("automatic_multi_iteration_loop_claim_detected")
        if execution.get("loop_advanced") is True or policy.get("loop_advanced") is True:
            blockers.append("loop_advance_claim_detected")
        if execution.get("queue_advanced") is True or policy.get("queue_advanced") is True:
            blockers.append("queue_advance_claim_detected")
        if execution.get("long_lived_session_managed") is True or policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("long_lived_session_claim_detected")
        if policy.get("automatic_live_callframe_recovery") is True:
            blockers.append("automatic_live_callframe_recovery_claim_detected")
        if policy.get("calls_mcp") is True:
            blockers.append("mcp_call_claim_detected")
        if policy.get("mobile_runtime_used") is True:
            blockers.append("mobile_runtime_claim_detected")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopMultiIterationFollowupCheckpointSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        execution = spec.automatic_loop_multi_iteration_execution_result if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        loop_plan = spec.next_loop_plan if spec else {}
        checkpoint_ready = PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint)
        loop_plan_ready = PausedSessionAutomaticLoopFollowupCheckpointManager._loop_plan_ready(loop_plan)
        next_iteration_reviewable = bool(PausedSessionAutomaticLoopFollowupCheckpointManager._dict_value(loop_plan, "readiness").get("next_loop_iteration_reviewable")) if loop_plan else False
        next_iteration_available = bool(PausedSessionAutomaticLoopFollowupCheckpointManager._dict_value(loop_plan, "next_iteration").get("available")) if loop_plan else False
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-followup-checkpoint.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "transaction_id": execution.get("transaction_id"),
            "journal_id": execution.get("journal_id"),
            "loop_id": execution.get("loop_id") or loop_plan.get("loop_id"),
            "workflow_id": execution.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": execution.get("pause_session_id") or checkpoint.get("pause_session_id") or loop_plan.get("pause_session_id"),
            "target_id": execution.get("target_id") or checkpoint.get("target_id") or loop_plan.get("target_id"),
            "source_statuses": {
                "automatic_loop_multi_iteration_execution_result": execution.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "next_loop_plan": loop_plan.get("status"),
            },
            "execution_summary": {
                "automatic_multi_iteration_execution_mvp": bool(execution.get("automatic_multi_iteration_execution_mvp")),
                "automatic_multi_iteration_executor_implemented": bool(execution.get("automatic_multi_iteration_executor_implemented")),
                "automatic_loop_executed": bool(execution.get("automatic_loop_executed")),
                "automatic_loop_one_iteration_executed": bool(execution.get("automatic_loop_one_iteration_executed")),
                "requested_iteration_budget": execution.get("requested_iteration_budget", 0),
                "max_iterations_per_apply": execution.get("max_iterations_per_apply", 1),
                "executed_iteration_count": execution.get("executed_iteration_count", 0),
                "checkpoint_required": bool(execution.get("checkpoint_required")),
                "partial_execution": execution.get("status") == "partial",
                "completed_execution": execution.get("status") == "completed",
                "automatic_multi_iteration_loop": bool(execution.get("automatic_multi_iteration_loop")),
                "loop_advanced": bool(execution.get("loop_advanced")),
                "queue_advanced": bool(execution.get("queue_advanced")),
                "long_lived_session_managed": bool(execution.get("long_lived_session_managed")),
            },
            "checkpoint_review": {
                "checkpoint_present": bool(checkpoint),
                "checkpoint_ready": checkpoint_ready,
                "checkpoint_status": checkpoint.get("status"),
                "callframe_count": checkpoint.get("callframe_count", 0),
                "continuation_ready_for_next_action": bool(checkpoint.get("continuation_ready_for_next_action")),
                "continuation_ready_for_next_capture_plan": bool(checkpoint.get("continuation_ready_for_next_capture_plan")),
                "live_callframe_recovery_ready": bool(checkpoint.get("live_callframe_recovery_ready")),
                "manual_checkpoint_required": bool(checkpoint.get("manual_checkpoint_required")),
            },
            "next_loop_review": {
                "next_loop_plan_present": bool(loop_plan),
                "next_loop_plan_ready": loop_plan_ready,
                "next_iteration_reviewable": next_iteration_reviewable,
                "next_iteration_available": next_iteration_available,
                "requires_review_approval": True,
                "requires_fresh_live_callframe": True,
                "requires_new_multi_iteration_execution_review": True,
                "would_execute_next_iteration": False,
            },
            "required_followups": cls._required_followups(checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers=blockers, checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _required_followups(*, checkpoint_ready: bool, loop_plan_ready: bool) -> list[dict[str, Any]]:
        if not checkpoint_ready:
            return [{"order": 1, "action": "checkpoint_paused_session_automatic_loop_multi_iteration_execution", "artifact": "workspace/paused-session-cross-process-continuation-checkpoint.json", "automatic": False}]
        if not loop_plan_ready:
            return [{"order": 1, "action": "plan_next_paused_session_loop_iteration_after_multi_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False}]
        return [{"order": 1, "action": "review_next_paused_session_automatic_loop_multi_iteration_step", "artifact": "workspace/paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json", "automatic": False}]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        policy = PausedSessionAutomaticLoopFollowupCheckpointManager._side_effect_policy()
        policy.update({
            "automatic_loop_multi_iteration_followup_checkpoint": True,
            "would_execute_next_iteration": False,
            "automatic_multi_iteration_loop": False,
            "automatic_live_callframe_recovery": False,
            "automatic_queue_advance": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        })
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_followup_checkpoint_request_missing": ("request", "No automatic-loop multi-iteration follow-up checkpoint review request was provided.", "request_paused_session_automatic_loop_multi_iteration_followup_checkpoint"),
            "automatic_loop_multi_iteration_execution_result_required": ("execution", "The Step 264 bounded multi-iteration execution result is required.", "provide_paused_session_automatic_loop_multi_iteration_execution_result"),
            "automatic_loop_multi_iteration_execution_result_blocked": ("execution", "The multi-iteration execution result is blocked, failed, unsupported, or timed out.", "inspect_paused_session_automatic_loop_multi_iteration_execution"),
            "automatic_loop_multi_iteration_execution_not_executed": ("execution", "The multi-iteration execution result has not executed a reviewed iteration yet.", "approve_paused_session_automatic_loop_multi_iteration_execution"),
            "multi_iteration_executor_exceeded_one_iteration": ("budget", "The Step 264 MVP must execute at most one reviewed iteration per apply.", "audit_paused_session_automatic_loop_multi_iteration_execution_result"),
            "automatic_loop_multi_iteration_followup_checkpoint_required": ("checkpoint", "Executed multi-iteration MVP steps require a continuation checkpoint before the next review.", "checkpoint_paused_session_automatic_loop_multi_iteration_execution"),
            "automatic_loop_multi_iteration_followup_checkpoint_not_ready": ("checkpoint", "The supplied continuation checkpoint is not ready for next review.", "recover_or_refresh_continuation_checkpoint"),
            "automatic_multi_iteration_loop_claim_detected": ("safety", "The execution result claims automatic multi-iteration looping, which remains disabled.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "loop_advance_claim_detected": ("safety", "The execution result claims loop advancement, which is outside the MVP boundary.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "queue_advance_claim_detected": ("safety", "The execution result claims queue advancement, which is outside the MVP boundary.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "long_lived_session_claim_detected": ("safety", "The execution result claims long-lived session management, which is outside the MVP boundary.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "automatic_live_callframe_recovery_claim_detected": ("safety", "The execution result claims automatic live callFrame recovery, which is outside the MVP boundary.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "mcp_call_claim_detected": ("safety", "The execution result claims MCP calls, which are disallowed for native automatic-loop follow-up.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
            "mobile_runtime_claim_detected": ("safety", "The execution result claims mobile runtime use, which is deferred.", "audit_automatic_loop_multi_iteration_execution_side_effects"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, blockers: list[str], checkpoint_ready: bool, loop_plan_ready: bool) -> str:
        if "automatic_loop_multi_iteration_followup_checkpoint_required" in blockers:
            return "checkpoint_paused_session_automatic_loop_multi_iteration_execution"
        if "automatic_loop_multi_iteration_followup_checkpoint_not_ready" in blockers:
            return "recover_or_refresh_continuation_checkpoint"
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint_blockers"
        if checkpoint_ready and not loop_plan_ready:
            return "plan_next_paused_session_loop_iteration_after_multi_iteration"
        if checkpoint_ready and loop_plan_ready:
            return "review_next_paused_session_automatic_loop_multi_iteration_step"
        return "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationNextStepPlanSpec:
    """Read-only next-step review descriptor after Step 265 follow-up.

    This descriptor consumes the multi-iteration execution follow-up checkpoint,
    latest continuation checkpoint, next loop plan, and optional fresh live
    callFrame evidence. It prepares the next explicit reviewed call into the
    Step 264 bounded multi-iteration executor MVP without executing anything.
    """

    followup_checkpoint: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationNextStepPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_next_step_plan")
            or context.get("pausedSessionAutomaticLoopMultiIterationNextStepPlan")
            or context.get("paused-session-automatic-loop-multi-iteration-next-step-plan")
            or context.get("plan_next_paused_session_automatic_loop_multi_iteration_step")
            or context.get("planNextPausedSessionAutomaticLoopMultiIterationStep")
            or context.get("review_next_paused_session_automatic_loop_multi_iteration_step")
            or context.get("reviewNextPausedSessionAutomaticLoopMultiIterationStep")
        )
        followup_container = _first_dict(
            context,
            "paused_session_automatic_loop_multi_iteration_followup_checkpoint",
            "pausedSessionAutomaticLoopMultiIterationFollowupCheckpoint",
            "paused-session-automatic-loop-multi-iteration-followup-checkpoint",
            "paused_session_automatic_loop_multi_iteration_execution_followup",
            "pausedSessionAutomaticLoopMultiIterationExecutionFollowup",
            "checkpoint_paused_session_automatic_loop_multi_iteration_execution",
            "checkpointPausedSessionAutomaticLoopMultiIterationExecution",
            "automatic_loop_multi_iteration_followup_checkpoint",
            "automaticLoopMultiIterationFollowupCheckpoint",
        )
        followup = dict(followup_container.get("checkpoint")) if isinstance(followup_container.get("checkpoint"), dict) else followup_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        if not requested and not followup:
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or followup.get("reviewer") or loop_plan.get("reviewer")
        return cls(
            followup_checkpoint=followup,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            live_callframe_recovery=recovery,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationNextStepPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "plan": self.plan, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationNextStepPlanManager:
    """Review-only next-step descriptor after Step 265 multi-iteration handoff."""

    _BLOCKER_TRANSLATION = {
        "automatic_loop_next_iteration_plan_request_missing": "automatic_loop_multi_iteration_next_step_plan_request_missing",
        "automatic_loop_followup_checkpoint_required": "automatic_loop_multi_iteration_followup_checkpoint_required",
        "automatic_loop_followup_checkpoint_blocked": "automatic_loop_multi_iteration_followup_checkpoint_blocked",
        "automatic_loop_followup_checkpoint_not_ready": "automatic_loop_multi_iteration_followup_checkpoint_not_ready",
        "automatic_loop_followup_checkpoint_not_ready_for_next_iteration": "automatic_loop_multi_iteration_followup_checkpoint_not_ready_for_next_step",
    }

    def plan(self, spec: PausedSessionAutomaticLoopMultiIterationNextStepPlanSpec | None) -> PausedSessionAutomaticLoopMultiIterationNextStepPlanResult:
        if spec is None:
            policy = self._side_effect_policy(PausedSessionAutomaticLoopNextIterationPlanManager._side_effect_policy())
            payload = {
                "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-next-step-plan.v1",
                "status": "blocked",
                "ready_for_review": False,
                "multi_iteration_next_step_plan": True,
                "blockers": ["automatic_loop_multi_iteration_next_step_plan_request_missing"],
                "blocker_details": self._blocker_details(["automatic_loop_multi_iteration_next_step_plan_request_missing"]),
                "next_action": "request_paused_session_automatic_loop_multi_iteration_next_step_plan",
                "side_effect_policy": policy,
            }
            return PausedSessionAutomaticLoopMultiIterationNextStepPlanResult(status="blocked", plan=payload, side_effect_policy=policy, reason="automatic_loop_multi_iteration_next_step_plan_request_missing")
        base_spec = PausedSessionAutomaticLoopNextIterationPlanSpec(
            followup_checkpoint=spec.followup_checkpoint,
            continuation_checkpoint=spec.continuation_checkpoint,
            next_loop_plan=spec.next_loop_plan,
            live_callframe_recovery=spec.live_callframe_recovery,
            reviewer=spec.reviewer,
        )
        base = PausedSessionAutomaticLoopNextIterationPlanManager().plan(base_spec)
        payload = dict(base.plan)
        translated_blockers = [self._BLOCKER_TRANSLATION.get(str(item), str(item)) for item in payload.get("blockers", [])]
        policy = self._side_effect_policy(base.side_effect_policy)
        payload.update(
            {
                "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-next-step-plan.v1",
                "multi_iteration_next_step_plan": True,
                "source_followup_artifact": "workspace/paused-session-automatic-loop-multi-iteration-followup-checkpoint.json",
                "target_execution_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
                "blockers": translated_blockers,
                "blocker_details": self._blocker_details(translated_blockers),
                "reason": translated_blockers[0] if translated_blockers else None,
                "next_action": self._next_action(translated_blockers),
                "side_effect_policy": policy,
            }
        )
        statuses = payload.get("source_statuses") if isinstance(payload.get("source_statuses"), dict) else {}
        statuses["automatic_loop_multi_iteration_followup_checkpoint"] = statuses.pop("automatic_loop_followup_checkpoint", spec.followup_checkpoint.get("status"))
        payload["source_statuses"] = statuses
        checkpoint_review = payload.get("checkpoint_review") if isinstance(payload.get("checkpoint_review"), dict) else {}
        checkpoint_review["multi_iteration_followup_checkpoint_ready"] = checkpoint_review.pop("followup_checkpoint_ready", False)
        payload["checkpoint_review"] = checkpoint_review
        execution_review_gates = payload.get("execution_review_gates") if isinstance(payload.get("execution_review_gates"), dict) else {}
        execution_review_gates.update(
            {
                "requires_ready_multi_iteration_followup_checkpoint": True,
                "requires_new_multi_iteration_execution_review": True,
                "requires_step264_executor_mvp": True,
                "bounded_one_iteration_only": True,
                "automatic_multi_iteration_loop": False,
                "automatic_queue_advance": False,
                "long_lived_cross_process_session": False,
            }
        )
        payload["execution_review_gates"] = execution_review_gates
        expected = payload.get("expected_executor") if isinstance(payload.get("expected_executor"), dict) else {}
        expected.update(
            {
                "name": "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": True,
                "step264_executor_mvp": True,
                "bounded_one_iteration_only": True,
                "future_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
                "delegates_to": "workspace/paused-session-multi-step-loop-execution.json",
            }
        )
        payload["expected_executor"] = expected
        next_iteration = payload.get("next_iteration") if isinstance(payload.get("next_iteration"), dict) else {}
        next_iteration.update(
            {
                "requires_new_multi_iteration_execution_review": True,
                "would_execute_next_iteration": False,
                "would_execute_multi_iteration": False,
                "automatic_multi_iteration_loop": False,
            }
        )
        payload["next_iteration"] = next_iteration
        status = "ready_for_review" if not translated_blockers else "blocked"
        payload["status"] = status
        payload["ready_for_review"] = status == "ready_for_review"
        return PausedSessionAutomaticLoopMultiIterationNextStepPlanResult(status=status, plan=payload, side_effect_policy=policy, reason=payload.get("reason"))

    @staticmethod
    def _side_effect_policy(base_policy: dict[str, Any]) -> dict[str, Any]:
        policy = dict(base_policy)
        policy.update(
            {
                "multi_iteration_next_step_plan_only": True,
                "next_iteration_plan_only": True,
                "would_execute_next_iteration": False,
                "would_execute_multi_iteration": False,
                "automatic_loop_executed": False,
                "automatic_loop_next_iteration_executed": False,
                "automatic_loop_multi_iteration_executed": False,
                "automatic_multi_iteration_loop": False,
                "automatic_queue_advance": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            }
        )
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_multi_iteration_next_step_plan_request_missing": ("request", "No multi-iteration next-step plan request was provided.", "request_paused_session_automatic_loop_multi_iteration_next_step_plan"),
            "automatic_loop_multi_iteration_followup_checkpoint_required": ("checkpoint", "A ready multi-iteration follow-up checkpoint descriptor is required before planning the next step.", "review_paused_session_automatic_loop_multi_iteration_followup_checkpoint"),
            "automatic_loop_multi_iteration_followup_checkpoint_blocked": ("checkpoint", "The multi-iteration follow-up checkpoint descriptor is blocked or failed.", "inspect_paused_session_automatic_loop_multi_iteration_followup_checkpoint_blockers"),
            "automatic_loop_multi_iteration_followup_checkpoint_not_ready": ("checkpoint", "The multi-iteration follow-up checkpoint descriptor is not ready for review.", "refresh_paused_session_automatic_loop_multi_iteration_followup_checkpoint"),
            "automatic_loop_multi_iteration_followup_checkpoint_not_ready_for_next_step": ("checkpoint", "The multi-iteration follow-up descriptor has not proven checkpoint and next-loop readiness.", "provide_ready_multi_iteration_checkpoint_and_loop_plan"),
            "continuation_checkpoint_required": ("checkpoint", "A continuation checkpoint is required before the next multi-iteration step review.", "checkpoint_paused_session_automatic_loop_multi_iteration_execution"),
            "continuation_checkpoint_not_ready": ("checkpoint", "The continuation checkpoint is not ready for next action review.", "recover_or_refresh_continuation_checkpoint"),
            "next_loop_plan_required": ("loop_plan", "A next loop plan is required before the next multi-iteration step review.", "plan_next_paused_session_loop_iteration_after_multi_iteration"),
            "next_loop_plan_not_ready": ("loop_plan", "The next loop plan is not ready for review.", "refresh_next_paused_session_loop_plan"),
            "next_loop_iteration_not_reviewable": ("loop_plan", "The next loop plan does not expose a reviewable next iteration.", "refresh_loop_plan_with_reviewable_next_iteration"),
            "fresh_live_callframe_recovery_required": ("callframe", "A fresh live callFrame recovery proof is required before execution review.", "recover_live_callframe_from_captured_pause"),
            "followup_checkpoint_wrote_checkpoint": ("safety", "The follow-up descriptor unexpectedly claims checkpoint writes.", "audit_multi_iteration_next_step_side_effects"),
            "followup_checkpoint_sent_cdp": ("safety", "The follow-up descriptor unexpectedly claims CDP commands.", "audit_multi_iteration_next_step_side_effects"),
            "followup_checkpoint_captured_event": ("safety", "The follow-up descriptor unexpectedly claims paused-event capture.", "audit_multi_iteration_next_step_side_effects"),
            "followup_checkpoint_advanced_loop_or_queue": ("safety", "The follow-up descriptor unexpectedly claims loop or queue advancement.", "audit_multi_iteration_next_step_side_effects"),
            "mcp_call_claim_detected": ("safety", "The follow-up descriptor claims MCP calls, which are disallowed.", "audit_multi_iteration_next_step_side_effects"),
            "mobile_runtime_claim_detected": ("safety", "The follow-up descriptor claims mobile runtime use, which is deferred.", "audit_multi_iteration_next_step_side_effects"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_next_step_plan"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_next_step_plan"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_multi_iteration_next_step_plan"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if "automatic_loop_multi_iteration_followup_checkpoint_required" in blockers or "automatic_loop_multi_iteration_followup_checkpoint_not_ready" in blockers:
            return "review_paused_session_automatic_loop_multi_iteration_followup_checkpoint"
        if "continuation_checkpoint_required" in blockers or "continuation_checkpoint_not_ready" in blockers:
            return "checkpoint_paused_session_automatic_loop_multi_iteration_execution"
        if "next_loop_plan_required" in blockers or "next_loop_plan_not_ready" in blockers or "next_loop_iteration_not_reviewable" in blockers:
            return "plan_next_paused_session_loop_iteration_after_multi_iteration"
        if "fresh_live_callframe_recovery_required" in blockers:
            return "recover_live_callframe_from_captured_pause"
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_next_step_plan_blockers"
        return "review_paused_session_automatic_loop_multi_iteration_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightSpec:
    """Read-only Step 267 executor-input preflight after Step 266.

    This descriptor consumes the Step 266 next-step plan plus the actual Step 264
    executor inputs and verifies that the next explicit reviewed Step 264 call can
    enter execution review. It never delegates to the executor, sends CDP, captures
    events, writes checkpoints, recovers callFrames, advances queues / loops,
    manages long-lived sessions, calls MCP, or touches mobile runtime chains.
    """

    next_step_plan: dict[str, Any] = field(default_factory=dict)
    execution_spec: PausedSessionAutomaticLoopMultiIterationExecutionSpec = field(default_factory=PausedSessionAutomaticLoopMultiIterationExecutionSpec)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_multi_iteration_executor_input_preflight")
            or context.get("pausedSessionAutomaticLoopMultiIterationExecutorInputPreflight")
            or context.get("paused-session-automatic-loop-multi-iteration-executor-input-preflight")
            or context.get("preflight_paused_session_automatic_loop_multi_iteration_executor_input")
            or context.get("preflightPausedSessionAutomaticLoopMultiIterationExecutorInput")
            or context.get("review_next_paused_session_automatic_loop_multi_iteration_executor_input")
            or context.get("reviewNextPausedSessionAutomaticLoopMultiIterationExecutorInput")
        )
        plan_container = _first_dict(
            context,
            "paused_session_automatic_loop_multi_iteration_next_step_plan",
            "pausedSessionAutomaticLoopMultiIterationNextStepPlan",
            "paused-session-automatic-loop-multi-iteration-next-step-plan",
            "plan_next_paused_session_automatic_loop_multi_iteration_step",
            "planNextPausedSessionAutomaticLoopMultiIterationStep",
            "review_next_paused_session_automatic_loop_multi_iteration_step",
            "reviewNextPausedSessionAutomaticLoopMultiIterationStep",
            "automatic_loop_multi_iteration_next_step_plan",
            "automaticLoopMultiIterationNextStepPlan",
            "next_step_plan",
            "nextStepPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        if not requested and not plan:
            return None
        execution_context = dict(context)
        execution_context["paused_session_automatic_loop_multi_iteration_execution"] = True
        execution_context["execute_paused_session_automatic_loop_multi_iteration"] = False
        execution_context["execute_multi_iteration"] = False
        execution_context["review_approved"] = False
        execution_spec = PausedSessionAutomaticLoopMultiIterationExecutionSpec.from_context(execution_context) or PausedSessionAutomaticLoopMultiIterationExecutionSpec()
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or plan.get("reviewer") or execution_spec.reviewer
        return cls(next_step_plan=plan, execution_spec=execution_spec, reviewer=str(reviewer).strip() if reviewer else None)


@dataclass(slots=True)
class PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "preflight": self.preflight, "side_effect_policy": self.side_effect_policy, "reason": self.reason}


class PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightManager:
    """Read-only input gate between Step 266 and the next reviewed Step 264 call."""

    def review(self, spec: PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightSpec | None) -> PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        policy = self._side_effect_policy()
        payload = self._payload(spec, status=status, blockers=blockers, policy=policy)
        return PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightResult(status=status, preflight=payload, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightSpec | None) -> list[str]:
        if spec is None:
            return ["multi_iteration_executor_input_preflight_request_missing"]
        blockers: list[str] = []
        plan = spec.next_step_plan
        if not plan:
            blockers.append("multi_iteration_next_step_plan_required")
        else:
            if plan.get("status") != "ready_for_review" or plan.get("ready_for_review") is not True:
                blockers.append("multi_iteration_next_step_plan_not_ready")
            if plan.get("blockers"):
                blockers.append("multi_iteration_next_step_plan_has_blockers")
            expected = plan.get("expected_executor") if isinstance(plan.get("expected_executor"), dict) else {}
            if expected and expected.get("name") not in {None, "execute_paused_session_automatic_loop_multi_iteration"}:
                blockers.append("multi_iteration_next_step_executor_name_mismatch")
            if expected and expected.get("step264_executor_mvp") is False:
                blockers.append("multi_iteration_next_step_missing_step264_executor_mvp")
            next_iteration = plan.get("next_iteration") if isinstance(plan.get("next_iteration"), dict) else {}
            if next_iteration and next_iteration.get("next_loop_plan_ready") is not True:
                blockers.append("multi_iteration_next_step_loop_plan_not_ready")
            if next_iteration and next_iteration.get("next_iteration_reviewable") is not True:
                blockers.append("multi_iteration_next_step_iteration_not_reviewable")
            if next_iteration and next_iteration.get("fresh_live_callframe_recovered") is not True:
                blockers.append("fresh_live_callframe_required")
            policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
            for key, blocker in (
                ("cdp_command_sent", "next_step_plan_sent_cdp"),
                ("debugger_event_subscribed", "next_step_plan_subscribed_debugger_event"),
                ("paused_event_captured", "next_step_plan_captured_paused_event"),
                ("checkpoint_written", "next_step_plan_wrote_checkpoint"),
                ("live_callframe_recovered", "next_step_plan_recovered_live_callframe"),
                ("loop_advanced", "next_step_plan_advanced_loop_or_queue"),
                ("queue_advanced", "next_step_plan_advanced_loop_or_queue"),
                ("long_lived_cross_process_session_managed", "next_step_plan_managed_long_lived_session"),
                ("calls_mcp", "mcp_call_claim_detected"),
                ("mobile_runtime_used", "mobile_runtime_claim_detected"),
            ):
                if policy.get(key) is True:
                    blockers.append(blocker)
            if next_iteration.get("would_execute_multi_iteration") is True or policy.get("would_execute_multi_iteration") is True:
                blockers.append("next_step_plan_execution_claim_detected")
            if next_iteration.get("automatic_multi_iteration_loop") is True or policy.get("automatic_multi_iteration_loop") is True:
                blockers.append("next_step_plan_automatic_loop_claim_detected")
        execution_blockers = PausedSessionAutomaticLoopMultiIterationExecutionManager._blockers(spec.execution_spec)
        blockers.extend(execution_blockers)
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: PausedSessionAutomaticLoopMultiIterationExecutorInputPreflightSpec | None,
        *,
        status: str,
        blockers: list[str],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        execution_spec = spec.execution_spec if spec else PausedSessionAutomaticLoopMultiIterationExecutionSpec()
        plan = spec.next_step_plan if spec else {}
        gate = execution_spec.bounded_executor_gate
        journal = execution_spec.transaction_journal
        loop_plan = execution_spec.loop_plan
        workflow = execution_spec.multi_step_workflow
        recovery = execution_spec.live_callframe_recovery
        planned_iterations = gate.get("planned_iterations") if isinstance(gate.get("planned_iterations"), list) else []
        selected_step = PausedSessionAutomaticLoopMultiIterationExecutionManager._selected_step_index(execution_spec)
        selected = next((item for item in planned_iterations if isinstance(item, dict) and int(item.get("workflow_step_index") or 0) == selected_step), {})
        ready = status == "ready_for_review"
        next_iteration = plan.get("next_iteration") if isinstance(plan.get("next_iteration"), dict) else {}
        checkpoint_review = plan.get("checkpoint_review") if isinstance(plan.get("checkpoint_review"), dict) else {}
        bounded_input = gate.get("bounded_executor_input") if isinstance(gate.get("bounded_executor_input"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-executor-input-preflight.v1",
            "status": status,
            "ready_for_review": ready,
            "ready_for_execution_review": ready,
            "ready_to_execute_now": False,
            "ready_to_execute_after_approval": False,
            "executor_input_preflight_only": True,
            "preflight_id": f"automatic-loop-multi-iteration-executor-input-preflight:{journal.get('journal_id') or gate.get('journal_id') or plan.get('transaction_id') or 'unbound'}",
            "source_next_step_plan": "workspace/paused-session-automatic-loop-multi-iteration-next-step-plan.json",
            "source_bounded_executor_gate": "workspace/paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json",
            "source_transaction_journal": "workspace/paused-session-automatic-loop-multi-iteration-executor-journal.json",
            "target_execution_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
            "transaction_id": journal.get("transaction_id") or gate.get("transaction_id") or plan.get("transaction_id"),
            "journal_id": journal.get("journal_id") or gate.get("journal_id"),
            "execution_plan_id": journal.get("execution_plan_id") or gate.get("execution_plan_id"),
            "policy_id": journal.get("policy_id") or gate.get("policy_id"),
            "loop_id": gate.get("loop_id") or loop_plan.get("loop_id"),
            "workflow_id": gate.get("workflow_id") or workflow.get("workflow_id"),
            "selected_step_index": selected_step or None,
            "reviewer": spec.reviewer if spec else execution_spec.reviewer,
            "next_step_plan_review": {
                "status": plan.get("status"),
                "ready_for_review": bool(plan.get("ready_for_review")),
                "multi_iteration_followup_checkpoint_ready": bool(checkpoint_review.get("multi_iteration_followup_checkpoint_ready")),
                "continuation_checkpoint_ready": bool(checkpoint_review.get("continuation_checkpoint_ready")),
                "next_loop_plan_ready": bool(next_iteration.get("next_loop_plan_ready")),
                "next_iteration_reviewable": bool(next_iteration.get("next_iteration_reviewable")),
                "fresh_live_callframe_recovered": bool(next_iteration.get("fresh_live_callframe_recovered")),
                "would_execute_multi_iteration": False,
            },
            "executor_input_checks": {
                "next_step_plan_ready": bool(plan.get("status") == "ready_for_review" and plan.get("ready_for_review") is True and not plan.get("blockers")),
                "bounded_executor_gate_ready": bool(gate.get("status") == "ready_for_review" and gate.get("bounded_executor_gate_ready_for_review") is True and gate.get("multi_iteration_bounded_executor_gate_ready_for_review") is True),
                "transaction_journal_written": bool(journal.get("status") == "written" and journal.get("journal_written") is True),
                "transaction_journal_started": bool(journal.get("transaction_started") is True),
                "loop_plan_ready": bool(loop_plan.get("status") == "ready_for_review" and loop_plan.get("ready_for_review") is True),
                "workflow_ready": bool(workflow.get("status") == "ready_for_review" and workflow.get("ready_for_review") is True),
                "fresh_live_callframe_recovered": bool(recovery.get("live_callframe_recovered") is True),
                "retained_attached_session_available": bool(execution_spec.attached_session_id),
                "selected_iteration_in_gate": bool(selected),
                "selected_iteration_ready_for_executor_review": bool(selected.get("ready_for_future_executor_review") is True),
                "requires_per_iteration_review": bool(bounded_input.get("requires_per_iteration_review") is True or selected.get("requires_per_iteration_review_gate") is True),
                "requires_checkpoint_after_iteration": bool(bounded_input.get("requires_checkpoint_after_each_iteration") is True or selected.get("requires_checkpoint_after_iteration") is True),
                "requires_fresh_live_callframe": bool(bounded_input.get("require_fresh_live_callframe") is True or selected.get("requires_fresh_live_callframe_before_execution") is True),
                "requires_retained_attached_session": bool(bounded_input.get("requires_retained_attached_session") is True),
                "stop_after_checkpoint": bool(bounded_input.get("requires_stop_after_each_checkpoint") is True or selected.get("requires_stop_after_checkpoint") is True),
                "review_approval_required_for_execution": True,
                "step264_executor_mvp": True,
            },
            "expected_executor": {
                "name": "execute_paused_session_automatic_loop_multi_iteration",
                "implemented": True,
                "step264_executor_mvp": True,
                "bounded_one_iteration_only": True,
                "requires_explicit_review_approval": True,
                "delegates_to": "workspace/paused-session-multi-step-loop-execution.json",
                "result_artifact": "workspace/paused-session-automatic-loop-multi-iteration-execution-result.json",
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers),
            "side_effect_policy": policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "executor_input_preflight_only": True,
            "would_execute_multi_iteration": False,
            "automatic_multi_iteration_loop": False,
            "automatic_loop_executed": False,
            "automatic_multi_iteration_executor_called": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "checkpoint_written": False,
            "live_callframe_recovered": False,
            "automatic_live_callframe_recovery": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "multi_iteration_executor_input_preflight_request_missing": ("request", "No multi-iteration executor-input preflight request was provided.", "request_paused_session_automatic_loop_multi_iteration_executor_input_preflight"),
            "multi_iteration_next_step_plan_required": ("next_step_plan", "A ready Step 266 multi-iteration next-step plan is required.", "review_paused_session_automatic_loop_multi_iteration_next_step_plan"),
            "multi_iteration_next_step_plan_not_ready": ("next_step_plan", "The Step 266 next-step plan is not ready for executor review.", "resolve_multi_iteration_next_step_plan_blockers"),
            "multi_iteration_next_step_plan_has_blockers": ("next_step_plan", "The Step 266 next-step plan still contains blockers.", "resolve_multi_iteration_next_step_plan_blockers"),
            "multi_iteration_next_step_executor_name_mismatch": ("next_step_plan", "The next-step plan points at an unexpected executor.", "refresh_multi_iteration_next_step_plan_executor_contract"),
            "multi_iteration_next_step_missing_step264_executor_mvp": ("next_step_plan", "The next-step plan must acknowledge the Step 264 executor MVP.", "refresh_multi_iteration_next_step_plan_executor_contract"),
            "multi_iteration_next_step_loop_plan_not_ready": ("loop_plan", "The next-step plan has not proven the next loop plan is ready.", "refresh_next_loop_plan_for_multi_iteration_executor_input"),
            "multi_iteration_next_step_iteration_not_reviewable": ("loop_plan", "The next-step plan has not proven a reviewable next iteration.", "refresh_next_loop_iteration_review_gate"),
            "fresh_live_callframe_required": ("callframe", "Fresh live callFrame evidence is required before executor review.", "recover_live_callframe_from_captured_pause"),
            "next_step_plan_sent_cdp": ("safety", "The next-step plan claims a CDP command was sent.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_subscribed_debugger_event": ("safety", "The next-step plan claims Debugger event subscription.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_captured_paused_event": ("safety", "The next-step plan claims paused-event capture.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_wrote_checkpoint": ("safety", "The next-step plan claims checkpoint writes.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_recovered_live_callframe": ("safety", "The next-step plan claims live callFrame recovery.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_advanced_loop_or_queue": ("safety", "The next-step plan claims loop or queue advancement.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_managed_long_lived_session": ("safety", "The next-step plan claims long-lived session management.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_execution_claim_detected": ("safety", "The next-step plan claims execution, but this preflight must remain read-only.", "audit_multi_iteration_next_step_plan_side_effects"),
            "next_step_plan_automatic_loop_claim_detected": ("safety", "The next-step plan claims automatic multi-iteration looping.", "audit_multi_iteration_next_step_plan_side_effects"),
            "mcp_call_claim_detected": ("safety", "The next-step plan claims MCP usage.", "remove_mcp_from_multi_iteration_executor_input_preflight"),
            "mobile_runtime_claim_detected": ("safety", "The next-step plan claims mobile runtime usage, which is deferred.", "remove_mobile_runtime_from_multi_iteration_executor_input_preflight"),
        }
        execution_catalog = {item["code"]: item for item in PausedSessionAutomaticLoopMultiIterationExecutionManager._blocker_details(blockers)}
        details = []
        for blocker in blockers:
            if blocker in catalog:
                category, explanation, next_action = catalog[blocker]
                details.append({"code": blocker, "category": category, "explanation": explanation, "next_action": next_action})
            elif blocker in execution_catalog:
                details.append(dict(execution_catalog[blocker]))
            else:
                details.append({"code": blocker, "category": "unknown", "explanation": blocker, "next_action": "inspect_paused_session_automatic_loop_multi_iteration_executor_input_preflight"})
        return details

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if any(str(item).startswith("multi_iteration_next_step") for item in blockers):
            return "review_paused_session_automatic_loop_multi_iteration_next_step_plan"
        if "fresh_live_callframe_required" in blockers:
            return "recover_live_callframe_from_captured_pause"
        if blockers:
            return "inspect_paused_session_automatic_loop_multi_iteration_executor_input_preflight_blockers"
        return "review_paused_session_automatic_loop_multi_iteration_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopNextIterationExecutionSpec:
    """Explicit-review-only executor for one planned automatic-loop next iteration.

    This consumes the read-only next-iteration plan descriptor and delegates at most
    one reviewed iteration to the existing paused-session loop executor. It does not
    recover callFrames, advance queues / loops, manage long-lived sessions, call MCP,
    or touch mobile runtime chains.
    """

    next_iteration_plan: dict[str, Any] = field(default_factory=dict)
    loop_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_next_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopNextIterationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_next_iteration_execution")
            or context.get("pausedSessionAutomaticLoopNextIterationExecution")
            or context.get("paused-session-automatic-loop-next-iteration-execution")
            or context.get("execute_paused_session_automatic_loop_next_iteration")
            or context.get("executePausedSessionAutomaticLoopNextIteration")
            or context.get("execute_next_paused_session_automatic_loop_iteration")
            or context.get("executeNextPausedSessionAutomaticLoopIteration")
        )
        plan_container = _first_dict(
            context,
            "paused_session_automatic_loop_following_iteration_plan",
            "pausedSessionAutomaticLoopFollowingIterationPlan",
            "paused-session-automatic-loop-following-iteration-plan",
            "automatic_loop_following_iteration_plan",
            "automaticLoopFollowingIterationPlan",
            "following_iteration_plan",
            "followingIterationPlan",
            "paused_session_automatic_loop_next_iteration_plan",
            "pausedSessionAutomaticLoopNextIterationPlan",
            "paused-session-automatic-loop-next-iteration-plan",
            "automatic_loop_next_iteration_plan",
            "automaticLoopNextIterationPlan",
            "next_iteration_plan",
            "nextIterationPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
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
        if not requested and not plan:
            return None
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_raw = context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", next_iteration.get("workflow_step_index")))))
        try:
            selected_step_index = int(selected_raw) if selected_raw is not None else None
        except (TypeError, ValueError):
            selected_step_index = None
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_paused_session_automatic_loop_next_iteration",
            context.get("executePausedSessionAutomaticLoopNextIteration", context.get("execute_next_paused_session_automatic_loop_iteration", context.get("executeNextPausedSessionAutomaticLoopIteration", context.get("execute_next_iteration", False)))),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or plan.get("pause_session_id") or loop_plan.get("pause_session_id") or workflow.get("pause_session_id") or recovery.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or plan.get("target_id") or loop_plan.get("target_id") or workflow.get("target_id") or recovery.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or plan.get("reviewer") or loop_plan.get("reviewer")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            next_iteration_plan=plan,
            loop_plan=loop_plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_next_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index) if selected_step_index is not None else None,
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
class PausedSessionAutomaticLoopNextIterationExecutionResult:
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


class PausedSessionAutomaticLoopNextIterationExecutionManager:
    """Execute at most one reviewed next automatic-loop iteration."""

    def execute(self, page: BrowserPage | None, spec: PausedSessionAutomaticLoopNextIterationExecutionSpec | None) -> PausedSessionAutomaticLoopNextIterationExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return PausedSessionAutomaticLoopNextIterationExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_next_iteration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return PausedSessionAutomaticLoopNextIterationExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return PausedSessionAutomaticLoopNextIterationExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        loop_spec = PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=True,
            review_approved=True,
            selected_step_index=self._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )
        result = PausedSessionMultiStepLoopExecutionManager().execute(page, loop_spec)
        inner = result.execution if isinstance(result.execution, dict) else {}
        inner_policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else {}
        status = "executed" if result.status == "executed" else result.status
        blockers_after = [] if status == "executed" else [result.reason or "automatic_loop_next_iteration_execution_failed"]
        payload = self._payload(spec, status=status, blockers=blockers_after, inner_result=inner, inner_policy=inner_policy, error=result.error)
        return PausedSessionAutomaticLoopNextIterationExecutionResult(status=status, execution=payload, side_effect_policy=self._side_effect_policy(inner_policy), reason=blockers_after[0] if blockers_after else None, error=result.error)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopNextIterationExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_next_iteration_execution_request_missing"]
        blockers: list[str] = []
        plan = spec.next_iteration_plan
        if not plan:
            blockers.append("next_iteration_plan_required")
        elif str(plan.get("status") or "") != "ready_for_review" or plan.get("ready_for_review") is not True:
            blockers.append("next_iteration_plan_not_ready")
        checkpoint_review = plan.get("checkpoint_review") if isinstance(plan.get("checkpoint_review"), dict) else {}
        next_iteration = plan.get("next_iteration") if isinstance(plan.get("next_iteration"), dict) else {}
        gates = plan.get("execution_review_gates") if isinstance(plan.get("execution_review_gates"), dict) else {}
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        if plan and checkpoint_review.get("followup_checkpoint_ready") is not True:
            blockers.append("followup_checkpoint_not_ready")
        if plan and checkpoint_review.get("continuation_checkpoint_ready") is not True:
            blockers.append("continuation_checkpoint_not_ready")
        if plan and next_iteration.get("next_loop_plan_ready") is not True:
            blockers.append("next_loop_plan_not_ready")
        if plan and next_iteration.get("next_iteration_reviewable") is not True:
            blockers.append("next_iteration_not_reviewable")
        if plan and next_iteration.get("fresh_live_callframe_recovered") is not True:
            blockers.append("fresh_live_callframe_recovery_required")
        if plan and gates.get("requires_explicit_execution_approval") is not True:
            blockers.append("explicit_execution_approval_gate_required")
        if plan and (policy.get("would_execute_next_iteration") is True or policy.get("automatic_loop_executed") is True or policy.get("loop_advanced") is True or policy.get("queue_advanced") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True):
            blockers.append("next_iteration_plan_side_effect_claim_detected")
        blockers.extend(PausedSessionMultiStepLoopExecutionManager._blockers(cls._loop_spec(spec)))
        return list(dict.fromkeys(blockers))

    @classmethod
    def _loop_spec(cls, spec: PausedSessionAutomaticLoopNextIterationExecutionSpec | None) -> PausedSessionMultiStepLoopExecutionSpec | None:
        if spec is None:
            return None
        return PausedSessionMultiStepLoopExecutionSpec(
            loop_plan=spec.loop_plan,
            multi_step_workflow=spec.multi_step_workflow,
            live_callframe_recovery=spec.live_callframe_recovery,
            cross_process_attach_probe=spec.cross_process_attach_probe,
            execute_loop_iteration=False,
            review_approved=False,
            selected_step_index=cls._selected_step_index(spec),
            pause_session_id=spec.pause_session_id,
            target_id=spec.target_id,
            attached_session_id=spec.attached_session_id,
            live_callframe_id=spec.live_callframe_id,
            timeout_ms=spec.timeout_ms,
            observed_paused_event=spec.observed_paused_event,
            reviewer=spec.reviewer,
            require_matching_session_id=spec.require_matching_session_id,
        )

    @classmethod
    def _selected_step_index(cls, spec: PausedSessionAutomaticLoopNextIterationExecutionSpec | None) -> int:
        if spec is None:
            return 0
        if spec.selected_step_index is not None:
            return spec.selected_step_index
        return PausedSessionMultiStepLoopExecutionManager._selected_step_index(cls._loop_spec(spec))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopNextIterationExecutionSpec | None, *, status: str, blockers: list[str], inner_result: dict[str, Any] | None = None, inner_policy: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
        plan = spec.next_iteration_plan if spec else {}
        inner = inner_result or {}
        policy = inner_policy or {}
        selected_index = cls._selected_step_index(spec)
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-next-iteration-execution.v1",
            "status": status,
            "transaction_id": plan.get("transaction_id"),
            "journal_id": plan.get("journal_id"),
            "loop_id": plan.get("loop_id") or (spec.loop_plan.get("loop_id") if spec else None),
            "workflow_id": plan.get("workflow_id") or (spec.multi_step_workflow.get("workflow_id") if spec else None),
            "pause_session_id": spec.pause_session_id if spec else plan.get("pause_session_id"),
            "target_id": spec.target_id if spec else plan.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "execute_next_iteration_requested": bool(spec and spec.execute_next_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "bounded_one_iteration_only": True,
            "selected_step_index": selected_index or None,
            "executed_iteration_count": 1 if status == "executed" else 0,
            "iteration_results": [inner] if inner else [],
            "source_next_iteration_plan_status": plan.get("status"),
            "delegated_executor_artifact": "workspace/paused-session-multi-step-loop-execution.json",
            "delegated_executor_status": inner.get("status"),
            "checkpoint_required": status == "executed",
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_loop_plan": "workspace/paused-session-multi-step-loop-plan.json",
            "expected_followup_next_iteration_plan": "workspace/paused-session-automatic-loop-next-iteration-plan.json",
            "automatic_loop_next_iteration_executed": status == "executed",
            "automatic_loop_executed": status == "executed",
            "automatic_loop_one_iteration_executed": status == "executed",
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_session_managed": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, inner=inner),
            "side_effect_policy": cls._side_effect_policy(policy),
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        policy = PausedSessionAutomaticLoopExecutionManager._side_effect_policy(inner_policy)
        policy.update({"automatic_loop_next_iteration_executor": True, "automatic_loop_next_iteration_executed": bool(policy.get("multi_step_loop_iteration_executed")), "automatic_multi_iteration_loop": False, "automatic_queue_advance": False, "loop_advanced": False, "queue_advanced": False, "long_lived_cross_process_session_managed": False, "calls_mcp": False, "mobile_runtime_used": False})
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_next_iteration_execution_request_missing": ("request", "No automatic-loop next-iteration execution request was provided.", "request_paused_session_automatic_loop_next_iteration_execution"),
            "next_iteration_plan_required": ("plan", "A ready automatic-loop next-iteration plan is required.", "review_paused_session_automatic_loop_next_iteration_plan"),
            "next_iteration_plan_not_ready": ("plan", "The automatic-loop next-iteration plan is not ready for execution review.", "resolve_next_iteration_plan_blockers"),
            "followup_checkpoint_not_ready": ("checkpoint", "The prior automatic-loop follow-up checkpoint is not ready.", "review_paused_session_automatic_loop_followup_checkpoint"),
            "continuation_checkpoint_not_ready": ("checkpoint", "The continuation checkpoint is not ready for the next iteration.", "refresh_continuation_checkpoint"),
            "next_loop_plan_not_ready": ("loop_plan", "The next loop plan is not ready.", "plan_next_paused_session_loop_iteration"),
            "next_iteration_not_reviewable": ("loop_plan", "The selected next iteration is not reviewable.", "review_next_paused_session_loop_iteration"),
            "fresh_live_callframe_recovery_required": ("debugger", "Fresh live callFrame recovery is required before executing the next iteration.", "recover_live_callframe_from_captured_pause"),
            "explicit_execution_approval_gate_required": ("review", "The next-iteration plan must require explicit execution approval.", "regenerate_next_iteration_plan"),
            "next_iteration_plan_side_effect_claim_detected": ("safety", "The next-iteration plan unexpectedly claims side effects.", "audit_next_iteration_plan_side_effects"),
            "review_approval_required": ("review", "Executing the next automatic-loop iteration requires explicit review approval.", "approve_paused_session_automatic_loop_next_iteration_execution"),
            "automatic_loop_next_iteration_execution_failed": ("runtime", "The delegated next-iteration executor failed.", "inspect_paused_session_automatic_loop_next_iteration_execution"),
        }
        fallback = PausedSessionMultiStepLoopExecutionManager._blocker_details(blockers)
        fallback_by_code = {item.get("code"): item for item in fallback}
        mapped: list[dict[str, Any]] = []
        for blocker in blockers:
            if blocker in catalog:
                category, explanation, next_action = catalog[blocker]
                mapped.append({"code": blocker, "category": category, "explanation": explanation, "next_action": next_action})
            else:
                mapped.append(fallback_by_code.get(blocker, {"code": blocker, "category": "unknown", "explanation": blocker, "next_action": "inspect_paused_session_automatic_loop_next_iteration_execution"}))
        return mapped

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], inner: dict[str, Any]) -> str:
        if blockers:
            return "inspect_paused_session_automatic_loop_next_iteration_execution_blockers"
        if status in {"ready_for_review", "review_required"}:
            return "approve_paused_session_automatic_loop_next_iteration_execution"
        if status == "executed" and inner.get("paused_event_captured"):
            return "checkpoint_automatic_loop_next_iteration_captured_pause"
        if status == "executed":
            return "review_paused_session_automatic_loop_next_iteration_execution_result"
        return "inspect_paused_session_automatic_loop_next_iteration_execution"


@dataclass(slots=True)
class PausedSessionAutomaticLoopNextIterationFollowupCheckpointSpec:
    """Read-only checkpoint handoff after automatic-loop next-iteration execution.

    This descriptor consumes the Step 253 next-iteration execution result plus
    optional continuation checkpoint / next loop plan evidence. It does not write
    checkpoints, recover live callFrames, send CDP commands, advance queues, or
    execute another iteration.
    """

    automatic_loop_next_iteration_execution: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    next_loop_plan: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionAutomaticLoopNextIterationFollowupCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_automatic_loop_next_iteration_followup_checkpoint")
            or context.get("pausedSessionAutomaticLoopNextIterationFollowupCheckpoint")
            or context.get("paused-session-automatic-loop-next-iteration-followup-checkpoint")
            or context.get("paused_session_automatic_loop_next_iteration_execution_followup")
            or context.get("pausedSessionAutomaticLoopNextIterationExecutionFollowup")
            or context.get("checkpoint_paused_session_automatic_loop_next_iteration_execution")
            or context.get("checkpointPausedSessionAutomaticLoopNextIterationExecution")
        )
        execution_container = _first_dict(
            context,
            "paused_session_automatic_loop_next_iteration_execution",
            "pausedSessionAutomaticLoopNextIterationExecution",
            "paused-session-automatic-loop-next-iteration-execution",
            "automatic_loop_next_iteration_execution",
            "automaticLoopNextIterationExecution",
            "automatic_loop_next_iteration_execution_result",
            "automaticLoopNextIterationExecutionResult",
            "execute_paused_session_automatic_loop_next_iteration",
            "executePausedSessionAutomaticLoopNextIteration",
            "execute_next_paused_session_automatic_loop_iteration",
            "executeNextPausedSessionAutomaticLoopIteration",
        )
        execution = dict(execution_container.get("execution")) if isinstance(execution_container.get("execution"), dict) else execution_container
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
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "next_loop_plan",
            "nextLoopPlan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        if not requested and not execution:
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId") or execution.get("reviewer") or loop_plan.get("reviewer")
        return cls(
            automatic_loop_next_iteration_execution=execution,
            continuation_checkpoint=checkpoint,
            next_loop_plan=loop_plan,
            reviewer=str(reviewer).strip() if reviewer else None,
        )


@dataclass(slots=True)
class PausedSessionAutomaticLoopNextIterationFollowupCheckpointResult:
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


class PausedSessionAutomaticLoopNextIterationFollowupCheckpointManager:
    """Review-only handoff descriptor after a reviewed next-iteration execution."""

    def review(self, spec: PausedSessionAutomaticLoopNextIterationFollowupCheckpointSpec | None) -> PausedSessionAutomaticLoopNextIterationFollowupCheckpointResult:
        blockers = self._blockers(spec)
        status = "ready_for_review" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionAutomaticLoopNextIterationFollowupCheckpointResult(status=status, checkpoint=payload, side_effect_policy=self._side_effect_policy(), reason=blockers[0] if blockers else None)

    @classmethod
    def _blockers(cls, spec: PausedSessionAutomaticLoopNextIterationFollowupCheckpointSpec | None) -> list[str]:
        if spec is None:
            return ["automatic_loop_next_iteration_followup_checkpoint_request_missing"]
        blockers: list[str] = []
        execution = spec.automatic_loop_next_iteration_execution
        checkpoint = spec.continuation_checkpoint
        if not execution:
            blockers.append("automatic_loop_next_iteration_execution_required")
            return blockers
        execution_status = str(execution.get("status") or "")
        policy = execution.get("side_effect_policy") if isinstance(execution.get("side_effect_policy"), dict) else {}
        if execution_status in {"blocked", "failed", "failure", "error", "timed_out", "unsupported"}:
            blockers.append("automatic_loop_next_iteration_execution_blocked")
        elif execution_status != "executed" or execution.get("automatic_loop_next_iteration_executed") is not True:
            blockers.append("automatic_loop_next_iteration_execution_not_executed")
        if execution.get("checkpoint_required") is True:
            if not checkpoint:
                blockers.append("automatic_loop_next_iteration_followup_checkpoint_required")
            elif not PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint):
                blockers.append("automatic_loop_next_iteration_followup_checkpoint_not_ready")
        if execution.get("loop_advanced") is True or policy.get("loop_advanced") is True:
            blockers.append("loop_advance_claim_detected")
        if execution.get("queue_advanced") is True or policy.get("queue_advanced") is True:
            blockers.append("queue_advance_claim_detected")
        if execution.get("long_lived_session_managed") is True or policy.get("long_lived_cross_process_session_managed") is True:
            blockers.append("long_lived_session_claim_detected")
        if policy.get("automatic_multi_iteration_loop") is True:
            blockers.append("automatic_multi_iteration_claim_detected")
        if policy.get("calls_mcp") is True:
            blockers.append("mcp_call_claim_detected")
        if policy.get("mobile_runtime_used") is True:
            blockers.append("mobile_runtime_claim_detected")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionAutomaticLoopNextIterationFollowupCheckpointSpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        execution = spec.automatic_loop_next_iteration_execution if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        loop_plan = spec.next_loop_plan if spec else {}
        checkpoint_ready = PausedSessionAutomaticLoopFollowupCheckpointManager._checkpoint_ready(checkpoint)
        loop_plan_ready = PausedSessionAutomaticLoopFollowupCheckpointManager._loop_plan_ready(loop_plan)
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-next-iteration-followup-checkpoint.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "transaction_id": execution.get("transaction_id"),
            "journal_id": execution.get("journal_id"),
            "loop_id": execution.get("loop_id") or loop_plan.get("loop_id"),
            "workflow_id": execution.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": execution.get("pause_session_id") or checkpoint.get("pause_session_id") or loop_plan.get("pause_session_id"),
            "target_id": execution.get("target_id") or checkpoint.get("target_id") or loop_plan.get("target_id"),
            "source_statuses": {
                "automatic_loop_next_iteration_execution": execution.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "next_loop_plan": loop_plan.get("status"),
            },
            "execution_summary": {
                "automatic_loop_next_iteration_executed": bool(execution.get("automatic_loop_next_iteration_executed")),
                "automatic_loop_executed": bool(execution.get("automatic_loop_executed")),
                "automatic_loop_one_iteration_executed": bool(execution.get("automatic_loop_one_iteration_executed")),
                "executed_iteration_count": execution.get("executed_iteration_count", 0),
                "checkpoint_required": bool(execution.get("checkpoint_required")),
                "loop_advanced": bool(execution.get("loop_advanced")),
                "queue_advanced": bool(execution.get("queue_advanced")),
                "long_lived_session_managed": bool(execution.get("long_lived_session_managed")),
            },
            "checkpoint_review": {
                "checkpoint_present": bool(checkpoint),
                "checkpoint_ready": checkpoint_ready,
                "checkpoint_status": checkpoint.get("status"),
                "callframe_count": checkpoint.get("callframe_count", 0),
                "continuation_ready_for_next_action": bool(checkpoint.get("continuation_ready_for_next_action")),
                "continuation_ready_for_next_capture_plan": bool(checkpoint.get("continuation_ready_for_next_capture_plan")),
                "live_callframe_recovery_ready": bool(checkpoint.get("live_callframe_recovery_ready")),
                "manual_checkpoint_required": bool(checkpoint.get("manual_checkpoint_required")),
            },
            "next_loop_review": {
                "next_loop_plan_present": bool(loop_plan),
                "next_loop_plan_ready": loop_plan_ready,
                "next_iteration_reviewable": bool(PausedSessionAutomaticLoopFollowupCheckpointManager._dict_value(loop_plan, "readiness").get("next_loop_iteration_reviewable")) if loop_plan else False,
                "next_iteration_available": bool(PausedSessionAutomaticLoopFollowupCheckpointManager._dict_value(loop_plan, "next_iteration").get("available")) if loop_plan else False,
                "requires_review_approval": True,
                "requires_fresh_live_callframe": True,
                "would_execute_next_iteration": False,
            },
            "required_followups": cls._required_followups(checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(blockers=blockers, checkpoint_ready=checkpoint_ready, loop_plan_ready=loop_plan_ready),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _required_followups(*, checkpoint_ready: bool, loop_plan_ready: bool) -> list[dict[str, Any]]:
        if not checkpoint_ready:
            return [{"order": 1, "action": "checkpoint_paused_session_automatic_loop_next_iteration_execution", "artifact": "workspace/paused-session-cross-process-continuation-checkpoint.json", "automatic": False}]
        if not loop_plan_ready:
            return [{"order": 1, "action": "plan_next_paused_session_loop_iteration_after_next_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False}]
        return [{"order": 1, "action": "review_following_paused_session_automatic_loop_iteration", "artifact": "workspace/paused-session-automatic-loop-next-iteration-plan.json", "automatic": False}]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        policy = PausedSessionAutomaticLoopFollowupCheckpointManager._side_effect_policy()
        policy.update({
            "automatic_loop_next_iteration_followup_checkpoint": True,
            "would_execute_next_iteration": False,
            "automatic_multi_iteration_loop": False,
            "automatic_queue_advance": False,
            "loop_advanced": False,
            "queue_advanced": False,
            "long_lived_cross_process_session_managed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        })
        return policy

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "automatic_loop_next_iteration_followup_checkpoint_request_missing": ("request", "No automatic-loop next-iteration follow-up checkpoint review request was provided.", "request_paused_session_automatic_loop_next_iteration_followup_checkpoint"),
            "automatic_loop_next_iteration_execution_required": ("execution", "The Step 253 automatic-loop next-iteration execution result is required.", "provide_paused_session_automatic_loop_next_iteration_execution"),
            "automatic_loop_next_iteration_execution_blocked": ("execution", "The next-iteration execution result is blocked, failed, unsupported, or timed out.", "inspect_paused_session_automatic_loop_next_iteration_execution"),
            "automatic_loop_next_iteration_execution_not_executed": ("execution", "The next-iteration execution result has not executed a reviewed iteration yet.", "approve_paused_session_automatic_loop_next_iteration_execution"),
            "automatic_loop_next_iteration_followup_checkpoint_required": ("checkpoint", "Executed next automatic-loop iterations require a continuation checkpoint before another iteration review.", "checkpoint_paused_session_automatic_loop_next_iteration_execution"),
            "automatic_loop_next_iteration_followup_checkpoint_not_ready": ("checkpoint", "The supplied continuation checkpoint is not ready for next iteration review.", "recover_or_refresh_continuation_checkpoint"),
            "loop_advance_claim_detected": ("safety", "The next-iteration execution claims loop advancement, which is outside the MVP boundary.", "audit_automatic_loop_next_iteration_execution_side_effects"),
            "queue_advance_claim_detected": ("safety", "The next-iteration execution claims queue advancement, which is outside the MVP boundary.", "audit_automatic_loop_next_iteration_execution_side_effects"),
            "long_lived_session_claim_detected": ("safety", "The next-iteration execution claims long-lived session management, which is outside the MVP boundary.", "audit_automatic_loop_next_iteration_execution_side_effects"),
            "automatic_multi_iteration_claim_detected": ("safety", "The next-iteration execution claims automatic multi-iteration looping, which is still deferred.", "audit_automatic_loop_next_iteration_execution_side_effects"),
            "mcp_call_claim_detected": ("safety", "The next-iteration execution claims MCP calls, which are disallowed for native automatic-loop follow-up.", "audit_automatic_loop_next_iteration_execution_side_effects"),
            "mobile_runtime_claim_detected": ("safety", "The next-iteration execution claims mobile runtime use, which is deferred.", "audit_automatic_loop_next_iteration_execution_side_effects"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, blockers: list[str], checkpoint_ready: bool, loop_plan_ready: bool) -> str:
        if "automatic_loop_next_iteration_followup_checkpoint_required" in blockers:
            return "checkpoint_paused_session_automatic_loop_next_iteration_execution"
        if "automatic_loop_next_iteration_followup_checkpoint_not_ready" in blockers:
            return "recover_or_refresh_continuation_checkpoint"
        if blockers:
            return "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint_blockers"
        if checkpoint_ready and not loop_plan_ready:
            return "plan_next_paused_session_loop_iteration_after_next_iteration"
        if checkpoint_ready and loop_plan_ready:
            return "review_following_paused_session_automatic_loop_iteration"
        return "inspect_paused_session_automatic_loop_next_iteration_followup_checkpoint"



