from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager, BreakpointResult, BreakpointSpec, PausedSessionActionSpec


JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


@dataclass(slots=True)
class ClosureScopeDiscoverySpec:
    """Explicit paused-callframe closure scope discovery request.

    This is intentionally a discovery baseline rather than an automatic hook:
    JavaScript does not expose a safe generic way to enumerate lexical closure
    bindings. Callers provide candidate binding names, then the manager proves
    which names resolve to functions in a paused callframe with read-only CDP
    `Debugger.evaluateOnCallFrame` expressions.
    """

    url_pattern: str
    line_number: int = 0
    column_number: int | None = None
    trigger_expression: str | None = None
    wait_after_trigger_ms: int = 0
    callframe_index: int = 0
    candidate_names: list[str] = field(default_factory=list)
    preserve_pause_state: bool = False
    pause_session_id: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureScopeDiscoverySpec | None":
        context = context or {}
        url_pattern = context.get("url_pattern") or context.get("url") or context.get("script_url")
        if not url_pattern:
            return None
        candidate_names = cls._coerce_candidate_names(
            context.get(
                "closure_function_names",
                context.get(
                    "closureFunctionNames",
                    context.get(
                        "candidate_names",
                        context.get(
                            "candidateNames",
                            context.get(
                                "function_names",
                                context.get(
                                    "functionNames",
                                    context.get("function_name", context.get("functionName")),
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )
        query_name = context.get("closure_query", context.get("closureQuery", context.get("target_function", context.get("targetFunction"))))
        if query_name:
            for name in cls._coerce_candidate_names(query_name):
                if name not in candidate_names:
                    candidate_names.append(name)
        for function_name in cls._coerce_candidate_names(context.get("function_name", context.get("functionName"))):
            if function_name not in candidate_names:
                candidate_names.append(function_name)
        if not candidate_names:
            return None
        column_raw = context.get("column_number", context.get("columnNumber"))
        preserve_pause_state = bool(
            context.get(
                "preserve_pause_state",
                context.get("preservePauseState", context.get("keep_paused", context.get("keepPaused", False))),
            )
        )
        pause_session_id = context.get("pause_session_id", context.get("pauseSessionId"))
        return cls(
            url_pattern=str(url_pattern),
            line_number=int(context.get("line_number", context.get("lineNumber", 0)) or 0),
            column_number=None if column_raw is None else int(column_raw),
            trigger_expression=str(context.get("trigger_expression", context.get("triggerExpression"))) if context.get("trigger_expression", context.get("triggerExpression")) else None,
            wait_after_trigger_ms=int(context.get("wait_after_trigger_ms", context.get("waitAfterTriggerMs", 0)) or 0),
            callframe_index=int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0),
            candidate_names=candidate_names,
            preserve_pause_state=preserve_pause_state,
            pause_session_id=str(pause_session_id) if pause_session_id else None,
        )

    def to_breakpoint_spec(self) -> BreakpointSpec:
        return BreakpointSpec(
            url_pattern=self.url_pattern,
            line_number=self.line_number,
            column_number=self.column_number,
            trigger_expression=self.trigger_expression,
            wait_after_trigger_ms=self.wait_after_trigger_ms,
            auto_resume=not self.preserve_pause_state,
            callframe_evaluations=[f"typeof {name}" for name in self.candidate_names],
            callframe_index=self.callframe_index,
            callframe_evaluation_policy="read_only",
            preserve_pause_state=self.preserve_pause_state,
            pause_session_id=self.pause_session_id,
        )

    @staticmethod
    def _coerce_candidate_names(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = [item.strip() for item in value.split(",")]
        elif isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            raw = [str(item).strip() for item in value if item is not None]
        else:
            raw = []
        names: list[str] = []
        for item in raw:
            if JS_IDENTIFIER_RE.fullmatch(item) and item not in names:
                names.append(item)
        return names


@dataclass(slots=True)
class ClosureScopeDiscoveryResult:
    status: str
    supported: bool
    functions: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    breakpoint: dict[str, Any] = field(default_factory=dict)
    scope_summary: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "function_count": len(self.functions),
            "candidate_count": len(self.candidates),
            "functions": self.functions,
            "candidates": self.candidates,
            "breakpoint": self.breakpoint,
            "scope_summary": self.scope_summary,
            "trigger": self.trigger,
            "error": self.error,
            "reason": self.reason,
        }


class ClosureScopeDiscoveryManager:
    """Discover closure-scope function candidates from an explicit paused callframe."""

    def discover(self, page: BrowserPage, spec: ClosureScopeDiscoverySpec | None) -> ClosureScopeDiscoveryResult:
        if spec is None:
            return ClosureScopeDiscoveryResult(status="unsupported", supported=False, reason="missing_closure_scope_discovery_spec")
        breakpoint_result = BreakpointManager().set_breakpoint(page, spec.to_breakpoint_spec())
        scope_summary = self._scope_summary(breakpoint_result, spec)
        functions = self._functions_from_evaluations(breakpoint_result, spec)
        candidates = self._candidates_from_functions(functions, breakpoint_result, spec)
        if not breakpoint_result.supported:
            status = "unsupported"
        elif breakpoint_result.status == "failed":
            status = "failed"
        elif candidates:
            status = "success"
        else:
            status = "partial"
        return ClosureScopeDiscoveryResult(
            status=status,
            supported=breakpoint_result.supported,
            functions=functions,
            candidates=candidates,
            breakpoint=breakpoint_result.to_dict(),
            scope_summary=scope_summary,
            trigger=breakpoint_result.trigger,
            error=breakpoint_result.error,
            reason=breakpoint_result.reason,
        )

    @staticmethod
    def _scope_summary(result: BreakpointResult, spec: ClosureScopeDiscoverySpec) -> dict[str, Any]:
        selected = result.callframes[spec.callframe_index] if 0 <= spec.callframe_index < len(result.callframes) else {}
        return {
            "paused_status": result.paused.get("status") if isinstance(result.paused, dict) else "unknown",
            "callframe_count": len(result.callframes),
            "selected_callframe_index": spec.callframe_index,
            "selected_callframe_id": selected.get("callFrameId") if isinstance(selected, dict) else None,
            "selected_function_name": selected.get("functionName") if isinstance(selected, dict) else None,
            "scope_count": selected.get("scopeCount") if isinstance(selected, dict) else None,
            "candidate_names": list(spec.candidate_names),
        }

    @staticmethod
    def _functions_from_evaluations(result: BreakpointResult, spec: ClosureScopeDiscoverySpec) -> list[dict[str, Any]]:
        functions: list[dict[str, Any]] = []
        expression_to_name = {f"typeof {name}": name for name in spec.candidate_names}
        for evaluation in result.callframe_evaluations:
            if not isinstance(evaluation, dict):
                continue
            name = expression_to_name.get(str(evaluation.get("expression") or ""))
            if not name:
                continue
            value = evaluation.get("value")
            entry = {
                "name": name,
                "available": evaluation.get("ok") is True,
                "typeof": value,
                "is_function": evaluation.get("ok") is True and value == "function",
                "callframe_index": evaluation.get("callframe_index"),
                "callFrameId": evaluation.get("callFrameId"),
                "evidence_expression": evaluation.get("expression"),
                "policy": evaluation.get("policy"),
                "throw_on_side_effect": evaluation.get("throw_on_side_effect"),
                "error": evaluation.get("error"),
            }
            functions.append(entry)
        return functions

    @staticmethod
    def _candidates_from_functions(functions: list[dict[str, Any]], result: BreakpointResult, spec: ClosureScopeDiscoverySpec) -> list[dict[str, Any]]:
        selected = result.callframes[spec.callframe_index] if 0 <= spec.callframe_index < len(result.callframes) else {}
        candidates: list[dict[str, Any]] = []
        for function in functions:
            if not function.get("is_function"):
                continue
            name = str(function.get("name") or "")
            candidates.append(
                {
                    "function_name": name,
                    "candidate_id": f"closure:{function.get('callFrameId')}:{name}",
                    "hook_kind": "closure-scope",
                    "hook_supported": False,
                    "next_action": "use_source_logpoint_or_callframe_evaluation",
                    "callframe_index": function.get("callframe_index"),
                    "callFrameId": function.get("callFrameId"),
                    "enclosing_function": selected.get("functionName") if isinstance(selected, dict) else None,
                    "url": selected.get("url") if isinstance(selected, dict) else None,
                    "location": selected.get("location") if isinstance(selected, dict) else None,
                    "evidence_expression": function.get("evidence_expression"),
                }
            )
        return candidates


@dataclass(slots=True)
class ClosureWrapperReplacementPlanSpec:
    """Review-only wrapper replacement planning for closure-scope function candidates.

    This spec deliberately consumes already-collected closure-scope candidate
    evidence. It does not evaluate JavaScript, assign lexical bindings, install
    wrappers, or require a live paused callframe. The goal is to make the next
    human review checkpoint explicit before any future reviewed executor exists.
    """

    candidates: list[dict[str, Any]] = field(default_factory=list)
    candidate_id: str | None = None
    function_name: str | None = None
    callframe_id: str | None = None
    wrapper_strategy: str = "log-only-call-through"
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperReplacementPlanSpec | None":
        context = context or {}
        raw_candidates = (
            context.get("closure_function_candidates")
            or context.get("closureFunctionCandidates")
            or context.get("closure-function-candidates")
            or context.get("candidates")
        )
        if raw_candidates is None:
            raw_candidates = cls._candidates_from_payload(
                context.get("closure_scope_discovery")
                or context.get("closureScopeDiscovery")
                or context.get("closure_functions")
                or context.get("closureFunctions")
            )
        candidates = cls._coerce_candidates(raw_candidates)
        explicit_candidate = context.get("candidate")
        if isinstance(explicit_candidate, dict):
            candidates.insert(0, dict(explicit_candidate))
        wrapper_strategy = str(
            context.get("wrapper_strategy", context.get("wrapperStrategy", "log-only-call-through")) or "log-only-call-through"
        )
        return cls(
            candidates=candidates,
            candidate_id=_string_or_none(context.get("candidate_id", context.get("candidateId"))),
            function_name=_string_or_none(context.get("function_name", context.get("functionName"))),
            callframe_id=_string_or_none(context.get("callframe_id", context.get("callFrameId"))),
            wrapper_strategy=wrapper_strategy,
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )

    @staticmethod
    def _candidates_from_payload(value: Any) -> Any:
        if isinstance(value, dict):
            if isinstance(value.get("candidates"), list):
                return value["candidates"]
            if isinstance(value.get("candidate"), dict):
                return [value["candidate"]]
        return value

    @staticmethod
    def _coerce_candidates(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            value = value.get("candidates", [value])
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes, bytearray, dict)):
            return []
        candidates: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                candidates.append(dict(item))
        return candidates


@dataclass(slots=True)
class ClosureWrapperReplacementPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    candidate_count: int = 0
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-plan.v1",
            "status": self.status,
            "candidate_count": self.candidate_count,
            "selected_candidate": self.selected_candidate,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperReplacementPlanManager:
    """Build a review-only plan for future closure wrapper replacement."""

    def plan(self, spec: ClosureWrapperReplacementPlanSpec | None) -> ClosureWrapperReplacementPlanResult:
        policy = self._side_effect_policy()
        if spec is None:
            return self._blocked(
                status="unsupported",
                reason="missing_closure_wrapper_replacement_plan_spec",
                candidate_count=0,
                policy=policy,
                selected_candidate={},
            )
        candidate_count = len(spec.candidates)
        selected, reason = self._select_candidate(spec)
        if not spec.candidates:
            return self._blocked(
                status="blocked",
                reason="missing_closure_candidates",
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate={},
            )
        if not selected:
            return self._blocked(
                status="blocked",
                reason=reason or "missing_selected_candidate",
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate={},
            )
        validation_reason = self._candidate_blocker(selected)
        if validation_reason:
            return self._blocked(
                status="blocked",
                reason=validation_reason,
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate=selected,
            )
        plan = self._plan_payload(spec, selected, status="ready_for_review", reason=None, policy=policy)
        return ClosureWrapperReplacementPlanResult(
            status="ready_for_review",
            plan=plan,
            selected_candidate=selected,
            candidate_count=candidate_count,
            side_effect_policy=policy,
        )

    def _blocked(
        self,
        *,
        status: str,
        reason: str,
        candidate_count: int,
        policy: dict[str, Any],
        selected_candidate: dict[str, Any],
    ) -> ClosureWrapperReplacementPlanResult:
        spec = ClosureWrapperReplacementPlanSpec(candidates=[selected_candidate] if selected_candidate else [])
        plan = self._plan_payload(spec, selected_candidate, status=status, reason=reason, policy=policy)
        return ClosureWrapperReplacementPlanResult(
            status=status,
            plan=plan,
            selected_candidate=selected_candidate,
            candidate_count=candidate_count,
            side_effect_policy=policy,
            reason=reason,
        )

    @staticmethod
    def _select_candidate(spec: ClosureWrapperReplacementPlanSpec) -> tuple[dict[str, Any], str | None]:
        if not spec.candidates:
            return {}, "missing_closure_candidates"
        matches = list(spec.candidates)
        if spec.candidate_id:
            matches = [item for item in matches if str(item.get("candidate_id") or "") == spec.candidate_id]
        if spec.function_name:
            matches = [item for item in matches if str(item.get("function_name") or item.get("name") or "") == spec.function_name]
        if spec.callframe_id:
            matches = [item for item in matches if str(item.get("callFrameId") or item.get("callframe_id") or "") == spec.callframe_id]
        if len(matches) == 1:
            return dict(matches[0]), None
        if not matches:
            return {}, "selected_candidate_not_found"
        return {}, "ambiguous_closure_candidate_selection"

    @staticmethod
    def _candidate_blocker(candidate: dict[str, Any]) -> str | None:
        if str(candidate.get("hook_kind") or "") != "closure-scope":
            return "candidate_not_closure_scope"
        if not str(candidate.get("function_name") or candidate.get("name") or ""):
            return "missing_closure_function_name"
        if not str(candidate.get("callFrameId") or candidate.get("callframe_id") or ""):
            return "callframe_id_not_stable"
        if candidate.get("is_function") is False:
            return "candidate_not_function"
        return None

    def _plan_payload(
        self,
        spec: ClosureWrapperReplacementPlanSpec,
        candidate: dict[str, Any],
        *,
        status: str,
        reason: str | None,
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        function_name = str(candidate.get("function_name") or candidate.get("name") or "")
        callframe_id = str(candidate.get("callFrameId") or candidate.get("callframe_id") or "")
        evidence_expression = str(candidate.get("evidence_expression") or "")
        lexical_binding_proven = bool(function_name and evidence_expression == f"typeof {function_name}")
        execution_blockers = [
            "assignment_safety_not_proven",
            "review_approval_required",
            "same_process_retained_pause_required",
            "automatic_replacement_not_supported",
        ]
        if status != "ready_for_review" and reason:
            execution_blockers.insert(0, reason)
        feasibility = {
            "candidate_has_stable_callframe": bool(callframe_id),
            "lexical_binding_proven": lexical_binding_proven,
            "assignment_safety_proven": False,
            "restore_plan_available": False,
            "restore_plan_available_after_execution": True,
            "reviewed_executor_available": True,
            "reviewed_executor_scope": "same-process-retained-paused-session",
            "automatic_replacement_supported": False,
            "reason": reason or "review_required_before_any_future_wrapper_replacement",
        }
        review_steps = [
            "review_closure_candidate_origin_and_scope_chain",
            "prove_assignment_safety_with_explicit_side_effect_audit",
            "preserve_same_process_pause_session_for_reviewed_execution",
            "approve_log_only_call_through_wrapper_payload",
            "run_reviewed_executor_only_after_explicit_approval",
            "review_generated_restore_plan_after_execution",
        ]
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-plan.v1",
            "status": status,
            "plan_id": "closure-wrapper-replacement-plan",
            "plan_only": True,
            "requires_review": True,
            "automatic_wrapper_replacement": False,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "wrapper_strategy": spec.wrapper_strategy,
            "reviewer_note": spec.reviewer_note,
            "selected_candidate": candidate,
            "replacement_feasibility": feasibility,
            "execution_blockers": execution_blockers,
            "review_steps": review_steps,
            "next_action": self._next_action(status, reason),
            "side_effect_policy": policy,
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "ready_for_review":
            return "review_closure_wrapper_replacement_plan_before_execution"
        if reason == "ambiguous_closure_candidate_selection":
            return "select_one_closure_candidate_before_wrapper_planning"
        if reason == "missing_closure_candidates":
            return "run_closure_scope_discovery_before_wrapper_planning"
        return "resolve_closure_wrapper_replacement_plan_blockers"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperReplacementExecutionSpec:
    """Explicit reviewed execution request for a closure wrapper replacement plan.

    This is intentionally narrow and same-process only. It consumes a previously
    reviewed `closure-wrapper-replacement-plan`, then delegates the actual CDP
    `Debugger.evaluateOnCallFrame` call to `BreakpointManager` so the existing
    paused-session policy, mutation audit, and continuation preflight stay in one
    place.
    """

    plan: dict[str, Any] = field(default_factory=dict)
    pause_session_id: str | None = None
    callframe_index: int = 0
    expected_callframe_id: str | None = None
    candidate_id: str | None = None
    function_name: str | None = None
    wrapper_strategy: str = "log-only-call-through"
    review_approved: bool = False
    execute: bool = False
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperReplacementExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_replacement_execution")
            or context.get("closureWrapperReplacementExecution")
            or context.get("execute_closure_wrapper_replacement")
            or context.get("executeClosureWrapperReplacement")
            or context.get("reviewed_closure_wrapper_replacement")
            or context.get("reviewedClosureWrapperReplacement")
        )
        raw_plan = (
            context.get("closure_wrapper_replacement_plan")
            or context.get("closureWrapperReplacementPlan")
            or context.get("closure-wrapper-replacement-plan")
            or context.get("plan")
        )
        plan = cls._coerce_plan(raw_plan)
        if not requested and not plan:
            return None
        selected_candidate = cls._selected_candidate(plan)
        callframe_index_raw = context.get("callframe_index", context.get("callFrameIndex"))
        if callframe_index_raw is None:
            callframe_index_raw = selected_candidate.get("callframe_index", selected_candidate.get("callFrameIndex", 0))
        strategy = str(
            context.get(
                "wrapper_strategy",
                context.get("wrapperStrategy", plan.get("wrapper_strategy", "log-only-call-through")),
            )
            or "log-only-call-through"
        )
        return cls(
            plan=plan,
            pause_session_id=_string_or_none(
                context.get(
                    "pause_session_id",
                    context.get("pauseSessionId", context.get("debugger_session_id", context.get("debuggerSessionId"))),
                )
            ),
            callframe_index=int(callframe_index_raw or 0),
            expected_callframe_id=_string_or_none(
                context.get(
                    "expected_callframe_id",
                    context.get(
                        "expectedCallFrameId",
                        context.get("callframe_id", context.get("callFrameId", selected_candidate.get("callFrameId"))),
                    ),
                )
            ),
            candidate_id=_string_or_none(context.get("candidate_id", context.get("candidateId", selected_candidate.get("candidate_id")))),
            function_name=_string_or_none(
                context.get("function_name", context.get("functionName", selected_candidate.get("function_name", selected_candidate.get("name"))))
            ),
            wrapper_strategy=strategy,
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            execute=bool(context.get("execute_closure_wrapper_replacement", context.get("executeClosureWrapperReplacement", requested))),
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )

    @staticmethod
    def _coerce_plan(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("plan"), dict):
            return dict(value["plan"])
        return dict(value)

    @staticmethod
    def _selected_candidate(plan: dict[str, Any]) -> dict[str, Any]:
        candidate = plan.get("selected_candidate")
        return dict(candidate) if isinstance(candidate, dict) else {}


@dataclass(slots=True)
class ClosureWrapperReplacementExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    callframe_evaluations: list[dict[str, Any]] = field(default_factory=list)
    mutation_audit: list[dict[str, Any]] = field(default_factory=list)
    continuation_preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-execution.v1",
            "status": self.status,
            "execution": self.execution,
            "selected_candidate": self.selected_candidate,
            "callframe_evaluations": self.callframe_evaluations,
            "mutation_audit": self.mutation_audit,
            "continuation_preflight": self.continuation_preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperReplacementExecutionManager:
    """Run one explicitly reviewed closure wrapper replacement from a retained pause."""

    SUPPORTED_STRATEGIES = {"log-only-call-through"}

    def execute(self, page: BrowserPage, spec: ClosureWrapperReplacementExecutionSpec | None) -> ClosureWrapperReplacementExecutionResult:
        if spec is None:
            return self._blocked("unsupported", "missing_closure_wrapper_replacement_execution_spec", spec=None)
        selected_candidate = ClosureWrapperReplacementExecutionSpec._selected_candidate(spec.plan)
        reason = self._blocker(spec, selected_candidate)
        if reason:
            return self._blocked("blocked", reason, spec=spec, selected_candidate=selected_candidate)
        function_name = str(spec.function_name or selected_candidate.get("function_name") or selected_candidate.get("name") or "")
        marker = self._marker(spec, selected_candidate, function_name)
        expression = self._install_expression(function_name=function_name, marker=marker)
        action_spec = PausedSessionActionSpec(
            pause_session_id=str(spec.pause_session_id),
            action="evaluate",
            callframe_evaluations=[expression],
            callframe_index=spec.callframe_index,
            callframe_evaluation_policy="allow_side_effects",
            debugger_actions=[],
        )
        breakpoint_result = BreakpointManager().run_paused_session_action(page, action_spec)
        evaluation = breakpoint_result.callframe_evaluations[0] if breakpoint_result.callframe_evaluations else {}
        post_reason = self._post_execution_reason(spec, evaluation)
        status = "applied" if breakpoint_result.status == "success" and post_reason is None else "failed"
        side_effect_policy = self._side_effect_policy(
            spec=spec,
            cdp_command_sent=bool(breakpoint_result.callframe_evaluations),
            callframe_evaluated=bool(breakpoint_result.callframe_evaluations),
            runtime_mutated=status == "applied",
            wrapper_installed=status == "applied",
        )
        execution = self._execution_payload(
            spec=spec,
            candidate=selected_candidate,
            function_name=function_name,
            marker=marker,
            expression=expression,
            evaluation=evaluation,
            status=status,
            reason=post_reason or breakpoint_result.reason,
            side_effect_policy=side_effect_policy,
        )
        return ClosureWrapperReplacementExecutionResult(
            status=status,
            execution=execution,
            selected_candidate=selected_candidate,
            callframe_evaluations=list(breakpoint_result.callframe_evaluations),
            mutation_audit=list(breakpoint_result.mutation_audit),
            continuation_preflight=dict(breakpoint_result.continuation_preflight),
            side_effect_policy=side_effect_policy,
            reason=post_reason or breakpoint_result.reason,
            error=breakpoint_result.error,
        )

    def _blocked(
        self,
        status: str,
        reason: str,
        *,
        spec: ClosureWrapperReplacementExecutionSpec | None,
        selected_candidate: dict[str, Any] | None = None,
    ) -> ClosureWrapperReplacementExecutionResult:
        candidate = selected_candidate if isinstance(selected_candidate, dict) else {}
        side_effect_policy = self._side_effect_policy(spec=spec, cdp_command_sent=False, callframe_evaluated=False, runtime_mutated=False, wrapper_installed=False)
        execution = {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-replacement-execution",
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "selected_candidate": candidate,
            "wrapper_strategy": spec.wrapper_strategy if spec else None,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "restore_plan": {},
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }
        return ClosureWrapperReplacementExecutionResult(
            status=status,
            execution=execution,
            selected_candidate=candidate,
            side_effect_policy=side_effect_policy,
            reason=reason,
        )

    @classmethod
    def _blocker(cls, spec: ClosureWrapperReplacementExecutionSpec, candidate: dict[str, Any]) -> str | None:
        if not spec.plan:
            return "missing_closure_wrapper_replacement_plan"
        if str(spec.plan.get("status") or "") != "ready_for_review":
            return "closure_wrapper_replacement_plan_not_ready"
        if not spec.execute:
            return "execute_closure_wrapper_replacement_flag_required"
        if not spec.review_approved:
            return "review_approval_required"
        if not spec.pause_session_id:
            return "pause_session_id_required"
        if spec.wrapper_strategy not in cls.SUPPORTED_STRATEGIES:
            return "unsupported_wrapper_strategy"
        if not candidate:
            return "missing_selected_candidate"
        if str(candidate.get("hook_kind") or "") != "closure-scope":
            return "candidate_not_closure_scope"
        function_name = str(spec.function_name or candidate.get("function_name") or candidate.get("name") or "")
        if not JS_IDENTIFIER_RE.fullmatch(function_name):
            return "missing_or_unsafe_closure_function_name"
        expected_callframe_id = str(spec.expected_callframe_id or candidate.get("callFrameId") or "")
        if not expected_callframe_id:
            return "callframe_id_not_stable"
        feasibility = spec.plan.get("replacement_feasibility") if isinstance(spec.plan.get("replacement_feasibility"), dict) else {}
        if feasibility.get("lexical_binding_proven") is False:
            return "lexical_binding_not_proven"
        return None

    @staticmethod
    def _post_execution_reason(spec: ClosureWrapperReplacementExecutionSpec, evaluation: dict[str, Any]) -> str | None:
        if not evaluation:
            return "missing_callframe_evaluation_result"
        if not evaluation.get("ok"):
            return str(evaluation.get("error") or "callframe_evaluation_failed")
        expected_callframe_id = str(spec.expected_callframe_id or "")
        observed_callframe_id = str(evaluation.get("callFrameId") or "")
        if expected_callframe_id and observed_callframe_id and expected_callframe_id != observed_callframe_id:
            return "callframe_id_mismatch"
        value = evaluation.get("value")
        if isinstance(value, dict):
            if value.get("ok") is False:
                return str(value.get("reason") or "wrapper_install_result_not_ok")
            if value.get("wrapperInstalled") is False:
                return "wrapper_install_not_confirmed"
        return None

    @staticmethod
    def _marker(spec: ClosureWrapperReplacementExecutionSpec, candidate: dict[str, Any], function_name: str) -> str:
        raw = spec.candidate_id or str(candidate.get("candidate_id") or function_name)
        safe = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("._:") or function_name
        return f"reverse-deepagent:closure-wrapper:{safe}"

    @staticmethod
    def _install_expression(*, function_name: str, marker: str) -> str:
        function_literal = json.dumps(function_name)
        marker_literal = json.dumps(marker)
        return f"""(() => {{
  const __rdgName = {function_literal};
  const __rdgMarker = {marker_literal};
  const __rdgPrevious = {function_name};
  if (typeof __rdgPrevious !== "function") {{
    return {{ ok: false, reason: "target_not_function", functionName: __rdgName, previousType: typeof __rdgPrevious }};
  }}
  const __rdgRoot = globalThis.__reverseDeepAgentClosureWrappers || (globalThis.__reverseDeepAgentClosureWrappers = {{ events: [], originals: {{}} }});
  if (!__rdgRoot.originals[__rdgMarker]) __rdgRoot.originals[__rdgMarker] = __rdgPrevious;
  const __rdgWrapper = function(...args) {{
    const __rdgStartedAt = Date.now();
    try {{
      const __rdgResult = __rdgPrevious.apply(this, args);
      __rdgRoot.events.push({{
        marker: __rdgMarker,
        functionName: __rdgName,
        kind: "return",
        argumentCount: args.length,
        resultType: typeof __rdgResult,
        startedAt: __rdgStartedAt,
        endedAt: Date.now()
      }});
      return __rdgResult;
    }} catch (__rdgError) {{
      __rdgRoot.events.push({{
        marker: __rdgMarker,
        functionName: __rdgName,
        kind: "throw",
        argumentCount: args.length,
        errorName: __rdgError && __rdgError.name,
        startedAt: __rdgStartedAt,
        endedAt: Date.now()
      }});
      throw __rdgError;
    }}
  }};
  try {{
    Object.defineProperty(__rdgWrapper, "__reverseDeepAgentOriginal", {{ value: __rdgPrevious }});
    Object.defineProperty(__rdgWrapper, "__reverseDeepAgentMarker", {{ value: __rdgMarker }});
  }} catch (__rdgDefineError) {{}}
  {function_name} = __rdgWrapper;
  return {{
    ok: typeof {function_name} === "function",
    marker: __rdgMarker,
    functionName: __rdgName,
    previousType: typeof __rdgPrevious,
    wrapperInstalled: typeof {function_name} === "function" && {function_name}.__reverseDeepAgentMarker === __rdgMarker,
    restoreExpressionAvailable: true,
    eventRootAvailable: !!globalThis.__reverseDeepAgentClosureWrappers
  }};
}})()"""

    @staticmethod
    def _restore_expression(*, function_name: str, marker: str) -> str:
        marker_literal = json.dumps(marker)
        return f"""(() => {{
  const __rdgMarker = {marker_literal};
  const __rdgRoot = globalThis.__reverseDeepAgentClosureWrappers;
  const __rdgOriginal = (__rdgRoot && __rdgRoot.originals && __rdgRoot.originals[__rdgMarker]) || ({function_name} && {function_name}.__reverseDeepAgentOriginal);
  if (typeof __rdgOriginal !== "function") return {{ ok: false, reason: "original_not_found", marker: __rdgMarker }};
  {function_name} = __rdgOriginal;
  return {{ ok: {function_name} === __rdgOriginal, marker: __rdgMarker, functionName: {json.dumps(function_name)}, restored: {function_name} === __rdgOriginal }};
}})()"""

    def _execution_payload(
        self,
        *,
        spec: ClosureWrapperReplacementExecutionSpec,
        candidate: dict[str, Any],
        function_name: str,
        marker: str,
        expression: str,
        evaluation: dict[str, Any],
        status: str,
        reason: str | None,
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-replacement-execution",
            "requires_review": True,
            "review_approved": spec.review_approved,
            "execute_requested": spec.execute,
            "wrapper_strategy": spec.wrapper_strategy,
            "selected_candidate": candidate,
            "pause_session_id": spec.pause_session_id,
            "callframe_index": spec.callframe_index,
            "expected_callframe_id": spec.expected_callframe_id,
            "observed_callframe_id": evaluation.get("callFrameId"),
            "function_name": function_name,
            "marker": marker,
            "wrapper_installed": status == "applied",
            "runtime_mutated": status == "applied",
            "cdp_command_sent": True,
            "callframe_evaluated": True,
            "assignment_expression": expression,
            "restore_plan": {
                "available": True,
                "requires_review": True,
                "function_name": function_name,
                "marker": marker,
                "restore_expression": self._restore_expression(function_name=function_name, marker=marker),
                "next_action": "review_restore_expression_before_uninstalling_closure_wrapper",
            },
            "evaluation_summary": {
                "ok": evaluation.get("ok"),
                "valueType": evaluation.get("valueType"),
                "side_effect_risk": evaluation.get("side_effect_risk"),
                "policy": evaluation.get("policy"),
                "throw_on_side_effect": evaluation.get("throw_on_side_effect"),
                "blocked": evaluation.get("blocked", False),
                "error": evaluation.get("error"),
            },
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "applied":
            return "invoke_target_flow_and_review_closure_wrapper_events_or_restore"
        if reason == "review_approval_required":
            return "approve_closure_wrapper_replacement_execution_before_retry"
        if reason == "pause_session_id_required":
            return "reproduce_pause_and_preserve_same_process_session"
        if reason in {"missing_closure_wrapper_replacement_plan", "closure_wrapper_replacement_plan_not_ready"}:
            return "prepare_ready_closure_wrapper_replacement_plan_before_execution"
        return "resolve_closure_wrapper_replacement_execution_blockers"

    @staticmethod
    def _side_effect_policy(
        *,
        spec: ClosureWrapperReplacementExecutionSpec | None,
        cdp_command_sent: bool,
        callframe_evaluated: bool,
        runtime_mutated: bool,
        wrapper_installed: bool,
    ) -> dict[str, Any]:
        return {
            "read_only": False,
            "plan_only": False,
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_command_sent,
            "callframe_evaluated": callframe_evaluated,
            "wrapper_installed": wrapper_installed,
            "runtime_mutated": runtime_mutated,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperRestoreExecutionSpec:
    """Explicit reviewed restore request for a previously installed closure wrapper."""

    restore_plan: dict[str, Any] = field(default_factory=dict)
    pause_session_id: str | None = None
    callframe_index: int = 0
    expected_callframe_id: str | None = None
    function_name: str | None = None
    marker: str | None = None
    review_approved: bool = False
    execute: bool = False
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperRestoreExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_restore_execution")
            or context.get("closureWrapperRestoreExecution")
            or context.get("execute_closure_wrapper_restore")
            or context.get("executeClosureWrapperRestore")
            or context.get("reviewed_closure_wrapper_restore")
            or context.get("reviewedClosureWrapperRestore")
        )
        raw_plan = (
            context.get("closure_wrapper_restore_plan")
            or context.get("closureWrapperRestorePlan")
            or context.get("closure-wrapper-restore-plan")
            or context.get("restore_plan")
            or context.get("restorePlan")
            or context.get("closure_wrapper_replacement_execution")
            or context.get("closureWrapperReplacementExecution")
        )
        restore_plan = cls._coerce_restore_plan(raw_plan)
        if not requested and not restore_plan:
            return None
        return cls(
            restore_plan=restore_plan,
            pause_session_id=_string_or_none(
                context.get(
                    "pause_session_id",
                    context.get("pauseSessionId", context.get("debugger_session_id", context.get("debuggerSessionId"))),
                )
            ),
            callframe_index=int(context.get("callframe_index", context.get("callFrameIndex", 0)) or 0),
            expected_callframe_id=_string_or_none(
                context.get(
                    "expected_callframe_id",
                    context.get("expectedCallFrameId", context.get("callframe_id", context.get("callFrameId"))),
                )
            ),
            function_name=_string_or_none(context.get("function_name", context.get("functionName", restore_plan.get("function_name")))),
            marker=_string_or_none(context.get("marker", restore_plan.get("marker"))),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            execute=bool(context.get("execute_closure_wrapper_restore", context.get("executeClosureWrapperRestore", requested))),
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )

    @staticmethod
    def _coerce_restore_plan(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("execution"), dict) and isinstance(value["execution"].get("restore_plan"), dict):
            plan = dict(value["execution"]["restore_plan"])
            if value["execution"].get("function_name") and "function_name" not in plan:
                plan["function_name"] = value["execution"].get("function_name")
            if value["execution"].get("marker") and "marker" not in plan:
                plan["marker"] = value["execution"].get("marker")
            return plan
        if isinstance(value.get("restore_plan"), dict):
            plan = dict(value["restore_plan"])
            if value.get("function_name") and "function_name" not in plan:
                plan["function_name"] = value.get("function_name")
            if value.get("marker") and "marker" not in plan:
                plan["marker"] = value.get("marker")
            return plan
        return dict(value)


@dataclass(slots=True)
class ClosureWrapperRestoreExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    callframe_evaluations: list[dict[str, Any]] = field(default_factory=list)
    mutation_audit: list[dict[str, Any]] = field(default_factory=list)
    continuation_preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-restore-execution.v1",
            "status": self.status,
            "execution": self.execution,
            "callframe_evaluations": self.callframe_evaluations,
            "mutation_audit": self.mutation_audit,
            "continuation_preflight": self.continuation_preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperRestoreExecutionManager:
    """Run one explicitly reviewed closure wrapper restore from a retained pause."""

    def execute(self, page: BrowserPage, spec: ClosureWrapperRestoreExecutionSpec | None) -> ClosureWrapperRestoreExecutionResult:
        if spec is None:
            return self._blocked("unsupported", "missing_closure_wrapper_restore_execution_spec", spec=None)
        reason = self._blocker(spec)
        if reason:
            return self._blocked("blocked", reason, spec=spec)
        expression = str(spec.restore_plan.get("restore_expression") or "")
        action_spec = PausedSessionActionSpec(
            pause_session_id=str(spec.pause_session_id),
            action="evaluate",
            callframe_evaluations=[expression],
            callframe_index=spec.callframe_index,
            callframe_evaluation_policy="allow_side_effects",
            debugger_actions=[],
        )
        breakpoint_result = BreakpointManager().run_paused_session_action(page, action_spec)
        evaluation = breakpoint_result.callframe_evaluations[0] if breakpoint_result.callframe_evaluations else {}
        post_reason = self._post_execution_reason(spec, evaluation)
        status = "restored" if breakpoint_result.status == "success" and post_reason is None else "failed"
        side_effect_policy = self._side_effect_policy(
            spec=spec,
            cdp_command_sent=bool(breakpoint_result.callframe_evaluations),
            callframe_evaluated=bool(breakpoint_result.callframe_evaluations),
            runtime_mutated=status == "restored",
            wrapper_restored=status == "restored",
        )
        execution = self._execution_payload(
            spec=spec,
            expression=expression,
            evaluation=evaluation,
            status=status,
            reason=post_reason or breakpoint_result.reason,
            side_effect_policy=side_effect_policy,
        )
        return ClosureWrapperRestoreExecutionResult(
            status=status,
            execution=execution,
            callframe_evaluations=list(breakpoint_result.callframe_evaluations),
            mutation_audit=list(breakpoint_result.mutation_audit),
            continuation_preflight=dict(breakpoint_result.continuation_preflight),
            side_effect_policy=side_effect_policy,
            reason=post_reason or breakpoint_result.reason,
            error=breakpoint_result.error,
        )

    def _blocked(
        self,
        status: str,
        reason: str,
        *,
        spec: ClosureWrapperRestoreExecutionSpec | None,
    ) -> ClosureWrapperRestoreExecutionResult:
        side_effect_policy = self._side_effect_policy(spec=spec, cdp_command_sent=False, callframe_evaluated=False, runtime_mutated=False, wrapper_restored=False)
        execution = {
            "schema_version": "reverse-deepagent.closure-wrapper-restore-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-restore-execution",
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "restore_plan": dict(spec.restore_plan) if spec else {},
            "function_name": spec.function_name if spec else None,
            "marker": spec.marker if spec else None,
            "wrapper_restored": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }
        return ClosureWrapperRestoreExecutionResult(status=status, execution=execution, side_effect_policy=side_effect_policy, reason=reason)

    @classmethod
    def _blocker(cls, spec: ClosureWrapperRestoreExecutionSpec) -> str | None:
        if not spec.restore_plan:
            return "missing_closure_wrapper_restore_plan"
        if not spec.execute:
            return "execute_closure_wrapper_restore_flag_required"
        if not spec.review_approved:
            return "review_approval_required"
        if not spec.pause_session_id:
            return "pause_session_id_required"
        if spec.restore_plan.get("available") is False:
            return "closure_wrapper_restore_plan_not_available"
        expression = str(spec.restore_plan.get("restore_expression") or "")
        if not expression:
            return "missing_restore_expression"
        function_name = str(spec.function_name or spec.restore_plan.get("function_name") or "")
        if not JS_IDENTIFIER_RE.fullmatch(function_name):
            return "missing_or_unsafe_closure_function_name"
        marker = str(spec.marker or spec.restore_plan.get("marker") or "")
        if not marker:
            return "missing_closure_wrapper_marker"
        if not cls._restore_expression_is_scoped(expression, function_name=function_name, marker=marker):
            return "unsafe_or_unscoped_restore_expression"
        return None

    @staticmethod
    def _restore_expression_is_scoped(expression: str, *, function_name: str, marker: str) -> bool:
        return (
            "__reverseDeepAgentClosureWrappers" in expression
            and json.dumps(marker) in expression
            and f"{function_name} =" in expression
            and "__rdgOriginal" in expression
        )

    @staticmethod
    def _post_execution_reason(spec: ClosureWrapperRestoreExecutionSpec, evaluation: dict[str, Any]) -> str | None:
        if not evaluation:
            return "missing_callframe_evaluation_result"
        if not evaluation.get("ok"):
            return str(evaluation.get("error") or "callframe_evaluation_failed")
        expected_callframe_id = str(spec.expected_callframe_id or "")
        observed_callframe_id = str(evaluation.get("callFrameId") or "")
        if expected_callframe_id and observed_callframe_id and expected_callframe_id != observed_callframe_id:
            return "callframe_id_mismatch"
        value = evaluation.get("value")
        if isinstance(value, dict):
            if value.get("ok") is False:
                return str(value.get("reason") or "wrapper_restore_result_not_ok")
            if value.get("restored") is False:
                return "wrapper_restore_not_confirmed"
        return None

    def _execution_payload(
        self,
        *,
        spec: ClosureWrapperRestoreExecutionSpec,
        expression: str,
        evaluation: dict[str, Any],
        status: str,
        reason: str | None,
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-restore-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-restore-execution",
            "requires_review": True,
            "review_approved": spec.review_approved,
            "execute_requested": spec.execute,
            "restore_plan": dict(spec.restore_plan),
            "pause_session_id": spec.pause_session_id,
            "callframe_index": spec.callframe_index,
            "expected_callframe_id": spec.expected_callframe_id,
            "observed_callframe_id": evaluation.get("callFrameId"),
            "function_name": spec.function_name or spec.restore_plan.get("function_name"),
            "marker": spec.marker or spec.restore_plan.get("marker"),
            "wrapper_restored": status == "restored",
            "runtime_mutated": status == "restored",
            "cdp_command_sent": True,
            "callframe_evaluated": True,
            "restore_expression": expression,
            "evaluation_summary": {
                "ok": evaluation.get("ok"),
                "valueType": evaluation.get("valueType"),
                "side_effect_risk": evaluation.get("side_effect_risk"),
                "policy": evaluation.get("policy"),
                "throw_on_side_effect": evaluation.get("throw_on_side_effect"),
                "blocked": evaluation.get("blocked", False),
                "error": evaluation.get("error"),
            },
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "restored":
            return "review_closure_wrapper_restore_result_or_continue_target_flow"
        if reason == "review_approval_required":
            return "approve_closure_wrapper_restore_execution_before_retry"
        if reason == "pause_session_id_required":
            return "reproduce_pause_and_preserve_same_process_session"
        if reason in {"missing_closure_wrapper_restore_plan", "missing_restore_expression"}:
            return "review_closure_wrapper_restore_plan_before_execution"
        return "resolve_closure_wrapper_restore_execution_blockers"

    @staticmethod
    def _side_effect_policy(
        *,
        spec: ClosureWrapperRestoreExecutionSpec | None,
        cdp_command_sent: bool,
        callframe_evaluated: bool,
        runtime_mutated: bool,
        wrapper_restored: bool,
    ) -> dict[str, Any]:
        return {
            "read_only": False,
            "plan_only": False,
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_command_sent,
            "callframe_evaluated": callframe_evaluated,
            "wrapper_restored": wrapper_restored,
            "runtime_mutated": runtime_mutated,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
