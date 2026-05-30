from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from pydantic import Field

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.session import BrowserPageRef
from reverse_deepagent.schemas.common import SchemaBaseModel


class RemoteCDPConfig(SchemaBaseModel):
    """Configuration for connecting to an existing Chrome DevTools endpoint."""

    browser_url: str = Field(default="http://127.0.0.1:9222", description="Chrome DevTools browser URL.")
    connect_timeout: float = Field(default=5.0, description="HTTP/WebSocket connect timeout in seconds.")
    navigation_wait: float = Field(default=0.5, description="Small wait after navigate to let the page commit.")
    page_target_type: str = Field(default="page", description="CDP target type used for browser tabs.")

    def safe_summary(self) -> dict[str, Any]:
        return {
            "browser_url": _redact_url(self.browser_url),
            "connect_timeout": self.connect_timeout,
            "navigation_wait": self.navigation_wait,
            "page_target_type": self.page_target_type,
        }


class RemoteCDPSession:
    """Minimal synchronous CDP session wrapper using websockets."""

    def __init__(self, ws_url: str, *, timeout: float = 5.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self._id = 0

    def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._id += 1
        message = {"id": self._id, "method": method}
        if params:
            message["params"] = params
        return asyncio.run(self._send(message))

    async def _send(self, message: dict[str, Any]) -> Any:
        try:
            from websockets.sync.client import connect
        except ModuleNotFoundError as exc:
            raise BrowserProviderUnavailableError(
                "websockets is not installed. Install the optional cdp dependency, for example: "
                'uv pip install --python "<repo-root>/.venv/bin/python" -e ".[cdp]"'
            ) from exc

        def _run() -> Any:
            connect_kwargs = {"open_timeout": self.timeout, "close_timeout": self.timeout, "ping_timeout": self.timeout}
            with connect(self.ws_url, **connect_kwargs) as websocket:
                websocket.send(json.dumps(message))
                while True:
                    raw = websocket.recv(timeout=self.timeout)
                    payload = json.loads(raw)
                    if payload.get("id") != message["id"]:
                        continue
                    if "error" in payload:
                        error = payload["error"] if isinstance(payload["error"], dict) else {"message": str(payload["error"])}
                        raise RuntimeError(error.get("message") or str(error))
                    return payload.get("result", {})

        return await asyncio.to_thread(_run)


class RemoteCDPPage:
    """Provider-neutral browser page backed by a remote Chrome DevTools target."""

    def __init__(self, provider: "RemoteCDPProvider", target: dict[str, Any]) -> None:
        self._provider = provider
        self._target = target
        self._session = RemoteCDPSession(str(target.get("webSocketDebuggerUrl", "")), timeout=provider.config.connect_timeout)
        self._url = str(target.get("url") or "")

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
        wait_seconds = self._provider.config.navigation_wait if timeout is None else min(timeout, self._provider.config.navigation_wait)
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
            Path(path).write_bytes(data)
            return None
        return data

    def cdp_session(self) -> RemoteCDPSession:
        return self._session

    def _evaluate_string(self, expression: str) -> str | None:
        value = self.evaluate(expression)
        return None if value is None else str(value)


class RemoteCDPBrowserSession:
    """Session wrapper that exposes page list and page creation over CDP."""

    def __init__(self, provider: "RemoteCDPProvider", browser_ws_url: str, browser_url: str) -> None:
        self._provider = provider
        self._browser_ws_url = browser_ws_url
        self._browser_url = browser_url

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    def _fetch_targets(self) -> list[dict[str, Any]]:
        payload = self._provider._fetch_json(urljoin(self._browser_url.rstrip("/") + "/", "json/list"))
        return payload if isinstance(payload, list) else []

    def list_pages(self) -> list[BrowserPageRef]:
        refs: list[BrowserPageRef] = []
        for index, target in enumerate(self._fetch_targets()):
            if target.get("type") != self._provider.config.page_target_type:
                continue
            refs.append(
                BrowserPageRef(
                    page_id=str(target.get("id") or index),
                    url=str(target.get("url") or ""),
                    title=target.get("title"),
                    selected=index == 0,
                )
            )
        return refs

    def new_page(self, url: str | None = None) -> RemoteCDPPage:
        created = self._provider._create_target(self._browser_url, url or "about:blank")
        return RemoteCDPPage(self._provider, created)

    def get_active_page(self) -> RemoteCDPPage | None:
        targets = self._fetch_targets()
        for target in targets:
            if target.get("type") == self._provider.config.page_target_type:
                return RemoteCDPPage(self._provider, target)
        return None

    def close(self) -> None:
        return None


class RemoteCDPProvider:
    """BrowserProvider backed by an existing Chrome DevTools endpoint."""

    provider_id = "remote-cdp"

    def __init__(self, config: RemoteCDPConfig | None = None) -> None:
        self.config = config or RemoteCDPConfig()
        self._session: RemoteCDPBrowserSession | None = None

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id=self.provider_id,
            display_name="Remote Chrome CDP",
            engine="chromium",
            transport="remote-cdp",
            supports_launch=False,
            supports_connect=True,
            supports_persistent_context=False,
            supports_cdp=True,
            supports_playwright_api=False,
            supports_proxy=False,
            supports_stealth=False,
            supports_humanize=False,
            supports_extensions=False,
            supports_mobile_emulation=False,
            supports_network_events=False,
            supports_response_body=False,
            supports_request_initiator=True,
            supports_script_source=True,
            supports_websocket_frames=True,
            supports_breakpoints=True,
            supports_runtime_eval=True,
            managed_browser=False,
            notes=[
                "connects to an existing Chrome DevTools endpoint",
                "useful when Playwright is unavailable but Chrome debug is reachable",
            ],
            config=self.config.safe_summary(),
        )

    def start(self) -> RemoteCDPBrowserSession:
        return self.connect()

    def connect(self) -> RemoteCDPBrowserSession:
        version = self._fetch_json(urljoin(self.config.browser_url.rstrip("/") + "/", "json/version"))
        browser_ws_url = str(version.get("webSocketDebuggerUrl") or "")
        if not browser_ws_url:
            raise BrowserProviderUnavailableError(f"Chrome DevTools endpoint at {self.config.browser_url!r} did not expose webSocketDebuggerUrl")
        self._session = RemoteCDPBrowserSession(self, browser_ws_url, self.config.browser_url)
        return self._session

    def stop(self) -> None:
        self._session = None

    def is_available(self) -> bool:
        try:
            version = self._fetch_json(urljoin(self.config.browser_url.rstrip("/") + "/", "json/version"))
        except Exception:
            return False
        return bool(isinstance(version, dict) and version.get("webSocketDebuggerUrl"))

    def _fetch_json(self, url: str) -> Any:
        request = Request(url, headers={"User-Agent": "reverse-deepagent"})
        with urlopen(request, timeout=self.config.connect_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _create_target(self, browser_url: str, target_url: str) -> dict[str, Any]:
        create_url = urljoin(browser_url.rstrip("/") + "/", f"json/new?{quote(target_url, safe=':/?&=%#')}")
        request = Request(create_url, method="PUT", headers={"User-Agent": "reverse-deepagent"})
        with urlopen(request, timeout=self.config.connect_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise BrowserProviderUnavailableError("Chrome DevTools /json/new did not return an object")
        return payload


def _redact_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
