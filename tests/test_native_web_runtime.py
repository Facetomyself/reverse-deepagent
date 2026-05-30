import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from reverse_deepagent.adapters.native_web import NativeWebRuntime
from reverse_deepagent.browser import BrowserPageRef, BrowserProviderCapabilities, PlaywrightBrowserPageAdapter
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline


class FakeCDPSession:
    def __init__(self) -> None:
        self.handlers = {}
        self.calls = []

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name, payload):
        for handler in self.handlers.get(event_name, []):
            handler(payload)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Network.getResponseBody":
            return {"body": '{"native":true}', "base64Encoded": False}
        if method == "Debugger.getScriptSource":
            return {"scriptSource": "function buildSign(){ return 'x-sign'; }"}
        if method == "Debugger.setBreakpointByUrl":
            return {"breakpointId": "bp-native-1", "locations": [{"scriptId": "script-1", "lineNumber": params.get("lineNumber", 0)}]}
        if method == "Runtime.evaluate":
            expression = (params or {}).get("expression", "")
            if "debugger" in expression:
                self.emit(
                    "Debugger.paused",
                    {
                        "reason": "debugCommand",
                        "hitBreakpoints": ["bp-native-1"],
                        "callFrames": [
                            {
                                "callFrameId": "native-cf-1",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 4, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                                "scopeChain": [{"type": "local"}],
                                "this": {"type": "object"},
                            }
                        ],
                    },
                )
            return {"result": {"type": "string", "value": "scheduled"}}
        if method == "Debugger.evaluateOnCallFrame":
            expression = (params or {}).get("expression", "")
            if expression == "typeof buildSign":
                return {"result": {"type": "string", "value": "function", "description": "function"}}
            if expression == "this && typeof this":
                return {"result": {"type": "string", "value": "object", "description": "object"}}
            return {"result": {"type": "undefined", "description": "undefined"}}
        if method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"}:
            return {}
        if method == "Debugger.resume":
            return {}
        return {}


class FakeRawPage:
    def __init__(self, context) -> None:
        self.context = context
        self.url = "about:blank"
        self.handlers = {}
        self._cdp_session = FakeCDPSession()
        self.hook_installed = False
        self.hook_events = []

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event, payload):
        for handler in self.handlers.get(event, []):
            handler(payload)

    def goto(self, url, **kwargs):
        self.url = url
        self._cdp_session.emit(
            "Network.requestWillBeSent",
            {
                "requestId": "req-1",
                "loaderId": "loader-1",
                "type": "XHR",
                "request": {"url": url.rstrip("/") + "/api/search", "method": "GET"},
                "initiator": {"type": "script", "stack": {"callFrames": [{"functionName": "buildSign"}]}},
                "timestamp": 1.0,
                "wallTime": 2.0,
            },
        )
        self._cdp_session.emit("Debugger.scriptParsed", {"scriptId": "script-1", "url": url.rstrip("/") + "/assets/app.js", "startLine": 0, "endLine": 4, "hash": "abc"})
        self._cdp_session.emit("Network.webSocketFrameReceived", {"requestId": "ws-1", "timestamp": 3.0, "response": {"opcode": 1, "mask": False, "payloadData": "hello"}})
        request = FakeRequest(url.rstrip("/") + "/api/search")
        self.emit("request", request)
        self.emit("response", FakeResponse(request))

    def title(self):
        return "Native Fixture"

    def content(self):
        return """
        <html>
          <head><script src="/assets/app.js"></script></head>
          <body><script>function buildSign(){ return "x-sign"; }</script></body>
        </html>
        """

    def evaluate(self, expression):
        if "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in expression:
            return {
                "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
                "function_name": "buildSign",
                "located": True,
                "callable_path": "window.buildSign",
                "invocation_ok": True,
                "invocation_result_type": "string",
                "sign": "sig_native_1700000000000",
                "sign_shape_ok": True,
                "replay_result": {
                    "attempted": True,
                    "ok": True,
                    "status": 200,
                    "echoed_sign": "sig_native_1700000000000",
                },
                "runtime_url": self.url,
            }
        if "__reverseDeepAgentHooks" in expression and "namespace:" in expression:
            self.hook_installed = True
            self.hook_events.append({"type": "fetch", "payload": {"url": self.url.rstrip("/") + "/api/search", "method": "GET"}})
            return {"ok": True, "installed": {"fetch_xhr": True, "cookie": True, "anti_debug": True}, "eventCount": len(self.hook_events)}
        if "not_installed" in expression:
            return {"ok": self.hook_installed, "installed": {"fetch_xhr": self.hook_installed, "cookie": self.hook_installed, "anti_debug": self.hook_installed}, "events": list(self.hook_events), "eventCount": len(self.hook_events)}
        if "performance.getEntriesByType" in expression:
            return [
                {
                    "name": self.url.rstrip("/") + "/api/search",
                    "initiatorType": "xmlhttprequest",
                    "startTime": 1.0,
                    "duration": 3.0,
                    "transferSize": 256,
                    "encodedBodySize": 128,
                    "decodedBodySize": 128,
                }
            ]
        return {
            "cookie": "",
            "localStorage": {"demo": "1"},
            "sessionStorage": {},
            "navigator": {"userAgent": "fake-native", "webdriver": False},
            "timezoneOffset": 0,
        }

    def cdp_session(self):
        return self._cdp_session

    def screenshot(self, **kwargs):
        return b"png"


class FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url
        self.method = "GET"
        self.resource_type = "xhr"
        self.headers = {}
        self.request_id = "req-1"


class FakeResponse:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.status = 200
        self.ok = True
        self.headers = {"content-type": "application/json"}


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakeRawPage(self)]
        self.closed = False

    def new_page(self):
        page = FakeRawPage(self)
        self.pages.append(page)
        return page

    def new_cdp_session(self, page):
        return page.cdp_session()

    def close(self):
        self.closed = True


class FakeSession:
    provider_id = "fake-native"

    def __init__(self) -> None:
        self.context = FakeContext()

    def list_pages(self):
        return [BrowserPageRef(page_id=str(index), url=page.url, title=page.title(), selected=index == 0) for index, page in enumerate(self.context.pages)]

    def new_page(self, url=None):
        page = PlaywrightBrowserPageAdapter(self.context.new_page())
        if url:
            page.goto(url)
        return page

    def get_active_page(self):
        return PlaywrightBrowserPageAdapter(self.context.pages[0])

    def close(self):
        self.context.close()


class FakeProvider:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = False
        self.session = FakeSession()

    def describe(self):
        return BrowserProviderCapabilities(
            provider_id="fake-native",
            display_name="Fake Native Browser",
            engine="chromium",
            transport="fake",
            supports_launch=True,
            supports_playwright_api=True,
            supports_network_events=True,
            supports_runtime_eval=True,
            managed_browser=True,
        )

    def start(self):
        self.started += 1
        return self.session

    def connect(self):
        return self.start()

    def stop(self):
        self.stopped = True

    def is_available(self):
        return True


