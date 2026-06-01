from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import FinalResult
from reverse_deepagent.workspace_contract import WorkspacePathResolution, WorkspacePathResolver, default_workspace_artifact_routes


ArtifactTool = Callable[..., dict[str, Any]]


def make_export_reverse_artifacts_tool(runtime: ReverseRuntime) -> ArtifactTool:
    """Create a tool wrapper that exports runtime artifacts."""

    def export_reverse_artifacts(final_result_json: str | None = None) -> dict[str, Any]:
        final_result = FinalResult.model_validate_json(final_result_json) if final_result_json else None
        return runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")

    export_reverse_artifacts.__name__ = "export_reverse_artifacts"
    export_reverse_artifacts.__doc__ = "Export runtime artifacts and return a normalized export bundle."
    return export_reverse_artifacts


def make_read_workspace_artifact_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only resolver-backed workspace artifact reader tool."""

    root = Path(default_artifact_root)

    def read_workspace_artifact(
        artifact_ref: str,
        artifact_root: str | None = None,
        max_chars: int = 20000,
    ) -> dict[str, Any]:
        """Read a workspace artifact by key, legacy path, future path, or virtual URI without mutating files."""

        return read_workspace_artifact_payload(
            artifact_ref=artifact_ref,
            default_artifact_root=root,
            artifact_root=artifact_root,
            max_chars=max_chars,
        )

    read_workspace_artifact.__name__ = "read_workspace_artifact"
    read_workspace_artifact.__doc__ = (
        "Read a workspace artifact by artifact key, legacy workspace/*.json path, "
        "future /workspace/<area>/ path, virtual://workspace/... URI, or artifact-root-relative path. "
        "The tool is read-only and does not migrate or dual-write artifacts."
    )
    return read_workspace_artifact


def make_audit_workspace_artifact_consumers_tool() -> ArtifactTool:
    """Create a read-only audit tool for workspace artifact-ref adoption."""

    def audit_workspace_artifact_consumers() -> dict[str, Any]:
        """Return a static resolver-adoption matrix for workspace artifact consumers."""

        return audit_workspace_artifact_consumers_payload()

    audit_workspace_artifact_consumers.__name__ = "audit_workspace_artifact_consumers"
    audit_workspace_artifact_consumers.__doc__ = (
        "Read-only audit of tools and workflow inputs that consume workspace artifacts or filesystem paths. "
        "Classifies consumers as resolver-ready, partial, candidate, explicit-filesystem-boundary, or non-workspace input; "
        "does not inspect files, write artifacts, migrate paths, enable dual-write, start browsers, or call MCP."
    )
    return audit_workspace_artifact_consumers


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


def audit_workspace_artifact_consumers_payload() -> dict[str, Any]:
    """Return the current resolver adoption matrix for known workspace consumers."""

    consumers = _workspace_consumer_audit_entries()
    by_status: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    for item in consumers:
        by_status[item["resolver_status"]] = by_status.get(item["resolver_status"], 0) + 1
        by_owner[item["owner"]] = by_owner.get(item["owner"], 0) + 1
    follow_up_candidates = [
        item
        for item in consumers
        if item["resolver_status"] in {"candidate", "partial"}
        and item["next_action"] not in {"keep-explicit-filesystem-boundary", "none"}
    ]
    explicit_boundaries = [item for item in consumers if item["resolver_status"] == "explicit-filesystem-boundary"]
    return {
        "schema_version": "reverse-deepagent.workspace-consumer-audit.v1",
        "status": "review",
        "summary": {
            "consumer_count": len(consumers),
            "by_status": dict(sorted(by_status.items())),
            "by_owner": dict(sorted(by_owner.items())),
            "follow_up_candidate_count": len(follow_up_candidates),
            "explicit_filesystem_boundary_count": len(explicit_boundaries),
            "mobile_full_runtime_chains_deferred": True,
        },
        "consumers": consumers,
        "follow_up_candidates": follow_up_candidates,
        "explicit_filesystem_boundaries": explicit_boundaries,
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


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


def _parse_delivery_source_audit(delivery_source_audit_json: str | None) -> dict[str, Any] | None:
    if not delivery_source_audit_json:
        return None
    try:
        payload = json.loads(delivery_source_audit_json)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "error": f"delivery_source_audit_json is not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "error": "delivery_source_audit_json must decode to an object",
        }
    return payload


def _summarize_delivery_source_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "schema_version": "missing",
            "status": "missing",
            "artifact_count": 0,
            "source_artifact_ref_count": 0,
            "source_path_count": 0,
            "workspace_resolved_count": 0,
            "external_source_path_count": 0,
            "legacy_source_path_count": 0,
            "future_source_path_count": 0,
            "artifact_root_relative_source_path_count": 0,
            "relative_source_path_count": 0,
            "by_source_input_kind": {},
            "by_source_path_kind": {},
            "malformed": False,
        }
    malformed = payload.get("status") == "malformed"
    return {
        "schema_version": payload.get("schema_version") or "unknown",
        "status": "malformed" if malformed else "observed",
        "artifact_count": _safe_int(payload.get("artifact_count")),
        "source_artifact_ref_count": _safe_int(payload.get("source_artifact_ref_count")),
        "source_path_count": _safe_int(payload.get("source_path_count")),
        "workspace_resolved_count": _safe_int(payload.get("workspace_resolved_count")),
        "external_source_path_count": _safe_int(payload.get("external_source_path_count")),
        "legacy_source_path_count": _safe_int(payload.get("legacy_source_path_count")),
        "future_source_path_count": _safe_int(payload.get("future_source_path_count")),
        "artifact_root_relative_source_path_count": _safe_int(payload.get("artifact_root_relative_source_path_count")),
        "relative_source_path_count": _safe_int(payload.get("relative_source_path_count")),
        "by_source_input_kind": payload.get("by_source_input_kind") if isinstance(payload.get("by_source_input_kind"), dict) else {},
        "by_source_path_kind": payload.get("by_source_path_kind") if isinstance(payload.get("by_source_path_kind"), dict) else {},
        "malformed": malformed,
        "error": payload.get("error") if malformed else "",
    }


def _workspace_migration_next_actions(
    *,
    limited_dual_write_blockers: list[str],
    foldered_blockers: list[str],
    delivery_source_audit_present: bool,
) -> list[str]:
    actions: list[str] = []
    if limited_dual_write_blockers:
        actions.append("resolve_candidate_consumers_before_dual_write_pilot")
    else:
        actions.append("review_limited_dual_write_pilot_for_registered_workspace_artifacts")
    if not delivery_source_audit_present:
        actions.append("run_execute_local_delivery_dry_run_and_collect_delivery_artifact_source_audit")
    if "source_path_usage_observed" in foldered_blockers:
        actions.append("continue_monitoring_source_path_usage_before_foldered_canonical_migration")
    if "external_source_path_usage_observed" in foldered_blockers:
        actions.append("keep_external_filesystem_delivery_sources_as_explicit_boundaries")
    if "partial_consumers_still_present" in foldered_blockers:
        actions.append("do_not_start_foldered_canonical_migration_until_partial_consumers_are_closed_or_explicitly_accepted")
    if not foldered_blockers:
        actions.append("review_narrow_foldered_canonical_migration_pilot")
    return actions


_LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"workspace", "runtime-context", "source", "network", "evidence"})
_MEDIUM_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"triage", "audit"})


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
            "default_allowed_categories": sorted(_LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES),
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


def _parse_readiness_report(readiness_report_json: str | None) -> dict[str, Any] | None:
    if not readiness_report_json:
        return None
    try:
        payload = json.loads(readiness_report_json)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "summary": {"limited_dual_write_pilot_status": "blocked"},
            "error": f"readiness_report_json is not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "summary": {"limited_dual_write_pilot_status": "blocked"},
            "error": "readiness_report_json must decode to an object",
        }
    return payload


def _parse_artifact_keys_json(artifact_keys_json: str | None) -> tuple[list[str] | None, str]:
    if artifact_keys_json is None:
        return None, ""
    try:
        payload = json.loads(artifact_keys_json)
    except json.JSONDecodeError as exc:
        return [], f"artifact_keys_json is not valid JSON: {exc}"
    if not isinstance(payload, list) or not all(isinstance(item, str) and item for item in payload):
        return [], "artifact_keys_json must decode to a list of non-empty strings"
    return list(dict.fromkeys(payload)), ""


def _dual_write_route_risk(route: Any) -> dict[str, Any]:
    if route.artifact_key == "workspace_dual_write_plan" or route.category in _MEDIUM_RISK_DUAL_WRITE_PILOT_CATEGORIES:
        risk_level = "medium"
        rationale = "review or audit artifact; explicit selection is allowed but should receive extra reviewer attention"
    elif _is_high_risk_dual_write_route(route):
        risk_level = "high"
        rationale = "delivery, rebuild, hook, trace, export, or transaction artifact; keep out of default pilot"
    elif route.category in _LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES:
        risk_level = "low"
        rationale = "metadata-or-evidence-style workspace artifact suitable for limited review pilot"
    else:
        risk_level = "high"
        rationale = "unclassified workspace artifact; keep out of default pilot until reviewed"
    return {
        "risk_level": risk_level,
        "rationale": rationale,
        "category": route.category,
        "producer_roles": list(route.producer_roles),
    }


def _is_high_risk_dual_write_route(route: Any) -> bool:
    high_risk_categories = {"export", "rebuild", "hook-timeline", "trace"}
    high_risk_prefixes = (
        "workspace_backend_",
        "workspace_delivery_",
        "workspace_external_",
        "workspace_final_delivery_",
    )
    if route.category in high_risk_categories:
        return True
    if route.artifact_key == "workspace_final":
        return True
    return any(str(route.artifact_key).startswith(prefix) for prefix in high_risk_prefixes)


def _readiness_limited_dual_write_status(readiness_report: dict[str, Any]) -> str:
    summary = readiness_report.get("summary") if isinstance(readiness_report.get("summary"), dict) else {}
    return str(summary.get("limited_dual_write_pilot_status") or "blocked")


def _compact_readiness_summary(readiness_report: dict[str, Any]) -> dict[str, Any]:
    summary = readiness_report.get("summary") if isinstance(readiness_report.get("summary"), dict) else {}
    return {
        "schema_version": readiness_report.get("schema_version") or "",
        "status": readiness_report.get("status") or "",
        "limited_dual_write_pilot_status": summary.get("limited_dual_write_pilot_status") or "blocked",
        "foldered_canonical_migration_status": summary.get("foldered_canonical_migration_status") or "blocked",
        "partial_count": _safe_int(summary.get("partial_count")),
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "delivery_source_audit_observed": bool(summary.get("delivery_source_audit_observed")),
    }


def _dual_write_pilot_next_actions(*, blockers: list[str], medium_risk_requested: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_migration_readiness_not_ready_for_dual_write_pilot" in blockers:
        actions.append("resolve_workspace_migration_readiness_blockers_before_pilot")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_or_register_unknown_artifact_keys")
    if "high_risk_requested_artifacts_require_separate_review" in blockers:
        actions.append("split_high_risk_delivery_or_transaction_artifacts_into_separate_manual_review")
    if "no_dual_write_pilot_candidates_selected" in blockers:
        actions.append("select_low_risk_workspace_artifact_keys_for_pilot")
    if medium_risk_requested and not blockers:
        actions.append("review_medium_risk_audit_or_triage_artifacts_before_pilot")
    if not blockers:
        actions.append("review_plan_then_run_pipeline_with_enable_workspace_dual_write_for_selected_scope_only")
    return actions


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def read_workspace_artifact_payload(
    *,
    artifact_ref: str,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Read a workspace artifact and return the same payload as the public reader tool."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    resolver = WorkspacePathResolver()
    resolution = resolver.resolve_artifact_key(artifact_ref) or resolver.resolve_path(artifact_ref)
    candidate_paths = _candidate_paths(effective_root, artifact_ref, resolution)
    checked_paths: list[str] = []
    for candidate in candidate_paths:
        checked_paths.append(str(candidate))
        if not candidate.exists() or not candidate.is_file():
            continue
        return _read_artifact_file(
            candidate,
            artifact_ref=artifact_ref,
            artifact_root=effective_root,
            resolution=resolution,
            candidate_paths=candidate_paths,
            checked_paths=checked_paths,
            max_chars=max_chars,
        )
    resolver_metrics = _workspace_resolver_metrics(
        artifact_ref=artifact_ref,
        artifact_root=effective_root,
        resolution=resolution,
        candidate_paths=candidate_paths,
        checked_paths=checked_paths,
        hit_path=None,
        status="missing",
    )
    return {
        "status": "missing",
        "artifact_ref": artifact_ref,
        "artifact_root": str(effective_root),
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolution": resolution.to_dict() if resolution else {},
        "checked_paths": checked_paths,
        "resolver_metrics": resolver_metrics,
        "side_effect_policy": _reader_side_effect_policy(),
    }


def load_workspace_artifact_json_object(
    *,
    artifact_ref: str,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    field_name: str = "artifact_ref",
    max_chars: int = 20000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a workspace artifact and return its JSON object plus read diagnostics."""

    result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        artifact_root=artifact_root,
        max_chars=max_chars,
    )
    if result.get("status") != "found":
        raise ValueError(f"{field_name} could not be read: {result.get('status')}; checked_paths={result.get('checked_paths')}")
    if result.get("content_type") != "json":
        raise ValueError(f"{field_name} must resolve to a JSON object artifact; content_type={result.get('content_type')}")
    value = result.get("json")
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must resolve to a JSON object artifact")
    return value, result


