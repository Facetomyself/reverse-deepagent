import unittest

from reverse_deepagent.browser.hooks import (
    AsyncChunkLoadManager,
    AsyncChunkLoadSpec,
    CustomLoaderTraversalPlanManager,
    CustomLoaderTraversalPlanSpec,
    ModuleDiscoveryManager,
    ModuleDiscoverySpec,
    ModuleFederationGetInitPlanManager,
    ModuleFederationGetInitPlanSpec,
    ModuleFederationGetInitProbeManager,
    ModuleFederationGetInitProbeSpec,
    ModuleHookManager,
    ModuleHookSpec,
)
from reverse_deepagent.fixtures.web_sign import FixtureProfile, _build_js


WEBPACK_MINIFIED_SOURCE = _build_js(FixtureProfile.WEBPACK_MINIFIED)


class ModuleHookPage:
    def __init__(self) -> None:
        self.installed = False
        self.events = []
        self.module_id = "731"
        self.export_name = "sign"
        self.hook_path = "window.__webpack_require__(731).sign"

    def evaluate(self, expression):
        if "__reverseDeepAgentHooks" in expression and "module_hooks" in expression and "moduleIdValue" in expression:
            self.installed = True
            return {
                "ok": True,
                "installed": [
                    {
                        "moduleId": self.module_id,
                        "exportName": self.export_name,
                        "functionName": self.export_name,
                        "requirePath": "window.__webpack_require__",
                        "hookPath": self.hook_path,
                    }
                ],
                "missing": [],
                "eventCount": len(self.events),
            }
        if "__reverseDeepAgentHooks" in expression and "module_export_" in expression and "eventCount" in expression:
            return {"ok": True, "events": list(self.events), "eventCount": len(self.events), "installed": {self.hook_path: self.installed}}
        if "__webpack_require__(731).sign" in expression:
            if self.installed:
                self.events.append(
                    {
                        "type": "module_export_call",
                        "payload": {
                            "moduleId": self.module_id,
                            "exportName": self.export_name,
                            "hookPath": self.hook_path,
                            "argCount": 2,
                        },
                    }
                )
                self.events.append(
                    {
                        "type": "module_export_return",
                        "payload": {
                            "moduleId": self.module_id,
                            "exportName": self.export_name,
                            "hookPath": self.hook_path,
                            "result": {"type": "string", "preview": "sig-demo"},
                        },
                    }
                )
            return "sig-demo"
        raise AssertionError(f"unexpected expression: {expression}")


class ModuleDiscoveryPage:
    url = "https://example.test/app"

    def __init__(self, source: str = WEBPACK_MINIFIED_SOURCE) -> None:
        self.source = source
        self.triggered = False
        self.runtime_payload = None

    def content(self):
        return '<html><head><script src="/assets/app.js"></script></head><body></body></html>'

    def evaluate(self, expression):
        if "__REVERSE_AGENT_MODULE_DISCOVERY__" in expression:
            if self.runtime_payload is not None:
                return self.runtime_payload
            raise AssertionError(f"unexpected expression: {expression}")
        if "fetch(" in expression and "/assets/app.js" in expression:
            return self.source
        if "__webpack_require__(731).sign" in expression:
            self.triggered = True
            return "sig-demo"
        raise AssertionError(f"unexpected expression: {expression}")


class AsyncChunkLoadPage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.executed_chunk_ids: list[str] = []

    def evaluate(self, expression):
        if "__REVERSE_AGENT_ASYNC_CHUNK_LOAD__" in expression:
            self.executed_chunk_ids.append("731")
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
        raise AssertionError(f"unexpected expression: {expression}")


