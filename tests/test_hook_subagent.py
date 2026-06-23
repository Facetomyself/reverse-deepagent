import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.subagents.hook import HOOK_SUBAGENT_DESCRIPTION, HOOK_SUBAGENT_NAME, build_hook_subagent, load_hook_prompt
from reverse_deepagent.tools.hook_tools import make_record_heap_snapshot_diff_executor_approval_tool, make_record_heap_snapshot_diff_executor_transaction_journal_tool, make_record_heap_snapshot_retained_size_approval_tool, make_record_heap_snapshot_retained_size_transaction_journal_tool, make_record_source_map_followthrough_dispatch_approval_tool, make_record_source_map_followthrough_dispatch_transaction_journal_tool, make_record_source_map_selected_executor_approval_tool, make_review_hook_artifacts_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def _ready_source_map_selected_executor_approval_plan() -> dict:
    side_effect_policy = {
        "approval_recorded": False,
        "fetch_source_map": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "debugger_execution_performed": False,
        "runtime_evaluated": False,
        "logpoint_installed": False,
        "hook_installed": False,
        "rebuild_executed": False,
        "surface_executor_invoked": False,
        "executor_invoked": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }
    return {
        "schema_version": "reverse-deepagent.source-map-selected-executor-approval-plan.v1",
        "status": "ready_for_review",
        "selected_action_id": "review-debugger-location-use",
        "selected_consumer": "debugger",
        "selected_review_gate": "explicit_debugger_location_review",
        "approval_plan_ready": True,
        "apply_plan_ready_for_review": True,
        "approval_recorded": False,
        "ready_to_apply_now": False,
        "surface_executor_invoked": False,
        "blockers": [],
        "approval_requirements": {
            "approval_schema_version": "reverse-deepagent.source-map-selected-executor-approval.v1",
            "approval_required": True,
            "approval_recorded": False,
            "required_approval_flag": "review_approved",
            "approval_record_artifact": "workspace/source-map-selected-executor-approval-record.json",
            "approval_scope": {
                "action_id": "review-debugger-location-use",
                "consumer": "debugger",
                "review_gate": "explicit_debugger_location_review",
            },
        },
        "apply_plan": {
            "apply_plan_schema_version": "reverse-deepagent.source-map-selected-executor-apply-plan.v1",
            "consumer": "debugger",
            "future_action": "execute_reviewed_source_map_debugger_location_action",
            "review_gate": "explicit_debugger_location_review",
            "requires_approval_record": True,
            "expected_approval_record_artifact": "workspace/source-map-selected-executor-approval-record.json",
            "future_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "mode_required": "apply",
            "write_result_required": True,
            "ready_to_apply_now": False,
            "executor_implemented_now": False,
            "surface_executor_invoked": False,
            "side_effect_policy": side_effect_policy,
        },
        "side_effect_policy": side_effect_policy,
        "next_action": "record_review_approval_for_source_map_debugger_executor",
    }



def _ready_heap_snapshot_diff_executor_approval_plan() -> dict:
    side_effect_policy = {
        "read_only": True,
        "review_only": True,
        "approval_plan_only": True,
        "transaction_plan_only": True,
        "files_mutated": False,
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "complete_heap_traversal": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }
    return {
        "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-plan.v1",
        "status": "ready_for_review",
        "review_only": True,
        "approval_plan_only": True,
        "transaction_plan_only": True,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "complete_heap_traversal_claimed": False,
        "diff_executor_implemented": False,
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "preflight_summary": {
            "before_digest": "sha256:before",
            "after_digest": "sha256:after",
            "raw_heap_ingestion_policy": "external-redacted-manifest",
            "parser_sandbox": "subprocess",
            "redaction_plan": "digest-only",
            "max_raw_heap_bytes": 128,
            "diff_executor_implemented": False,
        },
        "approval_plan": {
            "approval_scope": "heap-snapshot-diff-executor",
            "reviewer": "alice",
            "approval_record_artifact": "workspace/heap-snapshot-diff-executor-approval-record.json",
            "approval_recorded": False,
            "required_approval_flag": "approve_heap_snapshot_diff_executor",
            "required_write_flag": "write_result",
            "required_mode": "apply",
        },
        "transaction_plan": {
            "transaction_id": "heap-diff-txn-test",
            "idempotency_key": "heap-diff-idem-test",
            "transaction_journal_artifact": "workspace/heap-snapshot-diff-executor-journal.json",
            "bounded_gate_artifact": "workspace/heap-snapshot-diff-executor-bounded-gate.json",
            "result_artifact": "workspace/heap-snapshot-diff-executor-result.json",
            "transaction_started": False,
            "journal_written_now": False,
            "bounded_executor_gate_required": True,
        },
        "future_executor_contract": {
            "implemented": False,
            "requires_written_approval_record": True,
            "requires_written_transaction_journal": True,
            "requires_bounded_executor_gate": True,
            "requires_ready_executor_preflight": True,
            "requires_no_raw_heap_export": True,
            "requires_no_complete_traversal_claim": True,
            "result_artifact": "workspace/heap-snapshot-diff-executor-result.json",
        },
        "safety_gates": {
            "requires_ready_heap_snapshot_diff_executor_preflight": True,
            "requires_explicit_review_before_approval_record": True,
            "requires_transaction_journal_before_execution": True,
            "requires_bounded_executor_gate": True,
            "requires_no_executor_invocation_in_plan": True,
            "requires_raw_heap_unloaded": True,
            "requires_diff_uncomputed": True,
            "future_diff_executor_implemented": False,
        },
        "blockers": [],
        "warnings": [],
        "next_action": "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval",
        "side_effect_policy": side_effect_policy,
    }


