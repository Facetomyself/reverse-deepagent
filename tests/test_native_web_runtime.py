import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from reverse_deepagent.adapters.native_web import NativeWebRuntime
from reverse_deepagent.browser import BrowserPageRef, BrowserProviderCapabilities, PlaywrightBrowserPageAdapter
from reverse_deepagent.browser.hooks import BreakpointManager
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline
from reverse_deepagent.fixtures.web_sign import FixtureProfile, _build_js


WEBPACK_MINIFIED_SOURCE = _build_js(FixtureProfile.WEBPACK_MINIFIED)


class FakeCDPSession:
    def __init__(self, owner=None) -> None:
        self.handlers = {}
        self.calls = []
        self.owner = owner
        self.last_breakpoint_params = {}

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
            self.last_breakpoint_params = params or {}
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
            if self.owner is not None and getattr(self.owner, "source_logpoint_installed", False):
                self.owner.source_logpoint_events.append(
                    {
                        "type": "source_logpoint",
                        "payload": {
                            "logpointId": getattr(self.owner, "source_logpoint_id", "smoke-logpoint"),
                            "urlPattern": getattr(self.owner, "source_logpoint_url_pattern", ".*app\\.js$"),
                            "lineNumber": getattr(self.owner, "source_logpoint_line_number", 0),
                            "columnNumber": getattr(self.owner, "source_logpoint_column_number", None),
                            "label": getattr(self.owner, "source_logpoint_label", "smoke"),
                            "pauseOnHit": getattr(self.owner, "source_logpoint_pause_on_hit", False),
                            "ok": True,
                            "value": {"type": "string", "preview": "sig_native_1700000000000"},
                            "error": None,
                        },
                    }
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
        self.source_logpoint_installed = False
        self.source_logpoint_events = []
        self.source_logpoint_id = "smoke-logpoint"
        self.source_logpoint_url_pattern = ".*app\\.js$"
        self.source_logpoint_line_number = 0
        self.source_logpoint_column_number = None
        self.source_logpoint_label = "smoke"
        self.source_logpoint_pause_on_hit = False
        self._cdp_session = FakeCDPSession(owner=self)
        self.hook_installed = False
        self.hook_events = []
        self.function_hook_installed = False
        self.function_hook_events = []
        self.module_hook_installed = False
        self.module_hook_events = []
        self.async_chunk_loads = []
        self.module_federation_get_init_probes = []
        self.module_federation_factory_invocations = []
        self.external_source = ""
        self.runtime_module_payload = None
        self.page_mutation_html_length = 10
        self.page_mutation_text_length = 4
        self.page_mutation_body_child_count = 1
        self.page_mutation_local_storage_keys = ["demo"]
        self.page_mutation_session_storage_keys = []
        self.page_mutation_cookie_names = []
        self.page_mutation_globals = {"window.__token": {"type": "string", "preview": "before"}}
        self.object_root_mutated = False

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
        if "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__" in expression:
            return {
                "marker": "__REVERSE_AGENT_MUTATION_OBSERVER_TIMELINE__",
                "ok": True,
                "status": "success",
                "records": [
                    {
                        "index": 0,
                        "ts": 1,
                        "type": "childList",
                        "target": {"nodeType": "element", "tag": "body"},
                        "attributeName": None,
                        "oldValue": None,
                        "addedNodes": [{"nodeType": "element", "tag": "div", "text": "after"}],
                        "removedNodes": [],
                    },
                    {
                        "index": 1,
                        "ts": 2,
                        "type": "attributes",
                        "target": {"nodeType": "element", "tag": "main"},
                        "attributeName": "data-token",
                        "oldValue": None,
                        "addedNodes": [],
                        "removedNodes": [],
                    },
                ],
                "trigger": {"attempted": True, "ok": True, "result": {"value": "mutated"}},
                "observer": {"target": "document.body", "options": {"childList": True, "attributes": True}},
                "summary": {
                    "record_count": 2,
                    "types": ["attributes", "childList"],
                    "by_type": {"attributes": 1, "childList": 1},
                },
            }
        if "__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__" in expression:
            children = {
                "token": {
                    "path": "window.__appState.token",
                    "key": "token",
                    "type": "string",
                    "preview": "after" if self.object_root_mutated else "before",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": True,
                        "writable": not self.object_root_mutated,
                        "hasGetter": False,
                        "hasSetter": False,
                        "kind": "data",
                    },
                }
            }
            if self.object_root_mutated:
                children["nonce"] = {
                    "path": "window.__appState.nonce",
                    "key": "nonce",
                    "type": "number",
                    "preview": "9",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": True,
                        "writable": True,
                        "hasGetter": False,
                        "hasSetter": False,
                        "kind": "data",
                    },
                }
            else:
                children["stale"] = {
                    "path": "window.__appState.stale",
                    "key": "stale",
                    "type": "boolean",
                    "preview": "true",
                    "descriptor": {
                        "exists": True,
                        "enumerable": True,
                        "configurable": True,
                        "writable": True,
                        "hasGetter": False,
                        "hasSetter": False,
                        "kind": "data",
                    },
                }
            return {
                "marker": "__REVERSE_AGENT_OBJECT_ROOT_MUTATION_AUDIT__",
                "ok": True,
                "status": "success",
                "root_path": "window.__appState",
                "root": {"path": "window.__appState", "type": "object", "own_property_count": len(children), "children": children},
                "side_effect_policy": {
                    "default_recon": False,
                    "trigger_required_for_mutation": True,
                    "getter_invocation": False,
                    "prototype_traversal": False,
                    "calls_mcp": False,
                    "mobile_runtime_used": False,
                },
            }
        if "__REVERSE_AGENT_PAGE_MUTATION_AUDIT__" in expression:
            return {
                "marker": "__REVERSE_AGENT_PAGE_MUTATION_AUDIT__",
                "ok": True,
                "url": self.url,
                "title": "Native Fixture",
                "dom": {
                    "html_length": self.page_mutation_html_length,
                    "text_length": self.page_mutation_text_length,
                    "body_child_count": self.page_mutation_body_child_count,
                    "html_preview": "<main></main>",
                    "text_preview": "demo",
                },
                "storage": {
                    "localStorage": {
                        "available": True,
                        "count": len(self.page_mutation_local_storage_keys),
                        "keys": list(self.page_mutation_local_storage_keys),
                    },
                    "sessionStorage": {
                        "available": True,
                        "count": len(self.page_mutation_session_storage_keys),
                        "keys": list(self.page_mutation_session_storage_keys),
                    },
                },
                "cookies": {"count": len(self.page_mutation_cookie_names), "names": list(self.page_mutation_cookie_names)},
                "globals": dict(self.page_mutation_globals),
            }
        if "mutateNativeObjectRoot()" in expression:
            self.object_root_mutated = True
            return "object-mutated"
        if "mutateNativePage()" in expression:
            self.page_mutation_html_length = 44
            self.page_mutation_text_length = 12
            self.page_mutation_body_child_count = 2
            self.page_mutation_local_storage_keys.append("nonce")
            self.page_mutation_session_storage_keys.append("token")
            self.page_mutation_cookie_names.append("sid")
            self.page_mutation_globals["window.__token"] = {"type": "string", "preview": "after"}
            return "mutated"
        if "__REVERSE_AGENT_MODULE_DISCOVERY__" in expression:
            if self.runtime_module_payload is not None:
                return self.runtime_module_payload
            return {
                "ok": False,
                "status": "unsupported",
                "requirePath": "window.__webpack_require__",
                "cacheModules": [],
                "registryModules": [],
                "reason": "require_path_unavailable",
            }
        if "__REVERSE_AGENT_ASYNC_CHUNK_LOAD__" in expression:
            self.async_chunk_loads.append("731")
            return {
                "marker": "__REVERSE_AGENT_ASYNC_CHUNK_LOAD__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "runtimePath": "window.__webpack_require__",
                "chunkId": "731",
                "beforeRegistryCount": 1,
                "afterRegistryCount": 2,
                "addedRegistryKeys": ["731"],
                "beforeCacheCount": 0,
                "afterCacheCount": 0,
                "addedCacheKeys": [],
                "moduleFactoryInvoked": False,
            }
        if "__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__" in expression:
            self.module_federation_get_init_probes.append("./token")
            return {
                "marker": "__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "containerPath": "window.remoteOther",
                "exposedName": "./token",
                "shareScopePath": "window.__webpack_share_scopes__.default",
                "containerInitCalled": True,
                "remoteGetCalled": True,
                "remoteFactoryInvoked": False,
                "remoteCodeExecuted": False,
                "factoryType": "function",
                "beforeSharedScopeKeys": [],
                "afterSharedScopeKeys": ["default"],
                "addedSharedScopeKeys": ["default"],
                "beforeContainerKeys": ["get", "init"],
                "afterContainerKeys": ["get", "init"],
                "addedContainerKeys": [],
                "reviewRequiredBeforeFactoryInvocation": True,
            }
        if "__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__" in expression:
            self.module_federation_factory_invocations.append("./token")
            return {
                "marker": "__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "containerPath": "window.remoteOther",
                "exposedName": "./token",
                "shareScopePath": "window.__webpack_share_scopes__.default",
                "containerInitCalled": True,
                "remoteGetCalled": True,
                "remoteFactoryInvoked": True,
                "remoteCodeExecuted": True,
                "factoryType": "function",
                "moduleType": "object",
                "exportNames": ["sign"],
                "exportCount": 1,
                "exportPreviews": {"sign": {"type": "function", "name": "sign", "preview": "function sign() {}"}},
                "beforeSharedScopeKeys": [],
                "afterSharedScopeKeys": ["default"],
                "addedSharedScopeKeys": ["default"],
                "beforeContainerKeys": ["get", "init"],
                "afterContainerKeys": ["get", "init"],
                "addedContainerKeys": [],
            }
        if "fetch(" in expression and "/assets/app.js" in expression:
            return self.external_source
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
        if "__reverseDeepAgentSourceLogpoints" in expression and "source_logpoints" in expression and "installed: [{" in expression:
            self.source_logpoint_installed = True
            self.source_logpoint_id = "smoke-logpoint"
            self.source_logpoint_url_pattern = ".*app\\.js$"
            self.source_logpoint_line_number = 7
            self.source_logpoint_column_number = 0
            self.source_logpoint_label = "smoke"
            self.source_logpoint_pause_on_hit = False
            return {
                "ok": True,
                "installed": [
                    {
                        "logpointId": self.source_logpoint_id,
                        "urlPattern": self.source_logpoint_url_pattern,
                        "lineNumber": self.source_logpoint_line_number,
                        "columnNumber": self.source_logpoint_column_number,
                        "label": self.source_logpoint_label,
                        "pauseOnHit": self.source_logpoint_pause_on_hit,
                    }
                ],
                "missing": [],
                "eventCount": len(self.source_logpoint_events),
            }
        if "__reverseDeepAgentSourceLogpoints" in expression and "eventCount" in expression:
            return {
                "ok": self.source_logpoint_installed,
                "events": list(self.source_logpoint_events),
                "eventCount": len(self.source_logpoint_events),
                "installed": {self.source_logpoint_id: self.source_logpoint_installed},
            }
        if "__reverseDeepAgentHooks" in expression and "functionPaths" in expression and "function_hooks" in expression:
            self.function_hook_installed = True
            return {
                "ok": True,
                "installed": [{"path": "window.buildSign", "functionName": "buildSign", "candidateId": "script-1:buildSign"}],
                "missing": [],
                "eventCount": len(self.function_hook_events),
            }
        if "__reverseDeepAgentHooks" in expression and "function_" in expression and "eventCount" in expression and "module_hooks" not in expression:
            return {"ok": self.function_hook_installed, "events": list(self.function_hook_events), "eventCount": len(self.function_hook_events), "installed": {"window.buildSign": self.function_hook_installed}}
        if "__reverseDeepAgentHooks" in expression and "module_hooks" in expression and "moduleIdValue" in expression:
            self.module_hook_installed = True
            return {
                "ok": True,
                "installed": [
                    {
                        "moduleId": "731",
                        "exportName": "sign",
                        "functionName": "sign",
                        "requirePath": "window.__webpack_require__",
                        "hookPath": "window.__webpack_require__(731).sign",
                    }
                ],
                "missing": [],
                "eventCount": len(self.module_hook_events),
            }
        if "__reverseDeepAgentHooks" in expression and "module_export_" in expression and "eventCount" in expression:
            return {
                "ok": self.module_hook_installed,
                "events": list(self.module_hook_events),
                "eventCount": len(self.module_hook_events),
                "installed": {"window.__webpack_require__(731).sign": self.module_hook_installed},
            }
        if "__webpack_require__(731).sign" in expression:
            if self.module_hook_installed:
                self.module_hook_events.extend(
                    [
                        {
                            "type": "module_export_call",
                            "payload": {"moduleId": "731", "exportName": "sign", "hookPath": "window.__webpack_require__(731).sign", "argCount": 2},
                        },
                        {
                            "type": "module_export_return",
                            "payload": {
                                "moduleId": "731",
                                "exportName": "sign",
                                "hookPath": "window.__webpack_require__(731).sign",
                                "result": {"type": "string", "preview": "sig_native_1700000000000"},
                            },
                        },
                    ]
                )
            return "sig_native_1700000000000"
        if "window.buildSign" in expression:
            if self.function_hook_installed:
                self.function_hook_events.extend(
                    [
                        {"type": "function_call", "payload": {"path": "window.buildSign", "functionName": "buildSign", "argCount": 2}},
                        {"type": "function_return", "payload": {"path": "window.buildSign", "functionName": "buildSign", "result": {"type": "string", "preview": "sig_native_1700000000000"}}},
                    ]
                )
            return "sig_native_1700000000000"
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
            self.assertIn("workspace_flow_timeline", artifacts)
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
            flow_timeline = json.loads(Path(artifacts["workspace_flow_timeline"]).read_text(encoding="utf-8"))
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
        self.assertEqual(flow_timeline["status"], "success")
        self.assertEqual(flow_timeline["run_id"], "native-web-recon")
        self.assertEqual(flow_timeline["new_entry_count"], 5)
        self.assertEqual(flow_timeline["entry_count"], 5)
        self.assertIn("network.request", {entry["type"] for entry in flow_timeline["entries"]})
        self.assertIn("hook.fetch", {entry["type"] for entry in flow_timeline["entries"]})
        self.assertIn("replay.validation", {entry["type"] for entry in flow_timeline["entries"]})
        correlations = [entry["correlation"] for entry in flow_timeline["entries"]]
        candidate_id = function_candidates["candidates"][0]["candidate_id"]
        self.assertTrue(any(correlation.get("request_id") == "req-1" for correlation in correlations))
        self.assertTrue(any(correlation.get("url_path") == "/app/api/search" for correlation in correlations))
        self.assertTrue(any("buildSign" in correlation.get("function_names", []) for correlation in correlations))
        self.assertTrue(any(candidate_id in correlation.get("candidate_ids", []) for correlation in correlations))
        self.assertTrue(any(correlation.get("method") == "GET" for correlation in correlations))
        self.assertTrue(all(correlation.get("confidence") in {"none", "low", "medium"} for correlation in correlations))
        self.assertGreaterEqual(flow_timeline["correlation_group_count"], 3)
        groups_by_strategy = {group["strategy"]: group for group in flow_timeline["correlation_groups"]}
        self.assertEqual(groups_by_strategy["request_id"]["key"], {"request_id": "req-1"})
        self.assertEqual(groups_by_strategy["url_path_method"]["key"], {"url_path": "/app/api/search", "method": "GET"})
        self.assertEqual(groups_by_strategy["function_name"]["key"], {"function_name": "buildSign"})
        self.assertFalse(groups_by_strategy["url_path_method"]["stitching"])
        self.assertEqual(groups_by_strategy["function_name"]["scope"], "correlation-hints-only")
        self.assertEqual(groups_by_strategy["request_id"]["verification"]["status"], "reviewable")
        self.assertEqual(groups_by_strategy["url_path_method"]["verification"]["status"], "reviewable")
        self.assertEqual(groups_by_strategy["function_name"]["verification"]["status"], "reviewable")
        self.assertFalse(groups_by_strategy["function_name"]["verification"]["automatic_stitching"])
        self.assertGreaterEqual(flow_timeline["stitch_candidate_count"], 3)
        candidates_by_strategy = {candidate["strategy"]: candidate for candidate in flow_timeline["stitch_candidates"]}
        self.assertEqual(candidates_by_strategy["function_name"]["readiness"], "reviewable")
        self.assertFalse(candidates_by_strategy["function_name"]["automatic_stitching"])
        self.assertFalse(candidates_by_strategy["function_name"]["stitching"])
        self.assertEqual(candidates_by_strategy["function_name"]["scope"], "manual-stitch-candidate-only")
        self.assertGreaterEqual(flow_timeline["auto_stitch_dry_run_count"], 3)
        self.assertEqual(flow_timeline["auto_stitch_conflict_resolution_count"], flow_timeline["auto_stitch_dry_run_count"])
        self.assertFalse(flow_timeline["auto_stitch_conflict_resolution_summary"]["would_materialize"])
        self.assertEqual(flow_timeline["auto_stitch_policy_decision_count"], flow_timeline["auto_stitch_dry_run_count"])
        self.assertFalse(flow_timeline["auto_stitch_policy_summary"]["would_materialize"])
        self.assertEqual(flow_timeline["auto_stitch_materialization_plan_count"], 0)
        self.assertFalse(flow_timeline["auto_stitch_materialization_summary"]["writes_artifact"])
        dry_runs_by_strategy = {dry_run["strategy"]: dry_run for dry_run in flow_timeline["auto_stitch_dry_runs"]}
        self.assertTrue(dry_runs_by_strategy["function_name"]["dry_run"])
        self.assertTrue(dry_runs_by_strategy["function_name"]["review_required"])
        self.assertFalse(dry_runs_by_strategy["function_name"]["would_materialize"])
        self.assertFalse(dry_runs_by_strategy["function_name"]["automatic_stitching"])
        self.assertEqual(dry_runs_by_strategy["function_name"]["scope"], "auto-stitch-dry-run-only")
        self.assertEqual(flow_timeline["stitch_proposal_count"], 0)
        self.assertEqual(flow_timeline["stitch_proposals"], [])
        manifest_by_key = {entry["artifact_key"]: entry for entry in manifest["entries"]}
        self.assertEqual(manifest_by_key["workspace_dom_snapshot"]["metadata"]["browser_provider"], "fake-native")
        self.assertEqual(manifest_by_key["workspace_script_inventory"]["category"], "source")
        self.assertEqual(manifest_by_key["workspace_navigation_events"]["category"], "trace")
        self.assertEqual(manifest_by_key["workspace_response_bodies"]["category"], "network")
        self.assertEqual(manifest_by_key["workspace_websocket_frames"]["category"], "network")
        self.assertEqual(manifest_by_key["workspace_hook_timeline"]["category"], "hook-timeline")
        self.assertEqual(manifest_by_key["workspace_flow_timeline"]["category"], "trace")
        self.assertEqual(manifest_by_key["workspace_flow_timeline"]["metadata"]["browser_provider"], "fake-native")
        self.assertEqual(manifest_by_key["workspace_function_validations"]["category"], "trace")

    def test_native_web_runtime_apply_minimal_protection_installs_hooks(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("console.clear", {"reason": "unit-test"})
        self.assertEqual(result.status.value, "success")
        self.assertIn("install_hook:fetch_xhr", result.applied_actions)
        self.assertEqual(result.next_action, "resume_recon")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/hook-timeline.json")

    def test_native_web_runtime_apply_minimal_protection_installs_function_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "hook-function",
            {
                "function_name": "buildSign",
                "function_paths": ["window.buildSign"],
                "candidate_id": "script-1:buildSign",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            },
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["install_function_hook:buildSign"])
        self.assertIn("function_hook_status=success", result.verification)
        self.assertIn("function_hook_installed_count=1", result.verification)
        self.assertIn("function_hook_event_count=2", result.verification)
        self.assertEqual(result.next_action, "inspect_function_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/function-hooks.json")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/function-hook-timeline.json")
        self.assertEqual(result.artifacts[1].metadata["event_count"], 2)

    def test_native_web_runtime_apply_minimal_protection_installs_module_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "hook-module",
            {
                "module_id": "731",
                "export_name": "sign",
                "require_path": "window.__webpack_require__",
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["install_module_hook:731:sign"])
        self.assertIn("module_hook_status=success", result.verification)
        self.assertIn("module_hook_installed_count=1", result.verification)
        self.assertIn("module_hook_event_count=2", result.verification)
        self.assertEqual(result.next_action, "inspect_module_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-hooks.json")
        self.assertEqual(result.artifacts[0].metadata["module_id"], "731")
        self.assertEqual(result.artifacts[0].metadata["export_name"], "sign")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-hook-timeline.json")
        self.assertEqual(result.artifacts[1].metadata["event_count"], 2)

    def test_native_web_runtime_apply_minimal_protection_discovers_module_candidates(self) -> None:
        provider = FakeProvider()
        provider.session.context.pages[0].external_source = WEBPACK_MINIFIED_SOURCE
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("module-discovery", {"module_query": "sign"})

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["discover_module_exports"])
        self.assertIn("module_discovery_status=success", result.verification)
        self.assertIn("module_discovery_script_count=2", result.verification)
        self.assertIn("module_discovery_module_count=1", result.verification)
        self.assertIn("module_discovery_candidate_count=1", result.verification)
        self.assertEqual(result.next_action, "install_module_hook_from_candidate")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-registry.json")
        self.assertEqual(result.artifacts[0].metadata["module_count"], 1)
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-candidates.json")
        self.assertEqual(result.artifacts[1].metadata["candidate_count"], 1)

    def test_native_web_runtime_apply_minimal_protection_introspects_runtime_module_cache(self) -> None:
        provider = FakeProvider()
        provider.session.context.pages[0].runtime_module_payload = {
            "ok": True,
            "status": "success",
            "requirePath": "window.__webpack_require__",
            "cacheKeyCount": 1,
            "registryKeyCount": 0,
            "cacheModules": [
                {
                    "moduleId": "732",
                    "exportNames": ["runtimeSign"],
                    "exportTypes": {"runtimeSign": "function"},
                    "sourcePreview": "function runtimeSign(keyword) { return keyword; }",
                }
            ],
            "registryModules": [],
        }
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("module-discovery", {"module_query": "runtimeSign"})

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["discover_module_exports"])
        self.assertIn("module_discovery_runtime_status=success", result.verification)
        self.assertIn("module_discovery_runtime_module_count=1", result.verification)
        self.assertIn("module_discovery_module_count=1", result.verification)
        self.assertIn("module_discovery_candidate_count=1", result.verification)
        self.assertEqual(result.artifacts[0].metadata["runtime_status"], "success")
        self.assertEqual(result.artifacts[0].metadata["runtime_module_count"], 1)
        self.assertEqual(result.artifacts[1].metadata["candidate_count"], 1)

    def test_native_web_runtime_apply_minimal_protection_discovers_custom_and_federated_runtime_modules(self) -> None:
        provider = FakeProvider()
        provider.session.context.pages[0].runtime_module_payload = {
            "ok": True,
            "status": "success",
            "requirePath": "window.__webpack_require__",
            "runtimes": [
                {
                    "runtimePath": "window.__viteModules",
                    "runtimeKind": "object-runtime",
                    "customKeyCount": 1,
                    "customRuntimeModules": [
                        {
                            "moduleId": "/src/sign.ts",
                            "exportNames": ["buildSign"],
                            "exportTypes": {"buildSign": "function"},
                            "hookPaths": ["window.__viteModules[\"/src/sign.ts\"].buildSign"],
                            "sourcePreview": "function buildSign(keyword) { return keyword; }",
                        }
                    ],
                },
                {
                    "runtimePath": "window.remoteApp",
                    "runtimeKind": "module-federation",
                    "federationKeyCount": 1,
                    "federationModules": [
                        {
                            "moduleId": "./sign",
                            "exportNames": ["sign"],
                            "hookPaths": ["window.remoteApp.__reverseAgentExposes[\"./sign\"].sign"],
                            "sourcePreview": "function sign(keyword) { return keyword; }",
                        }
                    ],
                },
            ],
        }
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-discovery",
            {
                "module_query": "sign",
                "module_runtime_paths": ["window.__webpack_require__", "window.__viteModules", "window.remoteApp"],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["discover_module_exports"])
        self.assertIn("module_discovery_runtime_kinds=['object-runtime', 'module-federation']", result.verification)
        self.assertIn("module_discovery_custom_key_count=1", result.verification)
        self.assertIn("module_discovery_federation_key_count=1", result.verification)
        self.assertIn("module_discovery_candidate_count=2", result.verification)
        self.assertEqual(result.next_action, "install_module_hook_from_candidate")
        self.assertEqual(result.artifacts[0].metadata["runtime_kinds"], ["object-runtime", "module-federation"])
        self.assertEqual(result.artifacts[0].metadata["runtime_paths"], ["window.__viteModules", "window.remoteApp"])
        self.assertEqual(result.artifacts[0].metadata["custom_key_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["federation_key_count"], 1)
        self.assertEqual(result.artifacts[1].metadata["candidate_count"], 2)

    def test_native_web_runtime_apply_minimal_protection_reviews_async_chunk_graph(self) -> None:
        provider = FakeProvider()
        provider.session.context.pages[0].external_source = """
        const lazySign = () => import("./chunks/sign-panel.js");
        importScripts("/workers/sign-worker.js");
        """
        provider.session.context.pages[0].runtime_module_payload = {
            "ok": True,
            "status": "partial",
            "requirePath": "window.__webpack_require__",
            "chunkGraph": {
                "loaderCapabilities": {
                    "hasEnsureChunk": True,
                    "hasChunkFilenameResolver": True,
                    "loaderRegistryKeys": ["j"],
                    "publicPath": "/assets/",
                },
                "asyncChunks": [{"chunkId": "731", "target": "/assets/731.js", "loaderKind": "webpack-runtime"}],
            },
            "cacheModules": [],
            "registryModules": [],
        }
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection("module-discovery", {"module_query": "sign"})

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["discover_async_chunk_graph"])
        self.assertIn("module_discovery_chunk_graph_status=success", result.verification)
        self.assertIn("module_discovery_chunk_graph_candidate_count=3", result.verification)
        self.assertIn("module_discovery_chunk_graph_script_edge_count=2", result.verification)
        self.assertIn("module_discovery_chunk_graph_runtime_loader_count=1", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_graph_before_loading")
        self.assertEqual(result.artifacts[0].metadata["chunk_graph_status"], "success")
        self.assertEqual(result.artifacts[0].metadata["chunk_graph_candidate_count"], 3)
        self.assertEqual(result.artifacts[0].metadata["chunk_graph_runtime_loader_count"], 1)

    def test_native_web_runtime_plans_async_chunk_load_without_execution_by_default(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-load",
            {
                "chunk_id": "731",
                "target": "/assets/731.js",
                "loader_kind": "webpack-runtime",
                "runtime_path": "window.__webpack_require__",
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_load"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_load_status=planned", result.verification)
        self.assertIn("async_chunk_load_execution_attempted=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_load_plan_before_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-load-plan.json")
        self.assertEqual(result.artifacts[0].metadata["plan_status"], "ready_for_review")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/async-chunk-load-result.json")
        self.assertFalse(result.artifacts[1].metadata["execution_attempted"])

    def test_native_web_runtime_plans_custom_loader_traversal_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-plan",
            {
                "custom_loader_candidates": [
                    {
                        "chunk_id": "custom-sign",
                        "target": "window.__customLoader.load",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                        "runtime_path": "window.__customLoader",
                    }
                ]
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("custom_loader_traversal_plan_status=planned", result.verification)
        self.assertIn("custom_loader_traversal_candidate_count=1", result.verification)
        self.assertIn("custom_loader_traversal_ready_for_review_count=1", result.verification)
        self.assertIn("custom_loader_traversal_blocked_execution_count=1", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-plan.json")
        self.assertEqual(result.artifacts[0].metadata["plan_status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["custom_candidate_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_plans_module_federation_get_init_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-get-init-plan",
            {
                "module_federation_candidates": [
                    {
                        "runtime_path": "window.remoteApp",
                        "module_id": "./sign",
                        "export_names": ["sign"],
                        "hook_paths": ["window.remoteApp.__reverseAgentExposes[\"./sign\"].sign"],
                        "discovery_source": "module_federation",
                    }
                ]
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_get_init"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("module_federation_get_init_plan_status=planned", result.verification)
        self.assertIn("module_federation_get_init_candidate_count=1", result.verification)
        self.assertIn("module_federation_get_init_container_count=1", result.verification)
        self.assertIn("module_federation_get_init_exposed_module_count=1", result.verification)
        self.assertIn("module_federation_get_init_function_path_candidate_count=1", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_get_init_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-get-init-plan.json")
        self.assertEqual(result.artifacts[0].metadata["plan_status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["container_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_executes_reviewed_async_chunk_load(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-load",
            {
                "chunk_id": "731",
                "target": "/assets/731.js",
                "loader_kind": "webpack-runtime",
                "runtime_path": "window.__webpack_require__",
                "execute_chunk_load": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_async_chunk_load:731"])
        self.assertEqual(page.async_chunk_loads, ["731"])
        self.assertIn("async_chunk_load_status=success", result.verification)
        self.assertIn("async_chunk_load_execution_attempted=True", result.verification)
        self.assertIn("async_chunk_load_execution_ok=True", result.verification)
        self.assertIn("async_chunk_load_added_registry_key_count=1", result.verification)
        self.assertEqual(result.next_action, "inspect_module_registry_diff_after_chunk_load")
        self.assertTrue(result.artifacts[1].metadata["execution_ok"])
        self.assertEqual(result.artifacts[1].metadata["added_registry_key_count"], 1)

    def test_native_web_runtime_executes_reviewed_module_federation_get_init_probe(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-get-init",
            {
                "module_federation_candidates": [
                    {
                        "kind": "module-federation",
                        "runtime_path": "window.remoteOther",
                        "module_id": "./token",
                        "export_names": [],
                        "hook_paths": [],
                        "discovery_source": "module_federation",
                    }
                ],
                "execute_module_federation_get_init": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["probe_module_federation_get_init"])
        self.assertEqual(page.module_federation_get_init_probes, ["./token"])
        self.assertIn("module_federation_get_init_probe_status=success", result.verification)
        self.assertIn("module_federation_get_init_execution_attempted=True", result.verification)
        self.assertIn("module_federation_get_init_execution_ok=True", result.verification)
        self.assertIn("module_federation_get_init_container_init_called=True", result.verification)
        self.assertIn("module_federation_get_init_remote_get_called=True", result.verification)
        self.assertIn("module_federation_get_init_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_get_init_added_shared_scope_key_count=1", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_get_init_probe_before_factory_invocation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-get-init-plan.json")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-federation-get-init-result.json")
        self.assertTrue(result.artifacts[1].metadata["execution_ok"])
        self.assertTrue(result.artifacts[1].metadata["container_init_called"])
        self.assertTrue(result.artifacts[1].metadata["remote_get_called"])
        self.assertFalse(result.artifacts[1].metadata["remote_factory_invoked"])
        self.assertEqual(result.artifacts[1].metadata["added_shared_scope_key_count"], 1)
        self.assertEqual(result.artifacts[1].metadata["factory_type"], "function")

    def test_native_web_runtime_executes_reviewed_module_federation_factory_invoke(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-get-init",
            {
                "module_federation_candidates": [
                    {
                        "kind": "module-federation",
                        "runtime_path": "window.remoteOther",
                        "module_id": "./token",
                        "export_names": [],
                        "hook_paths": [],
                        "discovery_source": "module_federation",
                    }
                ],
                "execute_module_federation_factory": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["invoke_module_federation_factory"])
        self.assertEqual(page.module_federation_get_init_probes, ["./token"])
        self.assertEqual(page.module_federation_factory_invocations, ["./token"])
        self.assertIn("module_federation_factory_invoke_status=success", result.verification)
        self.assertIn("module_federation_get_init_execution_attempted=True", result.verification)
        self.assertIn("module_federation_get_init_remote_get_called=True", result.verification)
        self.assertIn("module_federation_factory_execution_attempted=True", result.verification)
        self.assertIn("module_federation_factory_execution_ok=True", result.verification)
        self.assertIn("module_federation_factory_remote_factory_invoked=True", result.verification)
        self.assertIn("module_federation_factory_remote_code_executed=True", result.verification)
        self.assertIn("module_federation_factory_export_count=1", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_factory_exports_before_hooking")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-get-init-plan.json")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-federation-factory-invoke-result.json")
        self.assertTrue(result.artifacts[1].metadata["factory_ok"])
        self.assertTrue(result.artifacts[1].metadata["remote_factory_invoked"])
        self.assertTrue(result.artifacts[1].metadata["remote_code_executed"])
        self.assertEqual(result.artifacts[1].metadata["export_count"], 1)
        self.assertEqual(result.artifacts[1].metadata["module_type"], "object")

    def test_native_web_runtime_plans_module_federation_export_hooks_from_factory_result(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-export-hook-plan",
            {
                "module_federation_factory_invoke_result": {
                    "status": "success",
                    "factory_execution": {
                        "remoteFactoryInvoked": True,
                        "remoteCodeExecuted": True,
                        "containerPath": "window.remoteOther",
                        "exposedName": "./token",
                        "moduleType": "object",
                        "exportNames": ["token"],
                        "exportPreviews": {"token": {"type": "function", "name": "token"}},
                    },
                }
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_export_hooks"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_export_hook_plan_status=planned", result.verification)
        self.assertIn("module_federation_export_hook_candidate_count=1", result.verification)
        self.assertIn("module_federation_export_hook_hookable_candidate_count=1", result.verification)
        self.assertIn("module_federation_export_hook_automatic_hook_installation=False", result.verification)
        self.assertIn("module_federation_export_hook_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_export_hook_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-export-hook-plan.json")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["hookable_candidate_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_hook_installation"])
        self.assertFalse(result.artifacts[0].metadata["recursive_federation_traversal"])

    def test_native_web_runtime_apply_minimal_protection_builds_flow_timeline(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-2",
                "request_id": "req-2",
                "previous_flow_timeline": {
                    "entries": [
                        {"sequence": 0, "flow_id": "sign-flow", "source": "network_requests", "type": "network.request"}
                    ]
                },
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST"}]},
                "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign", "method": "POST"}}]}},
                "debugger_timeline": {"entries": [{"type": "breakpoint.hit", "callFrameId": "cf-1"}]},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["build_flow_timeline"])
        self.assertIn("flow_timeline_status=success", result.verification)
        self.assertIn("flow_timeline_entry_count=4", result.verification)
        self.assertIn("flow_timeline_previous_entry_count=1", result.verification)
        self.assertIn("flow_timeline_new_entry_count=3", result.verification)
        self.assertIn("flow_timeline_correlation_group_count=1", result.verification)
        self.assertIn("flow_timeline_stitch_candidate_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_dry_run_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_conflict_resolution_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_policy_decision_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_plan_count=0", result.verification)
        self.assertIn("flow_timeline_stitch_proposal_count=0", result.verification)
        self.assertIn("flow_timeline_automatic_stitching=False", result.verification)
        self.assertIn("flow_timeline_continued_from_previous=True", result.verification)
        self.assertEqual(result.next_action, "inspect_flow_timeline_or_continue_next_request")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/flow-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["flow_id"], "sign-flow")
        self.assertEqual(result.artifacts[0].metadata["entry_count"], 4)
        self.assertEqual(result.artifacts[0].metadata["previous_entry_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["new_entry_count"], 3)
        self.assertEqual(result.artifacts[0].metadata["correlation_group_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["stitch_candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_dry_run_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_conflict_resolution_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_conflict_resolution_summary"]["no_conflict_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["auto_stitch_conflict_resolution_summary"]["would_materialize"])
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_policy_decision_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["auto_stitch_policy_summary"]["would_materialize"])
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_materialization_plan_count"], 0)
        self.assertFalse(result.artifacts[0].metadata["auto_stitch_materialization_summary"]["writes_artifact"])
        self.assertEqual(result.artifacts[0].metadata["stitch_proposal_count"], 0)
        self.assertFalse(result.artifacts[0].metadata["automatic_stitching"])
        self.assertTrue(result.artifacts[0].metadata["continued_from_previous"])
        self.assertEqual(result.artifacts[0].metadata["source_counts"]["network_requests"], 1)
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/auto-stitch-conflict-resolutions.json")
        self.assertEqual(result.artifacts[1].metadata["count"], 1)
        self.assertFalse(result.artifacts[1].metadata["would_materialize"])

    def test_native_web_runtime_materializes_review_approved_stitched_flow(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-2",
                "request_id": "req-2",
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST", "requestId": "req-2"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-2",
                            "url": "https://example.test/api/sign",
                            "method": "POST",
                            "initiator": {"stack": {"callFrames": [{"functionName": "buildSign"}]}},
                        }
                    ]
                },
                "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"}}]}},
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
                "stitch_review_decisions": [
                    {"proposal_id": "stitch-proposal-1", "status": "approved", "approved": True, "reviewer": "unit-reviewer"}
                ],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["build_flow_timeline", "materialize_review_approved_stitched_flow"])
        self.assertIn("flow_timeline_stitch_proposal_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_dry_run_count=3", result.verification)
        self.assertIn("flow_timeline_auto_stitch_conflict_resolution_count=3", result.verification)
        self.assertIn("flow_timeline_auto_stitch_policy_decision_count=3", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_plan_count=0", result.verification)
        self.assertIn("flow_timeline_stitch_review_decision_count=1", result.verification)
        self.assertIn("flow_timeline_stitched_flow_count=1", result.verification)
        self.assertEqual(result.next_action, "inspect_stitched_flow_or_use_for_replay_planning")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/flow-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_dry_run_count"], 3)
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_conflict_resolution_count"], 3)
        self.assertTrue(result.artifacts[0].metadata["auto_stitch_conflict_resolution_summary"]["review_required"])
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_policy_decision_count"], 3)
        self.assertFalse(result.artifacts[0].metadata["auto_stitch_policy_summary"]["automatic_materialization_enabled"])
        self.assertEqual(result.artifacts[0].metadata["auto_stitch_materialization_plan_count"], 0)
        self.assertFalse(result.artifacts[0].metadata["auto_stitch_materialization_summary"]["materialization_enabled"])
        self.assertEqual(result.artifacts[0].metadata["stitch_proposal_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["stitch_review_decision_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["stitched_flow_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_stitching"])
        artifacts_by_path = {artifact.path: artifact for artifact in result.artifacts}
        self.assertEqual(artifacts_by_path["virtual://workspace/auto-stitch-conflict-resolutions.json"].metadata["count"], 3)
        self.assertFalse(artifacts_by_path["virtual://workspace/auto-stitch-conflict-resolutions.json"].metadata["would_materialize"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow.json"].metadata["count"], 1)
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow.json"].metadata["automatic_stitching"])

    def test_native_web_runtime_materializes_review_approved_auto_stitch_plan(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-2",
                "request_id": "req-2",
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST", "requestId": "req-2"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-2",
                            "url": "https://example.test/api/sign",
                            "method": "POST",
                            "initiator": {"stack": {"callFrames": [{"functionName": "buildSign"}]}},
                        }
                    ]
                },
                "hook_timeline": {"snapshot": {"events": [{"type": "fetch", "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"}}]}},
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
                "auto_stitch_policy": {
                    "policy_id": "runtime-policy",
                    "min_confidence_score": 0.85,
                    "allow_conflicts": True,
                    "enable_automatic_materialization": True,
                },
                "auto_stitch_materialization_review_decisions": [
                    {
                        "plan_id": "auto-stitch-materialization-plan-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "runtime-reviewer",
                    }
                ],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(
            result.applied_actions,
            [
                "build_flow_timeline",
                "materialize_review_approved_auto_stitch_plan",
                "write_stitched_flow_materialization_audit",
                "write_stitched_flow_rollback_plan",
                "write_stitched_flow_materialization_transaction_log",
                "plan_stitched_flow_rollback_execution",
                "materialize_review_approved_stitched_flow",
            ],
        )
        self.assertIn("flow_timeline_auto_stitch_materialization_plan_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_conflict_resolution_count=3", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_review_decision_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_result_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_audit_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_rollback_plan_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_materialization_transaction_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_rollback_execution_plan_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_rollback_execution_result_count=0", result.verification)
        self.assertIn("flow_timeline_stitch_review_decision_count=0", result.verification)
        self.assertIn("flow_timeline_stitched_flow_count=1", result.verification)
        self.assertIn("flow_timeline_automatic_stitching=False", result.verification)
        self.assertEqual(result.next_action, "inspect_stitched_flow_or_use_for_replay_planning")

        flow_metadata = result.artifacts[0].metadata
        self.assertEqual(flow_metadata["auto_stitch_conflict_resolution_count"], 3)
        self.assertTrue(flow_metadata["auto_stitch_conflict_resolution_summary"]["review_required"])
        self.assertEqual(flow_metadata["auto_stitch_materialization_plan_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_review_decision_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_result_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_result_summary"]["materialized_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_materialization_result_summary"]["writes_artifact"])
        self.assertFalse(flow_metadata["auto_stitch_materialization_result_summary"]["automatic_stitching"])
        self.assertEqual(flow_metadata["auto_stitch_materialization_audit_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_audit_summary"]["audit_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_audit_summary"]["missing_audit_count"], 0)
        self.assertEqual(flow_metadata["auto_stitch_materialization_rollback_plan_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_rollback_summary"]["rollback_plan_count"], 1)
        self.assertFalse(flow_metadata["auto_stitch_materialization_rollback_summary"]["automatic_rollback"])
        self.assertEqual(flow_metadata["auto_stitch_materialization_transaction_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_transaction_summary"]["transaction_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_materialization_transaction_summary"]["ready_transaction_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_materialization_transaction_summary"]["transaction_log_only"])
        self.assertEqual(flow_metadata["auto_stitch_rollback_execution_plan_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_rollback_execution_summary"]["execution_plan_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_rollback_execution_summary"]["dry_run_only_by_default"])
        self.assertEqual(flow_metadata["auto_stitch_rollback_execution_result_count"], 0)
        self.assertEqual(flow_metadata["stitch_review_decision_count"], 0)
        self.assertEqual(flow_metadata["stitched_flow_count"], 1)
        self.assertFalse(flow_metadata["automatic_stitching"])

        artifacts_by_path = {artifact.path: artifact for artifact in result.artifacts}
        self.assertEqual(artifacts_by_path["virtual://workspace/auto-stitch-conflict-resolutions.json"].metadata["count"], 3)
        self.assertFalse(artifacts_by_path["virtual://workspace/auto-stitch-conflict-resolutions.json"].metadata["would_materialize"])
        self.assertEqual(artifacts_by_path["virtual://workspace/auto-stitch-materialization-results.json"].metadata["count"], 1)
        self.assertEqual(artifacts_by_path["virtual://workspace/auto-stitch-materialization-results.json"].metadata["summary"]["materialized_count"], 1)
        self.assertFalse(artifacts_by_path["virtual://workspace/auto-stitch-materialization-results.json"].metadata["automatic_stitching"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-materialization-audit.json"].metadata["count"], 1)
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-materialization-audit.json"].metadata["automatic_stitching"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-materialization-audit.json"].metadata["summary"]["audit_count"], 1)
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-rollback-plan.json"].metadata["count"], 1)
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-rollback-plan.json"].metadata["automatic_stitching"])
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-rollback-plan.json"].metadata["automatic_rollback"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-rollback-plan.json"].metadata["summary"]["rollback_plan_count"], 1)
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-materialization-transactions.json"].metadata["count"], 1)
        self.assertEqual(
            artifacts_by_path["virtual://workspace/stitched-flow-materialization-transactions.json"].metadata["summary"]["ready_transaction_count"],
            1,
        )
        self.assertTrue(artifacts_by_path["virtual://workspace/stitched-flow-materialization-transactions.json"].metadata["transaction_log_only"])
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-materialization-transactions.json"].metadata["automatic_rollback"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-rollback-executions.json"].metadata["plan_count"], 1)
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow-rollback-executions.json"].metadata["result_count"], 0)
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-rollback-executions.json"].metadata["target_artifact_mutated"])
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow-rollback-executions.json"].metadata["automatic_rollback"])
        self.assertEqual(artifacts_by_path["virtual://workspace/stitched-flow.json"].metadata["count"], 1)
        self.assertFalse(artifacts_by_path["virtual://workspace/stitched-flow.json"].metadata["automatic_stitching"])

    def test_native_web_runtime_recomputes_review_gate_after_approved_rollback_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-rollback",
                "request_id": "req-rollback",
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST", "requestId": "req-rollback"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-rollback",
                            "url": "https://example.test/api/sign",
                            "method": "POST",
                            "initiator": {"stack": {"callFrames": [{"functionName": "buildSign"}]}},
                        }
                    ]
                },
                "hook_timeline": {
                    "snapshot": {
                        "events": [
                            {
                                "type": "fetch",
                                "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"},
                            }
                        ]
                    }
                },
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
                "auto_stitch_policy": {
                    "policy_id": "runtime-policy",
                    "min_confidence_score": 0.85,
                    "allow_conflicts": True,
                    "enable_automatic_materialization": True,
                },
                "auto_stitch_materialization_review_decisions": [
                    {
                        "plan_id": "auto-stitch-materialization-plan-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "runtime-reviewer",
                    }
                ],
                "auto_stitch_rollback_execution_review_decisions": [
                    {
                        "rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "rollback-reviewer",
                    }
                ],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("record_review_approved_rollback_execution", result.applied_actions)
        self.assertIn("recompute_review_gate_after_rollback", result.applied_actions)
        self.assertIn("plan_physical_rollback_dry_run_diff", result.applied_actions)
        self.assertNotIn("apply_review_approved_physical_rollback", result.applied_actions)
        self.assertIn("flow_timeline_auto_stitch_rollback_execution_result_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_rollback_review_gate_recomputation_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_physical_rollback_dry_run_diff_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_physical_rollback_result_count=0", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_physical_rollback_review_gate_rerun_count=0", result.verification)
        self.assertIn("flow_timeline_auto_stitch_standard_review_gate_replacement_result_count=0", result.verification)

        flow_metadata = result.artifacts[0].metadata
        self.assertEqual(flow_metadata["auto_stitch_rollback_execution_result_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_rollback_review_gate_recomputation_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_rollback_review_gate_recomputation_summary"]["blocked_count"], 1)
        self.assertFalse(flow_metadata["auto_stitch_rollback_review_gate_recomputation_summary"]["physical_artifact_mutated"])
        self.assertEqual(flow_metadata["auto_stitch_physical_rollback_dry_run_diff_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_physical_rollback_dry_run_diff_summary"]["dry_run_diff_count"], 1)
        self.assertFalse(flow_metadata["auto_stitch_physical_rollback_dry_run_diff_summary"]["physical_artifact_mutated"])
        self.assertEqual(flow_metadata["auto_stitch_physical_rollback_result_count"], 0)
        self.assertFalse(flow_metadata["auto_stitch_physical_rollback_result_summary"]["target_artifact_mutated"])
        self.assertEqual(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_count"], 0)
        self.assertEqual(flow_metadata["auto_stitch_standard_review_gate_replacement_result_count"], 0)

        artifacts_by_path = {artifact.path: artifact for artifact in result.artifacts}
        gate_artifact = artifacts_by_path["virtual://workspace/review-gate-after-rollback.json"]
        self.assertEqual(gate_artifact.metadata["count"], 1)
        self.assertEqual(gate_artifact.metadata["summary"]["recomputation_count"], 1)
        self.assertTrue(gate_artifact.metadata["summary"]["does_not_replace_review_gate"])
        self.assertFalse(gate_artifact.metadata["delivery_allowed"])
        self.assertFalse(gate_artifact.metadata["target_artifact_mutated"])
        self.assertFalse(gate_artifact.metadata["automatic_rollback"])
        diff_artifact = artifacts_by_path["virtual://workspace/stitched-flow-physical-rollback-diff.json"]
        self.assertEqual(diff_artifact.metadata["count"], 1)
        self.assertEqual(diff_artifact.metadata["summary"]["dry_run_diff_count"], 1)
        self.assertTrue(diff_artifact.metadata["dry_run_only"])
        self.assertTrue(diff_artifact.metadata["would_mutate_if_approved"])
        self.assertFalse(diff_artifact.metadata["would_replace_review_gate"])
        self.assertFalse(diff_artifact.metadata["target_artifact_mutated"])
        self.assertFalse(diff_artifact.metadata["automatic_rollback"])

    def test_native_web_runtime_applies_review_approved_physical_rollback(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-physical-rollback",
                "request_id": "req-physical-rollback",
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST", "requestId": "req-physical-rollback"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-physical-rollback",
                            "url": "https://example.test/api/sign",
                            "method": "POST",
                            "initiator": {"stack": {"callFrames": [{"functionName": "buildSign"}]}},
                        }
                    ]
                },
                "hook_timeline": {
                    "snapshot": {
                        "events": [
                            {
                                "type": "fetch",
                                "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"},
                            }
                        ]
                    }
                },
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
                "auto_stitch_policy": {
                    "policy_id": "runtime-policy",
                    "min_confidence_score": 0.85,
                    "allow_conflicts": True,
                    "enable_automatic_materialization": True,
                },
                "auto_stitch_materialization_review_decisions": [
                    {
                        "plan_id": "auto-stitch-materialization-plan-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "runtime-reviewer",
                    }
                ],
                "auto_stitch_rollback_execution_review_decisions": [
                    {
                        "rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "rollback-reviewer",
                    }
                ],
                "auto_stitch_physical_rollback_review_decisions": [
                    {
                        "dry_run_id": "stitched-flow-physical-rollback-diff-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "physical-rollback-reviewer",
                    }
                ],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("apply_review_approved_physical_rollback", result.applied_actions)
        self.assertIn("rerun_review_gate_after_physical_rollback", result.applied_actions)
        self.assertNotIn("replace_standard_review_gate_after_physical_rollback", result.applied_actions)
        self.assertIn("flow_timeline_auto_stitch_physical_rollback_review_decision_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_physical_rollback_result_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_physical_rollback_review_gate_rerun_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_standard_review_gate_replacement_result_count=0", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count=0", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count=0", result.verification)
        self.assertIn("flow_timeline_stitched_flow_count=0", result.verification)

        flow_metadata = result.artifacts[0].metadata
        self.assertEqual(flow_metadata["auto_stitch_physical_rollback_result_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_physical_rollback_result_summary"]["physical_rollback_applied_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_physical_rollback_result_summary"]["target_artifact_mutated"])
        self.assertTrue(flow_metadata["auto_stitch_physical_rollback_result_summary"]["standard_review_gate_rerun_required"])
        self.assertFalse(flow_metadata["auto_stitch_physical_rollback_result_summary"]["would_replace_review_gate"])
        self.assertEqual(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_summary"]["rerun_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_summary"]["blocked_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_summary"]["target_artifact_mutated"])
        self.assertTrue(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_summary"]["does_not_replace_review_gate"])
        self.assertFalse(flow_metadata["auto_stitch_post_physical_rollback_review_gate_rerun_summary"]["would_replace_review_gate"])
        self.assertEqual(flow_metadata["auto_stitch_standard_review_gate_replacement_result_count"], 0)
        self.assertFalse(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["standard_review_gate_replaced"])
        self.assertEqual(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count"], 0)
        self.assertFalse(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["delivery_allowed"])
        self.assertEqual(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count"], 0)
        self.assertFalse(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["package_ready"])
        self.assertEqual(flow_metadata["stitched_flow_count"], 0)

        artifacts_by_path = {artifact.path: artifact for artifact in result.artifacts}
        result_artifact = artifacts_by_path["virtual://workspace/stitched-flow-physical-rollback-results.json"]
        self.assertEqual(result_artifact.metadata["count"], 1)
        self.assertEqual(result_artifact.metadata["summary"]["physical_rollback_applied_count"], 1)
        self.assertTrue(result_artifact.metadata["target_artifact_mutated"])
        self.assertFalse(result_artifact.metadata["automatic_rollback"])
        self.assertFalse(result_artifact.metadata["would_replace_review_gate"])
        gate_artifact = artifacts_by_path["virtual://workspace/review-gate-after-physical-rollback.json"]
        self.assertEqual(gate_artifact.metadata["count"], 1)
        self.assertEqual(gate_artifact.metadata["summary"]["rerun_count"], 1)
        self.assertTrue(gate_artifact.metadata["summary"]["does_not_replace_review_gate"])
        self.assertFalse(gate_artifact.metadata["delivery_allowed"])
        self.assertFalse(gate_artifact.metadata["automatic_rollback"])
        self.assertTrue(gate_artifact.metadata["target_artifact_mutated"])

    def test_native_web_runtime_records_review_approved_standard_review_gate_replacement(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "flow-timeline",
            {
                "flow_id": "sign-flow",
                "run_id": "run-gate-replacement",
                "request_id": "req-gate-replacement",
                "network_requests": {"items": [{"url": "https://example.test/api/sign", "method": "POST", "requestId": "req-gate-replacement"}]},
                "request_initiators": {
                    "items": [
                        {
                            "requestId": "req-gate-replacement",
                            "url": "https://example.test/api/sign",
                            "method": "POST",
                            "initiator": {"stack": {"callFrames": [{"functionName": "buildSign"}]}},
                        }
                    ]
                },
                "hook_timeline": {
                    "snapshot": {
                        "events": [
                            {
                                "type": "fetch",
                                "payload": {"url": "/api/sign", "method": "POST", "path": "window.buildSign", "functionName": "buildSign"},
                            }
                        ]
                    }
                },
                "replay_validation": {"validations": [{"candidate_id": "script-1:buildSign", "function_name": "buildSign", "replay_ok": True}]},
                "auto_stitch_policy": {
                    "policy_id": "runtime-policy",
                    "min_confidence_score": 0.85,
                    "allow_conflicts": True,
                    "enable_automatic_materialization": True,
                },
                "auto_stitch_materialization_review_decisions": [
                    {"plan_id": "auto-stitch-materialization-plan-1", "status": "approved", "approved": True}
                ],
                "auto_stitch_rollback_execution_review_decisions": [
                    {"rollback_execution_plan_id": "stitched-flow-rollback-execution-plan-1", "status": "approved", "approved": True}
                ],
                "auto_stitch_physical_rollback_review_decisions": [
                    {"dry_run_id": "stitched-flow-physical-rollback-diff-1", "status": "approved", "approved": True}
                ],
                "auto_stitch_standard_review_gate_replacement_review_decisions": [
                    {
                        "rerun_id": "stitched-flow-post-physical-rollback-review-gate-rerun-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "gate-reviewer",
                    }
                ],
                "auto_stitch_transaction_commit_review_decisions": [
                    {
                        "final_delivery_package_id": "standard-review-gate-replacement-final-delivery-package-1",
                        "status": "approved",
                        "approved": True,
                        "reviewer": "transaction-reviewer",
                    }
                ],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("replace_standard_review_gate_after_physical_rollback", result.applied_actions)
        self.assertIn("rerun_delivery_guard_after_standard_review_gate_replacement", result.applied_actions)
        self.assertIn("package_final_delivery_after_standard_review_gate_replacement", result.applied_actions)
        self.assertIn("record_final_delivery_transaction_commit", result.applied_actions)
        self.assertIn("flow_timeline_auto_stitch_standard_review_gate_replacement_review_decision_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_standard_review_gate_replacement_result_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count=1", result.verification)
        self.assertIn("flow_timeline_auto_stitch_transaction_commit_result_count=1", result.verification)

        flow_metadata = result.artifacts[0].metadata
        self.assertEqual(flow_metadata["auto_stitch_standard_review_gate_replacement_result_count"], 1)
        self.assertEqual(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["replacement_result_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["standard_review_gate_replaced"])
        self.assertTrue(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["delivery_guard_rerun_required"])
        self.assertFalse(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["delivery_allowed"])
        self.assertFalse(flow_metadata["auto_stitch_standard_review_gate_replacement_summary"]["automatic_delivery"])
        self.assertEqual(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count"], 1)
        self.assertTrue(
            flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["delivery_guard_rerun_performed"]
        )
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["delivery_guard_passed"])
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["delivery_allowed"])
        self.assertFalse(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["automatic_delivery"])
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"]["manual_delivery_required"])
        self.assertEqual(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["package_ready"])
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["final_delivery_packaged"])
        self.assertTrue(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["delivery_allowed"])
        self.assertFalse(flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["automatic_delivery"])
        self.assertFalse(
            flow_metadata["auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"]["cross_run_transaction_committed"]
        )
        self.assertEqual(flow_metadata["auto_stitch_transaction_commit_result_count"], 1)
        self.assertTrue(flow_metadata["auto_stitch_transaction_commit_summary"]["transaction_commit_recorded"])
        self.assertTrue(flow_metadata["auto_stitch_transaction_commit_summary"]["artifact_model_transaction_commit_recorded"])
        self.assertFalse(flow_metadata["auto_stitch_transaction_commit_summary"]["cross_run_transaction_committed"])
        self.assertFalse(flow_metadata["auto_stitch_transaction_commit_summary"]["manifest_revision_committed"])
        self.assertFalse(flow_metadata["auto_stitch_transaction_commit_summary"]["external_delivery_performed"])
        self.assertFalse(flow_metadata["auto_stitch_transaction_commit_summary"]["filesystem_artifact_mutated"])

        artifacts_by_path = {artifact.path: artifact for artifact in result.artifacts}
        gate_artifact = artifacts_by_path["virtual://workspace/review-gate-after-physical-rollback.json"]
        self.assertFalse(gate_artifact.metadata["does_not_replace_review_gate"])
        self.assertFalse(gate_artifact.metadata["summary"]["does_not_replace_review_gate"])
        replacement_artifact = artifacts_by_path["virtual://workspace/review-gate-replacement-results.json"]
        self.assertEqual(replacement_artifact.metadata["count"], 1)
        self.assertTrue(replacement_artifact.metadata["standard_review_gate_replaced"])
        self.assertTrue(replacement_artifact.metadata["target_artifact_mutated"])
        self.assertFalse(replacement_artifact.metadata["delivery_allowed"])
        self.assertFalse(replacement_artifact.metadata["automatic_delivery"])
        self.assertFalse(replacement_artifact.metadata["automatic_rollback"])
        delivery_guard_artifact = artifacts_by_path["virtual://workspace/delivery-guard-after-review-gate-replacement.json"]
        self.assertEqual(delivery_guard_artifact.metadata["count"], 1)
        self.assertTrue(delivery_guard_artifact.metadata["delivery_guard_rerun_performed"])
        self.assertTrue(delivery_guard_artifact.metadata["delivery_guard_passed"])
        self.assertTrue(delivery_guard_artifact.metadata["delivery_allowed"])
        self.assertFalse(delivery_guard_artifact.metadata["automatic_delivery"])
        self.assertTrue(delivery_guard_artifact.metadata["manual_delivery_required"])
        self.assertFalse(delivery_guard_artifact.metadata["automatic_rollback"])
        final_package_artifact = artifacts_by_path["virtual://workspace/final-delivery-package-after-review-gate-replacement.json"]
        self.assertEqual(final_package_artifact.metadata["count"], 1)
        self.assertTrue(final_package_artifact.metadata["package_ready"])
        self.assertTrue(final_package_artifact.metadata["final_delivery_packaged"])
        self.assertTrue(final_package_artifact.metadata["delivery_allowed"])
        self.assertFalse(final_package_artifact.metadata["automatic_delivery"])
        self.assertTrue(final_package_artifact.metadata["manual_delivery_required"])
        self.assertFalse(final_package_artifact.metadata["cross_run_transaction_committed"])
        self.assertFalse(final_package_artifact.metadata["manifest_revision_committed"])
        self.assertFalse(final_package_artifact.metadata["external_delivery_performed"])
        commit_artifact = artifacts_by_path["virtual://workspace/final-delivery-transaction-commit.json"]
        self.assertEqual(commit_artifact.metadata["count"], 1)
        self.assertTrue(commit_artifact.metadata["transaction_commit_recorded"])
        self.assertTrue(commit_artifact.metadata["artifact_model_transaction_commit_recorded"])
        self.assertFalse(commit_artifact.metadata["cross_run_transaction_committed"])
        self.assertFalse(commit_artifact.metadata["manifest_revision_committed"])
        self.assertFalse(commit_artifact.metadata["automatic_delivery"])
        self.assertFalse(commit_artifact.metadata["external_delivery_performed"])
        self.assertFalse(commit_artifact.metadata["filesystem_artifact_mutated"])

    def test_native_web_runtime_apply_minimal_protection_discovers_closure_scope_functions(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "closure-function-discovery",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 4,
                "closure_function_names": ["buildSign", "nonce"],
                "trigger_expression": "debugger; 'scheduled'",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["discover_closure_scope_functions"])
        self.assertIn("closure_scope_discovery_status=success", result.verification)
        self.assertIn("closure_scope_function_count=2", result.verification)
        self.assertIn("closure_scope_candidate_count=1", result.verification)
        self.assertIn("closure_scope_callframe_count=1", result.verification)
        self.assertEqual(result.next_action, "inspect_closure_function_candidates")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-functions.json")
        self.assertEqual(result.artifacts[0].metadata["function_count"], 2)
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/closure-function-candidates.json")
        self.assertEqual(result.artifacts[1].metadata["candidate_count"], 1)
        self.assertFalse(result.artifacts[1].metadata["hook_supported"])


    def test_native_web_runtime_apply_minimal_protection_audits_object_root_mutation(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "object-root-mutation-audit",
            {
                "root_path": "window.__appState",
                "trigger_expression": "mutateNativeObjectRoot()",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["audit_object_root_mutation"])
        self.assertIn("object_root_mutation_audit_status=success", result.verification)
        self.assertIn("object_root_mutation_audit_root_path=window.__appState", result.verification)
        self.assertIn("object_root_mutation_audit_changed=True", result.verification)
        self.assertIn("object_root_mutation_audit_change_count=4", result.verification)
        self.assertIn("object_root_mutation_audit_getter_invocation=False", result.verification)
        self.assertEqual(result.next_action, "inspect_object_root_mutation_audit")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/object-root-mutation-audit.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "success")
        self.assertEqual(result.artifacts[0].metadata["root_path"], "window.__appState")
        self.assertTrue(result.artifacts[0].metadata["changed"])
        self.assertEqual(result.artifacts[0].metadata["change_count"], 4)
        self.assertEqual(result.artifacts[0].metadata["categories"], ["added", "descriptor", "removed", "value"])
        self.assertFalse(result.artifacts[0].metadata["getter_invocation"])

    def test_native_web_runtime_apply_minimal_protection_audits_page_mutation(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "page-mutation-audit",
            {
                "trigger_expression": "mutateNativePage()",
                "global_names": ["window.__token"],
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["audit_page_mutation"])
        self.assertIn("page_mutation_audit_status=success", result.verification)
        self.assertIn("page_mutation_audit_changed=True", result.verification)
        self.assertIn("page_mutation_audit_change_count=7", result.verification)
        self.assertEqual(result.next_action, "inspect_page_mutation_audit")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/page-mutation-audit.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "success")
        self.assertTrue(result.artifacts[0].metadata["changed"])
        self.assertEqual(result.artifacts[0].metadata["change_count"], 7)
        self.assertEqual(result.artifacts[0].metadata["categories"], ["cookie", "dom", "global", "storage"])

    def test_native_web_runtime_apply_minimal_protection_captures_mutation_observer_timeline(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "mutation-observer-timeline",
            {
                "trigger_expression": "mutateNativePage()",
                "observer_wait_ms": 1,
                "mutation_record_limit": 20,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["observe_page_mutations"])
        self.assertIn("mutation_observer_timeline_status=success", result.verification)
        self.assertIn("mutation_observer_record_count=2", result.verification)
        self.assertIn("mutation_observer_types=['attributes', 'childList']", result.verification)
        self.assertIn("trigger_attempted=True", result.verification)
        self.assertEqual(result.next_action, "inspect_mutation_observer_timeline")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/mutation-observer-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "success")
        self.assertEqual(result.artifacts[0].metadata["record_count"], 2)
        self.assertEqual(result.artifacts[0].metadata["types"], ["attributes", "childList"])

    def test_native_web_runtime_plans_source_map_fetch_without_network_by_default(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-fetch",
            {
                "script_url": "https://example.test/assets/app.js",
                "script_source": "console.log('x');\n//# sourceMappingURL=app.js.map?token=secret",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_source_map_fetch"])
        self.assertIn("source_map_fetch_status=planned", result.verification)
        self.assertIn("source_map_fetch_allowed=True", result.verification)
        self.assertIn("source_map_fetch_attempted=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_fetch_plan_before_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-fetch-plan.json")
        self.assertTrue(result.artifacts[0].metadata["fetch_allowed"])
        self.assertEqual(result.artifacts[0].metadata["source_map_url_redacted"], "https://example.test/assets/app.js.map")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/source-map-fetch-result.json")
        self.assertFalse(result.artifacts[1].metadata["fetch_attempted"])

    def test_native_web_runtime_apply_minimal_protection_sets_source_logpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-logpoint",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 7,
                "column_number": 0,
                "log_expression": "window.buildSign('sign', 1700000000000)",
                "label": "smoke",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            },
        )
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["set_source_logpoint:.*app\\.js$:7"])
        self.assertIn("source_logpoint_status=success", result.verification)
        self.assertIn("source_logpoint_breakpoint_count=1", result.verification)
        self.assertIn("source_logpoint_event_count=1", result.verification)
        self.assertEqual(result.next_action, "inspect_source_logpoint_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-logpoints.json")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/source-logpoint-timeline.json")
        self.assertEqual(result.artifacts[1].metadata["event_count"], 1)
        page = provider.session.context.pages[0]
        self.assertIn("source_logpoint", page._cdp_session.last_breakpoint_params["condition"])

    def test_native_web_runtime_source_logpoint_uses_bundle_offset_remap(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-logpoint",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 99,
                "column_number": 9,
                "bundle_source": "alpha\nbeta\ngamma",
                "bundle_offset": 6,
                "log_expression": "window.buildSign('sign', 1700000000000)",
                "label": "smoke",
                "trigger_expression": "window.buildSign('sign', 1700000000000)",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["set_source_logpoint:.*app\\.js$:1"])
        self.assertIn("source_logpoint_remap_status=success", result.verification)
        self.assertIn("source_logpoint_remap_strategy=bundle_offset", result.verification)
        self.assertEqual(result.artifacts[0].metadata["line_number"], 1)
        self.assertEqual(result.artifacts[0].metadata["column_number"], 0)
        self.assertEqual(result.artifacts[0].metadata["remap"]["strategy"], "bundle_offset")
        page = provider.session.context.pages[0]
        self.assertEqual(page._cdp_session.last_breakpoint_params["lineNumber"], 1)
        self.assertEqual(page._cdp_session.last_breakpoint_params["columnNumber"], 0)

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
        self.assertIn("mutation_audit_count=2", result.verification)
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
        self.assertEqual(result.artifacts[4].path, "virtual://workspace/mutation-audit.json")
        self.assertEqual(result.artifacts[4].metadata["count"], 2)
        self.assertEqual(result.artifacts[4].metadata["policy"], "read_only")
        self.assertEqual(result.artifacts[5].path, "virtual://workspace/debugger-actions.json")
        self.assertEqual(result.artifacts[5].metadata["count"], 1)
        self.assertEqual(result.artifacts[6].path, "virtual://workspace/debugger-session.json")
        self.assertEqual(result.artifacts[6].metadata["lifecycle"], "action_controlled")
        self.assertEqual(result.artifacts[6].metadata["paused_event_count"], 1)
        self.assertEqual(result.artifacts[7].path, "virtual://workspace/debugger-timeline.json")
        self.assertEqual(result.artifacts[7].metadata["entry_count"], 7)
        self.assertIn(("Runtime.evaluate", {"expression": "setTimeout(() => { debugger; }, 0); 'scheduled'", "awaitPromise": False, "returnByValue": True, "userGesture": True}), page._cdp_session.calls)
        self.assertIn(
            ("Debugger.evaluateOnCallFrame", {"callFrameId": "native-cf-1", "expression": "typeof buildSign", "returnByValue": True, "silent": True, "throwOnSideEffect": True}),
            page._cdp_session.calls,
        )
        self.assertIn(("Debugger.stepOver", {}), page._cdp_session.calls)
        self.assertNotIn(("Debugger.resume", {}), page._cdp_session.calls)

    def test_native_web_runtime_can_resume_retained_paused_session(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        initial = runtime.apply_minimal_protection(
            "set-breakpoint",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 4,
                "trigger_expression": "debugger; 'scheduled'",
                "keep_paused": True,
                "pause_session_id": "native-paused-session",
            },
        )
        self.assertEqual(initial.status.value, "success")
        self.assertEqual(initial.next_action, "inspect_debugger_session_or_resume")
        follow_up = runtime.apply_minimal_protection(
            "paused-session",
            {
                "pause_session_id": "native-paused-session",
                "paused_session_action": "resume",
            },
        )
        self.assertEqual(follow_up.status.value, "success")
        self.assertEqual(follow_up.applied_actions, ["run_paused_session_action:native-paused-session"])
        self.assertEqual(follow_up.next_action, "continue_recon")
        self.assertIn("paused_session_lifecycle=resumed", follow_up.verification)
        self.assertIn("paused_session_preflight_status=live_available", follow_up.verification)
        self.assertIn("paused_session_preflight_source=registry", follow_up.verification)
        self.assertIn("paused_session_preflight_live_continuation_available=True", follow_up.verification)
        self.assertIn("paused_session_preflight_requested_action=resume", follow_up.verification)
        self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/debugger-session.json")
        self.assertEqual(follow_up.artifacts[0].metadata["lifecycle"], "resumed")
        self.assertEqual(follow_up.artifacts[0].metadata["preflight_status"], "live_available")
        self.assertEqual(follow_up.artifacts[0].metadata["preflight_source"], "registry")
        self.assertNotIn("native-paused-session", BreakpointManager._paused_sessions)

    def test_native_web_runtime_can_inspect_durable_paused_session_snapshot(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        with tempfile.TemporaryDirectory() as tmpdir:
            initial = runtime.apply_minimal_protection(
                "set-breakpoint",
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 4,
                    "trigger_expression": "debugger; 'scheduled'",
                    "keep_paused": True,
                    "pause_session_id": "native-durable-session",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                },
            )
            self.assertEqual(initial.status.value, "success")
            self.assertTrue((Path(tmpdir) / "native-durable-session.json").exists())

            BreakpointManager.clear_paused_sessions()
            follow_up = runtime.apply_minimal_protection(
                "paused-session",
                {
                    "pause_session_id": "native-durable-session",
                    "paused_session_action": "inspect",
                    "paused_session_store_dir": tmpdir,
                },
            )

            self.assertEqual(follow_up.status.value, "success")
            self.assertEqual(follow_up.applied_actions, ["run_paused_session_action:native-durable-session"])
            self.assertIn("paused_session_lifecycle=retained_paused", follow_up.verification)
            self.assertIn("paused_session_continued_from_store=True", follow_up.verification)
            self.assertIn("paused_session_continued_from_registry=False", follow_up.verification)
            self.assertIn("paused_session_live_continuation_available=False", follow_up.verification)
            self.assertIn("paused_session_preflight_status=inspect_only", follow_up.verification)
            self.assertIn("paused_session_preflight_source=durable_snapshot", follow_up.verification)
            self.assertIn("paused_session_preflight_live_continuation_available=False", follow_up.verification)
            self.assertIn("paused_session_preflight_reason=durable_snapshot_is_inspect_only", follow_up.verification)
            self.assertIn("paused_session_preflight_requested_action=inspect", follow_up.verification)
            self.assertIn("paused_session_reason=durable_paused_session_snapshot_loaded", follow_up.verification)
            self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/debugger-session.json")
            self.assertTrue(follow_up.artifacts[0].metadata["continued_from_store"])
            self.assertFalse(follow_up.artifacts[0].metadata["continued_from_registry"])
            self.assertFalse(follow_up.artifacts[0].metadata["live_continuation_available"])
            self.assertEqual(follow_up.artifacts[0].metadata["preflight_status"], "inspect_only")
            self.assertEqual(follow_up.artifacts[0].metadata["preflight_source"], "durable_snapshot")
            self.assertFalse(follow_up.artifacts[0].metadata["preflight_live_continuation_available"])
            self.assertEqual(follow_up.artifacts[1].path, "virtual://workspace/debugger-timeline.json")
            self.assertTrue(follow_up.artifacts[1].metadata["continued_from_store"])
            self.assertFalse(follow_up.artifacts[1].metadata["live_continuation_available"])

    def test_native_web_runtime_rejects_live_actions_from_durable_paused_session_snapshot(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        with tempfile.TemporaryDirectory() as tmpdir:
            initial = runtime.apply_minimal_protection(
                "set-breakpoint",
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 4,
                    "trigger_expression": "debugger; 'scheduled'",
                    "keep_paused": True,
                    "pause_session_id": "native-durable-session",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                },
            )
            self.assertEqual(initial.status.value, "success")

            BreakpointManager.clear_paused_sessions()
            follow_up = runtime.apply_minimal_protection(
                "paused-session",
                {
                    "pause_session_id": "native-durable-session",
                    "paused_session_action": "resume",
                    "paused_session_store_dir": tmpdir,
                },
            )

            self.assertEqual(follow_up.status.value, "failed")
            self.assertEqual(follow_up.applied_actions, [])
            self.assertIn("paused_session_error=live_paused_session_required", follow_up.verification)
            self.assertIn("paused_session_reason=durable_snapshot_is_inspect_only", follow_up.verification)
            self.assertIn("paused_session_continued_from_store=True", follow_up.verification)
            self.assertIn("paused_session_live_continuation_available=False", follow_up.verification)
            self.assertIn("paused_session_preflight_status=action_blocked", follow_up.verification)
            self.assertIn("paused_session_preflight_source=durable_snapshot", follow_up.verification)
            self.assertIn("paused_session_preflight_reason=live_paused_session_required", follow_up.verification)
            self.assertIn("paused_session_preflight_requested_action=resume", follow_up.verification)
            self.assertTrue(follow_up.artifacts[0].metadata["continued_from_store"])
            self.assertFalse(follow_up.artifacts[0].metadata["live_continuation_available"])
            self.assertEqual(follow_up.artifacts[0].metadata["preflight_status"], "action_blocked")
            self.assertEqual(follow_up.artifacts[0].metadata["preflight_reason"], "live_paused_session_required")

    def test_native_web_runtime_reports_missing_paused_session_preflight(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        follow_up = runtime.apply_minimal_protection(
            "paused-session",
            {
                "pause_session_id": "missing-native-session",
                "paused_session_action": "inspect",
            },
        )

        self.assertEqual(follow_up.status.value, "failed")
        self.assertEqual(follow_up.applied_actions, [])
        self.assertIn("paused_session_status=unsupported", follow_up.verification)
        self.assertIn("paused_session_preflight_status=unavailable", follow_up.verification)
        self.assertIn("paused_session_preflight_source=missing", follow_up.verification)
        self.assertIn("paused_session_preflight_live_continuation_available=False", follow_up.verification)
        self.assertIn("paused_session_preflight_reason=pause_session_not_found", follow_up.verification)
        self.assertEqual(follow_up.artifacts, [])


if __name__ == "__main__":
    unittest.main()
