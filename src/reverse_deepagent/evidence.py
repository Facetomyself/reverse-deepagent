from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import Field

from reverse_deepagent.schemas import ArtifactRef, ConfidenceLevel, EvidenceItem, EvidenceKind, SchemaBaseModel

PromotionStatus = Literal["candidate", "validated", "promoted", "rejected"]


class EvidencePromotionRecord(SchemaBaseModel):
    """Machine-readable evidence promotion record for one normalized evidence item."""

    evidence_id: str = Field(description="Stable id derived from evidence source/kind/anchor/summary.")
    status: PromotionStatus = Field(description="Promotion status for the evidence item.")
    source: str | None = Field(default=None, description="Original EvidenceItem.source.")
    anchor: str | None = Field(default=None, description="Original EvidenceItem.anchor.")
    kind: EvidenceKind = Field(description="Original EvidenceItem.kind.")
    summary: str = Field(description="Original evidence summary.")
    confidence: ConfidenceLevel | None = Field(default=None, description="Original evidence confidence.")
    score: float = Field(ge=0.0, le=1.0, description="Normalized promotion score.")
    reasons: list[str] = Field(default_factory=list, description="Positive signals that justify the status.")
    blockers: list[str] = Field(default_factory=list, description="Missing or weak signals that block stronger promotion.")
    artifact_paths: list[str] = Field(default_factory=list, description="Related artifact paths when discoverable.")
    details_digest: str = Field(description="SHA-256 digest of the JSON-serializable evidence details.")


class EvidencePromotionResult(SchemaBaseModel):
    """Promotion index for candidate, validated, and final promoted evidence."""

    candidates: list[EvidencePromotionRecord] = Field(default_factory=list, description="All normalized evidence candidates.")
    validated: list[EvidencePromotionRecord] = Field(default_factory=list, description="Evidence that passed generic validation gates.")
    promoted: list[EvidencePromotionRecord] = Field(default_factory=list, description="Evidence that should be highlighted in final reasoning/review.")
    rejected: list[EvidencePromotionRecord] = Field(default_factory=list, description="Evidence rejected or blocked by generic gates.")
    summary: dict[str, Any] = Field(default_factory=dict, description="Aggregate counts and review-facing status.")


def promote_evidence(
    evidence: list[EvidenceItem],
    artifacts: list[ArtifactRef] | None = None,
) -> EvidencePromotionResult:
    """Promote normalized evidence into candidate / validated / promoted buckets.

    This function is intentionally platform-neutral. It does not assume Web-only
    request/script semantics, but it recognizes stable generic signals such as
    confidence, source/context presence, runtime validation status, and replay
    readiness when those signals are present in details.
    """

    related_artifacts = artifacts or []
    candidates: list[EvidencePromotionRecord] = []
    validated: list[EvidencePromotionRecord] = []
    promoted: list[EvidencePromotionRecord] = []
    rejected: list[EvidencePromotionRecord] = []
    review_required_items: list[dict[str, Any]] = []

    for index, item in enumerate(evidence):
        review_required_items.extend(_review_required_items(item))
        candidate = _build_record(index, item, related_artifacts)
        candidates.append(candidate)
        validation = _with_status(candidate, *_decide_validation(candidate, item))
        if validation.status == "rejected":
            rejected.append(validation)
            continue
        if validation.status != "validated":
            continue
        validated.append(validation)
        final_status, final_score, final_reasons, final_blockers = _decide_promotion(validation, item)
        promoted_record = _with_status(validation, final_status, final_score, final_reasons, final_blockers)
        if promoted_record.status == "promoted":
            promoted.append(promoted_record)

    summary = {
        "candidate_count": len(candidates),
        "validated_count": len(validated),
        "promoted_count": len(promoted),
        "rejected_count": len(rejected),
        "status": "ready" if promoted else "partial" if validated else "empty" if not candidates else "blocked",
        "promoted_evidence_ids": [item.evidence_id for item in promoted],
        "validated_evidence_ids": [item.evidence_id for item in validated],
        "rejected_evidence_ids": [item.evidence_id for item in rejected],
        "review_required_count": len(review_required_items),
        "review_required_codes": sorted({str(item.get("code")) for item in review_required_items if item.get("code")}),
        "review_required_items": review_required_items,
    }
    return EvidencePromotionResult(
        candidates=candidates,
        validated=validated,
        promoted=promoted,
        rejected=rejected,
        summary=summary,
    )


