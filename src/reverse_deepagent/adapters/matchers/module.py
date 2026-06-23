from __future__ import annotations

from typing import Any


"""Module / async chunk / custom loader request predicates for NativeWebRuntime."""

from .closure import _is_closure_scope_discovery_request, _is_closure_wrapper_assignment_safety_request, _is_closure_wrapper_event_harvest_request, _is_closure_wrapper_replacement_execution_request, _is_closure_wrapper_replacement_plan_request, _is_closure_wrapper_restore_execution_request, _is_closure_wrapper_runtime_mutability_preflight_request

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


def _is_module_federation_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-recursive-traversal-plan",
        "module-federation-traversal-recursion-plan",
        "plan-module-federation-recursive-traversal",
        "federation-recursive-traversal-plan",
        "remote-module-recursive-traversal-plan",
        "module-federation-recursive-traversal-followup",
        "execute-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-checkpoint",
        "reviewed-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-execution",
        "execute-module-federation-recursive-traversal-next-step",
        "reviewed-module-federation-recursive-traversal-execution",
    } or any(
        key in context
        for key in (
            "module_federation_recursive_traversal_plan",
            "moduleFederationRecursiveTraversalPlan",
            "module-federation-recursive-traversal-plan",
            "module_federation_traversal_recursion_plan",
            "moduleFederationTraversalRecursionPlan",
            "plan_module_federation_recursive_traversal",
            "planModuleFederationRecursiveTraversal",
            "federation_recursive_traversal_plan",
            "federationRecursiveTraversalPlan",
            "module_federation_recursive_traversal_followup",
            "moduleFederationRecursiveTraversalFollowup",
            "module-federation-recursive-traversal-followup",
            "execute_module_federation_recursive_traversal_followup",
            "executeModuleFederationRecursiveTraversalFollowup",
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "execute_module_federation_recursive_traversal_next_step",
            "executeModuleFederationRecursiveTraversalNextStep",
        )
    ):
        return False
    if normalized in {
        "module-federation-traversal-workflow-execution",
        "module-federation-remote-traversal-workflow-execution",
        "federation-traversal-workflow-execution",
        "remote-module-traversal-workflow-execution",
        "execute-module-federation-traversal-workflow",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_traversal_workflow_execution",
            "moduleFederationTraversalWorkflowExecution",
            "module-federation-traversal-workflow-execution",
            "federation_traversal_workflow_execution",
            "federationTraversalWorkflowExecution",
            "execute_module_federation_traversal_workflow",
            "executeModuleFederationTraversalWorkflow",
        )
    )


def _is_module_federation_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-recursive-traversal-followup",
        "execute-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-checkpoint",
        "reviewed-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-execution",
        "execute-module-federation-recursive-traversal-next-step",
        "reviewed-module-federation-recursive-traversal-execution",
    } or any(
        key in context
        for key in (
            "module_federation_recursive_traversal_followup",
            "moduleFederationRecursiveTraversalFollowup",
            "module-federation-recursive-traversal-followup",
            "execute_module_federation_recursive_traversal_followup",
            "executeModuleFederationRecursiveTraversalFollowup",
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "execute_module_federation_recursive_traversal_next_step",
            "executeModuleFederationRecursiveTraversalNextStep",
        )
    ):
        return False
    if normalized in {
        "module-federation-recursive-traversal-plan",
        "module-federation-traversal-recursion-plan",
        "plan-module-federation-recursive-traversal",
        "federation-recursive-traversal-plan",
        "remote-module-recursive-traversal-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_recursive_traversal_plan",
            "moduleFederationRecursiveTraversalPlan",
            "module-federation-recursive-traversal-plan",
            "module_federation_traversal_recursion_plan",
            "moduleFederationTraversalRecursionPlan",
            "plan_module_federation_recursive_traversal",
            "planModuleFederationRecursiveTraversal",
            "federation_recursive_traversal_plan",
            "federationRecursiveTraversalPlan",
        )
    )


