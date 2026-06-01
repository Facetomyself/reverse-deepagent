from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Sequence

from reverse_deepagent.coordinator import legacy_mcp_alias_warning, run_platform_pipeline, run_reverse_pipeline
from reverse_deepagent.runtime.chrome import ChromeDebugConfig, DEFAULT_CHROME_PATH, DEFAULT_START_SCRIPT, DEFAULT_STOP_SCRIPT, DEFAULT_USER_DATA_DIR
from reverse_deepagent.runtime.legacy_mcp import DEFAULT_JSREVERSER_MCP_COMMAND, LegacyMcpPluginUnavailableError, legacy_mcp_install_guidance

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts"


def _parse_artifact_key_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    keys = [item.strip() for item in value.split(",") if item.strip()]
    return list(dict.fromkeys(keys))


def build_demo_parser() -> argparse.ArgumentParser:
    """Build the parser for the deterministic reverse pipeline demo."""

    parser = argparse.ArgumentParser(description="Run the Reverse DeepAgent deterministic coordinator demo.")
    parser.add_argument(
        "--task-text",
        default="https://example.com/search 找 sign 入口，并给出下一步建议",
        help="Free-form reverse task description.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Artifact output root directory.",
    )
    parser.add_argument(
        "--runtime",
        default="mock",
        help=(
            "Runtime backend to use. Common values: mock, native-web, legacy-mcp, playwright-cli, chrome-cdp, browser-cli. "
            "The old mcp value remains a deprecated compatibility alias for legacy-mcp and prints a warning. "
            "Aliases are resolved through the runtime registry."
        ),
    )
    parser.add_argument(
        "--ensure-chrome",
        action="store_true",
        help="Before using --runtime legacy-mcp or the deprecated mcp alias, run the recommended parameterized Chrome debug launcher.",
    )
    parser.add_argument(
        "--keep-chrome",
        action="store_true",
        help="When used with --ensure-chrome, keep the managed Chrome running after the demo. Default is to stop it.",
    )
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
    parser.add_argument("--playwright-command", default=None, help="Playwright CLI command for --runtime playwright-cli.")
    parser.add_argument("--cdp-browser-url", default=None, help="Existing Chrome DevTools browser URL for --runtime chrome-cdp. Does not launch Chrome.")
    parser.add_argument("--browser-cli-command", default=None, help="Generic browser CLI command for --runtime browser-cli.")
    parser.add_argument("--lightweight-request-timeout", type=float, default=None, help="Timeout for lightweight backend command / HTTP probes.")
    parser.add_argument("--browser", default=None, help="BrowserProvider id for --runtime native-web, such as playwright-chromium or cloakbrowser.")
    parser.add_argument("--browser-profile-dir", default=None, help="Optional BrowserProvider persistent profile directory.")
    parser.add_argument("--browser-headless", action=argparse.BooleanOptionalAction, default=None, help="Run BrowserProvider in headless mode when supported.")
    parser.add_argument("--browser-executable-path", default=None, help="Optional browser executable path for BrowserProvider launch.")
    parser.add_argument("--browser-args", default="", help="Extra BrowserProvider args as a shell-split string.")
    parser.add_argument("--browser-humanize", action=argparse.BooleanOptionalAction, default=None, help="Enable humanized BrowserProvider behavior when supported, such as CloakBrowser.")
    parser.add_argument("--browser-proxy", default=None, help="Optional BrowserProvider proxy URL. Avoid printing credentials in shared logs.")
    parser.add_argument("--browser-geoip", action="store_true", help="Let BrowserProvider derive geo settings from proxy/IP when supported.")
    parser.add_argument("--browser-locale", default=None, help="Optional BrowserProvider locale, such as zh-CN.")
    parser.add_argument("--browser-timezone", default=None, help="Optional BrowserProvider timezone, such as Asia/Shanghai.")
    parser.add_argument("--enable-workspace-dual-write", action="store_true", help="Opt in to writing registered workspace artifacts to both legacy and future foldered paths.")
    parser.add_argument(
        "--workspace-dual-write-artifact-keys",
        default="",
        help="Optional comma-separated artifact keys that limit --enable-workspace-dual-write to a reviewed pilot scope.",
    )
    return parser


