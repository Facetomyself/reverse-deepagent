import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.adapters.lightweight_web import (
    LightweightCommandResult,
    LightweightWebRuntimeConfig,
    create_lightweight_web_runtime,
)
from reverse_deepagent.cli import main_demo
from reverse_deepagent.coordinator import build_runtime, list_runtime_backends, run_reverse_pipeline
from reverse_deepagent.schemas import ReverseMode, ReverseStage, RouterResult, TaskCard


HTML = '<html><head><script src="/app.js"></script></head><body>fixture</body></html>'
APP_JS = "function buildSign(keyword, timestamp) { return 'sig_' + keyword + '_' + timestamp; }"


def ok_runner(command: list[str], timeout: float) -> LightweightCommandResult:
    return LightweightCommandResult(command=command, ok=True, returncode=0, stdout="Version 1.0")


def fake_http_get(url: str, timeout: float) -> tuple[int, str, str]:
    if url == "https://fixture.test/search":
        return 200, HTML, "text/html"
    if url == "https://fixture.test/app.js":
        return 200, APP_JS, "application/javascript"
    if url.endswith("/json/version"):
        return 200, json.dumps({"Browser": "Chrome/fixture", "webSocketDebuggerUrl": "ws://fixture"}), "application/json"
    if url.endswith("/json/list"):
        return 200, json.dumps([{"id": "page-1", "type": "page", "url": "https://fixture.test/search", "title": "Fixture"}]), "application/json"
    raise OSError(f"unexpected url: {url}")