def _is_module_federation_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-recursive-traversal-execution",
        "execute-module-federation-recursive-traversal-next-step",
        "reviewed-module-federation-recursive-traversal-execution",
    } or any(
        key in context
        for key in (
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "execute_module_federation_recursive_traversal_next_step",
            "executeModuleFederationRecursiveTraversalNextStep",
        )
    ):
        return False
    if normalized in {
        "module-federation-recursive-traversal-followup",
        "execute-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-checkpoint",
        "reviewed-module-federation-recursive-traversal-followup",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_recursive_traversal_followup",
            "moduleFederationRecursiveTraversalFollowup",
            "module-federation-recursive-traversal-followup",
            "execute_module_federation_recursive_traversal_followup",
            "executeModuleFederationRecursiveTraversalFollowup",
        )
    )


def _is_module_federation_recursive_continuation_journal_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if _is_module_federation_recursive_continuation_checkpoint_request(protection_name, context):
        return False
    if normalized in {
        "module-federation-recursive-continuation-journal",
        "module-federation-recursive-traversal-continuation-journal",
        "plan-module-federation-recursive-continuation",
        "append-module-federation-recursive-continuation-journal",
        "reviewed-module-federation-recursive-continuation-journal",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_recursive_continuation_journal",
            "moduleFederationRecursiveContinuationJournal",
            "module-federation-recursive-continuation-journal",
            "module_federation_recursive_traversal_continuation_journal",
            "moduleFederationRecursiveTraversalContinuationJournal",
            "module-federation-recursive-traversal-continuation-journal",
            "append_module_federation_recursive_continuation_journal",
            "appendModuleFederationRecursiveContinuationJournal",
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


def _is_module_federation_recursive_continuation_checkpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-recursive-continuation-checkpoint",
        "module-federation-recursive-traversal-continuation-checkpoint",
        "execute-module-federation-recursive-continuation-checkpoint",
        "execute-module-federation-recursive-traversal-continuation-checkpoint",
        "reviewed-module-federation-recursive-continuation-checkpoint",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_recursive_continuation_checkpoint",
            "moduleFederationRecursiveContinuationCheckpoint",
            "module-federation-recursive-continuation-checkpoint",
            "module_federation_recursive_traversal_continuation_checkpoint",
            "moduleFederationRecursiveTraversalContinuationCheckpoint",
            "module-federation-recursive-traversal-continuation-checkpoint",
            "execute_module_federation_recursive_continuation_checkpoint",
            "executeModuleFederationRecursiveContinuationCheckpoint",
            "reviewed_module_federation_recursive_continuation_checkpoint",
            "reviewedModuleFederationRecursiveContinuationCheckpoint",
        )
    )


def _is_module_federation_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-recursive-traversal-execution",
        "execute-module-federation-recursive-traversal-next-step",
        "reviewed-module-federation-recursive-traversal-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_recursive_traversal_execution",
            "moduleFederationRecursiveTraversalExecution",
            "module-federation-recursive-traversal-execution",
            "execute_module_federation_recursive_traversal",
            "executeModuleFederationRecursiveTraversal",
            "execute_module_federation_recursive_traversal_next_step",
            "executeModuleFederationRecursiveTraversalNextStep",
        )
    )


