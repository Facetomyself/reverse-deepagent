from __future__ import annotations

import json
import re
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reverse_deepagent.browser.base import BrowserPage


def _first_dict(context: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = context.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "attached", "available"}:
            return True
        if lowered in {"0", "false", "no", "n", "detached", "unavailable"}:
            return False
    return bool(value)


PAUSED_SESSION_LIVE_ACTIONS = {"resume", "step", "step_over", "step_into", "step_out", "evaluate", "evaluate_on_callframe", "eval"}


@dataclass(slots=True)
class BreakpointSpec:
    """Provider-neutral breakpoint request."""

    url_pattern: str
    line_number: int = 0
    column_number: int | None = None
    condition: str | None = None
    trigger_expression: str | None = None
    wait_after_trigger_ms: int = 0
    auto_resume: bool = True
    callframe_evaluations: list[str] = field(default_factory=list)
    callframe_index: int = 0
    callframe_evaluation_policy: str = "read_only"
    debugger_actions: list[str] = field(default_factory=list)
    preserve_pause_state: bool = False
    pause_session_id: str | None = None
    persist_paused_session: bool = False
    paused_session_store_dir: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "BreakpointSpec | None":
        context = context or {}
        url_pattern = context.get("url_pattern") or context.get("url") or context.get("script_url")
        if not url_pattern:
            return None
        line_number = int(context.get("line_number", context.get("lineNumber", 0)) or 0)
        column_raw = context.get("column_number", context.get("columnNumber"))
        column_number = None if column_raw is None else int(column_raw)
        condition = context.get("condition")
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        wait_raw = context.get("wait_after_trigger_ms", context.get("waitAfterTriggerMs", 0))
        evaluations_raw = (
            context.get("callframe_evaluations")
            or context.get("callframeEvaluations")
            or context.get("evaluate_on_callframe")
            or context.get("evaluateOnCallFrame")
        )
        debugger_actions_raw = (
            context.get("debugger_actions")
            or context.get("debuggerActions")
            or context.get("pause_actions")
            or context.get("pauseActions")
            or context.get("step_actions")
            or context.get("stepActions")
        )
        callframe_index_raw = context.get("callframe_index", context.get("callFrameIndex", 0))
        evaluation_policy_raw = context.get(
            "callframe_evaluation_policy",
            context.get("callframeEvaluationPolicy", context.get("evaluation_policy", context.get("evaluationPolicy"))),
        )
        allow_side_effects_raw = context.get(
            "allow_callframe_side_effects",
            context.get("allowCallframeSideEffects", context.get("allow_side_effects", context.get("allowSideEffects"))),
        )
        preserve_pause_state = bool(
            context.get(
                "preserve_pause_state",
                context.get("preservePauseState", context.get("keep_paused", context.get("keepPaused", False))),
            )
        )
        auto_resume_raw = context.get("auto_resume", context.get("autoResume"))
        persist_raw = context.get(
            "persist_paused_session",
            context.get("persistPausedSession", context.get("durable_paused_session", context.get("durablePausedSession", False))),
        )
        store_dir = context.get(
            "paused_session_store_dir",
            context.get("pausedSessionStoreDir", context.get("pause_session_store_dir", context.get("pauseSessionStoreDir"))),
        )
        return cls(
            url_pattern=str(url_pattern),
            line_number=line_number,
            column_number=column_number,
            condition=str(condition) if condition else None,
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            wait_after_trigger_ms=int(wait_raw or 0),
            auto_resume=bool(auto_resume_raw) if auto_resume_raw is not None else not preserve_pause_state,
            callframe_evaluations=cls._coerce_evaluations(evaluations_raw),
            callframe_index=int(callframe_index_raw or 0),
            callframe_evaluation_policy=cls._normalize_evaluation_policy(
                evaluation_policy_raw,
                allow_side_effects=bool(allow_side_effects_raw),
            ),
            debugger_actions=cls._coerce_actions(debugger_actions_raw),
            preserve_pause_state=preserve_pause_state,
            pause_session_id=str(context.get("pause_session_id", context.get("pauseSessionId"))) if context.get("pause_session_id", context.get("pauseSessionId")) else None,
            persist_paused_session=bool(persist_raw) or bool(store_dir),
            paused_session_store_dir=str(store_dir) if store_dir else None,
        )

    def to_cdp_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "urlRegex": self.url_pattern,
            "lineNumber": self.line_number,
        }
        if self.column_number is not None:
            params["columnNumber"] = self.column_number
        if self.condition:
            params["condition"] = self.condition
        return params

    @staticmethod
    def _coerce_evaluations(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            expressions: list[str] = []
            for item in value:
                if item is None:
                    continue
                expression = str(item).strip()
                if expression:
                    expressions.append(expression)
            return expressions
        return []

    @staticmethod
    def _coerce_actions(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            actions: list[str] = []
            for item in value:
                if item is None:
                    continue
                action = str(item).strip()
                if action:
                    actions.append(action)
            return actions
        return []

    @staticmethod
    def _normalize_evaluation_policy(raw: Any, *, allow_side_effects: bool = False) -> str:
        if allow_side_effects:
            return "allow_side_effects"
        value = str(raw or "read_only").strip().replace("-", "_").lower()
        if value in {"allow", "allow_side_effect", "allow_side_effects", "unsafe", "mutation", "mutating"}:
            return "allow_side_effects"
        if value in {"block", "block_dangerous", "strict", "deny_dangerous"}:
            return "block_dangerous"
        return "read_only"


@dataclass(slots=True)
class BreakpointResult:
    status: str
    supported: bool
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    paused: dict[str, Any] = field(default_factory=dict)
    callframes: list[dict[str, Any]] = field(default_factory=list)
    callframe_evaluations: list[dict[str, Any]] = field(default_factory=list)
    mutation_audit: list[dict[str, Any]] = field(default_factory=list)
    debugger_actions: list[dict[str, Any]] = field(default_factory=list)
    debugger_session: dict[str, Any] = field(default_factory=dict)
    debugger_timeline: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    continuation_preflight: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "count": len(self.breakpoints),
            "breakpoints": self.breakpoints,
            "paused": self.paused,
            "callframes": self.callframes,
            "callframe_count": len(self.callframes),
            "callframe_evaluations": self.callframe_evaluations,
            "callframe_evaluation_count": len(self.callframe_evaluations),
            "mutation_audit": self.mutation_audit,
            "mutation_audit_count": len(self.mutation_audit),
            "debugger_actions": self.debugger_actions,
            "debugger_action_count": len(self.debugger_actions),
            "debugger_session": self.debugger_session,
            "debugger_timeline": self.debugger_timeline,
            "trigger": self.trigger,
            "continuation_preflight": self.continuation_preflight,
            "error": self.error,
            "reason": self.reason,
        }


@dataclass(slots=True)
class PausedSessionActionSpec:
    """Follow-up action against a retained paused debugger session."""

    pause_session_id: str
    action: str = "inspect"
    callframe_evaluations: list[str] = field(default_factory=list)
    callframe_index: int = 0
    callframe_evaluation_policy: str = "read_only"
    debugger_actions: list[str] = field(default_factory=list)
    wait_after_action_ms: int = 0
    paused_session_store_dir: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionActionSpec | None":
        context = context or {}
        session_id = context.get("pause_session_id") or context.get("pauseSessionId") or context.get("debugger_session_id") or context.get("debuggerSessionId")
        if not session_id:
            return None
        raw_action = context.get(
            "paused_session_action",
            context.get("pausedSessionAction", context.get("debugger_session_action", context.get("debuggerSessionAction", context.get("session_action", "inspect")))),
        )
        action = str(raw_action or "inspect").strip().replace("-", "_").lower()
        evaluations_raw = (
            context.get("callframe_evaluations")
            or context.get("callframeEvaluations")
            or context.get("evaluate_on_callframe")
            or context.get("evaluateOnCallFrame")
        )
        debugger_actions_raw = (
            context.get("debugger_actions")
            or context.get("debuggerActions")
            or context.get("pause_actions")
            or context.get("pauseActions")
            or context.get("step_actions")
            or context.get("stepActions")
        )
        debugger_actions = BreakpointSpec._coerce_actions(debugger_actions_raw)
        if action in {"resume", "step_over", "stepover", "over", "step_into", "stepinto", "into", "step_out", "stepout", "out"} and not debugger_actions:
            debugger_actions = [action]
        evaluation_policy_raw = context.get(
            "callframe_evaluation_policy",
            context.get("callframeEvaluationPolicy", context.get("evaluation_policy", context.get("evaluationPolicy"))),
        )
        allow_side_effects_raw = context.get(
            "allow_callframe_side_effects",
            context.get("allowCallframeSideEffects", context.get("allow_side_effects", context.get("allowSideEffects"))),
        )
        store_dir = context.get(
            "paused_session_store_dir",
            context.get("pausedSessionStoreDir", context.get("pause_session_store_dir", context.get("pauseSessionStoreDir"))),
        )
        return cls(
            pause_session_id=str(session_id),
            action=action or "inspect",
            callframe_evaluations=BreakpointSpec._coerce_evaluations(evaluations_raw),
            callframe_index=int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0),
            callframe_evaluation_policy=BreakpointSpec._normalize_evaluation_policy(
                evaluation_policy_raw,
                allow_side_effects=bool(allow_side_effects_raw),
            ),
            debugger_actions=debugger_actions,
            wait_after_action_ms=int(context.get("wait_after_action_ms", context.get("waitAfterActionMs", 0)) or 0),
            paused_session_store_dir=str(store_dir) if store_dir else None,
        )

    def to_breakpoint_spec(self, base: BreakpointSpec) -> BreakpointSpec:
        return BreakpointSpec(
            url_pattern=base.url_pattern,
            line_number=base.line_number,
            column_number=base.column_number,
            condition=base.condition,
            trigger_expression=None,
            wait_after_trigger_ms=0,
            auto_resume=False,
            callframe_evaluations=list(self.callframe_evaluations),
            callframe_index=self.callframe_index,
            callframe_evaluation_policy=self.callframe_evaluation_policy,
            debugger_actions=list(self.debugger_actions),
            preserve_pause_state=True,
            pause_session_id=self.pause_session_id,
            persist_paused_session=bool(self.paused_session_store_dir),
            paused_session_store_dir=self.paused_session_store_dir,
        )


@dataclass(slots=True)
class PausedSessionLiveContinuationPreflightSpec:
    """Read-only live continuation preflight for retained / durable paused sessions."""

    pause_session_id: str
    requested_action: str = "inspect"
    paused_session_store_dir: str | None = None
    debugger_session: dict[str, Any] = field(default_factory=dict)
    debugger_timeline: dict[str, Any] = field(default_factory=dict)
    paused: dict[str, Any] = field(default_factory=dict)
    callframes: list[dict[str, Any]] = field(default_factory=list)
    callframe_index: int = 0
    require_live_action: bool = False
    target_attached: bool | None = None
    cdp_target_available: bool | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionLiveContinuationPreflightSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_live_continuation_preflight")
            or context.get("pausedSessionLiveContinuationPreflight")
            or context.get("paused-session-live-continuation-preflight")
            or context.get("cross_process_paused_session_live_preflight")
            or context.get("crossProcessPausedSessionLivePreflight")
            or context.get("preflight_paused_session_live_continuation")
            or context.get("preflightPausedSessionLiveContinuation")
        )
        session_id = context.get("pause_session_id") or context.get("pauseSessionId") or context.get("debugger_session_id") or context.get("debuggerSessionId")
        if not session_id and not requested:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", context.get("paused_session_action", context.get("pausedSessionAction", "inspect"))),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        store_dir = context.get(
            "paused_session_store_dir",
            context.get("pausedSessionStoreDir", context.get("pause_session_store_dir", context.get("pauseSessionStoreDir"))),
        )
        debugger_session = _first_dict(
            context,
            "debugger_session",
            "debuggerSession",
            "debugger-session",
            "paused_session",
            "pausedSession",
        )
        if isinstance(debugger_session.get("debugger_session"), dict):
            debugger_session = dict(debugger_session["debugger_session"])
        debugger_timeline = _first_dict(context, "debugger_timeline", "debuggerTimeline", "debugger-timeline")
        paused = _first_dict(context, "debugger_paused", "debuggerPaused", "debugger-paused", "paused")
        callframes_raw = context.get("callframes") or context.get("callFrames")
        if isinstance(callframes_raw, dict):
            callframes_raw = callframes_raw.get("callframes") or callframes_raw.get("callFrames") or callframes_raw.get("items")
        return cls(
            pause_session_id=str(session_id or ""),
            requested_action=action,
            paused_session_store_dir=str(store_dir) if store_dir else None,
            debugger_session=debugger_session,
            debugger_timeline=debugger_timeline,
            paused=paused,
            callframes=[item for item in callframes_raw if isinstance(item, dict)] if isinstance(callframes_raw, list) else [],
            callframe_index=int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0),
            require_live_action=bool(
                context.get("require_live_action")
                or context.get("requireLiveAction")
                or context.get("callframe_evaluations")
                or context.get("callframeEvaluations")
                or context.get("evaluate_on_callframe")
                or context.get("evaluateOnCallFrame")
            ),
            target_attached=_optional_bool(context.get("target_attached", context.get("targetAttached"))),
            cdp_target_available=_optional_bool(context.get("cdp_target_available", context.get("cdpTargetAvailable"))),
        )


