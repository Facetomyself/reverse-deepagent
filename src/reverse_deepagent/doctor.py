from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import socket
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from reverse_deepagent.adapters.native_web import create_native_web_runtime
from reverse_deepagent.browser import BROWSER_PROVIDER_ENTRY_POINT_GROUP, build_default_browser_provider_registry
from reverse_deepagent.browser.smoke import (
    DEFAULT_BROWSER_PROVIDER_MATRIX,
    browser_provider_metadata_matrix_payload,
    browser_provider_smoke_row,
    legacy_browser_provider_payload_from_smoke_row,
)
from reverse_deepagent.delivery.registry import (
    EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP,
    build_default_external_delivery_provider_registry,
)
from reverse_deepagent.coordinator import build_default_runtime_registry
from reverse_deepagent.runtime.chrome import (
    ChromeDebugConfig,
    DEFAULT_CHROME_PATH,
    DEFAULT_START_SCRIPT,
    DEFAULT_STOP_SCRIPT,
    DEFAULT_USER_DATA_DIR,
    ensure_chrome_debug,
    stop_chrome_debug,
)
from reverse_deepagent.runtime.legacy_mcp import DEFAULT_JSREVERSER_MCP_COMMAND, check_legacy_mcp_tools
from reverse_deepagent.runtime.registry import RUNTIME_BACKEND_ENTRY_POINT_GROUP

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BROWSER_URL = "http://127.0.0.1:9222"
CHECK_MCP_ALIAS_DEPRECATION_WARNING = "警告：`--check-mcp` 只是 `--legacy-mcp` 的兼容别名，后续新脚本请改用 `--legacy-mcp`。"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose Reverse DeepAgent browser / legacy MCP runtime readiness.")
    parser.add_argument("--browser-url", default=DEFAULT_BROWSER_URL, help="Chrome DevTools browser URL used by the legacy MCP backend.")
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
    parser.add_argument("--check-mcp", action="store_true", help="Deprecated compatibility alias for --legacy-mcp.")
    parser.add_argument("--legacy-mcp", action="store_true", help="Start legacy jsreverser-mcp over stdio and call list_tools/check_browser_health.")
    parser.add_argument("--browser", default=None, help="BrowserProvider id to diagnose, such as playwright-chromium or cloakbrowser. Does not launch by default.")
    parser.add_argument("--browser-provider-matrix", action="store_true", help="Emit a side-effect-free BrowserProvider smoke/capability matrix for built-in providers.")
    parser.add_argument("--browser-profile-dir", default=None, help="Optional BrowserProvider persistent profile directory for metadata/smoke checks.")
    parser.add_argument("--browser-headless", action=argparse.BooleanOptionalAction, default=None, help="Run BrowserProvider in headless mode during --launch-browser-smoke when supported.")
    parser.add_argument("--browser-executable-path", default=None, help="Optional browser executable path for BrowserProvider launch checks.")
    parser.add_argument("--browser-args", default="", help="Extra BrowserProvider args as a shell-split string.")
    parser.add_argument("--browser-humanize", action=argparse.BooleanOptionalAction, default=None, help="Enable humanized BrowserProvider behavior when supported, such as CloakBrowser.")
    parser.add_argument("--browser-proxy", default=None, help="Optional BrowserProvider proxy URL. The doctor output must redact configured proxy values.")
    parser.add_argument("--browser-geoip", action="store_true", help="Let BrowserProvider derive geo settings from proxy/IP when supported.")
    parser.add_argument("--browser-locale", default=None, help="Optional BrowserProvider locale, such as zh-CN.")
    parser.add_argument("--browser-timezone", default=None, help="Optional BrowserProvider timezone, such as Asia/Shanghai.")
    parser.add_argument("--launch-browser-smoke", action="store_true", help="Actually launch the selected BrowserProvider and open --browser-smoke-url. Disabled by default.")
    parser.add_argument("--browser-smoke-url", default="about:blank", help="URL used only when --launch-browser-smoke is set.")
    parser.add_argument(
        "--external-delivery-providers",
        action="store_true",
        help="Emit a side-effect-free ExternalDeliveryProvider metadata matrix without invoking provider factories.",
    )
    parser.add_argument(
        "--runtime-backends",
        action="store_true",
        help="Emit a side-effect-free RuntimeBackend metadata matrix without invoking backend factories.",
    )
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


