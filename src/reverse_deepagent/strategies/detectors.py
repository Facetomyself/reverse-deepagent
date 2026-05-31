from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .evidence_scoring import build_strategy_evidence_score
from .protected_flow_planner import build_protected_flow_triage_plan

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
    """Detect the best supported or triage-only rebuild strategy from a JS source snippet."""

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
    if _has_crypto_marker(source_context):
        return None
    direct_template_patterns = (
        r"`sig_\$\{keyword\}_\$\{timestamp\}`",
        r"['\"]sig_['\"]\s*\+\s*keyword\s*\+\s*['\"]_['\"]\s*\+\s*timestamp",
        r"['\"]sig_['\"]\s*\+\s*keyword\s*\+\s*['\"]_['\"]\s*\+\s*String\(\s*timestamp\s*\)",
    )
    if any(re.search(pattern, source_context, flags=re.IGNORECASE | re.DOTALL) for pattern in direct_template_patterns):
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


def _detect_protected_flow_triage(source_context: str) -> dict[str, Any] | None:
    findings = _protected_flow_findings(source_context)
    if not findings:
        return None

    categories = {finding["category"] for finding in findings}
    strategy_id = _triage_strategy_id(categories)
    positive_markers = [str(finding["marker"]) for finding in findings]
    runtime_requirements = _triage_runtime_requirements(categories)
    caveats = ["triage-only", "runtime-assisted execution required"]
    if "wasm" in categories:
        caveats.append("wasm module/glue must be inspected before porting")
    if "vm" in categories:
        caveats.append("custom bytecode VM semantics are not proven portable")
    if "anti_debug" in categories:
        caveats.append("anti-debug or anti-tamper checks can change runtime behavior")
    if "dynamic_secret" in categories:
        caveats.append("runtime-only or server-bound secret is not modeled")

    strategy = _strategy(
        strategy_id,
        supported=False,
        confidence="medium",
        description="WASM / VM / heavy obfuscation indicators were detected; pure-Python rebuild is not safe yet.",
        dependencies=[],
        template="unknown",
        confidence_reason=f"Detected protected runtime markers: {', '.join(positive_markers)}.",
        positive_markers=positive_markers,
        caveats=caveats,
    )
    strategy.update(
        {
            "triage": {
                "categories": sorted(categories),
                "findings": findings,
                "runtime_assisted": True,
            },
            "runtime_context_required": runtime_requirements,
            "runtime_replay_plan": {
                "mode": "runtime-assisted",
                "description": "Keep the original JS / WASM / VM flow under an instrumented runtime until portable semantics are proven.",
                "recommended_actions": [
                    "capture source snippets around protected markers",
                    "record request initiator stack and hook timeline",
                    "inspect WASM imports/exports or VM dispatcher entrypoints when present",
                    "promote only deterministic, browser-independent semantics to pure rebuild",
                ],
            },
            "hook_points": _triage_hook_points(findings),
            "known_blockers": caveats,
        }
    )
    strategy["triage_hook_plan"] = build_protected_flow_triage_plan(strategy)
    strategy["evidence_score"] = build_strategy_evidence_score(strategy)
    return strategy


def _detect_crypto_hash_strategy(source_context: str) -> dict[str, Any] | None:
    lowered = source_context.lower()
    template = _detect_message_template(source_context)
    hmac_call = _extract_hmac_call(source_context)
    if hmac_call is not None:
        algorithm = hmac_call["algorithm"]
        secret = _extract_literal_secret_from_argument(source_context, hmac_call["secret_argument"])
        display_algorithm = algorithm.upper().replace("SHA", "SHA-")
        return _strategy(
            f"hmac_{algorithm}_keyword_timestamp",
            supported=bool(secret),
            confidence="medium" if secret else "low",
            description=f"HMAC-{display_algorithm} over a keyword/timestamp message.",
            dependencies=["python-stdlib:hashlib", "python-stdlib:hmac"],
            template=template,
            salt=secret or "",
            confidence_reason=f"Detected HMAC-{display_algorithm} marker." + (" Literal secret was extracted." if secret else " Secret/key is dynamic or unavailable."),
            positive_markers=["hmac", algorithm],
            caveats=[] if secret else ["secret/key is dynamic or unavailable"],
        )
    for algorithm in ("md5", "sha1", "sha256", "sha512"):
        subtle_name = _webcrypto_algorithm_name(algorithm)
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
            salt=_extract_literal_salt(source_context),
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
            salt=_extract_literal_salt(source_context),
            confidence_reason="Detected encodeURIComponent/URLSearchParams marker in source context.",
            positive_markers=["encodeURIComponent/URLSearchParams", template],
        )
    return None


