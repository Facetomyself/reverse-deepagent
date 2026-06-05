from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from reverse_deepagent.browser.base import BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.registry import BrowserProviderRegistration
from reverse_deepagent.browser.session import BrowserPageRef

BROWSERBASE_CDP_BROWSER_PROVIDER_ID = "browserbase-cdp"
BROWSERBASE_CDP_BROWSER_PROVIDER_ALIASES = (
    "browserbase",
    "browserbase-provider",
    "browserbase-hosted-cdp",
)
_FACTORY_INVOCATION_COUNT = 0
_SESSION_EVENTS: list[dict[str, Any]] = []


@dataclass(frozen=True, slots=True)
class BrowserbaseCDPBrowserProviderConfig:
    """Non-secret config for Browserbase hosted CDP sessions."""

    display_name: str = "Browserbase CDP BrowserProvider"
    api_base_url: str = "https://api.browserbase.com"
    connect_url: str | None = None
    api_key: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    keep_alive: bool | None = None
    session_timeout_seconds: int | None = None
    region: str | None = None
    connect_timeout: float = 5.0
    navigation_wait: float = 0.5
    page_target_type: str = "page"

    def endpoint_configured(self) -> bool:
        return bool(self.connect_url)

    def api_material_configured(self) -> bool:
        return bool(self.api_key)

    def project_configured(self) -> bool:
        return bool(self.project_id)

    def summary(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "api_base_url": _redact_url(self.api_base_url),
            "connect_url": _redact_url(self.connect_url) if self.connect_url else None,
            "access_material_configured": self.api_material_configured(),
            "project_id": _redact_identifier(self.project_id) if self.project_id else None,
            "project_id_configured": self.project_configured(),
            "session_id": _redact_identifier(self.session_id) if self.session_id else None,
            "endpoint_configured": self.endpoint_configured(),
            "keep_alive": self.keep_alive,
            "session_timeout_seconds": self.session_timeout_seconds,
            "region": self.region,
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
            "page_target_type": self.page_target_type,
        }


@dataclass(slots=True)
class _BrowserbaseAllocation:
    session_id: str
    connect_url: str
    project_id: str | None = None
    owned: bool = True

    def safe_summary(self) -> dict[str, Any]:
        return {
            "session_id": _redact_identifier(self.session_id),
            "connect_url": _redact_url(self.connect_url),
            "project_id": _redact_identifier(self.project_id) if self.project_id else None,
            "owned": self.owned,
        }


class BrowserbaseDirectCDPConnection:
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


class BrowserbasePageCDPSession:
    def __init__(self, connection: BrowserbaseDirectCDPConnection, session_id: str) -> None:
        self._connection = connection
        self.session_id = session_id

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        return self._connection.send(method, params, session_id=self.session_id)


class BrowserbaseCDPPage:
    def __init__(self, browser_session: "BrowserbaseCDPBrowserSession", target_id: str, session_id: str, url: str | None = None) -> None:
        self._browser_session = browser_session
        self._target_id = target_id
        self._session = BrowserbasePageCDPSession(browser_session.connection, session_id)
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

    def cdp_session(self) -> BrowserbasePageCDPSession:
        return self._session

    def _evaluate_string(self, expression: str) -> str | None:
        value = self.evaluate(expression)
        return None if value is None else str(value)


class BrowserbaseCDPBrowserSession:
    def __init__(self, provider: "BrowserbaseCDPBrowserProvider", connection: BrowserbaseDirectCDPConnection) -> None:
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

    def new_page(self, url: str | None = None) -> BrowserbaseCDPPage:
        created = self.connection.send("Target.createTarget", {"url": url or "about:blank"})
        target_id = str(created.get("targetId") or "")
        if not target_id:
            raise BrowserProviderUnavailableError("Browserbase CDP Target.createTarget did not return targetId")
        return self._attach_page(target_id, url=url or "about:blank")

    def get_active_page(self) -> BrowserbaseCDPPage | None:
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

    def _attach_page(self, target_id: str, *, url: str) -> BrowserbaseCDPPage:
        attached = self.connection.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = str(attached.get("sessionId") or "")
        if not session_id:
            raise BrowserProviderUnavailableError("Browserbase CDP Target.attachToTarget did not return sessionId")
        return BrowserbaseCDPPage(self, target_id, session_id, url=url)


