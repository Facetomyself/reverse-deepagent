from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.tools.workspace_artifact_reader import (
    load_workspace_artifact_json_object,
    summarize_workspace_artifact_read,
)
from reverse_deepagent.tools.workspace_helpers import (
    _compact_pilot_plan_summary,
    _compact_readiness_summary,
    _dual_write_pilot_next_actions,
    _dual_write_pilot_result_next_actions,
    _dual_write_route_risk,
    _file_digest_stat,
    _is_high_risk_dual_write_route,
    _load_observed_dual_write_plan,
    _missing_file_stat,
    _observed_dual_write_records,
    _parse_artifact_keys_json,
    _parse_json_object,
    _parse_readiness_report,
    _planned_dual_write_candidates,
    _readiness_limited_dual_write_status,
    _safe_int,
    _workspace_dual_write_review_workflow,
    _workspace_dual_write_workflow_blocking_reasons,
    _workspace_dual_write_workflow_next_actions,
    _workspace_dual_write_workflow_status,
    _workspace_dual_write_workflow_warnings,
    _workspace_pilot_result_artifact_metadata,
    _artifact_ref_to_filesystem_path,
    _dual_write_candidate_result,
    _compact_observed_write_record,
)
from reverse_deepagent.tools.workspace_migration_readiness import assess_workspace_migration_readiness_payload
from reverse_deepagent.workspace_contract import WorkspacePathResolver, default_workspace_artifact_routes


ArtifactTool = Callable[..., dict[str, Any]]


def make_plan_workspace_dual_write_pilot_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for limited workspace dual-write pilot planning."""

    root = Path(default_artifact_root)

    def plan_workspace_dual_write_pilot(
        artifact_root: str | None = None,
        readiness_report_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 12,
    ) -> dict[str, Any]:
        """Plan a limited dual-write pilot without enabling dual-write or writing artifacts."""

        return plan_workspace_dual_write_pilot_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_report_json=readiness_report_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
        )

    plan_workspace_dual_write_pilot.__name__ = "plan_workspace_dual_write_pilot"
    plan_workspace_dual_write_pilot.__doc__ = (
        "Read-only limited workspace dual-write pilot plan. Uses workspace migration readiness, registered workspace routes, "
        "and optional explicit artifact keys to select reviewable low-risk pilot candidates. It only returns planned legacy/future "
        "write paths and review blockers; it does not inspect files, write artifacts, create directories, enable dual-write, migrate paths, "
        "change canonical paths, start browsers, or call MCP."
    )
    return plan_workspace_dual_write_pilot


def make_review_workspace_dual_write_pilot_workflow_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a review-first workflow tool for limited workspace dual-write pilots."""

    root = Path(default_artifact_root)

    def review_workspace_dual_write_pilot_workflow(
        artifact_root: str | None = None,
        delivery_source_audit_json: str | None = None,
        readiness_report_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 12,
        pilot_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Prepare and optionally verify a reviewed dual-write pilot workflow."""

        return review_workspace_dual_write_pilot_workflow_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            delivery_source_audit_json=delivery_source_audit_json,
            readiness_report_json=readiness_report_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            pilot_plan_json=pilot_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    review_workspace_dual_write_pilot_workflow.__name__ = "review_workspace_dual_write_pilot_workflow"
    review_workspace_dual_write_pilot_workflow.__doc__ = (
        "Compose workspace migration readiness, limited dual-write pilot planning, and optional observed-result verification "
        "into a single review workflow. It does not run the pipeline, enable dual-write, migrate paths, change canonical paths, "
        "start browsers, call MCP, or touch mobile runtimes. When write_result=true it only writes the pilot result audit artifact."
    )
    return review_workspace_dual_write_pilot_workflow


def make_record_workspace_dual_write_pilot_result_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a tool that inspects or records a limited workspace dual-write pilot result."""

    root = Path(default_artifact_root)

    def record_workspace_dual_write_pilot_result(
        artifact_root: str | None = None,
        pilot_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Inspect observed dual-write files and optionally write a pilot result audit artifact."""

        return record_workspace_dual_write_pilot_result_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            pilot_plan_json=pilot_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    record_workspace_dual_write_pilot_result.__name__ = "record_workspace_dual_write_pilot_result"
    record_workspace_dual_write_pilot_result.__doc__ = (
        "Inspect the output of an explicit workspace dual-write run against a reviewed pilot plan. "
        "By default it is read-only and only checks legacy/future file presence and digests. "
        "When write_result=true it writes only workspace/workspace-dual-write-pilot-result.json; "
        "it never enables dual-write, migrates paths, changes canonical paths, starts browsers, call MCP, or touches mobile runtimes."
    )
    return record_workspace_dual_write_pilot_result


def plan_workspace_dual_write_pilot_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_report_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 12,
) -> dict[str, Any]:
    """Return a plan-only limited dual-write pilot candidate report."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(default_artifact_root=effective_root)
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
            if _dual_write_route_risk(route)["risk_level"] != "low":
                continue
            selected_routes.append(route)
            if len(selected_routes) >= max_count:
                break
    if max_count == 0:
        selected_routes = []

    candidate_artifacts: list[dict[str, Any]] = []
    high_risk_requested: list[str] = []
    medium_risk_requested: list[str] = []
    for route in selected_routes:
        risk = _dual_write_route_risk(route)
        if explicit_selection and risk["risk_level"] == "high":
            high_risk_requested.append(route.artifact_key)
        if explicit_selection and risk["risk_level"] == "medium":
            medium_risk_requested.append(route.artifact_key)
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

    readiness_status = _readiness_limited_dual_write_status(readiness_report)
    blockers: list[str] = []
    if readiness_status != "ready_for_review":
        blockers.append("workspace_migration_readiness_not_ready_for_dual_write_pilot")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if high_risk_requested:
        blockers.append("high_risk_requested_artifacts_require_separate_review")
    if not candidate_artifacts:
        blockers.append("no_dual_write_pilot_candidates_selected")
    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_artifacts),
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "high_risk_requested_artifact_count": len(high_risk_requested),
            "medium_risk_requested_artifact_count": len(medium_risk_requested),
            "readiness_limited_dual_write_status": readiness_status,
            "max_artifacts": max_count,
            "explicit_selection": explicit_selection,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_risk_level": "low",
            "default_allowed_categories": sorted({"workspace", "runtime-context", "source", "network", "evidence"}),
            "explicit_keys_may_include_medium_risk": True,
            "high_risk_explicit_keys_block_plan": True,
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "actual_dual_write_enabled": False,
        },
        "readiness_summary": _compact_readiness_summary(readiness_report),
        "candidate_artifacts": candidate_artifacts,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "high_risk_requested_artifact_keys": high_risk_requested,
            "medium_risk_requested_artifact_keys": medium_risk_requested,
        },
        "blocking_reasons": blockers,
        "recommended_next_actions": _dual_write_pilot_next_actions(
            blockers=blockers,
            medium_risk_requested=medium_risk_requested,
        ),
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


