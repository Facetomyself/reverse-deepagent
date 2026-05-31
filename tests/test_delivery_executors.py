from __future__ import annotations

import hashlib
import json
import tempfile
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
