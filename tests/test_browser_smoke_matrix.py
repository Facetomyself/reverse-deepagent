import unittest

from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.smoke import (
    BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
    DEFAULT_BROWSER_PROVIDER_MATRIX,
    list_browser_provider_compatibility_rules,
    browser_provider_metadata_matrix_payload,
    browser_provider_smoke_matrix_payload,
    browser_provider_smoke_row,
    legacy_browser_provider_payload_from_smoke_row,
    validate_browser_provider_capability_compatibility,
)


class FakeProvider:
    def __init__(self, provider_id: str, available: bool = True) -> None:
        self.provider_id = provider_id
        self.available = available
        self.started = False
        self.stopped = False

    def describe(self) -> BrowserProviderCapabilities:
        return BrowserProviderCapabilities(
            provider_id=self.provider_id,
            display_name=f"Fake {self.provider_id}",
            engine="chromium",
            transport="fake",
            supports_launch=True,
            supports_connect=True,
            supports_persistent_context=True,
            supports_cdp=True,
            supports_playwright_api=True,
            supports_network_events=True,
            supports_response_body=True,
            supports_request_initiator=True,
            supports_script_source=True,
            supports_websocket_frames=True,
            supports_breakpoints=True,
            supports_runtime_eval=True,
            managed_browser=True,
        )

    def is_available(self) -> bool:
        return self.available

    def start(self):
        self.started = True
        return FakeSession(self.provider_id)

    def stop(self) -> None:
        self.stopped = True


class FakeRuntime:
    def __init__(self, provider: FakeProvider) -> None:
        self.browser_provider = provider


class FakeSession:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.page = FakePage()

    def get_active_page(self):
        return self.page

    def new_page(self, url: str | None = None):
        if url:
            self.page.goto(url)
        return self.page

    def list_pages(self):
        return []


class FakePage:
    url = "about:blank"

    def goto(self, url: str, timeout=None) -> None:
        self.url = url

    def title(self) -> str:
        return "Fake page"


