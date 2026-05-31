import importlib
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-template"


class BrowserProviderPluginTemplateTests(unittest.TestCase):
    def test_package_declares_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-template")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["template-browser"],
            "reverse_deepagent_browser_provider_template:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_factory_is_explicit(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_browser_provider_template")
            registration = module.browser_provider_registration()
            registry = BrowserProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create("browser-template")
            self.assertEqual(module.factory_invocation_count(), 1)
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_browser_provider_template", None)
        self.assertEqual(registration.provider_id, "template-browser")
        self.assertEqual(metadata[0]["provider_id"], "template-browser")
        self.assertIn("custom-browser-template", metadata[0]["aliases"])
        self.assertFalse(metadata[0]["supports_launch"])
        self.assertFalse(metadata[0]["supports_cdp"])
        self.assertEqual(provider.describe().provider_id, "template-browser")
        with self.assertRaises(BrowserProviderUnavailableError):
            provider.start()


if __name__ == "__main__":
    unittest.main()
