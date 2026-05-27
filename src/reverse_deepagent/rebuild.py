from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, ConfidenceLevel, ExecutionStatus, FinalResult, RebuildResult, TaskCard


def build_rebuild_bundle(task_card: TaskCard, final_result: FinalResult) -> tuple[dict[str, Any], dict[str, str]]:
    """Build a pure-Python rebuild plan and file bundle from validated candidates.

    This module deliberately emits a conservative demo bundle rather than
    pretending to be a universal JS-to-Python compiler. The current generator
    recognizes the deterministic local fixture algorithm and a simple mock
    template; unknown algorithms still produce a plan, but not runnable replay
    code.
    """

    validation_summary = _find_evidence_details(final_result, "function_validation_summary")
    validation_payload = _find_evidence_details(final_result, "function_validation_result")
    candidate_payload = _find_evidence_details(final_result, "function_candidate_card")
    runtime_context = _find_evidence_details(final_result, "runtime_context")

    validations = _as_list(validation_payload.get("validations"))
    candidates = _as_list(candidate_payload.get("candidates"))
    best_validation = _select_best_validation(validation_summary, validations)
    best_candidate = _match_candidate(best_validation, candidates)
    source_context = str(best_candidate.get("source_context") or "")
    strategy = _detect_algorithm_strategy(source_context)
    extraction = _build_pure_extraction(strategy, source_context, runtime_context)
    target_request_url = _pick_target_request_url(task_card, best_candidate)
    replay_url = _derive_replay_url(task_card, target_request_url)
    base_url = _derive_base_url(replay_url or task_card.target_url_or_file)
    ready = bool(best_validation and strategy["supported"] and (extraction["pure_extractable"] or extraction["context_aware_extractable"]) and replay_url)

    plan = {
        "ready": ready,
        "stage": "replay-delivery",
        "entrypoint": best_validation.get("function_name") if best_validation else None,
        "candidate_id": best_validation.get("candidate_id") if best_validation else None,
        "algorithm_strategy": strategy,
        "pure_extraction": extraction,
        "runtime_context": runtime_context,
        "source": {
            "file_url": best_candidate.get("file_url"),
            "script_id": best_candidate.get("script_id"),
            "line_number": best_candidate.get("line_number"),
            "source_complete": (best_validation.get("checks") or {}).get("source_complete") if best_validation else False,
        },
        "validation": {
            "status": best_validation.get("validation_status") if best_validation else "missing",
            "replay_ready": bool(validation_summary.get("replay_ready")),
            "sample_input": best_validation.get("sample_input") if best_validation else {},
            "sample_output": best_validation.get("sample_output") if best_validation else {},
            "replay_result": best_validation.get("replay_result") if best_validation else {},
        },
        "replay": {
            "base_url": base_url,
            "api_url": replay_url,
            "method": "POST",
            "headers": ["content-type", "x-sign", "x-fixture"],
            "body_fields": ["keyword", "timestamp", "sign", "fixture"],
        },
        "outputs": {
            "sign_rebuild": "artifacts/rebuild/sign_rebuild.py",
            "replay_demo": "artifacts/rebuild/replay_demo.py",
            "scrapy_middleware": "artifacts/rebuild/scrapy_middleware.py",
        },
        "limitations": _build_limitations(strategy),
    }

    files: dict[str, str] = {}
    if ready:
        files["sign_rebuild.py"] = render_sign_rebuild(plan)
        files["replay_demo.py"] = render_replay_demo(plan)
        files["scrapy_middleware.py"] = render_scrapy_middleware(plan)
    else:
        files["README.md"] = render_not_ready_readme(plan)
    return plan, files


