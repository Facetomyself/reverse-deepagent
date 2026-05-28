import unittest

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.runtime.base import BrowserSessionInfo
from reverse_deepagent.schemas import ReverseMode, ReverseStage, RouterResult, TaskCard


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def invoke(self, tool_name: str, params: dict):
        self.calls.append((tool_name, params))
        if tool_name == "check_browser_health":
            return {"status": "ok", "connected": True}
        if tool_name == "list_pages":
            return {"pages": [{"pageIdx": 0, "url": "https://example.com/search", "selected": True}]}
        if tool_name == "network_request":
            return {"requests": [{"id": 1, "url": "https://example.com/api/search", "method": "POST"}]}
        if tool_name == "search_in_sources":
            return {"results": [{"scriptId": "1", "url": "https://example.com/app.js", "lineNumber": 120}]}
        if tool_name == "get_request_initiator":
            return {"requestId": params.get("requestId"), "stack": ["search", "fetch"]}
        if tool_name == "get_script_source":
            return {"scriptId": params.get("scriptId"), "source": "function buildSign() {}"}
        if tool_name == "export_session_report":
            return {"ok": True, "format": params.get("format", "json")}
        if tool_name == "evaluate_script" and "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in str(params.get("function", "")):
            return {
                "ok": True,
                "result": {
                    "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
                    "function_name": "buildSign",
                    "located": True,
                    "callable_path": "window.reverseFixture.buildSign",
                    "invocation_ok": True,
                    "invocation_result_type": "string",
                    "sign": "sig_sign_1700000000000",
                    "sign_shape_ok": True,
                    "replay_result": {
                        "attempted": True,
                        "ok": True,
                        "status": 200,
                        "echoed_sign": "sig_sign_1700000000000",
                    },
                    "runtime_url": "https://example.com/search",
                },
            }
        if tool_name in {"navigate_page", "new_page", "inject_preload_script", "evaluate_script"}:
            return {"ok": True}
        raise AssertionError(f"unexpected tool: {tool_name}")


class RuntimeAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = JSReverserRuntime(bridge=FakeBridge())

    def test_ensure_browser_session_returns_normalized_state(self) -> None:
        browser = self.runtime.ensure_browser_session()
        self.assertTrue(browser.healthy)
        self.assertEqual(browser.page_count, 1)
        self.assertEqual(browser.selected_page_idx, 0)

    def test_run_web_recon_returns_structured_result(self) -> None:
        task_card = TaskCard(
            target_url_or_file="https://example.com/search",
            target_param_or_api="x-sign",
            goal="找到 x-sign 生成入口",
            boundaries="不登录，不做破坏性操作",
        )
        route = RouterResult(
            selected_mode=ReverseMode.FULL_WORKFLOW,
            selected_playbook="references/playbooks/full-workflow.md",
            initial_stage=ReverseStage.RECON,
            reasoning=["跨多个阶段"],
            next_action="delegate_to_web_recon",
        )

        result = self.runtime.run_web_recon(task_card, route)
        self.assertEqual(result.next_action, "extract_pure_logic_and_build_replay")
        self.assertTrue(result.evidence)
        self.assertEqual(result.key_findings.unknowns, [])
        self.assertIn("已采集 1 条请求发起链路证据", result.key_findings.facts)
        self.assertIn("已拉取 1 个源码上下文片段", result.key_findings.facts)
        self.assertTrue(any(item.source == "get_request_initiator" for item in result.evidence))
        self.assertTrue(any(item.source == "get_script_source" for item in result.evidence))
        candidate_evidence = next(item for item in result.evidence if item.source == "function_candidate_card")
        self.assertEqual(candidate_evidence.details["candidates"][0]["function_name"], "buildSign")
        validation_evidence = next(item for item in result.evidence if item.source == "function_validation_result")
        self.assertEqual(validation_evidence.details["validations"][0]["validation_status"], "success")
        self.assertTrue(validation_evidence.details["validations"][0]["checks"]["source_complete"])
        self.assertTrue(validation_evidence.details["validations"][0]["replay_result"]["ok"])
        self.assertTrue(any(item.path == "virtual://workspace/request-initiators.json" for item in result.artifacts))
        self.assertTrue(any(item.path == "virtual://workspace/source-contexts.json" for item in result.artifacts))
        self.assertTrue(any(item.path == "virtual://workspace/function-candidates.json" for item in result.artifacts))
        self.assertTrue(any(item.path == "virtual://workspace/function-validations.json" for item in result.artifacts))
        self.assertTrue(any(item.path == "virtual://workspace/function-validation-summary.json" for item in result.artifacts))

    def test_export_reverse_artifacts_returns_export_bundle(self) -> None:
        bundle = self.runtime.export_reverse_artifacts()
        self.assertEqual(len(bundle.exports), 1)
        self.assertEqual(bundle.artifacts[0]["path"], "virtual://exports/session-report.json")

    def test_collect_runtime_context_takes_multiple_samples(self) -> None:
        class ContextBridge:
            def __init__(self) -> None:
                self.evaluate_calls = 0

            def invoke(self, tool_name: str, params: dict):
                if tool_name == "get_storage":
                    return {"localStorage": {"device_id": "fixture-device"}}
                if tool_name == "evaluate_script":
                    self.evaluate_calls += 1
                    return {
                        "ok": True,
                        "result": {
                            "localStorage": {"device_id": "fixture-device", "nonce": f"n{self.evaluate_calls}"},
                            "navigator": {"userAgent": "FixtureBrowser/13.0"},
                            "timezoneOffset": -480,
                        },
                    }
                raise AssertionError(f"unexpected tool: {tool_name}")

        bridge = ContextBridge()
        runtime = JSReverserRuntime(
            bridge=bridge,
            runtime_context_sample_count=2,
            runtime_context_sample_interval_seconds=0,
        )
        browser = BrowserSessionInfo(
            healthy=True,
            page_count=1,
            selected_page_idx=0,
            active_url="https://example.com",
            details={},
        )
        runtime_context = runtime._collect_runtime_context(
            browser,
            [{"text": "const device = localStorage.getItem('device_id'); return navigator.userAgent + device;"}],
        )
        self.assertEqual(bridge.evaluate_calls, 2)
        self.assertEqual(len(runtime_context["samples"]), 2)
        self.assertEqual(runtime_context["captured_requirements"], ["localStorage", "navigator"])
        diff = runtime._build_runtime_context_diff(runtime_context)
        self.assertEqual(diff["status"], "multi_sample")
        self.assertIn("localStorage.nonce", diff["volatile_keys"])

    def test_runtime_context_diff_detects_multi_sample_volatile_keys(self) -> None:
        runtime_context = {
            "detected_requirements": ["localStorage", "navigator"],
            "captured_requirements": ["localStorage", "navigator"],
            "samples": [
                {
                    "localStorage": {"device_id": "fixture-device", "nonce": "n1"},
                    "navigator": {"userAgent": "FixtureBrowser/13.0"},
                    "sample_index": 0,
                    "collected_at_ms": 1000,
                },
                {
                    "localStorage": {"device_id": "fixture-device", "nonce": "n2"},
                    "navigator": {"userAgent": "FixtureBrowser/13.0"},
                    "sample_index": 1,
                    "collected_at_ms": 1050,
                },
            ],
        }
        diff = self.runtime._build_runtime_context_diff(runtime_context)
        self.assertEqual(diff["status"], "multi_sample")
        self.assertEqual(diff["sample_count"], 2)
        self.assertFalse(diff["stable"])
        self.assertIn("localStorage.device_id", diff["stable_keys"])
        self.assertIn("navigator.userAgent", diff["stable_keys"])
        self.assertIn("localStorage.nonce", diff["volatile_keys"])
        self.assertNotIn("sample_index", diff["volatile_keys"])
        self.assertNotIn("collected_at_ms", diff["volatile_keys"])
        self.assertEqual(diff["changes"]["localStorage.nonce"], ["n1", "n2"])

    def test_runtime_context_diff_marks_single_sample_stable_keys(self) -> None:
        runtime_context = {
            "detected_requirements": ["cookie", "navigator"],
            "captured_requirements": ["cookie", "navigator"],
            "cookies": {"document.cookie": "device_id=fixture-cookie-device"},
            "navigator": {"userAgent": "FixtureBrowser/13.0"},
        }
        diff = self.runtime._build_runtime_context_diff(runtime_context)
        self.assertEqual(diff["status"], "single_sample")
        self.assertTrue(diff["stable"])
        self.assertIn("cookies.document.cookie", diff["stable_keys"])
        self.assertIn("navigator.userAgent", diff["stable_keys"])
        self.assertEqual(diff["missing_requirements"], [])


if __name__ == "__main__":
    unittest.main()
