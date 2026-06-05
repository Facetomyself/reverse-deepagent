from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider
from reverse_deepagent.browser.session import BrowserPageRef
from reverse_deepagent.browser.registry import BrowserProviderRegistration

BROWSERLESS_CDP_BROWSER_PROVIDER_ID = "browserless-cdp"
BROWSERLESS_CDP_BROWSER_PROVIDER_ALIASES = (
    "browserless",
    "browserless-io",
    "browserless-provider",
    "browserless-hosted-cdp",
)
_FACTORY_INVOCATION_COUNT = 0
_CONNECTION_EVENTS: list[dict[str, Any]] = []


@dataclass(frozen=True, slots=True)
class BrowserlessCDPBrowserProviderConfig:
    """Non-secret config for Browserless-style hosted CDP endpoints."""

    display_name: str = "Browserless CDP BrowserProvider"
    browser_url: str | None = None
    browser_ws_url: str | None = None
    service_base_url: str | None = None
    tenant_label: str | None = None
    endpoint_configured: bool = False
    access_material_configured: bool = False
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
            "service_base_url": _redact_url(self.service_base_url) if self.service_base_url else None,
            "tenant_label": self.tenant_label,
            "endpoint_mode": self.endpoint_mode(),
            "endpoint_configured": self.endpoint_configured,
            "access_material_configured": self.access_material_configured,
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
            "page_target_type": self.page_target_type,
        }


class BrowserlessDirectCDPConnection:
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


class BrowserlessPageCDPSession:
    """Page-scoped CDP session carrying Target.attachToTarget session id."""

    def __init__(self, connection: BrowserlessDirectCDPConnection, session_id: str) -> None:
        self._connection = connection
        self.session_id = session_id

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return self._connection.send(method, params, session_id=self.session_id)


class BrowserlessCDPPage:
    """Provider-neutral page backed by a direct Browserless browser WebSocket."""

    def __init__(self, session: "BrowserlessDirectCDPBrowserSession", target_id: str, session_id: str, url: str | None = None) -> None:
        self._browser_session = session
        self._target_id = target_id
        self._session = BrowserlessPageCDPSession(session.connection, session_id)
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

    def cdp_session(self) -> BrowserlessPageCDPSession:
        return self._session

    def _evaluate_string(self, expression: str) -> str | None:
        value = self.evaluate(expression)
        return None if value is None else str(value)


class BrowserlessDirectCDPBrowserSession:
    """BrowserSession over a direct browser-level CDP WebSocket endpoint."""

    def __init__(self, provider: "BrowserlessCDPBrowserProvider", connection: BrowserlessDirectCDPConnection) -> None:
        self._provider = provider
        self.connection = connection
        self.config = provider.config

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    def list_pages(self) -> list[BrowserPageRef]:
        targets = self._target_infos()
        refs: list[BrowserPageRef] = []
        for index, target in enumerate(targets):
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

    def new_page(self, url: str | None = None) -> BrowserlessCDPPage:
        created = self.connection.send("Target.createTarget", {"url": url or "about:blank"})
        target_id = str(created.get("targetId") or "")
        if not target_id:
            raise BrowserProviderUnavailableError("Browserless CDP Target.createTarget did not return targetId")
        return self._attach_page(target_id, url=url or "about:blank")

    def get_active_page(self) -> BrowserlessCDPPage | None:
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

    def _attach_page(self, target_id: str, *, url: str) -> BrowserlessCDPPage:
        attached = self.connection.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = str(attached.get("sessionId") or "")
        if not session_id:
            raise BrowserProviderUnavailableError("Browserless CDP Target.attachToTarget did not return sessionId")
        return BrowserlessCDPPage(self, target_id, session_id, url=url)


class BrowserlessCDPBrowserProvider:
    """Browserless hosted CDP provider package."""

    provider_id = BROWSERLESS_CDP_BROWSER_PROVIDER_ID

    def __init__(self, config: BrowserlessCDPBrowserProviderConfig | None = None) -> None:
        self.config = config or BrowserlessCDPBrowserProviderConfig()
        self._delegate_provider: RemoteCDPProvider | None = None
        self._direct_session: BrowserlessDirectCDPBrowserSession | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return browserless_cdp_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
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
            connection = BrowserlessDirectCDPConnection(self.config.browser_ws_url, timeout=self.config.connect_timeout)
            connection.open()
            session = BrowserlessDirectCDPBrowserSession(self, connection)
            self._direct_session = session
            _record_event("connect_browser_websocket", self.config)
            return session
        raise BrowserProviderUnavailableError(
            "Browserless CDP provider requires browser_url / cdp_browser_url or browser_ws_url / cdp_browser_ws_url. "
            "Pass a reviewed Browserless endpoint only when explicitly creating the provider or running smoke."
        )

    def stop(self) -> None:
        if self._delegate_provider is not None:
            self._delegate_provider.stop()
            self._delegate_provider = None
        if self._direct_session is not None:
            self._direct_session.close()
            self._direct_session = None

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


