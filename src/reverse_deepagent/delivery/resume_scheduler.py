from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .lock_provider import (
    DeliveryTransactionLockProviderConfig,
    build_default_delivery_transaction_lock_provider_registry,
)
from .resume import DeliveryResumePlanner, DeliveryResumePlannerConfig
from .resume_runner import DeliveryResumeRunner, DeliveryResumeRunnerConfig, RESUME_ACTION_TO_APPROVAL_ACTION, SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS

SUPPORTED_DELIVERY_RESUME_WORKFLOW_ACTIONS: tuple[str, ...] = ("plan_workflow", "execute_workflow")
DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION = "acquire_delivery_transaction_lock_provider"
DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION = "renew_delivery_transaction_lock_provider"
DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION = "release_delivery_transaction_lock_provider"
DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS: dict[str, tuple[str, str]] = {
    DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION: ("acquire_lock", "acquired"),
    DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION: ("renew_lock", "renewed"),
    DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION: ("release_lock", "released"),
}
SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS: tuple[str, ...] = tuple(
    action for action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS if action != "plan_only"
) + tuple(DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS)
RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION: dict[str, str] = {
    **RESUME_ACTION_TO_APPROVAL_ACTION,
    DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION: "resume_acquire_delivery_transaction_lock_provider",
    DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION: "resume_renew_delivery_transaction_lock_provider",
    DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION: "resume_release_delivery_transaction_lock_provider",
}
_DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES = {"preflighted", "recovered", "committed", "executed", "acquired", "renewed", "released"}


@dataclass(frozen=True)
class DeliveryResumeWorkflowSchedulerConfig:
    """Configuration for the durable delivery resume workflow scheduler baseline.

    The scheduler coordinates multiple explicitly reviewed resume-runner steps
    and records a durable append-only step journal. It deliberately keeps the
    low-level recovery / commit semantics inside ``DeliveryResumeRunner`` and
    ``DeliveryTransactionTransitionExecutor``.
    """

    delivery_root: Path
    transaction_id: str | None = None
    action: str = "plan_workflow"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    step_actions: tuple[str, ...] = field(default_factory=tuple)
    max_steps: int = 5
    backend_manifest_path: Path | None = None
    expected_transaction_id: str | None = None
    approval_ledger_path: Path | None = None
    approval_decision: str = "approved"
    require_review_approval: bool = True
    require_transaction_lock: bool = False
    transaction_lock_owner: str | None = None
    transaction_lock_lease_seconds: int = 900
    lease_renewal_warning_seconds: int | None = None
    expected_resume_token: str | None = None
    expected_transaction_lock_fencing_token: str | None = None
    transaction_lock_provider_id: str = "local-file-lock"
    transaction_lock_provider_metadata: dict[str, Any] = field(default_factory=dict)
    write_workflow_record: bool = True
    workflow_record_name: str = "delivery-resume-workflow.json"
    workflow_journal_name: str = "delivery-resume-workflow-journal.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()

    def resolved_backend_manifest_path(self) -> Path | None:
        if self.backend_manifest_path is None:
            return None
        return self.backend_manifest_path.expanduser().resolve()

    def resolved_approval_ledger_path(self) -> Path:
        if self.approval_ledger_path is not None:
            return self.approval_ledger_path.expanduser().resolve()
        return self.resolved_delivery_root().parent / "workspace" / "review-approval-ledger.json"


@dataclass(frozen=True)
class DeliveryResumeWorkflowExecution:
    workflow_id: str
    transaction_id: str | None
    action: str
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    workflow_record_path: str | None
    workflow_journal_path: str | None
    resume_plan: dict[str, Any]
    planned_steps: list[dict[str, Any]]
    step_results: list[dict[str, Any]]
    existing_journal_summary: dict[str, Any]
    lock_lifecycle_plan: dict[str, Any]
    lease_renewal_plan: dict[str, Any]
    workflow_readiness_plan: dict[str, Any]
    approval_summary: dict[str, Any]
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        executed_steps = [step for step in self.step_results if step.get("status") not in {"planned", "skipped_completed"}]
        skipped_steps = [step for step in self.step_results if step.get("status") == "skipped_completed"]
        manifest_recovered = any(bool(_runner_policy(step).get("manifest_recovered")) for step in self.step_results)
        transaction_committed = any(bool(_runner_policy(step).get("transaction_committed")) for step in self.step_results)
        files_mutated = any(bool(_runner_policy(step).get("files_mutated")) for step in self.step_results)
        workflow_record_written = bool(self.workflow_record_path) and not self.dry_run and self.status in {"completed", "partially_completed", "recorded"}
        journal_written = bool(self.workflow_journal_path) and not self.dry_run and bool(self.step_results) and self.status != "planned"
        distributed_lock_acquired = any(_step_managed_distributed_lock(step, flag="lock_acquired", status="acquired") for step in self.step_results)
        distributed_lock_renewed = any(_step_renewed_distributed_lock(step) for step in self.step_results)
        distributed_lock_released = any(_step_managed_distributed_lock(step, flag="lock_released", status="released") for step in self.step_results)
        return {
            "workflow_id": self.workflow_id,
            "transaction_id": self.transaction_id,
            "action": self.action,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "workflow_record_path": self.workflow_record_path,
            "workflow_journal_path": self.workflow_journal_path,
            "resume_plan": self.resume_plan,
            "planned_steps": self.planned_steps,
            "step_results": self.step_results,
            "existing_journal_summary": self.existing_journal_summary,
            "lock_lifecycle_plan": self.lock_lifecycle_plan,
            "lease_renewal_plan": self.lease_renewal_plan,
            "workflow_readiness_plan": self.workflow_readiness_plan,
            "approval_summary": self.approval_summary,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_workflow_record": workflow_record_written,
                "writes_workflow_journal": journal_written,
                "uses_review_approval_ledger": True,
                "requires_review_approval_for_apply": True,
                "multi_step_scheduler": True,
                "executed_step_count": len(executed_steps),
                "skipped_completed_step_count": len(skipped_steps),
                "files_mutated": files_mutated,
                "manifest_recovered": manifest_recovered,
                "transaction_committed": transaction_committed,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "starts_new_local_delivery": False,
                "automatic_resume_without_review": False,
                "distributed_lock_acquired": distributed_lock_acquired,
                "distributed_lock_renewed": distributed_lock_renewed,
                "distributed_lock_released": distributed_lock_released,
                "physical_rollback_executed": False,
            },
        }