def _is_module_federation_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-traversal-workflow-plan",
        "module-federation-remote-traversal-workflow-plan",
        "federation-traversal-workflow-plan",
        "remote-module-traversal-workflow-plan",
        "plan-module-federation-traversal-workflow",
        "module-federation-traversal-workflow-execution",
        "execute-module-federation-traversal-workflow",
        "module-federation-recursive-traversal-plan",
        "module-federation-traversal-recursion-plan",
        "plan-module-federation-recursive-traversal",
        "module-federation-recursive-traversal-followup",
        "execute-module-federation-recursive-traversal-followup",
        "module-federation-recursive-traversal-checkpoint",
        "module-federation-recursive-traversal-execution",
        "execute-module-federation-recursive-traversal-next-step",
        "reviewed-module-federation-recursive-traversal-execution",
    } or any(key in context for key in (
        "module_federation_traversal_workflow_execution",
        "moduleFederationTraversalWorkflowExecution",
        "module-federation-traversal-workflow-execution",
        "execute_module_federation_traversal_workflow",
        "executeModuleFederationTraversalWorkflow",
        "module_federation_recursive_traversal_plan",
        "moduleFederationRecursiveTraversalPlan",
        "module-federation-recursive-traversal-plan",
        "module_federation_traversal_recursion_plan",
        "moduleFederationTraversalRecursionPlan",
        "plan_module_federation_recursive_traversal",
        "planModuleFederationRecursiveTraversal",
        "module_federation_recursive_traversal_followup",
        "moduleFederationRecursiveTraversalFollowup",
        "module-federation-recursive-traversal-followup",
        "execute_module_federation_recursive_traversal_followup",
        "executeModuleFederationRecursiveTraversalFollowup",
        "module_federation_recursive_traversal_execution",
        "moduleFederationRecursiveTraversalExecution",
        "module-federation-recursive-traversal-execution",
        "execute_module_federation_recursive_traversal_next_step",
        "executeModuleFederationRecursiveTraversalNextStep",
        "module_federation_traversal_workflow_plan",
        "moduleFederationTraversalWorkflowPlan",
        "module-federation-traversal-workflow-plan",
        "federation_traversal_workflow_plan",
        "federationTraversalWorkflowPlan",
        "plan_module_federation_traversal_workflow",
        "planModuleFederationTraversalWorkflow",
    )):
        return False
    if normalized in {
        "module-federation-traversal-graph",
        "module-federation-remote-traversal-graph",
        "federation-traversal-graph",
        "remote-module-traversal-graph",
        "plan-module-federation-traversal-graph",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_traversal_graph",
            "moduleFederationTraversalGraph",
            "module-federation-traversal-graph",
            "federation_traversal_graph",
            "federationTraversalGraph",
            "remote_module_traversal_graph",
            "remoteModuleTraversalGraph",
        )
    )


def _is_module_federation_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-traversal-workflow-plan",
        "module-federation-remote-traversal-workflow-plan",
        "federation-traversal-workflow-plan",
        "remote-module-traversal-workflow-plan",
        "plan-module-federation-traversal-workflow",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_traversal_workflow_plan",
            "moduleFederationTraversalWorkflowPlan",
            "module-federation-traversal-workflow-plan",
            "federation_traversal_workflow_plan",
            "federationTraversalWorkflowPlan",
            "plan_module_federation_traversal_workflow",
            "planModuleFederationTraversalWorkflow",
        )
    )


def _is_module_federation_get_init_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-get-init",
        "module-federation-get-init-plan",
        "federation-get-init",
        "federation-get-init-plan",
        "module-federation-plan",
        "federation-analysis-plan",
        "module-federation-export-hook-plan",
        "module-federation-export-hooks",
        "remote-export-hook-plan",
        "remote-export-hooks",
        "module-federation-export-hook-install",
        "module-federation-remote-export-hook",
        "remote-export-hook-install",
        "hook-module-federation-remote-export",
        "reviewed-remote-export-hook",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_get_init",
            "moduleFederationGetInit",
            "federation_get_init_plan",
            "federationGetInitPlan",
            "module_federation_plan",
            "moduleFederationPlan",
            "module_federation_candidate",
            "moduleFederationCandidate",
            "module_federation_candidates",
            "moduleFederationCandidates",
            "federation_candidate",
            "federationCandidate",
            "federation_candidates",
            "federationCandidates",
            "federation_modules",
            "federationModules",
            "exposed_modules",
            "exposedModules",
            "execute_module_federation_export_hook",
            "executeModuleFederationExportHook",
            "hook_module_federation_remote_export",
            "hookModuleFederationRemoteExport",
            "install_remote_export_hook",
            "installRemoteExportHook",
            "reviewed_remote_export_hook",
            "reviewedRemoteExportHook",
        )
    )


def _is_module_federation_get_init_probe_request(context: dict[str, Any]) -> bool:
    return any(
        bool(context.get(key))
        for key in (
            "execute_module_federation_get_init",
            "executeModuleFederationGetInit",
            "probe_module_federation_get_init",
            "probeModuleFederationGetInit",
            "execute_get_init",
            "executeGetInit",
        )
    )


def _is_module_federation_factory_invoke_request(context: dict[str, Any]) -> bool:
    return any(
        bool(context.get(key))
        for key in (
            "execute_module_federation_factory",
            "executeModuleFederationFactory",
            "invoke_module_federation_factory",
            "invokeModuleFederationFactory",
            "execute_remote_factory",
            "executeRemoteFactory",
            "invoke_remote_factory",
            "invokeRemoteFactory",
        )
    )


