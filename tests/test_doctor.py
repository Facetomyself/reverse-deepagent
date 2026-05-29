import argparse
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from reverse_deepagent.doctor import run_doctor


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
            "request_timeout": 1.0,
            "startup_timeout": 1.0,
            "strict": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_doctor_reports_static_browser_and_mcp_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = run_doctor(self.make_args(Path(tmp)))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["chrome"]["path"]["exists"])
        self.assertTrue(payload["mcp"]["command"]["exists"])
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

    def test_doctor_can_check_fake_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
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
            args = self.make_args(
                tmpdir,
                jsreverser_mcp_command=sys.executable,
                check_mcp=True,
            )
            # Python itself is executable, but the doctor expects the MCP command as one binary.
            # Use a wrapper to keep command semantics identical to jsreverser-mcp.
            wrapper = tmpdir / "fake_mcp.sh"
            wrapper.write_text(f"#!/usr/bin/env bash\nexec \"{sys.executable}\" \"{fake_mcp}\" \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o755)
            args.jsreverser_mcp_command = str(wrapper)
            payload = run_doctor(args)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["mcp_check"]["ok"])
        self.assertIn("check_browser_health", payload["mcp_check"]["tool_sample"])


if __name__ == "__main__":
    unittest.main()
