import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class DeepAgentDeliverySmokeTests(unittest.TestCase):
    def test_deepagent_delivery_smoke_generates_rebuild_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_deepagent_delivery_smoke.py"),
                    "--task-text",
                    "https://example.com/search 找 sign 入口，并生成纯算 replay 交付包",
                    "--artifact-root",
                    str(Path(tmpdir) / "artifacts"),
                ],
                check=True,
                text=True,
                capture_output=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            delivery = payload["delivery_result"]
            self.assertEqual(delivery["status"], "success")
            self.assertTrue(delivery["rebuild_plan"]["ready"])
            self.assertIn("ToolMessage", payload["message_types"])
            self.assertTrue(Path(delivery["generated_files"]["rebuild_plan"]).exists())
            self.assertTrue(Path(delivery["generated_files"]["sign_rebuild"]).exists())
            self.assertTrue(Path(delivery["generated_files"]["replay_demo"]).exists())
            self.assertTrue(Path(delivery["generated_files"]["scrapy_middleware"]).exists())
            self.assertEqual(payload["final_text"], "rebuild delivery completed")


if __name__ == "__main__":
    unittest.main()
