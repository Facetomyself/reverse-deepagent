import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.fixture_smoke import main_fixture_smoke

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

    def test_fixture_smoke_warns_for_deprecated_mcp_alias(self) -> None:
        class FakeProfile:
            value = "default"

        class FakeFixture:
            base_url = "http://127.0.0.1:8765"
            profile = FakeProfile()

            def close(self) -> None:
                pass

        class FakeOutput:
            def model_dump(self, mode: str = "json", exclude_none: bool = True) -> dict[str, object]:
                return {"final_result": {"status": "failed"}, "artifacts": {}}

        stdout = StringIO()
        stderr = StringIO()
        with patch("reverse_deepagent.fixture_smoke.start_fixture_server", return_value=FakeFixture()):
            with patch("reverse_deepagent.fixture_smoke.run_reverse_pipeline", return_value=FakeOutput()) as run_pipeline:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = main_fixture_smoke(["--runtime", "mcp", "--artifact-root", str(REPO_ROOT / "artifacts/deprecated-fixture-mcp-alias-test")])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["pipeline"]["final_result"]["status"], "failed")
        self.assertIn("legacy-mcp", stderr.getvalue())
        self.assertIn("兼容别名", stderr.getvalue())
        self.assertEqual(run_pipeline.call_args.kwargs["runtime_kind"], "mcp")

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

    def test_fixture_smoke_supports_realistic_web_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            webpack_result = subprocess.run(
                [
                    REVERSE_AGENT_FIXTURE_SMOKE,
                    "--profile",
                    "webpack-minified",
                    "--runtime",
                    "mock",
                    "--artifact-root",
                    str(root / "fixture-smoke-webpack-minified"),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            webpack_payload = json.loads(webpack_result.stdout)
            webpack_pipeline = webpack_payload["pipeline"]
            webpack_plan_path = Path(webpack_pipeline["artifacts"]["workspace_rebuild_plan"])
            webpack_sign_path = Path(webpack_pipeline["artifacts"]["rebuild_sign_rebuild"])
            webpack_plan = json.loads(webpack_plan_path.read_text(encoding="utf-8"))
            webpack_generated = subprocess.run(
                [sys.executable, str(webpack_sign_path)],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()

            token_result = subprocess.run(
                [
                    REVERSE_AGENT_FIXTURE_SMOKE,
                    "--profile",
                    "token-chain",
                    "--runtime",
                    "mock",
                    "--artifact-root",
                    str(root / "fixture-smoke-token-chain"),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            token_payload = json.loads(token_result.stdout)
            token_pipeline = token_payload["pipeline"]
            token_plan_path = Path(token_pipeline["artifacts"]["workspace_rebuild_plan"])
            token_sign_path = Path(token_pipeline["artifacts"]["rebuild_sign_rebuild"])
            token_plan = json.loads(token_plan_path.read_text(encoding="utf-8"))
            token_generated = subprocess.run(
                [sys.executable, str(token_sign_path)],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()

            hybrid_result = subprocess.run(
                [
                    REVERSE_AGENT_FIXTURE_SMOKE,
                    "--profile",
                    "hybrid-context",
                    "--runtime",
                    "mock",
                    "--artifact-root",
                    str(root / "fixture-smoke-hybrid-context"),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            hybrid_payload = json.loads(hybrid_result.stdout)
            hybrid_pipeline = hybrid_payload["pipeline"]
            hybrid_plan_path = Path(hybrid_pipeline["artifacts"]["workspace_rebuild_plan"])
            hybrid_sign_path = Path(hybrid_pipeline["artifacts"]["rebuild_sign_rebuild"])
            hybrid_plan = json.loads(hybrid_plan_path.read_text(encoding="utf-8"))
            hybrid_generated = subprocess.run(
                [sys.executable, str(hybrid_sign_path)],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()

        self.assertEqual(webpack_payload["fixture"]["profile"], "webpack-minified")
        self.assertEqual(webpack_plan["algorithm_strategy"]["id"], "sha256_keyword_timestamp")
        self.assertTrue(webpack_plan["ready"])
        self.assertEqual(webpack_generated, webpack_plan["validation"]["sample_output"]["sign"])

        self.assertEqual(token_payload["fixture"]["profile"], "token-chain")
        self.assertEqual(token_plan["algorithm_strategy"]["id"], "sha256_keyword_timestamp")
        self.assertTrue(token_plan["pure_extraction"]["context_aware_extractable"])
        self.assertEqual(token_plan["pure_extraction"]["runtime_context_binding"]["source"], "sessionStorage.fixture_token")
        self.assertEqual(token_generated, token_plan["validation"]["sample_output"]["sign"])

        self.assertEqual(hybrid_payload["fixture"]["profile"], "hybrid-context")
        self.assertEqual(hybrid_plan["algorithm_strategy"]["id"], "base64_keyword_timestamp")
        self.assertTrue(hybrid_plan["ready"])
        self.assertTrue(hybrid_plan["pure_extraction"]["context_aware_extractable"])
        self.assertFalse(hybrid_plan["pure_extraction"]["multiple_runtime_context_bindings_unsupported"])
        self.assertEqual(hybrid_generated, hybrid_plan["validation"]["sample_output"]["sign"])
        self.assertEqual(
            hybrid_plan["pure_extraction"]["runtime_context_binding_candidates"],
            ["localStorage.fixture_nonce", "cookie.csrf_token"],
        )


if __name__ == "__main__":
    unittest.main()
