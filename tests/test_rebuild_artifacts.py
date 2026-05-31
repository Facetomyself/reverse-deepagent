import json
import base64
import hashlib
import hmac
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.fixtures.web_sign import start_fixture_server
from reverse_deepagent.rebuild import list_algorithm_strategy_registry, write_rebuild_bundle
from reverse_deepagent.strategies import detect_algorithm_strategy
from reverse_deepagent.schemas import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ReverseMode,
    ReverseStage,
    TaskCard,
)


def _fixture_sign(keyword: str, timestamp: int) -> str:
    raw = f"{keyword}:{timestamp}:reverse-agent-fixture"
    hash_value = sum(ord(char) for char in raw) % 100000
    return f"sig_{hash_value:x}_{timestamp}"


def _final_result_for_source(
    source_context: str,
    sample_sign: str,
    *,
    target_url: str = "http://127.0.0.1:8765/",
    related_request_url: str | None = None,
    validation_overrides: dict | None = None,
    runtime_context: dict | None = None,
    runtime_context_diff: dict | None = None,
) -> FinalResult:
    task_card = TaskCard(
        target_url_or_file=target_url,
        target_param_or_api="sign",
        goal="生成纯算 replay",
        boundaries="fixture test",
    )
    candidate = {
        "candidate_id": "script:1:buildSign",
        "function_name": "buildSign",
        "file_url": f"{target_url.rstrip('/')}/app.js",
        "script_id": "script",
        "line_number": 1,
        "source_context": source_context,
        "related_requests": [{"id": 1, "method": "POST", "url": related_request_url or f"{target_url.rstrip('/')}/api/search"}],
    }
    validation = {
        "candidate_id": candidate["candidate_id"],
        "function_name": "buildSign",
        "validation_status": "success",
        "checks": {
            "source_complete": True,
            "runtime_located": True,
            "runtime_invocation_ok": True,
            "sign_shape_ok": True,
            "replay_attempted": True,
            "replay_ok": True,
        },
        "sample_input": {"keyword": "sign", "timestamp": 1700000000000},
        "sample_output": {"sign": sample_sign, "callable_path": "window.buildSign", "invocation_result_type": "string"},
        "replay_result": {"attempted": True, "ok": True},
    }
    if validation_overrides:
        validation.update(validation_overrides)
    evidence = [
        EvidenceItem(
            summary="candidate",
            kind=EvidenceKind.STATIC,
            source="function_candidate_card",
            details={"count": 1, "candidates": [candidate]},
            confidence=ConfidenceLevel.HIGH,
        ),
        EvidenceItem(
            summary="validation",
            kind=EvidenceKind.DYNAMIC,
            source="function_validation_result",
            details={"count": 1, "validations": [validation]},
            confidence=ConfidenceLevel.HIGH,
        ),
        EvidenceItem(
            summary="summary",
            kind=EvidenceKind.NOTE,
            source="function_validation_summary",
            details={
                "total": 1,
                "success_count": 1,
                "failed_count": 0,
                "replay_ready": True,
                "best_candidate_id": candidate["candidate_id"],
                "best_function_name": "buildSign",
            },
            confidence=ConfidenceLevel.HIGH,
        ),
    ]
    if runtime_context:
        evidence.append(
            EvidenceItem(
                summary="runtime context",
                kind=EvidenceKind.STORAGE,
                source="runtime_context",
                details=runtime_context,
                confidence=ConfidenceLevel.HIGH,
            )
        )
    if runtime_context_diff:
        evidence.append(
            EvidenceItem(
                summary="runtime context diff",
                kind=EvidenceKind.NOTE,
                source="runtime_context_diff",
                details=runtime_context_diff,
                confidence=ConfidenceLevel.HIGH,
            )
        )

    return FinalResult(
        task_card=task_card,
        mode=ReverseMode.FIND_ENTRY,
        stage=ReverseStage.REPLAY_DELIVERY,
        status=ExecutionStatus.SUCCESS,
        key_findings=KeyFindings(facts=["synthetic final result"]),
        evidence=evidence,
        artifacts=[],
        next_action="extract_pure_logic_and_build_replay",
        confidence=ConfidenceLevel.HIGH,
    )


