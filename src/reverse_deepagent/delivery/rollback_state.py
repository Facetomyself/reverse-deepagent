from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .state_machine import DeliveryTransactionSnapshot, evaluate_delivery_transaction_state


class DeliveryRollbackPhase(str, Enum):
    """Cross-run rollback workflow phases derived from delivery artifacts.

    The rollback state machine is intentionally read-only.  It consolidates the
    already-written transaction journal, recovery preflight, recovery result,
    commit record, external delivery result, and idempotency guard into a single
    workflow view so callers can decide which explicit executor action should be
    run next.
    """

    NO_TRANSACTION = "no_transaction"
    LOCAL_DELIVERY_APPLIED = "local_delivery_applied"
    ROLLBACK_PREFLIGHT_REQUIRED = "rollback_preflight_required"
    ROLLBACK_DECISION_REQUIRED = "rollback_decision_required"
    ROLLBACK_APPLIED = "rollback_applied"
    COMMITTED = "committed"
    EXTERNAL_DELIVERY_PERFORMED = "external_delivery_performed"
    DUPLICATE_TERMINAL_ACTION_BLOCKED = "duplicate_terminal_action_blocked"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DeliveryRollbackTransition:
    name: str
    requires_review: bool
    side_effect: bool
    executor: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requires_review": self.requires_review,
            "side_effect": self.side_effect,
            "executor": self.executor,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class DeliveryRollbackState:
    transaction_id: str | None
    phase: DeliveryRollbackPhase
    status: str
    terminal: bool
    blocked: bool
    recommended_action: str
    allowed_transitions: list[DeliveryRollbackTransition]
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    evidence_paths: dict[str, str]
    flags: dict[str, bool]
    transaction_state: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    source: str = "delivery-cross-run-rollback-state-machine-baseline"

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "phase": self.phase.value,
            "status": self.status,
            "terminal": self.terminal,
            "blocked": self.blocked,
            "recommended_action": self.recommended_action,
            "allowed_transitions": [item.to_dict() for item in self.allowed_transitions],
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "evidence_paths": self.evidence_paths,
            "flags": self.flags,
            "transaction_state": self.transaction_state,
            "notes": self.notes,
            "source": self.source,
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "manifest_mutated": False,
                "external_delivery_performed": False,
                "transaction_committed": False,
                "automatic_rollback": False,
            },
        }


def evaluate_delivery_rollback_state(record: Mapping[str, Any] | None) -> DeliveryRollbackState:
    """Return a read-only cross-run rollback phase for standard delivery artifacts."""

    payload = dict(record or {})
    snapshot = evaluate_delivery_transaction_state(payload)
    flags = dict(snapshot.flags)
    evidence_paths = dict(snapshot.evidence_paths)
    checks = _checks(snapshot)
    blocking_reasons = [check["name"] for check in checks if not check["passed"]]
    phase = _phase(snapshot, blocking_reasons)
    transitions = _allowed_transitions(phase, flags)
    status = _status(phase, blocking_reasons)
    recommended_action = _recommended_action(phase, transitions)
    terminal = phase in {
        DeliveryRollbackPhase.COMMITTED,
        DeliveryRollbackPhase.EXTERNAL_DELIVERY_PERFORMED,
        DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED,
    }
    notes = [
        "read_only_cross_run_rollback_state_machine_baseline",
        "does_not_execute_recovery_or_commit",
        "does_not_publish_external_delivery",
        "does_not_acquire_distributed_transaction_lock",
    ]
    if phase == DeliveryRollbackPhase.ROLLBACK_DECISION_REQUIRED:
        notes.append("reviewer_must_choose_recovery_or_commit_path")
    if phase == DeliveryRollbackPhase.ROLLBACK_APPLIED:
        notes.append("manifest_recovered_from_local_rollback_checkpoint")
    return DeliveryRollbackState(
        transaction_id=snapshot.transaction_id,
        phase=phase,
        status=status,
        terminal=terminal,
        blocked=bool(blocking_reasons) or phase in {DeliveryRollbackPhase.BLOCKED, DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED},
        recommended_action=recommended_action,
        allowed_transitions=transitions,
        checks=checks,
        blocking_reasons=blocking_reasons,
        evidence_paths=evidence_paths,
        flags=flags,
        transaction_state=snapshot.to_dict(),
        notes=notes,
    )


def _checks(snapshot: DeliveryTransactionSnapshot) -> list[dict[str, Any]]:
    flags = snapshot.flags
    return [
        {
            "name": "transaction_identity_available_if_started",
            "passed": True,
            "details": {"transaction_id": snapshot.transaction_id},
        },
        {
            "name": "external_delivery_not_performed_before_local_rollback",
            "passed": not bool(flags.get("external_delivery_performed")),
            "details": {"external_delivery_performed": bool(flags.get("external_delivery_performed"))},
        },
        {
            "name": "terminal_duplicate_guard_not_triggered",
            "passed": not bool(flags.get("transaction_idempotency_guard_triggered")),
            "details": {"transaction_idempotency_guard_triggered": bool(flags.get("transaction_idempotency_guard_triggered"))},
        },
        {
            "name": "transaction_state_not_blocked",
            "passed": not bool(snapshot.blocked),
            "details": {"state": snapshot.state.value, "blocking_reasons": snapshot.blocking_reasons},
        },
    ]


