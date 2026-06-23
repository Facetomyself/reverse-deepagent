from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .executors import DeliveryExecutionMode, _write_json
from .inspector import DELIVERY_TRANSACTION_ARTIFACT_NAMES, inspect_delivery_transaction_root

SUPPORTED_DELIVERY_RESUME_ACTIONS: tuple[str, ...] = ("plan_resume", "write_resume_plan")


@dataclass(frozen=True)
class DeliveryResumePlannerConfig:
    """Configuration for the durable delivery resume planner.

    The planner is deliberately narrower than a resume runner.  It reads the
    delivery root, summarizes transaction / rollback / lock evidence, and can
    optionally persist a reviewable ``delivery-resume-plan.json`` artifact.  It
    never executes transitions, restores manifests, publishes external delivery,
    commits transactions, or acquires / releases locks.
    """

    delivery_root: Path
    transaction_id: str | None = None
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    write_resume_plan: bool = True
    resume_plan_name: str = "delivery-resume-plan.json"
    expected_resume_token: str | None = None
    transaction_lock_owner: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryResumePlan:
    transaction_id: str | None
    status: str
    mode: str
    dry_run: bool
    delivery_root: str
    resume_plan_path: str | None
    inspection: dict[str, Any]
    state_snapshot: dict[str, Any]
    rollback_state: dict[str, Any]
    transition_plan: dict[str, Any]
    lock_summary: dict[str, Any]
    recommended_resume_action: str
    resume_steps: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        resume_plan_written = bool(self.resume_plan_path) and not self.dry_run and self.status.startswith("written")
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "delivery_root": self.delivery_root,
            "resume_plan_path": self.resume_plan_path,
            "inspection": self.inspection,
            "state_snapshot": self.state_snapshot,
            "rollback_state": self.rollback_state,
            "transition_plan": self.transition_plan,
            "lock_summary": self.lock_summary,
            "recommended_resume_action": self.recommended_resume_action,
            "resume_steps": self.resume_steps,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "read_only": self.dry_run,
                "writes_resume_plan_artifact": resume_plan_written,
                "artifact_record_written": resume_plan_written,
                "resume_plan_only": True,
                "automatic_resume": False,
                "delivery_payload_files_mutated": False,
                "files_mutated": False,
                "manifest_mutated": False,
                "manifest_recovered": False,
                "transaction_committed": False,
                "external_delivery_performed": False,
                "publishes_externally": False,
                "distributed_lock_acquired": False,
                "distributed_lock_released": False,
                "does_not_execute_transitions": True,
                "does_not_restore_manifest": True,
                "does_not_commit_transaction": True,
                "does_not_publish_external_delivery": True,
                "does_not_acquire_distributed_lock": True,
            },
        }


