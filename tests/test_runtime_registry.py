import unittest

from reverse_deepagent.runtime import RuntimeBackendCapabilities, RuntimeBackendRegistration, RuntimeBackendRegistry
from reverse_deepagent.runtime.base import BrowserSessionInfo, ReverseRuntime, RuntimeExportBundle
from reverse_deepagent.schemas import ProtectionResult, ReconResult, RouterResult, TaskCard


class DummyRuntime(ReverseRuntime):
    def ensure_browser_session(self) -> BrowserSessionInfo:
        return BrowserSessionInfo(healthy=True)

    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        raise NotImplementedError

    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class RuntimeRegistryTests(unittest.TestCase):
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

    def test_registry_reports_unknown_backends(self) -> None:
        registry = RuntimeBackendRegistry()
        with self.assertRaisesRegex(ValueError, "Unsupported runtime backend"):
            registry.resolve("missing")


if __name__ == "__main__":
    unittest.main()
