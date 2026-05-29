import unittest

from reverse_deepagent.browser.hooks import BreakpointManager, BreakpointSpec


class RecordingCDPSession:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.calls = []
        self.payload = payload or {"breakpointId": "bp-1", "locations": [{"scriptId": "script-1", "lineNumber": 3, "columnNumber": 0}]}
        self.error = error

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if self.error is not None and method == "Debugger.setBreakpointByUrl":
            raise self.error
        if method == "Debugger.setBreakpointByUrl":
            return self.payload
        return {}


class FakeBreakpointPage:
    def __init__(self, session=None) -> None:
        self._session = session

    @property
    def url(self):
        return "https://example.test/app"

    def goto(self, url, timeout=None):
        raise AssertionError("not used")

    def title(self):
        return ""

    def content(self):
        return ""

    def evaluate(self, expression):
        raise AssertionError("not used")

    def screenshot(self, path=None):
        return None

    def cdp_session(self):
        return self._session


class BreakpointManagerTests(unittest.TestCase):
    def test_breakpoint_spec_accepts_context_aliases(self) -> None:
        spec = BreakpointSpec.from_context({"url_pattern": ".*app\\.js$", "line_number": "7", "column_number": "2", "condition": "ready === true"})
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.url_pattern, ".*app\\.js$")
        self.assertEqual(spec.line_number, 7)
        self.assertEqual(spec.column_number, 2)
        self.assertEqual(spec.condition, "ready === true")
        self.assertEqual(
            spec.to_cdp_params(),
            {"urlRegex": ".*app\\.js$", "lineNumber": 7, "columnNumber": 2, "condition": "ready === true"},
        )

        camel = BreakpointSpec.from_context({"url": ".*bundle\\.js$", "lineNumber": 9, "columnNumber": 4})
        self.assertIsNotNone(camel)
        assert camel is not None
        self.assertEqual(camel.url_pattern, ".*bundle\\.js$")
        self.assertEqual(camel.line_number, 9)
        self.assertEqual(camel.column_number, 4)

        script_url = BreakpointSpec.from_context({"script_url": "https://cdn.example/app.js"})
        self.assertIsNotNone(script_url)
        assert script_url is not None
        self.assertEqual(script_url.url_pattern, "https://cdn.example/app.js")
        self.assertEqual(script_url.line_number, 0)
        self.assertIsNone(script_url.column_number)

    def test_breakpoint_spec_requires_url_pattern(self) -> None:
        self.assertIsNone(BreakpointSpec.from_context({"line_number": 3}))
        self.assertIsNone(BreakpointSpec.from_context({}))
        self.assertIsNone(BreakpointSpec.from_context(None))

    def test_set_breakpoint_without_cdp_is_unsupported(self) -> None:
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(None), BreakpointSpec.from_context({"url_pattern": ".*app.js"}))
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(result.supported)
        self.assertEqual(result.reason, "cdp_session_unavailable")
        self.assertEqual(result.to_dict()["count"], 0)

    def test_set_breakpoint_missing_spec_is_unsupported(self) -> None:
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(RecordingCDPSession()), None)
        self.assertEqual(result.status, "unsupported")
        self.assertFalse(result.supported)
        self.assertEqual(result.reason, "missing_url_pattern")

    def test_set_breakpoint_uses_debugger_by_url(self) -> None:
        session = RecordingCDPSession()
        spec = BreakpointSpec(url_pattern=".*app\\.js$", line_number=3)
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertTrue(result.supported)
        self.assertEqual(session.calls[0], ("Debugger.enable", {}))
        self.assertEqual(session.calls[1], ("Debugger.setBreakpointByUrl", {"urlRegex": ".*app\\.js$", "lineNumber": 3}))
        self.assertEqual(result.breakpoints[0]["breakpointId"], "bp-1")
        self.assertEqual(result.breakpoints[0]["locations"][0]["scriptId"], "script-1")

    def test_set_breakpoint_failure_is_structured(self) -> None:
        result = BreakpointManager().set_breakpoint(
            FakeBreakpointPage(RecordingCDPSession(error=RuntimeError("debugger blocked"))),
            BreakpointSpec(url_pattern=".*app\\.js$"),
        )
        self.assertEqual(result.status, "failed")
        self.assertTrue(result.supported)
        self.assertIn("debugger blocked", result.error or "")


if __name__ == "__main__":
    unittest.main()
