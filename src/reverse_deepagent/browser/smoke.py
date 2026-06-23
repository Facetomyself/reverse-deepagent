from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserProvider

BROWSER_SMOKE_MATRIX_VERSION = "2026-05-31.lifecycle-baseline"
BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION = "2026-05-31.metadata-compatibility-v1"
BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION = "2026-06-05.production-readiness-v5"
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


@dataclass(frozen=True, slots=True)
class BrowserProviderCompatibilityRule:
    """One metadata-only BrowserProvider capability compatibility rule."""

    rule_id: str
    severity: str
    message: str
    when_all: tuple[str, ...] = field(default_factory=tuple)
    when_any: tuple[str, ...] = field(default_factory=tuple)
    requires_all: tuple[str, ...] = field(default_factory=tuple)
    requires_any: tuple[str, ...] = field(default_factory=tuple)

    def applies_to(self, capabilities: dict[str, Any]) -> bool:
        if self.when_all and not all(_capability_enabled(capabilities, key) for key in self.when_all):
            return False
        if self.when_any and not any(_capability_enabled(capabilities, key) for key in self.when_any):
            return False
        return True

    def satisfied_by(self, capabilities: dict[str, Any]) -> bool:
        if self.requires_all and not all(_capability_enabled(capabilities, key) for key in self.requires_all):
            return False
        if self.requires_any and not any(_capability_enabled(capabilities, key) for key in self.requires_any):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "when_all": list(self.when_all),
            "when_any": list(self.when_any),
            "requires_all": list(self.requires_all),
            "requires_any": list(self.requires_any),
        }


@dataclass(frozen=True, slots=True)
class BrowserProviderProductionReadinessRule:
    """One metadata-only provider-specific production readiness rule."""

    rule_id: str
    severity: str
    message: str
    provider_ids: tuple[str, ...] = field(default_factory=tuple)
    transports: tuple[str, ...] = field(default_factory=tuple)
    requires_all: tuple[str, ...] = field(default_factory=tuple)
    metadata_equals: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    required_metadata_keys: tuple[str, ...] = field(default_factory=tuple)

    def applies_to(self, capabilities: dict[str, Any]) -> bool:
        provider_id = str(capabilities.get("provider_id") or "")
        transport = str(capabilities.get("transport") or "")
        if self.provider_ids and provider_id not in self.provider_ids:
            return False
        if self.transports and transport not in self.transports:
            return False
        return True

    def missing_metadata_keys(self, profile: dict[str, Any]) -> list[str]:
        return [key for key in self.required_metadata_keys if not str(profile.get(key) or "").strip()]

    def satisfied_by(self, capabilities: dict[str, Any], profile: dict[str, Any]) -> bool:
        if self.requires_all and not all(_capability_enabled(capabilities, key) for key in self.requires_all):
            return False
        if self.missing_metadata_keys(profile):
            return False
        for key, expected_value in self.metadata_equals:
            if str(profile.get(key) or "") != expected_value:
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "provider_ids": list(self.provider_ids),
            "transports": list(self.transports),
            "requires_all": list(self.requires_all),
            "metadata_equals": {key: value for key, value in self.metadata_equals},
            "required_metadata_keys": list(self.required_metadata_keys),
        }


