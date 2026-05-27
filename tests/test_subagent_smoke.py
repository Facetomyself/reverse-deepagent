import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class DeepAgentSubagentSmokeTests(unittest.TestCase):
    def test_deepagent_subagent_smoke_script_runs_and_delegates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_deepagent_subagent_smoke.py"),
                    "--task-text",
                    "请分析 http://localhost 上 sign 入口并给出一句话结论",
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
            self.assertEqual(payload["task_result"], "general-purpose subagent result")
            self.assertIn("ToolMessage", payload["message_types"])
            self.assertEqual(payload["final_text"], "subagent delegation completed")


if __name__ == "__main__":
    unittest.main()
