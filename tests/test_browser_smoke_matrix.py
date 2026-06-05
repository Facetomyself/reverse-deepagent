import unittest

from reverse_deepagent.browser.capabilities import BrowserProviderCapabilities
from reverse_deepagent.browser.providers import CloakBrowserProvider, PlaywrightChromiumProvider, RemoteCDPProvider
from reverse_deepagent.browser.smoke import (
    BROWSER_PROVIDER_COMPATIBILITY_RULE_VERSION,
    BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION,
    DEFAULT_BROWSER_PROVIDER_MATRIX,
    browser_provider_production_readiness,
    list_browser_provider_compatibility_rules,
    browser_provider_metadata_matrix_payload,
    browser_provider_smoke_matrix_payload,
    browser_provider_smoke_row,
    legacy_browser_provider_payload_from_smoke_row,
    list_browser_provider_production_readiness_rules,
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


    def test_production_readiness_rule_catalog_is_serializable_and_provider_specific(self) -> None:
        rules = list_browser_provider_production_readiness_rules()
        rule_ids = {rule["rule_id"] for rule in rules}
        self.assertIn("playwright_chromium_lifecycle_declared", rule_ids)
        self.assertIn("remote_cdp_attach_contract_declared", rule_ids)
        self.assertIn("cloakbrowser_production_lifecycle_declared", rule_ids)
        self.assertIn("hosted_cdp_reference_lifecycle_declared", rule_ids)
        self.assertIn("browserless_cdp_contract_declared", rule_ids)
        playwright_rule = next(rule for rule in rules if rule["rule_id"] == "playwright_chromium_lifecycle_declared")
        self.assertEqual(playwright_rule["provider_ids"], ["playwright-chromium"])
        self.assertEqual(playwright_rule["transports"], ["playwright"])
        self.assertIn("supports_persistent_context", playwright_rule["requires_all"])
        remote_rule = next(rule for rule in rules if rule["rule_id"] == "remote_cdp_attach_contract_declared")
        self.assertEqual(remote_rule["provider_ids"], ["remote-cdp"])
        self.assertEqual(remote_rule["metadata_equals"]["profile_lifecycle"], "external-browser-owned")
        cloak_rule = next(rule for rule in rules if rule["rule_id"] == "cloakbrowser_production_lifecycle_declared")
        self.assertEqual(cloak_rule["provider_ids"], ["cloakbrowser"])
        self.assertIn("supports_stealth", cloak_rule["requires_all"])
        hosted_rule = next(rule for rule in rules if rule["rule_id"] == "hosted_cdp_reference_lifecycle_declared")
        self.assertEqual(hosted_rule["severity"], "warning")
        self.assertEqual(hosted_rule["provider_ids"], ["hosted-cdp-reference"])
        self.assertIn("supports_launch", hosted_rule["requires_all"])
        self.assertEqual(hosted_rule["metadata_equals"]["session_recovery"], "session-id-reattach-or-endpoint-connect")
        browserless_rule = next(rule for rule in rules if rule["rule_id"] == "browserless_cdp_contract_declared")
        self.assertEqual(browserless_rule["provider_ids"], ["browserless-cdp"])
        self.assertEqual(browserless_rule["transports"], ["browserless-cdp"])
        self.assertIn("supports_runtime_eval", browserless_rule["requires_all"])
        self.assertEqual(browserless_rule["metadata_equals"]["health_check_mode"], "explicit-browserless-cdp-contract-smoke")
        self.assertIn("endpoint_security_policy", remote_rule["required_metadata_keys"])
        self.assertIn("stealth_policy", cloak_rule["required_metadata_keys"])
        self.assertIn("allocation_lifecycle_policy", hosted_rule["required_metadata_keys"])
        self.assertIn("account_boundary_policy", browserless_rule["required_metadata_keys"])

    def test_builtin_provider_specific_readiness_rules_pass_without_runtime_side_effects(self) -> None:
        providers = [
            PlaywrightChromiumProvider(),
            RemoteCDPProvider(),
            CloakBrowserProvider(),
        ]

        for provider in providers:
            with self.subTest(provider_id=provider.provider_id):
                readiness = browser_provider_production_readiness(provider.describe().model_dump(mode="json"))
                checks = {item["check_id"]: item for item in readiness["checks"]}
                provider_specific = [
                    item
                    for item in checks.values()
                    if str(item["check_id"]).startswith("provider_specific:")
                ]
                self.assertGreaterEqual(len(provider_specific), 1)
                self.assertTrue(all(item["status"] == "pass" for item in provider_specific))
                self.assertFalse(readiness["side_effect_policy"]["provider_factory_invoked"])
                self.assertFalse(readiness["side_effect_policy"]["availability_checked"])
                self.assertFalse(readiness["side_effect_policy"]["starts_browser"])

    def test_provider_specific_readiness_rule_warns_on_drift(self) -> None:
        readiness = browser_provider_production_readiness(
            BrowserProviderCapabilities(
                provider_id="hosted-cdp-reference",
                display_name="Hosted CDP Reference",
                transport="hosted-cdp-reference",
                supports_launch=True,
                supports_connect=True,
                supports_cdp=True,
                managed_browser=False,
                production_readiness={
                    "readiness_tier": "review-required",
                    "health_check_mode": "explicit-endpoint-probe-after-vendor-session-allocation",
                    "profile_lifecycle": "external-service-session-owned",
                    "allocation_lifecycle_policy": "explicit-start-allocates-and-stop-releases-owned-session",
                    "endpoint_security_policy": "caller-owned-or-reference-allocated-redacted-cdp-endpoint",
                    "session_recovery": "connect-existing-endpoint",
                    "intended_use": "reference-implementation-for-hosted-cdp-provider-packages",
                    "side_effect_boundary": "metadata-only-by-default",
                },
            ).model_dump(mode="json")
        )

        self.assertEqual(readiness["status"], "review-required")
        self.assertIn("provider_specific:hosted_cdp_reference_lifecycle_declared", readiness["warnings"])
        checks = {item["check_id"]: item for item in readiness["checks"]}
        self.assertEqual(checks["provider_specific:hosted_cdp_reference_lifecycle_declared"]["status"], "warn")

    def test_provider_specific_required_metadata_marks_incomplete(self) -> None:
        readiness = browser_provider_production_readiness(
            BrowserProviderCapabilities(
                provider_id="cloakbrowser",
                display_name="CloakBrowser",
                transport="cloakbrowser-playwright",
                supports_launch=True,
                supports_connect=True,
                supports_persistent_context=True,
                supports_cdp=True,
                supports_playwright_api=True,
                supports_proxy=True,
                supports_stealth=True,
                supports_humanize=True,
                supports_extensions=True,
                supports_mobile_emulation=True,
                supports_network_events=True,
                supports_response_body=True,
                supports_request_initiator=True,
                supports_script_source=True,
                supports_websocket_frames=True,
                supports_breakpoints=True,
                supports_runtime_eval=True,
                managed_browser=True,
                production_readiness={
                    "readiness_tier": "production-ready",
                    "health_check_mode": "optional-sdk-or-connect-endpoint",
                    "profile_lifecycle": "persistent-context-supported",
                    "proxy_policy": "provider-level-redacted",
                    "extension_policy": "launch-or-persistent-context",
                    "humanize_policy": "supported",
                    "session_recovery": "connect-over-cdp-or-persistent-context",
                    "intended_use": "optional-stealth-browser-provider",
                    "side_effect_boundary": "metadata-only-by-default",
                },
            ).model_dump(mode="json")
        )

        self.assertEqual(readiness["status"], "metadata-incomplete")
        self.assertIn("stealth_policy", readiness["missing_metadata"])
        checks = {item["check_id"]: item for item in readiness["checks"]}
        provider_check = checks["provider_specific:cloakbrowser_production_lifecycle_declared"]
        self.assertEqual(provider_check["status"], "missing")
        self.assertEqual(provider_check["missing_metadata_keys"], ["stealth_policy"])
        self.assertFalse(readiness["side_effect_policy"]["starts_browser"])

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
        self.assertIn("production_readiness_rules", payload)
        self.assertGreater(len(payload["compatibility_rules"]), 5)
        self.assertGreaterEqual(len(payload["production_readiness_rules"]), 1)
        self.assertEqual(payload["summary"]["provider_count"], 1)
        self.assertEqual(payload["summary"]["compatibility"]["compatible_count"], 1)
        self.assertEqual(payload["production_readiness_version"], BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION)
        self.assertEqual(payload["summary"]["production_readiness"]["metadata_incomplete_count"], 1)
        row = payload["providers"][0]
        self.assertEqual(row["provider_id"], "registered-browser")
        self.assertEqual(row["aliases"], ["registered-alias"])
        self.assertEqual(row["supported_modes"], ["connect", "cdp", "runtime-eval"])
        self.assertEqual(row["compatibility"]["status"], "compatible")
        self.assertEqual(row["production_readiness"]["status"], "metadata-incomplete")
        self.assertFalse(row["production_readiness"]["side_effect_policy"]["starts_browser"])
        lifecycle = {item["stage"]: item["status"] for item in row["lifecycle"]}
        self.assertEqual(lifecycle["configured"], "ok")
        self.assertEqual(lifecycle["availability_checked"], "not_checked")
        self.assertEqual(row["smoke"]["status"], "skipped")

    def test_production_readiness_classifies_provider_metadata(self) -> None:
        readiness = browser_provider_production_readiness(
            BrowserProviderCapabilities(
                provider_id="production-browser",
                display_name="Production Browser",
                supports_launch=True,
                supports_connect=True,
                supports_persistent_context=True,
                supports_proxy=True,
                supports_extensions=True,
                supports_humanize=True,
                production_readiness={
                    "readiness_tier": "production-ready",
                    "health_check_mode": "explicit-metadata-or-launch-smoke",
                    "profile_lifecycle": "persistent-context-supported",
                    "proxy_policy": "provider-level-redacted",
                    "extension_policy": "launch-controlled",
                    "humanize_policy": "supported",
                    "session_recovery": "connect-or-launch",
                    "intended_use": "production-provider",
                    "side_effect_boundary": "metadata-only-by-default",
                },
            ).model_dump(mode="json")
        )

        self.assertEqual(readiness["version"], BROWSER_PROVIDER_PRODUCTION_READINESS_VERSION)
        self.assertEqual(readiness["status"], "production-ready")
        self.assertEqual(readiness["missing_metadata"], [])
        self.assertFalse(readiness["side_effect_policy"]["provider_factory_invoked"])
        self.assertFalse(readiness["side_effect_policy"]["availability_checked"])
        self.assertFalse(readiness["side_effect_policy"]["launch_smoke_requested"])

    def test_production_readiness_marks_template_metadata_incomplete(self) -> None:
        readiness = browser_provider_production_readiness(
            BrowserProviderCapabilities(
                provider_id="template-browser",
                display_name="Template Browser",
                production_readiness={
                    "readiness_tier": "template-only",
                    "health_check_mode": "replace-me",
                    "profile_lifecycle": "replace-me",
                    "session_recovery": "replace-me",
                    "intended_use": "copy-and-replace-provider-template",
                    "side_effect_boundary": "metadata-only-by-default",
                },
            ).model_dump(mode="json")
        )

        self.assertEqual(readiness["status"], "metadata-incomplete")
        self.assertIn("production_provider_replacement", readiness["missing_metadata"])

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
