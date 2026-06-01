from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import FinalResult
from reverse_deepagent.workspace_contract import WorkspacePathResolution, WorkspacePathResolver


ArtifactTool = Callable[..., dict[str, Any]]


def make_export_reverse_artifacts_tool(runtime: ReverseRuntime) -> ArtifactTool:
    """Create a tool wrapper that exports runtime artifacts."""

    def export_reverse_artifacts(final_result_json: str | None = None) -> dict[str, Any]:
        final_result = FinalResult.model_validate_json(final_result_json) if final_result_json else None
        return runtime.export_reverse_artifacts(final_result=final_result).model_dump(mode="json")

    export_reverse_artifacts.__name__ = "export_reverse_artifacts"
    export_reverse_artifacts.__doc__ = "Export runtime artifacts and return a normalized export bundle."
    return export_reverse_artifacts


def make_read_workspace_artifact_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only resolver-backed workspace artifact reader tool."""

    root = Path(default_artifact_root)

    def read_workspace_artifact(
        artifact_ref: str,
        artifact_root: str | None = None,
        max_chars: int = 20000,
    ) -> dict[str, Any]:
        """Read a workspace artifact by key, legacy path, future path, or virtual URI without mutating files."""

        return read_workspace_artifact_payload(
            artifact_ref=artifact_ref,
            default_artifact_root=root,
            artifact_root=artifact_root,
            max_chars=max_chars,
        )

    read_workspace_artifact.__name__ = "read_workspace_artifact"
    read_workspace_artifact.__doc__ = (
        "Read a workspace artifact by artifact key, legacy workspace/*.json path, "
        "future /workspace/<area>/ path, virtual://workspace/... URI, or artifact-root-relative path. "
        "The tool is read-only and does not migrate or dual-write artifacts."
    )
    return read_workspace_artifact


def make_audit_workspace_artifact_consumers_tool() -> ArtifactTool:
    """Create a read-only audit tool for workspace artifact-ref adoption."""

    def audit_workspace_artifact_consumers() -> dict[str, Any]:
        """Return a static resolver-adoption matrix for workspace artifact consumers."""

        return audit_workspace_artifact_consumers_payload()

    audit_workspace_artifact_consumers.__name__ = "audit_workspace_artifact_consumers"
    audit_workspace_artifact_consumers.__doc__ = (
        "Read-only audit of tools and workflow inputs that consume workspace artifacts or filesystem paths. "
        "Classifies consumers as resolver-ready, partial, candidate, explicit-filesystem-boundary, or non-workspace input; "
        "does not inspect files, write artifacts, migrate paths, enable dual-write, start browsers, or call MCP."
    )
    return audit_workspace_artifact_consumers


def audit_workspace_artifact_consumers_payload() -> dict[str, Any]:
    """Return the current resolver adoption matrix for known workspace consumers."""

    consumers = _workspace_consumer_audit_entries()
    by_status: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    for item in consumers:
        by_status[item["resolver_status"]] = by_status.get(item["resolver_status"], 0) + 1
        by_owner[item["owner"]] = by_owner.get(item["owner"], 0) + 1
    follow_up_candidates = [
        item
        for item in consumers
        if item["resolver_status"] in {"candidate", "partial"}
        and item["next_action"] not in {"keep-explicit-filesystem-boundary", "none"}
    ]
    explicit_boundaries = [item for item in consumers if item["resolver_status"] == "explicit-filesystem-boundary"]
    return {
        "schema_version": "reverse-deepagent.workspace-consumer-audit.v1",
        "status": "review",
        "summary": {
            "consumer_count": len(consumers),
            "by_status": dict(sorted(by_status.items())),
            "by_owner": dict(sorted(by_owner.items())),
            "follow_up_candidate_count": len(follow_up_candidates),
            "explicit_filesystem_boundary_count": len(explicit_boundaries),
            "mobile_full_runtime_chains_deferred": True,
        },
        "consumers": consumers,
        "follow_up_candidates": follow_up_candidates,
        "explicit_filesystem_boundaries": explicit_boundaries,
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def read_workspace_artifact_payload(
    *,
    artifact_ref: str,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    max_chars: int = 20000,
) -> dict[str, Any]:
    """Read a workspace artifact and return the same payload as the public reader tool."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    resolver = WorkspacePathResolver()
    resolution = resolver.resolve_artifact_key(artifact_ref) or resolver.resolve_path(artifact_ref)
    candidate_paths = _candidate_paths(effective_root, artifact_ref, resolution)
    checked_paths: list[str] = []
    for candidate in candidate_paths:
        checked_paths.append(str(candidate))
        if not candidate.exists() or not candidate.is_file():
            continue
        return _read_artifact_file(
            candidate,
            artifact_ref=artifact_ref,
            artifact_root=effective_root,
            resolution=resolution,
            candidate_paths=candidate_paths,
            checked_paths=checked_paths,
            max_chars=max_chars,
        )
    resolver_metrics = _workspace_resolver_metrics(
        artifact_ref=artifact_ref,
        artifact_root=effective_root,
        resolution=resolution,
        candidate_paths=candidate_paths,
        checked_paths=checked_paths,
        hit_path=None,
        status="missing",
    )
    return {
        "status": "missing",
        "artifact_ref": artifact_ref,
        "artifact_root": str(effective_root),
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolution": resolution.to_dict() if resolution else {},
        "checked_paths": checked_paths,
        "resolver_metrics": resolver_metrics,
        "side_effect_policy": _reader_side_effect_policy(),
    }


