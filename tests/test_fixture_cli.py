import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REVERSE_AGENT_FIXTURE = shutil.which("reverse-agent-fixture") or str(REPO_ROOT / ".venv/bin/reverse-agent-fixture")
REVERSE_AGENT_FIXTURE_SMOKE = shutil.which("reverse-agent-fixture-smoke") or str(REPO_ROOT / ".venv/bin/reverse-agent-fixture-smoke")


class FixtureCliTests(unittest.TestCase):
    def test_fixture_check_command_runs(self) -> None:
        result = subprocess.run(
            [
                REVERSE_AGENT_FIXTURE,
                "--check",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["base_url"].startswith("http://127.0.0.1:"))
        self.assertEqual(payload["profile"], "default")
        self.assertTrue(payload["health"]["ok"])

    def test_fixture_check_command_supports_profile_selection(self) -> None:
        result = subprocess.run(
            [
                REVERSE_AGENT_FIXTURE,
                "--profile",
                "base64",
                "--check",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["profile"], "base64")
        self.assertEqual(payload["health"]["profile"], "base64")

    def test_fixture_smoke_command_runs_with_mock_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    REVERSE_AGENT_FIXTURE_SMOKE,
                    "--runtime",
                    "mock",
                    "--artifact-root",
                    str(Path(tmpdir) / "fixture-smoke-test"),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
        payload = json.loads(result.stdout)
        self.assertTrue(payload["fixture"]["base_url"].startswith("http://127.0.0.1:"))
        self.assertEqual(payload["fixture"]["profile"], "default")
        self.assertEqual(payload["pipeline"]["final_result"]["status"], "success")

    def test_fixture_smoke_command_is_profile_driven_e2e(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    REVERSE_AGENT_FIXTURE_SMOKE,
                    "--profile",
                    "sha256",
                    "--runtime",
                    "mock",
                    "--jsreverser-mcp-command",
                    str(REPO_ROOT / "fake-jsreverser-mcp"),
                    "--artifact-root",
                    str(Path(tmpdir) / "fixture-smoke-profile-test"),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)
            pipeline = payload["pipeline"]
            rebuild_plan_path = Path(pipeline["artifacts"]["workspace_rebuild_plan"])
            sign_rebuild_path = Path(pipeline["artifacts"]["rebuild_sign_rebuild"])
            rebuild_plan = json.loads(rebuild_plan_path.read_text(encoding="utf-8"))
            expected_sign = rebuild_plan["validation"]["sample_output"]["sign"]
            generated = subprocess.run(
                [sys.executable, str(sign_rebuild_path)],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
        self.assertEqual(payload["fixture"]["profile"], "sha256")
        self.assertEqual(pipeline["final_result"]["status"], "success")
        self.assertEqual(rebuild_plan["algorithm_strategy"]["id"], "sha256_keyword_timestamp")
        self.assertEqual(generated, expected_sign)


if __name__ == "__main__":
    unittest.main()
