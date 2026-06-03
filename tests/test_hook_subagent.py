import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.subagents.hook import HOOK_SUBAGENT_DESCRIPTION, HOOK_SUBAGENT_NAME, build_hook_subagent, load_hook_prompt
from reverse_deepagent.tools.hook_tools import make_review_hook_artifacts_tool


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


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
        self.assertEqual({tool.__name__ for tool in subagent["tools"]}, {"read_workspace_artifact", "review_hook_artifacts"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/hook.txt"
        self.assertIn("read-only hook artifact review", load_hook_prompt(path))

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
