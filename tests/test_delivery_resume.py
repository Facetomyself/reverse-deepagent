from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.delivery import (
    DeliveryArtifact,
    DeliveryExecutorConfig,
    DeliveryExecutionMode,
    DeliveryResumePlanner,
    DeliveryResumePlannerConfig,
    DeliveryResumeRunner,
    DeliveryResumeRunnerConfig,
    DeliveryResumeWorkflowScheduler,
    DeliveryResumeWorkflowSchedulerConfig,
    LocalDeliveryExecutor,
)
from reverse_deepagent.review_approval import ReviewApprovalConfig, ReviewApprovalLedgerWriter
from reverse_deepagent.tools.delivery_tools import (
    make_delivery_resume_planner_tool,
    make_delivery_resume_runner_tool,
    make_delivery_resume_workflow_scheduler_tool,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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


class DeliveryResumeWorkflowSchedulerTests(unittest.TestCase):
    def _write_mutated_manifest_transaction(self, root: Path, transaction_id: str) -> Path:
        return DeliveryResumeRunnerTests()._write_mutated_manifest_transaction(root, transaction_id)

    def _write_recoverable_manifest_transaction(self, root: Path, transaction_id: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        workspace = root.parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        source = workspace / "final-result.json"
        source.write_text('{"ok": true}\n', encoding="utf-8")
        backend_manifest = root / "backend-artifact-manifest.json"
        backend_manifest.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")

        LocalDeliveryExecutor(
            DeliveryExecutorConfig(
                delivery_root=root,
                transaction_id=transaction_id,
                mode=DeliveryExecutionMode.APPLY,
                commit_backend_manifest_mutation=True,
                preflight_backend_manifest_in_place_mutation=True,
                approve_backend_manifest_in_place_mutation=True,
                expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                backend_manifest_path=backend_manifest,
            )
        ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
        return backend_manifest

    def _write_approval(self, workspace_root: Path, transaction_id: str, action: str) -> dict[str, object]:
        return DeliveryResumeRunnerTests()._write_approval(workspace_root, transaction_id, action)

    def _write_provider_lock(self, root: Path, transaction_id: str, owner: str = "agent-a", fencing_token: str = "1") -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "delivery-distributed-transaction-lock.json").write_text(
            json.dumps(
                {
                    "version": "2026-06-01.delivery-transaction-lock-provider-v1",
                    "provider_id": "local-file-lock",
                    "transaction_id": transaction_id,
                    "owner": owner,
                    "fencing_token": fencing_token,
                    "lease_expires_at": "2999-01-01T00:00:00+00:00",
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "renewed_at": None,
                    "metadata": {
                        "distributed_lock_contract": True,
                        "coordination_scope": "local-filesystem-reference",
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_resume_workflow_scheduler_dry_run_plans_explicit_steps_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            manifest = self._write_mutated_manifest_transaction(root, "tx-workflow-plan")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-plan",
                    step_actions=("preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-plan",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["dry_run"])
            self.assertEqual([step["action"] for step in payload["planned_steps"]], ["preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"])
            self.assertTrue(all(step["status"] == "planned" for step in payload["step_results"]))
            self.assertFalse((root / "delivery-resume-workflow.json").exists())
            self.assertFalse((root / "delivery-resume-workflow-journal.json").exists())
            self.assertFalse(payload["side_effect_policy"]["writes_workflow_record"])
            self.assertFalse(payload["side_effect_policy"]["writes_workflow_journal"])

    def test_resume_workflow_scheduler_dry_run_plans_lock_provider_steps_without_provider_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-plan",
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "renew_delivery_transaction_lock_provider",
                        "release_delivery_transaction_lock_provider",
                    ),
                    transaction_lock_owner="agent-a",
                    expected_transaction_lock_fencing_token="1",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(
                [step["action"] for step in payload["planned_steps"]],
                [
                    "acquire_delivery_transaction_lock_provider",
                    "renew_delivery_transaction_lock_provider",
                    "release_delivery_transaction_lock_provider",
                ],
            )
            self.assertTrue(all(step["executor"] == "DeliveryTransactionLockProvider" for step in payload["planned_steps"]))
            self.assertEqual(payload["planned_steps"][0]["approval_action"], "resume_acquire_delivery_transaction_lock_provider")
            self.assertEqual(payload["planned_steps"][1]["approval_action"], "resume_renew_delivery_transaction_lock_provider")
            self.assertEqual(payload["planned_steps"][2]["approval_action"], "resume_release_delivery_transaction_lock_provider")
            self.assertEqual(payload["lock_lifecycle_plan"]["prepend_step_actions"], [])
            self.assertEqual(payload["lock_lifecycle_plan"]["append_step_actions"], [])
            self.assertTrue(all(step["status"] == "planned" for step in payload["step_results"]))
            self.assertFalse(payload["side_effect_policy"]["distributed_lock_acquired"])
            self.assertFalse(payload["side_effect_policy"]["distributed_lock_renewed"])
            self.assertFalse(payload["side_effect_policy"]["distributed_lock_released"])
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())
            self.assertFalse((root / "delivery-resume-workflow-journal.json").exists())

    def test_resume_workflow_scheduler_dry_run_recommends_lock_acquire_when_provider_lock_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-lock-acquire-plan")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-acquire-plan",
                    action="plan_workflow",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-lock-acquire-plan",
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["lock_lifecycle_plan"]["status"], "lifecycle_action_recommended")
            self.assertEqual(payload["lock_lifecycle_plan"]["reason"], "provider_lock_missing_for_reviewed_workflow")
            self.assertEqual(payload["lock_lifecycle_plan"]["prepend_step_actions"], ["acquire_delivery_transaction_lock_provider"])
            self.assertEqual(payload["lock_lifecycle_plan"]["requires_review_approval_actions"], ["resume_acquire_delivery_transaction_lock_provider"])
            self.assertEqual(payload["planned_steps"][0]["action"], "acquire_delivery_transaction_lock_provider")
            self.assertEqual(payload["planned_steps"][1]["action"], "preflight_backend_manifest_recovery")
            self.assertFalse(payload["lock_lifecycle_plan"]["automatic_lock_acquire"])
            self.assertFalse(payload["lock_lifecycle_plan"]["automatic_lock_lifecycle"])
            self.assertFalse(payload["lock_lifecycle_plan"]["starts_daemon"])
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())

    def test_resume_workflow_scheduler_dry_run_recommends_lock_release_for_terminal_provider_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir(parents=True)
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps({"transaction_id": "tx-lock-release-plan", "filesystem_artifact_mutated": True}),
                encoding="utf-8",
            )
            (root / "backend-artifact-manifest-transaction-commit.json").write_text(
                json.dumps({"source_transaction_id": "tx-lock-release-plan", "committed": True}),
                encoding="utf-8",
            )
            self._write_provider_lock(root, "tx-lock-release-plan", fencing_token="3")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-release-plan",
                    action="plan_workflow",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["lock_lifecycle_plan"]["status"], "lifecycle_action_recommended")
            self.assertEqual(payload["lock_lifecycle_plan"]["reason"], "terminal_transaction_has_provider_lock_evidence")
            self.assertEqual(payload["lock_lifecycle_plan"]["append_step_actions"], ["release_delivery_transaction_lock_provider"])
            self.assertEqual(payload["lock_lifecycle_plan"]["requires_review_approval_actions"], ["resume_release_delivery_transaction_lock_provider"])
            self.assertEqual([step["action"] for step in payload["planned_steps"]], ["release_delivery_transaction_lock_provider"])
            self.assertFalse(payload["lock_lifecycle_plan"]["automatic_lock_release"])
            self.assertFalse(payload["lock_lifecycle_plan"]["stale_takeover"])
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())

    def test_resume_workflow_scheduler_dry_run_recommends_lease_renewal_when_projection_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-lease-plan")
            self._write_provider_lock(root, "tx-lease-plan", fencing_token="1")
            lock_path = root / "delivery-distributed-transaction-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lease-plan",
                    action="plan_workflow",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-lease-plan",
                    transaction_lock_owner="agent-a",
                    lease_renewal_warning_seconds=60,
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["lease_renewal_plan"]["status"], "renewal_recommended")
            self.assertEqual(payload["lease_renewal_plan"]["reason"], "lease_expired")
            self.assertEqual(payload["lease_renewal_plan"]["recommended_step_action"], "renew_delivery_transaction_lock_provider")
            self.assertEqual(payload["lease_renewal_plan"]["source"], "provider_projection")
            self.assertEqual(payload["planned_steps"][0]["action"], "renew_delivery_transaction_lock_provider")
            self.assertEqual(payload["planned_steps"][1]["action"], "preflight_backend_manifest_recovery")
            self.assertTrue(payload["lease_renewal_plan"]["requires_review_approval"])
            self.assertFalse(payload["lease_renewal_plan"]["automatic_renewal"])
            self.assertFalse(payload["lease_renewal_plan"]["starts_daemon"])

    def test_resume_workflow_scheduler_dry_run_does_not_recommend_renewal_for_healthy_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-lease-healthy")
            self._write_provider_lock(root, "tx-lease-healthy", fencing_token="1")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lease-healthy",
                    action="plan_workflow",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-lease-healthy",
                    transaction_lock_owner="agent-a",
                    lease_renewal_warning_seconds=60,
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["lease_renewal_plan"]["status"], "not_required")
            self.assertEqual(payload["lease_renewal_plan"]["reason"], "lease_healthy")
            self.assertIsNone(payload["lease_renewal_plan"]["recommended_step_action"])
            self.assertEqual(payload["planned_steps"][0]["action"], "preflight_backend_manifest_recovery")
            self.assertNotIn("renew_delivery_transaction_lock_provider", [step["action"] for step in payload["planned_steps"]])

    def test_resume_workflow_scheduler_apply_blocks_without_all_step_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_mutated_manifest_transaction(root, "tx-workflow-block")
            self._write_approval(workspace, "tx-workflow-block", "resume_preflight_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-block",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-block",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("execute_requires_review_approval_for_all_pending_steps", payload["blocking_reasons"])
            self.assertEqual(payload["approval_summary"]["missing_step_actions"], ["apply_backend_manifest_recovery"])
            self.assertFalse((root / "backend-artifact-manifest-recovery-preflight.json").exists())
            self.assertFalse((root / "delivery-resume-workflow-journal.json").exists())

    def test_resume_workflow_scheduler_apply_blocks_lock_renewal_without_review_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            self._write_provider_lock(root, "tx-renew-block")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-renew-block",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("renew_delivery_transaction_lock_provider",),
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    transaction_lock_owner="agent-a",
                    expected_transaction_lock_fencing_token="1",
                )
            ).execute().to_dict()

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("execute_requires_review_approval_for_all_pending_steps", payload["blocking_reasons"])
            self.assertEqual(payload["approval_summary"]["missing_step_actions"], ["renew_delivery_transaction_lock_provider"])
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())
            self.assertFalse((root / "delivery-resume-workflow-journal.json").exists())

    def test_resume_workflow_scheduler_executes_approved_lock_acquire_and_release_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            self._write_approval(workspace, "tx-lock-lifecycle", "resume_acquire_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-lock-lifecycle", "resume_release_delivery_transaction_lock_provider")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-lock-lifecycle",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("acquire_delivery_transaction_lock_provider", "release_delivery_transaction_lock_provider"),
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            operation = json.loads((root / "delivery-distributed-transaction-lock-operation.json").read_text(encoding="utf-8"))
            journal = json.loads((root / "delivery-resume-workflow-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual([step["status"] for step in payload["step_results"]], ["acquired", "released"])
            self.assertTrue(payload["step_results"][0]["lock_operation"]["lock_acquired"])
            self.assertTrue(payload["step_results"][1]["lock_operation"]["lock_released"])
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_acquired"])
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_released"])
            self.assertFalse((root / "delivery-distributed-transaction-lock.json").exists())
            self.assertEqual(operation["status"], "released")
            self.assertEqual(journal["entry_count"], 2)
            self.assertEqual(
                [entry["action"] for entry in journal["entries"]],
                ["acquire_delivery_transaction_lock_provider", "release_delivery_transaction_lock_provider"],
            )
            self.assertEqual(journal["entries"][0]["lock_status"], "acquired")
            self.assertEqual(journal["entries"][1]["lock_status"], "released")

    def test_resume_workflow_scheduler_propagates_acquired_fencing_token_to_runner_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-propagate")
            self._write_approval(workspace, "tx-fence-propagate", "resume_acquire_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-fence-propagate", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-propagate", "resume_apply_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-propagate",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-propagate",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            runner = payload["step_results"][2]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            journal = json.loads((root / "delivery-resume-workflow-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][0]["status"], "acquired")
            self.assertEqual(payload["step_results"][1]["status"], "preflighted")
            self.assertEqual(payload["step_results"][2]["status"], "recovered")
            self.assertEqual(lock["expected_fencing_token"], "1")
            self.assertEqual(lock["fencing_token"], "1")
            self.assertTrue(lock["metadata"]["downstream_fencing_enforced"])
            propagation = payload["step_results"][2]["fencing_token_propagation"]
            self.assertTrue(propagation["workflow_fencing_token_propagated"])
            self.assertEqual(propagation["workflow_fencing_token_source"], "workflow_step:acquire_delivery_transaction_lock_provider")
            self.assertEqual(propagation["workflow_expected_transaction_lock_fencing_token"], "1")
            self.assertEqual(journal["entries"][2]["fencing_token_propagation"]["workflow_expected_transaction_lock_fencing_token"], "1")

    def test_resume_workflow_scheduler_explicit_fencing_token_overrides_propagated_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-explicit")
            self._write_provider_lock(root, "tx-fence-explicit", fencing_token="1")
            self._write_approval(workspace, "tx-fence-explicit", "resume_renew_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-fence-explicit", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-explicit", "resume_apply_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-explicit",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "renew_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-explicit",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                    expected_transaction_lock_fencing_token="1",
                )
            ).execute().to_dict()

            runner = payload["step_results"][2]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            propagation = payload["step_results"][2]["fencing_token_propagation"]
            self.assertEqual(payload["status"], "blocked")
            self.assertEqual(payload["step_results"][0]["status"], "renewed")
            self.assertEqual(payload["step_results"][0]["lock_operation"]["fencing_token"], "2")
            self.assertEqual(payload["step_results"][2]["status"], "blocked")
            self.assertEqual(lock["expected_fencing_token"], "1")
            self.assertEqual(lock["fencing_token"], "2")
            self.assertIn("expected_transaction_lock_fencing_token_matches", lock["blocking_reasons"])
            self.assertFalse(propagation["workflow_fencing_token_propagated"])
            self.assertEqual(propagation["workflow_fencing_token_source"], "config.expected_transaction_lock_fencing_token")
            self.assertEqual(propagation["workflow_expected_transaction_lock_fencing_token"], "1")
            self.assertEqual(propagation["workflow_explicit_expected_transaction_lock_fencing_token"], "1")

    def test_resume_workflow_scheduler_replays_journaled_fencing_token_for_skipped_lock_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-journal-replay")
            self._write_approval(workspace, "tx-fence-journal-replay", "resume_acquire_delivery_transaction_lock_provider")

            first = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-journal-replay",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("acquire_delivery_transaction_lock_provider",),
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()
            self._write_approval(workspace, "tx-fence-journal-replay", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-journal-replay", "resume_apply_backend_manifest_recovery")

            second = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-journal-replay",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-journal-replay",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            runner = second["step_results"][2]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            propagation = second["step_results"][2]["fencing_token_propagation"]
            replay = second["step_results"][0]["fencing_token_replay"]
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second["step_results"][0]["status"], "skipped_completed")
            self.assertEqual(replay["source"], "workflow_journal:acquire_delivery_transaction_lock_provider")
            self.assertEqual(replay["status"], "replayed")
            self.assertEqual(lock["expected_fencing_token"], "1")
            self.assertEqual(lock["fencing_token"], "1")
            self.assertTrue(lock["metadata"]["downstream_fencing_enforced"])
            self.assertTrue(propagation["workflow_fencing_token_propagated"])
            self.assertEqual(propagation["workflow_fencing_token_source"], "workflow_journal:acquire_delivery_transaction_lock_provider")

    def test_resume_workflow_scheduler_does_not_propagate_released_fencing_token_to_later_runner_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-release-clear")
            self._write_approval(workspace, "tx-fence-release-clear", "resume_acquire_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-fence-release-clear", "resume_release_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-fence-release-clear", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-release-clear", "resume_apply_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-release-clear",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "release_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-release-clear",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            runner = payload["step_results"][3]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][2]["status"], "preflighted")
            self.assertEqual(payload["step_results"][3]["status"], "recovered")
            self.assertIsNone(lock["expected_fencing_token"])
            self.assertFalse(lock["metadata"]["downstream_fencing_enforced"])
            propagation = payload["step_results"][2]["fencing_token_propagation"]
            self.assertFalse(propagation["workflow_fencing_token_propagated"])
            self.assertIsNone(propagation["workflow_expected_transaction_lock_fencing_token"])

    def test_resume_workflow_scheduler_replayed_release_clears_journaled_fencing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-journal-release")
            self._write_approval(workspace, "tx-fence-journal-release", "resume_acquire_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-fence-journal-release", "resume_release_delivery_transaction_lock_provider")

            first = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-journal-release",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("acquire_delivery_transaction_lock_provider", "release_delivery_transaction_lock_provider"),
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()
            self._write_approval(workspace, "tx-fence-journal-release", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-journal-release", "resume_apply_backend_manifest_recovery")

            second = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-journal-release",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "release_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-journal-release",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            runner = second["step_results"][3]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            propagation = second["step_results"][3]["fencing_token_propagation"]
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second["step_results"][0]["status"], "skipped_completed")
            self.assertEqual(second["step_results"][1]["status"], "skipped_completed")
            self.assertTrue(second["step_results"][1]["fencing_token_replay"]["clear_token"])
            self.assertIsNone(lock["expected_fencing_token"])
            self.assertFalse(lock["metadata"]["downstream_fencing_enforced"])
            self.assertFalse(propagation["workflow_fencing_token_propagated"])
            self.assertIsNone(propagation["workflow_expected_transaction_lock_fencing_token"])

    def test_resume_workflow_scheduler_does_not_replay_expired_journaled_fencing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-fence-journal-expired")
            root.mkdir(parents=True, exist_ok=True)
            (root / "delivery-resume-workflow-journal.json").write_text(
                json.dumps(
                    {
                        "version": "2026-06-01.delivery-resume-workflow-journal-v1",
                        "workflow_id": "previous-workflow",
                        "entries": [
                            {
                                "workflow_id": "previous-workflow",
                                "order": 1,
                                "action": "acquire_delivery_transaction_lock_provider",
                                "approval_action": "resume_acquire_delivery_transaction_lock_provider",
                                "status": "acquired",
                                "transaction_id": "tx-fence-journal-expired",
                                "lock_status": "acquired",
                                "lock_provider_id": "local-file-lock",
                                "lock_fencing_token": "1",
                                "lock_lease_expires_at": "2000-01-01T00:00:00+00:00",
                                "created_at": "2000-01-01T00:00:00+00:00",
                                "side_effect_policy": {"lock_acquired": True},
                            }
                        ],
                        "entry_count": 1,
                        "updated_at": "2000-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            self._write_provider_lock(root, "tx-fence-journal-expired", fencing_token="1")
            lock = json.loads((root / "delivery-distributed-transaction-lock.json").read_text(encoding="utf-8"))
            lock["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            (root / "delivery-distributed-transaction-lock.json").write_text(json.dumps(lock), encoding="utf-8")
            self._write_approval(workspace, "tx-fence-journal-expired", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-fence-journal-expired", "resume_apply_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-fence-journal-expired",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=(
                        "acquire_delivery_transaction_lock_provider",
                        "preflight_backend_manifest_recovery",
                        "apply_backend_manifest_recovery",
                    ),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-fence-journal-expired",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    require_transaction_lock=True,
                    transaction_lock_owner="agent-a",
                )
            ).execute().to_dict()

            runner = payload["step_results"][2]["runner_execution"]
            lock = runner["transition_execution"]["execution_result"]["transaction_lock"]
            replay = payload["step_results"][0]["fencing_token_replay"]
            propagation = payload["step_results"][2]["fencing_token_propagation"]
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][0]["status"], "skipped_completed")
            self.assertEqual(replay["status"], "not_replayed")
            self.assertEqual(replay["reason"], "lease_expired_or_malformed")
            self.assertIsNone(lock["expected_fencing_token"])
            self.assertFalse(lock["metadata"]["downstream_fencing_enforced"])
            self.assertFalse(propagation["workflow_fencing_token_propagated"])

    def test_resume_workflow_scheduler_executes_approved_lock_renewal_and_writes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            self._write_provider_lock(root, "tx-renew-run")
            self._write_approval(workspace, "tx-renew-run", "resume_renew_delivery_transaction_lock_provider")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-renew-run",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("renew_delivery_transaction_lock_provider",),
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    transaction_lock_owner="agent-a",
                    expected_transaction_lock_fencing_token="1",
                    transaction_lock_provider_metadata={"test": "renewal"},
                )
            ).execute().to_dict()

            lock = json.loads((root / "delivery-distributed-transaction-lock.json").read_text(encoding="utf-8"))
            operation = json.loads((root / "delivery-distributed-transaction-lock-operation.json").read_text(encoding="utf-8"))
            journal = json.loads((root / "delivery-resume-workflow-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][0]["status"], "renewed")
            self.assertEqual(payload["step_results"][0]["lock_operation"]["status"], "renewed")
            self.assertTrue(payload["step_results"][0]["lock_operation"]["lock_renewed"])
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_renewed"])
            self.assertEqual(lock["fencing_token"], "2")
            self.assertEqual(operation["fencing_token"], "2")
            self.assertEqual(journal["entry_count"], 1)
            self.assertEqual(journal["entries"][0]["action"], "renew_delivery_transaction_lock_provider")
            self.assertEqual(journal["entries"][0]["lock_status"], "renewed")
            self.assertEqual(journal["entries"][0]["lock_provider_id"], "local-file-lock")
            self.assertEqual(journal["entries"][0]["lock_fencing_token"], "2")

    def test_resume_workflow_scheduler_executes_approved_multi_step_recovery_and_writes_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-run")
            self._write_approval(workspace, "tx-workflow-run", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-workflow-run", "resume_apply_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-run",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-run",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                    metadata={"source": "scheduler-test"},
                )
            ).execute().to_dict()

            workflow_path = root / "delivery-resume-workflow.json"
            journal_path = root / "delivery-resume-workflow-journal.json"
            self.assertEqual(payload["status"], "completed")
            self.assertEqual([step["status"] for step in payload["step_results"]], ["preflighted", "recovered"])
            self.assertTrue(payload["side_effect_policy"]["writes_workflow_record"])
            self.assertTrue(payload["side_effect_policy"]["writes_workflow_journal"])
            self.assertTrue(payload["side_effect_policy"]["manifest_recovered"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])
            self.assertTrue(workflow_path.exists())
            self.assertTrue(journal_path.exists())
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["entry_count"], 2)
            self.assertEqual([entry["action"] for entry in journal["entries"]], ["preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"])
            self.assertTrue((root / "backend-artifact-manifest-recovery.json").exists())

    def test_resume_workflow_scheduler_skips_completed_journaled_steps_on_resume_of_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-resume")
            self._write_approval(workspace, "tx-workflow-resume", "resume_preflight_backend_manifest_recovery")

            first = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-resume",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("preflight_backend_manifest_recovery",),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-resume",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()
            self._write_approval(workspace, "tx-workflow-resume", "resume_apply_backend_manifest_recovery")

            second = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-resume",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-resume",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()

            journal = json.loads((root / "delivery-resume-workflow-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second["step_results"][0]["status"], "skipped_completed")
            self.assertEqual(second["step_results"][1]["status"], "recovered")
            self.assertEqual(second["step_results"][0]["journal_replay"]["entry_status"], "preflighted")
            self.assertEqual(second["step_results"][0]["journal_replay"]["runner_status"], "preflighted")
            self.assertEqual(second["step_results"][0]["journal_replay"]["transition_status"], "executed")
            self.assertTrue(second["step_results"][0]["journal_replay"]["readonly_replay_metadata_only"])
            self.assertFalse(second["step_results"][0]["journal_replay"]["side_effects_replayed"])
            self.assertEqual(journal["entry_count"], 2)
            self.assertEqual([entry["action"] for entry in journal["entries"]], ["preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"])

    def test_resume_workflow_scheduler_does_not_skip_steps_from_other_transaction_journal_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-no-cross-replay")
            root.mkdir(parents=True, exist_ok=True)
            (root / "delivery-resume-workflow-journal.json").write_text(
                json.dumps(
                    {
                        "version": "2026-06-01.delivery-resume-workflow-journal-v1",
                        "workflow_id": "previous-workflow",
                        "entries": [
                            {
                                "workflow_id": "previous-workflow",
                                "order": 1,
                                "action": "preflight_backend_manifest_recovery",
                                "approval_action": "resume_preflight_backend_manifest_recovery",
                                "status": "preflighted",
                                "transaction_id": "tx-other",
                                "runner_status": "preflighted",
                                "transition_status": "preflighted",
                                "created_at": "2026-06-01T00:00:00+00:00",
                                "side_effect_policy": {"manifest_recovered": False},
                            }
                        ],
                        "entry_count": 1,
                        "updated_at": "2026-06-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            self._write_approval(workspace, "tx-workflow-no-cross-replay", "resume_preflight_backend_manifest_recovery")

            payload = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-no-cross-replay",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=("preflight_backend_manifest_recovery",),
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-no-cross-replay",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()

            journal = json.loads((root / "delivery-resume-workflow-journal.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][0]["status"], "preflighted")
            self.assertNotIn("journal_replay", payload["step_results"][0])
            self.assertEqual(journal["entry_count"], 2)
            self.assertEqual([entry["transaction_id"] for entry in journal["entries"]], ["tx-other", "tx-workflow-no-cross-replay"])

    def test_resume_workflow_scheduler_records_noop_when_all_steps_are_journaled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-noop")
            self._write_approval(workspace, "tx-workflow-noop", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-workflow-noop", "resume_apply_backend_manifest_recovery")
            step_actions = ("preflight_backend_manifest_recovery", "apply_backend_manifest_recovery")

            first = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-noop",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=step_actions,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-noop",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()
            second = DeliveryResumeWorkflowScheduler(
                DeliveryResumeWorkflowSchedulerConfig(
                    delivery_root=root,
                    transaction_id="tx-workflow-noop",
                    action="execute_workflow",
                    mode=DeliveryExecutionMode.APPLY,
                    step_actions=step_actions,
                    backend_manifest_path=manifest,
                    expected_transaction_id="tx-workflow-noop",
                    approval_ledger_path=workspace / "review-approval-ledger.json",
                )
            ).execute().to_dict()

            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "recorded")
            self.assertEqual([step["status"] for step in second["step_results"]], ["skipped_completed", "skipped_completed"])
            self.assertEqual(second["approval_summary"]["expected_step_actions"], [])
            self.assertEqual(second["blocking_reasons"], [])

    def test_resume_workflow_scheduler_tool_executes_with_matching_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-tool")
            self._write_approval(workspace, "tx-workflow-tool", "resume_preflight_backend_manifest_recovery")
            self._write_approval(workspace, "tx-workflow-tool", "resume_apply_backend_manifest_recovery")
            tool = make_delivery_resume_workflow_scheduler_tool(root)

            payload = tool(
                transaction_id="tx-workflow-tool",
                action="execute_workflow",
                mode="apply",
                step_actions_json=json.dumps(["preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"]),
                backend_manifest_path=str(manifest),
                expected_transaction_id="tx-workflow-tool",
                approval_ledger_path=str(workspace / "review-approval-ledger.json"),
                metadata_json=json.dumps({"tool": True}),
            )

            self.assertEqual(payload["status"], "completed")
            self.assertTrue(payload["metadata"]["tool"])
            self.assertTrue((root / "delivery-resume-workflow.json").exists())
            self.assertTrue((root / "delivery-resume-workflow-journal.json").exists())

    def test_resume_workflow_scheduler_tool_plans_lease_renewal_warning_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            manifest = self._write_recoverable_manifest_transaction(root, "tx-workflow-tool-lease")
            self._write_provider_lock(root, "tx-workflow-tool-lease", fencing_token="1")
            lock_path = root / "delivery-distributed-transaction-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            tool = make_delivery_resume_workflow_scheduler_tool(root)

            payload = tool(
                transaction_id="tx-workflow-tool-lease",
                action="plan_workflow",
                mode="dry-run",
                backend_manifest_path=str(manifest),
                expected_transaction_id="tx-workflow-tool-lease",
                transaction_lock_owner="agent-a",
                lease_renewal_warning_seconds=30,
            )

            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["lease_renewal_plan"]["status"], "renewal_recommended")
            self.assertEqual(payload["lease_renewal_plan"]["warning_seconds"], 30)
            self.assertEqual(payload["lease_renewal_plan"]["requires_review_approval_action"], "resume_renew_delivery_transaction_lock_provider")
            self.assertEqual(payload["planned_steps"][0]["action"], "renew_delivery_transaction_lock_provider")
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())

    def test_resume_workflow_scheduler_tool_executes_lock_renewal_with_provider_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            self._write_provider_lock(root, "tx-renew-tool")
            self._write_approval(workspace, "tx-renew-tool", "resume_renew_delivery_transaction_lock_provider")
            tool = make_delivery_resume_workflow_scheduler_tool(root)

            payload = tool(
                transaction_id="tx-renew-tool",
                action="execute_workflow",
                mode="apply",
                step_actions_json=json.dumps(["renew_delivery_transaction_lock_provider"]),
                approval_ledger_path=str(workspace / "review-approval-ledger.json"),
                transaction_lock_owner="agent-a",
                expected_transaction_lock_fencing_token="1",
                transaction_lock_provider_id="local-file-lock",
                transaction_lock_provider_metadata_json=json.dumps({"redis_lock_key": "unused-test-key"}),
            )

            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["step_results"][0]["lock_operation"]["status"], "renewed")
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_renewed"])
            self.assertTrue((root / "delivery-resume-workflow.json").exists())
            self.assertTrue((root / "delivery-resume-workflow-journal.json").exists())

    def test_resume_workflow_scheduler_tool_executes_lock_acquire_release_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "delivery"
            workspace = base / "workspace"
            self._write_approval(workspace, "tx-lock-tool", "resume_acquire_delivery_transaction_lock_provider")
            self._write_approval(workspace, "tx-lock-tool", "resume_release_delivery_transaction_lock_provider")
            tool = make_delivery_resume_workflow_scheduler_tool(root)

            payload = tool(
                transaction_id="tx-lock-tool",
                action="execute_workflow",
                mode="apply",
                step_actions_json=json.dumps(
                    [
                        "acquire_delivery_transaction_lock_provider",
                        "release_delivery_transaction_lock_provider",
                    ]
                ),
                approval_ledger_path=str(workspace / "review-approval-ledger.json"),
                transaction_lock_owner="agent-a",
                transaction_lock_provider_id="local-file-lock",
            )

            self.assertEqual(payload["status"], "completed")
            self.assertEqual([step["status"] for step in payload["step_results"]], ["acquired", "released"])
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_acquired"])
            self.assertTrue(payload["side_effect_policy"]["distributed_lock_released"])
            self.assertTrue((root / "delivery-resume-workflow.json").exists())
            self.assertTrue((root / "delivery-resume-workflow-journal.json").exists())


if __name__ == "__main__":
    unittest.main()
