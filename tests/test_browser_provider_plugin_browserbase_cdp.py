from __future__ import annotations

import base64
import importlib
import json
import sys
import threading
import tomllib
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_smoke_row


class RuntimeWrapper:
    def __init__(self, browser_provider):
        self.browser_provider = browser_provider


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-browserbase-cdp"
MODULE_NAME = "reverse_deepagent_browser_provider_browserbase_cdp"


class FakeBrowserbaseWebSocketServer:
    def __init__(self) -> None:
        self.current_url = "about:blank"
        self.target_id = "target-page-1"
        self.session_id = "session-page-1"
        self.ws_server = serve(self._handle_ws, "127.0.0.1", 0)
        self.ws_thread = threading.Thread(target=self.ws_server.serve_forever, daemon=True)
        self.ws_thread.start()
        self.ws_port = self.ws_server.socket.getsockname()[1]
        self.ws_url = f"ws://127.0.0.1:{self.ws_port}/connect?token=raw-browserbase-token"

    def close(self) -> None:
        self.ws_server.shutdown()
        self.ws_thread.join(timeout=2)
        server_close = getattr(self.ws_server, "server_close", None)
        if callable(server_close):
            server_close()

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
            if method == "Target.getTargets":
                result = {"targetInfos": [self._target()]}
            elif method == "Target.createTarget":
                self.current_url = params.get("url") or "about:blank"
                result = {"targetId": self.target_id}
            elif method == "Target.attachToTarget":
                result = {"sessionId": self.session_id}
            elif method == "Runtime.evaluate":
                result = self._runtime_evaluate(params.get("expression", ""))
            elif method == "Page.navigate":
                self.current_url = params.get("url", self.current_url)
            elif method == "Page.captureScreenshot":
                result = {"data": base64.b64encode(b"browserbase-png").decode("ascii")}
            websocket.send(json.dumps({"id": message.get("id"), "result": result}))

    def _target(self) -> dict[str, str]:
        return {
            "targetId": self.target_id,
            "type": "page",
            "url": self.current_url,
            "title": "Fake Browserbase CDP",
        }

    def _runtime_evaluate(self, expression: str) -> dict[str, object]:
        if expression == "window.location.href":
            value: object = self.current_url
        elif expression == "document.title":
            value = "Fake Browserbase CDP"
        elif "document.documentElement.outerHTML" in expression:
            value = '<html><body><script>function browserbaseSign(){return "x";}</script></body></html>'
        elif expression == "(() => ({ok: true, answer: 43}))()":
            value = {"ok": True, "answer": 43}
        else:
            value = None
        return {"result": {"type": "object" if isinstance(value, dict) else "string", "value": value}}


class FakeBrowserbaseAPIServer:
    def __init__(self, connect_url: str) -> None:
        self.connect_url = connect_url
        self.requests: list[dict[str, object]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
                outer.requests.append(
                    {
                        "path": self.path,
                        "api_key": self.headers.get("X-BB-API-Key"),
                        "body": json.loads(body.decode("utf-8") or "{}"),
                    }
                )
                if self.path != "/v1/sessions":
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = {
                    "id": "browserbase-session-sensitive-1234",
                    "projectId": "project-sensitive-5678",
                    "connectUrl": outer.connect_url,
                }
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format, *args):  # noqa: A002
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def close(self) -> None:
        self.httpd.shutdown()
        self.thread.join(timeout=2)
        self.httpd.server_close()


