import importlib
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_smoke_row
from tests.test_remote_cdp_provider import FakeCDPServer


class RuntimeWrapper:
    def __init__(self, browser_provider):
        self.browser_provider = browser_provider


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-hosted-cdp-reference"
MODULE_NAME = "reverse_deepagent_browser_provider_hosted_cdp_reference"


class BrowserProviderPluginHostedCDPReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop(MODULE_NAME, None)

    def tearDown(self) -> None:
        sys.modules.pop(MODULE_NAME, None)
        package_src = str(PACKAGE_ROOT / "src")
        while package_src in sys.path:
            sys.path.remove(package_src)

    def _import_module(self):
        package_src = str(PACKAGE_ROOT / "src")
        if package_src not in sys.path:
            sys.path.insert(0, package_src)
        module = importlib.import_module(MODULE_NAME)
        module.reset_reference_state()
        return module

    def test_package_declares_hosted_cdp_reference_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-hosted-cdp-reference")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["hosted-cdp-reference"],
            "reverse_deepagent_browser_provider_hosted_cdp_reference:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_review_required(self) -> None:
        module = self._import_module()
        registration = module.browser_provider_registration()
        registry = BrowserProviderRegistry()
        registry.register(registration)
        metadata = registry.list_registration_metadata()
        matrix = browser_provider_metadata_matrix_payload(provider_metadata=metadata)

        self.assertEqual(module.factory_invocation_count(), 0)
        self.assertEqual(module.allocation_event_log(), [])
        provider = registry.create(
            "browser-service-reference",
            service_base_url="https://user:pass@broker.example.test/api?session=raw-value",
            session_id="session-sensitive-ish-long-value",
            access_material_configured=True,
        )
        self.assertEqual(module.factory_invocation_count(), 1)
        self.assertEqual(module.allocation_event_log(), [])

        self.assertEqual(registration.provider_id, "hosted-cdp-reference")
        self.assertEqual(metadata[0]["provider_id"], "hosted-cdp-reference")
        self.assertIn("hosted-cdp-ref", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_launch"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertTrue(metadata[0]["supports_cdp"])
        self.assertTrue(metadata[0]["managed_browser"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "review-required")
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        self.assertIn("production_readiness_rules", matrix)
        checks = {item["check_id"]: item for item in matrix["providers"][0]["production_readiness"]["checks"]}
        self.assertEqual(checks["provider_specific:hosted_cdp_reference_lifecycle_declared"]["status"], "pass")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)
        summary = provider.describe().config
        self.assertEqual(summary["service_base_url"], "https://broker.example.test/api?query=%3Credacted%3E")
        self.assertEqual(summary["session_id"], "sessio...alue")
        self.assertTrue(summary["access_material_configured"])
        self.assertNotIn("user:pass", str(summary))
        self.assertNotIn("raw-value", str(summary))
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()

    def test_explicit_endpoint_connect_delegates_to_remote_cdp_without_allocation(self) -> None:
        module = self._import_module()
        server = FakeCDPServer()
        try:
            provider = module.create_hosted_cdp_reference_browser_provider(
                browser_url=server.browser_url,
                service_base_url="https://user:pass@broker.example.test/api",
                access_material_configured=True,
                browser_navigation_wait=0,
            )
            payload = provider.describe().model_dump(mode="json")
            self.assertEqual(payload["config"]["browser_url"], server.browser_url)
            self.assertEqual(payload["config"]["service_base_url"], "https://broker.example.test/api")
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/reference-connect")
            self.assertEqual(page.url, "https://example.test/reference-connect")
            self.assertEqual(page.title(), "Fake CDP")
            provider.stop()
            events = module.allocation_event_log()
            self.assertEqual([item["event"] for item in events], ["attach_existing", "connect"])
            self.assertFalse(any(item["owned"] for item in events))
        finally:
            server.close()

    def test_reference_allocation_start_releases_owned_session_idempotently(self) -> None:
        module = self._import_module()
        server = FakeCDPServer()
        try:
            provider = module.create_hosted_cdp_reference_browser_provider(
                allocated_browser_url=server.browser_url,
                allocation_mode="in-memory-allocation",
                session_id="reviewed-reference-session-1",
                browser_navigation_wait=0,
            )
            session = provider.start()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/reference-start")
            self.assertEqual(page.url, "https://example.test/reference-start")
            allocation = provider.allocation_summary()
            self.assertIsNotNone(allocation)
            assert allocation is not None
            self.assertTrue(allocation["owned"])
            self.assertFalse(allocation["released"])
            provider.stop()
            provider.stop()
            events = module.allocation_event_log()
            self.assertEqual([item["event"] for item in events], ["allocate_reference", "start", "release_reference"])
            self.assertTrue(events[0]["owned"])
            self.assertTrue(events[-1]["owned"])
            self.assertEqual(events[-1]["session_id"], "review...on-1")
        finally:
            server.close()

    def test_launch_smoke_uses_reference_provider_lifecycle(self) -> None:
        module = self._import_module()
        server = FakeCDPServer()
        try:
            registry = BrowserProviderRegistry()
            registry.register(module.browser_provider_registration())

            def provider_factory(*, browser: str, **kwargs):
                return RuntimeWrapper(registry.create(browser, **kwargs))

            row = browser_provider_smoke_row(
                provider_id="hosted-cdp-ref",
                provider_factory=provider_factory,
                provider_kwargs={
                    "allocated_browser_url": server.browser_url,
                    "allocation_mode": "in-memory-allocation",
                    "browser_navigation_wait": 0,
                },
                include_availability=True,
                launch_smoke=True,
                smoke_url="https://example.test/reference-smoke",
            )
            self.assertTrue(row["ok"])
            self.assertEqual(row["provider_id"], "hosted-cdp-ref")
            self.assertTrue(row["available"])
            self.assertTrue(row["launched"])
            self.assertEqual(row["smoke"]["status"], "passed")
            events = module.allocation_event_log()
            self.assertIn("allocate_reference", [item["event"] for item in events])
            self.assertIn("release_reference", [item["event"] for item in events])
        finally:
            server.close()

    def test_missing_endpoint_blocks_start_and_connect_with_guidance(self) -> None:
        module = self._import_module()
        provider = module.create_hosted_cdp_reference_browser_provider(allocation_mode="in-memory-allocation")
        self.assertFalse(provider.is_available())
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires allocated_browser_url"):
            provider.start()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()
        self.assertEqual(module.allocation_event_log(), [])


if __name__ == "__main__":
    unittest.main()
