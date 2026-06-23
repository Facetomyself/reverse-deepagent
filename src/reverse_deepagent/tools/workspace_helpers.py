from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from reverse_deepagent.tools.workspace_artifact_reader import (
    _artifact_ref_to_filesystem_path,
    load_workspace_artifact_json_object,
    summarize_workspace_artifact_read,
)
from reverse_deepagent.workspace_contract import default_workspace_artifact_routes


_LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"workspace", "runtime-context", "source", "network", "evidence"})
_MEDIUM_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"triage", "audit"})


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _parse_json_object(payload_json: str | None, *, field_name: str) -> tuple[dict[str, Any] | None, str]:
    if not payload_json:
        return None, ""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return None, f"{field_name} is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{field_name} must decode to an object"
    return payload, ""


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


def _file_digest_stat(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _missing_file_stat(path)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"path": str(path), "exists": True, "size_bytes": size, "sha256": digest.hexdigest()}


def _missing_file_stat(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": False, "size_bytes": 0, "sha256": ""}


def _compact_observed_write_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    return {
        "artifact_key": record.get("artifact_key") or "",
        "canonical_path": record.get("canonical_path") or record.get("legacy_path") or "",
        "future_path": record.get("future_path") or "",
        "write_paths": list(record.get("write_paths") or []),
        "migration_status": record.get("migration_status") or "",
        "canonical_path_remains_authoritative": bool(record.get("canonical_path_remains_authoritative", True)),
    }


def _compact_pilot_plan_summary(pilot_plan: dict[str, Any]) -> dict[str, Any]:
    summary = pilot_plan.get("summary") if isinstance(pilot_plan.get("summary"), dict) else {}
    return {
        "schema_version": pilot_plan.get("schema_version") or "",
        "status": pilot_plan.get("status") or "",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "explicit_selection": bool(summary.get("explicit_selection")),
        "readiness_limited_dual_write_status": summary.get("readiness_limited_dual_write_status") or "",
        "legacy_canonical_path_remains_authoritative": bool((pilot_plan.get("selection_policy") or {}).get("legacy_canonical_path_remains_authoritative", True)) if isinstance(pilot_plan.get("selection_policy"), dict) else True,
    }


def _workspace_pilot_result_artifact_metadata(artifact_root: Path, *, written: bool) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_dual_write_pilot_result",
        "legacy_path": "workspace/workspace-dual-write-pilot-result.json",
        "future_path": "/workspace/delivery/workspace-dual-write-pilot-result.json",
        "path": str(artifact_root / "workspace" / "workspace-dual-write-pilot-result.json"),
        "written": written,
        "canonical_path_remains_authoritative": True,
    }


def _dual_write_pilot_result_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_dual_write_plan_unavailable_or_malformed" in blockers or "workspace_dual_write_plan_not_observed" in blockers:
        actions.append("run_pipeline_with_enable_workspace_dual_write_and_capture_workspace_dual_write_plan")
    if "pilot_plan_json_malformed" in blockers:
        actions.append("fix_pilot_plan_json_or_omit_it_to_use_default_plan")
    if "candidate_legacy_files_missing" in blockers or "candidate_future_files_missing" in blockers:
        actions.append("inspect_dual_write_output_paths_and_rerun_limited_pilot")
    if "candidate_digest_mismatch" in blockers:
        actions.append("compare_legacy_and_future_artifacts_before_any_migration")
    if "observed_dual_write_records_outside_pilot_plan" in warnings:
        actions.append("review_out_of_scope_observed_dual_writes_before_expanding_pilot")
    if "high_risk_artifacts_observed_in_dual_write_output" in warnings:
        actions.append("split_high_risk_artifacts_into_separate_manual_review")
    if status == "verified":
        actions.append("record_verified_pilot_result_then_review_next_low_risk_dual_write_scope")
    if not actions:
        actions.append("review_pilot_result_before_foldered_canonical_migration")
    return actions


