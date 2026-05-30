import unittest
from unittest.mock import patch

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
                browser_url="http://user:pass@127.0.0.1:9222",
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
        self.assertTrue(payload["supports_connect"])
        self.assertEqual(payload["config"]["browser_url"], "http://127.0.0.1:9222")
        self.assertEqual(payload["config"]["proxy"], "<configured>")
        self.assertNotIn("user:pass", str(payload))

    def test_missing_cloakbrowser_dependency_is_structured_unavailable(self) -> None:
        provider = CloakBrowserProvider()
        if provider.is_available():
            self.skipTest("cloakbrowser is installed in this environment")
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "cloakbrowser is not installed"):
            provider.start()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()

    def test_connect_mode_uses_playwright_cdp_without_loading_cloakbrowser(self) -> None:
        provider = CloakBrowserProvider(CloakBrowserConfig(browser_url="http://127.0.0.1:9222"))
        manager = FakePlaywrightManager()
        with patch.object(CloakBrowserProvider, "_load_sync_playwright", return_value=lambda: FakePlaywrightStarter(manager)):
            self.assertTrue(provider.is_available())
            session = provider.connect()

        self.assertEqual(session.provider_id, "cloakbrowser")
        self.assertEqual(manager.chromium.connected_url, "http://127.0.0.1:9222")
        self.assertEqual(manager.chromium.connected_timeout, 45_000)
        self.assertFalse(manager.stopped)
        provider.stop()
        self.assertTrue(manager.browser.closed)
        self.assertTrue(manager.stopped)

    def test_native_web_factory_can_select_cloakbrowser_without_starting_it(self) -> None:
        runtime = create_native_web_runtime(
            browser="cloakbrowser",
            browser_profile_dir="/tmp/reverse-agent-cloak-profile",
            browser_url="http://user:pass@127.0.0.1:9222",
            browser_humanize=True,
            browser_locale="zh-CN",
            browser_timezone="Asia/Shanghai",
            browser_proxy="http://user:pass@example.test:8080",
        )
        capabilities = runtime.describe_capabilities().model_dump(mode="json")
        provider = capabilities["config"]["provider"]
        self.assertEqual(provider["provider_id"], "cloakbrowser")
        self.assertEqual(provider["config"]["proxy"], "<configured>")
        self.assertEqual(provider["config"]["browser_url"], "http://127.0.0.1:9222")
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

class FakePlaywrightStarter:
    def __init__(self, manager) -> None:
        self._manager = manager

    def start(self):
        return self._manager


class FakePlaywrightManager:
    def __init__(self) -> None:
        self.browser = FakeConnectedBrowser()
        self.chromium = FakeChromium(self.browser)
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakeChromium:
    def __init__(self, browser) -> None:
        self.browser = browser
        self.connected_url = None
        self.connected_timeout = None

    def connect_over_cdp(self, browser_url, timeout=None):
        self.connected_url = browser_url
        self.connected_timeout = timeout
        return self.browser


class FakeConnectedBrowser:
    def __init__(self) -> None:
        self.contexts = [FakeBrowserContext()]
        self.closed = False

    def new_context(self):
        context = FakeBrowserContext()
        self.contexts.append(context)
        return context

    def close(self):
        self.closed = True


class FakeBrowserContext:
    pages = []

    def new_page(self):
        raise AssertionError("not used")

    def close(self):
        return None


if __name__ == "__main__":
    unittest.main()
