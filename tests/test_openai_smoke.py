import argparse
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.openai_smoke import resolve_openai_settings


class OpenAISmokeEntrypointTests(unittest.TestCase):
    def test_openai_smoke_help_does_not_require_api_key(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "reverse_deepagent.openai_smoke", "--help"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("--model", result.stdout)
        self.assertIn("--config", result.stdout)
        self.assertIn("--artifact-root", result.stdout)
        self.assertIn("OpenAI", result.stdout)


class OpenAIConfigTests(unittest.TestCase):
    def make_args(self, config_path: str, **overrides: object) -> argparse.Namespace:
        values = {
            "config": config_path,
            "model": None,
            "timeout": None,
            "max_retries": None,
            "temperature": None,
            "base_url": None,
            "organization": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_resolve_openai_settings_from_config_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[openai]",
                        'api_key = "sk-test-from-config"',
                        'model = "gpt-test-config"',
                        "timeout = 42",
                        "max_retries = 3",
                        'base_url = "https://api.example.test/v1"',
                        'organization = "org-test"',
                    ]
                ),
                encoding="utf-8",
            )
            settings = resolve_openai_settings(self.make_args(str(config_path)), environ={})

        self.assertEqual(settings.api_key, "sk-test-from-config")
        self.assertEqual(settings.model, "gpt-test-config")
        self.assertEqual(settings.timeout, 42.0)
        self.assertEqual(settings.max_retries, 3)
        self.assertEqual(settings.base_url, "https://api.example.test/v1")
        self.assertEqual(settings.organization, "org-test")

    def test_cli_and_env_override_config_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[openai]",
                        'api_key = "sk-test-from-config"',
                        'model = "gpt-test-config"',
                        "timeout = 42",
                        "max_retries = 3",
                    ]
                ),
                encoding="utf-8",
            )
            settings = resolve_openai_settings(
                self.make_args(str(config_path), model="gpt-cli", max_retries=9),
                environ={
                    "OPENAI_API_KEY": "sk-test-from-env",
                    "OPENAI_TIMEOUT": "88",
                },
            )

        self.assertEqual(settings.api_key, "sk-test-from-env")
        self.assertEqual(settings.model, "gpt-cli")
        self.assertEqual(settings.timeout, 88.0)
        self.assertEqual(settings.max_retries, 9)


if __name__ == "__main__":
    unittest.main()
