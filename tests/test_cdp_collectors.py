import unittest

from reverse_deepagent.browser.collectors.cdp import CDPEnhancedCollector


class NoCDPPage:
    url = "https://example.test/app"

    def cdp_session(self):
        return None


class FakeCDPSession:
    def __init__(self) -> None:
        self.calls = []

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Network.getResponseBody":
            return {"body": '{"ok":true}', "base64Encoded": False}
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


if __name__ == "__main__":
    unittest.main()
