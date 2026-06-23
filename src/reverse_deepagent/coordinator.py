from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field

from reverse_deepagent.evidence import promote_evidence, promotion_workspace_payloads
from reverse_deepagent.rebuild import write_rebuild_bundle
from reverse_deepagent.review_gate import evaluate_review_gate, review_gate_workspace_payload
from reverse_deepagent.runtime import (
    RuntimeBackendCapabilities,
    RuntimeExportBundle,
    ReverseRuntime,
    WebReverseRuntime,
)
from reverse_deepagent.runtime.chrome import ChromeCommandResult, ChromeDebugConfig, ensure_chrome_debug, stop_chrome_debug
from reverse_deepagent.runtime.legacy_mcp import (
    is_legacy_mcp_runtime_kind,
    legacy_mcp_alias_warning as _legacy_mcp_alias_warning,
)
from reverse_deepagent.runtime.manifest import (
    _artifact_category_from_key,
    _build_backend_artifact_manifest,
)
from reverse_deepagent.browser_provider_smoke_acceptance import browser_provider_smoke_acceptance as _browser_smoke_impl
from reverse_deepagent.runtime.registry import (
    DEFAULT_RUNTIME_BACKEND_REGISTRY,
    build_default_runtime_registry,
    build_runtime,
    list_runtime_backends,
)
from reverse_deepagent.schemas import (
    ArtifactKind,
    ArtifactRef,
    ConfidenceLevel,
    EvidenceItem,
    EvidenceKind,
    ExecutionStatus,
    FinalResult,
    KeyFindings,
    ReconResult,
    ReverseStage,
    RouterResult,
    SchemaBaseModel,
    TaskCard,
)
from reverse_deepagent.tools.route_tools import normalize_task_card, route_from_task_card
from reverse_deepagent.workspace_contract import WorkspacePathResolver, workspace_contract_payload

class ReversePipelineOutput(SchemaBaseModel):
    """Complete result returned by the deterministic coordinator pipeline."""

    final_result: FinalResult = Field(description="Final structured reverse result.")
    artifacts: dict[str, str] = Field(default_factory=dict, description="Generated artifact path index.")
    chrome_launch: ChromeCommandResult | None = Field(default=None, description="Chrome launch command result, if used.")
    chrome_stop: ChromeCommandResult | None = Field(default=None, description="Chrome stop command result, if used.")


class PlatformPipelineOutput(SchemaBaseModel):
    """Platform-neutral pipeline result for any ReverseRuntime backend."""

    final_result: FinalResult = Field(description="Final structured platform-neutral result.")
    artifacts: dict[str, str] = Field(default_factory=dict, description="Generated artifact path index.")
    runtime_capabilities: RuntimeBackendCapabilities = Field(description="Runtime backend capability snapshot used for routing.")
    runtime_export_bundle: RuntimeExportBundle = Field(description="Raw runtime export bundle emitted by the backend.")




def build_markdown_report(final_result: FinalResult) -> str:
    """Build a human-readable Markdown report from a final result."""

    findings = final_result.key_findings
    lines = [
        "# Reverse DeepAgent Demo Report",
        "",
        "## Task Card",
        f"- target_url_or_file: {final_result.task_card.target_url_or_file}",
        f"- target_param_or_api: {final_result.task_card.target_param_or_api}",
        f"- goal: {final_result.task_card.goal}",
        f"- boundaries: {final_result.task_card.boundaries}",
        f"- sample_request: {final_result.task_card.sample_request or ''}",
        f"- protection_hints: {', '.join(final_result.task_card.protection_hints)}",
        "",
        "## Result",
        f"- mode: {final_result.mode.value}",
        f"- stage: {final_result.stage.value}",
        f"- status: {final_result.status.value}",
        f"- confidence: {final_result.confidence.value}",
        f"- next_action: {final_result.next_action}",
        "",
        "## Facts",
    ]
    lines.extend([f"- {item}" for item in findings.facts] or ["- (none)"])
    lines.extend(["", "## Inferences"])
    lines.extend([f"- {item}" for item in findings.inferences] or ["- (none)"])
    lines.extend(["", "## Unknowns"])
    lines.extend([f"- {item}" for item in findings.unknowns] or ["- (none)"])
    return "\n".join(lines) + "\n"






def legacy_mcp_alias_warning(runtime_kind: str) -> str | None:
    """Return the deprecation warning for legacy MCP aliases, if applicable."""

    return _legacy_mcp_alias_warning(runtime_kind)




