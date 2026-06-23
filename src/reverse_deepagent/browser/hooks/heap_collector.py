from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)

from reverse_deepagent.browser.base import BrowserPage

@dataclass(slots=True)
class HeapSnapshotReadinessSpec:
    """Review-only CDP HeapProfiler heap snapshot readiness request.

    This descriptor is intentionally preflight-only: it normalizes caller-provided
    BrowserProvider / CDP / HeapProfiler capability evidence and future safety
    gates, but never starts a browser, sends CDP commands, or collects heap data.
    """

    browser_provider_id: str | None = None
    cdp_available: bool | None = None
    heap_profiler_capability: str = "unknown"
    max_snapshot_bytes: int = 25_000_000
    raw_heap_export_allowed: bool = False
    redaction_plan: str = "required"

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotReadinessSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_readiness",
                "heapSnapshotReadiness",
                "cdp_heap_snapshot_readiness",
                "cdpHeapSnapshotReadiness",
                "heap_profiler_readiness",
                "heapProfilerReadiness",
                "review_heap_snapshot_readiness",
                "reviewHeapSnapshotReadiness",
            )
        )
        has_evidence = any(
            key in context
            for key in (
                "browser_provider_id",
                "browserProviderId",
                "provider_id",
                "providerId",
                "cdp_available",
                "cdpAvailable",
                "heap_profiler_capability",
                "heapProfilerCapability",
                "heap_profiler_available",
                "heapProfilerAvailable",
            )
        )
        if not requested and not has_evidence:
            return None
        provider_id = context.get("browser_provider_id", context.get("browserProviderId", context.get("provider_id", context.get("providerId"))))
        cdp_available = cls._coerce_optional_bool(context.get("cdp_available", context.get("cdpAvailable")))
        capability = context.get("heap_profiler_capability", context.get("heapProfilerCapability"))
        if capability is None and "heap_profiler_available" in context:
            capability = "provided" if cls._coerce_optional_bool(context.get("heap_profiler_available")) else "missing"
        if capability is None and "heapProfilerAvailable" in context:
            capability = "provided" if cls._coerce_optional_bool(context.get("heapProfilerAvailable")) else "missing"
        max_bytes = int(context.get("max_snapshot_bytes", context.get("maxSnapshotBytes", 25_000_000)) or 25_000_000)
        raw_allowed = bool(context.get("raw_heap_export_allowed", context.get("rawHeapExportAllowed", False)))
        redaction_plan = str(context.get("redaction_plan", context.get("redactionPlan", "required")) or "required")
        return cls(
            browser_provider_id=str(provider_id).strip() if provider_id else None,
            cdp_available=cdp_available,
            heap_profiler_capability=str(capability or "unknown").strip().lower(),
            max_snapshot_bytes=max(1, max_bytes),
            raw_heap_export_allowed=raw_allowed,
            redaction_plan=redaction_plan,
        )

    @staticmethod
    def _coerce_optional_bool(value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "available", "provided", "supported"}:
                return True
            if lowered in {"0", "false", "no", "n", "missing", "unavailable", "unsupported"}:
                return False
        return bool(value)


@dataclass(slots=True)
class HeapSnapshotReadinessResult:
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


