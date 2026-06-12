from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from reverse_deepagent.strategies import (
    AlgorithmStrategyRule,
    StrategyDetectorProviderRegistration,
    build_strategy_evidence_score,
    strategy_detector_metadata_side_effect_policy,
)

REFERENCE_STRATEGY_DETECTOR_PROVIDER_ID = "reference-strategy-detector"
REFERENCE_STRATEGY_DETECTOR_ALIASES = ("fixture-strategy-detector", "reference-detector")
_DETECTOR_INVOCATION_COUNT = 0

_PATTERN_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "category": "signing-flow",
        "marker": "sign",
        "pattern": r"\b(?:sign|signature|sig|x-sign|x-signature|buildSign|makeSign)\b",
        "strategy_tag": "sign-marker",
    },
    {
        "category": "identity-or-challenge",
        "marker": "bearer-or-nonce-wording",
        "pattern": r"\b(?:bearer|access[_-]?token|auth[_-]?token|csrf|nonce|timestamp|ts)\b",
        "strategy_tag": "auth-marker",
    },
    {
        "category": "crypto",
        "marker": "hmac",
        "pattern": r"\b(?:hmac|HmacSHA256|HmacSHA1|HmacSHA512|CryptoJS\.Hmac|createHmac)\b",
        "strategy_tag": "hmac-marker",
    },
    {
        "category": "crypto",
        "marker": "aes",
        "pattern": r"\b(?:aes|AES|CryptoJS\.AES|subtle\.encrypt|subtle\.decrypt)\b",
        "strategy_tag": "aes-marker",
    },
    {
        "category": "crypto",
        "marker": "rsa",
        "pattern": r"\b(?:rsa|RSA|JSEncrypt|publicEncrypt|subtle\.importKey)\b",
        "strategy_tag": "rsa-marker",
    },
    {
        "category": "bundler",
        "marker": "webpack",
        "pattern": r"\b(?:webpackJsonp|__webpack_require__|webpackChunk|\.m\.exports)\b",
        "strategy_tag": "webpack-marker",
    },
    {
        "category": "network",
        "marker": "fetch",
        "pattern": r"\bfetch\s*\(",
        "strategy_tag": "fetch-marker",
    },
    {
        "category": "network",
        "marker": "xhr",
        "pattern": r"\b(?:XMLHttpRequest|\.open\s*\(|\.send\s*\()",
        "strategy_tag": "xhr-marker",
    },
)


def reference_detector(source_context: str) -> dict[str, Any]:
    """Detect conservative reference markers from an already-provided source string.

    This detector is deliberately pure: it does not read files, perform network
    access, start a browser, call MCP, evaluate JavaScript, execute replay, or
    collect runtime context. The only input is ``source_context``.
    """

    global _DETECTOR_INVOCATION_COUNT  # noqa: PLW0603
    _DETECTOR_INVOCATION_COUNT += 1
    findings = _find_markers(source_context)
    if not findings:
        return _unsupported_strategy()

    categories = sorted({finding["category"] for finding in findings})
    positive_markers = [finding["marker"] for finding in findings]
    strategy_id = _strategy_id(categories, positive_markers)
    supported = not _requires_runtime_review(categories, positive_markers)
    confidence = _confidence_for(categories, positive_markers, supported=supported)
    caveats = _caveats(categories, positive_markers)
    strategy = {
        "id": strategy_id,
        "supported": supported,
        "confidence": confidence,
        "description": "Reference StrategyDetector matched deterministic source markers for signing, crypto, bundler, or network triage.",
        "dependencies": ["python-stdlib:re"],
        "template": _template_hint(source_context),
        "salt": "",
        "confidence_reason": f"Detected reference marker categories: {', '.join(categories)}.",
        "confidence_score": _confidence_score(
            confidence,
            supported=supported,
            positive_markers=positive_markers,
            caveats=caveats,
        ),
        "marker_findings": findings,
        "runtime_context_required": _runtime_context_required(categories, positive_markers),
        "runtime_replay_plan": {
            "mode": "not-executed",
            "description": "Reference provider only reports markers; any runtime follow-up must be requested by an explicit reviewer action outside this detector.",
        },
    }
    strategy["evidence_score"] = build_strategy_evidence_score(strategy)
    return strategy


REFERENCE_RULES: tuple[AlgorithmStrategyRule, ...] = (
    AlgorithmStrategyRule(
        rule_id="reference_signing_marker_inventory",
        emits=("reference_signing_marker_inventory", "reference_signing_crypto_marker_inventory"),
        detector=lambda source_context: None,
        description="Detect source-level signing and challenge wording markers without runtime context collection.",
    ),
    AlgorithmStrategyRule(
        rule_id="reference_crypto_marker_inventory",
        emits=("reference_crypto_marker_inventory", "reference_signing_crypto_marker_inventory"),
        detector=lambda source_context: None,
        description="Detect HMAC / AES / RSA crypto markers from a provided source snippet.",
    ),
    AlgorithmStrategyRule(
        rule_id="reference_bundle_network_marker_inventory",
        emits=("reference_bundle_network_marker_inventory", "reference_network_marker_inventory"),
        detector=lambda source_context: None,
        description="Detect webpack and fetch / XHR markers from a provided source snippet.",
    ),
)


