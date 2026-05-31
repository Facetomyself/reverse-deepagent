from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read
from reverse_deepagent.schemas import FinalResult, RebuildResult, TaskCard


RebuildTool = Callable[..., dict[str, Any]]


def make_build_rebuild_delivery_tool(default_artifact_root: str | Path) -> RebuildTool:
    """Create a tool wrapper that generates rebuild delivery artifacts."""

    root = Path(default_artifact_root)

    def build_rebuild_delivery(
        task_card_json: str,
        final_result_json: str,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Generate rebuild-plan and delivery files from a validated final result."""

        task_card = TaskCard.model_validate_json(task_card_json)
        final_result = FinalResult.model_validate_json(final_result_json)
        target_root = Path(artifact_root) if artifact_root else root
        return write_rebuild_bundle(target_root, task_card, final_result).model_dump(mode="json")

    build_rebuild_delivery.__name__ = "build_rebuild_delivery"
    build_rebuild_delivery.__doc__ = (
        "Generate rebuild-plan.json plus sign_rebuild.py, replay_demo.py, scrapy_middleware.py, and a runnable Scrapy project. "
        "Inputs must be JSON strings generated from TaskCard and FinalResult. "
        "artifact_root is optional; when omitted, the agent default artifact root is used."
    )
    return build_rebuild_delivery



def make_review_rebuild_artifacts_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only tool for reviewing rebuild results and rebuild-plan payloads."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def review_rebuild_artifacts(
        rebuild_result_json: str | None = None,
        rebuild_plan_json: str | None = None,
        rebuild_result_artifact_ref: str | None = None,
        rebuild_plan_artifact_ref: str | None = None,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Review RebuildResult JSON without writing artifacts, running replay code, or executing delivery."""

        rebuild_payload, rebuild_artifact_read = _loads_object_or_artifact(
            rebuild_result_json,
            artifact_ref=rebuild_result_artifact_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="rebuild_result_json",
            artifact_field_name="rebuild_result_artifact_ref",
        )
        rebuild = RebuildResult.model_validate(rebuild_payload)
        explicit_plan, plan_artifact_read = _loads_optional_object_or_artifact(
            rebuild_plan_json,
            artifact_ref=rebuild_plan_artifact_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="rebuild_plan_json",
            artifact_field_name="rebuild_plan_artifact_ref",
        )
        plan = explicit_plan or rebuild.rebuild_plan or {}
        generated_files = dict(rebuild.generated_files or {})
        artifacts = [artifact.model_dump(mode="json") for artifact in rebuild.artifacts]
        review_hints = _list_of_dicts(plan.get("review_hints"))
        risk_hints = [hint for hint in review_hints if hint.get("severity") == "risk"]
        warning_hints = [hint for hint in review_hints if hint.get("severity") == "warning"]
        ready = bool(plan.get("ready"))
        runtime_assisted = plan.get("runtime_assisted") if isinstance(plan.get("runtime_assisted"), dict) else {}
        outputs = plan.get("outputs") if isinstance(plan.get("outputs"), dict) else {}

        blockers: list[str] = []
        warnings: list[str] = []
        if risk_hints:
            blockers.append("risk_review_hints_block_rebuild_delivery")
        if ready and not generated_files:
            blockers.append("ready_rebuild_has_no_generated_files")
        if ready and not artifacts:
            blockers.append("ready_rebuild_has_no_artifacts")
        if not ready:
            warnings.append("rebuild_plan_not_ready")
        if warning_hints:
            warnings.append("warning_review_hints_present")
        if ready and "scrapy_project" in outputs and "scrapy_project" not in generated_files:
            warnings.append("scrapy_project_output_declared_but_not_generated")
        if runtime_assisted and runtime_assisted.get("recommended") and ready:
            warnings.append("runtime_assisted_replay_recommended_for_ready_plan")

        status = "block" if blockers else "warn" if warnings else "pass"
        return {
            "version": "2026-05-31.rebuild-artifact-review-v1",
            "status": status,
            "blocked": bool(blockers),
            "warnings_present": bool(warnings),
            "next_action": _rebuild_next_action(status, blockers, warnings, rebuild.next_action),
            "artifact_input": {
                "rebuild_result": summarize_workspace_artifact_read(rebuild_artifact_read),
                "rebuild_plan": summarize_workspace_artifact_read(plan_artifact_read),
            },
            "summary": {
                "rebuild_status": str(rebuild.status),
                "stage": str(rebuild.stage),
                "ready": ready,
                "entrypoint": plan.get("entrypoint"),
                "candidate_id": plan.get("candidate_id"),
                "algorithm_strategy_id": (plan.get("algorithm_strategy") or {}).get("id") if isinstance(plan.get("algorithm_strategy"), dict) else None,
                "pure_extractable": bool(((plan.get("pure_extraction") or {}) if isinstance(plan.get("pure_extraction"), dict) else {}).get("pure_extractable")),
                "context_aware_extractable": bool(((plan.get("pure_extraction") or {}) if isinstance(plan.get("pure_extraction"), dict) else {}).get("context_aware_extractable")),
                "generated_file_count": len(generated_files),
                "generated_file_keys": sorted(generated_files),
                "artifact_count": len(artifacts),
                "review_hint_count": len(review_hints),
                "risk_hint_codes": [str(hint.get("code")) for hint in risk_hints if hint.get("code")],
                "warning_hint_codes": [str(hint.get("code")) for hint in warning_hints if hint.get("code")],
                "runtime_assisted_recommended": bool(runtime_assisted.get("recommended")) if runtime_assisted else False,
                "declared_outputs": sorted(str(key) for key in outputs),
            },
            "blockers": blockers,
            "warnings": warnings,
            "review_required_items": _rebuild_review_required_items(blockers, warnings, risk_hints, warning_hints),
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "artifacts_written": False,
                "replay_executed": False,
                "scrapy_executed": False,
                "delivery_executed": False,
                "external_delivery_performed": False,
                "manifest_mutated": False,
            },
        }

    review_rebuild_artifacts.__name__ = "review_rebuild_artifacts"
    return review_rebuild_artifacts


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


