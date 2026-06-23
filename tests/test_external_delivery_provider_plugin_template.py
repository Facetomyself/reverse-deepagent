import importlib
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.delivery import ExternalDeliveryPackage, ExternalDeliveryProviderRegistry


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-external-delivery-provider-template"


class ExternalDeliveryProviderPluginTemplateTests(unittest.TestCase):
    def test_package_declares_external_delivery_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-external-delivery-provider-template")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.external_delivery_providers"]
        self.assertEqual(
            entry_points["template-external-delivery"],
            "reverse_deepagent_external_delivery_provider_template:external_delivery_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_factory_is_explicit(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_external_delivery_provider_template")
            registration = module.external_delivery_provider_registration()
            registry = ExternalDeliveryProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create("external-delivery-template", target_service="internal-release-api")
            self.assertEqual(module.factory_invocation_count(), 1)
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_external_delivery_provider_template", None)

        self.assertEqual(registration.provider_id, "template-external-delivery")
        self.assertEqual(metadata[0]["provider_id"], "template-external-delivery")
        self.assertIn("custom-external-delivery-template", metadata[0]["aliases"])
        self.assertFalse(metadata[0]["supports_external_delivery"])
        self.assertTrue(metadata[0]["review_only"])
        self.assertTrue(metadata[0]["metadata"]["template_only"])
        self.assertFalse(metadata[0]["metadata"]["publishes_externally"])
        self.assertEqual(provider.provider_id, "template-external-delivery")

    def test_template_provider_dry_run_plans_and_apply_blocks_without_publishing(self) -> None:
        package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, package_src)
        try:
            module = importlib.import_module("reverse_deepagent_external_delivery_provider_template")
            provider = module.create_template_external_delivery_provider(target_service="s3-compatible")
            package = ExternalDeliveryPackage(
                transaction_id="tx-template",
                status="applied",
                mode="apply",
                delivery_root="/tmp/reverse-agent-template-delivery",
                receipt_path=None,
                transaction_journal_path=None,
                external_delivery_result_path=None,
                delivered_artifacts=[],
                planned_artifacts=[],
                local_errors=[],
                created_at="2026-06-01T00:00:00+00:00",
                metadata={"source": "test"},
            )
            dry_run = provider.deliver(
                package,
                dry_run=True,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:01+00:00",
            )
            apply_result = provider.deliver(
                package,
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:02+00:00",
            )
        finally:
            sys.path.remove(package_src)
            sys.modules.pop("reverse_deepagent_external_delivery_provider_template", None)

        self.assertEqual(dry_run.status, "planned")
        self.assertEqual(apply_result.status, "blocked")
        self.assertFalse(dry_run.external_delivery_performed)
        self.assertFalse(apply_result.external_delivery_performed)
        self.assertIn("template_provider_replaced_with_real_delivery_logic", apply_result.blocking_reasons)
        self.assertEqual(apply_result.metadata["config"]["target_service"], "s3-compatible")
        self.assertTrue(apply_result.metadata["template_only"])
        self.assertFalse(apply_result.metadata["publishes_externally"])
        self.assertEqual(len(apply_result.package_digest_sha256), 64)


if __name__ == "__main__":
    unittest.main()
