from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass(slots=True)
class FlowTimelineSpec:
    """Cross-request flow timeline continuation request.

    This is an explicit synthesis baseline. It does not subscribe to browser
    events by itself; callers pass already-captured network / hook / debugger /
    replay payloads, optionally with a previous flow timeline, then the manager
    normalizes them into a single append-only event stream.
    """

    flow_id: str = "default-flow"
    run_id: str | None = None
    request_id: str | None = None
    previous_timeline: dict[str, Any] = field(default_factory=dict)
    flow_events: list[dict[str, Any]] = field(default_factory=list)
    source_payloads: dict[str, Any] = field(default_factory=dict)
    stitch_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_policy: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_rollback_execution_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_physical_rollback_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    max_payload_preview_length: int = 480

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "FlowTimelineSpec | None":
        context = context or {}
        raw_previous = (
            context.get("previous_flow_timeline")
            or context.get("previousFlowTimeline")
            or context.get("flow_timeline")
            or context.get("flowTimeline")
        )
        previous = cls._coerce_mapping(raw_previous)
        flow_events = cls._coerce_events(context.get("flow_events", context.get("flowEvents", context.get("events"))))
        source_payloads = cls._collect_source_payloads(context)
        raw_review_decisions = cls._first_present(
            context,
            "stitch_review_decisions",
            "stitchReviewDecisions",
            "review_decisions",
            "reviewDecisions",
            "stitch_decisions",
        )
        stitch_review_decisions = cls._coerce_events(raw_review_decisions)
        auto_stitch_policy = cls._coerce_mapping(
            cls._first_present(
                context,
                "auto_stitch_policy",
                "autoStitchPolicy",
                "auto_stitching_policy",
                "autoStitchingPolicy",
            )
        )
        raw_materialization_review_decisions = cls._first_present(
            context,
            "auto_stitch_materialization_review_decisions",
            "autoStitchMaterializationReviewDecisions",
            "auto_stitch_materialization_plan_review_decisions",
            "autoStitchMaterializationPlanReviewDecisions",
            "materialization_review_decisions",
            "materializationReviewDecisions",
        )
        materialization_review_decisions = cls._coerce_events(raw_materialization_review_decisions)
        raw_rollback_execution_review_decisions = cls._first_present(
            context,
            "auto_stitch_rollback_execution_review_decisions",
            "autoStitchRollbackExecutionReviewDecisions",
            "rollback_execution_review_decisions",
            "rollbackExecutionReviewDecisions",
            "stitched_flow_rollback_review_decisions",
            "stitchedFlowRollbackReviewDecisions",
        )
        rollback_execution_review_decisions = cls._coerce_events(raw_rollback_execution_review_decisions)
        raw_physical_rollback_review_decisions = cls._first_present(
            context,
            "auto_stitch_physical_rollback_review_decisions",
            "autoStitchPhysicalRollbackReviewDecisions",
            "physical_rollback_review_decisions",
            "physicalRollbackReviewDecisions",
            "stitched_flow_physical_rollback_review_decisions",
            "stitchedFlowPhysicalRollbackReviewDecisions",
        )
        physical_rollback_review_decisions = cls._coerce_events(raw_physical_rollback_review_decisions)
        if (
            not previous
            and not flow_events
            and not source_payloads
            and not stitch_review_decisions
            and not auto_stitch_policy
            and not materialization_review_decisions
            and not rollback_execution_review_decisions
            and not physical_rollback_review_decisions
        ):
            return None
        flow_id = str(context.get("flow_id", context.get("flowId", previous.get("flow_id", "default-flow"))) or "default-flow")
        return cls(
            flow_id=flow_id,
            run_id=str(context.get("run_id", context.get("runId"))) if context.get("run_id", context.get("runId")) else None,
            request_id=str(context.get("request_id", context.get("requestId"))) if context.get("request_id", context.get("requestId")) else None,
            previous_timeline=previous,
            flow_events=flow_events,
            source_payloads=source_payloads,
            stitch_review_decisions=stitch_review_decisions,
            auto_stitch_policy=auto_stitch_policy,
            auto_stitch_materialization_review_decisions=materialization_review_decisions,
            auto_stitch_rollback_execution_review_decisions=rollback_execution_review_decisions,
            auto_stitch_physical_rollback_review_decisions=physical_rollback_review_decisions,
            max_payload_preview_length=int(context.get("max_payload_preview_length", context.get("maxPayloadPreviewLength", 480)) or 480),
        )

    @staticmethod
    def _coerce_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _first_present(context: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in context:
                return context.get(key)
        return None

    @staticmethod
    def _coerce_events(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [dict(value)]
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return FlowTimelineSpec._coerce_events(parsed)
        if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str, dict)):
            return [dict(item) for item in value if isinstance(item, dict)]
        return []

    @classmethod
    def _collect_source_payloads(cls, context: dict[str, Any]) -> dict[str, Any]:
        aliases = {
            "network_requests": ("network_requests", "networkRequests", "request_samples", "requestSamples"),
            "request_initiators": ("request_initiators", "requestInitiators"),
            "hook_timeline": ("hook_timeline", "hookTimeline"),
            "function_hook_timeline": ("function_hook_timeline", "functionHookTimeline"),
            "module_hook_timeline": ("module_hook_timeline", "moduleHookTimeline"),
            "debugger_timeline": ("debugger_timeline", "debuggerTimeline"),
            "source_logpoint_timeline": ("source_logpoint_timeline", "sourceLogpointTimeline"),
            "mutation_observer_timeline": ("mutation_observer_timeline", "mutationObserverTimeline"),
            "replay_validation": ("replay_validation", "replayValidation", "function_validations", "functionValidations"),
        }
        payloads: dict[str, Any] = {}
        for canonical, keys in aliases.items():
            for key in keys:
                if key in context:
                    payloads[canonical] = cls._coerce_payload(context[key])
                    break
        timeline_inputs = context.get("timeline_inputs", context.get("timelineInputs"))
        if isinstance(timeline_inputs, list):
            for item in timeline_inputs:
                if not isinstance(item, dict):
                    continue
                source = item.get("source") or item.get("name")
                if not source:
                    continue
                payloads[str(source)] = cls._coerce_payload(item.get("payload", item.get("data", item)))
        return payloads

    @classmethod
    def _coerce_payload(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip():
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value


@dataclass(slots=True)
class FlowTimelineResult:
    status: str
    flow_id: str
    run_id: str | None = None
    entries: list[dict[str, Any]] = field(default_factory=list)
    correlation_groups: list[dict[str, Any]] = field(default_factory=list)
    stitch_candidates: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_dry_runs: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_conflict_resolutions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_conflict_resolution_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_policy_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_policy_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_plans: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_results: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_result_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_audit_entries: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_audit_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_rollback_plans: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_rollback_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_materialization_transactions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_materialization_transaction_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_rollback_execution_plans: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_rollback_execution_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_rollback_execution_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_rollback_execution_results: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_rollback_execution_result_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_rollback_review_gate_recomputations: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_rollback_review_gate_recomputation_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_physical_rollback_dry_run_diffs: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_physical_rollback_dry_run_diff_summary: dict[str, Any] = field(default_factory=dict)
    auto_stitch_physical_rollback_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_physical_rollback_results: list[dict[str, Any]] = field(default_factory=list)
    auto_stitch_physical_rollback_result_summary: dict[str, Any] = field(default_factory=dict)
    stitch_proposals: list[dict[str, Any]] = field(default_factory=list)
    stitch_review_decisions: list[dict[str, Any]] = field(default_factory=list)
    stitched_flows: list[dict[str, Any]] = field(default_factory=list)
    previous_entry_count: int = 0
    new_entry_count: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    continued_from_previous: bool = False
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "flow_id": self.flow_id,
            "run_id": self.run_id,
            "entry_count": len(self.entries),
            "previous_entry_count": self.previous_entry_count,
            "new_entry_count": self.new_entry_count,
            "continued_from_previous": self.continued_from_previous,
            "source_counts": self.source_counts,
            "entries": self.entries,
            "correlation_group_count": len(self.correlation_groups),
            "correlation_groups": self.correlation_groups,
            "stitch_candidate_count": len(self.stitch_candidates),
            "stitch_candidates": self.stitch_candidates,
            "auto_stitch_dry_run_count": len(self.auto_stitch_dry_runs),
            "auto_stitch_dry_runs": self.auto_stitch_dry_runs,
            "auto_stitch_conflict_resolution_count": len(self.auto_stitch_conflict_resolutions),
            "auto_stitch_conflict_resolutions": self.auto_stitch_conflict_resolutions,
            "auto_stitch_conflict_resolution_summary": self.auto_stitch_conflict_resolution_summary,
            "auto_stitch_policy_decision_count": len(self.auto_stitch_policy_decisions),
            "auto_stitch_policy_decisions": self.auto_stitch_policy_decisions,
            "auto_stitch_policy_summary": self.auto_stitch_policy_summary,
            "auto_stitch_materialization_plan_count": len(self.auto_stitch_materialization_plans),
            "auto_stitch_materialization_plans": self.auto_stitch_materialization_plans,
            "auto_stitch_materialization_summary": self.auto_stitch_materialization_summary,
            "auto_stitch_materialization_review_decision_count": len(self.auto_stitch_materialization_review_decisions),
            "auto_stitch_materialization_review_decisions": self.auto_stitch_materialization_review_decisions,
            "auto_stitch_materialization_result_count": len(self.auto_stitch_materialization_results),
            "auto_stitch_materialization_results": self.auto_stitch_materialization_results,
            "auto_stitch_materialization_result_summary": self.auto_stitch_materialization_result_summary,
            "auto_stitch_materialization_audit_count": len(self.auto_stitch_materialization_audit_entries),
            "auto_stitch_materialization_audit_entries": self.auto_stitch_materialization_audit_entries,
            "auto_stitch_materialization_audit_summary": self.auto_stitch_materialization_audit_summary,
            "auto_stitch_materialization_rollback_plan_count": len(self.auto_stitch_materialization_rollback_plans),
            "auto_stitch_materialization_rollback_plans": self.auto_stitch_materialization_rollback_plans,
            "auto_stitch_materialization_rollback_summary": self.auto_stitch_materialization_rollback_summary,
            "auto_stitch_materialization_transaction_count": len(self.auto_stitch_materialization_transactions),
            "auto_stitch_materialization_transactions": self.auto_stitch_materialization_transactions,
            "auto_stitch_materialization_transaction_summary": self.auto_stitch_materialization_transaction_summary,
            "auto_stitch_rollback_execution_plan_count": len(self.auto_stitch_rollback_execution_plans),
            "auto_stitch_rollback_execution_plans": self.auto_stitch_rollback_execution_plans,
            "auto_stitch_rollback_execution_summary": self.auto_stitch_rollback_execution_summary,
            "auto_stitch_rollback_execution_review_decision_count": len(self.auto_stitch_rollback_execution_review_decisions),
            "auto_stitch_rollback_execution_review_decisions": self.auto_stitch_rollback_execution_review_decisions,
            "auto_stitch_rollback_execution_result_count": len(self.auto_stitch_rollback_execution_results),
            "auto_stitch_rollback_execution_results": self.auto_stitch_rollback_execution_results,
            "auto_stitch_rollback_execution_result_summary": self.auto_stitch_rollback_execution_result_summary,
            "auto_stitch_rollback_review_gate_recomputation_count": len(self.auto_stitch_rollback_review_gate_recomputations),
            "auto_stitch_rollback_review_gate_recomputations": self.auto_stitch_rollback_review_gate_recomputations,
            "auto_stitch_rollback_review_gate_recomputation_summary": self.auto_stitch_rollback_review_gate_recomputation_summary,
            "auto_stitch_physical_rollback_dry_run_diff_count": len(self.auto_stitch_physical_rollback_dry_run_diffs),
            "auto_stitch_physical_rollback_dry_run_diffs": self.auto_stitch_physical_rollback_dry_run_diffs,
            "auto_stitch_physical_rollback_dry_run_diff_summary": self.auto_stitch_physical_rollback_dry_run_diff_summary,
            "auto_stitch_physical_rollback_review_decision_count": len(self.auto_stitch_physical_rollback_review_decisions),
            "auto_stitch_physical_rollback_review_decisions": self.auto_stitch_physical_rollback_review_decisions,
            "auto_stitch_physical_rollback_result_count": len(self.auto_stitch_physical_rollback_results),
            "auto_stitch_physical_rollback_results": self.auto_stitch_physical_rollback_results,
            "auto_stitch_physical_rollback_result_summary": self.auto_stitch_physical_rollback_result_summary,
            "stitch_proposal_count": len(self.stitch_proposals),
            "stitch_proposals": self.stitch_proposals,
            "stitch_review_decision_count": len(self.stitch_review_decisions),
            "stitch_review_decisions": self.stitch_review_decisions,
            "stitched_flow_count": len(self.stitched_flows),
            "stitched_flows": self.stitched_flows,
            "error": self.error,
            "reason": self.reason,
        }


