from __future__ import annotations

import importlib
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from reverse_deepagent.delivery import (
    ExternalDeliveryPackage,
    ExternalDeliveryProviderRegistry,
    external_delivery_metadata_has_secret_like_keys,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-external-delivery-provider-gitlab-release"
MODULE_NAME = "reverse_deepagent_external_delivery_provider_gitlab_release"


class GitLabReleaseExternalDeliveryProviderPluginTests(unittest.TestCase):
    def test_package_declares_external_delivery_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-external-delivery-provider-gitlab-release")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.external_delivery_providers"]
        self.assertEqual(
            entry_points["gitlab-release"],
            "reverse_deepagent_external_delivery_provider_gitlab_release:external_delivery_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_factory_is_explicit(self) -> None:
        with _import_plugin_module() as module:
            registration = module.external_delivery_provider_registration()
            registry = ExternalDeliveryProviderRegistry()
            registry.register(registration)
            metadata = registry.list_registration_metadata()
            self.assertEqual(module.factory_invocation_count(), 0)
            provider = registry.create("gl-release", project_path="group/project", tag_name="v1", access_token="not-serialized")
            self.assertEqual(module.factory_invocation_count(), 1)

        self.assertEqual(registration.provider_id, "gitlab-release")
        self.assertEqual(metadata[0]["provider_id"], "gitlab-release")
        self.assertIn("gitlab-release-assets", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_external_delivery"])
        self.assertFalse(metadata[0]["review_only"])
        self.assertEqual(metadata[0]["transport"], "gitlab-release")
        self.assertTrue(metadata[0]["metadata"]["dry_run_side_effect_free"])
        self.assertTrue(metadata[0]["metadata"]["apply_requires_explicit_review_approval"])
        self.assertFalse(external_delivery_metadata_has_secret_like_keys(registration.capabilities.to_dict()))
        self.assertEqual(provider.provider_id, "gitlab-release")

    def test_dry_run_plans_without_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("dry-run must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/project",
                tag_name="v1.0.0",
                access_token="glpat-dry-run-secret",
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
        self.assertFalse(result.metadata["project_path_recorded"])
        self.assertEqual(result.recommended_actions, ["approve_gitlab_release_delivery_before_apply"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-dry-run-secret", serialized)
        self.assertNotIn("PRIVATE-TOKEN", serialized)
        self.assertNotIn("Authorization", serialized)

    def test_apply_blocks_without_explicit_review_approval_and_does_not_network(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("unapproved apply must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/project",
                tag_name="v1.0.0",
                access_token="glpat-unapproved-secret",
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
        self.assertIn("gitlab_release_apply_intent_reviewed", result.blocking_reasons)
        self.assertFalse(result.metadata["network_attempted"])

    def test_apply_with_mocked_http_success_records_secret_safe_metadata(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b'{"secret":"not-read"}')

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/private-project",
                tag_name="v1.0.0",
                release_name="Reverse DeepAgent v1.0.0",
                asset_name="delivery-package.json",
                access_token="glpat-apply-secret",
                api_base_url="https://gitlab.example.test/api/v4",
                approve_gitlab_release_delivery=True,
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
        self.assertEqual(call["url"], "https://gitlab.example.test/api/v4/projects/group%2Fprivate-project/releases")
        self.assertEqual(call["headers"]["PRIVATE-TOKEN"], "glpat-apply-secret")
        payload = json.loads(call["body"].decode("utf-8"))
        self.assertEqual(payload["tag_name"], "v1.0.0")
        self.assertIn("package_digest_sha256", payload["description"])
        self.assertEqual(result.metadata["request_status_code"], 201)
        self.assertFalse(result.metadata["binary_asset_upload"]["requested"])
        self.assertFalse(result.metadata["asset_upload_request_attempted"])
        self.assertFalse(result.metadata["asset_link_request_attempted"])
        self.assertEqual(result.metadata["http_library"], "injected-http-requester")
        self.assertTrue(result.metadata["network_attempted"])
        self.assertFalse(result.metadata["request_headers_recorded"])
        self.assertFalse(result.metadata["response_body_recorded"])
        self.assertFalse(result.metadata["response_headers_recorded"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-apply-secret", serialized)
        self.assertNotIn("PRIVATE-TOKEN", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("group/private-project", serialized)
        self.assertNotIn("group%2Fprivate-project", serialized)
        self.assertNotIn("not-read", serialized)

    def test_metadata_redacts_and_blocks_credentialed_or_queried_api_url(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                raise AssertionError("inline-secret api_base_url must be blocked before network IO")

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="secret-group/secret-project",
                tag_name="v2.0.0",
                access_token="glpat-redaction-secret",
                api_base_url="https://oauth2:url-secret@gitlab.example.test/api/v4?private_token=query-secret",
                approve_gitlab_release_delivery=True,
                http_requester=fail_if_called,
            )
            dry_run_result = provider.deliver(
                _package(),
                dry_run=True,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:04+00:00",
            )
            apply_result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:05+00:00",
            )

        self.assertEqual(calls, [])
        for result in (dry_run_result, apply_result):
            self.assertEqual(result.status, "blocked")
            self.assertFalse(result.external_delivery_performed)
            self.assertFalse(result.metadata["network_attempted"])
            self.assertIn("gitlab_api_url_has_no_inline_secret_material", result.blocking_reasons)
            self.assertTrue(result.metadata["api_query_redacted"])
            self.assertTrue(result.metadata["api_credentials_redacted"])
            inline_secret_check = next(check for check in result.checks if check["name"] == "gitlab_api_url_has_no_inline_secret_material")
            self.assertFalse(inline_secret_check["passed"])
            self.assertTrue(inline_secret_check["details"]["query_redacted"])
            self.assertTrue(inline_secret_check["details"]["credentials_redacted"])
            serialized = json.dumps(result.to_dict(), ensure_ascii=False)
            self.assertNotIn("glpat-redaction-secret", serialized)
            self.assertNotIn("url-secret", serialized)
            self.assertNotIn("query-secret", serialized)
            self.assertNotIn("secret-group/secret-project", serialized)
            self.assertNotIn("private_token", serialized)
            self.assertNotIn("?", result.metadata["api_base_url"] or "")
            self.assertNotIn("@", result.metadata["api_base_url"] or "")

    def test_dry_run_asset_upload_plans_without_network_or_file_read(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("dry-run asset plan must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/project",
                tag_name="v1.0.0",
                access_token="glpat-dry-run-asset-secret",
                upload_asset_path="/tmp/reverse-agent-this-file-must-not-be-read.bin",
                upload_asset_name="agent.bundle.tgz",
                http_requester=fail_if_called,
            )
            result = provider.deliver(
                _package(),
                dry_run=True,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:06+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "planned")
        self.assertFalse(result.external_delivery_performed)
        self.assertFalse(result.metadata["network_attempted"])
        upload_plan = result.metadata["binary_asset_upload"]
        self.assertTrue(upload_plan["requested"])
        self.assertEqual(upload_plan["name"], "agent.bundle.tgz")
        self.assertEqual(upload_plan["source_type"], "path")
        self.assertTrue(upload_plan["source_descriptor_present"])
        self.assertIsNone(upload_plan["source_size_bytes"])
        self.assertIsNone(upload_plan["source_digest_sha256"])
        self.assertIn("approve_gitlab_release_asset_upload_before_apply", result.recommended_actions)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-dry-run-asset-secret", serialized)
        self.assertNotIn("PRIVATE-TOKEN", serialized)

    def test_asset_upload_path_must_be_file_before_release_create(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("directory asset path must be blocked before creating a release")

        with tempfile.TemporaryDirectory() as directory, _import_plugin_module() as module:
            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/project",
                tag_name="v1.0.0",
                access_token="glpat-directory-secret",
                approve_gitlab_release_delivery=True,
                approve_gitlab_release_asset_upload=True,
                upload_asset_path=directory,
                upload_asset_name="agent.bin",
                http_requester=fail_if_called,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:06.5+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertFalse(result.metadata["network_attempted"])
        self.assertFalse(result.metadata["release_record_created"])
        self.assertIn("gitlab_release_asset_upload_executable_source_available", result.blocking_reasons)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-directory-secret", serialized)

    def test_asset_upload_apply_blocks_without_asset_upload_approval(self) -> None:
        calls: list[dict[str, object]] = []

        def fail_if_called(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
            calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
            raise AssertionError("unapproved asset upload must not perform network IO")

        with _import_plugin_module() as module:
            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/project",
                tag_name="v1.0.0",
                access_token="glpat-asset-unapproved-secret",
                approve_gitlab_release_delivery=True,
                upload_asset_bytes=b"binary payload",
                upload_asset_name="agent.bin",
                http_requester=fail_if_called,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:07+00:00",
            )

        self.assertEqual(calls, [])
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertFalse(result.metadata["network_attempted"])
        self.assertIn("gitlab_release_asset_upload_reviewed", result.blocking_reasons)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-asset-unapproved-secret", serialized)

    def test_apply_with_mocked_asset_upload_and_release_link_success(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                if url.endswith("/uploads"):
                    return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b'{"url":"/uploads/hash/agent.bin","secret":"not-recorded"}')
                return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b'{"secret":"not-read"}')

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/private-project",
                tag_name="v1.0.0",
                release_name="Reverse DeepAgent v1.0.0",
                access_token="glpat-asset-apply-secret",
                api_base_url="https://gitlab.example.test/api/v4",
                approve_gitlab_release_delivery=True,
                approve_gitlab_release_asset_upload=True,
                upload_asset_bytes=b"binary payload",
                upload_asset_name="agent.bin",
                upload_asset_content_type="application/octet-stream",
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:08+00:00",
            )

        self.assertEqual(result.status, "delivered")
        self.assertTrue(result.external_delivery_performed)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["url"], "https://gitlab.example.test/api/v4/projects/group%2Fprivate-project/releases")
        self.assertEqual(calls[1]["url"], "https://gitlab.example.test/api/v4/projects/group%2Fprivate-project/uploads")
        self.assertEqual(calls[2]["url"], "https://gitlab.example.test/api/v4/projects/group%2Fprivate-project/releases/v1.0.0/assets/links")
        self.assertIn("multipart/form-data", calls[1]["headers"]["Content-Type"])
        self.assertEqual(calls[1]["headers"]["PRIVATE-TOKEN"], "glpat-asset-apply-secret")
        link_payload = json.loads(calls[2]["body"].decode("utf-8"))
        self.assertEqual(link_payload["name"], "agent.bin")
        self.assertEqual(link_payload["link_type"], "package")
        self.assertTrue(link_payload["url"].endswith("/group/private-project/uploads/hash/agent.bin"))
        upload_plan = result.metadata["binary_asset_upload"]
        self.assertTrue(upload_plan["requested"])
        self.assertEqual(upload_plan["source_size_bytes"], len(b"binary payload"))
        self.assertEqual(upload_plan["source_digest_sha256"], module.hashlib.sha256(b"binary payload").hexdigest())
        self.assertTrue(result.metadata["release_record_created"])
        self.assertTrue(result.metadata["asset_upload_request_attempted"])
        self.assertTrue(result.metadata["asset_link_request_attempted"])
        self.assertFalse(result.metadata["upload_response_url_recorded"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-asset-apply-secret", serialized)
        self.assertNotIn("PRIVATE-TOKEN", serialized)
        self.assertNotIn("group/private-project", serialized)
        self.assertNotIn("group%2Fprivate-project", serialized)
        self.assertNotIn("not-recorded", serialized)
        self.assertNotIn("/uploads/hash/agent.bin", serialized)

    def test_asset_upload_response_absolute_url_is_blocked_and_redacted(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                if url.endswith("/uploads"):
                    return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b'{"url":"https://evil.example/uploads/hash/agent.bin"}')
                return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b"{}")

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="secret-group/secret-project",
                tag_name="v1.0.0",
                access_token="glpat-absolute-upload-secret",
                api_base_url="https://gitlab.example.test/api/v4",
                approve_gitlab_release_delivery=True,
                approve_gitlab_release_asset_upload=True,
                upload_asset_bytes=b"binary payload",
                upload_asset_name="agent.bin",
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:08.5+00:00",
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertTrue(result.metadata["release_record_created"])
        self.assertTrue(result.metadata["upload_response_body_parsed"])
        self.assertFalse(result.metadata["upload_response_url_recorded"])
        self.assertFalse(result.metadata["asset_link_request_attempted"])
        self.assertEqual(result.metadata["asset_upload_error"], "UnsafeOrMissingUploadUrl")
        self.assertIn("gitlab_project_upload_successful", result.blocking_reasons)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-absolute-upload-secret", serialized)
        self.assertNotIn("evil.example", serialized)
        self.assertNotIn("secret-group/secret-project", serialized)
        self.assertNotIn("/uploads/hash/agent.bin", serialized)

    def test_asset_upload_response_url_with_query_is_blocked_and_redacted(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                if url.endswith("/uploads"):
                    return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b'{"url":"/uploads/hash/agent.bin?token=query-secret"}')
                return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b"{}")

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="secret-group/secret-project",
                tag_name="v1.0.0",
                access_token="glpat-upload-redaction-secret",
                api_base_url="https://gitlab.example.test/api/v4",
                approve_gitlab_release_delivery=True,
                approve_gitlab_release_asset_upload=True,
                upload_asset_bytes=b"binary payload",
                upload_asset_name="agent.bin",
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:09+00:00",
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertTrue(result.metadata["release_record_created"])
        self.assertTrue(result.metadata["upload_response_body_parsed"])
        self.assertFalse(result.metadata["upload_response_url_recorded"])
        self.assertEqual(result.metadata["asset_upload_error"], "UnsafeOrMissingUploadUrl")
        self.assertIn("gitlab_project_upload_successful", result.blocking_reasons)
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-upload-redaction-secret", serialized)
        self.assertNotIn("query-secret", serialized)
        self.assertNotIn("secret-group/secret-project", serialized)
        self.assertNotIn("/uploads/hash/agent.bin", serialized)

    def test_partial_failure_release_created_but_asset_upload_failed_is_conservative(self) -> None:
        calls: list[dict[str, object]] = []

        with _import_plugin_module() as module:
            def fake_requester(url: str, body: bytes, headers: dict[str, str], method: str, timeout_seconds: float):
                calls.append({"url": url, "body": body, "headers": headers, "method": method, "timeout_seconds": timeout_seconds})
                if url.endswith("/uploads"):
                    return module.GitLabReleaseHttpResponse(status_code=500, error="HTTPError", body=b'{"secret":"not-recorded"}')
                return module.GitLabReleaseHttpResponse(status_code=201, error=None, body=b"{}")

            provider = module.create_gitlab_release_external_delivery_provider(
                project_path="group/private-project",
                tag_name="v1.0.0",
                access_token="glpat-partial-secret",
                api_base_url="https://gitlab.example.test/api/v4",
                approve_gitlab_release_delivery=True,
                approve_gitlab_release_asset_upload=True,
                upload_asset_bytes=b"binary payload",
                upload_asset_name="agent.bin",
                http_requester=fake_requester,
            )
            result = provider.deliver(
                _package(mode="apply"),
                dry_run=False,
                result_path="/tmp/external-delivery-result.json",
                created_at="2026-06-01T00:00:10+00:00",
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.external_delivery_performed)
        self.assertTrue(result.metadata["release_record_created"])
        self.assertTrue(result.metadata["external_side_effects_performed"])
        self.assertTrue(result.metadata["asset_upload_request_attempted"])
        self.assertFalse(result.metadata["asset_link_request_attempted"])
        self.assertEqual(result.metadata["asset_upload_status_code"], 500)
        self.assertIn("gitlab_project_upload_successful", result.blocking_reasons)
        self.assertEqual(result.recommended_actions, ["review_gitlab_release_partial_asset_upload_failure_before_retry"])
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        self.assertNotIn("glpat-partial-secret", serialized)
        self.assertNotIn("not-recorded", serialized)


def _package(*, mode: str = "apply") -> ExternalDeliveryPackage:
    return ExternalDeliveryPackage(
        transaction_id="tx-gitlab-release",
        status="applied",
        mode=mode,
        delivery_root="/tmp/reverse-agent-gitlab-delivery",
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
