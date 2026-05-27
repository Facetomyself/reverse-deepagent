import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class RunDemoChromeLifecycleTests(unittest.TestCase):
    def _write_fake_script(self, path: Path, marker: Path, label: str) -> None:
        path.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"echo '{label}:'\"$DEBUG_PORT|$USER_DATA_DIR\" >> \"{marker}\"\n"
            f"echo {label}\n",
            encoding="utf-8",
        )
        path.chmod(0o755)

    def _run_demo(self, tmpdir: str, start_script: Path, stop_script: Path, runtime: str, keep: bool) -> dict:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "src")
        args = [
            sys.executable,
            str(REPO_ROOT / "scripts/run_demo.py"),
            "--runtime",
            runtime,
            "--ensure-chrome",
            "--chrome-start-script",
            str(start_script),
            "--chrome-stop-script",
            str(stop_script),
            "--chrome-debug-port",
            "9444",
            "--chrome-user-data-dir",
            str(Path(tmpdir) / "profile"),
            "--artifact-root",
            str(Path(tmpdir) / "artifacts"),
        ]
        if keep:
            args.append("--keep-chrome")
        result = subprocess.run(args, check=True, text=True, capture_output=True, env=env)
        return json.loads(result.stdout)

    def test_mock_runtime_does_not_start_chrome_even_if_flag_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "lifecycle.txt"
            start_script = Path(tmpdir) / "start.sh"
            stop_script = Path(tmpdir) / "stop.sh"
            self._write_fake_script(start_script, marker, "start")
            self._write_fake_script(stop_script, marker, "stop")
            payload = self._run_demo(tmpdir, start_script, stop_script, runtime="mock", keep=False)
            self.assertNotIn("chrome_launch", payload)
            self.assertNotIn("chrome_stop", payload)
            self.assertFalse(marker.exists())

    def test_mcp_runtime_stops_managed_chrome_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "lifecycle.txt"
            start_script = Path(tmpdir) / "start.sh"
            stop_script = Path(tmpdir) / "stop.sh"
            self._write_fake_script(start_script, marker, "start")
            self._write_fake_script(stop_script, marker, "stop")
            payload = self._run_demo(tmpdir, start_script, stop_script, runtime="mcp", keep=False)
            self.assertIn("chrome_launch", payload)
            self.assertIn("chrome_stop", payload)
            content = marker.read_text(encoding="utf-8")
            self.assertIn("start:9444|", content)
            self.assertIn("stop:9444|", content)

    def test_mcp_runtime_keep_chrome_skips_stop_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            marker = Path(tmpdir) / "lifecycle.txt"
            start_script = Path(tmpdir) / "start.sh"
            stop_script = Path(tmpdir) / "stop.sh"
            self._write_fake_script(start_script, marker, "start")
            self._write_fake_script(stop_script, marker, "stop")
            payload = self._run_demo(tmpdir, start_script, stop_script, runtime="mcp", keep=True)
            self.assertIn("chrome_launch", payload)
            self.assertNotIn("chrome_stop", payload)
            content = marker.read_text(encoding="utf-8")
            self.assertIn("start:9444|", content)
            self.assertNotIn("stop:9444|", content)


if __name__ == "__main__":
    unittest.main()
