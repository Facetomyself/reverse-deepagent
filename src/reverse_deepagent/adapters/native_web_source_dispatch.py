from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.source_maps import (
    BundlerSymbolScopeManager,
    BundlerSymbolScopeSpec,
    SourceMapLookupManager,
    SourceMapLookupSpec,
    SourceMapSourceContentManager,
    SourceMapSourceContentSpec,
)
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    ExecutionStatus,
    ProtectionResult,
)


def dispatch_source_map_review_evidence(owner: Any, protection_name: str, context: dict) -> ProtectionResult | None:
    """Route the lowest-side-effect Source Map review-evidence requests.

    This helper is intentionally small: predicates stay on ``owner`` so
    ``_dispatch_source(...)`` order remains mechanically auditable, while
    manager business rules and payload construction stay equivalent to the
    original NativeWebRuntime branches.
    """
    if owner._is_source_map_lookup_request(protection_name, context):
        spec = SourceMapLookupSpec.from_context(context)
        result = SourceMapLookupManager().lookup(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        request = descriptor.get("lookup_request") if isinstance(descriptor.get("lookup_request"), dict) else {}
        location = descriptor.get("location") if isinstance(descriptor.get("location"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_lookup_status={result.status}",
            f"source_map_lookup_direction={request.get('lookup_direction', '')}",
            f"source_map_lookup_mapping_found={descriptor.get('mapping_found', False)}",
            f"source_map_lookup_strategy={location.get('strategy', '')}",
            "source_map_lookup_review_only=True",
            f"source_map_lookup_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_lookup_browser_started={policy.get('browser_started', False)}",
            f"source_map_lookup_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_lookup_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_lookup_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_lookup_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_lookup_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_lookup_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-lookup.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map lookup descriptor.",
            metadata={
                "status": result.status,
                "lookup_direction": request.get("lookup_direction", ""),
                "mapping_found": bool(descriptor.get("mapping_found", False)),
                "strategy": location.get("strategy", ""),
                "review_only": True,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
            },
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_map_lookup_before_debugger_or_hook_use"
            actions = ["review_source_map_lookup"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_payload_and_lookup_position"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_lookup_descriptor"
            actions = []
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    if owner._is_source_map_source_content_request(protection_name, context):
        spec = SourceMapSourceContentSpec.from_context(context)
        result = SourceMapSourceContentManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        request = descriptor.get("source_request") if isinstance(descriptor.get("source_request"), dict) else {}
        content_summary = descriptor.get("content_summary") if isinstance(descriptor.get("content_summary"), dict) else {}
        policy = result.side_effect_policy if isinstance(result.side_effect_policy, dict) else descriptor.get("side_effect_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        verification = [
            f"source_map_source_content_status={result.status}",
            f"source_map_source_content_available={descriptor.get('source_content_available', False)}",
            f"source_map_source_content_original_source={request.get('original_source', '')}",
            f"source_map_source_content_source_index={request.get('source_index')}",
            f"source_map_source_content_sha256={content_summary.get('sha256', '')}",
            "source_map_source_content_review_only=True",
            f"source_map_source_content_raw_exported={policy.get('raw_source_content_exported', False)}",
            f"source_map_source_content_preview_exported={policy.get('preview_exported', False)}",
            f"source_map_source_content_fetch_source_map={policy.get('fetch_source_map', False)}",
            f"source_map_source_content_browser_started={policy.get('browser_started', False)}",
            f"source_map_source_content_cdp_command_sent={policy.get('cdp_command_sent', False)}",
            f"source_map_source_content_runtime_evaluated={policy.get('runtime_evaluated', False)}",
            f"source_map_source_content_calls_mcp={policy.get('calls_mcp', False)}",
            f"source_map_source_content_mobile_runtime_used={policy.get('mobile_runtime_used', False)}",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"source_map_source_content_reason={result.reason}")
        if result.error:
            verification.append(f"source_map_source_content_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/source-map-source-content.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only Source Map sourcesContent availability descriptor.",
            metadata={
                "status": result.status,
                "source_content_available": bool(descriptor.get("source_content_available", False)),
                "original_source": request.get("original_source", ""),
                "source_index": request.get("source_index"),
                "sha256": content_summary.get("sha256", ""),
                "review_only": True,
                "raw_source_content_exported": False,
                "preview_exported": False,
                "fetch_source_map": False,
                "browser_started": False,
                "cdp_command_sent": False,
                "runtime_evaluated": False,
            },
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = descriptor.get("next_action") or "review_source_content_availability_before_debugger_or_rebuild"
            actions = ["review_source_map_source_content"]
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = descriptor.get("next_action") or "provide_source_map_with_sources_content"
            actions = []
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_source_map_source_content_descriptor"
            actions = []
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=actions,
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=str(next_action),
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
    if owner._is_bundler_symbol_scope_request(protection_name, context):
        spec = BundlerSymbolScopeSpec.from_context(context)
        result = BundlerSymbolScopeManager().review(spec)
        descriptor = result.descriptor if isinstance(result.descriptor, dict) else {}
        classification = descriptor.get("bundler_classification") if isinstance(descriptor.get("bundler_classification"), dict) else {}
        request = descriptor.get("symbol_request") if isinstance(descriptor.get("symbol_request"), dict) else {}
        verification = [
            f"bundler_symbol_scope_status={result.status}",
            f"bundler_symbol_scope_bundler={classification.get('bundler_kind', 'unknown')}",
            f"bundler_symbol_scope_candidate_count={descriptor.get('scope_candidate_count', 0)}",
            f"bundler_symbol_scope_symbol={request.get('symbol_name', '')}",
            "bundler_symbol_scope_review_only=True",
            "bundler_symbol_scope_fetch_source_map=False",
            "bundler_symbol_scope_logpoint_installed=False",
            "bundler_symbol_scope_cdp_command_sent=False",
            "bundler_symbol_scope_calls_mcp=False",
            "bundler_symbol_scope_mobile_runtime_used=False",
            f"context_keys={sorted(context.keys())}",
        ]
        if result.reason:
            verification.append(f"bundler_symbol_scope_reason={result.reason}")
        if result.error:
            verification.append(f"bundler_symbol_scope_error={result.error}")
        artifact = ArtifactRef(
            path="virtual://workspace/bundler-symbol-scope.json",
            kind=ArtifactKind.JSON,
            description="Native Web runtime review-only bundler symbol scope descriptor.",
            metadata={
                "status": result.status,
                "bundler_kind": classification.get("bundler_kind", "unknown"),
                "confidence": classification.get("confidence", "low"),
                "symbol_name": request.get("symbol_name", ""),
                "scope_candidate_count": descriptor.get("scope_candidate_count", 0),
                "review_only": True,
                "fetch_source_map": False,
                "logpoint_installed": False,
            },
        )
        if result.status == "ready_for_review":
            status = ExecutionStatus.SUCCESS
            next_action = "review_symbol_scope_before_source_logpoint_or_hook"
        elif result.status == "blocked":
            status = ExecutionStatus.PARTIAL
            next_action = "provide_source_map_symbol_and_original_source"
        else:
            status = ExecutionStatus.FAILED
            next_action = "inspect_bundler_symbol_scope_descriptor"
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=["review_bundler_symbol_scope"] if result.status in {"ready_for_review", "blocked"} else [],
            verification=verification,
            status=status,
            artifacts=[artifact],
            next_action=next_action,
            confidence=ConfidenceLevel.MEDIUM if result.status == "ready_for_review" else ConfidenceLevel.LOW,
        )
