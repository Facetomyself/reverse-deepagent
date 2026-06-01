import unittest
from typing import Any

from reverse_deepagent.browser.hooks import (
    AsyncChunkLoadManager,
    AsyncChunkLoadSpec,
    AsyncChunkModuleDiffManager,
    AsyncChunkModuleDiffSpec,
    AsyncChunkModuleHookManager,
    AsyncChunkModuleHookSpec,
    CustomLoaderExecutionManager,
    CustomLoaderExecutionPreflightManager,
    CustomLoaderExecutionPreflightSpec,
    CustomLoaderExecutionSpec,
    CustomLoaderModuleDiffManager,
    CustomLoaderModuleDiffSpec,
    CustomLoaderModuleHookManager,
    CustomLoaderModuleHookSpec,
    CustomLoaderTraversalPlanManager,
    CustomLoaderTraversalPlanSpec,
    ModuleFederationFactoryInvokeManager,
    ModuleFederationFactoryInvokeSpec,
    ModuleFederationExportHookPlanManager,
    ModuleFederationExportHookPlanSpec,
    ModuleFederationExportHookInstallManager,
    ModuleFederationExportHookInstallSpec,
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


class CustomLoaderExecutionPage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.executions: list[str] = []

    def evaluate(self, expression):
        if "__REVERSE_AGENT_CUSTOM_LOADER_EXECUTION__" in expression:
            self.executions.append("window.__customLoader.load")
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
                "before": {"registryKeys": ["1"], "cacheKeys": []},
                "after": {"registryKeys": ["1", "884"], "cacheKeys": ["884"]},
                "result": {"type": "object", "keys": ["moduleId"], "preview": '{"moduleId":"884"}'},
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


class ModuleFederationFactoryPage(ModuleFederationProbePage):
    def __init__(self) -> None:
        super().__init__()
        self.factory_invocations: list[str] = []

    def evaluate(self, expression):
        self.expressions.append(expression)
        if "__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__" in expression:
            self.factory_invocations.append("./sign")
            return {
                "marker": "__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__",
                "attempted": True,
                "ok": True,
                "status": "success",
                "containerPath": "window.remoteApp",
                "exposedName": "./sign",
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
                "addedSharedScopeKeys": ["default"],
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


class CustomLoaderExecutionPreflightManagerTests(unittest.TestCase):
    def _plan(self) -> dict[str, Any]:
        spec = CustomLoaderTraversalPlanSpec.from_context(
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
            }
        )
        return CustomLoaderTraversalPlanManager().plan(spec).plan

    def test_blocks_without_review_approval(self) -> None:
        spec = CustomLoaderExecutionPreflightSpec.from_context(
            {
                "custom_loader_traversal_plan": self._plan(),
                "candidate_index": 0,
            }
        )

        result = CustomLoaderExecutionPreflightManager().preflight(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertIn("review_approval_required", result.preflight["blocking_reasons"])
        self.assertTrue(result.side_effect_policy["preflight_only"])
        self.assertFalse(result.side_effect_policy["loader_invoked"])
        self.assertFalse(result.side_effect_policy["chunk_request_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_allows_reviewed_strict_dotted_custom_loader_candidate(self) -> None:
        spec = CustomLoaderExecutionPreflightSpec.from_context(
            {
                "custom_loader_traversal_plan": self._plan(),
                "candidate_index": 0,
                "review_approved": True,
                "expected_loader_path": "window.__customLoader.load",
            }
        )

        result = CustomLoaderExecutionPreflightManager().preflight(spec)

        self.assertEqual(result.status, "ready_for_execution_review")
        self.assertEqual(result.preflight["schema_version"], "reverse-deepagent.custom-loader-execution-preflight.v1")
        self.assertEqual(result.preflight["blocking_reasons"], [])
        self.assertEqual(result.preflight["next_action"], "execute_custom_loader_with_review_approval")
        self.assertFalse(result.side_effect_policy["runtime_loader_executed"])
        self.assertFalse(result.side_effect_policy["browser_state_mutated"])

    def test_blocks_dynamic_import_candidate(self) -> None:
        plan_spec = CustomLoaderTraversalPlanSpec.from_context(
            {
                "custom_loader_candidates": [
                    {
                        "chunk_id": "dynamic-sign",
                        "target": "import('/assets/sign.js')",
                        "loader_kind": "dynamic-import",
                        "edge_type": "dynamic-import",
                    }
                ]
            }
        )
        spec = CustomLoaderExecutionPreflightSpec.from_context(
            {
                "custom_loader_traversal_plan": CustomLoaderTraversalPlanManager().plan(plan_spec).plan,
                "candidate_index": 0,
                "review_approved": True,
            }
        )

        result = CustomLoaderExecutionPreflightManager().preflight(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("unsupported_loader_kind_for_custom_execution_preflight", result.preflight["blocking_reasons"])
        self.assertIn("strict_dotted_loader_path_required", result.preflight["blocking_reasons"])
        self.assertIn("dynamic_import_requires_dedicated_gate", result.preflight["blocking_reasons"])


class CustomLoaderExecutionManagerTests(unittest.TestCase):
    def _preflight(self) -> dict[str, Any]:
        return {
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

    def test_blocks_without_review_approval(self) -> None:
        spec = CustomLoaderExecutionSpec.from_context({"custom_loader_execution_preflight": self._preflight()})

        result = CustomLoaderExecutionManager().execute(CustomLoaderExecutionPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.side_effect_policy["loader_invoked"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_blocks_when_preflight_not_ready(self) -> None:
        preflight = self._preflight()
        preflight["status"] = "blocked"
        preflight["blocking_reasons"] = ["strict_dotted_loader_path_required"]
        spec = CustomLoaderExecutionSpec.from_context({"custom_loader_execution_preflight": preflight, "review_approved": True})

        result = CustomLoaderExecutionManager().execute(CustomLoaderExecutionPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "custom_loader_preflight_not_ready")

    def test_executes_reviewed_custom_loader_and_records_registry_diff(self) -> None:
        page = CustomLoaderExecutionPage()
        spec = CustomLoaderExecutionSpec.from_context(
            {
                "custom_loader_execution_preflight": self._preflight(),
                "review_approved": True,
                "loader_arguments": [{"chunk": "884"}],
            }
        )

        result = CustomLoaderExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(page.executions, ["window.__customLoader.load"])
        self.assertTrue(result.side_effect_policy["loader_invoked"])
        self.assertTrue(result.side_effect_policy["custom_loader_executed"])
        self.assertFalse(result.side_effect_policy["dynamic_import_executed"])
        self.assertFalse(result.side_effect_policy["module_federation_get_init_executed"])
        self.assertEqual(result.execution["addedRegistryKeys"], ["884"])
        self.assertEqual(result.execution["addedCacheKeys"], ["884"])
        self.assertEqual(result.execution["result"]["type"], "object")

    def test_blocks_dynamic_import_and_webpack_candidates(self) -> None:
        for loader_kind, edge_type, reason in (
            ("dynamic-import", "dynamic-import", "dynamic_import_requires_dedicated_gate"),
            ("webpack-runtime", "runtime-async-chunk", "use_async_chunk_load_for_webpack_loader"),
        ):
            preflight = self._preflight()
            preflight["selected_candidate"] = {
                "classification": "arbitrary_custom_loader",
                "loader_kind": loader_kind,
                "edge_type": edge_type,
                "loader_path": "window.__customLoader.load",
            }
            spec = CustomLoaderExecutionSpec.from_context({"custom_loader_execution_preflight": preflight, "review_approved": True})

            result = CustomLoaderExecutionManager().execute(CustomLoaderExecutionPage(), spec)

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.reason, reason)


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


class ModuleFederationFactoryInvokeManagerTests(unittest.TestCase):
    def test_module_federation_factory_invoke_plans_without_execute_flag(self) -> None:
        page = ModuleFederationFactoryPage()
        spec = ModuleFederationFactoryInvokeSpec.from_context(
            {
                "container_path": "window.remoteApp",
                "exposed_name": "./sign",
            }
        )

        result = ModuleFederationFactoryInvokeManager().plan_or_invoke(page, spec)

        self.assertEqual(result.status, "planned")
        self.assertFalse(result.factory_execution["attempted"])
        self.assertEqual(page.expressions, [])
        self.assertTrue(result.side_effect_policy["plan_only"])

    def test_module_federation_factory_invoke_blocks_without_review_approval(self) -> None:
        page = ModuleFederationFactoryPage()
        spec = ModuleFederationFactoryInvokeSpec.from_context(
            {
                "container_path": "window.remoteApp",
                "exposed_name": "./sign",
                "execute_module_federation_factory": True,
            }
        )

        result = ModuleFederationFactoryInvokeManager().plan_or_invoke(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.factory_execution["attempted"])
        self.assertEqual(page.expressions, [])

    def test_module_federation_factory_invoke_executes_reviewed_factory_and_summarizes_exports(self) -> None:
        page = ModuleFederationFactoryPage()
        spec = ModuleFederationFactoryInvokeSpec.from_context(
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
                "execute_module_federation_factory": True,
                "review_approved": True,
            }
        )

        result = ModuleFederationFactoryInvokeManager().plan_or_invoke(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(page.factory_invocations, ["./sign"])
        self.assertEqual(len(page.expressions), 2)
        self.assertIn("__REVERSE_AGENT_MODULE_FEDERATION_GET_INIT_PROBE__", page.expressions[0])
        self.assertIn("__REVERSE_AGENT_MODULE_FEDERATION_FACTORY_INVOKE__", page.expressions[1])
        self.assertTrue(result.get_init_execution["remoteGetCalled"])
        self.assertTrue(result.factory_execution["remoteFactoryInvoked"])
        self.assertTrue(result.factory_execution["remoteCodeExecuted"])
        self.assertEqual(result.factory_execution["exportNames"], ["sign"])
        self.assertEqual(result.factory_execution["moduleType"], "object")
        self.assertTrue(result.side_effect_policy["remote_factory_invoked"])
        self.assertTrue(result.side_effect_policy["remote_code_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])


class ModuleFederationRemoteExportHookPage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.installed = False
        self.events: list[dict] = []
        self.hook_path = "window.remoteApp:./sign:sign"

    def evaluate(self, expression):
        if "remote_export_hooks" in expression and "installed.push" in expression:
            self.installed = True
            return {
                "ok": True,
                "installed": [
                    {
                        "hookPath": self.hook_path,
                        "containerPath": "window.remoteApp",
                        "exposedName": "./sign",
                        "exportName": "sign",
                        "functionName": "sign",
                    }
                ],
                "missing": [],
                "eventCount": len(self.events),
            }
        if "remote_export_" in expression and "eventCount" in expression:
            return {"ok": self.installed, "events": list(self.events), "eventCount": len(self.events), "installed": {self.hook_path: self.installed}}
        if "window.remoteAppSign" in expression:
            if self.installed:
                self.events.append({"type": "remote_export_call", "payload": {"hookPath": self.hook_path, "containerPath": "window.remoteApp", "exposedName": "./sign", "exportName": "sign", "argCount": 1}})
                self.events.append({"type": "remote_export_return", "payload": {"hookPath": self.hook_path, "containerPath": "window.remoteApp", "exposedName": "./sign", "exportName": "sign", "result": {"type": "string", "preview": "remote-sig"}}})
            return "remote-sig"
        raise AssertionError(f"unexpected expression: {expression}")


class ModuleFederationExportHookPlanManagerTests(unittest.TestCase):
    def test_module_federation_export_hook_plan_recommends_function_exports_without_installing_hooks(self) -> None:
        spec = ModuleFederationExportHookPlanSpec.from_context(
            {
                "module_federation_factory_invoke_result": {
                    "status": "success",
                    "factory_execution": {
                        "remoteFactoryInvoked": True,
                        "remoteCodeExecuted": True,
                        "containerPath": "window.remoteApp",
                        "exposedName": "./sign",
                        "moduleType": "object",
                        "exportNames": ["sign", "version"],
                        "exportPreviews": {
                            "sign": {"type": "function", "name": "sign", "preview": "function sign() {}"},
                            "version": {"type": "string", "preview": "1.0.0"},
                        },
                    },
                }
            }
        )

        result = ModuleFederationExportHookPlanManager().plan(spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.plan["status"], "ready_for_review")
        self.assertEqual(result.plan["candidate_count"], 2)
        self.assertEqual(result.plan["hookable_candidate_count"], 1)
        self.assertEqual(result.plan["next_action"], "review_module_federation_export_hook_plan")
        self.assertTrue(result.plan["review_required"])
        self.assertFalse(result.plan["automatic_hook_installation"])
        self.assertFalse(result.plan["recursive_federation_traversal"])
        hookable = result.plan["candidates"][0]
        self.assertEqual(hookable["export_name"], "sign")
        self.assertEqual(hookable["hook_kind"], "remote-export-wrapper")
        self.assertTrue(hookable["hookable"])
        unsupported = result.plan["candidates"][1]
        self.assertFalse(unsupported["hookable"])
        self.assertIn("unsupported_remote_export_type:string", unsupported["blocking_reasons"])
        self.assertTrue(result.side_effect_policy["plan_only"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])
        self.assertFalse(result.side_effect_policy["invokes_remote_factory"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_module_federation_export_hook_plan_blocks_without_factory_execution(self) -> None:
        spec = ModuleFederationExportHookPlanSpec.from_context(
            {
                "module_federation_factory_invoke_result": {
                    "status": "planned",
                    "factory_execution": {"remoteFactoryInvoked": False, "remoteCodeExecuted": False},
                }
            }
        )

        result = ModuleFederationExportHookPlanManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "remote_factory_execution_required")
        self.assertFalse(result.side_effect_policy["executes_remote_code"])


class ModuleFederationExportHookInstallManagerTests(unittest.TestCase):
    def _plan_payload(self) -> dict:
        return {
            "status": "planned",
            "plan": {
                "status": "ready_for_review",
                "source": "module_federation_factory_invoke_result",
                "candidates": [
                    {
                        "kind": "module-federation-remote-export",
                        "export_name": "sign",
                        "export_type": "function",
                        "function_name": "sign",
                        "container_path": "window.remoteApp",
                        "exposed_name": "./sign",
                        "hook_kind": "remote-export-wrapper",
                        "hookable": True,
                        "requires_review_approval": True,
                        "automatic_hook_installation": False,
                        "recursive_federation_traversal": False,
                    }
                ],
            },
        }

    def test_blocks_without_review_approval(self) -> None:
        spec = ModuleFederationExportHookInstallSpec.from_context(
            {
                "module_federation_export_hook_plan": self._plan_payload(),
                "selected_export_hook_candidate": {"container_path": "window.remoteApp", "exposed_name": "./sign", "export_name": "sign"},
            }
        )

        result = ModuleFederationExportHookInstallManager().install(ModuleFederationRemoteExportHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.side_effect_policy["review_approved"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])

    def test_installs_reviewed_remote_export_hook_and_captures_events(self) -> None:
        page = ModuleFederationRemoteExportHookPage()
        spec = ModuleFederationExportHookInstallSpec.from_context(
            {
                "module_federation_export_hook_plan": self._plan_payload(),
                "selected_export_hook_candidate": {"container_path": "window.remoteApp", "exposed_name": "./sign", "export_name": "sign"},
                "review_approved": True,
                "trigger_expression": "window.remoteAppSign('demo')",
            }
        )

        result = ModuleFederationExportHookInstallManager().install(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.side_effect_policy["review_approved"])
        self.assertTrue(result.side_effect_policy["remote_factory_invoked"])
        self.assertTrue(result.side_effect_policy["remote_code_executed"])
        self.assertFalse(result.side_effect_policy["recursive_federation_traversal"])
        self.assertEqual(result.installed[0]["hookPath"], "window.remoteApp:./sign:sign")
        self.assertEqual(result.events[0]["type"], "remote_export_call")
        self.assertEqual(result.trigger["ok"], True)

    def test_blocks_non_hookable_remote_export_candidate(self) -> None:
        plan = self._plan_payload()
        plan["plan"]["candidates"][0].update({"hook_kind": "manual-inspection", "hookable": False})
        spec = ModuleFederationExportHookInstallSpec.from_context(
            {
                "module_federation_export_hook_plan": plan,
                "review_approved": True,
            }
        )

        result = ModuleFederationExportHookInstallManager().install(ModuleFederationRemoteExportHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "unsupported_remote_export_hook_kind")



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

    def test_async_chunk_module_diff_recommends_hook_candidates_after_reviewed_load(self) -> None:
        spec = AsyncChunkModuleDiffSpec.from_context(
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
                            "hook_kind": "module-export",
                        },
                        {
                            "module_id": "100",
                            "runtime_path": "window.__webpack_require__",
                            "export_names": ["other"],
                        },
                    ]
                },
            }
        )

        result = AsyncChunkModuleDiffManager().plan(spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.diff["status"], "ready_for_review")
        self.assertEqual(result.diff["chunk_id"], "731")
        self.assertEqual(result.diff["added_registry_keys"], ["731"])
        self.assertEqual(result.diff["matched_module_count"], 1)
        self.assertEqual(result.diff["candidate_count"], 1)
        candidate = result.diff["hook_candidates"][0]
        self.assertEqual(candidate["module_id"], "731")
        self.assertEqual(candidate["export_name"], "sign")
        self.assertEqual(candidate["hook_path"], "window.__webpack_require__(731).sign")
        self.assertEqual(candidate["recommended_follow_up"], "hook_module_export_after_chunk_review")
        self.assertFalse(result.diff["automatic_hook_installation"])
        self.assertFalse(result.side_effect_policy["loads_chunk"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])
        self.assertFalse(result.side_effect_policy["evaluates_javascript"])

    def test_async_chunk_module_diff_blocks_without_successful_load(self) -> None:
        spec = AsyncChunkModuleDiffSpec.from_context(
            {
                "async_chunk_load_result": {
                    "status": "planned",
                    "execution": {"attempted": False, "ok": False},
                }
            }
        )

        result = AsyncChunkModuleDiffManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "successful_async_chunk_load_required")
        self.assertFalse(result.side_effect_policy["module_factory_invoked"])


class CustomLoaderModuleDiffManagerTests(unittest.TestCase):
    def test_custom_loader_module_diff_recommends_hook_candidates_after_reviewed_execution(self) -> None:
        spec = CustomLoaderModuleDiffSpec.from_context(
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
                        },
                        {
                            "module_id": "100",
                            "runtime_path": "window.__webpack_require__",
                            "export_names": ["other"],
                        },
                    ]
                },
            }
        )

        result = CustomLoaderModuleDiffManager().plan(spec)

        self.assertEqual(result.status, "planned")
        self.assertEqual(result.diff["schema_version"], "reverse-deepagent.custom-loader-module-diff.v1")
        self.assertEqual(result.diff["status"], "ready_for_review")
        self.assertEqual(result.diff["source"], "custom_loader_execution_result")
        self.assertEqual(result.diff["loader_path"], "window.__customLoader.load")
        self.assertEqual(result.diff["added_registry_keys"], ["884"])
        self.assertEqual(result.diff["added_cache_keys"], ["884"])
        self.assertEqual(result.diff["matched_module_count"], 1)
        self.assertEqual(result.diff["candidate_count"], 1)
        candidate = result.diff["hook_candidates"][0]
        self.assertEqual(candidate["kind"], "custom-loader-module-export")
        self.assertEqual(candidate["hook_kind"], "module-export")
        self.assertEqual(candidate["source"], "custom_loader_module_diff")
        self.assertEqual(candidate["module_id"], "884")
        self.assertEqual(candidate["export_name"], "sign")
        self.assertEqual(candidate["hook_path"], "window.__webpack_require__(884).sign")
        self.assertEqual(candidate["recommended_follow_up"], "hook_module_export_after_custom_loader_review")
        self.assertFalse(result.diff["automatic_hook_installation"])
        self.assertFalse(result.diff["module_factory_invoked"])
        self.assertFalse(result.side_effect_policy["executes_custom_loader"])
        self.assertFalse(result.side_effect_policy["loads_chunk"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])
        self.assertFalse(result.side_effect_policy["evaluates_javascript"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_custom_loader_module_diff_blocks_without_successful_execution(self) -> None:
        spec = CustomLoaderModuleDiffSpec.from_context(
            {
                "custom_loader_execution_result": {
                    "status": "blocked",
                    "execution": {"attempted": False, "ok": False, "loaderInvoked": False},
                }
            }
        )

        result = CustomLoaderModuleDiffManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "successful_custom_loader_execution_required")
        self.assertFalse(result.side_effect_policy["executes_custom_loader"])
        self.assertFalse(result.side_effect_policy["module_factory_invoked"])


class AsyncChunkModuleHookManagerTests(unittest.TestCase):
    def _diff_payload(self) -> dict:
        return {
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
                        "requires_review_approval": True,
                        "automatic_hook_installation": False,
                        "source": "async_chunk_module_diff",
                    }
                ],
            },
        }

    def test_blocks_without_review_approval(self) -> None:
        spec = AsyncChunkModuleHookSpec.from_context(
            {
                "async_chunk_module_diff": self._diff_payload(),
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
            }
        )

        result = AsyncChunkModuleHookManager().install(ModuleHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.side_effect_policy["review_approved"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])

    def test_installs_reviewed_candidate_by_delegating_to_module_hook_manager(self) -> None:
        page = ModuleHookPage()
        spec = AsyncChunkModuleHookSpec.from_context(
            {
                "async_chunk_module_diff": self._diff_payload(),
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
                "review_approved": True,
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            }
        )

        result = AsyncChunkModuleHookManager().install(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.side_effect_policy["review_approved"])
        self.assertTrue(result.side_effect_policy["installs_hooks"])
        self.assertTrue(result.side_effect_policy["delegates_to_module_hook_manager"])
        self.assertEqual(result.selected_candidate["source"], "async_chunk_module_diff")
        self.assertIsNotNone(result.module_hook_result)
        assert result.module_hook_result is not None
        self.assertEqual(result.module_hook_result.installed[0]["hookPath"], "window.__webpack_require__(731).sign")
        self.assertEqual(result.module_hook_result.events[0]["type"], "module_export_call")

    def test_blocks_candidate_not_from_async_chunk_diff(self) -> None:
        spec = AsyncChunkModuleHookSpec.from_context(
            {
                "async_chunk_module_diff": self._diff_payload(),
                "selected_hook_candidate": {
                    "module_id": "999",
                    "export_name": "other",
                    "runtime_path": "window.__webpack_require__",
                    "hook_kind": "module-export",
                    "source": "manual_candidate",
                },
                "review_approved": True,
            }
        )

        result = AsyncChunkModuleHookManager().install(ModuleHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "candidate_not_from_async_chunk_module_diff")


