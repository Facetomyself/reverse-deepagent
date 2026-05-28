import unittest
from pathlib import Path

from reverse_deepagent.fixtures.web_sign import FIXTURE_PROFILE_VALUES


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "mcp-integration.yml"


class McpIntegrationWorkflowTests(unittest.TestCase):
    def test_workflow_exposes_continuous_profile_sets_and_artifacts(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("schedule:", workflow)
        self.assertIn("cron:", workflow)
        self.assertIn("profile_set:", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("reverse-agent-mcp/*-smoke.json", workflow)
        self.assertIn("GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("Preflight self-hosted dependencies", workflow)
        self.assertIn("test -x \"$JSREVERSER_MCP_PATH\"", workflow)
        self.assertIn("test -x \"$CHROME_PATH\"", workflow)
        for profile in FIXTURE_PROFILE_VALUES:
            self.assertIn(profile, workflow)
        for profile_set in ("selected", "core", "context", "realistic", "all"):
            self.assertIn(profile_set, workflow)
        self.assertIn("profiles=(webpack-minified token-chain hybrid-context)", workflow)
        self.assertIn("profiles=(context-localstorage context-cookie context-navigator token-chain hybrid-context)", workflow)


if __name__ == "__main__":
    unittest.main()
