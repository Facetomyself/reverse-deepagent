from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reverse_deepagent.evidence import EvidencePromotionResult
from reverse_deepagent.review_approval import ReviewApprovalConfig, ReviewApprovalLedgerWriter
from reverse_deepagent.review_gate import evaluate_review_gate
from reverse_deepagent.schemas import RebuildResult
from reverse_deepagent.tools.artifact_tools import load_workspace_artifact_json_object, summarize_workspace_artifact_read


def make_evaluate_review_gate_tool(default_artifact_root: str | Path | None = None):
    """Create a read-only tool for evaluating delivery review gates."""

    root = Path(default_artifact_root) if default_artifact_root is not None else Path("artifacts")

    def evaluate_delivery_review_gate(
        rebuild_result_json: str | None = None,
        evidence_promotion_json: str | None = None,
        rebuild_result_artifact_ref: str | None = None,
        evidence_promotion_artifact_ref: str | None = None,
        artifact_root: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate review gate from RebuildResult JSON and optional EvidencePromotionResult JSON."""

        rebuild_payload, rebuild_artifact_read = _loads_object_or_artifact(
            rebuild_result_json,
            artifact_ref=rebuild_result_artifact_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="rebuild_result_json",
            artifact_field_name="rebuild_result_artifact_ref",
        )
        evidence_payload, evidence_artifact_read = _loads_optional_object_or_artifact(
            evidence_promotion_json,
            artifact_ref=evidence_promotion_artifact_ref,
            artifact_root=artifact_root,
            default_artifact_root=root,
            field_name="evidence_promotion_json",
            artifact_field_name="evidence_promotion_artifact_ref",
        )
        rebuild = RebuildResult.model_validate(rebuild_payload)
        evidence = EvidencePromotionResult.model_validate(evidence_payload) if evidence_payload is not None else None
        gate = evaluate_review_gate(rebuild, evidence).model_dump(mode="json")
        gate["artifact_input"] = {
            "rebuild_result": summarize_workspace_artifact_read(rebuild_artifact_read),
            "evidence_promotion": summarize_workspace_artifact_read(evidence_artifact_read),
        }
        gate["side_effect_policy"] = {
            "read_only": True,
            "files_mutated": False,
            "artifacts_written": False,
            "delivery_executed": False,
            "external_delivery_performed": False,
            "review_decision_recorded": False,
        }
        return gate

    evaluate_delivery_review_gate.__name__ = "evaluate_delivery_review_gate"
    return evaluate_delivery_review_gate


def make_record_review_approval_tool(default_review_root: str | Path):
    """Create an explicit review approval ledger tool.

    The tool writes only review approval audit artifacts when explicitly run in
    apply mode with approval recording enabled. It never executes delivery,
    rollback, external publishing, or manifest mutation.
    """

    default_root = Path(default_review_root)

    def record_review_approval(
        subject_id: str,
        action: str,
        decision: str = "approved",
        reviewer: str | None = None,
        reason: str | None = None,
        mode: str = "dry-run",
        approve_decision_record: bool = False,
        subject_digest_sha256: str | None = None,
        expected_subject_digest_sha256: str | None = None,
        review_root: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Record a manual review decision into an append-only approval ledger."""

        metadata = _loads_optional_object(metadata_json, field_name="metadata_json")
        root = Path(review_root) if review_root else default_root
        config = ReviewApprovalConfig(
            review_root=root,
            subject_id=subject_id,
            action=action,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
            mode=mode,
            approve_decision_record=approve_decision_record,
            subject_digest_sha256=subject_digest_sha256,
            expected_subject_digest_sha256=expected_subject_digest_sha256,
            metadata={**metadata, "tool": "record_review_approval"},
        )
        return ReviewApprovalLedgerWriter(config).execute().to_dict()

    record_review_approval.__name__ = "record_review_approval"
    return record_review_approval


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
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON object text: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must decode to a JSON object")
    return value


def _loads_optional_object(payload: str | None, *, field_name: str) -> dict[str, Any]:
    if not payload:
        return {}
    return _loads_object(payload, field_name=field_name)
