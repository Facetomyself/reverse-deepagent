import importlib
import sys
import unittest
from pathlib import Path


class StrategyDetectorPluginTemplateTests(unittest.TestCase):
    def test_template_registration_is_metadata_only_and_detector_is_explicit(self) -> None:
        package_src = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-strategy-detector-template" / "src"
        sys.path.insert(0, str(package_src))
        try:
            module = importlib.import_module("reverse_deepagent_strategy_detector_template")
            before = module.detector_invocation_count()

            registration = module.strategy_detector_registration()
            metadata = registration.to_metadata()

            self.assertEqual(module.detector_invocation_count(), before)
            self.assertEqual(metadata["provider_id"], "template-strategy-detector")
            self.assertEqual(metadata["rules"][0]["rule_id"], "template_literal_strategy_rule")
            self.assertTrue(metadata["side_effect_policy"]["metadata_only"])
            self.assertFalse(metadata["side_effect_policy"]["browser_started"])
            self.assertFalse(metadata["side_effect_policy"]["calls_mcp"])
            self.assertFalse(metadata["side_effect_policy"]["mobile_runtime_used"])

            strategy = registration.detector("function sign(){/* TEMPLATE_SIGN_STRATEGY */}")

            self.assertEqual(module.detector_invocation_count(), before + 1)
            self.assertEqual(strategy["id"], "template_literal_strategy")
            self.assertTrue(strategy["supported"])
            self.assertIn("evidence_score", strategy)
        finally:
            try:
                sys.path.remove(str(package_src))
            except ValueError:
                pass

    def test_template_declares_strategy_detector_entry_point(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-strategy-detector-template" / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")

        self.assertIn('[project.entry-points."reverse_deepagent.strategy_detectors"]', text)
        self.assertIn("template-strategy-detector", text)


if __name__ == "__main__":
    unittest.main()
