from __future__ import annotations

import json
from typing import Any

from reverse_deepagent.evidence import EvidencePromotionResult
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


def _loads_object(payload: str, *, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} must be valid JSON object text: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must decode to a JSON object")
    return value
