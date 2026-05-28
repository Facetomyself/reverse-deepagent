from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

StrategyDetector = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class AlgorithmStrategyRule:
    """Registry entry for conservative source-pattern to rebuild-strategy detection."""

    rule_id: str
    emits: tuple[str, ...]
    detector: StrategyDetector
    description: str


def detect_algorithm_strategy(
    source_context: str,
    registry: tuple[AlgorithmStrategyRule, ...] | None = None,
) -> dict[str, Any]:
    """Detect the best supported rebuild strategy from a JS source snippet."""

    for rule in registry or ALGORITHM_STRATEGY_REGISTRY:
        strategy = rule.detector(source_context)
        if strategy:
            return strategy
    return _unsupported_strategy()


def list_algorithm_strategy_registry() -> list[dict[str, Any]]:
    """Return JSON-serializable metadata for registered strategy detectors."""

    return [
        {
            "rule_id": rule.rule_id,
            "emits": list(rule.emits),
            "description": rule.description,
        }
        for rule in ALGORITHM_STRATEGY_REGISTRY
    ]


def _detect_fixture_seed_strategy(source_context: str) -> dict[str, Any] | None:
    lowered = source_context.lower()
    if "fixture_seed" in lowered and "charcodeat" in lowered and "100000" in lowered:
        return _strategy(
            "fixture_seed_mod100000",
            supported=True,
            confidence="high",
            description="Sum charCodeAt(keyword:timestamp:FIXTURE_SEED) modulo 100000, then emit sig_<hex>_<timestamp>.",
            dependencies=["python-stdlib"],
            confidence_reason="Detected FIXTURE_SEED, charCodeAt reducer and modulo 100000 in source context.",
            positive_markers=["fixture_seed", "charCodeAt", "modulo 100000"],
        )
    return None


def _detect_sig_template_strategy(source_context: str) -> dict[str, Any] | None:
    if re.search(r"sig_.*keyword.*timestamp", source_context, flags=re.IGNORECASE | re.DOTALL):
        return _strategy(
            "sig_keyword_timestamp_template",
            supported=True,
            confidence="medium",
            description="Simple template sign of the form sig_<keyword>_<timestamp>.",
            dependencies=["python-stdlib"],
            confidence_reason="Detected sig_ template using keyword and timestamp.",
            positive_markers=["sig_ template", "keyword", "timestamp"],
        )
    return None


def _unsupported_strategy() -> dict[str, Any]:
    return _strategy(
        "unsupported_manual_port_required",
        supported=False,
        confidence="low",
        description="No safe pure-Python strategy recognized yet; manual port or JS execution backend is required.",
        dependencies=[],
        confidence_reason="No supported hash, hmac, encoding or deterministic template pattern was detected.",
        caveats=["manual port or runtime-backed execution required"],
    )


def _detect_crypto_hash_strategy(source_context: str) -> dict[str, Any] | None:
    lowered = source_context.lower()
    template = _detect_message_template(source_context)
    if "hmac" in lowered and "sha256" in lowered:
        secret = _extract_literal_secret(source_context)
        return _strategy(
            "hmac_sha256_keyword_timestamp",
            supported=bool(secret),
            confidence="medium" if secret else "low",
            description="HMAC-SHA256 over a keyword/timestamp message.",
            dependencies=["python-stdlib:hashlib", "python-stdlib:hmac"],
            template=template,
            salt=secret or "",
            confidence_reason="Detected HMAC-SHA256 marker." + (" Literal secret was extracted." if secret else " Secret/key is dynamic or unavailable."),
            positive_markers=["hmac", "sha256"],
            caveats=[] if secret else ["secret/key is dynamic or unavailable"],
        )
    for algorithm in ("md5", "sha1", "sha256"):
        subtle_name = "sha-256" if algorithm == "sha256" else "sha-1" if algorithm == "sha1" else algorithm
        patterns = [
            rf"\bcryptojs\.{algorithm}\b",
            rf"\bcrypto\.createhash\(['\"]{algorithm}['\"]\)",
            rf"subtle\.digest\(['\"]{subtle_name}['\"]",
            rf"\b{algorithm}\s*\(",
        ]
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns):
            return _strategy(
                f"{algorithm}_keyword_timestamp",
                supported=True,
                confidence="medium",
                description=f"{algorithm} hash over a keyword/timestamp message.",
                dependencies=["python-stdlib:hashlib"],
                template=template,
                salt=_extract_literal_salt(source_context),
                confidence_reason=f"Detected {algorithm} hash marker in source context.",
                positive_markers=[algorithm, template],
            )
    return None


