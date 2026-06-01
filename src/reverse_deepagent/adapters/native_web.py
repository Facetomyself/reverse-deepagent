from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from reverse_deepagent.browser import BrowserProvider, BrowserProviderRegistryError, BrowserProviderUnavailableError, BrowserSession, build_default_browser_provider_registry
from reverse_deepagent.browser.collectors import CDPEnhancedCollector, CDPEventCacheCollector, ConsoleCollector, DOMCollector, NetworkCollector, ScriptCollector, StorageCollector
from reverse_deepagent.browser.hooks import (
    AsyncChunkLoadManager,
    AsyncChunkLoadSpec,
    CustomLoaderTraversalPlanManager,
    CustomLoaderTraversalPlanSpec,
    ModuleFederationGetInitPlanManager,
    ModuleFederationGetInitPlanSpec,
    ModuleFederationGetInitProbeManager,
    ModuleFederationGetInitProbeSpec,
    BreakpointManager,
    BreakpointSpec,
    BrowserHookManager,
    ClosureScopeDiscoveryManager,
    ClosureScopeDiscoverySpec,
    FlowTimelineManager,
    FlowTimelineSpec,
    FunctionHookManager,
    FunctionHookSpec,
    ModuleDiscoveryManager,
    ModuleDiscoverySpec,
    ModuleHookManager,
    ModuleHookSpec,
    MutationObserverTimelineManager,
    MutationObserverTimelineSpec,
    ObjectRootMutationAuditManager,
    ObjectRootMutationAuditSpec,
    PageMutationAuditManager,
    PageMutationAuditSpec,
    PausedSessionActionSpec,
    SourceLogpointManager,
    SourceLogpointSpec,
)
from reverse_deepagent.browser.source_maps import SourceMapFetchManager, SourceMapFetchSpec
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
        flow_timeline = self._build_recon_flow_timeline(
            task_card,
            network_snapshot,
            cdp_snapshot,
            hook_timeline,
            function_validations,
            navigation_events,
        )

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
            flow_timeline,
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
            flow_timeline,
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
        if self._is_flow_timeline_request(protection_name, context):
            spec = FlowTimelineSpec.from_context(context)
            result = FlowTimelineManager().build(spec)
            entry_count = len(result.entries)
            stitch_candidate_count = len(result.stitch_candidates)
            auto_stitch_dry_run_count = len(result.auto_stitch_dry_runs)
            auto_stitch_conflict_resolution_count = len(result.auto_stitch_conflict_resolutions)
            auto_stitch_policy_decision_count = len(result.auto_stitch_policy_decisions)
            auto_stitch_materialization_plan_count = len(result.auto_stitch_materialization_plans)
            auto_stitch_materialization_review_decision_count = len(result.auto_stitch_materialization_review_decisions)
            auto_stitch_materialization_result_count = len(result.auto_stitch_materialization_results)
            auto_stitch_materialization_audit_count = len(result.auto_stitch_materialization_audit_entries)
            auto_stitch_materialization_rollback_plan_count = len(result.auto_stitch_materialization_rollback_plans)
            auto_stitch_materialization_transaction_count = len(result.auto_stitch_materialization_transactions)
            auto_stitch_rollback_execution_plan_count = len(result.auto_stitch_rollback_execution_plans)
            auto_stitch_rollback_execution_review_decision_count = len(result.auto_stitch_rollback_execution_review_decisions)
            auto_stitch_rollback_execution_result_count = len(result.auto_stitch_rollback_execution_results)
            auto_stitch_rollback_review_gate_recomputation_count = len(result.auto_stitch_rollback_review_gate_recomputations)
            auto_stitch_physical_rollback_dry_run_diff_count = len(result.auto_stitch_physical_rollback_dry_run_diffs)
            auto_stitch_physical_rollback_review_decision_count = len(result.auto_stitch_physical_rollback_review_decisions)
            auto_stitch_physical_rollback_result_count = len(result.auto_stitch_physical_rollback_results)
            auto_stitch_post_physical_rollback_review_gate_rerun_count = len(result.auto_stitch_post_physical_rollback_review_gate_reruns)
            auto_stitch_standard_review_gate_replacement_review_decision_count = len(result.auto_stitch_standard_review_gate_replacement_review_decisions)
            auto_stitch_standard_review_gate_replacement_result_count = len(result.auto_stitch_standard_review_gate_replacement_results)
            auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count = len(
                result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns
            )
            auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count = len(
                result.auto_stitch_post_standard_review_gate_replacement_final_delivery_packages
            )
            auto_stitch_transaction_commit_result_count = len(result.auto_stitch_transaction_commit_results)
            stitch_proposal_count = len(result.stitch_proposals)
            stitch_review_decision_count = len(result.stitch_review_decisions)
            stitched_flow_count = len(result.stitched_flows)
            verification = [
                f"flow_timeline_status={result.status}",
                f"flow_timeline_flow_id={result.flow_id}",
                f"flow_timeline_entry_count={entry_count}",
                f"flow_timeline_previous_entry_count={result.previous_entry_count}",
                f"flow_timeline_new_entry_count={result.new_entry_count}",
                f"flow_timeline_correlation_group_count={len(result.correlation_groups)}",
                f"flow_timeline_stitch_candidate_count={stitch_candidate_count}",
                f"flow_timeline_auto_stitch_dry_run_count={auto_stitch_dry_run_count}",
                f"flow_timeline_auto_stitch_conflict_resolution_count={auto_stitch_conflict_resolution_count}",
                f"flow_timeline_auto_stitch_policy_decision_count={auto_stitch_policy_decision_count}",
                f"flow_timeline_auto_stitch_materialization_plan_count={auto_stitch_materialization_plan_count}",
                f"flow_timeline_auto_stitch_materialization_review_decision_count={auto_stitch_materialization_review_decision_count}",
                f"flow_timeline_auto_stitch_materialization_result_count={auto_stitch_materialization_result_count}",
                f"flow_timeline_auto_stitch_materialization_audit_count={auto_stitch_materialization_audit_count}",
                f"flow_timeline_auto_stitch_materialization_rollback_plan_count={auto_stitch_materialization_rollback_plan_count}",
                f"flow_timeline_auto_stitch_materialization_transaction_count={auto_stitch_materialization_transaction_count}",
                f"flow_timeline_auto_stitch_rollback_execution_plan_count={auto_stitch_rollback_execution_plan_count}",
                f"flow_timeline_auto_stitch_rollback_execution_review_decision_count={auto_stitch_rollback_execution_review_decision_count}",
                f"flow_timeline_auto_stitch_rollback_execution_result_count={auto_stitch_rollback_execution_result_count}",
                f"flow_timeline_auto_stitch_rollback_review_gate_recomputation_count={auto_stitch_rollback_review_gate_recomputation_count}",
                f"flow_timeline_auto_stitch_physical_rollback_dry_run_diff_count={auto_stitch_physical_rollback_dry_run_diff_count}",
                f"flow_timeline_auto_stitch_physical_rollback_review_decision_count={auto_stitch_physical_rollback_review_decision_count}",
                f"flow_timeline_auto_stitch_physical_rollback_result_count={auto_stitch_physical_rollback_result_count}",
                f"flow_timeline_auto_stitch_post_physical_rollback_review_gate_rerun_count={auto_stitch_post_physical_rollback_review_gate_rerun_count}",
                f"flow_timeline_auto_stitch_standard_review_gate_replacement_review_decision_count={auto_stitch_standard_review_gate_replacement_review_decision_count}",
                f"flow_timeline_auto_stitch_standard_review_gate_replacement_result_count={auto_stitch_standard_review_gate_replacement_result_count}",
                f"flow_timeline_auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count={auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count}",
                f"flow_timeline_auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count={auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count}",
                f"flow_timeline_auto_stitch_transaction_commit_result_count={auto_stitch_transaction_commit_result_count}",
                f"flow_timeline_stitch_proposal_count={stitch_proposal_count}",
                f"flow_timeline_stitch_review_decision_count={stitch_review_decision_count}",
                f"flow_timeline_stitched_flow_count={stitched_flow_count}",
                f"flow_timeline_automatic_stitching=False",
                f"flow_timeline_continued_from_previous={result.continued_from_previous}",
                f"flow_timeline_sources={sorted(result.source_counts.keys())}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.reason:
                verification.append(f"flow_timeline_reason={result.reason}")
            if result.error:
                verification.append(f"flow_timeline_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/flow-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web cross-request flow timeline continuation baseline.",
                    metadata={
                        "status": result.status,
                        "flow_id": result.flow_id,
                        "run_id": result.run_id,
                        "entry_count": entry_count,
                        "previous_entry_count": result.previous_entry_count,
                        "new_entry_count": result.new_entry_count,
                        "correlation_group_count": len(result.correlation_groups),
                        "stitch_candidate_count": stitch_candidate_count,
                        "auto_stitch_dry_run_count": auto_stitch_dry_run_count,
                        "auto_stitch_conflict_resolution_count": auto_stitch_conflict_resolution_count,
                        "auto_stitch_conflict_resolution_summary": dict(result.auto_stitch_conflict_resolution_summary),
                        "auto_stitch_policy_decision_count": auto_stitch_policy_decision_count,
                        "auto_stitch_policy_summary": dict(result.auto_stitch_policy_summary),
                        "auto_stitch_materialization_plan_count": auto_stitch_materialization_plan_count,
                        "auto_stitch_materialization_summary": dict(result.auto_stitch_materialization_summary),
                        "auto_stitch_materialization_review_decision_count": auto_stitch_materialization_review_decision_count,
                        "auto_stitch_materialization_result_count": auto_stitch_materialization_result_count,
                        "auto_stitch_materialization_result_summary": dict(result.auto_stitch_materialization_result_summary),
                        "auto_stitch_materialization_audit_count": auto_stitch_materialization_audit_count,
                        "auto_stitch_materialization_audit_summary": dict(result.auto_stitch_materialization_audit_summary),
                        "auto_stitch_materialization_rollback_plan_count": auto_stitch_materialization_rollback_plan_count,
                        "auto_stitch_materialization_rollback_summary": dict(result.auto_stitch_materialization_rollback_summary),
                        "auto_stitch_materialization_transaction_count": auto_stitch_materialization_transaction_count,
                        "auto_stitch_materialization_transaction_summary": dict(result.auto_stitch_materialization_transaction_summary),
                        "auto_stitch_rollback_execution_plan_count": auto_stitch_rollback_execution_plan_count,
                        "auto_stitch_rollback_execution_summary": dict(result.auto_stitch_rollback_execution_summary),
                        "auto_stitch_rollback_execution_review_decision_count": auto_stitch_rollback_execution_review_decision_count,
                        "auto_stitch_rollback_execution_result_count": auto_stitch_rollback_execution_result_count,
                        "auto_stitch_rollback_execution_result_summary": dict(result.auto_stitch_rollback_execution_result_summary),
                        "auto_stitch_rollback_review_gate_recomputation_count": auto_stitch_rollback_review_gate_recomputation_count,
                        "auto_stitch_rollback_review_gate_recomputation_summary": dict(result.auto_stitch_rollback_review_gate_recomputation_summary),
                        "auto_stitch_physical_rollback_dry_run_diff_count": auto_stitch_physical_rollback_dry_run_diff_count,
                        "auto_stitch_physical_rollback_dry_run_diff_summary": dict(result.auto_stitch_physical_rollback_dry_run_diff_summary),
                        "auto_stitch_physical_rollback_review_decision_count": auto_stitch_physical_rollback_review_decision_count,
                        "auto_stitch_physical_rollback_result_count": auto_stitch_physical_rollback_result_count,
                        "auto_stitch_physical_rollback_result_summary": dict(result.auto_stitch_physical_rollback_result_summary),
                        "auto_stitch_post_physical_rollback_review_gate_rerun_count": auto_stitch_post_physical_rollback_review_gate_rerun_count,
                        "auto_stitch_post_physical_rollback_review_gate_rerun_summary": dict(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary),
                        "auto_stitch_standard_review_gate_replacement_review_decision_count": auto_stitch_standard_review_gate_replacement_review_decision_count,
                        "auto_stitch_standard_review_gate_replacement_result_count": auto_stitch_standard_review_gate_replacement_result_count,
                        "auto_stitch_standard_review_gate_replacement_summary": dict(result.auto_stitch_standard_review_gate_replacement_summary),
                        "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count": (
                            auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count
                        ),
                        "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary": dict(
                            result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary
                        ),
                        "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count": (
                            auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count
                        ),
                        "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary": dict(
                            result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary
                        ),
                        "auto_stitch_transaction_commit_result_count": auto_stitch_transaction_commit_result_count,
                        "auto_stitch_transaction_commit_summary": dict(result.auto_stitch_transaction_commit_summary),
                        "stitch_proposal_count": stitch_proposal_count,
                        "stitch_review_decision_count": stitch_review_decision_count,
                        "stitched_flow_count": stitched_flow_count,
                        "automatic_stitching": False,
                        "continued_from_previous": result.continued_from_previous,
                        "source_counts": result.source_counts,
                    },
                )
            ]
            if auto_stitch_conflict_resolution_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/auto-stitch-conflict-resolutions.json",
                        kind=ArtifactKind.JSON,
                        description="Review-only Native Web auto-stitch conflict resolution baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_conflict_resolution_count,
                            "summary": dict(result.auto_stitch_conflict_resolution_summary),
                            "automatic_stitching": False,
                            "would_materialize": False,
                            "source": "auto_stitch_conflict_resolution_baseline",
                        },
                    )
                )
            if auto_stitch_materialization_result_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/auto-stitch-materialization-results.json",
                        kind=ArtifactKind.JSON,
                        description="Review-approved Native Web auto-stitch materialization results.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_materialization_result_count,
                            "summary": dict(result.auto_stitch_materialization_result_summary),
                            "automatic_stitching": False,
                            "source": "review_approved_auto_stitch_materialization_plan",
                        },
                    )
                )
            if auto_stitch_materialization_audit_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-materialization-audit.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web stitched-flow materialization audit log.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_materialization_audit_count,
                            "summary": dict(result.auto_stitch_materialization_audit_summary),
                            "automatic_stitching": False,
                            "source": "review_approved_auto_stitch_materialization_plan",
                        },
                    )
                )
            if auto_stitch_materialization_rollback_plan_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-rollback-plan.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web stitched-flow materialization rollback plan.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_materialization_rollback_plan_count,
                            "summary": dict(result.auto_stitch_materialization_rollback_summary),
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "source": "review_approved_auto_stitch_materialization_plan",
                        },
                    )
                )
            if auto_stitch_materialization_transaction_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-materialization-transactions.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web stitched-flow materialization transaction log.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_materialization_transaction_count,
                            "summary": dict(result.auto_stitch_materialization_transaction_summary),
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "transaction_log_only": True,
                            "source": "review_approved_auto_stitch_materialization_plan",
                        },
                    )
                )
            if auto_stitch_rollback_execution_plan_count or auto_stitch_rollback_execution_result_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-rollback-executions.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web stitched-flow rollback execution plans and review-approved logical results.",
                        metadata={
                            "flow_id": result.flow_id,
                            "plan_count": auto_stitch_rollback_execution_plan_count,
                            "result_count": auto_stitch_rollback_execution_result_count,
                            "summary": dict(result.auto_stitch_rollback_execution_summary),
                            "result_summary": dict(result.auto_stitch_rollback_execution_result_summary),
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": False,
                            "source": "review_approved_rollback_execution_baseline",
                        },
                    )
                )
            if auto_stitch_rollback_review_gate_recomputation_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/review-gate-after-rollback.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web post-rollback review gate recomputation baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_rollback_review_gate_recomputation_count,
                            "summary": dict(result.auto_stitch_rollback_review_gate_recomputation_summary),
                            "does_not_replace_review_gate": True,
                            "delivery_allowed": False,
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": False,
                            "source": "post_rollback_review_gate_recompute_baseline",
                        },
                    )
                )
            if auto_stitch_physical_rollback_dry_run_diff_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-physical-rollback-diff.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web stitched-flow physical rollback dry-run diff.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_physical_rollback_dry_run_diff_count,
                            "summary": dict(result.auto_stitch_physical_rollback_dry_run_diff_summary),
                            "dry_run_only": True,
                            "would_mutate_if_approved": True,
                            "would_replace_review_gate": False,
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": False,
                            "source": "physical_rollback_dry_run_diff_baseline",
                        },
                    )
                )
            if auto_stitch_physical_rollback_result_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow-physical-rollback-results.json",
                        kind=ArtifactKind.JSON,
                        description="Review-approved Native Web stitched-flow physical rollback mutation results.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_physical_rollback_result_count,
                            "summary": dict(result.auto_stitch_physical_rollback_result_summary),
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": bool(result.auto_stitch_physical_rollback_result_summary.get("target_artifact_mutated")),
                            "would_replace_review_gate": False,
                            "source": "review_approved_physical_rollback_mutation_baseline",
                        },
                    )
                )
            if auto_stitch_post_physical_rollback_review_gate_rerun_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/review-gate-after-physical-rollback.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web post-physical-rollback standard review gate rerun baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_post_physical_rollback_review_gate_rerun_count,
                            "summary": dict(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary),
                            "does_not_replace_review_gate": bool(
                                result.auto_stitch_post_physical_rollback_review_gate_rerun_summary.get("does_not_replace_review_gate")
                            ),
                            "delivery_allowed": False,
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": bool(result.auto_stitch_post_physical_rollback_review_gate_rerun_summary.get("target_artifact_mutated")),
                            "source": "post_physical_rollback_review_gate_rerun_baseline",
                        },
                    )
                )
            if auto_stitch_standard_review_gate_replacement_result_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/review-gate-replacement-results.json",
                        kind=ArtifactKind.JSON,
                        description="Review-approved Native Web standard review gate replacement results.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_standard_review_gate_replacement_result_count,
                            "summary": dict(result.auto_stitch_standard_review_gate_replacement_summary),
                            "standard_review_gate_replaced": bool(result.auto_stitch_standard_review_gate_replacement_summary.get("standard_review_gate_replaced")),
                            "delivery_allowed": False,
                            "automatic_delivery": False,
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "target_artifact_mutated": bool(result.auto_stitch_standard_review_gate_replacement_summary.get("target_artifact_mutated")),
                            "source": "review_approved_standard_review_gate_replacement_baseline",
                        },
                    )
                )
            if auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/delivery-guard-after-review-gate-replacement.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web post-standard-review-gate-replacement delivery guard rerun baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count,
                            "summary": dict(result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary),
                            "delivery_guard_rerun_performed": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary.get(
                                    "delivery_guard_rerun_performed"
                                )
                            ),
                            "delivery_guard_passed": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary.get("delivery_guard_passed")
                            ),
                            "delivery_allowed": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary.get("delivery_allowed")
                            ),
                            "automatic_delivery": False,
                            "manual_delivery_required": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary.get(
                                    "manual_delivery_required"
                                )
                            ),
                            "automatic_stitching": False,
                            "automatic_rollback": False,
                            "source": "post_standard_review_gate_replacement_delivery_guard_rerun_baseline",
                        },
                    )
                )
            if auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/final-delivery-package-after-review-gate-replacement.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web final delivery package baseline after standard review gate replacement.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count,
                            "summary": dict(result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary),
                            "package_ready": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary.get("package_ready")
                            ),
                            "final_delivery_packaged": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary.get(
                                    "final_delivery_packaged"
                                )
                            ),
                            "delivery_allowed": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary.get("delivery_allowed")
                            ),
                            "automatic_delivery": False,
                            "manual_delivery_required": bool(
                                result.auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary.get(
                                    "manual_delivery_required"
                                )
                            ),
                            "cross_run_transaction_committed": False,
                            "manifest_revision_committed": False,
                            "external_delivery_performed": False,
                            "source": "post_standard_review_gate_replacement_final_delivery_package_baseline",
                        },
                    )
                )
            if auto_stitch_transaction_commit_result_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/final-delivery-transaction-commit.json",
                        kind=ArtifactKind.JSON,
                        description="Review-approved Native Web final delivery transaction commit baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": auto_stitch_transaction_commit_result_count,
                            "summary": dict(result.auto_stitch_transaction_commit_summary),
                            "transaction_commit_recorded": bool(result.auto_stitch_transaction_commit_summary.get("transaction_commit_recorded")),
                            "artifact_model_transaction_commit_recorded": bool(
                                result.auto_stitch_transaction_commit_summary.get("artifact_model_transaction_commit_recorded")
                            ),
                            "cross_run_transaction_committed": False,
                            "manifest_revision_committed": False,
                            "automatic_delivery": False,
                            "manual_delivery_required": bool(result.auto_stitch_transaction_commit_summary.get("manual_delivery_required")),
                            "external_delivery_performed": False,
                            "filesystem_artifact_mutated": False,
                            "source": "explicit_review_only_final_delivery_transaction_commit_baseline",
                        },
                    )
                )
            if stitched_flow_count:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/stitched-flow.json",
                        kind=ArtifactKind.JSON,
                        description="Review-approved Native Web stitched flow baseline.",
                        metadata={
                            "flow_id": result.flow_id,
                            "count": stitched_flow_count,
                            "automatic_stitching": False,
                            "source": "review_approved_stitch_proposal",
                        },
                    )
                )
            applied_actions = ["build_flow_timeline"] if entry_count else []
            if auto_stitch_materialization_result_count:
                applied_actions.append("materialize_review_approved_auto_stitch_plan")
            if auto_stitch_materialization_audit_count:
                applied_actions.append("write_stitched_flow_materialization_audit")
            if auto_stitch_materialization_rollback_plan_count:
                applied_actions.append("write_stitched_flow_rollback_plan")
            if auto_stitch_materialization_transaction_count:
                applied_actions.append("write_stitched_flow_materialization_transaction_log")
            if auto_stitch_rollback_execution_plan_count:
                applied_actions.append("plan_stitched_flow_rollback_execution")
            if auto_stitch_rollback_execution_result_count:
                applied_actions.append("record_review_approved_rollback_execution")
            if auto_stitch_rollback_review_gate_recomputation_count:
                applied_actions.append("recompute_review_gate_after_rollback")
            if auto_stitch_physical_rollback_dry_run_diff_count:
                applied_actions.append("plan_physical_rollback_dry_run_diff")
            if auto_stitch_physical_rollback_result_count:
                applied_actions.append("apply_review_approved_physical_rollback")
            if auto_stitch_post_physical_rollback_review_gate_rerun_count:
                applied_actions.append("rerun_review_gate_after_physical_rollback")
            if auto_stitch_standard_review_gate_replacement_result_count:
                applied_actions.append("replace_standard_review_gate_after_physical_rollback")
            if auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count:
                applied_actions.append("rerun_delivery_guard_after_standard_review_gate_replacement")
            if auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count:
                applied_actions.append("package_final_delivery_after_standard_review_gate_replacement")
            if auto_stitch_transaction_commit_result_count:
                applied_actions.append("record_final_delivery_transaction_commit")
            if stitched_flow_count:
                applied_actions.append("materialize_review_approved_stitched_flow")
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=applied_actions,
                verification=verification,
                status=ExecutionStatus.SUCCESS if result.new_entry_count or stitched_flow_count else ExecutionStatus.PARTIAL if entry_count else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=(
                    "inspect_stitched_flow_or_use_for_replay_planning"
                    if stitched_flow_count
                    else "inspect_flow_timeline_or_continue_next_request"
                    if entry_count
                    else "provide_timeline_inputs"
                ),
                confidence=ConfidenceLevel.MEDIUM if result.new_entry_count or stitched_flow_count else ConfidenceLevel.LOW,
            )
        if self._is_mutation_observer_timeline_request(protection_name, context):
            spec = MutationObserverTimelineSpec.from_context(context)
            result = MutationObserverTimelineManager().observe(page, spec)
            record_count = len(result.records)
            mutation_types = result.summary.get("types") if isinstance(result.summary.get("types"), list) else []
            verification = [
                f"mutation_observer_timeline_status={result.status}",
                f"mutation_observer_record_count={record_count}",
                f"mutation_observer_types={mutation_types}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"mutation_observer_reason={result.reason}")
            if result.error:
                verification.append(f"mutation_observer_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/mutation-observer-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime MutationObserver timeline around an explicit trigger.",
                    metadata={
                        "status": result.status,
                        "record_count": record_count,
                        "types": mutation_types,
                    },
                )
            ]
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=["observe_page_mutations"] if result.trigger.get("attempted") else [],
                verification=verification,
                status=ExecutionStatus.SUCCESS if result.status == "success" else ExecutionStatus.PARTIAL if result.status == "partial" else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action="inspect_mutation_observer_timeline" if record_count else "trigger_dom_mutation_or_adjust_observer_scope",
                confidence=ConfidenceLevel.MEDIUM if result.status == "success" else ConfidenceLevel.LOW,
            )
        if self._is_object_root_mutation_audit_request(protection_name, context):
            spec = ObjectRootMutationAuditSpec.from_context(context)
            result = ObjectRootMutationAuditManager().audit(page, spec)
            change_count = int(result.diff.get("change_count") or 0)
            categories = result.diff.get("categories") if isinstance(result.diff.get("categories"), list) else []
            root_path = spec.root_path if spec else "<missing>"
            verification = [
                f"object_root_mutation_audit_status={result.status}",
                f"object_root_mutation_audit_root_path={root_path}",
                f"object_root_mutation_audit_changed={bool(result.diff.get('changed'))}",
                f"object_root_mutation_audit_change_count={change_count}",
                f"object_root_mutation_audit_categories={categories}",
                f"object_root_mutation_audit_getter_invocation={result.side_effect_policy.get('getter_invocation', False)}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"object_root_mutation_audit_reason={result.reason}")
            if result.error:
                verification.append(f"object_root_mutation_audit_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/object-root-mutation-audit.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime descriptor-safe object-root before/after mutation audit.",
                    metadata={
                        "status": result.status,
                        "root_path": root_path,
                        "changed": bool(result.diff.get("changed")),
                        "change_count": change_count,
                        "categories": categories,
                        "getter_invocation": result.side_effect_policy.get("getter_invocation", False),
                    },
                )
            ]
            if result.status == "blocked":
                status = ExecutionStatus.PARTIAL
                next_action = "provide_safe_dotted_object_root_path"
            else:
                status = ExecutionStatus.SUCCESS if result.status == "success" else ExecutionStatus.PARTIAL if result.status == "partial" else ExecutionStatus.FAILED
                next_action = "inspect_object_root_mutation_audit" if change_count else "provide_trigger_or_expand_object_snapshot_scope"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=["audit_object_root_mutation"] if result.trigger.get("attempted") else [],
                verification=verification,
                status=status,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status == "success" else ConfidenceLevel.LOW,
            )
        if self._is_page_mutation_audit_request(protection_name, context):
            spec = PageMutationAuditSpec.from_context(context)
            result = PageMutationAuditManager().audit(page, spec)
            change_count = int(result.diff.get("change_count") or 0)
            categories = result.diff.get("categories") if isinstance(result.diff.get("categories"), list) else []
            verification = [
                f"page_mutation_audit_status={result.status}",
                f"page_mutation_audit_changed={bool(result.diff.get('changed'))}",
                f"page_mutation_audit_change_count={change_count}",
                f"page_mutation_audit_categories={categories}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"page_mutation_audit_reason={result.reason}")
            if result.error:
                verification.append(f"page_mutation_audit_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/page-mutation-audit.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime page-level before/after mutation audit.",
                    metadata={
                        "status": result.status,
                        "changed": bool(result.diff.get("changed")),
                        "change_count": change_count,
                        "categories": categories,
                    },
                )
            ]
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=["audit_page_mutation"] if result.trigger.get("attempted") else [],
                verification=verification,
                status=ExecutionStatus.SUCCESS if result.status == "success" else ExecutionStatus.PARTIAL if result.status == "partial" else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action="inspect_page_mutation_audit" if change_count else "provide_trigger_or_expand_snapshot_scope",
                confidence=ConfidenceLevel.MEDIUM if result.status == "success" else ConfidenceLevel.LOW,
            )
        if self._is_paused_session_request(protection_name, context):
            spec = PausedSessionActionSpec.from_context(context)
            result = BreakpointManager().run_paused_session_action(page, spec)
            pause_session_id = spec.pause_session_id if spec else "<missing>"
            paused_status = result.paused.get("status") if isinstance(result.paused, dict) else None
            debugger_lifecycle = result.debugger_session.get("lifecycle") if isinstance(result.debugger_session, dict) else None
            callframe_count = len(result.callframes)
            callframe_evaluation_count = len(result.callframe_evaluations)
            mutation_audit_count = len(result.mutation_audit)
            debugger_action_count = len(result.debugger_actions)
            debugger_session_count = result.debugger_session.get("paused_event_count", 0) if isinstance(result.debugger_session, dict) else 0
            debugger_timeline_count = result.debugger_timeline.get("entry_count", 0) if isinstance(result.debugger_timeline, dict) else 0
            continued_from_store = bool(result.debugger_session.get("continued_from_store")) if isinstance(result.debugger_session, dict) else False
            continued_from_registry = bool(result.debugger_session.get("continued_from_registry")) if isinstance(result.debugger_session, dict) else False
            live_continuation_available = bool(
                result.debugger_session.get(
                    "live_continuation_available",
                    continued_from_registry and debugger_lifecycle != "resumed",
                )
            ) if isinstance(result.debugger_session, dict) else False
            preflight = result.continuation_preflight if isinstance(result.continuation_preflight, dict) else {}
            preflight_status = str(preflight.get("status") or "unknown")
            preflight_source = str(preflight.get("source") or "unknown")
            preflight_live_available = bool(preflight.get("live_continuation_available", live_continuation_available))
            preflight_reason = preflight.get("blocked_reason") or preflight.get("reason")
            paused_session_metadata = {
                "continued_from_store": continued_from_store,
                "continued_from_registry": continued_from_registry,
                "live_continuation_available": live_continuation_available,
                "preflight_status": preflight_status,
                "preflight_source": preflight_source,
                "preflight_live_continuation_available": preflight_live_available,
            }
            if preflight_reason:
                paused_session_metadata["preflight_reason"] = preflight_reason
            verification = [
                f"paused_session_status={result.status}",
                f"paused_session_paused_status={paused_status or 'unknown'}",
                f"paused_session_lifecycle={debugger_lifecycle or 'unknown'}",
                f"paused_session_callframe_count={callframe_count}",
                f"paused_session_callframe_evaluation_count={callframe_evaluation_count}",
                f"paused_session_mutation_audit_count={mutation_audit_count}",
                f"paused_session_debugger_action_count={debugger_action_count}",
                f"paused_session_debugger_session_count={debugger_session_count}",
                f"paused_session_debugger_timeline_count={debugger_timeline_count}",
                f"paused_session_continued_from_store={continued_from_store}",
                f"paused_session_continued_from_registry={continued_from_registry}",
                f"paused_session_live_continuation_available={live_continuation_available}",
                f"paused_session_preflight_status={preflight_status}",
                f"paused_session_preflight_source={preflight_source}",
                f"paused_session_preflight_live_continuation_available={preflight_live_available}",
                f"context_keys={sorted(context.keys())}",
            ]
            if preflight_reason:
                verification.append(f"paused_session_preflight_reason={preflight_reason}")
            if preflight.get("requested_action"):
                verification.append(f"paused_session_preflight_requested_action={preflight['requested_action']}")
            if result.error:
                verification.append(f"paused_session_error={result.error}")
            if result.reason:
                verification.append(f"paused_session_reason={result.reason}")
            artifact_paths = []
            if result.debugger_session:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-session.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session snapshot.",
                        metadata={
                            "status": result.debugger_session.get("status", "unknown"),
                            "lifecycle": result.debugger_session.get("lifecycle", "unknown"),
                            "paused_event_count": result.debugger_session.get("paused_event_count", 0),
                            **paused_session_metadata,
                        },
                    )
                )
            if result.debugger_timeline:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-timeline.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session timeline.",
                        metadata={
                            "status": result.debugger_timeline.get("status", "unknown"),
                            "lifecycle": result.debugger_timeline.get("lifecycle", "unknown"),
                            "entry_count": result.debugger_timeline.get("entry_count", 0),
                            "paused_event_count": result.debugger_timeline.get("paused_event_count", 0),
                            **paused_session_metadata,
                        },
                    )
                )
            if result.callframes:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/callframes.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session callframes.",
                        metadata={"count": callframe_count, **paused_session_metadata},
                    )
                )
            if result.callframe_evaluations:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/callframe-evaluations.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session callframe evaluations.",
                        metadata={"count": callframe_evaluation_count, **paused_session_metadata},
                    )
                )
            if result.mutation_audit:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/mutation-audit.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session mutation audit.",
                        metadata={"count": mutation_audit_count, **paused_session_metadata},
                    )
                )
            if result.debugger_actions:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-actions.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime retained paused-session debugger actions.",
                        metadata={"count": debugger_action_count, **paused_session_metadata},
                    )
                )
            next_action = "inspect_debugger_session" if debugger_lifecycle != "resumed" else "continue_recon"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=[f"run_paused_session_action:{pause_session_id}"] if result.status == "success" else [],
                verification=verification,
                status=ExecutionStatus.SUCCESS if result.status == "success" else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status == "success" else ConfidenceLevel.LOW,
            )
        if self._is_closure_scope_discovery_request(protection_name, context):
            spec = ClosureScopeDiscoverySpec.from_context(context)
            result = ClosureScopeDiscoveryManager().discover(page, spec)
            function_count = len(result.functions)
            candidate_count = len(result.candidates)
            callframe_count = int(result.scope_summary.get("callframe_count") or 0)
            selected_callframe_id = result.scope_summary.get("selected_callframe_id")
            verification = [
                f"closure_scope_discovery_status={result.status}",
                f"closure_scope_function_count={function_count}",
                f"closure_scope_candidate_count={candidate_count}",
                f"closure_scope_callframe_count={callframe_count}",
                f"closure_scope_selected_callframe_id={selected_callframe_id or 'unknown'}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"closure_scope_reason={result.reason}")
            if result.error:
                verification.append(f"closure_scope_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/closure-functions.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime closure-scope function discovery evidence.",
                    metadata={
                        "status": result.status,
                        "function_count": function_count,
                        "callframe_count": callframe_count,
                        "selected_callframe_id": selected_callframe_id,
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/closure-function-candidates.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime closure-scope function candidates.",
                    metadata={
                        "status": result.status,
                        "candidate_count": candidate_count,
                        "hook_supported": False,
                    },
                ),
            ]
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=["discover_closure_scope_functions"] if result.supported else [],
                verification=verification,
                status=ExecutionStatus.SUCCESS if candidate_count else ExecutionStatus.PARTIAL if result.supported else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action="inspect_closure_function_candidates" if candidate_count else "provide_candidate_names_or_adjust_breakpoint",
                confidence=ConfidenceLevel.MEDIUM if candidate_count else ConfidenceLevel.LOW,
            )
        if self._is_source_map_fetch_request(protection_name, context):
            spec = SourceMapFetchSpec.from_context(context)
            result = SourceMapFetchManager().plan_or_fetch(spec)
            plan = result.plan if isinstance(result.plan, dict) else {}
            fetch_result = result.result if isinstance(result.result, dict) else {}
            verification = [
                f"source_map_fetch_status={result.status}",
                f"source_map_fetch_plan_status={plan.get('status', 'missing')}",
                f"source_map_fetch_detected={plan.get('source_mapping_url_detected', False)}",
                f"source_map_fetch_allowed={plan.get('fetch_allowed', False)}",
                f"source_map_fetch_attempted={fetch_result.get('attempted', False)}",
                f"context_keys={sorted(context.keys())}",
            ]
            if plan.get("blocking_reason"):
                verification.append(f"source_map_fetch_blocking_reason={plan['blocking_reason']}")
            if fetch_result.get("byte_count") is not None:
                verification.append(f"source_map_fetch_byte_count={fetch_result['byte_count']}")
            if fetch_result.get("indexed_section_url_count") is not None:
                verification.append(f"source_map_indexed_section_url_count={fetch_result['indexed_section_url_count']}")
            if result.reason:
                verification.append(f"source_map_fetch_reason={result.reason}")
            if result.error:
                verification.append(f"source_map_fetch_error={result.error}")
            artifacts = [
                ArtifactRef(
                    path="virtual://workspace/source-map-fetch-plan.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime external Source Map fetch plan.",
                    metadata={
                        "status": result.status,
                        "plan_status": plan.get("status"),
                        "source_map_url_redacted": plan.get("source_map_url_redacted"),
                        "fetch_allowed": plan.get("fetch_allowed", False),
                        "review_required": plan.get("review_required", True),
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/source-map-fetch-result.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime external Source Map fetch result metadata.",
                    metadata={
                        "status": result.status,
                        "fetch_attempted": fetch_result.get("attempted", False),
                        "fetch_ok": fetch_result.get("ok", False),
                        "byte_count": fetch_result.get("byte_count", 0),
                        "sources_count": fetch_result.get("sources_count", 0),
                        "indexed_section_url_count": fetch_result.get("indexed_section_url_count", 0),
                    },
                ),
            ]
            if result.status == "success":
                status = ExecutionStatus.SUCCESS
                next_action = "review_fetched_source_map_metadata_before_remap"
                actions = ["fetch_source_map"]
            elif result.status == "planned":
                status = ExecutionStatus.SUCCESS
                next_action = "review_source_map_fetch_plan_before_execution"
                actions = ["plan_source_map_fetch"]
            elif result.status == "blocked":
                status = ExecutionStatus.PARTIAL
                next_action = "approve_source_map_fetch_or_adjust_url_policy"
                actions = ["plan_source_map_fetch"]
            else:
                status = ExecutionStatus.FAILED
                next_action = "inspect_source_map_fetch_failure"
                actions = []
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=actions,
                verification=verification,
                status=status,
                artifacts=artifacts,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status in {"planned", "success"} else ConfidenceLevel.LOW,
            )
        if self._is_source_logpoint_request(protection_name, context):
            spec = SourceLogpointSpec.from_context(context)
            result = SourceLogpointManager().install(page, spec)
            breakpoint_count = len(result.breakpoints)
            event_count = len(result.events)
            verification = [
                f"source_logpoint_status={result.status}",
                f"source_logpoint_breakpoint_count={breakpoint_count}",
                f"source_logpoint_event_count={event_count}",
                f"context_keys={sorted(context.keys())}",
            ]
            if spec and spec.remap:
                verification.append(f"source_logpoint_remap_status={spec.remap.get('status')}")
                if spec.remap.get("strategy"):
                    verification.append(f"source_logpoint_remap_strategy={spec.remap['strategy']}")
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"source_logpoint_reason={result.reason}")
            if result.error:
                verification.append(f"source_logpoint_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/source-logpoints.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime source logpoint install result.",
                    metadata={
                        "status": result.status,
                        "breakpoint_count": breakpoint_count,
                        "url_pattern": spec.url_pattern if spec else "<missing>",
                        "line_number": spec.line_number if spec else 0,
                        "column_number": spec.column_number if spec else None,
                        "remap": spec.remap if spec else {},
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/source-logpoint-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime source logpoint timeline.",
                    metadata={
                        "status": "success" if event_count else "not_observed",
                        "event_count": event_count,
                        "url_pattern": spec.url_pattern if spec else "<missing>",
                        "line_number": spec.line_number if spec else 0,
                        "column_number": spec.column_number if spec else None,
                        "remap": spec.remap if spec else {},
                    },
                ),
            ]
            next_action = "inspect_source_logpoint_events" if event_count else "trigger_code_path_or_adjust_logpoint"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=(
                    [f"set_source_logpoint:{spec.url_pattern}:{spec.line_number}"] if spec and breakpoint_count else []
                ),
                verification=verification,
                status=ExecutionStatus.SUCCESS if breakpoint_count else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if breakpoint_count else ConfidenceLevel.LOW,
            )
        if self._is_function_hook_request(protection_name, context):
            spec = FunctionHookSpec.from_context(context)
            result = FunctionHookManager().install(page, spec)
            installed_count = len(result.installed)
            missing_count = len(result.missing)
            event_count = len(result.events)
            verification = [
                f"function_hook_status={result.status}",
                f"function_hook_installed_count={installed_count}",
                f"function_hook_missing_count={missing_count}",
                f"function_hook_event_count={event_count}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.error:
                verification.append(f"function_hook_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/function-hooks.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime target function hook install result.",
                    metadata={
                        "status": result.status,
                        "installed_count": installed_count,
                        "missing_count": missing_count,
                        "function_name": spec.function_name if spec else "<missing>",
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/function-hook-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime target function hook timeline.",
                    metadata={
                        "status": "success" if event_count else "not_observed",
                        "event_count": event_count,
                        "function_name": spec.function_name if spec else "<missing>",
                    },
                ),
            ]
            next_action = "inspect_function_hook_events" if event_count else "invoke_target_function_or_adjust_hook_path"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=(
                    [f"install_function_hook:{spec.function_name}"] if spec and result.installed else []
                ),
                verification=verification,
                status=ExecutionStatus.SUCCESS if installed_count else ExecutionStatus.PARTIAL if missing_count else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if installed_count else ConfidenceLevel.LOW,
            )
        if self._is_module_federation_get_init_request(protection_name, context):
            if self._is_module_federation_get_init_probe_request(context):
                spec = ModuleFederationGetInitProbeSpec.from_context(context)
                result = ModuleFederationGetInitProbeManager().plan_or_probe(page, spec)
                execution = result.execution if isinstance(result.execution, dict) else {}
                plan = result.plan if isinstance(result.plan, dict) else {}
                verification = [
                    f"module_federation_get_init_probe_status={result.status}",
                    f"module_federation_get_init_plan_status={plan.get('status', 'missing')}",
                    f"module_federation_get_init_execution_attempted={execution.get('attempted', False)}",
                    f"module_federation_get_init_execution_ok={execution.get('ok', False)}",
                    f"module_federation_get_init_container_init_called={execution.get('containerInitCalled', False)}",
                    f"module_federation_get_init_remote_get_called={execution.get('remoteGetCalled', False)}",
                    f"module_federation_get_init_remote_factory_invoked={execution.get('remoteFactoryInvoked', False)}",
                    f"context_keys={sorted(context.keys())}",
                ]
                if execution.get("addedSharedScopeKeys") is not None:
                    verification.append(f"module_federation_get_init_added_shared_scope_key_count={len(execution.get('addedSharedScopeKeys') or [])}")
                if execution.get("factoryType"):
                    verification.append(f"module_federation_get_init_factory_type={execution.get('factoryType')}")
                if execution.get("reason"):
                    verification.append(f"module_federation_get_init_execution_reason={execution['reason']}")
                if result.reason:
                    verification.append(f"module_federation_get_init_reason={result.reason}")
                if result.error:
                    verification.append(f"module_federation_get_init_error={result.error}")
                artifact_paths = [
                    ArtifactRef(
                        path="virtual://workspace/module-federation-get-init-plan.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime review-only Module Federation get/init plan.",
                        metadata={
                            "status": result.status,
                            "plan_status": plan.get("status"),
                            "candidate_count": plan.get("candidate_count", 0),
                            "container_count": plan.get("container_count", 0),
                            "exposed_module_count": plan.get("exposed_module_count", 0),
                            "function_path_candidate_count": plan.get("function_path_candidate_count", 0),
                            "blocked_execution_count": plan.get("blocked_execution_count", 0),
                            "review_required": plan.get("review_required", True),
                        },
                    ),
                    ArtifactRef(
                        path="virtual://workspace/module-federation-get-init-result.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime review-gated Module Federation init/get probe evidence.",
                        metadata={
                            "status": result.status,
                            "execution_attempted": execution.get("attempted", False),
                            "execution_ok": execution.get("ok", False),
                            "container_init_called": execution.get("containerInitCalled", False),
                            "remote_get_called": execution.get("remoteGetCalled", False),
                            "remote_factory_invoked": execution.get("remoteFactoryInvoked", False),
                            "added_shared_scope_key_count": len(execution.get("addedSharedScopeKeys") or []),
                            "factory_type": execution.get("factoryType"),
                        },
                    ),
                ]
                if result.status == "success":
                    next_action = "review_module_federation_get_init_probe_before_factory_invocation"
                    status = ExecutionStatus.SUCCESS
                    applied_actions = ["probe_module_federation_get_init"]
                elif result.status == "planned":
                    next_action = "review_module_federation_get_init_plan"
                    status = ExecutionStatus.SUCCESS
                    applied_actions = ["plan_module_federation_get_init"]
                elif result.status == "blocked":
                    next_action = "approve_module_federation_get_init_or_choose_function_path_candidate"
                    status = ExecutionStatus.PARTIAL
                    applied_actions = ["plan_module_federation_get_init"]
                else:
                    next_action = "inspect_module_federation_get_init_probe_failure"
                    status = ExecutionStatus.FAILED
                    applied_actions = []
                return ProtectionResult(
                    protection_name=protection_name,
                    applied_actions=applied_actions,
                    verification=verification,
                    status=status,
                    artifacts=artifact_paths,
                    next_action=next_action,
                    confidence=ConfidenceLevel.MEDIUM if result.status in {"planned", "success"} else ConfidenceLevel.LOW,
                )
            spec = ModuleFederationGetInitPlanSpec.from_context(context)
            result = ModuleFederationGetInitPlanManager().plan(spec)
            plan = result.plan if isinstance(result.plan, dict) else {}
            verification = [
                f"module_federation_get_init_plan_status={result.status}",
                f"module_federation_get_init_candidate_count={plan.get('candidate_count', 0)}",
                f"module_federation_get_init_container_count={plan.get('container_count', 0)}",
                f"module_federation_get_init_exposed_module_count={plan.get('exposed_module_count', 0)}",
                f"module_federation_get_init_function_path_candidate_count={plan.get('function_path_candidate_count', 0)}",
                f"module_federation_get_init_blocked_execution_count={plan.get('blocked_execution_count', 0)}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.reason:
                verification.append(f"module_federation_get_init_reason={result.reason}")
            if result.error:
                verification.append(f"module_federation_get_init_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/module-federation-get-init-plan.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime review-only Module Federation get/init plan.",
                    metadata={
                        "status": result.status,
                        "plan_status": plan.get("status"),
                        "candidate_count": plan.get("candidate_count", 0),
                        "container_count": plan.get("container_count", 0),
                        "exposed_module_count": plan.get("exposed_module_count", 0),
                        "function_path_candidate_count": plan.get("function_path_candidate_count", 0),
                        "blocked_execution_count": plan.get("blocked_execution_count", 0),
                        "review_required": plan.get("review_required", True),
                        "plan_only": result.side_effect_policy.get("plan_only", True),
                    },
                )
            ]
            if result.status == "planned":
                next_action = "review_module_federation_get_init_plan"
                status = ExecutionStatus.SUCCESS
                applied_actions = ["plan_module_federation_get_init"]
            elif result.status == "blocked":
                next_action = "provide_module_federation_candidates_from_module_discovery"
                status = ExecutionStatus.PARTIAL
                applied_actions = ["plan_module_federation_get_init"]
            else:
                next_action = "inspect_module_federation_get_init_request"
                status = ExecutionStatus.FAILED
                applied_actions = []
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=applied_actions,
                verification=verification,
                status=status,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status == "planned" else ConfidenceLevel.LOW,
            )
        if self._is_custom_loader_traversal_request(protection_name, context):
            spec = CustomLoaderTraversalPlanSpec.from_context(context)
            result = CustomLoaderTraversalPlanManager().plan(spec)
            plan = result.plan if isinstance(result.plan, dict) else {}
            verification = [
                f"custom_loader_traversal_plan_status={result.status}",
                f"custom_loader_traversal_candidate_count={plan.get('candidate_count', 0)}",
                f"custom_loader_traversal_ready_for_review_count={plan.get('ready_for_review_count', 0)}",
                f"custom_loader_traversal_blocked_execution_count={plan.get('blocked_execution_count', 0)}",
                f"custom_loader_traversal_custom_candidate_count={plan.get('custom_candidate_count', 0)}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.reason:
                verification.append(f"custom_loader_traversal_reason={result.reason}")
            if result.error:
                verification.append(f"custom_loader_traversal_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/custom-loader-traversal-plan.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime review-only custom loader traversal plan.",
                    metadata={
                        "status": result.status,
                        "plan_status": plan.get("status"),
                        "candidate_count": plan.get("candidate_count", 0),
                        "ready_for_review_count": plan.get("ready_for_review_count", 0),
                        "blocked_execution_count": plan.get("blocked_execution_count", 0),
                        "custom_candidate_count": plan.get("custom_candidate_count", 0),
                        "review_required": plan.get("review_required", True),
                        "plan_only": result.side_effect_policy.get("plan_only", True),
                    },
                )
            ]
            if result.status == "planned":
                next_action = "review_custom_loader_traversal_plan"
                status = ExecutionStatus.SUCCESS
                applied_actions = ["plan_custom_loader_traversal"]
            elif result.status == "blocked":
                next_action = "provide_custom_loader_candidates_from_chunk_graph"
                status = ExecutionStatus.PARTIAL
                applied_actions = ["plan_custom_loader_traversal"]
            else:
                next_action = "inspect_custom_loader_traversal_request"
                status = ExecutionStatus.FAILED
                applied_actions = []
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=applied_actions,
                verification=verification,
                status=status,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status == "planned" else ConfidenceLevel.LOW,
            )
        if self._is_async_chunk_load_request(protection_name, context):
            spec = AsyncChunkLoadSpec.from_context(context)
            result = AsyncChunkLoadManager().plan_or_execute(page, spec)
            execution = result.execution if isinstance(result.execution, dict) else {}
            plan = result.plan if isinstance(result.plan, dict) else {}
            verification = [
                f"async_chunk_load_status={result.status}",
                f"async_chunk_load_plan_status={plan.get('status', 'missing')}",
                f"async_chunk_load_chunk_id={plan.get('chunk_id', '<missing>')}",
                f"async_chunk_load_loader_kind={plan.get('loader_kind', '<missing>')}",
                f"async_chunk_load_execution_attempted={execution.get('attempted', False)}",
                f"async_chunk_load_execution_ok={execution.get('ok', False)}",
                f"context_keys={sorted(context.keys())}",
            ]
            if execution.get("addedRegistryKeys") is not None:
                verification.append(f"async_chunk_load_added_registry_key_count={len(execution.get('addedRegistryKeys') or [])}")
            if execution.get("reason"):
                verification.append(f"async_chunk_load_execution_reason={execution['reason']}")
            if result.reason:
                verification.append(f"async_chunk_load_reason={result.reason}")
            if result.error:
                verification.append(f"async_chunk_load_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/async-chunk-load-plan.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime reviewed async chunk load plan.",
                    metadata={
                        "status": result.status,
                        "plan_status": plan.get("status"),
                        "chunk_id": plan.get("chunk_id"),
                        "loader_kind": plan.get("loader_kind"),
                        "review_required": plan.get("review_required", True),
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/async-chunk-load-result.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime async chunk load execution evidence.",
                    metadata={
                        "status": result.status,
                        "execution_attempted": execution.get("attempted", False),
                        "execution_ok": execution.get("ok", False),
                        "chunk_id": plan.get("chunk_id"),
                        "added_registry_key_count": len(execution.get("addedRegistryKeys") or []),
                    },
                ),
            ]
            if result.status == "success":
                next_action = "inspect_module_registry_diff_after_chunk_load"
                status = ExecutionStatus.SUCCESS
                applied_actions = [f"execute_async_chunk_load:{plan.get('chunk_id', '<missing>')}"]
            elif result.status == "planned":
                next_action = "review_async_chunk_load_plan_before_execution"
                status = ExecutionStatus.SUCCESS
                applied_actions = ["plan_async_chunk_load"]
            elif result.status == "blocked":
                next_action = "approve_async_chunk_load_or_choose_supported_candidate"
                status = ExecutionStatus.PARTIAL
                applied_actions = ["plan_async_chunk_load"]
            else:
                next_action = "inspect_async_chunk_load_failure"
                status = ExecutionStatus.FAILED
                applied_actions = []
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=applied_actions,
                verification=verification,
                status=status,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if result.status in {"planned", "success"} else ConfidenceLevel.LOW,
            )
        if self._is_module_discovery_request(protection_name, context):
            discovery_context = {**context, "discover_modules": True}
            spec = ModuleDiscoverySpec.from_context(discovery_context)
            result = ModuleDiscoveryManager().discover(page, spec)
            module_count = len(result.modules)
            candidate_count = len(result.candidates)
            script_count = len(result.scripts)
            chunk_graph = result.chunk_graph if isinstance(result.chunk_graph, dict) else {}
            chunk_graph_status = str(chunk_graph.get("status") or "not_attempted")
            chunk_graph_candidate_count = int(chunk_graph.get("candidate_count") or 0)
            chunk_graph_script_edge_count = int(chunk_graph.get("script_edge_count") or 0)
            chunk_graph_runtime_loader_count = int(chunk_graph.get("runtime_loader_count") or 0)
            runtime_status = result.runtime.get("status") if result.runtime else "not_attempted"
            runtime_module_count = int(result.runtime.get("module_count") or 0) if result.runtime else 0
            runtime_kinds = result.runtime.get("runtime_kinds") if isinstance(result.runtime.get("runtime_kinds"), list) else []
            runtime_paths = result.runtime.get("runtime_paths") if isinstance(result.runtime.get("runtime_paths"), list) else []
            custom_key_count = int(result.runtime.get("custom_key_count") or 0) if result.runtime else 0
            federation_key_count = int(result.runtime.get("federation_key_count") or 0) if result.runtime else 0
            verification = [
                f"module_discovery_status={result.status}",
                f"module_discovery_script_count={script_count}",
                f"module_discovery_module_count={module_count}",
                f"module_discovery_candidate_count={candidate_count}",
                f"module_discovery_chunk_graph_status={chunk_graph_status}",
                f"module_discovery_chunk_graph_candidate_count={chunk_graph_candidate_count}",
                f"module_discovery_chunk_graph_script_edge_count={chunk_graph_script_edge_count}",
                f"module_discovery_chunk_graph_runtime_loader_count={chunk_graph_runtime_loader_count}",
                f"module_discovery_runtime_status={runtime_status}",
                f"module_discovery_runtime_module_count={runtime_module_count}",
                f"module_discovery_runtime_kinds={runtime_kinds}",
                f"module_discovery_custom_key_count={custom_key_count}",
                f"module_discovery_federation_key_count={federation_key_count}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.reason:
                verification.append(f"module_discovery_reason={result.reason}")
            if result.error:
                verification.append(f"module_discovery_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/module-registry.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime webpack-like module registry discovery.",
                    metadata={
                        "status": result.status,
                        "script_count": script_count,
                        "module_count": module_count,
                        "chunk_graph_status": chunk_graph_status,
                        "chunk_graph_candidate_count": chunk_graph_candidate_count,
                        "chunk_graph_script_edge_count": chunk_graph_script_edge_count,
                        "chunk_graph_runtime_loader_count": chunk_graph_runtime_loader_count,
                        "runtime_status": runtime_status,
                        "runtime_module_count": runtime_module_count,
                        "runtime_kinds": runtime_kinds,
                        "runtime_paths": runtime_paths,
                        "custom_key_count": custom_key_count,
                        "federation_key_count": federation_key_count,
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/module-candidates.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime webpack-like module export hook candidates.",
                    metadata={
                        "status": result.status,
                        "candidate_count": candidate_count,
                    },
                ),
            ]
            next_action = (
                "install_module_hook_from_candidate"
                if candidate_count
                else "review_async_chunk_graph_before_loading"
                if chunk_graph_candidate_count
                else "provide_module_id_or_expand_source_context"
            )
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=["discover_module_exports"] if module_count or candidate_count else ["discover_async_chunk_graph"] if chunk_graph_candidate_count else [],
                verification=verification,
                status=ExecutionStatus.SUCCESS if candidate_count or chunk_graph_candidate_count else ExecutionStatus.PARTIAL if script_count else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if candidate_count or chunk_graph_candidate_count else ConfidenceLevel.LOW,
            )
        if self._is_module_hook_request(protection_name, context):
            spec = ModuleHookSpec.from_context(context)
            result = ModuleHookManager().install(page, spec)
            installed_count = len(result.installed)
            missing_count = len(result.missing)
            event_count = len(result.events)
            verification = [
                f"module_hook_status={result.status}",
                f"module_hook_installed_count={installed_count}",
                f"module_hook_missing_count={missing_count}",
                f"module_hook_event_count={event_count}",
                f"context_keys={sorted(context.keys())}",
            ]
            if result.trigger:
                verification.append(f"trigger_attempted={result.trigger.get('attempted', False)}")
                if result.trigger.get("error"):
                    verification.append(f"trigger_error={result.trigger['error']}")
            if result.error:
                verification.append(f"module_hook_error={result.error}")
            artifact_paths = [
                ArtifactRef(
                    path="virtual://workspace/module-hooks.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime webpack-like module export hook install result.",
                    metadata={
                        "status": result.status,
                        "installed_count": installed_count,
                        "missing_count": missing_count,
                        "module_id": spec.module_id if spec else "<missing>",
                        "export_name": spec.export_name if spec else "<missing>",
                        "require_path": spec.require_path if spec else "<missing>",
                        "hook_path": spec.hook_path() if spec else "<missing>",
                    },
                ),
                ArtifactRef(
                    path="virtual://workspace/module-hook-timeline.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web runtime webpack-like module export hook timeline.",
                    metadata={
                        "status": "success" if event_count else "not_observed",
                        "event_count": event_count,
                        "module_id": spec.module_id if spec else "<missing>",
                        "export_name": spec.export_name if spec else "<missing>",
                        "hook_path": spec.hook_path() if spec else "<missing>",
                    },
                ),
            ]
            next_action = "inspect_module_hook_events" if event_count else "invoke_module_export_or_adjust_hook"
            return ProtectionResult(
                protection_name=protection_name,
                applied_actions=(
                    [f"install_module_hook:{spec.module_id}:{spec.export_name}"] if spec and result.installed else []
                ),
                verification=verification,
                status=ExecutionStatus.SUCCESS if installed_count else ExecutionStatus.PARTIAL if missing_count else ExecutionStatus.FAILED,
                artifacts=artifact_paths,
                next_action=next_action,
                confidence=ConfidenceLevel.MEDIUM if installed_count else ConfidenceLevel.LOW,
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
            debugger_lifecycle = result.debugger_session.get("lifecycle") if isinstance(result.debugger_session, dict) else None
            callframe_count = len(result.callframes)
            callframe_evaluation_count = len(result.callframe_evaluations)
            callframe_evaluation_policy = spec.callframe_evaluation_policy if spec else "unknown"
            mutation_audit_count = len(result.mutation_audit)
            debugger_action_count = len(result.debugger_actions)
            debugger_session_count = result.debugger_session.get("paused_event_count", 0) if isinstance(result.debugger_session, dict) else 0
            debugger_timeline_count = result.debugger_timeline.get("entry_count", 0) if isinstance(result.debugger_timeline, dict) else 0
            verification = [
                f"breakpoint_status={result.status}",
                f"breakpoint_supported={result.supported}",
                f"paused_status={paused_status or 'unknown'}",
                f"debugger_lifecycle={debugger_lifecycle or 'unknown'}",
                f"callframe_count={callframe_count}",
                f"callframe_evaluation_count={callframe_evaluation_count}",
                f"callframe_evaluation_policy={callframe_evaluation_policy}",
                f"mutation_audit_count={mutation_audit_count}",
                f"debugger_action_count={debugger_action_count}",
                f"debugger_session_count={debugger_session_count}",
                f"debugger_timeline_count={debugger_timeline_count}",
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
                            "policy": callframe_evaluation_policy,
                        },
                    )
                )
            if result.mutation_audit:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/mutation-audit.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime debugger mutation audit.",
                        metadata={
                            "count": mutation_audit_count,
                            "paused_status": paused_status or "unknown",
                            "policy": callframe_evaluation_policy,
                        },
                    )
                )
            if (spec and spec.debugger_actions) or result.debugger_actions:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-actions.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime debugger control action snapshot.",
                        metadata={
                            "count": debugger_action_count,
                            "paused_status": paused_status or "unknown",
                        },
                    )
                )
            if result.debugger_session:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-session.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime debugger paused-session snapshot.",
                        metadata={
                            "status": result.debugger_session.get("status", "unknown"),
                            "lifecycle": result.debugger_session.get("lifecycle", "unknown"),
                            "paused_event_count": result.debugger_session.get("paused_event_count", 0),
                        },
                    )
                )
            if result.debugger_timeline:
                artifact_paths.append(
                    ArtifactRef(
                        path="virtual://workspace/debugger-timeline.json",
                        kind=ArtifactKind.JSON,
                        description="Native Web runtime debugger event timeline.",
                        metadata={
                            "status": result.debugger_timeline.get("status", "unknown"),
                            "lifecycle": result.debugger_timeline.get("lifecycle", "unknown"),
                            "entry_count": result.debugger_timeline.get("entry_count", 0),
                            "paused_event_count": result.debugger_timeline.get("paused_event_count", 0),
                        },
                    )
                )
            if paused_status == "success":
                if debugger_action_count:
                    next_action = "inspect_debugger_action_result"
                elif result.debugger_session.get("lifecycle") == "retained_paused":
                    next_action = "inspect_debugger_session_or_resume"
                else:
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
    def _is_paused_session_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "paused-session",
            "pause-session",
            "debugger-session",
            "resume-paused-session",
            "inspect-paused-session",
            "evaluate-paused-session",
            "step-paused-session",
        }:
            return True
        return any(
            key in context
            for key in (
                "paused_session_action",
                "pausedSessionAction",
                "debugger_session_action",
                "debuggerSessionAction",
                "session_action",
            )
        )

    @staticmethod
    def _is_object_root_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "object-root-mutation-audit",
            "object-mutation-audit",
            "js-object-mutation-audit",
            "object-graph-diff",
        }:
            return True
        return any(
            key in context
            for key in (
                "object_root_mutation_audit",
                "objectRootMutationAudit",
                "object_mutation_audit",
                "objectMutationAudit",
                "object_root",
                "objectRoot",
                "object_root_path",
                "objectRootPath",
                "root_path",
                "rootPath",
                "js_object_root",
                "jsObjectRoot",
            )
        )

    @staticmethod
    def _is_page_mutation_audit_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "page-mutation-audit",
            "page-mutation",
            "audit-page-mutation",
            "mutation-audit-page",
            "dom-mutation-audit",
        }:
            return True
        return any(
            key in context
            for key in (
                "page_mutation_audit",
                "pageMutationAudit",
                "audit_page_mutation",
                "auditPageMutation",
                "selected_globals",
                "selectedGlobals",
                "global_names",
                "globalNames",
            )
        )

    @staticmethod
    def _is_flow_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "flow-timeline",
            "cross-request-timeline",
            "request-flow-timeline",
            "continue-flow-timeline",
            "timeline-continuation",
        }:
            return True
        return any(
            key in context
            for key in (
                "flow_timeline",
                "flowTimeline",
                "previous_flow_timeline",
                "previousFlowTimeline",
                "flow_events",
                "flowEvents",
                "timeline_inputs",
                "timelineInputs",
            )
        )

    @staticmethod
    def _is_mutation_observer_timeline_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "mutation-observer",
            "mutation-observer-timeline",
            "mutation-timeline",
            "page-mutation-timeline",
            "dom-mutation-timeline",
        }:
            return True
        return any(
            key in context
            for key in (
                "mutation_observer_timeline",
                "mutationObserverTimeline",
                "mutation_timeline",
                "mutationTimeline",
                "observer_wait_ms",
                "observerWaitMs",
                "mutation_record_limit",
                "mutationRecordLimit",
            )
        )

    @staticmethod
    def _is_closure_scope_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "closure-scope",
            "closure-scope-discovery",
            "closure-function",
            "closure-function-discovery",
            "closure-functions",
            "discover-closure-functions",
        }:
            return True
        return any(
            key in context
            for key in (
                "closure_function_names",
                "closureFunctionNames",
                "closure_query",
                "closureQuery",
                "closure_scope_discovery",
                "closureScopeDiscovery",
            )
        )

    @staticmethod
    def _is_source_map_fetch_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"source-map-fetch", "fetch-source-map", "source-map-url"}:
            return True
        return any(
            key in context
            for key in (
                "source_map_url",
                "sourceMapUrl",
                "source_mapping_url",
                "sourceMappingURL",
                "fetch_source_map",
                "fetchSourceMap",
                "fetch_indexed_section_urls",
                "fetchIndexedSectionUrls",
            )
        )

    @staticmethod
    def _is_source_logpoint_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"source-logpoint", "logpoint"}:
            return True
        return any(
            key in context
            for key in (
                "log_expression",
                "logExpression",
                "source_expression",
                "sourceExpression",
                "logpoint_id",
                "logpointId",
            )
        )

    @staticmethod
    def _is_module_discovery_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"}:
            return True
        return any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        )

    @staticmethod
    def _is_module_federation_get_init_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "module-federation-get-init",
            "module-federation-get-init-plan",
            "federation-get-init",
            "federation-get-init-plan",
            "module-federation-plan",
            "federation-analysis-plan",
        }:
            return True
        return any(
            key in context
            for key in (
                "module_federation_get_init",
                "moduleFederationGetInit",
                "federation_get_init_plan",
                "federationGetInitPlan",
                "module_federation_plan",
                "moduleFederationPlan",
                "module_federation_candidate",
                "moduleFederationCandidate",
                "module_federation_candidates",
                "moduleFederationCandidates",
                "federation_candidate",
                "federationCandidate",
                "federation_candidates",
                "federationCandidates",
                "federation_modules",
                "federationModules",
                "exposed_modules",
                "exposedModules",
            )
        )

    @staticmethod
    def _is_module_federation_get_init_probe_request(context: dict[str, Any]) -> bool:
        return any(
            bool(context.get(key))
            for key in (
                "execute_module_federation_get_init",
                "executeModuleFederationGetInit",
                "probe_module_federation_get_init",
                "probeModuleFederationGetInit",
                "execute_get_init",
                "executeGetInit",
            )
        )

    @staticmethod
    def _is_custom_loader_traversal_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {
            "custom-loader-traversal",
            "custom-loader-traversal-plan",
            "loader-traversal-plan",
            "custom-loader-plan",
            "deep-async-chunk-traversal",
        }:
            return True
        return any(
            key in context
            for key in (
                "custom_loader_traversal",
                "customLoaderTraversal",
                "loader_traversal_plan",
                "loaderTraversalPlan",
                "custom_loader_candidate",
                "customLoaderCandidate",
                "custom_loader_candidates",
                "customLoaderCandidates",
                "loader_candidates",
                "loaderCandidates",
                "chunk_graph",
                "chunkGraph",
            )
        )

    @staticmethod
    def _is_async_chunk_load_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"async-chunk-load", "load-async-chunk", "chunk-load", "webpack-chunk-load"}:
            return True
        return any(
            key in context
            for key in (
                "async_chunk_load",
                "asyncChunkLoad",
                "execute_chunk_load",
                "executeChunkLoad",
                "chunk_candidate",
                "chunkCandidate",
                "chunk_id",
                "chunkId",
            )
        )

    @staticmethod
    def _is_function_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if NativeWebRuntime._is_closure_scope_discovery_request(protection_name, context):
            return False
        if normalized in {"discover-module", "discover-modules", "module-discovery", "webpack-discovery"} or any(
            key in context
            for key in (
                "discover_modules",
                "discoverModules",
                "module_discovery",
                "moduleDiscovery",
                "module_query",
                "moduleQuery",
            )
        ):
            return False
        if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"} or any(
            key in context
            for key in (
                "module_id",
                "moduleId",
                "webpack_module_id",
                "webpackModuleId",
                "export_name",
                "exportName",
            )
        ):
            return False
        if normalized in {"hook-function", "function-hook", "target-function-hook"}:
            return True
        return any(
            key in context
            for key in (
                "function_name",
                "functionName",
                "function_path",
                "functionPath",
                "function_paths",
                "functionPaths",
                "hook_paths",
                "hookPaths",
                "candidate_id",
                "candidateId",
            )
        )

    @staticmethod
    def _is_module_hook_request(protection_name: str, context: dict[str, Any]) -> bool:
        normalized = protection_name.strip().lower()
        if normalized in {"hook-module", "module-hook", "webpack-module-hook", "module-export-hook"}:
            return True
        return any(
            key in context
            for key in (
                "module_id",
                "moduleId",
                "webpack_module_id",
                "webpackModuleId",
                "export_name",
                "exportName",
            )
        )

    @staticmethod
    def _build_recon_flow_timeline(
        task_card: TaskCard,
        network_snapshot: dict[str, Any],
        cdp_snapshot: dict[str, Any],
        hook_timeline: dict[str, Any],
        function_validations: list[dict[str, Any]],
        navigation_events: list[str],
    ) -> dict[str, Any]:
        flow_id = f"{task_card.target_url_or_file}::{task_card.target_param_or_api or task_card.goal}"
        flow_events = [
            {"type": "navigation", "payload": {"event": event}}
            for event in navigation_events
        ]
        spec = FlowTimelineSpec(
            flow_id=flow_id,
            run_id="native-web-recon",
            flow_events=flow_events,
            source_payloads={
                "network_requests": {"items": network_snapshot.get("requests", []) if isinstance(network_snapshot, dict) else []},
                "request_initiators": cdp_snapshot.get("request_initiators", {}) if isinstance(cdp_snapshot, dict) else {},
                "hook_timeline": hook_timeline,
                "replay_validation": {"validations": function_validations},
            },
        )
        return FlowTimelineManager().build(spec).to_dict()

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
        flow_timeline: dict[str, Any],
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
            EvidenceItem(summary="Native Web recon flow timeline assembled", kind=EvidenceKind.NOTE, source="flow_timeline", details=flow_timeline, confidence=ConfidenceLevel.MEDIUM),
        ]
        stitched_flows = flow_timeline.get("stitched_flows") if isinstance(flow_timeline.get("stitched_flows"), list) else []
        if stitched_flows:
            evidence.append(
                EvidenceItem(
                    summary="Native Web review-approved stitched flow materialized",
                    kind=EvidenceKind.NOTE,
                    source="stitched_flow",
                    details={
                        "count": len(stitched_flows),
                        "flow_id": flow_timeline.get("flow_id"),
                        "flows": stitched_flows,
                        "automatic_stitching": False,
                    },
                    confidence=ConfidenceLevel.MEDIUM,
                )
            )
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
        flow_timeline: dict[str, Any],
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
            ArtifactRef(
                path="virtual://workspace/flow-timeline.json",
                kind=ArtifactKind.JSON,
                description="Native Web recon flow timeline assembled from baseline collectors.",
                metadata={
                    "status": flow_timeline.get("status", "unknown"),
                    "flow_id": flow_timeline.get("flow_id"),
                    "entry_count": flow_timeline.get("entry_count", 0),
                    "new_entry_count": flow_timeline.get("new_entry_count", 0),
                    "correlation_group_count": flow_timeline.get("correlation_group_count", 0),
                    "stitch_candidate_count": flow_timeline.get("stitch_candidate_count", 0),
                    "auto_stitch_dry_run_count": flow_timeline.get("auto_stitch_dry_run_count", 0),
                    "auto_stitch_conflict_resolution_count": flow_timeline.get("auto_stitch_conflict_resolution_count", 0),
                    "auto_stitch_conflict_resolution_summary": flow_timeline.get("auto_stitch_conflict_resolution_summary", {}),
                    "auto_stitch_policy_decision_count": flow_timeline.get("auto_stitch_policy_decision_count", 0),
                    "auto_stitch_policy_summary": flow_timeline.get("auto_stitch_policy_summary", {}),
                    "auto_stitch_materialization_plan_count": flow_timeline.get("auto_stitch_materialization_plan_count", 0),
                    "auto_stitch_materialization_summary": flow_timeline.get("auto_stitch_materialization_summary", {}),
                    "auto_stitch_materialization_review_decision_count": flow_timeline.get("auto_stitch_materialization_review_decision_count", 0),
                    "auto_stitch_materialization_result_count": flow_timeline.get("auto_stitch_materialization_result_count", 0),
                    "auto_stitch_materialization_result_summary": flow_timeline.get("auto_stitch_materialization_result_summary", {}),
                    "auto_stitch_materialization_audit_count": flow_timeline.get("auto_stitch_materialization_audit_count", 0),
                    "auto_stitch_materialization_audit_summary": flow_timeline.get("auto_stitch_materialization_audit_summary", {}),
                    "auto_stitch_materialization_rollback_plan_count": flow_timeline.get("auto_stitch_materialization_rollback_plan_count", 0),
                    "auto_stitch_materialization_rollback_summary": flow_timeline.get("auto_stitch_materialization_rollback_summary", {}),
                    "auto_stitch_materialization_transaction_count": flow_timeline.get("auto_stitch_materialization_transaction_count", 0),
                    "auto_stitch_materialization_transaction_summary": flow_timeline.get("auto_stitch_materialization_transaction_summary", {}),
                    "auto_stitch_rollback_execution_plan_count": flow_timeline.get("auto_stitch_rollback_execution_plan_count", 0),
                    "auto_stitch_rollback_execution_summary": flow_timeline.get("auto_stitch_rollback_execution_summary", {}),
                    "auto_stitch_rollback_execution_review_decision_count": flow_timeline.get("auto_stitch_rollback_execution_review_decision_count", 0),
                    "auto_stitch_rollback_execution_result_count": flow_timeline.get("auto_stitch_rollback_execution_result_count", 0),
                    "auto_stitch_rollback_execution_result_summary": flow_timeline.get("auto_stitch_rollback_execution_result_summary", {}),
                    "auto_stitch_rollback_review_gate_recomputation_count": flow_timeline.get("auto_stitch_rollback_review_gate_recomputation_count", 0),
                    "auto_stitch_rollback_review_gate_recomputation_summary": flow_timeline.get("auto_stitch_rollback_review_gate_recomputation_summary", {}),
                    "auto_stitch_physical_rollback_dry_run_diff_count": flow_timeline.get("auto_stitch_physical_rollback_dry_run_diff_count", 0),
                    "auto_stitch_physical_rollback_dry_run_diff_summary": flow_timeline.get("auto_stitch_physical_rollback_dry_run_diff_summary", {}),
                    "auto_stitch_physical_rollback_review_decision_count": flow_timeline.get("auto_stitch_physical_rollback_review_decision_count", 0),
                    "auto_stitch_physical_rollback_result_count": flow_timeline.get("auto_stitch_physical_rollback_result_count", 0),
                    "auto_stitch_physical_rollback_result_summary": flow_timeline.get("auto_stitch_physical_rollback_result_summary", {}),
                    "auto_stitch_post_physical_rollback_review_gate_rerun_count": flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_rerun_count", 0),
                    "auto_stitch_post_physical_rollback_review_gate_rerun_summary": flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_rerun_summary", {}),
                    "auto_stitch_standard_review_gate_replacement_review_decision_count": flow_timeline.get("auto_stitch_standard_review_gate_replacement_review_decision_count", 0),
                    "auto_stitch_standard_review_gate_replacement_result_count": flow_timeline.get("auto_stitch_standard_review_gate_replacement_result_count", 0),
                    "auto_stitch_standard_review_gate_replacement_summary": flow_timeline.get("auto_stitch_standard_review_gate_replacement_summary", {}),
                    "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count": flow_timeline.get(
                        "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_count",
                        0,
                    ),
                    "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary": flow_timeline.get(
                        "auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary",
                        {},
                    ),
                    "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count": flow_timeline.get(
                        "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_count",
                        0,
                    ),
                    "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary": flow_timeline.get(
                        "auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary",
                        {},
                    ),
                    "auto_stitch_transaction_commit_result_count": flow_timeline.get("auto_stitch_transaction_commit_result_count", 0),
                    "auto_stitch_transaction_commit_summary": flow_timeline.get("auto_stitch_transaction_commit_summary", {}),
                    "stitch_proposal_count": flow_timeline.get("stitch_proposal_count", 0),
                    "stitch_review_decision_count": flow_timeline.get("stitch_review_decision_count", 0),
                    "stitched_flow_count": flow_timeline.get("stitched_flow_count", 0),
                    "automatic_stitching": False,
                    "continued_from_previous": bool(flow_timeline.get("continued_from_previous")),
                },
            ),
        ]
        conflict_resolutions = (
            flow_timeline.get("auto_stitch_conflict_resolutions")
            if isinstance(flow_timeline.get("auto_stitch_conflict_resolutions"), list)
            else []
        )
        if conflict_resolutions:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/auto-stitch-conflict-resolutions.json",
                    kind=ArtifactKind.JSON,
                    description="Review-only Native Web auto-stitch conflict resolution baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(conflict_resolutions),
                        "summary": flow_timeline.get("auto_stitch_conflict_resolution_summary", {}),
                        "automatic_stitching": False,
                        "would_materialize": False,
                        "source": "auto_stitch_conflict_resolution_baseline",
                    },
                )
            )
        materialization_results = (
            flow_timeline.get("auto_stitch_materialization_results")
            if isinstance(flow_timeline.get("auto_stitch_materialization_results"), list)
            else []
        )
        if materialization_results:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/auto-stitch-materialization-results.json",
                    kind=ArtifactKind.JSON,
                    description="Review-approved Native Web auto-stitch materialization results.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(materialization_results),
                        "summary": flow_timeline.get("auto_stitch_materialization_result_summary", {}),
                        "automatic_stitching": False,
                        "source": "review_approved_auto_stitch_materialization_plan",
                    },
                )
            )
        materialization_audits = (
            flow_timeline.get("auto_stitch_materialization_audit_entries")
            if isinstance(flow_timeline.get("auto_stitch_materialization_audit_entries"), list)
            else []
        )
        if materialization_audits:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-materialization-audit.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web stitched-flow materialization audit log.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(materialization_audits),
                        "summary": flow_timeline.get("auto_stitch_materialization_audit_summary", {}),
                        "automatic_stitching": False,
                        "source": "review_approved_auto_stitch_materialization_plan",
                    },
                )
            )
        rollback_plans = (
            flow_timeline.get("auto_stitch_materialization_rollback_plans")
            if isinstance(flow_timeline.get("auto_stitch_materialization_rollback_plans"), list)
            else []
        )
        if rollback_plans:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-rollback-plan.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web stitched-flow materialization rollback plan.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(rollback_plans),
                        "summary": flow_timeline.get("auto_stitch_materialization_rollback_summary", {}),
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "source": "review_approved_auto_stitch_materialization_plan",
                    },
                )
            )
        materialization_transactions = (
            flow_timeline.get("auto_stitch_materialization_transactions")
            if isinstance(flow_timeline.get("auto_stitch_materialization_transactions"), list)
            else []
        )
        if materialization_transactions:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-materialization-transactions.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web stitched-flow materialization transaction log.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(materialization_transactions),
                        "summary": flow_timeline.get("auto_stitch_materialization_transaction_summary", {}),
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "transaction_log_only": True,
                        "source": "review_approved_auto_stitch_materialization_plan",
                    },
                )
            )
        rollback_execution_plans = (
            flow_timeline.get("auto_stitch_rollback_execution_plans")
            if isinstance(flow_timeline.get("auto_stitch_rollback_execution_plans"), list)
            else []
        )
        rollback_execution_results = (
            flow_timeline.get("auto_stitch_rollback_execution_results")
            if isinstance(flow_timeline.get("auto_stitch_rollback_execution_results"), list)
            else []
        )
        if rollback_execution_plans or rollback_execution_results:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-rollback-executions.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web stitched-flow rollback execution plans and review-approved logical results.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "plan_count": len(rollback_execution_plans),
                        "result_count": len(rollback_execution_results),
                        "summary": flow_timeline.get("auto_stitch_rollback_execution_summary", {}),
                        "result_summary": flow_timeline.get("auto_stitch_rollback_execution_result_summary", {}),
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": False,
                        "source": "review_approved_rollback_execution_baseline",
                    },
                )
            )
        rollback_review_gate_recomputations = (
            flow_timeline.get("auto_stitch_rollback_review_gate_recomputations")
            if isinstance(flow_timeline.get("auto_stitch_rollback_review_gate_recomputations"), list)
            else []
        )
        if rollback_review_gate_recomputations:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/review-gate-after-rollback.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web post-rollback review gate recomputation baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(rollback_review_gate_recomputations),
                        "summary": flow_timeline.get("auto_stitch_rollback_review_gate_recomputation_summary", {}),
                        "does_not_replace_review_gate": True,
                        "delivery_allowed": False,
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": False,
                        "source": "post_rollback_review_gate_recompute_baseline",
                    },
                )
            )
        physical_rollback_dry_run_diffs = (
            flow_timeline.get("auto_stitch_physical_rollback_dry_run_diffs")
            if isinstance(flow_timeline.get("auto_stitch_physical_rollback_dry_run_diffs"), list)
            else []
        )
        if physical_rollback_dry_run_diffs:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-physical-rollback-diff.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web stitched-flow physical rollback dry-run diff.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(physical_rollback_dry_run_diffs),
                        "summary": flow_timeline.get("auto_stitch_physical_rollback_dry_run_diff_summary", {}),
                        "dry_run_only": True,
                        "would_mutate_if_approved": True,
                        "would_replace_review_gate": False,
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": False,
                        "source": "physical_rollback_dry_run_diff_baseline",
                    },
                )
            )
        physical_rollback_results = (
            flow_timeline.get("auto_stitch_physical_rollback_results")
            if isinstance(flow_timeline.get("auto_stitch_physical_rollback_results"), list)
            else []
        )
        if physical_rollback_results:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow-physical-rollback-results.json",
                    kind=ArtifactKind.JSON,
                    description="Review-approved Native Web stitched-flow physical rollback mutation results.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(physical_rollback_results),
                        "summary": flow_timeline.get("auto_stitch_physical_rollback_result_summary", {}),
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": bool(flow_timeline.get("auto_stitch_physical_rollback_result_summary", {}).get("target_artifact_mutated"))
                        if isinstance(flow_timeline.get("auto_stitch_physical_rollback_result_summary"), dict)
                        else False,
                        "would_replace_review_gate": False,
                        "source": "review_approved_physical_rollback_mutation_baseline",
                    },
                )
            )
        post_physical_rollback_review_gate_reruns = (
            flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_reruns")
            if isinstance(flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_reruns"), list)
            else []
        )
        if post_physical_rollback_review_gate_reruns:
            summary = (
                flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_rerun_summary", {})
                if isinstance(flow_timeline.get("auto_stitch_post_physical_rollback_review_gate_rerun_summary"), dict)
                else {}
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/review-gate-after-physical-rollback.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web post-physical-rollback standard review gate rerun baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(post_physical_rollback_review_gate_reruns),
                        "summary": summary,
                        "does_not_replace_review_gate": bool(summary.get("does_not_replace_review_gate")),
                        "delivery_allowed": False,
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": bool(summary.get("target_artifact_mutated")),
                        "source": "post_physical_rollback_review_gate_rerun_baseline",
                    },
                )
            )
        standard_review_gate_replacement_results = (
            flow_timeline.get("auto_stitch_standard_review_gate_replacement_results")
            if isinstance(flow_timeline.get("auto_stitch_standard_review_gate_replacement_results"), list)
            else []
        )
        if standard_review_gate_replacement_results:
            summary = (
                flow_timeline.get("auto_stitch_standard_review_gate_replacement_summary", {})
                if isinstance(flow_timeline.get("auto_stitch_standard_review_gate_replacement_summary"), dict)
                else {}
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/review-gate-replacement-results.json",
                    kind=ArtifactKind.JSON,
                    description="Review-approved Native Web standard review gate replacement results.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(standard_review_gate_replacement_results),
                        "summary": summary,
                        "standard_review_gate_replaced": bool(summary.get("standard_review_gate_replaced")),
                        "delivery_allowed": False,
                        "automatic_delivery": False,
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "target_artifact_mutated": bool(summary.get("target_artifact_mutated")),
                        "source": "review_approved_standard_review_gate_replacement_baseline",
                    },
                )
            )
        post_standard_review_gate_replacement_delivery_guard_reruns = (
            flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns")
            if isinstance(flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_delivery_guard_reruns"), list)
            else []
        )
        if post_standard_review_gate_replacement_delivery_guard_reruns:
            summary = (
                flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary", {})
                if isinstance(flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_delivery_guard_rerun_summary"), dict)
                else {}
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/delivery-guard-after-review-gate-replacement.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web post-standard-review-gate-replacement delivery guard rerun baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(post_standard_review_gate_replacement_delivery_guard_reruns),
                        "summary": summary,
                        "delivery_guard_rerun_performed": bool(summary.get("delivery_guard_rerun_performed")),
                        "delivery_guard_passed": bool(summary.get("delivery_guard_passed")),
                        "delivery_allowed": bool(summary.get("delivery_allowed")),
                        "automatic_delivery": False,
                        "manual_delivery_required": bool(summary.get("manual_delivery_required")),
                        "automatic_stitching": False,
                        "automatic_rollback": False,
                        "source": "post_standard_review_gate_replacement_delivery_guard_rerun_baseline",
                    },
                )
            )
        final_delivery_packages = (
            flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_final_delivery_packages")
            if isinstance(flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_final_delivery_packages"), list)
            else []
        )
        if final_delivery_packages:
            summary = (
                flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary", {})
                if isinstance(flow_timeline.get("auto_stitch_post_standard_review_gate_replacement_final_delivery_package_summary"), dict)
                else {}
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/final-delivery-package-after-review-gate-replacement.json",
                    kind=ArtifactKind.JSON,
                    description="Native Web final delivery package baseline after standard review gate replacement.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(final_delivery_packages),
                        "summary": summary,
                        "package_ready": bool(summary.get("package_ready")),
                        "final_delivery_packaged": bool(summary.get("final_delivery_packaged")),
                        "delivery_allowed": bool(summary.get("delivery_allowed")),
                        "automatic_delivery": False,
                        "manual_delivery_required": bool(summary.get("manual_delivery_required")),
                        "cross_run_transaction_committed": False,
                        "manifest_revision_committed": False,
                        "external_delivery_performed": False,
                        "source": "post_standard_review_gate_replacement_final_delivery_package_baseline",
                    },
                )
            )
        transaction_commit_results = (
            flow_timeline.get("auto_stitch_transaction_commit_results")
            if isinstance(flow_timeline.get("auto_stitch_transaction_commit_results"), list)
            else []
        )
        if transaction_commit_results:
            summary = (
                flow_timeline.get("auto_stitch_transaction_commit_summary", {})
                if isinstance(flow_timeline.get("auto_stitch_transaction_commit_summary"), dict)
                else {}
            )
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/final-delivery-transaction-commit.json",
                    kind=ArtifactKind.JSON,
                    description="Review-approved Native Web final delivery transaction commit baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(transaction_commit_results),
                        "summary": summary,
                        "transaction_commit_recorded": bool(summary.get("transaction_commit_recorded")),
                        "artifact_model_transaction_commit_recorded": bool(summary.get("artifact_model_transaction_commit_recorded")),
                        "cross_run_transaction_committed": False,
                        "manifest_revision_committed": False,
                        "automatic_delivery": False,
                        "manual_delivery_required": bool(summary.get("manual_delivery_required")),
                        "external_delivery_performed": False,
                        "filesystem_artifact_mutated": False,
                        "source": "explicit_review_only_final_delivery_transaction_commit_baseline",
                    },
                )
            )
        stitched_flows = flow_timeline.get("stitched_flows") if isinstance(flow_timeline.get("stitched_flows"), list) else []
        if stitched_flows:
            artifacts.append(
                ArtifactRef(
                    path="virtual://workspace/stitched-flow.json",
                    kind=ArtifactKind.JSON,
                    description="Review-approved Native Web stitched flow baseline.",
                    metadata={
                        "flow_id": flow_timeline.get("flow_id"),
                        "count": len(stitched_flows),
                        "automatic_stitching": False,
                        "source": "review_approved_stitch_proposal",
                    },
                )
            )
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
    """Create a NativeWebRuntime with a registry-resolved BrowserProvider."""

    if browser_provider is not None:
        return NativeWebRuntime(browser_provider=browser_provider)
    browser_id = browser or kwargs.get("browser_provider") or "playwright-chromium"
    try:
        provider = build_default_browser_provider_registry().create(browser_id, **kwargs)
    except BrowserProviderRegistryError as exc:
        raise BrowserProviderUnavailableError(f"Unsupported native browser provider: {browser_id}. {exc}") from exc
    return NativeWebRuntime(browser_provider=provider)
