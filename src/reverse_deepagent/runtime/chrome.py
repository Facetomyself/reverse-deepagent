from __future__ import annotations

import os
import subprocess
from importlib import resources
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import Field

from reverse_deepagent.schemas.common import SchemaBaseModel

DEFAULT_DEBUG_PORT = 9222
DEFAULT_DEBUG_ADDRESS = "127.0.0.1"
DEFAULT_BROWSER_URL = f"http://{DEFAULT_DEBUG_ADDRESS}:{DEFAULT_DEBUG_PORT}"
DEFAULT_CHROME_PATH = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
DEFAULT_USER_DATA_DIR = os.environ.get("REVERSE_AGENT_CHROME_USER_DATA_DIR", str(Path.home() / ".codex/browser-profiles/chrome-jsreverser"))
DEFAULT_STATE_DIR = os.environ.get("REVERSE_AGENT_STATE_DIR", str(Path.home() / ".codex/run/reverse-deepagent"))


def _packaged_script_path(name: str) -> str:
    return str(resources.files("reverse_deepagent").joinpath("scripts", name))


DEFAULT_START_SCRIPT = os.environ.get("REVERSE_AGENT_CHROME_START_SCRIPT", _packaged_script_path("start_chrome_debug.sh"))
DEFAULT_STOP_SCRIPT = os.environ.get("REVERSE_AGENT_CHROME_STOP_SCRIPT", _packaged_script_path("stop_chrome_debug.sh"))


class ChromeCommandResult(SchemaBaseModel):
    """Result of invoking a Chrome debug lifecycle command."""

    ok: bool = Field(description="Whether the launch/check command completed successfully.")
    returncode: int = Field(description="Subprocess return code.")
    browser_url: str = Field(description="Expected Chrome DevTools browser URL.")
    stdout: str = Field(default="", description="Launcher stdout.")
    stderr: str = Field(default="", description="Launcher stderr.")
    command: list[str] = Field(default_factory=list, description="Executed command.")
    env_overrides: dict[str, str] = Field(default_factory=dict, description="Environment overrides passed to the launcher.")


@dataclass(slots=True)
class ChromeDebugConfig:
    """Configurable Chrome debug port launcher settings."""

    debug_port: int = DEFAULT_DEBUG_PORT
    debug_address: str = DEFAULT_DEBUG_ADDRESS
    chrome_path: str = DEFAULT_CHROME_PATH
    user_data_dir: str = DEFAULT_USER_DATA_DIR
    state_dir: str = DEFAULT_STATE_DIR
    start_url: str = "about:blank"
    wait_seconds: int = 10
    extra_chrome_args: str = ""
    start_script: str = DEFAULT_START_SCRIPT
    stop_script: str = DEFAULT_STOP_SCRIPT

    @property
    def browser_url(self) -> str:
        return f"http://{self.debug_address}:{self.debug_port}"

    def env_overrides(self) -> dict[str, str]:
        return {
            "DEBUG_PORT": str(self.debug_port),
            "DEBUG_ADDRESS": self.debug_address,
            "CHROME_PATH": self.chrome_path,
            "USER_DATA_DIR": self.user_data_dir,
            "STATE_DIR": self.state_dir,
            "START_URL": self.start_url,
            "WAIT_SECONDS": str(self.wait_seconds),
            "EXTRA_CHROME_ARGS": self.extra_chrome_args,
        }


def ensure_chrome_debug(config: ChromeDebugConfig | None = None, timeout: float | None = None) -> ChromeCommandResult:
    """Run the recommended Chrome debug launcher with configurable parameters."""

    cfg = config or ChromeDebugConfig()
    command = ["bash", cfg.start_script]
    env = os.environ.copy()
    overrides = cfg.env_overrides()
    env.update(overrides)
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout or max(15, cfg.wait_seconds + 5),
        check=False,
    )
    return ChromeCommandResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        browser_url=cfg.browser_url,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command=command,
        env_overrides=overrides,
    )


def stop_chrome_debug(config: ChromeDebugConfig | None = None, timeout: float | None = None) -> ChromeCommandResult:
    """Run the recommended Chrome debug stop script with configurable parameters."""

    cfg = config or ChromeDebugConfig()
    command = ["bash", cfg.stop_script]
    env = os.environ.copy()
    overrides = cfg.env_overrides()
    env.update(overrides)
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout or 10,
        check=False,
    )
    return ChromeCommandResult(
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        browser_url=cfg.browser_url,
        stdout=proc.stdout,
        stderr=proc.stderr,
        command=command,
        env_overrides=overrides,
    )
