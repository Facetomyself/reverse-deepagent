import subprocess
import sys
import unittest


class OpenAISmokeEntrypointTests(unittest.TestCase):
    def test_openai_smoke_help_does_not_require_api_key(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "reverse_deepagent.openai_smoke", "--help"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("--model", result.stdout)
        self.assertIn("--artifact-root", result.stdout)
        self.assertIn("OpenAI", result.stdout)


if __name__ == "__main__":
    unittest.main()
