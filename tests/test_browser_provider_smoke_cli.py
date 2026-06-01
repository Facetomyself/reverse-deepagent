import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser_provider_smoke import run_browser_provider_smoke


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


if __name__ == "__main__":
    unittest.main()