class ModuleFederationProbePage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.expressions: list[str] = []

    def evaluate(self, expression):
        self.expressions.append(expression)
        if "__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__" in expression:
            return {
                "marker": "__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "containerPath": "window.remoteApp",
                "exposedName": "./sign",
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
        raise AssertionError(f"unexpected expression: {expression}")


class CustomLoaderTraversalPlanManagerTests(unittest.TestCase):
    def test_custom_loader_traversal_plan_accepts_chunk_graph_candidates_without_execution(self) -> None:
        spec = CustomLoaderTraversalPlanSpec.from_context(
            {
                "chunk_graph": {
                    "customLoaderCandidates": [
                        {
                            "chunkId": "custom-sign",
                            "target": "window.__customLoader.load",
                            "loaderKind": "custom-loader",
                            "edgeType": "custom-loader-candidate",
                            "runtimePath": "window.__customLoader",
                        },
                        {
                            "chunkId": "sign-dynamic",
                            "target": "import('/assets/sign.js')",
                            "loaderKind": "dynamic-import",
                            "edgeType": "dynamic-import",
                        },
                        {
                            "chunkId": "remote-sign",
                            "target": "window.remoteApp.get('./sign')",
                            "loaderKind": "module-federation",
                            "edgeType": "module-federation-expose",
                        },
                        {
                            "chunkId": "731",
                            "target": "/assets/731.js",
                            "loaderKind": "webpack-runtime",
                            "edgeType": "runtime-async-chunk",
                            "runtimePath": "window.__webpack_require__",
                        },
                    ]
                }
            }
        )

        result = CustomLoaderTraversalPlanManager().plan(spec)

        self.assertEqual(result.status, "planned")
        self.assertTrue(result.side_effect_policy["plan_only"])
        self.assertFalse(result.side_effect_policy["runtime_loader_executed"])
        self.assertFalse(result.side_effect_policy["chunk_request_sent"])
        self.assertFalse(result.side_effect_policy["dynamic_import_executed"])
        self.assertFalse(result.side_effect_policy["module_factory_invoked"])
        self.assertFalse(result.side_effect_policy["module_federation_get_init_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.custom-loader-traversal-plan.v1")
        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["candidate_count"], 4)
        classifications = {item["chunk_id"]: item["classification"] for item in plan["candidates"]}
        self.assertEqual(classifications["custom-sign"], "arbitrary_custom_loader")
        self.assertEqual(classifications["sign-dynamic"], "dynamic_import_execution_required")
        self.assertEqual(classifications["remote-sign"], "module_federation_get_init_required")
        self.assertEqual(classifications["731"], "webpack_loader_supported_elsewhere")
        follow_ups = {item["chunk_id"]: item["recommended_follow_up"] for item in plan["candidates"]}
        self.assertEqual(follow_ups["731"], "use_async_chunk_load_with_review_approval")
        dynamic = next(item for item in plan["candidates"] if item["chunk_id"] == "sign-dynamic")
        self.assertIn("dynamic_import_executes_module_body", dynamic["blocking_reasons"])
        federation = next(item for item in plan["candidates"] if item["chunk_id"] == "remote-sign")
        self.assertIn("module_federation_get_init_may_execute_remote_code", federation["blocking_reasons"])

    def test_custom_loader_traversal_plan_blocks_empty_explicit_request(self) -> None:
        spec = CustomLoaderTraversalPlanSpec.from_context({"custom_loader_traversal": True})

        result = CustomLoaderTraversalPlanManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "no_custom_loader_candidates")
        self.assertEqual(result.plan["status"], "blocked")
        self.assertEqual(result.plan["next_action"], "provide_custom_loader_candidates_from_chunk_graph")
        self.assertTrue(result.side_effect_policy["plan_only"])


