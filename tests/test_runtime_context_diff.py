from __future__ import annotations

import json
import unittest

from reverse_deepagent.strategies import RuntimeContextSample, diff_runtime_context_payload, diff_runtime_context_samples


class RuntimeContextDiffTests(unittest.TestCase):
    def test_classifies_stable_and_volatile_fields(self) -> None:
        result = diff_runtime_context_samples(
            [
                RuntimeContextSample(
                    sample_id="0",
                    context={
                        "localStorage": {"device_id": "fixture-device", "nonce": "n1"},
                        "navigator": {"userAgent": "FixtureBrowser/13.0"},
                        "timezoneOffset": -480,
                        "sample_index": 0,
                        "collected_at_ms": 1000,
                    },
                ),
                RuntimeContextSample(
                    sample_id="1",
                    context={
                        "localStorage": {"device_id": "fixture-device", "nonce": "n2"},
                        "navigator": {"userAgent": "FixtureBrowser/13.0"},
                        "timezoneOffset": -480,
                        "sample_index": 1,
                        "collected_at_ms": 1050,
                    },
                ),
            ],
            requirements=["localStorage", "navigator"],
            captured_requirements=["localStorage", "navigator"],
        )

        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["legacy_status"], "multi_sample")
        self.assertFalse(result["stable"])
        self.assertIn("localStorage.device_id", result["stable_keys"])
        self.assertIn("navigator.userAgent", result["stable_keys"])
        self.assertIn("timezoneOffset", result["stable_keys"])
        self.assertIn("localStorage.nonce", result["volatile_keys"])
        self.assertNotIn("sample_index", result["volatile_keys"])
        self.assertNotIn("collected_at_ms", result["volatile_keys"])
        by_path = {field["path"]: field for field in result["fields"]}
        self.assertEqual(by_path["localStorage.nonce"]["classification"], "volatile")
        self.assertEqual(by_path["localStorage.device_id"]["classification"], "stable")
        self.assertIn("runtime_context_volatile_fields_detected", result["review_hints"])

    def test_session_bound_secret_like_values_are_redacted(self) -> None:
        result = diff_runtime_context_samples(
            [
                {"sessionStorage": {"csrf_token": "fixture-redacted-value"}, "cookies": {"sid": "fixture-cookie-value"}},
                {"sessionStorage": {"csrf_token": "fixture-redacted-value"}, "cookies": {"sid": "fixture-cookie-value"}},
            ]
        )

        by_path = {field["path"]: field for field in result["fields"]}
        csrf = by_path["sessionStorage.csrf_token"]
        cookie = by_path["cookies.sid"]
        self.assertEqual(csrf["classification"], "session_bound")
        self.assertEqual(cookie["classification"], "session_bound")
        self.assertIn("sessionStorage.csrf_token", result["stable_keys"])
        self.assertTrue(csrf["value_preview"][0]["redacted"])
        self.assertTrue(cookie["value_preview"][0]["redacted"])
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("fixture-redacted-value", serialized)
        self.assertNotIn("fixture-cookie-value", serialized)
        self.assertIn("runtime_context_session_bound_fields_detected", result["review_hints"])
        self.assertIn("runtime_context_secret_like_values_redacted", result["review_hints"])

    def test_volatile_secret_like_changes_are_redacted(self) -> None:
        result = diff_runtime_context_samples(
            [
                {"localStorage": {"auth_token": "fixture-redacted-a"}},
                {"localStorage": {"auth_token": "fixture-redacted-b"}},
            ]
        )

        by_path = {field["path"]: field for field in result["fields"]}
        token = by_path["localStorage.auth_token"]
        self.assertEqual(token["classification"], "volatile")
        self.assertTrue(token["value_preview"][0]["redacted"])
        self.assertTrue(result["changes"]["localStorage.auth_token"][0]["redacted"])
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        self.assertNotIn("fixture-redacted-a", serialized)
        self.assertNotIn("fixture-redacted-b", serialized)

    def test_missing_and_type_drift_are_reported_separately(self) -> None:
        result = diff_runtime_context_samples(
            [
                {"localStorage": {"feature_flag": "on", "counter": "1"}},
                {"localStorage": {"counter": 1}},
            ]
        )

        by_path = {field["path"]: field for field in result["fields"]}
        self.assertEqual(by_path["localStorage.feature_flag"]["classification"], "missing_in_some_samples")
        self.assertEqual(by_path["localStorage.feature_flag"]["missing_count"], 1)
        self.assertEqual(by_path["localStorage.counter"]["classification"], "type_drift")
        self.assertIn("localStorage.feature_flag", result["volatile_keys"])
        self.assertIn("localStorage.counter", result["volatile_keys"])
        self.assertIn("runtime_context_missing_fields_detected", result["review_hints"])
        self.assertIn("runtime_context_type_drift_detected", result["review_hints"])

    def test_object_drift_reports_shape_without_exploding_arrays(self) -> None:
        result = diff_runtime_context_samples(
            [
                {"navigator": {"plugins": ["a", "b"]}},
                {"navigator": {"plugins": ["a", "c"]}},
            ]
        )

        by_path = {field["path"]: field for field in result["fields"]}
        plugins = by_path["navigator.plugins"]
        self.assertEqual(plugins["classification"], "object_drift")
        self.assertEqual(plugins["value_preview"][0]["shape"], {"length": 2, "item_types": ["str"]})
        self.assertIn("runtime_context_object_drift_detected", result["review_hints"])

    def test_payload_helper_preserves_legacy_fields(self) -> None:
        payload = {
            "detected_requirements": ["localStorage", "navigator"],
            "captured_requirements": ["localStorage", "navigator"],
            "samples": [
                {"localStorage": {"device_id": "fixture-device", "nonce": "n1"}, "navigator": {"userAgent": "FixtureBrowser/13.0"}},
                {"localStorage": {"device_id": "fixture-device", "nonce": "n2"}, "navigator": {"userAgent": "FixtureBrowser/13.0"}},
            ],
        }

        result = diff_runtime_context_payload(payload)

        self.assertEqual(result["status"], "analyzed")
        self.assertEqual(result["legacy_status"], "multi_sample")
        self.assertEqual(result["sample_count"], 2)
        self.assertIn("localStorage.device_id", result["stable_keys"])
        self.assertIn("localStorage.nonce", result["volatile_keys"])
        self.assertEqual(result["changes"]["localStorage.nonce"], ["n1", "n2"])
        json.dumps(result, ensure_ascii=False, sort_keys=True)

    def test_empty_input_returns_insufficient_samples(self) -> None:
        result = diff_runtime_context_samples([])

        self.assertEqual(result["status"], "insufficient_samples")
        self.assertEqual(result["sample_count"], 0)
        self.assertIn("runtime_context_missing_samples", result["review_hints"])


if __name__ == "__main__":
    unittest.main()
