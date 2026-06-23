from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage
from reverse_deepagent.browser.hooks.breakpoints import (
    BreakpointManager,
    BreakpointResult,
    BreakpointSpec,
)
from reverse_deepagent.browser.hooks.paused_session_live import PausedSessionActionSpec
from reverse_deepagent.browser.hooks.paused_session_cross_process import (
    PausedSessionMultiStepContinuationExecutionManager,
    PausedSessionMultiStepContinuationExecutionSpec,
)


JS_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION = "reverse-deepagent.closure-wrapper-strategy.v1"
DEFAULT_CLOSURE_WRAPPER_STRATEGY = "log-only-call-through"


def _first_dict(context: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = context.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


CLOSURE_WRAPPER_STRATEGY_CATALOG: dict[str, dict[str, Any]] = {
    "log-only-call-through": {
        "label": "Log-only call-through wrapper",
        "description": "Install a reviewed same-process wrapper that records argument count plus return/throw metadata, then calls the original target unchanged.",
        "supported_for_planning": True,
        "supported_for_install": True,
        "reviewed_execution_supported": True,
        "strategy_plan_only": False,
        "side_effect_profile": "reviewed-call-through-observation",
        "invokes_target": "only_when_target_flow_invokes_wrapper",
        "captures_arguments": False,
        "captures_argument_count": True,
        "captures_return": True,
        "captures_throw": True,
        "captures_return_value": False,
        "captures_throw_value": False,
        "mutates_arguments": False,
        "overrides_return": False,
        "suppresses_throw": False,
        "requires_restore": True,
        "requires_review": True,
        "requires_same_process_pause": True,
        "execution_scope": "same-process-retained-paused-session",
        "event_kinds": ["return", "throw"],
        "install_blockers": [],
    },
    "arg-preview": {
        "label": "Argument preview plan",
        "description": "Plan-only descriptor for a future argument-preview wrapper. It is not installable by the current executor.",
        "supported_for_planning": True,
        "supported_for_install": False,
        "reviewed_execution_supported": False,
        "strategy_plan_only": True,
        "side_effect_profile": "plan-only-argument-preview",
        "invokes_target": "not_supported_by_current_executor",
        "captures_arguments": True,
        "captures_argument_count": True,
        "captures_return": False,
        "captures_throw": False,
        "captures_return_value": False,
        "captures_throw_value": False,
        "mutates_arguments": False,
        "overrides_return": False,
        "suppresses_throw": False,
        "requires_restore": True,
        "requires_review": True,
        "requires_same_process_pause": True,
        "execution_scope": "plan-only",
        "event_kinds": ["argument-preview"],
        "install_blockers": ["wrapper_strategy_plan_only", "arg_preview_executor_not_implemented"],
    },
    "return-preview": {
        "label": "Return preview plan",
        "description": "Plan-only descriptor for a future return-preview wrapper. It must not override return values.",
        "supported_for_planning": True,
        "supported_for_install": False,
        "reviewed_execution_supported": False,
        "strategy_plan_only": True,
        "side_effect_profile": "plan-only-return-preview",
        "invokes_target": "not_supported_by_current_executor",
        "captures_arguments": False,
        "captures_argument_count": True,
        "captures_return": True,
        "captures_throw": False,
        "captures_return_value": True,
        "captures_throw_value": False,
        "mutates_arguments": False,
        "overrides_return": False,
        "suppresses_throw": False,
        "requires_restore": True,
        "requires_review": True,
        "requires_same_process_pause": True,
        "execution_scope": "plan-only",
        "event_kinds": ["return-preview"],
        "install_blockers": ["wrapper_strategy_plan_only", "return_preview_executor_not_implemented"],
    },
    "throw-preview": {
        "label": "Throw preview plan",
        "description": "Plan-only descriptor for a future throw-preview wrapper. It must rethrow unchanged.",
        "supported_for_planning": True,
        "supported_for_install": False,
        "reviewed_execution_supported": False,
        "strategy_plan_only": True,
        "side_effect_profile": "plan-only-throw-preview",
        "invokes_target": "not_supported_by_current_executor",
        "captures_arguments": False,
        "captures_argument_count": True,
        "captures_return": False,
        "captures_throw": True,
        "captures_return_value": False,
        "captures_throw_value": True,
        "mutates_arguments": False,
        "overrides_return": False,
        "suppresses_throw": False,
        "requires_restore": True,
        "requires_review": True,
        "requires_same_process_pause": True,
        "execution_scope": "plan-only",
        "event_kinds": ["throw-preview"],
        "install_blockers": ["wrapper_strategy_plan_only", "throw_preview_executor_not_implemented"],
    },
    "blocked-mutation-plan": {
        "label": "Blocked mutation plan",
        "description": "Plan-only descriptor that records a rejected mutation-style wrapper request without enabling argument mutation or return override.",
        "supported_for_planning": True,
        "supported_for_install": False,
        "reviewed_execution_supported": False,
        "strategy_plan_only": True,
        "side_effect_profile": "blocked-mutation-plan",
        "invokes_target": "blocked",
        "captures_arguments": False,
        "captures_argument_count": False,
        "captures_return": False,
        "captures_throw": False,
        "captures_return_value": False,
        "captures_throw_value": False,
        "mutates_arguments": False,
        "overrides_return": False,
        "suppresses_throw": False,
        "requires_restore": False,
        "requires_review": True,
        "requires_same_process_pause": True,
        "execution_scope": "blocked-plan-only",
        "event_kinds": [],
        "install_blockers": ["wrapper_strategy_plan_only", "mutation_style_wrapper_blocked"],
    },
}


def normalize_closure_wrapper_strategy(value: Any) -> str:
    strategy = str(value or DEFAULT_CLOSURE_WRAPPER_STRATEGY).strip()
    return strategy or DEFAULT_CLOSURE_WRAPPER_STRATEGY


def closure_wrapper_strategy_descriptor(strategy: Any) -> dict[str, Any]:
    normalized = normalize_closure_wrapper_strategy(strategy)
    template = CLOSURE_WRAPPER_STRATEGY_CATALOG.get(normalized)
    if template is None:
        return {
            "schema_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "strategy": normalized,
            "known_strategy": False,
            "supported_for_planning": False,
            "supported_for_install": False,
            "reviewed_execution_supported": False,
            "strategy_plan_only": True,
            "side_effect_profile": "unknown",
            "invokes_target": "blocked",
            "captures_arguments": False,
            "captures_argument_count": False,
            "captures_return": False,
            "captures_throw": False,
            "captures_return_value": False,
            "captures_throw_value": False,
            "mutates_arguments": False,
            "overrides_return": False,
            "suppresses_throw": False,
            "requires_restore": False,
            "requires_review": True,
            "requires_same_process_pause": True,
            "execution_scope": "unsupported",
            "event_kinds": [],
            "install_blockers": ["unsupported_wrapper_strategy"],
            "next_action": "choose_supported_closure_wrapper_strategy",
        }
    descriptor = dict(template)
    descriptor.update(
        {
            "schema_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "strategy": normalized,
            "known_strategy": True,
            "next_action": (
                "review_and_execute_log_only_call_through_wrapper"
                if template.get("supported_for_install")
                else "review_strategy_descriptor_and_keep_plan_only"
            ),
        }
    )
    descriptor["install_blockers"] = list(template.get("install_blockers") or [])
    descriptor["event_kinds"] = list(template.get("event_kinds") or [])
    return descriptor


def closure_wrapper_strategy_supported_for_install(strategy: Any) -> bool:
    return bool(closure_wrapper_strategy_descriptor(strategy).get("supported_for_install"))


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
    wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
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
        wrapper_strategy = normalize_closure_wrapper_strategy(
            context.get("wrapper_strategy", context.get("wrapperStrategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY))
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
                spec=spec,
            )
        if not selected:
            return self._blocked(
                status="blocked",
                reason=reason or "missing_selected_candidate",
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate={},
                spec=spec,
            )
        validation_reason = self._candidate_blocker(selected)
        if validation_reason:
            return self._blocked(
                status="blocked",
                reason=validation_reason,
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate=selected,
                spec=spec,
            )
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
        if not strategy_descriptor.get("supported_for_planning"):
            return self._blocked(
                status="blocked",
                reason="unsupported_wrapper_strategy",
                candidate_count=candidate_count,
                policy=policy,
                selected_candidate=selected,
                spec=spec,
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
        spec: ClosureWrapperReplacementPlanSpec | None = None,
    ) -> ClosureWrapperReplacementPlanResult:
        spec = spec or ClosureWrapperReplacementPlanSpec(candidates=[selected_candidate] if selected_candidate else [])
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
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
        lexical_binding_proven = bool(function_name and evidence_expression == f"typeof {function_name}")
        execution_blockers = [
            "assignment_safety_not_proven",
            "review_approval_required",
            "same_process_retained_pause_required",
            "automatic_replacement_not_supported",
        ]
        if not strategy_descriptor.get("supported_for_install"):
            execution_blockers.extend(str(item) for item in strategy_descriptor.get("install_blockers", []))
        if status != "ready_for_review" and reason:
            execution_blockers.insert(0, reason)
        feasibility = {
            "candidate_has_stable_callframe": bool(callframe_id),
            "lexical_binding_proven": lexical_binding_proven,
            "assignment_safety_proven": False,
            "restore_plan_available": False,
            "restore_plan_available_after_execution": bool(strategy_descriptor.get("requires_restore", True)),
            "reviewed_executor_available": bool(strategy_descriptor.get("supported_for_install")),
            "reviewed_executor_scope": strategy_descriptor.get("execution_scope") or "same-process-retained-paused-session",
            "automatic_replacement_supported": False,
            "wrapper_strategy_supported_for_planning": bool(strategy_descriptor.get("supported_for_planning")),
            "wrapper_strategy_supported_for_install": bool(strategy_descriptor.get("supported_for_install")),
            "wrapper_strategy_plan_only": bool(strategy_descriptor.get("strategy_plan_only")),
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
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
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
class ClosureWrapperAssignmentSafetySpec:
    """Review-only assignment safety proof for a closure wrapper replacement plan.

    The manager validates that one selected closure-scope candidate, the planned
    assignment target, and the narrow `log-only-call-through` wrapper strategy
    are internally consistent before a reviewed executor may run. It deliberately
    does not evaluate JavaScript or prove runtime mutability; runtime assignment
    can still fail and remains covered by the existing reviewed executor mutation
    audit.
    """

    plan: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    candidate_id: str | None = None
    function_name: str | None = None
    callframe_id: str | None = None
    wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperAssignmentSafetySpec | None":
        context = context or {}
        requested = bool(
            context.get("prove_closure_wrapper_assignment_safety")
            or context.get("proveClosureWrapperAssignmentSafety")
            or context.get("closure_wrapper_assignment_safety_proof_request")
            or context.get("closureWrapperAssignmentSafetyProofRequest")
        )
        raw_plan = (
            context.get("closure_wrapper_replacement_plan")
            or context.get("closureWrapperReplacementPlan")
            or context.get("closure-wrapper-replacement-plan")
            or context.get("plan")
        )
        plan = ClosureWrapperReplacementExecutionSpec._coerce_plan(raw_plan)
        raw_candidate = context.get("candidate") or context.get("selected_candidate") or context.get("selectedCandidate")
        selected_candidate = dict(raw_candidate) if isinstance(raw_candidate, dict) else ClosureWrapperReplacementExecutionSpec._selected_candidate(plan)
        if not requested and not plan and not selected_candidate:
            return None
        wrapper_strategy = normalize_closure_wrapper_strategy(
            context.get(
                "wrapper_strategy",
                context.get("wrapperStrategy", plan.get("wrapper_strategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY)),
            )
        )
        return cls(
            plan=plan,
            selected_candidate=selected_candidate,
            candidate_id=_string_or_none(context.get("candidate_id", context.get("candidateId", selected_candidate.get("candidate_id")))),
            function_name=_string_or_none(
                context.get("function_name", context.get("functionName", selected_candidate.get("function_name", selected_candidate.get("name"))))
            ),
            callframe_id=_string_or_none(
                context.get(
                    "callframe_id",
                    context.get("callFrameId", selected_candidate.get("callFrameId", selected_candidate.get("callframe_id"))),
                )
            ),
            wrapper_strategy=wrapper_strategy,
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )


@dataclass(slots=True)
class ClosureWrapperAssignmentSafetyResult:
    status: str
    assignment_safety: dict[str, Any] = field(default_factory=dict)
    selected_candidate: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-assignment-safety.v1",
            "status": self.status,
            "selected_candidate": self.selected_candidate,
            "assignment_safety": self.assignment_safety,
            "checks": self.checks,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperAssignmentSafetyManager:
    """Prove static safety gates for one reviewed closure wrapper assignment."""

    SUPPORTED_STRATEGIES = {
        strategy
        for strategy, descriptor in CLOSURE_WRAPPER_STRATEGY_CATALOG.items()
        if descriptor.get("supported_for_install")
    }

    def prove(self, spec: ClosureWrapperAssignmentSafetySpec | None) -> ClosureWrapperAssignmentSafetyResult:
        policy = self._side_effect_policy()
        if spec is None:
            return self._result(
                status="unsupported",
                reason="missing_closure_wrapper_assignment_safety_spec",
                spec=None,
                checks=[],
                policy=policy,
            )
        candidate = self._selected_candidate(spec)
        checks = self._checks(spec, candidate)
        failed_required = [item for item in checks if item.get("required") and not item.get("passed")]
        status = "ready_for_review" if not failed_required else "blocked"
        reason = None if status == "ready_for_review" else str(failed_required[0].get("check") or "assignment_safety_check_failed")
        return self._result(status=status, reason=reason, spec=spec, checks=checks, policy=policy, selected_candidate=candidate)

    @staticmethod
    def _selected_candidate(spec: ClosureWrapperAssignmentSafetySpec) -> dict[str, Any]:
        if spec.selected_candidate:
            return dict(spec.selected_candidate)
        return ClosureWrapperReplacementExecutionSpec._selected_candidate(spec.plan)

    def _checks(self, spec: ClosureWrapperAssignmentSafetySpec, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        function_name = str(spec.function_name or candidate.get("function_name") or candidate.get("name") or "")
        callframe_id = str(spec.callframe_id or candidate.get("callFrameId") or candidate.get("callframe_id") or "")
        candidate_id = str(spec.candidate_id or candidate.get("candidate_id") or "")
        evidence_expression = str(candidate.get("evidence_expression") or "")
        feasibility = spec.plan.get("replacement_feasibility") if isinstance(spec.plan.get("replacement_feasibility"), dict) else {}
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
        return [
            self._check("plan_ready_for_review", str(spec.plan.get("status") or "") == "ready_for_review", required=True, evidence=spec.plan.get("status")),
            self._check("candidate_is_closure_scope", str(candidate.get("hook_kind") or "") == "closure-scope", required=True, evidence=candidate.get("hook_kind")),
            self._check("candidate_id_matches_selection", bool(candidate_id) and candidate_id == str(candidate.get("candidate_id") or ""), required=True, evidence=candidate_id),
            self._check("function_name_safe_identifier", bool(JS_IDENTIFIER_RE.fullmatch(function_name)), required=True, evidence=function_name),
            self._check("stable_callframe_id_present", bool(callframe_id), required=True, evidence=callframe_id),
            self._check(
                "lexical_binding_typeof_evidence_matches",
                bool(function_name and evidence_expression == f"typeof {function_name}" and feasibility.get("lexical_binding_proven") is not False),
                required=True,
                evidence=evidence_expression,
            ),
            self._check(
                "wrapper_strategy_known",
                strategy_descriptor.get("supported_for_planning") is True,
                required=True,
                evidence=strategy_descriptor,
            ),
            self._check(
                "wrapper_strategy_install_supported",
                closure_wrapper_strategy_supported_for_install(spec.wrapper_strategy),
                required=True,
                evidence=strategy_descriptor,
            ),
            self._check("plan_is_read_only", spec.plan.get("runtime_mutated") is False and spec.plan.get("wrapper_installed") is False, required=True, evidence={"runtime_mutated": spec.plan.get("runtime_mutated"), "wrapper_installed": spec.plan.get("wrapper_installed")}),
            self._check("reviewed_executor_available", feasibility.get("reviewed_executor_available") is True, required=True, evidence=feasibility.get("reviewed_executor_available")),
            self._check("same_process_retained_pause_required", feasibility.get("reviewed_executor_scope") == "same-process-retained-paused-session", required=True, evidence=feasibility.get("reviewed_executor_scope")),
            self._check("restore_plan_available_after_execution", feasibility.get("restore_plan_available_after_execution") is True, required=True, evidence=feasibility.get("restore_plan_available_after_execution")),
            self._check("runtime_mutability_probe_not_executed", True, required=False, evidence="review-only-static-proof"),
        ]

    @staticmethod
    def _check(check: str, passed: bool, *, required: bool, evidence: Any) -> dict[str, Any]:
        return {"check": check, "passed": bool(passed), "required": bool(required), "evidence": evidence}

    def _result(
        self,
        *,
        status: str,
        reason: str | None,
        spec: ClosureWrapperAssignmentSafetySpec | None,
        checks: list[dict[str, Any]],
        policy: dict[str, Any],
        selected_candidate: dict[str, Any] | None = None,
    ) -> ClosureWrapperAssignmentSafetyResult:
        candidate = selected_candidate if isinstance(selected_candidate, dict) else {}
        function_name = str((spec.function_name if spec else None) or candidate.get("function_name") or candidate.get("name") or "")
        callframe_id = str((spec.callframe_id if spec else None) or candidate.get("callFrameId") or candidate.get("callframe_id") or "")
        passed_required = all(item.get("passed") for item in checks if item.get("required"))
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None)
        assignment_safety = {
            "schema_version": "reverse-deepagent.closure-wrapper-assignment-safety.v1",
            "status": status,
            "reason": reason,
            "proof_kind": "static-reviewed-assignment-safety",
            "proof_scope": "single-closure-candidate-same-process-reviewed-wrapper-assignment",
            "assignment_safety_proven": status == "ready_for_review" and passed_required,
            "safe_to_request_reviewed_execution": status == "ready_for_review" and passed_required,
            "runtime_mutability_proven": False,
            "runtime_mutability_probe_executed": False,
            "requires_review": True,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "function_name": function_name,
            "callFrameId": callframe_id,
            "wrapper_strategy": spec.wrapper_strategy if spec else None,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
            "selected_candidate": candidate,
            "check_count": len(checks),
            "passed_required_check_count": sum(1 for item in checks if item.get("required") and item.get("passed")),
            "failed_required_checks": [str(item.get("check")) for item in checks if item.get("required") and not item.get("passed")],
            "reviewer_note": spec.reviewer_note if spec else None,
            "next_action": self._next_action(status, reason),
            "side_effect_policy": policy,
        }
        return ClosureWrapperAssignmentSafetyResult(
            status=status,
            assignment_safety=assignment_safety,
            selected_candidate=candidate,
            checks=checks,
            side_effect_policy=policy,
            reason=reason,
        )

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "ready_for_review":
            return "approve_reviewed_closure_wrapper_replacement_execution_with_assignment_safety_proof"
        if reason == "plan_ready_for_review":
            return "prepare_ready_closure_wrapper_replacement_plan_before_assignment_safety"
        if reason == "lexical_binding_typeof_evidence_matches":
            return "rerun_closure_scope_discovery_before_assignment_safety"
        return "resolve_closure_wrapper_assignment_safety_blockers"

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
class ClosureWrapperRuntimeMutabilityPreflightSpec:
    """Review-only preflight for a future closure assignment mutability probe.

    This is the checkpoint after static assignment safety and before any future
    side-effecting runtime mutability probe. It prepares reviewable probe intent
    for a retained same-process pause, but it does not evaluate JavaScript,
    assign bindings, install wrappers, or mutate runtime state.
    """

    assignment_safety: dict[str, Any] = field(default_factory=dict)
    pause_session_id: str | None = None
    callframe_index: int = 0
    expected_callframe_id: str | None = None
    function_name: str | None = None
    wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperRuntimeMutabilityPreflightSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_runtime_mutability_preflight")
            or context.get("closureWrapperRuntimeMutabilityPreflight")
            or context.get("preflight_closure_wrapper_runtime_mutability")
            or context.get("preflightClosureWrapperRuntimeMutability")
            or context.get("closure_wrapper_mutability_preflight")
            or context.get("closureWrapperMutabilityPreflight")
        )
        raw_safety = (
            context.get("closure_wrapper_assignment_safety")
            or context.get("closureWrapperAssignmentSafety")
            or context.get("closure-wrapper-assignment-safety")
            or context.get("assignment_safety")
            or context.get("assignmentSafety")
        )
        assignment_safety = ClosureWrapperReplacementExecutionSpec._coerce_assignment_safety_proof(raw_safety)
        if not requested and not assignment_safety:
            return None
        callframe_index_raw = context.get("callframe_index", context.get("callFrameIndex", assignment_safety.get("callframe_index", 0)))
        return cls(
            assignment_safety=assignment_safety,
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
                    context.get("expectedCallFrameId", context.get("callframe_id", context.get("callFrameId", assignment_safety.get("callFrameId")))),
                )
            ),
            function_name=_string_or_none(context.get("function_name", context.get("functionName", assignment_safety.get("function_name")))),
            wrapper_strategy=normalize_closure_wrapper_strategy(
                context.get("wrapper_strategy", context.get("wrapperStrategy", assignment_safety.get("wrapper_strategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY)))
            ),
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )


@dataclass(slots=True)
class ClosureWrapperRuntimeMutabilityPreflightResult:
    status: str
    preflight: dict[str, Any] = field(default_factory=dict)
    assignment_safety: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-preflight.v1",
            "status": self.status,
            "preflight": self.preflight,
            "assignment_safety": self.assignment_safety,
            "checks": self.checks,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperRuntimeMutabilityPreflightManager:
    """Prepare a review checkpoint for a future runtime assignment mutability probe."""

    SUPPORTED_STRATEGIES = ClosureWrapperAssignmentSafetyManager.SUPPORTED_STRATEGIES

    def preflight(self, spec: ClosureWrapperRuntimeMutabilityPreflightSpec | None) -> ClosureWrapperRuntimeMutabilityPreflightResult:
        policy = self._side_effect_policy()
        if spec is None:
            return self._result(
                status="unsupported",
                reason="missing_closure_wrapper_runtime_mutability_preflight_spec",
                spec=None,
                checks=[],
                policy=policy,
            )
        checks = self._checks(spec)
        failed_required = [item for item in checks if item.get("required") and not item.get("passed")]
        status = "ready_for_review" if not failed_required else "blocked"
        reason = None if status == "ready_for_review" else str(failed_required[0].get("check") or "runtime_mutability_preflight_check_failed")
        return self._result(status=status, reason=reason, spec=spec, checks=checks, policy=policy)

    def _checks(self, spec: ClosureWrapperRuntimeMutabilityPreflightSpec) -> list[dict[str, Any]]:
        proof = spec.assignment_safety if isinstance(spec.assignment_safety, dict) else {}
        function_name = str(spec.function_name or proof.get("function_name") or "")
        callframe_id = str(spec.expected_callframe_id or proof.get("callFrameId") or proof.get("callframe_id") or "")
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
        return [
            self._check("assignment_safety_proven", proof.get("assignment_safety_proven") is True, required=True, evidence=proof.get("assignment_safety_proven")),
            self._check("safe_to_request_reviewed_execution", proof.get("safe_to_request_reviewed_execution") is True, required=True, evidence=proof.get("safe_to_request_reviewed_execution")),
            self._check("function_name_safe_identifier", bool(JS_IDENTIFIER_RE.fullmatch(function_name)), required=True, evidence=function_name),
            self._check("stable_callframe_id_present", bool(callframe_id), required=True, evidence=callframe_id),
            self._check("same_process_pause_session_provided", bool(spec.pause_session_id), required=True, evidence=spec.pause_session_id),
            self._check("wrapper_strategy_known", strategy_descriptor.get("supported_for_planning") is True, required=True, evidence=strategy_descriptor),
            self._check("wrapper_strategy_install_supported", closure_wrapper_strategy_supported_for_install(spec.wrapper_strategy), required=True, evidence=strategy_descriptor),
            self._check("runtime_mutability_not_already_claimed", proof.get("runtime_mutability_proven") is not True, required=False, evidence=proof.get("runtime_mutability_proven")),
            self._check("runtime_probe_not_executed", True, required=False, evidence="preflight-only"),
        ]

    @staticmethod
    def _check(check: str, passed: bool, *, required: bool, evidence: Any) -> dict[str, Any]:
        return {"check": check, "passed": bool(passed), "required": bool(required), "evidence": evidence}

    def _result(
        self,
        *,
        status: str,
        reason: str | None,
        spec: ClosureWrapperRuntimeMutabilityPreflightSpec | None,
        checks: list[dict[str, Any]],
        policy: dict[str, Any],
    ) -> ClosureWrapperRuntimeMutabilityPreflightResult:
        proof = spec.assignment_safety if spec and isinstance(spec.assignment_safety, dict) else {}
        function_name = str((spec.function_name if spec else None) or proof.get("function_name") or "")
        callframe_id = str((spec.expected_callframe_id if spec else None) or proof.get("callFrameId") or proof.get("callframe_id") or "")
        passed_required = all(item.get("passed") for item in checks if item.get("required"))
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None)
        preflight = {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-preflight.v1",
            "status": status,
            "reason": reason,
            "preflight_kind": "review-only-runtime-assignment-mutability-probe-plan",
            "runtime_mutability_probe_ready_for_review": status == "ready_for_review" and passed_required,
            "runtime_mutability_proven": False,
            "runtime_mutability_probe_executed": False,
            "requires_review": True,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "pause_session_id": spec.pause_session_id if spec else None,
            "callframe_index": spec.callframe_index if spec else 0,
            "expected_callframe_id": callframe_id,
            "function_name": function_name,
            "wrapper_strategy": spec.wrapper_strategy if spec else None,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
            "probe_plan": {
                "probe_kind": "reviewed-same-process-callframe-assignment-mutability",
                "requires_same_process_retained_pause": True,
                "requires_allow_side_effects_evaluation": True,
                "would_send_cdp_command": True,
                "would_mutate_runtime_temporarily": True,
                "default_execute_now": False,
                "strategy_supported_for_install": bool(strategy_descriptor.get("supported_for_install")),
                "strategy_plan_only": bool(strategy_descriptor.get("strategy_plan_only")),
                "strategy_install_blockers": list(strategy_descriptor.get("install_blockers") or []),
                "review_steps": [
                    "confirm_same_process_pause_session_is_still_live",
                    "review_assignment_safety_proof",
                    "approve_runtime_mutability_probe_payload",
                    "run_future_probe_with_mutation_audit_and_restore_guard",
                ],
            },
            "check_count": len(checks),
            "passed_required_check_count": sum(1 for item in checks if item.get("required") and item.get("passed")),
            "failed_required_checks": [str(item.get("check")) for item in checks if item.get("required") and not item.get("passed")],
            "reviewer_note": spec.reviewer_note if spec else None,
            "next_action": self._next_action(status, reason),
            "side_effect_policy": policy,
        }
        return ClosureWrapperRuntimeMutabilityPreflightResult(
            status=status,
            preflight=preflight,
            assignment_safety=proof,
            checks=checks,
            side_effect_policy=policy,
            reason=reason,
        )

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "ready_for_review":
            return "review_closure_wrapper_runtime_mutability_probe_before_execution"
        if reason == "assignment_safety_proven":
            return "prove_closure_wrapper_assignment_safety_before_mutability_preflight"
        if reason == "same_process_pause_session_provided":
            return "reproduce_pause_and_preserve_same_process_session"
        return "resolve_closure_wrapper_runtime_mutability_preflight_blockers"

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
class ClosureWrapperRuntimeMutabilityResultSpec:
    """Explicit reviewed execution request for a temporary closure assignment probe.

    This consumes the review-only runtime mutability preflight, then performs one
    same-process retained-callframe evaluation that temporarily assigns the
    selected lexical binding to a probe wrapper and immediately restores the
    original value. It proves only assignment mutability for the current retained
    pause; it does not install a durable wrapper or invoke the target function.
    """

    preflight: dict[str, Any] = field(default_factory=dict)
    pause_session_id: str | None = None
    callframe_index: int = 0
    expected_callframe_id: str | None = None
    function_name: str | None = None
    wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
    review_approved: bool = False
    execute: bool = False
    reviewer_note: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperRuntimeMutabilityResultSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_runtime_mutability_result")
            or context.get("closureWrapperRuntimeMutabilityResult")
            or context.get("execute_closure_wrapper_runtime_mutability_probe")
            or context.get("executeClosureWrapperRuntimeMutabilityProbe")
            or context.get("closure_wrapper_mutability_result")
            or context.get("closureWrapperMutabilityResult")
        )
        raw_preflight = (
            context.get("closure_wrapper_runtime_mutability_preflight")
            or context.get("closureWrapperRuntimeMutabilityPreflight")
            or context.get("closure-wrapper-runtime-mutability-preflight")
            or context.get("runtime_mutability_preflight")
            or context.get("runtimeMutabilityPreflight")
            or context.get("preflight")
        )
        preflight = cls._coerce_preflight(raw_preflight)
        if not requested and not preflight:
            return None
        callframe_index_raw = context.get("callframe_index", context.get("callFrameIndex", preflight.get("callframe_index", 0)))
        return cls(
            preflight=preflight,
            pause_session_id=_string_or_none(
                context.get(
                    "pause_session_id",
                    context.get("pauseSessionId", context.get("debugger_session_id", context.get("debuggerSessionId", preflight.get("pause_session_id")))),
                )
            ),
            callframe_index=int(callframe_index_raw or 0),
            expected_callframe_id=_string_or_none(
                context.get(
                    "expected_callframe_id",
                    context.get("expectedCallFrameId", context.get("callframe_id", context.get("callFrameId", preflight.get("expected_callframe_id")))),
                )
            ),
            function_name=_string_or_none(context.get("function_name", context.get("functionName", preflight.get("function_name")))),
            wrapper_strategy=normalize_closure_wrapper_strategy(
                context.get("wrapper_strategy", context.get("wrapperStrategy", preflight.get("wrapper_strategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY)))
            ),
            review_approved=bool(context.get("review_approved", context.get("reviewApproved", False))),
            execute=bool(context.get("execute_closure_wrapper_runtime_mutability_probe", context.get("executeClosureWrapperRuntimeMutabilityProbe", requested))),
            reviewer_note=_string_or_none(context.get("reviewer_note", context.get("reviewerNote"))),
        )

    @staticmethod
    def _coerce_preflight(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("preflight"), dict):
            return dict(value["preflight"])
        return dict(value)


@dataclass(slots=True)
class ClosureWrapperRuntimeMutabilityResult:
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    callframe_evaluations: list[dict[str, Any]] = field(default_factory=list)
    mutation_audit: list[dict[str, Any]] = field(default_factory=list)
    continuation_preflight: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-result.v1",
            "status": self.status,
            "result": self.result,
            "callframe_evaluations": self.callframe_evaluations,
            "mutation_audit": self.mutation_audit,
            "continuation_preflight": self.continuation_preflight,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperRuntimeMutabilityResultManager:
    """Run one reviewed temporary assignment mutability probe from a retained pause."""

    SUPPORTED_STRATEGIES = ClosureWrapperAssignmentSafetyManager.SUPPORTED_STRATEGIES

    def execute(self, page: BrowserPage, spec: ClosureWrapperRuntimeMutabilityResultSpec | None) -> ClosureWrapperRuntimeMutabilityResult:
        if spec is None:
            return self._blocked("unsupported", "missing_closure_wrapper_runtime_mutability_result_spec", spec=None)
        reason = self._blocker(spec)
        if reason:
            return self._blocked("blocked", reason, spec=spec)
        function_name = str(spec.function_name or spec.preflight.get("function_name") or "")
        marker = self._marker(spec, function_name)
        expression = self._probe_expression(function_name=function_name, marker=marker)
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
        status = "proven" if breakpoint_result.status == "success" and post_reason is None else "failed"
        side_effect_policy = self._side_effect_policy(
            spec=spec,
            cdp_command_sent=bool(breakpoint_result.callframe_evaluations),
            callframe_evaluated=bool(breakpoint_result.callframe_evaluations),
            runtime_mutated=bool(breakpoint_result.callframe_evaluations),
            wrapper_installed=False,
            temporary_assignment_attempted=bool(breakpoint_result.callframe_evaluations),
            original_restored=status == "proven",
        )
        payload = self._result_payload(
            spec=spec,
            function_name=function_name,
            marker=marker,
            expression=expression,
            evaluation=evaluation,
            status=status,
            reason=post_reason or breakpoint_result.reason,
            side_effect_policy=side_effect_policy,
        )
        return ClosureWrapperRuntimeMutabilityResult(
            status=status,
            result=payload,
            callframe_evaluations=list(breakpoint_result.callframe_evaluations),
            mutation_audit=list(breakpoint_result.mutation_audit),
            continuation_preflight=dict(breakpoint_result.continuation_preflight),
            side_effect_policy=side_effect_policy,
            reason=post_reason or breakpoint_result.reason,
            error=breakpoint_result.error,
        )

    def _blocked(self, status: str, reason: str, *, spec: ClosureWrapperRuntimeMutabilityResultSpec | None) -> ClosureWrapperRuntimeMutabilityResult:
        side_effect_policy = self._side_effect_policy(
            spec=spec,
            cdp_command_sent=False,
            callframe_evaluated=False,
            runtime_mutated=False,
            wrapper_installed=False,
            temporary_assignment_attempted=False,
            original_restored=False,
        )
        payload = {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-result.v1",
            "status": status,
            "reason": reason,
            "result_id": "closure-wrapper-runtime-mutability-result",
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "preflight": dict(spec.preflight) if spec else {},
            "function_name": spec.function_name if spec else None,
            "wrapper_strategy": spec.wrapper_strategy if spec else None,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None),
            "runtime_mutability_proven": False,
            "runtime_mutability_probe_executed": False,
            "temporary_assignment_attempted": False,
            "temporary_assignment_confirmed": False,
            "original_restored": False,
            "wrapper_installed": False,
            "runtime_mutated": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }
        return ClosureWrapperRuntimeMutabilityResult(status=status, result=payload, side_effect_policy=side_effect_policy, reason=reason)

    @classmethod
    def _blocker(cls, spec: ClosureWrapperRuntimeMutabilityResultSpec) -> str | None:
        if not spec.preflight:
            return "missing_closure_wrapper_runtime_mutability_preflight"
        if str(spec.preflight.get("status") or "") != "ready_for_review":
            return "closure_wrapper_runtime_mutability_preflight_not_ready"
        if spec.preflight.get("runtime_mutability_probe_ready_for_review") is not True:
            return "runtime_mutability_probe_not_ready_for_review"
        if not spec.execute:
            return "execute_closure_wrapper_runtime_mutability_probe_flag_required"
        if not spec.review_approved:
            return "review_approval_required"
        if not spec.pause_session_id:
            return "pause_session_id_required"
        if not closure_wrapper_strategy_descriptor(spec.wrapper_strategy).get("supported_for_planning"):
            return "unsupported_wrapper_strategy"
        if not closure_wrapper_strategy_supported_for_install(spec.wrapper_strategy):
            return "wrapper_strategy_install_not_supported"
        function_name = str(spec.function_name or spec.preflight.get("function_name") or "")
        if not JS_IDENTIFIER_RE.fullmatch(function_name):
            return "missing_or_unsafe_closure_function_name"
        expected_callframe_id = str(spec.expected_callframe_id or spec.preflight.get("expected_callframe_id") or "")
        if not expected_callframe_id:
            return "callframe_id_not_stable"
        if spec.preflight.get("wrapper_installed") is True:
            return "wrapper_already_installed"
        return None

    @staticmethod
    def _post_execution_reason(spec: ClosureWrapperRuntimeMutabilityResultSpec, evaluation: dict[str, Any]) -> str | None:
        if not evaluation:
            return "missing_callframe_evaluation_result"
        if not evaluation.get("ok"):
            return str(evaluation.get("error") or "callframe_evaluation_failed")
        expected_callframe_id = str(spec.expected_callframe_id or spec.preflight.get("expected_callframe_id") or "")
        observed_callframe_id = str(evaluation.get("callFrameId") or "")
        if expected_callframe_id and observed_callframe_id and expected_callframe_id != observed_callframe_id:
            return "callframe_id_mismatch"
        value = evaluation.get("value")
        if isinstance(value, dict):
            if value.get("ok") is False:
                return str(value.get("reason") or "runtime_mutability_probe_result_not_ok")
            if value.get("temporaryAssignmentConfirmed") is not True:
                return "temporary_assignment_not_confirmed"
            if value.get("originalRestored") is not True:
                return "original_restore_not_confirmed"
            if value.get("runtimeMutabilityProven") is not True:
                return "runtime_mutability_not_proven"
        return None

    @staticmethod
    def _marker(spec: ClosureWrapperRuntimeMutabilityResultSpec, function_name: str) -> str:
        raw = str(spec.preflight.get("expected_callframe_id") or spec.pause_session_id or function_name)
        safe = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("._:") or function_name
        return f"reverse-deepagent:closure-mutability-probe:{safe}:{function_name}"

    @staticmethod
    def _probe_expression(*, function_name: str, marker: str) -> str:
        function_literal = json.dumps(function_name)
        marker_literal = json.dumps(marker)
        return f"""(() => {{
  const __rdgName = {function_literal};
  const __rdgMarker = {marker_literal};
  const __rdgPrevious = {function_name};
  const __rdgProbeRecord = {{ marker: __rdgMarker, functionName: __rdgName, attempted: true }};
  const __rdgRoot = globalThis.__reverseDeepAgentClosureMutabilityProbes || (globalThis.__reverseDeepAgentClosureMutabilityProbes = {{ probes: [] }});
  if (typeof __rdgPrevious !== "function") {{
    __rdgProbeRecord.ok = false;
    __rdgProbeRecord.reason = "target_not_function";
    __rdgProbeRecord.previousType = typeof __rdgPrevious;
    __rdgRoot.probes.push(__rdgProbeRecord);
    return __rdgProbeRecord;
  }}
  const __rdgProbe = function(...args) {{ return __rdgPrevious.apply(this, args); }};
  let __rdgAssigned = false;
  let __rdgRestored = false;
  try {{
    {function_name} = __rdgProbe;
    __rdgAssigned = {function_name} === __rdgProbe;
  }} finally {{
    {function_name} = __rdgPrevious;
    __rdgRestored = {function_name} === __rdgPrevious;
  }}
  __rdgProbeRecord.ok = __rdgAssigned && __rdgRestored;
  __rdgProbeRecord.runtimeMutabilityProven = __rdgAssigned && __rdgRestored;
  __rdgProbeRecord.temporaryAssignmentConfirmed = __rdgAssigned;
  __rdgProbeRecord.originalRestored = __rdgRestored;
  __rdgProbeRecord.wrapperInstalled = false;
  __rdgProbeRecord.previousType = typeof __rdgPrevious;
  __rdgRoot.probes.push(__rdgProbeRecord);
  return __rdgProbeRecord;
}})()"""

    def _result_payload(
        self,
        *,
        spec: ClosureWrapperRuntimeMutabilityResultSpec,
        function_name: str,
        marker: str,
        expression: str,
        evaluation: dict[str, Any],
        status: str,
        reason: str | None,
        side_effect_policy: dict[str, Any],
    ) -> dict[str, Any]:
        value = evaluation.get("value") if isinstance(evaluation, dict) else None
        value_payload = value if isinstance(value, dict) else {}
        temporary_assignment_confirmed = bool(value_payload.get("temporaryAssignmentConfirmed")) if value_payload else status == "proven"
        original_restored = bool(value_payload.get("originalRestored")) if value_payload else status == "proven"
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-runtime-mutability-result.v1",
            "status": status,
            "reason": reason,
            "result_id": "closure-wrapper-runtime-mutability-result",
            "requires_review": True,
            "review_approved": spec.review_approved,
            "execute_requested": spec.execute,
            "preflight": dict(spec.preflight),
            "pause_session_id": spec.pause_session_id,
            "callframe_index": spec.callframe_index,
            "expected_callframe_id": spec.expected_callframe_id or spec.preflight.get("expected_callframe_id"),
            "observed_callframe_id": evaluation.get("callFrameId") if isinstance(evaluation, dict) else None,
            "function_name": function_name,
            "marker": marker,
            "wrapper_strategy": spec.wrapper_strategy,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
            "runtime_mutability_proven": status == "proven",
            "runtime_mutability_probe_executed": bool(evaluation),
            "temporary_assignment_attempted": bool(evaluation),
            "temporary_assignment_confirmed": temporary_assignment_confirmed,
            "original_restored": original_restored,
            "wrapper_installed": False,
            "runtime_mutated": bool(evaluation),
            "cdp_command_sent": bool(evaluation),
            "callframe_evaluated": bool(evaluation),
            "probe_expression": expression,
            "evaluation_summary": {
                "ok": evaluation.get("ok") if isinstance(evaluation, dict) else None,
                "valueType": evaluation.get("valueType") if isinstance(evaluation, dict) else None,
                "side_effect_risk": evaluation.get("side_effect_risk") if isinstance(evaluation, dict) else None,
                "policy": evaluation.get("policy") if isinstance(evaluation, dict) else None,
                "throw_on_side_effect": evaluation.get("throw_on_side_effect") if isinstance(evaluation, dict) else None,
                "blocked": evaluation.get("blocked", False) if isinstance(evaluation, dict) else False,
                "error": evaluation.get("error") if isinstance(evaluation, dict) else None,
            },
            "next_action": self._next_action(status, reason),
            "side_effect_policy": side_effect_policy,
        }

    @staticmethod
    def _next_action(status: str, reason: str | None) -> str:
        if status == "proven":
            return "review_runtime_mutability_result_then_optionally_execute_closure_wrapper_replacement"
        if reason == "review_approval_required":
            return "approve_closure_wrapper_runtime_mutability_probe_before_retry"
        if reason == "pause_session_id_required":
            return "reproduce_pause_and_preserve_same_process_session"
        if reason in {"missing_closure_wrapper_runtime_mutability_preflight", "closure_wrapper_runtime_mutability_preflight_not_ready"}:
            return "prepare_ready_closure_wrapper_runtime_mutability_preflight_before_probe"
        return "resolve_closure_wrapper_runtime_mutability_result_blockers"

    @staticmethod
    def _side_effect_policy(
        *,
        spec: ClosureWrapperRuntimeMutabilityResultSpec | None,
        cdp_command_sent: bool,
        callframe_evaluated: bool,
        runtime_mutated: bool,
        wrapper_installed: bool,
        temporary_assignment_attempted: bool,
        original_restored: bool,
    ) -> dict[str, Any]:
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy)
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
            "temporary_assignment_attempted": temporary_assignment_attempted,
            "original_restored": original_restored,
            "wrapper_installed": wrapper_installed,
            "runtime_mutated": runtime_mutated,
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
    wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
    assignment_safety_proof: dict[str, Any] = field(default_factory=dict)
    runtime_mutability_result: dict[str, Any] = field(default_factory=dict)
    require_runtime_mutability_result: bool = False
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
        strategy = normalize_closure_wrapper_strategy(
            context.get(
                "wrapper_strategy",
                context.get("wrapperStrategy", plan.get("wrapper_strategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY)),
            )
        )
        assignment_safety_proof = cls._coerce_assignment_safety_proof(
            context.get("closure_wrapper_assignment_safety")
            or context.get("closureWrapperAssignmentSafety")
            or context.get("closure-wrapper-assignment-safety")
            or context.get("assignment_safety_proof")
            or context.get("assignmentSafetyProof")
        )
        runtime_mutability_result = cls._coerce_runtime_mutability_result(
            context.get("closure_wrapper_runtime_mutability_result")
            or context.get("closureWrapperRuntimeMutabilityResult")
            or context.get("closure-wrapper-runtime-mutability-result")
            or context.get("runtime_mutability_result")
            or context.get("runtimeMutabilityResult")
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
            assignment_safety_proof=assignment_safety_proof,
            runtime_mutability_result=runtime_mutability_result,
            require_runtime_mutability_result=bool(
                context.get(
                    "require_closure_wrapper_runtime_mutability_result",
                    context.get(
                        "requireClosureWrapperRuntimeMutabilityResult",
                        context.get("require_runtime_mutability_result", context.get("requireRuntimeMutabilityResult", False)),
                    ),
                )
            ),
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

    @staticmethod
    def _coerce_assignment_safety_proof(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("assignment_safety"), dict):
            return dict(value["assignment_safety"])
        return dict(value)

    @staticmethod
    def _coerce_runtime_mutability_result(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        if isinstance(value.get("result"), dict):
            return dict(value["result"])
        return dict(value)


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

    SUPPORTED_STRATEGIES = ClosureWrapperAssignmentSafetyManager.SUPPORTED_STRATEGIES

    def execute(self, page: BrowserPage, spec: ClosureWrapperReplacementExecutionSpec | None) -> ClosureWrapperReplacementExecutionResult:
        if spec is None:
            return self._blocked("unsupported", "missing_closure_wrapper_replacement_execution_spec", spec=None)
        selected_candidate = ClosureWrapperReplacementExecutionSpec._selected_candidate(spec.plan)
        reason = self._blocker(spec, selected_candidate)
        if reason:
            return self._blocked("blocked", reason, spec=spec, selected_candidate=selected_candidate)
        function_name = str(spec.function_name or selected_candidate.get("function_name") or selected_candidate.get("name") or "")
        marker = self._marker(spec, selected_candidate, function_name)
        expression = self._install_expression(function_name=function_name, marker=marker, wrapper_strategy=spec.wrapper_strategy)
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
            "require_runtime_mutability_result": bool(spec.require_runtime_mutability_result) if spec else False,
            "runtime_mutability_result_proven": self._runtime_mutability_result_proven(spec, candidate) if spec else False,
            "selected_candidate": candidate,
            "wrapper_strategy": spec.wrapper_strategy if spec else None,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None),
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
        if not closure_wrapper_strategy_descriptor(spec.wrapper_strategy).get("supported_for_planning"):
            return "unsupported_wrapper_strategy"
        if not closure_wrapper_strategy_supported_for_install(spec.wrapper_strategy):
            return "wrapper_strategy_install_not_supported"
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
        if not cls._assignment_safety_proven(spec, candidate):
            return "closure_wrapper_assignment_safety_proof_required"
        if spec.require_runtime_mutability_result:
            runtime_mutability_blocker = cls._runtime_mutability_result_blocker(spec, candidate)
            if runtime_mutability_blocker:
                return runtime_mutability_blocker
        return None

    @staticmethod
    def _assignment_safety_proven(spec: ClosureWrapperReplacementExecutionSpec, candidate: dict[str, Any]) -> bool:
        proof = spec.assignment_safety_proof if isinstance(spec.assignment_safety_proof, dict) else {}
        if not proof:
            return False
        if proof.get("assignment_safety_proven") is not True:
            return False
        if proof.get("safe_to_request_reviewed_execution") is not True:
            return False
        function_name = str(spec.function_name or candidate.get("function_name") or candidate.get("name") or "")
        if function_name and str(proof.get("function_name") or proof.get("functionName") or "") != function_name:
            return False
        expected_callframe_id = str(spec.expected_callframe_id or candidate.get("callFrameId") or candidate.get("callframe_id") or "")
        if expected_callframe_id and str(proof.get("callFrameId") or proof.get("callframe_id") or "") != expected_callframe_id:
            return False
        if str(proof.get("wrapper_strategy") or spec.wrapper_strategy) != spec.wrapper_strategy:
            return False
        return True

    @classmethod
    def _runtime_mutability_result_proven(cls, spec: ClosureWrapperReplacementExecutionSpec | None, candidate: dict[str, Any]) -> bool:
        if spec is None:
            return False
        return cls._runtime_mutability_result_blocker(spec, candidate) is None

    @staticmethod
    def _runtime_mutability_result_blocker(spec: ClosureWrapperReplacementExecutionSpec, candidate: dict[str, Any]) -> str | None:
        result = spec.runtime_mutability_result if isinstance(spec.runtime_mutability_result, dict) else {}
        if not result:
            return "closure_wrapper_runtime_mutability_result_required"
        if str(result.get("status") or "") != "proven":
            return "closure_wrapper_runtime_mutability_result_not_proven"
        if result.get("runtime_mutability_proven") is not True:
            return "runtime_mutability_not_proven"
        if result.get("runtime_mutability_probe_executed") is not True:
            return "runtime_mutability_probe_not_executed"
        if result.get("original_restored") is not True:
            return "runtime_mutability_probe_original_not_restored"
        if result.get("wrapper_installed") is not False:
            return "runtime_mutability_probe_left_wrapper_installed"
        function_name = str(spec.function_name or candidate.get("function_name") or candidate.get("name") or "")
        if function_name and str(result.get("function_name") or result.get("functionName") or "") != function_name:
            return "runtime_mutability_result_function_mismatch"
        expected_callframe_id = str(spec.expected_callframe_id or candidate.get("callFrameId") or candidate.get("callframe_id") or "")
        result_callframe_id = str(result.get("expected_callframe_id") or result.get("callFrameId") or result.get("callframe_id") or result.get("observed_callframe_id") or "")
        if expected_callframe_id and result_callframe_id and result_callframe_id != expected_callframe_id:
            return "runtime_mutability_result_callframe_mismatch"
        if spec.pause_session_id and result.get("pause_session_id") and str(result.get("pause_session_id")) != str(spec.pause_session_id):
            return "runtime_mutability_result_pause_session_mismatch"
        if str(result.get("wrapper_strategy") or spec.wrapper_strategy) != spec.wrapper_strategy:
            return "runtime_mutability_result_strategy_mismatch"
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
    def _install_expression(*, function_name: str, marker: str, wrapper_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY) -> str:
        function_literal = json.dumps(function_name)
        marker_literal = json.dumps(marker)
        strategy_literal = json.dumps(normalize_closure_wrapper_strategy(wrapper_strategy))
        return f"""(() => {{
  const __rdgName = {function_literal};
  const __rdgMarker = {marker_literal};
  const __rdgStrategy = {strategy_literal};
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
        wrapperStrategy: __rdgStrategy,
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
        wrapperStrategy: __rdgStrategy,
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
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None)
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-replacement-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-replacement-execution",
            "requires_review": True,
            "review_approved": spec.review_approved,
            "execute_requested": spec.execute,
            "require_runtime_mutability_result": spec.require_runtime_mutability_result,
            "runtime_mutability_result_proven": self._runtime_mutability_result_proven(spec, candidate),
            "runtime_mutability_result": {
                "status": spec.runtime_mutability_result.get("status"),
                "runtime_mutability_proven": spec.runtime_mutability_result.get("runtime_mutability_proven"),
                "runtime_mutability_probe_executed": spec.runtime_mutability_result.get("runtime_mutability_probe_executed"),
                "original_restored": spec.runtime_mutability_result.get("original_restored"),
                "wrapper_installed": spec.runtime_mutability_result.get("wrapper_installed"),
                "function_name": spec.runtime_mutability_result.get("function_name"),
                "expected_callframe_id": spec.runtime_mutability_result.get("expected_callframe_id"),
                "observed_callframe_id": spec.runtime_mutability_result.get("observed_callframe_id"),
            },
            "wrapper_strategy": spec.wrapper_strategy,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
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
                "wrapper_strategy": spec.wrapper_strategy,
                "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
                "wrapper_strategy_descriptor": strategy_descriptor,
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
        if reason == "closure_wrapper_assignment_safety_proof_required":
            return "prove_closure_wrapper_assignment_safety_before_execution"
        if reason in {
            "closure_wrapper_runtime_mutability_result_required",
            "closure_wrapper_runtime_mutability_result_not_proven",
            "runtime_mutability_not_proven",
            "runtime_mutability_probe_not_executed",
            "runtime_mutability_probe_original_not_restored",
            "runtime_mutability_probe_left_wrapper_installed",
            "runtime_mutability_result_function_mismatch",
            "runtime_mutability_result_callframe_mismatch",
            "runtime_mutability_result_pause_session_mismatch",
            "runtime_mutability_result_strategy_mismatch",
        }:
            return "execute_and_review_closure_wrapper_runtime_mutability_probe_before_replacement"
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
        strategy_descriptor = closure_wrapper_strategy_descriptor(spec.wrapper_strategy if spec else None)
        return {
            "read_only": False,
            "plan_only": False,
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "require_runtime_mutability_result": bool(spec.require_runtime_mutability_result) if spec else False,
            "runtime_mutability_result_proven": ClosureWrapperReplacementExecutionManager._runtime_mutability_result_proven(spec, ClosureWrapperReplacementExecutionSpec._selected_candidate(spec.plan)) if spec else False,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
            "wrapper_strategy_supported_for_install": bool(strategy_descriptor.get("supported_for_install")),
            "wrapper_strategy_plan_only": bool(strategy_descriptor.get("strategy_plan_only")),
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
            "wrapper_strategy": (spec.restore_plan.get("wrapper_strategy") if spec else None),
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": closure_wrapper_strategy_descriptor((spec.restore_plan.get("wrapper_strategy") if spec else None)),
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
        wrapper_strategy = normalize_closure_wrapper_strategy(spec.restore_plan.get("wrapper_strategy", DEFAULT_CLOSURE_WRAPPER_STRATEGY))
        strategy_descriptor = closure_wrapper_strategy_descriptor(wrapper_strategy)
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-restore-execution.v1",
            "status": status,
            "reason": reason,
            "plan_id": "closure-wrapper-restore-execution",
            "requires_review": True,
            "review_approved": spec.review_approved,
            "execute_requested": spec.execute,
            "restore_plan": dict(spec.restore_plan),
            "wrapper_strategy": wrapper_strategy,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
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
        strategy_descriptor = closure_wrapper_strategy_descriptor((spec.restore_plan.get("wrapper_strategy") if spec else None))
        return {
            "read_only": False,
            "plan_only": False,
            "requires_review": True,
            "review_approved": bool(spec.review_approved) if spec else False,
            "execute_requested": bool(spec.execute) if spec else False,
            "strategy_descriptor_version": CLOSURE_WRAPPER_STRATEGY_DESCRIPTOR_VERSION,
            "wrapper_strategy_descriptor": strategy_descriptor,
            "wrapper_strategy_supported_for_install": bool(strategy_descriptor.get("supported_for_install")),
            "wrapper_strategy_plan_only": bool(strategy_descriptor.get("strategy_plan_only")),
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_command_sent,
            "callframe_evaluated": callframe_evaluated,
            "wrapper_restored": wrapper_restored,
            "runtime_mutated": runtime_mutated,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperEventHarvestSpec:
    """Explicit read-only snapshot request for closure wrapper events."""

    markers: list[str] = field(default_factory=list)
    function_names: list[str] = field(default_factory=list)
    limit: int = 300

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperEventHarvestSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_events")
            or context.get("closureWrapperEvents")
            or context.get("closure_wrapper_event_harvest")
            or context.get("closureWrapperEventHarvest")
            or context.get("harvest_closure_wrapper_events")
            or context.get("harvestClosureWrapperEvents")
        )
        markers = cls._coerce_list(context.get("markers", context.get("wrapper_markers", context.get("wrapperMarkers", context.get("marker")))))
        function_names = cls._coerce_list(
            context.get("function_names", context.get("functionNames", context.get("function_name", context.get("functionName"))))
        )
        if not requested and not markers and not function_names:
            return None
        return cls(
            markers=markers,
            function_names=[name for name in function_names if JS_IDENTIFIER_RE.fullmatch(name)],
            limit=max(1, min(1000, int(context.get("limit", context.get("event_limit", context.get("eventLimit", 300))) or 300))),
        )

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
        elif isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            items = [str(item).strip() for item in value if item is not None]
        else:
            items = []
        result: list[str] = []
        for item in items:
            if item and item not in result:
                result.append(item)
        return result


@dataclass(slots=True)
class ClosureWrapperEventHarvestResult:
    status: str
    events: list[dict[str, Any]] = field(default_factory=list)
    event_count: int = 0
    snapshot: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-events.v1",
            "status": self.status,
            "event_count": self.event_count,
            "events": self.events,
            "snapshot": self.snapshot,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperEventHarvestManager:
    """Read closure wrapper events from the runtime store without mutating target state."""

    def harvest(self, page: BrowserPage, spec: ClosureWrapperEventHarvestSpec | None) -> ClosureWrapperEventHarvestResult:
        spec = spec or ClosureWrapperEventHarvestSpec()
        try:
            payload = page.evaluate(self._snapshot_expression(spec))
        except Exception as exc:
            return ClosureWrapperEventHarvestResult(
                status="failed",
                snapshot={},
                side_effect_policy=self._side_effect_policy(),
                reason="runtime_eval_failed",
                error=str(exc),
            )
        snapshot = payload if isinstance(payload, dict) else {"ok": False, "reason": "non_object_snapshot", "valueType": type(payload).__name__}
        events = [dict(event) for event in snapshot.get("events", []) if isinstance(event, dict)]
        ok = bool(snapshot.get("ok", False))
        status = "success" if ok else "partial"
        reason = None if ok else str(snapshot.get("reason") or "closure_wrapper_event_store_unavailable")
        return ClosureWrapperEventHarvestResult(
            status=status,
            events=events,
            event_count=len(events),
            snapshot=snapshot,
            side_effect_policy=self._side_effect_policy(),
            reason=reason,
        )

    @staticmethod
    def _snapshot_expression(spec: ClosureWrapperEventHarvestSpec) -> str:
        markers_json = json.dumps(spec.markers, ensure_ascii=False)
        names_json = json.dumps(spec.function_names, ensure_ascii=False)
        limit = int(spec.limit)
        template = """(() => {{
  const __rdgRoot = globalThis.__reverseDeepAgentClosureWrappers;
  if (!__rdgRoot) return {{ ok: false, reason: "not_installed", events: [], eventCount: 0 }};
  const __rdgMarkers = new Set(__REVERSE_AGENT_CLOSURE_WRAPPER_MARKERS__);
  const __rdgNames = new Set(__REVERSE_AGENT_CLOSURE_WRAPPER_FUNCTIONS__);
  const __rdgLimit = __REVERSE_AGENT_CLOSURE_WRAPPER_LIMIT__;
  const __rdgEvents = Array.isArray(__rdgRoot.events) ? __rdgRoot.events : [];
  const __rdgFiltered = __rdgEvents.filter((event) => {{
    if (!event || typeof event !== "object") return false;
    if (__rdgMarkers.size && !__rdgMarkers.has(event.marker)) return false;
    if (__rdgNames.size && !__rdgNames.has(event.functionName)) return false;
    return true;
  }}).slice(-__rdgLimit);
  const __rdgStrategyCounts = {{}};
  for (const event of __rdgFiltered) {{
    const strategy = event && event.wrapperStrategy ? String(event.wrapperStrategy) : "unknown";
    __rdgStrategyCounts[strategy] = (__rdgStrategyCounts[strategy] || 0) + 1;
  }}
  return {{
    ok: true,
    events: __rdgFiltered,
    eventCount: __rdgFiltered.length,
    totalEventCount: __rdgEvents.length,
    strategyCounts: __rdgStrategyCounts,
    markerCount: Object.keys((__rdgRoot && __rdgRoot.originals) || {{}}).length,
    filters: {{ markers: Array.from(__rdgMarkers), functionNames: Array.from(__rdgNames), limit: __rdgLimit }}
  }};
}})()"""
        return (
            template.replace("__REVERSE_AGENT_CLOSURE_WRAPPER_MARKERS__", markers_json)
            .replace("__REVERSE_AGENT_CLOSURE_WRAPPER_FUNCTIONS__", names_json)
            .replace("__REVERSE_AGENT_CLOSURE_WRAPPER_LIMIT__", str(limit))
            .replace("{{", "{")
            .replace("}}", "}")
        )

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "plan_only": False,
            "requires_review": False,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperContinuationReadinessSpec:
    """Read-only descriptor for coordinating closure wrappers with paused-session continuation.

    This does not install wrappers, recover callFrames, or run debugger actions. It only
    normalizes existing same-process wrapper and paused-session continuation artifacts so a
    reviewer can decide whether a future wrapper-aware continuation step is worth approving.
    """

    replacement_execution: dict[str, Any] = field(default_factory=dict)
    event_harvest: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    multi_step_execution: dict[str, Any] = field(default_factory=dict)
    requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationReadinessSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_readiness")
            or context.get("closureWrapperContinuationReadiness")
            or context.get("closure-wrapper-continuation-readiness")
            or context.get("review_closure_wrapper_continuation")
            or context.get("reviewClosureWrapperContinuation")
            or context.get("wrapper_continuation_readiness")
            or context.get("wrapperContinuationReadiness")
        )
        replacement_execution = cls._coerce_object(
            context.get("closure_wrapper_replacement_execution")
            or context.get("closureWrapperReplacementExecution")
            or context.get("closure-wrapper-replacement-execution")
            or context.get("replacement_execution")
            or context.get("replacementExecution"),
            "execution",
        )
        event_harvest = cls._coerce_object(
            context.get("closure_wrapper_events")
            or context.get("closureWrapperEvents")
            or context.get("closure-wrapper-events")
            or context.get("closure_wrapper_event_harvest")
            or context.get("event_harvest")
            or context.get("eventHarvest"),
            "events",
        )
        continuation_checkpoint = cls._coerce_object(
            context.get("paused_session_cross_process_continuation_checkpoint")
            or context.get("pausedSessionCrossProcessContinuationCheckpoint")
            or context.get("paused-session-cross-process-continuation-checkpoint")
            or context.get("cross_process_continuation_checkpoint")
            or context.get("continuation_checkpoint")
            or context.get("continuationCheckpoint"),
            "checkpoint",
        )
        live_callframe_recovery = cls._coerce_object(
            context.get("paused_session_live_callframe_recovery")
            or context.get("pausedSessionLiveCallframeRecovery")
            or context.get("paused-session-live-callframe-recovery")
            or context.get("live_callframe_recovery")
            or context.get("liveCallframeRecovery"),
            "recovery",
        )
        multi_step_execution = cls._coerce_object(
            context.get("paused_session_multi_step_continuation_execution")
            or context.get("pausedSessionMultiStepContinuationExecution")
            or context.get("paused-session-multi-step-continuation-execution")
            or context.get("multi_step_continuation_execution")
            or context.get("multiStepContinuationExecution"),
            "execution",
        )
        if not requested and not any((replacement_execution, event_harvest, continuation_checkpoint, live_callframe_recovery, multi_step_execution)):
            return None
        return cls(
            replacement_execution=replacement_execution,
            event_harvest=event_harvest,
            continuation_checkpoint=continuation_checkpoint,
            live_callframe_recovery=live_callframe_recovery,
            multi_step_execution=multi_step_execution,
            requested=requested,
        )

    @staticmethod
    def _coerce_object(value: Any, nested_key: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(value)


@dataclass(slots=True)
class ClosureWrapperContinuationReadinessResult:
    status: str
    readiness: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-readiness.v1",
            "status": self.status,
            "readiness": self.readiness,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperContinuationReadinessManager:
    """Review-only bridge descriptor between closure wrapper evidence and continuation evidence."""

    def review(self, spec: ClosureWrapperContinuationReadinessSpec | None) -> ClosureWrapperContinuationReadinessResult:
        if spec is None:
            policy = self._side_effect_policy()
            return ClosureWrapperContinuationReadinessResult(
                status="unsupported",
                readiness=self._payload(None, "unsupported", ["closure_wrapper_continuation_readiness_request_missing"]),
                side_effect_policy=policy,
                reason="closure_wrapper_continuation_readiness_request_missing",
            )
        blockers = self._blockers(spec)
        status = "blocked" if blockers else "ready_for_review"
        payload = self._payload(spec, status, blockers)
        return ClosureWrapperContinuationReadinessResult(
            status=status,
            readiness=payload,
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationReadinessSpec) -> list[str]:
        blockers: list[str] = []
        execution = spec.replacement_execution
        checkpoint = spec.continuation_checkpoint
        recovery = spec.live_callframe_recovery
        if not execution:
            blockers.append("closure_wrapper_replacement_execution_required")
        else:
            if str(execution.get("status") or "") != "applied":
                blockers.append("closure_wrapper_replacement_not_applied")
            if execution.get("wrapper_installed") is not True:
                blockers.append("closure_wrapper_not_installed")
            if not isinstance(execution.get("restore_plan"), dict) or not execution.get("restore_plan"):
                blockers.append("closure_wrapper_restore_plan_required")
            descriptor = execution.get("wrapper_strategy_descriptor") if isinstance(execution.get("wrapper_strategy_descriptor"), dict) else closure_wrapper_strategy_descriptor(execution.get("wrapper_strategy"))
            if descriptor.get("supported_for_install") is not True:
                blockers.append("closure_wrapper_strategy_not_install_supported")
            if descriptor.get("strategy") != DEFAULT_CLOSURE_WRAPPER_STRATEGY:
                blockers.append("closure_wrapper_strategy_not_supported_for_continuation")
        continuation_ready = cls._continuation_ready(checkpoint, recovery)
        if not checkpoint and not recovery:
            blockers.append("paused_session_continuation_evidence_required")
        elif not continuation_ready:
            blockers.append("paused_session_continuation_not_ready")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _continuation_ready(checkpoint: dict[str, Any], recovery: dict[str, Any]) -> bool:
        checkpoint_ready_statuses = {"ready_for_next_action_review", "ready_for_live_callframe_recovery"}
        if checkpoint and (
            str(checkpoint.get("status") or "") in checkpoint_ready_statuses
            or checkpoint.get("continuation_ready_for_next_action") is True
            or checkpoint.get("live_callframe_recovery_ready") is True
        ):
            return True
        if recovery and str(recovery.get("status") or "") == "recovered" and recovery.get("live_callframe_recovered") is True:
            return True
        return False

    @classmethod
    def _payload(cls, spec: ClosureWrapperContinuationReadinessSpec | None, status: str, blockers: list[str]) -> dict[str, Any]:
        execution = spec.replacement_execution if spec else {}
        events = spec.event_harvest if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        multi_step = spec.multi_step_execution if spec else {}
        descriptor = execution.get("wrapper_strategy_descriptor") if isinstance(execution.get("wrapper_strategy_descriptor"), dict) else closure_wrapper_strategy_descriptor(execution.get("wrapper_strategy"))
        event_count = events.get("event_count", events.get("eventCount", 0))
        try:
            event_count = int(event_count or 0)
        except (TypeError, ValueError):
            event_count = 0
        continuation_ready = cls._continuation_ready(checkpoint, recovery)
        ready = status == "ready_for_review"
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-readiness.v1",
            "status": status,
            "ready_for_review": ready,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "same_process_wrapper_installed": bool(execution.get("wrapper_installed")),
            "wrapper_execution_status": _string_or_none(execution.get("status")),
            "wrapper_strategy": descriptor.get("strategy"),
            "wrapper_strategy_descriptor": descriptor,
            "function_name": _string_or_none(execution.get("function_name") or execution.get("functionName")),
            "marker": _string_or_none(execution.get("marker")),
            "restore_plan_available": bool(isinstance(execution.get("restore_plan"), dict) and execution.get("restore_plan")),
            "wrapper_event_harvest_observed": bool(events),
            "wrapper_event_count": event_count,
            "continuation_ready": continuation_ready,
            "continuation_checkpoint_status": _string_or_none(checkpoint.get("status")),
            "live_callframe_recovery_status": _string_or_none(recovery.get("status")),
            "live_callframe_recovered": bool(recovery.get("live_callframe_recovered")),
            "multi_step_execution_status": _string_or_none(multi_step.get("status")),
            "multi_step_iteration_executed": bool(multi_step.get("multi_step_iteration_executed")),
            "cross_process_wrapper_execution_supported": False,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "requires_manual_review": True,
            "next_action": cls._next_action(status, blockers, continuation_ready=continuation_ready),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_readiness_request_missing": ("request", "No closure wrapper continuation readiness evidence was supplied.", "provide_wrapper_and_continuation_artifacts"),
            "closure_wrapper_replacement_execution_required": ("wrapper", "A reviewed closure wrapper replacement execution artifact is required.", "install_reviewed_same_process_closure_wrapper"),
            "closure_wrapper_replacement_not_applied": ("wrapper", "The wrapper replacement execution is not applied.", "review_or_rerun_closure_wrapper_replacement_execution"),
            "closure_wrapper_not_installed": ("wrapper", "The replacement execution did not leave a wrapper installed.", "install_reviewed_same_process_closure_wrapper"),
            "closure_wrapper_restore_plan_required": ("wrapper", "A restore plan is required before wrapper-aware continuation review.", "capture_closure_wrapper_restore_plan"),
            "closure_wrapper_strategy_not_install_supported": ("wrapper", "The wrapper strategy is not supported by the current reviewed installer.", "choose_log_only_call_through_strategy"),
            "closure_wrapper_strategy_not_supported_for_continuation": ("wrapper", "Only the current log-only call-through strategy can enter continuation review.", "choose_log_only_call_through_strategy"),
            "paused_session_continuation_evidence_required": ("debugger", "Paused-session continuation checkpoint or live callFrame recovery evidence is required.", "checkpoint_cross_process_continuation"),
            "paused_session_continuation_not_ready": ("debugger", "The supplied paused-session continuation evidence is not ready.", "recover_live_callframe_or_checkpoint_continuation"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "review_closure_wrapper_continuation_readiness"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "review_closure_wrapper_continuation_readiness"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "review_closure_wrapper_continuation_readiness"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(status: str, blockers: list[str], *, continuation_ready: bool) -> str:
        if status == "ready_for_review":
            return "review_wrapper_continuation_readiness"
        if "closure_wrapper_replacement_execution_required" in blockers or "closure_wrapper_not_installed" in blockers:
            return "install_reviewed_same_process_closure_wrapper"
        if "closure_wrapper_restore_plan_required" in blockers:
            return "capture_closure_wrapper_restore_plan"
        if "paused_session_continuation_evidence_required" in blockers:
            return "checkpoint_cross_process_continuation"
        if not continuation_ready:
            return "recover_live_callframe_or_checkpoint_continuation"
        return "resolve_closure_wrapper_continuation_readiness_blockers"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "cross_process_wrapper_execution_supported": False,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperContinuationExecutionPlanSpec:
    """Review-only execution plan descriptor for closure wrapper continuation.

    This descriptor only composes existing wrapper readiness and paused-session continuation
    evidence. It does not install / restore wrappers, evaluate JavaScript, send CDP commands,
    recover callFrames, execute paused-session actions, or run continuation loops.
    """

    continuation_readiness: dict[str, Any] = field(default_factory=dict)
    session_lifecycle: dict[str, Any] = field(default_factory=dict)
    multi_step_loop_plan: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    plan_id: str | None = None
    requested_strategy: str = DEFAULT_CLOSURE_WRAPPER_STRATEGY
    reviewer: str | None = None
    requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationExecutionPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_execution_plan")
            or context.get("closureWrapperContinuationExecutionPlan")
            or context.get("closure-wrapper-continuation-execution-plan")
            or context.get("plan_closure_wrapper_continuation_execution")
            or context.get("planClosureWrapperContinuationExecution")
            or context.get("wrapper_continuation_execution_plan")
            or context.get("wrapperContinuationExecutionPlan")
        )
        readiness = cls._coerce_object(
            context.get("closure_wrapper_continuation_readiness")
            or context.get("closureWrapperContinuationReadiness")
            or context.get("closure-wrapper-continuation-readiness")
            or context.get("wrapper_continuation_readiness")
            or context.get("wrapperContinuationReadiness"),
            "readiness",
        )
        lifecycle = cls._coerce_object(
            context.get("paused_session_cross_process_session_lifecycle")
            or context.get("pausedSessionCrossProcessSessionLifecycle")
            or context.get("paused-session-cross-process-session-lifecycle")
            or context.get("paused_session_lifecycle")
            or context.get("pausedSessionLifecycle"),
            "lifecycle",
        )
        loop_plan = cls._coerce_object(
            context.get("paused_session_multi_step_loop_plan")
            or context.get("pausedSessionMultiStepLoopPlan")
            or context.get("paused-session-multi-step-loop-plan")
            or context.get("paused_session_continuation_loop_plan")
            or context.get("multi_step_continuation_loop_plan")
            or context.get("loop_plan")
            or context.get("loopPlan"),
            "loop_plan",
        )
        checkpoint = cls._coerce_object(
            context.get("paused_session_cross_process_continuation_checkpoint")
            or context.get("pausedSessionCrossProcessContinuationCheckpoint")
            or context.get("paused-session-cross-process-continuation-checkpoint")
            or context.get("continuation_checkpoint")
            or context.get("continuationCheckpoint"),
            "checkpoint",
        )
        recovery = cls._coerce_object(
            context.get("paused_session_live_callframe_recovery")
            or context.get("pausedSessionLiveCallframeRecovery")
            or context.get("paused-session-live-callframe-recovery")
            or context.get("live_callframe_recovery")
            or context.get("liveCallframeRecovery"),
            "recovery",
        )
        if not requested and not any((readiness, lifecycle, loop_plan, checkpoint, recovery)):
            return None
        strategy = str(context.get("requested_strategy") or context.get("requestedStrategy") or readiness.get("wrapper_strategy") or DEFAULT_CLOSURE_WRAPPER_STRATEGY).strip() or DEFAULT_CLOSURE_WRAPPER_STRATEGY
        plan_id = context.get("plan_id") or context.get("planId") or f"closure-wrapper-continuation-execution-plan-{strategy}"
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            continuation_readiness=readiness,
            session_lifecycle=lifecycle,
            multi_step_loop_plan=loop_plan,
            continuation_checkpoint=checkpoint,
            live_callframe_recovery=recovery,
            plan_id=str(plan_id).strip() if plan_id else None,
            requested_strategy=strategy,
            reviewer=str(reviewer).strip() if reviewer else None,
            requested=requested,
        )

    @staticmethod
    def _coerce_object(value: Any, nested_key: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(value)


@dataclass(slots=True)
class ClosureWrapperContinuationExecutionPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-execution-plan.v1",
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperContinuationExecutionPlanManager:
    """Review-only plan descriptor for future wrapper-aware continuation execution."""

    def plan(self, spec: ClosureWrapperContinuationExecutionPlanSpec | None) -> ClosureWrapperContinuationExecutionPlanResult:
        if spec is None:
            policy = self._side_effect_policy()
            return ClosureWrapperContinuationExecutionPlanResult(
                status="unsupported",
                plan=self._payload(None, "unsupported", ["closure_wrapper_continuation_execution_plan_request_missing"]),
                side_effect_policy=policy,
                reason="closure_wrapper_continuation_execution_plan_request_missing",
            )
        blockers = self._blockers(spec)
        status = "blocked" if blockers else "ready_for_review"
        return ClosureWrapperContinuationExecutionPlanResult(
            status=status,
            plan=self._payload(spec, status, blockers),
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationExecutionPlanSpec) -> list[str]:
        blockers: list[str] = []
        readiness = spec.continuation_readiness
        lifecycle = spec.session_lifecycle
        loop_plan = spec.multi_step_loop_plan
        checkpoint = spec.continuation_checkpoint
        recovery = spec.live_callframe_recovery
        if not readiness:
            blockers.append("closure_wrapper_continuation_readiness_required")
        else:
            if str(readiness.get("status") or "") in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("closure_wrapper_continuation_readiness_blocked")
            if readiness.get("ready_for_review") is not True:
                blockers.append("closure_wrapper_continuation_not_ready")
            if readiness.get("same_process_wrapper_installed") is not True:
                blockers.append("same_process_wrapper_required")
            if readiness.get("restore_plan_available") is not True:
                blockers.append("closure_wrapper_restore_plan_required")
            if readiness.get("wrapper_strategy") != DEFAULT_CLOSURE_WRAPPER_STRATEGY:
                blockers.append("closure_wrapper_strategy_not_supported_for_execution_plan")
            if readiness.get("continuation_ready") is not True:
                blockers.append("paused_session_continuation_not_ready")
        if spec.requested_strategy != DEFAULT_CLOSURE_WRAPPER_STRATEGY:
            blockers.append("requested_wrapper_strategy_not_supported")
        if lifecycle:
            lifecycle_status = str(lifecycle.get("status") or "")
            if lifecycle_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("paused_session_lifecycle_blocked")
        if loop_plan:
            loop_status = str(loop_plan.get("status") or "")
            if loop_status in {"blocked", "failed", "failure", "error", "unsupported"}:
                blockers.append("paused_session_loop_plan_blocked")
        if not any((loop_plan, checkpoint, recovery)):
            blockers.append("paused_session_execution_path_required")
        elif loop_plan and not cls._loop_plan_ready(loop_plan):
            blockers.append("paused_session_loop_plan_not_reviewable")
        elif not loop_plan and not cls._checkpoint_or_recovery_ready(checkpoint, recovery):
            blockers.append("paused_session_execution_path_not_ready")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _loop_plan_ready(loop_plan: dict[str, Any]) -> bool:
        readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
        return bool(loop_plan.get("ready_for_review") or readiness.get("next_loop_iteration_reviewable") or str(loop_plan.get("status") or "") == "ready_for_review")

    @staticmethod
    def _checkpoint_or_recovery_ready(checkpoint: dict[str, Any], recovery: dict[str, Any]) -> bool:
        if checkpoint and (
            checkpoint.get("continuation_ready_for_next_action") is True
            or checkpoint.get("live_callframe_recovery_ready") is True
            or str(checkpoint.get("status") or "") in {"ready_for_next_action_review", "ready_for_live_callframe_recovery", "ready_for_review"}
        ):
            return True
        if recovery and str(recovery.get("status") or "") == "recovered" and recovery.get("live_callframe_recovered") is True:
            return True
        return False

    @classmethod
    def _payload(cls, spec: ClosureWrapperContinuationExecutionPlanSpec | None, status: str, blockers: list[str]) -> dict[str, Any]:
        readiness = spec.continuation_readiness if spec else {}
        lifecycle = spec.session_lifecycle if spec else {}
        loop_plan = spec.multi_step_loop_plan if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        strategy = spec.requested_strategy if spec else DEFAULT_CLOSURE_WRAPPER_STRATEGY
        ready = status == "ready_for_review"
        next_loop_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-execution-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "plan_id": spec.plan_id if spec else None,
            "reviewer": spec.reviewer if spec else None,
            "requested_strategy": strategy,
            "wrapper_strategy": readiness.get("wrapper_strategy") or strategy,
            "function_name": readiness.get("function_name"),
            "marker": readiness.get("marker"),
            "same_process_wrapper_installed": bool(readiness.get("same_process_wrapper_installed")),
            "restore_plan_available": bool(readiness.get("restore_plan_available")),
            "wrapper_event_count": readiness.get("wrapper_event_count", 0),
            "source_statuses": {
                "continuation_readiness": readiness.get("status"),
                "session_lifecycle": lifecycle.get("status"),
                "multi_step_loop_plan": loop_plan.get("status"),
                "continuation_checkpoint": checkpoint.get("status"),
                "live_callframe_recovery": recovery.get("status"),
            },
            "execution_strategy": {
                "mode": "reviewed_plan_only",
                "same_process_wrapper_required": True,
                "cross_process_wrapper_execution_supported": False,
                "requested_strategy_supported": strategy == DEFAULT_CLOSURE_WRAPPER_STRATEGY,
                "supported_strategy": DEFAULT_CLOSURE_WRAPPER_STRATEGY,
                "automatic_wrapper_continuation_supported": False,
                "automatic_multi_step_loop_supported": False,
            },
            "planned_steps": cls._planned_steps(ready=ready, loop_plan=loop_plan, checkpoint=checkpoint, recovery=recovery),
            "review_gates": {
                "requires_wrapper_readiness_review": True,
                "requires_session_lifecycle_review": bool(lifecycle),
                "requires_loop_plan_review": bool(loop_plan),
                "requires_fresh_live_callframe_before_execution": True,
                "requires_retained_attached_session_before_execution": True,
                "requires_restore_plan_before_execution": True,
                "requires_explicit_execution_approval": True,
                "requires_post_execution_event_harvest": True,
                "requires_followup_checkpoint_after_debugger_action": True,
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_iteration": {
                "available": bool(next_loop_iteration),
                "workflow_step_index": next_loop_iteration.get("workflow_step_index"),
                "method": next_loop_iteration.get("method"),
                "fingerprint": next_loop_iteration.get("fingerprint"),
                "would_execute": False,
            },
            "next_action": cls._next_action(status, blockers, loop_plan=loop_plan),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _planned_steps(*, ready: bool, loop_plan: dict[str, Any], checkpoint: dict[str, Any], recovery: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"order": 1, "action": "review_closure_wrapper_continuation_readiness", "artifact": "workspace/closure-wrapper-continuation-readiness.json", "automatic": False, "ready": ready},
            {"order": 2, "action": "review_paused_session_lifecycle", "artifact": "workspace/paused-session-cross-process-session-lifecycle.json", "automatic": False, "observed": bool(loop_plan or checkpoint or recovery)},
            {"order": 3, "action": "review_next_paused_session_loop_iteration", "artifact": "workspace/paused-session-multi-step-loop-plan.json", "automatic": False, "observed": bool(loop_plan)},
            {"order": 4, "action": "approve_future_wrapper_continuation_execution", "artifact": "workspace/closure-wrapper-continuation-execution-plan.json", "automatic": False, "would_execute": False},
            {"order": 5, "action": "harvest_wrapper_events_after_reviewed_execution", "artifact": "workspace/closure-wrapper-events.json", "automatic": False, "would_trigger_target": False},
        ]

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_execution_plan_request_missing": ("request", "No closure wrapper continuation execution plan request was supplied.", "provide_wrapper_continuation_readiness"),
            "closure_wrapper_continuation_readiness_required": ("wrapper", "A wrapper continuation readiness descriptor is required.", "review_closure_wrapper_continuation_readiness"),
            "closure_wrapper_continuation_readiness_blocked": ("wrapper", "The supplied wrapper continuation readiness descriptor is blocked.", "resolve_closure_wrapper_continuation_readiness_blockers"),
            "closure_wrapper_continuation_not_ready": ("wrapper", "The wrapper continuation readiness descriptor is not ready for review.", "review_closure_wrapper_continuation_readiness"),
            "same_process_wrapper_required": ("wrapper", "A same-process reviewed wrapper must already be installed.", "install_reviewed_same_process_closure_wrapper"),
            "closure_wrapper_restore_plan_required": ("wrapper", "A restore plan is required before planning wrapper-aware continuation.", "capture_closure_wrapper_restore_plan"),
            "closure_wrapper_strategy_not_supported_for_execution_plan": ("wrapper", "Only log-only-call-through wrapper readiness can be planned for continuation.", "choose_log_only_call_through_strategy"),
            "requested_wrapper_strategy_not_supported": ("wrapper", "The requested wrapper continuation strategy is not supported by this plan baseline.", "choose_log_only_call_through_strategy"),
            "paused_session_continuation_not_ready": ("debugger", "Paused-session continuation evidence is not ready.", "checkpoint_or_recover_paused_session_continuation"),
            "paused_session_lifecycle_blocked": ("debugger", "The supplied paused-session lifecycle descriptor is blocked.", "resolve_paused_session_lifecycle_blockers"),
            "paused_session_loop_plan_blocked": ("debugger", "The supplied paused-session loop plan is blocked.", "resolve_paused_session_loop_plan_blockers"),
            "paused_session_execution_path_required": ("debugger", "A loop plan, continuation checkpoint, or live callFrame recovery artifact is required.", "plan_paused_session_continuation_loop"),
            "paused_session_loop_plan_not_reviewable": ("debugger", "The supplied paused-session loop plan is not ready for the next reviewed iteration.", "review_or_replan_paused_session_loop"),
            "paused_session_execution_path_not_ready": ("debugger", "The supplied checkpoint / recovery evidence is not ready for execution planning.", "recover_live_callframe_or_checkpoint_continuation"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution_plan"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution_plan"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution_plan"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(status: str, blockers: list[str], *, loop_plan: dict[str, Any]) -> str:
        if status == "ready_for_review":
            return "review_closure_wrapper_continuation_execution_plan"
        if "closure_wrapper_continuation_readiness_required" in blockers or "closure_wrapper_continuation_not_ready" in blockers:
            return "review_closure_wrapper_continuation_readiness"
        if "paused_session_execution_path_required" in blockers:
            return "plan_paused_session_continuation_loop"
        if "paused_session_loop_plan_not_reviewable" in blockers or "paused_session_loop_plan_blocked" in blockers:
            return "review_or_replan_paused_session_loop"
        if loop_plan:
            return "resolve_closure_wrapper_continuation_execution_plan_blockers"
        return "recover_live_callframe_or_checkpoint_continuation"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "wrapper_events_harvested": False,
            "cross_process_wrapper_execution_supported": False,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "automatic_live_callframe_recovery": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperContinuationExecutionSpec:
    """Review-gated one-iteration wrapper-aware paused-session continuation executor."""

    execution_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execute_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int = 1
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_execution")
            or context.get("closureWrapperContinuationExecution")
            or context.get("closure-wrapper-continuation-execution")
            or context.get("execute_closure_wrapper_continuation")
            or context.get("executeClosureWrapperContinuation")
            or context.get("wrapper_continuation_execution")
            or context.get("wrapperContinuationExecution")
        )
        plan_container = _first_dict(
            context,
            "closure_wrapper_continuation_execution_plan",
            "closureWrapperContinuationExecutionPlan",
            "closure-wrapper-continuation-execution-plan",
            "wrapper_continuation_execution_plan",
            "wrapperContinuationExecutionPlan",
        )
        plan = dict(plan_container.get("plan")) if isinstance(plan_container.get("plan"), dict) else plan_container
        workflow_container = _first_dict(
            context,
            "paused_session_multi_step_continuation_workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "paused-session-multi-step-continuation-workflow",
            "multi_step_continuation_workflow",
            "multiStepContinuationWorkflow",
            "continuation_workflow",
            "continuationWorkflow",
        )
        workflow = dict(workflow_container.get("workflow")) if isinstance(workflow_container.get("workflow"), dict) else workflow_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        if not requested and not plan:
            return None
        index_raw = context.get("selected_step_index", context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", 1))))
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            selected_step_index = int(index_raw)
        except (TypeError, ValueError):
            selected_step_index = 1
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_closure_wrapper_continuation",
            context.get("executeClosureWrapperContinuation", context.get("execute_iteration", context.get("executeIteration", False))),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or workflow.get("pause_session_id") or recovery.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or workflow.get("target_id") or recovery.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            execution_plan=plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execute_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index),
            pause_session_id=str(pause_session_id).strip() if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            attached_session_id=str(attached_session_id).strip() if attached_session_id else None,
            live_callframe_id=str(live_callframe_id).strip() if live_callframe_id else None,
            timeout_ms=max(10, timeout_ms),
            observed_paused_event=event,
            reviewer=str(reviewer).strip() if reviewer else None,
            require_matching_session_id=bool(match_raw),
        )


@dataclass(slots=True)
class ClosureWrapperContinuationExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-execution.v1",
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperContinuationExecutionManager:
    """Execute one reviewed paused-session iteration while an existing wrapper is installed."""

    def execute(self, page: BrowserPage | None, spec: ClosureWrapperContinuationExecutionSpec | None) -> ClosureWrapperContinuationExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return ClosureWrapperContinuationExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_iteration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return ClosureWrapperContinuationExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return ClosureWrapperContinuationExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        inner = PausedSessionMultiStepContinuationExecutionManager().execute(
            page,
            PausedSessionMultiStepContinuationExecutionSpec(
                workflow=spec.multi_step_workflow,
                live_callframe_recovery=spec.live_callframe_recovery,
                cross_process_attach_probe=spec.cross_process_attach_probe,
                execute_iteration=True,
                review_approved=True,
                selected_step_index=spec.selected_step_index,
                pause_session_id=spec.pause_session_id,
                target_id=spec.target_id,
                attached_session_id=spec.attached_session_id,
                live_callframe_id=spec.live_callframe_id,
                timeout_ms=spec.timeout_ms,
                observed_paused_event=spec.observed_paused_event,
                reviewer=spec.reviewer,
                require_matching_session_id=spec.require_matching_session_id,
            ),
        )
        status = "executed" if inner.status == "executed" else inner.status
        blockers_after = [] if status == "executed" else [inner.reason or "wrapper_continuation_iteration_failed"]
        payload = self._payload(
            spec,
            status=status,
            blockers=blockers_after,
            inner_result=inner.execution,
            inner_policy=inner.side_effect_policy,
            error=inner.error,
        )
        return ClosureWrapperContinuationExecutionResult(
            status=status,
            execution=payload,
            side_effect_policy=self._side_effect_policy(inner.side_effect_policy),
            reason=blockers_after[0] if blockers_after else None,
            error=inner.error,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["closure_wrapper_continuation_execution_request_missing"]
        blockers: list[str] = []
        plan = spec.execution_plan
        strategy = plan.get("execution_strategy") if isinstance(plan.get("execution_strategy"), dict) else {}
        if not plan:
            blockers.append("closure_wrapper_continuation_execution_plan_required")
        else:
            if str(plan.get("status") or "") not in {"ready_for_review"} or plan.get("ready_for_review") is not True:
                blockers.append("closure_wrapper_continuation_execution_plan_not_ready")
            if plan.get("same_process_wrapper_installed") is not True:
                blockers.append("same_process_wrapper_required")
            if plan.get("restore_plan_available") is not True:
                blockers.append("closure_wrapper_restore_plan_required")
            if strategy.get("automatic_wrapper_continuation_supported") is not False:
                blockers.append("automatic_wrapper_continuation_must_remain_disabled")
            if strategy.get("automatic_multi_step_loop_supported") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
            if strategy.get("supported_strategy") != DEFAULT_CLOSURE_WRAPPER_STRATEGY:
                blockers.append("unsupported_wrapper_strategy")
        if not spec.multi_step_workflow:
            blockers.append("multi_step_workflow_required")
        elif spec.multi_step_workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        if not spec.live_callframe_recovery:
            blockers.append("live_callframe_recovery_required")
        elif spec.live_callframe_recovery.get("status") == "blocked" or not spec.live_callframe_recovery.get("live_callframe_recovered"):
            blockers.append("live_callframe_recovery_blocked")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required")
        if not spec.live_callframe_id:
            blockers.append("live_callframe_id_required")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: ClosureWrapperContinuationExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        plan = spec.execution_plan if spec else {}
        workflow = spec.multi_step_workflow if spec else {}
        selected = inner_result.get("selected_step") if isinstance((inner_result or {}).get("selected_step"), dict) else {}
        policy = cls._side_effect_policy(inner_policy or {})
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-execution.v1",
            "status": status,
            "plan_id": plan.get("plan_id"),
            "workflow_id": workflow.get("workflow_id"),
            "pause_session_id": spec.pause_session_id if spec else workflow.get("pause_session_id"),
            "target_id": spec.target_id if spec else workflow.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "wrapper_strategy": plan.get("wrapper_strategy"),
            "function_name": plan.get("function_name"),
            "same_process_wrapper_installed": bool(plan.get("same_process_wrapper_installed")),
            "restore_plan_available": bool(plan.get("restore_plan_available")),
            "selected_step_index": spec.selected_step_index if spec else None,
            "selected_step": selected,
            "selected_method": (inner_result or {}).get("selected_method") or selected.get("method"),
            "execute_iteration_requested": bool(spec and spec.execute_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "executor_artifact": "workspace/paused-session-multi-step-continuation-execution.json",
            "executor_result": inner_result or {},
            "executor_status": (inner_result or {}).get("status"),
            "paused_event_captured": bool((inner_result or {}).get("paused_event_captured")),
            "manual_checkpoint_required_after_step": True,
            "post_execution_event_harvest_required": True,
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_wrapper_events": "workspace/closure-wrapper-events.json",
            "wrapper_continuation_iteration_executed": status == "executed",
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, paused_captured=bool((inner_result or {}).get("paused_event_captured"))),
            "side_effect_policy": policy,
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        cdp_sent = bool(inner_policy.get("cdp_command_sent"))
        return {
            "read_only": not cdp_sent,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_sent,
            "debugger_event_subscribed": bool(inner_policy.get("debugger_event_subscribed")),
            "paused_event_captured": bool(inner_policy.get("paused_event_captured")),
            "browser_resumed": bool(inner_policy.get("browser_resumed")),
            "debugger_stepped": bool(inner_policy.get("debugger_stepped")),
            "callframe_evaluated": bool(inner_policy.get("callframe_evaluated")),
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "wrapper_events_harvested": False,
            "cross_process_action_executed": bool(inner_policy.get("cross_process_action_executed") or cdp_sent),
            "wrapper_continuation_iteration_executed": cdp_sent,
            "bounded_one_iteration_only": True,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_execution_request_missing": ("request", "No wrapper continuation execution request was provided.", "request_closure_wrapper_continuation_execution"),
            "closure_wrapper_continuation_execution_plan_required": ("plan", "A ready wrapper continuation execution plan is required.", "plan_closure_wrapper_continuation_execution"),
            "closure_wrapper_continuation_execution_plan_not_ready": ("plan", "The wrapper continuation execution plan is not ready for review.", "review_closure_wrapper_continuation_execution_plan"),
            "same_process_wrapper_required": ("wrapper", "A same-process reviewed wrapper must already be installed.", "install_reviewed_same_process_closure_wrapper"),
            "closure_wrapper_restore_plan_required": ("wrapper", "A restore plan must exist before wrapper-aware continuation execution.", "capture_closure_wrapper_restore_plan"),
            "automatic_wrapper_continuation_must_remain_disabled": ("safety", "This executor only performs one reviewed iteration, not automatic wrapper continuation.", "disable_automatic_wrapper_continuation"),
            "automatic_multi_step_loop_must_remain_disabled": ("safety", "This executor does not run automatic multi-step loops.", "disable_automatic_multi_step_loop"),
            "unsupported_wrapper_strategy": ("wrapper", "Only log-only-call-through wrapper continuation is supported.", "choose_log_only_call_through_strategy"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step paused-session workflow is required.", "plan_multi_step_continuation_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The supplied multi-step workflow is not ready.", "review_or_replan_multi_step_continuation_workflow"),
            "live_callframe_recovery_required": ("debugger", "Fresh live callFrame recovery evidence is required.", "recover_live_callframe_from_checkpoint"),
            "live_callframe_recovery_blocked": ("debugger", "The supplied live callFrame recovery evidence is blocked.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_id_required": ("debugger", "The retained attached session id is required.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "The recovered live callFrame id is required.", "recover_live_callframe_from_checkpoint"),
            "review_approval_required": ("review", "Executing wrapper-aware continuation requires explicit review approval.", "approve_closure_wrapper_continuation_iteration"),
            "wrapper_continuation_iteration_failed": ("runtime", "The underlying paused-session iteration failed.", "inspect_closure_wrapper_continuation_execution"),
        }
        return [
            {"code": blocker, "category": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution"))[0], "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution"))[1], "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_execution"))[2]}
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], paused_captured: bool) -> str:
        if blockers:
            return "inspect_closure_wrapper_continuation_execution_blockers"
        if status in {"ready_for_review", "review_required"}:
            return "approve_closure_wrapper_continuation_iteration"
        if status == "executed" and paused_captured:
            return "harvest_wrapper_events_and_checkpoint_continuation"
        if status == "executed":
            return "harvest_closure_wrapper_events_after_reviewed_execution"
        return "inspect_closure_wrapper_continuation_execution"


@dataclass(slots=True)
class ClosureWrapperContinuationCheckpointSpec:
    """Read-only follow-up checkpoint after one wrapper-aware continuation iteration."""

    continuation_execution: dict[str, Any] = field(default_factory=dict)
    event_harvest: dict[str, Any] = field(default_factory=dict)
    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    multi_step_loop_plan: dict[str, Any] = field(default_factory=dict)
    previous_checkpoint: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationCheckpointSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_checkpoint")
            or context.get("closureWrapperContinuationCheckpoint")
            or context.get("closure-wrapper-continuation-checkpoint")
            or context.get("checkpoint_closure_wrapper_continuation")
            or context.get("checkpointClosureWrapperContinuation")
            or context.get("wrapper_continuation_checkpoint")
            or context.get("wrapperContinuationCheckpoint")
        )
        execution_container = _first_dict(
            context,
            "closure_wrapper_continuation_execution",
            "closureWrapperContinuationExecution",
            "closure-wrapper-continuation-execution",
            "wrapper_continuation_execution",
            "wrapperContinuationExecution",
        )
        execution = dict(execution_container.get("execution")) if isinstance(execution_container.get("execution"), dict) else execution_container
        events_container = _first_dict(
            context,
            "closure_wrapper_events",
            "closureWrapperEvents",
            "closure-wrapper-events",
            "closure_wrapper_event_harvest",
            "closureWrapperEventHarvest",
            "event_harvest",
            "eventHarvest",
        )
        checkpoint_container = _first_dict(
            context,
            "paused_session_cross_process_continuation_checkpoint",
            "pausedSessionCrossProcessContinuationCheckpoint",
            "paused-session-cross-process-continuation-checkpoint",
            "cross_process_continuation_checkpoint",
            "crossProcessContinuationCheckpoint",
            "continuation_checkpoint",
            "continuationCheckpoint",
        )
        checkpoint = dict(checkpoint_container.get("checkpoint")) if isinstance(checkpoint_container.get("checkpoint"), dict) else checkpoint_container
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        previous_container = _first_dict(
            context,
            "previous_closure_wrapper_continuation_checkpoint",
            "previousClosureWrapperContinuationCheckpoint",
            "previous-wrapper-continuation-checkpoint",
        )
        previous = dict(previous_container.get("checkpoint")) if isinstance(previous_container.get("checkpoint"), dict) else previous_container
        if not requested and not any((execution, events_container, checkpoint, loop_plan)):
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            continuation_execution=execution,
            event_harvest=events_container,
            continuation_checkpoint=checkpoint,
            multi_step_loop_plan=loop_plan,
            previous_checkpoint=previous,
            reviewer=str(reviewer).strip() if reviewer else None,
            requested=requested,
        )


@dataclass(slots=True)
class ClosureWrapperContinuationCheckpointResult:
    status: str
    checkpoint: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-checkpoint.v1",
            "status": self.status,
            "checkpoint": self.checkpoint,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperContinuationCheckpointManager:
    """Compose wrapper events and paused-session checkpoint evidence after one iteration."""

    def checkpoint(self, spec: ClosureWrapperContinuationCheckpointSpec | None) -> ClosureWrapperContinuationCheckpointResult:
        blockers = self._blockers(spec)
        status = "blocked" if blockers else "ready_for_review"
        payload = self._payload(spec, status=status, blockers=blockers)
        return ClosureWrapperContinuationCheckpointResult(
            status=status,
            checkpoint=payload,
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationCheckpointSpec | None) -> list[str]:
        if spec is None:
            return ["closure_wrapper_continuation_checkpoint_request_missing"]
        blockers: list[str] = []
        execution = spec.continuation_execution
        events = spec.event_harvest
        checkpoint = spec.continuation_checkpoint
        if not execution:
            blockers.append("closure_wrapper_continuation_execution_required")
        else:
            if execution.get("status") != "executed" or execution.get("wrapper_continuation_iteration_executed") is not True:
                blockers.append("closure_wrapper_continuation_execution_not_executed")
            if execution.get("automatic_wrapper_continuation") is not False:
                blockers.append("automatic_wrapper_continuation_must_remain_disabled")
            if execution.get("automatic_multi_step_loop") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
            if execution.get("post_execution_event_harvest_required") is not True:
                blockers.append("post_execution_event_harvest_requirement_missing")
            if execution.get("manual_checkpoint_required_after_step") is not True:
                blockers.append("manual_continuation_checkpoint_requirement_missing")
        if not events:
            blockers.append("closure_wrapper_events_required")
        else:
            if events.get("status") not in {"success"}:
                blockers.append("closure_wrapper_events_not_successful")
            if cls._event_count(events) <= 0:
                blockers.append("closure_wrapper_events_empty")
        if not checkpoint:
            blockers.append("paused_session_continuation_checkpoint_required")
        elif not cls._checkpoint_ready(checkpoint):
            blockers.append("paused_session_continuation_checkpoint_not_ready")
        return list(dict.fromkeys(blockers))

    @staticmethod
    def _event_count(events: dict[str, Any]) -> int:
        raw = events.get("event_count", events.get("eventCount"))
        if raw is None and isinstance(events.get("snapshot"), dict):
            raw = events["snapshot"].get("eventCount")
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _checkpoint_ready(checkpoint: dict[str, Any]) -> bool:
        return (
            checkpoint.get("status") in {"ready_for_next_action_review", "ready_for_live_callframe_recovery"}
            or checkpoint.get("continuation_ready_for_next_action") is True
            or checkpoint.get("live_callframe_recovery_ready") is True
        )

    @classmethod
    def _payload(
        cls,
        spec: ClosureWrapperContinuationCheckpointSpec | None,
        *,
        status: str,
        blockers: list[str],
    ) -> dict[str, Any]:
        execution = spec.continuation_execution if spec else {}
        events = spec.event_harvest if spec else {}
        checkpoint = spec.continuation_checkpoint if spec else {}
        loop_plan = spec.multi_step_loop_plan if spec else {}
        previous = spec.previous_checkpoint if spec else {}
        ready = status == "ready_for_review"
        event_count = cls._event_count(events)
        checkpoint_ready = cls._checkpoint_ready(checkpoint)
        next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        selected_step = execution.get("selected_step") if isinstance(execution.get("selected_step"), dict) else {}
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-checkpoint.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "plan_id": execution.get("plan_id"),
            "workflow_id": execution.get("workflow_id"),
            "pause_session_id": execution.get("pause_session_id") or checkpoint.get("pause_session_id"),
            "target_id": execution.get("target_id") or checkpoint.get("target_id"),
            "wrapper_strategy": execution.get("wrapper_strategy"),
            "function_name": execution.get("function_name"),
            "selected_step_index": execution.get("selected_step_index"),
            "selected_method": execution.get("selected_method") or selected_step.get("method"),
            "wrapper_continuation_iteration_executed": bool(execution.get("wrapper_continuation_iteration_executed")),
            "paused_event_captured": bool(execution.get("paused_event_captured") or checkpoint.get("paused_event_captured")),
            "post_execution_event_harvest_observed": bool(events),
            "post_execution_event_harvest_status": events.get("status"),
            "post_execution_event_count": event_count,
            "paused_session_checkpoint_observed": bool(checkpoint),
            "paused_session_checkpoint_status": checkpoint.get("status"),
            "paused_session_checkpoint_ready": checkpoint_ready,
            "live_callframe_recovered": bool(checkpoint.get("live_callframe_recovered")),
            "next_iteration_available": bool(next_iteration.get("available")),
            "next_iteration_step_index": next_iteration.get("workflow_step_index"),
            "next_iteration_method": next_iteration.get("method"),
            "previous_checkpoint_status": previous.get("status"),
            "followup_requirements": {
                "wrapper_events_harvested": bool(events),
                "wrapper_events_non_empty": event_count > 0,
                "paused_session_checkpoint_ready": checkpoint_ready,
                "manual_review_required_before_next_iteration": True,
                "automatic_wrapper_continuation": False,
                "automatic_multi_step_loop": False,
            },
            "next_iteration_review_input": {
                "closure_wrapper_continuation_execution_plan": True,
                "closure_wrapper_continuation_checkpoint": True,
                "paused_session_cross_process_continuation_checkpoint": checkpoint,
                "paused_session_multi_step_loop_plan": loop_plan,
                "source_artifact": "workspace/closure-wrapper-continuation-checkpoint.json",
            },
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, checkpoint_ready=checkpoint_ready, next_iteration_available=bool(next_iteration.get("available"))),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_checkpoint_request_missing": ("request", "No wrapper continuation checkpoint request was provided.", "provide_wrapper_continuation_followup_artifacts"),
            "closure_wrapper_continuation_execution_required": ("execution", "The reviewed wrapper continuation execution artifact is required.", "execute_reviewed_closure_wrapper_continuation_iteration"),
            "closure_wrapper_continuation_execution_not_executed": ("execution", "The wrapper continuation execution did not complete one reviewed iteration.", "approve_closure_wrapper_continuation_iteration"),
            "automatic_wrapper_continuation_must_remain_disabled": ("safety", "Automatic wrapper continuation must remain disabled.", "disable_automatic_wrapper_continuation"),
            "automatic_multi_step_loop_must_remain_disabled": ("safety", "Automatic multi-step loops must remain disabled.", "disable_automatic_multi_step_loop"),
            "post_execution_event_harvest_requirement_missing": ("hook", "The execution artifact did not require post-execution wrapper event harvest.", "recreate_execution_artifact_with_followup_requirements"),
            "manual_continuation_checkpoint_requirement_missing": ("debugger", "The execution artifact did not require a manual continuation checkpoint.", "recreate_execution_artifact_with_followup_requirements"),
            "closure_wrapper_events_required": ("hook", "Wrapper event harvest evidence is required after execution.", "harvest_closure_wrapper_events_after_reviewed_execution"),
            "closure_wrapper_events_not_successful": ("hook", "Wrapper event harvest did not complete successfully.", "rerun_closure_wrapper_event_harvest"),
            "closure_wrapper_events_empty": ("hook", "Wrapper event harvest is empty; invoke the reviewed target flow or inspect wrapper coverage.", "invoke_target_flow_then_harvest_closure_wrapper_events"),
            "paused_session_continuation_checkpoint_required": ("debugger", "Paused-session continuation checkpoint evidence is required.", "checkpoint_cross_process_continuation"),
            "paused_session_continuation_checkpoint_not_ready": ("debugger", "Paused-session checkpoint is not ready for the next reviewed action.", "recover_live_callframe_or_checkpoint_continuation"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_checkpoint"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_checkpoint"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_checkpoint"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], checkpoint_ready: bool, next_iteration_available: bool) -> str:
        if blockers:
            if "closure_wrapper_events_required" in blockers or "closure_wrapper_events_empty" in blockers:
                return "harvest_wrapper_events_after_reviewed_execution"
            if "paused_session_continuation_checkpoint_required" in blockers or "paused_session_continuation_checkpoint_not_ready" in blockers:
                return "checkpoint_or_recover_paused_session_continuation"
            return "resolve_closure_wrapper_continuation_checkpoint_blockers"
        if status == "ready_for_review" and checkpoint_ready and next_iteration_available:
            return "review_next_closure_wrapper_continuation_iteration"
        if status == "ready_for_review":
            return "review_closure_wrapper_continuation_checkpoint"
        return "inspect_closure_wrapper_continuation_checkpoint"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "wrapper_events_harvested": False,
            "wrapper_continuation_iteration_executed": False,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperContinuationNextIterationPlanSpec:
    """Review-only plan for the next wrapper-aware continuation iteration."""

    continuation_checkpoint: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_loop_plan: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    previous_next_iteration_plan: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    requested: bool = False

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationNextIterationPlanSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_next_iteration_plan")
            or context.get("closureWrapperContinuationNextIterationPlan")
            or context.get("closure-wrapper-continuation-next-iteration-plan")
            or context.get("plan_closure_wrapper_continuation_next_iteration")
            or context.get("planClosureWrapperContinuationNextIteration")
            or context.get("wrapper_continuation_next_iteration_plan")
            or context.get("wrapperContinuationNextIterationPlan")
        )
        checkpoint_container = _first_dict(
            context,
            "closure_wrapper_continuation_checkpoint",
            "closureWrapperContinuationCheckpoint",
            "closure-wrapper-continuation-checkpoint",
            "wrapper_continuation_checkpoint",
            "wrapperContinuationCheckpoint",
        )
        checkpoint = dict(checkpoint_container.get("checkpoint")) if isinstance(checkpoint_container.get("checkpoint"), dict) else checkpoint_container
        execution_plan_container = _first_dict(
            context,
            "closure_wrapper_continuation_execution_plan",
            "closureWrapperContinuationExecutionPlan",
            "closure-wrapper-continuation-execution-plan",
            "wrapper_continuation_execution_plan",
            "wrapperContinuationExecutionPlan",
        )
        execution_plan = dict(execution_plan_container.get("plan")) if isinstance(execution_plan_container.get("plan"), dict) else execution_plan_container
        loop_container = _first_dict(
            context,
            "paused_session_multi_step_loop_plan",
            "pausedSessionMultiStepLoopPlan",
            "paused-session-multi-step-loop-plan",
            "multi_step_loop_plan",
            "multiStepLoopPlan",
            "loop_plan",
            "loopPlan",
        )
        loop_plan = dict(loop_container.get("loop_plan")) if isinstance(loop_container.get("loop_plan"), dict) else loop_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        previous_container = _first_dict(
            context,
            "previous_closure_wrapper_continuation_next_iteration_plan",
            "previousClosureWrapperContinuationNextIterationPlan",
            "previous-wrapper-continuation-next-iteration-plan",
        )
        previous = dict(previous_container.get("plan")) if isinstance(previous_container.get("plan"), dict) else previous_container
        if not requested and not any((checkpoint, execution_plan, loop_plan, recovery)):
            return None
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        return cls(
            continuation_checkpoint=checkpoint,
            execution_plan=execution_plan,
            multi_step_loop_plan=loop_plan,
            live_callframe_recovery=recovery,
            previous_next_iteration_plan=previous,
            reviewer=str(reviewer).strip() if reviewer else None,
            requested=requested,
        )


@dataclass(slots=True)
class ClosureWrapperContinuationNextIterationPlanResult:
    status: str
    plan: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-next-iteration-plan.v1",
            "status": self.status,
            "plan": self.plan,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
        }


class ClosureWrapperContinuationNextIterationPlanManager:
    """Plan the next reviewed wrapper-aware continuation iteration without execution."""

    def plan(self, spec: ClosureWrapperContinuationNextIterationPlanSpec | None) -> ClosureWrapperContinuationNextIterationPlanResult:
        blockers = self._blockers(spec)
        status = "blocked" if blockers else "ready_for_review"
        payload = self._payload(spec, status=status, blockers=blockers)
        return ClosureWrapperContinuationNextIterationPlanResult(
            status=status,
            plan=payload,
            side_effect_policy=self._side_effect_policy(),
            reason=blockers[0] if blockers else None,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationNextIterationPlanSpec | None) -> list[str]:
        if spec is None:
            return ["closure_wrapper_continuation_next_iteration_plan_request_missing"]
        blockers: list[str] = []
        checkpoint = spec.continuation_checkpoint
        execution_plan = spec.execution_plan
        loop_plan = spec.multi_step_loop_plan
        if not checkpoint:
            blockers.append("closure_wrapper_continuation_checkpoint_required")
        else:
            if checkpoint.get("status") != "ready_for_review" or checkpoint.get("ready_for_review") is not True:
                blockers.append("closure_wrapper_continuation_checkpoint_not_ready")
            if checkpoint.get("next_iteration_available") is not True:
                blockers.append("next_wrapper_iteration_not_available")
            requirements = checkpoint.get("followup_requirements") if isinstance(checkpoint.get("followup_requirements"), dict) else {}
            if requirements.get("manual_review_required_before_next_iteration") is not True:
                blockers.append("manual_review_requirement_missing")
            if requirements.get("automatic_wrapper_continuation") is not False:
                blockers.append("automatic_wrapper_continuation_must_remain_disabled")
            if requirements.get("automatic_multi_step_loop") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
        if not execution_plan:
            blockers.append("closure_wrapper_continuation_execution_plan_required")
        else:
            strategy = execution_plan.get("execution_strategy") if isinstance(execution_plan.get("execution_strategy"), dict) else {}
            if execution_plan.get("status") != "ready_for_review" or execution_plan.get("ready_for_review") is not True:
                blockers.append("closure_wrapper_continuation_execution_plan_not_ready")
            if execution_plan.get("same_process_wrapper_installed") is not True:
                blockers.append("same_process_wrapper_required")
            if execution_plan.get("restore_plan_available") is not True:
                blockers.append("closure_wrapper_restore_plan_required")
            if strategy.get("supported_strategy") != DEFAULT_CLOSURE_WRAPPER_STRATEGY:
                blockers.append("unsupported_wrapper_strategy")
            if strategy.get("automatic_wrapper_continuation_supported") is not False:
                blockers.append("automatic_wrapper_continuation_must_remain_disabled")
            if strategy.get("automatic_multi_step_loop_supported") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
        if not loop_plan:
            blockers.append("paused_session_multi_step_loop_plan_required")
        else:
            next_iteration = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
            readiness = loop_plan.get("readiness") if isinstance(loop_plan.get("readiness"), dict) else {}
            if loop_plan.get("status") != "ready_for_review":
                blockers.append("paused_session_multi_step_loop_plan_not_ready")
            if next_iteration.get("available") is not True:
                blockers.append("paused_session_next_iteration_not_available")
            if readiness.get("automatic_multi_step_loop_supported") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: ClosureWrapperContinuationNextIterationPlanSpec | None,
        *,
        status: str,
        blockers: list[str],
    ) -> dict[str, Any]:
        checkpoint = spec.continuation_checkpoint if spec else {}
        execution_plan = spec.execution_plan if spec else {}
        loop_plan = spec.multi_step_loop_plan if spec else {}
        recovery = spec.live_callframe_recovery if spec else {}
        previous = spec.previous_next_iteration_plan if spec else {}
        checkpoint_next = checkpoint.get("next_iteration_review_input") if isinstance(checkpoint.get("next_iteration_review_input"), dict) else {}
        loop_next = loop_plan.get("next_iteration") if isinstance(loop_plan.get("next_iteration"), dict) else {}
        ready = status == "ready_for_review"
        live_callframe_recovered = bool(recovery.get("live_callframe_recovered"))
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-next-iteration-plan.v1",
            "status": status,
            "ready_for_review": ready,
            "reviewer": spec.reviewer if spec else None,
            "plan_id": cls._plan_id(checkpoint, loop_next),
            "source_execution_plan_id": execution_plan.get("plan_id") or checkpoint.get("plan_id"),
            "source_workflow_id": checkpoint.get("workflow_id") or loop_plan.get("workflow_id"),
            "pause_session_id": checkpoint.get("pause_session_id") or loop_plan.get("pause_session_id"),
            "target_id": checkpoint.get("target_id") or loop_plan.get("target_id"),
            "wrapper_strategy": checkpoint.get("wrapper_strategy") or execution_plan.get("wrapper_strategy"),
            "function_name": checkpoint.get("function_name") or execution_plan.get("function_name"),
            "source_checkpoint_status": checkpoint.get("status"),
            "source_checkpoint_ready": bool(checkpoint.get("ready_for_review")),
            "post_execution_event_count": checkpoint.get("post_execution_event_count", 0),
            "paused_session_checkpoint_status": checkpoint.get("paused_session_checkpoint_status"),
            "loop_plan_status": loop_plan.get("status"),
            "next_iteration_available": bool(checkpoint.get("next_iteration_available") and loop_next.get("available")),
            "next_iteration_step_index": checkpoint.get("next_iteration_step_index") or loop_next.get("workflow_step_index"),
            "next_iteration_method": checkpoint.get("next_iteration_method") or loop_next.get("method"),
            "next_iteration_fingerprint": loop_next.get("fingerprint"),
            "fresh_live_callframe_observed": live_callframe_recovered,
            "fresh_live_callframe_required_before_execution": not live_callframe_recovered,
            "previous_next_iteration_plan_status": previous.get("status"),
            "review_gates": {
                "checkpoint_ready": bool(checkpoint.get("ready_for_review")),
                "execution_plan_ready": bool(execution_plan.get("ready_for_review")),
                "loop_plan_ready": loop_plan.get("status") == "ready_for_review",
                "fresh_live_callframe_required_before_execution": not live_callframe_recovered,
                "manual_review_required_before_execution": True,
                "automatic_wrapper_continuation": False,
                "automatic_multi_step_loop": False,
            },
            "planned_steps": cls._planned_steps(live_callframe_recovered=live_callframe_recovered),
            "next_execution_review_input": {
                "closure_wrapper_continuation_execution": True,
                "closure_wrapper_continuation_execution_plan": execution_plan,
                "paused_session_multi_step_loop_plan": loop_plan,
                "paused_session_live_callframe_recovery": recovery,
                "selected_step_index": checkpoint.get("next_iteration_step_index") or loop_next.get("workflow_step_index"),
                "source_artifact": "workspace/closure-wrapper-continuation-next-iteration-plan.json",
                "requires_multi_step_workflow_artifact": "workspace/paused-session-multi-step-continuation-workflow.json",
                "requires_fresh_live_callframe": not live_callframe_recovered,
            },
            "source_review_input": checkpoint_next,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, live_callframe_recovered=live_callframe_recovered),
            "side_effect_policy": cls._side_effect_policy(),
        }

    @staticmethod
    def _plan_id(checkpoint: dict[str, Any], next_iteration: dict[str, Any]) -> str:
        base = checkpoint.get("plan_id") or checkpoint.get("workflow_id") or "closure-wrapper-continuation"
        step = checkpoint.get("next_iteration_step_index") or next_iteration.get("workflow_step_index") or "next"
        return f"{base}:next-iteration:{step}"

    @staticmethod
    def _planned_steps(*, live_callframe_recovered: bool) -> list[dict[str, Any]]:
        steps = [
            {
                "step": "review_checkpoint_and_next_iteration_plan",
                "status": "planned",
                "side_effects": False,
                "expected_artifact": "workspace/closure-wrapper-continuation-next-iteration-plan.json",
            }
        ]
        if not live_callframe_recovered:
            steps.append(
                {
                    "step": "recover_fresh_live_callframe_before_execution",
                    "status": "planned",
                    "side_effects": False,
                    "expected_artifact": "workspace/paused-session-live-callframe-recovery.json",
                }
            )
        steps.append(
            {
                "step": "approve_one_wrapper_aware_continuation_iteration",
                "status": "planned",
                "side_effects": False,
                "expected_artifact": "workspace/closure-wrapper-continuation-execution.json",
            }
        )
        return steps

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_next_iteration_plan_request_missing": ("request", "No wrapper continuation next-iteration plan request was provided.", "request_closure_wrapper_continuation_next_iteration_plan"),
            "closure_wrapper_continuation_checkpoint_required": ("checkpoint", "A ready wrapper continuation checkpoint is required.", "checkpoint_closure_wrapper_continuation_after_execution"),
            "closure_wrapper_continuation_checkpoint_not_ready": ("checkpoint", "The wrapper continuation checkpoint is not ready for next-iteration planning.", "review_closure_wrapper_continuation_checkpoint"),
            "next_wrapper_iteration_not_available": ("checkpoint", "The checkpoint did not expose a next wrapper-aware iteration.", "replan_paused_session_loop_or_stop"),
            "manual_review_requirement_missing": ("review", "The checkpoint must require manual review before the next iteration.", "recreate_checkpoint_with_manual_review_requirement"),
            "automatic_wrapper_continuation_must_remain_disabled": ("safety", "Automatic wrapper continuation must remain disabled.", "disable_automatic_wrapper_continuation"),
            "automatic_multi_step_loop_must_remain_disabled": ("safety", "Automatic multi-step loops must remain disabled.", "disable_automatic_multi_step_loop"),
            "closure_wrapper_continuation_execution_plan_required": ("plan", "The previous ready wrapper continuation execution plan is required.", "provide_closure_wrapper_continuation_execution_plan"),
            "closure_wrapper_continuation_execution_plan_not_ready": ("plan", "The wrapper continuation execution plan is not ready.", "review_closure_wrapper_continuation_execution_plan"),
            "same_process_wrapper_required": ("wrapper", "A same-process reviewed wrapper must already be installed.", "install_reviewed_same_process_closure_wrapper"),
            "closure_wrapper_restore_plan_required": ("wrapper", "A restore plan is required before any wrapper-aware continuation execution.", "capture_closure_wrapper_restore_plan"),
            "unsupported_wrapper_strategy": ("wrapper", "Only log-only-call-through wrapper continuation is supported.", "choose_log_only_call_through_strategy"),
            "paused_session_multi_step_loop_plan_required": ("debugger", "A ready paused-session multi-step loop plan is required.", "plan_paused_session_continuation_loop"),
            "paused_session_multi_step_loop_plan_not_ready": ("debugger", "The paused-session loop plan is not ready.", "review_paused_session_multi_step_loop_plan"),
            "paused_session_next_iteration_not_available": ("debugger", "The paused-session loop plan did not expose a next iteration.", "replan_paused_session_continuation_loop"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_next_iteration_plan"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_next_iteration_plan"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_continuation_next_iteration_plan"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], live_callframe_recovered: bool) -> str:
        if blockers:
            if "closure_wrapper_continuation_checkpoint_required" in blockers or "closure_wrapper_continuation_checkpoint_not_ready" in blockers:
                return "review_closure_wrapper_continuation_checkpoint"
            if "paused_session_multi_step_loop_plan_required" in blockers or "paused_session_multi_step_loop_plan_not_ready" in blockers:
                return "review_paused_session_multi_step_loop_plan"
            return "resolve_closure_wrapper_continuation_next_iteration_plan_blockers"
        if status == "ready_for_review" and not live_callframe_recovered:
            return "recover_live_callframe_for_next_wrapper_iteration"
        if status == "ready_for_review":
            return "review_next_closure_wrapper_continuation_execution"
        return "inspect_closure_wrapper_continuation_next_iteration_plan"

    @staticmethod
    def _side_effect_policy() -> dict[str, Any]:
        return {
            "read_only": True,
            "review_only": True,
            "plan_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": False,
            "debugger_event_subscribed": False,
            "paused_event_captured": False,
            "browser_resumed": False,
            "debugger_stepped": False,
            "callframe_evaluated": False,
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "wrapper_events_harvested": False,
            "live_callframe_recovered": False,
            "wrapper_continuation_iteration_executed": False,
            "queue_advanced": False,
            "loop_advanced": False,
            "next_iteration_planned": True,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }


@dataclass(slots=True)
class ClosureWrapperContinuationNextIterationExecutionSpec:
    """Review-gated execution of exactly one planned wrapper-aware next iteration."""

    next_iteration_plan: dict[str, Any] = field(default_factory=dict)
    multi_step_workflow: dict[str, Any] = field(default_factory=dict)
    live_callframe_recovery: dict[str, Any] = field(default_factory=dict)
    cross_process_attach_probe: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    execute_iteration: bool = False
    review_approved: bool = False
    selected_step_index: int | None = None
    pause_session_id: str | None = None
    target_id: str | None = None
    attached_session_id: str | None = None
    live_callframe_id: str | None = None
    timeout_ms: int = 5000
    observed_paused_event: dict[str, Any] = field(default_factory=dict)
    reviewer: str | None = None
    require_matching_session_id: bool = True

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "ClosureWrapperContinuationNextIterationExecutionSpec | None":
        context = context or {}
        requested = bool(
            context.get("closure_wrapper_continuation_next_iteration_execution")
            or context.get("closureWrapperContinuationNextIterationExecution")
            or context.get("closure-wrapper-continuation-next-iteration-execution")
            or context.get("execute_closure_wrapper_continuation_next_iteration")
            or context.get("executeClosureWrapperContinuationNextIteration")
            or context.get("wrapper_continuation_next_iteration_execution")
            or context.get("wrapperContinuationNextIterationExecution")
        )
        next_plan_container = _first_dict(
            context,
            "closure_wrapper_continuation_next_iteration_plan",
            "closureWrapperContinuationNextIterationPlan",
            "closure-wrapper-continuation-next-iteration-plan",
            "wrapper_continuation_next_iteration_plan",
            "wrapperContinuationNextIterationPlan",
        )
        next_plan = dict(next_plan_container.get("plan")) if isinstance(next_plan_container.get("plan"), dict) else next_plan_container
        review_input = next_plan.get("next_execution_review_input") if isinstance(next_plan.get("next_execution_review_input"), dict) else {}
        execution_plan_container = _first_dict(
            context,
            "closure_wrapper_continuation_execution_plan",
            "closureWrapperContinuationExecutionPlan",
            "closure-wrapper-continuation-execution-plan",
            "wrapper_continuation_execution_plan",
            "wrapperContinuationExecutionPlan",
        )
        execution_plan = dict(execution_plan_container.get("plan")) if isinstance(execution_plan_container.get("plan"), dict) else execution_plan_container
        if not execution_plan and isinstance(review_input.get("closure_wrapper_continuation_execution_plan"), dict):
            execution_plan = dict(review_input["closure_wrapper_continuation_execution_plan"])
        workflow_container = _first_dict(
            context,
            "paused_session_multi_step_continuation_workflow",
            "pausedSessionMultiStepContinuationWorkflow",
            "paused-session-multi-step-continuation-workflow",
            "multi_step_continuation_workflow",
            "multiStepContinuationWorkflow",
            "continuation_workflow",
            "continuationWorkflow",
        )
        workflow = dict(workflow_container.get("workflow")) if isinstance(workflow_container.get("workflow"), dict) else workflow_container
        recovery_container = _first_dict(
            context,
            "paused_session_live_callframe_recovery",
            "pausedSessionLiveCallframeRecovery",
            "paused-session-live-callframe-recovery",
            "live_callframe_recovery",
            "liveCallframeRecovery",
        )
        recovery = dict(recovery_container.get("recovery")) if isinstance(recovery_container.get("recovery"), dict) else recovery_container
        if not recovery and isinstance(review_input.get("paused_session_live_callframe_recovery"), dict):
            recovery = dict(review_input["paused_session_live_callframe_recovery"])
        attach_container = _first_dict(
            context,
            "paused_session_cross_process_attach_probe",
            "pausedSessionCrossProcessAttachProbe",
            "paused-session-cross-process-attach-probe",
            "cross_process_attach_probe",
            "crossProcessAttachProbe",
        )
        attach_probe = dict(attach_container.get("probe")) if isinstance(attach_container.get("probe"), dict) else attach_container
        if not requested and not next_plan:
            return None
        index_raw = context.get(
            "selected_step_index",
            context.get("selectedStepIndex", context.get("step_index", context.get("stepIndex", review_input.get("selected_step_index") or next_plan.get("next_iteration_step_index") or 1))),
        )
        timeout_raw = context.get("timeout_ms", context.get("timeoutMs", 5000))
        try:
            selected_step_index = int(index_raw)
        except (TypeError, ValueError):
            selected_step_index = 1
        try:
            timeout_ms = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_ms = 5000
        execute_raw = context.get(
            "execute_closure_wrapper_continuation_next_iteration",
            context.get("executeClosureWrapperContinuationNextIteration", context.get("execute_next_iteration", context.get("executeNextIteration", False))),
        )
        approved_raw = context.get("review_approved", context.get("reviewApproved", context.get("approved", False)))
        event = _first_dict(context, "observed_paused_event", "observedPausedEvent", "debugger_paused_event", "debuggerPausedEvent", "paused_event", "pausedEvent")
        attached_session_id = context.get("attached_session_id") or context.get("attachedSessionId") or recovery.get("attached_session_id") or attach_probe.get("attached_session_id")
        live_callframe_id = context.get("live_callframe_id") or context.get("liveCallframeId") or context.get("callFrameId") or recovery.get("live_callframe_id")
        pause_session_id = context.get("pause_session_id") or context.get("pauseSessionId") or next_plan.get("pause_session_id") or workflow.get("pause_session_id") or recovery.get("pause_session_id")
        target_id = context.get("target_id") or context.get("targetId") or next_plan.get("target_id") or workflow.get("target_id") or recovery.get("target_id")
        reviewer = context.get("reviewer") or context.get("reviewer_id") or context.get("reviewerId")
        match_raw = context.get("require_matching_session_id", context.get("requireMatchingSessionId", True))
        return cls(
            next_iteration_plan=next_plan,
            multi_step_workflow=workflow,
            live_callframe_recovery=recovery,
            cross_process_attach_probe=attach_probe,
            execution_plan=execution_plan,
            execute_iteration=bool(execute_raw),
            review_approved=bool(approved_raw),
            selected_step_index=max(1, selected_step_index),
            pause_session_id=str(pause_session_id).strip() if pause_session_id else None,
            target_id=str(target_id).strip() if target_id else None,
            attached_session_id=str(attached_session_id).strip() if attached_session_id else None,
            live_callframe_id=str(live_callframe_id).strip() if live_callframe_id else None,
            timeout_ms=max(10, timeout_ms),
            observed_paused_event=event,
            reviewer=str(reviewer).strip() if reviewer else None,
            require_matching_session_id=bool(match_raw),
        )


@dataclass(slots=True)
class ClosureWrapperContinuationNextIterationExecutionResult:
    status: str
    execution: dict[str, Any] = field(default_factory=dict)
    side_effect_policy: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-next-iteration-execution.v1",
            "status": self.status,
            "execution": self.execution,
            "side_effect_policy": self.side_effect_policy,
            "reason": self.reason,
            "error": self.error,
        }


class ClosureWrapperContinuationNextIterationExecutionManager:
    """Execute exactly one reviewed next iteration planned by Step 196."""

    def execute(self, page: BrowserPage | None, spec: ClosureWrapperContinuationNextIterationExecutionSpec | None) -> ClosureWrapperContinuationNextIterationExecutionResult:
        blockers = self._blockers(spec)
        if blockers:
            payload = self._payload(spec, status="blocked", blockers=blockers)
            return ClosureWrapperContinuationNextIterationExecutionResult(status="blocked", execution=payload, side_effect_policy=self._side_effect_policy({}), reason=blockers[0])
        if spec and not spec.execute_iteration:
            payload = self._payload(spec, status="ready_for_review", blockers=[])
            return ClosureWrapperContinuationNextIterationExecutionResult(status="ready_for_review", execution=payload, side_effect_policy=self._side_effect_policy({}))
        if spec and not spec.review_approved:
            payload = self._payload(spec, status="review_required", blockers=["review_approval_required"])
            return ClosureWrapperContinuationNextIterationExecutionResult(status="review_required", execution=payload, side_effect_policy=self._side_effect_policy({}), reason="review_approval_required")
        assert spec is not None
        inner = ClosureWrapperContinuationExecutionManager().execute(
            page,
            ClosureWrapperContinuationExecutionSpec(
                execution_plan=spec.execution_plan,
                multi_step_workflow=spec.multi_step_workflow,
                live_callframe_recovery=spec.live_callframe_recovery,
                cross_process_attach_probe=spec.cross_process_attach_probe,
                execute_iteration=True,
                review_approved=True,
                selected_step_index=spec.selected_step_index or 1,
                pause_session_id=spec.pause_session_id,
                target_id=spec.target_id,
                attached_session_id=spec.attached_session_id,
                live_callframe_id=spec.live_callframe_id,
                timeout_ms=spec.timeout_ms,
                observed_paused_event=spec.observed_paused_event,
                reviewer=spec.reviewer,
                require_matching_session_id=spec.require_matching_session_id,
            ),
        )
        status = "executed" if inner.status == "executed" else inner.status
        blockers_after = [] if status == "executed" else [inner.reason or "wrapper_next_iteration_execution_failed"]
        payload = self._payload(
            spec,
            status=status,
            blockers=blockers_after,
            inner_result=inner.execution,
            inner_policy=inner.side_effect_policy,
            error=inner.error,
        )
        return ClosureWrapperContinuationNextIterationExecutionResult(
            status=status,
            execution=payload,
            side_effect_policy=self._side_effect_policy(inner.side_effect_policy),
            reason=blockers_after[0] if blockers_after else None,
            error=inner.error,
        )

    @classmethod
    def _blockers(cls, spec: ClosureWrapperContinuationNextIterationExecutionSpec | None) -> list[str]:
        if spec is None:
            return ["closure_wrapper_continuation_next_iteration_execution_request_missing"]
        blockers: list[str] = []
        plan = spec.next_iteration_plan
        gates = plan.get("review_gates") if isinstance(plan.get("review_gates"), dict) else {}
        if not plan:
            blockers.append("closure_wrapper_continuation_next_iteration_plan_required")
        else:
            if plan.get("status") != "ready_for_review" or plan.get("ready_for_review") is not True:
                blockers.append("closure_wrapper_continuation_next_iteration_plan_not_ready")
            if plan.get("next_iteration_available") is not True:
                blockers.append("next_wrapper_iteration_not_available")
            if gates.get("manual_review_required_before_execution") is not True:
                blockers.append("manual_review_requirement_missing")
            if gates.get("automatic_wrapper_continuation") is not False:
                blockers.append("automatic_wrapper_continuation_must_remain_disabled")
            if gates.get("automatic_multi_step_loop") is not False:
                blockers.append("automatic_multi_step_loop_must_remain_disabled")
        if not spec.execution_plan:
            blockers.append("closure_wrapper_continuation_execution_plan_required")
        if not spec.multi_step_workflow:
            blockers.append("multi_step_workflow_required")
        elif spec.multi_step_workflow.get("status") != "ready_for_review":
            blockers.append("multi_step_workflow_not_ready")
        if not spec.live_callframe_recovery:
            blockers.append("live_callframe_recovery_required")
        elif spec.live_callframe_recovery.get("status") == "blocked" or not spec.live_callframe_recovery.get("live_callframe_recovered"):
            blockers.append("live_callframe_recovery_blocked")
        if not spec.attached_session_id:
            blockers.append("attached_session_id_required")
        if not spec.live_callframe_id:
            blockers.append("live_callframe_id_required")
        expected_step = plan.get("next_iteration_step_index")
        if expected_step is not None and spec.selected_step_index is not None:
            try:
                if int(expected_step) != int(spec.selected_step_index):
                    blockers.append("selected_step_mismatch")
            except (TypeError, ValueError):
                blockers.append("selected_step_mismatch")
        return list(dict.fromkeys(blockers))

    @classmethod
    def _payload(
        cls,
        spec: ClosureWrapperContinuationNextIterationExecutionSpec | None,
        *,
        status: str,
        blockers: list[str],
        inner_result: dict[str, Any] | None = None,
        inner_policy: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        plan = spec.next_iteration_plan if spec else {}
        workflow = spec.multi_step_workflow if spec else {}
        inner = inner_result or {}
        selected = inner.get("selected_step") if isinstance(inner.get("selected_step"), dict) else {}
        policy = cls._side_effect_policy(inner_policy or {})
        return {
            "schema_version": "reverse-deepagent.closure-wrapper-continuation-next-iteration-execution.v1",
            "status": status,
            "next_iteration_plan_id": plan.get("plan_id"),
            "source_execution_plan_id": plan.get("source_execution_plan_id"),
            "workflow_id": workflow.get("workflow_id") or plan.get("source_workflow_id"),
            "pause_session_id": spec.pause_session_id if spec else plan.get("pause_session_id"),
            "target_id": spec.target_id if spec else plan.get("target_id"),
            "reviewer": spec.reviewer if spec else None,
            "wrapper_strategy": plan.get("wrapper_strategy"),
            "function_name": plan.get("function_name"),
            "selected_step_index": spec.selected_step_index if spec else plan.get("next_iteration_step_index"),
            "selected_method": inner.get("selected_method") or selected.get("method") or plan.get("next_iteration_method"),
            "execute_iteration_requested": bool(spec and spec.execute_iteration),
            "review_approved": bool(spec and spec.review_approved),
            "next_iteration_plan_ready": bool(plan.get("ready_for_review")),
            "fresh_live_callframe_observed": bool(spec and spec.live_callframe_recovery.get("live_callframe_recovered")),
            "executor_artifact": "workspace/closure-wrapper-continuation-execution.json",
            "executor_result": inner,
            "executor_status": inner.get("status"),
            "paused_event_captured": bool(inner.get("paused_event_captured")),
            "manual_checkpoint_required_after_step": True,
            "post_execution_event_harvest_required": True,
            "expected_followup_checkpoint": "workspace/paused-session-cross-process-continuation-checkpoint.json",
            "expected_followup_wrapper_events": "workspace/closure-wrapper-events.json",
            "expected_followup_wrapper_checkpoint": "workspace/closure-wrapper-continuation-checkpoint.json",
            "wrapper_next_iteration_executed": status == "executed",
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "blockers": blockers,
            "blocker_details": cls._blocker_details(blockers),
            "reason": blockers[0] if blockers else None,
            "next_action": cls._next_action(status=status, blockers=blockers, paused_captured=bool(inner.get("paused_event_captured"))),
            "side_effect_policy": policy,
            "error": error,
        }

    @staticmethod
    def _side_effect_policy(inner_policy: dict[str, Any]) -> dict[str, Any]:
        cdp_sent = bool(inner_policy.get("cdp_command_sent"))
        return {
            "read_only": not cdp_sent,
            "review_only": True,
            "files_mutated": False,
            "artifacts_written_by_manager": False,
            "cdp_command_sent": cdp_sent,
            "debugger_event_subscribed": bool(inner_policy.get("debugger_event_subscribed")),
            "paused_event_captured": bool(inner_policy.get("paused_event_captured")),
            "browser_resumed": bool(inner_policy.get("browser_resumed")),
            "debugger_stepped": bool(inner_policy.get("debugger_stepped")),
            "callframe_evaluated": bool(inner_policy.get("callframe_evaluated")),
            "runtime_mutated": False,
            "wrapper_installed": False,
            "wrapper_restored": False,
            "wrapper_events_harvested": False,
            "live_callframe_recovered": False,
            "cross_process_action_executed": bool(inner_policy.get("cross_process_action_executed") or cdp_sent),
            "wrapper_continuation_iteration_executed": bool(inner_policy.get("wrapper_continuation_iteration_executed") or cdp_sent),
            "wrapper_next_iteration_executed": cdp_sent,
            "bounded_one_iteration_only": True,
            "queue_advanced": False,
            "loop_advanced": False,
            "automatic_wrapper_continuation": False,
            "automatic_multi_step_loop": False,
            "calls_mcp": False,
            "mobile_runtime_used": False,
        }

    @staticmethod
    def _blocker_details(blockers: list[str]) -> list[dict[str, Any]]:
        catalog = {
            "closure_wrapper_continuation_next_iteration_execution_request_missing": ("request", "No wrapper continuation next-iteration execution request was provided.", "request_closure_wrapper_continuation_next_iteration_execution"),
            "closure_wrapper_continuation_next_iteration_plan_required": ("plan", "A ready next-iteration plan is required before execution.", "plan_closure_wrapper_continuation_next_iteration"),
            "closure_wrapper_continuation_next_iteration_plan_not_ready": ("plan", "The next-iteration plan is not ready for execution review.", "review_closure_wrapper_continuation_next_iteration_plan"),
            "next_wrapper_iteration_not_available": ("plan", "The next-iteration plan did not expose an available next step.", "replan_closure_wrapper_continuation_next_iteration"),
            "manual_review_requirement_missing": ("review", "The plan must require manual review before execution.", "recreate_next_iteration_plan_with_manual_review_requirement"),
            "automatic_wrapper_continuation_must_remain_disabled": ("safety", "Automatic wrapper continuation must remain disabled.", "disable_automatic_wrapper_continuation"),
            "automatic_multi_step_loop_must_remain_disabled": ("safety", "Automatic multi-step loops must remain disabled.", "disable_automatic_multi_step_loop"),
            "closure_wrapper_continuation_execution_plan_required": ("plan", "The underlying wrapper continuation execution plan is required.", "provide_closure_wrapper_continuation_execution_plan"),
            "multi_step_workflow_required": ("workflow", "A ready multi-step paused-session workflow is required.", "provide_paused_session_multi_step_workflow"),
            "multi_step_workflow_not_ready": ("workflow", "The multi-step paused-session workflow is not ready.", "review_or_replan_multi_step_continuation_workflow"),
            "live_callframe_recovery_required": ("debugger", "Fresh live callFrame recovery evidence is required.", "recover_live_callframe_for_next_wrapper_iteration"),
            "live_callframe_recovery_blocked": ("debugger", "The supplied live callFrame recovery evidence is blocked.", "resolve_live_callframe_recovery_blockers"),
            "attached_session_id_required": ("debugger", "The retained attached session id is required.", "provide_attached_session_id"),
            "live_callframe_id_required": ("debugger", "The recovered live callFrame id is required.", "recover_live_callframe_for_next_wrapper_iteration"),
            "selected_step_mismatch": ("workflow", "The selected step does not match the reviewed next-iteration plan.", "select_reviewed_next_iteration_step"),
            "review_approval_required": ("review", "Executing the next wrapper-aware iteration requires explicit review approval.", "approve_closure_wrapper_next_iteration_execution"),
            "wrapper_next_iteration_execution_failed": ("runtime", "The delegated wrapper continuation executor failed.", "inspect_closure_wrapper_next_iteration_execution"),
        }
        return [
            {
                "code": blocker,
                "category": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_next_iteration_execution"))[0],
                "explanation": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_next_iteration_execution"))[1],
                "next_action": catalog.get(blocker, ("unknown", blocker, "inspect_closure_wrapper_next_iteration_execution"))[2],
            }
            for blocker in blockers
        ]

    @staticmethod
    def _next_action(*, status: str, blockers: list[str], paused_captured: bool) -> str:
        if status in {"ready_for_review", "review_required"}:
            return "approve_closure_wrapper_next_iteration_execution"
        if blockers:
            return "resolve_closure_wrapper_continuation_next_iteration_execution_blockers"
        if status == "executed" and paused_captured:
            return "harvest_wrapper_events_and_checkpoint_next_iteration"
        if status == "executed":
            return "harvest_closure_wrapper_events_after_next_iteration"
        return "inspect_closure_wrapper_next_iteration_execution"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