def browserless_cdp_browser_provider_capabilities(
    config: BrowserlessCDPBrowserProviderConfig | None = None,
) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret Browserless CDP metadata."""

    config = config or BrowserlessCDPBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=BROWSERLESS_CDP_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine="chromium-compatible",
        transport="browserless-cdp",
        target_platforms=["web"],
        supports_launch=False,
        supports_connect=True,
        supports_persistent_context=True,
        supports_cdp=True,
        supports_playwright_api=False,
        supports_proxy=False,
        supports_stealth=False,
        supports_humanize=False,
        supports_extensions=False,
        supports_mobile_emulation=False,
        supports_network_events=False,
        supports_response_body=True,
        supports_request_initiator=True,
        supports_script_source=True,
        supports_websocket_frames=True,
        supports_breakpoints=True,
        supports_runtime_eval=True,
        managed_browser=True,
        notes=[
            "Browserless hosted CDP provider package for reviewed HTTP DevTools or browser WebSocket endpoints",
            "registration and metadata matrix do not allocate sessions, read access material, probe endpoints, or call provider factories",
            "connect/start are explicit and delegate to RemoteCDPProvider or a direct browser-level CDP WebSocket wrapper",
            "proxy, stealth, extension, and mobile-emulation controls are treated as Browserless account/session policy outside this provider metadata",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "review-required",
            "health_check_mode": "explicit-browserless-cdp-contract-smoke",
            "profile_lifecycle": "browserless-session-owned",
            "proxy_policy": "browserless-account-or-session-owned-not-core-configured",
            "extension_policy": "browserless-account-or-session-owned-not-core-configured",
            "humanize_policy": "not-supported-by-this-provider-wrapper",
            "account_boundary_policy": "browserless-account-controls-secrets-and-session-policy",
            "endpoint_security_policy": "caller-supplied-redacted-browserless-endpoint",
            "session_recovery": "explicit-endpoint-or-reconnect-url",
            "intended_use": "browserless-hosted-cdp-provider-package",
            "side_effect_boundary": "metadata-listing-does-not-probe-browserless; connect-and-smoke-require-explicit-reviewed-endpoint",
        },
    )


def create_browserless_cdp_browser_provider(**kwargs: Any) -> BrowserlessCDPBrowserProvider:
    """Factory used only after explicit BrowserProviderRegistry.create(...)."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    browser_url = kwargs.get("browser_url") or kwargs.get("cdp_browser_url") or os.environ.get("BROWSERLESS_BROWSER_URL")
    browser_ws_url = (
        kwargs.get("browser_ws_url")
        or kwargs.get("cdp_browser_ws_url")
        or kwargs.get("browserless_browser_ws_url")
        or os.environ.get("BROWSERLESS_CDP_URL")
        or os.environ.get("BROWSERLESS_WS_URL")
    )
    service_base_url = kwargs.get("service_base_url") or os.environ.get("BROWSERLESS_SERVICE_URL")
    config = BrowserlessCDPBrowserProviderConfig(
        display_name=str(kwargs.get("display_name") or "Browserless CDP BrowserProvider"),
        browser_url=browser_url,
        browser_ws_url=browser_ws_url,
        service_base_url=service_base_url,
        tenant_label=kwargs.get("tenant_label"),
        endpoint_configured=bool(browser_url or browser_ws_url),
        access_material_configured=bool(kwargs.get("access_material_configured", False) or os.environ.get("BROWSERLESS_CDP_URL") or os.environ.get("BROWSERLESS_WS_URL")),
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") if kwargs.get("browser_navigation_wait") is not None else 0.5),
        page_target_type=str(kwargs.get("page_target_type") or "page"),
    )
    return BrowserlessCDPBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return Browserless CDP BrowserProvider registration without runtime side effects."""

    return BrowserProviderRegistration(
        provider_id=BROWSERLESS_CDP_BROWSER_PROVIDER_ID,
        aliases=BROWSERLESS_CDP_BROWSER_PROVIDER_ALIASES,
        capabilities=browserless_cdp_browser_provider_capabilities(),
        factory=create_browserless_cdp_browser_provider,
    )


def factory_invocation_count() -> int:
    """Expose factory invocation count for plugin contract tests."""

    return _FACTORY_INVOCATION_COUNT


def connection_event_log() -> list[dict[str, Any]]:
    """Return a copy of Browserless attach events for tests."""

    return [dict(item) for item in _CONNECTION_EVENTS]


def reset_browserless_state() -> None:
    """Reset test-observable module state."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT = 0
    _CONNECTION_EVENTS.clear()


def _record_event(event: str, config: BrowserlessCDPBrowserProviderConfig) -> None:
    _CONNECTION_EVENTS.append(
        {
            "event": event,
            "endpoint_mode": config.endpoint_mode(),
            "browser_url": _redact_url(config.browser_url) if config.browser_url else None,
            "browser_ws_url": _redact_url(config.browser_ws_url) if config.browser_ws_url else None,
            "service_base_url": _redact_url(config.service_base_url) if config.service_base_url else None,
        }
    )


def _redact_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    safe_query = urlencode({"query": "<redacted>"}) if parsed.query else ""
    return urlunsplit((parsed.scheme, netloc, parsed.path, safe_query, ""))
