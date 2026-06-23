from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, replace
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider
from reverse_deepagent.browser.registry import BrowserProviderRegistration
from reverse_deepagent.browser.session import BrowserPageRef

ANTIDETECT_CDP_BROWSER_PROVIDER_ID = "antidetect-cdp"
ANTIDETECT_CDP_BROWSER_PROVIDER_ALIASES = (
    "anti-detect-cdp",
    "antidetect-hosted-cdp",
    "anti-detect-hosted-cdp",
    "vendor-antidetect-cdp",
)
_FACTORY_INVOCATION_COUNT = 0
_CONNECTION_EVENTS: list[dict[str, Any]] = []

AntiDetectAllocationRequester = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class AntiDetectCDPBrowserProviderConfig:
    """Non-secret config for vendor-neutral anti-detect hosted CDP endpoints."""

    display_name: str = "AntiDetect Hosted CDP BrowserProvider"
    browser_url: str | None = None
    browser_ws_url: str | None = None
    allocation_id: str | None = None
    profile_id: str | None = None
    tenant_label: str | None = None
    allocation_requester: AntiDetectAllocationRequester | None = None
    allocation_request: dict[str, Any] | None = None
    reviewed_allocation_result: dict[str, Any] | None = None
    approve_antidetect_allocation: bool = False
    endpoint_configured: bool = False
    allocation_metadata_configured: bool = False
    connect_timeout: float = 5.0
    navigation_wait: float = 0.5
    page_target_type: str = "page"

    def endpoint_mode(self) -> str:
        if self.browser_url:
            return "http-devtools"
        if self.browser_ws_url:
            return "browser-websocket"
        return "unconfigured"

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "browser_url": _redact_url(self.browser_url) if self.browser_url else None,
            "browser_ws_url": _redact_url(self.browser_ws_url) if self.browser_ws_url else None,
            "allocation_id": _redact_identifier(self.allocation_id) if self.allocation_id else None,
            "profile_id": _redact_identifier(self.profile_id) if self.profile_id else None,
            "tenant_label": self.tenant_label,
            "allocator_configured": self.allocation_requester is not None,
            "allocation_request_fields": sorted(str(key) for key in (self.allocation_request or {}).keys()),
            "reviewed_allocation_result_configured": self.reviewed_allocation_result is not None,
            "approve_antidetect_allocation": self.approve_antidetect_allocation,
            "endpoint_mode": self.endpoint_mode(),
            "endpoint_configured": self.endpoint_configured,
            "allocation_metadata_configured": self.allocation_metadata_configured,
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
            "page_target_type": self.page_target_type,
        }


