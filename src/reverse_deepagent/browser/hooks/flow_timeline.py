from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


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
        if not previous and not flow_events and not source_payloads:
            return None
        flow_id = str(context.get("flow_id", context.get("flowId", previous.get("flow_id", "default-flow"))) or "default-flow")
        return cls(
            flow_id=flow_id,
            run_id=str(context.get("run_id", context.get("runId"))) if context.get("run_id", context.get("runId")) else None,
            request_id=str(context.get("request_id", context.get("requestId"))) if context.get("request_id", context.get("requestId")) else None,
            previous_timeline=previous,
            flow_events=flow_events,
            source_payloads=source_payloads,
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
        status = "success" if new_entries else "partial" if previous_entries else "unsupported"
        return FlowTimelineResult(
            status=status,
            flow_id=spec.flow_id,
            run_id=spec.run_id,
            entries=entries,
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
        return {
            "sequence": sequence,
            "flow_id": str(event.get("flow_id", event.get("flowId", spec.flow_id)) or spec.flow_id),
            "run_id": event.get("run_id", event.get("runId", spec.run_id)),
            "request_id": event.get("request_id", event.get("requestId", event.get("requestID", spec.request_id))),
            "source": source,
            "type": event_type or str(event.get("type", "event")),
            "timestamp": event.get("timestamp", event.get("ts")),
            "payload": payload,
        }

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
