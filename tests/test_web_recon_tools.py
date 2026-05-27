import json
import unittest

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.schemas import ReverseMode, ReverseStage, RouterResult, TaskCard
from reverse_deepagent.tools.browser_tools import make_ensure_browser_session_tool
from reverse_deepagent.tools.recon_tools import make_run_web_recon_tool


class FakeBridge:
    def invoke(self, tool_name: str, params: dict):
        if tool_name == "check_browser_health":
            return {"status": "ok", "connected": True}
        if tool_name == "list_pages":
            return {"pages": [{"pageIdx": 0, "url": "https://example.com/search", "selected": True}]}
        if tool_name == "network_request":
            return {"requests": [{"id": 1, "url": "https://example.com/api/search"}]}
        if tool_name == "search_in_sources":
            return {"results": [{"scriptId": "1", "url": "https://example.com/app.js", "lineNumber": 12}]}
        if tool_name in {"new_page", "navigate_page"}:
            return {"ok": True}
        raise AssertionError(f"unexpected tool {tool_name}")


class WebReconToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = JSReverserRuntime(bridge=FakeBridge())

    def test_ensure_browser_session_tool_returns_jsonable_dict(self) -> None:
        tool = make_ensure_browser_session_tool(self.runtime)
        payload = tool()
        self.assertTrue(payload["healthy"])
        self.assertEqual(payload["page_count"], 1)

    def test_run_web_recon_tool_accepts_json_strings(self) -> None:
        tool = make_run_web_recon_tool(self.runtime)
        task_card = TaskCard(
            target_url_or_file="https://example.com/search",
            target_param_or_api="x-sign",
            goal="找入口",
            boundaries="不登录",
        )
        route = RouterResult(
            selected_mode=ReverseMode.FULL_WORKFLOW,
            selected_playbook="references/playbooks/full-workflow.md",
            initial_stage=ReverseStage.NETWORK,
            reasoning=["测试"],
            next_action="delegate_to_web_recon",
        )
        payload = tool(task_card.model_dump_json(), route.model_dump_json())
        self.assertEqual(payload["next_action"], "move_to_source_analysis")
        self.assertEqual(payload["status"], "success")
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