def _loads_optional_object_or_artifact(
    payload: str | None,
    *,
    artifact_ref: str | None,
    artifact_root: str | None,
    default_artifact_root: Path,
    field_name: str,
    artifact_field_name: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if artifact_ref:
        value, read_result = load_workspace_artifact_json_object(
            artifact_ref=artifact_ref,
            default_artifact_root=default_artifact_root,
            artifact_root=artifact_root,
            field_name=artifact_field_name,
        )
        return value, read_result
    if payload:
        return _loads_object(payload, field_name=field_name), None
    return None, None


def _loads_object(payload: str, *, field_name: str) -> dict[str, Any]:
    import json

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


def _rebuild_next_action(status: str, blockers: list[str], warnings: list[str], fallback: str) -> str:
    if "risk_review_hints_block_rebuild_delivery" in blockers:
        return "resolve_rebuild_risk_hints_before_delivery"
    if "ready_rebuild_has_no_generated_files" in blockers or "ready_rebuild_has_no_artifacts" in blockers:
        return "regenerate_rebuild_bundle_before_delivery"
    if "rebuild_plan_not_ready" in warnings:
        return "manual_port_or_expand_source_context"
    if status == "warn":
        return "inspect_rebuild_warnings_before_delivery"
    return fallback or "rebuild_review_passed"


def _rebuild_review_required_items(
    blockers: list[str],
    warnings: list[str],
    risk_hints: list[dict[str, Any]],
    warning_hints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for hint in risk_hints:
        items.append({"code": "rebuild_risk_review_hint", "hint_code": str(hint.get("code") or ""), "message": str(hint.get("message") or "")})
    for code in blockers:
        if code != "risk_review_hints_block_rebuild_delivery":
            items.append({"code": code})
    for hint in warning_hints:
        items.append({"code": "rebuild_warning_review_hint", "hint_code": str(hint.get("code") or ""), "message": str(hint.get("message") or "")})
    for code in warnings:
        if code not in {"warning_review_hints_present"}:
            items.append({"code": code})
    return items
