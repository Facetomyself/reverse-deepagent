import unittest
from unittest.mock import patch

from reverse_deepagent.runtime import (
    RUNTIME_BACKEND_ENTRY_POINT_GROUP,
    RuntimeBackendCapabilities,
    RuntimeBackendRegistration,
    RuntimeBackendRegistry,
)
from reverse_deepagent.runtime.base import BrowserSessionInfo, ReverseRuntime, RuntimeExportBundle, WebReverseRuntime
from reverse_deepagent.runtime import registry as runtime_registry
from reverse_deepagent.schemas import ProtectionResult, ReconResult, RouterResult, TaskCard


class DummyRuntime(WebReverseRuntime):
    def ensure_browser_session(self) -> BrowserSessionInfo:
        return BrowserSessionInfo(healthy=True)

    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        raise NotImplementedError

    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class NonWebRuntime(ReverseRuntime):
    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class FakeEntryPoint:
    def __init__(self, name: str, value, group: str = RUNTIME_BACKEND_ENTRY_POINT_GROUP) -> None:
        self.name = name
        self.value = value
        self.group = group
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class FakeEntryPoints(list):
    def select(self, *, group: str):
        return FakeEntryPoints([entry_point for entry_point in self if entry_point.group == group])


class RuntimeRegistryTests(unittest.TestCase):

    def test_platform_neutral_runtime_does_not_require_browser_methods(self) -> None:
        runtime = NonWebRuntime()
        self.assertIsInstance(runtime, ReverseRuntime)
        self.assertNotIsInstance(runtime, WebReverseRuntime)
        self.assertFalse(hasattr(runtime, "ensure_browser_session"))
        self.assertFalse(hasattr(runtime, "run_web_recon"))

    def test_registry_resolves_aliases_and_lists_metadata(self) -> None:
        registry = RuntimeBackendRegistry()
        registry.register(
            RuntimeBackendRegistration(
                backend_id="dummy",
                aliases=("alias-dummy",),
                capabilities=RuntimeBackendCapabilities(
                    backend_id="dummy",
                    display_name="Dummy Runtime",
                    transport="in-process",
                    supports_web_recon=True,
                ),
                factory=lambda **_: DummyRuntime(),
            )
        )
        self.assertEqual(registry.resolve("alias-dummy").backend_id, "dummy")
        self.assertEqual(registry.backend_ids(), ["alias-dummy", "dummy"])
        metadata = registry.list_metadata()
        self.assertEqual(metadata[0]["backend_id"], "dummy")
        self.assertTrue(metadata[0]["supports_web_recon"])
        registration_metadata = registry.list_registration_metadata()
        self.assertEqual(registration_metadata[0]["backend_id"], "dummy")
        self.assertEqual(registration_metadata[0]["aliases"], ["alias-dummy"])
        self.assertEqual(registration_metadata[0]["keys"], ["dummy", "alias-dummy"])
        self.assertIsInstance(registry.create("dummy"), DummyRuntime)

    def test_registry_rejects_duplicate_keys(self) -> None:
        registry = RuntimeBackendRegistry()
        registration = RuntimeBackendRegistration(
            backend_id="dummy",
            capabilities=RuntimeBackendCapabilities(backend_id="dummy", display_name="Dummy Runtime"),
            factory=lambda **_: DummyRuntime(),
        )
        registry.register(registration)
        with self.assertRaises(ValueError):
            registry.register(registration)

    def test_registry_rejects_capability_backend_id_mismatch(self) -> None:
        registry = RuntimeBackendRegistry()
        with self.assertRaisesRegex(ValueError, "capability id mismatch"):
            registry.register(
                RuntimeBackendRegistration(
                    backend_id="dummy",
                    capabilities=RuntimeBackendCapabilities(backend_id="other", display_name="Other Runtime"),
                    factory=lambda **_: DummyRuntime(),
                )
            )

    def test_registry_reports_unknown_backends(self) -> None:
        registry = RuntimeBackendRegistry()
        with self.assertRaisesRegex(ValueError, "Unsupported runtime backend"):
            registry.resolve("missing")

    def test_registry_loads_entry_point_registration_without_invoking_factory(self) -> None:
        registry = RuntimeBackendRegistry()
        factory_calls: list[str] = []
        registration = RuntimeBackendRegistration(
            backend_id="plugin-web",
            aliases=("plugin-alias",),
            capabilities=RuntimeBackendCapabilities(
                backend_id="plugin-web",
                display_name="Plugin Web Runtime",
                transport="plugin",
                supports_web_recon=True,
            ),
            factory=lambda **_: factory_calls.append("called") or DummyRuntime(),
        )
        entry_point = FakeEntryPoint("plugin-web", registration)

        with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["plugin-web"])
        self.assertEqual(entry_point.load_count, 1)
        self.assertEqual(factory_calls, [])
        self.assertEqual(registry.resolve("plugin-alias").backend_id, "plugin-web")
        self.assertEqual(registry.list_metadata()[0]["transport"], "plugin")
        self.assertIsInstance(registry.create("plugin-web"), DummyRuntime)
        self.assertEqual(factory_calls, ["called"])

    def test_registry_loads_callable_entry_point_returning_multiple_registrations(self) -> None:
        def make_registration(backend_id: str) -> RuntimeBackendRegistration:
            return RuntimeBackendRegistration(
                backend_id=backend_id,
                capabilities=RuntimeBackendCapabilities(
                    backend_id=backend_id,
                    display_name=f"{backend_id} Runtime",
                    transport="plugin",
                ),
                factory=lambda **_: DummyRuntime(),
            )

        entry_point = FakeEntryPoint(
            "multi-plugin",
            lambda: [make_registration("plugin-one"), make_registration("plugin-two")],
        )
        registry = RuntimeBackendRegistry()

        with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["plugin-one", "plugin-two"])
        self.assertEqual(registry.backend_ids(), ["plugin-one", "plugin-two"])

    def test_registry_reports_invalid_entry_point_payloads(self) -> None:
        registry = RuntimeBackendRegistry()
        entry_point = FakeEntryPoint("bad-plugin", {"backend_id": "bad"})

        with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(TypeError, "bad-plugin"):
                registry.load_entry_points()

    def test_registry_reports_entry_point_load_errors(self) -> None:
        registry = RuntimeBackendRegistry()
        entry_point = FakeEntryPoint("boom-plugin", RuntimeError("boom"))

        with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(RuntimeError, "boom-plugin"):
                registry.load_entry_points()


if __name__ == "__main__":
    unittest.main()