class HeapSnapshotReadinessManager:
    """Review-only HeapProfiler heap snapshot preflight descriptor builder."""

    def review(self, spec: HeapSnapshotReadinessSpec | None) -> HeapSnapshotReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            descriptor = self._descriptor(None, status="blocked", blockers=["missing_heap_snapshot_readiness_request"], warnings=[], side_effect_policy=policy)
            return HeapSnapshotReadinessResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_readiness_request")

        blockers: list[str] = []
        warnings: list[str] = []
        if spec.cdp_available is not True:
            blockers.append("cdp_capability_evidence_missing_or_unavailable")
        if spec.heap_profiler_capability not in {"provided", "available", "supported", "true"}:
            blockers.append("heap_profiler_capability_evidence_missing_or_unavailable")
        if spec.raw_heap_export_allowed:
            warnings.append("raw_heap_export_requested_but_not_allowed_by_default")
        if spec.max_snapshot_bytes > 100_000_000:
            warnings.append("large_heap_snapshot_budget_requires_review")

        status = "blocked" if blockers else "ready_for_review"
        descriptor = self._descriptor(spec, status=status, blockers=blockers, warnings=warnings, side_effect_policy=policy)
        reason = blockers[0] if blockers else None
        return HeapSnapshotReadinessResult(status=status, descriptor=descriptor, side_effect_policy=policy, reason=reason)

    def _descriptor(
        self,
        spec: HeapSnapshotReadinessSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        provider_id = spec.browser_provider_id if spec else None
        cdp_available = spec.cdp_available if spec else None
        heap_capability = spec.heap_profiler_capability if spec else "unknown"
        max_bytes = spec.max_snapshot_bytes if spec else 25_000_000
        raw_allowed = spec.raw_heap_export_allowed if spec else False
        redaction_plan = spec.redaction_plan if spec else "required"
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-readiness.v1",
            "status": status,
            "review_only": True,
            "preflight_only": True,
            "heap_snapshot_collected": False,
            "heap_diff_computed": False,
            "complete_heap_traversal_claimed": False,
            "capability_evidence": {
                "browser_provider_id": provider_id,
                "cdp_available": cdp_available,
                "heap_profiler_capability": heap_capability,
                "heap_profiler_capability_provided": heap_capability in {"provided", "available", "supported", "true"},
            },
            "safety_gates": {
                "requires_explicit_review_approval": True,
                "requires_cdp_heap_profiler": True,
                "requires_redaction_plan": True,
                "redaction_plan": redaction_plan,
                "max_snapshot_bytes": max_bytes,
                "raw_heap_export_allowed": False,
                "raw_heap_export_requested": bool(raw_allowed),
                "digest_only_by_default": True,
                "no_raw_heap_export_by_default": True,
                "complete_heap_traversal_claimed": False,
            },
            "future_collection_contract": {
                "future_route": "heap-snapshot-collect",
                "implemented": True,
                "requires_explicit_review_approval": True,
                "requires_cdp_heap_profiler": True,
                "requires_redaction_plan": True,
                "requires_size_budget": True,
                "requires_no_raw_heap_export_by_default": True,
                "requires_digest_or_redacted_summary": True,
            },
            "blockers": blockers,
            "warnings": warnings,
            "next_action": "review_heap_snapshot_readiness_before_collection" if not blockers else "provide_cdp_heap_profiler_capability_evidence",
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
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class HeapSnapshotCollectSpec:
    """Explicit review-gated CDP HeapProfiler heap snapshot collection request.

    The MVP collects only digest / bounded metadata. It never exports raw heap
    chunks, never computes heap diffs, and never claims complete heap traversal.
    """

    review_approved: bool = False
    explicit_collection: bool = False
    readiness_descriptor: dict[str, Any] | None = None
    max_snapshot_bytes: int = 25_000_000
    raw_heap_export_allowed: bool = False
    redaction_plan: str = "required"
    report_progress: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "HeapSnapshotCollectSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "heap_snapshot_collect",
                "heapSnapshotCollect",
                "cdp_heap_snapshot_collect",
                "cdpHeapSnapshotCollect",
                "collect_heap_snapshot",
                "collectHeapSnapshot",
                "reviewed_heap_snapshot_collect",
                "reviewedHeapSnapshotCollect",
                "execute_heap_snapshot_collect",
                "executeHeapSnapshotCollect",
            )
        )
        if not requested:
            return None
        readiness = context.get(
            "heap_snapshot_readiness",
            context.get(
                "heapSnapshotReadiness",
                context.get("heap_snapshot_readiness_descriptor", context.get("heapSnapshotReadinessDescriptor")),
            ),
        )
        return cls(
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            explicit_collection=bool(
                context.get(
                    "collect_heap_snapshot",
                    context.get(
                        "collectHeapSnapshot",
                        context.get("execute_heap_snapshot_collect", context.get("executeHeapSnapshotCollect", False)),
                    ),
                )
            ),
            readiness_descriptor=readiness if isinstance(readiness, dict) else None,
            max_snapshot_bytes=max(1, int(context.get("max_snapshot_bytes", context.get("maxSnapshotBytes", 25_000_000)) or 25_000_000)),
            raw_heap_export_allowed=bool(context.get("raw_heap_export_allowed", context.get("rawHeapExportAllowed", False))),
            redaction_plan=str(context.get("redaction_plan", context.get("redactionPlan", "required")) or "required"),
            report_progress=bool(context.get("report_progress", context.get("reportProgress", False))),
        )


@dataclass(slots=True)
class HeapSnapshotCollectResult:
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


