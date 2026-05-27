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
            "sha256": "SHA-256",
            "base64": "btoa",
            "context-localstorage": "localStorage",
            "context-cookie": "document.cookie",
            "context-navigator": "navigator.userAgent",
        }
        for profile, marker in expectations.items():
            fixture = start_fixture_server(profile=profile)
            try:
                with urlopen(f"{fixture.base_url}/healthz", timeout=5) as response:  # nosec B310 - local fixture only
                    health = json.loads(response.read().decode("utf-8"))
                self.assertEqual(health["profile"], profile)
                with urlopen(f"{fixture.base_url}/app.js", timeout=5) as response:  # nosec B310 - local fixture only
                    app_js = response.read().decode("utf-8")
                self.assertIn(marker, app_js)
                self.assertIn("async function search", app_js)
            finally:
                fixture.close()


if __name__ == "__main__":
    unittest.main()
