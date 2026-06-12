from __future__ import annotations

from typing import Any

BROWSER_PROVIDER_SMOKE_ACCEPTANCE_SCHEMA = "reverse-deepagent.browser-provider-smoke-acceptance.v1"
BROWSER_PROVIDER_SMOKE_ACCEPTANCE_REPORT_SCHEMA = "reverse-deepagent.browser-provider-smoke-acceptance-report.v1"
BROWSER_PROVIDER_SMOKE_POLICY_DECISION_SCHEMA = "reverse-deepagent.browser-provider-smoke-policy-decision.v1"
BROWSER_PROVIDER_SMOKE_SCHEMA = "reverse-deepagent.browser-provider-smoke.v1"
EVIDENCE_LEVEL_ORDER = {
    "unknown": 0,
    "metadata-only": 1,
    "availability-check": 2,
    "launch-smoke": 3,
}
SUPPORTED_MINIMUM_EVIDENCE_LEVELS = ("metadata-only", "availability-check", "launch-smoke")


def browser_provider_smoke_acceptance(
    smoke_payload: dict[str, Any],
    *,
    expected_provider_id: str | None = None,
) -> dict[str, Any]:
    """Review existing BrowserProvider smoke JSON before accepting it as evidence.

    This is deliberately metadata-only: it does not generate smoke evidence,
    call provider factories, check availability, probe CDP, launch browsers,
    call MCP, or inspect mobile runtimes.
    """

    expected_provider = str(expected_provider_id or "")
    resolved_provider_id = str(smoke_payload.get("resolved_provider_id") or "")
    requested_provider_id = str(smoke_payload.get("requested_provider_id") or "")
    mode = str(smoke_payload.get("mode") or "unknown")
    schema_version = str(smoke_payload.get("schema_version") or "")
    side_effect_policy = smoke_payload.get("side_effect_policy") if isinstance(smoke_payload.get("side_effect_policy"), dict) else {}
    provider_row = smoke_payload.get("provider") if isinstance(smoke_payload.get("provider"), dict) else {}
    provider_smoke = provider_row.get("smoke") if isinstance(provider_row.get("smoke"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []
    if schema_version != BROWSER_PROVIDER_SMOKE_SCHEMA:
        blockers.append("browser_provider_smoke_schema_mismatch")
    if not bool(smoke_payload.get("ok")):
        blockers.append("browser_provider_smoke_not_ok")
    if not resolved_provider_id:
        blockers.append("resolved_provider_id_missing")
    if expected_provider and resolved_provider_id and expected_provider != resolved_provider_id:
        blockers.append("browser_provider_smoke_provider_mismatch")
    if bool(side_effect_policy.get("calls_mcp")):
        blockers.append("browser_provider_smoke_calls_mcp")
    if bool(side_effect_policy.get("touches_mobile_full_runtime_chains")):
        blockers.append("browser_provider_smoke_touches_mobile_full_runtime_chain")
    if mode == "launch-smoke":
        if not bool(side_effect_policy.get("launch_smoke_requested")):
            blockers.append("launch_smoke_mode_without_launch_request")
        if provider_smoke and provider_smoke.get("status") != "passed":
            blockers.append("launch_smoke_not_passed")
        if not provider_smoke:
            warnings.append("launch_smoke_result_not_embedded")
    elif bool(side_effect_policy.get("starts_browser")):
        blockers.append("browser_started_outside_launch_smoke_mode")
    if mode == "metadata-only":
        warnings.append("metadata_only_evidence_not_launch_smoke")
    if mode == "availability-check":
        warnings.append("availability_check_evidence_not_launch_smoke")
    if not expected_provider:
        warnings.append("runtime_provider_not_comparable")

    evidence_level = mode if mode in {"metadata-only", "availability-check", "launch-smoke"} else "unknown"
    accepted = not blockers
    launch_smoke_accepted = accepted and evidence_level == "launch-smoke"
    status = "accepted" if accepted else "blocked"
    next_action = (
        "review_browser_provider_launch_smoke_result"
        if launch_smoke_accepted
        else "optionally_run_explicit_launch_browser_smoke"
        if accepted
        else "regenerate_browser_provider_smoke_evidence"
    )
    required_follow_up = (
        "review_attached_launch_smoke_as_runtime_evidence"
        if launch_smoke_accepted
        else "run_explicit_launch_browser_smoke_before_claiming_runtime_smoke"
        if accepted
        else "regenerate_matching_browser_provider_smoke_json"
    )
    provider_match = bool(not expected_provider or expected_provider == resolved_provider_id)
    sorted_warnings = sorted(set(warnings))
    acceptance_report = {
        "schema_version": BROWSER_PROVIDER_SMOKE_ACCEPTANCE_REPORT_SCHEMA,
        "review_only": True,
        "metadata_only_gate": True,
        "status": status,
        "evidence_level": evidence_level,
        "runtime_launch_smoke_accepted": launch_smoke_accepted,
        "provider_match": provider_match,
        "provider_summary": {
            "expected_provider_id": expected_provider or None,
            "requested_provider_id": requested_provider_id or None,
            "resolved_provider_id": resolved_provider_id or None,
        },
        "evidence_summary": {
            "schema_version": schema_version or None,
            "mode": mode,
            "ok": bool(smoke_payload.get("ok")),
            "launch_smoke_requested": bool(side_effect_policy.get("launch_smoke_requested")),
            "provider_smoke_status": provider_smoke.get("status") if provider_smoke else None,
            "metadata_only_evidence": evidence_level == "metadata-only",
            "availability_check_evidence": evidence_level == "availability-check",
            "launch_smoke_evidence": evidence_level == "launch-smoke",
        },
        "side_effect_summary": {
            "attached_evidence_claims_browser_start": bool(side_effect_policy.get("starts_browser")),
            "attached_evidence_claims_mcp": bool(side_effect_policy.get("calls_mcp")),
            "attached_evidence_claims_mobile_full_runtime": bool(
                side_effect_policy.get("touches_mobile_full_runtime_chains")
            ),
            "acceptance_generated_smoke": False,
            "acceptance_invoked_provider_factory": False,
            "acceptance_checked_availability": False,
            "acceptance_probed_cdp_endpoint": False,
            "acceptance_started_browser": False,
            "acceptance_called_mcp": False,
            "acceptance_touched_mobile_full_runtime_chains": False,
        },
        "blockers": list(blockers),
        "warnings": sorted_warnings,
        "required_follow_up": required_follow_up,
        "next_action": next_action,
    }

    return {
        "schema_version": BROWSER_PROVIDER_SMOKE_ACCEPTANCE_SCHEMA,
        "status": status,
        "accepted": accepted,
        "runtime_launch_smoke_accepted": launch_smoke_accepted,
        "evidence_level": evidence_level,
        "expected_provider_id": expected_provider or None,
        "requested_provider_id": requested_provider_id or None,
        "resolved_provider_id": resolved_provider_id or None,
        "provider_match": provider_match,
        "blockers": blockers,
        "warnings": sorted_warnings,
        "side_effect_policy": {
            "metadata_only": True,
            "generates_smoke": False,
            "provider_factory_invoked": False,
            "availability_checked": False,
            "cdp_endpoint_probed": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
        "acceptance_report": acceptance_report,
        "next_action": next_action,
    }


def browser_provider_smoke_policy_decision(
    acceptance: dict[str, Any],
    *,
    minimum_evidence_level: str = "metadata-only",
    block_on_warnings: bool = False,
) -> dict[str, Any]:
    """Evaluate a review-only policy decision for accepted BrowserProvider smoke evidence."""

    minimum = str(minimum_evidence_level or "metadata-only")
    evidence_level = str(acceptance.get("evidence_level") or "unknown")
    blockers = list(acceptance.get("blockers") if isinstance(acceptance.get("blockers"), list) else [])
    warnings = list(acceptance.get("warnings") if isinstance(acceptance.get("warnings"), list) else [])
    policy_blockers: list[str] = []
    policy_warnings: list[str] = []

    if minimum not in SUPPORTED_MINIMUM_EVIDENCE_LEVELS:
        policy_blockers.append("unsupported_minimum_evidence_level")
    if not bool(acceptance.get("accepted")):
        policy_blockers.append("browser_provider_smoke_acceptance_blocked")
    current_rank = EVIDENCE_LEVEL_ORDER.get(evidence_level, 0)
    required_rank = EVIDENCE_LEVEL_ORDER.get(minimum, 0)
    if minimum in SUPPORTED_MINIMUM_EVIDENCE_LEVELS and current_rank < required_rank:
        policy_blockers.append("insufficient_browser_provider_smoke_evidence_level")
    if warnings and block_on_warnings:
        policy_blockers.append("browser_provider_smoke_warnings_blocked_by_policy")
    elif warnings:
        policy_warnings.extend(warnings)
    if blockers:
        policy_warnings.extend(f"acceptance_blocker:{item}" for item in blockers)

    if policy_blockers:
        decision = "block"
        next_action = "regenerate_or_upgrade_browser_provider_smoke_evidence"
    elif policy_warnings:
        decision = "warn"
        next_action = (
            "optionally_upgrade_browser_provider_smoke_evidence"
            if current_rank >= required_rank
            else "regenerate_or_upgrade_browser_provider_smoke_evidence"
        )
    else:
        decision = "pass"
        next_action = "accept_browser_provider_smoke_evidence_for_policy"
    return {
        "schema_version": BROWSER_PROVIDER_SMOKE_POLICY_DECISION_SCHEMA,
        "review_only": True,
        "metadata_only_gate": True,
        "decision": decision,
        "policy_passed": decision != "block",
        "minimum_evidence_level": minimum,
        "observed_evidence_level": evidence_level,
        "evidence_level_rank": current_rank,
        "minimum_evidence_level_rank": required_rank,
        "runtime_launch_smoke_accepted": bool(acceptance.get("runtime_launch_smoke_accepted")),
        "block_on_warnings": bool(block_on_warnings),
        "blockers": sorted(set(policy_blockers)),
        "warnings": sorted(set(policy_warnings)),
        "side_effect_policy": {
            "metadata_only": True,
            "reads_existing_acceptance": True,
            "generates_smoke": False,
            "provider_factory_invoked": False,
            "availability_checked": False,
            "cdp_endpoint_probed": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
        "next_action": next_action,
    }
