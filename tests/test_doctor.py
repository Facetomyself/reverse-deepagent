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
        self.assertEqual(matrix["summary"]["provider_count"], 3)
        by_provider = {item["provider_id"]: item for item in matrix["providers"]}
        self.assertIn("playwright-chromium", by_provider)
        self.assertIn("cloakbrowser", by_provider)
        self.assertIn("remote-cdp", by_provider)
        self.assertEqual(by_provider["remote-cdp"]["supported_modes"], ["connect", "cdp", "runtime-eval", "debugger"])
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
        self.assertEqual(matrix["summary"]["provider_count"], 2)
        self.assertEqual(matrix["summary"]["review_only_count"], 1)
        self.assertEqual(matrix["summary"]["external_delivery_capable_count"], 1)
        self.assertIn("manual-handoff", matrix["provider_ids"])
        self.assertIn("filesystem-release", matrix["provider_ids"])
        by_provider = {provider["provider_id"]: provider for provider in matrix["providers"]}
        provider = by_provider["review-only"]
        self.assertEqual(provider["aliases"], ["noop", "manual-handoff"])
        self.assertFalse(provider["supports_external_delivery"])
        local_archive = by_provider["local-archive"]
        self.assertEqual(local_archive["aliases"], ["filesystem-release", "archive"])
        self.assertTrue(local_archive["supports_external_delivery"])
        self.assertEqual(local_archive["transport"], "filesystem")
        self.assertFalse(matrix["side_effect_policy"]["provider_factories_invoked"])
        self.assertFalse(matrix["side_effect_policy"]["external_delivery_performed"])

    def test_external_delivery_provider_matrix_loads_entry_points_without_invoking_factories(self) -> None:
        factory_calls: list[str] = []
        registration = ExternalDeliveryProviderRegistration(
            provider_id="webhook-draft",
            aliases=("webhook",),
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
        self.assertIn("webhook", matrix["provider_ids"])
        by_provider = {item["provider_id"]: item for item in matrix["providers"]}
        self.assertEqual(by_provider["webhook-draft"]["aliases"], ["webhook"])
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
