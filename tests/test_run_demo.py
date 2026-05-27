import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class RunDemoScriptTests(unittest.TestCase):
    def test_run_demo_script_generates_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(REPO_ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/run_demo.py"),
                    "--task-text",
                    "https://example.com/search 找 sign 入口，并给出下一步建议",
                    "--artifact-root",
                    tmpdir,
                ],
                check=True,
                text=True,
                capture_output=True,
                env=env,
            )
            payload = json.loads(result.stdout)
            json_path = Path(payload["artifacts"]["json"])
            md_path = Path(payload["artifacts"]["markdown"])
            index_path = Path(payload["artifacts"]["index"])
            task_card_path = Path(payload["artifacts"]["workspace_task_card"])
            route_path = Path(payload["artifacts"]["workspace_route"])
            recon_path = Path(payload["artifacts"]["workspace_recon"])
            final_path = Path(payload["artifacts"]["workspace_final"])
            function_candidates_path = Path(payload["artifacts"]["workspace_function_candidates"])
            function_validations_path = Path(payload["artifacts"]["workspace_function_validations"])
            function_validation_summary_path = Path(payload["artifacts"]["workspace_function_validation_summary"])
            rebuild_plan_path = Path(payload["artifacts"]["workspace_rebuild_plan"])
            sign_rebuild_path = Path(payload["artifacts"]["rebuild_sign_rebuild"])
            replay_demo_path = Path(payload["artifacts"]["rebuild_replay_demo"])
            scrapy_middleware_path = Path(payload["artifacts"]["rebuild_scrapy_middleware"])

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(index_path.exists())
            self.assertTrue(task_card_path.exists())
            self.assertTrue(route_path.exists())
            self.assertTrue(recon_path.exists())
            self.assertTrue(final_path.exists())
            self.assertTrue(function_candidates_path.exists())
            self.assertTrue(function_validations_path.exists())
            self.assertTrue(function_validation_summary_path.exists())
            self.assertTrue(rebuild_plan_path.exists())
            self.assertTrue(sign_rebuild_path.exists())
            self.assertTrue(replay_demo_path.exists())
            self.assertTrue(scrapy_middleware_path.exists())
            self.assertEqual(payload["final_result"]["next_action"], "extract_pure_logic_and_build_replay")


if __name__ == "__main__":
    unittest.main()
