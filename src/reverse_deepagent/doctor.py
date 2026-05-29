from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from reverse_deepagent.adapters.jsreverser import DEFAULT_JSREVERSER_MCP_COMMAND
from reverse_deepagent.runtime.chrome import (
    ChromeDebugConfig,
    DEFAULT_CHROME_PATH,
    DEFAULT_START_SCRIPT,
    DEFAULT_STOP_SCRIPT,
    DEFAULT_USER_DATA_DIR,
    ensure_chrome_debug,
    stop_chrome_debug,
)
from reverse_deepagent.runtime.mcp_stdio import McpBridgeError, StdioMcpBridge

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BROWSER_URL = "http://127.0.0.1:9222"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose Reverse DeepAgent browser / MCP runtime readiness.")
    parser.add_argument("--browser-url", default=DEFAULT_BROWSER_URL, help="Chrome DevTools browser URL used by MCP.")
    parser.add_argument("--chrome-debug-port", type=int, default=9222, help="Chrome remote debugging port.")
    parser.add_argument("--chrome-debug-address", default="127.0.0.1", help="Chrome remote debugging bind address.")
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH, help="Chrome executable path.")
    parser.add_argument("--chrome-user-data-dir", default=DEFAULT_USER_DATA_DIR, help="Chrome user data directory.")
    parser.add_argument("--chrome-start-url", default="about:blank", help="Initial URL for managed Chrome.")
    parser.add_argument("--chrome-extra-args", default="", help="Extra Chrome args passed to the launcher as a shell-split string.")
    parser.add_argument("--chrome-wait-seconds", type=int, default=10, help="Seconds to wait for Chrome debug listener.")
    parser.add_argument("--chrome-start-script", default=DEFAULT_START_SCRIPT, help="Chrome debug launcher script path.")
    parser.add_argument("--chrome-stop-script", default=DEFAULT_STOP_SCRIPT, help="Chrome debug stop script path.")
    parser.add_argument("--jsreverser-mcp-command", default=DEFAULT_JSREVERSER_MCP_COMMAND, help="Path to the jsreverser-mcp executable.")
    parser.add_argument("--ensure-chrome", action="store_true", help="Start the managed Chrome debug listener before checks.")
    parser.add_argument("--keep-chrome", action="store_true", help="Keep Chrome running when --ensure-chrome starts it.")
    parser.add_argument("--check-mcp", action="store_true", help="Start jsreverser-mcp over stdio and call list_tools/check_browser_health.")
    parser.add_argument("--request-timeout", type=float, default=10.0, help="MCP request timeout in seconds.")
    parser.add_argument("--startup-timeout", type=float, default=10.0, help="MCP startup timeout in seconds.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required checks fail.")
    return parser


def _path_check(path: str) -> dict[str, Any]:
    expanded = Path(path).expanduser()
    return {
        "path": str(expanded),
        "exists": expanded.exists(),
        "is_file": expanded.is_file(),
        "executable": expanded.exists() and expanded.is_file() and bool(expanded.stat().st_mode & 0o111),
    }


def _command_check(command: str) -> dict[str, Any]:
    resolved = shutil.which(command) if "/" not in command else command
    exists = Path(resolved).exists() if resolved else False
    return {
        "command": command,
        "resolved": resolved,
        "exists": bool(exists),
        "executable": bool(resolved and exists and Path(resolved).is_file() and bool(Path(resolved).stat().st_mode & 0o111)),
    }