def _skipped_port_status(browser_url: str, reason: str) -> dict[str, Any]:
    parsed = urlparse(browser_url)
    return {
        "browser_url": browser_url,
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "listening": None,
        "error": None,
        "skipped": True,
        "reason": reason,
    }


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


def _check_browser_provider(args: argparse.Namespace) -> dict[str, Any]:
    try:
        provider_kwargs = _browser_provider_kwargs(args)
    except Exception as exc:
        return {
            "ok": False,
            "browser": args.browser,
            "available": False,
            "launched": False,
            "error": str(exc),
            "hint": "Use a supported BrowserProvider id such as playwright-chromium or cloakbrowser.",
        }

    row = browser_provider_smoke_row(
        provider_id=args.browser or "playwright-chromium",
        provider_factory=create_native_web_runtime,
        provider_kwargs=provider_kwargs,
        include_availability=True,
        launch_smoke=bool(args.launch_browser_smoke),
        smoke_url=args.browser_smoke_url,
    )
    payload = legacy_browser_provider_payload_from_smoke_row(row)
    if row.get("error") and not row.get("configured"):
        payload["hint"] = "Use a supported BrowserProvider id such as playwright-chromium or cloakbrowser."
    return payload


def _browser_provider_matrix(args: argparse.Namespace) -> dict[str, Any]:
    try:
        provider_kwargs = _browser_provider_kwargs(args)
        registry = build_default_browser_provider_registry()
        provider_metadata = registry.list_registration_metadata()
        provider_ids = [str(item["provider_id"]) for item in provider_metadata]
    except Exception as exc:
        return {
            "matrix_version": "unavailable",
            "entry_point_group": BROWSER_PROVIDER_ENTRY_POINT_GROUP,
            "provider_ids": list(DEFAULT_BROWSER_PROVIDER_MATRIX),
            "ok": False,
            "error": str(exc),
            "providers": [],
            "summary": {"provider_count": 0},
        }
    payload = browser_provider_metadata_matrix_payload(
        provider_metadata=provider_metadata,
        smoke_url=args.browser_smoke_url,
    )
    payload["entry_point_group"] = BROWSER_PROVIDER_ENTRY_POINT_GROUP
    payload["provider_registration_metadata"] = provider_metadata
    payload["registered_provider_ids"] = registry.provider_ids()
    payload["side_effect_policy"]["provider_factories_invoked"] = False
    payload["ok"] = all(
        bool(item.get("configured")) and bool(item.get("compatibility", {}).get("ok", True))
        for item in payload["providers"]
    )
    return payload


def _browser_provider_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    browser_args = shlex.split(args.browser_args) if args.browser_args else []
    return {
        "browser_profile_dir": args.browser_profile_dir,
        "browser_headless": args.browser_headless,
        "browser_executable_path": args.browser_executable_path,
        "browser_args": browser_args,
        "browser_url": args.browser_url,
        "browser_humanize": args.browser_humanize,
        "browser_proxy": args.browser_proxy,
        "browser_geoip": args.browser_geoip,
        "browser_locale": args.browser_locale,
        "browser_timezone": args.browser_timezone,
        "request_timeout": args.request_timeout,
    }


