import unittest

from reverse_deepagent.browser import (
    BrowserProviderCapabilities,
    BrowserProviderRegistration,
    BrowserProviderRegistry,
    BrowserProviderRegistryError,
)


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
        self.assertEqual(counter, {})

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
