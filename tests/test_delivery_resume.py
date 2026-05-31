from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.delivery import (
    DeliveryExecutionMode,
    DeliveryResumePlanner,
    DeliveryResumePlannerConfig,
    DeliveryResumeRunner,
    DeliveryResumeRunnerConfig,
)
from reverse_deepagent.review_approval import ReviewApprovalConfig, ReviewApprovalLedgerWriter
from reverse_deepagent.tools.delivery_tools import make_delivery_resume_planner_tool, make_delivery_resume_runner_tool


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



class DeliveryResumeRunnerTests(unittest.TestCase):
    def _write_mutated_manifest_transaction(self, root: Path, transaction_id: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        source_manifest = root / "backend-artifact-manifest.json"
        rollback_manifest = root / "backend-artifact-manifest.rollback.json"
        mutation_record = root / "backend-artifact-manifest-in-place-mutation.json"
        journal_path = root / "delivery-transaction-journal.json"
        source_manifest.write_text(json.dumps({"version": 2, "entries": []}), encoding="utf-8")
        rollback_manifest.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
        mutation_record.write_text(
            json.dumps(
                {
                    "transaction_id": transaction_id,
                    "mutated": True,
                    "source_manifest_path": str(source_manifest),
                    "rollback_path": str(rollback_manifest),
                }
            ),
            encoding="utf-8",
        )
        journal_path.write_text(
            json.dumps(
                {
                    "transaction_id": transaction_id,
                    "journal_path": str(journal_path),
                    "dry_run": False,
                    "filesystem_artifact_mutated": True,
                    "backend_manifest_mutated": True,
                    "backend_manifest_recovered": False,
                    "cross_run_transaction_committed": False,
                }
            ),
            encoding="utf-8",
        )
        return source_manifest

    def _write_approval(self, workspace_root: Path, transaction_id: str, action: str) -> dict[str, object]:
        return ReviewApprovalLedgerWriter(
            ReviewApprovalConfig(
                review_root=workspace_root,
                subject_id=transaction_id,
                action=action,
                decision="approved",
                reviewer="alice",
                reason="Approved resume runner action.",
                mode="apply",
                approve_decision_record=True,
            )
        ).execute().to_dict()

    def test_resume_runner_dry_run_plans_without_approval_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            manifest = self._write_mutated_manifest_transaction(root, "tx-resume-run")
            runner = DeliveryResumeRunner(
                DeliveryResumeRunnerConfig(
                    delivery_root=root,
                    transaction_id="tx-resume-run",
                    action="preflight_backend_manifest_recovery",
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-resume-run",
                )
            )

            payload = runner.execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["dry_run"])
            self.assertIsNone(payload["execution_record_path"])
            self.assertFalse((root / "delivery-resume-execution.json").exists())
            self.assertFalse(payload["approval"]["matched"])
            self.assertFalse(payload["side_effect_policy"]["writes_resume_execution_record"])
            self.assertFalse(payload["side_effect_policy"]["manifest_recovered"])

    def test_resume_runner_apply_blocks_without_review_approval_ledger_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            manifest = self._write_mutated_manifest_transaction(root, "tx-resume-block")

            payload = DeliveryResumeRunner(
                DeliveryResumeRunnerConfig(
                    delivery_root=root,
                    transaction_id="tx-resume-block",
                    action="preflight_backend_manifest_recovery",
                    mode=DeliveryExecutionMode.APPLY,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-resume-block",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_review_approval_ledger_entry", payload["blocking_reasons"])
            self.assertFalse((root / "delivery-resume-execution.json").exists())
            self.assertFalse((root / "backend-artifact-manifest-recovery-preflight.json").exists())

    def test_resume_runner_apply_executes_approved_recovery_preflight_and_writes_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_mutated_manifest_transaction(root, "tx-resume-preflight")
            approval = self._write_approval(workspace, "tx-resume-preflight", "resume_preflight_backend_manifest_recovery")

            payload = DeliveryResumeRunner(
                DeliveryResumeRunnerConfig(
                    delivery_root=root,
                    transaction_id="tx-resume-preflight",
                    action="preflight_backend_manifest_recovery",
                    mode=DeliveryExecutionMode.APPLY,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-resume-preflight",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    approval_id=str(approval["approval_id"]),
                )
            ).execute().to_dict()

            record_path = root / "delivery-resume-execution.json"
            self.assertEqual(payload["status"], "preflighted")
            self.assertTrue(payload["approval"]["matched"])
            self.assertEqual(payload["transition_execution"]["status"], "executed")
            self.assertTrue(record_path.exists())
            persisted = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["transaction_id"], "tx-resume-preflight")
            self.assertTrue((root / "backend-artifact-manifest-recovery-preflight.json").exists())
            self.assertTrue(payload["side_effect_policy"]["writes_resume_execution_record"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])
            self.assertFalse(payload["side_effect_policy"]["physical_rollback_executed"])

    def test_resume_runner_tool_can_execute_with_matching_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_mutated_manifest_transaction(root, "tx-resume-tool")
            self._write_approval(workspace, "tx-resume-tool", "resume_preflight_backend_manifest_recovery")
            tool = make_delivery_resume_runner_tool(root)

            payload = tool(
                transaction_id="tx-resume-tool",
                action="preflight_backend_manifest_recovery",
                mode="apply",
                backend_manifest_path=str(manifest),
                expected_transaction_id="tx-resume-tool",
                approval_ledger_path=str(workspace / "review-approval-ledger.json"),
                metadata_json=json.dumps({"tool": True}),
            )

            self.assertEqual(payload["status"], "preflighted")
            self.assertTrue(payload["metadata"]["tool"])
            self.assertTrue((root / "delivery-resume-execution.json").exists())


if __name__ == "__main__":
    unittest.main()
