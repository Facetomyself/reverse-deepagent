import json
import shutil
import subprocess
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