def promotion_workspace_payloads(result: EvidencePromotionResult) -> dict[str, Any]:
    """Return standard workspace JSON payloads for evidence promotion."""

    return {
        "evidence-candidates.json": {
            "items": [item.model_dump(mode="json") for item in result.candidates],
            "summary": result.summary,
        },
        "evidence-validated.json": {
            "items": [item.model_dump(mode="json") for item in result.validated],
            "summary": result.summary,
        },
        "evidence-promotion.json": result.model_dump(mode="json"),
    }


def _build_record(index: int, item: EvidenceItem, artifacts: list[ArtifactRef]) -> EvidencePromotionRecord:
    details_digest = _stable_digest(item.details)
    evidence_id = _evidence_id(index, item, details_digest)
    base_score, reasons, blockers = _base_score(item)
    return EvidencePromotionRecord(
        evidence_id=evidence_id,
        status="candidate",
        source=item.source,
        anchor=item.anchor,
        kind=item.kind,
        summary=item.summary,
        confidence=item.confidence,
        score=base_score,
        reasons=reasons,
        blockers=blockers,
        artifact_paths=_related_artifact_paths(item, artifacts),
        details_digest=details_digest,
    )


def _base_score(item: EvidenceItem) -> tuple[float, list[str], list[str]]:
    reasons: list[str] = []
    blockers: list[str] = []
    score = 0.2
    if item.confidence == ConfidenceLevel.HIGH:
        score += 0.35
        reasons.append("confidence=high")
    elif item.confidence == ConfidenceLevel.MEDIUM:
        score += 0.2
        reasons.append("confidence=medium")
    elif item.confidence == ConfidenceLevel.LOW:
        blockers.append("confidence=low")
    else:
        blockers.append("confidence=missing")

    if item.source:
        score += 0.1
        reasons.append(f"source={item.source}")
    else:
        blockers.append("source=missing")
    if item.anchor:
        score += 0.1
        reasons.append("anchor=present")
    if item.details:
        score += 0.1
        reasons.append("details=present")
    else:
        blockers.append("details=empty")
    if item.kind in {EvidenceKind.DYNAMIC, EvidenceKind.CALLSTACK, EvidenceKind.HOOK, EvidenceKind.REQUEST, EvidenceKind.STATIC, EvidenceKind.STORAGE}:
        score += 0.1
        reasons.append(f"kind={item.kind.value}")
    return min(score, 1.0), reasons, blockers


def _decide_validation(record: EvidencePromotionRecord, item: EvidenceItem) -> tuple[PromotionStatus, float, list[str], list[str]]:
    reasons = list(record.reasons)
    blockers = list(record.blockers)
    score = record.score
    details = item.details

    count = _coerce_int(details.get("count"))
    if count is not None:
        if count > 0:
            score += 0.08
            reasons.append(f"count={count}")
        else:
            blockers.append("count=0")

    if _has_non_empty_sample(details):
        score += 0.08
        reasons.append("sample=present")

    validation_signals = _validation_signals(details)
    if validation_signals:
        score += 0.15
        reasons.extend(validation_signals)

    failure_signals = _failure_signals(details)
    if failure_signals:
        blockers.extend(failure_signals)
        score -= 0.2

    score = max(0.0, min(score, 1.0))
    if score >= 0.55 and "confidence=low" not in blockers and not failure_signals:
        return "validated", score, reasons, blockers
    if score < 0.25 or failure_signals:
        return "rejected", score, reasons, blockers
    blockers.append("generic_validation_threshold_not_met")
    return "candidate", score, reasons, blockers


def _decide_promotion(record: EvidencePromotionRecord, item: EvidenceItem) -> tuple[PromotionStatus, float, list[str], list[str]]:
    reasons = list(record.reasons)
    blockers = list(record.blockers)
    score = record.score
    details = item.details
    source = item.source or ""

    important_sources = {
        "get_request_initiator",
        "get_script_source",
        "runtime_context",
        "runtime_context_diff",
        "function_candidate_card",
        "function_validation_result",
        "function_validation_summary",
        "platform_tool_probe",
        "runtime_export_bundle",
    }
    if source in important_sources:
        score += 0.1
        reasons.append("source=promotion_relevant")
    if source == "function_validation_summary" and details.get("replay_ready"):
        score += 0.2
        reasons.append("replay_ready=true")
    if source == "function_validation_result" and _any_validation_success(details):
        score += 0.2
        reasons.append("validation_status=success")
    if item.confidence == ConfidenceLevel.HIGH:
        score += 0.05
    score = min(score, 1.0)

    if record.status == "validated" and score >= 0.7:
        return "promoted", score, reasons, blockers
    blockers.append("promotion_threshold_not_met")
    return record.status, score, reasons, blockers