class DeliveryResumePlanner:
    """Build a durable, side-effect-safe resume plan for delivery transactions."""

    def __init__(self, config: DeliveryResumePlannerConfig) -> None:
        self.config = config

    def execute(self) -> DeliveryResumePlan:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        dry_run = self.config.mode == DeliveryExecutionMode.DRY_RUN
        inspection = inspect_delivery_transaction_root(delivery_root).to_dict()
        loaded_payload = _load_standard_payloads(delivery_root)
        state_snapshot = inspection["state_snapshot"]
        rollback_state = inspection["rollback_state"]
        transition_plan = inspection["transition_plan"]
        lock_summary = _lock_summary(
            delivery_root=delivery_root,
            loaded_payload=loaded_payload,
            expected_resume_token=self.config.expected_resume_token,
            transaction_lock_owner=self.config.transaction_lock_owner,
        )
        transaction_id = self.config.transaction_id or _first_str(
            state_snapshot.get("transaction_id"),
            rollback_state.get("transaction_id"),
            lock_summary.get("transaction_id"),
        )
        checks = self._checks(
            inspection=inspection,
            state_snapshot=state_snapshot,
            rollback_state=rollback_state,
            lock_summary=lock_summary,
            transaction_id=transaction_id,
        )
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        recommended_action = self._recommended_resume_action(
            state_snapshot=state_snapshot,
            rollback_state=rollback_state,
            transition_plan=transition_plan,
            lock_summary=lock_summary,
            blocking_reasons=blocking_reasons,
        )
        status = self._status(
            dry_run=dry_run,
            state_snapshot=state_snapshot,
            rollback_state=rollback_state,
            lock_summary=lock_summary,
            blocking_reasons=blocking_reasons,
        )
        resume_steps = self._resume_steps(
            recommended_action=recommended_action,
            status=status,
            state_snapshot=state_snapshot,
            rollback_state=rollback_state,
            transition_plan=transition_plan,
            lock_summary=lock_summary,
            blocking_reasons=blocking_reasons,
        )
        recommended_actions = self._recommended_actions(
            status=status,
            recommended_action=recommended_action,
            blocking_reasons=blocking_reasons,
            lock_summary=lock_summary,
        )
        resume_plan_path = (
            str(delivery_root / self.config.resume_plan_name)
            if self.config.write_resume_plan and not dry_run and not blocking_reasons
            else None
        )
        plan = DeliveryResumePlan(
            transaction_id=str(transaction_id) if transaction_id else None,
            status=status,
            mode=self.config.mode.value,
            dry_run=dry_run,
            delivery_root=str(delivery_root),
            resume_plan_path=resume_plan_path,
            inspection=_inspection_summary(inspection),
            state_snapshot=state_snapshot,
            rollback_state=rollback_state,
            transition_plan=transition_plan,
            lock_summary=lock_summary,
            recommended_resume_action=recommended_action,
            resume_steps=resume_steps,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "delivery-resume-planner",
                "scope": "delivery-resume-planner-baseline",
                "resume_plan_name": self.config.resume_plan_name,
                "writes_only_resume_plan_audit_artifact": True,
                "automatic_resume": False,
                "does_not_execute_transitions": True,
                "does_not_restore_manifest": True,
                "does_not_commit_transaction": True,
                "does_not_publish_external_delivery": True,
                "does_not_acquire_or_release_distributed_lock": True,
                "limitations": [
                    "does_not_execute_delivery_transition",
                    "does_not_restore_manifest",
                    "does_not_commit_cross_run_transaction",
                    "does_not_publish_external_delivery",
                    "does_not_acquire_distributed_transaction_lock",
                    "does_not_release_transaction_lock",
                    "does_not_auto_take_over_stale_locks",
                    "does_not_execute_physical_rollback",
                    "planner_only_not_resume_runner",
                ],
            },
        )
        if resume_plan_path:
            _write_json(Path(resume_plan_path), plan.to_dict())
        return plan

    def _checks(
        self,
        *,
        inspection: dict[str, Any],
        state_snapshot: dict[str, Any],
        rollback_state: dict[str, Any],
        lock_summary: dict[str, Any],
        transaction_id: str | None,
    ) -> list[dict[str, Any]]:
        load_errors = inspection.get("load_errors", {})
        config_transaction = self.config.transaction_id
        transaction_matches = not config_transaction or not transaction_id or str(config_transaction) == str(transaction_id)
        lock_blocks = bool(lock_summary.get("blocks_resume"))
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
                "name": "configured_transaction_id_matches_detected_transaction",
                "passed": transaction_matches,
                "details": {"configured_transaction_id": config_transaction, "detected_transaction_id": transaction_id},
            },
            {
                "name": "write_resume_plan_enabled_for_apply",
                "passed": self.config.mode == DeliveryExecutionMode.DRY_RUN or bool(self.config.write_resume_plan),
                "details": {"write_resume_plan": self.config.write_resume_plan, "mode": self.config.mode.value},
            },
            {
                "name": "active_transaction_lock_allows_resume",
                "passed": not lock_blocks,
                "details": lock_summary,
            },
            {
                "name": "transaction_state_not_blocked",
                "passed": not bool(state_snapshot.get("blocked")),
                "details": {
                    "state": state_snapshot.get("state"),
                    "blocking_reasons": state_snapshot.get("blocking_reasons", []),
                },
            },
            {
                "name": "rollback_state_not_blocked",
                "passed": not bool(rollback_state.get("blocked")) or bool(rollback_state.get("terminal")),
                "details": {
                    "phase": rollback_state.get("phase"),
                    "terminal": rollback_state.get("terminal"),
                    "blocking_reasons": rollback_state.get("blocking_reasons", []),
                },
            },
        ]

    @staticmethod
    def _status(
        *,
        dry_run: bool,
        state_snapshot: dict[str, Any],
        rollback_state: dict[str, Any],
        lock_summary: dict[str, Any],
        blocking_reasons: list[str],
    ) -> str:
        if blocking_reasons:
            return "blocked"
        phase = str(rollback_state.get("phase") or "")
        state = str(state_snapshot.get("state") or "")
        if phase == "no_transaction" and state == "planned":
            return "no_transaction"
        if bool(rollback_state.get("terminal")) or state in {"committed", "external_delivered"}:
            return "terminal"
        if phase == "rollback_decision_required" or state in {"manifest_mutated", "recovery_required"}:
            return "review_required" if dry_run else "written_review_required"
        if dry_run:
            return "planned"
        if lock_summary.get("active_lock") and lock_summary.get("resume_allowed"):
            return "written_resume_ready"
        return "written"

    @staticmethod
    def _recommended_resume_action(
        *,
        state_snapshot: dict[str, Any],
        rollback_state: dict[str, Any],
        transition_plan: dict[str, Any],
        lock_summary: dict[str, Any],
        blocking_reasons: list[str],
    ) -> str:
        if blocking_reasons:
            if lock_summary.get("blocks_resume"):
                return str(lock_summary.get("recommended_lock_action") or "review_or_release_delivery_transaction_lock")
            return "manual_review_blocked_resume_plan"
        phase = str(rollback_state.get("phase") or "")
        state = str(state_snapshot.get("state") or "")
        if phase == "no_transaction" and state == "planned":
            return "start_local_delivery_transaction"
        if phase in {"committed", "external_delivery_performed", "duplicate_terminal_action_blocked"} or state in {"committed", "external_delivered"}:
            return "review_terminal_transaction_no_resume"
        if phase == "rollback_preflight_required":
            return "preflight_rollback_after_review"
        if phase == "rollback_decision_required":
            return "choose_rollback_or_commit_after_review"
        if phase == "rollback_applied":
            return "review_recovered_manifest_before_new_transaction"
        transition = str(transition_plan.get("recommended_transition") or "")
        if transition:
            return transition
        return str(rollback_state.get("recommended_action") or state_snapshot.get("recommended_actions", ["review_delivery_transaction_state"])[0])

    @staticmethod
    def _resume_steps(
        *,
        recommended_action: str,
        status: str,
        state_snapshot: dict[str, Any],
        rollback_state: dict[str, Any],
        transition_plan: dict[str, Any],
        lock_summary: dict[str, Any],
        blocking_reasons: list[str],
    ) -> list[dict[str, Any]]:
        if blocking_reasons:
            return [
                {
                    "order": 1,
                    "action": "manual_review_blockers",
                    "executor": "human-review",
                    "side_effect": False,
                    "reasons": blocking_reasons,
                }
            ]
        steps: list[dict[str, Any]] = [
            {
                "order": 1,
                "action": "review_resume_plan",
                "executor": "human-review",
                "side_effect": False,
                "state": state_snapshot.get("state"),
                "rollback_phase": rollback_state.get("phase"),
            }
        ]
        if lock_summary.get("active_lock"):
            steps.append(
                {
                    "order": len(steps) + 1,
                    "action": "reuse_existing_local_lock_with_matching_owner_or_resume_token",
                    "executor": "LocalDeliveryExecutor",
                    "side_effect": False,
                    "lock_owner_matches": lock_summary.get("owner_matches"),
                    "resume_token_matches": lock_summary.get("resume_token_matches"),
                }
            )
        if status == "terminal":
            steps.append(
                {
                    "order": len(steps) + 1,
                    "action": recommended_action,
                    "executor": "human-review",
                    "side_effect": False,
                    "terminal": True,
                }
            )
            return steps
        executor = _executor_for_action(recommended_action, transition_plan=transition_plan, rollback_state=rollback_state)
        steps.append(
            {
                "order": len(steps) + 1,
                "action": recommended_action,
                "executor": executor,
                "side_effect": executor not in {"human-review", "DeliveryResumePlanner"},
                "requires_explicit_apply": executor not in {"human-review", "DeliveryResumePlanner"},
                "planner_executes_action": False,
            }
        )
        return steps

    @staticmethod
    def _recommended_actions(
        *,
        status: str,
        recommended_action: str,
        blocking_reasons: list[str],
        lock_summary: dict[str, Any],
    ) -> list[str]:
        if blocking_reasons:
            actions = ["fix_resume_plan_blockers_before_retry"]
            if lock_summary.get("blocks_resume"):
                actions.append(str(lock_summary.get("recommended_lock_action") or "review_or_release_delivery_transaction_lock"))
            return actions
        if status == "no_transaction":
            return ["start_local_delivery_transaction"]
        if status == "terminal":
            return ["review_terminal_transaction_artifacts", "do_not_resume_terminal_delivery_transaction"]
        actions = [recommended_action, "use_this_plan_as_input_to_reviewed_delivery_executor"]
        if status in {"review_required", "written_review_required"}:
            actions.insert(0, "obtain_human_review_decision_before_resume")
        return actions


