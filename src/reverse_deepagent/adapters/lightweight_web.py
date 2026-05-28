from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from pydantic import Field

from reverse_deepagent.adapters.jsreverser import JSReverserBridge, JSReverserRuntime
from reverse_deepagent.schemas import ArtifactKind, ArtifactRef, SchemaBaseModel


class LightweightCommandResult(SchemaBaseModel):
    """Normalized command probe result for lightweight Web backends."""

    command: list[str] = Field(description="Command argv that was attempted.")
    ok: bool = Field(description="Whether the command completed successfully.")
    returncode: int | None = Field(default=None, description="Process return code, or None when not started.")
    stdout: str = Field(default="", description="Captured stdout.")
    stderr: str = Field(default="", description="Captured stderr.")
    unavailable_reason: str | None = Field(default=None, description="Why the command could not run, if applicable.")


CommandRunner = Callable[[list[str], float], LightweightCommandResult]
HttpGetter = Callable[[str, float], tuple[int, str, str]]


class LightweightWebRuntimeConfig(SchemaBaseModel):
    """Serializable config for Playwright / CDP / browser CLI lightweight backends."""

    backend_id: str = Field(description="Stable backend id.")
    display_name: str = Field(description="Human-readable backend name.")
    transport: str = Field(description="Transport shape, such as playwright-cli, chrome-cdp, or browser-cli.")
    browser_url: str | None = Field(default=None, description="Existing Chrome DevTools browser URL for chrome-cdp.")
    command: str | None = Field(default=None, description="Optional local CLI command used for side-effect-light probes.")
    command_args: list[str] = Field(default_factory=list, description="Arguments used for command probes.")
    request_timeout: float = Field(default=10.0, description="Timeout for command and HTTP probes.")
    default_page_size: int = Field(default=20, description="Maximum source/search records returned to recon.")
    source_fetch_limit: int = Field(default=5, description="Maximum script-like sources fetched from a page.")
    user_agent: str = Field(default="reverse-deepagent-lightweight/0.1", description="User-Agent used for static source fetches.")

    def safe_summary(self) -> dict[str, Any]:
        """Return public-safe config metadata for manifests and capability dumps."""

        return self.model_dump(mode="json")