ALGORITHM_STRATEGY_REGISTRY: tuple[AlgorithmStrategyRule, ...] = (
    AlgorithmStrategyRule(
        rule_id="protected_flow_triage",
        emits=(
            "triage_wasm_module",
            "triage_vm_obfuscation",
            "triage_anti_debug_runtime",
            "triage_dynamic_secret",
            "triage_wasm_vm_obfuscation",
        ),
        detector=_detect_protected_flow_triage,
        description="Detect WASM, VM, anti-debug, heavy obfuscation, and dynamic-secret flows that must stay triage/runtime-assisted.",
    ),
    AlgorithmStrategyRule(
        rule_id="deterministic_fixture",
        emits=("fixture_seed_mod100000",),
        detector=_detect_fixture_seed_strategy,
        description="Detect the bundled deterministic fixture reducer.",
    ),
    AlgorithmStrategyRule(
        rule_id="crypto_hash",
        emits=(
            "hmac_md5_keyword_timestamp",
            "hmac_sha1_keyword_timestamp",
            "hmac_sha256_keyword_timestamp",
            "hmac_sha512_keyword_timestamp",
            "md5_keyword_timestamp",
            "sha1_keyword_timestamp",
            "sha256_keyword_timestamp",
            "sha512_keyword_timestamp",
        ),
        detector=_detect_crypto_hash_strategy,
        description="Detect hashlib / HMAC-compatible JavaScript hash flows.",
    ),
    AlgorithmStrategyRule(
        rule_id="sig_template",
        emits=("sig_keyword_timestamp_template",),
        detector=_detect_sig_template_strategy,
        description="Detect simple sig_<keyword>_<timestamp> template flows.",
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
    strategy = {
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
    strategy["evidence_score"] = build_strategy_evidence_score(strategy)
    return strategy


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


def _protected_flow_findings(source_context: str) -> list[dict[str, str]]:
    patterns: tuple[tuple[str, str, str], ...] = (
        ("wasm", "WebAssembly.instantiate", r"\bWebAssembly\.(?:instantiate|compile|instantiateStreaming|compileStreaming)\b"),
        ("wasm", ".wasm", r"['\"][^'\"]+\.wasm(?:\?[^'\"]*)?['\"]"),
        ("wasm", "wasm-bindgen", r"\b(?:wasm_bindgen|__wbindgen|wasm-bindgen)\b"),
        ("wasm", "Emscripten glue", r"\b(?:Module\[['\"]wasmMemory['\"]\]|HEAPU8|asm\.js|Emscripten)\b"),
        ("vm", "opcode dispatch loop", r"\b(?:opcode|opcodes|bytecode|byteCode|dispatchTable|vm_dispatch|instructionPointer)\b"),
        ("vm", "switch opcode dispatcher", r"switch\s*\([^)]*(?:opcode|op|instruction|bytecode)[^)]*\)"),
        ("vm", "encrypted function body", r"\b(?:decrypt|decode)\w*\s*\([^)]*(?:bytecode|payload|cipher|encrypted)[^)]*\)"),
        ("obfuscation", "control-flow flattening", r"\b(?:controlFlowFlattening|_0x[a-fA-F0-9]{4,}|stringArray|rotateStringArray)\b"),
        ("obfuscation", "runtime code generation", r"\b(?:eval|Function)\s*\("),
        ("anti_debug", "debugger trap", r"\bdebugger\b"),
        ("anti_debug", "DevTools detection", r"\b(?:devtools|__REACT_DEVTOOLS_GLOBAL_HOOK__|outerWidth\s*-\s*innerWidth)\b"),
        ("anti_debug", "timing probe", r"\b(?:performance\.now|Date\.now)\s*\(\s*\)\s*[+-]\s*(?:performance\.now|Date\.now)\s*\("),
        ("anti_debug", "function integrity check", r"\.toString\s*\(\s*\)\s*\.\s*(?:includes|indexOf|match)\s*\("),
        ("dynamic_secret", "runtime challenge", r"\b(?:__challenge|serverNonce|challengeToken|runtimeChallenge)\b"),
        ("dynamic_secret", "native bridge secret", r"\b(?:nativeBridge|JSBridge|invokeNativeSign|getNativeSecret)\b"),
    )
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for category, marker, pattern in patterns:
        match = re.search(pattern, source_context, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        key = (category, marker)
        if key in seen:
            continue
        seen.add(key)
        snippet = re.sub(r"\s+", " ", source_context[max(0, match.start() - 80) : match.end() + 80]).strip()
        findings.append({"category": category, "marker": marker, "snippet": snippet[:240]})
    return findings


def _triage_strategy_id(categories: set[str]) -> str:
    if len(categories & {"wasm", "vm", "obfuscation", "anti_debug", "dynamic_secret"}) > 1:
        return "triage_wasm_vm_obfuscation"
    if "wasm" in categories:
        return "triage_wasm_module"
    if "vm" in categories or "obfuscation" in categories:
        return "triage_vm_obfuscation"
    if "anti_debug" in categories:
        return "triage_anti_debug_runtime"
    if "dynamic_secret" in categories:
        return "triage_dynamic_secret"
    return "triage_wasm_vm_obfuscation"


def _triage_runtime_requirements(categories: set[str]) -> list[str]:
    requirements: list[str] = ["runtime-js-vm"]
    if "wasm" in categories:
        requirements.append("wasm-module")
    if "anti_debug" in categories:
        requirements.append("anti-debug-runtime")
    if "dynamic_secret" in categories:
        requirements.append("dynamic-secret")
    return requirements


def _triage_hook_points(findings: list[dict[str, str]]) -> list[str]:
    hook_points: list[str] = []
    for finding in findings:
        category = finding["category"]
        marker = finding["marker"]
        if category == "wasm":
            hook_points.extend(["WebAssembly.instantiate", "WebAssembly.compile", "fetch(.wasm)"])
        elif category in {"vm", "obfuscation"}:
            hook_points.extend(["VM dispatcher", "opcode table", "runtime code generation"])
        elif category == "anti_debug":
            hook_points.extend(["debugger/timing checks", "function integrity checks"])
        elif category == "dynamic_secret":
            hook_points.extend(["challenge/nonce source", "fingerprint/native bridge source"])
        hook_points.append(marker)
    return sorted(set(hook_points))


def _detect_message_template(source_context: str) -> str:
    normalized = re.sub(r"\s+", "", source_context.lower())
    if "keyword}:${timestamp}:" in normalized or "keyword+':'+timestamp+':'" in normalized:
        return "keyword_colon_timestamp_colon_salt"
    if "keyword}:${timestamp}" in normalized or "keyword+':'+timestamp" in normalized:
        return "keyword_colon_timestamp"
    if "keyword}${timestamp}" in normalized or "keyword+timestamp" in normalized:
        return "keyword_timestamp"
    return "keyword_colon_timestamp"


def _webcrypto_algorithm_name(algorithm: str) -> str:
    return {
        "sha1": "sha-1",
        "sha256": "sha-256",
        "sha512": "sha-512",
    }.get(algorithm, algorithm)


def _has_crypto_marker(source_context: str) -> bool:
    lowered = source_context.lower()
    return any(
        marker in lowered
        for marker in (
            "cryptojs",
            "subtle.digest",
            "createhash",
            "hmac",
            "md5",
            "sha1",
            "sha-1",
            "sha256",
            "sha-256",
            "sha512",
            "sha-512",
        )
    )


def _extract_literal_secret(source_context: str) -> str | None:
    call = _extract_hmac_call(source_context)
    if call is None:
        return None
    return _extract_literal_secret_from_argument(source_context, call["secret_argument"])


def _extract_literal_secret_from_argument(source_context: str, arg: str) -> str | None:
    literal = _strip_js_string_literal(arg)
    if literal is not None:
        return literal
    if re.fullmatch(r"[A-Za-z_$][\w$]*", arg):
        assignment = re.search(
            rf"(?:const|let|var)?\s*{re.escape(arg)}\s*=\s*['\"]([^'\"]+)['\"]",
            source_context,
            flags=re.IGNORECASE,
        )
        if assignment:
            return assignment.group(1)
    return None


def _extract_hmac_call(source_context: str) -> dict[str, str] | None:
    match = re.search(
        r"(?:CryptoJS\.)?(?P<name>hmac(?:md5|sha1|sha256|sha512)|Hmac(?:MD5|SHA1|SHA256|SHA512))\s*\(\s*(?:`[^`]*`|[^,]+)\s*,\s*(?P<secret>[^)]+?)\s*\)",
        source_context,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    algorithm = _hmac_algorithm_from_name(match.group("name"))
    if not algorithm:
        return None
    return {"algorithm": algorithm, "secret_argument": match.group("secret").strip()}


def _hmac_algorithm_from_name(name: str) -> str | None:
    normalized = name.lower()
    for algorithm in ("sha512", "sha256", "sha1", "md5"):
        if algorithm in normalized:
            return algorithm
    return None


def _strip_js_string_literal(value: str) -> str | None:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return None


def _extract_literal_salt(source_context: str) -> str:
    match = re.search(r"(?:salt|seed)\s*=\s*['\"]([^'\"]+)['\"]", source_context, flags=re.IGNORECASE)
    return match.group(1) if match else ""