@dataclass(slots=True)
class PausedSessionLiveContinuationPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "preflight": self.preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


@dataclass(slots=True)
class PausedSessionTargetAttachReadinessSpec:
    """Read-only target attach readiness proof for future cross-process paused-session continuation."""

    pause_session_id: str
    requested_action: str = "inspect"
    paused_session_store_dir: str | None = None
    debugger_session: dict[str, Any] = field(default_factory=dict)
    debugger_timeline: dict[str, Any] = field(default_factory=dict)
    paused: dict[str, Any] = field(default_factory=dict)
    callframes: list[dict[str, Any]] = field(default_factory=list)
    callframe_index: int = 0
    continuation_preflight: dict[str, Any] = field(default_factory=dict)
    target_candidates: list[dict[str, Any]] = field(default_factory=list)
    expected_url: str | None = None
    expected_frame_id: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionTargetAttachReadinessSpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_target_attach_readiness")
            or context.get("pausedSessionTargetAttachReadiness")
            or context.get("paused-session-target-attach-readiness")
            or context.get("cross_process_target_attach_readiness")
            or context.get("crossProcessTargetAttachReadiness")
            or context.get("cross_process_paused_session_target_attach_readiness")
            or context.get("crossProcessPausedSessionTargetAttachReadiness")
        )
        session_id = context.get("pause_session_id") or context.get("pauseSessionId") or context.get("debugger_session_id") or context.get("debuggerSessionId")
        if not session_id and not requested:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", context.get("paused_session_action", context.get("pausedSessionAction", "inspect"))),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        store_dir = context.get(
            "paused_session_store_dir",
            context.get("pausedSessionStoreDir", context.get("pause_session_store_dir", context.get("pauseSessionStoreDir"))),
        )
        debugger_session = _first_dict(
            context,
            "debugger_session",
            "debuggerSession",
            "debugger-session",
            "paused_session",
            "pausedSession",
        )
        if isinstance(debugger_session.get("debugger_session"), dict):
            debugger_session = dict(debugger_session["debugger_session"])
        debugger_timeline = _first_dict(context, "debugger_timeline", "debuggerTimeline", "debugger-timeline")
        paused = _first_dict(context, "debugger_paused", "debuggerPaused", "debugger-paused", "paused")
        preflight = _first_dict(
            context,
            "continuation_preflight",
            "continuationPreflight",
            "paused_session_live_continuation_preflight",
            "pausedSessionLiveContinuationPreflight",
            "paused-session-live-continuation-preflight",
        )
        if isinstance(preflight.get("preflight"), dict):
            preflight = dict(preflight["preflight"])
        callframes_raw = context.get("callframes") or context.get("callFrames")
        if isinstance(callframes_raw, dict):
            callframes_raw = callframes_raw.get("callframes") or callframes_raw.get("callFrames") or callframes_raw.get("items")
        target_raw = (
            context.get("target_candidates")
            or context.get("targetCandidates")
            or context.get("cdp_targets")
            or context.get("cdpTargets")
            or context.get("browser_targets")
            or context.get("browserTargets")
        )
        expected_url_raw = context.get("expected_url", context.get("expectedUrl"))
        expected_frame_id_raw = context.get("expected_frame_id", context.get("expectedFrameId"))
        return cls(
            pause_session_id=str(session_id or ""),
            requested_action=action,
            paused_session_store_dir=str(store_dir) if store_dir else None,
            debugger_session=debugger_session,
            debugger_timeline=debugger_timeline,
            paused=paused,
            callframes=[item for item in callframes_raw if isinstance(item, dict)] if isinstance(callframes_raw, list) else [],
            callframe_index=int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0),
            continuation_preflight=preflight,
            target_candidates=cls._coerce_target_candidates(target_raw),
            expected_url=(str(expected_url_raw).strip() or None) if expected_url_raw is not None else None,
            expected_frame_id=(str(expected_frame_id_raw).strip() or None) if expected_frame_id_raw is not None else None,
        )

    @staticmethod
    def _coerce_target_candidates(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            for key in ("targets", "items", "entries", "targetInfos", "target_infos"):
                nested = value.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []


@dataclass(slots=True)
class PausedSessionTargetAttachReadinessResult:
    status: str
    readiness: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readiness": self.readiness,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class PausedSessionTargetAttachReadinessManager:
    """Prove whether a paused-session snapshot has enough metadata for a future CDP target attach review."""

    LIVE_ACTIONS = PAUSED_SESSION_LIVE_ACTIONS

    def assess(self, spec: PausedSessionTargetAttachReadinessSpec | None) -> PausedSessionTargetAttachReadinessResult:
        policy = PausedSessionLiveContinuationPreflightManager._side_effect_policy()
        if spec is None or not spec.pause_session_id:
            readiness = self._readiness_payload(
                spec=None,
                source="missing",
                durable_snapshot={},
                registry_entry={},
                blockers=["paused_session_evidence_missing", "target_candidate_missing", "cross_process_live_continuation_not_implemented"],
            )
            return PausedSessionTargetAttachReadinessResult(status="blocked", readiness=readiness, side_effect_policy=policy, reason="paused_session_evidence_missing")
        registry_entry = BreakpointManager._paused_sessions.get(spec.pause_session_id)
        durable_snapshot = self._load_durable_snapshot(spec)
        source = "registry" if registry_entry else "durable_snapshot" if durable_snapshot else "provided_artifact" if any((spec.debugger_session, spec.paused, spec.callframes, spec.continuation_preflight)) else "missing"
        blockers = self._blockers(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot, source=source)
        attach_ready = not any(blocker in blockers for blocker in ("paused_session_evidence_missing", "target_candidate_missing", "target_id_missing", "target_url_mismatch", "paused_target_url_missing", "cdp_target_not_attachable"))
        status = "ready_for_attach_review" if attach_ready else "blocked"
        readiness = self._readiness_payload(spec=spec, source=source, durable_snapshot=durable_snapshot, registry_entry=registry_entry or {}, blockers=blockers)
        return PausedSessionTargetAttachReadinessResult(status=status, readiness=readiness, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @staticmethod
    def _load_durable_snapshot(spec: PausedSessionTargetAttachReadinessSpec) -> dict[str, Any]:
        path = BreakpointManager._paused_session_store_path(spec.pause_session_id, spec.paused_session_store_dir)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _blockers(
        cls,
        spec: PausedSessionTargetAttachReadinessSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
        source: str,
    ) -> list[str]:
        blockers: list[str] = []
        callframes = cls._callframes(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot)
        expected_url = cls._expected_url(spec, callframes, registry_entry=registry_entry, durable_snapshot=durable_snapshot)
        selected_target = cls._selected_target_candidate(spec, expected_url)
        if source == "missing":
            blockers.append("paused_session_evidence_missing")
        if not expected_url:
            blockers.append("paused_target_url_missing")
        if not spec.target_candidates and source != "registry":
            blockers.append("target_candidate_missing")
        if selected_target and not cls._target_id(selected_target):
            blockers.append("target_id_missing")
        if spec.target_candidates and expected_url and not selected_target:
            blockers.append("target_url_mismatch")
        if selected_target and not cls._target_attachable(selected_target):
            blockers.append("cdp_target_not_attachable")
        if cls._requested_action_requires_live_callframe(spec) and not cls._stable_live_callframe_available(spec, source=source, registry_entry=registry_entry, callframes=callframes):
            blockers.append("stable_live_callframe_unavailable")
        blockers.append("cross_process_live_continuation_not_implemented")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _readiness_payload(
        cls,
        *,
        spec: PausedSessionTargetAttachReadinessSpec | None,
        source: str,
        durable_snapshot: dict[str, Any],
        registry_entry: dict[str, Any],
        blockers: list[str],
    ) -> dict[str, Any]:
        callframes = cls._callframes(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot) if spec else []
        expected_url = cls._expected_url(spec, callframes, registry_entry=registry_entry, durable_snapshot=durable_snapshot) if spec else None
        selected_target = cls._selected_target_candidate(spec, expected_url) if spec else {}
        selected_callframe = cls._selected_callframe_summary(spec, callframes) if spec else {}
        same_process_registry = source == "registry" and bool(registry_entry)
        target_attach_ready = not any(blocker in blockers for blocker in ("paused_session_evidence_missing", "target_candidate_missing", "target_id_missing", "target_url_mismatch", "paused_target_url_missing", "cdp_target_not_attachable"))
        stable_live_callframe_available = bool(spec and cls._stable_live_callframe_available(spec, source=source, registry_entry=registry_entry, callframes=callframes))
        action_is_live = bool(spec and spec.requested_action in cls.LIVE_ACTIONS)
        continuation_preflight = cls._continuation_preflight(spec, durable_snapshot=durable_snapshot, registry_entry=registry_entry) if spec else {}
        return {
            "schema_version": "reverse-deepagent.paused-session-target-attach-readiness.v1",
            "status": "ready_for_attach_review" if target_attach_ready else "blocked",
            "source": source,
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": spec.requested_action if spec else None,
            "same_process_registry": same_process_registry,
            "durable_snapshot_found": bool(durable_snapshot),
            "provided_artifact_found": bool(spec and any((spec.debugger_session, spec.paused, spec.callframes, spec.continuation_preflight))),
            "target_attach_readiness_proven": target_attach_ready,
            "cross_process_live_continuation_supported": False,
            "cross_process_execution_ready": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(target_attach_ready=target_attach_ready, blockers=blockers),
            "paused_session_evidence": {
                "source": source,
                "debugger_session_lifecycle": cls._debugger_lifecycle(spec, durable_snapshot=durable_snapshot, registry_entry=registry_entry) if spec else "missing",
                "callframe_count": len(callframes),
                "selected_callframe": selected_callframe,
                "durable_callframe_id_present": bool(selected_callframe.get("has_callframe_id")) and source == "durable_snapshot",
                "stable_live_callframe_available": stable_live_callframe_available,
            },
            "target_correlation": {
                "expected_url": expected_url,
                "expected_frame_id": spec.expected_frame_id if spec else None,
                "candidate_count": len(spec.target_candidates) if spec else 0,
                "selected_target": cls._target_summary(selected_target),
                "url_match": bool(selected_target),
                "match_strategy": "same_process_registry" if same_process_registry else "exact_or_prefix_url" if selected_target else "none",
            },
            "attachability": {
                "cdp_target_attach_candidate_available": bool(selected_target) or same_process_registry,
                "target_id_available": bool(cls._target_id(selected_target)) or same_process_registry,
                "target_type_supported": cls._target_attachable(selected_target) or same_process_registry,
                "would_attach_cdp_target": False,
                "would_probe_cdp_target": False,
                "requires_explicit_future_attach_step": True,
            },
            "callframe_recovery": {
                "stable_live_callframe_available": stable_live_callframe_available,
                "selected_callframe_has_id": bool(selected_callframe.get("has_callframe_id")),
                "durable_callframe_id_reusable": False,
                "requires_new_paused_event_after_attach": not same_process_registry,
            },
            "action_capability": {
                "requested_action": spec.requested_action if spec else None,
                "is_live_action": action_is_live,
                "inspect_supported": bool(spec and (source != "missing" or bool(callframes))),
                "target_attach_review_supported": target_attach_ready,
                "evaluate_supported": False,
                "step_supported": False,
                "resume_supported": False,
                "reason": "cross_process_live_continuation_not_implemented",
            },
            "continuation_preflight_summary": {
                "status": continuation_preflight.get("status"),
                "source": continuation_preflight.get("source"),
                "live_continuation_available": bool(continuation_preflight.get("live_continuation_available")),
                "blockers": continuation_preflight.get("blockers") if isinstance(continuation_preflight.get("blockers"), list) else [],
            },
            "side_effect_policy": PausedSessionLiveContinuationPreflightManager._side_effect_policy(),
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "paused_session_evidence_missing": ("session_evidence", "No paused-session registry entry, durable snapshot, or provided artifact was found.", "collect_or_load_paused_session_snapshot"),
            "paused_target_url_missing": ("target_correlation", "No URL was available from the selected callframe, debugger session, snapshot, or explicit expected_url.", "provide_expected_url_or_callframe_url"),
            "target_candidate_missing": ("cdp_target", "No candidate CDP target metadata was provided for cross-process attach review.", "provide_target_candidates_from_browser_provider"),
            "target_id_missing": ("cdp_target", "The matched target metadata does not expose a targetId / target_id.", "collect_target_id_before_attach_review"),
            "target_url_mismatch": ("target_correlation", "Candidate targets do not match the paused callframe URL.", "refresh_targets_and_match_paused_frame_url"),
            "cdp_target_not_attachable": ("cdp_target", "The matched target type is not attachable for debugger continuation.", "select_page_or_webview_target"),
            "stable_live_callframe_unavailable": ("callframe", "A durable or provided callFrameId is not a reusable live callFrameId for cross-process actions.", "capture_new_paused_event_after_future_attach"),
            "cross_process_live_continuation_not_implemented": ("capability_boundary", "This proof is read-only readiness metadata; full automatic cross-process multi-step continuation is still not implemented.", "review_attach_readiness_before_cross_process_execution_plan"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_attach_readiness"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_attach_readiness"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_attach_readiness"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, target_attach_ready: bool, blockers: list[str]) -> str:
        if target_attach_ready:
            return "review_target_attach_plan_before_cross_process_continuation_executor"
        if "target_candidate_missing" in blockers:
            return "collect_cdp_target_candidates_before_attach_review"
        if "target_url_mismatch" in blockers:
            return "refresh_target_candidates_and_match_paused_url"
        if "paused_session_evidence_missing" in blockers:
            return "collect_or_load_paused_session_snapshot"
        return "inspect_attach_readiness_blockers"

    @classmethod
    def _callframes(
        cls,
        spec: PausedSessionTargetAttachReadinessSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if registry_entry and isinstance(registry_entry.get("paused_events"), list):
            return BreakpointManager._callframes_from_paused(registry_entry["paused_events"])
        durable_frames = durable_snapshot.get("callframes")
        if isinstance(durable_frames, list):
            return [item for item in durable_frames if isinstance(item, dict)]
        return list(spec.callframes)

    @classmethod
    def _expected_url(
        cls,
        spec: PausedSessionTargetAttachReadinessSpec,
        callframes: list[dict[str, Any]],
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
    ) -> str | None:
        if spec.expected_url:
            return spec.expected_url
        selected = cls._selected_callframe(spec, callframes)
        location = selected.get("location") if isinstance(selected.get("location"), dict) else {}
        for value in (
            selected.get("url"),
            location.get("url"),
            spec.debugger_session.get("url"),
            spec.debugger_session.get("page_url"),
            durable_snapshot.get("url"),
            durable_snapshot.get("page_url"),
            registry_entry.get("page").url if registry_entry and registry_entry.get("page") is not None and hasattr(registry_entry.get("page"), "url") else None,
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _selected_callframe(spec: PausedSessionTargetAttachReadinessSpec, callframes: list[dict[str, Any]]) -> dict[str, Any]:
        if spec.callframe_index < 0 or spec.callframe_index >= len(callframes):
            return {}
        return callframes[spec.callframe_index]

    @classmethod
    def _selected_callframe_summary(cls, spec: PausedSessionTargetAttachReadinessSpec, callframes: list[dict[str, Any]]) -> dict[str, Any]:
        frame = cls._selected_callframe(spec, callframes)
        if not frame:
            return {}
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        return {
            "function_name": frame.get("functionName") or frame.get("function_name") or frame.get("name"),
            "url": frame.get("url") or location.get("url"),
            "line_number": location.get("lineNumber", location.get("line_number")),
            "column_number": location.get("columnNumber", location.get("column_number")),
            "has_callframe_id": bool(frame.get("callFrameId") or frame.get("callframe_id") or frame.get("callFrameID")),
        }

    @classmethod
    def _selected_target_candidate(cls, spec: PausedSessionTargetAttachReadinessSpec, expected_url: str | None) -> dict[str, Any]:
        if not expected_url:
            return {}
        normalized_expected = cls._normalize_url(expected_url)
        for candidate in spec.target_candidates:
            candidate_url = candidate.get("url") or candidate.get("targetUrl") or candidate.get("target_url")
            if not isinstance(candidate_url, str):
                continue
            normalized_candidate = cls._normalize_url(candidate_url)
            if normalized_candidate == normalized_expected or normalized_expected.startswith(normalized_candidate) or normalized_candidate.startswith(normalized_expected):
                return candidate
        return {}

    @staticmethod
    def _normalize_url(value: str) -> str:
        return value.split("#", 1)[0].rstrip("/")

    @staticmethod
    def _target_id(target: dict[str, Any]) -> str:
        value = target.get("targetId") or target.get("target_id") or target.get("id")
        return str(value).strip() if value is not None else ""

    @classmethod
    def _target_summary(cls, target: dict[str, Any]) -> dict[str, Any]:
        if not target:
            return {}
        return {
            "target_id": cls._target_id(target),
            "type": target.get("type") or target.get("targetType") or target.get("target_type"),
            "url": target.get("url") or target.get("targetUrl") or target.get("target_url"),
            "attached": _optional_bool(target.get("attached")),
            "browser_context_id": target.get("browserContextId") or target.get("browser_context_id"),
        }

    @classmethod
    def _target_attachable(cls, target: dict[str, Any]) -> bool:
        if not target:
            return False
        target_type = str(target.get("type") or target.get("targetType") or target.get("target_type") or "page").strip().lower()
        return target_type in {"page", "webview", "iframe", "service_worker", "worker"}

    @classmethod
    def _stable_live_callframe_available(
        cls,
        spec: PausedSessionTargetAttachReadinessSpec,
        *,
        source: str,
        registry_entry: dict[str, Any] | None,
        callframes: list[dict[str, Any]],
    ) -> bool:
        return source == "registry" and bool(registry_entry) and bool(cls._selected_callframe_summary(spec, callframes).get("has_callframe_id"))

    @classmethod
    def _requested_action_requires_live_callframe(cls, spec: PausedSessionTargetAttachReadinessSpec) -> bool:
        return spec.requested_action in {"evaluate", "evaluate_on_callframe", "eval"}

    @staticmethod
    def _debugger_lifecycle(
        spec: PausedSessionTargetAttachReadinessSpec,
        *,
        durable_snapshot: dict[str, Any],
        registry_entry: dict[str, Any],
    ) -> str:
        for source in (
            registry_entry.get("debugger_session") if isinstance(registry_entry.get("debugger_session"), dict) else {},
            durable_snapshot.get("debugger_session") if isinstance(durable_snapshot.get("debugger_session"), dict) else {},
            spec.debugger_session,
        ):
            lifecycle = source.get("lifecycle") or source.get("status")
            if lifecycle:
                return str(lifecycle)
        return "unknown"

    @staticmethod
    def _continuation_preflight(
        spec: PausedSessionTargetAttachReadinessSpec,
        *,
        durable_snapshot: dict[str, Any],
        registry_entry: dict[str, Any],
    ) -> dict[str, Any]:
        if spec.continuation_preflight:
            return dict(spec.continuation_preflight)
        if isinstance(durable_snapshot.get("continuation_preflight"), dict):
            return dict(durable_snapshot["continuation_preflight"])
        if registry_entry and isinstance(registry_entry.get("debugger_session"), dict):
            preflight = registry_entry["debugger_session"].get("continuation_preflight")
            if isinstance(preflight, dict):
                return dict(preflight)
        return {}


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
class PausedSessionLiveCallframeRecoverySpec:
    """Read-only proof that a fresh live callFrame is available after attach probing."""

    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    cross_process_execution_plan: dict[str, Any] = field(default_factory=dict)
    paused_event: dict[str, Any] = field(default_factory=dict)
    debugger_session: dict[str, Any] = field(default_factory=dict)
    callframes: list[dict[str, Any]] = field(default_factory=list)
    pause_session_id: str | None = None
    requested_action: str = "inspect"
    target_id: str | None = None
    callframe_index: int = 0
    fresh_paused_event_after_attach: bool = False
    require_fresh_paused_event: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "PausedSessionLiveCallframeRecoverySpec | None":
        context = context or {}
        requested = bool(
            context.get("paused_session_live_callframe_recovery")
            or context.get("pausedSessionLiveCallframeRecovery")
            or context.get("paused-session-live-callframe-recovery")
            or context.get("cross_process_live_callframe_recovery")
            or context.get("crossProcessLiveCallframeRecovery")
            or context.get("recover_live_callframe_after_attach")
            or context.get("recoverLiveCallframeAfterAttach")
        )
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        plan_container = _first_dict(
            context,
            "paused_session_cross_process_execution_plan",
            "pausedSessionCrossProcessExecutionPlan",
            "paused-session-cross-process-execution-plan",
            "cross_process_execution_plan",
            "crossProcessExecutionPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        paused = _first_dict(
            context,
            "debugger_paused",
            "debuggerPaused",
            "paused",
            "paused_event",
            "pausedEvent",
            "debugger-paused",
        )
        session = _first_dict(context, "debugger_session", "debuggerSession", "debugger-session")
        callframes = cls._callframes_from_context(context, paused=paused, session=session)
        if not requested and not attach_probe and not callframes and not paused:
            return None
        action = str(
            context.get(
                "requested_action",
                context.get("requestedAction", attach_probe.get("requested_action", plan.get("requested_action", "inspect"))),
            )
            or "inspect"
        ).strip().replace("-", "_").lower()
        target_id = context.get("target_id") or context.get("targetId") or attach_probe.get("target_id") or cls._target_id_from_plan(plan)
        pause_session_id = (
            context.get("pause_session_id")
            or context.get("pauseSessionId")
            or attach_probe.get("pause_session_id")
            or plan.get("pause_session_id")
            or session.get("pause_session_id")
            or session.get("session_id")
        )
        fresh = bool(
            context.get("fresh_paused_event_after_attach")
            or context.get("freshPausedEventAfterAttach")
            or context.get("paused_event_after_attach")
            or context.get("pausedEventAfterAttach")
            or paused.get("fresh_paused_event_after_attach")
            or paused.get("paused_event_after_attach")
            or paused.get("captured_after_attach")
            or session.get("fresh_paused_event_after_attach")
        )
        require_raw = context.get("require_fresh_paused_event", context.get("requireFreshPausedEvent", True))
        try:
            callframe_index = int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0)
        except (TypeError, ValueError):
            callframe_index = 0
        return cls(
            cross_process_attach_probe=attach_probe,
            cross_process_execution_plan=plan,
            paused_event=paused,
            debugger_session=session,
            callframes=callframes,
            pause_session_id=str(pause_session_id) if pause_session_id else None,
            requested_action=action,
            target_id=str(target_id).strip() if target_id else None,
            callframe_index=max(0, callframe_index),
            fresh_paused_event_after_attach=fresh,
            require_fresh_paused_event=bool(require_raw),
        )

    @staticmethod
    def _target_id_from_plan(plan: dict[str, Any]) -> str:
        summary = plan.get("target_attach_readiness_summary") if isinstance(plan.get("target_attach_readiness_summary"), dict) else {}
        selected = summary.get("selected_target") if isinstance(summary.get("selected_target"), dict) else {}
        value = selected.get("target_id") or selected.get("targetId") or selected.get("id")
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _callframes_from_context(context: dict[str, Any], *, paused: dict[str, Any], session: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = (
            context.get("callframes"),
            context.get("callFrames"),
            paused.get("callFrames"),
            paused.get("callframes"),
            session.get("callframes"),
            session.get("callFrames"),
        )
        for value in candidates:
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("callFrames") or value.get("callframes") or value.get("items")
                if isinstance(nested, list):
                    return [dict(item) for item in nested if isinstance(item, dict)]
        return []


@dataclass(slots=True)
class PausedSessionLiveCallframeRecoveryResult:
    status: str
    recovery: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "recovery": self.recovery,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class PausedSessionLiveCallframeRecoveryManager:
    """Review provided paused/callframe evidence after attach probing without sending CDP commands."""

    def recover(self, spec: PausedSessionLiveCallframeRecoverySpec | None) -> PausedSessionLiveCallframeRecoveryResult:
        blockers = self._blockers(spec)
        status = "recovered" if not blockers else "blocked"
        payload = self._payload(spec, status=status, blockers=blockers)
        return PausedSessionLiveCallframeRecoveryResult(
            status=status,
            recovery=payload,
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: PausedSessionLiveCallframeRecoverySpec | None) -> list[str]:
        if spec is None:
            return ["live_callframe_recovery_request_missing"]
        blockers: list[str] = []
        probe = spec.cross_process_attach_probe
        if not probe:
            blockers.append("cross_process_attach_probe_required")
        elif probe.get("status") != "attached" or not probe.get("target_attached"):
            blockers.append("cross_process_target_not_attached")
        if not spec.target_id:
            blockers.append("target_id_required")
        if not spec.callframes:
            blockers.append("fresh_paused_callframes_required")
        elif spec.callframe_index >= len(spec.callframes):
            blockers.append("selected_callframe_index_out_of_range")
        else:
            selected = spec.callframes[spec.callframe_index]
            if not cls._callframe_id(selected):
                blockers.append("live_callframe_id_required")
        if spec.require_fresh_paused_event and not spec.fresh_paused_event_after_attach:
            blockers.append("fresh_paused_event_after_attach_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(cls, spec: PausedSessionLiveCallframeRecoverySpec | None, *, status: str, blockers: list[str]) -> dict[str, Any]:
        selected = cls._selected_callframe(spec)
        callframe_id = cls._callframe_id(selected)
        probe = spec.cross_process_attach_probe if spec else {}
        return {
            "schema_version": "reverse-deepagent.paused-session-live-callframe-recovery.v1",
            "status": status,
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": spec.requested_action if spec else None,
            "target_id": spec.target_id if spec else None,
            "attach_probe_status": probe.get("status"),
            "target_attached": bool(probe.get("target_attached")),
            "attached_session_id": probe.get("attached_session_id"),
            "target_detached": bool(probe.get("target_detached")),
            "fresh_paused_event_after_attach": bool(spec and spec.fresh_paused_event_after_attach),
            "require_fresh_paused_event": bool(spec.require_fresh_paused_event) if spec else True,
            "callframe_count": len(spec.callframes) if spec else 0,
            "selected_callframe_index": spec.callframe_index if spec else 0,
            "selected_callframe": cls._callframe_summary(selected),
            "selected_callframe_has_id": bool(callframe_id),
            "live_callframe_id": callframe_id,
            "live_callframe_recovered": status == "recovered",
            "debugger_domain_enabled": False,
            "live_action_executed": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "one_action_executor_ready_for_review": status == "recovered",
            "cross_process_action_executed": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _selected_callframe(spec: PausedSessionLiveCallframeRecoverySpec | None) -> dict[str, Any]:
        if not spec or not spec.callframes or spec.callframe_index >= len(spec.callframes):
            return {}
        return spec.callframes[spec.callframe_index]

    @staticmethod
    def _callframe_id(callframe: dict[str, Any]) -> str:
        value = callframe.get("callFrameId") or callframe.get("callframe_id") or callframe.get("id")
        return str(value).strip() if value is not None else ""

    @classmethod
    def _callframe_summary(cls, callframe: dict[str, Any]) -> dict[str, Any]:
        if not callframe:
            return {}
        location = callframe.get("location") if isinstance(callframe.get("location"), dict) else {}
        return {
            "callFrameId": cls._callframe_id(callframe),
            "functionName": str(callframe.get("functionName") or callframe.get("function_name") or callframe.get("name") or "anonymous"),
            "url": str(callframe.get("url") or location.get("url") or ""),
            "lineNumber": location.get("lineNumber", location.get("line_number")),
            "columnNumber": location.get("columnNumber", location.get("column_number")),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "cdp_target_detached": False,
            "debugger_domain_enabled": False,
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
            "live_callframe_recovery_request_missing": ("request", "No live callFrame recovery request was provided.", "request_live_callframe_recovery"),
            "cross_process_attach_probe_required": ("attach_probe", "A reviewed cross-process attach probe artifact is required before callFrame recovery review.", "run_reviewed_cross_process_attach_probe"),
            "cross_process_target_not_attached": ("attach_probe", "The attach probe did not prove a target attachment.", "rerun_or_review_cross_process_attach_probe"),
            "target_id_required": ("cdp_target", "A target id is required to correlate the recovered callFrame to the attached target.", "provide_target_id_for_callframe_recovery"),
            "fresh_paused_callframes_required": ("debugger", "Fresh paused callFrames after the attach probe are required.", "capture_new_paused_event_after_attach"),
            "selected_callframe_index_out_of_range": ("debugger", "The selected callFrame index is not present in the provided paused event.", "select_available_live_callframe"),
            "live_callframe_id_required": ("debugger", "The selected callFrame does not include a live callFrameId.", "capture_stable_live_callframe_id"),
            "fresh_paused_event_after_attach_required": ("debugger", "The provided callFrames are not marked as a fresh paused event after attach.", "capture_new_paused_event_after_attach"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_live_callframe_recovery"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_live_callframe_recovery"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_live_callframe_recovery"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str]) -> str:
        if status == "recovered":
            return "plan_cross_process_one_action_executor"
        if any(item in blockers for item in ("fresh_paused_callframes_required", "fresh_paused_event_after_attach_required", "live_callframe_id_required")):
            return "capture_new_paused_event_after_attach"
        if "cross_process_attach_probe_required" in blockers or "cross_process_target_not_attached" in blockers:
            return "run_reviewed_cross_process_attach_probe"
        return "inspect_live_callframe_recovery_blockers"


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


class PausedSessionLiveContinuationPreflightManager:
    """Inspect whether a paused session can be live-continued without sending CDP commands."""

    LIVE_ACTIONS = PAUSED_SESSION_LIVE_ACTIONS

    def preflight(self, spec: PausedSessionLiveContinuationPreflightSpec | None) -> PausedSessionLiveContinuationPreflightResult:
        policy = self._side_effect_policy()
        if spec is None or not spec.pause_session_id:
            preflight = self._preflight_payload(
                spec=None,
                source="missing",
                durable_snapshot={},
                registry_entry={},
                blockers=["live_paused_session_required", "target_not_attached", "debugger_session_not_live", "cdp_target_unavailable"],
            )
            return PausedSessionLiveContinuationPreflightResult(status="unavailable", preflight=preflight, side_effect_policy=policy, reason="missing_pause_session_id")

        registry_entry = BreakpointManager._paused_sessions.get(spec.pause_session_id)
        durable_snapshot = self._load_durable_snapshot(spec)
        source = "registry" if registry_entry else "durable_snapshot" if durable_snapshot else "provided_artifact" if any((spec.debugger_session, spec.paused, spec.callframes)) else "missing"
        blockers = self._blockers(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot, source=source)
        if blockers:
            live_action = spec.requested_action in self.LIVE_ACTIONS or spec.require_live_action
            inspect_supported = bool(durable_snapshot or registry_entry or spec.debugger_session or spec.paused or spec.callframes)
            status = "blocked" if live_action else "inspect_only" if inspect_supported else "unavailable"
        else:
            status = "live_available"
        preflight = self._preflight_payload(spec=spec, source=source, durable_snapshot=durable_snapshot, registry_entry=registry_entry or {}, blockers=blockers)
        reason = blockers[0] if blockers else None
        return PausedSessionLiveContinuationPreflightResult(status=status, preflight=preflight, side_effect_policy=policy, reason=reason)

    @classmethod
    def _blockers(
        cls,
        spec: PausedSessionLiveContinuationPreflightSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
        source: str,
    ) -> list[str]:
        blockers: list[str] = []
        live_action = spec.requested_action in cls.LIVE_ACTIONS or spec.require_live_action
        debugger_session = cls._debugger_session(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot)
        lifecycle = str(debugger_session.get("lifecycle") or "")
        target_attached = cls._target_attached(spec, source=source, registry_entry=registry_entry)
        cdp_target_available = cls._cdp_target_available(spec, source=source, registry_entry=registry_entry)
        live_session_available = bool(registry_entry) and lifecycle != "resumed"
        if live_action and not live_session_available:
            blockers.append("live_paused_session_required")
        if not target_attached:
            blockers.append("target_not_attached")
        if not live_session_available:
            blockers.append("debugger_session_not_live")
        if not cdp_target_available:
            blockers.append("cdp_target_unavailable")
        if live_action and cls._requires_stable_callframe(spec) and not cls._stable_callframe_available(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot, source=source):
            blockers.append("callframe_id_not_stable")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _load_durable_snapshot(spec: PausedSessionLiveContinuationPreflightSpec) -> dict[str, Any]:
        path = BreakpointManager._paused_session_store_path(spec.pause_session_id, spec.paused_session_store_dir)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _preflight_payload(
        cls,
        *,
        spec: PausedSessionLiveContinuationPreflightSpec | None,
        source: str,
        durable_snapshot: dict[str, Any],
        registry_entry: dict[str, Any],
        blockers: list[str],
    ) -> dict[str, Any]:
        debugger_session = cls._debugger_session(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot) if spec else {}
        callframes = cls._callframes(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot) if spec else []
        lifecycle = str(debugger_session.get("lifecycle") or "")
        same_process_registry = source == "registry" and bool(registry_entry)
        target_attached = cls._target_attached(spec, source=source, registry_entry=registry_entry) if spec else False
        cdp_target_available = cls._cdp_target_available(spec, source=source, registry_entry=registry_entry) if spec else False
        live_available = same_process_registry and lifecycle != "resumed" and target_attached and cdp_target_available and not blockers
        live_action = bool(spec and (spec.requested_action in cls.LIVE_ACTIONS or spec.require_live_action))
        inspect_supported = bool(durable_snapshot or same_process_registry or callframes)
        stable_callframe_required = bool(spec and cls._requires_stable_callframe(spec))
        selected_callframe_has_id = cls._selected_callframe_has_id(spec, callframes) if spec else False
        stable_callframe_available = same_process_registry and selected_callframe_has_id
        selected_callframe = cls._selected_callframe_summary(spec, callframes) if spec else {}
        payload_status = "live_available" if live_available else "blocked" if blockers and live_action else "inspect_only" if inspect_supported else "unavailable"
        return {
            "schema_version": "reverse-deepagent.paused-session-live-continuation-preflight.v1",
            "status": payload_status,
            "source": source,
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": spec.requested_action if spec else None,
            "same_process_registry": same_process_registry,
            "durable_snapshot_found": bool(durable_snapshot),
            "provided_artifact_found": bool(spec and any((spec.debugger_session, spec.paused, spec.callframes))),
            "target_attached": target_attached,
            "cdp_target_available": cdp_target_available,
            "pre_action_lifecycle": lifecycle or "unknown",
            "live_continuation_available": live_available,
            "cross_process_live_continuation_supported": False,
            "inspect_supported": inspect_supported,
            "evaluate_supported": live_available,
            "step_supported": live_available,
            "resume_supported": live_available,
            "callframe_count": len(callframes),
            "selected_callframe_has_id": selected_callframe_has_id,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(live_available=live_available, blockers=blockers),
            "live_session_diagnostics": {
                "same_process_registry": same_process_registry,
                "registry_entry_found": bool(registry_entry),
                "durable_snapshot_found": bool(durable_snapshot),
                "provided_artifact_found": bool(spec and any((spec.debugger_session, spec.paused, spec.callframes))),
                "debugger_session_lifecycle": lifecycle or "unknown",
                "live_session_available": same_process_registry and lifecycle != "resumed",
                "cross_process_live_continuation_supported": False,
                "cross_process_resume_supported": False,
                "cross_process_step_supported": False,
                "cross_process_evaluate_supported": False,
                "same_process_required_for_live_action": True,
            },
            "target_diagnostics": {
                "target_attached": target_attached,
                "cdp_target_available": cdp_target_available,
                "target_attached_source": "explicit_context" if spec and spec.target_attached is not None else "same_process_registry" if same_process_registry else "not_attached",
                "cdp_target_available_source": "explicit_context" if spec and spec.cdp_target_available is not None else "same_process_registry" if same_process_registry else "not_available",
                "would_attach_cdp_target": False,
                "would_probe_cdp_target": False,
            },
            "callframe_diagnostics": {
                "stable_callframe_required": stable_callframe_required,
                "stable_callframe_available": stable_callframe_available,
                "selected_callframe_has_id": selected_callframe_has_id,
                "selected_callframe_index": spec.callframe_index if spec else None,
                "selected_callframe": selected_callframe,
                "callframe_count": len(callframes),
                "evaluate_requires_live_callframe": bool(spec and spec.requested_action in {"evaluate", "evaluate_on_callframe", "eval"}),
            },
            "action_capability": {
                "requested_action": spec.requested_action if spec else None,
                "is_live_action": live_action,
                "inspect_supported": inspect_supported,
                "evaluate_supported": live_available,
                "step_supported": live_available,
                "resume_supported": live_available,
                "reason": blockers[0] if blockers else None,
            },
            "required_for_live": [
                "same_process_registry",
                "active_cdp_session",
                "attached_cdp_target",
                "retained_paused_lifecycle",
                "stable_callframe_id_for_evaluate",
            ],
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "live_paused_session_required": {
                "category": "session_lifecycle",
                "explanation": "Live resume, step, or callframe evaluation requires a retained same-process paused session.",
                "next_action": "reproduce_pause_in_current_process_before_live_action",
            },
            "target_not_attached": {
                "category": "cdp_target",
                "explanation": "No currently attached CDP target is proven for this paused session.",
                "next_action": "reproduce_pause_with_attached_browser_target",
            },
            "debugger_session_not_live": {
                "category": "session_lifecycle",
                "explanation": "The available evidence is a durable snapshot, provided artifact, missing session, or already-resumed session rather than a live registry entry.",
                "next_action": "use_same_process_registry_entry_or_limit_to_inspect_only",
            },
            "cdp_target_unavailable": {
                "category": "cdp_target",
                "explanation": "No live CDP session/target is available for sending debugger continuation commands.",
                "next_action": "reproduce_pause_against_a_live_cdp_capable_provider",
            },
            "callframe_id_not_stable": {
                "category": "callframe",
                "explanation": "Callframe evaluation requires a stable live callFrameId from the retained paused event.",
                "next_action": "reproduce_pause_and_capture_stable_live_callframe",
            },
        }
        return [{"code": blocker, **catalog.get(blocker, {"category": "unknown", "explanation": blocker, "next_action": "inspect_preflight_blocker"})} for blocker in blockers]

    @staticmethod
    def _selected_callframe_summary(spec: PausedSessionLiveContinuationPreflightSpec, callframes: list[dict[str, Any]]) -> dict[str, Any]:
        if spec.callframe_index < 0 or spec.callframe_index >= len(callframes):
            return {}
        frame = callframes[spec.callframe_index]
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        return {
            "function_name": frame.get("functionName") or frame.get("function_name") or frame.get("name"),
            "url": frame.get("url") or location.get("url"),
            "line_number": location.get("lineNumber", location.get("line_number")),
            "column_number": location.get("columnNumber", location.get("column_number")),
            "has_callframe_id": bool(frame.get("callFrameId")),
        }

    @staticmethod
    def _next_action(*, live_available: bool, blockers: list[str]) -> str:
        if live_available:
            return "continue_with_same_process_paused_session_action"
        if "callframe_id_not_stable" in blockers:
            return "reproduce_pause_and_capture_stable_live_callframe"
        if "live_paused_session_required" in blockers:
            return "reproduce_pause_in_current_process_before_live_action"
        return "inspect_snapshot_or_collect_fresh_pause_artifacts"

    @staticmethod
    def _debugger_session(
        spec: PausedSessionLiveContinuationPreflightSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        if registry_entry and isinstance(registry_entry.get("debugger_session"), dict):
            return dict(registry_entry["debugger_session"])
        if isinstance(durable_snapshot.get("debugger_session"), dict):
            return dict(durable_snapshot["debugger_session"])
        return dict(spec.debugger_session)

    @staticmethod
    def _callframes(
        spec: PausedSessionLiveContinuationPreflightSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if registry_entry and isinstance(registry_entry.get("paused_events"), list):
            return BreakpointManager._callframes_from_paused(registry_entry["paused_events"])
        durable_frames = durable_snapshot.get("callframes")
        if isinstance(durable_frames, list):
            return [item for item in durable_frames if isinstance(item, dict)]
        return list(spec.callframes)

    @staticmethod
    def _target_attached(
        spec: PausedSessionLiveContinuationPreflightSpec | None,
        *,
        source: str,
        registry_entry: dict[str, Any] | None,
    ) -> bool:
        if spec and spec.target_attached is not None:
            return spec.target_attached
        return source == "registry" and bool(registry_entry)

    @staticmethod
    def _cdp_target_available(
        spec: PausedSessionLiveContinuationPreflightSpec | None,
        *,
        source: str,
        registry_entry: dict[str, Any] | None,
    ) -> bool:
        if spec and spec.cdp_target_available is not None:
            return spec.cdp_target_available
        return source == "registry" and bool(registry_entry)

    @classmethod
    def _requires_stable_callframe(cls, spec: PausedSessionLiveContinuationPreflightSpec) -> bool:
        return spec.requested_action in {"evaluate", "evaluate_on_callframe", "eval"} or bool(spec.callframes)

    @classmethod
    def _stable_callframe_available(
        cls,
        spec: PausedSessionLiveContinuationPreflightSpec,
        *,
        registry_entry: dict[str, Any] | None,
        durable_snapshot: dict[str, Any],
        source: str,
    ) -> bool:
        if source != "registry" or not registry_entry:
            return False
        return cls._selected_callframe_has_id(spec, cls._callframes(spec, registry_entry=registry_entry, durable_snapshot=durable_snapshot))

    @staticmethod
    def _selected_callframe_has_id(spec: PausedSessionLiveContinuationPreflightSpec, callframes: list[dict[str, Any]]) -> bool:
        if spec.callframe_index < 0 or spec.callframe_index >= len(callframes):
            return False
        return bool(callframes[spec.callframe_index].get("callFrameId"))

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


class BreakpointManager:
    """Set CDP breakpoints behind a provider-neutral capability gate."""

    _paused_sessions: dict[str, dict[str, Any]] = {}

    @classmethod
    def clear_paused_sessions(cls) -> None:
        cls._paused_sessions.clear()

    def set_breakpoint(self, page: BrowserPage, spec: BreakpointSpec | None) -> BreakpointResult:
        if spec is None:
            return BreakpointResult(status="unsupported", supported=False, reason="missing_url_pattern")
        session = page.cdp_session()
        if session is None:
            return BreakpointResult(status="unsupported", supported=False, reason="cdp_session_unavailable")
        paused_events: list[dict[str, Any]] = []
        pause_subscription = self._subscribe_paused(session, paused_events, spec=spec)
        trigger: dict[str, Any] = {"attempted": False}
        try:
            session.send("Debugger.enable", {})
            payload = session.send("Debugger.setBreakpointByUrl", spec.to_cdp_params())
            trigger = self._run_trigger_expression(page, session, spec)
        except Exception as exc:
            breakpoints: list[dict[str, Any]] = []
            debugger_session = self._debugger_session_snapshot(paused_events, spec)
            evaluations = self._evaluations_from_paused(paused_events)
            return BreakpointResult(
                status="failed",
                supported=True,
                breakpoints=breakpoints,
                paused=self._paused_summary(paused_events, pause_subscription),
                callframes=self._callframes_from_paused(paused_events),
                callframe_evaluations=evaluations,
                mutation_audit=self._mutation_audit_from_evaluations(evaluations),
                debugger_actions=self._debugger_actions_from_paused(paused_events),
                debugger_session=debugger_session,
                debugger_timeline=self._debugger_timeline(paused_events, spec, trigger, breakpoints, debugger_session, error=str(exc)),
                trigger=trigger,
                error=str(exc),
            )
        breakpoint_id = payload.get("breakpointId") if isinstance(payload, dict) else None
        locations = payload.get("locations", []) if isinstance(payload, dict) else []
        paused = self._paused_summary(paused_events, pause_subscription)
        callframes = self._callframes_from_paused(paused_events)
        evaluations = self._evaluations_from_paused(paused_events)
        mutation_audit = self._mutation_audit_from_evaluations(evaluations)
        debugger_actions = self._debugger_actions_from_paused(paused_events)
        debugger_session = self._debugger_session_snapshot(paused_events, spec)
        breakpoints = [
            {
                "breakpointId": breakpoint_id,
                "urlPattern": spec.url_pattern,
                "lineNumber": spec.line_number,
                "columnNumber": spec.column_number,
                "condition": spec.condition,
                "locations": locations if isinstance(locations, list) else [],
            }
        ]
        result = BreakpointResult(
            status="success" if breakpoint_id else "partial",
            supported=True,
            breakpoints=breakpoints,
            paused=paused,
            callframes=callframes,
            callframe_evaluations=evaluations,
            mutation_audit=mutation_audit,
            debugger_actions=debugger_actions,
            debugger_session=debugger_session,
            debugger_timeline=self._debugger_timeline(paused_events, spec, trigger, breakpoints, debugger_session),
            trigger=trigger,
        )
        self._maybe_store_paused_session(session, page, spec, paused_events, pause_subscription, trigger, breakpoints, debugger_session)
        return result

    def run_paused_session_action(self, page: BrowserPage, spec: PausedSessionActionSpec | None) -> BreakpointResult:
        if spec is None:
            preflight = self._missing_paused_session_preflight(reason="missing_pause_session_id")
            return BreakpointResult(status="unsupported", supported=False, reason="missing_pause_session_id", continuation_preflight=preflight)
        entry = self._paused_sessions.get(spec.pause_session_id)
        if not entry:
            durable = self._load_durable_paused_session(spec)
            if durable is not None:
                return self._durable_paused_session_result(durable, spec)
            preflight = self._missing_paused_session_preflight(reason="pause_session_not_found", spec=spec)
            return BreakpointResult(status="unsupported", supported=False, reason="pause_session_not_found", continuation_preflight=preflight)
        preflight = self._registry_paused_session_preflight(spec, entry)
        session = entry["session"]
        paused_events = entry["paused_events"]
        base_spec = entry["spec"]
        breakpoints = entry.get("breakpoints", [])
        action_breakpoint_spec = spec.to_breakpoint_spec(base_spec)
        evaluations: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        error: str | None = None
        if spec.callframe_evaluations:
            evaluations = self._evaluate_callframe_expressions(session, self._callframes_from_paused(paused_events), action_breakpoint_spec)
            if paused_events:
                paused_events[0].setdefault("evaluations", []).extend(evaluations)
        if spec.debugger_actions:
            actions = self._run_debugger_actions(session, action_breakpoint_spec)
            if paused_events:
                paused_events[0].setdefault("debugger_actions", []).extend(actions)
            self._wait_after_trigger(entry.get("page") or page, spec.wait_after_action_ms)
        if spec.action == "inspect" and not evaluations and not actions:
            pass
        elif spec.action not in {"inspect", "evaluate", "eval", "resume", "step_over", "stepover", "over", "step_into", "stepinto", "into", "step_out", "stepout", "out"}:
            error = "unsupported_paused_session_action"
        base_debugger_session = self._debugger_session_snapshot(paused_events, action_breakpoint_spec)
        mutation_audit = self._mutation_audit_from_evaluations(evaluations)
        lifecycle = self._continued_pause_lifecycle(base_debugger_session, actions)
        base_debugger_session["lifecycle"] = lifecycle
        base_debugger_session["continued_from_registry"] = True
        base_debugger_session["registry_active"] = lifecycle != "resumed"
        base_debugger_session["live_continuation_available"] = lifecycle != "resumed"
        base_debugger_session["resume_supported"] = lifecycle != "resumed"
        preflight["action_supported"] = error is None
        preflight["post_action_lifecycle"] = lifecycle
        preflight["post_action_live_continuation_available"] = lifecycle != "resumed"
        if error:
            preflight["status"] = "action_blocked"
            preflight["blocked_action"] = True
            preflight["blocked_reason"] = error
            preflight["reason"] = error
        base_debugger_session["continuation_preflight"] = preflight
        timeline = self._debugger_timeline(paused_events, action_breakpoint_spec, {"attempted": False}, breakpoints, base_debugger_session, error=error)
        timeline["continued_from_registry"] = True
        timeline["registry_active"] = lifecycle != "resumed"
        timeline["live_continuation_available"] = lifecycle != "resumed"
        timeline["continuation_preflight"] = preflight
        action_entries = self._debugger_action_timeline_entries(actions, start_index=len(timeline["entries"]))
        timeline["entries"].extend(action_entries)
        timeline["entry_count"] = len(timeline["entries"])
        timeline["debugger_action_count"] = sum(
            len(event.get("debugger_actions", [])) for event in paused_events if isinstance(event.get("debugger_actions"), list)
        )
        if lifecycle == "resumed":
            self._paused_sessions.pop(spec.pause_session_id, None)
        else:
            entry["debugger_session"] = base_debugger_session
            entry["debugger_timeline"] = timeline
        return BreakpointResult(
            status="failed" if error else "success",
            supported=True,
            breakpoints=breakpoints,
            paused=self._paused_summary(paused_events, {"supported": True, "source": "paused_session_registry"}),
            callframes=self._callframes_from_paused(paused_events),
            callframe_evaluations=evaluations,
            mutation_audit=mutation_audit,
            debugger_actions=actions,
            debugger_session=base_debugger_session,
            debugger_timeline=timeline,
            trigger={"attempted": False},
            continuation_preflight=preflight,
            error=error,
            reason=None if not error else error,
        )

    def _maybe_store_paused_session(
        self,
        session: Any,
        page: BrowserPage,
        spec: BreakpointSpec,
        paused_events: list[dict[str, Any]],
        pause_subscription: dict[str, Any],
        trigger: dict[str, Any],
        breakpoints: list[dict[str, Any]],
        debugger_session: dict[str, Any],
    ) -> None:
        session_id = debugger_session.get("session_id")
        lifecycle = debugger_session.get("lifecycle")
        if not session_id or not paused_events or lifecycle not in {"retained_paused", "action_controlled"}:
            return
        timeline = self._debugger_timeline(paused_events, spec, trigger, breakpoints, debugger_session)
        self._paused_sessions[str(session_id)] = {
            "session": session,
            "page": page,
            "spec": spec,
            "paused_events": paused_events,
            "pause_subscription": pause_subscription,
            "breakpoints": breakpoints,
            "debugger_session": debugger_session,
            "debugger_timeline": timeline,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._maybe_store_durable_paused_session(spec, paused_events, pause_subscription, trigger, breakpoints, debugger_session, timeline)

    def _maybe_store_durable_paused_session(
        self,
        spec: BreakpointSpec,
        paused_events: list[dict[str, Any]],
        pause_subscription: dict[str, Any],
        trigger: dict[str, Any],
        breakpoints: list[dict[str, Any]],
        debugger_session: dict[str, Any],
        timeline: dict[str, Any],
    ) -> None:
        if not spec.persist_paused_session and not spec.paused_session_store_dir:
            return
        session_id = str(debugger_session.get("session_id") or self._default_pause_session_id(spec))
        now = time.time()
        payload = {
            "schema_version": 1,
            "kind": "durable_paused_session_snapshot",
            "created_at": now,
            "updated_at": now,
            "session_id": session_id,
            "live_continuation_available": False,
            "resume_supported": False,
            "reason": "durable snapshot is inspect-only; live CDP continuation requires same-process registry",
            "continuation_preflight": self._durable_paused_session_preflight(
                session_id=session_id,
                callframes=self._callframes_from_paused(paused_events),
                lifecycle=str(debugger_session.get("lifecycle") or "retained_paused"),
            ),
            "breakpoints": breakpoints,
            "paused": self._paused_summary(paused_events, pause_subscription),
            "callframes": self._callframes_from_paused(paused_events),
            "debugger_session": debugger_session,
            "debugger_timeline": timeline,
            "trigger": trigger,
        }
        store_path = self._paused_session_store_path(session_id, spec.paused_session_store_dir)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _load_durable_paused_session(self, spec: PausedSessionActionSpec) -> dict[str, Any] | None:
        store_path = self._paused_session_store_path(spec.pause_session_id, spec.paused_session_store_dir)
        if not store_path.exists():
            return None
        try:
            payload = json.loads(store_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _durable_paused_session_result(self, payload: dict[str, Any], spec: PausedSessionActionSpec) -> BreakpointResult:
        inspect_only = spec.action in {"inspect", "snapshot", "view"} and not spec.callframe_evaluations and not spec.debugger_actions
        stored_preflight = payload.get("continuation_preflight") if isinstance(payload.get("continuation_preflight"), dict) else None
        preflight = dict(stored_preflight) if stored_preflight else self._durable_paused_session_preflight(session_id=str(payload.get("session_id") or spec.pause_session_id))
        preflight.update({"requested_action": spec.action, "pause_session_id": spec.pause_session_id})
        if not inspect_only:
            preflight.update(
                {
                    "status": "action_blocked",
                    "blocked_action": True,
                    "blocked_reason": "live_paused_session_required",
                    "reason": "live_paused_session_required",
                }
            )
        debugger_session = dict(payload.get("debugger_session") if isinstance(payload.get("debugger_session"), dict) else {})
        debugger_session.update(
            {
                "continued_from_store": True,
                "live_continuation_available": False,
                "resume_supported": False,
                "durable_snapshot": True,
                "store_reason": payload.get("reason", "durable snapshot is inspect-only"),
                "continuation_preflight": preflight,
            }
        )
        timeline = dict(payload.get("debugger_timeline") if isinstance(payload.get("debugger_timeline"), dict) else {})
        timeline.update(
            {
                "continued_from_store": True,
                "live_continuation_available": False,
                "durable_snapshot": True,
                "continuation_preflight": preflight,
            }
        )
        base = {
            "supported": True,
            "breakpoints": self._list_of_dicts(payload.get("breakpoints")),
            "paused": payload.get("paused") if isinstance(payload.get("paused"), dict) else {},
            "callframes": self._list_of_dicts(payload.get("callframes")),
            "debugger_session": debugger_session,
            "debugger_timeline": timeline,
            "trigger": {"attempted": False},
            "continuation_preflight": preflight,
        }
        if inspect_only:
            return BreakpointResult(
                status="success",
                reason="durable_paused_session_snapshot_loaded",
                **base,
            )
        return BreakpointResult(
            status="failed",
            error="live_paused_session_required",
            reason="durable_snapshot_is_inspect_only",
            **base,
        )

    @staticmethod
    def _missing_paused_session_preflight(reason: str, spec: PausedSessionActionSpec | None = None) -> dict[str, Any]:
        blockers = ["live_paused_session_required", "target_not_attached", "debugger_session_not_live", "cdp_target_unavailable"]
        return {
            "status": "unavailable",
            "source": "missing",
            "pause_session_id": spec.pause_session_id if spec else None,
            "requested_action": spec.action if spec else None,
            "same_process_registry": False,
            "durable_snapshot_found": False,
            "target_attached": False,
            "live_continuation_available": False,
            "inspect_supported": False,
            "evaluate_supported": False,
            "step_supported": False,
            "resume_supported": False,
            "reason": reason,
            "blockers": blockers,
            "blocker_details": PausedSessionLiveContinuationPreflightManager._blocker_details(blockers),
            "live_session_diagnostics": {
                "same_process_registry": False,
                "registry_entry_found": False,
                "durable_snapshot_found": False,
                "provided_artifact_found": False,
                "debugger_session_lifecycle": "missing",
                "live_session_available": False,
                "cross_process_live_continuation_supported": False,
                "cross_process_resume_supported": False,
                "cross_process_step_supported": False,
                "cross_process_evaluate_supported": False,
                "same_process_required_for_live_action": True,
            },
            "target_diagnostics": {
                "target_attached": False,
                "cdp_target_available": False,
                "target_attached_source": "missing",
                "cdp_target_available_source": "missing",
                "would_attach_cdp_target": False,
                "would_probe_cdp_target": False,
            },
            "callframe_diagnostics": {
                "stable_callframe_required": bool(spec and spec.action in {"evaluate", "eval", "evaluate_on_callframe"}),
                "stable_callframe_available": False,
                "selected_callframe_has_id": False,
                "selected_callframe_index": spec.callframe_index if spec else None,
                "selected_callframe": {},
                "callframe_count": 0,
                "evaluate_requires_live_callframe": bool(spec and spec.action in {"evaluate", "eval", "evaluate_on_callframe"}),
            },
            "action_capability": {
                "requested_action": spec.action if spec else None,
                "is_live_action": bool(spec and spec.action in PausedSessionLiveContinuationPreflightManager.LIVE_ACTIONS),
                "inspect_supported": False,
                "evaluate_supported": False,
                "step_supported": False,
                "resume_supported": False,
                "reason": reason,
            },
        }

    @staticmethod
    def _registry_paused_session_preflight(spec: PausedSessionActionSpec, entry: dict[str, Any]) -> dict[str, Any]:
        debugger_session = entry.get("debugger_session") if isinstance(entry.get("debugger_session"), dict) else {}
        lifecycle = str(debugger_session.get("lifecycle") or "retained_paused")
        live_available = lifecycle != "resumed"
        callframes = BreakpointManager._callframes_from_paused(entry.get("paused_events", [])) if isinstance(entry.get("paused_events"), list) else []
        selected_has_id = 0 <= spec.callframe_index < len(callframes) and bool(callframes[spec.callframe_index].get("callFrameId"))
        selected_summary = {}
        if 0 <= spec.callframe_index < len(callframes):
            frame = callframes[spec.callframe_index]
            location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
            selected_summary = {
                "function_name": frame.get("functionName") or frame.get("function_name") or frame.get("name"),
                "url": frame.get("url") or location.get("url"),
                "line_number": location.get("lineNumber", location.get("line_number")),
                "column_number": location.get("columnNumber", location.get("column_number")),
                "has_callframe_id": selected_has_id,
            }
        return {
            "status": "live_available" if live_available else "unavailable",
            "source": "registry",
            "pause_session_id": spec.pause_session_id,
            "requested_action": spec.action,
            "same_process_registry": True,
            "durable_snapshot_found": False,
            "target_attached": True,
            "preflight_before_action": True,
            "pre_action_lifecycle": lifecycle,
            "live_continuation_available": live_available,
            "inspect_supported": live_available,
            "evaluate_supported": live_available,
            "step_supported": live_available,
            "resume_supported": live_available,
            "reason": None if live_available else "paused_session_already_resumed",
            "blockers": [] if live_available else ["debugger_session_not_live"],
            "blocker_details": [] if live_available else PausedSessionLiveContinuationPreflightManager._blocker_details(["debugger_session_not_live"]),
            "live_session_diagnostics": {
                "same_process_registry": True,
                "registry_entry_found": True,
                "durable_snapshot_found": False,
                "provided_artifact_found": False,
                "debugger_session_lifecycle": lifecycle,
                "live_session_available": live_available,
                "cross_process_live_continuation_supported": False,
                "cross_process_resume_supported": False,
                "cross_process_step_supported": False,
                "cross_process_evaluate_supported": False,
                "same_process_required_for_live_action": True,
            },
            "target_diagnostics": {
                "target_attached": live_available,
                "cdp_target_available": live_available,
                "target_attached_source": "same_process_registry",
                "cdp_target_available_source": "same_process_registry",
                "would_attach_cdp_target": False,
                "would_probe_cdp_target": False,
            },
            "callframe_diagnostics": {
                "stable_callframe_required": spec.action in {"evaluate", "eval", "evaluate_on_callframe"} or bool(spec.callframe_evaluations),
                "stable_callframe_available": live_available and selected_has_id,
                "selected_callframe_has_id": selected_has_id,
                "selected_callframe_index": spec.callframe_index,
                "selected_callframe": selected_summary,
                "callframe_count": len(callframes),
                "evaluate_requires_live_callframe": spec.action in {"evaluate", "eval", "evaluate_on_callframe"} or bool(spec.callframe_evaluations),
            },
            "action_capability": {
                "requested_action": spec.action,
                "is_live_action": spec.action in PausedSessionLiveContinuationPreflightManager.LIVE_ACTIONS or bool(spec.debugger_actions or spec.callframe_evaluations),
                "inspect_supported": live_available,
                "evaluate_supported": live_available,
                "step_supported": live_available,
                "resume_supported": live_available,
                "reason": None if live_available else "paused_session_already_resumed",
            },
        }

    @staticmethod
    def _durable_paused_session_preflight(*, session_id: str, callframes: list[dict[str, Any]] | None = None, lifecycle: str = "retained_paused") -> dict[str, Any]:
        callframes = callframes or []
        selected = callframes[0] if callframes else {}
        location = selected.get("location") if isinstance(selected.get("location"), dict) else {}
        return {
            "status": "inspect_only",
            "source": "durable_snapshot",
            "pause_session_id": session_id,
            "same_process_registry": False,
            "durable_snapshot_found": True,
            "target_attached": False,
            "live_continuation_available": False,
            "inspect_supported": True,
            "evaluate_supported": False,
            "step_supported": False,
            "resume_supported": False,
            "reason": "durable_snapshot_is_inspect_only",
            "blockers": ["live_paused_session_required", "target_not_attached", "debugger_session_not_live", "cdp_target_unavailable"],
            "blocker_details": PausedSessionLiveContinuationPreflightManager._blocker_details(
                ["live_paused_session_required", "target_not_attached", "debugger_session_not_live", "cdp_target_unavailable"]
            ),
            "live_session_diagnostics": {
                "same_process_registry": False,
                "registry_entry_found": False,
                "durable_snapshot_found": True,
                "provided_artifact_found": False,
                "debugger_session_lifecycle": lifecycle,
                "live_session_available": False,
                "cross_process_live_continuation_supported": False,
                "cross_process_resume_supported": False,
                "cross_process_step_supported": False,
                "cross_process_evaluate_supported": False,
                "same_process_required_for_live_action": True,
            },
            "target_diagnostics": {
                "target_attached": False,
                "cdp_target_available": False,
                "target_attached_source": "durable_snapshot_inspect_only",
                "cdp_target_available_source": "durable_snapshot_inspect_only",
                "would_attach_cdp_target": False,
                "would_probe_cdp_target": False,
            },
            "callframe_diagnostics": {
                "stable_callframe_required": False,
                "stable_callframe_available": False,
                "selected_callframe_has_id": bool(selected.get("callFrameId")),
                "selected_callframe_index": 0 if callframes else None,
                "selected_callframe": {
                    "function_name": selected.get("functionName") or selected.get("function_name") or selected.get("name"),
                    "url": selected.get("url") or location.get("url"),
                    "line_number": location.get("lineNumber", location.get("line_number")),
                    "column_number": location.get("columnNumber", location.get("column_number")),
                    "has_callframe_id": bool(selected.get("callFrameId")),
                } if selected else {},
                "callframe_count": len(callframes),
                "evaluate_requires_live_callframe": False,
            },
            "action_capability": {
                "requested_action": None,
                "is_live_action": False,
                "inspect_supported": True,
                "evaluate_supported": False,
                "step_supported": False,
                "resume_supported": False,
                "reason": "durable_snapshot_is_inspect_only",
            },
            "required_for_live": [
                "same_process_registry",
                "active_cdp_session",
                "attached_cdp_target",
                "retained_paused_lifecycle",
                "stable_callframe_id_for_evaluate",
            ],
        }

    @staticmethod
    def _continued_pause_lifecycle(debugger_session: dict[str, Any], actions: list[dict[str, Any]]) -> str:
        successful_methods = {str(item.get("method")) for item in actions if item.get("ok") and item.get("method")}
        if "Debugger.resume" in successful_methods:
            return "resumed"
        if successful_methods:
            return "action_controlled"
        return debugger_session.get("lifecycle", "retained_paused")

    @staticmethod
    def _debugger_action_timeline_entries(actions: list[dict[str, Any]], *, start_index: int) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for offset, action in enumerate(actions):
            entry = {
                "type": "debugger.session_action",
                "index": start_index + offset,
                "action": action.get("action"),
                "method": action.get("method"),
                "ok": action.get("ok"),
            }
            if action.get("error"):
                entry["error"] = action["error"]
            entries.append(entry)
        return entries

    @classmethod
    def _paused_session_store_path(cls, session_id: str, store_dir: str | None = None) -> Path:
        root = Path(store_dir) if store_dir else Path(tempfile.gettempdir()) / "reverse-deepagent-paused-sessions"
        return root / f"{cls._safe_session_id(session_id)}.json"

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", session_id).strip("._") or "paused-session"

    @staticmethod
    def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    def _subscribe_paused(self, session: Any, paused_events: list[dict[str, Any]], *, spec: BreakpointSpec) -> dict[str, Any]:
        on = getattr(session, "on", None)
        if not callable(on):
            return {"supported": False, "reason": "cdp_event_subscription_unavailable"}

        def handle_paused(params: Any) -> None:
            first_pause = not paused_events
            paused = self._normalize_paused(params)
            paused["evaluations"] = []
            paused["debugger_actions"] = []
            paused_events.append(paused)
            if first_pause:
                paused["evaluations"] = self._evaluate_callframe_expressions(session, paused.get("callFrames", []), spec)
                paused["debugger_actions"] = self._run_debugger_actions(session, spec)
            if not self._should_auto_resume(spec, paused["debugger_actions"]):
                paused["autoResume"] = {"attempted": False, "reason": "disabled_or_action_controlled"}
                return
            try:
                session.send("Debugger.resume", {})
                paused["autoResume"] = {"attempted": True, "ok": True, "method": "Debugger.resume"}
            except Exception as exc:
                paused["autoResume"] = {"attempted": True, "ok": False, "method": "Debugger.resume", "error": str(exc)}
                paused_events[-1]["autoResumeError"] = str(exc)

        try:
            on("Debugger.paused", handle_paused)
        except Exception as exc:
            return {"supported": False, "reason": "cdp_event_subscription_failed", "error": str(exc)}
        return {"supported": True}

    def _run_trigger_expression(self, page: BrowserPage, session: Any, spec: BreakpointSpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        if not spec.auto_resume:
            expression = self._scheduled_trigger_expression(spec.trigger_expression)
            trigger_mode = "scheduled"
        else:
            expression = spec.trigger_expression
            trigger_mode = "direct"
        try:
            payload = session.send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": False,
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}
        wait_after_trigger_ms = spec.wait_after_trigger_ms if spec.wait_after_trigger_ms > 0 else (1000 if trigger_mode == "scheduled" else 0)
        self._wait_after_trigger(page, wait_after_trigger_ms)
        return {
            "attempted": True,
            "ok": True,
            "mode": trigger_mode,
            "wait_after_trigger_ms": wait_after_trigger_ms,
            "result": payload if isinstance(payload, dict) else {"value": payload},
        }

    @staticmethod
    def _scheduled_trigger_expression(expression: str) -> str:
        return "setTimeout(() => {\n" + expression + "\n}, 0); 'reverse-agent-trigger-scheduled'"

    @staticmethod
    def _wait_after_trigger(page: BrowserPage, wait_after_trigger_ms: int) -> None:
        if wait_after_trigger_ms <= 0:
            return
        raw_page = getattr(page, "raw_page", None)
        wait_for_timeout = getattr(raw_page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            wait_for_timeout(wait_after_trigger_ms)
            return
        time.sleep(wait_after_trigger_ms / 1000)

    @classmethod
    def _paused_summary(cls, paused_events: list[dict[str, Any]], subscription: dict[str, Any]) -> dict[str, Any]:
        if paused_events:
            first = paused_events[0]
            return {
                "status": "success",
                "count": len(paused_events),
                "reason": first.get("reason"),
                "hitBreakpoints": first.get("hitBreakpoints", []),
                "subscription": subscription,
            }
        if subscription.get("supported"):
            return {"status": "not_observed", "count": 0, "subscription": subscription}
        return {"status": "unsupported", "count": 0, "subscription": subscription, "reason": subscription.get("reason")}

    @staticmethod
    def _callframes_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        frames = paused_events[0].get("callFrames", [])
        return frames if isinstance(frames, list) else []

    @staticmethod
    def _evaluations_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        evaluations = paused_events[0].get("evaluations", [])
        return evaluations if isinstance(evaluations, list) else []

    @staticmethod
    def _debugger_actions_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        actions = paused_events[0].get("debugger_actions", [])
        return actions if isinstance(actions, list) else []

    def _debugger_session_snapshot(self, paused_events: list[dict[str, Any]], spec: BreakpointSpec) -> dict[str, Any]:
        session_id = spec.pause_session_id or self._default_pause_session_id(spec)
        events = [self._pause_event_summary(index, event) for index, event in enumerate(paused_events)]
        callframes = self._callframes_from_paused(paused_events)
        selected_callframe = callframes[spec.callframe_index] if 0 <= spec.callframe_index < len(callframes) else None
        selected_callframe_id = selected_callframe.get("callFrameId") if isinstance(selected_callframe, dict) else None
        debugger_actions = self._debugger_actions_from_paused(paused_events)
        lifecycle = self._pause_lifecycle(paused_events, spec, debugger_actions)
        return {
            "session_id": session_id,
            "status": "success" if paused_events else "not_observed",
            "lifecycle": lifecycle,
            "preserve_pause_state": spec.preserve_pause_state,
            "auto_resume": spec.auto_resume,
            "paused_event_count": len(paused_events),
            "selected_callframe_index": spec.callframe_index,
            "selected_callframe_id": selected_callframe_id,
            "selected_callframe": selected_callframe,
            "events": events,
            "debugger_action_count": len(debugger_actions),
        }

    def _debugger_timeline(
        self,
        paused_events: list[dict[str, Any]],
        spec: BreakpointSpec,
        trigger: dict[str, Any],
        breakpoints: list[dict[str, Any]],
        debugger_session: dict[str, Any],
        *,
        error: str | None = None,
    ) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for breakpoint in breakpoints:
            entries.append(
                {
                    "type": "breakpoint.set",
                    "ok": bool(breakpoint.get("breakpointId")),
                    "breakpointId": breakpoint.get("breakpointId"),
                    "urlPattern": breakpoint.get("urlPattern"),
                    "lineNumber": breakpoint.get("lineNumber"),
                    "location_count": len(breakpoint.get("locations", [])) if isinstance(breakpoint.get("locations"), list) else 0,
                }
            )
        if trigger:
            entries.append(
                {
                    "type": "trigger.evaluate",
                    "attempted": bool(trigger.get("attempted")),
                    "ok": trigger.get("ok"),
                    "mode": trigger.get("mode"),
                    "wait_after_trigger_ms": trigger.get("wait_after_trigger_ms"),
                    **({"error": trigger["error"]} if trigger.get("error") else {}),
                }
            )
        for pause_index, event in enumerate(paused_events):
            summary = self._pause_event_summary(pause_index, event)
            entries.append({"type": "debugger.paused", "pause_index": pause_index, **summary})
            evaluations = event.get("evaluations", []) if isinstance(event.get("evaluations"), list) else []
            for evaluation in evaluations:
                if not isinstance(evaluation, dict):
                    continue
                entries.append(
                    {
                        "type": "callframe.evaluate",
                        "pause_index": pause_index,
                        "expression": evaluation.get("expression"),
                        "ok": evaluation.get("ok"),
                        "blocked": evaluation.get("blocked", False),
                        "policy": evaluation.get("policy"),
                        "side_effect_risk": evaluation.get("side_effect_risk"),
                        "throw_on_side_effect": evaluation.get("throw_on_side_effect"),
                        **({"error": evaluation["error"]} if evaluation.get("error") else {}),
                    }
                )
            actions = event.get("debugger_actions", []) if isinstance(event.get("debugger_actions"), list) else []
            for action in actions:
                if not isinstance(action, dict):
                    continue
                entries.append(
                    {
                        "type": "debugger.action",
                        "pause_index": pause_index,
                        "action": action.get("action"),
                        "method": action.get("method"),
                        "ok": action.get("ok"),
                        **({"error": action["error"]} if action.get("error") else {}),
                    }
                )
            auto_resume = event.get("autoResume") if isinstance(event.get("autoResume"), dict) else {}
            entries.append(
                {
                    "type": "debugger.resume",
                    "pause_index": pause_index,
                    "mode": "auto",
                    "attempted": bool(auto_resume.get("attempted")),
                    "ok": auto_resume.get("ok"),
                    "method": auto_resume.get("method"),
                    "reason": auto_resume.get("reason"),
                    **({"error": auto_resume["error"]} if auto_resume.get("error") else {}),
                }
            )
        for index, entry in enumerate(entries):
            entry["index"] = index
        return {
            "status": "failed" if error else debugger_session.get("status", "not_observed"),
            "session_id": debugger_session.get("session_id") or self._default_pause_session_id(spec),
            "lifecycle": debugger_session.get("lifecycle", "not_observed"),
            "entry_count": len(entries),
            "paused_event_count": len(paused_events),
            "evaluation_count": sum(len(event.get("evaluations", [])) for event in paused_events if isinstance(event.get("evaluations"), list)),
            "debugger_action_count": sum(len(event.get("debugger_actions", [])) for event in paused_events if isinstance(event.get("debugger_actions"), list)),
            "error": error,
            "entries": entries,
        }

    @staticmethod
    def _default_pause_session_id(spec: BreakpointSpec) -> str:
        return f"breakpoint:{spec.url_pattern}:{spec.line_number}:{spec.column_number if spec.column_number is not None else 0}"

    @staticmethod
    def _pause_event_summary(index: int, event: dict[str, Any]) -> dict[str, Any]:
        frames = event.get("callFrames", []) if isinstance(event.get("callFrames"), list) else []
        top = frames[0] if frames and isinstance(frames[0], dict) else {}
        summary = {
            "index": index,
            "reason": event.get("reason"),
            "hitBreakpoints": event.get("hitBreakpoints", []),
            "callframe_count": len(frames),
            "top_function": top.get("functionName"),
            "top_url": top.get("url"),
            "top_location": top.get("location"),
        }
        if event.get("autoResumeError"):
            summary["autoResumeError"] = event.get("autoResumeError")
        return summary

    @staticmethod
    def _pause_lifecycle(paused_events: list[dict[str, Any]], spec: BreakpointSpec, debugger_actions: list[dict[str, Any]]) -> str:
        if not paused_events:
            return "not_observed"
        successful_methods = {str(item.get("method")) for item in debugger_actions if item.get("ok") and item.get("method")}
        if successful_methods:
            return "action_controlled"
        if not spec.auto_resume:
            return "retained_paused"
        return "auto_resumed"

    @classmethod
    def _normalize_paused(cls, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return {"reason": "unknown", "callFrames": [], "rawType": type(params).__name__}
        callframes = [cls._normalize_callframe(frame) for frame in params.get("callFrames", []) if isinstance(frame, dict)]
        return {
            "reason": params.get("reason"),
            "hitBreakpoints": params.get("hitBreakpoints", []) if isinstance(params.get("hitBreakpoints"), list) else [],
            "callFrames": callframes,
            "callframe_count": len(callframes),
        }

    def _evaluate_callframe_expressions(self, session: Any, callframes: list[dict[str, Any]], spec: BreakpointSpec) -> list[dict[str, Any]]:
        if not spec.callframe_evaluations:
            return []
        if spec.callframe_index < 0 or spec.callframe_index >= len(callframes):
            return [
                {
                    "expression": expression,
                    "ok": False,
                    "error": "callframe_index_out_of_range",
                    "callframe_index": spec.callframe_index,
                }
                for expression in spec.callframe_evaluations
            ]
        callframe = callframes[spec.callframe_index]
        callframe_id = callframe.get("callFrameId")
        if not callframe_id:
            return [
                {
                    "expression": expression,
                    "ok": False,
                    "error": "callframe_id_unavailable",
                    "callframe_index": spec.callframe_index,
                }
                for expression in spec.callframe_evaluations
            ]
        evaluations: list[dict[str, Any]] = []
        for expression in spec.callframe_evaluations:
            decision = self._evaluation_policy_decision(expression, spec.callframe_evaluation_policy)
            if decision["blocked"]:
                evaluations.append(
                    {
                        "expression": expression,
                        "ok": False,
                        "blocked": True,
                        "error": "blocked_by_callframe_evaluation_policy",
                        "callframe_index": spec.callframe_index,
                        "callFrameId": callframe_id,
                        **decision,
                    }
                )
                continue
            try:
                payload = session.send(
                    "Debugger.evaluateOnCallFrame",
                    {
                        "callFrameId": callframe_id,
                        "expression": expression,
                        "returnByValue": True,
                        "silent": True,
                        "throwOnSideEffect": decision["throw_on_side_effect"],
                    },
                )
                evaluations.append(
                    self._with_evaluation_policy_metadata(
                        self._normalize_callframe_evaluation(expression, payload, spec.callframe_index, str(callframe_id)),
                        decision,
                    )
                )
            except Exception as exc:
                evaluations.append(
                    {
                        "expression": expression,
                        "ok": False,
                        "error": str(exc),
                        "callframe_index": spec.callframe_index,
                        "callFrameId": callframe_id,
                        **decision,
                    }
                )
        return evaluations

    @staticmethod
    def _evaluation_policy_decision(expression: str, policy: str) -> dict[str, Any]:
        risk, reason = BreakpointManager._side_effect_risk(expression)
        blocked = policy in {"read_only", "block_dangerous"} and risk == "high"
        return {
            "policy": policy,
            "side_effect_risk": risk,
            "side_effect_reason": reason,
            "blocked": blocked,
            "throw_on_side_effect": policy != "allow_side_effects",
        }

    @staticmethod
    def _mutation_category(risk_reason: str | None) -> str:
        if not risk_reason:
            return "unknown_mutation"
        if "cookie" in risk_reason:
            return "cookie_mutation"
        if "storage" in risk_reason:
            return "storage_mutation"
        if "navigation" in risk_reason:
            return "navigation_mutation"
        if "network" in risk_reason:
            return "network_side_effect"
        if "dynamic code" in risk_reason:
            return "dynamic_code_execution"
        if "assignment" in risk_reason:
            return "assignment_mutation"
        if "increment/decrement" in risk_reason:
            return "increment_decrement_mutation"
        if "function call" in risk_reason:
            return "runtime_call"
        if "read-only" in risk_reason:
            return "read_only_expression"
        return "unknown_mutation"

    @classmethod
    def _mutation_audit_from_evaluations(cls, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        audit: list[dict[str, Any]] = []
        for evaluation in evaluations:
            if not isinstance(evaluation, dict):
                continue
            risk = str(evaluation.get("side_effect_risk") or "unknown")
            reason = str(evaluation.get("side_effect_reason") or "")
            audit.append(
                {
                    "expression": evaluation.get("expression"),
                    "policy": evaluation.get("policy"),
                    "blocked": bool(evaluation.get("blocked", False)),
                    "ok": evaluation.get("ok"),
                    "risk": risk,
                    "mutation_category": cls._mutation_category(reason),
                    "reason": reason or "unspecified",
                    "throw_on_side_effect": evaluation.get("throw_on_side_effect"),
                    "callframe_index": evaluation.get("callframe_index"),
                    "callFrameId": evaluation.get("callFrameId"),
                }
            )
        return audit

    @staticmethod
    def _side_effect_risk(expression: str) -> tuple[str, str]:
        compact = expression.strip()
        high_risk_patterns = (
            (r"(?<![=!<>])=(?!=|>)", "assignment-like expression"),
            (r"\+\+|--", "increment/decrement operator"),
            (r"\bdelete\s+", "delete operator"),
            (r"\bdocument\s*\.\s*cookie\s*=", "document.cookie write"),
            (r"\b(?:localStorage|sessionStorage)\s*\.\s*(?:setItem|removeItem|clear)\s*\(", "storage mutation"),
            (r"\b(?:fetch|XMLHttpRequest|sendBeacon)\s*\(", "network side effect candidate"),
            (r"\b(?:eval|Function)\s*\(", "dynamic code execution"),
            (r"\b(?:location|window\.location|document\.location)\s*=", "navigation mutation"),
        )
        for pattern, reason in high_risk_patterns:
            if re.search(pattern, compact):
                return "high", reason
        if re.search(r"\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?\s*\(", compact):
            return "medium", "function call; guarded by CDP throwOnSideEffect unless explicitly allowed"
        return "low", "read-only expression shape"

    @staticmethod
    def _with_evaluation_policy_metadata(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        result.update(decision)
        return result

    def _run_debugger_actions(self, session: Any, spec: BreakpointSpec) -> list[dict[str, Any]]:
        if not spec.debugger_actions:
            return []
        results: list[dict[str, Any]] = []
        for action in spec.debugger_actions:
            method = self._normalize_debugger_action(action)
            if not method:
                results.append(
                    {
                        "action": action,
                        "ok": False,
                        "error": "unsupported_debugger_action",
                    }
                )
                continue
            try:
                payload = session.send(method, {})
                results.append(
                    {
                        "action": action,
                        "method": method,
                        "ok": True,
                        "result": payload if isinstance(payload, dict) else {"value": payload},
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "action": action,
                        "method": method,
                        "ok": False,
                        "error": str(exc),
                    }
                )
        return results

    @staticmethod
    def _should_auto_resume(spec: BreakpointSpec, debugger_actions: list[dict[str, Any]]) -> bool:
        if not spec.auto_resume:
            return False
        successful_methods = {str(item.get("method")) for item in debugger_actions if item.get("ok") and item.get("method")}
        return not successful_methods.intersection({"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"})

    @staticmethod
    def _normalize_debugger_action(action: str) -> str | None:
        normalized = action.strip().replace("-", "_").lower()
        if normalized in {"resume"}:
            return "Debugger.resume"
        if normalized in {"step_over", "stepover", "over"}:
            return "Debugger.stepOver"
        if normalized in {"step_into", "stepinto", "into"}:
            return "Debugger.stepInto"
        if normalized in {"step_out", "stepout", "out"}:
            return "Debugger.stepOut"
        return None

    @staticmethod
    def _normalize_callframe_evaluation(expression: str, payload: Any, callframe_index: int, callframe_id: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "expression": expression,
                "ok": True,
                "value": payload,
                "valueType": type(payload).__name__,
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        if payload.get("exceptionDetails"):
            details = payload.get("exceptionDetails") if isinstance(payload.get("exceptionDetails"), dict) else {}
            return {
                "expression": expression,
                "ok": False,
                "error": details.get("text") or "evaluateOnCallFrame exception",
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        if not isinstance(result, dict):
            return {
                "expression": expression,
                "ok": True,
                "value": result,
                "valueType": type(result).__name__,
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        value = result.get("value")
        if "unserializableValue" in result:
            value = result.get("unserializableValue")
        elif "value" not in result and "description" in result:
            value = result.get("description")
        return {
            "expression": expression,
            "ok": True,
            "value": value,
            "valueType": result.get("type"),
            "description": result.get("description"),
            "callframe_index": callframe_index,
            "callFrameId": callframe_id,
        }

    @staticmethod
    def _normalize_callframe(frame: dict[str, Any]) -> dict[str, Any]:
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        function_location = frame.get("functionLocation") if isinstance(frame.get("functionLocation"), dict) else {}
        url = frame.get("url")
        return {
            "callFrameId": frame.get("callFrameId"),
            "functionName": frame.get("functionName"),
            "url": url,
            "location": {
                "scriptId": location.get("scriptId"),
                "lineNumber": location.get("lineNumber"),
                "columnNumber": location.get("columnNumber"),
            },
            "functionLocation": {
                "scriptId": function_location.get("scriptId"),
                "lineNumber": function_location.get("lineNumber"),
                "columnNumber": function_location.get("columnNumber"),
            }
            if function_location
            else None,
            "scopeCount": len(frame.get("scopeChain", [])) if isinstance(frame.get("scopeChain"), list) else 0,
            "thisType": (frame.get("this") or {}).get("type") if isinstance(frame.get("this"), dict) else None,
        }
