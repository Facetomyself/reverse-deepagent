from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from reverse_deepagent.adapters.jsreverser import DEFAULT_JSREVERSER_MCP_COMMAND
from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.runtime.chrome import ChromeDebugConfig, DEFAULT_CHROME_PATH, DEFAULT_START_SCRIPT, DEFAULT_STOP_SCRIPT, DEFAULT_USER_DATA_DIR

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts"


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
        choices=["mock", "mcp"],
        default="mock",
        help="Runtime backend to use. mock is deterministic; mcp starts jsreverser-mcp over stdio.",
    )
    parser.add_argument(
        "--ensure-chrome",
        action="store_true",
        help="Before using --runtime mcp, run the recommended parameterized Chrome debug launcher.",
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
    return parser


def main_demo(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for running the deterministic reverse pipeline."""

    parser = build_demo_parser()
    args = parser.parse_args(argv)
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
    output = run_reverse_pipeline(
        task_text=args.task_text,
        artifact_root=Path(args.artifact_root),
        runtime_kind=args.runtime,
        chrome_config=chrome_config,
        ensure_chrome=args.ensure_chrome,
        keep_chrome=args.keep_chrome,
        mcp_command=args.jsreverser_mcp_command,
    )
    print(json.dumps(output.model_dump(mode="json", exclude_none=True), ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Top-level console entrypoint alias for the demo pipeline."""

    return main_demo(argv)
