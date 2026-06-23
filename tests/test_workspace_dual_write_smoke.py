import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.workspace_dual_write_smoke import run_workspace_dual_write_pilot_smoke


class WorkspaceDualWritePilotSmokeTests(unittest.TestCase):
    def test_smoke_runs_pipeline_and_records_verified_pilot_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"

            payload = run_workspace_dual_write_pilot_smoke(artifact_root=root, artifact_keys=["workspace_task_card"])

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-smoke.v1")
            self.assertEqual(payload["runtime"], "mock")
            self.assertEqual(payload["selected_artifact_keys"], ["workspace_task_card"])
            self.assertEqual(payload["pipeline"]["final_status"], "success")
            self.assertTrue((root / "workspace" / "workspace-dual-write-plan.json").exists())
            self.assertTrue((root / "workspace" / "workspace-dual-write-pilot-result.json").exists())
            self.assertTrue((root / "workspace" / "task-card.json").exists())
            self.assertTrue((root / "workspace" / "recon" / "task-card.json").exists())
            self.assertFalse((root / "workspace" / "recon" / "route-decision.json").exists())
            self.assertEqual(payload["workflow"]["status"], "verified")
            self.assertEqual(payload["workflow"]["summary"]["pilot_result_status"], "verified")
            self.assertEqual(payload["workflow"]["pilot_result"]["summary"]["verified_candidate_count"], 1)
            self.assertFalse(payload["side_effect_boundary"]["starts_browser"])
            self.assertFalse(payload["side_effect_boundary"]["calls_mcp"])
            self.assertFalse(payload["side_effect_boundary"]["changes_canonical_paths"])
            self.assertFalse(payload["side_effect_boundary"]["migrates_paths"])

    def test_module_cli_outputs_json_and_supports_read_only_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reverse_deepagent.workspace_dual_write_smoke",
                    "--artifact-root",
                    str(root),
                    "--artifact-keys",
                    "workspace_task_card",
                    "--no-write-result",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["workflow"]["status"], "verified")
            self.assertTrue((root / "workspace" / "workspace-dual-write-plan.json").exists())
            self.assertFalse((root / "workspace" / "workspace-dual-write-pilot-result.json").exists())
            self.assertTrue(payload["workflow"]["side_effect_policy"]["read_only"])
            self.assertFalse(payload["workflow"]["side_effect_policy"]["artifacts_written"])


if __name__ == "__main__":
    unittest.main()
