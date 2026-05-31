from __future__ import annotations

from collections.abc import Callable
from typing import Any

from reverse_deepagent.browser.base import BrowserProvider

BROWSER_SMOKE_MATRIX_VERSION = "2026-05-31.lifecycle-baseline"
BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION = "2026-05-31.metadata-compatibility-v1"
DEFAULT_BROWSER_PROVIDER_MATRIX: tuple[str, ...] = (
    "playwright-chromium",
    "cloakbrowser",
    "remote-cdp",
)
CAPABILITY_FLAG_KEYS: tuple[str, ...] = (
    "supports_launch",
    "supports_connect",
    "supports_persistent_context",
    "supports_cdp",
    "supports_playwright_api",
    "supports_proxy",
    "supports_stealth",
    "supports_humanize",
    "supports_extensions",
    "supports_mobile_emulation",
    "supports_network_events",
    "supports_response_body",
    "supports_request_initiator",
    "supports_script_source",
    "supports_websocket_frames",
    "supports_breakpoints",
    "supports_runtime_eval",
    "managed_browser",
)
LIFECYCLE_STAGES: tuple[str, ...] = (
    "configured",
    "capability_described",
    "availability_checked",
    "session_start_requested",
    "session_opened",
    "page_ready",
    "session_closed",
)
BrowserProviderFactory = Callable[..., Any]


def browser_provider_metadata_matrix_payload(
    *,
    provider_metadata: list[dict[str, Any]],
    smoke_url: str = "about:blank",
) -> dict[str, Any]:
    """Build a BrowserProvider matrix from registration metadata only.

    This path is stricter than ``browser_provider_smoke_matrix_payload``: it
    does not call provider factories, availability checks, CDP probes, or launch
    smoke. It is intended for doctor / CI metadata inventory.
    """

    rows = [_browser_provider_metadata_row(item, smoke_url=smoke_url) for item in provider_metadata]
    return {
        "matrix_version": BROWSER_SMOKE_MATRIX_VERSION,
        "provider_ids": [str(item.get("provider_id")) for item in provider_metadata],
        "ok": _matrix_ok(rows),
        "side_effect_policy": {
            "metadata_only_by_default": True,
            "availability_check_requested": False,
            "launch_smoke_requested": False,
            "does_not_use_mcp": True,
            "provider_factories_invoked": False,
        },
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "capability_flags": list(CAPABILITY_FLAG_KEYS),
        "compatibility_rule_version": BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
        "providers": rows,
        "summary": _matrix_summary(rows),
    }


def _browser_provider_metadata_row(metadata: dict[str, Any], *, smoke_url: str) -> dict[str, Any]:
    provider_id = str(metadata.get("provider_id") or "unknown")
    row: dict[str, Any] = {
        "provider_id": provider_id,
        "ok": True,
        "configured": True,
        "available": None,
        "launched": False,
        "launch_requested": False,
        "smoke_url": smoke_url,
        "capabilities": metadata,
        "capability_matrix": _capability_matrix(metadata),
        "compatibility": validate_browser_provider_capability_compatibility(metadata),
        "supported_modes": _supported_modes(metadata),
        "aliases": list(metadata.get("aliases", [])) if isinstance(metadata.get("aliases", []), list) else [],
        "keys": list(metadata.get("keys", [])) if isinstance(metadata.get("keys", []), list) else [],
        "lifecycle": [],
        "smoke": {"requested": False, "ok": None, "status": "skipped", "reason": "metadata-only registry matrix"},
    }
    _append_lifecycle(row, "configured", "ok", "provider registration metadata captured without invoking provider factory")
    _append_lifecycle(row, "capability_described", "ok", "provider capabilities read from registration metadata")
    _append_lifecycle(row, "availability_checked", "not_checked", "availability check is explicit and was not requested")
    _append_lifecycle(row, "session_start_requested", "skipped", "launch smoke was not requested")
    return row


