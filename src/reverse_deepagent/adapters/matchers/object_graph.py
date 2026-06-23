from __future__ import annotations

from typing import Any


"""Object graph / page mutation request predicates for NativeWebRuntime."""

def _is_object_graph_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "object-graph-diff",
        "js-object-graph-diff",
        "review-object-graph-diff",
        "heap-object-graph-diff",
    }:
        return True
    return any(
        key in context
        for key in (
            "object_graph_diff",
            "objectGraphDiff",
            "js_object_graph_diff",
            "jsObjectGraphDiff",
            "review_object_graph_diff",
            "reviewObjectGraphDiff",
        )
    )


def _is_runtime_object_graph_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "runtime-object-graph-diff",
        "runtime-collected-object-graph-diff",
        "js-runtime-object-graph-diff",
        "collect-runtime-object-graph-diff",
        "scoped-runtime-object-graph-diff",
    }:
        return True
    return any(
        key in context
        for key in (
            "runtime_object_graph_diff",
            "runtimeObjectGraphDiff",
            "runtime_collected_object_graph_diff",
            "runtimeCollectedObjectGraphDiff",
            "js_runtime_object_graph_diff",
            "jsRuntimeObjectGraphDiff",
        )
    )


def _is_object_root_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
    if _is_runtime_object_graph_diff_request(protection_name, context):
        return False
    normalized = protection_name.strip().lower()
    if normalized in {
        "object-root-mutation-audit",
        "object-mutation-audit",
        "js-object-mutation-audit",
    }:
        return True
    return any(
        key in context
        for key in (
            "object_root_mutation_audit",
            "objectRootMutationAudit",
            "object_mutation_audit",
            "objectMutationAudit",
            "object_root",
            "objectRoot",
            "object_root_path",
            "objectRootPath",
            "root_path",
            "rootPath",
            "js_object_root",
            "jsObjectRoot",
        )
    )


def _is_page_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "page-mutation-audit",
        "page-mutation",
        "audit-page-mutation",
        "mutation-audit-page",
        "dom-mutation-audit",
    }:
        return True
    return any(
        key in context
        for key in (
            "page_mutation_audit",
            "pageMutationAudit",
            "audit_page_mutation",
            "auditPageMutation",
            "selected_globals",
            "selectedGlobals",
            "global_names",
            "globalNames",
        )
    )


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


