from __future__ import annotations

from typing import Any

from reverse_deepagent.browser.base import BrowserCDPSession, BrowserPage

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


class CDPEnhancedCollector:
    """Collect best-effort CDP-enhanced metadata with explicit unsupported fallback."""

    def collect(self, page: BrowserPage, network_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        session = page.cdp_session()
        if session is None:
            return self._unsupported("cdp_session_unavailable")

        domains = self._enable_domains(session)
        request_initiators = self._collect_request_initiators(page)
        response_bodies = self._collect_response_bodies(session, network_snapshot or {})
        script_sources = self._collect_script_sources(session)
        websocket_frames = self._collect_websocket_frames_placeholder(domains)
        ok = any(
            item.get("status") == "success"
            for item in (request_initiators, response_bodies, script_sources, websocket_frames)
            if isinstance(item, dict)
        )
        return {
            "ok": ok,
            "supported": True,
            "domains": domains,
            "request_initiators": request_initiators,
            "response_bodies": response_bodies,
            "script_sources": script_sources,
            "websocket_frames": websocket_frames,
        }

    @staticmethod
    def _unsupported(reason: str) -> dict[str, Any]:
        item = {"status": "unsupported", "reason": reason, "count": 0, "items": []}
        return {
            "ok": False,
            "supported": False,
            "reason": reason,
            "domains": {},
            "request_initiators": item,
            "response_bodies": item,
            "script_sources": item,
            "websocket_frames": item,
        }

    @staticmethod
    def _enable_domains(session: BrowserCDPSession) -> dict[str, Any]:
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
    def _collect_response_bodies(session: BrowserCDPSession, network_snapshot: dict[str, Any]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        missing_request_id = 0
        for request in network_snapshot.get("requests", []) or []:
            if not isinstance(request, dict):
                continue
            request_id = request.get("requestId") or request.get("request_id")
            if not request_id:
                missing_request_id += 1
                continue
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
    def _collect_script_sources(session: BrowserCDPSession) -> dict[str, Any]:
        # Full script source capture requires Debugger.scriptParsed event buffering. This baseline
        # explicitly reports that the domain is reachable while event-backed cache is still pending.
        try:
            session.send("Debugger.enable", {})
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "count": 0, "items": []}
        return {"status": "unsupported", "reason": "scriptParsed_event_cache_not_implemented", "count": 0, "items": []}

    @staticmethod
    def _collect_websocket_frames_placeholder(domains: dict[str, Any]) -> dict[str, Any]:
        if not domains.get("Network", {}).get("ok"):
            return {"status": "unsupported", "reason": "network_domain_unavailable", "count": 0, "items": []}
        return {"status": "unsupported", "reason": "websocket_event_cache_not_implemented", "count": 0, "items": []}
