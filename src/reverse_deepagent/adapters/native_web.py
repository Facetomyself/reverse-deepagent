from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser import BrowserProvider, BrowserProviderUnavailableError, BrowserSession
from reverse_deepagent.browser.collectors import ConsoleCollector, DOMCollector, NetworkCollector, ScriptCollector, StorageCollector
from reverse_deepagent.browser.providers import CloakBrowserConfig, CloakBrowserProvider, PlaywrightChromiumConfig, PlaywrightChromiumProvider
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
        return RuntimeBackendCapabilities(
            backend_id=self.backend_id,
            display_name=self.display_name,
            transport=self.transport,
            target_platforms=["web"],
            supports_browser_session=True,
            supports_web_recon=True,
            supports_protection_patch=False,
            supports_artifact_export=True,
            supports_runtime_context=True,
            supports_replay_validation=False,
            managed_chrome=False,
            mcp_backed=False,
            evidence_kinds=["request", "static", "dynamic", "storage", "screenshot", "note"],
            artifact_kinds=["json", "markdown", "screenshot"],
            notes=[
                "native BrowserProvider-backed Web runtime",
                "baseline collectors do not require jsreverser-mcp",
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
        console.attach(page)
        network.attach(page)
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

        evidence = self._build_evidence(dom, storage, script_inventory, source_hits, network_snapshot, console_snapshot, navigation_events)
        artifacts = self._build_artifacts(network_snapshot, source_hits, storage, dom, console_snapshot)
        facts = [
            "Native Web runtime session is available",
            f"Browser provider: {self.browser_provider.describe().provider_id}",
            f"Collected {network_snapshot['count']} network request sample(s)",
            f"Collected {script_inventory['count']} script record(s)",
            f"Found {source_hits['count']} source hit(s) for target keyword",
        ]
        if navigation_events:
            facts.extend([f"Navigation event: {event}" for event in navigation_events])
        inferences = []
        unknowns = []
        if source_hits["count"]:
            inferences.append("Target keyword appears in collected script inventory; source analysis can continue without MCP")
        else:
            unknowns.append("No source hit found in baseline script inventory; CDP-enhanced script source capture may be needed")
        result = ReconResult(
            status=ExecutionStatus.SUCCESS if evidence else ExecutionStatus.PARTIAL,
            stage=ReverseStage.RECON,
            key_findings=KeyFindings(facts=facts, inferences=inferences, unknowns=unknowns),
            evidence=evidence,
            artifacts=artifacts,
            next_action="move_to_source_analysis" if source_hits["count"] else "enhance_native_collectors_or_adjust_keyword",
            confidence=ConfidenceLevel.MEDIUM,
        )
        self._last_recon = result
        return result

    def apply_minimal_protection(self, protection_name: str, context: dict[str, Any] | None = None) -> ProtectionResult:
        return ProtectionResult(
            protection_name=protection_name,
            applied_actions=[],
            verification=["Native Web hook manager is not implemented yet", f"context_keys={sorted((context or {}).keys())}"],
            status=ExecutionStatus.FAILED,
            artifacts=[],
            next_action="implement_native_hook_manager",
            confidence=ConfidenceLevel.LOW,
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
    def _build_evidence(
        dom: dict[str, Any],
        storage: dict[str, Any],
        script_inventory: dict[str, Any],
        source_hits: dict[str, Any],
        network_snapshot: dict[str, Any],
        console_snapshot: dict[str, Any],
        navigation_events: list[str],
    ) -> list[EvidenceItem]:
        return [
            EvidenceItem(summary="Native Web DOM snapshot collected", kind=EvidenceKind.DYNAMIC, source="dom_snapshot", details=dom, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web runtime context collected", kind=EvidenceKind.STORAGE, source="runtime_context", details=storage, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web network events collected", kind=EvidenceKind.REQUEST, source="network_request", details=network_snapshot, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web script inventory searched", kind=EvidenceKind.STATIC, source="search_in_sources", details=source_hits, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web script inventory collected", kind=EvidenceKind.STATIC, source="script_inventory", details=script_inventory, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web console events collected", kind=EvidenceKind.DYNAMIC, source="console_message", details=console_snapshot, confidence=ConfidenceLevel.MEDIUM),
            EvidenceItem(summary="Native Web navigation events", kind=EvidenceKind.NOTE, source="navigate_page", details={"events": navigation_events}, confidence=ConfidenceLevel.MEDIUM),
        ]

    @staticmethod
    def _build_artifacts(
        network_snapshot: dict[str, Any],
        source_hits: dict[str, Any],
        storage: dict[str, Any],
        dom: dict[str, Any],
        console_snapshot: dict[str, Any],
    ) -> list[ArtifactRef]:
        return [
            ArtifactRef(path="virtual://workspace/network-requests.json", kind=ArtifactKind.JSON, description="Native Web network request samples.", metadata={"count": network_snapshot.get("count", 0)}),
            ArtifactRef(path="virtual://workspace/source-hits.json", kind=ArtifactKind.JSON, description="Native Web source keyword hits.", metadata={"count": source_hits.get("count", 0)}),
            ArtifactRef(path="virtual://workspace/runtime-context.json", kind=ArtifactKind.JSON, description="Native Web runtime context snapshot.", metadata={"ok": storage.get("ok")}),
            ArtifactRef(path="virtual://workspace/dom-snapshot.json", kind=ArtifactKind.JSON, description="Native Web DOM snapshot.", metadata={"html_size": dom.get("html_size")}),
            ArtifactRef(path="virtual://workspace/console-messages.json", kind=ArtifactKind.JSON, description="Native Web console messages.", metadata={"count": console_snapshot.get("count", 0)}),
        ]


def create_native_web_runtime(*, browser_provider: BrowserProvider | None = None, browser: str | None = None, **kwargs: Any) -> NativeWebRuntime:
    """Create a NativeWebRuntime. Currently supports the Playwright Chromium provider skeleton."""

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
    raise BrowserProviderUnavailableError(f"Unsupported native browser provider: {browser_id}")
