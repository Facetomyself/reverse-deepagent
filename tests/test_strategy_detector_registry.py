import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from reverse_deepagent.strategies import (
    AlgorithmStrategyRule,
    StrategyDetectorProviderRegistration,
    StrategyDetectorProviderRegistry,
    StrategyDetectorRegistryError,
    build_default_strategy_detector_registry,
    detect_with_strategy_detector_registry,
    list_strategy_detector_provider_registry,
)


class StrategyDetectorProviderRegistryTests(unittest.TestCase):
    def test_default_registry_exposes_builtin_metadata_without_detection_side_effects(self) -> None:
        registry = build_default_strategy_detector_registry(load_entry_points=False)

        metadata = registry.list_metadata()

        self.assertEqual([item["provider_id"] for item in metadata], ["builtin-algorithm-strategy"])
        provider = metadata[0]
        self.assertEqual(provider["rule_count"], 5)
        self.assertEqual([rule["rule_id"] for rule in provider["rules"]], ["protected_flow_triage", "deterministic_fixture", "crypto_hash", "sig_template", "encoding"])
        self.assertIn("sha256_keyword_timestamp", provider["emits"])
        self.assertTrue(provider["side_effect_policy"]["metadata_only"])
        self.assertFalse(provider["side_effect_policy"]["browser_started"])
        self.assertFalse(provider["side_effect_policy"]["calls_mcp"])
        self.assertFalse(provider["side_effect_policy"]["mobile_runtime_used"])

    def test_default_registry_detection_preserves_builtin_strategy_behavior(self) -> None:
        strategy = detect_with_strategy_detector_registry("return CryptoJS.SHA256(`${keyword}:${timestamp}`).toString();", registry=build_default_strategy_detector_registry(load_entry_points=False))

        self.assertEqual(strategy["id"], "sha256_keyword_timestamp")
        self.assertTrue(strategy["supported"])
        self.assertEqual(strategy["detector_provider"]["provider_id"], "builtin-algorithm-strategy")
        self.assertFalse(strategy["detector_provider"]["side_effect_policy"]["browser_started"])

    def test_registry_loads_entry_point_registration_without_running_detector(self) -> None:
        calls = {"detector": 0}

        def plugin_detector(source: str) -> dict[str, Any]:
            calls["detector"] += 1
            return {
                "id": "plugin_literal_sign",
                "supported": True,
                "confidence": "medium",
                "description": "plugin detector",
                "dependencies": ["python-stdlib"],
                "template": "keyword_colon_timestamp",
                "salt": "",
                "confidence_reason": "test plugin matched",
                "confidence_score": {"score": 0.65, "label": "medium", "positive_markers": ["plugin"], "caveats": []},
                "evidence_score": {"score": 0.7, "label": "reviewable_candidate", "signals": ["plugin"], "blockers": [], "side_effect_policy": {"score_only": True}},
            }

        registration = StrategyDetectorProviderRegistration(
            provider_id="plugin-strategy",
            display_name="Plugin Strategy Detector",
            aliases=("plugin",),
            rules=(AlgorithmStrategyRule("plugin_rule", ("plugin_literal_sign",), lambda source: None, "test plugin rule"),),
            detector=plugin_detector,
            description="test plugin",
            metadata={"target_platforms": ["web"], "plugin_kind": "test"},
        )

        @dataclass
        class FakeEntryPoint:
            name: str

            def load(self) -> Any:
                return lambda: registration

        with mock.patch("reverse_deepagent.strategies.registry._entry_points_for_group", return_value=[FakeEntryPoint("plugin-strategy")]):
            registry = build_default_strategy_detector_registry(load_entry_points=True)

        self.assertEqual(calls["detector"], 0)
        self.assertTrue(registry.is_registered("plugin"))
        metadata = {item["provider_id"]: item for item in registry.list_metadata()}
        self.assertIn("plugin-strategy", metadata)
        self.assertEqual(metadata["plugin-strategy"]["rules"][0]["rule_id"], "plugin_rule")

        strategy = registry.detect("plugin sign", provider_id="plugin")

        self.assertEqual(calls["detector"], 1)
        self.assertEqual(strategy["id"], "plugin_literal_sign")
        self.assertEqual(strategy["detector_provider"]["provider_id"], "plugin-strategy")

    def test_provider_registration_rejects_secret_like_metadata(self) -> None:
        with self.assertRaises(StrategyDetectorRegistryError):
            StrategyDetectorProviderRegistration(
                provider_id="bad-provider",
                display_name="Bad Provider",
                rules=(AlgorithmStrategyRule("bad", ("bad",), lambda source: None, "bad"),),
                detector=lambda source: {"id": "bad"},
                metadata={"api_key": "raw-secret"},
            )

    def test_public_metadata_helper_uses_side_effect_free_default_registry(self) -> None:
        metadata = list_strategy_detector_provider_registry(load_entry_points=False)

        self.assertEqual(metadata[0]["provider_id"], "builtin-algorithm-strategy")
        self.assertTrue(metadata[0]["side_effect_policy"]["read_only"])


if __name__ == "__main__":
    unittest.main()
