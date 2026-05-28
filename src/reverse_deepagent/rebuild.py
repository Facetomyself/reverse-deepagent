from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, ConfidenceLevel, ExecutionStatus, FinalResult, RebuildResult, ReviewHint, TaskCard
from reverse_deepagent.strategies import (
    ALGORITHM_STRATEGY_REGISTRY,
    AlgorithmStrategyRule,
    detect_algorithm_strategy,
    list_algorithm_strategy_registry,
)


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
    validation_ready = _validation_is_ready(best_validation)
    ready = bool(validation_ready and strategy["supported"] and (extraction["pure_extractable"] or extraction["context_aware_extractable"]) and replay_url)
    review_hints = _build_review_hints(
        strategy=strategy,
        extraction=extraction,
        runtime_context=runtime_context,
        validation=best_validation,
        validation_ready=validation_ready,
        replay_url=replay_url,
        ready=ready,
    )

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
        "review_hints": review_hints,
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
SOURCE_SALT = HMAC_SECRET


def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_timestamp":
        return f"{{keyword}}{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_colon_timestamp_colon_salt":
        return f"{{keyword}}:{{timestamp}}:{{SOURCE_SALT}}"
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
SOURCE_SALT = {salt!r}
{context_constant}
def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp_colon_salt":
        return f"{{keyword}}:{{timestamp}}:{{{context_value_expression}}}"
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_timestamp":
        return f"{{keyword}}{{timestamp}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return base64.b64encode(_message(keyword, timestamp).encode("utf-8")).decode("ascii")
'''
        else:
            body = f'''import base64


SOURCE_TEMPLATE = {template!r}
SOURCE_SALT = {salt!r}


def _message(keyword: str, timestamp: int) -> str:
    if SOURCE_TEMPLATE == "keyword_colon_timestamp":
        return f"{{keyword}}:{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_timestamp":
        return f"{{keyword}}{{timestamp}}"
    if SOURCE_TEMPLATE == "keyword_colon_timestamp_colon_salt":
        return f"{{keyword}}:{{timestamp}}:{{SOURCE_SALT}}"
    return f"{{keyword}}:{{timestamp}}"


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = current_millis()
    return base64.b64encode(_message(keyword, timestamp).encode("utf-8")).decode("ascii")
'''
    elif strategy_id == "urlencode_keyword_timestamp":
        context_binding = _select_runtime_context_binding(runtime_context, extraction)
        context_constant = f"{context_binding[0]} = {context_binding[1]!r}\n" if context_binding else ""
        context_value_expression = context_binding[0] if context_binding else "SOURCE_SALT"
        body = f'''from urllib.parse import quote


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
    default_api_path = urlparse(default_api_url).path or "/api/search"
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
DEFAULT_API_PATH = {default_api_path!r}
DEFAULT_KEYWORD = {sample_keyword!r}


def replay(base_url: str, keyword: str, timestamp: int | None = None) -> dict:
    if timestamp is None:
        timestamp = current_millis()
    sign = build_sign(keyword, timestamp)
    api_url = urljoin(base_url.rstrip("/") + "/", DEFAULT_API_PATH.lstrip("/"))
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