class CustomLoaderModuleHookManagerTests(unittest.TestCase):
    def _diff_payload(self) -> dict:
        return {
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
                        "requires_review_approval": True,
                        "automatic_hook_installation": False,
                        "source": "custom_loader_module_diff",
                    }
                ],
            },
        }

    def test_blocks_without_review_approval(self) -> None:
        spec = CustomLoaderModuleHookSpec.from_context(
            {
                "custom_loader_module_diff": self._diff_payload(),
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
            }
        )

        result = CustomLoaderModuleHookManager().install(ModuleHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.side_effect_policy["review_approved"])
        self.assertFalse(result.side_effect_policy["installs_hooks"])
        self.assertFalse(result.side_effect_policy["executes_custom_loader"])

    def test_installs_reviewed_candidate_by_delegating_to_module_hook_manager(self) -> None:
        page = ModuleHookPage()
        spec = CustomLoaderModuleHookSpec.from_context(
            {
                "custom_loader_module_diff": self._diff_payload(),
                "selected_hook_candidate": {"module_id": "731", "export_name": "sign"},
                "review_approved": True,
                "trigger_expression": "window.__webpack_require__(731).sign('sign', 1700000000000)",
            }
        )

        result = CustomLoaderModuleHookManager().install(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.side_effect_policy["review_approved"])
        self.assertTrue(result.side_effect_policy["installs_hooks"])
        self.assertTrue(result.side_effect_policy["delegates_to_module_hook_manager"])
        self.assertFalse(result.side_effect_policy["executes_custom_loader"])
        self.assertEqual(result.selected_candidate["source"], "custom_loader_module_diff")
        self.assertIsNotNone(result.module_hook_result)
        assert result.module_hook_result is not None
        self.assertEqual(result.module_hook_result.installed[0]["hookPath"], "window.__webpack_require__(731).sign")
        self.assertEqual(result.module_hook_result.events[0]["type"], "module_export_call")

    def test_blocks_candidate_not_from_custom_loader_module_diff(self) -> None:
        spec = CustomLoaderModuleHookSpec.from_context(
            {
                "custom_loader_module_diff": self._diff_payload(),
                "selected_hook_candidate": {
                    "module_id": "999",
                    "export_name": "other",
                    "runtime_path": "window.__webpack_require__",
                    "hook_kind": "module-export",
                    "source": "manual_candidate",
                },
                "review_approved": True,
            }
        )

        result = CustomLoaderModuleHookManager().install(ModuleHookPage(), spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "candidate_not_from_custom_loader_module_diff")



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
