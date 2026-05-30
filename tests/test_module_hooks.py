import unittest

from reverse_deepagent.browser.hooks import (
    ModuleDiscoveryManager,
    ModuleDiscoverySpec,
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
