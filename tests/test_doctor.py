import argparse
import contextlib
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from pathlib import Path

from reverse_deepagent.delivery import (
    ExternalDeliveryProviderCapabilities,
    ExternalDeliveryProviderRegistration,
)
from reverse_deepagent.delivery import registry as delivery_registry
from reverse_deepagent.doctor import run_doctor
from reverse_deepagent.runtime import (
    RuntimeBackendCapabilities,
    RuntimeBackendRegistration,
)
from reverse_deepagent.runtime import registry as runtime_registry


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-legacy-mcp" / "src"


class FakeDeliveryEntryPoint:
    def __init__(self, name: str, value) -> None:
        self.name = name
        self.value = value

    def load(self):
        return self.value


class FakeDeliveryEntryPoints(list):
    def select(self, *, group: str):
        if group == "reverse_deepagent.external_delivery_providers":
            return FakeDeliveryEntryPoints(self)
        return FakeDeliveryEntryPoints()


class FakeRuntimeEntryPoint:
    def __init__(self, name: str, value) -> None:
        self.name = name
        self.value = value

    def load(self):
        return self.value


class FakeRuntimeEntryPoints(list):
    def select(self, *, group: str):
        if group == "reverse_deepagent.runtime_backends":
            return FakeRuntimeEntryPoints(self)
        return FakeRuntimeEntryPoints()


