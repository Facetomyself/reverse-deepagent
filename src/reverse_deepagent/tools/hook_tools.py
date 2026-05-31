from __future__ import annotations

import json
from collections import Counter
from typing import Any


HOOK_ARTIFACT_REVIEW_VERSION = "2026-05-31.hook-artifact-review-v1"


def make_review_hook_artifacts_tool():
    """Create a read-only tool that reviews hook inventory and timeline artifacts."""

    def review_hook_artifacts(hook_artifacts_json: str) -> dict[str, Any]:
        """Review hook artifacts without installing hooks, evaluating JavaScript, or triggering targets."""

        payload = _loads_object(hook_artifacts_json, field_name="hook_artifacts_json")
        function_hooks = _object_alias(payload, "function_hooks", "function-hooks", "functionHooks")
        function_timeline = _object_alias(payload, "function_hook_timeline", "function-hook-timeline", "functionHookTimeline")
        module_hooks = _object_alias(payload, "module_hooks", "module-hooks", "moduleHooks")
        module_timeline = _object_alias(payload, "module_hook_timeline", "module-hook-timeline", "moduleHookTimeline")
        generic_timeline = _object_alias(payload, "hook_timeline", "hook-timeline", "hookTimeline")
        source_logpoints = _object_alias(payload, "source_logpoints", "source-logpoints", "sourceLogpoints")
        module_candidates = _records_alias(payload, "module_candidates", "module-candidates", "moduleCandidates")
        function_candidates = _records_alias(payload, "function_candidates", "function-candidates", "functionCandidates")

        function_events = _records_from(function_timeline.get("events") or function_timeline.get("entries"))
        module_events = _records_from(module_timeline.get("events") or module_timeline.get("entries"))
        generic_snapshot = generic_timeline.get("snapshot") if isinstance(generic_timeline.get("snapshot"), dict) else {}
        generic_events = _records_from(generic_timeline.get("events") or generic_timeline.get("entries") or generic_snapshot.get("events"))
        installed_function_count = _count_hooks(function_hooks)
        installed_module_count = _count_hooks(module_hooks)
        source_logpoint_count = _intish(source_logpoints.get("count") or source_logpoints.get("installed_count") or len(_records_from(source_logpoints)))
        timeline_event_count = _event_count(function_timeline, function_events) + _event_count(module_timeline, module_events) + _event_count(generic_timeline, generic_events)
        missing_count = _intish(function_hooks.get("missing_count")) + _intish(module_hooks.get("missing_count")) + _intish(source_logpoints.get("missing_count"))
        candidate_count = len(module_candidates) + len(function_candidates)

        blockers: list[str] = []
        warnings: list[str] = []
        artifact_count = sum(bool(item) for item in (function_hooks, function_timeline, module_hooks, module_timeline, generic_timeline, source_logpoints)) + sum(bool(items) for items in (module_candidates, function_candidates))
        if not artifact_count:
            warnings.append("no_hook_artifacts_provided")
        if any(_status(item) in {"failed", "failure", "error", "unsupported"} for item in (function_hooks, module_hooks, source_logpoints, generic_timeline)):
            blockers.append("hook_artifact_reports_failure")
        if missing_count:
            warnings.append("hook_targets_missing")
        if installed_function_count + installed_module_count + source_logpoint_count > 0 and timeline_event_count == 0:
            warnings.append("installed_hooks_without_timeline_events")
        if candidate_count and installed_function_count + installed_module_count == 0:
            warnings.append("candidates_without_installed_hooks")

        status = "block" if blockers else "warn" if warnings else "pass"
        return {
            "version": HOOK_ARTIFACT_REVIEW_VERSION,
            "status": status,
            "blocked": bool(blockers),
            "warnings_present": bool(warnings),
            "next_action": _next_action(blockers, warnings),
            "summary": {
                "artifact_count": artifact_count,
                "installed_function_hook_count": installed_function_count,
                "installed_module_hook_count": installed_module_count,
                "source_logpoint_count": source_logpoint_count,
                "missing_hook_target_count": missing_count,
                "candidate_count": candidate_count,
                "function_hook_event_count": _event_count(function_timeline, function_events),
                "module_hook_event_count": _event_count(module_timeline, module_events),
                "generic_hook_event_count": _event_count(generic_timeline, generic_events),
                "timeline_event_count": timeline_event_count,
                "function_hook_event_type_counts": _event_type_counts(function_events),
                "module_hook_event_type_counts": _event_type_counts(module_events),
                "installed_function_targets": _installed_targets(function_hooks),
                "installed_module_targets": _installed_targets(module_hooks),
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(blockers, warnings, function_hooks, module_hooks, source_logpoints),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "hook_installed": False,
                "breakpoint_installed": False,
                "javascript_evaluated": False,
                "target_invoked": False,
                "runtime_mutated": False,
                "delivery_executed": False,
            },
        }

    review_hook_artifacts.__name__ = "review_hook_artifacts"
    return review_hook_artifacts


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
        records = _records_from(payload.get(key))
        if records:
            return records
    return []


