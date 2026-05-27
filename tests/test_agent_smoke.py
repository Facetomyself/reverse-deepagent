import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class DeepAgentSmokeTests(unittest.TestCase):
    def test_deepagent_smoke_script_runs_and_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_deepagent_smoke.py"),
                    "--task-text",
                    "http://localhost 找 sign 入口，并给出下一步建议",
                    "--artifact-root",
                    str(Path(tmpdir) / "artifacts"),
                ],
                check=True,
                text=True,
                capture_output=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["message_count"], 4)
            self.assertEqual(payload["route_result"]["selected_mode"], "find-entry")
            self.assertIn("ToolMessage", payload["message_types"])
            self.assertEqual(payload["final_text"], "deepagents invoke completed")


if __name__ == "__main__":
    unittest.main()