class LightweightWebBridge(JSReverserBridge):
    """Bridge exposing a JSReverser-like tool surface over lightweight Web probes.

    This bridge intentionally does not launch browsers. The CDP backend probes an
    already-running DevTools endpoint; Playwright / browser CLI backends only run
    side-effect-light version commands and static HTTP source fetches.
    """

    def __init__(
        self,
        config: LightweightWebRuntimeConfig,
        command_runner: CommandRunner | None = None,
        http_getter: HttpGetter | None = None,
    ) -> None:
        self.config = config
        self._command_runner = command_runner or run_lightweight_command
        self._http_getter = http_getter or self._default_http_get
        self.active_url: str | None = None
        self._probe_cache: dict[str, Any] | None = None
        self._source_cache: dict[str, dict[str, Any]] = {}
        self._source_cache_url: str | None = None

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "check_browser_health":
            return self._check_browser_health()
        if tool_name == "list_pages":
            return self._list_pages()
        if tool_name == "new_page":
            self.active_url = str(params.get("url") or self.active_url or "about:blank")
            return {"ok": True, "created": True, "url": self.active_url, "transport": self.config.transport}
        if tool_name == "navigate_page":
            self.active_url = str(params.get("url") or self.active_url or "about:blank")
            return {"ok": True, "navigated": True, "url": self.active_url, "transport": self.config.transport}
        if tool_name == "network_request":
            return {"requests": [], "note": "lightweight backend does not capture live network traffic"}
        if tool_name == "search_in_sources":
            return {"results": self._search_sources(str(params.get("query") or ""), int(params.get("maxResults") or self.config.default_page_size))}
        if tool_name == "get_script_source":
            return self._get_script_source(str(params.get("scriptId") or ""), params)
        if tool_name == "get_request_initiator":
            return {"requestId": params.get("requestId"), "initiator": None, "note": "lightweight backend has no initiator timeline"}
        if tool_name == "get_storage":
            return {"localStorage": {}, "sessionStorage": {}, "cookies": {}}
        if tool_name == "evaluate_script":
            return self._evaluate_script(str(params.get("function") or ""))
        if tool_name == "inject_preload_script":
            return {"ok": False, "unsupported": True, "note": "lightweight backend does not inject preload scripts"}
        if tool_name == "export_session_report":
            return self._export_session_report(params)
        raise RuntimeError(f"Unsupported lightweight Web tool: {tool_name}")

    def _check_browser_health(self) -> dict[str, Any]:
        probe = self._probe()
        return {
            "status": "ok" if probe.get("available") else "unavailable",
            "connected": bool(probe.get("available")),
            "backend_id": self.config.backend_id,
            "transport": self.config.transport,
            "probe": probe,
        }

    def _list_pages(self) -> dict[str, Any]:
        if self.config.transport == "chrome-cdp":
            pages_payload = self._fetch_cdp_json("/json/list")
            pages = []
            if isinstance(pages_payload.get("payload"), list):
                for index, item in enumerate(pages_payload["payload"]):
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "")
                    if not self.active_url and url and url != "about:blank":
                        self.active_url = url
                    pages.append(
                        {
                            "pageIdx": index,
                            "id": item.get("id"),
                            "url": url,
                            "title": item.get("title"),
                            "type": item.get("type"),
                            "selected": index == 0,
                        }
                    )
            return {"pages": pages, "raw": pages_payload}
        if self.active_url:
            return {"pages": [{"pageIdx": 0, "url": self.active_url, "selected": True, "synthetic": True}]}
        return {"pages": []}

    def _search_sources(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not query or not self._looks_like_http_url(self.active_url):
            return []
        self._fetch_page_sources(str(self.active_url))
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for script_id, item in self._source_cache.items():
            source = str(item.get("source") or "")
            lines = source.splitlines() or [source]
            for line_number, line in enumerate(lines, start=1):
                if query_lower not in line.lower():
                    continue
                results.append(
                    {
                        "scriptId": script_id,
                        "url": item.get("url"),
                        "lineNumber": line_number,
                        "preview": line.strip()[:240],
                        "transport": self.config.transport,
                    }
                )
                break
            if len(results) >= limit:
                break
        return results

    def _get_script_source(self, script_id: str, params: dict[str, Any]) -> dict[str, Any]:
        item = self._source_cache.get(script_id)
        if item is None:
            return {"scriptId": script_id, "source": "", "ok": False, "note": "source not cached"}
        return {
            "scriptId": script_id,
            "url": item.get("url"),
            "source": item.get("source") or "",
            "startLine": params.get("startLine"),
            "endLine": params.get("endLine"),
            "ok": True,
        }

    def _evaluate_script(self, function_source: str) -> dict[str, Any]:
        if "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in function_source:
            return {
                "ok": True,
                "result": {
                    "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
                    "located": False,
                    "invocation_ok": False,
                    "invocation_result_type": "unsupported",
                    "sign_shape_ok": False,
                    "replay_result": {"attempted": False, "ok": False, "reason": "lightweight backend cannot execute page JavaScript"},
                    "runtime_url": self.active_url,
                },
            }
        if "dumpStorage" in function_source or "navigator" in function_source:
            return {
                "ok": True,
                "result": {
                    "cookie": "",
                    "localStorage": {},
                    "sessionStorage": {},
                    "navigator": {},
                    "timezoneOffset": None,
                    "note": "lightweight backend has no live DOM runtime",
                },
            }
        return {"ok": False, "unsupported": True, "result": None}

    def _export_session_report(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "format": params.get("format", "json"),
            "backend_id": self.config.backend_id,
            "transport": self.config.transport,
            "active_url": self.active_url,
            "probe": self._probe(),
            "source_count": len(self._source_cache),
            "sources": [
                {"scriptId": key, "url": value.get("url"), "size": len(str(value.get("source") or ""))}
                for key, value in sorted(self._source_cache.items())
            ],
        }

    def _probe(self) -> dict[str, Any]:
        if self._probe_cache is not None:
            return self._probe_cache
        if self.config.transport == "chrome-cdp":
            version = self._fetch_cdp_json("/json/version")
            self._probe_cache = {
                "backend_id": self.config.backend_id,
                "transport": self.config.transport,
                "available": bool(version.get("ok")),
                "browser_url": self.config.browser_url,
                "version": version,
                "launch_attempted": False,
            }
            return self._probe_cache
        command = self._probe_command()
        result = run_lightweight_command(["<command-not-configured>"], self.config.request_timeout) if command is None else self._command_runner(command, self.config.request_timeout)
        self._probe_cache = {
            "backend_id": self.config.backend_id,
            "transport": self.config.transport,
            "available": result.ok,
            "command_probe": result.model_dump(mode="json"),
            "launch_attempted": False,
        }
        return self._probe_cache

    def _probe_command(self) -> list[str] | None:
        if not self.config.command:
            return None
        return [self.config.command, *self.config.command_args]

    def _fetch_cdp_json(self, path: str) -> dict[str, Any]:
        if not self.config.browser_url:
            return {"ok": False, "unavailable_reason": "browser_url_not_configured"}
        url = self.config.browser_url.rstrip("/") + path
        try:
            status, text, content_type = self._http_getter(url, self.config.request_timeout)
            payload = json.loads(text) if text else None
        except Exception as exc:
            return {"ok": False, "url": url, "unavailable_reason": str(exc)}
        return {"ok": 200 <= status < 300, "url": url, "status": status, "content_type": content_type, "payload": payload}

    def _fetch_page_sources(self, page_url: str) -> None:
        if self._source_cache_url != page_url:
            self._source_cache = {}
            self._source_cache_url = page_url
        if "page-html" in self._source_cache:
            return
        try:
            status, html, content_type = self._http_getter(page_url, self.config.request_timeout)
        except Exception as exc:
            self._source_cache["page-fetch-error"] = {"url": page_url, "source": str(exc), "kind": "error"}
            return
        self._source_cache["page-html"] = {"url": page_url, "source": html, "status": status, "content_type": content_type, "kind": "html"}
        parser = _ScriptSrcParser()
        parser.feed(html)
        for index, script_src in enumerate(parser.script_srcs[: self.config.source_fetch_limit], start=1):
            script_url = urljoin(page_url, script_src)
            if not self._looks_like_http_url(script_url):
                continue
            try:
                script_status, script_text, script_content_type = self._http_getter(script_url, self.config.request_timeout)
            except Exception:
                continue
            self._source_cache[f"script-{index}"] = {
                "url": script_url,
                "source": script_text,
                "status": script_status,
                "content_type": script_content_type,
                "kind": "script",
            }

    @staticmethod
    def _looks_like_http_url(value: str | None) -> bool:
        if not value:
            return False
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _default_http_get(self, url: str, timeout: float) -> tuple[int, str, str]:
        request = Request(url, headers={"User-Agent": self.config.user_agent})
        with urlopen(request, timeout=timeout) as response:  # nosec B310 - user-supplied local/authorized reverse target.
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body, response.headers.get("content-type", "")


class _ScriptSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.script_srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attrs_dict = {key.lower(): value for key, value in attrs if key}
        src = attrs_dict.get("src")
        if src:
            self.script_srcs.append(src)


def run_lightweight_command(command: list[str], timeout: float) -> LightweightCommandResult:
    """Run a side-effect-light local command probe."""

    if not command:
        return LightweightCommandResult(command=command, ok=False, unavailable_reason="empty command")
    executable = command[0]
    if executable.startswith("<") and executable.endswith(">"):
        return LightweightCommandResult(command=command, ok=False, unavailable_reason=executable.strip("<>"))
    if shutil.which(executable) is None and "/" not in executable:
        return LightweightCommandResult(command=command, ok=False, unavailable_reason=f"command not found: {executable}")
    try:
        proc = subprocess.run(  # noqa: S603 - explicit local tooling command configured by user/runtime.
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return LightweightCommandResult(
            command=command,
            ok=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            unavailable_reason=f"timeout after {timeout}s",
        )
    except OSError as exc:
        return LightweightCommandResult(command=command, ok=False, unavailable_reason=str(exc))
    return LightweightCommandResult(command=command, ok=proc.returncode == 0, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def create_lightweight_web_runtime(
    *,
    config: LightweightWebRuntimeConfig,
    command_runner: CommandRunner | None = None,
    http_getter: HttpGetter | None = None,
) -> JSReverserRuntime:
    """Create a JSReverserRuntime backed by lightweight Web bridge probes."""

    bridge = LightweightWebBridge(config=config, command_runner=command_runner, http_getter=http_getter)
    return JSReverserRuntime(
        bridge=bridge,
        backend_id=config.backend_id,
        display_name=config.display_name,
        transport=config.transport,
        default_page_size=config.default_page_size,
        backend_config=config.safe_summary(),
    )


__all__ = [
    "LightweightCommandResult",
    "LightweightWebBridge",
    "LightweightWebRuntimeConfig",
    "create_lightweight_web_runtime",
    "run_lightweight_command",
]
