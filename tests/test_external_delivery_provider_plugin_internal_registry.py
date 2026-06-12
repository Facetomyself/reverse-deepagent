from __future__ import annotations

import importlib
import json
import sys
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.delivery import (
    ExternalDeliveryPackage,
    ExternalDeliveryProviderRegistry,
    external_delivery_metadata_has_secret_like_keys,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-external-delivery-provider-internal-registry"
MODULE_NAME = "reverse_deepagent_external_delivery_provider_internal_registry"


class InternalRegistryExternalDeliveryProviderPluginTests(unittest.TestCase):
    def test_package_declares_external_delivery_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-external-delivery-provider-internal-registry")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.external_delivery_providers"]
        self.assertEqual(
            entry_points["internal-registry"],
            "reverse_deepagent_external_delivery_provider_internal_registry:external_delivery_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_factory_is_explicit(self) -> None:
        with _import_plugin_module() as module:
            registration = module.external_delivery_provider_registration()
            registry = ExternalDeliveryProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create(
                "artifact-registry",
                registry_endpoint_url="https://registry.example.test/api/artifacts",
                namespace="private/team",
                project="reverse-deepagent",
                repository="reviewed-deliveries",
                approve_internal_registry_delivery=True,
            )
            self.assertEqual(module.factory_invocation_count(), 1)

        self.assertEqual(registration.provider_id, "internal-registry")
        self.assertEqual(metadata[0]["provider_id"], "internal-registry")
        self.assertIn("artifact-registry", metadata[0]["aliases"])
        self.assertIn("internal-artifacts", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_external_delivery"])
        self.assertFalse(metadata[0]["review_only"])
        self.assertEqual(metadata[0]["transport"], "internal-artifact-registry")
        self.assertTrue(metadata[0]["metadata"]["side_effect_free"])
        self.assertTrue(metadata[0]["metadata"]["dry_run_side_effect_free"])
        self.assertTrue(metadata[0]["metadata"]["apply_requires_explicit_review_approval"])
        self.assertFalse(external_delivery_metadata_has_secret_like_keys(registration.capabilities.to_dict()))
        self.assertEqual(provider.provider_id, "internal-registry")

    def test_dry_run_plans_without_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("dry-run must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_internal_registry_external_delivery_provider(
                registry_endpoint_url="https://registry.example.test/api/artifacts",
                namespace="private/team",
                project="reverse-deepagent",
                repository="reviewed-deliveries",
                headers={"x-registry-review": "approved-plan"},
                auth_token="registry-dry-run-secret",
                http_requester=fail_if_called,
            )
            result = provider.deliver(
                _package(),
                dry_run=True,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:01+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "planned")
        self.assertFalse(result.external_delivery_performed)
        self.assertFalse(result.metadata["network_attempted"])
        self.assertEqual(result.recommended_actions, ["approve_internal_registry_delivery_before_apply"])
        self.assertEqual(result.metadata["registry_endpoint_url"], "https://registry.example.test/<redacted-registry-endpoint>")
        self.assertFalse(result.metadata["namespace_recorded"])
        self.assertFalse(result.metadata["project_recorded"])
        self.assertFalse(result.metadata["repository_recorded"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("registry-dry-run-secret", serialized)
        self.assertNotIn("approved-plan", serialized)
        self.assertNotIn("x-registry-review", serialized)
        self.assertNotIn("private/team", serialized)
        self.assertNotIn("reviewed-deliveries", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_apply_blocks_without_explicit_review_approval_and_does_not_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("unapproved apply must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_internal_registry_external_delivery_provider(
                registry_endpoint_url="https://registry.example.test/api/artifacts",
                namespace="private/team",
                project="reverse-deepagent",
                repository="reviewed-deliveries",
                auth_token="registry-unapproved-secret",
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:02+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertIn("internal_registry_apply_intent_reviewed", result.blocking_reasons)
        self.assertFalse(result.metadata["network_attempted"])
        self.assertNotIn("registry-unapproved-secret", json.dumps(result.to_dict(), ensure_ascii=False))

    def test_apply_with_mocked_http_success_records_secret_safe_metadata(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:

            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                return module.InternalRegistryHttpResponse(status_code=201, error=None, body=b'{"ignored":"response-body"}')

            provider = module.create_internal_registry_external_delivery_provider(
                registry_endpoint_url="https://registry.example.test/api/artifacts",
                namespace="secret-group/private-project",
                project="reverse-deepagent-private",
                repository="reviewed-deliveries",
                package_name="internal-agent-bundle",
                package_version="2026.06.01",
                headers={"Authorization": "Bearer header-secret", "x-registry-note": "private-note"},
                auth_token="fallback-token-not-used",
                approve_internal_registry_delivery=True,
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:03+00:00",
            )

        self.assertEqual(result.status, "delivered")
        self.assertTrue(result.external_delivery_performed)
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], "https://registry.example.test/api/artifacts")
        self.assertEqual(call["headers"]["Authorization"], "Bearer header-secret")
        self.assertEqual(call["headers"]["x-registry-note"], "private-note")
        payload = json.loads(call["body"].decode("utf-8"))
        self.assertEqual(payload["provider_id"], "internal-registry")
        self.assertEqual(payload["identity"]["raw_values_recorded"], False)
        self.assertIn("package_digest_sha256", payload)
        self.assertEqual(result.metadata["request_status_code"], 201)
        self.assertEqual(result.metadata["http_library"], "injected-http-requester")
        self.assertTrue(result.metadata["network_attempted"])
        self.assertFalse(result.metadata["request_headers_recorded"])
        self.assertFalse(result.metadata["response_body_recorded"])
        self.assertFalse(result.metadata["response_headers_recorded"])
        self.assertFalse(result.metadata["provider_config_values_recorded"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("Bearer header-secret", serialized)
        self.assertNotIn("fallback-token-not-used", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("private-note", serialized)
        self.assertNotIn("response-body", serialized)
        self.assertNotIn("secret-group/private-project", serialized)
        self.assertNotIn("reverse-deepagent-private", serialized)
        self.assertNotIn("reviewed-deliveries", serialized)
        self.assertNotIn("internal-agent-bundle", serialized)

    def test_inline_secret_endpoint_blocks_by_default(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:

            def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                raise AssertionError("inline-secret endpoint must be blocked before network IO")

            provider = module.create_internal_registry_external_delivery_provider(
                registry_endpoint_url="https://user:url-secret@registry.example.test/api/artifacts?token=query-secret",
                namespace="secret-group/private-project",
                project="reverse-deepagent-private",
                repository="reviewed-deliveries",
                auth_token="registry-redaction-secret",
                approve_internal_registry_delivery=True,
                http_requester=fail_if_called,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:04+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertFalse(result.metadata["network_attempted"])
        self.assertIn("internal_registry_endpoint_url_has_no_inline_secret_material", result.blocking_reasons)
        self.assertTrue(result.metadata["registry_endpoint_query_redacted"])
        self.assertTrue(result.metadata["registry_endpoint_userinfo_redacted"])
        self.assertNotIn("?", result.metadata["registry_endpoint_url"] or "")
        self.assertNotIn("@", result.metadata["registry_endpoint_url"] or "")
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("registry-redaction-secret", serialized)
        self.assertNotIn("url-secret", serialized)
        self.assertNotIn("query-secret", serialized)
        self.assertNotIn("secret-group/private-project", serialized)
        self.assertNotIn("private-project", serialized)

    def test_partial_failure_is_conservative_blocked_result(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:

            def failing_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                return module.InternalRegistryHttpResponse(status_code=503, error="http_error:503", body=b'{"secret":"not-recorded"}')

            provider = module.create_internal_registry_external_delivery_provider(
                registry_endpoint_url="https://registry.example.test/api/artifacts",
                namespace="private/team",
                project="reverse-deepagent",
                repository="reviewed-deliveries",
                approve_internal_registry_delivery=True,
                http_requester=failing_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:05+00:00",
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertTrue(result.metadata["network_attempted"])
        self.assertEqual(result.metadata["request_status_code"], 503)
        self.assertIn("internal_registry_publication_successful", result.blocking_reasons)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("not-recorded", serialized)
        self.assertNotIn("private/team", serialized)
        self.assertNotIn("reviewed-deliveries", serialized)


def _package(*, mode: str = "apply") -> ExternalDeliveryPackage:
    return ExternalDeliveryPackage(
        transaction_id="tx-internal-registry",
        status="applied",
        mode=mode,
        delivery_root="/tmp/reverse-agent-internal-registry-delivery",
        receipt_path=None,
        transaction_journal_path=None,
        external_delivery_result_path=None,
        delivered_artifacts=[{"destination_name": "delivery-package.json", "sha256": "abc123"}],
        planned_artifacts=[],
        local_errors=[],
        created_at="2026-06-01T00:00:00+00:00",
        metadata={"source": "test"},
    )


class _import_plugin_module:
    def __enter__(self):
        self.package_src = str(PACKAGE_ROOT / "src")
        sys.path.insert(0, self.package_src)
        self.module = importlib.import_module(MODULE_NAME)
        return self.module

    def __exit__(self, exc_type, exc, tb):
        sys.path.remove(self.package_src)
        sys.modules.pop(MODULE_NAME, None)
        return False


if __name__ == "__main__":
    unittest.main()
