from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

from reverse_deepagent.browser.base import BrowserPage


def _stable_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class HeapSnapshotDiffReadinessSpec:
    """Review-only pair review before any future heap snapshot diff executor."""

    before_collect_descriptor: dict[str, Any] | None = None
    after_collect_descriptor: dict[str, Any] | None = None
    max_byte_delta_ratio: float = 5.0
    require_same_provider: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffReadinessSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_readiness",
                "heapSnapshotDiffReadiness",
                "heap_snapshot_diff_review",
                "heapSnapshotDiffReview",
                "review_heap_snapshot_diff",
                "reviewHeapSnapshotDiff",
                "heap_diff_readiness",
                "heapDiffReadiness",
            )
        )
        before = context.get(
            "before_heap_snapshot_collect",
            context.get(
                "beforeHeapSnapshotCollect",
                context.get("baseline_heap_snapshot_collect", context.get("baselineHeapSnapshotCollect")),
            ),
        )
        after = context.get(
            "after_heap_snapshot_collect",
            context.get(
                "afterHeapSnapshotCollect",
                context.get("candidate_heap_snapshot_collect", context.get("candidateHeapSnapshotCollect")),
            ),
        )
        if not requested and not before and not after:
            return None
        ratio_raw = context.get("max_byte_delta_ratio", context.get("maxByteDeltaRatio", 5.0))
        try:
            ratio = float(ratio_raw)
        except (TypeError, ValueError):
            ratio = 5.0
        return cls(
            before_collect_descriptor=before if isinstance(before, dict) else None,
            after_collect_descriptor=after if isinstance(after, dict) else None,
            max_byte_delta_ratio=max(0.0, ratio),
            require_same_provider=bool(context.get("require_same_provider", context.get("requireSameProvider", True))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffReadinessResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffReadinessManager:
    """Review-only descriptor for future heap snapshot diff inputs."""

    def review(self, spec: HeapSnapshotDiffReadinessSpec | None) -> HeapSnapshotDiffReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=["missing_heap_snapshot_diff_readiness_request"],
                warnings=[],
                pair_summary={},
                side_effect_policy=policy,
            )
            return HeapSnapshotDiffReadinessResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_diff_readiness_request")

        before = spec.before_collect_descriptor or {}
        after = spec.after_collect_descriptor or {}
        blockers: list[str] = []
        warnings: list[str] = []
        if not before:
            blockers.append("before_heap_snapshot_collect_descriptor_required")
        if not after:
            blockers.append("after_heap_snapshot_collect_descriptor_required")
        for label, descriptor in (("before", before), ("after", after)):
            blockers.extend(self._collect_descriptor_blockers(label, descriptor))
        pair_summary = self._pair_summary(before, after)
        if before and after:
            before_provider = pair_summary.get("before_provider_id")
            after_provider = pair_summary.get("after_provider_id")
            if spec.require_same_provider and before_provider and after_provider and before_provider != after_provider:
                blockers.append("heap_snapshot_collect_provider_mismatch")
            if pair_summary.get("digest_equal"):
                warnings.append("heap_snapshot_collect_digests_equal")
            ratio = pair_summary.get("byte_delta_ratio")
            if isinstance(ratio, (int, float)) and spec.max_byte_delta_ratio and ratio > spec.max_byte_delta_ratio:
                warnings.append("heap_snapshot_collect_byte_delta_exceeds_review_ratio")

        status = "blocked" if blockers else "ready_for_review"
        descriptor = self._descriptor(spec, status=status, blockers=blockers, warnings=warnings, pair_summary=pair_summary, side_effect_policy=policy)
        return HeapSnapshotDiffReadinessResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @staticmethod
    def _collect_descriptor_blockers(label: str, descriptor: dict[str, Any]) -> list[str]:
        if not descriptor:
            return []
        blockers: list[str] = []
        if descriptor.get("schema_version") != "reverse-deepagent.heap-snapshot-collect.v1":
            blockers.append(f"{label}_heap_snapshot_collect_schema_mismatch")
        if descriptor.get("status") != "collected":
            blockers.append(f"{label}_heap_snapshot_collect_not_collected")
        metadata = descriptor.get("snapshot_metadata") if isinstance(descriptor.get("snapshot_metadata"), dict) else {}
        if not str(metadata.get("snapshot_digest") or "").startswith("sha256:"):
            blockers.append(f"{label}_heap_snapshot_collect_digest_missing")
        if int(metadata.get("snapshot_byte_count") or 0) <= 0:
            blockers.append(f"{label}_heap_snapshot_collect_byte_count_missing")
        policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
        if descriptor.get("raw_heap_exported") or policy.get("raw_heap_exported") or descriptor.get("raw_heap_available_in_artifact"):
            blockers.append(f"{label}_heap_snapshot_collect_raw_heap_export_detected")
        if descriptor.get("heap_diff_computed") or policy.get("heap_diff_computed"):
            blockers.append(f"{label}_heap_snapshot_collect_already_computed_diff")
        if descriptor.get("complete_heap_traversal_claimed") or policy.get("complete_heap_traversal"):
            blockers.append(f"{label}_heap_snapshot_collect_complete_traversal_claim_detected")
        return blockers

    @staticmethod
    def _pair_summary(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        before_meta = before.get("snapshot_metadata") if isinstance(before.get("snapshot_metadata"), dict) else {}
        after_meta = after.get("snapshot_metadata") if isinstance(after.get("snapshot_metadata"), dict) else {}
        before_readiness = before.get("readiness_summary") if isinstance(before.get("readiness_summary"), dict) else {}
        after_readiness = after.get("readiness_summary") if isinstance(after.get("readiness_summary"), dict) else {}
        before_bytes = int(before_meta.get("snapshot_byte_count") or 0)
        after_bytes = int(after_meta.get("snapshot_byte_count") or 0)
        delta = after_bytes - before_bytes
        ratio = abs(delta) / max(1, before_bytes) if before_bytes or after_bytes else None
        before_digest = before_meta.get("snapshot_digest")
        after_digest = after_meta.get("snapshot_digest")
        return {
            "before_digest": before_digest,
            "after_digest": after_digest,
            "digest_equal": bool(before_digest and after_digest and before_digest == after_digest),
            "before_snapshot_byte_count": before_bytes,
            "after_snapshot_byte_count": after_bytes,
            "byte_delta": delta,
            "byte_delta_ratio": ratio,
            "before_chunk_count": int(before_meta.get("chunk_count") or 0),
            "after_chunk_count": int(after_meta.get("chunk_count") or 0),
            "before_provider_id": before_readiness.get("browser_provider_id"),
            "after_provider_id": after_readiness.get("browser_provider_id"),
            "before_redacted_summary_only": bool(before_meta.get("redacted_summary_only")),
            "after_redacted_summary_only": bool(after_meta.get("redacted_summary_only")),
        }

    def _descriptor(
        self,
        spec: HeapSnapshotDiffReadinessSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        pair_summary: dict[str, Any],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-readiness.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_exported": False,
            "complete_heap_traversal_claimed": False,
            "pair_summary": pair_summary,
            "safety_gates": {
                "requires_two_collected_heap_snapshot_metadata_descriptors": True,
                "requires_raw_heap_absent": True,
                "requires_no_prior_heap_diff": True,
                "requires_no_complete_traversal_claim": True,
                "requires_same_provider": bool(spec.require_same_provider) if spec else True,
                "max_byte_delta_ratio": spec.max_byte_delta_ratio if spec else 5.0,
                "future_diff_executor_requires_explicit_review": True,
                "future_diff_executor_implemented": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_readiness_before_diff_executor" if not blockers else "provide_two_reviewed_heap_snapshot_collect_descriptors",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "default_recon": False,
            "files_mutated": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotDiffExecutorPreflightSpec:
    """Review-only preflight for a future raw-heap-aware diff executor.

    This is intentionally one step past diff readiness but still not the diff
    executor: it validates that reviewer-provided ingestion / parser / redaction
    gates are present before any future implementation may load raw heap data.
    """

    diff_readiness_descriptor: dict[str, Any] | None = None
    review_approved: bool = False
    raw_heap_ingestion_policy: str = "metadata-only"
    parser_sandbox: str = "required"
    redaction_plan: str = "required"
    max_raw_heap_bytes: int = 50_000_000
    export_raw_heap: bool = False
    compute_heap_diff: bool = False
    allow_complete_traversal_claim: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffExecutorPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_executor_preflight",
                "heapSnapshotDiffExecutorPreflight",
                "heap_snapshot_diff_preflight",
                "heapSnapshotDiffPreflight",
                "heap_diff_executor_preflight",
                "heapDiffExecutorPreflight",
                "review_heap_snapshot_diff_executor",
                "reviewHeapSnapshotDiffExecutor",
                "raw_heap_diff_preflight",
                "rawHeapDiffPreflight",
            )
        )
        readiness = context.get(
            "heap_snapshot_diff_readiness",
            context.get(
                "heapSnapshotDiffReadiness",
                context.get("heap_snapshot_diff_readiness_descriptor", context.get("heapSnapshotDiffReadinessDescriptor")),
            ),
        )
        if not requested and not readiness:
            return None
        max_raw = context.get("max_raw_heap_bytes", context.get("maxRawHeapBytes", 50_000_000))
        try:
            max_raw_bytes = int(max_raw or 50_000_000)
        except (TypeError, ValueError):
            max_raw_bytes = 50_000_000
        return cls(
            diff_readiness_descriptor=readiness if isinstance(readiness, dict) else None,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            raw_heap_ingestion_policy=str(context.get("raw_heap_ingestion_policy", context.get("rawHeapIngestionPolicy", "metadata-only")) or "metadata-only").strip().lower(),
            parser_sandbox=str(context.get("parser_sandbox", context.get("parserSandbox", "required")) or "required").strip().lower(),
            redaction_plan=str(context.get("redaction_plan", context.get("redactionPlan", "required")) or "required").strip().lower(),
            max_raw_heap_bytes=max(1, max_raw_bytes),
            export_raw_heap=bool(context.get("export_raw_heap", context.get("exportRawHeap", False))),
            compute_heap_diff=bool(context.get("compute_heap_diff", context.get("computeHeapDiff", False))),
            allow_complete_traversal_claim=bool(context.get("allow_complete_traversal_claim", context.get("allowCompleteTraversalClaim", False))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffExecutorPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffExecutorPreflightManager:
    """Review-only raw heap diff executor gate for a future implementation."""

    _READY_STATUSES = {"ready_for_review", "ready", "approved"}
    _SUPPORTED_INGESTION_POLICIES = {"metadata-only", "redacted-metadata-only", "external-redacted-manifest"}

    def review(self, spec: HeapSnapshotDiffExecutorPreflightSpec | None) -> HeapSnapshotDiffExecutorPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=["missing_heap_snapshot_diff_executor_preflight_request"],
                warnings=[],
                readiness_summary={},
                side_effect_policy=policy,
            )
            return HeapSnapshotDiffExecutorPreflightResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_diff_executor_preflight_request")

        readiness = spec.diff_readiness_descriptor or {}
        blockers: list[str] = []
        warnings: list[str] = []
        if not spec.review_approved:
            blockers.append("heap_snapshot_diff_executor_preflight_review_approval_required")
        if not readiness:
            blockers.append("heap_snapshot_diff_readiness_descriptor_required")
        else:
            blockers.extend(self._diff_readiness_blockers(readiness))
        if spec.raw_heap_ingestion_policy not in self._SUPPORTED_INGESTION_POLICIES:
            blockers.append("unsupported_raw_heap_ingestion_policy")
        if spec.parser_sandbox in {"", "none", "disabled", "false"}:
            blockers.append("heap_snapshot_parser_sandbox_required")
        if spec.redaction_plan in {"", "none", "disabled", "false"}:
            blockers.append("heap_snapshot_diff_redaction_plan_required")
        if spec.export_raw_heap:
            blockers.append("raw_heap_export_not_supported_by_preflight")
        if spec.compute_heap_diff:
            blockers.append("heap_diff_execution_not_supported_by_preflight")
        if spec.allow_complete_traversal_claim:
            blockers.append("complete_heap_traversal_claim_not_supported_by_preflight")
        if spec.max_raw_heap_bytes > 250_000_000:
            warnings.append("large_raw_heap_budget_requires_manual_review")

        status = "blocked" if blockers else "ready_for_review"
        readiness_summary = self._readiness_summary(readiness)
        descriptor = self._descriptor(spec, status=status, blockers=blockers, warnings=warnings, readiness_summary=readiness_summary, side_effect_policy=policy)
        return HeapSnapshotDiffExecutorPreflightResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _diff_readiness_blockers(cls, readiness: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if readiness.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-readiness.v1":
            blockers.append("heap_snapshot_diff_readiness_schema_mismatch")
        if readiness.get("status") not in cls._READY_STATUSES:
            blockers.append("heap_snapshot_diff_readiness_not_ready")
        policy = readiness.get("side_effect_policy") if isinstance(readiness.get("side_effect_policy"), dict) else {}
        gates = readiness.get("safety_gates") if isinstance(readiness.get("safety_gates"), dict) else {}
        if readiness.get("heap_diff_computed") or readiness.get("heap_snapshot_diff_computed") or policy.get("heap_diff_computed") or policy.get("heap_snapshot_diff_computed"):
            blockers.append("heap_snapshot_diff_readiness_already_computed_diff")
        if readiness.get("raw_heap_loaded") or policy.get("raw_heap_loaded"):
            blockers.append("heap_snapshot_diff_readiness_raw_heap_loaded")
        if readiness.get("raw_heap_exported") or policy.get("raw_heap_exported"):
            blockers.append("heap_snapshot_diff_readiness_raw_heap_exported")
        if readiness.get("complete_heap_traversal_claimed") or policy.get("complete_heap_traversal"):
            blockers.append("heap_snapshot_diff_readiness_complete_traversal_claim_detected")
        if gates.get("future_diff_executor_implemented") is True:
            blockers.append("unexpected_prior_diff_executor_implementation_claim")
        return blockers

    @staticmethod
    def _readiness_summary(readiness: dict[str, Any]) -> dict[str, Any]:
        pair = readiness.get("pair_summary") if isinstance(readiness.get("pair_summary"), dict) else {}
        gates = readiness.get("safety_gates") if isinstance(readiness.get("safety_gates"), dict) else {}
        return {
            "schema_version": readiness.get("schema_version"),
            "status": readiness.get("status"),
            "before_digest": pair.get("before_digest"),
            "after_digest": pair.get("after_digest"),
            "digest_equal": bool(pair.get("digest_equal")),
            "byte_delta": pair.get("byte_delta"),
            "byte_delta_ratio": pair.get("byte_delta_ratio"),
            "requires_same_provider": bool(gates.get("requires_same_provider", True)),
            "future_diff_executor_implemented": bool(gates.get("future_diff_executor_implemented", False)),
        }

    def _descriptor(
        self,
        spec: HeapSnapshotDiffExecutorPreflightSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        readiness_summary: dict[str, Any],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-preflight.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "executor_preflight_only": True,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "readiness_summary": readiness_summary,
            "ingestion_policy": {
                "raw_heap_ingestion_policy": spec.raw_heap_ingestion_policy if spec else "metadata-only",
                "supported_policies": sorted(self._SUPPORTED_INGESTION_POLICIES),
                "parser_sandbox": spec.parser_sandbox if spec else "required",
                "redaction_plan": spec.redaction_plan if spec else "required",
                "max_raw_heap_bytes": spec.max_raw_heap_bytes if spec else 50_000_000,
                "export_raw_heap_requested": bool(spec.export_raw_heap) if spec else False,
                "compute_heap_diff_requested": bool(spec.compute_heap_diff) if spec else False,
                "complete_traversal_claim_requested": bool(spec.allow_complete_traversal_claim) if spec else False,
            },
            "safety_gates": {
                "requires_explicit_review_approval": True,
                "review_approved": bool(spec.review_approved) if spec else False,
                "requires_ready_heap_snapshot_diff_readiness": True,
                "requires_supported_raw_heap_ingestion_policy": True,
                "requires_parser_sandbox": True,
                "requires_redaction_plan": True,
                "requires_size_budget": True,
                "requires_raw_heap_export_disabled": True,
                "requires_diff_execution_disabled_in_preflight": True,
                "requires_no_complete_traversal_claim": True,
                "future_diff_executor_requires_explicit_review": True,
                "future_diff_executor_implemented": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_executor_preflight_before_implementation" if not blockers else "resolve_heap_snapshot_diff_executor_preflight_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "executor_preflight_only": True,
            "default_recon": False,
            "files_mutated": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotDiffExecutorApprovalPlanSpec:
    """Review-only approval / transaction plan for a future heap diff executor.

    This descriptor plans the approval record, transaction journal, bounded gate,
    and result artifact contract after executor preflight. It does not record
    approval, write journals, load raw heap, or compute heap diffs.
    """

    executor_preflight_descriptor: dict[str, Any] | None = None
    reviewer: str | None = None
    approval_scope: str = "heap-snapshot-diff-executor"
    transaction_id: str | None = None
    idempotency_key: str | None = None
    approval_record_artifact: str = "workspace/heap-snapshot-diff-executor-approval-record.json"
    transaction_journal_artifact: str = "workspace/heap-snapshot-diff-executor-journal.json"
    bounded_gate_artifact: str = "workspace/heap-snapshot-diff-executor-bounded-gate.json"
    result_artifact: str = "workspace/heap-snapshot-diff-executor-result.json"
    require_bounded_executor_gate: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffExecutorApprovalPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_executor_approval_plan",
                "heapSnapshotDiffExecutorApprovalPlan",
                "heap_snapshot_diff_approval_plan",
                "heapSnapshotDiffApprovalPlan",
                "heap_diff_executor_approval_plan",
                "heapDiffExecutorApprovalPlan",
                "review_heap_snapshot_diff_executor_approval",
                "reviewHeapSnapshotDiffExecutorApproval",
                "raw_heap_diff_approval_plan",
                "rawHeapDiffApprovalPlan",
            )
        )
        preflight = context.get(
            "heap_snapshot_diff_executor_preflight",
            context.get(
                "heapSnapshotDiffExecutorPreflight",
                context.get("heap_snapshot_diff_executor_preflight_descriptor", context.get("heapSnapshotDiffExecutorPreflightDescriptor")),
            ),
        )
        if not requested and not preflight:
            return None
        transaction_id = context.get("transaction_id", context.get("transactionId"))
        idempotency_key = context.get("idempotency_key", context.get("idempotencyKey"))
        return cls(
            executor_preflight_descriptor=preflight if isinstance(preflight, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            approval_scope=str(context.get("approval_scope", context.get("approvalScope", "heap-snapshot-diff-executor")) or "heap-snapshot-diff-executor").strip(),
            transaction_id=str(transaction_id).strip() if transaction_id else None,
            idempotency_key=str(idempotency_key).strip() if idempotency_key else None,
            approval_record_artifact=str(context.get("approval_record_artifact", context.get("approvalRecordArtifact", "workspace/heap-snapshot-diff-executor-approval-record.json")) or "workspace/heap-snapshot-diff-executor-approval-record.json"),
            transaction_journal_artifact=str(context.get("transaction_journal_artifact", context.get("transactionJournalArtifact", "workspace/heap-snapshot-diff-executor-journal.json")) or "workspace/heap-snapshot-diff-executor-journal.json"),
            bounded_gate_artifact=str(context.get("bounded_gate_artifact", context.get("boundedGateArtifact", "workspace/heap-snapshot-diff-executor-bounded-gate.json")) or "workspace/heap-snapshot-diff-executor-bounded-gate.json"),
            result_artifact=str(context.get("result_artifact", context.get("resultArtifact", "workspace/heap-snapshot-diff-executor-result.json")) or "workspace/heap-snapshot-diff-executor-result.json"),
            require_bounded_executor_gate=bool(context.get("require_bounded_executor_gate", context.get("requireBoundedExecutorGate", True))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffExecutorApprovalPlanResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffExecutorApprovalPlanManager:
    """Review-only approval / transaction plan for a future heap diff executor."""

    _READY_STATUSES = {"ready_for_review", "ready", "approved"}

    def review(self, spec: HeapSnapshotDiffExecutorApprovalPlanSpec | None) -> HeapSnapshotDiffExecutorApprovalPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=["missing_heap_snapshot_diff_executor_approval_plan_request"],
                warnings=[],
                preflight_summary={},
                side_effect_policy=policy,
            )
            return HeapSnapshotDiffExecutorApprovalPlanResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_diff_executor_approval_plan_request")

        preflight = spec.executor_preflight_descriptor or {}
        blockers: list[str] = []
        warnings: list[str] = []
        if not preflight:
            blockers.append("heap_snapshot_diff_executor_preflight_descriptor_required")
        else:
            blockers.extend(self._preflight_blockers(preflight))
        if not spec.approval_scope:
            blockers.append("heap_snapshot_diff_executor_approval_scope_required")
        if not spec.reviewer:
            warnings.append("heap_snapshot_diff_executor_reviewer_required_before_approval_record")
        if not spec.transaction_id:
            warnings.append("heap_snapshot_diff_executor_transaction_id_will_be_derived")
        if not spec.idempotency_key:
            warnings.append("heap_snapshot_diff_executor_idempotency_key_will_be_derived")
        if not spec.require_bounded_executor_gate:
            blockers.append("bounded_executor_gate_required")

        status = "blocked" if blockers else "ready_for_review"
        preflight_summary = self._preflight_summary(preflight)
        descriptor = self._descriptor(spec, status=status, blockers=blockers, warnings=warnings, preflight_summary=preflight_summary, side_effect_policy=policy)
        return HeapSnapshotDiffExecutorApprovalPlanResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _preflight_blockers(cls, preflight: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        if preflight.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-executor-preflight.v1":
            blockers.append("heap_snapshot_diff_executor_preflight_schema_mismatch")
        if preflight.get("status") not in cls._READY_STATUSES:
            blockers.append("heap_snapshot_diff_executor_preflight_not_ready")
        policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        gates = preflight.get("safety_gates") if isinstance(preflight.get("safety_gates"), dict) else {}
        if preflight.get("diff_executor_implemented") or gates.get("future_diff_executor_implemented"):
            blockers.append("unexpected_diff_executor_implementation_claim")
        if preflight.get("raw_heap_loaded") or policy.get("raw_heap_loaded"):
            blockers.append("heap_snapshot_diff_executor_preflight_raw_heap_loaded")
        if preflight.get("raw_heap_parsed") or policy.get("raw_heap_parsed"):
            blockers.append("heap_snapshot_diff_executor_preflight_raw_heap_parsed")
        if preflight.get("raw_heap_exported") or policy.get("raw_heap_exported"):
            blockers.append("heap_snapshot_diff_executor_preflight_raw_heap_exported")
        if preflight.get("heap_diff_computed") or policy.get("heap_diff_computed"):
            blockers.append("heap_snapshot_diff_executor_preflight_already_computed_diff")
        if preflight.get("complete_heap_traversal_claimed") or policy.get("complete_heap_traversal"):
            blockers.append("heap_snapshot_diff_executor_preflight_complete_traversal_claim_detected")
        if gates.get("review_approved") is not True:
            blockers.append("heap_snapshot_diff_executor_preflight_review_approval_missing")
        return blockers

    @staticmethod
    def _preflight_summary(preflight: dict[str, Any]) -> dict[str, Any]:
        readiness = preflight.get("readiness_summary") if isinstance(preflight.get("readiness_summary"), dict) else {}
        ingestion = preflight.get("ingestion_policy") if isinstance(preflight.get("ingestion_policy"), dict) else {}
        return {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "before_digest": readiness.get("before_digest"),
            "after_digest": readiness.get("after_digest"),
            "raw_heap_ingestion_policy": ingestion.get("raw_heap_ingestion_policy"),
            "parser_sandbox": ingestion.get("parser_sandbox"),
            "redaction_plan": ingestion.get("redaction_plan"),
            "max_raw_heap_bytes": ingestion.get("max_raw_heap_bytes"),
            "diff_executor_implemented": bool(preflight.get("diff_executor_implemented", False)),
        }

    def _descriptor(
        self,
        spec: HeapSnapshotDiffExecutorApprovalPlanSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        preflight_summary: dict[str, Any],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        transaction_id = spec.transaction_id if spec and spec.transaction_id else self._derived_id("heap-diff-txn", preflight_summary)
        idempotency_key = spec.idempotency_key if spec and spec.idempotency_key else self._derived_id("heap-diff-idem", preflight_summary)
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1",
            "status": status,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "preflight_summary": preflight_summary,
            "approval_plan": {
                "approval_scope": spec.approval_scope if spec else "heap-snapshot-diff-executor",
                "reviewer": spec.reviewer if spec else None,
                "approval_record_artifact": spec.approval_record_artifact if spec else "workspace/heap-snapshot-diff-executor-approval-record.json",
                "approval_recorded": False,
                "required_approval_flag": "approve_heap_snapshot_diff_executor",
                "required_write_flag": "write_result",
                "required_mode": "apply",
            },
            "transaction_plan": {
                "transaction_id": transaction_id,
                "idempotency_key": idempotency_key,
                "transaction_journal_artifact": spec.transaction_journal_artifact if spec else "workspace/heap-snapshot-diff-executor-journal.json",
                "bounded_gate_artifact": spec.bounded_gate_artifact if spec else "workspace/heap-snapshot-diff-executor-bounded-gate.json",
                "result_artifact": spec.result_artifact if spec else "workspace/heap-snapshot-diff-executor-result.json",
                "transaction_started": False,
                "journal_written_now": False,
                "bounded_executor_gate_required": bool(spec.require_bounded_executor_gate) if spec else True,
            },
            "future_executor_contract": {
                "implemented": False,
                "requires_written_approval_record": True,
                "requires_written_transaction_journal": True,
                "requires_bounded_executor_gate": True,
                "requires_ready_executor_preflight": True,
                "requires_no_raw_heap_export": True,
                "requires_no_complete_traversal_claim": True,
                "result_artifact": spec.result_artifact if spec else "workspace/heap-snapshot-diff-executor-result.json",
            },
            "safety_gates": {
                "requires_ready_heap_snapshot_diff_executor_preflight": True,
                "requires_explicit_review_before_approval_record": True,
                "requires_transaction_journal_before_execution": True,
                "requires_bounded_executor_gate": True,
                "requires_no_executor_invocation_in_plan": True,
                "requires_raw_heap_unloaded": True,
                "requires_diff_uncomputed": True,
                "future_diff_executor_implemented": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval" if not blockers else "resolve_heap_snapshot_diff_executor_approval_plan_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _derived_id(prefix: str, summary: dict[str, Any]) -> str:
        payload = json.dumps(summary or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        digest = hashlib.sha256(payload).hexdigest()[:16]
        return f"{prefix}-{digest}"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "default_recon": False,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotDiffExecutorTransactionPreflightSpec:
    """Read-only transaction preflight before the heap diff journal writer.

    This descriptor consumes a ready approval / transaction plan and an explicit
    approval record. It does not start a transaction, write a journal, write the
    bounded gate, load raw heap snapshots, or compute heap diffs.
    """

    approval_plan_descriptor: dict[str, Any] | None = None
    approval_record_descriptor: dict[str, Any] | None = None
    expected_approval_scope: str | None = None
    expected_transaction_id: str | None = None
    expected_idempotency_key: str | None = None
    expected_plan_digest_sha256: str | None = None
    expected_preflight_digest_sha256: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffExecutorTransactionPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_executor_transaction_preflight",
                "heapSnapshotDiffExecutorTransactionPreflight",
                "heap_snapshot_diff_transaction_preflight",
                "heapSnapshotDiffTransactionPreflight",
                "heap_diff_executor_transaction_preflight",
                "heapDiffExecutorTransactionPreflight",
                "raw_heap_diff_transaction_preflight",
                "rawHeapDiffTransactionPreflight",
                "review_heap_snapshot_diff_executor_transaction_preflight",
                "reviewHeapSnapshotDiffExecutorTransactionPreflight",
                "preflight_heap_snapshot_diff_executor_transaction",
                "preflightHeapSnapshotDiffExecutorTransaction",
            )
        )
        plan = context.get(
            "heap_snapshot_diff_executor_approval_plan",
            context.get(
                "heapSnapshotDiffExecutorApprovalPlan",
                context.get("heap_snapshot_diff_executor_approval_plan_descriptor", context.get("heapSnapshotDiffExecutorApprovalPlanDescriptor")),
            ),
        )
        record = context.get(
            "heap_snapshot_diff_executor_approval_record",
            context.get(
                "heapSnapshotDiffExecutorApprovalRecord",
                context.get("heap_snapshot_diff_executor_approval_record_descriptor", context.get("heapSnapshotDiffExecutorApprovalRecordDescriptor")),
            ),
        )
        if not requested and not plan and not record:
            return None
        expected_approval_scope = context.get("expected_approval_scope", context.get("expectedApprovalScope"))
        expected_transaction_id = context.get("expected_transaction_id", context.get("expectedTransactionId"))
        expected_idempotency_key = context.get("expected_idempotency_key", context.get("expectedIdempotencyKey"))
        expected_plan_digest_sha256 = context.get("expected_plan_digest_sha256", context.get("expectedPlanDigestSha256"))
        expected_preflight_digest_sha256 = context.get("expected_preflight_digest_sha256", context.get("expectedPreflightDigestSha256"))
        return cls(
            approval_plan_descriptor=plan if isinstance(plan, dict) else None,
            approval_record_descriptor=record if isinstance(record, dict) else None,
            expected_approval_scope=str(expected_approval_scope).strip() if expected_approval_scope else None,
            expected_transaction_id=str(expected_transaction_id).strip() if expected_transaction_id else None,
            expected_idempotency_key=str(expected_idempotency_key).strip() if expected_idempotency_key else None,
            expected_plan_digest_sha256=str(expected_plan_digest_sha256).strip() if expected_plan_digest_sha256 else None,
            expected_preflight_digest_sha256=str(expected_preflight_digest_sha256).strip() if expected_preflight_digest_sha256 else None,
        )


@dataclass(slots=True)
class HeapSnapshotDiffExecutorTransactionPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffExecutorTransactionPreflightManager:
    """Read-only transaction preflight for the future heap diff journal writer."""

    _READY_PLAN_STATUSES = {"ready_for_review", "ready", "approved"}
    _READY_RECORD_STATUSES = {"written", "approved", "ready_for_review", "ready"}

    def review(self, spec: HeapSnapshotDiffExecutorTransactionPreflightSpec | None) -> HeapSnapshotDiffExecutorTransactionPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=["missing_heap_snapshot_diff_executor_transaction_preflight_request"],
                warnings=[],
                approval_summary={},
                transaction_summary={},
                preflight_summary={},
                guard_summary={},
                side_effect_policy=policy,
            )
            return HeapSnapshotDiffExecutorTransactionPreflightResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_diff_executor_transaction_preflight_request")

        plan = spec.approval_plan_descriptor or {}
        record = spec.approval_record_descriptor or {}
        blockers: list[str] = []
        warnings: list[str] = []
        if not plan:
            blockers.append("heap_snapshot_diff_executor_approval_plan_descriptor_required")
        else:
            blockers.extend(self._plan_blockers(plan))
        if not record:
            blockers.append("heap_snapshot_diff_executor_approval_record_descriptor_required")
        else:
            blockers.extend(self._record_blockers(record))
        if plan and record:
            blockers.extend(self._consistency_blockers(spec, plan, record))

        approval_summary = self._approval_summary(plan, record)
        transaction_summary = self._transaction_summary(plan, record)
        preflight_summary = self._preflight_summary(plan, record)
        guard_summary = self._guard_summary(spec, plan, record)
        status = "blocked" if blockers else "ready_for_review"
        if status == "ready_for_review":
            warnings.append("heap_snapshot_diff_executor_transaction_ready_for_journal_review")
        descriptor = self._descriptor(
            spec,
            status=status,
            blockers=blockers,
            warnings=warnings,
            approval_summary=approval_summary,
            transaction_summary=transaction_summary,
            preflight_summary=preflight_summary,
            guard_summary=guard_summary,
            side_effect_policy=policy,
        )
        return HeapSnapshotDiffExecutorTransactionPreflightResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _plan_blockers(cls, plan: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        future = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        if plan.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1":
            blockers.append("heap_snapshot_diff_executor_approval_plan_schema_mismatch")
        if plan.get("status") not in cls._READY_PLAN_STATUSES:
            blockers.append("heap_snapshot_diff_executor_approval_plan_not_ready")
        if plan.get("approval_recorded") is True or policy.get("approval_recorded") is True:
            blockers.append("approval_plan_claims_approval_recorded")
        if plan.get("transaction_started") is True or transaction.get("transaction_started") is True or policy.get("transaction_started") is True:
            blockers.append("approval_plan_claims_transaction_started")
        if plan.get("journal_written_now") is True or transaction.get("journal_written_now") is True or policy.get("journal_written_now") is True:
            blockers.append("approval_plan_claims_journal_written")
        if plan.get("bounded_executor_gate_written") is True or policy.get("bounded_executor_gate_written") is True:
            blockers.append("approval_plan_claims_bounded_gate_written")
        if plan.get("executor_invoked") is True or policy.get("executor_invoked") is True:
            blockers.append("approval_plan_claims_executor_invoked")
        blockers.extend(cls._no_heap_side_effect_blockers(plan, prefix="approval_plan"))
        if future.get("implemented") is True:
            blockers.append("approval_plan_claims_future_executor_implemented")
        return blockers

    @classmethod
    def _record_blockers(cls, record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        gates = record.get("executor_input_gates") if isinstance(record.get("executor_input_gates"), dict) else {}
        policy = record.get("side_effect_policy") if isinstance(record.get("side_effect_policy"), dict) else {}
        if record.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1":
            blockers.append("heap_snapshot_diff_executor_approval_record_schema_mismatch")
        if record.get("status") not in cls._READY_RECORD_STATUSES:
            blockers.append("heap_snapshot_diff_executor_approval_record_not_written")
        if record.get("approval_recorded") is not True:
            blockers.append("heap_snapshot_diff_executor_approval_record_missing_recorded_flag")
        if record.get("approved_for_execution") is not True:
            blockers.append("heap_snapshot_diff_executor_approval_record_not_approved_for_execution")
        if gates.get("transaction_started") is True or policy.get("transaction_started") is True:
            blockers.append("approval_record_claims_transaction_started")
        if gates.get("journal_written") is True or gates.get("journal_written_now") is True or policy.get("journal_written") is True or policy.get("journal_written_now") is True:
            blockers.append("approval_record_claims_journal_written")
        if gates.get("bounded_executor_gate_written") is True or policy.get("bounded_executor_gate_written") is True:
            blockers.append("approval_record_claims_bounded_gate_written")
        if gates.get("executor_invoked") is True or record.get("executor_invoked") is True or policy.get("executor_invoked") is True:
            blockers.append("approval_record_claims_executor_invoked")
        blockers.extend(cls._no_heap_side_effect_blockers(record, prefix="approval_record"))
        return blockers

    @classmethod
    def _consistency_blockers(cls, spec: HeapSnapshotDiffExecutorTransactionPreflightSpec, plan: dict[str, Any], record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        approval = plan.get("approval_plan") if isinstance(plan.get("approval_plan"), dict) else {}
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        plan_scope = approval.get("approval_scope")
        record_scope = record.get("approval_scope")
        plan_transaction_id = transaction.get("transaction_id")
        record_transaction_id = record.get("transaction_id")
        plan_idempotency_key = transaction.get("idempotency_key")
        record_idempotency_key = record.get("idempotency_key")
        if plan_scope and record_scope and plan_scope != record_scope:
            blockers.append("approval_scope_mismatch")
        if plan_transaction_id and record_transaction_id and plan_transaction_id != record_transaction_id:
            blockers.append("transaction_id_mismatch")
        if plan_idempotency_key and record_idempotency_key and plan_idempotency_key != record_idempotency_key:
            blockers.append("idempotency_key_mismatch")
        if spec.expected_approval_scope and spec.expected_approval_scope not in {plan_scope, record_scope}:
            blockers.append("expected_approval_scope_mismatch")
        if spec.expected_transaction_id and spec.expected_transaction_id not in {plan_transaction_id, record_transaction_id}:
            blockers.append("expected_transaction_id_mismatch")
        if spec.expected_idempotency_key and spec.expected_idempotency_key not in {plan_idempotency_key, record_idempotency_key}:
            blockers.append("expected_idempotency_key_mismatch")
        plan_digest = cls._digest(plan)
        record_plan_digest = record.get("approval_plan_digest_sha256")
        if record_plan_digest and record_plan_digest != plan_digest:
            blockers.append("approval_plan_digest_mismatch")
        if spec.expected_plan_digest_sha256 and spec.expected_plan_digest_sha256 not in {plan_digest, record_plan_digest}:
            blockers.append("expected_plan_digest_mismatch")
        preflight_digest = cls._preflight_digest(plan)
        record_preflight_digest = record.get("preflight_digest_sha256")
        if record_preflight_digest and preflight_digest and record_preflight_digest != preflight_digest:
            blockers.append("preflight_digest_mismatch")
        if spec.expected_preflight_digest_sha256 and spec.expected_preflight_digest_sha256 not in {preflight_digest, record_preflight_digest}:
            blockers.append("expected_preflight_digest_mismatch")
        return blockers

    @staticmethod
    def _no_heap_side_effect_blockers(descriptor: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
        pairs = (
            ("raw_heap_loaded", "raw_heap_loaded"),
            ("raw_heap_parsed", "raw_heap_parsed"),
            ("raw_heap_exported", "raw_heap_exported"),
            ("heap_diff_computed", "heap_diff_computed"),
            ("heap_snapshot_diff_computed", "heap_snapshot_diff_computed"),
        )
        for key, policy_key in pairs:
            if descriptor.get(key) is True or policy.get(policy_key) is True:
                blockers.append(f"{prefix}_{key}")
        if descriptor.get("complete_heap_traversal_claimed") is True or policy.get("complete_heap_traversal") is True:
            blockers.append(f"{prefix}_complete_heap_traversal_claimed")
        return blockers

    @staticmethod
    def _approval_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        approval = plan.get("approval_plan") if isinstance(plan.get("approval_plan"), dict) else {}
        return {
            "approval_scope": record.get("approval_scope") or approval.get("approval_scope"),
            "reviewer": record.get("reviewer") or approval.get("reviewer"),
            "approval_record_artifact": approval.get("approval_record_artifact") or record.get("artifact_path"),
            "approval_recorded": bool(record.get("approval_recorded")),
            "approved_for_execution": bool(record.get("approved_for_execution")),
        }

    @staticmethod
    def _transaction_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        gates = record.get("executor_input_gates") if isinstance(record.get("executor_input_gates"), dict) else {}
        return {
            "transaction_id": record.get("transaction_id") or transaction.get("transaction_id"),
            "idempotency_key": record.get("idempotency_key") or transaction.get("idempotency_key"),
            "transaction_journal_artifact": transaction.get("transaction_journal_artifact"),
            "bounded_gate_artifact": transaction.get("bounded_gate_artifact"),
            "result_artifact": transaction.get("result_artifact"),
            "transaction_started": bool(gates.get("transaction_started")) or bool(transaction.get("transaction_started")),
            "journal_written": bool(gates.get("journal_written")) or bool(transaction.get("journal_written_now")),
            "bounded_executor_gate_written": bool(gates.get("bounded_executor_gate_written")),
            "executor_invoked": bool(gates.get("executor_invoked")) or bool(record.get("executor_invoked")),
        }

    @staticmethod
    def _preflight_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        summary = plan.get("preflight_summary") if isinstance(plan.get("preflight_summary"), dict) else {}
        return {
            "before_digest": summary.get("before_digest"),
            "after_digest": summary.get("after_digest"),
            "preflight_digest_sha256": record.get("preflight_digest_sha256") or HeapSnapshotDiffExecutorTransactionPreflightManager._digest(summary) if summary else record.get("preflight_digest_sha256"),
            "raw_heap_ingestion_policy": summary.get("raw_heap_ingestion_policy"),
            "parser_sandbox": summary.get("parser_sandbox"),
            "redaction_plan": summary.get("redaction_plan"),
            "max_raw_heap_bytes": summary.get("max_raw_heap_bytes"),
        }

    @classmethod
    def _guard_summary(cls, spec: HeapSnapshotDiffExecutorTransactionPreflightSpec | None, plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return {
            "expected_approval_scope": spec.expected_approval_scope if spec else None,
            "expected_transaction_id": spec.expected_transaction_id if spec else None,
            "expected_idempotency_key": spec.expected_idempotency_key if spec else None,
            "expected_plan_digest_sha256": spec.expected_plan_digest_sha256 if spec else None,
            "expected_preflight_digest_sha256": spec.expected_preflight_digest_sha256 if spec else None,
            "approval_plan_digest_sha256": cls._digest(plan) if plan else None,
            "approval_record_digest_sha256": cls._digest(record) if record else None,
            "recorded_plan_digest_sha256": record.get("approval_plan_digest_sha256") if isinstance(record, dict) else None,
            "recorded_preflight_digest_sha256": record.get("preflight_digest_sha256") if isinstance(record, dict) else None,
        }

    def _descriptor(
        self,
        spec: HeapSnapshotDiffExecutorTransactionPreflightSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        approval_summary: dict[str, Any],
        transaction_summary: dict[str, Any],
        preflight_summary: dict[str, Any],
        guard_summary: dict[str, Any],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-preflight.v1",
            "status": status,
            "read_only": True,
            "review_only": True,
            "transaction_preflight_only": True,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "approval_summary": approval_summary,
            "transaction_summary": transaction_summary,
            "preflight_summary": preflight_summary,
            "guard_summary": guard_summary,
            "journal_writer_contract": {
                "implemented": False,
                "ready_for_journal_review": status == "ready_for_review",
                "requires_ready_transaction_preflight": True,
                "requires_explicit_review": True,
                "requires_transaction_id": True,
                "requires_idempotency_key": True,
                "transaction_journal_artifact": transaction_summary.get("transaction_journal_artifact") or "workspace/heap-snapshot-diff-executor-journal.json",
            },
            "future_executor_contract": {
                "implemented": False,
                "requires_written_transaction_journal": True,
                "requires_bounded_executor_gate": True,
                "requires_safe_raw_heap_parser": True,
                "requires_redacted_result_artifact": True,
                "result_artifact": transaction_summary.get("result_artifact") or "workspace/heap-snapshot-diff-executor-result.json",
            },
            "safety_gates": {
                "ready_to_write_journal": status == "ready_for_review",
                "ready_to_execute_now": False,
                "approval_record_verified": bool(approval_summary.get("approval_recorded")) and bool(approval_summary.get("approved_for_execution")) and not blockers,
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "complete_heap_traversal_claimed": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_executor_transaction_journal_writer" if not blockers else "resolve_heap_snapshot_diff_executor_transaction_preflight_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "transaction_preflight_only": True,
            "default_recon": False,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @classmethod
    def _preflight_digest(cls, plan: dict[str, Any]) -> str | None:
        summary = plan.get("preflight_summary") if isinstance(plan.get("preflight_summary"), dict) else {}
        return cls._digest(summary) if summary else None

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()


@dataclass(slots=True)
class HeapSnapshotDiffExecutorBoundedGateSpec:
    """Read-only bounded executor gate after a written heap diff transaction journal.

    This descriptor consumes the explicit transaction journal audit record and prepares
    a future bounded heap diff executor review input. It does not write a gate file,
    invoke an executor, load / parse / export raw heap data, or compute heap diffs.
    """

    transaction_journal_descriptor: dict[str, Any] | None = None
    reviewer: str | None = None
    expected_journal_id: str | None = None
    expected_transaction_preflight_id: str | None = None
    expected_transaction_id: str | None = None
    expected_idempotency_key: str | None = None
    expected_journal_digest_sha256: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffExecutorBoundedGateSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_executor_bounded_gate",
                "heapSnapshotDiffExecutorBoundedGate",
                "heap_snapshot_diff_executor_bounded_executor_gate",
                "heapSnapshotDiffExecutorBoundedExecutorGate",
                "heap_snapshot_diff_bounded_gate",
                "heapSnapshotDiffBoundedGate",
                "heap_diff_executor_bounded_gate",
                "heapDiffExecutorBoundedGate",
                "raw_heap_diff_bounded_gate",
                "rawHeapDiffBoundedGate",
                "review_heap_snapshot_diff_executor_bounded_gate",
                "reviewHeapSnapshotDiffExecutorBoundedGate",
            )
        )
        journal = context.get(
            "heap_snapshot_diff_executor_transaction_journal",
            context.get(
                "heapSnapshotDiffExecutorTransactionJournal",
                context.get(
                    "heap_snapshot_diff_executor_journal",
                    context.get(
                        "heapSnapshotDiffExecutorJournal",
                        context.get("heap_snapshot_diff_executor_transaction_journal_descriptor", context.get("heapSnapshotDiffExecutorTransactionJournalDescriptor")),
                    ),
                ),
            ),
        )
        if not requested and not journal:
            return None
        expected_journal_id = context.get("expected_journal_id", context.get("expectedJournalId"))
        expected_transaction_preflight_id = context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId"))
        expected_transaction_id = context.get("expected_transaction_id", context.get("expectedTransactionId"))
        expected_idempotency_key = context.get("expected_idempotency_key", context.get("expectedIdempotencyKey"))
        expected_journal_digest_sha256 = context.get("expected_journal_digest_sha256", context.get("expectedJournalDigestSha256"))
        return cls(
            transaction_journal_descriptor=journal if isinstance(journal, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            expected_journal_id=str(expected_journal_id).strip() if expected_journal_id else None,
            expected_transaction_preflight_id=str(expected_transaction_preflight_id).strip() if expected_transaction_preflight_id else None,
            expected_transaction_id=str(expected_transaction_id).strip() if expected_transaction_id else None,
            expected_idempotency_key=str(expected_idempotency_key).strip() if expected_idempotency_key else None,
            expected_journal_digest_sha256=str(expected_journal_digest_sha256).strip() if expected_journal_digest_sha256 else None,
        )


@dataclass(slots=True)
class HeapSnapshotDiffExecutorBoundedGateResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffExecutorBoundedGateManager:
    """Review-only bounded gate for a future heap snapshot diff executor."""

    def review(self, spec: HeapSnapshotDiffExecutorBoundedGateSpec | None) -> HeapSnapshotDiffExecutorBoundedGateResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._base_descriptor(status="blocked", reason="missing_heap_snapshot_diff_executor_bounded_gate_request")
            return HeapSnapshotDiffExecutorBoundedGateResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_diff_executor_bounded_gate_request")

        journal = spec.transaction_journal_descriptor or {}
        journal_digest = self._digest(journal) if journal else ""
        gates = journal.get("executor_input_gates") if isinstance(journal.get("executor_input_gates"), dict) else {}
        journal_summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
        preflight_summary = journal.get("preflight_summary") if isinstance(journal.get("preflight_summary"), dict) else {}
        checks = self._checks(
            spec=spec,
            journal=journal,
            gates=gates,
            journal_summary=journal_summary,
            journal_digest=journal_digest,
        )
        blockers = [check["name"] for check in checks if not check["passed"]]
        ready = not blockers
        descriptor = self._descriptor(
            spec=spec,
            journal=journal,
            gates=gates,
            journal_summary=journal_summary,
            preflight_summary=preflight_summary,
            journal_digest=journal_digest,
            blockers=blockers,
            checks=checks,
            side_effect_policy=policy,
        )
        return HeapSnapshotDiffExecutorBoundedGateResult(status="ready_for_review" if ready else "blocked", descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1",
            "status": status,
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "reason": reason,
            "source_transaction_journal_schema_version": "",
            "source_transaction_journal_status": "",
            "source_transaction_journal_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "transaction_id": "",
            "idempotency_key": "",
            "approval_scope": "",
            "reviewer": None,
            "transaction_journal_verified": False,
            "bounded_executor_gate_ready_for_review": False,
            "ready_for_executor_review": False,
            "ready_to_execute_now": False,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "bounded_executor_input": {},
            "future_executor_contract": {},
            "source_journal_summary": {},
            "checks": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_written_heap_snapshot_diff_executor_transaction_journal",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _descriptor(
        self,
        *,
        spec: HeapSnapshotDiffExecutorBoundedGateSpec,
        journal: dict[str, Any],
        gates: dict[str, Any],
        journal_summary: dict[str, Any],
        preflight_summary: dict[str, Any],
        journal_digest: str,
        blockers: list[str],
        checks: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        ready = not blockers
        transaction_id = str(journal.get("transaction_id") or "")
        idempotency_key = str(journal.get("idempotency_key") or "")
        result_artifact = "workspace/heap-snapshot-diff-executor-result.json"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1",
            "status": "ready_for_review" if ready else "blocked",
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "source_transaction_journal_schema_version": str(journal.get("schema_version") or ""),
            "source_transaction_journal_status": str(journal.get("status") or ""),
            "source_transaction_journal_digest_sha256": journal_digest,
            "expected_journal_digest_sha256": spec.expected_journal_digest_sha256,
            "journal_id": str(journal.get("journal_id") or ""),
            "transaction_preflight_id": str(journal.get("transaction_preflight_id") or ""),
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "approval_scope": str(journal.get("approval_scope") or ""),
            "reviewer": spec.reviewer,
            "transaction_journal_verified": ready,
            "bounded_executor_gate_ready_for_review": ready,
            "ready_for_executor_review": ready,
            "ready_to_execute_now": False,
            "transaction_started": bool(journal.get("transaction_started")),
            "journal_written": bool(journal.get("journal_written")),
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "diff_executor_implemented": False,
            "bounded_executor_input": self._bounded_executor_input(journal, gates, preflight_summary, result_artifact, ready),
            "future_executor_contract": self._future_executor_contract(result_artifact, ready),
            "source_journal_summary": self._journal_summary(journal, journal_summary, gates),
            "checks": checks,
            "blockers": blockers,
            "warnings": self._warnings(ready),
            "next_action": self._next_action(blockers),
            "side_effect_policy": side_effect_policy,
        }

    @classmethod
    def _checks(
        cls,
        *,
        spec: HeapSnapshotDiffExecutorBoundedGateSpec,
        journal: dict[str, Any],
        gates: dict[str, Any],
        journal_summary: dict[str, Any],
        journal_digest: str,
    ) -> list[dict[str, Any]]:
        blockers = journal.get("blockers") if isinstance(journal.get("blockers"), list) else []
        policy = journal.get("side_effect_policy") if isinstance(journal.get("side_effect_policy"), dict) else {}
        return [
            {"name": "transaction_journal_available", "passed": bool(journal), "details": {"journal_id": journal.get("journal_id")}},
            {"name": "transaction_journal_schema_matches", "passed": journal.get("schema_version") == "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1", "details": {"schema_version": journal.get("schema_version")}},
            {"name": "transaction_journal_written", "passed": journal.get("status") == "written" and journal.get("journal_written") is True, "details": {"status": journal.get("status"), "journal_written": journal.get("journal_written")}},
            {"name": "transaction_started", "passed": journal.get("transaction_started") is True and journal_summary.get("transaction_started") is True, "details": {"transaction_started": journal.get("transaction_started"), "summary_transaction_started": journal_summary.get("transaction_started")}},
            {"name": "journal_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "bounded_gate_followup_required", "passed": gates.get("requires_bounded_executor_gate") is True or journal_summary.get("requires_bounded_executor_gate_followup") is True, "details": {"gate_requires_bounded_executor_gate": gates.get("requires_bounded_executor_gate"), "summary_requires_bounded_executor_gate_followup": journal_summary.get("requires_bounded_executor_gate_followup")}},
            {"name": "explicit_executor_review_required", "passed": gates.get("requires_explicit_executor_review") is True, "details": {"requires_explicit_executor_review": gates.get("requires_explicit_executor_review")}},
            {"name": "journal_not_ready_to_execute_now", "passed": journal.get("ready_to_execute_now") is not True and gates.get("ready_to_execute_now") is not True, "details": {"journal_ready_to_execute_now": journal.get("ready_to_execute_now"), "gate_ready_to_execute_now": gates.get("ready_to_execute_now")}},
            {"name": "bounded_gate_not_already_written", "passed": journal.get("bounded_executor_gate_written") is not True and journal_summary.get("bounded_executor_gate_written") is not True and gates.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"journal_bounded_executor_gate_written": journal.get("bounded_executor_gate_written"), "summary_bounded_executor_gate_written": journal_summary.get("bounded_executor_gate_written"), "gate_bounded_executor_gate_written": gates.get("bounded_executor_gate_written"), "policy_bounded_executor_gate_written": policy.get("bounded_executor_gate_written")}},
            {"name": "executor_not_invoked", "passed": journal.get("executor_invoked") is not True and journal_summary.get("executor_invoked") is not True and gates.get("executor_invoked") is not True and policy.get("executor_invoked") is not True, "details": {"journal_executor_invoked": journal.get("executor_invoked"), "summary_executor_invoked": journal_summary.get("executor_invoked"), "gate_executor_invoked": gates.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked")}},
            {"name": "raw_heap_not_loaded", "passed": journal.get("raw_heap_loaded") is not True and journal_summary.get("raw_heap_loaded") is not True and gates.get("raw_heap_loaded") is not True and policy.get("raw_heap_loaded") is not True, "details": {"journal_raw_heap_loaded": journal.get("raw_heap_loaded"), "summary_raw_heap_loaded": journal_summary.get("raw_heap_loaded"), "gate_raw_heap_loaded": gates.get("raw_heap_loaded"), "policy_raw_heap_loaded": policy.get("raw_heap_loaded")}},
            {"name": "raw_heap_not_parsed", "passed": journal.get("raw_heap_parsed") is not True and journal_summary.get("raw_heap_parsed") is not True and gates.get("raw_heap_parsed") is not True and policy.get("raw_heap_parsed") is not True, "details": {"journal_raw_heap_parsed": journal.get("raw_heap_parsed"), "summary_raw_heap_parsed": journal_summary.get("raw_heap_parsed"), "gate_raw_heap_parsed": gates.get("raw_heap_parsed"), "policy_raw_heap_parsed": policy.get("raw_heap_parsed")}},
            {"name": "raw_heap_not_exported", "passed": journal.get("raw_heap_exported") is not True and journal_summary.get("raw_heap_exported") is not True and gates.get("raw_heap_exported") is not True and policy.get("raw_heap_exported") is not True, "details": {"journal_raw_heap_exported": journal.get("raw_heap_exported"), "summary_raw_heap_exported": journal_summary.get("raw_heap_exported"), "gate_raw_heap_exported": gates.get("raw_heap_exported"), "policy_raw_heap_exported": policy.get("raw_heap_exported")}},
            {"name": "heap_diff_not_computed", "passed": journal.get("heap_diff_computed") is not True and journal_summary.get("heap_diff_computed") is not True and gates.get("heap_diff_computed") is not True and policy.get("heap_diff_computed") is not True and policy.get("heap_snapshot_diff_computed") is not True, "details": {"journal_heap_diff_computed": journal.get("heap_diff_computed"), "summary_heap_diff_computed": journal_summary.get("heap_diff_computed"), "gate_heap_diff_computed": gates.get("heap_diff_computed"), "policy_heap_diff_computed": policy.get("heap_diff_computed")}},
            {"name": "complete_heap_traversal_not_claimed", "passed": journal.get("complete_heap_traversal_claimed") is not True and gates.get("complete_heap_traversal_claimed") is not True and policy.get("complete_heap_traversal") is not True, "details": {"journal_complete_heap_traversal_claimed": journal.get("complete_heap_traversal_claimed"), "gate_complete_heap_traversal_claimed": gates.get("complete_heap_traversal_claimed"), "policy_complete_heap_traversal": policy.get("complete_heap_traversal")}},
            {"name": "diff_executor_not_implemented", "passed": journal.get("diff_executor_implemented") is not True and gates.get("diff_executor_implemented") is not True, "details": {"journal_diff_executor_implemented": journal.get("diff_executor_implemented"), "gate_diff_executor_implemented": gates.get("diff_executor_implemented")}},
            {"name": "approval_scope_supported", "passed": journal.get("approval_scope") == "heap-snapshot-diff-executor", "details": {"approval_scope": journal.get("approval_scope")}},
            {"name": "transaction_id_present", "passed": bool(journal.get("transaction_id")), "details": {"transaction_id": journal.get("transaction_id")}},
            {"name": "idempotency_key_present", "passed": bool(journal.get("idempotency_key")), "details": {"idempotency_key": journal.get("idempotency_key")}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or journal.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": journal.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or journal.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": journal.get("transaction_preflight_id")}},
            {"name": "expected_transaction_id_matches", "passed": not spec.expected_transaction_id or journal.get("transaction_id") == spec.expected_transaction_id, "details": {"expected_transaction_id": spec.expected_transaction_id, "transaction_id": journal.get("transaction_id")}},
            {"name": "expected_idempotency_key_matches", "passed": not spec.expected_idempotency_key or journal.get("idempotency_key") == spec.expected_idempotency_key, "details": {"expected_idempotency_key": spec.expected_idempotency_key, "idempotency_key": journal.get("idempotency_key")}},
            {"name": "expected_journal_digest_matches", "passed": not spec.expected_journal_digest_sha256 or journal_digest == spec.expected_journal_digest_sha256, "details": {"expected_journal_digest_sha256": spec.expected_journal_digest_sha256, "transaction_journal_digest_sha256": journal_digest}},
            {"name": "journal_has_no_forbidden_runtime_side_effects", "passed": cls._journal_has_no_forbidden_runtime_side_effects(policy), "details": policy},
        ]

    @staticmethod
    def _bounded_executor_input(journal: dict[str, Any], gates: dict[str, Any], preflight_summary: dict[str, Any], result_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-bounded-input.v1",
            "journal_id": journal.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id"),
            "transaction_id": journal.get("transaction_id"),
            "idempotency_key": journal.get("idempotency_key"),
            "approval_scope": journal.get("approval_scope"),
            "result_artifact": result_artifact,
            "ready_for_executor_review": ready,
            "ready_to_execute_now": False,
            "requires_separate_executor_call": True,
            "requires_explicit_executor_review": True,
            "requires_safe_raw_heap_parser": True,
            "requires_redacted_result_artifact": True,
            "requires_no_raw_heap_export": True,
            "requires_no_complete_traversal_claim": True,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_diff_computed": False,
            "diff_executor_implemented": False,
            "preflight_summary": {
                "before_digest": preflight_summary.get("before_digest"),
                "after_digest": preflight_summary.get("after_digest"),
                "raw_heap_ingestion_policy": preflight_summary.get("raw_heap_ingestion_policy"),
                "parser_sandbox": preflight_summary.get("parser_sandbox"),
                "redaction_plan": preflight_summary.get("redaction_plan"),
                "max_raw_heap_bytes": preflight_summary.get("max_raw_heap_bytes"),
            },
            "source_executor_input_gates": {
                "approval_record_verified": bool(gates.get("approval_record_verified")),
                "transaction_started": bool(gates.get("transaction_started")),
                "journal_written": bool(gates.get("journal_written")),
                "requires_bounded_executor_gate": bool(gates.get("requires_bounded_executor_gate")),
                "requires_explicit_executor_review": bool(gates.get("requires_explicit_executor_review")),
            },
        }

    @staticmethod
    def _future_executor_contract(result_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-contract.v1",
            "executor_name": "execute_heap_snapshot_diff_executor",
            "implemented": False,
            "contract_ready_for_review": ready,
            "result_artifact": result_artifact,
            "requires_written_transaction_journal": True,
            "requires_bounded_executor_gate": True,
            "requires_explicit_executor_review": True,
            "requires_safe_raw_heap_parser": True,
            "requires_redacted_result_artifact": True,
            "requires_no_raw_heap_export": True,
            "requires_no_complete_traversal_claim": True,
        }

    @staticmethod
    def _journal_summary(journal: dict[str, Any], journal_summary: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": journal.get("schema_version"),
            "status": journal.get("status"),
            "journal_id": journal.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id"),
            "transaction_id": journal.get("transaction_id"),
            "idempotency_key": journal.get("idempotency_key"),
            "approval_scope": journal.get("approval_scope"),
            "transaction_started": bool(journal.get("transaction_started")) or bool(journal_summary.get("transaction_started")) or bool(gates.get("transaction_started")),
            "journal_written": bool(journal.get("journal_written")) or bool(journal_summary.get("journal_written")) or bool(gates.get("journal_written")),
            "requires_bounded_executor_gate_followup": bool(journal_summary.get("requires_bounded_executor_gate_followup")) or bool(gates.get("requires_bounded_executor_gate")),
            "bounded_executor_gate_written": bool(journal_summary.get("bounded_executor_gate_written")) or bool(gates.get("bounded_executor_gate_written")),
            "executor_invoked": bool(journal_summary.get("executor_invoked")) or bool(gates.get("executor_invoked")),
            "raw_heap_loaded": bool(journal_summary.get("raw_heap_loaded")) or bool(gates.get("raw_heap_loaded")),
            "raw_heap_parsed": bool(journal_summary.get("raw_heap_parsed")) or bool(gates.get("raw_heap_parsed")),
            "raw_heap_exported": bool(journal_summary.get("raw_heap_exported")) or bool(gates.get("raw_heap_exported")),
            "heap_diff_computed": bool(journal_summary.get("heap_diff_computed")) or bool(gates.get("heap_diff_computed")),
        }

    @staticmethod
    def _warnings(ready: bool) -> list[str]:
        warnings = ["heap_snapshot_diff_executor_bounded_gate_is_not_executor", "heap_snapshot_diff_executor_raw_heap_parser_required_after_gate"]
        if ready:
            warnings.append("heap_snapshot_diff_executor_bounded_gate_ready_for_executor_review")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            return "provide_written_heap_snapshot_diff_executor_transaction_journal"
        return "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "ready_to_execute_now": False,
            "executor_invoked": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _journal_has_no_forbidden_runtime_side_effects(policy: dict[str, Any]) -> bool:
        return not any(
            bool(policy.get(key))
            for key in (
                "bounded_executor_gate_written",
                "ready_to_execute_now",
                "executor_invoked",
                "browser_started",
                "provider_factory_invoked",
                "provider_availability_checked",
                "cdp_command_sent",
                "heap_profiler_enabled",
                "heap_snapshot_collected",
                "heap_snapshot_diff_computed",
                "heap_diff_computed",
                "raw_heap_loaded",
                "raw_heap_parsed",
                "raw_heap_exported",
                "complete_heap_traversal",
                "runtime_evaluated",
                "javascript_evaluated",
                "calls_mcp",
                "mobile_runtime_used",
            )
        )

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()


@dataclass(slots=True)
class HeapSnapshotDiffFollowupCheckpointSpec:
    """Read-only checkpoint that turns a summary diff result into reviewed next-step guidance."""

    executor_result: dict[str, Any] | None = None
    reviewer: str | None = None
    require_executed_result: bool = True
    min_node_delta_for_drilldown: int = 1
    min_self_size_delta_for_drilldown: int = 1
    allow_retained_size_planning: bool = True
    allow_path_to_root_planning: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffFollowupCheckpointSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_followup_checkpoint",
                "heapSnapshotDiffFollowupCheckpoint",
                "heap_snapshot_diff_analysis_plan",
                "heapSnapshotDiffAnalysisPlan",
                "review_heap_snapshot_diff_followup_checkpoint",
                "reviewHeapSnapshotDiffFollowupCheckpoint",
                "review_heap_snapshot_diff_executor_result_followup",
                "reviewHeapSnapshotDiffExecutorResultFollowup",
            )
        )
        executor_result = context.get(
            "heap_snapshot_diff_executor_result",
            context.get(
                "heapSnapshotDiffExecutorResult",
                context.get("heap_snapshot_diff_executor_result_descriptor", context.get("heapSnapshotDiffExecutorResultDescriptor")),
            ),
        )
        if not requested and not executor_result:
            return None
        return cls(
            executor_result=executor_result if isinstance(executor_result, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            require_executed_result=bool(context.get("require_executed_result", context.get("requireExecutedResult", True))),
            min_node_delta_for_drilldown=max(0, int(context.get("min_node_delta_for_drilldown", context.get("minNodeDeltaForDrilldown", 1)) or 0)),
            min_self_size_delta_for_drilldown=max(0, int(context.get("min_self_size_delta_for_drilldown", context.get("minSelfSizeDeltaForDrilldown", 1)) or 0)),
            allow_retained_size_planning=bool(context.get("allow_retained_size_planning", context.get("allowRetainedSizePlanning", True))),
            allow_path_to_root_planning=bool(context.get("allow_path_to_root_planning", context.get("allowPathToRootPlanning", True))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffFollowupCheckpointResult:
    status: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checkpoint": self.checkpoint,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffFollowupCheckpointManager:
    """Review-only follow-up planner for heap snapshot summary diff executor results."""

    def review(self, spec: HeapSnapshotDiffFollowupCheckpointSpec | None) -> HeapSnapshotDiffFollowupCheckpointResult:
        policy = self._side_effect_policy()
        if spec is None:
            checkpoint = self._checkpoint(None, ["missing_heap_snapshot_diff_followup_checkpoint_request"], [], {}, {}, policy)
            return HeapSnapshotDiffFollowupCheckpointResult(status="blocked", checkpoint=checkpoint, side_effect_policy=policy, reason="missing_heap_snapshot_diff_followup_checkpoint_request")
        blockers, warnings, result_summary = self._validate_result(spec)
        analysis = self._analysis_plan(spec, result_summary) if not blockers else {}
        checkpoint = self._checkpoint(spec, blockers, warnings, result_summary, analysis, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotDiffFollowupCheckpointResult(status=status, checkpoint=checkpoint, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_result(self, spec: HeapSnapshotDiffFollowupCheckpointSpec) -> tuple[list[str], list[str], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_diff_followup_checkpoint_review_only"]
        result = spec.executor_result or {}
        if not result:
            blockers.append("heap_snapshot_diff_executor_result_required")
            return blockers, warnings, {}
        if result.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-executor-result.v1":
            blockers.append("heap_snapshot_diff_executor_result_schema_mismatch")
        if spec.require_executed_result and result.get("status") != "executed":
            blockers.append("heap_snapshot_diff_executor_result_not_executed")
        if result.get("raw_heap_exported") is True:
            blockers.append("heap_snapshot_diff_executor_result_raw_heap_exported")
        if result.get("complete_heap_traversal_claimed") is True:
            blockers.append("heap_snapshot_diff_executor_result_complete_traversal_claimed")
        if result.get("raw_heap_parsed") is not True:
            blockers.append("heap_snapshot_diff_executor_result_raw_heap_not_parsed")
        if result.get("heap_diff_computed") is not True and result.get("heap_snapshot_diff_computed") is not True:
            blockers.append("heap_snapshot_diff_executor_result_diff_not_computed")
        policy = result.get("side_effect_policy") if isinstance(result.get("side_effect_policy"), dict) else {}
        if policy.get("raw_heap_exported") is True or policy.get("raw_strings_exported") is True:
            blockers.append("heap_snapshot_diff_executor_result_exported_raw_heap_or_strings")
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_diff_executor_result_forbidden_runtime_side_effect")
        if result.get("summary_only") is not True:
            warnings.append("heap_snapshot_diff_executor_result_summary_only_flag_missing")
        diff = result.get("diff") if isinstance(result.get("diff"), dict) else {}
        heap_summaries = result.get("heap_summaries") if isinstance(result.get("heap_summaries"), dict) else {}
        before = heap_summaries.get("before") if isinstance(heap_summaries.get("before"), dict) else {}
        after = heap_summaries.get("after") if isinstance(heap_summaries.get("after"), dict) else {}
        result_summary = {
            "schema_version": result.get("schema_version"),
            "status": result.get("status"),
            "executor_name": result.get("executor_name"),
            "executor_mvp": bool(result.get("executor_mvp")),
            "result_artifact": result.get("result_artifact", "workspace/heap-snapshot-diff-executor-result.json"),
            "reviewer": result.get("reviewer"),
            "transaction_id": (result.get("gate_summary") or {}).get("transaction_id") if isinstance(result.get("gate_summary"), dict) else None,
            "before_digest": before.get("raw_heap_digest_sha256"),
            "after_digest": after.get("raw_heap_digest_sha256"),
            "before_nodes": before.get("node_count_total"),
            "after_nodes": after.get("node_count_total"),
            "before_edges": before.get("edge_count_total"),
            "after_edges": after.get("edge_count_total"),
            "node_count_delta": int(diff.get("node_count_delta") or 0),
            "edge_count_delta": int(diff.get("edge_count_delta") or 0),
            "self_size_total_analyzed_delta": int(diff.get("self_size_total_analyzed_delta") or 0),
            "analysis_truncated": bool(diff.get("analysis_truncated") or before.get("node_analysis_truncated") or after.get("node_analysis_truncated") or before.get("edge_analysis_truncated") or after.get("edge_analysis_truncated")),
            "node_type_deltas": self._positive_rows(diff.get("node_type_deltas")),
            "edge_type_deltas": self._positive_rows(diff.get("edge_type_deltas")),
            "top_constructor_deltas": self._positive_rows(diff.get("top_constructor_deltas")),
            "raw_heap_exported": bool(result.get("raw_heap_exported")),
            "raw_strings_exported": bool(policy.get("raw_strings_exported")),
            "complete_heap_traversal_claimed": bool(result.get("complete_heap_traversal_claimed")),
            "summary_only": bool(result.get("summary_only")),
        }
        return blockers, warnings, result_summary

    def _analysis_plan(self, spec: HeapSnapshotDiffFollowupCheckpointSpec, summary: dict[str, Any]) -> dict[str, Any]:
        node_delta = abs(int(summary.get("node_count_delta") or 0))
        self_size_delta = abs(int(summary.get("self_size_total_analyzed_delta") or 0))
        constructor_growth = summary.get("top_constructor_deltas") or []
        node_type_growth = summary.get("node_type_deltas") or []
        recommendations: list[dict[str, Any]] = []
        if constructor_growth:
            recommendations.append(
                {
                    "action": "review_constructor_growth",
                    "reason": "constructor_count_delta_observed",
                    "automatic": False,
                    "requires_review": True,
                    "candidate_count": len(constructor_growth),
                }
            )
        if node_type_growth:
            recommendations.append(
                {
                    "action": "review_node_type_growth",
                    "reason": "node_type_delta_observed",
                    "automatic": False,
                    "requires_review": True,
                    "candidate_count": len(node_type_growth),
                }
            )
        if spec.allow_retained_size_planning and (self_size_delta >= spec.min_self_size_delta_for_drilldown or node_delta >= spec.min_node_delta_for_drilldown):
            recommendations.append(
                {
                    "action": "plan_retained_size_analysis",
                    "reason": "summary_delta_exceeds_review_threshold",
                    "automatic": False,
                    "requires_review": True,
                    "implemented": False,
                }
            )
        if spec.allow_path_to_root_planning and constructor_growth:
            recommendations.append(
                {
                    "action": "plan_path_to_root_analysis",
                    "reason": "constructor_growth_requires_root_cause_review",
                    "automatic": False,
                    "requires_review": True,
                    "implemented": False,
                }
            )
        if summary.get("analysis_truncated"):
            recommendations.append(
                {
                    "action": "review_larger_budget_or_scoped_second_pass",
                    "reason": "summary_analysis_was_truncated",
                    "automatic": False,
                    "requires_review": True,
                    "implemented": False,
                }
            )
        if not recommendations:
            recommendations.append(
                {
                    "action": "no_immediate_heap_followup_required",
                    "reason": "no_summary_delta_exceeded_review_threshold",
                    "automatic": False,
                    "requires_review": True,
                }
            )
        return {
            "plan_id": "heap-snapshot-diff-followup-checkpoint",
            "review_only": True,
            "checkpoint_only": True,
            "summary_delta_review": {
                "node_count_delta": summary.get("node_count_delta", 0),
                "edge_count_delta": summary.get("edge_count_delta", 0),
                "self_size_total_analyzed_delta": summary.get("self_size_total_analyzed_delta", 0),
                "analysis_truncated": bool(summary.get("analysis_truncated")),
            },
            "top_growth_signals": {
                "node_type_deltas": summary.get("node_type_deltas", [])[:10],
                "edge_type_deltas": summary.get("edge_type_deltas", [])[:10],
                "constructor_deltas": summary.get("top_constructor_deltas", [])[:10],
            },
            "recommendations": recommendations,
            "future_analysis_contracts": {
                "retained_size_analysis": {"implemented": False, "requires_raw_heap": True, "requires_explicit_review": True},
                "path_to_root_analysis": {"implemented": False, "requires_raw_heap": True, "requires_explicit_review": True},
                "raw_heap_file_ingestion": {"implemented": False, "requires_explicit_review": True},
                "automatic_followup_analysis": {"implemented": False, "allowed": False},
            },
        }

    def _checkpoint(
        self,
        spec: HeapSnapshotDiffFollowupCheckpointSpec | None,
        blockers: list[str],
        warnings: list[str],
        result_summary: dict[str, Any],
        analysis_plan: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1",
            "status": status,
            "checkpoint_name": "heap_snapshot_diff_followup_checkpoint",
            "checkpoint_artifact": "workspace/heap-snapshot-diff-followup-checkpoint.json",
            "review_only": True,
            "checkpoint_only": True,
            "reviewer": spec.reviewer if spec else None,
            "executor_result_summary": result_summary,
            "analysis_plan": analysis_plan,
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work" if not blockers else "resolve_heap_snapshot_diff_followup_checkpoint_blockers",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _positive_rows(rows: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                delta = int(item.get("delta") or 0)
            except Exception as e:
                _logger.debug("Failed to parse delta value from heap diff row: %s", e, exc_info=True)
                delta = 0
            if delta > 0:
                normalized.append({"name": str(item.get("name") or "unknown"), "before": int(item.get("before") or 0), "after": int(item.get("after") or 0), "delta": delta})
        normalized.sort(key=lambda item: int(item["delta"]), reverse=True)
        return normalized

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "checkpoint_only": True,
            "executor_invoked": False,
            "new_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotDiffSelectedAnalysisInputPreflightSpec:
    """Read-only preflight that selects one follow-up heap analysis input.

    This consumes the Step 324 follow-up checkpoint and prepares a reviewed input
    descriptor for a future constructor drilldown / retained-size / path-to-root /
    larger-budget pass. It does not read raw heap files, parse raw heap data again,
    compute retained size, compute path-to-root, or invoke any executor.
    """

    followup_checkpoint: dict[str, Any] | None = None
    selected_action: str | None = None
    selected_candidate_name: str | None = None
    reviewer: str | None = None
    require_ready_checkpoint: bool = True
    require_existing_recommendation: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffSelectedAnalysisInputPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_diff_selected_analysis_input_preflight",
                "heapSnapshotDiffSelectedAnalysisInputPreflight",
                "heap_snapshot_diff_followup_selected_analysis_preflight",
                "heapSnapshotDiffFollowupSelectedAnalysisPreflight",
                "heap_snapshot_diff_selected_followup_preflight",
                "heapSnapshotDiffSelectedFollowupPreflight",
                "review_heap_snapshot_diff_selected_analysis_input",
                "reviewHeapSnapshotDiffSelectedAnalysisInput",
            )
        )
        checkpoint = context.get(
            "heap_snapshot_diff_followup_checkpoint",
            context.get(
                "heapSnapshotDiffFollowupCheckpoint",
                context.get("heap_snapshot_diff_followup_checkpoint_descriptor", context.get("heapSnapshotDiffFollowupCheckpointDescriptor")),
            ),
        )
        if not requested and not checkpoint:
            return None
        return cls(
            followup_checkpoint=checkpoint if isinstance(checkpoint, dict) else None,
            selected_action=str(context.get("selected_analysis_action", context.get("selectedAnalysisAction", context.get("selected_action", context.get("selectedAction", "")))) or "").strip() or None,
            selected_candidate_name=str(context.get("selected_candidate_name", context.get("selectedCandidateName", context.get("candidate_name", context.get("candidateName", "")))) or "").strip() or None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            require_ready_checkpoint=bool(context.get("require_ready_checkpoint", context.get("requireReadyCheckpoint", True))),
            require_existing_recommendation=bool(context.get("require_existing_recommendation", context.get("requireExistingRecommendation", True))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffSelectedAnalysisInputPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "preflight": self.preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotDiffSelectedAnalysisInputPreflightManager:
    """Review-only selector for the next heap diff follow-up analysis input."""

    SUPPORTED_ACTIONS = {
        "review_constructor_growth",
        "review_node_type_growth",
        "plan_retained_size_analysis",
        "plan_path_to_root_analysis",
        "review_larger_budget_or_scoped_second_pass",
        "no_immediate_heap_followup_required",
    }

    RAW_HEAP_REQUIRED_ACTIONS = {
        "plan_retained_size_analysis",
        "plan_path_to_root_analysis",
        "review_larger_budget_or_scoped_second_pass",
    }

    def review(self, spec: HeapSnapshotDiffSelectedAnalysisInputPreflightSpec | None) -> HeapSnapshotDiffSelectedAnalysisInputPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            preflight = self._preflight(None, ["missing_heap_snapshot_diff_selected_analysis_input_preflight_request"], [], {}, {}, {}, policy)
            return HeapSnapshotDiffSelectedAnalysisInputPreflightResult(status="blocked", preflight=preflight, side_effect_policy=policy, reason="missing_heap_snapshot_diff_selected_analysis_input_preflight_request")
        blockers, warnings, checkpoint_summary, selected, selected_input = self._validate_and_select(spec)
        preflight = self._preflight(spec, blockers, warnings, checkpoint_summary, selected, selected_input, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotDiffSelectedAnalysisInputPreflightResult(status=status, preflight=preflight, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_and_select(self, spec: HeapSnapshotDiffSelectedAnalysisInputPreflightSpec) -> tuple[list[str], list[str], dict[str, Any], dict[str, Any], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_diff_selected_analysis_input_preflight_review_only"]
        checkpoint = spec.followup_checkpoint or {}
        if not checkpoint:
            blockers.append("heap_snapshot_diff_followup_checkpoint_required")
            return blockers, warnings, {}, {}, {}
        if checkpoint.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1":
            blockers.append("heap_snapshot_diff_followup_checkpoint_schema_mismatch")
        if spec.require_ready_checkpoint and checkpoint.get("status") != "ready_for_review":
            blockers.append("heap_snapshot_diff_followup_checkpoint_not_ready")
        if checkpoint.get("review_only") is not True or checkpoint.get("checkpoint_only") is not True:
            blockers.append("heap_snapshot_diff_followup_checkpoint_not_review_checkpoint")
        policy = checkpoint.get("side_effect_policy") if isinstance(checkpoint.get("side_effect_policy"), dict) else {}
        if checkpoint.get("raw_heap_loaded") is True or checkpoint.get("raw_heap_parsed") is True or policy.get("raw_heap_loaded") is True or policy.get("raw_heap_parsed") is True:
            blockers.append("heap_snapshot_diff_followup_checkpoint_claims_raw_heap_work")
        if checkpoint.get("heap_diff_computed") is True or checkpoint.get("new_heap_diff_computed") is True or policy.get("heap_diff_computed") is True:
            blockers.append("heap_snapshot_diff_followup_checkpoint_claims_new_diff")
        if checkpoint.get("retained_size_proven") is True or checkpoint.get("path_to_root_computed") is True:
            blockers.append("heap_snapshot_diff_followup_checkpoint_claims_followup_analysis")
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_diff_followup_checkpoint_forbidden_runtime_side_effect")
        analysis = checkpoint.get("analysis_plan") if isinstance(checkpoint.get("analysis_plan"), dict) else {}
        recommendations = analysis.get("recommendations") if isinstance(analysis.get("recommendations"), list) else []
        normalized_recommendations = [item for item in recommendations if isinstance(item, dict)]
        if not normalized_recommendations:
            blockers.append("heap_snapshot_diff_followup_recommendations_required")
        selected = self._select_recommendation(normalized_recommendations, spec.selected_action)
        if not selected and normalized_recommendations and spec.require_existing_recommendation:
            blockers.append("heap_snapshot_diff_selected_action_not_recommended")
        selected_action = str((selected or {}).get("action") or spec.selected_action or "").strip()
        if selected_action and selected_action not in self.SUPPORTED_ACTIONS:
            blockers.append("heap_snapshot_diff_selected_action_unsupported")
        if not selected_action and normalized_recommendations:
            selected_action = str(normalized_recommendations[0].get("action") or "")
            selected = dict(normalized_recommendations[0])
        checkpoint_summary = self._checkpoint_summary(checkpoint, normalized_recommendations)
        selected_input = self._selected_input(checkpoint, selected_action, spec.selected_candidate_name)
        return list(dict.fromkeys(blockers)), warnings, checkpoint_summary, selected or {}, selected_input

    @staticmethod
    def _select_recommendation(recommendations: list[dict[str, Any]], selected_action: str | None) -> dict[str, Any]:
        if selected_action:
            for item in recommendations:
                if str(item.get("action") or "") == selected_action:
                    return dict(item)
            return {}
        return dict(recommendations[0]) if recommendations else {}

    def _selected_input(self, checkpoint: dict[str, Any], selected_action: str, selected_candidate_name: str | None) -> dict[str, Any]:
        analysis = checkpoint.get("analysis_plan") if isinstance(checkpoint.get("analysis_plan"), dict) else {}
        signals = analysis.get("top_growth_signals") if isinstance(analysis.get("top_growth_signals"), dict) else {}
        constructors = signals.get("constructor_deltas") if isinstance(signals.get("constructor_deltas"), list) else []
        node_types = signals.get("node_type_deltas") if isinstance(signals.get("node_type_deltas"), list) else []
        edge_types = signals.get("edge_type_deltas") if isinstance(signals.get("edge_type_deltas"), list) else []
        candidates = self._candidate_rows(selected_action, constructors, node_types, edge_types, selected_candidate_name)
        raw_heap_required = selected_action in self.RAW_HEAP_REQUIRED_ACTIONS
        return {
            "selected_action": selected_action,
            "selected_candidate_name": selected_candidate_name,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "source_summary_delta_review": analysis.get("summary_delta_review") if isinstance(analysis.get("summary_delta_review"), dict) else {},
            "raw_heap_required_for_future_executor": raw_heap_required,
            "raw_heap_available_in_this_preflight": False,
            "requires_explicit_review_before_execution": True,
            "requires_separate_executor": selected_action != "no_immediate_heap_followup_required",
            "would_execute_in_this_preflight": False,
        }

    @staticmethod
    def _candidate_rows(selected_action: str, constructors: list[Any], node_types: list[Any], edge_types: list[Any], selected_candidate_name: str | None) -> list[dict[str, Any]]:
        if selected_action in {"review_constructor_growth", "plan_path_to_root_analysis"}:
            rows = constructors
        elif selected_action == "review_node_type_growth":
            rows = node_types
        elif selected_action == "plan_retained_size_analysis":
            rows = constructors or node_types
        elif selected_action == "review_larger_budget_or_scoped_second_pass":
            rows = constructors or node_types or edge_types
        else:
            rows = []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if selected_candidate_name and name != selected_candidate_name:
                continue
            candidates.append({
                "name": name,
                "before": int(item.get("before") or 0),
                "after": int(item.get("after") or 0),
                "delta": int(item.get("delta") or 0),
                "source": "summary_diff_followup_checkpoint",
                "raw_value_exported": False,
            })
        return candidates[:10]

    @staticmethod
    def _checkpoint_summary(checkpoint: dict[str, Any], recommendations: list[dict[str, Any]]) -> dict[str, Any]:
        result_summary = checkpoint.get("executor_result_summary") if isinstance(checkpoint.get("executor_result_summary"), dict) else {}
        analysis = checkpoint.get("analysis_plan") if isinstance(checkpoint.get("analysis_plan"), dict) else {}
        delta = analysis.get("summary_delta_review") if isinstance(analysis.get("summary_delta_review"), dict) else {}
        return {
            "schema_version": checkpoint.get("schema_version"),
            "status": checkpoint.get("status"),
            "checkpoint_artifact": checkpoint.get("checkpoint_artifact", "workspace/heap-snapshot-diff-followup-checkpoint.json"),
            "checkpoint_name": checkpoint.get("checkpoint_name"),
            "transaction_id": result_summary.get("transaction_id"),
            "executor_result_status": result_summary.get("status"),
            "executor_result_artifact": result_summary.get("result_artifact"),
            "node_count_delta": delta.get("node_count_delta"),
            "edge_count_delta": delta.get("edge_count_delta"),
            "self_size_total_analyzed_delta": delta.get("self_size_total_analyzed_delta"),
            "analysis_truncated": bool(delta.get("analysis_truncated")),
            "recommendation_count": len(recommendations),
            "recommended_actions": [str(item.get("action") or "") for item in recommendations],
        }

    def _preflight(
        self,
        spec: HeapSnapshotDiffSelectedAnalysisInputPreflightSpec | None,
        blockers: list[str],
        warnings: list[str],
        checkpoint_summary: dict[str, Any],
        selected_recommendation: dict[str, Any],
        selected_input: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        selected_action = str(selected_input.get("selected_action") or selected_recommendation.get("action") or "")
        raw_heap_required = bool(selected_input.get("raw_heap_required_for_future_executor"))
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-selected-analysis-input-preflight.v1",
            "status": status,
            "preflight_name": "heap_snapshot_diff_selected_analysis_input_preflight",
            "preflight_artifact": "workspace/heap-snapshot-diff-selected-analysis-input-preflight.json",
            "review_only": True,
            "preflight_only": True,
            "selection_only": True,
            "reviewer": spec.reviewer if spec else None,
            "source_checkpoint_summary": checkpoint_summary,
            "selected_recommendation": selected_recommendation,
            "selected_analysis_input": selected_input,
            "future_executor_contract": {
                "implemented": False,
                "selected_action": selected_action,
                "executor_name": self._future_executor_name(selected_action),
                "requires_explicit_review": True,
                "requires_raw_heap": raw_heap_required,
                "requires_raw_heap_ingestion_preflight": raw_heap_required,
                "result_artifact": self._future_result_artifact(selected_action),
                "automatic_execution_allowed": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": self._next_action(blockers, selected_action),
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "constructor_drilldown_computed": False,
            "larger_budget_second_pass_computed": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _future_executor_name(selected_action: str) -> str:
        mapping = {
            "review_constructor_growth": "review_heap_snapshot_constructor_growth_drilldown",
            "review_node_type_growth": "review_heap_snapshot_node_type_growth_drilldown",
            "plan_retained_size_analysis": "execute_heap_snapshot_retained_size_analysis",
            "plan_path_to_root_analysis": "execute_heap_snapshot_path_to_root_analysis",
            "review_larger_budget_or_scoped_second_pass": "execute_heap_snapshot_diff_larger_budget_second_pass",
            "no_immediate_heap_followup_required": "none",
        }
        return mapping.get(selected_action, "unknown")

    @staticmethod
    def _future_result_artifact(selected_action: str) -> str:
        mapping = {
            "review_constructor_growth": "workspace/heap-snapshot-constructor-growth-drilldown.json",
            "review_node_type_growth": "workspace/heap-snapshot-node-type-growth-drilldown.json",
            "plan_retained_size_analysis": "workspace/heap-snapshot-retained-size-analysis.json",
            "plan_path_to_root_analysis": "workspace/heap-snapshot-path-to-root-analysis.json",
            "review_larger_budget_or_scoped_second_pass": "workspace/heap-snapshot-diff-larger-budget-result.json",
            "no_immediate_heap_followup_required": "",
        }
        return mapping.get(selected_action, "")

    @staticmethod
    def _next_action(blockers: list[str], selected_action: str) -> str:
        if blockers:
            return "resolve_heap_snapshot_diff_selected_analysis_input_preflight_blockers"
        if selected_action == "no_immediate_heap_followup_required":
            return "record_heap_snapshot_diff_followup_review_decision"
        return "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "selection_only": True,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "constructor_drilldown_computed": False,
            "larger_budget_second_pass_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "automatic_followup_analysis": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotConstructorGrowthDrilldownSpec:
    """Read-only constructor-growth drilldown review descriptor.

    This consumes the Step 325 selected-analysis input preflight for
    `review_constructor_growth` and prepares a conservative constructor growth
    review package. It does not read raw heap files, parse raw heap data, compute
    retained size, compute path-to-root, or invoke a follow-up executor.
    """

    selected_analysis_input_preflight: dict[str, Any] | None = None
    selected_candidate_name: str | None = None
    reviewer: str | None = None
    require_ready_preflight: bool = True
    require_constructor_action: bool = True
    min_constructor_delta: int = 1

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotConstructorGrowthDrilldownSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_constructor_growth_drilldown",
                "heapSnapshotConstructorGrowthDrilldown",
                "heap_snapshot_diff_constructor_growth_drilldown",
                "heapSnapshotDiffConstructorGrowthDrilldown",
                "review_heap_snapshot_constructor_growth_drilldown",
                "reviewHeapSnapshotConstructorGrowthDrilldown",
                "review_heap_snapshot_diff_constructor_growth",
                "reviewHeapSnapshotDiffConstructorGrowth",
            )
        )
        preflight = context.get(
            "heap_snapshot_diff_selected_analysis_input_preflight",
            context.get(
                "heapSnapshotDiffSelectedAnalysisInputPreflight",
                context.get("selected_analysis_input_preflight", context.get("selectedAnalysisInputPreflight")),
            ),
        )
        if not requested and not preflight:
            return None
        return cls(
            selected_analysis_input_preflight=preflight if isinstance(preflight, dict) else None,
            selected_candidate_name=str(context.get("selected_candidate_name", context.get("selectedCandidateName", context.get("candidate_name", context.get("candidateName", "")))) or "").strip() or None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            require_ready_preflight=bool(context.get("require_ready_preflight", context.get("requireReadyPreflight", True))),
            require_constructor_action=bool(context.get("require_constructor_action", context.get("requireConstructorAction", True))),
            min_constructor_delta=max(0, int(context.get("min_constructor_delta", context.get("minConstructorDelta", 1)) or 0)),
        )


@dataclass(slots=True)
class HeapSnapshotConstructorGrowthDrilldownResult:
    status: str
    drilldown: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "drilldown": self.drilldown,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotConstructorGrowthDrilldownManager:
    """Review-only constructor growth drilldown over Step 325 selected input."""

    def review(self, spec: HeapSnapshotConstructorGrowthDrilldownSpec | None) -> HeapSnapshotConstructorGrowthDrilldownResult:
        policy = self._side_effect_policy()
        if spec is None:
            drilldown = self._drilldown(None, ["missing_heap_snapshot_constructor_growth_drilldown_request"], [], {}, {}, [], policy)
            return HeapSnapshotConstructorGrowthDrilldownResult(status="blocked", drilldown=drilldown, side_effect_policy=policy, reason="missing_heap_snapshot_constructor_growth_drilldown_request")
        blockers, warnings, preflight_summary, selected_input, candidates = self._validate(spec)
        drilldown = self._drilldown(spec, blockers, warnings, preflight_summary, selected_input, candidates, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotConstructorGrowthDrilldownResult(status=status, drilldown=drilldown, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate(self, spec: HeapSnapshotConstructorGrowthDrilldownSpec) -> tuple[list[str], list[str], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_constructor_growth_drilldown_review_only"]
        preflight = spec.selected_analysis_input_preflight or {}
        if not preflight:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_required")
            return blockers, warnings, {}, {}, []
        if preflight.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-selected-analysis-input-preflight.v1":
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_schema_mismatch")
        if spec.require_ready_preflight and preflight.get("status") != "ready_for_review":
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_not_ready")
        if preflight.get("review_only") is not True or preflight.get("preflight_only") is not True or preflight.get("selection_only") is not True:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_not_selection_gate")
        if preflight.get("raw_heap_loaded") is True or preflight.get("raw_heap_parsed") is True or preflight.get("heap_diff_computed") is True:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_claims_heap_work")
        if preflight.get("retained_size_proven") is True or preflight.get("path_to_root_computed") is True or preflight.get("constructor_drilldown_computed") is True:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_claims_followup_execution")
        policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_forbidden_runtime_side_effect")
        future = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        if future.get("implemented") is True or future.get("automatic_execution_allowed") is True:
            blockers.append("heap_snapshot_diff_selected_analysis_input_preflight_future_executor_enabled")
        selected_input = preflight.get("selected_analysis_input") if isinstance(preflight.get("selected_analysis_input"), dict) else {}
        selected_action = str(selected_input.get("selected_action") or future.get("selected_action") or "")
        if spec.require_constructor_action and selected_action != "review_constructor_growth":
            blockers.append("heap_snapshot_constructor_growth_action_required")
        candidates = self._candidate_rows(selected_input.get("candidates"), spec.selected_candidate_name, spec.min_constructor_delta)
        if not candidates:
            blockers.append("heap_snapshot_constructor_growth_candidates_required")
        preflight_summary = self._preflight_summary(preflight)
        return list(dict.fromkeys(blockers)), warnings, preflight_summary, selected_input, candidates

    @staticmethod
    def _candidate_rows(rows: Any, selected_candidate_name: str | None, min_delta: int) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if selected_candidate_name and name != selected_candidate_name:
                continue
            try:
                before = int(item.get("before") or 0)
                after = int(item.get("after") or 0)
                delta = int(item.get("delta") or 0)
            except Exception as e:
                _logger.debug("Failed to parse growth sample fields (before/after/delta): %s", e, exc_info=True)
                before = after = delta = 0
            if delta < min_delta:
                continue
            candidates.append({
                "name": name,
                "before": before,
                "after": after,
                "delta": delta,
                "growth_ratio": (float(after) / float(before)) if before > 0 else None,
                "source": str(item.get("source") or "summary_diff_followup_checkpoint"),
                "raw_value_exported": False,
                "requires_raw_heap_for_retained_size": True,
                "requires_raw_heap_for_path_to_root": True,
            })
        candidates.sort(key=lambda item: int(item["delta"]), reverse=True)
        return candidates[:10]

    @staticmethod
    def _preflight_summary(preflight: dict[str, Any]) -> dict[str, Any]:
        source = preflight.get("source_checkpoint_summary") if isinstance(preflight.get("source_checkpoint_summary"), dict) else {}
        selected_input = preflight.get("selected_analysis_input") if isinstance(preflight.get("selected_analysis_input"), dict) else {}
        future = preflight.get("future_executor_contract") if isinstance(preflight.get("future_executor_contract"), dict) else {}
        return {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "preflight_artifact": preflight.get("preflight_artifact", "workspace/heap-snapshot-diff-selected-analysis-input-preflight.json"),
            "transaction_id": source.get("transaction_id"),
            "source_checkpoint_status": source.get("status"),
            "executor_result_status": source.get("executor_result_status"),
            "node_count_delta": source.get("node_count_delta"),
            "edge_count_delta": source.get("edge_count_delta"),
            "self_size_total_analyzed_delta": source.get("self_size_total_analyzed_delta"),
            "selected_action": selected_input.get("selected_action") or future.get("selected_action"),
            "selected_candidate_name": selected_input.get("selected_candidate_name"),
            "future_executor_name": future.get("executor_name"),
            "future_result_artifact": future.get("result_artifact"),
        }

    def _drilldown(
        self,
        spec: HeapSnapshotConstructorGrowthDrilldownSpec | None,
        blockers: list[str],
        warnings: list[str],
        preflight_summary: dict[str, Any],
        selected_input: dict[str, Any],
        candidates: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1",
            "status": status,
            "drilldown_name": "heap_snapshot_constructor_growth_drilldown",
            "drilldown_artifact": "workspace/heap-snapshot-constructor-growth-drilldown.json",
            "review_only": True,
            "drilldown_only": True,
            "summary_only": True,
            "reviewer": spec.reviewer if spec else None,
            "source_selected_analysis_input_preflight": preflight_summary,
            "selected_action": selected_input.get("selected_action"),
            "selected_candidate_name": spec.selected_candidate_name if spec else None,
            "constructor_growth_summary": {
                "candidate_count": len(candidates),
                "total_positive_delta": sum(int(item.get("delta") or 0) for item in candidates),
                "top_candidate": candidates[0] if candidates else {},
                "candidates": candidates,
            },
            "review_recommendations": self._recommendations(candidates),
            "future_analysis_contracts": {
                "constructor_drilldown_execution": {"implemented": False, "requires_explicit_review": True, "requires_raw_heap": False},
                "retained_size_analysis": {"implemented": False, "requires_raw_heap": True, "requires_explicit_review": True},
                "path_to_root_analysis": {"implemented": False, "requires_raw_heap": True, "requires_explicit_review": True},
                "automatic_followup_analysis": {"implemented": False, "allowed": False},
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight" if not blockers else "resolve_heap_snapshot_constructor_growth_drilldown_blockers",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _recommendations(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        return [
            {
                "action": "review_constructor_growth_candidate",
                "reason": "constructor_count_delta_observed",
                "candidate_count": len(candidates),
                "requires_review": True,
                "automatic": False,
            },
            {
                "action": "plan_retained_size_analysis_preflight",
                "reason": "constructor_growth_may_require_retained_size_context",
                "requires_raw_heap": True,
                "requires_review": True,
                "implemented": False,
                "automatic": False,
            },
            {
                "action": "plan_path_to_root_analysis_preflight",
                "reason": "constructor_growth_may_require_retainer_path_context",
                "requires_raw_heap": True,
                "requires_review": True,
                "implemented": False,
                "automatic": False,
            },
        ]

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "drilldown_only": True,
            "summary_only": True,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "automatic_followup_analysis": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedPathPreflightSpec:
    """Read-only retained-size / path-to-root input preflight.

    This consumes the Step 326 constructor-growth review descriptor and prepares
    the next review input for future retained-size or path-to-root executors. It
    does not load raw heap files, parse heap graph structures, compute retained
    size, compute retainer paths, or invoke any follow-up executor.
    """

    constructor_growth_drilldown: dict[str, Any] | None = None
    selected_candidate_name: str | None = None
    requested_analysis: str = "retained-size-and-path-to-root"
    reviewer: str | None = None
    require_ready_drilldown: bool = True
    min_constructor_delta: int = 1
    max_candidate_count: int = 5

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedPathPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_path_preflight",
                "heapSnapshotRetainedPathPreflight",
                "heap_snapshot_constructor_growth_retained_path_preflight",
                "heapSnapshotConstructorGrowthRetainedPathPreflight",
                "heap_snapshot_retained_size_path_to_root_preflight",
                "heapSnapshotRetainedSizePathToRootPreflight",
                "review_heap_snapshot_retained_path_preflight",
                "reviewHeapSnapshotRetainedPathPreflight",
            )
        )
        drilldown = context.get(
            "heap_snapshot_constructor_growth_drilldown",
            context.get(
                "heapSnapshotConstructorGrowthDrilldown",
                context.get("constructor_growth_drilldown", context.get("constructorGrowthDrilldown")),
            ),
        )
        if not requested and not drilldown:
            return None
        return cls(
            constructor_growth_drilldown=drilldown if isinstance(drilldown, dict) else None,
            selected_candidate_name=str(context.get("selected_candidate_name", context.get("selectedCandidateName", context.get("candidate_name", context.get("candidateName", "")))) or "").strip() or None,
            requested_analysis=str(context.get("requested_analysis", context.get("requestedAnalysis", "retained-size-and-path-to-root")) or "retained-size-and-path-to-root").strip() or "retained-size-and-path-to-root",
            reviewer=str(context.get("reviewer") or "").strip() or None,
            require_ready_drilldown=bool(context.get("require_ready_drilldown", context.get("requireReadyDrilldown", True))),
            min_constructor_delta=max(0, int(context.get("min_constructor_delta", context.get("minConstructorDelta", 1)) or 0)),
            max_candidate_count=max(1, int(context.get("max_candidate_count", context.get("maxCandidateCount", 5)) or 5)),
        )


@dataclass(slots=True)
class HeapSnapshotRetainedPathPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "preflight": self.preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedPathPreflightManager:
    """Review-only retained-size / path-to-root preflight over Step 326 output."""

    SUPPORTED_ANALYSES = {
        "retained-size",
        "retained_size",
        "path-to-root",
        "path_to_root",
        "retained-size-and-path-to-root",
        "retained_size_and_path_to_root",
    }

    def review(self, spec: HeapSnapshotRetainedPathPreflightSpec | None) -> HeapSnapshotRetainedPathPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            preflight = self._preflight(None, ["missing_heap_snapshot_retained_path_preflight_request"], [], {}, [], policy)
            return HeapSnapshotRetainedPathPreflightResult(status="blocked", preflight=preflight, side_effect_policy=policy, reason="missing_heap_snapshot_retained_path_preflight_request")
        blockers, warnings, source_summary, candidates = self._validate(spec)
        preflight = self._preflight(spec, blockers, warnings, source_summary, candidates, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotRetainedPathPreflightResult(status=status, preflight=preflight, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate(self, spec: HeapSnapshotRetainedPathPreflightSpec) -> tuple[list[str], list[str], dict[str, Any], list[dict[str, Any]]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_retained_path_preflight_review_only"]
        drilldown = spec.constructor_growth_drilldown or {}
        if not drilldown:
            blockers.append("heap_snapshot_constructor_growth_drilldown_required")
            return blockers, warnings, {}, []
        if drilldown.get("schema_version") != "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1":
            blockers.append("heap_snapshot_constructor_growth_drilldown_schema_mismatch")
        if spec.require_ready_drilldown and drilldown.get("status") != "ready_for_review":
            blockers.append("heap_snapshot_constructor_growth_drilldown_not_ready")
        if drilldown.get("review_only") is not True or drilldown.get("drilldown_only") is not True or drilldown.get("summary_only") is not True:
            blockers.append("heap_snapshot_constructor_growth_drilldown_not_review_summary")
        if drilldown.get("raw_heap_loaded") is True or drilldown.get("raw_heap_parsed") is True or drilldown.get("heap_diff_computed") is True:
            blockers.append("heap_snapshot_constructor_growth_drilldown_claims_heap_work")
        if drilldown.get("constructor_drilldown_computed") is True or drilldown.get("retained_size_proven") is True or drilldown.get("path_to_root_computed") is True:
            blockers.append("heap_snapshot_constructor_growth_drilldown_claims_followup_execution")
        policy = drilldown.get("side_effect_policy") if isinstance(drilldown.get("side_effect_policy"), dict) else {}
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_constructor_growth_drilldown_forbidden_runtime_side_effect")
        requested_analysis = self._normalize_analysis(spec.requested_analysis)
        if requested_analysis not in self.SUPPORTED_ANALYSES:
            blockers.append("heap_snapshot_retained_path_requested_analysis_unsupported")
        contracts = drilldown.get("future_analysis_contracts") if isinstance(drilldown.get("future_analysis_contracts"), dict) else {}
        retained_contract = contracts.get("retained_size_analysis") if isinstance(contracts.get("retained_size_analysis"), dict) else {}
        path_contract = contracts.get("path_to_root_analysis") if isinstance(contracts.get("path_to_root_analysis"), dict) else {}
        if retained_contract.get("implemented") is True or path_contract.get("implemented") is True:
            blockers.append("heap_snapshot_retained_path_future_executor_already_implemented_claim")
        candidates = self._candidate_rows(drilldown, spec.selected_candidate_name, spec.min_constructor_delta, spec.max_candidate_count)
        if not candidates:
            blockers.append("heap_snapshot_retained_path_candidates_required")
        return list(dict.fromkeys(blockers)), warnings, self._source_summary(drilldown, requested_analysis), candidates

    @staticmethod
    def _normalize_analysis(value: str) -> str:
        return str(value or "").strip().lower().replace("_", "-")

    @staticmethod
    def _candidate_rows(drilldown: dict[str, Any], selected_candidate_name: str | None, min_delta: int, max_count: int) -> list[dict[str, Any]]:
        summary = drilldown.get("constructor_growth_summary") if isinstance(drilldown.get("constructor_growth_summary"), dict) else {}
        rows = summary.get("candidates") if isinstance(summary.get("candidates"), list) else []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if selected_candidate_name and name != selected_candidate_name:
                continue
            delta = int(item.get("delta") or 0)
            if delta < min_delta:
                continue
            candidates.append({
                "name": name,
                "before": int(item.get("before") or 0),
                "after": int(item.get("after") or 0),
                "delta": delta,
                "growth_ratio": item.get("growth_ratio"),
                "source": str(item.get("source") or "constructor_growth_drilldown"),
                "raw_value_exported": False,
                "requires_raw_heap_for_retained_size": True,
                "requires_raw_heap_for_path_to_root": True,
                "retained_size_preflight_ready": True,
                "path_to_root_preflight_ready": True,
                "would_execute_now": False,
            })
        candidates.sort(key=lambda row: int(row.get("delta") or 0), reverse=True)
        return candidates[:max_count]

    @staticmethod
    def _source_summary(drilldown: dict[str, Any], requested_analysis: str) -> dict[str, Any]:
        source = drilldown.get("source_selected_analysis_input_preflight") if isinstance(drilldown.get("source_selected_analysis_input_preflight"), dict) else {}
        summary = drilldown.get("constructor_growth_summary") if isinstance(drilldown.get("constructor_growth_summary"), dict) else {}
        top = summary.get("top_candidate") if isinstance(summary.get("top_candidate"), dict) else {}
        return {
            "schema_version": drilldown.get("schema_version"),
            "status": drilldown.get("status"),
            "drilldown_artifact": drilldown.get("drilldown_artifact", "workspace/heap-snapshot-constructor-growth-drilldown.json"),
            "transaction_id": source.get("transaction_id"),
            "source_preflight_status": source.get("status"),
            "selected_action": drilldown.get("selected_action"),
            "requested_analysis": requested_analysis,
            "candidate_count": summary.get("candidate_count"),
            "top_candidate_name": top.get("name"),
            "top_candidate_delta": top.get("delta"),
        }

    def _preflight(
        self,
        spec: HeapSnapshotRetainedPathPreflightSpec | None,
        blockers: list[str],
        warnings: list[str],
        source_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        requested_analysis = self._normalize_analysis(spec.requested_analysis if spec else "") or "retained-size-and-path-to-root"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-path-preflight.v1",
            "status": status,
            "preflight_name": "heap_snapshot_retained_path_preflight",
            "preflight_artifact": "workspace/heap-snapshot-retained-path-preflight.json",
            "review_only": True,
            "preflight_only": True,
            "handoff_only": True,
            "reviewer": spec.reviewer if spec else None,
            "source_constructor_growth_drilldown": source_summary,
            "requested_analysis": requested_analysis,
            "selected_candidate_name": spec.selected_candidate_name if spec else None,
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "raw_heap_requirements": {
                "requires_raw_heap": True,
                "requires_two_snapshots": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_parser_sandbox": True,
                "requires_redaction_plan": True,
                "raw_heap_available_in_this_preflight": False,
                "raw_heap_loaded_now": False,
            },
            "future_executor_contracts": {
                "retained_size_analysis": {
                    "executor_name": "execute_heap_snapshot_retained_size_analysis",
                    "implemented": False,
                    "requires_explicit_review": True,
                    "requires_raw_heap": True,
                    "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
                    "automatic_execution_allowed": False,
                },
                "path_to_root_analysis": {
                    "executor_name": "execute_heap_snapshot_path_to_root_analysis",
                    "implemented": False,
                    "requires_explicit_review": True,
                    "requires_raw_heap": True,
                    "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
                    "automatic_execution_allowed": False,
                },
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_retained_path_executor_inputs" if not blockers else "resolve_heap_snapshot_retained_path_preflight_blockers",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "preflight_only": True,
            "handoff_only": True,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "automatic_followup_analysis": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedSizeInputReviewSpec:
    """Read-only retained-size executor input review gate.

    This consumes the Step 327 retained-size / path-to-root preflight and
    prepares the next explicit review input for a future retained-size executor.
    It does not load raw heap files, parse heap graph structures, compute
    retained size, compute path-to-root, or invoke any follow-up executor.
    """

    retained_path_preflight: dict[str, Any] | None = None
    selected_candidate_name: str | None = None
    reviewer: str | None = None
    require_ready_preflight: bool = True
    require_raw_heap_plan: bool = True
    require_retained_size_contract: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeInputReviewSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_size_input_review",
                "heapSnapshotRetainedSizeInputReview",
                "heap_snapshot_retained_size_executor_input_review",
                "heapSnapshotRetainedSizeExecutorInputReview",
                "heap_snapshot_retained_size_approval_gate",
                "heapSnapshotRetainedSizeApprovalGate",
                "review_heap_snapshot_retained_size_input",
                "reviewHeapSnapshotRetainedSizeInput",
            )
        )
        preflight = context.get(
            "heap_snapshot_retained_path_preflight",
            context.get(
                "heapSnapshotRetainedPathPreflight",
                context.get("retained_path_preflight", context.get("retainedPathPreflight")),
            ),
        )
        if not requested and not preflight:
            return None
        return cls(
            retained_path_preflight=preflight if isinstance(preflight, dict) else None,
            selected_candidate_name=str(context.get("selected_candidate_name", context.get("selectedCandidateName", context.get("candidate_name", context.get("candidateName", "")))) or "").strip() or None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            require_ready_preflight=bool(context.get("require_ready_preflight", context.get("requireReadyPreflight", True))),
            require_raw_heap_plan=bool(context.get("require_raw_heap_plan", context.get("requireRawHeapPlan", True))),
            require_retained_size_contract=bool(context.get("require_retained_size_contract", context.get("requireRetainedSizeContract", True))),
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeInputReviewResult:
    status: str
    review: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "review": self.review,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedSizeInputReviewManager:
    """Review-only retained-size executor input gate over Step 327 output."""

    def review(self, spec: HeapSnapshotRetainedSizeInputReviewSpec | None) -> HeapSnapshotRetainedSizeInputReviewResult:
        policy = self._side_effect_policy()
        if spec is None:
            review = self._review(None, ["missing_heap_snapshot_retained_size_input_review_request"], [], {}, [], {}, policy)
            return HeapSnapshotRetainedSizeInputReviewResult(status="blocked", review=review, side_effect_policy=policy, reason="missing_heap_snapshot_retained_size_input_review_request")
        blockers, warnings, source_summary, candidates, retained_contract = self._validate(spec)
        review = self._review(spec, blockers, warnings, source_summary, candidates, retained_contract, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotRetainedSizeInputReviewResult(status=status, review=review, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate(self, spec: HeapSnapshotRetainedSizeInputReviewSpec) -> tuple[list[str], list[str], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_retained_size_input_review_only"]
        preflight = spec.retained_path_preflight or {}
        if not preflight:
            blockers.append("heap_snapshot_retained_path_preflight_required")
            return blockers, warnings, {}, [], {}
        if preflight.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-path-preflight.v1":
            blockers.append("heap_snapshot_retained_path_preflight_schema_mismatch")
        if spec.require_ready_preflight and preflight.get("status") != "ready_for_review":
            blockers.append("heap_snapshot_retained_path_preflight_not_ready")
        if preflight.get("review_only") is not True or preflight.get("preflight_only") is not True or preflight.get("handoff_only") is not True:
            blockers.append("heap_snapshot_retained_path_preflight_not_review_handoff")
        requested = str(preflight.get("requested_analysis") or "").strip().lower().replace("_", "-")
        if requested not in {"retained-size", "retained-size-and-path-to-root"}:
            blockers.append("heap_snapshot_retained_size_not_requested")
        for key in (
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "heap_diff_computed",
            "retained_size_proven",
            "path_to_root_computed",
            "larger_budget_second_pass_computed",
            "automatic_followup_analysis",
        ):
            if preflight.get(key) is True:
                blockers.append(f"heap_snapshot_retained_path_preflight_claims_{key}")
        policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_retained_path_preflight_forbidden_runtime_side_effect")
        raw_req = preflight.get("raw_heap_requirements") if isinstance(preflight.get("raw_heap_requirements"), dict) else {}
        if spec.require_raw_heap_plan:
            if raw_req.get("requires_raw_heap") is not True or raw_req.get("requires_raw_heap_ingestion_preflight") is not True:
                blockers.append("heap_snapshot_retained_size_raw_heap_requirements_incomplete")
            if raw_req.get("raw_heap_available_in_this_preflight") is True or raw_req.get("raw_heap_loaded_now") is True:
                blockers.append("heap_snapshot_retained_size_raw_heap_claimed_in_input_review")
        future = preflight.get("future_executor_contracts") if isinstance(preflight.get("future_executor_contracts"), dict) else {}
        retained_contract = future.get("retained_size_analysis") if isinstance(future.get("retained_size_analysis"), dict) else {}
        if spec.require_retained_size_contract:
            if not retained_contract:
                blockers.append("heap_snapshot_retained_size_future_executor_contract_required")
            elif retained_contract.get("implemented") is not False:
                blockers.append("heap_snapshot_retained_size_future_executor_contract_unexpected")
            if retained_contract and retained_contract.get("executor_name") not in {None, "execute_heap_snapshot_retained_size_analysis"}:
                blockers.append("heap_snapshot_retained_size_future_executor_name_mismatch")
        candidates = self._candidate_rows(preflight, spec.selected_candidate_name)
        if not candidates:
            blockers.append("heap_snapshot_retained_size_candidate_inputs_required")
        return list(dict.fromkeys(blockers)), warnings, self._source_summary(preflight), candidates, retained_contract

    @staticmethod
    def _candidate_rows(preflight: dict[str, Any], selected_candidate_name: str | None) -> list[dict[str, Any]]:
        rows = preflight.get("candidate_inputs") if isinstance(preflight.get("candidate_inputs"), list) else []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if selected_candidate_name and name != selected_candidate_name:
                continue
            candidates.append({
                "name": name,
                "before": int(item.get("before") or 0),
                "after": int(item.get("after") or 0),
                "delta": int(item.get("delta") or 0),
                "source": str(item.get("source") or "retained_path_preflight"),
                "requires_raw_heap_for_retained_size": True,
                "raw_value_exported": False,
                "retained_size_computed": False,
                "would_execute_now": False,
            })
        candidates.sort(key=lambda row: int(row.get("delta") or 0), reverse=True)
        return candidates

    @staticmethod
    def _source_summary(preflight: dict[str, Any]) -> dict[str, Any]:
        source = preflight.get("source_constructor_growth_drilldown") if isinstance(preflight.get("source_constructor_growth_drilldown"), dict) else {}
        return {
            "schema_version": preflight.get("schema_version"),
            "status": preflight.get("status"),
            "preflight_artifact": preflight.get("preflight_artifact", "workspace/heap-snapshot-retained-path-preflight.json"),
            "requested_analysis": preflight.get("requested_analysis"),
            "candidate_count": preflight.get("candidate_count"),
            "transaction_id": source.get("transaction_id"),
            "source_selected_action": source.get("selected_action"),
        }

    def _review(
        self,
        spec: HeapSnapshotRetainedSizeInputReviewSpec | None,
        blockers: list[str],
        warnings: list[str],
        source_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        retained_contract: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-input-review.v1",
            "status": status,
            "review_name": "heap_snapshot_retained_size_input_review",
            "review_artifact": "workspace/heap-snapshot-retained-size-input-review.json",
            "review_only": True,
            "input_review_only": True,
            "approval_gate_only": True,
            "retained_size_only": True,
            "reviewer": spec.reviewer if spec else None,
            "source_retained_path_preflight": source_summary,
            "selected_candidate_name": spec.selected_candidate_name if spec else None,
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "raw_heap_requirements": {
                "requires_raw_heap": True,
                "requires_two_snapshots": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_parser_sandbox": True,
                "requires_redaction_plan": True,
                "raw_heap_available_in_this_review": False,
                "raw_heap_loaded_now": False,
            },
            "executor_input_contract": {
                "executor_name": retained_contract.get("executor_name") or "execute_heap_snapshot_retained_size_analysis",
                "implemented": False,
                "requires_explicit_review": True,
                "requires_raw_heap": True,
                "requires_bounded_budget": True,
                "result_artifact": retained_contract.get("result_artifact") or "workspace/heap-snapshot-retained-size-analysis.json",
                "automatic_execution_allowed": False,
                "would_execute_now": False,
            },
            "approval_gate": {
                "approval_required": True,
                "approval_recorded": False,
                "transaction_started": False,
                "journal_written": False,
                "ready_to_execute_now": False,
                "next_artifact": "workspace/heap-snapshot-retained-size-approval-plan.json",
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_retained_size_approval_plan" if not blockers else "resolve_heap_snapshot_retained_size_input_review_blockers",
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "executor_invoked": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "input_review_only": True,
            "approval_gate_only": True,
            "retained_size_only": True,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "automatic_followup_analysis": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedSizeApprovalPlanSpec:
    """Read-only approval / transaction plan for a future retained-size executor."""

    retained_size_input_review: dict[str, Any] | None = None
    reviewer: str | None = None
    approval_reason: str | None = None
    expected_candidate_name: str | None = None
    require_ready_input_review: bool = True
    require_explicit_reviewer: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeApprovalPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_size_approval_plan",
                "heapSnapshotRetainedSizeApprovalPlan",
                "heap_snapshot_retained_size_executor_approval_plan",
                "heapSnapshotRetainedSizeExecutorApprovalPlan",
                "heap_snapshot_retained_size_transaction_plan",
                "heapSnapshotRetainedSizeTransactionPlan",
                "review_heap_snapshot_retained_size_approval_plan",
                "reviewHeapSnapshotRetainedSizeApprovalPlan",
            )
        )
        review = context.get(
            "heap_snapshot_retained_size_input_review",
            context.get(
                "heapSnapshotRetainedSizeInputReview",
                context.get("retained_size_input_review", context.get("retainedSizeInputReview")),
            ),
        )
        if not requested and not review:
            return None
        return cls(
            retained_size_input_review=review if isinstance(review, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            approval_reason=str(context.get("approval_reason", context.get("approvalReason", "")) or "").strip() or None,
            expected_candidate_name=str(context.get("expected_candidate_name", context.get("expectedCandidateName", "")) or "").strip() or None,
            require_ready_input_review=bool(context.get("require_ready_input_review", context.get("requireReadyInputReview", True))),
            require_explicit_reviewer=bool(context.get("require_explicit_reviewer", context.get("requireExplicitReviewer", False))),
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeApprovalPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedSizeApprovalPlanManager:
    """Review-only approval / transaction plan over retained-size input review."""

    def review(self, spec: HeapSnapshotRetainedSizeApprovalPlanSpec | None) -> HeapSnapshotRetainedSizeApprovalPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            plan = self._plan(None, ["missing_heap_snapshot_retained_size_approval_plan_request"], [], {}, [], {}, {}, policy)
            return HeapSnapshotRetainedSizeApprovalPlanResult(status="blocked", plan=plan, side_effect_policy=policy, reason="missing_heap_snapshot_retained_size_approval_plan_request")
        blockers, warnings, source_summary, candidates, executor_contract, approval_gate = self._validate(spec)
        plan = self._plan(spec, blockers, warnings, source_summary, candidates, executor_contract, approval_gate, policy)
        status = "ready_for_review" if not blockers else "blocked"
        return HeapSnapshotRetainedSizeApprovalPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate(self, spec: HeapSnapshotRetainedSizeApprovalPlanSpec) -> tuple[list[str], list[str], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = ["heap_snapshot_retained_size_approval_plan_review_only"]
        review = spec.retained_size_input_review or {}
        if not review:
            blockers.append("heap_snapshot_retained_size_input_review_required")
            return blockers, warnings, {}, [], {}, {}
        if review.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-input-review.v1":
            blockers.append("heap_snapshot_retained_size_input_review_schema_mismatch")
        if spec.require_ready_input_review and review.get("status") != "ready_for_review":
            blockers.append("heap_snapshot_retained_size_input_review_not_ready")
        if review.get("review_only") is not True or review.get("input_review_only") is not True or review.get("approval_gate_only") is not True:
            blockers.append("heap_snapshot_retained_size_input_review_not_approval_gate")
        if spec.require_explicit_reviewer and not spec.reviewer:
            blockers.append("heap_snapshot_retained_size_approval_reviewer_required")
        for key in (
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "heap_diff_computed",
            "retained_size_proven",
            "path_to_root_computed",
            "larger_budget_second_pass_computed",
            "executor_invoked",
            "automatic_followup_analysis",
        ):
            if review.get(key) is True:
                blockers.append(f"heap_snapshot_retained_size_input_review_claims_{key}")
        policy = review.get("side_effect_policy") if isinstance(review.get("side_effect_policy"), dict) else {}
        if policy.get("browser_started") is True or policy.get("cdp_command_sent") is True or policy.get("calls_mcp") is True or policy.get("mobile_runtime_used") is True:
            blockers.append("heap_snapshot_retained_size_input_review_forbidden_runtime_side_effect")
        executor_contract = review.get("executor_input_contract") if isinstance(review.get("executor_input_contract"), dict) else {}
        if not executor_contract:
            blockers.append("heap_snapshot_retained_size_executor_input_contract_required")
        elif executor_contract.get("implemented") is not False:
            blockers.append("heap_snapshot_retained_size_executor_input_contract_unexpected")
        if executor_contract and executor_contract.get("executor_name") not in {None, "execute_heap_snapshot_retained_size_analysis"}:
            blockers.append("heap_snapshot_retained_size_executor_name_mismatch")
        approval_gate = review.get("approval_gate") if isinstance(review.get("approval_gate"), dict) else {}
        if not approval_gate:
            blockers.append("heap_snapshot_retained_size_approval_gate_required")
        else:
            if approval_gate.get("approval_required") is not True:
                blockers.append("heap_snapshot_retained_size_approval_required_gate_missing")
            if approval_gate.get("ready_to_execute_now") is True or approval_gate.get("approval_recorded") is True or approval_gate.get("transaction_started") is True or approval_gate.get("journal_written") is True:
                blockers.append("heap_snapshot_retained_size_approval_gate_claims_execution_or_write")
        candidates = self._candidate_rows(review, spec.expected_candidate_name)
        if not candidates:
            blockers.append("heap_snapshot_retained_size_approval_plan_candidate_inputs_required")
        return list(dict.fromkeys(blockers)), warnings, self._source_summary(review), candidates, executor_contract, approval_gate

    @staticmethod
    def _candidate_rows(review: dict[str, Any], expected_candidate_name: str | None) -> list[dict[str, Any]]:
        rows = review.get("candidate_inputs") if isinstance(review.get("candidate_inputs"), list) else []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if expected_candidate_name and name != expected_candidate_name:
                continue
            candidates.append({
                "name": name,
                "delta": int(item.get("delta") or 0),
                "source": str(item.get("source") or "retained_size_input_review"),
                "requires_raw_heap_for_retained_size": True,
                "retained_size_computed": False,
                "would_execute_now": False,
            })
        candidates.sort(key=lambda row: int(row.get("delta") or 0), reverse=True)
        return candidates

    @staticmethod
    def _source_summary(review: dict[str, Any]) -> dict[str, Any]:
        source = review.get("source_retained_path_preflight") if isinstance(review.get("source_retained_path_preflight"), dict) else {}
        return {
            "schema_version": review.get("schema_version"),
            "status": review.get("status"),
            "review_artifact": review.get("review_artifact", "workspace/heap-snapshot-retained-size-input-review.json"),
            "candidate_count": review.get("candidate_count"),
            "transaction_id": source.get("transaction_id"),
            "source_requested_analysis": source.get("requested_analysis"),
        }

    def _plan(
        self,
        spec: HeapSnapshotRetainedSizeApprovalPlanSpec | None,
        blockers: list[str],
        warnings: list[str],
        source_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        executor_contract: dict[str, Any],
        approval_gate: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        status = "ready_for_review" if not blockers else "blocked"
        candidate_names = [str(item.get("name") or "unknown") for item in candidates]
        candidate_digest = _stable_digest({"candidates": candidate_names, "count": len(candidate_names)}) if candidates else None
        approval_plan_id = _stable_digest({"source": source_summary, "candidate_digest": candidate_digest, "executor": executor_contract.get("executor_name") or "execute_heap_snapshot_retained_size_analysis"}) if not blockers else None
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1",
            "status": status,
            "plan_name": "heap_snapshot_retained_size_approval_plan",
            "plan_artifact": "workspace/heap-snapshot-retained-size-approval-plan.json",
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "retained_size_only": True,
            "reviewer": spec.reviewer if spec else None,
            "approval_reason": spec.approval_reason if spec else None,
            "source_retained_size_input_review": source_summary,
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "candidate_digest": candidate_digest,
            "approval_plan": {
                "approval_plan_id": approval_plan_id,
                "approval_required": True,
                "approval_recorded": False,
                "approval_record_writer": "record_heap_snapshot_retained_size_approval",
                "approval_record_artifact": "workspace/heap-snapshot-retained-size-approval-record.json",
                "requires_reviewer": True,
                "requires_candidate_digest_match": True,
                "would_write_now": False,
            },
            "transaction_plan": {
                "transaction_plan_id": approval_plan_id,
                "transaction_started": False,
                "journal_written": False,
                "transaction_journal_writer": "record_heap_snapshot_retained_size_transaction_journal",
                "transaction_journal_artifact": "workspace/heap-snapshot-retained-size-executor-journal.json",
                "bounded_gate_artifact": "workspace/heap-snapshot-retained-size-bounded-gate.json",
                "result_artifact": executor_contract.get("result_artifact") or "workspace/heap-snapshot-retained-size-analysis.json",
                "would_start_transaction_now": False,
                "would_write_journal_now": False,
            },
            "executor_input_contract": {
                "executor_name": executor_contract.get("executor_name") or "execute_heap_snapshot_retained_size_analysis",
                "implemented": False,
                "requires_explicit_review": True,
                "requires_raw_heap": True,
                "requires_bounded_budget": True,
                "ready_to_execute_now": False,
                "automatic_execution_allowed": False,
            },
            "source_approval_gate": {
                "approval_required": bool(approval_gate.get("approval_required")),
                "ready_to_execute_now": bool(approval_gate.get("ready_to_execute_now")),
                "approval_recorded": bool(approval_gate.get("approval_recorded")),
                "transaction_started": bool(approval_gate.get("transaction_started")),
                "journal_written": bool(approval_gate.get("journal_written")),
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "record_heap_snapshot_retained_size_approval" if not blockers else "resolve_heap_snapshot_retained_size_approval_plan_blockers",
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "automatic_followup_analysis": False,
            "side_effect_policy": policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "approval_plan_only": True,
            "transaction_plan_only": True,
            "retained_size_only": True,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "constructor_drilldown_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "larger_budget_second_pass_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "automatic_followup_analysis": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedSizeTransactionPreflightSpec:
    """Read-only transaction preflight before retained-size journal writing."""

    approval_plan_descriptor: dict[str, Any] | None = None
    approval_record_descriptor: dict[str, Any] | None = None
    expected_approval_plan_id: str | None = None
    expected_transaction_plan_id: str | None = None
    expected_candidate_digest: str | None = None
    expected_plan_digest_sha256: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeTransactionPreflightSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_size_transaction_preflight",
                "heapSnapshotRetainedSizeTransactionPreflight",
                "heap_snapshot_retained_size_executor_transaction_preflight",
                "heapSnapshotRetainedSizeExecutorTransactionPreflight",
                "review_heap_snapshot_retained_size_transaction_preflight",
                "reviewHeapSnapshotRetainedSizeTransactionPreflight",
                "preflight_heap_snapshot_retained_size_transaction",
                "preflightHeapSnapshotRetainedSizeTransaction",
            )
        )
        plan = context.get(
            "heap_snapshot_retained_size_approval_plan",
            context.get(
                "heapSnapshotRetainedSizeApprovalPlan",
                context.get("heap_snapshot_retained_size_approval_plan_descriptor", context.get("heapSnapshotRetainedSizeApprovalPlanDescriptor")),
            ),
        )
        record = context.get(
            "heap_snapshot_retained_size_approval_record",
            context.get(
                "heapSnapshotRetainedSizeApprovalRecord",
                context.get("heap_snapshot_retained_size_approval_record_descriptor", context.get("heapSnapshotRetainedSizeApprovalRecordDescriptor")),
            ),
        )
        if not requested and not plan and not record:
            return None
        expected_approval_plan_id = context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId"))
        expected_transaction_plan_id = context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId"))
        expected_candidate_digest = context.get("expected_candidate_digest", context.get("expectedCandidateDigest"))
        expected_plan_digest_sha256 = context.get("expected_plan_digest_sha256", context.get("expectedPlanDigestSha256"))
        return cls(
            approval_plan_descriptor=plan if isinstance(plan, dict) else None,
            approval_record_descriptor=record if isinstance(record, dict) else None,
            expected_approval_plan_id=str(expected_approval_plan_id).strip() if expected_approval_plan_id else None,
            expected_transaction_plan_id=str(expected_transaction_plan_id).strip() if expected_transaction_plan_id else None,
            expected_candidate_digest=str(expected_candidate_digest).strip() if expected_candidate_digest else None,
            expected_plan_digest_sha256=str(expected_plan_digest_sha256).strip() if expected_plan_digest_sha256 else None,
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeTransactionPreflightResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedSizeTransactionPreflightManager:
    """Read-only transaction preflight for retained-size journal writing."""

    _READY_PLAN_STATUSES = {"ready_for_review", "ready", "approved"}
    _READY_RECORD_STATUSES = {"written", "approved", "ready_for_review", "ready"}

    def review(self, spec: HeapSnapshotRetainedSizeTransactionPreflightSpec | None) -> HeapSnapshotRetainedSizeTransactionPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(
                status="blocked",
                blockers=["missing_heap_snapshot_retained_size_transaction_preflight_request"],
                warnings=[],
                approval_summary={},
                transaction_summary={},
                candidate_summary={},
                guard_summary={},
                side_effect_policy=policy,
            )
            return HeapSnapshotRetainedSizeTransactionPreflightResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_retained_size_transaction_preflight_request")

        plan = spec.approval_plan_descriptor or {}
        record = spec.approval_record_descriptor or {}
        blockers: list[str] = []
        warnings: list[str] = []
        if not plan:
            blockers.append("heap_snapshot_retained_size_approval_plan_descriptor_required")
        else:
            blockers.extend(self._plan_blockers(plan))
        if not record:
            blockers.append("heap_snapshot_retained_size_approval_record_descriptor_required")
        else:
            blockers.extend(self._record_blockers(record))
        if plan and record:
            blockers.extend(self._consistency_blockers(spec, plan, record))

        approval_summary = self._approval_summary(plan, record)
        transaction_summary = self._transaction_summary(plan, record)
        candidate_summary = self._candidate_summary(plan, record)
        guard_summary = self._guard_summary(spec, plan, record)
        status = "blocked" if blockers else "ready_for_review"
        if status == "ready_for_review":
            warnings.append("heap_snapshot_retained_size_transaction_ready_for_journal_review")
        descriptor = self._descriptor(
            status=status,
            blockers=blockers,
            warnings=warnings,
            approval_summary=approval_summary,
            transaction_summary=transaction_summary,
            candidate_summary=candidate_summary,
            guard_summary=guard_summary,
            side_effect_policy=policy,
        )
        return HeapSnapshotRetainedSizeTransactionPreflightResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    @classmethod
    def _plan_blockers(cls, plan: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        policy = plan.get("side_effect_policy") if isinstance(plan.get("side_effect_policy"), dict) else {}
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        executor = plan.get("executor_input_contract") if isinstance(plan.get("executor_input_contract"), dict) else {}
        if plan.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1":
            blockers.append("heap_snapshot_retained_size_approval_plan_schema_mismatch")
        if plan.get("status") not in cls._READY_PLAN_STATUSES:
            blockers.append("heap_snapshot_retained_size_approval_plan_not_ready")
        if plan.get("approval_plan_only") is not True or plan.get("transaction_plan_only") is not True:
            blockers.append("heap_snapshot_retained_size_approval_plan_not_plan_only")
        if plan.get("retained_size_only") is not True:
            blockers.append("heap_snapshot_retained_size_approval_plan_not_retained_size_only")
        if plan.get("approval_recorded") is True or policy.get("approval_recorded") is True:
            blockers.append("approval_plan_claims_approval_recorded")
        if plan.get("transaction_started") is True or transaction.get("transaction_started") is True or policy.get("transaction_started") is True:
            blockers.append("approval_plan_claims_transaction_started")
        if plan.get("journal_written_now") is True or transaction.get("journal_written") is True or policy.get("journal_written_now") is True or policy.get("journal_written") is True:
            blockers.append("approval_plan_claims_journal_written")
        if plan.get("bounded_executor_gate_written") is True or policy.get("bounded_executor_gate_written") is True:
            blockers.append("approval_plan_claims_bounded_gate_written")
        if plan.get("executor_invoked") is True or policy.get("executor_invoked") is True or policy.get("future_executor_invoked") is True:
            blockers.append("approval_plan_claims_executor_invoked")
        if executor.get("implemented") is True or executor.get("ready_to_execute_now") is True:
            blockers.append("approval_plan_claims_future_executor_ready")
        blockers.extend(cls._no_retained_side_effect_blockers(plan, prefix="approval_plan"))
        return blockers

    @classmethod
    def _record_blockers(cls, record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        gates = record.get("executor_input_gates") if isinstance(record.get("executor_input_gates"), dict) else {}
        policy = record.get("side_effect_policy") if isinstance(record.get("side_effect_policy"), dict) else {}
        if record.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1":
            blockers.append("heap_snapshot_retained_size_approval_record_schema_mismatch")
        if record.get("status") not in cls._READY_RECORD_STATUSES:
            blockers.append("heap_snapshot_retained_size_approval_record_not_written")
        if record.get("approval_recorded") is not True:
            blockers.append("heap_snapshot_retained_size_approval_record_missing_recorded_flag")
        if record.get("approved_for_execution") is not True:
            blockers.append("heap_snapshot_retained_size_approval_record_not_approved_for_execution")
        if gates.get("transaction_started") is True or record.get("transaction_started") is True or policy.get("transaction_started") is True:
            blockers.append("approval_record_claims_transaction_started")
        if gates.get("journal_written") is True or gates.get("journal_written_now") is True or record.get("journal_written") is True or policy.get("journal_written") is True or policy.get("journal_written_now") is True:
            blockers.append("approval_record_claims_journal_written")
        if gates.get("bounded_executor_gate_written") is True or record.get("bounded_executor_gate_written") is True or policy.get("bounded_executor_gate_written") is True:
            blockers.append("approval_record_claims_bounded_gate_written")
        if gates.get("executor_invoked") is True or record.get("executor_invoked") is True or policy.get("executor_invoked") is True or policy.get("future_executor_invoked") is True:
            blockers.append("approval_record_claims_executor_invoked")
        blockers.extend(cls._no_retained_side_effect_blockers(record, prefix="approval_record"))
        return blockers

    @classmethod
    def _consistency_blockers(cls, spec: HeapSnapshotRetainedSizeTransactionPreflightSpec, plan: dict[str, Any], record: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        approval = plan.get("approval_plan") if isinstance(plan.get("approval_plan"), dict) else {}
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        plan_approval_id = approval.get("approval_plan_id")
        record_approval_id = record.get("approval_plan_id")
        plan_transaction_id = transaction.get("transaction_plan_id")
        record_transaction_id = record.get("transaction_plan_id")
        plan_candidate_digest = plan.get("candidate_digest")
        record_candidate_digest = record.get("candidate_digest")
        if plan_approval_id and record_approval_id and plan_approval_id != record_approval_id:
            blockers.append("approval_plan_id_mismatch")
        if plan_transaction_id and record_transaction_id and plan_transaction_id != record_transaction_id:
            blockers.append("transaction_plan_id_mismatch")
        if plan_candidate_digest and record_candidate_digest and plan_candidate_digest != record_candidate_digest:
            blockers.append("candidate_digest_mismatch")
        if spec.expected_approval_plan_id and spec.expected_approval_plan_id not in {plan_approval_id, record_approval_id}:
            blockers.append("expected_approval_plan_id_mismatch")
        if spec.expected_transaction_plan_id and spec.expected_transaction_plan_id not in {plan_transaction_id, record_transaction_id}:
            blockers.append("expected_transaction_plan_id_mismatch")
        if spec.expected_candidate_digest and spec.expected_candidate_digest not in {plan_candidate_digest, record_candidate_digest}:
            blockers.append("expected_candidate_digest_mismatch")
        plan_digest = cls._digest(plan)
        record_plan_digest = record.get("approval_plan_digest_sha256")
        if record_plan_digest and record_plan_digest != plan_digest:
            blockers.append("approval_plan_digest_mismatch")
        if spec.expected_plan_digest_sha256 and spec.expected_plan_digest_sha256 not in {plan_digest, record_plan_digest}:
            blockers.append("expected_plan_digest_mismatch")
        return blockers

    @staticmethod
    def _no_retained_side_effect_blockers(descriptor: dict[str, Any], *, prefix: str) -> list[str]:
        blockers: list[str] = []
        policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
        for key in (
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "heap_diff_computed",
            "heap_snapshot_diff_computed",
            "retained_size_proven",
            "path_to_root_computed",
        ):
            if descriptor.get(key) is True or policy.get(key) is True:
                blockers.append(f"{prefix}_{key}")
        if descriptor.get("complete_heap_traversal_claimed") is True or policy.get("complete_heap_traversal") is True:
            blockers.append(f"{prefix}_complete_heap_traversal_claimed")
        return blockers

    @staticmethod
    def _approval_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        approval = plan.get("approval_plan") if isinstance(plan.get("approval_plan"), dict) else {}
        return {
            "approval_plan_id": record.get("approval_plan_id") or approval.get("approval_plan_id"),
            "reviewer": record.get("reviewer") or plan.get("reviewer"),
            "approval_record_artifact": approval.get("approval_record_artifact") or "workspace/heap-snapshot-retained-size-approval-record.json",
            "approval_recorded": bool(record.get("approval_recorded")),
            "approved_for_execution": bool(record.get("approved_for_execution")),
        }

    @staticmethod
    def _transaction_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        transaction = plan.get("transaction_plan") if isinstance(plan.get("transaction_plan"), dict) else {}
        gates = record.get("executor_input_gates") if isinstance(record.get("executor_input_gates"), dict) else {}
        return {
            "transaction_plan_id": record.get("transaction_plan_id") or transaction.get("transaction_plan_id"),
            "transaction_journal_artifact": transaction.get("transaction_journal_artifact"),
            "bounded_gate_artifact": transaction.get("bounded_gate_artifact"),
            "result_artifact": transaction.get("result_artifact"),
            "transaction_started": bool(gates.get("transaction_started")) or bool(transaction.get("transaction_started")),
            "journal_written": bool(gates.get("journal_written")) or bool(transaction.get("journal_written")),
            "bounded_executor_gate_written": bool(gates.get("bounded_executor_gate_written")),
            "executor_invoked": bool(gates.get("executor_invoked")) or bool(record.get("executor_invoked")),
        }

    @staticmethod
    def _candidate_summary(plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        candidates = plan.get("candidate_inputs") if isinstance(plan.get("candidate_inputs"), list) else []
        top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        return {
            "candidate_digest": record.get("candidate_digest") or plan.get("candidate_digest"),
            "candidate_count": plan.get("candidate_count") or len(candidates),
            "top_candidate": top.get("name"),
        }

    @classmethod
    def _guard_summary(cls, spec: HeapSnapshotRetainedSizeTransactionPreflightSpec | None, plan: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        return {
            "expected_approval_plan_id": spec.expected_approval_plan_id if spec else None,
            "expected_transaction_plan_id": spec.expected_transaction_plan_id if spec else None,
            "expected_candidate_digest": spec.expected_candidate_digest if spec else None,
            "expected_plan_digest_sha256": spec.expected_plan_digest_sha256 if spec else None,
            "approval_plan_digest_sha256": cls._digest(plan) if plan else None,
            "approval_record_digest_sha256": cls._digest(record) if record else None,
            "recorded_plan_digest_sha256": record.get("approval_plan_digest_sha256") if isinstance(record, dict) else None,
        }

    def _descriptor(
        self,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        approval_summary: dict[str, Any],
        transaction_summary: dict[str, Any],
        candidate_summary: dict[str, Any],
        guard_summary: dict[str, Any],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1",
            "status": status,
            "read_only": True,
            "review_only": True,
            "transaction_preflight_only": True,
            "retained_size_only": True,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_executor_implemented": False,
            "approval_summary": approval_summary,
            "transaction_summary": transaction_summary,
            "candidate_summary": candidate_summary,
            "guard_summary": guard_summary,
            "journal_writer_contract": {
                "implemented": False,
                "ready_for_journal_review": status == "ready_for_review",
                "requires_ready_transaction_preflight": True,
                "requires_explicit_review": True,
                "requires_approval_record": True,
                "transaction_journal_artifact": transaction_summary.get("transaction_journal_artifact") or "workspace/heap-snapshot-retained-size-executor-journal.json",
            },
            "future_executor_contract": {
                "implemented": False,
                "requires_written_transaction_journal": True,
                "requires_bounded_executor_gate": True,
                "requires_raw_heap": True,
                "requires_bounded_budget": True,
                "result_artifact": transaction_summary.get("result_artifact") or "workspace/heap-snapshot-retained-size-analysis.json",
            },
            "safety_gates": {
                "ready_to_write_journal": status == "ready_for_review",
                "ready_to_execute_now": False,
                "approval_record_verified": bool(approval_summary.get("approval_recorded")) and bool(approval_summary.get("approved_for_execution")) and not blockers,
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "raw_strings_exported": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "complete_heap_traversal_claimed": False,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_retained_size_transaction_journal_writer" if not blockers else "resolve_heap_snapshot_retained_size_transaction_preflight_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "transaction_preflight_only": True,
            "retained_size_only": True,
            "default_recon": False,
            "files_mutated": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
            "journal_written_now": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()


@dataclass(slots=True)
class HeapSnapshotRetainedSizeBoundedGateSpec:
    """Review-only bounded gate before retained-size executor work."""

    transaction_journal_descriptor: dict[str, Any] | None = None
    reviewer: str | None = None
    expected_journal_id: str | None = None
    expected_transaction_preflight_id: str | None = None
    expected_transaction_plan_id: str | None = None
    expected_approval_plan_id: str | None = None
    expected_candidate_digest: str | None = None
    expected_journal_digest_sha256: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeBoundedGateSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_size_bounded_gate",
                "heapSnapshotRetainedSizeBoundedGate",
                "heap_snapshot_retained_size_bounded_executor_gate",
                "heapSnapshotRetainedSizeBoundedExecutorGate",
                "heap_snapshot_retained_size_executor_bounded_gate",
                "heapSnapshotRetainedSizeExecutorBoundedGate",
                "review_heap_snapshot_retained_size_bounded_gate",
                "reviewHeapSnapshotRetainedSizeBoundedGate",
            )
        )
        journal = context.get(
            "heap_snapshot_retained_size_transaction_journal",
            context.get(
                "heapSnapshotRetainedSizeTransactionJournal",
                context.get(
                    "heap_snapshot_retained_size_executor_journal",
                    context.get(
                        "heapSnapshotRetainedSizeExecutorJournal",
                        context.get(
                            "heap_snapshot_retained_size_transaction_journal_descriptor",
                            context.get("heapSnapshotRetainedSizeTransactionJournalDescriptor"),
                        ),
                    ),
                ),
            ),
        )
        if not requested and not journal:
            return None
        expected_journal_id = context.get("expected_journal_id", context.get("expectedJournalId"))
        expected_transaction_preflight_id = context.get("expected_transaction_preflight_id", context.get("expectedTransactionPreflightId"))
        expected_transaction_plan_id = context.get("expected_transaction_plan_id", context.get("expectedTransactionPlanId"))
        expected_approval_plan_id = context.get("expected_approval_plan_id", context.get("expectedApprovalPlanId"))
        expected_candidate_digest = context.get("expected_candidate_digest", context.get("expectedCandidateDigest"))
        expected_journal_digest_sha256 = context.get("expected_journal_digest_sha256", context.get("expectedJournalDigestSha256"))
        return cls(
            transaction_journal_descriptor=journal if isinstance(journal, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            expected_journal_id=str(expected_journal_id).strip() if expected_journal_id else None,
            expected_transaction_preflight_id=str(expected_transaction_preflight_id).strip() if expected_transaction_preflight_id else None,
            expected_transaction_plan_id=str(expected_transaction_plan_id).strip() if expected_transaction_plan_id else None,
            expected_approval_plan_id=str(expected_approval_plan_id).strip() if expected_approval_plan_id else None,
            expected_candidate_digest=str(expected_candidate_digest).strip() if expected_candidate_digest else None,
            expected_journal_digest_sha256=str(expected_journal_digest_sha256).strip() if expected_journal_digest_sha256 else None,
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeBoundedGateResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedSizeBoundedGateManager:
    """Read-only bounded gate for a future retained-size executor."""

    def review(self, spec: HeapSnapshotRetainedSizeBoundedGateSpec | None) -> HeapSnapshotRetainedSizeBoundedGateResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._base_descriptor(status="blocked", reason="missing_heap_snapshot_retained_size_bounded_gate_request")
            return HeapSnapshotRetainedSizeBoundedGateResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_retained_size_bounded_gate_request")

        journal = spec.transaction_journal_descriptor or {}
        journal_digest = self._digest(journal) if journal else ""
        gates = journal.get("executor_input_gates") if isinstance(journal.get("executor_input_gates"), dict) else {}
        journal_summary = journal.get("journal_summary") if isinstance(journal.get("journal_summary"), dict) else {}
        source_preflight = journal.get("source_transaction_preflight_summary") if isinstance(journal.get("source_transaction_preflight_summary"), dict) else {}
        candidate_summary = journal.get("candidate_summary") if isinstance(journal.get("candidate_summary"), dict) else {}
        checks = self._checks(
            spec=spec,
            journal=journal,
            gates=gates,
            journal_summary=journal_summary,
            source_preflight=source_preflight,
            journal_digest=journal_digest,
        )
        blockers = [check["name"] for check in checks if not check["passed"]]
        ready = not blockers
        descriptor = self._descriptor(
            spec=spec,
            journal=journal,
            gates=gates,
            journal_summary=journal_summary,
            source_preflight=source_preflight,
            candidate_summary=candidate_summary,
            journal_digest=journal_digest,
            blockers=blockers,
            checks=checks,
            side_effect_policy=policy,
        )
        return HeapSnapshotRetainedSizeBoundedGateResult(status="ready_for_review" if ready else "blocked", descriptor=descriptor, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1",
            "status": status,
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "retained_size_only": True,
            "reason": reason,
            "source_transaction_journal_schema_version": "",
            "source_transaction_journal_status": "",
            "source_transaction_journal_digest_sha256": "",
            "journal_id": "",
            "transaction_preflight_id": "",
            "transaction_plan_id": "",
            "approval_plan_id": "",
            "candidate_digest": "",
            "reviewer": None,
            "transaction_journal_verified": False,
            "bounded_executor_gate_ready_for_review": False,
            "ready_for_executor_review": False,
            "ready_to_execute_now": False,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_executor_implemented": False,
            "bounded_executor_input": {},
            "future_executor_contract": {},
            "source_journal_summary": {},
            "checks": [],
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_written_heap_snapshot_retained_size_transaction_journal",
            "side_effect_policy": self._side_effect_policy(),
        }

    def _descriptor(
        self,
        *,
        spec: HeapSnapshotRetainedSizeBoundedGateSpec,
        journal: dict[str, Any],
        gates: dict[str, Any],
        journal_summary: dict[str, Any],
        source_preflight: dict[str, Any],
        candidate_summary: dict[str, Any],
        journal_digest: str,
        blockers: list[str],
        checks: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        ready = not blockers
        result_artifact = "workspace/heap-snapshot-retained-size-analysis.json"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1",
            "status": "ready_for_review" if ready else "blocked",
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "retained_size_only": True,
            "source_transaction_journal_schema_version": str(journal.get("schema_version") or ""),
            "source_transaction_journal_status": str(journal.get("status") or ""),
            "source_transaction_journal_digest_sha256": journal_digest,
            "expected_journal_digest_sha256": spec.expected_journal_digest_sha256,
            "journal_id": str(journal.get("journal_id") or ""),
            "transaction_preflight_id": str(journal.get("transaction_preflight_id") or ""),
            "transaction_plan_id": str(journal.get("transaction_plan_id") or ""),
            "approval_plan_id": str(journal.get("approval_plan_id") or ""),
            "candidate_digest": str(journal.get("candidate_digest") or candidate_summary.get("candidate_digest") or ""),
            "reviewer": spec.reviewer,
            "transaction_journal_verified": ready,
            "bounded_executor_gate_ready_for_review": ready,
            "ready_for_executor_review": ready,
            "ready_to_execute_now": False,
            "transaction_started": bool(journal.get("transaction_started")),
            "journal_written": bool(journal.get("journal_written")),
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "retained_size_executor_implemented": False,
            "bounded_executor_input": self._bounded_executor_input(journal, gates, source_preflight, candidate_summary, result_artifact, ready),
            "future_executor_contract": self._future_executor_contract(result_artifact, ready),
            "source_journal_summary": self._journal_summary(journal, journal_summary, gates),
            "checks": checks,
            "blockers": blockers,
            "warnings": self._warnings(ready),
            "next_action": self._next_action(blockers),
            "side_effect_policy": side_effect_policy,
        }

    @classmethod
    def _checks(
        cls,
        *,
        spec: HeapSnapshotRetainedSizeBoundedGateSpec,
        journal: dict[str, Any],
        gates: dict[str, Any],
        journal_summary: dict[str, Any],
        source_preflight: dict[str, Any],
        journal_digest: str,
    ) -> list[dict[str, Any]]:
        blockers = journal.get("blockers") if isinstance(journal.get("blockers"), list) else []
        policy = journal.get("side_effect_policy") if isinstance(journal.get("side_effect_policy"), dict) else {}
        return [
            {"name": "transaction_journal_available", "passed": bool(journal), "details": {"journal_id": journal.get("journal_id")}},
            {"name": "transaction_journal_schema_matches", "passed": journal.get("schema_version") == "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1", "details": {"schema_version": journal.get("schema_version")}},
            {"name": "transaction_journal_written", "passed": journal.get("status") == "written" and journal.get("journal_written") is True, "details": {"status": journal.get("status"), "journal_written": journal.get("journal_written")}},
            {"name": "transaction_started", "passed": journal.get("transaction_started") is True and journal_summary.get("transaction_started") is True, "details": {"transaction_started": journal.get("transaction_started"), "summary_transaction_started": journal_summary.get("transaction_started")}},
            {"name": "journal_has_no_blockers", "passed": not blockers, "details": {"blockers": blockers}},
            {"name": "retained_size_only", "passed": source_preflight.get("retained_size_only") is True or journal.get("retained_size_only") is True or journal.get("schema_version") == "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1", "details": {"source_retained_size_only": source_preflight.get("retained_size_only"), "journal_retained_size_only": journal.get("retained_size_only")}},
            {"name": "bounded_gate_followup_required", "passed": gates.get("requires_bounded_executor_gate") is True or journal_summary.get("requires_bounded_executor_gate_followup") is True, "details": {"gate_requires_bounded_executor_gate": gates.get("requires_bounded_executor_gate"), "summary_requires_bounded_executor_gate_followup": journal_summary.get("requires_bounded_executor_gate_followup")}},
            {"name": "explicit_executor_review_required", "passed": gates.get("requires_explicit_executor_review") is True, "details": {"requires_explicit_executor_review": gates.get("requires_explicit_executor_review")}},
            {"name": "journal_not_ready_to_execute_now", "passed": journal.get("ready_to_execute_now") is not True and gates.get("ready_to_execute_now") is not True, "details": {"journal_ready_to_execute_now": journal.get("ready_to_execute_now"), "gate_ready_to_execute_now": gates.get("ready_to_execute_now")}},
            {"name": "bounded_gate_not_already_written", "passed": journal.get("bounded_executor_gate_written") is not True and journal_summary.get("bounded_executor_gate_written") is not True and gates.get("bounded_executor_gate_written") is not True and policy.get("bounded_executor_gate_written") is not True, "details": {"journal_bounded_executor_gate_written": journal.get("bounded_executor_gate_written"), "summary_bounded_executor_gate_written": journal_summary.get("bounded_executor_gate_written"), "gate_bounded_executor_gate_written": gates.get("bounded_executor_gate_written"), "policy_bounded_executor_gate_written": policy.get("bounded_executor_gate_written")}},
            {"name": "executor_not_invoked", "passed": journal.get("executor_invoked") is not True and journal_summary.get("executor_invoked") is not True and gates.get("executor_invoked") is not True and policy.get("executor_invoked") is not True, "details": {"journal_executor_invoked": journal.get("executor_invoked"), "summary_executor_invoked": journal_summary.get("executor_invoked"), "gate_executor_invoked": gates.get("executor_invoked"), "policy_executor_invoked": policy.get("executor_invoked")}},
            {"name": "raw_heap_not_loaded", "passed": journal.get("raw_heap_loaded") is not True and journal_summary.get("raw_heap_loaded") is not True and gates.get("raw_heap_loaded") is not True and policy.get("raw_heap_loaded") is not True, "details": {"journal_raw_heap_loaded": journal.get("raw_heap_loaded"), "summary_raw_heap_loaded": journal_summary.get("raw_heap_loaded"), "gate_raw_heap_loaded": gates.get("raw_heap_loaded"), "policy_raw_heap_loaded": policy.get("raw_heap_loaded")}},
            {"name": "raw_heap_not_parsed", "passed": journal.get("raw_heap_parsed") is not True and journal_summary.get("raw_heap_parsed") is not True and gates.get("raw_heap_parsed") is not True and policy.get("raw_heap_parsed") is not True, "details": {"journal_raw_heap_parsed": journal.get("raw_heap_parsed"), "summary_raw_heap_parsed": journal_summary.get("raw_heap_parsed"), "gate_raw_heap_parsed": gates.get("raw_heap_parsed"), "policy_raw_heap_parsed": policy.get("raw_heap_parsed")}},
            {"name": "raw_heap_not_exported", "passed": journal.get("raw_heap_exported") is not True and journal_summary.get("raw_heap_exported") is not True and gates.get("raw_heap_exported") is not True and policy.get("raw_heap_exported") is not True, "details": {"journal_raw_heap_exported": journal.get("raw_heap_exported"), "summary_raw_heap_exported": journal_summary.get("raw_heap_exported"), "gate_raw_heap_exported": gates.get("raw_heap_exported"), "policy_raw_heap_exported": policy.get("raw_heap_exported")}},
            {"name": "raw_strings_not_exported", "passed": journal.get("raw_strings_exported") is not True and gates.get("raw_strings_exported") is not True and policy.get("raw_strings_exported") is not True, "details": {"journal_raw_strings_exported": journal.get("raw_strings_exported"), "gate_raw_strings_exported": gates.get("raw_strings_exported"), "policy_raw_strings_exported": policy.get("raw_strings_exported")}},
            {"name": "heap_diff_not_computed", "passed": journal.get("heap_diff_computed") is not True and journal_summary.get("heap_diff_computed") is not True and gates.get("heap_diff_computed") is not True and policy.get("heap_diff_computed") is not True and policy.get("heap_snapshot_diff_computed") is not True, "details": {"journal_heap_diff_computed": journal.get("heap_diff_computed"), "summary_heap_diff_computed": journal_summary.get("heap_diff_computed"), "gate_heap_diff_computed": gates.get("heap_diff_computed"), "policy_heap_diff_computed": policy.get("heap_diff_computed")}},
            {"name": "retained_size_not_proven", "passed": journal.get("retained_size_proven") is not True and journal_summary.get("retained_size_proven") is not True and gates.get("retained_size_proven") is not True and policy.get("retained_size_proven") is not True, "details": {"journal_retained_size_proven": journal.get("retained_size_proven"), "summary_retained_size_proven": journal_summary.get("retained_size_proven"), "gate_retained_size_proven": gates.get("retained_size_proven"), "policy_retained_size_proven": policy.get("retained_size_proven")}},
            {"name": "path_to_root_not_computed", "passed": journal.get("path_to_root_computed") is not True and journal_summary.get("path_to_root_computed") is not True and gates.get("path_to_root_computed") is not True and policy.get("path_to_root_computed") is not True, "details": {"journal_path_to_root_computed": journal.get("path_to_root_computed"), "summary_path_to_root_computed": journal_summary.get("path_to_root_computed"), "gate_path_to_root_computed": gates.get("path_to_root_computed"), "policy_path_to_root_computed": policy.get("path_to_root_computed")}},
            {"name": "complete_heap_traversal_not_claimed", "passed": journal.get("complete_heap_traversal_claimed") is not True and gates.get("complete_heap_traversal_claimed") is not True and policy.get("complete_heap_traversal") is not True, "details": {"journal_complete_heap_traversal_claimed": journal.get("complete_heap_traversal_claimed"), "gate_complete_heap_traversal_claimed": gates.get("complete_heap_traversal_claimed"), "policy_complete_heap_traversal": policy.get("complete_heap_traversal")}},
            {"name": "retained_size_executor_not_implemented", "passed": journal.get("retained_size_executor_implemented") is not True and gates.get("retained_size_executor_implemented") is not True, "details": {"journal_retained_size_executor_implemented": journal.get("retained_size_executor_implemented"), "gate_retained_size_executor_implemented": gates.get("retained_size_executor_implemented")}},
            {"name": "transaction_plan_id_present", "passed": bool(journal.get("transaction_plan_id")), "details": {"transaction_plan_id": journal.get("transaction_plan_id")}},
            {"name": "approval_plan_id_present", "passed": bool(journal.get("approval_plan_id")), "details": {"approval_plan_id": journal.get("approval_plan_id")}},
            {"name": "candidate_digest_present", "passed": bool(journal.get("candidate_digest")), "details": {"candidate_digest": journal.get("candidate_digest")}},
            {"name": "expected_journal_id_matches", "passed": not spec.expected_journal_id or journal.get("journal_id") == spec.expected_journal_id, "details": {"expected_journal_id": spec.expected_journal_id, "journal_id": journal.get("journal_id")}},
            {"name": "expected_transaction_preflight_id_matches", "passed": not spec.expected_transaction_preflight_id or journal.get("transaction_preflight_id") == spec.expected_transaction_preflight_id, "details": {"expected_transaction_preflight_id": spec.expected_transaction_preflight_id, "transaction_preflight_id": journal.get("transaction_preflight_id")}},
            {"name": "expected_transaction_plan_id_matches", "passed": not spec.expected_transaction_plan_id or journal.get("transaction_plan_id") == spec.expected_transaction_plan_id, "details": {"expected_transaction_plan_id": spec.expected_transaction_plan_id, "transaction_plan_id": journal.get("transaction_plan_id")}},
            {"name": "expected_approval_plan_id_matches", "passed": not spec.expected_approval_plan_id or journal.get("approval_plan_id") == spec.expected_approval_plan_id, "details": {"expected_approval_plan_id": spec.expected_approval_plan_id, "approval_plan_id": journal.get("approval_plan_id")}},
            {"name": "expected_candidate_digest_matches", "passed": not spec.expected_candidate_digest or journal.get("candidate_digest") == spec.expected_candidate_digest, "details": {"expected_candidate_digest": spec.expected_candidate_digest, "candidate_digest": journal.get("candidate_digest")}},
            {"name": "expected_journal_digest_matches", "passed": not spec.expected_journal_digest_sha256 or journal_digest == spec.expected_journal_digest_sha256, "details": {"expected_journal_digest_sha256": spec.expected_journal_digest_sha256, "transaction_journal_digest_sha256": journal_digest}},
            {"name": "journal_has_no_forbidden_runtime_side_effects", "passed": cls._journal_has_no_forbidden_runtime_side_effects(policy), "details": policy},
        ]

    @staticmethod
    def _bounded_executor_input(journal: dict[str, Any], gates: dict[str, Any], source_preflight: dict[str, Any], candidate_summary: dict[str, Any], result_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-bounded-input.v1",
            "journal_id": journal.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id"),
            "transaction_plan_id": journal.get("transaction_plan_id"),
            "approval_plan_id": journal.get("approval_plan_id"),
            "candidate_digest": journal.get("candidate_digest") or candidate_summary.get("candidate_digest"),
            "result_artifact": result_artifact,
            "ready_for_executor_review": ready,
            "ready_to_execute_now": False,
            "retained_size_only": True,
            "requires_separate_executor_call": True,
            "requires_explicit_executor_review": True,
            "requires_raw_heap": True,
            "requires_bounded_budget": True,
            "requires_safe_raw_heap_parser": True,
            "requires_redacted_result_artifact": True,
            "requires_no_raw_heap_export": True,
            "requires_no_raw_strings_export": True,
            "requires_no_complete_traversal_claim": True,
            "bounded_executor_gate_written": False,
            "executor_invoked": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "retained_size_executor_implemented": False,
            "source_transaction_preflight_summary": {
                "schema_version": source_preflight.get("schema_version"),
                "status": source_preflight.get("status"),
                "ready_to_write_journal": source_preflight.get("ready_to_write_journal"),
                "ready_to_execute_now": source_preflight.get("ready_to_execute_now"),
            },
            "source_executor_input_gates": {
                "approval_record_verified": bool(gates.get("approval_record_verified")),
                "transaction_started": bool(gates.get("transaction_started")),
                "journal_written": bool(gates.get("journal_written")),
                "requires_bounded_executor_gate": bool(gates.get("requires_bounded_executor_gate")),
                "requires_explicit_executor_review": bool(gates.get("requires_explicit_executor_review")),
            },
        }

    @staticmethod
    def _future_executor_contract(result_artifact: str, ready: bool) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-executor-contract.v1",
            "executor_name": "execute_heap_snapshot_retained_size_analysis",
            "implemented": False,
            "contract_ready_for_review": ready,
            "result_artifact": result_artifact,
            "requires_written_transaction_journal": True,
            "requires_bounded_executor_gate": True,
            "requires_explicit_executor_review": True,
            "requires_raw_heap": True,
            "requires_bounded_budget": True,
            "requires_safe_raw_heap_parser": True,
            "requires_redacted_result_artifact": True,
            "requires_no_raw_heap_export": True,
            "requires_no_raw_strings_export": True,
            "requires_no_complete_traversal_claim": True,
            "path_to_root_executor_separate": True,
        }

    @staticmethod
    def _journal_summary(journal: dict[str, Any], journal_summary: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": journal.get("schema_version"),
            "status": journal.get("status"),
            "journal_id": journal.get("journal_id"),
            "transaction_preflight_id": journal.get("transaction_preflight_id"),
            "transaction_plan_id": journal.get("transaction_plan_id"),
            "approval_plan_id": journal.get("approval_plan_id"),
            "candidate_digest": journal.get("candidate_digest"),
            "transaction_started": bool(journal.get("transaction_started")) or bool(journal_summary.get("transaction_started")) or bool(gates.get("transaction_started")),
            "journal_written": bool(journal.get("journal_written")) or bool(journal_summary.get("journal_written")) or bool(gates.get("journal_written")),
            "requires_bounded_executor_gate_followup": bool(journal_summary.get("requires_bounded_executor_gate_followup")) or bool(gates.get("requires_bounded_executor_gate")),
            "bounded_executor_gate_written": bool(journal_summary.get("bounded_executor_gate_written")) or bool(gates.get("bounded_executor_gate_written")),
            "executor_invoked": bool(journal_summary.get("executor_invoked")) or bool(gates.get("executor_invoked")),
            "raw_heap_loaded": bool(journal_summary.get("raw_heap_loaded")) or bool(gates.get("raw_heap_loaded")),
            "raw_heap_parsed": bool(journal_summary.get("raw_heap_parsed")) or bool(gates.get("raw_heap_parsed")),
            "raw_heap_exported": bool(journal_summary.get("raw_heap_exported")) or bool(gates.get("raw_heap_exported")),
            "raw_strings_exported": bool(gates.get("raw_strings_exported")),
            "heap_diff_computed": bool(journal_summary.get("heap_diff_computed")) or bool(gates.get("heap_diff_computed")),
            "retained_size_proven": bool(journal_summary.get("retained_size_proven")) or bool(gates.get("retained_size_proven")),
            "path_to_root_computed": bool(journal_summary.get("path_to_root_computed")) or bool(gates.get("path_to_root_computed")),
        }

    @staticmethod
    def _warnings(ready: bool) -> list[str]:
        warnings = ["heap_snapshot_retained_size_bounded_gate_is_not_executor", "heap_snapshot_retained_size_raw_heap_parser_required_after_gate"]
        if ready:
            warnings.append("heap_snapshot_retained_size_bounded_gate_ready_for_executor_review")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str]) -> str:
        if blockers:
            return "provide_written_heap_snapshot_retained_size_transaction_journal"
        return "review_heap_snapshot_retained_size_executor_mvp"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "bounded_executor_gate_only": True,
            "retained_size_only": True,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "transaction_started": False,
            "journal_written": False,
            "bounded_executor_gate_written": False,
            "ready_to_execute_now": False,
            "executor_invoked": False,
            "future_executor_invoked": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _journal_has_no_forbidden_runtime_side_effects(policy: dict[str, Any]) -> bool:
        forbidden = (
            "bounded_executor_gate_written",
            "executor_invoked",
            "future_executor_invoked",
            "browser_started",
            "provider_factory_invoked",
            "provider_availability_checked",
            "cdp_command_sent",
            "heap_profiler_enabled",
            "heap_snapshot_collected",
            "heap_snapshot_diff_computed",
            "heap_diff_computed",
            "raw_heap_loaded",
            "raw_heap_parsed",
            "raw_heap_exported",
            "raw_strings_exported",
            "complete_heap_traversal",
            "retained_size_proven",
            "path_to_root_computed",
            "runtime_evaluated",
            "javascript_evaluated",
            "calls_mcp",
            "mobile_runtime_used",
        )
        return not any(policy.get(key) is True for key in forbidden)

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()


@dataclass(slots=True)
class HeapSnapshotDiffExecutorSpec:
    """Explicit-review-only MVP executor for redacted V8 heap snapshot summary diffs.

    The executor consumes caller-provided raw heap snapshot JSON objects and a ready
    bounded-gate descriptor. It never reads heap files by path, never exports raw
    heap content, and only emits bounded summary / diff metadata.
    """

    bounded_gate_descriptor: dict[str, Any] | None = None
    before_heap_snapshot: dict[str, Any] | None = None
    after_heap_snapshot: dict[str, Any] | None = None
    mode: str = "dry-run"
    review_approved: bool = False
    approve_execution: bool = False
    reviewer: str | None = None
    max_raw_heap_bytes: int = 5_000_000
    max_nodes: int = 100_000
    top_n: int = 20
    raw_heap_export_requested: bool = False
    complete_traversal_claim_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotDiffExecutorSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "execute_heap_snapshot_diff_executor",
                "executeHeapSnapshotDiffExecutor",
                "heap_snapshot_diff_executor_result",
                "heapSnapshotDiffExecutorResult",
                "heap_snapshot_diff_executor_mvp",
                "heapSnapshotDiffExecutorMvp",
                "raw_heap_diff_executor",
                "rawHeapDiffExecutor",
                "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp",
                "reviewHeapSnapshotDiffExecutorRawHeapParserOrExecutorMvp",
            )
        )
        bounded_gate = context.get(
            "heap_snapshot_diff_executor_bounded_gate",
            context.get(
                "heapSnapshotDiffExecutorBoundedGate",
                context.get("heap_snapshot_diff_executor_bounded_gate_descriptor", context.get("heapSnapshotDiffExecutorBoundedGateDescriptor")),
            ),
        )
        before_heap = context.get(
            "before_heap_snapshot",
            context.get("beforeHeapSnapshot", context.get("before_raw_heap_snapshot", context.get("beforeRawHeapSnapshot"))),
        )
        after_heap = context.get(
            "after_heap_snapshot",
            context.get("afterHeapSnapshot", context.get("after_raw_heap_snapshot", context.get("afterRawHeapSnapshot"))),
        )
        if not requested and not bounded_gate and not before_heap and not after_heap:
            return None
        gate_input = bounded_gate.get("bounded_executor_input") if isinstance(bounded_gate, dict) and isinstance(bounded_gate.get("bounded_executor_input"), dict) else {}
        preflight = gate_input.get("preflight_summary") if isinstance(gate_input.get("preflight_summary"), dict) else {}
        default_max_raw_heap_bytes = preflight.get("max_raw_heap_bytes") if isinstance(preflight.get("max_raw_heap_bytes"), int) else 5_000_000
        return cls(
            bounded_gate_descriptor=bounded_gate if isinstance(bounded_gate, dict) else None,
            before_heap_snapshot=before_heap if isinstance(before_heap, dict) else None,
            after_heap_snapshot=after_heap if isinstance(after_heap, dict) else None,
            mode=str(context.get("mode", "dry-run") or "dry-run"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            approve_execution=bool(
                context.get(
                    "approve_heap_snapshot_diff_executor_execution",
                    context.get("approveHeapSnapshotDiffExecutorExecution", context.get("approve_heap_snapshot_diff_executor", False)),
                )
            ),
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_raw_heap_bytes=max(1, int(context.get("max_raw_heap_bytes", context.get("maxRawHeapBytes", default_max_raw_heap_bytes)) or default_max_raw_heap_bytes)),
            max_nodes=max(1, int(context.get("max_nodes", context.get("maxNodes", 100_000)) or 100_000)),
            top_n=max(1, int(context.get("top_n", context.get("topN", 20)) or 20)),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotDiffExecutorResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class HeapSnapshotDiffExecutorManager:
    """Bounded explicit-review MVP for redacted V8 heap snapshot summary diffs."""

    _SENSITIVE_RE = re.compile(r"token|secret|password|passwd|cookie|authorization|apikey|api_key|credential", re.IGNORECASE)

    def execute(self, spec: HeapSnapshotDiffExecutorSpec | None) -> HeapSnapshotDiffExecutorResult:
        base_policy = self._side_effect_policy(executor_invoked=False, raw_heap_loaded=False, raw_heap_parsed=False, heap_diff_computed=False)
        if spec is None:
            descriptor = self._blocked_descriptor(None, ["missing_heap_snapshot_diff_executor_request"], base_policy)
            return HeapSnapshotDiffExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason="missing_heap_snapshot_diff_executor_request")

        blockers, warnings, gate_summary = self._pre_parse_checks(spec)
        if blockers:
            descriptor = self._blocked_descriptor(spec, blockers, base_policy, warnings=warnings, gate_summary=gate_summary)
            return HeapSnapshotDiffExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason=blockers[0])

        try:
            before_summary = self._parse_heap_snapshot(spec.before_heap_snapshot or {}, label="before", spec=spec)
            after_summary = self._parse_heap_snapshot(spec.after_heap_snapshot or {}, label="after", spec=spec)
            parse_blockers = []
            if before_summary.get("status") != "parsed":
                parse_blockers.append("before_heap_snapshot_parse_failed")
            if after_summary.get("status") != "parsed":
                parse_blockers.append("after_heap_snapshot_parse_failed")
            if parse_blockers:
                policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, heap_diff_computed=False)
                descriptor = self._blocked_descriptor(spec, parse_blockers, policy, warnings=warnings, gate_summary=gate_summary)
                descriptor["heap_summaries"] = {"before": before_summary, "after": after_summary}
                return HeapSnapshotDiffExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason=parse_blockers[0])
            diff = self._diff_summaries(before_summary, after_summary, spec=spec)
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=True, heap_diff_computed=True)
            descriptor = self._executed_descriptor(spec=spec, gate_summary=gate_summary, before_summary=before_summary, after_summary=after_summary, diff=diff, warnings=warnings, side_effect_policy=policy)
            return HeapSnapshotDiffExecutorResult(status="executed", descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, heap_diff_computed=False)
            descriptor = self._blocked_descriptor(spec, ["heap_snapshot_diff_executor_failed"], policy, warnings=warnings, gate_summary=gate_summary)
            descriptor["error"] = str(exc)
            return HeapSnapshotDiffExecutorResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_diff_executor_failed", error=str(exc))

    def _pre_parse_checks(self, spec: HeapSnapshotDiffExecutorSpec) -> tuple[list[str], list[str], dict[str, Any]]:
        blockers: list[str] = []
        warnings: list[str] = []
        gate = spec.bounded_gate_descriptor or {}
        gate_summary = self._gate_summary(gate)
        if not gate:
            blockers.append("heap_snapshot_diff_executor_bounded_gate_required")
        else:
            if gate.get("schema_version") != "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1":
                blockers.append("heap_snapshot_diff_executor_bounded_gate_schema_mismatch")
            if gate.get("status") not in {"ready_for_review", "ready"}:
                blockers.append("heap_snapshot_diff_executor_bounded_gate_not_ready")
            if gate.get("bounded_executor_gate_ready_for_review") is not True or gate.get("ready_for_executor_review") is not True:
                blockers.append("heap_snapshot_diff_executor_bounded_gate_review_not_ready")
            if gate.get("ready_to_execute_now") is True:
                blockers.append("heap_snapshot_diff_executor_bounded_gate_claims_ready_to_execute_now")
            policy = gate.get("side_effect_policy") if isinstance(gate.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(key)) for key in ("executor_invoked", "raw_heap_loaded", "raw_heap_parsed", "raw_heap_exported", "heap_diff_computed", "heap_snapshot_diff_computed")):
                blockers.append("heap_snapshot_diff_executor_bounded_gate_has_runtime_side_effects")
        if spec.mode != "apply":
            blockers.append("heap_snapshot_diff_executor_apply_mode_required")
        if not spec.review_approved:
            blockers.append("heap_snapshot_diff_executor_review_approval_required")
        if not spec.approve_execution:
            blockers.append("heap_snapshot_diff_executor_execution_approval_flag_required")
        if not spec.reviewer:
            blockers.append("heap_snapshot_diff_executor_reviewer_required")
        if not isinstance(spec.before_heap_snapshot, dict):
            blockers.append("before_heap_snapshot_required")
        if not isinstance(spec.after_heap_snapshot, dict):
            blockers.append("after_heap_snapshot_required")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        for label, snapshot in (("before", spec.before_heap_snapshot), ("after", spec.after_heap_snapshot)):
            if isinstance(snapshot, dict):
                size = self._json_size(snapshot)
                if size > spec.max_raw_heap_bytes:
                    blockers.append(f"{label}_heap_snapshot_exceeds_size_budget")
        warnings.append("heap_snapshot_diff_executor_mvp_summary_only")
        warnings.append("complete_heap_traversal_not_claimed")
        return blockers, warnings, gate_summary

    def _blocked_descriptor(
        self,
        spec: HeapSnapshotDiffExecutorSpec | None,
        blockers: list[str],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        gate_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-result.v1",
            "status": "blocked",
            "executor_name": "execute_heap_snapshot_diff_executor",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-diff-executor-result.json",
            "reviewer": spec.reviewer if spec else None,
            "gate_summary": gate_summary or {},
            "heap_summaries": {},
            "diff": {},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "resolve_heap_snapshot_diff_executor_result_blockers",
            "side_effect_policy": side_effect_policy,
        }

    def _executed_descriptor(
        self,
        *,
        spec: HeapSnapshotDiffExecutorSpec,
        gate_summary: dict[str, Any],
        before_summary: dict[str, Any],
        after_summary: dict[str, Any],
        diff: dict[str, Any],
        warnings: list[str],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-result.v1",
            "status": "executed",
            "executor_name": "execute_heap_snapshot_diff_executor",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-diff-executor-result.json",
            "reviewer": spec.reviewer,
            "gate_summary": gate_summary,
            "heap_summaries": {"before": before_summary, "after": after_summary},
            "diff": diff,
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "heap_snapshot_diff_computed": True,
            "heap_diff_computed": True,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": [],
            "warnings": warnings,
            "next_action": "review_heap_snapshot_diff_executor_result_before_followup",
            "side_effect_policy": side_effect_policy,
        }

    def _parse_heap_snapshot(self, snapshot: dict[str, Any], *, label: str, spec: HeapSnapshotDiffExecutorSpec) -> dict[str, Any]:
        snap = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}
        meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
        node_fields = meta.get("node_fields") if isinstance(meta.get("node_fields"), list) else []
        edge_fields = meta.get("edge_fields") if isinstance(meta.get("edge_fields"), list) else []
        node_types_meta = meta.get("node_types") if isinstance(meta.get("node_types"), list) else []
        edge_types_meta = meta.get("edge_types") if isinstance(meta.get("edge_types"), list) else []
        nodes = snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else []
        edges = snapshot.get("edges") if isinstance(snapshot.get("edges"), list) else []
        strings = snapshot.get("strings") if isinstance(snapshot.get("strings"), list) else []
        blockers: list[str] = []
        if not node_fields:
            blockers.append("node_fields_missing")
        if not nodes:
            blockers.append("nodes_missing")
        if not edge_fields:
            blockers.append("edge_fields_missing")
        if blockers:
            return {"label": label, "status": "blocked", "blockers": blockers, "raw_heap_digest_sha256": self._digest(snapshot), "raw_heap_size_bytes": self._json_size(snapshot)}
        node_field_count = len(node_fields)
        edge_field_count = len(edge_fields)
        node_count_total = len(nodes) // node_field_count if node_field_count else 0
        edge_count_total = len(edges) // edge_field_count if edge_field_count else 0
        node_type_names = node_types_meta[0] if node_types_meta and isinstance(node_types_meta[0], list) else []
        edge_type_names = edge_types_meta[0] if edge_types_meta and isinstance(edge_types_meta[0], list) else []
        type_idx = self._field_index(node_fields, "type")
        name_idx = self._field_index(node_fields, "name")
        self_size_idx = self._field_index(node_fields, "self_size")
        edge_type_idx = self._field_index(edge_fields, "type")
        node_type_counts: dict[str, int] = {}
        constructor_counts: dict[str, int] = {}
        self_size_total = 0
        analyzed_nodes = min(node_count_total, spec.max_nodes)
        for node_index in range(analyzed_nodes):
            offset = node_index * node_field_count
            node_type = self._typed_name(nodes, offset + type_idx, node_type_names, default="unknown") if type_idx >= 0 else "unknown"
            node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
            if self_size_idx >= 0:
                try:
                    self_size_total += int(nodes[offset + self_size_idx] or 0)
                except Exception as e:
                    _logger.debug("Failed to accumulate self_size for node: %s", e, exc_info=True)
                    pass  # noqa: intentional — some nodes have non-numeric self_size; safe to skip since total is approximate
            if name_idx >= 0 and node_type in {"object", "closure", "native", "synthetic", "code"}:
                name = self._string_at(strings, nodes[offset + name_idx] if offset + name_idx < len(nodes) else None)
                name = self._redact_name(name or "<anonymous>")
                constructor_counts[name] = constructor_counts.get(name, 0) + 1
        edge_type_counts: dict[str, int] = {}
        analyzed_edges = min(edge_count_total, spec.max_nodes * 4)
        for edge_index in range(analyzed_edges):
            offset = edge_index * edge_field_count
            edge_type = self._typed_name(edges, offset + edge_type_idx, edge_type_names, default="unknown") if edge_type_idx >= 0 else "unknown"
            edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1
        return {
            "label": label,
            "status": "parsed",
            "format": "v8_heap_snapshot",
            "raw_heap_digest_sha256": self._digest(snapshot),
            "raw_heap_size_bytes": self._json_size(snapshot),
            "node_count_total": node_count_total,
            "node_count_analyzed": analyzed_nodes,
            "node_analysis_truncated": node_count_total > analyzed_nodes,
            "edge_count_total": edge_count_total,
            "edge_count_analyzed": analyzed_edges,
            "edge_analysis_truncated": edge_count_total > analyzed_edges,
            "string_count": len(strings),
            "self_size_total_analyzed": self_size_total,
            "node_type_counts": dict(sorted(node_type_counts.items())),
            "edge_type_counts": dict(sorted(edge_type_counts.items())),
            "top_constructors": self._top_counts(constructor_counts, spec.top_n),
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal_claimed": False,
        }

    def _diff_summaries(self, before: dict[str, Any], after: dict[str, Any], *, spec: HeapSnapshotDiffExecutorSpec) -> dict[str, Any]:
        node_type_deltas = self._count_deltas(before.get("node_type_counts"), after.get("node_type_counts"))
        edge_type_deltas = self._count_deltas(before.get("edge_type_counts"), after.get("edge_type_counts"))
        constructor_before = {str(item.get("name")): int(item.get("count") or 0) for item in before.get("top_constructors", []) if isinstance(item, dict)}
        constructor_after = {str(item.get("name")): int(item.get("count") or 0) for item in after.get("top_constructors", []) if isinstance(item, dict)}
        constructor_deltas = self._count_deltas(constructor_before, constructor_after)[: spec.top_n]
        return {
            "summary_diff_only": True,
            "node_count_delta": int(after.get("node_count_total") or 0) - int(before.get("node_count_total") or 0),
            "edge_count_delta": int(after.get("edge_count_total") or 0) - int(before.get("edge_count_total") or 0),
            "self_size_total_analyzed_delta": int(after.get("self_size_total_analyzed") or 0) - int(before.get("self_size_total_analyzed") or 0),
            "node_type_deltas": node_type_deltas[: spec.top_n],
            "edge_type_deltas": edge_type_deltas[: spec.top_n],
            "top_constructor_deltas": constructor_deltas,
            "analysis_truncated": bool(before.get("node_analysis_truncated") or after.get("node_analysis_truncated") or before.get("edge_analysis_truncated") or after.get("edge_analysis_truncated")),
            "raw_heap_exported": False,
            "complete_heap_traversal_claimed": False,
        }

    @staticmethod
    def _count_deltas(before_counts: Any, after_counts: Any) -> list[dict[str, Any]]:
        before = before_counts if isinstance(before_counts, dict) else {}
        after = after_counts if isinstance(after_counts, dict) else {}
        rows: list[dict[str, Any]] = []
        for name in sorted(set(before) | set(after)):
            before_value = int(before.get(name) or 0)
            after_value = int(after.get(name) or 0)
            delta = after_value - before_value
            if delta:
                rows.append({"name": name, "before": before_value, "after": after_value, "delta": delta})
        rows.sort(key=lambda item: abs(int(item.get("delta") or 0)), reverse=True)
        return rows

    @staticmethod
    def _field_index(fields: list[Any], name: str) -> int:
        try:
            return [str(item) for item in fields].index(name)
        except ValueError:
            return -1

    @staticmethod
    def _typed_name(values: list[Any], index: int, names: list[Any], *, default: str) -> str:
        try:
            type_index = int(values[index])
            if 0 <= type_index < len(names):
                return str(names[type_index])
        except Exception as e:
            _logger.debug("Failed to resolve typed name at index in _typed_name: %s", e, exc_info=True)
            return default
        return default

    @staticmethod
    def _string_at(strings: list[Any], index: Any) -> str:
        try:
            idx = int(index)
            if 0 <= idx < len(strings):
                return str(strings[idx])
        except Exception as e:
            _logger.debug("Failed to resolve string at index in _string_at: %s", e, exc_info=True)
            return ""
        return ""

    def _redact_name(self, name: str) -> str:
        if self._SENSITIVE_RE.search(name):
            return "<redacted>"
        return name[:160]

    @staticmethod
    def _top_counts(counts: dict[str, int], limit: int) -> list[dict[str, Any]]:
        rows = [{"name": name, "count": count} for name, count in counts.items()]
        rows.sort(key=lambda item: (-int(item["count"]), str(item["name"])))
        return rows[:limit]

    @staticmethod
    def _gate_summary(gate: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": gate.get("schema_version"),
            "status": gate.get("status"),
            "journal_id": gate.get("journal_id"),
            "transaction_id": gate.get("transaction_id"),
            "idempotency_key": gate.get("idempotency_key"),
            "bounded_executor_gate_ready_for_review": bool(gate.get("bounded_executor_gate_ready_for_review")),
            "ready_for_executor_review": bool(gate.get("ready_for_executor_review")),
            "ready_to_execute_now": bool(gate.get("ready_to_execute_now")),
        }

    @staticmethod
    def _json_size(payload: dict[str, Any]) -> int:
        return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8", errors="replace"))

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()

    @staticmethod
    def _side_effect_policy(*, executor_invoked: bool, raw_heap_loaded: bool, raw_heap_parsed: bool, heap_diff_computed: bool) -> dict[str, Any]:
        return {
            "read_only": False if executor_invoked else True,
            "review_only": False if executor_invoked else True,
            "explicit_review_only": True,
            "executor_invoked": executor_invoked,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": heap_diff_computed,
            "heap_diff_computed": heap_diff_computed,
            "raw_heap_loaded": raw_heap_loaded,
            "raw_heap_parsed": raw_heap_parsed,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedSizeExecutorSpec:
    """Explicit-review-only MVP executor for bounded retained-size candidate estimates.

    This executor consumes a ready retained-size bounded gate plus a caller-provided
    V8 heap snapshot JSON object. It does not read heap files by path, does not
    export raw heap / string tables, and does not claim a complete retained-size
    proof. The MVP computes conservative candidate self-size and directly-owned
    local estimates suitable for review follow-up.
    """

    bounded_gate_descriptor: dict[str, Any] | None = None
    heap_snapshot: dict[str, Any] | None = None
    candidate_names: list[str] = field(default_factory=list)
    mode: str = "dry-run"
    review_approved: bool = False
    approve_execution: bool = False
    reviewer: str | None = None
    max_raw_heap_bytes: int = 5_000_000
    max_nodes: int = 100_000
    top_n: int = 20
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    complete_traversal_claim_requested: bool = False
    retained_size_proof_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeExecutorSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "execute_heap_snapshot_retained_size_analysis",
                "executeHeapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_analysis",
                "heapSnapshotRetainedSizeAnalysis",
                "heap_snapshot_retained_size_executor_result",
                "heapSnapshotRetainedSizeExecutorResult",
                "heap_snapshot_retained_size_executor_mvp",
                "heapSnapshotRetainedSizeExecutorMvp",
                "retained_size_heap_snapshot_executor",
                "retainedSizeHeapSnapshotExecutor",
            )
        )
        bounded_gate = context.get(
            "heap_snapshot_retained_size_bounded_gate",
            context.get(
                "heapSnapshotRetainedSizeBoundedGate",
                context.get(
                    "heap_snapshot_retained_size_bounded_gate_descriptor",
                    context.get("heapSnapshotRetainedSizeBoundedGateDescriptor"),
                ),
            ),
        )
        heap = context.get(
            "heap_snapshot",
            context.get(
                "heapSnapshot",
                context.get(
                    "raw_heap_snapshot",
                    context.get("rawHeapSnapshot", context.get("after_heap_snapshot", context.get("afterHeapSnapshot"))),
                ),
            ),
        )
        if not requested and not bounded_gate and not heap:
            return None
        bounded_input = bounded_gate.get("bounded_executor_input") if isinstance(bounded_gate, dict) and isinstance(bounded_gate.get("bounded_executor_input"), dict) else {}
        raw_names = context.get("candidate_names", context.get("candidateNames", context.get("candidate_name", context.get("candidateName"))))
        candidate_names: list[str] = []
        if isinstance(raw_names, list):
            candidate_names = [str(item).strip() for item in raw_names if str(item).strip()]
        elif raw_names:
            candidate_names = [str(raw_names).strip()]
        candidate_summary = bounded_gate.get("source_journal_summary", {}) if isinstance(bounded_gate, dict) and isinstance(bounded_gate.get("source_journal_summary"), dict) else {}
        candidate_from_summary = candidate_summary.get("top_candidate") or bounded_input.get("candidate_name") or bounded_input.get("candidate_digest")
        if not candidate_names and candidate_from_summary and not str(candidate_from_summary).startswith("sha256"):
            candidate_names = [str(candidate_from_summary)]
        return cls(
            bounded_gate_descriptor=bounded_gate if isinstance(bounded_gate, dict) else None,
            heap_snapshot=heap if isinstance(heap, dict) else None,
            candidate_names=candidate_names,
            mode=str(context.get("mode", "dry-run") or "dry-run"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            approve_execution=bool(
                context.get(
                    "approve_heap_snapshot_retained_size_execution",
                    context.get(
                        "approveHeapSnapshotRetainedSizeExecution",
                        context.get("approve_heap_snapshot_retained_size_analysis", context.get("approveHeapSnapshotRetainedSizeAnalysis", False)),
                    ),
                )
            ),
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_raw_heap_bytes=max(1, int(context.get("max_raw_heap_bytes", context.get("maxRawHeapBytes", 5_000_000)) or 5_000_000)),
            max_nodes=max(1, int(context.get("max_nodes", context.get("maxNodes", 100_000)) or 100_000)),
            top_n=max(1, int(context.get("top_n", context.get("topN", 20)) or 20)),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            retained_size_proof_requested=bool(context.get("retained_size_proof_requested", context.get("retainedSizeProofRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeExecutorResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class HeapSnapshotRetainedSizeExecutorManager:
    """Bounded explicit-review MVP for retained-size candidate estimates."""

    _SENSITIVE_RE = re.compile(r"token|secret|password|passwd|cookie|authorization|apikey|api_key|credential", re.IGNORECASE)

    def execute(self, spec: HeapSnapshotRetainedSizeExecutorSpec | None) -> HeapSnapshotRetainedSizeExecutorResult:
        base_policy = self._side_effect_policy(executor_invoked=False, raw_heap_loaded=False, raw_heap_parsed=False, retained_size_estimated=False)
        if spec is None:
            descriptor = self._blocked_descriptor(None, ["missing_heap_snapshot_retained_size_executor_request"], base_policy)
            return HeapSnapshotRetainedSizeExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason="missing_heap_snapshot_retained_size_executor_request")

        blockers, warnings, gate_summary = self._pre_parse_checks(spec)
        if blockers:
            descriptor = self._blocked_descriptor(spec, blockers, base_policy, warnings=warnings, gate_summary=gate_summary)
            return HeapSnapshotRetainedSizeExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason=blockers[0])

        try:
            analysis = self._analyze_heap_snapshot(spec.heap_snapshot or {}, spec=spec)
            if analysis.get("status") != "parsed":
                policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, retained_size_estimated=False)
                descriptor = self._blocked_descriptor(spec, ["heap_snapshot_retained_size_parse_failed"], policy, warnings=warnings, gate_summary=gate_summary)
                descriptor["heap_summary"] = analysis
                return HeapSnapshotRetainedSizeExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_retained_size_parse_failed")
            if not analysis.get("candidate_estimates"):
                policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=True, retained_size_estimated=False)
                descriptor = self._blocked_descriptor(spec, ["heap_snapshot_retained_size_candidates_not_found"], policy, warnings=warnings, gate_summary=gate_summary)
                descriptor["heap_summary"] = analysis
                return HeapSnapshotRetainedSizeExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_retained_size_candidates_not_found")
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=True, retained_size_estimated=True)
            descriptor = self._executed_descriptor(spec=spec, gate_summary=gate_summary, analysis=analysis, warnings=warnings, side_effect_policy=policy)
            return HeapSnapshotRetainedSizeExecutorResult(status="executed", descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, retained_size_estimated=False)
            descriptor = self._blocked_descriptor(spec, ["heap_snapshot_retained_size_executor_failed"], policy, warnings=warnings, gate_summary=gate_summary)
            descriptor["error"] = str(exc)
            return HeapSnapshotRetainedSizeExecutorResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_retained_size_executor_failed", error=str(exc))

    def _pre_parse_checks(self, spec: HeapSnapshotRetainedSizeExecutorSpec) -> tuple[list[str], list[str], dict[str, Any]]:
        blockers: list[str] = []
        warnings = ["heap_snapshot_retained_size_executor_mvp_estimate_only", "retained_size_proof_not_claimed", "path_to_root_not_computed"]
        gate = spec.bounded_gate_descriptor or {}
        gate_summary = self._gate_summary(gate)
        if not gate:
            blockers.append("heap_snapshot_retained_size_bounded_gate_required")
        else:
            if gate.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1":
                blockers.append("heap_snapshot_retained_size_bounded_gate_schema_mismatch")
            if gate.get("status") not in {"ready_for_review", "ready"}:
                blockers.append("heap_snapshot_retained_size_bounded_gate_not_ready")
            if gate.get("bounded_executor_gate_ready_for_review") is not True or gate.get("ready_for_executor_review") is not True:
                blockers.append("heap_snapshot_retained_size_bounded_gate_review_not_ready")
            if gate.get("retained_size_only") is not True:
                blockers.append("heap_snapshot_retained_size_bounded_gate_not_retained_size_only")
            if gate.get("ready_to_execute_now") is True:
                blockers.append("heap_snapshot_retained_size_bounded_gate_claims_ready_to_execute_now")
            future = gate.get("future_executor_contract") if isinstance(gate.get("future_executor_contract"), dict) else {}
            if future and future.get("executor_name") not in {None, "", "execute_heap_snapshot_retained_size_analysis"}:
                blockers.append("heap_snapshot_retained_size_future_executor_name_mismatch")
            policy = gate.get("side_effect_policy") if isinstance(gate.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(key)) for key in ("executor_invoked", "raw_heap_loaded", "raw_heap_parsed", "raw_heap_exported", "raw_strings_exported", "retained_size_proven", "path_to_root_computed")):
                blockers.append("heap_snapshot_retained_size_bounded_gate_has_runtime_side_effects")
        if spec.mode != "apply":
            blockers.append("heap_snapshot_retained_size_executor_apply_mode_required")
        if not spec.review_approved:
            blockers.append("heap_snapshot_retained_size_executor_review_approval_required")
        if not spec.approve_execution:
            blockers.append("heap_snapshot_retained_size_executor_execution_approval_flag_required")
        if not spec.reviewer:
            blockers.append("heap_snapshot_retained_size_executor_reviewer_required")
        if not isinstance(spec.heap_snapshot, dict):
            blockers.append("heap_snapshot_required")
        if not spec.candidate_names:
            blockers.append("heap_snapshot_retained_size_candidate_names_required")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.retained_size_proof_requested:
            blockers.append("retained_size_proof_claim_not_allowed_in_mvp")
        if isinstance(spec.heap_snapshot, dict) and self._json_size(spec.heap_snapshot) > spec.max_raw_heap_bytes:
            blockers.append("heap_snapshot_exceeds_size_budget")
        return blockers, warnings, gate_summary

    def _blocked_descriptor(
        self,
        spec: HeapSnapshotRetainedSizeExecutorSpec | None,
        blockers: list[str],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        gate_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "blocked",
            "executor_name": "execute_heap_snapshot_retained_size_analysis",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "reviewer": spec.reviewer if spec else None,
            "gate_summary": gate_summary or {},
            "requested_candidate_names": list(spec.candidate_names) if spec else [],
            "heap_summary": {},
            "candidate_estimates": [],
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "resolve_heap_snapshot_retained_size_analysis_blockers",
            "side_effect_policy": side_effect_policy,
        }

    def _executed_descriptor(
        self,
        *,
        spec: HeapSnapshotRetainedSizeExecutorSpec,
        gate_summary: dict[str, Any],
        analysis: dict[str, Any],
        warnings: list[str],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
            "status": "executed",
            "executor_name": "execute_heap_snapshot_retained_size_analysis",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "reviewer": spec.reviewer,
            "gate_summary": gate_summary,
            "requested_candidate_names": list(spec.candidate_names),
            "heap_summary": {key: value for key, value in analysis.items() if key != "candidate_estimates"},
            "candidate_estimates": analysis.get("candidate_estimates", []),
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": True,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": [],
            "warnings": warnings,
            "next_action": "review_heap_snapshot_retained_size_analysis_before_path_to_root_or_second_pass",
            "side_effect_policy": side_effect_policy,
        }

    def _analyze_heap_snapshot(self, snapshot: dict[str, Any], *, spec: HeapSnapshotRetainedSizeExecutorSpec) -> dict[str, Any]:
        snap = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}
        meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
        node_fields = meta.get("node_fields") if isinstance(meta.get("node_fields"), list) else []
        edge_fields = meta.get("edge_fields") if isinstance(meta.get("edge_fields"), list) else []
        node_types_meta = meta.get("node_types") if isinstance(meta.get("node_types"), list) else []
        edge_types_meta = meta.get("edge_types") if isinstance(meta.get("edge_types"), list) else []
        nodes = snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else []
        edges = snapshot.get("edges") if isinstance(snapshot.get("edges"), list) else []
        strings = snapshot.get("strings") if isinstance(snapshot.get("strings"), list) else []
        blockers: list[str] = []
        if not node_fields:
            blockers.append("node_fields_missing")
        if not nodes:
            blockers.append("nodes_missing")
        if not edge_fields:
            blockers.append("edge_fields_missing")
        if blockers:
            return {"status": "blocked", "blockers": blockers, "raw_heap_digest_sha256": self._digest(snapshot), "raw_heap_size_bytes": self._json_size(snapshot)}
        node_field_count = len(node_fields)
        edge_field_count = len(edge_fields)
        node_count_total = len(nodes) // node_field_count if node_field_count else 0
        edge_count_total = len(edges) // edge_field_count if edge_field_count else 0
        analyzed_nodes = min(node_count_total, spec.max_nodes)
        node_type_names = node_types_meta[0] if node_types_meta and isinstance(node_types_meta[0], list) else []
        edge_type_names = edge_types_meta[0] if edge_types_meta and isinstance(edge_types_meta[0], list) else []
        type_idx = self._field_index(node_fields, "type")
        name_idx = self._field_index(node_fields, "name")
        id_idx = self._field_index(node_fields, "id")
        self_size_idx = self._field_index(node_fields, "self_size")
        edge_count_idx = self._field_index(node_fields, "edge_count")
        edge_type_idx = self._field_index(edge_fields, "type")
        edge_name_idx = self._field_index(edge_fields, "name_or_index")
        edge_to_idx = self._field_index(edge_fields, "to_node")
        node_records: list[dict[str, Any]] = []
        inbound_counts: dict[int, int] = {}
        edge_cursor = 0
        for node_index in range(analyzed_nodes):
            offset = node_index * node_field_count
            raw_name = self._string_at(strings, nodes[offset + name_idx] if name_idx >= 0 and offset + name_idx < len(nodes) else None)
            node_type = self._typed_name(nodes, offset + type_idx, node_type_names, default="unknown") if type_idx >= 0 else "unknown"
            self_size = self._int_at(nodes, offset + self_size_idx) if self_size_idx >= 0 else 0
            edge_count = max(0, self._int_at(nodes, offset + edge_count_idx)) if edge_count_idx >= 0 else 0
            outgoing_edges: list[dict[str, Any]] = []
            for _ in range(edge_count):
                if edge_cursor + edge_field_count > len(edges):
                    break
                edge_offset = edge_cursor
                edge_type = self._typed_name(edges, edge_offset + edge_type_idx, edge_type_names, default="unknown") if edge_type_idx >= 0 else "unknown"
                edge_name = self._string_at(strings, edges[edge_offset + edge_name_idx] if edge_name_idx >= 0 and edge_offset + edge_name_idx < len(edges) else None)
                to_offset = self._int_at(edges, edge_offset + edge_to_idx) if edge_to_idx >= 0 else -1
                to_index = to_offset // node_field_count if node_field_count and to_offset >= 0 and to_offset % node_field_count == 0 else to_offset
                if 0 <= to_index < analyzed_nodes:
                    inbound_counts[to_index] = inbound_counts.get(to_index, 0) + 1
                outgoing_edges.append({"type": edge_type, "name": self._redact_name(edge_name), "to_index": to_index})
                edge_cursor += edge_field_count
            node_records.append({
                "node_index": node_index,
                "node_id": self._int_at(nodes, offset + id_idx) if id_idx >= 0 else node_index,
                "type": node_type,
                "raw_name": raw_name,
                "name": self._redact_name(raw_name or "<anonymous>"),
                "self_size": self_size,
                "edge_count": edge_count,
                "outgoing_edges": outgoing_edges,
            })
        requested = {name for name in spec.candidate_names}
        requested_redacted = {self._redact_name(name) for name in spec.candidate_names}
        candidate_rows: list[dict[str, Any]] = []
        for record in node_records:
            if requested and record["raw_name"] not in requested and record["name"] not in requested and record["name"] not in requested_redacted:
                continue
            directly_owned_size = 0
            directly_owned_count = 0
            sampled_edges: list[dict[str, Any]] = []
            for edge in record["outgoing_edges"][: spec.top_n]:
                target_index = int(edge.get("to_index") or -1)
                if 0 <= target_index < len(node_records):
                    target = node_records[target_index]
                    unique_owner = inbound_counts.get(target_index, 0) <= 1
                    if unique_owner and target_index != record["node_index"]:
                        directly_owned_size += int(target.get("self_size") or 0)
                        directly_owned_count += 1
                    sampled_edges.append({
                        "type": edge.get("type"),
                        "name": edge.get("name"),
                        "target_name": target.get("name"),
                        "target_type": target.get("type"),
                        "target_self_size": target.get("self_size"),
                        "unique_owner_estimate": unique_owner,
                    })
            candidate_rows.append({
                "name": record["name"],
                "node_type": record["type"],
                "node_id": record["node_id"],
                "node_index": record["node_index"],
                "self_size": record["self_size"],
                "directly_owned_node_count_estimate": directly_owned_count,
                "directly_owned_self_size_estimate": directly_owned_size,
                "retained_size_estimate": int(record["self_size"] or 0) + directly_owned_size,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "complete_heap_traversal_claimed": False,
                "sampled_outgoing_edges": sampled_edges,
            })
        candidate_rows.sort(key=lambda item: int(item.get("retained_size_estimate") or 0), reverse=True)
        return {
            "status": "parsed",
            "format": "v8_heap_snapshot",
            "raw_heap_digest_sha256": self._digest(snapshot),
            "raw_heap_size_bytes": self._json_size(snapshot),
            "node_count_total": node_count_total,
            "node_count_analyzed": analyzed_nodes,
            "node_analysis_truncated": node_count_total > analyzed_nodes,
            "edge_count_total": edge_count_total,
            "edge_count_analyzed": min(edge_count_total, edge_cursor // edge_field_count if edge_field_count else 0),
            "string_count": len(strings),
            "candidate_count": len(candidate_rows),
            "candidate_names_requested": list(spec.candidate_names),
            "candidate_estimates": candidate_rows[: spec.top_n],
            "analysis_method": "bounded_self_size_plus_direct_unique_outgoing_edge_estimate",
            "retained_size_estimated": bool(candidate_rows),
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal_claimed": False,
        }

    @staticmethod
    def _field_index(fields: list[Any], name: str) -> int:
        try:
            return [str(item) for item in fields].index(name)
        except ValueError:
            return -1

    @staticmethod
    def _typed_name(values: list[Any], index: int, names: list[Any], *, default: str) -> str:
        try:
            type_index = int(values[index])
            if 0 <= type_index < len(names):
                return str(names[type_index])
        except Exception as e:
            _logger.debug("Failed to resolve typed name at index in _typed_name: %s", e, exc_info=True)
            return default
        return default

    @staticmethod
    def _int_at(values: list[Any], index: int) -> int:
        try:
            return int(values[index] or 0)
        except Exception as e:
            _logger.debug("Failed to parse int value at index in _int_at: %s", e, exc_info=True)
            return 0

    @staticmethod
    def _string_at(strings: list[Any], index: Any) -> str:
        try:
            idx = int(index)
            if 0 <= idx < len(strings):
                return str(strings[idx])
        except Exception as e:
            _logger.debug("Failed to resolve string at index in _string_at: %s", e, exc_info=True)
            return ""
        return ""

    def _redact_name(self, name: str) -> str:
        if self._SENSITIVE_RE.search(name):
            return "<redacted>"
        return name[:160]

    @staticmethod
    def _gate_summary(gate: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": gate.get("schema_version"),
            "status": gate.get("status"),
            "journal_id": gate.get("journal_id"),
            "transaction_preflight_id": gate.get("transaction_preflight_id"),
            "transaction_plan_id": gate.get("transaction_plan_id"),
            "approval_plan_id": gate.get("approval_plan_id"),
            "candidate_digest": gate.get("candidate_digest"),
            "bounded_executor_gate_ready_for_review": bool(gate.get("bounded_executor_gate_ready_for_review")),
            "ready_for_executor_review": bool(gate.get("ready_for_executor_review")),
            "ready_to_execute_now": bool(gate.get("ready_to_execute_now")),
        }

    @staticmethod
    def _json_size(payload: dict[str, Any]) -> int:
        return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8", errors="replace"))

    @staticmethod
    def _digest(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
        return "sha256:" + hashlib.sha256(blob).hexdigest()

    @staticmethod
    def _side_effect_policy(*, executor_invoked: bool, raw_heap_loaded: bool, raw_heap_parsed: bool, retained_size_estimated: bool) -> dict[str, Any]:
        return {
            "read_only": False if executor_invoked else True,
            "review_only": False if executor_invoked else True,
            "explicit_review_only": True,
            "executor_invoked": executor_invoked,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": raw_heap_loaded,
            "raw_heap_parsed": raw_heap_parsed,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": retained_size_estimated,
            "retained_size_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotPathToRootExecutorSpec:
    """Explicit-review-only MVP executor for bounded heap snapshot path-to-root estimates.

    The executor consumes either an executed retained-size analysis result or a
    ready retained-size / path-to-root preflight descriptor plus a caller-provided
    V8 heap snapshot JSON object. It builds a bounded reverse-edge map and emits
    redacted candidate incoming-edge paths. It does not read heap files by path,
    export raw heap / strings, prove retained size, or claim complete reachability.
    """

    retained_size_analysis_descriptor: dict[str, Any] | None = None
    retained_path_preflight_descriptor: dict[str, Any] | None = None
    heap_snapshot: dict[str, Any] | None = None
    candidate_names: list[str] = field(default_factory=list)
    mode: str = "dry-run"
    review_approved: bool = False
    approve_execution: bool = False
    reviewer: str | None = None
    max_raw_heap_bytes: int = 5_000_000
    max_nodes: int = 100_000
    max_depth: int = 8
    top_n: int = 20
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    complete_traversal_claim_requested: bool = False
    retained_size_proof_requested: bool = False
    path_to_root_proof_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotPathToRootExecutorSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "execute_heap_snapshot_path_to_root_analysis",
                "executeHeapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_analysis",
                "heapSnapshotPathToRootAnalysis",
                "heap_snapshot_path_to_root_executor_result",
                "heapSnapshotPathToRootExecutorResult",
                "heap_snapshot_path_to_root_executor_mvp",
                "heapSnapshotPathToRootExecutorMvp",
                "path_to_root_heap_snapshot_executor",
                "pathToRootHeapSnapshotExecutor",
            )
        )
        retained_analysis = context.get(
            "heap_snapshot_retained_size_analysis",
            context.get(
                "heapSnapshotRetainedSizeAnalysis",
                context.get(
                    "heap_snapshot_retained_size_analysis_result",
                    context.get("heapSnapshotRetainedSizeAnalysisResult"),
                ),
            ),
        )
        retained_preflight = context.get(
            "heap_snapshot_retained_path_preflight",
            context.get(
                "heapSnapshotRetainedPathPreflight",
                context.get(
                    "heap_snapshot_retained_size_path_to_root_preflight",
                    context.get("heapSnapshotRetainedSizePathToRootPreflight"),
                ),
            ),
        )
        heap = context.get(
            "heap_snapshot",
            context.get(
                "heapSnapshot",
                context.get(
                    "raw_heap_snapshot",
                    context.get("rawHeapSnapshot", context.get("after_heap_snapshot", context.get("afterHeapSnapshot"))),
                ),
            ),
        )
        if not requested and not retained_analysis and not retained_preflight and not heap:
            return None
        raw_names = context.get("candidate_names", context.get("candidateNames", context.get("candidate_name", context.get("candidateName"))))
        candidate_names: list[str] = []
        if isinstance(raw_names, list):
            candidate_names = [str(item).strip() for item in raw_names if str(item).strip()]
        elif raw_names:
            candidate_names = [str(raw_names).strip()]
        if not candidate_names and isinstance(retained_analysis, dict):
            for item in retained_analysis.get("requested_candidate_names", []) if isinstance(retained_analysis.get("requested_candidate_names"), list) else []:
                if str(item).strip():
                    candidate_names.append(str(item).strip())
        if not candidate_names and isinstance(retained_analysis, dict):
            for item in retained_analysis.get("candidate_estimates", []) if isinstance(retained_analysis.get("candidate_estimates"), list) else []:
                name = item.get("name") if isinstance(item, dict) else None
                if name and str(name).strip():
                    candidate_names.append(str(name).strip())
        if not candidate_names and isinstance(retained_preflight, dict):
            for item in retained_preflight.get("candidate_inputs", []) if isinstance(retained_preflight.get("candidate_inputs"), list) else []:
                if not isinstance(item, dict):
                    continue
                name = item.get("candidate_name") or item.get("name")
                if name and str(name).strip() and not str(name).startswith("sha256"):
                    candidate_names.append(str(name).strip())
        deduped: list[str] = []
        for name in candidate_names:
            if name not in deduped:
                deduped.append(name)
        return cls(
            retained_size_analysis_descriptor=retained_analysis if isinstance(retained_analysis, dict) else None,
            retained_path_preflight_descriptor=retained_preflight if isinstance(retained_preflight, dict) else None,
            heap_snapshot=heap if isinstance(heap, dict) else None,
            candidate_names=deduped,
            mode=str(context.get("mode", "dry-run") or "dry-run"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            approve_execution=bool(
                context.get(
                    "approve_heap_snapshot_path_to_root_execution",
                    context.get(
                        "approveHeapSnapshotPathToRootExecution",
                        context.get("approve_heap_snapshot_path_to_root_analysis", context.get("approveHeapSnapshotPathToRootAnalysis", False)),
                    ),
                )
            ),
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_raw_heap_bytes=max(1, int(context.get("max_raw_heap_bytes", context.get("maxRawHeapBytes", 5_000_000)) or 5_000_000)),
            max_nodes=max(1, int(context.get("max_nodes", context.get("maxNodes", 100_000)) or 100_000)),
            max_depth=max(1, int(context.get("max_depth", context.get("maxDepth", 8)) or 8)),
            top_n=max(1, int(context.get("top_n", context.get("topN", 20)) or 20)),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            retained_size_proof_requested=bool(context.get("retained_size_proof_requested", context.get("retainedSizeProofRequested", False))),
            path_to_root_proof_requested=bool(context.get("path_to_root_proof_requested", context.get("pathToRootProofRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotPathToRootExecutorResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class HeapSnapshotPathToRootExecutorManager(HeapSnapshotRetainedSizeExecutorManager):
    """Bounded explicit-review MVP for heap snapshot path-to-root estimates."""

    def execute(self, spec: HeapSnapshotPathToRootExecutorSpec | None) -> HeapSnapshotPathToRootExecutorResult:
        base_policy = self._side_effect_policy(executor_invoked=False, raw_heap_loaded=False, raw_heap_parsed=False, path_to_root_estimated=False)
        if spec is None:
            descriptor = self._blocked_descriptor(None, ["missing_heap_snapshot_path_to_root_executor_request"], base_policy)
            return HeapSnapshotPathToRootExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason="missing_heap_snapshot_path_to_root_executor_request")
        blockers, warnings, source_summary = self._pre_parse_checks(spec)
        if blockers:
            descriptor = self._blocked_descriptor(spec, blockers, base_policy, warnings=warnings, source_summary=source_summary)
            return HeapSnapshotPathToRootExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason=blockers[0])
        try:
            analysis = self._analyze_heap_snapshot_for_paths(spec.heap_snapshot or {}, spec=spec)
            if analysis.get("status") != "parsed":
                policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, path_to_root_estimated=False)
                descriptor = self._blocked_descriptor(spec, ["heap_snapshot_path_to_root_parse_failed"], policy, warnings=warnings, source_summary=source_summary)
                descriptor["heap_summary"] = analysis
                return HeapSnapshotPathToRootExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_path_to_root_parse_failed")
            if not analysis.get("candidate_paths"):
                policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=True, path_to_root_estimated=False)
                descriptor = self._blocked_descriptor(spec, ["heap_snapshot_path_to_root_candidates_not_found"], policy, warnings=warnings, source_summary=source_summary)
                descriptor["heap_summary"] = analysis
                return HeapSnapshotPathToRootExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_path_to_root_candidates_not_found")
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=True, path_to_root_estimated=True)
            descriptor = self._executed_descriptor(spec=spec, source_summary=source_summary, analysis=analysis, warnings=warnings, side_effect_policy=policy)
            return HeapSnapshotPathToRootExecutorResult(status="executed", descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            policy = self._side_effect_policy(executor_invoked=True, raw_heap_loaded=True, raw_heap_parsed=False, path_to_root_estimated=False)
            descriptor = self._blocked_descriptor(spec, ["heap_snapshot_path_to_root_executor_failed"], policy, warnings=warnings, source_summary=source_summary)
            descriptor["error"] = str(exc)
            return HeapSnapshotPathToRootExecutorResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_path_to_root_executor_failed", error=str(exc))

    def _pre_parse_checks(self, spec: HeapSnapshotPathToRootExecutorSpec) -> tuple[list[str], list[str], dict[str, Any]]:
        blockers: list[str] = []
        warnings = ["heap_snapshot_path_to_root_executor_mvp_estimate_only", "path_to_root_proof_not_claimed", "retained_size_proof_not_claimed"]
        retained = spec.retained_size_analysis_descriptor or {}
        preflight = spec.retained_path_preflight_descriptor or {}
        source_summary = self._source_summary(retained, preflight)
        if not retained and not preflight:
            blockers.append("heap_snapshot_path_to_root_source_descriptor_required")
        if retained:
            if retained.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-analysis.v1":
                blockers.append("heap_snapshot_retained_size_analysis_schema_mismatch")
            if retained.get("status") != "executed":
                blockers.append("heap_snapshot_retained_size_analysis_not_executed")
            policy = retained.get("side_effect_policy") if isinstance(retained.get("side_effect_policy"), dict) else {}
            if retained.get("retained_size_estimated") is not True and policy.get("retained_size_estimated") is not True:
                blockers.append("heap_snapshot_retained_size_analysis_missing_estimate")
            if retained.get("raw_heap_exported") is True or policy.get("raw_heap_exported") is True:
                blockers.append("heap_snapshot_retained_size_analysis_exported_raw_heap")
            if retained.get("raw_strings_exported") is True or policy.get("raw_strings_exported") is True:
                blockers.append("heap_snapshot_retained_size_analysis_exported_raw_strings")
            if retained.get("path_to_root_computed") is True or policy.get("path_to_root_computed") is True:
                blockers.append("heap_snapshot_retained_size_analysis_already_computed_path_to_root")
        if preflight:
            if preflight.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-path-preflight.v1":
                blockers.append("heap_snapshot_retained_path_preflight_schema_mismatch")
            if preflight.get("status") not in {"ready_for_review", "ready"}:
                blockers.append("heap_snapshot_retained_path_preflight_not_ready")
            contracts = preflight.get("future_executor_contracts") if isinstance(preflight.get("future_executor_contracts"), dict) else {}
            path_contract = contracts.get("path_to_root_analysis") if isinstance(contracts.get("path_to_root_analysis"), dict) else {}
            if path_contract and path_contract.get("executor_name") not in {None, "", "execute_heap_snapshot_path_to_root_analysis"}:
                blockers.append("heap_snapshot_path_to_root_future_executor_name_mismatch")
            policy = preflight.get("side_effect_policy") if isinstance(preflight.get("side_effect_policy"), dict) else {}
            if any(bool(preflight.get(key)) or bool(policy.get(key)) for key in ("raw_heap_loaded", "raw_heap_parsed", "raw_heap_exported", "raw_strings_exported", "retained_size_proven", "path_to_root_computed")):
                blockers.append("heap_snapshot_retained_path_preflight_has_runtime_side_effects")
        if spec.mode != "apply":
            blockers.append("heap_snapshot_path_to_root_executor_apply_mode_required")
        if not spec.review_approved:
            blockers.append("heap_snapshot_path_to_root_executor_review_approval_required")
        if not spec.approve_execution:
            blockers.append("heap_snapshot_path_to_root_executor_execution_approval_flag_required")
        if not spec.reviewer:
            blockers.append("heap_snapshot_path_to_root_executor_reviewer_required")
        if not isinstance(spec.heap_snapshot, dict):
            blockers.append("heap_snapshot_required")
        if not spec.candidate_names:
            blockers.append("heap_snapshot_path_to_root_candidate_names_required")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.retained_size_proof_requested:
            blockers.append("retained_size_proof_claim_not_allowed_in_mvp")
        if spec.path_to_root_proof_requested:
            blockers.append("path_to_root_proof_claim_not_allowed_in_mvp")
        if isinstance(spec.heap_snapshot, dict) and self._json_size(spec.heap_snapshot) > spec.max_raw_heap_bytes:
            blockers.append("heap_snapshot_exceeds_size_budget")
        return blockers, warnings, source_summary

    def _blocked_descriptor(
        self,
        spec: HeapSnapshotPathToRootExecutorSpec | None,
        blockers: list[str],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        source_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "blocked",
            "executor_name": "execute_heap_snapshot_path_to_root_analysis",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": source_summary or {},
            "requested_candidate_names": list(spec.candidate_names) if spec else [],
            "heap_summary": {},
            "candidate_paths": [],
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": False,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "resolve_heap_snapshot_path_to_root_analysis_blockers",
            "side_effect_policy": side_effect_policy,
        }

    def _executed_descriptor(
        self,
        *,
        spec: HeapSnapshotPathToRootExecutorSpec,
        source_summary: dict[str, Any],
        analysis: dict[str, Any],
        warnings: list[str],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
            "status": "executed",
            "executor_name": "execute_heap_snapshot_path_to_root_analysis",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-path-to-root-analysis.json",
            "reviewer": spec.reviewer,
            "source_summary": source_summary,
            "requested_candidate_names": list(spec.candidate_names),
            "heap_summary": {key: value for key, value in analysis.items() if key != "candidate_paths"},
            "candidate_paths": analysis.get("candidate_paths", []),
            "raw_heap_loaded": True,
            "raw_heap_parsed": True,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "path_to_root_estimated": True,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": [],
            "warnings": warnings,
            "next_action": "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown",
            "side_effect_policy": side_effect_policy,
        }

    def _analyze_heap_snapshot_for_paths(self, snapshot: dict[str, Any], *, spec: HeapSnapshotPathToRootExecutorSpec) -> dict[str, Any]:
        snap = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}
        meta = snap.get("meta") if isinstance(snap.get("meta"), dict) else {}
        node_fields = meta.get("node_fields") if isinstance(meta.get("node_fields"), list) else []
        edge_fields = meta.get("edge_fields") if isinstance(meta.get("edge_fields"), list) else []
        node_types_meta = meta.get("node_types") if isinstance(meta.get("node_types"), list) else []
        edge_types_meta = meta.get("edge_types") if isinstance(meta.get("edge_types"), list) else []
        nodes = snapshot.get("nodes") if isinstance(snapshot.get("nodes"), list) else []
        edges = snapshot.get("edges") if isinstance(snapshot.get("edges"), list) else []
        strings = snapshot.get("strings") if isinstance(snapshot.get("strings"), list) else []
        blockers: list[str] = []
        if not node_fields:
            blockers.append("node_fields_missing")
        if not nodes:
            blockers.append("nodes_missing")
        if not edge_fields:
            blockers.append("edge_fields_missing")
        if blockers:
            return {"status": "blocked", "blockers": blockers, "raw_heap_digest_sha256": self._digest(snapshot), "raw_heap_size_bytes": self._json_size(snapshot)}
        node_field_count = len(node_fields)
        edge_field_count = len(edge_fields)
        node_count_total = len(nodes) // node_field_count if node_field_count else 0
        edge_count_total = len(edges) // edge_field_count if edge_field_count else 0
        analyzed_nodes = min(node_count_total, spec.max_nodes)
        node_type_names = node_types_meta[0] if node_types_meta and isinstance(node_types_meta[0], list) else []
        edge_type_names = edge_types_meta[0] if edge_types_meta and isinstance(edge_types_meta[0], list) else []
        type_idx = self._field_index(node_fields, "type")
        name_idx = self._field_index(node_fields, "name")
        id_idx = self._field_index(node_fields, "id")
        self_size_idx = self._field_index(node_fields, "self_size")
        edge_count_idx = self._field_index(node_fields, "edge_count")
        edge_type_idx = self._field_index(edge_fields, "type")
        edge_name_idx = self._field_index(edge_fields, "name_or_index")
        edge_to_idx = self._field_index(edge_fields, "to_node")
        node_records: list[dict[str, Any]] = []
        inbound_edges: dict[int, list[dict[str, Any]]] = {}
        edge_cursor = 0
        for node_index in range(analyzed_nodes):
            offset = node_index * node_field_count
            raw_name = self._string_at(strings, nodes[offset + name_idx] if name_idx >= 0 and offset + name_idx < len(nodes) else None)
            node_type = self._typed_name(nodes, offset + type_idx, node_type_names, default="unknown") if type_idx >= 0 else "unknown"
            edge_count = max(0, self._int_at(nodes, offset + edge_count_idx)) if edge_count_idx >= 0 else 0
            record = {
                "node_index": node_index,
                "node_id": self._int_at(nodes, offset + id_idx) if id_idx >= 0 else node_index,
                "type": node_type,
                "raw_name": raw_name,
                "name": self._redact_name(raw_name or "<anonymous>"),
                "self_size": self._int_at(nodes, offset + self_size_idx) if self_size_idx >= 0 else 0,
                "edge_count": edge_count,
            }
            node_records.append(record)
            for _ in range(edge_count):
                if edge_cursor + edge_field_count > len(edges):
                    break
                edge_offset = edge_cursor
                edge_type = self._typed_name(edges, edge_offset + edge_type_idx, edge_type_names, default="unknown") if edge_type_idx >= 0 else "unknown"
                edge_name = self._string_at(strings, edges[edge_offset + edge_name_idx] if edge_name_idx >= 0 and edge_offset + edge_name_idx < len(edges) else None)
                to_offset = self._int_at(edges, edge_offset + edge_to_idx) if edge_to_idx >= 0 else -1
                to_index = to_offset // node_field_count if node_field_count and to_offset >= 0 and to_offset % node_field_count == 0 else to_offset
                if 0 <= to_index < analyzed_nodes:
                    inbound_edges.setdefault(to_index, []).append({
                        "from_index": node_index,
                        "edge_type": edge_type,
                        "edge_name": self._redact_name(edge_name),
                    })
                edge_cursor += edge_field_count
        requested = {name for name in spec.candidate_names}
        requested_redacted = {self._redact_name(name) for name in spec.candidate_names}
        candidate_paths: list[dict[str, Any]] = []
        for record in node_records:
            if requested and record["raw_name"] not in requested and record["name"] not in requested and record["name"] not in requested_redacted:
                continue
            path_nodes, root_like = self._path_to_root(record["node_index"], node_records, inbound_edges, max_depth=spec.max_depth)
            candidate_paths.append({
                "candidate_name": record["name"],
                "candidate_node_type": record["type"],
                "candidate_node_id": record["node_id"],
                "candidate_node_index": record["node_index"],
                "bounded_path_to_root": path_nodes,
                "path_depth": max(0, len(path_nodes) - 1),
                "root_like_node_reached": root_like,
                "path_to_root_estimated": True,
                "path_to_root_proven": False,
                "retained_size_proven": False,
                "complete_heap_traversal_claimed": False,
            })
        candidate_paths.sort(key=lambda item: (not bool(item.get("root_like_node_reached")), int(item.get("path_depth") or 0)))
        return {
            "status": "parsed",
            "format": "v8_heap_snapshot",
            "raw_heap_digest_sha256": self._digest(snapshot),
            "raw_heap_size_bytes": self._json_size(snapshot),
            "node_count_total": node_count_total,
            "node_count_analyzed": analyzed_nodes,
            "node_analysis_truncated": node_count_total > analyzed_nodes,
            "edge_count_total": edge_count_total,
            "edge_count_analyzed": min(edge_count_total, edge_cursor // edge_field_count if edge_field_count else 0),
            "string_count": len(strings),
            "candidate_count": len(candidate_paths),
            "candidate_names_requested": list(spec.candidate_names),
            "candidate_paths": candidate_paths[: spec.top_n],
            "analysis_method": "bounded_reverse_edge_first_incoming_path_estimate",
            "path_to_root_estimated": bool(candidate_paths),
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "complete_heap_traversal_claimed": False,
        }

    def _path_to_root(self, start_index: int, node_records: list[dict[str, Any]], inbound_edges: dict[int, list[dict[str, Any]]], *, max_depth: int) -> tuple[list[dict[str, Any]], bool]:
        current = start_index
        seen: set[int] = set()
        reversed_path: list[dict[str, Any]] = []
        root_like = False
        depth = 0
        while 0 <= current < len(node_records) and current not in seen and depth <= max_depth:
            seen.add(current)
            record = node_records[current]
            incoming = inbound_edges.get(current, [])
            edge_from_parent = incoming[0] if incoming else None
            reversed_path.append({
                "node_name": record.get("name"),
                "node_type": record.get("type"),
                "node_id": record.get("node_id"),
                "node_index": record.get("node_index"),
                "incoming_edge_name": edge_from_parent.get("edge_name") if edge_from_parent else None,
                "incoming_edge_type": edge_from_parent.get("edge_type") if edge_from_parent else None,
            })
            if self._is_root_like(record, bool(incoming)):
                root_like = True
                break
            if not incoming:
                break
            current = int(incoming[0].get("from_index", -1))
            depth += 1
        path = list(reversed(reversed_path))
        return path, root_like

    @staticmethod
    def _is_root_like(record: dict[str, Any], has_incoming: bool) -> bool:
        name = str(record.get("name") or "")
        node_type = str(record.get("type") or "")
        return (not has_incoming) or node_type == "synthetic" or name in {"Window", "global", "globalThis", "<synthetic>", "(GC roots)"}

    @staticmethod
    def _source_summary(retained: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
        return {
            "retained_size_analysis_schema_version": retained.get("schema_version"),
            "retained_size_analysis_status": retained.get("status"),
            "retained_size_estimated": bool(retained.get("retained_size_estimated")) or bool((retained.get("side_effect_policy") or {}).get("retained_size_estimated")) if isinstance(retained.get("side_effect_policy"), dict) else bool(retained.get("retained_size_estimated")),
            "retained_path_preflight_schema_version": preflight.get("schema_version"),
            "retained_path_preflight_status": preflight.get("status"),
            "retained_path_preflight_ready": bool(preflight.get("path_to_root_preflight_ready")),
            "candidate_count": len(retained.get("candidate_estimates", [])) if isinstance(retained.get("candidate_estimates"), list) else len(preflight.get("candidate_inputs", [])) if isinstance(preflight.get("candidate_inputs"), list) else 0,
        }

    @staticmethod
    def _side_effect_policy(*, executor_invoked: bool, raw_heap_loaded: bool, raw_heap_parsed: bool, path_to_root_estimated: bool) -> dict[str, Any]:
        return {
            "read_only": False if executor_invoked else True,
            "review_only": False if executor_invoked else True,
            "explicit_review_only": True,
            "executor_invoked": executor_invoked,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": raw_heap_loaded,
            "raw_heap_parsed": raw_heap_parsed,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_estimated": path_to_root_estimated,
            "path_to_root_proven": False,
            "path_to_root_computed": path_to_root_estimated,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotConstructorGrowthDrilldownExecutorSpec:
    """Explicit-review-only MVP executor for descriptor-backed constructor growth drilldown.

    The executor consumes the ready constructor-growth drilldown review descriptor
    and computes bounded prioritization / follow-up rows from its redacted summary
    metadata. It does not load raw heap data, compute a new heap diff, prove
    retained-size / path-to-root facts, start browsers, send CDP, or call MCP.
    """

    constructor_growth_drilldown: dict[str, Any] | None = None
    selected_candidate_name: str | None = None
    mode: str = "dry-run"
    review_approved: bool = False
    approve_execution: bool = False
    reviewer: str | None = None
    max_candidates: int = 10
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    heap_diff_recompute_requested: bool = False
    retained_size_proof_requested: bool = False
    path_to_root_proof_requested: bool = False
    complete_traversal_claim_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotConstructorGrowthDrilldownExecutorSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "execute_heap_snapshot_constructor_growth_drilldown",
                "executeHeapSnapshotConstructorGrowthDrilldown",
                "execute_heap_snapshot_constructor_growth_drilldown_analysis",
                "executeHeapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_analysis",
                "heapSnapshotConstructorGrowthDrilldownAnalysis",
                "heap_snapshot_constructor_growth_drilldown_executor_result",
                "heapSnapshotConstructorGrowthDrilldownExecutorResult",
                "heap_snapshot_constructor_growth_drilldown_executor_mvp",
                "heapSnapshotConstructorGrowthDrilldownExecutorMvp",
                "constructor_growth_heap_snapshot_executor",
                "constructorGrowthHeapSnapshotExecutor",
            )
        )
        drilldown = context.get(
            "heap_snapshot_constructor_growth_drilldown",
            context.get(
                "heapSnapshotConstructorGrowthDrilldown",
                context.get(
                    "heap_snapshot_constructor_growth_drilldown_descriptor",
                    context.get("heapSnapshotConstructorGrowthDrilldownDescriptor"),
                ),
            ),
        )
        if not requested and not drilldown:
            return None
        return cls(
            constructor_growth_drilldown=drilldown if isinstance(drilldown, dict) else None,
            selected_candidate_name=str(context.get("selected_candidate_name", context.get("selectedCandidateName", context.get("candidate_name", context.get("candidateName", "")))) or "").strip() or None,
            mode=str(context.get("mode", "dry-run") or "dry-run"),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            approve_execution=bool(
                context.get(
                    "approve_heap_snapshot_constructor_growth_drilldown_execution",
                    context.get(
                        "approveHeapSnapshotConstructorGrowthDrilldownExecution",
                        context.get("approve_heap_snapshot_constructor_growth_drilldown_analysis", context.get("approveHeapSnapshotConstructorGrowthDrilldownAnalysis", False)),
                    ),
                )
            ),
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 10)) or 10)),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            heap_diff_recompute_requested=bool(context.get("heap_diff_recompute_requested", context.get("heapDiffRecomputeRequested", False))),
            retained_size_proof_requested=bool(context.get("retained_size_proof_requested", context.get("retainedSizeProofRequested", False))),
            path_to_root_proof_requested=bool(context.get("path_to_root_proof_requested", context.get("pathToRootProofRequested", False))),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotConstructorGrowthDrilldownExecutorResult:
    status: str
    descriptor: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "descriptor": self.descriptor,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class HeapSnapshotConstructorGrowthDrilldownExecutorManager:
    """Explicit-review descriptor-backed constructor growth drilldown MVP."""

    def execute(self, spec: HeapSnapshotConstructorGrowthDrilldownExecutorSpec | None) -> HeapSnapshotConstructorGrowthDrilldownExecutorResult:
        base_policy = self._side_effect_policy(executor_invoked=False, constructor_drilldown_computed=False)
        if spec is None:
            descriptor = self._blocked_descriptor(None, ["missing_heap_snapshot_constructor_growth_drilldown_executor_request"], base_policy)
            return HeapSnapshotConstructorGrowthDrilldownExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason="missing_heap_snapshot_constructor_growth_drilldown_executor_request")
        try:
            blockers, warnings, source_summary, candidates = self._pre_execution_checks(spec)
            if blockers:
                descriptor = self._blocked_descriptor(spec, blockers, base_policy, warnings=warnings, source_summary=source_summary)
                return HeapSnapshotConstructorGrowthDrilldownExecutorResult(status="blocked", descriptor=descriptor, side_effect_policy=base_policy, reason=blockers[0])
            policy = self._side_effect_policy(executor_invoked=True, constructor_drilldown_computed=True)
            descriptor = self._executed_descriptor(spec=spec, warnings=warnings, source_summary=source_summary, candidates=candidates, side_effect_policy=policy)
            return HeapSnapshotConstructorGrowthDrilldownExecutorResult(status="executed", descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            policy = self._side_effect_policy(executor_invoked=True, constructor_drilldown_computed=False)
            descriptor = self._blocked_descriptor(spec, ["heap_snapshot_constructor_growth_drilldown_executor_failed"], policy)
            descriptor["error"] = str(exc)
            return HeapSnapshotConstructorGrowthDrilldownExecutorResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_constructor_growth_drilldown_executor_failed", error=str(exc))

    def _pre_execution_checks(self, spec: HeapSnapshotConstructorGrowthDrilldownExecutorSpec) -> tuple[list[str], list[str], dict[str, Any], list[dict[str, Any]]]:
        blockers: list[str] = []
        warnings = ["heap_snapshot_constructor_growth_drilldown_executor_mvp_descriptor_backed", "heap_snapshot_constructor_growth_drilldown_no_raw_heap_loaded"]
        source = spec.constructor_growth_drilldown or {}
        if not source:
            blockers.append("heap_snapshot_constructor_growth_drilldown_descriptor_required")
        else:
            if source.get("schema_version") != "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1":
                blockers.append("heap_snapshot_constructor_growth_drilldown_schema_mismatch")
            if source.get("status") != "ready_for_review":
                blockers.append("heap_snapshot_constructor_growth_drilldown_not_ready")
            if source.get("review_only") is not True or source.get("drilldown_only") is not True or source.get("summary_only") is not True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_not_review_descriptor")
            if source.get("raw_heap_loaded") is True or source.get("raw_heap_parsed") is True or source.get("heap_diff_computed") is True or source.get("new_heap_diff_computed") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_claims_heap_work")
            if source.get("constructor_drilldown_computed") is True or source.get("retained_size_proven") is True or source.get("path_to_root_computed") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_claims_prior_execution")
            policy = source.get("side_effect_policy") if isinstance(source.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(key)) for key in ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used", "raw_heap_loaded", "raw_heap_parsed", "raw_heap_exported", "constructor_drilldown_computed")):
                blockers.append("heap_snapshot_constructor_growth_drilldown_has_forbidden_side_effects")
            contracts = source.get("future_analysis_contracts") if isinstance(source.get("future_analysis_contracts"), dict) else {}
            execution_contract = contracts.get("constructor_drilldown_execution") if isinstance(contracts.get("constructor_drilldown_execution"), dict) else {}
            if execution_contract and execution_contract.get("implemented") is not False:
                blockers.append("heap_snapshot_constructor_growth_future_executor_contract_unexpected")
        if spec.mode != "apply":
            blockers.append("heap_snapshot_constructor_growth_drilldown_executor_apply_mode_required")
        if not spec.review_approved:
            blockers.append("heap_snapshot_constructor_growth_drilldown_executor_review_approval_required")
        if not spec.approve_execution:
            blockers.append("heap_snapshot_constructor_growth_drilldown_executor_execution_approval_flag_required")
        if not spec.reviewer:
            blockers.append("heap_snapshot_constructor_growth_drilldown_executor_reviewer_required")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.heap_diff_recompute_requested:
            blockers.append("heap_diff_recompute_not_allowed_in_constructor_drilldown_mvp")
        if spec.retained_size_proof_requested:
            blockers.append("retained_size_proof_claim_not_allowed_in_mvp")
        if spec.path_to_root_proof_requested:
            blockers.append("path_to_root_proof_claim_not_allowed_in_mvp")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        candidates = self._candidate_rows(source, spec)
        if not candidates:
            blockers.append("heap_snapshot_constructor_growth_drilldown_candidates_required")
        return list(dict.fromkeys(blockers)), warnings, self._source_summary(source), candidates

    def _candidate_rows(self, source: dict[str, Any], spec: HeapSnapshotConstructorGrowthDrilldownExecutorSpec) -> list[dict[str, Any]]:
        summary = source.get("constructor_growth_summary") if isinstance(source.get("constructor_growth_summary"), dict) else {}
        rows = summary.get("candidates") if isinstance(summary.get("candidates"), list) else []
        candidates: list[dict[str, Any]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "unknown")
            if spec.selected_candidate_name and name != spec.selected_candidate_name:
                continue
            before = self._int(item.get("before"))
            after = self._int(item.get("after"))
            delta = self._int(item.get("delta"))
            ratio = (float(after) / float(before)) if before > 0 else None
            score = self._score(before=before, after=after, delta=delta)
            candidates.append({
                "name": name,
                "before": before,
                "after": after,
                "delta": delta,
                "growth_ratio": ratio,
                "growth_score": score,
                "severity": self._severity(score),
                "source": str(item.get("source") or "constructor_growth_drilldown"),
                "raw_value_exported": False,
                "descriptor_backed": True,
                "requires_retained_size_followup": True,
                "requires_path_to_root_followup": True,
                "recommended_next_actions": [
                    "review_heap_snapshot_retained_path_executor_inputs",
                    "review_heap_snapshot_retained_size_executor_mvp",
                    "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown",
                ],
            })
        candidates.sort(key=lambda item: (int(item.get("growth_score") or 0), int(item.get("delta") or 0)), reverse=True)
        return candidates[: spec.max_candidates]

    @staticmethod
    def _score(*, before: int, after: int, delta: int) -> int:
        base = max(0, delta) * 100
        if before <= 0 and after > 0:
            return base + 75
        if before > 0 and after >= before * 2:
            return base + 50
        return base

    @staticmethod
    def _severity(score: int) -> str:
        if score >= 500:
            return "high"
        if score >= 150:
            return "medium"
        return "low"

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception as e:
            _logger.debug("Failed to parse int value in _int: %s", e, exc_info=True)
            return 0

    @staticmethod
    def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
        summary = source.get("constructor_growth_summary") if isinstance(source.get("constructor_growth_summary"), dict) else {}
        preflight = source.get("source_selected_analysis_input_preflight") if isinstance(source.get("source_selected_analysis_input_preflight"), dict) else {}
        return {
            "schema_version": source.get("schema_version"),
            "status": source.get("status"),
            "drilldown_artifact": source.get("drilldown_artifact"),
            "transaction_id": preflight.get("transaction_id"),
            "selected_action": source.get("selected_action"),
            "candidate_count": summary.get("candidate_count"),
            "total_positive_delta": summary.get("total_positive_delta"),
            "top_candidate_name": (summary.get("top_candidate") or {}).get("name") if isinstance(summary.get("top_candidate"), dict) else None,
        }

    def _blocked_descriptor(
        self,
        spec: HeapSnapshotConstructorGrowthDrilldownExecutorSpec | None,
        blockers: list[str],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
        source_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "blocked",
            "executor_name": "execute_heap_snapshot_constructor_growth_drilldown",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-constructor-growth-drilldown-analysis.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": source_summary or {},
            "constructor_drilldown_rows": [],
            "constructor_drilldown_computed": False,
            "constructor_drilldown_proven": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "resolve_heap_snapshot_constructor_growth_drilldown_analysis_blockers",
            "side_effect_policy": side_effect_policy,
        }

    def _executed_descriptor(
        self,
        *,
        spec: HeapSnapshotConstructorGrowthDrilldownExecutorSpec,
        warnings: list[str],
        source_summary: dict[str, Any],
        candidates: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            "status": "executed",
            "executor_name": "execute_heap_snapshot_constructor_growth_drilldown",
            "executor_mvp": True,
            "explicit_review_only": True,
            "result_artifact": "workspace/heap-snapshot-constructor-growth-drilldown-analysis.json",
            "reviewer": spec.reviewer,
            "source_summary": source_summary,
            "selected_candidate_name": spec.selected_candidate_name,
            "constructor_drilldown_rows": candidates,
            "constructor_drilldown_summary": {
                "candidate_count": len(candidates),
                "top_candidate": candidates[0] if candidates else {},
                "total_delta": sum(int(item.get("delta") or 0) for item in candidates),
                "high_severity_count": sum(1 for item in candidates if item.get("severity") == "high"),
                "medium_severity_count": sum(1 for item in candidates if item.get("severity") == "medium"),
                "analysis_method": "descriptor_backed_constructor_growth_prioritization",
            },
            "constructor_drilldown_computed": True,
            "constructor_drilldown_proven": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "retained_size_proven": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal_claimed": False,
            "redacted_result": True,
            "summary_only": True,
            "blockers": [],
            "warnings": warnings,
            "next_action": "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _side_effect_policy(*, executor_invoked: bool, constructor_drilldown_computed: bool) -> dict[str, Any]:
        return {
            "read_only": False if executor_invoked else True,
            "review_only": False if executor_invoked else True,
            "explicit_review_only": True,
            "executor_invoked": executor_invoked,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": constructor_drilldown_computed,
            "constructor_drilldown_proven": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_estimated": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotAutomaticFollowupPlanSpec:
    """Read-only planner that joins finished heap-analysis MVP outputs.

    The planner consumes existing retained-size, path-to-root, and constructor
    growth analysis descriptors and emits a review plan for the next heap step.
    It deliberately does not read raw heap data, rerun diff logic, invoke
    retained/path/constructor executors, or claim proof-grade analysis.
    """

    retained_size_analysis: dict[str, Any] | None = None
    path_to_root_analysis: dict[str, Any] | None = None
    constructor_growth_drilldown_analysis: dict[str, Any] | None = None
    reviewer: str | None = None
    max_actions: int = 8
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    heap_diff_recompute_requested: bool = False
    retained_size_proof_requested: bool = False
    path_to_root_proof_requested: bool = False
    complete_traversal_claim_requested: bool = False
    automatic_execution_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotAutomaticFollowupPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_automatic_followup_plan",
                "heapSnapshotAutomaticFollowupPlan",
                "heap_snapshot_automatic_followup_planner",
                "heapSnapshotAutomaticFollowupPlanner",
                "heap_snapshot_followup_plan",
                "heapSnapshotFollowupPlan",
                "plan_heap_snapshot_automatic_followup",
                "planHeapSnapshotAutomaticFollowup",
                "review_heap_snapshot_automatic_followup_plan",
                "reviewHeapSnapshotAutomaticFollowupPlan",
            )
        )
        retained = context.get(
            "heap_snapshot_retained_size_analysis",
            context.get(
                "heapSnapshotRetainedSizeAnalysis",
                context.get("heap_snapshot_retained_size_analysis_result", context.get("heapSnapshotRetainedSizeAnalysisResult")),
            ),
        )
        path = context.get(
            "heap_snapshot_path_to_root_analysis",
            context.get(
                "heapSnapshotPathToRootAnalysis",
                context.get("heap_snapshot_path_to_root_analysis_result", context.get("heapSnapshotPathToRootAnalysisResult")),
            ),
        )
        constructor = context.get(
            "heap_snapshot_constructor_growth_drilldown_analysis",
            context.get(
                "heapSnapshotConstructorGrowthDrilldownAnalysis",
                context.get(
                    "heap_snapshot_constructor_growth_drilldown_analysis_result",
                    context.get("heapSnapshotConstructorGrowthDrilldownAnalysisResult"),
                ),
            ),
        )
        if not requested and not any(isinstance(item, dict) for item in (retained, path, constructor)):
            return None
        return cls(
            retained_size_analysis=retained if isinstance(retained, dict) else None,
            path_to_root_analysis=path if isinstance(path, dict) else None,
            constructor_growth_drilldown_analysis=constructor if isinstance(constructor, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_actions=max(1, int(context.get("max_actions", context.get("maxActions", 8)) or 8)),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            heap_diff_recompute_requested=bool(context.get("heap_diff_recompute_requested", context.get("heapDiffRecomputeRequested", False))),
            retained_size_proof_requested=bool(context.get("retained_size_proof_requested", context.get("retainedSizeProofRequested", False))),
            path_to_root_proof_requested=bool(context.get("path_to_root_proof_requested", context.get("pathToRootProofRequested", False))),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            automatic_execution_requested=bool(context.get("automatic_execution_requested", context.get("automaticExecutionRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotAutomaticFollowupPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotAutomaticFollowupPlanManager:
    """Read-only heap follow-up planner over existing analysis artifacts."""

    def review(self, spec: HeapSnapshotAutomaticFollowupPlanSpec | None) -> HeapSnapshotAutomaticFollowupPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            plan = self._plan_descriptor(None, ["missing_heap_snapshot_automatic_followup_plan_request"], [], policy)
            return HeapSnapshotAutomaticFollowupPlanResult(status="blocked", plan=plan, side_effect_policy=policy, reason="missing_heap_snapshot_automatic_followup_plan_request")
        blockers, warnings = self._validate_inputs(spec)
        actions = [] if blockers else self._recommended_actions(spec)
        plan = self._plan_descriptor(spec, blockers, actions, policy, warnings=warnings)
        status = "blocked" if blockers else "ready_for_review"
        return HeapSnapshotAutomaticFollowupPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_inputs(self, spec: HeapSnapshotAutomaticFollowupPlanSpec) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings = [
            "heap_snapshot_automatic_followup_plan_review_only",
            "heap_snapshot_automatic_followup_no_executor_invocation",
            "heap_snapshot_automatic_followup_no_raw_heap_ingestion",
        ]
        sources = {
            "retained_size_analysis": spec.retained_size_analysis,
            "path_to_root_analysis": spec.path_to_root_analysis,
            "constructor_growth_drilldown_analysis": spec.constructor_growth_drilldown_analysis,
        }
        if not any(isinstance(value, dict) for value in sources.values()):
            blockers.append("heap_snapshot_analysis_result_required")
        for key, descriptor in sources.items():
            if not isinstance(descriptor, dict):
                continue
            expected = {
                "retained_size_analysis": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
                "path_to_root_analysis": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
                "constructor_growth_drilldown_analysis": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
            }[key]
            if descriptor.get("schema_version") != expected:
                blockers.append(f"heap_snapshot_{key}_schema_mismatch")
            if descriptor.get("status") != "executed":
                blockers.append(f"heap_snapshot_{key}_not_executed")
            if descriptor.get("raw_heap_exported") is True or descriptor.get("raw_strings_exported") is True:
                blockers.append(f"heap_snapshot_{key}_exported_raw_data")
            if descriptor.get("complete_heap_traversal_claimed") is True:
                blockers.append(f"heap_snapshot_{key}_claims_complete_traversal")
            if descriptor.get("retained_size_proven") is True or descriptor.get("path_to_root_proven") is True or descriptor.get("constructor_drilldown_proven") is True:
                blockers.append(f"heap_snapshot_{key}_claims_proof_grade_analysis")
            policy = descriptor.get("side_effect_policy") if isinstance(descriptor.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(item)) for item in ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used")):
                blockers.append(f"heap_snapshot_{key}_has_forbidden_side_effects")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.heap_diff_recompute_requested:
            blockers.append("heap_diff_recompute_not_allowed_in_followup_planner")
        if spec.retained_size_proof_requested:
            blockers.append("retained_size_proof_claim_not_allowed_in_planner")
        if spec.path_to_root_proof_requested:
            blockers.append("path_to_root_proof_claim_not_allowed_in_planner")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.automatic_execution_requested:
            blockers.append("automatic_heap_followup_execution_not_allowed")
        return list(dict.fromkeys(blockers)), warnings

    def _recommended_actions(self, spec: HeapSnapshotAutomaticFollowupPlanSpec) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        retained = spec.retained_size_analysis or {}
        path = spec.path_to_root_analysis or {}
        constructor = spec.constructor_growth_drilldown_analysis or {}
        retained_candidates = retained.get("candidate_estimates") if isinstance(retained.get("candidate_estimates"), list) else []
        path_candidates = self._rows(path, "path_estimates", "candidate_paths")
        constructor_rows = constructor.get("constructor_drilldown_rows") if isinstance(constructor.get("constructor_drilldown_rows"), list) else []
        if constructor_rows and not retained_candidates:
            actions.append(self._action("review_retained_size_estimate_for_top_constructor_growth", 90, "high", "constructor_growth_without_retained_size_estimate", "execute_heap_snapshot_retained_size_analysis"))
        if retained_candidates and not path_candidates:
            actions.append(self._action("review_path_to_root_estimate_for_retained_candidates", 85, "high", "retained_size_without_path_to_root_estimate", "execute_heap_snapshot_path_to_root_analysis"))
        if constructor_rows and retained_candidates and path_candidates:
            actions.append(self._action("review_combined_heap_candidate_evidence", 80, "medium", "all_three_estimate_surfaces_available", "manual_review_combined_heap_evidence"))
        if retained_candidates:
            actions.append(self._action("plan_proof_grade_retained_size_analysis", 60, "medium", "retained_size_estimate_available_without_proof", "plan_heap_snapshot_retained_size_proof"))
        if path_candidates:
            actions.append(self._action("plan_proof_grade_path_to_root_analysis", 55, "medium", "path_to_root_estimate_available_without_proof", "plan_heap_snapshot_path_to_root_proof"))
        if constructor_rows:
            actions.append(self._action("plan_raw_heap_constructor_drilldown_proof", 50, "medium", "constructor_growth_prioritization_available_without_raw_heap_proof", "plan_raw_heap_constructor_drilldown_proof"))
        actions.append(self._action("plan_larger_budget_second_pass", 35, "low", "bounded_mvp_outputs_available", "plan_heap_snapshot_larger_budget_second_pass"))
        actions.append(self._action("keep_manual_review_gate_before_any_heap_executor", 30, "low", "automatic_followup_execution_disabled", "manual_review_gate"))
        actions.sort(key=lambda item: int(item.get("priority_score") or 0), reverse=True)
        return actions[: spec.max_actions]

    @staticmethod
    def _action(action: str, score: int, severity: str, reason: str, next_step: str) -> dict[str, Any]:
        return {
            "action": action,
            "priority_score": score,
            "severity": severity,
            "reason": reason,
            "next_step": next_step,
            "automatic_execution_allowed": False,
            "requires_explicit_review": True,
        }

    def _plan_descriptor(
        self,
        spec: HeapSnapshotAutomaticFollowupPlanSpec | None,
        blockers: list[str],
        actions: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        status = "blocked" if blockers else "ready_for_review"
        source_summary = self._source_summary(spec)
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "planner_name": "review_heap_snapshot_automatic_followup_plan",
            "plan_artifact": "workspace/heap-snapshot-automatic-followup-plan.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": source_summary,
            "recommended_actions": actions,
            "recommended_action_count": len(actions),
            "top_recommended_action": actions[0] if actions else {},
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "retained_size_estimated_now": False,
            "retained_size_proven": False,
            "path_to_root_estimated_now": False,
            "path_to_root_proven": False,
            "constructor_drilldown_computed_now": False,
            "constructor_drilldown_proven": False,
            "complete_heap_traversal_claimed": False,
            "automatic_followup_analysis": False,
            "automatic_execution_allowed": False,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass" if not blockers else "resolve_heap_snapshot_automatic_followup_plan_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _source_summary(spec: HeapSnapshotAutomaticFollowupPlanSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        return {
            "retained_size_analysis": HeapSnapshotAutomaticFollowupPlanManager._descriptor_summary(spec.retained_size_analysis, "candidate_estimates"),
            "path_to_root_analysis": HeapSnapshotAutomaticFollowupPlanManager._descriptor_summary(spec.path_to_root_analysis, "path_estimates", "candidate_paths"),
            "constructor_growth_drilldown_analysis": HeapSnapshotAutomaticFollowupPlanManager._descriptor_summary(spec.constructor_growth_drilldown_analysis, "constructor_drilldown_rows"),
        }

    @staticmethod
    def _descriptor_summary(descriptor: dict[str, Any] | None, *row_keys: str) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        rows = HeapSnapshotAutomaticFollowupPlanManager._rows(descriptor, *row_keys)
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "result_artifact": descriptor.get("result_artifact"),
            "row_count": len(rows),
            "raw_heap_exported": bool(descriptor.get("raw_heap_exported", False)),
            "raw_strings_exported": bool(descriptor.get("raw_strings_exported", False)),
            "retained_size_proven": bool(descriptor.get("retained_size_proven", False)),
            "path_to_root_proven": bool(descriptor.get("path_to_root_proven", False)),
            "constructor_drilldown_proven": bool(descriptor.get("constructor_drilldown_proven", False)),
            "complete_heap_traversal_claimed": bool(descriptor.get("complete_heap_traversal_claimed", False)),
        }

    @staticmethod
    def _rows(descriptor: dict[str, Any], *row_keys: str) -> list[Any]:
        for row_key in row_keys:
            rows = descriptor.get(row_key)
            if isinstance(rows, list):
                return rows
        return []

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": False,
            "constructor_drilldown_proven": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_estimated": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal": False,
            "automatic_followup_analysis": False,
            "automatic_execution_allowed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRetainedSizeProofPlanSpec:
    """Read-only retained-size proof planning over an existing estimate.

    This descriptor packages requirements for a future proof-grade retained-size
    executor without loading raw heap data, building a dominator tree, or proving
    retained size in the current step.
    """

    retained_size_analysis: dict[str, Any] | None = None
    automatic_followup_plan: dict[str, Any] | None = None
    reviewer: str | None = None
    max_candidates: int = 8
    raw_heap_ingestion_requested: bool = False
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    heap_diff_recompute_requested: bool = False
    retained_size_proof_execution_requested: bool = False
    complete_traversal_claim_requested: bool = False
    automatic_execution_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRetainedSizeProofPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_retained_size_proof_plan",
                "heapSnapshotRetainedSizeProofPlan",
                "heap_snapshot_retained_size_proof_planner",
                "heapSnapshotRetainedSizeProofPlanner",
                "plan_heap_snapshot_retained_size_proof",
                "planHeapSnapshotRetainedSizeProof",
                "review_heap_snapshot_retained_size_proof_plan",
                "reviewHeapSnapshotRetainedSizeProofPlan",
            )
        )
        retained = context.get(
            "heap_snapshot_retained_size_analysis",
            context.get(
                "heapSnapshotRetainedSizeAnalysis",
                context.get("heap_snapshot_retained_size_analysis_result", context.get("heapSnapshotRetainedSizeAnalysisResult")),
            ),
        )
        followup = context.get(
            "heap_snapshot_automatic_followup_plan",
            context.get(
                "heapSnapshotAutomaticFollowupPlan",
                context.get("heap_snapshot_automatic_followup_planner", context.get("heapSnapshotAutomaticFollowupPlanner")),
            ),
        )
        if not requested and not isinstance(retained, dict) and not isinstance(followup, dict):
            return None
        return cls(
            retained_size_analysis=retained if isinstance(retained, dict) else None,
            automatic_followup_plan=followup if isinstance(followup, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 8)) or 8)),
            raw_heap_ingestion_requested=bool(context.get("raw_heap_ingestion_requested", context.get("rawHeapIngestionRequested", False))),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            heap_diff_recompute_requested=bool(context.get("heap_diff_recompute_requested", context.get("heapDiffRecomputeRequested", False))),
            retained_size_proof_execution_requested=bool(
                context.get(
                    "retained_size_proof_execution_requested",
                    context.get("retainedSizeProofExecutionRequested", context.get("proof_executor_requested", context.get("proofExecutorRequested", False))),
                )
            ),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            automatic_execution_requested=bool(context.get("automatic_execution_requested", context.get("automaticExecutionRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotRetainedSizeProofPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRetainedSizeProofPlanManager:
    """Review-only retained-size proof planner after bounded estimate outputs."""

    def review(self, spec: HeapSnapshotRetainedSizeProofPlanSpec | None) -> HeapSnapshotRetainedSizeProofPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            plan = self._plan_descriptor(None, ["missing_heap_snapshot_retained_size_proof_plan_request"], [], policy)
            return HeapSnapshotRetainedSizeProofPlanResult(status="blocked", plan=plan, side_effect_policy=policy, reason="missing_heap_snapshot_retained_size_proof_plan_request")
        blockers, warnings = self._validate_inputs(spec)
        candidates = [] if blockers else self._candidate_inputs(spec)
        plan = self._plan_descriptor(spec, blockers, candidates, policy, warnings=warnings)
        status = "blocked" if blockers else "ready_for_review"
        return HeapSnapshotRetainedSizeProofPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_inputs(self, spec: HeapSnapshotRetainedSizeProofPlanSpec) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings = [
            "heap_snapshot_retained_size_proof_plan_review_only",
            "heap_snapshot_retained_size_proof_executor_not_invoked",
            "raw_heap_ingestion_deferred_to_future_review",
        ]
        retained = spec.retained_size_analysis
        if not isinstance(retained, dict):
            blockers.append("heap_snapshot_retained_size_analysis_required")
        else:
            if retained.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-analysis.v1":
                blockers.append("heap_snapshot_retained_size_analysis_schema_mismatch")
            if retained.get("status") != "executed":
                blockers.append("heap_snapshot_retained_size_analysis_not_executed")
            candidates = retained.get("candidate_estimates") if isinstance(retained.get("candidate_estimates"), list) else []
            if not candidates:
                blockers.append("heap_snapshot_retained_size_candidate_estimates_required")
            if retained.get("raw_heap_exported") is True or retained.get("raw_strings_exported") is True:
                blockers.append("heap_snapshot_retained_size_analysis_exported_raw_data")
            if retained.get("retained_size_proven") is True:
                blockers.append("heap_snapshot_retained_size_analysis_already_claims_proof")
            if retained.get("complete_heap_traversal_claimed") is True:
                blockers.append("heap_snapshot_retained_size_analysis_claims_complete_traversal")
            policy = retained.get("side_effect_policy") if isinstance(retained.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(item)) for item in ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used")):
                blockers.append("heap_snapshot_retained_size_analysis_has_forbidden_side_effects")
        followup = spec.automatic_followup_plan
        if isinstance(followup, dict):
            if followup.get("schema_version") != "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1":
                blockers.append("heap_snapshot_automatic_followup_plan_schema_mismatch")
            if followup.get("status") != "ready_for_review":
                blockers.append("heap_snapshot_automatic_followup_plan_not_ready")
            if followup.get("automatic_execution_allowed") is True:
                blockers.append("heap_snapshot_automatic_followup_plan_allows_automatic_execution")
            policy = followup.get("side_effect_policy") if isinstance(followup.get("side_effect_policy"), dict) else {}
            forbidden = (
                "browser_started",
                "cdp_command_sent",
                "calls_mcp",
                "mobile_runtime_used",
                "raw_heap_loaded",
                "raw_heap_parsed",
                "heap_diff_computed",
                "retained_size_proven",
                "path_to_root_proven",
                "automatic_execution_allowed",
            )
            if any(bool(policy.get(item)) for item in forbidden):
                blockers.append("heap_snapshot_automatic_followup_plan_has_forbidden_side_effects")
        if spec.raw_heap_ingestion_requested:
            blockers.append("raw_heap_ingestion_not_allowed_in_proof_plan")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.heap_diff_recompute_requested:
            blockers.append("heap_diff_recompute_not_allowed_in_retained_size_proof_plan")
        if spec.retained_size_proof_execution_requested:
            blockers.append("retained_size_proof_execution_not_allowed_in_plan")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.automatic_execution_requested:
            blockers.append("automatic_heap_followup_execution_not_allowed")
        return list(dict.fromkeys(blockers)), warnings

    def _candidate_inputs(self, spec: HeapSnapshotRetainedSizeProofPlanSpec) -> list[dict[str, Any]]:
        retained = spec.retained_size_analysis or {}
        candidates = retained.get("candidate_estimates") if isinstance(retained.get("candidate_estimates"), list) else []
        rows: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates[: spec.max_candidates]):
            if not isinstance(candidate, dict):
                continue
            rows.append(
                {
                    "index": index,
                    "name": candidate.get("name") or candidate.get("constructor") or candidate.get("candidate"),
                    "retained_size_estimate": candidate.get("retained_size_estimate", candidate.get("estimated_retained_size")),
                    "self_size": candidate.get("self_size"),
                    "node_count": candidate.get("node_count"),
                    "source": "heap_snapshot_retained_size_analysis",
                    "requires_raw_heap_for_proof": True,
                    "proof_available_now": False,
                }
            )
        return rows

    def _plan_descriptor(
        self,
        spec: HeapSnapshotRetainedSizeProofPlanSpec | None,
        blockers: list[str],
        candidates: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        status = "blocked" if blockers else "ready_for_review"
        source_summary = self._source_summary(spec)
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "proof_plan_only": True,
            "planner_name": "review_heap_snapshot_retained_size_proof_plan",
            "plan_artifact": "workspace/heap-snapshot-retained-size-proof-plan.json",
            "planned_result_artifact": "workspace/heap-snapshot-retained-size-proof.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": source_summary,
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "top_candidate": candidates[0] if candidates else {},
            "proof_requirements": {
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_parser_sandbox": True,
                "requires_redaction_policy": True,
                "requires_size_budget": True,
                "requires_dominator_tree": True,
                "requires_ownership_graph": True,
                "requires_explicit_review": True,
                "raw_heap_available_in_this_plan": False,
                "proof_computed_in_this_plan": False,
            },
            "future_executor_contract": {
                "executor_name": "execute_heap_snapshot_retained_size_proof",
                "implemented": False,
                "ready_to_execute_now": False,
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_dominator_tree": True,
                "requires_explicit_review": True,
                "result_artifact": "workspace/heap-snapshot-retained-size-proof.json",
            },
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "retained_size_estimated_now": False,
            "retained_size_proven": False,
            "path_to_root_proven": False,
            "complete_heap_traversal_claimed": False,
            "proof_executor_invoked": False,
            "automatic_execution_allowed": False,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor" if not blockers else "resolve_heap_snapshot_retained_size_proof_plan_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _source_summary(spec: HeapSnapshotRetainedSizeProofPlanSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        return {
            "retained_size_analysis": HeapSnapshotRetainedSizeProofPlanManager._retained_summary(spec.retained_size_analysis),
            "automatic_followup_plan": HeapSnapshotRetainedSizeProofPlanManager._followup_summary(spec.automatic_followup_plan),
        }

    @staticmethod
    def _retained_summary(descriptor: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        candidates = descriptor.get("candidate_estimates") if isinstance(descriptor.get("candidate_estimates"), list) else []
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "result_artifact": descriptor.get("result_artifact"),
            "candidate_count": len(candidates),
            "raw_heap_exported": bool(descriptor.get("raw_heap_exported", False)),
            "raw_strings_exported": bool(descriptor.get("raw_strings_exported", False)),
            "retained_size_estimated": bool(descriptor.get("retained_size_estimated", False)),
            "retained_size_proven": bool(descriptor.get("retained_size_proven", False)),
            "complete_heap_traversal_claimed": bool(descriptor.get("complete_heap_traversal_claimed", False)),
        }

    @staticmethod
    def _followup_summary(descriptor: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        actions = descriptor.get("recommended_actions") if isinstance(descriptor.get("recommended_actions"), list) else []
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "recommended_action_count": len(actions),
            "top_recommended_action": (descriptor.get("top_recommended_action") or {}).get("action") if isinstance(descriptor.get("top_recommended_action"), dict) else None,
            "automatic_execution_allowed": bool(descriptor.get("automatic_execution_allowed", False)),
        }

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "proof_plan_only": True,
            "executor_invoked": False,
            "proof_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": False,
            "constructor_drilldown_proven": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_estimated": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal": False,
            "complete_heap_traversal_claimed": False,
            "automatic_followup_analysis": False,
            "automatic_execution_allowed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec:
    """Read-only raw-heap constructor drilldown proof planning.

    This descriptor packages requirements for a future proof-grade raw-heap
    constructor drilldown executor without loading heap files, parsing raw heap
    nodes, walking retainers, or proving constructor reachability now.
    """

    constructor_growth_drilldown_analysis: dict[str, Any] | None = None
    automatic_followup_plan: dict[str, Any] | None = None
    retained_size_proof_plan: dict[str, Any] | None = None
    path_to_root_proof_plan: dict[str, Any] | None = None
    reviewer: str | None = None
    max_candidates: int = 8
    raw_heap_ingestion_requested: bool = False
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    heap_diff_recompute_requested: bool = False
    constructor_drilldown_proof_execution_requested: bool = False
    complete_traversal_claim_requested: bool = False
    retained_size_proof_claim_requested: bool = False
    path_to_root_proof_claim_requested: bool = False
    automatic_execution_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "heapSnapshotRawHeapConstructorDrilldownProofPlan",
                "heap_snapshot_raw_heap_constructor_drilldown_proof_planner",
                "heapSnapshotRawHeapConstructorDrilldownProofPlanner",
                "plan_heap_snapshot_raw_heap_constructor_drilldown_proof",
                "planHeapSnapshotRawHeapConstructorDrilldownProof",
                "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
                "reviewHeapSnapshotRawHeapConstructorDrilldownProofPlan",
            )
        )
        analysis = context.get(
            "heap_snapshot_constructor_growth_drilldown_analysis",
            context.get(
                "heapSnapshotConstructorGrowthDrilldownAnalysis",
                context.get(
                    "heap_snapshot_constructor_growth_drilldown_executor_result",
                    context.get("heapSnapshotConstructorGrowthDrilldownExecutorResult"),
                ),
            ),
        )
        followup = context.get(
            "heap_snapshot_automatic_followup_plan",
            context.get(
                "heapSnapshotAutomaticFollowupPlan",
                context.get("heap_snapshot_automatic_followup_planner", context.get("heapSnapshotAutomaticFollowupPlanner")),
            ),
        )
        retained_proof = context.get(
            "heap_snapshot_retained_size_proof_plan",
            context.get(
                "heapSnapshotRetainedSizeProofPlan",
                context.get("heap_snapshot_retained_size_proof_planner", context.get("heapSnapshotRetainedSizeProofPlanner")),
            ),
        )
        path_proof = context.get(
            "heap_snapshot_path_to_root_proof_plan",
            context.get(
                "heapSnapshotPathToRootProofPlan",
                context.get("heap_snapshot_path_to_root_proof_planner", context.get("heapSnapshotPathToRootProofPlanner")),
            ),
        )
        if not requested and not isinstance(analysis, dict) and not isinstance(followup, dict):
            return None
        return cls(
            constructor_growth_drilldown_analysis=analysis if isinstance(analysis, dict) else None,
            automatic_followup_plan=followup if isinstance(followup, dict) else None,
            retained_size_proof_plan=retained_proof if isinstance(retained_proof, dict) else None,
            path_to_root_proof_plan=path_proof if isinstance(path_proof, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 8)) or 8)),
            raw_heap_ingestion_requested=bool(context.get("raw_heap_ingestion_requested", context.get("rawHeapIngestionRequested", False))),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            heap_diff_recompute_requested=bool(context.get("heap_diff_recompute_requested", context.get("heapDiffRecomputeRequested", False))),
            constructor_drilldown_proof_execution_requested=bool(
                context.get(
                    "constructor_drilldown_proof_execution_requested",
                    context.get(
                        "constructorDrilldownProofExecutionRequested",
                        context.get("proof_executor_requested", context.get("proofExecutorRequested", False)),
                    ),
                )
            ),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            retained_size_proof_claim_requested=bool(context.get("retained_size_proof_claim_requested", context.get("retainedSizeProofClaimRequested", False))),
            path_to_root_proof_claim_requested=bool(context.get("path_to_root_proof_claim_requested", context.get("pathToRootProofClaimRequested", False))),
            automatic_execution_requested=bool(context.get("automatic_execution_requested", context.get("automaticExecutionRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotRawHeapConstructorDrilldownProofPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotRawHeapConstructorDrilldownProofPlanManager:
    """Review-only raw-heap constructor drilldown proof planner."""

    def review(self, spec: HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec | None) -> HeapSnapshotRawHeapConstructorDrilldownProofPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            plan = self._plan_descriptor(None, ["missing_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request"], [], policy)
            return HeapSnapshotRawHeapConstructorDrilldownProofPlanResult(status="blocked", plan=plan, side_effect_policy=policy, reason="missing_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_request")
        blockers, warnings = self._validate_inputs(spec)
        candidates = [] if blockers else self._candidate_inputs(spec)
        plan = self._plan_descriptor(spec, blockers, candidates, policy, warnings=warnings)
        status = "blocked" if blockers else "ready_for_review"
        return HeapSnapshotRawHeapConstructorDrilldownProofPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_inputs(self, spec: HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings = [
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan_review_only",
            "heap_snapshot_raw_heap_constructor_drilldown_proof_executor_not_invoked",
            "raw_heap_ingestion_deferred_to_future_review",
        ]
        analysis = spec.constructor_growth_drilldown_analysis
        if not isinstance(analysis, dict):
            blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_required")
        else:
            if analysis.get("schema_version") != "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1":
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_schema_mismatch")
            if analysis.get("status") != "executed":
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_not_executed")
            rows = self._constructor_rows(analysis)
            if not rows:
                blockers.append("heap_snapshot_constructor_growth_drilldown_rows_required")
            if analysis.get("raw_heap_loaded") is True or analysis.get("raw_heap_parsed") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_loaded_raw_heap")
            if analysis.get("raw_heap_exported") is True or analysis.get("raw_strings_exported") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_exported_raw_data")
            if analysis.get("constructor_drilldown_proven") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_already_claims_proof")
            if analysis.get("retained_size_proven") is True or analysis.get("path_to_root_computed") is True or analysis.get("path_to_root_proven") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_claims_related_proof")
            if analysis.get("complete_heap_traversal_claimed") is True:
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_claims_complete_traversal")
            policy = analysis.get("side_effect_policy") if isinstance(analysis.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(item)) for item in ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used")):
                blockers.append("heap_snapshot_constructor_growth_drilldown_analysis_has_forbidden_side_effects")
        followup = spec.automatic_followup_plan
        if isinstance(followup, dict):
            if followup.get("schema_version") != "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1":
                blockers.append("heap_snapshot_automatic_followup_plan_schema_mismatch")
            if followup.get("status") != "ready_for_review":
                blockers.append("heap_snapshot_automatic_followup_plan_not_ready")
            if followup.get("automatic_execution_allowed") is True:
                blockers.append("heap_snapshot_automatic_followup_plan_allows_automatic_execution")
            policy = followup.get("side_effect_policy") if isinstance(followup.get("side_effect_policy"), dict) else {}
            forbidden = ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used", "raw_heap_loaded", "raw_heap_parsed", "heap_diff_computed", "automatic_execution_allowed")
            if any(bool(policy.get(item)) for item in forbidden):
                blockers.append("heap_snapshot_automatic_followup_plan_has_forbidden_side_effects")
        self._validate_optional_proof_plan(spec.retained_size_proof_plan, "retained_size", blockers)
        self._validate_optional_proof_plan(spec.path_to_root_proof_plan, "path_to_root", blockers)
        if spec.raw_heap_ingestion_requested:
            blockers.append("raw_heap_ingestion_not_allowed_in_raw_heap_constructor_drilldown_proof_plan")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.heap_diff_recompute_requested:
            blockers.append("heap_diff_recompute_not_allowed_in_raw_heap_constructor_drilldown_proof_plan")
        if spec.constructor_drilldown_proof_execution_requested:
            blockers.append("constructor_drilldown_proof_execution_not_allowed_in_plan")
        if spec.retained_size_proof_claim_requested:
            blockers.append("retained_size_proof_claim_not_allowed")
        if spec.path_to_root_proof_claim_requested:
            blockers.append("path_to_root_proof_claim_not_allowed")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.automatic_execution_requested:
            blockers.append("automatic_heap_followup_execution_not_allowed")
        return list(dict.fromkeys(blockers)), warnings

    @staticmethod
    def _validate_optional_proof_plan(plan: dict[str, Any] | None, kind: str, blockers: list[str]) -> None:
        if not isinstance(plan, dict):
            return
        expected_schema = f"reverse-deepagent.heap-snapshot-{'retained-size' if kind == 'retained_size' else 'path-to-root'}-proof-plan.v1"
        prefix = f"heap_snapshot_{kind}_proof_plan"
        if plan.get("schema_version") != expected_schema:
            blockers.append(f"{prefix}_schema_mismatch")
        if plan.get("status") != "ready_for_review":
            blockers.append(f"{prefix}_not_ready")
        future = plan.get("future_executor_contract") if isinstance(plan.get("future_executor_contract"), dict) else {}
        if future.get("implemented") is True or future.get("ready_to_execute_now") is True:
            blockers.append(f"{prefix}_future_executor_enabled")
        if plan.get("automatic_execution_allowed") is True:
            blockers.append(f"{prefix}_allows_automatic_execution")
        if plan.get("raw_heap_loaded") is True or plan.get("raw_heap_parsed") is True or plan.get("raw_heap_exported") is True:
            blockers.append(f"{prefix}_has_raw_heap_side_effects")
        if plan.get("complete_heap_traversal_claimed") is True:
            blockers.append(f"{prefix}_claims_complete_traversal")

    def _candidate_inputs(self, spec: HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec) -> list[dict[str, Any]]:
        analysis = spec.constructor_growth_drilldown_analysis or {}
        rows = self._constructor_rows(analysis)
        candidates: list[dict[str, Any]] = []
        for index, row in enumerate(rows[: spec.max_candidates]):
            if not isinstance(row, dict):
                continue
            candidates.append(
                {
                    "index": index,
                    "constructor_name": row.get("constructor_name") or row.get("constructor") or row.get("name") or row.get("candidate"),
                    "growth_score": row.get("growth_score"),
                    "severity": row.get("severity"),
                    "node_count_delta": row.get("node_count_delta", row.get("count_delta")),
                    "retained_size_followup_recommended": bool(row.get("retained_size_followup_recommended", row.get("requires_retained_size_review", False))),
                    "path_to_root_followup_recommended": bool(row.get("path_to_root_followup_recommended", row.get("requires_path_to_root_review", False))),
                    "source": "heap_snapshot_constructor_growth_drilldown_analysis",
                    "requires_raw_heap_for_proof": True,
                    "proof_available_now": False,
                }
            )
        return candidates

    def _plan_descriptor(
        self,
        spec: HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec | None,
        blockers: list[str],
        candidates: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-raw-heap-constructor-drilldown-proof-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "proof_plan_only": True,
            "planner_name": "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan",
            "plan_artifact": "workspace/heap-snapshot-raw-heap-constructor-drilldown-proof-plan.json",
            "planned_result_artifact": "workspace/heap-snapshot-raw-heap-constructor-drilldown-proof.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": self._source_summary(spec),
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "top_candidate": candidates[0] if candidates else {},
            "proof_requirements": {
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_parser_sandbox": True,
                "requires_redaction_policy": True,
                "requires_size_budget": True,
                "requires_constructor_reachability_graph": True,
                "requires_retainer_edge_index": True,
                "requires_constructor_instance_grouping": True,
                "requires_dominator_or_retainer_context": True,
                "requires_explicit_review": True,
                "raw_heap_available_in_this_plan": False,
                "proof_computed_in_this_plan": False,
            },
            "future_executor_contract": {
                "executor_name": "execute_heap_snapshot_raw_heap_constructor_drilldown_proof",
                "implemented": False,
                "ready_to_execute_now": False,
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_constructor_reachability_graph": True,
                "requires_retainer_edge_index": True,
                "requires_explicit_review": True,
                "result_artifact": "workspace/heap-snapshot-raw-heap-constructor-drilldown-proof.json",
            },
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "constructor_drilldown_computed_now": False,
            "constructor_drilldown_proven": False,
            "retained_size_proven": False,
            "path_to_root_proven": False,
            "complete_heap_traversal_claimed": False,
            "proof_executor_invoked": False,
            "automatic_execution_allowed": False,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor" if not blockers else "resolve_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _source_summary(spec: HeapSnapshotRawHeapConstructorDrilldownProofPlanSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        return {
            "constructor_growth_drilldown_analysis": HeapSnapshotRawHeapConstructorDrilldownProofPlanManager._analysis_summary(spec.constructor_growth_drilldown_analysis),
            "automatic_followup_plan": HeapSnapshotRetainedSizeProofPlanManager._followup_summary(spec.automatic_followup_plan),
            "retained_size_proof_plan": HeapSnapshotPathToRootProofPlanManager._proof_plan_summary(spec.retained_size_proof_plan),
            "path_to_root_proof_plan": HeapSnapshotPathToRootProofPlanManager._proof_plan_summary(spec.path_to_root_proof_plan),
        }

    @staticmethod
    def _analysis_summary(descriptor: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        rows = HeapSnapshotRawHeapConstructorDrilldownProofPlanManager._constructor_rows(descriptor)
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "result_artifact": descriptor.get("result_artifact"),
            "candidate_count": len(rows),
            "raw_heap_loaded": bool(descriptor.get("raw_heap_loaded", False)),
            "raw_heap_parsed": bool(descriptor.get("raw_heap_parsed", False)),
            "raw_heap_exported": bool(descriptor.get("raw_heap_exported", False)),
            "raw_strings_exported": bool(descriptor.get("raw_strings_exported", False)),
            "constructor_drilldown_computed": bool(descriptor.get("constructor_drilldown_computed", False)),
            "constructor_drilldown_proven": bool(descriptor.get("constructor_drilldown_proven", False)),
            "complete_heap_traversal_claimed": bool(descriptor.get("complete_heap_traversal_claimed", False)),
        }

    @staticmethod
    def _constructor_rows(descriptor: dict[str, Any]) -> list[Any]:
        for key in ("constructor_drilldown_rows", "constructor_growth_rows", "candidate_constructors", "prioritized_constructors"):
            rows = descriptor.get(key)
            if isinstance(rows, list):
                return rows
        return []

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "proof_plan_only": True,
            "executor_invoked": False,
            "proof_executor_invoked": False,
            "default_recon": False,
            "files_mutated": False,
            "artifacts_written": False,
            "browser_started": False,
            "provider_factory_invoked": False,
            "provider_availability_checked": False,
            "cdp_command_sent": False,
            "heap_profiler_enabled": False,
            "heap_snapshot_collected": False,
            "heap_snapshot_diff_computed": False,
            "heap_diff_computed": False,
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "constructor_drilldown_computed": False,
            "constructor_drilldown_proven": False,
            "retained_size_estimated": False,
            "retained_size_proven": False,
            "path_to_root_estimated": False,
            "path_to_root_proven": False,
            "path_to_root_computed": False,
            "complete_heap_traversal": False,
            "complete_heap_traversal_claimed": False,
            "automatic_followup_analysis": False,
            "automatic_execution_allowed": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotPathToRootProofPlanSpec:
    """Read-only path-to-root proof planning over an existing path estimate."""

    path_to_root_analysis: dict[str, Any] | None = None
    retained_size_analysis: dict[str, Any] | None = None
    automatic_followup_plan: dict[str, Any] | None = None
    retained_size_proof_plan: dict[str, Any] | None = None
    reviewer: str | None = None
    max_candidates: int = 8
    raw_heap_ingestion_requested: bool = False
    raw_heap_export_requested: bool = False
    raw_strings_export_requested: bool = False
    heap_diff_recompute_requested: bool = False
    path_to_root_proof_execution_requested: bool = False
    complete_traversal_claim_requested: bool = False
    automatic_execution_requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotPathToRootProofPlanSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_path_to_root_proof_plan",
                "heapSnapshotPathToRootProofPlan",
                "heap_snapshot_path_to_root_proof_planner",
                "heapSnapshotPathToRootProofPlanner",
                "plan_heap_snapshot_path_to_root_proof",
                "planHeapSnapshotPathToRootProof",
                "review_heap_snapshot_path_to_root_proof_plan",
                "reviewHeapSnapshotPathToRootProofPlan",
            )
        )
        path = context.get(
            "heap_snapshot_path_to_root_analysis",
            context.get(
                "heapSnapshotPathToRootAnalysis",
                context.get("heap_snapshot_path_to_root_analysis_result", context.get("heapSnapshotPathToRootAnalysisResult")),
            ),
        )
        retained = context.get(
            "heap_snapshot_retained_size_analysis",
            context.get(
                "heapSnapshotRetainedSizeAnalysis",
                context.get("heap_snapshot_retained_size_analysis_result", context.get("heapSnapshotRetainedSizeAnalysisResult")),
            ),
        )
        followup = context.get(
            "heap_snapshot_automatic_followup_plan",
            context.get(
                "heapSnapshotAutomaticFollowupPlan",
                context.get("heap_snapshot_automatic_followup_planner", context.get("heapSnapshotAutomaticFollowupPlanner")),
            ),
        )
        retained_proof = context.get(
            "heap_snapshot_retained_size_proof_plan",
            context.get(
                "heapSnapshotRetainedSizeProofPlan",
                context.get("heap_snapshot_retained_size_proof_planner", context.get("heapSnapshotRetainedSizeProofPlanner")),
            ),
        )
        if not requested and not isinstance(path, dict) and not isinstance(followup, dict):
            return None
        return cls(
            path_to_root_analysis=path if isinstance(path, dict) else None,
            retained_size_analysis=retained if isinstance(retained, dict) else None,
            automatic_followup_plan=followup if isinstance(followup, dict) else None,
            retained_size_proof_plan=retained_proof if isinstance(retained_proof, dict) else None,
            reviewer=str(context.get("reviewer") or "").strip() or None,
            max_candidates=max(1, int(context.get("max_candidates", context.get("maxCandidates", 8)) or 8)),
            raw_heap_ingestion_requested=bool(context.get("raw_heap_ingestion_requested", context.get("rawHeapIngestionRequested", False))),
            raw_heap_export_requested=bool(context.get("raw_heap_export_requested", context.get("rawHeapExportRequested", False))),
            raw_strings_export_requested=bool(context.get("raw_strings_export_requested", context.get("rawStringsExportRequested", False))),
            heap_diff_recompute_requested=bool(context.get("heap_diff_recompute_requested", context.get("heapDiffRecomputeRequested", False))),
            path_to_root_proof_execution_requested=bool(
                context.get(
                    "path_to_root_proof_execution_requested",
                    context.get("pathToRootProofExecutionRequested", context.get("proof_executor_requested", context.get("proofExecutorRequested", False))),
                )
            ),
            complete_traversal_claim_requested=bool(context.get("complete_traversal_claim_requested", context.get("completeTraversalClaimRequested", False))),
            automatic_execution_requested=bool(context.get("automatic_execution_requested", context.get("automaticExecutionRequested", False))),
        )


@dataclass(slots=True)
class HeapSnapshotPathToRootProofPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class HeapSnapshotPathToRootProofPlanManager:
    """Review-only path-to-root proof planner after bounded path estimates."""

    def review(self, spec: HeapSnapshotPathToRootProofPlanSpec | None) -> HeapSnapshotPathToRootProofPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            plan = self._plan_descriptor(None, ["missing_heap_snapshot_path_to_root_proof_plan_request"], [], policy)
            return HeapSnapshotPathToRootProofPlanResult(status="blocked", plan=plan, side_effect_policy=policy, reason="missing_heap_snapshot_path_to_root_proof_plan_request")
        blockers, warnings = self._validate_inputs(spec)
        candidates = [] if blockers else self._candidate_inputs(spec)
        plan = self._plan_descriptor(spec, blockers, candidates, policy, warnings=warnings)
        status = "blocked" if blockers else "ready_for_review"
        return HeapSnapshotPathToRootProofPlanResult(status=status, plan=plan, side_effect_policy=policy, reason=blockers[0] if blockers else None)

    def _validate_inputs(self, spec: HeapSnapshotPathToRootProofPlanSpec) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings = [
            "heap_snapshot_path_to_root_proof_plan_review_only",
            "heap_snapshot_path_to_root_proof_executor_not_invoked",
            "raw_heap_ingestion_deferred_to_future_review",
        ]
        path = spec.path_to_root_analysis
        if not isinstance(path, dict):
            blockers.append("heap_snapshot_path_to_root_analysis_required")
        else:
            if path.get("schema_version") != "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1":
                blockers.append("heap_snapshot_path_to_root_analysis_schema_mismatch")
            if path.get("status") != "executed":
                blockers.append("heap_snapshot_path_to_root_analysis_not_executed")
            candidates = self._path_rows(path)
            if not candidates:
                blockers.append("heap_snapshot_path_to_root_candidate_paths_required")
            if path.get("raw_heap_exported") is True or path.get("raw_strings_exported") is True:
                blockers.append("heap_snapshot_path_to_root_analysis_exported_raw_data")
            if path.get("path_to_root_proven") is True:
                blockers.append("heap_snapshot_path_to_root_analysis_already_claims_proof")
            if path.get("retained_size_proven") is True:
                blockers.append("heap_snapshot_path_to_root_analysis_claims_retained_size_proof")
            if path.get("complete_heap_traversal_claimed") is True:
                blockers.append("heap_snapshot_path_to_root_analysis_claims_complete_traversal")
            policy = path.get("side_effect_policy") if isinstance(path.get("side_effect_policy"), dict) else {}
            if any(bool(policy.get(item)) for item in ("browser_started", "cdp_command_sent", "calls_mcp", "mobile_runtime_used")):
                blockers.append("heap_snapshot_path_to_root_analysis_has_forbidden_side_effects")
        retained = spec.retained_size_analysis
        if isinstance(retained, dict):
            if retained.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-analysis.v1":
                blockers.append("heap_snapshot_retained_size_analysis_schema_mismatch")
            if retained.get("status") != "executed":
                blockers.append("heap_snapshot_retained_size_analysis_not_executed")
            if retained.get("raw_heap_exported") is True or retained.get("raw_strings_exported") is True:
                blockers.append("heap_snapshot_retained_size_analysis_exported_raw_data")
            if retained.get("retained_size_proven") is True or retained.get("complete_heap_traversal_claimed") is True:
                blockers.append("heap_snapshot_retained_size_analysis_claims_proof_or_complete_traversal")
        followup = spec.automatic_followup_plan
        if isinstance(followup, dict):
            if followup.get("schema_version") != "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1":
                blockers.append("heap_snapshot_automatic_followup_plan_schema_mismatch")
            if followup.get("status") != "ready_for_review":
                blockers.append("heap_snapshot_automatic_followup_plan_not_ready")
            if followup.get("automatic_execution_allowed") is True:
                blockers.append("heap_snapshot_automatic_followup_plan_allows_automatic_execution")
            policy = followup.get("side_effect_policy") if isinstance(followup.get("side_effect_policy"), dict) else {}
            forbidden = (
                "browser_started",
                "cdp_command_sent",
                "calls_mcp",
                "mobile_runtime_used",
                "raw_heap_loaded",
                "raw_heap_parsed",
                "heap_diff_computed",
                "retained_size_proven",
                "path_to_root_proven",
                "automatic_execution_allowed",
            )
            if any(bool(policy.get(item)) for item in forbidden):
                blockers.append("heap_snapshot_automatic_followup_plan_has_forbidden_side_effects")
        retained_proof = spec.retained_size_proof_plan
        if isinstance(retained_proof, dict):
            if retained_proof.get("schema_version") != "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1":
                blockers.append("heap_snapshot_retained_size_proof_plan_schema_mismatch")
            if retained_proof.get("status") != "ready_for_review":
                blockers.append("heap_snapshot_retained_size_proof_plan_not_ready")
            future = retained_proof.get("future_executor_contract") if isinstance(retained_proof.get("future_executor_contract"), dict) else {}
            if future.get("implemented") is True or future.get("ready_to_execute_now") is True:
                blockers.append("heap_snapshot_retained_size_proof_plan_future_executor_enabled")
            if retained_proof.get("retained_size_proven") is True or retained_proof.get("automatic_execution_allowed") is True:
                blockers.append("heap_snapshot_retained_size_proof_plan_has_forbidden_side_effects")
        if spec.raw_heap_ingestion_requested:
            blockers.append("raw_heap_ingestion_not_allowed_in_path_to_root_proof_plan")
        if spec.raw_heap_export_requested:
            blockers.append("raw_heap_export_not_allowed")
        if spec.raw_strings_export_requested:
            blockers.append("raw_strings_export_not_allowed")
        if spec.heap_diff_recompute_requested:
            blockers.append("heap_diff_recompute_not_allowed_in_path_to_root_proof_plan")
        if spec.path_to_root_proof_execution_requested:
            blockers.append("path_to_root_proof_execution_not_allowed_in_plan")
        if spec.complete_traversal_claim_requested:
            blockers.append("complete_heap_traversal_claim_not_allowed")
        if spec.automatic_execution_requested:
            blockers.append("automatic_heap_followup_execution_not_allowed")
        return list(dict.fromkeys(blockers)), warnings

    def _candidate_inputs(self, spec: HeapSnapshotPathToRootProofPlanSpec) -> list[dict[str, Any]]:
        path = spec.path_to_root_analysis or {}
        rows = self._path_rows(path)
        candidates: list[dict[str, Any]] = []
        for index, row in enumerate(rows[: spec.max_candidates]):
            if not isinstance(row, dict):
                continue
            candidates.append(
                {
                    "index": index,
                    "name": row.get("name") or row.get("candidate_name") or row.get("candidate"),
                    "path_depth": row.get("path_depth", row.get("depth")),
                    "root_like_node_reached": row.get("root_like_node_reached", row.get("path_found_within_bounds")),
                    "incoming_edge_count": row.get("incoming_edge_count"),
                    "source": "heap_snapshot_path_to_root_analysis",
                    "requires_raw_heap_for_proof": True,
                    "proof_available_now": False,
                }
            )
        return candidates

    def _plan_descriptor(
        self,
        spec: HeapSnapshotPathToRootProofPlanSpec | None,
        blockers: list[str],
        candidates: list[dict[str, Any]],
        side_effect_policy: dict[str, Any],
        *,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        status = "blocked" if blockers else "ready_for_review"
        source_summary = self._source_summary(spec)
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-proof-plan.v1",
            "status": status,
            "review_only": True,
            "plan_only": True,
            "proof_plan_only": True,
            "planner_name": "review_heap_snapshot_path_to_root_proof_plan",
            "plan_artifact": "workspace/heap-snapshot-path-to-root-proof-plan.json",
            "planned_result_artifact": "workspace/heap-snapshot-path-to-root-proof.json",
            "reviewer": spec.reviewer if spec else None,
            "source_summary": source_summary,
            "candidate_inputs": candidates,
            "candidate_count": len(candidates),
            "top_candidate": candidates[0] if candidates else {},
            "proof_requirements": {
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_parser_sandbox": True,
                "requires_redaction_policy": True,
                "requires_size_budget": True,
                "requires_root_set_policy": True,
                "requires_full_incoming_edge_walk": True,
                "requires_cycle_detection": True,
                "requires_explicit_review": True,
                "raw_heap_available_in_this_plan": False,
                "proof_computed_in_this_plan": False,
            },
            "future_executor_contract": {
                "executor_name": "execute_heap_snapshot_path_to_root_proof",
                "implemented": False,
                "ready_to_execute_now": False,
                "requires_raw_heap": True,
                "requires_raw_heap_ingestion_preflight": True,
                "requires_root_set_policy": True,
                "requires_full_incoming_edge_walk": True,
                "requires_explicit_review": True,
                "result_artifact": "workspace/heap-snapshot-path-to-root-proof.json",
            },
            "raw_heap_loaded": False,
            "raw_heap_parsed": False,
            "raw_heap_exported": False,
            "raw_strings_exported": False,
            "heap_diff_computed": False,
            "new_heap_diff_computed": False,
            "path_to_root_estimated_now": False,
            "path_to_root_proven": False,
            "retained_size_proven": False,
            "complete_heap_traversal_claimed": False,
            "proof_executor_invoked": False,
            "automatic_execution_allowed": False,
            "blockers": blockers,
            "warnings": warnings or [],
            "next_action": "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor" if not blockers else "resolve_heap_snapshot_path_to_root_proof_plan_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _source_summary(spec: HeapSnapshotPathToRootProofPlanSpec | None) -> dict[str, Any]:
        if spec is None:
            return {}
        return {
            "path_to_root_analysis": HeapSnapshotPathToRootProofPlanManager._path_summary(spec.path_to_root_analysis),
            "retained_size_analysis": HeapSnapshotRetainedSizeProofPlanManager._retained_summary(spec.retained_size_analysis),
            "automatic_followup_plan": HeapSnapshotRetainedSizeProofPlanManager._followup_summary(spec.automatic_followup_plan),
            "retained_size_proof_plan": HeapSnapshotPathToRootProofPlanManager._proof_plan_summary(spec.retained_size_proof_plan),
        }

    @staticmethod
    def _path_summary(descriptor: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        rows = HeapSnapshotPathToRootProofPlanManager._path_rows(descriptor)
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "result_artifact": descriptor.get("result_artifact"),
            "candidate_count": len(rows),
            "raw_heap_exported": bool(descriptor.get("raw_heap_exported", False)),
            "raw_strings_exported": bool(descriptor.get("raw_strings_exported", False)),
            "path_to_root_estimated": bool(descriptor.get("path_to_root_estimated", False)),
            "path_to_root_proven": bool(descriptor.get("path_to_root_proven", False)),
            "complete_heap_traversal_claimed": bool(descriptor.get("complete_heap_traversal_claimed", False)),
        }

    @staticmethod
    def _proof_plan_summary(descriptor: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(descriptor, dict):
            return {"provided": False}
        return {
            "provided": True,
            "schema_version": descriptor.get("schema_version"),
            "status": descriptor.get("status"),
            "candidate_count": descriptor.get("candidate_count"),
            "proof_plan_only": bool(descriptor.get("proof_plan_only", False)),
            "automatic_execution_allowed": bool(descriptor.get("automatic_execution_allowed", False)),
        }

    @staticmethod
    def _path_rows(descriptor: dict[str, Any]) -> list[Any]:
        rows = descriptor.get("candidate_paths")
        if isinstance(rows, list):
            return rows
        rows = descriptor.get("path_estimates")
        if isinstance(rows, list):
            return rows
        return []

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        policy = HeapSnapshotRetainedSizeProofPlanManager._side_effect_policy()
        policy = dict(policy)
        policy.update(
            {
                "path_to_root_estimated": False,
                "path_to_root_proven": False,
                "complete_heap_traversal": False,
                "complete_heap_traversal_claimed": False,
            }
        )
        return policy
