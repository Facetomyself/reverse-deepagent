from __future__ import annotations

import json
from collections import Counter
from typing import Any


FLOW_TIMELINE_REVIEW_VERSION = "2026-05-31.flow-timeline-review-v1"


def make_review_flow_timeline_tool():
    """Create a read-only tool that summarizes flow timeline review state."""

    def review_flow_timeline(flow_timeline_json: str) -> dict[str, Any]:
        """Review a flow-timeline JSON payload without mutating artifacts or approving stitching."""

        timeline = _loads_object(flow_timeline_json, field_name="flow_timeline_json")
        entries = _list_of_dicts(timeline.get("entries"))
        correlation_groups = _list_of_dicts(timeline.get("correlation_groups"))
        stitch_candidates = _list_of_dicts(timeline.get("stitch_candidates"))
        stitch_proposals = _list_of_dicts(timeline.get("stitch_proposals"))
        dry_runs = _list_of_dicts(timeline.get("auto_stitch_dry_runs"))
        conflict_resolutions = _list_of_dicts(timeline.get("auto_stitch_conflict_resolutions"))
        policy_decisions = _list_of_dicts(timeline.get("auto_stitch_policy_decisions"))
        materialization_plans = _list_of_dicts(timeline.get("auto_stitch_materialization_plans"))
        materialization_results = _list_of_dicts(timeline.get("auto_stitch_materialization_results"))
        rollback_plans = _list_of_dicts(timeline.get("auto_stitch_rollback_execution_plans"))
        rollback_results = _list_of_dicts(timeline.get("auto_stitch_rollback_execution_results"))

        pending_proposals = [item for item in stitch_proposals if _proposal_is_pending_review(item)]
        approved_proposals = [item for item in stitch_proposals if _proposal_is_approved(item)]
        blocked_policy_decisions = [item for item in policy_decisions if _status(item) in {"blocked", "not_eligible", "not_ready"}]
        review_ready_groups = [item for item in correlation_groups if _verification_status(item) == "ready_for_manual_stitch_review"]
        reviewable_groups = [item for item in correlation_groups if _verification_status(item) == "reviewable"]
        materialization_requested = any(_boolish(item.get("materialization_requested")) for item in policy_decisions)
        approved_materializations = [item for item in materialization_results if _boolish(item.get("approved")) or _boolish(item.get("materialized"))]

        blockers: list[str] = []
        warnings: list[str] = []
        if pending_proposals:
            blockers.append("pending_stitch_proposals_require_review")
        if blocked_policy_decisions:
            blockers.append("auto_stitch_policy_blocked")
        if materialization_requested and not approved_materializations:
            blockers.append("materialization_requested_without_approval")
        if dry_runs and not materialization_plans and not approved_materializations:
            warnings.append("dry_runs_have_no_materialization_plan")
        if conflict_resolutions and any(_boolish(item.get("has_unresolved_conflicts")) or item.get("unresolved_conflicts") for item in conflict_resolutions):
            blockers.append("unresolved_stitch_conflicts")
        if rollback_plans and not rollback_results:
            warnings.append("rollback_plan_without_reviewed_result")
        if review_ready_groups and not stitch_proposals:
            warnings.append("review_ready_groups_without_stitch_proposals")

        status = "block" if blockers else "warn" if warnings else "pass"
        next_action = _next_action(status, blockers, warnings, bool(review_ready_groups or pending_proposals))
        return {
            "version": FLOW_TIMELINE_REVIEW_VERSION,
            "status": status,
            "blocked": bool(blockers),
            "warnings_present": bool(warnings),
            "next_action": next_action,
            "summary": {
                "entry_count": len(entries),
                "entry_source_counts": _source_counts(entries),
                "correlation_group_count": len(correlation_groups),
                "correlation_group_status_counts": _status_counts(_verification_status(item) for item in correlation_groups),
                "reviewable_group_count": len(reviewable_groups),
                "review_ready_group_count": len(review_ready_groups),
                "stitch_candidate_count": len(stitch_candidates),
                "stitch_proposal_count": len(stitch_proposals),
                "pending_stitch_proposal_count": len(pending_proposals),
                "approved_stitch_proposal_count": len(approved_proposals),
                "auto_stitch_dry_run_count": len(dry_runs),
                "auto_stitch_conflict_resolution_count": len(conflict_resolutions),
                "auto_stitch_policy_decision_count": len(policy_decisions),
                "blocked_policy_decision_count": len(blocked_policy_decisions),
                "auto_stitch_materialization_plan_count": len(materialization_plans),
                "auto_stitch_materialization_result_count": len(materialization_results),
                "approved_materialization_count": len(approved_materializations),
                "rollback_execution_plan_count": len(rollback_plans),
                "rollback_execution_result_count": len(rollback_results),
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _review_required_items(pending_proposals, blocked_policy_decisions, conflict_resolutions),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "timeline_materialized": False,
                "review_decision_recorded": False,
                "rollback_executed": False,
                "delivery_executed": False,
            },
        }

    review_flow_timeline.__name__ = "review_flow_timeline"
    return review_flow_timeline


