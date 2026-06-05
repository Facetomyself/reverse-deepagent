import unittest

from reverse_deepagent.browser.hooks import (
    BreakpointManager,
    ClosureScopeDiscoveryManager,
    ClosureScopeDiscoverySpec,
    ClosureWrapperAssignmentSafetyManager,
    ClosureWrapperAssignmentSafetySpec,
    ClosureWrapperContinuationCheckpointManager,
    ClosureWrapperContinuationCheckpointSpec,
    ClosureWrapperContinuationExecutionPlanManager,
    ClosureWrapperContinuationExecutionPlanSpec,
    ClosureWrapperContinuationExecutionManager,
    ClosureWrapperContinuationExecutionSpec,
    ClosureWrapperContinuationReadinessManager,
    ClosureWrapperContinuationReadinessSpec,
    ClosureWrapperEventHarvestManager,
    ClosureWrapperEventHarvestSpec,
    ClosureWrapperRuntimeMutabilityPreflightManager,
    ClosureWrapperRuntimeMutabilityPreflightSpec,
    ClosureWrapperRuntimeMutabilityResultManager,
    ClosureWrapperRuntimeMutabilityResultSpec,
    ClosureWrapperRestoreExecutionManager,
    ClosureWrapperRestoreExecutionSpec,
    ClosureWrapperReplacementExecutionManager,
    ClosureWrapperReplacementExecutionSpec,
    ClosureWrapperReplacementPlanManager,
    ClosureWrapperReplacementPlanSpec,
)
from reverse_deepagent.browser.hooks.closure_scope import closure_wrapper_strategy_descriptor


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
            if isinstance(expression, str) and "__reverseDeepAgentClosureMutabilityProbes" in expression:
                return {
                    "result": {
                        "type": "object",
                        "value": {
                            "ok": True,
                            "functionName": "buildSign",
                            "runtimeMutabilityProven": True,
                            "temporaryAssignmentConfirmed": True,
                            "originalRestored": True,
                            "wrapperInstalled": False,
                        },
                        "description": "Object",
                    }
                }
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
        self.assertEqual(payload["plan"]["wrapper_strategy_descriptor"]["strategy"], "log-only-call-through")
        self.assertTrue(payload["plan"]["wrapper_strategy_descriptor"]["supported_for_install"])
        self.assertFalse(payload["plan"]["wrapper_strategy_descriptor"]["strategy_plan_only"])
        self.assertTrue(payload["plan"]["replacement_feasibility"]["wrapper_strategy_supported_for_install"])
        self.assertTrue(payload["plan"]["replacement_feasibility"]["lexical_binding_proven"])
        self.assertTrue(payload["plan"]["replacement_feasibility"]["reviewed_executor_available"])
        self.assertEqual(payload["plan"]["replacement_feasibility"]["reviewed_executor_scope"], "same-process-retained-paused-session")
        self.assertIn("assignment_safety_not_proven", payload["plan"]["execution_blockers"])
        self.assertNotIn("reviewed_executor_not_implemented", payload["plan"]["execution_blockers"])
        self.assertEqual(payload["plan"]["next_action"], "review_closure_wrapper_replacement_plan_before_execution")
        self.assertTrue(payload["side_effect_policy"]["read_only"])
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["mobile_runtime_used"])

    def test_plans_descriptor_for_plan_only_wrapper_strategy_without_enabling_install(self) -> None:
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
                "wrapper_strategy": "arg-preview",
            }
        )

        result = ClosureWrapperReplacementPlanManager().plan(spec)
        payload = result.to_dict()

        self.assertEqual(result.status, "ready_for_review")
        descriptor = payload["plan"]["wrapper_strategy_descriptor"]
        self.assertEqual(descriptor["schema_version"], "reverse-deepagent.closure-wrapper-strategy.v1")
        self.assertEqual(descriptor["strategy"], "arg-preview")
        self.assertTrue(descriptor["supported_for_planning"])
        self.assertFalse(descriptor["supported_for_install"])
        self.assertTrue(descriptor["strategy_plan_only"])
        self.assertIn("wrapper_strategy_plan_only", payload["plan"]["execution_blockers"])
        self.assertIn("arg_preview_executor_not_implemented", payload["plan"]["execution_blockers"])
        self.assertFalse(payload["plan"]["replacement_feasibility"]["reviewed_executor_available"])
        self.assertTrue(payload["plan"]["replacement_feasibility"]["wrapper_strategy_plan_only"])
        self.assertFalse(payload["plan"]["automatic_wrapper_replacement"])
        self.assertFalse(payload["side_effect_policy"]["runtime_mutated"])

    def test_strategy_descriptor_reports_unknown_strategy_as_unsupported(self) -> None:
        descriptor = closure_wrapper_strategy_descriptor("unknown-preview")

        self.assertEqual(descriptor["strategy"], "unknown-preview")
        self.assertFalse(descriptor["known_strategy"])
        self.assertFalse(descriptor["supported_for_planning"])
        self.assertFalse(descriptor["supported_for_install"])
        self.assertIn("unsupported_wrapper_strategy", descriptor["install_blockers"])

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
        self.assertEqual(payload["assignment_safety"]["wrapper_strategy_descriptor"]["strategy"], "log-only-call-through")
        self.assertTrue(payload["assignment_safety"]["wrapper_strategy_descriptor"]["supported_for_install"])
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_assignment_safety_for_plan_only_strategy_descriptor(self) -> None:
        plan = ClosureWrapperReplacementPlanManager().plan(
            ClosureWrapperReplacementPlanSpec.from_context(
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
                    "wrapper_strategy": "return-preview",
                }
            )
        ).plan
        spec = ClosureWrapperAssignmentSafetySpec.from_context(
            {
                "prove_closure_wrapper_assignment_safety": True,
                "closure_wrapper_replacement_plan": plan,
            }
        )

        result = ClosureWrapperAssignmentSafetyManager().prove(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "wrapper_strategy_install_supported")
        self.assertFalse(result.assignment_safety["assignment_safety_proven"])
        self.assertEqual(result.assignment_safety["wrapper_strategy_descriptor"]["strategy"], "return-preview")
        self.assertTrue(result.assignment_safety["wrapper_strategy_descriptor"]["strategy_plan_only"])

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