BROWSER_PROVIDER_PRODUCTION_READINESS_RULES: tuple[BrowserProviderProductionReadinessRule, ...] = (
    BrowserProviderProductionReadinessRule(
        rule_id="playwright_chromium_lifecycle_declared",
        severity="warning",
        provider_ids=("playwright-chromium",),
        transports=("playwright",),
        requires_all=(
            "supports_launch",
            "supports_connect",
            "supports_persistent_context",
            "supports_cdp",
            "supports_playwright_api",
            "managed_browser",
        ),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-availability-or-launch-smoke"),
            ("profile_lifecycle", "temporary-context-or-user-data-dir"),
            ("session_recovery", "connect-over-cdp-or-launch-new-session"),
        ),
        message=(
            "playwright-chromium should declare launch/connect/persistent-context/CDP lifecycle support "
            "and the reviewed availability-or-launch-smoke metadata used by the native browser baseline"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="remote_cdp_attach_contract_declared",
        severity="warning",
        provider_ids=("remote-cdp",),
        transports=("remote-cdp",),
        requires_all=(
            "supports_connect",
            "supports_cdp",
            "supports_request_initiator",
            "supports_script_source",
            "supports_websocket_frames",
            "supports_breakpoints",
            "supports_runtime_eval",
        ),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-endpoint-probe"),
            ("profile_lifecycle", "external-browser-owned"),
            ("session_recovery", "connect-existing-endpoint"),
        ),
        required_metadata_keys=("endpoint_security_policy",),
        message=(
            "remote-cdp should declare attach-only CDP lifecycle support and explicit endpoint-probe "
            "metadata without implying browser ownership or launch control"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="cloakbrowser_production_lifecycle_declared",
        severity="warning",
        provider_ids=("cloakbrowser",),
        transports=("cloakbrowser-playwright",),
        requires_all=(
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
        ),
        metadata_equals=(
            ("readiness_tier", "production-ready"),
            ("health_check_mode", "optional-sdk-or-connect-endpoint"),
            ("profile_lifecycle", "persistent-context-supported"),
            ("session_recovery", "connect-over-cdp-or-persistent-context"),
        ),
        required_metadata_keys=("stealth_policy",),
        message=(
            "cloakbrowser should keep production lifecycle metadata aligned with its launch, persistent-context, "
            "connect, stealth, humanize, proxy, and CDP capability contract"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="hosted_cdp_reference_lifecycle_declared",
        severity="warning",
        provider_ids=("hosted-cdp-reference",),
        requires_all=("supports_launch", "supports_connect", "supports_cdp", "managed_browser"),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-reference-allocation-and-cdp-contract-smoke"),
            ("session_recovery", "session-id-reattach-or-endpoint-connect"),
        ),
        required_metadata_keys=("allocation_lifecycle_policy", "endpoint_security_policy"),
        message=(
            "hosted-cdp-reference should declare launch/connect/CDP lifecycle support and the reviewed "
            "allocation/attach/release readiness metadata used by production provider packages"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="browserless_cdp_contract_declared",
        severity="warning",
        provider_ids=("browserless-cdp",),
        transports=("browserless-cdp",),
        requires_all=(
            "supports_connect",
            "supports_cdp",
            "supports_response_body",
            "supports_request_initiator",
            "supports_script_source",
            "supports_websocket_frames",
            "supports_breakpoints",
            "supports_runtime_eval",
            "managed_browser",
        ),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-browserless-cdp-contract-smoke"),
            ("profile_lifecycle", "browserless-session-owned"),
            ("session_recovery", "explicit-endpoint-or-reconnect-url"),
        ),
        required_metadata_keys=("account_boundary_policy", "endpoint_security_policy"),
        message=(
            "browserless-cdp should declare a reviewed hosted-CDP connect contract, Browserless-owned "
            "session lifecycle metadata, and explicit endpoint smoke requirements without probing endpoints "
            "during metadata listing"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="browserbase_cdp_contract_declared",
        severity="warning",
        provider_ids=("browserbase-cdp",),
        transports=("browserbase-cdp",),
        requires_all=(
            "supports_launch",
            "supports_connect",
            "supports_cdp",
            "supports_response_body",
            "supports_request_initiator",
            "supports_script_source",
            "supports_websocket_frames",
            "supports_breakpoints",
            "supports_runtime_eval",
            "managed_browser",
        ),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-browserbase-session-smoke"),
            ("profile_lifecycle", "browserbase-session-owned"),
            ("session_recovery", "explicit-connect-url-or-created-session-connect-url"),
        ),
        required_metadata_keys=("account_boundary_policy", "endpoint_security_policy", "allocation_lifecycle_policy"),
        message=(
            "browserbase-cdp should declare explicit Browserbase Session creation / connectUrl attach "
            "metadata, account-boundary controls, and smoke evidence requirements without reading API keys "
            "or creating sessions during metadata listing"
        ),
    ),
    BrowserProviderProductionReadinessRule(
        rule_id="antidetect_cdp_contract_declared",
        severity="warning",
        provider_ids=("antidetect-cdp",),
        transports=("antidetect-cdp",),
        requires_all=(
            "supports_launch",
            "supports_connect",
            "supports_persistent_context",
            "supports_cdp",
            "supports_proxy",
            "supports_stealth",
            "supports_humanize",
            "supports_extensions",
            "supports_mobile_emulation",
            "supports_response_body",
            "supports_request_initiator",
            "supports_script_source",
            "supports_websocket_frames",
            "supports_breakpoints",
            "supports_runtime_eval",
            "managed_browser",
        ),
        metadata_equals=(
            ("readiness_tier", "review-required"),
            ("health_check_mode", "explicit-antidetect-cdp-contract-smoke"),
            ("profile_lifecycle", "anti-detect-service-profile-owned"),
            ("session_recovery", "explicit-endpoint-or-profile-session-reattach"),
        ),
        required_metadata_keys=(
            "stealth_policy",
            "account_boundary_policy",
            "endpoint_security_policy",
            "allocation_lifecycle_policy",
            "allocator_contract",
            "profile_persistence_policy",
        ),
        message=(
            "antidetect-cdp should declare a review-gated hosted anti-detect CDP allocation / attach contract "
            "with reviewed stealth/profile/account-boundary/endpoint/allocation metadata; metadata listing must "
            "not read secrets, call allocators, allocate vendor sessions, probe endpoints, or start browsers"
        ),
    ),
)