class ModuleFederationGetInitPlanManagerTests(unittest.TestCase):
    def test_module_federation_get_init_plan_accepts_module_candidates_without_execution(self) -> None:
        spec = ModuleFederationGetInitPlanSpec.from_context(
            {
                "module_candidates": [
                    {
                        "kind": "module-federation",
                        "discovery_source": "module_federation",
                        "runtime_path": "window.remoteApp",
                        "module_id": "./sign",
                        "export_names": ["sign"],
                        "hook_paths": ["window.remoteApp.__reverseAgentExposes[\"./sign\"].sign"],
                    },
                    {
                        "kind": "module-federation",
                        "discovery_source": "module_federation",
                        "runtime_path": "window.remoteOther",
                        "module_id": "./token",
                        "export_names": [],
                        "hook_paths": [],
                    },
                ]
            }
        )

        result = ModuleFederationGetInitPlanManager().plan(spec)

        self.assertEqual(result.status, "planned")
        self.assertTrue(result.side_effect_policy["plan_only"])
        self.assertFalse(result.side_effect_policy["container_init_executed"])
        self.assertFalse(result.side_effect_policy["remote_get_called"])
        self.assertFalse(result.side_effect_policy["remote_factory_invoked"])
        self.assertFalse(result.side_effect_policy["shared_scope_mutated"])
        self.assertFalse(result.side_effect_policy["remote_code_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        plan = result.plan
        self.assertEqual(plan["schema_version"], "reverse-deepagent.module-federation-get-init-plan.v1")
        self.assertEqual(plan["status"], "ready_for_review")
        self.assertEqual(plan["candidate_count"], 2)
        self.assertEqual(plan["container_count"], 2)
        self.assertEqual(plan["exposed_module_count"], 2)
        self.assertEqual(plan["function_path_candidate_count"], 1)
        by_module = {item["module_id"]: item for item in plan["candidates"]}
        self.assertEqual(by_module["./sign"]["classification"], "function_path_candidate_available")
        self.assertEqual(by_module["./sign"]["recommended_follow_up"], "prefer_hook_function_candidate_without_get_init_execution")
        self.assertEqual(by_module["./token"]["classification"], "remote_exposed_module_get_init_required")
        self.assertIn("remote_factory_executes_remote_module_body", by_module["./token"]["blocking_reasons"])

    def test_module_federation_get_init_plan_blocks_unsafe_container_path(self) -> None:
        spec = ModuleFederationGetInitPlanSpec.from_context(
            {
                "container_path": "window.remoteApp.init(window.__webpack_share_scopes__.default)",
                "exposed_name": "./sign",
            }
        )

        result = ModuleFederationGetInitPlanManager().plan(spec)

        self.assertEqual(result.status, "planned")
        candidate = result.plan["candidates"][0]
        self.assertEqual(candidate["status"], "blocked")
        self.assertEqual(candidate["classification"], "unsupported_container_path")
        self.assertIn("dynamic_container_path_execution_not_supported", candidate["blocking_reasons"])
        self.assertFalse(candidate["side_effect_policy"]["executed_now"])

    def test_module_federation_get_init_plan_blocks_empty_explicit_request(self) -> None:
        spec = ModuleFederationGetInitPlanSpec.from_context({"module_federation_get_init": True})

        result = ModuleFederationGetInitPlanManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "no_module_federation_candidates")
        self.assertEqual(result.plan["status"], "blocked")
        self.assertEqual(result.plan["next_action"], "provide_module_federation_candidates_from_module_discovery")


class ModuleFederationGetInitProbeManagerTests(unittest.TestCase):
    def test_module_federation_get_init_probe_plans_without_execute_flag(self) -> None:
        page = ModuleFederationProbePage()
        spec = ModuleFederationGetInitProbeSpec.from_context(
            {
                "container_path": "window.remoteApp",
                "exposed_name": "./sign",
            }
        )

        result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.plan["status"], "ready_for_review")
        self.assertFalse(result.execution["attempted"])
        self.assertEqual(page.expressions, [])
        self.assertTrue(result.side_effect_policy["plan_only"])
        self.assertFalse(result.side_effect_policy["container_init_executed"])
        self.assertFalse(result.side_effect_policy["remote_get_called"])

    def test_module_federation_get_init_probe_blocks_without_review_approval(self) -> None:
        page = ModuleFederationProbePage()
        spec = ModuleFederationGetInitProbeSpec.from_context(
            {
                "container_path": "window.remoteApp",
                "exposed_name": "./sign",
                "execute_module_federation_get_init": True,
            }
        )

        result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.execution["attempted"])
        self.assertEqual(page.expressions, [])

    def test_module_federation_get_init_probe_blocks_function_path_candidate(self) -> None:
        page = ModuleFederationProbePage()
        spec = ModuleFederationGetInitProbeSpec.from_context(
            {
                "module_federation_candidates": [
                    {
                        "kind": "module-federation",
                        "runtime_path": "window.remoteApp",
                        "module_id": "./sign",
                        "export_names": ["sign"],
                        "hook_paths": ["window.remoteApp.__reverseAgentExposes[\"./sign\"].sign"],
                        "discovery_source": "module_federation",
                    }
                ],
                "execute_module_federation_get_init": True,
                "review_approved": True,
            }
        )

        result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "prefer_existing_function_path_candidate")
        self.assertFalse(result.execution["attempted"])
        self.assertEqual(page.expressions, [])

    def test_module_federation_get_init_probe_executes_reviewed_get_init_without_factory(self) -> None:
        page = ModuleFederationProbePage()
        spec = ModuleFederationGetInitProbeSpec.from_context(
            {
                "module_federation_candidates": [
                    {
                        "kind": "module-federation",
                        "runtime_path": "window.remoteApp",
                        "module_id": "./sign",
                        "export_names": [],
                        "hook_paths": [],
                        "discovery_source": "module_federation",
                    }
                ],
                "execute_module_federation_get_init": True,
                "review_approved": True,
            }
        )

        result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(len(page.expressions), 1)
        self.assertIn("__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__", page.expressions[0])
        self.assertTrue(result.execution["containerInitCalled"])
        self.assertTrue(result.execution["remoteGetCalled"])
        self.assertFalse(result.execution["remoteFactoryInvoked"])
        self.assertEqual(result.execution["factoryType"], "function")
        self.assertTrue(result.side_effect_policy["container_init_executed"])
        self.assertTrue(result.side_effect_policy["remote_get_called"])
        self.assertFalse(result.side_effect_policy["remote_factory_invoked"])
        self.assertFalse(result.side_effect_policy["remote_code_executed"])


