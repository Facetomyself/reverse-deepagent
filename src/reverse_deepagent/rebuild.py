from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, ConfidenceLevel, ExecutionStatus, FinalResult, RebuildResult, ReviewHint, TaskCard
from reverse_deepagent.strategies import (
    ALGORITHM_STRATEGY_REGISTRY,
    AlgorithmStrategyRule,
    detect_algorithm_strategy,
    build_strategy_evidence_score,
    diff_runtime_context_payload,
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
    runtime_context_diff = _runtime_context_diff_for_review(
        runtime_context,
        _find_evidence_details(final_result, "runtime_context_diff"),
    )

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
    evidence_score = build_strategy_evidence_score(
        strategy,
        extraction=extraction,
        runtime_context_diff=runtime_context_diff,
        validation=best_validation,
        validation_ready=validation_ready,
        replay_url=replay_url,
        ready=ready,
    )
    review_hints = _build_review_hints(
        strategy=strategy,
        extraction=extraction,
        runtime_context=runtime_context,
        runtime_context_diff=runtime_context_diff,
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
        "runtime_context_diff": runtime_context_diff,
        "evidence_score": evidence_score,
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
            "scrapy_project": "artifacts/rebuild/scrapy_project/",
            "scrapy_export_manifest": "artifacts/rebuild/scrapy_export_manifest.json",
        },
        "runtime_assisted": _build_runtime_assisted_plan(strategy),
        "limitations": _build_limitations(strategy),
        "review_hints": review_hints,
    }

    files: dict[str, str] = {}
    if ready:
        files["sign_rebuild.py"] = render_sign_rebuild(plan)
        files["replay_demo.py"] = render_replay_demo(plan)
        files["scrapy_middleware.py"] = render_scrapy_middleware(plan)
        files.update(render_scrapy_project(plan))
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        key = _generated_file_key(filename)
        generated_files[key] = str(path)
        artifacts.append(
            ArtifactRef(
                path=str(path),
                kind=_artifact_kind_for_generated_file(filename),
                description=f"Generated rebuild delivery file: {filename}",
                metadata={"filename": filename},
            )
        )
    scrapy_project_dir = rebuild_dir / "scrapy_project"
    if scrapy_project_dir.exists():
        generated_files["scrapy_project"] = str(scrapy_project_dir)


    ready = bool(plan.get("ready"))
    return RebuildResult(
        status=ExecutionStatus.SUCCESS if ready else ExecutionStatus.PARTIAL,
        rebuild_plan=plan,
        generated_files=generated_files,
        artifacts=artifacts,
        next_action="run_replay_demo_or_integrate_scrapy" if ready else "manual_port_or_expand_source_context",
        confidence=ConfidenceLevel.HIGH if ready else ConfidenceLevel.LOW,
    )