def _is_module_federation_export_hook_install_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-export-hook-install",
        "module-federation-remote-export-hook",
        "remote-export-hook-install",
        "hook-module-federation-remote-export",
        "reviewed-remote-export-hook",
    }:
        return True
    return any(
        bool(context.get(key))
        for key in (
            "execute_module_federation_export_hook",
            "executeModuleFederationExportHook",
            "hook_module_federation_remote_export",
            "hookModuleFederationRemoteExport",
            "install_remote_export_hook",
            "installRemoteExportHook",
            "reviewed_remote_export_hook",
            "reviewedRemoteExportHook",
        )
    )


def _is_module_federation_export_hook_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "module-federation-export-hook-plan",
        "module-federation-export-hooks",
        "remote-export-hook-plan",
        "remote-export-hooks",
    }:
        return True
    return any(
        key in context
        for key in (
            "module_federation_export_hook_plan",
            "moduleFederationExportHookPlan",
            "remote_export_hook_plan",
            "remoteExportHookPlan",
            "module_federation_factory_invoke_result",
            "moduleFederationFactoryInvokeResult",
            "module-federation-factory-invoke-result",
        )
    )


def _is_custom_loader_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-execution",
        "execute-custom-loader",
        "reviewed-custom-loader-execution",
        "custom-loader-execute",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_execution",
            "customLoaderExecution",
            "execute_custom_loader",
            "executeCustomLoader",
            "reviewed_custom_loader_execution",
            "reviewedCustomLoaderExecution",
        )
    ) and any(
        key in context
        for key in (
            "custom_loader_execution_preflight",
            "customLoaderExecutionPreflight",
            "custom-loader-execution-preflight",
            "custom_loader_preflight",
            "customLoaderPreflight",
        )
    )


def _is_custom_loader_continuation_workflow_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-continuation-workflow",
        "custom-loader-continuation-plan",
        "plan-custom-loader-continuation",
        "review-custom-loader-continuation-workflow",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_continuation_workflow",
            "customLoaderContinuationWorkflow",
            "custom-loader-continuation-workflow",
            "plan_custom_loader_continuation_workflow",
            "planCustomLoaderContinuationWorkflow",
        )
    )


def _is_custom_loader_continuation_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-continuation-execution",
        "execute-custom-loader-continuation-step",
        "custom-loader-continuation-step",
        "reviewed-custom-loader-continuation-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_continuation_execution",
            "customLoaderContinuationExecution",
            "custom-loader-continuation-execution",
            "execute_custom_loader_continuation_step",
            "executeCustomLoaderContinuationStep",
        )
    )


def _is_custom_loader_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-traversal-workflow-execution",
        "execute-custom-loader-traversal-workflow",
        "custom-loader-traversal-workflow-step",
        "reviewed-custom-loader-traversal-workflow-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal_workflow_execution",
            "customLoaderTraversalWorkflowExecution",
            "custom-loader-traversal-workflow-execution",
            "execute_custom_loader_traversal_workflow",
            "executeCustomLoaderTraversalWorkflow",
        )
    )


def _is_custom_loader_traversal_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-traversal-loop-execution",
        "execute-custom-loader-traversal-loop",
        "custom-loader-bounded-loop-execution",
        "reviewed-custom-loader-traversal-loop-execution",
        "custom-loader-recursive-traversal-plan",
        "custom-loader-traversal-recursion-plan",
        "plan-custom-loader-recursive-traversal",
    } or any(
        key in context
        for key in (
            "custom_loader_traversal_loop_execution",
            "customLoaderTraversalLoopExecution",
            "custom-loader-traversal-loop-execution",
            "execute_custom_loader_traversal_loop",
            "executeCustomLoaderTraversalLoop",
            "custom_loader_recursive_traversal_plan",
            "customLoaderRecursiveTraversalPlan",
            "custom-loader-recursive-traversal-plan",
            "custom_loader_traversal_recursion_plan",
            "customLoaderTraversalRecursionPlan",
            "plan_custom_loader_recursive_traversal",
            "planCustomLoaderRecursiveTraversal",
        )
    ):
        return False
    if normalized in {
        "custom-loader-traversal-loop-plan",
        "custom-loader-deep-traversal-loop",
        "plan-custom-loader-traversal-loop",
        "custom-loader-bounded-traversal-loop",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal_loop_plan",
            "customLoaderTraversalLoopPlan",
            "custom-loader-traversal-loop-plan",
            "custom_loader_deep_traversal_loop",
            "customLoaderDeepTraversalLoop",
            "plan_custom_loader_traversal_loop",
            "planCustomLoaderTraversalLoop",
        )
    )


