from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from reverse_deepagent.runtime.base import BrowserSessionInfo, ReverseRuntime, RuntimeBackendCapabilities, RuntimeExportBundle
from reverse_deepagent.runtime.mcp_stdio import StdioMcpBridge
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ProtectionResult,
    ReconResult,
    ReverseStage,
    RouterResult,
    TaskCard,
)


class JSReverserBridge(Protocol):
    """Bridge interface for invoking JSReverser capabilities from Python.

    The real implementation can talk to MCP, a local proxy, or any tool transport.
    """

    def invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        ...


DEFAULT_JSREVERSER_MCP_COMMAND = "/opt/homebrew/bin/jsreverser-mcp"
DEFAULT_REMOTE_DEBUGGING_URL = "http://127.0.0.1:9222"


def create_jsreverser_mcp_runtime(
    *,
    command: str = DEFAULT_JSREVERSER_MCP_COMMAND,
    browser_url: str = DEFAULT_REMOTE_DEBUGGING_URL,
    request_timeout: float = 30.0,
    startup_timeout: float = 15.0,
) -> "JSReverserRuntime":
    """Create a JSReverser runtime backed by a real stdio MCP process."""

    bridge = StdioMcpBridge(
        command=[command, "--browserUrl", browser_url],
        request_timeout=request_timeout,
        startup_timeout=startup_timeout,
    )
    return JSReverserRuntime(bridge=bridge)