class ModuleDiscoveryManagerTests(unittest.TestCase):
    def test_from_context_accepts_query_or_discovery_flag(self) -> None:
        by_query = ModuleDiscoverySpec.from_context({"module_query": "sign"})
        by_flag = ModuleDiscoverySpec.from_context(
            {
                "discover_modules": True,
                "require_path": "window.__r",
                "module_runtime_paths": "window.__r, window.__viteModules, window.remoteApp",
            }
        )

        self.assertIsNotNone(by_query)
        assert by_query is not None
        self.assertEqual(by_query.query, "sign")
        self.assertEqual(by_query.require_path, "window.__webpack_require__")
        self.assertIsNotNone(by_flag)
        assert by_flag is not None
        self.assertEqual(by_flag.require_path, "window.__r")
        self.assertEqual(by_flag.module_runtime_paths, ["window.__r", "window.__viteModules", "window.remoteApp"])
        self.assertIsNone(ModuleDiscoverySpec.from_context({}))

    def test_discovers_webpack_like_module_exports_from_fixture_source(self) -> None:
        page = ModuleDiscoveryPage()
        spec = ModuleDiscoverySpec.from_context({"module_query": "sign"})

        result = ModuleDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.modules), 1)
        self.assertEqual(result.modules[0]["module_id"], "731")
        self.assertEqual(result.modules[0]["export_names"], ["sign"])
        self.assertEqual(result.candidates[0]["module_id"], "731")
        self.assertEqual(result.candidates[0]["export_name"], "sign")
        self.assertEqual(result.candidates[0]["hook_path"], "window.__webpack_require__(731).sign")
        self.assertFalse(result.trigger["attempted"])

    def test_discovers_candidates_with_custom_require_path_and_trigger(self) -> None:
        page = ModuleDiscoveryPage()
        spec = ModuleDiscoverySpec.from_context(
            {
                "discover_modules": True,
                "module_query": "sign",
                "require_path": "window.__r",
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            }
        )

        result = ModuleDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(page.triggered)
        self.assertTrue(result.trigger["ok"])
        self.assertEqual(result.candidates[0]["hook_path"], "window.__r(731).sign")

    def test_discovers_runtime_cache_and_registry_exports_without_requiring_modules(self) -> None:
        page = ModuleDiscoveryPage(source="")
        page.runtime_payload = {
            "ok": True,
            "status": "success",
            "requirePath": "window.__webpack_require__",
            "cacheKeyCount": 1,
            "registryKeyCount": 1,
            "cacheModules": [
                {
                    "moduleId": "731",
                    "exportNames": ["sign"],
                    "exportTypes": {"sign": "function"},
                    "sourcePreview": "async function sign(keyword, timestamp) { return 'sig'; }",
                }
            ],
            "registryModules": [
                {
                    "moduleId": "732",
                    "source": "function(module) { module.exports = { async token(keyword) { return keyword; } }; }",
                    "sourcePreview": "function(module) { module.exports = { async token(keyword) {",
                }
            ],
        }
        spec = ModuleDiscoverySpec.from_context({"discover_modules": True})

        result = ModuleDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.runtime["status"], "success")
        self.assertEqual(result.runtime["cache_key_count"], 1)
        self.assertEqual(result.runtime["registry_key_count"], 1)
        self.assertEqual(result.runtime["module_count"], 2)
        by_id = {item["module_id"]: item for item in result.modules}
        self.assertEqual(by_id["731"]["discovery_source"], "runtime_cache")
        self.assertEqual(by_id["731"]["export_names"], ["sign"])
        self.assertEqual(by_id["732"]["discovery_source"], "runtime_registry")
        self.assertEqual(by_id["732"]["export_names"], ["token"])
        hook_paths = {item["hook_path"] for item in result.candidates}
        self.assertEqual(hook_paths, {"window.__webpack_require__(731).sign", "window.__webpack_require__(732).token"})

    def test_discovers_custom_runtime_and_federation_function_path_candidates(self) -> None:
        page = ModuleDiscoveryPage(source="")
        page.runtime_payload = {
            "ok": True,
            "status": "success",
            "requirePath": "window.__webpack_require__",
            "runtimes": [
                {
                    "runtimePath": "window.__viteModules",
                    "runtimeKind": "object-runtime",
                    "customKeyCount": 2,
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
                            "exposedName": "./sign",
                            "exportNames": ["sign"],
                            "exportTypes": {"sign": "function"},
                            "hookPaths": ["window.remoteApp.__reverseAgentExposes[\"./sign\"].sign"],
                            "sourcePreview": "function sign(keyword) { return keyword; }",
                        }
                    ],
                },
            ],
        }
        spec = ModuleDiscoverySpec.from_context(
            {
                "discover_modules": True,
                "module_runtime_paths": ["window.__webpack_require__", "window.__viteModules", "window.remoteApp"],
                "module_query": "sign",
            }
        )

        result = ModuleDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.runtime["runtime_paths"], ["window.__viteModules", "window.remoteApp"])
        self.assertEqual(result.runtime["runtime_kinds"], ["object-runtime", "module-federation"])
        self.assertEqual(result.runtime["custom_key_count"], 2)
        self.assertEqual(result.runtime["federation_key_count"], 1)
        by_source = {item["discovery_source"]: item for item in result.modules}
        self.assertEqual(by_source["custom_runtime"]["hook_kind"], "function-path")
        self.assertEqual(by_source["module_federation"]["hook_kind"], "function-path")
        candidates = {item["export_name"]: item for item in result.candidates}
        self.assertEqual(candidates["buildSign"]["hook_path"], 'window.__viteModules["/src/sign.ts"].buildSign')
        self.assertEqual(candidates["buildSign"]["hook_kind"], "function-path")
        self.assertEqual(candidates["sign"]["hook_path"], 'window.remoteApp.__reverseAgentExposes["./sign"].sign')
        self.assertEqual(candidates["sign"]["discovery_source"], "module_federation")

    def test_discovers_async_chunk_graph_without_executing_loaders(self) -> None:
        source = """
        const lazySign = () => import("./chunks/sign-panel.js");
        __webpack_require__.e(731).then(__webpack_require__.bind(__webpack_require__, 731));
        importScripts("/workers/sign-worker.js");
        """
        page = ModuleDiscoveryPage(source=source)
        page.runtime_payload = {
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
                "customLoaderCandidates": [{"target": "window.__customLoader.load", "chunkId": "custom-sign"}],
            },
            "cacheModules": [],
            "registryModules": [],
        }
        spec = ModuleDiscoverySpec.from_context({"discover_modules": True, "module_query": "sign"})

        result = ModuleDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.candidates, [])
        graph = result.chunk_graph
        self.assertEqual(graph["status"], "success")
        self.assertEqual(graph["script_edge_count"], 2)
        self.assertEqual(graph["runtime_loader_count"], 1)
        self.assertGreaterEqual(graph["candidate_count"], 3)
        self.assertFalse(graph["side_effect_policy"]["runtime_loader_executed"])
        self.assertFalse(graph["side_effect_policy"]["chunk_request_sent"])
        edge_types = {item["edge_type"] for item in graph["candidates"]}
        self.assertIn("dynamic-import", edge_types)
        self.assertIn("worker-importScripts", edge_types)
        self.assertIn("runtime-async-chunk", edge_types)
        loader = graph["runtime_loaders"][0]
        self.assertTrue(loader["has_async_chunk_loader"])
        self.assertTrue(loader["has_chunk_filename_resolver"])
        self.assertEqual(loader["loader_registry_keys"], ["j"])
        self.assertEqual(result.to_dict()["chunk_graph_candidate_count"], graph["candidate_count"])

    def test_async_chunk_load_plans_by_default_without_executing_loader(self) -> None:
        page = AsyncChunkLoadPage()
        spec = AsyncChunkLoadSpec.from_context(
            {
                "chunk_candidate": {
                    "chunk_id": "731",
                    "target": "/assets/731.js",
                    "loader_kind": "webpack-runtime",
                    "runtime_path": "window.__webpack_require__",
                }
            }
        )

        result = AsyncChunkLoadManager().plan_or_execute(page, spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.plan["status"], "ready_for_review")
        self.assertTrue(result.plan["review_required"])
        self.assertFalse(result.execution["attempted"])
        self.assertFalse(page.executed_chunk_ids)
        self.assertTrue(result.side_effect_policy["plan_only_by_default"])
        self.assertTrue(result.side_effect_policy["requires_review_approval"])
        self.assertFalse(result.side_effect_policy["module_factory_invoked"])

    def test_async_chunk_load_blocks_execution_without_review_approval(self) -> None:
        page = AsyncChunkLoadPage()
        spec = AsyncChunkLoadSpec.from_context(
            {
                "chunk_id": "731",
                "loader_kind": "webpack-runtime",
                "runtime_path": "window.__webpack_require__",
                "execute_chunk_load": True,
            }
        )

        result = AsyncChunkLoadManager().plan_or_execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.execution["attempted"])
        self.assertFalse(page.executed_chunk_ids)

    def test_async_chunk_load_executes_reviewed_webpack_loader_and_records_registry_diff(self) -> None:
        page = AsyncChunkLoadPage()
        spec = AsyncChunkLoadSpec.from_context(
            {
                "chunk_id": "731",
                "target": "/assets/731.js",
                "loader_kind": "webpack-runtime",
                "runtime_path": "window.__webpack_require__",
                "execute_chunk_load": True,
                "review_approved": True,
            }
        )

        result = AsyncChunkLoadManager().plan_or_execute(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(page.executed_chunk_ids, ["731"])
        self.assertTrue(result.execution["ok"])
        self.assertEqual(result.execution["addedRegistryKeys"], ["731"])
        self.assertTrue(result.side_effect_policy["runtime_loader_executed"])
        self.assertTrue(result.side_effect_policy["chunk_request_sent"])
        self.assertFalse(result.side_effect_policy["dynamic_import_executed"])
        self.assertFalse(result.side_effect_policy["module_factory_invoked"])

    def test_async_chunk_load_blocks_arbitrary_custom_loader_execution(self) -> None:
        page = AsyncChunkLoadPage()
        spec = AsyncChunkLoadSpec.from_context(
            {
                "chunk_id": "custom-sign",
                "target": "window.__customLoader.load",
                "loader_kind": "custom-loader",
                "execute_chunk_load": True,
                "review_approved": True,
            }
        )

        result = AsyncChunkLoadManager().plan_or_execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "unsupported_loader_kind_for_execution")
        self.assertFalse(result.execution["attempted"])
        self.assertFalse(page.executed_chunk_ids)
        self.assertFalse(result.plan["execution_supported"])
        self.assertFalse(result.plan["side_effect_policy"]["custom_loader_executed"])

    def test_async_chunk_load_blocks_expression_runtime_path_execution(self) -> None:
        page = AsyncChunkLoadPage()
        spec = AsyncChunkLoadSpec.from_context(
            {
                "chunk_id": "731",
                "loader_kind": "webpack-runtime",
                "runtime_path": "window.sideEffect(), window.__webpack_require__",
                "execute_chunk_load": True,
                "review_approved": True,
            }
        )

        result = AsyncChunkLoadManager().plan_or_execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "unsupported_runtime_path_for_execution")
        self.assertFalse(result.execution["attempted"])
        self.assertFalse(page.executed_chunk_ids)


