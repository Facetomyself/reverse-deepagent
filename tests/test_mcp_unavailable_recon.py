import unittest

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime
from reverse_deepagent.schemas import ReverseMode, ReverseStage, RouterResult, TaskCard


class UnavailableBridge:
    def invoke(self, tool_name: str, params: dict):
        if tool_name == "check_browser_health":
            return {"content": [{"type": "text", "text": "Failed to connect to remote browser: fetch failed"}], "text": "Failed to connect to remote browser: fetch failed"}
        return {"content": [{"type": "text", "text": "Failed to connect to remote browser: fetch failed"}], "text": "Failed to connect to remote browser: fetch failed"}


class McpUnavailableReconTests(unittest.TestCase):
    def test_unavailable_browser_returns_failed_recon(self) -> None:
        runtime = JSReverserRuntime(bridge=UnavailableBridge())
        result = runtime.run_web_recon(
            TaskCard(target_url_or_file="https://example.com/search", target_param_or_api="sign", goal="找入口", boundaries="不登录"),
            RouterResult(selected_mode=ReverseMode.FIND_ENTRY, selected_playbook="references/playbooks/find-entry.md", initial_stage=ReverseStage.NETWORK, next_action="delegate_to_web_recon"),
        )
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.next_action, "ensure_browser_session")


if __name__ == "__main__":
    unittest.main()
