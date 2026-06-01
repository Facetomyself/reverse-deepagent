import importlib
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_smoke_row


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-fixture"


class RuntimeWrapper:
    def __init__(self, browser_provider):
        self.browser_provider = browser_provider


class BrowserProviderPluginFixtureTests(unittest.TestCase):
    def test_package_declares_functional_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-fixture")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["fixture-browser"],
            "reverse_deepagent_browser_provider_fixture:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_provider_is_functional(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_browser_provider_fixture")
            registration = module.browser_provider_registration()
            registry = BrowserProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            matrix = browser_provider_metadata_matrix_payload(provider_metadata=metadata)
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create("fixture", browser_url="https://fixture.test/landing", title="Fixture Smoke")
            self.assertEqual(module.factory_invocation_count(), 1)
            session = provider.start()
            page = session.get_active_page()
            connected = provider.connect()
            provider.stop()
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_browser_provider_fixture", None)

        self.assertEqual(registration.provider_id, "fixture-browser")
        self.assertEqual(metadata[0]["provider_id"], "fixture-browser")
        self.assertIn("ci-browser-fixture", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_launch"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertFalse(metadata[0]["supports_cdp"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "fixture-only")
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["compatibility"]["status"], "compatible")
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)
        self.assertEqual(page.url, "https://fixture.test/landing")
        self.assertEqual(page.title(), "Fixture Smoke")
        page.goto("https://fixture.test/next")
        self.assertEqual(page.evaluate("location.href"), "https://fixture.test/next")
        self.assertEqual(session.list_pages()[0].url, "https://fixture.test/next")
        self.assertEqual(connected.provider_id, "fixture-browser")
        self.assertTrue(session.closed)
        self.assertTrue(connected.closed)

    def test_smoke_row_can_launch_external_fixture_provider(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_browser_provider_fixture")
            registry = BrowserProviderRegistry()
            registry.register(module.browser_provider_registration())

            def provider_factory(*, browser: str, **kwargs):
                return RuntimeWrapper(registry.create(browser, **kwargs))

            row = browser_provider_smoke_row(
                provider_id="ci-browser-fixture",
                provider_factory=provider_factory,
                provider_kwargs={"title": "Fixture Launch"},
                include_availability=True,
                launch_smoke=True,
                smoke_url="https://fixture.test/smoke",
            )
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_browser_provider_fixture", None)

        self.assertTrue(row["ok"])
        self.assertTrue(row["available"])
        self.assertTrue(row["launched"])
        self.assertEqual(row["provider_id"], "ci-browser-fixture")
        self.assertEqual(row["capabilities"]["provider_id"], "fixture-browser")
        self.assertEqual(row["production_readiness"]["status"], "review-required")
        self.assertEqual(row["smoke"]["status"], "passed")
        self.assertEqual(row["smoke"]["url"], "https://fixture.test/smoke")
        self.assertEqual(row["smoke"]["title"], "Fixture Launch")
        lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
        self.assertEqual(lifecycle["availability_checked"], "ok")
        self.assertEqual(lifecycle["session_opened"], "ok")
        self.assertEqual(lifecycle["session_closed"], "ok")


if __name__ == "__main__":
    unittest.main()