class ModuleHookManagerTests(unittest.TestCase):
    def test_from_context_accepts_webpack_module_export(self) -> None:
        spec = ModuleHookSpec.from_context(
            {
                "webpack_module_id": 731,
                "export_name": "sign",
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.module_id, "731")
        self.assertEqual(spec.export_name, "sign")
        self.assertEqual(spec.require_path, "window.__webpack_require__")
        self.assertEqual(spec.hook_path(), "window.__webpack_require__(731).sign")

    def test_hook_path_quotes_string_module_ids_and_non_identifier_exports(self) -> None:
        spec = ModuleHookSpec.from_context(
            {
                "module_id": "./src/sign.ts",
                "export_name": "default-sign",
                "require_path": "window.__webpack_require__",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.hook_path(), 'window.__webpack_require__("./src/sign.ts")["default-sign"]')

    def test_install_and_snapshot_module_hook(self) -> None:
        page = ModuleHookPage()
        manager = ModuleHookManager()
        spec = ModuleHookSpec.from_context(
            {
                "module_id": "731",
                "export_name": "sign",
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        result = manager.install(page, spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.installed[0]["moduleId"], "731")
        self.assertEqual(result.installed[0]["exportName"], "sign")
        self.assertEqual(result.events[0]["type"], "module_export_call")
        self.assertEqual(result.events[1]["type"], "module_export_return")
        self.assertEqual(result.trigger["ok"], True)
        self.assertEqual(result.trigger["result"]["value"], "sig-demo")

    def test_missing_module_context_is_unsupported(self) -> None:
        self.assertIsNone(ModuleHookSpec.from_context({}))
        self.assertIsNone(ModuleHookSpec.from_context({"module_id": "731"}))
        self.assertIsNone(ModuleHookSpec.from_context({"export_name": "sign"}))


if __name__ == "__main__":
    unittest.main()
