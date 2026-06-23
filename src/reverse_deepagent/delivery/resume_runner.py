from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .resume import DeliveryResumePlanner, DeliveryResumePlannerConfig
from .transitions import DeliveryTransactionTransitionExecutor, DeliveryTransitionExecutorConfig

SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS: tuple[str, ...] = (
    "plan_only",
    "preflight_backend_manifest_recovery",
    "apply_backend_manifest_recovery",
    "commit_cross_run_transaction",
)
RESUME_ACTION_TO_APPROVAL_ACTION: dict[str, str] = {
    "preflight_backend_manifest_recovery": "resume_preflight_backend_manifest_recovery",
    "apply_backend_manifest_recovery": "resume_apply_backend_manifest_recovery",
    "commit_cross_run_transaction": "resume_commit_cross_run_transaction",
}


@dataclass(frozen=True)
class DeliveryResumeRunnerConfig:
    """Configuration for the conservative durable delivery resume runner.

    The runner consumes the existing resume planner output and, only with an
    explicit approval ledger entry, delegates one supported transition to the
    existing transition executor.  It does not start new local deliveries,
    publish external delivery, release or acquire distributed locks, choose an
    ambiguous rollback-vs-commit path, or execute physical rollback.
    """

    delivery_root: Path
    transaction_id: str | None = None
    action: str = "plan_only"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    backend_manifest_path: Path | None = None
    expected_transaction_id: str | None = None
    approval_ledger_path: Path | None = None
    approval_subject_id: str | None = None
    approval_action: str | None = None
    approval_decision: str = "approved"
    approval_id: str | None = None
    require_review_approval: bool = True
    require_transaction_lock: bool = False
    transaction_lock_owner: str | None = None
    transaction_lock_lease_seconds: int = 900
    expected_resume_token: str | None = None
    expected_transaction_lock_fencing_token: str | None = None
    write_execution_record: bool = True
    execution_record_name: str = "delivery-resume-execution.json"
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
class DeliveryResumeExecution:
    transaction_id: str | None
    action: str
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    execution_record_path: str | None
    resume_plan: dict[str, Any]
    approval: dict[str, Any]
    transition_execution: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        transition = self.transition_execution if isinstance(self.transition_execution, dict) else {}
        result = transition.get("execution_result") if isinstance(transition.get("execution_result"), dict) else {}
        execution_record_written = bool(self.execution_record_path) and not self.dry_run and self.status in {
            "executed",
            "preflighted",
            "recovered",
            "committed",
            "recorded",
        }
        manifest_recovered = bool(result.get("backend_manifest_recovered"))
        transaction_committed = bool(result.get("cross_run_transaction_committed"))
        files_mutated = bool(result.get("filesystem_artifact_mutated"))
        return {
            "transaction_id": self.transaction_id,
            "action": self.action,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "execution_record_path": self.execution_record_path,
            "resume_plan": self.resume_plan,
            "approval": self.approval,
            "transition_execution": self.transition_execution,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_resume_execution_record": execution_record_written,
                "uses_review_approval_ledger": True,
                "requires_review_approval_for_apply": True,
                "delegates_to_transition_executor": self.action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS and self.action != "plan_only",
                "files_mutated": files_mutated,
                "manifest_recovered": manifest_recovered,
                "transaction_committed": transaction_committed,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "starts_new_local_delivery": False,
                "automatic_resume": False,
                "distributed_lock_acquired": False,
                "distributed_lock_released": False,
                "physical_rollback_executed": False,
            },
        }


