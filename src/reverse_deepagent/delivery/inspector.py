from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rollback_state import evaluate_delivery_rollback_state
from .state_machine import evaluate_delivery_transaction_state, plan_delivery_transition

DELIVERY_TRANSACTION_INSPECTOR_VERSION = "2026-05-31.delivery-transaction-inspector-v1"
DELIVERY_TRANSACTION_ARTIFACT_NAMES: dict[str, str] = {
    "transaction_journal": "delivery-transaction-journal.json",
    "external_delivery_result": "external-delivery-result.json",
    "external_delivery_idempotency_ledger": "external-delivery-idempotency-ledger.json",
    "delivery_transition_execution": "delivery-transition-execution.json",
    "transaction_lock": "delivery-transaction-lock.json",
    "transaction_lock_release": "delivery-transaction-lock-release.json",
    "transaction_idempotency_guard": "delivery-transaction-idempotency-guard.json",
    "backend_manifest_recovery_preflight": "backend-artifact-manifest-recovery-preflight.json",
    "backend_manifest_recovery": "backend-artifact-manifest-recovery.json",
    "backend_manifest_transaction_commit": "backend-artifact-manifest-transaction-commit.json",
}


@dataclass(frozen=True)
class DeliveryTransactionInspection:
    """Read-only inspection result for delivery transaction artifacts."""

    root: str
    ok: bool
    state_snapshot: dict[str, Any]
    transition_plan: dict[str, Any]
    rollback_state: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    missing_artifacts: list[str] = field(default_factory=list)
    load_errors: dict[str, str] = field(default_factory=dict)
    version: str = DELIVERY_TRANSACTION_INSPECTOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "root": self.root,
            "ok": self.ok,
            "state_snapshot": self.state_snapshot,
            "transition_plan": self.transition_plan,
            "rollback_state": self.rollback_state,
            "artifacts": self.artifacts,
            "missing_artifacts": self.missing_artifacts,
            "load_errors": self.load_errors,
            "side_effect_policy": {
                "read_only": True,
                "files_mutated": False,
                "manifest_mutated": False,
                "external_delivery_performed": False,
                "transaction_committed": False,
            },
        }


def inspect_delivery_transaction_root(root: str | Path) -> DeliveryTransactionInspection:
    """Inspect standard delivery transaction artifacts from a delivery root.

    The inspector reads JSON artifacts only. It does not execute local delivery,
    restore manifests, mutate journals, publish externally, or commit a
    transaction. Missing optional artifacts are reported separately so callers
    can distinguish "not reached yet" from malformed evidence.
    """

    root_path = Path(root).expanduser()
    artifacts: dict[str, dict[str, Any]] = {}
    loaded_payload: dict[str, Any] = {}
    missing: list[str] = []
    load_errors: dict[str, str] = {}

    for key, filename in DELIVERY_TRANSACTION_ARTIFACT_NAMES.items():
        path = root_path / filename
        artifact_record: dict[str, Any] = {
            "path": str(path),
            "exists": path.exists(),
            "loaded": False,
        }
        if not path.exists():
            missing.append(key)
            artifacts[key] = artifact_record
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - inspector must report malformed artifacts without raising.
            artifact_record["error"] = str(exc)
            load_errors[key] = str(exc)
            artifacts[key] = artifact_record
            continue
        artifact_record["loaded"] = isinstance(payload, dict)
        if isinstance(payload, dict):
            artifact_record["keys"] = sorted(str(item) for item in payload.keys())
            loaded_payload[key] = payload
        else:
            artifact_record["error"] = "artifact JSON root must be an object"
            load_errors[key] = "artifact JSON root must be an object"
        artifacts[key] = artifact_record

    state_input = _inspection_state_input(loaded_payload)
    snapshot = evaluate_delivery_transaction_state(state_input)
    transition = plan_delivery_transition(snapshot)
    rollback_state = evaluate_delivery_rollback_state(state_input)
    ok = bool(loaded_payload.get("transaction_journal")) and not load_errors and not snapshot.blocked
    return DeliveryTransactionInspection(
        root=str(root_path),
        ok=ok,
        state_snapshot=snapshot.to_dict(),
        transition_plan=transition.to_dict(),
        rollback_state=rollback_state.to_dict(),
        artifacts=artifacts,
        missing_artifacts=missing,
        load_errors=load_errors,
    )


def _inspection_state_input(loaded_payload: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in DELIVERY_TRANSACTION_ARTIFACT_NAMES:
        if key in loaded_payload:
            payload[key] = loaded_payload[key]
    journal = loaded_payload.get("transaction_journal")
    if isinstance(journal, dict):
        payload.update({key: value for key, value in journal.items() if key not in payload})
        payload["transaction_journal"] = journal
    return payload