class ClosureWrapperRuntimeMutabilityPreflightManagerTests(unittest.TestCase):
    @staticmethod
    def _assignment_safety() -> dict:
        plan = ClosureWrapperAssignmentSafetyManagerTests._ready_plan()
        return ClosureWrapperAssignmentSafetyManager().prove(
            ClosureWrapperAssignmentSafetySpec.from_context(
                {
                    "prove_closure_wrapper_assignment_safety": True,
                    "closure_wrapper_replacement_plan": plan,
                }
            )
        ).assignment_safety

    def test_preflights_runtime_mutability_probe_without_side_effects(self) -> None:
        spec = ClosureWrapperRuntimeMutabilityPreflightSpec.from_context(
            {
                "closure_wrapper_runtime_mutability_preflight": True,
                "closure_wrapper_assignment_safety": self._assignment_safety(),
                "pause_session_id": "closure-mutability-session",
            }
        )

        result = ClosureWrapperRuntimeMutabilityPreflightManager().preflight(spec)
        payload = result.to_dict()

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(payload["schema_version"], "reverse-deepagent.closure-wrapper-runtime-mutability-preflight.v1")
        self.assertTrue(payload["preflight"]["runtime_mutability_probe_ready_for_review"])
        self.assertFalse(payload["preflight"]["runtime_mutability_proven"])
        self.assertFalse(payload["preflight"]["runtime_mutability_probe_executed"])
        self.assertFalse(payload["preflight"]["runtime_mutated"])
        self.assertFalse(payload["preflight"]["cdp_command_sent"])
        self.assertFalse(payload["preflight"]["callframe_evaluated"])
        self.assertEqual(payload["preflight"]["function_name"], "buildSign")
        self.assertEqual(payload["preflight"]["expected_callframe_id"], "cf-closure-1")
        self.assertEqual(payload["preflight"]["wrapper_strategy_descriptor"]["strategy"], "log-only-call-through")
        self.assertTrue(payload["preflight"]["wrapper_strategy_descriptor"]["supported_for_install"])
        self.assertTrue(payload["preflight"]["probe_plan"]["requires_allow_side_effects_evaluation"])
        self.assertFalse(payload["side_effect_policy"]["calls_mcp"])
        self.assertFalse(payload["side_effect_policy"]["mobile_runtime_used"])

    def test_blocks_runtime_mutability_preflight_without_retained_pause(self) -> None:
        spec = ClosureWrapperRuntimeMutabilityPreflightSpec.from_context(
            {
                "closure_wrapper_runtime_mutability_preflight": True,
                "closure_wrapper_assignment_safety": self._assignment_safety(),
            }
        )

        result = ClosureWrapperRuntimeMutabilityPreflightManager().preflight(spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "same_process_pause_session_provided")
        self.assertFalse(result.preflight["runtime_mutability_probe_ready_for_review"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])




