from __future__ import annotations

from typing import Any

from reverse_deepagent.strategies import (
    AlgorithmStrategyRule,
    StrategyDetectorProviderRegistration,
    build_strategy_evidence_score,
    strategy_detector_metadata_side_effect_policy,
)

TEMPLATE_STRATEGY_DETECTOR_PROVIDER_ID = "template-strategy-detector"
TEMPLATE_STRATEGY_DETECTOR_ALIASES = ("strategy-template", "custom-strategy-template")
_DETECTOR_INVOCATION_COUNT = 0


def template_detector(source_context: str) -> dict[str, Any]:
    """Copy-and-replace detector scaffold.

    Real detectors should stay pure and source-context based. They should not
    start browsers, fetch remote resources, call MCP, evaluate JavaScript, or
    collect runtime context from inside the detector.
    """

    global _DETECTOR_INVOCATION_COUNT  # noqa: PLW0603
    _DETECTOR_INVOCATION_COUNT += 1
    if "TEMPLATE_SIGN_STRATEGY" not in source_context:
        return {
            "id": "unsupported_manual_port_required",
            "supported": False,
            "confidence": "low",
            "description": "Template strategy detector did not match the source context.",
            "dependencies": [],
            "template": "unknown",
            "salt": "",
            "confidence_reason": "No TEMPLATE_SIGN_STRATEGY marker was present.",
            "confidence_score": {"score": 0.2, "label": "low", "positive_markers": [], "caveats": ["template detector did not match"]},
            "evidence_score": build_strategy_evidence_score({"supported": False, "confidence": "low", "replay_url": ""}),
        }
    strategy = {
        "id": "template_literal_strategy",
        "supported": True,
        "confidence": "medium",
        "description": "Template detector matched TEMPLATE_SIGN_STRATEGY marker.",
        "dependencies": ["python-stdlib"],
        "template": "keyword_colon_timestamp",
        "salt": "",
        "confidence_reason": "Detected TEMPLATE_SIGN_STRATEGY marker.",
        "confidence_score": {"score": 0.65, "label": "medium", "positive_markers": ["TEMPLATE_SIGN_STRATEGY"], "caveats": []},
    }
    strategy["evidence_score"] = build_strategy_evidence_score(strategy)
    return strategy


TEMPLATE_RULES: tuple[AlgorithmStrategyRule, ...] = (
    AlgorithmStrategyRule(
        rule_id="template_literal_strategy_rule",
        emits=("template_literal_strategy",),
        detector=lambda source_context: None,
        description="Template rule placeholder; replace with real conservative strategy detection.",
    ),
)


def strategy_detector_registration() -> StrategyDetectorProviderRegistration:
    """Return the template StrategyDetector provider registration without running detection."""

    return StrategyDetectorProviderRegistration(
        provider_id=TEMPLATE_STRATEGY_DETECTOR_PROVIDER_ID,
        display_name="Template StrategyDetector provider",
        aliases=TEMPLATE_STRATEGY_DETECTOR_ALIASES,
        rules=TEMPLATE_RULES,
        detector=template_detector,
        description="Copy-and-replace StrategyDetector plugin template.",
        metadata={
            "target_platforms": ["web"],
            "detector_scope": "source-snippet-patterns",
            "plugin_kind": "template-only",
            "runtime_context_collection": False,
            "replay_execution": False,
        },
        side_effect_policy=strategy_detector_metadata_side_effect_policy(),
    )


def detector_invocation_count() -> int:
    """Expose detector invocation count for template contract tests."""

    return _DETECTOR_INVOCATION_COUNT
