import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.delivery.inspector import (
    DELIVERY_TRANSACTION_INSPECTOR_VERSION,
    inspect_delivery_transaction_root,
)


class DeliveryTransactionInspectorTests(unittest.TestCase):
    def test_inspector_reads_journal_and_recommends_next_transition_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal_path = root / "delivery-transaction-journal.json"
            journal_path.write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-local",
                        "journal_path": str(journal_path),
                        "dry_run": False,
                        "filesystem_artifact_mutated": True,
                        "entries": [{"artifact_key": "report", "status": "delivered"}],
                    }
                ),
                encoding="utf-8",
            )

            inspection = inspect_delivery_transaction_root(root).to_dict()

        self.assertTrue(inspection["ok"])
        self.assertEqual(inspection["version"], DELIVERY_TRANSACTION_INSPECTOR_VERSION)
        self.assertEqual(inspection["state_snapshot"]["transaction_id"], "tx-local")
        self.assertEqual(inspection["state_snapshot"]["state"], "local_applied")
        self.assertEqual(inspection["transition_plan"]["recommended_transition"], "review_or_commit_manifest_revision")
        self.assertEqual(inspection["rollback_state"]["phase"], "local_delivery_applied")
        self.assertEqual(inspection["rollback_state"]["recommended_action"], "review_or_commit_manifest_revision")
        self.assertTrue(inspection["side_effect_policy"]["read_only"])
        self.assertFalse(inspection["side_effect_policy"]["files_mutated"])
        self.assertFalse(inspection["side_effect_policy"]["external_delivery_performed"])
        self.assertTrue(inspection["artifacts"]["transaction_journal"]["loaded"])
        self.assertIn("external_delivery_result", inspection["missing_artifacts"])
        self.assertIn("external_delivery_idempotency_ledger", inspection["missing_artifacts"])
        self.assertIn("delivery_transition_execution", inspection["missing_artifacts"])

    def test_inspector_loads_external_delivery_result_and_commit_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps({"transaction_id": "tx-commit", "filesystem_artifact_mutated": True}),
                encoding="utf-8",
            )
            (root / "external-delivery-result.json").write_text(
                json.dumps({"transaction_id": "tx-commit", "external_delivery_performed": True}),
                encoding="utf-8",
            )
            (root / "external-delivery-idempotency-ledger.json").write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-commit",
                        "ledger_path": str(root / "external-delivery-idempotency-ledger.json"),
                        "entry_count": 1,
                        "entries": [{"transaction_id": "tx-commit", "external_delivery_performed": True}],
                    }
                ),
                encoding="utf-8",
            )
            (root / "backend-artifact-manifest-transaction-commit.json").write_text(
                json.dumps({"source_transaction_id": "tx-commit", "committed": True}),
                encoding="utf-8",
            )

            inspection = inspect_delivery_transaction_root(root).to_dict()

        self.assertTrue(inspection["ok"])
        self.assertEqual(inspection["state_snapshot"]["state"], "committed")
        self.assertEqual(inspection["rollback_state"]["phase"], "external_delivery_performed")
        self.assertTrue(inspection["rollback_state"]["terminal"])
        self.assertIn("external_delivered", inspection["state_snapshot"]["completed_states"])
        self.assertTrue(inspection["state_snapshot"]["flags"]["external_delivery_idempotency_ledger_recorded"])
        self.assertIn("external_delivery_idempotency_ledger", inspection["state_snapshot"]["evidence_paths"])
        self.assertEqual(inspection["transition_plan"]["recommended_transition"], "no_next_transition")

    def test_inspector_reports_malformed_artifact_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "delivery-transaction-journal.json").write_text("{not-json", encoding="utf-8")

            inspection = inspect_delivery_transaction_root(root).to_dict()

        self.assertFalse(inspection["ok"])
        self.assertIn("transaction_journal", inspection["load_errors"])
        self.assertEqual(inspection["state_snapshot"]["state"], "planned")


if __name__ == "__main__":
    unittest.main()
