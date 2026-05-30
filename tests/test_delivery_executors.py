from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from reverse_deepagent.delivery import DeliveryArtifact, DeliveryExecutionMode, DeliveryExecutorConfig, LocalDeliveryExecutor


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