def browser_provider_smoke_matrix_payload(
    *,
    provider_ids: tuple[str, ...] | list[str] | None = None,
    provider_factory: BrowserProviderFactory,
    provider_kwargs: dict[str, Any] | None = None,
    include_availability: bool = False,
    launch_smoke: bool = False,
    smoke_url: str = "about:blank",
) -> dict[str, Any]:
    """Build a normalized BrowserProvider smoke matrix.

    By default this is side-effect free: it instantiates providers and reads
    capability metadata only. Availability checks can import optional provider
    dependencies or probe remote endpoints, and launch smoke can start/connect a
    browser session, so both are explicit knobs.
    """

    selected_provider_ids = tuple(provider_ids or DEFAULT_BROWSER_PROVIDER_MATRIX)
    kwargs = dict(provider_kwargs or {})
    rows = [
        browser_provider_smoke_row(
            provider_id=provider_id,
            provider_factory=provider_factory,
            provider_kwargs=kwargs,
            include_availability=include_availability,
            launch_smoke=launch_smoke,
            smoke_url=smoke_url,
        )
        for provider_id in selected_provider_ids
    ]
    return {
        "matrix_version": BROWSER_SMOKE_MATRIX_VERSION,
        "provider_ids": list(selected_provider_ids),
        "ok": _matrix_ok(rows),
        "side_effect_policy": {
            "metadata_only_by_default": True,
            "availability_check_requested": include_availability,
            "launch_smoke_requested": launch_smoke,
            "does_not_use_mcp": True,
        },
        "lifecycle_stages": list(LIFECYCLE_STAGES),
        "capability_flags": list(CAPABILITY_FLAG_KEYS),
        "compatibility_rule_version": BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
        "providers": rows,
        "summary": _matrix_summary(rows),
    }


def browser_provider_smoke_row(
    *,
    provider_id: str,
    provider_factory: BrowserProviderFactory,
    provider_kwargs: dict[str, Any] | None = None,
    include_availability: bool = False,
    launch_smoke: bool = False,
    smoke_url: str = "about:blank",
) -> dict[str, Any]:
    """Return one provider smoke row with normalized lifecycle events."""

    kwargs = dict(provider_kwargs or {})
    row: dict[str, Any] = {
        "provider_id": provider_id,
        "ok": False,
        "configured": False,
        "available": None,
        "launched": False,
        "launch_requested": bool(launch_smoke),
        "smoke_url": smoke_url,
        "lifecycle": [],
    }
    provider: BrowserProvider | None = None
    try:
        provider = provider_factory(browser=provider_id, **kwargs).browser_provider
        row["configured"] = True
        _append_lifecycle(row, "configured", "ok", "provider factory returned a BrowserProvider")
        capabilities = provider.describe().model_dump(mode="json")
        row["capabilities"] = capabilities
        row["capability_matrix"] = _capability_matrix(capabilities)
        row["compatibility"] = validate_browser_provider_capability_compatibility(capabilities)
        row["supported_modes"] = _supported_modes(capabilities)
        _append_lifecycle(row, "capability_described", "ok", "provider capabilities captured without launching")
    except Exception as exc:
        row["error"] = str(exc)
        row["supported_modes"] = []
        row["capability_matrix"] = {}
        _append_lifecycle(row, "configured", "failed", str(exc))
        row["smoke"] = {"requested": bool(launch_smoke), "ok": False, "status": "configuration_failed"}
        return row

    availability_error: str | None = None
    available: bool | None = None
    if include_availability:
        try:
            available = bool(provider.is_available())
            row["available"] = available
            _append_lifecycle(
                row,
                "availability_checked",
                "ok" if available else "unavailable",
                "provider dependency or endpoint is available" if available else "provider dependency or endpoint is unavailable",
            )
        except Exception as exc:
            available = False
            availability_error = str(exc)
            row["available"] = False
            row["availability_error"] = availability_error
            _append_lifecycle(row, "availability_checked", "failed", availability_error)
    else:
        _append_lifecycle(row, "availability_checked", "not_checked", "availability check is explicit and was not requested")

    if not launch_smoke:
        row["ok"] = bool(available) if include_availability else True
        row["smoke"] = {"requested": False, "ok": None, "status": "skipped", "reason": "launch_smoke=false"}
        _append_lifecycle(row, "session_start_requested", "skipped", "launch smoke was not requested")
        return row

    if include_availability and not available:
        row["ok"] = False
        row["smoke"] = {
            "requested": True,
            "ok": False,
            "status": "blocked",
            "reason": availability_error or "provider unavailable",
        }
        _append_lifecycle(row, "session_start_requested", "blocked", "provider unavailable")
        return row

    try:
        _append_lifecycle(row, "session_start_requested", "ok", "provider.start() requested")
        session = provider.start()
        _append_lifecycle(row, "session_opened", "ok", "browser session opened")
        page = session.get_active_page() or session.new_page(smoke_url)
        if page.url == "about:blank" and smoke_url and smoke_url != "about:blank":
            page.goto(smoke_url)
        title = page.title()
        page_count = len(session.list_pages())
        row["launched"] = True
        row["ok"] = True
        row["smoke"] = {
            "requested": True,
            "ok": True,
            "status": "passed",
            "url": page.url,
            "title": title,
            "page_count": page_count,
        }
        _append_lifecycle(row, "page_ready", "ok", "smoke page is reachable")
    except Exception as exc:
        row["ok"] = False
        row["smoke"] = {"requested": True, "ok": False, "status": "failed", "error": str(exc), "url": smoke_url}
        _append_lifecycle(row, "page_ready", "failed", str(exc))
    finally:
        try:
            provider.stop()
            _append_lifecycle(row, "session_closed", "ok", "provider.stop() completed")
        except Exception as exc:
            row["ok"] = False
            row.setdefault("smoke", {"requested": True, "ok": False, "status": "failed"})["close_error"] = str(exc)
            _append_lifecycle(row, "session_closed", "failed", str(exc))
    return row


