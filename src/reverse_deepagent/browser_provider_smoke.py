from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from reverse_deepagent.adapters.native_web import create_native_web_runtime
from reverse_deepagent.browser import build_default_browser_provider_registry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_smoke_row

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_ROOT = DEFAULT_REPO_ROOT / "artifacts" / "browser-provider-smoke"
DEFAULT_BROWSER_PROVIDER = "playwright-chromium"
DEFAULT_SMOKE_URL = "about:blank"
BrowserProviderFactory = Callable[..., Any]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture BrowserProvider smoke evidence into workspace/browser-provider-smoke.json. "
            "Default mode is registry metadata-only and does not invoke provider factories, "
            "check availability, launch browsers, or call MCP."
        )
    )
    parser.add_argument("--browser", default=DEFAULT_BROWSER_PROVIDER, help="BrowserProvider id or alias, such as playwright-chromium, cloakbrowser, or remote-cdp.")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT), help="Artifact output root directory.")
    parser.add_argument("--browser-smoke-url", default=DEFAULT_SMOKE_URL, help="URL used only when --launch-browser-smoke is set.")
    parser.add_argument("--include-availability", action="store_true", help="Call provider.is_available(); may import optional SDKs or probe endpoints.")
    parser.add_argument("--launch-browser-smoke", action="store_true", help="Actually start/connect the BrowserProvider and open --browser-smoke-url.")
    parser.add_argument("--browser-url", default=None, help="Existing browser/CDP URL for connect-capable providers such as remote-cdp or CloakBrowser connect mode.")
    parser.add_argument("--browser-profile-dir", default=None, help="Optional BrowserProvider persistent profile directory.")
    parser.add_argument("--browser-headless", action=argparse.BooleanOptionalAction, default=None, help="Run provider headless when supported.")
    parser.add_argument("--browser-executable-path", default=None, help="Optional browser executable path for launch-capable providers.")
    parser.add_argument("--browser-args", default="", help="Extra BrowserProvider args as a shell-split string.")
    parser.add_argument("--browser-humanize", action=argparse.BooleanOptionalAction, default=None, help="Enable humanized provider behavior when supported, such as CloakBrowser.")
    parser.add_argument("--browser-proxy", default=None, help="Optional provider proxy URL. Outputs must keep provider summaries secret-safe.")
    parser.add_argument("--browser-geoip", action="store_true", help="Let provider derive geo settings from proxy/IP when supported.")
    parser.add_argument("--browser-locale", default=None, help="Optional provider locale, such as zh-CN.")
    parser.add_argument("--browser-timezone", default=None, help="Optional provider timezone, such as Asia/Shanghai.")
    parser.add_argument("--request-timeout", type=float, default=10.0, help="Provider request timeout for connect/probe paths.")
    return parser


def _provider_kwargs_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "browser_profile_dir": args.browser_profile_dir,
        "browser_headless": args.browser_headless,
        "browser_executable_path": args.browser_executable_path,
        "browser_args": shlex.split(args.browser_args) if args.browser_args else [],
        "browser_url": args.browser_url,
        "browser_humanize": args.browser_humanize,
        "browser_proxy": args.browser_proxy,
        "browser_geoip": args.browser_geoip,
        "browser_locale": args.browser_locale,
        "browser_timezone": args.browser_timezone,
        "request_timeout": args.request_timeout,
    }


def _metadata_row_for_provider(provider_id: str, *, smoke_url: str) -> tuple[dict[str, Any], str]:
    registry = build_default_browser_provider_registry()
    resolved = registry.resolve(provider_id)
    metadata_by_id = {str(item.get("provider_id")): item for item in registry.list_registration_metadata()}
    metadata = metadata_by_id.get(resolved.provider_id)
    if metadata is None:
        raise ValueError(f"BrowserProvider metadata for {provider_id!r} could not be found after resolution")
    matrix = browser_provider_metadata_matrix_payload(provider_metadata=[metadata], smoke_url=smoke_url)
    row = matrix["providers"][0]
    row["requested_provider_id"] = provider_id
    row["resolved_provider_id"] = resolved.provider_id
    return row, resolved.provider_id


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_browser_provider_smoke(
    *,
    browser: str = DEFAULT_BROWSER_PROVIDER,
    artifact_root: str | Path = DEFAULT_ARTIFACT_ROOT,
    smoke_url: str = DEFAULT_SMOKE_URL,
    include_availability: bool = False,
    launch_browser_smoke: bool = False,
    provider_kwargs: dict[str, Any] | None = None,
    provider_factory: BrowserProviderFactory = create_native_web_runtime,
) -> dict[str, Any]:
    root = Path(artifact_root)
    artifact_path = root / "workspace" / "browser-provider-smoke.json"
    requested_provider = str(browser or DEFAULT_BROWSER_PROVIDER)
    kwargs = dict(provider_kwargs or {})
    if launch_browser_smoke:
        include_availability = True

    if include_availability or launch_browser_smoke:
        row = browser_provider_smoke_row(
            provider_id=requested_provider,
            provider_factory=provider_factory,
            provider_kwargs=kwargs,
            include_availability=include_availability,
            launch_smoke=launch_browser_smoke,
            smoke_url=smoke_url,
        )
        resolved_provider = str(row.get("capabilities", {}).get("provider_id") or requested_provider) if isinstance(row.get("capabilities"), dict) else requested_provider
        provider_factories_invoked = True
        mode = "launch-smoke" if launch_browser_smoke else "availability-check"
    else:
        row, resolved_provider = _metadata_row_for_provider(requested_provider, smoke_url=smoke_url)
        provider_factories_invoked = False
        mode = "metadata-only"

    payload = {
        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
        "artifact_key": "workspace_browser_provider_smoke",
        "artifact_path": str(artifact_path),
        "mode": mode,
        "ok": bool(row.get("ok")),
        "requested_provider_id": requested_provider,
        "resolved_provider_id": resolved_provider,
        "smoke_url": smoke_url,
        "provider": row,
        "side_effect_policy": {
            "metadata_only_by_default": True,
            "availability_check_requested": bool(include_availability),
            "launch_smoke_requested": bool(launch_browser_smoke),
            "provider_factories_invoked": provider_factories_invoked,
            "starts_browser": bool(launch_browser_smoke),
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
            "writes_artifact": True,
            "artifact_only": True,
        },
        "next_action": _next_action(row, include_availability=include_availability, launch_browser_smoke=launch_browser_smoke),
    }
    _write_json(artifact_path, payload)
    return payload


def _next_action(row: dict[str, Any], *, include_availability: bool, launch_browser_smoke: bool) -> str:
    if launch_browser_smoke:
        return "review_browser_provider_launch_smoke_result" if row.get("ok") else "fix_browser_provider_launch_smoke"
    if include_availability:
        return "run_explicit_launch_browser_smoke" if row.get("ok") else "fix_browser_provider_availability"
    return "optionally_run_availability_or_launch_smoke"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = run_browser_provider_smoke(
        browser=args.browser,
        artifact_root=args.artifact_root,
        smoke_url=args.browser_smoke_url,
        include_availability=args.include_availability,
        launch_browser_smoke=args.launch_browser_smoke,
        provider_kwargs=_provider_kwargs_from_args(args),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
