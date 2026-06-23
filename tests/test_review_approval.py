from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.review_approval import ReviewApprovalConfig, ReviewApprovalLedgerWriter
from reverse_deepagent.tools.review_tools import make_record_review_approval_tool


class ReviewApprovalLedgerTests(unittest.TestCase):
    def test_dry_run_is_read_only_and_plans_review_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            record = ReviewApprovalLedgerWriter(
                ReviewApprovalConfig(
                    review_root=root,
                    subject_id="proposal-1",
                    action="materialize_stitched_flow",
                    reviewer="alice",
                    reason="Evidence is sufficient.",
                )
            ).execute()
            payload = record.to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["dry_run"])
            self.assertIsNone(payload["record_path"])
            self.assertIsNone(payload["ledger_path"])
            self.assertFalse((root / "review-approval-record.json").exists())
            self.assertFalse((root / "review-approval-ledger.json").exists())
            self.assertTrue(payload["side_effect_policy"]["dry_run_is_read_only"])
            self.assertFalse(payload["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(payload["side_effect_policy"]["delivery_executed"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])

    def test_apply_requires_explicit_record_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            payload = ReviewApprovalLedgerWriter(
                ReviewApprovalConfig(
                    review_root=root,
                    subject_id="proposal-1",
                    action="materialize_stitched_flow",
                    reviewer="alice",
                    mode="apply",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_explicit_approval_record", payload["blocking_reasons"])
            self.assertFalse((root / "review-approval-record.json").exists())
            self.assertFalse((root / "review-approval-ledger.json").exists())

    def test_apply_writes_record_and_append_only_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            config = ReviewApprovalConfig(
                review_root=root,
                subject_id="proposal-1",
                action="materialize_stitched_flow",
                decision="approved",
                reviewer="alice",
                reason="Reviewed source and replay artifacts.",
                mode="apply",
                approve_decision_record=True,
                subject_digest_sha256="abc",
                expected_subject_digest_sha256="abc",
                metadata={"ticket": "R-1"},
            )

            first = ReviewApprovalLedgerWriter(config).execute().to_dict()
            second = ReviewApprovalLedgerWriter(config).execute().to_dict()

            self.assertEqual(first["status"], "written")
            self.assertEqual(first["ledger_entry_count"], 1)
            self.assertEqual(second["ledger_entry_count"], 2)
            record_path = root / "review-approval-record.json"
            ledger_path = root / "review-approval-ledger.json"
            self.assertTrue(record_path.exists())
            self.assertTrue(ledger_path.exists())
            record_payload = json.loads(record_path.read_text(encoding="utf-8"))
            ledger_payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            self.assertEqual(record_payload["approval_id"], second["approval_id"])
            self.assertEqual(ledger_payload["entry_count"], 2)
            self.assertEqual(len(ledger_payload["entries"]), 2)
            self.assertEqual(ledger_payload["entries"][0]["approval_id"], first["approval_id"])
            self.assertEqual(ledger_payload["entries"][1]["approval_id"], second["approval_id"])
            self.assertTrue(second["side_effect_policy"]["writes_approval_record"])
            self.assertTrue(second["side_effect_policy"]["review_decision_recorded"])
            self.assertFalse(second["side_effect_policy"]["manifest_mutated"])
            self.assertFalse(second["side_effect_policy"]["transaction_committed"])

    def test_blocks_missing_reviewer_unsupported_decision_bad_mode_and_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            payload = ReviewApprovalLedgerWriter(
                ReviewApprovalConfig(
                    review_root=root,
                    subject_id="proposal-1",
                    action="materialize_stitched_flow",
                    decision="rubber_stamp",
                    mode="apply-now",
                    approve_decision_record=True,
                    subject_digest_sha256="actual",
                    expected_subject_digest_sha256="expected",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("decision_supported", payload["blocking_reasons"])
            self.assertIn("mode_supported", payload["blocking_reasons"])
            self.assertIn("reviewer_present", payload["blocking_reasons"])
            self.assertIn("subject_digest_matches_expected", payload["blocking_reasons"])
            self.assertFalse((root / "review-approval-record.json").exists())
            self.assertFalse((root / "review-approval-ledger.json").exists())

    def test_record_review_approval_tool_writes_only_review_audit_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            tool = make_record_review_approval_tool(root)

            payload = tool(
                subject_id="delivery-package-1",
                action="approve_delivery_package",
                decision="approved",
                reviewer="alice",
                reason="Ready for explicit delivery executor.",
                mode="apply",
                approve_decision_record=True,
                metadata_json=json.dumps({"source": "unit-test"}),
            )

            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["metadata"]["tool"], "record_review_approval")
            self.assertEqual(payload["metadata"]["source"], "unit-test")
            self.assertTrue((root / "review-approval-record.json").exists())
            self.assertTrue((root / "review-approval-ledger.json").exists())
            self.assertFalse(payload["side_effect_policy"]["delivery_executed"])
            self.assertFalse(payload["side_effect_policy"]["rollback_executed"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])


if __name__ == "__main__":
    unittest.main()
