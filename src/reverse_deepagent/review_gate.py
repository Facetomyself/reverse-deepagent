from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from reverse_deepagent.evidence import EvidencePromotionResult
from reverse_deepagent.schemas import RebuildResult, ReviewHint, SchemaBaseModel

ReviewGateStatus = Literal["pass", "warn", "block"]


class ReviewGateResult(SchemaBaseModel):
    """Machine-readable delivery gate result derived from review_hints and evidence promotion."""

    gate_name: str = Field(default="review_hints_delivery_gate", description="Stable gate identifier.")
    status: ReviewGateStatus = Field(description="Gate outcome: pass, warn, or block.")
    blocked: bool = Field(description="Whether automated delivery / pure replay should be blocked.")
    ready: bool = Field(description="Whether the rebuild plan itself claims ready=true.")
    review_hints: list[ReviewHint] = Field(default_factory=list, description="Validated review hints consumed by the gate.")
    hint_counts: dict[str, int] = Field(default_factory=dict, description="Counts by severity.")
    blocking_hint_codes: list[str] = Field(default_factory=list, description="Risk hint codes that block automated delivery.")
    warning_hint_codes: list[str] = Field(default_factory=list, description="Warning hint codes that require manual review.")
    info_hint_codes: list[str] = Field(default_factory=list, description="Informational hint codes.")
    evidence_status: str | None = Field(default=None, description="Evidence promotion summary status, if available.")
    evidence_counts: dict[str, int] = Field(default_factory=dict, description="Evidence promotion counts used by the gate.")
    reasons: list[str] = Field(default_factory=list, description="Human-readable reasons for the gate outcome.")
    next_action: str = Field(description="Recommended action after evaluating the gate.")


def evaluate_review_gate(
    rebuild_result: RebuildResult,
    evidence_promotion: EvidencePromotionResult | None = None,
) -> ReviewGateResult:
    """Evaluate automatic delivery gate from rebuild review_hints and promoted evidence."""

    plan = rebuild_result.rebuild_plan or {}
    ready = bool(plan.get("ready"))
    hints = _coerce_review_hints(plan.get("review_hints"))
    risk_codes = [hint.code for hint in hints if hint.severity == "risk"]
    warning_codes = [hint.code for hint in hints if hint.severity == "warning"]
    info_codes = [hint.code for hint in hints if hint.severity == "info"]
    hint_counts = {
        "risk": len(risk_codes),
        "warning": len(warning_codes),
        "info": len(info_codes),
        "total": len(hints),
    }
    evidence_summary = evidence_promotion.summary if evidence_promotion is not None else {}
    evidence_counts = {
        "candidate": int(evidence_summary.get("candidate_count") or 0),
        "validated": int(evidence_summary.get("validated_count") or 0),
        "promoted": int(evidence_summary.get("promoted_count") or 0),
        "rejected": int(evidence_summary.get("rejected_count") or 0),
    }
    evidence_status = str(evidence_summary.get("status")) if evidence_summary else None

    reasons: list[str] = []
    if not ready:
        reasons.append("rebuild_plan.ready=false")
    if risk_codes:
        reasons.append("risk_review_hints_present")
    if evidence_promotion is not None:
        if evidence_counts["validated"] <= 0:
            reasons.append("validated_evidence_missing")
        if evidence_counts["promoted"] <= 0:
            reasons.append("promoted_evidence_missing")
        if evidence_counts["rejected"] > 0:
            reasons.append("rejected_evidence_present")
    if warning_codes:
        reasons.append("warning_review_hints_present")

    blocked = bool(risk_codes) or not ready
    if evidence_promotion is not None and evidence_counts["validated"] <= 0:
        blocked = True
    if evidence_promotion is not None and evidence_counts["promoted"] <= 0 and ready:
        # Ready delivery without promoted evidence is contradictory enough to block automation.
        blocked = True
    if blocked:
        status: ReviewGateStatus = "block"
        next_action = "manual_review_or_expand_evidence"
    elif warning_codes or (evidence_promotion is not None and evidence_counts["rejected"] > 0):
        status = "warn"
        next_action = "manual_review_before_delivery"
    else:
        status = "pass"
        reasons.append("ready_without_blocking_review_hints")
        next_action = "delivery_allowed"

    return ReviewGateResult(
        status=status,
        blocked=blocked,
        ready=ready,
        review_hints=hints,
        hint_counts=hint_counts,
        blocking_hint_codes=risk_codes,
        warning_hint_codes=warning_codes,
        info_hint_codes=info_codes,
        evidence_status=evidence_status,
        evidence_counts=evidence_counts,
        reasons=_dedupe(reasons),
        next_action=next_action,
    )


def review_gate_workspace_payload(result: ReviewGateResult) -> dict[str, Any]:
    """Return the standard workspace JSON payload for review gate output."""

    return result.model_dump(mode="json")


def _coerce_review_hints(payload: Any) -> list[ReviewHint]:
    if not isinstance(payload, list):
        return []
    hints: list[ReviewHint] = []
    for item in payload:
        try:
            hints.append(item if isinstance(item, ReviewHint) else ReviewHint.model_validate(item))
        except Exception:
            hints.append(
                ReviewHint(
                    severity="risk",
                    category="review_hints",
                    code="invalid_review_hint",
                    message="Invalid review hint payload encountered; block automated delivery until the plan is regenerated.",
                    evidence=[repr(item)],
                )
            )
    return hints


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


__all__ = ["ReviewGateResult", "evaluate_review_gate", "review_gate_workspace_payload"]
