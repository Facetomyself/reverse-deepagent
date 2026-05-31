from __future__ import annotations

import unittest
from unittest.mock import patch

from reverse_deepagent.delivery import (
    EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP,
    ExternalDeliveryPackage,
    ExternalDeliveryProviderCapabilities,
    ExternalDeliveryProviderRegistration,
    ExternalDeliveryProviderRegistry,
    ExternalDeliveryResult,
    GitHubReleaseExternalDeliveryProvider,
    LocalArchiveExternalDeliveryProvider,
    PresignedObjectExternalDeliveryProvider,
    ReviewOnlyExternalDeliveryProvider,
    WebhookExternalDeliveryProvider,
    build_default_external_delivery_provider_registry,
    external_delivery_metadata_has_secret_like_keys,
)
from reverse_deepagent.delivery import registry as delivery_registry


class DummyExternalDeliveryProvider:
    provider_id = "dummy-provider"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status="delivered",
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=True,
            package_digest_sha256="dummy-digest",
            checks=[{"name": "dummy_provider_delivered", "passed": True, "details": {}}],
            blocking_reasons=[],
            recommended_actions=["review_dummy_external_delivery"],
            created_at=created_at,
            metadata={"scope": "dummy-external-delivery-provider"},
        )


class FakeEntryPoint:
    def __init__(self, name: str, value, group: str = EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP) -> None:
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


