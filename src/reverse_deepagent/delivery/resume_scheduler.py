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
        existing_journal_summary = _journal_summary(existing_entries)
        planned_steps = self._planned_steps(resume_plan=resume_plan, completed_actions=set(existing_journal_summary["completed_actions"]))
        approval_summary = _approval_summary(
            ledger_path=self.config.resolved_approval_ledger_path(),
            transaction_id=transaction_id,
            step_actions=[str(step["action"]) for step in planned_steps if not step.get("already_completed")],
            expected_decision=self.config.approval_decision,
        )
        checks = self._checks(
            resume_plan=resume_plan,
            planned_steps=planned_steps,
            approval_summary=approval_summary,
            transaction_id=transaction_id,
        )
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        step_results: list[dict[str, Any]] = []
        if not blocking_reasons:
            step_results = self._run_steps(
                workflow_id=workflow_id,
                delivery_root=delivery_root,
                transaction_id=str(transaction_id or ""),
                planned_steps=planned_steps,
                created_at=created_at,
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

    def _planned_steps(self, *, resume_plan: dict[str, Any], completed_actions: set[str]) -> list[dict[str, Any]]:
        actions = list(self.config.step_actions) if self.config.step_actions else _default_step_actions(resume_plan)
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
                "passed": resume_plan.get("status") != "terminal",
                "details": {"resume_plan_status": resume_plan.get("status")},
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
    ) -> list[dict[str, Any]]:
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        results: list[dict[str, Any]] = []
        propagated_fencing_token = str(self.config.expected_transaction_lock_fencing_token or "").strip() or None
        propagated_fencing_source = "config.expected_transaction_lock_fencing_token" if propagated_fencing_token else None
        for step in planned_steps:
            action = str(step.get("action") or "")
            if step.get("already_completed"):
                results.append(
                    {
                        **step,
                        "status": "skipped_completed",
                        "dry_run": dry_run,
                        "workflow_id": workflow_id,
                        "created_at": created_at,
                        "runner_execution": None,
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
    return []


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


def _journal_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    completed_actions = []
    for entry in entries:
        action = str(entry.get("action") or "")
        status = str(entry.get("status") or "")
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
