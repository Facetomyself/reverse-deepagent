import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.subagents.debugger import (
    DEBUGGER_SUBAGENT_DESCRIPTION,
    DEBUGGER_SUBAGENT_NAME,
    build_debugger_subagent,
    load_debugger_prompt,
)
from reverse_deepagent.tools.debugger_tools import (
    make_record_paused_session_automatic_loop_executor_approval_tool,
    make_record_paused_session_automatic_loop_transaction_journal_tool,
    make_review_debugger_artifacts_tool,
    make_review_paused_session_automatic_loop_bounded_executor_gate_tool,
    make_review_paused_session_automatic_loop_transaction_preflight_tool,
)


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


def _ready_automatic_loop_executor_approval_plan() -> dict:
    return {
        "schema_version": "reverse-deepagent.paused-session-automatic-loop-executor-approval-plan.v1",
        "status": "ready_for_review",
        "ready_for_review": True,
        "approval_plan_ready_for_review": True,
        "approval_plan_id": "automatic-loop-executor-approval-plan:preflight-1",
        "preflight_id": "preflight-1",
        "plan_id": "plan-1",
        "loop_id": "loop-1",
        "workflow_id": "workflow-1",
        "pause_session_id": "pause-1",
        "target_id": "target-1",
        "approved_iteration_count": 1,
        "max_approved_iterations": 2,
        "approved_iterations": [
            {
                "iteration_index": 0,
                "workflow_step_index": 0,
                "method": "Debugger.stepOver",
                "fingerprint": "step-0",
                "requires_checkpoint_after_iteration": True,
            }
        ],
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_recorded": False,
            "transaction_started": False,
            "journal_written": False,
        },
        "future_executor_contract": {
            "implemented": False,
            "executor_name": "execute_paused_session_automatic_loop",
        },
        "transaction_plan": {
            "transaction_id": "automatic-loop-executor-transaction:preflight-1",
            "transaction_started": False,
            "journal_written_now": False,
        },
        "blockers": [],
        "next_action": "review_future_bounded_automatic_loop_executor_approval_transaction",
    }


def _ready_automatic_loop_executor_approval_record() -> dict:
    return {
        "schema_version": "reverse-deepagent.paused-session-automatic-loop-executor-approval-record.v1",
        "status": "written",
        "approval_recorded": True,
        "approved_for_execution": True,
        "approval_record_id": "automatic-loop-executor-approval-record:abc123",
        "approval_plan_id": "automatic-loop-executor-approval-plan:preflight-1",
        "preflight_id": "preflight-1",
        "plan_id": "plan-1",
        "loop_id": "loop-1",
        "workflow_id": "workflow-1",
        "pause_session_id": "pause-1",
        "target_id": "target-1",
        "decision": "approved",
        "reviewer": "alice",
        "approved_iterations": [
            {
                "iteration_index": 0,
                "workflow_step_index": 0,
                "method": "Debugger.stepOver",
                "fingerprint": "step-0",
                "executed_now": False,
                "requires_checkpoint_after_iteration": True,
            }
        ],
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_recorded": True,
            "approved_for_execution": True,
            "transaction_started": False,
            "journal_written": False,
        },
        "side_effect_policy": {
            "writes_approval_record": True,
            "writes_transaction_journal": False,
            "transaction_started": False,
            "automatic_loop_executed": False,
            "cdp_command_sent": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        },
        "blockers": [],
    }


def _ready_automatic_loop_transaction_preflight() -> dict:
    return {
        "schema_version": "reverse-deepagent.paused-session-automatic-loop-transaction-preflight.v1",
        "status": "ready_for_review",
        "ready_for_review": True,
        "transaction_preflight_ready_for_review": True,
        "transaction_preflight_id": "automatic-loop-transaction-preflight:record-1",
        "approval_record_id": "automatic-loop-executor-approval-record:abc123",
        "approval_plan_id": "automatic-loop-executor-approval-plan:preflight-1",
        "preflight_id": "preflight-1",
        "plan_id": "plan-1",
        "loop_id": "loop-1",
        "workflow_id": "workflow-1",
        "pause_session_id": "pause-1",
        "target_id": "target-1",
        "transaction_plan": {
            "transaction_id": "automatic-loop-executor-transaction:preflight-1",
            "idempotency_key": "automatic-loop-executor-transaction:preflight-1",
            "transaction_started": False,
            "journal_written_now": False,
            "journal_artifact": "workspace/paused-session-automatic-loop-executor-journal.json",
            "result_artifact": "workspace/paused-session-automatic-loop-execution-result.json",
            "ready_for_journal_writer_review": True,
            "ready_to_write_now": False,
            "future_journal_writer_implemented": False,
        },
        "journal_writer_input_gates": {
            "approval_plan_verified": True,
            "approval_record_verified": True,
            "ready_for_review": True,
            "ready_to_write_now": False,
            "transaction_started": False,
            "journal_written": False,
            "automatic_loop_executed": False,
        },
        "planned_journal_entries": [
            {
                "entry_index": 0,
                "entry_kind": "planned_iteration",
                "iteration_index": 0,
                "workflow_step_index": 0,
                "method": "Debugger.stepOver",
                "fingerprint": "step-0",
                "would_write_now": False,
                "requires_checkpoint_after_iteration": True,
            }
        ],
        "side_effect_policy": {
            "read_only": True,
            "writes_transaction_journal": False,
            "transaction_started": False,
            "automatic_loop_executed": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        },
        "blockers": [],
    }


def _ready_automatic_loop_transaction_journal() -> dict:
    return {
        "schema_version": "reverse-deepagent.paused-session-automatic-loop-transaction-journal.v1",
        "status": "written",
        "journal_written": True,
        "transaction_started": True,
        "journal_id": "automatic-loop-transaction-journal:abc123",
        "transaction_preflight_id": "automatic-loop-transaction-preflight:record-1",
        "approval_record_id": "automatic-loop-executor-approval-record:abc123",
        "approval_plan_id": "automatic-loop-executor-approval-plan:preflight-1",
        "preflight_id": "preflight-1",
        "transaction_id": "automatic-loop-executor-transaction:preflight-1",
        "plan_id": "plan-1",
        "loop_id": "loop-1",
        "workflow_id": "workflow-1",
        "pause_session_id": "pause-1",
        "target_id": "target-1",
        "journal_entries": [
            {
                "entry_index": 0,
                "entry_kind": "transaction_started",
                "transaction_id": "automatic-loop-executor-transaction:preflight-1",
                "automatic_loop_executed": False,
            },
            {
                "entry_index": 1,
                "entry_kind": "planned_iteration_journaled",
                "iteration_index": 0,
                "workflow_step_index": 0,
                "method": "Debugger.stepOver",
                "fingerprint": "step-0",
                "executed_now": False,
                "requires_fresh_live_callframe_before_execution": True,
                "requires_checkpoint_after_iteration": True,
            },
        ],
        "journal_summary": {
            "entry_count": 2,
            "planned_entry_count": 2,
            "transaction_started": True,
            "journal_written": True,
            "automatic_loop_executed": False,
            "requires_bounded_executor_followup": True,
        },
        "executor_input_gates": {
            "ready_to_execute_now": False,
            "approval_record_verified": True,
            "transaction_started": True,
            "journal_written": True,
            "automatic_loop_executed": False,
            "requires_fresh_live_callframe_per_iteration": True,
            "requires_checkpoint_after_each_iteration": True,
            "requires_bounded_executor_review": True,
        },
        "side_effect_policy": {
            "writes_transaction_journal": True,
            "transaction_started": True,
            "journal_written": True,
            "automatic_loop_executed": False,
            "cdp_command_sent": False,
            "cdp_target_attached": False,
            "debugger_event_subscribed": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        },
        "blockers": [],
    }


