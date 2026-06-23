from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class StrategyEvidenceScore:
    """Provider-neutral review score for strategy / rebuild evidence.

    This score is deliberately advisory.  It does not decide rebuild readiness,
    does not collect browser evidence, does not execute replay, and does not
    relax review gates.  Callers can attach it to strategy / rebuild payloads so
    review, rebuild, and future subagents share one compact scoring surface.
    """

    score: float
    label: str
    recommended_next_action: str
    components: Mapping[str, Any]
    signals: Sequence[str]
    blockers: Sequence[str]
    side_effect_policy: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "label": self.label,
            "recommended_next_action": self.recommended_next_action,
            "components": dict(self.components),
            "signals": list(self.signals),
            "blockers": list(self.blockers),
            "side_effect_policy": dict(self.side_effect_policy),
        }


def build_strategy_evidence_score(
    strategy: Mapping[str, Any],
    *,
    extraction: Mapping[str, Any] | None = None,
    runtime_context_diff: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
    validation_ready: bool | None = None,
    replay_url: str | None = None,
    ready: bool | None = None,
) -> dict[str, Any]:
    """Build a conservative evidence score from existing strategy / rebuild evidence.

    The output is JSON-serializable and stable enough for plans, review hints, and
    subagents.  It intentionally uses only already-collected payloads.
    """

    extraction = extraction or {}
    runtime_context_diff = runtime_context_diff or {}
    validation = validation or {}
    score = _base_strategy_score(strategy)
    signals: list[str] = []
    blockers: list[str] = []
    components: dict[str, Any] = {
        "strategy": _strategy_component(strategy),
        "validation": _validation_component(validation, validation_ready),
        "runtime_context": _runtime_context_component(runtime_context_diff, extraction),
        "protected_flow": _protected_flow_component(strategy),
        "rebuild": _rebuild_component(extraction, ready=ready, replay_url=replay_url),
    }

    if strategy.get("supported"):
        score += 0.08
        signals.append("strategy_supported")
    else:
        score -= 0.22
        blockers.append("strategy_not_supported")

    if validation_ready is True:
        score += 0.12
        signals.append("validation_ready")
    elif validation_ready is False or validation:
        score -= 0.16
        blockers.append("validation_not_ready")

    if replay_url:
        score += 0.06
        signals.append("replay_url_available")
    else:
        score -= 0.08
        blockers.append("missing_replay_url")

    if extraction.get("pure_extractable"):
        score += 0.12
        signals.append("pure_extractable")
    elif extraction.get("context_aware_extractable"):
        score -= 0.04
        signals.append("context_aware_extractable")
    elif extraction:
        score -= 0.16
        blockers.append("manual_port_required")

    if extraction.get("runtime_context_binding_required"):
        signals.append("runtime_context_binding_required")
    missing_bindings = [str(item) for item in extraction.get("missing_runtime_context_bindings", []) if item]
    if missing_bindings:
        score -= min(0.18, 0.06 * len(missing_bindings))
        blockers.append("missing_runtime_context_binding")

    if _is_triage_strategy(strategy):
        score -= 0.2
        blockers.append("protected_flow_triage_required")
        signals.extend(_protected_flow_signals(strategy))

    runtime_penalty, runtime_signals, runtime_blockers = _runtime_context_score_adjustments(runtime_context_diff)
    score += runtime_penalty
    signals.extend(runtime_signals)
    blockers.extend(runtime_blockers)

    if ready is True:
        score += 0.08
        signals.append("rebuild_ready")
    elif ready is False:
        score -= 0.08
        blockers.append("rebuild_not_ready")

    normalized_score = round(max(0.0, min(1.0, score)), 2)
    unique_signals = _unique(signals)
    unique_blockers = _unique(blockers)
    label = _score_label(normalized_score, unique_blockers)
    recommended_next_action = _recommended_next_action(label, unique_blockers, unique_signals)
    components["score_inputs"] = {
        "base_score": _base_strategy_score(strategy),
        "final_score": normalized_score,
        "label": label,
        "ready_input": ready,
    }
    return StrategyEvidenceScore(
        score=normalized_score,
        label=label,
        recommended_next_action=recommended_next_action,
        components=components,
        signals=unique_signals,
        blockers=unique_blockers,
        side_effect_policy={
            "score_only": True,
            "collects_runtime_context": False,
            "executes_replay": False,
            "starts_browser": False,
            "calls_mcp": False,
            "changes_ready_calculation": False,
            "mobile_full_runtime_chain": False,
        },
    ).to_dict()