def write_outputs(
    base_dir: Path,
    task_card: TaskCard,
    route_result: RouterResult,
    recon_result: ReconResult,
    final_result: FinalResult,
    export_bundle: dict[str, Any],
    runtime_capabilities: RuntimeBackendCapabilities | None = None,
    browser_provider_smoke: dict[str, Any] | None = None,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: set[str] | None = None,) -> dict[str, str]:
    """Persist the standard workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    workspace_resolver = WorkspacePathResolver(enable_dual_write=enable_workspace_dual_write, dual_write_artifact_keys=workspace_dual_write_artifact_keys)
    workspace_write_records: list[dict[str, Any]] = []
    report_json_path = reports_dir / "demo-final-result.json"
    report_md_path = reports_dir / "demo-final-report.md"
    index_path = exports_dir / "artifact-index.json"
    workspace_artifact_paths = _write_workspace_artifacts(base_dir, workspace_dir, final_result, workspace_resolver, workspace_write_records)
    rebuild_result = write_rebuild_bundle(base_dir, task_card, final_result)
    rebuild_artifact_paths = _rebuild_paths_from_result(rebuild_result)

    task_card_path = _write_workspace_json(base_dir, "workspace_task_card", task_card.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    route_path = _write_workspace_json(base_dir, "workspace_route", route_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    recon_path = _write_workspace_json(base_dir, "workspace_recon", recon_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    final_workspace_path = _write_workspace_json(base_dir, "workspace_final", final_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    workspace_contract_path = _write_workspace_json(base_dir, "workspace_workspace_contract", workspace_contract_payload(), workspace_resolver, workspace_write_records)
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(base_dir, workspace_dir, evidence_promotion, workspace_resolver, workspace_write_records)
    review_gate = evaluate_review_gate(rebuild_result, evidence_promotion)
    review_gate_path = _write_review_gate_artifact(base_dir, workspace_dir, review_gate, workspace_resolver, workspace_write_records)
    _write_json(report_json_path, final_result.model_dump(mode="json"))
    report_md_path.write_text(build_markdown_report(final_result), encoding="utf-8")

    output_paths = {
        "workspace_task_card": str(task_card_path),
        "workspace_route": str(route_path),
        "workspace_recon": str(recon_path),
        "workspace_final": str(final_workspace_path),
        "workspace_workspace_contract": str(workspace_contract_path),
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "index": str(index_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in workspace_artifact_paths.items()})
    output_paths.update({f"workspace_{key}": value for key, value in evidence_artifact_paths.items()})
    output_paths["workspace_review_gate"] = str(review_gate_path)
    output_paths.update({f"rebuild_{key}": value for key, value in rebuild_artifact_paths.items() if key != "rebuild_plan"})
    if "rebuild_plan" in rebuild_artifact_paths:
        output_paths["workspace_rebuild_plan"] = rebuild_artifact_paths["rebuild_plan"]
    if enable_workspace_dual_write:
        dual_write_plan_path = base_dir / "workspace" / "workspace-dual-write-plan.json"
        output_paths["workspace_dual_write_plan"] = str(dual_write_plan_path)
    manifest_path = base_dir / "workspace" / "backend-artifact-manifest.json"
    output_paths["workspace_backend_artifact_manifest"] = str(manifest_path)

    capabilities = runtime_capabilities or RuntimeBackendCapabilities(backend_id="unknown", display_name="Unknown Runtime")
    browser_provider_smoke_path: Path | None = None
    browser_provider_smoke_attachment: dict[str, Any] | None = None
    browser_provider_smoke_acceptance: dict[str, Any] | None = None
    if browser_provider_smoke is not None:
        browser_provider_smoke_attachment = dict(browser_provider_smoke)
        browser_provider_smoke_acceptance = _browser_provider_smoke_acceptance(browser_provider_smoke_attachment, capabilities)
        browser_provider_smoke_attachment["attachment_acceptance"] = browser_provider_smoke_acceptance
        browser_provider_smoke_path = _write_workspace_json(
            base_dir,
            "workspace_browser_provider_smoke",
            browser_provider_smoke_attachment,
            workspace_resolver,
            workspace_write_records,
        )
        output_paths["workspace_browser_provider_smoke"] = str(browser_provider_smoke_path)
    runtime_artifacts = export_bundle.get("artifacts", []) if isinstance(export_bundle, dict) else []
    backend_artifact_manifest = _build_backend_artifact_manifest(capabilities, output_paths, extra_artifacts=runtime_artifacts)
    manifest_path = _write_workspace_json(base_dir, "workspace_backend_artifact_manifest", backend_artifact_manifest.model_dump(mode="json"), workspace_resolver, workspace_write_records)

    artifact_index = {
        "workspace": {
            "task_card": str(task_card_path),
            "route_decision": str(route_path),
            "recon_result": str(recon_path),
            "final_result": str(final_workspace_path),
            "workspace_contract": str(workspace_contract_path),
        },
        "reports": {
            "json": str(report_json_path),
            "markdown": str(report_md_path),
        },
        "runtime_exports": export_bundle,
        "workspace_artifacts": workspace_artifact_paths,
        "evidence_promotion": evidence_promotion.model_dump(mode="json"),
        "evidence_artifacts": evidence_artifact_paths,
        "review_gate": review_gate.model_dump(mode="json"),
        "review_gate_artifact": str(review_gate_path),
        "rebuild_artifacts": rebuild_artifact_paths,
        "backend_artifact_manifest": str(manifest_path),
        "rebuild_result": rebuild_result.model_dump(mode="json"),
    }
    if enable_workspace_dual_write:
        dual_write_plan = _workspace_dual_write_plan_payload(workspace_write_records, dual_write_artifact_keys=workspace_dual_write_artifact_keys)
        dual_write_plan_path = _write_workspace_json(base_dir, "workspace_dual_write_plan", dual_write_plan, workspace_resolver, workspace_write_records)
        artifact_index["workspace"]["dual_write_plan"] = str(dual_write_plan_path)
        artifact_index["workspace_dual_write"] = dual_write_plan
    if browser_provider_smoke_path is not None:
        artifact_index["workspace"]["browser_provider_smoke"] = str(browser_provider_smoke_path)
        artifact_index["browser_provider_smoke"] = browser_provider_smoke_attachment
        artifact_index["browser_provider_smoke_acceptance"] = browser_provider_smoke_acceptance
    _write_json(index_path, artifact_index)
    return output_paths





def build_platform_markdown_report(final_result: FinalResult, capabilities: RuntimeBackendCapabilities) -> str:
    """Build a human-readable Markdown report for the platform-neutral pipeline."""

    findings = final_result.key_findings
    lines = [
        "# Reverse DeepAgent Platform Pipeline Report",
        "",
        "## Runtime",
        f"- backend_id: {capabilities.backend_id}",
        f"- display_name: {capabilities.display_name}",
        f"- transport: {capabilities.transport}",
        f"- target_platforms: {', '.join(capabilities.target_platforms) or '(unknown)'}",
        f"- supports_browser_session: {capabilities.supports_browser_session}",
        f"- supports_web_recon: {capabilities.supports_web_recon}",
        f"- supports_artifact_export: {capabilities.supports_artifact_export}",
        "",
        "## Task Card",
        f"- target_url_or_file: {final_result.task_card.target_url_or_file}",
        f"- target_param_or_api: {final_result.task_card.target_param_or_api}",
        f"- goal: {final_result.task_card.goal}",
        f"- boundaries: {final_result.task_card.boundaries}",
        f"- sample_request: {final_result.task_card.sample_request or ''}",
        f"- protection_hints: {', '.join(final_result.task_card.protection_hints)}",
        "",
        "## Result",
        f"- mode: {final_result.mode.value}",
        f"- stage: {final_result.stage.value}",
        f"- status: {final_result.status.value}",
        f"- confidence: {final_result.confidence.value}",
        f"- next_action: {final_result.next_action}",
        "",
        "## Facts",
    ]
    lines.extend([f"- {item}" for item in findings.facts] or ["- (none)"])
    lines.extend(["", "## Inferences"])
    lines.extend([f"- {item}" for item in findings.inferences] or ["- (none)"])
    lines.extend(["", "## Unknowns"])
    lines.extend([f"- {item}" for item in findings.unknowns] or ["- (none)"])
    return "\n".join(lines) + "\n"


def run_platform_pipeline(
    task_text: str,
    artifact_root: Path,
    runtime_kind: str = "android-adb",
    runtime: ReverseRuntime | None = None,
    enable_workspace_dual_write: bool = False,
    **runtime_kwargs: Any,
) -> PlatformPipelineOutput:
    """Run a platform-neutral runtime pipeline without assuming browser/Web recon semantics.

    The pipeline performs task normalization, route selection, capability capture,
    runtime artifact export, and standard artifact persistence for any
    :class:`ReverseRuntime`. It intentionally does not call Web-only methods such
    as ``ensure_browser_session`` or ``run_web_recon``.
    """

    task_card = normalize_task_card(task_text)
    route_result = route_from_task_card(task_card, task_text=task_text)
    active_runtime = runtime or build_runtime(runtime_kind, **runtime_kwargs)
    capabilities = active_runtime.describe_capabilities()
    export_bundle = active_runtime.export_reverse_artifacts(final_result=None)
    final_result = _final_from_runtime_export(task_card, route_result, capabilities, export_bundle)
    export_bundle = export_bundle.model_copy(update={"final_result": final_result})
    paths = write_platform_outputs(
        artifact_root,
        task_card,
        route_result,
        final_result,
        capabilities,
        export_bundle,
        enable_workspace_dual_write=enable_workspace_dual_write,
    )
    return PlatformPipelineOutput(
        final_result=final_result,
        artifacts=paths,
        runtime_capabilities=capabilities,
        runtime_export_bundle=export_bundle,
    )


def write_platform_outputs(
    base_dir: Path,
    task_card: TaskCard,
    route_result: RouterResult,
    final_result: FinalResult,
    runtime_capabilities: RuntimeBackendCapabilities,
    export_bundle: RuntimeExportBundle,
    enable_workspace_dual_write: bool = False,
) -> dict[str, str]:
    """Persist the platform-neutral workspace/report/export artifact set."""

    workspace_dir = base_dir / "workspace"
    reports_dir = base_dir / "reports"
    exports_dir = base_dir / "exports"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    workspace_resolver = WorkspacePathResolver(enable_dual_write=enable_workspace_dual_write)
    workspace_write_records: list[dict[str, Any]] = []
    report_json_path = reports_dir / "platform-pipeline-result.json"
    report_md_path = reports_dir / "platform-pipeline-report.md"
    index_path = exports_dir / "artifact-index.json"

    export_payload = export_bundle.model_dump(mode="json")
    task_card_path = _write_workspace_json(base_dir, "workspace_task_card", task_card.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    route_path = _write_workspace_json(base_dir, "workspace_route", route_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    capabilities_path = _write_workspace_json(base_dir, "workspace_runtime_capabilities", runtime_capabilities.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    export_bundle_path = _write_workspace_json(base_dir, "workspace_runtime_export_bundle", export_payload, workspace_resolver, workspace_write_records)
    final_workspace_path = _write_workspace_json(base_dir, "workspace_final", final_result.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    workspace_contract_path = _write_workspace_json(base_dir, "workspace_workspace_contract", workspace_contract_payload(), workspace_resolver, workspace_write_records)
    evidence_promotion = promote_evidence(final_result.evidence, final_result.artifacts)
    evidence_artifact_paths = _write_evidence_promotion_artifacts(base_dir, workspace_dir, evidence_promotion, workspace_resolver, workspace_write_records)
    _write_json(report_json_path, final_result.model_dump(mode="json"))
    report_md_path.write_text(build_platform_markdown_report(final_result, runtime_capabilities), encoding="utf-8")

    output_paths = {
        "workspace_task_card": str(task_card_path),
        "workspace_route": str(route_path),
        "workspace_runtime_capabilities": str(capabilities_path),
        "workspace_runtime_export_bundle": str(export_bundle_path),
        "workspace_final": str(final_workspace_path),
        "workspace_workspace_contract": str(workspace_contract_path),
        "json": str(report_json_path),
        "markdown": str(report_md_path),
        "index": str(index_path),
    }
    output_paths.update({f"workspace_{key}": value for key, value in evidence_artifact_paths.items()})
    platform_probe_path = _write_platform_tool_probe_if_present(base_dir, workspace_dir, export_bundle, workspace_resolver, workspace_write_records)
    if platform_probe_path is not None:
        output_paths["workspace_platform_tool_probe"] = str(platform_probe_path)
    if enable_workspace_dual_write:
        output_paths["workspace_dual_write_plan"] = str(base_dir / "workspace" / "workspace-dual-write-plan.json")
    manifest_path = base_dir / "workspace" / "backend-artifact-manifest.json"
    output_paths["workspace_backend_artifact_manifest"] = str(manifest_path)

    manifest = _build_backend_artifact_manifest(
        runtime_capabilities,
        output_paths,
        extra_artifacts=export_payload.get("artifacts", []),
    )
    manifest_path = _write_workspace_json(base_dir, "workspace_backend_artifact_manifest", manifest.model_dump(mode="json"), workspace_resolver, workspace_write_records)
    artifact_index = {
        "workspace": {
            "task_card": str(task_card_path),
            "route_decision": str(route_path),
            "runtime_capabilities": str(capabilities_path),
            "runtime_export_bundle": str(export_bundle_path),
            "final_result": str(final_workspace_path),
            "workspace_contract": str(workspace_contract_path),
            "platform_tool_probe": str(platform_probe_path) if platform_probe_path is not None else None,
        },
        "reports": {
            "json": str(report_json_path),
            "markdown": str(report_md_path),
        },
        "runtime_exports": export_payload,
        "evidence_promotion": evidence_promotion.model_dump(mode="json"),
        "evidence_artifacts": evidence_artifact_paths,
        "backend_artifact_manifest": str(manifest_path),
    }
    if enable_workspace_dual_write:
        dual_write_plan = _workspace_dual_write_plan_payload(workspace_write_records, dual_write_artifact_keys=workspace_dual_write_artifact_keys)
        dual_write_plan_path = _write_workspace_json(base_dir, "workspace_dual_write_plan", dual_write_plan, workspace_resolver, workspace_write_records)
        artifact_index["workspace"]["dual_write_plan"] = str(dual_write_plan_path)
        artifact_index["workspace_dual_write"] = dual_write_plan
    _write_json(index_path, artifact_index)
    return output_paths


def _write_platform_tool_probe_if_present(
    base_dir: Path,
    workspace_dir: Path,
    export_bundle: RuntimeExportBundle,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path | None:
    for item in export_bundle.exports:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "platform_tool_probe":
            continue
        return _write_workspace_json(base_dir, "workspace_platform_tool_probe", item.get("payload", {}), resolver, write_records)
    return None



def _artifact_refs_from_runtime_export(export_bundle: RuntimeExportBundle) -> list[ArtifactRef]:
    artifact_refs: list[ArtifactRef] = []
    for artifact in export_bundle.artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        if not path:
            continue
        artifact_refs.append(
            ArtifactRef(
                path=str(path),
                kind=artifact.get("kind") or ArtifactKind.OTHER,
                description=artifact.get("description"),
                metadata=artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {},
            )
        )
    return artifact_refs

def _final_from_runtime_export(
    task_card: TaskCard,
    route_result: RouterResult,
    capabilities: RuntimeBackendCapabilities,
    export_bundle: RuntimeExportBundle,
) -> FinalResult:
    probe = _platform_tool_probe_from_export(export_bundle)
    artifacts = _artifact_refs_from_runtime_export(export_bundle)
    export_count = len(export_bundle.exports)
    artifact_count = len(export_bundle.artifacts)
    facts = [
        f"Runtime backend '{capabilities.backend_id}' uses transport '{capabilities.transport}'.",
        f"Target platforms: {', '.join(capabilities.target_platforms) or 'unknown'}.",
        f"Runtime export emitted {export_count} export payload(s) and {artifact_count} artifact reference(s).",
    ]
    evidence_details: dict[str, Any] = {
        "capabilities": capabilities.model_dump(mode="json"),
        "export_count": export_count,
        "artifact_count": artifact_count,
    }
    status = ExecutionStatus.SUCCESS if artifact_count or export_count else ExecutionStatus.PARTIAL
    confidence = ConfidenceLevel.MEDIUM
    next_action = "inspect_runtime_export_bundle"
    unknowns: list[str] = []
    inferences = [
        "The platform-neutral pipeline completed without invoking Web-only browser recon methods.",
    ]
    if probe is not None:
        available = bool(probe.get("available"))
        facts.append(f"Platform toolchain available: {available}.")
        evidence_details["platform_tool_probe"] = probe
        if available:
            next_action = "continue_with_platform_specific_recon_or_hooking"
            confidence = ConfidenceLevel.MEDIUM
        else:
            status = ExecutionStatus.PARTIAL
            next_action = "install_or_configure_platform_tooling"
            confidence = ConfidenceLevel.LOW
            unknowns.append("Runtime-specific recon/hooking cannot proceed until the local platform toolchain is available.")
    elif not capabilities.supports_artifact_export and not (artifact_count or export_count):
        status = ExecutionStatus.PARTIAL
        confidence = ConfidenceLevel.LOW
        unknowns.append("Runtime does not advertise artifact export support; only capability metadata was captured.")

    evidence = [
        EvidenceItem(
            summary=f"Captured capability metadata for runtime backend {capabilities.backend_id}.",
            kind=EvidenceKind.NOTE,
            source="runtime_capabilities",
            anchor=capabilities.backend_id,
            details=capabilities.model_dump(mode="json"),
            confidence=ConfidenceLevel.HIGH,
        ),
        EvidenceItem(
            summary=f"Captured runtime export bundle with {export_count} export payload(s).",
            kind=EvidenceKind.OTHER,
            source="runtime_export_bundle",
            anchor=capabilities.backend_id,
            details=evidence_details,
            confidence=confidence,
        ),
    ]
    if probe is not None:
        evidence.append(
            EvidenceItem(
                summary="Captured side-effect-light platform toolchain probe.",
                kind=EvidenceKind.DYNAMIC,
                source="platform_tool_probe",
                anchor=capabilities.backend_id,
                details=probe,
                confidence=ConfidenceLevel.MEDIUM if probe.get("available") else ConfidenceLevel.LOW,
            )
        )
    return FinalResult(
        task_card=task_card,
        mode=route_result.selected_mode,
        stage=ReverseStage.CONTEXT,
        status=status,
        key_findings=KeyFindings(facts=facts, inferences=inferences, unknowns=unknowns),
        evidence=evidence,
        artifacts=artifacts,
        next_action=next_action,
        confidence=confidence,
    )


def _platform_tool_probe_from_export(export_bundle: RuntimeExportBundle) -> dict[str, Any] | None:
    for item in export_bundle.exports:
        if not isinstance(item, dict):
            continue
        if item.get("tool") == "platform_tool_probe" and isinstance(item.get("payload"), dict):
            return item["payload"]
    return None

def run_reverse_pipeline(
    task_text: str,
    artifact_root: Path,
    runtime_kind: str = "mock",
    chrome_config: ChromeDebugConfig | None = None,
    ensure_chrome: bool = False,
    keep_chrome: bool = False,
    mcp_command: str | None = None,
    runtime: WebReverseRuntime | None = None,
    browser_provider_smoke: dict[str, Any] | None = None,
    enable_workspace_dual_write: bool = False,
    workspace_dual_write_artifact_keys: set[str] | None = None,    **runtime_kwargs: Any,
) -> ReversePipelineOutput:
    """Run the deterministic reverse coordinator pipeline.

    This function is the stable package-level orchestration entry for scripts,
    tests, and future deepagents wrappers. It performs task normalization,
    routing, Web recon, final result assembly, runtime artifact export, and
    standard output persistence.
    """

    task_card = normalize_task_card(task_text)
    route_result = route_from_task_card(task_card, task_text=task_text)
    chrome_launch = None
    chrome_stop = None
    should_stop_chrome = False
    owns_runtime = runtime is None
    active_runtime = runtime or build_runtime(
        runtime_kind,
        browser_url=chrome_config.browser_url if chrome_config else None,
        mcp_command=mcp_command,
        **runtime_kwargs,
    )
    try:
        if not isinstance(active_runtime, WebReverseRuntime):
            capabilities = active_runtime.describe_capabilities()
            raise TypeError(
                f"Runtime backend {capabilities.backend_id!r} does not implement WebReverseRuntime; "
                "run_reverse_pipeline is the Web pipeline entrypoint."
            )
        runtime_capabilities = active_runtime.describe_capabilities()

        if _is_legacy_mcp_runtime_kind(runtime_kind) and ensure_chrome:
            chrome_launch = ensure_chrome_debug(chrome_config)
            if not chrome_launch.ok:
                raise RuntimeError(f"Failed to ensure Chrome debug session: {chrome_launch.stderr or chrome_launch.stdout}")
            should_stop_chrome = not keep_chrome

        recon_result = active_runtime.run_web_recon(task_card=task_card, route_result=route_result)
        final_result = _final_from_recon(task_card, route_result, recon_result)
        export_bundle = active_runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")
    finally:
        if owns_runtime:
            close = getattr(active_runtime, "close", None)
            if callable(close):
                close()
        if should_stop_chrome:
            chrome_stop = stop_chrome_debug(chrome_config)

    paths = write_outputs(
        artifact_root,
        task_card,
        route_result,
        recon_result,
        final_result,
        export_bundle,
        runtime_capabilities=runtime_capabilities,
        enable_workspace_dual_write=enable_workspace_dual_write,
        workspace_dual_write_artifact_keys=workspace_dual_write_artifact_keys,        browser_provider_smoke=browser_provider_smoke,
    )
    return ReversePipelineOutput(
        final_result=final_result,
        artifacts=paths,
        chrome_launch=chrome_launch,
        chrome_stop=chrome_stop,
    )


def _is_legacy_mcp_runtime_kind(runtime_kind: str) -> bool:
    return is_legacy_mcp_runtime_kind(runtime_kind)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_workspace_json(
    base_dir: Path,
    artifact_key: str,
    payload: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path:
    resolution = resolver.resolve_artifact_key(artifact_key)
    if resolution is None:
        fallback_path = base_dir / "workspace" / f"{artifact_key.removeprefix('workspace_').replace('_', '-')}.json"
        _write_json(fallback_path, payload)
        return fallback_path

    canonical_path = base_dir / resolution.legacy_path
    written_paths: list[str] = []
    for write_path in resolution.write_paths:
        target_path = _workspace_filesystem_path(base_dir, write_path)
        _write_json(target_path, payload)
        written_paths.append(str(target_path))
    write_records.append(
        {
            "artifact_key": artifact_key,
            "canonical_path": str(canonical_path),
            "future_path": str(_workspace_filesystem_path(base_dir, resolution.future_path)),
            "virtual_uri": resolution.virtual_uri,
            "write_paths": written_paths,
            "dual_write_enabled": resolution.dual_write_enabled,
            "dual_write_scope_enabled": resolution.dual_write_scope_enabled,
            "dual_write_in_scope": resolution.dual_write_in_scope,
            "physical_migration_enabled": resolution.physical_migration_enabled,
            "canonical_path_remains_authoritative": resolution.canonical_path_remains_authoritative,
            "migration_status": resolution.migration_status,
        }
    )
    return canonical_path


def _workspace_filesystem_path(base_dir: Path, workspace_path: str) -> Path:
    if workspace_path.startswith("virtual://workspace/"):
        return base_dir / workspace_path.removeprefix("virtual://")
    if workspace_path.startswith("/workspace/"):
        return base_dir / workspace_path.lstrip("/")
    if workspace_path.startswith("workspace/"):
        return base_dir / workspace_path
    return base_dir / "workspace" / workspace_path


def _workspace_dual_write_plan_payload(write_records: list[dict[str, Any]], dual_write_artifact_keys: set[str] | None = None) -> dict[str, Any]:
    dual_written = [record for record in write_records if record.get("dual_write_enabled")]
    out_of_scope = [record for record in write_records if not record.get("dual_write_in_scope", True)]
    scoped = dual_write_artifact_keys is not None
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-plan.v1",
        "status": "applied" if dual_written else "not-enabled",
        "mode": "scoped-opt-in-dual-write" if scoped else "opt-in-dual-write",
        "dual_write_scope_enabled": scoped,
        "dual_write_scope_artifact_keys": sorted(dual_write_artifact_keys) if scoped else None,
        "canonical_path_remains_authoritative": True,
        "physical_migration_enabled": False,
        "record_count": len(write_records),
        "dual_written_count": len(dual_written),
        "out_of_scope_record_count": len(out_of_scope),
        "records": write_records,
    }


def _workspace_artifact_key_from_filename(filename: str) -> str:
    return f"workspace_{filename.removesuffix('.json').replace('-', '_').replace('.', '_')}"


def _write_evidence_promotion_artifacts(
    base_dir: Path,
    workspace_dir: Path,
    evidence_promotion: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> dict[str, str]:
    paths: dict[str, str] = {}
    for filename, payload in promotion_workspace_payloads(evidence_promotion).items():
        artifact_key = _workspace_artifact_key_from_filename(filename)
        path = _write_workspace_json(base_dir, artifact_key, payload, resolver, write_records)
        paths[filename.removesuffix(".json").replace("-", "_")] = str(path)
    return paths


def _write_review_gate_artifact(
    base_dir: Path,
    workspace_dir: Path,
    review_gate: Any,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> Path:
    return _write_workspace_json(base_dir, "workspace_review_gate", review_gate_workspace_payload(review_gate), resolver, write_records)


def _write_workspace_artifacts(
    base_dir: Path,
    workspace_dir: Path,
    final_result: FinalResult,
    resolver: WorkspacePathResolver,
    write_records: list[dict[str, Any]],
) -> dict[str, str]:
    payloads = _extract_workspace_artifact_payloads(final_result)
    paths: dict[str, str] = {}
    for filename, payload in payloads.items():
        artifact_key = _workspace_artifact_key_from_filename(filename)
        path = _write_workspace_json(base_dir, artifact_key, payload, resolver, write_records)
        paths[filename.removesuffix(".json").replace("-", "_")] = str(path)
    return paths


def _rebuild_paths_from_result(rebuild_result: Any) -> dict[str, str]:
    paths: dict[str, str] = {}
    generated_files = getattr(rebuild_result, "generated_files", None) or {}
    for key, value in generated_files.items():
        paths[key] = value
    return paths


def _extract_workspace_artifact_payloads(final_result: FinalResult) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for evidence in final_result.evidence:
        if evidence.source == "network_request":
            payloads["network-requests.json"] = evidence.details
        elif evidence.source == "search_in_sources":
            payloads["source-hits.json"] = evidence.details
        elif evidence.source == "get_request_initiator":
            payloads["request-initiators.json"] = evidence.details
        elif evidence.source == "get_script_source":
            payloads["source-contexts.json"] = evidence.details
        elif evidence.source == "response_body_metadata":
            payloads["response-bodies.json"] = evidence.details
        elif evidence.source == "websocket_frame_metadata":
            payloads["websocket-frames.json"] = evidence.details
        elif evidence.source == "runtime_hook_timeline":
            payloads["hook-timeline.json"] = evidence.details
        elif evidence.source == "flow_timeline":
            payloads["flow-timeline.json"] = evidence.details
        elif evidence.source == "stitched_flow":
            payloads["stitched-flow.json"] = evidence.details
        elif evidence.source == "function_hooks":
            payloads["function-hooks.json"] = evidence.details
        elif evidence.source == "function_hook_timeline":
            payloads["function-hook-timeline.json"] = evidence.details
        elif evidence.source == "source_logpoints":
            payloads["source-logpoints.json"] = evidence.details
        elif evidence.source == "source_logpoint_timeline":
            payloads["source-logpoint-timeline.json"] = evidence.details
        elif evidence.source == "breakpoint_manager":
            payloads["breakpoints.json"] = evidence.details
        elif evidence.source == "async_chunk_load_plan":
            payloads["async-chunk-load-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_load_result":
            payloads["async-chunk-load-result.json"] = evidence.details
        elif evidence.source == "async_chunk_module_diff":
            payloads["async-chunk-module-diff.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_execution":
            payloads["async-chunk-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_followup":
            payloads["async-chunk-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "async_chunk_recursive_traversal_plan":
            payloads["async-chunk-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_graph":
            payloads["async-chunk-traversal-graph.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_loop_execution":
            payloads["async-chunk-traversal-loop-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_loop_plan":
            payloads["async-chunk-traversal-loop-plan.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_workflow_execution":
            payloads["async-chunk-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "async_chunk_traversal_workflow_plan":
            payloads["async-chunk-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "bundler_symbol_scope":
            payloads["bundler-symbol-scope.json"] = evidence.details
        elif evidence.source == "closure_function_candidates":
            payloads["closure-function-candidates.json"] = evidence.details
        elif evidence.source == "closure_functions":
            payloads["closure-functions.json"] = evidence.details
        elif evidence.source == "closure_wrapper_assignment_safety":
            payloads["closure-wrapper-assignment-safety.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_checkpoint":
            payloads["closure-wrapper-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_execution":
            payloads["closure-wrapper-continuation-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_execution_plan":
            payloads["closure-wrapper-continuation-execution-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_next_iteration_execution":
            payloads["closure-wrapper-continuation-next-iteration-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_next_iteration_plan":
            payloads["closure-wrapper-continuation-next-iteration-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_continuation_readiness":
            payloads["closure-wrapper-continuation-readiness.json"] = evidence.details
        elif evidence.source == "closure_wrapper_events":
            payloads["closure-wrapper-events.json"] = evidence.details
        elif evidence.source == "closure_wrapper_replacement_execution":
            payloads["closure-wrapper-replacement-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_replacement_plan":
            payloads["closure-wrapper-replacement-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_restore_execution":
            payloads["closure-wrapper-restore-execution.json"] = evidence.details
        elif evidence.source == "closure_wrapper_restore_plan":
            payloads["closure-wrapper-restore-plan.json"] = evidence.details
        elif evidence.source == "closure_wrapper_runtime_mutability_preflight":
            payloads["closure-wrapper-runtime-mutability-preflight.json"] = evidence.details
        elif evidence.source == "closure_wrapper_runtime_mutability_result":
            payloads["closure-wrapper-runtime-mutability-result.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_execution":
            payloads["custom-loader-continuation-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_journal":
            payloads["custom-loader-continuation-journal.json"] = evidence.details
        elif evidence.source == "custom_loader_continuation_workflow":
            payloads["custom-loader-continuation-workflow.json"] = evidence.details
        elif evidence.source == "custom_loader_execution_preflight":
            payloads["custom-loader-execution-preflight.json"] = evidence.details
        elif evidence.source == "custom_loader_execution_result":
            payloads["custom-loader-execution-result.json"] = evidence.details
        elif evidence.source == "custom_loader_module_diff":
            payloads["custom-loader-module-diff.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_execution":
            payloads["custom-loader-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_followup":
            payloads["custom-loader-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "custom_loader_recursive_traversal_plan":
            payloads["custom-loader-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_graph":
            payloads["custom-loader-traversal-graph.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_loop_execution":
            payloads["custom-loader-traversal-loop-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_loop_plan":
            payloads["custom-loader-traversal-loop-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_plan":
            payloads["custom-loader-traversal-plan.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_workflow_execution":
            payloads["custom-loader-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "custom_loader_traversal_workflow_plan":
            payloads["custom-loader-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_automatic_followup_plan":
            payloads["heap-snapshot-automatic-followup-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_collect":
            payloads["heap-snapshot-collect.json"] = evidence.details
        elif evidence.source == "heap_snapshot_constructor_growth_drilldown":
            payloads["heap-snapshot-constructor-growth-drilldown.json"] = evidence.details
        elif evidence.source == "heap_snapshot_constructor_growth_drilldown_analysis":
            payloads["heap-snapshot-constructor-growth-drilldown-analysis.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_approval_plan":
            payloads["heap-snapshot-diff-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_approval_record":
            payloads["heap-snapshot-diff-executor-approval-record.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_bounded_gate":
            payloads["heap-snapshot-diff-executor-bounded-gate.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_preflight":
            payloads["heap-snapshot-diff-executor-preflight.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_result":
            payloads["heap-snapshot-diff-executor-result.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_transaction_journal":
            payloads["heap-snapshot-diff-executor-journal.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_executor_transaction_preflight":
            payloads["heap-snapshot-diff-executor-transaction-preflight.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_followup_checkpoint":
            payloads["heap-snapshot-diff-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_readiness":
            payloads["heap-snapshot-diff-readiness.json"] = evidence.details
        elif evidence.source == "heap_snapshot_diff_selected_analysis_input_preflight":
            payloads["heap-snapshot-diff-selected-analysis-input-preflight.json"] = evidence.details
        elif evidence.source == "heap_snapshot_path_to_root_analysis":
            payloads["heap-snapshot-path-to-root-analysis.json"] = evidence.details
        elif evidence.source == "heap_snapshot_path_to_root_proof_plan":
            payloads["heap-snapshot-path-to-root-proof-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_raw_heap_constructor_drilldown_proof_plan":
            payloads["heap-snapshot-raw-heap-constructor-drilldown-proof-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_readiness":
            payloads["heap-snapshot-readiness.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_path_preflight":
            payloads["heap-snapshot-retained-path-preflight.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_analysis":
            payloads["heap-snapshot-retained-size-analysis.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_approval_plan":
            payloads["heap-snapshot-retained-size-approval-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_approval_record":
            payloads["heap-snapshot-retained-size-approval-record.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_bounded_gate":
            payloads["heap-snapshot-retained-size-bounded-gate.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_input_review":
            payloads["heap-snapshot-retained-size-input-review.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_proof_plan":
            payloads["heap-snapshot-retained-size-proof-plan.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_transaction_journal":
            payloads["heap-snapshot-retained-size-executor-journal.json"] = evidence.details
        elif evidence.source == "heap_snapshot_retained_size_transaction_preflight":
            payloads["heap-snapshot-retained-size-transaction-preflight.json"] = evidence.details
        elif evidence.source == "module_federation_export_hook_plan":
            payloads["module-federation-export-hook-plan.json"] = evidence.details
        elif evidence.source == "module_federation_factory_invoke_result":
            payloads["module-federation-factory-invoke-result.json"] = evidence.details
        elif evidence.source == "module_federation_get_init_plan":
            payloads["module-federation-get-init-plan.json"] = evidence.details
        elif evidence.source == "module_federation_get_init_result":
            payloads["module-federation-get-init-result.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_continuation_checkpoint":
            payloads["module-federation-recursive-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_continuation_journal":
            payloads["module-federation-recursive-continuation-journal.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_execution":
            payloads["module-federation-recursive-traversal-execution.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_followup":
            payloads["module-federation-recursive-traversal-followup.json"] = evidence.details
        elif evidence.source == "module_federation_recursive_traversal_plan":
            payloads["module-federation-recursive-traversal-plan.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_graph":
            payloads["module-federation-traversal-graph.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_workflow_execution":
            payloads["module-federation-traversal-workflow-execution.json"] = evidence.details
        elif evidence.source == "module_federation_traversal_workflow_plan":
            payloads["module-federation-traversal-workflow-plan.json"] = evidence.details
        elif evidence.source == "object_graph_diff":
            payloads["object-graph-diff.json"] = evidence.details
        elif evidence.source == "object_root_mutation_audit":
            payloads["object-root-mutation-audit.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_bounded_executor_gate":
            payloads["paused-session-automatic-loop-bounded-executor-gate.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_execution_plan":
            payloads["paused-session-automatic-loop-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_execution_result":
            payloads["paused-session-automatic-loop-execution-result.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_approval_plan":
            payloads["paused-session-automatic-loop-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_approval_record":
            payloads["paused-session-automatic-loop-executor-approval-record.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_journal":
            payloads["paused-session-automatic-loop-executor-journal.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_executor_preflight":
            payloads["paused-session-automatic-loop-executor-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_following_iteration_plan":
            payloads["paused-session-automatic-loop-following-iteration-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_followup_checkpoint":
            payloads["paused-session-automatic-loop-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_bounded_executor_gate":
            payloads["paused-session-automatic-loop-multi-iteration-bounded-executor-gate.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_execution_plan":
            payloads["paused-session-automatic-loop-multi-iteration-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_execution_result":
            payloads["paused-session-automatic-loop-multi-iteration-execution-result.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_approval_plan":
            payloads["paused-session-automatic-loop-multi-iteration-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_approval_record":
            payloads["paused-session-automatic-loop-multi-iteration-executor-approval-record.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_input_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-executor-input-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_executor_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-executor-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_followup_checkpoint":
            payloads["paused-session-automatic-loop-multi-iteration-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_next_step_plan":
            payloads["paused-session-automatic-loop-multi-iteration-next-step-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_policy":
            payloads["paused-session-automatic-loop-multi-iteration-policy.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_transaction_journal":
            payloads["paused-session-automatic-loop-multi-iteration-executor-journal.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_multi_iteration_transaction_preflight":
            payloads["paused-session-automatic-loop-multi-iteration-transaction-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_execution":
            payloads["paused-session-automatic-loop-next-iteration-execution.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_followup_checkpoint":
            payloads["paused-session-automatic-loop-next-iteration-followup-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_next_iteration_plan":
            payloads["paused-session-automatic-loop-next-iteration-plan.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_readiness":
            payloads["paused-session-automatic-loop-readiness.json"] = evidence.details
        elif evidence.source == "paused_session_automatic_loop_transaction_preflight":
            payloads["paused-session-automatic-loop-transaction-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_attach_probe":
            payloads["paused-session-cross-process-attach-probe.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_continuation_checkpoint":
            payloads["paused-session-cross-process-continuation-checkpoint.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_execution_plan":
            payloads["paused-session-cross-process-execution-plan.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_one_action_execution":
            payloads["paused-session-cross-process-one-action-execution.json"] = evidence.details
        elif evidence.source == "paused_session_cross_process_session_lifecycle":
            payloads["paused-session-cross-process-session-lifecycle.json"] = evidence.details
        elif evidence.source == "paused_session_live_callframe_recovery":
            payloads["paused-session-live-callframe-recovery.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_continuation_execution":
            payloads["paused-session-multi-step-continuation-execution.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_continuation_workflow":
            payloads["paused-session-multi-step-continuation-workflow.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_loop_execution":
            payloads["paused-session-multi-step-loop-execution.json"] = evidence.details
        elif evidence.source == "paused_session_multi_step_loop_plan":
            payloads["paused-session-multi-step-loop-plan.json"] = evidence.details
        elif evidence.source == "paused_session_next_paused_event_capture_execution":
            payloads["paused-session-next-paused-event-capture-execution.json"] = evidence.details
        elif evidence.source == "paused_session_next_paused_event_capture_plan":
            payloads["paused-session-next-paused-event-capture-plan.json"] = evidence.details
        elif evidence.source == "paused_session_pre_action_subscribe_and_action":
            payloads["paused-session-pre-action-subscribe-and-action.json"] = evidence.details
        elif evidence.source == "paused_session_target_attach_readiness":
            payloads["paused-session-target-attach-readiness.json"] = evidence.details
        elif evidence.source == "recursive_continuation_readiness":
            payloads["recursive-continuation-readiness.json"] = evidence.details
        elif evidence.source == "runtime_object_graph_diff":
            payloads["runtime-object-graph-diff.json"] = evidence.details
        elif evidence.source == "source_map_consumer_action_plan":
            payloads["source-map-consumer-action-plan.json"] = evidence.details
        elif evidence.source == "source_map_consumer_materialization":
            payloads["source-map-consumer-materialization.json"] = evidence.details
        elif evidence.source == "source_map_debugger_candidate_selection":
            payloads["source-map-debugger-candidate-selection.json"] = evidence.details
        elif evidence.source == "source_map_debugger_candidates":
            payloads["source-map-debugger-candidates.json"] = evidence.details
        elif evidence.source == "source_map_debugger_execution_result":
            payloads["source-map-debugger-execution-result.json"] = evidence.details
        elif evidence.source == "source_map_fetch_plan":
            payloads["source-map-fetch-plan.json"] = evidence.details
        elif evidence.source == "source_map_fetch_result":
            payloads["source-map-fetch-result.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_chain_readiness":
            payloads["source-map-followthrough-chain-readiness.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_completion_checkpoint":
            payloads["source-map-followthrough-completion-checkpoint.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_approval_plan":
            payloads["source-map-followthrough-dispatch-approval-plan.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_approval_record":
            payloads["source-map-followthrough-dispatch-approval-record.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_bounded_executor_gate":
            payloads["source-map-followthrough-dispatch-bounded-executor-gate.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_preflight":
            payloads["source-map-followthrough-dispatch-preflight.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_transaction_journal":
            payloads["source-map-followthrough-dispatch-transaction-journal.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatch_transaction_preflight":
            payloads["source-map-followthrough-dispatch-transaction-preflight.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatcher_apply_preflight":
            payloads["source-map-followthrough-dispatcher-apply-preflight.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatcher_handoff":
            payloads["source-map-followthrough-dispatcher-handoff.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_dispatcher_result":
            payloads["source-map-followthrough-dispatcher-result.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_one_step_plan":
            payloads["source-map-followthrough-one-step-plan.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_review":
            payloads["source-map-followthrough-review.json"] = evidence.details
        elif evidence.source == "source_map_followthrough_surface_selection":
            payloads["source-map-followthrough-surface-selection.json"] = evidence.details
        elif evidence.source == "source_map_hook_candidate_selection":
            payloads["source-map-hook-candidate-selection.json"] = evidence.details
        elif evidence.source == "source_map_hook_candidates":
            payloads["source-map-hook-candidates.json"] = evidence.details
        elif evidence.source == "source_map_hook_install_result":
            payloads["source-map-hook-install-result.json"] = evidence.details
        elif evidence.source == "source_map_lookup":
            payloads["source-map-lookup.json"] = evidence.details
        elif evidence.source == "source_map_readiness":
            payloads["source-map-readiness.json"] = evidence.details
        elif evidence.source == "source_map_rebuild_generation_result":
            payloads["source-map-rebuild-generation-result.json"] = evidence.details
        elif evidence.source == "source_map_rebuild_result":
            payloads["source-map-rebuild-result.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_application_handoff":
            payloads["source-map-selected-executor-application-handoff.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_apply_preflight":
            payloads["source-map-selected-executor-apply-preflight.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_approval_plan":
            payloads["source-map-selected-executor-approval-plan.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_approval_record":
            payloads["source-map-selected-executor-approval-record.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_input_review":
            payloads["source-map-selected-executor-input-review.json"] = evidence.details
        elif evidence.source == "source_map_selected_executor_result_checkpoint":
            payloads["source-map-selected-executor-result-checkpoint.json"] = evidence.details
        elif evidence.source == "source_map_source_content":
            payloads["source-map-source-content.json"] = evidence.details
        elif evidence.source == "source_map_source_logpoint_install_result":
            payloads["source-map-source-logpoint-install-result.json"] = evidence.details
        elif evidence.source == "source_map_terminal_review_closure_checkpoint":
            payloads["source-map-terminal-review-closure-checkpoint.json"] = evidence.details
        elif evidence.source == "source_map_terminal_review_final_audit":
            payloads["source-map-terminal-review-final-audit.json"] = evidence.details
        elif evidence.source == "source_map_terminal_review_package":
            payloads["source-map-terminal-review-package.json"] = evidence.details
        elif evidence.source == "source_map_typed_payload_preflight":
            payloads["source-map-typed-payload-preflight.json"] = evidence.details
        elif evidence.source == "paused_session_live_continuation_preflight":
            payloads["paused-session-live-continuation-preflight.json"] = evidence.details
        elif evidence.source == "debugger_paused":
            payloads["debugger-paused.json"] = evidence.details
        elif evidence.source == "debugger_callframes":
            payloads["callframes.json"] = evidence.details
        elif evidence.source == "debugger_callframe_evaluations":
            payloads["callframe-evaluations.json"] = evidence.details
        elif evidence.source == "debugger_actions":
            payloads["debugger-actions.json"] = evidence.details
        elif evidence.source == "debugger_session":
            payloads["debugger-session.json"] = evidence.details
        elif evidence.source == "debugger_timeline":
            payloads["debugger-timeline.json"] = evidence.details
        elif evidence.source == "runtime_context":
            payloads["runtime-context.json"] = evidence.details
        elif evidence.source == "dom_snapshot":
            payloads["dom-snapshot.json"] = evidence.details
        elif evidence.source == "script_inventory":
            payloads["script-inventory.json"] = evidence.details
        elif evidence.source == "console_message":
            payloads["console-messages.json"] = evidence.details
        elif evidence.source == "navigate_page":
            payloads["navigation-events.json"] = evidence.details
        elif evidence.source == "runtime_context_diff":
            payloads["runtime-context-diff.json"] = evidence.details
        elif evidence.source == "function_candidate_card":
            payloads["function-candidates.json"] = evidence.details
        elif evidence.source == "function_validation_result":
            payloads["function-validations.json"] = evidence.details
        elif evidence.source == "function_validation_summary":
            payloads["function-validation-summary.json"] = evidence.details
    return payloads



def _browser_provider_smoke_acceptance(smoke_payload: dict[str, Any], capabilities: RuntimeBackendCapabilities) -> dict[str, Any]:
    """Review existing BrowserProvider smoke JSON before attaching it to Web artifacts."""
    provider = capabilities.config.get("provider") if isinstance(capabilities.config, dict) else None
    expected_provider_id = str(provider.get("provider_id") or "") if isinstance(provider, dict) else ""
    return _browser_smoke_impl(smoke_payload, expected_provider_id=expected_provider_id)

def _final_from_recon(task_card: TaskCard, route_result: RouterResult, recon_result: ReconResult) -> FinalResult:
    return FinalResult(
        task_card=task_card,
        mode=route_result.selected_mode,
        stage=recon_result.stage,
        status=recon_result.status,
        key_findings=KeyFindings(
            facts=recon_result.key_findings.facts,
            inferences=recon_result.key_findings.inferences,
            unknowns=recon_result.key_findings.unknowns,
        ),
        evidence=recon_result.evidence,
        artifacts=recon_result.artifacts,
        next_action=recon_result.next_action,
        confidence=recon_result.confidence,
    )
