import json
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.cli import main_demo

REPO_ROOT = Path(__file__).resolve().parents[1]
REVERSE_AGENT_DEMO = shutil.which("reverse-agent-demo") or str(REPO_ROOT / ".venv/bin/reverse-agent-demo")


class ConsoleScriptTests(unittest.TestCase):
    def test_reverse_agent_demo_console_script_runs(self) -> None:
        result = subprocess.run(
            [
                REVERSE_AGENT_DEMO,
                "--runtime",
                "mock",
                "--artifact-root",
                str(REPO_ROOT / "artifacts/console-script-test"),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["final_result"]["status"], "success")
        self.assertTrue(Path(payload["artifacts"]["json"]).exists())

    def test_reverse_agent_demo_warns_for_deprecated_mcp_alias(self) -> None:
        class FakeOutput:
            def model_dump(self, mode: str = "json", exclude_none: bool = True) -> dict[str, object]:
                return {"final_result": {"status": "failed"}, "artifacts": {}}

        stdout = StringIO()
        stderr = StringIO()
        with patch("reverse_deepagent.cli.run_reverse_pipeline", return_value=FakeOutput()) as run_pipeline:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main_demo(["--runtime", "mcp", "--artifact-root", str(REPO_ROOT / "artifacts/deprecated-mcp-alias-test")])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["final_result"]["status"], "failed")
        self.assertIn("legacy-mcp", stderr.getvalue())
        self.assertIn("兼容别名", stderr.getvalue())
        self.assertEqual(run_pipeline.call_args.kwargs["runtime_kind"], "mcp")


if __name__ == "__main__":
    unittest.main()
