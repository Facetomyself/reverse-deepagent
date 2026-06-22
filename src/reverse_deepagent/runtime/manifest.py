from __future__ import annotations

from pathlib import Path
from typing import Any

from reverse_deepagent.runtime.base import RuntimeArtifactManifest, RuntimeArtifactManifestEntry, RuntimeBackendCapabilities
from reverse_deepagent.workspace_contract import workspace_manifest_alias_metadata


def _build_backend_artifact_manifest(
    capabilities: RuntimeBackendCapabilities,
    output_paths: dict[str, str],
    extra_artifacts: list[dict[str, Any]] | None = None,
) -> RuntimeArtifactManifest:
    entries = [
        RuntimeArtifactManifestEntry(
            artifact_key=key,
            path=path,
            category=_artifact_category_from_key(key),
            kind=_artifact_kind_from_path(path),
            producer_backend_id=capabilities.backend_id,
            producer_transport=capabilities.transport,
            target_platforms=capabilities.target_platforms,
            description=_artifact_description_from_key(key),
            metadata=_artifact_manifest_entry_metadata(capabilities, key, path),
        )
        for key, path in sorted(output_paths.items())
    ]
    entries.extend(_runtime_artifact_manifest_entries(capabilities, extra_artifacts or []))
    return RuntimeArtifactManifest(
        producer_backend_id=capabilities.backend_id,
        producer_transport=capabilities.transport,
        target_platforms=capabilities.target_platforms,
        entries=entries,
    )


