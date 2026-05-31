from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.delivery import (
    DeliveryExecutionMode,
    DeliveryResumePlanner,
    DeliveryResumePlannerConfig,
)
from reverse_deepagent.tools.delivery_tools import make_delivery_resume_planner_tool


class DeliveryResumePlannerTests(unittest.TestCase):
    def test_resume_planner_dry_run_recommends_local_delivery_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            planner = DeliveryResumePlanner(
                DeliveryResumePlannerConfig(delivery_root=root, transaction_id="tx-new")
            )

            plan = planner.execute().to_dict()

        self.assertEqual(plan["status"], "no_transaction")
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["transaction_id"], "tx-new")
        self.assertEqual(plan["recommended_resume_action"], "start_local_delivery_transaction")
        self.assertIsNone(plan["resume_plan_path"])
        self.assertFalse((root / "delivery-resume-plan.json").exists())
        self.assertFalse(plan["side_effect_policy"]["writes_resume_plan_artifact"])
        self.assertTrue(plan["side_effect_policy"]["does_not_execute_transitions"])

    def test_resume_planner_blocks_on_active_lock_held_by_other_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-lock-block",
                        "dry_run": False,
                        "filesystem_artifact_mutated": True,
                    }
                ),
                encoding="utf-8",
            )
            (root / "delivery-transaction-lock.json").write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-lock-block",
                        "owner": "agent-a",
                        "resume_token": "resume-a",
                        "lease_expires_at": "2999-01-01T00:00:00+00:00",
                        "status": "acquired",
                    }
                ),
                encoding="utf-8",
            )

            plan = DeliveryResumePlanner(
                DeliveryResumePlannerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-block",
                    transaction_lock_owner="agent-b",
                    expected_resume_token="resume-b",
                )
            ).execute().to_dict()

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["recommended_resume_action"], "review_or_release_delivery_transaction_lock")
        self.assertIn("active_transaction_lock_allows_resume", plan["blocking_reasons"])
        self.assertTrue(plan["lock_summary"]["blocks_resume"])
        self.assertFalse(plan["lock_summary"]["resume_allowed"])
        self.assertEqual(plan["resume_steps"][0]["action"], "manual_review_blockers")

    def test_resume_planner_accepts_matching_resume_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-lock-resume",
                        "dry_run": False,
                        "filesystem_artifact_mutated": True,
                    }
                ),
                encoding="utf-8",
            )
            (root / "delivery-transaction-lock.json").write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-lock-resume",
                        "owner": "agent-a",
                        "resume_token": "resume-a",
                        "lease_expires_at": "2999-01-01T00:00:00+00:00",
                        "status": "acquired",
                    }
                ),
                encoding="utf-8",
            )

            plan = DeliveryResumePlanner(
                DeliveryResumePlannerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-resume",
                    transaction_lock_owner="agent-b",
                    expected_resume_token="resume-a",
                )
            ).execute().to_dict()

        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["lock_summary"]["resume_token_matches"], True)
        self.assertEqual(plan["lock_summary"]["resume_allowed"], True)
        self.assertNotIn("active_transaction_lock_allows_resume", plan["blocking_reasons"])
        self.assertEqual(plan["resume_steps"][1]["action"], "reuse_existing_local_lock_with_matching_owner_or_resume_token")

    def test_resume_planner_write_plan_writes_only_resume_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            journal_path = root / "delivery-transaction-journal.json"
            journal_path.write_text(
                json.dumps(
                    {
                        "transaction_id": "tx-write-plan",
                        "journal_path": str(journal_path),
                        "dry_run": False,
                        "filesystem_artifact_mutated": True,
                        "entries": [{"artifact_key": "report", "status": "delivered"}],
                    }
                ),
                encoding="utf-8",
            )
            before_journal = journal_path.read_text(encoding="utf-8")

            plan = DeliveryResumePlanner(
                DeliveryResumePlannerConfig(
                    delivery_root=root,
                    transaction_id="tx-write-plan",
                    mode=DeliveryExecutionMode.APPLY,
                    metadata={"source": "test"},
                )
            ).execute().to_dict()

            resume_path = root / "delivery-resume-plan.json"
            after_journal = journal_path.read_text(encoding="utf-8")
            resume_exists = resume_path.exists()
            persisted = json.loads(resume_path.read_text(encoding="utf-8"))

        self.assertEqual(plan["status"], "written")
        self.assertEqual(plan["resume_plan_path"], str(resume_path.resolve()))
        self.assertTrue(resume_exists)
        self.assertEqual(before_journal, after_journal)
        self.assertEqual(persisted["transaction_id"], "tx-write-plan")
        self.assertEqual(persisted["metadata"]["source"], "test")
        self.assertTrue(persisted["side_effect_policy"]["writes_resume_plan_artifact"])
        self.assertFalse(persisted["side_effect_policy"]["manifest_mutated"])
        self.assertFalse(persisted["side_effect_policy"]["external_delivery_performed"])
        self.assertTrue(persisted["side_effect_policy"]["does_not_commit_transaction"])

    def test_resume_planner_returns_terminal_status_for_committed_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps({"transaction_id": "tx-terminal", "filesystem_artifact_mutated": True}),
                encoding="utf-8",
            )
            (root / "backend-artifact-manifest-transaction-commit.json").write_text(
                json.dumps({"source_transaction_id": "tx-terminal", "committed": True}),
                encoding="utf-8",
            )

            plan = DeliveryResumePlanner(DeliveryResumePlannerConfig(delivery_root=root)).execute().to_dict()

        self.assertEqual(plan["status"], "terminal")
        self.assertEqual(plan["recommended_resume_action"], "review_terminal_transaction_no_resume")
        self.assertIn("do_not_resume_terminal_delivery_transaction", plan["recommended_actions"])

    def test_delivery_resume_tool_writes_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps({"transaction_id": "tx-tool-resume", "filesystem_artifact_mutated": True}),
                encoding="utf-8",
            )
            tool = make_delivery_resume_planner_tool(root)

            result = tool(transaction_id="tx-tool-resume", mode="apply", metadata_json=json.dumps({"tool": True}))
            resume_exists = (root / "delivery-resume-plan.json").exists()

        self.assertEqual(result["status"], "written")
        self.assertEqual(result["metadata"]["tool"], True)
        self.assertTrue(resume_exists)
        self.assertTrue(result["side_effect_policy"]["writes_resume_plan_artifact"])


if __name__ == "__main__":
    unittest.main()
