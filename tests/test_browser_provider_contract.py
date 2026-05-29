import unittest
from typing import Any

from reverse_deepagent.browser import (
    BrowserPageRef,
    BrowserProvider,
    BrowserProviderCapabilities,
    BrowserSession,
    metadata_has_secret_like_keys,
)


class FakePage:
    @property
    def url(self) -> str:
        return "https://example.test"

    def goto(self, url: str, timeout: float | None = None) -> None:
        self._url = url

    def title(self) -> str:
        return "Example"

    def content(self) -> str:
        return "<html></html>"

    def evaluate(self, expression: str) -> Any:
        return {"expression": expression}

    def screenshot(self, path: str | None = None) -> bytes | None:
        return b"fake-image"

    def cdp_session(self) -> None:
        return None


class FakeSession:
    provider_id = "fake-browser"

    def list_pages(self) -> list[BrowserPageRef]:
        return [BrowserPageRef(page_id="0", url="https://example.test", title="Example", selected=True)]

    def new_page(self, url: str | None = None) -> FakePage:
        return FakePage()

    def get_active_page(self) -> FakePage:
        return FakePage()

    def close(self) -> None:
        self.closed = True


class FakeProvider:
    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id="fake-browser",
            display_name="Fake Browser",
            engine="chromium",
            transport="in-process",
            supports_launch=True,
            supports_playwright_api=True,
            supports_network_events=True,
            supports_runtime_eval=True,
        )

    def start(self) -> FakeSession:
        return FakeSession()

    def connect(self) -> FakeSession:
        return FakeSession()

    def stop(self) -> None:
        self.stopped = True

    def is_available(self) -> bool:
        return True


class BrowserProviderContractTests(unittest.TestCase):
    def test_capabilities_are_json_serializable(self) -> None:
        capabilities = FakeProvider().describe()
        payload = capabilities.model_dump(mode="json")
        self.assertEqual(payload["provider_id"], "fake-browser")
        self.assertEqual(payload["target_platforms"], ["web"])
        self.assertTrue(payload["supports_launch"])
        self.assertFalse(metadata_has_secret_like_keys(payload))

    def test_provider_and_session_match_protocols(self) -> None:
        provider = FakeProvider()
        self.assertIsInstance(provider, BrowserProvider)
        session = provider.start()
        self.assertIsInstance(session, BrowserSession)
        self.assertEqual(session.list_pages()[0].page_id, "0")
        self.assertEqual(session.get_active_page().title(), "Example")

    def test_secret_like_metadata_keys_are_detected(self) -> None:
        self.assertTrue(metadata_has_secret_like_keys({"config": {"api_token": "redacted"}}))
        self.assertTrue(metadata_has_secret_like_keys({"headers": {"Authorization": "Bearer redacted"}}))
        self.assertFalse(metadata_has_secret_like_keys({"config": {"proxy_enabled": True, "locale": "zh-CN"}}))


if __name__ == "__main__":
    unittest.main()
