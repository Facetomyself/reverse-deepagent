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
    DeliveryRecoveryExecutorConfig,
    DeliveryTransactionRecoveryExecutor,
    DeliveryRollbackPhase,
    DeliveryTransactionTransitionExecutor,
    DeliveryTransactionState,
    DeliveryTransitionExecutorConfig,
    ExternalDeliveryPackage,
    ExternalDeliveryResult,
    LocalDeliveryExecutor,
    evaluate_delivery_transaction_state,
    evaluate_delivery_rollback_state,
    plan_delivery_transition,
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


class DeliveryTransactionStateMachineTests(TestCase):
    def test_dry_run_result_embeds_planned_transaction_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(delivery_root=root / "delivery", transaction_id="tx-plan")
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            payload = result.to_dict()
            state = payload["transaction_state"]
            self.assertEqual(state["state"], DeliveryTransactionState.PLANNED.value)
            self.assertEqual(state["completed_states"], [DeliveryTransactionState.PLANNED.value])
            self.assertFalse(state["blocked"])
            self.assertTrue(state["flags"]["dry_run"])
            self.assertIn("review_delivery_plan_before_apply", state["recommended_actions"])

            plan = plan_delivery_transition(result.transaction_state)
            self.assertEqual(plan.recommended_transition, "apply_local_delivery")
            self.assertTrue(plan.requires_review)

    def test_apply_result_maps_to_local_applied_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-apply",
                    mode=DeliveryExecutionMode.APPLY,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            state = result.transaction_state.to_dict()
            self.assertEqual(state["state"], DeliveryTransactionState.LOCAL_APPLIED.value)
            self.assertIn(DeliveryTransactionState.LOCAL_APPLIED.value, state["completed_states"])
            self.assertTrue(state["flags"]["filesystem_artifact_mutated"])
            self.assertIn("journal", state["evidence_paths"])
            self.assertIn("review_local_delivery_receipt", state["recommended_actions"])

    def test_manifest_mutation_maps_to_recovery_required_without_auto_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-mutated",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            snapshot = result.transaction_state
            state = snapshot.to_dict()
            self.assertEqual(state["state"], DeliveryTransactionState.RECOVERY_REQUIRED.value)
            self.assertIn(DeliveryTransactionState.MANIFEST_PATCH_WRITTEN.value, state["completed_states"])
            self.assertIn(DeliveryTransactionState.MANIFEST_PREFLIGHT_PASSED.value, state["completed_states"])
            self.assertIn(DeliveryTransactionState.MANIFEST_MUTATED.value, state["completed_states"])
            self.assertIn(DeliveryTransactionState.RECOVERY_REQUIRED.value, state["completed_states"])
            self.assertTrue(state["flags"]["backend_manifest_mutated"])
            self.assertTrue(state["flags"]["backend_manifest_rollback_written"])
            self.assertFalse(state["flags"]["cross_run_transaction_committed"])
            self.assertIn("choose_commit_or_recovery_path", state["recommended_actions"])

            plan = plan_delivery_transition(snapshot)
            self.assertEqual(plan.recommended_transition, "apply_recovery_or_commit_after_review")

            rollback_state = evaluate_delivery_rollback_state(result.to_dict()).to_dict()
            self.assertEqual(rollback_state["phase"], DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED.value)
            self.assertEqual(rollback_state["recommended_action"], "preflight_backend_manifest_recovery")
            self.assertEqual(rollback_state["allowed_transitions"][0]["name"], "preflight_backend_manifest_recovery")
            self.assertTrue(rollback_state["side_effect_policy"]["read_only"])

    def test_external_delivery_result_maps_to_external_delivered_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-external",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                    external_delivery_provider=FakeExternalDeliveryProvider(),
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            state = result.transaction_state.to_dict()
            self.assertEqual(state["state"], DeliveryTransactionState.EXTERNAL_DELIVERED.value)
            self.assertIn(DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED.value, state["completed_states"])
            self.assertIn(DeliveryTransactionState.EXTERNAL_DELIVERED.value, state["completed_states"])
            self.assertTrue(state["flags"]["external_delivery_performed"])
            self.assertTrue(state["flags"]["external_delivery_idempotency_ledger_recorded"])
            self.assertIn("external_delivery_result", state["evidence_paths"])
            self.assertIn("external_delivery_idempotency_ledger", state["evidence_paths"])

    def test_review_only_external_delivery_blocker_maps_to_blocked_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=root / "delivery",
                    transaction_id="tx-review-only",
                    mode=DeliveryExecutionMode.APPLY,
                    request_external_delivery=True,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            state = result.transaction_state.to_dict()
            self.assertEqual(state["state"], DeliveryTransactionState.BLOCKED.value)
            self.assertTrue(state["blocked"])
            self.assertIn(DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED.value, state["completed_states"])
            self.assertIn("external_delivery_provider_configured", state["blocking_reasons"])

    def test_cross_run_commit_journal_maps_to_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
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
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-commit-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-commit",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-commit-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            state = result.transaction_state.to_dict()
            self.assertEqual(state["state"], DeliveryTransactionState.COMMITTED.value)
            self.assertIn(DeliveryTransactionState.COMMITTED.value, state["completed_states"])
            self.assertTrue(state["flags"]["cross_run_transaction_committed"])
            self.assertIn("backend_manifest_transaction_commit", state["evidence_paths"])

            rollback_state = evaluate_delivery_rollback_state(result.to_dict()).to_dict()
            self.assertEqual(rollback_state["phase"], DeliveryRollbackPhase.COMMITTED.value)
            self.assertTrue(rollback_state["terminal"])
            self.assertEqual(rollback_state["recommended_action"], "review_committed_transaction_journal")

            journal = json.loads((delivery_root / "delivery-transaction-journal.json").read_text(encoding="utf-8"))
            reevaluated = evaluate_delivery_transaction_state(journal).to_dict()
            self.assertEqual(reevaluated["state"], DeliveryTransactionState.COMMITTED.value)
            self.assertEqual(reevaluated["transaction_id"], "tx-commit-source")

    def test_rollback_state_machine_requires_review_decision_after_recovery_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-decision-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-decision-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-rollback-decision-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            rollback_state = evaluate_delivery_rollback_state(result.to_dict()).to_dict()
            self.assertEqual(rollback_state["phase"], DeliveryRollbackPhase.ROLLBACK_DECISION_REQUIRED.value)
            self.assertEqual(rollback_state["status"], "awaiting_reviewer_decision")
            self.assertEqual(
                [item["name"] for item in rollback_state["allowed_transitions"]],
                ["apply_backend_manifest_recovery", "commit_cross_run_transaction"],
            )
            self.assertIn("reviewer_must_choose_recovery_or_commit_path", rollback_state["notes"])

    def test_rollback_state_machine_reports_recovered_manifest_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-recovered-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-recovered-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-rollback-recovered-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            result = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-recovered-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    apply_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-rollback-recovered-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            rollback_state = evaluate_delivery_rollback_state(result.to_dict()).to_dict()
            self.assertEqual(rollback_state["phase"], DeliveryRollbackPhase.ROLLBACK_APPLIED.value)
            self.assertEqual(rollback_state["status"], "recovered")
            self.assertFalse(rollback_state["terminal"])
            self.assertEqual(rollback_state["allowed_transitions"][0]["name"], "review_recovered_manifest_before_new_transaction")

    def test_rollback_state_machine_reports_duplicate_terminal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-duplicate-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-duplicate-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    preflight_backend_manifest_recovery=True,
                    expected_recovery_transaction_id="tx-rollback-duplicate-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-duplicate-commit-first",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-rollback-duplicate-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            duplicate = LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-rollback-duplicate-commit-second",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_cross_run_transaction=True,
                    expected_commit_transaction_id="tx-rollback-duplicate-source",
                    backend_manifest_path=backend_manifest,
                )
            ).execute([])

            rollback_state = evaluate_delivery_rollback_state(duplicate.to_dict()).to_dict()
            self.assertEqual(rollback_state["phase"], DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED.value)
            self.assertEqual(rollback_state["status"], "duplicate_blocked")
            self.assertTrue(rollback_state["terminal"])
            self.assertTrue(rollback_state["blocked"])
            self.assertEqual(rollback_state["recommended_action"], "inspect_existing_terminal_transaction_artifact")

    def test_transition_executor_plans_supported_transition_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            execution = DeliveryTransactionTransitionExecutor(
                DeliveryTransitionExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-plan",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    transition="preflight_backend_manifest_recovery",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-transition-source",
                )
            ).execute()

            payload = execution.to_dict()
            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["resolved_transition"], "preflight_backend_manifest_recovery")
            self.assertIsNone(payload["execution_record_path"])
            self.assertIsNotNone(payload["execution_result"])
            self.assertEqual(payload["execution_result"]["backend_manifest_recovery_preflight"]["status"], "planned")
            self.assertFalse((delivery_root / "delivery-transition-execution.json").exists())

    def test_transition_executor_requires_explicit_transition_for_apply_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-ambiguous",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            execution = DeliveryTransactionTransitionExecutor(
                DeliveryTransitionExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-auto",
                    mode=DeliveryExecutionMode.APPLY,
                    transition="auto",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-transition-ambiguous",
                )
            ).execute()

            payload = execution.to_dict()
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_requires_explicit_transition", payload["blocking_reasons"])
            self.assertIn("ambiguous_transition_requires_explicit_selection", payload["blocking_reasons"])
            self.assertIsNone(payload["execution_result"])
            self.assertFalse((delivery_root / "delivery-transition-execution.json").exists())

    def test_transition_executor_can_apply_recovery_preflight_and_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-commit-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            preflight = DeliveryTransactionTransitionExecutor(
                DeliveryTransitionExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-preflight",
                    mode=DeliveryExecutionMode.APPLY,
                    transition="preflight_backend_manifest_recovery",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-transition-commit-source",
                )
            ).execute()
            self.assertEqual(preflight.status, "executed")
            self.assertEqual(preflight.execution_result["backend_manifest_recovery_preflight"]["status"], "ready_for_review")

            commit = DeliveryTransactionTransitionExecutor(
                DeliveryTransitionExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-transition-commit",
                    mode=DeliveryExecutionMode.APPLY,
                    transition="commit_cross_run_transaction",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-transition-commit-source",
                )
            ).execute()

            payload = commit.to_dict()
            self.assertEqual(payload["status"], "executed")
            self.assertTrue(payload["execution_result"]["cross_run_transaction_committed"])
            self.assertTrue(payload["side_effect_policy"]["transaction_committed"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])
            self.assertTrue((delivery_root / "delivery-transition-execution.json").exists())

    def test_recovery_executor_plans_recovery_workflow_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-plan-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            execution = DeliveryTransactionRecoveryExecutor(
                DeliveryRecoveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-plan",
                    mode=DeliveryExecutionMode.DRY_RUN,
                    action="plan_recovery",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-recovery-plan-source",
                )
            ).execute()

            payload = execution.to_dict()
            self.assertEqual(payload["status"], "planned")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["action"], "plan_recovery")
            self.assertEqual(payload["before_state"]["state"], DeliveryTransactionState.RECOVERY_REQUIRED.value)
            self.assertEqual(payload["transition_executions"], [])
            self.assertFalse(payload["side_effect_policy"]["manifest_recovered"])
            self.assertFalse((delivery_root / "delivery-recovery-execution.json").exists())

    def test_recovery_executor_blocks_apply_without_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-blocked-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            execution = DeliveryTransactionRecoveryExecutor(
                DeliveryRecoveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-blocked",
                    mode=DeliveryExecutionMode.APPLY,
                    action="apply_recovery",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-recovery-blocked-source",
                    approve_recovery=False,
                )
            ).execute()

            payload = execution.to_dict()
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("apply_recovery_requires_explicit_approval", payload["blocking_reasons"])
            self.assertEqual(payload["transition_executions"], [])
            self.assertFalse((delivery_root / "delivery-recovery-execution.json").exists())

    def test_recovery_executor_can_apply_preflight_then_recovery_when_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _write_source(root)
            backend_manifest = _write_backend_manifest(root)
            original_manifest = json.loads(backend_manifest.read_text(encoding="utf-8"))
            delivery_root = root / "delivery"
            LocalDeliveryExecutor(
                DeliveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-apply-source",
                    mode=DeliveryExecutionMode.APPLY,
                    commit_backend_manifest_mutation=True,
                    preflight_backend_manifest_in_place_mutation=True,
                    approve_backend_manifest_in_place_mutation=True,
                    expected_backend_manifest_digest_sha256=_sha256_file(backend_manifest),
                    backend_manifest_path=backend_manifest,
                )
            ).execute([DeliveryArtifact(source_path=source, artifact_key="workspace_final")])

            execution = DeliveryTransactionRecoveryExecutor(
                DeliveryRecoveryExecutorConfig(
                    delivery_root=delivery_root,
                    transaction_id="tx-recovery-apply",
                    mode=DeliveryExecutionMode.APPLY,
                    action="apply_recovery",
                    backend_manifest_path=backend_manifest,
                    expected_transaction_id="tx-recovery-apply-source",
                    approve_recovery=True,
                )
            ).execute()

            payload = execution.to_dict()
            self.assertEqual(payload["status"], "recovered")
            self.assertEqual([item["resolved_transition"] for item in payload["transition_executions"]], [
                "preflight_backend_manifest_recovery",
                "apply_backend_manifest_recovery",
            ])
            self.assertTrue(payload["side_effect_policy"]["manifest_recovered"])
            self.assertFalse(payload["side_effect_policy"]["external_delivery_performed"])
            self.assertEqual(payload["after_state"]["state"], DeliveryTransactionState.RECOVERED.value)
            self.assertEqual(json.loads(backend_manifest.read_text(encoding="utf-8")), original_manifest)
            self.assertTrue((delivery_root / "delivery-recovery-execution.json").exists())
            self.assertFalse((delivery_root / "delivery-transition-execution.json").exists())



def _write_source(root: Path) -> Path:
    source = root / "workspace" / "final-result.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"ok": true}\n', encoding="utf-8")
    return source


def _write_backend_manifest(root: Path) -> Path:
    manifest = root / "workspace" / "backend-artifact-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"entries": []}\n', encoding="utf-8")
    return manifest


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    import unittest

    unittest.main()
