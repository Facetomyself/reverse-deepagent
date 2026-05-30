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