class DeliveryResumeWorkflowScheduler:
    """Review-gated multi-step scheduler for durable delivery resume workflows."""

    def __init__(self, config: DeliveryResumeWorkflowSchedulerConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryResumeWorkflowExecution:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        workflow_id = _workflow_id(created_at=created_at, delivery_root=delivery_root, transaction_id=self.config.transaction_id, action=self.config.action)
        resume_plan = DeliveryResumePlanner(
            DeliveryResumePlannerConfig(
                delivery_root=delivery_root,
                transaction_id=self.config.transaction_id,
                mode=DeliveryExecutionMode.DRY_RUN,
                write_resume_plan=False,
                expected_resume_token=self.config.expected_resume_token,
                transaction_lock_owner=self.config.transaction_lock_owner,
                metadata={**self.config.metadata, "resume_workflow_scheduler_preflight": True},
            )
        ).execute().to_dict()
        transaction_id = self.config.transaction_id or _first_str(resume_plan.get("transaction_id"))
        existing_entries = _read_workflow_journal_entries(delivery_root / self.config.workflow_journal_name)
        existing_journal_summary = _journal_summary(existing_entries, transaction_id=str(transaction_id or ""))
        lease_renewal_plan = _lease_renewal_plan(
            delivery_root=delivery_root,
            existing_entries=existing_entries,
            transaction_id=str(transaction_id or ""),
            created_at=created_at,
            warning_seconds=self.config.lease_renewal_warning_seconds
            if self.config.lease_renewal_warning_seconds is not None
            else max(1, int(self.config.transaction_lock_lease_seconds) // 3),
        )
        lock_lifecycle_plan = _lock_lifecycle_plan(
            delivery_root=delivery_root,
            existing_entries=existing_entries,
            resume_plan=resume_plan,
            transaction_id=str(transaction_id or ""),
            created_at=created_at,
            lease_renewal_plan=lease_renewal_plan,
        )
        planned_steps = self._planned_steps(
            resume_plan=resume_plan,
            completed_actions=set(existing_journal_summary["completed_actions"]),
            lease_renewal_plan=lease_renewal_plan,
            lock_lifecycle_plan=lock_lifecycle_plan,
        )
        approval_summary = _approval_summary(
            ledger_path=self.config.resolved_approval_ledger_path(),
            transaction_id=transaction_id,
            step_actions=[str(step["action"]) for step in planned_steps if not step.get("already_completed")],
            expected_decision=self.config.approval_decision,
        )
        runtime_gate_evidence_projection = _runtime_gate_evidence_projection(
            delivery_root=delivery_root,
            backend_manifest_path=self.config.resolved_backend_manifest_path(),
            transaction_id=str(transaction_id or ""),
            planned_steps=planned_steps,
            created_at=created_at,
            require_transaction_lock=self.config.require_transaction_lock,
            explicit_expected_fencing_token_configured=bool(self.config.expected_transaction_lock_fencing_token),
        )
        checks = self._checks(
            resume_plan=resume_plan,
            planned_steps=planned_steps,
            approval_summary=approval_summary,
            transaction_id=transaction_id,
        )
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        workflow_readiness_plan = _workflow_readiness_plan(
            action=self.config.action,
            mode=self.config.mode,
            transaction_id=str(transaction_id or ""),
            planned_steps=planned_steps,
            approval_summary=approval_summary,
            checks=checks,
            blocking_reasons=blocking_reasons,
            existing_journal_summary=existing_journal_summary,
            lock_lifecycle_plan=lock_lifecycle_plan,
            lease_renewal_plan=lease_renewal_plan,
            require_transaction_lock=self.config.require_transaction_lock,
            explicit_expected_fencing_token_configured=bool(self.config.expected_transaction_lock_fencing_token),
            runtime_gate_evidence_projection=runtime_gate_evidence_projection,
        )
        step_results: list[dict[str, Any]] = []
        if not blocking_reasons:
            step_results = self._run_steps(
                workflow_id=workflow_id,
                delivery_root=delivery_root,
                transaction_id=str(transaction_id or ""),
                planned_steps=planned_steps,
                created_at=created_at,
                existing_entries=existing_entries,
            )
            failed_steps = [step for step in step_results if step.get("status") == "blocked"]
            if failed_steps:
                blocking_reasons.append("resume_workflow_step_blocked")
        status = self._status(blocking_reasons=blocking_reasons, step_results=step_results, dry_run=dry_run)
        workflow_record_path = (
            str(delivery_root / self.config.workflow_record_name)
            if self.config.write_workflow_record and not dry_run and status in {"completed", "partially_completed", "recorded"}
            else None
        )
        workflow_journal_path = str(delivery_root / self.config.workflow_journal_name) if not dry_run and step_results and status != "planned" else None
        execution = DeliveryResumeWorkflowExecution(
            workflow_id=workflow_id,
            transaction_id=str(transaction_id) if transaction_id else None,
            action=self.config.action,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            workflow_record_path=workflow_record_path,
            workflow_journal_path=workflow_journal_path,
            resume_plan=resume_plan,
            planned_steps=planned_steps,
            step_results=step_results,
            existing_journal_summary=existing_journal_summary,
            lock_lifecycle_plan=lock_lifecycle_plan,
            lease_renewal_plan=lease_renewal_plan,
            workflow_readiness_plan=workflow_readiness_plan,
            approval_summary=approval_summary,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status=status, step_results=step_results),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-resume-workflow-scheduler",
                "scope": "delivery-resume-workflow-scheduler-baseline",
                "supported_actions": list(SUPPORTED_DELIVERY_RESUME_WORKFLOW_ACTIONS),
                "supported_step_actions": list(SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS),
                "approval_ledger_path": str(self.config.resolved_approval_ledger_path()),
                "workflow_journal_name": self.config.workflow_journal_name,
                "automatic_resume_without_review": False,
                "limitations": [
                    "explicit_step_actions_only_for_multi_step_apply",
                    "requires_review_approval_ledger_for_apply",
                    "delegates_each_step_to_delivery_resume_runner",
                    "journal_skips_completed_steps_but_does_not_replay_arbitrary_side_effects",
                    "does_not_start_new_local_delivery",
                    "does_not_publish_external_delivery",
                    "lock_provider_acquire_renew_release_are_explicit_steps_only",
                    "does_not_automatically_acquire_renew_or_release_distributed_locks",
                    "does_not_execute_physical_rollback",
                ],
            },
        )
        if workflow_record_path:
            _write_json(Path(workflow_record_path), execution.to_dict())
        if workflow_journal_path:
            _append_workflow_journal(
                path=Path(workflow_journal_path),
                workflow_id=workflow_id,
                created_at=created_at,
                previous_entries=existing_entries,
                new_entries=[step for step in step_results if step.get("journal_recordable")],
            )
        return execution

    def _planned_steps(
        self,
        *,
        resume_plan: dict[str, Any],
        completed_actions: set[str],
        lease_renewal_plan: dict[str, Any],
        lock_lifecycle_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        actions = list(self.config.step_actions) if self.config.step_actions else _default_step_actions(resume_plan)
        if not self.config.step_actions:
            for action in reversed(lock_lifecycle_plan.get("prepend_step_actions", [])):
                if action in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS and action not in actions and action not in completed_actions:
                    actions = [str(action), *actions]
            for action in lock_lifecycle_plan.get("append_step_actions", []):
                if action in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS and action not in actions and action not in completed_actions:
                    actions = [*actions, str(action)]
        if (
            not self.config.step_actions
            and lease_renewal_plan.get("recommended_step_action") == DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION
            and DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION not in actions
            and DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION not in completed_actions
        ):
            actions = [DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION, *actions]
        steps: list[dict[str, Any]] = []
        for index, action in enumerate(actions[: max(0, int(self.config.max_steps))], start=1):
            steps.append(
                {
                    "order": index,
                    "action": str(action),
                    "approval_action": RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION.get(str(action)),
                    "already_completed": str(action) in completed_actions,
                    "executor": "DeliveryTransactionLockProvider" if str(action) in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS else "DeliveryResumeRunner",
                    "side_effect": True,
                }
            )
        return steps

    def _checks(
        self,
        *,
        resume_plan: dict[str, Any],
        planned_steps: list[dict[str, Any]],
        approval_summary: dict[str, Any],
        transaction_id: str | None,
    ) -> list[dict[str, Any]]:
        action = str(self.config.action or "")
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        pending_steps = [step for step in planned_steps if not step.get("already_completed")]
        unsupported_steps = [str(step.get("action")) for step in planned_steps if step.get("action") not in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS]
        missing_approvals = approval_summary.get("missing_step_actions", [])
        terminal_release_only = bool(planned_steps) and all(str(step.get("action") or "") == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION for step in planned_steps)
        return [
            {
                "name": "resume_workflow_action_supported",
                "passed": action in SUPPORTED_DELIVERY_RESUME_WORKFLOW_ACTIONS,
                "details": {"action": action, "supported": list(SUPPORTED_DELIVERY_RESUME_WORKFLOW_ACTIONS)},
            },
            {
                "name": "resume_plan_not_blocked",
                "passed": not bool(resume_plan.get("blocking_reasons")),
                "details": {"status": resume_plan.get("status"), "blocking_reasons": resume_plan.get("blocking_reasons", [])},
            },
            {
                "name": "terminal_transactions_are_not_scheduled",
                "passed": resume_plan.get("status") != "terminal" or terminal_release_only,
                "details": {"resume_plan_status": resume_plan.get("status"), "terminal_release_only": terminal_release_only},
            },
            {
                "name": "workflow_has_supported_steps",
                "passed": bool(planned_steps) and not unsupported_steps,
                "details": {"planned_step_count": len(planned_steps), "unsupported_steps": unsupported_steps},
            },
            {
                "name": "max_steps_not_exceeded",
                "passed": len(planned_steps) <= max(0, int(self.config.max_steps)),
                "details": {"planned_step_count": len(planned_steps), "max_steps": self.config.max_steps},
            },
            {
                "name": "execute_requires_planned_steps",
                "passed": dry_run or action != "execute_workflow" or bool(planned_steps),
                "details": {"pending_step_count": len(pending_steps), "completed_step_count": len(planned_steps) - len(pending_steps)},
            },
            {
                "name": "execute_requires_detected_transaction_id",
                "passed": dry_run or action != "execute_workflow" or bool(str(transaction_id or "").strip()),
                "details": {"transaction_id": transaction_id},
            },
            {
                "name": "execute_requires_review_approval_for_all_pending_steps",
                "passed": dry_run or action != "execute_workflow" or not self.config.require_review_approval or not missing_approvals,
                "details": {
                    "required": self.config.require_review_approval,
                    "missing_step_actions": missing_approvals,
                    "matched_step_actions": approval_summary.get("matched_step_actions", []),
                },
            },
        ]

    def _run_steps(
        self,
        *,
        workflow_id: str,
        delivery_root: Path,
        transaction_id: str,
        planned_steps: list[dict[str, Any]],
        created_at: str,
        existing_entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        results: list[dict[str, Any]] = []
        propagated_fencing_token = str(self.config.expected_transaction_lock_fencing_token or "").strip() or None
        propagated_fencing_source = "config.expected_transaction_lock_fencing_token" if propagated_fencing_token else None
        journal_fencing_state = _journal_fencing_replay_state(
            entries=existing_entries,
            transaction_id=transaction_id,
            created_at=created_at,
        )
        journal_replay_state = _journal_replay_state(entries=existing_entries, transaction_id=transaction_id)
        for step in planned_steps:
            action = str(step.get("action") or "")
            if step.get("already_completed"):
                replay = _journal_fencing_replay_for_skipped_step(journal_fencing_state, action=action)
                journal_replay = _journal_replay_for_skipped_step(journal_replay_state, action=action)
                if replay.get("clear_token"):
                    propagated_fencing_token = None
                    propagated_fencing_source = None
                elif replay.get("fencing_token") and not self.config.expected_transaction_lock_fencing_token:
                    propagated_fencing_token = str(replay["fencing_token"])
                    propagated_fencing_source = str(replay["source"])
                results.append(
                    {
                        **step,
                        "status": "skipped_completed",
                        "dry_run": dry_run,
                        "workflow_id": workflow_id,
                        "created_at": created_at,
                        "runner_execution": None,
                        "fencing_token_replay": replay,
                        "journal_replay": journal_replay,
                        "journal_recordable": False,
                    }
                )
                continue
            if dry_run or self.config.action == "plan_workflow":
                results.append(
                    {
                        **step,
                        "status": "planned",
                        "dry_run": True,
                        "workflow_id": workflow_id,
                        "created_at": created_at,
                        "runner_execution": None,
                        "journal_recordable": False,
                    }
                )
                continue
            if action in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS:
                lock_result = self._run_lock_provider_step(
                    delivery_root=delivery_root,
                    transaction_id=transaction_id,
                    workflow_id=workflow_id,
                    step=step,
                    created_at=created_at,
                )
                results.append(lock_result)
                propagation = _fencing_token_propagation_from_lock_step(lock_result)
                if propagation.get("clear_token"):
                    propagated_fencing_token = None
                    propagated_fencing_source = None
                elif propagation.get("fencing_token"):
                    propagated_fencing_token = str(propagation["fencing_token"])
                    propagated_fencing_source = str(propagation["source"])
                if lock_result.get("status") == "blocked":
                    break
                continue
            expected_fencing_token = self.config.expected_transaction_lock_fencing_token or propagated_fencing_token
            fencing_metadata = _fencing_propagation_metadata(
                expected_fencing_token=expected_fencing_token,
                propagated_fencing_token=propagated_fencing_token,
                propagated_fencing_source=propagated_fencing_source,
                explicit_expected_fencing_token=self.config.expected_transaction_lock_fencing_token,
            )
            runner = DeliveryResumeRunner(
                DeliveryResumeRunnerConfig(
                    delivery_root=delivery_root,
                    transaction_id=transaction_id,
                    action=action,
                    mode=self.config.mode,
                    backend_manifest_path=self.config.resolved_backend_manifest_path(),
                    expected_transaction_id=self.config.expected_transaction_id or transaction_id,
                    approval_ledger_path=self.config.resolved_approval_ledger_path(),
                    approval_action=RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION.get(action),
                    approval_decision=self.config.approval_decision,
                    require_review_approval=self.config.require_review_approval,
                    require_transaction_lock=self.config.require_transaction_lock,
                    transaction_lock_owner=self.config.transaction_lock_owner,
                    transaction_lock_lease_seconds=self.config.transaction_lock_lease_seconds,
                    expected_resume_token=self.config.expected_resume_token,
                    expected_transaction_lock_fencing_token=expected_fencing_token,
                    write_execution_record=False,
                    metadata={
                        **self.config.metadata,
                        **fencing_metadata,
                        "resume_workflow_scheduler": True,
                        "resume_workflow_id": workflow_id,
                        "resume_workflow_step_order": step.get("order"),
                        "resume_workflow_step_action": action,
                    },
                )
            ).execute().to_dict()
            results.append(
                {
                    **step,
                    "status": runner.get("status"),
                    "dry_run": False,
                    "workflow_id": workflow_id,
                    "created_at": created_at,
                    "runner_execution": runner,
                    "fencing_token_propagation": fencing_metadata,
                    "journal_recordable": runner.get("status") in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES,
                }
            )
            if runner.get("status") == "blocked":
                break
        return results

    def _run_lock_provider_step(
        self,
        *,
        delivery_root: Path,
        transaction_id: str,
        workflow_id: str,
        step: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        workflow_action = str(step.get("action") or "")
        provider_action, success_status = DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS[workflow_action]
        owner = str(self.config.transaction_lock_owner or transaction_id).strip() or transaction_id
        registry = build_default_delivery_transaction_lock_provider_registry()
        provider = registry.create(self.config.transaction_lock_provider_id)
        config = DeliveryTransactionLockProviderConfig(
            lock_root=delivery_root,
            transaction_id=transaction_id,
            owner=owner,
            action=provider_action,
            mode=self.config.mode,
            lease_seconds=self.config.transaction_lock_lease_seconds,
            expected_owner=owner if provider_action in {"renew_lock", "release_lock"} else None,
            expected_fencing_token=self.config.expected_transaction_lock_fencing_token,
            approve_release=provider_action == "release_lock",
            metadata={
                **self.config.transaction_lock_provider_metadata,
                **self.config.metadata,
                "resume_workflow_scheduler": True,
                "resume_workflow_id": workflow_id,
                "resume_workflow_step_order": step.get("order"),
                "resume_workflow_step_action": step.get("action"),
            },
        )
        operation = provider.manage_lock(config, created_at=created_at).to_dict()
        return {
            **step,
            "status": operation.get("status"),
            "dry_run": False,
            "workflow_id": workflow_id,
            "created_at": created_at,
            "lock_operation": operation,
            "runner_execution": None,
            "journal_recordable": operation.get("status") == success_status,
        }

    @staticmethod
    def _status(*, blocking_reasons: list[str], step_results: list[dict[str, Any]], dry_run: bool) -> str:
        if blocking_reasons:
            return "blocked"
        if dry_run or not step_results or all(step.get("status") == "planned" for step in step_results):
            return "planned"
        if all(step.get("status") == "skipped_completed" for step in step_results):
            return "recorded"
        if all(step.get("status") in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES | {"skipped_completed"} for step in step_results):
            return "completed"
        if any(step.get("status") in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES for step in step_results):
            return "partially_completed"
        return "recorded"

    @staticmethod
    def _recommended_actions(*, status: str, step_results: list[dict[str, Any]]) -> list[str]:
        if status == "blocked":
            return ["inspect_resume_workflow_scheduler_checks_and_step_results"]
        if status == "planned":
            return ["record_review_approval_for_each_pending_resume_workflow_step_then_execute_workflow"]
        if status == "completed":
            if any(step.get("action") == "apply_backend_manifest_recovery" for step in step_results):
                return ["review_recovered_manifest_before_commit_or_new_delivery"]
            if any(step.get("action") == "commit_cross_run_transaction" for step in step_results):
                return ["review_committed_transaction_before_external_delivery"]
            return ["review_completed_resume_workflow"]
        return ["review_resume_workflow_journal_before_continuing"]


def _default_step_actions(resume_plan: dict[str, Any]) -> list[str]:
    recommended = str(resume_plan.get("recommended_resume_action") or "")
    if recommended in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS:
        return [recommended]
    transition = resume_plan.get("transition_plan") if isinstance(resume_plan.get("transition_plan"), dict) else {}
    transition_recommended = str(transition.get("recommended_transition") or "")
    if transition_recommended in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS:
        return [transition_recommended]
    if transition_recommended == "apply_recovery_or_commit_after_review":
        return ["preflight_backend_manifest_recovery"]
    return []


def _workflow_readiness_plan(
    *,
    action: str,
    mode: DeliveryExecutionMode,
    transaction_id: str,
    planned_steps: list[dict[str, Any]],
    approval_summary: dict[str, Any],
    checks: list[dict[str, Any]],
    blocking_reasons: list[str],
    existing_journal_summary: dict[str, Any],
    lock_lifecycle_plan: dict[str, Any],
    lease_renewal_plan: dict[str, Any],
    require_transaction_lock: bool,
    explicit_expected_fencing_token_configured: bool,
    runtime_gate_evidence_projection: dict[str, Any],
) -> dict[str, Any]:
    """Build a side-effect-free readiness summary for review/subagent routing."""

    pending_steps = [step for step in planned_steps if not step.get("already_completed")]
    completed_steps = [step for step in planned_steps if step.get("already_completed")]
    failed_checks = [str(check.get("name") or "") for check in checks if not check.get("passed")]
    expected_step_actions = [str(action) for action in approval_summary.get("expected_step_actions", []) if str(action).strip()]
    missing_step_actions = [str(action) for action in approval_summary.get("missing_step_actions", []) if str(action).strip()]
    matched_step_actions = [str(action) for action in approval_summary.get("matched_step_actions", []) if str(action).strip()]
    required_approval_actions = _approval_actions_for_step_actions(expected_step_actions)
    missing_approval_actions = _approval_actions_for_step_actions(missing_step_actions)
    matched_approval_actions = _approval_actions_for_step_actions(matched_step_actions)
    requires_lock_provider_action = any(str(step.get("action") or "") in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS for step in planned_steps)
    lock_lifecycle_recommended = bool(lock_lifecycle_plan.get("recommended_step_actions"))
    lease_renewal_recommended = bool(lease_renewal_plan.get("recommended_step_action"))
    uses_journal_replay_context = bool(existing_journal_summary.get("completed_actions")) or any(step.get("already_completed") for step in planned_steps)
    step_dependency_contexts = _workflow_step_dependency_contexts(
        planned_steps=planned_steps,
        approval_summary=approval_summary,
        blocking_reasons=blocking_reasons,
        existing_journal_summary=existing_journal_summary,
        lock_lifecycle_plan=lock_lifecycle_plan,
        lease_renewal_plan=lease_renewal_plan,
        require_transaction_lock=require_transaction_lock,
        explicit_expected_fencing_token_configured=explicit_expected_fencing_token_configured,
        runtime_gate_evidence_projection=runtime_gate_evidence_projection,
    )
    dependency_summary = _workflow_step_dependency_summary(step_dependency_contexts)

    if blocking_reasons or failed_checks:
        status = "blocked"
        next_review_actions = ["inspect_resume_workflow_scheduler_checks"]
    elif not planned_steps:
        status = "no_steps"
        next_review_actions = ["inspect_delivery_transaction_state"]
    elif missing_approval_actions:
        status = "ready_for_review"
        next_review_actions = ["record_review_approval_for_each_pending_resume_workflow_step"]
    elif action == "execute_workflow" and mode == DeliveryExecutionMode.APPLY:
        status = "ready_to_execute"
        next_review_actions = ["execute_delivery_resume_workflow"]
    else:
        status = "ready_for_review"
        next_review_actions = ["review_planned_resume_workflow_steps"]

    return {
        "enabled": True,
        "status": status,
        "transaction_id": transaction_id or None,
        "action": action,
        "mode": mode.value,
        "planned_step_count": len(planned_steps),
        "pending_step_count": len(pending_steps),
        "already_completed_step_count": len(completed_steps),
        "pending_step_actions": [str(step.get("action") or "") for step in pending_steps],
        "already_completed_step_actions": [str(step.get("action") or "") for step in completed_steps],
        "required_step_actions": expected_step_actions,
        "missing_step_actions": missing_step_actions,
        "matched_step_actions": matched_step_actions,
        "required_approval_actions": required_approval_actions,
        "missing_approval_actions": missing_approval_actions,
        "matched_approval_actions": matched_approval_actions,
        "blocking_reasons": list(blocking_reasons),
        "failed_checks": failed_checks,
        "lock_lifecycle_status": lock_lifecycle_plan.get("status"),
        "lock_lifecycle_reason": lock_lifecycle_plan.get("reason"),
        "lease_renewal_status": lease_renewal_plan.get("status"),
        "lease_renewal_reason": lease_renewal_plan.get("reason"),
        "requires_lock_provider_action": requires_lock_provider_action,
        "requires_fencing_review": bool(
            requires_lock_provider_action or lock_lifecycle_recommended or lease_renewal_recommended
        ),
        "uses_journal_replay_context": uses_journal_replay_context,
        "journal_completed_actions": list(existing_journal_summary.get("completed_actions", [])),
        "runtime_gate_evidence_projection": runtime_gate_evidence_projection,
        "step_dependency_contexts": step_dependency_contexts,
        "dependency_summary": dependency_summary,
        "next_review_actions": next_review_actions,
        "dry_run_plan_only": True,
        "side_effects_performed": False,
        "automatic_execution": False,
        "starts_daemon": False,
        "automatic_lock_lifecycle": False,
        "automatic_lease_renewal": False,
    }


def _workflow_step_dependency_contexts(
    *,
    planned_steps: list[dict[str, Any]],
    approval_summary: dict[str, Any],
    blocking_reasons: list[str],
    existing_journal_summary: dict[str, Any],
    lock_lifecycle_plan: dict[str, Any],
    lease_renewal_plan: dict[str, Any],
    require_transaction_lock: bool,
    explicit_expected_fencing_token_configured: bool,
    runtime_gate_evidence_projection: dict[str, Any],
) -> list[dict[str, Any]]:
    """Describe conservative step dependencies without claiming gate success."""

    matched_step_actions = {str(action) for action in approval_summary.get("matched_step_actions", [])}
    missing_step_actions = {str(action) for action in approval_summary.get("missing_step_actions", [])}
    journal_completed_actions = {str(action) for action in existing_journal_summary.get("completed_actions", [])}
    contexts: list[dict[str, Any]] = []
    preceding_steps: list[dict[str, Any]] = []
    planned_lock_source_actions: list[str] = []
    planned_fencing_source_actions: list[str] = []
    for step in planned_steps:
        action = str(step.get("action") or "")
        already_completed = bool(step.get("already_completed"))
        predecessor_actions = [str(item.get("action") or "") for item in preceding_steps]
        completed_predecessor_actions = [
            str(item.get("action") or "")
            for item in preceding_steps
            if item.get("already_completed") or str(item.get("action") or "") in journal_completed_actions
        ]
        planned_predecessor_actions = [
            str(item.get("action") or "")
            for item in preceding_steps
            if not item.get("already_completed") and str(item.get("action") or "") not in journal_completed_actions
        ]
        approval_action = RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION.get(action)
        approval_required = not already_completed and bool(approval_action)
        approval_matched = not approval_required or action in matched_step_actions
        approval_missing = approval_required and action in missing_step_actions
        provider_lock_dependency = _provider_lock_dependency(
            action=action,
            preceding_lock_actions=planned_lock_source_actions,
            lock_lifecycle_plan=lock_lifecycle_plan,
            require_transaction_lock=require_transaction_lock,
        )
        fencing_dependency = _fencing_dependency(
            action=action,
            preceding_fencing_actions=planned_fencing_source_actions,
            lock_lifecycle_plan=lock_lifecycle_plan,
            lease_renewal_plan=lease_renewal_plan,
            require_transaction_lock=require_transaction_lock,
            explicit_expected_fencing_token_configured=explicit_expected_fencing_token_configured,
        )
        recovery_preflight_dependency = _recovery_preflight_dependency(
            action=action,
            predecessor_actions=predecessor_actions,
            journal_completed_actions=journal_completed_actions,
        )
        if already_completed:
            readiness = "journal_replay_available"
        elif approval_missing:
            readiness = "review_approval_required"
        elif blocking_reasons:
            readiness = "workflow_checks_blocked"
        else:
            readiness = "ready_for_ordered_execution_review"
        runtime_gate_checks = _runtime_gate_checks_for_step(action)
        runtime_gate_evidence = _runtime_gate_evidence_for_step(
            action=action,
            runtime_gate_checks=runtime_gate_checks,
            projection=runtime_gate_evidence_projection,
        )
        contexts.append(
            {
                "order": step.get("order"),
                "action": action,
                "executor": step.get("executor"),
                "readiness": readiness,
                "already_completed": already_completed,
                "journal_replay_available": already_completed and action in journal_completed_actions,
                "approval": {
                    "required": approval_required,
                    "action": approval_action,
                    "matched": approval_matched,
                    "missing": approval_missing,
                },
                "serial_dependencies": {
                    "predecessor_actions": predecessor_actions,
                    "completed_predecessor_actions": completed_predecessor_actions,
                    "planned_predecessor_actions": planned_predecessor_actions,
                    "runtime_order_enforced_by_scheduler": True,
                },
                "provider_lock_dependency": provider_lock_dependency,
                "fencing_dependency": fencing_dependency,
                "recovery_preflight_dependency": recovery_preflight_dependency,
                "runtime_gate_checks": runtime_gate_checks,
                "runtime_gate_review_required": bool(runtime_gate_checks),
                "runtime_gate_evidence": runtime_gate_evidence,
                "side_effects_performed": False,
                "readonly_dependency_metadata_only": True,
            }
        )
        preceding_steps.append(step)
        if action in {DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION}:
            planned_lock_source_actions = [action]
            planned_fencing_source_actions = [action]
        elif action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION:
            planned_lock_source_actions = []
            planned_fencing_source_actions = []
    return contexts


def _provider_lock_dependency(
    *,
    action: str,
    preceding_lock_actions: list[str],
    lock_lifecycle_plan: dict[str, Any],
    require_transaction_lock: bool,
) -> dict[str, Any]:
    provider_action = action in {
        DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION,
        DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION,
    }
    runner_action = action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS and action != "plan_only"
    required = provider_action or bool(require_transaction_lock and runner_action)
    evidence_present = bool(lock_lifecycle_plan.get("provider_lock_evidence_present"))
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION:
        status = "step_acquires_provider_lock"
    elif preceding_lock_actions:
        status = "planned_predecessor_lock_action"
    elif evidence_present:
        status = "provider_projection_or_journal_evidence_present"
    elif required:
        status = "runtime_provider_lock_review_required"
    else:
        status = "not_required"
    return {
        "required": required,
        "status": status,
        "provider_lock_evidence_present": evidence_present,
        "planned_predecessor_lock_actions": preceding_lock_actions,
        "runtime_gate_must_revalidate": required,
    }


def _fencing_dependency(
    *,
    action: str,
    preceding_fencing_actions: list[str],
    lock_lifecycle_plan: dict[str, Any],
    lease_renewal_plan: dict[str, Any],
    require_transaction_lock: bool,
    explicit_expected_fencing_token_configured: bool,
) -> dict[str, Any]:
    runner_action = action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS and action != "plan_only"
    lock_provider_action = action in {
        DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION,
        DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION,
    }
    required = bool(
        explicit_expected_fencing_token_configured
        or (require_transaction_lock and runner_action)
        or lock_provider_action
    )
    evidence_present = bool(lock_lifecycle_plan.get("fencing_token_present"))
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION:
        status = "step_produces_fencing_evidence"
    elif explicit_expected_fencing_token_configured:
        status = "explicit_expected_fencing_token_configured"
    elif preceding_fencing_actions:
        status = "planned_predecessor_fencing_evidence"
    elif evidence_present:
        status = "provider_projection_or_journal_fencing_evidence_present"
    elif required:
        status = "runtime_fencing_review_required"
    else:
        status = "not_required"
    return {
        "required": required,
        "status": status,
        "explicit_expected_fencing_token_configured": explicit_expected_fencing_token_configured,
        "fencing_token_evidence_present": evidence_present,
        "lease_renewal_status": lease_renewal_plan.get("status"),
        "planned_predecessor_fencing_actions": preceding_fencing_actions,
        "runtime_gate_must_revalidate": required,
    }


def _recovery_preflight_dependency(
    *,
    action: str,
    predecessor_actions: list[str],
    journal_completed_actions: set[str],
) -> dict[str, Any]:
    required = action in {"apply_backend_manifest_recovery", "commit_cross_run_transaction"}
    if not required:
        status = "not_required"
    elif "preflight_backend_manifest_recovery" in journal_completed_actions:
        status = "journal_completed_recovery_preflight"
    elif "preflight_backend_manifest_recovery" in predecessor_actions:
        status = "planned_predecessor_recovery_preflight"
    else:
        status = "runtime_recovery_preflight_artifact_review_required"
    return {
        "required": required,
        "status": status,
        "runtime_gate_must_revalidate": required,
    }


def _runtime_gate_checks_for_step(action: str) -> list[str]:
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION:
        return ["provider_acquire_lock_contract_checks"]
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION:
        return ["provider_lock_owner_and_fencing_checks", "provider_lease_renewal_checks"]
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION:
        return ["provider_lock_owner_and_fencing_checks", "provider_release_approval_checks"]
    if action == "preflight_backend_manifest_recovery":
        return ["transaction_journal_and_manifest_digest_checks", "rollback_checkpoint_evidence_checks_if_mutated"]
    if action == "apply_backend_manifest_recovery":
        return ["recovery_preflight_artifact_checks", "rollback_checkpoint_and_manifest_digest_checks", "transaction_lock_and_fencing_checks_if_configured"]
    if action == "commit_cross_run_transaction":
        return ["recovery_preflight_artifact_checks", "manifest_digest_and_transaction_id_checks", "transaction_lock_and_fencing_checks_if_configured"]
    return ["supported_step_runtime_checks"]


def _workflow_step_dependency_summary(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "step_count": len(contexts),
        "approval_required_step_count": sum(1 for item in contexts if item.get("approval", {}).get("required")),
        "approval_missing_step_count": sum(1 for item in contexts if item.get("approval", {}).get("missing")),
        "journal_replay_step_count": sum(1 for item in contexts if item.get("journal_replay_available")),
        "provider_lock_review_step_count": sum(1 for item in contexts if item.get("provider_lock_dependency", {}).get("required")),
        "fencing_review_step_count": sum(1 for item in contexts if item.get("fencing_dependency", {}).get("required")),
        "recovery_preflight_review_step_count": sum(1 for item in contexts if item.get("recovery_preflight_dependency", {}).get("required")),
        "runtime_gate_review_step_count": sum(1 for item in contexts if item.get("runtime_gate_review_required")),
        "runtime_gate_evidence_missing_step_count": sum(
            1 for item in contexts if item.get("runtime_gate_evidence", {}).get("missing_artifact_keys")
        ),
        "runtime_gate_evidence_malformed_step_count": sum(
            1 for item in contexts if item.get("runtime_gate_evidence", {}).get("malformed_artifact_keys")
        ),
        "runtime_gate_evidence_stale_step_count": sum(
            1 for item in contexts if item.get("runtime_gate_evidence", {}).get("stale_artifact_keys")
        ),
        "runtime_gate_evidence_transaction_mismatch_step_count": sum(
            1 for item in contexts if item.get("runtime_gate_evidence", {}).get("transaction_mismatch_artifact_keys")
        ),
        "side_effects_performed": False,
        "readonly_dependency_metadata_only": True,
    }


def _runtime_gate_evidence_projection(
    *,
    delivery_root: Path,
    backend_manifest_path: Path | None,
    transaction_id: str,
    planned_steps: list[dict[str, Any]],
    created_at: str,
    require_transaction_lock: bool,
    explicit_expected_fencing_token_configured: bool,
) -> dict[str, Any]:
    """Project existing gate artifacts without claiming apply-time validation."""

    planned_actions = {str(step.get("action") or "") for step in planned_steps}
    runner_actions = {"preflight_backend_manifest_recovery", "apply_backend_manifest_recovery", "commit_cross_run_transaction"}
    lock_provider_actions = set(DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS)
    artifacts = [
        _runtime_gate_json_artifact_projection(
            artifact_key="transaction_journal",
            path=delivery_root / "delivery-transaction-journal.json",
            transaction_id=transaction_id,
            transaction_id_fields=("transaction_id",),
            relevant_step_actions=runner_actions,
            planned_actions=planned_actions,
            created_at=created_at,
            summary_fields=(
                "backend_manifest_mutated",
                "backend_manifest_recovered",
                "backend_manifest_rollback_written",
                "cross_run_transaction_committed",
                "external_delivery_performed",
            ),
        ),
        _runtime_gate_file_artifact_projection(
            artifact_key="rollback_checkpoint",
            path=delivery_root / "backend-artifact-manifest.rollback.json",
            relevant_step_actions={"preflight_backend_manifest_recovery", "apply_backend_manifest_recovery"},
            planned_actions=planned_actions,
        ),
        _runtime_gate_json_artifact_projection(
            artifact_key="recovery_preflight",
            path=delivery_root / "backend-artifact-manifest-recovery-preflight.json",
            transaction_id=transaction_id,
            transaction_id_fields=("journal_transaction_id", "expected_recovery_transaction_id"),
            relevant_step_actions={"apply_backend_manifest_recovery", "commit_cross_run_transaction"},
            planned_actions=planned_actions,
            created_at=created_at,
            summary_fields=("status", "recovery_available", "backend_manifest_mutated", "backend_manifest_rollback_written"),
        ),
        _runtime_gate_json_artifact_projection(
            artifact_key="provider_lock_projection",
            path=delivery_root / "delivery-distributed-transaction-lock.json",
            transaction_id=transaction_id,
            transaction_id_fields=("transaction_id",),
            relevant_step_actions=lock_provider_actions | runner_actions,
            planned_actions=planned_actions,
            created_at=created_at,
            lease_field="lease_expires_at",
            summary_fields=("provider_id", "owner", "fencing_token", "lease_expires_at"),
            summary_presence_only_fields=("owner", "fencing_token"),
            required_for_current_plan=bool(
                planned_actions & {DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION}
                or (planned_actions & runner_actions and (require_transaction_lock or explicit_expected_fencing_token_configured))
            ),
        ),
        _runtime_gate_json_artifact_projection(
            artifact_key="local_transaction_lock",
            path=delivery_root / "delivery-transaction-lock.json",
            transaction_id=transaction_id,
            transaction_id_fields=("transaction_id",),
            relevant_step_actions=runner_actions,
            planned_actions=planned_actions,
            created_at=created_at,
            lease_field="lease_expires_at",
            summary_fields=("owner", "resume_token", "lease_expires_at"),
            summary_presence_only_fields=("owner", "resume_token"),
            required_for_current_plan=bool(require_transaction_lock and planned_actions & runner_actions),
        ),
        _runtime_gate_json_artifact_projection(
            artifact_key="terminal_commit_record",
            path=delivery_root / "backend-artifact-manifest-transaction-commit.json",
            transaction_id=transaction_id,
            transaction_id_fields=("source_transaction_id", "expected_commit_transaction_id"),
            relevant_step_actions={"commit_cross_run_transaction"},
            planned_actions=planned_actions,
            created_at=created_at,
            summary_fields=("status", "committed", "cross_run_transaction_committed", "external_delivery_performed"),
            required_for_current_plan=False,
        ),
        _runtime_gate_file_artifact_projection(
            artifact_key="backend_manifest",
            path=backend_manifest_path,
            relevant_step_actions=runner_actions,
            planned_actions=planned_actions,
        ),
    ]
    status_counts = {
        status: sum(1 for artifact in artifacts if artifact.get("status") == status)
        for status in ("observed", "missing", "malformed", "stale")
    }
    mismatch_count = sum(1 for artifact in artifacts if artifact.get("transaction_match") is False)
    missing_required = [
        str(artifact.get("artifact_key"))
        for artifact in artifacts
        if artifact.get("required_for_current_plan") and artifact.get("status") == "missing"
    ]
    if status_counts["malformed"] or status_counts["stale"] or mismatch_count:
        status = "review_required"
    elif status_counts["observed"]:
        status = "evidence_observed"
    else:
        status = "no_artifacts_observed"
    return {
        "enabled": True,
        "status": status,
        "delivery_root": str(delivery_root),
        "transaction_id": transaction_id or None,
        "artifacts": artifacts,
        "summary": {
            "artifact_count": len(artifacts),
            "observed_count": status_counts["observed"],
            "missing_count": status_counts["missing"],
            "malformed_count": status_counts["malformed"],
            "stale_count": status_counts["stale"],
            "transaction_mismatch_count": mismatch_count,
            "missing_required_review_artifact_keys": missing_required,
        },
        "runtime_gate_must_revalidate": True,
        "readonly_artifact_projection_only": True,
        "side_effects_performed": False,
        "provider_contacted": False,
        "artifacts_written": False,
    }


def _runtime_gate_json_artifact_projection(
    *,
    artifact_key: str,
    path: Path,
    transaction_id: str,
    transaction_id_fields: tuple[str, ...],
    relevant_step_actions: set[str],
    planned_actions: set[str],
    created_at: str,
    summary_fields: tuple[str, ...],
    summary_presence_only_fields: tuple[str, ...] = (),
    lease_field: str | None = None,
    required_for_current_plan: bool | None = None,
) -> dict[str, Any]:
    projection = _runtime_gate_file_artifact_projection(
        artifact_key=artifact_key,
        path=path,
        relevant_step_actions=relevant_step_actions,
        planned_actions=planned_actions,
        required_for_current_plan=required_for_current_plan,
    )
    if not projection["exists"]:
        return projection
    payload, load_error = _read_json_object_with_status(path)
    if load_error:
        return {**projection, "status": "malformed", "load_error": load_error}
    transaction_values = [
        str(payload.get(field) or "").strip()
        for field in transaction_id_fields
        if str(payload.get(field) or "").strip()
    ]
    transaction_match = None if not transaction_id or not transaction_values else all(value == transaction_id for value in transaction_values)
    summary: dict[str, Any] = {}
    for field in summary_fields:
        value = payload.get(field)
        summary[field] = bool(value) if field in summary_presence_only_fields else value
    stale = bool(lease_field and payload.get(lease_field) and _iso_datetime_is_expired(payload.get(lease_field), now_iso=created_at))
    return {
        **projection,
        "status": "stale" if stale else "observed",
        "transaction_match": transaction_match,
        "transaction_id_fields_checked": list(transaction_id_fields),
        "lease_stale": stale if lease_field else None,
        "summary": summary,
    }


def _runtime_gate_file_artifact_projection(
    *,
    artifact_key: str,
    path: Path | None,
    relevant_step_actions: set[str],
    planned_actions: set[str],
    required_for_current_plan: bool | None = None,
) -> dict[str, Any]:
    exists = bool(path and path.exists())
    relevant_actions = sorted(relevant_step_actions)
    required = bool(planned_actions & relevant_step_actions) if required_for_current_plan is None else bool(required_for_current_plan)
    return {
        "artifact_key": artifact_key,
        "path": str(path) if path else None,
        "exists": exists,
        "status": "observed" if exists else "missing",
        "digest_sha256": _file_sha256(path) if path and exists else None,
        "relevant_step_actions": relevant_actions,
        "required_for_current_plan": required,
        "runtime_gate_must_revalidate": True,
        "readonly_artifact_projection_only": True,
    }


def _runtime_gate_evidence_for_step(
    *,
    action: str,
    runtime_gate_checks: list[str],
    projection: dict[str, Any],
) -> dict[str, Any]:
    artifacts = [
        artifact
        for artifact in projection.get("artifacts", [])
        if action in artifact.get("relevant_step_actions", [])
    ]
    return {
        "artifact_refs": [
            {
                "artifact_key": artifact.get("artifact_key"),
                "path": artifact.get("path"),
                "status": artifact.get("status"),
                "exists": artifact.get("exists"),
                "transaction_match": artifact.get("transaction_match"),
                "lease_stale": artifact.get("lease_stale"),
                "runtime_gate_must_revalidate": True,
            }
            for artifact in artifacts
        ],
        "observed_artifact_keys": [str(artifact.get("artifact_key")) for artifact in artifacts if artifact.get("status") == "observed"],
        "missing_artifact_keys": [str(artifact.get("artifact_key")) for artifact in artifacts if artifact.get("status") == "missing"],
        "malformed_artifact_keys": [str(artifact.get("artifact_key")) for artifact in artifacts if artifact.get("status") == "malformed"],
        "stale_artifact_keys": [str(artifact.get("artifact_key")) for artifact in artifacts if artifact.get("status") == "stale"],
        "transaction_mismatch_artifact_keys": [
            str(artifact.get("artifact_key")) for artifact in artifacts if artifact.get("transaction_match") is False
        ],
        "runtime_gate_checks": list(runtime_gate_checks),
        "runtime_gate_must_revalidate": bool(runtime_gate_checks),
        "readonly_artifact_projection_only": True,
        "side_effects_performed": False,
    }


def _read_json_object_with_status(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - review metadata must report malformed JSON conservatively.
        return {}, "invalid_json"
    if not isinstance(payload, dict):
        return {}, "json_root_is_not_object"
    return payload, None


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approval_actions_for_step_actions(step_actions: list[str]) -> list[str]:
    approval_actions: list[str] = []
    for step_action in step_actions:
        approval_action = RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION.get(str(step_action))
        if approval_action and approval_action not in approval_actions:
            approval_actions.append(approval_action)
    return approval_actions


def _runner_policy(step: dict[str, Any]) -> dict[str, Any]:
    runner = step.get("runner_execution") if isinstance(step.get("runner_execution"), dict) else {}
    policy = runner.get("side_effect_policy") if isinstance(runner.get("side_effect_policy"), dict) else {}
    return policy


def _lock_policy(step: dict[str, Any]) -> dict[str, Any]:
    operation = step.get("lock_operation") if isinstance(step.get("lock_operation"), dict) else {}
    policy = operation.get("side_effect_policy") if isinstance(operation.get("side_effect_policy"), dict) else {}
    return policy


def _step_renewed_distributed_lock(step: dict[str, Any]) -> bool:
    return _step_managed_distributed_lock(step, flag="lock_renewed", status="renewed")


def _step_managed_distributed_lock(step: dict[str, Any], *, flag: str, status: str) -> bool:
    operation = step.get("lock_operation") if isinstance(step.get("lock_operation"), dict) else {}
    return (
        step.get("action") in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS
        and step.get("status") == status
        and bool(operation.get(flag))
    )


def _fencing_token_propagation_from_lock_step(step: dict[str, Any]) -> dict[str, Any]:
    operation = step.get("lock_operation") if isinstance(step.get("lock_operation"), dict) else {}
    action = str(step.get("action") or "")
    status = str(step.get("status") or "")
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION and status == "released":
        return {
            "clear_token": True,
            "source": f"workflow_step:{action}",
        }
    if action in {DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION} and status in {"acquired", "renewed"}:
        token = str(operation.get("fencing_token") or "").strip()
        if token:
            return {
                "fencing_token": token,
                "source": f"workflow_step:{action}",
                "provider_id": operation.get("provider_id"),
                "lease_expires_at": operation.get("lease_expires_at"),
            }
    return {}


def _journal_fencing_replay_state(
    *,
    entries: list[dict[str, Any]],
    transaction_id: str,
    created_at: str,
) -> dict[str, dict[str, Any]]:
    """Return conservative replay metadata for journaled lock-provider steps.

    The replay state is intentionally scoped to the selected transaction and to
    successful lock-provider lifecycle entries.  It does not re-run provider
    operations and does not make stale or malformed lease evidence usable.
    """

    state: dict[str, dict[str, Any]] = {}
    propagated_token: str | None = None
    propagated_source: str | None = None
    propagated_provider_id: Any = None
    propagated_lease_expires_at: Any = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        action = str(entry.get("action") or "")
        status = str(entry.get("status") or "")
        if action not in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS or status not in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES:
            continue
        entry_transaction_id = str(entry.get("transaction_id") or "").strip()
        if transaction_id and entry_transaction_id and entry_transaction_id != transaction_id:
            continue
        source = f"workflow_journal:{action}"
        if action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION and status == "released":
            propagated_token = None
            propagated_source = None
            propagated_provider_id = None
            propagated_lease_expires_at = None
            state[action] = {
                "clear_token": True,
                "source": source,
                "status": "replayed",
                "entry_status": status,
            }
            continue
        if action in {DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION} and status in {"acquired", "renewed"}:
            token = str(entry.get("lock_fencing_token") or "").strip()
            lease_expires_at = entry.get("lock_lease_expires_at")
            if not token:
                propagated_token = None
                propagated_source = None
                propagated_provider_id = None
                propagated_lease_expires_at = None
                state[action] = {
                    "status": "not_replayed",
                    "reason": "missing_fencing_token",
                    "source": source,
                    "entry_status": status,
                    "lease_expires_at": lease_expires_at,
                }
                continue
            if _iso_datetime_is_expired(lease_expires_at, now_iso=created_at):
                propagated_token = None
                propagated_source = None
                propagated_provider_id = None
                propagated_lease_expires_at = None
                state[action] = {
                    "status": "not_replayed",
                    "reason": "lease_expired_or_malformed",
                    "source": source,
                    "entry_status": status,
                    "lease_expires_at": lease_expires_at,
                }
                continue
            propagated_token = token
            propagated_source = source
            propagated_provider_id = entry.get("lock_provider_id")
            propagated_lease_expires_at = lease_expires_at
            state[action] = {
                "fencing_token": propagated_token,
                "source": propagated_source,
                "provider_id": propagated_provider_id,
                "lease_expires_at": propagated_lease_expires_at,
                "status": "replayed",
                "entry_status": status,
            }
            continue
    if propagated_token:
        state["__current__"] = {
            "fencing_token": propagated_token,
            "source": propagated_source,
            "provider_id": propagated_provider_id,
            "lease_expires_at": propagated_lease_expires_at,
            "status": "replayed",
        }
    return state


def _journal_fencing_replay_for_skipped_step(state: dict[str, dict[str, Any]], *, action: str) -> dict[str, Any]:
    if action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION:
        replay = state.get(action)
        return dict(replay) if isinstance(replay, dict) else {"clear_token": True, "source": f"workflow_journal:{action}", "status": "replayed"}
    if action in {DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION}:
        current = state.get("__current__")
        if isinstance(current, dict):
            return dict(current)
        replay = state.get(action)
        return dict(replay) if isinstance(replay, dict) else {}
    current = state.get("__current__")
    return dict(current) if isinstance(current, dict) else {}


def _journal_replay_state(*, entries: list[dict[str, Any]], transaction_id: str) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        action = str(entry.get("action") or "")
        status = str(entry.get("status") or "")
        if action not in SUPPORTED_DELIVERY_RESUME_WORKFLOW_STEP_ACTIONS or status not in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES:
            continue
        entry_transaction_id = str(entry.get("transaction_id") or "").strip()
        if transaction_id and entry_transaction_id and entry_transaction_id != transaction_id:
            continue
        state[action] = _journal_replay_entry_summary(entry)
    return state


def _journal_replay_for_skipped_step(state: dict[str, dict[str, Any]], *, action: str) -> dict[str, Any]:
    replay = state.get(action)
    return dict(replay) if isinstance(replay, dict) else {}


def _journal_replay_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    policy = entry.get("side_effect_policy") if isinstance(entry.get("side_effect_policy"), dict) else {}
    return {
        "status": "replayed",
        "source": "workflow_journal",
        "workflow_id": entry.get("workflow_id"),
        "order": entry.get("order"),
        "action": entry.get("action"),
        "approval_action": entry.get("approval_action"),
        "entry_status": entry.get("status"),
        "transaction_id": entry.get("transaction_id"),
        "runner_status": entry.get("runner_status"),
        "lock_status": entry.get("lock_status"),
        "lock_provider_id": entry.get("lock_provider_id"),
        "lock_fencing_token": entry.get("lock_fencing_token"),
        "lock_lease_expires_at": entry.get("lock_lease_expires_at"),
        "transition_status": entry.get("transition_status"),
        "created_at": entry.get("created_at"),
        "side_effect_policy": dict(policy),
        "side_effects_replayed": False,
        "readonly_replay_metadata_only": True,
    }


def _lock_lifecycle_plan(
    *,
    delivery_root: Path,
    existing_entries: list[dict[str, Any]],
    resume_plan: dict[str, Any],
    transaction_id: str,
    created_at: str,
    lease_renewal_plan: dict[str, Any],
) -> dict[str, Any]:
    evidence = _lock_lifecycle_evidence(
        delivery_root=delivery_root,
        existing_entries=existing_entries,
        transaction_id=transaction_id,
        created_at=created_at,
    )
    default_actions = _default_step_actions(resume_plan)
    resume_status = str(resume_plan.get("status") or "")
    has_runner_work = any(action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS and action != "plan_only" for action in default_actions)
    provider_lock_evidence_present = bool(evidence.get("provider_lock_evidence_present"))
    terminal_with_lock = resume_status == "terminal" and provider_lock_evidence_present
    should_acquire = bool(has_runner_work and not provider_lock_evidence_present and resume_status not in {"terminal", "no_transaction", "blocked"})
    should_release = bool(terminal_with_lock)
    prepend_step_actions = [DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION] if should_acquire else []
    append_step_actions = [DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION] if should_release else []
    if should_acquire:
        status = "lifecycle_action_recommended"
        reason = "provider_lock_missing_for_reviewed_workflow"
    elif should_release:
        status = "lifecycle_action_recommended"
        reason = "terminal_transaction_has_provider_lock_evidence"
    elif evidence.get("active_lock_evidence"):
        status = "not_required"
        reason = "provider_lock_evidence_present"
    else:
        status = "not_required"
        reason = "no_lifecycle_action_required"
    return {
        "enabled": True,
        "status": status,
        "reason": reason,
        "source": evidence.get("source"),
        "provider_id": evidence.get("provider_id"),
        "transaction_id": evidence.get("transaction_id") or None,
        "owner": evidence.get("owner"),
        "fencing_token_present": bool(evidence.get("fencing_token")),
        "lease_expires_at": evidence.get("lease_expires_at"),
        "lease_stale": evidence.get("lease_stale"),
        "active_lock_evidence": bool(evidence.get("active_lock_evidence")),
        "provider_lock_evidence_present": provider_lock_evidence_present,
        "default_step_actions": default_actions,
        "prepend_step_actions": prepend_step_actions,
        "append_step_actions": append_step_actions,
        "recommended_step_actions": [*prepend_step_actions, *append_step_actions],
        "requires_review_approval_actions": [
            RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION[action] for action in [*prepend_step_actions, *append_step_actions]
        ],
        "lease_renewal_plan_status": lease_renewal_plan.get("status"),
        "dry_run_plan_only": True,
        "automatic_lock_acquire": False,
        "automatic_lock_release": False,
        "automatic_lock_lifecycle": False,
        "starts_daemon": False,
        "stale_takeover": False,
        "requires_review_approval": bool(prepend_step_actions or append_step_actions),
    }


def _lock_lifecycle_evidence(
    *,
    delivery_root: Path,
    existing_entries: list[dict[str, Any]],
    transaction_id: str,
    created_at: str,
) -> dict[str, Any]:
    projection = _lease_candidate_from_projection(
        _read_json_object(delivery_root / "delivery-distributed-transaction-lock.json"),
        transaction_id=transaction_id,
    )
    journal = _lease_candidate_from_journal(existing_entries, transaction_id=transaction_id)
    candidate = projection if projection.get("lease_expires_at") or projection.get("fencing_token") else journal
    lease_expires_at = candidate.get("lease_expires_at")
    lease_stale = _iso_datetime_is_expired(lease_expires_at, now_iso=created_at) if lease_expires_at else False
    evidence_present = bool(candidate.get("fencing_token") or candidate.get("lease_expires_at"))
    active = bool(candidate.get("fencing_token")) and not lease_stale
    return {
        **candidate,
        "lease_stale": lease_stale,
        "provider_lock_evidence_present": evidence_present,
        "active_lock_evidence": active,
    }


def _lease_renewal_plan(
    *,
    delivery_root: Path,
    existing_entries: list[dict[str, Any]],
    transaction_id: str,
    created_at: str,
    warning_seconds: int,
) -> dict[str, Any]:
    projection = _read_json_object(delivery_root / "delivery-distributed-transaction-lock.json")
    projection_candidate = _lease_candidate_from_projection(projection, transaction_id=transaction_id)
    journal_candidate = _lease_candidate_from_journal(existing_entries, transaction_id=transaction_id)
    candidate = projection_candidate if projection_candidate.get("lease_expires_at") else journal_candidate
    lease_expires_at = str(candidate.get("lease_expires_at") or "")
    remaining_seconds = _iso_datetime_remaining_seconds(lease_expires_at, now_iso=created_at) if lease_expires_at else None
    warning_seconds = max(0, int(warning_seconds))
    lease_missing = not bool(lease_expires_at)
    lease_expired = remaining_seconds is not None and remaining_seconds <= 0
    lease_expiring = remaining_seconds is not None and 0 < remaining_seconds <= warning_seconds
    should_plan_renewal = bool(candidate.get("fencing_token")) and (lease_expired or lease_expiring)
    if lease_missing:
        reason = "lease_missing"
    elif lease_expired:
        reason = "lease_expired"
    elif lease_expiring:
        reason = "lease_expiring_soon"
    else:
        reason = "lease_healthy"
    return {
        "enabled": True,
        "status": "renewal_recommended" if should_plan_renewal else "not_required",
        "reason": reason,
        "recommended_step_action": DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION if should_plan_renewal else None,
        "requires_review_approval_action": RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION[DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION] if should_plan_renewal else None,
        "source": candidate.get("source"),
        "provider_id": candidate.get("provider_id"),
        "transaction_id": candidate.get("transaction_id") or None,
        "owner": candidate.get("owner"),
        "fencing_token_present": bool(candidate.get("fencing_token")),
        "lease_expires_at": lease_expires_at or None,
        "remaining_seconds": remaining_seconds,
        "warning_seconds": warning_seconds,
        "dry_run_plan_only": True,
        "automatic_renewal": False,
        "starts_daemon": False,
        "requires_review_approval": bool(should_plan_renewal),
    }


def _lease_candidate_from_projection(payload: dict[str, Any], *, transaction_id: str) -> dict[str, Any]:
    if not payload:
        return {"source": "provider_projection_missing"}
    payload_transaction_id = str(payload.get("transaction_id") or "").strip()
    if transaction_id and payload_transaction_id and payload_transaction_id != transaction_id:
        return {"source": "provider_projection_transaction_mismatch", "transaction_id": payload_transaction_id}
    return {
        "source": "provider_projection",
        "provider_id": payload.get("provider_id"),
        "transaction_id": payload_transaction_id,
        "owner": payload.get("owner"),
        "fencing_token": payload.get("fencing_token"),
        "lease_expires_at": payload.get("lease_expires_at"),
    }


def _lease_candidate_from_journal(entries: list[dict[str, Any]], *, transaction_id: str) -> dict[str, Any]:
    candidate: dict[str, Any] = {"source": "workflow_journal_missing"}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        action = str(entry.get("action") or "")
        status = str(entry.get("status") or "")
        if action not in DELIVERY_RESUME_WORKFLOW_LOCK_PROVIDER_ACTIONS or status not in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES:
            continue
        entry_transaction_id = str(entry.get("transaction_id") or "").strip()
        if transaction_id and entry_transaction_id and entry_transaction_id != transaction_id:
            continue
        if action == DELIVERY_RESUME_WORKFLOW_LOCK_RELEASE_ACTION and status == "released":
            candidate = {
                "source": "workflow_journal_release",
                "transaction_id": entry_transaction_id,
                "provider_id": entry.get("lock_provider_id"),
                "fencing_token": None,
                "lease_expires_at": None,
            }
            continue
        if action in {DELIVERY_RESUME_WORKFLOW_LOCK_ACQUIRE_ACTION, DELIVERY_RESUME_WORKFLOW_LOCK_RENEWAL_ACTION} and status in {"acquired", "renewed"}:
            candidate = {
                "source": f"workflow_journal:{action}",
                "transaction_id": entry_transaction_id,
                "provider_id": entry.get("lock_provider_id"),
                "fencing_token": entry.get("lock_fencing_token"),
                "lease_expires_at": entry.get("lock_lease_expires_at"),
            }
    return candidate


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - planning treats malformed projection as missing.
        return {}
    return payload if isinstance(payload, dict) else {}


def _iso_datetime_is_expired(value: Any, *, now_iso: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    try:
        expires_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
        now = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return expires_at <= now


def _iso_datetime_remaining_seconds(value: Any, *, now_iso: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        expires_at = datetime.fromisoformat(text.replace("Z", "+00:00"))
        now = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return int((expires_at - now).total_seconds())


def _fencing_propagation_metadata(
    *,
    expected_fencing_token: str | None,
    propagated_fencing_token: str | None,
    propagated_fencing_source: str | None,
    explicit_expected_fencing_token: str | None,
) -> dict[str, Any]:
    return {
        "workflow_fencing_token_propagation": True,
        "workflow_fencing_token_propagated": bool(propagated_fencing_token and not explicit_expected_fencing_token),
        "workflow_fencing_token_source": "config.expected_transaction_lock_fencing_token" if explicit_expected_fencing_token else propagated_fencing_source,
        "workflow_expected_transaction_lock_fencing_token": expected_fencing_token,
        "workflow_explicit_expected_transaction_lock_fencing_token": explicit_expected_fencing_token,
    }


def _approval_summary(*, ledger_path: Path, transaction_id: str | None, step_actions: list[str], expected_decision: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "ledger_path": str(ledger_path),
        "ledger_exists": ledger_path.exists(),
        "expected_subject_id": transaction_id,
        "expected_decision": expected_decision,
        "expected_step_actions": step_actions,
        "matched_step_actions": [],
        "missing_step_actions": list(step_actions),
        "matched_entries": [],
        "entry_count": 0,
        "load_error": None,
    }
    if not step_actions:
        summary["missing_step_actions"] = []
        return summary
    if not ledger_path.exists():
        return summary
    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - returned as structured audit info.
        summary["load_error"] = str(exc)
        return summary
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        summary["load_error"] = "approval ledger payload must contain entries list"
        return summary
    summary["entry_count"] = len(entries)
    matched_actions: list[str] = []
    matched_entries: list[dict[str, Any]] = []
    for action in step_actions:
        approval_action = RESUME_WORKFLOW_ACTION_TO_APPROVAL_ACTION.get(action)
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            if transaction_id and entry.get("subject_id") != transaction_id:
                continue
            if approval_action and entry.get("action") != approval_action:
                continue
            if entry.get("decision") != expected_decision:
                continue
            if entry.get("status") != "written":
                continue
            matched_actions.append(action)
            matched_entries.append(_approval_entry_summary(entry, step_action=action))
            break
    summary["matched_step_actions"] = matched_actions
    summary["missing_step_actions"] = [action for action in step_actions if action not in set(matched_actions)]
    summary["matched_entries"] = matched_entries
    return summary


def _approval_entry_summary(entry: dict[str, Any], *, step_action: str) -> dict[str, Any]:
    return {
        "step_action": step_action,
        "approval_id": entry.get("approval_id"),
        "subject_id": entry.get("subject_id"),
        "action": entry.get("action"),
        "decision": entry.get("decision"),
        "status": entry.get("status"),
        "reviewer": entry.get("reviewer"),
        "reason": entry.get("reason"),
        "created_at": entry.get("created_at"),
    }


def _read_workflow_journal_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - malformed journals are treated as empty for baseline resume-of-resume.
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else None
    return [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def _journal_summary(entries: list[dict[str, Any]], *, transaction_id: str = "") -> dict[str, Any]:
    completed_actions = []
    for entry in entries:
        action = str(entry.get("action") or "")
        status = str(entry.get("status") or "")
        entry_transaction_id = str(entry.get("transaction_id") or "").strip()
        if transaction_id and entry_transaction_id and entry_transaction_id != transaction_id:
            continue
        if action and status in _DELIVERY_RESUME_WORKFLOW_SUCCESS_STATUSES and action not in completed_actions:
            completed_actions.append(action)
    return {
        "entry_count": len(entries),
        "completed_actions": completed_actions,
        "completed_step_count": len(completed_actions),
        "malformed_entries_ignored": False,
    }


def _append_workflow_journal(*, path: Path, workflow_id: str, created_at: str, previous_entries: list[dict[str, Any]], new_entries: list[dict[str, Any]]) -> None:
    sanitized_entries = [*_sanitize_existing_entries(previous_entries), *[_journal_entry_from_step(step) for step in new_entries]]
    _write_json(
        path,
        {
            "version": "2026-06-01.delivery-resume-workflow-journal-v1",
            "workflow_id": workflow_id,
            "entries": sanitized_entries,
            "entry_count": len(sanitized_entries),
            "updated_at": created_at,
        },
    )


def _sanitize_existing_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def _journal_entry_from_step(step: dict[str, Any]) -> dict[str, Any]:
    runner = step.get("runner_execution") if isinstance(step.get("runner_execution"), dict) else {}
    lock_operation = step.get("lock_operation") if isinstance(step.get("lock_operation"), dict) else {}
    fencing_propagation = step.get("fencing_token_propagation") if isinstance(step.get("fencing_token_propagation"), dict) else {}
    return {
        "workflow_id": step.get("workflow_id"),
        "order": step.get("order"),
        "action": step.get("action"),
        "approval_action": step.get("approval_action"),
        "status": step.get("status"),
        "transaction_id": runner.get("transaction_id") or lock_operation.get("transaction_id"),
        "runner_status": runner.get("status"),
        "lock_status": lock_operation.get("status"),
        "lock_provider_id": lock_operation.get("provider_id"),
        "lock_fencing_token": lock_operation.get("fencing_token"),
        "lock_lease_expires_at": lock_operation.get("lease_expires_at"),
        "fencing_token_propagation": fencing_propagation,
        "transition_status": runner.get("transition_execution", {}).get("status") if isinstance(runner.get("transition_execution"), dict) else None,
        "created_at": step.get("created_at"),
        "side_effect_policy": runner.get("side_effect_policy", {}) or lock_operation.get("side_effect_policy", {}),
    }


def _workflow_id(*, created_at: str, delivery_root: Path, transaction_id: str | None, action: str) -> str:
    digest = hashlib.sha256(f"{delivery_root}\0{transaction_id or ''}\0{action}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"delivery-resume-workflow-{digest}"


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