class BrowserProviderSmokeMatrixTests(unittest.TestCase):
    def fake_factory(self, *, browser: str, **kwargs):
        return FakeRuntime(FakeProvider(browser, available=kwargs.get("available", True)))

    def test_metadata_matrix_is_side_effect_free_by_default(self) -> None:
        payload = browser_provider_smoke_matrix_payload(
            provider_ids=DEFAULT_BROWSER_PROVIDER_MATRIX,
            provider_factory=self.fake_factory,
            provider_kwargs={"available": True},
        )
        self.assertEqual(payload["summary"]["provider_count"], len(DEFAULT_BROWSER_PROVIDER_MATRIX))
        self.assertTrue(payload["side_effect_policy"]["metadata_only_by_default"])
        self.assertFalse(payload["side_effect_policy"]["availability_check_requested"])
        self.assertFalse(payload["side_effect_policy"]["launch_smoke_requested"])
        for row in payload["providers"]:
            self.assertTrue(row["configured"])
            self.assertTrue(row["ok"])
            self.assertIsNone(row["available"])
            self.assertEqual(row["smoke"]["status"], "skipped")
            lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
            self.assertEqual(lifecycle["availability_checked"], "not_checked")
            self.assertEqual(lifecycle["session_start_requested"], "skipped")



    def test_compatibility_rule_catalog_is_serializable_and_extensible(self) -> None:
        rules = list_browser_provider_compatibility_rules()
        rule_ids = {rule["rule_id"] for rule in rules}
        self.assertIn("breakpoints_require_cdp", rule_ids)
        self.assertIn("humanize_requires_page_control_transport", rule_ids)
        self.assertIn("mobile_emulation_requires_page_control_transport", rule_ids)
        self.assertIn("extensions_require_launch_or_persistent_context", rule_ids)
        self.assertIn("proxy_requires_launch_or_managed_browser", rule_ids)
        for rule in rules:
            self.assertIn(rule["severity"], {"error", "warning"})
            self.assertIn("message", rule)
            self.assertIsInstance(rule["when_all"], list)
            self.assertIsInstance(rule["requires_any"], list)

    def test_registration_metadata_matrix_does_not_call_provider_factory(self) -> None:
        metadata = [
            BrowserProviderCapabilities(
                provider_id="registered-browser",
                display_name="Registered Browser",
                engine="chromium",
                transport="registry",
                supports_connect=True,
                supports_cdp=True,
                supports_runtime_eval=True,
            ).model_dump(mode="json")
            | {"aliases": ["registered-alias"], "keys": ["registered-browser", "registered-alias"]}
        ]

        payload = browser_provider_metadata_matrix_payload(provider_metadata=metadata)

        self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["compatibility_rule_version"], BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION)
        self.assertIn("compatibility_rules", payload)
        self.assertGreater(len(payload["compatibility_rules"]), 5)
        self.assertEqual(payload["summary"]["provider_count"], 1)
        self.assertEqual(payload["summary"]["compatibility"]["compatible_count"], 1)
        row = payload["providers"][0]
        self.assertEqual(row["provider_id"], "registered-browser")
        self.assertEqual(row["aliases"], ["registered-alias"])
        self.assertEqual(row["supported_modes"], ["connect", "cdp", "runtime-eval"])
        self.assertEqual(row["compatibility"]["status"], "compatible")
        lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
        self.assertEqual(lifecycle["configured"], "ok")
        self.assertEqual(lifecycle["availability_checked"], "not_checked")
        self.assertEqual(row["smoke"]["status"], "skipped")

    def test_capability_compatibility_flags_invalid_breakpoint_combo(self) -> None:
        compatibility = validate_browser_provider_capability_compatibility(
            BrowserProviderCapabilities(
                provider_id="bad-debugger",
                display_name="Bad Debugger",
                supports_launch=True,
                supports_breakpoints=True,
                supports_runtime_eval=True,
            ).model_dump(mode="json")
        )

        self.assertFalse(compatibility["ok"])
        self.assertEqual(compatibility["status"], "error")
        self.assertIn("breakpoints_require_cdp", {item["code"] for item in compatibility["errors"]})
        self.assertGreaterEqual(compatibility["rule_count"], 10)
        self.assertGreaterEqual(compatibility["evaluated_rule_count"], 2)

    def test_new_provider_flags_emit_compatibility_warnings(self) -> None:
        compatibility = validate_browser_provider_capability_compatibility(
            BrowserProviderCapabilities(
                provider_id="thin-stealth-service",
                display_name="Thin Stealth Service",
                supports_connect=True,
                supports_proxy=True,
                supports_humanize=True,
                supports_mobile_emulation=True,
                supports_extensions=True,
            ).model_dump(mode="json")
        )

        self.assertTrue(compatibility["ok"])
        self.assertEqual(compatibility["status"], "warning")
        warning_codes = {item["code"] for item in compatibility["warnings"]}
        self.assertIn("humanize_requires_page_control_transport", warning_codes)
        self.assertIn("mobile_emulation_requires_page_control_transport", warning_codes)
        self.assertIn("extensions_require_launch_or_persistent_context", warning_codes)
        self.assertIn("proxy_requires_launch_or_managed_browser", warning_codes)

    def test_metadata_matrix_marks_incompatible_provider_not_ok(self) -> None:
        metadata = [
            BrowserProviderCapabilities(
                provider_id="bad-websocket",
                display_name="Bad WebSocket",
                supports_connect=True,
                supports_websocket_frames=True,
            ).model_dump(mode="json")
        ]

        payload = browser_provider_metadata_matrix_payload(provider_metadata=metadata)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["summary"]["compatibility"]["error_count"], 1)
        self.assertEqual(payload["providers"][0]["compatibility"]["status"], "error")

    def test_availability_and_launch_lifecycle_are_recorded(self) -> None:
        row = browser_provider_smoke_row(
            provider_id="fake-browser",
            provider_factory=self.fake_factory,
            provider_kwargs={"available": True},
            include_availability=True,
            launch_smoke=True,
            smoke_url="https://example.test",
        )
        self.assertTrue(row["ok"])
        self.assertTrue(row["available"])
        self.assertTrue(row["launched"])
        self.assertEqual(row["smoke"]["status"], "passed")
        self.assertEqual(row["smoke"]["url"], "https://example.test")
        lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
        self.assertEqual(lifecycle["session_opened"], "ok")
        self.assertEqual(lifecycle["page_ready"], "ok")
        self.assertEqual(lifecycle["session_closed"], "ok")

    def test_unavailable_provider_blocks_launch_smoke(self) -> None:
        row = browser_provider_smoke_row(
            provider_id="fake-browser",
            provider_factory=self.fake_factory,
            provider_kwargs={"available": False},
            include_availability=True,
            launch_smoke=True,
        )
        self.assertFalse(row["ok"])
        self.assertFalse(row["available"])
        self.assertFalse(row["launched"])
        self.assertEqual(row["smoke"]["status"], "blocked")

    def test_legacy_doctor_payload_projection_keeps_old_shape(self) -> None:
        row = browser_provider_smoke_row(
            provider_id="fake-browser",
            provider_factory=self.fake_factory,
            provider_kwargs={"available": True},
            include_availability=True,
            launch_smoke=False,
        )
        payload = legacy_browser_provider_payload_from_smoke_row(row)
        self.assertEqual(payload["browser"], "fake-browser")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["available"])
        self.assertFalse(payload["launched"])
        self.assertIn("capabilities", payload)
        self.assertIn("smoke_matrix", payload)


if __name__ == "__main__":
    unittest.main()
