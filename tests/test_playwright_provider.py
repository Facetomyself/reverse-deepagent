import unittest

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.providers import PlaywrightChromiumConfig, PlaywrightChromiumProvider


class PlaywrightProviderTests(unittest.TestCase):
    def test_describe_is_serializable_and_side_effect_light(self) -> None:
        provider = PlaywrightChromiumProvider(
            PlaywrightChromiumConfig(
                headless=True,
                profile_dir="/tmp/reverse-agent-playwright-profile",
                browser_url="http://127.0.0.1:9222",
            )
        )
        payload = provider.describe().model_dump(mode="json")
        self.assertEqual(payload["provider_id"], "playwright-chromium")
        self.assertEqual(payload["transport"], "playwright")
        self.assertTrue(payload["supports_persistent_context"])
        self.assertTrue(payload["supports_cdp"])
        self.assertEqual(payload["config"]["profile_dir"], "/tmp/reverse-agent-playwright-profile")
        self.assertEqual(payload["production_readiness"]["readiness_tier"], "review-required")
        self.assertEqual(payload["production_readiness"]["profile_lifecycle"], "temporary-context-or-user-data-dir")

    def test_missing_playwright_dependency_is_structured_unavailable(self) -> None:
        provider = PlaywrightChromiumProvider()
        if provider.is_available():
            self.skipTest("playwright is installed in this environment")
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "playwright is not installed"):
            provider.start()

    def test_connect_requires_browser_url_before_loading_dependency(self) -> None:
        provider = PlaywrightChromiumProvider(PlaywrightChromiumConfig(browser_url=None))
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()


if __name__ == "__main__":
    unittest.main()
