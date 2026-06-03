from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.hooks.breakpoints import BreakpointManager, BreakpointResult, BreakpointSpec


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
            "restore_plan_missing",
            "reviewed_executor_not_implemented",
            "automatic_replacement_not_supported",
        ]
        if status != "ready_for_review" and reason:
            execution_blockers.insert(0, reason)
        feasibility = {
            "candidate_has_stable_callframe": bool(callframe_id),
            "lexical_binding_proven": lexical_binding_proven,
            "assignment_safety_proven": False,
            "restore_plan_available": False,
            "reviewed_executor_available": False,
            "automatic_replacement_supported": False,
            "reason": reason or "review_required_before_any_future_wrapper_replacement",
        }
        review_steps = [
            "review_closure_candidate_origin_and_scope_chain",
            "prove_assignment_safety_with_explicit_side_effect_audit",
            "prepare_restore_plan_for_original_lexical_binding",
            "design_reviewed_call_through_wrapper_payload",
            "run_future_reviewed_executor_only_after_explicit_approval",
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


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
