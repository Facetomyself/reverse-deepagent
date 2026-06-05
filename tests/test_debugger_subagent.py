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

    def test_review_debugger_artifacts_warns_for_attach_ready_without_cross_process_executor(self) -> None:
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
        self.assertIn("target_attach_ready_but_cross_process_execution_not_implemented", result["warnings"])
        self.assertEqual(result["next_action"], "review_target_attach_plan_before_cross_process_continuation_executor")
        readiness = result["summary"]["target_attach_readiness"]
        self.assertTrue(readiness["target_attach_readiness_proven"])
        self.assertFalse(readiness["cross_process_execution_ready"])
        self.assertEqual(readiness["expected_url"], "https://example.test/app.js")
        self.assertTrue(readiness["target_id_available"])
        self.assertFalse(readiness["would_attach_cdp_target"])
        self.assertEqual(result["review_required_items"][0]["code"], "target_attach_ready_but_cross_process_execution_not_implemented")
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
                    "cross_process_executor_implemented": False,
                    "cross_process_action_supported": False,
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
        self.assertIn("cross_process_execution_plan_ready_but_executor_not_implemented", result["warnings"])
        self.assertEqual(result["next_action"], "implement_reviewed_cross_process_attach_probe_next")
        plan = result["summary"]["cross_process_execution_plan"]
        self.assertTrue(plan["execution_plan_ready_for_review"])
        self.assertFalse(plan["cross_process_execution_ready"])
        self.assertFalse(plan["cross_process_executor_implemented"])
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
        self.assertIn("attach_probe_ready_but_live_callframe_recovery_not_implemented", result["warnings"])
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
                    "cross_process_executor_implemented": False,
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
