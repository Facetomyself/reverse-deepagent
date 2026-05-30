import sys
import unittest
from pathlib import Path

from reverse_deepagent.adapters.jsreverser import JSReverserRuntime


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "packages" / "reverse-deepagent-legacy-mcp" / "src"


def load_legacy_mcp_plugin():
    sys.path.insert(0, str(PACKAGE_SRC))
    try:
        sys.modules.pop("reverse_deepagent_legacy_mcp", None)
        import reverse_deepagent_legacy_mcp as plugin
        return plugin
    finally:
        if str(PACKAGE_SRC) in sys.path:
            sys.path.remove(str(PACKAGE_SRC))


class FakeBridge:
    def invoke(self, tool_name: str, params: dict):
        if tool_name == "check_browser_health":
            return {"content": [{"type": "text", "text": "Failed to connect to remote browser: fetch failed"}], "text": "Failed to connect to remote browser: fetch failed"}
        if tool_name == "list_pages":
            return {"pages": []}
        raise AssertionError(tool_name)


class MarkdownBridge:
    def invoke(self, tool_name: str, params: dict):
        if tool_name == "check_browser_health":
            return {
                "content": [
                    {"type": "text", "text": "{\n  \"traceId\": \"check_browser_health_123\"\n}"},
                    {
                        "type": "text",
                        "text": "# check_browser_health response\n```json\n{\n  \"healthy\": false,\n  \"connected\": false\n}\n```",
                    },
                ],
                "text": "{\n  \"traceId\": \"check_browser_health_123\"\n}\n# check_browser_health response\n```json\n{\n  \"healthy\": false,\n  \"connected\": false\n}\n```",
            }
        if tool_name == "list_pages":
            return {
                "content": [
                    {"type": "text", "text": "{\n  \"traceId\": \"list_pages_456\"\n}"},
                    {"type": "text", "text": "# list_pages response\n## Pages\n0: about:blank [selected]"},
                ],
                "text": "{\n  \"traceId\": \"list_pages_456\"\n}\n# list_pages response\n## Pages\n0: about:blank [selected]",
            }
        raise AssertionError(tool_name)


class RealReturnShapeTests(unittest.TestCase):
    def test_failed_browser_health_text_is_not_healthy(self) -> None:
        runtime = JSReverserRuntime(bridge=FakeBridge())
        browser = runtime.ensure_browser_session()
        self.assertFalse(browser.healthy)
        self.assertEqual(browser.page_count, 0)

    def test_markdown_list_pages_are_parsed_into_browser_session(self) -> None:
        runtime = JSReverserRuntime(bridge=MarkdownBridge())
        browser = runtime.ensure_browser_session()
        self.assertTrue(browser.healthy)
        self.assertEqual(browser.page_count, 1)
        self.assertEqual(browser.selected_page_idx, 0)
        self.assertEqual(browser.active_url, "about:blank")

    def test_real_runtime_factory_uses_stdio_bridge(self) -> None:
        runtime = load_legacy_mcp_plugin().create_jsreverser_mcp_runtime(request_timeout=1, startup_timeout=1)
        self.assertIsInstance(runtime, JSReverserRuntime)

    def test_markdown_network_requests_are_parsed(self) -> None:
        payload = {
            "text": "# network_request response\n"
            "## Network requests\n"
            "reqid=1 GET http://127.0.0.1:54628/ [success - 200]\n"
            "reqid=5 POST http://127.0.0.1:54628/api/search?keyword=sign&t=1 [success - 200]"
        }
        items = JSReverserRuntime._extract_request_items(payload)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[1]["method"], "POST")
        self.assertIn("/api/search", items[1]["url"])

    def test_markdown_source_hits_are_parsed(self) -> None:
        payload = {
            "text": '# search_in_sources response\nFound 2 match(es) for "sign":\n\n'
            "[5] http://127.0.0.1:54628/app.js:4\n"
            "  function buildSign(keyword, timestamp) {\n\n"
            "[5] http://127.0.0.1:54628/app.js:23\n"
            "  'x-sign': sign,\n"
        }
        hits = JSReverserRuntime._extract_source_hits(payload)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["lineNumber"], 4)
        self.assertIn("buildSign", hits[0]["preview"])


if __name__ == "__main__":
    unittest.main()
