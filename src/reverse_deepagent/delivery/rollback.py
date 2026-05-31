from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .inspector import inspect_delivery_transaction_root
from .rollback_state import DeliveryRollbackPhase
from .rollback_writer import DeliveryRollbackStateArtifactWriter, DeliveryRollbackStateWriterConfig
from .transitions import DeliveryTransactionTransitionExecutor, DeliveryTransitionExecutorConfig

SUPPORTED_DELIVERY_ROLLBACK_ACTIONS: tuple[str, ...] = (
    "plan_rollback",
    "preflight_rollback",
)


@dataclass(frozen=True)
class DeliveryRollbackExecutorConfig:
    """Configuration for a conservative delivery rollback executor baseline.

    This executor does not apply rollback.  It can plan the rollback path and,
    when explicitly requested in apply mode, materialize the rollback-state
    audit artifact and recovery preflight record that a later reviewed physical
    rollback executor can consume.
    """

    delivery_root: Path
    transaction_id: str
    action: str = "plan_rollback"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    backend_manifest_path: Path | None = None
    expected_transaction_id: str | None = None
    write_execution_record: bool = True
    execution_record_name: str = "delivery-rollback-execution.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()

    def resolved_backend_manifest_path(self) -> Path | None:
        if self.backend_manifest_path is None:
            return None
        return self.backend_manifest_path.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryRollbackExecution:
    transaction_id: str
    action: str
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    execution_record_path: str | None
    before_rollback_state: dict[str, Any]
    rollback_plan: dict[str, Any]
    state_write: dict[str, Any] | None
    transition_executions: list[dict[str, Any]]
    after_rollback_state: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        transition_wrote_preflight = any(
            _transition_wrote_recovery_preflight(item) for item in self.transition_executions
        )
        rollback_state_written = bool(
            isinstance(self.state_write, dict)
            and self.state_write.get("side_effect_policy", {}).get("writes_rollback_state_artifact")
        )
        return {
            "transaction_id": self.transaction_id,
            "action": self.action,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "execution_record_path": self.execution_record_path,
            "before_rollback_state": self.before_rollback_state,
            "rollback_plan": self.rollback_plan,
            "state_write": self.state_write,
            "transition_executions": self.transition_executions,
            "after_rollback_state": self.after_rollback_state,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_rollback_state_artifact": rollback_state_written,
                "writes_recovery_preflight": transition_wrote_preflight,
                "files_mutated": False,
                "manifest_mutated": False,
                "manifest_recovered": False,
                "transaction_committed": False,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "physical_rollback_performed": False,
                "automatic_rollback": False,
                "distributed_lock_acquired": False,
            },
        }


