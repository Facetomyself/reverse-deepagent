from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .inspector import inspect_delivery_transaction_root
from .transitions import DeliveryTransactionTransitionExecutor, DeliveryTransitionExecutorConfig

SUPPORTED_DELIVERY_RECOVERY_ACTIONS: tuple[str, ...] = (
    "plan_recovery",
    "preflight_recovery",
    "apply_recovery",
)


@dataclass(frozen=True)
class DeliveryRecoveryExecutorConfig:
    """Configuration for a conservative delivery recovery workflow executor.

    This executor is intentionally one level above the explicit transition shell:
    it can plan a recovery workflow and, only with explicit approval, orchestrate
    the preflight -> apply recovery sequence.  Low-level digest, journal,
    rollback-checkpoint, and source-manifest checks remain delegated to
    ``LocalDeliveryExecutor`` through ``DeliveryTransactionTransitionExecutor``.
    """

    delivery_root: Path
    transaction_id: str
    action: str = "plan_recovery"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    backend_manifest_path: Path | None = None
    expected_transaction_id: str | None = None
    approve_recovery: bool = False
    require_transaction_lock: bool = False
    transaction_lock_owner: str | None = None
    transaction_lock_lease_seconds: int = 900
    expected_resume_token: str | None = None
    expected_transaction_lock_fencing_token: str | None = None
    write_execution_record: bool = True
    execution_record_name: str = "delivery-recovery-execution.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()

    def resolved_backend_manifest_path(self) -> Path | None:
        if self.backend_manifest_path is None:
            return None
        return self.backend_manifest_path.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryRecoveryExecution:
    transaction_id: str
    action: str
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    execution_record_path: str | None
    before_state: dict[str, Any]
    recovery_plan: dict[str, Any]
    transition_executions: list[dict[str, Any]]
    after_state: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        manifest_recovered = any(
            bool(step.get("execution_result", {}).get("backend_manifest_recovered"))
            for step in self.transition_executions
            if isinstance(step.get("execution_result"), dict)
        )
        return {
            "transaction_id": self.transaction_id,
            "action": self.action,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "execution_record_path": self.execution_record_path,
            "before_state": self.before_state,
            "recovery_plan": self.recovery_plan,
            "transition_executions": self.transition_executions,
            "after_state": self.after_state,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "orchestrates_recovery_transitions": self.action in {"preflight_recovery", "apply_recovery"},
                "files_mutated": bool(manifest_recovered),
                "manifest_recovered": bool(manifest_recovered),
                "transaction_committed": False,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "automatic_recovery": False,
            },
        }