def _is_custom_loader_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-recursive-traversal-execution",
        "execute-custom-loader-recursive-traversal",
        "execute-custom-loader-recursive-traversal-next-loop",
        "reviewed-custom-loader-recursive-traversal-execution",
        "custom-loader-recursive-traversal-followup",
        "execute-custom-loader-recursive-traversal-followup",
        "custom-loader-recursive-traversal-checkpoint",
        "reviewed-custom-loader-recursive-traversal-followup",
    } or any(
        key in context
        for key in (
            "custom_loader_recursive_traversal_execution",
            "customLoaderRecursiveTraversalExecution",
            "custom-loader-recursive-traversal-execution",
            "execute_custom_loader_recursive_traversal",
            "executeCustomLoaderRecursiveTraversal",
            "custom_loader_recursive_traversal_followup",
            "customLoaderRecursiveTraversalFollowup",
            "custom-loader-recursive-traversal-followup",
            "execute_custom_loader_recursive_traversal_followup",
            "executeCustomLoaderRecursiveTraversalFollowup",
        )
    ):
        return False
    if normalized in {
        "custom-loader-recursive-traversal-plan",
        "custom-loader-traversal-recursion-plan",
        "plan-custom-loader-recursive-traversal",
        "custom-loader-deeper-recursive-traversal",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_recursive_traversal_plan",
            "customLoaderRecursiveTraversalPlan",
            "custom-loader-recursive-traversal-plan",
            "custom_loader_traversal_recursion_plan",
            "customLoaderTraversalRecursionPlan",
            "plan_custom_loader_recursive_traversal",
            "planCustomLoaderRecursiveTraversal",
        )
    )


def _is_custom_loader_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-recursive-traversal-execution",
        "execute-custom-loader-recursive-traversal",
        "execute-custom-loader-recursive-traversal-next-loop",
        "reviewed-custom-loader-recursive-traversal-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_recursive_traversal_execution",
            "customLoaderRecursiveTraversalExecution",
            "custom-loader-recursive-traversal-execution",
            "execute_custom_loader_recursive_traversal",
            "executeCustomLoaderRecursiveTraversal",
            "execute_custom_loader_recursive_traversal_next_loop",
            "executeCustomLoaderRecursiveTraversalNextLoop",
        )
    )


def _is_custom_loader_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-recursive-traversal-execution",
        "execute-custom-loader-recursive-traversal",
        "execute-custom-loader-recursive-traversal-next-loop",
        "reviewed-custom-loader-recursive-traversal-execution",
    } or any(
        key in context
        for key in (
            "custom_loader_recursive_traversal_execution",
            "customLoaderRecursiveTraversalExecution",
            "custom-loader-recursive-traversal-execution",
            "execute_custom_loader_recursive_traversal",
            "executeCustomLoaderRecursiveTraversal",
        )
    ):
        return False
    if normalized in {
        "custom-loader-recursive-traversal-followup",
        "execute-custom-loader-recursive-traversal-followup",
        "custom-loader-recursive-traversal-checkpoint",
        "reviewed-custom-loader-recursive-traversal-followup",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_recursive_traversal_followup",
            "customLoaderRecursiveTraversalFollowup",
            "custom-loader-recursive-traversal-followup",
            "execute_custom_loader_recursive_traversal_followup",
            "executeCustomLoaderRecursiveTraversalFollowup",
        )
    )


def _is_custom_loader_traversal_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-traversal-loop-execution",
        "execute-custom-loader-traversal-loop",
        "custom-loader-bounded-loop-execution",
        "reviewed-custom-loader-traversal-loop-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal_loop_execution",
            "customLoaderTraversalLoopExecution",
            "custom-loader-traversal-loop-execution",
            "execute_custom_loader_traversal_loop",
            "executeCustomLoaderTraversalLoop",
        )
    )