def _detect_encoding_strategy(source_context: str) -> dict[str, Any] | None:
    lowered = source_context.lower()
    template = _detect_message_template(source_context)
    if "btoa" in lowered or "base64" in lowered:
        return _strategy(
            "base64_keyword_timestamp",
            supported=True,
            confidence="medium",
            description="Base64 encoding over a keyword/timestamp message.",
            dependencies=["python-stdlib:base64"],
            template=template,
            confidence_reason="Detected btoa/base64 marker in source context.",
            positive_markers=["btoa/base64", template],
        )
    if "encodeuricomponent" in lowered or "urlsearchparams" in lowered:
        return _strategy(
            "urlencode_keyword_timestamp",
            supported=True,
            confidence="medium",
            description="URL encoding over a keyword/timestamp message.",
            dependencies=["python-stdlib:urllib.parse"],
            template=template,
            confidence_reason="Detected encodeURIComponent/URLSearchParams marker in source context.",
            positive_markers=["encodeURIComponent/URLSearchParams", template],
        )
    return None


ALGORITHM_STRATEGY_REGISTRY: tuple[AlgorithmStrategyRule, ...] = (
    AlgorithmStrategyRule(
        rule_id="deterministic_fixture",
        emits=("fixture_seed_mod100000",),
        detector=_detect_fixture_seed_strategy,
        description="Detect the bundled deterministic fixture reducer.",
    ),
    AlgorithmStrategyRule(
        rule_id="sig_template",
        emits=("sig_keyword_timestamp_template",),
        detector=_detect_sig_template_strategy,
        description="Detect simple sig_<keyword>_<timestamp> template flows.",
    ),
    AlgorithmStrategyRule(
        rule_id="crypto_hash",
        emits=(
            "hmac_sha256_keyword_timestamp",
            "md5_keyword_timestamp",
            "sha1_keyword_timestamp",
            "sha256_keyword_timestamp",
        ),
        detector=_detect_crypto_hash_strategy,
        description="Detect hashlib / HMAC-compatible JavaScript hash flows.",
    ),
    AlgorithmStrategyRule(
        rule_id="encoding",
        emits=("base64_keyword_timestamp", "urlencode_keyword_timestamp"),
        detector=_detect_encoding_strategy,
        description="Detect simple browser encoding flows such as btoa or encodeURIComponent.",
    ),
)


def _strategy(
    strategy_id: str,
    *,
    supported: bool,
    confidence: str,
    description: str,
    dependencies: list[str],
    confidence_reason: str,
    template: str = "keyword_colon_timestamp",
    salt: str = "",
    positive_markers: list[str] | None = None,
    caveats: list[str] | None = None,
) -> dict[str, Any]:
    confidence_score = _confidence_score(
        confidence,
        supported=supported,
        positive_markers=positive_markers or [],
        caveats=caveats or [],
    )
    return {
        "id": strategy_id,
        "supported": supported,
        "confidence": confidence,
        "confidence_score": confidence_score,
        "description": description,
        "dependencies": dependencies,
        "template": template,
        "salt": salt,
        "confidence_reason": confidence_reason,
    }


def _confidence_score(
    confidence: str,
    *,
    supported: bool,
    positive_markers: list[str],
    caveats: list[str],
) -> dict[str, Any]:
    base_score = {
        "high": 0.9,
        "medium": 0.65,
        "low": 0.25,
    }.get(confidence, 0.25)
    if not supported:
        base_score = min(base_score, 0.2)
    if caveats:
        base_score = max(0.0, base_score - min(0.25, 0.08 * len(caveats)))
    return {
        "score": round(base_score, 2),
        "label": confidence,
        "positive_markers": positive_markers,
        "caveats": caveats,
    }


def _detect_message_template(source_context: str) -> str:
    normalized = re.sub(r"\s+", "", source_context.lower())
    if "keyword}:${timestamp}:" in normalized or "keyword+':'+timestamp+':'" in normalized:
        return "keyword_colon_timestamp_colon_salt"
    if "keyword}:${timestamp}" in normalized or "keyword+':'+timestamp" in normalized:
        return "keyword_colon_timestamp"
    if "keyword}${timestamp}" in normalized or "keyword+timestamp" in normalized:
        return "keyword_timestamp"
    return "keyword_colon_timestamp"


def _extract_literal_secret(source_context: str) -> str | None:
    for pattern in (
        r"(?:secret|key|salt)\s*=\s*['\"]([^'\"]+)['\"]",
        r"hmac(?:sha256)?\s*\([^,]+,\s*['\"]([^'\"]+)['\"]",
        r"HmacSHA256\s*\([^,]+,\s*['\"]([^'\"]+)['\"]",
    ):
        match = re.search(pattern, source_context, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_literal_salt(source_context: str) -> str:
    match = re.search(r"(?:salt|seed)\s*=\s*['\"]([^'\"]+)['\"]", source_context, flags=re.IGNORECASE)
    return match.group(1) if match else ""
