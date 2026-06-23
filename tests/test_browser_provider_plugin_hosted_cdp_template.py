import importlib
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload
from tests.test_remote_cdp_provider import FakeCDPServer


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-hosted-cdp-template"


class BrowserProviderPluginHostedCDPTemplateTests(unittest.TestCase):
    def test_package_declares_hosted_cdp_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-hosted-cdp-template")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["hosted-cdp-template"],
            "reverse_deepagent_browser_provider_hosted_cdp_template:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_review_required(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_browser_provider_hosted_cdp_template")
            registration = module.browser_provider_registration()
            registry = BrowserProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            matrix = browser_provider_metadata_matrix_payload(provider_metadata=metadata)
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create("remote-browser-service", service_base_url="https://user:pass@broker.example.test/api")
            self.assertEqual(module.factory_invocation_count(), 1)
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_browser_provider_hosted_cdp_template", None)

        self.assertEqual(registration.provider_id, "hosted-cdp-template")
        self.assertEqual(metadata[0]["provider_id"], "hosted-cdp-template")
        self.assertIn("hosted-cdp", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertTrue(metadata[0]["supports_cdp"])
        self.assertTrue(metadata[0]["supports_runtime_eval"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "review-required")
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)
        self.assertEqual(provider.describe().config["service_base_url"], "https://broker.example.test/api")
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()

    def test_configured_browser_url_delegates_to_remote_cdp_provider(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        server = FakeCDPServer()
        try:
            module = importlib.import_module("reverse_deepagent_browser_provider_hosted_cdp_template")
            provider = module.create_hosted_cdp_browser_provider(
                browser_url=server.browser_url,
                service_base_url="https://user:pass@broker.example.test/api",
                access_material_configured=True,
                browser_navigation_wait=0,
            )
            payload = provider.describe().model_dump(mode="json")
            self.assertEqual(payload["config"]["service_base_url"], "https://broker.example.test/api")
            self.assertTrue(payload["config"]["access_material_configured"])
            self.assertNotIn("user:pass", str(payload))
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/hosted")
            self.assertEqual(page.url, "https://example.test/hosted")
            self.assertEqual(page.title(), "Fake CDP")
            provider.stop()
        finally:
            server.close()
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_browser_provider_hosted_cdp_template", None)


if __name__ == "__main__":
    unittest.main()