def _base_strategy_score(strategy: Mapping[str, Any]) -> float:
    confidence_score = strategy.get("confidence_score")
    if isinstance(confidence_score, Mapping):
        raw_score = confidence_score.get("score")
        if isinstance(raw_score, int | float):
            return float(raw_score)
    confidence = str(strategy.get("confidence") or "low").lower()
    return {"high": 0.9, "medium": 0.65, "low": 0.25}.get(confidence, 0.25)


def _strategy_component(strategy: Mapping[str, Any]) -> dict[str, Any]:
    confidence_score = strategy.get("confidence_score") if isinstance(strategy.get("confidence_score"), Mapping) else {}
    return {
        "id": str(strategy.get("id") or "unknown"),
        "supported": bool(strategy.get("supported")),
        "confidence": str(strategy.get("confidence") or confidence_score.get("label") or "unknown"),
        "confidence_score": confidence_score.get("score"),
        "caveat_count": len(confidence_score.get("caveats", [])) if isinstance(confidence_score.get("caveats"), list) else 0,
    }


def _validation_component(validation: Mapping[str, Any], validation_ready: bool | None) -> dict[str, Any]:
    replay_result = validation.get("replay_result") if isinstance(validation.get("replay_result"), Mapping) else {}
    checks = validation.get("checks") if isinstance(validation.get("checks"), Mapping) else {}
    return {
        "validation_ready": validation_ready,
        "status": validation.get("validation_status") or "missing",
        "replay_ok": replay_result.get("ok"),
        "source_complete": checks.get("source_complete"),
        "runtime_invocation_ok": checks.get("runtime_invocation_ok"),
        "sign_shape_ok": checks.get("sign_shape_ok"),
    }


def _runtime_context_component(runtime_context_diff: Mapping[str, Any], extraction: Mapping[str, Any]) -> dict[str, Any]:
    summary = runtime_context_diff.get("summary") if isinstance(runtime_context_diff.get("summary"), Mapping) else {}
    return {
        "status": runtime_context_diff.get("status") or "missing",
        "stable": runtime_context_diff.get("stable"),
        "sample_count": runtime_context_diff.get("sample_count", 0),
        "required": [str(item) for item in extraction.get("runtime_context_required", []) if item],
        "captured": [str(item) for item in extraction.get("captured_runtime_context", []) if item],
        "volatile_field_count": int(summary.get("volatile_field_count") or 0),
        "session_bound_field_count": int(summary.get("session_bound_field_count") or 0),
        "missing_field_count": int(summary.get("missing_field_count") or 0),
        "missing_requirement_count": int(summary.get("missing_requirement_count") or len(runtime_context_diff.get("missing_requirements", []) or [])),
        "type_drift_field_count": int(summary.get("type_drift_field_count") or 0),
        "object_drift_field_count": int(summary.get("object_drift_field_count") or 0),
    }


def _protected_flow_component(strategy: Mapping[str, Any]) -> dict[str, Any]:
    triage = strategy.get("triage") if isinstance(strategy.get("triage"), Mapping) else {}
    triage_hook_plan = strategy.get("triage_hook_plan") if isinstance(strategy.get("triage_hook_plan"), Mapping) else {}
    return {
        "triage": bool(triage),
        "categories": [str(item) for item in triage.get("categories", []) if item],
        "hook_plan_status": triage_hook_plan.get("status") or "missing",
        "hook_plan_count": len(triage_hook_plan.get("hook_plans", [])) if isinstance(triage_hook_plan.get("hook_plans"), list) else 0,
    }


def _rebuild_component(extraction: Mapping[str, Any], *, ready: bool | None, replay_url: str | None) -> dict[str, Any]:
    return {
        "ready": ready,
        "replay_url_available": bool(replay_url),
        "pure_extractable": bool(extraction.get("pure_extractable")),
        "context_aware_extractable": bool(extraction.get("context_aware_extractable")),
        "manual_port_required": bool(extraction.get("manual_port_required")),
    }