def write_rebuild_bundle(base_dir: Path, task_card: TaskCard, final_result: FinalResult) -> RebuildResult:
    """Persist rebuild plan and delivery files under a standard artifact root."""

    workspace_dir = base_dir / "workspace"
    rebuild_dir = base_dir / "rebuild"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    rebuild_dir.mkdir(parents=True, exist_ok=True)

    plan, files = build_rebuild_bundle(task_card, final_result)
    generated_files: dict[str, str] = {}
    artifacts: list[ArtifactRef] = []

    plan_path = workspace_dir / "rebuild-plan.json"
    _write_json(plan_path, plan)
    generated_files["rebuild_plan"] = str(plan_path)
    artifacts.append(
        ArtifactRef(
            path=str(plan_path),
            kind=ArtifactKind.JSON,
            description="Structured rebuild plan generated from validated function candidates.",
            metadata={"ready": bool(plan.get("ready")), "stage": plan.get("stage")},
        )
    )

    for filename, content in files.items():
        path = rebuild_dir / filename
        path.write_text(content, encoding="utf-8")
        key = filename.rsplit(".", 1)[0].replace("-", "_")
        generated_files[key] = str(path)
        artifacts.append(
            ArtifactRef(
                path=str(path),
                kind=ArtifactKind.REBUILD if filename.endswith(".py") else ArtifactKind.MARKDOWN,
                description=f"Generated rebuild delivery file: {filename}",
                metadata={"filename": filename},
            )
        )

    ready = bool(plan.get("ready"))
    return RebuildResult(
        status=ExecutionStatus.SUCCESS if ready else ExecutionStatus.PARTIAL,
        rebuild_plan=plan,
        generated_files=generated_files,
        artifacts=artifacts,
        next_action="run_replay_demo_or_integrate_scrapy" if ready else "manual_port_or_expand_source_context",
        confidence=ConfidenceLevel.HIGH if ready else ConfidenceLevel.LOW,
    )


def render_sign_rebuild(plan: dict[str, Any]) -> str:
    # Render a standalone pure-Python sign calculator.
    strategy_id = (plan.get("algorithm_strategy") or {}).get("id")
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    sample_output = (plan.get("validation") or {}).get("sample_output") or {}
    sample_keyword = sample_input.get("keyword", "sign")
    sample_timestamp = int(sample_input.get("timestamp") or 1700000000000)
    sample_sign = sample_output.get("sign") or ""
    strategy = plan.get("algorithm_strategy") or {}
    extraction = plan.get("pure_extraction") or {}
    runtime_context = plan.get("runtime_context") or {}
    template = strategy.get("template", "keyword_colon_timestamp")
    salt = strategy.get("salt", "")

    if strategy_id == "fixture_seed_mod100000":
        body = '''FIXTURE_SEED = "reverse-agent-fixture"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    raw = f"{keyword}:{timestamp}:{FIXTURE_SEED}"
    hash_value = sum(ord(char) for char in raw) % 100000
    return f"sig_{hash_value:x}_{timestamp}"
'''
    elif strategy_id == "sig_keyword_timestamp_template":
        body = '''def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return f"sig_{keyword}_{timestamp}"
'''
    elif strategy_id in {"md5_keyword_timestamp", "sha1_keyword_timestamp", "sha256_keyword_timestamp"}:
        algorithm = strategy_id.split("_", 1)[0]
        context_binding = _select_runtime_context_binding(runtime_context, extraction)
        context_constant = f"{context_binding[0]} = {context_binding[1]!r}\n" if context_binding else ""
        context_value_expression = context_binding[0] if context_binding else "SOURCE_SALT"
        body = f'''import hashlib


HASH_ALGORITHM = {algorithm!r}
SOURCE_TEMPLATE = {template!r}
SOURCE_SALT = {salt!r}
{context_constant}
def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_timestamp":
        return f"{{keyword}}{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_colon_timestamp_colon_salt":
        return f"{{keyword}}:{{timestamp}}:{{{context_value_expression}}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return getattr(hashlib, HASH_ALGORITHM)(_message(keyword, timestamp).encode("utf-8")).hexdigest()
'''
    elif strategy_id == "hmac_sha256_keyword_timestamp":
        body = f'''import hashlib
import hmac


HMAC_SECRET = {salt!r}
SOURCE_TEMPLATE = {template!r}


def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return hmac.new(HMAC_SECRET.encode("utf-8"), _message(keyword, timestamp).encode("utf-8"), hashlib.sha256).hexdigest()
'''
    elif strategy_id == "base64_keyword_timestamp":
        context_binding = _select_runtime_context_binding(runtime_context, extraction)
        if extraction.get("context_aware_extractable") and context_binding:
            context_constant = f"{context_binding[0]} = {context_binding[1]!r}\n"
            context_value_expression = context_binding[0]
            body = f'''import base64


SOURCE_TEMPLATE = {template!r}
{context_constant}
def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp_colon_salt":
        return f"{{keyword}}:{{timestamp}}:{{{context_value_expression}}}"
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return base64.b64encode(_message(keyword, timestamp).encode("utf-8")).decode("ascii")
'''
        else:
            body = f'''import base64


SOURCE_TEMPLATE = {template!r}


def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return base64.b64encode(_message(keyword, timestamp).encode("utf-8")).decode("ascii")
'''
    elif strategy_id == "urlencode_keyword_timestamp":
        body = f'''from urllib.parse import quote


SOURCE_TEMPLATE = {template!r}


def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return quote(_message(keyword, timestamp), safe="")
'''
    else:
        body = '''def build_sign(keyword: str, timestamp: int | None = None) -> str:
    raise NotImplementedError("No supported pure-Python rebuild strategy was detected.")
'''

    return f'''from __future__ import annotations

import time

GENERATOR = "reverse_deepagent"
ALGORITHM_STRATEGY = {strategy_id!r}
SAMPLE_KEYWORD = {sample_keyword!r}
SAMPLE_TIMESTAMP = {sample_timestamp!r}
SAMPLE_SIGN = {sample_sign!r}


def current_millis() -> int:
    return int(time.time() * 1000)


{body}

def self_check() -> bool:
    if not SAMPLE_SIGN:
        return True
    return build_sign(SAMPLE_KEYWORD, SAMPLE_TIMESTAMP) == SAMPLE_SIGN


if __name__ == "__main__":
    sign = build_sign(SAMPLE_KEYWORD, SAMPLE_TIMESTAMP)
    print(sign)
    if SAMPLE_SIGN and sign != SAMPLE_SIGN:
        raise SystemExit(f"self-check failed: expected {{SAMPLE_SIGN}}, got {{sign}}")
'''

