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

PAUSED_SESSION_LIVE_ACTIONS = {'resume', 'step', 'step_over', 'step_into', 'step_out', 'evaluate', 'evaluate_on_callframe', 'eval'}

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
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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


class PausedSessionLiveContinuationPreflightManager:
    """Inspect whether a paused session can be live-continued without sending CDP commands."""

    LIVE_ACTIONS = PAUSED_SESSION_LIVE_ACTIONS

    def preflight(self, spec: PausedSessionLiveContinuationPreflightSpec | None) -> PausedSessionLiveContinuationPreflightResult:
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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
        from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager  # lazy import (circular-safe)
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