def _load_standard_payloads(delivery_root: Path) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for key, filename in DELIVERY_TRANSACTION_ARTIFACT_NAMES.items():
        path = delivery_root / filename
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - inspector carries the exact error; planner only needs loaded payloads.
            continue
        if isinstance(payload, dict):
            payloads[key] = payload
    return payloads


def _lock_summary(
    *,
    delivery_root: Path,
    loaded_payload: dict[str, Any],
    expected_resume_token: str | None,
    transaction_lock_owner: str | None,
) -> dict[str, Any]:
    lock_path = delivery_root / "delivery-transaction-lock.json"
    release_path = delivery_root / "delivery-transaction-lock-release.json"
    lock = loaded_payload.get("transaction_lock") if isinstance(loaded_payload.get("transaction_lock"), dict) else None
    release = loaded_payload.get("transaction_lock_release") if isinstance(loaded_payload.get("transaction_lock_release"), dict) else None
    owner = str(lock.get("owner") or "") if lock else ""
    lock_transaction_id = str(lock.get("transaction_id") or "") if lock else ""
    resume_token = str(lock.get("resume_token") or "") if lock else ""
    lease_expires_at = str(lock.get("lease_expires_at") or "") if lock else ""
    stale = _lease_is_stale(lease_expires_at)
    owner_matches = bool(transaction_lock_owner and owner and transaction_lock_owner == owner)
    token_matches = bool(expected_resume_token and resume_token and expected_resume_token == resume_token)
    active_lock = bool(lock)
    released_without_live_lock = bool(release and release.get("lock_removed") and not active_lock)
    resume_allowed = not active_lock or (not stale and (owner_matches or token_matches))
    blocks_resume = active_lock and not resume_allowed
    if stale:
        recommended_lock_action = "review_or_release_stale_delivery_transaction_lock"
    elif active_lock and not (owner_matches or token_matches):
        recommended_lock_action = "review_or_release_delivery_transaction_lock"
    else:
        recommended_lock_action = "continue_with_reviewed_resume_plan"
    return {
        "lock_path": str(lock_path),
        "lock_exists": lock_path.exists(),
        "lock_loaded": bool(lock),
        "release_path": str(release_path),
        "release_exists": release_path.exists(),
        "release_loaded": bool(release),
        "active_lock": active_lock,
        "released_without_live_lock": released_without_live_lock,
        "transaction_id": lock_transaction_id or None,
        "owner": owner or None,
        "configured_owner": transaction_lock_owner,
        "owner_matches": owner_matches,
        "resume_token_present": bool(resume_token),
        "expected_resume_token_configured": bool(expected_resume_token),
        "resume_token_matches": token_matches,
        "lease_expires_at": lease_expires_at or None,
        "stale_lock_detected": stale,
        "resume_allowed": resume_allowed,
        "blocks_resume": blocks_resume,
        "recommended_lock_action": recommended_lock_action,
        "distributed_lock": False,
        "automatic_stale_takeover": False,
    }