def strategy_detector_registration() -> StrategyDetectorProviderRegistration:
    """Return the reference StrategyDetector provider registration without running detection."""

    return StrategyDetectorProviderRegistration(
        provider_id=REFERENCE_STRATEGY_DETECTOR_PROVIDER_ID,
        display_name="Reference StrategyDetector provider",
        aliases=REFERENCE_STRATEGY_DETECTOR_ALIASES,
        rules=REFERENCE_RULES,
        detector=reference_detector,
        description="Pure Python reference StrategyDetector provider for deterministic marker inventory fixtures.",
        metadata={
            "target_platforms": ["web"],
            "detector_scope": "provided-source-string-marker-inventory",
            "plugin_kind": "reference-fixture",
            "deterministic": True,
            "runtime_context_collection": False,
            "replay_execution": False,
            "browser_provider_usage": False,
            "mcp_usage": False,
            "external_io": False,
            "catalog_version": "2026-06-12.reference-marker-v1",
        },
        side_effect_policy=strategy_detector_metadata_side_effect_policy(),
    )


def detector_invocation_count() -> int:
    """Expose detector invocation count for side-effect-free registration tests."""

    return _DETECTOR_INVOCATION_COUNT


def _find_markers(source_context: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in _PATTERN_CATALOG:
        match = re.search(str(item["pattern"]), source_context, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        category = str(item["category"])
        marker = str(item["marker"])
        key = (category, marker)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "category": category,
                "marker": marker,
                "strategy_tag": str(item["strategy_tag"]),
                "match_span": [match.start(), match.end()],
                "match_length": match.end() - match.start(),
                "source_length": len(source_context),
                "pattern_digest_sha256": _digest_text(str(item["pattern"])),
                "context_redacted": True,
            }
        )
    return findings


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strategy_id(categories: Iterable[str], positive_markers: list[str]) -> str:
    category_set = set(categories)
    if "signing-flow" in category_set and "crypto" in category_set:
        return "reference_signing_crypto_marker_inventory"
    if "crypto" in category_set:
        return "reference_crypto_marker_inventory"
    if "bundler" in category_set or "network" in category_set:
        if category_set <= {"bundler", "network"}:
            return "reference_bundle_network_marker_inventory"
        return "reference_network_marker_inventory"
    if positive_markers:
        return "reference_signing_marker_inventory"
    return "unsupported_manual_port_required"


def _requires_runtime_review(categories: Iterable[str], positive_markers: list[str]) -> bool:
    category_set = set(categories)
    return "crypto" in category_set and any(marker in {"aes", "rsa"} for marker in positive_markers)


def _confidence_for(categories: Iterable[str], positive_markers: list[str], *, supported: bool) -> str:
    category_set = set(categories)
    if not supported:
        return "low"
    if "signing-flow" in category_set and "crypto" in category_set and len(positive_markers) >= 3:
        return "high"
    if len(positive_markers) >= 2:
        return "medium"
    return "low"


def _caveats(categories: Iterable[str], positive_markers: list[str]) -> list[str]:
    caveats: list[str] = []
    category_set = set(categories)
    if "crypto" in category_set and any(marker in {"aes", "rsa"} for marker in positive_markers):
        caveats.append("asymmetric or encryption marker requires manual review before pure rebuild")
    if "network" in category_set:
        caveats.append("network marker is inventory-only and does not imply replay readiness")
    if "bundler" in category_set:
        caveats.append("bundled source marker may require source-map or module-boundary review")
    return caveats


def _runtime_context_required(categories: Iterable[str], positive_markers: list[str]) -> list[str]:
    requirements: list[str] = []
    category_set = set(categories)
    if "network" in category_set:
        requirements.append("explicit-review-network-context")
    if any(marker in {"aes", "rsa"} for marker in positive_markers):
        requirements.append("explicit-review-crypto-parameters")
    return requirements


def _template_hint(source_context: str) -> str:
    normalized = re.sub(r"\s+", "", source_context.lower())
    if "keyword}:${timestamp}" in normalized or "keyword+':'+timestamp" in normalized:
        return "keyword_colon_timestamp"
    if "keyword}${timestamp}" in normalized or "keyword+timestamp" in normalized:
        return "keyword_timestamp"
    return "unknown"


def _confidence_score(
    confidence: str,
    *,
    supported: bool,
    positive_markers: list[str],
    caveats: list[str],
) -> dict[str, Any]:
    base_score = {"high": 0.9, "medium": 0.65, "low": 0.25}.get(confidence, 0.25)
    if not supported:
        base_score = min(base_score, 0.2)
    if caveats:
        base_score = max(0.0, base_score - min(0.25, 0.06 * len(caveats)))
    return {
        "score": round(base_score, 2),
        "label": confidence,
        "positive_markers": positive_markers,
        "caveats": caveats,
    }


def _unsupported_strategy() -> dict[str, Any]:
    strategy = {
        "id": "unsupported_manual_port_required",
        "supported": False,
        "confidence": "low",
        "description": "Reference StrategyDetector did not match deterministic source markers.",
        "dependencies": [],
        "template": "unknown",
        "salt": "",
        "confidence_reason": "No reference marker was present in the provided source string.",
        "confidence_score": {
            "score": 0.2,
            "label": "low",
            "positive_markers": [],
            "caveats": ["reference detector did not match"],
        },
        "marker_findings": [],
        "runtime_context_required": [],
        "runtime_replay_plan": {
            "mode": "not-executed",
            "description": "No replay was executed by the reference detector.",
        },
    }
    strategy["evidence_score"] = build_strategy_evidence_score(strategy)
    return strategy
