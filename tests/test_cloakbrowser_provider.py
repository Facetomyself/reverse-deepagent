import unittest

from reverse_deepagent.adapters.native_web import create_native_web_runtime
from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.providers import CloakBrowserConfig, CloakBrowserProvider


class CloakBrowserProviderTests(unittest.TestCase):
    def test_describe_is_serializable_and_redacts_proxy(self) -> None:
        provider = CloakBrowserProvider(
            CloakBrowserConfig(
                headless=False,
                humanize=True,
                profile_dir="/tmp/reverse-agent-cloak-profile",
                proxy="http://user:pass@example.test:8080",
                locale="zh-CN",
                timezone="Asia/Shanghai",
            )
        )
        payload = provider.describe().model_dump(mode="json")
        self.assertEqual(payload["provider_id"], "cloakbrowser")
        self.assertEqual(payload["transport"], "cloakbrowser-playwright")
        self.assertTrue(payload["supports_stealth"])
        self.assertTrue(payload["supports_humanize"])
        self.assertEqual(payload["config"]["proxy"], "<configured>")
        self.assertNotIn("user:pass", str(payload))

    def test_missing_cloakbrowser_dependency_is_structured_unavailable(self) -> None:
        provider = CloakBrowserProvider()
        if provider.is_available():
            self.skipTest("cloakbrowser is installed in this environment")
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "cloakbrowser is not installed"):
            provider.start()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "does not support connect mode"):
            provider.connect()

    def test_native_web_factory_can_select_cloakbrowser_without_starting_it(self) -> None:
        runtime = create_native_web_runtime(
            browser="cloakbrowser",
            browser_profile_dir="/tmp/reverse-agent-cloak-profile",
            browser_humanize=True,
            browser_locale="zh-CN",
            browser_timezone="Asia/Shanghai",
            browser_proxy="http://user:pass@example.test:8080",
        )
        capabilities = runtime.describe_capabilities().model_dump(mode="json")
        provider = capabilities["config"]["provider"]
        self.assertEqual(provider["provider_id"], "cloakbrowser")
        self.assertEqual(provider["config"]["proxy"], "<configured>")
        self.assertTrue(provider["supports_stealth"])
        self.assertTrue(provider["config"]["humanize"])

    def test_native_web_factory_keeps_cloakbrowser_humanize_enabled_by_default(self) -> None:
        runtime = create_native_web_runtime(browser="cloakbrowser", browser_humanize=None)
        provider = runtime.describe_capabilities().model_dump(mode="json")["config"]["provider"]
        self.assertTrue(provider["config"]["humanize"])

    def test_launch_kwargs_use_current_cloakbrowser_timezone_key(self) -> None:
        provider = CloakBrowserProvider(CloakBrowserConfig(timezone="Asia/Shanghai"))
        kwargs = provider._launch_kwargs()
        self.assertEqual(kwargs["timezone"], "Asia/Shanghai")
        self.assertNotIn("timezone_id", kwargs)


if __name__ == "__main__":
    unittest.main()