def render_replay_demo(plan: dict[str, Any]) -> str:
    """Render a standalone urllib-based replay script."""

    replay = plan.get("replay") or {}
    default_base_url = replay.get("base_url") or "http://127.0.0.1:8765"
    default_api_url = replay.get("api_url") or urljoin(default_base_url.rstrip("/") + "/", "/api/search")
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    sample_keyword = sample_input.get("keyword", "sign")
    return f'''from __future__ import annotations

import argparse
import json
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from sign_rebuild import build_sign, current_millis, self_check

DEFAULT_BASE_URL = {default_base_url!r}
DEFAULT_API_URL = {default_api_url!r}
DEFAULT_KEYWORD = {sample_keyword!r}


def replay(base_url: str, keyword: str, timestamp: int | None = None) -> dict:
    if timestamp is None:
        timestamp = current_millis()
    sign = build_sign(keyword, timestamp)
    api_url = urljoin(base_url.rstrip("/") + "/", "/api/search")
    query = urlencode({{"keyword": keyword, "t": timestamp}})
    payload = {{
        "keyword": keyword,
        "timestamp": timestamp,
        "sign": sign,
        "fixture": "reverse-agent-fixture",
    }}
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{{api_url}}?{{query}}",
        data=raw_body,
        method="POST",
        headers={{
            "content-type": "application/json",
            "x-sign": sign,
            "x-fixture": "reverse-agent-fixture",
        }},
    )
    with urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode("utf-8"))
    return {{
        "ok": bool(body.get("ok")) and body.get("headers", {{}}).get("x-sign") == sign,
        "status": getattr(response, "status", None),
        "url": f"{{api_url}}?{{query}}",
        "sign": sign,
        "response": body,
    }}


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the rebuilt sign flow without a browser.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD)
    parser.add_argument("--timestamp", type=int, default=None)
    args = parser.parse_args()
    if not self_check():
        raise SystemExit("sign_rebuild.py self-check failed")
    result = replay(args.base_url, args.keyword, args.timestamp)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_scrapy_middleware(plan: dict[str, Any]) -> str:
    """Render a dependency-light Scrapy middleware sketch."""

    return '''from __future__ import annotations

import json
from urllib.parse import urlencode

from sign_rebuild import build_sign, current_millis


