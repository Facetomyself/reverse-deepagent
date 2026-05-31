import unittest
from unittest.mock import patch

from reverse_deepagent.browser import (
    BROWSER_PROVIDER_ENTRY_POINT_GROUP,
    BrowserProviderCapabilities,
    BrowserProviderRegistration,
    BrowserProviderRegistry,
    BrowserProviderRegistryError,
    build_default_browser_provider_registry,
)
from reverse_deepagent.browser import registry as browser_registry
from reverse_deepagent.browser.providers import CloakBrowserProvider, PlaywrightChromiumProvider, RemoteCDPProvider


class CountingProvider:
    def __init__(self, counter: dict[str, int]) -> None:
        counter["created"] = counter.get("created", 0) + 1
        self.counter = counter

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(provider_id="counting", display_name="Counting")

    def start(self):
        raise NotImplementedError

    def connect(self):
        raise NotImplementedError

    def stop(self) -> None:
        pass

    def is_available(self) -> bool:
        return True


class FakeEntryPoint:
    def __init__(self, name: str, value, group: str = BROWSER_PROVIDER_ENTRY_POINT_GROUP) -> None:
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


def capabilities(provider_id: str = "counting") -> BrowserProviderCapabilities:
    return BrowserProviderCapabilities(
        provider_id=provider_id,
        display_name="Counting Browser",
        engine="chromium",
        transport="fake",
        supports_launch=True,
        supports_connect=False,
        supports_persistent_context=True,
        supports_runtime_eval=True,
        config={"profile_strategy": "temporary"},
    )


