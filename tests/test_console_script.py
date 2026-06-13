import json
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.cli import main_demo
from reverse_deepagent.runtime.legacy_mcp import LegacyMcpPluginUnavailableError

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
                # Deprecated alias string kept only to verify compatibility warning behavior.
                exit_code = main_demo(["--runtime", "mcp", "--artifact-root", str(REPO_ROOT / "artifacts/deprecated-mcp-alias-test")])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["final_result"]["status"], "failed")
        self.assertIn("legacy-mcp", stderr.getvalue())
        self.assertIn("兼容别名", stderr.getvalue())
        self.assertEqual(run_pipeline.call_args.kwargs["runtime_kind"], "mcp")

    def test_reverse_agent_demo_attaches_browser_provider_smoke_json(self) -> None:
        class FakeOutput:
            def model_dump(self, mode: str = "json", exclude_none: bool = True) -> dict[str, object]:
                return {"final_result": {"status": "success"}, "artifacts": {"workspace_browser_provider_smoke": "attached"}}

        smoke_payload = {
            "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
            "mode": "metadata-only",
            "ok": True,
            "resolved_provider_id": "playwright-chromium",
            "side_effect_policy": {
                "provider_factories_invoked": False,
                "starts_browser": False,
                "probes_cdp_endpoint": False,
                "calls_mcp": False,
            },
        }
        smoke_path = REPO_ROOT / "artifacts/console-script-browser-provider-smoke-input.json"
        smoke_path.parent.mkdir(parents=True, exist_ok=True)
        smoke_path.write_text(json.dumps(smoke_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        stdout = StringIO()
        stderr = StringIO()
        with patch("reverse_deepagent.cli.run_reverse_pipeline", return_value=FakeOutput()) as run_pipeline:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main_demo(
                    [
                        "--runtime",
                        "mock",
                        "--artifact-root",
                        str(REPO_ROOT / "artifacts/browser-provider-smoke-json-test"),
                        "--browser-provider-smoke-json",
                        str(smoke_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue())["artifacts"]["workspace_browser_provider_smoke"], "attached")
        self.assertEqual(run_pipeline.call_args.kwargs["browser_provider_smoke"], smoke_payload)

    def test_reverse_agent_demo_reports_missing_legacy_mcp_plugin_as_json(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with patch(
            "reverse_deepagent.cli.run_reverse_pipeline",
            side_effect=LegacyMcpPluginUnavailableError("legacy MCP optional backend is not installed"),
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main_demo(["--runtime", "legacy-mcp", "--artifact-root", str(REPO_ROOT / "artifacts/missing-legacy-mcp-plugin-test")])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        payload = json.loads(stderr.getvalue())
        self.assertFalse(payload["ok"])
        self.assertIn("legacy MCP optional backend is not installed", payload["error"])
        self.assertEqual(payload["install_guidance"]["package"], "reverse-deepagent-legacy-mcp")
        self.assertEqual(payload["install_guidance"]["preferred_web_runtime"], "native-web")


if __name__ == "__main__":
    unittest.main()