def _runtime_context_score_adjustments(runtime_context_diff: Mapping[str, Any]) -> tuple[float, list[str], list[str]]:
    if not runtime_context_diff:
        return 0.0, [], []
    summary = runtime_context_diff.get("summary") if isinstance(runtime_context_diff.get("summary"), Mapping) else {}
    volatile_count = int(summary.get("volatile_field_count") or _field_count(runtime_context_diff, "volatile"))
    session_bound_count = int(summary.get("session_bound_field_count") or _field_count(runtime_context_diff, "session_bound"))
    missing_count = int(summary.get("missing_field_count") or _field_count(runtime_context_diff, "missing_in_some_samples"))
    missing_requirement_count = int(summary.get("missing_requirement_count") or len(runtime_context_diff.get("missing_requirements", []) or []))
    type_drift_count = int(summary.get("type_drift_field_count") or _field_count(runtime_context_diff, "type_drift"))
    object_drift_count = int(summary.get("object_drift_field_count") or _field_count(runtime_context_diff, "object_drift"))
    stable_count = int(summary.get("stable_field_count") or _field_count(runtime_context_diff, "stable"))

    adjustment = 0.0
    signals: list[str] = []
    blockers: list[str] = []
    if stable_count and not any((volatile_count, missing_count, missing_requirement_count, type_drift_count, object_drift_count)):
        adjustment += 0.04
        signals.append("runtime_context_stable")
    if session_bound_count:
        adjustment -= min(0.08, 0.02 * session_bound_count)
        signals.append("session_bound_runtime_context")
    if volatile_count:
        adjustment -= min(0.18, 0.05 * volatile_count)
        blockers.append("volatile_runtime_context")
    if missing_count or missing_requirement_count:
        adjustment -= min(0.2, 0.05 * (missing_count + missing_requirement_count))
        blockers.append("missing_runtime_context")
    if type_drift_count:
        adjustment -= min(0.16, 0.05 * type_drift_count)
        blockers.append("runtime_context_type_drift")
    if object_drift_count:
        adjustment -= min(0.1, 0.03 * object_drift_count)
        signals.append("runtime_context_object_drift")
    return adjustment, signals, blockers


def _field_count(runtime_context_diff: Mapping[str, Any], classification: str) -> int:
    fields = runtime_context_diff.get("fields")
    if not isinstance(fields, list):
        return 0
    return sum(1 for item in fields if isinstance(item, Mapping) and item.get("classification") == classification)


def _is_triage_strategy(strategy: Mapping[str, Any]) -> bool:
    return str(strategy.get("id") or "").startswith("triage_") or isinstance(strategy.get("triage"), Mapping)


def _protected_flow_signals(strategy: Mapping[str, Any]) -> list[str]:
    triage = strategy.get("triage") if isinstance(strategy.get("triage"), Mapping) else {}
    categories = [str(item) for item in triage.get("categories", []) if item]
    return [f"protected_flow:{category}" for category in categories]


def _score_label(score: float, blockers: Sequence[str]) -> str:
    if "protected_flow_triage_required" in blockers or "strategy_not_supported" in blockers or "manual_port_required" in blockers:
        if score < 0.45:
            return "runtime_assisted_required"
    if score >= 0.78 and not blockers:
        return "strong_pure_candidate"
    if score >= 0.62 and not any(blocker in blockers for blocker in ("validation_not_ready", "missing_runtime_context", "volatile_runtime_context")):
        return "reviewable_candidate"
    if score >= 0.38:
        return "needs_more_evidence"
    return "runtime_assisted_required"


def _recommended_next_action(label: str, blockers: Sequence[str], signals: Sequence[str]) -> str:
    blocker_set = set(blockers)
    signal_set = set(signals)
    if "protected_flow_triage_required" in blocker_set:
        return "run_reviewed_runtime_triage_hooks_before_porting"
    if "validation_not_ready" in blocker_set:
        return "rerun_runtime_validation_before_delivery"
    if "missing_runtime_context" in blocker_set or "missing_runtime_context_binding" in blocker_set:
        return "collect_required_runtime_context_samples"
    if "volatile_runtime_context" in blocker_set:
        return "bind_volatile_runtime_context_dynamically"
    if label == "strong_pure_candidate":
        return "review_generated_pure_rebuild_and_prepare_delivery"
    if "context_aware_extractable" in signal_set:
        return "review_context_aware_rebuild_before_scaling"
    if label == "reviewable_candidate":
        return "manual_review_before_delivery"
    return "expand_source_runtime_evidence_or_keep_runtime_backend"


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
