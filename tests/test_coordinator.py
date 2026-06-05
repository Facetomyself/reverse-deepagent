import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.coordinator import (
    _artifact_category_from_key,
    _extract_workspace_artifact_payloads,
    build_default_runtime_registry,
    build_runtime,
    legacy_mcp_alias_warning,
    list_runtime_backends,
    run_reverse_pipeline,
)
from reverse_deepagent.runtime import ReverseRuntime, RuntimeExportBundle
from reverse_deepagent.runtime.legacy_mcp import LegacyMcpPluginUnavailableError
from reverse_deepagent.runtime import registry as runtime_registry
from reverse_deepagent.runtime.registry import RuntimeBackendCapabilities, RuntimeBackendRegistration
from reverse_deepagent.schemas import (
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ProtectionResult,
    ReverseMode,
    ReverseStage,
    TaskCard,
)


class NonWebRuntime(ReverseRuntime):
    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class FakeEntryPoint:
    def __init__(self, name: str, value) -> None:
        self.name = name
        self.value = value

    def load(self):
        return self.value


class FakeEntryPoints(list):
    def select(self, *, group: str):
        return FakeEntryPoints(self)


class CoordinatorTests(unittest.TestCase):
    def test_build_runtime_exposes_mock_capabilities(self) -> None:
        runtime = build_runtime("mock")
        capabilities = runtime.describe_capabilities()
        self.assertEqual(capabilities.backend_id, "mock")
        self.assertEqual(capabilities.transport, "in-process")
        self.assertTrue(capabilities.supports_web_recon)
        self.assertFalse(capabilities.mcp_backed)

    def test_runtime_backend_metadata_lists_mock_without_builtin_legacy_mcp(self) -> None:
        metadata = list_runtime_backends()
        by_id = {item["backend_id"]: item for item in metadata}
        self.assertIn("mock", by_id)
        self.assertIn("native-web", by_id)
        self.assertNotIn("legacy-mcp", by_id)
        self.assertNotIn("mcp", by_id)
        self.assertFalse(any(item.get("mcp_backed") for item in by_id.values()))

    def test_default_registry_can_be_built_without_legacy_mcp(self) -> None:
        registry = build_default_runtime_registry(include_entry_points=False, include_legacy_mcp=False)
        metadata = {item["backend_id"]: item for item in registry.list_metadata()}
        self.assertIn("mock", metadata)
        self.assertIn("native-web", metadata)
        self.assertNotIn("legacy-mcp", metadata)
        self.assertFalse(any(item.get("mcp_backed") for item in metadata.values()))
        with self.assertRaisesRegex(ValueError, "Unsupported runtime backend"):
            registry.resolve("legacy-mcp")

    def test_entry_point_legacy_mcp_registration_is_loaded_when_installed(self) -> None:
        external_registration = RuntimeBackendRegistration(
            backend_id="legacy-mcp",
            aliases=("mcp", "jsreverser-mcp"),
            capabilities=RuntimeBackendCapabilities(
                backend_id="legacy-mcp",
                display_name="External Legacy MCP Plugin",
                transport="external-mcp-plugin",
                target_platforms=["web"],
                supports_web_recon=True,
                mcp_backed=True,
                config={"source": "entry-point"},
            ),
            factory=lambda **_: NonWebRuntime(),
        )
        entry_points = FakeEntryPoints([FakeEntryPoint("legacy-mcp", external_registration)])
        with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=entry_points):
            registry = build_default_runtime_registry(include_entry_points=True, include_legacy_mcp=True)

        metadata = {item["backend_id"]: item for item in registry.list_metadata()}
        self.assertEqual(metadata["legacy-mcp"]["transport"], "external-mcp-plugin")
        self.assertEqual(metadata["legacy-mcp"]["config"]["source"], "entry-point")
        self.assertEqual(registry.resolve("mcp").capabilities.display_name, "External Legacy MCP Plugin")

    def test_workspace_artifact_payloads_include_breakpoint_manager(self) -> None:
        final_result = FinalResult(
            task_card=TaskCard(
                target_url_or_file="https://example.test",
                target_param_or_api="sign",
                goal="set breakpoint",
                boundaries="unit test",
            ),
            mode=ReverseMode.DEBUG_BLOCKED,
            stage=ReverseStage.BREAKPOINT,
            status=ExecutionStatus.SUCCESS,
            key_findings=KeyFindings(),
            evidence=[
                EvidenceItem(
                    summary="Native breakpoint manager result",
                    kind=EvidenceKind.CALLSTACK,
                    source="breakpoint_manager",
                    details={"status": "success", "count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native debugger callframe evaluations",
                    kind=EvidenceKind.CALLSTACK,
                    source="debugger_callframe_evaluations",
                    details={"evaluations": [{"expression": "typeof buildSign", "ok": True, "value": "function"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native debugger actions",
                    kind=EvidenceKind.CALLSTACK,
                    source="debugger_actions",
                    details={"actions": [{"action": "step_over", "method": "Debugger.stepOver", "ok": True}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native debugger paused session",
                    kind=EvidenceKind.CALLSTACK,
                    source="debugger_session",
                    details={"session_id": "unit-paused-session", "lifecycle": "action_controlled"},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native debugger timeline",
                    kind=EvidenceKind.CALLSTACK,
                    source="debugger_timeline",
                    details={"session_id": "unit-paused-session", "entry_count": 4, "entries": [{"type": "debugger.paused"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native paused-session live continuation preflight",
                    kind=EvidenceKind.CALLSTACK,
                    source="paused_session_live_continuation_preflight",
                    details={"status": "blocked", "preflight": {"source": "durable_snapshot", "live_continuation_available": False}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper replacement plan",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_replacement_plan",
                    details={"status": "ready_for_review", "plan": {"wrapper_installed": False}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper assignment safety proof",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_assignment_safety",
                    details={"status": "ready_for_review", "assignment_safety": {"assignment_safety_proven": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper runtime mutability preflight",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_runtime_mutability_preflight",
                    details={"status": "ready_for_review", "preflight": {"runtime_mutability_probe_ready_for_review": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper replacement execution",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_replacement_execution",
                    details={"status": "applied", "execution": {"wrapper_installed": True, "runtime_mutated": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper restore plan",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_restore_plan",
                    details={"status": "ready_for_review", "restore_plan": {"available": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper restore execution",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_restore_execution",
                    details={"status": "restored", "execution": {"wrapper_restored": True, "runtime_mutated": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native closure wrapper events",
                    kind=EvidenceKind.HOOK,
                    source="closure_wrapper_events",
                    details={"status": "success", "event_count": 1, "events": [{"functionName": "buildSign"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native function hook timeline",
                    kind=EvidenceKind.HOOK,
                    source="function_hook_timeline",
                    details={"event_count": 2, "events": [{"type": "function_call"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native function hook install result",
                    kind=EvidenceKind.HOOK,
                    source="function_hooks",
                    details={"installed_count": 1, "installed": [{"path": "window.buildSign"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk load plan",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_load_plan",
                    details={"status": "ready_for_review", "chunk_id": "731"},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk load result",
                    kind=EvidenceKind.DYNAMIC,
                    source="async_chunk_load_result",
                    details={"status": "success", "addedRegistryKeys": ["731"]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk module diff",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_module_diff",
                    details={"status": "planned", "candidate_count": 1, "matched_module_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk traversal graph",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_traversal_graph",
                    details={"status": "ready_for_review", "queue_count": 1, "node_count": 2},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk traversal workflow plan",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_traversal_workflow_plan",
                    details={"status": "ready_for_review", "planned_step_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk traversal workflow execution",
                    kind=EvidenceKind.DYNAMIC,
                    source="async_chunk_traversal_workflow_execution",
                    details={"status": "module_diff_ready", "stage_count": 6},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk traversal loop plan",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_traversal_loop_plan",
                    details={"status": "ready_for_review", "planned_iteration_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk traversal loop execution",
                    kind=EvidenceKind.DYNAMIC,
                    source="async_chunk_traversal_loop_execution",
                    details={"status": "module_diff_ready", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk recursive traversal plan",
                    kind=EvidenceKind.NOTE,
                    source="async_chunk_recursive_traversal_plan",
                    details={"status": "ready_for_graph_rebuild", "latest_loop_execution_status": "module_diff_ready"},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk recursive traversal followup",
                    kind=EvidenceKind.DYNAMIC,
                    source="async_chunk_recursive_traversal_followup",
                    details={"status": "next_loop_plan_ready", "stage_count": 4},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native async chunk recursive traversal execution",
                    kind=EvidenceKind.DYNAMIC,
                    source="async_chunk_recursive_traversal_execution",
                    details={"status": "next_loop_module_diff_ready", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation traversal graph",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_traversal_graph",
                    details={"status": "ready_for_review", "queue_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation traversal workflow plan",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_traversal_workflow_plan",
                    details={"status": "ready_for_review", "planned_step_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation traversal workflow execution",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_traversal_workflow_execution",
                    details={"status": "factory_invoke_success", "stage_count": 4},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation recursive traversal plan",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_recursive_traversal_plan",
                    details={"status": "ready_for_next_step_review", "latest_graph_queue_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation recursive traversal followup",
                    kind=EvidenceKind.DYNAMIC,
                    source="module_federation_recursive_traversal_followup",
                    details={"status": "next_step_review_ready", "stage_count": 4},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation recursive traversal execution",
                    kind=EvidenceKind.DYNAMIC,
                    source="module_federation_recursive_traversal_execution",
                    details={"status": "next_step_execution_progressed", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation recursive continuation journal",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_recursive_continuation_journal",
                    details={"status": "ready_for_review", "record_count": 0},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native source map fetch plan",
                    kind=EvidenceKind.NOTE,
                    source="source_map_fetch_plan",
                    details={"status": "ready_for_review", "source_map_url_redacted": "https://example.test/app.js.map"},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal plan",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_traversal_plan",
                    details={"status": "planned", "candidate_count": 1, "ready_for_review_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal graph",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_traversal_graph",
                    details={"status": "ready_for_review", "queue_count": 1, "node_count": 2},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal workflow plan",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_traversal_workflow_plan",
                    details={"status": "ready_for_review", "planned_step_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader continuation workflow",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_continuation_workflow",
                    details={"status": "ready_for_review", "selected_candidate_index": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader continuation journal",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_continuation_journal",
                    details={"status": "journal_appended", "record_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader continuation execution",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_continuation_execution",
                    details={"status": "journal_appended", "stage_count": 5},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader execution preflight",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_execution_preflight",
                    details={"status": "ready_for_execution_review", "blocking_reasons": []},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader execution result",
                    kind=EvidenceKind.DYNAMIC,
                    source="custom_loader_execution_result",
                    details={"status": "success", "addedRegistryKeys": ["884"]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader module diff",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_module_diff",
                    details={"status": "planned", "candidate_count": 1, "matched_module_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation get/init plan",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_get_init_plan",
                    details={"status": "planned", "candidate_count": 1, "container_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation get/init probe result",
                    kind=EvidenceKind.DYNAMIC,
                    source="module_federation_get_init_result",
                    details={"status": "success", "execution": {"remoteFactoryInvoked": False}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation factory invoke result",
                    kind=EvidenceKind.DYNAMIC,
                    source="module_federation_factory_invoke_result",
                    details={"status": "success", "factory_execution": {"remoteFactoryInvoked": True}},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native module federation export hook plan",
                    kind=EvidenceKind.NOTE,
                    source="module_federation_export_hook_plan",
                    details={"status": "planned", "hookable_candidate_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native source map fetch result",
                    kind=EvidenceKind.DYNAMIC,
                    source="source_map_fetch_result",
                    details={"status": "success", "byte_count": 128},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native object-root mutation audit",
                    kind=EvidenceKind.DYNAMIC,
                    source="object_root_mutation_audit",
                    details={"status": "success", "change_count": 4, "root_path": "window.__appState"},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal workflow execution",
                    kind=EvidenceKind.HOOK,
                    source="custom_loader_traversal_workflow_execution",
                    details={"status": "journal_appended", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal loop plan",
                    kind=EvidenceKind.NOTE,
                    source="custom_loader_traversal_loop_plan",
                    details={"status": "ready_for_review", "planned_iteration_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader traversal loop execution",
                    kind=EvidenceKind.HOOK,
                    source="custom_loader_traversal_loop_execution",
                    details={"status": "journal_appended", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader recursive traversal plan",
                    kind=EvidenceKind.HOOK,
                    source="custom_loader_recursive_traversal_plan",
                    details={"status": "ready_for_next_loop_review", "latest_graph_queue_count": 1},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader recursive traversal followup",
                    kind=EvidenceKind.HOOK,
                    source="custom_loader_recursive_traversal_followup",
                    details={"status": "next_loop_plan_ready", "stage_count": 5},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native custom loader recursive traversal execution",
                    kind=EvidenceKind.HOOK,
                    source="custom_loader_recursive_traversal_execution",
                    details={"status": "next_loop_journal_appended", "stage_count": 3},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native source logpoint timeline",
                    kind=EvidenceKind.HOOK,
                    source="source_logpoint_timeline",
                    details={"event_count": 1, "events": [{"type": "source_logpoint"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native source logpoint install result",
                    kind=EvidenceKind.HOOK,
                    source="source_logpoints",
                    details={"count": 1, "breakpoints": [{"breakpointId": "bp-logpoint-1"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
                EvidenceItem(
                    summary="Native review-approved stitched flow",
                    kind=EvidenceKind.NOTE,
                    source="stitched_flow",
                    details={"count": 1, "flows": [{"stitched_flow_id": "stitched-flow-1"}]},
                    confidence=ConfidenceLevel.MEDIUM,
                ),
            ],
            artifacts=[],
            next_action="wait_for_breakpoint",
            confidence=ConfidenceLevel.MEDIUM,
        )
        payloads = _extract_workspace_artifact_payloads(final_result)
        self.assertEqual(payloads["breakpoints.json"], {"status": "success", "count": 1})
        self.assertEqual(payloads["callframe-evaluations.json"]["evaluations"][0]["value"], "function")
        self.assertEqual(payloads["debugger-actions.json"]["actions"][0]["method"], "Debugger.stepOver")
        self.assertEqual(payloads["debugger-session.json"]["session_id"], "unit-paused-session")
        self.assertEqual(payloads["debugger-timeline.json"]["entry_count"], 4)
        self.assertEqual(payloads["paused-session-live-continuation-preflight.json"]["preflight"]["source"], "durable_snapshot")
        self.assertEqual(payloads["closure-wrapper-replacement-plan.json"]["status"], "ready_for_review")
        self.assertFalse(payloads["closure-wrapper-replacement-plan.json"]["plan"]["wrapper_installed"])
        self.assertTrue(payloads["closure-wrapper-assignment-safety.json"]["assignment_safety"]["assignment_safety_proven"])
        self.assertTrue(payloads["closure-wrapper-runtime-mutability-preflight.json"]["preflight"]["runtime_mutability_probe_ready_for_review"])
        self.assertEqual(payloads["closure-wrapper-replacement-execution.json"]["status"], "applied")
        self.assertTrue(payloads["closure-wrapper-replacement-execution.json"]["execution"]["wrapper_installed"])
        self.assertEqual(payloads["closure-wrapper-restore-plan.json"]["status"], "ready_for_review")
        self.assertTrue(payloads["closure-wrapper-restore-plan.json"]["restore_plan"]["available"])
        self.assertEqual(payloads["closure-wrapper-restore-execution.json"]["status"], "restored")
        self.assertTrue(payloads["closure-wrapper-restore-execution.json"]["execution"]["wrapper_restored"])
        self.assertEqual(payloads["closure-wrapper-events.json"]["event_count"], 1)
        self.assertEqual(payloads["function-hooks.json"]["installed_count"], 1)
        self.assertEqual(payloads["function-hook-timeline.json"]["event_count"], 2)
        self.assertEqual(payloads["async-chunk-load-plan.json"]["chunk_id"], "731")
        self.assertEqual(payloads["async-chunk-module-diff.json"]["candidate_count"], 1)
        self.assertEqual(payloads["async-chunk-traversal-graph.json"]["queue_count"], 1)
        self.assertEqual(payloads["async-chunk-traversal-workflow-plan.json"]["planned_step_count"], 1)
        self.assertEqual(payloads["async-chunk-traversal-workflow-execution.json"]["stage_count"], 6)
        self.assertEqual(payloads["async-chunk-traversal-loop-plan.json"]["planned_iteration_count"], 1)
        self.assertEqual(payloads["async-chunk-traversal-loop-execution.json"]["stage_count"], 3)
        self.assertEqual(payloads["custom-loader-traversal-plan.json"]["candidate_count"], 1)
        self.assertEqual(payloads["custom-loader-traversal-graph.json"]["queue_count"], 1)
        self.assertEqual(payloads["custom-loader-traversal-workflow-plan.json"]["planned_step_count"], 1)
        self.assertEqual(payloads["custom-loader-traversal-workflow-execution.json"]["stage_count"], 3)
        self.assertEqual(payloads["custom-loader-traversal-loop-plan.json"]["planned_iteration_count"], 1)
        self.assertEqual(payloads["custom-loader-traversal-loop-execution.json"]["stage_count"], 3)
        self.assertEqual(payloads["custom-loader-recursive-traversal-plan.json"]["latest_graph_queue_count"], 1)
        self.assertEqual(payloads["custom-loader-recursive-traversal-followup.json"]["stage_count"], 5)
        self.assertEqual(payloads["custom-loader-recursive-traversal-execution.json"]["stage_count"], 3)
        self.assertEqual(payloads["custom-loader-continuation-workflow.json"]["selected_candidate_index"], 1)
        self.assertEqual(payloads["custom-loader-continuation-journal.json"]["record_count"], 1)
        self.assertEqual(payloads["custom-loader-continuation-execution.json"]["stage_count"], 5)
        self.assertEqual(payloads["custom-loader-execution-preflight.json"]["status"], "ready_for_execution_review")
        self.assertEqual(payloads["custom-loader-execution-result.json"]["addedRegistryKeys"], ["884"])
        self.assertEqual(payloads["custom-loader-module-diff.json"]["candidate_count"], 1)
        self.assertEqual(payloads["module-federation-get-init-plan.json"]["container_count"], 1)
        self.assertEqual(payloads["module-federation-get-init-result.json"]["execution"]["remoteFactoryInvoked"], False)
        self.assertEqual(payloads["module-federation-factory-invoke-result.json"]["factory_execution"]["remoteFactoryInvoked"], True)
        self.assertEqual(payloads["module-federation-export-hook-plan.json"]["hookable_candidate_count"], 1)
        self.assertEqual(payloads["module-federation-traversal-graph.json"]["queue_count"], 1)
        self.assertEqual(payloads["module-federation-traversal-workflow-plan.json"]["planned_step_count"], 1)
        self.assertEqual(payloads["module-federation-traversal-workflow-execution.json"]["stage_count"], 4)
        self.assertEqual(payloads["module-federation-recursive-traversal-plan.json"]["status"], "ready_for_next_step_review")
        self.assertEqual(payloads["module-federation-recursive-traversal-followup.json"]["status"], "next_step_review_ready")
        self.assertEqual(payloads["module-federation-recursive-traversal-execution.json"]["status"], "next_step_execution_progressed")
        self.assertEqual(payloads["module-federation-recursive-continuation-journal.json"]["status"], "ready_for_review")
        self.assertEqual(payloads["async-chunk-load-result.json"]["addedRegistryKeys"], ["731"])
        self.assertEqual(payloads["async-chunk-recursive-traversal-plan.json"]["status"], "ready_for_graph_rebuild")
        self.assertEqual(payloads["async-chunk-recursive-traversal-followup.json"]["status"], "next_loop_plan_ready")
        self.assertEqual(payloads["async-chunk-recursive-traversal-execution.json"]["status"], "next_loop_module_diff_ready")
        self.assertEqual(payloads["source-map-fetch-plan.json"]["source_map_url_redacted"], "https://example.test/app.js.map")
        self.assertEqual(payloads["source-map-fetch-result.json"]["byte_count"], 128)
        self.assertEqual(payloads["object-root-mutation-audit.json"]["root_path"], "window.__appState")
        self.assertEqual(payloads["object-root-mutation-audit.json"]["change_count"], 4)
        self.assertEqual(payloads["source-logpoints.json"]["count"], 1)
        self.assertEqual(payloads["source-logpoint-timeline.json"]["event_count"], 1)
        self.assertEqual(payloads["stitched-flow.json"]["flows"][0]["stitched_flow_id"], "stitched-flow-1")
        self.assertEqual(_artifact_category_from_key("workspace_breakpoints"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_function_hooks"), "hook-timeline")
        self.assertEqual(_artifact_category_from_key("workspace_function_hook_timeline"), "hook-timeline")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_traversal_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_traversal_graph"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_traversal_workflow_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_traversal_loop_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_traversal_loop_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_recursive_traversal_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_recursive_traversal_followup"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_recursive_traversal_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_continuation_workflow"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_continuation_journal"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_continuation_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_execution_preflight"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_execution_result"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_custom_loader_module_diff"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_module_diff"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_traversal_graph"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_traversal_workflow_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_traversal_workflow_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_traversal_loop_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_traversal_loop_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_recursive_traversal_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_recursive_traversal_followup"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_recursive_traversal_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_get_init_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_get_init_result"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_factory_invoke_result"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_export_hook_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_traversal_graph"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_traversal_workflow_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_traversal_workflow_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_recursive_traversal_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_recursive_traversal_followup"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_recursive_traversal_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_module_federation_recursive_continuation_journal"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_load_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_async_chunk_load_result"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_source_map_fetch_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_source_map_fetch_result"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_source_logpoints"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_source_logpoint_timeline"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_object_root_mutation_audit"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_callframe_evaluations"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_debugger_actions"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_debugger_session"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_debugger_timeline"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_paused_session_live_continuation_preflight"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_closure_functions"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_closure_function_candidates"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_replacement_plan"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_assignment_safety"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_runtime_mutability_preflight"), "triage")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_replacement_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_restore_plan"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_restore_execution"), "audit")
        self.assertEqual(_artifact_category_from_key("workspace_closure_wrapper_events"), "hook-timeline")
        self.assertEqual(_artifact_category_from_key("workspace_stitched_flow"), "trace")
        self.assertEqual(_artifact_category_from_key("workspace_external_delivery_duplicate_guard"), "export")

    def test_build_runtime_legacy_mcp_without_optional_plugin_reports_guidance(self) -> None:
        with self.assertRaisesRegex(LegacyMcpPluginUnavailableError, "install_hint") as ctx:
            build_runtime(
                "legacy-mcp",
                browser_url="http://127.0.0.1:9555",
                mcp_command="/tmp/jsreverser-mcp",
            )
        self.assertIn("reverse-deepagent-legacy-mcp", str(ctx.exception))
        self.assertIn("native-web", str(ctx.exception))

        with self.assertRaisesRegex(LegacyMcpPluginUnavailableError, "reverse-deepagent-legacy-mcp"):
            build_runtime("mcp", browser_url="http://127.0.0.1:9555", mcp_command="/tmp/jsreverser-mcp")

    def test_legacy_mcp_alias_warning_only_targets_deprecated_aliases(self) -> None:
        self.assertIsNone(legacy_mcp_alias_warning("legacy-mcp"))
        self.assertIsNone(legacy_mcp_alias_warning("native-web"))
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("mcp") or "")
        self.assertIn("legacy-mcp", legacy_mcp_alias_warning("jsreverser-mcp") or "")

    def test_web_pipeline_rejects_platform_neutral_non_web_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(TypeError, "does not implement WebReverseRuntime"):
                run_reverse_pipeline(
                    task_text="android://demo 找 sign",
                    artifact_root=Path(tmpdir) / "artifacts",
                    runtime_kind="mock",
                    runtime=NonWebRuntime(),
                )

    def test_run_reverse_pipeline_returns_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mock",
            )
            self.assertEqual(output.final_result.status.value, "success")
            self.assertIn("workspace_task_card", output.artifacts)
            self.assertIn("workspace_function_candidates", output.artifacts)
            self.assertIn("workspace_function_validations", output.artifacts)
            self.assertIn("workspace_function_validation_summary", output.artifacts)
            self.assertIn("workspace_backend_artifact_manifest", output.artifacts)
            self.assertIn("workspace_workspace_contract", output.artifacts)
            self.assertIn("workspace_rebuild_plan", output.artifacts)
            self.assertIn("rebuild_sign_rebuild", output.artifacts)
            self.assertIn("rebuild_replay_demo", output.artifacts)
            self.assertIn("rebuild_scrapy_middleware", output.artifacts)
            self.assertIn("rebuild_scrapy_export_manifest", output.artifacts)
            self.assertIn("rebuild_scrapy_project", output.artifacts)
            self.assertTrue(Path(output.artifacts["workspace_function_candidates"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validations"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_function_validation_summary"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_backend_artifact_manifest"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_workspace_contract"]).exists())
            self.assertTrue(Path(output.artifacts["workspace_rebuild_plan"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_sign_rebuild"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_replay_demo"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_middleware"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_export_manifest"]).exists())
            self.assertTrue(Path(output.artifacts["rebuild_scrapy_project"]).is_dir())
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["producer_backend_id"], "mock")
            self.assertEqual(manifest["producer_transport"], "in-process")
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            manifest_keys = set(manifest_by_key)
            manifest_paths = {item["path"] for item in manifest["entries"]}
            self.assertIn("workspace_task_card", manifest_keys)
            self.assertIn("workspace_backend_artifact_manifest", manifest_keys)
            self.assertIn("workspace_workspace_contract", manifest_keys)
            self.assertIn("rebuild_sign_rebuild", manifest_keys)
            self.assertIn("rebuild_scrapy_export_manifest", manifest_keys)
            self.assertIn("rebuild_scrapy_project", manifest_keys)
            self.assertIn("virtual://exports/session-report.json", manifest_paths)
            self.assertEqual(manifest_by_key["workspace_network_requests"]["category"], "network")
            self.assertEqual(manifest_by_key["workspace_source_contexts"]["category"], "source")
            self.assertEqual(manifest_by_key["workspace_function_validations"]["category"], "trace")
            self.assertEqual(manifest_by_key["workspace_workspace_contract"]["category"], "workspace")
            self.assertEqual(manifest_by_key["rebuild_sign_rebuild"]["category"], "rebuild")
            self.assertEqual(manifest_by_key["rebuild_scrapy_export_manifest"]["kind"], "json")
            self.assertEqual(manifest_by_key["rebuild_scrapy_project"]["category"], "rebuild")
            self.assertIsNone(output.chrome_launch)
            self.assertIsNone(output.chrome_stop)

    def test_web_pipeline_can_attach_browser_provider_smoke_evidence(self) -> None:
        smoke_payload = {
            "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
            "artifact_key": "workspace_browser_provider_smoke",
            "mode": "metadata-only",
            "ok": True,
            "requested_provider_id": "playwright-chromium",
            "resolved_provider_id": "playwright-chromium",
            "side_effect_policy": {
                "provider_factories_invoked": False,
                "starts_browser": False,
                "probes_cdp_endpoint": False,
                "calls_mcp": False,
            },
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=root,
                runtime_kind="mock",
                browser_provider_smoke=smoke_payload,
            )

            smoke_path = root / "workspace" / "browser-provider-smoke.json"
            self.assertEqual(output.artifacts["workspace_browser_provider_smoke"], str(smoke_path))
            self.assertTrue(smoke_path.exists())
            self.assertEqual(json.loads(smoke_path.read_text(encoding="utf-8")), smoke_payload)

            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertIn("workspace_browser_provider_smoke", manifest_by_key)
            smoke_entry = manifest_by_key["workspace_browser_provider_smoke"]
            self.assertEqual(smoke_entry["path"], str(smoke_path))
            self.assertEqual(smoke_entry["category"], "runtime-context")
            self.assertEqual(smoke_entry["kind"], "json")
            smoke_alias = smoke_entry["metadata"]["workspace_alias"]
            self.assertEqual(smoke_alias["canonical_path"], "workspace/browser-provider-smoke.json")
            self.assertEqual(smoke_alias["future_path"], "/workspace/browser/browser-provider-smoke.json")
            self.assertEqual(smoke_alias["virtual_uri"], "virtual://workspace/browser/browser-provider-smoke.json")
            self.assertTrue(smoke_alias["canonical_path_remains_authoritative"])
            self.assertEqual(smoke_alias["migration_status"], "manifest-alias-only")

            index = json.loads(Path(output.artifacts["index"]).read_text(encoding="utf-8"))
            self.assertEqual(index["workspace"]["browser_provider_smoke"], str(smoke_path))
            self.assertEqual(index["browser_provider_smoke"], smoke_payload)


if __name__ == "__main__":
    unittest.main()