class DeliveryRollbackExecutor:
    """Plan and preflight a reviewed delivery rollback workflow."""

    def __init__(self, config: DeliveryRollbackExecutorConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryRollbackExecution:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        before_inspection = inspect_delivery_transaction_root(delivery_root).to_dict()
        before_rollback_state = before_inspection["rollback_state"]
        rollback_plan = self._build_rollback_plan(before_rollback_state)
        checks = self._build_checks(before_inspection, before_rollback_state)
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        state_write: dict[str, Any] | None = None
        transition_executions: list[dict[str, Any]] = []
        after_rollback_state: dict[str, Any] | None = None
        if not blocking_reasons:
            state_write = self._write_state_artifact()
            transition_executions = self._execute_action()
            if state_write or transition_executions:
                after_rollback_state = inspect_delivery_transaction_root(delivery_root).to_dict()["rollback_state"]
        status = self._status(blocking_reasons, transition_executions, dry_run)
        execution_record_path = (
            str(delivery_root / self.config.execution_record_name)
            if self.config.write_execution_record and not dry_run and not blocking_reasons
            else None
        )
        execution = DeliveryRollbackExecution(
            transaction_id=self.config.transaction_id,
            action=self.config.action,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            execution_record_path=execution_record_path,
            before_rollback_state=before_rollback_state,
            rollback_plan=rollback_plan,
            state_write=state_write,
            transition_executions=transition_executions,
            after_rollback_state=after_rollback_state,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-rollback-executor",
                "scope": "delivery-rollback-executor-preflight-baseline",
                "supported_actions": list(SUPPORTED_DELIVERY_ROLLBACK_ACTIONS),
                "delegates_preflight_to_transition_executor": True,
                "automatic_rollback": False,
                "limitations": [
                    "does_not_apply_manifest_recovery",
                    "does_not_commit_cross_run_transaction",
                    "does_not_publish_external_delivery",
                    "does_not_execute_physical_rollback",
                    "does_not_acquire_distributed_transaction_lock",
                    "does_not_implement_resume_semantics",
                ],
            },
        )
        if execution_record_path:
            _write_json(Path(execution_record_path), execution.to_dict())
        return execution

    def _build_rollback_plan(self, rollback_state: dict[str, Any]) -> dict[str, Any]:
        phase = str(rollback_state.get("phase") or "")
        preflight_ready = phase == DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED.value
        steps = [
            {
                "name": "write_delivery_rollback_state",
                "required": True,
                "mode": self.config.mode.value if self.config.action == "preflight_rollback" else DeliveryExecutionMode.DRY_RUN.value,
                "side_effect": self.config.mode == DeliveryExecutionMode.APPLY and self.config.action == "preflight_rollback",
            },
            {
                "name": "preflight_backend_manifest_recovery",
                "required": preflight_ready,
                "mode": self.config.mode.value if self.config.action == "preflight_rollback" else DeliveryExecutionMode.DRY_RUN.value,
                "side_effect": self.config.mode == DeliveryExecutionMode.APPLY and self.config.action == "preflight_rollback",
            },
            {
                "name": "review_rollback_or_commit_decision",
                "required": True,
                "mode": DeliveryExecutionMode.DRY_RUN.value,
                "side_effect": False,
            },
        ]
        return {
            "source": "delivery-rollback-executor-preflight-baseline",
            "current_phase": phase,
            "requested_action": self.config.action,
            "steps": steps,
            "allowed_transitions": rollback_state.get("allowed_transitions", []),
            "requires_review": True,
            "requires_expected_transaction_id_for_apply": True,
            "automatic_rollback": False,
            "physical_rollback_performed": False,
            "external_delivery_performed": False,
            "publishes_externally": False,
        }

    def _build_checks(self, inspection: dict[str, Any], rollback_state: dict[str, Any]) -> list[dict[str, Any]]:
        action = str(self.config.action or "")
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        preflight = action == "preflight_rollback"
        phase = str(rollback_state.get("phase") or "")
        flags = rollback_state.get("flags") if isinstance(rollback_state.get("flags"), dict) else {}
        load_errors = inspection.get("load_errors", {})
        return [
            {
                "name": "rollback_action_is_supported",
                "passed": action in SUPPORTED_DELIVERY_ROLLBACK_ACTIONS,
                "details": {"action": action, "supported": list(SUPPORTED_DELIVERY_ROLLBACK_ACTIONS)},
            },
            {
                "name": "inspection_has_no_load_errors",
                "passed": not bool(load_errors),
                "details": {"load_errors": load_errors},
            },
            {
                "name": "rollback_state_not_terminal",
                "passed": phase not in {
                    DeliveryRollbackPhase.COMMITTED.value,
                    DeliveryRollbackPhase.EXTERNAL_DELIVERY_PERFORMED.value,
                    DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED.value,
                },
                "details": {"phase": phase},
            },
            {
                "name": "rollback_state_not_blocked",
                "passed": not bool(rollback_state.get("blocked")),
                "details": {"phase": phase, "blocking_reasons": rollback_state.get("blocking_reasons", [])},
            },
            {
                "name": "external_delivery_not_performed_before_rollback",
                "passed": not bool(flags.get("external_delivery_performed")),
                "details": {"external_delivery_performed": bool(flags.get("external_delivery_performed"))},
            },
            {
                "name": "terminal_duplicate_guard_not_triggered",
                "passed": not bool(flags.get("transaction_idempotency_guard_triggered")),
                "details": {"transaction_idempotency_guard_triggered": bool(flags.get("transaction_idempotency_guard_triggered"))},
            },
            {
                "name": "preflight_rollback_requires_recoverable_phase",
                "passed": dry_run or not preflight or phase == DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED.value,
                "details": {"phase": phase, "required_phase": DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED.value},
            },
            {
                "name": "preflight_rollback_requires_expected_transaction_id",
                "passed": dry_run or not preflight or bool(str(self.config.expected_transaction_id or "").strip()),
                "details": {"expected_transaction_id_configured": bool(str(self.config.expected_transaction_id or "").strip())},
            },
            {
                "name": "preflight_rollback_requires_backend_manifest_path",
                "passed": dry_run or not preflight or self.config.resolved_backend_manifest_path() is not None,
                "details": {"backend_manifest_path_configured": self.config.resolved_backend_manifest_path() is not None},
            },
        ]

    def _write_state_artifact(self) -> dict[str, Any] | None:
        if self.config.action != "preflight_rollback":
            return None
        state_write = DeliveryRollbackStateArtifactWriter(
            DeliveryRollbackStateWriterConfig(
                delivery_root=self.config.delivery_root,
                transaction_id=self.config.transaction_id,
                mode=self.config.mode,
                metadata={
                    **self.config.metadata,
                    "rollback_executor": True,
                    "rollback_action": self.config.action,
                },
            )
        ).execute()
        return state_write.to_dict()

    def _execute_action(self) -> list[dict[str, Any]]:
        if self.config.action != "preflight_rollback":
            return []
        transition = DeliveryTransactionTransitionExecutor(
            DeliveryTransitionExecutorConfig(
                delivery_root=self.config.delivery_root,
                transaction_id=f"{self.config.transaction_id}-preflight",
                transition="preflight_backend_manifest_recovery",
                mode=self.config.mode,
                backend_manifest_path=self.config.backend_manifest_path,
                expected_transaction_id=self.config.expected_transaction_id,
                write_execution_record=False,
                metadata={
                    **self.config.metadata,
                    "rollback_executor": True,
                    "rollback_action": self.config.action,
                    "rollback_step": "preflight_backend_manifest_recovery",
                },
            )
        ).execute()
        return [transition.to_dict()]

    @staticmethod
    def _status(
        blocking_reasons: list[str],
        transition_executions: list[dict[str, Any]],
        dry_run: bool,
    ) -> str:
        if blocking_reasons:
            return "blocked"
        if dry_run:
            return "planned"
        if any(item.get("status") == "blocked" for item in transition_executions):
            return "blocked"
        if transition_executions:
            return "preflighted"
        return "planned"

    @staticmethod
    def _recommended_actions(status: str) -> list[str]:
        return {
            "blocked": ["fix_delivery_rollback_preflight_blockers_before_retry"],
            "planned": ["review_delivery_rollback_plan_before_preflight"],
            "preflighted": [
                "review_backend_manifest_recovery_preflight",
                "choose_apply_recovery_or_commit_cross_run_transaction_after_review",
            ],
        }.get(status, ["review_delivery_rollback_execution"])


def _transition_wrote_recovery_preflight(transition_execution: dict[str, Any]) -> bool:
    execution_result = transition_execution.get("execution_result")
    if not isinstance(execution_result, dict):
        return False
    preflight = execution_result.get("backend_manifest_recovery_preflight")
    return bool(isinstance(preflight, dict) and preflight.get("status") in {"ready_for_review", "no_recovery_required", "passed"})
