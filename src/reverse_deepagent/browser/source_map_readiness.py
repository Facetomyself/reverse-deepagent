from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceMapReadinessSpec:
    """Review-only Source Map evidence readiness join request.

    The readiness descriptor consumes already-produced Source Map review
    artifacts. It never parses raw source content, fetches Source Maps, starts
    a browser, sends CDP commands, installs logpoints, evaluates JavaScript, or
    calls MCP.
    """

    source_map_lookup: dict[str, Any] = field(default_factory=dict)
    source_map_source_content: dict[str, Any] = field(default_factory=dict)
    bundler_symbol_scope: dict[str, Any] = field(default_factory=dict)
    source_map_fetch_result: dict[str, Any] = field(default_factory=dict)
    source_map_fetch_plan: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "SourceMapReadinessSpec | None":
        context = context or {}
        requested = any(
            bool(context.get(key))
            for key in (
                "source_map_readiness",
                "sourceMapReadiness",
                "review_source_map_readiness",
                "reviewSourceMapReadiness",
                "source_map_debugger_readiness",
                "sourceMapDebuggerReadiness",
            )
        )
        lookup = cls._object_alias(context, "source_map_lookup", "source-map-lookup", "sourceMapLookup", "source_map_consumer", "sourceMapConsumer")
        source_content = cls._object_alias(
            context,
            "source_map_source_content",
            "source-map-source-content",
            "sourceMapSourceContent",
            "source_map_sources_content",
            "sourceMapSourcesContent",
        )
        symbol_scope = cls._object_alias(
            context,
            "bundler_symbol_scope",
            "bundler-symbol-scope",
            "bundlerSymbolScope",
            "source_map_symbol_scope",
            "sourceMapSymbolScope",
        )
        fetch_result = cls._object_alias(context, "source_map_fetch_result", "source-map-fetch-result", "sourceMapFetchResult")
        fetch_plan = cls._object_alias(context, "source_map_fetch_plan", "source-map-fetch-plan", "sourceMapFetchPlan")
        if not requested and not any((lookup, source_content, symbol_scope, fetch_result, fetch_plan)):
            return None
        return cls(
            source_map_lookup=lookup,
            source_map_source_content=source_content,
            bundler_symbol_scope=symbol_scope,
            source_map_fetch_result=fetch_result,
            source_map_fetch_plan=fetch_plan,
        )

    @classmethod
    def _object_alias(cls, payload: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}


@dataclass(slots=True)
class SourceMapReadinessResult:
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