class ReverseSignMiddleware:
    """Scrapy downloader middleware sketch for the rebuilt sign flow.

    Usage:
      DOWNLOADER_MIDDLEWARES = {
          "your_project.middlewares.ReverseSignMiddleware": 543,
      }

    Expected request.meta fields:
      - reverse_keyword: keyword to sign, default "sign"
      - reverse_sign_enabled: set False to skip signing
    """

    def process_request(self, request, spider):  # noqa: D401
        if request.meta.get("reverse_sign_enabled", True) is False:
            return None

        keyword = request.meta.get("reverse_keyword", "sign")
        timestamp = int(request.meta.get("reverse_timestamp") or current_millis())
        sign = build_sign(keyword, timestamp)
        payload = {
            "keyword": keyword,
            "timestamp": timestamp,
            "sign": sign,
            "fixture": "reverse-agent-fixture",
        }
        signed_url = request.url
        if "?" not in signed_url:
            signed_url = f"{signed_url}?{urlencode({'keyword': keyword, 't': timestamp})}"

        return request.replace(
            url=signed_url,
            method="POST",
            headers={
                **request.headers,
                b"content-type": b"application/json",
                b"x-sign": sign.encode("utf-8"),
                b"x-fixture": b"reverse-agent-fixture",
            },
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
'''


def render_not_ready_readme(plan: dict[str, Any]) -> str:
    return "# Rebuild bundle not ready\n\n" + json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _select_runtime_context_binding(runtime_context: dict[str, Any], extraction: dict[str, Any]) -> tuple[str, str, str] | None:
    if not extraction.get("context_aware_extractable") or not isinstance(runtime_context, dict):
        return None
    requirements = [str(item) for item in extraction.get("runtime_context_required", [])]
    if "localStorage" in requirements:
        device_id = _extract_mapping_value(runtime_context.get("localStorage"), "device_id")
        if device_id:
            return ("LOCAL_STORAGE_DEVICE_ID", device_id, "localStorage.device_id")
    if "cookie" in requirements:
        device_id = _extract_cookie_value(runtime_context.get("cookies"), "device_id")
        if device_id:
            return ("COOKIE_DEVICE_ID", device_id, "cookie.device_id")
    if "navigator" in requirements:
        navigator = runtime_context.get("navigator")
        user_agent = _extract_mapping_value(navigator, "userAgent")
        if user_agent:
            return ("NAVIGATOR_USER_AGENT", user_agent, "navigator.userAgent")
    return None


def _extract_mapping_value(value: Any, key: str) -> str | None:
    if isinstance(value, dict):
        item = value.get(key)
        if item is not None:
            return str(item)
    return None


def _extract_cookie_value(value: Any, key: str) -> str | None:
    if isinstance(value, dict):
        direct = value.get(key)
        if direct is not None:
            return str(direct)
        cookie_header = value.get("document.cookie") or value.get("cookie")
        if isinstance(cookie_header, str):
            return _parse_cookie_header(cookie_header).get(key)
    if isinstance(value, str):
        return _parse_cookie_header(value).get(key)
    return None


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, raw_value = part.split("=", 1)
        name = name.strip()
        if not name:
            continue
        parsed[name] = raw_value.strip()
    return parsed


def _find_evidence_details(final_result: FinalResult, source: str) -> dict[str, Any]:
    for item in final_result.evidence:
        if item.source == source:
            return item.details
    return {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _select_best_validation(summary: dict[str, Any], validations: list[dict[str, Any]]) -> dict[str, Any]:
    best_candidate_id = summary.get("best_candidate_id")
    if best_candidate_id:
        for validation in validations:
            if validation.get("candidate_id") == best_candidate_id:
                return validation
    replay_ready = [item for item in validations if (item.get("replay_result") or {}).get("ok")]
    if replay_ready:
        return replay_ready[0]
    return validations[0] if validations else {}


def _match_candidate(best_validation: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_id = best_validation.get("candidate_id")
    if candidate_id:
        for candidate in candidates:
            if candidate.get("candidate_id") == candidate_id:
                return candidate
    function_name = best_validation.get("function_name")
    if function_name:
        for candidate in candidates:
            if candidate.get("function_name") == function_name:
                return candidate
    return candidates[0] if candidates else {}


def _detect_algorithm_strategy(source_context: str) -> dict[str, Any]:
    lowered = source_context.lower()
    if "fixture_seed" in lowered and "charcodeat" in lowered and "100000" in lowered:
        return _strategy(
            "fixture_seed_mod100000",
            supported=True,
            confidence="high",
            description="Sum charCodeAt(keyword:timestamp:FIXTURE_SEED) modulo 100000, then emit sig_<hex>_<timestamp>.",
            dependencies=["python-stdlib"],
            confidence_reason="Detected FIXTURE_SEED, charCodeAt reducer and modulo 100000 in source context.",
        )
    if re.search(r"sig_.*keyword.*timestamp", source_context, flags=re.IGNORECASE | re.DOTALL):
        return _strategy(
            "sig_keyword_timestamp_template",
            supported=True,
            confidence="medium",
            description="Simple template sign of the form sig_<keyword>_<timestamp>.",
            dependencies=["python-stdlib"],
            confidence_reason="Detected sig_ template using keyword and timestamp.",
        )
    crypto_strategy = _detect_crypto_hash_strategy(source_context)
    if crypto_strategy:
        return crypto_strategy
    encoding_strategy = _detect_encoding_strategy(source_context)
    if encoding_strategy:
        return encoding_strategy
    return _strategy(
        "unsupported_manual_port_required",
        supported=False,
        confidence="low",
        description="No safe pure-Python strategy recognized yet; manual port or JS execution backend is required.",
        dependencies=[],
        confidence_reason="No supported hash, hmac, encoding or deterministic template pattern was detected.",
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
        )
    return None


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
) -> dict[str, Any]:
    return {
        "id": strategy_id,
        "supported": supported,
        "confidence": confidence,
        "description": description,
        "dependencies": dependencies,
        "template": template,
        "salt": salt,
        "confidence_reason": confidence_reason,
    }


def _build_pure_extraction(strategy: dict[str, Any], source_context: str, runtime_context: dict[str, Any]) -> dict[str, Any]:
    runtime_context_required = _detect_runtime_context_requirements(source_context)
    pure_extractable = bool(strategy.get("supported")) and not runtime_context_required
    captured_runtime_context = _captured_runtime_context_requirements(runtime_context, runtime_context_required)
    context_aware_extractable = bool(strategy.get("supported")) and bool(runtime_context_required) and set(captured_runtime_context) >= set(runtime_context_required)
    return {
        "pure_extractable": pure_extractable,
        "context_aware_extractable": context_aware_extractable,
        "manual_port_required": not (pure_extractable or context_aware_extractable),
        "runtime_context_required": runtime_context_required,
        "captured_runtime_context": captured_runtime_context,
        "dependencies": strategy.get("dependencies", []),
        "confidence_reason": strategy.get("confidence_reason", ""),
    }


def _captured_runtime_context_requirements(runtime_context: dict[str, Any], requirements: list[str]) -> list[str]:
    if not runtime_context:
        return []
    captured = runtime_context.get("captured_requirements")
    if isinstance(captured, list):
        return [str(item) for item in captured if str(item) in requirements]
    result: list[str] = []
    for requirement in requirements:
        if requirement == "localStorage" and runtime_context.get("localStorage"):
            result.append(requirement)
        elif requirement == "sessionStorage" and runtime_context.get("sessionStorage"):
            result.append(requirement)
        elif requirement == "cookie" and runtime_context.get("cookies"):
            result.append(requirement)
        elif requirement == "navigator" and runtime_context.get("navigator"):
            result.append(requirement)
        elif requirement == "timezone" and "timezoneOffset" in runtime_context:
            result.append(requirement)
    return result


def _detect_runtime_context_requirements(source_context: str) -> list[str]:
    lowered = source_context.lower()
    markers = {
        "cookie": ["document.cookie", "cookie"],
        "localStorage": ["localstorage"],
        "sessionStorage": ["sessionstorage"],
        "navigator": ["navigator.", "useragent", "platform"],
        "timezone": ["timezone", "gettimezoneoffset"],
        "canvas": ["canvas", "todataurl", "getimagedata"],
    }
    requirements: list[str] = []
    for name, needles in markers.items():
        if any(needle in lowered for needle in needles):
            requirements.append(name)
    return requirements


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


def _pick_target_request_url(task_card: TaskCard, candidate: dict[str, Any]) -> str:
    related = candidate.get("related_requests")
    if isinstance(related, list):
        for item in related:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and "/api/" in item["url"]:
                return item["url"]
        for item in related:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
    return task_card.target_url_or_file


def _derive_replay_url(task_card: TaskCard, request_url: str) -> str:
    parsed_request = urlparse(request_url)
    if parsed_request.scheme in {"http", "https"} and parsed_request.netloc:
        if "/api/" in parsed_request.path:
            return urlunparse((parsed_request.scheme, parsed_request.netloc, parsed_request.path, "", "", ""))
        return urljoin(request_url.rstrip("/") + "/", "/api/search")

    parsed_target = urlparse(task_card.target_url_or_file)
    if parsed_target.scheme in {"http", "https"} and parsed_target.netloc:
        return urljoin(task_card.target_url_or_file.rstrip("/") + "/", "/api/search")
    return ""


def _derive_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _build_limitations(strategy: dict[str, Any]) -> list[str]:
    if strategy.get("supported"):
        return [
            "当前脚本只覆盖已验证样本的 sign 纯算与最小 replay。",
            "真实目标若存在 nonce、cookie、设备指纹或服务端会话绑定，需要继续把这些上下文加入 rebuild plan。",
            "Scrapy middleware 是交付草案，需要按目标站点的 request/response 结构接入项目。",
        ]
    return [
        "尚未识别可安全自动移植的纯算算法。",
        "需要继续扩大 source context、做 AST/人工复核，或保留 JS runtime 执行后端。",
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