class BrowserbaseCDPBrowserProvider:
    """Browserbase hosted CDP BrowserProvider package."""

    provider_id = BROWSERBASE_CDP_BROWSER_PROVIDER_ID

    def __init__(self, config: BrowserbaseCDPBrowserProviderConfig | None = None) -> None:
        self.config = config or BrowserbaseCDPBrowserProviderConfig()
        self._direct_session: BrowserbaseCDPBrowserSession | None = None
        self._allocation: _BrowserbaseAllocation | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return browserbase_cdp_browser_provider_capabilities(self.config)

    def start(self) -> BrowserSession:
        allocation = self._allocation or self._create_session()
        self._allocation = allocation
        return self._connect_url(allocation.connect_url, event="start")

    def connect(self) -> BrowserSession:
        if self._allocation is not None:
            return self._connect_url(self._allocation.connect_url, event="connect_owned_session")
        if not self.config.connect_url:
            raise BrowserProviderUnavailableError(
                "Browserbase CDP provider requires connect_url / browser_ws_url / browserbase_connect_url for connect(). "
                "Use start() with a reviewed api_key to create a Browserbase Session explicitly."
            )
        _record_event("attach_existing", self.config, session_id=self.config.session_id, connect_url=self.config.connect_url, owned=False)
        return self._connect_url(self.config.connect_url, event="connect")

    def stop(self) -> None:
        if self._direct_session is not None:
            self._direct_session.close()
            self._direct_session = None
        if self._allocation is not None:
            _record_event("close_local_session", self.config, session_id=self._allocation.session_id, connect_url=self._allocation.connect_url, owned=self._allocation.owned)

    def is_available(self) -> bool:
        return bool(self.config.connect_url or self.config.api_key)

    def allocation_summary(self) -> dict[str, Any] | None:
        return self._allocation.safe_summary() if self._allocation is not None else None

    def _create_session(self) -> _BrowserbaseAllocation:
        if not self.config.api_key:
            raise BrowserProviderUnavailableError("Browserbase CDP start() requires api_key / BROWSERBASE_API_KEY for explicit session creation.")
        url = urljoin(self.config.api_base_url.rstrip("/") + "/", "v1/sessions")
        body: dict[str, Any] = {}
        if self.config.project_id:
            body["projectId"] = self.config.project_id
        browser_settings: dict[str, Any] = {}
        if self.config.keep_alive is not None:
            body["keepAlive"] = self.config.keep_alive
        if self.config.session_timeout_seconds is not None:
            browser_settings["timeout"] = self.config.session_timeout_seconds
        if self.config.region:
            browser_settings["region"] = self.config.region
        if browser_settings:
            body["browserSettings"] = browser_settings
        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-BB-API-Key": self.config.api_key,
                "User-Agent": "reverse-deepagent-browserbase-cdp",
            },
        )
        with urlopen(request, timeout=self.config.connect_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise BrowserProviderUnavailableError("Browserbase create session did not return an object")
        connect_url = str(payload.get("connectUrl") or "")
        session_id = str(payload.get("id") or "")
        if not connect_url or not session_id:
            raise BrowserProviderUnavailableError("Browserbase create session did not return id and connectUrl")
        allocation = _BrowserbaseAllocation(session_id=session_id, connect_url=connect_url, project_id=str(payload.get("projectId") or self.config.project_id or "") or None, owned=True)
        _record_event("create_session", self.config, session_id=allocation.session_id, connect_url=allocation.connect_url, owned=True)
        return allocation

    def _connect_url(self, connect_url: str, *, event: str) -> BrowserbaseCDPBrowserSession:
        connection = BrowserbaseDirectCDPConnection(connect_url, timeout=self.config.connect_timeout)
        connection.open()
        session = BrowserbaseCDPBrowserSession(self, connection)
        self._direct_session = session
        _record_event(event, self.config, session_id=self._allocation.session_id if self._allocation else self.config.session_id, connect_url=connect_url, owned=bool(self._allocation and self._allocation.owned))
        return session


def browserbase_cdp_browser_provider_capabilities(config: BrowserbaseCDPBrowserProviderConfig | None = None) -> BrowserProviderCapabilities:
    """Return side-effect-free, non-secret Browserbase CDP metadata."""

    config = config or BrowserbaseCDPBrowserProviderConfig()
    return BrowserProviderCapabilities(
        provider_id=BROWSERBASE_CDP_BROWSER_PROVIDER_ID,
        display_name=config.display_name,
        engine="chromium-compatible",
        transport="browserbase-cdp",
        target_platforms=["web"],
        supports_launch=True,
        supports_connect=True,
        supports_persistent_context=True,
        supports_cdp=True,
        supports_playwright_api=False,
        supports_proxy=True,
        supports_stealth=False,
        supports_humanize=False,
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
            "Browserbase hosted CDP provider package using reviewed connectUrl or explicit Session API creation",
            "registration and metadata matrix do not read API keys, create sessions, open sockets, or call provider factories",
            "start() is the only path that can POST /v1/sessions; connect() only attaches to a caller-supplied reviewed connectUrl",
            "API key, project id, connectUrl, and session id are redacted from metadata and event logs",
        ],
        config=config.summary(),
        production_readiness={
            "readiness_tier": "review-required",
            "health_check_mode": "explicit-browserbase-session-smoke",
            "profile_lifecycle": "browserbase-session-owned",
            "proxy_policy": "browserbase-project-or-session-owned-not-core-configured",
            "extension_policy": "browserbase-project-or-session-owned-not-core-configured",
            "humanize_policy": "not-supported-by-this-provider-wrapper",
            "account_boundary_policy": "browserbase-project-controls-secrets-and-session-policy",
            "endpoint_security_policy": "caller-supplied-redacted-browserbase-connect-url-or-session-api",
            "allocation_lifecycle_policy": "metadata-does-not-create-sessions; explicit-start-posts-v1-sessions; stop-closes-local-cdp-only",
            "session_recovery": "explicit-connect-url-or-created-session-connect-url",
            "intended_use": "browserbase-hosted-cdp-provider-package",
            "side_effect_boundary": "metadata-listing-does-not-read-env-or-contact-browserbase; start/connect-and-smoke-require-explicit-reviewed-config",
        },
    )


