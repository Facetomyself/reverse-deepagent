from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.tools.workspace_artifact_reader import (
    audit_workspace_artifact_consumers_payload,
    load_workspace_artifact_json_object,
    read_workspace_artifact_payload,
    summarize_workspace_artifact_read,
)
from reverse_deepagent.tools.workspace_helpers import (
    _compact_readiness_summary,
    _compact_workspace_consumer_score,
    _dual_write_route_risk,
    _load_observed_dual_write_plan,
    _parse_artifact_keys_json,
    _parse_delivery_source_audit,
    _parse_json_object,
    _parse_readiness_report,
    _planned_dual_write_candidates,
    _safe_int,
    _summarize_delivery_source_audit_payload,
    _workspace_migration_next_actions,
    _observed_dual_write_records,
    _dual_write_candidate_result,
)
from reverse_deepagent.workspace_contract import WorkspacePathResolver, default_workspace_artifact_routes, workspace_virtual_uri


ArtifactTool = Callable[..., dict[str, Any]]


def make_assess_workspace_migration_readiness_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for workspace migration readiness planning."""

    root = Path(default_artifact_root)

    def assess_workspace_migration_readiness(
        artifact_root: str | None = None,
        delivery_source_audit_json: str | None = None,
    ) -> dict[str, Any]:
        """Assess dual-write and foldered-canonical migration readiness without mutating files."""

        return assess_workspace_migration_readiness_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )

    assess_workspace_migration_readiness.__name__ = "assess_workspace_migration_readiness"
    assess_workspace_migration_readiness.__doc__ = (
        "Read-only workspace migration readiness report. Combines workspace consumer adoption status, "
        "registered artifact route counts, and optional execute_local_delivery delivery_artifact_source_audit JSON "
        "to distinguish limited dual-write pilot readiness from foldered-canonical migration blockers. "
        "It does not inspect files, write artifacts, create directories, enable dual-write, migrate paths, start browsers, or call MCP."
    )
    return assess_workspace_migration_readiness


def make_assess_workspace_consumer_readiness_score_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only scoring tool for workspace consumer migration readiness."""

    root = Path(default_artifact_root)

    def assess_workspace_consumer_readiness_score(
        artifact_root: str | None = None,
        readiness_report_json: str | None = None,
        pilot_result_json: str | None = None,
        delivery_source_audit_json: str | None = None,
    ) -> dict[str, Any]:
        """Score workspace consumer readiness without enabling dual-write or migrating paths."""

        return assess_workspace_consumer_readiness_score_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_report_json=readiness_report_json,
            pilot_result_json=pilot_result_json,
            delivery_source_audit_json=delivery_source_audit_json,
        )

    assess_workspace_consumer_readiness_score.__name__ = "assess_workspace_consumer_readiness_score"
    assess_workspace_consumer_readiness_score.__doc__ = (
        "Read-only workspace consumer readiness score for dual-write expansion and foldered-canonical migration review. "
        "It consumes the static consumer audit, optional migration readiness report, optional delivery source audit JSON, "
        "and optional observed dual-write pilot result JSON. It does not inspect files, write artifacts, create directories, "
        "enable dual-write, migrate paths, change canonical paths, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return assess_workspace_consumer_readiness_score


def make_plan_workspace_dual_write_expansion_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for reviewed opt-in workspace dual-write expansion planning."""

    root = Path(default_artifact_root)

    def plan_workspace_dual_write_expansion(
        artifact_root: str | None = None,
        readiness_score_json: str | None = None,
        readiness_report_json: str | None = None,
        pilot_result_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 24,
        include_medium_risk: bool = False,
    ) -> dict[str, Any]:
        """Plan opt-in dual-write expansion without enabling dual-write or writing artifacts."""

        return plan_workspace_dual_write_expansion_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_score_json=readiness_score_json,
            readiness_report_json=readiness_report_json,
            pilot_result_json=pilot_result_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            include_medium_risk=include_medium_risk,
        )

    plan_workspace_dual_write_expansion.__name__ = "plan_workspace_dual_write_expansion"
    plan_workspace_dual_write_expansion.__doc__ = (
        "Read-only opt-in workspace dual-write expansion plan. It consumes workspace-consumer-readiness-score evidence, "
        "optional migration readiness / pilot result inputs, and optional reviewed artifact keys to produce the next reviewed expansion scope. "
        "It does not inspect files, write artifacts, create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, "
        "start browsers, call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_dual_write_expansion


def make_review_workspace_dual_write_expansion_workflow_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a review workflow tool for opt-in dual-write expansion evidence."""

    root = Path(default_artifact_root)

    def review_workspace_dual_write_expansion_workflow(
        artifact_root: str | None = None,
        expansion_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Review an expansion plan and observed dual-write output without running pipelines."""

        return review_workspace_dual_write_expansion_workflow_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            expansion_plan_json=expansion_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    review_workspace_dual_write_expansion_workflow.__name__ = "review_workspace_dual_write_expansion_workflow"
    review_workspace_dual_write_expansion_workflow.__doc__ = (
        "Review-first workflow for an opt-in workspace dual-write expansion scope. It consumes a ready expansion plan "
        "and optional observed workspace-dual-write-plan evidence, verifies output compatibility, and optionally writes "
        "workspace/workspace-dual-write-expansion-result.json only when write_result=true. It does not run pipelines, "
        "enable dual-write, migrate paths, change canonical paths, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_dual_write_expansion_workflow


def make_record_workspace_dual_write_expansion_result_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a verifier for observed opt-in dual-write expansion output."""

    root = Path(default_artifact_root)

    def record_workspace_dual_write_expansion_result(
        artifact_root: str | None = None,
        expansion_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Verify observed expansion output and optionally write an audit artifact."""

        return record_workspace_dual_write_expansion_result_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            expansion_plan_json=expansion_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    record_workspace_dual_write_expansion_result.__name__ = "record_workspace_dual_write_expansion_result"
    record_workspace_dual_write_expansion_result.__doc__ = (
        "Verify an observed scoped workspace dual-write expansion output against a reviewed expansion plan. "
        "Default mode is read-only and inspects existing legacy/future artifact files plus workspace-dual-write-plan evidence; "
        "write_result=true writes only workspace/workspace-dual-write-expansion-result.json. It never runs pipelines, enables dual-write, "
        "migrates paths, changes canonical paths, starts browsers, call MCP, or touch mobile full runtime chains."
    )
    return record_workspace_dual_write_expansion_result


def assess_workspace_migration_readiness_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    delivery_source_audit_json: str | None = None,
) -> dict[str, Any]:
    """Return a read-only migration readiness report for workspace path evolution."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    consumer_audit = audit_workspace_artifact_consumers_payload()
    consumers = consumer_audit["consumers"]
    resolver_ready = [item for item in consumers if item["resolver_status"] == "resolver-ready"]
    partial = [item for item in consumers if item["resolver_status"] == "partial"]
    candidates = [item for item in consumers if item["resolver_status"] == "candidate"]
    explicit_boundaries = [item for item in consumers if item["resolver_status"] == "explicit-filesystem-boundary"]
    delivery_source_audit = _parse_delivery_source_audit(delivery_source_audit_json)
    delivery_source_summary = _summarize_delivery_source_audit_payload(delivery_source_audit)
    registered_routes = default_workspace_artifact_routes()

    limited_dual_write_blockers: list[str] = []
    if candidates:
        limited_dual_write_blockers.append("candidate_consumers_require_resolver_adoption")
    if not resolver_ready:
        limited_dual_write_blockers.append("no_resolver_ready_consumers")
    limited_dual_write_status = "ready_for_review" if not limited_dual_write_blockers else "blocked"

    foldered_blockers: list[str] = []
    if partial:
        foldered_blockers.append("partial_consumers_still_present")
    if candidates:
        foldered_blockers.append("candidate_consumers_require_resolver_adoption")
    if delivery_source_audit is None:
        foldered_blockers.append("delivery_source_audit_evidence_missing")
    elif delivery_source_summary["malformed"]:
        foldered_blockers.append("delivery_source_audit_malformed")
    elif delivery_source_summary["source_path_count"] > 0:
        foldered_blockers.append("source_path_usage_observed")
    if delivery_source_summary["external_source_path_count"] > 0:
        foldered_blockers.append("external_source_path_usage_observed")
    foldered_canonical_status = "ready_for_review" if not foldered_blockers else "blocked"

    return {
        "schema_version": "reverse-deepagent.workspace-migration-readiness.v1",
        "status": "review",
        "artifact_root": str(effective_root),
        "summary": {
            "consumer_count": consumer_audit["summary"]["consumer_count"],
            "resolver_ready_count": len(resolver_ready),
            "partial_count": len(partial),
            "candidate_count": len(candidates),
            "explicit_filesystem_boundary_count": len(explicit_boundaries),
            "registered_workspace_route_count": len(registered_routes),
            "delivery_source_audit_observed": delivery_source_audit is not None,
            "limited_dual_write_pilot_status": limited_dual_write_status,
            "foldered_canonical_migration_status": foldered_canonical_status,
            "mobile_full_runtime_chains_deferred": True,
        },
        "consumer_readiness": {
            "resolver_ready_consumers": [item["consumer_id"] for item in resolver_ready],
            "partial_consumers": [item["consumer_id"] for item in partial],
            "candidate_consumers": [item["consumer_id"] for item in candidates],
            "explicit_filesystem_boundaries": [item["consumer_id"] for item in explicit_boundaries],
        },
        "delivery_source_audit": delivery_source_summary,
        "migration_readiness": {
            "limited_dual_write_pilot": {
                "status": limited_dual_write_status,
                "blocking_reasons": limited_dual_write_blockers,
                "allowed_scope": "registered-workspace-artifacts-only",
                "requires_explicit_opt_in": True,
                "keeps_legacy_canonical_path": True,
                "writes_future_foldered_copy": limited_dual_write_status == "ready_for_review",
                "review_required": True,
            },
            "foldered_canonical_migration": {
                "status": foldered_canonical_status,
                "blocking_reasons": foldered_blockers,
                "requires_no_partial_consumers": True,
                "requires_delivery_source_audit_without_source_path_usage": True,
                "keeps_explicit_filesystem_boundaries": True,
                "review_required": True,
            },
        },
        "recommended_next_actions": _workspace_migration_next_actions(
            limited_dual_write_blockers=limited_dual_write_blockers,
            foldered_blockers=foldered_blockers,
            delivery_source_audit_present=delivery_source_audit is not None,
        ),
        "source_evidence": {
            "consumer_audit_schema_version": consumer_audit["schema_version"],
            "delivery_source_audit_schema_version": delivery_source_summary["schema_version"],
        },
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def assess_workspace_consumer_readiness_score_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_report_json: str | None = None,
    pilot_result_json: str | None = None,
    delivery_source_audit_json: str | None = None,
) -> dict[str, Any]:
    """Return a read-only score for workspace consumer migration readiness."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    consumer_audit = audit_workspace_artifact_consumers_payload()
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(
            default_artifact_root=effective_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )
    pilot_result, pilot_result_error = _parse_json_object(pilot_result_json, field_name="pilot_result_json")
    consumer_summary = _workspace_consumer_score_summary(consumer_audit)
    readiness_summary = _compact_readiness_summary(readiness_report)
    delivery_source_summary = _score_delivery_source_summary(readiness_report)
    pilot_evidence = _workspace_pilot_result_score(pilot_result, pilot_result_error)
    scoring = _workspace_consumer_scoring(
        consumer_summary=consumer_summary,
        readiness_summary=readiness_summary,
        delivery_source_summary=delivery_source_summary,
        pilot_evidence=pilot_evidence,
    )
    readiness = _workspace_consumer_readiness_decision(scoring, readiness_summary, delivery_source_summary, pilot_evidence)
    return {
        "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
        "status": readiness["status"],
        "artifact_root": str(effective_root),
        "summary": {
            "overall_score": scoring["overall_score"],
            "overall_label": scoring["overall_label"],
            "consumer_count": consumer_summary["consumer_count"],
            "resolver_ready_count": consumer_summary["resolver_ready_count"],
            "partial_count": consumer_summary["partial_count"],
            "candidate_count": consumer_summary["candidate_count"],
            "explicit_filesystem_boundary_count": consumer_summary["explicit_filesystem_boundary_count"],
            "limited_dual_write_pilot_status": readiness_summary["limited_dual_write_pilot_status"],
            "foldered_canonical_migration_status": readiness_summary["foldered_canonical_migration_status"],
            "pilot_result_status": pilot_evidence["status"],
            "blocking_reason_count": len(readiness["blocking_reasons"]),
            "warning_count": len(readiness["warnings"]),
            "review_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "scores": scoring["scores"],
        "consumer_audit_summary": consumer_summary,
        "migration_readiness_summary": readiness_summary,
        "delivery_source_audit_summary": delivery_source_summary,
        "pilot_evidence": pilot_evidence,
        "readiness": readiness,
        "blocking_reasons": readiness["blocking_reasons"],
        "warnings": readiness["warnings"],
        "recommended_next_actions": readiness["recommended_next_actions"],
        "source_evidence": {
            "consumer_audit_schema_version": consumer_audit.get("schema_version") or "",
            "migration_readiness_schema_version": readiness_report.get("schema_version") or "",
            "pilot_result_schema_version": pilot_evidence.get("schema_version") or "missing",
            "delivery_source_audit_status": delivery_source_summary["status"],
        },
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _workspace_consumer_score_summary(consumer_audit: dict[str, Any]) -> dict[str, Any]:
    consumers = consumer_audit.get("consumers") if isinstance(consumer_audit.get("consumers"), list) else []
    by_status = consumer_audit.get("summary", {}).get("by_status") if isinstance(consumer_audit.get("summary"), dict) else {}
    if not isinstance(by_status, dict):
        by_status = {}
    consumer_count = len(consumers)
    resolver_ready_count = _safe_int(by_status.get("resolver-ready"))
    partial_count = _safe_int(by_status.get("partial"))
    candidate_count = _safe_int(by_status.get("candidate"))
    explicit_boundary_count = _safe_int(by_status.get("explicit-filesystem-boundary"))
    non_workspace_count = _safe_int(by_status.get("non-workspace-input"))
    migration_relevant_count = resolver_ready_count + partial_count + candidate_count
    unresolved_count = partial_count + candidate_count
    resolver_ready_ratio = round(resolver_ready_count / migration_relevant_count, 4) if migration_relevant_count else 0.0
    return {
        "consumer_count": consumer_count,
        "migration_relevant_count": migration_relevant_count,
        "resolver_ready_count": resolver_ready_count,
        "partial_count": partial_count,
        "candidate_count": candidate_count,
        "unresolved_consumer_count": unresolved_count,
        "explicit_filesystem_boundary_count": explicit_boundary_count,
        "non_workspace_input_count": non_workspace_count,
        "resolver_ready_ratio": resolver_ready_ratio,
        "by_status": dict(sorted(by_status.items())),
    }


def _score_delivery_source_summary(readiness_report: dict[str, Any]) -> dict[str, Any]:
    payload = readiness_report.get("delivery_source_audit") if isinstance(readiness_report.get("delivery_source_audit"), dict) else {}
    if not payload:
        return {
            "schema_version": "missing",
            "status": "missing",
            "source_path_count": 0,
            "workspace_resolved_count": 0,
            "external_source_path_count": 0,
            "source_path_risk": "unknown",
        }
    source_path_count = _safe_int(payload.get("source_path_count"))
    external_count = _safe_int(payload.get("external_source_path_count"))
    risk = "none" if source_path_count == 0 and external_count == 0 else "observed"
    return {
        "schema_version": payload.get("schema_version") or "unknown",
        "status": payload.get("status") or "unknown",
        "source_path_count": source_path_count,
        "workspace_resolved_count": _safe_int(payload.get("workspace_resolved_count")),
        "external_source_path_count": external_count,
        "legacy_source_path_count": _safe_int(payload.get("legacy_source_path_count")),
        "future_source_path_count": _safe_int(payload.get("future_source_path_count")),
        "artifact_root_relative_source_path_count": _safe_int(payload.get("artifact_root_relative_source_path_count")),
        "relative_source_path_count": _safe_int(payload.get("relative_source_path_count")),
        "source_path_risk": risk,
    }


def _workspace_pilot_result_score(pilot_result: dict[str, Any] | None, pilot_result_error: str) -> dict[str, Any]:
    if pilot_result_error:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "score": 0.0,
            "verified_candidate_count": 0,
            "planned_candidate_count": 0,
            "blocking_reasons": ["pilot_result_json_malformed"],
            "warnings": [],
            "error": pilot_result_error,
        }
    if not pilot_result:
        return {
            "schema_version": "missing",
            "status": "not_observed",
            "score": 0.0,
            "verified_candidate_count": 0,
            "planned_candidate_count": 0,
            "blocking_reasons": [],
            "warnings": ["dual_write_pilot_result_not_provided"],
        }
    summary = pilot_result.get("summary") if isinstance(pilot_result.get("summary"), dict) else {}
    status = str(pilot_result.get("status") or "unknown")
    planned = _safe_int(summary.get("planned_candidate_count"))
    verified = _safe_int(summary.get("verified_candidate_count"))
    if status == "verified" and planned and verified >= planned:
        score = 1.0
    elif status in {"partial", "verified"} and planned:
        score = round(max(0.0, min(1.0, verified / planned)), 4)
    elif status == "not_run":
        score = 0.0
    else:
        score = 0.0
    blockers = pilot_result.get("blocking_reasons") if isinstance(pilot_result.get("blocking_reasons"), list) else []
    warnings = pilot_result.get("warnings") if isinstance(pilot_result.get("warnings"), list) else []
    return {
        "schema_version": pilot_result.get("schema_version") or "unknown",
        "status": status,
        "score": score,
        "verified_candidate_count": verified,
        "planned_candidate_count": planned,
        "blocking_reasons": [str(item) for item in blockers],
        "warnings": [str(item) for item in warnings],
    }


def _workspace_consumer_scoring(
    *,
    consumer_summary: dict[str, Any],
    readiness_summary: dict[str, Any],
    delivery_source_summary: dict[str, Any],
    pilot_evidence: dict[str, Any],
) -> dict[str, Any]:
    migration_relevant = consumer_summary["migration_relevant_count"]
    resolver_adoption = consumer_summary["resolver_ready_ratio"] if migration_relevant else 0.0
    virtual_uri_adoption = resolver_adoption
    future_path_readiness = 1.0 if readiness_summary["limited_dual_write_pilot_status"] == "ready_for_review" else 0.0
    source_path_risk_score = 1.0 if delivery_source_summary["source_path_risk"] == "none" else 0.0
    if delivery_source_summary["status"] == "missing":
        source_path_risk_score = 0.25
    pilot_score = float(pilot_evidence.get("score") or 0.0)
    foldered_canonical = 1.0 if readiness_summary["foldered_canonical_migration_status"] == "ready_for_review" else 0.0
    scores = {
        "resolver_adoption": round(resolver_adoption, 4),
        "virtual_uri_adoption": round(virtual_uri_adoption, 4),
        "future_path_readiness": round(future_path_readiness, 4),
        "source_path_risk": round(source_path_risk_score, 4),
        "dual_write_pilot_evidence": round(pilot_score, 4),
        "foldered_canonical_readiness": round(foldered_canonical, 4),
    }
    overall = round(
        scores["resolver_adoption"] * 0.30
        + scores["virtual_uri_adoption"] * 0.10
        + scores["future_path_readiness"] * 0.20
        + scores["source_path_risk"] * 0.15
        + scores["dual_write_pilot_evidence"] * 0.15
        + scores["foldered_canonical_readiness"] * 0.10,
        4,
    )
    if overall >= 0.86:
        label = "ready_for_foldered_canonical_review"
    elif overall >= 0.62:
        label = "ready_for_limited_dual_write_review"
    elif overall >= 0.40:
        label = "needs_targeted_resolver_adoption"
    else:
        label = "blocked"
    return {"scores": scores, "overall_score": overall, "overall_label": label}


def _workspace_consumer_readiness_decision(
    scoring: dict[str, Any],
    readiness_summary: dict[str, Any],
    delivery_source_summary: dict[str, Any],
    pilot_evidence: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    scores = scoring["scores"]
    if scores["resolver_adoption"] < 1.0:
        blockers.append("resolver_adoption_incomplete")
    if readiness_summary["limited_dual_write_pilot_status"] != "ready_for_review":
        blockers.append("limited_dual_write_pilot_not_ready")
    if delivery_source_summary["status"] == "missing":
        warnings.append("delivery_source_audit_missing")
    if delivery_source_summary["source_path_count"] > 0:
        blockers.append("source_path_usage_observed")
    if delivery_source_summary["external_source_path_count"] > 0:
        blockers.append("external_source_path_usage_observed")
    if pilot_evidence["status"] in {"malformed", "blocked"}:
        blockers.append("dual_write_pilot_result_not_usable")
    elif pilot_evidence["status"] == "not_observed":
        warnings.append("dual_write_pilot_result_not_observed")
    elif pilot_evidence["score"] < 1.0:
        warnings.append("dual_write_pilot_not_fully_verified")
    foldered_ready = readiness_summary["foldered_canonical_migration_status"] == "ready_for_review"
    if foldered_ready and pilot_evidence["score"] >= 1.0 and not blockers:
        status = "ready_for_foldered_canonical_review"
    elif readiness_summary["limited_dual_write_pilot_status"] == "ready_for_review" and "limited_dual_write_pilot_not_ready" not in blockers:
        status = "ready_for_limited_dual_write_review"
    else:
        status = "blocked"
    actions = _workspace_consumer_score_next_actions(status, blockers, warnings, pilot_evidence)
    return {
        "status": status,
        "review_required": True,
        "foldered_canonical_migration_allowed": status == "ready_for_foldered_canonical_review",
        "limited_dual_write_expansion_review_allowed": status in {"ready_for_limited_dual_write_review", "ready_for_foldered_canonical_review"},
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": actions,
    }


def _workspace_consumer_score_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
    pilot_evidence: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if "resolver_adoption_incomplete" in blockers:
        actions.append("close_partial_or_candidate_workspace_consumers_before_foldered_canonical_migration")
    if "limited_dual_write_pilot_not_ready" in blockers:
        actions.append("resolve_workspace_migration_readiness_blockers_before_dual_write_expansion")
    if "source_path_usage_observed" in blockers:
        actions.append("replace_workspace_source_path_inputs_with_artifact_ref_where_possible")
    if "external_source_path_usage_observed" in blockers:
        actions.append("keep_external_filesystem_sources_as_explicit_delivery_boundaries")
    if "delivery_source_audit_missing" in warnings:
        actions.append("run_execute_local_delivery_dry_run_and_collect_delivery_artifact_source_audit")
    if pilot_evidence["status"] == "not_observed":
        actions.append("run_reviewed_scoped_dual_write_pilot_and_record_result_before_foldered_canonical_review")
    if "dual_write_pilot_not_fully_verified" in warnings:
        actions.append("resolve_dual_write_pilot_verification_gaps_before_expansion")
    if status == "ready_for_limited_dual_write_review":
        actions.append("review_opt_in_dual_write_expansion_scope_using_low_risk_artifact_keys")
    if status == "ready_for_foldered_canonical_review":
        actions.append("review_narrow_foldered_canonical_migration_pilot")
    if not actions:
        actions.append("resolve_workspace_consumer_readiness_blockers")
    return actions


def plan_workspace_dual_write_expansion_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_score_json: str | None = None,
    readiness_report_json: str | None = None,
    pilot_result_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 24,
    include_medium_risk: bool = False,
) -> dict[str, Any]:
    """Return a read-only opt-in dual-write expansion plan."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_score, readiness_score_error = _load_or_compute_workspace_consumer_readiness_score(
        default_artifact_root=effective_root,
        readiness_score_json=readiness_score_json,
        readiness_report_json=readiness_report_json,
        pilot_result_json=pilot_result_json,
    )
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    if not bool(readiness.get("limited_dual_write_expansion_review_allowed")):
        return {
            "schema_version": "reverse-deepagent.workspace-dual-write-expansion-plan.v1",
            "status": "blocked",
            "artifact_root": str(effective_root),
            "summary": {
                "candidate_count": 0,
                "pilot_result_status": (readiness_score.get("pilot_evidence") or {}).get("status") if isinstance(readiness_score.get("pilot_evidence"), dict) else "missing",
                "pilot_evidence_score": float((readiness_score.get("pilot_evidence") or {}).get("score") or 0.0) if isinstance(readiness_score.get("pilot_evidence"), dict) else 0.0,
                "mobile_full_runtime_chains_deferred": True,
            },
            "readiness_score_summary": _compact_workspace_consumer_score(readiness_score),
            "candidate_artifacts": [],
            "blocking_reasons": ["workspace_consumer_readiness_not_ready_for_expansion"],
            "warnings": [],
            "recommended_next_actions": _workspace_dual_write_expansion_next_actions(
                ["workspace_consumer_readiness_not_ready_for_expansion"], []
            ),
            "side_effect_policy": {
                "read_only": True,
                "files_inspected": False,
                "artifacts_written": False,
                "creates_directories": False,
                "runs_pipeline": False,
                "enables_dual_write": False,
                "migrates_paths": False,
                "changes_canonical_paths": False,
                "starts_browser": False,
                "calls_mcp": False,
                "touches_mobile_full_runtime_chains": False,
            },
        }

    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    routes = list(default_workspace_artifact_routes())
    routes_by_key = {route.artifact_key: route for route in routes}
    resolver = WorkspacePathResolver(enable_dual_write=True)
    max_count = max(0, int(max_artifacts))

    explicit_selection = requested_keys is not None
    selected_routes: list[Any] = []
    unknown_keys: list[str] = []
    if explicit_selection:
        for key in requested_keys or []:
            route = routes_by_key.get(key)
            if route is None:
                unknown_keys.append(key)
                continue
            selected_routes.append(route)
        if max_count:
            selected_routes = selected_routes[:max_count]
    else:
        for route in routes:
            risk_level = _dual_write_route_risk(route)["risk_level"]
            if risk_level == "high":
                continue
            if risk_level == "medium" and not include_medium_risk:
                continue
            selected_routes.append(route)
            if len(selected_routes) >= max_count:
                break
    if max_count == 0:
        selected_routes = []

    candidate_artifacts: list[dict[str, Any]] = []
    high_risk_requested: list[str] = []
    medium_risk_selected: list[str] = []
    for route in selected_routes:
        risk = _dual_write_route_risk(route)
        if explicit_selection and risk["risk_level"] == "high":
            high_risk_requested.append(route.artifact_key)
        if risk["risk_level"] == "medium":
            medium_risk_selected.append(route.artifact_key)
        plan = resolver.plan_dual_write(route.artifact_key)
        candidate_artifacts.append(
            {
                "artifact_key": route.artifact_key,
                "legacy_path": route.legacy_path,
                "future_path": route.future_path,
                "virtual_uri": plan.get("virtual_uri"),
                "category": route.category,
                "producer_roles": list(route.producer_roles),
                "risk": risk,
                "dual_write_plan": plan,
                "review_required": True,
            }
        )

    pilot_evidence = readiness_score.get("pilot_evidence") if isinstance(readiness_score.get("pilot_evidence"), dict) else {}
    readiness_status = str(readiness_score.get("status") or "blocked")
    pilot_score = float(pilot_evidence.get("score") or 0.0)
    blockers: list[str] = []
    warnings: list[str] = []
    if readiness_score_error:
        blockers.append("workspace_consumer_readiness_score_malformed")
    if not bool(readiness.get("limited_dual_write_expansion_review_allowed")):
        blockers.append("workspace_consumer_readiness_not_ready_for_expansion")
    if pilot_score < 1.0:
        blockers.append("verified_dual_write_pilot_result_required_before_expansion")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if high_risk_requested:
        blockers.append("high_risk_requested_artifacts_require_separate_review")
    if medium_risk_selected and not include_medium_risk:
        blockers.append("medium_risk_artifacts_require_explicit_include_medium_risk")
    if not candidate_artifacts:
        blockers.append("no_dual_write_expansion_candidates_selected")
    if medium_risk_selected and include_medium_risk:
        warnings.append("medium_risk_artifacts_selected_for_explicit_review")
    if readiness_status == "ready_for_limited_dual_write_review" and pilot_score >= 1.0:
        warnings.append("foldered_canonical_migration_still_requires_separate_review")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_artifacts),
            "readiness_score_status": readiness_status,
            "readiness_score_overall": readiness_score.get("summary", {}).get("overall_score") if isinstance(readiness_score.get("summary"), dict) else None,
            "pilot_result_status": pilot_evidence.get("status") or "missing",
            "pilot_evidence_score": pilot_score,
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "high_risk_requested_artifact_count": len(high_risk_requested),
            "medium_risk_selected_artifact_count": len(medium_risk_selected),
            "explicit_selection": explicit_selection,
            "max_artifacts": max_count,
            "review_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_risk_level": "low",
            "default_allows_medium_risk": False,
            "include_medium_risk_requested": bool(include_medium_risk),
            "requires_workspace_consumer_readiness_score": True,
            "requires_verified_dual_write_pilot_result": True,
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "actual_dual_write_enabled": False,
        },
        "readiness_score_summary": _compact_workspace_consumer_score(readiness_score),
        "candidate_artifacts": candidate_artifacts,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "high_risk_requested_artifact_keys": high_risk_requested,
            "medium_risk_selected_artifact_keys": medium_risk_selected,
        },
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_expansion_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_compute_workspace_consumer_readiness_score(
    *,
    default_artifact_root: Path,
    readiness_score_json: str | None,
    readiness_report_json: str | None,
    pilot_result_json: str | None,
) -> tuple[dict[str, Any], str]:
    payload, error = _parse_json_object(readiness_score_json, field_name="readiness_score_json")
    if payload is not None or error:
        if payload is not None:
            return payload, ""
        return {
            "schema_version": "invalid-json",
            "status": "blocked",
            "summary": {"overall_score": 0.0},
            "readiness": {"limited_dual_write_expansion_review_allowed": False},
            "pilot_evidence": {"status": "malformed", "score": 0.0},
        }, error
    return assess_workspace_consumer_readiness_score_payload(
        default_artifact_root=default_artifact_root,
        readiness_report_json=readiness_report_json,
        pilot_result_json=pilot_result_json,
    ), ""


