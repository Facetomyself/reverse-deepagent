import unittest

from reverse_deepagent.browser.redaction import (
    REDACTED_VALUE,
    is_sensitive_key,
    redact_cookie_header,
    redact_header_value,
    redact_mapping,
)


class BrowserRedactionTests(unittest.TestCase):
    def assert_raw_secrets_absent(self, result, *raw_values: str) -> None:
        rendered = str(result)
        for raw_value in raw_values:
            self.assertNotIn(raw_value, rendered)

    def test_sensitive_key_matcher_is_case_insensitive_and_separator_tolerant(self) -> None:
        sensitive_keys = [
            "token",
            "AUTH_TOKEN",
            "secret",
            "password",
            "passwd",
            "cookie",
            "Authorization",
            "Proxy-Authorization",
            "Set-Cookie",
            "apikey",
            "api_key",
            "X-API-Key",
            "credential",
            "csrf_token",
            "session-id",
            "bearer",
        ]
        for key in sensitive_keys:
            with self.subTest(key=key):
                self.assertTrue(is_sensitive_key(key))

        self.assertFalse(is_sensitive_key("content-type"))
        self.assertFalse(is_sensitive_key("x-request-id"))

    def test_authorization_header_redacts_value_but_preserves_scheme(self) -> None:
        result = redact_header_value("Authorization", "Bearer super-secret-token")

        self.assertEqual(result, f"Bearer {REDACTED_VALUE}")
        self.assert_raw_secrets_absent(result, "super-secret-token")

    def test_proxy_authorization_header_redacts_value_but_preserves_scheme(self) -> None:
        result = redact_header_value("Proxy-Authorization", "Basic raw-proxy-password")

        self.assertEqual(result, f"Basic {REDACTED_VALUE}")
        self.assert_raw_secrets_absent(result, "raw-proxy-password")

    def test_cookie_header_preserves_cookie_names_not_values(self) -> None:
        result = redact_cookie_header("sid=raw-session; csrf=raw-csrf; theme=dark; Secure")

        self.assertIn("sid=", result)
        self.assertIn("csrf=", result)
        self.assertIn("theme=", result)
        self.assertIn("Secure", result)
        self.assert_raw_secrets_absent(result, "raw-session", "raw-csrf", "dark")

    def test_redact_mapping_keeps_header_names_and_non_sensitive_values(self) -> None:
        headers = {
            "Authorization": "Bearer super-secret-token",
            "Cookie": "sid=raw-session; csrf=raw-csrf",
            "Set-Cookie": "sid=raw-set-cookie; Path=/; HttpOnly",
            "Proxy-Authorization": "Basic raw-proxy-password",
            "X-API-Key": "raw-api-key",
            "content-type": "application/json",
            "x-request-id": "request-123",
        }

        result = redact_mapping(headers)

        self.assertEqual(result["Authorization"], f"Bearer {REDACTED_VALUE}")
        self.assertEqual(result["Proxy-Authorization"], f"Basic {REDACTED_VALUE}")
        self.assertIn("sid=", result["Cookie"])
        self.assertIn("csrf=", result["Cookie"])
        self.assertIn("sid=", result["Set-Cookie"])
        self.assertEqual(result["X-API-Key"], REDACTED_VALUE)
        self.assertEqual(result["content-type"], "application/json")
        self.assertEqual(result["x-request-id"], "request-123")
        self.assert_raw_secrets_absent(
            result,
            "super-secret-token",
            "raw-session",
            "raw-csrf",
            "raw-set-cookie",
            "raw-proxy-password",
            "raw-api-key",
        )

    def test_redact_mapping_recurses_for_nested_non_sensitive_containers(self) -> None:
        storage = {
            "localStorage": {
                "theme": "dark",
                "auth_token": "raw-local-token",
                "csrfToken": "raw-csrf-token",
            },
            "sessionStorage": {
                "nonce": "visible-nonce",
                "session_id": "raw-browser-session-id",
            },
            "metadata": {"session_id": "raw-session-id", "safe": "visible"},
        }

        result = redact_mapping(storage)

        self.assertEqual(result["localStorage"]["theme"], "dark")
        self.assertEqual(result["localStorage"]["auth_token"], REDACTED_VALUE)
        self.assertEqual(result["localStorage"]["csrfToken"], REDACTED_VALUE)
        self.assertEqual(result["sessionStorage"]["nonce"], "visible-nonce")
        self.assertEqual(result["sessionStorage"]["session_id"], REDACTED_VALUE)
        self.assertEqual(result["metadata"]["session_id"], REDACTED_VALUE)
        self.assertEqual(result["metadata"]["safe"], "visible")
        self.assert_raw_secrets_absent(
            result,
            "raw-local-token",
            "raw-csrf-token",
            "raw-browser-session-id",
            "raw-session-id",
        )

    def test_non_sensitive_header_value_is_returned_unchanged(self) -> None:
        self.assertEqual(redact_header_value("content-type", "application/json"), "application/json")


if __name__ == "__main__":
    unittest.main()