class BrowserProviderRegistryTests(unittest.TestCase):
    def test_register_resolve_alias_and_create(self) -> None:
        counter: dict[str, int] = {}
        registry = BrowserProviderRegistry()
        registry.register(
            BrowserProviderRegistration(
                provider_id="counting",
                aliases=("fake", "test-browser"),
                capabilities=capabilities(),
                factory=lambda **kwargs: CountingProvider(counter),
            )
        )

        self.assertEqual(registry.resolve("fake").provider_id, "counting")
        self.assertEqual(registry.provider_ids(), ["counting", "fake", "test-browser"])
        provider = registry.create("test-browser")
        self.assertIsInstance(provider, CountingProvider)
        self.assertEqual(counter["created"], 1)

    def test_listing_metadata_is_side_effect_free(self) -> None:
        counter: dict[str, int] = {}
        registry = BrowserProviderRegistry()
        registry.register(
            BrowserProviderRegistration(
                provider_id="counting",
                aliases=("fake",),
                capabilities=capabilities(),
                factory=lambda **kwargs: CountingProvider(counter),
            )
        )

        metadata = registry.list_metadata()
        self.assertEqual(metadata[0]["provider_id"], "counting")
        registration_metadata = registry.list_registration_metadata()
        self.assertEqual(registration_metadata[0]["aliases"], ["fake"])
        self.assertEqual(registration_metadata[0]["keys"], ["counting", "fake"])
        self.assertEqual(counter, {})

    def test_default_registry_exposes_builtin_providers_and_aliases(self) -> None:
        registry = build_default_browser_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("chromium").provider_id, "playwright-chromium")
        self.assertEqual(registry.resolve("cloak").provider_id, "cloakbrowser")
        self.assertEqual(registry.resolve("cdp-provider").provider_id, "remote-cdp")
        self.assertIn("chrome-cdp-provider", registry.provider_ids())
        provider_metadata = {item["provider_id"]: item for item in registry.list_registration_metadata()}
        self.assertEqual(provider_metadata["playwright-chromium"]["aliases"], ["playwright", "chromium"])
        self.assertTrue(provider_metadata["cloakbrowser"]["supports_stealth"])
        self.assertTrue(provider_metadata["remote-cdp"]["supports_cdp"])
        self.assertIsInstance(registry.create("playwright"), PlaywrightChromiumProvider)
        self.assertIsInstance(registry.create("cloak-browser"), CloakBrowserProvider)
        self.assertIsInstance(registry.create("chrome-cdp-provider"), RemoteCDPProvider)

    def test_registry_loads_entry_point_without_invoking_provider_factory(self) -> None:
        factory_calls: list[str] = []
        registration = BrowserProviderRegistration(
            provider_id="plugin-browser",
            aliases=("plugin-alias",),
            capabilities=BrowserProviderCapabilities(
                provider_id="plugin-browser",
                display_name="Plugin Browser",
                engine="chromium",
                transport="plugin",
                supports_launch=True,
            ),
            factory=lambda **_: factory_calls.append("called") or CountingProvider({}),
        )
        entry_point = FakeEntryPoint("plugin-browser", registration)
        registry = BrowserProviderRegistry()

        with patch.object(browser_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["plugin-browser"])
        self.assertEqual(entry_point.load_count, 1)
        self.assertEqual(factory_calls, [])
        self.assertEqual(registry.resolve("plugin-alias").provider_id, "plugin-browser")
        self.assertEqual(registry.list_metadata()[0]["transport"], "plugin")
        self.assertIsInstance(registry.create("plugin-browser"), CountingProvider)
        self.assertEqual(factory_calls, ["called"])

    def test_registry_loads_callable_entry_point_returning_multiple_registrations(self) -> None:
        def make_registration(provider_id: str) -> BrowserProviderRegistration:
            return BrowserProviderRegistration(
                provider_id=provider_id,
                capabilities=BrowserProviderCapabilities(provider_id=provider_id, display_name=f"{provider_id} Browser"),
                factory=lambda **_: CountingProvider({}),
            )

        entry_point = FakeEntryPoint("multi-browser", lambda: [make_registration("one"), make_registration("two")])
        registry = BrowserProviderRegistry()

        with patch.object(browser_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["one", "two"])
        self.assertEqual(registry.provider_ids(), ["one", "two"])

    def test_registry_reports_invalid_entry_point_payloads(self) -> None:
        registry = BrowserProviderRegistry()
        entry_point = FakeEntryPoint("bad-browser", {"provider_id": "bad"})

        with patch.object(browser_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(TypeError, "bad-browser"):
                registry.load_entry_points()

    def test_registry_reports_entry_point_load_errors(self) -> None:
        registry = BrowserProviderRegistry()
        entry_point = FakeEntryPoint("boom-browser", RuntimeError("boom"))

        with patch.object(browser_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(RuntimeError, "boom-browser"):
                registry.load_entry_points()

    def test_unknown_provider_error_is_explicit(self) -> None:
        registry = BrowserProviderRegistry()
        registry.register(
            BrowserProviderRegistration(
                provider_id="counting",
                aliases=("fake",),
                capabilities=capabilities(),
                factory=lambda **kwargs: CountingProvider({}),
            )
        )
        with self.assertRaisesRegex(BrowserProviderRegistryError, "Unsupported browser provider: missing.*counting.*fake"):
            registry.resolve("missing")

    def test_duplicate_keys_are_rejected(self) -> None:
        registry = BrowserProviderRegistry()
        registration = BrowserProviderRegistration(
            provider_id="counting",
            aliases=("fake",),
            capabilities=capabilities(),
            factory=lambda **kwargs: CountingProvider({}),
        )
        registry.register(registration)
        with self.assertRaisesRegex(BrowserProviderRegistryError, "already registered"):
            registry.register(registration)

    def test_capability_provider_id_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(BrowserProviderRegistryError, "does not match"):
            BrowserProviderRegistration(
                provider_id="counting",
                capabilities=capabilities("other"),
                factory=lambda **kwargs: CountingProvider({}),
            )

    def test_secret_like_capability_metadata_is_rejected(self) -> None:
        with self.assertRaisesRegex(BrowserProviderRegistryError, "secret-like"):
            BrowserProviderRegistration(
                provider_id="counting",
                capabilities=capabilities().model_copy(update={"config": {"api_token": "redacted"}}),
                factory=lambda **kwargs: CountingProvider({}),
            )


if __name__ == "__main__":
    unittest.main()
