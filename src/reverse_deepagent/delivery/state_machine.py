from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeliveryTransactionState(str, Enum):
    """Coarse-grained local delivery transaction state.

    This is a read-only state model over the existing delivery journal / result
    artifacts.  It does not execute transitions, publish externally, recover
    manifests, or mutate files by itself.
    """

    PLANNED = "planned"
    LOCAL_APPLIED = "local_applied"
    MANIFEST_REVISION_COMMITTED = "manifest_revision_committed"
    MANIFEST_PATCH_WRITTEN = "manifest_patch_written"
    MANIFEST_PREFLIGHT_PASSED = "manifest_preflight_passed"
    MANIFEST_MUTATED = "manifest_mutated"
    RECOVERY_REQUIRED = "recovery_required"
    RECOVERED = "recovered"
    EXTERNAL_DELIVERY_ATTEMPTED = "external_delivery_attempted"
    EXTERNAL_DELIVERED = "external_delivered"
    COMMITTED = "committed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class DeliveryTransactionSnapshot:
    """Machine-readable transaction state snapshot.

    ``completed_states`` records every milestone proven by the supplied
    artifacts.  ``state`` is the most actionable current state after applying
    blockers and precedence rules.
    """

    transaction_id: str | None
    state: DeliveryTransactionState
    completed_states: list[DeliveryTransactionState]
    blocked: bool
    blocking_reasons: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    evidence_paths: dict[str, str] = field(default_factory=dict)
    flags: dict[str, bool] = field(default_factory=dict)
    source: str = "delivery-transaction-state-machine-baseline"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "state": self.state.value,
            "completed_states": [item.value for item in self.completed_states],
            "blocked": self.blocked,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "evidence_paths": self.evidence_paths,
            "flags": self.flags,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DeliveryTransitionPlan:
    """Read-only next-transition recommendation for a transaction snapshot."""

    current_state: DeliveryTransactionState
    recommended_transition: str
    requires_review: bool
    allowed_without_side_effects: bool
    blocking_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "recommended_transition": self.recommended_transition,
            "requires_review": self.requires_review,
            "allowed_without_side_effects": self.allowed_without_side_effects,
            "blocking_reasons": self.blocking_reasons,
            "notes": self.notes,
        }


def evaluate_delivery_transaction_state(record: Mapping[str, Any] | None) -> DeliveryTransactionSnapshot:
    """Evaluate the current transaction state from a result or journal payload.

    The input may be a full ``DeliveryExecutionResult.to_dict()`` payload, a
    ``DeliveryTransactionJournal.to_dict()`` payload, or a partial artifact map
    containing known nested records such as ``external_delivery_result`` or
    ``backend_manifest_transaction_commit``.
    """

    payload = dict(record or {})
    journal = _mapping(payload.get("transaction_journal")) or payload
    external_result = _mapping(payload.get("external_delivery_result"))
    external_idempotency_ledger = _mapping(payload.get("external_delivery_idempotency_ledger"))
    recovery_preflight = _mapping(payload.get("backend_manifest_recovery_preflight"))
    recovery_result = _mapping(payload.get("backend_manifest_recovery"))
    transaction_commit = _mapping(payload.get("backend_manifest_transaction_commit"))

    transaction_id = _first_str(
        payload.get("transaction_id"),
        journal.get("transaction_id"),
        external_result.get("transaction_id") if external_result else None,
        recovery_result.get("source_transaction_id") if recovery_result else None,
        transaction_commit.get("source_transaction_id") if transaction_commit else None,
    )

    flags = _state_flags(
        payload,
        journal,
        external_result,
        external_idempotency_ledger,
        recovery_preflight,
        recovery_result,
        transaction_commit,
    )
    completed_states = _completed_states(flags)
    blocking_reasons = _blocking_reasons(payload, external_result, recovery_preflight, recovery_result, transaction_commit)
    blocked = bool(blocking_reasons) or bool(payload.get("errors"))
    state = _current_state(flags, completed_states, blocked=blocked)
    evidence_paths = _evidence_paths(
        journal,
        external_result,
        external_idempotency_ledger,
        recovery_preflight,
        recovery_result,
        transaction_commit,
    )
    recommended_actions = _recommended_actions(state, flags, blocking_reasons)
    notes = [
        "read_only_state_model",
        "does_not_execute_delivery_transition",
        "does_not_publish_external_delivery",
        "does_not_restore_or_mutate_manifest",
    ]
    if flags.get("external_delivery_performed"):
        notes.append("external_delivery_performed_by_configured_provider")
    if flags.get("external_delivery_idempotency_ledger_recorded"):
        notes.append("external_delivery_idempotency_ledger_recorded")
    if flags.get("cross_run_transaction_committed"):
        notes.append("local_transaction_journal_marked_committed")
    return DeliveryTransactionSnapshot(
        transaction_id=transaction_id,
        state=state,
        completed_states=completed_states,
        blocked=blocked,
        blocking_reasons=blocking_reasons,
        recommended_actions=recommended_actions,
        evidence_paths=evidence_paths,
        flags=flags,
        notes=notes,
    )


