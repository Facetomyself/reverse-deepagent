import unittest

from reverse_deepagent.browser.hooks import ClosureScopeDiscoveryManager, ClosureScopeDiscoverySpec


class ClosureScopeCDPSession:
    def __init__(self) -> None:
        self.calls = []
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "Debugger.enable":
            return {}
        if method == "Debugger.setBreakpointByUrl":
            return {"breakpointId": "bp-closure-1", "locations": [{"scriptId": "script-1", "lineNumber": params.get("lineNumber", 0)}]}
        if method == "Runtime.evaluate":
            for handler in self.handlers.get("Debugger.paused", []):
                handler(
                    {
                        "reason": "debugCommand",
                        "hitBreakpoints": ["bp-closure-1"],
                        "callFrames": [
                            {
                                "callFrameId": "cf-closure-1",
                                "functionName": "outerBuild",
                                "location": {"scriptId": "script-1", "lineNumber": 12, "columnNumber": 4},
                                "functionLocation": {"scriptId": "script-1", "lineNumber": 9, "columnNumber": 0},
                                "url": "https://example.test/assets/app.js",
                                "scopeChain": [{"type": "local"}, {"type": "closure"}, {"type": "global"}],
                                "this": {"type": "object"},
                            }
                        ],
                    }
                )
            return {"result": {"type": "string", "value": "scheduled"}}
        if method == "Debugger.evaluateOnCallFrame":
            expression = (params or {}).get("expression")
            if expression == "typeof buildSign":
                return {"result": {"type": "string", "value": "function", "description": "function"}}
            if expression == "typeof nonce":
                return {"result": {"type": "string", "value": "string", "description": "string"}}
            return {"result": {"type": "string", "value": "undefined", "description": "undefined"}}
        if method == "Debugger.resume":
            return {}
        return {}


class ClosureScopePage:
    url = "https://example.test/app"

    def __init__(self, session=None) -> None:
        self._session = session

    def cdp_session(self):
        return self._session


class ClosureScopeDiscoveryManagerTests(unittest.TestCase):
    def test_from_context_accepts_candidate_aliases_and_filters_invalid_names(self) -> None:
        spec = ClosureScopeDiscoverySpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 12,
                "closure_function_names": "buildSign, invalid-name, nonce",
                "functionName": "fallbackName",
                "trigger_expression": "debugger; 'scheduled'",
            }
        )

        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.url_pattern, ".*app\\.js$")
        self.assertEqual(spec.line_number, 12)
        self.assertEqual(spec.candidate_names, ["buildSign", "nonce", "fallbackName"])
        self.assertEqual(spec.to_breakpoint_spec().callframe_evaluations, ["typeof buildSign", "typeof nonce", "typeof fallbackName"])

    def test_discovers_closure_function_candidates_from_paused_callframe(self) -> None:
        session = ClosureScopeCDPSession()
        page = ClosureScopePage(session)
        spec = ClosureScopeDiscoverySpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 12,
                "closure_function_names": ["buildSign", "nonce"],
                "trigger_expression": "debugger; 'scheduled'",
            }
        )

        result = ClosureScopeDiscoveryManager().discover(page, spec)

        self.assertEqual(result.status, "success")
        self.assertTrue(result.supported)
        self.assertEqual(result.scope_summary["callframe_count"], 1)
        self.assertEqual(result.scope_summary["selected_function_name"], "outerBuild")
        self.assertEqual(len(result.functions), 2)
        by_name = {item["name"]: item for item in result.functions}
        self.assertTrue(by_name["buildSign"]["is_function"])
        self.assertFalse(by_name["nonce"]["is_function"])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0]["function_name"], "buildSign")
        self.assertEqual(result.candidates[0]["hook_kind"], "closure-scope")
        self.assertFalse(result.candidates[0]["hook_supported"])
        self.assertEqual(result.candidates[0]["enclosing_function"], "outerBuild")
        self.assertIn(("Debugger.resume", {}), session.calls)

    def test_missing_candidate_names_is_not_a_discovery_request(self) -> None:
        self.assertIsNone(ClosureScopeDiscoverySpec.from_context({"url_pattern": ".*app\\.js$"}))


if __name__ == "__main__":
    unittest.main()