def _lease_is_stale(value: str) -> bool:
    if not value:
        return False
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _inspection_summary(inspection: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": inspection.get("version"),
        "ok": inspection.get("ok"),
        "missing_artifacts": inspection.get("missing_artifacts", []),
        "load_errors": inspection.get("load_errors", {}),
        "artifact_status": {
            key: {
                "path": value.get("path"),
                "exists": value.get("exists"),
                "loaded": value.get("loaded"),
                "keys": value.get("keys", []),
                "error": value.get("error"),
            }
            for key, value in inspection.get("artifacts", {}).items()
            if isinstance(value, dict)
        },
    }


def _executor_for_action(action: str, *, transition_plan: dict[str, Any], rollback_state: dict[str, Any]) -> str:
    if action in {"start_local_delivery_transaction", "apply_local_delivery"}:
        return "LocalDeliveryExecutor"
    if action in {"preflight_rollback_after_review", "choose_rollback_or_commit_after_review"}:
        return "DeliveryRollbackExecutor"
    if action in {"preflight_backend_manifest_recovery", "apply_recovery_or_commit_after_review"}:
        return "DeliveryTransactionRecoveryExecutor"
    if action in {"commit_cross_run_transaction", "review_commit_or_recovery_path"}:
        return "DeliveryTransactionTransitionExecutor"
    transition = str(transition_plan.get("recommended_transition") or "")
    if action == transition and action not in {"no_next_transition", "fix_blocking_reasons"}:
        return "DeliveryTransactionTransitionExecutor"
    if rollback_state.get("allowed_transitions"):
        return str(rollback_state["allowed_transitions"][0].get("executor") or "human-review")
    return "human-review"


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is not None:
            text = str(value)
            if text:
                return text
    return None