ARTIFACT_CATEGORY_BY_KEY = {
    "workspace_network_requests": "network",
    "workspace_source_hits": "source",
    "workspace_source_contexts": "source",
    "workspace_script_inventory": "source",
    "workspace_response_bodies": "network",
    "workspace_websocket_frames": "network",
    "workspace_hook_timeline": "hook-timeline",
    "workspace_flow_timeline": "trace",
    "workspace_stitched_flow": "trace",
    "workspace_function_hooks": "hook-timeline",
    "workspace_function_hook_timeline": "hook-timeline",
    "workspace_module_hooks": "hook-timeline",
    "workspace_module_hook_timeline": "hook-timeline",
    "workspace_async_chunk_load_plan": "triage",
    "workspace_async_chunk_traversal_graph": "triage",
    "workspace_async_chunk_traversal_workflow_plan": "triage",
    "workspace_async_chunk_traversal_workflow_execution": "audit",
    "workspace_async_chunk_traversal_loop_plan": "triage",
    "workspace_async_chunk_traversal_loop_execution": "audit",
    "workspace_async_chunk_recursive_traversal_plan": "triage",
    "workspace_async_chunk_recursive_traversal_followup": "audit",
    "workspace_async_chunk_recursive_traversal_execution": "audit",
    "workspace_async_chunk_module_diff": "triage",
    "workspace_custom_loader_traversal_plan": "triage",
    "workspace_custom_loader_traversal_graph": "triage",
    "workspace_custom_loader_traversal_workflow_plan": "triage",
    "workspace_custom_loader_traversal_workflow_execution": "audit",
    "workspace_custom_loader_traversal_loop_plan": "triage",
    "workspace_custom_loader_traversal_loop_execution": "audit",
    "workspace_custom_loader_recursive_traversal_plan": "triage",
    "workspace_custom_loader_recursive_traversal_followup": "audit",
    "workspace_custom_loader_recursive_traversal_execution": "audit",
    "workspace_custom_loader_continuation_workflow": "triage",
    "workspace_custom_loader_continuation_journal": "audit",
    "workspace_custom_loader_continuation_execution": "audit",
    "workspace_custom_loader_execution_preflight": "triage",
    "workspace_custom_loader_execution_result": "trace",
    "workspace_custom_loader_module_diff": "triage",
    "workspace_module_federation_get_init_plan": "triage",
    "workspace_module_federation_get_init_result": "trace",
    "workspace_module_federation_factory_invoke_result": "trace",
    "workspace_module_federation_export_hook_plan": "triage",
    "workspace_module_federation_traversal_graph": "triage",
    "workspace_module_federation_traversal_workflow_plan": "triage",
    "workspace_module_federation_traversal_workflow_execution": "audit",
    "workspace_module_federation_recursive_traversal_plan": "triage",
    "workspace_module_federation_recursive_traversal_followup": "audit",
    "workspace_module_federation_recursive_traversal_execution": "audit",
    "workspace_module_federation_recursive_continuation_journal": "audit",
    "workspace_module_federation_recursive_continuation_checkpoint": "audit",
    "workspace_recursive_continuation_readiness": "audit",
    "workspace_async_chunk_load_result": "trace",
    "workspace_source_map_fetch_plan": "triage",
    "workspace_source_map_fetch_result": "trace",
    "workspace_source_map_lookup": "triage",
    "workspace_source_map_source_content": "triage",
    "workspace_source_map_readiness": "triage",
    "workspace_source_map_consumer_action_plan": "triage",
    "workspace_source_map_consumer_materialization": "triage",
    "workspace_source_map_typed_payload_preflight": "triage",
    "workspace_source_map_followthrough_review": "triage",
    "workspace_source_map_followthrough_chain_readiness": "triage",
    "workspace_source_map_followthrough_one_step_plan": "triage",
    "workspace_source_map_followthrough_dispatch_preflight": "triage",
    "workspace_source_map_followthrough_dispatch_approval_plan": "triage",
    "workspace_source_map_followthrough_dispatch_approval_record": "audit",
    "workspace_source_map_followthrough_dispatch_transaction_preflight": "audit",
    "workspace_source_map_followthrough_dispatch_transaction_journal": "audit",
    "workspace_source_map_followthrough_dispatch_bounded_executor_gate": "audit",
    "workspace_source_map_followthrough_dispatcher_handoff": "audit",
    "workspace_source_map_followthrough_dispatcher_apply_preflight": "audit",
    "workspace_source_map_followthrough_dispatcher_result": "audit",
    "workspace_source_map_followthrough_surface_selection": "triage",
    "workspace_source_map_selected_executor_input_review": "triage",
    "workspace_source_map_selected_executor_approval_plan": "triage",
    "workspace_source_map_selected_executor_approval_record": "audit",
    "workspace_source_map_selected_executor_apply_preflight": "audit",
    "workspace_source_map_selected_executor_application_handoff": "audit",
    "workspace_source_map_selected_executor_result_checkpoint": "audit",
    "workspace_source_map_followthrough_completion_checkpoint": "audit",
    "workspace_source_map_terminal_review_package": "audit",
    "workspace_source_map_terminal_review_closure_checkpoint": "audit",
    "workspace_source_map_terminal_review_final_audit": "audit",
    "workspace_source_map_source_logpoint_install_result": "audit",
    "workspace_source_map_debugger_candidates": "triage",
    "workspace_source_map_debugger_candidate_selection": "triage",
    "workspace_source_map_debugger_execution_result": "audit",
    "workspace_source_map_hook_candidates": "triage",
    "workspace_source_map_hook_candidate_selection": "triage",
    "workspace_source_map_hook_install_result": "audit",
    "workspace_source_map_rebuild_result": "audit",
    "workspace_source_map_rebuild_generation_result": "audit",
    "workspace_bundler_symbol_scope": "triage",
    "workspace_source_logpoints": "trace",
    "workspace_source_logpoint_timeline": "trace",
    "workspace_mutation_audit": "trace",
    "workspace_page_mutation_audit": "trace",
    "workspace_object_root_mutation_audit": "trace",
    "workspace_object_graph_diff": "triage",
    "workspace_runtime_object_graph_diff": "triage",
    "workspace_heap_snapshot_readiness": "triage",
    "workspace_heap_snapshot_collect": "audit",
    "workspace_heap_snapshot_diff_readiness": "triage",
    "workspace_heap_snapshot_diff_executor_preflight": "triage",
    "workspace_heap_snapshot_diff_executor_approval_plan": "triage",
    "workspace_heap_snapshot_diff_executor_approval_record": "audit",
    "workspace_heap_snapshot_diff_executor_transaction_preflight": "triage",
    "workspace_heap_snapshot_diff_executor_transaction_journal": "audit",
    "workspace_heap_snapshot_diff_executor_bounded_gate": "triage",
    "workspace_heap_snapshot_diff_executor_result": "audit",
    "workspace_heap_snapshot_diff_followup_checkpoint": "audit",
    "workspace_heap_snapshot_diff_selected_analysis_input_preflight": "triage",
    "workspace_heap_snapshot_constructor_growth_drilldown": "triage",
    "workspace_heap_snapshot_constructor_growth_drilldown_analysis": "audit",
    "workspace_heap_snapshot_automatic_followup_plan": "triage",
    "workspace_heap_snapshot_retained_size_proof_plan": "triage",
    "workspace_heap_snapshot_path_to_root_proof_plan": "triage",
    "workspace_heap_snapshot_raw_heap_constructor_drilldown_proof_plan": "triage",
    "workspace_heap_snapshot_retained_path_preflight": "triage",
    "workspace_heap_snapshot_retained_size_input_review": "triage",
    "workspace_heap_snapshot_retained_size_approval_plan": "triage",
    "workspace_heap_snapshot_retained_size_approval_record": "audit",
    "workspace_heap_snapshot_retained_size_transaction_preflight": "triage",
    "workspace_heap_snapshot_retained_size_transaction_journal": "audit",
    "workspace_heap_snapshot_retained_size_bounded_gate": "triage",
    "workspace_heap_snapshot_retained_size_analysis": "audit",
    "workspace_heap_snapshot_path_to_root_analysis": "audit",
    "workspace_mutation_observer_timeline": "trace",
    "workspace_breakpoints": "trace",
    "workspace_debugger_paused": "trace",
    "workspace_callframes": "trace",
    "workspace_callframe_evaluations": "trace",
    "workspace_debugger_actions": "trace",
    "workspace_debugger_session": "trace",
    "workspace_debugger_timeline": "trace",
    "workspace_paused_session_live_continuation_preflight": "audit",
    "workspace_paused_session_target_attach_readiness": "audit",
    "workspace_paused_session_cross_process_execution_plan": "triage",
    "workspace_paused_session_cross_process_session_lifecycle": "triage",
    "workspace_paused_session_cross_process_attach_probe": "audit",
    "workspace_paused_session_live_callframe_recovery": "audit",
    "workspace_paused_session_cross_process_one_action_execution": "audit",
    "workspace_paused_session_next_paused_event_capture_plan": "triage",
    "workspace_paused_session_next_paused_event_capture_execution": "audit",
    "workspace_paused_session_pre_action_subscribe_and_action": "audit",
    "workspace_paused_session_cross_process_continuation_checkpoint": "audit",
    "workspace_paused_session_multi_step_continuation_workflow": "triage",
    "workspace_paused_session_multi_step_continuation_execution": "audit",
    "workspace_paused_session_multi_step_loop_plan": "triage",
    "workspace_paused_session_multi_step_loop_execution": "audit",
    "workspace_paused_session_automatic_loop_readiness": "triage",
    "workspace_paused_session_automatic_loop_execution_plan": "triage",
    "workspace_paused_session_automatic_loop_executor_preflight": "triage",
    "workspace_paused_session_automatic_loop_executor_approval_plan": "triage",
    "workspace_paused_session_automatic_loop_executor_approval_record": "audit",
    "workspace_paused_session_automatic_loop_transaction_preflight": "audit",
    "workspace_paused_session_automatic_loop_executor_journal": "audit",
    "workspace_paused_session_automatic_loop_bounded_executor_gate": "audit",
    "workspace_paused_session_automatic_loop_execution_result": "audit",
    "workspace_paused_session_automatic_loop_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_next_iteration_plan": "triage",
    "workspace_paused_session_automatic_loop_next_iteration_execution": "audit",
    "workspace_paused_session_automatic_loop_next_iteration_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_following_iteration_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_policy": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_preflight": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_execution_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_approval_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_approval_record": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_transaction_preflight": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_journal": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_bounded_executor_gate": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_execution_result": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_followup_checkpoint": "audit",
    "workspace_paused_session_automatic_loop_multi_iteration_next_step_plan": "triage",
    "workspace_paused_session_automatic_loop_multi_iteration_executor_input_preflight": "triage",
    "workspace_closure_functions": "trace",
    "workspace_closure_function_candidates": "triage",
    "workspace_closure_wrapper_replacement_plan": "triage",
    "workspace_closure_wrapper_assignment_safety": "triage",
    "workspace_closure_wrapper_runtime_mutability_preflight": "triage",
    "workspace_closure_wrapper_runtime_mutability_result": "audit",
    "workspace_closure_wrapper_replacement_execution": "audit",
    "workspace_closure_wrapper_restore_plan": "audit",
    "workspace_closure_wrapper_restore_execution": "audit",
    "workspace_closure_wrapper_events": "hook-timeline",
    "workspace_closure_wrapper_continuation_readiness": "triage",
    "workspace_closure_wrapper_continuation_execution_plan": "triage",
    "workspace_closure_wrapper_continuation_execution": "audit",
    "workspace_closure_wrapper_continuation_checkpoint": "triage",
    "workspace_closure_wrapper_continuation_next_iteration_plan": "triage",
    "workspace_closure_wrapper_continuation_next_iteration_execution": "audit",
    "workspace_request_initiators": "trace",
    "workspace_navigation_events": "trace",
    "workspace_browser_provider_smoke": "runtime-context",
    "workspace_runtime_context": "runtime-context",
    "workspace_dom_snapshot": "runtime-context",
    "workspace_console_messages": "runtime-context",
    "workspace_runtime_context_diff": "runtime-context",
    "workspace_runtime_capabilities": "runtime-context",
    "workspace_runtime_export_bundle": "export",
    "workspace_workspace_contract": "workspace",
    "workspace_platform_tool_probe": "runtime-context",
    "workspace_function_candidates": "source",
    "workspace_function_validations": "trace",
    "workspace_function_validation_summary": "trace",
    "workspace_evidence_candidates": "evidence",
    "workspace_evidence_validated": "evidence",
    "workspace_evidence_promotion": "evidence",
    "workspace_stitched_flow_physical_rollback_diff": "trace",
    "workspace_stitched_flow_physical_rollback_results": "trace",
    "workspace_review_gate_after_rollback": "triage",
    "workspace_review_gate_after_physical_rollback": "triage",
    "workspace_review_gate_replacement_results": "triage",
    "workspace_delivery_guard_after_review_gate_replacement": "triage",
    "workspace_final_delivery_package_after_review_gate_replacement": "export",
    "workspace_final_delivery_transaction_commit": "export",
    "workspace_delivery_receipt": "export",
    "workspace_delivery_transaction_journal": "export",
    "workspace_external_delivery_result": "export",
    "workspace_external_delivery_duplicate_guard": "export",
    "workspace_delivery_manifest_revision": "export",
    "workspace_backend_artifact_manifest_mutation": "export",
    "workspace_backend_artifact_manifest_patched": "export",
    "workspace_backend_artifact_manifest_preflight": "triage",
    "workspace_backend_artifact_manifest_in_place_mutation": "export",
    "workspace_backend_artifact_manifest_rollback": "export",
    "workspace_backend_artifact_manifest_recovery_preflight": "triage",
    "workspace_backend_artifact_manifest_recovery": "export",
    "workspace_backend_artifact_manifest_transaction_commit": "export",
    "workspace_review_gate": "triage",
}


