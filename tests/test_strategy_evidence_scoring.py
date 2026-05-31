import unittest

from reverse_deepagent.strategies import build_strategy_evidence_score, detect_algorithm_strategy


class StrategyEvidenceScoringTests(unittest.TestCase):
    def test_supported_validated_pure_strategy_is_strong_candidate(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        )
        score = build_strategy_evidence_score(
            strategy,
            extraction={"pure_extractable": True, "context_aware_extractable": False, "manual_port_required": False},
            validation={
                "validation_status": "success",
                "checks": {"source_complete": True, "runtime_invocation_ok": True, "sign_shape_ok": True},
                "replay_result": {"ok": True},
            },
            validation_ready=True,
            replay_url="https://example.test/api/search",
            ready=True,
        )
        self.assertEqual(score["label"], "strong_pure_candidate")
        self.assertGreaterEqual(score["score"], 0.78)
        self.assertIn("strategy_supported", score["signals"])
        self.assertIn("pure_extractable", score["signals"])
        self.assertEqual(score["blockers"], [])
        self.assertEqual(score["recommended_next_action"], "review_generated_pure_rebuild_and_prepare_delivery")
        self.assertTrue(score["side_effect_policy"]["score_only"])
        self.assertFalse(score["side_effect_policy"]["changes_ready_calculation"])

    def test_runtime_context_drift_lowers_context_aware_score(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  return btoa(`${keyword}:${timestamp}:${nonce}`);
}"""
        )
        runtime_context_diff = {
            "status": "analyzed",
            "sample_count": 2,
            "missing_requirements": ["localStorage"],
            "fields": [
                {"path": "localStorage.nonce", "classification": "volatile"},
                {"path": "localStorage.feature", "classification": "missing_in_some_samples"},
                {"path": "localStorage.counter", "classification": "type_drift"},
            ],
            "summary": {
                "volatile_field_count": 1,
                "missing_field_count": 1,
                "missing_requirement_count": 1,
                "type_drift_field_count": 1,
            },
        }
        score = build_strategy_evidence_score(
            strategy,
            extraction={
                "pure_extractable": False,
                "context_aware_extractable": True,
                "manual_port_required": False,
                "runtime_context_binding_required": True,
                "runtime_context_required": ["localStorage"],
                "captured_runtime_context": ["localStorage"],
            },
            runtime_context_diff=runtime_context_diff,
            validation_ready=True,
            replay_url="https://example.test/api/search",
            ready=True,
        )
        self.assertEqual(score["label"], "needs_more_evidence")
        self.assertIn("volatile_runtime_context", score["blockers"])
        self.assertIn("missing_runtime_context", score["blockers"])
        self.assertIn("runtime_context_type_drift", score["blockers"])
        self.assertEqual(score["recommended_next_action"], "collect_required_runtime_context_samples")
        self.assertEqual(score["components"]["runtime_context"]["volatile_field_count"], 1)
        self.assertEqual(score["components"]["runtime_context"]["missing_requirement_count"], 1)

    def test_protected_flow_score_requires_runtime_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """async function buildSign(keyword, timestamp) {
  debugger;
  const wasm = await WebAssembly.instantiateStreaming(fetch('/sign.wasm'), {});
  const opcode = wasm.instance.exports.opcode_for('sign');
  switch (opcode) { case 7: return wasm.instance.exports.sign(keyword, timestamp); }
}"""
        )
        score = build_strategy_evidence_score(
            strategy,
            extraction={"pure_extractable": False, "context_aware_extractable": False, "manual_port_required": True},
            validation_ready=True,
            replay_url="https://example.test/api/search",
            ready=False,
        )
        self.assertEqual(score["label"], "runtime_assisted_required")
        self.assertIn("protected_flow_triage_required", score["blockers"])
        self.assertIn("manual_port_required", score["blockers"])
        self.assertIn("protected_flow:wasm", score["signals"])
        self.assertIn("protected_flow:anti_debug", score["signals"])
        self.assertEqual(score["recommended_next_action"], "run_reviewed_runtime_triage_hooks_before_porting")
        self.assertTrue(score["components"]["protected_flow"]["triage"])
        self.assertGreater(score["components"]["protected_flow"]["hook_plan_count"], 0)


if __name__ == "__main__":
    unittest.main()