def legacy_browser_provider_payload_from_smoke_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project one matrix row into the historical doctor browser_provider shape."""

    payload: dict[str, Any] = {
        "ok": bool(row.get("ok")),
        "browser": row.get("provider_id"),
        "available": bool(row.get("available")) if row.get("available") is not None else bool(row.get("ok")),
        "launched": bool(row.get("launched")),
        "launch_requested": bool(row.get("launch_requested")),
        "capabilities": row.get("capabilities", {}),
        "smoke_matrix": row,
    }
    if row.get("availability_error"):
        payload["availability_error"] = row["availability_error"]
    if row.get("error"):
        payload["error"] = row["error"]
    smoke = row.get("smoke") if isinstance(row.get("smoke"), dict) else {}
    if row.get("available") is False and not row.get("launch_requested"):
        payload["hint"] = "Install the provider optional dependency or choose another BrowserProvider. Metadata was collected without launching a browser."
    elif row.get("available") is True and not row.get("launch_requested"):
        payload["hint"] = "Provider dependency is available. Add --launch-browser-smoke to start a real browser smoke test."
    if row.get("launch_requested"):
        payload["smoke"] = smoke
    return payload


def _capability_matrix(capabilities: dict[str, Any]) -> dict[str, bool]:
    return {key: bool(capabilities.get(key)) for key in CAPABILITY_FLAG_KEYS}


def _supported_modes(capabilities: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    if capabilities.get("supports_launch"):
        modes.append("launch")
    if capabilities.get("supports_connect"):
        modes.append("connect")
    if capabilities.get("supports_persistent_context"):
        modes.append("persistent-context")
    if capabilities.get("supports_cdp"):
        modes.append("cdp")
    if capabilities.get("supports_runtime_eval"):
        modes.append("runtime-eval")
    if capabilities.get("supports_breakpoints"):
        modes.append("debugger")
    return modes


def validate_browser_provider_capability_compatibility(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Validate BrowserProvider capability combinations without side effects.

    This is intentionally metadata-only. It does not inspect provider objects,
    import optional SDKs, probe CDP endpoints, or launch browsers. The goal is
    to flag impossible or suspicious capability combinations before a provider
    is used by native-web.
    """

    provider_id = str(capabilities.get("provider_id") or "unknown")
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    def enabled(key: str) -> bool:
        return bool(capabilities.get(key))

    def add_error(code: str, message: str) -> None:
        errors.append({"code": code, "message": message})

    def add_warning(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    if provider_id == "unknown":
        add_error("missing_provider_id", "capabilities must include a stable provider_id")

    has_lifecycle_mode = enabled("supports_launch") or enabled("supports_connect")
    if enabled("supports_breakpoints") and not enabled("supports_cdp"):
        add_error("breakpoints_require_cdp", "supports_breakpoints requires supports_cdp for Debugger domain access")
    if enabled("supports_persistent_context") and not has_lifecycle_mode:
        add_error(
            "persistent_context_requires_lifecycle",
            "supports_persistent_context requires launch or connect lifecycle support",
        )
    for feature_key, code in (
        ("supports_response_body", "response_body_requires_network_or_cdp"),
        ("supports_request_initiator", "request_initiator_requires_network_or_cdp"),
        ("supports_websocket_frames", "websocket_frames_require_network_or_cdp"),
    ):
        if enabled(feature_key) and not (enabled("supports_network_events") or enabled("supports_cdp")):
            add_error(code, f"{feature_key} requires supports_network_events or supports_cdp")

    if enabled("supports_runtime_eval") and not (enabled("supports_playwright_api") or enabled("supports_cdp")):
        add_warning(
            "runtime_eval_without_known_transport",
            "supports_runtime_eval is declared without supports_playwright_api or supports_cdp",
        )
    if enabled("supports_script_source") and not (
        enabled("supports_cdp") or enabled("supports_network_events") or enabled("supports_runtime_eval")
    ):
        add_warning(
            "script_source_without_known_acquisition_path",
            "supports_script_source is declared without CDP, network events, or runtime eval",
        )
    if enabled("supports_cdp") and not has_lifecycle_mode:
        add_warning("cdp_without_lifecycle_mode", "supports_cdp is declared but provider cannot launch or connect")
    if enabled("managed_browser") and not enabled("supports_launch"):
        add_warning("managed_browser_without_launch", "managed_browser usually implies supports_launch")
    if any(enabled(key) for key in CAPABILITY_FLAG_KEYS if key != "managed_browser") and not has_lifecycle_mode:
        add_warning("capabilities_without_lifecycle_mode", "runtime capabilities are declared but provider cannot launch or connect")

    status = "error" if errors else "warning" if warnings else "compatible"
    return {
        "rule_version": BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
        "provider_id": provider_id,
        "status": status,
        "ok": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def _append_lifecycle(row: dict[str, Any], stage: str, status: str, message: str) -> None:
    row.setdefault("lifecycle", []).append({"stage": stage, "status": status, "message": message})


def _matrix_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compatibility_items = [row.get("compatibility") for row in rows if isinstance(row.get("compatibility"), dict)]
    return {
        "provider_count": len(rows),
        "configured_count": sum(1 for row in rows if row.get("configured")),
        "available_count": sum(1 for row in rows if row.get("available") is True),
        "launch_requested_count": sum(1 for row in rows if row.get("launch_requested")),
        "launched_count": sum(1 for row in rows if row.get("launched")),
        "failed_count": sum(1 for row in rows if row.get("ok") is False and row.get("launch_requested")),
        "metadata_ok_count": sum(1 for row in rows if row.get("configured") and row.get("capabilities")),
        "compatibility": {
            "compatible_count": sum(1 for item in compatibility_items if item.get("status") == "compatible"),
            "warning_count": sum(1 for item in compatibility_items if item.get("status") == "warning"),
            "error_count": sum(1 for item in compatibility_items if item.get("status") == "error"),
        },
    }


def _matrix_ok(rows: list[dict[str, Any]]) -> bool:
    return all(bool(row.get("configured")) and bool(row.get("compatibility", {}).get("ok", True)) for row in rows)
