import json
import base64
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.fixtures.web_sign import start_fixture_server
from reverse_deepagent.rebuild import write_rebuild_bundle
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
    runtime_context: dict | None = None,
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
        "related_requests": [{"id": 1, "method": "POST", "url": f"{target_url.rstrip('/')}/api/search"}],
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
            self.assertIn("README", rebuild.generated_files)

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
            sign_rebuild_path = Path(rebuild.generated_files["sign_rebuild"])
            result = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.stdout.strip(), sample_sign)

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