def _artifact_manifest_entry_metadata(capabilities: RuntimeBackendCapabilities, artifact_key: str, path: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"path_style": "virtual" if path.startswith("virtual://") else "filesystem"}
    metadata.update(workspace_manifest_alias_metadata(artifact_key))
    provider = capabilities.config.get("provider") if isinstance(capabilities.config, dict) else None
    if isinstance(provider, dict):
        provider_id = provider.get("provider_id")
        if provider_id:
            metadata["browser_provider"] = provider_id
        provider_transport = provider.get("transport")
        if provider_transport:
            metadata["browser_provider_transport"] = provider_transport
    return metadata


def _artifact_category_from_key(key: str) -> str:
    if key in ARTIFACT_CATEGORY_BY_KEY:
        return ARTIFACT_CATEGORY_BY_KEY[key]
    if key.startswith("workspace_"):
        return "workspace"
    if key.startswith("rebuild_"):
        return "rebuild"
    if key in {"json", "markdown"}:
        return "report"
    if key == "index":
        return "export"
    return "other"


def _artifact_kind_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".py":
        return "rebuild"
    return "other"


def _runtime_artifact_manifest_entries(
    capabilities: RuntimeBackendCapabilities,
    artifacts: list[dict[str, Any]],
) -> list[RuntimeArtifactManifestEntry]:
    entries: list[RuntimeArtifactManifestEntry] = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            continue
        path = str(artifact.get("path") or "")
        if not path:
            continue
        metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
        artifact_key = str(
            artifact.get("artifact_key")
            or metadata.get("artifact_key")
            or _artifact_key_from_runtime_path(path, index)
        )
        entry_metadata = dict(metadata)
        entry_metadata.setdefault("path_style", "virtual" if path.startswith("virtual://") else "filesystem")
        entry_metadata.setdefault("source", "runtime_export_bundle")
        entries.append(
            RuntimeArtifactManifestEntry(
                artifact_key=artifact_key,
                path=path,
                category=_artifact_category_from_runtime_artifact(path, artifact, metadata),
                kind=str(artifact.get("kind") or _artifact_kind_from_path(path)),
                producer_backend_id=capabilities.backend_id,
                producer_transport=capabilities.transport,
                target_platforms=capabilities.target_platforms,
                description=artifact.get("description"),
                metadata=entry_metadata,
            )
        )
    return entries


def _artifact_key_from_runtime_path(path: str, index: int) -> str:
    normalized = path
    for prefix in ("virtual://", "file://"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    normalized = normalized.strip("/") or f"artifact_{index}"
    stem = Path(normalized).with_suffix("").as_posix()
    safe = "".join(ch if ch.isalnum() else "_" for ch in stem).strip("_")
    return f"runtime_{safe or f'artifact_{index}'}"


def _artifact_category_from_runtime_artifact(path: str, artifact: dict[str, Any], metadata: dict[str, Any]) -> str:
    explicit_category = artifact.get("category") or metadata.get("category")
    if explicit_category:
        return str(explicit_category)
    if path.startswith("virtual://exports/session"):
        return "session"
    if path.startswith("virtual://exports/"):
        return "export"
    if path.startswith("virtual://workspace/"):
        return _artifact_category_from_key(_artifact_key_from_runtime_path(path, 0))
    if path.startswith("virtual://protection/"):
        return "triage"
    return "other"


def _artifact_description_from_key(key: str) -> str:
    return key.replace("_", " ")