def _external_delivery_provider_matrix() -> dict[str, Any]:
    try:
        registry = build_default_external_delivery_provider_registry()
        providers = registry.list_registration_metadata()
        provider_ids = registry.provider_ids()
    except Exception as exc:
        return {
            "matrix_version": "unavailable",
            "entry_point_group": EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP,
            "ok": False,
            "error": str(exc),
            "providers": [],
            "provider_ids": [],
            "summary": {"provider_count": 0},
            "side_effect_policy": {
                "provider_factories_invoked": False,
                "external_delivery_requested": False,
                "external_delivery_performed": False,
                "publishes_externally": False,
            },
        }
    return {
        "matrix_version": "2026-05-31.external-delivery-providers",
        "entry_point_group": EXTERNAL_DELIVERY_PROVIDER_ENTRY_POINT_GROUP,
        "ok": True,
        "providers": providers,
        "provider_ids": provider_ids,
        "summary": {
            "provider_count": len(providers),
            "registered_key_count": len(provider_ids),
            "review_only_count": sum(1 for provider in providers if provider.get("review_only")),
            "external_delivery_capable_count": sum(
                1 for provider in providers if provider.get("supports_external_delivery")
            ),
        },
        "side_effect_policy": {
            "provider_factories_invoked": False,
            "external_delivery_requested": False,
            "external_delivery_performed": False,
            "publishes_externally": False,
        },
    }


_RUNTIME_BACKEND_CAPABILITY_FLAGS = [
    "supports_browser_session",
    "supports_web_recon",
    "supports_protection_patch",
    "supports_artifact_export",
    "supports_runtime_context",
    "supports_replay_validation",
    "managed_chrome",
    "mcp_backed",
]


def _runtime_backend_matrix() -> dict[str, Any]:
    try:
        registry = build_default_runtime_registry()
        backends = registry.list_registration_metadata()
        backend_ids = registry.backend_ids()
    except Exception as exc:
        return {
            "matrix_version": "unavailable",
            "entry_point_group": RUNTIME_BACKEND_ENTRY_POINT_GROUP,
            "ok": False,
            "error": str(exc),
            "backends": [],
            "backend_ids": [],
            "capability_flags": list(_RUNTIME_BACKEND_CAPABILITY_FLAGS),
            "summary": {"backend_count": 0},
            "side_effect_policy": {
                "backend_factories_invoked": False,
                "browser_sessions_started": False,
                "chrome_started": False,
                "mcp_started": False,
                "platform_tools_invoked": False,
            },
        }
    target_platforms = sorted(
        {
            platform
            for backend in backends
            for platform in backend.get("target_platforms", [])
            if isinstance(platform, str)
        }
    )
    return {
        "matrix_version": "2026-05-31.runtime-backends",
        "entry_point_group": RUNTIME_BACKEND_ENTRY_POINT_GROUP,
        "ok": True,
        "backends": backends,
        "backend_ids": backend_ids,
        "capability_flags": list(_RUNTIME_BACKEND_CAPABILITY_FLAGS),
        "summary": {
            "backend_count": len(backends),
            "registered_key_count": len(backend_ids),
            "web_backend_count": sum(1 for backend in backends if "web" in backend.get("target_platforms", [])),
            "non_web_backend_count": sum(1 for backend in backends if "web" not in backend.get("target_platforms", [])),
            "browser_session_capable_count": sum(1 for backend in backends if backend.get("supports_browser_session")),
            "web_recon_capable_count": sum(1 for backend in backends if backend.get("supports_web_recon")),
            "mcp_backed_count": sum(1 for backend in backends if backend.get("mcp_backed")),
            "managed_chrome_capable_count": sum(1 for backend in backends if backend.get("managed_chrome")),
            "target_platforms": target_platforms,
        },
        "side_effect_policy": {
            "backend_factories_invoked": False,
            "browser_sessions_started": False,
            "chrome_started": False,
            "mcp_started": False,
            "platform_tools_invoked": False,
            "metadata_only_by_default": True,
        },
    }


