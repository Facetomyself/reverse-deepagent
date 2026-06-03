import unittest

from reverse_deepagent.browser.hooks import (
    ClosureScopeDiscoveryManager,
    ClosureScopeDiscoverySpec,
    ClosureWrapperReplacementPlanManager,
    ClosureWrapperReplacementPlanSpec,
)


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


class ClosureWrapperReplacementPlanManagerTests(unittest.TestCase):
    def test_plans_review_only_wrapper_replacement_from_closure_candidate(self) -> None:
        spec = ClosureWrapperReplacementPlanSpec.from_context(
            {
                "closure_function_candidates": [
                    {
                        "function_name": "buildSign",
                        "candidate_id": "closure:cf-closure-1:buildSign",
                        "hook_kind": "closure-scope",
                        "hook_supported": False,
                        "callFrameId": "cf-closure-1",
                        "evidence_expression": "typeof buildSign",
                    }
                ],
                "candidate_id": "closure:cf-closure-1:buildSign",
                "wrapper_strategy": "log-only-call-through",
            }
        )

        result = ClosureWrapperReplacementPlanManager().plan(spec)
        payload = result.to_dict()

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.selected_candidate["function_name"], "buildSign")
        self.assertEqual(payload["schema_version"], "reverse-deepagent.closure-wrapper-replacement-plan.v1")
        self.assertTrue(payload["plan"]["plan_only"])
        self.assertTrue(payload["plan"]["requires_review"])
        self.assertFalse(payload["plan"]["automatic_wrapper_replacement"])
        self.assertFalse(payload["plan"]["wrapper_installed"])
        self.assertFalse(payload["plan"]["runtime_mutated"])
        self.assertFalse(payload["plan"]["cdp_command_sent"])
        self.assertFalse(payload["plan"]["callframe_evaluated"])
        self.assertTrue(payload["plan"]["replacement_feasibility"]["lexical_binding_proven"])
        self.assertIn("assignment_safety_not_proven", payload["plan"]["execution_blockers"])
        self.assertEqual(payload["plan"]["next_action"], "review_closure_wrapper_replacement_plan_before_execution")
        self.assertTrue(payload["side_effect_policy"]["read_only"])
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_ambiguous_closure_candidate_selection(self) -> None:
        spec = ClosureWrapperReplacementPlanSpec.from_context(
            {
                "closure_function_candidates": [
                    {"function_name": "buildSign", "candidate_id": "closure:cf-1:buildSign", "hook_kind": "closure-scope", "callFrameId": "cf-1"},
                    {"function_name": "buildSign", "candidate_id": "closure:cf-2:buildSign", "hook_kind": "closure-scope", "callFrameId": "cf-2"},
                ]
            }
        )

        result = ClosureWrapperReplacementPlanManager().plan(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "ambiguous_closure_candidate_selection")
        self.assertEqual(result.plan["next_action"], "select_one_closure_candidate_before_wrapper_planning")
        self.assertFalse(result.plan["wrapper_installed"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])


if __name__ == "__main__":
    unittest.main()
