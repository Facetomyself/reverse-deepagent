import importlib
import socket
import sys
import tomllib
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

from reverse_deepagent.browser.capabilities import metadata_has_secret_like_keys
from reverse_deepagent.strategies import (
    StrategyDetectorProviderRegistration,
    StrategyDetectorProviderRegistry,
    StrategyDetectorRegistryError,
    build_default_strategy_detector_registry,
)


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-strategy-detector-reference" / "src"
PACKAGE_PYPROJECT = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-strategy-detector-reference" / "pyproject.toml"


class StrategyDetectorReferenceProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PACKAGE_SRC))
        self.addCleanup(self._remove_package_src)

    def _remove_package_src(self) -> None:
        try:
            sys.path.remove(str(PACKAGE_SRC))
        except ValueError:
            pass

    def test_pyproject_declares_strategy_detector_entry_point(self) -> None:
        text = PACKAGE_PYPROJECT.read_text(encoding="utf-8")
        config = tomllib.loads(text)
        entry_points = config["project"]["entry-points"]["reverse_deepagent.strategy_detectors"]

        self.assertIn('[project.entry-points."reverse_deepagent.strategy_detectors"]', text)
        self.assertEqual(
            entry_points["reference-strategy-detector"],
            "reverse_deepagent_strategy_detector_reference:strategy_detector_registration",
        )

    def test_registration_metadata_is_side_effect_free_and_non_secret(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        before = module.detector_invocation_count()

        with mock.patch("builtins.open", side_effect=AssertionError("metadata registration must not read files")), mock.patch.object(
            socket, "socket", side_effect=AssertionError("metadata registration must not access network")
        ):
            registration = module.strategy_detector_registration()
            metadata = registration.to_metadata()

        self.assertEqual(module.detector_invocation_count(), before)
        self.assertEqual(metadata["provider_id"], "reference-strategy-detector")
        self.assertEqual(metadata["aliases"], ["fixture-strategy-detector", "reference-detector"])
        self.assertEqual(metadata["rule_count"], 3)
        self.assertFalse(metadata_has_secret_like_keys(metadata["metadata"]))
        self.assertFalse(metadata_has_secret_like_keys(metadata["side_effect_policy"]))
        self.assertTrue(metadata["side_effect_policy"]["metadata_only"])
        self.assertTrue(metadata["side_effect_policy"]["read_only"])
        self.assertFalse(metadata["side_effect_policy"]["runtime_context_collected"])
        self.assertFalse(metadata["side_effect_policy"]["replay_executed"])
        self.assertFalse(metadata["side_effect_policy"]["browser_started"])
        self.assertFalse(metadata["side_effect_policy"]["calls_mcp"])
        self.assertFalse(metadata["side_effect_policy"]["mobile_runtime_used"])

    def test_secret_like_metadata_is_rejected_for_reference_registration_shape(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")

        with self.assertRaises(StrategyDetectorRegistryError):
            StrategyDetectorProviderRegistration(
                provider_id="bad-reference-provider",
                display_name="Bad Reference Provider",
                aliases=("bad-reference",),
                rules=module.REFERENCE_RULES,
                detector=module.reference_detector,
                description="bad metadata shape",
                metadata={"api_key": "do-not-allow"},
            )

    def test_factory_detector_is_explicit_and_marker_detection_is_deterministic(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        registration = module.strategy_detector_registration()
        before = module.detector_invocation_count()
        source = """
        window.webpackJsonp = window.webpackJsonp || [];
        function buildSign(keyword, timestamp) {
          const nonce = window.authToken || timestamp;
          const sig = CryptoJS.HmacSHA256(`${keyword}:${timestamp}`, nonce).toString();
          return fetch('/api/search', { headers: { 'x-sign': sig } });
        }
        """

        first = registration.detector(source)
        second = registration.detector(source)

        self.assertEqual(module.detector_invocation_count(), before + 2)
        self.assertEqual(first, second)
        self.assertEqual(first["id"], "reference_signing_crypto_marker_inventory")
        self.assertTrue(first["supported"])
        self.assertEqual(first["confidence"], "high")
        markers = {finding["marker"] for finding in first["marker_findings"]}
        self.assertTrue({"sign", "bearer-or-nonce-wording", "hmac", "webpack", "fetch"}.issubset(markers))
        self.assertEqual(first["template"], "keyword_colon_timestamp")
        self.assertEqual(first["salt"], "")
        self.assertIn("evidence_score", first)
        self.assertFalse(first["evidence_score"]["side_effect_policy"]["starts_browser"])
        self.assertFalse(first["evidence_score"]["side_effect_policy"]["calls_mcp"])

    def test_detector_reports_runtime_review_for_aes_rsa_without_collecting_context(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        strategy = module.strategy_detector_registration().detector(
            """
            function encrypt(payload) {
              const crypt = new JSEncrypt();
              return CryptoJS.AES.encrypt(payload, crypt.getPublicKey()).toString();
            }
            """
        )

        self.assertEqual(strategy["id"], "reference_crypto_marker_inventory")
        self.assertFalse(strategy["supported"])
        self.assertIn("explicit-review-crypto-parameters", strategy["runtime_context_required"])
        self.assertEqual(strategy["runtime_replay_plan"]["mode"], "not-executed")
        caveats = strategy["confidence_score"]["caveats"]
        self.assertIn("asymmetric or encryption marker requires manual review before pure rebuild", caveats)

    def test_detector_result_does_not_export_raw_source_context(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        raw_secret = "Bearer sk-live-secret-token"
        source = f"""
        const authToken = {raw_secret!r};
        const sig = CryptoJS.HmacSHA256(`/private/path?token=${{authToken}}`, authToken).toString();
        fetch('/api/private?token=' + authToken, {{ headers: {{ Authorization: authToken, 'x-sign': sig }} }});
        """

        strategy = module.strategy_detector_registration().detector(source)
        serialized = repr(strategy)

        self.assertNotIn(raw_secret, serialized)
        self.assertNotIn("/private/path?token", serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("snippet", serialized)
        self.assertTrue(strategy["marker_findings"])
        for finding in strategy["marker_findings"]:
            self.assertTrue(finding["context_redacted"])
            self.assertIn("match_span", finding)
            self.assertIn("pattern_digest_sha256", finding)
            self.assertNotIn("snippet", finding)

    def test_registry_alias_resolution_with_entry_point_registration(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        registration = module.strategy_detector_registration()

        @dataclass
        class FakeEntryPoint:
            name: str

            def load(self) -> Any:
                return module.strategy_detector_registration

        with mock.patch("reverse_deepagent.strategies.registry._entry_points_for_group", return_value=[FakeEntryPoint("reference-strategy-detector")]):
            registry = build_default_strategy_detector_registry(load_entry_points=True)

        self.assertTrue(registry.is_registered("reference-strategy-detector"))
        self.assertTrue(registry.is_registered("fixture-strategy-detector"))
        self.assertTrue(registry.is_registered("reference-detector"))
        self.assertEqual(registry.resolve("fixture-strategy-detector").provider_id, registration.provider_id)
        strategy = registry.detect("const xhr = new XMLHttpRequest(); xhr.open('GET', '/api'); xhr.send();", provider_id="reference-detector")
        self.assertEqual(strategy["id"], "reference_bundle_network_marker_inventory")
        self.assertEqual(strategy["detector_provider"]["provider_id"], "reference-strategy-detector")
        self.assertFalse(strategy["detector_provider"]["side_effect_policy"]["browser_started"])

    def test_manual_registry_registration_resolves_aliases(self) -> None:
        module = importlib.import_module("reverse_deepagent_strategy_detector_reference")
        registry = StrategyDetectorProviderRegistry()
        registry.register(module.strategy_detector_registration())

        self.assertEqual(registry.resolve("reference-detector").provider_id, "reference-strategy-detector")
        self.assertEqual(registry.resolve("fixture-strategy-detector").provider_id, "reference-strategy-detector")
        metadata = registry.list_metadata()[0]
        self.assertEqual(metadata["keys"], ["reference-strategy-detector", "fixture-strategy-detector", "reference-detector"])


if __name__ == "__main__":
    unittest.main()