def _loads_object(payload: str, *, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON object text: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must decode to a JSON object")
    return value


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _status(item: dict[str, Any]) -> str:
    for key in ("status", "decision", "result"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _verification_status(item: dict[str, Any]) -> str:
    verification = item.get("verification")
    if isinstance(verification, dict):
        status = verification.get("status")
        if isinstance(status, str):
            return status
    status = item.get("verification_status") or item.get("status")
    return str(status) if status is not None else "unknown"


def _proposal_is_pending_review(item: dict[str, Any]) -> bool:
    decision = item.get("review_decision")
    if isinstance(decision, dict):
        status = decision.get("status")
        if status == "pending_review" or _boolish(decision.get("review_required")) and not _boolish(decision.get("approved")):
            return True
    return _boolish(item.get("review_required")) and not _boolish(item.get("approved"))


def _proposal_is_approved(item: dict[str, Any]) -> bool:
    decision = item.get("review_decision")
    if isinstance(decision, dict):
        return _boolish(decision.get("approved")) or decision.get("status") == "approved"
    return _boolish(item.get("approved"))


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "approved"}
    return bool(value)


def _source_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for entry in entries:
        source = entry.get("source") or entry.get("kind") or entry.get("type") or "unknown"
        counter[str(source)] += 1
    return dict(sorted(counter.items()))


def _status_counts(statuses: Any) -> dict[str, int]:
    counter = Counter(str(status or "unknown") for status in statuses)
    return dict(sorted(counter.items()))


def _next_action(status: str, blockers: list[str], warnings: list[str], review_context_present: bool) -> str:
    if "pending_stitch_proposals_require_review" in blockers:
        return "review_stitch_proposals_before_materialization_or_delivery"
    if "auto_stitch_policy_blocked" in blockers or "unresolved_stitch_conflicts" in blockers:
        return "resolve_timeline_conflicts_or_collect_more_evidence"
    if "materialization_requested_without_approval" in blockers:
        return "record_explicit_materialization_review_decision"
    if status == "warn" and review_context_present:
        return "prepare_manual_timeline_review"
    if status == "warn":
        return "inspect_timeline_warnings"
    return "timeline_review_passed"


def _review_required_items(
    pending_proposals: list[dict[str, Any]],
    blocked_policy_decisions: list[dict[str, Any]],
    conflict_resolutions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for proposal in pending_proposals:
        items.append(
            {
                "code": "flow_timeline_stitch_proposal_pending_review",
                "proposal_id": str(proposal.get("proposal_id") or proposal.get("id") or ""),
                "blocking_conditions": _string_list(proposal.get("blocking_conditions")),
            }
        )
    for decision in blocked_policy_decisions:
        items.append(
            {
                "code": "auto_stitch_policy_blocked",
                "decision_id": str(decision.get("decision_id") or decision.get("id") or ""),
                "blockers": _string_list(decision.get("blockers") or decision.get("blocking_reasons")),
            }
        )
    for resolution in conflict_resolutions:
        conflicts = resolution.get("unresolved_conflicts")
        if conflicts:
            items.append(
                {
                    "code": "auto_stitch_unresolved_conflicts",
                    "resolution_id": str(resolution.get("resolution_id") or resolution.get("id") or ""),
                    "unresolved_conflicts": _string_list(conflicts),
                }
            )
    return items


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
