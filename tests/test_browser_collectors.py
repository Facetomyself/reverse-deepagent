import unittest

from reverse_deepagent.browser import PlaywrightBrowserPageAdapter
from reverse_deepagent.browser.collectors import (
    ConsoleCollector,
    DOMCollector,
    NetworkCollector,
    ScreenshotCollector,
    ScriptCollector,
    StorageCollector,
)


class FakeRawPage:
    def __init__(self) -> None:
        self.url = "https://example.test/app"
        self.handlers = {}
        self.screenshots = []

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event, payload):
        for handler in self.handlers.get(event, []):
            handler(payload)

    def title(self):
        return "Example App"

    def content(self):
        return """
        <html>
          <head><script src="/assets/app.js"></script></head>
          <body>
            <script>const sign = "demo"; function buildSign(){ return sign; }</script>
          </body>
        </html>
        """

    def evaluate(self, expression):
        if "fetch(" in expression and "/assets/app.js" in expression:
            return "function buildExternalSign(){ return 'external'; }"
        return {
            "cookie": "sid=raw-session; csrf=raw-csrf",
            "localStorage": {"theme": "dark", "auth_token": "raw-local-auth-token"},
            "sessionStorage": {"nonce": "123", "session": "raw-session-storage-secret"},
            "navigator": {"userAgent": "fake", "webdriver": False},
            "timezoneOffset": -480,
        }

    def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)
        return b"png" if "path" not in kwargs else None


class FakeConsoleMessage:
    def type(self):
        return "log"

    def text(self):
        return "hello"


class FakeRequest:
    def __init__(self, url="https://example.test/api/search") -> None:
        self.url = url
        self.method = "POST"
        self.resource_type = "xhr"
        self.requestId = "request-123"
        self.headers = {
            "x-demo": "1",
            "Authorization": "Bearer raw-authorization-token",
            "Cookie": "sid=raw-cookie; csrf=raw-csrf-cookie",
            "Proxy-Authorization": "Basic raw-proxy-authorization",
            "X-API-Key": "raw-api-key",
            "csrf_token": "raw-csrf-token",
            "auth_token": "raw-header-auth-token",
            "session": "raw-header-session",
        }


class FakeResponse:
    def __init__(self, request) -> None:
        self.request = request
        self.status = 200
        self.ok = True
        self.headers = {
            "content-type": "application/json",
            "Set-Cookie": "sid=raw-set-cookie; HttpOnly",
        }


class BrowserCollectorTests(unittest.TestCase):
    def make_page(self) -> PlaywrightBrowserPageAdapter:
        return PlaywrightBrowserPageAdapter(FakeRawPage())

    def test_dom_storage_script_and_screenshot_collectors(self) -> None:
        page = self.make_page()

        dom = DOMCollector().collect(page)
        self.assertEqual(dom["url"], "https://example.test/app")
        self.assertEqual(dom["title"], "Example App")
        self.assertGreater(dom["html_size"], 0)

        storage = StorageCollector().collect(page)
        self.assertTrue(storage["ok"])
        self.assertEqual(storage["localStorage"]["theme"], "dark")
        self.assertIn("auth_token", storage["localStorage"])
        self.assertEqual(storage["sessionStorage"]["nonce"], "123")
        self.assertIn("session", storage["sessionStorage"])
        self.assertFalse(storage["navigator"]["webdriver"])
        storage_snapshot = str(storage)
        for raw_secret in (
            "raw-session",
            "raw-csrf",
            "raw-local-auth-token",
            "raw-session-storage-secret",
        ):
            self.assertNotIn(raw_secret, storage_snapshot)

        inventory = ScriptCollector().collect(page)
        self.assertEqual(inventory["count"], 2)
        hits = ScriptCollector().search(inventory, "buildSign")
        self.assertEqual(hits["count"], 1)
        self.assertEqual(hits["results"][0]["kind"], "inline")
        external_hits = ScriptCollector().search(inventory, "buildExternalSign")
        self.assertEqual(external_hits["count"], 1)
        self.assertEqual(external_hits["results"][0]["kind"], "external")

        screenshot = ScreenshotCollector().collect(page)
        self.assertTrue(screenshot["in_memory"])
        self.assertEqual(screenshot["bytes"], 3)
        saved = ScreenshotCollector().collect(page, path="/tmp/example.png")
        self.assertFalse(saved["in_memory"])
        self.assertEqual(saved["path"], "/tmp/example.png")

    def test_console_and_network_collectors_attach_to_raw_page_events(self) -> None:
        page = self.make_page()
        raw = page.raw_page

        console = ConsoleCollector()
        self.assertTrue(console.attach(page))
        raw.emit("console", FakeConsoleMessage())
        console_snapshot = console.snapshot()
        self.assertEqual(console_snapshot["count"], 1)
        self.assertEqual(console_snapshot["messages"][0]["text"], "hello")

        network = NetworkCollector()
        self.assertTrue(network.attach(page))
        request = FakeRequest()
        raw.emit("request", request)
        raw.emit("response", FakeResponse(request))
        network_snapshot = network.snapshot()
        self.assertEqual(network_snapshot["count"], 1)
        item = network_snapshot["requests"][0]
        self.assertEqual(item["method"], "POST")
        self.assertEqual(item["status"], 200)
        self.assertEqual(item["resource_type"], "xhr")
        self.assertEqual(item["requestId"], "request-123")
        self.assertEqual(item["headers"]["x-demo"], "1")
        for header_name in (
            "Authorization",
            "Cookie",
            "Proxy-Authorization",
            "X-API-Key",
            "csrf_token",
            "auth_token",
            "session",
        ):
            self.assertIn(header_name, item["headers"])
        self.assertIn("Set-Cookie", item["response_headers"])
        network_snapshot_text = str(network_snapshot)
        for raw_secret in (
            "raw-authorization-token",
            "raw-cookie",
            "raw-csrf-cookie",
            "raw-proxy-authorization",
            "raw-api-key",
            "raw-csrf-token",
            "raw-header-auth-token",
            "raw-header-session",
            "raw-set-cookie",
        ):
            self.assertNotIn(raw_secret, network_snapshot_text)


if __name__ == "__main__":
    unittest.main()
