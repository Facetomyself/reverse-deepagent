import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import reverse_deepagent.adapters.native_web as native_web_adapter
from reverse_deepagent.adapters.native_web import NativeWebRuntime
from reverse_deepagent.adapters.native_web_source_dispatch import dispatch_source_map_review_evidence
from reverse_deepagent.browser import BrowserPageRef, BrowserProviderCapabilities, PlaywrightBrowserPageAdapter
from reverse_deepagent.browser.hooks import BreakpointManager, ClosureWrapperReplacementExecutionManager, HookInstallResult, HookSnapshot
from reverse_deepagent.browser.source_maps import (
    SourceMapFollowthroughDispatchApprovalPlanManager,
    SourceMapFollowthroughDispatchApprovalPlanSpec,
    SourceMapDebuggerCandidateSelectionManager,
    SourceMapDebuggerCandidateSelectionSpec,
    SourceMapHookCandidateSelectionManager,
    SourceMapHookCandidateSelectionSpec,
)
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline
from reverse_deepagent.fixtures.web_sign import FixtureProfile, _build_js
from reverse_deepagent.schemas import ConfidenceLevel, EvidenceItem, EvidenceKind, ExecutionStatus, FinalResult, KeyFindings, ReverseMode, ReverseStage, TaskCard


WEBPACK_MINIFIED_SOURCE = _build_js(FixtureProfile.WEBPACK_MINIFIED)


def _v8_heap_snapshot_for_native_test(*, extra_object: bool = False) -> dict[str, Any]:
    strings = ["", "Window", "Object", "ExtraObject", "prop"]
    nodes = [3, 1, 1, 64, 1, 0, 3, 2, 2, 32, 0, 0]
    if extra_object:
        nodes.extend([3, 3, 3, 48, 0, 0])
    edges = [2, 4, 1]
    if extra_object:
        edges.extend([2, 4, 2])
    return {
        "snapshot": {
            "meta": {
                "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                "node_types": [["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"], "string", "number", "number", "number", "number"],
                "edge_fields": ["type", "name_or_index", "to_node"],
                "edge_types": [["context", "element", "property", "internal", "hidden", "shortcut", "weak"], "string_or_number", "node"],
            }
        },
        "nodes": nodes,
        "edges": edges,
        "strings": strings,
    }


