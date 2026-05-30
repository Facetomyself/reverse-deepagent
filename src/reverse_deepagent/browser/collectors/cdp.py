from __future__ import annotations

from typing import Any, Callable

from reverse_deepagent.browser.base import BrowserCDPSession, BrowserPage
from reverse_deepagent.browser.collectors.scripts import ScriptCollector

PERFORMANCE_RESOURCE_EXPRESSION = """
(() => performance.getEntriesByType('resource').slice(-50).map((entry) => ({
  name: entry.name,
  initiatorType: entry.initiatorType,
  startTime: entry.startTime,
  duration: entry.duration,
  transferSize: entry.transferSize,
  encodedBodySize: entry.encodedBodySize,
  decodedBodySize: entry.decodedBodySize,
})))()
"""


class CDPEventCacheCollector:
    """Cache CDP events that must be subscribed before navigation."""

    def __init__(self, *, request_limit: int = 100, script_limit: int = 50, websocket_limit: int = 100, preview_limit: int = 240) -> None:
        self.request_limit = request_limit
        self.script_limit = script_limit
        self.websocket_limit = websocket_limit
        self.preview_limit = preview_limit
        self._session: BrowserCDPSession | None = None
        self._attached = False
        self._supported = False
        self._reason = "not_attached"
        self._domains: dict[str, Any] = {}
        self._request_initiators: list[dict[str, Any]] = []
        self._script_sources: list[dict[str, Any]] = []
        self._websocket_frames: list[dict[str, Any]] = []

    def attach(self, page: BrowserPage) -> bool:
        session = page.cdp_session()
        if session is None:
            self._reason = "cdp_session_unavailable"
            return False
        on = getattr(session, "on", None)
        if not callable(on):
            self._session = session
            self._domains = CDPEnhancedCollector.enable_domains(session)
            self._reason = "cdp_event_subscription_unavailable"
            return False

        self._session = session
        self._domains = CDPEnhancedCollector.enable_domains(session)
        self._subscribe(on, "Network.requestWillBeSent", self._handle_request_will_be_sent)
        self._subscribe(on, "Debugger.scriptParsed", self._handle_script_parsed)
        self._subscribe(on, "Network.webSocketFrameSent", lambda params: self._handle_websocket_frame("sent", params))
        self._subscribe(on, "Network.webSocketFrameReceived", lambda params: self._handle_websocket_frame("received", params))
        self._attached = True
        self._supported = True
        self._reason = "attached"
        return True

    @staticmethod
    def _subscribe(on: Callable[[str, Callable[[Any], None]], Any], event_name: str, handler: Callable[[Any], None]) -> None:
        on(event_name, handler)

    def snapshot(self) -> dict[str, Any]:
        return {
            "attached": self._attached,
            "supported": self._supported,
            "reason": self._reason,
            "domains": self._domains,
            "request_initiators": self._bucket(self._request_initiators, empty_reason="no_request_initiator_events"),
            "script_sources": self._bucket(self._script_sources, empty_reason="no_script_parsed_events"),
            "websocket_frames": self._bucket(self._websocket_frames, empty_reason="no_websocket_frame_events"),
        }

    @staticmethod
    def _bucket(items: list[dict[str, Any]], *, empty_reason: str) -> dict[str, Any]:
        if items:
            return {"status": "success", "count": len(items), "items": list(items)}
        return {"status": "unsupported", "reason": empty_reason, "count": 0, "items": []}

    def _handle_request_will_be_sent(self, params: Any) -> None:
        if len(self._request_initiators) >= self.request_limit or not isinstance(params, dict):
            return
        request = params.get("request") if isinstance(params.get("request"), dict) else {}
        self._request_initiators.append(
            {
                "requestId": params.get("requestId"),
                "loaderId": params.get("loaderId"),
                "url": request.get("url") or params.get("documentURL"),
                "method": request.get("method"),
                "resourceType": params.get("type"),
                "initiator": params.get("initiator"),
                "timestamp": params.get("timestamp"),
                "wallTime": params.get("wallTime"),
            }
        )

    def _handle_script_parsed(self, params: Any) -> None:
        if len(self._script_sources) >= self.script_limit or not isinstance(params, dict):
            return
        script_id = params.get("scriptId")
        item = {
            "scriptId": script_id,
            "url": params.get("url"),
            "startLine": params.get("startLine"),
            "endLine": params.get("endLine"),
            "hash": params.get("hash"),
        }
        if self._session is not None and script_id:
            try:
                payload = self._session.send("Debugger.getScriptSource", {"scriptId": script_id})
                source = str(payload.get("scriptSource", "")) if isinstance(payload, dict) else str(payload)
                item.update({"ok": True, "sourceSize": len(source), "sourcePreview": source[: self.preview_limit]})
            except Exception as exc:
                item.update({"ok": False, "error": str(exc)})
        self._script_sources.append(item)

    def _handle_websocket_frame(self, direction: str, params: Any) -> None:
        if len(self._websocket_frames) >= self.websocket_limit or not isinstance(params, dict):
            return
        response = params.get("response") if isinstance(params.get("response"), dict) else {}
        payload = str(response.get("payloadData", ""))
        self._websocket_frames.append(
            {
                "direction": direction,
                "requestId": params.get("requestId"),
                "timestamp": params.get("timestamp"),
                "opcode": response.get("opcode"),
                "mask": response.get("mask"),
                "payloadSize": len(payload),
                "payloadPreview": payload[: self.preview_limit],
            }
        )


