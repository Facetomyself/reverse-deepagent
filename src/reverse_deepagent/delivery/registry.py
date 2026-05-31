from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Any, Callable

from reverse_deepagent.delivery.executors import (
    DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES,
    ExternalDeliveryProvider,
    GitHubReleaseExternalDeliveryProvider,
    LocalArchiveExternalDeliveryProvider,
    PresignedObjectExternalDeliveryProvider,
    ReviewOnlyExternalDeliveryProvider,
    WebhookExternalDeliveryProvider,
    external_delivery_metadata_has_secret_like_keys,
)

ExternalDeliveryProviderFactory = Callable[..., ExternalDeliveryProvider]
EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP = "reverse_deepagent.external_delivery_providers"


@dataclass(frozen=True, slots=True)
class ExternalDeliveryProviderCapabilities:
    provider_id: str
    display_name: str
    transport: str = "in-process"
    supports_external_delivery: bool = False
    review_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "transport": self.transport,
            "supports_external_delivery": self.supports_external_delivery,
            "review_only": self.review_only,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ExternalDeliveryProviderRegistration:
    provider_id: str
    capabilities: ExternalDeliveryProviderCapabilities
    factory: ExternalDeliveryProviderFactory
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if external_delivery_metadata_has_secret_like_keys(self.capabilities.to_dict()):
            raise ValueError(f"External delivery provider capabilities for {self.provider_id!r} contain secret-like metadata keys")

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.provider_id, *self.aliases)


class ExternalDeliveryProviderRegistry:
    """Side-effect-light registry for pluggable external delivery providers."""

    def __init__(self) -> None:
        self._registrations: dict[str, ExternalDeliveryProviderRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: ExternalDeliveryProviderRegistration) -> None:
        canonical = registration.provider_id
        if registration.capabilities.provider_id != canonical:
            raise ValueError(
                "External delivery provider capability id mismatch: "
                f"registration={canonical!r}, capabilities={registration.capabilities.provider_id!r}"
            )
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise ValueError(f"External delivery provider key already registered: {key}")
        self._registrations[canonical] = registration
        for alias in registration.aliases:
            self._aliases[alias] = canonical

    def load_entry_points(self, group: str = EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP) -> list[str]:
        """Load provider registrations without invoking provider factories."""

        loaded_provider_ids: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                plugin_value = entry_point.load()
            except Exception as exc:
                raise RuntimeError(f"Failed to load external delivery provider entry point {entry_point.name!r}: {exc}") from exc
            registrations = self._coerce_plugin_registrations(entry_point.name, plugin_value)
            for registration in registrations:
                self.register(registration)
                loaded_provider_ids.append(registration.provider_id)
        return loaded_provider_ids

    def resolve(self, provider_id: str) -> ExternalDeliveryProviderRegistration:
        canonical = provider_id if provider_id in self._registrations else self._aliases.get(provider_id)
        if canonical is None:
            known = ", ".join(self.provider_ids())
            raise ValueError(f"Unsupported external delivery provider: {provider_id}. Known providers: {known}")
        return self._registrations[canonical]

    def is_registered(self, provider_id: str) -> bool:
        return provider_id in self._registrations or provider_id in self._aliases

    def create(self, provider_id: str, **kwargs: Any) -> ExternalDeliveryProvider:
        registration = self.resolve(provider_id)
        return registration.factory(**kwargs)

    def provider_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_capabilities(self) -> list[ExternalDeliveryProviderCapabilities]:
        return [self._registrations[key].capabilities for key in sorted(self._registrations)]

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.list_capabilities()]

    def list_registration_metadata(self) -> list[dict[str, Any]]:
        """Return canonical provider metadata plus aliases without creating providers."""

        payloads: list[dict[str, Any]] = []
        for provider_id in sorted(self._registrations):
            registration = self._registrations[provider_id]
            payload = registration.capabilities.to_dict()
            payload["aliases"] = list(registration.aliases)
            payload["keys"] = list(registration.keys)
            payloads.append(payload)
        return payloads

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[ExternalDeliveryProviderRegistration]:
        if isinstance(value, ExternalDeliveryProviderRegistration):
            return [value]
        if callable(value):
            return ExternalDeliveryProviderRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, ExternalDeliveryProviderRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "External delivery provider entry point "
            f"{entry_point_name!r} must return an ExternalDeliveryProviderRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