def _build_review_hints(
    *,
    strategy: dict[str, Any],
    extraction: dict[str, Any],
    runtime_context: dict[str, Any],
    validation: dict[str, Any],
    validation_ready: bool,
    replay_url: str,
    ready: bool,
) -> list[dict[str, Any]]:
    """Build machine-readable hints for reviewing generated rebuild artifacts."""

    hints: list[dict[str, Any]] = []
    strategy_id = str(strategy.get("id") or "unknown")
    confidence_score = strategy.get("confidence_score") if isinstance(strategy.get("confidence_score"), dict) else {}
    confidence_label = str(confidence_score.get("label") or strategy.get("confidence") or "unknown")
    confidence_value = confidence_score.get("score")

    if validation and not validation_ready:
        hints.append(
            _review_hint(
                severity="risk",
                category="replay",
                code="validation_not_ready",
                message="Runtime validation is incomplete or failed; generated runnable replay artifacts must remain partial.",
                evidence=_validation_not_ready_evidence(validation),
            )
        )

    if extraction.get("pure_extractable"):
        hints.append(
            _review_hint(
                severity="info",
                category="strategy",
                code="pure_strategy_detected",
                message="Supported pure-Python rebuild strategy detected; review generated sign_rebuild.py against the captured sample before reuse.",
                evidence=[
                    f"strategy={strategy_id}",
                    f"confidence={confidence_label}",
                    f"score={confidence_value}",
                    "runtime_context_required=[]",
                ],
            )
        )
    elif extraction.get("context_aware_extractable"):
        required = [str(item) for item in extraction.get("runtime_context_required", [])]
        captured = [str(item) for item in extraction.get("captured_runtime_context", [])]
        hints.append(
            _review_hint(
                severity="warning",
                category="runtime_context",
                code="context_aware_rebuild",
                message="Generated rebuild depends on captured browser/runtime context; verify these values are stable before running at scale.",
                evidence=[
                    f"strategy={strategy_id}",
                    f"runtime_context_required={','.join(required)}",
                    f"captured_runtime_context={','.join(captured)}",
                ],
            )
        )
    else:
        missing = [
            item
            for item in extraction.get("runtime_context_required", [])
            if item not in set(extraction.get("captured_runtime_context", []))
        ]
        caveats = []
        confidence_payload = strategy.get("confidence_score")
        if isinstance(confidence_payload, dict):
            caveats = [str(item) for item in confidence_payload.get("caveats", [])]
        hints.append(
            _review_hint(
                severity="risk",
                category="manual_port",
                code="manual_port_required",
                message="No complete automatic rebuild is available; expand source/runtime evidence or keep a JS runtime backend for this flow.",
                evidence=[
                    f"strategy={strategy_id}",
                    f"supported={bool(strategy.get('supported'))}",
                    f"missing_runtime_context={','.join(str(item) for item in missing)}",
                    *[f"caveat={item}" for item in caveats],
                ],
            )
        )

    replay_result = validation.get("replay_result") if isinstance(validation, dict) else {}
    if replay_result and not replay_result.get("ok"):
        hints.append(
            _review_hint(
                severity="risk" if not ready else "warning",
                category="replay",
                code="sample_replay_not_ok",
                message="Captured replay result was not successful; re-run validation before treating delivery as ready.",
                evidence=[f"replay_result={json.dumps(replay_result, ensure_ascii=False, sort_keys=True)}"],
            )
        )
    if not replay_url:
        hints.append(
            _review_hint(
                severity="risk" if not ready else "warning",
                category="replay",
                code="missing_replay_url",
                message="No concrete replay URL was derived; integrate generated sign code manually into the target request path before delivery.",
                evidence=["replay_url="],
            )
        )
    volatile_keys = runtime_context.get("volatile_keys") if isinstance(runtime_context, dict) else None
    if volatile_keys:
        hints.append(
            _review_hint(
                severity="risk",
                category="runtime_context",
                code="volatile_runtime_context",
                message="Runtime context contains volatile keys; bind them dynamically instead of hard-coding generated constants.",
                evidence=[
                    f"volatile_keys={','.join(str(item) for item in volatile_keys)}",
                    f"runtime_context_required={','.join(str(item) for item in extraction.get('runtime_context_required', []))}",
                    f"captured_runtime_context={','.join(str(item) for item in extraction.get('captured_runtime_context', []))}",
                ],
            )
        )
    return hints


def _review_hint(*, severity: str, category: str, code: str, message: str, evidence: list[str]) -> dict[str, Any]:
    return ReviewHint(
        severity=severity,
        category=category,
        code=code,
        message=message,
        evidence=evidence,
    ).model_dump(mode="json")


def _validation_is_ready(validation: dict[str, Any]) -> bool:
    if not validation or validation.get("validation_status") != "success":
        return False
    checks = validation.get("checks")
    if not isinstance(checks, dict):
        return False
    required_checks = ("source_complete", "runtime_invocation_ok", "sign_shape_ok")
    if not all(checks.get(item) is True for item in required_checks):
        return False
    if checks.get("replay_attempted") is True:
        replay_result = validation.get("replay_result")
        return checks.get("replay_ok") is True and isinstance(replay_result, dict) and replay_result.get("ok") is True
    return True


def _validation_not_ready_evidence(validation: dict[str, Any]) -> list[str]:
    checks = validation.get("checks") if isinstance(validation, dict) else {}
    replay_result = validation.get("replay_result") if isinstance(validation, dict) else {}
    evidence = [f"validation_status={validation.get('validation_status')}"]
    if isinstance(checks, dict):
        for key in ("source_complete", "runtime_invocation_ok", "sign_shape_ok", "replay_attempted", "replay_ok"):
            if key in checks:
                evidence.append(f"check.{key}={checks.get(key)}")
    if isinstance(replay_result, dict) and "ok" in replay_result:
        evidence.append(f"replay_result.ok={replay_result.get('ok')}")
    return evidence


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


def _detect_algorithm_strategy(
    source_context: str,
    registry: tuple[AlgorithmStrategyRule, ...] | None = None,
) -> dict[str, Any]:
    return detect_algorithm_strategy(source_context, registry=registry)


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
