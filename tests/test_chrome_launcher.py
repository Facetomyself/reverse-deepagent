import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.runtime.chrome import ChromeDebugConfig, ensure_chrome_debug


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPTS = (
    REPO_ROOT / "scripts" / "start_chrome_debug.sh",
    REPO_ROOT / "src" / "reverse_deepagent" / "scripts" / "start_chrome_debug.sh",
)
STOP_SCRIPTS = (
    REPO_ROOT / "scripts" / "stop_chrome_debug.sh",
    REPO_ROOT / "src" / "reverse_deepagent" / "scripts" / "stop_chrome_debug.sh",
)


class ChromeLauncherTests(unittest.TestCase):
    def test_ensure_chrome_debug_passes_configurable_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "env.txt"
            script = Path(tmpdir) / "fake_start.sh"
            script.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"echo \"$DEBUG_PORT|$DEBUG_ADDRESS|$USER_DATA_DIR|$START_URL|$EXTRA_CHROME_ARGS\" > \"{output}\"\n"
                "echo started\n",
                encoding="utf-8",
            )
            script.chmod(0o755)
            config = ChromeDebugConfig(
                debug_port=9333,
                debug_address="127.0.0.1",
                user_data_dir="/tmp/reverse-agent-profile",
                start_url="http://localhost/demo",
                extra_chrome_args="--disable-web-security",
                start_script=str(script),
            )
            result = ensure_chrome_debug(config, timeout=5)
            self.assertTrue(result.ok)
            self.assertEqual(result.browser_url, "http://127.0.0.1:9333")
            self.assertEqual(output.read_text(encoding="utf-8").strip(), "9333|127.0.0.1|/tmp/reverse-agent-profile|http://localhost/demo|--disable-web-security")

    def test_launcher_shell_scripts_pass_bash_syntax_check(self) -> None:
        scripts = [*START_SCRIPTS, *STOP_SCRIPTS]
        result = subprocess.run(
            ["bash", "-n", *map(str, scripts)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_start_script_rejects_invalid_debug_port_before_open(self) -> None:
        for script in START_SCRIPTS:
            with self.subTest(script=str(script)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    marker = tmp / "open-called"
                    fake_bin = tmp / "bin"
                    fake_bin.mkdir()
                    fake_open = fake_bin / "open"
                    fake_open.write_text(
                        "#!/usr/bin/env bash\n"
                        f"touch '{marker}'\n"
                        "exit 0\n",
                        encoding="utf-8",
                    )
                    fake_open.chmod(0o755)
                    env = os.environ.copy()
                    env.update(
                        {
                            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                            "DEBUG_PORT": "9222;bad",
                            "CHROME_PATH": "/bin/sh",
                            "STATE_DIR": str(tmp / "state"),
                            "USER_DATA_DIR": str(tmp / "profile"),
                        }
                    )
                    result = subprocess.run(
                        ["bash", str(script)],
                        text=True,
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("DEBUG_PORT must be an integer", result.stderr)
                    self.assertFalse(marker.exists(), "invalid DEBUG_PORT must not invoke open")

    def test_start_script_rejects_invalid_wait_seconds_before_open(self) -> None:
        for script in START_SCRIPTS:
            with self.subTest(script=str(script)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    marker = tmp / "open-called"
                    fake_bin = tmp / "bin"
                    fake_bin.mkdir()
                    fake_open = fake_bin / "open"
                    fake_open.write_text(
                        "#!/usr/bin/env bash\n"
                        f"touch '{marker}'\n"
                        "exit 0\n",
                        encoding="utf-8",
                    )
                    fake_open.chmod(0o755)
                    env = os.environ.copy()
                    env.update(
                        {
                            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                            "DEBUG_PORT": "9222",
                            "WAIT_SECONDS": "-1",
                            "CHROME_PATH": "/bin/sh",
                            "STATE_DIR": str(tmp / "state"),
                            "USER_DATA_DIR": str(tmp / "profile"),
                        }
                    )
                    result = subprocess.run(
                        ["bash", str(script)],
                        text=True,
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("WAIT_SECONDS must be a non-negative integer", result.stderr)
                    self.assertFalse(marker.exists(), "invalid WAIT_SECONDS must not invoke open")

    def test_stop_script_rejects_invalid_debug_port_before_lsof_or_state_paths(self) -> None:
        for script in STOP_SCRIPTS:
            with self.subTest(script=str(script)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    marker = tmp / "lsof-called"
                    fake_bin = tmp / "bin"
                    fake_bin.mkdir()
                    fake_lsof = fake_bin / "lsof"
                    fake_lsof.write_text(
                        "#!/usr/bin/env bash\n"
                        f"touch '{marker}'\n"
                        "exit 0\n",
                        encoding="utf-8",
                    )
                    fake_lsof.chmod(0o755)
                    env = os.environ.copy()
                    env.update(
                        {
                            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                            "DEBUG_PORT": "0",
                            "STATE_DIR": str(tmp / "state"),
                            "USER_DATA_DIR": str(tmp / "profile"),
                        }
                    )
                    result = subprocess.run(
                        ["bash", str(script)],
                        text=True,
                        capture_output=True,
                        env=env,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("DEBUG_PORT must be in the range", result.stderr)
                    self.assertFalse(marker.exists(), "invalid DEBUG_PORT must not invoke lsof")


if __name__ == "__main__":
    unittest.main()