BROWSER_PROVIDER_COMPATIBILITY_RULES: tuple[BrowserProviderCompatibilityRule, ...] = (
    BrowserProviderCompatibilityRule(
        rule_id="breakpoints_require_cdp",
        severity="error",
        when_all=("supports_breakpoints",),
        requires_all=("supports_cdp",),
        message="supports_breakpoints requires supports_cdp for Debugger domain access",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="persistent_context_requires_lifecycle",
        severity="error",
        when_all=("supports_persistent_context",),
        requires_any=("supports_launch", "supports_connect"),
        message="supports_persistent_context requires launch or connect lifecycle support",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="response_body_requires_network_or_cdp",
        severity="error",
        when_all=("supports_response_body",),
        requires_any=("supports_network_events", "supports_cdp"),
        message="supports_response_body requires supports_network_events or supports_cdp",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="request_initiator_requires_network_or_cdp",
        severity="error",
        when_all=("supports_request_initiator",),
        requires_any=("supports_network_events", "supports_cdp"),
        message="supports_request_initiator requires supports_network_events or supports_cdp",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="websocket_frames_require_network_or_cdp",
        severity="error",
        when_all=("supports_websocket_frames",),
        requires_any=("supports_network_events", "supports_cdp"),
        message="supports_websocket_frames requires supports_network_events or supports_cdp",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="runtime_eval_without_known_transport",
        severity="warning",
        when_all=("supports_runtime_eval",),
        requires_any=("supports_playwright_api", "supports_cdp"),
        message="supports_runtime_eval is declared without supports_playwright_api or supports_cdp",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="script_source_without_known_acquisition_path",
        severity="warning",
        when_all=("supports_script_source",),
        requires_any=("supports_cdp", "supports_network_events", "supports_runtime_eval"),
        message="supports_script_source is declared without CDP, network events, or runtime eval",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="cdp_without_lifecycle_mode",
        severity="warning",
        when_all=("supports_cdp",),
        requires_any=("supports_launch", "supports_connect"),
        message="supports_cdp is declared but provider cannot launch or connect",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="managed_browser_without_launch",
        severity="warning",
        when_all=("managed_browser",),
        requires_all=("supports_launch",),
        message="managed_browser usually implies supports_launch",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="humanize_requires_page_control_transport",
        severity="warning",
        when_all=("supports_humanize",),
        requires_any=("supports_playwright_api", "supports_cdp"),
        message="supports_humanize should expose Playwright or CDP page control",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="mobile_emulation_requires_page_control_transport",
        severity="warning",
        when_all=("supports_mobile_emulation",),
        requires_any=("supports_playwright_api", "supports_cdp"),
        message="supports_mobile_emulation should expose Playwright or CDP emulation controls",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="extensions_require_launch_or_persistent_context",
        severity="warning",
        when_all=("supports_extensions",),
        requires_any=("supports_launch", "supports_persistent_context"),
        message="supports_extensions usually requires launch or persistent-context control",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="proxy_requires_launch_or_managed_browser",
        severity="warning",
        when_all=("supports_proxy",),
        requires_any=("supports_launch", "managed_browser"),
        message="provider-level proxy configuration usually requires launch control or a managed browser service",
    ),
    BrowserProviderCompatibilityRule(
        rule_id="capabilities_without_lifecycle_mode",
        severity="warning",
        when_any=tuple(key for key in CAPABILITY_FLAG_KEYS if key != "managed_browser"),
        requires_any=("supports_launch", "supports_connect"),
        message="runtime capabilities are declared but provider cannot launch or connect",
    ),
)


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
        "production_readiness_version": BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION,
        "compatibility_rules": list_browser_provider_compatibility_rules(),
        "production_readiness_rules": list_browser_provider_production_readiness_rules(),
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
        "production_readiness": browser_provider_production_readiness(metadata),
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
        "production_readiness_version": BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION,
        "compatibility_rules": list_browser_provider_compatibility_rules(),
        "production_readiness_rules": list_browser_provider_production_readiness_rules(),
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
        row["production_readiness"] = browser_provider_production_readiness(capabilities)
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