class DoctorTests(unittest.TestCase):
    def make_args(self, tmpdir: Path, **overrides: object) -> argparse.Namespace:
        chrome = tmpdir / "chrome"
        start_script = tmpdir / "start.sh"
        stop_script = tmpdir / "stop.sh"
        mcp = tmpdir / "fake_mcp.py"
        chrome.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        chrome.chmod(0o755)
        start_script.write_text("#!/usr/bin/env bash\necho started\n", encoding="utf-8")
        start_script.chmod(0o755)
        stop_script.write_text("#!/usr/bin/env bash\necho stopped\n", encoding="utf-8")
        stop_script.chmod(0o755)
        mcp.write_text("print('fake')\n", encoding="utf-8")
        mcp.chmod(0o755)
        values = {
            "browser_url": "http://127.0.0.1:65530",
            "chrome_debug_port": 65530,
            "chrome_debug_address": "127.0.0.1",
            "chrome_path": str(chrome),
            "chrome_user_data_dir": str(tmpdir / "profile"),
            "chrome_start_url": "about:blank",
            "chrome_extra_args": "",
            "chrome_wait_seconds": 1,
            "chrome_start_script": str(start_script),
            "chrome_stop_script": str(stop_script),
            "jsreverser_mcp_command": str(mcp),
            "ensure_chrome": False,
            "keep_chrome": False,
            "check_mcp": False,
            "legacy_mcp": False,
            "browser": None,
            "browser_provider_matrix": False,
            "browser_profile_dir": None,
            "browser_headless": None,
            "browser_executable_path": None,
            "browser_args": "",
            "browser_humanize": None,
            "browser_proxy": None,
            "browser_geoip": False,
            "browser_locale": None,
            "browser_timezone": None,
            "launch_browser_smoke": False,
            "browser_smoke_url": "about:blank",
            "external_delivery_providers": False,
            "runtime_backends": False,
            "delivery_transaction_root": None,
            "request_timeout": 1.0,
            "startup_timeout": 1.0,
            "strict": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def write_fake_mcp_wrapper(self, tmpdir: Path) -> Path:
        fake_mcp = tmpdir / "fake_mcp_server.py"
        fake_mcp.write_text(
            textwrap.dedent(
                '''
                import json
                import sys

                def write_message(message):
                    sys.stdout.write(json.dumps(message) + '\\n')
                    sys.stdout.flush()

                for line in sys.stdin.buffer:
                    message = json.loads(line.decode('utf-8'))
                    if message.get('method') == 'initialize':
                        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'protocolVersion': '2025-03-26', 'capabilities': {}, 'serverInfo': {'name': 'fake', 'version': '0.1'}}})
                    elif message.get('method') == 'notifications/initialized':
                        continue
                    elif message.get('method') == 'tools/list':
                        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'tools': [{'name': 'check_browser_health'}]}})
                    elif message.get('method') == 'tools/call':
                        write_message({'jsonrpc': '2.0', 'id': message['id'], 'result': {'content': [{'type': 'text', 'text': json.dumps({'healthy': True})}]}})
                '''
            ),
            encoding="utf-8",
        )
        wrapper = tmpdir / "fake_mcp.sh"
        wrapper.write_text(f"#!/usr/bin/env bash\nexec \"{sys.executable}\" \"{fake_mcp}\" \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        return wrapper

    @contextlib.contextmanager
    def with_legacy_plugin_path(self):
        sys.path.insert(0, str(PACKAGE_SRC))
        try:
            sys.modules.pop("reverse_deepagent_legacy_mcp", None)
            yield
        finally:
            sys.modules.pop("reverse_deepagent_legacy_mcp", None)
            if str(PACKAGE_SRC) in sys.path:
                sys.path.remove(str(PACKAGE_SRC))

    def test_doctor_reports_static_browser_and_mcp_paths(self) -> None:
        class FakeCapabilities:
            def model_dump(self, mode: str = "json") -> dict[str, object]:
                return {"provider_id": "fake-provider", "config": {}}

        class FakeProvider:
            def describe(self) -> FakeCapabilities:
                return FakeCapabilities()

            def is_available(self) -> bool:
                return True

            def stop(self) -> None:
                pass

        class FakeRuntime:
            browser_provider = FakeProvider()

        with tempfile.TemporaryDirectory() as tmp:
            with patch("reverse_deepagent.doctor.create_native_web_runtime", return_value=FakeRuntime()):
                payload = run_doctor(self.make_args(Path(tmp)))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["chrome"]["path"]["exists"])
        self.assertTrue(payload["mcp"]["command"]["exists"])
        self.assertTrue(payload["browser_provider"]["ok"])
        self.assertIn("reverse-agent-demo", payload["console_scripts"]["repo_venv_scripts"])

    def test_doctor_help_does_not_require_chrome_or_mcp(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "reverse_deepagent.doctor", "--help"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("--ensure-chrome", result.stdout)
        self.assertIn("--check-mcp", result.stdout)
        self.assertIn("--legacy-mcp", result.stdout)
        self.assertIn("--browser", result.stdout)
        self.assertIn("--browser-provider-matrix", result.stdout)
        self.assertIn("--launch-browser-smoke", result.stdout)
        self.assertIn("--external-delivery-providers", result.stdout)

    def test_doctor_can_check_fake_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            args = self.make_args(
                tmpdir,
                jsreverser_mcp_command=sys.executable,
                check_mcp=True,
            )
            # Python itself is executable, but the doctor expects the MCP command as one binary.
            # Use a wrapper to keep command semantics identical to jsreverser-mcp.
            wrapper = self.write_fake_mcp_wrapper(tmpdir)
            args.jsreverser_mcp_command = str(wrapper)
            with self.with_legacy_plugin_path():
                payload = run_doctor(args)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["mcp_check"]["ok"])
        self.assertTrue(payload["legacy_mcp_check"]["ok"])
        self.assertIn("deprecation_warnings", payload)
        self.assertTrue(payload["deprecation_warnings"][0].startswith("警告：`--check-mcp`"))
        self.assertIn("check_browser_health", payload["mcp_check"]["tool_sample"])

    def test_doctor_legacy_mcp_flag_checks_fake_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            wrapper = self.write_fake_mcp_wrapper(tmpdir)
            with self.with_legacy_plugin_path():
                payload = run_doctor(self.make_args(tmpdir, jsreverser_mcp_command=str(wrapper), legacy_mcp=True))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["legacy_mcp_check"]["ok"])
        self.assertTrue(payload["mcp_check"]["ok"])

    def test_doctor_legacy_mcp_without_optional_plugin_reports_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            wrapper = self.write_fake_mcp_wrapper(tmpdir)
            payload = run_doctor(self.make_args(tmpdir, jsreverser_mcp_command=str(wrapper), legacy_mcp=True))
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["legacy_mcp_check"]["ok"])
        self.assertEqual(payload["legacy_mcp_check"]["error"], "legacy_mcp_optional_backend_not_installed")
        self.assertEqual(payload["legacy_mcp_check"]["install_guidance"]["package"], "reverse-deepagent-legacy-mcp")

    def test_doctor_can_check_playwright_provider_without_launching(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(self.make_args(Path(tmp), browser="playwright-chromium"))
        provider = payload["browser_provider"]
        self.assertEqual(provider["browser"], "playwright-chromium")
        self.assertFalse(provider["launched"])
        self.assertIn("capabilities", provider)
        self.assertEqual(provider["capabilities"]["provider_id"], "playwright-chromium")
        self.assertIn("smoke_matrix", provider)
        lifecycle = {item["stage"]: item["status"] for item in provider["smoke_matrix"]["lifecycle"]}
        self.assertIn("availability_checked", lifecycle)
        self.assertEqual(lifecycle["session_start_requested"], "skipped")

    def test_doctor_can_emit_side_effect_free_browser_provider_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(self.make_args(Path(tmp), browser_provider_matrix=True, jsreverser_mcp_command=str(Path(tmp) / "missing-mcp")))
        matrix = payload["browser_provider_smoke_matrix"]
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["port_before"]["skipped"])
        self.assertTrue(payload["port_after_launch"]["skipped"])
        self.assertTrue(matrix["ok"])
        self.assertFalse(matrix["side_effect_policy"]["availability_check_requested"])
        self.assertFalse(matrix["side_effect_policy"]["launch_smoke_requested"])
        self.assertFalse(matrix["side_effect_policy"]["provider_factories_invoked"])
        self.assertEqual(matrix["entry_point_group"], "reverse_deepagent.browser_providers")
        self.assertIn("provider_registration_metadata", matrix)
        self.assertEqual(matrix["compatibility_rule_version"], "2026-05-31.metadata-compatibility-v1")
        self.assertEqual(matrix["summary"]["provider_count"], 3)
        self.assertEqual(matrix["summary"]["compatibility"]["error_count"], 0)
        by_provider = {item["provider_id"]: item for item in matrix["providers"]}
        self.assertIn("playwright-chromium", by_provider)
        self.assertIn("cloakbrowser", by_provider)
        self.assertIn("remote-cdp", by_provider)
        self.assertEqual(by_provider["remote-cdp"]["supported_modes"], ["connect", "cdp", "runtime-eval", "debugger"])
        self.assertEqual(by_provider["remote-cdp"]["compatibility"]["status"], "compatible")
        for row in matrix["providers"]:
            lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
            self.assertEqual(lifecycle["availability_checked"], "not_checked")
            self.assertEqual(lifecycle["session_start_requested"], "skipped")

    def test_doctor_can_emit_side_effect_free_external_delivery_provider_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(
                self.make_args(
                    Path(tmp),
                    external_delivery_providers=True,
                    jsreverser_mcp_command=str(Path(tmp) / "missing-mcp"),
                )
            )
        matrix = payload["external_delivery_provider_matrix"]
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["mcp"]["command"]["exists"])
        self.assertTrue(payload["port_before"]["skipped"])
        self.assertTrue(payload["port_after_launch"]["skipped"])
        self.assertEqual(matrix["entry_point_group"], "reverse_deepagent.external_delivery_providers")
        self.assertEqual(matrix["summary"]["provider_count"], 5)
        self.assertEqual(matrix["summary"]["review_only_count"], 1)
        self.assertEqual(matrix["summary"]["external_delivery_capable_count"], 4)
        self.assertIn("github-release", matrix["provider_ids"])
        self.assertIn("gh-release", matrix["provider_ids"])
        self.assertIn("github-release-assets", matrix["provider_ids"])
        self.assertIn("manual-handoff", matrix["provider_ids"])
        self.assertIn("filesystem-release", matrix["provider_ids"])
        self.assertIn("http-webhook", matrix["provider_ids"])
        self.assertIn("object-storage", matrix["provider_ids"])
        self.assertIn("s3-presigned", matrix["provider_ids"])
        by_provider = {provider["provider_id"]: provider for provider in matrix["providers"]}
        github_release = by_provider["github-release"]
        self.assertEqual(github_release["aliases"], ["gh-release", "github-release-assets"])
        self.assertTrue(github_release["supports_external_delivery"])
        self.assertEqual(github_release["transport"], "github-release")
        self.assertTrue(github_release["metadata"]["supports_existing_release_reuse"])
        self.assertTrue(github_release["metadata"]["supports_existing_asset_preflight"])
        self.assertTrue(github_release["metadata"]["supports_existing_asset_overwrite_preflight"])
        self.assertTrue(github_release["metadata"]["supports_existing_asset_delete_preflight"])
        self.assertEqual(github_release["metadata"]["existing_asset_conflict_default"], "block")
        self.assertTrue(github_release["metadata"]["supports_existing_asset_overwrite"])
        self.assertTrue(github_release["metadata"]["supports_existing_asset_delete"])
        self.assertTrue(github_release["metadata"]["existing_asset_overwrite_requires_explicit_approval"])
        self.assertTrue(github_release["metadata"]["supports_explicit_retry"])
        self.assertEqual(github_release["metadata"]["default_retry_attempts"], 0)
        self.assertIn(503, github_release["metadata"]["default_retry_status_codes"])
        provider = by_provider["review-only"]
        self.assertEqual(provider["aliases"], ["noop", "manual-handoff"])
        self.assertFalse(provider["supports_external_delivery"])
        local_archive = by_provider["local-archive"]
        self.assertEqual(local_archive["aliases"], ["filesystem-release", "archive"])
        self.assertTrue(local_archive["supports_external_delivery"])
        self.assertEqual(local_archive["transport"], "filesystem")
        webhook = by_provider["webhook"]
        self.assertEqual(webhook["aliases"], ["webhook-json", "http-webhook"])
        self.assertTrue(webhook["supports_external_delivery"])
        self.assertEqual(webhook["transport"], "webhook")
        self.assertTrue(webhook["metadata"]["supports_explicit_retry"])
        self.assertEqual(webhook["metadata"]["default_retry_attempts"], 0)
        presigned = by_provider["presigned-object"]
        self.assertEqual(presigned["aliases"], ["object-storage", "presigned-url", "s3-presigned"])
        self.assertTrue(presigned["supports_external_delivery"])
        self.assertEqual(presigned["transport"], "object-storage")
        self.assertTrue(presigned["metadata"]["supports_explicit_retry"])
        self.assertEqual(presigned["metadata"]["default_retry_attempts"], 0)
        self.assertFalse(matrix["side_effect_policy"]["provider_factories_invoked"])
        self.assertFalse(matrix["side_effect_policy"]["external_delivery_performed"])

    def test_doctor_can_emit_side_effect_free_runtime_backend_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(
                self.make_args(
                    Path(tmp),
                    runtime_backends=True,
                    jsreverser_mcp_command=str(Path(tmp) / "missing-mcp"),
                )
            )
        matrix = payload["runtime_backend_matrix"]
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["mcp"]["command"]["exists"])
        self.assertTrue(payload["port_before"]["skipped"])
        self.assertTrue(payload["port_after_launch"]["skipped"])
        self.assertEqual(matrix["entry_point_group"], "reverse_deepagent.runtime_backends")
        self.assertEqual(matrix["summary"]["backend_count"], 9)
        self.assertEqual(matrix["summary"]["registered_key_count"], 26)
        self.assertEqual(matrix["summary"]["web_backend_count"], 6)
        self.assertEqual(matrix["summary"]["non_web_backend_count"], 3)
        self.assertEqual(matrix["summary"]["mcp_backed_count"], 0)
        self.assertEqual(matrix["summary"]["managed_chrome_capable_count"], 0)
        self.assertEqual(matrix["summary"]["target_platforms"], ["android", "ios", "mini-program", "web"])
        self.assertIn("native-web", matrix["backend_ids"])
        self.assertIn("browser-native", matrix["backend_ids"])
        self.assertIn("android-adb", matrix["backend_ids"])
        self.assertIn("wechat-devtools", matrix["backend_ids"])
        by_backend = {backend["backend_id"]: backend for backend in matrix["backends"]}
        self.assertEqual(by_backend["native-web"]["aliases"], ["web", "browser-native"])
        self.assertTrue(by_backend["native-web"]["supports_web_recon"])
        self.assertFalse(by_backend["native-web"]["mcp_backed"])
        self.assertEqual(by_backend["android-adb"]["target_platforms"], ["android"])
        self.assertFalse(by_backend["android-adb"]["supports_browser_session"])
        self.assertFalse(matrix["side_effect_policy"]["backend_factories_invoked"])
        self.assertFalse(matrix["side_effect_policy"]["chrome_started"])
        self.assertFalse(matrix["side_effect_policy"]["mcp_started"])
        self.assertFalse(matrix["side_effect_policy"]["platform_tools_invoked"])

    def test_doctor_can_inspect_delivery_transaction_without_browser_or_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "delivery"
            root.mkdir()
            (root / "delivery-transaction-journal.json").write_text(
                json.dumps({"transaction_id": "tx-doctor", "filesystem_artifact_mutated": True}),
                encoding="utf-8",
            )
            payload = run_doctor(
                self.make_args(
                    Path(tmp),
                    delivery_transaction_root=str(root),
                    jsreverser_mcp_command=str(Path(tmp) / "missing-mcp"),
                )
            )
        transaction = payload["delivery_transaction"]
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["port_before"]["skipped"])
        self.assertTrue(payload["port_after_launch"]["skipped"])
        self.assertTrue(transaction["ok"])
        self.assertEqual(transaction["state_snapshot"]["transaction_id"], "tx-doctor")
        self.assertEqual(transaction["state_snapshot"]["state"], "local_applied")
        self.assertFalse(transaction["side_effect_policy"]["manifest_mutated"])
        self.assertFalse(transaction["side_effect_policy"]["external_delivery_performed"])

    def test_runtime_backend_matrix_loads_entry_points_without_invoking_factories(self) -> None:
        factory_calls: list[str] = []
        registration = RuntimeBackendRegistration(
            backend_id="plugin-runtime",
            aliases=("plugin-runtime-alias",),
            capabilities=RuntimeBackendCapabilities(
                backend_id="plugin-runtime",
                display_name="Plugin Runtime",
                transport="plugin",
                target_platforms=["web"],
                supports_web_recon=True,
            ),
            factory=lambda **_: factory_calls.append("called"),
        )
        entry_points = FakeRuntimeEntryPoints([FakeRuntimeEntryPoint("plugin-runtime", registration)])

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runtime_registry.importlib_metadata, "entry_points", return_value=entry_points):
                payload = run_doctor(self.make_args(Path(tmp), runtime_backends=True))

        matrix = payload["runtime_backend_matrix"]
        self.assertTrue(payload["ok"])
        self.assertEqual(factory_calls, [])
        self.assertIn("plugin-runtime", matrix["backend_ids"])
        self.assertIn("plugin-runtime-alias", matrix["backend_ids"])
        by_backend = {item["backend_id"]: item for item in matrix["backends"]}
        self.assertEqual(by_backend["plugin-runtime"]["aliases"], ["plugin-runtime-alias"])
        self.assertTrue(by_backend["plugin-runtime"]["supports_web_recon"])

    def test_external_delivery_provider_matrix_loads_entry_points_without_invoking_factories(self) -> None:
        factory_calls: list[str] = []
        registration = ExternalDeliveryProviderRegistration(
            provider_id="webhook-draft",
            aliases=("webhook-draft-alias",),
            capabilities=ExternalDeliveryProviderCapabilities(
                provider_id="webhook-draft",
                display_name="Webhook Draft Delivery",
                transport="webhook",
                supports_external_delivery=True,
                review_only=False,
            ),
            factory=lambda **_: factory_calls.append("called"),
        )
        entry_points = FakeDeliveryEntryPoints([FakeDeliveryEntryPoint("webhook-draft", registration)])

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(delivery_registry.importlib_metadata, "entry_points", return_value=entry_points):
                payload = run_doctor(self.make_args(Path(tmp), external_delivery_providers=True))

        matrix = payload["external_delivery_provider_matrix"]
        self.assertTrue(payload["ok"])
        self.assertEqual(factory_calls, [])
        self.assertIn("webhook-draft", matrix["provider_ids"])
        self.assertIn("webhook-draft-alias", matrix["provider_ids"])
        by_provider = {item["provider_id"]: item for item in matrix["providers"]}
        self.assertEqual(by_provider["webhook-draft"]["aliases"], ["webhook-draft-alias"])
        self.assertTrue(by_provider["webhook-draft"]["supports_external_delivery"])

    def test_doctor_redacts_cloakbrowser_proxy_and_does_not_launch_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(
                self.make_args(
                    Path(tmp),
                    browser="cloakbrowser",
                    browser_proxy="http://user:pass@example.test:8080",
                    browser_locale="zh-CN",
                    browser_timezone="Asia/Shanghai",
                )
            )
        provider = payload["browser_provider"]
        self.assertEqual(provider["browser"], "cloakbrowser")
        self.assertFalse(provider["launched"])
        self.assertEqual(provider["capabilities"]["config"]["proxy"], "<configured>")
        self.assertNotIn("user:pass", json.dumps(provider, ensure_ascii=False))

    def test_doctor_reports_unknown_browser_provider_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(self.make_args(Path(tmp), browser="unknown-browser"))
        provider = payload["browser_provider"]
        self.assertFalse(payload["ok"])
        self.assertFalse(provider["ok"])
        self.assertIn("Unsupported native browser provider", provider["error"])

    def test_browser_provider_only_check_does_not_require_mcp_command(self) -> None:
        class FakeCapabilities:
            def model_dump(self, mode: str = "json") -> dict[str, object]:
                return {"provider_id": "fake-provider", "config": {}}

        class FakeProvider:
            def describe(self) -> FakeCapabilities:
                return FakeCapabilities()

            def is_available(self) -> bool:
                return True

            def stop(self) -> None:
                pass

        class FakeRuntime:
            browser_provider = FakeProvider()

        with tempfile.TemporaryDirectory() as tmp:
            args = self.make_args(
                Path(tmp),
                browser="fake-provider",
                jsreverser_mcp_command=str(Path(tmp) / "missing-mcp"),
            )
            with patch("reverse_deepagent.doctor.create_native_web_runtime", return_value=FakeRuntime()):
                payload = run_doctor(args)
        self.assertFalse(payload["mcp"]["command"]["exists"])
        self.assertTrue(payload["browser_provider"]["ok"])
        self.assertTrue(payload["ok"])

    def test_doctor_reports_malformed_browser_args_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(self.make_args(Path(tmp), browser="cloakbrowser", browser_args='"unterminated'))
        provider = payload["browser_provider"]
        self.assertFalse(provider["ok"])
        self.assertFalse(provider["launched"])
        self.assertIn("No closing quotation", provider["error"])


if __name__ == "__main__":
    unittest.main()
