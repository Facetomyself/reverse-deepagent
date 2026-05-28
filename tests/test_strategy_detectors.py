import unittest

from reverse_deepagent.strategies import detect_algorithm_strategy, list_algorithm_strategy_registry


class StrategyDetectorTests(unittest.TestCase):
    def test_registry_metadata_is_ordered_and_serializable(self) -> None:
        registry = list_algorithm_strategy_registry()
        self.assertEqual([item["rule_id"] for item in registry], ["deterministic_fixture", "sig_template", "crypto_hash", "encoding"])
        emitted = {strategy_id for item in registry for strategy_id in item["emits"]}
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

    def test_unsupported_strategy_is_explicit(self) -> None:
        strategy = detect_algorithm_strategy("function buildSign() { return window.someVm.run(); }")
        self.assertEqual(strategy["id"], "unsupported_manual_port_required")
        self.assertFalse(strategy["supported"])
        self.assertEqual(strategy["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
