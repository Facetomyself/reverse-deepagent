import unittest
from pathlib import Path

from reverse_deepagent.agent import build_reverse_agent
from reverse_deepagent.subagents.browser_runtime import (
    BROWSER_RUNTIME_SUBAGENT_DESCRIPTION,
    BROWSER_RUNTIME_SUBAGENT_NAME,
    build_browser_runtime_subagent,
    load_browser_runtime_prompt,
)
from reverse_deepagent.runtime.base import BrowserSessionInfo, RuntimeExportBundle, WebReverseRuntime
from reverse_deepagent.schemas import ProtectionResult, ReconResult, RouterResult, TaskCard
from reverse_deepagent.tools.browser_tools import (
    make_browser_provider_matrix_tool,
    make_describe_browser_provider_tool,
)


class DummyRuntime(WebReverseRuntime):
    def ensure_browser_session(self) -> BrowserSessionInfo:
        return BrowserSessionInfo(healthy=True, pages=[])

    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        raise NotImplementedError

    def apply_minimal_protection(self, protection_name: str, context: dict | None = None) -> ProtectionResult:
        raise NotImplementedError

    def export_reverse_artifacts(self, final_result=None) -> RuntimeExportBundle:
        return RuntimeExportBundle(final_result=final_result)


class ToolFriendlyFakeModel:
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # noqa: D401, ANN001
        return self


class BrowserRuntimeSubagentTests(unittest.TestCase):
    def test_browser_provider_matrix_tool_is_metadata_only(self) -> None:
        tool = make_browser_provider_matrix_tool()
        payload = tool()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["entry_point_group"], "reverse_deepagent.browser_providers")
        self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
        self.assertFalse(payload["side_effect_policy"]["launch_smoke_requested"])
        by_provider = {item["provider_id"]: item for item in payload["providers"]}
        self.assertIn("playwright-chromium", by_provider)
        self.assertIn("cloakbrowser", by_provider)
        self.assertIn("remote-cdp", by_provider)

    def test_describe_browser_provider_tool_resolves_alias_without_factory(self) -> None:
        tool = make_describe_browser_provider_tool()
        payload = tool("cloak")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["provider_id"], "cloakbrowser")
        self.assertEqual(payload["requested_provider_id"], "cloak")
        self.assertIn("cloak-browser", payload["aliases"])
        self.assertTrue(payload["capability_matrix"]["supports_stealth"])
        self.assertFalse(payload["side_effect_policy"]["provider_factory_invoked"])
        self.assertFalse(payload["side_effect_policy"]["browser_started"])
        self.assertFalse(payload["side_effect_policy"]["mcp_used"])

    def test_describe_browser_provider_tool_reports_unknown_provider(self) -> None:
        tool = make_describe_browser_provider_tool()
        payload = tool("missing-browser")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["provider_id"], "missing-browser")
        self.assertIn("Unsupported browser provider", payload["error"])
        self.assertIn("playwright-chromium", payload["registered_provider_ids"])
        self.assertFalse(payload["side_effect_policy"]["provider_factory_invoked"])

    def test_browser_runtime_subagent_exposes_provider_and_session_tools(self) -> None:
        subagent = build_browser_runtime_subagent(DummyRuntime())

        self.assertEqual(subagent["name"], BROWSER_RUNTIME_SUBAGENT_NAME)
        self.assertEqual(subagent["description"], BROWSER_RUNTIME_SUBAGENT_DESCRIPTION)
        self.assertIn("Browser Runtime Subagent", subagent["system_prompt"])
        tool_names = {tool.__name__ for tool in subagent["tools"]}
        self.assertEqual(tool_names, {"list_browser_providers", "describe_browser_provider", "ensure_browser_session"})

    def test_browser_runtime_subagent_without_runtime_keeps_metadata_tools_only(self) -> None:
        subagent = build_browser_runtime_subagent()
        tool_names = {tool.__name__ for tool in subagent["tools"]}
        self.assertEqual(tool_names, {"list_browser_providers", "describe_browser_provider"})

    def test_prompt_loader_supports_custom_path(self) -> None:
        path = Path(__file__).resolve().parents[1] / "src/reverse_deepagent/prompts/browser_runtime.txt"
        self.assertIn("metadata-only", load_browser_runtime_prompt(path))

    def test_default_agent_includes_browser_runtime_when_runtime_is_provided(self) -> None:
        captured = {}

        def fake_create_deep_agent(**kwargs):
            captured.update(kwargs)
            return {"captured": kwargs}

        import reverse_deepagent.agent as agent_module

        original = agent_module.create_deep_agent
        try:
            agent_module.create_deep_agent = fake_create_deep_agent
            build_reverse_agent(model=ToolFriendlyFakeModel(), runtime=DummyRuntime())
        finally:
            agent_module.create_deep_agent = original

        names = [item["name"] for item in captured["subagents"]]
        self.assertIn("browser_runtime", names)
        self.assertLess(names.index("browser_runtime"), names.index("web_recon"))


if __name__ == "__main__":
    unittest.main()