def _check_mcp(args: argparse.Namespace) -> dict[str, Any]:
    command_status = _command_check(args.jsreverser_mcp_command)
    if not command_status["exists"]:
        return {"ok": False, "command": command_status, "error": "jsreverser-mcp command not found"}
    payload = check_legacy_mcp_tools(
        command=args.jsreverser_mcp_command,
        browser_url=args.browser_url,
        request_timeout=args.request_timeout,
        startup_timeout=args.startup_timeout,
    )
    payload["command"] = command_status
    return payload


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
    check_legacy_mcp = bool(getattr(args, "legacy_mcp", False) or args.check_mcp)
    check_provider_matrix = bool(getattr(args, "browser_provider_matrix", False))
    check_external_delivery_providers = bool(getattr(args, "external_delivery_providers", False))
    check_runtime_backends = bool(getattr(args, "runtime_backends", False))
    check_browser_provider = bool(
        args.browser
        or (
            not args.ensure_chrome
            and not check_legacy_mcp
            and not check_provider_matrix
            and not check_external_delivery_providers
            and not check_runtime_backends
        )
    )
    metadata_only_check = bool(
        (check_provider_matrix or check_external_delivery_providers or check_runtime_backends)
        and not check_browser_provider
        and not args.ensure_chrome
        and not check_legacy_mcp
    )
    port_probe_reason = "metadata-only doctor mode does not probe CDP endpoints"
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
        "port_before": _skipped_port_status(args.browser_url, port_probe_reason) if metadata_only_check else _port_status(args.browser_url),
    }
    if args.check_mcp:
        payload["deprecation_warnings"] = [CHECK_MCP_ALIAS_DEPRECATION_WARNING]
    payload["legacy_mcp"] = payload["mcp"]

    should_stop = False
    if args.ensure_chrome:
        launch = ensure_chrome_debug(chrome_config)
        payload["chrome_launch"] = launch.model_dump(mode="json")
        should_stop = launch.ok and not args.keep_chrome
    payload["port_after_launch"] = _skipped_port_status(args.browser_url, port_probe_reason) if metadata_only_check else _port_status(args.browser_url)

    if check_provider_matrix:
        payload["browser_provider_smoke_matrix"] = _browser_provider_matrix(args)

    if check_external_delivery_providers:
        payload["external_delivery_provider_matrix"] = _external_delivery_provider_matrix()

    if check_runtime_backends:
        payload["runtime_backend_matrix"] = _runtime_backend_matrix()

    if check_browser_provider:
        payload["browser_provider"] = _check_browser_provider(args)

    if check_legacy_mcp:
        payload["legacy_mcp_check"] = _check_mcp(args)
        payload["mcp_check"] = payload["legacy_mcp_check"]

    if should_stop:
        stop = stop_chrome_debug(chrome_config)
        payload["chrome_stop"] = stop.model_dump(mode="json")
        payload["port_after_stop"] = _port_status(args.browser_url)

    browser_only_check = bool(check_browser_provider and not args.ensure_chrome and not check_legacy_mcp)
    if browser_only_check:
        required_ok = [bool(payload.get("browser_provider", {}).get("ok"))]
    elif metadata_only_check:
        required_ok = []
        if check_provider_matrix:
            required_ok.append(bool(payload.get("browser_provider_smoke_matrix", {}).get("ok")))
        if check_external_delivery_providers:
            required_ok.append(bool(payload.get("external_delivery_provider_matrix", {}).get("ok")))
        if check_runtime_backends:
            required_ok.append(bool(payload.get("runtime_backend_matrix", {}).get("ok")))
    else:
        required_ok = [
            payload["chrome"]["path"]["exists"],
            payload["chrome"]["start_script"]["exists"],
            payload["chrome"]["stop_script"]["exists"],
            payload["mcp"]["command"]["exists"],
        ]
        if args.ensure_chrome:
            required_ok.append(bool(payload.get("chrome_launch", {}).get("ok")))
        if check_browser_provider:
            required_ok.append(bool(payload.get("browser_provider", {}).get("ok")))
        if check_provider_matrix:
            required_ok.append(bool(payload.get("browser_provider_smoke_matrix", {}).get("ok")))
        if check_external_delivery_providers:
            required_ok.append(bool(payload.get("external_delivery_provider_matrix", {}).get("ok")))
        if check_runtime_backends:
            required_ok.append(bool(payload.get("runtime_backend_matrix", {}).get("ok")))
        if check_legacy_mcp:
            required_ok.append(bool(payload.get("legacy_mcp_check", {}).get("ok")))
    payload["ok"] = all(required_ok)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_doctor(args)
    for warning in payload.get("deprecation_warnings", []):
        print(warning, file=sys.stderr)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