def _records_from(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("items", "entries", "events", "records", "candidates", "hooks", "logpoints"):
            records = _records_from(value.get(key))
            if records:
                return records
    return []


def _status(item: dict[str, Any]) -> str:
    value = item.get("status") or item.get("result") or item.get("state")
    return value.lower() if isinstance(value, str) else ""


def _intish(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _count_hooks(payload: dict[str, Any]) -> int:
    for key in ("installed_count", "count"):
        count = _intish(payload.get(key))
        if count:
            return count
    installed = payload.get("installed")
    if isinstance(installed, dict):
        return sum(1 for value in installed.values() if bool(value))
    hooks = _records_from(payload)
    if hooks:
        return len(hooks)
    return 0


def _event_count(payload: dict[str, Any], events: list[dict[str, Any]]) -> int:
    return _intish(payload.get("event_count") or payload.get("eventCount") or payload.get("entry_count") or payload.get("count")) or len(events)


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("type") or item.get("event") or item.get("kind") or "unknown") for item in events)
    return dict(sorted(counter.items()))


def _installed_targets(payload: dict[str, Any]) -> list[str]:
    installed = payload.get("installed")
    if isinstance(installed, dict):
        return sorted(str(key) for key, value in installed.items() if bool(value))
    targets = payload.get("installed_targets") or payload.get("targets")
    if isinstance(targets, list):
        return [str(item) for item in targets if item is not None]
    return []


def _next_action(blockers: list[str], warnings: list[str]) -> str:
    if "hook_artifact_reports_failure" in blockers:
        return "inspect_hook_failure_and_adjust_target_paths"
    if "no_hook_artifacts_provided" in warnings:
        return "collect_hook_artifacts_before_review"
    if "hook_targets_missing" in warnings:
        return "adjust_missing_hook_paths_or_module_exports"
    if "installed_hooks_without_timeline_events" in warnings:
        return "invoke_hooked_targets_or_wait_for_runtime_events"
    if "candidates_without_installed_hooks" in warnings:
        return "install_reviewed_hook_from_candidate_before_capture"
    if warnings:
        return "inspect_hook_warnings"
    return "hook_review_passed"


def _review_required_items(
    blockers: list[str],
    warnings: list[str],
    function_hooks: dict[str, Any],
    module_hooks: dict[str, Any],
    source_logpoints: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for code in blockers + warnings:
        if code == "no_hook_artifacts_provided":
            continue
        items.append(
            {
                "code": code,
                "function_hook_status": _status(function_hooks),
                "module_hook_status": _status(module_hooks),
                "source_logpoint_status": _status(source_logpoints),
                "function_hook_error": str(function_hooks.get("error") or ""),
                "module_hook_error": str(module_hooks.get("error") or ""),
                "source_logpoint_error": str(source_logpoints.get("error") or ""),
            }
        )
    return items