def _ready_heap_snapshot_diff_executor_transaction_preflight() -> dict:
    return {
        "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-preflight.v1",
        "status": "ready_for_review",
        "read_only": True,
        "review_only": True,
        "transaction_preflight_only": True,
        "files_mutated": False,
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "complete_heap_traversal_claimed": False,
        "diff_executor_implemented": False,
        "approval_summary": {"approval_scope": "heap-snapshot-diff-executor", "reviewer": "alice", "approval_recorded": True, "approved_for_execution": True},
        "transaction_summary": {"transaction_id": "heap-diff-txn-test", "idempotency_key": "heap-diff-idem-test", "transaction_journal_artifact": "workspace/heap-snapshot-diff-executor-journal.json", "bounded_gate_artifact": "workspace/heap-snapshot-diff-executor-bounded-gate.json", "result_artifact": "workspace/heap-snapshot-diff-executor-result.json", "transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False},
        "preflight_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "raw_heap_ingestion_policy": "metadata-only", "parser_sandbox": "subprocess", "redaction_plan": "digest-only", "max_raw_heap_bytes": 128},
        "journal_writer_contract": {"implemented": False, "ready_for_journal_review": True, "requires_ready_transaction_preflight": True, "requires_explicit_review": True, "transaction_journal_artifact": "workspace/heap-snapshot-diff-executor-journal.json"},
        "future_executor_contract": {"implemented": False, "requires_written_transaction_journal": True, "requires_bounded_executor_gate": True, "requires_safe_raw_heap_parser": True, "result_artifact": "workspace/heap-snapshot-diff-executor-result.json"},
        "safety_gates": {"ready_to_write_journal": True, "ready_to_execute_now": False, "approval_record_verified": True, "transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False, "complete_heap_traversal_claimed": False},
        "blockers": [],
        "warnings": ["heap_snapshot_diff_executor_transaction_ready_for_journal_review"],
        "next_action": "review_heap_snapshot_diff_executor_transaction_journal_writer",
        "side_effect_policy": {"read_only": True, "review_only": True, "transaction_preflight_only": True, "files_mutated": False, "approval_recorded": False, "transaction_started": False, "journal_written": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "browser_started": False, "provider_factory_invoked": False, "provider_availability_checked": False, "cdp_command_sent": False, "heap_profiler_enabled": False, "heap_snapshot_collected": False, "heap_snapshot_diff_computed": False, "heap_diff_computed": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "complete_heap_traversal": False, "runtime_evaluated": False, "javascript_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
    }



def _ready_heap_snapshot_retained_size_transaction_preflight() -> dict:
    return {
        "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1",
        "status": "ready_for_review",
        "read_only": True,
        "review_only": True,
        "transaction_preflight_only": True,
        "retained_size_only": True,
        "files_mutated": False,
        "transaction_started": False,
        "journal_written": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "complete_heap_traversal_claimed": False,
        "approval_summary": {"approval_plan_id": "retained-size-approval-plan-test", "reviewer": "alice", "approval_recorded": True, "approved_for_execution": True},
        "transaction_summary": {"transaction_plan_id": "retained-size-approval-plan-test", "transaction_journal_artifact": "workspace/heap-snapshot-retained-size-executor-journal.json", "bounded_gate_artifact": "workspace/heap-snapshot-retained-size-bounded-gate.json", "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json", "transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False},
        "candidate_summary": {"candidate_digest": "retained-size-candidate-digest-test", "candidate_count": 1, "top_candidate": "LeakyThing"},
        "journal_writer_contract": {"implemented": False, "ready_for_journal_review": True, "requires_ready_transaction_preflight": True, "requires_explicit_review": True, "requires_approval_record": True, "transaction_journal_artifact": "workspace/heap-snapshot-retained-size-executor-journal.json"},
        "future_executor_contract": {"implemented": False, "requires_written_transaction_journal": True, "requires_bounded_executor_gate": True, "requires_raw_heap": True, "requires_bounded_budget": True, "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"},
        "safety_gates": {"ready_to_write_journal": True, "ready_to_execute_now": False, "approval_record_verified": True, "transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "raw_strings_exported": False, "heap_diff_computed": False, "retained_size_proven": False, "path_to_root_computed": False, "complete_heap_traversal_claimed": False},
        "blockers": [],
        "warnings": ["heap_snapshot_retained_size_transaction_ready_for_journal_review"],
        "next_action": "review_heap_snapshot_retained_size_transaction_journal_writer",
        "side_effect_policy": {"read_only": True, "review_only": True, "transaction_preflight_only": True, "retained_size_only": True, "files_mutated": False, "transaction_started": False, "journal_written": False, "journal_written_now": False, "bounded_executor_gate_written": False, "executor_invoked": False, "future_executor_invoked": False, "browser_started": False, "provider_factory_invoked": False, "provider_availability_checked": False, "cdp_command_sent": False, "heap_profiler_enabled": False, "heap_snapshot_collected": False, "heap_snapshot_diff_computed": False, "heap_diff_computed": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "raw_strings_exported": False, "complete_heap_traversal": False, "retained_size_proven": False, "path_to_root_computed": False, "runtime_evaluated": False, "javascript_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
    }

def _ready_heap_snapshot_retained_size_approval_plan() -> dict:
    side_effect_policy = {
        "read_only": True,
        "review_only": True,
        "approval_plan_only": True,
        "transaction_plan_only": True,
        "retained_size_only": True,
        "files_mutated": False,
        "artifacts_written": False,
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "future_executor_invoked": False,
        "browser_started": False,
        "provider_factory_invoked": False,
        "provider_availability_checked": False,
        "cdp_command_sent": False,
        "heap_profiler_enabled": False,
        "heap_snapshot_collected": False,
        "heap_snapshot_diff_computed": False,
        "heap_diff_computed": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "complete_heap_traversal": False,
        "constructor_drilldown_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "runtime_evaluated": False,
        "javascript_evaluated": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }
    return {
        "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1",
        "status": "ready_for_review",
        "plan_name": "heap_snapshot_retained_size_approval_plan",
        "review_only": True,
        "approval_plan_only": True,
        "transaction_plan_only": True,
        "retained_size_only": True,
        "source_retained_size_input_review": {
            "schema_version": "reverse-deepagent.heap-snapshot-retained-size-input-review.v1",
            "status": "ready_for_review",
            "candidate_count": 1,
            "approval_gate": {"approval_required": True, "ready_to_execute_now": False},
        },
        "candidate_inputs": [{"name": "LeakyThing", "delta": 1}],
        "candidate_count": 1,
        "candidate_digest": "retained-size-candidate-digest-test",
        "approval_plan": {
            "approval_plan_id": "retained-size-approval-plan-test",
            "approval_required": True,
            "approval_recorded": False,
            "approval_record_writer": "record_heap_snapshot_retained_size_approval",
            "approval_record_artifact": "workspace/heap-snapshot-retained-size-approval-record.json",
            "requires_reviewer": True,
            "requires_candidate_digest_match": True,
            "would_write_now": False,
        },
        "transaction_plan": {
            "transaction_plan_id": "retained-size-approval-plan-test",
            "transaction_started": False,
            "journal_written": False,
            "transaction_journal_writer": "record_heap_snapshot_retained_size_transaction_journal",
            "transaction_journal_artifact": "workspace/heap-snapshot-retained-size-executor-journal.json",
            "bounded_gate_artifact": "workspace/heap-snapshot-retained-size-bounded-gate.json",
            "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json",
            "would_start_transaction_now": False,
            "would_write_journal_now": False,
        },
        "executor_input_contract": {
            "executor_name": "execute_heap_snapshot_retained_size_analysis",
            "implemented": False,
            "requires_explicit_review": True,
            "requires_raw_heap": True,
            "requires_bounded_budget": True,
            "ready_to_execute_now": False,
            "automatic_execution_allowed": False,
        },
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written_now": False,
        "bounded_executor_gate_written": False,
        "executor_invoked": False,
        "raw_heap_loaded": False,
        "raw_heap_parsed": False,
        "raw_heap_exported": False,
        "raw_strings_exported": False,
        "heap_diff_computed": False,
        "retained_size_proven": False,
        "path_to_root_computed": False,
        "blockers": [],
        "warnings": ["heap_snapshot_retained_size_approval_plan_review_only"],
        "next_action": "record_heap_snapshot_retained_size_approval",
        "side_effect_policy": side_effect_policy,
    }


def _ready_source_map_followthrough_dispatch_approval_plan() -> dict:
    side_effect_policy = {
        "read_only": True,
        "review_only": True,
        "approval_plan_only": True,
        "transaction_plan_only": True,
        "files_mutated": False,
        "artifacts_written_by_manager": False,
        "approval_recorded": False,
        "approval_artifact_written": False,
        "transaction_started": False,
        "journal_written": False,
        "apply_preflight_invoked": False,
        "fetch_source_map": False,
        "source_map_fetched": False,
        "browser_started": False,
        "cdp_command_sent": False,
        "debugger_execution_performed": False,
        "runtime_evaluated": False,
        "logpoint_installed": False,
        "hook_installed": False,
        "rebuild_executed": False,
        "surface_executor_invoked": False,
        "dispatch_target_invoked": False,
        "executor_invoked": False,
        "calls_mcp": False,
        "mobile_runtime_used": False,
    }
    return {
        "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-plan.v1",
        "status": "ready_for_review",
        "selected_consumer": "debugger",
        "dispatch_surface": "source-map-debugger-execution-result",
        "planned_required_artifact": "workspace/source-map-debugger-execution-result.json",
        "approval_plan_ready_for_review": True,
        "transaction_plan_ready_for_review": True,
        "ready_to_dispatch_now": False,
        "approval_recorded": False,
        "transaction_started": False,
        "journal_written": False,
        "will_write_approval_record": False,
        "will_start_transaction": False,
        "will_invoke_dispatch_target": False,
        "will_invoke_next_action": False,
        "automatic_dispatch_supported": False,
        "automatic_followthrough_supported": False,
        "automatic_execution_supported": False,
        "blockers": [],
        "approval_plan": {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval.v1",
            "approval_plan_id": "source-map-dispatch-approval-plan:test",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "next_action": "execute_reviewed_source_map_debugger_location_action",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "review_gate": "explicit_source_map_followthrough_dispatch_review",
            "source_dispatch_preflight_digest_sha256": "preflight-digest",
            "requires_explicit_review": True,
            "requires_approval_record": True,
            "requires_transaction_journal": True,
            "approval_recorded": False,
            "ready_to_dispatch_now": False,
            "side_effect_policy": side_effect_policy,
        },
        "transaction_plan": {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-plan.v1",
            "transaction_plan_id": "source-map-dispatch-transaction-plan:test",
            "approval_plan_id": "source-map-dispatch-approval-plan:test",
            "transaction_started": False,
            "journal_written_now": False,
            "journal_required_before_dispatch": True,
            "rollback_checkpoint_required": True,
            "ready_to_dispatch_now": False,
            "side_effect_policy": side_effect_policy,
        },
        "side_effect_policy": side_effect_policy,
        "next_action": "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval",
    }


def _ready_source_map_followthrough_dispatch_transaction_preflight() -> dict:
    approval_plan = _ready_source_map_followthrough_dispatch_approval_plan()
    approval_plan_digest = hashlib.sha256(json.dumps(approval_plan, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1",
        "status": "ready_for_review",
        "review_only": True,
        "read_only": True,
        "transaction_preflight_only": True,
        "journal_writer_gate_only": True,
        "source_dispatch_approval_plan_digest_sha256": approval_plan_digest,
        "selected_consumer": "debugger",
        "dispatch_surface": "source-map-debugger-execution-result",
        "planned_required_artifact": "workspace/source-map-debugger-execution-result.json",
        "approval_plan_id": "source-map-dispatch-approval-plan:test",
        "approval_record_id": "source-map-followthrough-dispatch-approval-record:test",
        "transaction_plan_id": "source-map-dispatch-transaction-plan:test",
        "approval_record_verified": True,
        "transaction_plan_verified": True,
        "transaction_preflight_ready_for_review": True,
        "journal_writer_gate_ready_for_review": True,
        "ready_to_write_now": False,
        "ready_to_dispatch_now": False,
        "approval_recorded": True,
        "approved_for_dispatch": True,
        "transaction_started": False,
        "journal_written": False,
        "will_write_transaction_journal": False,
        "will_start_transaction": False,
        "will_invoke_dispatch_target": False,
        "will_invoke_next_action": False,
        "will_execute_debugger": False,
        "will_install_source_logpoint": False,
        "will_install_hook": False,
        "will_run_rebuild": False,
        "automatic_dispatch_supported": False,
        "automatic_followthrough_supported": False,
        "automatic_execution_supported": False,
        "transaction_preflight": {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight-gate.v1",
            "selected_consumer": "debugger",
            "dispatch_surface": "source-map-debugger-execution-result",
            "required_result_artifact": "workspace/source-map-debugger-execution-result.json",
            "approval_plan_id": "source-map-dispatch-approval-plan:test",
            "approval_record_id": "source-map-followthrough-dispatch-approval-record:test",
            "transaction_plan_id": "source-map-dispatch-transaction-plan:test",
            "approval_record_verified": True,
            "ready_to_write_now": False,
            "transaction_started": False,
            "journal_written": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
            "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        },
        "journal_writer_gate": {
            "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-journal-writer-gate.v1",
            "transaction_plan_id": "source-map-dispatch-transaction-plan:test",
            "approval_record_id": "source-map-followthrough-dispatch-approval-record:test",
            "journal_artifact": "workspace/source-map-followthrough-dispatch-transaction-journal.json",
            "requires_approval_record": True,
            "requires_ready_transaction_preflight": True,
            "requires_explicit_journal_write_approval": True,
            "journal_required_before_dispatch": True,
            "approval_recorded": True,
            "approved_for_dispatch": True,
            "ready_to_write_now": False,
            "journal_written_now": False,
            "dispatch_target_invoked": False,
            "executor_invoked": False,
        },
        "blockers": [],
        "side_effect_policy": {"browser_started": False, "cdp_command_sent": False, "runtime_evaluated": False, "calls_mcp": False, "mobile_runtime_used": False},
        "next_action": "review_source_map_followthrough_dispatch_transaction_journal_writer",
    }


class HookSubagentTests(unittest.TestCase):
    def test_review_hook_artifacts_warns_when_installed_hooks_have_no_events(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "function_hooks": {"status": "success", "installed_count": 1, "installed": {"window.buildSign": True}},
            "function_hook_timeline": {"events": []},
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("installed_hooks_without_timeline_events", result["warnings"])
        self.assertEqual(result["next_action"], "invoke_hooked_targets_or_wait_for_runtime_events")
        self.assertEqual(result["summary"]["installed_function_hook_count"], 1)
        self.assertEqual(result["summary"]["installed_function_targets"], ["window.buildSign"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])
        self.assertFalse(result["side_effect_policy"]["target_invoked"])

    def test_review_hook_artifacts_passes_captured_function_and_module_events(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "function_hooks": {"status": "success", "installed": {"window.buildSign": True}},
            "function_hook_timeline": {"events": [{"type": "call"}, {"type": "return"}]},
            "module_hooks": {"status": "success", "installed": {"window.__webpack_require__(731).sign": True}},
            "module_hook_timeline": {"events": [{"type": "call"}]},
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["next_action"], "hook_review_passed")
        self.assertEqual(result["summary"]["timeline_event_count"], 3)
        self.assertEqual(result["summary"]["function_hook_event_type_counts"]["call"], 1)
        self.assertEqual(result["summary"]["module_hook_event_type_counts"]["call"], 1)

    def test_review_hook_artifacts_blocks_failed_hook_artifact(self) -> None:
        tool = make_review_hook_artifacts_tool()
        result = tool(json.dumps({"module_hooks": {"status": "failed", "error": "missing export"}}))

        self.assertEqual(result["status"], "block")
        self.assertIn("hook_artifact_reports_failure", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_hook_failure_and_adjust_target_paths")
        self.assertEqual(result["review_required_items"][0]["module_hook_error"], "missing export")

    def test_review_hook_artifacts_warns_for_unexecuted_async_chunk_load_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_load_plan": {
                "status": "ready_for_review",
                "chunk_id": "731",
                "loader_kind": "webpack-runtime",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_load_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_load_plan_before_execution")
        self.assertEqual(result["summary"]["async_chunk_load_plan_status"], "ready_for_review")
        self.assertFalse(result["summary"]["async_chunk_load_execution_attempted"])
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_bundler_symbol_scope_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "bundler_symbol_scope": {
                "status": "ready_for_review",
                "scope_candidate_count": 1,
                "next_action": "review_symbol_scope_before_source_logpoint_or_hook",
                "hook_readiness": {"source_logpoint_reviewable": True, "automatic_logpoint_install_supported": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("bundler_symbol_scope_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_symbol_scope_before_source_logpoint_or_hook")
        self.assertEqual(result["summary"]["bundler_symbol_scope_status"], "ready_for_review")
        self.assertEqual(result["summary"]["bundler_symbol_scope_candidate_count"], 1)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_bundler_symbol_scope_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"bundler_symbol_scope": {"status": "blocked", "reason": "missing_source_map_payload"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("bundler_symbol_scope_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_source_map_symbol_and_original_source")

    def test_review_hook_artifacts_warns_for_source_map_lookup_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_lookup": {
                "status": "ready_for_review",
                "mapping_found": True,
                "location": {"strategy": "source_map_generated_exact"},
                "next_action": "review_source_map_lookup_before_debugger_or_hook_use",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_lookup_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_lookup_before_debugger_or_hook_use")
        self.assertEqual(result["summary"]["source_map_lookup_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_lookup_mapping_found"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_lookup_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_lookup": {"status": "blocked", "reason": "missing_source_map_payload"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_lookup_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_source_map_payload_and_lookup_position")

    def test_review_hook_artifacts_warns_for_source_map_source_content_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_source_content": {
                "status": "ready_for_review",
                "source_content_available": True,
                "content_summary": {"sha256": "abc123", "preview_exported": False, "raw_content_exported": False},
                "next_action": "review_source_content_availability_before_debugger_or_rebuild",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_source_content_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_content_availability_before_debugger_or_rebuild")
        self.assertEqual(result["summary"]["source_map_source_content_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_source_content_available"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_source_content_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_source_content": {"status": "blocked", "reason": "source_content_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_source_content_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_source_map_with_sources_content")

    def test_review_hook_artifacts_warns_for_source_map_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_readiness": {
                "status": "ready_for_review",
                "readiness": {"debugger_location_ready": True, "rebuild_source_metadata_ready": True},
                "next_action": "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_readiness_before_debugger_rebuild_or_logpoint_planning")
        self.assertEqual(result["summary"]["source_map_readiness_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_readiness_debugger_location_ready"])
        self.assertTrue(result["summary"]["source_map_readiness_rebuild_source_metadata_ready"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_warns_for_source_map_consumer_action_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_consumer_action_plan": {
                "status": "ready_for_review",
                "action_plan_count": 3,
                "next_action": "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_consumer_action_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_consumer_action_plan_before_debugger_rebuild_or_logpoint_execution")
        self.assertEqual(result["summary"]["source_map_consumer_action_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_consumer_action_plan_count"], 3)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_warns_for_source_map_consumer_materialization_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_consumer_materialization": {
                "status": "ready_for_review",
                "materialization_count": 2,
                "next_action": "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_consumer_materialization_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_consumer_materialization_before_debugger_rebuild_logpoint_or_hook_execution")
        self.assertEqual(result["summary"]["source_map_consumer_materialization_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_consumer_materialization_count"], 2)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_consumer_materialization_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_consumer_materialization": {"status": "blocked", "reason": "source_map_consumer_action_plan_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_consumer_materialization_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_consumer_action_plan_descriptor")

    def test_review_hook_artifacts_warns_for_source_map_typed_payload_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_typed_payload_preflight": {
                "status": "ready_for_review",
                "preflight_payload_count": 2,
                "next_action": "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_typed_payload_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_typed_payload_preflight_before_explicit_debugger_logpoint_rebuild_or_hook_execution")
        self.assertEqual(result["summary"]["source_map_typed_payload_preflight_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_typed_payload_preflight_count"], 2)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_typed_payload_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_typed_payload_preflight": {"status": "blocked", "reason": "typed_review_payloads_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_typed_payload_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_source_map_consumer_materialization_with_typed_payloads")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_review_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_review": {
                "status": "ready_for_review",
                "followthrough_review_count": 2,
                "next_action": "choose_explicit_source_map_followthrough_review_surface",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_review_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "choose_explicit_source_map_followthrough_review_surface")
        self.assertEqual(result["summary"]["source_map_followthrough_review_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_review_count"], 2)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_review_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_review": {"status": "blocked", "reason": "source_map_typed_payload_preflight_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_review_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_typed_payload_preflight_descriptor")


    def test_review_hook_artifacts_warns_for_source_map_followthrough_chain_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_chain_readiness": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "completed_stage": "source_map_selected_executor_apply_preflight",
                "next_stage": "selected_executor_result_review",
                "next_action": "review_source_map_debugger_executor_application",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_chain_readiness_requires_next_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_chain_readiness_next_action")
        self.assertEqual(result["summary"]["source_map_followthrough_chain_readiness_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_chain_readiness_selected_consumer"], "debugger")
        self.assertEqual(result["summary"]["source_map_followthrough_chain_readiness_completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(result["summary"]["source_map_followthrough_chain_readiness_next_stage"], "selected_executor_result_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_chain_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_chain_readiness": {"status": "blocked", "reason": "source_map_followthrough_chain_evidence_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_chain_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_chain_readiness_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_one_step_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_one_step_plan": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "source_chain_completed_stage": "source_map_selected_executor_apply_preflight",
                "source_chain_next_stage": "selected_executor_result_review",
                "source_chain_next_action": "review_source_map_debugger_executor_application",
                "planned_step_ready_for_review": True,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_one_step_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_one_step_plan_before_next_action")
        self.assertEqual(result["summary"]["source_map_followthrough_one_step_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_one_step_plan_selected_consumer"], "debugger")
        self.assertEqual(result["summary"]["source_map_followthrough_one_step_plan_source_chain_completed_stage"], "source_map_selected_executor_apply_preflight")
        self.assertEqual(result["summary"]["source_map_followthrough_one_step_plan_source_chain_next_stage"], "selected_executor_result_review")
        self.assertTrue(result["summary"]["source_map_followthrough_one_step_plan_planned_step_ready_for_review"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_one_step_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_one_step_plan": {"status": "blocked", "reason": "source_map_followthrough_one_step_plan_blocked"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_one_step_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_one_step_plan_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_preflight": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "planned_next_action": "review_source_map_debugger_executor_application",
                "planned_required_artifact": "workspace/source-map-debugger-execution-result.json",
                "dispatch_target": {"dispatch_surface": "source-map-debugger-execution-result"},
                "dispatcher_input_ready_for_review": True,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatch_preflight_before_explicit_executor_call")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_preflight_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_preflight_selected_consumer"], "debugger")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_preflight_dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_preflight_dispatcher_input_ready_for_review"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_preflight": {"status": "blocked", "reason": "source_map_followthrough_dispatch_target_unsupported"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatch_preflight_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_approval_plan": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "approval_plan_ready_for_review": True,
                "transaction_plan_ready_for_review": True,
                "ready_to_dispatch_now": False,
                "approval_recorded": False,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_approval_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatch_approval_plan_before_recording_approval")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_approval_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_approval_plan_selected_consumer"], "debugger")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_approval_plan_dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_approval_plan_ready_for_review"])
        self.assertFalse(result["summary"]["source_map_followthrough_dispatch_approval_plan_ready_to_dispatch_now"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_approval_plan": {"status": "blocked", "reason": "source_map_followthrough_dispatch_preflight_not_ready"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_approval_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatch_approval_plan_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_surface_selection_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_surface_selection": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "next_action": "review_selected_source_map_followthrough_surface_before_execution",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_surface_selection_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_selected_source_map_followthrough_surface_before_execution")
        self.assertEqual(result["summary"]["source_map_followthrough_surface_selection_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_surface_selection_selected_consumer"], "debugger")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_surface_selection_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_surface_selection": {"status": "blocked", "reason": "source_map_followthrough_surface_selector_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_surface_selection_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_followthrough_review_descriptor")

    def test_review_hook_artifacts_warns_for_source_map_selected_executor_input_review_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_input_review": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "next_action": "review_debugger_location_before_cdp_command",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_input_review_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_input_before_surface_execution")
        self.assertEqual(result["summary"]["source_map_selected_executor_input_review_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_selected_executor_input_review_selected_consumer"], "debugger")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_input_review_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_input_review": {"status": "blocked", "reason": "selected_executor_input_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_input_review_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_followthrough_surface_selection_descriptor")

    def test_review_hook_artifacts_warns_for_source_map_selected_executor_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_approval_plan": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "next_action": "record_review_approval_for_source_map_debugger_executor",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_approval_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_approval_plan_before_apply")
        self.assertEqual(result["summary"]["source_map_selected_executor_approval_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_selected_executor_approval_plan_selected_consumer"], "debugger")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_approval_plan": {"status": "blocked", "reason": "executor_review_package_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_approval_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_selected_executor_input_review_descriptor")

    def test_record_source_map_selected_executor_approval_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_selected_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_selected_executor_approval_plan()),
                reviewer="alice",
                reason="Reviewed selected debugger executor input.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["approval_recorded"])
            self.assertFalse((artifact_root / "workspace" / "source-map-selected-executor-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(result["side_effect_policy"]["debugger_execution_performed"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_source_map_selected_executor_approval_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_selected_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_selected_executor_approval_plan()),
                mode="apply",
                write_result=True,
                approve_approval_record=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_approval_record", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "source-map-selected-executor-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])

    def test_record_source_map_selected_executor_approval_apply_writes_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_selected_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_selected_executor_approval_plan()),
                reviewer="alice",
                decision="approved",
                reason="Approved selected debugger executor apply preflight input.",
                mode="apply",
                write_result=True,
                approve_approval_record=True,
                expected_action_id="review-debugger-location-use",
                expected_consumer="debugger",
                expected_gate="explicit_debugger_location_review",
                metadata_json=json.dumps({"ticket": "SMAP-1"}),
            )

            record_path = artifact_root / "workspace" / "source-map-selected-executor-approval-record.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["approval_recorded"])
            self.assertTrue(result["approved_for_apply"])
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "reverse-deepagent.source-map-selected-executor-approval-record.v1")
            self.assertEqual(record["selected_consumer"], "debugger")
            self.assertEqual(record["selected_review_gate"], "explicit_debugger_location_review")
            self.assertTrue(record["executor_input_gates"]["approval_recorded"])
            self.assertFalse(record["executor_input_gates"]["ready_to_apply_now"])
            self.assertFalse(record["executor_input_gates"]["surface_executor_invoked"])
            self.assertFalse(record["executor_input_gates"]["debugger_executed"])
            self.assertEqual(record["metadata"]["ticket"], "SMAP-1")
            self.assertTrue(record["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(record["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(record["side_effect_policy"]["runtime_evaluated"])
            self.assertFalse(record["side_effect_policy"]["logpoint_installed"])
            self.assertFalse(record["side_effect_policy"]["hook_installed"])
            self.assertFalse(record["side_effect_policy"]["rebuild_executed"])
            self.assertFalse(record["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record["side_effect_policy"]["mobile_runtime_used"])

    def test_review_hook_artifacts_warns_for_source_map_selected_executor_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_approval_record": {
                "schema_version": "reverse-deepagent.source-map-selected-executor-approval-record.v1",
                "status": "written",
                "selected_consumer": "debugger",
                "approved_for_apply": True,
                "next_action": "review_source_map_selected_executor_apply_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_approval_record_ready_for_apply_preflight", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_apply_preflight")
        self.assertEqual(result["summary"]["source_map_selected_executor_approval_record_status"], "written")
        self.assertTrue(result["summary"]["source_map_selected_executor_approval_record_approved_for_apply"])

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_approval_record": {"status": "blocked", "reason": "approval_plan_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_approval_record_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_selected_executor_approval_plan_descriptor")

    def test_record_source_map_followthrough_dispatch_approval_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_followthrough_dispatch_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_followthrough_dispatch_approval_plan()),
                reviewer="alice",
                reason="Reviewed dispatch approval plan.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["approval_recorded"])
            self.assertFalse((artifact_root / "workspace" / "source-map-followthrough-dispatch-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(result["side_effect_policy"]["transaction_started"])
            self.assertFalse(result["side_effect_policy"]["journal_written"])
            self.assertFalse(result["side_effect_policy"]["dispatch_target_invoked"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_source_map_followthrough_dispatch_approval_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_followthrough_dispatch_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_followthrough_dispatch_approval_plan()),
                mode="apply",
                write_result=True,
                approve_approval_record=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_approval_record", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "source-map-followthrough-dispatch-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])

    def test_record_source_map_followthrough_dispatch_approval_apply_writes_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_followthrough_dispatch_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_source_map_followthrough_dispatch_approval_plan()),
                reviewer="alice",
                decision="approved",
                reason="Approved one reviewed Source Map debugger dispatch.",
                mode="apply",
                write_result=True,
                approve_approval_record=True,
                expected_approval_plan_id="source-map-dispatch-approval-plan:test",
                expected_consumer="debugger",
                expected_dispatch_surface="source-map-debugger-execution-result",
                expected_required_artifact="workspace/source-map-debugger-execution-result.json",
                metadata_json=json.dumps({"ticket": "SMAP-293"}),
            )

            record_path = artifact_root / "workspace" / "source-map-followthrough-dispatch-approval-record.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["approval_recorded"])
            self.assertTrue(result["approved_for_dispatch"])
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1")
            self.assertEqual(record["selected_consumer"], "debugger")
            self.assertEqual(record["dispatch_surface"], "source-map-debugger-execution-result")
            self.assertTrue(record["dispatch_input_gates"]["approval_recorded"])
            self.assertFalse(record["dispatch_input_gates"]["ready_to_dispatch_now"])
            self.assertFalse(record["dispatch_input_gates"]["transaction_started"])
            self.assertFalse(record["dispatch_input_gates"]["journal_written"])
            self.assertFalse(record["dispatch_input_gates"]["dispatch_target_invoked"])
            self.assertEqual(record["metadata"]["ticket"], "SMAP-293")
            self.assertTrue(record["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(record["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(record["side_effect_policy"]["runtime_evaluated"])
            self.assertFalse(record["side_effect_policy"]["logpoint_installed"])
            self.assertFalse(record["side_effect_policy"]["hook_installed"])
            self.assertFalse(record["side_effect_policy"]["rebuild_executed"])
            self.assertFalse(record["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record["side_effect_policy"]["mobile_runtime_used"])

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_approval_record": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-approval-record.v1",
                "status": "written",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "approved_for_dispatch": True,
                "next_action": "review_source_map_followthrough_dispatch_transaction_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_approval_record_ready_for_transaction_preflight", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatch_transaction_preflight")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_approval_record_status"], "written")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_approval_record_approved_for_dispatch"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_approval_record": {"status": "blocked", "reason": "approval_plan_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_approval_record_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_followthrough_dispatch_approval_plan_descriptor")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_transaction_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_transaction_preflight": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-preflight.v1",
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "transaction_preflight_ready_for_review": True,
                "journal_writer_gate_ready_for_review": True,
                "next_action": "review_source_map_followthrough_dispatch_transaction_journal_writer",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_ready_for_journal_writer", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatch_transaction_journal_writer")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_transaction_preflight_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_transaction_preflight_selected_consumer"], "debugger")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_transaction_preflight_dispatch_surface"], "source-map-debugger-execution-result")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_transaction_preflight_ready_for_review"])
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_transaction_preflight_journal_writer_gate_ready"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_transaction_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_transaction_preflight": {"status": "blocked", "reason": "approval_record_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_transaction_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatch_transaction_preflight_failure")

    def test_record_source_map_followthrough_dispatch_transaction_journal_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_followthrough_dispatch_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_source_map_followthrough_dispatch_transaction_preflight()),
                reviewer="alice",
                reason="Reviewed transaction preflight.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["journal_written"])
            self.assertFalse((artifact_root / "workspace" / "source-map-followthrough-dispatch-transaction-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(result["side_effect_policy"]["dispatch_target_invoked"])
            self.assertFalse(result["side_effect_policy"]["executor_invoked"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_source_map_followthrough_dispatch_transaction_journal_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_source_map_followthrough_dispatch_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_source_map_followthrough_dispatch_transaction_preflight()),
                mode="apply",
                write_result=True,
                approve_transaction_journal=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_transaction_journal", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "source-map-followthrough-dispatch-transaction-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])

    def test_record_source_map_followthrough_dispatch_transaction_journal_apply_writes_journal_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            transaction_preflight = _ready_source_map_followthrough_dispatch_transaction_preflight()
            preflight_digest = hashlib.sha256(json.dumps(transaction_preflight, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
            tool = make_record_source_map_followthrough_dispatch_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(transaction_preflight),
                reviewer="alice",
                reason="Approved transaction journal write.",
                mode="apply",
                write_result=True,
                approve_transaction_journal=True,
                expected_approval_record_id="source-map-followthrough-dispatch-approval-record:test",
                expected_transaction_plan_id="source-map-dispatch-transaction-plan:test",
                expected_approval_plan_id="source-map-dispatch-approval-plan:test",
                expected_consumer="debugger",
                expected_dispatch_surface="source-map-debugger-execution-result",
                expected_required_artifact="workspace/source-map-debugger-execution-result.json",
                expected_preflight_digest_sha256=preflight_digest,
                metadata_json=json.dumps({"ticket": "SMAP-295"}),
            )

            journal_path = artifact_root / "workspace" / "source-map-followthrough-dispatch-transaction-journal.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["journal_written"])
            self.assertTrue(result["transaction_started"])
            self.assertTrue(journal_path.exists())
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["schema_version"], "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1")
            self.assertEqual(journal["selected_consumer"], "debugger")
            self.assertEqual(journal["dispatch_surface"], "source-map-debugger-execution-result")
            self.assertTrue(journal["dispatch_input_gates"]["transaction_started"])
            self.assertTrue(journal["dispatch_input_gates"]["journal_written"])
            self.assertFalse(journal["dispatch_input_gates"]["ready_to_dispatch_now"])
            self.assertFalse(journal["dispatch_input_gates"]["dispatch_target_invoked"])
            self.assertFalse(journal["dispatch_input_gates"]["executor_invoked"])
            self.assertEqual(journal["metadata"]["ticket"], "SMAP-295")
            self.assertTrue(journal["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(journal["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(journal["side_effect_policy"]["runtime_evaluated"])
            self.assertFalse(journal["side_effect_policy"]["dispatch_target_invoked"])
            self.assertFalse(journal["side_effect_policy"]["executor_invoked"])
            self.assertFalse(journal["side_effect_policy"]["calls_mcp"])
            self.assertFalse(journal["side_effect_policy"]["mobile_runtime_used"])

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_transaction_journal(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_transaction_journal": {
                "schema_version": "reverse-deepagent.source-map-followthrough-dispatch-transaction-journal.v1",
                "status": "written",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "journal_written": True,
                "transaction_started": True,
                "next_action": "review_source_map_followthrough_dispatch_bounded_executor_gate",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_transaction_journal_ready_for_bounded_gate", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatch_bounded_executor_gate")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_transaction_journal_status"], "written")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_transaction_journal_written"])
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_transaction_journal_started"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_transaction_journal(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_transaction_journal": {"status": "blocked", "reason": "transaction_preflight_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_transaction_journal_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatch_transaction_journal_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatch_bounded_executor_gate(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatch_bounded_executor_gate": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "bounded_executor_gate_ready_for_review": True,
                "ready_for_dispatcher_handoff_review": True,
                "next_action": "review_source_map_followthrough_dispatcher_handoff",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatcher_handoff")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatch_bounded_executor_gate_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_bounded_executor_gate_ready_for_review"])
        self.assertTrue(result["summary"]["source_map_followthrough_dispatch_bounded_executor_gate_ready_for_dispatcher_handoff"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatch_bounded_executor_gate(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatch_bounded_executor_gate": {"status": "blocked", "blockers": ["transaction_journal_written"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatch_bounded_executor_gate_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatch_bounded_executor_gate_failure")


    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatcher_handoff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatcher_handoff": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "dispatcher_handoff_ready_for_review": True,
                "ready_for_explicit_dispatch_review": True,
                "next_action": "review_source_map_followthrough_dispatcher_apply_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatcher_handoff_ready_for_apply_preflight_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatcher_apply_preflight")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatcher_handoff_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatcher_handoff_ready_for_review"])
        self.assertTrue(result["summary"]["source_map_followthrough_dispatcher_handoff_ready_for_explicit_dispatch_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatcher_handoff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatcher_handoff": {"status": "blocked", "blockers": ["bounded_gate_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatcher_handoff_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatcher_handoff_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatcher_apply_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatcher_apply_preflight": {
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "dispatcher_apply_preflight_ready_for_review": True,
                "ready_for_explicit_dispatcher_mvp_review": True,
                "next_action": "review_source_map_followthrough_dispatcher_mvp",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_dispatcher_mvp")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatcher_apply_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatcher_apply_preflight_ready_for_review"])
        self.assertTrue(result["summary"]["source_map_followthrough_dispatcher_apply_preflight_ready_for_dispatcher_mvp"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatcher_apply_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatcher_apply_preflight": {"status": "blocked", "blockers": ["dispatcher_handoff_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatcher_apply_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatcher_apply_preflight_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_dispatcher_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_dispatcher_result": {
                "status": "dispatched",
                "selected_consumer": "debugger",
                "dispatch_surface": "source-map-debugger-execution-result",
                "dispatcher_decision_recorded": True,
                "dispatch_target_invoked": False,
                "selected_executor_invoked": False,
                "selected_executor_apply_preflight_invoked": False,
                "next_action": "review_source_map_selected_executor_apply_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_dispatcher_result_ready_for_selected_executor_apply_preflight", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_apply_preflight")
        self.assertEqual(result["summary"]["source_map_followthrough_dispatcher_result_status"], "dispatched")
        self.assertTrue(result["summary"]["source_map_followthrough_dispatcher_result_decision_recorded"])
        self.assertFalse(result["summary"]["source_map_followthrough_dispatcher_result_selected_executor_invoked"])
        self.assertFalse(result["summary"]["source_map_followthrough_dispatcher_result_selected_executor_apply_preflight_invoked"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_dispatcher_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_dispatcher_result": {"status": "blocked", "blockers": ["dispatcher_apply_preflight_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_dispatcher_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_dispatcher_result_failure")

    def test_review_hook_artifacts_warns_for_source_map_selected_executor_apply_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_apply_preflight": {
                "schema_version": "reverse-deepagent.source-map-selected-executor-apply-preflight.v1",
                "status": "ready_for_review",
                "selected_consumer": "debugger",
                "ready_for_selected_executor_review": True,
                "next_action": "review_source_map_debugger_executor_application",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_apply_preflight_ready_for_executor_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_application_handoff")
        self.assertEqual(result["summary"]["source_map_selected_executor_apply_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["source_map_selected_executor_apply_preflight_ready_for_selected_executor_review"])

    def test_review_hook_artifacts_warns_for_source_map_selected_executor_application_handoff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_application_handoff": {
                "schema_version": "reverse-deepagent.source-map-selected-executor-application-handoff.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "application_surface": "source-map-hook-application",
                "ready_for_application_review": True,
                "next_action": "review_source_map_hook_executor_application",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_application_handoff_ready_for_application_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_application")
        self.assertEqual(result["summary"]["source_map_selected_executor_application_handoff_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_selected_executor_application_handoff_application_surface"], "source-map-hook-application")
        self.assertTrue(result["summary"]["source_map_selected_executor_application_handoff_ready_for_application_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_application_handoff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_application_handoff": {"status": "blocked", "blockers": ["source_map_selected_executor_apply_preflight_not_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_application_handoff_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_selected_executor_application_handoff_failure")


    def test_review_hook_artifacts_warns_for_source_map_selected_executor_result_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_selected_executor_result_checkpoint": {
                "schema_version": "reverse-deepagent.source-map-selected-executor-result-checkpoint.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "application_surface": "source-map-hook-application",
                "application_result_status": "success",
                "ready_for_next_explicit_review": True,
                "next_action": "review_source_map_selected_executor_result_checkpoint",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_selected_executor_result_checkpoint_ready_for_followthrough_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_selected_executor_result_checkpoint")
        self.assertEqual(result["summary"]["source_map_selected_executor_result_checkpoint_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_selected_executor_result_checkpoint_application_surface"], "source-map-hook-application")
        self.assertTrue(result["summary"]["source_map_selected_executor_result_checkpoint_ready_for_next_explicit_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_result_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_result_checkpoint": {"status": "blocked", "blockers": ["source_map_selected_executor_application_result_not_success"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_result_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_selected_executor_result_checkpoint_failure")

    def test_review_hook_artifacts_warns_for_source_map_followthrough_completion_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_followthrough_completion_checkpoint": {
                "schema_version": "reverse-deepagent.source-map-followthrough-completion-checkpoint.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "completion_status": "terminal_review_candidate",
                "terminal_review_candidate": True,
                "followup_required": False,
                "ready_for_completion_review": True,
                "next_action": "inspect_source_map_hook_install_timeline",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_followthrough_completion_checkpoint_ready_for_completion_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_followthrough_completion_checkpoint")
        self.assertEqual(result["summary"]["source_map_followthrough_completion_checkpoint_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_followthrough_completion_checkpoint_selected_consumer"], "hook")
        self.assertEqual(result["summary"]["source_map_followthrough_completion_checkpoint_completion_status"], "terminal_review_candidate")
        self.assertTrue(result["summary"]["source_map_followthrough_completion_checkpoint_terminal_review_candidate"])

    def test_review_hook_artifacts_blocks_failed_source_map_followthrough_completion_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_followthrough_completion_checkpoint": {"status": "blocked", "blockers": ["source_map_selected_executor_result_checkpoint_not_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_followthrough_completion_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_followthrough_completion_checkpoint_failure")

    def test_review_hook_artifacts_warns_for_source_map_terminal_review_package(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_terminal_review_package": {
                "schema_version": "reverse-deepagent.source-map-terminal-review-package.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "completion_status": "terminal_review_candidate",
                "ready_for_terminal_review": True,
                "next_action": "review_source_map_terminal_review_package",
                "terminal_review_package": {"package_kind": "terminal-review-package", "recommended_review_action": "inspect_source_map_hook_install_timeline"},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_terminal_review_package_ready_for_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_terminal_review_package")
        self.assertEqual(result["summary"]["source_map_terminal_review_package_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_terminal_review_package_selected_consumer"], "hook")
        self.assertTrue(result["summary"]["source_map_terminal_review_package_ready_for_terminal_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_terminal_review_package(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_terminal_review_package": {"status": "blocked", "blockers": ["source_map_followthrough_completion_checkpoint_not_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_terminal_review_package_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_terminal_review_package_failure")

    def test_review_hook_artifacts_warns_for_source_map_terminal_review_closure_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_terminal_review_closure_checkpoint": {
                "schema_version": "reverse-deepagent.source-map-terminal-review-closure-checkpoint.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "closure_status": "terminal_review_observed",
                "ready_for_closure_audit_review": True,
                "next_action": "review_source_map_terminal_review_closure_checkpoint",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_terminal_review_closure_checkpoint_ready_for_closure_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_terminal_review_closure_checkpoint")
        self.assertEqual(result["summary"]["source_map_terminal_review_closure_checkpoint_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_terminal_review_closure_checkpoint_selected_consumer"], "hook")
        self.assertTrue(result["summary"]["source_map_terminal_review_closure_checkpoint_ready_for_closure_audit_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_terminal_review_closure_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_terminal_review_closure_checkpoint": {"status": "blocked", "blockers": ["source_map_terminal_review_observed_result_missing"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_terminal_review_closure_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_terminal_review_closure_checkpoint_failure")

    def test_review_hook_artifacts_warns_for_source_map_terminal_review_final_audit(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_terminal_review_final_audit": {
                "schema_version": "reverse-deepagent.source-map-terminal-review-final-audit.v1",
                "status": "ready_for_review",
                "selected_consumer": "hook",
                "final_audit_status": "source_map_followthrough_review_closed",
                "ready_for_final_audit_review": True,
                "next_action": "review_source_map_terminal_review_final_audit",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_terminal_review_final_audit_ready_for_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_terminal_review_final_audit")
        self.assertEqual(result["summary"]["source_map_terminal_review_final_audit_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_terminal_review_final_audit_selected_consumer"], "hook")
        self.assertTrue(result["summary"]["source_map_terminal_review_final_audit_ready_for_final_audit_review"])

    def test_review_hook_artifacts_blocks_failed_source_map_terminal_review_final_audit(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_terminal_review_final_audit": {"status": "blocked", "blockers": ["source_map_terminal_review_closure_checkpoint_not_ready"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_terminal_review_final_audit_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_terminal_review_final_audit_failure")

    def test_review_hook_artifacts_blocks_failed_source_map_selected_executor_apply_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_selected_executor_apply_preflight": {"status": "blocked", "reason": "approval_record_plan_digest_mismatch"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_selected_executor_apply_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_matching_source_map_selected_executor_approval_plan_and_record")

    def test_review_hook_artifacts_warns_for_source_map_source_logpoint_install_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_source_logpoint_install_result": {
                "status": "success",
                "selected_consumer": "source-logpoint",
                "breakpoint_count": 1,
                "event_count": 1,
                "logpoint_installed": True,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_source_logpoint_install_result_requires_timeline_review", result["warnings"])
        self.assertEqual(result["next_action"], "inspect_source_map_source_logpoint_events")
        self.assertEqual(result["summary"]["source_map_source_logpoint_install_result_status"], "success")
        self.assertTrue(result["summary"]["source_map_source_logpoint_install_result_logpoint_installed"])

    def test_review_hook_artifacts_blocks_failed_source_map_source_logpoint_install_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_source_logpoint_install_result": {"status": "failed", "error": "Debugger.setBreakpointByUrl failed"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_source_logpoint_install_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_source_logpoint_install_failure")

    def test_review_hook_artifacts_warns_for_source_map_hook_install_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_hook_install_result": {
                "status": "success",
                "selected_consumer": "hook",
                "hook_kind": "function",
                "hook_installed": True,
                "installed_count": 1,
                "event_count": 2,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_hook_install_result_requires_timeline_review", result["warnings"])
        self.assertEqual(result["next_action"], "inspect_source_map_hook_events")
        self.assertEqual(result["summary"]["source_map_hook_install_result_status"], "success")
        self.assertEqual(result["summary"]["source_map_hook_install_result_hook_kind"], "function")
        self.assertEqual(result["summary"]["source_map_hook_install_result_installed_count"], 1)
        self.assertEqual(result["summary"]["source_map_hook_install_result_event_count"], 2)
        self.assertTrue(result["summary"]["source_map_hook_install_result_hook_installed"])

    def test_review_hook_artifacts_warns_for_source_map_hook_candidates(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_hook_candidates": {
                "status": "ready_for_review",
                "bundler_kind": "webpack",
                "candidate_count": 2,
                "ready_for_hook_install_review_count": 1,
                "candidates": [{"candidate_id": "source-map-hook-function:buildSign:4:0:0"}],
            }
        }

        result = tool(json.dumps(payload))

        self.assertIn("source_map_hook_candidates_require_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_hook_candidates_before_selected_hook_install")
        self.assertEqual(result["summary"]["source_map_hook_candidates_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_hook_candidates_candidate_count"], 2)
        self.assertEqual(result["summary"]["source_map_hook_candidates_ready_for_install_review_count"], 1)
        self.assertEqual(result["summary"]["source_map_hook_candidates_bundler_kind"], "webpack")
        self.assertEqual(result["summary"]["source_map_hook_candidates_candidate_ids"], ["source-map-hook-function:buildSign:4:0:0"])

    def test_review_hook_artifacts_blocks_failed_source_map_hook_candidates(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_hook_candidates": {"status": "blocked", "blockers": ["bundler_symbol_scope_not_ready"]}}

        result = tool(json.dumps(payload))

        self.assertIn("source_map_hook_candidates_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_hook_candidate_refinement_failure")

    def test_review_hook_artifacts_warns_for_source_map_hook_candidate_selection(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_hook_candidate_selection": {
                "status": "ready_for_review",
                "candidate_count": 1,
                "selected_candidate_id": "source-map-hook-function:buildSign:4:0:0",
                "selected_action_id": "source-map-hook-candidate:source-map-hook-function:buildSign:4:0:0",
                "selected_consumer": "hook",
                "ready_for_selected_executor_input_review": True,
                "review_only": True,
                "plan_only": True,
                "handoff_only": True,
                "hook_installed": False,
                "automatic_hook_installation": False,
                "side_effect_policy": {"hook_installed": False, "automatic_hook_installation": False, "runtime_evaluated": False, "calls_mcp": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertIn("source_map_hook_candidate_selection_requires_input_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_selected_source_map_hook_candidate_input")
        self.assertEqual(result["summary"]["source_map_hook_candidate_selection_status"], "ready_for_review")
        self.assertEqual(result["summary"]["source_map_hook_candidate_selection_candidate_count"], 1)
        self.assertEqual(result["summary"]["source_map_hook_candidate_selection_selected_candidate_id"], "source-map-hook-function:buildSign:4:0:0")
        self.assertTrue(result["summary"]["source_map_hook_candidate_selection_ready_for_selected_executor_input_review"])
        self.assertFalse(result["summary"]["source_map_hook_candidate_selection_hook_installed"])
        self.assertFalse(result["summary"]["source_map_hook_candidate_selection_automatic_hook_installation"])

    def test_review_hook_artifacts_blocks_failed_source_map_hook_candidate_selection(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_hook_candidate_selection": {"status": "blocked", "blockers": ["source_map_hook_candidate_selection_ambiguous"]}}

        result = tool(json.dumps(payload))

        self.assertIn("source_map_hook_candidate_selection_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_hook_candidate_selection_failure")

    def test_review_hook_artifacts_blocks_failed_source_map_hook_install_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_hook_install_result": {"status": "blocked", "blockers": ["source_map_hook_install_not_approved"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_hook_install_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_hook_install_failure")

    def test_review_hook_artifacts_warns_for_source_map_rebuild_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_rebuild_result": {
                "status": "success",
                "selected_consumer": "rebuild",
                "source_content_digest": "abc123",
                "metadata_only": True,
                "rebuild_metadata_applied": True,
                "rebuild_executed": False,
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_rebuild_result_requires_rebuild_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_source_map_rebuild_metadata_before_rebuild_generation")
        self.assertEqual(result["summary"]["source_map_rebuild_result_status"], "success")
        self.assertEqual(result["summary"]["source_map_rebuild_result_digest"], "abc123")
        self.assertTrue(result["summary"]["source_map_rebuild_result_metadata_only"])
        self.assertTrue(result["summary"]["source_map_rebuild_result_rebuild_metadata_applied"])
        self.assertFalse(result["summary"]["source_map_rebuild_result_rebuild_executed"])

    def test_review_hook_artifacts_blocks_failed_source_map_rebuild_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_rebuild_result": {"status": "blocked", "blockers": ["source_map_rebuild_metadata_not_approved"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_rebuild_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_rebuild_metadata_application_failure")

    def test_review_hook_artifacts_warns_for_source_map_rebuild_generation_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "source_map_rebuild_generation_result": {
                "status": "success",
                "source_content_digest": "abc123",
                "rebuild_bundle_generated": True,
                "rebuild_executed": True,
                "rebuild_ready": True,
                "generated_file_count": 5,
                "algorithm_strategy_id": "md5_keyword_timestamp",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("source_map_rebuild_generation_result_requires_rebuild_artifact_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_generated_rebuild_bundle_before_delivery")
        self.assertEqual(result["summary"]["source_map_rebuild_generation_result_status"], "success")
        self.assertTrue(result["summary"]["source_map_rebuild_generation_result_ready"])
        self.assertEqual(result["summary"]["source_map_rebuild_generation_result_generated_file_count"], 5)
        self.assertTrue(result["summary"]["source_map_rebuild_generation_result_rebuild_bundle_generated"])
        self.assertTrue(result["summary"]["source_map_rebuild_generation_result_rebuild_executed"])
        self.assertEqual(result["summary"]["source_map_rebuild_generation_result_algorithm_strategy_id"], "md5_keyword_timestamp")

    def test_review_hook_artifacts_blocks_failed_source_map_rebuild_generation_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_rebuild_generation_result": {"status": "blocked", "blockers": ["source_map_rebuild_generation_not_approved"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_rebuild_generation_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_source_map_rebuild_generation_failure")

    def test_review_hook_artifacts_blocks_failed_source_map_consumer_action_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_consumer_action_plan": {"status": "blocked", "reason": "source_map_readiness_descriptor_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_consumer_action_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_source_map_readiness_descriptor")

    def test_review_hook_artifacts_blocks_failed_source_map_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"source_map_readiness": {"status": "blocked", "reason": "source_map_lookup_descriptor_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("source_map_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_source_map_lookup_and_source_content_descriptors")

    def test_review_hook_artifacts_warns_for_object_graph_diff_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "object_graph_diff": {
                "status": "ready_for_review",
                "change_count": 2,
                "risk_summary": {"risk": "high"},
                "next_action": "review_object_graph_diff_before_hook_or_replay",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("object_graph_diff_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_object_graph_diff_before_hook_or_replay")
        self.assertEqual(result["summary"]["object_graph_diff_status"], "ready_for_review")
        self.assertEqual(result["summary"]["object_graph_diff_change_count"], 2)
        self.assertEqual(result["summary"]["object_graph_diff_risk"], "high")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_object_graph_diff_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"object_graph_diff": {"status": "blocked", "reason": "missing_before_or_after_snapshot"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("object_graph_diff_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_before_and_after_object_graph_snapshots")

    def test_review_hook_artifacts_warns_for_runtime_object_graph_diff_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "runtime_object_graph_diff": {
                "status": "ready_for_review",
                "change_count": 4,
                "runtime_collection": {"root_path": "window.__appState"},
                "risk_summary": {"risk": "high"},
                "side_effect_policy": {"runtime_evaluated": True, "full_heap_snapshot": False},
                "next_action": "review_runtime_object_graph_diff_before_hook_or_replay",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("runtime_object_graph_diff_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_runtime_object_graph_diff_before_hook_or_replay")
        self.assertEqual(result["summary"]["runtime_object_graph_diff_status"], "ready_for_review")
        self.assertEqual(result["summary"]["runtime_object_graph_diff_root_path"], "window.__appState")
        self.assertEqual(result["summary"]["runtime_object_graph_diff_change_count"], 4)
        self.assertEqual(result["summary"]["runtime_object_graph_diff_risk"], "high")
        self.assertTrue(result["summary"]["runtime_object_graph_diff_runtime_evaluated"])
        self.assertFalse(result["summary"]["runtime_object_graph_diff_full_heap_snapshot"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_runtime_object_graph_diff_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"runtime_object_graph_diff": {"status": "blocked", "reason": "unsupported_runtime_object_root_path"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("runtime_object_graph_diff_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_supported_runtime_object_root_path")


    def test_review_hook_artifacts_warns_for_heap_snapshot_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_readiness": {
                "status": "ready_for_review",
                "capability_evidence": {
                    "browser_provider_id": "remote-cdp",
                    "cdp_available": True,
                    "heap_profiler_capability": "provided",
                },
                "safety_gates": {"raw_heap_export_allowed": False},
                "heap_snapshot_collected": False,
                "side_effect_policy": {"browser_started": False, "cdp_command_sent": False},
                "next_action": "review_heap_snapshot_readiness_before_collection",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_readiness_before_collection")
        self.assertEqual(result["summary"]["heap_snapshot_readiness_status"], "ready_for_review")
        self.assertEqual(result["summary"]["heap_snapshot_readiness_provider_id"], "remote-cdp")
        self.assertTrue(result["summary"]["heap_snapshot_readiness_cdp_available"])
        self.assertEqual(result["summary"]["heap_snapshot_readiness_heap_profiler_capability"], "provided")
        self.assertFalse(result["summary"]["heap_snapshot_readiness_heap_snapshot_collected"])
        self.assertFalse(result["summary"]["heap_snapshot_readiness_cdp_command_sent"])
        self.assertFalse(result["summary"]["heap_snapshot_readiness_browser_started"])
        self.assertFalse(result["summary"]["heap_snapshot_readiness_raw_heap_export_allowed"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_readiness": {"status": "blocked", "blockers": ["cdp_capability_evidence_missing_or_unavailable"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_cdp_heap_profiler_capability_evidence")

    def test_review_hook_artifacts_warns_for_heap_snapshot_collect_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_collect": {
                "status": "collected",
                "review_approved": True,
                "explicit_collection": True,
                "heap_snapshot_collected": True,
                "heap_diff_computed": False,
                "raw_heap_exported": False,
                "snapshot_metadata": {"snapshot_digest": "sha256:abc", "snapshot_byte_count": 32, "chunk_count": 1},
                "side_effect_policy": {
                    "cdp_command_sent": True,
                    "heap_profiler_enabled": True,
                    "heap_diff_computed": False,
                    "raw_heap_exported": False,
                    "complete_heap_traversal": False,
                },
                "next_action": "review_heap_snapshot_collect_before_heap_diff",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_collect_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_collect_before_heap_diff")
        self.assertEqual(result["summary"]["heap_snapshot_collect_status"], "collected")
        self.assertTrue(result["summary"]["heap_snapshot_collect_review_approved"])
        self.assertTrue(result["summary"]["heap_snapshot_collect_explicit_collection"])
        self.assertTrue(result["summary"]["heap_snapshot_collect_heap_snapshot_collected"])
        self.assertEqual(result["summary"]["heap_snapshot_collect_digest"], "sha256:abc")
        self.assertEqual(result["summary"]["heap_snapshot_collect_byte_count"], 32)
        self.assertEqual(result["summary"]["heap_snapshot_collect_chunk_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_collect_cdp_command_sent"])
        self.assertTrue(result["summary"]["heap_snapshot_collect_heap_profiler_enabled"])
        self.assertFalse(result["summary"]["heap_snapshot_collect_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_collect_raw_heap_exported"])
        self.assertFalse(result["summary"]["heap_snapshot_collect_complete_heap_traversal"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_collect_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_collect": {"status": "blocked", "blockers": ["heap_snapshot_collect_review_approval_required"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_collect_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_collect_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_readiness": {
                "status": "ready_for_review",
                "heap_diff_computed": False,
                "raw_heap_loaded": False,
                "raw_heap_exported": False,
                "pair_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after", "digest_equal": False, "byte_delta": 32},
                "side_effect_policy": {
                    "heap_diff_computed": False,
                    "raw_heap_loaded": False,
                    "raw_heap_exported": False,
                    "complete_heap_traversal": False,
                },
                "next_action": "review_heap_snapshot_diff_readiness_before_diff_executor",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_readiness_before_diff_executor")
        self.assertEqual(result["summary"]["heap_snapshot_diff_readiness_status"], "ready_for_review")
        self.assertEqual(result["summary"]["heap_snapshot_diff_readiness_before_digest"], "sha256:before")
        self.assertEqual(result["summary"]["heap_snapshot_diff_readiness_after_digest"], "sha256:after")
        self.assertFalse(result["summary"]["heap_snapshot_diff_readiness_digest_equal"])
        self.assertEqual(result["summary"]["heap_snapshot_diff_readiness_byte_delta"], 32)
        self.assertFalse(result["summary"]["heap_snapshot_diff_readiness_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_readiness_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_readiness_raw_heap_exported"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_readiness_complete_heap_traversal"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_readiness_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_diff_readiness": {"status": "blocked", "blockers": ["before_heap_snapshot_collect_descriptor_required"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_two_reviewed_heap_snapshot_collect_descriptors")

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_executor_preflight": {
                "status": "ready_for_review",
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "readiness_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after"},
                "ingestion_policy": {"raw_heap_ingestion_policy": "metadata-only"},
                "safety_gates": {"future_diff_executor_implemented": False},
                "side_effect_policy": {
                    "raw_heap_loaded": False,
                    "raw_heap_parsed": False,
                    "raw_heap_exported": False,
                    "heap_diff_computed": False,
                    "complete_heap_traversal": False,
                },
                "next_action": "review_heap_snapshot_diff_executor_preflight_before_implementation",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_preflight_before_implementation")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_preflight_status"], "ready_for_review")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_preflight_before_digest"], "sha256:before")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_preflight_after_digest"], "sha256:after")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_preflight_raw_heap_ingestion_policy"], "metadata-only")
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_future_diff_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_raw_heap_parsed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_raw_heap_exported"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_preflight_complete_heap_traversal"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_executor_preflight_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_diff_executor_preflight": {"status": "blocked", "blockers": ["heap_snapshot_diff_readiness_descriptor_required"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_executor_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_diff_executor_preflight_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_executor_approval_plan": {
                "status": "ready_for_review",
                "approval_recorded": False,
                "transaction_started": False,
                "journal_written_now": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "preflight_summary": {"before_digest": "sha256:before", "after_digest": "sha256:after"},
                "approval_plan": {"approval_scope": "heap-snapshot-diff-executor", "approval_recorded": False},
                "transaction_plan": {"transaction_id": "heap-diff-txn-1", "journal_written_now": False},
                "future_executor_contract": {"implemented": False},
                "side_effect_policy": {
                    "approval_recorded": False,
                    "transaction_started": False,
                    "journal_written_now": False,
                    "executor_invoked": False,
                    "raw_heap_loaded": False,
                    "raw_heap_exported": False,
                    "heap_diff_computed": False,
                    "complete_heap_traversal": False,
                },
                "next_action": "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_approval_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_approval_plan_before_recording_approval")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_approval_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_approval_plan_before_digest"], "sha256:before")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_approval_plan_after_digest"], "sha256:after")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_approval_plan_approval_scope"], "heap-snapshot-diff-executor")
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_approval_recorded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_transaction_started"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_journal_written_now"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_raw_heap_exported"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_approval_plan_complete_heap_traversal"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_executor_approval_plan_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_diff_executor_approval_plan": {"status": "blocked", "blockers": ["heap_snapshot_diff_executor_preflight_descriptor_required"]}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_executor_approval_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_diff_executor_approval_plan_blockers")

    def test_record_heap_snapshot_diff_executor_approval_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_diff_executor_approval_plan()),
                reviewer="alice",
                reason="Reviewed heap diff executor approval plan.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["approval_recorded"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-diff-executor-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(result["side_effect_policy"]["transaction_started"])
            self.assertFalse(result["side_effect_policy"]["journal_written"])
            self.assertFalse(result["side_effect_policy"]["executor_invoked"])
            self.assertFalse(result["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(result["side_effect_policy"]["heap_diff_computed"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_heap_snapshot_diff_executor_approval_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_diff_executor_approval_plan()),
                mode="apply",
                write_result=True,
                approve_heap_snapshot_diff_executor=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_heap_snapshot_diff_executor_approval", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-diff-executor-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])

    def test_record_heap_snapshot_diff_executor_approval_apply_writes_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_diff_executor_approval_plan()),
                reviewer="alice",
                decision="approved",
                reason="Approved heap snapshot diff executor transaction preflight handoff.",
                mode="apply",
                write_result=True,
                approve_heap_snapshot_diff_executor=True,
                expected_approval_scope="heap-snapshot-diff-executor",
                expected_transaction_id="heap-diff-txn-test",
                expected_idempotency_key="heap-diff-idem-test",
                metadata_json=json.dumps({"ticket": "HEAP-319"}),
            )

            record_path = artifact_root / "workspace" / "heap-snapshot-diff-executor-approval-record.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["approval_recorded"])
            self.assertTrue(result["approved_for_execution"])
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1")
            self.assertEqual(record["approval_scope"], "heap-snapshot-diff-executor")
            self.assertEqual(record["transaction_id"], "heap-diff-txn-test")
            self.assertTrue(record["executor_input_gates"]["approval_recorded"])
            self.assertFalse(record["executor_input_gates"]["ready_to_execute_now"])
            self.assertFalse(record["executor_input_gates"]["transaction_started"])
            self.assertFalse(record["executor_input_gates"]["journal_written"])
            self.assertFalse(record["executor_input_gates"]["bounded_executor_gate_written"])
            self.assertFalse(record["executor_input_gates"]["executor_invoked"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_loaded"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_parsed"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_exported"])
            self.assertFalse(record["executor_input_gates"]["heap_diff_computed"])
            self.assertEqual(record["metadata"]["ticket"], "HEAP-319")
            self.assertTrue(record["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(record["side_effect_policy"]["transaction_started"])
            self.assertFalse(record["side_effect_policy"]["journal_written"])
            self.assertFalse(record["side_effect_policy"]["bounded_executor_gate_written"])
            self.assertFalse(record["side_effect_policy"]["executor_invoked"])
            self.assertFalse(record["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_parsed"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_exported"])
            self.assertFalse(record["side_effect_policy"]["heap_diff_computed"])
            self.assertFalse(record["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record["side_effect_policy"]["mobile_runtime_used"])

    def test_record_heap_snapshot_retained_size_approval_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_retained_size_approval_plan()),
                reviewer="alice",
                reason="Reviewed retained-size approval plan.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["approval_recorded"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-retained-size-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(result["side_effect_policy"]["transaction_started"])
            self.assertFalse(result["side_effect_policy"]["journal_written"])
            self.assertFalse(result["side_effect_policy"]["executor_invoked"])
            self.assertFalse(result["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(result["side_effect_policy"]["retained_size_proven"])
            self.assertFalse(result["side_effect_policy"]["path_to_root_computed"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_heap_snapshot_retained_size_approval_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_retained_size_approval_plan()),
                mode="apply",
                write_result=True,
                approve_heap_snapshot_retained_size=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_heap_snapshot_retained_size_approval", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-retained-size-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])

    def test_record_heap_snapshot_retained_size_approval_apply_writes_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_approval_tool(artifact_root)

            result = tool(
                approval_plan_json=json.dumps(_ready_heap_snapshot_retained_size_approval_plan()),
                reviewer="alice",
                decision="approved",
                reason="Approved retained-size transaction preflight handoff.",
                mode="apply",
                write_result=True,
                approve_heap_snapshot_retained_size=True,
                expected_approval_plan_id="retained-size-approval-plan-test",
                expected_transaction_plan_id="retained-size-approval-plan-test",
                expected_candidate_digest="retained-size-candidate-digest-test",
                metadata_json=json.dumps({"ticket": "HEAP-330"}),
            )

            record_path = artifact_root / "workspace" / "heap-snapshot-retained-size-approval-record.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["approval_recorded"])
            self.assertTrue(result["approved_for_execution"])
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1")
            self.assertEqual(record["approval_plan_id"], "retained-size-approval-plan-test")
            self.assertEqual(record["transaction_plan_id"], "retained-size-approval-plan-test")
            self.assertEqual(record["candidate_digest"], "retained-size-candidate-digest-test")
            self.assertTrue(record["executor_input_gates"]["approval_recorded"])
            self.assertFalse(record["executor_input_gates"]["ready_to_execute_now"])
            self.assertFalse(record["executor_input_gates"]["transaction_started"])
            self.assertFalse(record["executor_input_gates"]["journal_written"])
            self.assertFalse(record["executor_input_gates"]["bounded_executor_gate_written"])
            self.assertFalse(record["executor_input_gates"]["executor_invoked"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_loaded"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_parsed"])
            self.assertFalse(record["executor_input_gates"]["raw_heap_exported"])
            self.assertFalse(record["executor_input_gates"]["heap_diff_computed"])
            self.assertFalse(record["executor_input_gates"]["retained_size_proven"])
            self.assertFalse(record["executor_input_gates"]["path_to_root_computed"])
            self.assertEqual(record["next_action"], "review_heap_snapshot_retained_size_transaction_preflight")
            self.assertEqual(record["metadata"]["ticket"], "HEAP-330")
            self.assertTrue(record["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(record["side_effect_policy"]["transaction_started"])
            self.assertFalse(record["side_effect_policy"]["journal_written"])
            self.assertFalse(record["side_effect_policy"]["bounded_executor_gate_written"])
            self.assertFalse(record["side_effect_policy"]["executor_invoked"])
            self.assertFalse(record["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_parsed"])
            self.assertFalse(record["side_effect_policy"]["raw_heap_exported"])
            self.assertFalse(record["side_effect_policy"]["retained_size_proven"])
            self.assertFalse(record["side_effect_policy"]["path_to_root_computed"])
            self.assertFalse(record["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record["side_effect_policy"]["mobile_runtime_used"])

    def test_record_heap_snapshot_retained_size_transaction_journal_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_retained_size_transaction_preflight()),
                reviewer="alice",
                reason="Reviewed retained-size transaction preflight.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["journal_written"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-retained-size-executor-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(result["side_effect_policy"]["bounded_executor_gate_written"])
            self.assertFalse(result["side_effect_policy"]["executor_invoked"])
            self.assertFalse(result["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(result["side_effect_policy"]["retained_size_proven"])
            self.assertFalse(result["side_effect_policy"]["path_to_root_computed"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_heap_snapshot_retained_size_transaction_journal_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_retained_size_transaction_preflight()),
                mode="apply",
                write_result=True,
                approve_transaction_journal=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_transaction_journal", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-retained-size-executor-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])

    def test_record_heap_snapshot_retained_size_transaction_journal_apply_writes_journal_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_retained_size_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_retained_size_transaction_preflight()),
                reviewer="alice",
                reason="Approved retained-size journal write.",
                mode="apply",
                write_result=True,
                approve_transaction_journal=True,
                expected_approval_plan_id="retained-size-approval-plan-test",
                expected_transaction_plan_id="retained-size-approval-plan-test",
                expected_candidate_digest="retained-size-candidate-digest-test",
                metadata_json=json.dumps({"ticket": "HEAP-332"}),
            )

            journal_path = artifact_root / "workspace" / "heap-snapshot-retained-size-executor-journal.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["journal_written"])
            self.assertTrue(result["transaction_started"])
            self.assertTrue(journal_path.exists())
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["schema_version"], "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1")
            self.assertEqual(journal["transaction_plan_id"], "retained-size-approval-plan-test")
            self.assertEqual(journal["candidate_digest"], "retained-size-candidate-digest-test")
            self.assertTrue(journal["journal_summary"]["journal_written"])
            self.assertFalse(journal["journal_summary"]["bounded_executor_gate_written"])
            self.assertFalse(journal["journal_summary"]["executor_invoked"])
            self.assertFalse(journal["journal_summary"]["raw_heap_loaded"])
            self.assertFalse(journal["journal_summary"]["retained_size_proven"])
            self.assertFalse(journal["journal_summary"]["path_to_root_computed"])
            self.assertFalse(journal["executor_input_gates"]["ready_to_execute_now"])
            self.assertTrue(journal["executor_input_gates"]["journal_written"])
            self.assertFalse(journal["executor_input_gates"]["bounded_executor_gate_written"])
            self.assertFalse(journal["executor_input_gates"]["executor_invoked"])
            self.assertFalse(journal["executor_input_gates"]["raw_heap_parsed"])
            self.assertFalse(journal["executor_input_gates"]["retained_size_proven"])
            self.assertFalse(journal["executor_input_gates"]["path_to_root_computed"])
            self.assertEqual(journal["metadata"]["ticket"], "HEAP-332")
            self.assertTrue(journal["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(journal["side_effect_policy"]["retained_size_proven"])
            self.assertFalse(journal["side_effect_policy"]["path_to_root_computed"])


    def test_record_heap_snapshot_diff_executor_transaction_journal_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_diff_executor_transaction_preflight()),
                reviewer="alice",
                reason="Reviewed heap diff executor transaction preflight.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["journal_written"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-diff-executor-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(result["side_effect_policy"]["bounded_executor_gate_written"])
            self.assertFalse(result["side_effect_policy"]["executor_invoked"])
            self.assertFalse(result["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(result["side_effect_policy"]["heap_diff_computed"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])

    def test_record_heap_snapshot_diff_executor_transaction_journal_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_diff_executor_transaction_preflight()),
                mode="apply",
                write_result=True,
                approve_transaction_journal=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_transaction_journal", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "heap-snapshot-diff-executor-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])

    def test_record_heap_snapshot_diff_executor_transaction_journal_apply_writes_journal_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_heap_snapshot_diff_executor_transaction_journal_tool(artifact_root)

            result = tool(
                transaction_preflight_json=json.dumps(_ready_heap_snapshot_diff_executor_transaction_preflight()),
                reviewer="alice",
                reason="Approved heap snapshot diff executor journal write.",
                mode="apply",
                write_result=True,
                approve_transaction_journal=True,
                expected_approval_scope="heap-snapshot-diff-executor",
                expected_transaction_id="heap-diff-txn-test",
                expected_idempotency_key="heap-diff-idem-test",
                metadata_json=json.dumps({"ticket": "HEAP-321"}),
            )

            journal_path = artifact_root / "workspace" / "heap-snapshot-diff-executor-journal.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["journal_written"])
            self.assertTrue(result["transaction_started"])
            self.assertTrue(journal_path.exists())
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["schema_version"], "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1")
            self.assertEqual(journal["transaction_id"], "heap-diff-txn-test")
            self.assertTrue(journal["journal_summary"]["journal_written"])
            self.assertFalse(journal["journal_summary"]["bounded_executor_gate_written"])
            self.assertFalse(journal["journal_summary"]["executor_invoked"])
            self.assertFalse(journal["journal_summary"]["raw_heap_loaded"])
            self.assertFalse(journal["journal_summary"]["heap_diff_computed"])
            self.assertFalse(journal["executor_input_gates"]["ready_to_execute_now"])
            self.assertTrue(journal["executor_input_gates"]["journal_written"])
            self.assertFalse(journal["executor_input_gates"]["bounded_executor_gate_written"])
            self.assertFalse(journal["executor_input_gates"]["executor_invoked"])
            self.assertFalse(journal["executor_input_gates"]["raw_heap_parsed"])
            self.assertEqual(journal["metadata"]["ticket"], "HEAP-321")
            self.assertTrue(journal["side_effect_policy"]["writes_transaction_journal"])
            self.assertTrue(journal["side_effect_policy"]["transaction_started"])
            self.assertTrue(journal["side_effect_policy"]["journal_written"])
            self.assertFalse(journal["side_effect_policy"]["bounded_executor_gate_written"])
            self.assertFalse(journal["side_effect_policy"]["executor_invoked"])
            self.assertFalse(journal["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(journal["side_effect_policy"]["raw_heap_loaded"])
            self.assertFalse(journal["side_effect_policy"]["raw_heap_parsed"])
            self.assertFalse(journal["side_effect_policy"]["raw_heap_exported"])
            self.assertFalse(journal["side_effect_policy"]["heap_diff_computed"])
            self.assertFalse(journal["side_effect_policy"]["calls_mcp"])
            self.assertFalse(journal["side_effect_policy"]["mobile_runtime_used"])

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_executor_approval_record": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-approval-record.v1",
                "status": "written",
                "approval_scope": "heap-snapshot-diff-executor",
                "approval_recorded": True,
                "approved_for_execution": True,
                "executor_input_gates": {"transaction_started": False, "journal_written": False, "executor_invoked": False},
                "next_action": "review_heap_snapshot_diff_executor_transaction_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_approval_record_ready_for_transaction_preflight", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_transaction_preflight")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_approval_record_status"], "written")
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_approval_record_approved_for_execution"])

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_transaction_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_executor_transaction_preflight": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-preflight.v1",
                "status": "ready_for_review",
                "approval_summary": {"approval_scope": "heap-snapshot-diff-executor", "approval_recorded": True, "approved_for_execution": True},
                "transaction_summary": {"transaction_id": "heap-diff-txn-test", "idempotency_key": "heap-diff-idem-test"},
                "journal_writer_contract": {"ready_for_journal_review": True, "implemented": False},
                "side_effect_policy": {"transaction_started": False, "journal_written": False, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
                "next_action": "review_heap_snapshot_diff_executor_transaction_journal_writer",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_transaction_preflight_ready_for_journal_writer", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_transaction_journal_writer")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_ready_to_write_journal"])
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_transaction_id"], "heap-diff-txn-test")
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_journal_written"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_transaction_preflight_heap_diff_computed"])

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_transaction_journal(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_diff_executor_transaction_journal": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-transaction-journal.v1",
                "status": "written",
                "journal_written": True,
                "transaction_started": True,
                "transaction_id": "heap-diff-txn-test",
                "executor_input_gates": {"bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
                "side_effect_policy": {"writes_transaction_journal": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "heap_diff_computed": False},
                "next_action": "review_heap_snapshot_diff_executor_bounded_gate",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_transaction_journal_ready_for_bounded_gate", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_bounded_gate")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_transaction_journal_status"], "written")
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_transaction_journal_written"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_transaction_journal_started"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_transaction_journal_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_transaction_journal_heap_diff_computed"])


    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_bounded_gate(self) -> None:
        payload = {
            "heap_snapshot_diff_executor_bounded_gate": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-bounded-gate.v1",
                "status": "ready_for_review",
                "journal_id": "heap-snapshot-diff-executor-transaction-journal:abc123",
                "transaction_id": "heap-diff-txn-test",
                "bounded_executor_gate_ready_for_review": True,
                "ready_to_execute_now": False,
                "future_executor_contract": {"implemented": False},
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "next_action": "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_ready_for_executor_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_raw_heap_parser_or_executor_mvp")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_bounded_gate_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_bounded_gate_ready_for_review"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_bounded_gate_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_bounded_gate_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_bounded_gate_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_bounded_gate_heap_diff_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_executor_bounded_gate(self) -> None:
        payload = {"heap_snapshot_diff_executor_bounded_gate": {"status": "blocked", "blockers": ["transaction_journal_written"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_executor_bounded_gate_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_written_heap_snapshot_diff_executor_transaction_journal")

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_executor_result(self) -> None:
        payload = {
            "heap_snapshot_diff_executor_result": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-executor-result.v1",
                "status": "executed",
                "executor_mvp": True,
                "raw_heap_loaded": True,
                "raw_heap_parsed": True,
                "raw_heap_exported": False,
                "heap_diff_computed": True,
                "complete_heap_traversal_claimed": False,
                "next_action": "review_heap_snapshot_diff_executor_result_before_followup",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_executor_result_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_executor_result_before_followup")
        self.assertEqual(result["summary"]["heap_snapshot_diff_executor_result_status"], "executed")
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_result_executor_mvp"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_result_raw_heap_parsed"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_executor_result_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_result_raw_heap_exported"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_executor_result_complete_heap_traversal_claimed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_executor_result(self) -> None:
        payload = {"heap_snapshot_diff_executor_result": {"status": "blocked", "blockers": ["raw_heap_export_not_allowed"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_executor_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_diff_executor_result_blockers")



    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_followup_checkpoint(self) -> None:
        payload = {
            "heap_snapshot_diff_followup_checkpoint": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-followup-checkpoint.v1",
                "status": "ready_for_review",
                "review_only": True,
                "checkpoint_only": True,
                "executor_result_summary": {"node_count_delta": 1},
                "analysis_plan": {"recommendations": [{"action": "plan_retained_size_analysis"}]},
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "complete_heap_traversal_claimed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_followup_checkpoint_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_followup_plan_before_retained_size_or_path_to_root_work")
        self.assertEqual(result["summary"]["heap_snapshot_diff_followup_checkpoint_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_diff_followup_checkpoint_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_followup_checkpoint_checkpoint_only"])
        self.assertEqual(result["summary"]["heap_snapshot_diff_followup_checkpoint_node_delta"], 1)
        self.assertEqual(result["summary"]["heap_snapshot_diff_followup_checkpoint_recommendation_count"], 1)
        self.assertFalse(result["summary"]["heap_snapshot_diff_followup_checkpoint_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_followup_checkpoint_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_followup_checkpoint_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_followup_checkpoint_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_followup_checkpoint(self) -> None:
        payload = {"heap_snapshot_diff_followup_checkpoint": {"status": "blocked", "blockers": ["heap_snapshot_diff_executor_result_required"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_followup_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_diff_followup_checkpoint_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_diff_selected_analysis_input_preflight(self) -> None:
        payload = {
            "heap_snapshot_diff_selected_analysis_input_preflight": {
                "schema_version": "reverse-deepagent.heap-snapshot-diff-selected-analysis-input-preflight.v1",
                "status": "ready_for_review",
                "review_only": True,
                "preflight_only": True,
                "selection_only": True,
                "source_checkpoint_summary": {"status": "ready_for_review", "transaction_id": "heap-diff-txn-1"},
                "selected_analysis_input": {"selected_action": "plan_retained_size_analysis", "candidate_count": 1},
                "future_executor_contract": {"implemented": False, "requires_raw_heap": True},
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_diff_selected_analysis_input_before_raw_heap_or_drilldown_work")
        self.assertEqual(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_preflight_only"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_selection_only"])
        self.assertEqual(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_selected_action"], "plan_retained_size_analysis")
        self.assertEqual(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_candidate_count"], 1)
        self.assertFalse(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_future_executor_implemented"])
        self.assertTrue(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_requires_raw_heap"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_diff_selected_analysis_input_preflight_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_selected_analysis_input_preflight(self) -> None:
        payload = {"heap_snapshot_diff_selected_analysis_input_preflight": {"status": "blocked", "blockers": ["heap_snapshot_diff_followup_checkpoint_required"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_selected_analysis_input_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_diff_selected_analysis_input_preflight_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_constructor_growth_drilldown(self) -> None:
        payload = {
            "heap_snapshot_constructor_growth_drilldown": {
                "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown.v1",
                "status": "ready_for_review",
                "review_only": True,
                "drilldown_only": True,
                "summary_only": True,
                "selected_action": "review_constructor_growth",
                "constructor_growth_summary": {"candidate_count": 1, "top_candidate": {"name": "LeakyThing", "delta": 1}},
                "future_analysis_contracts": {"retained_size_analysis": {"implemented": False}, "path_to_root_analysis": {"implemented": False}},
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "constructor_drilldown_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_constructor_growth_before_retained_size_or_path_to_root_preflight")
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_constructor_growth_drilldown_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_constructor_growth_drilldown_drilldown_only"])
        self.assertTrue(result["summary"]["heap_snapshot_constructor_growth_drilldown_summary_only"])
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_selected_action"], "review_constructor_growth")
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_candidate_count"], 1)
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_top_candidate"], "LeakyThing")
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_retained_size_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_path_to_root_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_constructor_drilldown_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_constructor_growth_drilldown(self) -> None:
        payload = {"heap_snapshot_constructor_growth_drilldown": {"status": "blocked", "blockers": ["heap_snapshot_constructor_growth_candidates_required"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_constructor_growth_drilldown_blockers")


    def test_review_hook_artifacts_warns_for_heap_snapshot_constructor_growth_drilldown_analysis(self) -> None:
        payload = {
            "heap_snapshot_constructor_growth_drilldown_analysis": {
                "schema_version": "reverse-deepagent.heap-snapshot-constructor-growth-drilldown-analysis.v1",
                "status": "executed",
                "constructor_drilldown_computed": True,
                "constructor_drilldown_proven": False,
                "raw_heap_loaded": False,
                "raw_heap_exported": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "constructor_drilldown_rows": [{"name": "LeakyThing", "delta": 3}],
                "next_action": "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_ready_for_retained_size_path_or_second_pass_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_constructor_growth_drilldown_analysis_before_retained_size_path_to_root_or_second_pass")
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_status"], "executed")
        self.assertEqual(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_constructor_drilldown_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_constructor_growth_drilldown_analysis_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_constructor_growth_drilldown_analysis(self) -> None:
        payload = {"heap_snapshot_constructor_growth_drilldown_analysis": {"status": "blocked", "blockers": ["approval_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_constructor_growth_drilldown_analysis_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_constructor_growth_drilldown_analysis_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_automatic_followup_plan(self) -> None:
        payload = {
            "heap_snapshot_automatic_followup_plan": {
                "schema_version": "reverse-deepagent.heap-snapshot-automatic-followup-plan.v1",
                "status": "ready_for_review",
                "review_only": True,
                "plan_only": True,
                "recommended_action_count": 2,
                "top_recommended_action": {"action": "review_combined_heap_candidate_evidence"},
                "raw_heap_loaded": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_proven": False,
                "automatic_execution_allowed": False,
                "next_action": "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_automatic_followup_plan_ready_for_proof_or_second_pass_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_automatic_followup_plan_before_proof_or_second_pass")
        self.assertEqual(result["summary"]["heap_snapshot_automatic_followup_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_automatic_followup_plan_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_automatic_followup_plan_plan_only"])
        self.assertEqual(result["summary"]["heap_snapshot_automatic_followup_plan_recommended_action_count"], 2)
        self.assertEqual(result["summary"]["heap_snapshot_automatic_followup_plan_top_action"], "review_combined_heap_candidate_evidence")
        self.assertFalse(result["summary"]["heap_snapshot_automatic_followup_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_automatic_followup_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_automatic_followup_plan_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_automatic_followup_plan_path_to_root_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_automatic_followup_plan_automatic_execution_allowed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_automatic_followup_plan(self) -> None:
        payload = {"heap_snapshot_automatic_followup_plan": {"status": "blocked", "blockers": ["heap_snapshot_analysis_result_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_automatic_followup_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_automatic_followup_plan_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_proof_plan(self) -> None:
        payload = {
            "heap_snapshot_retained_size_proof_plan": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-proof-plan.v1",
                "status": "ready_for_review",
                "review_only": True,
                "plan_only": True,
                "proof_plan_only": True,
                "candidate_count": 1,
                "proof_requirements": {"requires_raw_heap": True},
                "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
                "raw_heap_loaded": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "automatic_execution_allowed": False,
                "next_action": "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_proof_plan_ready_for_raw_heap_ingestion_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_proof_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_proof_plan_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_proof_plan_plan_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_proof_plan_proof_plan_only"])
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_proof_plan_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_proof_plan_requires_raw_heap"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_proof_plan_automatic_execution_allowed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_proof_plan(self) -> None:
        payload = {"heap_snapshot_retained_size_proof_plan": {"status": "blocked", "blockers": ["heap_snapshot_retained_size_analysis_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_proof_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_size_proof_plan_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_path_to_root_proof_plan(self) -> None:
        payload = {
            "heap_snapshot_path_to_root_proof_plan": {
                "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-proof-plan.v1",
                "status": "ready_for_review",
                "review_only": True,
                "plan_only": True,
                "proof_plan_only": True,
                "candidate_count": 1,
                "proof_requirements": {"requires_raw_heap": True},
                "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
                "raw_heap_loaded": False,
                "heap_diff_computed": False,
                "path_to_root_proven": False,
                "automatic_execution_allowed": False,
                "next_action": "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_path_to_root_proof_plan_ready_for_raw_heap_ingestion_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_path_to_root_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result["summary"]["heap_snapshot_path_to_root_proof_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_proof_plan_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_proof_plan_plan_only"])
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_proof_plan_proof_plan_only"])
        self.assertEqual(result["summary"]["heap_snapshot_path_to_root_proof_plan_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_proof_plan_requires_raw_heap"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_path_to_root_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_proof_plan_automatic_execution_allowed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_path_to_root_proof_plan(self) -> None:
        payload = {"heap_snapshot_path_to_root_proof_plan": {"status": "blocked", "blockers": ["heap_snapshot_path_to_root_analysis_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_path_to_root_proof_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_path_to_root_proof_plan_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_raw_heap_constructor_drilldown_proof_plan(self) -> None:
        payload = {
            "heap_snapshot_raw_heap_constructor_drilldown_proof_plan": {
                "schema_version": "reverse-deepagent.heap-snapshot-raw-heap-constructor-drilldown-proof-plan.v1",
                "status": "ready_for_review",
                "review_only": True,
                "plan_only": True,
                "proof_plan_only": True,
                "candidate_count": 1,
                "proof_requirements": {"requires_raw_heap": True, "requires_constructor_reachability_graph": True},
                "future_executor_contract": {"implemented": False, "ready_to_execute_now": False},
                "raw_heap_loaded": False,
                "heap_diff_computed": False,
                "constructor_drilldown_proven": False,
                "automatic_execution_allowed": False,
                "next_action": "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_for_raw_heap_ingestion_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_before_raw_heap_ingestion_or_executor")
        self.assertEqual(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_plan_only"])
        self.assertTrue(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_proof_plan_only"])
        self.assertEqual(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_raw_heap"])
        self.assertTrue(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_requires_constructor_reachability_graph"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_constructor_drilldown_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_raw_heap_constructor_drilldown_proof_plan_automatic_execution_allowed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_raw_heap_constructor_drilldown_proof_plan(self) -> None:
        payload = {"heap_snapshot_raw_heap_constructor_drilldown_proof_plan": {"status": "blocked", "blockers": ["heap_snapshot_constructor_growth_drilldown_analysis_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_raw_heap_constructor_drilldown_proof_plan_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_path_preflight(self) -> None:
        payload = {
            "heap_snapshot_retained_path_preflight": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-path-preflight.v1",
                "status": "ready_for_review",
                "review_only": True,
                "preflight_only": True,
                "handoff_only": True,
                "requested_analysis": "retained-size-and-path-to-root",
                "candidate_count": 1,
                "candidate_inputs": [{"name": "LeakyThing", "delta": 1}],
                "raw_heap_requirements": {"requires_raw_heap": True},
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_retained_path_executor_inputs",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_path_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_path_executor_inputs")
        self.assertEqual(result["summary"]["heap_snapshot_retained_path_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_path_preflight_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_path_preflight_preflight_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_path_preflight_handoff_only"])
        self.assertEqual(result["summary"]["heap_snapshot_retained_path_preflight_candidate_count"], 1)
        self.assertEqual(result["summary"]["heap_snapshot_retained_path_preflight_top_candidate"], "LeakyThing")
        self.assertTrue(result["summary"]["heap_snapshot_retained_path_preflight_requires_raw_heap"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_path_preflight_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_path_preflight_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_path_preflight_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_path_preflight_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_path_preflight(self) -> None:
        payload = {"heap_snapshot_retained_path_preflight": {"status": "blocked", "blockers": ["heap_snapshot_retained_path_candidates_required"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_path_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_path_preflight_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_input_review(self) -> None:
        payload = {
            "heap_snapshot_retained_size_input_review": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-input-review.v1",
                "status": "ready_for_review",
                "review_only": True,
                "input_review_only": True,
                "approval_gate_only": True,
                "candidate_count": 1,
                "candidate_inputs": [{"name": "LeakyThing", "delta": 1}],
                "raw_heap_requirements": {"requires_raw_heap": True},
                "executor_input_contract": {"implemented": False, "executor_name": "execute_heap_snapshot_retained_size_analysis"},
                "approval_gate": {"approval_required": True, "ready_to_execute_now": False},
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_retained_size_approval_plan",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_input_review_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_approval_plan")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_input_review_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_input_review_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_input_review_input_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_input_review_approval_gate_only"])
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_input_review_candidate_count"], 1)
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_input_review_top_candidate"], "LeakyThing")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_input_review_requires_raw_heap"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_executor_implemented"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_input_review_approval_required"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_input_review_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_input_review(self) -> None:
        payload = {"heap_snapshot_retained_size_input_review": {"status": "blocked", "blockers": ["heap_snapshot_retained_size_candidate_inputs_required"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_input_review_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_size_input_review_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_approval_plan(self) -> None:
        payload = {
            "heap_snapshot_retained_size_approval_plan": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-plan.v1",
                "status": "ready_for_review",
                "review_only": True,
                "approval_plan_only": True,
                "transaction_plan_only": True,
                "candidate_count": 1,
                "candidate_inputs": [{"name": "LeakyThing", "delta": 1}],
                "executor_input_contract": {"implemented": False, "ready_to_execute_now": False},
                "approval_plan": {"approval_required": True, "approval_recorded": False},
                "transaction_plan": {"transaction_started": False, "journal_written": False},
                "approval_recorded": False,
                "transaction_started": False,
                "journal_written_now": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "record_heap_snapshot_retained_size_approval",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_approval_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "record_heap_snapshot_retained_size_approval")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_approval_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_approval_plan_review_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_approval_plan_approval_plan_only"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_approval_plan_transaction_plan_only"])
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_approval_plan_candidate_count"], 1)
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_approval_plan_top_candidate"], "LeakyThing")
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_approval_recorded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_transaction_started"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_journal_written_now"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_heap_diff_computed"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_plan_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_approval_plan(self) -> None:
        payload = {"heap_snapshot_retained_size_approval_plan": {"status": "blocked", "blockers": ["heap_snapshot_retained_size_input_review_not_ready"]}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_approval_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_size_approval_plan_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "heap_snapshot_retained_size_approval_record": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-approval-record.v1",
                "status": "written",
                "approval_recorded": True,
                "approved_for_execution": True,
                "candidate_digest": "retained-size-candidate-digest-test",
                "transaction_plan_id": "retained-size-approval-plan-test",
                "executor_input_gates": {
                    "transaction_started": False,
                    "journal_written": False,
                    "bounded_executor_gate_written": False,
                    "executor_invoked": False,
                    "raw_heap_loaded": False,
                    "raw_heap_parsed": False,
                    "raw_heap_exported": False,
                    "heap_diff_computed": False,
                    "retained_size_proven": False,
                    "path_to_root_computed": False,
                },
                "next_action": "review_heap_snapshot_retained_size_transaction_preflight",
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_approval_record_ready_for_transaction_preflight", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_transaction_preflight")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_approval_record_status"], "written")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_approval_record_approval_recorded"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_approval_record_approved_for_execution"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_transaction_started"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_journal_written"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_raw_heap_loaded"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_approval_record_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_approval_record(self) -> None:
        payload = {"heap_snapshot_retained_size_approval_record": {"status": "blocked", "reason": "approval_plan_missing"}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_approval_record_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_heap_snapshot_retained_size_approval_plan_descriptor")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_transaction_preflight(self) -> None:
        payload = {
            "heap_snapshot_retained_size_transaction_preflight": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-preflight.v1",
                "status": "ready_for_review",
                "approval_summary": {"approval_plan_id": "retained-size-approval-plan-test", "approval_recorded": True, "approved_for_execution": True},
                "transaction_summary": {"transaction_plan_id": "retained-size-approval-plan-test", "transaction_started": False, "journal_written": False},
                "candidate_summary": {"candidate_digest": "retained-size-candidate-digest-test"},
                "journal_writer_contract": {"ready_for_journal_review": True, "implemented": False},
                "transaction_started": False,
                "journal_written": False,
                "bounded_executor_gate_written": False,
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "heap_diff_computed": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_retained_size_transaction_journal_writer",
            }
        }
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_ready_for_journal_writer", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_transaction_journal_writer")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_transaction_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_transaction_preflight_ready_to_write_journal"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_preflight_transaction_started"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_preflight_journal_written"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_preflight_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_preflight_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_preflight_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_transaction_preflight(self) -> None:
        payload = {"heap_snapshot_retained_size_transaction_preflight": {"status": "blocked", "reason": "approval_record_missing"}}
        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_transaction_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_size_transaction_preflight_blockers")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_transaction_journal(self) -> None:
        payload = {
            "heap_snapshot_retained_size_transaction_journal": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-transaction-journal.v1",
                "status": "written",
                "journal_written": True,
                "transaction_started": True,
                "transaction_plan_id": "retained-size-approval-plan-test",
                "candidate_digest": "retained-size-candidate-digest-test",
                "executor_input_gates": {"bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "retained_size_proven": False, "path_to_root_computed": False},
                "side_effect_policy": {"writes_transaction_journal": True, "bounded_executor_gate_written": False, "executor_invoked": False, "raw_heap_loaded": False, "raw_heap_parsed": False, "raw_heap_exported": False, "retained_size_proven": False, "path_to_root_computed": False},
                "next_action": "review_heap_snapshot_retained_size_bounded_gate",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_transaction_journal_ready_for_bounded_gate", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_bounded_gate")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_transaction_journal_status"], "written")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_transaction_journal_written"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_transaction_journal_started"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_journal_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_journal_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_transaction_journal_path_to_root_computed"])



    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_bounded_gate(self) -> None:
        payload = {
            "heap_snapshot_retained_size_bounded_gate": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-bounded-gate.v1",
                "status": "ready_for_review",
                "journal_id": "retained-size-journal-test",
                "transaction_plan_id": "retained-size-approval-plan-test",
                "approval_plan_id": "retained-size-approval-plan-test",
                "candidate_digest": "retained-size-candidate-digest-test",
                "bounded_executor_gate_ready_for_review": True,
                "ready_to_execute_now": False,
                "future_executor_contract": {"implemented": False, "executor_name": "execute_heap_snapshot_retained_size_analysis", "result_artifact": "workspace/heap-snapshot-retained-size-analysis.json"},
                "executor_invoked": False,
                "raw_heap_loaded": False,
                "raw_heap_parsed": False,
                "raw_heap_exported": False,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "next_action": "review_heap_snapshot_retained_size_executor_mvp",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_bounded_gate_ready_for_executor_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_executor_mvp")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_bounded_gate_status"], "ready_for_review")
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_bounded_gate_ready_for_review"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_bounded_gate_ready_to_execute_now"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_bounded_gate_future_executor_implemented"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_bounded_gate_executor_invoked"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_bounded_gate_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_bounded_gate_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_bounded_gate(self) -> None:
        payload = {"heap_snapshot_retained_size_bounded_gate": {"status": "blocked", "blockers": ["transaction_journal_written"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_bounded_gate_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_written_heap_snapshot_retained_size_transaction_journal")

    def test_review_hook_artifacts_warns_for_heap_snapshot_retained_size_analysis(self) -> None:
        payload = {
            "heap_snapshot_retained_size_analysis": {
                "schema_version": "reverse-deepagent.heap-snapshot-retained-size-analysis.v1",
                "status": "executed",
                "retained_size_estimated": True,
                "retained_size_proven": False,
                "path_to_root_computed": False,
                "raw_heap_loaded": True,
                "raw_heap_parsed": True,
                "raw_heap_exported": False,
                "raw_strings_exported": False,
                "candidate_estimates": [{"name": "LeakyThing", "retained_size_estimate": 64}],
                "next_action": "review_heap_snapshot_retained_size_analysis_before_path_to_root_or_second_pass",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_retained_size_analysis_ready_for_path_to_root_or_second_pass_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_retained_size_analysis_before_path_to_root_or_second_pass")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_analysis_status"], "executed")
        self.assertEqual(result["summary"]["heap_snapshot_retained_size_analysis_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_analysis_raw_heap_loaded"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_analysis_raw_heap_parsed"])
        self.assertTrue(result["summary"]["heap_snapshot_retained_size_analysis_retained_size_estimated"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_analysis_retained_size_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_retained_size_analysis_path_to_root_computed"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_retained_size_analysis(self) -> None:
        payload = {"heap_snapshot_retained_size_analysis": {"status": "blocked", "blockers": ["heap_snapshot_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_retained_size_analysis_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_retained_size_analysis_blockers")


    def test_review_hook_artifacts_warns_for_heap_snapshot_path_to_root_analysis(self) -> None:
        payload = {
            "heap_snapshot_path_to_root_analysis": {
                "schema_version": "reverse-deepagent.heap-snapshot-path-to-root-analysis.v1",
                "status": "executed",
                "path_to_root_estimated": True,
                "path_to_root_proven": False,
                "retained_size_proven": False,
                "raw_heap_loaded": True,
                "raw_heap_parsed": True,
                "raw_heap_exported": False,
                "raw_strings_exported": False,
                "candidate_paths": [{"candidate_name": "LeakyThing", "path_depth": 2}],
                "next_action": "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown",
            }
        }

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("heap_snapshot_path_to_root_analysis_ready_for_second_pass_or_constructor_drilldown_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_heap_snapshot_path_to_root_analysis_before_second_pass_or_constructor_drilldown")
        self.assertEqual(result["summary"]["heap_snapshot_path_to_root_analysis_status"], "executed")
        self.assertEqual(result["summary"]["heap_snapshot_path_to_root_analysis_candidate_count"], 1)
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_analysis_raw_heap_loaded"])
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_analysis_raw_heap_parsed"])
        self.assertTrue(result["summary"]["heap_snapshot_path_to_root_analysis_path_to_root_estimated"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_analysis_path_to_root_proven"])
        self.assertFalse(result["summary"]["heap_snapshot_path_to_root_analysis_retained_size_proven"])

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_path_to_root_analysis(self) -> None:
        payload = {"heap_snapshot_path_to_root_analysis": {"status": "blocked", "blockers": ["heap_snapshot_required"]}}

        result = make_review_hook_artifacts_tool()(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_path_to_root_analysis_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_heap_snapshot_path_to_root_analysis_blockers")

    def test_review_hook_artifacts_blocks_failed_heap_snapshot_diff_executor_approval_record(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {"heap_snapshot_diff_executor_approval_record": {"status": "blocked", "reason": "approval_plan_missing"}}

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("heap_snapshot_diff_executor_approval_record_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "provide_ready_heap_snapshot_diff_executor_approval_plan_descriptor")

    def test_review_hook_artifacts_warns_for_closure_wrapper_replacement_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_replacement_plan": {
                "status": "ready_for_review",
                "plan": {
                    "status": "ready_for_review",
                    "next_action": "review_closure_wrapper_replacement_plan_before_execution",
                    "wrapper_installed": False,
                    "runtime_mutated": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_replacement_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_replacement_plan_before_execution")
        self.assertEqual(result["summary"]["closure_wrapper_replacement_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["closure_wrapper_replacement_plan_next_action"], "review_closure_wrapper_replacement_plan_before_execution")
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_replacement_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["hook_installed"])
        self.assertFalse(result["side_effect_policy"]["javascript_evaluated"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_plan_only_closure_wrapper_strategy_descriptor(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_replacement_plan": {
                "status": "ready_for_review",
                "plan": {
                    "status": "ready_for_review",
                    "next_action": "review_closure_wrapper_replacement_plan_before_execution",
                    "wrapper_strategy": "arg-preview",
                    "wrapper_strategy_descriptor": {
                        "schema_version": "reverse-deepagent.closure-wrapper-strategy.v1",
                        "strategy": "arg-preview",
                        "supported_for_planning": True,
                        "supported_for_install": False,
                        "strategy_plan_only": True,
                        "install_blockers": ["wrapper_strategy_plan_only"],
                    },
                    "wrapper_installed": False,
                    "runtime_mutated": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_strategy_descriptor_plan_only_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_strategy_descriptor_before_execution")
        self.assertEqual(result["summary"]["closure_wrapper_strategy"], "arg-preview")
        self.assertFalse(result["summary"]["closure_wrapper_strategy_supported_for_install"])
        self.assertTrue(result["summary"]["closure_wrapper_strategy_plan_only"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_strategy"], "arg-preview")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_assignment_safety(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_replacement_plan": {
                "status": "ready_for_review",
                "plan": {"status": "ready_for_review", "wrapper_installed": False},
            },
            "closure_wrapper_assignment_safety": {
                "status": "ready_for_review",
                "assignment_safety": {
                    "status": "ready_for_review",
                    "assignment_safety_proven": True,
                    "next_action": "approve_reviewed_closure_wrapper_replacement_execution_with_assignment_safety_proof",
                },
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertNotIn("closure_wrapper_replacement_plan_requires_review", result["warnings"])
        self.assertIn("closure_wrapper_assignment_safety_requires_execution_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_reviewed_closure_wrapper_replacement_execution_with_assignment_safety_proof")
        self.assertEqual(result["summary"]["closure_wrapper_assignment_safety_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_assignment_safety_proven"])
        self.assertTrue(result["review_required_items"][0]["closure_wrapper_assignment_safety_proven"])

    def test_review_hook_artifacts_blocks_failed_closure_wrapper_assignment_safety(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_assignment_safety": {
                "status": "blocked",
                "assignment_safety": {"assignment_safety_proven": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_assignment_safety_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_assignment_safety_blockers")

    def test_review_hook_artifacts_warns_for_closure_wrapper_runtime_mutability_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_runtime_mutability_preflight": {
                "status": "ready_for_review",
                "preflight": {
                    "status": "ready_for_review",
                    "runtime_mutability_probe_ready_for_review": True,
                    "next_action": "review_closure_wrapper_runtime_mutability_probe_before_execution",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_runtime_mutability_preflight_requires_probe_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_runtime_mutability_probe_before_execution")
        self.assertEqual(result["summary"]["closure_wrapper_runtime_mutability_preflight_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_runtime_mutability_probe_ready_for_review"])
        self.assertTrue(result["review_required_items"][0]["closure_wrapper_runtime_mutability_probe_ready_for_review"])

    def test_review_hook_artifacts_blocks_failed_closure_wrapper_runtime_mutability_preflight(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_runtime_mutability_preflight": {
                "status": "blocked",
                "preflight": {"runtime_mutability_probe_ready_for_review": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_runtime_mutability_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_runtime_mutability_preflight_blockers")

    def test_review_hook_artifacts_warns_for_closure_wrapper_runtime_mutability_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_runtime_mutability_result": {
                "status": "proven",
                "result": {
                    "status": "proven",
                    "runtime_mutability_proven": True,
                    "original_restored": True,
                    "next_action": "review_runtime_mutability_result_then_optionally_execute_closure_wrapper_replacement",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_runtime_mutability_result_requires_replacement_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_runtime_mutability_result_then_optionally_execute_closure_wrapper_replacement")
        self.assertEqual(result["summary"]["closure_wrapper_runtime_mutability_result_status"], "proven")
        self.assertTrue(result["summary"]["closure_wrapper_runtime_mutability_result_proven"])
        self.assertTrue(result["summary"]["closure_wrapper_runtime_mutability_result_original_restored"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_runtime_mutability_result_status"], "proven")

    def test_review_hook_artifacts_blocks_failed_closure_wrapper_runtime_mutability_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_runtime_mutability_result": {
                "status": "failed",
                "result": {"runtime_mutability_proven": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_runtime_mutability_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_runtime_mutability_result_blockers")

    def test_review_hook_artifacts_warns_for_closure_wrapper_replacement_execution_restore(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_replacement_execution": {
                "status": "applied",
                "execution": {
                    "status": "applied",
                    "next_action": "invoke_target_flow_and_review_closure_wrapper_events_or_restore",
                    "wrapper_installed": True,
                    "runtime_mutated": True,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_replacement_execution_restore_review_required", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_restore_plan_or_invoke_target_flow")
        self.assertEqual(result["summary"]["closure_wrapper_replacement_execution_status"], "applied")
        self.assertTrue(result["summary"]["closure_wrapper_replacement_execution_wrapper_installed"])
        self.assertTrue(result["summary"]["closure_wrapper_replacement_execution_runtime_mutated"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_replacement_execution_status"], "applied")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_restore_execution_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_restore_execution": {
                "status": "restored",
                "execution": {
                    "status": "restored",
                    "next_action": "review_closure_wrapper_restore_result_or_continue_target_flow",
                    "wrapper_restored": True,
                    "runtime_mutated": True,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_restore_execution_result_review_required", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_restore_execution_result_or_continue_target_flow")
        self.assertEqual(result["summary"]["closure_wrapper_restore_execution_status"], "restored")
        self.assertTrue(result["summary"]["closure_wrapper_restore_execution_wrapper_restored"])
        self.assertTrue(result["summary"]["closure_wrapper_restore_execution_runtime_mutated"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_restore_execution_status"], "restored")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_empty_closure_wrapper_events(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_events": {
                "status": "success",
                "event_count": 0,
                "events": [],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_events_empty", result["warnings"])
        self.assertEqual(result["next_action"], "invoke_target_flow_then_harvest_closure_wrapper_events")
        self.assertEqual(result["summary"]["closure_wrapper_event_count"], 0)
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_event_count"], 0)
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_readiness(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_readiness": {
                "status": "ready_for_review",
                "readiness": {
                    "status": "ready_for_review",
                    "continuation_ready": True,
                    "automatic_wrapper_continuation": False,
                    "next_action": "review_wrapper_continuation_readiness",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_wrapper_continuation_readiness")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_readiness_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_ready"])
        self.assertFalse(result["summary"]["closure_wrapper_continuation_automatic_wrapper_continuation"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_readiness_status"], "ready_for_review")
        self.assertTrue(result["review_required_items"][0]["closure_wrapper_continuation_ready"])
        self.assertFalse(result["review_required_items"][0]["closure_wrapper_continuation_automatic_wrapper_continuation"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_readiness(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_readiness": {
                "status": "blocked",
                "readiness": {
                    "status": "blocked",
                    "blockers": ["closure_wrapper_replacement_execution_required"],
                    "continuation_ready": False,
                    "automatic_wrapper_continuation": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_readiness_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_readiness_status"], "blocked")
        self.assertFalse(result["summary"]["closure_wrapper_continuation_ready"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_execution_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_execution_plan": {
                "status": "ready_for_review",
                "plan": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "next_action": "review_closure_wrapper_continuation_execution_plan",
                    "execution_strategy": {
                        "automatic_wrapper_continuation_supported": False,
                        "automatic_multi_step_loop_supported": False,
                    },
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_execution_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_continuation_execution_plan")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_execution_plan_ready"])
        self.assertFalse(result["summary"]["closure_wrapper_continuation_execution_plan_automatic_wrapper_continuation"])
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_plan_next_action"], "review_closure_wrapper_continuation_execution_plan")
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_execution_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_execution_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_execution_plan": {
                "status": "blocked",
                "plan": {
                    "status": "blocked",
                    "blockers": ["paused_session_execution_path_required"],
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_execution_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_execution_plan_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_plan_status"], "blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_execution_review(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_execution": {
                "status": "review_required",
                "execution": {
                    "status": "review_required",
                    "next_action": "approve_closure_wrapper_continuation_iteration",
                    "wrapper_continuation_iteration_executed": False,
                    "paused_event_captured": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_closure_wrapper_continuation_iteration")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_status"], "review_required")
        self.assertFalse(result["summary"]["closure_wrapper_continuation_execution_iteration_executed"])
        self.assertFalse(result["summary"]["closure_wrapper_continuation_execution_paused_event_captured"])
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_next_action"], "approve_closure_wrapper_continuation_iteration")
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_execution_status"], "review_required")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_executed_closure_wrapper_continuation_followup(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_execution": {
                "status": "executed",
                "execution": {
                    "status": "executed",
                    "next_action": "harvest_wrapper_events_and_checkpoint_continuation",
                    "wrapper_continuation_iteration_executed": True,
                    "paused_event_captured": True,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_execution_requires_event_harvest_and_checkpoint", result["warnings"])
        self.assertEqual(result["next_action"], "harvest_wrapper_events_and_checkpoint_continuation")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_status"], "executed")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_execution_iteration_executed"])
        self.assertTrue(result["summary"]["closure_wrapper_continuation_execution_paused_event_captured"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_execution": {
                "status": "blocked",
                "execution": {
                    "status": "blocked",
                    "blockers": ["multi_step_workflow_required"],
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_execution_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_execution_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_execution_status"], "blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_checkpoint_review(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_checkpoint": {
                "status": "ready_for_review",
                "checkpoint": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "post_execution_event_count": 1,
                    "next_action": "review_next_closure_wrapper_continuation_iteration",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_checkpoint_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_continuation_checkpoint")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_checkpoint_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_checkpoint_ready"])
        self.assertEqual(result["summary"]["closure_wrapper_continuation_checkpoint_event_count"], 1)
        self.assertEqual(result["summary"]["closure_wrapper_continuation_checkpoint_next_action"], "review_next_closure_wrapper_continuation_iteration")
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_checkpoint_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_checkpoint": {
                "status": "blocked",
                "checkpoint": {
                    "status": "blocked",
                    "blockers": ["closure_wrapper_events_required"],
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_checkpoint_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_checkpoint_status"], "blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_next_iteration_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_next_iteration_plan": {
                "status": "ready_for_review",
                "plan": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "next_iteration_step_index": 2,
                    "next_iteration_method": "Debugger.stepOver",
                    "next_action": "recover_live_callframe_for_next_wrapper_iteration",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_closure_wrapper_continuation_next_iteration_plan")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_plan_status"], "ready_for_review")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_next_iteration_plan_ready"])
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_plan_step_index"], 2)
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_plan_method"], "Debugger.stepOver")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_plan_next_action"], "recover_live_callframe_for_next_wrapper_iteration")
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_next_iteration_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_next_iteration_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_next_iteration_plan": {
                "status": "blocked",
                "plan": {
                    "status": "blocked",
                    "blockers": ["closure_wrapper_continuation_checkpoint_required"],
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_next_iteration_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_next_iteration_plan_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_plan_status"], "blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_closure_wrapper_continuation_next_iteration_execution_review(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_next_iteration_execution": {
                "status": "review_required",
                "execution": {
                    "status": "review_required",
                    "wrapper_next_iteration_executed": False,
                    "paused_event_captured": False,
                    "next_action": "approve_closure_wrapper_next_iteration_execution",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_closure_wrapper_next_iteration_execution")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_execution_status"], "review_required")
        self.assertFalse(result["summary"]["closure_wrapper_continuation_next_iteration_execution_executed"])
        self.assertFalse(result["summary"]["closure_wrapper_continuation_next_iteration_execution_paused_event_captured"])
        self.assertEqual(result["review_required_items"][0]["closure_wrapper_continuation_next_iteration_execution_status"], "review_required")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_executed_closure_wrapper_next_iteration_followup(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_next_iteration_execution": {
                "status": "executed",
                "execution": {
                    "status": "executed",
                    "wrapper_next_iteration_executed": True,
                    "paused_event_captured": True,
                    "next_action": "harvest_wrapper_events_and_checkpoint_next_iteration",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_requires_event_harvest_and_checkpoint", result["warnings"])
        self.assertEqual(result["next_action"], "harvest_wrapper_events_and_checkpoint_next_iteration")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_execution_status"], "executed")
        self.assertTrue(result["summary"]["closure_wrapper_continuation_next_iteration_execution_executed"])
        self.assertTrue(result["summary"]["closure_wrapper_continuation_next_iteration_execution_paused_event_captured"])

    def test_review_hook_artifacts_blocks_closure_wrapper_continuation_next_iteration_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "closure_wrapper_continuation_next_iteration_execution": {
                "status": "blocked",
                "execution": {
                    "status": "blocked",
                    "blockers": ["live_callframe_recovery_required"],
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("closure_wrapper_continuation_next_iteration_execution_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_closure_wrapper_continuation_next_iteration_execution_blockers")
        self.assertEqual(result["summary"]["closure_wrapper_continuation_next_iteration_execution_status"], "blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["runtime_mutated"])

    def test_review_hook_artifacts_warns_for_async_chunk_traversal_graph(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_traversal_graph": {
                "status": "ready_for_review",
                "graph": {
                    "status": "ready_for_review",
                    "queue_count": 1,
                    "loaded_chunk_count": 0,
                    "next_action": "review_async_chunk_traversal_graph_queue",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_traversal_graph_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_traversal_graph_queue")
        self.assertEqual(result["summary"]["async_chunk_traversal_graph_status"], "ready_for_review")
        self.assertEqual(result["summary"]["async_chunk_traversal_graph_queue_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_traversal_graph_loaded_chunk_count"], 0)
        self.assertEqual(result["review_required_items"][0]["async_chunk_traversal_graph_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_traversal_workflow_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_traversal_workflow_plan": {
                "status": "ready_for_review",
                "workflow_plan": {
                    "status": "ready_for_review",
                    "planned_step_count": 1,
                    "next_action": "review_async_chunk_traversal_workflow_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_traversal_workflow_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_traversal_workflow_plan")
        self.assertEqual(result["summary"]["async_chunk_traversal_workflow_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["async_chunk_traversal_workflow_planned_step_count"], 1)
        self.assertEqual(result["review_required_items"][0]["async_chunk_traversal_workflow_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_traversal_workflow_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_traversal_workflow_execution": {
                "status": "ready_for_review",
                "execution": {
                    "status": "ready_for_review",
                    "stages": [{"stage": "select_async_chunk_traversal_workflow_step"}],
                    "next_action": "review_async_chunk_traversal_workflow_execution_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_traversal_workflow_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_traversal_workflow_execution_plan")
        self.assertEqual(result["summary"]["async_chunk_traversal_workflow_execution_status"], "ready_for_review")
        self.assertEqual(result["summary"]["async_chunk_traversal_workflow_execution_stage_count"], 1)
        self.assertEqual(result["review_required_items"][0]["async_chunk_traversal_workflow_execution_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_traversal_loop_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_traversal_loop_plan": {
                "status": "ready_for_review",
                "loop_plan": {
                    "status": "ready_for_review",
                    "planned_iteration_count": 1,
                    "next_action": "review_async_chunk_traversal_loop_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_traversal_loop_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_traversal_loop_plan")
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_plan_iteration_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_plan_next_action"], "review_async_chunk_traversal_loop_plan")
        self.assertEqual(result["review_required_items"][0]["async_chunk_traversal_loop_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_traversal_loop_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_traversal_loop_execution": {
                "status": "ready_for_review",
                "execution": {
                    "status": "ready_for_review",
                    "stages": [{"stage": "select_async_chunk_traversal_loop_iteration"}],
                    "next_action": "review_async_chunk_traversal_loop_execution_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_traversal_loop_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_traversal_loop_execution_plan")
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_execution_status"], "ready_for_review")
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_traversal_loop_execution_next_action"], "review_async_chunk_traversal_loop_execution_plan")
        self.assertEqual(result["review_required_items"][0]["async_chunk_traversal_loop_execution_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_traversal_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_plan": {
                "status": "planned",
                "plan": {
                    "status": "ready_for_review",
                    "candidate_count": 1,
                    "ready_for_review_count": 1,
                    "blocked_execution_count": 1,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_plan")
        self.assertEqual(result["summary"]["custom_loader_traversal_plan_status"], "planned")
        self.assertEqual(result["summary"]["custom_loader_traversal_candidate_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_traversal_ready_for_review_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_traversal_blocked_execution_count"], 1)
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_traversal_graph(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_graph": {
                "status": "ready_for_review",
                "graph": {
                    "status": "ready_for_review",
                    "queue_count": 1,
                    "depth_blocked_count": 0,
                    "next_action": "review_custom_loader_traversal_graph_queue",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_graph_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_graph_queue")
        self.assertEqual(result["summary"]["custom_loader_traversal_graph_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_traversal_graph_queue_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_traversal_graph_depth_blocked_count"], 0)
        self.assertEqual(result["review_required_items"][0]["custom_loader_traversal_graph_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])


    def test_review_hook_artifacts_warns_for_custom_loader_traversal_workflow_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_workflow_plan": {
                "status": "ready_for_review",
                "workflow_plan": {
                    "status": "ready_for_review",
                    "planned_step_count": 1,
                    "next_action": "review_custom_loader_traversal_workflow_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_workflow_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_workflow_plan")
        self.assertEqual(result["summary"]["custom_loader_traversal_workflow_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_traversal_workflow_planned_step_count"], 1)
        self.assertEqual(result["review_required_items"][0]["custom_loader_traversal_workflow_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])


    def test_review_hook_artifacts_warns_for_custom_loader_traversal_workflow_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_workflow_execution": {
                "status": "ready_for_review",
                "execution": {
                    "status": "ready_for_review",
                    "stage_count": 3,
                    "stages": [
                        {"stage": "select_traversal_workflow_step", "status": "selected"},
                        {"stage": "plan_continuation_workflow", "status": "pending"},
                        {"stage": "stop_before_recursive_traversal", "status": "stopped"},
                    ],
                    "next_action": "review_custom_loader_traversal_workflow_execution_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_workflow_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_workflow_execution_plan")
        self.assertEqual(result["summary"]["custom_loader_traversal_workflow_execution_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_traversal_workflow_execution_stage_count"], 3)
        self.assertEqual(result["summary"]["custom_loader_traversal_workflow_execution_next_action"], "review_custom_loader_traversal_workflow_execution_plan")
        self.assertEqual(result["review_required_items"][0]["custom_loader_traversal_workflow_execution_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])


    def test_review_hook_artifacts_warns_for_custom_loader_traversal_loop_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_loop_plan": {
                "status": "ready_for_review",
                "loop_plan": {
                    "status": "ready_for_review",
                    "planned_iteration_count": 1,
                    "next_action": "review_custom_loader_traversal_loop_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_loop_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_loop_plan")
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_plan_iteration_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_plan_next_action"], "review_custom_loader_traversal_loop_plan")
        self.assertEqual(result["review_required_items"][0]["custom_loader_traversal_loop_plan_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_traversal_loop_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_loop_execution": {
                "status": "ready_for_review",
                "execution": {
                    "status": "ready_for_review",
                    "stages": [{"stage": "select_custom_loader_traversal_loop_iteration"}],
                    "next_action": "review_custom_loader_traversal_loop_execution_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_traversal_loop_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_traversal_loop_execution_plan")
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_execution_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_traversal_loop_execution_next_action"], "review_custom_loader_traversal_loop_execution_plan")
        self.assertEqual(result["review_required_items"][0]["custom_loader_traversal_loop_execution_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_recursive_traversal_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_recursive_traversal_plan": {
                "status": "ready_for_next_loop_review",
                "recursive_plan": {
                    "status": "ready_for_next_loop_review",
                    "next_action": "review_next_async_chunk_traversal_loop_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_recursive_traversal_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_recursive_traversal_plan")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_plan_status"], "ready_for_next_loop_review")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_plan_next_action"], "review_next_async_chunk_traversal_loop_plan")
        self.assertEqual(result["review_required_items"][0]["async_chunk_recursive_traversal_plan_status"], "ready_for_next_loop_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_recursive_traversal_followup(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_recursive_traversal_followup": {
                "status": "next_loop_plan_ready",
                "followup": {
                    "status": "next_loop_plan_ready",
                    "stages": [{"stage": "plan_next_async_chunk_traversal_loop"}],
                    "next_action": "review_next_async_chunk_traversal_loop_plan_before_execution",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_recursive_traversal_followup_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_recursive_traversal_followup")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_followup_status"], "next_loop_plan_ready")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_followup_stage_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_followup_next_action"], "review_next_async_chunk_traversal_loop_plan_before_execution")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_async_chunk_recursive_traversal_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_recursive_traversal_execution": {
                "status": "next_loop_module_diff_ready",
                "execution": {
                    "status": "next_loop_module_diff_ready",
                    "stages": [{"stage": "execute_next_bounded_async_chunk_loop"}],
                    "next_action": "plan_next_async_chunk_recursive_traversal_checkpoint",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_recursive_traversal_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_recursive_traversal_execution")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_execution_status"], "next_loop_module_diff_ready")
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_recursive_traversal_execution_next_action"], "plan_next_async_chunk_recursive_traversal_checkpoint")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_recursive_traversal_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_recursive_traversal_plan": {
                "status": "ready_for_next_loop_review",
                "recursive_plan": {
                    "status": "ready_for_next_loop_review",
                    "next_action": "review_next_custom_loader_traversal_loop_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_recursive_traversal_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_recursive_traversal_plan")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_plan_status"], "ready_for_next_loop_review")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_plan_next_action"], "review_next_custom_loader_traversal_loop_plan")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_recursive_traversal_followup(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_recursive_traversal_followup": {
                "status": "next_loop_plan_ready",
                "followup": {
                    "status": "next_loop_plan_ready",
                    "stages": [{"stage": "plan_next_traversal_loop"}],
                    "next_action": "review_next_custom_loader_traversal_loop_plan_before_execution",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_recursive_traversal_followup_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_recursive_traversal_followup")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_followup_status"], "next_loop_plan_ready")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_followup_stage_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_followup_next_action"], "review_next_custom_loader_traversal_loop_plan_before_execution")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_custom_loader_recursive_traversal_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_recursive_traversal_execution": {
                "status": "next_loop_journal_appended",
                "execution": {
                    "status": "next_loop_journal_appended",
                    "stages": [{"stage": "execute_next_bounded_custom_loader_loop"}],
                    "next_action": "plan_next_custom_loader_recursive_traversal_checkpoint",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_recursive_traversal_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_recursive_traversal_execution")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_execution_status"], "next_loop_journal_appended")
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_recursive_traversal_execution_next_action"], "plan_next_custom_loader_recursive_traversal_checkpoint")
        self.assertTrue(result["side_effect_policy"]["read_only"])



    def test_review_hook_artifacts_warns_for_custom_loader_continuation_workflow(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_continuation_workflow": {
                "status": "ready_for_review",
                "workflow": {
                    "status": "ready_for_review",
                    "selected_candidate_index": 1,
                    "review_approved": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_continuation_workflow_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_continuation_workflow")
        self.assertEqual(result["summary"]["custom_loader_continuation_workflow_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_continuation_workflow_selected_candidate_index"], 1)
        self.assertFalse(result["summary"]["custom_loader_continuation_workflow_review_approved"])

    def test_review_hook_artifacts_warns_for_custom_loader_continuation_journal(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_continuation_journal": {
                "status": "ready_for_review",
                "journal": {
                    "status": "ready_for_review",
                    "record_count": 0,
                    "writes_journal_now": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_continuation_journal_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_continuation_journal_append")
        self.assertEqual(result["summary"]["custom_loader_continuation_journal_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_continuation_journal_record_count"], 0)
        self.assertFalse(result["summary"]["custom_loader_continuation_journal_writes_journal"])

    def test_review_hook_artifacts_warns_for_custom_loader_continuation_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_continuation_execution": {
                "status": "ready_for_review",
                "execution": {
                    "status": "ready_for_review",
                    "stages": [{"stage": "preflight", "status": "pending"}],
                    "next_action": "review_custom_loader_continuation_execution_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_continuation_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_continuation_execution_plan")
        self.assertEqual(result["summary"]["custom_loader_continuation_execution_status"], "ready_for_review")
        self.assertEqual(result["summary"]["custom_loader_continuation_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_continuation_execution_next_action"], "review_custom_loader_continuation_execution_plan")

    def test_review_hook_artifacts_warns_for_custom_loader_preflight_ready_to_execute(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_execution_preflight": {
                "status": "ready_for_execution_review",
                "preflight": {"status": "ready_for_execution_review"},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "execute_custom_loader_with_review_approval")
        self.assertEqual(result["summary"]["custom_loader_execution_preflight_status"], "ready_for_execution_review")

    def test_review_hook_artifacts_warns_for_reviewed_custom_loader_execution_without_module_diff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_traversal_plan": {
                "status": "planned",
                "plan": {"status": "ready_for_review", "candidate_count": 1, "ready_for_review_count": 1},
            },
            "custom_loader_execution_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True, "loaderInvoked": True, "addedRegistryKeys": ["884"]},
            },
        }

        result = tool(json.dumps(payload))

        self.assertNotIn("custom_loader_traversal_requires_review", result["warnings"])
        self.assertNotIn("custom_loader_execution_requires_review", result["warnings"])
        self.assertIn("custom_loader_module_diff_required", result["warnings"])
        self.assertEqual(result["next_action"], "run_custom_loader_module_diff_after_reviewed_execution")
        self.assertEqual(result["summary"]["custom_loader_execution_result_status"], "success")
        self.assertTrue(result["summary"]["custom_loader_execution_attempted"])
        self.assertTrue(result["summary"]["custom_loader_execution_loader_invoked"])
        self.assertEqual(result["summary"]["custom_loader_execution_added_registry_key_count"], 1)

    def test_review_hook_artifacts_warns_for_custom_loader_module_diff_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_execution_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True, "loaderInvoked": True, "addedRegistryKeys": ["884"]},
            },
            "custom_loader_module_diff": {
                "status": "planned",
                "matched_module_count": 1,
                "candidate_count": 1,
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("custom_loader_module_diff_requires_review", result["warnings"])
        self.assertNotIn("custom_loader_module_diff_required", result["warnings"])
        self.assertEqual(result["next_action"], "review_custom_loader_module_diff_hook_candidates")
        self.assertEqual(result["summary"]["custom_loader_module_diff_status"], "planned")
        self.assertEqual(result["summary"]["custom_loader_module_diff_matched_module_count"], 1)
        self.assertEqual(result["summary"]["custom_loader_module_diff_hook_candidate_count"], 1)
        self.assertEqual(result["review_required_items"][0]["custom_loader_module_diff_status"], "planned")

    def test_review_hook_artifacts_suppresses_custom_loader_module_diff_review_after_module_hook_install(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "custom_loader_execution_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True, "loaderInvoked": True, "addedRegistryKeys": ["884"]},
            },
            "custom_loader_module_diff": {
                "status": "planned",
                "matched_module_count": 1,
                "candidate_count": 1,
            },
            "module_hooks": {
                "status": "success",
                "installed": {"window.__webpack_require__(884).sign": True},
            },
            "module_hook_timeline": {
                "status": "success",
                "events": [
                    {"type": "module_export_call", "payload": {"moduleId": "884", "exportName": "sign"}}
                ],
            },
        }

        result = tool(json.dumps(payload))

        self.assertNotIn("custom_loader_module_diff_required", result["warnings"])
        self.assertNotIn("custom_loader_module_diff_requires_review", result["warnings"])
        self.assertEqual(result["summary"]["installed_module_hook_count"], 1)
        self.assertEqual(result["next_action"], "hook_review_passed")

    def test_review_hook_artifacts_warns_for_module_federation_get_init_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_get_init_plan": {
                "status": "planned",
                "plan": {
                    "status": "ready_for_review",
                    "candidate_count": 1,
                    "container_count": 1,
                    "exposed_module_count": 1,
                    "blocked_execution_count": 1,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_get_init_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_get_init_plan")
        self.assertEqual(result["summary"]["module_federation_get_init_plan_status"], "planned")
        self.assertEqual(result["summary"]["module_federation_get_init_candidate_count"], 1)
        self.assertEqual(result["summary"]["module_federation_get_init_container_count"], 1)
        self.assertEqual(result["summary"]["module_federation_get_init_exposed_module_count"], 1)
        self.assertEqual(result["summary"]["module_federation_get_init_blocked_execution_count"], 1)
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_reviewed_async_chunk_load_without_module_diff(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_load_plan": {"status": "ready_for_review", "chunk_id": "731"},
            "async_chunk_load_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True},
                "addedRegistryKeys": ["731"],
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_module_diff_required", result["warnings"])
        self.assertEqual(result["next_action"], "run_async_chunk_module_diff_after_reviewed_load")
        self.assertEqual(result["summary"]["async_chunk_load_result_status"], "success")
        self.assertTrue(result["summary"]["async_chunk_load_execution_attempted"])
        self.assertEqual(result["summary"]["async_chunk_load_added_registry_key_count"], 1)

    def test_review_hook_artifacts_warns_for_async_chunk_module_diff_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_load_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True, "addedRegistryKeys": ["731"]},
            },
            "async_chunk_module_diff": {
                "status": "planned",
                "matched_module_count": 1,
                "candidate_count": 1,
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("async_chunk_module_diff_requires_review", result["warnings"])
        self.assertNotIn("async_chunk_module_diff_required", result["warnings"])
        self.assertEqual(result["next_action"], "review_async_chunk_module_diff_hook_candidates")
        self.assertEqual(result["summary"]["async_chunk_module_diff_status"], "planned")
        self.assertEqual(result["summary"]["async_chunk_module_diff_matched_module_count"], 1)
        self.assertEqual(result["summary"]["async_chunk_module_diff_hook_candidate_count"], 1)
        self.assertEqual(result["review_required_items"][0]["async_chunk_module_diff_status"], "planned")


    def test_review_hook_artifacts_suppresses_async_chunk_diff_review_after_module_hook_install(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "async_chunk_load_result": {
                "status": "success",
                "execution": {"attempted": True, "ok": True, "addedRegistryKeys": ["731"]},
            },
            "async_chunk_module_diff": {
                "status": "planned",
                "matched_module_count": 1,
                "candidate_count": 1,
            },
            "module_hooks": {
                "status": "success",
                "installed": {"window.__webpack_require__(731).sign": True},
            },
            "module_hook_timeline": {
                "status": "success",
                "events": [
                    {"type": "module_export_call", "payload": {"moduleId": "731", "exportName": "sign"}}
                ],
            },
        }

        result = tool(json.dumps(payload))

        self.assertNotIn("async_chunk_module_diff_requires_review", result["warnings"])
        self.assertEqual(result["summary"]["installed_module_hook_count"], 1)
        self.assertEqual(result["next_action"], "hook_review_passed")

    def test_review_hook_artifacts_warns_for_module_federation_get_init_probe_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_get_init_plan": {
                "status": "planned",
                "plan": {"status": "ready_for_review", "candidate_count": 1},
            },
            "module_federation_get_init_result": {
                "status": "success",
                "execution": {
                    "attempted": True,
                    "ok": True,
                    "containerInitCalled": True,
                    "remoteGetCalled": True,
                    "remoteFactoryInvoked": False,
                    "addedSharedScopeKeys": ["default"],
                },
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_get_init_probe_requires_factory_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_get_init_probe_before_factory_invocation")
        self.assertEqual(result["summary"]["module_federation_get_init_result_status"], "success")
        self.assertTrue(result["summary"]["module_federation_get_init_execution_attempted"])
        self.assertTrue(result["summary"]["module_federation_get_init_container_init_called"])
        self.assertTrue(result["summary"]["module_federation_get_init_remote_get_called"])
        self.assertFalse(result["summary"]["module_federation_get_init_remote_factory_invoked"])
        self.assertEqual(result["summary"]["module_federation_get_init_added_shared_scope_key_count"], 1)
        self.assertEqual(result["review_required_items"][0]["module_federation_get_init_result_status"], "success")

    def test_review_hook_artifacts_warns_for_module_federation_factory_invoke_result(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_get_init_plan": {
                "status": "planned",
                "plan": {"status": "ready_for_review", "candidate_count": 1},
            },
            "module_federation_factory_invoke_result": {
                "status": "success",
                "factory_execution": {
                    "attempted": True,
                    "ok": True,
                    "remoteFactoryInvoked": True,
                    "remoteCodeExecuted": True,
                    "exportNames": ["sign"],
                },
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_factory_exports_require_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_factory_exports_before_hooking")
        self.assertEqual(result["summary"]["module_federation_factory_invoke_result_status"], "success")
        self.assertTrue(result["summary"]["module_federation_factory_execution_attempted"])
        self.assertTrue(result["summary"]["module_federation_factory_remote_factory_invoked"])
        self.assertTrue(result["summary"]["module_federation_factory_remote_code_executed"])
        self.assertEqual(result["summary"]["module_federation_factory_export_count"], 1)
        self.assertEqual(result["review_required_items"][0]["module_federation_factory_invoke_result_status"], "success")


    def test_review_hook_artifacts_warns_for_module_federation_traversal_graph(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_traversal_graph": {
                "status": "ready_for_review",
                "graph": {
                    "status": "ready_for_review",
                    "queue_count": 1,
                    "next_action": "review_module_federation_traversal_workflow_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_traversal_graph_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_traversal_graph")
        self.assertEqual(result["summary"]["module_federation_traversal_graph_status"], "ready_for_review")
        self.assertEqual(result["summary"]["module_federation_traversal_graph_queue_count"], 1)
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_module_federation_traversal_workflow_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_traversal_workflow_plan": {
                "status": "ready_for_review",
                "workflow_plan": {
                    "status": "ready_for_review",
                    "planned_step_count": 1,
                    "next_action": "review_module_federation_traversal_workflow_plan",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_traversal_workflow_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_traversal_workflow_plan")
        self.assertEqual(result["summary"]["module_federation_traversal_workflow_plan_status"], "ready_for_review")
        self.assertEqual(result["summary"]["module_federation_traversal_workflow_planned_step_count"], 1)
        self.assertTrue(result["side_effect_policy"]["read_only"])



    def test_review_hook_artifacts_warns_for_module_federation_traversal_workflow_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_traversal_workflow_execution": {
                "status": "factory_invoke_success",
                "execution": {
                    "status": "factory_invoke_success",
                    "stages": [{"stage": "invoke_one_reviewed_module_federation_remote_factory", "status": "success"}],
                    "next_action": "plan_module_federation_export_hook_after_reviewed_factory_invoke",
                    "module_federation_factory_invoke_result": {"factory_execution": {"remoteFactoryInvoked": True}},
                },
                "side_effect_policy": {"remote_factory_invoked": True, "export_hook_installed": False},
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_traversal_workflow_execution_next_stage_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_traversal_workflow_execution_next_stage")
        self.assertEqual(result["summary"]["module_federation_traversal_workflow_execution_status"], "factory_invoke_success")
        self.assertEqual(result["summary"]["module_federation_traversal_workflow_execution_stage_count"], 1)
        self.assertTrue(result["summary"]["module_federation_traversal_workflow_execution_remote_factory_invoked"])
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_module_federation_recursive_traversal_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_recursive_traversal_plan": {
                "status": "ready_for_next_step_review",
                "recursive_plan": {
                    "status": "ready_for_next_step_review",
                    "latest_workflow_execution_status": "factory_invoke_success",
                    "latest_graph_queue_count": 1,
                    "latest_workflow_planned_step_count": 1,
                    "next_action": "review_next_module_federation_traversal_workflow_step",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_recursive_traversal_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_recursive_traversal_plan")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_plan_status"], "ready_for_next_step_review")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_plan_next_action"], "review_next_module_federation_traversal_workflow_step")
        self.assertEqual(result["review_required_items"][0]["module_federation_recursive_traversal_plan_status"], "ready_for_next_step_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_module_federation_recursive_traversal_followup(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_recursive_traversal_followup": {
                "status": "next_step_review_ready",
                "followup": {
                    "status": "next_step_review_ready",
                    "stages": [{"stage": "plan_next_traversal_step_review", "status": "ready_for_review"}],
                    "next_action": "review_next_module_federation_traversal_workflow_execution",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_recursive_traversal_followup_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_recursive_traversal_followup")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_followup_status"], "next_step_review_ready")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_followup_stage_count"], 1)
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_followup_next_action"], "review_next_module_federation_traversal_workflow_execution")
        self.assertEqual(result["review_required_items"][0]["module_federation_recursive_traversal_followup_status"], "next_step_review_ready")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_module_federation_recursive_continuation_journal(self) -> None:
        tool = make_review_hook_artifacts_tool()
        result = tool(json.dumps({
            "module_federation_recursive_continuation_journal": {
                "status": "ready_for_review",
                "journal": {
                    "status": "ready_for_review",
                    "record_count": 0,
                    "writes_journal_now": False,
                    "next_action": "review_module_federation_recursive_continuation_journal_append",
                },
            }
        }))

        self.assertIn("module_federation_recursive_continuation_journal_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_recursive_continuation_journal_append")
        self.assertEqual(result["summary"]["module_federation_recursive_continuation_journal_status"], "ready_for_review")
        self.assertEqual(result["summary"]["module_federation_recursive_continuation_journal_record_count"], 0)
        self.assertFalse(result["summary"]["module_federation_recursive_continuation_journal_writes_journal"])
        self.assertEqual(result["review_required_items"][0]["module_federation_recursive_continuation_journal_status"], "ready_for_review")

    def test_review_hook_artifacts_warns_for_module_federation_recursive_continuation_checkpoint(self) -> None:
        tool = make_review_hook_artifacts_tool()
        result = tool(json.dumps({
            "module_federation_recursive_continuation_checkpoint": {
                "status": "next_execution_review_ready",
                "checkpoint": {
                    "status": "next_execution_review_ready",
                    "stages": [{"stage": "review_next_module_federation_recursive_traversal_execution", "status": "ready_for_review"}],
                    "next_action": "review_next_module_federation_recursive_traversal_execution",
                },
            }
        }))

        self.assertIn("module_federation_recursive_continuation_checkpoint_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_recursive_continuation_checkpoint")
        self.assertEqual(result["summary"]["module_federation_recursive_continuation_checkpoint_status"], "next_execution_review_ready")
        self.assertEqual(result["summary"]["module_federation_recursive_continuation_checkpoint_stage_count"], 1)
        self.assertEqual(result["summary"]["module_federation_recursive_continuation_checkpoint_next_action"], "review_next_module_federation_recursive_traversal_execution")
        self.assertEqual(result["review_required_items"][0]["module_federation_recursive_continuation_checkpoint_status"], "next_execution_review_ready")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_recursive_continuation_readiness(self) -> None:
        tool = make_review_hook_artifacts_tool()
        result = tool(json.dumps({
            "recursive_continuation_readiness": {
                "schema_version": "reverse-deepagent.recursive-continuation-readiness.v1",
                "status": "ready_for_review",
                "system_count": 3,
                "ready_systems": ["custom_loader", "async_chunk", "module_federation"],
                "blocked_systems": [],
                "deeper_recursion_executor_ready": False,
            }
        }))

        self.assertIn("recursive_continuation_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_recursive_continuation_readiness")
        self.assertEqual(result["summary"]["recursive_continuation_readiness_status"], "ready_for_review")
        self.assertEqual(result["summary"]["recursive_continuation_readiness_system_count"], 3)
        self.assertEqual(result["summary"]["recursive_continuation_readiness_ready_systems"], ["custom_loader", "async_chunk", "module_federation"])
        self.assertFalse(result["summary"]["recursive_continuation_readiness_deeper_recursion_executor_ready"])
        self.assertEqual(result["review_required_items"][0]["recursive_continuation_readiness_status"], "ready_for_review")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_blocks_for_recursive_continuation_readiness(self) -> None:
        tool = make_review_hook_artifacts_tool()
        result = tool(json.dumps({
            "recursive_continuation_readiness": {
                "readiness": {
                    "schema_version": "reverse-deepagent.recursive-continuation-readiness.v1",
                    "status": "blocked",
                    "system_count": 1,
                    "ready_systems": [],
                    "blocked_systems": ["async_chunk"],
                    "blocking_reasons": ["async_chunk_recursive_plan_blocked"],
                    "deeper_recursion_executor_ready": False,
                }
            }
        }))

        self.assertIn("recursive_continuation_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_recursive_continuation_readiness_blockers")
        self.assertEqual(result["summary"]["recursive_continuation_readiness_status"], "blocked")
        self.assertEqual(result["summary"]["recursive_continuation_readiness_blocked_systems"], ["async_chunk"])


    def test_review_hook_artifacts_warns_for_module_federation_recursive_traversal_execution(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_recursive_traversal_execution": {
                "status": "next_step_execution_progressed",
                "execution": {
                    "status": "next_step_execution_progressed",
                    "stages": [{"stage": "execute_next_module_federation_traversal_workflow_step", "status": "factory_invoke_success"}],
                    "next_action": "continue_reviewed_module_federation_traversal_step_or_plan_next_checkpoint",
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_recursive_traversal_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_recursive_traversal_execution")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_execution_status"], "next_step_execution_progressed")
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_execution_stage_count"], 1)
        self.assertEqual(result["summary"]["module_federation_recursive_traversal_execution_next_action"], "continue_reviewed_module_federation_traversal_step_or_plan_next_checkpoint")
        self.assertEqual(result["review_required_items"][0]["module_federation_recursive_traversal_execution_status"], "next_step_execution_progressed")
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_hook_artifacts_warns_for_module_federation_export_hook_plan(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_factory_invoke_result": {
                "status": "success",
                "factory_execution": {
                    "attempted": True,
                    "ok": True,
                    "remoteFactoryInvoked": True,
                    "remoteCodeExecuted": True,
                    "exportNames": ["sign"],
                },
            },
            "module_federation_export_hook_plan": {
                "status": "planned",
                "candidate_count": 1,
                "hookable_candidate_count": 1,
            },
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("module_federation_export_hook_plan_requires_review", result["warnings"])
        self.assertNotIn("module_federation_factory_exports_require_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_module_federation_export_hook_plan")
        self.assertEqual(result["summary"]["module_federation_export_hook_plan_status"], "planned")
        self.assertEqual(result["summary"]["module_federation_export_hook_candidate_count"], 1)
        self.assertEqual(result["summary"]["module_federation_export_hook_hookable_candidate_count"], 1)
        self.assertEqual(result["review_required_items"][0]["module_federation_export_hook_plan_status"], "planned")



    def test_review_hook_artifacts_suppresses_federation_export_plan_after_function_hook_install(self) -> None:
        tool = make_review_hook_artifacts_tool()
        payload = {
            "module_federation_factory_invoke_result": {
                "status": "success",
                "factory_execution": {
                    "attempted": True,
                    "ok": True,
                    "remoteFactoryInvoked": True,
                    "remoteCodeExecuted": True,
                    "exportNames": ["sign"],
                },
            },
            "module_federation_export_hook_plan": {
                "status": "planned",
                "candidate_count": 1,
                "hookable_candidate_count": 1,
            },
            "function_hooks": {
                "status": "success",
                "installed": {"window.remoteApp:./sign:sign": True},
            },
            "function_hook_timeline": {
                "status": "success",
                "events": [
                    {"type": "remote_export_call", "payload": {"hookPath": "window.remoteApp:./sign:sign"}}
                ],
            },
        }

        result = tool(json.dumps(payload))

        self.assertNotIn("module_federation_export_hook_plan_requires_review", result["warnings"])
        self.assertEqual(result["summary"]["installed_function_hook_count"], 1)
        self.assertEqual(result["next_action"], "hook_review_passed")

    def test_review_hook_artifacts_reads_artifact_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            payload = {
                "function_hooks": {"status": "success", "installed": {"window.buildSign": True}},
                "function_hook_timeline": {"events": [{"type": "call"}]},
            }
            (workspace / "function-hooks.json").write_text(json.dumps(payload), encoding="utf-8")

            result = make_review_hook_artifacts_tool(artifact_root)(hook_artifacts_ref="workspace_function_hooks")

            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["summary"]["installed_function_hook_count"], 1)
            self.assertEqual(result["artifact_input"]["artifact_ref"], "workspace_function_hooks")
            self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_build_hook_subagent_exposes_read_only_review_tool(self) -> None:
        subagent = build_hook_subagent()

        self.assertEqual(subagent["name"], HOOK_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], HOOK_SUBAGENT_DESCRIPTION)
        self.assertIn("Hook Subagent", subagent["system_prompt"])
        self.assertEqual(
            {tool.__name__ for tool in subagent["tools"]},
            {
                "read_workspace_artifact",
                "review_hook_artifacts",
                "record_heap_snapshot_diff_executor_approval",
                "record_heap_snapshot_diff_executor_transaction_journal",
                "record_heap_snapshot_retained_size_approval",
                "record_heap_snapshot_retained_size_transaction_journal",
                "record_source_map_selected_executor_approval",
                "record_source_map_followthrough_dispatch_approval",
                "record_source_map_followthrough_dispatch_transaction_journal",
            },
        )

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/hook.txt"
        self.assertIn("record_heap_snapshot_diff_executor_approval", load_hook_prompt(path))
        self.assertIn("record_heap_snapshot_diff_executor_transaction_journal", load_hook_prompt(path))
        self.assertIn("record_heap_snapshot_retained_size_approval", load_hook_prompt(path))
        self.assertIn("record_heap_snapshot_retained_size_transaction_journal", load_hook_prompt(path))
        self.assertIn("record_source_map_selected_executor_approval", load_hook_prompt(path))
        self.assertIn("record_source_map_followthrough_dispatch_approval", load_hook_prompt(path))
        self.assertIn("record_source_map_followthrough_dispatch_transaction_journal", load_hook_prompt(path))

    def test_default_agent_includes_hook_before_timeline(self) -> None:
        captured = {}

        def fake_create_deep_agent(**kwargs):
            captured.update(kwargs)
            return {"captured": kwargs}

        import reverse_deepagent.agent as agent_module

        original = agent_module.create_deep_agent
        try:
            agent_module.create_deep_agent = fake_create_deep_agent
            build_reverse_agent(model=ToolFriendlyFakeModel())
        finally:
            agent_module.create_deep_agent = original

        names = [item["name"] for item in captured["subagents"]]
        self.assertIn("hook", names)
        self.assertLess(names.index("debugger"), names.index("hook"))
        self.assertLess(names.index("hook"), names.index("timeline"))


if __name__ == "__main__":
    unittest.main()
