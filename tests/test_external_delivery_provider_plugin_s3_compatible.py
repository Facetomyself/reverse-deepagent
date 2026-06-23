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


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-external-delivery-provider-s3-compatible"
MODULE_NAME = "reverse_deepagent_external_delivery_provider_s3_compatible"


class S3CompatibleExternalDeliveryProviderPluginTests(unittest.TestCase):
    def test_package_declares_external_delivery_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-external-delivery-provider-s3-compatible")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.external_delivery_providers"]
        self.assertEqual(
            entry_points["s3-compatible"],
            "reverse_deepagent_external_delivery_provider_s3_compatible:external_delivery_provider_registration",
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
                "minio",
                endpoint_url="https://minio.example.test",
                bucket="reviewed-deliveries",
                object_name="tx-1/delivery.json",
                approve_s3_delivery=True,
            )
            self.assertEqual(module.factory_invocation_count(), 1)

        self.assertEqual(registration.provider_id, "s3-compatible")
        self.assertEqual(metadata[0]["provider_id"], "s3-compatible")
        self.assertIn("s3", metadata[0]["aliases"])
        self.assertIn("s3-object", metadata[0]["aliases"])
        self.assertIn("minio", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_external_delivery"])
        self.assertFalse(metadata[0]["review_only"])
        self.assertEqual(metadata[0]["transport"], "s3-compatible-object-storage")
        self.assertTrue(metadata[0]["metadata"]["side_effect_free"])
        self.assertTrue(metadata[0]["metadata"]["dry_run_side_effect_free"])
        self.assertTrue(metadata[0]["metadata"]["apply_requires_explicit_review_approval"])
        self.assertFalse(external_delivery_metadata_has_secret_like_keys(registration.capabilities.to_dict()))
        self.assertEqual(provider.provider_id, "s3-compatible")

    def test_dry_run_plans_without_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("dry-run must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_s3_compatible_external_delivery_provider(
                endpoint_url="https://minio.example.test",
                bucket="reviewed-deliveries",
                object_name="tx-dry-run/delivery.json",
                headers={"x-amz-meta-review": "approved-plan"},
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
        self.assertEqual(result.recommended_actions, ["approve_s3_delivery_before_apply"])
        self.assertEqual(result.metadata["target_url"], "https://minio.example.test/<redacted-object-target>")
        self.assertEqual(result.metadata["object_name"], "tx-dry-run/delivery.json")
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("approved-plan", serialized)
        self.assertNotIn("x-amz-meta-review", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_apply_blocks_without_explicit_review_approval_and_does_not_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("unapproved apply must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_s3_compatible_external_delivery_provider(
                endpoint_url="https://minio.example.test",
                bucket="reviewed-deliveries",
                object_name="tx-unapproved/delivery.json",
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
        self.assertIn("s3_apply_intent_reviewed", result.blocking_reasons)
        self.assertFalse(result.metadata["network_attempted"])

    def test_apply_with_mocked_http_success_records_secret_safe_metadata(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:

            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                return module.S3CompatibleHttpResponse(status_code=200, error=None, body=b'{"ignored":"response-body"}')

            provider = module.create_s3_compatible_external_delivery_provider(
                endpoint_url="https://minio.example.test/base",
                bucket="reviewed-deliveries",
                object_name="tx-apply/delivery-package.json",
                headers={"Authorization": "Bearer header-secret", "x-amz-meta-source": "private-note"},
                approve_s3_delivery=True,
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
        self.assertEqual(call["method"], "PUT")
        self.assertEqual(call["url"], "https://minio.example.test/base/reviewed-deliveries/tx-apply/delivery-package.json")
        self.assertEqual(call["headers"]["Authorization"], "Bearer header-secret")
        self.assertEqual(call["headers"]["x-amz-meta-source"], "private-note")
        payload = json.loads(call["body"].decode("utf-8"))
        self.assertEqual(payload["provider_id"], "s3-compatible")
        self.assertEqual(payload["object_name"], "tx-apply/delivery-package.json")
        self.assertIn("package_digest_sha256", payload)
        self.assertEqual(result.metadata["request_status_code"], 200)
        self.assertEqual(result.metadata["http_library"], "injected-http-requester")
        self.assertTrue(result.metadata["network_attempted"])
        self.assertFalse(result.metadata["request_headers_recorded"])
        self.assertFalse(result.metadata["response_body_recorded"])
        self.assertFalse(result.metadata["response_headers_recorded"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("Bearer header-secret", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("private-note", serialized)
        self.assertNotIn("response-body", serialized)
        self.assertNotIn("reviewed-deliveries", serialized)

    def test_inline_url_material_blocks_by_default_and_presigned_review_stays_redacted(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:

            def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                raise AssertionError("inline URL material must be blocked before network IO")

            blocked_provider = module.create_s3_compatible_external_delivery_provider(
                upload_url="https://user:url-secret@minio.example.test/reviewed-deliveries/object.json?X-Amz-Signature=query-secret",
                approve_s3_delivery=True,
                http_requester=fail_if_called,
            )
            blocked_result = blocked_provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:04+00:00",
            )
            reviewed_calls: list[dict[str, object]] = []

            def reviewed_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                reviewed_calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                return module.S3CompatibleHttpResponse(status_code=204, error=None, body=b"")

            reviewed_provider = module.create_s3_compatible_external_delivery_provider(
                upload_url="https://minio.example.test/reviewed-deliveries/object.json?X-Amz-Signature=query-secret",
                allow_reviewed_presigned_url=True,
                approve_s3_delivery=True,
                http_requester=reviewed_requester,
            )
            reviewed_result = reviewed_provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:05+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(blocked_result.status, "blocked")
        self.assertFalse(blocked_result.external_delivery_performed)
        self.assertFalse(blocked_result.metadata["network_attempted"])
        self.assertIn("s3_target_url_has_no_unreviewed_inline_material", blocked_result.blocking_reasons)
        self.assertTrue(blocked_result.metadata["target_query_redacted"])
        self.assertTrue(blocked_result.metadata["target_userinfo_redacted"])
        self.assertNotIn("?", blocked_result.metadata["target_url"] or "")
        self.assertNotIn("@", blocked_result.metadata["target_url"] or "")
        blocked_serialized = json.dumps(blocked_result.to_dict(), ensure_ascii=False)
        self.assertNotIn("url-secret", blocked_serialized)
        self.assertNotIn("query-secret", blocked_serialized)
        self.assertNotIn("X-Amz-Signature", blocked_serialized)

        self.assertEqual(reviewed_result.status, "delivered")
        self.assertTrue(reviewed_result.external_delivery_performed)
        self.assertTrue(reviewed_result.metadata["reviewed_presigned_mode"])
        self.assertEqual(len(reviewed_calls), 1)
        self.assertIn("X-Amz-Signature=query-secret", reviewed_calls[0]["url"])
        reviewed_serialized = json.dumps(reviewed_result.to_dict(), ensure_ascii=False)
        self.assertNotIn("query-secret", reviewed_serialized)
        self.assertNotIn("X-Amz-Signature", reviewed_serialized)
        self.assertNotIn("?", reviewed_result.metadata["target_url"] or "")


def _package(*, mode: str = "apply") -> ExternalDeliveryPackage:
    return ExternalDeliveryPackage(
        transaction_id="tx-s3-compatible",
        status="applied",
        mode=mode,
        delivery_root="/tmp/reverse-agent-s3-compatible-delivery",
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
