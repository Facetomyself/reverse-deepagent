import unittest

from reverse_deepagent.browser.hooks import (
    BreakpointManager,
    ClosureScopeDiscoveryManager,
    ClosureScopeDiscoverySpec,
    ClosureWrapperAssignmentSafetyManager,
    ClosureWrapperAssignmentSafetySpec,
    ClosureWrapperEventHarvestManager,
    ClosureWrapperEventHarvestSpec,
    ClosureWrapperRestoreExecutionManager,
    ClosureWrapperRestoreExecutionSpec,
    ClosureWrapperReplacementExecutionManager,
    ClosureWrapperReplacementExecutionSpec,
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
            if isinstance(expression, str) and "__rdgOriginal" in expression and "__reverseDeepAgentClosureWrappers" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "restored": True,
                        },
                        "description": "Object",
                    }
                }
            if isinstance(expression, str) and "__reverseDeepAgentClosureWrappers" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "wrapperInstalled": True,
                            "restoreExpressionAvailable": True,
                        },
                        "description": "Object",
                    }
                }
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

    def evaluate(self, expression):
        if "__reverseDeepAgentClosureWrappers" in expression:
            events = [
                {"marker": "marker-a", "functionName": "buildSign", "kind": "return", "argumentCount": 2},
                {"marker": "marker-b", "functionName": "otherSign", "kind": "throw", "argumentCount": 1},
            ]
            if "not_installed_marker" in expression:
                return {"ok": False, "reason": "not_installed", "events": [], "eventCount": 0}
            filtered = [event for event in events if event["functionName"] == "buildSign"]
            return {"ok": True, "events": filtered, "eventCount": len(filtered), "totalEventCount": len(events), "markerCount": 2}
        return {}


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
        self.assertTrue(payload["plan"]["replacement_feasibility"]["reviewed_executor_available"])
        self.assertEqual(payload["plan"]["replacement_feasibility"]["reviewed_executor_scope"], "same-process-retained-paused-session")
        self.assertIn("assignment_safety_not_proven", payload["plan"]["execution_blockers"])
        self.assertNotIn("reviewed_executor_not_implemented", payload["plan"]["execution_blockers"])
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


class ClosureWrapperAssignmentSafetyManagerTests(unittest.TestCase):
    @staticmethod
    def _ready_plan() -> dict:
        return ClosureWrapperReplacementPlanManager().plan(
            ClosureWrapperReplacementPlanSpec.from_context(
                {
                    "closure_function_candidates": [
                        {
                            "function_name": "buildSign",
                            "candidate_id": "closure:cf-closure-1:buildSign",
                            "hook_kind": "closure-scope",
                            "hook_supported": False,
                            "callframe_index": 0,
                            "callFrameId": "cf-closure-1",
                            "evidence_expression": "typeof buildSign",
                        }
                    ],
                    "candidate_id": "closure:cf-closure-1:buildSign",
                }
            )
        ).plan

    def test_proves_review_only_assignment_safety_from_replacement_plan(self) -> None:
        spec = ClosureWrapperAssignmentSafetySpec.from_context(
            {
                "prove_closure_wrapper_assignment_safety": True,
                "closure_wrapper_replacement_plan": self._ready_plan(),
            }
        )

        result = ClosureWrapperAssignmentSafetyManager().prove(spec)
        payload = result.to_dict()

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(payload["schema_version"], "reverse-deepagent.closure-wrapper-assignment-safety.v1")
        self.assertTrue(payload["assignment_safety"]["assignment_safety_proven"])
        self.assertTrue(payload["assignment_safety"]["safe_to_request_reviewed_execution"])
        self.assertFalse(payload["assignment_safety"]["runtime_mutability_proven"])
        self.assertFalse(payload["assignment_safety"]["runtime_mutability_probe_executed"])
        self.assertFalse(payload["assignment_safety"]["runtime_mutated"])
        self.assertFalse(payload["assignment_safety"]["cdp_command_sent"])
        self.assertFalse(payload["assignment_safety"]["callframe_evaluated"])
        self.assertEqual(payload["assignment_safety"]["function_name"], "buildSign")
        self.assertEqual(payload["assignment_safety"]["callFrameId"], "cf-closure-1")
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_assignment_safety_when_lexical_evidence_is_missing(self) -> None:
        plan = self._ready_plan()
        plan["selected_candidate"] = dict(plan["selected_candidate"], evidence_expression="typeof otherName")
        spec = ClosureWrapperAssignmentSafetySpec.from_context(
            {
                "prove_closure_wrapper_assignment_safety": True,
                "closure_wrapper_replacement_plan": plan,
            }
        )

        result = ClosureWrapperAssignmentSafetyManager().prove(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "lexical_binding_typeof_evidence_matches")
        self.assertFalse(result.assignment_safety["assignment_safety_proven"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])


class ClosureWrapperReplacementExecutionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def tearDown(self) -> None:
        BreakpointManager.clear_paused_sessions()

    @staticmethod
    def _ready_plan() -> dict:
        plan_spec = ClosureWrapperReplacementPlanSpec.from_context(
            {
                "closure_function_candidates": [
                    {
                        "function_name": "buildSign",
                        "candidate_id": "closure:cf-closure-1:buildSign",
                        "hook_kind": "closure-scope",
                        "hook_supported": False,
                        "callframe_index": 0,
                        "callFrameId": "cf-closure-1",
                        "evidence_expression": "typeof buildSign",
                    }
                ],
                "candidate_id": "closure:cf-closure-1:buildSign",
            }
        )
        result = ClosureWrapperReplacementPlanManager().plan(plan_spec)
        return result.plan

    @staticmethod
    def _assignment_safety(plan: dict) -> dict:
        return ClosureWrapperAssignmentSafetyManager().prove(
            ClosureWrapperAssignmentSafetySpec.from_context(
                {
                    "prove_closure_wrapper_assignment_safety": True,
                    "closure_wrapper_replacement_plan": plan,
                }
            )
        ).assignment_safety

    def _preserve_pause(self, session_id: str = "closure-exec-session") -> tuple[ClosureScopeCDPSession, ClosureScopePage]:
        session = ClosureScopeCDPSession()
        page = ClosureScopePage(session)
        spec = ClosureScopeDiscoverySpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 12,
                "closure_function_names": ["buildSign"],
                "trigger_expression": "debugger; 'scheduled'",
                "preserve_pause_state": True,
                "pause_session_id": session_id,
            }
        )
        result = ClosureScopeDiscoveryManager().discover(page, spec)
        self.assertEqual(result.status, "success")
        self.assertIn(session_id, BreakpointManager._paused_sessions)
        return session, page

    def test_blocks_without_review_approval_or_cdp_side_effects(self) -> None:
        session, page = self._preserve_pause()
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": self._ready_plan(),
                "closure_wrapper_assignment_safety": self._assignment_safety(self._ready_plan()),
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": False,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), 1)

    def test_executes_reviewed_wrapper_replacement_from_retained_pause(self) -> None:
        session, page = self._preserve_pause()
        plan = self._ready_plan()
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": plan,
                "closure_wrapper_assignment_safety": self._assignment_safety(plan),
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "applied")
        self.assertTrue(result.side_effect_policy["cdp_command_sent"])
        self.assertTrue(result.side_effect_policy["callframe_evaluated"])
        self.assertTrue(result.side_effect_policy["wrapper_installed"])
        self.assertTrue(result.side_effect_policy["runtime_mutated"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        self.assertEqual(result.execution["schema_version"], "reverse-deepagent.closure-wrapper-replacement-execution.v1")
        self.assertEqual(result.execution["function_name"], "buildSign")
        self.assertIn("restore_expression", result.execution["restore_plan"])
        eval_calls = [params for method, params in session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertGreaterEqual(len(eval_calls), 2)
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("buildSign =", eval_calls[-1]["expression"])
        self.assertIn("__reverseDeepAgentClosureWrappers", eval_calls[-1]["expression"])

    def test_blocks_execution_without_assignment_safety_proof(self) -> None:
        session, page = self._preserve_pause()
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": self._ready_plan(),
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "closure_wrapper_assignment_safety_proof_required")
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), 1)


class ClosureWrapperRestoreExecutionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def tearDown(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def _installed_wrapper(self) -> tuple[ClosureScopeCDPSession, ClosureScopePage, dict]:
        session = ClosureScopeCDPSession()
        page = ClosureScopePage(session)
        discovery_spec = ClosureScopeDiscoverySpec.from_context(
            {
                "url_pattern": ".*app\\.js$",
                "line_number": 12,
                "closure_function_names": ["buildSign"],
                "trigger_expression": "debugger; 'scheduled'",
                "preserve_pause_state": True,
                "pause_session_id": "closure-restore-session",
            }
        )
        discovery = ClosureScopeDiscoveryManager().discover(page, discovery_spec)
        self.assertEqual(discovery.status, "success")
        plan = ClosureWrapperReplacementPlanManager().plan(
            ClosureWrapperReplacementPlanSpec.from_context(
                {
                    "closure_function_candidates": discovery.candidates,
                    "candidate_id": "closure:cf-closure-1:buildSign",
                }
            )
        )
        install = ClosureWrapperReplacementExecutionManager().execute(
            page,
            ClosureWrapperReplacementExecutionSpec.from_context(
                {
                    "closure_wrapper_replacement_execution": True,
                    "closure_wrapper_replacement_plan": plan.plan,
                    "closure_wrapper_assignment_safety": ClosureWrapperAssignmentSafetyManager().prove(
                        ClosureWrapperAssignmentSafetySpec.from_context(
                            {
                                "prove_closure_wrapper_assignment_safety": True,
                                "closure_wrapper_replacement_plan": plan.plan,
                            }
                        )
                    ).assignment_safety,
                    "pause_session_id": "closure-restore-session",
                    "execute_closure_wrapper_replacement": True,
                    "review_approved": True,
                }
            ),
        )
        self.assertEqual(install.status, "applied")
        return session, page, install.execution["restore_plan"]

    def test_blocks_without_review_approval_or_cdp_side_effects(self) -> None:
        session, page, restore_plan = self._installed_wrapper()
        before = sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame")
        spec = ClosureWrapperRestoreExecutionSpec.from_context(
            {
                "closure_wrapper_restore_execution": True,
                "closure_wrapper_restore_plan": restore_plan,
                "pause_session_id": "closure-restore-session",
                "execute_closure_wrapper_restore": True,
            }
        )

        result = ClosureWrapperRestoreExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), before)
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])

    def test_executes_reviewed_restore_from_retained_pause(self) -> None:
        session, page, restore_plan = self._installed_wrapper()
        spec = ClosureWrapperRestoreExecutionSpec.from_context(
            {
                "closure_wrapper_restore_execution": True,
                "closure_wrapper_restore_plan": restore_plan,
                "pause_session_id": "closure-restore-session",
                "execute_closure_wrapper_restore": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperRestoreExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "restored")
        self.assertEqual(result.execution["schema_version"], "reverse-deepagent.closure-wrapper-restore-execution.v1")
        self.assertTrue(result.execution["wrapper_restored"])
        self.assertTrue(result.execution["runtime_mutated"])
        self.assertTrue(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        eval_calls = [params for method, params in session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("__rdgOriginal", eval_calls[-1]["expression"])
        self.assertIn("__reverseDeepAgentClosureWrappers", eval_calls[-1]["expression"])


class ClosureWrapperEventHarvestManagerTests(unittest.TestCase):
    def test_harvests_filtered_closure_wrapper_events_read_only(self) -> None:
        page = ClosureScopePage()
        spec = ClosureWrapperEventHarvestSpec.from_context({"closure_wrapper_events": True, "function_name": "buildSign"})

        result = ClosureWrapperEventHarvestManager().harvest(page, spec)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.event_count, 1)
        self.assertEqual(result.events[0]["functionName"], "buildSign")
        self.assertTrue(result.side_effect_policy["read_only"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_missing_event_store_is_partial_without_runtime_mutation(self) -> None:
        page = ClosureScopePage()
        spec = ClosureWrapperEventHarvestSpec.from_context({"closure_wrapper_events": True, "marker": "not_installed_marker"})

        result = ClosureWrapperEventHarvestManager().harvest(page, spec)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.reason, "not_installed")
        self.assertEqual(result.event_count, 0)
        self.assertFalse(result.side_effect_policy["runtime_mutated"])


if __name__ == "__main__":
    unittest.main()