def _workspace_dual_write_workflow_status(
    readiness_report: dict[str, Any],
    pilot_plan: dict[str, Any],
    pilot_result: dict[str, Any],
) -> str:
    if _readiness_limited_dual_write_status(readiness_report) != "ready_for_review":
        return "blocked"
    if pilot_plan.get("status") == "blocked":
        return "blocked"
    result_status = str(pilot_result.get("status") or "unknown")
    if result_status == "verified":
        return "verified"
    if result_status == "partial":
        return "partial"
    if result_status == "blocked":
        return "blocked"
    if result_status == "not_run":
        return "ready_for_review"
    return "ready_for_review"


def _workspace_dual_write_workflow_blocking_reasons(
    readiness_report: dict[str, Any],
    pilot_plan: dict[str, Any],
    pilot_result: dict[str, Any],
    status: str,
) -> list[str]:
    reasons: list[str] = []
    if _readiness_limited_dual_write_status(readiness_report) != "ready_for_review":
        reasons.append("workspace_migration_readiness_not_ready_for_dual_write_pilot")
    for reason in pilot_plan.get("blocking_reasons") or []:
        reasons.append(f"pilot_plan:{reason}")
    if status in {"blocked", "partial"}:
        for reason in pilot_result.get("blocking_reasons") or []:
            reasons.append(f"pilot_result:{reason}")
    return list(dict.fromkeys(reasons))


def _workspace_dual_write_workflow_warnings(pilot_result: dict[str, Any]) -> list[str]:
    return [f"pilot_result:{item}" for item in pilot_result.get("warnings") or []]


