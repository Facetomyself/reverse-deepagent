import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser_provider_smoke import (
    build_launch_command_payload,
    review_browser_provider_smoke_json,
    run_browser_provider_smoke,
)


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"

    def goto(self, url: str) -> None:
        self.url = url

    def title(self) -> str:
        return "Fake Provider Smoke"


class FakeSession:
    def __init__(self) -> None:
        self.page = FakePage()

    def get_active_page(self) -> FakePage:
        return self.page

    def new_page(self, url: str = "about:blank") -> FakePage:
        self.page = FakePage()
        self.page.url = url
        return self.page

    def list_pages(self) -> list[FakePage]:
        return [self.page]


class FakeProvider:
    def __init__(self) -> None:
        self.stopped = False

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id="fake-browser",
            display_name="Fake Browser",
            transport="fake",
            supports_launch=True,
            supports_connect=True,
            supports_cdp=True,
            supports_runtime_eval=True,
            managed_browser=True,
            production_readiness={
                "readiness_tier": "review-required",
                "health_check_mode": "explicit-test-smoke",
                "profile_lifecycle": "temporary-context",
                "session_recovery": "launch-new-session",
                "intended_use": "test-provider",
                "side_effect_boundary": "explicit-smoke-only",
            },
        )

    def is_available(self) -> bool:
        return True

    def start(self) -> FakeSession:
        return FakeSession()

    def stop(self) -> None:
        self.stopped = True


class FakeRuntime:
    browser_provider = FakeProvider()


def fake_provider_factory(**kwargs):  # noqa: ANN001
    return FakeRuntime()


def raising_provider_factory(**kwargs):  # noqa: ANN001
    raise AssertionError("metadata-only smoke must not invoke provider factory")