class ClosureWrapperRuntimeMutabilityResultManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def tearDown(self) -> None:
        BreakpointManager.clear_paused_sessions()

    @staticmethod
    def _preflight() -> dict:
        return ClosureWrapperRuntimeMutabilityPreflightManager().preflight(
            ClosureWrapperRuntimeMutabilityPreflightSpec.from_context(
                {
                    "closure_wrapper_runtime_mutability_preflight": True,
                    "closure_wrapper_assignment_safety": ClosureWrapperRuntimeMutabilityPreflightManagerTests._assignment_safety(),
                    "pause_session_id": "closure-mutability-result-session",
                }
            )
        ).preflight

    def _preserve_pause(self, session_id: str = "closure-mutability-result-session") -> tuple[ClosureScopeCDPSession, ClosureScopePage]:
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
        before = sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame")
        spec = ClosureWrapperRuntimeMutabilityResultSpec.from_context(
            {
                "closure_wrapper_runtime_mutability_result": True,
                "closure_wrapper_runtime_mutability_preflight": self._preflight(),
                "pause_session_id": "closure-mutability-result-session",
                "execute_closure_wrapper_runtime_mutability_probe": True,
            }
        )

        result = ClosureWrapperRuntimeMutabilityResultManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "review_approval_required")
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), before)
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertFalse(result.result["runtime_mutability_proven"])

    def test_executes_reviewed_runtime_mutability_probe_and_restores_original(self) -> None:
        session, page = self._preserve_pause()
        spec = ClosureWrapperRuntimeMutabilityResultSpec.from_context(
            {
                "closure_wrapper_runtime_mutability_result": True,
                "closure_wrapper_runtime_mutability_preflight": self._preflight(),
                "pause_session_id": "closure-mutability-result-session",
                "execute_closure_wrapper_runtime_mutability_probe": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperRuntimeMutabilityResultManager().execute(page, spec)

        self.assertEqual(result.status, "proven")
        self.assertEqual(result.result["schema_version"], "reverse-deepagent.closure-wrapper-runtime-mutability-result.v1")
        self.assertTrue(result.result["runtime_mutability_proven"])
        self.assertTrue(result.result["runtime_mutability_probe_executed"])
        self.assertTrue(result.result["temporary_assignment_confirmed"])
        self.assertTrue(result.result["original_restored"])
        self.assertEqual(result.result["wrapper_strategy_descriptor"]["strategy"], "log-only-call-through")
        self.assertTrue(result.result["wrapper_strategy_descriptor"]["supported_for_install"])
        self.assertFalse(result.result["wrapper_installed"])
        self.assertTrue(result.side_effect_policy["cdp_command_sent"])
        self.assertTrue(result.side_effect_policy["callframe_evaluated"])
        self.assertTrue(result.side_effect_policy["runtime_mutated"])
        self.assertFalse(result.side_effect_policy["wrapper_installed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])
        eval_calls = [params for method, params in session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("__reverseDeepAgentClosureMutabilityProbes", eval_calls[-1]["expression"])
        self.assertIn("buildSign = __rdgProbe", eval_calls[-1]["expression"])
        self.assertIn("buildSign = __rdgPrevious", eval_calls[-1]["expression"])

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

    @staticmethod
    def _runtime_mutability_result(plan: dict, *, session_id: str = "closure-exec-session") -> dict:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-result.v1",
            "status": "proven",
            "runtime_mutability_proven": True,
            "runtime_mutability_probe_executed": True,
            "temporary_assignment_confirmed": True,
            "original_restored": True,
            "wrapper_installed": False,
            "function_name": "buildSign",
            "expected_callframe_id": "cf-closure-1",
            "observed_callframe_id": "cf-closure-1",
            "pause_session_id": session_id,
            "wrapper_strategy": "log-only-call-through",
            "preflight": {
                "status": "ready_for_review",
                "selected_candidate": plan.get("selected_candidate"),
            },
        }

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
        self.assertEqual(result.execution["wrapper_strategy_descriptor"]["strategy"], "log-only-call-through")
        self.assertTrue(result.execution["wrapper_strategy_descriptor"]["supported_for_install"])
        self.assertIn("restore_expression", result.execution["restore_plan"])
        self.assertEqual(result.execution["restore_plan"]["wrapper_strategy"], "log-only-call-through")
        eval_calls = [params for method, params in session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertGreaterEqual(len(eval_calls), 2)
        self.assertFalse(eval_calls[-1]["throwOnSideEffect"])
        self.assertIn("buildSign =", eval_calls[-1]["expression"])
        self.assertIn("__reverseDeepAgentClosureWrappers", eval_calls[-1]["expression"])

    def test_blocks_replacement_when_required_runtime_mutability_result_is_missing(self) -> None:
        session, page = self._preserve_pause()
        plan = self._ready_plan()
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": plan,
                "closure_wrapper_assignment_safety": self._assignment_safety(plan),
                "require_closure_wrapper_runtime_mutability_result": True,
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "closure_wrapper_runtime_mutability_result_required")
        self.assertTrue(result.side_effect_policy["require_runtime_mutability_result"])
        self.assertFalse(result.side_effect_policy["runtime_mutability_result_proven"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertEqual(result.execution["next_action"], "execute_and_review_closure_wrapper_runtime_mutability_probe_before_replacement")
        self.assertEqual(sum(1 for method, _params in session.calls if method == "Debugger.evaluateOnCallFrame"), 1)

    def test_executes_replacement_when_required_runtime_mutability_result_matches(self) -> None:
        session, page = self._preserve_pause()
        plan = self._ready_plan()
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": plan,
                "closure_wrapper_assignment_safety": self._assignment_safety(plan),
                "closure_wrapper_runtime_mutability_result": self._runtime_mutability_result(plan),
                "require_closure_wrapper_runtime_mutability_result": True,
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "applied")
        self.assertTrue(result.side_effect_policy["require_runtime_mutability_result"])
        self.assertTrue(result.side_effect_policy["runtime_mutability_result_proven"])
        self.assertTrue(result.execution["runtime_mutability_result_proven"])
        self.assertTrue(result.execution["runtime_mutability_result"]["original_restored"])
        self.assertTrue(result.side_effect_policy["wrapper_installed"])
        eval_calls = [params for method, params in session.calls if method == "Debugger.evaluateOnCallFrame"]
        self.assertGreaterEqual(len(eval_calls), 2)

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

    def test_blocks_replacement_execution_for_plan_only_strategy_without_cdp_side_effects(self) -> None:
        session, page = self._preserve_pause()
        plan = self._ready_plan()
        plan["wrapper_strategy"] = "arg-preview"
        plan["wrapper_strategy_descriptor"] = closure_wrapper_strategy_descriptor("arg-preview")
        plan["replacement_feasibility"]["wrapper_strategy_supported_for_install"] = False
        plan["replacement_feasibility"]["wrapper_strategy_plan_only"] = True
        proof = dict(self._assignment_safety(self._ready_plan()), wrapper_strategy="arg-preview")
        spec = ClosureWrapperReplacementExecutionSpec.from_context(
            {
                "closure_wrapper_replacement_execution": True,
                "closure_wrapper_replacement_plan": plan,
                "closure_wrapper_assignment_safety": proof,
                "wrapper_strategy": "arg-preview",
                "pause_session_id": "closure-exec-session",
                "execute_closure_wrapper_replacement": True,
                "review_approved": True,
            }
        )

        result = ClosureWrapperReplacementExecutionManager().execute(page, spec)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "wrapper_strategy_install_not_supported")
        self.assertEqual(result.execution["wrapper_strategy_descriptor"]["strategy"], "arg-preview")
        self.assertTrue(result.execution["wrapper_strategy_descriptor"]["strategy_plan_only"])
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


class ClosureWrapperContinuationReadinessManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def tearDown(self) -> None:
        BreakpointManager.clear_paused_sessions()

    def _installed_wrapper(self) -> tuple[ClosureScopeCDPSession, ClosureScopePage, dict]:
        session = ClosureScopeCDPSession()
        page = ClosureScopePage(session)
        discovery = ClosureScopeDiscoveryManager().discover(
            page,
            ClosureScopeDiscoverySpec.from_context(
                {
                    "url_pattern": ".*app\\.js$",
                    "line_number": 12,
                    "closure_function_names": ["buildSign"],
                    "trigger_expression": "debugger; 'scheduled'",
                    "preserve_pause_state": True,
                    "pause_session_id": "closure-continuation-session",
                }
            ),
        )
        self.assertEqual(discovery.status, "success")
        plan = ClosureWrapperReplacementPlanManager().plan(
            ClosureWrapperReplacementPlanSpec.from_context(
                {
                    "closure_function_candidates": discovery.candidates,
                    "candidate_id": "closure:cf-closure-1:buildSign",
                }
            )
        )
        assignment = ClosureWrapperAssignmentSafetyManager().prove(
            ClosureWrapperAssignmentSafetySpec.from_context(
                {
                    "prove_closure_wrapper_assignment_safety": True,
                    "closure_wrapper_replacement_plan": plan.plan,
                }
            )
        )
        install = ClosureWrapperReplacementExecutionManager().execute(
            page,
            ClosureWrapperReplacementExecutionSpec.from_context(
                {
                    "closure_wrapper_replacement_execution": True,
                    "closure_wrapper_replacement_plan": plan.plan,
                    "closure_wrapper_assignment_safety": assignment.assignment_safety,
                    "pause_session_id": "closure-continuation-session",
                    "execute_closure_wrapper_replacement": True,
                    "review_approved": True,
                }
            ),
        )
        self.assertEqual(install.status, "applied")
        return session, page, install.execution

    def test_readiness_links_installed_wrapper_to_continuation_checkpoint_without_side_effects(self) -> None:
        session, _page, execution = self._installed_wrapper()
        before_calls = len(session.calls)
        spec = ClosureWrapperContinuationReadinessSpec.from_context(
            {
                "closure_wrapper_continuation_readiness": True,
                "closure_wrapper_replacement_execution": {"execution": execution},
                "closure_wrapper_events": {
                    "status": "success",
                    "event_count": 1,
                    "events": [{"marker": execution["marker"], "functionName": "buildSign"}],
                },
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "continuation_ready_for_next_action": True,
                        "pause_session_id": "pause-wrapper-continuation",
                        "selected_callframe_id": "live-cf-wrapper",
                    }
                },
            }
        )

        result = ClosureWrapperContinuationReadinessManager().review(spec)

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(len(session.calls), before_calls)
        readiness = result.readiness
        self.assertEqual(readiness["schema_version"], "reverse-deepagent.closure-wrapper-continuation-readiness.v1")
        self.assertTrue(readiness["ready_for_review"])
        self.assertTrue(readiness["same_process_wrapper_installed"])
        self.assertTrue(readiness["continuation_ready"])
        self.assertEqual(readiness["wrapper_event_count"], 1)
        self.assertFalse(readiness["cross_process_wrapper_execution_supported"])
        self.assertFalse(readiness["automatic_wrapper_continuation"])
        self.assertFalse(readiness["automatic_multi_step_loop"])
        self.assertEqual(readiness["next_action"], "review_wrapper_continuation_readiness")
        self.assertTrue(result.side_effect_policy["read_only"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["callframe_evaluated"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])
        self.assertFalse(result.side_effect_policy["wrapper_installed"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])

    def test_readiness_blocks_without_wrapper_execution_or_continuation_evidence(self) -> None:
        spec = ClosureWrapperContinuationReadinessSpec.from_context({"closure_wrapper_continuation_readiness": True})

        result = ClosureWrapperContinuationReadinessManager().review(spec)

        self.assertEqual(result.status, "blocked")
        self.assertIn("closure_wrapper_replacement_execution_required", result.readiness["blockers"])
        self.assertIn("paused_session_continuation_evidence_required", result.readiness["blockers"])
        self.assertEqual(result.readiness["next_action"], "install_reviewed_same_process_closure_wrapper")
        self.assertTrue(result.side_effect_policy["read_only"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["runtime_mutated"])


class ClosureWrapperContinuationExecutionPlanManagerTests(unittest.TestCase):
    def test_plans_wrapper_continuation_execution_review_without_side_effects(self) -> None:
        spec = ClosureWrapperContinuationExecutionPlanSpec.from_context(
            {
                "closure_wrapper_continuation_execution_plan": True,
                "reviewer": "unit-reviewer",
                "closure_wrapper_continuation_readiness": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "same_process_wrapper_installed": True,
                    "restore_plan_available": True,
                    "wrapper_strategy": "log-only-call-through",
                    "function_name": "buildSign",
                    "marker": "reverse-deepagent:closure-wrapper:buildSign",
                    "continuation_ready": True,
                    "wrapper_event_count": 2,
                },
                "paused_session_cross_process_session_lifecycle": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                },
                "paused_session_multi_step_loop_plan": {
                    "status": "ready_for_review",
                    "ready_for_review": True,
                    "readiness": {
                        "next_loop_iteration_reviewable": True,
                        "automatic_multi_step_loop_supported": False,
                    },
                    "next_iteration": {
                        "workflow_step_index": 1,
                        "method": "Debugger.stepOver",
                        "fingerprint": "loop-step-1",
                    },
                },
            }
        )

        result = ClosureWrapperContinuationExecutionPlanManager().plan(spec)
        payload = result.to_dict()
        plan = payload["plan"]
        policy = payload["side_effect_policy"]

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(payload["schema_version"], "reverse-deepagent.closure-wrapper-continuation-execution-plan.v1")
        self.assertTrue(plan["ready_for_review"])
        self.assertEqual(plan["reviewer"], "unit-reviewer")
        self.assertEqual(plan["wrapper_strategy"], "log-only-call-through")
        self.assertEqual(plan["function_name"], "buildSign")
        self.assertTrue(plan["same_process_wrapper_installed"])
        self.assertTrue(plan["restore_plan_available"])
        self.assertEqual(plan["wrapper_event_count"], 2)
        self.assertEqual(plan["source_statuses"]["multi_step_loop_plan"], "ready_for_review")
        self.assertEqual(plan["execution_strategy"]["mode"], "reviewed_plan_only")
        self.assertFalse(plan["execution_strategy"]["cross_process_wrapper_execution_supported"])
        self.assertFalse(plan["execution_strategy"]["automatic_wrapper_continuation_supported"])
        self.assertFalse(plan["execution_strategy"]["automatic_multi_step_loop_supported"])
        self.assertTrue(plan["review_gates"]["requires_explicit_execution_approval"])
        self.assertTrue(plan["review_gates"]["requires_restore_plan_before_execution"])
        self.assertEqual(plan["next_iteration"]["method"], "Debugger.stepOver")
        self.assertFalse(plan["next_iteration"]["would_execute"])
        self.assertEqual(plan["next_action"], "review_closure_wrapper_continuation_execution_plan")
        self.assertTrue(policy["read_only"])
        self.assertTrue(policy["review_only"])
        self.assertTrue(policy["plan_only"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["debugger_event_subscribed"])
        self.assertFalse(policy["paused_event_captured"])
        self.assertFalse(policy["callframe_evaluated"])
        self.assertFalse(policy["runtime_mutated"])
        self.assertFalse(policy["wrapper_installed"])
        self.assertFalse(policy["wrapper_restored"])
        self.assertFalse(policy["automatic_wrapper_continuation"])
        self.assertFalse(policy["automatic_multi_step_loop"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_blocks_without_readiness_or_paused_session_execution_path(self) -> None:
        spec = ClosureWrapperContinuationExecutionPlanSpec.from_context(
            {
                "closure_wrapper_continuation_execution_plan": True,
            }
        )

        result = ClosureWrapperContinuationExecutionPlanManager().plan(spec)
        plan = result.plan
        policy = result.side_effect_policy

        self.assertEqual(result.status, "blocked")
        self.assertIn("closure_wrapper_continuation_readiness_required", plan["blockers"])
        self.assertIn("paused_session_execution_path_required", plan["blockers"])
        self.assertEqual(plan["next_action"], "review_closure_wrapper_continuation_readiness")
        self.assertTrue(policy["read_only"])
        self.assertTrue(policy["plan_only"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["debugger_event_subscribed"])
        self.assertFalse(policy["callframe_evaluated"])
        self.assertFalse(policy["runtime_mutated"])
        self.assertFalse(policy["wrapper_installed"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])


class ClosureWrapperContinuationExecutionManagerTests(unittest.TestCase):
    def test_ready_for_review_without_executing_iteration(self) -> None:
        spec = ClosureWrapperContinuationExecutionSpec.from_context(
            {
                "closure_wrapper_continuation_execution": True,
                "closure_wrapper_continuation_execution_plan": {
                    "plan": {
                        "status": "ready_for_review",
                        "ready_for_review": True,
                        "plan_id": "wrapper-continuation-plan-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "same_process_wrapper_installed": True,
                        "restore_plan_available": True,
                        "execution_strategy": {
                            "supported_strategy": "log-only-call-through",
                            "automatic_wrapper_continuation_supported": False,
                            "automatic_multi_step_loop_supported": False,
                        },
                    }
                },
                "paused_session_multi_step_continuation_workflow": {
                    "workflow": {
                        "status": "ready_for_review",
                        "workflow_id": "wrapper-workflow-1",
                        "planned_steps": [
                            {"step_index": 1, "requested_action": "step_over", "method": "Debugger.stepOver", "fingerprint": "1:Debugger.stepOver:"}
                        ],
                        "duplicate_fingerprints": [],
                    }
                },
                "paused_session_live_callframe_recovery": {
                    "recovery": {
                        "status": "recovered",
                        "attached_session_id": "attached-session-1",
                        "live_callframe_id": "cf-live-1",
                        "live_callframe_recovered": True,
                    }
                },
                "attached_session_id": "attached-session-1",
                "live_callframe_id": "cf-live-1",
            }
        )

        result = ClosureWrapperContinuationExecutionManager().execute(None, spec)
        execution = result.execution
        policy = result.side_effect_policy

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(execution["schema_version"], "reverse-deepagent.closure-wrapper-continuation-execution.v1")
        self.assertEqual(execution["next_action"], "approve_closure_wrapper_continuation_iteration")
        self.assertEqual(execution["wrapper_strategy"], "log-only-call-through")
        self.assertFalse(execution["wrapper_continuation_iteration_executed"])
        self.assertFalse(execution["automatic_wrapper_continuation"])
        self.assertFalse(execution["automatic_multi_step_loop"])
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["runtime_mutated"])
        self.assertFalse(policy["wrapper_installed"])
        self.assertFalse(policy["wrapper_restored"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_blocks_without_plan_or_workflow(self) -> None:
        spec = ClosureWrapperContinuationExecutionSpec.from_context(
            {
                "closure_wrapper_continuation_execution": True,
            }
        )

        result = ClosureWrapperContinuationExecutionManager().execute(None, spec)
        execution = result.execution

        self.assertEqual(result.status, "blocked")
        self.assertIn("closure_wrapper_continuation_execution_plan_required", execution["blockers"])
        self.assertIn("multi_step_workflow_required", execution["blockers"])
        self.assertIn("live_callframe_recovery_required", execution["blockers"])
        self.assertEqual(execution["next_action"], "inspect_closure_wrapper_continuation_execution_blockers")
        self.assertTrue(result.side_effect_policy["read_only"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])


class ClosureWrapperContinuationCheckpointManagerTests(unittest.TestCase):
    def test_checkpoint_ready_after_events_and_paused_session_checkpoint(self) -> None:
        spec = ClosureWrapperContinuationCheckpointSpec.from_context(
            {
                "closure_wrapper_continuation_checkpoint": True,
                "closure_wrapper_continuation_execution": {
                    "execution": {
                        "status": "executed",
                        "plan_id": "wrapper-continuation-plan-1",
                        "workflow_id": "wrapper-workflow-1",
                        "wrapper_strategy": "log-only-call-through",
                        "function_name": "buildSign",
                        "selected_step_index": 1,
                        "selected_method": "Debugger.stepOver",
                        "wrapper_continuation_iteration_executed": True,
                        "paused_event_captured": True,
                        "post_execution_event_harvest_required": True,
                        "manual_checkpoint_required_after_step": True,
                        "automatic_wrapper_continuation": False,
                        "automatic_multi_step_loop": False,
                    }
                },
                "closure_wrapper_events": {"status": "success", "event_count": 1},
                "paused_session_cross_process_continuation_checkpoint": {
                    "checkpoint": {
                        "status": "ready_for_next_action_review",
                        "pause_session_id": "pause-1",
                        "target_id": "target-1",
                        "paused_event_captured": True,
                        "continuation_ready_for_next_action": True,
                        "live_callframe_recovered": True,
                    }
                },
                "paused_session_multi_step_loop_plan": {
                    "loop_plan": {
                        "next_iteration": {
                            "available": True,
                            "workflow_step_index": 2,
                            "method": "Debugger.stepOver",
                        }
                    }
                },
            }
        )

        result = ClosureWrapperContinuationCheckpointManager().checkpoint(spec)
        checkpoint = result.checkpoint
        policy = result.side_effect_policy

        self.assertEqual(result.status, "ready_for_review")
        self.assertEqual(checkpoint["schema_version"], "reverse-deepagent.closure-wrapper-continuation-checkpoint.v1")
        self.assertTrue(checkpoint["ready_for_review"])
        self.assertEqual(checkpoint["next_action"], "review_next_closure_wrapper_continuation_iteration")
        self.assertEqual(checkpoint["post_execution_event_count"], 1)
        self.assertTrue(checkpoint["paused_session_checkpoint_ready"])
        self.assertTrue(checkpoint["next_iteration_available"])
        self.assertFalse(policy["cdp_command_sent"])
        self.assertFalse(policy["runtime_mutated"])
        self.assertFalse(policy["wrapper_installed"])
        self.assertFalse(policy["wrapper_restored"])
        self.assertFalse(policy["wrapper_events_harvested"])
        self.assertFalse(policy["wrapper_continuation_iteration_executed"])
        self.assertFalse(policy["automatic_wrapper_continuation"])
        self.assertFalse(policy["automatic_multi_step_loop"])
        self.assertFalse(policy["calls_mcp"])
        self.assertFalse(policy["mobile_runtime_used"])

    def test_checkpoint_blocks_without_followup_events_or_checkpoint(self) -> None:
        spec = ClosureWrapperContinuationCheckpointSpec.from_context(
            {
                "closure_wrapper_continuation_checkpoint": True,
                "closure_wrapper_continuation_execution": {
                    "execution": {
                        "status": "executed",
                        "wrapper_continuation_iteration_executed": True,
                        "post_execution_event_harvest_required": True,
                        "manual_checkpoint_required_after_step": True,
                        "automatic_wrapper_continuation": False,
                        "automatic_multi_step_loop": False,
                    }
                },
            }
        )

        result = ClosureWrapperContinuationCheckpointManager().checkpoint(spec)
        checkpoint = result.checkpoint

        self.assertEqual(result.status, "blocked")
        self.assertIn("closure_wrapper_events_required", checkpoint["blockers"])
        self.assertIn("paused_session_continuation_checkpoint_required", checkpoint["blockers"])
        self.assertEqual(checkpoint["next_action"], "harvest_wrapper_events_after_reviewed_execution")
        self.assertTrue(result.side_effect_policy["read_only"])
        self.assertFalse(result.side_effect_policy["cdp_command_sent"])
        self.assertFalse(result.side_effect_policy["calls_mcp"])
        self.assertFalse(result.side_effect_policy["mobile_runtime_used"])


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
