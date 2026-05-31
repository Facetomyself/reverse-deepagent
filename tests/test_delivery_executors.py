from __future__ import annotations

import hashlib
import http.server
import json
import tempfile
import threading
from pathlib import Path
from unittest import TestCase

from reverse_deepagent.delivery import (
    DeliveryArtifact,
    DeliveryExecutionMode,
    DeliveryExecutorConfig,
    ExternalDeliveryPackage,
    ExternalDeliveryResult,
    LocalDeliveryExecutor,
)


class FakeExternalDeliveryProvider:
    provider_id = "fake-provider"

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
            package_digest_sha256="fake-package-digest",
            checks=[{"name": "fake_provider_delivered", "passed": True, "details": {}}],
            blocking_reasons=[],
            recommended_actions=["review_fake_external_delivery_result"],
            created_at=created_at,
            metadata={"scope": "test-fake-external-delivery-provider"},
        )


class CountingExternalDeliveryProvider(FakeExternalDeliveryProvider):
    def __init__(self) -> None:
        self.calls = 0
        self.packages: list[ExternalDeliveryPackage] = []

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        self.calls += 1
        self.packages.append(package)
        return super().deliver(package, dry_run=dry_run, result_path=result_path, created_at=created_at)


class RecordingWebhookHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RetryingWebhookHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        if len(self.__class__.requests) == 1:
            self.send_response(503)
            self.send_header("Retry-After", "2")
            self.send_header("X-RateLimit-Limit", "60")
            self.send_header("X-RateLimit-Remaining", "0")
            self.send_header("X-RateLimit-Reset", "1234567890")
            self.send_header("X-RateLimit-Used", "60")
            self.send_header("X-RateLimit-Resource", "webhook")
            self.end_headers()
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RecordingObjectHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.__class__.requests.append(
            {
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RecordingGitHubReleaseHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def _record_request(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._record_request(body)
        if self.path == "/repos/owner/repo/releases":
            response = json.dumps(
                {
                    "id": 1,
                    "assets_url": f"http://127.0.0.1:{self.server.server_port}/repos/owner/repo/releases/1/assets?asset_query=hidden",
                    "upload_url": f"http://127.0.0.1:{self.server.server_port}/uploads/assets{{?name,label}}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path.startswith("/uploads/assets?name="):
            response = b'{"id":2}'
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._record_request()
        if self.path.startswith("/repos/owner/repo/releases/1/assets"):
            response = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RetryingGitHubReleaseHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def _record_request(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._record_request(body)
        release_request_count = sum(
            1
            for request in self.__class__.requests
            if request.get("method") == "POST" and request.get("path") == "/repos/owner/repo/releases"
        )
        if self.path == "/repos/owner/repo/releases" and release_request_count == 1:
            response = b'{"message":"secondary rate limit","secret":"body-not-recorded"}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.send_header("Retry-After", "3")
            self.send_header("X-RateLimit-Limit", "5000")
            self.send_header("X-RateLimit-Remaining", "0")
            self.send_header("X-RateLimit-Reset", "1234567891")
            self.send_header("X-RateLimit-Used", "5000")
            self.send_header("X-RateLimit-Resource", "core")
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path == "/repos/owner/repo/releases":
            response = json.dumps(
                {
                    "id": 9,
                    "assets_url": f"http://127.0.0.1:{self.server.server_port}/repos/owner/repo/releases/9/assets?asset_query=hidden",
                    "upload_url": f"http://127.0.0.1:{self.server.server_port}/uploads/retry{{?name,label}}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path.startswith("/uploads/retry?name="):
            response = b'{"id":10}'
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._record_request()
        if self.path.startswith("/repos/owner/repo/releases/9/assets"):
            response = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RecordingGitHubReleaseReuseHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def _record_request(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._record_request(body)
        if self.path == "/repos/owner/repo/releases":
            response = b'{"message":"already_exists","secret":"body-not-recorded"}'
            self.send_response(422)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path.startswith("/uploads/existing?name="):
            response = b'{"id":3,"secret":"upload-response-not-recorded"}'
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._record_request()
        if self.path == "/repos/owner/repo/releases/tags/v0-existing":
            response = json.dumps(
                {
                    "id": 2,
                    "assets_url": f"http://127.0.0.1:{self.server.server_port}/repos/owner/repo/releases/2/assets?asset_query=hidden",
                    "upload_url": f"http://127.0.0.1:{self.server.server_port}/uploads/existing{{?name,label}}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path.startswith("/repos/owner/repo/releases/2/assets"):
            response = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class RecordingGitHubReleaseAssetPreflightHandler(http.server.BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    existing_assets: list[dict[str, object]] = []
    delete_status_code: int = 204

    def _record_request(self, body: bytes = b"") -> None:
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": body,
            }
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._record_request(body)
        if self.path == "/repos/owner/repo/releases":
            response = json.dumps(
                {
                    "id": 7,
                    "assets_url": f"http://127.0.0.1:{self.server.server_port}/repos/owner/repo/releases/7/assets?asset_query=hidden",
                    "upload_url": f"http://127.0.0.1:{self.server.server_port}/uploads/duplicate{{?name,label}}",
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        if self.path.startswith("/uploads/duplicate?name="):
            response = b'{"id":8,"secret":"upload-response-not-recorded"}'
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._record_request()
        if self.path.startswith("/repos/owner/repo/releases/7/assets"):
            response = json.dumps(
                self.__class__.existing_assets,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
        self._record_request()
        self.send_response(int(self.__class__.delete_status_code))
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib handler API
        return


class LocalDeliveryExecutorTests(TestCase):
    def test_dry_run_plans_local_delivery_without_writing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-1",
                    mode=DeliveryExecutionMode.DRY_RUN,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertTrue(result.dry_run)
            self.assertTrue(result.delivery_allowed)
            self.assertFalse(result.filesystem_artifact_mutated)
            self.assertFalse(result.external_delivery_performed)
            self.assertFalse(result.manifest_revision_committed)
            self.assertEqual(result.next_action, "approve_local_delivery_apply")
            self.assertEqual(len(result.planned_artifacts), 1)
            self.assertFalse(delivery_root.exists())
            self.assertIsNone(result.receipt.receipt_path)
            self.assertIsNone(result.transaction_journal.journal_path)
            self.assertFalse(result.transaction_journal.filesystem_artifact_mutated)

    def test_apply_copies_artifacts_and_writes_receipt_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    metadata={"source": "unit-test"},
                )
            ).execute(
                [
                    DeliveryArtifact(
                        source_path=source,
                        artifact_key="workspace_final",
                        destination_name="final-result.json",
                        metadata={"category": "final"},
                    )
                ]
            )

            delivered = delivery_root / "final-result.json"
            receipt_path = delivery_root / "delivery-receipt.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "delivered")
            self.assertFalse(result.dry_run)
            self.assertTrue(result.delivery_allowed)
            self.assertTrue(result.filesystem_artifact_mutated)
            self.assertFalse(result.external_delivery_performed)
            self.assertFalse(result.manifest_revision_committed)
            self.assertTrue(delivered.exists())
            self.assertEqual(delivered.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertTrue(receipt_path.exists())
            self.assertTrue(journal_path.exists())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["transaction_id"], "tx-apply")
            self.assertEqual(receipt["status"], "delivered")
            self.assertEqual(receipt["delivered_artifacts"][0]["artifact_key"], "workspace_final")
            self.assertEqual(journal["status"], "delivered")
            self.assertTrue(journal["filesystem_artifact_mutated"])
            self.assertFalse(journal["external_delivery_performed"])
            self.assertFalse(journal["manifest_revision_committed"])
            self.assertIn("does_not_publish_external_delivery", journal["metadata"]["limitations"])


    def test_apply_can_commit_local_manifest_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-manifest",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_manifest_revision=True,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            revision_path = delivery_root / "delivery-manifest-revision.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "delivered")
            self.assertTrue(result.manifest_revision_committed)
            self.assertIsNotNone(result.manifest_revision)
            self.assertTrue(result.manifest_revision.committed)
            self.assertFalse(result.manifest_revision.backend_manifest_mutated)
            self.assertTrue(revision_path.exists())
            revision = json.loads(revision_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(revision["status"], "committed")
            self.assertEqual(revision["revision_id"], "manifest-revision-tx-manifest")
            self.assertFalse(revision["backend_manifest_mutated"])
            self.assertEqual(journal["manifest_revision_path"], str(revision_path.resolve()))
            self.assertTrue(journal["manifest_revision_committed"])

    def test_dry_run_manifest_revision_request_is_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-manifest-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    commit_manifest_revision=True,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.manifest_revision_committed)
            self.assertIsNotNone(result.manifest_revision)
            self.assertEqual(result.manifest_revision.status, "planned")
            self.assertFalse(result.manifest_revision.committed)
            self.assertTrue(result.manifest_revision.dry_run)
            self.assertFalse((delivery_root / "delivery-manifest-revision.json").exists())

    def test_dry_run_backend_manifest_mutation_request_is_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = root / "workspace" / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-backend-manifest-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    commit_backend_manifest_mutation=True,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.backend_manifest_patch_written)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertIsNotNone(result.backend_manifest_mutation)
            self.assertEqual(result.backend_manifest_mutation.status, "planned")
            self.assertTrue(result.backend_manifest_mutation.backend_manifest_mutation_planned)
            self.assertFalse(result.backend_manifest_mutation.backend_manifest_patch_written)
            self.assertFalse(result.backend_manifest_mutation.backend_manifest_mutated)
            self.assertFalse((delivery_root / "backend-artifact-manifest-mutation.json").exists())
            self.assertFalse((delivery_root / "backend-artifact-manifest.patched.json").exists())
            self.assertFalse(delivery_root.exists())

    def test_apply_writes_backend_manifest_mutation_and_patched_copy_without_in_place_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {
                "schema_version": "reverse-deepagent.backend-artifact-manifest.v1",
                "entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}],
            }
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-backend-manifest",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_manifest_revision=True,
                    commit_backend_manifest_mutation=True,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            mutation_path = delivery_root / "backend-artifact-manifest-mutation.json"
            patched_path = delivery_root / "backend-artifact-manifest.patched.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "delivered")
            self.assertTrue(result.backend_manifest_patch_written)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertIsNotNone(result.backend_manifest_mutation)
            self.assertEqual(result.backend_manifest_mutation.status, "patch_written")
            self.assertTrue(result.backend_manifest_mutation.backend_manifest_patch_written)
            self.assertFalse(result.backend_manifest_mutation.backend_manifest_mutated)
            self.assertTrue(mutation_path.exists())
            self.assertTrue(patched_path.exists())
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)

            mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
            patched = json.loads(patched_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            added_keys = {entry["artifact_key"] for entry in mutation["added_entries"]}
            patched_keys = {entry["artifact_key"] for entry in patched["entries"]}
            self.assertIn("workspace_final", added_keys)
            self.assertIn("workspace_delivery_receipt", added_keys)
            self.assertIn("workspace_delivery_transaction_journal", added_keys)
            self.assertIn("workspace_delivery_manifest_revision", added_keys)
            self.assertIn("workspace_backend_artifact_manifest_mutation", added_keys)
            self.assertIn("workspace_backend_artifact_manifest_patched", added_keys)
            self.assertIn("existing", patched_keys)
            self.assertTrue(added_keys.issubset(patched_keys))
            self.assertFalse(patched["mutation_policy"]["backend_manifest_mutated"])
            self.assertTrue(patched["mutation_policy"]["backend_manifest_patch_written"])
            self.assertEqual(journal["backend_manifest_mutation_path"], str(mutation_path.resolve()))
            self.assertEqual(journal["backend_manifest_patched_path"], str(patched_path.resolve()))
            self.assertTrue(journal["backend_manifest_patch_written"])
            self.assertFalse(journal["backend_manifest_mutated"])
            self.assertIn("writes_local_patched_manifest_copy_only", mutation["metadata"]["limitations"])

    def test_dry_run_backend_manifest_in_place_preflight_is_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = root / "workspace" / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-preflight-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.backend_manifest_in_place_preflight_passed)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertIsNotNone(result.backend_manifest_in_place_preflight)
            self.assertEqual(result.backend_manifest_in_place_preflight.status, "planned")
            self.assertTrue(result.backend_manifest_in_place_preflight.dry_run)
            self.assertFalse(result.backend_manifest_in_place_preflight.in_place_mutation_allowed)
            self.assertFalse((delivery_root / "backend-artifact-manifest-preflight.json").exists())
            self.assertFalse(delivery_root.exists())

    def test_apply_writes_backend_manifest_in_place_preflight_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {"entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}]}
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            expected_digest = _sha256_file(backend_manifest)
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=expected_digest,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            preflight_path = delivery_root / "backend-artifact-manifest-preflight.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertTrue(result.backend_manifest_patch_written)
            self.assertTrue(result.backend_manifest_in_place_preflight_passed)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertIsNotNone(result.backend_manifest_in_place_preflight)
            self.assertEqual(result.backend_manifest_in_place_preflight.status, "passed")
            self.assertTrue(result.backend_manifest_in_place_preflight.in_place_mutation_allowed)
            self.assertTrue(preflight_path.exists())
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)

            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(preflight["status"], "passed")
            self.assertTrue(preflight["in_place_mutation_allowed"])
            self.assertFalse(preflight["backend_manifest_mutated"])
            self.assertEqual(preflight["source_manifest_digest_sha256"], expected_digest)
            self.assertEqual(preflight["expected_source_manifest_digest_sha256"], expected_digest)
            self.assertFalse(preflight["blocking_reasons"])
            self.assertTrue(all(check["passed"] for check in preflight["checks"]))
            self.assertEqual(journal["backend_manifest_preflight_path"], str(preflight_path.resolve()))
            self.assertTrue(journal["backend_manifest_in_place_preflight_passed"])
            self.assertFalse(journal["backend_manifest_mutated"])

    def test_backend_manifest_in_place_preflight_blocks_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-preflight-blocked",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256="0" * 64,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertFalse(result.backend_manifest_in_place_preflight_passed)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertIsNotNone(result.backend_manifest_in_place_preflight)
            self.assertEqual(result.backend_manifest_in_place_preflight.status, "blocked")
            self.assertIn("expected_source_manifest_digest_matches", result.backend_manifest_in_place_preflight.blocking_reasons)
            preflight = json.loads((delivery_root / "backend-artifact-manifest-preflight.json").read_text(encoding="utf-8"))
            self.assertEqual(preflight["status"], "blocked")
            self.assertFalse(preflight["in_place_mutation_allowed"])
            self.assertIn("expected_source_manifest_digest_matches", preflight["blocking_reasons"])

    def test_backend_manifest_in_place_mutation_requires_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {"entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}]}
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-no-in-place-approval",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            self.assertTrue(result.backend_manifest_in_place_preflight_passed)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertFalse(result.backend_manifest_rollback_written)
            self.assertIsNone(result.backend_manifest_in_place_mutation)
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            self.assertFalse((delivery_root / "backend-artifact-manifest-in-place-mutation.json").exists())
            self.assertFalse((delivery_root / "backend-artifact-manifest.rollback.json").exists())

    def test_backend_manifest_in_place_mutation_blocks_digest_mismatch_even_with_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {"entries": []}
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-in-place-blocked",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256="0" * 64,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            self.assertFalse(result.backend_manifest_in_place_preflight_passed)
            self.assertFalse(result.backend_manifest_mutated)
            self.assertFalse(result.backend_manifest_rollback_written)
            self.assertIsNotNone(result.backend_manifest_in_place_mutation)
            self.assertEqual(result.backend_manifest_in_place_mutation.status, "blocked")
            self.assertIn("expected_source_manifest_digest_matches_current", result.backend_manifest_in_place_mutation.blocking_reasons)
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            self.assertTrue((delivery_root / "backend-artifact-manifest-in-place-mutation.json").exists())
            self.assertFalse((delivery_root / "backend-artifact-manifest.rollback.json").exists())

    def test_backend_manifest_in_place_mutation_applies_after_preflight_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {
                "schema_version": "reverse-deepagent.backend-artifact-manifest.v1",
                "entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}],
            }
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            expected_digest = _sha256_file(backend_manifest)
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-in-place-approved",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_manifest_revision=True,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=expected_digest,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            in_place_path = delivery_root / "backend-artifact-manifest-in-place-mutation.json"
            rollback_path = delivery_root / "backend-artifact-manifest.rollback.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "delivered")
            self.assertTrue(result.backend_manifest_patch_written)
            self.assertTrue(result.backend_manifest_in_place_preflight_passed)
            self.assertTrue(result.backend_manifest_mutated)
            self.assertTrue(result.backend_manifest_rollback_written)
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.backend_manifest_in_place_mutation)
            self.assertEqual(result.backend_manifest_in_place_mutation.status, "applied")
            self.assertTrue(result.backend_manifest_in_place_mutation.backend_manifest_mutated)
            self.assertTrue(in_place_path.exists())
            self.assertTrue(rollback_path.exists())

            rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
            mutated = json.loads(backend_manifest.read_text(encoding="utf-8"))
            mutation_record = json.loads(in_place_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            mutated_keys = {entry["artifact_key"] for entry in mutated["entries"]}
            self.assertEqual(rollback, original_manifest)
            self.assertIn("existing", mutated_keys)
            self.assertIn("workspace_final", mutated_keys)
            self.assertIn("workspace_backend_artifact_manifest_in_place_mutation", mutated_keys)
            self.assertIn("workspace_backend_artifact_manifest_rollback", mutated_keys)
            self.assertTrue(mutated["mutation_policy"]["backend_manifest_mutated"])
            self.assertTrue(mutated["mutation_policy"]["backend_manifest_in_place_mutation_approved"])
            self.assertFalse(mutated["mutation_policy"]["external_delivery_performed"])
            self.assertFalse(mutated["mutation_policy"]["cross_run_transaction_committed"])
            self.assertEqual(mutation_record["status"], "applied")
            self.assertTrue(mutation_record["rollback_checkpoint_written"])
            self.assertTrue(mutation_record["backend_manifest_mutated"])
            self.assertEqual(journal["backend_manifest_in_place_mutation_path"], str(in_place_path.resolve()))
            self.assertEqual(journal["backend_manifest_rollback_path"], str(rollback_path.resolve()))
            self.assertTrue(journal["backend_manifest_rollback_written"])
            self.assertTrue(journal["backend_manifest_mutated"])
            self.assertFalse(journal["external_delivery_performed"])

    def test_backend_manifest_recovery_preflight_is_ready_after_approved_in_place_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recoverable",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            previous_journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recoverable",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            preflight_path = delivery_root / "backend-artifact-manifest-recovery-preflight.json"
            self.assertEqual(result.status, "preflighted")
            self.assertTrue(result.backend_manifest_recovery_preflight_passed)
            self.assertIsNotNone(result.backend_manifest_recovery_preflight)
            self.assertEqual(result.backend_manifest_recovery_preflight.status, "ready_for_review")
            self.assertTrue(result.backend_manifest_recovery_preflight.recovery_available)
            self.assertTrue(preflight_path.exists())
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            self.assertEqual(preflight["status"], "ready_for_review")
            self.assertTrue(preflight["recovery_available"])
            self.assertTrue(preflight["backend_manifest_mutated"])
            self.assertTrue(preflight["backend_manifest_rollback_written"])
            self.assertFalse(preflight["external_delivery_performed"])
            self.assertFalse(preflight["cross_run_transaction_committed"])
            self.assertFalse(preflight["blocking_reasons"])
            self.assertIn("review_rollback_checkpoint_before_physical_recovery", preflight["recommended_actions"])
            self.assertEqual(json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8")), previous_journal)

    def test_backend_manifest_recovery_preflight_blocks_source_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-drift-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            mutated = json.loads(backend_manifest.read_text(encoding="utf-8"))
            mutated["entries"].append({"artifact_key": "manual_drift", "path": "workspace/manual.json", "kind": "json"})
            backend_manifest.write_text(json.dumps(mutated, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-drift",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-drift-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            self.assertFalse(result.backend_manifest_recovery_preflight_passed)
            self.assertIsNotNone(result.backend_manifest_recovery_preflight)
            self.assertEqual(result.backend_manifest_recovery_preflight.status, "blocked")
            self.assertIn("source_matches_post_mutation_digest_if_mutated", result.backend_manifest_recovery_preflight.blocking_reasons)
            preflight = json.loads((delivery_root / "backend-artifact-manifest-recovery-preflight.json").read_text(encoding="utf-8"))
            self.assertIn("source_matches_post_mutation_digest_if_mutated", preflight["blocking_reasons"])

    def test_backend_manifest_recovery_preflight_reports_no_recovery_required_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-no-recovery-needed",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-none",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-no-recovery-needed",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            self.assertTrue(result.backend_manifest_recovery_preflight_passed)
            self.assertIsNotNone(result.backend_manifest_recovery_preflight)
            self.assertEqual(result.backend_manifest_recovery_preflight.status, "no_recovery_required")
            self.assertFalse(result.backend_manifest_recovery_preflight.recovery_available)
            self.assertEqual(result.next_action, "review_backend_manifest_recovery_preflight")

    def test_backend_manifest_transaction_commit_updates_journal_after_recovery_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-recovery-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-commit-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-cross-run-commit",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-commit-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            commit_path = delivery_root / "backend-artifact-manifest-transaction-commit.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "committed")
            self.assertTrue(result.cross_run_transaction_committed)
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.backend_manifest_transaction_commit)
            self.assertEqual(result.backend_manifest_transaction_commit.status, "committed")
            self.assertTrue(result.backend_manifest_transaction_commit.committed)
            self.assertTrue(commit_path.exists())
            commit = json.loads(commit_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(commit["source_transaction_id"], "tx-commit-source")
            self.assertTrue(commit["cross_run_transaction_committed"])
            self.assertTrue(commit["backend_manifest_recovery_preflight_passed"])
            self.assertFalse(commit["blocking_reasons"])
            self.assertEqual(journal["transaction_id"], "tx-commit-source")
            self.assertTrue(journal["cross_run_transaction_committed"])
            self.assertEqual(
                journal["backend_manifest_recovery_preflight_path"],
                str((delivery_root / "backend-artifact-manifest-recovery-preflight.json").resolve()),
            )
            self.assertEqual(journal["backend_manifest_transaction_commit_path"], str(commit_path.resolve()))
            self.assertEqual(journal["backend_manifest_in_place_mutation_path"], str((delivery_root / "backend-artifact-manifest-in-place-mutation.json").resolve()))
            self.assertTrue(journal["backend_manifest_mutated"])
            self.assertFalse(journal["external_delivery_performed"])

    def test_duplicate_cross_run_transaction_commit_preserves_terminal_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-idempotent-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-idempotent-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-commit-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-idempotent-first",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-commit-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            commit_path = delivery_root / "backend-artifact-manifest-transaction-commit.json"
            original_commit = json.loads(commit_path.read_text(encoding="utf-8"))
            duplicate = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-idempotent-second",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-commit-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            guard_path = delivery_root / "delivery-transaction-idempotency-guard.json"
            preserved_commit = json.loads(commit_path.read_text(encoding="utf-8"))
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
            self.assertEqual(duplicate.status, "blocked")
            self.assertIsNotNone(duplicate.transaction_idempotency_guard)
            self.assertEqual(duplicate.transaction_idempotency_guard.operation, "commit_cross_run_transaction")
            self.assertTrue(duplicate.transaction_state.flags["transaction_idempotency_guard_triggered"])
            self.assertEqual(duplicate.transaction_state.evidence_paths["transaction_idempotency_guard"], str(guard_path.resolve()))
            self.assertEqual(original_commit, preserved_commit)
            self.assertEqual(guard["status"], "duplicate_blocked")
            self.assertTrue(guard["duplicate_guard_triggered"])
            self.assertTrue(guard["terminal_artifact_preserved"])
            self.assertEqual(guard["terminal_artifact_path"], str(commit_path.resolve()))

    def test_backend_manifest_transaction_commit_blocks_stale_recovery_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-drift-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-drift-recovery-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-commit-drift-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])
            mutated = json.loads(backend_manifest.read_text(encoding="utf-8"))
            mutated["entries"].append({"artifact_key": "late_drift", "path": "workspace/late.json", "kind": "json"})
            backend_manifest.write_text(json.dumps(mutated, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-cross-run-commit-blocked",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-commit-drift-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            commit_path = delivery_root / "backend-artifact-manifest-transaction-commit.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "blocked")
            self.assertFalse(result.cross_run_transaction_committed)
            self.assertIsNotNone(result.backend_manifest_transaction_commit)
            self.assertEqual(result.backend_manifest_transaction_commit.status, "blocked")
            self.assertIn(
                "recovery_preflight_source_digest_matches_current",
                result.backend_manifest_transaction_commit.blocking_reasons,
            )
            self.assertTrue(commit_path.exists())
            self.assertFalse(journal.get("cross_run_transaction_committed", False))
            self.assertIsNone(journal.get("backend_manifest_transaction_commit_path"))

    def test_backend_manifest_recovery_restores_rollback_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {"entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}]}
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-restore-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            self.assertNotEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-restore-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-restore-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-restore-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    apply_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-restore-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            recovery_path = delivery_root / "backend-artifact-manifest-recovery.json"
            journal_path = delivery_root / "delivery-transaction-journal.json"
            self.assertEqual(result.status, "recovered")
            self.assertTrue(result.backend_manifest_recovered)
            self.assertIsNotNone(result.backend_manifest_recovery)
            self.assertEqual(result.backend_manifest_recovery.status, "recovered")
            self.assertTrue(result.backend_manifest_recovery.recovered)
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            self.assertTrue(recovery_path.exists())
            recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(recovery["source_transaction_id"], "tx-recovery-restore-source")
            self.assertEqual(recovery["post_recovery_manifest_digest_sha256"], recovery["rollback_manifest_digest_sha256"])
            self.assertTrue(journal["backend_manifest_recovered"])
            self.assertEqual(journal["backend_manifest_recovery_path"], str(recovery_path.resolve()))
            self.assertEqual(journal["transaction_id"], "tx-recovery-restore-source")
            self.assertTrue(journal["backend_manifest_mutated"])
            self.assertFalse(journal["cross_run_transaction_committed"])
            self.assertFalse(journal["external_delivery_performed"])

    def test_duplicate_backend_manifest_recovery_preserves_terminal_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            original_manifest = {"entries": [{"artifact_key": "existing", "path": "workspace/existing.json", "kind": "json"}]}
            backend_manifest.write_text(json.dumps(original_manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-idempotent-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-idempotent-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-idempotent-first",
                    mode=DeliveryExecutionMode.APPLY,
                    apply_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            recovery_path = delivery_root / "backend-artifact-manifest-recovery.json"
            original_recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            duplicate = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-idempotent-second",
                    mode=DeliveryExecutionMode.APPLY,
                    apply_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-idempotent-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            guard_path = delivery_root / "delivery-transaction-idempotency-guard.json"
            preserved_recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
            guard = json.loads(guard_path.read_text(encoding="utf-8"))
            self.assertEqual(duplicate.status, "blocked")
            self.assertIsNotNone(duplicate.transaction_idempotency_guard)
            self.assertEqual(duplicate.transaction_idempotency_guard.operation, "apply_backend_manifest_recovery")
            self.assertTrue(duplicate.transaction_state.flags["transaction_idempotency_guard_triggered"])
            self.assertEqual(duplicate.transaction_state.evidence_paths["transaction_idempotency_guard"], str(guard_path.resolve()))
            self.assertEqual(original_recovery, preserved_recovery)
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            self.assertEqual(guard["status"], "duplicate_blocked")
            self.assertTrue(guard["duplicate_guard_triggered"])
            self.assertTrue(guard["terminal_artifact_preserved"])
            self.assertEqual(guard["terminal_artifact_path"], str(recovery_path.resolve()))

    def test_backend_manifest_recovery_blocks_source_manifest_drift_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-drift-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final", destination_name="final-result.json")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-drift-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-drift-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])
            mutated = json.loads(backend_manifest.read_text(encoding="utf-8"))
            mutated["entries"].append({"artifact_key": "late_drift", "path": "workspace/late.json", "kind": "json"})
            backend_manifest.write_text(json.dumps(mutated, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-drift-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    apply_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-recovery-drift-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            recovery_path = delivery_root / "backend-artifact-manifest-recovery.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "blocked")
            self.assertFalse(result.backend_manifest_recovered)
            self.assertIsNotNone(result.backend_manifest_recovery)
            self.assertEqual(result.backend_manifest_recovery.status, "blocked")
            self.assertIn("source_matches_recovery_preflight_digest", result.backend_manifest_recovery.blocking_reasons)
            self.assertTrue(recovery_path.exists())
            self.assertFalse(journal.get("backend_manifest_recovered", False))
            self.assertIsNone(journal.get("backend_manifest_recovery_path"))


    def test_external_delivery_request_can_use_default_registry_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-alias",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider_id="manual-handoff",
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "external_delivery_blocked")
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.provider_id, "review-only")

    def test_missing_required_source_blocks_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-missing",
                    mode=DeliveryExecutionMode.APPLY,
                )
            ).execute([DeliveryArtifact(source_path=root / "missing.json", artifact_key="missing")])

            self.assertEqual(result.status, "failed")
            self.assertFalse(result.delivery_allowed)
            self.assertFalse(result.filesystem_artifact_mutated)
            self.assertEqual(result.next_action, "fix_delivery_artifact_inputs")
            self.assertTrue(result.errors)
            self.assertIn("missing_source", result.errors[0])

    def test_external_delivery_request_writes_review_only_blocker_without_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-review-only",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            external_result_path = delivery_root / "external-delivery-result.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            external_result = json.loads(external_result_path.read_text(encoding="utf-8"))
            self.assertEqual(result.status, "external_delivery_blocked")
            self.assertFalse(result.delivery_allowed)
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.status, "blocked")
            self.assertIn("external_delivery_provider_configured", result.external_delivery_result.blocking_reasons)
            self.assertTrue(external_result_path.exists())
            self.assertEqual(external_result["provider_id"], "review-only")
            self.assertFalse(journal["external_delivery_performed"])
            self.assertEqual(Path(journal["external_delivery_result_path"]).resolve(), external_result_path.resolve())

    def test_external_delivery_provider_contract_can_mark_external_delivery_performed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-fake",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=FakeExternalDeliveryProvider(),
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            external_result = json.loads((delivery_root / "external-delivery-result.json").read_text(encoding="utf-8"))
            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.delivery_allowed)
            self.assertTrue(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.provider_id, "fake-provider")
            self.assertTrue(journal["external_delivery_performed"])
            self.assertTrue(external_result["external_delivery_performed"])

    def test_external_delivery_writes_idempotency_ledger_for_performed_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-ledger",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=FakeExternalDeliveryProvider(),
                    external_delivery_idempotency_key="ledger-key-1",
                    external_delivery_provider_config={"api_token": "ledger-secret"},
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            ledger_path = delivery_root / "external-delivery-idempotency-ledger.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(result.status, "external_delivered")
            self.assertIsNotNone(result.external_delivery_idempotency_ledger)
            self.assertTrue(ledger_path.exists())
            self.assertEqual(Path(journal["external_delivery_idempotency_ledger_path"]).resolve(), ledger_path.resolve())
            self.assertEqual(ledger["transaction_id"], "tx-external-ledger")
            self.assertEqual(ledger["idempotency_key"], "ledger-key-1")
            self.assertEqual(ledger["provider_id"], "fake-provider")
            self.assertTrue(ledger["external_delivery_performed"])
            self.assertFalse(ledger["duplicate_guard_triggered"])
            self.assertEqual(ledger["entry_count"], 1)
            self.assertEqual(ledger["entries"][0]["status"], "delivered")
            self.assertEqual(ledger["entries"][0]["idempotency_key"], "ledger-key-1")
            self.assertFalse(ledger["entries"][0]["attempt_summary"]["headers_recorded"])
            self.assertFalse(ledger["metadata"]["provider_config_values_recorded"])
            serialized_ledger = json.dumps(ledger, ensure_ascii=False)
            self.assertNotIn("ledger-secret", serialized_ledger)

    def test_external_delivery_provider_config_is_summarized_without_exporting_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            provider = CountingExternalDeliveryProvider()

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-provider-config-summary",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=provider,
                    external_delivery_provider_config={
                        "webhook_url": "https://example.invalid/hook",
                        "api_token": "super-secret-token",
                    },
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "external_delivered")
            self.assertEqual(provider.calls, 1)
            summary = provider.packages[0].metadata["external_delivery_provider_config_summary"]
            self.assertEqual(summary["key_count"], 2)
            self.assertEqual(summary["non_secret_keys"], ["webhook_url"])
            self.assertEqual(summary["secret_like_key_count"], 1)
            self.assertFalse(summary["raw_values_exported"])
            serialized_package = json.dumps(provider.packages[0].to_dict(), ensure_ascii=False)
            self.assertNotIn("super-secret-token", serialized_package)
            self.assertNotIn("https://example.invalid/hook", serialized_package)

    def test_local_archive_external_delivery_dry_run_is_side_effect_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            archive_root = root / "archive"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-local-archive-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    request_external_delivery=True,
                    external_delivery_provider_id="local-archive",
                    external_delivery_provider_config={"archive_root": str(archive_root)},
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.status, "planned")
            self.assertEqual(result.external_delivery_result.provider_id, "local-archive")
            self.assertFalse(delivery_root.exists())
            self.assertFalse(archive_root.exists())
            self.assertFalse(result.external_delivery_result.metadata["archived_artifacts"])

    def test_local_archive_external_delivery_apply_copies_delivered_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            archive_root = root / "archive"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-local-archive-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider_id="filesystem-release",
                    external_delivery_provider_config={"archive_root": str(archive_root)},
                )
            ).execute(
                [
                    DeliveryArtifact(
                        source_path=source,
                        artifact_key="workspace_final",
                        destination_name="final-result.json",
                    )
                ]
            )

            release_dir = archive_root / "tx-local-archive-apply"
            archived = release_dir / "final-result.json"
            manifest_path = release_dir / "local-archive-manifest.json"
            checksums_path = release_dir / "local-archive-checksums.json"
            external_result_path = delivery_root / "external-delivery-result.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            external_result = json.loads(external_result_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checksums = json.loads(checksums_path.read_text(encoding="utf-8"))

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertTrue(result.delivery_allowed)
            self.assertTrue(archived.exists())
            self.assertEqual(archived.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertEqual(manifest["provider_id"], "local-archive")
            self.assertEqual(manifest["archive_release_dir"], str(release_dir.resolve()))
            self.assertEqual(checksums["artifacts"][0]["digest_sha256"], _sha256_file(archived))
            self.assertEqual(external_result["metadata"]["archive_manifest_path"], str(manifest_path.resolve()))
            self.assertTrue(external_result["external_delivery_performed"])
            self.assertTrue(journal["external_delivery_performed"])
            self.assertEqual(Path(journal["external_delivery_result_path"]).resolve(), external_result_path.resolve())

    def test_webhook_external_delivery_dry_run_redacts_target_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            webhook_url = "https://user:pass@example.invalid/hook?delivery_token=secret-value"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-webhook-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    request_external_delivery=True,
                    external_delivery_provider_id="webhook",
                    external_delivery_provider_config={
                        "webhook_url": webhook_url,
                        "headers": {"Authorization": "Token hidden-value"},
                    },
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            metadata = result.external_delivery_result.metadata
            self.assertEqual(metadata["target_url"], "https://example.invalid/hook")
            self.assertTrue(metadata["target_query_redacted"])
            self.assertTrue(metadata["target_credentials_redacted"])
            self.assertFalse(metadata["request_attempted"])
            self.assertEqual(metadata["external_delivery_provider_config_summary"]["secret_like_key_count"], 1)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("secret-value", serialized_result)
            self.assertNotIn("hidden-value", serialized_result)
            self.assertNotIn("user:pass", serialized_result)
            self.assertFalse((root / "delivery").exists())

    def test_webhook_external_delivery_apply_posts_json_without_recording_response_body_or_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingWebhookHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingWebhookHandler)
            server.timeout = 5
            thread = threading.Thread(target=server.handle_request)
            thread.daemon = True
            thread.start()
            try:
                webhook_url = f"http://127.0.0.1:{server.server_port}/deliver?query_secret=redacted"
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-webhook-apply",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="http-webhook",
                        external_delivery_provider_config={
                            "webhook_url": webhook_url,
                            "headers": {"Authorization": "Token local-test-secret"},
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingWebhookHandler.requests), 1)
            request = RecordingWebhookHandler.requests[0]
            self.assertEqual(request["path"], "/deliver?query_secret=redacted")
            self.assertEqual(request["headers"]["Authorization"], "Token local-test-secret")
            body = json.loads(bytes(request["body"]).decode("utf-8"))
            self.assertEqual(body["provider_id"], "webhook")
            self.assertEqual(body["transaction_id"], "tx-webhook-apply")
            self.assertEqual(body["package"]["metadata"]["provider_id"], "webhook")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertEqual(metadata["target_url"], f"http://127.0.0.1:{server.server_port}/deliver")
            self.assertTrue(metadata["target_query_redacted"])
            self.assertTrue(metadata["request_attempted"])
            self.assertTrue(metadata["request_succeeded"])
            self.assertEqual(metadata["response_status_code"], 204)
            self.assertFalse(metadata["response_body_recorded"])
            self.assertFalse(metadata["response_headers_recorded"])
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("local-test-secret", serialized_result)
            self.assertNotIn("query_secret=redacted", serialized_result)
            self.assertTrue((delivery_root / "external-delivery-result.json").exists())

    def test_webhook_external_delivery_can_retry_retryable_status_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RetryingWebhookHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RetryingWebhookHandler)
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                webhook_url = f"http://127.0.0.1:{server.server_port}/deliver?query_secret=redacted"
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-webhook-retry",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="webhook",
                        external_delivery_provider_config={
                            "webhook_url": webhook_url,
                            "headers": {"Authorization": "Token retry-secret"},
                            "timeout_seconds": 5,
                            "retry_attempts": 1,
                            "retry_backoff_seconds": 0,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RetryingWebhookHandler.requests), 2)
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["retry_enabled"])
            self.assertEqual(metadata["retry_attempts_configured"], 1)
            self.assertEqual(metadata["request_attempt_count"], 2)
            self.assertEqual(metadata["request_retry_count"], 1)
            self.assertEqual(metadata["response_status_code"], 204)
            self.assertEqual(metadata["request_attempts"][0]["status_code"], 503)
            self.assertTrue(metadata["request_attempts"][0]["will_retry"])
            self.assertEqual(metadata["request_attempts"][0]["retry_after_seconds"], 2)
            self.assertTrue(metadata["request_attempts"][0]["retry_after_seen"])
            self.assertFalse(metadata["request_attempts"][0]["retry_after_honored"])
            self.assertEqual(metadata["request_attempts"][0]["planned_retry_delay_seconds"], 0.0)
            self.assertEqual(metadata["request_attempts"][0]["rate_limit"]["remaining"], 0)
            self.assertEqual(metadata["request_attempts"][0]["rate_limit"]["resource"], "webhook")
            self.assertEqual(metadata["request_attempts"][1]["status_code"], 204)
            self.assertFalse(metadata["request_attempts"][1]["will_retry"])
            self.assertTrue(metadata["request_retry_summary"]["retry_after_seen"])
            self.assertFalse(metadata["request_retry_summary"]["retry_after_honored"])
            self.assertTrue(metadata["request_retry_summary"]["rate_limit_seen"])
            self.assertFalse(metadata["request_retry_summary"]["headers_recorded"])
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("retry-secret", serialized_result)
            self.assertNotIn("query_secret=redacted", serialized_result)
            ledger = json.loads((delivery_root / "external-delivery-idempotency-ledger.json").read_text(encoding="utf-8"))
            attempt_summary = ledger["entries"][0]["attempt_summary"]
            self.assertEqual(attempt_summary["attempt_count"], 2)
            self.assertEqual(attempt_summary["retry_count"], 1)
            self.assertEqual(attempt_summary["stages"][0]["stage"], "request")
            self.assertTrue(attempt_summary["retry_after_seen"])
            self.assertTrue(attempt_summary["rate_limit_seen"])
            self.assertFalse(attempt_summary["headers_recorded"])
            self.assertEqual(attempt_summary["stages"][0]["attempts"][0]["status_code"], 503)
            self.assertEqual(attempt_summary["stages"][0]["attempts"][0]["retry_after_seconds"], 2)
            self.assertEqual(attempt_summary["stages"][0]["attempts"][0]["rate_limit"]["limit"], 60)
            self.assertEqual(attempt_summary["stages"][0]["attempts"][1]["status_code"], 204)
            serialized_ledger = json.dumps(ledger, ensure_ascii=False)
            self.assertNotIn("retry-secret", serialized_ledger)
            self.assertNotIn("query_secret=redacted", serialized_ledger)

    def test_presigned_object_external_delivery_dry_run_redacts_target_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            presigned_url = "https://user:pass@example.invalid/releases/final.json?X-Amz-Signature=secret-value"

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-presigned-object-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    request_external_delivery=True,
                    external_delivery_provider_id="object-storage",
                    external_delivery_provider_config={
                        "presigned_url": presigned_url,
                        "object_name": "final.json",
                        "headers": {"x-amz-meta-secret": "hidden-value"},
                    },
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.provider_id, "presigned-object")
            metadata = result.external_delivery_result.metadata
            self.assertEqual(metadata["target_url"], "https://example.invalid/releases/final.json")
            self.assertEqual(metadata["object_name"], "final.json")
            self.assertTrue(metadata["target_query_redacted"])
            self.assertTrue(metadata["target_credentials_redacted"])
            self.assertFalse(metadata["request_attempted"])
            self.assertEqual(metadata["external_delivery_provider_config_summary"]["secret_like_key_count"], 1)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("secret-value", serialized_result)
            self.assertNotIn("hidden-value", serialized_result)
            self.assertNotIn("user:pass", serialized_result)
            self.assertFalse((root / "delivery").exists())

    def test_presigned_object_external_delivery_apply_puts_json_without_recording_response_body_or_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingObjectHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingObjectHandler)
            server.timeout = 5
            thread = threading.Thread(target=server.handle_request)
            thread.daemon = True
            thread.start()
            try:
                presigned_url = f"http://127.0.0.1:{server.server_port}/bucket/final.json?upload_secret=redacted"
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-presigned-object-apply",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="s3-presigned",
                        external_delivery_provider_config={
                            "presigned_url": presigned_url,
                            "object_name": "final.json",
                            "content_type": "application/vnd.reverse-agent.delivery+json",
                            "headers": {"x-amz-meta-review": "approved-local-test-secret"},
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingObjectHandler.requests), 1)
            request = RecordingObjectHandler.requests[0]
            self.assertEqual(request["path"], "/bucket/final.json?upload_secret=redacted")
            request_headers = {str(key).lower(): value for key, value in dict(request["headers"]).items()}
            self.assertEqual(request_headers["x-amz-meta-review"], "approved-local-test-secret")
            self.assertEqual(request_headers["content-type"], "application/vnd.reverse-agent.delivery+json")
            body = json.loads(bytes(request["body"]).decode("utf-8"))
            self.assertEqual(body["provider_id"], "presigned-object")
            self.assertEqual(body["transaction_id"], "tx-presigned-object-apply")
            self.assertEqual(body["object_name"], "final.json")
            self.assertEqual(body["package"]["metadata"]["provider_id"], "presigned-object")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertEqual(metadata["target_url"], f"http://127.0.0.1:{server.server_port}/bucket/final.json")
            self.assertEqual(metadata["request_method"], "PUT")
            self.assertTrue(metadata["target_query_redacted"])
            self.assertTrue(metadata["request_attempted"])
            self.assertTrue(metadata["request_succeeded"])
            self.assertEqual(metadata["response_status_code"], 200)
            self.assertFalse(metadata["response_body_recorded"])
            self.assertFalse(metadata["response_headers_recorded"])
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("approved-local-test-secret", serialized_result)
            self.assertNotIn("upload_secret=redacted", serialized_result)
            self.assertTrue((delivery_root / "external-delivery-result.json").exists())

    def test_github_release_external_delivery_dry_run_redacts_config_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-github-release-dry-run",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    request_external_delivery=True,
                    external_delivery_provider_id="gh-release",
                    external_delivery_provider_config={
                        "repository": "https://github.com/owner/repo.git",
                        "tag_name": "v0-test",
                        "asset_name": "reverse-delivery.json",
                        "token": "ghp_secret_token",
                        "api_base_url": "https://user:pass@api.github.invalid?api_token=secret",
                    },
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(result.status, "planned")
            self.assertFalse(result.external_delivery_performed)
            self.assertIsNotNone(result.external_delivery_result)
            self.assertEqual(result.external_delivery_result.provider_id, "github-release")
            metadata = result.external_delivery_result.metadata
            self.assertEqual(metadata["repository"], "owner/repo")
            self.assertEqual(metadata["tag_name"], "v0-test")
            self.assertEqual(metadata["asset_name"], "reverse-delivery.json")
            self.assertEqual(metadata["release_api_url"], "https://api.github.invalid")
            self.assertTrue(metadata["api_query_redacted"])
            self.assertTrue(metadata["api_credentials_redacted"])
            self.assertFalse(metadata["release_request_attempted"])
            self.assertFalse(metadata["upload_request_attempted"])
            self.assertFalse(metadata["response_body_recorded"])
            self.assertFalse(metadata["response_headers_recorded"])
            self.assertFalse(metadata["request_headers_recorded"])
            self.assertEqual(metadata["external_delivery_provider_config_summary"]["secret_like_key_count"], 1)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_secret_token", serialized_result)
            self.assertNotIn("api_token=secret", serialized_result)
            self.assertNotIn("user:pass", serialized_result)
            self.assertFalse((root / "delivery").exists())

    def test_github_release_external_delivery_apply_posts_release_and_asset_without_recording_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseHandler)
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-apply",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release-assets",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-test",
                            "release_name": "Reverse DeepAgent v0 test",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_local_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseHandler.requests), 3)
            release_request, assets_request, upload_request = RecordingGitHubReleaseHandler.requests
            self.assertEqual(release_request["method"], "POST")
            self.assertEqual(release_request["path"], "/repos/owner/repo/releases")
            self.assertEqual(assets_request["method"], "GET")
            self.assertEqual(
                assets_request["path"],
                "/repos/owner/repo/releases/1/assets?asset_query=hidden",
            )
            self.assertEqual(upload_request["method"], "POST")
            self.assertEqual(upload_request["path"], "/uploads/assets?name=reverse-delivery.json")
            release_headers = {str(key).lower(): value for key, value in dict(release_request["headers"]).items()}
            assets_headers = {str(key).lower(): value for key, value in dict(assets_request["headers"]).items()}
            upload_headers = {str(key).lower(): value for key, value in dict(upload_request["headers"]).items()}
            self.assertEqual(release_headers["authorization"], "Bearer ghp_local_secret")
            self.assertEqual(assets_headers["authorization"], "Bearer ghp_local_secret")
            self.assertEqual(upload_headers["authorization"], "Bearer ghp_local_secret")
            release_body = json.loads(bytes(release_request["body"]).decode("utf-8"))
            self.assertEqual(release_body["tag_name"], "v0-test")
            self.assertEqual(release_body["name"], "Reverse DeepAgent v0 test")
            upload_body = json.loads(bytes(upload_request["body"]).decode("utf-8"))
            self.assertEqual(upload_body["provider_id"], "github-release")
            self.assertEqual(upload_body["transaction_id"], "tx-github-release-apply")
            self.assertEqual(upload_body["repository"], "owner/repo")
            self.assertEqual(upload_body["asset_name"], "reverse-delivery.json")
            self.assertEqual(upload_body["package"]["metadata"]["provider_id"], "github-release")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertEqual(metadata["release_api_url"], f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases")
            self.assertEqual(metadata["assets_url"], f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/1/assets")
            self.assertEqual(metadata["upload_url"], f"http://127.0.0.1:{server.server_port}/uploads/assets")
            self.assertTrue(metadata["check_existing_asset"])
            self.assertFalse(metadata["allow_existing_asset"])
            self.assertTrue(metadata["release_request_attempted"])
            self.assertTrue(metadata["asset_lookup_attempted"])
            self.assertTrue(metadata["upload_request_attempted"])
            self.assertTrue(metadata["release_succeeded"])
            self.assertTrue(metadata["asset_lookup_succeeded"])
            self.assertFalse(metadata["existing_asset_found"])
            self.assertEqual(metadata["existing_asset_count"], 0)
            self.assertTrue(metadata["upload_succeeded"])
            self.assertEqual(metadata["release_status_code"], 201)
            self.assertEqual(metadata["asset_lookup_status_code"], 200)
            self.assertEqual(metadata["upload_status_code"], 201)
            self.assertFalse(metadata["response_body_recorded"])
            self.assertFalse(metadata["response_headers_recorded"])
            self.assertFalse(metadata["request_headers_recorded"])
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_local_secret", serialized_result)
            self.assertNotIn("Authorization", serialized_result)
            self.assertNotIn("asset_query=hidden", serialized_result)
            self.assertTrue((delivery_root / "external-delivery-result.json").exists())

    def test_github_release_external_delivery_records_retry_after_and_rate_limit_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RetryingGitHubReleaseHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RetryingGitHubReleaseHandler)
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request(), server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-retry-rate-limit",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-retry",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_retry_rate_limit_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "timeout_seconds": 5,
                            "retry_attempts": 1,
                            "retry_backoff_seconds": 0,
                            "retry_jitter_seconds": 0,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RetryingGitHubReleaseHandler.requests), 4)
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertEqual(metadata["release_request_attempt_count"], 2)
            self.assertEqual(metadata["release_request_retry_count"], 1)
            self.assertEqual(metadata["release_request_attempts"][0]["status_code"], 429)
            self.assertEqual(metadata["release_request_attempts"][0]["retry_after_seconds"], 3)
            self.assertTrue(metadata["release_request_attempts"][0]["retry_after_seen"])
            self.assertFalse(metadata["release_request_attempts"][0]["retry_after_honored"])
            self.assertEqual(metadata["release_request_attempts"][0]["planned_retry_delay_seconds"], 0.0)
            self.assertEqual(metadata["release_request_attempts"][0]["rate_limit"]["limit"], 5000)
            self.assertEqual(metadata["release_request_attempts"][0]["rate_limit"]["remaining"], 0)
            self.assertEqual(metadata["release_request_attempts"][0]["rate_limit"]["resource"], "core")
            self.assertEqual(metadata["release_request_attempts"][1]["status_code"], 201)
            self.assertTrue(metadata["release_request_retry_summary"]["retry_after_seen"])
            self.assertTrue(metadata["release_request_retry_summary"]["rate_limit_seen"])
            self.assertFalse(metadata["release_request_retry_summary"]["headers_recorded"])
            self.assertEqual(metadata["retry_jitter_seconds"], 0.0)
            self.assertTrue(metadata["honor_retry_after"])
            ledger = json.loads((delivery_root / "external-delivery-idempotency-ledger.json").read_text(encoding="utf-8"))
            attempt_summary = ledger["entries"][0]["attempt_summary"]
            self.assertTrue(attempt_summary["retry_after_seen"])
            self.assertTrue(attempt_summary["rate_limit_seen"])
            release_stage = next(stage for stage in attempt_summary["stages"] if stage["stage"] == "release_request")
            self.assertEqual(release_stage["attempts"][0]["retry_after_seconds"], 3)
            self.assertEqual(release_stage["attempts"][0]["rate_limit"]["used"], 5000)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            serialized_ledger = json.dumps(ledger, ensure_ascii=False)
            self.assertNotIn("ghp_retry_rate_limit_secret", serialized_result)
            self.assertNotIn("body-not-recorded", serialized_result)
            self.assertNotIn("ghp_retry_rate_limit_secret", serialized_ledger)
            self.assertNotIn("body-not-recorded", serialized_ledger)

    def test_github_release_external_delivery_apply_can_reuse_existing_release_when_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseReuseHandler.requests = []
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseReuseHandler)
            server.timeout = 5
            thread = threading.Thread(
                target=lambda: [server.handle_request(), server.handle_request(), server.handle_request(), server.handle_request()]
            )
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-reuse",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-existing",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_reuse_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "reuse_existing_release": True,
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseReuseHandler.requests), 4)
            create_request, lookup_request, assets_request, upload_request = RecordingGitHubReleaseReuseHandler.requests
            self.assertEqual(create_request["method"], "POST")
            self.assertEqual(create_request["path"], "/repos/owner/repo/releases")
            self.assertEqual(lookup_request["method"], "GET")
            self.assertEqual(lookup_request["path"], "/repos/owner/repo/releases/tags/v0-existing")
            self.assertEqual(assets_request["method"], "GET")
            self.assertEqual(
                assets_request["path"],
                "/repos/owner/repo/releases/2/assets?asset_query=hidden",
            )
            self.assertEqual(upload_request["method"], "POST")
            self.assertEqual(upload_request["path"], "/uploads/existing?name=reverse-delivery.json")
            for request in (create_request, lookup_request, assets_request, upload_request):
                headers = {str(key).lower(): value for key, value in dict(request["headers"]).items()}
                self.assertEqual(headers["authorization"], "Bearer ghp_reuse_secret")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["reuse_existing_release"])
            self.assertTrue(metadata["release_request_attempted"])
            self.assertEqual(metadata["release_status_code"], 422)
            self.assertFalse(metadata["release_created"])
            self.assertTrue(metadata["existing_release_lookup_attempted"])
            self.assertTrue(metadata["existing_release_lookup_succeeded"])
            self.assertTrue(metadata["existing_release_reused"])
            self.assertEqual(metadata["existing_release_status_code"], 200)
            self.assertEqual(
                metadata["existing_release_api_url"],
                f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/tags/v0-existing",
            )
            self.assertEqual(metadata["assets_url"], f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/2/assets")
            self.assertTrue(metadata["check_existing_asset"])
            self.assertFalse(metadata["allow_existing_asset"])
            self.assertTrue(metadata["asset_lookup_attempted"])
            self.assertTrue(metadata["asset_lookup_succeeded"])
            self.assertFalse(metadata["existing_asset_found"])
            self.assertEqual(metadata["existing_asset_count"], 0)
            self.assertEqual(metadata["asset_lookup_status_code"], 200)
            self.assertTrue(metadata["release_succeeded"])
            self.assertTrue(metadata["upload_succeeded"])
            self.assertEqual(metadata["upload_status_code"], 201)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_reuse_secret", serialized_result)
            self.assertNotIn("body-not-recorded", serialized_result)
            self.assertNotIn("upload-response-not-recorded", serialized_result)
            self.assertNotIn("asset_query=hidden", serialized_result)
            self.assertTrue((delivery_root / "external-delivery-result.json").exists())

    def test_github_release_external_delivery_blocks_existing_asset_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseAssetPreflightHandler.requests = []
            RecordingGitHubReleaseAssetPreflightHandler.existing_assets = [
                {
                    "id": 7,
                    "name": "reverse-delivery.json",
                    "url": f"http://127.0.0.1:1/repos/owner/repo/releases/assets/7?api_secret=hidden",
                    "browser_download_url": "https://example.invalid/body-not-recorded?download_secret=hidden",
                    "size": 123,
                    "content_type": "application/json",
                    "state": "uploaded",
                }
            ]
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseAssetPreflightHandler)
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-asset-conflict",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-duplicate",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_asset_conflict_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivery_blocked")
            self.assertFalse(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseAssetPreflightHandler.requests), 2)
            release_request, assets_request = RecordingGitHubReleaseAssetPreflightHandler.requests
            self.assertEqual(release_request["method"], "POST")
            self.assertEqual(assets_request["method"], "GET")
            self.assertFalse(any(request["method"] == "DELETE" for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            self.assertFalse(any(str(request["path"]).startswith("/uploads/duplicate") for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["check_existing_asset"])
            self.assertFalse(metadata["allow_existing_asset"])
            self.assertTrue(metadata["release_succeeded"])
            self.assertTrue(metadata["asset_lookup_attempted"])
            self.assertTrue(metadata["asset_lookup_succeeded"])
            self.assertTrue(metadata["existing_asset_found"])
            self.assertEqual(metadata["existing_asset_count"], 1)
            self.assertEqual(metadata["existing_asset"]["id"], 7)
            self.assertEqual(metadata["existing_asset"]["name"], "reverse-delivery.json")
            self.assertEqual(metadata["existing_asset"]["api_url"], "http://127.0.0.1:1/repos/owner/repo/releases/assets/7")
            self.assertTrue(metadata["existing_asset"]["browser_download_url_present"])
            self.assertFalse(metadata["existing_asset"]["browser_download_url_recorded"])
            overwrite_plan = metadata["existing_asset_overwrite_plan"]
            self.assertEqual(overwrite_plan["status"], "requires_review")
            self.assertTrue(overwrite_plan["delete_required"])
            self.assertTrue(overwrite_plan["overwrite_required"])
            self.assertFalse(overwrite_plan["delete_performed"])
            self.assertFalse(overwrite_plan["overwrite_performed"])
            self.assertTrue(overwrite_plan["requires_explicit_approval"])
            self.assertEqual(overwrite_plan["recommended_transition"], "approve_github_release_asset_delete_then_upload")
            self.assertFalse(overwrite_plan["side_effect_policy"]["sends_delete_request"])
            self.assertFalse(overwrite_plan["side_effect_policy"]["uploads_replacement_asset"])
            self.assertEqual(metadata["asset_lookup_status_code"], 200)
            self.assertFalse(metadata["upload_request_attempted"])
            self.assertFalse(metadata["upload_succeeded"])
            self.assertIn("github_release_asset_not_already_present", result.external_delivery_result.blocking_reasons)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_asset_conflict_secret", serialized_result)
            self.assertNotIn("asset_query=hidden", serialized_result)
            self.assertNotIn("api_secret=hidden", serialized_result)
            self.assertNotIn("download_secret=hidden", serialized_result)
            self.assertNotIn("body-not-recorded", serialized_result)

    def test_github_release_external_delivery_can_attempt_upload_when_existing_asset_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseAssetPreflightHandler.requests = []
            RecordingGitHubReleaseAssetPreflightHandler.existing_assets = [
                {
                    "id": 7,
                    "name": "reverse-delivery.json",
                    "url": "https://api.github.example.invalid/repos/owner/repo/releases/assets/7?api_secret=hidden",
                    "browser_download_url": "https://example.invalid/body-not-recorded?download_secret=hidden",
                }
            ]
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseAssetPreflightHandler)
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-asset-allowed",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-duplicate",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_asset_allowed_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "allow_existing_asset": True,
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseAssetPreflightHandler.requests), 3)
            release_request, assets_request, upload_request = RecordingGitHubReleaseAssetPreflightHandler.requests
            self.assertEqual(release_request["method"], "POST")
            self.assertEqual(assets_request["method"], "GET")
            self.assertEqual(upload_request["method"], "POST")
            self.assertFalse(any(request["method"] == "DELETE" for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            self.assertEqual(upload_request["path"], "/uploads/duplicate?name=reverse-delivery.json")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["check_existing_asset"])
            self.assertTrue(metadata["allow_existing_asset"])
            self.assertTrue(metadata["existing_asset_found"])
            self.assertEqual(metadata["existing_asset_count"], 1)
            self.assertEqual(metadata["existing_asset_overwrite_plan"]["status"], "requires_review")
            self.assertTrue(metadata["existing_asset_overwrite_plan"]["allow_existing_asset"])
            self.assertFalse(metadata["existing_asset_overwrite_plan"]["delete_performed"])
            self.assertFalse(metadata["existing_asset_overwrite_plan"]["overwrite_performed"])
            self.assertTrue(metadata["upload_request_attempted"])
            self.assertTrue(metadata["upload_succeeded"])
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_asset_allowed_secret", serialized_result)
            self.assertNotIn("asset_query=hidden", serialized_result)
            self.assertNotIn("api_secret=hidden", serialized_result)
            self.assertNotIn("download_secret=hidden", serialized_result)
            self.assertNotIn("body-not-recorded", serialized_result)

    def test_github_release_external_delivery_can_delete_existing_asset_then_upload_when_explicitly_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseAssetPreflightHandler.requests = []
            RecordingGitHubReleaseAssetPreflightHandler.delete_status_code = 204
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseAssetPreflightHandler)
            RecordingGitHubReleaseAssetPreflightHandler.existing_assets = [
                {
                    "id": 7,
                    "name": "reverse-delivery.json",
                    "url": f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/assets/7?api_secret=hidden",
                    "browser_download_url": "https://example.invalid/body-not-recorded?download_secret=hidden",
                }
            ]
            server.timeout = 5
            thread = threading.Thread(
                target=lambda: [server.handle_request(), server.handle_request(), server.handle_request(), server.handle_request()]
            )
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-asset-overwrite",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-duplicate",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_asset_overwrite_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "approve_existing_asset_delete": True,
                            "approve_replacement_upload": True,
                            "expected_existing_asset_id": 7,
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivered")
            self.assertTrue(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseAssetPreflightHandler.requests), 4)
            release_request, assets_request, delete_request, upload_request = RecordingGitHubReleaseAssetPreflightHandler.requests
            self.assertEqual(release_request["method"], "POST")
            self.assertEqual(assets_request["method"], "GET")
            self.assertEqual(delete_request["method"], "DELETE")
            self.assertEqual(delete_request["path"], "/repos/owner/repo/releases/assets/7?api_secret=hidden")
            self.assertEqual(upload_request["method"], "POST")
            self.assertEqual(upload_request["path"], "/uploads/duplicate?name=reverse-delivery.json")
            for request in RecordingGitHubReleaseAssetPreflightHandler.requests:
                headers = {str(key).lower(): value for key, value in dict(request["headers"]).items()}
                self.assertEqual(headers["authorization"], "Bearer ghp_asset_overwrite_secret")
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["approve_existing_asset_delete"])
            self.assertTrue(metadata["approve_replacement_upload"])
            self.assertTrue(metadata["expected_existing_asset_id_configured"])
            self.assertTrue(metadata["existing_asset_identity_matches"])
            self.assertTrue(metadata["existing_asset_delete_request_attempted"])
            self.assertTrue(metadata["existing_asset_delete_succeeded"])
            self.assertEqual(metadata["existing_asset_delete_status_code"], 204)
            self.assertTrue(metadata["existing_asset_delete_performed"])
            self.assertTrue(metadata["existing_asset_overwrite_performed"])
            self.assertTrue(metadata["upload_request_attempted"])
            self.assertTrue(metadata["upload_succeeded"])
            overwrite_plan = metadata["existing_asset_overwrite_plan"]
            self.assertTrue(overwrite_plan["delete_performed"])
            self.assertTrue(overwrite_plan["overwrite_performed"])
            self.assertFalse(overwrite_plan["requires_explicit_approval"])
            self.assertEqual(overwrite_plan["recommended_transition"], "review_github_release_asset_overwrite_result")
            self.assertTrue(overwrite_plan["side_effect_policy"]["sends_delete_request"])
            self.assertTrue(overwrite_plan["side_effect_policy"]["uploads_replacement_asset"])
            ledger = json.loads((delivery_root / "external-delivery-idempotency-ledger.json").read_text(encoding="utf-8"))
            stages = {stage["stage"]: stage for stage in ledger["entries"][0]["attempt_summary"]["stages"]}
            self.assertEqual(stages["existing_asset_delete"]["attempt_count"], 1)
            self.assertEqual(stages["existing_asset_delete"]["attempts"][0]["status_code"], 204)
            self.assertEqual(stages["upload_request"]["attempts"][0]["status_code"], 201)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_asset_overwrite_secret", serialized_result)
            self.assertNotIn("api_secret=hidden", serialized_result)
            self.assertNotIn("download_secret=hidden", serialized_result)
            self.assertNotIn("body-not-recorded", serialized_result)

    def test_github_release_external_delivery_blocks_overwrite_when_expected_asset_id_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseAssetPreflightHandler.requests = []
            RecordingGitHubReleaseAssetPreflightHandler.delete_status_code = 204
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseAssetPreflightHandler)
            RecordingGitHubReleaseAssetPreflightHandler.existing_assets = [
                {
                    "id": 7,
                    "name": "reverse-delivery.json",
                    "url": f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/assets/7?api_secret=hidden",
                }
            ]
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-asset-overwrite-id-mismatch",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-duplicate",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_asset_mismatch_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "approve_existing_asset_delete": True,
                            "approve_replacement_upload": True,
                            "expected_existing_asset_id": 999,
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivery_blocked")
            self.assertFalse(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseAssetPreflightHandler.requests), 2)
            self.assertFalse(any(request["method"] == "DELETE" for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            self.assertFalse(any(request["method"] == "POST" and str(request["path"]).startswith("/uploads/") for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertFalse(metadata["existing_asset_identity_matches"])
            self.assertFalse(metadata["existing_asset_delete_request_attempted"])
            self.assertFalse(metadata["existing_asset_delete_succeeded"])
            self.assertFalse(metadata["existing_asset_overwrite_performed"])
            self.assertIn("github_release_existing_asset_delete_approved", result.external_delivery_result.blocking_reasons)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_asset_mismatch_secret", serialized_result)
            self.assertNotIn("api_secret=hidden", serialized_result)

    def test_github_release_external_delivery_does_not_upload_replacement_when_delete_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            RecordingGitHubReleaseAssetPreflightHandler.requests = []
            RecordingGitHubReleaseAssetPreflightHandler.delete_status_code = 500
            server = http.server.HTTPServer(("127.0.0.1", 0), RecordingGitHubReleaseAssetPreflightHandler)
            RecordingGitHubReleaseAssetPreflightHandler.existing_assets = [
                {
                    "id": 7,
                    "name": "reverse-delivery.json",
                    "url": f"http://127.0.0.1:{server.server_port}/repos/owner/repo/releases/assets/7?api_secret=hidden",
                }
            ]
            server.timeout = 5
            thread = threading.Thread(target=lambda: [server.handle_request(), server.handle_request(), server.handle_request()])
            thread.daemon = True
            thread.start()
            try:
                result = LocalDeliveryExecutor(
                    DeliveryExecutorConfig(
                        delivery_root=delivery_root,
                        transaction_id="tx-github-release-asset-delete-fails",
                        mode=DeliveryExecutionMode.APPLY,
                        request_external_delivery=True,
                        external_delivery_provider_id="github-release",
                        external_delivery_provider_config={
                            "repository": "owner/repo",
                            "tag_name": "v0-duplicate",
                            "asset_name": "reverse-delivery.json",
                            "token": "ghp_asset_delete_fail_secret",
                            "api_base_url": f"http://127.0.0.1:{server.server_port}",
                            "approve_existing_asset_delete": True,
                            "approve_replacement_upload": True,
                            "expected_existing_asset_id": 7,
                            "timeout_seconds": 5,
                        },
                    )
                ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            finally:
                thread.join(timeout=5)
                server.server_close()

            self.assertEqual(result.status, "external_delivery_blocked")
            self.assertFalse(result.external_delivery_performed)
            self.assertEqual(len(RecordingGitHubReleaseAssetPreflightHandler.requests), 3)
            self.assertEqual(RecordingGitHubReleaseAssetPreflightHandler.requests[2]["method"], "DELETE")
            self.assertFalse(any(request["method"] == "POST" and str(request["path"]).startswith("/uploads/") for request in RecordingGitHubReleaseAssetPreflightHandler.requests))
            metadata = result.external_delivery_result.metadata if result.external_delivery_result else {}
            self.assertTrue(metadata["existing_asset_identity_matches"])
            self.assertTrue(metadata["existing_asset_delete_request_attempted"])
            self.assertFalse(metadata["existing_asset_delete_succeeded"])
            self.assertEqual(metadata["existing_asset_delete_status_code"], 500)
            self.assertFalse(metadata["upload_request_attempted"])
            self.assertFalse(metadata["upload_succeeded"])
            self.assertFalse(metadata["existing_asset_overwrite_performed"])
            self.assertIn("github_release_existing_asset_delete_successful", result.external_delivery_result.blocking_reasons)
            ledger = json.loads((delivery_root / "external-delivery-idempotency-ledger.json").read_text(encoding="utf-8"))
            stages = {stage["stage"]: stage for stage in ledger["entries"][0]["attempt_summary"]["stages"]}
            self.assertEqual(stages["existing_asset_delete"]["attempt_count"], 1)
            self.assertEqual(stages["existing_asset_delete"]["attempts"][0]["status_code"], 500)
            self.assertEqual(stages["upload_request"]["attempt_count"], 0)
            serialized_result = json.dumps(result.external_delivery_result.to_dict(), ensure_ascii=False)
            self.assertNotIn("ghp_asset_delete_fail_secret", serialized_result)
            self.assertNotIn("api_secret=hidden", serialized_result)

    def test_external_delivery_duplicate_guard_blocks_provider_before_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"
            first_provider = CountingExternalDeliveryProvider()

            first = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-first",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=first_provider,
                    external_delivery_idempotency_key="delivery-key-1",
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(first.status, "external_delivered")
            self.assertEqual(first_provider.calls, 1)
            first_result_path = delivery_root / "external-delivery-result.json"
            self.assertTrue(first_result_path.exists())
            first_result = json.loads(first_result_path.read_text(encoding="utf-8"))
            self.assertTrue(first_result["external_delivery_performed"])

            retry_provider = CountingExternalDeliveryProvider()
            retry = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-retry",
                    mode=DeliveryExecutionMode.APPLY,
                    overwrite=True,
                    request_external_delivery=True,
                    external_delivery_provider=retry_provider,
                    external_delivery_idempotency_key="delivery-key-1",
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            guard_path = delivery_root / "external-delivery-duplicate-guard.json"
            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(retry.status, "external_delivery_blocked")
            self.assertEqual(retry_provider.calls, 0)
            self.assertFalse(retry.external_delivery_performed)
            self.assertIsNotNone(retry.external_delivery_result)
            self.assertIn("external_delivery_not_previously_performed", retry.external_delivery_result.blocking_reasons)
            self.assertTrue(retry.external_delivery_result.metadata["duplicate_guard_triggered"])
            self.assertEqual(Path(retry.external_delivery_result.result_path).resolve(), guard_path.resolve())
            self.assertTrue(guard_path.exists())
            self.assertTrue(journal["external_delivery_performed"])
            self.assertEqual(journal["external_delivery_idempotency_key"], "delivery-key-1")
            self.assertEqual(Path(journal["external_delivery_result_path"]).resolve(), first_result_path.resolve())
            self.assertTrue(json.loads(first_result_path.read_text(encoding="utf-8"))["external_delivery_performed"])
            ledger = json.loads((delivery_root / "external-delivery-idempotency-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["entry_count"], 2)
            self.assertTrue(ledger["entries"][0]["external_delivery_performed"])
            self.assertFalse(ledger["entries"][0]["duplicate_guard_triggered"])
            self.assertFalse(ledger["entries"][1]["external_delivery_performed"])
            self.assertTrue(ledger["entries"][1]["duplicate_guard_triggered"])
            self.assertFalse(ledger["entries"][1]["provider_factory_invoked"])
            self.assertIn("duplicate_guard_blocks_provider_invocation", ledger["metadata"]["limitations"])

    def test_external_delivery_duplicate_guard_can_be_explicitly_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            delivery_root = root / "delivery"

            first_provider = CountingExternalDeliveryProvider()
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-first",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=first_provider,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            override_provider = CountingExternalDeliveryProvider()
            retry = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-external-override",
                    mode=DeliveryExecutionMode.APPLY,
                    overwrite=True,
                    request_external_delivery=True,
                    external_delivery_provider=override_provider,
                    allow_duplicate_external_delivery=True,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            self.assertEqual(retry.status, "external_delivered")
            self.assertEqual(override_provider.calls, 1)
            self.assertTrue(retry.external_delivery_performed)
            self.assertEqual(override_provider.packages[0].metadata["external_delivery_idempotency_key"], "tx-external-override")
            self.assertTrue(override_provider.packages[0].metadata["allow_duplicate_external_delivery"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
