import json
import subprocess
import sys
import unittest
from pathlib import Path

from reverse_deepagent.browser_provider_smoke_policy import browser_provider_smoke_policy_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "browser-provider-smoke"
METADATA_ONLY_FIXTURE = FIXTURE_ROOT / "cloakbrowser-metadata-only.json"
LAUNCH_SMOKE_FIXTURE = FIXTURE_ROOT / "cloakbrowser-launch-smoke.json"


class BrowserProviderSmokePolicyGateTests(unittest.TestCase):
    def _load_fixture(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_fixture_contract_is_redacted_and_side_effect_explicit(self) -> None:
        for path in (METADATA_ONLY_FIXTURE, LAUNCH_SMOKE_FIXTURE):
            with self.subTest(path=path.name):
                payload = self._load_fixture(path)
                dumped = json.dumps(payload, ensure_ascii=False)
                self.assertEqual(payload["schema_version"], "reverse-deepagent.browser-provider-smoke.v1")
                self.assertEqual(payload["requested_provider_id"], "cloakbrowser")
                self.assertEqual(payload["resolved_provider_id"], "cloakbrowser")
                self.assertTrue(payload["ok"])
                self.assertNotIn("user:pass", dumped)
                self.assertNotIn("Authorization", dumped)
                self.assertNotIn("Bearer ", dumped)
                self.assertNotIn("/Users/", dumped)
                side_effect_policy = payload["side_effect_policy"]
                self.assertFalse(side_effect_policy["calls_mcp"])
                self.assertFalse(side_effect_policy["touches_mobile_full_runtime_chains"])

        metadata_payload = self._load_fixture(METADATA_ONLY_FIXTURE)
        self.assertEqual(metadata_payload["mode"], "metadata-only")
        self.assertFalse(metadata_payload["side_effect_policy"]["provider_factories_invoked"])
        self.assertFalse(metadata_payload["side_effect_policy"]["starts_browser"])
        self.assertFalse(metadata_payload["side_effect_policy"]["launch_smoke_requested"])

        launch_payload = self._load_fixture(LAUNCH_SMOKE_FIXTURE)
        self.assertEqual(launch_payload["mode"], "launch-smoke")
        self.assertTrue(launch_payload["side_effect_policy"]["provider_factories_invoked"])
        self.assertTrue(launch_payload["side_effect_policy"]["starts_browser"])
        self.assertTrue(launch_payload["side_effect_policy"]["launch_smoke_requested"])
        self.assertEqual(launch_payload["provider"]["smoke"]["status"], "passed")

    def test_policy_gate_blocks_metadata_only_fixture_by_default_without_side_effects(self) -> None:
        payload = browser_provider_smoke_policy_gate(
            smoke_json_path=METADATA_ONLY_FIXTURE,
            expected_provider_id="cloakbrowser",
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["schema_version"], "reverse-deepagent.browser-provider-smoke-policy-gate.v1")
        self.assertEqual(payload["minimum_evidence_level"], "launch-smoke")
        self.assertEqual(payload["policy_decision"]["decision"], "block")
        self.assertFalse(payload["policy_decision"]["policy_passed"])
        self.assertEqual(payload["policy_decision"]["observed_evidence_level"], "metadata-only")
        self.assertIn("insufficient_browser_provider_smoke_evidence_level", payload["policy_decision"]["blockers"])
        self.assertFalse(payload["attachment_acceptance"]["runtime_launch_smoke_accepted"])
        self.assertFalse(payload["side_effect_policy"]["writes_artifact"])
        self.assertFalse(payload["side_effect_policy"]["provider_registry_resolved"])
        self.assertFalse(payload["side_effect_policy"]["provider_factories_invoked"])
        self.assertFalse(payload["side_effect_policy"]["starts_browser"])
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["touches_mobile_full_runtime_chains"])

    def test_policy_gate_passes_matching_launch_smoke_fixture(self) -> None:
        payload = browser_provider_smoke_policy_gate(
            smoke_json_path=LAUNCH_SMOKE_FIXTURE,
            expected_provider_id="cloakbrowser",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["policy_decision"]["decision"], "pass")
        self.assertTrue(payload["policy_decision"]["policy_passed"])
        self.assertTrue(payload["attachment_acceptance"]["runtime_launch_smoke_accepted"])
        self.assertEqual(payload["ci_gate"]["observed_evidence_level"], "launch-smoke")
        self.assertFalse(payload["side_effect_policy"]["starts_browser"])

    def test_module_cli_returns_nonzero_for_policy_block_fixture(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "reverse_deepagent.browser_provider_smoke_policy",
                "--smoke-json",
                str(METADATA_ONLY_FIXTURE),
                "--expected-provider",
                "cloakbrowser",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["policy_decision"]["decision"], "block")
        self.assertIn("insufficient_browser_provider_smoke_evidence_level", payload["policy_decision"]["blockers"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