def create_browserbase_cdp_browser_provider(**kwargs: Any) -> BrowserbaseCDPBrowserProvider:
    """Factory used only after explicit BrowserProviderRegistry.create(...)."""

    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT += 1
    connect_url = (
        kwargs.get("connect_url")
        or kwargs.get("browser_ws_url")
        or kwargs.get("browserbase_connect_url")
        or os.environ.get("BROWSERBASE_CONNECT_URL")
    )
    api_key = kwargs.get("api_key") or os.environ.get("BROWSERBASE_API_KEY")
    project_id = kwargs.get("project_id") or os.environ.get("BROWSERBASE_PROJECT_ID")
    api_base_url = kwargs.get("api_base_url") or os.environ.get("BROWSERBASE_API_BASE_URL") or "https://api.browserbase.com"
    timeout_value = kwargs.get("session_timeout_seconds") or kwargs.get("browserbase_session_timeout")
    config = BrowserbaseCDPBrowserProviderConfig(
        display_name=str(kwargs.get("display_name") or "Browserbase CDP BrowserProvider"),
        api_base_url=str(api_base_url),
        connect_url=str(connect_url) if connect_url else None,
        api_key=str(api_key) if api_key else None,
        project_id=str(project_id) if project_id else None,
        session_id=str(kwargs.get("session_id")) if kwargs.get("session_id") else None,
        keep_alive=kwargs.get("keep_alive") if kwargs.get("keep_alive") is None else bool(kwargs.get("keep_alive")),
        session_timeout_seconds=int(timeout_value) if timeout_value is not None else None,
        region=str(kwargs.get("region")) if kwargs.get("region") else None,
        connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
        navigation_wait=float(kwargs.get("browser_navigation_wait") if kwargs.get("browser_navigation_wait") is not None else 0.5),
        page_target_type=str(kwargs.get("page_target_type") or "page"),
    )
    return BrowserbaseCDPBrowserProvider(config=config)


def browser_provider_registration() -> BrowserProviderRegistration:
    """Return Browserbase CDP BrowserProvider registration without runtime side effects."""

    return BrowserProviderRegistration(
        provider_id=BROWSERBASE_CDP_BROWSER_PROVIDER_ID,
        aliases=BROWSERBASE_CDP_BROWSER_PROVIDER_ALIASES,
        capabilities=browserbase_cdp_browser_provider_capabilities(),
        factory=create_browserbase_cdp_browser_provider,
    )


def factory_invocation_count() -> int:
    return _FACTORY_INVOCATION_COUNT


def session_event_log() -> list[dict[str, Any]]:
    return [dict(item) for item in _SESSION_EVENTS]


def reset_browserbase_state() -> None:
    global _FACTORY_INVOCATION_COUNT  # noqa: PLW0603
    _FACTORY_INVOCATION_COUNT = 0
    _SESSION_EVENTS.clear()


def _record_event(event: str, config: BrowserbaseCDPBrowserProviderConfig, *, session_id: str | None = None, connect_url: str | None = None, owned: bool = False) -> None:
    _SESSION_EVENTS.append(
        {
            "event": event,
            "api_base_url": _redact_url(config.api_base_url),
            "connect_url": _redact_url(connect_url or config.connect_url) if (connect_url or config.connect_url) else None,
            "session_id": _redact_identifier(session_id) if session_id else None,
            "project_id": _redact_identifier(config.project_id) if config.project_id else None,
            "access_material_configured": config.api_material_configured(),
            "owned": owned,
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


def _redact_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 10:
        return "<redacted>"
    return f"{value[:6]}...{value[-4:]}"
