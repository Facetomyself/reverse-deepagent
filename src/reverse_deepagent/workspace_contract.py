from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Iterable
from typing import Any


CONTRACT_VERSION = "2026-05-31.indexed-only"


@dataclass(frozen=True)
class WorkspaceFolderContract:
    """Machine-readable DeepAgents virtual workspace folder contract.

    The contract is intentionally an index layer. Existing flat workspace
    artifacts remain canonical until a future migration provides compatibility
    aliases and tests.
    """

    virtual_folder: str
    purpose: str
    owner_roles: tuple[str, ...]
    migration_status: str = "indexed-only"


@dataclass(frozen=True)
class SubagentRoleContract:
    """Stable subagent role contract used by orchestration and documentation."""

    role: str
    responsibility: str
    current_status: str
    workspace_folders: tuple[str, ...]


@dataclass(frozen=True)
class MiddlewareContract:
    """Ordered middleware/checkpoint contract for the reverse pipeline."""

    name: str
    order: int
    responsibility: str
    gates: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceArtifactRoute:
    """Route an existing flat artifact into the future virtual folder layout."""

    artifact_key: str
    legacy_path: str
    virtual_folder: str
    future_path: str
    category: str
    producer_roles: tuple[str, ...]
    migration_status: str = "indexed-only"


