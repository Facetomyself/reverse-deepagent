from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from reverse_deepagent.delivery import (
    ExternalDeliveryPackage,
    ExternalDeliveryProviderCapabilities,
    ExternalDeliveryProviderRegistration,
    ExternalDeliveryResult,
)

TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ID = "template-external-delivery"
TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ALIASES = ("external-delivery-template", "custom-external-delivery-template")
_FACTORY_INVOCATION_COUNT = 0


@dataclass(frozen=True, slots=True)
class TemplateExternalDeliveryProviderConfig:
    """Non-secret config summary for a copied ExternalDeliveryProvider template."""

    display_name: str = "Template ExternalDeliveryProvider"
    transport: str = "template"
    target_service: str = "replace-me"

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "transport": self.transport,
            "target_service": self.target_service,
        }


@dataclass(frozen=True)
class TemplateExternalDeliveryProvider:
    """Copy-and-replace ExternalDeliveryProvider skeleton.

    The template is metadata-complete but publication-disabled by design. Real
    plugins should replace `deliver()` with SDK-specific or HTTP publication
    code and preserve dry-run / secret-redaction semantics.
    """

    config: TemplateExternalDeliveryProviderConfig | None = None
    provider_id: str = TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ID

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        config = self.config or TemplateExternalDeliveryProviderConfig()
        local_ready = not package.local_errors
        template_replaced = False
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "template_provider_replaced_with_real_delivery_logic",
                "passed": template_replaced,
                "details": {
                    "provider_id": self.provider_id,
                    "template_only": True,
                    "target_service": config.target_service,
                },
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        status = "planned" if dry_run and local_ready else "blocked"
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=False,
            package_digest_sha256=_package_digest_sha256(package),
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=[
                "replace_template_external_delivery_provider_before_apply",
                "keep_dry_run_and_secret_redaction_contracts",
            ],
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "external-delivery-provider-template",
                "automatic_delivery": False,
                "template_only": True,
                "publishes_externally": False,
                "config": config.summary(),
                "limitations": [
                    "template_provider_does_not_publish",
                    "replace_deliver_method_before_production_use",
                    "metadata_loading_must_not_invoke_factory_or_read_credentials",
                ],
            },
        )


def template_external_delivery_provider_capabilities(
    config: TemplateExternalDeliveryProviderConfig | None = None,
) -> ExternalDeliveryProviderCapabilities:
    """Return side-effect-free, non-secret provider metadata."""

    config = config or TemplateExternalDeliveryProviderConfig()
    return ExternalDeliveryProviderCapabilities(
        provider_id=TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ID,
        display_name=config.display_name,
        transport=config.transport,
        supports_external_delivery=False,
        review_only=True,
        metadata={
            "side_effect_free": True,
            "dry_run_side_effect_free": True,
            "writes_external_delivery_result": True,
            "publishes_externally": False,
            "template_only": True,
            "target_service": config.target_service,
            "replace_before_apply": True,
            "records_response_body": False,
            "records_response_headers": False,
        },
    )


def create_template_external_delivery_provider(**kwargs: Any) -> TemplateExternalDeliveryProvider:
    """Factory used by the ExternalDeliveryProviderRegistry.

    Registry metadata listing must not call this function. Tests intentionally
    track invocations so template authors can see the side-effect boundary.
    """

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    config = TemplateExternalDeliveryProviderConfig(
        display_name=kwargs.get("display_name", "Template ExternalDeliveryProvider"),
        transport=kwargs.get("transport", "template"),
        target_service=kwargs.get("target_service", "replace-me"),
    )
    return TemplateExternalDeliveryProvider(config=config)


def external_delivery_provider_registration() -> ExternalDeliveryProviderRegistration:
    """Return the template ExternalDeliveryProvider registration without side effects."""

    return ExternalDeliveryProviderRegistration(
        provider_id=TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ID,
        aliases=TEMPLATE_EXTERNAL_DELIVERY_PROVIDER_ALIASES,
        capabilities=template_external_delivery_provider_capabilities(),
        factory=create_template_external_delivery_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for template contract tests."""

    return _FACTORY_INVOCATION_COUNT


def _package_digest_sha256(package: ExternalDeliveryPackage) -> str:
    payload = json.dumps(package.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
