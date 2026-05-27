from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from reverse_deepagent.coordinator import run_reverse_pipeline
from reverse_deepagent.fixtures.web_sign import FIXTURE_PROFILE_VALUES, start_fixture_server
from reverse_deepagent.runtime.chrome import ChromeDebugConfig, DEFAULT_CHROME_PATH, DEFAULT_START_SCRIPT, DEFAULT_STOP_SCRIPT

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts/fixture-smoke"


def build_fixture_smoke_parser() -> argparse.ArgumentParser:
    """Build the parser for the localhost fixture smoke command."""

    parser = argparse.ArgumentParser(description="Run reverse pipeline against the local sign fixture.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for the fixture server.")
    parser.add_argument("--port", type=int, default=0, help="Bind port for the fixture server. Default 0 picks a free port.")
    parser.add_argument("--profile", choices=FIXTURE_PROFILE_VALUES, default="default", help="Fixture algorithm/profile to smoke.")
    parser.add_argument("--runtime", choices=["mock", "mcp"], default="mock", help="Runtime backend for the reverse pipeline.")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT), help="Artifact output root directory.")
    parser.add_argument("--ensure-chrome", action="store_true", help="Before using --runtime mcp, start a managed Chrome debug session.")
    parser.add_argument("--keep-chrome", action="store_true", help="When used with --ensure-chrome, keep managed Chrome running after the smoke.")
    parser.add_argument("--chrome-debug-port", type=int, default=9445, help="Chrome remote debugging port.")
    parser.add_argument("--chrome-debug-address", default="127.0.0.1", help="Chrome remote debugging bind address.")
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH, help="Chrome executable path.")
    parser.add_argument("--chrome-user-data-dir", default="/tmp/reverse-agent-chrome-fixture-smoke", help="Chrome user data directory.")
    parser.add_argument("--chrome-extra-args", default="", help="Extra Chrome args passed to the launcher as a shell-split string.")
    parser.add_argument("--chrome-wait-seconds", type=int, default=10, help="Seconds to wait for Chrome debug listener.")
    parser.add_argument("--chrome-start-script", default=DEFAULT_START_SCRIPT, help="Chrome debug launcher script path.")
    parser.add_argument("--chrome-stop-script", default=DEFAULT_STOP_SCRIPT, help="Chrome debug stop script path.")
    return parser


def main_fixture_smoke(argv: Sequence[str] | None = None) -> int:
    """Console entrypoint for fixture-backed reverse pipeline smoke."""

    args = build_fixture_smoke_parser().parse_args(argv)
    fixture = start_fixture_server(host=args.host, port=args.port, profile=args.profile)
    try:
        task_text = f"{fixture.base_url}/ 使用 {args.profile} profile 找 sign 入口，并给出下一步建议"
        chrome_config = ChromeDebugConfig(
            debug_port=args.chrome_debug_port,
            debug_address=args.chrome_debug_address,
            chrome_path=args.chrome_path,
            user_data_dir=args.chrome_user_data_dir,
            start_url="about:blank",
            extra_chrome_args=args.chrome_extra_args,
            wait_seconds=args.chrome_wait_seconds,
            start_script=args.chrome_start_script,
            stop_script=args.chrome_stop_script,
        )
        output = run_reverse_pipeline(
            task_text=task_text,
            artifact_root=Path(args.artifact_root),
            runtime_kind=args.runtime,
            chrome_config=chrome_config,
            ensure_chrome=args.ensure_chrome,
            keep_chrome=args.keep_chrome,
        )
        payload = {
            "fixture": {
                "base_url": fixture.base_url,
                "profile": fixture.profile.value,
                "page_url": f"{fixture.base_url}/",
                "app_js_url": f"{fixture.base_url}/app.js",
                "api_url": f"{fixture.base_url}/api/search",
            },
            "pipeline": output.model_dump(mode="json", exclude_none=True),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        fixture.close()


if __name__ == "__main__":
    raise SystemExit(main_fixture_smoke())