@dataclass(frozen=True)
class WorkspacePathResolution:
    """Resolved workspace artifact path view used before physical migration.

    The resolution is deliberately conservative: the legacy flat path remains
    the canonical read/write path unless callers explicitly opt in to a dual
    write plan.  This lets consumers move to a resolver API before the project
    performs any filesystem-level folder migration.
    """

    artifact_key: str
    legacy_path: str
    future_path: str
    virtual_uri: str
    canonical_path: str
    canonical_uri: str
    read_paths: tuple[str, ...]
    write_paths: tuple[str, ...]
    dual_write_enabled: bool
    physical_migration_enabled: bool
    canonical_path_remains_authoritative: bool
    migration_status: str
    virtual_folder: str
    category: str
    producer_roles: tuple[str, ...]
    dual_write_scope_enabled: bool = False
    dual_write_in_scope: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _jsonable_dataclass_items(items: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [asdict(item) for item in items]


def workspace_virtual_uri(path: str) -> str:
    """Return the stable virtual URI for a workspace path.

    ``WorkspaceArtifactRoute.future_path`` uses a leading ``/workspace/...``
    folder path for human readability. Runtime artifact refs historically use
    ``virtual://workspace/...`` without the leading slash, so manifest aliases
    keep that existing URI style.
    """

    return f"virtual://{path.lstrip('/')}"


def _normalize_workspace_lookup(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("virtual://"):
        return workspace_virtual_uri(normalized.removeprefix("virtual://"))
    if normalized.startswith("/workspace/"):
        return normalized
    if normalized.startswith("workspace/"):
        return normalized
    return normalized


def default_workspace_folders() -> tuple[WorkspaceFolderContract, ...]:
    """Return the stable indexed-only virtual folder layout."""

    return (
        WorkspaceFolderContract(
            virtual_folder="/workspace/recon/",
            purpose="Task normalization, route decisions, baseline recon notes, and source/network discovery.",
            owner_roles=("router", "web_recon"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/browser/",
            purpose="BrowserProvider session, navigation, DOM, console, storage, and provider smoke outputs.",
            owner_roles=("browser_runtime", "web_recon"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/debugger/",
            purpose="Breakpoints, paused snapshots, callframes, debugger actions, and paused-session continuation metadata.",
            owner_roles=("debugger", "protector"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/hooks/",
            purpose="Runtime hook installation results and hook timelines for functions, modules, requests, and anti-debug patches.",
            owner_roles=("hook", "protector"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/timeline/",
            purpose="Cross-request flow timeline evidence, conservative correlation groups, stitch candidates, proposals, and approved stitched-flow baselines.",
            owner_roles=("timeline", "review"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/rebuild/",
            purpose="Pure extraction, replay, Scrapy, and rebuild planning artifacts.",
            owner_roles=("rebuild", "delivery"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/review/",
            purpose="Review gates, review hints, delivery blocking decisions, and manual approval state.",
            owner_roles=("review", "delivery"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/delivery/",
            purpose="Final structured result, reports, artifact indexes, and delivery-ready summaries.",
            owner_roles=("delivery",),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/runtime/",
            purpose="Runtime capabilities, provider metadata, platform tool probes, and runtime export bundles.",
            owner_roles=("browser_runtime", "router"),
        ),
        WorkspaceFolderContract(
            virtual_folder="/workspace/evidence/",
            purpose="Evidence candidates, validated evidence, promotion records, and review-required evidence summaries.",
            owner_roles=("web_recon", "review"),
        ),
    )


def default_subagent_roles() -> tuple[SubagentRoleContract, ...]:
    """Return current and planned subagent role boundaries."""

    return (
        SubagentRoleContract(
            role="coordinator",
            responsibility="Owns task normalization, route orchestration, artifact manifesting, and final delivery synthesis.",
            current_status="implemented",
            workspace_folders=("/workspace/delivery/", "/workspace/evidence/", "/workspace/runtime/"),
        ),
        SubagentRoleContract(
            role="router",
            responsibility="Classifies reverse tasks and selects runtime/platform strategy without touching browser or MCP transport details.",
            current_status="implemented",
            workspace_folders=("/workspace/recon/", "/workspace/runtime/"),
        ),
        SubagentRoleContract(
            role="web_recon",
            responsibility="Runs Web recon through normalized runtime adapters and emits source, network, context, and evidence candidates.",
            current_status="implemented",
            workspace_folders=("/workspace/recon/", "/workspace/browser/", "/workspace/evidence/"),
        ),
        SubagentRoleContract(
            role="protector",
            responsibility="Applies explicit minimal protections, hooks, breakpoint/debugger flows, and opt-in mutation audits.",
            current_status="implemented",
            workspace_folders=("/workspace/debugger/", "/workspace/hooks/"),
        ),
        SubagentRoleContract(
            role="delivery",
            responsibility="Packages final reports, rebuild bundles, artifact index, and delivery guard outputs.",
            current_status="implemented",
            workspace_folders=("/workspace/rebuild/", "/workspace/review/", "/workspace/delivery/"),
        ),
        SubagentRoleContract(
            role="browser_runtime",
            responsibility="Owns BrowserProvider lifecycle, provider capability discovery, and browser smoke evidence.",
            current_status="implemented",
            workspace_folders=("/workspace/browser/", "/workspace/runtime/"),
        ),
        SubagentRoleContract(
            role="debugger",
            responsibility="Owns read-only debugger artifact review, paused-session continuation preflight summaries, callframe evidence, and debugger timeline decision boundaries.",
            current_status="implemented",
            workspace_folders=("/workspace/debugger/",),
        ),
        SubagentRoleContract(
            role="hook",
            responsibility="Owns read-only hook artifact review, function/module hook inventory summaries, hook timeline capture readiness, and source-logpoint audit boundaries.",
            current_status="implemented",
            workspace_folders=("/workspace/hooks/",),
        ),
        SubagentRoleContract(
            role="timeline",
            responsibility="Owns read-only flow timeline review, correlation group summaries, stitch proposal blockers, and auto-stitch gate boundaries.",
            current_status="implemented",
            workspace_folders=("/workspace/timeline/",),
        ),
        SubagentRoleContract(
            role="rebuild",
            responsibility="Owns rebuild generation and read-only rebuild artifact review for pure extraction, context-aware replay, generated Scrapy projects, and rebuild readiness boundaries.",
            current_status="implemented",
            workspace_folders=("/workspace/rebuild/",),
        ),
        SubagentRoleContract(
            role="review",
            responsibility="Owns evidence promotion review requirements, read-only review gate evaluation, and manual approval boundaries.",
            current_status="implemented",
            workspace_folders=("/workspace/review/", "/workspace/evidence/", "/workspace/timeline/"),
        ),
    )


def default_middleware_chain() -> tuple[MiddlewareContract, ...]:
    """Return the deterministic high-level middleware/checkpoint order."""

    return (
        MiddlewareContract(
            name="task_normalize",
            order=10,
            responsibility="Normalize user task text into a TaskCard and route-ready task record.",
        ),
        MiddlewareContract(
            name="runtime_capability",
            order=20,
            responsibility="Capture runtime/backend/provider capabilities before invoking runtime-specific work.",
        ),
        MiddlewareContract(
            name="browser_session",
            order=30,
            responsibility="Ensure or attach to an explicit browser session only for Web runtimes that support BrowserProvider semantics.",
            gates=("web-runtime-only", "no-implicit-mcp-start"),
        ),
        MiddlewareContract(
            name="evidence_promotion",
            order=40,
            responsibility="Promote raw evidence into machine-readable review/delivery readiness records.",
        ),
        MiddlewareContract(
            name="review_gate",
            order=50,
            responsibility="Block delivery when evidence, rebuild, or timeline stitch proposals require manual review.",
        ),
        MiddlewareContract(
            name="artifact_manifest",
            order=60,
            responsibility="Write backend-aware artifact manifest entries with platform-neutral categories.",
        ),
        MiddlewareContract(
            name="delivery_guard",
            order=70,
            responsibility="Package final reports only after review and artifact contracts are represented.",
        ),
    )


def default_workspace_artifact_routes() -> tuple[WorkspaceArtifactRoute, ...]:
    """Return indexed-only routes for existing flat workspace artifacts."""

    routes = (
        ("workspace_task_card", "workspace/task-card.json", "/workspace/recon/", "task-card.json", "workspace", ("router",)),
        ("workspace_dual_write_plan", "workspace/workspace-dual-write-plan.json", "/workspace/delivery/", "workspace-dual-write-plan.json", "workspace", ("coordinator", "delivery")),
        ("workspace_dual_write_pilot_result", "workspace/workspace-dual-write-pilot-result.json", "/workspace/delivery/", "workspace-dual-write-pilot-result.json", "audit", ("coordinator", "review")),
        ("workspace_route", "workspace/route-decision.json", "/workspace/recon/", "route-decision.json", "workspace", ("router",)),
        ("workspace_recon", "workspace/recon-result.json", "/workspace/recon/", "recon-result.json", "workspace", ("web_recon",)),
        ("workspace_network_requests", "workspace/network-requests.json", "/workspace/recon/", "network-requests.json", "network", ("web_recon",)),
        ("workspace_source_hits", "workspace/source-hits.json", "/workspace/recon/", "source-hits.json", "source", ("web_recon",)),
        ("workspace_source_contexts", "workspace/source-contexts.json", "/workspace/recon/", "source-contexts.json", "source", ("web_recon",)),
        ("workspace_script_inventory", "workspace/script-inventory.json", "/workspace/recon/", "script-inventory.json", "source", ("web_recon",)),
        ("workspace_dom_snapshot", "workspace/dom-snapshot.json", "/workspace/browser/", "dom-snapshot.json", "runtime-context", ("browser_runtime", "web_recon")),
        ("workspace_console_messages", "workspace/console-messages.json", "/workspace/browser/", "console-messages.json", "runtime-context", ("browser_runtime", "web_recon")),
        ("workspace_navigation_events", "workspace/navigation-events.json", "/workspace/browser/", "navigation-events.json", "trace", ("browser_runtime", "web_recon")),
        ("workspace_browser_provider_smoke", "workspace/browser-provider-smoke.json", "/workspace/browser/", "browser-provider-smoke.json", "runtime-context", ("browser_runtime", "review")),
        ("workspace_runtime_context", "workspace/runtime-context.json", "/workspace/runtime/", "runtime-context.json", "runtime-context", ("browser_runtime",)),
        ("workspace_runtime_context_diff", "workspace/runtime-context-diff.json", "/workspace/runtime/", "runtime-context-diff.json", "runtime-context", ("browser_runtime",)),
        ("workspace_runtime_capabilities", "workspace/runtime-capabilities.json", "/workspace/runtime/", "runtime-capabilities.json", "runtime-context", ("router", "browser_runtime")),
        ("workspace_runtime_export_bundle", "workspace/runtime-export-bundle.json", "/workspace/runtime/", "runtime-export-bundle.json", "export", ("router", "browser_runtime")),
        ("workspace_platform_tool_probe", "workspace/platform-tool-probe.json", "/workspace/runtime/", "platform-tool-probe.json", "runtime-context", ("router",)),
        ("workspace_breakpoints", "workspace/breakpoints.json", "/workspace/debugger/", "breakpoints.json", "trace", ("debugger", "protector")),
        ("workspace_debugger_paused", "workspace/debugger-paused.json", "/workspace/debugger/", "debugger-paused.json", "trace", ("debugger", "protector")),
        ("workspace_callframes", "workspace/callframes.json", "/workspace/debugger/", "callframes.json", "trace", ("debugger", "protector")),
        ("workspace_callframe_evaluations", "workspace/callframe-evaluations.json", "/workspace/debugger/", "callframe-evaluations.json", "trace", ("debugger", "protector")),
        ("workspace_debugger_actions", "workspace/debugger-actions.json", "/workspace/debugger/", "debugger-actions.json", "trace", ("debugger", "protector")),
        ("workspace_debugger_session", "workspace/debugger-session.json", "/workspace/debugger/", "debugger-session.json", "trace", ("debugger", "protector")),
        ("workspace_debugger_timeline", "workspace/debugger-timeline.json", "/workspace/debugger/", "debugger-timeline.json", "trace", ("debugger", "timeline")),
        ("workspace_protection_triage_hooks", "workspace/protection-triage-hooks.json", "/workspace/hooks/", "protection-triage-hooks.json", "hook-timeline", ("hook", "debugger", "review")),
        ("workspace_wasm_runtime_candidates", "workspace/wasm-runtime-candidates.json", "/workspace/runtime/", "wasm-runtime-candidates.json", "runtime-context", ("hook", "web_recon", "review")),
        ("workspace_vm_dispatcher_candidates", "workspace/vm-dispatcher-candidates.json", "/workspace/runtime/", "vm-dispatcher-candidates.json", "runtime-context", ("debugger", "hook", "review")),
        ("workspace_hook_timeline", "workspace/hook-timeline.json", "/workspace/hooks/", "hook-timeline.json", "hook-timeline", ("hook", "protector")),
        ("workspace_function_hooks", "workspace/function-hooks.json", "/workspace/hooks/", "function-hooks.json", "hook-timeline", ("hook", "protector")),
        ("workspace_function_hook_timeline", "workspace/function-hook-timeline.json", "/workspace/hooks/", "function-hook-timeline.json", "hook-timeline", ("hook", "timeline")),
        ("workspace_module_hooks", "workspace/module-hooks.json", "/workspace/hooks/", "module-hooks.json", "hook-timeline", ("hook", "protector")),
        ("workspace_module_hook_timeline", "workspace/module-hook-timeline.json", "/workspace/hooks/", "module-hook-timeline.json", "hook-timeline", ("hook", "timeline")),
        ("workspace_async_chunk_load_plan", "workspace/async-chunk-load-plan.json", "/workspace/runtime/", "async-chunk-load-plan.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_async_chunk_module_diff", "workspace/async-chunk-module-diff.json", "/workspace/hooks/", "async-chunk-module-diff.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_traversal_plan", "workspace/custom-loader-traversal-plan.json", "/workspace/runtime/", "custom-loader-traversal-plan.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_continuation_workflow", "workspace/custom-loader-continuation-workflow.json", "/workspace/runtime/", "custom-loader-continuation-workflow.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_continuation_journal", "workspace/custom-loader-continuation-journal.json", "/workspace/runtime/", "custom-loader-continuation-journal.json", "audit", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_continuation_execution", "workspace/custom-loader-continuation-execution.json", "/workspace/runtime/", "custom-loader-continuation-execution.json", "audit", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_execution_preflight", "workspace/custom-loader-execution-preflight.json", "/workspace/runtime/", "custom-loader-execution-preflight.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_execution_result", "workspace/custom-loader-execution-result.json", "/workspace/runtime/", "custom-loader-execution-result.json", "trace", ("hook", "browser_runtime", "review")),
        ("workspace_custom_loader_module_diff", "workspace/custom-loader-module-diff.json", "/workspace/hooks/", "custom-loader-module-diff.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_module_federation_get_init_plan", "workspace/module-federation-get-init-plan.json", "/workspace/runtime/", "module-federation-get-init-plan.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_module_federation_get_init_result", "workspace/module-federation-get-init-result.json", "/workspace/runtime/", "module-federation-get-init-result.json", "trace", ("hook", "browser_runtime", "review")),
        ("workspace_module_federation_factory_invoke_result", "workspace/module-federation-factory-invoke-result.json", "/workspace/runtime/", "module-federation-factory-invoke-result.json", "trace", ("hook", "browser_runtime", "review")),
        ("workspace_module_federation_export_hook_plan", "workspace/module-federation-export-hook-plan.json", "/workspace/hooks/", "module-federation-export-hook-plan.json", "triage", ("hook", "browser_runtime", "review")),
        ("workspace_async_chunk_load_result", "workspace/async-chunk-load-result.json", "/workspace/runtime/", "async-chunk-load-result.json", "trace", ("hook", "browser_runtime", "review")),
        ("workspace_source_map_fetch_plan", "workspace/source-map-fetch-plan.json", "/workspace/debugger/", "source-map-fetch-plan.json", "triage", ("debugger", "hook", "review")),
        ("workspace_source_map_fetch_result", "workspace/source-map-fetch-result.json", "/workspace/debugger/", "source-map-fetch-result.json", "trace", ("debugger", "hook", "review")),
        ("workspace_source_logpoints", "workspace/source-logpoints.json", "/workspace/debugger/", "source-logpoints.json", "trace", ("debugger", "hook")),
        ("workspace_source_logpoint_timeline", "workspace/source-logpoint-timeline.json", "/workspace/timeline/", "source-logpoint-timeline.json", "trace", ("timeline", "debugger")),
        ("workspace_mutation_audit", "workspace/mutation-audit.json", "/workspace/debugger/", "mutation-audit.json", "trace", ("debugger", "review")),
        ("workspace_page_mutation_audit", "workspace/page-mutation-audit.json", "/workspace/browser/", "page-mutation-audit.json", "trace", ("browser_runtime", "review")),
        ("workspace_object_root_mutation_audit", "workspace/object-root-mutation-audit.json", "/workspace/browser/", "object-root-mutation-audit.json", "trace", ("browser_runtime", "review")),
        ("workspace_mutation_observer_timeline", "workspace/mutation-observer-timeline.json", "/workspace/timeline/", "mutation-observer-timeline.json", "trace", ("timeline", "browser_runtime")),
        ("workspace_flow_timeline", "workspace/flow-timeline.json", "/workspace/timeline/", "flow-timeline.json", "trace", ("timeline", "review")),
        ("workspace_auto_stitch_conflict_resolutions", "workspace/auto-stitch-conflict-resolutions.json", "/workspace/timeline/", "auto-stitch-conflict-resolutions.json", "trace", ("timeline", "review")),
        ("workspace_auto_stitch_materialization_results", "workspace/auto-stitch-materialization-results.json", "/workspace/timeline/", "auto-stitch-materialization-results.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_materialization_audit", "workspace/stitched-flow-materialization-audit.json", "/workspace/timeline/", "stitched-flow-materialization-audit.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_rollback_plan", "workspace/stitched-flow-rollback-plan.json", "/workspace/timeline/", "stitched-flow-rollback-plan.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_materialization_transactions", "workspace/stitched-flow-materialization-transactions.json", "/workspace/timeline/", "stitched-flow-materialization-transactions.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_rollback_executions", "workspace/stitched-flow-rollback-executions.json", "/workspace/timeline/", "stitched-flow-rollback-executions.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_physical_rollback_diff", "workspace/stitched-flow-physical-rollback-diff.json", "/workspace/timeline/", "stitched-flow-physical-rollback-diff.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow_physical_rollback_results", "workspace/stitched-flow-physical-rollback-results.json", "/workspace/timeline/", "stitched-flow-physical-rollback-results.json", "trace", ("timeline", "review")),
        ("workspace_stitched_flow", "workspace/stitched-flow.json", "/workspace/timeline/", "stitched-flow.json", "trace", ("timeline", "review")),
        ("workspace_function_candidates", "workspace/function-candidates.json", "/workspace/evidence/", "function-candidates.json", "source", ("web_recon", "rebuild")),
        ("workspace_function_validations", "workspace/function-validations.json", "/workspace/evidence/", "function-validations.json", "trace", ("web_recon", "rebuild")),
        ("workspace_function_validation_summary", "workspace/function-validation-summary.json", "/workspace/evidence/", "function-validation-summary.json", "trace", ("web_recon", "rebuild")),
        ("workspace_evidence_candidates", "workspace/evidence-candidates.json", "/workspace/evidence/", "evidence-candidates.json", "evidence", ("web_recon", "review")),
        ("workspace_evidence_validated", "workspace/evidence-validated.json", "/workspace/evidence/", "evidence-validated.json", "evidence", ("web_recon", "review")),
        ("workspace_evidence_promotion", "workspace/evidence-promotion.json", "/workspace/evidence/", "evidence-promotion.json", "evidence", ("review",)),
        ("workspace_review_approval_record", "workspace/review-approval-record.json", "/workspace/review/", "review-approval-record.json", "audit", ("review", "delivery")),
        ("workspace_review_approval_ledger", "workspace/review-approval-ledger.json", "/workspace/review/", "review-approval-ledger.json", "audit", ("review", "delivery")),
        ("workspace_review_gate_after_rollback", "workspace/review-gate-after-rollback.json", "/workspace/review/", "review-gate-after-rollback.json", "triage", ("review", "timeline")),
        ("workspace_review_gate_after_physical_rollback", "workspace/review-gate-after-physical-rollback.json", "/workspace/review/", "review-gate-after-physical-rollback.json", "triage", ("review", "timeline")),
        ("workspace_review_gate_replacement_results", "workspace/review-gate-replacement-results.json", "/workspace/review/", "review-gate-replacement-results.json", "triage", ("review", "delivery")),
        ("workspace_delivery_guard_after_review_gate_replacement", "workspace/delivery-guard-after-review-gate-replacement.json", "/workspace/delivery/", "delivery-guard-after-review-gate-replacement.json", "triage", ("delivery", "review")),
        ("workspace_final_delivery_package_after_review_gate_replacement", "workspace/final-delivery-package-after-review-gate-replacement.json", "/workspace/delivery/", "final-delivery-package-after-review-gate-replacement.json", "export", ("delivery", "review")),
        ("workspace_final_delivery_transaction_commit", "workspace/final-delivery-transaction-commit.json", "/workspace/delivery/", "final-delivery-transaction-commit.json", "export", ("delivery", "review")),
        ("workspace_delivery_receipt", "workspace/delivery-receipt.json", "/workspace/delivery/", "delivery-receipt.json", "export", ("delivery", "review")),
        ("workspace_delivery_transaction_journal", "workspace/delivery-transaction-journal.json", "/workspace/delivery/", "delivery-transaction-journal.json", "export", ("delivery", "review")),
        ("workspace_external_delivery_result", "workspace/external-delivery-result.json", "/workspace/delivery/", "external-delivery-result.json", "export", ("delivery", "review")),
        ("workspace_external_delivery_duplicate_guard", "workspace/external-delivery-duplicate-guard.json", "/workspace/delivery/", "external-delivery-duplicate-guard.json", "export", ("delivery", "review")),
        ("workspace_external_delivery_idempotency_ledger", "workspace/external-delivery-idempotency-ledger.json", "/workspace/delivery/", "external-delivery-idempotency-ledger.json", "export", ("delivery", "review")),
        ("workspace_delivery_transaction_lock", "workspace/delivery-transaction-lock.json", "/workspace/delivery/", "delivery-transaction-lock.json", "triage", ("delivery", "review")),
        ("workspace_delivery_transaction_lock_release", "workspace/delivery-transaction-lock-release.json", "/workspace/delivery/", "delivery-transaction-lock-release.json", "audit", ("delivery", "review")),
        ("workspace_delivery_distributed_transaction_lock", "workspace/delivery-distributed-transaction-lock.json", "/workspace/delivery/", "delivery-distributed-transaction-lock.json", "triage", ("delivery", "review")),
        ("workspace_delivery_distributed_transaction_lock_operation", "workspace/delivery-distributed-transaction-lock-operation.json", "/workspace/delivery/", "delivery-distributed-transaction-lock-operation.json", "audit", ("delivery", "review")),
        ("workspace_delivery_resume_plan", "workspace/delivery-resume-plan.json", "/workspace/delivery/", "delivery-resume-plan.json", "triage", ("delivery", "review")),
        ("workspace_delivery_resume_execution", "workspace/delivery-resume-execution.json", "/workspace/delivery/", "delivery-resume-execution.json", "triage", ("delivery", "review")),
        ("workspace_delivery_resume_workflow", "workspace/delivery-resume-workflow.json", "/workspace/delivery/", "delivery-resume-workflow.json", "triage", ("delivery", "review")),
        ("workspace_delivery_resume_workflow_journal", "workspace/delivery-resume-workflow-journal.json", "/workspace/delivery/", "delivery-resume-workflow-journal.json", "audit", ("delivery", "review")),
        ("workspace_delivery_transaction_idempotency_guard", "workspace/delivery-transaction-idempotency-guard.json", "/workspace/delivery/", "delivery-transaction-idempotency-guard.json", "export", ("delivery", "review")),
        ("workspace_delivery_rollback_state", "workspace/delivery-rollback-state.json", "/workspace/delivery/", "delivery-rollback-state.json", "triage", ("delivery", "review")),
        ("workspace_delivery_rollback_execution", "workspace/delivery-rollback-execution.json", "/workspace/delivery/", "delivery-rollback-execution.json", "triage", ("delivery", "review")),
        ("workspace_delivery_transition_execution", "workspace/delivery-transition-execution.json", "/workspace/delivery/", "delivery-transition-execution.json", "triage", ("delivery", "review")),
        ("workspace_delivery_recovery_execution", "workspace/delivery-recovery-execution.json", "/workspace/delivery/", "delivery-recovery-execution.json", "triage", ("delivery", "review")),
        ("workspace_delivery_manifest_revision", "workspace/delivery-manifest-revision.json", "/workspace/delivery/", "delivery-manifest-revision.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_mutation", "workspace/backend-artifact-manifest-mutation.json", "/workspace/delivery/", "backend-artifact-manifest-mutation.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_patched", "workspace/backend-artifact-manifest.patched.json", "/workspace/delivery/", "backend-artifact-manifest.patched.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_preflight", "workspace/backend-artifact-manifest-preflight.json", "/workspace/delivery/", "backend-artifact-manifest-preflight.json", "triage", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_in_place_mutation", "workspace/backend-artifact-manifest-in-place-mutation.json", "/workspace/delivery/", "backend-artifact-manifest-in-place-mutation.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_rollback", "workspace/backend-artifact-manifest.rollback.json", "/workspace/delivery/", "backend-artifact-manifest.rollback.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_recovery_preflight", "workspace/backend-artifact-manifest-recovery-preflight.json", "/workspace/delivery/", "backend-artifact-manifest-recovery-preflight.json", "triage", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_recovery", "workspace/backend-artifact-manifest-recovery.json", "/workspace/delivery/", "backend-artifact-manifest-recovery.json", "export", ("delivery", "review")),
        ("workspace_backend_artifact_manifest_transaction_commit", "workspace/backend-artifact-manifest-transaction-commit.json", "/workspace/delivery/", "backend-artifact-manifest-transaction-commit.json", "export", ("delivery", "review")),
        ("workspace_review_gate", "workspace/review-gate.json", "/workspace/review/", "review-gate.json", "triage", ("review", "delivery")),
        ("workspace_rebuild_plan", "workspace/rebuild-plan.json", "/workspace/rebuild/", "rebuild-plan.json", "rebuild", ("rebuild", "delivery")),
        ("workspace_final", "workspace/final-result.json", "/workspace/delivery/", "final-result.json", "workspace", ("delivery", "coordinator")),
        ("workspace_backend_artifact_manifest", "workspace/backend-artifact-manifest.json", "/workspace/delivery/", "backend-artifact-manifest.json", "export", ("delivery", "coordinator")),
        ("workspace_workspace_contract", "workspace/workspace-contract.json", "/workspace/delivery/", "workspace-contract.json", "workspace", ("coordinator", "delivery")),
    )
    return tuple(
        WorkspaceArtifactRoute(
            artifact_key=artifact_key,
            legacy_path=legacy_path,
            virtual_folder=virtual_folder,
            future_path=f"{virtual_folder}{filename}",
            category=category,
            producer_roles=producer_roles,
        )
        for artifact_key, legacy_path, virtual_folder, filename, category, producer_roles in routes
    )


def workspace_artifact_routes_by_key() -> dict[str, WorkspaceArtifactRoute]:
    """Return workspace artifact routes keyed by canonical artifact key."""

    return {route.artifact_key: route for route in default_workspace_artifact_routes()}


def workspace_artifact_routes_by_path() -> dict[str, WorkspaceArtifactRoute]:
    """Return workspace artifact routes keyed by legacy path, future path, and virtual URI."""

    routes: dict[str, WorkspaceArtifactRoute] = {}
    for route in default_workspace_artifact_routes():
        routes[route.legacy_path] = route
        routes[route.future_path] = route
        routes[workspace_virtual_uri(route.future_path)] = route
    return routes


class WorkspacePathResolver:
    """Resolve canonical and future workspace paths without moving artifacts.

    ``enable_dual_write`` is an opt-in planning flag.  When enabled, write
    plans include both the canonical flat path and the foldered future path,
    but ``canonical_path_remains_authoritative`` stays true until a later
    physical migration explicitly changes the contract.
    """

    def __init__(
        self,
        *,
        enable_dual_write: bool = False,
        physical_migration_enabled: bool = False,
        dual_write_artifact_keys: Iterable[str] | None = None,
    ) -> None:
        self.enable_dual_write = enable_dual_write
        self.physical_migration_enabled = physical_migration_enabled
        self.dual_write_artifact_keys = (
            None
            if dual_write_artifact_keys is None
            else frozenset(str(key) for key in dual_write_artifact_keys if str(key))
        )
        self._routes_by_key = workspace_artifact_routes_by_key()
        self._routes_by_path = workspace_artifact_routes_by_path()

    def resolve_artifact_key(self, artifact_key: str) -> WorkspacePathResolution | None:
        route = self._routes_by_key.get(artifact_key)
        if route is None:
            return None
        return self._resolution_for_route(route)

    def resolve_path(self, path_or_uri: str) -> WorkspacePathResolution | None:
        route = self._routes_by_path.get(_normalize_workspace_lookup(path_or_uri))
        if route is None:
            return None
        return self._resolution_for_route(route)

    def plan_dual_write(self, artifact_key: str) -> dict[str, Any]:
        resolution = self.resolve_artifact_key(artifact_key)
        if resolution is None:
            return {
                "artifact_key": artifact_key,
                "status": "unknown-artifact",
                "write_paths": (),
                "dual_write_enabled": self.enable_dual_write,
                "physical_migration_enabled": self.physical_migration_enabled,
            }
        return {
            "artifact_key": artifact_key,
            "status": "planned" if resolution.dual_write_enabled else "out-of-scope" if resolution.dual_write_scope_enabled else "not-enabled",
            "canonical_path": resolution.canonical_path,
            "future_path": resolution.future_path,
            "virtual_uri": resolution.virtual_uri,
            "write_paths": resolution.write_paths,
            "dual_write_enabled": resolution.dual_write_enabled,
            "dual_write_scope_enabled": resolution.dual_write_scope_enabled,
            "dual_write_in_scope": resolution.dual_write_in_scope,
            "physical_migration_enabled": resolution.physical_migration_enabled,
            "canonical_path_remains_authoritative": resolution.canonical_path_remains_authoritative,
            "migration_status": resolution.migration_status,
        }

    def _resolution_for_route(self, route: WorkspaceArtifactRoute) -> WorkspacePathResolution:
        scope_enabled = self.dual_write_artifact_keys is not None
        in_scope = not scope_enabled or route.artifact_key in self.dual_write_artifact_keys
        dual_write_enabled = self.enable_dual_write and in_scope
        write_paths = (route.legacy_path, route.future_path) if dual_write_enabled else (route.legacy_path,)
        if dual_write_enabled and scope_enabled:
            migration_status = "scoped-dual-write-plan-only"
        elif dual_write_enabled:
            migration_status = "dual-write-plan-only"
        elif self.enable_dual_write and scope_enabled:
            migration_status = "dual-write-out-of-scope"
        else:
            migration_status = "resolver-only"
        return WorkspacePathResolution(
            artifact_key=route.artifact_key,
            legacy_path=route.legacy_path,
            future_path=route.future_path,
            virtual_uri=workspace_virtual_uri(route.future_path),
            canonical_path=route.legacy_path,
            canonical_uri=workspace_virtual_uri(route.legacy_path),
            read_paths=(route.legacy_path, route.future_path, workspace_virtual_uri(route.future_path)),
            write_paths=write_paths,
            dual_write_enabled=dual_write_enabled,
            physical_migration_enabled=self.physical_migration_enabled,
            canonical_path_remains_authoritative=True,
            migration_status=migration_status,
            virtual_folder=route.virtual_folder,
            category=route.category,
            producer_roles=route.producer_roles,
            dual_write_scope_enabled=scope_enabled,
            dual_write_in_scope=in_scope,
        )


def workspace_manifest_alias_metadata(artifact_key: str) -> dict[str, Any]:
    """Return manifest-only virtual folder alias metadata for an artifact.

    Existing flat ``workspace/*.json`` paths remain canonical. The returned
    metadata is an alias index that lets consumers discover the future
    DeepAgents virtual folder path without requiring a physical path migration.
    """

    route = workspace_artifact_routes_by_key().get(artifact_key)
    if route is None:
        return {}
    resolver = WorkspacePathResolver()
    resolution = resolver.resolve_artifact_key(artifact_key)
    if resolution is None:
        return {}
    return {
        "workspace_alias": {
            "canonical_path": resolution.canonical_path,
            "canonical_uri": resolution.canonical_uri,
            "canonical_path_remains_authoritative": resolution.canonical_path_remains_authoritative,
            "virtual_folder": resolution.virtual_folder,
            "future_path": resolution.future_path,
            "virtual_uri": resolution.virtual_uri,
            "migration_status": "manifest-alias-only",
            "route_migration_status": route.migration_status,
            "resolver_migration_status": resolution.migration_status,
            "category": resolution.category,
            "producer_roles": list(resolution.producer_roles),
        }
    }


def workspace_contract_payload() -> dict[str, Any]:
    """Return the current DeepAgents workspace contract as JSON-ready data."""

    routes = default_workspace_artifact_routes()
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "indexed-only",
        "path_migration_policy": {
            "existing_flat_workspace_paths_remain_canonical": True,
            "do_not_move_existing_artifacts_without_compatibility_aliases": True,
            "foldered_paths_are_future_targets": True,
            "backend_manifest_includes_foldered_aliases": True,
            "foldered_aliases_are_manifest_only": True,
            "workspace_path_resolver_available": True,
            "dual_write_is_opt_in": True,
            "dual_write_default_enabled": False,
            "actual_dual_write_writer_available": True,
            "physical_migration_default_enabled": False,
        },
        "path_resolver": {
            "status": "resolver-only",
            "default_canonical_path": "legacy_path",
            "default_write_policy": "legacy-only",
            "opt_in_dual_write_policy": "legacy-and-future-path",
            "dual_write_audit_artifact": "workspace/workspace-dual-write-plan.json",
            "does_not_create_directories": False,
            "does_not_move_existing_artifacts": True,
        },
        "workspace_folders": _jsonable_dataclass_items(default_workspace_folders()),
        "subagent_roles": _jsonable_dataclass_items(default_subagent_roles()),
        "middleware_chain": _jsonable_dataclass_items(default_middleware_chain()),
        "artifact_routes": _jsonable_dataclass_items(routes),
        "artifact_route_count": len(routes),
    }
