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
