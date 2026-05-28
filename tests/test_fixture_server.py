import json
import unittest
from urllib.request import Request, urlopen

from reverse_deepagent.fixtures.web_sign import start_fixture_server


class FixtureServerTests(unittest.TestCase):
    def test_fixture_serves_page_js_health_and_api(self) -> None:
        fixture = start_fixture_server()
        try:
            with urlopen(f"{fixture.base_url}/healthz", timeout=5) as response:  # nosec B310 - local fixture only
                health = json.loads(response.read().decode("utf-8"))
            self.assertTrue(health["ok"])
            self.assertIn("profile_metadata", health)

            with urlopen(f"{fixture.base_url}/app.js", timeout=5) as response:  # nosec B310 - local fixture only
                app_js = response.read().decode("utf-8")
            self.assertIn("function buildSign", app_js)
            self.assertIn("x-sign", app_js)

            request = Request(
                f"{fixture.base_url}/api/search?keyword=sign&t=1",
                data=json.dumps({"keyword": "sign", "sign": "sig_test"}).encode("utf-8"),
                headers={"content-type": "application/json", "x-sign": "sig_test"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:  # nosec B310 - local fixture only
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["keyword"], "sign")
            self.assertEqual(payload["headers"]["x-sign"], "sig_test")
        finally:
            fixture.close()

    def test_fixture_profiles_expose_strategy_markers(self) -> None:
        expectations = {
            "md5": "function md5",
            "sha1": "SHA-1",
            "sha256": "SHA-256",
            "base64": "btoa",
            "context-localstorage": "localStorage",
            "context-cookie": "document.cookie",
            "context-navigator": "navigator.userAgent",
            "webpack-minified": "__webpack_require__",
            "token-chain": "/api/bootstrap",
            "hybrid-context": "csrf_token",
        }
        expected_strategies = {
            "md5": "md5_keyword_timestamp",
            "sha1": "sha1_keyword_timestamp",
            "sha256": "sha256_keyword_timestamp",
            "base64": "base64_keyword_timestamp",
            "context-localstorage": "base64_keyword_timestamp",
            "context-cookie": "base64_keyword_timestamp",
            "context-navigator": "sha256_keyword_timestamp",
            "webpack-minified": "sha256_keyword_timestamp",
            "token-chain": "sha256_keyword_timestamp",
            "hybrid-context": "base64_keyword_timestamp",
        }
        for profile, marker in expectations.items():
            fixture = start_fixture_server(profile=profile)
            try:
                with urlopen(f"{fixture.base_url}/healthz", timeout=5) as response:  # nosec B310 - local fixture only
                    health = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["profile"], profile)
                self.assertEqual(health["profile_metadata"]["expected_strategy"], expected_strategies[profile])
                with urlopen(f"{fixture.base_url}/app.js", timeout=5) as response:  # nosec B310 - local fixture only
                    app_js = response.read().decode("utf-8")
                self.assertIn(marker, app_js)
                self.assertIn("async function search", app_js)
            finally:
                fixture.close()

    def test_token_chain_profile_exposes_bootstrap_endpoint(self) -> None:
        fixture = start_fixture_server(profile="token-chain")
        try:
            with urlopen(f"{fixture.base_url}/api/bootstrap?keyword=sign", timeout=5) as response:  # nosec B310 - local fixture only
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["profile"], "token-chain")
            self.assertEqual(payload["token"], "fixture-token")
            self.assertEqual(payload["keyword"], "sign")
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
