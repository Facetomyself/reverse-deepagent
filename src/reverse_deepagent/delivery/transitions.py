from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, DeliveryExecutionResult, DeliveryExecutorConfig, LocalDeliveryExecutor, _write_json
from .inspector import inspect_delivery_transaction_root


SUPPORTED_DELIVERY_TRANSITIONS: tuple[str, ...] = (
    "preflight_backend_manifest_recovery",
    "apply_backend_manifest_recovery",
    "commit_cross_run_transaction",
)


@dataclass(frozen=True)
class DeliveryTransitionExecutorConfig:
    """Configuration for explicit delivery transaction transition execution.

    The transition executor is a conservative orchestration shell over the
    existing local delivery executor.  Dry-run remains read-only; apply mode
    requires an explicit supported transition name and keeps all low-level
    recovery / commit checks inside ``LocalDeliveryExecutor``.
    """

    delivery_root: Path
    transaction_id: str
    transition: str = "auto"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    backend_manifest_path: Path | None = None
    expected_transaction_id: str | None = None
    require_transaction_lock: bool = False
    transaction_lock_owner: str | None = None
    transaction_lock_lease_seconds: int = 900
    expected_resume_token: str | None = None
    expected_transaction_lock_fencing_token: str | None = None
    write_execution_record: bool = True
    execution_record_name: str = "delivery-transition-execution.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()

    def resolved_backend_manifest_path(self) -> Path | None:
        if self.backend_manifest_path is None:
            return None
        return self.backend_manifest_path.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryTransitionExecution:
    transaction_id: str
    requested_transition: str
    resolved_transition: str | None
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    execution_record_path: str | None
    before_state: dict[str, Any]
    transition_plan: dict[str, Any]
    execution_result: dict[str, Any] | None
    after_state: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "requested_transition": self.requested_transition,
            "resolved_transition": self.resolved_transition,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "execution_record_path": self.execution_record_path,
            "before_state": self.before_state,
            "transition_plan": self.transition_plan,
            "execution_result": self.execution_result,
            "after_state": self.after_state,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "files_mutated": bool(self.execution_result and self.execution_result.get("filesystem_artifact_mutated")),
                "manifest_recovered": bool(self.execution_result and self.execution_result.get("backend_manifest_recovered")),
                "transaction_committed": bool(self.execution_result and self.execution_result.get("cross_run_transaction_committed")),
                "external_delivery_performed": False,
                "publishes_externally": False,
            },
        }


