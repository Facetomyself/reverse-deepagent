from __future__ import annotations

import base64
import importlib
import json
import sys
import threading
import tomllib
import unittest
from pathlib import Path

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_smoke_row
from tests.test_remote_cdp_provider import FakeCDPServer


class RuntimeWrapper:
    def __init__(self, browser_provider):
        self.browser_provider = browser_provider


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-browserless-cdp"
MODULE_NAME = "reverse_deepagent_browser_provider_browserless_cdp"


class FakeBrowserlessWebSocketServer:
    def __init__(self) -> None:
        self.current_url = "about:blank"
        self.target_id = "target-page-1"
        self.session_id = "session-page-1"
        self.ws_server = serve(self._handle_ws, "127.0.0.1", 0)
        self.ws_thread = threading.Thread(target=self.ws_server.serve_forever, daemon=True)
        self.ws_thread.start()
        self.ws_port = self.ws_server.socket.getsockname()[1]
        self.ws_url = f"ws://127.0.0.1:{self.ws_port}/?session=raw-session-value"

    def close(self) -> None:
        self.ws_server.shutdown()
        self.ws_thread.join(timeout=2)

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
                result = {"data": base64.b64encode(b"browserless-png").decode("ascii")}
            websocket.send(json.dumps({"id": message.get("id"), "result": result}))

    def _target(self) -> dict[str, str]:
        return {
            "targetId": self.target_id,
            "type": "page",
            "url": self.current_url,
            "title": "Fake Browserless CDP",
        }

    def _runtime_evaluate(self, expression: str) -> dict[str, object]:
        if expression == "window.location.href":
            value: object = self.current_url
        elif expression == "document.title":
            value = "Fake Browserless CDP"
        elif "document.documentElement.outerHTML" in expression:
            value = '<html><body><script>function browserlessSign(){return "x";}</script></body></html>'
        elif expression == "(() => ({ok: true, answer: 42}))()":
            value = {"ok": True, "answer": 42}
        else:
            value = None
        return {"result": {"type": "object" if isinstance(value, dict) else "string", "value": value}}


class BrowserProviderPluginBrowserlessCDPTests(unittest.TestCase):
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
        module.reset_browserless_state()
        return module

    def test_package_declares_browserless_cdp_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-browserless-cdp")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["browserless-cdp"],
            "reverse_deepagent_browser_provider_browserless_cdp:browser_provider_registration",
        )
        self.assertIn("reverse-deepagent==0.1.0", pyproject["project"]["dependencies"])

    def test_registration_metadata_is_side_effect_free_and_readiness_checked(self) -> None:
        module = self._import_module()
        registration = module.browser_provider_registration()
        registry = BrowserProviderRegistry()
        registry.register(registration)
        metadata = registry.list_registration_metadata()
        matrix = browser_provider_metadata_matrix_payload(provider_metadata=metadata)

        self.assertEqual(module.factory_invocation_count(), 0)
        self.assertEqual(module.connection_event_log(), [])
        self.assertEqual(registration.provider_id, "browserless-cdp")
        self.assertIn("browserless", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertFalse(metadata[0]["supports_launch"])
        self.assertTrue(metadata[0]["supports_cdp"])
        self.assertTrue(metadata[0]["managed_browser"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "review-required")
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        checks = {item["check_id"]: item for item in matrix["providers"][0]["production_readiness"]["checks"]}
        self.assertEqual(checks["provider_specific:browserless_cdp_contract_declared"]["status"], "pass")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)

        provider = registry.create(
            "browserless",
            browser_ws_url="wss://viewer:example@production.example.browserless.io?session=raw-session-value",
            service_base_url="https://viewer:example@api.browserless.io/sessions?session=raw-session-value",
            access_material_configured=True,
        )
        self.assertEqual(module.factory_invocation_count(), 1)
        self.assertEqual(module.connection_event_log(), [])
        summary = provider.describe().config
        self.assertEqual(summary["browser_ws_url"], "wss://production.example.browserless.io?query=%3Credacted%3E")
        self.assertEqual(summary["service_base_url"], "https://api.browserless.io/sessions?query=%3Credacted%3E")
        self.assertTrue(summary["endpoint_configured"])
        self.assertTrue(summary["access_material_configured"])
        self.assertNotIn("raw-session-value", str(summary))
        self.assertNotIn("viewer:example", str(summary))

    def test_missing_endpoint_blocks_start_and_connect_with_guidance(self) -> None:
        module = self._import_module()
        provider = module.create_browserless_cdp_browser_provider()
        self.assertFalse(provider.is_available())
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.start()
        self.assertEqual(module.connection_event_log(), [])

    def test_http_devtools_endpoint_delegates_to_remote_cdp(self) -> None:
        module = self._import_module()
        server = FakeCDPServer()
        try:
            provider = module.create_browserless_cdp_browser_provider(
                browser_url=server.browser_url,
                browser_navigation_wait=0,
            )
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/browserless-http")
            self.assertEqual(page.url, "https://example.test/browserless-http")
            self.assertEqual(page.title(), "Fake CDP")
            provider.stop()
            self.assertEqual(module.connection_event_log()[0]["event"], "connect_http_devtools")
        finally:
            server.close()

    def test_direct_browser_websocket_endpoint_supports_minimal_page_flow(self) -> None:
        module = self._import_module()
        server = FakeBrowserlessWebSocketServer()
        try:
            provider = module.create_browserless_cdp_browser_provider(
                browser_ws_url=server.ws_url,
                browser_navigation_wait=0,
            )
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/browserless-ws")
            self.assertEqual(page.url, "https://example.test/browserless-ws")
            self.assertEqual(page.title(), "Fake Browserless CDP")
            self.assertIn("browserlessSign", page.content())
            self.assertEqual(page.evaluate("(() => ({ok: true, answer: 42}))()")["answer"], 42)
            self.assertEqual(page.screenshot(), b"browserless-png")
            refs = session.list_pages()
            self.assertEqual(refs[0].url, "https://example.test/browserless-ws")
            provider.stop()
            events = module.connection_event_log()
            self.assertEqual(events[0]["event"], "connect_browser_websocket")
            self.assertEqual(events[0]["browser_ws_url"], f"ws://127.0.0.1:{server.ws_port}/?query=%3Credacted%3E")
        finally:
            server.close()

    def test_launch_smoke_uses_browserless_connect_contract(self) -> None:
        module = self._import_module()
        server = FakeBrowserlessWebSocketServer()
        try:
            registry = BrowserProviderRegistry()
            registry.register(module.browser_provider_registration())

            def provider_factory(*, browser: str, **kwargs):
                return RuntimeWrapper(registry.create(browser, **kwargs))

            row = browser_provider_smoke_row(
                provider_id="browserless",
                provider_factory=provider_factory,
                provider_kwargs={
                    "browser_ws_url": server.ws_url,
                    "browser_navigation_wait": 0,
                },
                include_availability=True,
                launch_smoke=True,
                smoke_url="https://example.test/browserless-smoke",
            )
            self.assertTrue(row["ok"])
            self.assertTrue(row["available"])
            self.assertTrue(row["launched"])
            self.assertEqual(row["smoke"]["status"], "passed")
            self.assertEqual(module.connection_event_log()[0]["event"], "connect_browser_websocket")
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