class AntiDetectDirectCDPConnection:
    """Small synchronous browser-level CDP WebSocket connection."""

    def __init__(self, ws_url: str, *, timeout: float = 5.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self._id = 0
        self._websocket: Any | None = None

    def open(self) -> None:
        if self._websocket is not None:
            return
        try:
            from websockets.sync.client import connect
        except ModuleNotFoundError as exc:
            raise BrowserProviderUnavailableError(
                "websockets is not installed. Install the optional cdp dependency, for example: "
                'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cdp]"'
            ) from exc
        self._websocket = connect(self.ws_url, open_timeout=self.timeout, close_timeout=self.timeout, ping_timeout=self.timeout)

    def close(self) -> None:
        if self._websocket is None:
            return
        self._websocket.close()
        self._websocket = None

    def send(self, method: str, params: dict[str, Any] | None = None, *, session_id: str | None = None) -> Any:
        self.open()
        assert self._websocket is not None
        self._id += 1
        message: dict[str, Any] = {"id": self._id, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self._websocket.send(json.dumps(message))
        while True:
            raw = self._websocket.recv(timeout=self.timeout)
            payload = json.loads(raw)
            if payload.get("id") != message["id"]:
                continue
            if "error" in payload:
                error = payload["error"] if isinstance(payload["error"], dict) else {"message": str(payload["error"])}
                raise RuntimeError(error.get("message") or str(error))
            return payload.get("result", {})


class AntiDetectPageCDPSession:
    """Page-scoped CDP session carrying Target.attachToTarget session id."""

    def __init__(self, connection: AntiDetectDirectCDPConnection, session_id: str) -> None:
        self._connection = connection
        self.session_id = session_id

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return self._connection.send(method, params, session_id=self.session_id)


class AntiDetectCDPPage:
    """Provider-neutral page backed by a browser-level anti-detect CDP WebSocket."""

    def __init__(self, session: "AntiDetectCDPBrowserSession", target_id: str, session_id: str, url: str | None = None) -> None:
        self._browser_session = session
        self._target_id = target_id
        self._session = AntiDetectPageCDPSession(session.connection, session_id)
        self._url = url or "about:blank"

    @property
    def url(self) -> str:
        try:
            value = self._evaluate_string("window.location.href")
            return value or self._url
        except Exception:
            return self._url

    def goto(self, url: str, timeout: float | None = None) -> None:
        self._session.send("Page.enable", {})
        self._session.send("Runtime.enable", {})
        self._session.send("Page.navigate", {"url": url})
        self._url = url
        wait_seconds = self._browser_session.config.navigation_wait if timeout is None else min(timeout, self._browser_session.config.navigation_wait)
        if wait_seconds > 0:
            asyncio.run(asyncio.sleep(wait_seconds))

    def title(self) -> str:
        return self._evaluate_string("document.title") or ""

    def content(self) -> str:
        return self._evaluate_string("document.documentElement ? document.documentElement.outerHTML : ''") or ""

    def evaluate(self, expression: str) -> Any:
        payload = self._session.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True, "userGesture": True},
        )
        if not isinstance(payload, dict):
            return payload
        if "exceptionDetails" in payload:
            details = payload.get("exceptionDetails") or {}
            raise RuntimeError(details.get("text") or "CDP evaluation failed")
        result = payload.get("result", {})
        if isinstance(result, dict):
            if "value" in result:
                return result["value"]
            if "unserializableValue" in result:
                return result["unserializableValue"]
            if "description" in result:
                return result["description"]
        return payload

    def screenshot(self, path: str | None = None) -> bytes | None:
        payload = self._session.send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(str(payload.get("data", ""))) if isinstance(payload, dict) and payload.get("data") else b""
        if path:
            from pathlib import Path

            Path(path).write_bytes(data)
            return None
        return data

    def cdp_session(self) -> AntiDetectPageCDPSession:
        return self._session

    def _evaluate_string(self, expression: str) -> str | None:
        value = self.evaluate(expression)
        return None if value is None else str(value)


class AntiDetectCDPBrowserSession:
    """BrowserSession over a reviewed anti-detect browser CDP WebSocket endpoint."""

    def __init__(self, provider: "AntiDetectCDPBrowserProvider", connection: AntiDetectDirectCDPConnection) -> None:
        self._provider = provider
        self.connection = connection
        self.config = provider.config

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    def list_pages(self) -> list[BrowserPageRef]:
        refs: list[BrowserPageRef] = []
        for index, target in enumerate(self._target_infos()):
            refs.append(
                BrowserPageRef(
                    page_id=str(target.get("targetId") or index),
                    url=str(target.get("url") or ""),
                    title=target.get("title"),
                    selected=index == 0,
                    metadata={"target_type": target.get("type")},
                )
            )
        return refs

    def new_page(self, url: str | None = None) -> AntiDetectCDPPage:
        created = self.connection.send("Target.createTarget", {"url": url or "about:blank"})
        target_id = str(created.get("targetId") or "")
        if not target_id:
            raise BrowserProviderUnavailableError("AntiDetect CDP Target.createTarget did not return targetId")
        return self._attach_page(target_id, url=url or "about:blank")

    def get_active_page(self) -> AntiDetectCDPPage | None:
        targets = self._target_infos()
        if not targets:
            return self.new_page("about:blank")
        target = targets[0]
        return self._attach_page(str(target.get("targetId") or ""), url=str(target.get("url") or "about:blank"))

    def close(self) -> None:
        self.connection.close()

    def _target_infos(self) -> list[dict[str, Any]]:
        payload = self.connection.send("Target.getTargets", {})
        infos = payload.get("targetInfos") if isinstance(payload, dict) else []
        return [item for item in infos if isinstance(item, dict) and item.get("type") == self.config.page_target_type]

    def _attach_page(self, target_id: str, *, url: str) -> AntiDetectCDPPage:
        attached = self.connection.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = str(attached.get("sessionId") or "")
        if not session_id:
            raise BrowserProviderUnavailableError("AntiDetect CDP Target.attachToTarget did not return sessionId")
        return AntiDetectCDPPage(self, target_id, session_id, url=url)