def _review_required_items(item: EvidenceItem) -> list[dict[str, Any]]:
    """Extract evidence-level manual review requirements from structured details."""

    if item.source != "flow_timeline":
        return []
    proposals = item.details.get("stitch_proposals")
    if not isinstance(proposals, list):
        return []
    required: list[dict[str, Any]] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        raw_decision = proposal.get("review_decision")
        decision = raw_decision if isinstance(raw_decision, dict) else {}
        review_required = bool(decision.get("review_required"))
        approved = bool(decision.get("approved"))
        status = str(decision.get("status") or "")
        if not review_required and status != "pending_review":
            continue
        if approved and status in {"approved", "passed"}:
            continue
        required.append(
            {
                "code": "flow_timeline_stitch_proposal_pending_review",
                "source": item.source,
                "proposal_id": proposal.get("proposal_id"),
                "candidate_id": proposal.get("candidate_id"),
                "group_id": proposal.get("group_id"),
                "strategy": proposal.get("strategy"),
                "scope": proposal.get("scope"),
                "review_status": status or "pending_review",
                "blocking_conditions": _blocking_conditions(proposal),
            }
        )
    return required


def _blocking_conditions(proposal: dict[str, Any]) -> list[Any]:
    blocking_conditions = proposal.get("blocking_conditions")
    if not isinstance(blocking_conditions, list):
        return []
    return list(blocking_conditions)


def _with_status(
    record: EvidencePromotionRecord,
    status: PromotionStatus,
    score: float,
    reasons: list[str],
    blockers: list[str],
) -> EvidencePromotionRecord:
    return record.model_copy(
        update={
            "status": status,
            "score": round(max(0.0, min(score, 1.0)), 4),
            "reasons": _dedupe(reasons),
            "blockers": _dedupe(blockers),
        }
    )


def _validation_signals(details: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if details.get("captured_requirements"):
        signals.append("captured_requirements=present")
    if details.get("stable_keys"):
        signals.append("stable_keys=present")
    if details.get("available") is True:
        signals.append("available=true")
    if details.get("replay_ready") is True:
        signals.append("replay_ready=true")
    if _any_validation_success(details):
        signals.append("validation_status=success")
    return signals


def _failure_signals(details: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if details.get("available") is False:
        signals.append("available=false")
    if details.get("ok") is False and details.get("unsupported") is True:
        signals.append("unsupported=true")
    if details.get("status") == "failed":
        signals.append("status=failed")
    return signals


def _any_validation_success(details: dict[str, Any]) -> bool:
    validations = details.get("validations")
    if not isinstance(validations, list):
        return False
    return any(isinstance(item, dict) and item.get("validation_status") == "success" for item in validations)


def _has_non_empty_sample(details: dict[str, Any]) -> bool:
    sample = details.get("sample")
    return isinstance(sample, list) and len(sample) > 0


def _related_artifact_paths(item: EvidenceItem, artifacts: list[ArtifactRef]) -> list[str]:
    source = item.source or ""
    source_tokens = _source_artifact_tokens(source)
    paths: list[str] = []
    for artifact in artifacts:
        path = artifact.path
        normalized = path.replace("-", "_").lower()
        if any(token in normalized for token in source_tokens):
            paths.append(path)
    return sorted(set(paths))


def _source_artifact_tokens(source: str) -> list[str]:
    mapping = {
        "network_request": ["network_requests"],
        "search_in_sources": ["source_hits"],
        "get_request_initiator": ["request_initiators"],
        "get_script_source": ["source_contexts"],
        "runtime_context": ["runtime_context"],
        "runtime_context_diff": ["runtime_context_diff"],
        "function_candidate_card": ["function_candidates"],
        "function_validation_result": ["function_validations"],
        "function_validation_summary": ["function_validation_summary"],
        "platform_tool_probe": ["platform_tool_probe", "tool_probe"],
    }
    return mapping.get(source, [source.replace("-", "_").lower()] if source else [])


def _evidence_id(index: int, item: EvidenceItem, details_digest: str) -> str:
    raw = "|".join([
        str(index),
        item.kind.value,
        item.source or "",
        item.anchor or "",
        item.summary,
        details_digest[:16],
    ])
    return "ev_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]  # noqa: S324 - stable non-security id.


def _stable_digest(payload: dict[str, Any]) -> str:
    import json

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


__all__ = [
    "EvidencePromotionRecord",
    "EvidencePromotionResult",
    "promote_evidence",
    "promotion_workspace_payloads",
]
