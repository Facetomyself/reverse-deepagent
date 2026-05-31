from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .inspector import inspect_delivery_transaction_root


@dataclass(frozen=True)
class DeliveryRollbackStateWriterConfig:
    """Configuration for writing a durable rollback-state audit artifact.

    The writer is deliberately narrower than a rollback executor.  It only
    persists the read-only rollback state derived from existing delivery
    transaction artifacts.  It never restores manifests, commits transactions,
    calls external delivery providers, or acquires transaction locks.
    """

    delivery_root: Path
    transaction_id: str | None = None
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    write_state_record: bool = True
    state_record_name: str = "delivery-rollback-state.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryRollbackStateWrite:
    transaction_id: str | None
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    state_record_path: str | None
    rollback_state: dict[str, Any]
    inspection: dict[str, Any]
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        state_artifact_written = bool(self.state_record_path) and not self.dry_run and self.status.startswith("written")
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "state_record_path": self.state_record_path,
            "rollback_state": self.rollback_state,
            "inspection": self.inspection,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_rollback_state_artifact": state_artifact_written,
                "artifact_record_written": state_artifact_written,
                "delivery_payload_files_mutated": False,
                "manifest_mutated": False,
                "manifest_recovered": False,
                "transaction_committed": False,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "automatic_rollback": False,
                "distributed_lock_acquired": False,
            },
        }


class DeliveryRollbackStateArtifactWriter:
    """Write the read-only rollback state as a durable delivery artifact."""

    def __init__(self, config: DeliveryRollbackStateWriterConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryRollbackStateWrite:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        inspection = inspect_delivery_transaction_root(delivery_root).to_dict()
        rollback_state = inspection["rollback_state"]
        transaction_id = self.config.transaction_id or rollback_state.get("transaction_id")
        checks = self._checks(inspection)
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        status = self._status(dry_run=dry_run, rollback_state=rollback_state, blocking_reasons=blocking_reasons)
        state_record_path = (
            str(delivery_root / self.config.state_record_name)
            if self.config.write_state_record and not dry_run and not blocking_reasons
            else None
        )
        execution = DeliveryRollbackStateWrite(
            transaction_id=str(transaction_id) if transaction_id else None,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            state_record_path=state_record_path,
            rollback_state=rollback_state,
            inspection={
                "version": inspection.get("version"),
                "ok": inspection.get("ok"),
                "missing_artifacts": inspection.get("missing_artifacts", []),
                "load_errors": inspection.get("load_errors", {}),
                "artifact_status": {
                    key: {
                        "path": value.get("path"),
                        "exists": value.get("exists"),
                        "loaded": value.get("loaded"),
                        "error": value.get("error"),
                    }
                    for key, value in inspection.get("artifacts", {}).items()
                    if isinstance(value, dict)
                },
            },
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status, rollback_state, blocking_reasons),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-rollback-state-artifact-writer",
                "scope": "delivery-rollback-state-artifact-writer-baseline",
                "state_record_name": self.config.state_record_name,
                "writes_only_rollback_state_audit_artifact": True,
                "does_not_execute_recovery_or_commit": True,
                "does_not_publish_external_delivery": True,
                "does_not_acquire_distributed_transaction_lock": True,
                "limitations": [
                    "does_not_restore_manifest",
                    "does_not_commit_cross_run_transaction",
                    "does_not_publish_external_delivery",
                    "does_not_execute_physical_rollback",
                    "does_not_implement_resume_semantics",
                ],
            },
        )
        if state_record_path:
            _write_json(Path(state_record_path), execution.to_dict())
        return execution

    def _checks(self, inspection: dict[str, Any]) -> list[dict[str, Any]]:
        load_errors = inspection.get("load_errors", {})
        return [
            {
                "name": "delivery_root_inspected",
                "passed": True,
                "details": {"delivery_root": str(self.config.resolved_delivery_root())},
            },
            {
                "name": "inspection_has_no_load_errors",
                "passed": not bool(load_errors),
                "details": {"load_errors": load_errors},
            },
            {
                "name": "write_state_record_enabled",
                "passed": self.config.mode == DeliveryExecutionMode.DRY_RUN or bool(self.config.write_state_record),
                "details": {"write_state_record": self.config.write_state_record},
            },
        ]

    @staticmethod
    def _status(*, dry_run: bool, rollback_state: dict[str, Any], blocking_reasons: list[str]) -> str:
        if blocking_reasons:
            return "blocked"
        if dry_run:
            return "planned"
        if bool(rollback_state.get("blocked")):
            return "written_blocked_state"
        return "written"

    @staticmethod
    def _recommended_actions(status: str, rollback_state: dict[str, Any], blocking_reasons: list[str]) -> list[str]:
        if blocking_reasons:
            return ["fix_rollback_state_artifact_writer_blockers_before_retry"]
        if status == "planned":
            return ["review_rollback_state_before_apply_write"]
        recommended = str(rollback_state.get("recommended_action") or "review_written_rollback_state_artifact")
        return [recommended, "use_delivery_rollback_state_as_durable_input_for_reviewed_executor"]
