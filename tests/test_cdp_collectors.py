import unittest

from reverse_deepagent.browser.collectors.cdp import CDPEnhancedCollector, CDPEventCacheCollector


class NoCDPPage:
    url = "https://example.test/app"

    def cdp_session(self):
        return None


class FakeCDPSession:
    def __init__(self) -> None:
        self.calls = []
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name, payload):
        for handler in self.handlers.get(event_name, []):
            handler(payload)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Network.getResponseBody":
            return {"body": '{"ok":true}', "base64Encoded": False}
        if method == "Debugger.getScriptSource":
            return {"scriptSource": "function buildSign(){ return 'x-sign'; }"}
        return {}


class FakeCDPPage:
    url = "https://example.test/app"

    def __init__(self) -> None:
        self.session = FakeCDPSession()

    def cdp_session(self):
        return self.session

    def evaluate(self, expression):
        return [
            {
                "name": "https://example.test/api/search",
                "initiatorType": "fetch",
                "startTime": 1.0,
                "duration": 2.0,
                "transferSize": 128,
                "encodedBodySize": 64,
                "decodedBodySize": 64,
            }
        ]


class CDPEnhancedCollectorTests(unittest.TestCase):
    def test_collect_returns_unsupported_when_page_has_no_cdp_session(self) -> None:
        payload = CDPEnhancedCollector().collect(NoCDPPage())
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["supported"])
        self.assertEqual(payload["reason"], "cdp_session_unavailable")
        self.assertEqual(payload["request_initiators"]["status"], "unsupported")
        self.assertEqual(payload["response_bodies"]["status"], "unsupported")

    def test_collect_uses_cdp_for_response_body_metadata_and_runtime_resources(self) -> None:
        page = FakeCDPPage()
        payload = CDPEnhancedCollector().collect(
            page,
            {
                "requests": [
                    {
                        "requestId": "req-1",
                        "url": "https://example.test/api/search",
                    }
                ]
            },
        )
        self.assertTrue(payload["supported"])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["domains"]["Network"]["ok"])
        self.assertEqual(payload["request_initiators"]["count"], 1)
        self.assertEqual(payload["request_initiators"]["items"][0]["initiatorType"], "fetch")
        self.assertEqual(payload["response_bodies"]["status"], "success")
        self.assertEqual(payload["response_bodies"]["items"][0]["bodySize"], len('{"ok":true}'))
        self.assertEqual(payload["script_sources"]["status"], "unsupported")
        self.assertEqual(payload["websocket_frames"]["status"], "unsupported")
        self.assertIn(("Network.getResponseBody", {"requestId": "req-1"}), page.session.calls)

    def test_event_cache_collects_request_script_and_websocket_events(self) -> None:
        page = FakeCDPPage()
        cache = CDPEventCacheCollector()
        self.assertTrue(cache.attach(page))
        page.session.emit(
            "Network.requestWillBeSent",
            {
                "requestId": "req-evt-1",
                "loaderId": "loader-1",
                "type": "Fetch",
                "request": {"url": "https://example.test/api/sign", "method": "POST"},
                "initiator": {"type": "script", "stack": {"callFrames": [{"functionName": "buildSign"}]}},
                "timestamp": 1.0,
                "wallTime": 2.0,
            },
        )
        page.session.emit(
            "Debugger.scriptParsed",
            {"scriptId": "script-1", "url": "https://example.test/app.js", "startLine": 0, "endLine": 10, "hash": "abc"},
        )
        page.session.emit(
            "Network.webSocketFrameReceived",
            {"requestId": "ws-1", "timestamp": 3.0, "response": {"opcode": 1, "mask": False, "payloadData": "hello"}},
        )
        snapshot = cache.snapshot()
        self.assertEqual(snapshot["request_initiators"]["status"], "success")
        self.assertEqual(snapshot["request_initiators"]["items"][0]["requestId"], "req-evt-1")
        self.assertEqual(snapshot["script_sources"]["status"], "success")
        self.assertIn("buildSign", snapshot["script_sources"]["items"][0]["sourcePreview"])
        self.assertEqual(snapshot["websocket_frames"]["status"], "success")
        self.assertEqual(snapshot["websocket_frames"]["items"][0]["payloadPreview"], "hello")

    def test_enhanced_collector_prefers_event_cache_over_performance_fallback(self) -> None:
        page = FakeCDPPage()
        event_snapshot = {
            "request_initiators": {"status": "success", "count": 1, "items": [{"requestId": "req-evt-1", "url": "https://example.test/api/sign"}]},
            "script_sources": {"status": "success", "count": 1, "items": [{"scriptId": "script-1", "sourcePreview": "function buildSign(){}"}]},
            "websocket_frames": {"status": "success", "count": 1, "items": [{"requestId": "ws-1", "payloadPreview": "hello"}]},
        }
        payload = CDPEnhancedCollector().collect(page, {"requests": []}, event_snapshot)
        self.assertEqual(payload["request_initiators"]["items"][0]["requestId"], "req-evt-1")
        self.assertEqual(payload["response_bodies"]["status"], "success")
        self.assertEqual(payload["script_sources"]["status"], "success")
        self.assertEqual(payload["websocket_frames"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