def list_browser_provider_compatibility_rules() -> list[dict[str, Any]]:
    """Return metadata-only BrowserProvider compatibility rule catalog."""

    return [rule.to_dict() for rule in BROWSER_PROVIDER_COMPATIBILITY_RULES]


def list_browser_provider_production_readiness_rules() -> list[dict[str, Any]]:
    """Return metadata-only provider-specific production readiness rule catalog."""

    return [rule.to_dict() for rule in BROWSER_PROVIDER_PRODUCTION_READINESS_RULES]


def browser_provider_production_readiness(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Evaluate provider production-readiness metadata without side effects.

    The evaluator intentionally uses only serialized provider capabilities. It
    does not import optional SDKs, call provider factories, probe CDP endpoints,
    launch browsers, check availability, or depend on MCP. Providers can use
    this metadata to document production seams while the coordinator remains
    provider-neutral.
    """

    provider_id = str(capabilities.get("provider_id") or "unknown")
    metadata = capabilities.get("production_readiness")
    profile = metadata if isinstance(metadata, dict) else {}
    checks: list[dict[str, Any]] = []
    missing_metadata: list[str] = []
    warnings: list[str] = []

    def add_check(check_id: str, status: str, message: str, *, required_key: str | None = None, extra: dict[str, Any] | None = None) -> None:
        check = {"check_id": check_id, "status": status, "message": message}
        if extra:
            check.update(extra)
        checks.append(check)
        if status == "missing" and required_key:
            missing_metadata.append(required_key)
        if status == "warn":
            warnings.append(check_id)

    if not profile:
        add_check("production_metadata_present", "missing", "production_readiness metadata is missing", required_key="production_readiness")
    else:
        add_check("production_metadata_present", "pass", "production_readiness metadata is present")

    required_fields = (
        "health_check_mode",
        "profile_lifecycle",
        "session_recovery",
        "intended_use",
        "side_effect_boundary",
    )
    for field_name in required_fields:
        value = str(profile.get(field_name) or "").strip()
        add_check(
            f"{field_name}_declared",
            "pass" if value else "missing",
            f"{field_name} is declared" if value else f"{field_name} is not declared",
            required_key=field_name if not value else None,
        )

    lifecycle_supported = bool(capabilities.get("supports_launch") or capabilities.get("supports_connect"))
    add_check(
        "lifecycle_entrypoint_available",
        "pass" if lifecycle_supported else "warn",
        "provider can launch or connect" if lifecycle_supported else "provider cannot launch or connect; runtime use requires template replacement",
    )

    if capabilities.get("supports_persistent_context"):
        add_check(
            "persistent_profile_lifecycle_documented",
            "pass" if profile.get("profile_lifecycle") else "missing",
            "persistent profile lifecycle is documented"
            if profile.get("profile_lifecycle")
            else "supports_persistent_context requires profile_lifecycle metadata",
            required_key=None if profile.get("profile_lifecycle") else "profile_lifecycle",
        )
    else:
        add_check("persistent_profile_lifecycle_documented", "not-applicable", "provider does not claim persistent context support")

    if capabilities.get("supports_proxy"):
        add_check(
            "proxy_policy_documented",
            "pass" if profile.get("proxy_policy") else "missing",
            "provider-level proxy policy is documented" if profile.get("proxy_policy") else "supports_proxy requires proxy_policy metadata",
            required_key=None if profile.get("proxy_policy") else "proxy_policy",
        )
    else:
        add_check("proxy_policy_documented", "not-applicable", "provider does not claim provider-level proxy support")

    if capabilities.get("supports_extensions"):
        add_check(
            "extension_policy_documented",
            "pass" if profile.get("extension_policy") else "missing",
            "extension lifecycle policy is documented" if profile.get("extension_policy") else "supports_extensions requires extension_policy metadata",
            required_key=None if profile.get("extension_policy") else "extension_policy",
        )
    else:
        add_check("extension_policy_documented", "not-applicable", "provider does not claim extension support")

    if capabilities.get("supports_humanize"):
        add_check(
            "humanize_policy_documented",
            "pass" if profile.get("humanize_policy") else "missing",
            "humanized interaction policy is documented" if profile.get("humanize_policy") else "supports_humanize requires humanize_policy metadata",
            required_key=None if profile.get("humanize_policy") else "humanize_policy",
        )
    else:
        add_check("humanize_policy_documented", "not-applicable", "provider does not claim humanized interaction support")

    readiness_tier = str(profile.get("readiness_tier") or "").strip()
    if readiness_tier in {"template-only", "metadata-incomplete"}:
        add_check("readiness_tier", "missing", f"provider is declared as {readiness_tier}", required_key="production_provider_replacement")
    elif readiness_tier in {"fixture-only", "review-required"}:
        add_check("readiness_tier", "warn", f"provider is declared as {readiness_tier}")
    elif readiness_tier == "production-ready":
        add_check("readiness_tier", "pass", "provider declares production-ready metadata")
    elif readiness_tier:
        add_check("readiness_tier", "warn", f"provider declares unrecognized readiness_tier={readiness_tier}")
    else:
        add_check("readiness_tier", "missing", "readiness_tier is not declared", required_key="readiness_tier")

    provider_specific_rules = _evaluate_provider_specific_readiness_rules(capabilities, profile)
    for rule_result in provider_specific_rules:
        add_check(
            rule_result["check_id"],
            rule_result["status"],
            rule_result["message"],
            extra={
                "missing_metadata_keys": list(rule_result.get("missing_metadata_keys", [])),
                "rule_id": rule_result.get("rule_id"),
                "severity": rule_result.get("severity"),
            },
        )
        if rule_result["status"] == "missing":
            missing_metadata.extend(str(key) for key in rule_result.get("missing_metadata_keys", []))

    unique_missing = sorted(set(missing_metadata))
    unique_warnings = sorted(set(warnings))
    pass_count = sum(1 for item in checks if item["status"] == "pass")
    applicable_count = sum(1 for item in checks if item["status"] != "not-applicable")
    score = int(round((pass_count / applicable_count) * 100)) if applicable_count else 100
    if unique_missing:
        status = "metadata-incomplete"
    elif unique_warnings:
        status = "review-required"
    else:
        status = "production-ready"
    return {
        "version": BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION,
        "provider_id": provider_id,
        "status": status,
        "score": score,
        "readiness_tier": readiness_tier or "unspecified",
        "checks": checks,
        "warnings": unique_warnings,
        "missing_metadata": unique_missing,
        "side_effect_policy": {
            "metadata_only": True,
            "provider_factory_invoked": False,
            "availability_checked": False,
            "launch_smoke_requested": False,
            "cdp_endpoint_probed": False,
            "starts_browser": False,
            "calls_mcp": False,
        },
    }


def _evaluate_provider_specific_readiness_rules(capabilities: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for rule in BROWSER_PROVIDER_PRODUCTION_READINESS_RULES:
        if not rule.applies_to(capabilities):
            continue
        missing_keys = rule.missing_metadata_keys(profile)
        passed = rule.satisfied_by(capabilities, profile)
        status = "pass" if passed else "missing" if missing_keys or rule.severity == "error" else "warn"
        results.append(
            {
                "check_id": f"provider_specific:{rule.rule_id}",
                "status": status,
                "message": rule.message if not passed else f"{rule.rule_id} provider-specific readiness rule passed",
                "rule_id": rule.rule_id,
                "severity": rule.severity,
                "missing_metadata_keys": missing_keys,
            }
        )
    return results


def validate_browser_provider_capability_compatibility(capabilities: dict[str, Any]) -> dict[str, Any]:
    """Validate BrowserProvider capability combinations without side effects.

    This is intentionally metadata-only. It does not inspect provider objects,
    import optional SDKs, probe CDP endpoints, or launch browsers. The goal is
    to flag impossible or suspicious capability combinations before a provider
    is used by native-web.
    """

    provider_id = str(capabilities.get("provider_id") or "unknown")
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evaluated_rules: list[dict[str, Any]] = []

    if provider_id == "unknown":
        errors.append({"code": "missing_provider_id", "message": "capabilities must include a stable provider_id", "severity": "error"})

    for rule in BROWSER_PROVIDER_COMPATIBILITY_RULES:
        if not rule.applies_to(capabilities):
            continue
        passed = rule.satisfied_by(capabilities)
        evaluated_rules.append({"rule_id": rule.rule_id, "severity": rule.severity, "passed": passed})
        if passed:
            continue
        issue = {
            "code": rule.rule_id,
            "message": rule.message,
            "severity": rule.severity,
            "when_all": list(rule.when_all),
            "when_any": list(rule.when_any),
            "requires_all": list(rule.requires_all),
            "requires_any": list(rule.requires_any),
        }
        if rule.severity == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    status = "error" if errors else "warning" if warnings else "compatible"
    return {
        "rule_version": BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
        "provider_id": provider_id,
        "status": status,
        "ok": not errors,
        "rule_count": len(BROWSER_PROVIDER_COMPATIBILITY_RULES),
        "evaluated_rule_count": len(evaluated_rules),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "evaluated_rules": evaluated_rules,
    }


def _capability_enabled(capabilities: dict[str, Any], key: str) -> bool:
    return bool(capabilities.get(key))


def _append_lifecycle(row: dict[str, Any], stage: str, status: str, message: str) -> None:
    row.setdefault("lifecycle", []).append({"stage": stage, "status": status, "message": message})


def _matrix_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compatibility_items = [row.get("compatibility") for row in rows if isinstance(row.get("compatibility"), dict)]
    readiness_items = [row.get("production_readiness") for row in rows if isinstance(row.get("production_readiness"), dict)]
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
        "production_readiness": {
            "production_ready_count": sum(1 for item in readiness_items if item.get("status") == "production-ready"),
            "review_required_count": sum(1 for item in readiness_items if item.get("status") == "review-required"),
            "metadata_incomplete_count": sum(1 for item in readiness_items if item.get("status") == "metadata-incomplete"),
        },
    }


def _matrix_ok(rows: list[dict[str, Any]]) -> bool:
    return all(bool(row.get("configured")) and bool(row.get("compatibility", {}).get("ok", True)) for row in rows)