def load_workspace_artifact_json_object(
    *,
    artifact_ref: str,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    field_name: str = "artifact_ref",
    max_chars: int = 20000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a workspace artifact and return its JSON object plus read diagnostics."""

    result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        artifact_root=artifact_root,
        max_chars=max_chars,
    )
    if result.get("status") != "found":
        raise ValueError(f"{field_name} could not be read: {result.get('status')}; checked_paths={result.get('checked_paths')}")
    if result.get("content_type") != "json":
        raise ValueError(f"{field_name} must resolve to a JSON object artifact; content_type={result.get('content_type')}")
    value = result.get("json")
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must resolve to a JSON object artifact")
    return value, result


def _workspace_consumer_audit_entries() -> list[dict[str, Any]]:
    """Return the static list of known workspace artifact / path consumers."""

    return [
        _consumer_entry(
            consumer_id="coordinator.read_workspace_artifact",
            owner="coordinator",
            tool="read_workspace_artifact",
            inputs=("artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact key, legacy path, future path, virtual URI, and artifact-root-relative fallback",
            next_action="none",
            rationale="Shared read-only resolver consumer with compatibility metrics.",
        ),
        _consumer_entry(
            consumer_id="timeline.review_flow_timeline",
            owner="timeline",
            tool="review_flow_timeline",
            inputs=("flow_timeline_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads through load_workspace_artifact_json_object.",
        ),
        _consumer_entry(
            consumer_id="hook.review_hook_artifacts",
            owner="hook",
            tool="review_hook_artifacts",
            inputs=("hook_artifacts_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads hook artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="debugger.review_debugger_artifacts",
            owner="debugger",
            tool="review_debugger_artifacts",
            inputs=("debugger_artifacts_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref input plus legacy JSON string input",
            next_action="none",
            rationale="Specialized review helper reads debugger artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="rebuild.review_rebuild_artifacts",
            owner="rebuild",
            tool="review_rebuild_artifacts",
            inputs=("rebuild_result_artifact_ref", "rebuild_plan_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref inputs plus legacy JSON string inputs",
            next_action="none",
            rationale="Read-only rebuild review accepts artifact refs for both result and plan payloads.",
        ),
        _consumer_entry(
            consumer_id="review.evaluate_delivery_review_gate",
            owner="review",
            tool="evaluate_delivery_review_gate",
            inputs=("rebuild_result_artifact_ref", "evidence_promotion_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="artifact-ref inputs plus legacy JSON string inputs",
            next_action="none",
            rationale="Review gate consumes reviewed JSON object artifacts through the shared resolver.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_local_delivery.artifacts_json",
            owner="delivery",
            tool="execute_local_delivery",
            inputs=("artifacts_json[].source_artifact_ref", "artifacts_json[].artifact_ref", "artifact_root"),
            resolver_status="partial",
            current_support="source_artifact_ref / artifact_ref are resolver-ready; source_path remains supported for explicit filesystem delivery",
            next_action="monitor-source_path-usage-before-tightening",
            rationale="Delivery artifact source normalization is resolver-ready, but source_path is intentionally retained for non-workspace files and backward compatibility.",
        ),
        _consumer_entry(
            consumer_id="rebuild.build_rebuild_delivery",
            owner="rebuild",
            tool="build_rebuild_delivery",
            inputs=("task_card_json", "final_result_json", "task_card_artifact_ref", "final_result_artifact_ref", "artifact_root"),
            resolver_status="resolver-ready",
            current_support="JSON string inputs or workspace artifact refs for task card and final result; artifact_root selects output root",
            next_action="none",
            rationale="Optional artifact refs reduce manual read-then-paste handoff without changing rebuild output writes or delivery gates.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_resume",
            owner="delivery",
            tool="execute_delivery_resume",
            inputs=("backend_manifest_path", "approval_ledger_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Resume runner validates and mutates transaction-scoped delivery state; backend manifest and approval ledger paths are apply-time safety gates.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_transition",
            owner="delivery",
            tool="execute_delivery_transition",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Transition execution can recover or commit backend manifest state and must not silently reinterpret mutation targets through workspace aliases.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_recovery",
            owner="delivery",
            tool="execute_delivery_recovery",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Recovery can restore a backend manifest from checkpoints; explicit paths keep reviewer intent and digest checks unambiguous.",
        ),
        _consumer_entry(
            consumer_id="delivery.execute_delivery_rollback",
            owner="delivery",
            tool="execute_delivery_rollback",
            inputs=("backend_manifest_path", "delivery_root"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit filesystem paths only",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Rollback preflight / apply is a physical mutation boundary and should not be hidden behind artifact alias lookup.",
        ),
        _consumer_entry(
            consumer_id="review.record_review_approval",
            owner="review",
            tool="record_review_approval",
            inputs=("review_root", "subject_id", "subject_digest_sha256"),
            resolver_status="explicit-filesystem-boundary",
            current_support="explicit review root plus logical subject identifiers",
            next_action="keep-explicit-filesystem-boundary",
            rationale="Approval recording writes append-only audit artifacts; subject refs should stay logical and review_root should stay explicit.",
        ),
        _consumer_entry(
            consumer_id="delivery.plan_delivery_resume",
            owner="delivery",
            tool="plan_delivery_resume",
            inputs=("delivery_root", "transaction_id"),
            resolver_status="non-workspace-input",
            current_support="transaction root inspection only",
            next_action="none",
            rationale="The planner inspects a delivery transaction root, not workspace artifacts.",
        ),
        _consumer_entry(
            consumer_id="delivery.manage_delivery_transaction_lock_provider",
            owner="delivery",
            tool="manage_delivery_transaction_lock_provider",
            inputs=("delivery_root", "provider_id", "transaction_id"),
            resolver_status="non-workspace-input",
            current_support="transaction lock provider root and logical lock ids",
            next_action="none",
            rationale="Lock provider operations are transaction lease boundaries, not workspace artifact consumption.",
        ),
    ]


def _consumer_entry(
    *,
    consumer_id: str,
    owner: str,
    tool: str,
    inputs: tuple[str, ...],
    resolver_status: str,
    current_support: str,
    next_action: str,
    rationale: str,
) -> dict[str, Any]:
    return {
        "consumer_id": consumer_id,
        "owner": owner,
        "tool": tool,
        "inputs": list(inputs),
        "resolver_status": resolver_status,
        "current_support": current_support,
        "next_action": next_action,
        "rationale": rationale,
    }

def summarize_workspace_artifact_read(result: dict[str, Any] | None) -> dict[str, Any]:
    """Return compact, secret-safe diagnostics for artifact-ref based tool inputs."""

    if not result:
        return {}
    return {
        "status": result.get("status"),
        "artifact_ref": result.get("artifact_ref"),
        "artifact_root": result.get("artifact_root"),
        "path": result.get("path"),
        "content_type": result.get("content_type"),
        "content_truncated": bool(result.get("content_truncated")),
        "resolution_status": result.get("resolution_status"),
        "resolution": result.get("resolution") or {},
        "checked_paths": result.get("checked_paths") or [],
        "resolver_metrics": result.get("resolver_metrics") or {},
    }


def _candidate_paths(root: Path, artifact_ref: str, resolution: WorkspacePathResolution | None) -> list[Path]:
    raw_candidates: list[str] = []
    if resolution is not None:
        raw_candidates.extend(resolution.read_paths)
        raw_candidates.extend((resolution.canonical_path, resolution.future_path, resolution.virtual_uri))
    else:
        raw_candidates.append(artifact_ref)
    paths: list[Path] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        path = _artifact_ref_to_filesystem_path(root, raw)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def _artifact_ref_to_filesystem_path(root: Path, value: str) -> Path:
    value = str(value).strip()
    if value.startswith("virtual://"):
        parsed = urlparse(value)
        netloc = parsed.netloc.strip("/")
        path = parsed.path.strip("/")
        relative = "/".join(part for part in (netloc, path) if part)
        return root / relative
    if value.startswith("/workspace/"):
        return root / value.lstrip("/")
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _artifact_ref_kind(artifact_ref: str, resolution: WorkspacePathResolution | None) -> str:
    value = str(artifact_ref).strip()
    if resolution is not None:
        if value == resolution.artifact_key:
            return "artifact-key"
        if value == resolution.legacy_path:
            return "legacy-path"
        if value == resolution.future_path or value.startswith("/workspace/"):
            return "future-path"
        if value == resolution.virtual_uri or value.startswith("virtual://"):
            return "virtual-uri"
    if value.startswith("virtual://"):
        return "virtual-uri"
    if value.startswith("/workspace/"):
        return "future-path"
    path = Path(value)
    if path.is_absolute():
        return "absolute-path"
    return "relative-path"


def _workspace_path_kind(path: Path, artifact_root: Path, resolution: WorkspacePathResolution | None) -> str:
    if resolution is None:
        return "direct-absolute" if path.is_absolute() and not _is_relative_to(path, artifact_root) else "direct-relative"
    canonical_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.canonical_path)
    future_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.future_path)
    if path == canonical_path:
        return "legacy-canonical"
    if path == future_path:
        return "future-foldered"
    if path.is_absolute() and not _is_relative_to(path, artifact_root):
        return "direct-absolute"
    return "direct-relative"


def _workspace_resolver_metrics(
    *,
    artifact_ref: str,
    artifact_root: Path,
    resolution: WorkspacePathResolution | None,
    candidate_paths: list[Path],
    checked_paths: list[str],
    hit_path: Path | None,
    status: str,
) -> dict[str, Any]:
    """Return read-only resolver compatibility diagnostics for migration planning."""

    checked_path_set = set(checked_paths)
    legacy_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.legacy_path) if resolution else None
    future_path = _artifact_ref_to_filesystem_path(artifact_root, resolution.future_path) if resolution else None
    hit_path_kind = _workspace_path_kind(hit_path, artifact_root, resolution) if hit_path is not None else None
    legacy_path_checked = str(legacy_path) in checked_path_set if legacy_path is not None else False
    future_path_checked = str(future_path) in checked_path_set if future_path is not None else False
    direct_path_fallback_used = resolution is None and hit_path is not None
    return {
        "schema_version": "reverse-deepagent.workspace-resolver-metrics.v1",
        "artifact_ref_kind": _artifact_ref_kind(artifact_ref, resolution),
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolved_artifact_key": resolution.artifact_key if resolution else "",
        "canonical_path": resolution.canonical_path if resolution else "",
        "future_path": resolution.future_path if resolution else "",
        "canonical_path_authoritative": bool(resolution.canonical_path_remains_authoritative) if resolution else False,
        "candidate_path_count": len(candidate_paths),
        "checked_path_count": len(checked_paths),
        "hit_path_kind": hit_path_kind,
        "legacy_path_checked": legacy_path_checked,
        "future_path_checked": future_path_checked,
        "future_path_fallback_used": hit_path_kind == "future-foldered" and legacy_path_checked,
        "direct_path_fallback_used": direct_path_fallback_used,
        "missing": status == "missing",
        "read_only": True,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_artifact_file(
    path: Path,
    *,
    artifact_ref: str,
    artifact_root: Path,
    resolution: WorkspacePathResolution | None,
    candidate_paths: list[Path],
    checked_paths: list[str],
    max_chars: int,
) -> dict[str, Any]:
    resolver_metrics = _workspace_resolver_metrics(
        artifact_ref=artifact_ref,
        artifact_root=artifact_root,
        resolution=resolution,
        candidate_paths=candidate_paths,
        checked_paths=checked_paths,
        hit_path=path,
        status="found",
    )
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {
            "status": "error",
            "artifact_ref": artifact_ref,
            "artifact_root": str(artifact_root),
            "path": str(path),
            "error": f"artifact is not valid UTF-8 text: {exc}",
            "resolution_status": "resolved" if resolution else "direct-path-fallback",
            "resolution": resolution.to_dict() if resolution else {},
            "checked_paths": checked_paths,
            "resolver_metrics": {**resolver_metrics, "missing": False},
            "side_effect_policy": _reader_side_effect_policy(),
        }
    parsed_json: Any | None = None
    parse_error = ""
    content_type = "text"
    if path.suffix.lower() == ".json" or raw_text.lstrip().startswith(("{", "[")):
        try:
            parsed_json = json.loads(raw_text)
            content_type = "json"
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            content_type = "invalid-json"
    truncated = len(raw_text) > max_chars
    return {
        "status": "found",
        "artifact_ref": artifact_ref,
        "artifact_root": str(artifact_root),
        "path": str(path),
        "content_type": content_type,
        "content": raw_text[:max_chars],
        "content_truncated": truncated,
        "content_length": len(raw_text),
        "json": parsed_json if parsed_json is not None else None,
        "json_parse_error": parse_error,
        "resolution_status": "resolved" if resolution else "direct-path-fallback",
        "resolution": resolution.to_dict() if resolution else {},
        "checked_paths": checked_paths,
        "resolver_metrics": resolver_metrics,
        "side_effect_policy": _reader_side_effect_policy(),
    }


def _reader_side_effect_policy() -> dict[str, bool]:
    return {
        "read_only": True,
        "writes_artifacts": False,
        "moves_artifacts": False,
        "creates_directories": False,
        "enables_dual_write": False,
        "changes_canonical_path": False,
        "starts_browser": False,
        "calls_mcp": False,
    }