def review_workspace_dual_write_pilot_workflow_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    delivery_source_audit_json: str | None = None,
    readiness_report_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 12,
    pilot_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Compose readiness, pilot planning, and optional result verification."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(
            default_artifact_root=effective_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )
    pilot_plan, pilot_plan_error = _parse_json_object(pilot_plan_json, field_name="pilot_plan_json")
    if pilot_plan is None:
        if pilot_plan_error:
            pilot_plan = _malformed_dual_write_pilot_plan(
                artifact_root=effective_root,
                error=pilot_plan_error,
                readiness_report=readiness_report,
            )
        else:
            pilot_plan = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=effective_root,
                readiness_report_json=json.dumps(readiness_report, sort_keys=True),
                artifact_keys_json=artifact_keys_json,
                max_artifacts=max_artifacts,
            )

    pilot_result = record_workspace_dual_write_pilot_result_payload(
        default_artifact_root=effective_root,
        pilot_plan_json=json.dumps(pilot_plan, sort_keys=True),
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
        write_result=write_result,
    )
    status = _workspace_dual_write_workflow_status(readiness_report, pilot_plan, pilot_result)
    blocking_reasons = _workspace_dual_write_workflow_blocking_reasons(readiness_report, pilot_plan, pilot_result, status)
    warnings = _workspace_dual_write_workflow_warnings(pilot_result)
    candidate_keys = [str(item.get("artifact_key")) for item in pilot_plan.get("candidate_artifacts", []) if item.get("artifact_key")]
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-workflow.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "readiness_status": readiness_report.get("status") or "unknown",
            "readiness_limited_dual_write_status": _readiness_limited_dual_write_status(readiness_report),
            "pilot_plan_status": pilot_plan.get("status") or "unknown",
            "pilot_result_status": pilot_result.get("status") or "unknown",
            "selected_artifact_count": len(candidate_keys),
            "blocking_reason_count": len(blocking_reasons),
            "warning_count": len(warnings),
            "review_required": True,
            "write_result_requested": bool(write_result),
            "mobile_full_runtime_chains_deferred": True,
        },
        "readiness_report": readiness_report,
        "pilot_plan": pilot_plan,
        "pilot_result": pilot_result,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_workflow_next_actions(status, pilot_result),
        "review_workflow": _workspace_dual_write_review_workflow(
            candidate_keys=candidate_keys,
            result_status=str(pilot_result.get("status") or "unknown"),
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
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _malformed_dual_write_pilot_plan(
    *,
    artifact_root: Path,
    error: str,
    readiness_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-plan.v1",
        "status": "blocked",
        "artifact_root": str(artifact_root),
        "summary": {
            "candidate_count": 0,
            "readiness_limited_dual_write_status": _readiness_limited_dual_write_status(readiness_report),
            "mobile_full_runtime_chains_deferred": True,
        },
        "readiness_summary": _compact_readiness_summary(readiness_report),
        "candidate_artifacts": [],
        "blocking_reasons": ["pilot_plan_json_malformed"],
        "error": error,
        "recommended_next_actions": ["fix_pilot_plan_json_or_omit_it_to_use_default_plan"],
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


def record_workspace_dual_write_pilot_result_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    pilot_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Inspect an explicit dual-write run and optionally record a pilot result artifact."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    pilot_plan, pilot_plan_error = _parse_json_object(pilot_plan_json, field_name="pilot_plan_json")
    if pilot_plan is None and not pilot_plan_error:
        pilot_plan = plan_workspace_dual_write_pilot_payload(default_artifact_root=effective_root)
    observed_plan, observed_plan_error, observed_input = _load_observed_dual_write_plan(
        default_artifact_root=effective_root,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
    )
    planned_candidates = _planned_dual_write_candidates(pilot_plan if isinstance(pilot_plan, dict) else {})
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
    out_of_scope_observed: list[dict[str, Any]] = []
    high_risk_observed: list[dict[str, Any]] = []
    medium_risk_observed: list[dict[str, Any]] = []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    for record in observed_records:
        key = str(record.get("artifact_key") or "")
        if not key or key == "workspace_dual_write_pilot_result" or not record.get("dual_write_enabled"):
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

    blocking_reasons: list[str] = []
    warnings: list[str] = []
    if pilot_plan_error:
        blocking_reasons.append("pilot_plan_json_malformed")
    if observed_plan_error:
        blocking_reasons.append("workspace_dual_write_plan_unavailable_or_malformed")
    if not observed_records:
        blocking_reasons.append("workspace_dual_write_plan_not_observed")
    if not planned_candidates:
        blocking_reasons.append("pilot_plan_has_no_candidates")
    if missing_legacy_count:
        blocking_reasons.append("candidate_legacy_files_missing")
    if missing_future_count:
        blocking_reasons.append("candidate_future_files_missing")
    if digest_mismatch_count:
        blocking_reasons.append("candidate_digest_mismatch")
    if not_observed_count:
        warnings.append("some_planned_candidates_not_seen_in_workspace_dual_write_plan")
    if out_of_scope_observed:
        warnings.append("observed_dual_write_records_outside_pilot_plan")
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

    result_artifact = _workspace_pilot_result_artifact_metadata(effective_root, written=False)
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
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
        "pilot_plan_summary": _compact_pilot_plan_summary(pilot_plan if isinstance(pilot_plan, dict) else {}),
        "observed_dual_write_plan_input": observed_input,
        "candidate_results": candidate_results,
        "out_of_scope_observed_artifacts": out_of_scope_observed,
        "high_risk_observed_artifacts": high_risk_observed,
        "medium_risk_observed_artifacts": medium_risk_observed,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_next_actions": _dual_write_pilot_result_next_actions(status, blocking_reasons, warnings),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if write_result:
        result_path = effective_root / "workspace" / "workspace-dual-write-pilot-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_pilot_result_artifact_metadata(effective_root, written=True)
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