class DeliveryTransactionRecoveryExecutor:
    """Review-gated workflow executor for local delivery transaction recovery."""

    def __init__(self, config: DeliveryRecoveryExecutorConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryRecoveryExecution:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        before_inspection = inspect_delivery_transaction_root(delivery_root).to_dict()
        before_state = before_inspection["state_snapshot"]
        recovery_plan = self._build_recovery_plan(before_inspection)
        checks = self._build_checks(before_state)
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        transition_executions: list[dict[str, Any]] = []
        after_state: dict[str, Any] | None = None
        if not blocking_reasons:
            transition_executions = self._execute_action()
            if transition_executions:
                after_state = inspect_delivery_transaction_root(delivery_root).to_dict()["state_snapshot"]
        status = self._status(blocking_reasons, transition_executions, dry_run)
        execution_record_path = (
            str(delivery_root / self.config.execution_record_name)
            if self.config.write_execution_record and not dry_run and not blocking_reasons and transition_executions
            else None
        )
        execution = DeliveryRecoveryExecution(
            transaction_id=self.config.transaction_id,
            action=self.config.action,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            execution_record_path=execution_record_path,
            before_state=before_state,
            recovery_plan=recovery_plan,
            transition_executions=transition_executions,
            after_state=after_state,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-transaction-recovery-executor",
                "scope": "delivery-transaction-recovery-executor-baseline",
                "supported_actions": list(SUPPORTED_DELIVERY_RECOVERY_ACTIONS),
                "delegates_to_transition_executor": True,
                "automatic_recovery": False,
                "limitations": [
                    "explicit_approval_required_for_apply_recovery",
                    "delegates_low_level_checks_to_local_delivery_executor",
                    "does_not_commit_cross_run_transaction",
                    "does_not_publish_external_delivery",
                    "does_not_implement_cross_run_rollback_state_machine",
                ],
            },
        )
        if execution_record_path:
            _write_json(Path(execution_record_path), execution.to_dict())
        return execution

    def _build_recovery_plan(self, inspection: dict[str, Any]) -> dict[str, Any]:
        state_snapshot = inspection.get("state_snapshot") if isinstance(inspection.get("state_snapshot"), dict) else {}
        transition_plan = inspection.get("transition_plan") if isinstance(inspection.get("transition_plan"), dict) else {}
        steps = [
            {
                "name": "preflight_backend_manifest_recovery",
                "required": True,
                "mode": self.config.mode.value if self.config.action != "plan_recovery" else DeliveryExecutionMode.DRY_RUN.value,
                "side_effect": self.config.mode == DeliveryExecutionMode.APPLY and self.config.action in {"preflight_recovery", "apply_recovery"},
            },
            {
                "name": "apply_backend_manifest_recovery",
                "required": self.config.action == "apply_recovery",
                "mode": self.config.mode.value if self.config.action == "apply_recovery" else DeliveryExecutionMode.DRY_RUN.value,
                "side_effect": self.config.mode == DeliveryExecutionMode.APPLY and self.config.action == "apply_recovery",
                "requires_approval": True,
            },
        ]
        return {
            "source": "delivery-transaction-recovery-executor-baseline",
            "current_state": state_snapshot.get("state"),
            "transition_plan": transition_plan,
            "requested_action": self.config.action,
            "steps": steps,
            "requires_review": True,
            "automatic_recovery": False,
            "external_delivery_performed": False,
            "publishes_externally": False,
        }

    def _build_checks(self, before_state: dict[str, Any]) -> list[dict[str, Any]]:
        action = str(self.config.action or "")
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        apply_recovery = action == "apply_recovery"
        return [
            {
                "name": "recovery_action_is_supported",
                "passed": action in SUPPORTED_DELIVERY_RECOVERY_ACTIONS,
                "details": {"action": action, "supported": list(SUPPORTED_DELIVERY_RECOVERY_ACTIONS)},
            },
            {
                "name": "transaction_state_is_not_blocked",
                "passed": not bool(before_state.get("blocked")),
                "details": {"state": before_state.get("state"), "blocking_reasons": before_state.get("blocking_reasons", [])},
            },
            {
                "name": "external_delivery_not_performed_before_recovery",
                "passed": not bool(before_state.get("flags", {}).get("external_delivery_performed")),
                "details": {"external_delivery_performed": bool(before_state.get("flags", {}).get("external_delivery_performed"))},
            },
            {
                "name": "apply_recovery_requires_explicit_approval",
                "passed": dry_run or not apply_recovery or bool(self.config.approve_recovery),
                "details": {"approve_recovery": bool(self.config.approve_recovery), "mode": self.config.mode.value},
            },
            {
                "name": "apply_recovery_requires_expected_transaction_id",
                "passed": dry_run or not apply_recovery or bool(str(self.config.expected_transaction_id or "").strip()),
                "details": {"expected_transaction_id_configured": bool(str(self.config.expected_transaction_id or "").strip())},
            },
        ]

    def _execute_action(self) -> list[dict[str, Any]]:
        action = str(self.config.action or "")
        if action == "plan_recovery":
            return []
        steps = ["preflight_backend_manifest_recovery"]
        if action == "apply_recovery":
            steps.append("apply_backend_manifest_recovery")
        executions: list[dict[str, Any]] = []
        for step in steps:
            transition = DeliveryTransactionTransitionExecutor(
                DeliveryTransitionExecutorConfig(
                    delivery_root=self.config.delivery_root,
                    transaction_id=self.config.transaction_id if len(steps) == 1 else f"{self.config.transaction_id}-{step}",
                    transition=step,
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
                        "recovery_executor": True,
                        "recovery_action": action,
                        "recovery_step": step,
                    },
                )
            ).execute()
            payload = transition.to_dict()
            executions.append(payload)
            if payload.get("status") == "blocked":
                break
        return executions

    def _status(self, blocking_reasons: list[str], transition_executions: list[dict[str, Any]], dry_run: bool) -> str:
        if blocking_reasons:
            return "blocked"
        if self.config.action == "plan_recovery" or dry_run:
            return "planned"
        if any(item.get("status") == "blocked" for item in transition_executions):
            return "blocked"
        if self.config.action == "preflight_recovery":
            return "preflighted"
        if self.config.action == "apply_recovery" and any(
            bool(item.get("execution_result", {}).get("backend_manifest_recovered"))
            for item in transition_executions
            if isinstance(item.get("execution_result"), dict)
        ):
            return "recovered"
        return "executed"

    def _recommended_actions(self, status: str) -> list[str]:
        if status == "blocked":
            return ["inspect_recovery_checks_and_transaction_state"]
        if status == "planned":
            return ["apply_preflight_recovery_after_review", "apply_recovery_with_explicit_approval_after_preflight"]
        if status == "preflighted":
            return ["review_recovery_preflight_then_apply_recovery_or_commit"]
        if status == "recovered":
            return ["review_recovered_manifest_before_retry_or_commit"]
        return ["review_recovery_execution"]