class DeliveryResumeRunner:
    """Review-gated runner for one durable delivery resume transition."""

    def __init__(self, config: DeliveryResumeRunnerConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryResumeExecution:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        transaction_id = self.config.transaction_id
        resume_plan = DeliveryResumePlanner(
            DeliveryResumePlannerConfig(
                delivery_root=delivery_root,
                transaction_id=transaction_id,
                mode=DeliveryExecutionMode.DRY_RUN,
                write_resume_plan=False,
                expected_resume_token=self.config.expected_resume_token,
                transaction_lock_owner=self.config.transaction_lock_owner,
                metadata={**self.config.metadata, "resume_runner_preflight": True},
            )
        ).execute().to_dict()
        detected_transaction_id = transaction_id or _first_str(resume_plan.get("transaction_id"))
        approval = self._approval_summary(detected_transaction_id)
        checks = self._checks(resume_plan=resume_plan, approval=approval, transaction_id=detected_transaction_id)
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        transition_execution: dict[str, Any] | None = None
        if not blocking_reasons and self.config.action != "plan_only":
            transition_execution = self._execute_transition(str(detected_transaction_id or ""))
            if transition_execution.get("status") == "blocked":
                blocking_reasons.append("transition_execution_blocked")
        status = self._status(blocking_reasons=blocking_reasons, transition_execution=transition_execution, dry_run=dry_run)
        execution_record_path = (
            str(delivery_root / self.config.execution_record_name)
            if self.config.write_execution_record and not dry_run and status not in {"blocked", "planned"}
            else None
        )
        execution = DeliveryResumeExecution(
            transaction_id=str(detected_transaction_id) if detected_transaction_id else None,
            action=self.config.action,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            execution_record_path=execution_record_path,
            resume_plan=resume_plan,
            approval=approval,
            transition_execution=transition_execution,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status=status, transition_execution=transition_execution),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-resume-runner",
                "scope": "delivery-resume-runner-baseline",
                "supported_actions": list(SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS),
                "approval_ledger_path": str(self.config.resolved_approval_ledger_path()),
                "automatic_resume": False,
                "limitations": [
                    "one_explicit_transition_per_run",
                    "requires_review_approval_ledger_for_apply",
                    "delegates_low_level_checks_to_transition_executor",
                    "does_not_start_new_local_delivery",
                    "does_not_publish_external_delivery",
                    "does_not_release_or_acquire_distributed_locks",
                    "does_not_execute_physical_rollback",
                ],
            },
        )
        if execution_record_path:
            _write_json(Path(execution_record_path), execution.to_dict())
        return execution

    def _checks(self, *, resume_plan: dict[str, Any], approval: dict[str, Any], transaction_id: str | None) -> list[dict[str, Any]]:
        action = str(self.config.action or "")
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        recommended = str(resume_plan.get("recommended_resume_action") or "")
        expected_action = _approval_action_for_runner_action(action, self.config.approval_action)
        return [
            {
                "name": "resume_runner_action_supported",
                "passed": action in SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS,
                "details": {"action": action, "supported": list(SUPPORTED_DELIVERY_RESUME_RUNNER_ACTIONS)},
            },
            {
                "name": "resume_plan_not_blocked",
                "passed": not bool(resume_plan.get("blocking_reasons")),
                "details": {"status": resume_plan.get("status"), "blocking_reasons": resume_plan.get("blocking_reasons", [])},
            },
            {
                "name": "terminal_transactions_are_not_resumed",
                "passed": resume_plan.get("status") != "terminal",
                "details": {"resume_plan_status": resume_plan.get("status")},
            },
            {
                "name": "runner_does_not_start_new_delivery_transactions",
                "passed": action == "plan_only" or recommended != "start_local_delivery_transaction",
                "details": {"recommended_resume_action": recommended, "action": action},
            },
            {
                "name": "apply_requires_explicit_runner_action",
                "passed": dry_run or action != "plan_only",
                "details": {"mode": self.config.mode.value, "action": action},
            },
            {
                "name": "apply_requires_detected_transaction_id",
                "passed": dry_run or bool(str(transaction_id or "").strip()),
                "details": {"transaction_id": transaction_id},
            },
            {
                "name": "apply_requires_review_approval_ledger_entry",
                "passed": dry_run or not self.config.require_review_approval or bool(approval.get("matched")),
                "details": {
                    "required": self.config.require_review_approval,
                    "matched": approval.get("matched"),
                    "expected_subject_id": approval.get("expected_subject_id"),
                    "expected_action": expected_action,
                    "ledger_path": approval.get("ledger_path"),
                },
            },
        ]

    def _approval_summary(self, transaction_id: str | None) -> dict[str, Any]:
        ledger_path = self.config.resolved_approval_ledger_path()
        expected_subject = self.config.approval_subject_id or transaction_id
        expected_action = _approval_action_for_runner_action(self.config.action, self.config.approval_action)
        summary: dict[str, Any] = {
            "ledger_path": str(ledger_path),
            "ledger_exists": ledger_path.exists(),
            "expected_subject_id": expected_subject,
            "expected_action": expected_action,
            "expected_decision": self.config.approval_decision,
            "expected_approval_id": self.config.approval_id,
            "matched": False,
            "matched_entry": None,
            "entry_count": 0,
            "load_error": None,
        }
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
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            if self.config.approval_id and entry.get("approval_id") != self.config.approval_id:
                continue
            if expected_subject and entry.get("subject_id") != expected_subject:
                continue
            if expected_action and entry.get("action") != expected_action:
                continue
            if entry.get("decision") != self.config.approval_decision:
                continue
            if entry.get("status") != "written":
                continue
            summary["matched"] = True
            summary["matched_entry"] = _approval_entry_summary(entry)
            break
        return summary

    def _execute_transition(self, transaction_id: str) -> dict[str, Any]:
        transition = DeliveryTransactionTransitionExecutor(
            DeliveryTransitionExecutorConfig(
                delivery_root=self.config.delivery_root,
                transaction_id=transaction_id,
                transition=self.config.action,
                mode=self.config.mode,
                backend_manifest_path=self.config.backend_manifest_path,
                expected_transaction_id=self.config.expected_transaction_id,
                require_transaction_lock=self.config.require_transaction_lock,
                transaction_lock_owner=self.config.transaction_lock_owner,
                transaction_lock_lease_seconds=self.config.transaction_lock_lease_seconds,
                expected_resume_token=self.config.expected_resume_token,
                expected_transaction_lock_fencing_token=self.config.expected_transaction_lock_fencing_token,
                write_execution_record=False,
                metadata={
                    **self.config.metadata,
                    "resume_runner": True,
                    "resume_runner_action": self.config.action,
                },
            )
        ).execute()
        return transition.to_dict()

    def _status(self, *, blocking_reasons: list[str], transition_execution: dict[str, Any] | None, dry_run: bool) -> str:
        if blocking_reasons:
            return "blocked"
        if dry_run or self.config.action == "plan_only":
            return "planned"
        if not transition_execution:
            return "recorded"
        if transition_execution.get("status") == "blocked":
            return "blocked"
        if self.config.action == "preflight_backend_manifest_recovery":
            return "preflighted"
        result = transition_execution.get("execution_result") if isinstance(transition_execution.get("execution_result"), dict) else {}
        if self.config.action == "apply_backend_manifest_recovery" and result.get("backend_manifest_recovered"):
            return "recovered"
        if self.config.action == "commit_cross_run_transaction" and result.get("cross_run_transaction_committed"):
            return "committed"
        return "executed"

    @staticmethod
    def _recommended_actions(*, status: str, transition_execution: dict[str, Any] | None) -> list[str]:
        if status == "blocked":
            return ["inspect_resume_runner_checks_and_approval_ledger"]
        if status == "planned":
            return ["record_review_approval_then_apply_explicit_resume_runner_action"]
        if transition_execution and transition_execution.get("recommended_actions"):
            return [str(item) for item in transition_execution.get("recommended_actions", [])]
        if status == "preflighted":
            return ["review_recovery_preflight_then_apply_recovery_or_commit"]
        if status == "recovered":
            return ["review_recovered_manifest_before_retry_or_commit"]
        if status == "committed":
            return ["review_committed_transaction_before_external_delivery"]
        return ["review_resume_execution"]


def _approval_action_for_runner_action(action: str, configured: str | None) -> str | None:
    if configured is not None:
        return configured
    return RESUME_ACTION_TO_APPROVAL_ACTION.get(action)


def _approval_entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_id": entry.get("approval_id"),
        "subject_id": entry.get("subject_id"),
        "action": entry.get("action"),
        "decision": entry.get("decision"),
        "status": entry.get("status"),
        "reviewer": entry.get("reviewer"),
        "reason": entry.get("reason"),
        "created_at": entry.get("created_at"),
        "subject_digest_sha256": entry.get("subject_digest_sha256"),
        "expected_subject_digest_sha256": entry.get("expected_subject_digest_sha256"),
    }


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