class DeliveryTransactionTransitionExecutor:
    """Explicit transition executor for delivery transaction recovery / commit steps."""

    def __init__(self, config: DeliveryTransitionExecutorConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryTransitionExecution:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        inspection_before = inspect_delivery_transaction_root(delivery_root).to_dict()
        before_state = inspection_before["state_snapshot"]
        transition_plan = inspection_before["transition_plan"]
        resolved_transition = self._resolve_transition(transition_plan)
        checks = self._build_checks(resolved_transition, before_state, transition_plan)
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        execution_result: DeliveryExecutionResult | None = None
        after_state: dict[str, Any] | None = None
        if not blocking_reasons:
            execution_result = self._execute_transition(resolved_transition)
            after_state = execution_result.transaction_state.to_dict()
        status = self._status(blocking_reasons, execution_result, dry_run)
        execution_record_path = (
            str(delivery_root / self.config.execution_record_name)
            if self.config.write_execution_record and not dry_run and not blocking_reasons
            else None
        )
        execution = DeliveryTransitionExecution(
            transaction_id=self.config.transaction_id,
            requested_transition=self.config.transition,
            resolved_transition=resolved_transition,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            execution_record_path=execution_record_path,
            before_state=before_state,
            transition_plan=transition_plan,
            execution_result=execution_result.to_dict() if execution_result else None,
            after_state=after_state,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status, resolved_transition, execution_result),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-transaction-transition-executor",
                "scope": "delivery-transaction-transition-executor-baseline",
                "supported_transitions": list(SUPPORTED_DELIVERY_TRANSITIONS),
                "automatic_transition_execution": False,
                "limitations": [
                    "explicit_transition_only_for_apply",
                    "delegates_to_local_delivery_executor_checks",
                    "does_not_publish_external_delivery",
                    "does_not_select_ambiguous_recovery_or_commit_path",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
        )
        if execution_record_path:
            _write_json(Path(execution_record_path), execution.to_dict())
        return execution

    def _resolve_transition(self, transition_plan: dict[str, Any]) -> str | None:
        requested = str(self.config.transition or "").strip()
        if requested == "auto":
            return str(transition_plan.get("recommended_transition") or "")
        return requested

    def _build_checks(
        self,
        resolved_transition: str | None,
        before_state: dict[str, Any],
        transition_plan: dict[str, Any],
    ) -> list[dict[str, Any]]:
        requested = str(self.config.transition or "")
        blocked = bool(before_state.get("blocked"))
        recommended = str(transition_plan.get("recommended_transition") or "")
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        return [
            {
                "name": "transition_is_supported",
                "passed": bool(resolved_transition in SUPPORTED_DELIVERY_TRANSITIONS),
                "details": {"resolved_transition": resolved_transition, "supported": list(SUPPORTED_DELIVERY_TRANSITIONS)},
            },
            {
                "name": "transaction_state_is_not_blocked",
                "passed": not blocked,
                "details": {"state": before_state.get("state"), "blocking_reasons": before_state.get("blocking_reasons", [])},
            },
            {
                "name": "apply_requires_explicit_transition",
                "passed": dry_run or requested != "auto",
                "details": {"requested_transition": requested, "mode": self.config.mode.value},
            },
            {
                "name": "ambiguous_transition_requires_explicit_selection",
                "passed": resolved_transition != "apply_recovery_or_commit_after_review",
                "details": {"recommended_transition": recommended},
            },
            {
                "name": "external_delivery_not_performed_before_transition",
                "passed": not bool(before_state.get("flags", {}).get("external_delivery_performed")),
                "details": {"external_delivery_performed": bool(before_state.get("flags", {}).get("external_delivery_performed"))},
            },
        ]

    def _execute_transition(self, transition: str | None) -> DeliveryExecutionResult:
        config_kwargs: dict[str, Any] = {
            "delivery_root": self.config.delivery_root,
            "transaction_id": self.config.transaction_id,
            "mode": self.config.mode,
            "backend_manifest_path": self.config.backend_manifest_path,
            "require_transaction_lock": self.config.require_transaction_lock,
            "transaction_lock_owner": self.config.transaction_lock_owner,
            "transaction_lock_lease_seconds": self.config.transaction_lock_lease_seconds,
            "expected_resume_token": self.config.expected_resume_token,
            "expected_transaction_lock_fencing_token": self.config.expected_transaction_lock_fencing_token,
            "metadata": {
                **self.config.metadata,
                "transition_executor": True,
                "requested_transition": self.config.transition,
                "resolved_transition": transition,
            },
        }
        if transition == "preflight_backend_manifest_recovery":
            config_kwargs["preflight_backend_manifest_recovery"] = True
            config_kwargs["expected_recovery_transaction_id"] = self.config.expected_transaction_id
        elif transition == "apply_backend_manifest_recovery":
            config_kwargs["apply_backend_manifest_recovery"] = True
            config_kwargs["expected_recovery_transaction_id"] = self.config.expected_transaction_id
        elif transition == "commit_cross_run_transaction":
            config_kwargs["commit_cross_run_transaction"] = True
            config_kwargs["expected_commit_transaction_id"] = self.config.expected_transaction_id
        else:  # pragma: no cover - guarded by checks.
            raise ValueError(f"Unsupported delivery transition: {transition!r}")
        return LocalDeliveryExecutor(DeliveryExecutorConfig(**config_kwargs)).execute([])

    @staticmethod
    def _status(
        blocking_reasons: list[str],
        execution_result: DeliveryExecutionResult | None,
        dry_run: bool,
    ) -> str:
        if blocking_reasons:
            return "blocked"
        if execution_result is None:
            return "planned" if dry_run else "skipped"
        if dry_run:
            return "planned"
        if execution_result.status in {"blocked", "failed"} or execution_result.errors:
            return "blocked"
        return "executed"

    @staticmethod
    def _recommended_actions(
        status: str,
        resolved_transition: str | None,
        execution_result: DeliveryExecutionResult | None,
    ) -> list[str]:
        if status == "blocked":
            return ["inspect_transition_checks_and_transaction_state"]
        if status == "planned":
            return [f"apply_explicit_{resolved_transition}_after_review"] if resolved_transition else ["select_supported_transition"]
        if execution_result:
            return [execution_result.next_action]
        return ["review_transition_execution"]
