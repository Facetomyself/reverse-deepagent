from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser import BrowserProvider, BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.collectors import CDPEnhancedCollector, CDPEventCacheCollector, ConsoleCollector, DOMCollector, NetworkCollector, ScriptCollector, StorageCollector
from reverse_deepagent.browser.hooks import BreakpointManager, BreakpointSpec, BrowserHookManager
from reverse_deepagent.browser.providers import (
    CloakBrowserConfig,
    CloakBrowserProvider,
    PlaywrightChromiumConfig,
    PlaywrightChromiumProvider,
    RemoteCDPConfig,
    RemoteCDPProvider,
)
from reverse_deepagent.runtime.base import BrowserSessionInfo, RuntimeBackendCapabilities, RuntimeExportBundle, WebReverseRuntime
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


@dataclass(slots=True)
class NativeWebRuntime(WebReverseRuntime):
    """Native Web runtime backed by a BrowserProvider and project-owned collectors."""

    browser_provider: BrowserProvider
    backend_id: str = "native-web"
    display_name: str = "Native Web Runtime"
    transport: str = "browser-provider"
    _session: BrowserSession | None = field(default=None, init=False, repr=False)
    _last_recon: ReconResult | None = field(default=None, init=False, repr=False)

    def describe_capabilities(self) -> RuntimeBackendCapabilities:
        provider_capabilities = self.browser_provider.describe()
        supports_runtime_eval = bool(getattr(provider_capabilities, "supports_runtime_eval", False))
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
            supports_replay_validation=supports_runtime_eval,
            managed_chrome=False,
            mcp_backed=False,
            evidence_kinds=["request", "static", "dynamic", "storage", "screenshot", "note"],
            artifact_kinds=["json", "markdown", "screenshot"],
            notes=[
                "native BrowserProvider-backed Web runtime",
                "baseline collectors do not require jsreverser-mcp",
                "function replay validation is enabled when the selected provider supports runtime eval",
            ],
            config={"provider": provider_capabilities.model_dump(mode="json")},
        )

    def ensure_browser_session(self) -> BrowserSessionInfo:
        try:
            session = self._ensure_session()
        except Exception as exc:
            return BrowserSessionInfo(
                healthy=False,
                page_count=0,
                selected_page_idx=None,
                active_url=None,
                details={"error": str(exc), "provider": self.browser_provider.describe().model_dump(mode="json")},
            )
        pages = session.list_pages()
        active = pages[0] if pages else None
        return BrowserSessionInfo(
            healthy=True,
            page_count=len(pages),
            selected_page_idx=0 if pages else None,
            active_url=active.url if active else None,
            details={"provider": self.browser_provider.describe().model_dump(mode="json"), "pages": [page.model_dump(mode="json") for page in pages]},
        )

    def run_web_recon(self, task_card: TaskCard, route_result: RouterResult) -> ReconResult:
        try:
            session = self._ensure_session()
        except Exception as exc:
            result = ReconResult(
                status=ExecutionStatus.FAILED,
                stage=ReverseStage.RECON,
                key_findings=KeyFindings(
                    facts=[],
                    inferences=["Native Web browser provider is unavailable"],
                    unknowns=["Target page, network requests, and script sources were not collected"],
                ),
                evidence=[
                    EvidenceItem(
                        summary="Native Web provider unavailable",
                        kind=EvidenceKind.NOTE,
                        source="native_web_provider",
                        details={"error": str(exc), "provider": self.browser_provider.describe().model_dump(mode="json")},
                        confidence=ConfidenceLevel.HIGH,
                    )
                ],
                artifacts=[],
                next_action="ensure_browser_provider",
                confidence=ConfidenceLevel.LOW,
            )
            self._last_recon = result
            return result

        page = session.get_active_page() or session.new_page()
        console = ConsoleCollector()
        network = NetworkCollector()
        cdp_events = CDPEventCacheCollector()
        hooks = BrowserHookManager()
        console.attach(page)
        network.attach(page)
        cdp_events.attach(page)
        hook_install = hooks.install(page)
        navigation_events: list[str] = []
        if self._looks_like_url(task_card.target_url_or_file) and page.url != task_card.target_url_or_file:
            page.goto(task_card.target_url_or_file)
            navigation_events.append(f"navigated:{task_card.target_url_or_file}")

        dom = DOMCollector().collect(page)
        storage = StorageCollector().collect(page)
        script_inventory = ScriptCollector().collect(page)
        source_hits = ScriptCollector().search(script_inventory, task_card.target_param_or_api)
        network_snapshot = network.snapshot()
        console_snapshot = console.snapshot()
        hook_snapshot = hooks.snapshot(page)
        hook_timeline = {"install": hook_install.to_dict(), "snapshot": hook_snapshot.to_dict()}
        cdp_event_snapshot = cdp_events.snapshot()
        cdp_snapshot = CDPEnhancedCollector().collect(page, network_snapshot, cdp_event_snapshot, hook_timeline)
        function_candidates = self._build_function_candidates(task_card, network_snapshot, source_hits, script_inventory)
        function_validations = self._validate_function_candidates(task_card, function_candidates, page)
        function_validation_summary = self._summarize_function_validations(function_validations)

        evidence = self._build_evidence(
            dom,
            storage,
            script_inventory,
            source_hits,
            network_snapshot,
            console_snapshot,
            navigation_events,
            cdp_snapshot,
            hook_timeline,
            function_candidates,
            function_validations,
            function_validation_summary,
        )
        artifacts = self._build_artifacts(
            network_snapshot,
            source_hits,
            storage,
            dom,
            console_snapshot,
            cdp_snapshot,
            hook_timeline,
            function_candidates,
            function_validations,
            function_validation_summary,
        )
        facts = [
            "Native Web runtime session is available",
            f"Browser provider: {self.browser_provider.describe().provider_id}",
            f"Collected {network_snapshot['count']} network request sample(s)",
            f"Collected {script_inventory['count']} script record(s)",
            f"Found {source_hits['count']} source hit(s) for target keyword",
        ]
        if navigation_events:
            facts.extend([f"Navigation event: {event}" for event in navigation_events])
        if function_candidates:
            facts.append(f"Built {len(function_candidates)} candidate function card(s)")
        if function_validation_summary:
            replay_ready = function_validation_summary.get("replay_ready")
            facts.append(
                f"Validated {function_validation_summary.get('total', 0)} candidate function(s); replay_ready={bool(replay_ready)}"
            )
        inferences = []
        unknowns = []
        if source_hits["count"]:
            inferences.append("Target keyword appears in collected script inventory; source analysis can continue without MCP")
        else:
            unknowns.append("No source hit found in baseline script inventory; CDP-enhanced script source capture may be needed")
        if function_validation_summary.get("replay_ready"):
            inferences.append("At least one candidate function was runtime-validated and replayed successfully")
        result = ReconResult(
            status=ExecutionStatus.SUCCESS if evidence else ExecutionStatus.PARTIAL,
            stage=ReverseStage.RECON,
            key_findings=KeyFindings(facts=facts, inferences=inferences, unknowns=unknowns),
            evidence=evidence,
            artifacts=artifacts,
            next_action=self._next_action_for_recon(source_hits, function_validation_summary),
            confidence=ConfidenceLevel.MEDIUM,
        )
        self._last_recon = result
        return result

    def apply_minimal_protection(self, protection_name: str, context: dict[str, Any] | None = None) -> ProtectionResult:
        context = context or {}
        try:
            session = self._ensure_session()
            page = session.get_active_page() or session.new_page()
        except Exception as exc:
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[],
                verification=[f"Native Web browser provider unavailable: {exc}", f"context_keys={sorted(context.keys())}"],
                status=ExecutionStatus.FAILED,
                artifacts=[],
                next_action="ensure_browser_provider",
                confidence=ConfidenceLevel.LOW,
            )
        if self._is_breakpoint_request(protection_name, context):
            spec = BreakpointSpec.from_context(context)
            result = BreakpointManager().set_breakpoint(page, spec)
            status = ExecutionStatus.SUCCESS
            if result.status == "partial":
                status = ExecutionStatus.PARTIAL
            elif result.status in {"failed", "unsupported"}:
                status = ExecutionStatus.FAILED
            pattern = spec.url_pattern if spec else "<missing>"
            paused_status = result.paused.get("status") if isinstance(result.paused, dict) else None
            callframe_count = len(result.callframes)
            callframe_evaluation_count = len(result.callframe_evaluations)
            verification = [
                f"breakpoint_status={result.status}",
                f"breakpoint_supported={result.supported}",
                f"paused_status={paused_status or 'unknown'}",
                f"callframe_count={callframe_count}",
                f"callframe_evaluation_count={callframe_evaluation_count}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"breakpoint_reason={result.reason}")
            if result.error:
                verification.append(f"breakpoint_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/breakpoints.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime breakpoint manager result.",
                    metadata={
                        "status": result.status,
                        "supported": result.supported,
                        "count": len(result.breakpoints),
                        "protection_name": protection_name,
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/debugger-paused.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime paused debugger snapshot.",
                    metadata={
                        "status": paused_status or "unknown",
                        "count": result.paused.get("count", 0) if isinstance(result.paused, dict) else 0,
                        "callframe_count": callframe_count,
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/callframes.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime debugger callframe snapshot.",
                    metadata={
                        "count": callframe_count,
                        "paused_status": paused_status or "unknown",
                    },
                ),
            ]
            if (spec and spec.callframe_evaluations) or result.callframe_evaluations:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/callframe-evaluations.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime debugger callframe evaluation snapshot.",
                        metadata={
                            "count": callframe_evaluation_count,
                            "paused_status": paused_status or "unknown",
                        },
                    )
                )
            if paused_status == "success":
                next_action = "inspect_callframes_or_resume"
            elif result.status in {"success", "partial"}:
                next_action = "wait_for_breakpoint"
            else:
                next_action = "ensure_cdp_breakpoint_capability"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=(
                    [f"set_breakpoint_by_url:{pattern}"] + (["capture_debugger_paused"] if paused_status == "success" else [])
                )
                if result.supported
                else [],
                verification=verification,
                status=status,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status in {"success", "partial"} else ConfidenceLevel.LOW,
            )
        hooks = BrowserHookManager()
        install = hooks.install(page)
        snapshot = hooks.snapshot(page)
        applied_actions = [f"install_hook:{name}" for name, enabled in install.installed.items() if enabled]
        if not applied_actions and install.ok:
            applied_actions = ["install_hook:runtime_baseline"]
        verification = [
            f"hook_install_ok={install.ok}",
            f"hook_event_count={snapshot.event_count}",
            f"context_keys={sorted(context.keys())}",
        ]
        if install.error:
            verification.append(f"hook_install_error={install.error}")
        status = ExecutionStatus.SUCCESS if install.ok else ExecutionStatus.FAILED
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=applied_actions,
            verification=verification,
            status=status,
            artifacts=[
                ArtifactRef(
                    path="virtual://workspace/hook-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime hook install and event timeline.",
                    metadata={"event_count": snapshot.event_count, "installed": install.installed, "protection_name": protection_name},
                )
            ],
            next_action="resume_recon" if install.ok else "ensure_browser_provider_or_hook_capability",
            confidence=ConfidenceLevel.MEDIUM if install.ok else ConfidenceLevel.LOW,
        )

    def export_reverse_artifacts(self, final_result: FinalResult | None = None) -> RuntimeExportBundle:
        exports: list[dict[str, Any]] = [
            {
                "tool": "native_web_runtime_export",
                "backend_id": self.backend_id,
                "provider": self.browser_provider.describe().model_dump(mode="json"),
                "last_recon_status": self._last_recon.status.value if self._last_recon else None,
            }
        ]
        return RuntimeExportBundle(final_result=final_result, exports=exports, artifacts=[])

    def close(self) -> None:
        try:
            self.browser_provider.stop()
        finally:
            self._session = None

    def _ensure_session(self) -> BrowserSession:
        if self._session is not None:
            return self._session
        if not self.browser_provider.is_available():
            raise BrowserProviderUnavailableError(f"Browser provider is unavailable: {self.browser_provider.describe().provider_id}")
        self._session = self.browser_provider.start()
        return self._session

    @staticmethod
    def _looks_like_url(value: str) -> bool:
        return value.startswith("http://") or value.startswith("https://")

    @staticmethod
    def _is_breakpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"breakpoint", "set-breakpoint", "debugger-breakpoint"}:
            return True
        return any(key in context for key in ("url_pattern", "script_url", "line_number", "lineNumber"))

    @staticmethod
    def _build_evidence(
        dom: dict[str, Any],
        storage: dict[str, Any],
        script_inventory: dict[str, Any],
        source_hits: dict[str, Any],
        network_snapshot: dict[str, Any],
        console_snapshot: dict[str, Any],
        navigation_events: list[str],
        cdp_snapshot: dict[str, Any],
        hook_timeline: dict[str, Any],
        function_candidates: list[dict[str, Any]],
        function_validations: list[dict[str, Any]],
        function_validation_summary: dict[str, Any],
    ) -> list[EvidenceItem]:
        evidence = [
            EvidenceItem(summary="Native Web DOM snapshot collected", kind=EvidenceKind.DYNAMIC, source="dom_snapshot", details=dom, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web runtime context collected", kind=EvidenceKind.STORAGE, source="runtime_context", details=storage, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web network events collected", kind=EvidenceKind.REQUEST, source="network_request", details=network_snapshot, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web script inventory searched", kind=EvidenceKind.STATIC, source="search_in_sources", details=source_hits, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web script inventory collected", kind=EvidenceKind.STATIC, source="script_inventory", details=script_inventory, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web console events collected", kind=EvidenceKind.DYNAMIC, source="console_message", details=console_snapshot, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web navigation events", kind=EvidenceKind.NOTE, source="navigate_page", details={"events": navigation_events}, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web CDP request initiators collected", kind=EvidenceKind.CALLSTACK, source="get_request_initiator", details=cdp_snapshot.get("request_initiators", {}), confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web CDP response body metadata collected", kind=EvidenceKind.REQUEST, source="response_body_metadata", details=cdp_snapshot.get("response_bodies", {}), confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web CDP script source metadata collected", kind=EvidenceKind.STATIC, source="get_script_source", details=cdp_snapshot.get("script_sources", {}), confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web CDP WebSocket metadata collected", kind=EvidenceKind.WEBSOCKET, source="websocket_frame_metadata", details=cdp_snapshot.get("websocket_frames", {}), confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web runtime hook timeline collected", kind=EvidenceKind.HOOK, source="runtime_hook_timeline", details=hook_timeline, confidence=ConfidenceLevel.MEDIUM),
        ]
        if function_candidates:
            evidence.append(
                EvidenceItem(
                    summary="Native Web candidate function cards assembled",
                    kind=EvidenceKind.STATIC,
                    source="function_candidate_card",
                    details={"count": len(function_candidates), "candidates": function_candidates},
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )
        if function_validations:
            evidence.append(
                EvidenceItem(
                    summary="Native Web candidate function runtime validations completed",
                    kind=EvidenceKind.DYNAMIC,
                    source="function_validation_result",
                    details={"count": len(function_validations), "validations": function_validations},
                    confidence=ConfidenceLevel.HIGH if function_validation_summary.get("replay_ready") else ConfidenceLevel.MEDIUM,
                )
            )
        if function_validation_summary:
            evidence.append(
                EvidenceItem(
                    summary="Native Web candidate function validation summary computed",
                    kind=EvidenceKind.NOTE,
                    source="function_validation_summary",
                    details=function_validation_summary,
                    confidence=ConfidenceLevel.HIGH if function_validation_summary.get("replay_ready") else ConfidenceLevel.MEDIUM,
                )
            )
        return evidence

    @staticmethod
    def _build_artifacts(
        network_snapshot: dict[str, Any],
        source_hits: dict[str, Any],
        storage: dict[str, Any],
        dom: dict[str, Any],
        console_snapshot: dict[str, Any],
        cdp_snapshot: dict[str, Any],
        hook_timeline: dict[str, Any],
        function_candidates: list[dict[str, Any]],
        function_validations: list[dict[str, Any]],
        function_validation_summary: dict[str, Any],
    ) -> list[ArtifactRef]:
        artifacts = [
            ArtifactRef(path="virtual://workspace/network-requests.json", kind=ArtifactKind.JSON, description="Native Web network request samples.", metadata={"count": network_snapshot.get("count", 0)}),
            ArtifactRef(path="virtual://workspace/source-hits.json", kind=ArtifactKind.JSON, description="Native Web source keyword hits.", metadata={"count": source_hits.get("count", 0)}),
            ArtifactRef(path="virtual://workspace/runtime-context.json", kind=ArtifactKind.JSON, description="Native Web runtime context snapshot.", metadata={"ok": storage.get("ok")}),
            ArtifactRef(path="virtual://workspace/dom-snapshot.json", kind=ArtifactKind.JSON, description="Native Web DOM snapshot.", metadata={"html_size": dom.get("html_size")}),
            ArtifactRef(path="virtual://workspace/console-messages.json", kind=ArtifactKind.JSON, description="Native Web console messages.", metadata={"count": console_snapshot.get("count", 0)}),
            ArtifactRef(path="virtual://workspace/request-initiators.json", kind=ArtifactKind.JSON, description="Native Web CDP request initiator metadata.", metadata={"count": cdp_snapshot.get("request_initiators", {}).get("count", 0), "supported": cdp_snapshot.get("supported", False)}),
            ArtifactRef(path="virtual://workspace/response-bodies.json", kind=ArtifactKind.JSON, description="Native Web CDP response body metadata.", metadata={"count": cdp_snapshot.get("response_bodies", {}).get("count", 0), "supported": cdp_snapshot.get("supported", False)}),
            ArtifactRef(path="virtual://workspace/source-contexts.json", kind=ArtifactKind.JSON, description="Native Web CDP script source metadata.", metadata={"count": cdp_snapshot.get("script_sources", {}).get("count", 0), "supported": cdp_snapshot.get("supported", False)}),
            ArtifactRef(path="virtual://workspace/websocket-frames.json", kind=ArtifactKind.JSON, description="Native Web CDP WebSocket frame metadata.", metadata={"count": cdp_snapshot.get("websocket_frames", {}).get("count", 0), "supported": cdp_snapshot.get("supported", False)}),
            ArtifactRef(path="virtual://workspace/hook-timeline.json", kind=ArtifactKind.JSON, description="Native Web runtime hook timeline.", metadata={"count": hook_timeline.get("snapshot", {}).get("eventCount", 0), "installed": hook_timeline.get("install", {}).get("installed", {})}),
        ]
        if function_candidates:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-candidates.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web candidate function cards.",
                    metadata={"count": len(function_candidates)},
                )
            )
        if function_validations:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-validations.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web candidate function runtime validations.",
                    metadata={"count": len(function_validations), "replay_ready": bool(function_validation_summary.get("replay_ready"))},
                )
            )
        if function_validation_summary:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/function-validation-summary.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web candidate function validation summary.",
                    metadata={"replay_ready": bool(function_validation_summary.get("replay_ready"))},
                )
            )
        return artifacts

    def _build_function_candidates(
        self,
        task_card: TaskCard,
        network_snapshot: dict[str, Any],
        source_hits: dict[str, Any],
        script_inventory: dict[str, Any],
    ) -> list[dict[str, Any]]:
        inventory_by_id = {
            str(item.get("scriptId")): item
            for item in script_inventory.get("scripts", [])
            if isinstance(item, dict) and item.get("scriptId") is not None
        }
        candidates: list[dict[str, Any]] = []
        for hit in source_hits.get("results", []) or []:
            if not isinstance(hit, dict):
                continue
            script_id = str(hit.get("scriptId") or "")
            inventory_item = inventory_by_id.get(script_id, {})
            source_text = str(inventory_item.get("source") or "")
            preview = str(hit.get("preview") or self._first_non_empty_line(source_text))
            function_name = self._extract_function_name(source_text) or self._extract_function_name(preview)
            if not function_name:
                continue
            candidate_id = f"{script_id}:{function_name}"
            related_requests = self._select_target_requests(task_card, network_snapshot.get("requests", []) or [], limit=3)
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "function_name": function_name,
                    "file_url": hit.get("url"),
                    "script_id": script_id,
                    "line_number": self._coerce_int(hit.get("lineNumber") or hit.get("line") or hit.get("line_number")) or 0,
                    "target_param_or_api": task_card.target_param_or_api,
                    "preview": preview,
                    "source_context": source_text,
                    "related_requests": related_requests,
                    "confidence": ConfidenceLevel.HIGH.value if related_requests else ConfidenceLevel.MEDIUM.value,
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
        page: Any,
    ) -> list[dict[str, Any]]:
        if not function_candidates or not getattr(self.browser_provider.describe(), "supports_runtime_eval", False):
            return []

        validations: list[dict[str, Any]] = []
        for candidate in function_candidates[:3]:
            function_name = str(candidate.get("function_name") or "")
            if not function_name:
                continue
            runtime_result: dict[str, Any]
            try:
                payload = page.evaluate(self._build_candidate_validation_script(task_card, candidate))
                runtime_result = self._normalize_evaluate_result(payload)
            except Exception as exc:
                runtime_result = {
                    "marker": "__REVERSE_AGENT_VALIDATE_CANDIDATE__",
                    "function_name": function_name,
                    "located": False,
                    "invocation_ok": False,
                    "sign_shape_ok": False,
                    "replay_result": {"attempted": False, "ok": False, "reason": "runtime_eval_failed"},
                    "runtime_url": getattr(page, "url", ""),
                    "invocation_error": str(exc),
                }
            checks = {
                "source_complete": self._looks_like_complete_function_source(str(candidate.get("source_context") or ""), function_name),
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
                    "sample_input": {"keyword": self._validation_keyword(task_card), "timestamp": 1700000000000},
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
        replay_ready_items = [item for item in function_validations if bool((item.get("replay_result") or {}).get("ok"))]
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

    @staticmethod
    def _build_candidate_validation_script(task_card: TaskCard, candidate: dict[str, Any]) -> str:
        function_name = json.dumps(str(candidate.get("function_name") or ""), ensure_ascii=False)
        keyword = json.dumps(NativeWebRuntime._validation_keyword(task_card), ensure_ascii=False)
        return f"""async () => {{
  const marker = "__REVERSE_AGENT_VALIDATE_CANDIDATE__";
  const functionName = {function_name};
  const keyword = {keyword};
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

    @staticmethod
    def _normalize_evaluate_result(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            for key in ("result", "value", "data"):
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
                if isinstance(value, str):
                    parsed = NativeWebRuntime._parse_json_object(value)
                    if parsed:
                        return parsed
            text = NativeWebRuntime._payload_text(payload)
            parsed = NativeWebRuntime._parse_json_object(text)
            if parsed:
                return parsed
            return payload
        if isinstance(payload, str):
            parsed = NativeWebRuntime._parse_json_object(payload)
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
            return None

    @staticmethod
    def _payload_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str):
                return text
        return ""

    @staticmethod
    def _validation_keyword(task_card: TaskCard) -> str:
        target = (task_card.target_param_or_api or "").strip()
        lowered = target.lower()
        if not target or lowered in {"x-sign", "sign", "unknown-target"}:
            return "sign"
        if "/" in target:
            return "sign"
        return target[:32]

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

    def _select_target_requests(self, task_card: TaskCard, request_items: list[dict[str, Any]], limit: int = 2) -> list[dict[str, Any]]:
        target = task_card.target_param_or_api.lower()
        selected: list[dict[str, Any]] = []
        fallback: list[dict[str, Any]] = []
        for item in request_items:
            url = str(item.get("url", "")).lower()
            method = str(item.get("method", "")).upper()
            if target and target != "unknown-target" and target in url:
                selected.append(item)
            elif "/api/" in url or method not in {"", "GET"}:
                fallback.append(item)
        return (selected + fallback)[:limit]

    @staticmethod
    def _first_non_empty_line(text: str) -> str:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

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

    def _next_action_for_recon(self, source_hits: dict[str, Any], function_validation_summary: dict[str, Any]) -> str:
        if function_validation_summary.get("replay_ready"):
            return "extract_pure_logic_and_build_replay"
        if source_hits.get("count", 0):
            return "move_to_source_analysis"
        return "enhance_native_collectors_or_adjust_keyword"


def create_native_web_runtime(*, browser_provider: BrowserProvider | None = None, browser: str | None = None, **kwargs: Any) -> NativeWebRuntime:
    """Create a NativeWebRuntime with a selectable BrowserProvider."""

    if browser_provider is not None:
        return NativeWebRuntime(browser_provider=browser_provider)
    browser_id = browser or kwargs.get("browser_provider") or "playwright-chromium"
    browser_headless = kwargs.get("browser_headless")
    if browser_id in {"playwright-chromium", "playwright", "chromium"}:
        config = PlaywrightChromiumConfig(
            headless=True if browser_headless is None else bool(browser_headless),
            profile_dir=kwargs.get("browser_profile_dir"),
            browser_url=kwargs.get("browser_url"),
            executable_path=kwargs.get("browser_executable_path"),
            args=kwargs.get("browser_args") or [],
        )
        return NativeWebRuntime(browser_provider=PlaywrightChromiumProvider(config=config))
    if browser_id in {"cloakbrowser", "cloak", "cloak-browser"}:
        browser_humanize = kwargs.get("browser_humanize")
        config = CloakBrowserConfig(
            headless=False if browser_headless is None else bool(browser_headless),
            humanize=True if browser_humanize is None else bool(browser_humanize),
            profile_dir=kwargs.get("browser_profile_dir"),
            proxy=kwargs.get("browser_proxy"),
            geoip=bool(kwargs.get("browser_geoip", False)),
            locale=kwargs.get("browser_locale"),
            timezone=kwargs.get("browser_timezone"),
            args=kwargs.get("browser_args") or [],
        )
        return NativeWebRuntime(browser_provider=CloakBrowserProvider(config=config))
    if browser_id in {"remote-cdp", "chrome-cdp-provider", "cdp-provider"}:
        config = RemoteCDPConfig(
            browser_url=kwargs.get("browser_url") or kwargs.get("cdp_browser_url") or "http://127.0.0.1:9222",
            connect_timeout=float(kwargs.get("request_timeout") or kwargs.get("browser_connect_timeout") or 5.0),
            navigation_wait=float(kwargs.get("browser_navigation_wait") or 0.5),
        )
        return NativeWebRuntime(browser_provider=RemoteCDPProvider(config=config))
    raise BrowserProviderUnavailableError(f"Unsupported native browser provider: {browser_id}")
