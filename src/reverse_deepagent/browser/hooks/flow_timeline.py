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
        if not previous and not flow_events and not source_payloads and not stitch_review_decisions:
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
        stitch_proposals = self._stitch_proposals(stitch_candidates)
        stitch_proposals = self._apply_review_decisions(stitch_proposals, spec.stitch_review_decisions)
        stitched_flows = self._stitched_flows(stitch_proposals, stitch_candidates, entries)
        status = "success" if new_entries or stitched_flows else "partial" if previous_entries else "unsupported"
        return FlowTimelineResult(
            status=status,
            flow_id=spec.flow_id,
            run_id=spec.run_id,
            entries=entries,
            correlation_groups=correlation_groups,
            stitch_candidates=stitch_candidates,
            auto_stitch_dry_runs=auto_stitch_dry_runs,
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
