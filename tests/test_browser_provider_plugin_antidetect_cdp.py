from __future__ import annotations

import importlib
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from reverse_deepagent.browser.base import BrowserProviderUnavailableError
from reverse_deepagent.browser.registry import BrowserProviderRegistry
from reverse_deepagent.browser.smoke import browser_provider_metadata_matrix_payload, browser_provider_production_readiness


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-browser-provider-antidetect-cdp"
MODULE_NAME = "reverse_deepagent_browser_provider_antidetect_cdp"


class FakeAntiDetectDirectCDPConnection:
    def __init__(self, ws_url: str, *, timeout: float = 5.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self.opened = False
        self.closed = False
        self.current_url = "about:blank"
        self.target_id = "target-page-1"
        self.session_id = "session-page-1"

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True

    def send(self, method: str, params: dict | None = None, *, session_id: str | None = None):
        params = params or {}
        if method == "Target.getTargets":
            return {"targetInfos": [self._target()]}
        if method == "Target.createTarget":
            self.current_url = params.get("url") or "about:blank"
            return {"targetId": self.target_id}
        if method == "Target.attachToTarget":
            return {"sessionId": self.session_id}
        if method == "Page.enable" or method == "Runtime.enable":
            return {}
        if method == "Page.navigate":
            self.current_url = params.get("url", self.current_url)
            return {}
        if method == "Page.captureScreenshot":
            return {"data": "YW50aWRldGVjdC1wbmc="}
        if method == "Runtime.evaluate":
            return self._runtime_evaluate(params.get("expression", ""))
        return {}

    def _target(self) -> dict[str, str]:
        return {
            "targetId": self.target_id,
            "type": "page",
            "url": self.current_url,
            "title": "Fake AntiDetect CDP",
        }

    def _runtime_evaluate(self, expression: str) -> dict[str, object]:
        if expression == "window.location.href":
            value: object = self.current_url
        elif expression == "document.title":
            value = "Fake AntiDetect CDP"
        elif "document.documentElement.outerHTML" in expression:
            value = '<html><body><script>function antiDetectSign(){return "x";}</script></body></html>'
        elif expression == "(() => ({ok: true, answer: 44}))()":
            value = {"ok": True, "answer": 44}
        else:
            value = None
        return {"result": {"type": "object" if isinstance(value, dict) else "string", "value": value}}


class BrowserProviderPluginAntiDetectCDPTests(unittest.TestCase):
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
        module.reset_antidetect_state()
        return module

    def test_package_declares_antidetect_cdp_browser_provider_entry_point(self) -> None:
        pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(pyproject["project"]["name"], "reverse-deepagent-browser-provider-antidetect-cdp")
        entry_points = pyproject["project"]["entry-points"]["reverse_deepagent.browser_providers"]
        self.assertEqual(
            entry_points["antidetect-cdp"],
            "reverse_deepagent_browser_provider_antidetect_cdp:browser_provider_registration",
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
        self.assertEqual(registration.provider_id, "antidetect-cdp")
        self.assertIn("anti-detect-cdp", metadata[0]["aliases"])
        self.assertFalse(metadata[0]["supports_launch"])
        self.assertTrue(metadata[0]["supports_connect"])
        self.assertTrue(metadata[0]["supports_cdp"])
        self.assertTrue(metadata[0]["supports_stealth"])
        self.assertTrue(metadata[0]["supports_humanize"])
        self.assertTrue(metadata[0]["supports_persistent_context"])
        self.assertTrue(metadata[0]["managed_browser"])
        self.assertEqual(metadata[0]["production_readiness"]["readiness_tier"], "review-required")
        self.assertEqual(
            metadata[0]["production_readiness"]["profile_persistence_policy"],
            "vendor-profile-id-or-account-profile-controls-persistence-outside-core",
        )
        self.assertTrue(matrix["ok"])
        self.assertEqual(matrix["providers"][0]["production_readiness"]["status"], "review-required")
        checks = {item["check_id"]: item for item in matrix["providers"][0]["production_readiness"]["checks"]}
        self.assertEqual(checks["provider_specific:antidetect_cdp_contract_declared"]["status"], "pass")
        self.assertEqual(matrix["summary"]["production_readiness"]["review_required_count"], 1)

        provider = registry.create(
            "anti-detect-cdp",
            browser_ws_url="wss://operator:secret@vendor.example/connect?token=raw-secret-token",
            allocation_id="allocation-sensitive-1234",
            profile_id="profile-sensitive-5678",
            tenant_label="reviewed-tenant",
        )
        self.assertEqual(module.factory_invocation_count(), 1)
        self.assertEqual(module.connection_event_log(), [])
        summary = provider.describe().config
        self.assertEqual(summary["browser_ws_url"], "wss://vendor.example/connect?query=%3Credacted%3E")
        self.assertEqual(summary["allocation_id"], "alloca...1234")
        self.assertEqual(summary["profile_id"], "profil...5678")
        self.assertTrue(summary["endpoint_configured"])
        self.assertTrue(summary["allocation_metadata_configured"])
        self.assertNotIn("raw-secret-token", str(summary))
        self.assertNotIn("operator:secret", str(summary))
        self.assertNotIn("allocation-sensitive-1234", str(summary))
        self.assertNotIn("profile-sensitive-5678", str(summary))

    def test_missing_endpoint_blocks_start_and_connect_with_guidance(self) -> None:
        module = self._import_module()
        provider = module.create_antidetect_cdp_browser_provider()
        self.assertFalse(provider.is_available())
        with self.assertRaisesRegex(BrowserProviderUnavailableError, "requires browser_url"):
            provider.connect()
        with self.assertRaisesRegex(BrowserProviderUnavailableError, r"start\(\) is review-gated"):
            provider.start()
        self.assertEqual(module.connection_event_log(), [])

    def test_reviewed_browser_websocket_endpoint_supports_minimal_page_flow(self) -> None:
        module = self._import_module()
        ws_url = "ws://operator:secret@127.0.0.1:9222/connect?token=raw-antidetect-token"
        with patch.object(module, "AntiDetectDirectCDPConnection", FakeAntiDetectDirectCDPConnection):
            provider = module.create_antidetect_cdp_browser_provider(
                browser_ws_url=ws_url,
                allocation_id="allocation-sensitive-1234",
                profile_id="profile-sensitive-5678",
                browser_navigation_wait=0,
            )
            self.assertTrue(provider.is_available())
            session = provider.connect()
            page = session.get_active_page()
            self.assertIsNotNone(page)
            assert page is not None
            page.goto("https://example.test/antidetect-connect")
            self.assertEqual(page.url, "https://example.test/antidetect-connect")
            self.assertEqual(page.title(), "Fake AntiDetect CDP")
            self.assertIn("antiDetectSign", page.content())
            self.assertEqual(page.evaluate("(() => ({ok: true, answer: 44}))()")["answer"], 44)
            self.assertEqual(page.screenshot(), b"antidetect-png")
            refs = session.list_pages()
            self.assertEqual(refs[0].url, "https://example.test/antidetect-connect")
            provider.stop()
            events = module.connection_event_log()
            self.assertEqual(events[0]["event"], "connect_browser_websocket")
            self.assertEqual(events[0]["browser_ws_url"], "ws://127.0.0.1:9222/connect?query=%3Credacted%3E")
            self.assertEqual(events[0]["allocation_id"], "alloca...1234")
            self.assertEqual(events[0]["profile_id"], "profil...5678")
            self.assertEqual(events[1]["event"], "close_local_attach_only")
            self.assertNotIn("raw-antidetect-token", str(events))
            self.assertNotIn("operator:secret", str(events))

    def test_provider_specific_readiness_marks_missing_antidetect_metadata_incomplete(self) -> None:
        module = self._import_module()
        capabilities = module.antidetect_cdp_browser_provider_capabilities().model_copy(deep=True)
        profile = dict(capabilities.production_readiness)
        profile.pop("stealth_policy")
        profile.pop("profile_persistence_policy")
        capabilities.production_readiness = profile

        readiness = browser_provider_production_readiness(capabilities.model_dump(mode="json"))

        self.assertEqual(readiness["status"], "metadata-incomplete")
        self.assertIn("stealth_policy", readiness["missing_metadata"])
        self.assertIn("profile_persistence_policy", readiness["missing_metadata"])
        checks = {item["check_id"]: item for item in readiness["checks"]}
        self.assertEqual(checks["provider_specific:antidetect_cdp_contract_declared"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