def plan_delivery_transition(snapshot: DeliveryTransactionSnapshot) -> DeliveryTransitionPlan:
    """Return a conservative next-transition recommendation."""

    if snapshot.blocked:
        return DeliveryTransitionPlan(
            current_state=snapshot.state,
            recommended_transition="fix_blocking_reasons",
            requires_review=True,
            allowed_without_side_effects=True,
            blocking_reasons=snapshot.blocking_reasons,
            notes=["resolve blockers before applying, publishing, committing, or recovering"],
        )
    transition_by_state = {
        DeliveryTransactionState.PLANNED: ("apply_local_delivery", True),
        DeliveryTransactionState.LOCAL_APPLIED: ("review_or_commit_manifest_revision", True),
        DeliveryTransactionState.MANIFEST_REVISION_COMMITTED: ("review_backend_manifest_patch_request", True),
        DeliveryTransactionState.MANIFEST_PATCH_WRITTEN: ("preflight_backend_manifest_in_place_mutation", True),
        DeliveryTransactionState.MANIFEST_PREFLIGHT_PASSED: ("approve_backend_manifest_in_place_mutation", True),
        DeliveryTransactionState.MANIFEST_MUTATED: ("review_commit_or_recovery_path", True),
        DeliveryTransactionState.RECOVERY_REQUIRED: ("apply_recovery_or_commit_after_review", True),
        DeliveryTransactionState.RECOVERED: ("review_recovered_manifest_before_retry", True),
        DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED: ("review_external_delivery_result", True),
        DeliveryTransactionState.EXTERNAL_DELIVERED: ("review_external_delivery_before_commit_record", True),
        DeliveryTransactionState.COMMITTED: ("no_next_transition", False),
        DeliveryTransactionState.BLOCKED: ("fix_blocking_reasons", True),
    }
    transition, requires_review = transition_by_state[snapshot.state]
    return DeliveryTransitionPlan(
        current_state=snapshot.state,
        recommended_transition=transition,
        requires_review=requires_review,
        allowed_without_side_effects=transition in {"fix_blocking_reasons", "review_external_delivery_result", "no_next_transition"},
        notes=["transition_plan_only", "caller_must_invoke_explicit_executor_mode_for_side_effects"],
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is not None:
            text = str(value)
            if text:
                return text
    return None


def _state_flags(
    payload: Mapping[str, Any],
    journal: Mapping[str, Any],
    external_result: Mapping[str, Any],
    external_idempotency_ledger: Mapping[str, Any],
    recovery_preflight: Mapping[str, Any],
    recovery_result: Mapping[str, Any],
    transaction_commit: Mapping[str, Any],
) -> dict[str, bool]:
    external_metadata = _mapping(external_result.get("metadata"))
    return {
        "dry_run": _bool(payload, journal, "dry_run"),
        "delivery_allowed": bool(payload.get("delivery_allowed", not payload.get("errors"))),
        "filesystem_artifact_mutated": _bool(payload, journal, "filesystem_artifact_mutated") or _journal_has_delivered_entry(journal),
        "manifest_revision_committed": _bool(payload, journal, "manifest_revision_committed"),
        "backend_manifest_patch_written": _bool(payload, journal, "backend_manifest_patch_written"),
        "backend_manifest_in_place_preflight_passed": _bool(payload, journal, "backend_manifest_in_place_preflight_passed"),
        "backend_manifest_recovery_preflight_passed": _bool(payload, journal, "backend_manifest_recovery_preflight_passed")
        or str(recovery_preflight.get("status") or "") in {"ready_for_review", "no_recovery_required"},
        "backend_manifest_rollback_written": _bool(payload, journal, "backend_manifest_rollback_written"),
        "backend_manifest_mutated": _bool(payload, journal, "backend_manifest_mutated"),
        "backend_manifest_recovered": _bool(payload, journal, "backend_manifest_recovered") or bool(recovery_result.get("recovered")),
        "external_delivery_requested": bool(
            payload.get("external_delivery_result")
            or payload.get("external_delivery_idempotency_ledger")
            or journal.get("external_delivery_result_path")
            or journal.get("external_delivery_idempotency_ledger_path")
            or external_result.get("external_delivery_requested")
        ),
        "external_delivery_attempted": bool(
            payload.get("external_delivery_result")
            or payload.get("external_delivery_idempotency_ledger")
            or journal.get("external_delivery_result_path")
            or journal.get("external_delivery_idempotency_ledger_path")
            or external_result.get("external_delivery_requested")
            or external_idempotency_ledger.get("entry_count")
            or external_metadata.get("request_attempted")
            or external_metadata.get("duplicate_guard_triggered")
        ),
        "external_delivery_performed": _bool(payload, journal, "external_delivery_performed") or bool(external_result.get("external_delivery_performed")),
        "duplicate_guard_triggered": bool(external_metadata.get("duplicate_guard_triggered")),
        "external_delivery_idempotency_ledger_recorded": bool(
            payload.get("external_delivery_idempotency_ledger")
            or journal.get("external_delivery_idempotency_ledger_path")
            or external_idempotency_ledger.get("entry_count")
        ),
        "cross_run_transaction_committed": _bool(payload, journal, "cross_run_transaction_committed") or bool(transaction_commit.get("committed")),
    }


def _bool(payload: Mapping[str, Any], journal: Mapping[str, Any], key: str) -> bool:
    return bool(payload.get(key) or journal.get(key))


def _journal_has_delivered_entry(journal: Mapping[str, Any]) -> bool:
    entries = journal.get("entries")
    if not isinstance(entries, list):
        return False
    return any(isinstance(entry, Mapping) and entry.get("status") == "delivered" for entry in entries)


def _completed_states(flags: Mapping[str, bool]) -> list[DeliveryTransactionState]:
    states = [DeliveryTransactionState.PLANNED]
    ordered_flag_states: tuple[tuple[str, DeliveryTransactionState], ...] = (
        ("filesystem_artifact_mutated", DeliveryTransactionState.LOCAL_APPLIED),
        ("manifest_revision_committed", DeliveryTransactionState.MANIFEST_REVISION_COMMITTED),
        ("backend_manifest_patch_written", DeliveryTransactionState.MANIFEST_PATCH_WRITTEN),
        ("backend_manifest_in_place_preflight_passed", DeliveryTransactionState.MANIFEST_PREFLIGHT_PASSED),
        ("backend_manifest_mutated", DeliveryTransactionState.MANIFEST_MUTATED),
        ("backend_manifest_recovery_preflight_passed", DeliveryTransactionState.RECOVERY_REQUIRED),
        ("backend_manifest_recovered", DeliveryTransactionState.RECOVERED),
        ("external_delivery_attempted", DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED),
        ("external_delivery_performed", DeliveryTransactionState.EXTERNAL_DELIVERED),
        ("cross_run_transaction_committed", DeliveryTransactionState.COMMITTED),
    )
    for flag, state in ordered_flag_states:
        if flags.get(flag):
            states.append(state)
    if (
        flags.get("backend_manifest_mutated")
        and flags.get("backend_manifest_rollback_written")
        and DeliveryTransactionState.RECOVERY_REQUIRED not in states
    ):
        states.append(DeliveryTransactionState.RECOVERY_REQUIRED)
    return states


def _current_state(
    flags: Mapping[str, bool],
    completed_states: list[DeliveryTransactionState],
    *,
    blocked: bool,
) -> DeliveryTransactionState:
    if blocked:
        return DeliveryTransactionState.BLOCKED
    if flags.get("cross_run_transaction_committed"):
        return DeliveryTransactionState.COMMITTED
    if flags.get("external_delivery_performed"):
        return DeliveryTransactionState.EXTERNAL_DELIVERED
    if flags.get("external_delivery_attempted"):
        return DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED
    if flags.get("backend_manifest_recovered"):
        return DeliveryTransactionState.RECOVERED
    if flags.get("backend_manifest_recovery_preflight_passed") or (
        flags.get("backend_manifest_mutated") and flags.get("backend_manifest_rollback_written")
    ):
        return DeliveryTransactionState.RECOVERY_REQUIRED
    if completed_states:
        return completed_states[-1]
    return DeliveryTransactionState.PLANNED


def _blocking_reasons(
    payload: Mapping[str, Any],
    external_result: Mapping[str, Any],
    recovery_preflight: Mapping[str, Any],
    recovery_result: Mapping[str, Any],
    transaction_commit: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    for source in (payload, external_result, recovery_preflight, recovery_result, transaction_commit):
        raw = source.get("blocking_reasons") if isinstance(source, Mapping) else None
        if isinstance(raw, list):
            reasons.extend(str(item) for item in raw if item)
    errors = payload.get("errors")
    if isinstance(errors, list):
        reasons.extend(f"error:{item}" for item in errors if item)
    if str(payload.get("status") or "") == "blocked":
        reasons.append("delivery_result_status_blocked")
    return _dedupe(reasons)


def _evidence_paths(
    journal: Mapping[str, Any],
    external_result: Mapping[str, Any],
    external_idempotency_ledger: Mapping[str, Any],
    recovery_preflight: Mapping[str, Any],
    recovery_result: Mapping[str, Any],
    transaction_commit: Mapping[str, Any],
) -> dict[str, str]:
    candidates = {
        "journal": journal.get("journal_path"),
        "manifest_revision": journal.get("manifest_revision_path"),
        "backend_manifest_mutation": journal.get("backend_manifest_mutation_path"),
        "backend_manifest_patched": journal.get("backend_manifest_patched_path"),
        "backend_manifest_preflight": journal.get("backend_manifest_preflight_path"),
        "backend_manifest_in_place_mutation": journal.get("backend_manifest_in_place_mutation_path"),
        "backend_manifest_rollback": journal.get("backend_manifest_rollback_path"),
        "backend_manifest_recovery_preflight": journal.get("backend_manifest_recovery_preflight_path")
        or recovery_preflight.get("preflight_path"),
        "backend_manifest_recovery": journal.get("backend_manifest_recovery_path") or recovery_result.get("recovery_path"),
        "backend_manifest_transaction_commit": journal.get("backend_manifest_transaction_commit_path")
        or transaction_commit.get("commit_path"),
        "external_delivery_result": journal.get("external_delivery_result_path") or external_result.get("result_path"),
        "external_delivery_idempotency_ledger": journal.get("external_delivery_idempotency_ledger_path")
        or external_idempotency_ledger.get("ledger_path"),
    }
    return {key: str(value) for key, value in candidates.items() if value}


def _recommended_actions(
    state: DeliveryTransactionState,
    flags: Mapping[str, bool],
    blocking_reasons: list[str],
) -> list[str]:
    if blocking_reasons:
        return ["inspect_transaction_state_blockers", "fix_blocking_reasons_before_retry"]
    if state == DeliveryTransactionState.COMMITTED:
        return ["review_committed_transaction_journal"]
    if state == DeliveryTransactionState.EXTERNAL_DELIVERED:
        return ["review_external_delivery_result", "commit_transaction_record_after_review"]
    if state == DeliveryTransactionState.EXTERNAL_DELIVERY_ATTEMPTED:
        return ["review_external_delivery_attempt", "retry_or_configure_provider_after_review"]
    if state == DeliveryTransactionState.RECOVERED:
        return ["review_recovered_manifest", "rerun_preflight_before_new_commit"]
    if state == DeliveryTransactionState.RECOVERY_REQUIRED:
        if flags.get("backend_manifest_mutated"):
            return ["review_backend_manifest_mutation", "choose_commit_or_recovery_path"]
        return ["review_backend_manifest_recovery_preflight"]
    if state == DeliveryTransactionState.MANIFEST_MUTATED:
        return ["review_backend_manifest_in_place_mutation_before_cross_run_commit"]
    if state == DeliveryTransactionState.MANIFEST_PREFLIGHT_PASSED:
        return ["review_backend_manifest_preflight", "approve_in_place_mutation_if_safe"]
    if state == DeliveryTransactionState.MANIFEST_PATCH_WRITTEN:
        return ["review_backend_manifest_patch", "run_in_place_mutation_preflight_if_needed"]
    if state == DeliveryTransactionState.MANIFEST_REVISION_COMMITTED:
        return ["review_manifest_revision", "plan_backend_manifest_patch_if_needed"]
    if state == DeliveryTransactionState.LOCAL_APPLIED:
        return ["review_local_delivery_receipt", "request_external_delivery_or_manifest_commit_after_review"]
    return ["review_delivery_plan_before_apply"]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