def _is_custom_loader_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-traversal-workflow-plan",
        "custom-loader-deep-traversal-workflow",
        "plan-custom-loader-traversal-workflow",
        "custom-loader-multi-step-traversal-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal_workflow_plan",
            "customLoaderTraversalWorkflowPlan",
            "custom-loader-traversal-workflow-plan",
            "custom_loader_deep_traversal_workflow",
            "customLoaderDeepTraversalWorkflow",
            "plan_custom_loader_traversal_workflow",
            "planCustomLoaderTraversalWorkflow",
        )
    )


def _is_custom_loader_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-traversal-graph",
        "custom-loader-continuation-queue",
        "plan-custom-loader-deep-traversal",
        "custom-loader-deep-traversal-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal_graph",
            "customLoaderTraversalGraph",
            "custom-loader-traversal-graph",
            "custom_loader_continuation_queue",
            "customLoaderContinuationQueue",
            "plan_custom_loader_deep_traversal",
            "planCustomLoaderDeepTraversal",
        )
    )


def _is_custom_loader_continuation_journal_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-continuation-journal",
        "append-custom-loader-continuation-journal",
        "custom-loader-continuation-journal-append",
        "review-custom-loader-continuation-journal",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_continuation_journal",
            "customLoaderContinuationJournal",
            "custom-loader-continuation-journal",
            "append_custom_loader_continuation_journal",
            "appendCustomLoaderContinuationJournal",
        )
    )


def _is_custom_loader_execution_preflight_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-execution-preflight",
        "custom-loader-preflight",
        "preflight-custom-loader-execution",
        "review-custom-loader-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_execution_preflight",
            "customLoaderExecutionPreflight",
            "execute_custom_loader",
            "executeCustomLoader",
            "custom_loader_traversal_plan",
            "customLoaderTraversalPlan",
            "custom-loader-traversal-plan",
        )
    ) and any(
        key in context
        for key in (
            "selected_custom_loader_candidate",
            "selectedCustomLoaderCandidate",
            "selected_loader_candidate",
            "selectedLoaderCandidate",
            "selected_candidate",
            "selectedCandidate",
            "candidate_index",
            "candidateIndex",
        )
    )


def _is_custom_loader_traversal_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if (
        normalized.startswith("async-chunk-")
        or "async-chunk-recursive-traversal" in normalized
        or normalized in {"deep-async-chunk-traversal", "plan-async-chunk-deep-traversal"}
        or any(key in context for key in (
            "async_chunk_recursive_traversal_plan",
            "asyncChunkRecursiveTraversalPlan",
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
        ))
    ):
        return False
    if normalized in {
        "custom-loader-traversal",
        "custom-loader-traversal-plan",
        "loader-traversal-plan",
        "custom-loader-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_traversal",
            "customLoaderTraversal",
            "loader_traversal_plan",
            "loaderTraversalPlan",
            "custom_loader_candidate",
            "customLoaderCandidate",
            "custom_loader_candidates",
            "customLoaderCandidates",
            "loader_candidates",
            "loaderCandidates",
            "chunk_graph",
            "chunkGraph",
        )
    )


def _is_async_chunk_traversal_graph_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-traversal-graph",
        "async-chunk-graph-queue",
        "plan-async-chunk-deep-traversal",
        "async-chunk-deep-traversal-graph",
        "deep-async-chunk-traversal",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_traversal_graph",
            "asyncChunkTraversalGraph",
            "async-chunk-traversal-graph",
            "async_chunk_graph_queue",
            "asyncChunkGraphQueue",
            "plan_async_chunk_deep_traversal",
            "planAsyncChunkDeepTraversal",
        )
    )


