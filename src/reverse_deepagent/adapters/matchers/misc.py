from __future__ import annotations

from typing import Any

from reverse_deepagent.adapters.matchers.closure import (
    _is_closure_scope_discovery_request,
    _is_closure_wrapper_assignment_safety_request,
    _is_closure_wrapper_event_harvest_request,
    _is_closure_wrapper_replacement_execution_request,
    _is_closure_wrapper_replacement_plan_request,
    _is_closure_wrapper_restore_execution_request,
    _is_closure_wrapper_runtime_mutability_preflight_request,
)


def _is_breakpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"breakpoint", "set-breakpoint", "debugger-breakpoint"}:
            return True
        return any(key in context for key in ("url_pattern", "script_url", "line_number", "lineNumber"))


def _is_flow_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "flow-timeline",
            "cross-request-timeline",
            "request-flow-timeline",
            "continue-flow-timeline",
            "timeline-continuation",
        }:
            return True
        return any(
            key in context
            for key in (
                "flow_timeline",
                "flowTimeline",
                "previous_flow_timeline",
                "previousFlowTimeline",
                "flow_events",
                "flowEvents",
                "timeline_inputs",
                "timelineInputs",
            )
        )


def _is_mutation_observer_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "mutation-observer",
            "mutation-observer-timeline",
            "mutation-timeline",
            "page-mutation-timeline",
            "dom-mutation-timeline",
        }:
            return True
        return any(
            key in context
            for key in (
                "mutation_observer_timeline",
                "mutationObserverTimeline",
                "mutation_timeline",
                "mutationTimeline",
                "observer_wait_ms",
                "observerWaitMs",
                "mutation_record_limit",
                "mutationRecordLimit",
            )
        )


def _is_bundler_symbol_scope_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"bundler-symbol-scope", "source-map-symbol-scope", "review-bundler-symbol-scope", "plan-source-symbol-scope"}:
            return True
        return any(
            key in context
            for key in (
                "bundler_symbol_scope",
                "bundlerSymbolScope",
                "source_map_symbol_scope",
                "sourceMapSymbolScope",
                "review_bundler_symbol_scope",
                "reviewBundlerSymbolScope",
            )
        )


def _is_source_logpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"source-logpoint", "logpoint"}:
            return True
        return any(
            key in context
            for key in (
                "log_expression",
                "logExpression",
                "source_expression",
                "sourceExpression",
                "logpoint_id",
                "logpointId",
            )
        )


def _is_module_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"}:
            return True
        return any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        )


def _is_recursive_continuation_readiness_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "recursive-continuation-readiness",
            "traversal-continuation-readiness",
            "review-recursive-continuation-readiness",
            "review-traversal-continuation-readiness",
        }:
            return True
        return any(
            key in context
            for key in (
                "recursive_continuation_readiness",
                "recursiveContinuationReadiness",
                "recursive-continuation-readiness",
                "traversal_continuation_readiness",
                "traversalContinuationReadiness",
                "review_recursive_continuation_readiness",
                "reviewRecursiveContinuationReadiness",
            )
        )


def _is_function_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if _is_closure_wrapper_runtime_mutability_preflight_request(protection_name, context):
            return False
        if _is_closure_wrapper_assignment_safety_request(protection_name, context):
            return False
        if _is_closure_wrapper_event_harvest_request(protection_name, context):
            return False
        if _is_closure_wrapper_restore_execution_request(protection_name, context):
            return False
        if _is_closure_wrapper_replacement_execution_request(protection_name, context):
            return False
        if _is_closure_wrapper_replacement_plan_request(protection_name, context):
            return False
        if _is_closure_scope_discovery_request(protection_name, context):
            return False
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"} or any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        ):
            return False
        if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"} or any(
            key in context
            for key in (
                "module_id",
                "moduleId",
                "webpack_module_id",
                "webpackModuleId",
                "export_name",
                "exportName",
            )
        ):
            return False
        if normalized in {"hook-function", "function-hook", "target-function-hook"}:
            return True
        return any(
            key in context
            for key in (
                "function_name",
                "functionName",
                "function_path",
                "functionPath",
                "function_paths",
                "functionPaths",
                "hook_paths",
                "hookPaths",
                "candidate_id",
                "candidateId",
            )
        )