class FixtureRebuildBridge:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "check_browser_health":
            return {"status": "ok", "connected": True}
        if tool_name == "list_pages":
            return {"pages": [{"pageIdx": 0, "url": f"{self.base_url}/", "selected": True}]}
        if tool_name in {"new_page", "navigate_page"}:
            return {"ok": True}
        if tool_name == "network_request":
            return {"requests": [{"id": 1, "url": f"{self.base_url}/api/search", "method": "POST"}]}
        if tool_name == "search_in_sources":
            return {
                "results": [
                    {
                        "scriptId": "fixture-app",
                        "url": f"{self.base_url}/app.js",
                        "lineNumber": 4,
                        "preview": "function buildSign(keyword, timestamp) {",
                    }
                ]
            }
        if tool_name == "get_request_initiator":
            return {"requestId": params.get("requestId"), "stack": ["search", "fetch"]}
        if tool_name == "get_script_source":
            return {
                "scriptId": params.get("scriptId"),
                "source": """function buildSign(keyword, timestamp) {
  const FIXTURE_SEED = 'reverse-agent-fixture';
  const raw = `${keyword}:${timestamp}:${FIXTURE_SEED}`;
  const hash = Array.from(raw).reduce((acc, char) => (acc + char.charCodeAt(0)) % 100000, 0);
  return `sig_${hash.toString(16)}_${timestamp}`;
}""",
            }
        if tool_name == "evaluate_script" and "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in str(params.get("function", "")):
            timestamp = 1700000000000
            sign = _fixture_sign("sign", timestamp)
            return {
                "ok": True,
                "result": {
                    "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
                    "function_name": "buildSign",
                    "located": True,
                    "callable_path": "window.reverseFixture.buildSign",
                    "invocation_ok": True,
                    "invocation_result_type": "string",
                    "sign": sign,
                    "sign_shape_ok": True,
                    "replay_result": {"attempted": True, "ok": True, "status": 200, "echoed_sign": sign},
                    "runtime_url": f"{self.base_url}/",
                },
            }
        if tool_name == "evaluate_script":
            return {"ok": True, "result": {"readyState": "complete"}}
        if tool_name == "export_session_report":
            return {"ok": True}
        raise AssertionError(f"unexpected tool: {tool_name}")


class StrategyRegistryTests(unittest.TestCase):
    def test_strategy_registry_exposes_ordered_metadata(self) -> None:
        registry = list_algorithm_strategy_registry()
        self.assertEqual(
            [item["rule_id"] for item in registry],
            ["protected_flow_triage", "deterministic_fixture", "crypto_hash", "sig_template", "encoding"],
        )
        emitted = {strategy_id for item in registry for strategy_id in item["emits"]}
        self.assertIn("triage_wasm_module", emitted)
        self.assertIn("triage_vm_obfuscation", emitted)
        self.assertIn("triage_anti_debug_runtime", emitted)
        self.assertIn("triage_dynamic_secret", emitted)
        self.assertIn("triage_wasm_vm_obfuscation", emitted)
        self.assertIn("fixture_seed_mod100000", emitted)
        self.assertIn("md5_keyword_timestamp", emitted)
        self.assertIn("sha1_keyword_timestamp", emitted)
        self.assertIn("sha256_keyword_timestamp", emitted)
        self.assertIn("sha512_keyword_timestamp", emitted)
        self.assertIn("hmac_md5_keyword_timestamp", emitted)
        self.assertIn("hmac_sha1_keyword_timestamp", emitted)
        self.assertIn("hmac_sha512_keyword_timestamp", emitted)
        self.assertIn("base64_keyword_timestamp", emitted)
        self.assertIn("urlencode_keyword_timestamp", emitted)

    def test_protected_flow_triage_takes_precedence_over_hash_markers(self) -> None:
        strategy = detect_algorithm_strategy(
            """async function buildSign(keyword, timestamp) {
  debugger;
  const wasm = await WebAssembly.instantiateStreaming(fetch('/sign.wasm'), {});
  const digest = CryptoJS.SHA256(`${keyword}:${timestamp}`).toString();
  return wasm.instance.exports.sign(digest, window.__challenge);
}"""
        )
        self.assertEqual(strategy["id"], "triage_wasm_vm_obfuscation")
        self.assertFalse(strategy["supported"])
        self.assertIn("wasm", strategy["triage"]["categories"])
        self.assertIn("anti_debug", strategy["triage"]["categories"])
        self.assertIn("dynamic_secret", strategy["triage"]["categories"])
        self.assertIn("runtime-js-vm", strategy["runtime_context_required"])
        self.assertIn("wasm-module", strategy["runtime_context_required"])
        self.assertIn("runtime-assisted execution required", strategy["confidence_score"]["caveats"])


class RebuildArtifactTests(unittest.TestCase):
    def test_generated_replay_demo_replays_fixture_without_browser(self) -> None:
        fixture = start_fixture_server()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                runtime = JSReverserRuntime(bridge=FixtureRebuildBridge(fixture.base_url), post_navigation_wait_seconds=0)
                output = run_reverse_pipeline(
                    task_text=f"{fixture.base_url}/ 找 sign 入口，并生成纯算 replay",
                    artifact_root=Path(tmpdir) / "artifacts",
                    runtime_kind="mock",
                    runtime=runtime,
                )
                sign_rebuild_path = Path(output.artifacts["rebuild_sign_rebuild"])
                replay_demo_path = Path(output.artifacts["rebuild_replay_demo"])
                rebuild_plan_path = Path(output.artifacts["workspace_rebuild_plan"])
                self.assertTrue(sign_rebuild_path.exists())
                self.assertTrue(replay_demo_path.exists())
                plan = json.loads(rebuild_plan_path.read_text(encoding="utf-8"))
                self.assertTrue(plan["ready"])
                self.assertEqual(plan["algorithm_strategy"]["id"], "fixture_seed_mod100000")

                subprocess.run(
                    [sys.executable, str(sign_rebuild_path)],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(replay_demo_path),
                        "--base-url",
                        fixture.base_url,
                        "--keyword",
                        "sign",
                        "--timestamp",
                        "1700000000000",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                replay_payload = json.loads(result.stdout)
                self.assertTrue(replay_payload["ok"])
                self.assertEqual(replay_payload["sign"], _fixture_sign("sign", 1700000000000))
        finally:
            fixture.close()

    def test_md5_strategy_generates_self_checking_sign_rebuild(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        sample_sign = hashlib.md5("sign:1700000000000".encode("utf-8")).hexdigest()
        final_result = _final_result_for_source(source_context, sample_sign)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], "md5_keyword_timestamp")
            self.assertTrue(rebuild.rebuild_plan["pure_extraction"]["pure_extractable"])
            hints = rebuild.rebuild_plan["review_hints"]
            self.assertIn("pure_strategy_detected", {hint["code"] for hint in hints})
            self.assertEqual({hint["severity"] for hint in hints}, {"info"})
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_replay_demo_preserves_derived_api_path(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        sample_sign = hashlib.md5("sign:1700000000000".encode("utf-8")).hexdigest()
        final_result = _final_result_for_source(
            source_context,
            sample_sign,
            target_url="http://127.0.0.1:8765/",
            related_request_url="http://127.0.0.1:8765/api/custom-sign",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            replay_demo = Path(rebuild.generated_files["replay_demo"]).read_text(encoding="utf-8")
            self.assertIn('DEFAULT_API_PATH = \'/api/custom-sign\'', replay_demo)
            self.assertIn('urljoin(base_url.rstrip("/") + "/", DEFAULT_API_PATH.lstrip("/"))', replay_demo)

    def test_scrapy_project_is_generated_and_middleware_signs_requests(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return btoa(`${keyword}:${timestamp}`);
}"""
        sample_sign = base64.b64encode("sign:1700000000000".encode("utf-8")).decode("ascii")
        final_result = _final_result_for_source(source_context, sample_sign)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            project_dir = Path(rebuild.generated_files["scrapy_project"])
            self.assertTrue((project_dir / "scrapy.cfg").exists())
            self.assertTrue((project_dir / "reverse_sign_project" / "settings.py").exists())
            self.assertTrue((project_dir / "reverse_sign_project" / "middlewares.py").exists())
            self.assertTrue((project_dir / "reverse_sign_project" / "spiders" / "replay_spider.py").exists())
            manifest = json.loads(Path(rebuild.generated_files["scrapy_export_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "scrapy-export")
            self.assertEqual(manifest["spider"], "reverse_sign_replay")
            self.assertEqual(manifest["middleware"], "reverse_sign_project.middlewares.ReverseSignMiddleware")
            self.assertTrue(any("--output" in command for command in manifest["commands"]))
            runner = (project_dir / "runner.py").read_text(encoding="utf-8")
            self.assertIn("--output", runner)
            self.assertIn('command.extend(["-O", args.output])', runner)
            subprocess.run(
                [sys.executable, "-m", "compileall", "-q", str(project_dir)],
                check=True,
                text=True,
                capture_output=True,
            )
            probe = subprocess.run(
                [sys.executable, "-", str(project_dir), sample_sign],
                input="""
import json
import sys

project_dir = sys.argv[1]
expected_sign = sys.argv[2]
sys.path.insert(0, project_dir)

from reverse_sign_project.middlewares import ReverseSignMiddleware


class FakeRequest:
    def __init__(self, url, meta=None, headers=None, body=b"", method="GET"):
        self.url = url
        self.meta = dict(meta or {})
        self.headers = dict(headers or {})
        self.body = body
        self.method = method

    def replace(self, url=None, method=None, headers=None, body=None):
        merged_headers = dict(self.headers)
        if headers:
            merged_headers.update(headers)
        return FakeRequest(
            url or self.url,
            meta=self.meta,
            headers=merged_headers,
            body=self.body if body is None else body,
            method=method or self.method,
        )


request = FakeRequest(
    "http://127.0.0.1:8765/seed",
    meta={"reverse_base_url": "http://127.0.0.1:8765", "reverse_keyword": "sign", "reverse_timestamp": 1700000000000},
)
signed = ReverseSignMiddleware(default_keyword="sign", default_api_path="/api/search").process_request(request, None)
payload = json.loads(signed.body.decode("utf-8"))
result = {
    "url": signed.url,
    "method": signed.method,
    "x_sign": signed.headers[b"x-sign"].decode("utf-8"),
    "payload": payload,
    "matches": signed.headers[b"x-sign"].decode("utf-8") == expected_sign == payload["sign"],
}
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
""",
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(probe.stdout)
            self.assertTrue(payload["matches"])
            self.assertEqual(payload["method"], "POST")
            self.assertIn("/api/search?", payload["url"])
            self.assertEqual(payload["payload"]["keyword"], "sign")

    def test_template_variants_generate_self_checking_sign_rebuilds(self) -> None:
        cases = [
            (
                """function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return hmacSha256(`${keyword}${timestamp}`, secret);
}""",
                hmac.new(b"fixture-secret", b"sign1700000000000", hashlib.sha256).hexdigest(),
                "hmac_sha256_keyword_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  return btoa(`${keyword}${timestamp}`);
}""",
                base64.b64encode("sign1700000000000".encode("utf-8")).decode("ascii"),
                "base64_keyword_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return CryptoJS.HmacSHA512(`${keyword}${timestamp}`, secret).toString();
}""",
                hmac.new(b"fixture-secret", b"sign1700000000000", hashlib.sha512).hexdigest(),
                "hmac_sha512_keyword_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  return encodeURIComponent(`${keyword}${timestamp}`);
}""",
                "sign1700000000000",
                "urlencode_keyword_timestamp",
            ),
        ]
        for source_context, sample_sign, expected_strategy in cases:
            with self.subTest(expected_strategy=expected_strategy):
                final_result = _final_result_for_source(source_context, sample_sign)
                with tempfile.TemporaryDirectory() as tmpdir:
                    rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
                    self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
                    self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], expected_strategy)
                    sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
                    result = subprocess.run(
                        [sys.executable, str(sign_rebuild_path)],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
                    self.assertEqual(result.stdout.strip(), sample_sign)

    def test_hmac_sha512_rebuild_ignores_unrelated_sha256_marker(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const marker = CryptoJS.SHA256('probe').toString();
  const secret = 'fixture-secret';
  return CryptoJS.HmacSHA512(`${keyword}:${timestamp}`, secret).toString();
}"""
        sample_sign = hmac.new(b"fixture-secret", b"sign:1700000000000", hashlib.sha512).hexdigest()
        final_result = _final_result_for_source(source_context, sample_sign)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], "hmac_sha512_keyword_timestamp")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_failed_validation_blocks_runnable_rebuild(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        sample_sign = hashlib.md5("sign:1700000000000".encode("utf-8")).hexdigest()
        final_result = _final_result_for_source(
            source_context,
            sample_sign,
            validation_overrides={
                "validation_status": "failed",
                "checks": {
                    "source_complete": True,
                    "runtime_located": False,
                    "runtime_invocation_ok": False,
                    "sign_shape_ok": False,
                    "replay_attempted": True,
                    "replay_ok": False,
                },
                "replay_result": {"attempted": True, "ok": False},
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertIn("README", rebuild.generated_files)
            hint_codes = {hint["code"] for hint in rebuild.rebuild_plan["review_hints"]}
            self.assertIn("validation_not_ready", hint_codes)
            self.assertIn("sample_replay_not_ok", hint_codes)

    def test_missing_replay_url_adds_risk_review_hint(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        sample_sign = hashlib.md5("sign:1700000000000".encode("utf-8")).hexdigest()
        final_result = _final_result_for_source(
            source_context,
            sample_sign,
            target_url="/tmp/local-app.js",
            related_request_url="/tmp/local-api",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            missing_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "missing_replay_url")
            self.assertEqual(missing_hint["severity"], "risk")
            self.assertEqual(missing_hint["category"], "replay")
            self.assertIn("README", rebuild.generated_files)

    def test_sha1_strategy_generates_self_checking_sign_rebuild(self) -> None:
        source_context = """async function buildSign(keyword, timestamp) {
  const raw = `${keyword}:${timestamp}`;
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
        sample_sign = hashlib.sha1("sign:1700000000000".encode("utf-8")).hexdigest()
        final_result = _final_result_for_source(source_context, sample_sign)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], "sha1_keyword_timestamp")
            self.assertTrue(rebuild.rebuild_plan["pure_extraction"]["pure_extractable"])
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_runtime_context_dependency_blocks_pure_extraction(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const device = localStorage.getItem('device_id');
  return CryptoJS.SHA256(`${keyword}:${timestamp}:${device}`).toString();
}"""
        final_result = _final_result_for_source(source_context, "placeholder")
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(rebuild.rebuild_plan["ready"])
            self.assertFalse(rebuild.rebuild_plan["pure_extraction"]["pure_extractable"])
            self.assertIn("localStorage", rebuild.rebuild_plan["pure_extraction"]["runtime_context_required"])
            manual_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertEqual(manual_hint["severity"], "risk")
            self.assertEqual(manual_hint["category"], "manual_port")
            self.assertIn("missing_runtime_context=localStorage", manual_hint["evidence"])
            self.assertIn("README", rebuild.generated_files)

    def test_wasm_vm_triage_blocks_fake_pure_rebuild(self) -> None:
        source_context = """async function buildSign(keyword, timestamp) {
  debugger;
  const wasm = await WebAssembly.instantiateStreaming(fetch('/sign.wasm'), {});
  const opcode = wasm.instance.exports.opcode_for('sign');
  switch (opcode) {
    case 7:
      return wasm.instance.exports.sign(keyword, timestamp, window.__challenge);
    default:
      return new Function('payload', 'return payload')(keyword);
  }
}"""
        final_result = _final_result_for_source(source_context, "placeholder-sign")
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            plan = rebuild.rebuild_plan
            self.assertFalse(plan["ready"])
            self.assertEqual(plan["algorithm_strategy"]["id"], "triage_wasm_vm_obfuscation")
            self.assertFalse(plan["algorithm_strategy"]["supported"])
            self.assertFalse(plan["pure_extraction"]["pure_extractable"])
            self.assertFalse(plan["pure_extraction"]["context_aware_extractable"])
            self.assertTrue(plan["pure_extraction"]["manual_port_required"])
            self.assertIn("runtime-js-vm", plan["pure_extraction"]["runtime_context_required"])
            self.assertIn("wasm-module", plan["pure_extraction"]["runtime_context_required"])
            self.assertTrue(plan["runtime_assisted"]["required"])
            manual_hint = next(hint for hint in plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertEqual(manual_hint["severity"], "risk")
            self.assertIn("strategy=triage_wasm_vm_obfuscation", manual_hint["evidence"])
            self.assertIn("README", rebuild.generated_files)
            self.assertNotIn("sign_rebuild", rebuild.generated_files)
            readme = Path(rebuild.generated_files["README"]).read_text(encoding="utf-8")
            self.assertIn("Runtime-assisted triage required", readme)

    def test_runtime_context_diff_adds_session_bound_review_hint(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const token = sessionStorage.getItem('token');
  const raw = `${keyword}:${timestamp}:${token}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-token".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["sessionStorage"],
            "captured_requirements": ["sessionStorage"],
            "samples": [
                {"sessionStorage": {"token": "fixture-token"}},
                {"sessionStorage": {"token": "fixture-token"}},
            ],
            "sessionStorage": {"token": "fixture-token"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            plan = rebuild.rebuild_plan
            self.assertIn("runtime_context_diff", plan)
            hint_codes = {hint["code"] for hint in plan["review_hints"]}
            self.assertIn("context_aware_rebuild", hint_codes)
            self.assertIn("session_bound_runtime_context", hint_codes)
            session_hint = next(hint for hint in plan["review_hints"] if hint["code"] == "session_bound_runtime_context")
            self.assertEqual(session_hint["severity"], "warning")
            self.assertIn("session_bound_keys=sessionStorage.token", session_hint["evidence"])

    def test_runtime_context_diff_adds_volatile_review_hint_from_payload(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const raw = `${keyword}:${timestamp}:${nonce}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:n2".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "samples": [
                {"localStorage": {"nonce": "n1"}},
                {"localStorage": {"nonce": "n2"}},
            ],
            "localStorage": {"nonce": "n2"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            volatile_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "volatile_runtime_context")
            self.assertEqual(volatile_hint["severity"], "risk")
            self.assertIn("volatile_keys=localStorage.nonce", volatile_hint["evidence"])
            self.assertIn("volatile_field_count=1", volatile_hint["evidence"])

    def test_runtime_context_diff_evidence_adds_missing_type_and_object_hints(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  return btoa(`${keyword}:${timestamp}`);
}"""
        sample_sign = base64.b64encode("sign:1700000000000".encode("utf-8")).decode("ascii")
        runtime_context_diff = {
            "status": "analyzed",
            "sample_count": 2,
            "stable_keys": [],
            "volatile_keys": ["localStorage.feature_flag", "localStorage.counter", "navigator.plugins"],
            "missing_requirements": ["navigator"],
            "fields": [
                {"path": "localStorage.feature_flag", "classification": "missing_in_some_samples"},
                {"path": "localStorage.counter", "classification": "type_drift"},
                {"path": "navigator.plugins", "classification": "object_drift"},
            ],
            "summary": {
                "missing_field_count": 1,
                "missing_requirement_count": 1,
                "type_drift_field_count": 1,
                "object_drift_field_count": 1,
            },
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context_diff=runtime_context_diff)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            hint_codes = {hint["code"] for hint in rebuild.rebuild_plan["review_hints"]}
            self.assertIn("missing_runtime_context_field", hint_codes)
            self.assertIn("runtime_context_type_drift", hint_codes)
            self.assertIn("runtime_context_object_drift", hint_codes)
            missing_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "missing_runtime_context_field")
            self.assertIn("missing_keys=localStorage.feature_flag", missing_hint["evidence"])
            self.assertIn("missing_requirements=navigator", missing_hint["evidence"])

    def test_captured_runtime_context_enables_context_aware_rebuild(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const device = localStorage.getItem('device_id') || 'fixture-device';
  const raw = `${keyword}:${timestamp}:${device}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-device".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "localStorage": {"device_id": "fixture-device"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertTrue(rebuild.rebuild_plan["ready"])
            self.assertFalse(rebuild.rebuild_plan["pure_extraction"]["pure_extractable"])
            self.assertTrue(rebuild.rebuild_plan["pure_extraction"]["context_aware_extractable"])
            context_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "context_aware_rebuild")
            self.assertEqual(context_hint["severity"], "warning")
            self.assertEqual(context_hint["category"], "runtime_context")
            self.assertIn("runtime_context_required=localStorage", context_hint["evidence"])
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_localstorage_nonce_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const raw = `${keyword}:${timestamp}:${nonce}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-nonce".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "localStorage": {"nonce": "fixture-nonce"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "localStorage.nonce")
            self.assertEqual(binding["value"], "fixture-nonce")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_specific_runtime_context_key_must_be_captured(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const raw = `${keyword}:${timestamp}:${nonce}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-nonce".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "localStorage": {"device_id": "fixture-device"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            plan = rebuild.rebuild_plan
            extraction = plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(plan["ready"])
            self.assertFalse(extraction["pure_extractable"])
            self.assertFalse(extraction["context_aware_extractable"])
            self.assertTrue(extraction["manual_port_required"])
            self.assertTrue(extraction["runtime_context_binding_required"])
            self.assertIn("localStorage.nonce", extraction["runtime_context_binding_candidates"])
            self.assertIsNone(extraction["runtime_context_binding"])
            manual_hint = next(hint for hint in plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertIn("missing_runtime_context_binding=localStorage.nonce", manual_hint["evidence"])
            self.assertIn("README", rebuild.generated_files)
            self.assertNotIn("sign_rebuild", rebuild.generated_files)

    def test_optional_chaining_runtime_context_key_must_be_captured(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage?.getItem(`nonce`);
  const raw = `${keyword}:${timestamp}:${nonce}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-nonce".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "localStorage": {"device_id": "fixture-device"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            extraction = rebuild.rebuild_plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(rebuild.rebuild_plan["ready"])
            self.assertIn("localStorage.nonce", extraction["runtime_context_binding_candidates"])
            self.assertEqual(extraction["missing_runtime_context_bindings"], ["localStorage.nonce"])
            self.assertIsNone(extraction["runtime_context_binding"])
            self.assertNotIn("sign_rebuild", rebuild.generated_files)

    def test_multiple_runtime_context_bindings_are_auto_ported_when_all_values_are_captured(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const match = document.cookie.match(/(?:^|;\\s*)csrf=([^;]+)/);
  const csrf = match ? decodeURIComponent(match[1]) : '';
  const raw = `${keyword}:${timestamp}:${nonce}:${csrf}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-nonce:fixture-csrf".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage", "cookie"],
            "captured_requirements": ["localStorage", "cookie"],
            "localStorage": {"nonce": "fixture-nonce"},
            "cookies": {"document.cookie": "csrf=fixture-csrf; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            extraction = rebuild.rebuild_plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertTrue(rebuild.rebuild_plan["ready"])
            self.assertTrue(extraction["context_aware_extractable"])
            self.assertFalse(extraction["multiple_runtime_context_bindings_unsupported"])
            self.assertEqual(
                [item["source"] for item in extraction["runtime_context_bindings"]],
                ["localStorage.nonce", "cookie.csrf"],
            )
            context_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "context_aware_rebuild")
            self.assertIn("runtime_context_bindings=localStorage.nonce,cookie.csrf", context_hint["evidence"])
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_missing_one_of_multiple_runtime_context_bindings_blocks_ready(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const match = document.cookie.match(/(?:^|;\\s*)csrf=([^;]+)/);
  const csrf = match ? decodeURIComponent(match[1]) : '';
  const raw = `${keyword}:${timestamp}:${nonce}:${csrf}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-nonce:fixture-csrf".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["localStorage", "cookie"],
            "captured_requirements": ["localStorage", "cookie"],
            "localStorage": {"device_id": "fixture-device"},
            "cookies": {"document.cookie": "csrf=fixture-csrf; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            extraction = rebuild.rebuild_plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(rebuild.rebuild_plan["ready"])
            self.assertEqual([item["source"] for item in extraction["runtime_context_bindings"]], ["cookie.csrf"])
            self.assertEqual(extraction["missing_runtime_context_bindings"], ["localStorage.nonce"])
            manual_hint = next(hint for hint in rebuild.rebuild_plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertIn("missing_runtime_context_binding=localStorage.nonce", manual_hint["evidence"])
            self.assertNotIn("sign_rebuild", rebuild.generated_files)

    def test_sessionstorage_token_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const token = sessionStorage.getItem('token');
  const raw = `${keyword}:${timestamp}:${token}`;
  return CryptoJS.SHA256(raw).toString();
}"""
        sample_sign = hashlib.sha256("sign:1700000000000:fixture-token".encode("utf-8")).hexdigest()
        runtime_context = {
            "detected_requirements": ["sessionStorage"],
            "captured_requirements": ["sessionStorage"],
            "sessionStorage": {"token": "fixture-token"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "sessionStorage.token")
            self.assertEqual(binding["value"], "fixture-token")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_sessionstorage_specific_key_must_be_captured(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const token = sessionStorage.getItem('token');
  const raw = `${keyword}:${timestamp}:${token}`;
  return CryptoJS.SHA256(raw).toString();
}"""
        sample_sign = hashlib.sha256("sign:1700000000000:fixture-token".encode("utf-8")).hexdigest()
        runtime_context = {
            "detected_requirements": ["sessionStorage"],
            "captured_requirements": ["sessionStorage"],
            "sessionStorage": {"session_id": "fixture-session"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            plan = rebuild.rebuild_plan
            extraction = plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(plan["ready"])
            self.assertFalse(extraction["context_aware_extractable"])
            self.assertTrue(extraction["manual_port_required"])
            self.assertIn("sessionStorage.token", extraction["runtime_context_binding_candidates"])
            self.assertIsNone(extraction["runtime_context_binding"])
            manual_hint = next(hint for hint in plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertIn("missing_runtime_context_binding=sessionStorage.token", manual_hint["evidence"])
            self.assertIn("README", rebuild.generated_files)
            self.assertNotIn("sign_rebuild", rebuild.generated_files)

    def test_cookie_runtime_context_enables_context_aware_rebuild(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const match = document.cookie.match(/(?:^|;\\s*)device_id=([^;]+)/);
  const device = match ? decodeURIComponent(match[1]) : 'fixture-cookie-device';
  const raw = `${keyword}:${timestamp}:${device}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-cookie-device".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["cookie"],
            "captured_requirements": ["cookie"],
            "cookies": {"document.cookie": "device_id=fixture-cookie-device; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertTrue(rebuild.rebuild_plan["ready"])
            self.assertTrue(rebuild.rebuild_plan["pure_extraction"]["context_aware_extractable"])
            self.assertIn("cookie", rebuild.rebuild_plan["pure_extraction"]["captured_runtime_context"])
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_cookie_specific_key_must_be_captured(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const match = document.cookie.match(/(?:^|;\\s*)csrf=([^;]+)/);
  const csrf = match ? decodeURIComponent(match[1]) : '';
  const raw = `${keyword}:${timestamp}:${csrf}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-csrf".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["cookie"],
            "captured_requirements": ["cookie"],
            "cookies": {"document.cookie": "device_id=fixture-device; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            plan = rebuild.rebuild_plan
            extraction = plan["pure_extraction"]
            self.assertEqual(rebuild.status, ExecutionStatus.PARTIAL)
            self.assertFalse(plan["ready"])
            self.assertFalse(extraction["context_aware_extractable"])
            self.assertTrue(extraction["manual_port_required"])
            self.assertIn("cookie.csrf", extraction["runtime_context_binding_candidates"])
            self.assertIsNone(extraction["runtime_context_binding"])
            manual_hint = next(hint for hint in plan["review_hints"] if hint["code"] == "manual_port_required")
            self.assertIn("missing_runtime_context_binding=cookie.csrf", manual_hint["evidence"])
            self.assertIn("README", rebuild.generated_files)
            self.assertNotIn("sign_rebuild", rebuild.generated_files)

    def test_cookie_csrf_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const match = document.cookie.match(/(?:^|;\\s*)csrf=([^;]+)/);
  const csrf = match ? decodeURIComponent(match[1]) : '';
  const raw = `${keyword}:${timestamp}:${csrf}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-csrf".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["cookie"],
            "captured_requirements": ["cookie"],
            "cookies": {"document.cookie": "csrf=fixture-csrf; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "cookie.csrf")
            self.assertEqual(binding["value"], "fixture-csrf")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_cookie_split_startswith_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const row = document.cookie.split('; ').find((item) => item.startsWith('csrf='));
  const csrf = row ? decodeURIComponent(row.split('=')[1]) : '';
  const raw = `${keyword}:${timestamp}:${csrf}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:fixture-csrf".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["cookie"],
            "captured_requirements": ["cookie"],
            "cookies": {"document.cookie": "csrf=fixture-csrf; path=/"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "cookie.csrf")
            self.assertEqual(binding["value"], "fixture-csrf")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_timezone_offset_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const tz = new Date().getTimezoneOffset();
  const raw = `${keyword}:${timestamp}:${tz}`;
  return btoa(raw);
}"""
        sample_sign = base64.b64encode("sign:1700000000000:-480".encode("utf-8")).decode("ascii")
        runtime_context = {
            "detected_requirements": ["timezone"],
            "captured_requirements": ["timezone"],
            "timezoneOffset": -480,
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "timezone.timezoneOffset")
            self.assertEqual(binding["constant"], "TIMEZONE_OFFSET")
            self.assertEqual(binding["value"], "-480")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_hmac_message_context_is_auto_completed(self) -> None:
        source_context = """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  const raw = `${keyword}:${timestamp}:${nonce}`;
  return CryptoJS.HmacSHA256(raw, 'fixture-secret').toString();
}"""
        sample_sign = hmac.new(
            b"fixture-secret",
            "sign:1700000000000:fixture-nonce".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        runtime_context = {
            "detected_requirements": ["localStorage"],
            "captured_requirements": ["localStorage"],
            "localStorage": {"nonce": "fixture-nonce"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], "hmac_sha256_keyword_timestamp")
            binding = rebuild.rebuild_plan["pure_extraction"]["runtime_context_binding"]
            self.assertEqual(binding["source"], "localStorage.nonce")
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

    def test_navigator_runtime_context_enables_context_aware_sha256_rebuild(self) -> None:
        source_context = """async function buildSign(keyword, timestamp) {
  const userAgent = navigator.userAgent;
  const raw = `${keyword}:${timestamp}:${userAgent}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  const bytes = Array.from(new Uint8Array(digest));
  return bytes.map((item) => item.toString(16).padStart(2, '0')).join('');
}"""
        user_agent = "FixtureBrowser/13.0"
        sample_sign = hashlib.sha256(f"sign:1700000000000:{user_agent}".encode("utf-8")).hexdigest()
        runtime_context = {
            "detected_requirements": ["navigator"],
            "captured_requirements": ["navigator"],
            "navigator": {"userAgent": user_agent, "platform": "fixture", "language": "zh-CN"},
        }
        final_result = _final_result_for_source(source_context, sample_sign, runtime_context=runtime_context)
        with tempfile.TemporaryDirectory() as tmpdir:
            rebuild = write_rebuild_bundle(Path(tmpdir) / "artifacts", final_result.task_card, final_result)
            self.assertEqual(rebuild.status, ExecutionStatus.SUCCESS)
            self.assertTrue(rebuild.rebuild_plan["ready"])
            self.assertEqual(rebuild.rebuild_plan["algorithm_strategy"]["id"], "sha256_keyword_timestamp")
            self.assertTrue(rebuild.rebuild_plan["pure_extraction"]["context_aware_extractable"])
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)


if __name__ == "__main__":
    unittest.main()