def _workspace_dual_write_workflow_next_actions(status: str, pilot_result: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if status == "ready_for_review":
        actions.append("review_pilot_plan_then_run_explicit_scoped_dual_write_pipeline")
    if status in {"verified", "partial"}:
        actions.append("review_pilot_result_before_expanding_dual_write_scope")
    if status == "verified":
        actions.append("consider_next_low_risk_artifact_scope_after_review")
    if status == "blocked":
        actions.append("resolve_workflow_blockers_before_running_dual_write_pilot")
    for action in pilot_result.get("recommended_next_actions") or []:
        if action not in actions:
            actions.append(action)
    return actions


def _workspace_dual_write_review_workflow(
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
                "step": "resolve_workflow_blockers",
                "description": "Resolve readiness, pilot plan, or verification blockers before running a scoped dual-write pipeline.",
                "requires_review": True,
                "runs_inside_this_tool": False,
            }
        ]
    else:
        commands = [
            {
                "step": "run_explicit_scoped_dual_write_pipeline",
                "description": "Run the normal pipeline separately with reviewed low-risk artifact keys only.",
                "flags": [
                    "--enable-workspace-dual-write",
                    "--workspace-dual-write-artifact-keys",
                    key_arg,
                ],
                "requires_review": True,
                "runs_inside_this_tool": False,
            },
            {
                "step": "verify_observed_dual_write_output",
                "description": "Call this workflow again after the pipeline writes workspace/workspace-dual-write-plan.json, or pass workspace_dual_write_plan_json directly.",
                "tool": "review_workspace_dual_write_pilot_workflow",
                "suggested_arguments": {
                    "artifact_keys_json": json.dumps(candidate_keys),
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": False,
                },
                "requires_review": True,
            },
            {
                "step": "record_verified_pilot_result",
                "description": "Only after reviewing the verification payload, call with write_result=true to write the audit artifact.",
                "tool": "review_workspace_dual_write_pilot_workflow",
                "suggested_arguments": {
                    "artifact_keys_json": json.dumps(candidate_keys),
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


def _planned_dual_write_candidates(pilot_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in pilot_plan.get("candidate_artifacts") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("artifact_key") or "")
        if not key:
            continue
        legacy_path = str(item.get("legacy_path") or item.get("canonical_path") or "")
        future_path = str(item.get("future_path") or "")
        plan = item.get("dual_write_plan") if isinstance(item.get("dual_write_plan"), dict) else {}
        if not legacy_path:
            legacy_path = str(plan.get("canonical_path") or "")
        if not future_path:
            future_path = str(plan.get("future_path") or "")
        candidates.append({
            "artifact_key": key,
            "legacy_path": legacy_path,
            "future_path": future_path,
            "risk": item.get("risk") if isinstance(item.get("risk"), dict) else {},
        })
    return candidates


def _observed_dual_write_records(observed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        observed_plan.get("write_records")
        or observed_plan.get("workspace_write_records")
        or observed_plan.get("records")
        or observed_plan.get("artifacts")
        or []
    )
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _load_observed_dual_write_plan(
    *,
    default_artifact_root: Path,
    workspace_dual_write_plan_json: str | None,
    workspace_dual_write_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    if workspace_dual_write_plan_json:
        payload, error = _parse_json_object(workspace_dual_write_plan_json, field_name="workspace_dual_write_plan_json")
        return payload, error, {"kind": "json", "error": error}
    if not workspace_dual_write_plan_artifact_ref:
        return None, "workspace_dual_write_plan_artifact_ref is empty", {"kind": "none", "error": "workspace_dual_write_plan_artifact_ref is empty"}
    try:
        payload, read_diagnostics = load_workspace_artifact_json_object(
            artifact_ref=workspace_dual_write_plan_artifact_ref,
            default_artifact_root=default_artifact_root,
            field_name="workspace_dual_write_plan_artifact_ref",
        )
    except ValueError as exc:
        return None, str(exc), {
            "kind": "artifact_ref",
            "artifact_ref": workspace_dual_write_plan_artifact_ref,
            "status": "error",
            "error": str(exc),
        }
    return payload, "", {
        "kind": "artifact_ref",
        "artifact_ref": workspace_dual_write_plan_artifact_ref,
        "status": "found",
        "read": summarize_workspace_artifact_read(read_diagnostics),
    }


def _dual_write_candidate_result(artifact_root: Path, candidate: dict[str, Any], observed_record: dict[str, Any] | None) -> dict[str, Any]:
    legacy_path = str(candidate.get("legacy_path") or "")
    future_path = str(candidate.get("future_path") or "")
    legacy_file = _artifact_ref_to_filesystem_path(artifact_root, legacy_path) if legacy_path else artifact_root / ""
    future_file = _artifact_ref_to_filesystem_path(artifact_root, future_path) if future_path else artifact_root / ""
    legacy_stat = _file_digest_stat(legacy_file) if legacy_path else _missing_file_stat(legacy_file)
    future_stat = _file_digest_stat(future_file) if future_path else _missing_file_stat(future_file)
    observed = observed_record is not None
    digest_match = bool(legacy_stat.get("exists") and future_stat.get("exists") and legacy_stat.get("sha256") == future_stat.get("sha256"))
    if not observed:
        status = "not_observed"
    elif not legacy_stat["exists"]:
        status = "missing_legacy"
    elif not future_stat["exists"]:
        status = "missing_future"
    elif not digest_match:
        status = "digest_mismatch"
    else:
        status = "verified_dual_written"
    return {
        "artifact_key": candidate["artifact_key"],
        "status": status,
        "observed_in_workspace_dual_write_plan": observed,
        "legacy_path": legacy_path,
        "future_path": future_path,
        "legacy_file": legacy_stat,
        "future_file": future_stat,
        "digest_match": digest_match,
        "canonical_path_remains_authoritative": True,
        "observed_record": _compact_observed_write_record(observed_record),
        "risk": candidate.get("risk") or {},
    }


def _compact_workspace_consumer_score(readiness_score: dict[str, Any]) -> dict[str, Any]:
    summary = readiness_score.get("summary") if isinstance(readiness_score.get("summary"), dict) else {}
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    pilot = readiness_score.get("pilot_evidence") if isinstance(readiness_score.get("pilot_evidence"), dict) else {}
    return {
        "schema_version": readiness_score.get("schema_version") or "",
        "status": readiness_score.get("status") or "blocked",
        "overall_score": summary.get("overall_score"),
        "overall_label": summary.get("overall_label"),
        "limited_dual_write_expansion_review_allowed": bool(readiness.get("limited_dual_write_expansion_review_allowed")),
        "foldered_canonical_migration_allowed": bool(readiness.get("foldered_canonical_migration_allowed")),
        "pilot_result_status": pilot.get("status") or "missing",
        "pilot_evidence_score": float(pilot.get("score") or 0.0),
        "blocking_reasons": readiness_score.get("blocking_reasons") if isinstance(readiness_score.get("blocking_reasons"), list) else [],
        "warnings": readiness_score.get("warnings") if isinstance(readiness_score.get("warnings"), list) else [],
    }