def _port_status(browser_url: str) -> dict[str, Any]:
    parsed = urlparse(browser_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    listening = False
    error = None
    try:
        with socket.create_connection((host, port), timeout=1.0):
            listening = True
    except OSError as exc:
        error = str(exc)
    return {"browser_url": browser_url, "host": host, "port": port, "listening": listening, "error": error}


def _console_script_status() -> dict[str, Any]:
    scripts = {
        "reverse-agent-demo": shutil.which("reverse-agent-demo"),
        "reverse-agent-fixture-smoke": shutil.which("reverse-agent-fixture-smoke"),
        "reverse-agent-openai-smoke": shutil.which("reverse-agent-openai-smoke"),
        "reverse-agent-doctor": shutil.which("reverse-agent-doctor"),
    }
    local_bin = DEFAULT_REPO_ROOT / ".venv/bin"
    local_scripts = {name: str(local_bin / name) for name in scripts}
    return {
        "path_entries_include_repo_venv": str(local_bin) in os.environ.get("PATH", "").split(os.pathsep),
        "scripts_on_path": scripts,
        "repo_venv_scripts": {
            name: {"path": path, "exists": Path(path).exists()} for name, path in local_scripts.items()
        },
        "hint": f'Run `source "{local_bin}/activate"` or call scripts through absolute paths if scripts_on_path are null.',
    }


def _check_mcp(args: argparse.Namespace) -> dict[str, Any]:
    command_status = _command_check(args.jsreverser_mcp_command)
    if not command_status["exists"]:
        return {"ok": False, "command": command_status, "error": "jsreverser-mcp command not found"}
    bridge = StdioMcpBridge(
        command=[args.jsreverser_mcp_command, "--browserUrl", args.browser_url],
        request_timeout=args.request_timeout,
        startup_timeout=args.startup_timeout,
    )
    try:
        with bridge:
            tools = bridge.list_tools()
            health = bridge.invoke("check_browser_health", {})
        tool_names = [item.get("name") for item in tools.get("tools", []) if isinstance(item, dict)]
        return {
            "ok": True,
            "command": command_status,
            "tool_count": len(tool_names),
            "tool_sample": tool_names[:20],
            "health": health,
        }
    except (McpBridgeError, OSError, RuntimeError) as exc:
        return {
            "ok": False,
            "command": command_status,
            "error": str(exc),
            "stderr": bridge.get_stderr()[-2000:],
        }


def run_doctor(args: argparse.Namespace) -> dict[str, Any]:
    chrome_config = ChromeDebugConfig(
        debug_port=args.chrome_debug_port,
        debug_address=args.chrome_debug_address,
        chrome_path=args.chrome_path,
        user_data_dir=args.chrome_user_data_dir,
        start_url=args.chrome_start_url,
        extra_chrome_args=args.chrome_extra_args,
        wait_seconds=args.chrome_wait_seconds,
        start_script=args.chrome_start_script,
        stop_script=args.chrome_stop_script,
    )
    payload: dict[str, Any] = {
        "ok": True,
        "repo_root": str(DEFAULT_REPO_ROOT),
        "python": sys.executable,
        "console_scripts": _console_script_status(),
        "chrome": {
            "path": _path_check(args.chrome_path),
            "start_script": _path_check(args.chrome_start_script),
            "stop_script": _path_check(args.chrome_stop_script),
            "browser_url": args.browser_url,
        },
        "mcp": {
            "command": _command_check(args.jsreverser_mcp_command),
        },
        "port_before": _port_status(args.browser_url),
    }

    should_stop = False
    if args.ensure_chrome:
        launch = ensure_chrome_debug(chrome_config)
        payload["chrome_launch"] = launch.model_dump(mode="json")
        should_stop = launch.ok and not args.keep_chrome
    payload["port_after_launch"] = _port_status(args.browser_url)

    if args.check_mcp:
        payload["mcp_check"] = _check_mcp(args)

    if should_stop:
        stop = stop_chrome_debug(chrome_config)
        payload["chrome_stop"] = stop.model_dump(mode="json")
        payload["port_after_stop"] = _port_status(args.browser_url)

    required_ok = [
        payload["chrome"]["path"]["exists"],
        payload["chrome"]["start_script"]["exists"],
        payload["chrome"]["stop_script"]["exists"],
        payload["mcp"]["command"]["exists"],
    ]
    if args.ensure_chrome:
        required_ok.append(bool(payload.get("chrome_launch", {}).get("ok")))
    if args.check_mcp:
        required_ok.append(bool(payload.get("mcp_check", {}).get("ok")))
    payload["ok"] = all(required_ok)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_doctor(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