def main_demo(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for running the deterministic reverse pipeline."""

    parser = build_demo_parser()
    args = parser.parse_args(argv)
    warning = legacy_mcp_alias_warning(args.runtime)
    if warning:
        print(warning, file=sys.stderr)
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
    try:
        output = run_reverse_pipeline(
            task_text=args.task_text,
            artifact_root=Path(args.artifact_root),
            runtime_kind=args.runtime,
            chrome_config=chrome_config,
            ensure_chrome=args.ensure_chrome,
            keep_chrome=args.keep_chrome,
            mcp_command=args.jsreverser_mcp_command,
            playwright_command=args.playwright_command,
            cdp_browser_url=args.cdp_browser_url,
            browser_cli_command=args.browser_cli_command,
            request_timeout=args.lightweight_request_timeout,
            browser=args.browser,
            browser_profile_dir=args.browser_profile_dir,
            browser_headless=args.browser_headless,
            browser_executable_path=args.browser_executable_path,
            browser_args=shlex.split(args.browser_args) if args.browser_args else None,
            browser_humanize=args.browser_humanize,
            browser_proxy=args.browser_proxy,
            browser_geoip=args.browser_geoip,
            browser_locale=args.browser_locale,
            browser_timezone=args.browser_timezone,
            enable_workspace_dual_write=args.enable_workspace_dual_write,
            workspace_dual_write_artifact_keys=_parse_artifact_key_list(args.workspace_dual_write_artifact_keys),
        )
    except LegacyMcpPluginUnavailableError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "install_guidance": legacy_mcp_install_guidance()},
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(output.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))
    return 0


def build_platform_parser() -> argparse.ArgumentParser:
    """Build the parser for the platform-neutral runtime pipeline."""

    parser = argparse.ArgumentParser(description="Run the Reverse DeepAgent platform-neutral runtime pipeline.")
    parser.add_argument(
        "--task-text",
        default="android://demo 找 sign 入口，并给出平台 runtime 下一步建议",
        help="Free-form reverse task description.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(DEFAULT_ARTIFACT_ROOT),
        help="Artifact output root directory.",
    )
    parser.add_argument(
        "--runtime",
        default="android-adb",
        help="Runtime backend id or alias, such as android-adb, ios-simulator, or mini-program-devtools.",
    )
    parser.add_argument("--android-adb-command", default=None, help="ADB command path/name for android-adb runtime.")
    parser.add_argument("--android-device-serial", default=None, help="Optional Android device serial.")
    parser.add_argument("--android-package-name", default=None, help="Optional Android package name.")
    parser.add_argument("--ios-xcrun-command", default=None, help="xcrun command path/name for ios-simulator runtime.")
    parser.add_argument("--ios-device-id", default=None, help="Optional iOS simulator/device id.")
    parser.add_argument("--ios-bundle-id", default=None, help="Optional iOS bundle id.")
    parser.add_argument("--mini-program-devtools-command", default=None, help="Optional vendor mini-program devtools CLI path/name.")
    parser.add_argument("--mini-program-vendor", default=None, help="Mini-program vendor, for example wechat or alipay.")
    parser.add_argument("--mini-program-project-path", default=None, help="Optional mini-program local project path.")
    parser.add_argument("--enable-workspace-dual-write", action="store_true", help="Opt in to writing registered workspace artifacts to both legacy and future foldered paths.")
    parser.add_argument(
        "--workspace-dual-write-artifact-keys",
        default="",
        help="Optional comma-separated artifact keys that limit --enable-workspace-dual-write to a reviewed pilot scope.",
    )
    return parser


def main_platform(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for the platform-neutral runtime pipeline."""

    parser = build_platform_parser()
    args = parser.parse_args(argv)
    runtime_kwargs = {
        "android_adb_command": args.android_adb_command,
        "android_device_serial": args.android_device_serial,
        "android_package_name": args.android_package_name,
        "ios_xcrun_command": args.ios_xcrun_command,
        "ios_device_id": args.ios_device_id,
        "ios_bundle_id": args.ios_bundle_id,
        "mini_program_devtools_command": args.mini_program_devtools_command,
        "mini_program_vendor": args.mini_program_vendor,
        "mini_program_project_path": args.mini_program_project_path,
    }
    output = run_platform_pipeline(
        task_text=args.task_text,
        artifact_root=Path(args.artifact_root),
        runtime_kind=args.runtime,
        enable_workspace_dual_write=args.enable_workspace_dual_write,
        workspace_dual_write_artifact_keys=_parse_artifact_key_list(args.workspace_dual_write_artifact_keys),
        **runtime_kwargs,
    )
    print(json.dumps(output.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Top-level console entrypoint alias for the demo pipeline."""

    return main_demo(argv)