def _is_async_chunk_recursive_traversal_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-recursive-traversal-execution",
        "execute-async-chunk-recursive-traversal",
        "execute-async-chunk-recursive-traversal-next-loop",
        "reviewed-async-chunk-recursive-traversal-execution",
        "async-chunk-recursive-traversal-followup",
        "execute-async-chunk-recursive-traversal-followup",
        "async-chunk-recursive-traversal-checkpoint",
        "reviewed-async-chunk-recursive-traversal-followup",
    } or any(
        key in context
        for key in (
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "async-chunk-recursive-traversal-execution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
            "async-chunk-recursive-traversal-followup",
            "execute_async_chunk_recursive_traversal_followup",
            "executeAsyncChunkRecursiveTraversalFollowup",
        )
    ):
        return False
    if normalized in {
        "async-chunk-recursive-traversal-plan",
        "async-chunk-traversal-recursion-plan",
        "plan-async-chunk-recursive-traversal",
        "async-chunk-deeper-recursive-traversal",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_recursive_traversal_plan",
            "asyncChunkRecursiveTraversalPlan",
            "async-chunk-recursive-traversal-plan",
            "async_chunk_traversal_recursion_plan",
            "asyncChunkTraversalRecursionPlan",
            "plan_async_chunk_recursive_traversal",
            "planAsyncChunkRecursiveTraversal",
        )
    )


def _is_async_chunk_recursive_traversal_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-recursive-traversal-execution",
        "execute-async-chunk-recursive-traversal",
        "execute-async-chunk-recursive-traversal-next-loop",
        "reviewed-async-chunk-recursive-traversal-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "async-chunk-recursive-traversal-execution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
            "execute_async_chunk_recursive_traversal_next_loop",
            "executeAsyncChunkRecursiveTraversalNextLoop",
        )
    )


def _is_async_chunk_recursive_traversal_followup_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-recursive-traversal-execution",
        "execute-async-chunk-recursive-traversal",
        "execute-async-chunk-recursive-traversal-next-loop",
        "reviewed-async-chunk-recursive-traversal-execution",
    } or any(
        key in context
        for key in (
            "async_chunk_recursive_traversal_execution",
            "asyncChunkRecursiveTraversalExecution",
            "async-chunk-recursive-traversal-execution",
            "execute_async_chunk_recursive_traversal",
            "executeAsyncChunkRecursiveTraversal",
        )
    ):
        return False
    if normalized in {
        "async-chunk-recursive-traversal-followup",
        "execute-async-chunk-recursive-traversal-followup",
        "async-chunk-recursive-traversal-checkpoint",
        "reviewed-async-chunk-recursive-traversal-followup",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_recursive_traversal_followup",
            "asyncChunkRecursiveTraversalFollowup",
            "async-chunk-recursive-traversal-followup",
            "execute_async_chunk_recursive_traversal_followup",
            "executeAsyncChunkRecursiveTraversalFollowup",
        )
    )


def _is_async_chunk_traversal_loop_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-recursive-traversal-plan",
        "async-chunk-traversal-recursion-plan",
        "plan-async-chunk-recursive-traversal",
        "async-chunk-recursive-traversal-followup",
        "execute-async-chunk-recursive-traversal-followup",
        "async-chunk-recursive-traversal-checkpoint",
        "async-chunk-recursive-traversal-execution",
        "execute-async-chunk-recursive-traversal",
        "execute-async-chunk-recursive-traversal-next-loop",
    } or any(key in context for key in (
        "async_chunk_recursive_traversal_plan",
        "asyncChunkRecursiveTraversalPlan",
        "async_chunk_recursive_traversal_followup",
        "asyncChunkRecursiveTraversalFollowup",
        "async_chunk_recursive_traversal_execution",
        "asyncChunkRecursiveTraversalExecution",
        "execute_async_chunk_recursive_traversal",
        "executeAsyncChunkRecursiveTraversal",
    )):
        return False
    if normalized in {
        "async-chunk-traversal-loop-plan",
        "async-chunk-deep-traversal-loop",
        "plan-async-chunk-traversal-loop",
        "async-chunk-bounded-traversal-loop",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_traversal_loop_plan",
            "asyncChunkTraversalLoopPlan",
            "async-chunk-traversal-loop-plan",
            "async_chunk_deep_traversal_loop",
            "asyncChunkDeepTraversalLoop",
            "plan_async_chunk_traversal_loop",
            "planAsyncChunkTraversalLoop",
        )
    )