class BrowserProviderPluginBrowserbaseCDPTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop(MODULE_NAME, None)

    def tearDown(self) -> None:
        sys.modules.pop(MODULE_NAME, None)
        package_src = str(PACKAGE_ROOT / "src")
        while package_src in sys.path:
            sys.path.remove(package_src)

    def _import_module(self):
        package_src = str(PACKAGE_ROOT / "src")
        if package_src not in sys.path:
            sys.path.insert(0, package_src)
        module = importlib.import_module(MODULE_NAME)
        module.reset_browserbase_state()
        return module

    def test_package_declares_browserbase_cdp_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-browserbase-cdp")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["browserbase-cdp"],
            "reverse_deepagent_browser_provider_browserbase_cdp:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_review_required(self) -> None:
        module = self._import_module()
        registration = module.browser_provider_registration()
        registry = BrowserProviderRegistry()
        registry.register(registration)
        metadata = registry.list_registration_metadata()
        matrix = browser_provider_metadata_matrix_payload(provider_metadata=metadata)

        self.assertEqual(module.factory_invocation_count(), 0)
        self.assertEqual(module.session_event_log(), [])
        self.assertEqual(registration.provider_id, "browserbase-cdp")
        self.assertIn("browserbase", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_launch"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertTrue(metadata[0]["supports_cdp"])
        self.assertTrue(metadata[0]["managed_browser"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "review-required")
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)

        provider = registry.create(
            "browserbase",
            connect_url="wss://user:pass@sessions.browserbase.com/connect?apiKey=raw-secret",
            api_key="bb_raw_api_key",
            project_id="project-sensitive-5678",
        )
        self.assertEqual(module.factory_invocation_count(), 1)
        self.assertEqual(module.session_event_log(), [])
        summary = provider.describe().config
        self.assertEqual(summary["connect_url"], "wss://sessions.browserbase.com/connect?query=%3Credacted%3E")
        self.assertTrue(summary["access_material_configured"])
        self.assertEqual(summary["project_id"], "projec...5678")
        self.assertNotIn("bb_raw_api_key", str(summary))
        self.assertNotIn("raw-secret", str(summary))
        self.assertNotIn("user:pass", str(summary))

    def test_missing_config_blocks_start_and_connect_with_guidance(self) -> None:
        module = self._import_module()
        provider = module.create_browserbase_cdp_browser_provider()
        self.assertFalse(provider.is_available())
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires connect_url"):
            provider.connect()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires api_key"):
            provider.start()
        self.assertEqual(module.session_event_log(), [])

    def test_reviewed_connect_url_supports_minimal_page_flow(self) -> None:
        module = self._import_module()
        server = FakeBrowserbaseWebSocketServer()
        try:
            provider = module.create_browserbase_cdp_browser_provider(
                connect_url=server.ws_url,
                browser_navigation_wait=0,
            )
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/browserbase-connect")
            self.assertEqual(page.url, "https://example.test/browserbase-connect")
            self.assertEqual(page.title(), "Fake Browserbase CDP")
            self.assertIn("browserbaseSign", page.content())
            self.assertEqual(page.evaluate("(() => ({ok: true, answer: 43}))()")["answer"], 43)
            self.assertEqual(page.screenshot(), b"browserbase-png")
            refs = session.list_pages()
            self.assertEqual(refs[0].url, "https://example.test/browserbase-connect")
            provider.stop()
            events = module.session_event_log()
            self.assertEqual(events[0]["event"], "attach_existing")
            self.assertEqual(events[1]["event"], "connect")
            self.assertEqual(events[1]["connect_url"], f"ws://127.0.0.1:{server.ws_port}/connect?query=%3Credacted%3E")
        finally:
            server.close()

    def test_explicit_start_creates_browserbase_session_and_launch_smoke_uses_connect_url(self) -> None:
        module = self._import_module()
        ws_server = FakeBrowserbaseWebSocketServer()
        api_server = FakeBrowserbaseAPIServer(ws_server.ws_url)
        try:
            registry = BrowserProviderRegistry()
            registry.register(module.browser_provider_registration())

            def provider_factory(*, browser: str, **kwargs):
                return RuntimeWrapper(registry.create(browser, **kwargs))

            row = browser_provider_smoke_row(
                provider_id="browserbase",
                provider_factory=provider_factory,
                provider_kwargs={
                    "api_base_url": api_server.url,
                    "api_key": "bb_raw_api_key",
                    "project_id": "project-sensitive-5678",
                    "keep_alive": True,
                    "session_timeout_seconds": 120,
                    "browser_navigation_wait": 0,
                },
                include_availability=True,
                launch_smoke=True,
                smoke_url="https://example.test/browserbase-smoke",
            )
            self.assertTrue(row["ok"])
            self.assertTrue(row["available"])
            self.assertTrue(row["launched"])
            self.assertEqual(row["smoke"]["status"], "passed")
            self.assertEqual(len(api_server.requests), 1)
            request = api_server.requests[0]
            self.assertEqual(request["path"], "/v1/sessions")
            self.assertEqual(request["api_key"], "bb_raw_api_key")
            self.assertEqual(request["body"]["projectId"], "project-sensitive-5678")
            self.assertTrue(request["body"]["keepAlive"])
            self.assertEqual(request["body"]["browserSettings"]["timeout"], 120)
            events = module.session_event_log()
            self.assertEqual([item["event"] for item in events[:2]], ["create_session", "start"])
            self.assertNotIn("bb_raw_api_key", str(events))
            self.assertNotIn("raw-browserbase-token", str(events))
            self.assertIn("close_local_session", [item["event"] for item in events])
        finally:
            api_server.close()
            ws_server.close()


if __name__ == "__main__":
    unittest.main()