class AntiDetectCDPBrowserProvider:
    """Vendor-neutral anti-detect hosted CDP BrowserProvider package."""

    provider_id = ANTIDETECT_CDP_BROWSER_PROVIDER_ID

    def __init__(self, config: AntiDetectCDPBrowserProviderConfig | None = None) -> None:
        self.config = config or AntiDetectCDPBrowserProviderConfig()
        self._delegate_provider: RemoteCDPProvider | None = None
        self._direct_session: AntiDetectCDPBrowserSession | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return antidetect_cdp_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        if not self.config.approve_antidetect_allocation:
            raise BrowserProviderUnavailableError(
                "AntiDetect CDP start() is review-gated and requires approve_antidetect_allocation=True. "
                "Without explicit approval the provider will not call an allocator, contact a vendor, or start a browser."
            )
        if self.config.reviewed_allocation_result is None and self.config.allocation_requester is None:
            raise BrowserProviderUnavailableError(
                "AntiDetect CDP start() requires an injected allocation_requester or reviewed_allocation_result. "
                "Metadata listing and unapproved runtime paths never allocate sessions, read secrets, probe endpoints, "
                "or start vendor browsers."
            )
        allocation_result = self.config.reviewed_allocation_result
        if allocation_result is None:
            assert self.config.allocation_requester is not None
            request = _allocation_request_payload(self.config)
            allocation_result = self.config.allocation_requester(request)
        handoff_config = _config_from_allocation_result(self.config, allocation_result)
        _record_event("allocation_reviewed_endpoint_handoff", handoff_config)
        self.config = handoff_config
        return self.connect()

    def connect(self) -> BrowserSession:
        if self.config.browser_url:
            provider = RemoteCDPProvider(
                RemoteCDPConfig(
                    browser_url=self.config.browser_url,
                    connect_timeout=self.config.connect_timeout,
                    navigation_wait=self.config.navigation_wait,
                    page_target_type=self.config.page_target_type,
                )
            )
            session = provider.connect()
            self._delegate_provider = provider
            _record_event("connect_http_devtools", self.config)
            return session
        if self.config.browser_ws_url:
            connection = AntiDetectDirectCDPConnection(self.config.browser_ws_url, timeout=self.config.connect_timeout)
            connection.open()
            session = AntiDetectCDPBrowserSession(self, connection)
            self._direct_session = session
            _record_event("connect_browser_websocket", self.config)
            return session
        raise BrowserProviderUnavailableError(
            "AntiDetect CDP provider requires browser_url / cdp_browser_url or browser_ws_url / cdp_browser_ws_url. "
            "Pass a reviewed anti-detect hosted browser CDP endpoint only when explicitly creating the provider or running smoke. "
            "Metadata listing never allocates sessions, probes endpoints, reads secrets, or starts vendor browsers."
        )

    def stop(self) -> None:
        closed_session = False
        if self._delegate_provider is not None:
            self._delegate_provider.stop()
            self._delegate_provider = None
            closed_session = True
        if self._direct_session is not None:
            self._direct_session.close()
            self._direct_session = None
            closed_session = True
        if closed_session and self.config.allocation_id:
            _record_event("close_local_attach_only", self.config)

    def is_available(self) -> bool:
        if self.config.browser_url:
            return RemoteCDPProvider(
                RemoteCDPConfig(
                    browser_url=self.config.browser_url,
                    connect_timeout=self.config.connect_timeout,
                    navigation_wait=self.config.navigation_wait,
                    page_target_type=self.config.page_target_type,
                )
            ).is_available()
        return bool(self.config.browser_ws_url)


