from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ReviewApprovalMode = str
SUPPORTED_REVIEW_APPROVAL_MODES: tuple[str, ...] = ("dry-run", "apply")
SUPPORTED_REVIEW_APPROVAL_DECISIONS: tuple[str, ...] = ("approved", "rejected", "needs_changes")
SUPPORTED_REVIEW_APPROVAL_ACTIONS: tuple[str, ...] = ("record_review_decision", "write_approval_ledger")


@dataclass(frozen=True)
class ReviewApprovalConfig:
    review_root: Path
    subject_id: str
    action: str
    decision: str = "approved"
    reviewer: str | None = None
    reason: str | None = None
    mode: str = "dry-run"
    approve_decision_record: bool = False
    subject_digest_sha256: str | None = None
    expected_subject_digest_sha256: str | None = None
    ledger_name: str = "review-approval-ledger.json"
    record_name: str = "review-approval-record.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_review_root(self) -> Path:
        return self.review_root.expanduser().resolve()


@dataclass(frozen=True)
class ReviewApprovalRecord:
    approval_id: str
    subject_id: str
    action: str
    decision: str
    status: str
    mode: str
    dry_run: bool
    reviewer: str | None
    reason: str | None
    review_root: str
    record_path: str | None
    ledger_path: str | None
    ledger_entry_count: int
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    subject_digest_sha256: str | None = None
    expected_subject_digest_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        written = bool(self.record_path and self.ledger_path) and not self.dry_run and self.status == "written"
        return {
            "approval_id": self.approval_id,
            "subject_id": self.subject_id,
            "action": self.action,
            "decision": self.decision,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "review_root": self.review_root,
            "record_path": self.record_path,
            "ledger_path": self.ledger_path,
            "ledger_entry_count": self.ledger_entry_count,
            "subject_digest_sha256": self.subject_digest_sha256,
            "expected_subject_digest_sha256": self.expected_subject_digest_sha256,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_approval_record": written,
                "writes_approval_ledger": written,
                "review_decision_recorded": written,
                "delivery_executed": False,
                "external_delivery_performed": False,
                "manifest_mutated": False,
                "transaction_committed": False,
                "rollback_executed": False,
                "automatic_approval": False,
            },
        }


class ReviewApprovalLedgerWriter:
    def __init__(self, config: ReviewApprovalConfig) -> None:
        self.config = config

    def execute(self) -> ReviewApprovalRecord:
        created_at = datetime.now(timezone.utc).isoformat()
        dry_run = self.config.mode == "dry-run"
        root = self.config.resolved_review_root()
        approval_id = _approval_id(self.config.subject_id, self.config.action, self.config.decision, created_at)
        checks = self._checks()
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        status = "blocked" if blocking_reasons else "planned" if dry_run else "written"
        ledger_path = root / self.config.ledger_name
        record_path = root / self.config.record_name
        previous_entries = _read_ledger_entries(ledger_path) if not dry_run and not blocking_reasons else []
        record = ReviewApprovalRecord(
            approval_id=approval_id,
            subject_id=self.config.subject_id,
            action=self.config.action,
            decision=self.config.decision,
            status=status,
            mode=self.config.mode,
            dry_run=dry_run,
            reviewer=self.config.reviewer,
            reason=self.config.reason,
            review_root=str(root),
            record_path=str(record_path) if not dry_run and not blocking_reasons else None,
            ledger_path=str(ledger_path) if not dry_run and not blocking_reasons else None,
            ledger_entry_count=len(previous_entries) + (0 if dry_run or blocking_reasons else 1),
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=self._recommended_actions(status, blocking_reasons),
            created_at=created_at,
            subject_digest_sha256=self.config.subject_digest_sha256,
            expected_subject_digest_sha256=self.config.expected_subject_digest_sha256,
            metadata={
                **self.config.metadata,
                "executor": "review-approval-ledger-writer",
                "scope": "review-approval-ledger-baseline",
                "append_only_ledger": True,
                "does_not_execute_delivery": True,
                "does_not_mutate_manifest": True,
                "does_not_publish_external_delivery": True,
            },
        )
        if record.record_path and record.ledger_path:
            entry = record.to_dict()
            entries = [*previous_entries, entry]
            _write_json(record_path, entry)
            _write_json(ledger_path, {"version": "2026-06-01.review-approval-ledger-v1", "entries": entries, "entry_count": len(entries), "updated_at": created_at})
        return record

    def _checks(self) -> list[dict[str, Any]]:
        digest_matches = (
            not self.config.expected_subject_digest_sha256
            or not self.config.subject_digest_sha256
            or self.config.expected_subject_digest_sha256 == self.config.subject_digest_sha256
        )
        return [
            {"name": "subject_id_present", "passed": bool(self.config.subject_id.strip()), "details": {"subject_id": self.config.subject_id}},
            {"name": "action_present", "passed": bool(self.config.action.strip()), "details": {"action": self.config.action}},
            {"name": "decision_supported", "passed": self.config.decision in SUPPORTED_REVIEW_APPROVAL_DECISIONS, "details": {"decision": self.config.decision}},
            {"name": "mode_supported", "passed": self.config.mode in SUPPORTED_REVIEW_APPROVAL_MODES, "details": {"mode": self.config.mode}},
            {"name": "reviewer_present", "passed": bool((self.config.reviewer or "").strip()), "details": {"reviewer": self.config.reviewer}},
            {"name": "apply_requires_explicit_approval_record", "passed": self.config.mode == "dry-run" or bool(self.config.approve_decision_record), "details": {"approve_decision_record": self.config.approve_decision_record}},
            {"name": "subject_digest_matches_expected", "passed": digest_matches, "details": {"subject_digest_sha256": self.config.subject_digest_sha256, "expected_subject_digest_sha256": self.config.expected_subject_digest_sha256}},
        ]

    @staticmethod
    def _recommended_actions(status: str, blocking_reasons: list[str]) -> list[str]:
        if blocking_reasons:
            return ["fix_review_approval_record_blockers_before_retry"]
        if status == "planned":
            return ["review_approval_record_before_apply_write"]
        return ["use_review_approval_ledger_as_input_to_review_gated_executor"]


def _approval_id(subject_id: str, action: str, decision: str, created_at: str) -> str:
    digest = hashlib.sha256(f"{subject_id}\0{action}\0{decision}\0{created_at}".encode("utf-8")).hexdigest()[:16]
    return f"review-approval-{digest}"


def _read_ledger_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - malformed prior ledger is not trusted as entries.
        return []
    entries = payload.get("entries") if isinstance(payload, dict) else None
    return [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