class CDPEnhancedCollector:
    """Collect best-effort CDP-enhanced metadata with explicit unsupported fallback."""

    def collect(
        self,
        page: BrowserPage,
        network_snapshot: dict[str, Any] | None = None,
        event_snapshot: dict[str, Any] | None = None,
        hook_timeline: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = page.cdp_session()
        if session is None:
            return self._unsupported("cdp_session_unavailable")

        domains = self.enable_domains(session)
        event_snapshot = event_snapshot or {}
        request_initiators = self._prefer_event_bucket(event_snapshot, "request_initiators") or self._collect_request_initiators(page)
        response_bodies = self._collect_response_bodies(session, network_snapshot or {}, event_snapshot)
        script_sources = self._prefer_event_bucket(event_snapshot, "script_sources") or self._collect_script_sources(page, session)
        websocket_frames = (
            self._prefer_event_bucket(event_snapshot, "websocket_frames")
            or self._collect_websocket_frames_from_hooks(hook_timeline or {})
            or self._collect_websocket_frames_placeholder(domains)
        )
        ok = any(
            item.get("status") == "success"
            for item in (request_initiators, response_bodies, script_sources, websocket_frames)
            if isinstance(item, dict)
        )
        return {
            "ok": ok,
            "supported": True,
            "domains": domains,
            "event_cache": event_snapshot,
            "request_initiators": request_initiators,
            "response_bodies": response_bodies,
            "script_sources": script_sources,
            "websocket_frames": websocket_frames,
        }

    @staticmethod
    def _prefer_event_bucket(event_snapshot: dict[str, Any], key: str) -> dict[str, Any] | None:
        bucket = event_snapshot.get(key)
        if isinstance(bucket, dict) and bucket.get("status") == "success":
            return bucket
        return None

    @staticmethod
    def _unsupported(reason: str) -> dict[str, Any]:
        item = {"status": "unsupported", "reason": reason, "count": 0, "items": []}
        return {
            "ok": False,
            "supported": False,
            "reason": reason,
            "domains": {},
            "event_cache": {},
            "request_initiators": item,
            "response_bodies": item,
            "script_sources": item,
            "websocket_frames": item,
        }

    @staticmethod
    def enable_domains(session: BrowserCDPSession) -> dict[str, Any]:
        domains: dict[str, Any] = {}
        for domain, method in {
            "Network": "Network.enable",
            "Runtime": "Runtime.enable",
            "Debugger": "Debugger.enable",
        }.items():
            try:
                session.send(method, {})
                domains[domain] = {"ok": True}
            except Exception as exc:
                domains[domain] = {"ok": False, "error": str(exc)}
        return domains

    @staticmethod
    def _collect_request_initiators(page: BrowserPage) -> dict[str, Any]:
        try:
            result = page.evaluate(PERFORMANCE_RESOURCE_EXPRESSION)
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "count": 0, "items": []}
        if not isinstance(result, list):
            return {"status": "failed", "error": "performance resource expression returned non-list", "count": 0, "items": []}
        items = [item for item in result if isinstance(item, dict)]
        return {"status": "success", "count": len(items), "items": items}

    @staticmethod
    def _collect_response_bodies(session: BrowserCDPSession, network_snapshot: dict[str, Any], event_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        candidates.extend([request for request in network_snapshot.get("requests", []) or [] if isinstance(request, dict)])
        event_bucket = (event_snapshot or {}).get("request_initiators")
        if isinstance(event_bucket, dict):
            candidates.extend([request for request in event_bucket.get("items", []) or [] if isinstance(request, dict)])

        items: list[dict[str, Any]] = []
        missing_request_id = 0
        seen_request_ids: set[str] = set()
        for request in candidates:
            request_id = request.get("requestId") or request.get("request_id")
            if not request_id:
                missing_request_id += 1
                continue
            request_id = str(request_id)
            if request_id in seen_request_ids:
                continue
            seen_request_ids.add(request_id)
            try:
                body = session.send("Network.getResponseBody", {"requestId": request_id})
            except Exception as exc:
                items.append({"requestId": request_id, "url": request.get("url"), "ok": False, "error": str(exc)})
                continue
            body_text = str(body.get("body", "")) if isinstance(body, dict) else str(body)
            base64_encoded = bool(body.get("base64Encoded")) if isinstance(body, dict) else False
            items.append(
                {
                    "requestId": request_id,
                    "url": request.get("url"),
                    "ok": True,
                    "base64Encoded": base64_encoded,
                    "bodySize": len(body_text),
                    "preview": body_text[:240] if not base64_encoded else "<base64>",
                }
            )
        status = "success" if items else "unsupported"
        reason = None if items else "network_snapshot_has_no_request_ids"
        return {"status": status, "reason": reason, "count": len(items), "missing_request_id": missing_request_id, "items": items}

    @staticmethod
    def _collect_script_sources(page: BrowserPage, session: BrowserCDPSession) -> dict[str, Any]:
        debugger_enabled = True
        try:
            session.send("Debugger.enable", {})
        except Exception as exc:
            debugger_enabled = False
            debugger_error = str(exc)
        else:
            debugger_error = None

        try:
            inventory = ScriptCollector().collect(page)
        except Exception as exc:
            if debugger_enabled:
                return {"status": "unsupported", "reason": "script_inventory_unavailable", "error": str(exc), "count": 0, "items": []}
            return {"status": "failed", "error": debugger_error or str(exc), "count": 0, "items": []}

        items: list[dict[str, Any]] = []
        for item in inventory.get("scripts", []) or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or "")
            items.append(
                {
                    "scriptId": item.get("scriptId"),
                    "url": item.get("url"),
                    "kind": item.get("kind"),
                    "ok": True,
                    "sourceSize": len(source),
                    "sourcePreview": source[:240],
                    "fallback": "html_script_inventory",
                }
            )
        if not items:
            return {"status": "unsupported", "reason": "script_inventory_empty", "count": 0, "items": [], "debuggerEnabled": debugger_enabled}
        has_source = any(bool(item.get("sourcePreview")) for item in items)
        return {
            "status": "success" if has_source else "partial",
            "reason": None if has_source else "script_inventory_has_urls_without_inline_source",
            "count": len(items),
            "items": items,
            "debuggerEnabled": debugger_enabled,
            "debuggerError": debugger_error,
        }

    @staticmethod
    def _collect_websocket_frames_from_hooks(hook_timeline: dict[str, Any]) -> dict[str, Any] | None:
        snapshot = hook_timeline.get("snapshot") if isinstance(hook_timeline, dict) else None
        events = snapshot.get("events", []) if isinstance(snapshot, dict) else []
        items: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "websocket_frame":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            items.append(
                {
                    "direction": payload.get("direction"),
                    "url": payload.get("url"),
                    "timestamp": event.get("ts"),
                    "opcode": payload.get("opcode"),
                    "payloadSize": payload.get("payloadSize"),
                    "payloadPreview": payload.get("payloadPreview", ""),
                    "source": "runtime_hook_timeline",
                }
            )
        if not items:
            return None
        return {"status": "success", "count": len(items), "items": items, "source": "runtime_hook_timeline"}

    @staticmethod
    def _collect_websocket_frames_placeholder(domains: dict[str, Any]) -> dict[str, Any]:
        if not domains.get("Network", {}).get("ok"):
            return {"status": "unsupported", "reason": "network_domain_unavailable", "count": 0, "items": []}
        return {"status": "unsupported", "reason": "websocket_event_cache_not_implemented", "count": 0, "items": []}
