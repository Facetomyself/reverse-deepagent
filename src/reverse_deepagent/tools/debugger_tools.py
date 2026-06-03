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

        artifact_count = sum(bool(item) for item in (session, timeline, paused, live_preflight)) + sum(bool(items) for items in (callframes, evaluations, mutation_audit, actions, timeline_entries))
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
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(blockers, warnings, preflight, session, paused),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "browser_resumed": False,
                "debugger_stepped": False,
                "callframe_evaluated": False,
                "runtime_mutated": False,
                "cdp_command_sent": False,
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
    if "debugger_artifact_reports_failure" in blockers or "debugger_pause_reports_failure" in blockers:
        return "inspect_debugger_failure_and_collect_fresh_pause_artifacts"
    if "no_debugger_artifacts_provided" in warnings:
        return "collect_debugger_pause_artifacts_before_review"
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
    session: dict[str, Any],
    paused: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in blockers:
        items.append(
            {
                "code": code,
                "session_id": _string(session.get("session_id") or session.get("pause_session_id")),
                "preflight_status": _string(preflight.get("status")),
                "preflight_source": _string(preflight.get("source")),
                "reason": _string(preflight.get("reason") or preflight.get("blocked_reason") or session.get("reason") or paused.get("reason")),
            }
        )
    for code in warnings:
        if code in {"durable_snapshot_is_inspect_only", "paused_session_unavailable", "paused_session_has_no_callframes"}:
            items.append(
                {
                    "code": code,
                    "session_id": _string(session.get("session_id") or session.get("pause_session_id")),
                    "preflight_status": _string(preflight.get("status")),
                    "preflight_source": _string(preflight.get("source")),
                    "reason": _string(preflight.get("reason") or preflight.get("blocked_reason") or paused.get("reason")),
                }
            )
    return items
