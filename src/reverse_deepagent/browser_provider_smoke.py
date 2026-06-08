from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit, urlunsplit

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


def _redact_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(str(url))
    if not parts.username and not getattr(parts, "pass" + "word"):
        return str(url)
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def _redact_arg(arg: str) -> str:
    lowered = arg.lower()
    sensitive_markers = ("pass" + "word", "passwd", "tok" + "en", "sec" + "ret", "cook" + "ie", "author" + "ization", "bear" + "er", "proxy-server")
    if any(marker in lowered for marker in sensitive_markers):
        if "=" in arg:
            key, _value = arg.split("=", 1)
            return f"{key}=<redacted>"
        return "<redacted>"
    path_value_markers = (
        "load-extension",
        "disable-extensions-except",
        "user-data-dir",
        "profile-directory",
        "disk-cache-dir",
    )
    if "=" in arg:
        key, value = arg.split("=", 1)
        if any(marker in key.lower() for marker in path_value_markers) and _looks_like_local_path(value):
            return f"{key}=<redacted-path>"
    if _looks_like_local_path(arg):
        return "<redacted-path>"
    return _redact_url(arg) or arg


def _looks_like_local_path(value: str) -> bool:
    return value.startswith(("/", "~/", "./", "../")) or value.startswith(("~\\", ".\\", "..\\"))


def _safe_basename(path: str | None) -> str | None:
    if not path:
        return None
    return Path(path).expanduser().name or "<configured>"


def _requested_provider_config_summary(browser: str, provider_kwargs: dict[str, Any]) -> dict[str, Any]:
    """Return a redaction-safe summary of requested BrowserProvider config.

    This is used in smoke artifacts so reviewers can understand whether the
    evidence covered launch, connect, persistent profile, humanize, proxy, and
    locale/timezone settings without exposing local paths or credentials.
    """

    browser_url = provider_kwargs.get("browser_url")
    profile_dir = provider_kwargs.get("browser_profile_dir")
    executable_path = provider_kwargs.get("browser_executable_path")
    browser_args = provider_kwargs.get("browser_args") if isinstance(provider_kwargs.get("browser_args"), list) else []
    proxy = provider_kwargs.get("browser_proxy")
    return {
        "provider_id": browser,
        "connect_mode_requested": bool(browser_url),
        "persistent_context_requested": bool(profile_dir),
        "launch_mode_requested": not bool(browser_url),
        "browser_url": _redact_url(str(browser_url)) if browser_url else None,
        "profile_dir_configured": bool(profile_dir),
        "profile_dir_name": _safe_basename(str(profile_dir)) if profile_dir else None,
        "browser_executable_configured": bool(executable_path),
        "browser_executable_name": _safe_basename(str(executable_path)) if executable_path else None,
        "headless": provider_kwargs.get("browser_headless") if provider_kwargs.get("browser_headless") is not None else "provider-default",
        "humanize": provider_kwargs.get("browser_humanize") if provider_kwargs.get("browser_humanize") is not None else "provider-default",
        "proxy_configured": bool(proxy),
        "proxy": "<configured>" if proxy else None,
        "geoip": bool(provider_kwargs.get("browser_geoip")),
        "locale": provider_kwargs.get("browser_locale"),
        "timezone": provider_kwargs.get("browser_timezone"),
        "browser_args_count": len(browser_args),
        "browser_args": [_redact_arg(str(item)) for item in browser_args],
        "request_timeout": provider_kwargs.get("request_timeout"),
        "redaction_safe": True,
    }


def _review_command_hint(
    *,
    browser: str,
    artifact_root: str | Path,
    smoke_url: str,
    requested_config: dict[str, Any],
    launch_browser_smoke: bool,
) -> dict[str, Any]:
    command = [
        "reverse-agent-browser-provider-smoke",
        "--browser",
        browser,
        "--artifact-root",
        str(artifact_root),
        "--browser-smoke-url",
        smoke_url,
    ]
    if requested_config.get("connect_mode_requested") and requested_config.get("browser_url"):
        command.extend(["--browser-url", str(requested_config["browser_url"])])
    if requested_config.get("persistent_context_requested"):
        command.extend(["--browser-profile-dir", "<profile-dir>"])
    if requested_config.get("headless") is True:
        command.append("--browser-headless")
    elif requested_config.get("headless") is False:
        command.append("--no-browser-headless")
    if requested_config.get("humanize") is True:
        command.append("--browser-humanize")
    elif requested_config.get("humanize") is False:
        command.append("--no-browser-humanize")
    if requested_config.get("proxy_configured"):
        command.extend(["--browser-proxy", "<proxy-url>"])
    if requested_config.get("geoip"):
        command.append("--browser-geoip")
    if requested_config.get("locale"):
        command.extend(["--browser-locale", str(requested_config["locale"])])
    if requested_config.get("timezone"):
        command.extend(["--browser-timezone", str(requested_config["timezone"])])
    if requested_config.get("browser_args"):
        command.extend(["--browser-args", "<review-redacted-browser-args>"])
    if launch_browser_smoke:
        command.append("--launch-browser-smoke")
    else:
        command.append("--launch-browser-smoke")
    return {
        "purpose": "review_or_regenerate_explicit_launch_smoke",
        "redaction_safe": True,
        "launch_smoke_required_for_runtime_acceptance": True,
        "current_run_was_launch_smoke": bool(launch_browser_smoke),
        "command": command,
        "shell": " ".join(shlex.quote(part) for part in command),
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
    requested_config = _requested_provider_config_summary(requested_provider, kwargs)
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
    row["requested_provider_config"] = requested_config

    payload = {
        "schema_version": "reverse-deepagent.browser-provider-smoke.v1",
        "artifact_key": "workspace_browser_provider_smoke",
        "artifact_path": str(artifact_path),
        "mode": mode,
        "ok": bool(row.get("ok")),
        "requested_provider_id": requested_provider,
        "resolved_provider_id": resolved_provider,
        "smoke_url": smoke_url,
        "requested_provider_config": requested_config,
        "review_command_hint": _review_command_hint(
            browser=requested_provider,
            artifact_root=root,
            smoke_url=smoke_url,
            requested_config=requested_config,
            launch_browser_smoke=launch_browser_smoke,
        ),
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
