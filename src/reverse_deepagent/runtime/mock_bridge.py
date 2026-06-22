"""Deterministic JSReverser bridge for local demo and contract validation."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen


class MockJSReverserBridge:
    """Deterministic JSReverser bridge for local demo and contract validation.

    The mock backend is intentionally profile-aware for localhost fixture URLs:
    it reads the fixture ``/app.js`` source, exposes matching network/source
    evidence, and returns validation samples that agree with the selected
    fixture profile. Non-fixture demo runs keep the historical static example.
    """

    def __init__(self, active_url: str = "https://example.com/search") -> None:
        self.active_url = active_url
        self._source_cache: dict[str, str] = {}
        self._health_cache: dict[str, Any] = {}

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        if tool_name == "check_browser_health":
            return {"status": "ok", "connected": True}
        if tool_name == "list_pages":
            return {"pages": [{"pageIdx": 0, "url": self.active_url, "selected": True}]}
        if tool_name == "new_page":
            self.active_url = str(params.get("url") or self.active_url)
            return {"ok": True, "created": True, "url": self.active_url}
        if tool_name == "navigate_page":
            self.active_url = str(params.get("url") or self.active_url)
            return {"ok": True, "navigated": True, "url": self.active_url}
        if tool_name == "network_request":
            return {"requests": self._network_requests()}
        if tool_name == "search_in_sources":
            return {"results": [self._source_hit(params.get("query", "sign"))]}
        if tool_name == "evaluate_script" and "__REVERSE_AGENT_VALIDATE_CANDIDATE__" in str(params.get("function", "")):
            return {"ok": True, "result": self._validation_result()}
        if tool_name == "evaluate_script":
            function_source = str(params.get("function", ""))
            if "dumpStorage" in function_source or "navigator" in function_source:
                return {"ok": True, "result": self._runtime_environment()}
            return {"ok": True, "result": {"readyState": "complete", "url": self.active_url}}
        if tool_name == "get_storage":
            return self._storage_payload()
        if tool_name == "get_request_initiator":
            return {
                "requestId": params.get("requestId"),
                "initiator": "window.reverseFixture.search -> fetch('/api/search')",
                "stack": ["search", "fetch"],
            }
        if tool_name == "get_script_source":
            return {
                "scriptId": params.get("scriptId"),
                "startLine": params.get("startLine"),
                "endLine": params.get("endLine"),
                "source": self._source_text(),
            }
        if tool_name == "inject_preload_script":
            return {"ok": True}
        if tool_name == "export_session_report":
            return {"ok": True, "format": params.get("format", "json"), "items": 3, "active_url": self.active_url}
        raise RuntimeError(f"Unsupported mock tool: {tool_name}")

    def _network_requests(self) -> list[dict[str, Any]]:
        if self._is_fixture_url():
            requests = [
                {"id": 101, "url": urljoin(self.active_url.rstrip("/") + "/", "api/search"), "method": "POST"},
                {"id": 102, "url": urljoin(self.active_url.rstrip("/") + "/", "app.js"), "method": "GET"},
            ]
            if self._profile() == "token-chain":
                requests.insert(0, {"id": 100, "url": urljoin(self.active_url.rstrip("/") + "/", "api/bootstrap"), "method": "GET"})
            return requests
        return [
            {"id": 101, "url": "https://example.com/api/search", "method": "POST"},
            {"id": 102, "url": "https://example.com/api/bootstrap", "method": "GET"},
        ]

    def _source_hit(self, query: Any) -> dict[str, Any]:
        source = self._source_text()
        line_number = self._build_sign_line_number(source)
        preview = self._line_at(source, line_number) or f"const token = build('{query}')"
        return {
            "scriptId": "fixture-app" if self._is_fixture_url() else "1",
            "url": urljoin(self.active_url.rstrip("/") + "/", "app.js") if self._is_fixture_url() else "https://example.com/static/app.js",
            "lineNumber": line_number,
            "preview": preview,
        }

    def _validation_result(self) -> dict[str, Any]:
        sign = self._sample_sign()
        return {
            "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
            "function_name": "buildSign",
            "located": True,
            "callable_path": "window.reverseFixture.buildSign",
            "invocation_ok": True,
            "invocation_result_type": "string",
            "sign": sign,
            "sign_shape_ok": bool(sign),
            "replay_result": {
                "attempted": True,
                "ok": bool(sign),
                "status": 200,
                "echoed_sign": sign,
                "body": {"headers": {"x-sign": sign, "x-fixture-profile": self._profile()}},
            },
            "runtime_url": self.active_url,
        }

    def _source_text(self) -> str:
        if not self._is_fixture_url():
            return "function buildSign(keyword, timestamp) {\n  return `sig_${keyword}_${timestamp}`;\n}"
        app_js_url = urljoin(self.active_url.rstrip("/") + "/", "app.js")
        if app_js_url not in self._source_cache:
            self._source_cache[app_js_url] = self._fetch_text(app_js_url)
        return self._source_cache[app_js_url]

    def _health(self) -> dict[str, Any]:
        if not self._is_fixture_url():
            return {}
        health_url = urljoin(self.active_url.rstrip("/") + "/", "healthz")
        if health_url not in self._health_cache:
            try:
                self._health_cache[health_url] = json.loads(self._fetch_text(health_url))
            except Exception:
                self._health_cache[health_url] = {}
        return self._health_cache[health_url] if isinstance(self._health_cache[health_url], dict) else {}

    def _profile(self) -> str:
        return str(self._health().get("profile") or "default")

    def _sample_sign(self) -> str:
        keyword = "sign"
        timestamp = 1700000000000
        profile = self._profile()
        if not self._is_fixture_url():
            return f"sig_{keyword}_{timestamp}"
        raw = f"{keyword}:{timestamp}"
        if profile == "default":
            seeded = f"{raw}:reverse-agent-fixture"
            digest = sum(ord(char) for char in seeded) % 100000
            return f"sig_{digest:x}_{timestamp}"
        if profile == "md5":
            return hashlib.md5(raw.encode("utf-8")).hexdigest()  # noqa: S324 - deterministic fixture compatibility
        if profile == "sha1":
            return hashlib.sha1(raw.encode("utf-8")).hexdigest()  # noqa: S324 - deterministic fixture compatibility
        if profile in {"sha256", "webpack-minified"}:
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if profile == "base64":
            return base64.b64encode(raw.encode("utf-8")).decode("ascii")
        if profile == "context-localstorage":
            return base64.b64encode(f"{raw}:fixture-device".encode("utf-8")).decode("ascii")
        if profile == "context-cookie":
            return base64.b64encode(f"{raw}:fixture-cookie-device".encode("utf-8")).decode("ascii")
        if profile == "context-navigator":
            return hashlib.sha256(f"{raw}:ReverseDeepAgentMock/1.0".encode("utf-8")).hexdigest()
        if profile == "token-chain":
            return hashlib.sha256(f"{raw}:fixture-token".encode("utf-8")).hexdigest()
        if profile == "hybrid-context":
            return base64.b64encode(f"{raw}:fixture-nonce:fixture-csrf".encode("utf-8")).decode("ascii")
        return f"sig_{keyword}_{timestamp}"

    def _storage_payload(self) -> dict[str, Any]:
        profile = self._profile()
        local_storage: dict[str, str] = {}
        session_storage: dict[str, str] = {}
        cookies: dict[str, str] = {}
        if profile == "context-localstorage":
            local_storage["device_id"] = "fixture-device"
        elif profile == "hybrid-context":
            local_storage["fixture_nonce"] = "fixture-nonce"
            cookies["csrf_token"] = "fixture-csrf"
        if profile == "token-chain":
            session_storage["fixture_token"] = "fixture-token"
        if profile == "context-cookie":
            cookies["device_id"] = "fixture-cookie-device"
        return {
            "localStorage": local_storage,
            "sessionStorage": session_storage,
            "cookies": cookies,
        }

    def _runtime_environment(self) -> dict[str, Any]:
        profile = self._profile()
        cookie = ""
        local_storage: dict[str, str] = {}
        session_storage: dict[str, str] = {}
        if profile == "context-cookie":
            cookie = "device_id=fixture-cookie-device"
        elif profile == "context-localstorage":
            local_storage["device_id"] = "fixture-device"
        elif profile == "token-chain":
            session_storage["fixture_token"] = "fixture-token"
        elif profile == "hybrid-context":
            cookie = "csrf_token=fixture-csrf"
            local_storage["fixture_nonce"] = "fixture-nonce"
        return {
            "cookie": cookie,
            "localStorage": local_storage,
            "sessionStorage": session_storage,
            "navigator": {
                "userAgent": "ReverseDeepAgentMock/1.0",
                "platform": "MacIntel",
                "language": "zh-CN",
            },
            "timezoneOffset": -480,
        }

    def _is_fixture_url(self) -> bool:
        parsed = urlparse(self.active_url)
        return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}

    @staticmethod
    def _fetch_text(url: str) -> str:
        with urlopen(url, timeout=5) as response:  # nosec B310 - local fixture smoke only
            return response.read().decode("utf-8")

    @staticmethod
    def _build_sign_line_number(source: str) -> int:
        for index, line in enumerate(source.splitlines(), start=1):
            if "function buildSign" in line:
                return index
        return 1

    @staticmethod
    def _line_at(source: str, line_number: int) -> str:
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