def _generated_file_key(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    return stem.replace("/", "_").replace("-", "_")


def _artifact_kind_for_generated_file(filename: str) -> ArtifactKind:
    suffix = Path(filename).suffix.lower()
    if suffix == ".py":
        return ArtifactKind.REBUILD
    if suffix == ".json":
        return ArtifactKind.JSON
    if suffix in {".md", ".markdown"}:
        return ArtifactKind.MARKDOWN
    return ArtifactKind.OTHER


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
    elif strategy_id in {"md5_keyword_timestamp", "sha1_keyword_timestamp", "sha256_keyword_timestamp", "sha512_keyword_timestamp"}:
        algorithm = strategy_id.split("_", 1)[0]
        context_bindings = _select_runtime_context_bindings(runtime_context, extraction)
        context_constant, context_value_expression = _render_runtime_context_binding_block(context_bindings, fallback="SOURCE_SALT")
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
    elif strategy_id in {
        "hmac_md5_keyword_timestamp",
        "hmac_sha1_keyword_timestamp",
        "hmac_sha256_keyword_timestamp",
        "hmac_sha512_keyword_timestamp",
    }:
        hmac_algorithm = str(strategy_id).removeprefix("hmac_").split("_keyword_timestamp", 1)[0]
        context_bindings = _select_runtime_context_bindings(runtime_context, extraction)
        context_constant, context_value_expression = _render_runtime_context_binding_block(context_bindings, fallback="HMAC_SECRET")
        body = f'''import hashlib
import hmac


HMAC_SECRET = {salt!r}
HMAC_ALGORITHM = {hmac_algorithm!r}
SOURCE_TEMPLATE = {template!r}
SOURCE_SALT = HMAC_SECRET
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
    return hmac.new(HMAC_SECRET.encode("utf-8"), _message(keyword, timestamp).encode("utf-8"), getattr(hashlib, HMAC_ALGORITHM)).hexdigest()
'''
    elif strategy_id == "base64_keyword_timestamp":
        context_bindings = _select_runtime_context_bindings(runtime_context, extraction)
        if extraction.get("context_aware_extractable") and context_bindings:
            context_constant, context_value_expression = _render_runtime_context_binding_block(context_bindings, fallback="SOURCE_SALT")
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
        context_bindings = _select_runtime_context_bindings(runtime_context, extraction)
        context_constant, context_value_expression = _render_runtime_context_binding_block(context_bindings, fallback="SOURCE_SALT")
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
    """Render a dependency-light Scrapy downloader middleware."""

    replay = plan.get("replay") or {}
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    default_keyword = sample_input.get("keyword", "sign")
    default_api_url = replay.get("api_url") or "http://127.0.0.1:8765/api/search"
    default_api_path = urlparse(default_api_url).path or "/api/search"
    return f'''from __future__ import annotations

import json
from urllib.parse import urlencode, urljoin

from sign_rebuild import build_sign, current_millis

DEFAULT_KEYWORD = {default_keyword!r}
DEFAULT_API_PATH = {default_api_path!r}


class ReverseSignMiddleware:
    """Scrapy downloader middleware for the rebuilt sign flow.

    Usage:
      DOWNLOADER_MIDDLEWARES = {{
          "your_project.middlewares.ReverseSignMiddleware": 543,
      }}

    Expected request.meta fields:
      - reverse_keyword: keyword to sign, default DEFAULT_KEYWORD
      - reverse_timestamp: optional fixed timestamp for deterministic replay
      - reverse_base_url: optional base URL when request.url is only a seed URL
      - reverse_sign_enabled: set False to skip signing
    """

    def process_request(self, request, spider=None):  # noqa: D401
        if request.meta.get("reverse_sign_enabled", True) is False or request.meta.get("reverse_signed") is True:
            return None

        keyword = request.meta.get("reverse_keyword", DEFAULT_KEYWORD)
        timestamp = int(request.meta.get("reverse_timestamp") or current_millis())
        sign = build_sign(keyword, timestamp)
        payload = {{
            "keyword": keyword,
            "timestamp": timestamp,
            "sign": sign,
            "fixture": "reverse-agent-fixture",
        }}
        base_url = request.meta.get("reverse_base_url")
        signed_url = request.url if not base_url else urljoin(str(base_url).rstrip("/") + "/", DEFAULT_API_PATH.lstrip("/"))
        if "?" not in signed_url:
            signed_url = f"{{signed_url}}?{{urlencode({{'keyword': keyword, 't': timestamp}})}}"

        signed = request.replace(
            url=signed_url,
            method="POST",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        signed.headers[b"content-type"] = b"application/json"
        signed.headers[b"x-sign"] = sign.encode("utf-8")
        signed.headers[b"x-fixture"] = b"reverse-agent-fixture"
        signed.meta["reverse_signed"] = True
        return signed
'''


def render_scrapy_project(plan: dict[str, Any]) -> dict[str, str]:
    """Render a runnable Scrapy project around the rebuilt sign flow."""

    return {
        "scrapy_export_manifest.json": render_scrapy_export_manifest(plan),
        "scrapy_project/scrapy.cfg": render_scrapy_cfg(),
        "scrapy_project/README.md": render_scrapy_project_readme(plan),
        "scrapy_project/runner.py": render_scrapy_runner(),
        "scrapy_project/reverse_sign_project/__init__.py": "",
        "scrapy_project/reverse_sign_project/items.py": render_scrapy_items(),
        "scrapy_project/reverse_sign_project/middlewares.py": render_scrapy_project_middleware(plan),
        "scrapy_project/reverse_sign_project/settings.py": render_scrapy_settings(plan),
        "scrapy_project/reverse_sign_project/sign_adapter.py": render_scrapy_sign_adapter(),
        "scrapy_project/reverse_sign_project/spiders/__init__.py": "",
        "scrapy_project/reverse_sign_project/spiders/replay_spider.py": render_scrapy_replay_spider(plan),
    }


def render_scrapy_export_manifest(plan: dict[str, Any]) -> str:
    replay = plan.get("replay") or {}
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    payload = {
        "schema_version": 1,
        "kind": "scrapy-export",
        "status": "ready" if plan.get("ready") else "partial",
        "project_root": "rebuild/scrapy_project",
        "settings_module": "reverse_sign_project.settings",
        "spider": "reverse_sign_replay",
        "middleware": "reverse_sign_project.middlewares.ReverseSignMiddleware",
        "commands": [
            "cd rebuild/scrapy_project && scrapy crawl reverse_sign_replay",
            "cd rebuild/scrapy_project && python runner.py --base-url <target-base-url> --output result.json",
        ],
        "default_base_url": replay.get("base_url"),
        "default_api_url": replay.get("api_url"),
        "default_keyword": sample_input.get("keyword", "sign"),
        "generated_files": [
            "scrapy.cfg",
            "runner.py",
            "reverse_sign_project/settings.py",
            "reverse_sign_project/middlewares.py",
            "reverse_sign_project/spiders/replay_spider.py",
            "reverse_sign_project/sign_adapter.py",
        ],
        "notes": [
            "Install with the optional extra: pip install reverse-deepagent[scrapy] or install scrapy in this environment.",
            "The project imports ../sign_rebuild.py through reverse_sign_project.sign_adapter, so keep the generated Scrapy project next to sign_rebuild.py.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_scrapy_cfg() -> str:
    return '''[settings]
default = reverse_sign_project.settings

[deploy]
project = reverse_sign_project
'''


def render_scrapy_settings(plan: dict[str, Any]) -> str:
    replay = plan.get("replay") or {}
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    default_base_url = replay.get("base_url") or "http://127.0.0.1:8765"
    default_api_url = replay.get("api_url") or urljoin(default_base_url.rstrip("/") + "/", "/api/search")
    default_api_path = urlparse(default_api_url).path or "/api/search"
    default_keyword = sample_input.get("keyword", "sign")
    return f'''BOT_NAME = "reverse_sign_project"

SPIDER_MODULES = ["reverse_sign_project.spiders"]
NEWSPIDER_MODULE = "reverse_sign_project.spiders"

ROBOTSTXT_OBEY = False
LOG_LEVEL = "INFO"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

DOWNLOADER_MIDDLEWARES = {{
    "reverse_sign_project.middlewares.ReverseSignMiddleware": 543,
}}

REVERSE_SIGN_DEFAULT_BASE_URL = {default_base_url!r}
REVERSE_SIGN_DEFAULT_API_PATH = {default_api_path!r}
REVERSE_SIGN_DEFAULT_KEYWORD = {default_keyword!r}
'''


def render_scrapy_sign_adapter() -> str:
    return '''from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_sign_module() -> ModuleType:
    sign_path = Path(__file__).resolve().parents[2] / "sign_rebuild.py"
    spec = importlib.util.spec_from_file_location("reverse_generated_sign_rebuild", sign_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import generated sign_rebuild.py from {sign_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SIGN_MODULE = _load_sign_module()


def build_sign(keyword: str, timestamp: int | None = None) -> str:
    return str(_SIGN_MODULE.build_sign(keyword, timestamp))


def current_millis() -> int:
    return int(_SIGN_MODULE.current_millis())


def self_check() -> bool:
    checker: Any = getattr(_SIGN_MODULE, "self_check", None)
    return True if checker is None else bool(checker())
'''


def render_scrapy_project_middleware(plan: dict[str, Any]) -> str:
    replay = plan.get("replay") or {}
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    default_keyword = sample_input.get("keyword", "sign")
    default_api_url = replay.get("api_url") or "http://127.0.0.1:8765/api/search"
    default_api_path = urlparse(default_api_url).path or "/api/search"
    return f'''from __future__ import annotations

import json
from urllib.parse import urlencode, urljoin

from .sign_adapter import build_sign, current_millis

DEFAULT_KEYWORD = {default_keyword!r}
DEFAULT_API_PATH = {default_api_path!r}


class ReverseSignMiddleware:
    """Downloader middleware that signs target replay requests."""

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            default_keyword=crawler.settings.get("REVERSE_SIGN_DEFAULT_KEYWORD", DEFAULT_KEYWORD),
            default_api_path=crawler.settings.get("REVERSE_SIGN_DEFAULT_API_PATH", DEFAULT_API_PATH),
        )

    def __init__(self, default_keyword: str = DEFAULT_KEYWORD, default_api_path: str = DEFAULT_API_PATH) -> None:
        self.default_keyword = default_keyword
        self.default_api_path = default_api_path

    def process_request(self, request, spider=None):  # noqa: D401
        if request.meta.get("reverse_sign_enabled", True) is False or request.meta.get("reverse_signed") is True:
            return None
        keyword = request.meta.get("reverse_keyword", self.default_keyword)
        timestamp = int(request.meta.get("reverse_timestamp") or current_millis())
        sign = build_sign(keyword, timestamp)
        payload = {{
            "keyword": keyword,
            "timestamp": timestamp,
            "sign": sign,
            "fixture": "reverse-agent-fixture",
        }}
        base_url = request.meta.get("reverse_base_url")
        signed_url = request.url if not base_url else urljoin(str(base_url).rstrip("/") + "/", self.default_api_path.lstrip("/"))
        if "?" not in signed_url:
            signed_url = f"{{signed_url}}?{{urlencode({{'keyword': keyword, 't': timestamp}})}}"
        signed = request.replace(
            url=signed_url,
            method="POST",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        signed.headers[b"content-type"] = b"application/json"
        signed.headers[b"x-sign"] = sign.encode("utf-8")
        signed.headers[b"x-fixture"] = b"reverse-agent-fixture"
        signed.meta["reverse_signed"] = True
        return signed
'''


def render_scrapy_replay_spider(plan: dict[str, Any]) -> str:
    replay = plan.get("replay") or {}
    sample_input = (plan.get("validation") or {}).get("sample_input") or {}
    default_base_url = replay.get("base_url") or "http://127.0.0.1:8765"
    default_keyword = sample_input.get("keyword", "sign")
    return f'''from __future__ import annotations

import json
from typing import Any

try:
    import scrapy
except ImportError:  # pragma: no cover - importable without optional dependency
    scrapy = None


BaseSpider = scrapy.Spider if scrapy is not None else object


class ReverseSignReplaySpider(BaseSpider):
    name = "reverse_sign_replay"
    custom_settings = {{
        "DOWNLOADER_MIDDLEWARES": {{"reverse_sign_project.middlewares.ReverseSignMiddleware": 543}},
    }}

    def __init__(self, base_url: str = {default_base_url!r}, keyword: str = {default_keyword!r}, timestamp: str | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = base_url
        self.keyword = keyword
        self.timestamp = int(timestamp) if timestamp else None

    def _start_request(self):
        if scrapy is None:
            raise RuntimeError("Scrapy is not installed. Install with: pip install reverse-deepagent[scrapy]")
        return scrapy.Request(
            self.base_url,
            callback=self.parse,
            dont_filter=True,
            meta={{
                "reverse_base_url": self.base_url,
                "reverse_keyword": self.keyword,
                "reverse_timestamp": self.timestamp,
            }},
        )

    async def start(self):
        yield self._start_request()

    def start_requests(self):
        yield self._start_request()

    def parse(self, response):
        try:
            body = json.loads(response.text)
        except Exception:
            body = {{"raw": response.text}}
        yield {{
            "ok": bool(body.get("ok")) if isinstance(body, dict) else False,
            "status": response.status,
            "url": response.url,
            "body": body,
        }}
'''


def render_scrapy_items() -> str:
    return '''from __future__ import annotations

try:
    import scrapy
except ImportError:  # pragma: no cover - importable without optional dependency
    scrapy = None


if scrapy is not None:
    class ReverseReplayItem(scrapy.Item):
        ok = scrapy.Field()
        status = scrapy.Field()
        url = scrapy.Field()
        body = scrapy.Field()
else:
    class ReverseReplayItem(dict):
        pass
'''


def render_scrapy_runner() -> str:
    return '''from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run generated Scrapy replay spider.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--output", default=None, help="Optional feed output path passed to Scrapy -O.")
    args = parser.parse_args()
    try:
        from scrapy.cmdline import execute
    except ImportError as exc:
        raise SystemExit("Scrapy is not installed. Install with: pip install reverse-deepagent[scrapy]") from exc

    command = ["scrapy", "crawl", "reverse_sign_replay"]
    if args.base_url:
        command.extend(["-a", f"base_url={args.base_url}"])
    if args.keyword:
        command.extend(["-a", f"keyword={args.keyword}"])
    if args.timestamp:
        command.extend(["-a", f"timestamp={args.timestamp}"])
    if args.output:
        command.extend(["-O", args.output])
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    execute(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def render_scrapy_project_readme(plan: dict[str, Any]) -> str:
    replay = plan.get("replay") or {}
    default_base_url = replay.get("base_url") or "http://127.0.0.1:8765"
    return f'''# Generated Scrapy Replay Project

This directory is a runnable Scrapy project generated by `reverse_deepagent`.
It reuses `../sign_rebuild.py` through `reverse_sign_project.sign_adapter` and signs outgoing replay requests in `ReverseSignMiddleware`.

## Install

```bash
pip install reverse-deepagent[scrapy]
# or install Scrapy manually in the current environment
pip install scrapy
```

## Run

```bash
cd "rebuild/scrapy_project"
scrapy crawl reverse_sign_replay -a base_url={default_base_url!r}
```

You can also use the thin runner:

```bash
python runner.py --base-url {default_base_url!r} --output result.json
```

## Files

- `scrapy.cfg`: Scrapy settings entrypoint.
- `reverse_sign_project/settings.py`: generated project settings and middleware registration.
- `reverse_sign_project/middlewares.py`: signs request URL, headers and JSON body.
- `reverse_sign_project/spiders/replay_spider.py`: minimal replay spider.
- `reverse_sign_project/sign_adapter.py`: imports the sibling `../sign_rebuild.py`.
'''


def render_not_ready_readme(plan: dict[str, Any]) -> str:
    strategy = plan.get("algorithm_strategy") if isinstance(plan.get("algorithm_strategy"), dict) else {}
    runtime_assisted = plan.get("runtime_assisted") if isinstance(plan.get("runtime_assisted"), dict) else {}
    if str(strategy.get("id", "")).startswith("triage_"):
        lines = [
            "# Runtime-assisted triage required",
            "",
            "The captured flow contains WASM / VM / obfuscation / anti-debug or dynamic-secret indicators.",
            "No pure-Python rebuild files were generated because the portable algorithm is not proven yet.",
            "",
            "Recommended next actions:",
        ]
        for action in runtime_assisted.get("recommended_actions", []):
            lines.append(f"- {action}")
        triage_hook_plan = runtime_assisted.get("triage_hook_plan") if isinstance(runtime_assisted.get("triage_hook_plan"), dict) else {}
        if triage_hook_plan:
            lines.extend(["", "Plan-only hook/debugger candidates:"])
            for item in triage_hook_plan.get("hook_plans", []):
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {item.get('plan_id')}: {item.get('target')} -> {item.get('recommended_subagent')}")
            artifacts = [str(item.get("artifact_key")) for item in triage_hook_plan.get("runtime_artifacts", []) if isinstance(item, dict) and item.get("artifact_key")]
            if artifacts:
                lines.extend(["", "Planned artifacts:"])
                lines.extend([f"- {artifact}" for artifact in artifacts])
        lines.extend(["", "Full machine-readable plan:", "", "```json", json.dumps(plan, ensure_ascii=False, indent=2), "```", ""])
        return "\n".join(lines)
    return "# Rebuild bundle not ready\n\n" + json.dumps(plan, ensure_ascii=False, indent=2) + "\n"


def _build_review_hints(
    *,
    strategy: dict[str, Any],
    extraction: dict[str, Any],
    runtime_context: dict[str, Any],
    runtime_context_diff: dict[str, Any],
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
        binding_sources = [str(item.get("source")) for item in extraction.get("runtime_context_bindings", []) if isinstance(item, dict) and item.get("source")]
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
                    f"runtime_context_bindings={','.join(binding_sources)}",
                ],
            )
        )
    else:
        missing = [
            item
            for item in extraction.get("runtime_context_required", [])
            if item not in set(extraction.get("captured_runtime_context", []))
        ]
        missing_bindings: list[str] = []
        if extraction.get("runtime_context_binding_required") and not extraction.get("runtime_context_binding"):
            missing_bindings = [str(item) for item in extraction.get("missing_runtime_context_bindings", [])]
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
                    f"missing_runtime_context_binding={','.join(missing_bindings)}",
                    f"multiple_runtime_context_bindings_unsupported={bool(extraction.get('multiple_runtime_context_bindings_unsupported'))}",
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
    hints.extend(
        _runtime_context_diff_review_hints(
            runtime_context_diff,
            extraction=extraction,
        )
    )
    return hints


def _runtime_context_diff_for_review(runtime_context: dict[str, Any], runtime_context_diff: dict[str, Any]) -> dict[str, Any]:
    if isinstance(runtime_context_diff, dict) and runtime_context_diff:
        return runtime_context_diff
    if isinstance(runtime_context, dict) and runtime_context:
        return diff_runtime_context_payload(runtime_context)
    return {}


def _runtime_context_diff_review_hints(runtime_context_diff: dict[str, Any], *, extraction: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(runtime_context_diff, dict) or not runtime_context_diff:
        return []
    fields = [field for field in runtime_context_diff.get("fields", []) if isinstance(field, dict)]
    summary = runtime_context_diff.get("summary") if isinstance(runtime_context_diff.get("summary"), dict) else {}
    required = ",".join(str(item) for item in extraction.get("runtime_context_required", []))
    captured = ",".join(str(item) for item in extraction.get("captured_runtime_context", []))
    hints: list[dict[str, Any]] = []

    volatile_paths = _runtime_context_field_paths(fields, "volatile") or [str(item) for item in runtime_context_diff.get("volatile_keys", [])]
    if volatile_paths:
        hints.append(
            _review_hint(
                severity="risk",
                category="runtime_context",
                code="volatile_runtime_context",
                message="Runtime context contains volatile keys; bind them dynamically instead of hard-coding generated constants.",
                evidence=[
                    f"volatile_keys={','.join(volatile_paths)}",
                    f"volatile_field_count={summary.get('volatile_field_count', len(volatile_paths))}",
                    f"runtime_context_required={required}",
                    f"captured_runtime_context={captured}",
                ],
            )
        )

    session_bound_paths = _runtime_context_field_paths(fields, "session_bound")
    if session_bound_paths:
        hints.append(
            _review_hint(
                severity="warning",
                category="runtime_context",
                code="session_bound_runtime_context",
                message="Runtime context contains session-bound values; generated constants should be treated as fixture defaults, not reusable secrets.",
                evidence=[
                    f"session_bound_keys={','.join(session_bound_paths)}",
                    f"session_bound_field_count={summary.get('session_bound_field_count', len(session_bound_paths))}",
                    f"secret_like_field_count={summary.get('secret_like_field_count', 0)}",
                ],
            )
        )

    missing_paths = _runtime_context_field_paths(fields, "missing_in_some_samples")
    missing_requirements = [str(item) for item in runtime_context_diff.get("missing_requirements", [])]
    if missing_paths or missing_requirements:
        hints.append(
            _review_hint(
                severity="risk",
                category="runtime_context",
                code="missing_runtime_context_field",
                message="Runtime context diff shows missing fields or requirements; collect more samples before treating generated rebuild artifacts as stable.",
                evidence=[
                    f"missing_keys={','.join(missing_paths)}",
                    f"missing_requirements={','.join(missing_requirements)}",
                    f"missing_field_count={summary.get('missing_field_count', len(missing_paths))}",
                    f"missing_requirement_count={summary.get('missing_requirement_count', len(missing_requirements))}",
                ],
            )
        )

    type_drift_paths = _runtime_context_field_paths(fields, "type_drift")
    if type_drift_paths:
        hints.append(
            _review_hint(
                severity="risk",
                category="runtime_context",
                code="runtime_context_type_drift",
                message="Runtime context values changed type across samples; normalize inputs or keep this rebuild runtime-assisted.",
                evidence=[
                    f"type_drift_keys={','.join(type_drift_paths)}",
                    f"type_drift_field_count={summary.get('type_drift_field_count', len(type_drift_paths))}",
                ],
            )
        )

    object_drift_paths = _runtime_context_field_paths(fields, "object_drift")
    if object_drift_paths:
        hints.append(
            _review_hint(
                severity="warning",
                category="runtime_context",
                code="runtime_context_object_drift",
                message="Runtime context object or array shape changed across samples; review nested shape before reusing generated constants.",
                evidence=[
                    f"object_drift_keys={','.join(object_drift_paths)}",
                    f"object_drift_field_count={summary.get('object_drift_field_count', len(object_drift_paths))}",
                ],
            )
        )
    return hints


def _runtime_context_field_paths(fields: list[dict[str, Any]], classification: str) -> list[str]:
    paths = [str(field.get("path")) for field in fields if field.get("classification") == classification and field.get("path")]
    return sorted(dict.fromkeys(paths))


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
    binding = extraction.get("runtime_context_binding")
    if isinstance(binding, dict) and binding.get("constant") and binding.get("value") is not None and binding.get("source"):
        return (str(binding["constant"]), str(binding["value"]), str(binding["source"]))
    requirements = [str(item) for item in extraction.get("runtime_context_required", [])]
    if "localStorage" in requirements:
        device_id = _extract_mapping_value(runtime_context.get("localStorage"), "device_id")
        if device_id:
            return ("LOCAL_STORAGE_DEVICE_ID", device_id, "localStorage.device_id")
    if "sessionStorage" in requirements:
        session_id = _first_mapping_value(runtime_context.get("sessionStorage"), ("session_id", "sessionId", "token", "nonce"))
        if session_id:
            return ("SESSION_STORAGE_VALUE", session_id[1], f"sessionStorage.{session_id[0]}")
    if "cookie" in requirements:
        device_id = _extract_cookie_value(runtime_context.get("cookies"), "device_id")
        if device_id:
            return ("COOKIE_DEVICE_ID", device_id, "cookie.device_id")
    if "navigator" in requirements:
        navigator = runtime_context.get("navigator")
        user_agent = _extract_mapping_value(navigator, "userAgent")
        if user_agent:
            return ("NAVIGATOR_USER_AGENT", user_agent, "navigator.userAgent")
    if "timezone" in requirements and "timezoneOffset" in runtime_context:
        return ("TIMEZONE_OFFSET", str(runtime_context.get("timezoneOffset")), "timezone.timezoneOffset")
    return None


def _select_runtime_context_bindings(runtime_context: dict[str, Any], extraction: dict[str, Any]) -> list[tuple[str, str, str]]:
    if not extraction.get("context_aware_extractable") or not isinstance(runtime_context, dict):
        return []
    bindings = extraction.get("runtime_context_bindings")
    if isinstance(bindings, list) and bindings and not extraction.get("missing_runtime_context_bindings"):
        normalized: list[tuple[str, str, str]] = []
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            constant = binding.get("constant")
            value = binding.get("value")
            source = binding.get("source")
            if constant and value is not None and source:
                normalized.append((str(constant), str(value), str(source)))
        if len(normalized) == len(bindings):
            return normalized
    single = _select_runtime_context_binding(runtime_context, extraction)
    return [single] if single else []


def _render_runtime_context_binding_block(bindings: list[tuple[str, str, str]], *, fallback: str) -> tuple[str, str]:
    if not bindings:
        return "", fallback
    lines: list[str] = []
    constants: list[str] = []
    for constant, value, _source in bindings:
        lines.append(f"{constant} = {value!r}")
        constants.append(constant)
    if len(constants) == 1:
        return "\n".join(lines) + "\n", constants[0]
    lines.append(f"RUNTIME_CONTEXT_VALUES = ({', '.join(constants)},)")
    lines.append("RUNTIME_CONTEXT_SUFFIX = ':'.join(RUNTIME_CONTEXT_VALUES)")
    return "\n".join(lines) + "\n", "RUNTIME_CONTEXT_SUFFIX"


def _first_mapping_value(value: Any, keys: tuple[str, ...]) -> tuple[str, str] | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        item = value.get(key)
        if item is not None:
            return (key, str(item))
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
    runtime_context_required = _merge_requirements(
        _detect_runtime_context_requirements(source_context),
        [str(item) for item in strategy.get("runtime_context_required", []) if item],
    )
    pure_extractable = bool(strategy.get("supported")) and not runtime_context_required
    captured_runtime_context = _captured_runtime_context_requirements(runtime_context, runtime_context_required)
    binding_candidates = _runtime_context_binding_candidates(source_context)
    runtime_context_bindings: list[dict[str, str]] = []
    missing_runtime_context_bindings = [source for source, _key in binding_candidates]
    family_context_captured = bool(runtime_context_required) and set(captured_runtime_context) >= set(runtime_context_required)
    if bool(strategy.get("supported")) and family_context_captured:
        runtime_context_bindings, missing_runtime_context_bindings = _resolve_runtime_context_bindings(
            binding_candidates,
            runtime_context,
            runtime_context_required,
        )
    bindings_complete = bool(binding_candidates) and not missing_runtime_context_bindings and len(runtime_context_bindings) == len(binding_candidates)
    runtime_context_binding = runtime_context_bindings[0] if len(runtime_context_bindings) == 1 and bindings_complete else None
    context_aware_extractable = bool(strategy.get("supported")) and family_context_captured and bindings_complete
    return {
        "pure_extractable": pure_extractable,
        "context_aware_extractable": context_aware_extractable,
        "manual_port_required": not (pure_extractable or context_aware_extractable),
        "runtime_context_required": runtime_context_required,
        "captured_runtime_context": captured_runtime_context,
        "runtime_context_binding": runtime_context_binding,
        "runtime_context_bindings": runtime_context_bindings,
        "missing_runtime_context_bindings": missing_runtime_context_bindings,
        "runtime_context_binding_required": bool(binding_candidates),
        "runtime_context_binding_candidates": [source for source, _key in binding_candidates],
        "multiple_runtime_context_bindings_unsupported": len(binding_candidates) > 1 and not bindings_complete,
        "dependencies": strategy.get("dependencies", []),
        "confidence_reason": strategy.get("confidence_reason", ""),
    }


def _merge_requirements(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item not in merged:
                merged.append(item)
    return merged


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


def _resolve_runtime_context_bindings(
    candidates: list[tuple[str, str]],
    runtime_context: dict[str, Any],
    requirements: list[str],
) -> tuple[list[dict[str, str]], list[str]]:
    resolved: list[dict[str, str]] = []
    missing: list[str] = []
    if not isinstance(runtime_context, dict):
        return resolved, [source for source, _key in candidates]
    for source, key in candidates:
        value = _resolve_runtime_context_value(source, key, runtime_context, requirements)
        if value is None:
            missing.append(source)
            continue
        resolved.append(
            {
                "source": source,
                "key": key,
                "constant": _runtime_context_constant_name(source),
                "value": value,
            }
        )
    return resolved, missing


def _resolve_runtime_context_value(source: str, key: str, runtime_context: dict[str, Any], requirements: list[str]) -> str | None:
    family = source.split(".", 1)[0]
    if family == "localStorage" and "localStorage" in requirements:
        return _extract_mapping_value(runtime_context.get("localStorage"), key)
    if family == "sessionStorage" and "sessionStorage" in requirements:
        return _extract_mapping_value(runtime_context.get("sessionStorage"), key)
    if family == "cookie" and "cookie" in requirements:
        return _extract_cookie_value(runtime_context.get("cookies"), key)
    if family == "navigator" and "navigator" in requirements:
        return _extract_mapping_value(runtime_context.get("navigator"), key)
    if family == "timezone" and "timezone" in requirements and key == "timezoneOffset":
        return str(runtime_context.get("timezoneOffset")) if "timezoneOffset" in runtime_context else None
    return None


def _runtime_context_binding_candidates(source_context: str) -> list[tuple[str, str]]:
    patterns: tuple[tuple[str, str], ...] = (
        ("localStorage", r"(?<![\w$])localStorage\??\.getItem\(\s*['\"`]([^'\"`]+)['\"`]\s*\)"),
        ("localStorage", r"(?<![\w$])localStorage\??\[['\"`]([^'\"`]+)['\"`]\]"),
        ("localStorage", r"(?<![\w$])localStorage\.(?!(?:getItem|setItem|removeItem|clear|key|length)\b)([A-Za-z_$][\w$]*)"),
        ("sessionStorage", r"(?<![\w$])sessionStorage\??\.getItem\(\s*['\"`]([^'\"`]+)['\"`]\s*\)"),
        ("sessionStorage", r"(?<![\w$])sessionStorage\??\[['\"`]([^'\"`]+)['\"`]\]"),
        ("sessionStorage", r"(?<![\w$])sessionStorage\.(?!(?:getItem|setItem|removeItem|clear|key|length)\b)([A-Za-z_$][\w$]*)"),
        ("navigator", r"(?<![\w$])navigator\??\.(userAgent|platform|language|languages|vendor|hardwareConcurrency)"),
    )
    candidates: list[tuple[str, str]] = []
    for family, pattern in patterns:
        for match in re.finditer(pattern, source_context, flags=re.IGNORECASE):
            key = match.group(1)
            candidates.append((f"{family}.{key}", key))
    for key in _extract_cookie_names(source_context):
        candidates.append((f"cookie.{key}", key))
    if "gettimezoneoffset" in source_context.lower() or "timezoneoffset" in source_context.lower():
        candidates.append(("timezone.timezoneOffset", "timezoneOffset"))
    return _dedupe_binding_candidates(candidates)


def _extract_cookie_names(source_context: str) -> list[str]:
    names: list[str] = []
    cookie_patterns = (
        r"(?<![\w$])document\.cookie\.match\(\s*/[^/]*?([A-Za-z0-9_$.-]+)=",
        r"(?<![\w$])document\.cookie[^;\n]+?['\"`]([A-Za-z0-9_$.-]+)=",
        r"(?<![\w$])document\.cookie[\s\S]{0,240}?(?:startsWith|includes)\(\s*['\"`]([A-Za-z0-9_$.-]+)=",
    )
    for pattern in cookie_patterns:
        for match in re.finditer(pattern, source_context, flags=re.IGNORECASE | re.DOTALL):
            name = match.group(1)
            if name:
                names.append(name.replace("\\", ""))
    return _dedupe_strings(names)


def _runtime_context_constant_name(source: str) -> str:
    family, _separator, key = source.partition(".")
    family_prefixes = {
        "localStorage": "LOCAL_STORAGE",
        "sessionStorage": "SESSION_STORAGE",
        "cookie": "COOKIE",
        "navigator": "NAVIGATOR",
        "timezone": "TIMEZONE",
    }
    prefix = family_prefixes.get(family)
    if prefix and key:
        key_token = _constant_token(key)
        if key_token == prefix or key_token.startswith(f"{prefix}_"):
            return key_token
        return f"{prefix}_{key_token}"
    return _constant_token(source) or "RUNTIME_CONTEXT_VALUE"


def _constant_token(value: str) -> str:
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^A-Z0-9]+", "_", snake.upper()).strip("_")


def _dedupe_binding_candidates(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    output: list[tuple[str, str]] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        output.append(candidate)
    return output


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _detect_runtime_context_requirements(source_context: str) -> list[str]:
    lowered = source_context.lower()
    markers = {
        "cookie": ["document.cookie", "cookie"],
        "localStorage": ["localstorage"],
        "sessionStorage": ["sessionstorage"],
        "navigator": ["navigator.", "useragent", "platform"],
        "timezone": ["timezoneoffset", "gettimezoneoffset"],
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


def _build_runtime_assisted_plan(strategy: dict[str, Any]) -> dict[str, Any]:
    if not str(strategy.get("id", "")).startswith("triage_"):
        return {}
    replay_plan = strategy.get("runtime_replay_plan") if isinstance(strategy.get("runtime_replay_plan"), dict) else {}
    return {
        "required": True,
        "mode": replay_plan.get("mode", "runtime-assisted"),
        "description": replay_plan.get(
            "description",
            "Keep the original protected code under an instrumented runtime until portable semantics are proven.",
        ),
        "hook_points": [str(item) for item in strategy.get("hook_points", [])],
        "triage_hook_plan": strategy.get("triage_hook_plan") if isinstance(strategy.get("triage_hook_plan"), dict) else {},
        "known_blockers": [str(item) for item in strategy.get("known_blockers", [])],
        "recommended_actions": [str(item) for item in replay_plan.get("recommended_actions", [])],
    }


def _build_limitations(strategy: dict[str, Any]) -> list[str]:
    if str(strategy.get("id", "")).startswith("triage_"):
        return [
            "检测到 WASM / VM / 混淆 / 反调试 / 动态 secret 标记，当前不生成纯 Python sign_rebuild.py。",
            "必须保留浏览器或 JS runtime 辅助执行，直到算法语义、动态上下文和 replay 输入都被证明可移植。",
        ]
    if strategy.get("supported"):
        return [
            "当前脚本只覆盖已验证样本的 sign 纯算与最小 replay。",
            "真实目标若存在 nonce、cookie、设备指纹或服务端会话绑定，需要继续把这些上下文加入 rebuild plan。",
            "已生成 Scrapy replay 项目；真实目标接入前仍需要复核 request/response 字段、headers 和调度策略。",
        ]
    return [
        "尚未识别可安全自动移植的纯算算法。",
        "需要继续扩大 source context、做 AST/人工复核，或保留 JS runtime 执行后端。",
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