class HeapSnapshotCollectManager:
    """Explicit-review-only HeapProfiler snapshot metadata collector."""

    _READY_STATUSES = {"ready_for_review", "ready", "approved"}
    _SUPPORTED_HEAP_CAPABILITIES = {"provided", "available", "supported", "true"}

    def collect(self, page: BrowserPage, spec: HeapSnapshotCollectSpec | None) -> HeapSnapshotCollectResult:
        policy = self._side_effect_policy(cdp_command_sent=False, heap_profiler_enabled=False, heap_snapshot_collected=False)
        if spec is None:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=["missing_heap_snapshot_collect_request"],
                warnings=[],
                commands_sent=[],
                snapshot_metadata={},
                side_effect_policy=policy,
            )
            return HeapSnapshotCollectResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason="missing_heap_snapshot_collect_request")

        blockers, warnings = self._review_gates(spec)
        if blockers:
            descriptor = self._descriptor(
                spec,
                status="blocked",
                blockers=blockers,
                warnings=warnings,
                commands_sent=[],
                snapshot_metadata={},
                side_effect_policy=policy,
            )
            return HeapSnapshotCollectResult(status="blocked", descriptor=descriptor, side_effect_policy=policy, reason=blockers[0])

        cdp = page.cdp_session()
        if cdp is None:
            descriptor = self._descriptor(
                spec,
                status="unsupported",
                blockers=["cdp_session_unavailable"],
                warnings=warnings,
                commands_sent=[],
                snapshot_metadata={},
                side_effect_policy=policy,
            )
            return HeapSnapshotCollectResult(status="unsupported", descriptor=descriptor, side_effect_policy=policy, reason="cdp_session_unavailable")

        chunks: list[str] = []
        if hasattr(cdp, "on"):
            try:
                cdp.on("HeapProfiler.addHeapSnapshotChunk", lambda payload: chunks.append(str((payload or {}).get("chunk", ""))))
            except Exception as e:
                _logger.debug("Failed to subscribe to heap snapshot chunk events: %s", e, exc_info=True)
                warnings.append("heap_snapshot_chunk_subscription_failed")

        commands_sent: list[str] = []
        try:
            cdp.send("HeapProfiler.enable")
            commands_sent.append("HeapProfiler.enable")
            result = cdp.send("HeapProfiler.takeHeapSnapshot", {"reportProgress": bool(spec.report_progress)})
            commands_sent.append("HeapProfiler.takeHeapSnapshot")
        except Exception as exc:  # pragma: no cover - exercised by adapter-specific sessions
            policy = self._side_effect_policy(
                cdp_command_sent=bool(commands_sent),
                heap_profiler_enabled="HeapProfiler.enable" in commands_sent,
                heap_snapshot_collected=False,
            )
            descriptor = self._descriptor(
                spec,
                status="failed",
                blockers=["heap_snapshot_collect_failed"],
                warnings=warnings,
                commands_sent=commands_sent,
                snapshot_metadata={},
                side_effect_policy=policy,
                error=str(exc),
            )
            return HeapSnapshotCollectResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="heap_snapshot_collect_failed", error=str(exc))
        finally:
            if "HeapProfiler.enable" in commands_sent:
                try:
                    cdp.send("HeapProfiler.disable")
                    commands_sent.append("HeapProfiler.disable")
                except Exception as e:
                    _logger.debug("Failed to disable HeapProfiler: %s", e, exc_info=True)
                    warnings.append("heap_profiler_disable_failed")

        snapshot_metadata = self._snapshot_metadata(chunks=chunks, result=result, max_snapshot_bytes=spec.max_snapshot_bytes)
        if snapshot_metadata["snapshot_byte_count"] > spec.max_snapshot_bytes:
            warnings.append("heap_snapshot_observed_size_exceeds_budget")
        policy = self._side_effect_policy(cdp_command_sent=True, heap_profiler_enabled=True, heap_snapshot_collected=True)
        descriptor = self._descriptor(
            spec,
            status="collected",
            blockers=[],
            warnings=warnings,
            commands_sent=commands_sent,
            snapshot_metadata=snapshot_metadata,
            side_effect_policy=policy,
        )
        return HeapSnapshotCollectResult(status="collected", descriptor=descriptor, side_effect_policy=policy)

    def _review_gates(self, spec: HeapSnapshotCollectSpec) -> tuple[list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not spec.review_approved:
            blockers.append("heap_snapshot_collect_review_approval_required")
        if not spec.explicit_collection:
            blockers.append("explicit_heap_snapshot_collection_flag_required")
        if spec.raw_heap_export_allowed:
            blockers.append("raw_heap_export_not_supported_by_mvp")
        if not spec.redaction_plan or spec.redaction_plan == "none":
            blockers.append("heap_snapshot_redaction_plan_required")
        readiness = spec.readiness_descriptor if isinstance(spec.readiness_descriptor, dict) else {}
        if not readiness:
            blockers.append("heap_snapshot_readiness_descriptor_required")
            return blockers, warnings
        if readiness.get("status") not in self._READY_STATUSES:
            blockers.append("heap_snapshot_readiness_not_ready")
        capability = readiness.get("capability_evidence") if isinstance(readiness.get("capability_evidence"), dict) else {}
        if capability.get("cdp_available") is not True:
            blockers.append("heap_snapshot_readiness_cdp_unavailable")
        heap_capability = str(capability.get("heap_profiler_capability") or "unknown").lower()
        if heap_capability not in self._SUPPORTED_HEAP_CAPABILITIES:
            blockers.append("heap_snapshot_readiness_heap_profiler_unavailable")
        safety = readiness.get("safety_gates") if isinstance(readiness.get("safety_gates"), dict) else {}
        if safety.get("raw_heap_export_requested") or safety.get("raw_heap_export_allowed"):
            warnings.append("readiness_requested_raw_heap_export_but_collect_mvp_blocks_raw_export")
        return blockers, warnings

    @staticmethod
    def _snapshot_metadata(*, chunks: list[str], result: Any, max_snapshot_bytes: int) -> dict[str, Any]:
        if chunks:
            payload = "".join(chunks).encode("utf-8", errors="replace")
            source = "HeapProfiler.addHeapSnapshotChunk"
        else:
            payload = json.dumps(result or {}, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8", errors="replace")
            source = "HeapProfiler.takeHeapSnapshot_result"
        digest = hashlib.sha256(payload).hexdigest()
        return {
            "snapshot_digest": f"sha256:{digest}",
            "snapshot_byte_count": len(payload),
            "chunk_count": len(chunks),
            "chunk_stream_observed": bool(chunks),
            "metadata_source": source,
            "max_snapshot_bytes": max_snapshot_bytes,
            "redacted_summary_only": True,
            "raw_heap_available_in_artifact": False,
            "node_count_estimate": None,
        }

    def _descriptor(
        self,
        spec: HeapSnapshotCollectSpec | None,
        *,
        status: str,
        blockers: list[str],
        warnings: list[str],
        commands_sent: list[str],
        snapshot_metadata: dict[str, Any],
        side_effect_policy: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        readiness = spec.readiness_descriptor if spec and isinstance(spec.readiness_descriptor, dict) else {}
        return {
            "schema_version": "reverse-deepagent.heap-snapshot-collect.v1",
            "status": status,
            "review_approved": bool(spec.review_approved) if spec else False,
            "explicit_collection": bool(spec.explicit_collection) if spec else False,
            "heap_snapshot_collected": status == "collected",
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "raw_heap_available_in_artifact": False,
            "complete_heap_traversal_claimed": False,
            "snapshot_metadata": snapshot_metadata,
            "readiness_summary": self._readiness_summary(readiness),
            "safety_gates": {
                "requires_explicit_review_approval": True,
                "requires_explicit_collection_flag": True,
                "requires_ready_heap_snapshot_readiness": True,
                "requires_cdp_session": True,
                "requires_redaction_plan": True,
                "redaction_plan": spec.redaction_plan if spec else "required",
                "max_snapshot_bytes": spec.max_snapshot_bytes if spec else 25_000_000,
                "raw_heap_export_allowed": False,
                "digest_only_by_default": True,
                "no_raw_heap_export_by_default": True,
            },
            "cdp": {
                "session_available": bool(commands_sent),
                "commands_sent": commands_sent,
                "heap_profiler_enable_sent": "HeapProfiler.enable" in commands_sent,
                "take_heap_snapshot_sent": "HeapProfiler.takeHeapSnapshot" in commands_sent,
                "heap_profiler_disable_sent": "HeapProfiler.disable" in commands_sent,
            },
            "blockers": blockers,
            "warnings": warnings,
            "error": error,
            "next_action": "review_heap_snapshot_collect_before_heap_diff" if status == "collected" else "resolve_heap_snapshot_collect_blockers",
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _readiness_summary(readiness: dict[str, Any]) -> dict[str, Any]:
        capability = readiness.get("capability_evidence") if isinstance(readiness.get("capability_evidence"), dict) else {}
        safety = readiness.get("safety_gates") if isinstance(readiness.get("safety_gates"), dict) else {}
        return {
            "schema_version": readiness.get("schema_version"),
            "status": readiness.get("status"),
            "browser_provider_id": capability.get("browser_provider_id"),
            "cdp_available": capability.get("cdp_available"),
            "heap_profiler_capability": capability.get("heap_profiler_capability"),
            "max_snapshot_bytes": safety.get("max_snapshot_bytes"),
            "redaction_plan": safety.get("redaction_plan"),
            "raw_heap_export_allowed": safety.get("raw_heap_export_allowed", False),
        }

    @staticmethod
    def _side_effect_policy(*, cdp_command_sent: bool, heap_profiler_enabled: bool, heap_snapshot_collected: bool) -> dict[str, Any]:
        return {
            "read_only": False,
            "review_only": False,
            "explicit_only": True,
            "default_recon": False,
            "files_mutated": False,
            "browser_started": True,
            "provider_factory_invoked": True,
            "provider_availability_checked": True,
            "cdp_command_sent": bool(cdp_command_sent),
            "heap_profiler_enabled": bool(heap_profiler_enabled),
            "heap_snapshot_collected": bool(heap_snapshot_collected),
            "heap_diff_computed": False,
            "raw_heap_exported": False,
            "complete_heap_traversal": False,
            "runtime_evaluated": False,
            "javascript_evaluated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