def review_only_external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id="review-only",
        aliases=("noop", "manual-handoff"),
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id="review-only",
            display_name="Review-only external delivery handoff",
            transport="in-process",
            supports_external_delivery=False,
            review_only=True,
            metadata={
                "side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": False,
            },
        ),
        factory=lambda **_: ReviewOnlyExternalDeliveryProvider(),
    )


def local_archive_external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id="local-archive",
        aliases=("filesystem-release", "archive"),
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id="local-archive",
            display_name="Local archive external delivery",
            transport="filesystem",
            supports_external_delivery=True,
            review_only=False,
            metadata={
                "side_effect_free": False,
                "dry_run_side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": True,
                "external_boundary": "local-filesystem-archive",
                "network_required": False,
            },
        ),
        factory=lambda **kwargs: LocalArchiveExternalDeliveryProvider(**kwargs),
    )


def presigned_object_external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id="presigned-object",
        aliases=("object-storage", "presigned-url", "s3-presigned"),
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id="presigned-object",
            display_name="Presigned object storage external delivery",
            transport="object-storage",
            supports_external_delivery=True,
            review_only=False,
            metadata={
                "side_effect_free": False,
                "dry_run_side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": True,
                "external_boundary": "presigned-object-storage-url",
                "sends_http_put": True,
                "supports_explicit_retry": True,
                "default_retry_attempts": 0,
                "default_retry_status_codes": list(DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES),
                "records_response_body": False,
                "records_response_headers": False,
                "cloud_sdk_required": False,
            },
        ),
        factory=lambda **kwargs: PresignedObjectExternalDeliveryProvider(**kwargs),
    )


def webhook_external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id="webhook",
        aliases=("webhook-json", "http-webhook"),
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id="webhook",
            display_name="HTTP JSON webhook external delivery",
            transport="webhook",
            supports_external_delivery=True,
            review_only=False,
            metadata={
                "side_effect_free": False,
                "dry_run_side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": True,
                "external_boundary": "http-json-webhook",
                "sends_http_post": True,
                "supports_explicit_retry": True,
                "default_retry_attempts": 0,
                "default_retry_status_codes": list(DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES),
                "records_response_body": False,
                "records_response_headers": False,
            },
        ),
        factory=lambda **kwargs: WebhookExternalDeliveryProvider(**kwargs),
    )


def github_release_external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    return ExternalDeliveryProviderRegistration(
        provider_id="github-release",
        aliases=("gh-release", "github-release-assets"),
        capabilities=ExternalDeliveryProviderCapabilities(
            provider_id="github-release",
            display_name="GitHub Release asset external delivery",
            transport="github-release",
            supports_external_delivery=True,
            review_only=False,
            metadata={
                "side_effect_free": False,
                "dry_run_side_effect_free": True,
                "writes_external_delivery_result": True,
                "publishes_externally": True,
                "external_boundary": "github-release-asset",
                "sends_http_post": True,
                "supports_explicit_retry": True,
                "default_retry_attempts": 0,
                "default_retry_status_codes": list(DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES),
                "supports_existing_release_reuse": True,
                "supports_existing_asset_preflight": True,
                "supports_existing_asset_overwrite_preflight": True,
                "supports_existing_asset_delete_preflight": True,
                "existing_asset_conflict_default": "block",
                "supports_existing_asset_overwrite": True,
                "supports_existing_asset_delete": True,
                "existing_asset_overwrite_requires_explicit_approval": True,
                "records_response_body": False,
                "records_response_headers": False,
                "github_sdk_required": False,
            },
        ),
        factory=lambda **kwargs: GitHubReleaseExternalDeliveryProvider(**kwargs),
    )


def build_default_external_delivery_provider_registry(*, load_entry_points: bool = True) -> ExternalDeliveryProviderRegistry:
    registry = ExternalDeliveryProviderRegistry()
    registry.register(github_release_external_delivery_provider_registration())
    registry.register(local_archive_external_delivery_provider_registration())
    registry.register(presigned_object_external_delivery_provider_registration())
    registry.register(review_only_external_delivery_provider_registration())
    registry.register(webhook_external_delivery_provider_registration())
    if load_entry_points:
        registry.load_entry_points()
    return registry


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=group)
    else:  # pragma: no cover - compatibility with older importlib.metadata APIs
        selected = entry_points.get(group, [])
    return list(selected)
