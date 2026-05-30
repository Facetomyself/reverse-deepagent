import unittest

from reverse_deepagent.browser.hooks import BreakpointManager, BreakpointSpec


class RecordingCDPSession:
    def __init__(
        self,
        payload=None,
        error: Exception | None = None,
        emit_pause_on_evaluate: bool = False,
        emit_pause_on_step: bool = False,
    ) -> None:
        self.calls = []
        self.payload = payload or {"breakpointId": "bp-1", "locations": [{"scriptId": "script-1", "lineNumber": 3, "columnNumber": 0}]}
        self.error = error
        self.emit_pause_on_evaluate = emit_pause_on_evaluate
        self.emit_pause_on_step = emit_pause_on_step
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def send(self, method, params=None):
        self.calls.append((method, params or {}))
        if self.error is not None and method == "Debugger.setBreakpointByUrl":
            raise self.error
        if method == "Debugger.setBreakpointByUrl":
            return self.payload
        if method == "Runtime.evaluate":
            if self.emit_pause_on_evaluate:
                for handler in self.handlers.get("Debugger.paused", []):
                    handler(
                        {
                            "reason": "debugCommand",
                            "hitBreakpoints": ["bp-1"],
                            "callFrames": [
                                {
                                    "callFrameId": "cf-1",
                                    "functionName": "buildSign",
                                    "location": {"scriptId": "script-1", "lineNumber": 3, "columnNumber": 2},
                                    "functionLocation": {"scriptId": "script-1", "lineNumber": 1, "columnNumber": 0},
                                    "url": "https://example.test/app.js",
                                    "scopeChain": [{"type": "local"}],
                                    "this": {"type": "object"},
                                }
                            ],
                        }
                    )
            return {"result": {"type": "string", "value": "scheduled"}}
        if method == "Debugger.evaluateOnCallFrame":
            expression = (params or {}).get("expression")
            value = "function" if expression == "typeof buildSign" else True if expression == "this && typeof this" else "ok"
            value_type = "boolean" if isinstance(value, bool) else "string"
            return {"result": {"type": value_type, "value": value, "description": str(value)}}
        if method in {"Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"}:
            if self.emit_pause_on_step:
                for handler in self.handlers.get("Debugger.paused", []):
                    handler(
                        {
                            "reason": "step",
                            "hitBreakpoints": [],
                            "callFrames": [
                                {
                                    "callFrameId": "cf-2",
                                    "functionName": "buildSign",
                                    "location": {"scriptId": "script-1", "lineNumber": 4, "columnNumber": 2},
                                    "url": "https://example.test/app.js",
                                    "scopeChain": [{"type": "local"}],
                                    "this": {"type": "object"},
                                }
                            ],
                        }
                    )
            return {}
        if method == "Debugger.resume":
            return {}
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

        eval_spec = BreakpointSpec.from_context(
            {
                "script_url": "https://cdn.example/app.js",
                "evaluateOnCallFrame": ["typeof buildSign", " this && typeof this "],
                "callFrameIndex": "0",
                "evaluationPolicy": "block-dangerous",
                "debuggerActions": ["step-over"],
                "preservePauseState": True,
                "pauseSessionId": "session-1",
            }
        )
        self.assertIsNotNone(eval_spec)
        assert eval_spec is not None
        self.assertEqual(eval_spec.callframe_evaluations, ["typeof buildSign", "this && typeof this"])
        self.assertEqual(eval_spec.callframe_index, 0)
        self.assertEqual(eval_spec.callframe_evaluation_policy, "block_dangerous")
        self.assertEqual(eval_spec.debugger_actions, ["step-over"])
        self.assertTrue(eval_spec.preserve_pause_state)
        self.assertFalse(eval_spec.auto_resume)
        self.assertEqual(eval_spec.pause_session_id, "session-1")

        unsafe_spec = BreakpointSpec.from_context({"url": ".*", "allowCallframeSideEffects": True})
        self.assertIsNotNone(unsafe_spec)
        assert unsafe_spec is not None
        self.assertEqual(unsafe_spec.callframe_evaluation_policy, "allow_side_effects")

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
        self.assertEqual(result.paused["status"], "not_observed")

    def test_set_breakpoint_can_capture_paused_callframes_with_trigger(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True, emit_pause_on_step=True)
        spec = BreakpointSpec(
            url_pattern=".*app\\.js$",
            line_number=3,
            trigger_expression="setTimeout(() => { debugger; }, 0); 'scheduled'",
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.paused["status"], "success")
        self.assertEqual(result.paused["reason"], "debugCommand")
        self.assertEqual(result.callframes[0]["functionName"], "buildSign")
        self.assertEqual(result.callframes[0]["location"]["lineNumber"], 3)
        self.assertTrue(result.trigger["attempted"])
        self.assertIn(("Debugger.resume", {}), session.calls)
        self.assertEqual(result.to_dict()["callframe_count"], 1)

    def test_set_breakpoint_evaluates_explicit_callframe_expressions_before_resume(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True, emit_pause_on_step=True)
        spec = BreakpointSpec(
            url_pattern=".*app\\.js$",
            line_number=3,
            trigger_expression="debugger; 'scheduled'",
            callframe_evaluations=["typeof buildSign", "this && typeof this"],
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.paused["status"], "success")
        self.assertEqual(result.to_dict()["callframe_evaluation_count"], 2)
        self.assertEqual(result.callframe_evaluations[0]["expression"], "typeof buildSign")
        self.assertTrue(result.callframe_evaluations[0]["ok"])
        self.assertEqual(result.callframe_evaluations[0]["value"], "function")
        self.assertEqual(result.callframe_evaluations[0]["valueType"], "string")
        self.assertEqual(result.callframe_evaluations[0]["callFrameId"], "cf-1")
        self.assertEqual(result.callframe_evaluations[0]["policy"], "read_only")
        self.assertTrue(result.callframe_evaluations[0]["throw_on_side_effect"])
        self.assertEqual(result.callframe_evaluations[1]["value"], True)
        self.assertEqual(result.debugger_timeline["status"], "success")
        self.assertEqual(result.debugger_timeline["evaluation_count"], 2)
        self.assertIn("callframe.evaluate", [entry["type"] for entry in result.debugger_timeline["entries"]])
        evaluate_index = next(index for index, call in enumerate(session.calls) if call[0] == "Debugger.evaluateOnCallFrame")
        resume_index = next(index for index, call in enumerate(session.calls) if call[0] == "Debugger.resume")
        self.assertLess(evaluate_index, resume_index)

    def test_callframe_evaluation_policy_blocks_dangerous_default_expressions(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True)
        spec = BreakpointSpec(
            url_pattern=".*app\\.js$",
            line_number=3,
            trigger_expression="debugger; 'scheduled'",
            callframe_evaluations=["typeof buildSign", "window.__sideEffect = 1"],
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.to_dict()["callframe_evaluation_count"], 2)
        self.assertTrue(result.callframe_evaluations[0]["ok"])
        self.assertFalse(result.callframe_evaluations[1]["ok"])
        self.assertTrue(result.callframe_evaluations[1]["blocked"])
        self.assertEqual(result.callframe_evaluations[1]["error"], "blocked_by_callframe_evaluation_policy")
        self.assertEqual(result.callframe_evaluations[1]["side_effect_risk"], "high")
        blocked_entries = [entry for entry in result.debugger_timeline["entries"] if entry["type"] == "callframe.evaluate" and entry.get("blocked")]
        self.assertEqual(blocked_entries[0]["error"], "blocked_by_callframe_evaluation_policy")
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), 1)

    def test_callframe_evaluation_policy_can_explicitly_allow_side_effects(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True)
        spec = BreakpointSpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 3,
                "trigger_expression": "debugger; 'scheduled'",
                "callframe_evaluations": ["window.__sideEffect = 1"],
                "allow_callframe_side_effects": True,
            }
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.to_dict()["callframe_evaluation_count"], 1)
        self.assertTrue(result.callframe_evaluations[0]["ok"])
        self.assertFalse(result.callframe_evaluations[0]["blocked"])
        self.assertEqual(result.callframe_evaluations[0]["policy"], "allow_side_effects")
        evaluate_call = next(call for call in session.calls if call[0] == "Debugger.evaluateOnCallFrame")
        self.assertFalse(evaluate_call[1]["throwOnSideEffect"])

    def test_set_breakpoint_runs_explicit_debugger_step_actions_without_auto_resume(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True, emit_pause_on_step=True)
        spec = BreakpointSpec(
            url_pattern=".*app\\.js$",
            line_number=3,
            trigger_expression="debugger; 'scheduled'",
            callframe_evaluations=["typeof buildSign"],
            debugger_actions=["step_over"],
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.paused["status"], "success")
        self.assertEqual(result.to_dict()["debugger_action_count"], 1)
        self.assertEqual(result.to_dict()["debugger_session"]["lifecycle"], "action_controlled")
        self.assertEqual(result.to_dict()["debugger_session"]["selected_callframe_id"], "cf-1")
        self.assertEqual(result.to_dict()["debugger_timeline"]["lifecycle"], "action_controlled")
        self.assertEqual(result.to_dict()["debugger_timeline"]["debugger_action_count"], 1)
        self.assertEqual(result.debugger_actions[0]["action"], "step_over")
        self.assertEqual(result.debugger_actions[0]["method"], "Debugger.stepOver")
        self.assertTrue(result.debugger_actions[0]["ok"])
        self.assertEqual(result.paused["count"], 2)
        evaluate_index = next(index for index, call in enumerate(session.calls) if call[0] == "Debugger.evaluateOnCallFrame")
        step_index = next(index for index, call in enumerate(session.calls) if call[0] == "Debugger.stepOver")
        self.assertLess(evaluate_index, step_index)
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.stepOver"), 1)
        self.assertIn(("Debugger.resume", {}), session.calls)

    def test_set_breakpoint_can_preserve_paused_session_without_auto_resume(self) -> None:
        session = RecordingCDPSession(emit_pause_on_evaluate=True)
        spec = BreakpointSpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 3,
                "trigger_expression": "debugger; 'scheduled'",
                "wait_after_trigger_ms": 1,
                "keep_paused": True,
                "pause_session_id": "unit-paused-session",
            }
        )
        result = BreakpointManager().set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.paused["status"], "success")
        self.assertEqual(result.debugger_session["session_id"], "unit-paused-session")
        self.assertEqual(result.debugger_session["lifecycle"], "retained_paused")
        self.assertEqual(result.debugger_session["selected_callframe_id"], "cf-1")
        self.assertEqual(result.debugger_session["events"][0]["top_function"], "buildSign")
        self.assertEqual(result.debugger_timeline["lifecycle"], "retained_paused")
        self.assertIn("debugger.resume", [entry["type"] for entry in result.debugger_timeline["entries"]])
        self.assertEqual(result.trigger["mode"], "scheduled")
        self.assertNotIn(("Debugger.resume", {}), session.calls)

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
