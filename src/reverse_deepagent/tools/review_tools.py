from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reverse_deepagent.evidence import EvidencePromotionResult
from reverse_deepagent.review_approval import ReviewApprovalConfig, ReviewApprovalLedgerWriter
from reverse_deepagent.review_gate import evaluate_review_gate
from reverse_deepagent.schemas import RebuildResult


def make_evaluate_review_gate_tool():
    """Create a read-only tool for evaluating delivery review gates."""

    def evaluate_delivery_review_gate(
        rebuild_result_json: str,
        evidence_promotion_json: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate review gate from RebuildResult JSON and optional EvidencePromotionResult JSON."""

        rebuild_payload = _loads_object(rebuild_result_json, field_name="rebuild_result_json")
        evidence_payload = _loads_object(evidence_promotion_json, field_name="evidence_promotion_json") if evidence_promotion_json else None
        rebuild = RebuildResult.model_validate(rebuild_payload)
        evidence = EvidencePromotionResult.model_validate(evidence_payload) if evidence_payload is not None else None
        gate = evaluate_review_gate(rebuild, evidence).model_dump(mode="json")
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