class LightweightWebBackendTests(unittest.TestCase):
    def test_lightweight_playwright_runtime_collects_static_source_without_live_js(self) -> None:
        runtime = create_lightweight_web_runtime(
            config=LightweightWebRuntimeConfig(
                backend_id="playwright-cli",
                display_name="Playwright CLI Runtime",
                transport="playwright-cli",
                command="playwright",
                command_args=["--version"],
            ),
            command_runner=ok_runner,
            http_getter=fake_http_get,
        )
        task_card = TaskCard(
            target_url_or_file="https://fixture.test/search",
            target_param_or_api="buildSign",
            goal="找到 buildSign 入口",
            boundaries="不登录，不做破坏性操作",
        )
        route = RouterResult(
            selected_mode=ReverseMode.FIND_ENTRY,
            selected_playbook="references/playbooks/find-entry.md",
            initial_stage=ReverseStage.RECON,
            reasoning=["需要源码定位"],
            next_action="delegate_to_web_recon",
        )

        result = runtime.run_web_recon(task_card, route)
        self.assertEqual(result.status.value, "success")
        self.assertTrue(any(item.source == "search_in_sources" for item in result.evidence))
        source_context = next(item for item in result.evidence if item.source == "get_script_source")
        self.assertIn("buildSign", json.dumps(source_context.details, ensure_ascii=False))
        validation = next(item for item in result.evidence if item.source == "function_validation_result")
        self.assertEqual(validation.details["validations"][0]["validation_status"], "partial")
        self.assertFalse(validation.details["validations"][0]["checks"]["runtime_invocation_ok"])
        bundle = runtime.export_reverse_artifacts()
        self.assertEqual(bundle.artifacts[0]["path"], "virtual://exports/session-report.json")
        self.assertEqual(bundle.exports[0]["payload"]["source_count"], 2)

    def test_lightweight_source_cache_is_scoped_by_active_url(self) -> None:
        def multi_page_http_get(url: str, timeout: float) -> tuple[int, str, str]:
            if url == "https://fixture.test/one":
                return 200, '<script src="/one.js"></script>', "text/html"
            if url == "https://fixture.test/two":
                return 200, '<script src="/two.js"></script>', "text/html"
            if url == "https://fixture.test/one.js":
                return 200, "function buildOneSign() { return 'one'; }", "application/javascript"
            if url == "https://fixture.test/two.js":
                return 200, "function buildTwoSign() { return 'two'; }", "application/javascript"
            raise OSError(f"unexpected url: {url}")

        runtime = create_lightweight_web_runtime(
            config=LightweightWebRuntimeConfig(
                backend_id="playwright-cli",
                display_name="Playwright CLI Runtime",
                transport="playwright-cli",
                command="playwright",
                command_args=["--version"],
            ),
            command_runner=ok_runner,
            http_getter=multi_page_http_get,
        )
        bridge = runtime.bridge
        bridge.invoke("new_page", {"url": "https://fixture.test/one"})
        self.assertTrue(bridge.invoke("search_in_sources", {"query": "buildOneSign"})["results"])
        bridge.invoke("navigate_page", {"url": "https://fixture.test/two"})
        self.assertEqual(bridge.invoke("search_in_sources", {"query": "buildOneSign"})["results"], [])
        self.assertTrue(bridge.invoke("search_in_sources", {"query": "buildTwoSign"})["results"])

    def test_chrome_cdp_bridge_probes_existing_endpoint_without_launching_chrome(self) -> None:
        runtime = create_lightweight_web_runtime(
            config=LightweightWebRuntimeConfig(
                backend_id="chrome-cdp",
                display_name="Chrome CDP Runtime",
                transport="chrome-cdp",
                browser_url="http://127.0.0.1:9555",
            ),
            http_getter=fake_http_get,
        )
        capabilities = runtime.describe_capabilities()
        self.assertEqual(capabilities.backend_id, "chrome-cdp")
        self.assertFalse(capabilities.managed_chrome)
        browser = runtime.ensure_browser_session()
        self.assertTrue(browser.healthy)
        self.assertEqual(browser.active_url, "https://fixture.test/search")
        self.assertFalse(browser.details["health"]["probe"]["launch_attempted"])

    def test_default_registry_lists_lightweight_web_backends(self) -> None:
        metadata = {item["backend_id"]: item for item in list_runtime_backends()}
        for backend_id, transport in (
            ("playwright-cli", "playwright-cli"),
            ("chrome-cdp", "chrome-cdp"),
            ("browser-cli", "browser-cli"),
        ):
            self.assertIn(backend_id, metadata)
            self.assertEqual(metadata[backend_id]["target_platforms"], ["web"])
            self.assertEqual(metadata[backend_id]["transport"], transport)
            self.assertTrue(metadata[backend_id]["supports_web_recon"])
            self.assertFalse(metadata[backend_id]["supports_protection_patch"])
            self.assertFalse(metadata[backend_id]["supports_runtime_context"])
            self.assertFalse(metadata[backend_id]["supports_replay_validation"])
            self.assertFalse(metadata[backend_id]["mcp_backed"])

    def test_build_runtime_resolves_lightweight_aliases(self) -> None:
        self.assertEqual(build_runtime("playwright").describe_capabilities().backend_id, "playwright-cli")
        cdp_capabilities = build_runtime("cdp").describe_capabilities()
        browser_cli_capabilities = build_runtime("cli-browser").describe_capabilities()
        self.assertEqual(cdp_capabilities.backend_id, "chrome-cdp")
        self.assertEqual(browser_cli_capabilities.backend_id, "browser-cli")
        self.assertFalse(cdp_capabilities.managed_chrome)
        self.assertFalse(browser_cli_capabilities.managed_chrome)
        self.assertFalse(cdp_capabilities.supports_replay_validation)
        self.assertFalse(browser_cli_capabilities.supports_protection_patch)

    def test_lightweight_protection_attempt_is_structured_failure(self) -> None:
        result = build_runtime("browser-cli").apply_minimal_protection("console.clear")
        self.assertEqual(result.status.value, "failed")
        self.assertEqual(result.next_action, "switch_to_mcp_or_full_browser_runtime")
        self.assertIn("unsupported_lightweight_protection:console.clear", result.applied_actions)

    def test_browser_cli_pipeline_fails_structurally_when_command_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="browser-cli",
            )
            self.assertEqual(output.final_result.status.value, "failed")
            self.assertEqual(output.final_result.next_action, "ensure_browser_session")
            manifest = json.loads(Path(output.artifacts["workspace_backend_artifact_manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["producer_backend_id"], "browser-cli")
            self.assertIn("virtual://exports/session-report.json", {item["path"] for item in manifest["entries"]})

    def test_demo_cli_accepts_lightweight_runtime_and_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main_demo(
                    [
                        "--runtime",
                        "browser-cli",
                        "--browser-cli-command",
                        "reverse-agent-command-that-should-not-exist",
                        "--task-text",
                        "https://example.com/search 找 sign",
                        "--artifact-root",
                        str(Path(tmpdir) / "artifacts"),
                    ]
                )
            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["final_result"]["status"], "failed")
            self.assertEqual(payload["final_result"]["next_action"], "ensure_browser_session")
            self.assertEqual(payload["artifacts"]["workspace_backend_artifact_manifest"].endswith("backend-artifact-manifest.json"), True)


if __name__ == "__main__":
    unittest.main()