@dataclass(slots=True)
class JSReverserRuntime(ReverseRuntime):
    """Runtime adapter backed by JSReverser capabilities."""

    bridge: JSReverserBridge
    backend_id: str = "jsreverser-mcp"
    display_name: str = "JSReverser MCP"
    transport: str = "mcp-stdio"
    default_page_size: int = 20
    post_navigation_wait_seconds: float = 0.5
    runtime_context_sample_count: int = 3
    runtime_context_sample_interval_seconds: float = 0.05

    def describe_capabilities(self) -> RuntimeBackendCapabilities:
        """Return capability metadata for the JSReverser-compatible runtime."""

        return RuntimeBackendCapabilities(
            backend_id=self.backend_id,
            display_name=self.display_name,
            transport=self.transport,
            target_platforms=["web"],
            supports_browser_session=True,
            supports_web_recon=True,
            supports_protection_patch=True,
            supports_artifact_export=True,
            supports_runtime_context=True,
            supports_replay_validation=True,
            managed_chrome=self.transport in {"mcp-stdio", "cdp", "browser-cli"},
            mcp_backed=self.transport == "mcp-stdio",
            evidence_kinds=["request", "callstack", "static", "dynamic", "storage", "note"],
            artifact_kinds=["json", "export", "rebuild", "markdown"],
            notes=[
                "web-first runtime adapter",
                "normalizes mixed MCP / text return shapes before exposing evidence",
            ],
            config={
                "default_page_size": self.default_page_size,
                "post_navigation_wait_seconds": self.post_navigation_wait_seconds,
                "runtime_context_sample_count": self.runtime_context_sample_count,
                "runtime_context_sample_interval_seconds": self.runtime_context_sample_interval_seconds,
            },
        )

    def ensure_browser_session(self) -> BrowserSessionInfo:
        health_payload = self._safe_invoke("check_browser_health", {})
        pages_payload = self._safe_invoke("list_pages", {})

        pages = self._extract_pages(pages_payload)
        selected_page_idx, active_url = self._pick_active_page(pages)
        healthy = self._coerce_healthy(health_payload)
        if not healthy and pages and not self._payload_has_failure(pages_payload):
            healthy = True

        return BrowserSessionInfo(
            healthy=healthy,
            page_count=len(pages),
            selected_page_idx=selected_page_idx,
            active_url=active_url,
            details={
                "health": health_payload,
                "pages": pages_payload,
            },
        )

    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        browser = self.ensure_browser_session()
        navigation_events: list[str] = []

        if not browser.healthy:
            return ReconResult(
                status=ExecutionStatus.FAILED,
                stage=ReverseStage.RECON,
                key_findings=KeyFindings(
                    facts=[],
                    inferences=["浏览器运行时不可用，无法继续 Web 侦察"],
                    unknowns=["尚未确认目标页面、网络请求和源码命中"],
                ),
                evidence=self._build_recon_evidence(browser, [], [], []),
                artifacts=[],
                next_action="ensure_browser_session",
                confidence=ConfidenceLevel.LOW,
            )

        if self._looks_like_url(task_card.target_url_or_file):
            selected_idx = browser.selected_page_idx if browser.selected_page_idx is not None else 0
            if browser.page_count <= 0:
                self._safe_invoke("new_page", {"url": task_card.target_url_or_file})
                navigation_events.append(f"opened_new_page:{task_card.target_url_or_file}")
                browser = browser.model_copy(update={"page_count": max(browser.page_count, 1), "selected_page_idx": selected_idx, "active_url": task_card.target_url_or_file})
            elif browser.active_url != task_card.target_url_or_file:
                self._safe_invoke("navigate_page", {"pageIdx": selected_idx, "type": "url", "url": task_card.target_url_or_file})
                navigation_events.append(f"navigated_page:{selected_idx}:{task_card.target_url_or_file}")
                browser = browser.model_copy(update={"active_url": task_card.target_url_or_file})
            self._run_post_navigation_probe(selected_idx, task_card.target_param_or_api, navigation_events)

        requests_payload = self._safe_invoke(
            "network_request",
            {
                "action": "list",
                "targetPageIdx": browser.selected_page_idx,
                "pageSize": self.default_page_size,
                "includePreservedRequests": True,
            },
        )
        source_payload = self._safe_invoke(
            "search_in_sources",
            {
                "query": task_card.target_param_or_api,
                "pageIdx": browser.selected_page_idx,
                "maxResults": self.default_page_size,
                "excludeMinified": False,
            },
        )

        request_items = self._extract_request_items(requests_payload)
        source_hits = self._extract_source_hits(source_payload)
        request_initiators = self._collect_request_initiators(task_card, request_items)
        source_contexts = self._collect_source_contexts(source_hits)
        runtime_context = self._collect_runtime_context(browser, source_contexts)
        runtime_context_diff = self._build_runtime_context_diff(runtime_context) if runtime_context else {}
        function_candidates = self._build_function_candidates(task_card, request_items, request_initiators, source_hits, source_contexts)
        function_validations = self._validate_function_candidates(task_card, function_candidates, browser)
        function_validation_summary = self._summarize_function_validations(function_validations)

        findings = KeyFindings(
            facts=self._build_fact_findings(
                browser,
                request_items,
                source_hits,
                navigation_events,
                request_initiators,
                source_contexts,
                runtime_context,
                function_candidates,
                function_validations,
            ),
            inferences=self._build_inference_findings(task_card, request_items, source_hits),
            unknowns=self._build_unknown_findings(task_card, request_items, source_hits),
        )
        evidence = self._build_recon_evidence(
            browser,
            request_items,
            source_hits,
            navigation_events,
            request_initiators,
            source_contexts,
            runtime_context,
            runtime_context_diff,
            function_candidates,
            function_validations,
            function_validation_summary,
        )
        artifacts = self._build_recon_artifacts(
            request_items,
            source_hits,
            request_initiators,
            source_contexts,
            runtime_context,
            runtime_context_diff,
            function_candidates,
            function_validations,
            function_validation_summary,
        )

        if not browser.healthy and not request_items and not source_hits:
            status = ExecutionStatus.FAILED
            confidence = ConfidenceLevel.LOW
            next_action = "ensure_browser_session"
        else:
            status = ExecutionStatus.SUCCESS if source_hits else ExecutionStatus.PARTIAL
            confidence = ConfidenceLevel.HIGH if function_validation_summary.get("replay_ready") else ConfidenceLevel.HIGH if source_hits else ConfidenceLevel.MEDIUM if request_items else ConfidenceLevel.LOW
            next_action = self._determine_next_action(source_hits, request_items, function_validation_summary)

        return ReconResult(
            status=status,
            stage=ReverseStage.RECON,
            key_findings=findings,
            evidence=evidence,
            artifacts=artifacts,
            next_action=next_action,
            confidence=confidence,
        )

    def apply_minimal_protection(self, protection_name: str, context: dict[str, Any] | None = None) -> ProtectionResult:
        context = context or {}
        applied_actions: list[str] = []
        verification: list[str] = []
        artifacts: list[ArtifactRef] = []

        normalized = protection_name.strip().lower()
        status = ExecutionStatus.PARTIAL
        confidence = ConfidenceLevel.MEDIUM

        if normalized in {"console.clear", "console-clear"}:
            script = "(() => { if (window.console) { window.console.clear = () => undefined; } })();"
            self._safe_invoke("inject_preload_script", {"script": script})
            applied_actions.append("inject_preload_script:disable_console_clear")
            verification.append("console.clear overridden in preload script")
            status = ExecutionStatus.SUCCESS
            confidence = ConfidenceLevel.HIGH
        elif normalized in {"debugger", "infinite debugger"}:
            script = context.get("script") or "window.__REVERSE_DEBUGGER_PATCH__ = true;"
            self._safe_invoke("inject_preload_script", {"script": script})
            applied_actions.append("inject_preload_script:debugger_patch")
            verification.append("debugger patch script injected")
            status = ExecutionStatus.PARTIAL
            confidence = ConfidenceLevel.MEDIUM
        elif normalized in {"devtools-size", "size detection", "尺寸检测"}:
            script = context.get("script") or "window.__REVERSE_DEVTOOLS_SIZE_PATCH__ = true;"
            self._safe_invoke("inject_preload_script", {"script": script})
            applied_actions.append("inject_preload_script:devtools_size_patch")
            verification.append("devtools size patch script injected")
            status = ExecutionStatus.PARTIAL
            confidence = ConfidenceLevel.MEDIUM
        elif normalized in {"redirect", "redirect / location", "location"}:
            script = context.get("script") or "window.__REVERSE_REDIRECT_PATCH__ = true;"
            self._safe_invoke("inject_preload_script", {"script": script})
            applied_actions.append("inject_preload_script:redirect_patch")
            verification.append("redirect patch script injected")
            status = ExecutionStatus.PARTIAL
            confidence = ConfidenceLevel.MEDIUM
        else:
            applied_actions.append(f"unsupported_protection:{protection_name}")
            verification.append("no built-in minimal patch available")
            status = ExecutionStatus.FAILED
            confidence = ConfidenceLevel.LOW

        artifacts.append(
            ArtifactRef(
                path=f"virtual://protection/{normalized}",
                kind=ArtifactKind.LOG,
                description="Protection attempt summary.",
                metadata={"protection_name": protection_name, "context": context},
            )
        )

        next_action = "resume_recon" if status != ExecutionStatus.FAILED else "manual_protection_triage"
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=applied_actions,
            verification=verification,
            status=status,
            artifacts=artifacts,
            next_action=next_action,
            confidence=confidence,
        )

    def export_reverse_artifacts(self, final_result: FinalResult | None = None) -> RuntimeExportBundle:
        exports: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []

        session_report = self._safe_invoke("export_session_report", {"format": "json", "includeHookData": True})
        exports.append({"tool": "export_session_report", "payload": session_report})
        artifacts.append(
            ArtifactRef(
                path="virtual://exports/session-report.json",
                kind=ArtifactKind.EXPORT,
                description="Serialized session report exported from JSReverser runtime.",
                metadata={"tool": "export_session_report"},
            ).model_dump()
        )

        return RuntimeExportBundle(final_result=final_result, exports=exports, artifacts=artifacts)

    def close(self) -> None:
        """Close the underlying bridge if it exposes a stop method."""

        stop = getattr(self.bridge, "stop", None)
        if callable(stop):
            stop()

    def _safe_invoke(self, tool_name: str, params: dict[str, Any]) -> Any:
        return self.bridge.invoke(tool_name, self._clean_params(params))

    def _optional_invoke(self, tool_name: str, params: dict[str, Any]) -> Any | None:
        try:
            return self._safe_invoke(tool_name, params)
        except Exception:
            return None

    def _collect_request_initiators(self, task_card: TaskCard, request_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        initiators: list[dict[str, Any]] = []
        for request_item in self._select_target_requests(task_card, request_items):
            request_id = self._coerce_int(request_item.get("id") or request_item.get("reqid") or request_item.get("requestId"))
            if request_id is None:
                continue
            payload = self._optional_invoke(
                "get_request_initiator",
                {
                    "requestId": request_id,
                    "targetUrl": task_card.target_url_or_file,
                    "goal": task_card.goal,
                },
            )
            if payload is None:
                continue
            initiators.append(
                {
                    "request": request_item,
                    "requestId": request_id,
                    "payload": payload,
                    "text": self._payload_text(payload) or json.dumps(payload, ensure_ascii=False),
                }
            )
        return initiators

    def _collect_source_contexts(self, source_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for hit in self._select_source_hits(source_hits):
            script_id = hit.get("scriptId") or hit.get("script_id")
            line_number = self._coerce_int(hit.get("lineNumber") or hit.get("line") or hit.get("line_number"))
            if script_id is None or line_number is None:
                continue
            payload = self._optional_invoke(
                "get_script_source",
                {
                    "scriptId": str(script_id),
                    "startLine": max(1, line_number - 3),
                    "endLine": line_number + 8,
                },
            )
            if payload is None:
                continue
            contexts.append(
                {
                    "hit": hit,
                    "scriptId": str(script_id),
                    "lineNumber": line_number,
                    "payload": payload,
                    "text": self._payload_text(payload) or self._extract_source_text(payload),
                }
            )
        return contexts

    def _collect_runtime_context(
        self,
        browser: BrowserSessionInfo,
        source_contexts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        requirements = self._detect_runtime_context_requirements(source_contexts)
        if not requirements:
            return {}

        page_idx = browser.selected_page_idx if browser.selected_page_idx is not None else 0
        sample_count = max(1, int(self.runtime_context_sample_count or 1))
        samples: list[dict[str, Any]] = []
        storage_raw: Any = None
        environment_raw: Any = None
        runtime_context: dict[str, Any] = {"detected_requirements": requirements}

        for sample_index in range(sample_count):
            storage_payload = self._optional_invoke("get_storage", {"pageIdx": page_idx, "type": "all"})
            env_payload = self._optional_invoke(
                "evaluate_script",
                {"pageIdx": page_idx, "function": self._runtime_context_probe_script()},
            )
            if sample_index == 0:
                storage_raw = storage_payload
                environment_raw = env_payload
            sample = self._merge_runtime_context_sample(storage_payload, env_payload)
            sample["sample_index"] = sample_index
            sample["collected_at_ms"] = int(time.time() * 1000)
            samples.append(sample)
            if sample_index < sample_count - 1 and self.runtime_context_sample_interval_seconds > 0:
                time.sleep(self.runtime_context_sample_interval_seconds)

        first_sample = samples[0] if samples else {}
        runtime_context["storage_raw"] = storage_raw
        runtime_context["environment_raw"] = environment_raw
        runtime_context["samples"] = samples
        for key in ("localStorage", "sessionStorage", "cookies", "navigator"):
            value = first_sample.get(key)
            if value:
                runtime_context[key] = value
        if "timezoneOffset" in first_sample:
            runtime_context["timezoneOffset"] = first_sample.get("timezoneOffset")

        captured = [
            requirement
            for requirement in requirements
            if self._runtime_context_has_requirement(runtime_context, requirement)
        ]
        runtime_context["captured_requirements"] = captured
        runtime_context["status"] = "complete" if set(captured) >= set(requirements) else "partial"
        return runtime_context

    @staticmethod
    def _runtime_context_probe_script() -> str:
        return """() => {
  const dumpStorage = (storage) => {
    const output = {};
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      output[key] = storage.getItem(key);
    }
    return output;
  };
  return {
  cookie: document.cookie || "",
  localStorage: dumpStorage(localStorage),
  sessionStorage: dumpStorage(sessionStorage),
  navigator: {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    language: navigator.language
  },
  timezoneOffset: new Date().getTimezoneOffset()
};}"""

    def _merge_runtime_context_sample(self, storage_payload: Any, env_payload: Any) -> dict[str, Any]:
        storage_context = self._normalize_storage_context(storage_payload)
        env_context = self._normalize_evaluate_result(env_payload)
        sample: dict[str, Any] = {}
        for key in ("localStorage", "sessionStorage", "cookies"):
            value = storage_context.get(key)
            if value:
                sample[key] = value
        if isinstance(env_context.get("localStorage"), dict):
            sample["localStorage"] = {**sample.get("localStorage", {}), **env_context["localStorage"]}
        if isinstance(env_context.get("sessionStorage"), dict):
            sample["sessionStorage"] = {**sample.get("sessionStorage", {}), **env_context["sessionStorage"]}
        if isinstance(env_context.get("navigator"), dict):
            sample["navigator"] = env_context["navigator"]
        if env_context.get("cookie") and "cookies" not in sample:
            sample["cookies"] = {"document.cookie": env_context.get("cookie")}
        if "timezoneOffset" in env_context:
            sample["timezoneOffset"] = env_context.get("timezoneOffset")
        return sample

    @classmethod
    def _build_runtime_context_diff(cls, runtime_context: dict[str, Any]) -> dict[str, Any]:
        """Build a conservative runtime context stability summary."""

        if not runtime_context:
            return {}

        requirements = [str(item) for item in runtime_context.get("detected_requirements", []) if item]
        captured = [str(item) for item in runtime_context.get("captured_requirements", []) if item]
        missing_requirements = [item for item in requirements if item not in captured]
        raw_samples = runtime_context.get("samples")
        samples = [item for item in raw_samples if isinstance(item, dict)] if isinstance(raw_samples, list) else []
        if len(samples) >= 2:
            return cls._build_multi_sample_runtime_context_diff(samples, requirements, captured, missing_requirements)

        sample = samples[0] if len(samples) == 1 else runtime_context
        flat = cls._filter_runtime_context_flattened(cls._flatten_runtime_context(sample))
        return {
            "status": "single_sample",
            "stable": not missing_requirements,
            "sample_count": 1,
            "requirements": requirements,
            "captured_requirements": captured,
            "stable_keys": sorted(flat),
            "volatile_keys": [],
            "missing_requirements": missing_requirements,
            "changes": {},
            "notes": ["single sample only; collect multiple samples to detect volatile context keys"],
        }

    @classmethod
    def _build_multi_sample_runtime_context_diff(
        cls,
        samples: list[dict[str, Any]],
        requirements: list[str],
        captured: list[str],
        missing_requirements: list[str],
    ) -> dict[str, Any]:
        flattened_samples = [cls._filter_runtime_context_flattened(cls._flatten_runtime_context(sample)) for sample in samples]
        all_keys = sorted({key for sample in flattened_samples for key in sample})
        stable_keys: list[str] = []
        volatile_keys: list[str] = []
        changes: dict[str, list[Any]] = {}
        for key in all_keys:
            values = [sample.get(key, "__MISSING__") for sample in flattened_samples]
            comparable = [cls._stable_json(value) for value in values]
            if len(set(comparable)) == 1:
                stable_keys.append(key)
            else:
                volatile_keys.append(key)
                unique_values: list[Any] = []
                seen: set[str] = set()
                for value, fingerprint in zip(values, comparable, strict=False):
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    unique_values.append(None if value == "__MISSING__" else value)
                    if len(unique_values) >= 5:
                        break
                changes[key] = unique_values
        return {
            "status": "multi_sample",
            "stable": not volatile_keys and not missing_requirements,
            "sample_count": len(samples),
            "requirements": requirements,
            "captured_requirements": captured,
            "stable_keys": stable_keys,
            "volatile_keys": volatile_keys,
            "missing_requirements": missing_requirements,
            "changes": changes,
            "notes": [
                "multi-sample runtime context diff; volatile keys should be treated as runtime-bound inputs",
                "sample_index and collected_at_ms are metadata and excluded from stability decisions",
            ],
        }

    @classmethod
    def _filter_runtime_context_flattened(cls, flat: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in flat.items()
            if not key.endswith("_raw")
            and key not in {"sample_index", "collected_at_ms"}
            and not key.startswith("environment_raw")
            and not key.startswith("storage_raw")
            and not key.startswith("samples.")
            and ".environment_raw" not in key
            and ".storage_raw" not in key
        }

    @staticmethod
    def _stable_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except TypeError:
            return str(value)

    @classmethod
    def _flatten_runtime_context(cls, value: Any, prefix: str = "") -> dict[str, Any]:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                output.update(cls._flatten_runtime_context(item, next_prefix))
            return output
        if isinstance(value, list):
            return {prefix: value}
        return {prefix: value}

    @classmethod
    def _detect_runtime_context_requirements(cls, source_contexts: list[dict[str, Any]]) -> list[str]:
        text = "\n".join(str(item.get("text") or item.get("source_context") or "") for item in source_contexts).lower()
        markers = {
            "cookie": ["document.cookie", "cookie"],
            "localStorage": ["localstorage"],
            "sessionStorage": ["sessionstorage"],
            "navigator": ["navigator.", "useragent", "platform"],
            "timezone": ["timezone", "gettimezoneoffset"],
            "canvas": ["canvas", "todataurl", "getimagedata"],
        }
        requirements: list[str] = []
        for name, needles in markers.items():
            if any(needle in text for needle in needles):
                requirements.append(name)
        return requirements

    @classmethod
    def _normalize_storage_context(cls, payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            embedded = cls._extract_embedded_json(payload)
            candidates = [payload, *[item for item in embedded if isinstance(item, dict)]]
        else:
            parsed = cls._parse_json_object(payload) if isinstance(payload, str) else None
            candidates = [parsed] if parsed else []

        normalized: dict[str, Any] = {}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for source_key, target_key in (
                ("localStorage", "localStorage"),
                ("local_storage", "localStorage"),
                ("sessionStorage", "sessionStorage"),
                ("session_storage", "sessionStorage"),
                ("cookies", "cookies"),
            ):
                if source_key not in candidate:
                    continue
                normalized[target_key] = cls._normalize_name_value_collection(candidate[source_key])
        return normalized

    @classmethod
    def _normalize_name_value_collection(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            result: dict[str, Any] = {}
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("key")
                item_value = item.get("value")
                if name is not None:
                    result[str(name)] = item_value
            return result
        return {}

    @staticmethod
    def _runtime_context_has_requirement(runtime_context: dict[str, Any], requirement: str) -> bool:
        if requirement == "localStorage":
            return bool(runtime_context.get("localStorage"))
        if requirement == "sessionStorage":
            return bool(runtime_context.get("sessionStorage"))
        if requirement == "cookie":
            return bool(runtime_context.get("cookies"))
        if requirement == "navigator":
            return bool(runtime_context.get("navigator"))
        if requirement == "timezone":
            return "timezoneOffset" in runtime_context
        if requirement == "canvas":
            return False
        return False

    def _build_function_candidates(
        self,
        task_card: TaskCard,
        request_items: list[dict[str, Any]],
        request_initiators: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
        source_contexts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        contexts_by_key: dict[tuple[str, int], dict[str, Any]] = {}
        for context in source_contexts:
            key = (str(context.get("scriptId", "")), int(context.get("lineNumber") or 0))
            contexts_by_key[key] = context

        candidates: list[dict[str, Any]] = []
        selected_hits = self._select_source_hits(source_hits, limit=3)
        related_requests = self._select_target_requests(task_card, request_items, limit=3)
        for hit in selected_hits:
            script_id = str(hit.get("scriptId") or hit.get("script_id") or "")
            line_number = self._coerce_int(hit.get("lineNumber") or hit.get("line") or hit.get("line_number")) or 0
            context = contexts_by_key.get((script_id, line_number), {})
            source_text = str(context.get("text") or hit.get("preview") or "")
            preview = str(hit.get("preview") or self._first_non_empty_line(source_text))
            function_name = self._extract_function_name(source_text) or self._extract_function_name(preview)
            if not function_name:
                continue
            candidate_id = f"{script_id}:{line_number}:{function_name}"
            confidence = ConfidenceLevel.HIGH.value if function_name != "unknown" and request_initiators else ConfidenceLevel.MEDIUM.value
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "function_name": function_name,
                    "file_url": hit.get("url"),
                    "script_id": script_id,
                    "line_number": line_number,
                    "target_param_or_api": task_card.target_param_or_api,
                    "preview": preview,
                    "source_context": source_text,
                    "related_requests": related_requests,
                    "request_initiators": request_initiators,
                    "confidence": confidence,
                    "next_actions": [
                        f"hook {function_name}",
                        "extract pure sign logic",
                        "replay /api request with rebuilt sign",
                    ],
                }
            )
        return candidates

    def _validate_function_candidates(
        self,
        task_card: TaskCard,
        function_candidates: list[dict[str, Any]],
        browser: BrowserSessionInfo,
    ) -> list[dict[str, Any]]:
        """Best-effort runtime validation for promoted function candidates.

        The validation intentionally stays adapter-local: upper layers get a
        normalized result without knowing whether the backend used MCP,
        Playwright, CDP, a CLI shim, or a future mobile runtime.
        """

        if not function_candidates or not browser.healthy:
            return []

        page_idx = browser.selected_page_idx if browser.selected_page_idx is not None else 0
        validations: list[dict[str, Any]] = []
        for candidate in function_candidates[:3]:
            function_name = str(candidate.get("function_name") or "")
            if not function_name:
                continue

            source_context = str(candidate.get("source_context") or "")
            source_complete = self._looks_like_complete_function_source(source_context, function_name)
            payload = self._optional_invoke(
                "evaluate_script",
                {
                    "pageIdx": page_idx,
                    "function": self._build_candidate_validation_script(task_card, candidate),
                },
            )
            runtime_result = self._normalize_evaluate_result(payload)
            checks = {
                "source_complete": source_complete,
                "runtime_located": bool(runtime_result.get("located")),
                "runtime_invocation_ok": bool(runtime_result.get("invocation_ok")),
                "sign_shape_ok": bool(runtime_result.get("sign_shape_ok")),
                "replay_attempted": bool((runtime_result.get("replay_result") or {}).get("attempted")),
                "replay_ok": bool((runtime_result.get("replay_result") or {}).get("ok")),
            }
            validation_status = self._validation_status_from_checks(checks)
            validations.append(
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "function_name": function_name,
                    "validation_status": validation_status,
                    "checks": checks,
                    "sample_input": {
                        "keyword": self._validation_keyword(task_card),
                        "timestamp": 1700000000000,
                    },
                    "sample_output": {
                        "callable_path": runtime_result.get("callable_path"),
                        "sign": runtime_result.get("sign"),
                        "invocation_result_type": runtime_result.get("invocation_result_type"),
                    },
                    "replay_result": runtime_result.get("replay_result") or {"attempted": False, "ok": False},
                    "runtime_url": runtime_result.get("runtime_url"),
                    "confidence": self._validation_confidence(validation_status, checks),
                    "next_action": self._validation_next_action(validation_status, checks),
                    "raw_runtime_result": runtime_result,
                }
            )
        return validations

    @staticmethod
    def _summarize_function_validations(function_validations: list[dict[str, Any]]) -> dict[str, Any]:
        if not function_validations:
            return {}

        success_items = [item for item in function_validations if item.get("validation_status") == ExecutionStatus.SUCCESS.value]
        replay_ready_items = [
            item
            for item in function_validations
            if bool((item.get("replay_result") or {}).get("ok"))
        ]
        partial_items = [item for item in function_validations if item.get("validation_status") == ExecutionStatus.PARTIAL.value]
        best_candidate = replay_ready_items[0] if replay_ready_items else success_items[0] if success_items else partial_items[0] if partial_items else function_validations[0]
        return {
            "total": len(function_validations),
            "success_count": len(success_items),
            "partial_count": len(partial_items),
            "failed_count": len([item for item in function_validations if item.get("validation_status") == ExecutionStatus.FAILED.value]),
            "replay_ready": bool(replay_ready_items),
            "best_candidate_id": best_candidate.get("candidate_id"),
            "best_function_name": best_candidate.get("function_name"),
            "next_action": "extract_pure_logic_and_build_replay" if replay_ready_items else "expand_runtime_validation",
        }

    def _build_candidate_validation_script(self, task_card: TaskCard, candidate: dict[str, Any]) -> str:
        function_name = str(candidate.get("function_name") or "")
        keyword = self._validation_keyword(task_card)
        serialized_function_name = json.dumps(function_name, ensure_ascii=False)
        serialized_keyword = json.dumps(keyword, ensure_ascii=False)
        return f"""async () => {{
  const marker = "__REVERSE_AGENT_VALIDATE_CANDIDATE__";
  const functionName = {serialized_function_name};
  const keyword = {serialized_keyword};
  const timestamp = 1700000000000;
  const holders = [
    {{ path: `window.${{functionName}}`, value: window[functionName] }},
    {{ path: `window.reverseFixture.${{functionName}}`, value: window.reverseFixture && window.reverseFixture[functionName] }}
  ];
  const located = holders.find((item) => typeof item.value === "function");
  if (!located) {{
    return {{
      marker,
      function_name: functionName,
      located: false,
      invocation_ok: false,
      sign_shape_ok: false,
      replay_result: {{ attempted: false, ok: false, reason: "function_not_located" }},
      runtime_url: location.href
    }};
  }}

  let invocationResult = null;
  let invocationOk = false;
  let invocationError = null;
  let sign = null;
  try {{
    if (/sign/i.test(functionName) || located.value.length >= 2) {{
      invocationResult = await located.value(keyword, timestamp);
      sign = invocationResult;
    }} else {{
      invocationResult = await located.value(keyword);
      sign = invocationResult && (
        (invocationResult.headers && invocationResult.headers["x-sign"]) ||
        (invocationResult.body && invocationResult.body.sign) ||
        invocationResult.sign
      );
    }}
    invocationOk = true;
  }} catch (error) {{
    invocationError = String(error && error.message ? error.message : error);
  }}

  const signShapeOk = typeof sign === "string" && sign.length > 0 && /sign|sig_|token|[a-f0-9]{{6,}}/i.test(sign);
  let replayResult = {{ attempted: false, ok: false, reason: "missing_sign" }};
  if (typeof sign === "string" && /^https?:$/.test(location.protocol)) {{
    const payload = {{ keyword, timestamp, sign, fixture: "reverse-agent-fixture" }};
    try {{
      const response = await fetch(`/api/search?keyword=${{encodeURIComponent(keyword)}}&t=${{timestamp}}`, {{
        method: "POST",
        headers: {{
          "content-type": "application/json",
          "x-sign": sign,
          "x-fixture": "reverse-agent-fixture"
        }},
        body: JSON.stringify(payload)
      }});
      const body = await response.json().catch(() => null);
      replayResult = {{
        attempted: true,
        ok: response.ok && !!body && body.headers && body.headers["x-sign"] === sign,
        status: response.status,
        echoed_sign: body && body.headers ? body.headers["x-sign"] : null,
        body
      }};
    }} catch (error) {{
      replayResult = {{
        attempted: true,
        ok: false,
        error: String(error && error.message ? error.message : error)
      }};
    }}
  }}

  return {{
    marker,
    function_name: functionName,
    located: true,
    callable_path: located.path,
    invocation_ok: invocationOk,
    invocation_error: invocationError,
    invocation_result_type: invocationResult === null ? "null" : Array.isArray(invocationResult) ? "array" : typeof invocationResult,
    sign,
    sign_shape_ok: signShapeOk,
    replay_result: replayResult,
    runtime_url: location.href
  }};
}}"""

    @classmethod
    def _normalize_evaluate_result(cls, payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            for key in ("result", "value", "data"):
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    parsed = cls._parse_json_object(value)
                    if parsed:
                        return parsed
            embedded = cls._extract_embedded_json(payload)
            for item in embedded:
                if isinstance(item, dict):
                    return item
            text = cls._payload_text(payload)
            parsed = cls._parse_json_object(text)
            if parsed:
                return parsed
            return payload
        if isinstance(payload, str):
            parsed = cls._parse_json_object(payload)
            return parsed or {"text": payload}
        return {}

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        stripped = text.strip()
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        first = stripped.find("{")
        last = stripped.rfind("}")
        if first >= 0 and last > first:
            try:
                parsed = json.loads(stripped[first : last + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _looks_like_complete_function_source(source_text: str, function_name: str) -> bool:
        if not source_text or function_name not in source_text:
            return False
        match = re.search(rf"\b(?:async\s+)?function\s+{re.escape(function_name)}\s*\(", source_text)
        if not match:
            return False
        depth = 0
        opened = False
        for char in source_text[match.start() :]:
            if char == "{":
                depth += 1
                opened = True
            elif char == "}":
                depth -= 1
                if opened and depth <= 0:
                    return True
        return False

    @staticmethod
    def _validation_status_from_checks(checks: dict[str, Any]) -> str:
        if checks.get("runtime_located") and checks.get("runtime_invocation_ok") and checks.get("replay_ok"):
            return ExecutionStatus.SUCCESS.value
        if checks.get("runtime_located") and checks.get("runtime_invocation_ok"):
            return ExecutionStatus.PARTIAL.value
        if checks.get("source_complete"):
            return ExecutionStatus.PARTIAL.value
        return ExecutionStatus.FAILED.value

    @staticmethod
    def _validation_confidence(validation_status: str, checks: dict[str, Any]) -> str:
        if validation_status == ExecutionStatus.SUCCESS.value and checks.get("replay_ok"):
            return ConfidenceLevel.HIGH.value
        if validation_status in {ExecutionStatus.SUCCESS.value, ExecutionStatus.PARTIAL.value}:
            return ConfidenceLevel.MEDIUM.value
        return ConfidenceLevel.LOW.value

    @staticmethod
    def _validation_next_action(validation_status: str, checks: dict[str, Any]) -> str:
        if validation_status == ExecutionStatus.SUCCESS.value and checks.get("replay_ok"):
            return "extract_pure_logic_and_build_replay"
        if checks.get("runtime_located"):
            return "stabilize_replay_sample"
        if checks.get("source_complete"):
            return "evaluate_candidate_in_runtime_scope"
        return "expand_source_context_or_hook_runtime"

    @staticmethod
    def _validation_keyword(task_card: TaskCard) -> str:
        target = (task_card.target_param_or_api or "").strip()
        lowered = target.lower()
        if not target or lowered in {"x-sign", "sign", "unknown-target"}:
            return "sign"
        if "/" in target:
            return "sign"
        return target[:32]

    def _select_target_requests(self, task_card: TaskCard, request_items: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
        target = task_card.target_param_or_api.lower()
        selected: list[dict[str, Any]] = []
        fallback: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in request_items:
            request_id = self._coerce_int(item.get("id") or item.get("reqid") or item.get("requestId"))
            if request_id is not None and request_id in seen:
                continue
            if request_id is not None:
                seen.add(request_id)
            url = str(item.get("url", "")).lower()
            method = str(item.get("method", "")).upper()
            if target and target != "unknown-target" and target in url:
                selected.append(item)
            elif "/api/" in url or method not in {"", "GET"}:
                fallback.append(item)
        return (selected + fallback)[:limit]

    def _select_source_hits(self, source_hits: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        fallback: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for hit in source_hits:
            url = str(hit.get("url", ""))
            line_number = self._coerce_int(hit.get("lineNumber") or hit.get("line") or hit.get("line_number")) or 0
            key = (url, line_number)
            if key in seen:
                continue
            seen.add(key)
            if url.startswith("pptr:") or "node_modules" in url:
                fallback.append(hit)
            else:
                selected.append(hit)
        return (selected + fallback)[:limit]

    @staticmethod
    def _extract_source_text(payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("source", "text", "content"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
        return ""

    @staticmethod
    def _first_non_empty_line(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    @staticmethod
    def _extract_function_name(text: str) -> str | None:
        patterns = [
            r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(",
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)",
            r"\b([A-Za-z_$][\w$]*)\s*:\s*function\s*\(",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None

    def _run_post_navigation_probe(self, page_idx: int, keyword: str, navigation_events: list[str]) -> None:
        if self.post_navigation_wait_seconds > 0:
            time.sleep(self.post_navigation_wait_seconds)
        escaped_keyword = json.dumps(keyword, ensure_ascii=False)
        script = f"""async () => {{
  await new Promise((resolve) => setTimeout(resolve, 250));
  if (window.reverseFixture && typeof window.reverseFixture.search === 'function') {{
    return await window.reverseFixture.search({escaped_keyword});
  }}
  return {{
    readyState: document.readyState,
    url: location.href,
    title: document.title
  }};
}}"""
        try:
            self._safe_invoke("evaluate_script", {"pageIdx": page_idx, "function": script})
            navigation_events.append(f"evaluated_page_probe:{page_idx}")
        except Exception:
            navigation_events.append(f"page_probe_unavailable:{page_idx}")

    @classmethod
    def _clean_params(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._clean_params(item) for key, item in value.items() if item is not None}
        if isinstance(value, list):
            return [cls._clean_params(item) for item in value]
        return value

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @classmethod
    def _coerce_healthy(cls, payload: Any) -> bool:
        if isinstance(payload, dict):
            parsed_json = cls._extract_embedded_json(payload)
            for item in parsed_json:
                if isinstance(item, dict):
                    for key in ("healthy", "ok", "connected", "ready"):
                        if key in item and item[key]:
                            return True
            text = cls._payload_text(payload)
            if cls._text_has_failure(text):
                return False
            for key in ("healthy", "ok", "connected", "ready"):
                if key in payload:
                    return bool(payload[key])
            status = payload.get("status")
            if isinstance(status, str):
                return status.lower() in {"ok", "healthy", "ready", "connected"}
        if isinstance(payload, str):
            return not cls._text_has_failure(payload)
        return bool(payload)

    @classmethod
    def _payload_has_failure(cls, payload: Any) -> bool:
        return cls._text_has_failure(cls._payload_text(payload))

    @staticmethod
    def _text_has_failure(text: str) -> bool:
        lowered_text = text.lower()
        return any(marker in lowered_text for marker in ("failed", "error", "cannot", "refused", "fetch failed"))

    @classmethod
    def _payload_text(cls, payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str):
                return text
            chunks: list[str] = []
            content = payload.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                        chunks.append(item["text"])
            return "\n".join(chunks)
        return ""

    @classmethod
    def _extract_embedded_json(cls, payload: Any) -> list[Any]:
        text = cls._payload_text(payload)
        if not text:
            return []

        candidates = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        parsed: list[Any] = []
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                parsed.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue
        return parsed

    @classmethod
    def _extract_list_from_payload(cls, payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            for item in cls._extract_embedded_json(payload):
                if isinstance(item, list):
                    return [entry for entry in item if isinstance(entry, dict)]
                if isinstance(item, dict):
                    for key in keys:
                        value = item.get(key)
                        if isinstance(value, list):
                            return [entry for entry in value if isinstance(entry, dict)]
        return []

    @classmethod
    def _extract_pages(cls, payload: Any) -> list[dict[str, Any]]:
        pages = cls._extract_list_from_payload(payload, ("pages", "items", "data", "result"))
        if pages:
            return pages

        text = cls._payload_text(payload)
        parsed_pages: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for line in text.splitlines():
            match = re.match(r"^\s*(?P<idx>\d+):\s+(?P<url>\S+)(?:\s+\[(?P<flags>[^\]]+)\])?\s*$", line)
            if not match:
                continue
            key = (int(match.group("idx")), match.group("url"))
            if key in seen:
                continue
            seen.add(key)
            flags = {item.strip().lower() for item in (match.group("flags") or "").split(",") if item.strip()}
            parsed_pages.append(
                {
                    "pageIdx": int(match.group("idx")),
                    "url": match.group("url"),
                    "selected": "selected" in flags,
                    "active": "active" in flags,
                }
            )
        return parsed_pages

    @staticmethod
    def _pick_active_page(pages: list[dict[str, Any]]) -> tuple[int | None, str | None]:
        if not pages:
            return None, None
        for idx, page in enumerate(pages):
            if page.get("selected") or page.get("active"):
                return int(page.get("pageIdx", idx)), page.get("url")
        page = pages[0]
        return int(page.get("pageIdx", 0)), page.get("url")

    @classmethod
    def _extract_request_items(cls, payload: Any) -> list[dict[str, Any]]:
        items = cls._extract_list_from_payload(payload, ("requests", "items", "data", "result"))
        if items:
            return items
        return cls._extract_markdown_requests(payload)

    @classmethod
    def _extract_source_hits(cls, payload: Any) -> list[dict[str, Any]]:
        items = cls._extract_list_from_payload(payload, ("matches", "results", "items", "data", "result"))
        if items:
            return items
        return cls._extract_markdown_source_hits(payload)

    @classmethod
    def _extract_markdown_requests(cls, payload: Any) -> list[dict[str, Any]]:
        text = cls._payload_text(payload)
        requests: list[dict[str, Any]] = []
        pattern = re.compile(r"^reqid=(?P<id>\d+)\s+(?P<method>[A-Z]+)\s+(?P<url>\S+)\s+\[(?P<status>[^\]]+)\]\s*$")
        for line in text.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            requests.append(
                {
                    "id": int(match.group("id")),
                    "method": match.group("method"),
                    "url": match.group("url"),
                    "status": match.group("status"),
                }
            )
        return requests

    @classmethod
    def _extract_markdown_source_hits(cls, payload: Any) -> list[dict[str, Any]]:
        text = cls._payload_text(payload)
        hits: list[dict[str, Any]] = []
        lines = text.splitlines()
        pattern = re.compile(r"^\[(?P<scriptId>[^\]]+)\]\s+(?P<url>.+):(?P<lineNumber>\d+)\s*$")
        for index, line in enumerate(lines):
            match = pattern.match(line.strip())
            if not match:
                continue
            preview = ""
            if index + 1 < len(lines):
                preview = lines[index + 1].strip()
            hits.append(
                {
                    "scriptId": match.group("scriptId"),
                    "url": match.group("url"),
                    "lineNumber": int(match.group("lineNumber")),
                    "preview": preview,
                }
            )
        return hits

    @staticmethod
    def _build_fact_findings(
        browser: BrowserSessionInfo,
        request_items: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
        navigation_events: list[str],
        request_initiators: list[dict[str, Any]] | None = None,
        source_contexts: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
        function_candidates: list[dict[str, Any]] | None = None,
        function_validations: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        facts: list[str] = []
        request_initiators = request_initiators or []
        source_contexts = source_contexts or []
        runtime_context = runtime_context or {}
        function_candidates = function_candidates or []
        function_validations = function_validations or []
        if browser.healthy:
            facts.append("浏览器运行时已连接并可用")
        if browser.active_url:
            facts.append(f"当前活动页面为 {browser.active_url}")
        if request_items:
            facts.append(f"已观察到 {len(request_items)} 条网络请求样本")
        if source_hits:
            facts.append(f"已命中 {len(source_hits)} 条源码搜索结果")
        if request_initiators:
            facts.append(f"已采集 {len(request_initiators)} 条请求发起链路证据")
        if source_contexts:
            facts.append(f"已拉取 {len(source_contexts)} 个源码上下文片段")
        captured_runtime_context = runtime_context.get("captured_requirements") if isinstance(runtime_context, dict) else []
        if captured_runtime_context:
            facts.append(f"已采集 {len(captured_runtime_context)} 项运行时上下文：{', '.join(captured_runtime_context)}")
        if function_candidates:
            facts.append(f"已生成 {len(function_candidates)} 张候选函数卡片")
        if function_validations:
            replay_ready_count = len([item for item in function_validations if bool((item.get("replay_result") or {}).get("ok"))])
            facts.append(f"已完成 {len(function_validations)} 条候选函数验证，其中 {replay_ready_count} 条 replay 校验通过")
        for event in navigation_events:
            facts.append(f"执行了导航动作：{event}")
        return facts

    @staticmethod
    def _build_inference_findings(
        task_card: TaskCard,
        request_items: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
    ) -> list[str]:
        inferences: list[str] = []
        if source_hits:
            inferences.append(f"参数或接口关键字 {task_card.target_param_or_api} 已出现在源码搜索结果中，建议进入 source 阶段定位入口")
        elif request_items:
            inferences.append("已拿到网络请求样本，但还缺少稳定的源码命中，下一步更适合做 initiator 或 source 扩展取证")
        else:
            inferences.append("当前还没有拿到足够的网络与源码证据，可能需要先稳定页面动作或补 hook")
        return inferences

    @staticmethod
    def _build_unknown_findings(
        task_card: TaskCard,
        request_items: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
    ) -> list[str]:
        unknowns: list[str] = []
        if not request_items:
            unknowns.append("尚未确认目标请求是否已稳定触发")
        if not source_hits:
            unknowns.append(f"尚未确认 {task_card.target_param_or_api} 的具体源码位置或生成函数")
        return unknowns

    @staticmethod
    def _build_recon_evidence(
        browser: BrowserSessionInfo,
        request_items: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
        navigation_events: list[str],
        request_initiators: list[dict[str, Any]] | None = None,
        source_contexts: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
        runtime_context_diff: dict[str, Any] | None = None,
        function_candidates: list[dict[str, Any]] | None = None,
        function_validations: list[dict[str, Any]] | None = None,
        function_validation_summary: dict[str, Any] | None = None,
    ) -> list[EvidenceItem]:
        request_initiators = request_initiators or []
        source_contexts = source_contexts or []
        runtime_context = runtime_context or {}
        runtime_context_diff = runtime_context_diff or {}
        function_candidates = function_candidates or []
        function_validations = function_validations or []
        function_validation_summary = function_validation_summary or {}
        evidence: list[EvidenceItem] = [
            EvidenceItem(
                summary="浏览器运行时状态检查完成",
                kind=EvidenceKind.OTHER,
                source="check_browser_health",
                details=browser.model_dump(),
                confidence=ConfidenceLevel.HIGH if browser.healthy else ConfidenceLevel.LOW,
            )
        ]
        if request_items:
            evidence.append(
                EvidenceItem(
                    summary=f"采集到 {len(request_items)} 条网络请求样本",
                    kind=EvidenceKind.REQUEST,
                    source="network_request",
                    details={"count": len(request_items), "sample": request_items[:3]},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )
        if source_hits:
            evidence.append(
                EvidenceItem(
                    summary=f"搜索命中 {len(source_hits)} 条源码结果",
                    kind=EvidenceKind.STATIC,
                    source="search_in_sources",
                    details={"count": len(source_hits), "sample": source_hits[:3]},
                    confidence=ConfidenceLevel.HIGH,
                )
            )
        if request_initiators:
            evidence.append(
                EvidenceItem(
                    summary=f"采集到 {len(request_initiators)} 条请求发起链路",
                    kind=EvidenceKind.CALLSTACK,
                    source="get_request_initiator",
                    anchor=",".join(str(item.get("requestId")) for item in request_initiators),
                    details={"count": len(request_initiators), "sample": request_initiators[:2]},
                    confidence=ConfidenceLevel.HIGH,
                )
            )
        if source_contexts:
            evidence.append(
                EvidenceItem(
                    summary=f"拉取到 {len(source_contexts)} 个源码上下文片段",
                    kind=EvidenceKind.STATIC,
                    source="get_script_source",
                    anchor=",".join(f"{item.get('scriptId')}:{item.get('lineNumber')}" for item in source_contexts),
                    details={"count": len(source_contexts), "sample": source_contexts[:2]},
                    confidence=ConfidenceLevel.HIGH,
                )
            )
        if runtime_context:
            evidence.append(
                EvidenceItem(
                    summary="采集到运行时上下文证据",
                    kind=EvidenceKind.STORAGE,
                    source="runtime_context",
                    anchor=",".join(runtime_context.get("captured_requirements", [])) if isinstance(runtime_context.get("captured_requirements"), list) else None,
                    details=runtime_context,
                    confidence=ConfidenceLevel.HIGH if runtime_context.get("captured_requirements") else ConfidenceLevel.MEDIUM,
                )
            )
        if runtime_context_diff:
            evidence.append(
                EvidenceItem(
                    summary="生成运行时上下文稳定性摘要",
                    kind=EvidenceKind.NOTE,
                    source="runtime_context_diff",
                    anchor=",".join(runtime_context_diff.get("stable_keys", [])[:5]) if isinstance(runtime_context_diff.get("stable_keys"), list) else None,
                    details=runtime_context_diff,
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )
        if function_candidates:
            evidence.append(
                EvidenceItem(
                    summary=f"生成 {len(function_candidates)} 张候选函数卡片",
                    kind=EvidenceKind.STATIC,
                    source="function_candidate_card",
                    anchor=",".join(str(item.get("candidate_id")) for item in function_candidates),
                    details={"count": len(function_candidates), "candidates": function_candidates},
                    confidence=ConfidenceLevel.HIGH,
                )
            )
        if function_validations:
            confidence = ConfidenceLevel.HIGH if function_validation_summary.get("replay_ready") else ConfidenceLevel.MEDIUM
            evidence.append(
                EvidenceItem(
                    summary=f"完成 {len(function_validations)} 条候选函数 runtime/replay 验证",
                    kind=EvidenceKind.DYNAMIC,
                    source="function_validation_result",
                    anchor=",".join(str(item.get("candidate_id")) for item in function_validations),
                    details={"count": len(function_validations), "validations": function_validations},
                    confidence=confidence,
                )
            )
            evidence.append(
                EvidenceItem(
                    summary="候选函数验证摘要已生成",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    anchor=str(function_validation_summary.get("best_candidate_id") or ""),
                    details=function_validation_summary,
                    confidence=confidence,
                )
            )
        for event in navigation_events:
            evidence.append(
                EvidenceItem(
                    summary=f"执行导航事件 {event}",
                    kind=EvidenceKind.NOTE,
                    source="navigate_page/new_page",
                    details={"event": event},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )
        return evidence

    @staticmethod
    def _build_recon_artifacts(
        request_items: list[dict[str, Any]],
        source_hits: list[dict[str, Any]],
        request_initiators: list[dict[str, Any]] | None = None,
        source_contexts: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
        runtime_context_diff: dict[str, Any] | None = None,
        function_candidates: list[dict[str, Any]] | None = None,
        function_validations: list[dict[str, Any]] | None = None,
        function_validation_summary: dict[str, Any] | None = None,
    ) -> list[ArtifactRef]:
        request_initiators = request_initiators or []
        source_contexts = source_contexts or []
        runtime_context = runtime_context or {}
        runtime_context_diff = runtime_context_diff or {}
        function_candidates = function_candidates or []
        function_validations = function_validations or []
        function_validation_summary = function_validation_summary or {}
        artifacts: list[ArtifactRef] = []
        if request_items:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/network-requests.json",
                    kind=ArtifactKind.JSON,
                    description="Normalized request samples gathered during recon.",
                    metadata={"count": len(request_items)},
                )
            )
        if source_hits:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/source-hits.json",
                    kind=ArtifactKind.JSON,
                    description="Normalized source search hits gathered during recon.",
                    metadata={"count": len(source_hits)},
                )
            )
        if request_initiators:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/request-initiators.json",
                    kind=ArtifactKind.JSON,
                    description="Request initiator / callstack evidence gathered during recon.",
                    metadata={"count": len(request_initiators)},
                )
            )
        if source_contexts:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/source-contexts.json",
                    kind=ArtifactKind.JSON,
                    description="Source context snippets around selected source hits.",
                    metadata={"count": len(source_contexts)},
                )
            )
        if runtime_context:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/runtime-context.json",
                    kind=ArtifactKind.JSON,
                    description="Runtime context evidence collected from storage / browser environment.",
                    metadata={"captured_requirements": runtime_context.get("captured_requirements", [])},
                )
            )
        if runtime_context_diff:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/runtime-context-diff.json",
                    kind=ArtifactKind.JSON,
                    description="Runtime context stability summary for context-aware rebuild decisions.",
                    metadata={"status": runtime_context_diff.get("status"), "stable": runtime_context_diff.get("stable")},
                )
            )
        if function_candidates:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-candidates.json",
                    kind=ArtifactKind.JSON,
                    description="Candidate sign function cards promoted from source/request evidence.",
                    metadata={"count": len(function_candidates)},
                )
            )
        if function_validations:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-validations.json",
                    kind=ArtifactKind.JSON,
                    description="Runtime and replay validation results for promoted function candidates.",
                    metadata={"count": len(function_validations), "replay_ready": bool(function_validation_summary.get("replay_ready"))},
                )
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-validation-summary.json",
                    kind=ArtifactKind.JSON,
                    description="Summary of validated function candidates and replay readiness.",
                    metadata={"best_candidate_id": function_validation_summary.get("best_candidate_id")},
                )
            )
        return artifacts

    @staticmethod
    def _determine_next_action(
        source_hits: list[dict[str, Any]],
        request_items: list[dict[str, Any]],
        function_validation_summary: dict[str, Any] | None = None,
    ) -> str:
        function_validation_summary = function_validation_summary or {}
        if function_validation_summary.get("replay_ready"):
            return "extract_pure_logic_and_build_replay"
        if function_validation_summary:
            return str(function_validation_summary.get("next_action") or "expand_runtime_validation")
        if source_hits:
            return "move_to_source_analysis"
        if request_items:
            return "capture_request_initiator"
        return "stabilize_page_and_expand_runtime_observation"