class BrowserProviderSmokeCliTests(unittest.TestCase):
    def test_metadata_only_smoke_writes_artifact_without_invoking_provider_factory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"

            payload = run_browser_provider_smoke(
                browser="playwright-chromium",
                artifact_root=root,
                provider_factory=raising_provider_factory,
            )

            artifact_path = root / "workspace" / "browser-provider-smoke.json"
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "metadata-only")
            self.assertEqual(payload["artifact_key"], "workspace_browser_provider_smoke")
            self.assertEqual(payload["requested_provider_id"], "playwright-chromium")
            self.assertEqual(payload["resolved_provider_id"], "playwright-chromium")
            self.assertTrue(artifact_path.exists())
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertFalse(payload["side_effect_policy"]["availability_check_requested"])
            self.assertFalse(payload["side_effect_policy"]["launch_smoke_requested"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            written = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(written["schema_version"], "reverse-deepagent.browser-provider-smoke.v1")
            self.assertEqual(written["provider"]["smoke"]["status"], "skipped")

    def test_metadata_only_cloakbrowser_smoke_records_redacted_requested_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"

            payload = run_browser_provider_smoke(
                browser="cloakbrowser",
                artifact_root=root,
                smoke_url="https://example.test/smoke",
                provider_kwargs={
                    "browser_url": "http://user:pass@127.0.0.1:9222",
                    "browser_profile_dir": "/Users/example/private-profile",
                    "browser_headless": False,
                    "browser_humanize": True,
                    "browser_proxy": "http://user:pass@example.test:8080",
                    "browser_geoip": True,
                    "browser_locale": "zh-CN",
                    "browser_timezone": "Asia/Shanghai",
                    "browser_args": ["--load-extension=/Users/example/ext", "--proxy-server=http://user:pass@example.test:8080"],
                    "request_timeout": 12.5,
                },
                provider_factory=raising_provider_factory,
            )

            artifact_path = root / "workspace" / "browser-provider-smoke.json"
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "metadata-only")
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            config = payload["requested_provider_config"]
            self.assertEqual(config, payload["provider"]["requested_provider_config"])
            self.assertEqual(config["provider_id"], "cloakbrowser")
            self.assertTrue(config["connect_mode_requested"])
            self.assertTrue(config["persistent_context_requested"])
            self.assertFalse(config["launch_mode_requested"])
            self.assertEqual(config["browser_url"], "http://127.0.0.1:9222")
            self.assertTrue(config["profile_dir_configured"])
            self.assertEqual(config["profile_dir_name"], "private-profile")
            self.assertFalse(config["headless"])
            self.assertTrue(config["humanize"])
            self.assertTrue(config["proxy_configured"])
            self.assertEqual(config["proxy"], "<configured>")
            self.assertTrue(config["geoip"])
            self.assertEqual(config["locale"], "zh-CN")
            self.assertEqual(config["timezone"], "Asia/Shanghai")
            self.assertEqual(config["browser_args_count"], 2)
            self.assertEqual(config["browser_args"][0], "--load-extension=<redacted-path>")
            self.assertEqual(config["browser_args"][1], "--proxy-server=<redacted>")
            self.assertTrue(config["redaction_safe"])
            self.assertNotIn("user:pass", json.dumps(payload, ensure_ascii=False))
            self.assertNotIn("/Users/example", json.dumps(payload, ensure_ascii=False))
            hint = payload["review_command_hint"]
            self.assertTrue(hint["launch_smoke_required_for_runtime_acceptance"])
            self.assertFalse(hint["current_run_was_launch_smoke"])
            self.assertIn("--launch-browser-smoke", hint["command"])
            self.assertIn("--browser-url", hint["command"])
            self.assertIn("http://127.0.0.1:9222", hint["command"])

            written = json.loads(artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(written["requested_provider_config"], config)

    def test_launch_smoke_writes_verified_provider_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"

            payload = run_browser_provider_smoke(
                browser="fake-browser",
                artifact_root=root,
                smoke_url="https://example.test/smoke",
                launch_browser_smoke=True,
                provider_factory=fake_provider_factory,
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "launch-smoke")
            self.assertEqual(payload["provider"]["smoke"]["status"], "passed")
            self.assertEqual(payload["provider"]["smoke"]["url"], "https://example.test/smoke")
            self.assertTrue(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertTrue(payload["side_effect_policy"]["availability_check_requested"])
            self.assertTrue(payload["side_effect_policy"]["launch_smoke_requested"])
            self.assertTrue(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertEqual(payload["next_action"], "review_browser_provider_launch_smoke_result")

    def test_module_cli_outputs_metadata_only_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reverse_deepagent.browser_provider_smoke",
                    "--browser",
                    "playwright-chromium",
                    "--artifact-root",
                    str(root),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["mode"], "metadata-only")
            self.assertTrue((root / "workspace" / "browser-provider-smoke.json").exists())
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])

    def test_print_launch_command_payload_is_side_effect_free_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"

            payload = build_launch_command_payload(
                browser="cloakbrowser",
                artifact_root=root,
                smoke_url="https://example.test/smoke",
                provider_kwargs={
                    "browser_url": "http://user:pass@127.0.0.1:9222",
                    "browser_profile_dir": "/Users/example/private-profile",
                    "browser_proxy": "http://user:pass@example.test:8080",
                    "browser_locale": "zh-CN",
                    "browser_timezone": "Asia/Shanghai",
                    "browser_args": ["--load-extension=/Users/example/ext", "--proxy-server=http://user:pass@example.test:8080"],
                    "request_timeout": 12.5,
                },
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], "reverse-deepagent.browser-provider-launch-command.v1")
            self.assertEqual(payload["mode"], "print-launch-command")
            self.assertFalse(payload["side_effect_policy"]["provider_registry_resolved"])
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["writes_artifact"])
            self.assertFalse((root / "workspace" / "browser-provider-smoke.json").exists())
            dumped = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("user:pass", dumped)
            self.assertNotIn("/Users/example", dumped)
            self.assertEqual(payload["requested_provider_config"]["browser_url"], "http://127.0.0.1:9222")
            self.assertEqual(payload["requested_provider_config"]["proxy"], "<configured>")
            hint = payload["review_command_hint"]
            self.assertIn("--launch-browser-smoke", hint["command"])
            self.assertIn("--browser-url", hint["command"])
            self.assertIn("http://127.0.0.1:9222", hint["command"])

    def test_module_cli_print_launch_command_does_not_write_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reverse_deepagent.browser_provider_smoke",
                    "--browser",
                    "cloakbrowser",
                    "--artifact-root",
                    str(root),
                    "--browser-smoke-url",
                    "https://example.test/smoke",
                    "--browser-url",
                    "http://user:pass@127.0.0.1:9222",
                    "--browser-profile-dir",
                    "/Users/example/private-profile",
                    "--browser-proxy",
                    "http://user:pass@example.test:8080",
                    "--browser-args",
                    "--load-extension=/Users/example/ext --proxy-server=http://user:pass@example.test:8080",
                    "--print-launch-command",
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(payload["mode"], "print-launch-command")
            self.assertFalse(payload["side_effect_policy"]["writes_artifact"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse((root / "workspace" / "browser-provider-smoke.json").exists())
            self.assertNotIn("user:pass", result.stdout)
            self.assertNotIn("/Users/example", result.stdout)

    def test_review_smoke_json_reports_acceptance_without_writing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            smoke_path = root / "workspace" / "browser-provider-smoke.json"
            smoke_path.parent.mkdir(parents=True)
            smoke_path.write_text(
                json.dumps(
                    {
                        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
                        "artifact_key": "workspace_browser_provider_smoke",
                        "mode": "metadata-only",
                        "ok": True,
                        "requested_provider_id": "cloakbrowser",
                        "resolved_provider_id": "cloakbrowser",
                        "side_effect_policy": {
                            "provider_factories_invoked": False,
                            "starts_browser": False,
                            "calls_mcp": False,
                            "touches_mobile_full_runtime_chains": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = review_browser_provider_smoke_json(
                smoke_json_path=smoke_path,
                expected_provider_id="cloakbrowser",
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schema_version"], "reverse-deepagent.browser-provider-smoke-review.v1")
            self.assertEqual(payload["mode"], "review-smoke-json")
            self.assertFalse(payload["attachment_acceptance"]["runtime_launch_smoke_accepted"])
            self.assertEqual(payload["acceptance_report"]["evidence_level"], "metadata-only")
            self.assertEqual(payload["policy_decision"]["decision"], "warn")
            self.assertTrue(payload["policy_decision"]["policy_passed"])
            self.assertEqual(payload["policy_decision"]["minimum_evidence_level"], "metadata-only")
            self.assertEqual(payload["policy_decision"]["observed_evidence_level"], "metadata-only")
            self.assertEqual(
                payload["acceptance_report"]["required_follow_up"],
                "run_explicit_launch_browser_smoke_before_claiming_runtime_smoke",
            )
            self.assertFalse(payload["side_effect_policy"]["writes_artifact"])
            self.assertFalse(payload["side_effect_policy"]["provider_registry_resolved"])
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
            self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])
            self.assertFalse((root / "workspace" / "browser-provider-smoke-review.json").exists())

    def test_review_smoke_json_policy_blocks_when_minimum_evidence_is_not_met(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            smoke_path = Path(tmpdir) / "browser-provider-smoke.json"
            smoke_path.write_text(
                json.dumps(
                    {
                        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
                        "mode": "metadata-only",
                        "ok": True,
                        "requested_provider_id": "cloakbrowser",
                        "resolved_provider_id": "cloakbrowser",
                        "side_effect_policy": {
                            "provider_factories_invoked": False,
                            "starts_browser": False,
                            "calls_mcp": False,
                            "touches_mobile_full_runtime_chains": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = review_browser_provider_smoke_json(
                smoke_json_path=smoke_path,
                expected_provider_id="cloakbrowser",
                minimum_evidence_level="launch-smoke",
            )

            self.assertFalse(payload["ok"])
            self.assertTrue(payload["attachment_acceptance"]["accepted"])
            self.assertEqual(payload["policy_decision"]["decision"], "block")
            self.assertFalse(payload["policy_decision"]["policy_passed"])
            self.assertEqual(payload["policy_decision"]["minimum_evidence_level"], "launch-smoke")
            self.assertEqual(payload["policy_decision"]["observed_evidence_level"], "metadata-only")
            self.assertIn(
                "insufficient_browser_provider_smoke_evidence_level",
                payload["policy_decision"]["blockers"],
            )
            self.assertFalse(payload["policy_decision"]["side_effect_policy"]["starts_browser"])

    def test_review_smoke_json_policy_passes_matching_launch_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            smoke_path = Path(tmpdir) / "browser-provider-smoke.json"
            smoke_path.write_text(
                json.dumps(
                    {
                        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
                        "mode": "launch-smoke",
                        "ok": True,
                        "requested_provider_id": "cloakbrowser",
                        "resolved_provider_id": "cloakbrowser",
                        "provider": {"smoke": {"status": "passed", "url": "about:blank"}},
                        "side_effect_policy": {
                            "launch_smoke_requested": True,
                            "starts_browser": True,
                            "calls_mcp": False,
                            "touches_mobile_full_runtime_chains": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            payload = review_browser_provider_smoke_json(
                smoke_json_path=smoke_path,
                expected_provider_id="cloakbrowser",
                minimum_evidence_level="launch-smoke",
            )

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["attachment_acceptance"]["runtime_launch_smoke_accepted"])
            self.assertEqual(payload["policy_decision"]["decision"], "pass")
            self.assertTrue(payload["policy_decision"]["policy_passed"])
            self.assertEqual(payload["policy_decision"]["minimum_evidence_level"], "launch-smoke")
            self.assertEqual(payload["policy_decision"]["observed_evidence_level"], "launch-smoke")
            self.assertFalse(payload["policy_decision"]["side_effect_policy"]["starts_browser"])

    def test_module_cli_review_smoke_json_blocks_provider_mismatch_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            smoke_path = root / "browser-provider-smoke.json"
            smoke_path.write_text(
                json.dumps(
                    {
                        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
                        "mode": "launch-smoke",
                        "ok": True,
                        "requested_provider_id": "remote-cdp",
                        "resolved_provider_id": "remote-cdp",
                        "provider": {"smoke": {"status": "passed"}},
                        "side_effect_policy": {
                            "launch_smoke_requested": True,
                            "starts_browser": True,
                            "calls_mcp": False,
                            "touches_mobile_full_runtime_chains": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "reverse_deepagent.browser_provider_smoke",
                    "--review-smoke-json",
                    str(smoke_path),
                    "--expected-provider",
                    "cloakbrowser",
                    "--minimum-evidence-level",
                    "launch-smoke",
                    "--browser-args",
                    '"unterminated',
                ],
                check=False,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 2)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["mode"], "review-smoke-json")
            self.assertIn("browser_provider_smoke_provider_mismatch", payload["attachment_acceptance"]["blockers"])
            self.assertEqual(
                payload["acceptance_report"]["required_follow_up"],
                "regenerate_matching_browser_provider_smoke_json",
            )
            self.assertEqual(payload["policy_decision"]["decision"], "block")
            self.assertFalse(payload["policy_decision"]["policy_passed"])
            self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])


if __name__ == "__main__":
    unittest.main()