class NativeWebRuntimeTests(unittest.TestCase):
    def test_registry_lists_native_web_without_starting_playwright(self) -> None:
        metadata = {item["backend_id"]: item for item in list_runtime_backends()}
        self.assertIn("native-web", metadata)
        self.assertFalse(metadata["native-web"]["mcp_backed"])
        self.assertTrue(metadata["native-web"]["supports_protection_patch"])
        self.assertTrue(metadata["native-web"]["supports_replay_validation"])
        self.assertEqual(metadata["native-web"]["config"]["default_browser_provider"], "playwright-chromium")

        runtime = build_runtime("native-web")
        capabilities = runtime.describe_capabilities().model_dump(mode="json")
        self.assertEqual(capabilities["backend_id"], "native-web")
        self.assertTrue(capabilities["supports_protection_patch"])
        self.assertTrue(capabilities["supports_replay_validation"])
        self.assertEqual(capabilities["config"]["provider"]["provider_id"], "playwright-chromium")

    def test_registry_factory_preserves_browser_provider_config(self) -> None:
        runtime = build_runtime(
            "native-web",
            browser="cloakbrowser",
            browser_headless=False,
            browser_humanize=False,
            browser_proxy="http://127.0.0.1:7890",
            browser_geoip=True,
            browser_locale="zh-CN",
            browser_timezone="Asia/Shanghai",
            browser_args=["--disable-gpu"],
        )
        provider = runtime.browser_provider
        config = provider.config.model_dump(mode="json")
        self.assertEqual(provider.provider_id, "cloakbrowser")
        self.assertFalse(config["headless"])
        self.assertFalse(config["humanize"])
        self.assertEqual(config["proxy"], "http://127.0.0.1:7890")
        self.assertTrue(config["geoip"])
        self.assertEqual(config["locale"], "zh-CN")
        self.assertEqual(config["timezone"], "Asia/Shanghai")
        self.assertEqual(config["args"], ["--disable-gpu"])


    def test_native_web_runtime_pipeline_writes_core_artifacts_without_mcp(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.test/app 找 buildSign 入口",
                artifact_root=Path(tmpdir),
                runtime_kind="native-web",
                runtime=runtime,
            )
            artifacts = output.artifacts
            self.assertEqual(output.final_result.status.value, "success")
            self.assertEqual(output.final_result.next_action, "extract_pure_logic_and_build_replay")
            self.assertIn("workspace_network_requests", artifacts)
            self.assertIn("workspace_source_hits", artifacts)
            self.assertIn("workspace_runtime_context", artifacts)
            self.assertIn("workspace_dom_snapshot", artifacts)
            self.assertIn("workspace_script_inventory", artifacts)
            self.assertIn("workspace_console_messages", artifacts)
            self.assertIn("workspace_navigation_events", artifacts)
            self.assertIn("workspace_function_candidates", artifacts)
            self.assertIn("workspace_function_validations", artifacts)
            self.assertIn("workspace_function_validation_summary", artifacts)
            network = json.loads(Path(artifacts["workspace_network_requests"]).read_text(encoding="utf-8"))
            source_hits = json.loads(Path(artifacts["workspace_source_hits"]).read_text(encoding="utf-8"))
            runtime_context = json.loads(Path(artifacts["workspace_runtime_context"]).read_text(encoding="utf-8"))
            dom_snapshot = json.loads(Path(artifacts["workspace_dom_snapshot"]).read_text(encoding="utf-8"))
            script_inventory = json.loads(Path(artifacts["workspace_script_inventory"]).read_text(encoding="utf-8"))
            console_messages = json.loads(Path(artifacts["workspace_console_messages"]).read_text(encoding="utf-8"))
            navigation_events = json.loads(Path(artifacts["workspace_navigation_events"]).read_text(encoding="utf-8"))
            request_initiators = json.loads(Path(artifacts["workspace_request_initiators"]).read_text(encoding="utf-8"))
            response_bodies = json.loads(Path(artifacts["workspace_response_bodies"]).read_text(encoding="utf-8"))
            source_contexts = json.loads(Path(artifacts["workspace_source_contexts"]).read_text(encoding="utf-8"))
            websocket_frames = json.loads(Path(artifacts["workspace_websocket_frames"]).read_text(encoding="utf-8"))
            hook_timeline = json.loads(Path(artifacts["workspace_hook_timeline"]).read_text(encoding="utf-8"))
            function_candidates = json.loads(Path(artifacts["workspace_function_candidates"]).read_text(encoding="utf-8"))
            function_validations = json.loads(Path(artifacts["workspace_function_validations"]).read_text(encoding="utf-8"))
            function_validation_summary = json.loads(Path(artifacts["workspace_function_validation_summary"]).read_text(encoding="utf-8"))
            manifest = json.loads(Path(artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))

        self.assertEqual(provider.started, 1)
        self.assertEqual(network["count"], 1)
        self.assertEqual(source_hits["count"], 1)
        self.assertTrue(runtime_context["ok"])
        self.assertEqual(function_candidates["candidates"][0]["function_name"], "buildSign")
        self.assertEqual(function_validations["validations"][0]["validation_status"], "success")
        self.assertTrue(function_validation_summary["replay_ready"])
        self.assertGreater(dom_snapshot["html_size"], 0)
        self.assertEqual(script_inventory["count"], 2)
        self.assertEqual(console_messages["count"], 0)
        self.assertEqual(navigation_events["events"], ["navigated:https://example.test/app"])
        self.assertEqual(request_initiators["status"], "success")
        self.assertEqual(request_initiators["count"], 1)
        self.assertEqual(response_bodies["status"], "success")
        self.assertEqual(response_bodies["items"][0]["preview"], '{"native":true}')
        self.assertEqual(source_contexts["status"], "success")
        self.assertIn("buildSign", source_contexts["items"][0]["sourcePreview"])
        self.assertEqual(websocket_frames["status"], "success")
        self.assertEqual(websocket_frames["items"][0]["payloadPreview"], "hello")
        self.assertTrue(hook_timeline["install"]["ok"])
        self.assertEqual(hook_timeline["snapshot"]["eventCount"], 1)
        self.assertEqual(hook_timeline["snapshot"]["events"][0]["type"], "fetch")
        manifest_by_key = {entry["artifact_key"]: entry for entry in manifest["entries"]}
        self.assertEqual(manifest_by_key["workspace_dom_snapshot"]["metadata"]["browser_provider"], "fake-native")
        self.assertEqual(manifest_by_key["workspace_script_inventory"]["category"], "source")
        self.assertEqual(manifest_by_key["workspace_navigation_events"]["category"], "trace")
        self.assertEqual(manifest_by_key["workspace_response_bodies"]["category"], "network")
        self.assertEqual(manifest_by_key["workspace_websocket_frames"]["category"], "network")
        self.assertEqual(manifest_by_key["workspace_hook_timeline"]["category"], "hook-timeline")
        self.assertEqual(manifest_by_key["workspace_function_validations"]["category"], "trace")

    def test_native_web_runtime_apply_minimal_protection_installs_hooks(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("console.clear", {"reason": "unit-test"})
        self.assertEqual(result.status.value, "success")
        self.assertIn("install_hook:fetch_xhr", result.applied_actions)
        self.assertEqual(result.next_action, "resume_recon")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/hook-timeline.json")

    def test_native_web_runtime_apply_minimal_protection_sets_breakpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("set-breakpoint", {"url_pattern": ".*app\\.js$", "line_number": 4})
        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["set_breakpoint_by_url:.*app\\.js$"])
        self.assertEqual(result.next_action, "wait_for_breakpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/breakpoints.json")
        self.assertIn(("Debugger.enable", {}), page._cdp_session.calls)
        self.assertIn(("Debugger.setBreakpointByUrl", {"urlRegex": ".*app\\.js$", "lineNumber": 4}), page._cdp_session.calls)
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/debugger-paused.json")
        self.assertEqual(result.artifacts[1].metadata["status"], "not_observed")

    def test_native_web_runtime_apply_minimal_protection_captures_paused_callframes(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "set-breakpoint",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 4,
                "trigger_expression": "setTimeout(() => { debugger; }, 0); 'scheduled'",
                "callframe_evaluations": ["typeof buildSign", "this && typeof this"],
                "debugger_actions": ["step_over"],
            },
        )
        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.next_action, "inspect_debugger_action_result")
        self.assertIn("capture_debugger_paused", result.applied_actions)
        self.assertIn("paused_status=success", result.verification)
        self.assertIn("debugger_lifecycle=action_controlled", result.verification)
        self.assertIn("callframe_count=1", result.verification)
        self.assertIn("callframe_evaluation_count=2", result.verification)
        self.assertIn("callframe_evaluation_policy=read_only", result.verification)
        self.assertIn("debugger_action_count=1", result.verification)
        self.assertIn("debugger_session_count=1", result.verification)
        self.assertIn("debugger_timeline_count=7", result.verification)
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/debugger-paused.json")
        self.assertEqual(result.artifacts[1].metadata["status"], "success")
        self.assertEqual(result.artifacts[2].path, "virtual://workspace/callframes.json")
        self.assertEqual(result.artifacts[2].metadata["count"], 1)
        self.assertEqual(result.artifacts[3].path, "virtual://workspace/callframe-evaluations.json")
        self.assertEqual(result.artifacts[3].metadata["count"], 2)
        self.assertEqual(result.artifacts[3].metadata["policy"], "read_only")
        self.assertEqual(result.artifacts[4].path, "virtual://workspace/debugger-actions.json")
        self.assertEqual(result.artifacts[4].metadata["count"], 1)
        self.assertEqual(result.artifacts[5].path, "virtual://workspace/debugger-session.json")
        self.assertEqual(result.artifacts[5].metadata["lifecycle"], "action_controlled")
        self.assertEqual(result.artifacts[5].metadata["paused_event_count"], 1)
        self.assertEqual(result.artifacts[6].path, "virtual://workspace/debugger-timeline.json")
        self.assertEqual(result.artifacts[6].metadata["entry_count"], 7)
        self.assertIn(("Runtime.evaluate", {"expression": "setTimeout(() => { debugger; }, 0); 'scheduled'", "awaitPromise": False, "returnByValue": True, "userGesture": True}), page._cdp_session.calls)
        self.assertIn(
            ("Debugger.evaluateOnCallFrame", {"callFrameId": "native-cf-1", "expression": "typeof buildSign", "returnByValue": True, "silent": True, "throwOnSideEffect": True}),
            page._cdp_session.calls,
        )
        self.assertIn(("Debugger.stepOver", {}), page._cdp_session.calls)
        self.assertNotIn(("Debugger.resume", {}), page._cdp_session.calls)


if __name__ == "__main__":
    unittest.main()
