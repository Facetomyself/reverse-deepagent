import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.runtime.chrome import ChromeDebugConfig, ensure_chrome_debug


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


if __name__ == "__main__":
    unittest.main()