def _v8_heap_snapshot_path_to_root_for_native_test() -> dict[str, Any]:
    strings = ["", "Window", "Object", "TokenSecret", "child", "secret"]
    return {
        "snapshot": {
            "meta": {
                "node_fields": ["type", "name", "id", "self_size", "edge_count", "trace_node_id"],
                "node_types": [["hidden", "array", "string", "object", "code", "closure", "regexp", "number", "native", "synthetic"], "string", "number", "number", "number", "number"],
                "edge_fields": ["type", "name_or_index", "to_node"],
                "edge_types": [["context", "element", "property", "internal", "hidden", "shortcut", "weak"], "string_or_number", "node"],
            }
        },
        "nodes": [3, 1, 1, 64, 1, 0, 3, 2, 2, 32, 1, 0, 3, 3, 3, 48, 0, 0],
        "edges": [2, 4, 6, 2, 5, 12],
        "strings": strings,
    }


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
        if method == "Target.attachToTarget":
            return {"sessionId": "attached-session-1"}
        if method == "Target.detachFromTarget":
            return {}
        if method == "HeapProfiler.enable":
            return {}
        if method == "HeapProfiler.takeHeapSnapshot":
            self.emit("HeapProfiler.addHeapSnapshotChunk", {"chunk": '{"snapshot":{"meta":{}},"nodes":[1,2,3]}'})
            return {}
        if method == "HeapProfiler.disable":
            return {}
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
            if "__reverseDeepAgentClosureMutabilityProbes" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "runtimeMutabilityProven": True,
                            "temporaryAssignmentConfirmed": True,
                            "originalRestored": True,
                            "wrapperInstalled": False,
                        },
                        "description": "Object",
                    }
                }
            if "__rdgOriginal" in expression and "__reverseDeepAgentClosureWrappers" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "restored": True,
                        },
                        "description": "Object",
                    }
                }
            if "__reverseDeepAgentClosureWrappers" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "wrapperInstalled": True,
                            "restoreExpressionAvailable": True,
                        },
                        "description": "Object",
                    }
                }
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
        self.custom_loader_executions = []
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
        if "__reverseDeepAgentClosureWrappers" in expression and "totalEventCount" in expression:
            return {
                "ok": True,
                "events": [
                    {
                        "marker": "reverse-deepagent:closure-wrapper:closure:native-cf-1:buildSign",
                        "functionName": "buildSign",
                        "wrapperStrategy": "log-only-call-through",
                        "kind": "return",
                        "argumentCount": 2,
                    }
                ],
                "eventCount": 1,
                "totalEventCount": 1,
                "strategyCounts": {"log-only-call-through": 1},
                "markerCount": 1,
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
        if "__REVERSE_AGENT_CUSTOM_LOADER_EXECUTION__" in expression:
            self.custom_loader_executions.append("window.__customLoader.load")
            return {
                "marker": "__REVERSE_AGENT_CUSTOM_LOADER_EXECUTION__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "loaderPath": "window.__customLoader.load",
                "loaderInvoked": True,
                "beforeRegistryCount": 1,
                "afterRegistryCount": 2,
                "addedRegistryKeys": ["884"],
                "removedRegistryKeys": [],
                "changedRegistryKeys": [],
                "beforeCacheCount": 0,
                "afterCacheCount": 1,
                "addedCacheKeys": ["884"],
                "removedCacheKeys": [],
                "changedCacheKeys": [],
                "result": {"type": "object", "keys": ["moduleId"], "preview": '{"moduleId":"884"}'},
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
        if "remote_export_hooks" in expression and "installed.push" in expression:
            self.function_hook_installed = True
            return {
                "ok": True,
                "installed": [
                    {
                        "hookPath": "window.remoteOther:./token:token",
                        "containerPath": "window.remoteOther",
                        "exposedName": "./token",
                        "exportName": "token",
                        "functionName": "token",
                    }
                ],
                "missing": [],
                "eventCount": len(self.function_hook_events),
            }
        if "remote_export_" in expression and "eventCount" in expression:
            return {
                "ok": self.function_hook_installed,
                "events": list(self.function_hook_events),
                "eventCount": len(self.function_hook_events),
                "installed": {"window.remoteOther:./token:token": self.function_hook_installed},
            }
        if "window.remoteToken" in expression:
            if self.function_hook_installed:
                self.function_hook_events.append({"type": "remote_export_call", "payload": {"hookPath": "window.remoteOther:./token:token", "containerPath": "window.remoteOther", "exposedName": "./token", "exportName": "token", "argCount": 1}})
                self.function_hook_events.append({"type": "remote_export_return", "payload": {"hookPath": "window.remoteOther:./token:token", "containerPath": "window.remoteOther", "exposedName": "./token", "exportName": "token", "result": {"type": "string", "preview": "remote-token"}}})
            return "remote-token"
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
        self.assertIn("hook_install_ok=True", result.verification)
        self.assertIn("hook_event_count=1", result.verification)
        self.assertIn("context_keys=['reason']", result.verification)
        self.assertEqual(result.next_action, "resume_recon")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/hook-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["event_count"], 1)
        self.assertEqual(
            result.artifacts[0].metadata["installed"],
            {"fetch_xhr": True, "cookie": True, "anti_debug": True},
        )
        self.assertEqual(result.artifacts[0].metadata["protection_name"], "console.clear")
        self.assertEqual(result.confidence.value, "medium")

    def test_native_web_runtime_default_hook_fallback_install_failure_remains_equivalent(self) -> None:
        class FailingHookManager:
            def install(self, page):
                return HookInstallResult(ok=False, installed={"fetch_xhr": False}, error="install_failed")

            def snapshot(self, page):
                return HookSnapshot(ok=False, installed={"fetch_xhr": False}, events=[], event_count=0, reason="not_installed")

        original_manager = native_web_adapter.BrowserHookManager
        native_web_adapter.BrowserHookManager = FailingHookManager
        try:
            provider = FakeProvider()
            runtime = NativeWebRuntime(browser_provider=provider)
            result = runtime.apply_minimal_protection("console.clear", {"reason": "unit-test"})
        finally:
            native_web_adapter.BrowserHookManager = original_manager

        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("hook_install_ok=False", result.verification)
        self.assertIn("hook_event_count=0", result.verification)
        self.assertIn("context_keys=['reason']", result.verification)
        self.assertIn("hook_install_error=install_failed", result.verification)
        self.assertEqual(result.next_action, "ensure_browser_provider_or_hook_capability")
        self.assertEqual(result.confidence.value, "low")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/hook-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["event_count"], 0)
        self.assertEqual(result.artifacts[0].metadata["installed"], {"fetch_xhr": False})
        self.assertEqual(result.artifacts[0].metadata["protection_name"], "console.clear")

    def test_native_web_runtime_apply_minimal_protection_installs_function_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        def fail_if_fallback_called(protection_name, context, page):
            raise AssertionError("default hook fallback must not run for hook-function")

        runtime._dispatch_default_hook_fallback = fail_if_fallback_called
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
        self.assertNotEqual(result.artifacts[0].path, "virtual://workspace/hook-timeline.json")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/function-hook-timeline.json")
        self.assertEqual(result.artifacts[1].metadata["event_count"], 2)

    def test_native_web_runtime_default_hook_fallback_not_called_when_provider_unavailable(self) -> None:
        from reverse_deepagent.browser import BrowserProviderUnavailableError

        class UnavailableProvider(FakeProvider):
            def start(self):
                raise BrowserProviderUnavailableError("test_unavailable")

        runtime = NativeWebRuntime(browser_provider=UnavailableProvider())

        def fail_if_fallback_called(protection_name, context, page):
            raise AssertionError("default hook fallback must not run before page acquisition")

        runtime._dispatch_default_hook_fallback = fail_if_fallback_called
        result = runtime.apply_minimal_protection("console.clear", {"reason": "unit-test"})

        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "ensure_browser_provider")
        self.assertIn("Native Web browser provider unavailable: test_unavailable", result.verification)
        self.assertIn("context_keys=['reason']", result.verification)
        self.assertEqual(result.artifacts, [])

    def test_native_web_runtime_assesses_recursive_continuation_readiness_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "recursive-continuation-readiness",
            {
                "recursive_continuation_readiness": True,
                "custom_loader_continuation_journal": {
                    "status": "ready_for_review",
                    "record_count": 1,
                    "records": [{"candidate_fingerprint": "custom|loader|1"}],
                },
                "async_chunk_recursive_traversal_followup": {
                    "status": "next_loop_plan_ready",
                    "stages": [{"stage": "plan_next_bounded_async_chunk_traversal_loop", "status": "planned"}],
                },
                "module_federation_recursive_continuation_checkpoint": {
                    "status": "next_execution_review_ready",
                    "stages": [{"stage": "review_next_module_federation_recursive_traversal_execution", "status": "ready_for_review"}],
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["assess_recursive_continuation_readiness"])
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/recursive-continuation-readiness.json")
        self.assertEqual(result.artifacts[0].metadata["system_count"], 3)
        self.assertEqual(set(result.artifacts[0].metadata["ready_systems"]), {"custom_loader", "async_chunk", "module_federation"})
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])
        self.assertFalse(result.artifacts[0].metadata["deeper_recursion_executor_ready"])
        self.assertIn("recursive_continuation_readiness_status=ready_for_review", result.verification)
        self.assertIn("recursive_continuation_readiness_system_count=3", result.verification)
        self.assertIn("recursive_continuation_readiness_loader_invoked=False", result.verification)
        self.assertIn("recursive_continuation_readiness_chunk_request_sent=False", result.verification)
        self.assertIn("recursive_continuation_readiness_remote_code_executed=False", result.verification)
        self.assertIn("recursive_continuation_readiness_artifacts_written=False", result.verification)

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

    def test_native_web_runtime_plans_async_chunk_traversal_graph_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-traversal-graph",
            {
                "chunk_graph": {
                    "status": "success",
                    "candidate_count": 2,
                    "candidates": [
                        {
                            "edge_type": "runtime-async-chunk",
                            "loader_kind": "webpack-runtime",
                            "chunk_id": "731",
                            "target": "/assets/731.js",
                            "runtime_path": "window.__webpack_require__",
                        },
                        {
                            "edge_type": "dynamic-import",
                            "loader_kind": "es-dynamic-import",
                            "chunk_id": "./chunks/sign-panel.js",
                            "target": "./chunks/sign-panel.js",
                        },
                    ],
                }
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_traversal_graph"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_traversal_graph_status=ready_for_review", result.verification)
        self.assertIn("async_chunk_traversal_graph_node_count=2", result.verification)
        self.assertIn("async_chunk_traversal_graph_queue_count=1", result.verification)
        self.assertIn("async_chunk_traversal_graph_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_traversal_graph_queue")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-graph.json")
        self.assertEqual(result.artifacts[0].metadata["queue_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_plans_async_chunk_traversal_workflow_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-traversal-workflow-plan",
            {
                "async_chunk_traversal_graph": {
                    "schema_version": "reverse-deepagent.async-chunk-traversal-graph.v1",
                    "status": "ready_for_review",
                    "graph_id": "async-chunk-traversal-graph",
                    "queue_count": 1,
                    "review_queue": [
                        {
                            "node_id": "async-chunk-node-0",
                            "candidate_index": 0,
                            "chunk_id": "731",
                            "target": "/assets/731.js",
                            "loader_kind": "webpack-runtime",
                            "edge_type": "runtime-async-chunk",
                            "runtime_path": "window.__webpack_require__",
                            "queue_status": "ready_for_review",
                        }
                    ],
                }
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_traversal_workflow"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_traversal_workflow_plan_status=ready_for_review", result.verification)
        self.assertIn("async_chunk_traversal_workflow_plan_planned_step_count=1", result.verification)
        self.assertIn("async_chunk_traversal_workflow_plan_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_traversal_workflow_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-workflow-plan.json")
        self.assertEqual(result.artifacts[0].metadata["planned_step_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_plans_async_chunk_traversal_workflow_execution_without_loading_chunk(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "async-chunk-traversal-workflow-execution",
            {"async_chunk_traversal_workflow_plan": workflow_plan},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_traversal_workflow_execution_step"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_traversal_workflow_execution_status=ready_for_review", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_runtime_loader_executed=False", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_traversal_workflow_execution_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-workflow-execution.json")
        self.assertFalse(result.artifacts[0].metadata["runtime_loader_executed"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_plans_async_chunk_traversal_loop_without_loading_chunk(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "async-chunk-traversal-loop-plan",
            {
                "async_chunk_traversal_workflow_plan": workflow_plan,
                "max_loop_iterations": 2,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_traversal_loop"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_traversal_loop_plan_status=ready_for_review", result.verification)
        self.assertIn("async_chunk_traversal_loop_plan_iteration_count=1", result.verification)
        self.assertIn("async_chunk_traversal_loop_plan_automatic_loop_execution=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_plan_automatic_queue_advance=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_plan_automatic_recursive_traversal=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_plan_runtime_loader_executed=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_traversal_loop_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-loop-plan.json")
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["runtime_loader_executed"])

    def test_native_web_runtime_executes_one_reviewed_async_chunk_traversal_workflow_step(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-async-chunk-traversal-workflow",
            {
                "async_chunk_traversal_workflow_plan": workflow_plan,
                "plan_async_chunk_load": True,
                "execute_async_chunk_load": True,
                "run_module_diff": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "731", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_async_chunk_traversal_workflow_step"])
        self.assertEqual(page.async_chunk_loads, ["731"])
        self.assertIn("async_chunk_traversal_workflow_execution_status=module_diff_ready", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_load_planned=True", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_runtime_loader_executed=True", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_chunk_request_sent=True", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_module_diff_executed=True", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("async_chunk_traversal_workflow_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_module_diff_hook_candidates")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-workflow-execution.json")
        self.assertTrue(result.artifacts[0].metadata["runtime_loader_executed"])
        self.assertTrue(result.artifacts[0].metadata["chunk_request_sent"])
        self.assertTrue(result.artifacts[0].metadata["module_diff_executed"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_one_reviewed_async_chunk_loop_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }
        loop_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-loop-plan.v1",
            "status": "ready_for_review",
            "plan_id": "async-chunk-traversal-loop-plan",
            "source_workflow_plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "iterations": [
                {
                    "iteration_index": 0,
                    "source_step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-async-chunk-traversal-loop",
            {
                "async_chunk_traversal_loop_plan": loop_plan,
                "async_chunk_traversal_workflow_plan": workflow_plan,
                "plan_async_chunk_load": True,
                "execute_async_chunk_load": True,
                "run_module_diff": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "731", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_async_chunk_traversal_loop_iteration"])
        self.assertEqual(page.async_chunk_loads, ["731"])
        self.assertIn("async_chunk_traversal_loop_execution_status=module_diff_ready", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_selected_iteration_index=0", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_runtime_loader_executed=True", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_chunk_request_sent=True", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_module_diff_executed=True", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_traversal_graph_rebuilt=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_workflow_replanned=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_automatic_loop_execution=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("async_chunk_traversal_loop_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_module_diff_then_rebuild_graph")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-traversal-loop-execution.json")
        self.assertTrue(result.artifacts[0].metadata["runtime_loader_executed"])
        self.assertTrue(result.artifacts[0].metadata["chunk_request_sent"])
        self.assertTrue(result.artifacts[0].metadata["module_diff_executed"])
        self.assertFalse(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_plans_async_chunk_recursive_traversal_followup(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        loop_execution = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-loop-execution.v1",
            "status": "module_diff_ready",
            "next_action": "review_async_chunk_module_diff_then_rebuild_graph",
        }

        result = runtime.apply_minimal_protection(
            "async-chunk-recursive-traversal-plan",
            {"async_chunk_traversal_loop_execution": loop_execution},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_recursive_traversal_followup"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_recursive_traversal_plan_status=ready_for_graph_rebuild", result.verification)
        self.assertIn("async_chunk_recursive_traversal_plan_runtime_loader_executed=False", result.verification)
        self.assertIn("async_chunk_recursive_traversal_plan_chunk_request_sent=False", result.verification)
        self.assertIn("async_chunk_recursive_traversal_plan_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "rebuild_async_chunk_traversal_graph_before_next_recursive_loop")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-recursive-traversal-plan.json")
        self.assertEqual(result.artifacts[0].metadata["recursive_plan_status"], "ready_for_graph_rebuild")
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_reviewed_async_chunk_recursive_traversal_followup(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        recursive_plan = {
            "schema_version": "reverse-deepagent.async-chunk-recursive-traversal-plan.v1",
            "plan_id": "async-chunk-recursive-traversal-plan",
            "status": "ready_for_graph_rebuild",
        }
        chunk_graph = {
            "status": "success",
            "candidates": [
                {
                    "edge_type": "runtime-async-chunk",
                    "loader_kind": "webpack-runtime",
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-async-chunk-recursive-traversal-followup",
            {
                "async_chunk_recursive_traversal_plan": recursive_plan,
                "chunk_graph": chunk_graph,
                "rebuild_graph": True,
                "replan_workflow": True,
                "plan_next_loop": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_async_chunk_recursive_traversal_followup_checkpoint"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_recursive_traversal_followup_status=next_loop_plan_ready", result.verification)
        self.assertIn("async_chunk_recursive_traversal_followup_traversal_graph_rebuilt=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_followup_workflow_replanned=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_followup_loop_plan_created=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_followup_chunk_request_sent=False", result.verification)
        self.assertIn("async_chunk_recursive_traversal_followup_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_async_chunk_traversal_loop_plan_before_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-recursive-traversal-followup.json")
        self.assertTrue(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertTrue(result.artifacts[0].metadata["workflow_replanned"])
        self.assertTrue(result.artifacts[0].metadata["loop_plan_created"])
        self.assertFalse(result.artifacts[0].metadata["chunk_request_sent"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_reviewed_async_chunk_recursive_traversal_next_loop(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }
        loop_plan = {
            "schema_version": "reverse-deepagent.async-chunk-traversal-loop-plan.v1",
            "status": "ready_for_review",
            "plan_id": "async-chunk-traversal-loop-plan",
            "source_workflow_plan_id": "native-async-traversal-workflow-plan",
            "source_graph_id": "async-chunk-traversal-graph",
            "iterations": [
                {
                    "iteration_index": 0,
                    "source_step_index": 0,
                    "candidate_index": 0,
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "edge_type": "runtime-async-chunk",
                    "runtime_path": "window.__webpack_require__",
                }
            ],
        }
        followup = {
            "schema_version": "reverse-deepagent.async-chunk-recursive-traversal-followup.v1",
            "status": "next_loop_plan_ready",
            "async_chunk_traversal_loop_plan": {"status": "ready_for_review", "loop_plan": loop_plan},
            "async_chunk_traversal_workflow_plan": {"status": "ready_for_review", "workflow_plan": workflow_plan},
        }

        result = runtime.apply_minimal_protection(
            "execute-async-chunk-recursive-traversal-next-loop",
            {
                "async_chunk_recursive_traversal_followup": followup,
                "plan_async_chunk_load": True,
                "execute_async_chunk_load": True,
                "run_module_diff": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "731", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_async_chunk_recursive_traversal_next_loop"])
        self.assertEqual(page.async_chunk_loads, ["731"])
        self.assertIn("async_chunk_recursive_traversal_execution_status=next_loop_module_diff_ready", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_loop_execution_started=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_runtime_loader_executed=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_chunk_request_sent=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_module_diff_executed=True", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("async_chunk_recursive_traversal_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "plan_next_async_chunk_recursive_traversal_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-recursive-traversal-execution.json")
        self.assertTrue(result.artifacts[0].metadata["loop_execution_started"])
        self.assertTrue(result.artifacts[0].metadata["runtime_loader_executed"])
        self.assertTrue(result.artifacts[0].metadata["chunk_request_sent"])
        self.assertTrue(result.artifacts[0].metadata["module_diff_executed"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

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

    def test_native_web_runtime_plans_custom_loader_traversal_continuation_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-plan",
            {
                "traversal_depth": 2,
                "custom_loader_execution_result": {
                    "status": "success",
                    "selected_candidate": {
                        "chunk_id": "custom-sign",
                        "target": "window.__customLoader.load",
                        "loader_path": "window.__customLoader.load",
                        "loader_kind": "custom-loader",
                    },
                    "execution": {
                        "attempted": True,
                        "ok": True,
                        "loaderInvoked": True,
                        "loaderPath": "window.__customLoader.load",
                    },
                },
                "next_custom_loader_candidates": [
                    {
                        "chunk_id": "custom-sign",
                        "target": "window.__customLoader.load",
                        "loader_path": "window.__customLoader.load",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                    },
                    {
                        "chunk_id": "custom-sign-child",
                        "target": "window.__customLoader.loadChild",
                        "loader_path": "window.__customLoader.loadChild",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                        "parent_loader_path": "window.__customLoader.load",
                        "depth": 2,
                    },
                ],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_traversal_plan_status=planned", result.verification)
        self.assertIn("custom_loader_traversal_candidate_count=2", result.verification)
        self.assertIn("custom_loader_traversal_ready_continuation_count=1", result.verification)
        self.assertIn("custom_loader_traversal_already_executed_count=1", result.verification)
        self.assertIn("custom_loader_traversal_previous_execution_count=1", result.verification)
        self.assertEqual(result.next_action, "review_next_custom_loader_continuation_candidate")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-plan.json")
        self.assertEqual(result.artifacts[0].metadata["ready_continuation_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["already_executed_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["previous_execution_count"], 1)

    def test_native_web_runtime_plans_custom_loader_traversal_graph_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-graph",
            {
                "custom_loader_traversal_plan": {
                    "status": "planned",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                            "chunk_id": "custom-sign",
                            "depth": 1,
                            "continuation_supported": True,
                            "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                        },
                        {
                            "index": 1,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_path": "window.__customLoader.loadChild",
                            "target": "window.__customLoader.loadChild",
                            "chunk_id": "custom-sign-child",
                            "parent_loader_path": "window.__customLoader.load",
                            "depth": 2,
                            "continuation_supported": True,
                        },
                    ],
                },
                "custom_loader_continuation_journal": {
                    "journal": {
                        "records": [
                            {
                                "loader_path": "window.__customLoader.load",
                                "candidate_fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                            }
                        ]
                    }
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal_graph"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_traversal_graph_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_traversal_graph_node_count=2", result.verification)
        self.assertIn("custom_loader_traversal_graph_queue_count=1", result.verification)
        self.assertIn("custom_loader_traversal_graph_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_graph_queue")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-graph.json")
        self.assertEqual(result.artifacts[0].metadata["queue_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_blocks_custom_loader_traversal_graph_depth_overflow(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "plan-custom-loader-deep-traversal",
            {
                "custom_loader_traversal_plan": {
                    "status": "planned",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_path": "window.__customLoader.loadGrandChild",
                            "target": "window.__customLoader.loadGrandChild",
                            "chunk_id": "too-deep",
                            "depth": 4,
                            "continuation_supported": True,
                        }
                    ],
                },
                "max_traversal_depth": 2,
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal_graph"])
        self.assertIn("custom_loader_traversal_graph_status=blocked", result.verification)
        self.assertIn("custom_loader_traversal_graph_reason=max_traversal_depth_exceeded", result.verification)
        self.assertIn("custom_loader_traversal_graph_depth_blocked_count=1", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_depth_before_continuing")
        self.assertEqual(result.artifacts[0].metadata["depth_blocked_count"], 1)


    def test_native_web_runtime_plans_custom_loader_traversal_workflow_plan_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-workflow-plan",
            {
                "custom_loader_traversal_graph": {
                    "schema_version": "reverse-deepagent.custom-loader-traversal-graph.v1",
                    "status": "ready_for_review",
                    "queue_count": 1,
                    "review_queue": [
                        {
                            "node_id": "custom-loader-node-1",
                            "candidate_index": 1,
                            "loader_path": "window.__customLoader.loadChild",
                            "target": "window.__customLoader.loadChild",
                            "chunk_id": "custom-sign-child",
                            "depth": 2,
                            "queue_status": "ready_for_review",
                        }
                    ],
                }
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal_workflow"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_traversal_workflow_plan_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_traversal_workflow_plan_planned_step_count=1", result.verification)
        self.assertIn("custom_loader_traversal_workflow_plan_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_workflow_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-workflow-plan.json")
        self.assertEqual(result.artifacts[0].metadata["planned_step_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])

    def test_native_web_runtime_blocks_custom_loader_traversal_workflow_plan_without_queue(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "plan-custom-loader-traversal-workflow",
            {
                "custom_loader_traversal_graph": {
                    "schema_version": "reverse-deepagent.custom-loader-traversal-graph.v1",
                    "status": "blocked",
                    "queue_count": 0,
                    "depth_blocked_count": 1,
                    "review_queue": [],
                }
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal_workflow"])
        self.assertIn("custom_loader_traversal_workflow_plan_status=blocked", result.verification)
        self.assertIn("custom_loader_traversal_workflow_plan_reason=custom_loader_traversal_graph_blocked", result.verification)
        self.assertEqual(result.next_action, "revise_custom_loader_traversal_graph_inputs")
        self.assertEqual(result.artifacts[0].metadata["planned_step_count"], 0)


    def test_native_web_runtime_plans_custom_loader_traversal_workflow_execution_without_running_loader(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-workflow-execution",
            {"custom_loader_traversal_workflow_plan": workflow_plan},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_traversal_workflow_step"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_traversal_workflow_execution_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_loader_invoked=False", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_workflow_execution_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-workflow-execution.json")
        self.assertFalse(result.artifacts[0].metadata["loader_invoked"])
        self.assertFalse(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_plans_custom_loader_traversal_loop_without_running_loader(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "custom-loader-traversal-loop-plan",
            {"custom_loader_traversal_workflow_plan": workflow_plan, "max_loop_iterations": 2},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_traversal_loop"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_traversal_loop_plan_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_traversal_loop_plan_iteration_count=1", result.verification)
        self.assertIn("custom_loader_traversal_loop_plan_automatic_loop_execution=False", result.verification)
        self.assertIn("custom_loader_traversal_loop_plan_automatic_recursive_traversal=False", result.verification)
        self.assertIn("custom_loader_traversal_loop_plan_traversal_graph_rebuilt=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_traversal_loop_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-loop-plan.json")
        self.assertEqual(result.artifacts[0].metadata["planned_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["bounded_loop"])
        self.assertFalse(result.artifacts[0].metadata["automatic_loop_execution"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_one_reviewed_custom_loader_loop_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        traversal_plan = {
            "status": "planned",
            "candidates": [
                {
                    "index": 0,
                    "status": "ready_for_review",
                    "classification": "arbitrary_custom_loader",
                    "loader_kind": "custom-loader",
                    "edge_type": "custom-loader-candidate",
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "continuation_supported": True,
                }
            ],
        }
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                }
            ],
        }
        loop_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-loop-plan.v1",
            "status": "ready_for_review",
            "plan_id": "custom-loader-traversal-loop-plan",
            "source_workflow_plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "iterations": [
                {
                    "iteration_index": 0,
                    "source_step_index": 0,
                    "candidate_index": 0,
                    "candidate_fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                    "loader_path": "window.__customLoader.load",
                    "depth": 1,
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-custom-loader-traversal-loop",
            {
                "custom_loader_traversal_loop_plan": loop_plan,
                "custom_loader_traversal_workflow_plan": workflow_plan,
                "custom_loader_traversal_plan": traversal_plan,
                "plan_continuation_workflow": True,
                "run_preflight": True,
                "execute_custom_loader": True,
                "run_module_diff": True,
                "append_journal": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "884", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_traversal_loop_iteration"])
        self.assertEqual(page.custom_loader_executions, ["window.__customLoader.load"])
        self.assertIn("custom_loader_traversal_loop_execution_status=journal_appended", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_selected_iteration_index=0", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_loader_invoked=True", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_writes_journal=True", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_traversal_graph_rebuilt=False", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_workflow_replanned=False", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("custom_loader_traversal_loop_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "rebuild_custom_loader_traversal_graph_and_replan_workflow_before_next_loop_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-loop-execution.json")
        self.assertTrue(result.artifacts[0].metadata["loader_invoked"])
        self.assertTrue(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertFalse(result.artifacts[0].metadata["workflow_replanned"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_plans_custom_loader_recursive_traversal_followup(self) -> None:
        runtime = NativeWebRuntime(browser_provider=FakeProvider())

        result = runtime.apply_minimal_protection(
            "custom-loader-recursive-traversal-plan",
            {
                "custom_loader_traversal_loop_execution": {
                    "schema_version": "reverse-deepagent.custom-loader-traversal-loop-execution.v1",
                    "status": "journal_appended",
                    "next_action": "rebuild_custom_loader_traversal_graph_and_replan_workflow_before_next_loop_iteration",
                },
                "custom_loader_traversal_graph": {"status": "ready_for_review", "queue_count": 1, "review_queue": [{"node_id": "n1"}]},
                "custom_loader_traversal_workflow_plan": {"status": "ready_for_review", "planned_step_count": 1, "planned_steps": [{"step_index": 0}]},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_recursive_traversal_followup"])
        self.assertIn("custom_loader_recursive_traversal_plan_status=ready_for_next_loop_review", result.verification)
        self.assertIn("custom_loader_recursive_traversal_plan_latest_loop_execution_status=journal_appended", result.verification)
        self.assertIn("custom_loader_recursive_traversal_plan_latest_graph_queue_count=1", result.verification)
        self.assertIn("custom_loader_recursive_traversal_plan_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_custom_loader_traversal_loop_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-recursive-traversal-plan.json")
        self.assertTrue(result.artifacts[0].metadata["bounded_recursion"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_reviewed_custom_loader_recursive_traversal_followup(self) -> None:
        runtime = NativeWebRuntime(browser_provider=FakeProvider())

        result = runtime.apply_minimal_protection(
            "execute-custom-loader-recursive-traversal-followup",
            {
                "custom_loader_recursive_traversal_plan": {
                    "schema_version": "reverse-deepagent.custom-loader-recursive-traversal-plan.v1",
                    "plan_id": "custom-loader-recursive-traversal-plan",
                    "status": "ready_for_graph_rebuild",
                },
                "custom_loader_traversal_plan": {
                    "schema_version": "reverse-deepagent.custom-loader-traversal-plan.v1",
                    "status": "ready_for_review",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_kind": "custom-loader",
                            "edge_type": "custom-loader-candidate",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                            "chunk_id": "custom-sign",
                            "depth": 1,
                            "continuation_supported": True,
                            "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                        },
                        {
                            "index": 1,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_kind": "custom-loader",
                            "edge_type": "custom-loader-candidate",
                            "loader_path": "window.__customLoader.loadChild",
                            "target": "window.__customLoader.loadChild",
                            "chunk_id": "custom-sign-child",
                            "parent_loader_path": "window.__customLoader.load",
                            "depth": 2,
                            "continuation_supported": True,
                        },
                    ],
                },
                "custom_loader_continuation_journal": {
                    "journal": {
                        "records": [
                            {
                                "candidate_fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                            }
                        ]
                    }
                },
                "custom_loader_traversal_loop_execution": {
                    "schema_version": "reverse-deepagent.custom-loader-traversal-loop-execution.v1",
                    "status": "journal_appended",
                    "execution": {"status": "journal_appended"},
                },
                "rebuild_graph": True,
                "replan_workflow": True,
                "plan_next_loop": True,
                "review_approved": True,
                "max_loop_iterations": 2,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_recursive_traversal_followup_checkpoint"])
        self.assertIn("custom_loader_recursive_traversal_followup_status=next_loop_plan_ready", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_traversal_graph_rebuilt=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_workflow_replanned=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_loop_plan_created=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_loader_invoked=False", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_writes_journal=False", result.verification)
        self.assertIn("custom_loader_recursive_traversal_followup_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_custom_loader_traversal_loop_plan_before_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-recursive-traversal-followup.json")
        self.assertTrue(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertTrue(result.artifacts[0].metadata["workflow_replanned"])
        self.assertTrue(result.artifacts[0].metadata["loop_plan_created"])
        self.assertFalse(result.artifacts[0].metadata["loader_invoked"])
        self.assertFalse(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_reviewed_custom_loader_recursive_traversal_next_loop(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        traversal_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-plan.v1",
            "status": "ready_for_review",
            "candidates": [
                {
                    "index": 0,
                    "status": "ready_for_review",
                    "classification": "arbitrary_custom_loader",
                    "loader_kind": "custom-loader",
                    "edge_type": "custom-loader-candidate",
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "continuation_supported": True,
                }
            ],
        }
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                }
            ],
        }
        loop_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-loop-plan.v1",
            "status": "ready_for_review",
            "plan_id": "custom-loader-traversal-loop-plan",
            "source_workflow_plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "iterations": [
                {
                    "iteration_index": 0,
                    "source_step_index": 0,
                    "candidate_index": 0,
                    "candidate_fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                    "loader_path": "window.__customLoader.load",
                    "depth": 1,
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-custom-loader-recursive-traversal-next-loop",
            {
                "custom_loader_recursive_traversal_followup": {
                    "schema_version": "reverse-deepagent.custom-loader-recursive-traversal-followup.v1",
                    "status": "next_loop_plan_ready",
                    "next_action": "review_next_custom_loader_traversal_loop_plan_before_execution",
                    "custom_loader_traversal_loop_plan": {"status": "ready_for_review", "loop_plan": loop_plan},
                    "custom_loader_traversal_workflow_plan": {"status": "ready_for_review", "workflow_plan": workflow_plan},
                },
                "custom_loader_traversal_plan": traversal_plan,
                "plan_continuation_workflow": True,
                "run_preflight": True,
                "execute_custom_loader": True,
                "run_module_diff": True,
                "append_journal": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "884", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_recursive_traversal_next_loop"])
        self.assertEqual(page.custom_loader_executions, ["window.__customLoader.load"])
        self.assertIn("custom_loader_recursive_traversal_execution_status=next_loop_journal_appended", result.verification)
        self.assertIn("custom_loader_recursive_traversal_execution_loop_execution_started=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_execution_loader_invoked=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_execution_writes_journal=True", result.verification)
        self.assertIn("custom_loader_recursive_traversal_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("custom_loader_recursive_traversal_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "plan_next_custom_loader_recursive_traversal_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-recursive-traversal-execution.json")
        self.assertTrue(result.artifacts[0].metadata["loader_invoked"])
        self.assertTrue(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_one_reviewed_custom_loader_traversal_workflow_step(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        traversal_plan = {
            "status": "planned",
            "candidates": [
                {
                    "index": 0,
                    "status": "ready_for_review",
                    "classification": "arbitrary_custom_loader",
                    "loader_kind": "custom-loader",
                    "edge_type": "custom-loader-candidate",
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "continuation_supported": True,
                }
            ],
        }
        workflow_plan = {
            "schema_version": "reverse-deepagent.custom-loader-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "plan_id": "native-traversal-workflow-plan",
            "source_graph_id": "custom-loader-traversal-graph",
            "planned_steps": [
                {
                    "step_index": 0,
                    "candidate_index": 0,
                    "loader_path": "window.__customLoader.load",
                    "target": "window.__customLoader.load",
                    "chunk_id": "custom-sign",
                    "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-custom-loader-traversal-workflow",
            {
                "custom_loader_traversal_workflow_plan": workflow_plan,
                "custom_loader_traversal_plan": traversal_plan,
                "plan_continuation_workflow": True,
                "run_preflight": True,
                "execute_custom_loader": True,
                "run_module_diff": True,
                "append_journal": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "884", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_traversal_workflow_step"])
        self.assertEqual(page.custom_loader_executions, ["window.__customLoader.load"])
        self.assertIn("custom_loader_traversal_workflow_execution_status=journal_appended", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_continuation_workflow_planned=True", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_preflight_executed=True", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_loader_invoked=True", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_writes_journal=True", result.verification)
        self.assertIn("custom_loader_traversal_workflow_execution_traversal_graph_rebuilt=False", result.verification)
        self.assertEqual(result.next_action, "rebuild_custom_loader_traversal_graph_and_stop_before_next_review")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-traversal-workflow-execution.json")
        self.assertTrue(result.artifacts[0].metadata["loader_invoked"])
        self.assertTrue(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])



    def test_native_web_runtime_plans_custom_loader_continuation_workflow_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        traversal_plan = runtime.apply_minimal_protection(
            "custom-loader-traversal-plan",
            {
                "traversal_depth": 2,
                "custom_loader_execution_result": {
                    "status": "success",
                    "selected_candidate": {
                        "chunk_id": "custom-sign",
                        "target": "window.__customLoader.load",
                        "loader_path": "window.__customLoader.load",
                        "loader_kind": "custom-loader",
                    },
                    "execution": {"attempted": True, "ok": True, "loaderInvoked": True, "loaderPath": "window.__customLoader.load"},
                },
                "next_custom_loader_candidates": [
                    {
                        "chunk_id": "custom-sign",
                        "target": "window.__customLoader.load",
                        "loader_path": "window.__customLoader.load",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                    },
                    {
                        "chunk_id": "custom-sign-child",
                        "target": "window.__customLoader.loadChild",
                        "loader_path": "window.__customLoader.loadChild",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                        "parent_loader_path": "window.__customLoader.load",
                        "depth": 2,
                    },
                ],
            },
        )
        result = runtime.apply_minimal_protection(
            "custom-loader-continuation-workflow",
            {
                "custom_loader_traversal_plan": traversal_plan.artifacts[0].metadata | {
                    "status": "ready_for_review",
                    "candidate_count": 2,
                    "ready_continuation_count": 1,
                    "candidates": [
                        {
                            "index": 0,
                            "status": "already_executed",
                            "classification": "arbitrary_custom_loader",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                            "loader_kind": "custom-loader",
                            "already_executed": True,
                            "continuation_supported": False,
                        },
                        {
                            "index": 1,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_path": "window.__customLoader.loadChild",
                            "target": "window.__customLoader.loadChild",
                            "loader_kind": "custom-loader",
                            "parent_loader_path": "window.__customLoader.load",
                            "depth": 2,
                            "continuation_supported": True,
                        },
                    ],
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_continuation_workflow"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_continuation_workflow_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_continuation_workflow_selected_candidate_index=1", result.verification)
        self.assertIn("custom_loader_continuation_workflow_loader_invoked=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_continuation_workflow")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-continuation-workflow.json")
        self.assertEqual(result.artifacts[0].metadata["selected_candidate_index"], 1)
        self.assertFalse(result.artifacts[0].metadata["writes_journal"])

    def test_native_web_runtime_appends_custom_loader_continuation_journal_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-workflow.v1",
            "workflow_id": "native-continuation",
            "status": "ready_for_review",
            "selected_candidate_index": 1,
            "selected_candidate": {
                "index": 1,
                "status": "ready_for_review",
                "classification": "arbitrary_custom_loader",
                "loader_path": "window.__customLoader.loadChild",
                "target": "window.__customLoader.loadChild",
                "chunk_id": "custom-sign-child",
                "fingerprint": "window.__customLoader.loadChild|window.__customLoader.loadChild|custom-sign-child",
                "continuation_supported": True,
            },
        }

        result = runtime.apply_minimal_protection(
            "custom-loader-continuation-journal",
            {
                "custom_loader_continuation_workflow": workflow,
                "write_journal": True,
                "review_approved": True,
                "custom_loader_execution_result": {
                    "status": "success",
                    "execution": {"attempted": True, "ok": True, "loaderInvoked": True},
                },
                "custom_loader_module_diff": {"status": "planned", "diff": {"matched_module_count": 1}},
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["append_custom_loader_continuation_journal"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_continuation_journal_status=journal_appended", result.verification)
        self.assertIn("custom_loader_continuation_journal_writes_journal=True", result.verification)
        self.assertIn("custom_loader_continuation_journal_loader_invoked=False", result.verification)
        self.assertEqual(result.next_action, "run_or_review_next_custom_loader_continuation_step")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-continuation-journal.json")
        self.assertEqual(result.artifacts[0].metadata["record_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_plans_custom_loader_continuation_execution_without_flags(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-workflow.v1",
            "workflow_id": "native-continuation-execution",
            "status": "approved_for_preflight",
            "selected_candidate_index": 0,
            "selected_candidate": {
                "index": 0,
                "status": "ready_for_review",
                "classification": "arbitrary_custom_loader",
                "loader_kind": "custom-loader",
                "edge_type": "custom-loader-candidate",
                "loader_path": "window.__customLoader.load",
                "target": "window.__customLoader.load",
            },
            "preflight_input": {
                "custom_loader_traversal_plan": {
                    "status": "planned",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_kind": "custom-loader",
                            "edge_type": "custom-loader-candidate",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                        }
                    ],
                },
                "candidate_index": 0,
                "expected_loader_path": "window.__customLoader.load",
                "review_approved": True,
            },
        }

        result = runtime.apply_minimal_protection(
            "custom-loader-continuation-execution",
            {"custom_loader_continuation_workflow": workflow},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_custom_loader_continuation_step"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_continuation_execution_status=ready_for_review", result.verification)
        self.assertIn("custom_loader_continuation_execution_loader_invoked=False", result.verification)
        self.assertIn("custom_loader_continuation_execution_automatic_recursive_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_continuation_execution_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-continuation-execution.json")
        self.assertFalse(result.artifacts[0].metadata["loader_invoked"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_executes_one_reviewed_custom_loader_continuation_step(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow = {
            "schema_version": "reverse-deepagent.custom-loader-continuation-workflow.v1",
            "workflow_id": "native-continuation-execution",
            "status": "approved_for_preflight",
            "selected_candidate_index": 0,
            "selected_candidate": {
                "index": 0,
                "status": "ready_for_review",
                "classification": "arbitrary_custom_loader",
                "loader_kind": "custom-loader",
                "edge_type": "custom-loader-candidate",
                "loader_path": "window.__customLoader.load",
                "target": "window.__customLoader.load",
                "fingerprint": "window.__customLoader.load|window.__customLoader.load|custom-sign",
            },
            "preflight_input": {
                "custom_loader_traversal_plan": {
                    "status": "planned",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "classification": "arbitrary_custom_loader",
                            "loader_kind": "custom-loader",
                            "edge_type": "custom-loader-candidate",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                        }
                    ],
                },
                "candidate_index": 0,
                "expected_loader_path": "window.__customLoader.load",
                "review_approved": True,
            },
        }

        result = runtime.apply_minimal_protection(
            "execute-custom-loader-continuation-step",
            {
                "custom_loader_continuation_workflow": workflow,
                "run_preflight": True,
                "execute_custom_loader": True,
                "run_module_diff": True,
                "append_journal": True,
                "review_approved": True,
                "module_discovery": {"status": "success"},
                "modules": [{"module_id": "884", "export_names": ["sign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(page.custom_loader_executions, ["window.__customLoader.load"])
        self.assertIn("custom_loader_continuation_execution_status=journal_appended", result.verification)
        self.assertIn("custom_loader_continuation_execution_preflight_executed=True", result.verification)
        self.assertIn("custom_loader_continuation_execution_loader_invoked=True", result.verification)
        self.assertIn("custom_loader_continuation_execution_module_diff_executed=True", result.verification)
        self.assertIn("custom_loader_continuation_execution_writes_journal=True", result.verification)
        self.assertEqual(result.next_action, "plan_next_custom_loader_continuation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-continuation-execution.json")
        self.assertTrue(result.artifacts[0].metadata["loader_invoked"])
        self.assertTrue(result.artifacts[0].metadata["writes_journal"])
        self.assertFalse(result.artifacts[0].metadata["automatic_recursive_traversal"])

    def test_native_web_runtime_preflights_reviewed_custom_loader_execution_without_running_loader(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        traversal = runtime.apply_minimal_protection(
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
        plan = {"status": "planned", "candidates": [{"index": 0, "classification": "arbitrary_custom_loader", "loader_kind": "custom-loader", "edge_type": "custom-loader-candidate", "loader_path": "window.__customLoader.load", "target": "window.__customLoader.load"}]}
        self.assertEqual(traversal.status.value, "success")

        result = runtime.apply_minimal_protection(
            "custom-loader-execution-preflight",
            {
                "custom_loader_traversal_plan": plan,
                "candidate_index": 0,
                "review_approved": True,
                "expected_loader_path": "window.__customLoader.load",
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["preflight_custom_loader_execution"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("custom_loader_execution_preflight_status=ready_for_execution_review", result.verification)
        self.assertIn("custom_loader_execution_preflight_loader_invoked=False", result.verification)
        self.assertEqual(result.next_action, "execute_custom_loader_with_review_approval")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-execution-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["preflight_status"], "ready_for_execution_review")
        self.assertTrue(result.artifacts[0].metadata["preflight_only"])

    def test_native_web_runtime_blocks_custom_loader_execution_preflight_without_review(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-execution-preflight",
            {
                "custom_loader_traversal_plan": {
                    "status": "planned",
                    "candidates": [
                        {
                            "index": 0,
                            "classification": "arbitrary_custom_loader",
                            "loader_kind": "custom-loader",
                            "edge_type": "custom-loader-candidate",
                            "loader_path": "window.__customLoader.load",
                            "target": "window.__customLoader.load",
                        }
                    ],
                },
                "candidate_index": 0,
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["preflight_custom_loader_execution"])
        self.assertIn("custom_loader_execution_preflight_status=blocked", result.verification)
        self.assertEqual(result.next_action, "resolve_custom_loader_preflight_blockers")

    def test_native_web_runtime_executes_reviewed_custom_loader_after_preflight(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.custom-loader-execution-preflight.v1",
            "status": "ready_for_execution_review",
            "selected_candidate": {
                "index": 0,
                "classification": "arbitrary_custom_loader",
                "loader_kind": "custom-loader",
                "edge_type": "custom-loader-candidate",
                "loader_path": "window.__customLoader.load",
                "target": "window.__customLoader.load",
            },
            "blocking_reasons": [],
        }

        result = runtime.apply_minimal_protection(
            "custom-loader-execution",
            {
                "custom_loader_execution_preflight": preflight,
                "review_approved": True,
                "loader_arguments": [{"chunk": "884"}],
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(page.custom_loader_executions, ["window.__customLoader.load"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertEqual(result.applied_actions, ["execute_custom_loader:window.__customLoader.load"])
        self.assertIn("custom_loader_execution_status=success", result.verification)
        self.assertIn("custom_loader_execution_loader_invoked=True", result.verification)
        self.assertIn("custom_loader_execution_added_registry_key_count=1", result.verification)
        self.assertEqual(result.next_action, "inspect_custom_loader_execution_result_or_refresh_module_diff")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-execution-result.json")
        self.assertTrue(result.artifacts[0].metadata["execution_ok"])
        self.assertEqual(result.artifacts[0].metadata["added_registry_key_count"], 1)

    def test_native_web_runtime_blocks_custom_loader_execution_without_review(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-execution",
            {
                "custom_loader_execution_preflight": {
                    "schema_version": "reverse-deepagent.custom-loader-execution-preflight.v1",
                    "status": "ready_for_execution_review",
                    "selected_candidate": {
                        "classification": "arbitrary_custom_loader",
                        "loader_kind": "custom-loader",
                        "edge_type": "custom-loader-candidate",
                        "loader_path": "window.__customLoader.load",
                    },
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(page.custom_loader_executions, [])
        self.assertEqual(result.next_action, "approve_custom_loader_execution")
        self.assertIn("custom_loader_execution_status=blocked", result.verification)

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

    def test_native_web_runtime_plans_async_chunk_module_diff_after_reviewed_load(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-module-diff",
            {
                "async_chunk_load_result": {
                    "status": "success",
                    "execution": {
                        "attempted": True,
                        "ok": True,
                        "chunkId": "731",
                        "runtimePath": "window.__webpack_require__",
                        "addedRegistryKeys": ["731"],
                    },
                },
                "module_discovery": {
                    "modules": [
                        {
                            "module_id": "731",
                            "runtime_path": "window.__webpack_require__",
                            "export_names": ["sign"],
                            "export_types": {"sign": "function"},
                        }
                    ]
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_async_chunk_module_diff"])
        self.assertEqual(page.async_chunk_loads, [])
        self.assertIn("async_chunk_module_diff_status=planned", result.verification)
        self.assertIn("async_chunk_module_diff_added_registry_key_count=1", result.verification)
        self.assertIn("async_chunk_module_diff_matched_module_count=1", result.verification)
        self.assertIn("async_chunk_module_diff_hook_candidate_count=1", result.verification)
        self.assertIn("async_chunk_module_diff_automatic_hook_installation=False", result.verification)
        self.assertEqual(result.next_action, "review_async_chunk_module_diff_hook_candidates")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/async-chunk-module-diff.json")
        self.assertEqual(result.artifacts[0].metadata["chunk_id"], "731")
        self.assertEqual(result.artifacts[0].metadata["added_registry_key_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["matched_module_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_hook_installation"])


    def test_native_web_runtime_plans_custom_loader_module_diff_after_reviewed_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-module-diff",
            {
                "custom_loader_execution_result": {
                    "status": "success",
                    "execution": {
                        "attempted": True,
                        "ok": True,
                        "loaderInvoked": True,
                        "loaderPath": "window.__customLoader.load",
                        "addedRegistryKeys": ["884"],
                        "addedCacheKeys": ["884"],
                    },
                },
                "module_discovery": {
                    "modules": [
                        {
                            "module_id": "884",
                            "runtime_path": "window.__webpack_require__",
                            "export_names": ["sign"],
                            "export_types": {"sign": "function"},
                        }
                    ]
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_custom_loader_module_diff"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_module_diff_status=planned", result.verification)
        self.assertIn("custom_loader_module_diff_added_registry_key_count=1", result.verification)
        self.assertIn("custom_loader_module_diff_matched_module_count=1", result.verification)
        self.assertIn("custom_loader_module_diff_hook_candidate_count=1", result.verification)
        self.assertIn("custom_loader_module_diff_automatic_hook_installation=False", result.verification)
        self.assertEqual(result.next_action, "review_custom_loader_module_diff_hook_candidates")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/custom-loader-module-diff.json")
        self.assertEqual(result.artifacts[0].metadata["loader_path"], "window.__customLoader.load")
        self.assertEqual(result.artifacts[0].metadata["added_registry_key_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["matched_module_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_hook_installation"])


    def test_native_web_runtime_installs_reviewed_async_chunk_module_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-module-hook",
            {
                "async_chunk_module_diff": {
                    "status": "planned",
                    "diff": {
                        "status": "ready_for_review",
                        "hook_candidates": [
                            {
                                "kind": "async-chunk-module-export",
                                "hook_kind": "module-export",
                                "module_id": "731",
                                "export_name": "sign",
                                "runtime_path": "window.__webpack_require__",
                                "hook_path": "window.__webpack_require__(731).sign",
                                "source": "async_chunk_module_diff",
                            }
                        ],
                    },
                },
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
                "review_approved": True,
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["hook_async_chunk_module_export:731:sign"])
        self.assertIn("async_chunk_module_hook_status=success", result.verification)
        self.assertIn("async_chunk_module_hook_review_approved=True", result.verification)
        self.assertIn("async_chunk_module_hook_installed_count=1", result.verification)
        self.assertIn("async_chunk_module_hook_event_count=2", result.verification)
        self.assertEqual(result.next_action, "inspect_async_chunk_module_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-hooks.json")
        self.assertEqual(result.artifacts[0].metadata["source"], "async_chunk_module_diff")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-hook-timeline.json")

    def test_native_web_runtime_blocks_async_chunk_module_hook_without_review(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "async-chunk-module-hook",
            {
                "async_chunk_module_diff": {
                    "status": "planned",
                    "diff": {
                        "status": "ready_for_review",
                        "hook_candidates": [
                            {
                                "hook_kind": "module-export",
                                "module_id": "731",
                                "export_name": "sign",
                                "runtime_path": "window.__webpack_require__",
                                "source": "async_chunk_module_diff",
                            }
                        ],
                    },
                },
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("async_chunk_module_hook_reason=review_approval_required", result.verification)
        self.assertEqual(result.next_action, "approve_async_chunk_module_hook_candidate")
        self.assertFalse(result.artifacts[0].metadata["review_approved"])

    def test_native_web_runtime_installs_reviewed_custom_loader_module_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-module-hook",
            {
                "custom_loader_module_diff": {
                    "status": "planned",
                    "diff": {
                        "status": "ready_for_review",
                        "hook_candidates": [
                            {
                                "kind": "custom-loader-module-export",
                                "hook_kind": "module-export",
                                "module_id": "731",
                                "export_name": "sign",
                                "runtime_path": "window.__webpack_require__",
                                "hook_path": "window.__webpack_require__(731).sign",
                                "source": "custom_loader_module_diff",
                            }
                        ],
                    },
                },
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
                "review_approved": True,
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["hook_custom_loader_module_export:731:sign"])
        self.assertEqual(page.custom_loader_executions, [])
        self.assertIn("custom_loader_module_hook_status=success", result.verification)
        self.assertIn("custom_loader_module_hook_review_approved=True", result.verification)
        self.assertIn("custom_loader_module_hook_installed_count=1", result.verification)
        self.assertIn("custom_loader_module_hook_event_count=2", result.verification)
        self.assertEqual(result.next_action, "inspect_custom_loader_module_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-hooks.json")
        self.assertEqual(result.artifacts[0].metadata["source"], "custom_loader_module_diff")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/module-hook-timeline.json")

    def test_native_web_runtime_blocks_custom_loader_module_hook_without_review(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "custom-loader-module-hook",
            {
                "custom_loader_module_diff": {
                    "status": "planned",
                    "diff": {
                        "status": "ready_for_review",
                        "hook_candidates": [
                            {
                                "hook_kind": "module-export",
                                "module_id": "731",
                                "export_name": "sign",
                                "runtime_path": "window.__webpack_require__",
                                "source": "custom_loader_module_diff",
                            }
                        ],
                    },
                },
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("custom_loader_module_hook_reason=review_approval_required", result.verification)
        self.assertEqual(result.next_action, "approve_custom_loader_module_hook_candidate")
        self.assertFalse(result.artifacts[0].metadata["review_approved"])


    def test_native_web_runtime_plans_module_federation_traversal_graph_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "module-federation-traversal-graph",
            {
                "module_federation_get_init_plan": {
                    "status": "ready_for_review",
                    "candidates": [
                        {
                            "status": "ready_for_review",
                            "container_path": "window.remoteApp",
                            "exposed_name": "./sign",
                            "module_id": "./sign",
                            "function_path_candidate_available": False,
                        }
                    ],
                }
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_traversal_graph"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_traversal_graph_status=ready_for_review", result.verification)
        self.assertIn("module_federation_traversal_graph_node_count=1", result.verification)
        self.assertIn("module_federation_traversal_graph_queue_count=1", result.verification)
        self.assertIn("module_federation_traversal_graph_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_traversal_graph_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_traversal_workflow_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-traversal-graph.json")
        self.assertEqual(result.artifacts[0].metadata["queue_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])

    def test_native_web_runtime_plans_module_federation_traversal_workflow_without_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        graph = {
            "schema_version": "reverse-deepagent.module-federation-traversal-graph.v1",
            "status": "ready_for_review",
            "nodes": [
                {
                    "node_id": "remote-module:window.remoteApp:./sign",
                    "node_type": "remote-module-candidate",
                    "status": "requires_factory_review",
                    "blocking_reasons": ["remote_factory_execution_requires_review"],
                }
            ],
            "review_queue": [
                {
                    "queue_index": 0,
                    "node_id": "remote-module:window.remoteApp:./sign",
                    "node_type": "remote-module-candidate",
                    "status": "requires_factory_review",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "module-federation-traversal-workflow-plan",
            {"module_federation_traversal_graph": graph},
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_traversal_workflow"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_traversal_workflow_plan_status=ready_for_review", result.verification)
        self.assertIn("module_federation_traversal_workflow_planned_step_count=1", result.verification)
        self.assertIn("module_federation_traversal_workflow_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_traversal_workflow_executed=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_traversal_workflow_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-traversal-workflow-plan.json")
        self.assertEqual(result.artifacts[0].metadata["planned_step_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["workflow_executed"])



    def test_native_web_runtime_executes_one_reviewed_module_federation_traversal_workflow_step(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.module-federation-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "planned_steps": [
                {
                    "step_index": 0,
                    "node_id": "remote-module:window.remoteOther:./token",
                    "node_type": "remote-module-candidate",
                    "node_status": "requires_factory_review",
                    "action": "review_module_federation_factory_invoke_for_traversal",
                    "container_path": "window.remoteOther",
                    "exposed_name": "./token",
                    "node": {"container_path": "window.remoteOther", "exposed_name": "./token"},
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "module-federation-traversal-workflow-execution",
            {
                "module_federation_traversal_workflow_plan": workflow_plan,
                "invoke_remote_factory": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_module_federation_traversal_workflow_step"])
        self.assertEqual(page.module_federation_get_init_probes, ["./token"])
        self.assertEqual(page.module_federation_factory_invocations, ["./token"])
        self.assertIn("module_federation_traversal_workflow_execution_status=factory_invoke_success", result.verification)
        self.assertIn("module_federation_traversal_workflow_execution_remote_factory_invoked=True", result.verification)
        self.assertIn("module_federation_traversal_workflow_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("module_federation_traversal_workflow_execution_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "plan_module_federation_export_hook_after_reviewed_factory_invoke")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-traversal-workflow-execution.json")
        self.assertTrue(result.artifacts[0].metadata["remote_factory_invoked"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])

    def test_native_web_runtime_plans_module_federation_recursive_traversal_followup(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "module-federation-recursive-traversal-plan",
            {
                "module_federation_traversal_workflow_execution": {
                    "status": "factory_invoke_success",
                    "next_action": "plan_module_federation_export_hook_after_reviewed_factory_invoke",
                },
                "latest_module_federation_traversal_graph": {
                    "status": "ready_for_review",
                    "queue_count": 1,
                    "review_queue": [{"node_id": "remote-module:window.remoteOther:./token"}],
                },
                "latest_module_federation_traversal_workflow_plan": {
                    "status": "ready_for_review",
                    "planned_step_count": 1,
                    "planned_steps": [{"step_index": 0}],
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_recursive_traversal_followup"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_traversal_plan_status=ready_for_next_step_review", result.verification)
        self.assertIn("module_federation_recursive_traversal_plan_latest_workflow_execution_status=factory_invoke_success", result.verification)
        self.assertIn("module_federation_recursive_traversal_plan_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_plan_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_module_federation_traversal_workflow_step")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-traversal-plan.json")
        self.assertEqual(result.artifacts[0].metadata["recursive_plan_status"], "ready_for_next_step_review")
        self.assertFalse(result.artifacts[0].metadata["recursive_federation_traversal"])

    def test_native_web_runtime_plans_module_federation_recursive_traversal_followup_checkpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "module-federation-recursive-traversal-followup",
            {
                "module_federation_recursive_traversal_plan": {
                    "schema_version": "reverse-deepagent.module-federation-recursive-traversal-plan.v1",
                    "status": "ready_for_graph_rebuild",
                    "plan_id": "module-federation-recursive-traversal-plan",
                },
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_recursive_traversal_followup"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_traversal_followup_status=ready_for_review", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_traversal_graph_rebuilt=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_remote_code_executed=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_recursive_traversal_followup_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-traversal-followup.json")

    def test_native_web_runtime_executes_reviewed_module_federation_recursive_traversal_followup_checkpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "execute-module-federation-recursive-traversal-followup",
            {
                "module_federation_recursive_traversal_plan": {
                    "schema_version": "reverse-deepagent.module-federation-recursive-traversal-plan.v1",
                    "status": "ready_for_graph_rebuild",
                    "plan_id": "module-federation-recursive-traversal-plan",
                },
                "module_federation_get_init_plan": {
                    "schema_version": "reverse-deepagent.module-federation-get-init-plan.v1",
                    "status": "ready_for_review",
                    "candidates": [
                        {
                            "index": 0,
                            "status": "ready_for_review",
                            "container_path": "window.remoteOther",
                            "exposed_name": "./token",
                            "module_id": "./token",
                            "function_path_candidate_available": False,
                        }
                    ],
                },
                "module_federation_traversal_workflow_execution": {"status": "factory_invoke_success"},
                "rebuild_graph": True,
                "replan_workflow": True,
                "plan_next_step": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_module_federation_recursive_traversal_followup_checkpoint"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_traversal_followup_status=next_step_review_ready", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_traversal_graph_rebuilt=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_workflow_replanned=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_next_step_review_planned=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_remote_code_executed=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_followup_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_module_federation_traversal_workflow_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-traversal-followup.json")
        self.assertTrue(result.artifacts[0].metadata["next_step_review_planned"])
        self.assertFalse(result.artifacts[0].metadata["recursive_federation_traversal"])

    def test_native_web_runtime_plans_module_federation_recursive_traversal_execution(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.module-federation-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "planned_steps": [
                {
                    "step_index": 0,
                    "node_id": "remote-module:window.remoteOther:./token",
                    "node_type": "remote-module-candidate",
                    "node_status": "requires_factory_review",
                    "action": "review_module_federation_factory_invoke_for_traversal",
                    "container_path": "window.remoteOther",
                    "exposed_name": "./token",
                    "node": {"container_path": "window.remoteOther", "exposed_name": "./token"},
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "module-federation-recursive-traversal-execution",
            {
                "module_federation_recursive_traversal_followup": {"status": "next_step_review_ready"},
                "module_federation_traversal_workflow_plan": workflow_plan,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_recursive_traversal_execution_step"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_traversal_execution_status=ready_for_review", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_workflow_execution_status=ready_for_review", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_workflow_execution_started=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_recursive_traversal_execution_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-traversal-execution.json")
        self.assertFalse(result.artifacts[0].metadata["workflow_execution_started"])

    def test_native_web_runtime_executes_reviewed_module_federation_recursive_traversal_next_step(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        workflow_plan = {
            "schema_version": "reverse-deepagent.module-federation-traversal-workflow-plan.v1",
            "status": "ready_for_review",
            "planned_steps": [
                {
                    "step_index": 0,
                    "node_id": "remote-module:window.remoteOther:./token",
                    "node_type": "remote-module-candidate",
                    "node_status": "requires_factory_review",
                    "action": "review_module_federation_factory_invoke_for_traversal",
                    "container_path": "window.remoteOther",
                    "exposed_name": "./token",
                    "node": {"container_path": "window.remoteOther", "exposed_name": "./token"},
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "execute-module-federation-recursive-traversal-next-step",
            {
                "module_federation_recursive_traversal_followup": {"status": "next_step_review_ready"},
                "module_federation_traversal_workflow_plan": workflow_plan,
                "invoke_remote_factory": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_module_federation_recursive_traversal_next_step"])
        self.assertEqual(page.module_federation_get_init_probes, ["./token"])
        self.assertEqual(page.module_federation_factory_invocations, ["./token"])
        self.assertIn("module_federation_recursive_traversal_execution_status=next_step_execution_progressed", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_workflow_execution_status=factory_invoke_success", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_workflow_execution_started=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_remote_factory_invoked=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_remote_code_executed=True", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_automatic_queue_advance=False", result.verification)
        self.assertIn("module_federation_recursive_traversal_execution_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "continue_reviewed_module_federation_traversal_step_or_plan_next_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-traversal-execution.json")
        self.assertTrue(result.artifacts[0].metadata["workflow_execution_started"])
        self.assertFalse(result.artifacts[0].metadata["automatic_queue_advance"])

    def test_native_web_runtime_plans_module_federation_recursive_continuation_journal(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        recursive_execution = {
            "status": "next_step_execution_progressed",
            "execution": {
                "status": "next_step_execution_progressed",
                "workflow_plan_id": "module-federation-traversal-workflow-plan",
                "workflow_execution_status": "factory_invoke_success",
                "selected_step_index": 0,
                "selected_node_id": "remote-module:window.remoteOther:./token",
                "selected_action": "review_module_federation_factory_invoke_for_traversal",
            },
            "side_effect_policy": {"remote_factory_invoked": True, "remote_code_executed": True},
        }

        result = runtime.apply_minimal_protection(
            "module-federation-recursive-continuation-journal",
            {
                "module_federation_recursive_traversal_execution": recursive_execution,
                "module_federation_recursive_traversal_followup": {"status": "next_step_review_ready"},
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_recursive_continuation_journal"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_continuation_journal_status=ready_for_review", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_writes_journal=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_remote_factory_invoked_by_journal=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_automatic_queue_advance=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_recursive_continuation_journal_append")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-continuation-journal.json")
        self.assertEqual(result.artifacts[0].metadata["record_count"], 0)
        self.assertFalse(result.artifacts[0].metadata["writes_journal_now"])

    def test_native_web_runtime_appends_reviewed_module_federation_recursive_continuation_journal(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        recursive_execution = {
            "status": "next_step_execution_progressed",
            "execution": {
                "status": "next_step_execution_progressed",
                "workflow_plan_id": "module-federation-traversal-workflow-plan",
                "workflow_execution_status": "factory_invoke_success",
                "selected_step_index": 0,
                "selected_node_id": "remote-module:window.remoteOther:./token",
                "selected_action": "review_module_federation_factory_invoke_for_traversal",
            },
            "side_effect_policy": {"remote_factory_invoked": True, "remote_code_executed": True},
        }

        result = runtime.apply_minimal_protection(
            "append-module-federation-recursive-continuation-journal",
            {
                "module_federation_recursive_traversal_execution": recursive_execution,
                "write_journal": True,
                "review_approved": True,
                "reviewer": "tester",
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["append_module_federation_recursive_continuation_journal"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_continuation_journal_status=journal_appended", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_writes_journal=True", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_remote_code_executed_by_journal=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_journal_traversal_graph_rebuilt=False", result.verification)
        self.assertEqual(result.next_action, "plan_next_module_federation_recursive_checkpoint_from_journal")
        self.assertEqual(result.artifacts[0].metadata["record_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["writes_journal_now"])
        self.assertFalse(result.artifacts[0].metadata["recursive_federation_traversal"])

    def test_native_web_runtime_plans_module_federation_recursive_continuation_checkpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        journal = {
            "status": "journal_appended",
            "record_count": 1,
            "records": [
                {
                    "recursive_execution_status": "next_step_execution_progressed",
                    "workflow_execution_status": "factory_invoke_success",
                    "selected_node_id": "remote-module:window.remoteOther:./token",
                    "selected_action": "review_module_federation_factory_invoke_for_traversal",
                }
            ],
        }

        result = runtime.apply_minimal_protection(
            "module-federation-recursive-continuation-checkpoint",
            {
                "module_federation_recursive_continuation_journal": journal,
                "module_federation_recursive_traversal_execution": {"status": "next_step_execution_progressed"},
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["plan_module_federation_recursive_continuation_checkpoint"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_continuation_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_remote_factory_invoked=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_remote_code_executed=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_automatic_queue_advance=False", result.verification)
        self.assertEqual(result.next_action, "review_module_federation_recursive_continuation_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/module-federation-recursive-continuation-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["source_journal_record_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["recursive_federation_traversal"])

    def test_native_web_runtime_executes_reviewed_module_federation_recursive_continuation_checkpoint(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        journal = {
            "status": "journal_appended",
            "record_count": 1,
            "records": [
                {
                    "recursive_execution_status": "next_step_execution_progressed",
                    "workflow_execution_status": "factory_invoke_success",
                    "selected_node_id": "remote-module:window.remoteOther:./token",
                    "selected_action": "review_module_federation_factory_invoke_for_traversal",
                }
            ],
        }
        get_init_plan = {
            "plan": {
                "candidates": [
                    {"container_path": "window.remoteOther", "exposed_name": "./token", "remote_name": "remoteOther"}
                ]
            }
        }

        result = runtime.apply_minimal_protection(
            "execute-module-federation-recursive-continuation-checkpoint",
            {
                "module_federation_recursive_continuation_journal": journal,
                "module_federation_recursive_traversal_execution": {"status": "next_step_execution_progressed"},
                "module_federation_get_init_plan": get_init_plan,
                "verify_execution": True,
                "rebuild_graph": True,
                "replan_workflow": True,
                "plan_next_execution_review": True,
                "review_approved": True,
            },
        )

        page = provider.session.context.pages[0]
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_module_federation_recursive_continuation_checkpoint"])
        self.assertEqual(page.module_federation_get_init_probes, [])
        self.assertEqual(page.module_federation_factory_invocations, [])
        self.assertIn("module_federation_recursive_continuation_checkpoint_status=next_execution_review_ready", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_traversal_graph_rebuilt=True", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_workflow_replanned=True", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_next_execution_review_planned=True", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_remote_code_executed=False", result.verification)
        self.assertIn("module_federation_recursive_continuation_checkpoint_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "review_next_module_federation_recursive_traversal_execution")
        self.assertTrue(result.artifacts[0].metadata["traversal_graph_rebuilt"])
        self.assertTrue(result.artifacts[0].metadata["workflow_replanned"])
        self.assertTrue(result.artifacts[0].metadata["next_execution_review_planned"])
        self.assertFalse(result.artifacts[0].metadata["remote_code_executed"])


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


    def test_native_web_runtime_installs_reviewed_module_federation_remote_export_hook(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-export-hook-install",
            {
                "module_federation_export_hook_plan": {
                    "status": "planned",
                    "plan": {
                        "status": "ready_for_review",
                        "candidates": [
                            {
                                "kind": "module-federation-remote-export",
                                "export_name": "token",
                                "export_type": "function",
                                "function_name": "token",
                                "container_path": "window.remoteOther",
                                "exposed_name": "./token",
                                "hook_kind": "remote-export-wrapper",
                                "hookable": True,
                                "requires_review_approval": True,
                                "automatic_hook_installation": False,
                                "recursive_federation_traversal": False,
                            }
                        ],
                    },
                },
                "selected_export_hook_candidate": {"container_path": "window.remoteOther", "exposed_name": "./token", "export_name": "token"},
                "review_approved": True,
                "trigger_expression": "window.remoteToken('demo')",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["hook_module_federation_remote_export:window.remoteOther:./token:token"])
        self.assertIn("module_federation_export_hook_install_status=success", result.verification)
        self.assertIn("module_federation_export_hook_review_approved=True", result.verification)
        self.assertIn("module_federation_export_hook_installed_count=1", result.verification)
        self.assertIn("module_federation_export_hook_event_count=2", result.verification)
        self.assertIn("module_federation_export_hook_recursive_federation_traversal=False", result.verification)
        self.assertEqual(result.next_action, "inspect_module_federation_export_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/function-hooks.json")
        self.assertEqual(result.artifacts[0].metadata["source"], "module_federation_export_hook_plan")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/function-hook-timeline.json")

    def test_native_web_runtime_blocks_module_federation_remote_export_hook_without_review(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "module-federation-export-hook-install",
            {
                "module_federation_export_hook_plan": {
                    "status": "planned",
                    "plan": {
                        "status": "ready_for_review",
                        "candidates": [
                            {
                                "kind": "module-federation-remote-export",
                                "export_name": "token",
                                "container_path": "window.remoteOther",
                                "exposed_name": "./token",
                                "hook_kind": "remote-export-wrapper",
                                "hookable": True,
                            }
                        ],
                    },
                },
                "selected_export_hook_candidate": {"container_path": "window.remoteOther", "exposed_name": "./token", "export_name": "token"},
            },
        )

        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("module_federation_export_hook_install_reason=review_approval_required", result.verification)
        self.assertEqual(result.next_action, "approve_module_federation_export_hook_candidate")
        self.assertFalse(result.artifacts[0].metadata["review_approved"])

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

    def test_native_web_runtime_plans_closure_wrapper_replacement_without_browser_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "closure-wrapper-replacement-plan",
            {
                "closure_function_candidates": [
                    {
                        "function_name": "buildSign",
                        "candidate_id": "closure:native-cf-1:buildSign",
                        "hook_kind": "closure-scope",
                        "hook_supported": False,
                        "callFrameId": "native-cf-1",
                        "evidence_expression": "typeof buildSign",
                    }
                ],
                "candidate_id": "closure:native-cf-1:buildSign",
                "closure_wrapper_runtime_mutability_result": {
                    "status": "proven",
                    "runtime_mutability_proven": True,
                    "function_name": "buildSign",
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["plan_closure_wrapper_replacement"])
        self.assertIn("closure_wrapper_replacement_plan_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_replacement_plan_only=True", result.verification)
        self.assertIn("closure_wrapper_replacement_strategy=log-only-call-through", result.verification)
        self.assertIn("closure_wrapper_replacement_strategy_supported_for_install=True", result.verification)
        self.assertIn("closure_wrapper_replacement_strategy_plan_only=False", result.verification)
        self.assertIn("closure_wrapper_replacement_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_replacement_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_replacement_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_replacement_callframe_evaluated=False", result.verification)
        self.assertEqual(result.next_action, "review_closure_wrapper_replacement_plan_before_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-replacement-plan.json")
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(result.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_installed"])
        self.assertFalse(result.artifacts[0].metadata["runtime_mutated"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["callframe_evaluated"])

    def test_native_web_runtime_proves_closure_wrapper_assignment_safety_without_browser_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        plan = {
            "status": "ready_for_review",
            "wrapper_strategy": "log-only-call-through",
            "runtime_mutated": False,
            "wrapper_installed": False,
            "selected_candidate": {
                "function_name": "buildSign",
                "candidate_id": "closure:native-cf-1:buildSign",
                "hook_kind": "closure-scope",
                "hook_supported": False,
                "callframe_index": 0,
                "callFrameId": "native-cf-1",
                "evidence_expression": "typeof buildSign",
            },
            "replacement_feasibility": {
                "lexical_binding_proven": True,
                "reviewed_executor_available": True,
                "reviewed_executor_scope": "same-process-retained-paused-session",
                "restore_plan_available_after_execution": True,
            },
        }
        result = runtime.apply_minimal_protection(
            "closure-wrapper-assignment-safety",
            {
                "closure_wrapper_replacement_plan": plan,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["prove_closure_wrapper_assignment_safety"])
        self.assertIn("closure_wrapper_assignment_safety_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_proven=True", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_strategy=log-only-call-through", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_strategy_supported_for_install=True", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_strategy_plan_only=False", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_assignment_safety_callframe_evaluated=False", result.verification)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-assignment-safety.json")
        self.assertTrue(result.artifacts[0].metadata["assignment_safety_proven"])
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(result.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertFalse(result.artifacts[0].metadata["runtime_mutated"])

    def test_native_web_runtime_preflights_closure_wrapper_runtime_mutability_without_browser_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        assignment_safety = {
            "status": "ready_for_review",
            "assignment_safety_proven": True,
            "safe_to_request_reviewed_execution": True,
            "runtime_mutability_proven": False,
            "function_name": "buildSign",
            "callFrameId": "native-cf-1",
            "wrapper_strategy": "log-only-call-through",
        }
        result = runtime.apply_minimal_protection(
            "closure-wrapper-runtime-mutability-preflight",
            {
                "closure_wrapper_assignment_safety": assignment_safety,
                "pause_session_id": "native-closure-exec",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, ["preflight_closure_wrapper_runtime_mutability"])
        self.assertIn("closure_wrapper_runtime_mutability_preflight_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_probe_ready_for_review=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_strategy=log-only-call-through", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_strategy_supported_for_install=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_strategy_plan_only=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_proven=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_callframe_evaluated=False", result.verification)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-runtime-mutability-preflight.json")
        self.assertTrue(result.artifacts[0].metadata["runtime_mutability_probe_ready_for_review"])
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(result.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertFalse(result.artifacts[0].metadata["runtime_mutability_proven"])
        self.assertFalse(result.artifacts[0].metadata["runtime_mutated"])

    def test_native_web_runtime_executes_reviewed_closure_wrapper_runtime_mutability_probe(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        discovery = runtime.apply_minimal_protection(
            "closure-function-discovery",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 4,
                "closure_function_names": ["buildSign"],
                "trigger_expression": "debugger; 'scheduled'",
                "preserve_pause_state": True,
                "pause_session_id": "native-closure-mutability-result",
            },
        )
        self.assertEqual(discovery.status.value, "success")
        preflight = {
            "status": "ready_for_review",
            "runtime_mutability_probe_ready_for_review": True,
            "runtime_mutability_proven": False,
            "runtime_mutability_probe_executed": False,
            "function_name": "buildSign",
            "expected_callframe_id": "native-cf-1",
            "pause_session_id": "native-closure-mutability-result",
            "wrapper_strategy": "log-only-call-through",
            "wrapper_installed": False,
        }

        result = runtime.apply_minimal_protection(
            "closure-wrapper-runtime-mutability-result",
            {
                "closure_wrapper_runtime_mutability_preflight": preflight,
                "pause_session_id": "native-closure-mutability-result",
                "execute_closure_wrapper_runtime_mutability_probe": True,
                "review_approved": True,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_reviewed_closure_wrapper_runtime_mutability_probe"])
        self.assertIn("closure_wrapper_runtime_mutability_result_status=proven", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_result_strategy=log-only-call-through", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_result_strategy_supported_for_install=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_result_strategy_plan_only=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_review_approved=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_proven=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_probe_executed=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_original_restored=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_runtime_mutated=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_cdp_command_sent=True", result.verification)
        self.assertIn("closure_wrapper_runtime_mutability_callframe_evaluated=True", result.verification)
        self.assertEqual(result.next_action, "review_runtime_mutability_result_then_optionally_execute_closure_wrapper_replacement")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-runtime-mutability-result.json")
        self.assertTrue(result.artifacts[0].metadata["runtime_mutability_proven"])
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(result.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertTrue(result.artifacts[0].metadata["original_restored"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_installed"])
        page = provider.session.context.pages[0]
        eval_calls = [params for method, params in page._cdp_session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("__reverseDeepAgentClosureMutabilityProbes", eval_calls[-1]["expression"])

    def test_native_web_runtime_executes_reviewed_closure_wrapper_replacement(self) -> None:
        BreakpointManager.clear_paused_sessions()
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        discovery = runtime.apply_minimal_protection(
            "closure-function-discovery",
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 4,
                "closure_function_names": ["buildSign"],
                "trigger_expression": "debugger; 'scheduled'",
                "preserve_pause_state": True,
                "pause_session_id": "native-closure-exec",
            },
        )
        self.assertEqual(discovery.status.value, "success")
        plan = runtime.apply_minimal_protection(
            "closure-wrapper-replacement-plan",
            {
                "closure_function_candidates": [
                    {
                        "function_name": "buildSign",
                        "candidate_id": "closure:native-cf-1:buildSign",
                        "hook_kind": "closure-scope",
                        "hook_supported": False,
                        "callframe_index": 0,
                        "callFrameId": "native-cf-1",
                        "evidence_expression": "typeof buildSign",
                    }
                ],
                "candidate_id": "closure:native-cf-1:buildSign",
            },
        )
        self.assertEqual(plan.status.value, "partial")
        replacement_plan_payload = {
            "status": "ready_for_review",
            "wrapper_strategy": "log-only-call-through",
            "runtime_mutated": False,
            "wrapper_installed": False,
            "selected_candidate": {
                "function_name": "buildSign",
                "candidate_id": "closure:native-cf-1:buildSign",
                "hook_kind": "closure-scope",
                "hook_supported": False,
                "callframe_index": 0,
                "callFrameId": "native-cf-1",
                "evidence_expression": "typeof buildSign",
            },
            "replacement_feasibility": {
                "lexical_binding_proven": True,
                "reviewed_executor_available": True,
                "reviewed_executor_scope": "same-process-retained-paused-session",
                "restore_plan_available_after_execution": True,
            },
        }
        assignment_safety = runtime.apply_minimal_protection(
            "closure-wrapper-assignment-safety",
            {
                "closure_wrapper_replacement_plan": replacement_plan_payload,
            },
        )
        self.assertEqual(assignment_safety.status.value, "partial")

        result = runtime.apply_minimal_protection(
            "closure-wrapper-replacement-execution",
            {
                "closure_wrapper_replacement_plan": replacement_plan_payload,
                "closure_wrapper_assignment_safety": {
                    "assignment_safety_proven": True,
                    "safe_to_request_reviewed_execution": True,
                    "function_name": "buildSign",
                    "callFrameId": "native-cf-1",
                    "wrapper_strategy": "log-only-call-through",
                },
                "closure_wrapper_runtime_mutability_result": {
                    "status": "proven",
                    "runtime_mutability_proven": True,
                    "runtime_mutability_probe_executed": True,
                    "temporary_assignment_confirmed": True,
                    "original_restored": True,
                    "wrapper_installed": False,
                    "function_name": "buildSign",
                    "expected_callframe_id": "native-cf-1",
                    "observed_callframe_id": "native-cf-1",
                    "pause_session_id": "native-closure-exec",
                    "wrapper_strategy": "log-only-call-through",
                },
                "require_closure_wrapper_runtime_mutability_result": True,
                "pause_session_id": "native-closure-exec",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_reviewed_closure_wrapper_replacement"])
        self.assertIn("closure_wrapper_replacement_execution_status=applied", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_strategy=log-only-call-through", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_strategy_supported_for_install=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_strategy_plan_only=False", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_assignment_safety_proven=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_require_runtime_mutability_result=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_runtime_mutability_result_proven=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_review_approved=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_wrapper_installed=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_runtime_mutated=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_cdp_command_sent=True", result.verification)
        self.assertIn("closure_wrapper_replacement_execution_callframe_evaluated=True", result.verification)
        self.assertEqual(result.next_action, "invoke_target_flow_and_review_closure_wrapper_events_or_restore")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-replacement-execution.json")
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(result.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(result.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertTrue(result.artifacts[0].metadata["wrapper_installed"])
        self.assertTrue(result.artifacts[0].metadata["runtime_mutated"])
        self.assertTrue(result.artifacts[0].metadata["require_runtime_mutability_result"])
        self.assertTrue(result.artifacts[0].metadata["runtime_mutability_result_proven"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/closure-wrapper-restore-plan.json")
        self.assertTrue(result.artifacts[1].metadata["available"])
        self.assertEqual(result.artifacts[1].metadata["wrapper_strategy"], "log-only-call-through")
        page = provider.session.context.pages[0]
        eval_calls = [params for method, params in page._cdp_session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])

        restore = runtime.apply_minimal_protection(
            "closure-wrapper-restore-execution",
            {
                "closure_wrapper_restore_plan": {
                    "available": True,
                    "requires_review": True,
                    "function_name": "buildSign",
                    "marker": "reverse-deepagent:closure-wrapper:closure:native-cf-1:buildSign",
                    "wrapper_strategy": "log-only-call-through",
                    "restore_expression": ClosureWrapperReplacementExecutionManager._restore_expression(
                        function_name="buildSign",
                        marker="reverse-deepagent:closure-wrapper:closure:native-cf-1:buildSign",
                    ),
                },
                "pause_session_id": "native-closure-exec",
                "execute_closure_wrapper_restore": True,
                "review_approved": True,
            },
        )

        self.assertEqual(restore.status.value, "success")
        self.assertEqual(restore.applied_actions, ["execute_reviewed_closure_wrapper_restore"])
        self.assertIn("closure_wrapper_restore_execution_status=restored", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_strategy=log-only-call-through", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_strategy_supported_for_install=True", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_strategy_plan_only=False", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_review_approved=True", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_wrapper_restored=True", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_runtime_mutated=True", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_cdp_command_sent=True", restore.verification)
        self.assertIn("closure_wrapper_restore_execution_callframe_evaluated=True", restore.verification)
        self.assertEqual(restore.next_action, "review_closure_wrapper_restore_result_or_continue_target_flow")
        self.assertEqual(restore.artifacts[0].path, "virtual://workspace/closure-wrapper-restore-execution.json")
        self.assertEqual(restore.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertTrue(restore.artifacts[0].metadata["wrapper_strategy_supported_for_install"])
        self.assertFalse(restore.artifacts[0].metadata["wrapper_strategy_plan_only"])
        self.assertTrue(restore.artifacts[0].metadata["wrapper_restored"])
        self.assertTrue(restore.artifacts[0].metadata["runtime_mutated"])
        eval_calls = [params for method, params in page._cdp_session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("__rdgOriginal", eval_calls[-1]["expression"])

        events = runtime.apply_minimal_protection(
            "closure-wrapper-events",
            {
                "closure_wrapper_events": True,
                "function_name": "buildSign",
                "limit": 10,
            },
        )

        self.assertEqual(events.status.value, "success")
        self.assertEqual(events.applied_actions, ["harvest_closure_wrapper_events"])
        self.assertIn("closure_wrapper_events_status=success", events.verification)
        self.assertIn("closure_wrapper_events_count=1", events.verification)
        self.assertIn("closure_wrapper_events_strategy_count=1", events.verification)
        self.assertIn("closure_wrapper_events_runtime_mutated=False", events.verification)
        self.assertIn("closure_wrapper_events_cdp_command_sent=False", events.verification)
        self.assertEqual(events.next_action, "inspect_closure_wrapper_events")
        self.assertEqual(events.artifacts[0].path, "virtual://workspace/closure-wrapper-events.json")
        self.assertEqual(events.artifacts[0].metadata["event_count"], 1)
        self.assertEqual(events.artifacts[0].metadata["strategy_counts"]["log-only-call-through"], 1)
        self.assertFalse(events.artifacts[0].metadata["runtime_mutated"])
        BreakpointManager.clear_paused_sessions()

    def test_native_web_runtime_reviews_closure_wrapper_continuation_readiness_without_side_effects(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "closure-wrapper-continuation-readiness",
            {
                "closure_wrapper_replacement_execution": {
                    "execution": {
                        "status": "applied",
                        "function_name": "buildSign",
                        "marker": "reverse-deepagent:closure-wrapper:buildSign",
                        "wrapper_strategy": "log-only-call-through",
                        "wrapper_strategy_descriptor": {
                            "strategy": "log-only-call-through",
                            "supported_for_install": True,
                            "strategy_plan_only": False,
                        },
                        "wrapper_installed": True,
                        "restore_plan": {"available": True, "requires_review": True},
                    }
                },
                "closure_wrapper_events": {"status": "success", "event_count": 1},
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "continuation_ready_for_next_action": True,
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_closure_wrapper_continuation_readiness"])
        self.assertIn("closure_wrapper_continuation_readiness_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_ready_for_review=True", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_wrapper_installed=True", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_continuation_ready=True", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_cross_process_wrapper_execution_supported=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_callframe_evaluated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_wrapper_continuation_readiness")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-readiness.json")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["same_process_wrapper_installed"])
        self.assertTrue(result.artifacts[0].metadata["continuation_ready"])
        self.assertFalse(result.artifacts[0].metadata["cross_process_wrapper_execution_supported"])
        self.assertFalse(result.artifacts[0].metadata["automatic_wrapper_continuation"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])

    def test_native_web_runtime_plans_closure_wrapper_continuation_execution_without_side_effects(self) -> None:
        provider = FakeProvider()
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "closure-wrapper-continuation-execution-plan",
            {
                "closure_wrapper_continuation_execution_plan": True,
                "reviewer": "native-reviewer",
                "closure_wrapper_continuation_readiness": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "same_process_wrapper_installed": True,
                    "restore_plan_available": True,
                    "wrapper_strategy": "log-only-call-through",
                    "function_name": "buildSign",
                    "marker": "reverse-deepagent:closure-wrapper:buildSign",
                    "continuation_ready": True,
                    "wrapper_event_count": 1,
                },
                "paused_session_cross_process_session_lifecycle": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                },
                "paused_session_multi_step_loop_plan": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "readiness": {
                        "next_loop_iteration_reviewable": True,
                        "automatic_multi_step_loop_supported": False,
                    },
                    "next_iteration": {
                        "workflow_step_index": 2,
                        "method": "Debugger.stepOver",
                        "fingerprint": "native-wrapper-loop-step-2",
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_closure_wrapper_continuation_execution_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-execution-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["same_process_wrapper_installed"])
        self.assertTrue(result.artifacts[0].metadata["restore_plan_available"])
        self.assertFalse(result.artifacts[0].metadata["cross_process_wrapper_execution_supported"])
        self.assertFalse(result.artifacts[0].metadata["automatic_wrapper_continuation"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertIn("closure_wrapper_continuation_execution_plan_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_ready_for_review=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_wrapper_installed=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_restore_plan_available=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_cross_process_wrapper_execution_supported=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_requires_execution_approval=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_debugger_event_subscribed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_paused_event_captured=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_callframe_evaluated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_wrapper_installed_by_manager=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_wrapper_restored=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_plan_mobile_runtime_used=False", result.verification)
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["runtime_mutated"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["wrapper_installed"])
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_native_web_runtime_executes_reviewed_closure_wrapper_continuation_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "closure-wrapper-continuation-execution",
            {
                "closure_wrapper_continuation_execution": True,
                "execute_closure_wrapper_continuation": True,
                "review_approved": True,
                "selected_step_index": 1,
                "closure_wrapper_continuation_execution_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "native-wrapper-plan-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "same_process_wrapper_installed": True,
                        "restore_plan_available": True,
                        "execution_strategy": {
                            "supported_strategy": "log-only-call-through",
                            "automatic_wrapper_continuation_supported": False,
                            "automatic_multi_step_loop_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-wrapper-workflow-1",
                        "planned_steps": [
                            {"step_index": 1, "requested_action": "step_over", "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"}
                        ],
                        "duplicate_fingerprints": [],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-wrapper-cf-1",
                        "live_callframe_recovered": True,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-wrapper-cf-1",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-wrapper-cf-2",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 9, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_reviewed_closure_wrapper_continuation_iteration"])
        self.assertEqual(result.next_action, "harvest_wrapper_events_and_checkpoint_continuation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-execution.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[0].metadata["selected_method"], "Debugger.stepOver")
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertTrue(result.artifacts[0].metadata["post_execution_event_harvest_required"])
        self.assertIn("closure_wrapper_continuation_execution_status=executed", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_cdp_command_sent=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_event_subscribed=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_paused_event_captured=True", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_wrapper_restored=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_wrapper_events_harvested=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_native_web_runtime_reviews_closure_wrapper_continuation_checkpoint_without_side_effects(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "closure-wrapper-continuation-checkpoint",
            {
                "closure_wrapper_continuation_checkpoint": True,
                "closure_wrapper_continuation_execution": {
                    "execution": {
                        "status": "executed",
                        "plan_id": "native-wrapper-plan-1",
                        "workflow_id": "native-wrapper-workflow-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "selected_step_index": 1,
                        "selected_method": "Debugger.stepOver",
                        "wrapper_continuation_iteration_executed": True,
                        "paused_event_captured": True,
                        "post_execution_event_harvest_required": True,
                        "manual_checkpoint_required_after_step": True,
                        "automatic_wrapper_continuation": False,
                        "automatic_multi_step_loop": False,
                    }
                },
                "closure_wrapper_events": {"status": "success", "event_count": 1},
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "paused_event_captured": True,
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovered": True,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "next_iteration": {
                            "available": True,
                            "workflow_step_index": 2,
                            "method": "Debugger.stepOver",
                        }
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_next_closure_wrapper_continuation_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[0].metadata["post_execution_event_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["paused_session_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_available"])
        self.assertIn("closure_wrapper_continuation_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_event_count=1", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_event_subscribed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_paused_event_captured=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_wrapper_restored=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_wrapper_events_harvested=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_iteration_executed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_native_web_runtime_plans_closure_wrapper_continuation_next_iteration_without_side_effects(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "closure-wrapper-continuation-next-iteration-plan",
            {
                "closure_wrapper_continuation_next_iteration_plan": True,
                "closure_wrapper_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "native-wrapper-plan-1",
                        "workflow_id": "native-wrapper-workflow-1",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "post_execution_event_count": 1,
                        "paused_session_checkpoint_status": "ready_for_next_action_review",
                        "next_iteration_available": True,
                        "next_iteration_step_index": 2,
                        "next_iteration_method": "Debugger.stepOver",
                        "followup_requirements": {
                            "manual_review_required_before_next_iteration": True,
                            "automatic_wrapper_continuation": False,
                            "automatic_multi_step_loop": False,
                        },
                    }
                },
                "closure_wrapper_continuation_execution_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "native-wrapper-plan-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "same_process_wrapper_installed": True,
                        "restore_plan_available": True,
                        "execution_strategy": {
                            "supported_strategy": "log-only-call-through",
                            "automatic_wrapper_continuation_supported": False,
                            "automatic_multi_step_loop_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "workflow_id": "native-wrapper-workflow-1",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "next_iteration": {
                            "available": True,
                            "workflow_step_index": 2,
                            "method": "Debugger.stepOver",
                            "fingerprint": "2:Debugger.stepOver:",
                        },
                        "readiness": {"automatic_multi_step_loop_supported": False},
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "recover_live_callframe_for_next_wrapper_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-next-iteration-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[0].metadata["next_iteration_step_index"], 2)
        self.assertEqual(result.artifacts[0].metadata["next_iteration_method"], "Debugger.stepOver")
        self.assertTrue(result.artifacts[0].metadata["fresh_live_callframe_required_before_execution"])
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_status=ready_for_review", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_step_index=2", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_method=Debugger.stepOver", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_cdp_command_sent=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_event_subscribed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_paused_event_captured=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_wrapper_restored=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_wrapper_events_harvested=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_live_callframe_recovered=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_iteration_executed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_queue_advanced=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_native_web_runtime_executes_reviewed_closure_wrapper_continuation_next_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "execute-closure-wrapper-continuation-next-iteration",
            {
                "closure_wrapper_continuation_next_iteration_execution": True,
                "execute_closure_wrapper_continuation_next_iteration": True,
                "review_approved": True,
                "selected_step_index": 2,
                "closure_wrapper_continuation_next_iteration_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "native-wrapper-next-plan-1",
                        "source_execution_plan_id": "native-wrapper-plan-1",
                        "source_workflow_id": "native-wrapper-workflow-1",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "next_iteration_available": True,
                        "next_iteration_step_index": 2,
                        "next_iteration_method": "Debugger.stepOver",
                        "review_gates": {
                            "manual_review_required_before_execution": True,
                            "automatic_wrapper_continuation": False,
                            "automatic_multi_step_loop": False,
                        },
                    }
                },
                "closure_wrapper_continuation_execution_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "native-wrapper-plan-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "same_process_wrapper_installed": True,
                        "restore_plan_available": True,
                        "execution_strategy": {
                            "supported_strategy": "log-only-call-through",
                            "automatic_wrapper_continuation_supported": False,
                            "automatic_multi_step_loop_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-wrapper-workflow-1",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "planned_steps": [
                            {"step_index": 1, "requested_action": "step_over", "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"},
                            {"step_index": 2, "requested_action": "step_over", "method": "Debugger.stepOver", "fingerprint": "2:Debugger.stepOver:"},
                        ],
                        "duplicate_fingerprints": [],
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "next_iteration": {"available": True, "workflow_step_index": 2, "method": "Debugger.stepOver"},
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-wrapper-pause-1",
                        "target_id": "native-wrapper-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-wrapper-cf-2",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "paused_session_cross_process_attach_probe": {
                    "probe": {"status": "attached", "attached_session_id": "attached-session-1", "target_attached": True, "target_detached": False}
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-wrapper-cf-2",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-wrapper-cf-3",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 10, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_closure_wrapper_next_iteration"])
        self.assertEqual(result.next_action, "harvest_wrapper_events_and_checkpoint_next_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/closure-wrapper-continuation-next-iteration-execution.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertEqual(result.artifacts[0].metadata["wrapper_strategy"], "log-only-call-through")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertEqual(result.artifacts[0].metadata["selected_step_index"], 2)
        self.assertEqual(result.artifacts[0].metadata["selected_method"], "Debugger.stepOver")
        self.assertTrue(result.artifacts[0].metadata["wrapper_next_iteration_executed"])
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_status=executed", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_cdp_command_sent=True", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_event_subscribed=True", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_paused_event_captured=True", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_runtime_mutated=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_wrapper_installed=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_wrapper_restored=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_wrapper_events_harvested=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_live_callframe_recovered=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_queue_advanced=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_loop_advanced=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_automatic_multi_step_loop=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_calls_mcp=False", result.verification)
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_native_web_runtime_reviews_cross_process_session_lifecycle_without_side_effects(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)

        result = runtime.apply_minimal_protection(
            "paused-session-cross-process-session-lifecycle",
            {
                "paused_session_cross_process_attach_probe": {
                    "probe": {
                        "status": "attached",
                        "pause_session_id": "native-lifecycle-1",
                        "target_id": "target-native-lifecycle",
                        "attached_session_id": "attached-session-1",
                        "target_attached": True,
                        "target_detached": False,
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-lifecycle-1",
                        "target_id": "target-native-lifecycle",
                        "attached_session_id": "attached-session-1",
                        "target_attached": True,
                        "fresh_paused_event_after_attach": True,
                        "live_callframe_recovered": True,
                        "live_callframe_id": "live-cf-native-lifecycle",
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-lifecycle-1",
                        "target_id": "target-native-lifecycle",
                        "continuation_ready_for_next_action": True,
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("paused_session_cross_process_session_lifecycle_status=ready_for_review", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_ready_for_review=True", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_target_still_alive_proven=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_automatic_multi_step_loop=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_automatic_wrapper_continuation=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_cdp_target_attached=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_debugger_event_subscribed=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_cross_process_action_executed=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_calls_mcp=False", result.verification)
        self.assertIn("paused_session_cross_process_session_lifecycle_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_paused_session_lifecycle_before_next_continuation_step")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-cross-process-session-lifecycle.json")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["target_still_alive_proven"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["automatic_wrapper_continuation"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])

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


    def test_native_web_runtime_reviews_heap_snapshot_readiness_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "heap-snapshot-readiness",
            {
                "heap_snapshot_readiness": True,
                "browser_provider_id": "remote-cdp",
                "cdp_available": True,
                "heap_profiler_capability": "provided",
                "max_snapshot_bytes": 2048,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_readiness_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_readiness_provider_id=remote-cdp", result.verification)
        self.assertIn("heap_snapshot_readiness_cdp_available=True", result.verification)
        self.assertIn("heap_snapshot_readiness_heap_profiler_capability=provided", result.verification)
        self.assertIn("heap_snapshot_readiness_heap_snapshot_collected=False", result.verification)
        self.assertIn("heap_snapshot_readiness_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_readiness_raw_heap_export_allowed=False", result.verification)
        self.assertIn("heap_snapshot_readiness_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_readiness_provider_factory_invoked=False", result.verification)
        self.assertIn("heap_snapshot_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_readiness_heap_profiler_enabled=False", result.verification)
        self.assertIn("heap_snapshot_readiness_runtime_evaluated=False", result.verification)
        self.assertIn("heap_snapshot_readiness_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_readiness_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_readiness_before_collection")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-readiness.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["browser_provider_id"], "remote-cdp")
        self.assertTrue(result.artifacts[0].metadata["cdp_available"])
        self.assertEqual(result.artifacts[0].metadata["heap_profiler_capability"], "provided")
        self.assertFalse(result.artifacts[0].metadata["heap_snapshot_collected"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_export_allowed"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal_claimed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_blocks_heap_snapshot_collect_without_review_before_cdp(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        readiness = {
            "schema_version": "reverse-deepagent.heap-snapshot-readiness.v1",
            "status": "ready_for_review",
            "capability_evidence": {"browser_provider_id": "fake-native", "cdp_available": True, "heap_profiler_capability": "provided"},
            "safety_gates": {"max_snapshot_bytes": 4096, "redaction_plan": "required", "raw_heap_export_allowed": False},
        }
        result = runtime.apply_minimal_protection(
            "heap-snapshot-collect",
            {
                "heap_snapshot_collect": True,
                "collect_heap_snapshot": True,
                "heap_snapshot_readiness": readiness,
            },
        )

        cdp_calls = provider.session.context.pages[0]._cdp_session.calls
        self.assertEqual(provider.started, 1)
        self.assertEqual(cdp_calls, [])
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_collect_status=blocked", result.verification)
        self.assertIn("heap_snapshot_collect_reason=heap_snapshot_collect_review_approval_required", result.verification)
        self.assertIn("heap_snapshot_collect_cdp_command_sent=False", result.verification)
        self.assertEqual(result.next_action, "resolve_heap_snapshot_collect_blockers")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-collect.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
        self.assertFalse(result.artifacts[0].metadata["heap_snapshot_collected"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])

    def test_native_web_runtime_collects_heap_snapshot_metadata_with_review_gates(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        readiness = {
            "schema_version": "reverse-deepagent.heap-snapshot-readiness.v1",
            "status": "ready_for_review",
            "capability_evidence": {"browser_provider_id": "fake-native", "cdp_available": True, "heap_profiler_capability": "provided"},
            "safety_gates": {"max_snapshot_bytes": 4096, "redaction_plan": "required", "raw_heap_export_allowed": False},
        }
        result = runtime.apply_minimal_protection(
            "heap-snapshot-collect",
            {
                "heap_snapshot_collect": True,
                "collect_heap_snapshot": True,
                "review_approved": True,
                "heap_snapshot_readiness": readiness,
                "max_snapshot_bytes": 4096,
            },
        )

        cdp_calls = provider.session.context.pages[0]._cdp_session.calls
        self.assertEqual(provider.started, 1)
        self.assertEqual([call[0] for call in cdp_calls], ["HeapProfiler.enable", "HeapProfiler.takeHeapSnapshot", "HeapProfiler.disable"])
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["collect_heap_snapshot_metadata"])
        self.assertIn("heap_snapshot_collect_status=collected", result.verification)
        self.assertIn("heap_snapshot_collect_collected=True", result.verification)
        self.assertTrue(any(item.startswith("heap_snapshot_collect_digest=sha256:") for item in result.verification))
        self.assertIn("heap_snapshot_collect_chunk_count=1", result.verification)
        self.assertIn("heap_snapshot_collect_cdp_command_sent=True", result.verification)
        self.assertIn("heap_snapshot_collect_heap_profiler_enabled=True", result.verification)
        self.assertIn("heap_snapshot_collect_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_collect_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_collect_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_collect_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_collect_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_collect_before_heap_diff")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-collect.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "collected")
        self.assertTrue(result.artifacts[0].metadata["heap_snapshot_collected"])
        self.assertTrue(result.artifacts[0].metadata["snapshot_digest"].startswith("sha256:"))
        self.assertGreater(result.artifacts[0].metadata["snapshot_byte_count"], 0)
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_diff_readiness_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        before = {
            "schema_version": "reverse-deepagent.heap-snapshot-collect.v1",
            "status": "collected",
            "heap_snapshot_collected": True,
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "raw_heap_available_in_artifact": False,
            "complete_heap_traversal_claimed": False,
            "snapshot_metadata": {"snapshot_digest": "sha256:before", "snapshot_byte_count": 64, "chunk_count": 1, "redacted_summary_only": True},
            "readiness_summary": {"browser_provider_id": "fake-native"},
            "side_effect_policy": {"cdp_command_sent": True, "heap_diff_computed": False, "raw_heap_exported": False, "complete_heap_traversal": False},
        }
        after = {
            "schema_version": "reverse-deepagent.heap-snapshot-collect.v1",
            "status": "collected",
            "heap_snapshot_collected": True,
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "raw_heap_available_in_artifact": False,
            "complete_heap_traversal_claimed": False,
            "snapshot_metadata": {"snapshot_digest": "sha256:after", "snapshot_byte_count": 96, "chunk_count": 1, "redacted_summary_only": True},
            "readiness_summary": {"browser_provider_id": "fake-native"},
            "side_effect_policy": {"cdp_command_sent": True, "heap_diff_computed": False, "raw_heap_exported": False, "complete_heap_traversal": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-readiness",
            {
                "heap_snapshot_diff_readiness": True,
                "before_heap_snapshot_collect": before,
                "after_heap_snapshot_collect": after,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_readiness_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_before_digest=sha256:before", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_after_digest=sha256:after", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_byte_delta=32", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_future_diff_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_readiness_before_diff_executor")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-readiness.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["before_digest"], "sha256:before")
        self.assertEqual(result.artifacts[0].metadata["after_digest"], "sha256:after")
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_diff_executor_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        readiness = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-readiness.v1",
            "status": "ready_for_review",
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_exported": False,
            "complete_heap_traversal_claimed": False,
            "pair_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "byte_delta": 32, "digest_equal": False},
            "safety_gates": {"future_diff_executor_implemented": False},
            "side_effect_policy": {"heap_diff_computed": False, "raw_heap_loaded": False, "raw_heap_exported": False, "complete_heap_traversal": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-executor-preflight",
            {
                "heap_snapshot_diff_executor_preflight": True,
                "review_approved": True,
                "heap_snapshot_diff_readiness": readiness,
                "raw_heap_ingestion_policy": "metadata-only",
                "parser_sandbox": "subprocess",
                "redaction_plan": "digest-only",
                "max_raw_heap_bytes": 1024,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_executor_preflight_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_before_digest=sha256:before", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_after_digest=sha256:after", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_raw_heap_ingestion_policy=metadata-only", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_future_diff_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_executor_preflight_before_implementation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-executor-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["raw_heap_ingestion_policy"], "metadata-only")
        self.assertFalse(result.artifacts[0].metadata["future_diff_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_diff_executor_approval_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-preflight.v1",
            "status": "ready_for_review",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "readiness_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after"},
            "ingestion_policy": {"raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 1024},
            "safety_gates": {"review_approved": True, "future_diff_executor_implemented": False},
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "complete_heap_traversal": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-executor-approval-plan",
            {
                "heap_snapshot_diff_executor_approval_plan": True,
                "heap_snapshot_diff_executor_preflight": preflight,
                "reviewer": "alice",
                "transaction_id": "heap-diff-txn-1",
                "idempotency_key": "heap-diff-idem-1",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_executor_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_before_digest=sha256:before", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_after_digest=sha256:after", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_approval_scope=heap-snapshot-diff-executor", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_idempotency_key=heap-diff-idem-1", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_transaction_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_journal_written_now=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_executor_invoked=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_approval_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-executor-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["approval_scope"], "heap-snapshot-diff-executor")
        self.assertFalse(result.artifacts[0].metadata["approval_recorded"])
        self.assertEqual(result.artifacts[0].metadata["transaction_id"], "heap-diff-txn-1")
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written_now"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_diff_executor_transaction_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        approval_plan = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1",
            "status": "ready_for_review",
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "heap_snapshot_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "preflight_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 1024},
            "approval_plan": {"approval_scope": "heap-snapshot-diff-executor", "reviewer": "alice", "approval_record_artifact": "workspace/heap-snapshot-diff-executor-approval-record.json", "approval_recorded": False},
            "transaction_plan": {"transaction_id": "heap-diff-txn-1", "idempotency_key": "heap-diff-idem-1", "transaction_journal_artifact": "workspace/heap-snapshot-diff-executor-journal.json", "bounded_gate_artifact": "workspace/heap-snapshot-diff-executor-bounded-gate.json", "result_artifact": "workspace/heap-snapshot-diff-executor-result.json", "transaction_started": False, "journal_written_now": False},
            "future_executor_contract": {"implemented": False},
            "side_effect_policy": {"approval_recorded": False, "transaction_started": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "heap_snapshot_diff_computed": False, "complete_heap_traversal": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        approval_record = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1",
            "status": "written",
            "approval_scope": "heap-snapshot-diff-executor",
            "reviewer": "alice",
            "approval_recorded": True,
            "approved_for_execution": True,
            "transaction_id": "heap-diff-txn-1",
            "idempotency_key": "heap-diff-idem-1",
            "executor_input_gates": {"transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
            "side_effect_policy": {"transaction_started": False, "journal_written": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "heap_snapshot_diff_computed": False, "complete_heap_traversal": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-executor-transaction-preflight",
            {
                "heap_snapshot_diff_executor_transaction_preflight": True,
                "heap_snapshot_diff_executor_approval_plan": approval_plan,
                "heap_snapshot_diff_executor_approval_record": approval_record,
                "expected_transaction_id": "heap-diff-txn-1",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_approval_scope=heap-snapshot-diff-executor", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_approval_recorded=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_approved_for_execution=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_ready_to_write_journal=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_transaction_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_journal_written=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_bounded_executor_gate_written=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_executor_invoked=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_executor_transaction_journal_writer")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-executor-transaction-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_journal_review"])
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])


    def test_native_web_runtime_reviews_heap_snapshot_diff_executor_bounded_gate_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        transaction_journal = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "heap-snapshot-diff-executor-transaction-journal:abc123",
            "transaction_preflight_id": "heap-snapshot-diff-executor-transaction-preflight:def456",
            "transaction_id": "heap-diff-txn-1",
            "idempotency_key": "heap-diff-idem-1",
            "approval_scope": "heap-snapshot-diff-executor",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "preflight_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 1024},
            "journal_summary": {"transaction_started": True, "journal_written": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "requires_bounded_executor_gate_followup": True},
            "executor_input_gates": {"approval_record_verified": True, "transaction_started": True, "journal_written": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "complete_heap_traversal_claimed": False, "diff_executor_implemented": False, "requires_bounded_executor_gate": True, "requires_explicit_executor_review": True, "ready_to_execute_now": False},
            "blockers": [],
            "side_effect_policy": {"writes_transaction_journal": True, "transaction_started": True, "journal_written": True, "bounded_executor_gate_written": False, "ready_to_execute_now": False, "executor_invoked": False, "browser_started": False, "provider_factory_invoked": False, "cdp_command_sent": False, "heap_profiler_enabled": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "heap_snapshot_diff_computed": False, "complete_heap_traversal": False, "runtime_evaluated": False, "javascript_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-executor-bounded-gate",
            {
                "heap_snapshot_diff_executor_bounded_gate": True,
                "heap_snapshot_diff_executor_transaction_journal": transaction_journal,
                "expected_transaction_id": "heap-diff-txn-1",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_journal_written=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_ready_for_review=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_requires_safe_raw_heap_parser=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_executor_invoked=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-executor-bounded-gate.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["bounded_executor_gate_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_executes_heap_snapshot_diff_executor_mvp_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        bounded_gate = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1",
            "status": "ready_for_review",
            "journal_id": "heap-snapshot-diff-executor-transaction-journal:abc123",
            "transaction_id": "heap-diff-txn-1",
            "idempotency_key": "heap-diff-idem-1",
            "bounded_executor_gate_ready_for_review": True,
            "ready_for_executor_review": True,
            "ready_to_execute_now": False,
            "side_effect_policy": {"executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
        }

        result = runtime.apply_minimal_protection(
            "execute-heap-snapshot-diff-executor",
            {
                "execute_heap_snapshot_diff_executor": True,
                "heap_snapshot_diff_executor_bounded_gate": bounded_gate,
                "before_heap_snapshot": _v8_heap_snapshot_for_native_test(extra_object=False),
                "after_heap_snapshot": _v8_heap_snapshot_for_native_test(extra_object=True),
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_diff_executor_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_heap_snapshot_diff_executor_mvp"])
        self.assertIn("heap_snapshot_diff_executor_result_status=executed", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_executor_invoked=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_raw_heap_loaded=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_raw_heap_parsed=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_heap_diff_computed=True", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_mobile_runtime_used=False", result.verification)
        self.assertIn("heap_snapshot_diff_executor_result_node_delta=1", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_executor_result_before_followup")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-executor-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertTrue(result.artifacts[0].metadata["executor_mvp"])
        self.assertTrue(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_exported"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal_claimed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])



    def test_native_web_runtime_reviews_heap_snapshot_diff_followup_checkpoint_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        executor_result = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-result.v1",
            "status": "executed",
            "executor_name": "execute_heap_snapshot_diff_executor",
            "executor_mvp": True,
            "result_artifact": "workspace/heap-snapshot-diff-executor-result.json",
            "reviewer": "alice",
            "gate_summary": {"transaction_id": "heap-diff-txn-1"},
            "heap_summaries": {
                "before": {"raw_heap_digest_sha256": "sha256:before", "node_count_total": 2, "edge_count_total": 1},
                "after": {"raw_heap_digest_sha256": "sha256:after", "node_count_total": 3, "edge_count_total": 2},
            },
            "diff": {
                "node_count_delta": 1,
                "edge_count_delta": 1,
                "self_size_total_analyzed_delta": 64,
                "node_type_deltas": [{"name": "object", "before": 1, "after": 2, "delta": 1}],
                "top_constructor_deltas": [{"name": "LeakyThing", "before": 0, "after": 1, "delta": 1}],
            },
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "heap_diff_computed": True,
            "complete_heap_traversal_claimed": False,
            "summary_only": True,
            "side_effect_policy": {"raw_heap_exported": False, "raw_strings_exported": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-followup-checkpoint",
            {
                "heap_snapshot_diff_followup_checkpoint": True,
                "heap_snapshot_diff_executor_result": executor_result,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_followup_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_executor_result_status=executed", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_node_delta=1", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_retained_size_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_path_to_root_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_complete_heap_traversal=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_followup_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-followup-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertFalse(result.artifacts[0].metadata["retained_size_analysis_implemented"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_analysis_implemented"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_diff_selected_analysis_input_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        checkpoint = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1",
            "status": "ready_for_review",
            "review_only": True,
            "checkpoint_only": True,
            "checkpoint_artifact": "workspace/heap-snapshot-diff-followup-checkpoint.json",
            "executor_result_summary": {"status": "executed", "transaction_id": "heap-diff-txn-1", "result_artifact": "workspace/heap-snapshot-diff-executor-result.json"},
            "analysis_plan": {
                "summary_delta_review": {"node_count_delta": 1, "edge_count_delta": 1, "self_size_total_analyzed_delta": 64, "analysis_truncated": False},
                "top_growth_signals": {
                    "constructor_deltas": [{"name": "LeakyThing", "before": 0, "after": 1, "delta": 1}],
                    "node_type_deltas": [{"name": "object", "before": 1, "after": 2, "delta": 1}],
                    "edge_type_deltas": [],
                },
                "recommendations": [
                    {"action": "review_constructor_growth", "requires_review": True},
                    {"action": "plan_retained_size_analysis", "requires_review": True, "implemented": False},
                ],
            },
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-diff-selected-analysis-input-preflight",
            {
                "heap_snapshot_diff_selected_analysis_input_preflight": True,
                "heap_snapshot_diff_followup_checkpoint": checkpoint,
                "selected_analysis_action": "plan_retained_size_analysis",
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_selected_action=plan_retained_size_analysis", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_source_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-diff-selected-analysis-input-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["selected_action"], "plan_retained_size_analysis")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_heap_snapshot_constructor_growth_drilldown_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-selected-analysis-input-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "selection_only": True,
            "source_checkpoint_summary": {"status": "ready_for_review", "transaction_id": "heap-diff-txn-1", "executor_result_status": "executed", "node_count_delta": 1, "edge_count_delta": 1},
            "selected_analysis_input": {
                "selected_action": "review_constructor_growth",
                "candidate_count": 1,
                "candidates": [{"name": "LeakyThing", "before": 0, "after": 1, "delta": 1, "source": "summary_diff_followup_checkpoint", "raw_value_exported": False}],
            },
            "future_executor_contract": {"implemented": False, "selected_action": "review_constructor_growth", "executor_name": "review_heap_snapshot_constructor_growth_drilldown", "requires_raw_heap": False},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "constructor_drilldown_computed": False,
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-constructor-growth-drilldown",
            {
                "heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_diff_selected_analysis_input_preflight": preflight,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_constructor_growth_drilldown_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_selected_action=review_constructor_growth", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_top_candidate=LeakyThing", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_top_delta=1", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_transaction_id=heap-diff-txn-1", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_retained_size_implemented=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_path_to_root_implemented=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_constructor_drilldown_computed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-constructor-growth-drilldown.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["selected_action"], "review_constructor_growth")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["top_candidate"], "LeakyThing")
        self.assertFalse(result.artifacts[0].metadata["retained_size_analysis_implemented"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_analysis_implemented"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])


    def test_native_web_runtime_executes_heap_snapshot_constructor_growth_drilldown_analysis_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        drilldown = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1",
            "status": "ready_for_review",
            "review_only": True,
            "drilldown_only": True,
            "summary_only": True,
            "selected_action": "review_constructor_growth",
            "source_selected_analysis_input_preflight": {"status": "ready_for_review", "transaction_id": "heap-diff-txn-1"},
            "constructor_growth_summary": {
                "candidate_count": 1,
                "total_positive_delta": 3,
                "top_candidate": {"name": "LeakyThing", "before": 0, "after": 3, "delta": 3},
                "candidates": [{"name": "LeakyThing", "before": 0, "after": 3, "delta": 3, "source": "summary_diff_followup_checkpoint"}],
            },
            "future_analysis_contracts": {"constructor_drilldown_execution": {"implemented": False, "requires_explicit_review": True, "requires_raw_heap": False}},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "constructor_drilldown_computed": False},
        }

        result = runtime.apply_minimal_protection(
            "execute-heap-snapshot-constructor-growth-drilldown",
            {
                "execute_heap_snapshot_constructor_growth_drilldown": True,
                "heap_snapshot_constructor_growth_drilldown": drilldown,
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_constructor_growth_drilldown_execution": True,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_heap_snapshot_constructor_growth_drilldown_mvp"])
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_status=executed", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_top_candidate=LeakyThing", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_computed=True", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_proven=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-constructor-growth-drilldown-analysis.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertTrue(result.artifacts[0].metadata["constructor_drilldown_computed"])
        self.assertFalse(result.artifacts[0].metadata["constructor_drilldown_proven"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_heap_snapshot_automatic_followup_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        retained = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "candidate_estimates": [{"name": "LeakyThing", "retained_size_estimate": 64}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        path = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "candidate_paths": [{"candidate_name": "LeakyThing", "path_depth": 2, "root_like_node_reached": True}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": True,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        constructor = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-constructor-growth-drilldown-analysis.json",
            "constructor_drilldown_computed": True,
            "constructor_drilldown_proven": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "constructor_drilldown_rows": [{"name": "LeakyThing", "delta": 3}],
            "raw_heap_loaded": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-automatic-followup-plan",
            {
                "heap_snapshot_automatic_followup_plan": True,
                "heap_snapshot_retained_size_analysis": retained,
                "heap_snapshot_path_to_root_analysis": path,
                "heap_snapshot_constructor_growth_drilldown_analysis": constructor,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_automatic_followup_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_recommended_action_count=6", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_top_action=review_combined_heap_candidate_evidence", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_retained_size_provided=True", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_path_to_root_provided=True", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_constructor_growth_provided=True", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_path_to_root_proven=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_automatic_execution_allowed=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_automatic_followup_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-automatic-followup-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertEqual(result.artifacts[0].metadata["recommended_action_count"], 6)
        self.assertEqual(result.artifacts[0].metadata["top_recommended_action"], "review_combined_heap_candidate_evidence")
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_proven"])
        self.assertFalse(result.artifacts[0].metadata["constructor_drilldown_proven"])
        self.assertFalse(result.artifacts[0].metadata["automatic_execution_allowed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_size_proof_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        retained = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "candidate_estimates": [{"name": "LeakyThing", "retained_size_estimate": 64}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        followup = {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": "ready_for_review",
            "automatic_execution_allowed": False,
            "recommended_actions": [{"action": "plan_proof_grade_retained_size_analysis"}],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-size-proof-plan",
            {
                "heap_snapshot_retained_size_proof_plan": True,
                "heap_snapshot_retained_size_analysis": retained,
                "heap_snapshot_automatic_followup_plan": followup,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_size_proof_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_automatic_execution_allowed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_proof_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-proof-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertTrue(result.artifacts[0].metadata["proof_plan_only"])
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["automatic_execution_allowed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_heap_snapshot_path_to_root_proof_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        path = {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "candidate_paths": [{"candidate_name": "LeakyThing", "path_depth": 2, "root_like_node_reached": True}],
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": True,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        followup = {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": "ready_for_review",
            "automatic_execution_allowed": False,
            "recommended_actions": [{"action": "plan_proof_grade_path_to_root_analysis"}],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False},
        }
        retained_proof = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1",
            "status": "ready_for_review",
            "proof_plan_only": True,
            "candidate_count": 1,
            "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
            "retained_size_proven": False,
            "automatic_execution_allowed": False,
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-path-to-root-proof-plan",
            {
                "heap_snapshot_path_to_root_proof_plan": True,
                "heap_snapshot_path_to_root_analysis": path,
                "heap_snapshot_automatic_followup_plan": followup,
                "heap_snapshot_retained_size_proof_plan": retained_proof,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_path_to_root_proof_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_path_to_root_proven=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_automatic_execution_allowed=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proof_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-path-to-root-proof-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertTrue(result.artifacts[0].metadata["proof_plan_only"])
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_proven"])
        self.assertFalse(result.artifacts[0].metadata["automatic_execution_allowed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        analysis = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "executed",
            "result_artifact": "workspace/heap-snapshot-constructor-growth-drilldown-analysis.json",
            "constructor_drilldown_rows": [{"constructor_name": "LeakyThing", "growth_score": 91, "severity": "high", "node_count_delta": 7}],
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": True,
            "constructor_drilldown_proven": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-raw-heap-constructor-drilldown-proof-plan",
            {
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan": True,
                "heap_snapshot_constructor_growth_drilldown_analysis": analysis,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_constructor_reachability_graph=True", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_raw_heap_parsed=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_heap_diff_computed=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_constructor_drilldown_proven=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_automatic_execution_allowed=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_calls_mcp=False", result.verification)
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-raw-heap-constructor-drilldown-proof-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertTrue(result.artifacts[0].metadata["proof_plan_only"])
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertTrue(result.artifacts[0].metadata["requires_constructor_reachability_graph"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_parsed"])
        self.assertFalse(result.artifacts[0].metadata["heap_diff_computed"])
        self.assertFalse(result.artifacts[0].metadata["constructor_drilldown_proven"])
        self.assertFalse(result.artifacts[0].metadata["automatic_execution_allowed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_path_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        drilldown = {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1",
            "status": "ready_for_review",
            "review_only": True,
            "drilldown_only": True,
            "summary_only": True,
            "source_selected_analysis_input_preflight": {"status": "ready_for_review", "transaction_id": "heap-diff-txn-1"},
            "selected_action": "review_constructor_growth",
            "constructor_growth_summary": {
                "candidate_count": 1,
                "top_candidate": {"name": "LeakyThing", "before": 0, "after": 1, "delta": 1},
                "candidates": [{"name": "LeakyThing", "before": 0, "after": 1, "delta": 1, "source": "summary_diff_followup_checkpoint", "raw_value_exported": False}],
            },
            "future_analysis_contracts": {"retained_size_analysis": {"implemented": False}, "path_to_root_analysis": {"implemented": False}},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "heap_diff_computed": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-path-preflight",
            {
                "heap_snapshot_retained_path_preflight": True,
                "heap_snapshot_constructor_growth_drilldown": drilldown,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_path_preflight_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_top_candidate=LeakyThing", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_retained_path_preflight_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_path_executor_inputs")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-path-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["top_candidate"], "LeakyThing")
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_computed"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_size_input_review_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-path-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "handoff_only": True,
            "requested_analysis": "retained-size-and-path-to-root",
            "source_constructor_growth_drilldown": {"status": "ready_for_review", "transaction_id": "heap-diff-txn-1", "selected_action": "review_constructor_growth"},
            "candidate_count": 1,
            "candidate_inputs": [{"name": "LeakyThing", "before": 0, "after": 1, "delta": 1, "source": "constructor_growth_drilldown"}],
            "raw_heap_requirements": {"requires_raw_heap": True, "requires_raw_heap_ingestion_preflight": True, "raw_heap_available_in_this_preflight": False, "raw_heap_loaded_now": False},
            "future_executor_contracts": {"retained_size_analysis": {"executor_name": "execute_heap_snapshot_retained_size_analysis", "implemented": False, "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"}},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-size-input-review",
            {
                "heap_snapshot_retained_size_input_review": True,
                "heap_snapshot_retained_path_preflight": preflight,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_size_input_review_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_top_candidate=LeakyThing", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_requires_raw_heap=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_input_review_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_size_approval_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-input-review.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["top_candidate"], "LeakyThing")
        self.assertTrue(result.artifacts[0].metadata["requires_raw_heap"])
        self.assertFalse(result.artifacts[0].metadata["executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_computed"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_size_approval_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        input_review = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-input-review.v1",
            "status": "ready_for_review",
            "review_only": True,
            "input_review_only": True,
            "approval_gate_only": True,
            "candidate_count": 1,
            "candidate_inputs": [{"name": "LeakyThing", "delta": 1, "source": "retained_path_preflight"}],
            "source_retained_path_preflight": {"transaction_id": "heap-diff-txn-1", "requested_analysis": "retained-size-and-path-to-root"},
            "raw_heap_requirements": {"requires_raw_heap": True, "requires_raw_heap_ingestion_preflight": True},
            "executor_input_contract": {"executor_name": "execute_heap_snapshot_retained_size_analysis", "implemented": False, "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"},
            "approval_gate": {"approval_required": True, "approval_recorded": False, "transaction_started": False, "journal_written": False, "ready_to_execute_now": False},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "executor_invoked": False,
            "side_effect_policy": {"raw_heap_loaded": False, "raw_heap_parsed": False, "heap_diff_computed": False, "browser_started": False, "cdp_command_sent": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-size-approval-plan",
            {
                "heap_snapshot_retained_size_approval_plan": True,
                "heap_snapshot_retained_size_input_review": input_review,
                "reviewer": "alice",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_size_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_candidate_count=1", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_top_candidate=LeakyThing", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_transaction_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_journal_written=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_browser_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_approval_plan_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "record_heap_snapshot_retained_size_approval")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["top_candidate"], "LeakyThing")
        self.assertFalse(result.artifacts[0].metadata["executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["approval_recorded"])
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["raw_heap_loaded"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_size_transaction_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        approval_plan = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1",
            "status": "ready_for_review",
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "retained_size_only": True,
            "candidate_count": 1,
            "candidate_inputs": [{"name": "LeakyThing", "delta": 1}],
            "candidate_digest": "retained-size-candidate-digest-test",
            "approval_plan": {"approval_plan_id": "retained-size-approval-plan-test", "approval_recorded": False, "approval_record_artifact": "workspace/heap-snapshot-retained-size-approval-record.json", "approval_record_writer": "record_heap_snapshot_retained_size_approval"},
            "transaction_plan": {"transaction_plan_id": "retained-size-approval-plan-test", "transaction_started": False, "journal_written": False, "transaction_journal_artifact": "workspace/heap-snapshot-retained-size-executor-journal.json", "bounded_gate_artifact": "workspace/heap-snapshot-retained-size-bounded-gate.json", "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"},
            "executor_input_contract": {"implemented": False, "ready_to_execute_now": False},
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "side_effect_policy": {"approval_recorded": False, "transaction_started": False, "journal_written": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "retained_size_proven": False, "path_to_root_computed": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        approval_record = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1",
            "status": "written",
            "approval_recorded": True,
            "approved_for_execution": True,
            "approval_plan_id": "retained-size-approval-plan-test",
            "transaction_plan_id": "retained-size-approval-plan-test",
            "candidate_digest": "retained-size-candidate-digest-test",
            "executor_input_gates": {"transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "retained_size_proven": False, "path_to_root_computed": False},
            "side_effect_policy": {"transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "retained_size_proven": False, "path_to_root_computed": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-size-transaction-preflight",
            {
                "heap_snapshot_retained_size_transaction_preflight": True,
                "heap_snapshot_retained_size_approval_plan": approval_plan,
                "heap_snapshot_retained_size_approval_record": approval_record,
                "expected_transaction_plan_id": "retained-size-approval-plan-test",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_approval_recorded=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_approved_for_execution=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_transaction_plan_id=retained-size-approval-plan-test", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_ready_to_write_journal=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_transaction_started=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_journal_written=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_executor_invoked=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_size_transaction_journal_writer")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-transaction-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_journal_review"])
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])

    def test_native_web_runtime_reviews_heap_snapshot_retained_size_bounded_gate_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        journal = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "retained-size-journal-test",
            "transaction_preflight_id": "retained-size-preflight-test",
            "transaction_plan_id": "retained-size-approval-plan-test",
            "approval_plan_id": "retained-size-approval-plan-test",
            "candidate_digest": "retained-size-candidate-digest-test",
            "source_transaction_preflight_summary": {"schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1", "status": "ready_for_review", "retained_size_only": True, "ready_to_write_journal": True, "ready_to_execute_now": False},
            "candidate_summary": {"candidate_digest": "retained-size-candidate-digest-test", "candidate_count": 1, "top_candidate": "LeakyThing"},
            "journal_summary": {"transaction_started": True, "journal_written": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "retained_size_proven": False, "path_to_root_computed": False, "requires_bounded_executor_gate_followup": True},
            "executor_input_gates": {"ready_to_execute_now": False, "approval_record_verified": True, "transaction_started": True, "journal_written": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "raw_strings_exported": False, "heap_diff_computed": False, "retained_size_proven": False, "path_to_root_computed": False, "complete_heap_traversal_claimed": False, "retained_size_executor_implemented": False, "requires_bounded_executor_gate": True, "requires_explicit_executor_review": True},
            "blockers": [],
            "side_effect_policy": {"writes_transaction_journal": True, "bounded_executor_gate_written": False, "executor_invoked": False, "future_executor_invoked": False, "browser_started": False, "provider_factory_invoked": False, "provider_availability_checked": False, "cdp_command_sent": False, "heap_profiler_enabled": False, "heap_snapshot_collected": False, "heap_snapshot_diff_computed": False, "heap_diff_computed": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "raw_strings_exported": False, "complete_heap_traversal": False, "retained_size_proven": False, "path_to_root_computed": False, "runtime_evaluated": False, "javascript_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "heap-snapshot-retained-size-bounded-gate",
            {
                "heap_snapshot_retained_size_bounded_gate": True,
                "heap_snapshot_retained_size_transaction_journal": journal,
                "expected_transaction_plan_id": "retained-size-approval-plan-test",
                "expected_candidate_digest": "retained-size-candidate-digest-test",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("heap_snapshot_retained_size_bounded_gate_status=ready_for_review", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_transaction_plan_id=retained-size-approval-plan-test", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_candidate_digest=retained-size-candidate-digest-test", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_journal_written=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_ready_for_review=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_ready_to_execute_now=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_future_executor_implemented=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_executor_invoked=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_raw_heap_loaded=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_bounded_gate_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_size_executor_mvp")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-bounded-gate.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["bounded_executor_gate_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])

    def test_native_web_runtime_executes_heap_snapshot_retained_size_analysis_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        gate = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1",
            "status": "ready_for_review",
            "retained_size_only": True,
            "journal_id": "retained-size-journal-test",
            "transaction_plan_id": "retained-size-approval-plan-test",
            "approval_plan_id": "retained-size-approval-plan-test",
            "candidate_digest": "retained-size-candidate-digest-test",
            "bounded_executor_gate_ready_for_review": True,
            "ready_for_executor_review": True,
            "ready_to_execute_now": False,
            "future_executor_contract": {"executor_name": "execute_heap_snapshot_retained_size_analysis", "implemented": False, "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"},
            "side_effect_policy": {"executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "raw_strings_exported": False, "retained_size_proven": False, "path_to_root_computed": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "execute-heap-snapshot-retained-size-analysis",
            {
                "execute_heap_snapshot_retained_size_analysis": True,
                "heap_snapshot_retained_size_bounded_gate": gate,
                "heap_snapshot": _v8_heap_snapshot_for_native_test(extra_object=True),
                "candidate_name": "ExtraObject",
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_retained_size_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_heap_snapshot_retained_size_analysis_mvp"])
        self.assertIn("heap_snapshot_retained_size_analysis_status=executed", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_journal_id=retained-size-journal-test", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_raw_heap_loaded=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_raw_heap_parsed=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_raw_strings_exported=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_retained_size_estimated=True", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_path_to_root_computed=False", result.verification)
        self.assertIn("heap_snapshot_retained_size_analysis_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_retained_size_analysis_before_path_to_root_or_second_pass")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-retained-size-analysis.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertTrue(result.artifacts[0].metadata["retained_size_estimated"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_computed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])


    def test_native_web_runtime_executes_heap_snapshot_path_to_root_analysis_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        retained_analysis = {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "candidate_estimates": [{"name": "<redacted>", "retained_size_estimate": 48}],
            "requested_candidate_names": ["TokenSecret"],
        }

        result = runtime.apply_minimal_protection(
            "execute-heap-snapshot-path-to-root-analysis",
            {
                "execute_heap_snapshot_path_to_root_analysis": True,
                "heap_snapshot_retained_size_analysis": retained_analysis,
                "heap_snapshot": _v8_heap_snapshot_path_to_root_for_native_test(),
                "candidate_name": "TokenSecret",
                "mode": "apply",
                "review_approved": True,
                "approve_heap_snapshot_path_to_root_execution": True,
                "reviewer": "alice",
                "max_raw_heap_bytes": 20000,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_heap_snapshot_path_to_root_analysis_mvp"])
        self.assertIn("heap_snapshot_path_to_root_analysis_status=executed", result.verification)
        self.assertIn("heap_snapshot_path_to_root_raw_heap_loaded=True", result.verification)
        self.assertIn("heap_snapshot_path_to_root_raw_heap_parsed=True", result.verification)
        self.assertIn("heap_snapshot_path_to_root_raw_heap_exported=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_raw_strings_exported=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_estimated=True", result.verification)
        self.assertIn("heap_snapshot_path_to_root_proven=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_retained_size_proven=False", result.verification)
        self.assertIn("heap_snapshot_path_to_root_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/heap-snapshot-path-to-root-analysis.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertTrue(result.artifacts[0].metadata["path_to_root_estimated"])
        self.assertFalse(result.artifacts[0].metadata["path_to_root_proven"])
        self.assertFalse(result.artifacts[0].metadata["retained_size_proven"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_object_graph_diff_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "object-graph-diff",
            {
                "before_snapshot": {"store": {"authToken": "before", "count": 1}},
                "after_snapshot": {"store": {"authToken": "after", "count": 2}},
                "include_values": True,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_object_graph_diff"])
        self.assertIn("object_graph_diff_status=ready_for_review", result.verification)
        self.assertIn("object_graph_diff_changed=True", result.verification)
        self.assertIn("object_graph_diff_change_count=2", result.verification)
        self.assertIn("object_graph_diff_review_only=True", result.verification)
        self.assertIn("object_graph_diff_browser_started=False", result.verification)
        self.assertIn("object_graph_diff_cdp_command_sent=False", result.verification)
        self.assertIn("object_graph_diff_runtime_evaluated=False", result.verification)
        self.assertIn("object_graph_diff_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_object_graph_diff_before_hook_or_replay")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/object-graph-diff.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["changed"])
        self.assertEqual(result.artifacts[0].metadata["change_count"], 2)
        self.assertEqual(result.artifacts[0].metadata["risk"], "high")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_collects_runtime_object_graph_diff_explicitly(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "runtime-object-graph-diff",
            {
                "runtime_object_graph_diff": True,
                "object_root": "window.__appState",
                "trigger_expression": "mutateNativeObjectRoot()",
            },
        )

        self.assertEqual(provider.started, 1)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["collect_runtime_object_graph_diff"])
        self.assertIn("runtime_object_graph_diff_status=ready_for_review", result.verification)
        self.assertIn("runtime_object_graph_diff_root_path=window.__appState", result.verification)
        self.assertIn("runtime_object_graph_diff_changed=True", result.verification)
        self.assertIn("runtime_object_graph_diff_change_count=4", result.verification)
        self.assertIn("runtime_object_graph_diff_explicit_collection=True", result.verification)
        self.assertIn("runtime_object_graph_diff_snapshot_source=runtime_collected_object_root_snapshots", result.verification)
        self.assertIn("runtime_object_graph_diff_default_recon=False", result.verification)
        self.assertIn("runtime_object_graph_diff_cdp_command_sent=False", result.verification)
        self.assertIn("runtime_object_graph_diff_runtime_evaluated=True", result.verification)
        self.assertIn("runtime_object_graph_diff_trigger_executed=True", result.verification)
        self.assertIn("runtime_object_graph_diff_getter_invocation=False", result.verification)
        self.assertIn("runtime_object_graph_diff_prototype_traversal=False", result.verification)
        self.assertIn("runtime_object_graph_diff_full_heap_snapshot=False", result.verification)
        self.assertIn("runtime_object_graph_diff_complete_heap_traversal=False", result.verification)
        self.assertIn("runtime_object_graph_diff_calls_mcp=False", result.verification)
        self.assertIn("runtime_object_graph_diff_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_runtime_object_graph_diff_before_hook_or_replay")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/runtime-object-graph-diff.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["root_path"], "window.__appState")
        self.assertTrue(result.artifacts[0].metadata["changed"])
        self.assertEqual(result.artifacts[0].metadata["change_count"], 4)
        self.assertEqual(result.artifacts[0].metadata["risk"], "high")
        self.assertTrue(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["full_heap_snapshot"])
        self.assertFalse(result.artifacts[0].metadata["complete_heap_traversal"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

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

    def test_native_web_runtime_reviews_bundler_symbol_scope_without_runtime_side_effects(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "bundler-symbol-scope",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "script_url": "https://example.test/assets/app.js",
                "script_source": "var __webpack_require__ = {};",
                "symbol_name": "buildSign",
                "original_source": "webpack://demo/src/sign.ts",
                "original_line": 0,
                "original_column": 0,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_bundler_symbol_scope"])
        self.assertIn("bundler_symbol_scope_status=ready_for_review", result.verification)
        self.assertIn("bundler_symbol_scope_bundler=webpack", result.verification)
        self.assertIn("bundler_symbol_scope_candidate_count=1", result.verification)
        self.assertIn("bundler_symbol_scope_fetch_source_map=False", result.verification)
        self.assertIn("bundler_symbol_scope_logpoint_installed=False", result.verification)
        self.assertIn("bundler_symbol_scope_cdp_command_sent=False", result.verification)
        self.assertIn("bundler_symbol_scope_calls_mcp=False", result.verification)
        self.assertIn("bundler_symbol_scope_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_symbol_scope_before_source_logpoint_or_hook")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/bundler-symbol-scope.json")
        self.assertEqual(result.artifacts[0].metadata["bundler_kind"], "webpack")
        self.assertEqual(result.artifacts[0].metadata["symbol_name"], "buildSign")
        self.assertEqual(result.artifacts[0].metadata["scope_candidate_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertFalse(result.artifacts[0].metadata["fetch_source_map"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])

    def test_native_web_runtime_reviews_source_map_lookup_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-lookup",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "generated_line": 0,
                "generated_column": 0,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_lookup"])
        self.assertIn("source_map_lookup_status=ready_for_review", result.verification)
        self.assertIn("source_map_lookup_direction=generated_to_original", result.verification)
        self.assertIn("source_map_lookup_mapping_found=True", result.verification)
        self.assertIn("source_map_lookup_strategy=source_map_generated_exact", result.verification)
        self.assertIn("source_map_lookup_review_only=True", result.verification)
        self.assertIn("source_map_lookup_fetch_source_map=False", result.verification)
        self.assertIn("source_map_lookup_browser_started=False", result.verification)
        self.assertIn("source_map_lookup_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_lookup_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_lookup_calls_mcp=False", result.verification)
        self.assertIn("source_map_lookup_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_lookup_before_debugger_or_hook_use")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-lookup.json")
        self.assertEqual(result.artifacts[0].metadata["lookup_direction"], "generated_to_original")
        self.assertTrue(result.artifacts[0].metadata["mapping_found"])
        self.assertEqual(result.artifacts[0].metadata["strategy"], "source_map_generated_exact")
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_native_web_runtime_reviews_source_map_source_content_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-source-content",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "sourcesContent": ["export function buildSign(){ return 'x'; }\n"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "original_source": "webpack://demo/src/sign.ts",
                "include_source_preview": True,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_source_content"])
        self.assertIn("source_map_source_content_status=ready_for_review", result.verification)
        self.assertIn("source_map_source_content_available=True", result.verification)
        self.assertIn("source_map_source_content_original_source=webpack://demo/src/sign.ts", result.verification)
        self.assertIn("source_map_source_content_review_only=True", result.verification)
        self.assertIn("source_map_source_content_raw_exported=False", result.verification)
        self.assertIn("source_map_source_content_preview_exported=False", result.verification)
        self.assertIn("source_map_source_content_fetch_source_map=False", result.verification)
        self.assertIn("source_map_source_content_browser_started=False", result.verification)
        self.assertIn("source_map_source_content_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_source_content_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_source_content_calls_mcp=False", result.verification)
        self.assertIn("source_map_source_content_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_content_availability_before_debugger_or_rebuild")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-source-content.json")
        self.assertTrue(result.artifacts[0].metadata["source_content_available"])
        self.assertEqual(result.artifacts[0].metadata["original_source"], "webpack://demo/src/sign.ts")
        self.assertTrue(result.artifacts[0].metadata["sha256"])
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
        self.assertFalse(result.artifacts[0].metadata["preview_exported"])
        self.assertFalse(result.artifacts[0].metadata["fetch_source_map"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

    def test_source_dispatch_review_evidence_helper_routes_lookup_shape_without_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = dispatch_source_map_review_evidence(
            runtime,
            "source-map-lookup",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "generated_line": 0,
                "generated_column": 0,
            },
        )

        self.assertIsNotNone(result)
        self.assertIsNone(runtime._session)
        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_lookup"])
        self.assertEqual(result.next_action, "review_source_map_lookup_before_debugger_or_hook_use")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-lookup.json")
        self.assertEqual(result.artifacts[0].kind.value, "json")
        self.assertEqual(
            result.artifacts[0].description,
            "Native Web runtime review-only Source Map lookup descriptor.",
        )
        self.assertEqual(
            result.artifacts[0].metadata,
            {
                "status": "ready_for_review",
                "lookup_direction": "generated_to_original",
                "mapping_found": True,
                "strategy": "source_map_generated_exact",
                "review_only": True,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
            },
        )
        self.assertIn("source_map_lookup_calls_mcp=False", result.verification)
        self.assertIn("source_map_lookup_mobile_runtime_used=False", result.verification)

    def test_source_dispatch_review_evidence_helper_routes_source_content_shape_without_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = dispatch_source_map_review_evidence(
            runtime,
            "source-map-source-content",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "sourcesContent": ["export function buildSign(){ return 'x'; }\n"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "original_source": "webpack://demo/src/sign.ts",
                "include_source_preview": True,
            },
        )

        self.assertIsNotNone(result)
        self.assertIsNone(runtime._session)
        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_source_content"])
        self.assertEqual(result.next_action, "review_source_content_availability_before_debugger_or_rebuild")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-source-content.json")
        self.assertEqual(result.artifacts[0].kind.value, "json")
        self.assertEqual(
            result.artifacts[0].description,
            "Native Web runtime review-only Source Map sourcesContent availability descriptor.",
        )
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["source_content_available"])
        self.assertEqual(result.artifacts[0].metadata["original_source"], "webpack://demo/src/sign.ts")
        self.assertTrue(result.artifacts[0].metadata["sha256"])
        self.assertTrue(result.artifacts[0].metadata["review_only"])
        self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
        self.assertFalse(result.artifacts[0].metadata["preview_exported"])
        self.assertFalse(result.artifacts[0].metadata["fetch_source_map"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertIn("source_map_source_content_calls_mcp=False", result.verification)
        self.assertIn("source_map_source_content_mobile_runtime_used=False", result.verification)

    def test_source_dispatch_review_evidence_helper_routes_bundler_symbol_scope_shape_without_session(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = dispatch_source_map_review_evidence(
            runtime,
            "bundler-symbol-scope",
            {
                "source_map": {
                    "version": 3,
                    "sourceRoot": "webpack://demo",
                    "sources": ["./src/sign.ts"],
                    "names": ["buildSign"],
                    "mappings": "AAAAA",
                },
                "script_url": "https://example.test/assets/app.js",
                "script_source": "var __webpack_require__ = {};",
                "symbol_name": "buildSign",
                "original_source": "webpack://demo/src/sign.ts",
                "original_line": 0,
                "original_column": 0,
            },
        )

        self.assertIsNotNone(result)
        self.assertIsNone(runtime._session)
        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_bundler_symbol_scope"])
        self.assertEqual(result.next_action, "review_symbol_scope_before_source_logpoint_or_hook")
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/bundler-symbol-scope.json")
        self.assertEqual(result.artifacts[0].kind.value, "json")
        self.assertEqual(
            result.artifacts[0].description,
            "Native Web runtime review-only bundler symbol scope descriptor.",
        )
        self.assertEqual(
            result.artifacts[0].metadata,
            {
                "status": "ready_for_review",
                "bundler_kind": "webpack",
                "confidence": "high",
                "symbol_name": "buildSign",
                "scope_candidate_count": 1,
                "review_only": True,
                "fetch_source_map": False,
                "logpoint_installed": False,
            },
        )
        self.assertIn("bundler_symbol_scope_cdp_command_sent=False", result.verification)
        self.assertIn("bundler_symbol_scope_calls_mcp=False", result.verification)
        self.assertIn("bundler_symbol_scope_mobile_runtime_used=False", result.verification)

    def test_native_web_runtime_reviews_source_map_consumer_action_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-consumer-action-plan",
            {
                "source_map_readiness": {
                    "status": "ready_for_review",
                    "readiness": {
                        "debugger_location_ready": True,
                        "source_content_metadata_ready": True,
                        "source_logpoint_planning_ready": True,
                        "rebuild_source_metadata_ready": True,
                        "bundler_scope_review_ready": True,
                    },
                    "blockers": [],
                },
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "mapping_found": True,
                    "location": {"strategy": "source_map_generated_exact", "source": "src/sign.ts"},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "hook_readiness": {"source_logpoint_reviewable": True},
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_consumer_action_plan"])
        self.assertIn("source_map_consumer_action_plan_status=ready_for_review", result.verification)
        self.assertIn("source_map_consumer_action_plan_count=4", result.verification)
        self.assertIn("source_map_consumer_action_plan_review_only=True", result.verification)
        self.assertIn("source_map_consumer_action_plan_plan_only=True", result.verification)
        self.assertIn("source_map_consumer_action_plan_fetch_source_map=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_browser_started=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_logpoint_installed=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_hook_installed=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_rebuild_executed=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_calls_mcp=False", result.verification)
        self.assertIn("source_map_consumer_action_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-consumer-action-plan.json")
        self.assertEqual(result.artifacts[0].metadata["action_plan_count"], 4)
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_consumer_materialization_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        action_plan = {
            "schema_version": "reverse-deepagent.source-map-consumer-action-plan.v1",
            "status": "ready_for_review",
            "action_plan_count": 2,
            "action_plans": [
                {
                    "action_id": "review-debugger-location-use",
                    "consumer": "debugger",
                    "status": "ready_for_review",
                    "review_required": True,
                    "plan_only": True,
                    "execute_automatically": False,
                    "required_inputs": ["source-map-readiness", "source-map-lookup"],
                    "evidence": {"mapping_strategy": "source_map_generated_exact", "source": "src/sign.ts", "line_number": 0, "column_number": 4},
                },
                {
                    "action_id": "review-rebuild-source-metadata-use",
                    "consumer": "rebuild",
                    "status": "ready_for_review",
                    "review_required": True,
                    "plan_only": True,
                    "execute_automatically": False,
                    "required_inputs": ["source-map-readiness", "source-map-source-content"],
                    "evidence": {"sha256": "abc123", "source_content_available": True},
                },
            ],
            "side_effect_policy": {"raw_source_content_exported": False, "preview_exported": False},
        }
        result = runtime.apply_minimal_protection(
            "source-map-consumer-materialization",
            {"source_map_consumer_action_plan": action_plan},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_consumer_materialization"])
        self.assertIn("source_map_consumer_materialization_status=ready_for_review", result.verification)
        self.assertIn("source_map_consumer_materialization_count=2", result.verification)
        self.assertIn(
            "source_map_consumer_materialization_typed_payload_schema_version=reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            result.verification,
        )
        self.assertIn("source_map_consumer_materialization_typed_payload_count=2", result.verification)
        self.assertIn("source_map_consumer_materialization_typed_payload_consumers=debugger,rebuild", result.verification)
        self.assertIn("source_map_consumer_materialization_review_only=True", result.verification)
        self.assertIn("source_map_consumer_materialization_plan_only=True", result.verification)
        self.assertIn("source_map_consumer_materialization_fetch_source_map=False", result.verification)
        self.assertIn("source_map_consumer_materialization_browser_started=False", result.verification)
        self.assertIn("source_map_consumer_materialization_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_consumer_materialization_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_consumer_materialization_logpoint_installed=False", result.verification)
        self.assertIn("source_map_consumer_materialization_hook_installed=False", result.verification)
        self.assertIn("source_map_consumer_materialization_rebuild_executed=False", result.verification)
        self.assertIn("source_map_consumer_materialization_calls_mcp=False", result.verification)
        self.assertIn("source_map_consumer_materialization_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-consumer-materialization.json")
        self.assertEqual(result.artifacts[0].metadata["materialization_count"], 2)
        self.assertEqual(
            result.artifacts[0].metadata["typed_payload_schema_version"],
            "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
        )
        self.assertEqual(result.artifacts[0].metadata["typed_review_payload_count"], 2)
        self.assertEqual(result.artifacts[0].metadata["typed_review_payload_consumers"], ["debugger", "rebuild"])
        self.assertTrue(result.artifacts[0].metadata["plan_only"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_typed_payload_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        materialization = {
            "schema_version": "reverse-deepagent.source-map-consumer-materialization.v1",
            "status": "ready_for_review",
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "typed_review_payloads": [
                {
                    "schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
                    "action_id": "review-debugger-location-use",
                    "consumer": "debugger",
                    "payload_kind": "debugger-location-review",
                    "status": "ready_for_review",
                    "review_required": True,
                    "execute_automatically": False,
                    "executor_input": {
                        "location": {"url": "https://example.test/app.js", "line_number": 10, "column_number": 4},
                        "cdp_command": None,
                        "requires_review_before_debugger_use": True,
                    },
                    "safety": {"cdp_command_sent": False, "debugger_execution_performed": False},
                },
                {
                    "schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
                    "action_id": "review-rebuild-source-metadata-use",
                    "consumer": "rebuild",
                    "payload_kind": "rebuild-source-metadata-review",
                    "status": "ready_for_review",
                    "review_required": True,
                    "execute_automatically": False,
                    "executor_input": {
                        "source_content_digest": "abc123",
                        "raw_source_content": None,
                        "raw_content_exported": False,
                        "preview_exported": False,
                    },
                    "safety": {"raw_source_content_exported": False, "preview_exported": False, "rebuild_executed": False},
                },
            ],
            "side_effect_policy": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-typed-payload-preflight",
            {"source_map_consumer_materialization": materialization},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_typed_payload_preflight"])
        self.assertIn("source_map_typed_payload_preflight_status=ready_for_review", result.verification)
        self.assertIn("source_map_typed_payload_preflight_count=2", result.verification)
        self.assertIn("source_map_typed_payload_preflight_consumers=debugger,rebuild", result.verification)
        self.assertIn(
            "source_map_typed_payload_preflight_schema_version=reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            result.verification,
        )
        self.assertIn("source_map_typed_payload_preflight_ready_for_followthrough_review=True", result.verification)
        self.assertIn("source_map_typed_payload_preflight_review_only=True", result.verification)
        self.assertIn("source_map_typed_payload_preflight_plan_only=True", result.verification)
        self.assertIn("source_map_typed_payload_preflight_preflight_only=True", result.verification)
        self.assertIn("source_map_typed_payload_preflight_raw_exported=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_preview_exported=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_fetch_source_map=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_browser_started=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_debugger_execution_performed=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_logpoint_installed=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_hook_installed=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_rebuild_executed=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_calls_mcp=False", result.verification)
        self.assertIn("source_map_typed_payload_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-typed-payload-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["preflight_payload_count"], 2)
        self.assertEqual(
            result.artifacts[0].metadata["typed_payload_schema_version"],
            "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
        )
        self.assertEqual(result.artifacts[0].metadata["consumers"], ["debugger", "rebuild"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_followthrough_review"])
        self.assertTrue(result.artifacts[0].metadata["preflight_only"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_followthrough_review_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.source-map-typed-payload-preflight.v1",
            "status": "ready_for_review",
            "ready_for_followthrough_review": True,
            "typed_payload_schema_version": "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            "preflight_payloads": [
                {
                    "action_id": "review-debugger-location-use",
                    "consumer": "debugger",
                    "payload_kind": "debugger-location-review",
                    "status": "ready_for_review",
                    "review_required": True,
                    "execute_automatically": False,
                    "ready_for_followthrough_review": True,
                    "followthrough_review_surface": "review_debugger_location_executor_input",
                    "executor_input": {
                        "location": {"url": "https://example.test/app.js", "line_number": 10, "column_number": 4},
                        "cdp_command": None,
                        "requires_review_before_debugger_use": True,
                    },
                    "executor_invoked": False,
                    "side_effect_policy": {"cdp_command_sent": False, "debugger_execution_performed": False},
                },
                {
                    "action_id": "review-rebuild-source-metadata-use",
                    "consumer": "rebuild",
                    "payload_kind": "rebuild-source-metadata-review",
                    "status": "ready_for_review",
                    "review_required": True,
                    "execute_automatically": False,
                    "ready_for_followthrough_review": True,
                    "followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
                    "executor_input": {
                        "source_content_digest": "abc123",
                        "raw_source_content": None,
                        "raw_content_exported": False,
                        "preview_exported": False,
                    },
                    "executor_invoked": False,
                    "side_effect_policy": {"raw_source_content_exported": False, "preview_exported": False, "rebuild_executed": False},
                },
            ],
            "followthrough_executor_invoked": False,
            "side_effect_policy": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-followthrough-review",
            {"source_map_typed_payload_preflight": preflight},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_review"])
        self.assertIn("source_map_followthrough_review_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_review_count=2", result.verification)
        self.assertIn("source_map_followthrough_review_ready_count=2", result.verification)
        self.assertIn("source_map_followthrough_review_consumers=debugger,rebuild", result.verification)
        self.assertIn(
            "source_map_followthrough_review_schema_version=reverse-deepagent.source-map-consumer-typed-review-payload.v1",
            result.verification,
        )
        self.assertIn("source_map_followthrough_review_ready_for_explicit_review=True", result.verification)
        self.assertIn("source_map_followthrough_review_review_only=True", result.verification)
        self.assertIn("source_map_followthrough_review_plan_only=True", result.verification)
        self.assertIn("source_map_followthrough_review_handoff_only=True", result.verification)
        self.assertIn("source_map_followthrough_review_raw_exported=False", result.verification)
        self.assertIn("source_map_followthrough_review_preview_exported=False", result.verification)
        self.assertIn("source_map_followthrough_review_fetch_source_map=False", result.verification)
        self.assertIn("source_map_followthrough_review_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_review_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_review_debugger_execution_performed=False", result.verification)
        self.assertIn("source_map_followthrough_review_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_followthrough_review_logpoint_installed=False", result.verification)
        self.assertIn("source_map_followthrough_review_hook_installed=False", result.verification)
        self.assertIn("source_map_followthrough_review_rebuild_executed=False", result.verification)
        self.assertIn("source_map_followthrough_review_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_review_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "choose_explicit_source_map_followthrough_review_surface")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-review.json")
        self.assertEqual(result.artifacts[0].metadata["followthrough_review_count"], 2)
        self.assertEqual(
            result.artifacts[0].metadata["typed_payload_schema_version"],
            "reverse-deepagent.source-map-consumer-typed-review-payload.v1",
        )
        self.assertEqual(result.artifacts[0].metadata["consumers"], ["debugger", "rebuild"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_explicit_review"])
        self.assertTrue(result.artifacts[0].metadata["handoff_only"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_selects_source_map_followthrough_surface_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        followthrough_review = {
            "schema_version": "reverse-deepagent.source-map-followthrough-review.v1",
            "status": "ready_for_review",
            "ready_for_explicit_review": True,
            "followthrough_reviews": [
                {
                    "action_id": "review-debugger-location-use",
                    "consumer": "debugger",
                    "payload_kind": "debugger-location-review",
                    "status": "ready_for_review",
                    "explicit_review_required": True,
                    "execute_automatically": False,
                    "followthrough_review_surface": "review_debugger_location_executor_input",
                    "review_prompt": "Review debugger location executor input before any CDP Debugger command.",
                    "next_action": "review_debugger_location_before_cdp_command",
                    "executor_input": {"location": {"url": "https://example.test/app.js", "line_number": 10, "column_number": 4}},
                    "executor_invoked": False,
                    "side_effect_policy": {"cdp_command_sent": False, "debugger_execution_performed": False},
                },
                {
                    "action_id": "review-rebuild-source-metadata-use",
                    "consumer": "rebuild",
                    "payload_kind": "rebuild-source-metadata-review",
                    "status": "ready_for_review",
                    "explicit_review_required": True,
                    "execute_automatically": False,
                    "followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
                    "review_prompt": "Review digest-only rebuild metadata before generation.",
                    "next_action": "review_rebuild_source_metadata_before_generation",
                    "executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
                    "executor_invoked": False,
                    "side_effect_policy": {"raw_source_content_exported": False, "preview_exported": False, "rebuild_executed": False},
                },
            ],
            "followthrough_executor_invoked": False,
            "side_effect_policy": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-followthrough-surface-selection",
            {
                "source_map_followthrough_review": followthrough_review,
                "source_map_followthrough_surface_consumers": ["rebuild"],
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["select_source_map_followthrough_surface"])
        self.assertIn("source_map_followthrough_surface_selection_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_candidate_count=2", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_selected_action_id=review-rebuild-source-metadata-use", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_selected_consumer=rebuild", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_selected_surface=review_rebuild_source_metadata_executor_input", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_ready_for_surface_review=True", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_review_only=True", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_plan_only=True", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_selection_only=True", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_handoff_only=True", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_logpoint_installed=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_hook_installed=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_rebuild_executed=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_surface_selection_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_rebuild_source_metadata_before_generation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-surface-selection.json")
        self.assertEqual(result.artifacts[0].metadata["candidate_review_count"], 2)
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["selected_payload_kind"], "rebuild-source-metadata-review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_surface_review"])
        self.assertTrue(result.artifacts[0].metadata["selection_only"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_selected_executor_input_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        selection = {
            "schema_version": "reverse-deepagent.source-map-followthrough-surface-selection.v1",
            "status": "ready_for_review",
            "ready_for_surface_review": True,
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
            "selected_review": {
                "action_id": "review-rebuild-source-metadata-use",
                "consumer": "rebuild",
                "payload_kind": "rebuild-source-metadata-review",
                "status": "ready_for_review",
                "review_required": True,
                "explicit_review_required": True,
                "execute_automatically": False,
                "followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
                "review_prompt": "Review digest-only rebuild metadata before generation.",
                "next_action": "review_rebuild_source_metadata_before_generation",
                "executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
                "executor_invoked": False,
                "side_effect_policy": {"raw_source_content_exported": False, "preview_exported": False, "rebuild_executed": False},
            },
            "selected_executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
            "surface_executor_invoked": False,
            "side_effect_policy": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-selected-executor-input-review",
            {"source_map_followthrough_surface_selection": selection, "expected_consumer": "rebuild"},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_input"])
        self.assertIn("source_map_selected_executor_input_review_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_input_review_selected_action_id=review-rebuild-source-metadata-use", result.verification)
        self.assertIn("source_map_selected_executor_input_review_selected_consumer=rebuild", result.verification)
        self.assertIn("source_map_selected_executor_input_review_selected_surface=review_rebuild_source_metadata_executor_input", result.verification)
        self.assertIn("source_map_selected_executor_input_review_package_ready=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_ready_for_executor_review=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_gate=explicit_rebuild_source_metadata_review", result.verification)
        self.assertIn("source_map_selected_executor_input_review_review_only=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_plan_only=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_preflight_only=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_handoff_only=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_browser_started=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_logpoint_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_hook_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_rebuild_executed=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_rebuild_source_metadata_before_generation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-input-review.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["review_gate"], "explicit_rebuild_source_metadata_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_executor_review"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_selected_executor_approval_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        side_effect_policy = {
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
        input_review = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-input-review.v1",
            "status": "ready_for_review",
            "ready_for_executor_review": True,
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
            "executor_review_package": {
                "package_version": "reverse-deepagent.source-map-selected-executor-input-review.package.v1",
                "action_id": "review-rebuild-source-metadata-use",
                "consumer": "rebuild",
                "followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
                "executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
                "review_gate": {"gate": "explicit_rebuild_source_metadata_review", "required_approval_flag": "review_approved"},
                "requires_explicit_review": True,
                "ready_for_downstream_review": True,
                "execute_automatically": False,
                "executor_invoked": False,
                "side_effect_policy": side_effect_policy,
            },
            "surface_executor_invoked": False,
            "side_effect_policy": side_effect_policy,
        }
        result = runtime.apply_minimal_protection(
            "source-map-selected-executor-approval-plan",
            {"source_map_selected_executor_input_review": input_review, "expected_consumer": "rebuild"},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_approval_plan"])
        self.assertIn("source_map_selected_executor_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_selected_action_id=review-rebuild-source-metadata-use", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_selected_consumer=rebuild", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_selected_gate=explicit_rebuild_source_metadata_review", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_approval_ready=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_apply_ready_for_review=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_ready_to_apply_now=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_review_only=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_plan_only=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_approval_plan_only=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_apply_plan_only=True", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_browser_started=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_logpoint_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_hook_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_rebuild_executed=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_approval_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "record_review_approval_for_source_map_rebuild_executor")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_rebuild_source_metadata_review")
        self.assertTrue(result.artifacts[0].metadata["approval_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["apply_plan_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["approval_recorded"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_apply_now"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])


    def test_native_web_runtime_reviews_source_map_selected_executor_apply_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        side_effect_policy = {
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "debugger_execution_performed": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "hook_installed": False,
            "rebuild_executed": False,
            "surface_executor_invoked": False,
            "executor_invoked": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
        approval_plan = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-approval-plan.v1",
            "status": "ready_for_review",
            "review_only": True,
            "plan_only": True,
            "approval_plan_only": True,
            "apply_plan_only": True,
            "handoff_only": True,
            "approval_plan_ready": True,
            "apply_plan_ready_for_review": True,
            "approval_recorded": False,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
            "selected_review_gate": "explicit_rebuild_source_metadata_review",
            "executor_review_package": {
                "package_version": "reverse-deepagent.source-map-selected-executor-input-review.package.v1",
                "action_id": "review-rebuild-source-metadata-use",
                "consumer": "rebuild",
                "followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
                "executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
                "review_gate": {"gate": "explicit_rebuild_source_metadata_review", "required_approval_flag": "review_approved"},
                "requires_explicit_review": True,
                "ready_for_downstream_review": True,
                "execute_automatically": False,
                "executor_invoked": False,
                "side_effect_policy": side_effect_policy,
            },
            "apply_plan": {
                "apply_plan_schema_version": "reverse-deepagent.source-map-selected-executor-apply-plan.v1",
                "consumer": "rebuild",
                "future_action": "run_reviewed_source_map_rebuild_metadata_generation",
                "review_gate": "explicit_rebuild_source_metadata_review",
                "executor_input": {"source_content_digest": "abc123", "raw_source_content": None, "raw_content_exported": False, "preview_exported": False},
                "requires_approval_record": True,
                "future_result_artifact": "workspace/source-map-rebuild-result.json",
                "ready_to_apply_now": False,
                "surface_executor_invoked": False,
                "side_effect_policy": side_effect_policy,
            },
            "blockers": [],
            "warnings": [],
            "side_effect_policy": side_effect_policy,
        }
        approval_record = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-approval-record.v1",
            "status": "written",
            "approval_recorded": True,
            "approved_for_apply": True,
            "approval_record_id": "source-map-selected-executor-approval-record:native-web",
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_review_gate": "explicit_rebuild_source_metadata_review",
            "decision": "approved",
            "reviewer": "reviewer-1",
            "approval_plan_digest_sha256": hashlib.sha256(json.dumps(approval_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
            "blockers": [],
            "side_effect_policy": {**side_effect_policy, "approval_recorded": True, "files_mutated": True, "approval_record_writer_only": True},
        }
        dispatcher_result = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-result.v1",
            "status": "dispatched",
            "dispatcher_result_id": "source-map-dispatcher-result:native-web",
            "selected_consumer": "rebuild",
            "dispatch_surface": "source-map-rebuild-result",
            "required_result_artifact": "workspace/source-map-rebuild-result.json",
            "dispatcher_decision_recorded": True,
            "requires_selected_executor_apply_preflight": True,
            "dispatcher_mvp_invoked": True,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "runtime_apply_preflight_invoked": False,
            "ready_to_execute_selected_executor_now": False,
            "blockers": [],
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "selected_executor_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        dispatcher_result_digest = hashlib.sha256(json.dumps(dispatcher_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        result = runtime.apply_minimal_protection(
            "source-map-selected-executor-apply-preflight",
            {
                "source_map_selected_executor_approval_plan": approval_plan,
                "source_map_selected_executor_approval_record": approval_record,
                "source_map_followthrough_dispatcher_result": dispatcher_result,
                "expected_consumer": "rebuild",
                "expected_dispatcher_result_id": "source-map-dispatcher-result:native-web",
                "expected_dispatcher_result_digest_sha256": dispatcher_result_digest,
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_apply_preflight"])
        self.assertIn("source_map_selected_executor_apply_preflight_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_selected_action_id=review-rebuild-source-metadata-use", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_selected_consumer=rebuild", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_selected_gate=explicit_rebuild_source_metadata_review", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_approval_record_verified=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_executor_input_ready=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_verified=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_decision_recorded=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_id=source-map-dispatcher-result:native-web", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_optional=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_handoff_only=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_selected_executor_invoked=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_selected_executor_apply_preflight_invoked=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_dispatcher_result_dispatch_target_invoked=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_ready_for_selected_executor_review=True", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_ready_to_apply_now=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_future_executor_implemented=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_browser_started=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_logpoint_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_hook_installed=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_rebuild_executed=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_apply_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_rebuild_executor_application")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-apply-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_rebuild_source_metadata_review")
        self.assertTrue(result.artifacts[0].metadata["approval_record_verified"])
        self.assertTrue(result.artifacts[0].metadata["executor_input_ready"])
        self.assertTrue(result.artifacts[0].metadata["dispatcher_result_verified"])
        self.assertTrue(result.artifacts[0].metadata["dispatcher_decision_recorded"])
        self.assertEqual(result.artifacts[0].metadata["dispatcher_result_id"], "source-map-dispatcher-result:native-web")
        self.assertFalse(result.artifacts[0].metadata["dispatcher_result_optional"])
        self.assertTrue(result.artifacts[0].metadata["dispatcher_result_handoff_only"])
        self.assertFalse(result.artifacts[0].metadata["dispatcher_result_selected_executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["dispatcher_result_selected_executor_apply_preflight_invoked"])
        self.assertFalse(result.artifacts[0].metadata["dispatcher_result_dispatch_target_invoked"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_apply_now"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])


    def test_native_web_runtime_reviews_source_map_selected_executor_application_handoff_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        apply_preflight = self._ready_source_map_debugger_apply_preflight()
        apply_preflight_digest = hashlib.sha256(json.dumps(apply_preflight, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        result = runtime.apply_minimal_protection(
            "source-map-selected-executor-application-handoff",
            {
                "source_map_selected_executor_application_handoff": True,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "expected_apply_preflight_digest_sha256": apply_preflight_digest,
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_application_handoff"])
        self.assertIn("source_map_selected_executor_application_handoff_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_selected_action_id=review-debugger-location-use", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_application_surface=source-map-debugger-application", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_application_input_key=source_map_debugger_location_input", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_ready_for_application_review=True", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_browser_started=False", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_application_handoff_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_debugger_executor_application")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-application-handoff.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["application_surface"], "source-map-debugger-application")
        self.assertEqual(result.artifacts[0].metadata["application_input_key"], "source_map_debugger_location_input")
        self.assertEqual(result.artifacts[0].metadata["required_approval_flags"], ["review_approved", "approve_source_map_debugger_action"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_application_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["surface_executor_invoked"])


    def test_native_web_runtime_reviews_source_map_selected_executor_result_checkpoint_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        handoff = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-application-handoff.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "application_surface": "source-map-debugger-application",
            "future_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "ready_for_application_review": True,
            "ready_to_execute_now": False,
            "application_invoked": False,
            "surface_executor_invoked": False,
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        application_result = {
            "schema_version": "reverse-deepagent.source-map-debugger-execution-result.v1",
            "status": "success",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "approval_record_id": "source-map-selected-executor-approval:review-debugger-location-use",
            "reviewer": "analyst",
            "review_approved": True,
            "approve_source_map_debugger_action": True,
            "mode": "apply",
            "breakpoint_count": 1,
            "breakpoint_set": True,
            "browser_started": True,
            "runtime_evaluated": False,
            "cdp_command_sent": True,
            "debugger_location_applied": True,
            "debugger_execution_performed": True,
            "surface_executor_invoked": True,
            "automatic_continuation": False,
            "automatic_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
        result = runtime.apply_minimal_protection(
            "source-map-selected-executor-result-checkpoint",
            {
                "source_map_selected_executor_result_checkpoint": True,
                "source_map_selected_executor_application_handoff": handoff,
                "source_map_selected_executor_application_result": application_result,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_result_checkpoint"])
        self.assertIn("source_map_selected_executor_result_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_application_surface=source-map-debugger-application", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_application_result_status=success", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_application_result_verified=True", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_ready_for_next_explicit_review=True", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_observed_browser_started=True", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_observed_cdp_command_sent=True", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_browser_started_by_checkpoint=False", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_cdp_command_sent_by_checkpoint=False", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_result_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_selected_executor_result_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-result-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["application_result_status"], "success")
        self.assertTrue(result.artifacts[0].metadata["application_result_verified"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_next_explicit_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["browser_started_by_checkpoint"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent_by_checkpoint"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated_by_checkpoint"])


    def test_native_web_runtime_reviews_source_map_followthrough_completion_checkpoint_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result_checkpoint = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "application_surface": "source-map-debugger-application",
            "application_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "application_result_status": "success",
            "application_result_verified": True,
            "application_handoff_verified": True,
            "ready_for_next_explicit_review": True,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
        result = runtime.apply_minimal_protection(
            "source-map-followthrough-completion-checkpoint",
            {
                "source_map_followthrough_completion_checkpoint": True,
                "source_map_selected_executor_result_checkpoint": result_checkpoint,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_completion_checkpoint"])
        self.assertIn("source_map_followthrough_completion_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_completion_status=terminal_review_candidate", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_terminal_review_candidate=True", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_followup_required=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_ready_for_completion_review=True", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_recommended_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_browser_started_by_completion=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_cdp_command_sent_by_completion=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_runtime_evaluated_by_completion=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_completion_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "inspect_source_map_debugger_execution_artifacts")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-completion-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["completion_status"], "terminal_review_candidate")
        self.assertTrue(result.artifacts[0].metadata["terminal_review_candidate"])
        self.assertFalse(result.artifacts[0].metadata["followup_required"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_completion_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["browser_started_by_completion"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent_by_completion"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated_by_completion"])


    def test_native_web_runtime_reviews_source_map_terminal_review_package_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        completion = {
            "schema_version": "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "application_surface": "source-map-debugger-application",
            "completion_status": "terminal_review_candidate",
            "terminal_review_candidate": True,
            "followup_required": False,
            "completion_checkpoint_ready": True,
            "ready_for_completion_review": True,
            "ready_for_next_explicit_review": True,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "completion_review": {
                "recommended_review_action": "inspect_source_map_debugger_execution_artifacts",
                "required_artifacts": ["workspace/source-map-debugger-execution-result.json", "workspace/breakpoints.json"],
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-terminal-review-package",
            {
                "source_map_terminal_review_package": True,
                "source_map_followthrough_completion_checkpoint": completion,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_terminal_review_package"])
        self.assertIn("source_map_terminal_review_package_status=ready_for_review", result.verification)
        self.assertIn("source_map_terminal_review_package_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_terminal_review_package_completion_status=terminal_review_candidate", result.verification)
        self.assertIn("source_map_terminal_review_package_terminal_review_candidate=True", result.verification)
        self.assertIn("source_map_terminal_review_package_ready_for_terminal_review=True", result.verification)
        self.assertIn("source_map_terminal_review_package_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_terminal_review_package_recommended_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_terminal_review_package_recommended_action_executed=False", result.verification)
        self.assertIn("source_map_terminal_review_package_browser_started_by_package=False", result.verification)
        self.assertIn("source_map_terminal_review_package_cdp_command_sent_by_package=False", result.verification)
        self.assertIn("source_map_terminal_review_package_runtime_evaluated_by_package=False", result.verification)
        self.assertIn("source_map_terminal_review_package_calls_mcp=False", result.verification)
        self.assertIn("source_map_terminal_review_package_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_terminal_review_package")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-terminal-review-package.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["package_kind"], "terminal-review-package")
        self.assertTrue(result.artifacts[0].metadata["ready_for_terminal_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["recommended_action_executed"])
        self.assertFalse(result.artifacts[0].metadata["browser_started_by_package"])


    def test_native_web_runtime_reviews_source_map_terminal_review_closure_checkpoint_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        terminal_package = {
            "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "application_surface": "source-map-debugger-application",
            "completion_status": "terminal_review_candidate",
            "terminal_review_candidate": True,
            "followup_required": False,
            "ready_for_terminal_review": True,
            "ready_for_audit_handoff_review": True,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "recommended_action_executed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "terminal_review_package": {
                "schema_version": "reverse-deepagent.source-map-terminal-review-package.payload.v1",
                "package_kind": "terminal-review-package",
                "recommended_review_action": "inspect_source_map_debugger_execution_artifacts",
                "required_artifacts": ["workspace/source-map-debugger-execution-result.json", "workspace/breakpoints.json"],
                "execute_recommended_action": False,
            },
        }
        observed = {
            "schema_version": "reverse-deepagent.source-map-terminal-review-observed-result.v1",
            "status": "reviewed",
            "review_completed": True,
            "observed_review_action": "inspect_source_map_debugger_execution_artifacts",
            "reviewer": "analyst",
        }
        result = runtime.apply_minimal_protection(
            "source-map-terminal-review-closure-checkpoint",
            {
                "source_map_terminal_review_closure_checkpoint": True,
                "source_map_terminal_review_package": terminal_package,
                "source_map_terminal_review_observed_result": observed,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_terminal_review_closure_checkpoint"])
        self.assertIn("source_map_terminal_review_closure_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_closure_status=terminal_review_observed", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_ready_for_closure_audit_review=True", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_recommended_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_observed_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_recommended_action_executed_by_checkpoint=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_browser_started_by_checkpoint=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_cdp_command_sent_by_checkpoint=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_runtime_evaluated_by_checkpoint=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("source_map_terminal_review_closure_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_terminal_review_closure_checkpoint")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-terminal-review-closure-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["closure_status"], "terminal_review_observed")
        self.assertTrue(result.artifacts[0].metadata["ready_for_closure_audit_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["recommended_action_executed_by_checkpoint"])
        self.assertFalse(result.artifacts[0].metadata["browser_started_by_checkpoint"])


    def test_native_web_runtime_reviews_source_map_terminal_review_final_audit_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        closure = {
            "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_review_gate": "explicit_debugger_location_review",
            "application_surface": "source-map-debugger-application",
            "closure_status": "terminal_review_observed",
            "terminal_review_candidate": True,
            "followup_required": False,
            "ready_for_closure_audit_review": True,
            "observed_review_completed": True,
            "ready_to_execute_now": False,
            "execute_next_automatically": False,
            "recommended_action_executed_by_checkpoint": False,
            "recommended_review_action": "inspect_source_map_debugger_execution_artifacts",
            "observed_review_action": "inspect_source_map_debugger_execution_artifacts",
            "required_artifacts": ["workspace/source-map-debugger-execution-result.json", "workspace/breakpoints.json"],
            "source_terminal_review_package_digest_sha256": "pkg-digest",
            "source_observed_result_digest_sha256": "obs-digest",
            "calls_mcp": False,
            "mobile_runtime_used": False,
            "closure_audit": {
                "schema_version": "reverse-deepagent.source-map-terminal-review-closure-audit.v1",
                "manual_review_observed": True,
                "execute_recommended_action": False,
            },
        }
        result = runtime.apply_minimal_protection(
            "source-map-terminal-review-final-audit",
            {
                "source_map_terminal_review_final_audit": True,
                "source_map_terminal_review_closure_checkpoint": closure,
                "expected_consumer": "debugger",
                "expected_action_id": "review-debugger-location-use",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_terminal_review_final_audit"])
        self.assertIn("source_map_terminal_review_final_audit_status=ready_for_review", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_final_audit_status=source_map_followthrough_review_closed", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_ready_for_final_audit_review=True", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_ready_to_execute_now=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_recommended_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_observed_review_action=inspect_source_map_debugger_execution_artifacts", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_recommended_action_executed_by_rollup=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_browser_started_by_rollup=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_cdp_command_sent_by_rollup=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_runtime_evaluated_by_rollup=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_calls_mcp=False", result.verification)
        self.assertIn("source_map_terminal_review_final_audit_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_terminal_review_final_audit")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-terminal-review-final-audit.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["final_audit_status"], "source_map_followthrough_review_closed")
        self.assertTrue(result.artifacts[0].metadata["ready_for_final_audit_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["recommended_action_executed_by_rollup"])
        self.assertFalse(result.artifacts[0].metadata["browser_started_by_rollup"])


    def test_native_web_runtime_reviews_source_map_followthrough_chain_readiness_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        apply_preflight = {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": "ready_for_review",
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
            "selected_review_gate": "explicit_rebuild_source_metadata_review",
            "approval_record_verified": True,
            "executor_input_ready": True,
            "ready_for_selected_executor_review": True,
            "ready_to_apply_now": False,
            "future_executor_contract": {"implemented": False},
            "future_action": "run_reviewed_source_map_rebuild_metadata_generation",
            "future_result_artifact": "workspace/source-map-rebuild-result.json",
            "blockers": [],
            "side_effect_policy": {
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-chain-readiness",
            {
                "source_map_followthrough_chain_readiness": True,
                "source_map_selected_executor_apply_preflight": apply_preflight,
                "expected_consumer": "rebuild",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_chain_readiness"])
        self.assertIn("source_map_followthrough_chain_readiness_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_selected_consumer=rebuild", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_completed_stage=source_map_selected_executor_apply_preflight", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_next_stage=selected_executor_result_review", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_next_required_artifact=workspace/source-map-rebuild-generation-result.json", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_selected_executor_result_ready=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_ready_for_selected_executor_review=True", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_review_only=True", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_plan_only=True", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_orchestration_only=True", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_handoff_only=True", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_automatic_followthrough_supported=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_logpoint_installed=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_hook_installed=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_rebuild_executed=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_chain_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_rebuild_generation_or_metadata_result")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-chain-readiness.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(result.artifacts[0].metadata["next_stage"], "selected_executor_result_review")
        self.assertEqual(result.artifacts[0].metadata["next_required_artifact"], "workspace/source-map-rebuild-generation-result.json")
        self.assertTrue(result.artifacts[0].metadata["orchestration_only"])
        self.assertFalse(result.artifacts[0].metadata["automatic_followthrough_supported"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_followthrough_one_step_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        chain = {
            "schema_version": "reverse-deepagent.source-map-followthrough-chain-readiness.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "completed_stage": "source_map_selected_executor_apply_preflight",
            "next_stage": "selected_executor_result_review",
            "next_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "next_action": "review_source_map_debugger_executor_application",
            "selected_executor_result_ready": False,
            "automatic_followthrough_supported": False,
            "automatic_execution_supported": False,
            "blockers": [],
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-one-step-plan",
            {
                "source_map_followthrough_one_step_plan": True,
                "source_map_followthrough_chain_readiness": chain,
                "expected_consumer": "debugger",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_one_step_plan"])
        self.assertIn("source_map_followthrough_one_step_plan_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_source_chain_completed_stage=source_map_selected_executor_apply_preflight", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_source_chain_next_stage=selected_executor_result_review", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_source_chain_next_action=review_source_map_debugger_executor_application", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_planned_step_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_review_only=True", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_plan_only=True", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_will_invoke_next_action=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_hook_installed=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_rebuild_executed=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_one_step_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_one_step_plan_before_next_action")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-one-step-plan.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["source_chain_completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(result.artifacts[0].metadata["source_chain_next_stage"], "selected_executor_result_review")
        self.assertEqual(result.artifacts[0].metadata["source_chain_next_action"], "review_source_map_debugger_executor_application")
        self.assertTrue(result.artifacts[0].metadata["one_step_plan_only"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_next_action"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatch_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        one_step_plan = {
            "schema_version": "reverse-deepagent.source-map-followthrough-one-step-plan.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "source_chain_next_stage": "selected_executor_result_review",
            "source_chain_next_action": "review_source_map_debugger_executor_application",
            "source_chain_next_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "planned_step_ready_for_review": True,
            "will_invoke_next_action": False,
            "automatic_execution_supported": False,
            "planned_step": {
                "step_id": "source-map-followthrough-one-step:debugger",
                "step_schema_version": "reverse-deepagent.source-map-followthrough-one-step.v1",
                "selected_consumer": "debugger",
                "next_stage": "selected_executor_result_review",
                "next_action": "review_source_map_debugger_executor_application",
                "next_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "requires_explicit_review": True,
                "requires_separate_executor_call": True,
                "execute_automatically": False,
                "executor_invoked": False,
                "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
            },
            "blockers": [],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatch-preflight",
            {
                "source_map_followthrough_dispatch_preflight": True,
                "source_map_followthrough_one_step_plan": one_step_plan,
                "expected_consumer": "debugger",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatch_preflight"])
        self.assertIn("source_map_followthrough_dispatch_preflight_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_planned_next_action=review_source_map_debugger_executor_application", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_dispatch_surface=source-map-debugger-execution-result", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_dispatcher_input_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_will_invoke_dispatch_target=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatch-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["dispatcher_input_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_dispatch_target"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatch_approval_plan_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "planned_next_action": "review_source_map_debugger_executor_application",
            "planned_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "dispatch_target": {"dispatch_surface": "source-map-debugger-execution-result"},
            "dispatcher_input_ready_for_review": True,
            "dispatcher_input": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-input.v1",
                "dispatch_surface": "source-map-debugger-execution-result",
                "selected_consumer": "debugger",
                "next_action": "review_source_map_debugger_executor_application",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "review_gate": "explicit_source_map_debugger_executor_review",
                "requires_explicit_review": True,
                "requires_separate_executor_call": True,
                "dispatcher_invoked": False,
                "executor_invoked": False,
                "approval_recorded": False,
                "apply_preflight_invoked": False,
                "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
            },
            "blockers": [],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatch-approval-plan",
            {
                "source_map_followthrough_dispatch_approval_plan": True,
                "source_map_followthrough_dispatch_preflight": preflight,
                "expected_consumer": "debugger",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatch_approval_plan"])
        self.assertIn("source_map_followthrough_dispatch_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_dispatch_surface=source-map-debugger-execution-result", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_plan_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_ready_to_dispatch_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_transaction_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_will_invoke_dispatch_target=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_approval_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatch-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["approval_plan_ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["transaction_plan_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_dispatch_now"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_dispatch_target"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatch_transaction_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        dispatch_preflight = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-preflight.v1",
            "status": "ready_for_review",
            "selected_consumer": "debugger",
            "planned_next_action": "review_source_map_debugger_executor_application",
            "planned_required_artifact": "workspace/source-map-debugger-execution-result.json",
            "dispatch_target": {"dispatch_surface": "source-map-debugger-execution-result"},
            "dispatcher_input_ready_for_review": True,
            "dispatcher_input": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-input.v1",
                "dispatch_surface": "source-map-debugger-execution-result",
                "selected_consumer": "debugger",
                "next_action": "review_source_map_debugger_executor_application",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "review_gate": "explicit_source_map_debugger_executor_review",
                "requires_explicit_review": True,
                "requires_separate_executor_call": True,
                "dispatcher_invoked": False,
                "executor_invoked": False,
                "approval_recorded": False,
                "apply_preflight_invoked": False,
                "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
            },
            "blockers": [],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        }
        approval_descriptor = SourceMapFollowthroughDispatchApprovalPlanManager().review(
            SourceMapFollowthroughDispatchApprovalPlanSpec.from_context(
                {
                    "source_map_followthrough_dispatch_approval_plan": True,
                    "source_map_followthrough_dispatch_preflight": dispatch_preflight,
                    "expected_consumer": "debugger",
                    "expected_dispatch_surface": "source-map-debugger-execution-result",
                    "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                    "reviewer": "analyst",
                }
            )
        ).descriptor
        plan_digest = hashlib.sha256(json.dumps(approval_descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        approval_record = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1",
            "status": "written",
            "approval_recorded": True,
            "approved_for_dispatch": True,
            "decision": "approved",
            "approval_record_id": "source-map-followthrough-dispatch-approval-record:native",
            "approval_plan_id": approval_descriptor["approval_plan"]["approval_plan_id"],
            "transaction_plan_id": approval_descriptor["transaction_plan"]["transaction_plan_id"],
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "approval_plan_digest_sha256": plan_digest,
            "dispatch_input_gates": {
                "approval_recorded": True,
                "approved_for_dispatch": True,
                "ready_to_dispatch_now": False,
                "transaction_started": False,
                "journal_written": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "requires_transaction_preflight_followup": True,
                "requires_transaction_journal_before_dispatch": True,
            },
            "side_effect_policy": {
                "approval_record_writer": True,
                "dry_run_is_read_only": True,
                "files_mutated": True,
                "artifacts_written": True,
                "writes_approval_record": True,
                "approval_recorded": True,
                "ready_to_dispatch_now": False,
                "transaction_started": False,
                "journal_written": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatch-transaction-preflight",
            {
                "source_map_followthrough_dispatch_transaction_preflight": True,
                "source_map_followthrough_dispatch_approval_plan": approval_descriptor,
                "source_map_followthrough_dispatch_approval_record": approval_record,
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "expected_plan_digest_sha256": plan_digest,
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatch_transaction_preflight"])
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_dispatch_surface=source-map-debugger-execution-result", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_approval_record_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_transaction_plan_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_journal_writer_gate_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_ready_to_write_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_ready_to_dispatch_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_transaction_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_journal_written=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_will_write_transaction_journal=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_will_invoke_dispatch_target=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatch_transaction_journal_writer")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatch-transaction-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["transaction_preflight_ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["journal_writer_gate_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["will_write_transaction_journal"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_dispatch_target"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatch_bounded_executor_gate_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        journal = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1",
            "status": "written",
            "journal_written": True,
            "transaction_started": True,
            "journal_id": "source-map-followthrough-dispatch-transaction-journal:native",
            "transaction_preflight_id": "source-map-followthrough-dispatch-transaction-preflight:native",
            "approval_record_id": "source-map-followthrough-dispatch-approval-record:native",
            "approval_plan_id": "source-map-followthrough-dispatch-approval:native",
            "transaction_plan_id": "source-map-followthrough-dispatch-transaction:native",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "journal_summary": {
                "entry_count": 2,
                "planned_entry_count": 2,
                "transaction_started": True,
                "journal_written": True,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "requires_bounded_dispatch_gate_followup": True,
            },
            "dispatch_input_gates": {
                "ready_to_dispatch_now": False,
                "approval_record_verified": True,
                "transaction_plan_verified": True,
                "transaction_started": True,
                "journal_written": True,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "debugger_executed": False,
                "source_logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "requires_bounded_dispatch_gate": True,
                "requires_explicit_dispatch_review": True,
            },
            "blockers": [],
            "side_effect_policy": {
                "transaction_journal_writer": True,
                "files_mutated": True,
                "artifacts_written": True,
                "writes_transaction_journal": True,
                "transaction_started": True,
                "journal_written": True,
                "ready_to_dispatch_now": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "debugger_execution_performed": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        journal_digest = hashlib.sha256(json.dumps(journal, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatch-bounded-executor-gate",
            {
                "source_map_followthrough_dispatch_bounded_executor_gate": True,
                "source_map_followthrough_dispatch_transaction_journal": journal,
                "expected_journal_id": journal["journal_id"],
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "expected_journal_digest_sha256": journal_digest,
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatch_bounded_executor_gate"])
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_dispatch_surface=source-map-debugger-execution-result", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_transaction_journal_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_ready_to_dispatch_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_dispatch_target_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_executor_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_future_dispatcher_implemented=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_calls_mcp=False", result.verification)
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatcher_handoff")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatch-bounded-executor-gate.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["bounded_executor_gate_ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_dispatcher_handoff_review"])
        self.assertFalse(result.artifacts[0].metadata["future_dispatcher_contract"]["implemented"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_dispatch_target"])
        self.assertFalse(result.artifacts[0].metadata["will_invoke_next_action"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatcher_handoff_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        gate = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-bounded-executor-gate.v1",
            "status": "ready_for_review",
            "review_only": True,
            "read_only": True,
            "bounded_executor_gate_only": True,
            "handoff_only": True,
            "journal_id": "journal-1",
            "transaction_preflight_id": "tx-preflight-1",
            "approval_record_id": "approval-record-1",
            "approval_plan_id": "approval-plan-1",
            "transaction_plan_id": "transaction-plan-1",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "transaction_journal_verified": True,
            "bounded_executor_gate_ready_for_review": True,
            "ready_for_dispatcher_handoff_review": True,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "bounded_dispatch_input": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-bounded-input.v1",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "journal_id": "journal-1",
                "transaction_preflight_id": "tx-preflight-1",
                "approval_record_id": "approval-record-1",
                "transaction_plan_id": "transaction-plan-1",
                "ready_for_dispatcher_handoff_review": True,
                "ready_to_dispatch_now": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
            },
            "future_dispatcher_contract": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-contract.v1",
                "dispatcher_name": "dispatch_source_map_followthrough_next_action",
                "implemented": False,
                "result_artifact": "workspace/source-map-followthrough-dispatcher-handoff.json",
                "requires_explicit_review": True,
            },
            "blockers": [],
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "apply_preflight_invoked": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        gate_digest = hashlib.sha256(json.dumps(gate, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatcher-handoff",
            {
                "source_map_followthrough_dispatcher_handoff": True,
                "source_map_followthrough_dispatch_bounded_executor_gate": gate,
                "expected_gate_digest_sha256": gate_digest,
                "expected_journal_id": "journal-1",
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatcher_handoff"])
        self.assertIn("source_map_followthrough_dispatcher_handoff_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_bounded_gate_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_ready_for_explicit_dispatch_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_ready_to_dispatch_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_dispatcher_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_dispatch_target_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_executor_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_handoff_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatcher_apply_preflight")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatcher-handoff.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["dispatcher_handoff_ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_explicit_dispatch_review"])
        self.assertFalse(result.artifacts[0].metadata["dispatcher_invoked"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_reviews_source_map_followthrough_dispatcher_apply_preflight_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        handoff = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-handoff.v1",
            "status": "ready_for_review",
            "review_only": True,
            "read_only": True,
            "dispatcher_handoff_only": True,
            "handoff_only": True,
            "journal_id": "journal-1",
            "transaction_preflight_id": "tx-preflight-1",
            "approval_record_id": "approval-record-1",
            "approval_plan_id": "approval-plan-1",
            "transaction_plan_id": "transaction-plan-1",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "bounded_gate_verified": True,
            "dispatcher_handoff_ready_for_review": True,
            "ready_for_explicit_dispatch_review": True,
            "ready_for_selected_executor_review": True,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "dispatcher_handoff": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-handoff-input.v1",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "journal_id": "journal-1",
                "transaction_preflight_id": "tx-preflight-1",
                "approval_record_id": "approval-record-1",
                "transaction_plan_id": "transaction-plan-1",
                "dispatcher_name": "dispatch_source_map_followthrough_next_action",
                "ready_for_explicit_dispatch_review": True,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "requires_selected_executor_apply_preflight": True,
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
            },
            "selected_executor_review_contract": {
                "schema_version": "reverse-deepagent.source-map-followthrough-selected-executor-review-contract.v1",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "ready_for_review": True,
                "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
                "must_review_apply_preflight_before_executor": True,
                "must_not_invoke_executor_from_handoff": True,
            },
            "blockers": [],
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "selected_executor_invoked": False,
                "apply_preflight_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        handoff_digest = hashlib.sha256(json.dumps(handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatcher-apply-preflight",
            {
                "source_map_followthrough_dispatcher_apply_preflight": True,
                "source_map_followthrough_dispatcher_handoff": handoff,
                "expected_handoff_digest_sha256": handoff_digest,
                "expected_journal_id": "journal-1",
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_followthrough_dispatcher_apply_preflight"])
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_status=ready_for_review", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_handoff_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_ready_for_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp_review=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_ready_to_dispatch_now=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_dispatcher_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_dispatch_target_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_executor_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_selected_executor_apply_preflight_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_followthrough_dispatcher_mvp")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatcher-apply-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result.artifacts[0].metadata["dispatcher_apply_preflight_ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["ready_for_explicit_dispatcher_mvp_review"])
        self.assertFalse(result.artifacts[0].metadata["dispatcher_invoked"])
        self.assertFalse(result.artifacts[0].metadata["executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])

    def test_native_web_runtime_records_source_map_followthrough_dispatcher_result_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        apply_preflight = {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight.v1",
            "status": "ready_for_review",
            "journal_id": "journal-1",
            "transaction_preflight_id": "tx-preflight-1",
            "approval_record_id": "dispatch-approval-1",
            "approval_plan_id": "dispatch-approval-plan-1",
            "transaction_plan_id": "tx-plan-1",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "dispatcher_apply_preflight_ready_for_review": True,
            "ready_for_explicit_dispatcher_mvp_review": True,
            "ready_to_dispatch_now": False,
            "ready_to_execute_now": False,
            "dispatcher_invoked": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "selected_executor_invoked": False,
            "selected_executor_apply_preflight_invoked": False,
            "dispatcher_apply_preflight": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-apply-preflight-input.v1",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "journal_id": "journal-1",
                "transaction_preflight_id": "tx-preflight-1",
                "approval_record_id": "dispatch-approval-1",
                "transaction_plan_id": "tx-plan-1",
                "dispatcher_name": "dispatch_source_map_followthrough_next_action",
                "ready_for_explicit_dispatcher_mvp_review": True,
                "ready_to_dispatch_now": False,
                "ready_to_execute_now": False,
                "requires_explicit_dispatcher_mvp_review": True,
                "requires_selected_executor_apply_preflight": True,
                "selected_executor_apply_preflight_artifact": "workspace/source-map-selected-executor-apply-preflight.json",
                "dispatcher_invoked": False,
                "dispatch_target_invoked": False,
                "executor_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
            },
            "future_dispatcher_mvp_contract": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatcher-mvp-contract.v1",
                "dispatcher_name": "dispatch_source_map_followthrough_next_action",
                "implemented": False,
                "contract_ready_for_review": True,
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
                "input_artifact": "workspace/source-map-followthrough-dispatcher-apply-preflight.json",
                "result_artifact": "workspace/source-map-followthrough-dispatcher-result.json",
                "requires_explicit_review": True,
                "requires_selected_executor_apply_preflight": True,
                "must_not_skip_selected_executor_apply_preflight": True,
            },
            "blockers": [],
            "side_effect_policy": {
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }
        apply_preflight_digest = hashlib.sha256(json.dumps(apply_preflight, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

        result = runtime.apply_minimal_protection(
            "source-map-followthrough-dispatcher-result",
            {
                "source_map_followthrough_dispatcher_result": True,
                "source_map_followthrough_dispatcher_apply_preflight": apply_preflight,
                "mode": "apply",
                "write_result": True,
                "review_approved": True,
                "approve_dispatcher_mvp": True,
                "reviewer": "analyst",
                "expected_apply_preflight_digest_sha256": apply_preflight_digest,
                "expected_journal_id": "journal-1",
                "expected_consumer": "debugger",
                "expected_dispatch_surface": "source-map-debugger-execution-result",
                "expected_required_artifact": "workspace/source-map-debugger-execution-result.json",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["record_source_map_followthrough_dispatcher_result"])
        self.assertIn("source_map_followthrough_dispatcher_result_status=dispatched", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_apply_preflight_verified=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_decision_recorded=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_dispatch_target_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_selected_executor_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_selected_executor_apply_preflight_invoked=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_requires_selected_executor_apply_preflight=True", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_browser_started=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_followthrough_dispatcher_result_calls_mcp=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_selected_executor_apply_preflight")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-followthrough-dispatcher-result.json")
        self.assertTrue(result.artifacts[0].metadata["dispatcher_decision_recorded"])
        self.assertFalse(result.artifacts[0].metadata["dispatch_target_invoked"])
        self.assertFalse(result.artifacts[0].metadata["selected_executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["selected_executor_apply_preflight_invoked"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_source_map_readiness_without_starting_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-readiness",
            {
                "source_map_lookup": {
                    "status": "ready_for_review",
                    "mapping_found": True,
                    "location": {"strategy": "source_map_generated_exact"},
                },
                "source_map_source_content": {
                    "status": "ready_for_review",
                    "source_content_available": True,
                    "content_summary": {"sha256": "abc123", "raw_content_exported": False, "preview_exported": False},
                },
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "scope_candidate_count": 1,
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "hook_readiness": {"source_logpoint_reviewable": True},
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_readiness"])
        self.assertIn("source_map_readiness_status=ready_for_review", result.verification)
        self.assertIn("source_map_readiness_debugger_location_ready=True", result.verification)
        self.assertIn("source_map_readiness_source_content_metadata_ready=True", result.verification)
        self.assertIn("source_map_readiness_rebuild_source_metadata_ready=True", result.verification)
        self.assertIn("source_map_readiness_source_logpoint_planning_ready=True", result.verification)
        self.assertIn("source_map_readiness_bundler_scope_review_ready=True", result.verification)
        self.assertIn("source_map_readiness_source_content_sha256=abc123", result.verification)
        self.assertIn("source_map_readiness_review_only=True", result.verification)
        self.assertIn("source_map_readiness_raw_exported=False", result.verification)
        self.assertIn("source_map_readiness_preview_exported=False", result.verification)
        self.assertIn("source_map_readiness_fetch_source_map=False", result.verification)
        self.assertIn("source_map_readiness_browser_started=False", result.verification)
        self.assertIn("source_map_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_readiness_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_readiness_logpoint_installed=False", result.verification)
        self.assertIn("source_map_readiness_calls_mcp=False", result.verification)
        self.assertIn("source_map_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-readiness.json")
        self.assertTrue(result.artifacts[0].metadata["debugger_location_ready"])
        self.assertTrue(result.artifacts[0].metadata["source_content_metadata_ready"])
        self.assertTrue(result.artifacts[0].metadata["rebuild_source_metadata_ready"])
        self.assertTrue(result.artifacts[0].metadata["source_logpoint_planning_ready"])
        self.assertTrue(result.artifacts[0].metadata["bundler_scope_review_ready"])
        self.assertEqual(result.artifacts[0].metadata["sha256"], "abc123")
        self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
        self.assertFalse(result.artifacts[0].metadata["preview_exported"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])

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

    @staticmethod
    def _ready_source_map_source_logpoint_apply_preflight() -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "selected_action_id": "review-source-logpoint-plan",
            "selected_consumer": "source-logpoint",
            "selected_followthrough_review_surface": "review_source_logpoint_executor_input",
            "selected_review_gate": "explicit_source_logpoint_install_review",
            "approval_record_id": "source-map-selected-executor-approval-record:logpoint",
            "approval_record_verified": True,
            "executor_input_ready": True,
            "ready_for_selected_executor_review": True,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "source_logpoint_installed": False,
            "executor_input": {
                "source_logpoint_plan": {
                    "bundler_kind": "webpack",
                    "scope_candidate_count": 1,
                    "install_supported": False,
                    "logpoint_installed": False,
                },
                "source_logpoint_spec_input": {
                    "url_pattern_required": True,
                    "log_expression_required": True,
                    "install_supported_now": False,
                },
            },
            "future_executor_contract": {
                "implemented": False,
                "future_action": "install_reviewed_source_map_source_logpoint",
                "requires_explicit_executor_approval": True,
                "requires_apply_mode": True,
                "requires_write_result": True,
                "requires_reviewed_apply_preflight": True,
            },
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "preflight_only": True,
                "apply_preflight_only": True,
                "handoff_only": True,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "logpoint_installed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    @staticmethod
    def _ready_source_map_debugger_apply_preflight() -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "selected_action_id": "review-debugger-location-use",
            "selected_consumer": "debugger",
            "selected_followthrough_review_surface": "review_debugger_location_executor_input",
            "selected_review_gate": "explicit_debugger_location_review",
            "approval_record_id": "source-map-selected-executor-approval-record:debugger",
            "approval_record_verified": True,
            "executor_input_ready": True,
            "ready_for_selected_executor_review": True,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "debugger_executed": False,
            "executor_input": {
                "location": {
                    "source": "src/sign.ts",
                    "line_number": 4,
                    "column_number": 0,
                    "mapping_strategy": "source_map_generated_exact",
                },
                "cdp_command": None,
                "requires_review_before_debugger_use": True,
            },
            "future_executor_contract": {
                "implemented": False,
                "future_action": "execute_reviewed_source_map_debugger_location_action",
                "requires_explicit_executor_approval": True,
                "requires_apply_mode": True,
                "requires_write_result": True,
                "requires_reviewed_apply_preflight": True,
            },
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "preflight_only": True,
                "apply_preflight_only": True,
                "handoff_only": True,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "debugger_execution_performed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    @staticmethod
    def _ready_source_map_hook_apply_preflight() -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "selected_action_id": "review-hook-symbol-scope-use",
            "selected_consumer": "hook",
            "selected_followthrough_review_surface": "review_hook_symbol_scope_executor_input",
            "selected_review_gate": "explicit_hook_symbol_scope_review",
            "approval_record_id": "source-map-selected-executor-approval-record:hook",
            "approval_record_verified": True,
            "executor_input_ready": True,
            "ready_for_selected_executor_review": True,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "hook_installed": False,
            "executor_input": {
                "hook_symbol_scope": {
                    "bundler_kind": "webpack",
                    "scope_candidate_count": 1,
                    "symbol": "buildSign",
                    "source": "src/sign.ts",
                },
                "hook_candidate_review_required": True,
                "hook_install_supported_now": False,
            },
            "future_executor_contract": {
                "implemented": False,
                "future_action": "install_reviewed_source_map_hook_symbol_scope",
                "requires_explicit_executor_approval": True,
                "requires_apply_mode": True,
                "requires_write_result": True,
                "requires_reviewed_apply_preflight": True,
            },
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "preflight_only": True,
                "apply_preflight_only": True,
                "handoff_only": True,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "hook_installed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    @staticmethod
    def _ready_source_map_rebuild_apply_preflight() -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
            "status": "ready_for_review",
            "review_only": True,
            "preflight_only": True,
            "apply_preflight_only": True,
            "handoff_only": True,
            "selected_action_id": "review-rebuild-source-metadata-use",
            "selected_consumer": "rebuild",
            "selected_followthrough_review_surface": "review_rebuild_source_metadata_executor_input",
            "selected_review_gate": "explicit_rebuild_source_metadata_review",
            "approval_record_id": "source-map-selected-executor-approval-record:rebuild",
            "approval_record_verified": True,
            "executor_input_ready": True,
            "ready_for_selected_executor_review": True,
            "ready_to_apply_now": False,
            "surface_executor_invoked": False,
            "rebuild_executed": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "executor_input": {
                "source_content_digest": "abc123",
                "source_content_available": True,
                "raw_source_content": None,
                "raw_content_exported": False,
                "preview_exported": False,
            },
            "future_executor_contract": {
                "implemented": False,
                "future_action": "run_reviewed_source_map_rebuild_metadata_generation",
                "requires_explicit_executor_approval": True,
                "requires_apply_mode": True,
                "requires_write_result": True,
                "requires_reviewed_apply_preflight": True,
            },
            "side_effect_policy": {
                "read_only": True,
                "review_only": True,
                "preflight_only": True,
                "apply_preflight_only": True,
                "handoff_only": True,
                "browser_started": False,
                "runtime_evaluated": False,
                "cdp_command_sent": False,
                "logpoint_installed": False,
                "hook_installed": False,
                "rebuild_executed": False,
                "surface_executor_invoked": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

    @staticmethod
    def _successful_source_map_rebuild_metadata_result() -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-rebuild-result.v1",
            "status": "success",
            "selected_consumer": "rebuild",
            "selected_review_gate": "explicit_rebuild_source_metadata_review",
            "source_content_digest": "abc123",
            "source_content_available": True,
            "metadata_only": True,
            "rebuild_metadata_applied": True,
            "rebuild_bundle_generated": False,
            "rebuild_executed": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "raw_source_content_included": False,
            "source_map_fetched": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _source_map_rebuild_generation_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
        task_card = TaskCard(
            target_url_or_file="https://example.test/",
            target_param_or_api="sign",
            goal="生成纯算 replay",
            boundaries="source map rebuild generation test",
        )
        source_context = """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        sample_sign = hashlib.md5("sign:1700000000000".encode("utf-8")).hexdigest()
        candidate = {
            "candidate_id": "source-map:buildSign",
            "function_name": "buildSign",
            "file_url": "https://example.test/assets/app.js",
            "script_id": "script-1",
            "line_number": 1,
            "source_context": source_context,
            "related_requests": [{"id": 1, "method": "POST", "url": "https://example.test/api/search"}],
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
        final_result = FinalResult(
            task_card=task_card,
            mode=ReverseMode.FIND_ENTRY,
            stage=ReverseStage.REPLAY_DELIVERY,
            status=ExecutionStatus.SUCCESS,
            key_findings=KeyFindings(facts=["reviewed source-map rebuild input"]),
            evidence=[
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
            ],
            artifacts=[],
            next_action="extract_pure_logic_and_build_replay",
            confidence=ConfidenceLevel.HIGH,
        )
        return task_card.model_dump(mode="json"), final_result.model_dump(mode="json")

    def test_native_web_runtime_applies_reviewed_source_map_function_hook_install(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-hook-application",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_map_hook_install": True,
                "reviewer": "reviewer-1",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_hook_apply_preflight(),
                "source_map_hook_install_input": {
                    "hook_kind": "function",
                    "function_name": "buildSign",
                    "function_paths": ["window.buildSign"],
                    "candidate_id": "source-map-hook:buildSign",
                    "trigger_expression": "window.buildSign('sign', 1700000000000)",
                    "cdp_command": None,
                },
            },
        )

        self.assertEqual(provider.started, 1)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["install_source_map_function_hook:buildSign"])
        self.assertIn("source_map_hook_application_status=success", result.verification)
        self.assertIn("source_map_hook_application_installed_count=1", result.verification)
        self.assertIn("source_map_hook_application_event_count=2", result.verification)
        self.assertIn("source_map_hook_application_browser_started=True", result.verification)
        self.assertIn("source_map_hook_application_runtime_evaluated=True", result.verification)
        self.assertIn("source_map_hook_application_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_hook_application_hook_installed=True", result.verification)
        self.assertIn("source_map_hook_application_function_hook_installed=True", result.verification)
        self.assertIn("source_map_hook_application_module_hook_installed=False", result.verification)
        self.assertIn("source_map_hook_application_calls_mcp=False", result.verification)
        self.assertIn("source_map_hook_application_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "inspect_source_map_hook_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-hook-install-result.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-hook-install-result.v1")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "hook")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_hook_symbol_scope_review")
        self.assertEqual(result.artifacts[0].metadata["hook_kind"], "function")
        self.assertEqual(result.artifacts[0].metadata["function_name"], "buildSign")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertTrue(result.artifacts[0].metadata["approve_source_map_hook_install"])
        self.assertTrue(result.artifacts[0].metadata["browser_started"])
        self.assertTrue(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertTrue(result.artifacts[0].metadata["hook_installed"])
        self.assertTrue(result.artifacts[0].metadata["function_hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["module_hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["automatic_hook_installation"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/function-hooks.json")
        self.assertEqual(result.artifacts[2].path, "virtual://workspace/function-hook-timeline.json")
        self.assertEqual(result.artifacts[2].metadata["event_count"], 2)

    def test_native_web_runtime_refines_source_map_hook_candidates_without_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-hook-candidates",
            {
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "symbol_request": {"symbol_name": "buildSign", "original_source": "webpack://demo/src/sign.ts"},
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "scope_candidates": [
                        {
                            "kind": "source-map-name",
                            "symbol_name": "buildSign",
                            "original_source": "webpack://demo/src/sign.ts",
                            "generated_line_number": 4,
                            "generated_column_number": 0,
                            "strategy": "source_map_name",
                        }
                    ],
                    "scope_candidate_count": 1,
                    "hook_readiness": {"source_logpoint_reviewable": True},
                    "side_effect_policy": {"browser_started": False, "hook_installed": False, "calls_mcp": False},
                },
                "function_paths": ["window.buildSign"],
                "module_candidates": [{"module_id": "731", "export_names": ["buildSign"], "runtime_path": "window.__webpack_require__"}],
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["refine_source_map_hook_candidates"])
        self.assertIn("source_map_hook_candidates_status=ready_for_review", result.verification)
        self.assertIn("source_map_hook_candidates_candidate_count=2", result.verification)
        self.assertIn("source_map_hook_candidates_ready_for_install_review_count=2", result.verification)
        self.assertIn("source_map_hook_candidates_browser_started=False", result.verification)
        self.assertIn("source_map_hook_candidates_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_hook_candidates_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_hook_candidates_hook_installed=False", result.verification)
        self.assertIn("source_map_hook_candidates_automatic_hook_installation=False", result.verification)
        self.assertIn("source_map_hook_candidates_calls_mcp=False", result.verification)
        self.assertIn("source_map_hook_candidates_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_hook_candidates_before_selected_hook_install")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-hook-candidates.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-hook-candidates.v1")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 2)
        self.assertEqual(result.artifacts[0].metadata["ready_for_hook_install_review_count"], 2)
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_reviews_source_map_debugger_candidates_without_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-debugger-candidates",
            {
                "script_url": "https://example.test/assets/app.js",
                "bundler_symbol_scope": {
                    "status": "ready_for_review",
                    "script_url": "https://example.test/assets/app.js",
                    "symbol_request": {"symbol_name": "buildSign", "original_source": "webpack://demo/src/sign.ts"},
                    "bundler_classification": {"bundler_kind": "webpack"},
                    "scope_candidates": [
                        {
                            "kind": "source-map-name",
                            "symbol_name": "buildSign",
                            "original_source": "webpack://demo/src/sign.ts",
                            "generated_line_number": 4,
                            "generated_column_number": 0,
                            "strategy": "source_map_name",
                        }
                    ],
                    "scope_candidate_count": 1,
                    "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "calls_mcp": False},
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_debugger_candidates"])
        self.assertIn("source_map_debugger_candidates_status=ready_for_review", result.verification)
        self.assertIn("source_map_debugger_candidates_candidate_count=1", result.verification)
        self.assertIn("source_map_debugger_candidates_ready_for_location_review_count=1", result.verification)
        self.assertIn("source_map_debugger_candidates_browser_started=False", result.verification)
        self.assertIn("source_map_debugger_candidates_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_debugger_candidates_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_debugger_candidates_debugger_execution_performed=False", result.verification)
        self.assertIn("source_map_debugger_candidates_breakpoint_installed=False", result.verification)
        self.assertIn("source_map_debugger_candidates_automatic_debugger_continuation=False", result.verification)
        self.assertIn("source_map_debugger_candidates_calls_mcp=False", result.verification)
        self.assertIn("source_map_debugger_candidates_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_debugger_candidates_before_selected_debugger_apply")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-debugger-candidates.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-debugger-candidates.v1")
        self.assertEqual(result.artifacts[0].metadata["candidate_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["ready_for_debugger_location_review_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["debugger_execution_performed"])
        self.assertFalse(result.artifacts[0].metadata["breakpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])

    def test_native_web_runtime_selects_source_map_hook_candidate_without_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        candidates = {
            "schema_version": "reverse-deepagent.source-map-hook-candidates.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "ready_for_hook_install_review_count": 1,
            "review_only": True,
            "plan_only": True,
            "candidates": [
                {
                    "candidate_id": "source-map-hook-function:buildSign:4:0:0",
                    "candidate_kind": "source-map-function-symbol",
                    "hook_kind": "function",
                    "status": "ready_for_review",
                    "ready_for_hook_install_review": True,
                    "install_automatically": False,
                    "symbol_name": "buildSign",
                    "original_source": "webpack://demo/src/sign.ts",
                    "suggested_hook_install_input": {
                        "hook_kind": "function",
                        "function_name": "buildSign",
                        "function_paths": ["window.buildSign"],
                        "candidate_id": "source-map-hook-function:buildSign:4:0:0",
                        "cdp_command": None,
                        "install_supported_now": False,
                        "requires_explicit_review": True,
                    },
                }
            ],
            "side_effect_policy": {"browser_started": False, "runtime_evaluated": False, "hook_installed": False, "automatic_hook_installation": False},
        }
        result = runtime.apply_minimal_protection(
            "source-map-hook-candidate-selection",
            {
                "source_map_hook_candidates": candidates,
                "selected_candidate_id": "source-map-hook-function:buildSign:4:0:0",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["select_source_map_hook_candidate"])
        self.assertIn("source_map_hook_candidate_selection_status=ready_for_review", result.verification)
        self.assertIn("source_map_hook_candidate_selection_candidate_count=1", result.verification)
        self.assertIn("source_map_hook_candidate_selection_selected_candidate_id=source-map-hook-function:buildSign:4:0:0", result.verification)
        self.assertIn("source_map_hook_candidate_selection_ready_for_input_review=True", result.verification)
        self.assertIn("source_map_hook_candidate_selection_browser_started=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_hook_installed=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_automatic_hook_installation=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_calls_mcp=False", result.verification)
        self.assertIn("source_map_hook_candidate_selection_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "run_source_map_selected_executor_input_review_for_selected_hook_candidate")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-hook-candidate-selection.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-hook-candidate-selection.v1")
        self.assertTrue(result.artifacts[0].metadata["ready_for_selected_executor_input_review"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["automatic_hook_installation"])

    def test_native_web_runtime_reviews_selected_source_map_hook_candidate_input_aliases_without_browser(self) -> None:
        candidates = {
            "schema_version": "reverse-deepagent.source-map-hook-candidates.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "ready_for_hook_install_review_count": 1,
            "review_only": True,
            "plan_only": True,
            "candidates": [
                {
                    "candidate_id": "source-map-hook-function:buildSign:4:0:0",
                    "candidate_kind": "source-map-function-symbol",
                    "hook_kind": "function",
                    "status": "ready_for_review",
                    "ready_for_hook_install_review": True,
                    "install_automatically": False,
                    "symbol_name": "buildSign",
                    "suggested_hook_install_input": {
                        "hook_kind": "function",
                        "function_name": "buildSign",
                        "function_paths": ["window.buildSign"],
                        "candidate_id": "source-map-hook-function:buildSign:4:0:0",
                        "cdp_command": None,
                        "install_supported_now": False,
                        "requires_explicit_review": True,
                    },
                }
            ],
            "side_effect_policy": {"browser_started": False, "runtime_evaluated": False, "hook_installed": False, "automatic_hook_installation": False},
        }
        candidate_selection = SourceMapHookCandidateSelectionManager().review(
            SourceMapHookCandidateSelectionSpec.from_context(
                {
                    "source_map_hook_candidate_selection": True,
                    "source_map_hook_candidates": candidates,
                    "selected_candidate_id": "source-map-hook-function:buildSign:4:0:0",
                    "reviewer": "analyst",
                }
            )
        ).descriptor

        for protection_name in (
            "source-map-hook-candidate-selected-input-review",
            "source-map-hook-candidate-executor-input-review",
            "source-map-hook-candidate-selected-executor-input-review",
            "review-source-map-hook-candidate-selected-input",
        ):
            provider = FakeProvider()
            runtime = NativeWebRuntime(browser_provider=provider)
            result = runtime.apply_minimal_protection(
                protection_name,
                {"source_map_hook_candidate_selection": candidate_selection},
            )

            self.assertEqual(provider.started, 0)
            self.assertEqual(result.status.value, "success")
            self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_input"])
            self.assertIn("source_map_selected_executor_input_review_status=ready_for_review", result.verification)
            self.assertIn("source_map_selected_executor_input_review_selected_consumer=hook", result.verification)
            self.assertIn("source_map_selected_executor_input_review_selected_surface=review_hook_symbol_scope_executor_input", result.verification)
            self.assertIn("source_map_selected_executor_input_review_source_hook_candidate_selection_id=source-map-hook-function:buildSign:4:0:0", result.verification)
            self.assertIn("source_map_selected_executor_input_review_source_hook_candidate_selection_ready=True", result.verification)
            self.assertIn("source_map_selected_executor_input_review_package_ready=True", result.verification)
            self.assertIn("source_map_selected_executor_input_review_ready_for_executor_review=True", result.verification)
            self.assertIn("source_map_selected_executor_input_review_gate=explicit_hook_symbol_scope_review", result.verification)
            self.assertIn("source_map_selected_executor_input_review_browser_started=False", result.verification)
            self.assertIn("source_map_selected_executor_input_review_cdp_command_sent=False", result.verification)
            self.assertIn("source_map_selected_executor_input_review_runtime_evaluated=False", result.verification)
            self.assertIn("source_map_selected_executor_input_review_calls_mcp=False", result.verification)
            self.assertIn("source_map_selected_executor_input_review_mobile_runtime_used=False", result.verification)
            self.assertEqual(result.next_action, "review_hook_symbol_scope_before_runtime_hook")
            self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-input-review.json")
            self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "hook")
            self.assertEqual(result.artifacts[0].metadata["source_hook_candidate_selection_id"], "source-map-hook-function:buildSign:4:0:0")
            self.assertTrue(result.artifacts[0].metadata["source_hook_candidate_selection_ready"])
            self.assertEqual(result.artifacts[0].metadata["review_gate"], "explicit_hook_symbol_scope_review")
            self.assertTrue(result.artifacts[0].metadata["ready_for_executor_review"])
            self.assertFalse(result.artifacts[0].metadata["browser_started"])
            self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
            self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])

    def test_native_web_runtime_selects_source_map_debugger_candidate_without_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        candidates = {
            "schema_version": "reverse-deepagent.source-map-debugger-candidates.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "ready_for_debugger_location_review_count": 1,
            "review_only": True,
            "plan_only": True,
            "candidates": [
                {
                    "candidate_id": "source-map-debugger:buildSign",
                    "candidate_kind": "source-map-symbol-generated-location",
                    "status": "ready_for_review",
                    "ready_for_debugger_location_review": True,
                    "apply_automatically": False,
                    "suggested_debugger_location_input": {
                        "url_pattern": "https://example.test/assets/app.js",
                        "line_number": 4,
                        "column_number": 0,
                        "source": "webpack://demo/src/sign.ts",
                        "mapping_strategy": "source_map_name",
                        "candidate_id": "source-map-debugger:buildSign",
                        "cdp_command": None,
                        "requires_explicit_review": True,
                    },
                }
            ],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "debugger_execution_performed": False},
        }
        result = runtime.apply_minimal_protection(
            "source-map-debugger-candidate-selection",
            {
                "source_map_debugger_candidates": candidates,
                "selected_candidate_id": "source-map-debugger:buildSign",
                "reviewer": "analyst",
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["select_source_map_debugger_candidate"])
        self.assertIn("source_map_debugger_candidate_selection_status=ready_for_review", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_candidate_count=1", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_selected_candidate_id=source-map-debugger:buildSign", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_ready_for_input_review=True", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_browser_started=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_debugger_execution_performed=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_breakpoint_installed=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_automatic_debugger_continuation=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_calls_mcp=False", result.verification)
        self.assertIn("source_map_debugger_candidate_selection_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "run_source_map_selected_executor_input_review_for_selected_debugger_candidate")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-debugger-candidate-selection.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-debugger-candidate-selection.v1")
        self.assertTrue(result.artifacts[0].metadata["ready_for_selected_executor_input_review"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["debugger_execution_performed"])
        self.assertFalse(result.artifacts[0].metadata["breakpoint_installed"])

    def test_native_web_runtime_reviews_selected_source_map_debugger_candidate_input_without_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        candidates = {
            "schema_version": "reverse-deepagent.source-map-debugger-candidates.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "ready_for_debugger_location_review_count": 1,
            "review_only": True,
            "plan_only": True,
            "candidates": [
                {
                    "candidate_id": "source-map-debugger:buildSign",
                    "candidate_kind": "source-map-symbol-generated-location",
                    "status": "ready_for_review",
                    "ready_for_debugger_location_review": True,
                    "apply_automatically": False,
                    "suggested_debugger_location_input": {
                        "url_pattern": "https://example.test/assets/app.js",
                        "line_number": 4,
                        "column_number": 0,
                        "source": "webpack://demo/src/sign.ts",
                        "mapping_strategy": "source_map_name",
                        "candidate_id": "source-map-debugger:buildSign",
                        "cdp_command": None,
                        "requires_explicit_review": True,
                    },
                }
            ],
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "debugger_execution_performed": False},
        }
        selection_result = runtime.apply_minimal_protection(
            "source-map-debugger-candidate-selection",
            {
                "source_map_debugger_candidates": candidates,
                "selected_candidate_id": "source-map-debugger:buildSign",
                "reviewer": "analyst",
            },
        )
        candidate_selection = SourceMapDebuggerCandidateSelectionManager().review(
            SourceMapDebuggerCandidateSelectionSpec.from_context(
                {
                    "source_map_debugger_candidate_selection": True,
                    "source_map_debugger_candidates": candidates,
                    "selected_candidate_id": "source-map-debugger:buildSign",
                    "reviewer": "analyst",
                }
            )
        ).descriptor

        result = runtime.apply_minimal_protection(
            "source-map-debugger-candidate-selected-input-review",
            {"source_map_debugger_candidate_selection": candidate_selection},
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(selection_result.status.value, "success")
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["review_source_map_selected_executor_input"])
        self.assertIn("source_map_selected_executor_input_review_status=ready_for_review", result.verification)
        self.assertIn("source_map_selected_executor_input_review_selected_consumer=debugger", result.verification)
        self.assertIn("source_map_selected_executor_input_review_selected_surface=review_debugger_location_executor_input", result.verification)
        self.assertIn("source_map_selected_executor_input_review_source_debugger_candidate_selection_id=source-map-debugger:buildSign", result.verification)
        self.assertIn("source_map_selected_executor_input_review_source_debugger_candidate_selection_ready=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_package_ready=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_ready_for_executor_review=True", result.verification)
        self.assertIn("source_map_selected_executor_input_review_gate=explicit_debugger_location_review", result.verification)
        self.assertIn("source_map_selected_executor_input_review_browser_started=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_calls_mcp=False", result.verification)
        self.assertIn("source_map_selected_executor_input_review_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "review_debugger_location_before_cdp_command")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-selected-executor-input-review.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["source_debugger_candidate_selection_id"], "source-map-debugger:buildSign")
        self.assertTrue(result.artifacts[0].metadata["source_debugger_candidate_selection_ready"])
        self.assertEqual(result.artifacts[0].metadata["review_gate"], "explicit_debugger_location_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_executor_review"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])

    def test_native_web_runtime_blocks_source_map_hook_without_review_before_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-hook-application",
            {
                "mode": "dry-run",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_hook_apply_preflight(),
                "source_map_hook_install_input": {
                    "hook_kind": "function",
                    "function_name": "buildSign",
                    "function_paths": ["window.buildSign"],
                    "cdp_command": None,
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertTrue(any("source_map_hook_application_requires_apply_mode" in item for item in result.verification))
        self.assertIn("source_map_hook_application_blockers=source_map_hook_application_requires_apply_mode,source_map_hook_application_review_not_approved,source_map_hook_install_not_approved,source_map_hook_reviewer_missing", result.verification)
        self.assertEqual(result.next_action, "approve_source_map_hook_install_before_apply")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-hook-install-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["hook_installed"])
        self.assertFalse(result.artifacts[0].metadata["surface_executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])

    def test_native_web_runtime_applies_reviewed_source_map_debugger_location(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-debugger-application",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_map_debugger_action": True,
                "reviewer": "reviewer-1",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_debugger_apply_preflight(),
                "source_map_debugger_location_input": {
                    "location": {
                        "source": "src/sign.ts",
                        "line_number": 4,
                        "column_number": 0,
                        "mapping_strategy": "source_map_generated_exact",
                    },
                    "url_pattern": ".*app\.js$",
                    "line_number": 4,
                    "column_number": 0,
                    "cdp_command": None,
                    "requires_review_before_debugger_use": True,
                    "trigger_expression": "setTimeout(() => { debugger; }, 0); 'scheduled'",
                    "debugger_actions": ["step_over"],
                },
            },
        )

        self.assertEqual(provider.started, 1)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["apply_source_map_debugger_location:.*app\.js$:4", "capture_debugger_paused"])
        self.assertIn("source_map_debugger_application_status=success", result.verification)
        self.assertIn("source_map_debugger_application_breakpoint_count=1", result.verification)
        self.assertIn("source_map_debugger_application_paused_status=success", result.verification)
        self.assertIn("source_map_debugger_application_callframe_count=1", result.verification)
        self.assertIn("source_map_debugger_application_debugger_action_count=1", result.verification)
        self.assertIn("source_map_debugger_application_browser_started=True", result.verification)
        self.assertIn("source_map_debugger_application_runtime_evaluated=True", result.verification)
        self.assertIn("source_map_debugger_application_cdp_command_sent=True", result.verification)
        self.assertIn("source_map_debugger_application_debugger_location_applied=True", result.verification)
        self.assertIn("source_map_debugger_application_calls_mcp=False", result.verification)
        self.assertIn("source_map_debugger_application_mobile_runtime_used=False", result.verification)
        self.assertEqual(result.next_action, "inspect_source_map_debugger_execution_artifacts")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-debugger-execution-result.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-debugger-execution-result.v1")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "debugger")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_debugger_location_review")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertTrue(result.artifacts[0].metadata["approve_source_map_debugger_action"])
        self.assertTrue(result.artifacts[0].metadata["browser_started"])
        self.assertTrue(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertTrue(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertTrue(result.artifacts[0].metadata["debugger_location_applied"])
        self.assertFalse(result.artifacts[0].metadata["automatic_continuation"])
        self.assertFalse(result.artifacts[0].metadata["automatic_loop"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])
        paths = [artifact.path for artifact in result.artifacts]
        self.assertIn("virtual://workspace/breakpoints.json", paths)
        self.assertIn("virtual://workspace/debugger-paused.json", paths)
        self.assertIn("virtual://workspace/callframes.json", paths)
        self.assertIn("virtual://workspace/debugger-actions.json", paths)
        page = provider.session.context.pages[0]
        self.assertIn(("Debugger.enable", {}), page._cdp_session.calls)
        self.assertIn(("Debugger.setBreakpointByUrl", {"urlRegex": ".*app\.js$", "lineNumber": 4, "columnNumber": 0}), page._cdp_session.calls)
        self.assertIn(("Debugger.stepOver", {}), page._cdp_session.calls)

    def test_native_web_runtime_blocks_source_map_debugger_without_review_before_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-debugger-application",
            {
                "mode": "dry-run",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_debugger_apply_preflight(),
                "source_map_debugger_location_input": {
                    "location": {"source": "src/sign.ts", "line_number": 4, "column_number": 0},
                    "url_pattern": ".*app\.js$",
                    "line_number": 4,
                    "cdp_command": None,
                    "requires_review_before_debugger_use": True,
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertTrue(any("source_map_debugger_application_requires_apply_mode" in item for item in result.verification))
        self.assertIn("source_map_debugger_application_browser_started=False", result.verification)
        self.assertEqual(result.next_action, "approve_source_map_debugger_location_before_apply")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-debugger-execution-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["debugger_location_applied"])
        self.assertFalse(result.artifacts[0].metadata["surface_executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])

    def test_native_web_runtime_applies_reviewed_source_map_rebuild_metadata(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-rebuild-metadata-application",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_map_rebuild_metadata": True,
                "reviewer": "reviewer-1",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_rebuild_apply_preflight(),
                "rebuild_source_metadata_input": {
                    "source_content_digest": "abc123",
                    "source_content_available": True,
                    "raw_source_content": None,
                    "raw_content_exported": False,
                    "preview_exported": False,
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["apply_source_map_rebuild_metadata:abc123"])
        self.assertIn("source_map_rebuild_metadata_application_status=success", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_metadata_only=True", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_rebuild_metadata_applied=True", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_browser_started=False", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_cdp_command_sent=False", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_runtime_evaluated=False", result.verification)
        self.assertIn("source_map_rebuild_metadata_application_rebuild_bundle_generated=False", result.verification)
        self.assertEqual(result.next_action, "review_source_map_rebuild_metadata_result_before_rebuild_generation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-rebuild-result.json")
        self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-rebuild-result.v1")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "rebuild")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_rebuild_source_metadata_review")
        self.assertEqual(result.artifacts[0].metadata["source_content_digest"], "abc123")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertTrue(result.artifacts[0].metadata["approve_source_map_rebuild_metadata"])
        self.assertTrue(result.artifacts[0].metadata["metadata_only"])
        self.assertTrue(result.artifacts[0].metadata["rebuild_metadata_applied"])
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
        self.assertFalse(result.artifacts[0].metadata["preview_exported"])
        self.assertFalse(result.artifacts[0].metadata["raw_source_content_included"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_bundle_generated"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])

    def test_native_web_runtime_blocks_source_map_rebuild_metadata_without_review_before_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-rebuild-metadata-application",
            {
                "mode": "dry-run",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_rebuild_apply_preflight(),
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertTrue(
            any("source_map_rebuild_metadata_application_requires_apply_mode" in item for item in result.verification)
        )
        self.assertEqual(result.next_action, "approve_source_map_rebuild_metadata_before_apply")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-rebuild-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["surface_executor_invoked"])
        self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])

    def test_native_web_runtime_generates_reviewed_source_map_rebuild_bundle(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        task_card, final_result = self._source_map_rebuild_generation_inputs()
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir) / "artifacts"
            result = runtime.apply_minimal_protection(
                "source-map-rebuild-generation",
                {
                    "mode": "apply",
                    "review_approved": True,
                    "approve_source_map_rebuild_generation": True,
                    "reviewer": "reviewer-1",
                    "artifact_root": str(artifact_root),
                    "source_map_rebuild_result": self._successful_source_map_rebuild_metadata_result(),
                    "task_card": task_card,
                    "final_result": final_result,
                },
            )

            self.assertEqual(provider.started, 0)
            self.assertEqual(result.status.value, "success")
            self.assertEqual(result.applied_actions, ["generate_source_map_rebuild_bundle:abc123"])
            self.assertIn("source_map_rebuild_generation_status=success", result.verification)
            self.assertIn("source_map_rebuild_generation_rebuild_bundle_generated=True", result.verification)
            self.assertIn("source_map_rebuild_generation_rebuild_executed=True", result.verification)
            self.assertIn("source_map_rebuild_generation_browser_started=False", result.verification)
            self.assertIn("source_map_rebuild_generation_runtime_evaluated=False", result.verification)
            self.assertIn("source_map_rebuild_generation_cdp_command_sent=False", result.verification)
            self.assertIn("source_map_rebuild_generation_source_map_fetched=False", result.verification)
            self.assertIn("source_map_rebuild_generation_calls_mcp=False", result.verification)
            self.assertIn("source_map_rebuild_generation_mobile_runtime_used=False", result.verification)
            self.assertEqual(result.next_action, "review_generated_rebuild_bundle_before_delivery")
            self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-rebuild-generation-result.json")
            self.assertEqual(result.artifacts[0].metadata["schema_version"], "reverse-deepagent.source-map-rebuild-generation-result.v1")
            self.assertEqual(result.artifacts[0].metadata["status"], "success")
            self.assertTrue(result.artifacts[0].metadata["metadata_result_verified"])
            self.assertEqual(result.artifacts[0].metadata["source_content_digest"], "abc123")
            self.assertTrue(result.artifacts[0].metadata["review_approved"])
            self.assertTrue(result.artifacts[0].metadata["approve_source_map_rebuild_generation"])
            self.assertFalse(result.artifacts[0].metadata["metadata_only"])
            self.assertTrue(result.artifacts[0].metadata["rebuild_metadata_applied"])
            self.assertTrue(result.artifacts[0].metadata["rebuild_bundle_generated"])
            self.assertTrue(result.artifacts[0].metadata["rebuild_executed"])
            self.assertFalse(result.artifacts[0].metadata["browser_started"])
            self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
            self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
            self.assertFalse(result.artifacts[0].metadata["source_map_fetched"])
            self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
            self.assertFalse(result.artifacts[0].metadata["preview_exported"])
            self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
            self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])
            self.assertEqual(result.artifacts[0].metadata["algorithm_strategy_id"], "md5_keyword_timestamp")
            self.assertGreaterEqual(result.artifacts[0].metadata["generated_file_count"], 4)
            self.assertTrue((artifact_root / "workspace" / "rebuild-plan.json").exists())
            self.assertTrue((artifact_root / "rebuild" / "sign_rebuild.py").exists())

    def test_native_web_runtime_blocks_source_map_rebuild_generation_without_review_before_writes(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_root = Path(tmpdir) / "artifacts"
            result = runtime.apply_minimal_protection(
                "source-map-rebuild-generation",
                {
                    "mode": "dry-run",
                    "artifact_root": str(artifact_root),
                    "source_map_rebuild_result": self._successful_source_map_rebuild_metadata_result(),
                },
            )

            self.assertEqual(provider.started, 0)
            self.assertFalse(artifact_root.exists())
            self.assertEqual(result.status.value, "partial")
            self.assertEqual(result.applied_actions, [])
            self.assertTrue(any("source_map_rebuild_generation_requires_apply_mode" in item for item in result.verification))
            self.assertEqual(result.next_action, "approve_source_map_rebuild_generation_before_apply")
            self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-rebuild-generation-result.json")
            self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
            self.assertFalse(result.artifacts[0].metadata["rebuild_bundle_generated"])
            self.assertFalse(result.artifacts[0].metadata["rebuild_executed"])
            self.assertFalse(result.artifacts[0].metadata["browser_started"])
            self.assertFalse(result.artifacts[0].metadata["runtime_evaluated"])
            self.assertFalse(result.artifacts[0].metadata["cdp_command_sent"])
            self.assertFalse(result.artifacts[0].metadata["source_map_fetched"])
            self.assertFalse(result.artifacts[0].metadata["raw_source_content_exported"])
            self.assertFalse(result.artifacts[0].metadata["preview_exported"])
            self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
            self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])

    def test_native_web_runtime_applies_reviewed_source_map_source_logpoint_install(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_logpoint_install": True,
                "reviewer": "reviewer-1",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_source_logpoint_apply_preflight(),
                "source_logpoint_install_input": {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 7,
                    "column_number": 0,
                    "log_expression": "window.buildSign('sign', 1700000000000)",
                    "label": "smoke",
                    "trigger_expression": "window.buildSign('sign', 1700000000000)",
                },
            },
        )

        self.assertEqual(provider.started, 1)
        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["install_source_map_source_logpoint:.*app\\.js$:7"])
        self.assertIn("source_map_source_logpoint_application_status=success", result.verification)
        self.assertIn("source_map_source_logpoint_application_breakpoint_count=1", result.verification)
        self.assertIn("source_map_source_logpoint_application_event_count=1", result.verification)
        self.assertIn("source_map_source_logpoint_application_logpoint_installed=True", result.verification)
        self.assertEqual(result.next_action, "inspect_source_map_source_logpoint_events")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-source-logpoint-install-result.json")
        self.assertEqual(result.artifacts[0].metadata["selected_consumer"], "source-logpoint")
        self.assertEqual(result.artifacts[0].metadata["selected_review_gate"], "explicit_source_logpoint_install_review")
        self.assertTrue(result.artifacts[0].metadata["review_approved"])
        self.assertTrue(result.artifacts[0].metadata["approve_source_logpoint_install"])
        self.assertTrue(result.artifacts[0].metadata["browser_started"])
        self.assertTrue(result.artifacts[0].metadata["runtime_evaluated"])
        self.assertTrue(result.artifacts[0].metadata["cdp_command_sent"])
        self.assertTrue(result.artifacts[0].metadata["logpoint_installed"])
        self.assertFalse(result.artifacts[0].metadata["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["mobile_runtime_used"])
        self.assertEqual(result.artifacts[1].path, "virtual://workspace/source-logpoints.json")
        self.assertEqual(result.artifacts[2].path, "virtual://workspace/source-logpoint-timeline.json")
        self.assertEqual(result.artifacts[2].metadata["event_count"], 1)

    def test_native_web_runtime_blocks_source_map_source_logpoint_install_without_review_before_browser(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "dry-run",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_source_logpoint_apply_preflight(),
                "source_logpoint_install_input": {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 7,
                    "log_expression": "window.buildSign('sign', 1700000000000)",
                },
            },
        )

        self.assertEqual(provider.started, 0)
        self.assertEqual(result.status.value, "partial")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("source_map_source_logpoint_application_requires_apply_mode", result.verification[-2])
        self.assertEqual(result.next_action, "approve_source_map_source_logpoint_install_before_apply")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/source-map-source-logpoint-install-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "blocked")
        self.assertFalse(result.artifacts[0].metadata["browser_started"])
        self.assertFalse(result.artifacts[0].metadata["logpoint_installed"])

    def test_native_web_runtime_source_logpoint_applies_with_bundle_offset_remap(self) -> None:
        """Source-logpoint with bundle_offset remap: remap metadata captured in artifact."""
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_logpoint_install": True,
                "reviewer": "alice",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_source_logpoint_apply_preflight(),
                "source_logpoint_install_input": {
                    "url_pattern": ".*bundle\\.js$",
                    "line_number": 0,
                    "column_number": 1234,
                    "log_expression": "window.__sign",
                    "label": "remap-test",
                    "bundle_offset": 1234,
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("source_map_source_logpoint_application_logpoint_installed=True", result.verification)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.path, "virtual://workspace/source-map-source-logpoint-install-result.json")
        self.assertTrue(artifact.metadata["logpoint_installed"])
        self.assertTrue(artifact.metadata["cdp_command_sent"])
        self.assertEqual(provider.started, 1)

    def test_native_web_runtime_source_logpoint_returns_failed_on_provider_unavailable(self) -> None:
        """When browser provider raises on ensure_browser_session, result is failed with no CDP sent."""
        from reverse_deepagent.browser import BrowserProviderUnavailableError
        class UnavailableProvider(FakeProvider):
            def start(self) -> None:
                raise BrowserProviderUnavailableError("test_unavailable")
        provider = UnavailableProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_logpoint_install": True,
                "reviewer": "alice",
                "source_map_selected_executor_apply_preflight": self._ready_source_map_source_logpoint_apply_preflight(),
                "source_logpoint_install_input": {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 5,
                    "log_expression": "window.__sign",
                },
            },
        )

        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.applied_actions, [])
        self.assertIn("ensure_browser_provider", result.next_action)

    def test_native_web_runtime_source_logpoint_names_remap_captured_in_verification(self) -> None:
        """Source-logpoint install with names_count > 0 is reflected in verification metadata."""
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = self._ready_source_map_source_logpoint_apply_preflight()
        # Inject a non-zero names_count to simulate a source map with `names` table
        preflight["source_map_metadata"] = {"names_count": 5, "sources_count": 1}
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_logpoint_install": True,
                "reviewer": "alice",
                "source_map_selected_executor_apply_preflight": preflight,
                "source_logpoint_install_input": {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 7,
                    "log_expression": "window.__sign",
                    "label": "names-test",
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("source_map_source_logpoint_application_logpoint_installed=True", result.verification)
        artifact = result.artifacts[0]
        self.assertTrue(artifact.metadata["logpoint_installed"])
        self.assertTrue(artifact.metadata["cdp_command_sent"])

    def test_native_web_runtime_source_logpoint_sources_content_digest_in_artifact(self) -> None:
        """When sources_content_available is set in preflight, artifact records it as metadata."""
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        preflight = self._ready_source_map_source_logpoint_apply_preflight()
        preflight["sources_content_available"] = True
        preflight["sources_content_digest"] = "sha256:abc123"
        result = runtime.apply_minimal_protection(
            "source-map-source-logpoint-install",
            {
                "mode": "apply",
                "review_approved": True,
                "approve_source_logpoint_install": True,
                "reviewer": "alice",
                "source_map_selected_executor_apply_preflight": preflight,
                "source_logpoint_install_input": {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 7,
                    "log_expression": "window.__sign",
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        artifact = result.artifacts[0]
        self.assertTrue(artifact.metadata["logpoint_installed"])
        # The artifact path and core fields must be present regardless of
        # whether the preflight contains optional sources_content metadata.
        self.assertEqual(artifact.path, "virtual://workspace/source-map-source-logpoint-install-result.json")

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

    def test_native_web_runtime_preflights_durable_paused_session_live_continuation_without_action(self) -> None:
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
                    "pause_session_id": "native-durable-live-preflight",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                },
            )
            self.assertEqual(initial.status.value, "success")
            page = provider.session.context.pages[0]
            call_count = len(page._cdp_session.calls)

            BreakpointManager.clear_paused_sessions()
            follow_up = runtime.apply_minimal_protection(
                "paused-session-live-continuation-preflight",
                {
                    "pause_session_id": "native-durable-live-preflight",
                    "requested_action": "resume",
                    "paused_session_store_dir": tmpdir,
                },
            )

            self.assertEqual(follow_up.status.value, "partial")
            self.assertEqual(follow_up.applied_actions, ["preflight_paused_session_live_continuation"])
            self.assertEqual(follow_up.next_action, "reproduce_pause_in_current_process_before_live_action")
            self.assertIn("paused_session_live_preflight_status=blocked", follow_up.verification)
            self.assertIn("paused_session_live_preflight_source=durable_snapshot", follow_up.verification)
            self.assertIn("paused_session_live_preflight_live_continuation_available=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_cross_process_live_continuation_supported=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_live_session_available=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_same_process_required=True", follow_up.verification)
            self.assertIn("paused_session_live_preflight_stable_callframe_required=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_browser_resumed=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_debugger_stepped=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_callframe_evaluated=False", follow_up.verification)
            self.assertIn("paused_session_live_preflight_cdp_command_sent=False", follow_up.verification)
            self.assertTrue(any(item.startswith("paused_session_live_preflight_blockers=live_paused_session_required") for item in follow_up.verification))
            self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/paused-session-live-continuation-preflight.json")
            self.assertEqual(follow_up.artifacts[0].metadata["source"], "durable_snapshot")
            self.assertFalse(follow_up.artifacts[0].metadata["live_continuation_available"])
            self.assertFalse(follow_up.artifacts[0].metadata["cross_process_live_continuation_supported"])
            self.assertFalse(follow_up.artifacts[0].metadata["live_session_diagnostics"]["live_session_available"])
            self.assertEqual(follow_up.artifacts[0].metadata["target_diagnostics"]["target_attached_source"], "not_attached")
            self.assertFalse(follow_up.artifacts[0].metadata["action_capability"]["resume_supported"])
            self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_native_web_runtime_preflights_same_process_paused_session_without_resuming(self) -> None:
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
                "pause_session_id": "native-same-process-live-preflight",
            },
        )
        self.assertEqual(initial.status.value, "success")
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        follow_up = runtime.apply_minimal_protection(
            "paused-session-live-continuation-preflight",
            {
                "pause_session_id": "native-same-process-live-preflight",
                "requested_action": "resume",
            },
        )

        self.assertEqual(follow_up.status.value, "success")
        self.assertEqual(follow_up.applied_actions, ["preflight_paused_session_live_continuation"])
        self.assertEqual(follow_up.next_action, "continue_with_same_process_paused_session_action")
        self.assertIn("paused_session_live_preflight_status=live_available", follow_up.verification)
        self.assertIn("paused_session_live_preflight_source=registry", follow_up.verification)
        self.assertIn("paused_session_live_preflight_same_process_registry=True", follow_up.verification)
        self.assertIn("paused_session_live_preflight_live_continuation_available=True", follow_up.verification)
        self.assertIn("paused_session_live_preflight_cross_process_live_continuation_supported=False", follow_up.verification)
        self.assertIn("paused_session_live_preflight_live_session_available=True", follow_up.verification)
        self.assertIn("paused_session_live_preflight_target_diagnostic_source=same_process_registry", follow_up.verification)
        self.assertIn("paused_session_live_preflight_action_is_live=True", follow_up.verification)
        self.assertIn("paused_session_live_preflight_browser_resumed=False", follow_up.verification)
        self.assertIn("paused_session_live_preflight_cdp_command_sent=False", follow_up.verification)
        self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/paused-session-live-continuation-preflight.json")
        self.assertTrue(follow_up.artifacts[0].metadata["live_continuation_available"])
        self.assertTrue(follow_up.artifacts[0].metadata["live_session_diagnostics"]["live_session_available"])
        self.assertTrue(follow_up.artifacts[0].metadata["target_diagnostics"]["target_attached"])
        self.assertTrue(follow_up.artifacts[0].metadata["action_capability"]["resume_supported"])
        self.assertIn("native-same-process-live-preflight", BreakpointManager._paused_sessions)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_native_web_runtime_assesses_paused_session_target_attach_readiness_without_attaching(self) -> None:
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
                    "pause_session_id": "native-attach-ready",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                },
            )
            self.assertEqual(initial.status.value, "success")
            page = provider.session.context.pages[0]
            call_count = len(page._cdp_session.calls)

            BreakpointManager.clear_paused_sessions()
            follow_up = runtime.apply_minimal_protection(
                "paused-session-target-attach-readiness",
                {
                    "pause_session_id": "native-attach-ready",
                    "requested_action": "evaluate",
                    "paused_session_store_dir": tmpdir,
                    "target_candidates": [
                        {
                            "targetId": "target-native-1",
                            "type": "page",
                            "url": "https://example.test/assets/app.js",
                        }
                    ],
                },
            )

            self.assertEqual(follow_up.status.value, "success")
            self.assertEqual(follow_up.applied_actions, ["assess_paused_session_target_attach_readiness"])
            self.assertEqual(follow_up.next_action, "review_target_attach_plan_before_cross_process_continuation_executor")
            self.assertIn("paused_session_target_attach_readiness_status=ready_for_attach_review", follow_up.verification)
            self.assertIn("paused_session_target_attach_readiness_source=durable_snapshot", follow_up.verification)
            self.assertIn("paused_session_target_attach_readiness_proven=True", follow_up.verification)
            self.assertIn("paused_session_target_attach_cross_process_execution_ready=False", follow_up.verification)
            self.assertIn("paused_session_target_attach_cross_process_live_continuation_supported=False", follow_up.verification)
            self.assertIn("paused_session_target_attach_would_attach_cdp_target=False", follow_up.verification)
            self.assertIn("paused_session_target_attach_cdp_command_sent=False", follow_up.verification)
            self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/paused-session-target-attach-readiness.json")
            self.assertTrue(follow_up.artifacts[0].metadata["target_attach_readiness_proven"])
            self.assertFalse(follow_up.artifacts[0].metadata["cross_process_execution_ready"])
            self.assertEqual(follow_up.artifacts[0].metadata["target_correlation"]["selected_target"]["target_id"], "target-native-1")
            self.assertFalse(follow_up.artifacts[0].metadata["attachability"]["would_attach_cdp_target"])
            self.assertFalse(follow_up.artifacts[0].metadata["callframe_recovery"]["durable_callframe_id_reusable"])
            self.assertEqual(len(page._cdp_session.calls), call_count)



    def test_paused_session_live_callframe_recovery_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-live-callframe-recovery",
            {
                "paused_session_live_callframe_recovery": True,
                "fresh_paused_event_after_attach": True,
                "paused_session_cross_process_attach_probe": {
                    "probe": {
                        "status": "attached",
                        "pause_session_id": "native-recover-1",
                        "requested_action": "evaluate",
                        "target_id": "target-native-recover-1",
                        "target_attached": True,
                        "attached_session_id": "attached-session-1",
                        "target_detached": True,
                    }
                },
                "debugger_paused": {
                    "callFrames": [
                        {
                            "callFrameId": "native-live-cf-1",
                            "functionName": "buildSign",
                            "url": "https://example.test/assets/app.js",
                            "location": {"lineNumber": 4, "columnNumber": 0},
                        }
                    ]
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-live-callframe-recovery.json")
        self.assertIn("paused_session_live_callframe_recovery_status=recovered", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_target_attached=True", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_fresh_paused_event_after_attach=True", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_selected_callframe_has_id=True", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_live_callframe_recovered=True", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_debugger_domain_enabled=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_live_action_executed=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_browser_resumed=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_debugger_stepped=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_calls_mcp=False", result.verification)
        self.assertIn("paused_session_live_callframe_recovery_mobile_runtime_used=False", result.verification)
        self.assertTrue(result.artifacts[0].metadata["live_callframe_recovered"])
        self.assertTrue(result.artifacts[0].metadata["one_action_executor_ready_for_review"])
        self.assertEqual(len(page._cdp_session.calls), call_count)


    def test_paused_session_next_paused_event_capture_plan_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-next-paused-event-capture-plan",
            {
                "paused_session_next_paused_event_capture_plan": True,
                "paused_session_cross_process_one_action_execution": {
                    "execution": {
                        "status": "executed",
                        "pause_session_id": "native-next-pause",
                        "requested_action": "step_over",
                        "method": "Debugger.stepOver",
                        "target_id": "target-native-next-pause",
                        "attached_session_id": "attached-session-1",
                        "live_action_executed": True,
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_next_paused_event_capture_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-next-paused-event-capture-plan.json")
        self.assertTrue(result.artifacts[0].metadata["requires_next_paused_event_capture"])
        self.assertTrue(result.artifacts[0].metadata["plan_ready_for_review"])
        self.assertFalse(result.artifacts[0].metadata["automatic_capture_supported"])
        self.assertIn("paused_session_next_paused_event_capture_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_plan_event_subscribed=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_plan_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_next_paused_event_capture_execution_from_native_runtime_captures_event(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-next-paused-event-capture-execution",
            {
                "paused_session_next_paused_event_capture_execution": True,
                "execute_next_paused_event_capture": True,
                "review_approved": True,
                "paused_session_next_paused_event_capture_plan": {
                    "status": "ready_for_review",
                    "plan_ready_for_review": True,
                    "requires_next_paused_event_capture": True,
                    "method": "Debugger.stepOver",
                    "pause_session_id": "native-next-capture",
                    "target_id": "target-native-next-capture",
                    "attached_session_id": "attached-session-1",
                    "timeout_ms": 10,
                },
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-live-cf-2",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 6, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["capture_next_paused_event"])
        self.assertEqual(result.next_action, "recover_live_callframe_from_captured_pause")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-next-paused-event-capture-execution.json")
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertEqual(result.artifacts[0].metadata["callframe_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["live_callframe_recovery_ready"])
        self.assertIn("paused_session_next_paused_event_capture_execution_status=captured", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_event_subscribed=True", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_browser_resumed=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_debugger_stepped=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_next_paused_event_capture_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_pre_action_subscribe_and_action_from_native_runtime_captures_event(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-pre-action-subscribe-and-action",
            {
                "paused_session_pre_action_subscribe_and_action": True,
                "execute_pre_action_subscribe_and_action": True,
                "review_approved": True,
                "requested_action": "step_over",
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-pre-action-1",
                        "target_id": "target-native-pre-action-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-live-cf-pre-action-1",
                        "live_callframe_recovered": True,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-live-cf-pre-action-1",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-live-cf-pre-action-2",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 7, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["pre_action_subscribe_and_action"])
        self.assertEqual(result.next_action, "checkpoint_cross_process_continuation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-pre-action-subscribe-and-action.json")
        self.assertTrue(result.artifacts[0].metadata["pre_action_event_subscribed"])
        self.assertTrue(result.artifacts[0].metadata["action_sent_after_subscription"])
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertEqual(result.artifacts[0].metadata["callframe_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["live_callframe_recovery_ready"])
        self.assertIn("paused_session_pre_action_subscribe_and_action_status=captured", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_pre_subscribed=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_action_after_subscription=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_event_subscribed=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_debugger_stepped=True", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_multi_step_continuation=False", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_calls_mcp=False", result.verification)
        self.assertIn("paused_session_pre_action_subscribe_and_action_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_paused_session_multi_step_continuation_execution_from_native_runtime_runs_one_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-multi-step-continuation-execution",
            {
                "paused_session_multi_step_continuation_execution": True,
                "execute_paused_session_continuation_iteration": True,
                "review_approved": True,
                "selected_step_index": 1,
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-exec-workflow-1",
                        "planned_steps": [
                            {"step_index": 1, "requested_action": "step_over", "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"}
                        ],
                        "duplicate_fingerprints": [],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-exec-pause-1",
                        "target_id": "native-exec-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-exec-cf-1",
                        "live_callframe_recovered": True,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-exec-cf-1",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-exec-cf-2",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 9, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["multi_step_continuation_iteration"])
        self.assertEqual(result.next_action, "checkpoint_cross_process_continuation")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-multi-step-continuation-execution.json")
        self.assertEqual(result.artifacts[0].metadata["selected_step_index"], 1)
        self.assertEqual(result.artifacts[0].metadata["selected_method"], "Debugger.stepOver")
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertTrue(result.artifacts[0].metadata["manual_checkpoint_required_after_step"])
        self.assertIn("paused_session_multi_step_continuation_execution_status=executed", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_event_subscribed=True", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_multi_step_executed=True", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_automatic_loop=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_paused_session_multi_step_continuation_workflow_from_native_runtime_is_review_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-multi-step-continuation-workflow",
            {
                "paused_session_multi_step_continuation_workflow": True,
                "workflow_id": "native-workflow-1",
                "max_planned_steps": 2,
                "planned_actions": ["step_over", "step_out"],
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-workflow-pause-1",
                        "target_id": "native-workflow-target-1",
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovered": True,
                    }
                },
                "attached_session_id": "attached-session-1",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "approve_multi_step_continuation_workflow")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-multi-step-continuation-workflow.json")
        self.assertEqual(result.artifacts[0].metadata["planned_step_count"], 2)
        self.assertTrue(result.artifacts[0].metadata["manual_checkpoint_required_after_each_step"])
        self.assertTrue(result.artifacts[0].metadata["execute_at_most_one_action_per_review"])
        self.assertIn("paused_session_multi_step_continuation_workflow_status=ready_for_review", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_step_count=2", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_event_subscribed=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_calls_mcp=False", result.verification)
        self.assertIn("paused_session_multi_step_continuation_workflow_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_readiness_from_native_runtime_is_review_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-readiness",
            {
                "paused_session_automatic_loop_readiness": True,
                "max_automatic_iterations": 2,
                "paused_session_cross_process_session_lifecycle": {
                    "lifecycle": {"status": "ready_for_review", "pause_session_id": "native-auto-pause-1", "target_id": "native-auto-target-1"}
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-auto-workflow-1",
                        "planned_steps": [
                            {"step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver"},
                            {"step_index": 2, "method": "Debugger.stepOut", "fingerprint": "2:Debugger.stepOut"},
                        ],
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-auto-loop-1",
                        "workflow_id": "native-auto-workflow-1",
                        "readiness": {"next_loop_iteration_reviewable": True, "automatic_multi_step_loop_supported": False},
                        "iteration_plan": [
                            {"iteration_index": 1, "workflow_step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver"},
                            {"iteration_index": 2, "workflow_step_index": 2, "method": "Debugger.stepOut", "fingerprint": "2:Debugger.stepOut"},
                        ],
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_bounded_automatic_loop_executor_contract")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-readiness.json")
        self.assertEqual(result.artifacts[0].metadata["candidate_iteration_count"], 2)
        self.assertFalse(result.artifacts[0].metadata["automation_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["long_lived_cross_process_session_managed"])
        self.assertIn("paused_session_automatic_loop_readiness_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_executor_implemented=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_automatic_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_readiness_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_execution_plan_from_native_runtime_is_plan_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        readiness = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-readiness.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "automation_executor_implemented": False,
            "automatic_multi_step_loop_supported": False,
            "loop_id": "native-auto-loop-plan-1",
            "workflow_id": "native-auto-workflow-plan-1",
            "pause_session_id": "native-auto-pause-plan-1",
            "target_id": "native-auto-target-plan-1",
            "candidate_iteration_count": 2,
            "candidate_iterations": [
                {"iteration_index": 1, "workflow_step_index": 0, "method": "Debugger.stepOver", "fingerprint": "a"},
                {"iteration_index": 2, "workflow_step_index": 1, "method": "Debugger.resume", "fingerprint": "b"},
            ],
            "blockers": [],
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-execution-plan",
            {
                "paused_session_automatic_loop_execution_plan": True,
                "paused_session_automatic_loop_readiness": readiness,
                "max_planned_iterations": 2,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_bounded_automatic_loop_executor_plan")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-execution-plan.json")
        self.assertEqual(result.artifacts[0].metadata["planned_iteration_count"], 2)
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["long_lived_cross_process_session_managed"])
        self.assertIn("paused_session_automatic_loop_execution_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_executor_implemented=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_automatic_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_executor_preflight_from_native_runtime_is_preflight_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        execution_plan = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-execution-plan.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "execution_plan_ready_for_review": True,
            "plan_id": "automatic-loop-plan:native-preflight-loop-1",
            "loop_id": "native-preflight-loop-1",
            "workflow_id": "native-preflight-workflow-1",
            "pause_session_id": "native-preflight-pause-1",
            "target_id": "native-preflight-target-1",
            "planned_iteration_count": 2,
            "max_planned_iterations": 2,
            "planned_iterations": [
                {"iteration_index": 1, "workflow_step_index": 0, "method": "Debugger.stepOver", "fingerprint": "a"},
                {"iteration_index": 2, "workflow_step_index": 1, "method": "Debugger.resume", "fingerprint": "b"},
            ],
            "review_gates": {
                "requires_review_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
            },
            "future_executor_contract": {"executor_name": "execute_paused_session_automatic_loop", "implemented": False},
            "blockers": [],
            "side_effect_policy": {
                "cdp_command_sent": False,
                "debugger_event_subscribed": False,
                "paused_event_captured": False,
                "callframe_evaluated": False,
                "multi_step_continuation_executed": False,
                "automatic_multi_step_loop": False,
                "automatic_queue_advance": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-executor-preflight",
            {
                "paused_session_automatic_loop_executor_preflight": True,
                "paused_session_automatic_loop_execution_plan": execution_plan,
                "max_preflight_iterations": 2,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_bounded_automatic_loop_executor_preflight")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-executor-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["preflight_iteration_count"], 2)
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["long_lived_cross_process_session_managed"])
        self.assertIn("paused_session_automatic_loop_executor_preflight_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_executor_implemented=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_automatic_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_executor_approval_plan_from_native_runtime_is_plan_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        preflight = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-executor-preflight.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "executor_preflight_ready_for_review": True,
            "preflight_id": "automatic-loop-executor-preflight:native-approval-1",
            "plan_id": "automatic-loop-plan:native-approval-1",
            "loop_id": "native-approval-loop-1",
            "workflow_id": "native-approval-workflow-1",
            "pause_session_id": "native-approval-pause-1",
            "target_id": "native-approval-target-1",
            "preflight_iteration_count": 2,
            "max_preflight_iterations": 2,
            "preflight_iterations": [
                {"iteration_index": 1, "workflow_step_index": 0, "method": "Debugger.stepOver", "fingerprint": "a"},
                {"iteration_index": 2, "workflow_step_index": 1, "method": "Debugger.resume", "fingerprint": "b"},
            ],
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "executor_implemented": False,
                "requires_review_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
            },
            "future_executor_contract": {"executor_name": "execute_paused_session_automatic_loop", "implemented": False},
            "blockers": [],
            "side_effect_policy": {
                "cdp_command_sent": False,
                "cdp_target_attached": False,
                "debugger_domain_enabled": False,
                "debugger_event_subscribed": False,
                "paused_event_captured": False,
                "callframe_evaluated": False,
                "runtime_mutated": False,
                "multi_step_continuation_executed": False,
                "automatic_multi_step_loop": False,
                "automatic_queue_advance": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-executor-approval-plan",
            {
                "paused_session_automatic_loop_executor_approval_plan": True,
                "paused_session_automatic_loop_executor_preflight": preflight,
                "max_approved_iterations": 2,
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_bounded_automatic_loop_executor_approval_transaction")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-executor-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["approved_iteration_count"], 2)
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["approval_recorded"])
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertFalse(result.artifacts[0].metadata["long_lived_cross_process_session_managed"])
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_executor_implemented=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_transaction_started=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_journal_written=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_automatic_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_execution_from_native_runtime_runs_one_reviewed_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "execute-paused-session-automatic-loop",
            {
                "paused_session_automatic_loop_execution": True,
                "execute_paused_session_automatic_loop": True,
                "review_approved": True,
                "paused_session_automatic_loop_bounded_executor_gate": {
                    "status": "ready_for_review",
                    "bounded_executor_gate_ready_for_review": True,
                    "ready_to_execute_now": False,
                    "automatic_loop_executed": False,
                    "transaction_id": "native-auto-tx-1",
                    "journal_id": "native-auto-journal-1",
                    "loop_id": "native-auto-exec-loop-1",
                    "workflow_id": "native-auto-exec-workflow-1",
                },
                "paused_session_automatic_loop_transaction_journal": {
                    "status": "written",
                    "journal_written": True,
                    "transaction_started": True,
                    "transaction_id": "native-auto-tx-1",
                    "journal_id": "native-auto-journal-1",
                    "journal_summary": {"automatic_loop_executed": False},
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-auto-exec-loop-1",
                        "workflow_id": "native-auto-exec-workflow-1",
                        "pause_session_id": "native-auto-exec-pause-1",
                        "target_id": "native-auto-exec-target-1",
                        "next_iteration": {
                            "available": True,
                            "ready_for_review": True,
                            "workflow_step_index": 1,
                            "method": "Debugger.stepOver",
                        },
                        "readiness": {
                            "next_loop_iteration_reviewable": True,
                            "automatic_multi_step_loop_supported": False,
                            "automatic_queue_advance_supported": False,
                            "automatic_live_callframe_recovery_supported": False,
                            "automatic_wrapper_continuation_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-auto-exec-workflow-1",
                        "pause_session_id": "native-auto-exec-pause-1",
                        "target_id": "native-auto-exec-target-1",
                        "planned_steps": [{"step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"}],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-auto-exec-pause-1",
                        "target_id": "native-auto-exec-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-auto-cf-1",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-auto-cf-1",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-auto-cf-2",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 10, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["paused_session_automatic_loop_one_iteration"])
        self.assertEqual(result.next_action, "checkpoint_automatic_loop_iteration_captured_pause")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-execution-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertEqual(result.artifacts[0].metadata["executed_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["checkpoint_required"])
        self.assertFalse(result.artifacts[0].metadata["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["long_lived_session_managed"])
        self.assertIn("paused_session_automatic_loop_execution_status=executed", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_event_subscribed=True", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_bounded_one_iteration_only=True", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_paused_session_automatic_loop_followup_checkpoint_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-followup-checkpoint",
            {
                "paused_session_automatic_loop_followup_checkpoint": True,
                "reviewer": "native-debug-reviewer",
                "paused_session_automatic_loop_execution_result": {
                    "execution": {
                        "status": "executed",
                        "transaction_id": "native-follow-tx-1",
                        "journal_id": "native-follow-journal-1",
                        "loop_id": "native-follow-loop-1",
                        "workflow_id": "native-follow-workflow-1",
                        "pause_session_id": "native-follow-pause-1",
                        "target_id": "native-follow-target-1",
                        "executed_iteration_count": 1,
                        "checkpoint_required": True,
                        "automatic_loop_executed": True,
                        "automatic_loop_one_iteration_executed": True,
                        "loop_advanced": False,
                        "queue_advanced": False,
                        "long_lived_session_managed": False,
                        "side_effect_policy": {
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-follow-pause-1",
                        "target_id": "native-follow-target-1",
                        "callframe_count": 1,
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovery_ready": True,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-follow-loop-1",
                        "workflow_id": "native-follow-workflow-1",
                        "pause_session_id": "native-follow-pause-1",
                        "target_id": "native-follow-target-1",
                        "next_iteration": {"available": True, "workflow_step_index": 2, "method": "Debugger.stepOver"},
                        "readiness": {
                            "next_loop_iteration_reviewable": True,
                            "automatic_multi_step_loop_supported": False,
                        },
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_next_paused_session_automatic_loop_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-followup-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertEqual(result.artifacts[0].metadata["transaction_id"], "native-follow-tx-1")
        self.assertTrue(result.artifacts[0].metadata["checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["checkpoint_written"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["debugger_event_subscribed"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["multi_step_continuation_executed"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_checkpoint_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_next_loop_plan_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_next_iteration_reviewable=True", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_checkpoint_written=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_next_iteration_plan_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-next-iteration-plan",
            {
                "paused_session_automatic_loop_next_iteration_plan": True,
                "reviewer": "native-next-reviewer",
                "paused_session_automatic_loop_followup_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-next-tx-1",
                        "journal_id": "native-next-journal-1",
                        "loop_id": "native-next-loop-1",
                        "workflow_id": "native-next-workflow-1",
                        "pause_session_id": "native-next-pause-1",
                        "target_id": "native-next-target-1",
                        "checkpoint_review": {"checkpoint_ready": True},
                        "next_loop_review": {"next_loop_plan_ready": True, "next_iteration_reviewable": True},
                        "side_effect_policy": {
                            "checkpoint_written": False,
                            "cdp_command_sent": False,
                            "debugger_event_subscribed": False,
                            "paused_event_captured": False,
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-next-pause-1",
                        "target_id": "native-next-target-1",
                        "callframe_count": 1,
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovery_ready": True,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-next-loop-1",
                        "workflow_id": "native-next-workflow-1",
                        "pause_session_id": "native-next-pause-1",
                        "target_id": "native-next-target-1",
                        "next_iteration": {
                            "available": True,
                            "selected_step_index": 2,
                            "selected_step": {"method": "Debugger.stepOver", "action": "step_over"},
                        },
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "ready_for_review",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "native-next-callframe-1",
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_paused_session_automatic_loop_next_iteration_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-next-iteration-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertEqual(result.artifacts[0].metadata["transaction_id"], "native-next-tx-1")
        self.assertTrue(result.artifacts[0].metadata["followup_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["continuation_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertTrue(result.artifacts[0].metadata["fresh_live_callframe_recovered"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["would_execute_next_iteration"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["debugger_event_subscribed"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["paused_event_captured"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["callframe_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_followup_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_checkpoint_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_loop_plan_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_next_iteration_reviewable=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_fresh_live_callframe_recovered=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_would_execute_next_iteration=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_event_subscribed=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_next_iteration_execution_from_native_runtime_runs_one_reviewed_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "execute-paused-session-automatic-loop-next-iteration",
            {
                "paused_session_automatic_loop_next_iteration_execution": True,
                "execute_paused_session_automatic_loop_next_iteration": True,
                "review_approved": True,
                "paused_session_automatic_loop_next_iteration_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-next-exec-tx-1",
                        "journal_id": "native-next-exec-journal-1",
                        "loop_id": "native-next-exec-loop-1",
                        "workflow_id": "native-next-exec-workflow-1",
                        "pause_session_id": "native-next-exec-pause-1",
                        "target_id": "native-next-exec-target-1",
                        "checkpoint_review": {"followup_checkpoint_ready": True, "continuation_checkpoint_ready": True},
                        "next_iteration": {
                            "next_loop_plan_ready": True,
                            "next_iteration_reviewable": True,
                            "fresh_live_callframe_recovered": True,
                        },
                        "execution_review_gates": {"requires_explicit_execution_approval": True},
                        "side_effect_policy": {"would_execute_next_iteration": False, "loop_advanced": False, "queue_advanced": False, "calls_mcp": False, "mobile_runtime_used": False},
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-next-exec-loop-1",
                        "workflow_id": "native-next-exec-workflow-1",
                        "pause_session_id": "native-next-exec-pause-1",
                        "target_id": "native-next-exec-target-1",
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 1, "method": "Debugger.stepOver"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-next-exec-workflow-1",
                        "planned_steps": [{"step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"}],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-next-exec-pause-1",
                        "target_id": "native-next-exec-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-next-exec-cf-1",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-next-exec-cf-1",
                "timeout_ms": 10,
                "observed_paused_event": {"params": {"reason": "step", "callFrames": [{"callFrameId": "native-next-exec-cf-2"}]}},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_paused_session_automatic_loop_next_iteration"])
        self.assertEqual(result.next_action, "checkpoint_automatic_loop_next_iteration_captured_pause")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-next-iteration-execution.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertEqual(result.artifacts[0].metadata["executed_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["checkpoint_required"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_status=executed", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_event_subscribed=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_bounded_one_iteration_only=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_long_lived_session=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")

    def test_paused_session_automatic_loop_multi_iteration_execution_from_native_runtime_runs_one_reviewed_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "execute-paused-session-automatic-loop-multi-iteration",
            {
                "paused_session_automatic_loop_multi_iteration_execution": True,
                "execute_paused_session_automatic_loop_multi_iteration": True,
                "review_approved": True,
                "max_iterations": 2,
                "paused_session_automatic_loop_multi_iteration_bounded_executor_gate": {
                    "status": "ready_for_review",
                    "bounded_executor_gate_ready_for_review": True,
                    "multi_iteration_bounded_executor_gate_ready_for_review": True,
                    "ready_to_execute_now": False,
                    "automatic_loop_executed": False,
                    "automatic_multi_iteration_loop": False,
                    "automatic_multi_iteration_execution_allowed_now": False,
                    "transaction_id": "native-multi-exec-tx-1",
                    "journal_id": "native-multi-exec-journal-1",
                    "loop_id": "native-multi-exec-loop-1",
                    "workflow_id": "native-multi-exec-workflow-1",
                    "planned_iterations": [
                        {
                            "iteration_index": 1,
                            "source_iteration_index": 0,
                            "workflow_step_index": 1,
                            "method": "Debugger.stepOver",
                            "ready_for_future_executor_review": True,
                            "requires_per_iteration_review_gate": True,
                            "requires_fresh_live_callframe_before_execution": True,
                            "requires_checkpoint_after_iteration": True,
                            "requires_stop_after_checkpoint": True,
                        },
                        {
                            "iteration_index": 2,
                            "source_iteration_index": 1,
                            "workflow_step_index": 2,
                            "method": "Debugger.stepInto",
                            "ready_for_future_executor_review": True,
                            "requires_per_iteration_review_gate": True,
                            "requires_fresh_live_callframe_before_execution": True,
                            "requires_checkpoint_after_iteration": True,
                            "requires_stop_after_checkpoint": True,
                        },
                    ],
                    "bounded_executor_input": {
                        "max_iterations": 2,
                        "requires_per_iteration_review": True,
                        "requires_checkpoint_after_each_iteration": True,
                        "requires_stop_after_each_checkpoint": True,
                        "require_fresh_live_callframe": True,
                        "requires_retained_attached_session": True,
                        "automatic_queue_advance_allowed": False,
                        "automatic_loop_advance_allowed": False,
                        "automatic_live_callframe_recovery_allowed": False,
                        "long_lived_session_management_allowed": False,
                    },
                },
                "paused_session_automatic_loop_multi_iteration_transaction_journal": {
                    "status": "written",
                    "journal_written": True,
                    "transaction_started": True,
                    "transaction_id": "native-multi-exec-tx-1",
                    "journal_id": "native-multi-exec-journal-1",
                    "journal_summary": {"automatic_loop_executed": False, "automatic_multi_iteration_loop": False},
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-multi-exec-loop-1",
                        "workflow_id": "native-multi-exec-workflow-1",
                        "pause_session_id": "native-multi-exec-pause-1",
                        "target_id": "native-multi-exec-target-1",
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 1, "method": "Debugger.stepOver"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {"status": "ready_for_review", "workflow_id": "native-multi-exec-workflow-1", "planned_steps": [{"step_index": 1, "method": "Debugger.stepOver"}]}
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-multi-exec-pause-1",
                        "target_id": "native-multi-exec-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-multi-exec-cf-1",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-multi-exec-cf-1",
                "timeout_ms": 10,
                "observed_paused_event": {"params": {"reason": "step", "callFrames": [{"callFrameId": "native-multi-exec-cf-2"}]}},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_paused_session_automatic_loop_multi_iteration"])
        self.assertEqual(result.next_action, "checkpoint_multi_iteration_step_before_next_review")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-execution-result.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "partial")
        self.assertEqual(result.artifacts[0].metadata["requested_iteration_budget"], 2)
        self.assertEqual(result.artifacts[0].metadata["executed_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["checkpoint_required"])
        self.assertTrue(result.artifacts[0].metadata["automatic_multi_iteration_execution_mvp"])
        self.assertTrue(result.artifacts[0].metadata["automatic_multi_iteration_executor_implemented"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_iteration_loop"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_status=partial", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_executed_iterations=1", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_checkpoint_required=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_bounded_one_iteration_only=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOver")



    def test_paused_session_automatic_loop_multi_iteration_followup_checkpoint_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-followup-checkpoint",
            {
                "paused_session_automatic_loop_multi_iteration_followup_checkpoint": True,
                "reviewer": "native-multi-followup-reviewer",
                "paused_session_automatic_loop_multi_iteration_execution_result": {
                    "execution": {
                        "status": "partial",
                        "transaction_id": "native-multi-followup-tx-1",
                        "journal_id": "native-multi-followup-journal-1",
                        "loop_id": "native-multi-followup-loop-1",
                        "workflow_id": "native-multi-followup-workflow-1",
                        "pause_session_id": "native-multi-followup-pause-1",
                        "target_id": "native-multi-followup-target-1",
                        "requested_iteration_budget": 2,
                        "max_iterations_per_apply": 1,
                        "executed_iteration_count": 1,
                        "checkpoint_required": True,
                        "automatic_multi_iteration_execution_mvp": True,
                        "automatic_multi_iteration_executor_implemented": True,
                        "automatic_multi_iteration_loop": False,
                        "automatic_loop_executed": True,
                        "automatic_loop_one_iteration_executed": True,
                        "loop_advanced": False,
                        "queue_advanced": False,
                        "long_lived_session_managed": False,
                        "side_effect_policy": {
                            "automatic_multi_iteration_loop": False,
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "native-multi-followup-pause-1",
                        "target_id": "native-multi-followup-target-1",
                        "callframe_count": 1,
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovery_ready": True,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-multi-followup-loop-1",
                        "workflow_id": "native-multi-followup-workflow-1",
                        "pause_session_id": "native-multi-followup-pause-1",
                        "target_id": "native-multi-followup-target-1",
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 2, "method": "Debugger.stepInto"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_next_paused_session_automatic_loop_multi_iteration_step")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-followup-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["executed_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_iteration_loop"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["checkpoint_written"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_checkpoint_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_next_loop_plan_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_followup_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_multi_iteration_next_step_plan_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-next-step-plan",
            {
                "paused_session_automatic_loop_multi_iteration_next_step_plan": True,
                "reviewer": "native-multi-next-step-reviewer",
                "paused_session_automatic_loop_multi_iteration_followup_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-multi-next-step-tx-1",
                        "journal_id": "native-multi-next-step-journal-1",
                        "checkpoint_review": {"checkpoint_ready": True},
                        "next_loop_review": {"next_loop_plan_ready": True, "next_iteration_reviewable": True},
                        "side_effect_policy": {
                            "checkpoint_written": False,
                            "cdp_command_sent": False,
                            "debugger_event_subscribed": False,
                            "paused_event_captured": False,
                            "automatic_multi_iteration_loop": False,
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "continuation_ready_for_next_action": True,
                        "callframe_count": 1,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-multi-next-step-loop-1",
                        "workflow_id": "native-multi-next-step-workflow-1",
                        "readiness": {"next_loop_iteration_reviewable": True},
                        "review_gates": {"requires_fresh_live_callframe": True},
                        "next_iteration": {
                            "available": True,
                            "selected_step_index": 1,
                            "selected_step": {"method": "Debugger.stepInto", "action": "step_into"},
                        },
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "ready_for_review",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "native-cf-live-266",
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_paused_session_automatic_loop_multi_iteration_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-next-step-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_review"])
        self.assertTrue(result.artifacts[0].metadata["multi_iteration_followup_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["continuation_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertTrue(result.artifacts[0].metadata["fresh_live_callframe_recovered"])
        self.assertEqual(result.artifacts[0].metadata["expected_executor"], "execute_paused_session_automatic_loop_multi_iteration")
        self.assertTrue(result.artifacts[0].metadata["step264_executor_mvp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["would_execute_multi_iteration"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["automatic_multi_iteration_loop"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["debugger_event_subscribed"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["paused_event_captured"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_followup_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_checkpoint_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_loop_plan_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_next_iteration_reviewable=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_fresh_live_callframe_recovered=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_expected_executor=execute_paused_session_automatic_loop_multi_iteration", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_step264_executor_mvp=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_would_execute_multi_iteration=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_next_step_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)


    def test_paused_session_automatic_loop_multi_iteration_executor_input_preflight_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-executor-input-preflight",
            {
                "paused_session_automatic_loop_multi_iteration_executor_input_preflight": True,
                "reviewer": "native-multi-input-reviewer",
                "paused_session_automatic_loop_multi_iteration_next_step_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-multi-input-tx-1",
                        "checkpoint_review": {"multi_iteration_followup_checkpoint_ready": True, "continuation_checkpoint_ready": True},
                        "next_iteration": {
                            "next_loop_plan_ready": True,
                            "next_iteration_reviewable": True,
                            "fresh_live_callframe_recovered": True,
                            "would_execute_multi_iteration": False,
                            "automatic_multi_iteration_loop": False,
                        },
                        "expected_executor": {"name": "execute_paused_session_automatic_loop_multi_iteration", "implemented": True, "step264_executor_mvp": True},
                        "blockers": [],
                        "side_effect_policy": {
                            "would_execute_multi_iteration": False,
                            "automatic_multi_iteration_loop": False,
                            "cdp_command_sent": False,
                            "debugger_event_subscribed": False,
                            "paused_event_captured": False,
                            "checkpoint_written": False,
                            "live_callframe_recovered": False,
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "long_lived_cross_process_session_managed": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                    }
                },
                "paused_session_automatic_loop_multi_iteration_bounded_executor_gate": {
                    "status": "ready_for_review",
                    "bounded_executor_gate_ready_for_review": True,
                    "multi_iteration_bounded_executor_gate_ready_for_review": True,
                    "ready_to_execute_now": False,
                    "automatic_loop_executed": False,
                    "automatic_multi_iteration_loop": False,
                    "automatic_multi_iteration_execution_allowed_now": False,
                    "transaction_id": "native-multi-input-tx-1",
                    "journal_id": "native-multi-input-journal-1",
                    "loop_id": "native-multi-input-loop-1",
                    "workflow_id": "native-multi-input-workflow-1",
                    "planned_iterations": [
                        {
                            "iteration_index": 1,
                            "source_iteration_index": 0,
                            "workflow_step_index": 1,
                            "method": "Debugger.stepOver",
                            "ready_for_future_executor_review": True,
                            "requires_per_iteration_review_gate": True,
                            "requires_fresh_live_callframe_before_execution": True,
                            "requires_checkpoint_after_iteration": True,
                            "requires_stop_after_checkpoint": True,
                        }
                    ],
                    "bounded_executor_input": {
                        "max_iterations": 2,
                        "requires_per_iteration_review": True,
                        "requires_checkpoint_after_each_iteration": True,
                        "requires_stop_after_each_checkpoint": True,
                        "require_fresh_live_callframe": True,
                        "requires_retained_attached_session": True,
                        "automatic_queue_advance_allowed": False,
                        "automatic_loop_advance_allowed": False,
                        "automatic_live_callframe_recovery_allowed": False,
                        "long_lived_session_management_allowed": False,
                    },
                },
                "paused_session_automatic_loop_multi_iteration_transaction_journal": {
                    "status": "written",
                    "journal_written": True,
                    "transaction_started": True,
                    "transaction_id": "native-multi-input-tx-1",
                    "journal_id": "native-multi-input-journal-1",
                    "journal_summary": {"automatic_loop_executed": False, "automatic_multi_iteration_loop": False},
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-multi-input-loop-1",
                        "workflow_id": "native-multi-input-workflow-1",
                        "pause_session_id": "native-pause-input-1",
                        "target_id": "native-target-input-1",
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 1, "method": "Debugger.stepOver"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "workflow_id": "native-multi-input-workflow-1",
                        "planned_steps": [{"step_index": 1, "method": "Debugger.stepOver"}],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-pause-input-1",
                        "target_id": "native-target-input-1",
                        "attached_session_id": "native-attached-input-1",
                        "live_callframe_id": "native-cf-input-1",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "attached_session_id": "native-attached-input-1",
                "live_callframe_id": "native-cf-input-1",
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_paused_session_automatic_loop_multi_iteration_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-executor-input-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["ready_for_execution_review"])
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertTrue(result.artifacts[0].metadata["next_step_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["bounded_executor_gate_ready"])
        self.assertTrue(result.artifacts[0].metadata["transaction_journal_written"])
        self.assertTrue(result.artifacts[0].metadata["loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["workflow_ready"])
        self.assertTrue(result.artifacts[0].metadata["fresh_live_callframe_recovered"])
        self.assertTrue(result.artifacts[0].metadata["retained_attached_session_available"])
        self.assertEqual(result.artifacts[0].metadata["expected_executor"], "execute_paused_session_automatic_loop_multi_iteration")
        self.assertTrue(result.artifacts[0].metadata["step264_executor_mvp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["would_execute_multi_iteration"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["automatic_multi_iteration_loop"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["debugger_event_subscribed"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["paused_event_captured"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["checkpoint_written"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["live_callframe_recovered"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_ready_for_execution_review=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_next_step_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_gate_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_journal_written=True", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_would_execute_multi_iteration=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_input_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_next_iteration_followup_checkpoint_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "checkpoint-paused-session-automatic-loop-next-iteration-execution",
            {
                "paused_session_automatic_loop_next_iteration_followup_checkpoint": True,
                "paused_session_automatic_loop_next_iteration_execution": {
                    "execution": {
                        "status": "executed",
                        "transaction_id": "native-next-followup-tx-1",
                        "journal_id": "native-next-followup-journal-1",
                        "loop_id": "native-next-followup-loop-1",
                        "workflow_id": "native-next-followup-workflow-1",
                        "pause_session_id": "native-next-followup-pause-1",
                        "target_id": "native-next-followup-target-1",
                        "automatic_loop_next_iteration_executed": True,
                        "automatic_loop_executed": True,
                        "automatic_loop_one_iteration_executed": True,
                        "executed_iteration_count": 1,
                        "checkpoint_required": True,
                        "loop_advanced": False,
                        "queue_advanced": False,
                        "side_effect_policy": {"loop_advanced": False, "queue_advanced": False, "calls_mcp": False, "mobile_runtime_used": False},
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {"status": "ready_for_next_action_review", "continuation_ready_for_next_action": True, "callframe_count": 1}
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-next-followup-loop-1",
                        "workflow_id": "native-next-followup-workflow-1",
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 2, "method": "Debugger.stepOver"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_following_paused_session_automatic_loop_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-next-iteration-followup-checkpoint.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["checkpoint_written"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_checkpoint_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_next_loop_plan_ready=True", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_next_iteration_followup_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)


    def test_paused_session_automatic_loop_following_iteration_plan_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "review-following-paused-session-automatic-loop-iteration",
            {
                "paused_session_automatic_loop_following_iteration_plan": True,
                "paused_session_automatic_loop_next_iteration_followup_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-following-tx-1",
                        "checkpoint_review": {"checkpoint_ready": True},
                        "next_loop_review": {"next_loop_plan_ready": True, "next_iteration_reviewable": True},
                        "side_effect_policy": {"checkpoint_written": False, "cdp_command_sent": False, "loop_advanced": False, "queue_advanced": False, "calls_mcp": False, "mobile_runtime_used": False},
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {"checkpoint": {"status": "ready_for_next_action_review", "continuation_ready_for_next_action": True, "callframe_count": 1}},
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "next_iteration": {"available": True, "ready_for_review": True, "workflow_step_index": 3, "method": "Debugger.stepOver"},
                        "readiness": {"next_loop_iteration_reviewable": True},
                    }
                },
                "paused_session_live_callframe_recovery": {"recovery": {"status": "recovered", "live_callframe_recovered": True, "live_callframe_id": "native-following-cf-1"}},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_paused_session_automatic_loop_next_iteration_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-following-iteration-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertTrue(result.artifacts[0].metadata["followup_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["continuation_checkpoint_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_loop_plan_ready"])
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertTrue(result.artifacts[0].metadata["fresh_live_callframe_recovered"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["would_execute_next_iteration"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result.artifacts[0].metadata["side_effect_policy"]["mobile_runtime_used"])
        self.assertIn("paused_session_automatic_loop_following_iteration_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_following_iteration_plan_would_execute_next_iteration=False", result.verification)
        self.assertIn("paused_session_automatic_loop_following_iteration_plan_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_following_iteration_plan_queue_advanced=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_multi_iteration_policy_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "review-paused-session-automatic-loop-multi-iteration-policy",
            {
                "paused_session_automatic_loop_multi_iteration_policy": True,
                "max_policy_iterations": 3,
                "paused_session_automatic_loop_following_iteration_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "transaction_id": "native-policy-tx-1",
                        "loop_id": "native-policy-loop-1",
                        "workflow_id": "native-policy-workflow-1",
                        "checkpoint_review": {"followup_checkpoint_ready": True, "continuation_checkpoint_ready": True},
                        "next_iteration": {"next_loop_plan_ready": True, "next_iteration_reviewable": True, "fresh_live_callframe_recovered": True},
                        "side_effect_policy": {
                            "would_execute_next_iteration": False,
                            "cdp_command_sent": False,
                            "loop_advanced": False,
                            "queue_advanced": False,
                            "calls_mcp": False,
                            "mobile_runtime_used": False,
                        },
                        "blockers": [],
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_paused_session_automatic_loop_multi_iteration_executor_contract")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-policy.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["max_policy_iterations"], 3)
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_iteration_executor_implemented"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_budget=3", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_executor_implemented=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_execution_allowed_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_policy_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_multi_iteration_executor_preflight_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)
        policy = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-policy.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "policy_id": "automatic-loop-policy:native-policy-tx-1",
            "transaction_id": "native-policy-tx-1",
            "loop_id": "native-policy-loop-1",
            "workflow_id": "native-policy-workflow-1",
            "budget_policy": {
                "max_policy_iterations": 3,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_review_per_iteration": True,
                "requires_checkpoint_after_each_iteration": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "stop_after_each_checkpoint": True,
            },
            "per_iteration_gates": [
                {
                    "iteration_number": index,
                    "requires_explicit_review": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_fresh_live_callframe": True,
                    "requires_stop_for_review_after_checkpoint": True,
                    "would_execute_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                }
                for index in range(1, 4)
            ],
            "future_executor_contract": {"executor_name": "execute_paused_session_automatic_loop_multi_iteration", "implemented": False},
            "side_effect_policy": {
                "automatic_multi_iteration_loop": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
            "blockers": [],
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-executor-preflight",
            {
                "paused_session_automatic_loop_multi_iteration_executor_preflight": True,
                "max_preflight_iterations": 3,
                "paused_session_automatic_loop_multi_iteration_policy": {"policy": policy},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_paused_session_automatic_loop_multi_iteration_executor_preflight")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-executor-preflight.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["preflight_iteration_count"], 3)
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_iteration_executor_implemented"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_iteration_count=3", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_preflight_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_multi_iteration_execution_plan_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)
        preflight = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-executor-preflight.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "executor_preflight_ready_for_review": True,
            "preflight_id": "automatic-loop-multi-iteration-preflight:automatic-loop-policy:native-policy-tx-1",
            "policy_id": "automatic-loop-policy:native-policy-tx-1",
            "transaction_id": "native-policy-tx-1",
            "loop_id": "native-policy-loop-1",
            "workflow_id": "native-policy-workflow-1",
            "preflight_iteration_count": 3,
            "policy_iteration_budget": 3,
            "source_policy": {"ready_for_review": True},
            "executor_input_gates": {
                "ready_to_execute_now": False,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_transaction_journal": True,
                "requires_per_iteration_review_gate": True,
                "requires_per_iteration_checkpoint_gate": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_non_daemon_execution": True,
                "requires_bounded_iteration_budget": True,
            },
            "preflight_iterations": [
                {
                    "iteration_number": index,
                    "policy_gate_ready": True,
                    "requires_explicit_review": True,
                    "requires_transaction_journal": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_stop_for_review_after_checkpoint": True,
                    "would_execute_in_this_descriptor": False,
                    "would_write_checkpoint_in_this_descriptor": False,
                    "would_recover_live_callframe_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                }
                for index in range(1, 4)
            ],
            "future_executor_contract": {"executor_name": "execute_paused_session_automatic_loop_multi_iteration", "implemented": False},
            "side_effect_policy": {
                "automatic_multi_iteration_loop": False,
                "checkpoint_written": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
            "blockers": [],
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-execution-plan",
            {
                "paused_session_automatic_loop_multi_iteration_execution_plan": True,
                "max_planned_iterations": 3,
                "paused_session_automatic_loop_multi_iteration_executor_preflight": {"preflight": preflight},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_paused_session_automatic_loop_multi_iteration_executor_execution")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-execution-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["planned_iteration_count"], 3)
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_iteration_executor_implemented"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_planned_iteration_count=3", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_loop_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_queue_advanced=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_execution_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_automatic_loop_multi_iteration_executor_approval_plan_from_native_runtime_is_plan_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)
        execution_plan = {
            "schema_version": "reverse-deepagent.paused-session-automatic-loop-multi-iteration-execution-plan.v1",
            "status": "ready_for_review",
            "ready_for_review": True,
            "execution_plan_ready_for_review": True,
            "execution_plan_id": "automatic-loop-multi-iteration-execution-plan:automatic-loop-multi-iteration-preflight:automatic-loop-policy:native-policy-tx-1",
            "preflight_id": "automatic-loop-multi-iteration-preflight:automatic-loop-policy:native-policy-tx-1",
            "policy_id": "automatic-loop-policy:native-policy-tx-1",
            "transaction_id": "native-policy-tx-1",
            "loop_id": "native-policy-loop-1",
            "workflow_id": "native-policy-workflow-1",
            "execution_review_gates": {
                "ready_to_execute_now": False,
                "execution_plan_only": True,
                "automatic_multi_iteration_executor_implemented": False,
                "automatic_multi_iteration_execution_allowed_now": False,
                "requires_transaction_journal": True,
                "requires_per_iteration_review_gate": True,
                "requires_per_iteration_checkpoint_gate": True,
                "requires_fresh_live_callframe_per_iteration": True,
                "requires_stop_after_each_checkpoint": True,
                "requires_retained_attached_session_per_iteration": True,
                "requires_non_daemon_execution": True,
                "requires_bounded_iteration_budget": True,
            },
            "planned_iteration_count": 3,
            "max_planned_iterations": 3,
            "planned_iterations": [
                {
                    "iteration_number": index,
                    "plan_iteration_index": index - 1,
                    "source_policy_gate_ready": True,
                    "requires_explicit_review": True,
                    "requires_transaction_journal": True,
                    "requires_fresh_live_callframe": True,
                    "requires_retained_attached_session": True,
                    "requires_checkpoint_after_iteration": True,
                    "requires_stop_for_review_after_checkpoint": True,
                    "would_execute_in_this_descriptor": False,
                    "would_delegate_to_future_executor_now": False,
                    "would_write_checkpoint_in_this_descriptor": False,
                    "would_recover_live_callframe_in_this_descriptor": False,
                    "would_advance_queue_in_this_descriptor": False,
                }
                for index in range(1, 4)
            ],
            "future_executor_contract": {"executor_name": "execute_paused_session_automatic_loop_multi_iteration", "implemented": False},
            "side_effect_policy": {
                "automatic_multi_iteration_loop": False,
                "checkpoint_written": False,
                "loop_advanced": False,
                "queue_advanced": False,
                "long_lived_cross_process_session_managed": False,
                "calls_mcp": False,
                "mobile_runtime_used": False,
            },
            "blockers": [],
        }

        result = runtime.apply_minimal_protection(
            "paused-session-automatic-loop-multi-iteration-executor-approval-plan",
            {
                "paused_session_automatic_loop_multi_iteration_executor_approval_plan": True,
                "max_approved_iterations": 3,
                "paused_session_automatic_loop_multi_iteration_execution_plan": {"plan": execution_plan},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_future_paused_session_automatic_loop_multi_iteration_executor_approval_transaction")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-automatic-loop-multi-iteration-executor-approval-plan.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "ready_for_review")
        self.assertEqual(result.artifacts[0].metadata["approved_iteration_count"], 3)
        self.assertFalse(result.artifacts[0].metadata["ready_to_execute_now"])
        self.assertFalse(result.artifacts[0].metadata["approval_recorded"])
        self.assertFalse(result.artifacts[0].metadata["transaction_started"])
        self.assertFalse(result.artifacts[0].metadata["journal_written"])
        self.assertFalse(result.artifacts[0].metadata["future_executor_implemented"])
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_approved_iterations=3", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_ready_to_execute_now=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_approval_recorded=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_transaction_started=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_journal_written=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_automatic_multi_iteration_loop=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_automatic_loop_multi_iteration_executor_approval_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_multi_step_loop_plan_from_native_runtime_is_review_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-multi-step-loop-plan",
            {
                "paused_session_multi_step_loop_plan": True,
                "max_loop_iterations": 3,
                "paused_session_cross_process_session_lifecycle": {
                    "lifecycle": {
                        "status": "ready_for_review",
                        "pause_session_id": "native-loop-pause-1",
                        "target_id": "native-loop-target-1",
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-loop-workflow-1",
                        "pause_session_id": "native-loop-pause-1",
                        "target_id": "native-loop-target-1",
                        "planned_steps": [
                            {"step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:", "expected_executor_artifact": "workspace/paused-session-pre-action-subscribe-and-action.json"},
                            {"step_index": 2, "method": "Debugger.stepOut", "fingerprint": "2:Debugger.stepOut:", "expected_executor_artifact": "workspace/paused-session-pre-action-subscribe-and-action.json"},
                        ],
                    }
                },
                "paused_session_multi_step_continuation_execution": {
                    "execution": {
                        "status": "executed",
                        "selected_step_index": 1,
                        "multi_step_iteration_executed": True,
                        "paused_event_captured": True,
                    }
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "continuation_ready_for_next_action": True,
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "review_next_paused_session_loop_iteration")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-multi-step-loop-plan.json")
        self.assertEqual(result.artifacts[0].metadata["completed_iteration_count"], 1)
        self.assertEqual(result.artifacts[0].metadata["remaining_iteration_count"], 1)
        self.assertTrue(result.artifacts[0].metadata["next_iteration_reviewable"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertIn("paused_session_multi_step_loop_plan_status=ready_for_review", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_next_iteration_reviewable=True", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_next_step_index=2", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_debugger_event_subscribed=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_multi_step_executed=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_automatic_loop=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_calls_mcp=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_plan_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_multi_step_loop_execution_from_native_runtime_runs_one_reviewed_iteration(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "execute-paused-session-loop-iteration",
            {
                "paused_session_multi_step_loop_execution": True,
                "execute_paused_session_loop_iteration": True,
                "review_approved": True,
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "loop_id": "native-loop-exec-1",
                        "workflow_id": "native-loop-workflow-1",
                        "pause_session_id": "native-loop-pause-1",
                        "target_id": "native-loop-target-1",
                        "next_iteration": {
                            "available": True,
                            "ready_for_review": True,
                            "workflow_step_index": 2,
                            "method": "Debugger.stepOut",
                        },
                        "readiness": {
                            "next_loop_iteration_reviewable": True,
                            "automatic_multi_step_loop_supported": False,
                            "automatic_queue_advance_supported": False,
                            "automatic_live_callframe_recovery_supported": False,
                            "automatic_wrapper_continuation_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "native-loop-workflow-1",
                        "pause_session_id": "native-loop-pause-1",
                        "target_id": "native-loop-target-1",
                        "planned_steps": [
                            {"step_index": 1, "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"},
                            {"step_index": 2, "method": "Debugger.stepOut", "fingerprint": "2:Debugger.stepOut:"},
                        ],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-loop-pause-1",
                        "target_id": "native-loop-target-1",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "native-loop-cf-2",
                        "live_callframe_recovered": True,
                        "target_detached": False,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "native-loop-cf-2",
                "timeout_ms": 10,
                "observed_paused_event": {
                    "sessionId": "attached-session-1",
                    "params": {
                        "reason": "step",
                        "callFrames": [
                            {
                                "callFrameId": "native-loop-cf-3",
                                "functionName": "buildSign",
                                "location": {"scriptId": "script-1", "lineNumber": 10, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                            }
                        ],
                    },
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["paused_session_loop_iteration"])
        self.assertEqual(result.next_action, "checkpoint_loop_iteration_captured_pause")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-multi-step-loop-execution.json")
        self.assertEqual(result.artifacts[0].metadata["status"], "executed")
        self.assertEqual(result.artifacts[0].metadata["selected_step_index"], 2)
        self.assertEqual(result.artifacts[0].metadata["selected_method"], "Debugger.stepOut")
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertFalse(result.artifacts[0].metadata["loop_advanced"])
        self.assertFalse(result.artifacts[0].metadata["queue_advanced"])
        self.assertFalse(result.artifacts[0].metadata["automatic_multi_step_loop"])
        self.assertIn("paused_session_multi_step_loop_execution_status=executed", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_event_subscribed=True", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_paused_event_captured=True", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_loop_advanced=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_queue_advanced=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_automatic_loop=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_calls_mcp=False", result.verification)
        self.assertIn("paused_session_multi_step_loop_execution_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count + 1)
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.stepOut")

    def test_paused_session_cross_process_continuation_checkpoint_from_native_runtime_is_read_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        result = runtime.apply_minimal_protection(
            "paused-session-cross-process-continuation-checkpoint",
            {
                "paused_session_cross_process_continuation_checkpoint": True,
                "paused_session_next_paused_event_capture_execution": {
                    "execution": {
                        "status": "captured",
                        "pause_session_id": "native-checkpoint-1",
                        "target_id": "target-native-checkpoint-1",
                        "attached_session_id": "attached-session-1",
                        "method": "Debugger.stepOver",
                        "paused_event_captured": True,
                        "captured_event_count": 1,
                        "live_callframe_recovery_ready": True,
                        "callframes": [{"callFrameId": "native-live-cf-3", "functionName": "buildSign"}],
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, [])
        self.assertEqual(result.next_action, "recover_live_callframe_from_captured_pause")
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-cross-process-continuation-checkpoint.json")
        self.assertTrue(result.artifacts[0].metadata["paused_event_captured"])
        self.assertEqual(result.artifacts[0].metadata["callframe_count"], 1)
        self.assertFalse(result.artifacts[0].metadata["live_callframe_recovered"])
        self.assertIn("paused_session_cross_process_continuation_checkpoint_status=ready_for_live_callframe_recovery", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_paused_event_captured=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_cdp_command_sent=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_event_subscribed=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_browser_resumed=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_debugger_stepped=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_calls_mcp=False", result.verification)
        self.assertIn("paused_session_cross_process_continuation_checkpoint_mobile_runtime_used=False", result.verification)
        self.assertEqual(len(page._cdp_session.calls), call_count)

    def test_paused_session_cross_process_one_action_from_native_runtime_executes_once(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]

        result = runtime.apply_minimal_protection(
            "paused-session-cross-process-one-action",
            {
                "paused_session_cross_process_one_action": True,
                "execute_cross_process_one_action": True,
                "review_approved": True,
                "requested_action": "evaluate",
                "expression": "typeof buildSign",
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "native-one-action-1",
                        "requested_action": "evaluate",
                        "target_id": "target-native-recover-1",
                        "target_attached": True,
                        "target_detached": False,
                        "attached_session_id": "attached-session-1",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "native-live-cf-1",
                    }
                },
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertEqual(result.applied_actions, ["execute_cross_process_one_action"])
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-cross-process-one-action-execution.json")
        self.assertEqual(page._cdp_session.calls[-1][0], "Debugger.evaluateOnCallFrame")
        self.assertEqual(page._cdp_session.calls[-1][1]["sessionId"], "attached-session-1")
        self.assertEqual(page._cdp_session.calls[-1][1]["callFrameId"], "native-live-cf-1")
        self.assertIn("paused_session_cross_process_one_action_status=executed", result.verification)
        self.assertIn("paused_session_cross_process_one_action_method=Debugger.evaluateOnCallFrame", result.verification)
        self.assertIn("paused_session_cross_process_one_action_live_action_executed=True", result.verification)
        self.assertIn("paused_session_cross_process_one_action_callframe_evaluated=True", result.verification)
        self.assertIn("paused_session_cross_process_one_action_cdp_command_sent=True", result.verification)
        self.assertIn("paused_session_cross_process_one_action_debugger_domain_enabled=False", result.verification)
        self.assertIn("paused_session_cross_process_one_action_calls_mcp=False", result.verification)
        self.assertIn("paused_session_cross_process_one_action_mobile_runtime_used=False", result.verification)
        self.assertTrue(result.artifacts[0].metadata["live_action_executed"])
        self.assertTrue(result.artifacts[0].metadata["callframe_evaluated"])
        self.assertFalse(result.artifacts[0].metadata["browser_resumed"])
        self.assertFalse(result.artifacts[0].metadata["debugger_stepped"])

    def test_paused_session_cross_process_attach_probe_from_native_runtime_requires_review_and_attaches_only(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        plan = {
            "status": "ready_for_executor_review",
            "execution_plan_ready_for_review": True,
            "pause_session_id": "native-attach-probe",
            "requested_action": "evaluate",
            "target_attach_readiness_proven": True,
            "target_attach_readiness_summary": {
                "selected_target": {"target_id": "target-native-probe-1", "type": "page"},
                "target_id_available": True,
            },
            "cross_process_execution_ready": False,
            "cross_process_executor_implemented": True,
        }

        result = runtime.apply_minimal_protection(
            "paused-session-cross-process-attach-probe",
            {
                "paused_session_cross_process_attach_probe": True,
                "execute_cross_process_attach_probe": True,
                "review_approved": True,
                "paused_session_cross_process_execution_plan": {"plan": plan},
            },
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("probe_paused_session_cross_process_attach", result.applied_actions)
        self.assertEqual(result.artifacts[0].path, "virtual://workspace/paused-session-cross-process-attach-probe.json")
        self.assertIn("paused_session_cross_process_attach_probe_attach_attempted=True", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_target_attached=True", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_target_detached=True", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_debugger_domain_enabled=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_live_callframe_recovered=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_live_action_executed=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_browser_resumed=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_debugger_stepped=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_callframe_evaluated=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_calls_mcp=False", result.verification)
        self.assertIn("paused_session_cross_process_attach_probe_mobile_runtime_used=False", result.verification)
        page = provider.session.context.pages[0]
        self.assertIn(("Target.attachToTarget", {"targetId": "target-native-probe-1", "flatten": True}), page._cdp_session.calls)
        self.assertIn(("Target.detachFromTarget", {"sessionId": "attached-session-1"}), page._cdp_session.calls)
        forbidden = {"Debugger.enable", "Debugger.resume", "Debugger.stepOver", "Debugger.evaluateOnCallFrame", "Runtime.evaluate"}
        self.assertFalse(any(method in forbidden for method, _ in page._cdp_session.calls))

    def test_native_web_runtime_plans_cross_process_paused_execution_without_cdp_action(self) -> None:
        provider = FakeProvider()
        runtime = NativeWebRuntime(browser_provider=provider)
        page = provider.session.context.pages[0]
        call_count = len(page._cdp_session.calls)

        follow_up = runtime.apply_minimal_protection(
            "paused-session-cross-process-execution-plan",
            {
                "paused_session_cross_process_execution_plan": True,
                "paused_session_target_attach_readiness": {
                    "readiness": {
                        "status": "ready_for_attach_review",
                        "source": "durable_snapshot",
                        "pause_session_id": "native-cross-plan",
                        "requested_action": "evaluate",
                        "target_attach_readiness_proven": True,
                        "target_correlation": {
                            "expected_url": "https://example.test/app.js",
                            "candidate_count": 1,
                            "selected_target": {
                                "target_id": "target-native-plan-1",
                                "type": "page",
                                "url": "https://example.test/app.js",
                            },
                        },
                        "attachability": {
                            "target_id_available": True,
                            "target_type_supported": True,
                            "requires_explicit_future_attach_step": True,
                        },
                        "callframe_recovery": {
                            "stable_live_callframe_available": False,
                            "selected_callframe_has_id": True,
                            "requires_new_paused_event_after_attach": True,
                        },
                    }
                },
            },
        )

        self.assertEqual(follow_up.status.value, "success")
        self.assertEqual(follow_up.applied_actions, ["plan_paused_session_cross_process_execution"])
        self.assertEqual(follow_up.next_action, "run_reviewed_cross_process_attach_probe_next")
        self.assertIn("paused_session_cross_process_execution_plan_status=ready_for_executor_review", follow_up.verification)
        self.assertIn("paused_session_cross_process_execution_plan_ready_for_review=True", follow_up.verification)
        self.assertIn("paused_session_cross_process_execution_ready=False", follow_up.verification)
        self.assertIn("paused_session_cross_process_executor_implemented=True", follow_up.verification)
        self.assertIn("paused_session_cross_process_would_attach_cdp_target=False", follow_up.verification)
        self.assertIn("paused_session_cross_process_cdp_command_sent=False", follow_up.verification)
        self.assertIn("paused_session_cross_process_calls_mcp=False", follow_up.verification)
        self.assertIn("paused_session_cross_process_mobile_runtime_used=False", follow_up.verification)
        self.assertEqual(follow_up.artifacts[0].path, "virtual://workspace/paused-session-cross-process-execution-plan.json")
        self.assertTrue(follow_up.artifacts[0].metadata["execution_plan_ready_for_review"])
        self.assertFalse(follow_up.artifacts[0].metadata["cross_process_execution_ready"])
        self.assertTrue(follow_up.artifacts[0].metadata["cross_process_executor_implemented"])
        self.assertEqual(
            follow_up.artifacts[0].metadata["target_attach_readiness_summary"]["selected_target"]["target_id"],
            "target-native-plan-1",
        )
        self.assertEqual(len(page._cdp_session.calls), call_count)

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
