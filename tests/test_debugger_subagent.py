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
from reverse_deepagent.tools.debugger_tools import make_review_debugger_artifacts_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


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

    def test_build_debugger_subagent_exposes_read_only_review_tool(self) -> None:
        subagent = build_debugger_subagent()

        self.assertEqual(subagent["name"], DEBUGGER_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], DEBUGGER_SUBAGENT_DESCRIPTION)
        self.assertIn("Debugger Subagent", subagent["system_prompt"])
        tool_names = {tool.__name__ for tool in subagent["tools"]}
        self.assertEqual(tool_names, {"read_workspace_artifact", "review_debugger_artifacts"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/debugger.txt"
        self.assertIn("read-only debugger artifact review", load_debugger_prompt(path))

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
