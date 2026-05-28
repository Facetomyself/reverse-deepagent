import unittest

from reverse_deepagent.strategies import detect_algorithm_strategy, list_algorithm_strategy_registry


class StrategyDetectorTests(unittest.TestCase):
    def test_registry_metadata_is_ordered_and_serializable(self) -> None:
        registry = list_algorithm_strategy_registry()
        self.assertEqual(
            [item["rule_id"] for item in registry],
            ["protected_flow_triage", "deterministic_fixture", "crypto_hash", "sig_template", "encoding"],
        )
        emitted = {strategy_id for item in registry for strategy_id in item["emits"]}
        self.assertIn("triage_wasm_module", emitted)
        self.assertIn("triage_vm_obfuscation", emitted)
        self.assertIn("triage_anti_debug_runtime", emitted)
        self.assertIn("triage_dynamic_secret", emitted)
        self.assertIn("triage_wasm_vm_obfuscation", emitted)
        self.assertIn("fixture_seed_mod100000", emitted)
        self.assertIn("md5_keyword_timestamp", emitted)
        self.assertIn("sha1_keyword_timestamp", emitted)
        self.assertIn("sha256_keyword_timestamp", emitted)
        self.assertIn("hmac_sha256_keyword_timestamp", emitted)
        self.assertIn("base64_keyword_timestamp", emitted)
        self.assertIn("urlencode_keyword_timestamp", emitted)

    def test_detects_hash_and_template_variants(self) -> None:
        cases = [
            (
                """function buildSign(keyword, timestamp) {
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}""",
                "md5_keyword_timestamp",
                "keyword_colon_timestamp",
            ),
            (
                """async function buildSign(keyword, timestamp) {
  const digest = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(`${keyword}:${timestamp}`));
  return digest;
}""",
                "sha1_keyword_timestamp",
                "keyword_colon_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  return sha256(`${keyword}${timestamp}`);
}""",
                "sha256_keyword_timestamp",
                "keyword_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return hmacSha256(`${keyword}:${timestamp}`, secret);
}""",
                "hmac_sha256_keyword_timestamp",
                "keyword_colon_timestamp",
            ),
            (
                """function buildSign(keyword, timestamp) {
  return btoa(`${keyword}:${timestamp}`);
}""",
                "base64_keyword_timestamp",
                "keyword_colon_timestamp",
            ),
        ]
        for source_context, expected_id, expected_template in cases:
            with self.subTest(expected_id=expected_id):
                strategy = detect_algorithm_strategy(source_context)
                self.assertEqual(strategy["id"], expected_id)
                self.assertEqual(strategy["template"], expected_template)
                self.assertIn("confidence", strategy)
                self.assertIn("confidence_score", strategy)
                self.assertGreater(strategy["confidence_score"]["score"], 0)
                self.assertEqual(strategy["confidence_score"]["label"], strategy["confidence"])

    def test_unsupported_strategy_is_explicit(self) -> None:
        strategy = detect_algorithm_strategy("function buildSign() { return window.someVm.run(); }")
        self.assertEqual(strategy["id"], "unsupported_manual_port_required")
        self.assertFalse(strategy["supported"])
        self.assertEqual(strategy["confidence"], "low")
        self.assertLessEqual(strategy["confidence_score"]["score"], 0.2)
        self.assertIn("manual port or runtime-backed execution required", strategy["confidence_score"]["caveats"])

    def test_confidence_score_records_caveats_for_dynamic_hmac_secret(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  return hmacSha256(`${keyword}:${timestamp}`, window.dynamicSecret);
}"""
        )
        self.assertEqual(strategy["id"], "hmac_sha256_keyword_timestamp")
        self.assertFalse(strategy["supported"])
        self.assertEqual(strategy["confidence"], "low")
        self.assertIn("secret/key is dynamic or unavailable", strategy["confidence_score"]["caveats"])

    def test_sig_template_does_not_shadow_crypto_hash_markers(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  return `sig_${CryptoJS.MD5(`${keyword}:${timestamp}`)}_${timestamp}`;
}"""
        )
        self.assertEqual(strategy["id"], "md5_keyword_timestamp")

    def test_hmac_secret_must_be_bound_to_hmac_argument(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const apiKey = 'public-key';
  return hmacSha256(`${keyword}:${timestamp}`, window.dynamicSecret);
}"""
        )
        self.assertEqual(strategy["id"], "hmac_sha256_keyword_timestamp")
        self.assertFalse(strategy["supported"])
        self.assertIn("secret/key is dynamic or unavailable", strategy["confidence_score"]["caveats"])

    def test_hmac_literal_variable_argument_is_supported(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const secret = 'fixture-secret';
  return hmacSha256(`${keyword}:${timestamp}`, secret);
}"""
        )
        self.assertEqual(strategy["id"], "hmac_sha256_keyword_timestamp")
        self.assertTrue(strategy["supported"])
        self.assertEqual(strategy["salt"], "fixture-secret")

    def test_client_ip_argument_does_not_trigger_vm_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp, ip) {
  return CryptoJS.SHA256(`${keyword}:${timestamp}:${ip}`).toString();
}"""
        )
        self.assertEqual(strategy["id"], "sha256_keyword_timestamp")

    def test_storage_nonce_hash_is_not_triage_by_name_only(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const nonce = localStorage.getItem('nonce');
  return CryptoJS.SHA256(`${keyword}:${timestamp}:${nonce}`).toString();
}"""
        )
        self.assertEqual(strategy["id"], "sha256_keyword_timestamp")

    def test_cookie_csrf_hash_is_not_triage_by_name_only(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const csrf = document.cookie.match(/csrf=([^;]+)/)?.[1];
  return CryptoJS.SHA256(`${keyword}:${timestamp}:${csrf}`).toString();
}"""
        )
        self.assertEqual(strategy["id"], "sha256_keyword_timestamp")

    def test_wasm_only_triggers_wasm_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """async function buildSign(keyword, timestamp) {
  const wasm = await WebAssembly.instantiateStreaming(fetch('/sign.wasm'), {});
  return wasm.instance.exports.sign(keyword, timestamp);
}"""
        )
        self.assertEqual(strategy["id"], "triage_wasm_module")
        self.assertEqual(strategy["triage"]["categories"], ["wasm"])
        self.assertIn("wasm-module", strategy["runtime_context_required"])

    def test_vm_only_triggers_vm_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  const opcode = bytecode[instructionPointer++];
  switch (opcode) {
    case 7:
      return dispatchTable[opcode](keyword, timestamp);
  }
}"""
        )
        self.assertEqual(strategy["id"], "triage_vm_obfuscation")
        self.assertIn("vm", strategy["triage"]["categories"])

    def test_anti_debug_only_triggers_runtime_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  debugger;
  return CryptoJS.MD5(`${keyword}:${timestamp}`).toString();
}"""
        )
        self.assertEqual(strategy["id"], "triage_anti_debug_runtime")
        self.assertIn("anti_debug", strategy["triage"]["categories"])

    def test_strong_dynamic_secret_triggers_dynamic_secret_triage(self) -> None:
        strategy = detect_algorithm_strategy(
            """function buildSign(keyword, timestamp) {
  return signWithChallenge(keyword, timestamp, window.__challenge);
}"""
        )
        self.assertEqual(strategy["id"], "triage_dynamic_secret")
        self.assertIn("dynamic_secret", strategy["triage"]["categories"])


if __name__ == "__main__":
    unittest.main()