class SourceMapReadinessManager:
    """Build a review-only join descriptor for Source Map debugger / rebuild readiness."""

    def review(self, spec: SourceMapReadinessSpec | None) -> SourceMapReadinessResult:
        policy = self._side_effect_policy()
        if spec is None:
            return SourceMapReadinessResult(status="unsupported", reason="missing_source_map_readiness_request", side_effect_policy=policy)
        try:
            descriptor = self._descriptor(spec)
            return SourceMapReadinessResult(status=str(descriptor["status"]), descriptor=descriptor, side_effect_policy=policy)
        except Exception as exc:
            descriptor = self._base_descriptor(status="failed", reason="source_map_readiness_review_failed")
            descriptor["error"] = str(exc)
            return SourceMapReadinessResult(status="failed", descriptor=descriptor, side_effect_policy=policy, reason="source_map_readiness_review_failed", error=str(exc))

    def _descriptor(self, spec: SourceMapReadinessSpec) -> dict[str, Any]:
        evidence_status = self._evidence_status(spec)
        readiness = self._readiness(evidence_status, spec)
        blockers = self._blockers(evidence_status, readiness)
        warnings = self._warnings(evidence_status, readiness)
        status = "blocked" if blockers else "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.source-map-readiness.v1",
            "status": status,
            "review_only": True,
            "evidence_status": evidence_status,
            "readiness": readiness,
            "blockers": blockers,
            "warnings": warnings,
            "next_action": self._next_action(blockers, warnings, readiness),
            "side_effect_policy": self._side_effect_policy(),
        }

    def _base_descriptor(self, *, status: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.source-map-readiness.v1",
            "status": status,
            "review_only": True,
            "reason": reason,
            "evidence_status": {},
            "readiness": {},
            "blockers": [reason],
            "warnings": [],
            "next_action": "provide_source_map_lookup_and_source_content_descriptors",
            "side_effect_policy": self._side_effect_policy(),
        }

    @classmethod
    def _evidence_status(cls, spec: SourceMapReadinessSpec) -> dict[str, Any]:
        lookup = spec.source_map_lookup
        source_content = spec.source_map_source_content
        symbol_scope = spec.bundler_symbol_scope
        fetch_result = spec.source_map_fetch_result
        fetch_plan = spec.source_map_fetch_plan
        content_summary = source_content.get("content_summary") if isinstance(source_content.get("content_summary"), dict) else {}
        return {
            "lookup": {
                "present": bool(lookup),
                "status": cls._status(lookup),
                "mapping_found": bool(lookup.get("mapping_found", False)),
                "strategy": cls._nested_get(lookup, "location", "strategy") or "",
                "next_action": lookup.get("next_action") or "",
            },
            "source_content": {
                "present": bool(source_content),
                "status": cls._status(source_content),
                "source_content_available": bool(source_content.get("source_content_available", False)),
                "sha256": content_summary.get("sha256", ""),
                "raw_content_exported": bool(content_summary.get("raw_content_exported", source_content.get("raw_content_exported", False))),
                "preview_exported": bool(content_summary.get("preview_exported", source_content.get("preview_exported", False))),
                "next_action": source_content.get("next_action") or "",
            },
            "symbol_scope": {
                "present": bool(symbol_scope),
                "status": cls._status(symbol_scope),
                "scope_candidate_count": cls._intish(symbol_scope.get("scope_candidate_count")),
                "source_logpoint_reviewable": bool(cls._nested_get(symbol_scope, "hook_readiness", "source_logpoint_reviewable")),
                "bundler_kind": cls._nested_get(symbol_scope, "bundler_classification", "bundler_kind") or "unknown",
                "next_action": symbol_scope.get("next_action") or "",
            },
            "fetch_result": {
                "present": bool(fetch_result),
                "status": cls._status(fetch_result),
                "ok": bool(fetch_result.get("ok", False)),
                "attempted": bool(fetch_result.get("attempted", False)),
                "payload_exported": bool(fetch_result.get("payload_exported", False)),
            },
            "fetch_plan": {
                "present": bool(fetch_plan),
                "status": cls._status(fetch_plan),
                "fetch_allowed": bool(fetch_plan.get("fetch_allowed", False)),
                "source_map_url_redacted": fetch_plan.get("source_map_url_redacted", ""),
            },
        }

    @staticmethod
    def _readiness(evidence_status: dict[str, Any], spec: SourceMapReadinessSpec) -> dict[str, Any]:
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        symbol_scope = evidence_status["symbol_scope"]
        fetch_result = evidence_status["fetch_result"]
        mapping_ready = bool(lookup["present"] and lookup["status"] == "ready_for_review" and lookup["mapping_found"])
        content_ready = bool(
            source_content["present"]
            and source_content["status"] == "ready_for_review"
            and source_content["source_content_available"]
            and not source_content["raw_content_exported"]
            and not source_content["preview_exported"]
        )
        symbol_reviewable = bool(symbol_scope["present"] and symbol_scope["status"] == "ready_for_review" and symbol_scope["source_logpoint_reviewable"])
        fetch_metadata_ready = bool(fetch_result["present"] and fetch_result["status"] in {"success", "ready_for_review", "planned"} and not fetch_result["payload_exported"])
        return {
            "debugger_location_ready": mapping_ready,
            "source_content_metadata_ready": content_ready,
            "source_logpoint_planning_ready": bool(mapping_ready and (symbol_reviewable or not spec.bundler_symbol_scope)),
            "rebuild_source_metadata_ready": bool(mapping_ready and content_ready),
            "bundler_scope_review_ready": symbol_reviewable,
            "fetch_metadata_ready": fetch_metadata_ready,
            "raw_source_content_exported": bool(source_content["raw_content_exported"]),
            "preview_exported": bool(source_content["preview_exported"]),
            "automatic_logpoint_install_supported": False,
            "automatic_debugger_execution_supported": False,
            "raw_source_aware_rebuild_supported": False,
        }

    @staticmethod
    def _blockers(evidence_status: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        lookup = evidence_status["lookup"]
        source_content = evidence_status["source_content"]
        if not lookup["present"]:
            blockers.append("source_map_lookup_descriptor_missing")
        elif lookup["status"] in {"blocked", "failed", "failure", "error", "unsupported"} or not lookup["mapping_found"]:
            blockers.append("source_map_lookup_not_ready")
        if not source_content["present"]:
            blockers.append("source_map_source_content_descriptor_missing")
        elif source_content["status"] in {"blocked", "failed", "failure", "error", "unsupported"} or not source_content["source_content_available"]:
            blockers.append("source_map_source_content_not_ready")
        if readiness.get("raw_source_content_exported"):
            blockers.append("raw_source_content_export_detected")
        if readiness.get("preview_exported"):
            blockers.append("source_content_preview_export_detected")
        return blockers

    @staticmethod
    def _warnings(evidence_status: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        symbol_scope = evidence_status["symbol_scope"]
        fetch_result = evidence_status["fetch_result"]
        if not symbol_scope["present"]:
            warnings.append("bundler_symbol_scope_descriptor_missing")
        elif symbol_scope["status"] in {"blocked", "failed", "failure", "error", "unsupported"}:
            warnings.append("bundler_symbol_scope_not_ready")
        elif not readiness.get("bundler_scope_review_ready"):
            warnings.append("bundler_symbol_scope_not_reviewable")
        if fetch_result["present"] and fetch_result["payload_exported"]:
            warnings.append("source_map_fetch_payload_exported")
        if not readiness.get("fetch_metadata_ready"):
            warnings.append("source_map_fetch_metadata_not_confirmed")
        return warnings

    @staticmethod
    def _next_action(blockers: list[str], warnings: list[str], readiness: dict[str, Any]) -> str:
        if "source_map_lookup_descriptor_missing" in blockers or "source_map_lookup_not_ready" in blockers:
            return "provide_ready_source_map_lookup_descriptor"
        if "source_map_source_content_descriptor_missing" in blockers or "source_map_source_content_not_ready" in blockers:
            return "provide_ready_source_map_source_content_descriptor"
        if "raw_source_content_export_detected" in blockers or "source_content_preview_export_detected" in blockers:
            return "replace_source_content_descriptor_with_metadata_only_version"
        if "bundler_symbol_scope_descriptor_missing" in warnings or "bundler_symbol_scope_not_ready" in warnings or "bundler_symbol_scope_not_reviewable" in warnings:
            return "review_source_map_readiness_then_add_bundler_symbol_scope"
        if readiness.get("rebuild_source_metadata_ready"):
            return "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning"
        return "review_source_map_readiness"

    @staticmethod
    def _status(payload: dict[str, Any]) -> str:
        return str(payload.get("status") or payload.get("state") or "").strip().lower()

    @staticmethod
    def _intish(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
        current: Any = payload
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "raw_source_content_exported": False,
            "preview_exported": False,
            "fetch_source_map": False,
            "browser_started": False,
            "cdp_command_sent": False,
            "runtime_evaluated": False,
            "logpoint_installed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }
