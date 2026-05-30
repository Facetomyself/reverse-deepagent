from __future__ import annotations

import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser.base import BrowserPage


@dataclass(slots=True)
class BreakpointSpec:
    """Provider-neutral breakpoint request."""

    url_pattern: str
    line_number: int = 0
    column_number: int | None = None
    condition: str | None = None
    trigger_expression: str | None = None
    wait_after_trigger_ms: int = 0
    auto_resume: bool = True
    callframe_evaluations: list[str] = field(default_factory=list)
    callframe_index: int = 0
    callframe_evaluation_policy: str = "read_only"
    debugger_actions: list[str] = field(default_factory=list)
    preserve_pause_state: bool = False
    pause_session_id: str | None = None

    @classmethod
    def from_context(cls, context: dict[str, Any] | None = None) -> "BreakpointSpec | None":
        context = context or {}
        url_pattern = context.get("url_pattern") or context.get("url") or context.get("script_url")
        if not url_pattern:
            return None
        line_number = int(context.get("line_number", context.get("lineNumber", 0)) or 0)
        column_raw = context.get("column_number", context.get("columnNumber"))
        column_number = None if column_raw is None else int(column_raw)
        condition = context.get("condition")
        trigger_expression = context.get("trigger_expression", context.get("triggerExpression"))
        wait_raw = context.get("wait_after_trigger_ms", context.get("waitAfterTriggerMs", 0))
        evaluations_raw = (
            context.get("callframe_evaluations")
            or context.get("callframeEvaluations")
            or context.get("evaluate_on_callframe")
            or context.get("evaluateOnCallFrame")
        )
        debugger_actions_raw = (
            context.get("debugger_actions")
            or context.get("debuggerActions")
            or context.get("pause_actions")
            or context.get("pauseActions")
            or context.get("step_actions")
            or context.get("stepActions")
        )
        callframe_index_raw = context.get("callframe_index", context.get("callFrameIndex", 0))
        evaluation_policy_raw = context.get(
            "callframe_evaluation_policy",
            context.get("callframeEvaluationPolicy", context.get("evaluation_policy", context.get("evaluationPolicy"))),
        )
        allow_side_effects_raw = context.get(
            "allow_callframe_side_effects",
            context.get("allowCallframeSideEffects", context.get("allow_side_effects", context.get("allowSideEffects"))),
        )
        preserve_pause_state = bool(
            context.get(
                "preserve_pause_state",
                context.get("preservePauseState", context.get("keep_paused", context.get("keepPaused", False))),
            )
        )
        auto_resume_raw = context.get("auto_resume", context.get("autoResume"))
        return cls(
            url_pattern=str(url_pattern),
            line_number=line_number,
            column_number=column_number,
            condition=str(condition) if condition else None,
            trigger_expression=str(trigger_expression) if trigger_expression else None,
            wait_after_trigger_ms=int(wait_raw or 0),
            auto_resume=bool(auto_resume_raw) if auto_resume_raw is not None else not preserve_pause_state,
            callframe_evaluations=cls._coerce_evaluations(evaluations_raw),
            callframe_index=int(callframe_index_raw or 0),
            callframe_evaluation_policy=cls._normalize_evaluation_policy(
                evaluation_policy_raw,
                allow_side_effects=bool(allow_side_effects_raw),
            ),
            debugger_actions=cls._coerce_actions(debugger_actions_raw),
            preserve_pause_state=preserve_pause_state,
            pause_session_id=str(context.get("pause_session_id", context.get("pauseSessionId"))) if context.get("pause_session_id", context.get("pauseSessionId")) else None,
        )

    def to_cdp_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "urlRegex": self.url_pattern,
            "lineNumber": self.line_number,
        }
        if self.column_number is not None:
            params["columnNumber"] = self.column_number
        if self.condition:
            params["condition"] = self.condition
        return params

    @staticmethod
    def _coerce_evaluations(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            expressions: list[str] = []
            for item in value:
                if item is None:
                    continue
                expression = str(item).strip()
                if expression:
                    expressions.append(expression)
            return expressions
        return []

    @staticmethod
    def _coerce_actions(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if isinstance(value, Iterable) and not isinstance(value, (dict, bytes, bytearray)):
            actions: list[str] = []
            for item in value:
                if item is None:
                    continue
                action = str(item).strip()
                if action:
                    actions.append(action)
            return actions
        return []

    @staticmethod
    def _normalize_evaluation_policy(raw: Any, *, allow_side_effects: bool = False) -> str:
        if allow_side_effects:
            return "allow_side_effects"
        value = str(raw or "read_only").strip().replace("-", "_").lower()
        if value in {"allow", "allow_side_effect", "allow_side_effects", "unsafe", "mutation", "mutating"}:
            return "allow_side_effects"
        if value in {"block", "block_dangerous", "strict", "deny_dangerous"}:
            return "block_dangerous"
        return "read_only"


@dataclass(slots=True)
class BreakpointResult:
    status: str
    supported: bool
    breakpoints: list[dict[str, Any]] = field(default_factory=list)
    paused: dict[str, Any] = field(default_factory=dict)
    callframes: list[dict[str, Any]] = field(default_factory=list)
    callframe_evaluations: list[dict[str, Any]] = field(default_factory=list)
    debugger_actions: list[dict[str, Any]] = field(default_factory=list)
    debugger_session: dict[str, Any] = field(default_factory=dict)
    trigger: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "supported": self.supported,
            "count": len(self.breakpoints),
            "breakpoints": self.breakpoints,
            "paused": self.paused,
            "callframes": self.callframes,
            "callframe_count": len(self.callframes),
            "callframe_evaluations": self.callframe_evaluations,
            "callframe_evaluation_count": len(self.callframe_evaluations),
            "debugger_actions": self.debugger_actions,
            "debugger_action_count": len(self.debugger_actions),
            "debugger_session": self.debugger_session,
            "trigger": self.trigger,
            "error": self.error,
            "reason": self.reason,
        }


class BreakpointManager:
    """Set CDP breakpoints behind a provider-neutral capability gate."""

    def set_breakpoint(self, page: BrowserPage, spec: BreakpointSpec | None) -> BreakpointResult:
        if spec is None:
            return BreakpointResult(status="unsupported", supported=False, reason="missing_url_pattern")
        session = page.cdp_session()
        if session is None:
            return BreakpointResult(status="unsupported", supported=False, reason="cdp_session_unavailable")
        paused_events: list[dict[str, Any]] = []
        pause_subscription = self._subscribe_paused(session, paused_events, spec=spec)
        trigger: dict[str, Any] = {"attempted": False}
        try:
            session.send("Debugger.enable", {})
            payload = session.send("Debugger.setBreakpointByUrl", spec.to_cdp_params())
            trigger = self._run_trigger_expression(page, session, spec)
        except Exception as exc:
            return BreakpointResult(
                status="failed",
                supported=True,
                paused=self._paused_summary(paused_events, pause_subscription),
                callframes=self._callframes_from_paused(paused_events),
                callframe_evaluations=self._evaluations_from_paused(paused_events),
                debugger_actions=self._debugger_actions_from_paused(paused_events),
                debugger_session=self._debugger_session_snapshot(paused_events, spec),
                trigger=trigger,
                error=str(exc),
            )
        breakpoint_id = payload.get("breakpointId") if isinstance(payload, dict) else None
        locations = payload.get("locations", []) if isinstance(payload, dict) else []
        paused = self._paused_summary(paused_events, pause_subscription)
        callframes = self._callframes_from_paused(paused_events)
        evaluations = self._evaluations_from_paused(paused_events)
        debugger_actions = self._debugger_actions_from_paused(paused_events)
        debugger_session = self._debugger_session_snapshot(paused_events, spec)
        return BreakpointResult(
            status="success" if breakpoint_id else "partial",
            supported=True,
            breakpoints=[
                {
                    "breakpointId": breakpoint_id,
                    "urlPattern": spec.url_pattern,
                    "lineNumber": spec.line_number,
                    "columnNumber": spec.column_number,
                    "condition": spec.condition,
                    "locations": locations if isinstance(locations, list) else [],
                }
            ],
            paused=paused,
            callframes=callframes,
            callframe_evaluations=evaluations,
            debugger_actions=debugger_actions,
            debugger_session=debugger_session,
            trigger=trigger,
        )

    def _subscribe_paused(self, session: Any, paused_events: list[dict[str, Any]], *, spec: BreakpointSpec) -> dict[str, Any]:
        on = getattr(session, "on", None)
        if not callable(on):
            return {"supported": False, "reason": "cdp_event_subscription_unavailable"}

        def handle_paused(params: Any) -> None:
            first_pause = not paused_events
            paused = self._normalize_paused(params)
            paused["evaluations"] = []
            paused["debugger_actions"] = []
            paused_events.append(paused)
            if first_pause:
                paused["evaluations"] = self._evaluate_callframe_expressions(session, paused.get("callFrames", []), spec)
                paused["debugger_actions"] = self._run_debugger_actions(session, spec)
            if not self._should_auto_resume(spec, paused["debugger_actions"]):
                return
            try:
                session.send("Debugger.resume", {})
            except Exception as exc:
                paused_events[-1]["autoResumeError"] = str(exc)

        try:
            on("Debugger.paused", handle_paused)
        except Exception as exc:
            return {"supported": False, "reason": "cdp_event_subscription_failed", "error": str(exc)}
        return {"supported": True}

    def _run_trigger_expression(self, page: BrowserPage, session: Any, spec: BreakpointSpec) -> dict[str, Any]:
        if not spec.trigger_expression:
            return {"attempted": False}
        if not spec.auto_resume:
            expression = self._scheduled_trigger_expression(spec.trigger_expression)
            trigger_mode = "scheduled"
        else:
            expression = spec.trigger_expression
            trigger_mode = "direct"
        try:
            payload = session.send(
                "Runtime.evaluate",
                {
                    "expression": expression,
                    "awaitPromise": False,
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
        except Exception as exc:
            return {"attempted": True, "ok": False, "error": str(exc)}
        wait_after_trigger_ms = spec.wait_after_trigger_ms if spec.wait_after_trigger_ms > 0 else (1000 if trigger_mode == "scheduled" else 0)
        self._wait_after_trigger(page, wait_after_trigger_ms)
        return {
            "attempted": True,
            "ok": True,
            "mode": trigger_mode,
            "wait_after_trigger_ms": wait_after_trigger_ms,
            "result": payload if isinstance(payload, dict) else {"value": payload},
        }

    @staticmethod
    def _scheduled_trigger_expression(expression: str) -> str:
        return "setTimeout(() => {\n" + expression + "\n}, 0); 'reverse-agent-trigger-scheduled'"

    @staticmethod
    def _wait_after_trigger(page: BrowserPage, wait_after_trigger_ms: int) -> None:
        if wait_after_trigger_ms <= 0:
            return
        raw_page = getattr(page, "raw_page", None)
        wait_for_timeout = getattr(raw_page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            wait_for_timeout(wait_after_trigger_ms)
            return
        time.sleep(wait_after_trigger_ms / 1000)

    @classmethod
    def _paused_summary(cls, paused_events: list[dict[str, Any]], subscription: dict[str, Any]) -> dict[str, Any]:
        if paused_events:
            first = paused_events[0]
            return {
                "status": "success",
                "count": len(paused_events),
                "reason": first.get("reason"),
                "hitBreakpoints": first.get("hitBreakpoints", []),
                "subscription": subscription,
            }
        if subscription.get("supported"):
            return {"status": "not_observed", "count": 0, "subscription": subscription}
        return {"status": "unsupported", "count": 0, "subscription": subscription, "reason": subscription.get("reason")}

    @staticmethod
    def _callframes_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        frames = paused_events[0].get("callFrames", [])
        return frames if isinstance(frames, list) else []

    @staticmethod
    def _evaluations_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        evaluations = paused_events[0].get("evaluations", [])
        return evaluations if isinstance(evaluations, list) else []

    @staticmethod
    def _debugger_actions_from_paused(paused_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not paused_events:
            return []
        actions = paused_events[0].get("debugger_actions", [])
        return actions if isinstance(actions, list) else []

    def _debugger_session_snapshot(self, paused_events: list[dict[str, Any]], spec: BreakpointSpec) -> dict[str, Any]:
        session_id = spec.pause_session_id or self._default_pause_session_id(spec)
        events = [self._pause_event_summary(index, event) for index, event in enumerate(paused_events)]
        callframes = self._callframes_from_paused(paused_events)
        selected_callframe = callframes[spec.callframe_index] if 0 <= spec.callframe_index < len(callframes) else None
        selected_callframe_id = selected_callframe.get("callFrameId") if isinstance(selected_callframe, dict) else None
        debugger_actions = self._debugger_actions_from_paused(paused_events)
        lifecycle = self._pause_lifecycle(paused_events, spec, debugger_actions)
        return {
            "session_id": session_id,
            "status": "success" if paused_events else "not_observed",
            "lifecycle": lifecycle,
            "preserve_pause_state": spec.preserve_pause_state,
            "auto_resume": spec.auto_resume,
            "paused_event_count": len(paused_events),
            "selected_callframe_index": spec.callframe_index,
            "selected_callframe_id": selected_callframe_id,
            "selected_callframe": selected_callframe,
            "events": events,
            "debugger_action_count": len(debugger_actions),
        }

    @staticmethod
    def _default_pause_session_id(spec: BreakpointSpec) -> str:
        return f"breakpoint:{spec.url_pattern}:{spec.line_number}:{spec.column_number if spec.column_number is not None else 0}"

    @staticmethod
    def _pause_event_summary(index: int, event: dict[str, Any]) -> dict[str, Any]:
        frames = event.get("callFrames", []) if isinstance(event.get("callFrames"), list) else []
        top = frames[0] if frames and isinstance(frames[0], dict) else {}
        summary = {
            "index": index,
            "reason": event.get("reason"),
            "hitBreakpoints": event.get("hitBreakpoints", []),
            "callframe_count": len(frames),
            "top_function": top.get("functionName"),
            "top_url": top.get("url"),
            "top_location": top.get("location"),
        }
        if event.get("autoResumeError"):
            summary["autoResumeError"] = event.get("autoResumeError")
        return summary

    @staticmethod
    def _pause_lifecycle(paused_events: list[dict[str, Any]], spec: BreakpointSpec, debugger_actions: list[dict[str, Any]]) -> str:
        if not paused_events:
            return "not_observed"
        successful_methods = {str(item.get("method")) for item in debugger_actions if item.get("ok") and item.get("method")}
        if successful_methods:
            return "action_controlled"
        if not spec.auto_resume:
            return "retained_paused"
        return "auto_resumed"

    @classmethod
    def _normalize_paused(cls, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return {"reason": "unknown", "callFrames": [], "rawType": type(params).__name__}
        callframes = [cls._normalize_callframe(frame) for frame in params.get("callFrames", []) if isinstance(frame, dict)]
        return {
            "reason": params.get("reason"),
            "hitBreakpoints": params.get("hitBreakpoints", []) if isinstance(params.get("hitBreakpoints"), list) else [],
            "callFrames": callframes,
            "callframe_count": len(callframes),
        }

    def _evaluate_callframe_expressions(self, session: Any, callframes: list[dict[str, Any]], spec: BreakpointSpec) -> list[dict[str, Any]]:
        if not spec.callframe_evaluations:
            return []
        if spec.callframe_index < 0 or spec.callframe_index >= len(callframes):
            return [
                {
                    "expression": expression,
                    "ok": False,
                    "error": "callframe_index_out_of_range",
                    "callframe_index": spec.callframe_index,
                }
                for expression in spec.callframe_evaluations
            ]
        callframe = callframes[spec.callframe_index]
        callframe_id = callframe.get("callFrameId")
        if not callframe_id:
            return [
                {
                    "expression": expression,
                    "ok": False,
                    "error": "callframe_id_unavailable",
                    "callframe_index": spec.callframe_index,
                }
                for expression in spec.callframe_evaluations
            ]
        evaluations: list[dict[str, Any]] = []
        for expression in spec.callframe_evaluations:
            decision = self._evaluation_policy_decision(expression, spec.callframe_evaluation_policy)
            if decision["blocked"]:
                evaluations.append(
                    {
                        "expression": expression,
                        "ok": False,
                        "blocked": True,
                        "error": "blocked_by_callframe_evaluation_policy",
                        "callframe_index": spec.callframe_index,
                        "callFrameId": callframe_id,
                        **decision,
                    }
                )
                continue
            try:
                payload = session.send(
                    "Debugger.evaluateOnCallFrame",
                    {
                        "callFrameId": callframe_id,
                        "expression": expression,
                        "returnByValue": True,
                        "silent": True,
                        "throwOnSideEffect": decision["throw_on_side_effect"],
                    },
                )
                evaluations.append(
                    self._with_evaluation_policy_metadata(
                        self._normalize_callframe_evaluation(expression, payload, spec.callframe_index, str(callframe_id)),
                        decision,
                    )
                )
            except Exception as exc:
                evaluations.append(
                    {
                        "expression": expression,
                        "ok": False,
                        "error": str(exc),
                        "callframe_index": spec.callframe_index,
                        "callFrameId": callframe_id,
                        **decision,
                    }
                )
        return evaluations

    @staticmethod
    def _evaluation_policy_decision(expression: str, policy: str) -> dict[str, Any]:
        risk, reason = BreakpointManager._side_effect_risk(expression)
        blocked = policy in {"read_only", "block_dangerous"} and risk == "high"
        return {
            "policy": policy,
            "side_effect_risk": risk,
            "side_effect_reason": reason,
            "blocked": blocked,
            "throw_on_side_effect": policy != "allow_side_effects",
        }

    @staticmethod
    def _side_effect_risk(expression: str) -> tuple[str, str]:
        compact = expression.strip()
        high_risk_patterns = (
            (r"(?<![=!<>])=(?!=|>)", "assignment-like expression"),
            (r"\+\+|--", "increment/decrement operator"),
            (r"\bdelete\s+", "delete operator"),
            (r"\bdocument\s*\.\s*cookie\s*=", "document.cookie write"),
            (r"\b(?:localStorage|sessionStorage)\s*\.\s*(?:setItem|removeItem|clear)\s*\(", "storage mutation"),
            (r"\b(?:fetch|XMLHttpRequest|sendBeacon)\s*\(", "network side effect candidate"),
            (r"\b(?:eval|Function)\s*\(", "dynamic code execution"),
            (r"\b(?:location|window\.location|document\.location)\s*=", "navigation mutation"),
        )
        for pattern, reason in high_risk_patterns:
            if re.search(pattern, compact):
                return "high", reason
        if re.search(r"\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?\s*\(", compact):
            return "medium", "function call; guarded by CDP throwOnSideEffect unless explicitly allowed"
        return "low", "read-only expression shape"

    @staticmethod
    def _with_evaluation_policy_metadata(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        result.update(decision)
        return result

    def _run_debugger_actions(self, session: Any, spec: BreakpointSpec) -> list[dict[str, Any]]:
        if not spec.debugger_actions:
            return []
        results: list[dict[str, Any]] = []
        for action in spec.debugger_actions:
            method = self._normalize_debugger_action(action)
            if not method:
                results.append(
                    {
                        "action": action,
                        "ok": False,
                        "error": "unsupported_debugger_action",
                    }
                )
                continue
            try:
                payload = session.send(method, {})
                results.append(
                    {
                        "action": action,
                        "method": method,
                        "ok": True,
                        "result": payload if isinstance(payload, dict) else {"value": payload},
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "action": action,
                        "method": method,
                        "ok": False,
                        "error": str(exc),
                    }
                )
        return results

    @staticmethod
    def _should_auto_resume(spec: BreakpointSpec, debugger_actions: list[dict[str, Any]]) -> bool:
        if not spec.auto_resume:
            return False
        successful_methods = {str(item.get("method")) for item in debugger_actions if item.get("ok") and item.get("method")}
        return not successful_methods.intersection({"Debugger.resume", "Debugger.stepOver", "Debugger.stepInto", "Debugger.stepOut"})

    @staticmethod
    def _normalize_debugger_action(action: str) -> str | None:
        normalized = action.strip().replace("-", "_").lower()
        if normalized in {"resume"}:
            return "Debugger.resume"
        if normalized in {"step_over", "stepover", "over"}:
            return "Debugger.stepOver"
        if normalized in {"step_into", "stepinto", "into"}:
            return "Debugger.stepInto"
        if normalized in {"step_out", "stepout", "out"}:
            return "Debugger.stepOut"
        return None

    @staticmethod
    def _normalize_callframe_evaluation(expression: str, payload: Any, callframe_index: int, callframe_id: str) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "expression": expression,
                "ok": True,
                "value": payload,
                "valueType": type(payload).__name__,
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        if payload.get("exceptionDetails"):
            details = payload.get("exceptionDetails") if isinstance(payload.get("exceptionDetails"), dict) else {}
            return {
                "expression": expression,
                "ok": False,
                "error": details.get("text") or "evaluateOnCallFrame exception",
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
        if not isinstance(result, dict):
            return {
                "expression": expression,
                "ok": True,
                "value": result,
                "valueType": type(result).__name__,
                "callframe_index": callframe_index,
                "callFrameId": callframe_id,
            }
        value = result.get("value")
        if "unserializableValue" in result:
            value = result.get("unserializableValue")
        elif "value" not in result and "description" in result:
            value = result.get("description")
        return {
            "expression": expression,
            "ok": True,
            "value": value,
            "valueType": result.get("type"),
            "description": result.get("description"),
            "callframe_index": callframe_index,
            "callFrameId": callframe_id,
        }

    @staticmethod
    def _normalize_callframe(frame: dict[str, Any]) -> dict[str, Any]:
        location = frame.get("location") if isinstance(frame.get("location"), dict) else {}
        function_location = frame.get("functionLocation") if isinstance(frame.get("functionLocation"), dict) else {}
        url = frame.get("url")
        return {
            "callFrameId": frame.get("callFrameId"),
            "functionName": frame.get("functionName"),
            "url": url,
            "location": {
                "scriptId": location.get("scriptId"),
                "lineNumber": location.get("lineNumber"),
                "columnNumber": location.get("columnNumber"),
            },
            "functionLocation": {
                "scriptId": function_location.get("scriptId"),
                "lineNumber": function_location.get("lineNumber"),
                "columnNumber": function_location.get("columnNumber"),
            }
            if function_location
            else None,
            "scopeCount": len(frame.get("scopeChain", [])) if isinstance(frame.get("scopeChain"), list) else 0,
            "thisType": (frame.get("this") or {}).get("type") if isinstance(frame.get("this"), dict) else None,
        }