def _workspace_dual_write_expansion_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_consumer_readiness_score_malformed" in blockers:
        actions.append("fix_readiness_score_json_or_omit_it_to_recompute_score")
    if "workspace_consumer_readiness_not_ready_for_expansion" in blockers:
        actions.append("resolve_workspace_consumer_readiness_blockers_before_expansion")
    if "verified_dual_write_pilot_result_required_before_expansion" in blockers:
        actions.append("run_and_record_verified_dual_write_pilot_before_expansion")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_or_register_unknown_artifact_keys")
    if "high_risk_requested_artifacts_require_separate_review" in blockers:
        actions.append("split_high_risk_delivery_or_transaction_artifacts_into_separate_manual_review")
    if "no_dual_write_expansion_candidates_selected" in blockers:
        actions.append("register_additional_low_risk_artifact_keys_or_run_dual_write_pilot_first")
    if not blockers and not warnings:
        actions.append("review_expansion_plan_then_run_pipeline_with_scoped_keys")
    if not actions:
        actions.append("resolve_expansion_plan_blockers_before_running_pipeline")
    return actions


def review_workspace_dual_write_expansion_workflow_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    expansion_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Review opt-in dual-write expansion readiness and observed evidence."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    expansion_plan, expansion_plan_error = _load_or_compute_workspace_dual_write_expansion_plan(
        default_artifact_root=effective_root,
        expansion_plan_json=expansion_plan_json,
    )
    expansion_result = record_workspace_dual_write_expansion_result_payload(
        default_artifact_root=effective_root,
        expansion_plan_json=json.dumps(expansion_plan) if isinstance(expansion_plan, dict) else None,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
        write_result=write_result,
    )
    status = _workspace_dual_write_expansion_workflow_status(expansion_plan, expansion_result, expansion_plan_error)
    blockers = _workspace_dual_write_expansion_workflow_blockers(expansion_plan, expansion_result, expansion_plan_error, status)
    warnings = _workspace_dual_write_expansion_workflow_warnings(expansion_plan, expansion_result)
    candidate_keys = [item["artifact_key"] for item in _planned_dual_write_candidates(expansion_plan if isinstance(expansion_plan, dict) else {})]
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-workflow.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "expansion_plan_status": expansion_plan.get("status") if isinstance(expansion_plan, dict) else "malformed",
            "expansion_result_status": expansion_result.get("status") or "unknown",
            "candidate_count": len(candidate_keys),
            "verified_candidate_count": _safe_int((expansion_result.get("summary") or {}).get("verified_candidate_count")) if isinstance(expansion_result.get("summary"), dict) else 0,
            "write_result_requested": bool(write_result),
            "legacy_canonical_path_remains_authoritative": True,
            "foldered_canonical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "expansion_plan_summary": _compact_expansion_plan_summary(expansion_plan if isinstance(expansion_plan, dict) else {}),
        "expansion_result": expansion_result,
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_expansion_workflow_next_actions(status, expansion_result),
        "review_workflow": _workspace_dual_write_expansion_review_workflow(
            candidate_keys=candidate_keys,
            result_status=str(expansion_result.get("status") or "unknown"),
            workflow_status=status,
            write_result=write_result,
        ),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def record_workspace_dual_write_expansion_result_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    expansion_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Inspect an explicit expansion dual-write run and optionally record a result artifact."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    expansion_plan, expansion_plan_error = _load_or_compute_workspace_dual_write_expansion_plan(
        default_artifact_root=effective_root,
        expansion_plan_json=expansion_plan_json,
    )
    observed_plan, observed_plan_error, observed_input = _load_observed_dual_write_plan(
        default_artifact_root=effective_root,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
    )
    planned_candidates = _planned_dual_write_candidates(expansion_plan if isinstance(expansion_plan, dict) else {})
    observed_records = _observed_dual_write_records(observed_plan if isinstance(observed_plan, dict) else {})
    observed_by_key = {str(record.get("artifact_key") or ""): record for record in observed_records if record.get("artifact_key")}

    candidate_results: list[dict[str, Any]] = []
    verified_count = 0
    missing_legacy_count = 0
    missing_future_count = 0
    digest_mismatch_count = 0
    not_observed_count = 0
    for candidate in planned_candidates:
        result = _dual_write_candidate_result(effective_root, candidate, observed_by_key.get(candidate["artifact_key"]))
        candidate_results.append(result)
        status = result["status"]
        if status == "verified_dual_written":
            verified_count += 1
        if status == "missing_legacy":
            missing_legacy_count += 1
        if status == "missing_future":
            missing_future_count += 1
        if status == "digest_mismatch":
            digest_mismatch_count += 1
        if status == "not_observed":
            not_observed_count += 1

    planned_keys = {item["artifact_key"] for item in planned_candidates}
    out_of_scope_observed, high_risk_observed, medium_risk_observed = _classify_observed_dual_write_scope(
        observed_records=observed_records,
        planned_keys=planned_keys,
        self_artifact_keys={"workspace_dual_write_expansion_result", "workspace_dual_write_expansion_workflow"},
    )

    blocking_reasons: list[str] = []
    warnings: list[str] = []
    if expansion_plan_error:
        blocking_reasons.append("expansion_plan_json_malformed")
    if isinstance(expansion_plan, dict) and expansion_plan.get("status") == "blocked":
        blocking_reasons.append("workspace_dual_write_expansion_plan_not_ready")
    if isinstance(expansion_plan, dict):
        for reason in expansion_plan.get("blocking_reasons") or []:
            blocking_reasons.append(f"expansion_plan:{reason}")
    if observed_plan_error:
        blocking_reasons.append("workspace_dual_write_plan_unavailable_or_malformed")
    if not observed_records:
        blocking_reasons.append("workspace_dual_write_plan_not_observed")
    if not planned_candidates:
        blocking_reasons.append("expansion_plan_has_no_candidates")
    if missing_legacy_count:
        blocking_reasons.append("candidate_legacy_files_missing")
    if missing_future_count:
        blocking_reasons.append("candidate_future_files_missing")
    if digest_mismatch_count:
        blocking_reasons.append("candidate_digest_mismatch")
    if not_observed_count:
        warnings.append("some_planned_candidates_not_seen_in_workspace_dual_write_plan")
    if out_of_scope_observed:
        warnings.append("observed_dual_write_records_outside_expansion_plan")
    if high_risk_observed:
        warnings.append("high_risk_artifacts_observed_in_dual_write_output")
    if medium_risk_observed:
        warnings.append("medium_risk_artifacts_observed_in_dual_write_output")

    if observed_plan_error or not observed_records:
        status = "not_run"
    elif blocking_reasons:
        status = "blocked"
    elif verified_count == len(planned_candidates) and not out_of_scope_observed and not high_risk_observed:
        status = "verified"
    else:
        status = "partial"

    result_artifact = _workspace_expansion_result_artifact_metadata(effective_root, written=False)
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-result.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "result_artifact": result_artifact,
        "summary": {
            "planned_candidate_count": len(planned_candidates),
            "observed_write_record_count": len(observed_records),
            "verified_candidate_count": verified_count,
            "missing_legacy_count": missing_legacy_count,
            "missing_future_count": missing_future_count,
            "digest_mismatch_count": digest_mismatch_count,
            "not_observed_candidate_count": not_observed_count,
            "out_of_scope_observed_count": len(out_of_scope_observed),
            "high_risk_observed_count": len(high_risk_observed),
            "medium_risk_observed_count": len(medium_risk_observed),
            "legacy_canonical_path_remains_authoritative": True,
            "foldered_canonical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "expansion_plan_summary": _compact_expansion_plan_summary(expansion_plan if isinstance(expansion_plan, dict) else {}),
        "observed_dual_write_plan_input": observed_input,
        "candidate_results": candidate_results,
        "out_of_scope_observed_artifacts": out_of_scope_observed,
        "high_risk_observed_artifacts": high_risk_observed,
        "medium_risk_observed_artifacts": medium_risk_observed,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _dual_write_expansion_result_next_actions(status, blocking_reasons, warnings),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if write_result:
        result_path = effective_root / "workspace" / "workspace-dual-write-expansion-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_expansion_result_artifact_metadata(effective_root, written=True)
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_compute_workspace_dual_write_expansion_plan(*, default_artifact_root: Path, expansion_plan_json: str | None) -> tuple[dict[str, Any], str]:
    payload, error = _parse_json_object(expansion_plan_json, field_name="expansion_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, ""
        return {
            "schema_version": "invalid-json",
            "status": "blocked",
            "summary": {"candidate_count": 0},
            "candidate_artifacts": [],
            "blocking_reasons": ["expansion_plan_json_malformed"],
            "warnings": [],
        }, error
    return plan_workspace_dual_write_expansion_payload(default_artifact_root=default_artifact_root), ""


def _compact_expansion_plan_summary(expansion_plan: dict[str, Any]) -> dict[str, Any]:
    summary = expansion_plan.get("summary") if isinstance(expansion_plan.get("summary"), dict) else {}
    selection_policy = expansion_plan.get("selection_policy") if isinstance(expansion_plan.get("selection_policy"), dict) else {}
    return {
        "schema_version": expansion_plan.get("schema_version") or "",
        "status": expansion_plan.get("status") or "",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "explicit_selection": bool(summary.get("explicit_selection")),
        "pilot_result_status": summary.get("pilot_result_status") or "",
        "pilot_evidence_score": float(summary.get("pilot_evidence_score") or 0.0),
        "legacy_canonical_path_remains_authoritative": bool(selection_policy.get("legacy_canonical_path_remains_authoritative", True)),
        "physical_migration_enabled": bool(selection_policy.get("physical_migration_enabled", False)),
        "actual_dual_write_enabled": bool(selection_policy.get("actual_dual_write_enabled", False)),
    }


def _workspace_expansion_result_artifact_metadata(artifact_root: Path, *, written: bool) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_dual_write_expansion_result",
        "legacy_path": "workspace/workspace-dual-write-expansion-result.json",
        "future_path": "/workspace/review/workspace-dual-write-expansion-result.json",
        "path": str(artifact_root / "workspace" / "workspace-dual-write-expansion-result.json"),
        "written": written,
        "canonical_path_remains_authoritative": True,
    }


def _classify_observed_dual_write_scope(
    *,
    observed_records: list[dict[str, Any]],
    planned_keys: set[str],
    self_artifact_keys: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    out_of_scope_observed: list[dict[str, Any]] = []
    high_risk_observed: list[dict[str, Any]] = []
    medium_risk_observed: list[dict[str, Any]] = []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    for record in observed_records:
        key = str(record.get("artifact_key") or "")
        if not key or key in self_artifact_keys or not record.get("dual_write_enabled"):
            continue
        route = routes_by_key.get(key)
        risk = _dual_write_route_risk(route) if route is not None else {"risk_level": "unknown", "rationale": "observed artifact is not registered", "category": "unknown", "producer_roles": []}
        summary = {
            "artifact_key": key,
            "legacy_path": record.get("canonical_path") or record.get("legacy_path") or "",
            "future_path": record.get("future_path") or "",
            "write_paths": list(record.get("write_paths") or []),
            "dual_write_enabled": bool(record.get("dual_write_enabled")),
            "risk": risk,
        }
        if key not in planned_keys:
            out_of_scope_observed.append(summary)
        if risk.get("risk_level") == "high":
            high_risk_observed.append(summary)
        if risk.get("risk_level") == "medium":
            medium_risk_observed.append(summary)
    return out_of_scope_observed, high_risk_observed, medium_risk_observed


def _dual_write_expansion_result_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_dual_write_plan_unavailable_or_malformed" in blockers or "workspace_dual_write_plan_not_observed" in blockers:
        actions.append("run_pipeline_with_scoped_expansion_keys_and_capture_workspace_dual_write_plan")
    if "expansion_plan_json_malformed" in blockers:
        actions.append("fix_expansion_plan_json_or_omit_it_to_recompute_plan")
    if "workspace_dual_write_expansion_plan_not_ready" in blockers:
        actions.append("resolve_expansion_plan_blockers_before_running_pipeline")
    if "candidate_legacy_files_missing" in blockers or "candidate_future_files_missing" in blockers:
        actions.append("inspect_dual_write_expansion_output_paths_and_rerun_scoped_pipeline")
    if "candidate_digest_mismatch" in blockers:
        actions.append("compare_legacy_and_future_expansion_artifacts_before_any_migration")
    if "observed_dual_write_records_outside_expansion_plan" in warnings:
        actions.append("review_out_of_scope_observed_dual_writes_before_next_expansion")
    if "high_risk_artifacts_observed_in_dual_write_output" in warnings:
        actions.append("split_high_risk_artifacts_into_separate_manual_review")
    if status == "verified":
        actions.append("feed_verified_expansion_result_back_into_workspace_readiness_before_foldered_canonical_pilot")
    if not actions:
        actions.append("review_expansion_result_before_next_dual_write_scope")
    return actions


def _workspace_dual_write_expansion_workflow_status(expansion_plan: dict[str, Any], expansion_result: dict[str, Any], expansion_plan_error: str) -> str:
    if expansion_plan_error or expansion_plan.get("status") == "blocked":
        return "blocked"
    result_status = str(expansion_result.get("status") or "unknown")
    if result_status == "verified":
        return "verified"
    if result_status == "partial":
        return "partial"
    if result_status == "blocked":
        return "blocked"
    if result_status == "not_run":
        return "ready_for_review"
    return "ready_for_review"


def _workspace_dual_write_expansion_workflow_blockers(
    expansion_plan: dict[str, Any],
    expansion_result: dict[str, Any],
    expansion_plan_error: str,
    status: str,
) -> list[str]:
    reasons: list[str] = []
    if expansion_plan_error:
        reasons.append("expansion_plan_json_malformed")
    if expansion_plan.get("status") == "blocked":
        reasons.append("workspace_dual_write_expansion_plan_not_ready")
    for reason in expansion_plan.get("blocking_reasons") or []:
        reasons.append(f"expansion_plan:{reason}")
    if status in {"blocked", "partial"}:
        for reason in expansion_result.get("blocking_reasons") or []:
            reasons.append(f"expansion_result:{reason}")
    return list(dict.fromkeys(reasons))


def _workspace_dual_write_expansion_workflow_warnings(expansion_plan: dict[str, Any], expansion_result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    warnings.extend(f"expansion_plan:{item}" for item in expansion_plan.get("warnings") or [])
    warnings.extend(f"expansion_result:{item}" for item in expansion_result.get("warnings") or [])
    return list(dict.fromkeys(warnings))


def _workspace_dual_write_expansion_workflow_next_actions(status: str, expansion_result: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if status == "ready_for_review":
        actions.append("review_expansion_plan_then_run_explicit_scoped_dual_write_pipeline")
    if status in {"verified", "partial"}:
        actions.append("review_expansion_result_before_foldered_canonical_migration_pilot")
    if status == "verified":
        actions.append("update_consumer_readiness_with_verified_expansion_evidence")
    if status == "blocked":
        actions.append("resolve_expansion_workflow_blockers_before_running_dual_write_expansion")
    for action in expansion_result.get("recommended_next_actions") or []:
        if action not in actions:
            actions.append(action)
    return actions


def _workspace_dual_write_expansion_review_workflow(
    *,
    candidate_keys: list[str],
    result_status: str,
    workflow_status: str,
    write_result: bool,
) -> dict[str, Any]:
    key_arg = ",".join(candidate_keys)
    if workflow_status == "blocked":
        commands = [
            {
                "step": "resolve_expansion_workflow_blockers",
                "description": "Resolve expansion plan or observed-result blockers before running an opt-in dual-write expansion pipeline.",
                "requires_review": True,
                "runs_inside_this_tool": False,
            }
        ]
    else:
        commands = [
            {
                "step": "run_explicit_scoped_dual_write_expansion_pipeline",
                "description": "Run the normal pipeline separately with reviewed expansion artifact keys only.",
                "flags": [
                    "--enable-workspace-dual-write",
                    "--workspace-dual-write-artifact-keys",
                    key_arg,
                ],
                "requires_review": True,
                "runs_inside_this_tool": False,
            },
            {
                "step": "verify_observed_dual_write_expansion_output",
                "description": "Call this workflow again after the pipeline writes workspace/workspace-dual-write-plan.json, or pass workspace_dual_write_plan_json directly.",
                "tool": "review_workspace_dual_write_expansion_workflow",
                "suggested_arguments": {
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": False,
                },
                "requires_review": True,
            },
            {
                "step": "record_verified_expansion_result",
                "description": "Only after reviewing the verification payload, call with write_result=true to write the expansion audit artifact.",
                "tool": "review_workspace_dual_write_expansion_workflow",
                "suggested_arguments": {
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": True,
                },
                "requires_review": True,
                "already_requested": bool(write_result),
            },
        ]
    return {
        "requires_explicit_pipeline_run": workflow_status != "blocked",
        "requires_review_before_expansion": True,
        "requires_result_review_before_writing_audit": True,
        "workflow_status": workflow_status,
        "result_verification_status": result_status,
        "selected_artifact_keys": candidate_keys,
        "recommended_commands": commands,
        "does_not_run_pipeline": True,
        "does_not_enable_dual_write": True,
        "does_not_migrate_paths": True,
        "legacy_canonical_path_remains_authoritative": True,
    }