def _workspace_consumer_audit_entries() -> list[dict[str, Any]]:
    """Return the static list of known workspace artifact / path consumers."""

    return [
        _consumer_entry(
            consumer_id="coordinator.read_workspace_artifact",
            owner="coordinator",
            tool="read_workspace_artifact",
            inputs=("artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact key, legacy path, future path, virtual URI, and artifact-root-relative fallback",
            next_action="none",
            rationale="Shared read-only resolver consumer with compatibility metrics.",
        ),
        _consumer_entry(
            consumer_id="timeline.review_flow_timeline",
            owner="timeline",
            tool="review_flow_timeline",
            inputs=("flow_timeline_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads through load_workspace_artifact_json_object.",
        ),
        _consumer_entry(
            consumer_id="hook.review_hook_artifacts",
            owner="hook",
            tool="review_hook_artifacts",
            inputs=("hook_artifacts_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads hook artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="debugger.review_debugger_artifacts",
            owner="debugger",
            tool="review_debugger_artifacts",
            inputs=("debugger_artifacts_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads debugger artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="rebuild.review_rebuild_artifacts",
            owner="rebuild",
            tool="review_rebuild_artifacts",
            inputs=("rebuild_result_artifact_ref", "rebuild_plan_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref inputs plus legacy JSON string inputs",
            next_action="none",
            rationale="Read-only rebuild review accepts artifact refs for both result and plan payloads.",
        ),
        _consumer_entry(
            consumer_id="review.evaluate_delivery_review_gate",
            owner="review",
            tool="evaluate_delivery_review_gate",
            inputs=("rebuild_result_artifact_ref", "evidence_promotion_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref inputs plus legacy JSON string inputs",
            next_action="none",
            rationale="Review gate consumes reviewed JSON object artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_local_delivery.artifacts_json",
            owner="delivery",
            tool="execute_local_delivery",
            inputs=("artifacts_json[].source_artifact_ref", "artifacts_json[].artifact_ref", "artifact_root"),
            resolver_status="partial",
            current_support=(
                "source_artifact_ref / artifact_ref are resolver-ready; source_path remains supported with "
                "delivery_source_audit classification for explicit filesystem delivery and backward compatibility"
            ),
            next_action="continue-source_path-usage-monitoring-before-tightening",
            rationale=(
                "Delivery artifact source normalization is resolver-ready and now emits source compatibility metrics, "
                "but source_path is intentionally retained for non-workspace files and backward compatibility."
            ),
        ),
        _consumer_entry(
            consumer_id="rebuild.build_rebuild_delivery",
            owner="rebuild",
            tool="build_rebuild_delivery",
            inputs=("task_card_json", "final_result_json", "task_card_artifact_ref", "final_result_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="JSON string inputs or workspace artifact refs for task card and final result; artifact_root selects output root",
            next_action="none",
            rationale="Optional artifact refs reduce manual read-then-paste handoff without changing rebuild output writes or delivery gates.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_resume",
            owner="delivery",
            tool="execute_delivery_resume",
            inputs=("backend_manifest_path", "approval_ledger_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Resume runner validates and mutates transaction-scoped delivery state; backend manifest and approval ledger paths are apply-time safety gates.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_transition",
            owner="delivery",
            tool="execute_delivery_transition",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Transition execution can recover or commit backend manifest state and must not silently reinterpret mutation targets through workspace aliases.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_recovery",
            owner="delivery",
            tool="execute_delivery_recovery",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Recovery can restore a backend manifest from checkpoints; explicit paths keep reviewer intent and digest checks unambiguous.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_rollback",
            owner="delivery",
            tool="execute_delivery_rollback",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Rollback preflight / apply is a physical mutation boundary and should not be hidden behind artifact alias lookup.",
        ),
        _consumer_entry(
            consumer_id="review.record_review_approval",
            owner="review",
            tool="record_review_approval",
            inputs=("review_root", "subject_id", "subject_digest_sha256"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit review root plus logical subject identifiers",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Approval recording writes append-only audit artifacts; subject refs should stay logical and review_root should stay explicit.",
        ),
        _consumer_entry(
            consumer_id="delivery.plan_delivery_resume",
            owner="delivery",
            tool="plan_delivery_resume",
            inputs=("delivery_root", "transaction_id"),
            resolver_status="non-workspace-input",
            current_support="transaction root inspection only",
            next_action="none",
            rationale="The planner inspects a delivery transaction root, not workspace artifacts.",
        ),
        _consumer_entry(
            consumer_id="delivery.manage_delivery_transaction_lock_provider",
            owner="delivery",
            tool="manage_delivery_transaction_lock_provider",
            inputs=("delivery_root", "provider_id", "transaction_id"),
            resolver_status="non-workspace-input",
            current_support="transaction lock provider root and logical lock ids",
            next_action="none",
            rationale="Lock provider operations are transaction lease boundaries, not workspace artifact consumption.",
        ),
    ]


def _consumer_entry(
    *,
    consumer_id: str,
    owner: str,
    tool: str,
    inputs: tuple[str, ...],
    resolver_status: str,
    current_support: str,
    next_action: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "consumer_id": consumer_id,
        "owner": owner,
        "tool": tool,
        "inputs": list(inputs),
        "resolver_status": resolver_status,
        "current_support": current_support,
        "next_action": next_action,
        "rationale": rationale,
    }

def summarize_workspace_artifact_read(result: dict[str, Any] | None) -> dict[str, Any]:
    """Return compact, secret-safe diagnostics for artifact-ref based tool inputs."""

    if not result:
        return {}
    return {
        "status": result.get("status"),
        "artifact_ref": result.get("artifact_ref"),
        "artifact_root": result.get("artifact_root"),
        "path": result.get("path"),
        "content_type": result.get("content_type"),
        "content_truncated": bool(result.get("content_truncated")),
        "resolution_status": result.get("resolution_status"),
        "resolution": result.get("resolution") or {},
        "checked_paths": result.get("checked_paths") or [],
        "resolver_metrics": result.get("resolver_metrics") or {},
    }


def _candidate_paths(root: Path, artifact_ref: str, resolution: WorkspacePathResolution | None) -> list[Path]:
    raw_candidates: list[str] = []
    if resolution is not None:
        raw_candidates.extend(resolution.read_paths)
        raw_candidates.extend((resolution.canonical_path, resolution.future_path, resolution.virtual_uri))
    else:
        raw_candidates.append(artifact_ref)
    paths: list[Path] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        path = _artifact_ref_to_filesystem_path(root, raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _artifact_ref_to_filesystem_path(root: Path, value: str) -> Path:
    value = str(value).strip()
    if value.startswith("virtual://"):
        parsed = urlparse(value)
        netloc = parsed.netloc.strip("/")
        path = parsed.path.strip("/")
        relative = "/".join(part for part in (netloc, path) if part)
        return root / relative
    if value.startswith("/workspace/"):
        return root / value.lstrip("/")
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _artifact_ref_kind(artifact_ref: str, resolution: WorkspacePathResolution | None) -> str:
    value = str(artifact_ref).strip()
    if resolution is not None:
        if value == resolution.artifact_key:
            return "artifact-key"
        if value == resolution.legacy_path:
            return "legacy-path"
        if value == resolution.future_path or value.startswith("/workspace/"):
            return "future-path"
        if value == resolution.virtual_uri or value.startswith("virtual://"):
            return "virtual-uri"
    if value.startswith("virtual://"):
        return "virtual-uri"
    if value.startswith("/workspace/"):
        return "future-path"
    path = Path(value)
    if path.is_absolute():
        return "absolute-path"
    return "relative-path"


def _workspace_path_kind(path: Path, artifact_root: Path, resolution: WorkspacePathResolution | None) -> str:
    if resolution is None:
        return "direct-absolute" if path.is_absolute() and not _is_relative_to(path, artifact_root) else "direct-relative"
    canonical_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.canonical_path)
    future_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.future_path)
    if path == canonical_path:
        return "legacy-canonical"
    if path == future_path:
        return "future-foldered"
    if path.is_absolute() and not _is_relative_to(path, artifact_root):
        return "direct-absolute"
    return "direct-relative"


def _workspace_resolver_metrics(
    *,
    artifact_ref: str,
    artifact_root: Path,
    resolution: WorkspacePathResolution | None,
    candidate_paths: list[Path],
    checked_paths: list[str],
    hit_path: Path | None,
    status: str,
) -> dict[str, Any]:
    """Return read-only resolver compatibility diagnostics for migration planning."""

    checked_path_set = set(checked_paths)
    legacy_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.legacy_path) if resolution else None
    future_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.future_path) if resolution else None
    hit_path_kind = _workspace_path_kind(hit_path, artifact_root, resolution) if hit_path is not None else None
    legacy_path_checked = str(legacy_path) in checked_path_set if legacy_path is not None else False
    future_path_checked = str(future_path) in checked_path_set if future_path is not None else False
    direct_path_fallback_used = resolution is None and hit_path is not None
    return {
        "schema_version": "reverse-deepagent.workspace-resolver-metrics.v1",
        "artifact_ref_kind": _artifact_ref_kind(artifact_ref, resolution),
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolved_artifact_key": resolution.artifact_key if resolution else "",
        "canonical_path": resolution.canonical_path if resolution else "",
        "future_path": resolution.future_path if resolution else "",
        "canonical_path_authoritative": bool(resolution.canonical_path_remains_authoritative) if resolution else False,
        "candidate_path_count": len(candidate_paths),
        "checked_path_count": len(checked_paths),
        "hit_path_kind": hit_path_kind,
        "legacy_path_checked": legacy_path_checked,
        "future_path_checked": future_path_checked,
        "future_path_fallback_used": hit_path_kind == "future-foldered" and legacy_path_checked,
        "direct_path_fallback_used": direct_path_fallback_used,
        "missing": status == "missing",
        "read_only": True,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_artifact_file(
    path: Path,
    *,
    artifact_ref: str,
    artifact_root: Path,
    resolution: WorkspacePathResolution | None,
    candidate_paths: list[Path],
    checked_paths: list[str],
    max_chars: int,
) -> dict[str, Any]:
    resolver_metrics = _workspace_resolver_metrics(
        artifact_ref=artifact_ref,
        artifact_root=artifact_root,
        resolution=resolution,
        candidate_paths=candidate_paths,
        checked_paths=checked_paths,
        hit_path=path,
        status="found",
    )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {
            "status": "error",
            "artifact_ref": artifact_ref,
            "artifact_root": str(artifact_root),
            "path": str(path),
            "error": f"artifact is not valid UTF-8 text: {exc}",
            "resolution_status": "resolved" if resolution else "direct-path-fallback",
            "resolution": resolution.to_dict() if resolution else {},
            "checked_paths": checked_paths,
            "resolver_metrics": {**resolver_metrics, "missing": False},
            "side_effect_policy": _reader_side_effect_policy(),
        }
    parsed_json: Any | None = None
    parse_error = ""
    content_type = "text"
    if path.suffix.lower() == ".json" or raw_text.lstrip().startswith(("{", "[")):
        try:
            parsed_json = json.loads(raw_text)
            content_type = "json"
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            content_type = "invalid-json"
    truncated = len(raw_text) > max_chars
    return {
        "status": "found",
        "artifact_ref": artifact_ref,
        "artifact_root": str(artifact_root),
        "path": str(path),
        "content_type": content_type,
        "content": raw_text[:max_chars],
        "content_truncated": truncated,
        "content_length": len(raw_text),
        "json": parsed_json if parsed_json is not None else None,
        "json_parse_error": parse_error,
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolution": resolution.to_dict() if resolution else {},
        "checked_paths": checked_paths,
        "resolver_metrics": resolver_metrics,
        "side_effect_policy": _reader_side_effect_policy(),
    }


def _reader_side_effect_policy() -> dict[str, bool]:
    return {
        "read_only": True,
        "writes_artifacts": False,
        "moves_artifacts": False,
        "creates_directories": False,
        "enables_dual_write": False,
        "changes_canonical_path": False,
        "starts_browser": False,
        "calls_mcp": False,
    }