def _phase(snapshot: DeliveryTransactionSnapshot, blocking_reasons: list[str]) -> DeliveryRollbackPhase:
    flags = snapshot.flags
    if flags.get("transaction_idempotency_guard_triggered"):
        return DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED
    if flags.get("external_delivery_performed"):
        return DeliveryRollbackPhase.EXTERNAL_DELIVERY_PERFORMED
    if flags.get("cross_run_transaction_committed"):
        return DeliveryRollbackPhase.COMMITTED
    if snapshot.blocked or blocking_reasons:
        return DeliveryRollbackPhase.BLOCKED
    if flags.get("backend_manifest_recovered"):
        return DeliveryRollbackPhase.ROLLBACK_APPLIED
    if flags.get("backend_manifest_recovery_preflight_passed"):
        return DeliveryRollbackPhase.ROLLBACK_DECISION_REQUIRED
    if flags.get("backend_manifest_mutated") or flags.get("backend_manifest_rollback_written"):
        return DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED
    if flags.get("filesystem_artifact_mutated"):
        return DeliveryRollbackPhase.LOCAL_DELIVERY_APPLIED
    return DeliveryRollbackPhase.NO_TRANSACTION


def _allowed_transitions(phase: DeliveryRollbackPhase, flags: Mapping[str, bool]) -> list[DeliveryRollbackTransition]:
    if phase == DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED:
        return [
            DeliveryRollbackTransition(
                name="preflight_backend_manifest_recovery",
                requires_review=True,
                side_effect=True,
                executor="DeliveryTransactionTransitionExecutor",
                rationale="write recovery preflight review record before choosing rollback or commit",
            )
        ]
    if phase == DeliveryRollbackPhase.ROLLBACK_DECISION_REQUIRED:
        transitions = [
            DeliveryRollbackTransition(
                name="apply_backend_manifest_recovery",
                requires_review=True,
                side_effect=True,
                executor="DeliveryTransactionRecoveryExecutor",
                rationale="restore source backend manifest from rollback checkpoint after explicit approval",
            )
        ]
        if flags.get("backend_manifest_recovery_preflight_passed"):
            transitions.append(
                DeliveryRollbackTransition(
                    name="commit_cross_run_transaction",
                    requires_review=True,
                    side_effect=True,
                    executor="DeliveryTransactionTransitionExecutor",
                    rationale="commit the reviewed mutated manifest transaction instead of rolling it back",
                )
            )
        return transitions
    if phase == DeliveryRollbackPhase.ROLLBACK_APPLIED:
        return [
            DeliveryRollbackTransition(
                name="review_recovered_manifest_before_new_transaction",
                requires_review=True,
                side_effect=False,
                executor="human-review",
                rationale="recovered manifest should be reviewed before a new delivery attempt",
            )
        ]
    if phase == DeliveryRollbackPhase.LOCAL_DELIVERY_APPLIED:
        return [
            DeliveryRollbackTransition(
                name="review_or_commit_manifest_revision",
                requires_review=True,
                side_effect=False,
                executor="human-review",
                rationale="local delivery exists but backend manifest rollback path is not active yet",
            )
        ]
    return []


def _recommended_action(phase: DeliveryRollbackPhase, transitions: list[DeliveryRollbackTransition]) -> str:
    if transitions:
        return transitions[0].name
    return {
        DeliveryRollbackPhase.NO_TRANSACTION: "start_local_delivery_transaction",
        DeliveryRollbackPhase.COMMITTED: "review_committed_transaction_journal",
        DeliveryRollbackPhase.EXTERNAL_DELIVERY_PERFORMED: "review_external_delivery_before_any_local_rollback",
        DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED: "inspect_existing_terminal_transaction_artifact",
        DeliveryRollbackPhase.BLOCKED: "fix_rollback_state_blockers_before_retry",
    }.get(phase, "review_rollback_state")


def _status(phase: DeliveryRollbackPhase, blocking_reasons: list[str]) -> str:
    if phase == DeliveryRollbackPhase.DUPLICATE_TERMINAL_ACTION_BLOCKED:
        return "duplicate_blocked"
    if phase == DeliveryRollbackPhase.EXTERNAL_DELIVERY_PERFORMED:
        return "external_delivery_guarded"
    if blocking_reasons or phase == DeliveryRollbackPhase.BLOCKED:
        return "blocked"
    if phase == DeliveryRollbackPhase.COMMITTED:
        return "committed"
    if phase == DeliveryRollbackPhase.ROLLBACK_APPLIED:
        return "recovered"
    if phase == DeliveryRollbackPhase.ROLLBACK_DECISION_REQUIRED:
        return "awaiting_reviewer_decision"
    if phase == DeliveryRollbackPhase.ROLLBACK_PREFLIGHT_REQUIRED:
        return "preflight_required"
    if phase == DeliveryRollbackPhase.LOCAL_DELIVERY_APPLIED:
        return "local_delivery_applied"
    return "not_started"
