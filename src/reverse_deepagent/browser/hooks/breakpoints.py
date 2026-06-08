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