def _is_async_chunk_traversal_loop_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-recursive-traversal-execution",
        "execute-async-chunk-recursive-traversal",
        "execute-async-chunk-recursive-traversal-next-loop",
        "async-chunk-recursive-traversal-followup",
        "execute-async-chunk-recursive-traversal-followup",
    } or any(key in context for key in (
        "async_chunk_recursive_traversal_execution",
        "asyncChunkRecursiveTraversalExecution",
        "execute_async_chunk_recursive_traversal",
        "executeAsyncChunkRecursiveTraversal",
        "async_chunk_recursive_traversal_followup",
        "asyncChunkRecursiveTraversalFollowup",
    )):
        return False
    if normalized in {
        "async-chunk-traversal-loop-execution",
        "execute-async-chunk-traversal-loop",
        "async-chunk-bounded-loop-execution",
        "reviewed-async-chunk-traversal-loop-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_traversal_loop_execution",
            "asyncChunkTraversalLoopExecution",
            "async-chunk-traversal-loop-execution",
            "execute_async_chunk_traversal_loop",
            "executeAsyncChunkTraversalLoop",
        )
    )


def _is_async_chunk_traversal_workflow_execution_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-traversal-workflow-execution",
        "execute-async-chunk-traversal-workflow",
        "async-chunk-traversal-workflow-step",
        "reviewed-async-chunk-traversal-workflow-execution",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_traversal_workflow_execution",
            "asyncChunkTraversalWorkflowExecution",
            "async-chunk-traversal-workflow-execution",
            "execute_async_chunk_traversal_workflow",
            "executeAsyncChunkTraversalWorkflow",
        )
    )


def _is_async_chunk_traversal_workflow_plan_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-traversal-workflow-plan",
        "async-chunk-deep-traversal-workflow",
        "plan-async-chunk-traversal-workflow",
        "async-chunk-multi-step-traversal-plan",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_traversal_workflow_plan",
            "asyncChunkTraversalWorkflowPlan",
            "async-chunk-traversal-workflow-plan",
            "async_chunk_deep_traversal_workflow",
            "asyncChunkDeepTraversalWorkflow",
            "plan_async_chunk_traversal_workflow",
            "planAsyncChunkTraversalWorkflow",
        )
    )


def _is_async_chunk_load_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"async-chunk-load", "load-async-chunk", "chunk-load", "webpack-chunk-load"}:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_load",
            "asyncChunkLoad",
            "execute_chunk_load",
            "executeChunkLoad",
            "chunk_candidate",
            "chunkCandidate",
            "chunk_id",
            "chunkId",
        )
    )


def _is_async_chunk_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-module-hook",
        "async-chunk-hook-module",
        "hook-async-chunk-module",
        "reviewed-async-chunk-module-hook",
    }:
        return True
    return any(
        key in context
        for key in (
            "execute_async_chunk_module_hook",
            "executeAsyncChunkModuleHook",
            "hook_async_chunk_module",
            "hookAsyncChunkModule",
            "reviewed_async_chunk_module_hook",
            "reviewedAsyncChunkModuleHook",
        )
    )


def _is_custom_loader_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-module-hook",
        "custom-loader-hook-module",
        "hook-custom-loader-module",
        "reviewed-custom-loader-module-hook",
    }:
        return True
    return any(
        key in context
        for key in (
            "execute_custom_loader_module_hook",
            "executeCustomLoaderModuleHook",
            "hook_custom_loader_module",
            "hookCustomLoaderModule",
            "reviewed_custom_loader_module_hook",
            "reviewedCustomLoaderModuleHook",
        )
    )


def _is_async_chunk_module_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "async-chunk-module-diff",
        "async-chunk-hook-candidates",
        "chunk-module-diff",
        "chunk-hook-candidates",
    }:
        return True
    return any(
        key in context
        for key in (
            "async_chunk_module_diff",
            "asyncChunkModuleDiff",
            "async_chunk_hook_candidates",
            "asyncChunkHookCandidates",
        )
    )


def _is_custom_loader_module_diff_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {
        "custom-loader-module-diff",
        "custom-loader-hook-candidates",
        "custom-loader-execution-module-diff",
        "custom-loader-execution-diff",
    }:
        return True
    return any(
        key in context
        for key in (
            "custom_loader_module_diff",
            "customLoaderModuleDiff",
            "custom_loader_hook_candidates",
            "customLoaderHookCandidates",
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


def _is_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
    normalized = protection_name.strip().lower()
    if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"}:
        return True
    return any(
        key in context
        for key in (
            "module_id",
            "moduleId",
            "webpack_module_id",
            "webpackModuleId",
            "export_name",
            "exportName",
        )
    )


