import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.browser.hooks import (
    BreakpointManager,
    BreakpointSpec,
    PausedSessionActionSpec,
    PausedSessionCrossProcessAttachProbeManager,
    PausedSessionCrossProcessAttachProbeSpec,
    PausedSessionCrossProcessExecutionPlanManager,
    PausedSessionCrossProcessExecutionPlanSpec,
    PausedSessionCrossProcessOneActionManager,
    PausedSessionCrossProcessOneActionSpec,
    PausedSessionLiveCallframeRecoveryManager,
    PausedSessionLiveCallframeRecoverySpec,
    PausedSessionLiveContinuationPreflightManager,
    PausedSessionLiveContinuationPreflightSpec,
    PausedSessionTargetAttachReadinessManager,
    PausedSessionTargetAttachReadinessSpec,
)


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
        if method == "Target.attachToTarget":
            return {"sessionId": "attached-session-1"}
        if method == "Target.detachFromTarget":
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
        self.assertEqual(result.to_dict()["mutation_audit_count"], 2)
        self.assertEqual(result.mutation_audit[0]["mutation_category"], "read_only_expression")
        self.assertEqual(result.mutation_audit[0]["risk"], "low")
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
        self.assertEqual(result.to_dict()["mutation_audit_count"], 2)
        self.assertEqual(result.mutation_audit[1]["mutation_category"], "assignment_mutation")
        self.assertTrue(result.mutation_audit[1]["blocked"])
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
        self.assertEqual(result.to_dict()["mutation_audit_count"], 1)
        self.assertEqual(result.mutation_audit[0]["mutation_category"], "assignment_mutation")
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
        BreakpointManager.clear_paused_sessions()
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

    def test_paused_session_registry_supports_resume_follow_up(self) -> None:
        BreakpointManager.clear_paused_sessions()
        session = RecordingCDPSession(emit_pause_on_evaluate=True, emit_pause_on_step=True)
        manager = BreakpointManager()
        spec = BreakpointSpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 3,
                "trigger_expression": "debugger; 'scheduled'",
                "keep_paused": True,
                "pause_session_id": "session-follow-up",
            }
        )
        initial = manager.set_breakpoint(FakeBreakpointPage(session), spec)
        self.assertEqual(initial.debugger_session["lifecycle"], "retained_paused")
        self.assertIn("session-follow-up", BreakpointManager._paused_sessions)
        follow_up = manager.run_paused_session_action(
            FakeBreakpointPage(session),
            PausedSessionActionSpec.from_context({"pause_session_id": "session-follow-up", "paused_session_action": "resume"}),
        )
        self.assertEqual(follow_up.status, "success")
        self.assertEqual(follow_up.debugger_session["lifecycle"], "resumed")
        self.assertEqual(follow_up.debugger_session["continued_from_registry"], True)
        self.assertEqual(follow_up.continuation_preflight["status"], "live_available")
        self.assertEqual(follow_up.continuation_preflight["source"], "registry")
        self.assertTrue(follow_up.continuation_preflight["same_process_registry"])
        self.assertTrue(follow_up.continuation_preflight["target_attached"])
        self.assertTrue(follow_up.continuation_preflight["preflight_before_action"])
        self.assertTrue(follow_up.continuation_preflight["live_continuation_available"])
        self.assertEqual(follow_up.continuation_preflight["requested_action"], "resume")
        self.assertEqual(follow_up.continuation_preflight["post_action_lifecycle"], "resumed")
        self.assertFalse(follow_up.continuation_preflight["post_action_live_continuation_available"])
        self.assertEqual(follow_up.to_dict()["continuation_preflight"]["source"], "registry")
        self.assertEqual(follow_up.debugger_session["continuation_preflight"]["source"], "registry")
        self.assertEqual(follow_up.debugger_timeline["continuation_preflight"]["source"], "registry")
        self.assertIn("debugger.session_action", [entry["type"] for entry in follow_up.debugger_timeline["entries"]])
        self.assertNotIn("session-follow-up", BreakpointManager._paused_sessions)
        self.assertIn(("Debugger.resume", {}), session.calls)

    def test_paused_session_can_persist_durable_snapshot_for_cross_process_inspect(self) -> None:
        BreakpointManager.clear_paused_sessions()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = RecordingCDPSession(emit_pause_on_evaluate=True)
            manager = BreakpointManager()
            spec = BreakpointSpec.from_context(
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 3,
                    "trigger_expression": "debugger; 'scheduled'",
                    "keep_paused": True,
                    "pause_session_id": "durable-session",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                }
            )

            result = manager.set_breakpoint(FakeBreakpointPage(session), spec)

            self.assertEqual(result.status, "success")
            self.assertEqual(result.debugger_session["lifecycle"], "retained_paused")
            snapshot_path = Path(tmpdir) / "durable-session.json"
            self.assertTrue(snapshot_path.exists())
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "durable_paused_session_snapshot")
            self.assertEqual(payload["session_id"], "durable-session")
            self.assertFalse(payload["resume_supported"])
            self.assertFalse(payload["live_continuation_available"])
            self.assertEqual(payload["continuation_preflight"]["status"], "inspect_only")
            self.assertEqual(payload["continuation_preflight"]["source"], "durable_snapshot")
            self.assertFalse(payload["continuation_preflight"]["live_continuation_available"])
            self.assertTrue(payload["continuation_preflight"]["inspect_supported"])
            self.assertEqual(payload["callframes"][0]["functionName"], "buildSign")

            BreakpointManager.clear_paused_sessions()
            follow_up = manager.run_paused_session_action(
                FakeBreakpointPage(None),
                PausedSessionActionSpec.from_context(
                    {
                        "pause_session_id": "durable-session",
                        "paused_session_action": "inspect",
                        "paused_session_store_dir": tmpdir,
                    }
                ),
            )

            self.assertEqual(follow_up.status, "success")
            self.assertEqual(follow_up.reason, "durable_paused_session_snapshot_loaded")
            self.assertTrue(follow_up.debugger_session["continued_from_store"])
            self.assertFalse(follow_up.debugger_session["live_continuation_available"])
            self.assertFalse(follow_up.debugger_session["resume_supported"])
            self.assertTrue(follow_up.debugger_timeline["continued_from_store"])
            self.assertEqual(follow_up.continuation_preflight["status"], "inspect_only")
            self.assertEqual(follow_up.continuation_preflight["source"], "durable_snapshot")
            self.assertFalse(follow_up.continuation_preflight["same_process_registry"])
            self.assertFalse(follow_up.continuation_preflight["live_continuation_available"])
            self.assertTrue(follow_up.continuation_preflight["inspect_supported"])
            self.assertFalse(follow_up.continuation_preflight["resume_supported"])
            self.assertEqual(follow_up.continuation_preflight["reason"], "durable_snapshot_is_inspect_only")
            self.assertEqual(follow_up.debugger_session["continuation_preflight"]["status"], "inspect_only")
            self.assertEqual(follow_up.debugger_timeline["continuation_preflight"]["status"], "inspect_only")
            self.assertEqual(follow_up.callframes[0]["functionName"], "buildSign")

    def test_durable_paused_session_snapshot_rejects_live_resume(self) -> None:
        BreakpointManager.clear_paused_sessions()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = RecordingCDPSession(emit_pause_on_evaluate=True)
            manager = BreakpointManager()
            spec = BreakpointSpec.from_context(
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 3,
                    "trigger_expression": "debugger; 'scheduled'",
                    "keep_paused": True,
                    "pause_session_id": "durable-session",
                    "persist_paused_session": True,
                    "paused_session_store_dir": tmpdir,
                }
            )
            initial = manager.set_breakpoint(FakeBreakpointPage(session), spec)
            self.assertEqual(initial.status, "success")

            BreakpointManager.clear_paused_sessions()
            follow_up = manager.run_paused_session_action(
                FakeBreakpointPage(None),
                PausedSessionActionSpec.from_context(
                    {
                        "pause_session_id": "durable-session",
                        "paused_session_action": "resume",
                        "paused_session_store_dir": tmpdir,
                    }
                ),
            )

            self.assertEqual(follow_up.status, "failed")
            self.assertEqual(follow_up.error, "live_paused_session_required")
            self.assertEqual(follow_up.reason, "durable_snapshot_is_inspect_only")
            self.assertTrue(follow_up.debugger_session["continued_from_store"])
            self.assertFalse(follow_up.debugger_session["live_continuation_available"])
            self.assertFalse(follow_up.debugger_session["resume_supported"])
            self.assertEqual(follow_up.continuation_preflight["status"], "action_blocked")
            self.assertEqual(follow_up.continuation_preflight["source"], "durable_snapshot")
            self.assertTrue(follow_up.continuation_preflight["blocked_action"])
            self.assertEqual(follow_up.continuation_preflight["blocked_reason"], "live_paused_session_required")
            self.assertFalse(follow_up.continuation_preflight["live_continuation_available"])
            self.assertEqual(follow_up.debugger_session["continuation_preflight"]["status"], "action_blocked")
            self.assertNotIn(("Debugger.resume", {}), session.calls)

    def test_live_continuation_preflight_blocks_durable_snapshot_resume_without_side_effects(self) -> None:
        BreakpointManager.clear_paused_sessions()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = RecordingCDPSession(emit_pause_on_evaluate=True)
            manager = BreakpointManager()
            initial = manager.set_breakpoint(
                FakeBreakpointPage(session),
                BreakpointSpec.from_context(
                    {
                        "url_pattern": ".*app\\.js$",
                        "line_number": 3,
                        "trigger_expression": "debugger; 'scheduled'",
                        "keep_paused": True,
                        "pause_session_id": "durable-live-preflight",
                        "persist_paused_session": True,
                        "paused_session_store_dir": tmpdir,
                    }
                ),
            )
            self.assertEqual(initial.status, "success")
            initial_call_count = len(session.calls)

            BreakpointManager.clear_paused_sessions()
            result = PausedSessionLiveContinuationPreflightManager().preflight(
                PausedSessionLiveContinuationPreflightSpec.from_context(
                    {
                        "pause_session_id": "durable-live-preflight",
                        "requested_action": "resume",
                        "paused_session_store_dir": tmpdir,
                    }
                )
            )

            self.assertEqual(result.status, "blocked")
            self.assertEqual(result.reason, "live_paused_session_required")
            self.assertEqual(result.preflight["source"], "durable_snapshot")
            self.assertTrue(result.preflight["durable_snapshot_found"])
            self.assertFalse(result.preflight["same_process_registry"])
            self.assertFalse(result.preflight["live_continuation_available"])
            self.assertFalse(result.preflight["cross_process_live_continuation_supported"])
            self.assertFalse(result.preflight["resume_supported"])
            self.assertIn("live_paused_session_required", result.preflight["blockers"])
            self.assertIn("target_not_attached", result.preflight["blockers"])
            self.assertIn("debugger_session_not_live", result.preflight["blockers"])
            self.assertIn("cdp_target_unavailable", result.preflight["blockers"])
            self.assertEqual(result.preflight["live_session_diagnostics"]["debugger_session_lifecycle"], "retained_paused")
            self.assertFalse(result.preflight["live_session_diagnostics"]["live_session_available"])
            self.assertTrue(result.preflight["live_session_diagnostics"]["same_process_required_for_live_action"])
            self.assertFalse(result.preflight["live_session_diagnostics"]["cross_process_resume_supported"])
            self.assertEqual(result.preflight["target_diagnostics"]["target_attached_source"], "not_attached")
            self.assertFalse(result.preflight["target_diagnostics"]["would_attach_cdp_target"])
            self.assertEqual(result.preflight["callframe_diagnostics"]["callframe_count"], 1)
            self.assertFalse(result.preflight["callframe_diagnostics"]["stable_callframe_required"])
            self.assertEqual(result.preflight["action_capability"]["requested_action"], "resume")
            self.assertTrue(result.preflight["action_capability"]["is_live_action"])
            self.assertEqual(result.preflight["blocker_details"][0]["code"], "live_paused_session_required")
            self.assertFalse(result.side_effect_policy["cdp_command_sent"])
            self.assertFalse(result.side_effect_policy["browser_resumed"])
            self.assertFalse(result.side_effect_policy["debugger_stepped"])
            self.assertFalse(result.side_effect_policy["callframe_evaluated"])
            self.assertEqual(len(session.calls), initial_call_count)

    def test_live_continuation_preflight_reports_same_process_registry_available(self) -> None:
        BreakpointManager.clear_paused_sessions()
        session = RecordingCDPSession(emit_pause_on_evaluate=True)
        manager = BreakpointManager()
        initial = manager.set_breakpoint(
            FakeBreakpointPage(session),
            BreakpointSpec.from_context(
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 3,
                    "trigger_expression": "debugger; 'scheduled'",
                    "keep_paused": True,
                    "pause_session_id": "same-process-live-preflight",
                }
            ),
        )
        self.assertEqual(initial.status, "success")
        initial_call_count = len(session.calls)

        result = PausedSessionLiveContinuationPreflightManager().preflight(
            PausedSessionLiveContinuationPreflightSpec.from_context(
                {
                    "pause_session_id": "same-process-live-preflight",
                    "requested_action": "resume",
                }
            )
        )

        self.assertEqual(result.status, "live_available")
        self.assertEqual(result.preflight["source"], "registry")
        self.assertTrue(result.preflight["same_process_registry"])
        self.assertTrue(result.preflight["target_attached"])
        self.assertTrue(result.preflight["cdp_target_available"])
        self.assertTrue(result.preflight["live_continuation_available"])
        self.assertFalse(result.preflight["cross_process_live_continuation_supported"])
        self.assertEqual(result.preflight["blockers"], [])
        self.assertTrue(result.preflight["live_session_diagnostics"]["live_session_available"])
        self.assertEqual(result.preflight["live_session_diagnostics"]["debugger_session_lifecycle"], "retained_paused")
        self.assertEqual(result.preflight["target_diagnostics"]["target_attached_source"], "same_process_registry")
        self.assertTrue(result.preflight["target_diagnostics"]["target_attached"])
        self.assertEqual(result.preflight["callframe_diagnostics"]["callframe_count"], 1)
        self.assertFalse(result.preflight["callframe_diagnostics"]["stable_callframe_required"])
        self.assertEqual(result.preflight["action_capability"]["requested_action"], "resume")
        self.assertTrue(result.preflight["action_capability"]["resume_supported"])
        self.assertIn("same-process-live-preflight", BreakpointManager._paused_sessions)
        self.assertEqual(len(session.calls), initial_call_count)

    def test_live_continuation_preflight_blocks_artifact_only_evaluate_without_stable_callframe(self) -> None:
        BreakpointManager.clear_paused_sessions()

        result = PausedSessionLiveContinuationPreflightManager().preflight(
            PausedSessionLiveContinuationPreflightSpec.from_context(
                {
                    "pause_session_id": "artifact-only",
                    "requested_action": "evaluate",
                    "debugger_session": {"session_id": "artifact-only", "lifecycle": "retained_paused"},
                    "callframes": [{"functionName": "sign", "location": {"lineNumber": 1}}],
                }
            )
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.preflight["source"], "provided_artifact")
        self.assertTrue(result.preflight["provided_artifact_found"])
        self.assertFalse(result.preflight["same_process_registry"])
        self.assertFalse(result.preflight["selected_callframe_has_id"])
        self.assertFalse(result.preflight["live_continuation_available"])
        self.assertFalse(result.preflight["evaluate_supported"])
        self.assertIn("live_paused_session_required", result.preflight["blockers"])
        self.assertIn("target_not_attached", result.preflight["blockers"])
        self.assertIn("debugger_session_not_live", result.preflight["blockers"])
        self.assertIn("cdp_target_unavailable", result.preflight["blockers"])
        self.assertIn("callframe_id_not_stable", result.preflight["blockers"])
        self.assertFalse(result.preflight["live_session_diagnostics"]["live_session_available"])
        self.assertTrue(result.preflight["live_session_diagnostics"]["same_process_required_for_live_action"])
        self.assertFalse(result.preflight["target_diagnostics"]["target_attached"])
        self.assertTrue(result.preflight["callframe_diagnostics"]["stable_callframe_required"])
        self.assertFalse(result.preflight["callframe_diagnostics"]["stable_callframe_available"])
        self.assertEqual(result.preflight["callframe_diagnostics"]["selected_callframe"]["function_name"], "sign")
        self.assertTrue(result.preflight["action_capability"]["is_live_action"])
        self.assertFalse(result.preflight["action_capability"]["evaluate_supported"])
        self.assertIn("callframe", {detail["category"] for detail in result.preflight["blocker_details"]})
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_target_attach_readiness_proves_durable_snapshot_target_match_without_side_effects(self) -> None:
        BreakpointManager.clear_paused_sessions()
        with tempfile.TemporaryDirectory() as tmpdir:
            session = RecordingCDPSession(emit_pause_on_evaluate=True)
            manager = BreakpointManager()
            initial = manager.set_breakpoint(
                FakeBreakpointPage(session),
                BreakpointSpec.from_context(
                    {
                        "url_pattern": ".*app\\.js$",
                        "line_number": 3,
                        "trigger_expression": "debugger; 'scheduled'",
                        "keep_paused": True,
                        "pause_session_id": "attach-ready",
                        "persist_paused_session": True,
                        "paused_session_store_dir": tmpdir,
                    }
                ),
            )
            self.assertEqual(initial.status, "success")
            initial_call_count = len(session.calls)

            BreakpointManager.clear_paused_sessions()
            result = PausedSessionTargetAttachReadinessManager().assess(
                PausedSessionTargetAttachReadinessSpec.from_context(
                    {
                        "pause_session_id": "attach-ready",
                        "requested_action": "evaluate",
                        "paused_session_store_dir": tmpdir,
                        "target_candidates": [
                            {
                                "targetId": "target-1",
                                "type": "page",
                                "url": "https://example.test/app.js",
                                "attached": False,
                            }
                        ],
                    }
                )
            )

            self.assertEqual(result.status, "ready_for_attach_review")
            self.assertEqual(result.reason, "stable_live_callframe_unavailable")
            self.assertEqual(result.readiness["source"], "durable_snapshot")
            self.assertTrue(result.readiness["target_attach_readiness_proven"])
            self.assertFalse(result.readiness["cross_process_execution_ready"])
            self.assertFalse(result.readiness["cross_process_live_continuation_supported"])
            self.assertIn("stable_live_callframe_unavailable", result.readiness["blockers"])
            self.assertIn("cross_process_live_continuation_not_implemented", result.readiness["blockers"])
            self.assertEqual(result.readiness["target_correlation"]["selected_target"]["target_id"], "target-1")
            self.assertTrue(result.readiness["target_correlation"]["url_match"])
            self.assertTrue(result.readiness["attachability"]["target_id_available"])
            self.assertFalse(result.readiness["attachability"]["would_attach_cdp_target"])
            self.assertFalse(result.readiness["callframe_recovery"]["durable_callframe_id_reusable"])
            self.assertTrue(result.readiness["callframe_recovery"]["requires_new_paused_event_after_attach"])
            self.assertFalse(result.readiness["action_capability"]["evaluate_supported"])
            self.assertFalse(result.side_effect_policy["cdp_command_sent"])
            self.assertFalse(result.side_effect_policy["cdp_target_attached"])
            self.assertFalse(result.side_effect_policy["callframe_evaluated"])
            self.assertEqual(len(session.calls), initial_call_count)

    def test_target_attach_readiness_blocks_when_target_candidates_do_not_match_paused_url(self) -> None:
        BreakpointManager.clear_paused_sessions()
        result = PausedSessionTargetAttachReadinessManager().assess(
            PausedSessionTargetAttachReadinessSpec.from_context(
                {
                    "pause_session_id": "artifact-target-mismatch",
                    "requested_action": "resume",
                    "debugger_session": {"session_id": "artifact-target-mismatch", "lifecycle": "retained_paused"},
                    "callframes": [{"functionName": "sign", "url": "https://example.test/app.js", "callFrameId": "cf-stale"}],
                    "target_candidates": [{"targetId": "target-2", "type": "page", "url": "https://other.test/app.js"}],
                }
            )
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "target_url_mismatch")
        self.assertEqual(result.readiness["source"], "provided_artifact")
        self.assertFalse(result.readiness["target_attach_readiness_proven"])
        self.assertIn("target_url_mismatch", result.readiness["blockers"])
        self.assertFalse(result.readiness["target_correlation"]["url_match"])
        self.assertFalse(result.readiness["attachability"]["would_probe_cdp_target"])
        self.assertFalse(result.side_effect_policy["browser_resumed"])

    def test_cross_process_execution_plan_uses_attach_readiness_without_side_effects(self) -> None:
        spec = PausedSessionCrossProcessExecutionPlanSpec.from_context(
            {
                "paused_session_cross_process_execution_plan": True,
                "paused_session_target_attach_readiness": {
                    "readiness": {
                        "status": "ready_for_attach_review",
                        "source": "durable_snapshot",
                        "pause_session_id": "plan-session-1",
                        "requested_action": "evaluate",
                        "target_attach_readiness_proven": True,
                        "target_correlation": {
                            "expected_url": "https://example.test/app.js",
                            "candidate_count": 1,
                            "selected_target": {"target_id": "target-1", "type": "page", "url": "https://example.test/app.js"},
                        },
                        "attachability": {
                            "target_id_available": True,
                            "target_type_supported": True,
                            "requires_explicit_future_attach_step": True,
                        },
                        "callframe_recovery": {
                            "stable_live_callframe_available": False,
                            "selected_callframe_has_id": True,
                            "requires_new_paused_event_after_attach": True,
                        },
                    }
                },
            }
        )

        result = PausedSessionCrossProcessExecutionPlanManager().plan(spec)
        plan = result.plan

        self.assertEqual(result.status, "ready_for_executor_review")
        self.assertTrue(plan["execution_plan_ready_for_review"])
        self.assertFalse(plan["cross_process_execution_ready"])
        self.assertTrue(plan["cross_process_executor_implemented"])
        self.assertEqual(plan["next_action"], "run_reviewed_cross_process_attach_probe_next")
        self.assertEqual(plan["target_attach_readiness_summary"]["selected_target"]["target_id"], "target-1")
        self.assertTrue(plan["review_gates"]["attach_probe_review_required"])
        self.assertTrue(plan["review_gates"]["action_execution_review_required"])
        self.assertTrue(plan["callframe_recovery_plan"]["requires_new_paused_event_after_attach"])
        self.assertIn("full_cross_process_continuation_not_implemented", plan["capability_boundaries"])
        self.assertFalse(result.side_effect_policy["would_attach_cdp_target"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["browser_resumed"])
        self.assertFalse(result.side_effect_policy["debugger_stepped"])
        self.assertFalse(result.side_effect_policy["callframe_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])


    def test_paused_session_cross_process_attach_probe_ready_for_review_without_side_effects(self) -> None:
        plan = {
            "status": "ready_for_executor_review",
            "execution_plan_ready_for_review": True,
            "target_attach_readiness_proven": True,
            "pause_session_id": "attach-probe-1",
            "requested_action": "evaluate",
            "target_attach_readiness_summary": {
                "selected_target": {"target_id": "target-attach-1", "type": "page"},
                "target_id_available": True,
            },
        }
        spec = PausedSessionCrossProcessAttachProbeSpec.from_context(
            {
                "paused_session_cross_process_attach_probe": True,
                "paused_session_cross_process_execution_plan": {"plan": plan},
            }
        )

        result = PausedSessionCrossProcessAttachProbeManager().probe(None, spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(result.probe["next_action"], "approve_cross_process_attach_probe")
        self.assertFalse(result.probe["attach_attempted"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_paused_session_cross_process_attach_probe_blocks_without_plan(self) -> None:
        spec = PausedSessionCrossProcessAttachProbeSpec.from_context({"paused_session_cross_process_attach_probe": True})

        result = PausedSessionCrossProcessAttachProbeManager().probe(None, spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("cross_process_execution_plan_required", result.probe["blockers"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_paused_session_cross_process_attach_probe_requires_review_approval(self) -> None:
        session = RecordingCDPSession()
        page = FakeBreakpointPage(session)
        plan = {
            "status": "ready_for_executor_review",
            "execution_plan_ready_for_review": True,
            "target_attach_readiness_proven": True,
            "target_attach_readiness_summary": {
                "selected_target": {"target_id": "target-attach-1", "type": "page"},
                "target_id_available": True,
            },
        }
        spec = PausedSessionCrossProcessAttachProbeSpec.from_context(
            {
                "paused_session_cross_process_attach_probe": True,
                "execute_cross_process_attach_probe": True,
                "review_approved": False,
                "paused_session_cross_process_execution_plan": {"plan": plan},
            }
        )

        result = PausedSessionCrossProcessAttachProbeManager().probe(page, spec)

        self.assertEqual(result.status, "review_required")
        self.assertIn("review_approval_required", result.probe["blockers"])
        self.assertEqual(session.calls, [])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_paused_session_cross_process_attach_probe_attaches_and_detaches_only(self) -> None:
        session = RecordingCDPSession()
        page = FakeBreakpointPage(session)
        plan = {
            "status": "ready_for_executor_review",
            "execution_plan_ready_for_review": True,
            "target_attach_readiness_proven": True,
            "pause_session_id": "attach-probe-1",
            "requested_action": "evaluate",
            "target_attach_readiness_summary": {
                "selected_target": {"target_id": "target-attach-1", "type": "page"},
                "target_id_available": True,
            },
        }
        spec = PausedSessionCrossProcessAttachProbeSpec.from_context(
            {
                "paused_session_cross_process_attach_probe": True,
                "execute_cross_process_attach_probe": True,
                "review_approved": True,
                "paused_session_cross_process_execution_plan": {"plan": plan},
            }
        )

        result = PausedSessionCrossProcessAttachProbeManager().probe(page, spec)

        self.assertEqual(result.status, "attached")
        self.assertEqual(result.probe["attached_session_id"], "attached-session-1")
        self.assertEqual(result.probe["cdp_methods"], ["Target.attachToTarget", "Target.detachFromTarget"])
        self.assertIn(("Target.attachToTarget", {"targetId": "target-attach-1", "flatten": True}), session.calls)
        self.assertIn(("Target.detachFromTarget", {"sessionId": "attached-session-1"}), session.calls)
        forbidden = {"Debugger.enable", "Debugger.resume", "Debugger.stepOver", "Debugger.evaluateOnCallFrame", "Runtime.evaluate"}
        self.assertFalse(any(method in forbidden for method, _ in session.calls))
        self.assertTrue(result.side_effect_policy["cdp_command_sent"])
        self.assertTrue(result.side_effect_policy["cdp_target_attached"])
        self.assertTrue(result.side_effect_policy["cdp_target_detached"])
        self.assertFalse(result.side_effect_policy["live_action_executed"])
        self.assertFalse(result.probe["debugger_domain_enabled"])
        self.assertFalse(result.probe["live_callframe_recovered"])


    def test_paused_session_live_callframe_recovery_recovers_fresh_callframe_without_side_effects(self) -> None:
        spec = PausedSessionLiveCallframeRecoverySpec.from_context(
            {
                "paused_session_live_callframe_recovery": True,
                "fresh_paused_event_after_attach": True,
                "paused_session_cross_process_attach_probe": {
                    "probe": {
                        "status": "attached",
                        "pause_session_id": "recover-1",
                        "requested_action": "evaluate",
                        "target_id": "target-recover-1",
                        "target_attached": True,
                        "attached_session_id": "attached-session-1",
                        "target_detached": True,
                    }
                },
                "debugger_paused": {
                    "callFrames": [
                        {
                            "callFrameId": "live-cf-1",
                            "functionName": "buildSign",
                            "url": "https://example.test/app.js",
                            "location": {"lineNumber": 3, "columnNumber": 2},
                        }
                    ]
                },
            }
        )

        result = PausedSessionLiveCallframeRecoveryManager().recover(spec)

        self.assertEqual(result.status, "recovered")
        self.assertTrue(result.recovery["live_callframe_recovered"])
        self.assertEqual(result.recovery["live_callframe_id"], "live-cf-1")
        self.assertEqual(result.recovery["next_action"], "plan_cross_process_one_action_executor")
        self.assertTrue(result.recovery["one_action_executor_ready_for_review"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["callframe_evaluated"])
        self.assertFalse(result.side_effect_policy["live_action_executed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_paused_session_live_callframe_recovery_blocks_without_fresh_paused_event(self) -> None:
        spec = PausedSessionLiveCallframeRecoverySpec.from_context(
            {
                "paused_session_live_callframe_recovery": True,
                "paused_session_cross_process_attach_probe": {
                    "probe": {"status": "attached", "target_id": "target-recover-1", "target_attached": True}
                },
                "callframes": [{"callFrameId": "stale-cf-1", "functionName": "buildSign"}],
            }
        )

        result = PausedSessionLiveCallframeRecoveryManager().recover(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("fresh_paused_event_after_attach_required", result.recovery["blockers"])
        self.assertFalse(result.recovery["live_callframe_recovered"])
        self.assertEqual(result.recovery["next_action"], "capture_new_paused_event_after_attach")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_paused_session_live_callframe_recovery_blocks_without_attach_probe(self) -> None:
        spec = PausedSessionLiveCallframeRecoverySpec.from_context(
            {
                "paused_session_live_callframe_recovery": True,
                "fresh_paused_event_after_attach": True,
                "callframes": [{"callFrameId": "live-cf-1", "functionName": "buildSign"}],
            }
        )

        result = PausedSessionLiveCallframeRecoveryManager().recover(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("cross_process_attach_probe_required", result.recovery["blockers"])
        self.assertEqual(result.recovery["next_action"], "run_reviewed_cross_process_attach_probe")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_cross_process_one_action_executes_reviewed_evaluate_once(self) -> None:
        session = RecordingCDPSession()
        spec = PausedSessionCrossProcessOneActionSpec.from_context(
            {
                "paused_session_cross_process_one_action": True,
                "execute_cross_process_one_action": True,
                "review_approved": True,
                "requested_action": "evaluate",
                "expression": "typeof buildSign",
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "pause_session_id": "recover-1",
                        "requested_action": "evaluate",
                        "target_id": "target-recover-1",
                        "target_attached": True,
                        "target_detached": False,
                        "attached_session_id": "attached-session-1",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "live-cf-1",
                    }
                },
            }
        )

        result = PausedSessionCrossProcessOneActionManager().execute(FakeBreakpointPage(session), spec)

        self.assertEqual(result.status, "executed")
        self.assertEqual(session.calls[-1][0], "Debugger.evaluateOnCallFrame")
        self.assertEqual(session.calls[-1][1]["sessionId"], "attached-session-1")
        self.assertEqual(session.calls[-1][1]["callFrameId"], "live-cf-1")
        self.assertEqual(result.execution["method"], "Debugger.evaluateOnCallFrame")
        self.assertTrue(result.execution["live_action_executed"])
        self.assertTrue(result.execution["callframe_evaluated"])
        self.assertFalse(result.execution["browser_resumed"])
        self.assertFalse(result.execution["debugger_stepped"])
        self.assertTrue(result.side_effect_policy["cdp_command_sent"])
        self.assertTrue(result.side_effect_policy["callframe_evaluated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_cross_process_one_action_requires_review_approval(self) -> None:
        session = RecordingCDPSession()
        spec = PausedSessionCrossProcessOneActionSpec.from_context(
            {
                "paused_session_cross_process_one_action": True,
                "execute_cross_process_one_action": True,
                "requested_action": "resume",
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "target_detached": False,
                        "attached_session_id": "attached-session-1",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "live-cf-1",
                    }
                },
            }
        )

        result = PausedSessionCrossProcessOneActionManager().execute(FakeBreakpointPage(session), spec)

        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertEqual(result.execution["next_action"], "approve_cross_process_one_action_execution")
        self.assertEqual(session.calls, [])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_cross_process_one_action_blocks_detached_attach_probe_session(self) -> None:
        spec = PausedSessionCrossProcessOneActionSpec.from_context(
            {
                "paused_session_cross_process_one_action": True,
                "requested_action": "resume",
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "target_detached": True,
                        "attached_session_id": "attached-session-1",
                        "live_callframe_recovered": True,
                        "live_callframe_id": "live-cf-1",
                    }
                },
            }
        )

        result = PausedSessionCrossProcessOneActionManager().execute(FakeBreakpointPage(RecordingCDPSession()), spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("attached_session_retained_required", result.execution["blockers"])
        self.assertEqual(result.execution["next_action"], "rerun_attach_probe_without_detach_for_one_action")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_cross_process_execution_plan_blocks_without_attach_readiness(self) -> None:
        result = PausedSessionCrossProcessExecutionPlanManager().plan(
            PausedSessionCrossProcessExecutionPlanSpec.from_context(
                {"paused_session_cross_process_execution_plan": True, "pause_session_id": "missing-readiness"}
            )
        )

        self.assertEqual(result.status, "blocked")
        self.assertIn("target_attach_readiness_required", result.plan["blockers"])
        self.assertEqual(result.plan["next_action"], "produce_paused_session_target_attach_readiness")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])

    def test_missing_paused_session_reports_unavailable_preflight(self) -> None:
        BreakpointManager.clear_paused_sessions()
        follow_up = BreakpointManager().run_paused_session_action(
            FakeBreakpointPage(None),
            PausedSessionActionSpec.from_context({"pause_session_id": "missing-session", "paused_session_action": "inspect"}),
        )

        self.assertEqual(follow_up.status, "unsupported")
        self.assertEqual(follow_up.reason, "pause_session_not_found")
        self.assertEqual(follow_up.continuation_preflight["status"], "unavailable")
        self.assertEqual(follow_up.continuation_preflight["source"], "missing")
        self.assertEqual(follow_up.continuation_preflight["pause_session_id"], "missing-session")
        self.assertFalse(follow_up.continuation_preflight["same_process_registry"])
        self.assertFalse(follow_up.continuation_preflight["durable_snapshot_found"])
        self.assertFalse(follow_up.continuation_preflight["live_continuation_available"])
        self.assertEqual(follow_up.continuation_preflight["reason"], "pause_session_not_found")

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