class FlowTimelineManager:
    """Normalize and continue timeline fragments across explicit reverse runs."""

    def build(self, spec: FlowTimelineSpec | None) -> FlowTimelineResult:
        if spec is None:
            return FlowTimelineResult(status="unsupported", flow_id="unknown", reason="missing_flow_timeline_spec")
        previous_entries = self._previous_entries(spec)
        next_sequence = self._next_sequence(previous_entries)
        entries = [dict(entry) for entry in previous_entries]
        source_counts: dict[str, int] = {}
        new_entries: list[dict[str, Any]] = []

        for event in spec.flow_events:
            new_entries.append(self._entry_from_event(event, spec, "flow_event", next_sequence + len(new_entries)))
        for source, payload in spec.source_payloads.items():
            source_entries = self._entries_from_source(source, payload, spec, next_sequence + len(new_entries))
            source_counts[source] = len(source_entries)
            new_entries.extend(source_entries)

        entries.extend(new_entries)
        correlation_groups = self._correlation_groups(entries)
        stitch_candidates = self._stitch_candidates(correlation_groups, entries)
        auto_stitch_dry_runs = self._auto_stitch_dry_runs(stitch_candidates)
        auto_stitch_conflict_resolutions = self._auto_stitch_conflict_resolutions(auto_stitch_dry_runs, stitch_candidates)
        auto_stitch_conflict_resolution_summary = self._auto_stitch_conflict_resolution_summary(auto_stitch_conflict_resolutions)
        auto_stitch_policy_decisions = self._auto_stitch_policy_decisions(auto_stitch_dry_runs, spec.auto_stitch_policy)
        auto_stitch_policy_summary = self._auto_stitch_policy_summary(auto_stitch_policy_decisions, spec.auto_stitch_policy)
        auto_stitch_materialization_plans = self._auto_stitch_materialization_plans(
            auto_stitch_policy_decisions,
            auto_stitch_dry_runs,
            stitch_candidates,
            auto_stitch_conflict_resolutions,
            spec.auto_stitch_policy,
        )
        auto_stitch_materialization_plans = self._apply_materialization_review_decisions(
            auto_stitch_materialization_plans,
            spec.auto_stitch_materialization_review_decisions,
        )
        auto_stitch_materialization_summary = self._auto_stitch_materialization_summary(
            auto_stitch_materialization_plans,
            auto_stitch_policy_decisions,
            spec.auto_stitch_policy,
        )
        stitch_proposals = self._stitch_proposals(stitch_candidates)
        stitch_proposals = self._apply_review_decisions(stitch_proposals, spec.stitch_review_decisions)
        stitched_flows = self._stitched_flows(stitch_proposals, stitch_candidates, entries)
        auto_stitch_materialization_results = self._auto_stitch_materialization_results(
            auto_stitch_materialization_plans,
            entries,
            existing_stitched_flows=stitched_flows,
        )
        stitched_flows = [
            *stitched_flows,
            *self._stitched_flows_from_materialization_results(
                auto_stitch_materialization_results,
                existing_count=len(stitched_flows),
            ),
        ]
        auto_stitch_materialization_result_summary = self._auto_stitch_materialization_result_summary(
            auto_stitch_materialization_results,
            spec.auto_stitch_materialization_review_decisions,
        )
        auto_stitch_materialization_audit_entries = self._auto_stitch_materialization_audit_entries(
            auto_stitch_materialization_results,
            spec,
        )
        auto_stitch_materialization_audit_summary = self._auto_stitch_materialization_audit_summary(
            auto_stitch_materialization_audit_entries,
            auto_stitch_materialization_results,
        )
        auto_stitch_materialization_rollback_plans = self._auto_stitch_materialization_rollback_plans(
            auto_stitch_materialization_results,
            auto_stitch_materialization_audit_entries,
        )
        auto_stitch_materialization_rollback_summary = self._auto_stitch_materialization_rollback_summary(
            auto_stitch_materialization_rollback_plans,
            auto_stitch_materialization_results,
        )
        auto_stitch_materialization_transactions = self._auto_stitch_materialization_transactions(
            auto_stitch_materialization_results,
            auto_stitch_materialization_audit_entries,
            auto_stitch_materialization_rollback_plans,
        )
        auto_stitch_materialization_transaction_summary = self._auto_stitch_materialization_transaction_summary(
            auto_stitch_materialization_transactions,
            auto_stitch_materialization_results,
        )
        auto_stitch_rollback_execution_plans = self._auto_stitch_rollback_execution_plans(
            auto_stitch_materialization_rollback_plans,
            auto_stitch_materialization_transactions,
        )
        auto_stitch_rollback_execution_plans = self._apply_rollback_execution_review_decisions(
            auto_stitch_rollback_execution_plans,
            spec.auto_stitch_rollback_execution_review_decisions,
        )
        auto_stitch_rollback_execution_summary = self._auto_stitch_rollback_execution_summary(
            auto_stitch_rollback_execution_plans,
            auto_stitch_materialization_transactions,
        )
        auto_stitch_rollback_execution_results = self._auto_stitch_rollback_execution_results(
            auto_stitch_rollback_execution_plans,
            auto_stitch_materialization_transactions,
        )
        auto_stitch_rollback_execution_result_summary = self._auto_stitch_rollback_execution_result_summary(
            auto_stitch_rollback_execution_results,
            spec.auto_stitch_rollback_execution_review_decisions,
        )
        auto_stitch_rollback_review_gate_recomputations = self._auto_stitch_rollback_review_gate_recomputations(
            auto_stitch_rollback_execution_results,
        )
        auto_stitch_rollback_review_gate_recomputation_summary = self._auto_stitch_rollback_review_gate_recomputation_summary(
            auto_stitch_rollback_review_gate_recomputations,
            auto_stitch_rollback_execution_results,
        )
        auto_stitch_physical_rollback_dry_run_diffs = self._auto_stitch_physical_rollback_dry_run_diffs(
            auto_stitch_rollback_execution_results,
            auto_stitch_rollback_review_gate_recomputations,
        )
        auto_stitch_physical_rollback_dry_run_diffs = self._apply_physical_rollback_review_decisions(
            auto_stitch_physical_rollback_dry_run_diffs,
            spec.auto_stitch_physical_rollback_review_decisions,
        )
        auto_stitch_physical_rollback_dry_run_diff_summary = self._auto_stitch_physical_rollback_dry_run_diff_summary(
            auto_stitch_physical_rollback_dry_run_diffs,
            auto_stitch_rollback_execution_results,
        )
        auto_stitch_physical_rollback_results = self._auto_stitch_physical_rollback_results(
            auto_stitch_physical_rollback_dry_run_diffs,
            stitched_flows,
        )
        stitched_flows = self._stitched_flows_after_physical_rollback_results(
            stitched_flows,
            auto_stitch_physical_rollback_results,
        )
        auto_stitch_physical_rollback_result_summary = self._auto_stitch_physical_rollback_result_summary(
            auto_stitch_physical_rollback_results,
            spec.auto_stitch_physical_rollback_review_decisions,
        )
        status = "success" if new_entries or stitched_flows else "partial" if previous_entries else "unsupported"
        return FlowTimelineResult(
            status=status,
            flow_id=spec.flow_id,
            run_id=spec.run_id,
            entries=entries,
            correlation_groups=correlation_groups,
            stitch_candidates=stitch_candidates,
            auto_stitch_dry_runs=auto_stitch_dry_runs,
            auto_stitch_conflict_resolutions=auto_stitch_conflict_resolutions,
            auto_stitch_conflict_resolution_summary=auto_stitch_conflict_resolution_summary,
            auto_stitch_policy_decisions=auto_stitch_policy_decisions,
            auto_stitch_policy_summary=auto_stitch_policy_summary,
            auto_stitch_materialization_plans=auto_stitch_materialization_plans,
            auto_stitch_materialization_summary=auto_stitch_materialization_summary,
            auto_stitch_materialization_review_decisions=list(spec.auto_stitch_materialization_review_decisions),
            auto_stitch_materialization_results=auto_stitch_materialization_results,
            auto_stitch_materialization_result_summary=auto_stitch_materialization_result_summary,
            auto_stitch_materialization_audit_entries=auto_stitch_materialization_audit_entries,
            auto_stitch_materialization_audit_summary=auto_stitch_materialization_audit_summary,
            auto_stitch_materialization_rollback_plans=auto_stitch_materialization_rollback_plans,
            auto_stitch_materialization_rollback_summary=auto_stitch_materialization_rollback_summary,
            auto_stitch_materialization_transactions=auto_stitch_materialization_transactions,
            auto_stitch_materialization_transaction_summary=auto_stitch_materialization_transaction_summary,
            auto_stitch_rollback_execution_plans=auto_stitch_rollback_execution_plans,
            auto_stitch_rollback_execution_summary=auto_stitch_rollback_execution_summary,
            auto_stitch_rollback_execution_review_decisions=list(spec.auto_stitch_rollback_execution_review_decisions),
            auto_stitch_rollback_execution_results=auto_stitch_rollback_execution_results,
            auto_stitch_rollback_execution_result_summary=auto_stitch_rollback_execution_result_summary,
            auto_stitch_rollback_review_gate_recomputations=auto_stitch_rollback_review_gate_recomputations,
            auto_stitch_rollback_review_gate_recomputation_summary=auto_stitch_rollback_review_gate_recomputation_summary,
            auto_stitch_physical_rollback_dry_run_diffs=auto_stitch_physical_rollback_dry_run_diffs,
            auto_stitch_physical_rollback_dry_run_diff_summary=auto_stitch_physical_rollback_dry_run_diff_summary,
            auto_stitch_physical_rollback_review_decisions=list(spec.auto_stitch_physical_rollback_review_decisions),
            auto_stitch_physical_rollback_results=auto_stitch_physical_rollback_results,
            auto_stitch_physical_rollback_result_summary=auto_stitch_physical_rollback_result_summary,
            stitch_proposals=stitch_proposals,
            stitch_review_decisions=list(spec.stitch_review_decisions),
            stitched_flows=stitched_flows,
            previous_entry_count=len(previous_entries),
            new_entry_count=len(new_entries),
            source_counts=source_counts,
            continued_from_previous=bool(previous_entries),
            reason=None if entries else "no_timeline_entries",
        )

    @staticmethod
    def _previous_entries(spec: FlowTimelineSpec) -> list[dict[str, Any]]:
        raw_entries = spec.previous_timeline.get("entries") if isinstance(spec.previous_timeline, dict) else []
        return [dict(item) for item in raw_entries if isinstance(item, dict)] if isinstance(raw_entries, list) else []

    @staticmethod
    def _next_sequence(entries: list[dict[str, Any]]) -> int:
        sequences = [int(item.get("sequence", -1)) for item in entries if isinstance(item.get("sequence"), int)]
        return (max(sequences) + 1) if sequences else len(entries)

    def _entries_from_source(self, source: str, payload: Any, spec: FlowTimelineSpec, start_sequence: int) -> list[dict[str, Any]]:
        items: list[tuple[str, dict[str, Any]]] = []
        if source in {"network_requests", "request_initiators"}:
            for item in self._items(payload):
                items.append(("network.request", item))
        elif source == "hook_timeline":
            snapshot = payload.get("snapshot", {}) if isinstance(payload, dict) else {}
            for item in self._items(snapshot.get("events") if isinstance(snapshot, dict) else payload):
                items.append((f"hook.{item.get('type', 'event')}", item))
        elif source == "function_hook_timeline":
            for item in self._items(payload.get("events") if isinstance(payload, dict) else payload):
                items.append((f"function_hook.{item.get('type', 'event')}", item))
        elif source == "module_hook_timeline":
            for item in self._items(payload.get("events") if isinstance(payload, dict) else payload):
                items.append((f"module_hook.{item.get('type', 'event')}", item))
        elif source == "debugger_timeline":
            for item in self._items(payload.get("entries") if isinstance(payload, dict) else payload):
                items.append((f"debugger.{item.get('type', 'event')}", item))
        elif source == "source_logpoint_timeline":
            for item in self._items(payload.get("events") if isinstance(payload, dict) else payload):
                items.append((f"source_logpoint.{item.get('type', 'event')}", item))
        elif source == "mutation_observer_timeline":
            for item in self._items(payload.get("records") if isinstance(payload, dict) else payload):
                items.append((f"mutation.{item.get('type', 'record')}", item))
        elif source == "replay_validation":
            for item in self._items(payload.get("validations") if isinstance(payload, dict) else payload):
                items.append(("replay.validation", item))
        else:
            for item in self._items(payload):
                items.append((f"{source}.event", item))
        return [self._entry_from_event(item, spec, source, start_sequence + index, event_type=event_type) for index, (event_type, item) in enumerate(items)]

    @staticmethod
    def _items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            if isinstance(value.get("items"), list):
                return [dict(item) for item in value["items"] if isinstance(item, dict)]
            if isinstance(value.get("events"), list):
                return [dict(item) for item in value["events"] if isinstance(item, dict)]
            return [dict(value)]
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        return []

    def _entry_from_event(self, event: dict[str, Any], spec: FlowTimelineSpec, source: str, sequence: int, *, event_type: str | None = None) -> dict[str, Any]:
        payload = self._safe_payload(event, spec.max_payload_preview_length)
        event_request_id = event.get("request_id", event.get("requestId", event.get("requestID")))
        request_id = event_request_id or spec.request_id
        return {
            "sequence": sequence,
            "flow_id": str(event.get("flow_id", event.get("flowId", spec.flow_id)) or spec.flow_id),
            "run_id": event.get("run_id", event.get("runId", spec.run_id)),
            "request_id": request_id,
            "source": source,
            "type": event_type or str(event.get("type", "event")),
            "timestamp": event.get("timestamp", event.get("ts")),
            "payload": payload,
            "correlation": self._correlation_hints(event, spec, request_id=event_request_id),
        }

    def _correlation_hints(self, event: dict[str, Any], spec: FlowTimelineSpec, *, request_id: Any = None) -> dict[str, Any]:
        """Extract conservative, machine-readable correlation hints.

        These hints are intentionally not matches.  They help later review or a
        separate stitching stage reason about likely request / hook / replay
        relationships without claiming automatic cross-request correlation.
        """

        resolved_request_id = request_id or self._first_string(
            event,
            (
                ("request_id",),
                ("requestId",),
                ("requestID",),
                ("id",),
                ("reqid",),
                ("payload", "request_id"),
                ("payload", "requestId"),
                ("payload", "requestID"),
                ("payload", "id"),
                ("payload", "reqid"),
                ("request", "requestId"),
                ("request", "request_id"),
            ),
        )
        url = self._first_string(
            event,
            (
                ("url",),
                ("name",),
                ("request", "url"),
                ("payload", "url"),
                ("payload", "name"),
                ("payload", "request", "url"),
                ("raw_runtime_result", "runtime_url"),
                ("payload", "raw_runtime_result", "runtime_url"),
                ("runtime_url",),
            ),
        )
        method = self._first_string(
            event,
            (
                ("method",),
                ("request", "method"),
                ("payload", "method"),
                ("payload", "request", "method"),
            ),
        )
        url_path = self._url_path(url)
        function_names = self._unique_strings(
            [
                *self._strings_for_paths(
                    event,
                    (
                        ("function_name",),
                        ("functionName",),
                        ("function",),
                        ("payload", "function_name"),
                        ("payload", "functionName"),
                        ("payload", "function"),
                        ("sample_output", "function_name"),
                        ("sample_output", "functionName"),
                    ),
                ),
                *self._callframe_function_names(event),
            ]
        )
        candidate_ids = self._unique_strings(
            self._strings_for_paths(
                event,
                (
                    ("candidate_id",),
                    ("candidateId",),
                    ("payload", "candidate_id"),
                    ("payload", "candidateId"),
                    ("raw_runtime_result", "candidate_id"),
                    ("raw_runtime_result", "candidateId"),
                ),
            )
        )
        hook_paths = self._unique_strings(
            self._strings_for_paths(
                event,
                (
                    ("path",),
                    ("hookPath",),
                    ("hook_path",),
                    ("callable_path",),
                    ("payload", "path"),
                    ("payload", "hookPath"),
                    ("payload", "hook_path"),
                    ("payload", "callable_path"),
                    ("sample_output", "callable_path"),
                    ("sample_output", "path"),
                    ("sample_output", "hookPath"),
                ),
            )
        )

        hints: list[str] = []
        correlation: dict[str, Any] = {}
        if resolved_request_id:
            request_id_text = str(resolved_request_id)
            correlation["request_id"] = request_id_text
            hints.append(f"request_id={request_id_text}")
        if url:
            correlation["url"] = url
            hints.append(f"url={url}")
        if url_path:
            correlation["url_path"] = url_path
            hints.append(f"url_path={url_path}")
        if method:
            method_text = method.upper()
            correlation["method"] = method_text
            hints.append(f"method={method_text}")
        if function_names:
            correlation["function_names"] = function_names
            hints.extend(f"function_name={name}" for name in function_names)
        if candidate_ids:
            correlation["candidate_ids"] = candidate_ids
            hints.extend(f"candidate_id={candidate_id}" for candidate_id in candidate_ids)
        if hook_paths:
            correlation["hook_paths"] = hook_paths
            hints.extend(f"hook_path={path}" for path in hook_paths)

        if resolved_request_id or url_path:
            confidence = "medium"
        elif function_names or candidate_ids or hook_paths:
            confidence = "low"
        else:
            confidence = "none"
        correlation["confidence"] = confidence
        correlation["hints"] = hints
        return correlation

    def _correlation_groups(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build conservative candidate groups from per-entry correlation hints.

        A group means "these entries share the same hint", not "these entries
        are proven to belong to the same full reverse flow".  Callers that need
        true stitching must add a separate matching / verification stage.
        """

        buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
        for entry in entries:
            correlation = entry.get("correlation")
            if not isinstance(correlation, dict):
                continue
            for strategy, key_data, confidence in self._group_candidates(correlation):
                group_key = (strategy, tuple(sorted(key_data.items())))
                bucket = buckets.setdefault(
                    group_key,
                    {
                        "strategy": strategy,
                        "key": dict(key_data),
                        "confidence": confidence,
                        "entry_sequences": [],
                        "entry_types": [],
                        "sources": [],
                        "hints": [],
                    },
                )
                sequence = entry.get("sequence")
                if sequence not in bucket["entry_sequences"]:
                    bucket["entry_sequences"].append(sequence)
                entry_type = entry.get("type")
                if entry_type and entry_type not in bucket["entry_types"]:
                    bucket["entry_types"].append(entry_type)
                source = entry.get("source")
                if source and source not in bucket["sources"]:
                    bucket["sources"].append(source)
                for hint in correlation.get("hints", []):
                    if isinstance(hint, str) and hint not in bucket["hints"]:
                        bucket["hints"].append(hint)

        priority = {"medium": 0, "low": 1, "none": 2}
        groups = [
            group
            for group in buckets.values()
            if len([sequence for sequence in group["entry_sequences"] if sequence is not None]) >= 2
        ]
        groups.sort(
            key=lambda group: (
                priority.get(str(group.get("confidence")), 9),
                str(group.get("strategy")),
                json.dumps(group.get("key", {}), ensure_ascii=False, sort_keys=True),
            )
        )
        for index, group in enumerate(groups, 1):
            group["group_id"] = f"cg-{index}"
            group["entry_count"] = len(group["entry_sequences"])
            group["stitching"] = False
            group["scope"] = "correlation-hints-only"
            group["verification"] = self._group_verification(group)
        return groups

    def _stitch_candidates(self, groups: list[dict[str, Any]], entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Promote reviewable correlation groups into manual stitch candidates.

        These candidates are intentionally conservative: they provide an
        ordered review path for humans or later review-gated agents, but they do
        not assert that the flow is stitched and they never enable automatic
        stitching.
        """

        entries_by_sequence = {entry.get("sequence"): entry for entry in entries}
        candidates: list[dict[str, Any]] = []
        allowed_statuses = {"reviewable", "ready_for_manual_stitch_review"}
        confidence_order = {"ready_for_manual_stitch_review": 0, "reviewable": 1}
        candidate_groups = []
        for group in groups:
            verification = group.get("verification") if isinstance(group.get("verification"), dict) else {}
            status = str(verification.get("status") or "weak")
            if status not in allowed_statuses:
                continue
            candidate_groups.append((confidence_order.get(status, 9), group))
        candidate_groups.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("group_id")),
                str(item[1].get("strategy")),
            )
        )
        for index, (_rank, group) in enumerate(candidate_groups, 1):
            verification = group.get("verification") if isinstance(group.get("verification"), dict) else {}
            path = []
            for sequence in group.get("entry_sequences", []):
                entry = entries_by_sequence.get(sequence)
                if not isinstance(entry, dict):
                    continue
                path.append(
                    {
                        "sequence": entry.get("sequence"),
                        "source": entry.get("source"),
                        "type": entry.get("type"),
                        "request_id": entry.get("request_id"),
                        "correlation": entry.get("correlation") if isinstance(entry.get("correlation"), dict) else {},
                    }
                )
            evidence = verification.get("evidence") if isinstance(verification.get("evidence"), dict) else {}
            readiness = str(verification.get("status") or "reviewable")
            candidates.append(
                {
                    "candidate_id": f"stitch-{index}",
                    "group_id": group.get("group_id"),
                    "strategy": group.get("strategy"),
                    "key": group.get("key", {}),
                    "readiness": readiness,
                    "confidence": "medium" if readiness == "ready_for_manual_stitch_review" else "low",
                    "entry_sequences": list(group.get("entry_sequences", [])),
                    "entry_types": list(group.get("entry_types", [])),
                    "sources": list(group.get("sources", [])),
                    "path": path,
                    "path_length": len(path),
                    "evidence": evidence,
                    "missing_for_ready": list(verification.get("missing_for_ready", [])) if isinstance(verification.get("missing_for_ready"), list) else [],
                    "reasons": list(verification.get("reasons", [])) if isinstance(verification.get("reasons"), list) else [],
                    "next_action": "manual_stitch_review" if readiness == "ready_for_manual_stitch_review" else "collect_missing_evidence_or_review_manually",
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "manual-stitch-candidate-only",
                }
            )
        return candidates

    @classmethod
    def _auto_stitch_dry_runs(cls, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score stitch candidates without materializing or applying them.

        This is intentionally a dry-run layer.  It gives later review agents or
        humans a deterministic score and conflict summary, but it never flips
        ``automatic_stitching`` to true and never creates stitched flows.
        """

        dry_runs: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates, 1):
            evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
            missing_for_ready = list(candidate.get("missing_for_ready", [])) if isinstance(candidate.get("missing_for_ready"), list) else []
            conflict_reasons = cls._auto_stitch_conflict_reasons(candidate, candidates)
            confidence_score, score_reasons = cls._auto_stitch_confidence_score(candidate, evidence, missing_for_ready)
            confidence = "high" if confidence_score >= 0.85 else "medium" if confidence_score >= 0.6 else "low"
            blockers = ["dry_run_only", "review_required", "automatic_application_disabled"]
            blockers.extend(f"missing_{name}" for name in missing_for_ready)
            blockers.extend(conflict_reasons)
            dry_runs.append(
                {
                    "dry_run_id": f"auto-stitch-dry-run-{index}",
                    "candidate_id": candidate.get("candidate_id"),
                    "group_id": candidate.get("group_id"),
                    "strategy": candidate.get("strategy"),
                    "key": candidate.get("key", {}) if isinstance(candidate.get("key"), dict) else {},
                    "readiness": candidate.get("readiness"),
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "score_reasons": score_reasons,
                    "entry_sequences": list(candidate.get("entry_sequences", [])) if isinstance(candidate.get("entry_sequences"), list) else [],
                    "entry_types": list(candidate.get("entry_types", [])) if isinstance(candidate.get("entry_types"), list) else [],
                    "sources": list(candidate.get("sources", [])) if isinstance(candidate.get("sources"), list) else [],
                    "path_length": candidate.get("path_length", 0),
                    "supporting_evidence": evidence,
                    "missing_for_ready": missing_for_ready,
                    "conflict_reasons": conflict_reasons,
                    "blocking_conditions": cls._unique_strings(blockers),
                    "review_required": True,
                    "would_materialize": False,
                    "dry_run": True,
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "auto-stitch-dry-run-only",
                    "next_action": "review_auto_stitch_dry_run_before_materialization",
                }
            )
        return dry_runs

    @classmethod
    def _auto_stitch_confidence_score(
        cls,
        candidate: dict[str, Any],
        evidence: dict[str, Any],
        missing_for_ready: list[str],
    ) -> tuple[float, list[str]]:
        score = 0.15
        reasons = ["base_candidate_score"]
        readiness = str(candidate.get("readiness") or "")
        if readiness == "ready_for_manual_stitch_review":
            score += 0.2
            reasons.append("readiness=ready_for_manual_stitch_review")
        elif readiness == "reviewable":
            score += 0.1
            reasons.append("readiness=reviewable")
        weights = {
            "request_initiator": 0.2,
            "runtime_hook": 0.2,
            "replay_validation": 0.2,
            "network_request": 0.05,
            "debugger": 0.05,
            "source_logpoint": 0.05,
            "mutation": 0.03,
        }
        for key, weight in weights.items():
            if evidence.get(key):
                score += weight
                reasons.append(f"evidence={key}")
        path_length = candidate.get("path_length")
        if isinstance(path_length, int) and path_length >= 3:
            score += 0.05
            reasons.append("path_length>=3")
        if missing_for_ready:
            score -= min(0.3, 0.1 * len(missing_for_ready))
            reasons.append(f"missing_for_ready={','.join(missing_for_ready)}")
        score = max(0.0, min(1.0, score))
        return round(score, 2), reasons

    @classmethod
    def _auto_stitch_conflict_reasons(cls, candidate: dict[str, Any], candidates: list[dict[str, Any]]) -> list[str]:
        conflicts: list[str] = []
        candidate_id = candidate.get("candidate_id")
        strategy = candidate.get("strategy")
        sequences = {item for item in candidate.get("entry_sequences", []) if item is not None} if isinstance(candidate.get("entry_sequences"), list) else set()
        for other in candidates:
            if other.get("candidate_id") == candidate_id:
                continue
            other_sequences = {item for item in other.get("entry_sequences", []) if item is not None} if isinstance(other.get("entry_sequences"), list) else set()
            overlap = sorted(sequences.intersection(other_sequences))
            if overlap:
                conflicts.append(f"overlaps_with_{other.get('candidate_id')}:{','.join(str(item) for item in overlap)}")
            if other.get("strategy") == strategy and other.get("key") != candidate.get("key"):
                conflicts.append(f"same_strategy_alternative={other.get('candidate_id')}")
        return cls._unique_strings(conflicts)

    @classmethod
    def _auto_stitch_conflict_resolutions(
        cls,
        dry_runs: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build conservative, review-only conflict resolution records.

        The resolver is intentionally non-authoritative: it can identify a
        deterministic review-preferred candidate for a conflict set, but it
        never marks conflicts as applied, never materializes a stitched flow,
        and never enables automatic stitching.
        """

        dry_runs_by_candidate_id = {str(item.get("candidate_id")): item for item in dry_runs if item.get("candidate_id")}
        candidates_by_id = {str(item.get("candidate_id")): item for item in candidates if item.get("candidate_id")}
        resolutions: list[dict[str, Any]] = []
        for index, dry_run in enumerate(dry_runs, 1):
            candidate_id = str(dry_run.get("candidate_id") or "")
            candidate = candidates_by_id.get(candidate_id, {})
            conflict_reasons = cls._string_values(dry_run.get("conflict_reasons"))
            related_candidate_ids = cls._related_conflict_candidate_ids(candidate_id, conflict_reasons)
            cohort_ids = [item for item in related_candidate_ids if item in dry_runs_by_candidate_id]
            selected_candidate_id = cls._review_preferred_candidate_id(cohort_ids, dry_runs_by_candidate_id) if conflict_reasons else candidate_id or None
            alternative_candidate_ids = [item for item in cohort_ids if item != selected_candidate_id]
            unresolved_conflicts = conflict_reasons
            status = "review_required" if unresolved_conflicts else "no_conflict"
            strategy = "prefer_highest_confidence_review_required" if unresolved_conflicts else "no_conflict"
            resolutions.append(
                {
                    "resolution_id": f"auto-stitch-conflict-resolution-{index}",
                    "candidate_id": candidate_id or None,
                    "dry_run_id": dry_run.get("dry_run_id"),
                    "group_id": dry_run.get("group_id"),
                    "status": status,
                    "strategy": strategy,
                    "conflict_reasons": conflict_reasons,
                    "resolved_conflicts": [],
                    "unresolved_conflicts": unresolved_conflicts,
                    "selected_candidate_id": selected_candidate_id,
                    "alternative_candidate_ids": alternative_candidate_ids,
                    "related_candidate_ids": cohort_ids,
                    "entry_sequences": cls._integer_values(candidate.get("entry_sequences")),
                    "confidence_score": float(dry_run.get("confidence_score") or 0.0),
                    "review_required": bool(unresolved_conflicts),
                    "would_materialize": False,
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "auto-stitch-conflict-resolution-baseline",
                    "next_action": "review_conflict_resolution_before_materialization" if unresolved_conflicts else "continue_policy_review",
                }
            )
        return resolutions

    @classmethod
    def _auto_stitch_conflict_resolution_summary(cls, resolutions: list[dict[str, Any]]) -> dict[str, Any]:
        conflict_count = sum(1 for item in resolutions if item.get("conflict_reasons"))
        no_conflict_count = sum(1 for item in resolutions if not item.get("conflict_reasons"))
        unresolved_count = sum(1 for item in resolutions if item.get("unresolved_conflicts"))
        return {
            "resolution_count": len(resolutions),
            "conflict_count": conflict_count,
            "no_conflict_count": no_conflict_count,
            "resolved_by_policy_count": 0,
            "unresolved_count": unresolved_count,
            "review_required": bool(conflict_count),
            "would_materialize": False,
            "automatic_stitching": False,
            "stitching": False,
            "scope": "auto-stitch-conflict-resolution-summary",
            "next_action": "review_conflict_resolutions_before_materialization" if conflict_count else "continue_policy_review",
        }

    @classmethod
    def _related_conflict_candidate_ids(cls, candidate_id: str, conflict_reasons: list[str]) -> list[str]:
        candidate_ids = [candidate_id] if candidate_id else []
        for reason in conflict_reasons:
            if reason.startswith("overlaps_with_"):
                remainder = reason[len("overlaps_with_") :]
                other_id = remainder.split(":", 1)[0]
                if other_id:
                    candidate_ids.append(other_id)
            elif reason.startswith("same_strategy_alternative="):
                other_id = reason.split("=", 1)[1]
                if other_id:
                    candidate_ids.append(other_id)
        return cls._unique_strings(candidate_ids)

    @staticmethod
    def _review_preferred_candidate_id(
        candidate_ids: list[str],
        dry_runs_by_candidate_id: dict[str, dict[str, Any]],
    ) -> str | None:
        if not candidate_ids:
            return None

        def sort_key(candidate_id: str) -> tuple[float, int, str]:
            dry_run = dry_runs_by_candidate_id.get(candidate_id, {})
            try:
                score = float(dry_run.get("confidence_score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            path_length = int(dry_run.get("path_length") or 0)
            return (score, path_length, candidate_id)

        return sorted(candidate_ids, key=sort_key, reverse=True)[0]

    @staticmethod
    def _integer_values(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        integers: list[int] = []
        for item in value:
            if isinstance(item, int):
                integers.append(item)
        return integers


    @classmethod
    def _auto_stitch_policy_decisions(
        cls,
        dry_runs: list[dict[str, Any]],
        policy: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate dry-run records against a conservative auto-stitch policy.

        This prepares a future materialization gate without applying it.  Even
        when a dry-run is high confidence, the current baseline keeps
        ``would_materialize`` false and routes the item to review-gated
        materialization.
        """

        policy = policy or {}
        min_score = cls._float_policy_value(policy, "min_confidence_score", "minConfidenceScore", default=0.85)
        allow_conflicts = cls._bool_policy_value(policy, "allow_conflicts", "allowConflicts", default=False)
        require_review = cls._bool_policy_value(policy, "require_review_approval", "requireReviewApproval", default=True)
        automatic_requested = cls._bool_policy_value(
            policy,
            "enable_automatic_materialization",
            "enableAutomaticMaterialization",
            "automatic_materialization_enabled",
            "automaticMaterializationEnabled",
            default=False,
        )
        decisions: list[dict[str, Any]] = []
        for index, dry_run in enumerate(dry_runs, 1):
            confidence_score = float(dry_run.get("confidence_score") or 0.0)
            conflict_reasons = cls._string_values(dry_run.get("conflict_reasons"))
            missing_for_ready = cls._string_values(dry_run.get("missing_for_ready"))
            blockers: list[str] = ["review_required" if require_review else "policy_review_not_required_but_baseline_review_gate_still_required"]
            reasons: list[str] = []
            if confidence_score >= min_score:
                reasons.append("confidence_score_meets_policy_threshold")
            else:
                blockers.append("confidence_score_below_policy_threshold")
                reasons.append("confidence_score_below_policy_threshold")
            if missing_for_ready:
                blockers.extend(f"missing_{name}" for name in missing_for_ready)
                reasons.append("missing_ready_evidence")
            if conflict_reasons and not allow_conflicts:
                blockers.append("conflict_review_required")
                reasons.append("conflict_reasons_present")
            if automatic_requested:
                blockers.append("automatic_materialization_not_implemented")
                reasons.append("automatic_materialization_requested_but_not_implemented")
            else:
                blockers.append("automatic_materialization_disabled")
                reasons.append("automatic_materialization_disabled")
            eligible_for_review_gate = confidence_score >= min_score and not missing_for_ready and (allow_conflicts or not conflict_reasons)
            status = "ready_for_review_gate" if eligible_for_review_gate else "blocked"
            decisions.append(
                {
                    "decision_id": f"auto-stitch-policy-decision-{index}",
                    "dry_run_id": dry_run.get("dry_run_id"),
                    "candidate_id": dry_run.get("candidate_id"),
                    "group_id": dry_run.get("group_id"),
                    "status": status,
                    "eligible_for_review_gate": eligible_for_review_gate,
                    "confidence_score": confidence_score,
                    "min_confidence_score": min_score,
                    "conflict_reasons": conflict_reasons,
                    "missing_for_ready": missing_for_ready,
                    "policy_reasons": cls._unique_strings(reasons),
                    "policy_blocking_conditions": cls._unique_strings(blockers),
                    "review_required": True,
                    "would_materialize": False,
                    "automatic_materialization_requested": automatic_requested,
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "auto-stitch-policy-decision-only",
                    "next_action": "review_policy_eligible_candidate_before_materialization" if eligible_for_review_gate else "collect_missing_evidence_or_resolve_policy_blockers",
                }
            )
        return decisions

    @classmethod
    def _auto_stitch_policy_summary(
        cls,
        decisions: list[dict[str, Any]],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = policy or {}
        eligible_count = sum(1 for item in decisions if item.get("eligible_for_review_gate"))
        blocked_count = len(decisions) - eligible_count
        return {
            "policy_id": str(policy.get("policy_id") or policy.get("policyId") or "default-conservative-auto-stitch-policy"),
            "decision_count": len(decisions),
            "eligible_for_review_gate_count": eligible_count,
            "blocked_count": blocked_count,
            "automatic_materialization_enabled": False,
            "automatic_stitching": False,
            "would_materialize": False,
            "review_required": True,
            "scope": "auto-stitch-policy-summary-only",
            "next_action": "review_policy_decisions_before_enabling_materialization" if decisions else "collect_reviewable_stitch_candidates",
        }

    @staticmethod
    def _float_policy_value(policy: dict[str, Any], *keys: str, default: float) -> float:
        for key in keys:
            if key not in policy:
                continue
            try:
                return float(policy[key])
            except (TypeError, ValueError):
                return default
        return default

    @staticmethod
    def _bool_policy_value(policy: dict[str, Any], *keys: str, default: bool) -> bool:
        for key in keys:
            if key not in policy:
                continue
            value = policy[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"1", "true", "yes", "on", "enabled"}:
                    return True
                if normalized in {"0", "false", "no", "off", "disabled"}:
                    return False
            if isinstance(value, (int, float)):
                return bool(value)
        return default


    @classmethod
    def _auto_stitch_materialization_plans(
        cls,
        decisions: list[dict[str, Any]],
        dry_runs: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        conflict_resolutions: list[dict[str, Any]],
        policy: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build plan-only materialization proposals for policy-eligible decisions.

        The returned records describe how a future materializer would write a
        stitched flow after review.  They deliberately do not write artifacts,
        do not flip ``stitching`` to true, and do not replace reviewer-approved
        ``stitch_review_decisions``.
        """

        policy = policy or {}
        plan_enabled = cls._bool_policy_value(policy, "enable_materialization_plan", "enableMaterializationPlan", default=True)
        if not plan_enabled:
            return []
        dry_runs_by_id = {dry_run.get("dry_run_id"): dry_run for dry_run in dry_runs}
        candidates_by_id = {candidate.get("candidate_id"): candidate for candidate in candidates}
        conflict_resolutions_by_candidate_id = {item.get("candidate_id"): item for item in conflict_resolutions}
        plans: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.get("status") != "ready_for_review_gate" or not decision.get("eligible_for_review_gate"):
                continue
            dry_run = dry_runs_by_id.get(decision.get("dry_run_id"), {})
            candidate = candidates_by_id.get(decision.get("candidate_id"), {})
            conflict_resolution = conflict_resolutions_by_candidate_id.get(decision.get("candidate_id"), {})
            conflict_reasons = cls._string_values(decision.get("conflict_reasons"))
            entry_sequences = list(candidate.get("entry_sequences", [])) if isinstance(candidate.get("entry_sequences"), list) else []
            plans.append(
                {
                    "plan_id": f"auto-stitch-materialization-plan-{len(plans) + 1}",
                    "decision_id": decision.get("decision_id"),
                    "dry_run_id": decision.get("dry_run_id"),
                    "candidate_id": decision.get("candidate_id"),
                    "group_id": decision.get("group_id"),
                    "status": "plan_ready_for_review",
                    "materialization_mode": "plan_only",
                    "target_artifact": "workspace/stitched-flow.json",
                    "virtual_target_artifact": "virtual://workspace/stitched-flow.json",
                    "entry_sequences": entry_sequences,
                    "entry_count": len(entry_sequences),
                    "path": list(candidate.get("path", [])) if isinstance(candidate.get("path"), list) else [],
                    "path_length": int(candidate.get("path_length") or dry_run.get("path_length") or 0),
                    "confidence_score": decision.get("confidence_score"),
                    "confidence": dry_run.get("confidence"),
                    "evidence": dict(candidate.get("evidence", {})) if isinstance(candidate.get("evidence"), dict) else {},
                    "conflict_resolution": {
                        "resolution_id": conflict_resolution.get("resolution_id"),
                        "strategy": "policy_allowed_conflicts_review_required" if conflict_reasons else "none_required",
                        "unresolved_conflicts": conflict_reasons,
                        "selected_candidate_id": conflict_resolution.get("selected_candidate_id", decision.get("candidate_id")),
                        "alternative_candidate_ids": list(conflict_resolution.get("alternative_candidate_ids", []))
                        if isinstance(conflict_resolution.get("alternative_candidate_ids"), list)
                        else [],
                        "review_required": bool(conflict_reasons),
                    },
                    "review_requirements": [
                        "approve_auto_stitch_materialization_plan",
                        "confirm_entry_order_matches_observed_runtime_flow",
                        "confirm_conflict_resolution_is_acceptable",
                        "confirm_replay_validation_matches_original_request_semantics",
                    ],
                    "rollback_plan": {
                        "strategy": "do_not_write_until_reviewed",
                        "revert_artifact": "workspace/stitched-flow.json",
                        "audit_artifact": "workspace/flow-timeline.json",
                    },
                    "policy_blocking_conditions": cls._unique_strings(
                        [*cls._string_values(decision.get("policy_blocking_conditions")), "missing_materialization_reviewer_approval"]
                    ),
                    "review_required": True,
                    "would_materialize": False,
                    "writes_artifact": False,
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "auto-stitch-materialization-plan-only",
                    "next_action": "review_materialization_plan_before_enabling_stitched_flow_write",
                }
            )
        return plans

    @classmethod
    def _auto_stitch_materialization_summary(
        cls,
        plans: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        policy = policy or {}
        eligible_decision_count = sum(1 for decision in decisions if decision.get("eligible_for_review_gate"))
        return {
            "plan_count": len(plans),
            "eligible_decision_count": eligible_decision_count,
            "blocked_decision_count": max(0, len(decisions) - eligible_decision_count),
            "plan_generation_enabled": cls._bool_policy_value(policy, "enable_materialization_plan", "enableMaterializationPlan", default=True),
            "materialization_enabled": False,
            "writes_artifact": False,
            "would_materialize": False,
            "automatic_stitching": False,
            "review_required": True,
            "scope": "auto-stitch-materialization-summary-only",
            "next_action": "review_materialization_plans" if plans else "collect_policy_eligible_stitch_decisions",
        }

    def _apply_materialization_review_decisions(
        self,
        plans: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not decisions:
            return plans
        output: list[dict[str, Any]] = []
        for plan in plans:
            next_plan = dict(plan)
            decision = self._matching_materialization_review_decision(next_plan, decisions)
            if decision is not None:
                next_plan = self._materialization_plan_with_review_decision(next_plan, decision)
            output.append(next_plan)
        return output

    @staticmethod
    def _matching_materialization_review_decision(
        plan: dict[str, Any],
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            if decision.get("plan_id") and decision.get("plan_id") == plan.get("plan_id"):
                return decision
            if decision.get("planId") and decision.get("planId") == plan.get("plan_id"):
                return decision
            if decision.get("decision_id") and decision.get("decision_id") == plan.get("decision_id"):
                return decision
            if decision.get("decisionId") and decision.get("decisionId") == plan.get("decision_id"):
                return decision
            if decision.get("candidate_id") and decision.get("candidate_id") == plan.get("candidate_id"):
                return decision
            if decision.get("candidateId") and decision.get("candidateId") == plan.get("candidate_id"):
                return decision
            if decision.get("group_id") and decision.get("group_id") == plan.get("group_id"):
                return decision
            if decision.get("groupId") and decision.get("groupId") == plan.get("group_id"):
                return decision
        return None

    @classmethod
    def _materialization_plan_with_review_decision(
        cls,
        plan: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        next_plan = dict(plan)
        status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
        approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
        rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
        review_decision = {
            "status": "approved" if approved else "rejected" if rejected else status or "pending_review",
            "approved": approved and not rejected,
            "review_required": not approved,
            "review_gate": "auto_stitch_materialization_review_decision",
        }
        for key in ("reviewer", "reviewed_by", "reviewedBy", "reviewed_at", "reviewedAt", "reason", "notes"):
            if decision.get(key) is not None:
                review_decision[key] = decision.get(key)
        next_plan["review_decision"] = review_decision
        next_plan["review_decision_input"] = dict(decision)
        if approved and not rejected:
            review_resolved_blockers = {
                "missing_materialization_reviewer_approval",
                "review_required",
                "policy_review_not_required_but_baseline_review_gate_still_required",
                "automatic_materialization_disabled",
                "automatic_materialization_not_implemented",
            }
            next_plan["status"] = "approved_for_materialization"
            next_plan["materialization_mode"] = "review_approved_plan"
            next_plan["blocking_conditions"] = []
            next_plan["policy_blocking_conditions"] = [
                condition
                for condition in cls._string_values(next_plan.get("policy_blocking_conditions"))
                if condition not in review_resolved_blockers
            ]
            next_plan["review_required"] = False
            next_plan["next_action"] = "materialize_review_approved_auto_stitch_plan"
            next_plan["scope"] = "review-approved-auto-stitch-materialization-plan"
        elif rejected:
            next_plan["status"] = "rejected"
            next_plan["blocking_conditions"] = cls._unique_strings(
                [*cls._string_values(next_plan.get("blocking_conditions")), "materialization_reviewer_rejected"]
            )
            next_plan["policy_blocking_conditions"] = cls._unique_strings(
                [*cls._string_values(next_plan.get("policy_blocking_conditions")), "materialization_reviewer_rejected"]
            )
            next_plan["next_action"] = "collect_more_evidence_or_revise_materialization_plan"
        return next_plan

    @classmethod
    def _auto_stitch_materialization_results(
        cls,
        plans: list[dict[str, Any]],
        entries: list[dict[str, Any]],
        *,
        existing_stitched_flows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        entries_by_sequence = {entry.get("sequence"): entry for entry in entries}
        existing_candidate_ids = {
            flow.get("candidate_id")
            for flow in existing_stitched_flows or []
            if isinstance(flow, dict) and flow.get("candidate_id")
        }
        results: list[dict[str, Any]] = []
        for plan in plans:
            review_decision = plan.get("review_decision") if isinstance(plan.get("review_decision"), dict) else {}
            if review_decision.get("status") != "approved" or not review_decision.get("approved"):
                continue
            candidate_id = plan.get("candidate_id")
            if candidate_id in existing_candidate_ids:
                results.append(
                    {
                        "result_id": f"auto-stitch-materialization-result-{len(results) + 1}",
                        "plan_id": plan.get("plan_id"),
                        "decision_id": plan.get("decision_id"),
                        "candidate_id": candidate_id,
                        "group_id": plan.get("group_id"),
                        "status": "skipped_duplicate",
                        "reason": "candidate_already_materialized_by_stitch_review_decision",
                        "review_decision": review_decision,
                        "materialized": False,
                        "writes_artifact": False,
                        "would_materialize": False,
                        "automatic_stitching": False,
                        "stitching": False,
                        "scope": "review-approved-auto-stitch-materialization-baseline",
                        "next_action": "inspect_existing_stitched_flow",
                    }
                )
                continue
            entry_sequences = list(plan.get("entry_sequences", [])) if isinstance(plan.get("entry_sequences"), list) else []
            entry_types = [
                entries_by_sequence[sequence].get("type")
                for sequence in entry_sequences
                if isinstance(entries_by_sequence.get(sequence), dict)
            ]
            sources = [
                entries_by_sequence[sequence].get("source")
                for sequence in entry_sequences
                if isinstance(entries_by_sequence.get(sequence), dict)
            ]
            result_id = f"auto-stitch-materialization-result-{len(results) + 1}"
            results.append(
                {
                    "result_id": result_id,
                    "transaction_id": f"auto-stitch-materialization-txn-{len(results) + 1}",
                    "plan_id": plan.get("plan_id"),
                    "decision_id": plan.get("decision_id"),
                    "dry_run_id": plan.get("dry_run_id"),
                    "candidate_id": candidate_id,
                    "group_id": plan.get("group_id"),
                    "status": "materialized",
                    "materialization_mode": "review_approved_plan",
                    "target_artifact": plan.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": plan.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "entry_sequences": entry_sequences,
                    "entry_count": len(entry_sequences),
                    "entry_types": cls._unique_strings(entry_types),
                    "sources": cls._unique_strings(sources),
                    "path": list(plan.get("path", [])) if isinstance(plan.get("path"), list) else [],
                    "path_length": int(plan.get("path_length") or 0),
                    "confidence": plan.get("confidence"),
                    "confidence_score": plan.get("confidence_score"),
                    "evidence": dict(plan.get("evidence", {})) if isinstance(plan.get("evidence"), dict) else {},
                    "conflict_resolution": dict(plan.get("conflict_resolution", {})) if isinstance(plan.get("conflict_resolution"), dict) else {},
                    "review_decision": review_decision,
                    "review_decision_input": dict(plan.get("review_decision_input", {})) if isinstance(plan.get("review_decision_input"), dict) else {},
                    "audit": {
                        "source_plan_id": plan.get("plan_id"),
                        "source_decision_id": plan.get("decision_id"),
                        "review_gate": "auto_stitch_materialization_review_decision",
                        "artifact_write_intent": "stitched-flow.json",
                    },
                    "rollback_plan": {
                        **(dict(plan.get("rollback_plan", {})) if isinstance(plan.get("rollback_plan"), dict) else {}),
                        "strategy": "manual_revert_review_approved_materialization",
                    },
                    "materialized": True,
                    "writes_artifact": True,
                    "would_materialize": True,
                    "review_required": False,
                    "automatic_stitching": False,
                    "stitching": True,
                    "source": "review_approved_auto_stitch_materialization_plan",
                    "scope": "review-approved-auto-stitch-materialization-baseline",
                    "limitations": [
                        "review_approved_not_fully_automatic",
                        "conflict_resolution_policy_baseline",
                        "no_full_browser_event_subscription",
                    ],
                    "next_action": "inspect_materialized_stitched_flow_and_audit",
                }
            )
        return results

    @classmethod
    def _stitched_flows_from_materialization_results(
        cls,
        results: list[dict[str, Any]],
        *,
        existing_count: int = 0,
    ) -> list[dict[str, Any]]:
        stitched: list[dict[str, Any]] = []
        for result in results:
            if result.get("status") != "materialized" or not result.get("materialized"):
                continue
            stitched.append(
                {
                    "stitched_flow_id": f"stitched-flow-{existing_count + len(stitched) + 1}",
                    "materialization_result_id": result.get("result_id"),
                    "plan_id": result.get("plan_id"),
                    "decision_id": result.get("decision_id"),
                    "candidate_id": result.get("candidate_id"),
                    "group_id": result.get("group_id"),
                    "confidence": result.get("confidence", "medium"),
                    "confidence_score": result.get("confidence_score"),
                    "status": "approved",
                    "entry_sequences": list(result.get("entry_sequences", [])) if isinstance(result.get("entry_sequences"), list) else [],
                    "entry_count": int(result.get("entry_count") or 0),
                    "entry_types": list(result.get("entry_types", [])) if isinstance(result.get("entry_types"), list) else [],
                    "sources": list(result.get("sources", [])) if isinstance(result.get("sources"), list) else [],
                    "path": list(result.get("path", [])) if isinstance(result.get("path"), list) else [],
                    "path_length": int(result.get("path_length") or 0),
                    "evidence": dict(result.get("evidence", {})) if isinstance(result.get("evidence"), dict) else {},
                    "conflict_resolution": dict(result.get("conflict_resolution", {})) if isinstance(result.get("conflict_resolution"), dict) else {},
                    "review_decision": dict(result.get("review_decision", {})) if isinstance(result.get("review_decision"), dict) else {},
                    "source": "review_approved_auto_stitch_materialization_plan",
                    "scope": "review-approved-auto-stitch-materialization-baseline",
                    "stitching": True,
                    "automatic_stitching": False,
                    "limitations": list(result.get("limitations", [])) if isinstance(result.get("limitations"), list) else [],
                    "next_action": "inspect_materialized_stitched_flow_and_audit",
                }
            )
        return stitched

    @classmethod
    def _auto_stitch_materialization_result_summary(
        cls,
        results: list[dict[str, Any]],
        review_decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        materialized_count = sum(1 for result in results if result.get("status") == "materialized")
        duplicate_count = sum(1 for result in results if result.get("status") == "skipped_duplicate")
        approved_count = 0
        rejected_count = 0
        pending_count = 0
        for decision in review_decisions:
            if not isinstance(decision, dict):
                continue
            status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
            approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
            rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
            if approved and not rejected:
                approved_count += 1
            elif rejected:
                rejected_count += 1
            else:
                pending_count += 1
        return {
            "result_count": len(results),
            "materialized_count": materialized_count,
            "duplicate_skipped_count": duplicate_count,
            "review_decision_count": len(review_decisions),
            "approved_review_decision_count": approved_count,
            "rejected_review_decision_count": rejected_count,
            "pending_review_decision_count": pending_count,
            "materialization_enabled": bool(materialized_count),
            "writes_artifact": bool(materialized_count),
            "would_materialize": bool(materialized_count),
            "automatic_stitching": False,
            "review_required": not bool(materialized_count),
            "scope": "review-approved-auto-stitch-materialization-result-summary",
            "next_action": "inspect_materialized_stitched_flow_and_audit" if materialized_count else "review_materialization_plans",
        }

    @classmethod
    def _auto_stitch_materialization_audit_entries(
        cls,
        results: list[dict[str, Any]],
        spec: FlowTimelineSpec,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for result in results:
            if result.get("status") != "materialized" or not result.get("materialized"):
                continue
            audit_id = f"stitched-flow-materialization-audit-{len(entries) + 1}"
            transaction_id = str(result.get("transaction_id") or f"auto-stitch-materialization-txn-{len(entries) + 1}")
            review_decision = result.get("review_decision") if isinstance(result.get("review_decision"), dict) else {}
            entries.append(
                {
                    "audit_id": audit_id,
                    "transaction_id": transaction_id,
                    "result_id": result.get("result_id"),
                    "plan_id": result.get("plan_id"),
                    "decision_id": result.get("decision_id"),
                    "dry_run_id": result.get("dry_run_id"),
                    "candidate_id": result.get("candidate_id"),
                    "group_id": result.get("group_id"),
                    "flow_id": spec.flow_id,
                    "run_id": spec.run_id,
                    "status": "audit_ready",
                    "operation": "write_stitched_flow",
                    "operation_mode": "review_approved_materialization",
                    "target_artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": result.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "audit_artifact": "workspace/stitched-flow-materialization-audit.json",
                    "virtual_audit_artifact": "virtual://workspace/stitched-flow-materialization-audit.json",
                    "rollback_artifact": "workspace/stitched-flow-rollback-plan.json",
                    "virtual_rollback_artifact": "virtual://workspace/stitched-flow-rollback-plan.json",
                    "entry_sequences": list(result.get("entry_sequences", [])) if isinstance(result.get("entry_sequences"), list) else [],
                    "entry_count": int(result.get("entry_count") or 0),
                    "entry_types": list(result.get("entry_types", [])) if isinstance(result.get("entry_types"), list) else [],
                    "sources": list(result.get("sources", [])) if isinstance(result.get("sources"), list) else [],
                    "path_length": int(result.get("path_length") or 0),
                    "confidence": result.get("confidence"),
                    "confidence_score": result.get("confidence_score"),
                    "review": {
                        "status": review_decision.get("status"),
                        "approved": bool(review_decision.get("approved")),
                        "reviewer": review_decision.get("reviewer") or review_decision.get("reviewed_by") or review_decision.get("reviewedBy"),
                        "reviewed_at": review_decision.get("reviewed_at") or review_decision.get("reviewedAt"),
                        "reason": review_decision.get("reason"),
                    },
                    "conflict_resolution": dict(result.get("conflict_resolution", {})) if isinstance(result.get("conflict_resolution"), dict) else {},
                    "preconditions": [
                        "auto_stitch_materialization_plan_exists",
                        "explicit_materialization_review_approved",
                        "target_entries_present_in_flow_timeline",
                        "automatic_stitching_remains_disabled",
                    ],
                    "postconditions": [
                        "stitched_flow_baseline_contains_materialization_result_id",
                        "audit_record_written_before_delivery_use",
                        "rollback_plan_available_for_manual_revert",
                    ],
                    "invariants": {
                        "automatic_stitching": False,
                        "review_approval_required": True,
                        "writes_artifact_requires_audit": True,
                    },
                    "writes_artifact": True,
                    "would_materialize": True,
                    "automatic_stitching": False,
                    "stitching": True,
                    "scope": "stitched-flow-materialization-audit-baseline",
                    "next_action": "inspect_rollback_plan_before_using_materialized_flow",
                }
            )
        return entries

    @staticmethod
    def _auto_stitch_materialization_audit_summary(
        audit_entries: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        materialized_result_count = sum(1 for result in results if result.get("status") == "materialized")
        audited_result_ids = {
            entry.get("result_id")
            for entry in audit_entries
            if isinstance(entry, dict) and entry.get("result_id")
        }
        return {
            "audit_count": len(audit_entries),
            "materialized_result_count": materialized_result_count,
            "audited_result_count": len(audited_result_ids),
            "missing_audit_count": max(0, materialized_result_count - len(audited_result_ids)),
            "transaction_count": len({entry.get("transaction_id") for entry in audit_entries if entry.get("transaction_id")}),
            "audit_artifact": "workspace/stitched-flow-materialization-audit.json",
            "virtual_audit_artifact": "virtual://workspace/stitched-flow-materialization-audit.json",
            "writes_artifact": bool(audit_entries),
            "automatic_stitching": False,
            "review_required": not bool(audit_entries),
            "scope": "stitched-flow-materialization-audit-summary",
            "next_action": "inspect_rollback_plans" if audit_entries else "materialize_review_approved_plan_before_audit",
        }

    @classmethod
    def _auto_stitch_materialization_rollback_plans(
        cls,
        results: list[dict[str, Any]],
        audit_entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        audits_by_result_id = {entry.get("result_id"): entry for entry in audit_entries if isinstance(entry, dict)}
        plans: list[dict[str, Any]] = []
        for result in results:
            if result.get("status") != "materialized" or not result.get("materialized"):
                continue
            audit = audits_by_result_id.get(result.get("result_id"), {})
            rollback_id = f"stitched-flow-rollback-plan-{len(plans) + 1}"
            transaction_id = result.get("transaction_id") or audit.get("transaction_id")
            plans.append(
                {
                    "rollback_id": rollback_id,
                    "transaction_id": transaction_id,
                    "audit_id": audit.get("audit_id"),
                    "result_id": result.get("result_id"),
                    "plan_id": result.get("plan_id"),
                    "candidate_id": result.get("candidate_id"),
                    "group_id": result.get("group_id"),
                    "status": "rollback_ready",
                    "rollback_mode": "manual_review_required",
                    "target_artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": result.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "rollback_artifact": "workspace/stitched-flow-rollback-plan.json",
                    "virtual_rollback_artifact": "virtual://workspace/stitched-flow-rollback-plan.json",
                    "entry_sequences": list(result.get("entry_sequences", [])) if isinstance(result.get("entry_sequences"), list) else [],
                    "entry_count": int(result.get("entry_count") or 0),
                    "remove_selectors": {
                        "materialization_result_id": result.get("result_id"),
                        "plan_id": result.get("plan_id"),
                        "candidate_id": result.get("candidate_id"),
                        "group_id": result.get("group_id"),
                    },
                    "rollback_steps": [
                        "locate_stitched_flow_entries_matching_remove_selectors",
                        "remove_or_mark_reverted_materialized_flow_entry",
                        "preserve_original_flow_timeline_entries",
                        "record_manual_revert_reason_in_review_notes",
                        "rerun_replay_validation_before_reusing_artifact",
                    ],
                    "verification_requirements": [
                        "confirm_reverted_flow_no_longer_used_for_delivery",
                        "confirm_original_evidence_entries_are_preserved",
                        "confirm_review_gate_recomputed_after_rollback",
                    ],
                    "source_audit": {
                        "audit_id": audit.get("audit_id"),
                        "audit_artifact": audit.get("audit_artifact", "workspace/stitched-flow-materialization-audit.json"),
                    },
                    "review_required": True,
                    "writes_artifact": False,
                    "would_revert": False,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "scope": "stitched-flow-rollback-plan-baseline",
                    "next_action": "review_rollback_plan_before_reverting_stitched_flow",
                }
            )
        return plans

    @staticmethod
    def _auto_stitch_materialization_rollback_summary(
        rollback_plans: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        materialized_result_count = sum(1 for result in results if result.get("status") == "materialized")
        return {
            "rollback_plan_count": len(rollback_plans),
            "materialized_result_count": materialized_result_count,
            "missing_rollback_plan_count": max(0, materialized_result_count - len(rollback_plans)),
            "rollback_artifact": "workspace/stitched-flow-rollback-plan.json",
            "virtual_rollback_artifact": "virtual://workspace/stitched-flow-rollback-plan.json",
            "writes_artifact": bool(rollback_plans),
            "automatic_rollback": False,
            "automatic_stitching": False,
            "review_required": bool(rollback_plans),
            "scope": "stitched-flow-rollback-plan-summary",
            "next_action": "review_rollback_plan_before_reverting_stitched_flow" if rollback_plans else "materialize_review_approved_plan_before_rollback_planning",
        }

    @classmethod
    def _auto_stitch_materialization_transactions(
        cls,
        results: list[dict[str, Any]],
        audit_entries: list[dict[str, Any]],
        rollback_plans: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Aggregate result, audit and rollback links without executing them."""

        audits_by_transaction_id = {
            str(entry.get("transaction_id")): entry
            for entry in audit_entries
            if isinstance(entry, dict) and entry.get("transaction_id")
        }
        rollbacks_by_transaction_id = {
            str(plan.get("transaction_id")): plan
            for plan in rollback_plans
            if isinstance(plan, dict) and plan.get("transaction_id")
        }
        transactions: list[dict[str, Any]] = []
        for result in results:
            if result.get("status") != "materialized" or not result.get("materialized"):
                continue
            transaction_id = str(result.get("transaction_id") or f"auto-stitch-materialization-txn-{len(transactions) + 1}")
            audit = audits_by_transaction_id.get(transaction_id, {})
            rollback = rollbacks_by_transaction_id.get(transaction_id, {})
            missing_links: list[str] = []
            if not audit:
                missing_links.append("missing_materialization_audit")
            if not rollback:
                missing_links.append("missing_rollback_plan")
            review_decision = result.get("review_decision") if isinstance(result.get("review_decision"), dict) else {}
            conflict_resolution = result.get("conflict_resolution") if isinstance(result.get("conflict_resolution"), dict) else {}
            transactions.append(
                {
                    "transaction_id": transaction_id,
                    "transaction_log_id": f"auto-stitch-materialization-transaction-{len(transactions) + 1}",
                    "status": "transaction_ready" if not missing_links else "transaction_incomplete",
                    "flow_id": audit.get("flow_id"),
                    "run_id": audit.get("run_id"),
                    "result_id": result.get("result_id"),
                    "audit_id": audit.get("audit_id"),
                    "rollback_id": rollback.get("rollback_id"),
                    "plan_id": result.get("plan_id"),
                    "decision_id": result.get("decision_id"),
                    "dry_run_id": result.get("dry_run_id"),
                    "candidate_id": result.get("candidate_id"),
                    "group_id": result.get("group_id"),
                    "target_artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": result.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "entry_sequences": list(result.get("entry_sequences", [])) if isinstance(result.get("entry_sequences"), list) else [],
                    "entry_count": int(result.get("entry_count") or 0),
                    "confidence": result.get("confidence"),
                    "confidence_score": result.get("confidence_score"),
                    "review": {
                        "status": review_decision.get("status"),
                        "approved": bool(review_decision.get("approved")),
                        "reviewer": review_decision.get("reviewer") or review_decision.get("reviewed_by") or review_decision.get("reviewedBy"),
                        "reviewed_at": review_decision.get("reviewed_at") or review_decision.get("reviewedAt"),
                    },
                    "conflict_resolution": {
                        "resolution_id": conflict_resolution.get("resolution_id"),
                        "selected_candidate_id": conflict_resolution.get("selected_candidate_id"),
                        "alternative_candidate_ids": list(conflict_resolution.get("alternative_candidate_ids", []))
                        if isinstance(conflict_resolution.get("alternative_candidate_ids"), list)
                        else [],
                        "unresolved_conflicts": list(conflict_resolution.get("unresolved_conflicts", []))
                        if isinstance(conflict_resolution.get("unresolved_conflicts"), list)
                        else [],
                    },
                    "stages": [
                        {
                            "stage": "materialization_result",
                            "status": result.get("status"),
                            "artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                            "writes_artifact": bool(result.get("writes_artifact")),
                        },
                        {
                            "stage": "materialization_audit",
                            "status": audit.get("status", "missing"),
                            "artifact": audit.get("audit_artifact", "workspace/stitched-flow-materialization-audit.json"),
                            "writes_artifact": bool(audit.get("writes_artifact")),
                        },
                        {
                            "stage": "rollback_plan",
                            "status": rollback.get("status", "missing"),
                            "artifact": rollback.get("rollback_artifact", "workspace/stitched-flow-rollback-plan.json"),
                            "writes_artifact": bool(rollback.get("writes_artifact")),
                        },
                    ],
                    "integrity": {
                        "has_materialization_result": True,
                        "has_audit": bool(audit),
                        "has_rollback_plan": bool(rollback),
                        "missing_links": missing_links,
                    },
                    "source_artifacts": {
                        "flow_timeline": "workspace/flow-timeline.json",
                        "materialization_results": "workspace/auto-stitch-materialization-results.json",
                        "materialization_audit": "workspace/stitched-flow-materialization-audit.json",
                        "rollback_plan": "workspace/stitched-flow-rollback-plan.json",
                    },
                    "review_required": bool(missing_links),
                    "writes_artifact": bool(result.get("writes_artifact")),
                    "would_materialize": bool(result.get("would_materialize")),
                    "would_revert": False,
                    "automatic_stitching": False,
                    "automatic_rollback": False,
                    "transaction_log_only": True,
                    "scope": "stitched-flow-materialization-transaction-log-baseline",
                    "next_action": "review_materialization_transaction_and_rollback_plan"
                    if not missing_links
                    else "repair_materialization_transaction_links_before_use",
                }
            )
        return transactions

    @staticmethod
    def _auto_stitch_materialization_transaction_summary(
        transactions: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        materialized_result_count = sum(1 for result in results if result.get("status") == "materialized")
        ready_count = sum(1 for item in transactions if item.get("status") == "transaction_ready")
        incomplete_count = sum(1 for item in transactions if item.get("status") != "transaction_ready")
        return {
            "transaction_count": len(transactions),
            "materialized_result_count": materialized_result_count,
            "ready_transaction_count": ready_count,
            "incomplete_transaction_count": incomplete_count,
            "missing_transaction_count": max(0, materialized_result_count - len(transactions)),
            "transaction_artifact": "workspace/stitched-flow-materialization-transactions.json",
            "virtual_transaction_artifact": "virtual://workspace/stitched-flow-materialization-transactions.json",
            "writes_artifact": bool(transactions),
            "would_materialize": bool(transactions),
            "would_revert": False,
            "automatic_stitching": False,
            "automatic_rollback": False,
            "transaction_log_only": True,
            "review_required": bool(incomplete_count),
            "scope": "stitched-flow-materialization-transaction-summary",
            "next_action": "review_materialization_transactions_before_rollback_executor"
            if transactions
            else "materialize_review_approved_plan_before_transaction_log",
        }

    @classmethod
    def _auto_stitch_rollback_execution_plans(
        cls,
        rollback_plans: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        transactions_by_id = {item.get("transaction_id"): item for item in transactions if isinstance(item, dict)}
        execution_plans: list[dict[str, Any]] = []
        for rollback in rollback_plans:
            if rollback.get("status") != "rollback_ready":
                continue
            transaction = transactions_by_id.get(rollback.get("transaction_id"), {})
            execution_plans.append(
                {
                    "rollback_execution_plan_id": f"stitched-flow-rollback-execution-plan-{len(execution_plans) + 1}",
                    "transaction_id": rollback.get("transaction_id"),
                    "rollback_id": rollback.get("rollback_id"),
                    "audit_id": rollback.get("audit_id"),
                    "result_id": rollback.get("result_id"),
                    "plan_id": rollback.get("plan_id"),
                    "candidate_id": rollback.get("candidate_id"),
                    "group_id": rollback.get("group_id"),
                    "status": "rollback_execution_plan_ready_for_review",
                    "execution_mode": "dry_run_only",
                    "target_artifact": rollback.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": rollback.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "execution_artifact": "workspace/stitched-flow-rollback-executions.json",
                    "virtual_execution_artifact": "virtual://workspace/stitched-flow-rollback-executions.json",
                    "entry_sequences": list(rollback.get("entry_sequences", [])) if isinstance(rollback.get("entry_sequences"), list) else [],
                    "entry_count": int(rollback.get("entry_count") or 0),
                    "remove_selectors": dict(rollback.get("remove_selectors", {})) if isinstance(rollback.get("remove_selectors"), dict) else {},
                    "rollback_steps": list(rollback.get("rollback_steps", [])) if isinstance(rollback.get("rollback_steps"), list) else [],
                    "verification_requirements": cls._unique_strings(
                        [
                            *cls._string_values(rollback.get("verification_requirements")),
                            "confirm_rollback_execution_review_approved",
                            "confirm_target_artifact_not_physically_deleted_by_baseline",
                        ]
                    ),
                    "transaction_integrity": dict(transaction.get("integrity", {})) if isinstance(transaction.get("integrity"), dict) else {},
                    "review_requirements": [
                        "approve_rollback_execution_plan",
                        "confirm_materialization_transaction_is_ready",
                        "confirm_rollback_selectors_match_materialized_flow",
                        "confirm_review_gate_recompute_plan_exists",
                    ],
                    "review_required": True,
                    "dry_run": True,
                    "would_revert": False,
                    "writes_artifact": False,
                    "target_artifact_mutated": False,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "scope": "stitched-flow-rollback-execution-plan-baseline",
                    "next_action": "review_rollback_execution_plan_before_recording_logical_revert",
                }
            )
        return execution_plans

    def _apply_rollback_execution_review_decisions(
        self,
        plans: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not decisions:
            return plans
        output: list[dict[str, Any]] = []
        for plan in plans:
            next_plan = dict(plan)
            decision = self._matching_rollback_execution_review_decision(next_plan, decisions)
            if decision is not None:
                next_plan = self._rollback_execution_plan_with_review_decision(next_plan, decision)
            output.append(next_plan)
        return output

    @staticmethod
    def _matching_rollback_execution_review_decision(
        plan: dict[str, Any],
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            if decision.get("rollback_execution_plan_id") and decision.get("rollback_execution_plan_id") == plan.get("rollback_execution_plan_id"):
                return decision
            if decision.get("rollbackExecutionPlanId") and decision.get("rollbackExecutionPlanId") == plan.get("rollback_execution_plan_id"):
                return decision
            if decision.get("rollback_id") and decision.get("rollback_id") == plan.get("rollback_id"):
                return decision
            if decision.get("rollbackId") and decision.get("rollbackId") == plan.get("rollback_id"):
                return decision
            if decision.get("transaction_id") and decision.get("transaction_id") == plan.get("transaction_id"):
                return decision
            if decision.get("transactionId") and decision.get("transactionId") == plan.get("transaction_id"):
                return decision
            if decision.get("result_id") and decision.get("result_id") == plan.get("result_id"):
                return decision
            if decision.get("resultId") and decision.get("resultId") == plan.get("result_id"):
                return decision
        return None

    @classmethod
    def _rollback_execution_plan_with_review_decision(
        cls,
        plan: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        next_plan = dict(plan)
        status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
        approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
        rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
        review_decision = {
            "status": "approved" if approved else "rejected" if rejected else status or "pending_review",
            "approved": approved and not rejected,
            "review_required": not approved,
            "review_gate": "auto_stitch_rollback_execution_review_decision",
        }
        for key in ("reviewer", "reviewed_by", "reviewedBy", "reviewed_at", "reviewedAt", "reason", "notes"):
            if decision.get(key) is not None:
                review_decision[key] = decision.get(key)
        next_plan["review_decision"] = review_decision
        next_plan["review_decision_input"] = dict(decision)
        if approved and not rejected:
            next_plan["status"] = "approved_for_rollback_execution"
            next_plan["execution_mode"] = "review_approved_logical_revert_baseline"
            next_plan["review_required"] = False
            next_plan["dry_run"] = False
            next_plan["would_revert"] = True
            next_plan["next_action"] = "record_review_approved_rollback_execution_result"
            next_plan["scope"] = "review-approved-rollback-execution-plan"
        elif rejected:
            next_plan["status"] = "rejected"
            next_plan["blocking_conditions"] = cls._unique_strings(
                [*cls._string_values(next_plan.get("blocking_conditions")), "rollback_execution_reviewer_rejected"]
            )
            next_plan["next_action"] = "revise_rollback_execution_plan_or_collect_more_evidence"
        return next_plan

    @staticmethod
    def _auto_stitch_rollback_execution_summary(
        plans: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        approved_count = sum(1 for item in plans if item.get("status") == "approved_for_rollback_execution")
        rejected_count = sum(1 for item in plans if item.get("status") == "rejected")
        return {
            "execution_plan_count": len(plans),
            "transaction_count": len(transactions),
            "approved_execution_plan_count": approved_count,
            "rejected_execution_plan_count": rejected_count,
            "pending_execution_plan_count": max(0, len(plans) - approved_count - rejected_count),
            "execution_artifact": "workspace/stitched-flow-rollback-executions.json",
            "virtual_execution_artifact": "virtual://workspace/stitched-flow-rollback-executions.json",
            "dry_run_only_by_default": True,
            "would_revert": bool(approved_count),
            "writes_artifact": False,
            "target_artifact_mutated": False,
            "automatic_rollback": False,
            "automatic_stitching": False,
            "review_required": bool(plans) and not bool(approved_count),
            "scope": "stitched-flow-rollback-execution-summary",
            "next_action": "review_rollback_execution_plans" if plans and not approved_count else "record_approved_rollback_execution_results" if approved_count else "materialize_review_approved_plan_before_rollback_execution",
        }

    @classmethod
    def _auto_stitch_rollback_execution_results(
        cls,
        plans: list[dict[str, Any]],
        transactions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        transactions_by_id = {item.get("transaction_id"): item for item in transactions if isinstance(item, dict)}
        results: list[dict[str, Any]] = []
        for plan in plans:
            if plan.get("status") != "approved_for_rollback_execution":
                continue
            transaction = transactions_by_id.get(plan.get("transaction_id"), {})
            review_decision = plan.get("review_decision") if isinstance(plan.get("review_decision"), dict) else {}
            results.append(
                {
                    "rollback_execution_result_id": f"stitched-flow-rollback-execution-result-{len(results) + 1}",
                    "rollback_execution_plan_id": plan.get("rollback_execution_plan_id"),
                    "transaction_id": plan.get("transaction_id"),
                    "rollback_id": plan.get("rollback_id"),
                    "audit_id": plan.get("audit_id"),
                    "materialization_result_id": plan.get("result_id"),
                    "candidate_id": plan.get("candidate_id"),
                    "group_id": plan.get("group_id"),
                    "status": "logical_revert_recorded",
                    "execution_mode": "review_approved_logical_revert_baseline",
                    "target_artifact": plan.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": plan.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "execution_artifact": plan.get("execution_artifact", "workspace/stitched-flow-rollback-executions.json"),
                    "virtual_execution_artifact": plan.get("virtual_execution_artifact", "virtual://workspace/stitched-flow-rollback-executions.json"),
                    "entry_sequences": list(plan.get("entry_sequences", [])) if isinstance(plan.get("entry_sequences"), list) else [],
                    "entry_count": int(plan.get("entry_count") or 0),
                    "remove_selectors": dict(plan.get("remove_selectors", {})) if isinstance(plan.get("remove_selectors"), dict) else {},
                    "transaction_integrity": dict(transaction.get("integrity", {})) if isinstance(transaction.get("integrity"), dict) else {},
                    "review_decision": review_decision,
                    "review_decision_input": dict(plan.get("review_decision_input", {})) if isinstance(plan.get("review_decision_input"), dict) else {},
                    "logical_rollback_recorded": True,
                    "rollback_executed": True,
                    "physical_artifact_mutated": False,
                    "target_artifact_mutated": False,
                    "writes_artifact": True,
                    "would_revert": True,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "review_required": False,
                    "scope": "review-approved-rollback-execution-result-baseline",
                    "limitations": [
                        "review_approved_not_automatic",
                        "logical_revert_record_only",
                        "target_artifact_not_physically_deleted",
                        "review_gate_recompute_baseline_does_not_replace_standard_gate",
                    ],
                    "next_action": "recompute_review_gate_after_rollback_before_delivery",
                }
            )
        return results

    @classmethod
    def _auto_stitch_rollback_execution_result_summary(
        cls,
        results: list[dict[str, Any]],
        review_decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        approved_count = 0
        rejected_count = 0
        pending_count = 0
        for decision in review_decisions:
            if not isinstance(decision, dict):
                continue
            status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
            approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
            rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
            if approved and not rejected:
                approved_count += 1
            elif rejected:
                rejected_count += 1
            else:
                pending_count += 1
        return {
            "rollback_execution_result_count": len(results),
            "logical_revert_recorded_count": sum(1 for item in results if item.get("logical_rollback_recorded")),
            "review_decision_count": len(review_decisions),
            "approved_review_decision_count": approved_count,
            "rejected_review_decision_count": rejected_count,
            "pending_review_decision_count": pending_count,
            "writes_artifact": bool(results),
            "would_revert": bool(results),
            "physical_artifact_mutated": False,
            "target_artifact_mutated": False,
            "automatic_rollback": False,
            "automatic_stitching": False,
            "review_required": not bool(results),
            "scope": "review-approved-rollback-execution-result-summary",
            "next_action": "recompute_review_gate_after_rollback_before_delivery" if results else "review_rollback_execution_plans",
        }

    @classmethod
    def _auto_stitch_rollback_review_gate_recomputations(
        cls,
        rollback_execution_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        recomputations: list[dict[str, Any]] = []
        for result in rollback_execution_results:
            if result.get("status") != "logical_revert_recorded" or not result.get("logical_rollback_recorded"):
                continue
            recomputations.append(
                {
                    "recomputation_id": f"stitched-flow-rollback-review-gate-recompute-{len(recomputations) + 1}",
                    "status": "post_rollback_review_required",
                    "gate_name": "rollback_after_materialization_review_gate",
                    "source": "review_approved_logical_rollback_result",
                    "rollback_execution_result_id": result.get("rollback_execution_result_id"),
                    "rollback_execution_plan_id": result.get("rollback_execution_plan_id"),
                    "transaction_id": result.get("transaction_id"),
                    "rollback_id": result.get("rollback_id"),
                    "result_id": result.get("result_id"),
                    "target_artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                    "review_gate_artifact": "workspace/review-gate-after-rollback.json",
                    "virtual_review_gate_artifact": "virtual://workspace/review-gate-after-rollback.json",
                    "logical_rollback_recorded": True,
                    "physical_artifact_mutated": False,
                    "target_artifact_mutated": False,
                    "does_not_replace_review_gate": True,
                    "delivery_allowed": False,
                    "blocked": True,
                    "review_required": True,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "recompute_baseline": True,
                    "reasons": [
                        "logical_rollback_recorded",
                        "physical_artifact_not_mutated",
                        "post_rollback_delivery_gate_requires_review",
                    ],
                    "blocking_conditions": [
                        "review_logical_rollback_result",
                        "confirm_stitched_flow_artifact_state_after_rollback",
                        "rerun_standard_review_gate_before_delivery",
                    ],
                    "next_action": "review_logical_rollback_and_rerun_delivery_gate_before_delivery",
                }
            )
        return recomputations

    @classmethod
    def _auto_stitch_rollback_review_gate_recomputation_summary(
        cls,
        recomputations: list[dict[str, Any]],
        rollback_execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        blocked_count = sum(1 for item in recomputations if item.get("blocked"))
        return {
            "recomputation_count": len(recomputations),
            "source_rollback_execution_result_count": len(rollback_execution_results),
            "blocked_count": blocked_count,
            "delivery_allowed_count": sum(1 for item in recomputations if item.get("delivery_allowed")),
            "review_required": bool(recomputations),
            "physical_artifact_mutated": False,
            "target_artifact_mutated": False,
            "automatic_rollback": False,
            "automatic_stitching": False,
            "does_not_replace_review_gate": bool(recomputations),
            "review_gate_artifact": "workspace/review-gate-after-rollback.json",
            "virtual_review_gate_artifact": "virtual://workspace/review-gate-after-rollback.json",
            "scope": "post-rollback-review-gate-recompute-baseline",
            "next_action": (
                "review_logical_rollback_and_rerun_delivery_gate_before_delivery"
                if recomputations
                else "record_review_approved_rollback_execution_before_recomputing_gate"
            ),
        }

    @classmethod
    def _auto_stitch_physical_rollback_dry_run_diffs(
        cls,
        rollback_execution_results: list[dict[str, Any]],
        rollback_review_gate_recomputations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        recomputations_by_result_id = {
            item.get("rollback_execution_result_id"): item
            for item in rollback_review_gate_recomputations
            if isinstance(item, dict) and item.get("rollback_execution_result_id")
        }
        dry_runs: list[dict[str, Any]] = []
        for result in rollback_execution_results:
            if result.get("status") != "logical_revert_recorded" or not result.get("logical_rollback_recorded"):
                continue
            recomputation = recomputations_by_result_id.get(result.get("rollback_execution_result_id"), {})
            if not recomputation:
                continue
            remove_selectors = dict(result.get("remove_selectors", {})) if isinstance(result.get("remove_selectors"), dict) else {}
            entry_sequences = list(result.get("entry_sequences", [])) if isinstance(result.get("entry_sequences"), list) else []
            dry_runs.append(
                {
                    "dry_run_id": f"stitched-flow-physical-rollback-diff-{len(dry_runs) + 1}",
                    "status": "physical_rollback_diff_ready_for_review",
                    "diff_mode": "dry_run_only",
                    "source": "post_rollback_review_gate_recompute_baseline",
                    "rollback_execution_result_id": result.get("rollback_execution_result_id"),
                    "rollback_execution_plan_id": result.get("rollback_execution_plan_id"),
                    "review_gate_recomputation_id": recomputation.get("recomputation_id"),
                    "transaction_id": result.get("transaction_id"),
                    "rollback_id": result.get("rollback_id"),
                    "audit_id": result.get("audit_id"),
                    "materialization_result_id": result.get("materialization_result_id"),
                    "candidate_id": result.get("candidate_id"),
                    "group_id": result.get("group_id"),
                    "target_artifact": result.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": result.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "diff_artifact": "workspace/stitched-flow-physical-rollback-diff.json",
                    "virtual_diff_artifact": "virtual://workspace/stitched-flow-physical-rollback-diff.json",
                    "review_gate_artifact": recomputation.get("review_gate_artifact", "workspace/review-gate-after-rollback.json"),
                    "dry_run": True,
                    "review_required": True,
                    "would_mutate_if_approved": True,
                    "would_remove_entries": bool(entry_sequences or remove_selectors),
                    "would_update_manifest": True,
                    "would_replace_review_gate": False,
                    "writes_artifact": False,
                    "physical_artifact_mutated": False,
                    "target_artifact_mutated": False,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "diff": {
                        "operation": "remove_review_approved_stitched_flow_materialization",
                        "target_artifact_action": "remove_matching_materialized_stitched_flow_entries",
                        "entry_sequences_to_remove": entry_sequences,
                        "remove_selectors": remove_selectors,
                        "manifest_updates": [
                            {
                                "artifact_key": "workspace_stitched_flow",
                                "action": "mark_removed_or_replaced_after_approved_physical_rollback",
                                "dry_run_only": True,
                            },
                            {
                                "artifact_key": "workspace_backend_artifact_manifest",
                                "action": "record_physical_rollback_transaction_if_approved",
                                "dry_run_only": True,
                            },
                        ],
                        "review_gate_updates": [
                            {
                                "artifact_key": "workspace_review_gate",
                                "action": "rerun_standard_gate_after_physical_rollback",
                                "dry_run_only": True,
                            }
                        ],
                    },
                    "verification_requirements": [
                        "confirm_target_artifact_contains_selected_materialization_before_mutation",
                        "confirm_backend_artifact_manifest_update_is_reviewed",
                        "confirm_standard_review_gate_will_be_rerun_after_physical_rollback",
                        "confirm_no_unrelated_stitched_flow_entries_are_removed",
                    ],
                    "blocking_conditions": [
                        "physical_rollback_reviewer_approval_required",
                        "standard_review_gate_replacement_not_performed_by_baseline",
                    ],
                    "next_action": "review_physical_rollback_diff_before_any_artifact_mutation",
                }
            )
        return dry_runs

    @classmethod
    def _auto_stitch_physical_rollback_dry_run_diff_summary(
        cls,
        dry_run_diffs: list[dict[str, Any]],
        rollback_execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        approved_count = sum(1 for item in dry_run_diffs if item.get("status") == "approved_for_physical_rollback")
        return {
            "dry_run_diff_count": len(dry_run_diffs),
            "source_rollback_execution_result_count": len(rollback_execution_results),
            "review_required_count": sum(1 for item in dry_run_diffs if item.get("review_required")),
            "approved_for_physical_rollback_count": approved_count,
            "would_mutate_if_approved_count": sum(1 for item in dry_run_diffs if item.get("would_mutate_if_approved")),
            "would_update_manifest_count": sum(1 for item in dry_run_diffs if item.get("would_update_manifest")),
            "would_replace_review_gate": False,
            "writes_artifact": False,
            "physical_artifact_mutated": False,
            "target_artifact_mutated": False,
            "automatic_rollback": False,
            "automatic_stitching": False,
            "dry_run_only": not bool(approved_count),
            "diff_artifact": "workspace/stitched-flow-physical-rollback-diff.json",
            "virtual_diff_artifact": "virtual://workspace/stitched-flow-physical-rollback-diff.json",
            "scope": "physical-rollback-dry-run-diff-baseline",
            "next_action": (
                "apply_review_approved_physical_rollback"
                if approved_count
                else "review_physical_rollback_diff_before_any_artifact_mutation"
                if dry_run_diffs
                else "record_logical_rollback_and_post_rollback_gate_before_physical_diff"
            ),
        }

    def _apply_physical_rollback_review_decisions(
        self,
        dry_run_diffs: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not decisions:
            return dry_run_diffs
        output: list[dict[str, Any]] = []
        for dry_run in dry_run_diffs:
            next_dry_run = dict(dry_run)
            decision = self._matching_physical_rollback_review_decision(next_dry_run, decisions)
            if decision is not None:
                next_dry_run = self._physical_rollback_dry_run_with_review_decision(next_dry_run, decision)
            output.append(next_dry_run)
        return output

    @staticmethod
    def _matching_physical_rollback_review_decision(
        dry_run: dict[str, Any],
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            if decision.get("dry_run_id") and decision.get("dry_run_id") == dry_run.get("dry_run_id"):
                return decision
            if decision.get("dryRunId") and decision.get("dryRunId") == dry_run.get("dry_run_id"):
                return decision
            if decision.get("rollback_execution_result_id") and decision.get("rollback_execution_result_id") == dry_run.get("rollback_execution_result_id"):
                return decision
            if decision.get("rollbackExecutionResultId") and decision.get("rollbackExecutionResultId") == dry_run.get("rollback_execution_result_id"):
                return decision
            if decision.get("rollback_execution_plan_id") and decision.get("rollback_execution_plan_id") == dry_run.get("rollback_execution_plan_id"):
                return decision
            if decision.get("rollbackExecutionPlanId") and decision.get("rollbackExecutionPlanId") == dry_run.get("rollback_execution_plan_id"):
                return decision
            if decision.get("transaction_id") and decision.get("transaction_id") == dry_run.get("transaction_id"):
                return decision
            if decision.get("transactionId") and decision.get("transactionId") == dry_run.get("transaction_id"):
                return decision
            if decision.get("materialization_result_id") and decision.get("materialization_result_id") == dry_run.get("materialization_result_id"):
                return decision
            if decision.get("materializationResultId") and decision.get("materializationResultId") == dry_run.get("materialization_result_id"):
                return decision
        return None

    @classmethod
    def _physical_rollback_dry_run_with_review_decision(
        cls,
        dry_run: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        next_dry_run = dict(dry_run)
        status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
        approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
        rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
        review_decision = {
            "status": "approved" if approved else "rejected" if rejected else status or "pending_review",
            "approved": approved and not rejected,
            "review_required": not approved,
            "review_gate": "auto_stitch_physical_rollback_review_decision",
        }
        for key in ("reviewer", "reviewed_by", "reviewedBy", "reviewed_at", "reviewedAt", "reason", "notes"):
            if decision.get(key) is not None:
                review_decision[key] = decision.get(key)
        next_dry_run["review_decision"] = review_decision
        next_dry_run["review_decision_input"] = dict(decision)
        if approved and not rejected:
            next_dry_run["status"] = "approved_for_physical_rollback"
            next_dry_run["diff_mode"] = "review_approved_physical_rollback"
            next_dry_run["dry_run"] = False
            next_dry_run["review_required"] = False
            next_dry_run["writes_artifact"] = True
            next_dry_run["blocking_conditions"] = [
                condition
                for condition in cls._string_values(next_dry_run.get("blocking_conditions"))
                if condition != "physical_rollback_reviewer_approval_required"
            ]
            next_dry_run["next_action"] = "apply_review_approved_physical_rollback"
        elif rejected:
            next_dry_run["status"] = "rejected"
            next_dry_run["blocking_conditions"] = cls._unique_strings(
                [*cls._string_values(next_dry_run.get("blocking_conditions")), "physical_rollback_reviewer_rejected"]
            )
            next_dry_run["next_action"] = "revise_physical_rollback_diff_or_collect_more_evidence"
        return next_dry_run

    @classmethod
    def _auto_stitch_physical_rollback_results(
        cls,
        dry_run_diffs: list[dict[str, Any]],
        stitched_flows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for dry_run in dry_run_diffs:
            review_decision = dry_run.get("review_decision") if isinstance(dry_run.get("review_decision"), dict) else {}
            if dry_run.get("status") != "approved_for_physical_rollback" or not review_decision.get("approved"):
                continue
            matched = cls._matching_stitched_flows_for_physical_rollback(dry_run, stitched_flows)
            matched_ids = [str(flow.get("stitched_flow_id")) for flow in matched if flow.get("stitched_flow_id")]
            matched_materialization_ids = [
                str(flow.get("materialization_result_id"))
                for flow in matched
                if flow.get("materialization_result_id")
            ]
            entry_sequences_to_remove = list(dry_run.get("diff", {}).get("entry_sequences_to_remove", [])) if isinstance(dry_run.get("diff"), dict) else []
            result_status = "physical_rollback_applied" if matched else "physical_rollback_noop_missing_target"
            results.append(
                {
                    "physical_rollback_result_id": f"stitched-flow-physical-rollback-result-{len(results) + 1}",
                    "dry_run_id": dry_run.get("dry_run_id"),
                    "rollback_execution_result_id": dry_run.get("rollback_execution_result_id"),
                    "rollback_execution_plan_id": dry_run.get("rollback_execution_plan_id"),
                    "review_gate_recomputation_id": dry_run.get("review_gate_recomputation_id"),
                    "transaction_id": dry_run.get("transaction_id"),
                    "rollback_id": dry_run.get("rollback_id"),
                    "audit_id": dry_run.get("audit_id"),
                    "materialization_result_id": dry_run.get("materialization_result_id"),
                    "candidate_id": dry_run.get("candidate_id"),
                    "group_id": dry_run.get("group_id"),
                    "status": result_status,
                    "execution_mode": "review_approved_physical_rollback",
                    "target_artifact": dry_run.get("target_artifact", "workspace/stitched-flow.json"),
                    "virtual_target_artifact": dry_run.get("virtual_target_artifact", "virtual://workspace/stitched-flow.json"),
                    "result_artifact": "workspace/stitched-flow-physical-rollback-results.json",
                    "virtual_result_artifact": "virtual://workspace/stitched-flow-physical-rollback-results.json",
                    "diff_artifact": dry_run.get("diff_artifact", "workspace/stitched-flow-physical-rollback-diff.json"),
                    "matched_stitched_flow_ids": matched_ids,
                    "matched_materialization_result_ids": matched_materialization_ids,
                    "removed_entry_sequences": entry_sequences_to_remove,
                    "removed_entry_count": len(entry_sequences_to_remove),
                    "remove_selectors": dict(dry_run.get("diff", {}).get("remove_selectors", {})) if isinstance(dry_run.get("diff"), dict) and isinstance(dry_run.get("diff", {}).get("remove_selectors"), dict) else {},
                    "review_decision": review_decision,
                    "review_decision_input": dict(dry_run.get("review_decision_input", {})) if isinstance(dry_run.get("review_decision_input"), dict) else {},
                    "physical_rollback_applied": bool(matched),
                    "physical_artifact_mutated": bool(matched),
                    "target_artifact_mutated": bool(matched),
                    "writes_artifact": True,
                    "manifest_update_required": bool(matched),
                    "standard_review_gate_rerun_required": bool(matched),
                    "would_replace_review_gate": False,
                    "automatic_rollback": False,
                    "automatic_stitching": False,
                    "review_required": False,
                    "limitations": [
                        "review_approved_not_automatic",
                        "standard_review_gate_replacement_not_performed",
                        "artifact_model_mutation_only",
                    ],
                    "next_action": (
                        "rerun_standard_review_gate_after_physical_rollback"
                        if matched
                        else "inspect_stitched_flow_state_before_retrying_physical_rollback"
                    ),
                }
            )
        return results

    @classmethod
    def _matching_stitched_flows_for_physical_rollback(
        cls,
        dry_run: dict[str, Any],
        stitched_flows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        diff = dry_run.get("diff") if isinstance(dry_run.get("diff"), dict) else {}
        selectors = diff.get("remove_selectors") if isinstance(diff.get("remove_selectors"), dict) else {}
        entry_sequences = set(diff.get("entry_sequences_to_remove", [])) if isinstance(diff.get("entry_sequences_to_remove"), list) else set()
        matched: list[dict[str, Any]] = []
        for flow in stitched_flows:
            if not isinstance(flow, dict):
                continue
            if selectors.get("materialization_result_id") and selectors.get("materialization_result_id") == flow.get("materialization_result_id"):
                matched.append(flow)
                continue
            if selectors.get("plan_id") and selectors.get("plan_id") == flow.get("plan_id"):
                matched.append(flow)
                continue
            if selectors.get("candidate_id") and selectors.get("candidate_id") == flow.get("candidate_id"):
                matched.append(flow)
                continue
            if selectors.get("group_id") and selectors.get("group_id") == flow.get("group_id"):
                matched.append(flow)
                continue
            flow_sequences = set(flow.get("entry_sequences", [])) if isinstance(flow.get("entry_sequences"), list) else set()
            if entry_sequences and flow_sequences and entry_sequences.issubset(flow_sequences):
                matched.append(flow)
        return matched

    @classmethod
    def _stitched_flows_after_physical_rollback_results(
        cls,
        stitched_flows: list[dict[str, Any]],
        physical_rollback_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        removed_ids = {
            stitched_flow_id
            for result in physical_rollback_results
            if result.get("physical_rollback_applied")
            for stitched_flow_id in cls._string_values(result.get("matched_stitched_flow_ids"))
        }
        if not removed_ids:
            return stitched_flows
        return [
            flow
            for flow in stitched_flows
            if not isinstance(flow, dict) or str(flow.get("stitched_flow_id")) not in removed_ids
        ]

    @classmethod
    def _auto_stitch_physical_rollback_result_summary(
        cls,
        results: list[dict[str, Any]],
        review_decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        approved_count = 0
        rejected_count = 0
        pending_count = 0
        for decision in review_decisions:
            if not isinstance(decision, dict):
                continue
            status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
            approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
            rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
            if approved and not rejected:
                approved_count += 1
            elif rejected:
                rejected_count += 1
            else:
                pending_count += 1
        applied_count = sum(1 for result in results if result.get("physical_rollback_applied"))
        return {
            "physical_rollback_result_count": len(results),
            "physical_rollback_applied_count": applied_count,
            "noop_missing_target_count": sum(1 for result in results if result.get("status") == "physical_rollback_noop_missing_target"),
            "review_decision_count": len(review_decisions),
            "approved_review_decision_count": approved_count,
            "rejected_review_decision_count": rejected_count,
            "pending_review_decision_count": pending_count,
            "writes_artifact": bool(results),
            "physical_artifact_mutated": bool(applied_count),
            "target_artifact_mutated": bool(applied_count),
            "manifest_update_required": bool(applied_count),
            "standard_review_gate_rerun_required": bool(applied_count),
            "would_replace_review_gate": False,
            "automatic_rollback": False,
            "automatic_stitching": False,
            "result_artifact": "workspace/stitched-flow-physical-rollback-results.json",
            "virtual_result_artifact": "virtual://workspace/stitched-flow-physical-rollback-results.json",
            "scope": "review-approved-physical-rollback-mutation-baseline",
            "next_action": (
                "rerun_standard_review_gate_after_physical_rollback"
                if applied_count
                else "review_physical_rollback_diff_before_any_artifact_mutation"
            ),
        }

    @staticmethod
    def _stitch_proposals(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Create review-gated stitch proposals from ready manual candidates.

        A proposal is still not a stitched flow.  It is the next machine-readable
        step after a candidate has enough initiator + hook + replay evidence to
        be reviewed.  Nothing in this layer approves or applies stitching; a
        later review gate must explicitly make that decision.
        """

        proposals: list[dict[str, Any]] = []
        approval_requirements = [
            "confirm_entry_order_matches_observed_runtime_flow",
            "confirm_request_identity_or_function_path_matches_target",
            "confirm_replay_validation_matches_original_request_semantics",
            "confirm_no_conflicting_correlation_group_has_stronger_evidence",
        ]
        for candidate in candidates:
            if candidate.get("readiness") != "ready_for_manual_stitch_review":
                continue
            missing_for_ready = candidate.get("missing_for_ready") if isinstance(candidate.get("missing_for_ready"), list) else []
            if missing_for_ready:
                continue
            proposals.append(
                {
                    "proposal_id": f"stitch-proposal-{len(proposals) + 1}",
                    "candidate_id": candidate.get("candidate_id"),
                    "group_id": candidate.get("group_id"),
                    "strategy": candidate.get("strategy"),
                    "key": candidate.get("key", {}),
                    "confidence": candidate.get("confidence", "medium"),
                    "entry_sequences": list(candidate.get("entry_sequences", [])) if isinstance(candidate.get("entry_sequences"), list) else [],
                    "path_length": candidate.get("path_length", 0),
                    "evidence": candidate.get("evidence", {}) if isinstance(candidate.get("evidence"), dict) else {},
                    "approval_requirements": list(approval_requirements),
                    "blocking_conditions": [
                        "missing_reviewer_approval",
                        "automatic_application_disabled",
                    ],
                    "review_decision": {
                        "status": "pending_review",
                        "approved": False,
                        "review_required": True,
                        "review_gate": "manual_or_future_review_gate",
                    },
                    "next_action": "review_stitch_proposal_before_applying",
                    "automatic_stitching": False,
                    "stitching": False,
                    "scope": "review-gated-stitch-proposal-only",
                }
            )
        return proposals

    def _apply_review_decisions(
        self,
        proposals: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not decisions:
            return proposals
        output: list[dict[str, Any]] = []
        for proposal in proposals:
            next_proposal = dict(proposal)
            decision = self._matching_review_decision(next_proposal, decisions)
            if decision is not None:
                next_proposal = self._proposal_with_review_decision(next_proposal, decision)
            output.append(next_proposal)
        return output

    @staticmethod
    def _matching_review_decision(
        proposal: dict[str, Any],
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            if decision.get("proposal_id") and decision.get("proposal_id") == proposal.get("proposal_id"):
                return decision
            if decision.get("proposalId") and decision.get("proposalId") == proposal.get("proposal_id"):
                return decision
            if decision.get("candidate_id") and decision.get("candidate_id") == proposal.get("candidate_id"):
                return decision
            if decision.get("candidateId") and decision.get("candidateId") == proposal.get("candidate_id"):
                return decision
            if decision.get("group_id") and decision.get("group_id") == proposal.get("group_id"):
                return decision
            if decision.get("groupId") and decision.get("groupId") == proposal.get("group_id"):
                return decision
        return None

    @classmethod
    def _proposal_with_review_decision(
        cls,
        proposal: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        next_proposal = dict(proposal)
        status = str(decision.get("status") or decision.get("decision") or "").strip().lower()
        approved = bool(decision.get("approved")) or status in {"approved", "pass", "passed"}
        rejected = bool(decision.get("rejected")) or status in {"rejected", "denied", "blocked"}
        review_decision = dict(next_proposal.get("review_decision", {}))
        review_decision.update(
            {
                "status": "approved" if approved else "rejected" if rejected else status or "pending_review",
                "approved": approved and not rejected,
                "review_required": not approved,
                "review_gate": "manual_review_decision",
            }
        )
        for key in ("reviewer", "reviewed_by", "reviewedBy", "reviewed_at", "reviewedAt", "reason", "notes"):
            if decision.get(key) is not None:
                review_decision[key] = decision.get(key)
        next_proposal["review_decision"] = review_decision
        next_proposal["review_decision_input"] = dict(decision)
        if approved and not rejected:
            next_proposal["blocking_conditions"] = []
            next_proposal["next_action"] = "materialize_approved_stitched_flow"
            next_proposal["scope"] = "review-approved-stitch-proposal"
        elif rejected:
            next_proposal["blocking_conditions"] = cls._unique_strings(
                [*cls._string_values(next_proposal.get("blocking_conditions")), "reviewer_rejected"]
            )
            next_proposal["next_action"] = "collect_more_evidence_or_revise_stitch_proposal"
        return next_proposal

    @staticmethod
    def _stitched_flows(
        proposals: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidates_by_id = {candidate.get("candidate_id"): candidate for candidate in candidates}
        entries_by_sequence = {entry.get("sequence"): entry for entry in entries}
        stitched: list[dict[str, Any]] = []
        for proposal in proposals:
            review_decision = proposal.get("review_decision")
            if not isinstance(review_decision, dict):
                continue
            if not review_decision.get("approved") or review_decision.get("status") != "approved":
                continue
            candidate = candidates_by_id.get(proposal.get("candidate_id"), {})
            entry_sequences = proposal.get("entry_sequences") if isinstance(proposal.get("entry_sequences"), list) else []
            path = candidate.get("path") if isinstance(candidate.get("path"), list) else []
            stitched.append(
                {
                    "stitched_flow_id": f"stitched-flow-{len(stitched) + 1}",
                    "proposal_id": proposal.get("proposal_id"),
                    "candidate_id": proposal.get("candidate_id"),
                    "group_id": proposal.get("group_id"),
                    "strategy": proposal.get("strategy"),
                    "key": proposal.get("key", {}) if isinstance(proposal.get("key"), dict) else {},
                    "confidence": proposal.get("confidence", "medium"),
                    "status": "approved",
                    "entry_sequences": list(entry_sequences),
                    "entry_count": len(entry_sequences),
                    "entry_types": [
                        entries_by_sequence[sequence].get("type")
                        for sequence in entry_sequences
                        if isinstance(entries_by_sequence.get(sequence), dict)
                    ],
                    "sources": list(candidate.get("sources", [])) if isinstance(candidate.get("sources"), list) else [],
                    "path": list(path),
                    "path_length": len(path),
                    "evidence": proposal.get("evidence", {}) if isinstance(proposal.get("evidence"), dict) else {},
                    "review_decision": review_decision,
                    "source": "review_approved_stitch_proposal",
                    "scope": "review-approved-stitch-baseline",
                    "stitching": True,
                    "automatic_stitching": False,
                    "limitations": [
                        "review_approved_not_automatically_inferred",
                        "no_full_browser_event_subscription",
                    ],
                    "next_action": "inspect_stitched_flow_or_use_for_replay_planning",
                }
            )
        return stitched

    @staticmethod
    def _group_verification(group: dict[str, Any]) -> dict[str, Any]:
        sources = {str(source) for source in group.get("sources", [])}
        entry_types = {str(entry_type) for entry_type in group.get("entry_types", [])}
        evidence = {
            "network_request": "network_requests" in sources,
            "request_initiator": "request_initiators" in sources,
            "runtime_hook": any(source.endswith("hook_timeline") for source in sources) or any(entry_type.startswith(("hook.", "function_hook.", "module_hook.")) for entry_type in entry_types),
            "replay_validation": "replay_validation" in sources or "replay.validation" in entry_types,
            "debugger": "debugger_timeline" in sources or any(entry_type.startswith("debugger.") for entry_type in entry_types),
            "source_logpoint": "source_logpoint_timeline" in sources or any(entry_type.startswith("source_logpoint.") for entry_type in entry_types),
            "mutation": "mutation_observer_timeline" in sources or any(entry_type.startswith("mutation.") for entry_type in entry_types),
        }
        required_for_ready = ("request_initiator", "runtime_hook", "replay_validation")
        missing_for_ready = [name for name in required_for_ready if not evidence[name]]
        if not missing_for_ready:
            status = "ready_for_manual_stitch_review"
            next_action = "review_group_against_request_and_replay_evidence"
            reasons = ["initiator_hook_and_replay_evidence_present"]
        elif (
            evidence["request_initiator"]
            and evidence["runtime_hook"]
            or evidence["runtime_hook"]
            and evidence["replay_validation"]
            or evidence["request_initiator"]
            and evidence["replay_validation"]
            or evidence["network_request"]
            and evidence["runtime_hook"]
            or evidence["network_request"]
            and evidence["request_initiator"]
        ):
            status = "reviewable"
            next_action = "collect_missing_evidence_or_review_manually"
            reasons = ["multiple_complementary_evidence_types_present"]
        else:
            status = "weak"
            next_action = "collect_more_timeline_evidence"
            reasons = ["insufficient_complementary_evidence"]
        return {
            "status": status,
            "automatic_stitching": False,
            "evidence": evidence,
            "missing_for_ready": missing_for_ready,
            "reasons": reasons,
            "next_action": next_action,
        }

    @staticmethod
    def _group_candidates(correlation: dict[str, Any]) -> list[tuple[str, dict[str, str], str]]:
        candidates: list[tuple[str, dict[str, str], str]] = []
        request_id = correlation.get("request_id")
        if request_id:
            candidates.append(("request_id", {"request_id": str(request_id)}, "medium"))
        url_path = correlation.get("url_path")
        method = correlation.get("method")
        if url_path and method:
            candidates.append(("url_path_method", {"url_path": str(url_path), "method": str(method).upper()}, "medium"))
        function_names = correlation.get("function_names")
        for function_name in function_names if isinstance(function_names, list) else []:
            if function_name:
                candidates.append(("function_name", {"function_name": str(function_name)}, "low"))
        candidate_ids = correlation.get("candidate_ids")
        for candidate_id in candidate_ids if isinstance(candidate_ids, list) else []:
            if candidate_id:
                candidates.append(("candidate_id", {"candidate_id": str(candidate_id)}, "low"))
        hook_paths = correlation.get("hook_paths")
        for hook_path in hook_paths if isinstance(hook_paths, list) else []:
            if hook_path:
                candidates.append(("hook_path", {"hook_path": str(hook_path)}, "low"))
        return candidates

    @classmethod
    def _first_string(cls, data: dict[str, Any], paths: Iterable[tuple[str, ...]]) -> str | None:
        for value in cls._strings_for_paths(data, paths):
            return value
        return None

    @classmethod
    def _strings_for_paths(cls, data: Any, paths: Iterable[tuple[str, ...]]) -> list[str]:
        values: list[str] = []
        for path in paths:
            value = cls._value_at_path(data, path)
            values.extend(cls._string_values(value))
        return cls._unique_strings(values)

    @staticmethod
    def _value_at_path(data: Any, path: tuple[str, ...]) -> Any:
        current = data
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @classmethod
    def _string_values(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return [str(value)]
        if isinstance(value, list):
            values: list[str] = []
            for item in value:
                values.extend(cls._string_values(item))
            return values
        return []

    @classmethod
    def _callframe_function_names(cls, event: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for callframes in cls._callframe_lists(event):
            if not isinstance(callframes, list):
                continue
            for frame in callframes:
                if not isinstance(frame, dict):
                    continue
                values.extend(cls._string_values(frame.get("functionName")))
                values.extend(cls._string_values(frame.get("function_name")))
        return cls._unique_strings(values)

    @classmethod
    def _callframe_lists(cls, event: dict[str, Any]) -> list[Any]:
        paths = (
            ("callFrames",),
            ("stack", "callFrames"),
            ("initiator", "stack", "callFrames"),
            ("payload", "callFrames"),
            ("payload", "stack", "callFrames"),
            ("payload", "initiator", "stack", "callFrames"),
        )
        return [cls._value_at_path(event, path) for path in paths]

    @staticmethod
    def _url_path(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        path = parsed.path
        if not path and url.startswith("/"):
            path = url.split("?", 1)[0]
        return path or None

    @staticmethod
    def _unique_strings(values: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique

    @staticmethod
    def _safe_payload(event: dict[str, Any], max_length: int) -> dict[str, Any]:
        safe = dict(event)
        for key in ("flow_id", "flowId", "run_id", "runId", "request_id", "requestId", "requestID"):
            safe.pop(key, None)
        try:
            encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True)
        except TypeError:
            safe = {key: str(value) for key, value in safe.items()}
            encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True)
        if len(encoded) <= max_length:
            return safe
        return {
            "preview": encoded[:max_length],
            "truncated": True,
            "original_size": len(encoded),
        }
