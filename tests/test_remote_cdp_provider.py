import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from reverse_deepagent.browser.providers import RemoteCDPConfig, RemoteCDPProvider
from reverse_deepagent.coordinator import build_runtime


class FakeCDPServer:
    def __init__(self) -> None:
        self.current_url = "about:blank"
        self.ws_server = serve(self._handle_ws, "127.0.0.1", 0)
        self.ws_thread = threading.Thread(target=self.ws_server.serve_forever, daemon=True)
        self.ws_thread.start()
        self.ws_port = self.ws_server.socket.getsockname()[1]
        self.http_server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
        self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        self.http_port = self.http_server.server_address[1]
        self.browser_url = f"http://127.0.0.1:{self.http_port}"
        self.ws_url = f"ws://127.0.0.1:{self.ws_port}/devtools/page/page-1"

    def close(self) -> None:
        self.http_server.shutdown()
        self.http_server.server_close()
        self.ws_server.shutdown()
        self.http_thread.join(timeout=2)
        self.ws_thread.join(timeout=2)

    def _make_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/json/version":
                    self._write({"Browser": "FakeChrome", "webSocketDebuggerUrl": outer.ws_url})
                    return
                if self.path == "/json/list":
                    self._write([outer._target()])
                    return
                self.send_error(404)

            def do_PUT(self):
                if self.path.startswith("/json/new"):
                    outer.current_url = "about:blank"
                    self._write(outer._target())
                    return
                self.send_error(404)

            def log_message(self, *_args):
                return

            def _write(self, payload):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _target(self):
        return {
            "id": "page-1",
            "type": "page",
            "url": self.current_url,
            "title": "Fake CDP",
            "webSocketDebuggerUrl": self.ws_url,
        }

    def _handle_ws(self, websocket) -> None:
        while True:
            try:
                raw = websocket.recv()
            except ConnectionClosed:
                return
            message = json.loads(raw)
            method = message.get("method")
            params = message.get("params") or {}
            result = {}
            if method == "Runtime.evaluate":
                result = self._runtime_evaluate(params.get("expression", ""))
            elif method == "Page.navigate":
                self.current_url = params.get("url", self.current_url)
            elif method == "Page.captureScreenshot":
                result = {"data": base64.b64encode(b"png").decode("ascii")}
            websocket.send(json.dumps({"id": message.get("id"), "result": result}))

    def _runtime_evaluate(self, expression: str):
        if expression == "window.location.href":
            value = self.current_url
        elif expression == "document.title":
            value = "Fake CDP"
        elif "document.documentElement.outerHTML" in expression:
            value = '<html><head><script src="/app.js"></script></head><body><script>function buildSign(){return "x";}</script></body></html>'
        elif expression == "(() => ({ok: true, answer: 42}))()":
            value = {"ok": True, "answer": 42}
        else:
            value = None
        return {"result": {"type": "object" if isinstance(value, dict) else "string", "value": value}}


class RemoteCDPProviderTests(unittest.TestCase):
    def test_provider_connects_to_existing_cdp_endpoint(self) -> None:
        server = FakeCDPServer()
        try:
            provider = RemoteCDPProvider(RemoteCDPConfig(browser_url=server.browser_url, navigation_wait=0))
            self.assertTrue(provider.is_available())
            capabilities = provider.describe().model_dump(mode="json")
            self.assertEqual(capabilities["provider_id"], "remote-cdp")
            self.assertEqual(capabilities["transport"], "remote-cdp")

            session = provider.start()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/app")
            self.assertEqual(page.url, "https://example.test/app")
            self.assertEqual(page.title(), "Fake CDP")
            self.assertIn("buildSign", page.content())
            self.assertEqual(page.evaluate("(() => ({ok: true, answer: 42}))()")["answer"], 42)
            self.assertEqual(page.screenshot(), b"png")
        finally:
            server.close()

    def test_runtime_factory_selects_remote_cdp_provider(self) -> None:
        server = FakeCDPServer()
        try:
            runtime = build_runtime("remote-cdp", browser_url=server.browser_url)
            provider = runtime.browser_provider
            self.assertEqual(provider.describe().provider_id, "remote-cdp")
            self.assertTrue(provider.is_available())
        finally:
            server.close()

    def test_capability_summary_redacts_url_credentials(self) -> None:
        provider = RemoteCDPProvider(RemoteCDPConfig(browser_url="http://user:pass@127.0.0.1:9222"))
        summary = provider.describe().model_dump(mode="json")["config"]
        self.assertEqual(summary["browser_url"], "http://127.0.0.1:9222")


if __name__ == "__main__":
    unittest.main()