def antidetect_cdp_browser_provider_capabilities(
    config: AntiDetectCDPBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret anti-detect hosted CDP metadata."""

    config = config or AntiDetectCDPBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=ANTIDETECT_CDP_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine="chromium-compatible",
        transport="antidetect-cdp",
        target_platforms=["web"],
        supports_launch=True,
        supports_connect=True,
        supports_persistent_context=True,
        supports_cdp=True,
        supports_playwright_api=False,
        supports_proxy=True,
        supports_stealth=True,
        supports_humanize=True,
        supports_extensions=True,
        supports_mobile_emulation=True,
        supports_network_events=False,
        supports_response_body=True,
        supports_request_initiator=True,
        supports_script_source=True,
        supports_websocket_frames=True,
        supports_breakpoints=True,
        supports_runtime_eval=True,
        managed_browser=True,
        notes=[
            "vendor-neutral anti-detect hosted CDP provider package for reviewed HTTP DevTools or browser WebSocket endpoints",
            "registration and metadata matrix do not allocate sessions, read access material, probe endpoints, or call provider factories",
            "start() is review-gated; it only calls an injected allocator or consumes a reviewed allocation descriptor when approve_antidetect_allocation=True",
            "stealth, proxy, humanize, extensions, mobile emulation, account boundary, allocation, and profile persistence are declared as vendor account/session policy metadata",
            "endpoint and allocation identifiers are redacted from config summaries, allocation handoff metadata, and connection event logs",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "review-required",
            "health_check_mode": "explicit-antidetect-cdp-contract-smoke",
            "profile_lifecycle": "anti-detect-service-profile-owned",
            "profile_persistence_policy": "vendor-profile-id-or-account-profile-controls-persistence-outside-core",
            "proxy_policy": "vendor-account-or-profile-owned-not-core-configured",
            "extension_policy": "vendor-account-or-profile-owned-not-core-configured",
            "humanize_policy": "vendor-account-or-profile-owned-not-core-implemented",
            "stealth_policy": "vendor-account-or-profile-fingerprint-policy-reviewed-outside-core",
            "account_boundary_policy": "vendor-tenant-or-account-controls-secrets-profiles-proxies-and-session-policy",
            "endpoint_security_policy": "caller-supplied-redacted-reviewed-cdp-endpoint; no endpoint is read from metadata listing",
            "allocation_lifecycle_policy": "metadata-does-not-allocate; start-requires-explicit-approval-and-injected-allocator-or-reviewed-result; connect-attaches-only; stop-closes-local-cdp-session-only",
            "allocator_contract": "vendor-neutral-injected-allocation-requester-or-reviewed-allocation-result; approve_antidetect_allocation-required; endpoint-and-identifiers-redacted",
            "session_recovery": "explicit-endpoint-or-profile-session-reattach",
            "intended_use": "vendor-neutral-antidetect-hosted-cdp-provider-package",
            "side_effect_boundary": "metadata-listing-does-not-read-env-or-secrets-contact-vendor-probe-cdp-call-allocator-or-start-browser; allocation-apply-requires-explicit-approval-and-injected-allocator; connect-and-smoke-require-explicit-reviewed-endpoint",
        },
    )


def create_antidetect_cdp_browser_provider(**kwargs: Any) -> AntiDetectCDPBrowserProvider:
    """Factory used only after explicit BrowserProviderRegistry.create(...)."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    browser_url = kwargs.get("browser_url") or kwargs.get("cdp_browser_url") or kwargs.get("antidetect_browser_url")
    browser_ws_url = kwargs.get("browser_ws_url") or kwargs.get("cdp_browser_ws_url") or kwargs.get("antidetect_browser_ws_url")
    allocation_id = kwargs.get("allocation_id") or kwargs.get("antidetect_allocation_id")
    profile_id = kwargs.get("profile_id") or kwargs.get("antidetect_profile_id")
    allocation_requester = kwargs.get("allocation_requester") or kwargs.get("antidetect_allocation_requester")
    if allocation_requester is not None and not callable(allocation_requester):
        raise TypeError("allocation_requester must be callable")
    reviewed_allocation_result = (
        kwargs.get("reviewed_allocation_result")
        or kwargs.get("allocation_result")
        or kwargs.get("antidetect_allocation_result")
    )
    config = AntiDetectCDPBrowserProviderConfig(
        display_name=str(kwargs.get("display_name") or "AntiDetect Hosted CDP BrowserProvider"),
        browser_url=str(browser_url) if browser_url else None,
        browser_ws_url=str(browser_ws_url) if browser_ws_url else None,
        allocation_id=str(allocation_id) if allocation_id else None,
        profile_id=str(profile_id) if profile_id else None,
        tenant_label=kwargs.get("tenant_label"),
        allocation_requester=allocation_requester,
        allocation_request=dict(kwargs.get("allocation_request") or kwargs.get("antidetect_allocation_request") or {}),
        reviewed_allocation_result=dict(reviewed_allocation_result) if isinstance(reviewed_allocation_result, dict) else None,
        approve_antidetect_allocation=bool(kwargs.get("approve_antidetect_allocation", False)),
        endpoint_configured=bool(browser_url or browser_ws_url),
        allocation_metadata_configured=bool(allocation_id or profile_id or kwargs.get("allocation_metadata_configured", False)),
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") if kwargs.get("browser_navigation_wait") is not None else 0.5),
        page_target_type=str(kwargs.get("page_target_type") or "page"),
    )
    return AntiDetectCDPBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return AntiDetect CDP BrowserProvider registration without runtime side effects."""

    return BrowserProviderRegistration(
        provider_id=ANTIDETECT_CDP_BROWSER_PROVIDER_ID,
        aliases=ANTIDETECT_CDP_BROWSER_PROVIDER_ALIASES,
        capabilities=antidetect_cdp_browser_provider_capabilities(),
        factory=create_antidetect_cdp_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for plugin contract tests."""

    return _FACTORY_INVOCATION_COUNT


def connection_event_log() -> list[dict[str, Any]]:
    """Return a copy of anti-detect attach events for tests."""

    return [dict(item) for item in _CONNECTION_EVENTS]


def reset_antidetect_state() -> None:
    """Reset test-observable module state."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT = 0
    _CONNECTION_EVENTS.clear()


def _allocation_request_payload(config: AntiDetectCDPBrowserProviderConfig) -> dict[str, Any]:
    request = dict(config.allocation_request or {})
    request.setdefault("provider_id", ANTIDETECT_CDP_BROWSER_PROVIDER_ID)
    request.setdefault("tenant_label", config.tenant_label)
    request.setdefault("profile_id", config.profile_id)
    request.setdefault("allocation_id", config.allocation_id)
    request.setdefault("endpoint_mode", "allocator-reviewed-cdp-endpoint")
    return request


def _config_from_allocation_result(
    config: AntiDetectCDPBrowserProviderConfig,
    allocation_result: dict[str, Any],
) -> AntiDetectCDPBrowserProviderConfig:
    browser_url = (
        allocation_result.get("browser_url")
        or allocation_result.get("cdp_browser_url")
        or allocation_result.get("http_devtools_url")
    )
    browser_ws_url = (
        allocation_result.get("browser_ws_url")
        or allocation_result.get("cdp_browser_ws_url")
        or allocation_result.get("websocket_url")
        or allocation_result.get("ws_url")
    )
    endpoint = allocation_result.get("endpoint") or allocation_result.get("cdp_endpoint")
    if endpoint and not browser_url and not browser_ws_url:
        endpoint_text = str(endpoint)
        if endpoint_text.startswith(("ws://", "wss://")):
            browser_ws_url = endpoint_text
        else:
            browser_url = endpoint_text
    if not browser_url and not browser_ws_url:
        raise BrowserProviderUnavailableError(
            "AntiDetect allocation result did not include browser_url or browser_ws_url for reviewed CDP attach."
        )
    allocation_id = allocation_result.get("allocation_id") or allocation_result.get("session_id") or config.allocation_id
    profile_id = allocation_result.get("profile_id") or config.profile_id
    tenant_label = allocation_result.get("tenant_label") or config.tenant_label
    return replace(
        config,
        browser_url=str(browser_url) if browser_url else None,
        browser_ws_url=str(browser_ws_url) if browser_ws_url else None,
        allocation_id=str(allocation_id) if allocation_id else None,
        profile_id=str(profile_id) if profile_id else None,
        tenant_label=str(tenant_label) if tenant_label else None,
        endpoint_configured=True,
        allocation_metadata_configured=True,
        reviewed_allocation_result=_redact_allocation_result(allocation_result),
    )


def _redact_allocation_result(allocation_result: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in allocation_result.items():
        key_text = str(key)
        if value is None:
            redacted[key_text] = None
        elif key_text in {
            "browser_url",
            "cdp_browser_url",
            "http_devtools_url",
            "browser_ws_url",
            "cdp_browser_ws_url",
            "websocket_url",
            "ws_url",
            "endpoint",
            "cdp_endpoint",
        }:
            redacted[key_text] = _redact_url(str(value))
        elif key_text in {"allocation_id", "session_id", "profile_id"}:
            redacted[key_text] = _redact_identifier(str(value))
        elif any(marker in key_text.lower() for marker in ("token", "secret", "password", "key", "credential", "auth")):
            redacted[key_text] = "<redacted>"
        elif isinstance(value, (bool, int, float)):
            redacted[key_text] = value
        elif key_text in {"tenant_label", "status", "endpoint_mode"}:
            redacted[key_text] = str(value)
        else:
            redacted[key_text] = "<redacted>"
    return redacted


def _record_event(event: str, config: AntiDetectCDPBrowserProviderConfig) -> None:
    _CONNECTION_EVENTS.append(
        {
            "event": event,
            "browser_url": _redact_url(config.browser_url) if config.browser_url else None,
            "browser_ws_url": _redact_url(config.browser_ws_url) if config.browser_ws_url else None,
            "allocation_id": _redact_identifier(config.allocation_id) if config.allocation_id else None,
            "profile_id": _redact_identifier(config.profile_id) if config.profile_id else None,
            "tenant_label": config.tenant_label,
            "endpoint_mode": config.endpoint_mode(),
            "allocation_metadata_configured": config.allocation_metadata_configured,
            "allocator_configured": config.allocation_requester is not None,
            "allocation_approved": config.approve_antidetect_allocation,
            "reviewed_allocation_result": _redact_allocation_result(config.reviewed_allocation_result or {})
            if config.reviewed_allocation_result
            else None,
        }
    )


def _redact_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 12:
        return "<redacted>"
    return f"{value[:6]}...{value[-4:]}"


def _redact_url(value: str | None) -> str | None:
    if not value:
        return value
    parts = urlsplit(value)
    netloc = parts.hostname or ""
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    query = urlencode({"query": "<redacted>"}) if parts.query else ""
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))