class ExternalDeliveryProviderRegistryTests(unittest.TestCase):
    def test_default_registry_exposes_review_only_provider_and_aliases(self) -> None:
        registry = build_default_external_delivery_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("review-only").provider_id, "review-only")
        self.assertEqual(registry.resolve("manual-handoff").provider_id, "review-only")
        self.assertIn("noop", registry.provider_ids())
        by_provider = {metadata["provider_id"]: metadata for metadata in registry.list_metadata()}
        metadata = by_provider["review-only"]
        self.assertFalse(metadata["supports_external_delivery"])
        self.assertTrue(metadata["review_only"])
        self.assertIsInstance(registry.create("noop"), ReviewOnlyExternalDeliveryProvider)

    def test_default_registry_exposes_local_archive_provider_and_aliases(self) -> None:
        registry = build_default_external_delivery_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("filesystem-release").provider_id, "local-archive")
        self.assertIn("archive", registry.provider_ids())
        by_provider = {metadata["provider_id"]: metadata for metadata in registry.list_metadata()}
        metadata = by_provider["local-archive"]
        self.assertTrue(metadata["supports_external_delivery"])
        self.assertFalse(metadata["review_only"])
        self.assertEqual(metadata["transport"], "filesystem")
        provider = registry.create("filesystem-release", archive_root="/tmp/reverse-agent-archive")
        self.assertIsInstance(provider, LocalArchiveExternalDeliveryProvider)

    def test_default_registry_exposes_webhook_provider_and_aliases(self) -> None:
        registry = build_default_external_delivery_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("http-webhook").provider_id, "webhook")
        self.assertIn("webhook-json", registry.provider_ids())
        by_provider = {metadata["provider_id"]: metadata for metadata in registry.list_metadata()}
        metadata = by_provider["webhook"]
        self.assertTrue(metadata["supports_external_delivery"])
        self.assertFalse(metadata["review_only"])
        self.assertEqual(metadata["transport"], "webhook")
        provider = registry.create("webhook-json", webhook_url="https://example.invalid/deliver")
        self.assertIsInstance(provider, WebhookExternalDeliveryProvider)

    def test_default_registry_exposes_presigned_object_provider_and_aliases(self) -> None:
        registry = build_default_external_delivery_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("object-storage").provider_id, "presigned-object")
        self.assertIn("presigned-url", registry.provider_ids())
        self.assertIn("s3-presigned", registry.provider_ids())
        by_provider = {metadata["provider_id"]: metadata for metadata in registry.list_metadata()}
        metadata = by_provider["presigned-object"]
        self.assertTrue(metadata["supports_external_delivery"])
        self.assertFalse(metadata["review_only"])
        self.assertEqual(metadata["transport"], "object-storage")
        provider = registry.create("s3-presigned", presigned_url="https://example.invalid/object")
        self.assertIsInstance(provider, PresignedObjectExternalDeliveryProvider)

    def test_default_registry_exposes_github_release_provider_and_aliases(self) -> None:
        registry = build_default_external_delivery_provider_registry(load_entry_points=False)

        self.assertEqual(registry.resolve("gh-release").provider_id, "github-release")
        self.assertIn("github-release-assets", registry.provider_ids())
        by_provider = {metadata["provider_id"]: metadata for metadata in registry.list_metadata()}
        metadata = by_provider["github-release"]
        self.assertTrue(metadata["supports_external_delivery"])
        self.assertFalse(metadata["review_only"])
        self.assertEqual(metadata["transport"], "github-release")
        self.assertTrue(metadata["metadata"]["supports_existing_release_reuse"])
        provider = registry.create(
            "github-release-assets",
            repository="owner/repo",
            tag_name="v1",
            token="not-serialized",
        )
        self.assertIsInstance(provider, GitHubReleaseExternalDeliveryProvider)

    def test_registry_rejects_duplicate_keys(self) -> None:
        registry = ExternalDeliveryProviderRegistry()
        registration = ExternalDeliveryProviderRegistration(
            provider_id="dummy",
            capabilities=ExternalDeliveryProviderCapabilities(provider_id="dummy", display_name="Dummy"),
            factory=lambda **_: DummyExternalDeliveryProvider(),
        )
        registry.register(registration)
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(registration)

    def test_registry_rejects_capability_provider_id_mismatch(self) -> None:
        registry = ExternalDeliveryProviderRegistry()
        with self.assertRaisesRegex(ValueError, "capability id mismatch"):
            registry.register(
                ExternalDeliveryProviderRegistration(
                    provider_id="dummy",
                    capabilities=ExternalDeliveryProviderCapabilities(provider_id="other", display_name="Other"),
                    factory=lambda **_: DummyExternalDeliveryProvider(),
                )
            )

    def test_secret_like_capability_metadata_is_rejected(self) -> None:
        self.assertTrue(external_delivery_metadata_has_secret_like_keys({"config": {"api_token": "redacted"}}))
        self.assertTrue(external_delivery_metadata_has_secret_like_keys({"headers": {"Authorization": "Bearer redacted"}}))
        self.assertFalse(external_delivery_metadata_has_secret_like_keys({"config": {"archive_root_configurable": True}}))
        with self.assertRaisesRegex(ValueError, "secret-like"):
            ExternalDeliveryProviderRegistration(
                provider_id="leaky-delivery",
                capabilities=ExternalDeliveryProviderCapabilities(
                    provider_id="leaky-delivery",
                    display_name="Leaky Delivery",
                    metadata={"api_token": "redacted"},
                ),
                factory=lambda **_: DummyExternalDeliveryProvider(),
            )

    def test_registry_loads_entry_point_without_invoking_provider_factory(self) -> None:
        factory_calls: list[str] = []
        registration = ExternalDeliveryProviderRegistration(
            provider_id="plugin-delivery",
            aliases=("plugin-alias",),
            capabilities=ExternalDeliveryProviderCapabilities(
                provider_id="plugin-delivery",
                display_name="Plugin Delivery",
                transport="plugin",
                supports_external_delivery=True,
                review_only=False,
            ),
            factory=lambda **_: factory_calls.append("called") or DummyExternalDeliveryProvider(),
        )
        entry_point = FakeEntryPoint("plugin-delivery", registration)
        registry = ExternalDeliveryProviderRegistry()

        with patch.object(delivery_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["plugin-delivery"])
        self.assertEqual(entry_point.load_count, 1)
        self.assertEqual(factory_calls, [])
        self.assertEqual(registry.resolve("plugin-alias").provider_id, "plugin-delivery")
        self.assertEqual(registry.list_metadata()[0]["transport"], "plugin")
        self.assertIsInstance(registry.create("plugin-delivery"), DummyExternalDeliveryProvider)
        self.assertEqual(factory_calls, ["called"])

    def test_registry_loads_callable_entry_point_returning_multiple_registrations(self) -> None:
        def make_registration(provider_id: str) -> ExternalDeliveryProviderRegistration:
            return ExternalDeliveryProviderRegistration(
                provider_id=provider_id,
                capabilities=ExternalDeliveryProviderCapabilities(provider_id=provider_id, display_name=f"{provider_id} Delivery"),
                factory=lambda **_: DummyExternalDeliveryProvider(),
            )

        entry_point = FakeEntryPoint("multi-delivery", lambda: [make_registration("one"), make_registration("two")])
        registry = ExternalDeliveryProviderRegistry()

        with patch.object(delivery_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            loaded = registry.load_entry_points()

        self.assertEqual(loaded, ["one", "two"])
        self.assertEqual(registry.provider_ids(), ["one", "two"])

    def test_registry_reports_invalid_entry_point_payloads(self) -> None:
        registry = ExternalDeliveryProviderRegistry()
        entry_point = FakeEntryPoint("bad-delivery", {"provider_id": "bad"})

        with patch.object(delivery_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(TypeError, "bad-delivery"):
                registry.load_entry_points()

    def test_registry_reports_entry_point_load_errors(self) -> None:
        registry = ExternalDeliveryProviderRegistry()
        entry_point = FakeEntryPoint("boom-delivery", RuntimeError("boom"))

        with patch.object(delivery_registry.importlib_metadata, "entry_points", return_value=FakeEntryPoints([entry_point])):
            with self.assertRaisesRegex(RuntimeError, "boom-delivery"):
                registry.load_entry_points()


if __name__ == "__main__":
    unittest.main()