class DebuggerSubagentTests(unittest.TestCase):
    def test_review_debugger_artifacts_blocks_durable_snapshot_live_resume(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "debugger_session": {
                "session_id": "durable-1",
                "status": "unsupported",
                "reason": "durable_snapshot_is_inspect_only",
                "continuation_preflight": {
                    "status": "action_blocked",
                    "source": "durable_snapshot",
                    "reason": "live_paused_session_required",
                    "requested_action": "resume",
                    "live_continuation_available": False,
                    "live_session_diagnostics": {
                        "live_session_available": False,
                        "debugger_session_lifecycle": "retained_paused",
                        "same_process_required_for_live_action": True,
                    },
                    "target_diagnostics": {
                        "target_attached": False,
                        "cdp_target_available": False,
                        "target_attached_source": "durable_snapshot_inspect_only",
                    },
                    "callframe_diagnostics": {
                        "stable_callframe_required": False,
                        "stable_callframe_available": False,
                        "callframe_count": 1,
                    },
                },
            },
            "callframes": [
                {
                    "functionName": "buildSign",
                    "location": {"url": "https://example.test/app.js", "lineNumber": 12, "columnNumber": 4},
                }
            ],
            "debugger_timeline": {"entry_count": 2, "entries": [{"event": "paused"}, {"event": "snapshot_loaded"}]},
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertTrue(result["blocked"])
        self.assertIn("paused_session_action_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "use_live_same_process_paused_session_before_resume_step_or_evaluate")
        self.assertEqual(result["summary"]["session_id"], "durable-1")
        self.assertFalse(result["summary"]["live_session_diagnostics"]["live_session_available"])
        self.assertTrue(result["summary"]["live_session_diagnostics"]["same_process_required_for_live_action"])
        self.assertEqual(result["summary"]["target_diagnostics"]["target_attached_source"], "durable_snapshot_inspect_only")
        self.assertFalse(result["review_required_items"][0]["diagnostics"]["target_attached"])
        self.assertEqual(result["summary"]["callframe_count"], 1)
        self.assertEqual(result["summary"]["top_callframes"][0]["function_name"], "buildSign")
        self.assertEqual(result["review_required_items"][0]["code"], "paused_session_action_blocked")
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["browser_resumed"])
        self.assertFalse(result["side_effect_policy"]["callframe_evaluated"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_passes_live_available_paused_session(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "debugger_session": {
                "session_id": "live-1",
                "status": "success",
                "continuation_preflight": {
                    "status": "live_available",
                    "source": "registry",
                    "requested_action": "inspect",
                    "live_continuation_available": True,
                },
            },
            "debugger_paused": {"status": "paused"},
            "callframes": [{"functionName": "sign", "location": {"lineNumber": 1}}],
            "debugger_timeline": {"entries": [{"event": "paused"}, {"event": "callframes_captured"}]},
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["next_action"], "debugger_review_passed")
        self.assertEqual(result["summary"]["preflight_source"], "registry")
        self.assertTrue(result["summary"]["live_continuation_available"])
        self.assertEqual(result["summary"]["timeline_event_counts"]["paused"], 1)

    def test_review_debugger_artifacts_blocks_live_continuation_preflight(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_live_continuation_preflight": {
                "status": "blocked",
                "preflight": {
                    "status": "blocked",
                    "source": "durable_snapshot",
                    "requested_action": "resume",
                    "live_continuation_available": False,
                    "cross_process_live_continuation_supported": False,
                    "blockers": ["live_paused_session_required", "target_not_attached"],
                    "reason": "live_paused_session_required",
                    "live_session_diagnostics": {
                        "live_session_available": False,
                        "debugger_session_lifecycle": "retained_paused",
                        "same_process_required_for_live_action": True,
                    },
                    "target_diagnostics": {
                        "target_attached": False,
                        "cdp_target_available": False,
                        "target_attached_source": "not_attached",
                    },
                    "callframe_diagnostics": {
                        "stable_callframe_required": True,
                        "stable_callframe_available": False,
                        "selected_callframe_has_id": False,
                    },
                    "action_capability": {
                        "requested_action": "resume",
                        "is_live_action": True,
                        "resume_supported": False,
                    },
                },
                "side_effect_policy": {
                    "read_only": True,
                    "cdp_command_sent": False,
                    "browser_resumed": False,
                    "debugger_stepped": False,
                    "callframe_evaluated": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertTrue(result["blocked"])
        self.assertIn("paused_session_live_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "reproduce_pause_in_current_process_before_live_action")
        self.assertFalse(result["summary"]["live_continuation_available"])
        self.assertFalse(result["summary"]["cross_process_live_continuation_supported"])
        self.assertEqual(result["summary"]["preflight_blockers"], ["live_paused_session_required", "target_not_attached"])
        self.assertFalse(result["summary"]["live_session_diagnostics"]["live_session_available"])
        self.assertEqual(result["summary"]["target_diagnostics"]["target_attached_source"], "not_attached")
        self.assertTrue(result["summary"]["callframe_diagnostics"]["stable_callframe_required"])
        self.assertTrue(result["summary"]["action_capability"]["is_live_action"])
        self.assertTrue(result["review_required_items"][0]["diagnostics"]["same_process_required_for_live_action"])
        self.assertTrue(result["side_effect_policy"]["read_only"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result["side_effect_policy"]["browser_resumed"])
        self.assertFalse(result["side_effect_policy"]["debugger_stepped"])
        self.assertFalse(result["side_effect_policy"]["callframe_evaluated"])

    def test_review_debugger_artifacts_warns_for_attach_ready_without_execution_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_target_attach_readiness": {
                "status": "ready_for_attach_review",
                "readiness": {
                    "status": "ready_for_attach_review",
                    "source": "durable_snapshot",
                    "pause_session_id": "attach-ready-1",
                    "requested_action": "evaluate",
                    "target_attach_readiness_proven": True,
                    "cross_process_live_continuation_supported": False,
                    "cross_process_execution_ready": False,
                    "blockers": ["stable_live_callframe_unavailable", "cross_process_live_continuation_not_implemented"],
                    "target_correlation": {
                        "expected_url": "https://example.test/app.js",
                        "candidate_count": 1,
                        "url_match": True,
                    },
                    "attachability": {
                        "target_id_available": True,
                        "would_attach_cdp_target": False,
                    },
                    "callframe_recovery": {
                        "stable_live_callframe_available": False,
                        "requires_new_paused_event_after_attach": True,
                    },
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("target_attach_ready_but_execution_plan_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "plan_cross_process_execution_after_target_attach_readiness")
        readiness = result["summary"]["target_attach_readiness"]
        self.assertTrue(readiness["target_attach_readiness_proven"])
        self.assertFalse(readiness["cross_process_execution_ready"])
        self.assertEqual(readiness["expected_url"], "https://example.test/app.js")
        self.assertTrue(readiness["target_id_available"])
        self.assertFalse(readiness["would_attach_cdp_target"])
        self.assertEqual(result["review_required_items"][0]["code"], "target_attach_ready_but_execution_plan_not_observed")
        self.assertFalse(result["review_required_items"][0]["attach_readiness_diagnostics"]["cross_process_execution_ready"])
        self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_review_debugger_artifacts_blocks_target_attach_readiness_failure(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_target_attach_readiness": {
                "readiness": {
                    "status": "blocked",
                    "source": "provided_artifact",
                    "pause_session_id": "attach-blocked-1",
                    "target_attach_readiness_proven": False,
                    "cross_process_execution_ready": False,
                    "blockers": ["target_url_mismatch", "cross_process_live_continuation_not_implemented"],
                    "target_correlation": {
                        "expected_url": "https://example.test/app.js",
                        "candidate_count": 1,
                        "url_match": False,
                    },
                    "attachability": {
                        "target_id_available": False,
                        "would_attach_cdp_target": False,
                    },
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_target_attach_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "collect_target_candidates_or_match_paused_url_before_attach_review")
        self.assertFalse(result["summary"]["target_attach_readiness"]["target_attach_readiness_proven"])
        self.assertFalse(result["review_required_items"][0]["attach_readiness_diagnostics"]["url_match"])

    def test_review_debugger_artifacts_warns_for_cross_process_execution_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_execution_plan": {
                "status": "ready_for_executor_review",
                "plan": {
                    "status": "ready_for_executor_review",
                    "pause_session_id": "cross-plan-1",
                    "requested_action": "evaluate",
                    "execution_plan_ready_for_review": True,
                    "cross_process_execution_ready": False,
                    "cross_process_executor_implemented": True,
                    "cross_process_action_supported": True,
                    "target_attach_readiness_proven": True,
                    "blockers": [],
                    "target_attach_readiness_summary": {
                        "expected_url": "https://example.test/app.js",
                        "candidate_count": 1,
                        "selected_target": {"target_id": "target-1", "type": "page"},
                        "target_id_available": True,
                    },
                    "callframe_recovery_plan": {
                        "requires_new_paused_event_after_attach": True,
                    },
                    "review_gates": {
                        "attach_probe_review_required": True,
                        "action_execution_review_required": True,
                    },
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_execution_plan_ready_but_attach_probe_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "run_reviewed_cross_process_attach_probe_next")
        plan = result["summary"]["cross_process_execution_plan"]
        self.assertTrue(plan["execution_plan_ready_for_review"])
        self.assertFalse(plan["cross_process_execution_ready"])
        self.assertTrue(plan["cross_process_executor_implemented"])
        self.assertTrue(plan["target_id_available"])
        self.assertTrue(plan["requires_new_paused_event_after_attach"])
        self.assertTrue(result["review_required_items"][0]["cross_process_execution_plan_diagnostics"]["execution_plan_ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_cross_process_session_lifecycle(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_session_lifecycle": {
                "status": "ready_for_review",
                "lifecycle": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "pause_session_id": "debugger-life-1",
                    "target_id": "target-debugger-life",
                    "session_diagnostics": {"attached_session_retained": True},
                    "target_diagnostics": {
                        "target_still_alive_proven": False,
                        "target_still_alive_proof_requires_cdp_probe": True,
                    },
                    "debugger_diagnostics": {
                        "live_callframe_recovered": True,
                        "live_callframe_id_present": True,
                    },
                    "continuation_diagnostics": {
                        "automatic_multi_step_loop_supported": False,
                        "automatic_wrapper_continuation_supported": False,
                    },
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_session_lifecycle_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_paused_session_lifecycle_before_next_continuation_step")
        lifecycle = result["summary"]["cross_process_session_lifecycle"]
        self.assertTrue(lifecycle["ready_for_review"])
        self.assertTrue(lifecycle["attached_session_retained"])
        self.assertFalse(lifecycle["target_still_alive_proven"])
        self.assertFalse(lifecycle["automatic_multi_step_loop_supported"])
        self.assertFalse(lifecycle["automatic_wrapper_continuation_supported"])
        self.assertTrue(result["review_required_items"][0]["cross_process_session_lifecycle_diagnostics"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_cross_process_session_lifecycle(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_session_lifecycle": {
                "status": "blocked",
                "lifecycle": {
                    "status": "blocked",
                    "blockers": ["target_id_required"],
                    "ready_for_review": False,
                },
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_cross_process_session_lifecycle_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_paused_session_lifecycle_blockers")
        self.assertFalse(result["summary"]["cross_process_session_lifecycle"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])


    def test_review_debugger_artifacts_warns_after_cross_process_attach_probe_without_live_callframe(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_attach_probe": {
                "probe": {
                    "status": "attached",
                    "pause_session_id": "attach-probe-review-1",
                    "requested_action": "evaluate",
                    "target_id": "target-review-1",
                    "attach_attempted": True,
                    "target_attached": True,
                    "target_detached": True,
                    "debugger_domain_enabled": False,
                    "live_callframe_recovered": False,
                    "live_action_executed": False,
                    "browser_resumed": False,
                    "debugger_stepped": False,
                    "callframe_evaluated": False,
                    "cdp_methods": ["Target.attachToTarget", "Target.detachFromTarget"],
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("attach_probe_ready_but_live_callframe_recovery_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "review_attach_probe_result_before_live_callframe_recovery")
        probe = result["summary"]["cross_process_attach_probe"]
        self.assertEqual(probe["status"], "attached")
        self.assertTrue(probe["attach_attempted"])
        self.assertTrue(probe["target_attached"])
        self.assertTrue(probe["target_detached"])
        self.assertFalse(probe["debugger_domain_enabled"])
        self.assertFalse(probe["live_callframe_recovered"])
        self.assertFalse(probe["live_action_executed"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result["side_effect_policy"]["mobile_runtime_used"])


    def test_review_debugger_artifacts_warns_when_live_callframe_recovered_but_executor_missing(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_live_callframe_recovery": {
                "recovery": {
                    "status": "recovered",
                    "pause_session_id": "recover-review-1",
                    "requested_action": "evaluate",
                    "target_id": "target-review-1",
                    "attach_probe_status": "attached",
                    "target_attached": True,
                    "fresh_paused_event_after_attach": True,
                    "callframe_count": 1,
                    "selected_callframe_has_id": True,
                    "live_callframe_recovered": True,
                    "one_action_executor_ready_for_review": True,
                    "debugger_domain_enabled": False,
                    "live_action_executed": False,
                    "browser_resumed": False,
                    "debugger_stepped": False,
                    "callframe_evaluated": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("live_callframe_recovered_one_action_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "plan_cross_process_one_action_executor")
        recovery = result["summary"]["live_callframe_recovery"]
        self.assertEqual(recovery["status"], "recovered")
        self.assertTrue(recovery["live_callframe_recovered"])
        self.assertTrue(recovery["one_action_executor_ready_for_review"])
        self.assertFalse(recovery["callframe_evaluated"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_live_callframe_recovery_failure(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_live_callframe_recovery": {
                "recovery": {
                    "status": "blocked",
                    "target_id": "target-review-1",
                    "target_attached": True,
                    "fresh_paused_event_after_attach": False,
                    "callframe_count": 1,
                    "selected_callframe_has_id": True,
                    "live_callframe_recovered": False,
                    "blockers": ["fresh_paused_event_after_attach_required"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_live_callframe_recovery_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "capture_new_paused_event_after_attach")
        self.assertEqual(result["review_required_items"][0]["live_callframe_recovery_diagnostics"]["status"], "blocked")
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])


    def test_review_debugger_artifacts_warns_when_one_action_needs_next_paused_event_capture_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_one_action_execution": {
                "execution": {
                    "status": "executed",
                    "requested_action": "step_over",
                    "method": "Debugger.stepOver",
                    "live_action_executed": True,
                    "debugger_stepped": True,
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_one_action_next_paused_event_capture_plan_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "plan_next_paused_event_capture")
        self.assertEqual(result["summary"]["next_paused_event_capture_plan"]["status"], "unknown")
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_next_paused_event_capture_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_next_paused_event_capture_plan": {
                "plan": {
                    "status": "ready_for_review",
                    "method": "Debugger.stepOver",
                    "requires_next_paused_event_capture": True,
                    "plan_ready_for_review": True,
                    "automatic_capture_supported": False,
                    "capture_window": "after_step_until_next_debugger_paused",
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("next_paused_event_capture_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_next_paused_event_capture_plan")
        plan = result["summary"]["next_paused_event_capture_plan"]
        self.assertTrue(plan["plan_ready_for_review"])
        self.assertTrue(plan["requires_next_paused_event_capture"])
        self.assertFalse(plan["automatic_capture_supported"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_pre_action_orchestration_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_pre_action_subscribe_and_action": {
                "orchestration": {
                    "status": "ready_for_review",
                    "method": "Debugger.stepOver",
                    "pre_action_event_subscribed": False,
                    "action_sent_after_subscription": False,
                    "paused_event_captured": False,
                    "captured_event_count": 0,
                    "callframe_count": 0,
                    "live_callframe_recovery_ready": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("pre_action_subscribe_and_action_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_pre_action_subscribe_and_action")
        orchestration = result["summary"]["pre_action_subscribe_and_action"]
        self.assertEqual(orchestration["status"], "ready_for_review")
        self.assertFalse(orchestration["paused_event_captured"])

    def test_review_debugger_artifacts_warns_for_captured_pre_action_orchestration(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_pre_action_subscribe_and_action": {
                "orchestration": {
                    "status": "captured",
                    "method": "Debugger.stepOver",
                    "pre_action_event_subscribed": True,
                    "action_sent_after_subscription": True,
                    "live_action_executed": True,
                    "paused_event_captured": True,
                    "captured_event_count": 1,
                    "callframe_count": 1,
                    "live_callframe_recovery_ready": True,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("pre_action_subscribe_and_action_captured_checkpoint_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "checkpoint_cross_process_continuation")
        orchestration = result["summary"]["pre_action_subscribe_and_action"]
        self.assertTrue(orchestration["pre_action_event_subscribed"])
        self.assertTrue(orchestration["action_sent_after_subscription"])
        self.assertTrue(orchestration["paused_event_captured"])
        self.assertEqual(orchestration["callframe_count"], 1)

    def test_review_debugger_artifacts_warns_for_multi_step_continuation_workflow_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_continuation_workflow": {
                "workflow": {
                    "status": "ready_for_review",
                    "workflow_id": "workflow-review-1",
                    "planned_step_count": 2,
                    "max_planned_steps": 2,
                    "execute_at_most_one_action_per_review": True,
                    "manual_checkpoint_required_after_each_step": True,
                    "automatic_loop": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("multi_step_continuation_workflow_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_multi_step_continuation_workflow")
        workflow = result["summary"]["multi_step_continuation_workflow"]
        self.assertEqual(workflow["status"], "ready_for_review")
        self.assertEqual(workflow["planned_step_count"], 2)
        self.assertTrue(workflow["execute_at_most_one_action_per_review"])
        self.assertFalse(workflow["automatic_loop"])
        self.assertTrue(result["review_required_items"][0]["multi_step_continuation_workflow_diagnostics"]["manual_checkpoint_required_after_each_step"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_multi_step_continuation_execution_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_continuation_execution": {
                "execution": {
                    "status": "ready_for_review",
                    "workflow_id": "workflow-exec-review-1",
                    "selected_step_index": 1,
                    "selected_method": "Debugger.stepOver",
                    "multi_step_iteration_executed": False,
                    "automatic_loop": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("multi_step_continuation_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_multi_step_continuation_iteration")
        execution = result["summary"]["multi_step_continuation_execution"]
        self.assertEqual(execution["status"], "ready_for_review")
        self.assertEqual(execution["selected_method"], "Debugger.stepOver")
        self.assertFalse(execution["automatic_loop"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_multi_step_continuation_execution_checkpoint(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_continuation_execution": {
                "execution": {
                    "status": "executed",
                    "workflow_id": "workflow-exec-review-2",
                    "selected_step_index": 1,
                    "selected_method": "Debugger.stepOver",
                    "paused_event_captured": True,
                    "manual_checkpoint_required_after_step": True,
                    "multi_step_iteration_executed": True,
                    "automatic_loop": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("multi_step_continuation_execution_checkpoint_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "checkpoint_cross_process_continuation")
        self.assertTrue(result["review_required_items"][0]["multi_step_continuation_execution_diagnostics"]["manual_checkpoint_required_after_step"])

    def test_review_debugger_artifacts_blocks_multi_step_continuation_workflow(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_continuation_workflow": {
                "workflow": {
                    "status": "blocked",
                    "planned_step_count": 0,
                    "blockers": ["planned_actions_required"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_multi_step_continuation_workflow_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_multi_step_continuation_workflow_blockers")

    def test_review_debugger_artifacts_warns_for_multi_step_loop_plan_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_loop_plan": {
                "loop_plan": {
                    "status": "ready_for_review",
                    "loop_id": "loop-review-1",
                    "workflow_id": "workflow-review-1",
                    "completed_iteration_count": 1,
                    "remaining_iteration_count": 1,
                    "planned_iteration_count": 1,
                    "ready_for_review": True,
                    "readiness": {
                        "next_loop_iteration_reviewable": True,
                        "automatic_multi_step_loop_supported": False,
                        "automatic_queue_advance_supported": False,
                    },
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("multi_step_loop_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_next_paused_session_loop_iteration")
        loop_plan = result["summary"]["multi_step_loop_plan"]
        self.assertTrue(loop_plan["ready_for_review"])
        self.assertTrue(loop_plan["next_iteration_reviewable"])
        self.assertFalse(loop_plan["automatic_multi_step_loop_supported"])
        self.assertTrue(result["review_required_items"][0]["multi_step_loop_plan_diagnostics"]["next_iteration_reviewable"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_multi_step_loop_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_loop_plan": {
                "loop_plan": {
                    "status": "blocked",
                    "blockers": ["followup_checkpoint_required"],
                    "ready_for_review": False,
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_multi_step_loop_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_multi_step_loop_plan_blockers")
        self.assertFalse(result["summary"]["multi_step_loop_plan"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_multi_step_loop_execution_checkpoint(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_loop_execution": {
                "execution": {
                    "status": "executed",
                    "loop_id": "loop-exec-review-1",
                    "workflow_id": "workflow-exec-review-1",
                    "selected_step_index": 2,
                    "selected_method": "Debugger.stepOver",
                    "executor_artifact": "workspace/paused-session-multi-step-continuation-execution.json",
                    "paused_event_captured": True,
                    "manual_checkpoint_required_after_iteration": True,
                    "multi_step_loop_iteration_executed": True,
                    "loop_advanced": False,
                    "queue_advanced": False,
                    "automatic_multi_step_loop": False,
                    "automatic_wrapper_continuation": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("multi_step_loop_execution_checkpoint_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "checkpoint_loop_iteration_captured_pause")
        loop_execution = result["summary"]["multi_step_loop_execution"]
        self.assertTrue(loop_execution["multi_step_loop_iteration_executed"])
        self.assertFalse(loop_execution["loop_advanced"])
        self.assertFalse(loop_execution["queue_advanced"])
        self.assertFalse(loop_execution["automatic_multi_step_loop"])
        self.assertTrue(result["review_required_items"][0]["multi_step_loop_execution_diagnostics"]["multi_step_loop_iteration_executed"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_readiness_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_readiness": {
                "status": "ready_for_review",
                "ready_for_review": True,
                "automation_executor_implemented": False,
                "automatic_multi_step_loop_supported": False,
                "candidate_iteration_count": 2,
                "max_automatic_iterations": 2,
                "next_action": "review_future_bounded_automatic_loop_executor_contract",
                "blockers": [],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_readiness_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_future_bounded_automatic_loop_executor_contract")
        readiness = result["summary"]["automatic_loop_readiness"]
        self.assertTrue(readiness["ready_for_review"])
        self.assertFalse(readiness["automation_executor_implemented"])
        self.assertFalse(readiness["automatic_multi_step_loop_supported"])
        self.assertEqual(readiness["candidate_iteration_count"], 2)
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_readiness(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_readiness": {
                "status": "blocked",
                "ready_for_review": False,
                "blockers": ["multi_step_loop_plan_required"],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_readiness_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_readiness_blockers")
        self.assertFalse(result["summary"]["automatic_loop_readiness"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_execution_plan_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_execution_plan": {
                "status": "ready_for_review",
                "ready_for_review": True,
                "execution_plan_ready_for_review": True,
                "planned_iteration_count": 2,
                "max_planned_iterations": 2,
                "future_executor_contract": {"implemented": False},
                "next_action": "review_future_bounded_automatic_loop_executor_plan",
                "blockers": [],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_execution_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_future_bounded_automatic_loop_executor_plan")
        execution_plan = result["summary"]["automatic_loop_execution_plan"]
        self.assertTrue(execution_plan["ready_for_review"])
        self.assertTrue(execution_plan["execution_plan_ready_for_review"])
        self.assertEqual(execution_plan["planned_iteration_count"], 2)
        self.assertFalse(execution_plan["future_executor_implemented"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_execution_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_execution_plan": {
                "status": "blocked",
                "ready_for_review": False,
                "blockers": ["automatic_loop_readiness_required"],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_execution_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_execution_plan_blockers")
        self.assertFalse(result["summary"]["automatic_loop_execution_plan"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_executor_preflight_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_executor_preflight": {
                "status": "ready_for_review",
                "ready_for_review": True,
                "executor_preflight_ready_for_review": True,
                "preflight_iteration_count": 2,
                "max_preflight_iterations": 2,
                "executor_input_gates": {"ready_to_execute_now": False},
                "future_executor_contract": {"implemented": False},
                "next_action": "review_future_bounded_automatic_loop_executor_preflight",
                "blockers": [],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_executor_preflight_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_future_bounded_automatic_loop_executor_preflight")
        preflight = result["summary"]["automatic_loop_executor_preflight"]
        self.assertTrue(preflight["ready_for_review"])
        self.assertTrue(preflight["executor_preflight_ready_for_review"])
        self.assertFalse(preflight["ready_to_execute_now"])
        self.assertEqual(preflight["preflight_iteration_count"], 2)
        self.assertFalse(preflight["future_executor_implemented"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_executor_preflight(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_executor_preflight": {
                "status": "blocked",
                "ready_for_review": False,
                "blockers": ["automatic_loop_execution_plan_required"],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_executor_preflight_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_executor_preflight_blockers")
        self.assertFalse(result["summary"]["automatic_loop_executor_preflight"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_executor_approval_plan_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_executor_approval_plan": {
                "status": "ready_for_review",
                "ready_for_review": True,
                "approval_plan_ready_for_review": True,
                "approved_iteration_count": 2,
                "max_approved_iterations": 2,
                "executor_input_gates": {
                    "ready_to_execute_now": False,
                    "approval_recorded": False,
                },
                "transaction_plan": {
                    "transaction_started": False,
                    "journal_written_now": False,
                },
                "future_executor_contract": {"implemented": False},
                "next_action": "review_future_bounded_automatic_loop_executor_approval_transaction",
                "blockers": [],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_executor_approval_plan_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_future_bounded_automatic_loop_executor_approval_transaction")
        approval = result["summary"]["automatic_loop_executor_approval_plan"]
        self.assertTrue(approval["ready_for_review"])
        self.assertTrue(approval["approval_plan_ready_for_review"])
        self.assertFalse(approval["ready_to_execute_now"])
        self.assertFalse(approval["approval_recorded"])
        self.assertFalse(approval["transaction_started"])
        self.assertFalse(approval["journal_written"])
        self.assertEqual(approval["approved_iteration_count"], 2)
        self.assertFalse(approval["future_executor_implemented"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_executor_approval_plan(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_executor_approval_plan": {
                "status": "blocked",
                "ready_for_review": False,
                "blockers": ["automatic_loop_executor_preflight_required"],
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_executor_approval_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_executor_approval_plan_blockers")
        self.assertFalse(result["summary"]["automatic_loop_executor_approval_plan"]["ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_execution_result_checkpoint(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_execution_result": {
                "execution": {
                    "status": "executed",
                    "transaction_id": "automatic-loop-executor-transaction:preflight-1",
                    "journal_id": "automatic-loop-journal-1",
                    "executed_iteration_count": 1,
                    "checkpoint_required": True,
                    "automatic_loop_executed": True,
                    "automatic_loop_one_iteration_executed": True,
                    "loop_advanced": False,
                    "queue_advanced": False,
                    "long_lived_session_managed": False,
                    "blockers": [],
                    "side_effect_policy": {
                        "automatic_loop_executor": True,
                        "automatic_loop_one_iteration_executed": True,
                        "automatic_multi_step_loop": False,
                        "bounded_one_iteration_only": True,
                        "calls_mcp": False,
                        "mobile_runtime_used": False,
                    },
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_execution_checkpoint_required", result["warnings"])
        self.assertEqual(result["next_action"], "checkpoint_paused_session_automatic_loop_execution")
        execution = result["summary"]["automatic_loop_execution_result"]
        self.assertEqual(execution["executed_iteration_count"], 1)
        self.assertTrue(execution["automatic_loop_executed"])
        self.assertTrue(execution["automatic_loop_one_iteration_executed"])
        self.assertTrue(execution["checkpoint_required"])
        self.assertFalse(execution["loop_advanced"])
        self.assertFalse(execution["queue_advanced"])
        self.assertFalse(execution["calls_mcp"])
        self.assertFalse(execution["mobile_runtime_used"])
        self.assertTrue(result["review_required_items"][0]["automatic_loop_execution_result_diagnostics"]["automatic_loop_one_iteration_executed"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_execution_result(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_execution_result": {
                "execution": {
                    "status": "blocked",
                    "executed_iteration_count": 0,
                    "checkpoint_required": False,
                    "automatic_loop_executed": False,
                    "automatic_loop_one_iteration_executed": False,
                    "loop_advanced": False,
                    "queue_advanced": False,
                    "blockers": ["bounded_executor_gate_required"],
                    "side_effect_policy": {
                        "automatic_loop_executor": True,
                        "automatic_loop_one_iteration_executed": False,
                        "automatic_multi_step_loop": False,
                        "calls_mcp": False,
                        "mobile_runtime_used": False,
                    },
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_execution_result_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_execution_result_blockers")
        execution = result["summary"]["automatic_loop_execution_result"]
        self.assertEqual(execution["blockers"], ["bounded_executor_gate_required"])
        self.assertFalse(execution["automatic_loop_executed"])
        self.assertFalse(execution["automatic_loop_one_iteration_executed"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_automatic_loop_followup_checkpoint(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_followup_checkpoint": {
                "checkpoint": {
                    "status": "blocked",
                    "ready_for_review": False,
                    "transaction_id": "automatic-loop-executor-transaction:followup-1",
                    "checkpoint_review": {"checkpoint_ready": False},
                    "next_loop_review": {"next_loop_plan_ready": False, "next_iteration_reviewable": False},
                    "blockers": ["automatic_loop_followup_checkpoint_required"],
                    "side_effect_policy": {
                        "checkpoint_written": False,
                        "loop_advanced": False,
                        "queue_advanced": False,
                        "calls_mcp": False,
                        "mobile_runtime_used": False,
                    },
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_automatic_loop_followup_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_paused_session_automatic_loop_followup_checkpoint_blockers")
        followup = result["summary"]["automatic_loop_followup_checkpoint"]
        self.assertEqual(followup["status"], "blocked")
        self.assertFalse(followup["ready_for_review"])
        self.assertFalse(followup["checkpoint_ready"])
        self.assertFalse(followup["next_loop_plan_ready"])
        self.assertFalse(followup["next_iteration_reviewable"])
        self.assertFalse(followup["checkpoint_written"])
        self.assertFalse(followup["loop_advanced"])
        self.assertFalse(followup["queue_advanced"])
        self.assertFalse(followup["calls_mcp"])
        self.assertFalse(followup["mobile_runtime_used"])
        diagnostics = result["review_required_items"][0]["automatic_loop_followup_checkpoint_diagnostics"]
        self.assertEqual(diagnostics["blockers"], ["automatic_loop_followup_checkpoint_required"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_warns_for_automatic_loop_followup_checkpoint_next_loop_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_automatic_loop_followup_checkpoint": {
                "checkpoint": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "transaction_id": "automatic-loop-executor-transaction:followup-2",
                    "checkpoint_review": {"checkpoint_ready": True},
                    "next_loop_review": {"next_loop_plan_ready": True, "next_iteration_reviewable": True},
                    "blockers": [],
                    "side_effect_policy": {
                        "checkpoint_written": False,
                        "loop_advanced": False,
                        "queue_advanced": False,
                        "calls_mcp": False,
                        "mobile_runtime_used": False,
                    },
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("automatic_loop_followup_checkpoint_ready_for_next_loop_review", result["warnings"])
        self.assertEqual(result["next_action"], "review_next_paused_session_automatic_loop_iteration")
        followup = result["summary"]["automatic_loop_followup_checkpoint"]
        self.assertEqual(followup["status"], "ready_for_review")
        self.assertTrue(followup["ready_for_review"])
        self.assertTrue(followup["checkpoint_ready"])
        self.assertTrue(followup["next_loop_plan_ready"])
        self.assertTrue(followup["next_iteration_reviewable"])
        self.assertFalse(followup["checkpoint_written"])
        self.assertFalse(followup["loop_advanced"])
        self.assertFalse(followup["queue_advanced"])
        self.assertFalse(followup["calls_mcp"])
        self.assertFalse(followup["mobile_runtime_used"])
        diagnostics = result["review_required_items"][0]["automatic_loop_followup_checkpoint_diagnostics"]
        self.assertTrue(diagnostics["next_loop_plan_ready"])
        self.assertTrue(diagnostics["next_iteration_reviewable"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_multi_step_loop_execution(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_multi_step_loop_execution": {
                "execution": {
                    "status": "blocked",
                    "blockers": ["multi_step_loop_plan_not_ready"],
                    "multi_step_loop_iteration_executed": False,
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_multi_step_loop_execution_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_multi_step_loop_execution_blockers")
        self.assertFalse(result["summary"]["multi_step_loop_execution"]["multi_step_loop_iteration_executed"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_pre_action_orchestration_timeout(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_pre_action_subscribe_and_action": {
                "orchestration": {
                    "status": "timed_out",
                    "method": "Debugger.stepOver",
                    "pre_action_event_subscribed": True,
                    "action_sent_after_subscription": True,
                    "live_action_executed": True,
                    "paused_event_captured": False,
                    "captured_event_count": 0,
                    "callframe_count": 0,
                    "live_callframe_recovery_ready": False,
                    "blockers": ["next_paused_event_capture_timed_out"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_pre_action_subscribe_and_action_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_pre_action_subscribe_and_action_blockers")

    def test_review_debugger_artifacts_warns_for_next_paused_event_capture_execution_review(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_next_paused_event_capture_execution": {
                "execution": {
                    "status": "ready_for_review",
                    "method": "Debugger.stepOver",
                    "debugger_event_subscribed": False,
                    "paused_event_captured": False,
                    "callframe_count": 0,
                    "live_callframe_recovery_ready": False,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("next_paused_event_capture_execution_requires_review", result["warnings"])
        self.assertEqual(result["next_action"], "approve_next_paused_event_capture_execution")
        execution = result["summary"]["next_paused_event_capture_execution"]
        self.assertEqual(execution["status"], "ready_for_review")
        self.assertFalse(execution["paused_event_captured"])

    def test_review_debugger_artifacts_warns_for_captured_next_paused_event(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_next_paused_event_capture_execution": {
                "execution": {
                    "status": "captured",
                    "method": "Debugger.stepOver",
                    "debugger_event_subscribed": True,
                    "paused_event_captured": True,
                    "captured_event_count": 1,
                    "callframe_count": 1,
                    "live_callframe_recovery_ready": True,
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("next_paused_event_captured_continuation_checkpoint_not_observed", result["warnings"])
        self.assertEqual(result["next_action"], "checkpoint_cross_process_continuation")
        execution = result["summary"]["next_paused_event_capture_execution"]
        self.assertTrue(execution["paused_event_captured"])
        self.assertTrue(execution["live_callframe_recovery_ready"])

    def test_review_debugger_artifacts_warns_for_continuation_checkpoint_live_recovery(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_continuation_checkpoint": {
                "checkpoint": {
                    "status": "ready_for_live_callframe_recovery",
                    "paused_event_captured": True,
                    "callframe_count": 1,
                    "selected_callframe_id": "live-cf-3",
                    "manual_checkpoint_required": True,
                    "next_action": "recover_live_callframe_from_captured_pause",
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_continuation_checkpoint_requires_live_callframe_recovery", result["warnings"])
        self.assertEqual(result["next_action"], "recover_live_callframe_from_captured_pause")
        checkpoint = result["summary"]["cross_process_continuation_checkpoint"]
        self.assertTrue(checkpoint["paused_event_captured"])
        self.assertEqual(checkpoint["callframe_count"], 1)
        self.assertTrue(checkpoint["manual_checkpoint_required"])

    def test_review_debugger_artifacts_warns_for_continuation_checkpoint_next_action(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_continuation_checkpoint": {
                "checkpoint": {
                    "status": "ready_for_next_action_review",
                    "paused_event_captured": True,
                    "callframe_count": 1,
                    "selected_callframe_id": "live-cf-4",
                    "live_callframe_recovered": True,
                    "continuation_ready_for_next_action": True,
                    "manual_checkpoint_required": True,
                    "next_action": "plan_next_cross_process_one_action",
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_continuation_checkpoint_ready_for_next_action_review", result["warnings"])
        self.assertEqual(result["next_action"], "plan_multi_step_continuation_workflow")
        checkpoint = result["summary"]["cross_process_continuation_checkpoint"]
        self.assertTrue(checkpoint["continuation_ready_for_next_action"])

    def test_review_debugger_artifacts_blocks_continuation_checkpoint_blocked(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_continuation_checkpoint": {
                "checkpoint": {
                    "status": "blocked",
                    "paused_event_captured": False,
                    "callframe_count": 0,
                    "manual_checkpoint_required": True,
                    "next_action": "inspect_continuation_checkpoint_blockers",
                    "blockers": ["next_paused_event_not_captured"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_cross_process_continuation_checkpoint_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_continuation_checkpoint_blockers")

    def test_review_debugger_artifacts_warns_for_cross_process_one_action_execution_result(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_one_action_execution": {
                "execution": {
                    "status": "executed",
                    "pause_session_id": "one-action-review-1",
                    "requested_action": "evaluate",
                    "method": "Debugger.evaluateOnCallFrame",
                    "target_id": "target-review-1",
                    "attached_session_id": "attached-session-1",
                    "live_callframe_id": "live-cf-1",
                    "live_callframe_recovered": True,
                    "execute_action_requested": True,
                    "review_approved": True,
                    "live_action_executed": True,
                    "browser_resumed": False,
                    "debugger_stepped": False,
                    "callframe_evaluated": True,
                    "cdp_methods": ["Debugger.evaluateOnCallFrame"],
                    "blockers": [],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "warn")
        self.assertIn("cross_process_one_action_executed_review_result", result["warnings"])
        self.assertEqual(result["next_action"], "review_cross_process_one_action_result")
        execution = result["summary"]["cross_process_one_action_execution"]
        self.assertEqual(execution["status"], "executed")
        self.assertTrue(execution["live_action_executed"])
        self.assertTrue(execution["callframe_evaluated"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_cross_process_one_action_failure(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_one_action_execution": {
                "execution": {
                    "status": "failed",
                    "requested_action": "resume",
                    "method": "Debugger.resume",
                    "attached_session_id": "attached-session-1",
                    "live_callframe_id": "live-cf-1",
                    "live_action_executed": False,
                    "browser_resumed": False,
                    "debugger_stepped": False,
                    "callframe_evaluated": False,
                    "blockers": ["cross_process_one_action_failed"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_cross_process_one_action_execution_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "inspect_cross_process_one_action_error")
        self.assertEqual(result["review_required_items"][0]["cross_process_one_action_diagnostics"]["status"], "failed")
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_cross_process_attach_probe_failure(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_attach_probe": {
                "probe": {
                    "status": "blocked",
                    "target_id": "",
                    "attach_attempted": False,
                    "target_attached": False,
                    "target_detached": False,
                    "blockers": ["target_id_required"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_cross_process_attach_probe_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_cross_process_attach_probe_blockers")
        self.assertEqual(result["review_required_items"][0]["cross_process_attach_probe_diagnostics"]["status"], "blocked")
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_review_debugger_artifacts_blocks_cross_process_execution_plan_failure(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        payload = {
            "paused_session_cross_process_execution_plan": {
                "plan": {
                    "status": "blocked",
                    "execution_plan_ready_for_review": False,
                    "cross_process_execution_ready": False,
                    "cross_process_executor_implemented": True,
                    "blockers": ["target_attach_readiness_required"],
                }
            }
        }

        result = tool(json.dumps(payload))

        self.assertEqual(result["status"], "block")
        self.assertIn("paused_session_cross_process_execution_plan_blocked", result["blockers"])
        self.assertEqual(result["next_action"], "resolve_cross_process_execution_plan_blockers")
        self.assertFalse(result["summary"]["cross_process_execution_plan"]["execution_plan_ready_for_review"])

    def test_review_debugger_artifacts_warns_when_no_artifacts_are_present(self) -> None:
        tool = make_review_debugger_artifacts_tool()
        result = tool("{}")

        self.assertEqual(result["status"], "warn")
        self.assertIn("no_debugger_artifacts_provided", result["warnings"])
        self.assertEqual(result["next_action"], "collect_debugger_pause_artifacts_before_review")


    def test_review_debugger_artifacts_reads_artifact_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            payload = {
                "debugger_session": {"session_id": "live-1", "status": "success"},
                "debugger_paused": {"status": "paused"},
                "callframes": [{"functionName": "sign"}],
            }
            (workspace / "debugger-session.json").write_text(json.dumps(payload), encoding="utf-8")

            result = make_review_debugger_artifacts_tool(artifact_root)(debugger_artifacts_ref="workspace_debugger_session")

            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["summary"]["session_id"], "live-1")
            self.assertEqual(result["artifact_input"]["artifact_ref"], "workspace_debugger_session")
            self.assertTrue(result["side_effect_policy"]["read_only"])

    def test_record_automatic_loop_executor_approval_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_paused_session_automatic_loop_executor_approval_tool(artifact_root)
            result = tool(
                approval_plan_json=json.dumps(_ready_automatic_loop_executor_approval_plan()),
                reviewer="alice",
                reason="Ready to approve transaction preflight input.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["approval_recorded"])
            self.assertFalse((artifact_root / "workspace" / "paused-session-automatic-loop-executor-approval-record.json").exists())
            self.assertTrue(result["side_effect_policy"]["dry_run_is_read_only"])
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(result["side_effect_policy"]["automatic_loop_executed"])

    def test_record_automatic_loop_executor_approval_apply_requires_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_paused_session_automatic_loop_executor_approval_tool(artifact_root)
            result = tool(
                approval_plan_json=json.dumps(_ready_automatic_loop_executor_approval_plan()),
                mode="apply",
                write_result=True,
                approve_approval_record=False,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("reviewer_present", result["blockers"])
            self.assertIn("apply_requires_explicit_approval_record", result["blockers"])
            self.assertFalse((artifact_root / "workspace" / "paused-session-automatic-loop-executor-approval-record.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_approval_record"])

    def test_record_automatic_loop_executor_approval_apply_writes_record_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_paused_session_automatic_loop_executor_approval_tool(artifact_root)
            result = tool(
                approval_plan_json=json.dumps(_ready_automatic_loop_executor_approval_plan()),
                reviewer="alice",
                decision="approved",
                reason="Reviewed bounded iterations and transaction gates.",
                mode="apply",
                write_result=True,
                approve_approval_record=True,
                expected_preflight_id="preflight-1",
                metadata_json=json.dumps({"ticket": "DBG-1"}),
            )

            record_path = artifact_root / "workspace" / "paused-session-automatic-loop-executor-approval-record.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["approval_recorded"])
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema_version"], "reverse-deepagent.paused-session-automatic-loop-executor-approval-record.v1")
            self.assertEqual(record["preflight_id"], "preflight-1")
            self.assertTrue(record["executor_input_gates"]["approval_recorded"])
            self.assertFalse(record["executor_input_gates"]["transaction_started"])
            self.assertFalse(record["executor_input_gates"]["journal_written"])
            self.assertEqual(record["metadata"]["ticket"], "DBG-1")
            self.assertTrue(record["side_effect_policy"]["writes_approval_record"])
            self.assertFalse(record["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(record["side_effect_policy"]["automatic_loop_executed"])
            self.assertFalse(record["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(record["side_effect_policy"]["calls_mcp"])
            self.assertFalse(record["side_effect_policy"]["mobile_runtime_used"])

    def test_review_automatic_loop_transaction_preflight_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_review_paused_session_automatic_loop_transaction_preflight_tool(artifact_root)
            result = tool(
                approval_plan_json=json.dumps(_ready_automatic_loop_executor_approval_plan()),
                approval_record_json=json.dumps(_ready_automatic_loop_executor_approval_record()),
                expected_preflight_id="preflight-1",
                metadata_json=json.dumps({"ticket": "DBG-2"}),
            )

            self.assertEqual(result["status"], "ready_for_review")
            self.assertTrue(result["transaction_preflight_ready_for_review"])
            self.assertFalse((artifact_root / "workspace" / "paused-session-automatic-loop-transaction-preflight.json").exists())
            self.assertEqual(result["transaction_plan"]["transaction_id"], "automatic-loop-executor-transaction:preflight-1")
            self.assertFalse(result["transaction_plan"]["transaction_started"])
            self.assertFalse(result["transaction_plan"]["journal_written_now"])
            self.assertFalse(result["transaction_plan"]["ready_to_write_now"])
            self.assertTrue(result["journal_writer_input_gates"]["approval_record_verified"])
            self.assertFalse(result["journal_writer_input_gates"]["journal_written"])
            self.assertEqual(result["planned_journal_entries"][0]["method"], "Debugger.stepOver")
            self.assertEqual(result["metadata"]["ticket"], "DBG-2")
            self.assertTrue(result["side_effect_policy"]["read_only"])
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(result["side_effect_policy"]["transaction_started"])
            self.assertFalse(result["side_effect_policy"]["automatic_loop_executed"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(result["side_effect_policy"]["calls_mcp"])
            self.assertFalse(result["side_effect_policy"]["mobile_runtime_used"])

    def test_review_automatic_loop_transaction_preflight_blocks_unapproved_or_mismatched_record(self) -> None:
        plan = _ready_automatic_loop_executor_approval_plan()
        record = _ready_automatic_loop_executor_approval_record()
        record["decision"] = "rejected"
        record["approved_for_execution"] = False
        record["preflight_id"] = "other-preflight"
        tool = make_review_paused_session_automatic_loop_transaction_preflight_tool()

        result = tool(
            approval_plan_json=json.dumps(plan),
            approval_record_json=json.dumps(record),
            expected_preflight_id="preflight-1",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("approval_record_approved_for_execution", result["blockers"])
        self.assertIn("approval_record_matches_preflight_id", result["blockers"])
        self.assertFalse(result["journal_writer_input_gates"]["approval_record_verified"])
        self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])

    def test_review_automatic_loop_transaction_preflight_reads_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "paused-session-automatic-loop-executor-approval-plan.json").write_text(
                json.dumps(_ready_automatic_loop_executor_approval_plan()),
                encoding="utf-8",
            )
            (workspace / "paused-session-automatic-loop-executor-approval-record.json").write_text(
                json.dumps(_ready_automatic_loop_executor_approval_record()),
                encoding="utf-8",
            )

            result = make_review_paused_session_automatic_loop_transaction_preflight_tool(artifact_root)(
                approval_plan_ref="workspace_paused_session_automatic_loop_executor_approval_plan",
                approval_record_ref="workspace_paused_session_automatic_loop_executor_approval_record",
            )

            self.assertEqual(result["status"], "ready_for_review")
            self.assertEqual(result["metadata"]["approval_plan_read"]["artifact_ref"], "workspace_paused_session_automatic_loop_executor_approval_plan")
            self.assertEqual(result["metadata"]["approval_record_read"]["artifact_ref"], "workspace_paused_session_automatic_loop_executor_approval_record")

    def test_record_automatic_loop_transaction_journal_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_paused_session_automatic_loop_transaction_journal_tool(artifact_root)
            result = tool(
                transaction_preflight_json=json.dumps(_ready_automatic_loop_transaction_preflight()),
                reviewer="alice",
                reason="Journal input reviewed.",
            )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["journal_written"])
            self.assertFalse((artifact_root / "workspace" / "paused-session-automatic-loop-executor-journal.json").exists())
            self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(result["side_effect_policy"]["transaction_started"])
            self.assertFalse(result["side_effect_policy"]["automatic_loop_executed"])
            self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])

    def test_record_automatic_loop_transaction_journal_apply_requires_explicit_gates(self) -> None:
        tool = make_record_paused_session_automatic_loop_transaction_journal_tool()
        result = tool(
            transaction_preflight_json=json.dumps(_ready_automatic_loop_transaction_preflight()),
            mode="apply",
            write_result=True,
            approve_transaction_journal=False,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("reviewer_present", result["blockers"])
        self.assertIn("apply_requires_explicit_transaction_journal", result["blockers"])
        self.assertFalse(result["journal_written"])
        self.assertFalse(result["side_effect_policy"]["writes_transaction_journal"])

    def test_record_automatic_loop_transaction_journal_apply_writes_journal_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            tool = make_record_paused_session_automatic_loop_transaction_journal_tool(artifact_root)
            result = tool(
                transaction_preflight_json=json.dumps(_ready_automatic_loop_transaction_preflight()),
                reviewer="alice",
                reason="Reviewed journal transaction start.",
                mode="apply",
                write_result=True,
                approve_transaction_journal=True,
                expected_transaction_id="automatic-loop-executor-transaction:preflight-1",
                expected_preflight_id="preflight-1",
                metadata_json=json.dumps({"ticket": "DBG-3"}),
            )

            journal_path = artifact_root / "workspace" / "paused-session-automatic-loop-executor-journal.json"
            self.assertEqual(result["status"], "written")
            self.assertTrue(result["journal_written"])
            self.assertTrue(result["transaction_started"])
            self.assertTrue(journal_path.exists())
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual(journal["schema_version"], "reverse-deepagent.paused-session-automatic-loop-transaction-journal.v1")
            self.assertEqual(journal["transaction_id"], "automatic-loop-executor-transaction:preflight-1")
            self.assertTrue(journal["journal_summary"]["journal_written"])
            self.assertFalse(journal["journal_summary"]["automatic_loop_executed"])
            self.assertEqual(journal["journal_entries"][0]["entry_kind"], "transaction_started")
            self.assertEqual(journal["journal_entries"][1]["entry_kind"], "planned_iteration_journaled")
            self.assertFalse(journal["journal_entries"][1]["executed_now"])
            self.assertTrue(journal["executor_input_gates"]["transaction_started"])
            self.assertTrue(journal["executor_input_gates"]["journal_written"])
            self.assertFalse(journal["executor_input_gates"]["automatic_loop_executed"])
            self.assertEqual(journal["metadata"]["ticket"], "DBG-3")
            self.assertTrue(journal["side_effect_policy"]["writes_transaction_journal"])
            self.assertFalse(journal["side_effect_policy"]["automatic_loop_executed"])
            self.assertFalse(journal["side_effect_policy"]["cdp_command_sent"])
            self.assertFalse(journal["side_effect_policy"]["calls_mcp"])
            self.assertFalse(journal["side_effect_policy"]["mobile_runtime_used"])

    def test_record_automatic_loop_transaction_journal_blocks_existing_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "paused-session-automatic-loop-executor-journal.json").write_text(
                json.dumps({"schema_version": "existing"}),
                encoding="utf-8",
            )
            tool = make_record_paused_session_automatic_loop_transaction_journal_tool(artifact_root)
            result = tool(
                transaction_preflight_json=json.dumps(_ready_automatic_loop_transaction_preflight()),
                reviewer="alice",
                mode="apply",
                write_result=True,
                approve_transaction_journal=True,
            )

            self.assertEqual(result["status"], "blocked")
            self.assertIn("journal_file_not_already_present", result["blockers"])
            self.assertFalse(result["journal_written"])
            self.assertEqual(json.loads((workspace / "paused-session-automatic-loop-executor-journal.json").read_text(encoding="utf-8"))["schema_version"], "existing")

    def test_record_automatic_loop_transaction_journal_reads_artifact_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "paused-session-automatic-loop-transaction-preflight.json").write_text(
                json.dumps(_ready_automatic_loop_transaction_preflight()),
                encoding="utf-8",
            )
            result = make_record_paused_session_automatic_loop_transaction_journal_tool(artifact_root)(
                transaction_preflight_ref="workspace_paused_session_automatic_loop_transaction_preflight",
                reviewer="alice",
            )

            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["metadata"]["artifact_read"]["artifact_ref"], "workspace_paused_session_automatic_loop_transaction_preflight")

    def test_review_automatic_loop_bounded_executor_gate_is_read_only(self) -> None:
        tool = make_review_paused_session_automatic_loop_bounded_executor_gate_tool()
        result = tool(
            transaction_journal_json=json.dumps(_ready_automatic_loop_transaction_journal()),
            expected_transaction_id="automatic-loop-executor-transaction:preflight-1",
            max_iterations=1,
        )

        self.assertEqual(result["status"], "ready_for_review")
        self.assertTrue(result["bounded_executor_gate_ready_for_review"])
        self.assertFalse(result["ready_to_execute_now"])
        self.assertFalse(result["automatic_loop_executed"])
        self.assertEqual(result["bounded_executor_input"]["max_iterations"], 1)
        self.assertEqual(result["future_executor_contract"]["executor_name"], "execute_paused_session_automatic_loop")
        self.assertFalse(result["future_executor_contract"]["implemented"])
        self.assertEqual(result["future_executor_contract"]["result_contract"]["artifact"], "workspace/paused-session-automatic-loop-execution-result.json")
        self.assertFalse(result["side_effect_policy"]["writes_artifact"])
        self.assertFalse(result["side_effect_policy"]["cdp_command_sent"])
        self.assertFalse(result["side_effect_policy"]["calls_mcp"])
        self.assertFalse(result["side_effect_policy"]["mobile_runtime_used"])

    def test_review_automatic_loop_bounded_executor_gate_blocks_bad_journal(self) -> None:
        journal = _ready_automatic_loop_transaction_journal()
        journal["journal_written"] = False
        journal["side_effect_policy"]["automatic_loop_executed"] = True
        result = make_review_paused_session_automatic_loop_bounded_executor_gate_tool()(
            transaction_journal_json=json.dumps(journal),
            max_iterations=2,
        )

        self.assertEqual(result["status"], "blocked")
        self.assertIn("transaction_journal_written", result["blockers"])
        self.assertIn("journal_not_already_executed", result["blockers"])
        self.assertIn("max_iterations_within_planned_entries", result["blockers"])
        self.assertFalse(result["bounded_executor_gate_ready_for_review"])
        self.assertFalse(result["side_effect_policy"]["automatic_loop_executed"])

    def test_review_automatic_loop_bounded_executor_gate_reads_artifact_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact_root = Path(tmp) / "artifacts"
            workspace = artifact_root / "workspace"
            workspace.mkdir(parents=True)
            (workspace / "paused-session-automatic-loop-executor-journal.json").write_text(
                json.dumps(_ready_automatic_loop_transaction_journal()),
                encoding="utf-8",
            )
            result = make_review_paused_session_automatic_loop_bounded_executor_gate_tool(artifact_root)(
                transaction_journal_ref="workspace_paused_session_automatic_loop_executor_journal",
            )

            self.assertEqual(result["status"], "ready_for_review")
            self.assertEqual(result["metadata"]["artifact_read"]["artifact_ref"], "workspace_paused_session_automatic_loop_executor_journal")

    def test_build_debugger_subagent_exposes_review_and_approval_record_tools(self) -> None:
        subagent = build_debugger_subagent()

        self.assertEqual(subagent["name"], DEBUGGER_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], DEBUGGER_SUBAGENT_DESCRIPTION)
        self.assertIn("Debugger Subagent", subagent["system_prompt"])
        tool_names = {tool.__name__ for tool in subagent["tools"]}
        self.assertEqual(
            tool_names,
            {
                "read_workspace_artifact",
                "review_debugger_artifacts",
                "record_paused_session_automatic_loop_executor_approval",
                "review_paused_session_automatic_loop_transaction_preflight",
                "record_paused_session_automatic_loop_transaction_journal",
                "review_paused_session_automatic_loop_bounded_executor_gate",
            },
        )

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/debugger.txt"
        self.assertIn("approval record", load_debugger_prompt(path))
        self.assertIn("review_paused_session_automatic_loop_transaction_preflight", load_debugger_prompt(path))
        self.assertIn("record_paused_session_automatic_loop_transaction_journal", load_debugger_prompt(path))
        self.assertIn("review_paused_session_automatic_loop_bounded_executor_gate", load_debugger_prompt(path))
        self.assertIn("preflight-only", load_debugger_prompt(path))

    def test_default_agent_includes_debugger_before_timeline(self) -> None:
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
        self.assertIn("debugger", names)
        self.assertLess(names.index("debugger"), names.index("timeline"))


if __name__ == "__main__":
    unittest.main()
