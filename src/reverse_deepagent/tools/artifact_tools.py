from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from reverse_deepagent.runtime.base import ReverseRuntime
from reverse_deepagent.schemas import FinalResult
from reverse_deepagent.workspace_contract import WorkspacePathResolution, WorkspacePathResolver, default_workspace_artifact_routes, workspace_virtual_uri


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


def make_assess_workspace_migration_readiness_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for workspace migration readiness planning."""

    root = Path(default_artifact_root)

    def assess_workspace_migration_readiness(
        artifact_root: str | None = None,
        delivery_source_audit_json: str | None = None,
    ) -> dict[str, Any]:
        """Assess dual-write and foldered-canonical migration readiness without mutating files."""

        return assess_workspace_migration_readiness_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )

    assess_workspace_migration_readiness.__name__ = "assess_workspace_migration_readiness"
    assess_workspace_migration_readiness.__doc__ = (
        "Read-only workspace migration readiness report. Combines workspace consumer adoption status, "
        "registered artifact route counts, and optional execute_local_delivery delivery_artifact_source_audit JSON "
        "to distinguish limited dual-write pilot readiness from foldered-canonical migration blockers. "
        "It does not inspect files, write artifacts, create directories, enable dual-write, migrate paths, start browsers, or call MCP."
    )
    return assess_workspace_migration_readiness


def make_assess_workspace_consumer_readiness_score_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only scoring tool for workspace consumer migration readiness."""

    root = Path(default_artifact_root)

    def assess_workspace_consumer_readiness_score(
        artifact_root: str | None = None,
        readiness_report_json: str | None = None,
        pilot_result_json: str | None = None,
        delivery_source_audit_json: str | None = None,
    ) -> dict[str, Any]:
        """Score workspace consumer readiness without enabling dual-write or migrating paths."""

        return assess_workspace_consumer_readiness_score_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_report_json=readiness_report_json,
            pilot_result_json=pilot_result_json,
            delivery_source_audit_json=delivery_source_audit_json,
        )

    assess_workspace_consumer_readiness_score.__name__ = "assess_workspace_consumer_readiness_score"
    assess_workspace_consumer_readiness_score.__doc__ = (
        "Read-only workspace consumer readiness score for dual-write expansion and foldered-canonical migration review. "
        "It consumes the static consumer audit, optional migration readiness report, optional delivery source audit JSON, "
        "and optional observed dual-write pilot result JSON. It does not inspect files, write artifacts, create directories, "
        "enable dual-write, migrate paths, change canonical paths, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return assess_workspace_consumer_readiness_score


def make_plan_workspace_dual_write_expansion_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for reviewed opt-in workspace dual-write expansion planning."""

    root = Path(default_artifact_root)

    def plan_workspace_dual_write_expansion(
        artifact_root: str | None = None,
        readiness_score_json: str | None = None,
        readiness_report_json: str | None = None,
        pilot_result_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 24,
        include_medium_risk: bool = False,
    ) -> dict[str, Any]:
        """Plan opt-in dual-write expansion without enabling dual-write or writing artifacts."""

        return plan_workspace_dual_write_expansion_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_score_json=readiness_score_json,
            readiness_report_json=readiness_report_json,
            pilot_result_json=pilot_result_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            include_medium_risk=include_medium_risk,
        )

    plan_workspace_dual_write_expansion.__name__ = "plan_workspace_dual_write_expansion"
    plan_workspace_dual_write_expansion.__doc__ = (
        "Read-only opt-in workspace dual-write expansion plan. It consumes workspace-consumer-readiness-score evidence, "
        "optional migration readiness / pilot result inputs, and optional reviewed artifact keys to produce the next reviewed expansion scope. "
        "It does not inspect files, write artifacts, create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, "
        "start browsers, call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_dual_write_expansion


def make_review_workspace_dual_write_expansion_workflow_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a review workflow tool for opt-in dual-write expansion evidence."""

    root = Path(default_artifact_root)

    def review_workspace_dual_write_expansion_workflow(
        artifact_root: str | None = None,
        expansion_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Review an expansion plan and observed dual-write output without running pipelines."""

        return review_workspace_dual_write_expansion_workflow_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            expansion_plan_json=expansion_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    review_workspace_dual_write_expansion_workflow.__name__ = "review_workspace_dual_write_expansion_workflow"
    review_workspace_dual_write_expansion_workflow.__doc__ = (
        "Review-first workflow for an opt-in workspace dual-write expansion scope. It consumes a ready expansion plan "
        "and optional observed workspace-dual-write-plan evidence, verifies output compatibility, and optionally writes "
        "workspace/workspace-dual-write-expansion-result.json only when write_result=true. It does not run pipelines, "
        "enable dual-write, migrate paths, change canonical paths, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_dual_write_expansion_workflow


def make_record_workspace_dual_write_expansion_result_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a verifier for observed opt-in dual-write expansion output."""

    root = Path(default_artifact_root)

    def record_workspace_dual_write_expansion_result(
        artifact_root: str | None = None,
        expansion_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Verify observed expansion output and optionally write an audit artifact."""

        return record_workspace_dual_write_expansion_result_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            expansion_plan_json=expansion_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    record_workspace_dual_write_expansion_result.__name__ = "record_workspace_dual_write_expansion_result"
    record_workspace_dual_write_expansion_result.__doc__ = (
        "Verify an observed scoped workspace dual-write expansion output against a reviewed expansion plan. "
        "Default mode is read-only and inspects existing legacy/future artifact files plus workspace-dual-write-plan evidence; "
        "write_result=true writes only workspace/workspace-dual-write-expansion-result.json. It never runs pipelines, enables dual-write, "
        "migrates paths, changes canonical paths, starts browsers, calls MCP, or touches mobile full runtime chains."
    )
    return record_workspace_dual_write_expansion_result


def make_plan_workspace_foldered_canonical_migration_pilot_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only planner for a narrow foldered-canonical migration pilot."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_migration_pilot(
        artifact_root: str | None = None,
        readiness_score_json: str | None = None,
        readiness_report_json: str | None = None,
        pilot_result_json: str | None = None,
        expansion_result_json: str | None = None,
        expansion_result_artifact_ref: str | None = "workspace_dual_write_expansion_result",
        artifact_keys_json: str | None = None,
        max_artifacts: int = 8,
        include_medium_risk: bool = False,
    ) -> dict[str, Any]:
        """Plan, but never execute, a narrow foldered-canonical migration pilot."""

        return plan_workspace_foldered_canonical_migration_pilot_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_score_json=readiness_score_json,
            readiness_report_json=readiness_report_json,
            pilot_result_json=pilot_result_json,
            expansion_result_json=expansion_result_json,
            expansion_result_artifact_ref=expansion_result_artifact_ref,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            include_medium_risk=include_medium_risk,
        )

    plan_workspace_foldered_canonical_migration_pilot.__name__ = "plan_workspace_foldered_canonical_migration_pilot"
    plan_workspace_foldered_canonical_migration_pilot.__doc__ = (
        "Read-only / plan-only narrow foldered-canonical migration pilot descriptor. It consumes workspace consumer readiness "
        "and verified expansion result evidence, then proposes reviewed artifact keys whose future foldered paths could be piloted. "
        "It does not write artifacts, create directories, migrate paths, change canonical paths, run pipelines, start browsers, call MCP, "
        "or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_migration_pilot


def make_review_workspace_foldered_canonical_migration_preflight_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only preflight reviewer for a foldered-canonical migration pilot."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_preflight(
        artifact_root: str | None = None,
        migration_pilot_plan_json: str | None = None,
        migration_pilot_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_pilot_plan",
    ) -> dict[str, Any]:
        """Inspect pilot candidate files and produce rollback requirements without mutating paths."""

        return review_workspace_foldered_canonical_migration_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_pilot_plan_json=migration_pilot_plan_json,
            migration_pilot_plan_artifact_ref=migration_pilot_plan_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_preflight.__name__ = "review_workspace_foldered_canonical_migration_preflight"
    review_workspace_foldered_canonical_migration_preflight.__doc__ = (
        "Read-only execution preflight for a reviewed foldered-canonical migration pilot plan. It inspects existing "
        "legacy/future candidate files, compares digests, and emits rollback requirements. It does not write artifacts, "
        "create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, mutate manifests, "
        "start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_preflight


def make_plan_workspace_foldered_canonical_migration_apply_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only apply-plan reviewer for foldered-canonical migration."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_migration_apply(
        artifact_root: str | None = None,
        migration_preflight_json: str | None = None,
        migration_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_preflight",
        include_medium_risk: bool = False,
    ) -> dict[str, Any]:
        """Plan, but never execute, a foldered-canonical migration apply step."""

        return plan_workspace_foldered_canonical_migration_apply_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_preflight_json=migration_preflight_json,
            migration_preflight_artifact_ref=migration_preflight_artifact_ref,
            include_medium_risk=include_medium_risk,
        )

    plan_workspace_foldered_canonical_migration_apply.__name__ = "plan_workspace_foldered_canonical_migration_apply"
    plan_workspace_foldered_canonical_migration_apply.__doc__ = (
        "Read-only / plan-only foldered-canonical migration apply descriptor. It consumes a ready preflight, "
        "then emits manifest mutation guards, rollback requirements, compatibility gates, and planned apply steps. "
        "It does not write artifacts, create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, "
        "mutate manifests, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_migration_apply


def make_plan_workspace_foldered_canonical_migration_approval_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only approval / transaction reviewer for foldered-canonical migration apply."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_migration_approval(
        artifact_root: str | None = None,
        migration_apply_plan_json: str | None = None,
        migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
        reviewer: str | None = None,
        review_ticket: str | None = None,
        transaction_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Plan approval, transaction, idempotency, rollback, and validation gates without executing apply."""

        return plan_workspace_foldered_canonical_migration_approval_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_apply_plan_json=migration_apply_plan_json,
            migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
            reviewer=reviewer,
            review_ticket=review_ticket,
            transaction_id=transaction_id,
            idempotency_key=idempotency_key,
        )

    plan_workspace_foldered_canonical_migration_approval.__name__ = "plan_workspace_foldered_canonical_migration_approval"
    plan_workspace_foldered_canonical_migration_approval.__doc__ = (
        "Read-only / plan-only foldered-canonical migration apply approval and transaction descriptor. It consumes a ready "
        "apply plan, then emits approval ledger requirements, transaction journal plans, idempotency guards, stale evidence "
        "guards, manifest dry-run requirements, rollback checkpoint requirements, post-apply validation requirements, and "
        "compatibility windows. It does not record approval, write journals, inspect files, write artifacts, create directories, "
        "run pipelines, enable dual-write, migrate paths, change canonical paths, mutate manifests, start browsers, call MCP, "
        "or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_migration_approval


def make_review_workspace_foldered_canonical_migration_manifest_dry_run_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only manifest dry-run / rollback checkpoint reviewer for foldered-canonical migration."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_manifest_dry_run(
        artifact_root: str | None = None,
        migration_approval_plan_json: str | None = None,
        migration_approval_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_approval_plan",
        migration_apply_plan_json: str | None = None,
        migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Preview manifest promotion and rollback checkpoint requirements without mutating files."""

        return review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_approval_plan_json=migration_approval_plan_json,
            migration_approval_plan_artifact_ref=migration_approval_plan_artifact_ref,
            migration_apply_plan_json=migration_apply_plan_json,
            migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_manifest_dry_run.__name__ = "review_workspace_foldered_canonical_migration_manifest_dry_run"
    review_workspace_foldered_canonical_migration_manifest_dry_run.__doc__ = (
        "Read-only foldered-canonical migration manifest dry-run and rollback checkpoint descriptor. It consumes a ready "
        "approval plan, matching apply plan, and optional backend artifact manifest, then previews manifest canonical-path "
        "promotion updates plus rollback checkpoint requirements. It does not record approval, write journals, write artifacts, "
        "create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, mutate manifests, start "
        "browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_manifest_dry_run


def make_review_workspace_foldered_canonical_migration_post_apply_validation_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only post-apply validation reviewer for foldered-canonical migration."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_post_apply_validation(
        artifact_root: str | None = None,
        migration_manifest_dry_run_json: str | None = None,
        migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
        migration_apply_plan_json: str | None = None,
        migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
        post_apply_backend_manifest_json: str | None = None,
        post_apply_backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Validate observed post-apply manifest state without mutating manifests or paths."""

        return review_workspace_foldered_canonical_migration_post_apply_validation_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_manifest_dry_run_json=migration_manifest_dry_run_json,
            migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
            migration_apply_plan_json=migration_apply_plan_json,
            migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
            post_apply_backend_manifest_json=post_apply_backend_manifest_json,
            post_apply_backend_manifest_artifact_ref=post_apply_backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_post_apply_validation.__name__ = "review_workspace_foldered_canonical_migration_post_apply_validation"
    review_workspace_foldered_canonical_migration_post_apply_validation.__doc__ = (
        "Read-only foldered-canonical migration post-apply validation descriptor. It consumes a ready manifest dry-run, "
        "matching apply plan, and observed post-apply backend artifact manifest, then verifies manifest canonical-path "
        "promotion evidence and legacy fallback requirements for review. It does not write validation artifacts, write "
        "rollback checkpoints, record approval, write journals, inspect files, create directories, run pipelines, enable "
        "dual-write, migrate paths, change canonical paths, mutate manifests, start browsers, call MCP, or touch mobile "
        "full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_post_apply_validation


def make_record_workspace_foldered_canonical_migration_post_apply_validation_result_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a writer for reviewed foldered-canonical post-apply validation result artifacts."""

    root = Path(default_artifact_root)

    def record_workspace_foldered_canonical_migration_post_apply_validation_result(
        artifact_root: str | None = None,
        post_apply_validation_json: str | None = None,
        post_apply_validation_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_apply_validation",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Record post-apply validation evidence without mutating manifests or tightening legacy fallback."""

        return record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            post_apply_validation_json=post_apply_validation_json,
            post_apply_validation_artifact_ref=post_apply_validation_artifact_ref,
            write_result=write_result,
        )

    record_workspace_foldered_canonical_migration_post_apply_validation_result.__name__ = (
        "record_workspace_foldered_canonical_migration_post_apply_validation_result"
    )
    record_workspace_foldered_canonical_migration_post_apply_validation_result.__doc__ = (
        "Record a durable foldered-canonical post-apply validation result from an existing validation descriptor. "
        "Defaults to dry-run; write_result=true writes only workspace/workspace-foldered-canonical-migration-post-apply-validation-result.json. "
        "It does not mutate backend manifests, move files, tighten legacy fallback, finalize migration, run pipelines, start browsers, "
        "call MCP, or touch mobile full runtime chains."
    )
    return record_workspace_foldered_canonical_migration_post_apply_validation_result


def make_review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only readiness reviewer for legacy fallback tightening."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_legacy_fallback_tightening_readiness(
        artifact_root: str | None = None,
        post_apply_validation_result_json: str | None = None,
        post_apply_validation_result_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_apply_validation_result",
        readiness_score_json: str | None = None,
        readiness_score_artifact_ref: str | None = "workspace_consumer_readiness_score",
    ) -> dict[str, Any]:
        """Review whether legacy fallback tightening can be planned, without mutating manifests."""

        return review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            post_apply_validation_result_json=post_apply_validation_result_json,
            post_apply_validation_result_artifact_ref=post_apply_validation_result_artifact_ref,
            readiness_score_json=readiness_score_json,
            readiness_score_artifact_ref=readiness_score_artifact_ref,
        )

    review_workspace_foldered_canonical_legacy_fallback_tightening_readiness.__name__ = (
        "review_workspace_foldered_canonical_legacy_fallback_tightening_readiness"
    )
    review_workspace_foldered_canonical_legacy_fallback_tightening_readiness.__doc__ = (
        "Read-only legacy fallback tightening readiness descriptor. It consumes a verified post-apply validation result and "
        "an explicit workspace consumer readiness score artifact / JSON, then reports whether a separate reviewed tightening "
        "plan may be prepared. It does not write artifacts, mutate manifests, change canonical paths, tighten fallback, finalize "
        "migration, run pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_legacy_fallback_tightening_readiness


def make_plan_workspace_foldered_canonical_legacy_fallback_tightening_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a review-only legacy fallback tightening apply plan descriptor."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_legacy_fallback_tightening(
        artifact_root: str | None = None,
        legacy_fallback_tightening_readiness_json: str | None = None,
        legacy_fallback_tightening_readiness_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_readiness",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        artifact_keys_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan reviewed legacy fallback metadata tightening without mutating backend manifests."""

        return plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            legacy_fallback_tightening_readiness_json=legacy_fallback_tightening_readiness_json,
            legacy_fallback_tightening_readiness_artifact_ref=legacy_fallback_tightening_readiness_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            artifact_keys_json=artifact_keys_json,
        )

    plan_workspace_foldered_canonical_legacy_fallback_tightening.__name__ = (
        "plan_workspace_foldered_canonical_legacy_fallback_tightening"
    )
    plan_workspace_foldered_canonical_legacy_fallback_tightening.__doc__ = (
        "Review-only legacy fallback tightening apply plan descriptor. It consumes a ready tightening readiness descriptor "
        "and current backend artifact manifest, then previews which workspace_alias legacy fallback metadata a separate "
        "executor may tighten. It does not write artifacts, mutate manifests, tighten fallback, finalize migration, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_legacy_fallback_tightening


def make_review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only legacy fallback tightening executor preflight descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_legacy_fallback_tightening_preflight(
        artifact_root: str | None = None,
        legacy_fallback_tightening_plan_json: str | None = None,
        legacy_fallback_tightening_plan_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        review_approval_ledger_json: str | None = None,
        review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
    ) -> dict[str, Any]:
        """Review legacy fallback tightening executor inputs without mutating manifests."""

        return review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            legacy_fallback_tightening_plan_json=legacy_fallback_tightening_plan_json,
            legacy_fallback_tightening_plan_artifact_ref=legacy_fallback_tightening_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            review_approval_ledger_json=review_approval_ledger_json,
            review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
        )

    review_workspace_foldered_canonical_legacy_fallback_tightening_preflight.__name__ = (
        "review_workspace_foldered_canonical_legacy_fallback_tightening_preflight"
    )
    review_workspace_foldered_canonical_legacy_fallback_tightening_preflight.__doc__ = (
        "Read-only legacy fallback tightening executor preflight descriptor. It consumes a ready tightening plan, current "
        "backend artifact manifest, and review approval ledger evidence, then revalidates the explicit executor gate before "
        "any metadata mutation. It does not write artifacts, write journals, mutate manifests, tighten fallback, finalize "
        "migration, run pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_legacy_fallback_tightening_preflight


def make_execute_workspace_foldered_canonical_legacy_fallback_tightening_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create an explicit-review-only legacy fallback tightening executor."""

    root = Path(default_artifact_root)

    def execute_workspace_foldered_canonical_legacy_fallback_tightening(
        artifact_root: str | None = None,
        mode: str = "dry-run",
        approve_legacy_fallback_tightening: bool = False,
        legacy_fallback_tightening_preflight_json: str | None = None,
        legacy_fallback_tightening_preflight_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_preflight",
        legacy_fallback_tightening_plan_json: str | None = None,
        legacy_fallback_tightening_plan_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        expected_plan_digest: str | None = None,
    ) -> dict[str, Any]:
        """Apply reviewed legacy fallback metadata tightening with journal and result evidence."""

        return execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            mode=mode,
            approve_legacy_fallback_tightening=approve_legacy_fallback_tightening,
            legacy_fallback_tightening_preflight_json=legacy_fallback_tightening_preflight_json,
            legacy_fallback_tightening_preflight_artifact_ref=legacy_fallback_tightening_preflight_artifact_ref,
            legacy_fallback_tightening_plan_json=legacy_fallback_tightening_plan_json,
            legacy_fallback_tightening_plan_artifact_ref=legacy_fallback_tightening_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            expected_plan_digest=expected_plan_digest,
        )

    execute_workspace_foldered_canonical_legacy_fallback_tightening.__name__ = (
        "execute_workspace_foldered_canonical_legacy_fallback_tightening"
    )
    execute_workspace_foldered_canonical_legacy_fallback_tightening.__doc__ = (
        "Explicit-review-only legacy fallback tightening executor. Defaults to dry-run; apply mode requires "
        "approve_legacy_fallback_tightening=true, ready preflight evidence, matching plan digest, and a current backend "
        "artifact manifest. It writes append-only tightening journal, result artifact, and updates workspace_alias legacy "
        "fallback metadata only in apply mode. It does not move files, change canonical paths, finalize migration, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return execute_workspace_foldered_canonical_legacy_fallback_tightening


def make_review_workspace_foldered_canonical_migration_finalization_readiness_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only readiness reviewer for foldered-canonical migration finalization."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_finalization_readiness(
        artifact_root: str | None = None,
        legacy_fallback_tightening_result_json: str | None = None,
        legacy_fallback_tightening_result_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_result",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Review whether a separate finalization plan can be prepared without mutating manifests."""

        return review_workspace_foldered_canonical_migration_finalization_readiness_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            legacy_fallback_tightening_result_json=legacy_fallback_tightening_result_json,
            legacy_fallback_tightening_result_artifact_ref=legacy_fallback_tightening_result_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_finalization_readiness.__name__ = (
        "review_workspace_foldered_canonical_migration_finalization_readiness"
    )
    review_workspace_foldered_canonical_migration_finalization_readiness.__doc__ = (
        "Read-only foldered-canonical migration finalization readiness descriptor. It consumes an applied legacy fallback "
        "tightening result and the current backend artifact manifest, then verifies that finalization can move to a separate "
        "reviewed plan. It does not write artifacts, mutate manifests, change canonical paths, finalize migration, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_finalization_readiness


def make_plan_workspace_foldered_canonical_migration_finalization_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a review-only foldered-canonical migration finalization plan descriptor."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_migration_finalization(
        artifact_root: str | None = None,
        finalization_readiness_json: str | None = None,
        finalization_readiness_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_readiness",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        artifact_keys_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan finalization metadata changes without mutating manifests or changing paths."""

        return plan_workspace_foldered_canonical_migration_finalization_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            finalization_readiness_json=finalization_readiness_json,
            finalization_readiness_artifact_ref=finalization_readiness_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            artifact_keys_json=artifact_keys_json,
        )

    plan_workspace_foldered_canonical_migration_finalization.__name__ = (
        "plan_workspace_foldered_canonical_migration_finalization"
    )
    plan_workspace_foldered_canonical_migration_finalization.__doc__ = (
        "Review-only foldered-canonical migration finalization plan descriptor. It consumes a ready finalization readiness "
        "descriptor and current backend artifact manifest, then previews finalization metadata updates for a later reviewed "
        "preflight / executor. It does not write artifacts, mutate manifests, change canonical paths, finalize migration, "
        "run pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_migration_finalization


def make_review_workspace_foldered_canonical_migration_finalization_preflight_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only foldered-canonical migration finalization preflight descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_finalization_preflight(
        artifact_root: str | None = None,
        finalization_plan_json: str | None = None,
        finalization_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        review_approval_ledger_json: str | None = None,
        review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
    ) -> dict[str, Any]:
        """Preflight reviewed finalization without writing journals or mutating manifests."""

        return review_workspace_foldered_canonical_migration_finalization_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            finalization_plan_json=finalization_plan_json,
            finalization_plan_artifact_ref=finalization_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            review_approval_ledger_json=review_approval_ledger_json,
            review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_finalization_preflight.__name__ = (
        "review_workspace_foldered_canonical_migration_finalization_preflight"
    )
    review_workspace_foldered_canonical_migration_finalization_preflight.__doc__ = (
        "Read-only foldered-canonical migration finalization preflight descriptor. It consumes a ready finalization plan, "
        "current backend artifact manifest, and matching review approval ledger evidence before a later explicit executor. "
        "It does not write artifacts, write journals, mutate manifests, change canonical paths, finalize migration, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_finalization_preflight


def make_execute_workspace_foldered_canonical_migration_finalization_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create an explicit-review-only foldered-canonical migration finalization executor."""

    root = Path(default_artifact_root)

    def execute_workspace_foldered_canonical_migration_finalization(
        artifact_root: str | None = None,
        mode: str = "dry-run",
        approve_finalization: bool = False,
        finalization_preflight_json: str | None = None,
        finalization_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_preflight",
        finalization_plan_json: str | None = None,
        finalization_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        expected_plan_digest: str | None = None,
    ) -> dict[str, Any]:
        """Finalize reviewed foldered-canonical metadata with journal and result evidence."""

        return execute_workspace_foldered_canonical_migration_finalization_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            mode=mode,
            approve_finalization=approve_finalization,
            finalization_preflight_json=finalization_preflight_json,
            finalization_preflight_artifact_ref=finalization_preflight_artifact_ref,
            finalization_plan_json=finalization_plan_json,
            finalization_plan_artifact_ref=finalization_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            expected_plan_digest=expected_plan_digest,
        )

    execute_workspace_foldered_canonical_migration_finalization.__name__ = (
        "execute_workspace_foldered_canonical_migration_finalization"
    )
    execute_workspace_foldered_canonical_migration_finalization.__doc__ = (
        "Explicit-review-only foldered-canonical migration finalization executor. Defaults to dry-run; apply mode requires "
        "approve_finalization=true, ready preflight evidence, matching plan digest, and a current backend artifact manifest. "
        "It writes append-only finalization journal, result artifact, and updates workspace_alias finalization metadata only "
        "in apply mode. It does not move files, change canonical paths, run pipelines, start browsers, call MCP, or touch "
        "mobile full runtime chains."
    )
    return execute_workspace_foldered_canonical_migration_finalization


def make_review_workspace_foldered_canonical_migration_post_finalization_audit_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only post-finalization audit descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_post_finalization_audit(
        artifact_root: str | None = None,
        finalization_result_json: str | None = None,
        finalization_result_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_result",
        finalization_journal_json: str | None = None,
        finalization_journal_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_journal",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Audit finalization result / journal / backend manifest consistency without side effects."""

        return review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            finalization_result_json=finalization_result_json,
            finalization_result_artifact_ref=finalization_result_artifact_ref,
            finalization_journal_json=finalization_journal_json,
            finalization_journal_artifact_ref=finalization_journal_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_post_finalization_audit.__name__ = (
        "review_workspace_foldered_canonical_migration_post_finalization_audit"
    )
    review_workspace_foldered_canonical_migration_post_finalization_audit.__doc__ = (
        "Read-only foldered-canonical post-finalization audit descriptor. It consumes a finalization result, "
        "append-only finalization journal, and current backend artifact manifest, then verifies transaction, "
        "idempotency, workspace_alias finalization metadata, and canonical path stability. It does not write artifacts, "
        "mutate manifests, move files, change canonical paths, run pipelines, start browsers, call MCP, or touch mobile "
        "full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_post_finalization_audit


def make_review_workspace_foldered_canonical_broader_rollout_readiness_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only broader rollout readiness descriptor after foldered-canonical finalization."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_broader_rollout_readiness(
        artifact_root: str | None = None,
        post_finalization_audit_json: str | None = None,
        post_finalization_audit_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_finalization_audit",
        readiness_score_json: str | None = None,
        readiness_score_artifact_ref: str | None = "workspace_consumer_readiness_score",
        delivery_source_audit_json: str | None = None,
        expansion_result_json: str | None = None,
        expansion_result_artifact_ref: str | None = "workspace_dual_write_expansion_result",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Review broader rollout readiness without authorizing rollout or mutating artifacts."""

        return review_workspace_foldered_canonical_broader_rollout_readiness_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            post_finalization_audit_json=post_finalization_audit_json,
            post_finalization_audit_artifact_ref=post_finalization_audit_artifact_ref,
            readiness_score_json=readiness_score_json,
            readiness_score_artifact_ref=readiness_score_artifact_ref,
            delivery_source_audit_json=delivery_source_audit_json,
            expansion_result_json=expansion_result_json,
            expansion_result_artifact_ref=expansion_result_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_broader_rollout_readiness.__name__ = (
        "review_workspace_foldered_canonical_broader_rollout_readiness"
    )
    review_workspace_foldered_canonical_broader_rollout_readiness.__doc__ = (
        "Read-only foldered-canonical broader rollout readiness descriptor. It consumes post-finalization audit, "
        "workspace consumer readiness, delivery source recheck, verified dual-write expansion evidence, and current backend "
        "manifest evidence. It does not write artifacts, mutate manifests, enable rollout, run pipelines, start browsers, "
        "call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_broader_rollout_readiness


def make_plan_workspace_foldered_canonical_broader_rollout_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a review-only broader rollout plan descriptor after readiness review."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_broader_rollout(
        artifact_root: str | None = None,
        broader_rollout_readiness_json: str | None = None,
        broader_rollout_readiness_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_readiness",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        artifact_keys_json: str | None = None,
        max_artifacts: int = 32,
        include_medium_risk: bool = False,
    ) -> dict[str, Any]:
        """Plan a broader rollout review scope without applying rollout or mutating manifests."""

        return plan_workspace_foldered_canonical_broader_rollout_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            broader_rollout_readiness_json=broader_rollout_readiness_json,
            broader_rollout_readiness_artifact_ref=broader_rollout_readiness_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            include_medium_risk=include_medium_risk,
        )

    plan_workspace_foldered_canonical_broader_rollout.__name__ = "plan_workspace_foldered_canonical_broader_rollout"
    plan_workspace_foldered_canonical_broader_rollout.__doc__ = (
        "Review-only / plan-only foldered-canonical broader rollout descriptor. It consumes broader rollout readiness "
        "evidence plus the current backend manifest, then selects finalized workspace artifact keys for a separate reviewed "
        "rollout plan. It does not write artifacts, mutate manifests, enable dual-write, apply rollout, start browsers, "
        "call MCP, or touch mobile full runtime chains."
    )
    return plan_workspace_foldered_canonical_broader_rollout


def make_review_workspace_foldered_canonical_broader_rollout_preflight_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only broader rollout executor preflight descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_broader_rollout_preflight(
        artifact_root: str | None = None,
        broader_rollout_plan_json: str | None = None,
        broader_rollout_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        review_approval_ledger_json: str | None = None,
        review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
    ) -> dict[str, Any]:
        """Review broader rollout executor inputs without applying rollout or mutating manifests."""

        return review_workspace_foldered_canonical_broader_rollout_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            broader_rollout_plan_json=broader_rollout_plan_json,
            broader_rollout_plan_artifact_ref=broader_rollout_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            review_approval_ledger_json=review_approval_ledger_json,
            review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
        )

    review_workspace_foldered_canonical_broader_rollout_preflight.__name__ = (
        "review_workspace_foldered_canonical_broader_rollout_preflight"
    )
    review_workspace_foldered_canonical_broader_rollout_preflight.__doc__ = (
        "Read-only foldered-canonical broader rollout executor preflight descriptor. It consumes a ready broader rollout "
        "plan, current backend artifact manifest, and review approval ledger evidence, then revalidates the explicit "
        "executor gate before any broader rollout apply. It does not write artifacts, write journals, mutate manifests, "
        "enable dual-write, apply rollout, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_broader_rollout_preflight


def make_execute_workspace_foldered_canonical_broader_rollout_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create an explicit-review-only broader rollout executor."""

    root = Path(default_artifact_root)

    def execute_workspace_foldered_canonical_broader_rollout(
        artifact_root: str | None = None,
        mode: str = "dry-run",
        approve_broader_rollout: bool = False,
        broader_rollout_preflight_json: str | None = None,
        broader_rollout_preflight_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_preflight",
        broader_rollout_plan_json: str | None = None,
        broader_rollout_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        expected_plan_digest: str | None = None,
    ) -> dict[str, Any]:
        """Apply reviewed broader rollout metadata with journal and result evidence."""

        return execute_workspace_foldered_canonical_broader_rollout_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            mode=mode,
            approve_broader_rollout=approve_broader_rollout,
            broader_rollout_preflight_json=broader_rollout_preflight_json,
            broader_rollout_preflight_artifact_ref=broader_rollout_preflight_artifact_ref,
            broader_rollout_plan_json=broader_rollout_plan_json,
            broader_rollout_plan_artifact_ref=broader_rollout_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            expected_plan_digest=expected_plan_digest,
        )

    execute_workspace_foldered_canonical_broader_rollout.__name__ = "execute_workspace_foldered_canonical_broader_rollout"
    execute_workspace_foldered_canonical_broader_rollout.__doc__ = (
        "Explicit-review-only foldered-canonical broader rollout executor. Defaults to dry-run; apply mode requires "
        "approve_broader_rollout=true, ready preflight evidence, matching plan digest, and a current backend artifact "
        "manifest artifact ref. It writes append-only rollout journal, result artifact, and updates workspace_alias broader "
        "rollout metadata only in apply mode. It does not move files, change canonical paths, enable dual-write, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return execute_workspace_foldered_canonical_broader_rollout


def make_review_workspace_foldered_canonical_broader_rollout_post_audit_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only broader rollout post-audit descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_broader_rollout_post_audit(
        artifact_root: str | None = None,
        broader_rollout_result_json: str | None = None,
        broader_rollout_result_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_result",
        broader_rollout_journal_json: str | None = None,
        broader_rollout_journal_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_journal",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    ) -> dict[str, Any]:
        """Audit broader rollout result / journal / backend manifest consistency without side effects."""

        return review_workspace_foldered_canonical_broader_rollout_post_audit_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            broader_rollout_result_json=broader_rollout_result_json,
            broader_rollout_result_artifact_ref=broader_rollout_result_artifact_ref,
            broader_rollout_journal_json=broader_rollout_journal_json,
            broader_rollout_journal_artifact_ref=broader_rollout_journal_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
        )

    review_workspace_foldered_canonical_broader_rollout_post_audit.__name__ = (
        "review_workspace_foldered_canonical_broader_rollout_post_audit"
    )
    review_workspace_foldered_canonical_broader_rollout_post_audit.__doc__ = (
        "Read-only foldered-canonical broader rollout post-audit descriptor. It consumes a broader rollout result, "
        "append-only broader rollout journal, and current backend artifact manifest, then verifies transaction, "
        "idempotency, workspace_alias broader rollout metadata, and canonical path stability. It does not write artifacts, "
        "mutate manifests, move files, change canonical paths, enable dual-write, run pipelines, start browsers, call MCP, "
        "or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_broader_rollout_post_audit


def make_plan_workspace_foldered_canonical_broader_rollout_rollback_decision_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a review-only rollback-vs-commit decision plan descriptor."""

    root = Path(default_artifact_root)

    def plan_workspace_foldered_canonical_broader_rollout_rollback_decision(
        artifact_root: str | None = None,
        broader_rollout_post_audit_json: str | None = None,
        broader_rollout_post_audit_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_post_audit",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        requested_decision: str | None = None,
    ) -> dict[str, Any]:
        """Plan a reviewed rollback-vs-commit decision without recording or executing it."""

        return plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            broader_rollout_post_audit_json=broader_rollout_post_audit_json,
            broader_rollout_post_audit_artifact_ref=broader_rollout_post_audit_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            requested_decision=requested_decision,
        )

    plan_workspace_foldered_canonical_broader_rollout_rollback_decision.__name__ = (
        "plan_workspace_foldered_canonical_broader_rollout_rollback_decision"
    )
    plan_workspace_foldered_canonical_broader_rollout_rollback_decision.__doc__ = (
        "Review-only foldered-canonical broader rollout rollback-vs-commit decision plan descriptor. It consumes a "
        "verified broader rollout post-audit descriptor and current backend artifact manifest, then prepares commit, "
        "rollback, or defer review options without recording a decision, mutating manifests, rolling back metadata, "
        "committing rollout state, moving files, running pipelines, starting browsers, calling MCP, or touching mobile "
        "full runtime chains."
    )
    return plan_workspace_foldered_canonical_broader_rollout_rollback_decision


def make_record_workspace_foldered_canonical_broader_rollout_decision_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a reviewed decision record writer for broader rollout rollback-vs-commit review."""

    root = Path(default_artifact_root)

    def record_workspace_foldered_canonical_broader_rollout_decision(
        artifact_root: str | None = None,
        rollback_decision_plan_json: str | None = None,
        rollback_decision_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_rollback_decision_plan",
        decision: str | None = None,
        reviewer: str | None = None,
        reason: str | None = None,
        write_result: bool = False,
        approve_decision_record: bool = False,
    ) -> dict[str, Any]:
        """Record a reviewed commit / rollback / defer decision without executing it."""

        return record_workspace_foldered_canonical_broader_rollout_decision_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            rollback_decision_plan_json=rollback_decision_plan_json,
            rollback_decision_plan_artifact_ref=rollback_decision_plan_artifact_ref,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
            write_result=write_result,
            approve_decision_record=approve_decision_record,
        )

    record_workspace_foldered_canonical_broader_rollout_decision.__name__ = (
        "record_workspace_foldered_canonical_broader_rollout_decision"
    )
    record_workspace_foldered_canonical_broader_rollout_decision.__doc__ = (
        "Record a reviewed foldered-canonical broader rollout commit / rollback / defer decision. It consumes a "
        "ready rollback-vs-commit decision plan and only writes "
        "workspace/workspace-foldered-canonical-broader-rollout-decision-record.json when write_result=true, "
        "approve_decision_record=true, and a reviewer is provided. It never commits broader rollout state, rolls back "
        "metadata, mutates manifests, moves files, runs pipelines, starts browsers, calls MCP, or touches mobile full "
        "runtime chains."
    )
    return record_workspace_foldered_canonical_broader_rollout_decision


def make_execute_workspace_foldered_canonical_broader_rollout_commit_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create an explicit-review-only broader rollout commit executor."""

    root = Path(default_artifact_root)

    def execute_workspace_foldered_canonical_broader_rollout_commit(
        artifact_root: str | None = None,
        mode: str = "dry-run",
        approve_commit: bool = False,
        decision_record_json: str | None = None,
        decision_record_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_decision_record",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        expected_transaction_id: str | None = None,
    ) -> dict[str, Any]:
        """Commit reviewed broader rollout terminal metadata without rolling back or moving artifacts."""

        return execute_workspace_foldered_canonical_broader_rollout_commit_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            mode=mode,
            approve_commit=approve_commit,
            decision_record_json=decision_record_json,
            decision_record_artifact_ref=decision_record_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            expected_transaction_id=expected_transaction_id,
        )

    execute_workspace_foldered_canonical_broader_rollout_commit.__name__ = (
        "execute_workspace_foldered_canonical_broader_rollout_commit"
    )
    execute_workspace_foldered_canonical_broader_rollout_commit.__doc__ = (
        "Explicit-review-only foldered-canonical broader rollout commit executor. Defaults to dry-run; apply mode "
        "requires approve_commit=true, a recorded commit decision, matching current backend manifest transaction metadata, "
        "and an artifact-ref backend manifest. It writes append-only commit journal, commit result artifact, and accepted "
        "commit metadata only in apply mode. It never rolls back metadata, moves files, changes canonical paths, enables "
        "dual-write, runs pipelines, starts browsers, calls MCP, or touches mobile full runtime chains."
    )
    return execute_workspace_foldered_canonical_broader_rollout_commit


def make_review_workspace_foldered_canonical_broader_rollout_rollback_preflight_tool(
    default_artifact_root: str | Path,
) -> ArtifactTool:
    """Create a read-only broader rollout rollback executor preflight descriptor."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_broader_rollout_rollback_preflight(
        artifact_root: str | None = None,
        decision_record_json: str | None = None,
        decision_record_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_decision_record",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        commit_journal_json: str | None = None,
        commit_journal_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_commit_journal",
        expected_transaction_id: str | None = None,
    ) -> dict[str, Any]:
        """Review rollback executor inputs without mutating broader rollout metadata."""

        return review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            decision_record_json=decision_record_json,
            decision_record_artifact_ref=decision_record_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            commit_journal_json=commit_journal_json,
            commit_journal_artifact_ref=commit_journal_artifact_ref,
            expected_transaction_id=expected_transaction_id,
        )

    review_workspace_foldered_canonical_broader_rollout_rollback_preflight.__name__ = (
        "review_workspace_foldered_canonical_broader_rollout_rollback_preflight"
    )
    review_workspace_foldered_canonical_broader_rollout_rollback_preflight.__doc__ = (
        "Read-only foldered-canonical broader rollout rollback executor preflight descriptor. It consumes a recorded "
        "rollback decision, current backend artifact manifest, and optional commit journal evidence, then verifies "
        "transaction, canonical-path stability, not-committed state, and rollback executor gates. It does not write "
        "artifacts, mutate manifests, roll back metadata, move files, change canonical paths, enable dual-write, run "
        "pipelines, start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_broader_rollout_rollback_preflight


def make_review_workspace_foldered_canonical_migration_physical_apply_preflight_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only physical-apply preflight reviewer for foldered-canonical migration."""

    root = Path(default_artifact_root)

    def review_workspace_foldered_canonical_migration_physical_apply_preflight(
        artifact_root: str | None = None,
        migration_manifest_dry_run_json: str | None = None,
        migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
        migration_apply_plan_json: str | None = None,
        migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
        review_approval_ledger_json: str | None = None,
        review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
        rollback_checkpoint_json: str | None = None,
        rollback_checkpoint_artifact_ref: str | None = "workspace_foldered_canonical_migration_rollback_checkpoint",
    ) -> dict[str, Any]:
        """Review physical apply executor inputs without writing journals, checkpoints, or manifests."""

        return review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            migration_manifest_dry_run_json=migration_manifest_dry_run_json,
            migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
            migration_apply_plan_json=migration_apply_plan_json,
            migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
            review_approval_ledger_json=review_approval_ledger_json,
            review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
            rollback_checkpoint_json=rollback_checkpoint_json,
            rollback_checkpoint_artifact_ref=rollback_checkpoint_artifact_ref,
        )

    review_workspace_foldered_canonical_migration_physical_apply_preflight.__name__ = "review_workspace_foldered_canonical_migration_physical_apply_preflight"
    review_workspace_foldered_canonical_migration_physical_apply_preflight.__doc__ = (
        "Read-only foldered-canonical migration physical apply executor preflight descriptor. It consumes a ready manifest "
        "dry-run, matching apply plan, review approval ledger evidence, and optional rollback checkpoint evidence, then checks "
        "the explicit executor gate before any mutation. It does not write journals, write checkpoints, write artifacts, inspect "
        "files, create directories, run pipelines, enable dual-write, migrate paths, change canonical paths, mutate manifests, "
        "start browsers, call MCP, or touch mobile full runtime chains."
    )
    return review_workspace_foldered_canonical_migration_physical_apply_preflight


def make_execute_workspace_foldered_canonical_physical_apply_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create an explicit-review-only physical apply executor for foldered-canonical migration."""

    root = Path(default_artifact_root)

    def execute_workspace_foldered_canonical_physical_apply(
        artifact_root: str | None = None,
        mode: str = "dry-run",
        approve_physical_apply: bool = False,
        physical_apply_preflight_json: str | None = None,
        physical_apply_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_physical_apply_preflight",
        migration_manifest_dry_run_json: str | None = None,
        migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
        migration_apply_plan_json: str | None = None,
        migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
        backend_manifest_json: str | None = None,
        backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
        expected_apply_plan_digest: str | None = None,
    ) -> dict[str, Any]:
        """Apply a reviewed foldered-canonical backend manifest promotion with journal and rollback checkpoint."""

        return execute_workspace_foldered_canonical_physical_apply_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            mode=mode,
            approve_physical_apply=approve_physical_apply,
            physical_apply_preflight_json=physical_apply_preflight_json,
            physical_apply_preflight_artifact_ref=physical_apply_preflight_artifact_ref,
            migration_manifest_dry_run_json=migration_manifest_dry_run_json,
            migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
            migration_apply_plan_json=migration_apply_plan_json,
            migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
            backend_manifest_json=backend_manifest_json,
            backend_manifest_artifact_ref=backend_manifest_artifact_ref,
            expected_apply_plan_digest=expected_apply_plan_digest,
        )

    execute_workspace_foldered_canonical_physical_apply.__name__ = "execute_workspace_foldered_canonical_physical_apply"
    execute_workspace_foldered_canonical_physical_apply.__doc__ = (
        "Explicit-review-only foldered-canonical physical apply executor. Defaults to dry-run; apply mode requires "
        "approve_physical_apply=true, ready physical-apply preflight evidence, matching manifest dry-run / apply-plan digest, "
        "and a current backend artifact manifest. It writes a rollback checkpoint, append-only apply journal, result artifact, "
        "and updates workspace/backend-artifact-manifest.json canonical paths only in apply mode. It does not move workspace files, "
        "run pipelines, start browsers, call MCP, tighten legacy fallback, or touch mobile full runtime chains."
    )
    return execute_workspace_foldered_canonical_physical_apply


def make_plan_workspace_dual_write_pilot_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a read-only tool for limited workspace dual-write pilot planning."""

    root = Path(default_artifact_root)

    def plan_workspace_dual_write_pilot(
        artifact_root: str | None = None,
        readiness_report_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 12,
    ) -> dict[str, Any]:
        """Plan a limited dual-write pilot without enabling dual-write or writing artifacts."""

        return plan_workspace_dual_write_pilot_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            readiness_report_json=readiness_report_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
        )

    plan_workspace_dual_write_pilot.__name__ = "plan_workspace_dual_write_pilot"
    plan_workspace_dual_write_pilot.__doc__ = (
        "Read-only limited workspace dual-write pilot plan. Uses workspace migration readiness, registered workspace routes, "
        "and optional explicit artifact keys to select reviewable low-risk pilot candidates. It only returns planned legacy/future "
        "write paths and review blockers; it does not inspect files, write artifacts, create directories, enable dual-write, migrate paths, "
        "change canonical paths, start browsers, or call MCP."
    )
    return plan_workspace_dual_write_pilot


def make_review_workspace_dual_write_pilot_workflow_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a review-first workflow tool for limited workspace dual-write pilots."""

    root = Path(default_artifact_root)

    def review_workspace_dual_write_pilot_workflow(
        artifact_root: str | None = None,
        delivery_source_audit_json: str | None = None,
        readiness_report_json: str | None = None,
        artifact_keys_json: str | None = None,
        max_artifacts: int = 12,
        pilot_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Prepare and optionally verify a reviewed dual-write pilot workflow."""

        return review_workspace_dual_write_pilot_workflow_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            delivery_source_audit_json=delivery_source_audit_json,
            readiness_report_json=readiness_report_json,
            artifact_keys_json=artifact_keys_json,
            max_artifacts=max_artifacts,
            pilot_plan_json=pilot_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    review_workspace_dual_write_pilot_workflow.__name__ = "review_workspace_dual_write_pilot_workflow"
    review_workspace_dual_write_pilot_workflow.__doc__ = (
        "Compose workspace migration readiness, limited dual-write pilot planning, and optional observed-result verification "
        "into a single review workflow. It does not run the pipeline, enable dual-write, migrate paths, change canonical paths, "
        "start browsers, call MCP, or touch mobile runtimes. When write_result=true it only writes the pilot result audit artifact."
    )
    return review_workspace_dual_write_pilot_workflow


def make_record_workspace_dual_write_pilot_result_tool(default_artifact_root: str | Path) -> ArtifactTool:
    """Create a tool that inspects or records a limited workspace dual-write pilot result."""

    root = Path(default_artifact_root)

    def record_workspace_dual_write_pilot_result(
        artifact_root: str | None = None,
        pilot_plan_json: str | None = None,
        workspace_dual_write_plan_json: str | None = None,
        workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Inspect observed dual-write files and optionally write a pilot result audit artifact."""

        return record_workspace_dual_write_pilot_result_payload(
            default_artifact_root=root,
            artifact_root=artifact_root,
            pilot_plan_json=pilot_plan_json,
            workspace_dual_write_plan_json=workspace_dual_write_plan_json,
            workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
            write_result=write_result,
        )

    record_workspace_dual_write_pilot_result.__name__ = "record_workspace_dual_write_pilot_result"
    record_workspace_dual_write_pilot_result.__doc__ = (
        "Inspect the output of an explicit workspace dual-write run against a reviewed pilot plan. "
        "By default it is read-only and only checks legacy/future file presence and digests. "
        "When write_result=true it writes only workspace/workspace-dual-write-pilot-result.json; "
        "it never enables dual-write, migrates paths, changes canonical paths, starts browsers, calls MCP, or touches mobile runtimes."
    )
    return record_workspace_dual_write_pilot_result


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


def assess_workspace_migration_readiness_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    delivery_source_audit_json: str | None = None,
) -> dict[str, Any]:
    """Return a read-only migration readiness report for workspace path evolution."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    consumer_audit = audit_workspace_artifact_consumers_payload()
    consumers = consumer_audit["consumers"]
    resolver_ready = [item for item in consumers if item["resolver_status"] == "resolver-ready"]
    partial = [item for item in consumers if item["resolver_status"] == "partial"]
    candidates = [item for item in consumers if item["resolver_status"] == "candidate"]
    explicit_boundaries = [item for item in consumers if item["resolver_status"] == "explicit-filesystem-boundary"]
    delivery_source_audit = _parse_delivery_source_audit(delivery_source_audit_json)
    delivery_source_summary = _summarize_delivery_source_audit_payload(delivery_source_audit)
    registered_routes = default_workspace_artifact_routes()

    limited_dual_write_blockers: list[str] = []
    if candidates:
        limited_dual_write_blockers.append("candidate_consumers_require_resolver_adoption")
    if not resolver_ready:
        limited_dual_write_blockers.append("no_resolver_ready_consumers")
    limited_dual_write_status = "ready_for_review" if not limited_dual_write_blockers else "blocked"

    foldered_blockers: list[str] = []
    if partial:
        foldered_blockers.append("partial_consumers_still_present")
    if candidates:
        foldered_blockers.append("candidate_consumers_require_resolver_adoption")
    if delivery_source_audit is None:
        foldered_blockers.append("delivery_source_audit_evidence_missing")
    elif delivery_source_summary["malformed"]:
        foldered_blockers.append("delivery_source_audit_malformed")
    elif delivery_source_summary["source_path_count"] > 0:
        foldered_blockers.append("source_path_usage_observed")
    if delivery_source_summary["external_source_path_count"] > 0:
        foldered_blockers.append("external_source_path_usage_observed")
    foldered_canonical_status = "ready_for_review" if not foldered_blockers else "blocked"

    return {
        "schema_version": "reverse-deepagent.workspace-migration-readiness.v1",
        "status": "review",
        "artifact_root": str(effective_root),
        "summary": {
            "consumer_count": consumer_audit["summary"]["consumer_count"],
            "resolver_ready_count": len(resolver_ready),
            "partial_count": len(partial),
            "candidate_count": len(candidates),
            "explicit_filesystem_boundary_count": len(explicit_boundaries),
            "registered_workspace_route_count": len(registered_routes),
            "delivery_source_audit_observed": delivery_source_audit is not None,
            "limited_dual_write_pilot_status": limited_dual_write_status,
            "foldered_canonical_migration_status": foldered_canonical_status,
            "mobile_full_runtime_chains_deferred": True,
        },
        "consumer_readiness": {
            "resolver_ready_consumers": [item["consumer_id"] for item in resolver_ready],
            "partial_consumers": [item["consumer_id"] for item in partial],
            "candidate_consumers": [item["consumer_id"] for item in candidates],
            "explicit_filesystem_boundaries": [item["consumer_id"] for item in explicit_boundaries],
        },
        "delivery_source_audit": delivery_source_summary,
        "migration_readiness": {
            "limited_dual_write_pilot": {
                "status": limited_dual_write_status,
                "blocking_reasons": limited_dual_write_blockers,
                "allowed_scope": "registered-workspace-artifacts-only",
                "requires_explicit_opt_in": True,
                "keeps_legacy_canonical_path": True,
                "writes_future_foldered_copy": limited_dual_write_status == "ready_for_review",
                "review_required": True,
            },
            "foldered_canonical_migration": {
                "status": foldered_canonical_status,
                "blocking_reasons": foldered_blockers,
                "requires_no_partial_consumers": True,
                "requires_delivery_source_audit_without_source_path_usage": True,
                "keeps_explicit_filesystem_boundaries": True,
                "review_required": True,
            },
        },
        "recommended_next_actions": _workspace_migration_next_actions(
            limited_dual_write_blockers=limited_dual_write_blockers,
            foldered_blockers=foldered_blockers,
            delivery_source_audit_present=delivery_source_audit is not None,
        ),
        "source_evidence": {
            "consumer_audit_schema_version": consumer_audit["schema_version"],
            "delivery_source_audit_schema_version": delivery_source_summary["schema_version"],
        },
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def assess_workspace_consumer_readiness_score_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_report_json: str | None = None,
    pilot_result_json: str | None = None,
    delivery_source_audit_json: str | None = None,
) -> dict[str, Any]:
    """Return a read-only score for workspace consumer migration readiness."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    consumer_audit = audit_workspace_artifact_consumers_payload()
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(
            default_artifact_root=effective_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )
    pilot_result, pilot_result_error = _parse_json_object(pilot_result_json, field_name="pilot_result_json")
    consumer_summary = _workspace_consumer_score_summary(consumer_audit)
    readiness_summary = _compact_readiness_summary(readiness_report)
    delivery_source_summary = _score_delivery_source_summary(readiness_report)
    pilot_evidence = _workspace_pilot_result_score(pilot_result, pilot_result_error)
    scoring = _workspace_consumer_scoring(
        consumer_summary=consumer_summary,
        readiness_summary=readiness_summary,
        delivery_source_summary=delivery_source_summary,
        pilot_evidence=pilot_evidence,
    )
    readiness = _workspace_consumer_readiness_decision(scoring, readiness_summary, delivery_source_summary, pilot_evidence)
    return {
        "schema_version": "reverse-deepagent.workspace-consumer-readiness-score.v1",
        "status": readiness["status"],
        "artifact_root": str(effective_root),
        "summary": {
            "overall_score": scoring["overall_score"],
            "overall_label": scoring["overall_label"],
            "consumer_count": consumer_summary["consumer_count"],
            "resolver_ready_count": consumer_summary["resolver_ready_count"],
            "partial_count": consumer_summary["partial_count"],
            "candidate_count": consumer_summary["candidate_count"],
            "explicit_filesystem_boundary_count": consumer_summary["explicit_filesystem_boundary_count"],
            "limited_dual_write_pilot_status": readiness_summary["limited_dual_write_pilot_status"],
            "foldered_canonical_migration_status": readiness_summary["foldered_canonical_migration_status"],
            "pilot_result_status": pilot_evidence["status"],
            "blocking_reason_count": len(readiness["blocking_reasons"]),
            "warning_count": len(readiness["warnings"]),
            "review_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "scores": scoring["scores"],
        "consumer_audit_summary": consumer_summary,
        "migration_readiness_summary": readiness_summary,
        "delivery_source_audit_summary": delivery_source_summary,
        "pilot_evidence": pilot_evidence,
        "readiness": readiness,
        "blocking_reasons": readiness["blocking_reasons"],
        "warnings": readiness["warnings"],
        "recommended_next_actions": readiness["recommended_next_actions"],
        "source_evidence": {
            "consumer_audit_schema_version": consumer_audit.get("schema_version") or "",
            "migration_readiness_schema_version": readiness_report.get("schema_version") or "",
            "pilot_result_schema_version": pilot_evidence.get("schema_version") or "missing",
            "delivery_source_audit_status": delivery_source_summary["status"],
        },
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _workspace_consumer_score_summary(consumer_audit: dict[str, Any]) -> dict[str, Any]:
    consumers = consumer_audit.get("consumers") if isinstance(consumer_audit.get("consumers"), list) else []
    by_status = consumer_audit.get("summary", {}).get("by_status") if isinstance(consumer_audit.get("summary"), dict) else {}
    if not isinstance(by_status, dict):
        by_status = {}
    consumer_count = len(consumers)
    resolver_ready_count = _safe_int(by_status.get("resolver-ready"))
    partial_count = _safe_int(by_status.get("partial"))
    candidate_count = _safe_int(by_status.get("candidate"))
    explicit_boundary_count = _safe_int(by_status.get("explicit-filesystem-boundary"))
    non_workspace_count = _safe_int(by_status.get("non-workspace-input"))
    migration_relevant_count = resolver_ready_count + partial_count + candidate_count
    unresolved_count = partial_count + candidate_count
    resolver_ready_ratio = round(resolver_ready_count / migration_relevant_count, 4) if migration_relevant_count else 0.0
    return {
        "consumer_count": consumer_count,
        "migration_relevant_count": migration_relevant_count,
        "resolver_ready_count": resolver_ready_count,
        "partial_count": partial_count,
        "candidate_count": candidate_count,
        "unresolved_consumer_count": unresolved_count,
        "explicit_filesystem_boundary_count": explicit_boundary_count,
        "non_workspace_input_count": non_workspace_count,
        "resolver_ready_ratio": resolver_ready_ratio,
        "by_status": dict(sorted(by_status.items())),
    }


def _score_delivery_source_summary(readiness_report: dict[str, Any]) -> dict[str, Any]:
    payload = readiness_report.get("delivery_source_audit") if isinstance(readiness_report.get("delivery_source_audit"), dict) else {}
    if not payload:
        return {
            "schema_version": "missing",
            "status": "missing",
            "source_path_count": 0,
            "workspace_resolved_count": 0,
            "external_source_path_count": 0,
            "source_path_risk": "unknown",
        }
    source_path_count = _safe_int(payload.get("source_path_count"))
    external_count = _safe_int(payload.get("external_source_path_count"))
    risk = "none" if source_path_count == 0 and external_count == 0 else "observed"
    return {
        "schema_version": payload.get("schema_version") or "unknown",
        "status": payload.get("status") or "unknown",
        "source_path_count": source_path_count,
        "workspace_resolved_count": _safe_int(payload.get("workspace_resolved_count")),
        "external_source_path_count": external_count,
        "legacy_source_path_count": _safe_int(payload.get("legacy_source_path_count")),
        "future_source_path_count": _safe_int(payload.get("future_source_path_count")),
        "artifact_root_relative_source_path_count": _safe_int(payload.get("artifact_root_relative_source_path_count")),
        "relative_source_path_count": _safe_int(payload.get("relative_source_path_count")),
        "source_path_risk": risk,
    }


def _workspace_pilot_result_score(pilot_result: dict[str, Any] | None, pilot_result_error: str) -> dict[str, Any]:
    if pilot_result_error:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "score": 0.0,
            "verified_candidate_count": 0,
            "planned_candidate_count": 0,
            "blocking_reasons": ["pilot_result_json_malformed"],
            "warnings": [],
            "error": pilot_result_error,
        }
    if not pilot_result:
        return {
            "schema_version": "missing",
            "status": "not_observed",
            "score": 0.0,
            "verified_candidate_count": 0,
            "planned_candidate_count": 0,
            "blocking_reasons": [],
            "warnings": ["dual_write_pilot_result_not_provided"],
        }
    summary = pilot_result.get("summary") if isinstance(pilot_result.get("summary"), dict) else {}
    status = str(pilot_result.get("status") or "unknown")
    planned = _safe_int(summary.get("planned_candidate_count"))
    verified = _safe_int(summary.get("verified_candidate_count"))
    if status == "verified" and planned and verified >= planned:
        score = 1.0
    elif status in {"partial", "verified"} and planned:
        score = round(max(0.0, min(1.0, verified / planned)), 4)
    elif status == "not_run":
        score = 0.0
    else:
        score = 0.0
    blockers = pilot_result.get("blocking_reasons") if isinstance(pilot_result.get("blocking_reasons"), list) else []
    warnings = pilot_result.get("warnings") if isinstance(pilot_result.get("warnings"), list) else []
    return {
        "schema_version": pilot_result.get("schema_version") or "unknown",
        "status": status,
        "score": score,
        "verified_candidate_count": verified,
        "planned_candidate_count": planned,
        "blocking_reasons": [str(item) for item in blockers],
        "warnings": [str(item) for item in warnings],
    }


def _workspace_consumer_scoring(
    *,
    consumer_summary: dict[str, Any],
    readiness_summary: dict[str, Any],
    delivery_source_summary: dict[str, Any],
    pilot_evidence: dict[str, Any],
) -> dict[str, Any]:
    migration_relevant = consumer_summary["migration_relevant_count"]
    resolver_adoption = consumer_summary["resolver_ready_ratio"] if migration_relevant else 0.0
    virtual_uri_adoption = resolver_adoption
    future_path_readiness = 1.0 if readiness_summary["limited_dual_write_pilot_status"] == "ready_for_review" else 0.0
    source_path_risk_score = 1.0 if delivery_source_summary["source_path_risk"] == "none" else 0.0
    if delivery_source_summary["status"] == "missing":
        source_path_risk_score = 0.25
    pilot_score = float(pilot_evidence.get("score") or 0.0)
    foldered_canonical = 1.0 if readiness_summary["foldered_canonical_migration_status"] == "ready_for_review" else 0.0
    scores = {
        "resolver_adoption": round(resolver_adoption, 4),
        "virtual_uri_adoption": round(virtual_uri_adoption, 4),
        "future_path_readiness": round(future_path_readiness, 4),
        "source_path_risk": round(source_path_risk_score, 4),
        "dual_write_pilot_evidence": round(pilot_score, 4),
        "foldered_canonical_readiness": round(foldered_canonical, 4),
    }
    overall = round(
        scores["resolver_adoption"] * 0.30
        + scores["virtual_uri_adoption"] * 0.10
        + scores["future_path_readiness"] * 0.20
        + scores["source_path_risk"] * 0.15
        + scores["dual_write_pilot_evidence"] * 0.15
        + scores["foldered_canonical_readiness"] * 0.10,
        4,
    )
    if overall >= 0.86:
        label = "ready_for_foldered_canonical_review"
    elif overall >= 0.62:
        label = "ready_for_limited_dual_write_review"
    elif overall >= 0.40:
        label = "needs_targeted_resolver_adoption"
    else:
        label = "blocked"
    return {"scores": scores, "overall_score": overall, "overall_label": label}


def _workspace_consumer_readiness_decision(
    scoring: dict[str, Any],
    readiness_summary: dict[str, Any],
    delivery_source_summary: dict[str, Any],
    pilot_evidence: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    scores = scoring["scores"]
    if scores["resolver_adoption"] < 1.0:
        blockers.append("resolver_adoption_incomplete")
    if readiness_summary["limited_dual_write_pilot_status"] != "ready_for_review":
        blockers.append("limited_dual_write_pilot_not_ready")
    if delivery_source_summary["status"] == "missing":
        warnings.append("delivery_source_audit_missing")
    if delivery_source_summary["source_path_count"] > 0:
        blockers.append("source_path_usage_observed")
    if delivery_source_summary["external_source_path_count"] > 0:
        blockers.append("external_source_path_usage_observed")
    if pilot_evidence["status"] in {"malformed", "blocked"}:
        blockers.append("dual_write_pilot_result_not_usable")
    elif pilot_evidence["status"] == "not_observed":
        warnings.append("dual_write_pilot_result_not_observed")
    elif pilot_evidence["score"] < 1.0:
        warnings.append("dual_write_pilot_not_fully_verified")
    foldered_ready = readiness_summary["foldered_canonical_migration_status"] == "ready_for_review"
    if foldered_ready and pilot_evidence["score"] >= 1.0 and not blockers:
        status = "ready_for_foldered_canonical_review"
    elif readiness_summary["limited_dual_write_pilot_status"] == "ready_for_review" and "limited_dual_write_pilot_not_ready" not in blockers:
        status = "ready_for_limited_dual_write_review"
    else:
        status = "blocked"
    actions = _workspace_consumer_score_next_actions(status, blockers, warnings, pilot_evidence)
    return {
        "status": status,
        "review_required": True,
        "foldered_canonical_migration_allowed": status == "ready_for_foldered_canonical_review",
        "limited_dual_write_expansion_review_allowed": status in {"ready_for_limited_dual_write_review", "ready_for_foldered_canonical_review"},
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": actions,
    }


def _workspace_consumer_score_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
    pilot_evidence: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if "resolver_adoption_incomplete" in blockers:
        actions.append("close_partial_or_candidate_workspace_consumers_before_foldered_canonical_migration")
    if "limited_dual_write_pilot_not_ready" in blockers:
        actions.append("resolve_workspace_migration_readiness_blockers_before_dual_write_expansion")
    if "source_path_usage_observed" in blockers:
        actions.append("replace_workspace_source_path_inputs_with_artifact_ref_where_possible")
    if "external_source_path_usage_observed" in blockers:
        actions.append("keep_external_filesystem_sources_as_explicit_delivery_boundaries")
    if "delivery_source_audit_missing" in warnings:
        actions.append("run_execute_local_delivery_dry_run_and_collect_delivery_artifact_source_audit")
    if pilot_evidence["status"] == "not_observed":
        actions.append("run_reviewed_scoped_dual_write_pilot_and_record_result_before_foldered_canonical_review")
    if "dual_write_pilot_not_fully_verified" in warnings:
        actions.append("resolve_dual_write_pilot_verification_gaps_before_expansion")
    if status == "ready_for_limited_dual_write_review":
        actions.append("review_opt_in_dual_write_expansion_scope_using_low_risk_artifact_keys")
    if status == "ready_for_foldered_canonical_review":
        actions.append("review_narrow_foldered_canonical_migration_pilot")
    if not actions:
        actions.append("resolve_workspace_consumer_readiness_blockers")
    return actions


def plan_workspace_dual_write_expansion_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_score_json: str | None = None,
    readiness_report_json: str | None = None,
    pilot_result_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 24,
    include_medium_risk: bool = False,
) -> dict[str, Any]:
    """Return a review-only opt-in dual-write expansion plan."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_score, readiness_score_error = _load_or_compute_workspace_consumer_readiness_score(
        default_artifact_root=effective_root,
        readiness_score_json=readiness_score_json,
        readiness_report_json=readiness_report_json,
        pilot_result_json=pilot_result_json,
    )
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    explicit_selection = requested_keys is not None
    max_count = max(0, int(max_artifacts))
    routes = list(default_workspace_artifact_routes())
    routes_by_key = {route.artifact_key: route for route in routes}
    resolver = WorkspacePathResolver(enable_dual_write=True)

    selected_routes: list[Any] = []
    unknown_keys: list[str] = []
    if explicit_selection:
        for key in requested_keys or []:
            route = routes_by_key.get(key)
            if route is None:
                unknown_keys.append(key)
                continue
            selected_routes.append(route)
        if max_count:
            selected_routes = selected_routes[:max_count]
    else:
        for route in routes:
            risk = _dual_write_route_risk(route)
            if risk["risk_level"] == "low" or (include_medium_risk and risk["risk_level"] == "medium"):
                selected_routes.append(route)
            if max_count and len(selected_routes) >= max_count:
                break
    if max_count == 0:
        selected_routes = []

    candidate_artifacts: list[dict[str, Any]] = []
    high_risk_requested: list[str] = []
    medium_risk_selected: list[str] = []
    for route in selected_routes:
        risk = _dual_write_route_risk(route)
        if risk["risk_level"] == "high":
            high_risk_requested.append(route.artifact_key)
        if risk["risk_level"] == "medium":
            medium_risk_selected.append(route.artifact_key)
        plan = resolver.plan_dual_write(route.artifact_key)
        candidate_artifacts.append(
            {
                "artifact_key": route.artifact_key,
                "legacy_path": route.legacy_path,
                "future_path": route.future_path,
                "virtual_uri": plan.get("virtual_uri"),
                "category": route.category,
                "producer_roles": list(route.producer_roles),
                "risk": risk,
                "dual_write_plan": plan,
                "review_required": True,
                "expansion_only": True,
            }
        )

    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    pilot_evidence = readiness_score.get("pilot_evidence") if isinstance(readiness_score.get("pilot_evidence"), dict) else {}
    readiness_status = str(readiness_score.get("status") or "blocked")
    pilot_score = float(pilot_evidence.get("score") or 0.0)
    blockers: list[str] = []
    warnings: list[str] = []
    if readiness_score_error:
        blockers.append("workspace_consumer_readiness_score_malformed")
    if not bool(readiness.get("limited_dual_write_expansion_review_allowed")):
        blockers.append("workspace_consumer_readiness_not_ready_for_expansion")
    if pilot_score < 1.0:
        blockers.append("verified_dual_write_pilot_result_required_before_expansion")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if high_risk_requested:
        blockers.append("high_risk_requested_artifacts_require_separate_review")
    if medium_risk_selected and not include_medium_risk:
        blockers.append("medium_risk_artifacts_require_explicit_include_medium_risk")
    if not candidate_artifacts:
        blockers.append("no_dual_write_expansion_candidates_selected")
    if medium_risk_selected and include_medium_risk:
        warnings.append("medium_risk_artifacts_selected_for_explicit_review")
    if readiness_status == "ready_for_limited_dual_write_review" and pilot_score >= 1.0:
        warnings.append("foldered_canonical_migration_still_requires_separate_review")
    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_artifacts),
            "readiness_score_status": readiness_status,
            "readiness_score_overall": readiness_score.get("summary", {}).get("overall_score") if isinstance(readiness_score.get("summary"), dict) else None,
            "pilot_result_status": pilot_evidence.get("status") or "missing",
            "pilot_evidence_score": pilot_score,
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "high_risk_requested_artifact_count": len(high_risk_requested),
            "medium_risk_selected_artifact_count": len(medium_risk_selected),
            "explicit_selection": explicit_selection,
            "max_artifacts": max_count,
            "review_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_risk_level": "low",
            "default_allows_medium_risk": False,
            "include_medium_risk_requested": bool(include_medium_risk),
            "requires_workspace_consumer_readiness_score": True,
            "requires_verified_dual_write_pilot_result": True,
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "actual_dual_write_enabled": False,
        },
        "readiness_score_summary": _compact_workspace_consumer_score(readiness_score),
        "candidate_artifacts": candidate_artifacts,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "high_risk_requested_artifact_keys": high_risk_requested,
            "medium_risk_selected_artifact_keys": medium_risk_selected,
        },
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_expansion_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_compute_workspace_consumer_readiness_score(
    *,
    default_artifact_root: Path,
    readiness_score_json: str | None,
    readiness_report_json: str | None,
    pilot_result_json: str | None,
) -> tuple[dict[str, Any], str]:
    payload, error = _parse_json_object(readiness_score_json, field_name="readiness_score_json")
    if payload is not None or error:
        if payload is not None:
            return payload, ""
        return {
            "schema_version": "invalid-json",
            "status": "blocked",
            "summary": {"overall_score": 0.0},
            "readiness": {"limited_dual_write_expansion_review_allowed": False},
            "pilot_evidence": {"status": "malformed", "score": 0.0},
        }, error
    return assess_workspace_consumer_readiness_score_payload(
        default_artifact_root=default_artifact_root,
        readiness_report_json=readiness_report_json,
        pilot_result_json=pilot_result_json,
    ), ""


def _compact_workspace_consumer_score(readiness_score: dict[str, Any]) -> dict[str, Any]:
    summary = readiness_score.get("summary") if isinstance(readiness_score.get("summary"), dict) else {}
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    pilot = readiness_score.get("pilot_evidence") if isinstance(readiness_score.get("pilot_evidence"), dict) else {}
    return {
        "schema_version": readiness_score.get("schema_version") or "",
        "status": readiness_score.get("status") or "blocked",
        "overall_score": summary.get("overall_score"),
        "overall_label": summary.get("overall_label"),
        "limited_dual_write_expansion_review_allowed": bool(readiness.get("limited_dual_write_expansion_review_allowed")),
        "foldered_canonical_migration_allowed": bool(readiness.get("foldered_canonical_migration_allowed")),
        "pilot_result_status": pilot.get("status") or "missing",
        "pilot_evidence_score": float(pilot.get("score") or 0.0),
        "blocking_reasons": readiness_score.get("blocking_reasons") if isinstance(readiness_score.get("blocking_reasons"), list) else [],
        "warnings": readiness_score.get("warnings") if isinstance(readiness_score.get("warnings"), list) else [],
    }


def _workspace_dual_write_expansion_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_consumer_readiness_score_malformed" in blockers:
        actions.append("fix_readiness_score_json_or_omit_it_to_recompute_score")
    if "workspace_consumer_readiness_not_ready_for_expansion" in blockers:
        actions.append("resolve_workspace_consumer_readiness_blockers_before_expansion")
    if "verified_dual_write_pilot_result_required_before_expansion" in blockers:
        actions.append("run_and_record_verified_scoped_dual_write_pilot_before_expansion")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_expansion_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_or_register_unknown_artifact_keys")
    if "high_risk_requested_artifacts_require_separate_review" in blockers:
        actions.append("split_high_risk_delivery_or_transaction_artifacts_into_separate_manual_review")
    if "medium_risk_artifacts_require_explicit_include_medium_risk" in blockers:
        actions.append("set_include_medium_risk_only_after_explicit_review")
    if "no_dual_write_expansion_candidates_selected" in blockers:
        actions.append("select_reviewed_low_risk_workspace_artifact_keys_for_expansion")
    if not blockers:
        actions.append("review_expansion_plan_then_run_pipeline_with_scoped_workspace_dual_write_keys")
    if "foldered_canonical_migration_still_requires_separate_review" in warnings:
        actions.append("keep_foldered_canonical_migration_as_separate_pilot_after_expansion_evidence")
    return actions


def review_workspace_dual_write_expansion_workflow_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    expansion_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Review opt-in dual-write expansion readiness and observed evidence."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    expansion_plan, expansion_plan_error = _load_or_compute_workspace_dual_write_expansion_plan(
        default_artifact_root=effective_root,
        expansion_plan_json=expansion_plan_json,
    )
    expansion_result = record_workspace_dual_write_expansion_result_payload(
        default_artifact_root=effective_root,
        expansion_plan_json=json.dumps(expansion_plan) if isinstance(expansion_plan, dict) else None,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
        write_result=write_result,
    )
    status = _workspace_dual_write_expansion_workflow_status(expansion_plan, expansion_result, expansion_plan_error)
    blockers = _workspace_dual_write_expansion_workflow_blockers(expansion_plan, expansion_result, expansion_plan_error, status)
    warnings = _workspace_dual_write_expansion_workflow_warnings(expansion_plan, expansion_result)
    candidate_keys = [item["artifact_key"] for item in _planned_dual_write_candidates(expansion_plan if isinstance(expansion_plan, dict) else {})]
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-workflow.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "expansion_plan_status": expansion_plan.get("status") if isinstance(expansion_plan, dict) else "malformed",
            "expansion_result_status": expansion_result.get("status") or "unknown",
            "candidate_count": len(candidate_keys),
            "verified_candidate_count": _safe_int((expansion_result.get("summary") or {}).get("verified_candidate_count")) if isinstance(expansion_result.get("summary"), dict) else 0,
            "write_result_requested": bool(write_result),
            "legacy_canonical_path_remains_authoritative": True,
            "foldered_canonical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "expansion_plan_summary": _compact_expansion_plan_summary(expansion_plan if isinstance(expansion_plan, dict) else {}),
        "expansion_result": expansion_result,
        "blocking_reasons": blockers,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_expansion_workflow_next_actions(status, expansion_result),
        "review_workflow": _workspace_dual_write_expansion_review_workflow(
            candidate_keys=candidate_keys,
            result_status=str(expansion_result.get("status") or "unknown"),
            workflow_status=status,
            write_result=write_result,
        ),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def record_workspace_dual_write_expansion_result_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    expansion_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Inspect an explicit expansion dual-write run and optionally record a result artifact."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    expansion_plan, expansion_plan_error = _load_or_compute_workspace_dual_write_expansion_plan(
        default_artifact_root=effective_root,
        expansion_plan_json=expansion_plan_json,
    )
    observed_plan, observed_plan_error, observed_input = _load_observed_dual_write_plan(
        default_artifact_root=effective_root,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
    )
    planned_candidates = _planned_dual_write_candidates(expansion_plan if isinstance(expansion_plan, dict) else {})
    observed_records = _observed_dual_write_records(observed_plan if isinstance(observed_plan, dict) else {})
    observed_by_key = {str(record.get("artifact_key") or ""): record for record in observed_records if record.get("artifact_key")}

    candidate_results: list[dict[str, Any]] = []
    verified_count = 0
    missing_legacy_count = 0
    missing_future_count = 0
    digest_mismatch_count = 0
    not_observed_count = 0
    for candidate in planned_candidates:
        result = _dual_write_candidate_result(effective_root, candidate, observed_by_key.get(candidate["artifact_key"]))
        candidate_results.append(result)
        status = result["status"]
        if status == "verified_dual_written":
            verified_count += 1
        if status == "missing_legacy":
            missing_legacy_count += 1
        if status == "missing_future":
            missing_future_count += 1
        if status == "digest_mismatch":
            digest_mismatch_count += 1
        if status == "not_observed":
            not_observed_count += 1

    planned_keys = {item["artifact_key"] for item in planned_candidates}
    out_of_scope_observed, high_risk_observed, medium_risk_observed = _classify_observed_dual_write_scope(
        observed_records=observed_records,
        planned_keys=planned_keys,
        self_artifact_keys={"workspace_dual_write_expansion_result", "workspace_dual_write_expansion_workflow"},
    )

    blocking_reasons: list[str] = []
    warnings: list[str] = []
    if expansion_plan_error:
        blocking_reasons.append("expansion_plan_json_malformed")
    if isinstance(expansion_plan, dict) and expansion_plan.get("status") == "blocked":
        blocking_reasons.append("workspace_dual_write_expansion_plan_not_ready")
    if isinstance(expansion_plan, dict):
        for reason in expansion_plan.get("blocking_reasons") or []:
            blocking_reasons.append(f"expansion_plan:{reason}")
    if observed_plan_error:
        blocking_reasons.append("workspace_dual_write_plan_unavailable_or_malformed")
    if not observed_records:
        blocking_reasons.append("workspace_dual_write_plan_not_observed")
    if not planned_candidates:
        blocking_reasons.append("expansion_plan_has_no_candidates")
    if missing_legacy_count:
        blocking_reasons.append("candidate_legacy_files_missing")
    if missing_future_count:
        blocking_reasons.append("candidate_future_files_missing")
    if digest_mismatch_count:
        blocking_reasons.append("candidate_digest_mismatch")
    if not_observed_count:
        warnings.append("some_planned_candidates_not_seen_in_workspace_dual_write_plan")
    if out_of_scope_observed:
        warnings.append("observed_dual_write_records_outside_expansion_plan")
    if high_risk_observed:
        warnings.append("high_risk_artifacts_observed_in_dual_write_output")
    if medium_risk_observed:
        warnings.append("medium_risk_artifacts_observed_in_dual_write_output")

    if observed_plan_error or not observed_records:
        status = "not_run"
    elif blocking_reasons:
        status = "blocked"
    elif verified_count == len(planned_candidates) and not out_of_scope_observed and not high_risk_observed:
        status = "verified"
    else:
        status = "partial"

    result_artifact = _workspace_expansion_result_artifact_metadata(effective_root, written=False)
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-dual-write-expansion-result.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "result_artifact": result_artifact,
        "summary": {
            "planned_candidate_count": len(planned_candidates),
            "observed_write_record_count": len(observed_records),
            "verified_candidate_count": verified_count,
            "missing_legacy_count": missing_legacy_count,
            "missing_future_count": missing_future_count,
            "digest_mismatch_count": digest_mismatch_count,
            "not_observed_candidate_count": not_observed_count,
            "out_of_scope_observed_count": len(out_of_scope_observed),
            "high_risk_observed_count": len(high_risk_observed),
            "medium_risk_observed_count": len(medium_risk_observed),
            "legacy_canonical_path_remains_authoritative": True,
            "foldered_canonical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "expansion_plan_summary": _compact_expansion_plan_summary(expansion_plan if isinstance(expansion_plan, dict) else {}),
        "observed_dual_write_plan_input": observed_input,
        "candidate_results": candidate_results,
        "out_of_scope_observed_artifacts": out_of_scope_observed,
        "high_risk_observed_artifacts": high_risk_observed,
        "medium_risk_observed_artifacts": medium_risk_observed,
        "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _dual_write_expansion_result_next_actions(status, blocking_reasons, warnings),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if write_result:
        result_path = effective_root / "workspace" / "workspace-dual-write-expansion-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_expansion_result_artifact_metadata(effective_root, written=True)
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_compute_workspace_dual_write_expansion_plan(*, default_artifact_root: Path, expansion_plan_json: str | None) -> tuple[dict[str, Any], str]:
    payload, error = _parse_json_object(expansion_plan_json, field_name="expansion_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, ""
        return {
            "schema_version": "invalid-json",
            "status": "blocked",
            "summary": {"candidate_count": 0},
            "candidate_artifacts": [],
            "blocking_reasons": ["expansion_plan_json_malformed"],
            "warnings": [],
        }, error
    return plan_workspace_dual_write_expansion_payload(default_artifact_root=default_artifact_root), ""


def _compact_expansion_plan_summary(expansion_plan: dict[str, Any]) -> dict[str, Any]:
    summary = expansion_plan.get("summary") if isinstance(expansion_plan.get("summary"), dict) else {}
    selection_policy = expansion_plan.get("selection_policy") if isinstance(expansion_plan.get("selection_policy"), dict) else {}
    return {
        "schema_version": expansion_plan.get("schema_version") or "",
        "status": expansion_plan.get("status") or "",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "explicit_selection": bool(summary.get("explicit_selection")),
        "pilot_result_status": summary.get("pilot_result_status") or "",
        "pilot_evidence_score": float(summary.get("pilot_evidence_score") or 0.0),
        "legacy_canonical_path_remains_authoritative": bool(selection_policy.get("legacy_canonical_path_remains_authoritative", True)),
        "physical_migration_enabled": bool(selection_policy.get("physical_migration_enabled", False)),
        "actual_dual_write_enabled": bool(selection_policy.get("actual_dual_write_enabled", False)),
    }


def _workspace_expansion_result_artifact_metadata(artifact_root: Path, *, written: bool) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_dual_write_expansion_result",
        "legacy_path": "workspace/workspace-dual-write-expansion-result.json",
        "future_path": "/workspace/review/workspace-dual-write-expansion-result.json",
        "path": str(artifact_root / "workspace" / "workspace-dual-write-expansion-result.json"),
        "written": written,
        "canonical_path_remains_authoritative": True,
    }


def _classify_observed_dual_write_scope(
    *,
    observed_records: list[dict[str, Any]],
    planned_keys: set[str],
    self_artifact_keys: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    out_of_scope_observed: list[dict[str, Any]] = []
    high_risk_observed: list[dict[str, Any]] = []
    medium_risk_observed: list[dict[str, Any]] = []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    for record in observed_records:
        key = str(record.get("artifact_key") or "")
        if not key or key in self_artifact_keys or not record.get("dual_write_enabled"):
            continue
        route = routes_by_key.get(key)
        risk = _dual_write_route_risk(route) if route is not None else {"risk_level": "unknown", "rationale": "observed artifact is not registered", "category": "unknown", "producer_roles": []}
        summary = {
            "artifact_key": key,
            "legacy_path": record.get("canonical_path") or record.get("legacy_path") or "",
            "future_path": record.get("future_path") or "",
            "write_paths": list(record.get("write_paths") or []),
            "dual_write_enabled": bool(record.get("dual_write_enabled")),
            "risk": risk,
        }
        if key not in planned_keys:
            out_of_scope_observed.append(summary)
        if risk.get("risk_level") == "high":
            high_risk_observed.append(summary)
        if risk.get("risk_level") == "medium":
            medium_risk_observed.append(summary)
    return out_of_scope_observed, high_risk_observed, medium_risk_observed


def _dual_write_expansion_result_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_dual_write_plan_unavailable_or_malformed" in blockers or "workspace_dual_write_plan_not_observed" in blockers:
        actions.append("run_pipeline_with_scoped_expansion_keys_and_capture_workspace_dual_write_plan")
    if "expansion_plan_json_malformed" in blockers:
        actions.append("fix_expansion_plan_json_or_omit_it_to_recompute_plan")
    if "workspace_dual_write_expansion_plan_not_ready" in blockers:
        actions.append("resolve_expansion_plan_blockers_before_running_pipeline")
    if "candidate_legacy_files_missing" in blockers or "candidate_future_files_missing" in blockers:
        actions.append("inspect_dual_write_expansion_output_paths_and_rerun_scoped_pipeline")
    if "candidate_digest_mismatch" in blockers:
        actions.append("compare_legacy_and_future_expansion_artifacts_before_any_migration")
    if "observed_dual_write_records_outside_expansion_plan" in warnings:
        actions.append("review_out_of_scope_observed_dual_writes_before_next_expansion")
    if "high_risk_artifacts_observed_in_dual_write_output" in warnings:
        actions.append("split_high_risk_artifacts_into_separate_manual_review")
    if status == "verified":
        actions.append("feed_verified_expansion_result_back_into_workspace_readiness_before_foldered_canonical_pilot")
    if not actions:
        actions.append("review_expansion_result_before_next_dual_write_scope")
    return actions


def _workspace_dual_write_expansion_workflow_status(expansion_plan: dict[str, Any], expansion_result: dict[str, Any], expansion_plan_error: str) -> str:
    if expansion_plan_error or expansion_plan.get("status") == "blocked":
        return "blocked"
    result_status = str(expansion_result.get("status") or "unknown")
    if result_status == "verified":
        return "verified"
    if result_status == "partial":
        return "partial"
    if result_status == "blocked":
        return "blocked"
    if result_status == "not_run":
        return "ready_for_review"
    return "ready_for_review"


def _workspace_dual_write_expansion_workflow_blockers(
    expansion_plan: dict[str, Any],
    expansion_result: dict[str, Any],
    expansion_plan_error: str,
    status: str,
) -> list[str]:
    reasons: list[str] = []
    if expansion_plan_error:
        reasons.append("expansion_plan_json_malformed")
    if expansion_plan.get("status") == "blocked":
        reasons.append("workspace_dual_write_expansion_plan_not_ready")
    for reason in expansion_plan.get("blocking_reasons") or []:
        reasons.append(f"expansion_plan:{reason}")
    if status in {"blocked", "partial"}:
        for reason in expansion_result.get("blocking_reasons") or []:
            reasons.append(f"expansion_result:{reason}")
    return list(dict.fromkeys(reasons))


def _workspace_dual_write_expansion_workflow_warnings(expansion_plan: dict[str, Any], expansion_result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    warnings.extend(f"expansion_plan:{item}" for item in expansion_plan.get("warnings") or [])
    warnings.extend(f"expansion_result:{item}" for item in expansion_result.get("warnings") or [])
    return list(dict.fromkeys(warnings))


def _workspace_dual_write_expansion_workflow_next_actions(status: str, expansion_result: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if status == "ready_for_review":
        actions.append("review_expansion_plan_then_run_explicit_scoped_dual_write_pipeline")
    if status in {"verified", "partial"}:
        actions.append("review_expansion_result_before_foldered_canonical_migration_pilot")
    if status == "verified":
        actions.append("update_consumer_readiness_with_verified_expansion_evidence")
    if status == "blocked":
        actions.append("resolve_expansion_workflow_blockers_before_running_dual_write_expansion")
    for action in expansion_result.get("recommended_next_actions") or []:
        if action not in actions:
            actions.append(action)
    return actions


def _workspace_dual_write_expansion_review_workflow(
    *,
    candidate_keys: list[str],
    result_status: str,
    workflow_status: str,
    write_result: bool,
) -> dict[str, Any]:
    key_arg = ",".join(candidate_keys)
    if workflow_status == "blocked":
        commands = [
            {
                "step": "resolve_expansion_workflow_blockers",
                "description": "Resolve expansion plan or observed-result blockers before running an opt-in dual-write expansion pipeline.",
                "requires_review": True,
                "runs_inside_this_tool": False,
            }
        ]
    else:
        commands = [
            {
                "step": "run_explicit_scoped_dual_write_expansion_pipeline",
                "description": "Run the normal pipeline separately with reviewed expansion artifact keys only.",
                "flags": [
                    "--enable-workspace-dual-write",
                    "--workspace-dual-write-artifact-keys",
                    key_arg,
                ],
                "requires_review": True,
                "runs_inside_this_tool": False,
            },
            {
                "step": "verify_observed_dual_write_expansion_output",
                "description": "Call this workflow again after the pipeline writes workspace/workspace-dual-write-plan.json, or pass workspace_dual_write_plan_json directly.",
                "tool": "review_workspace_dual_write_expansion_workflow",
                "suggested_arguments": {
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": False,
                },
                "requires_review": True,
            },
            {
                "step": "record_verified_expansion_result",
                "description": "Only after reviewing the verification payload, call with write_result=true to write the expansion audit artifact.",
                "tool": "review_workspace_dual_write_expansion_workflow",
                "suggested_arguments": {
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": True,
                },
                "requires_review": True,
                "already_requested": bool(write_result),
            },
        ]
    return {
        "requires_explicit_pipeline_run": workflow_status != "blocked",
        "requires_review_before_expansion": True,
        "requires_result_review_before_writing_audit": True,
        "workflow_status": workflow_status,
        "result_verification_status": result_status,
        "selected_artifact_keys": candidate_keys,
        "recommended_commands": commands,
        "does_not_run_pipeline": True,
        "does_not_enable_dual_write": True,
        "does_not_migrate_paths": True,
        "legacy_canonical_path_remains_authoritative": True,
    }


def plan_workspace_foldered_canonical_migration_pilot_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_score_json: str | None = None,
    readiness_report_json: str | None = None,
    pilot_result_json: str | None = None,
    expansion_result_json: str | None = None,
    expansion_result_artifact_ref: str | None = "workspace_dual_write_expansion_result",
    artifact_keys_json: str | None = None,
    max_artifacts: int = 8,
    include_medium_risk: bool = False,
) -> dict[str, Any]:
    """Return a review-only plan for a narrow foldered-canonical migration pilot."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_score, readiness_score_error = _load_or_compute_workspace_consumer_readiness_score(
        default_artifact_root=effective_root,
        readiness_score_json=readiness_score_json,
        readiness_report_json=readiness_report_json,
        pilot_result_json=pilot_result_json,
    )
    expansion_result, expansion_result_error, expansion_result_input = _load_or_read_workspace_dual_write_expansion_result(
        default_artifact_root=effective_root,
        expansion_result_json=expansion_result_json,
        expansion_result_artifact_ref=expansion_result_artifact_ref,
    )
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    explicit_selection = requested_keys is not None
    max_count = max(0, int(max_artifacts))

    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    verified_keys = _verified_expansion_result_artifact_keys(expansion_result if isinstance(expansion_result, dict) else {})
    selected_keys = requested_keys or verified_keys
    if max_count:
        selected_keys = selected_keys[:max_count]
    elif max_count == 0:
        selected_keys = []

    candidate_artifacts: list[dict[str, Any]] = []
    unknown_keys: list[str] = []
    not_verified_keys: list[str] = []
    high_risk_requested: list[str] = []
    medium_risk_selected: list[str] = []
    for key in selected_keys:
        route = routes_by_key.get(key)
        if route is None:
            unknown_keys.append(key)
            continue
        if key not in verified_keys:
            not_verified_keys.append(key)
        risk = _dual_write_route_risk(route)
        if risk["risk_level"] == "high":
            high_risk_requested.append(key)
        if risk["risk_level"] == "medium":
            medium_risk_selected.append(key)
        candidate_artifacts.append(_foldered_canonical_migration_candidate(route, risk))

    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    readiness_status = str(readiness_score.get("status") or "blocked")
    expansion_status = str(expansion_result.get("status") or "missing") if isinstance(expansion_result, dict) else "missing"
    blockers: list[str] = []
    warnings: list[str] = []
    if readiness_score_error:
        blockers.append("workspace_consumer_readiness_score_malformed")
    if not readiness.get("foldered_canonical_migration_allowed") or readiness_status != "ready_for_foldered_canonical_review":
        blockers.append("workspace_consumers_not_ready_for_foldered_canonical_migration")
    if expansion_result_error:
        blockers.append("workspace_dual_write_expansion_result_unavailable_or_malformed")
    if expansion_status != "verified":
        blockers.append("verified_workspace_dual_write_expansion_result_required")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if not_verified_keys:
        blockers.append("requested_artifacts_not_verified_by_expansion_result")
    if high_risk_requested:
        blockers.append("high_risk_requested_artifacts_require_separate_review")
    if medium_risk_selected and not include_medium_risk:
        blockers.append("medium_risk_artifacts_require_explicit_include_medium_risk")
    if not candidate_artifacts:
        blockers.append("no_foldered_canonical_migration_candidates_selected")
    if medium_risk_selected and include_medium_risk:
        warnings.append("medium_risk_artifacts_selected_for_foldered_canonical_review")
    if not blockers:
        warnings.append("canonical_path_change_requires_separate_reviewed_execution_after_pilot_plan")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-pilot-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_artifacts),
            "verified_expansion_artifact_count": len(verified_keys),
            "readiness_score_status": readiness_status,
            "expansion_result_status": expansion_status,
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "not_verified_requested_artifact_key_count": len(not_verified_keys),
            "high_risk_requested_artifact_count": len(high_risk_requested),
            "medium_risk_selected_artifact_count": len(medium_risk_selected),
            "explicit_selection": explicit_selection,
            "max_artifacts": max_count,
            "review_required": True,
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_source": "verified_expansion_result_artifact_keys",
            "requires_workspace_consumer_readiness_score": True,
            "requires_foldered_canonical_migration_allowed": True,
            "requires_verified_expansion_result": True,
            "explicit_keys_must_be_verified_by_expansion_result": True,
            "default_allows_medium_risk": False,
            "include_medium_risk_requested": bool(include_medium_risk),
            "high_risk_explicit_keys_block_plan": True,
            "legacy_canonical_path_remains_authoritative": True,
            "plan_only": True,
            "physical_migration_enabled": False,
            "actual_canonical_path_change_enabled": False,
        },
        "readiness_score_summary": _compact_workspace_consumer_score(readiness_score),
        "expansion_result_summary": _compact_workspace_dual_write_expansion_result(expansion_result if isinstance(expansion_result, dict) else {}),
        "expansion_result_input": expansion_result_input,
        "candidate_artifacts": candidate_artifacts,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "not_verified_artifact_keys": not_verified_keys,
            "high_risk_requested_artifact_keys": high_risk_requested,
            "medium_risk_selected_artifact_keys": medium_risk_selected,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_migration_pilot_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": True,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_dual_write_expansion_result(
    *,
    default_artifact_root: Path,
    expansion_result_json: str | None,
    expansion_result_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(expansion_result_json, field_name="expansion_result_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "malformed", "summary": {}}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = expansion_result_artifact_ref or "workspace_dual_write_expansion_result"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "not_observed", "summary": {}}, "workspace_dual_write_expansion_result_not_observed", input_summary


def _verified_expansion_result_artifact_keys(expansion_result: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for item in expansion_result.get("candidate_results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "verified_dual_written":
            continue
        key = str(item.get("artifact_key") or "")
        if key:
            keys.append(key)
    return list(dict.fromkeys(keys))


def _foldered_canonical_migration_candidate(route: Any, risk: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_key": route.artifact_key,
        "legacy_canonical_path": route.legacy_path,
        "current_canonical_path": route.legacy_path,
        "future_canonical_path": route.future_path,
        "future_path": route.future_path,
        "virtual_uri": workspace_virtual_uri(route.future_path),
        "virtual_folder": route.virtual_folder,
        "category": route.category,
        "producer_roles": list(route.producer_roles),
        "risk": risk,
        "migration_plan": {
            "plan_only": True,
            "review_required": True,
            "legacy_canonical_path_remains_authoritative": True,
            "future_path_candidate": route.future_path,
            "physical_migration_enabled": False,
            "canonical_path_change_enabled": False,
            "rollback_plan_required_before_execution": True,
        },
    }


def _compact_workspace_dual_write_expansion_result(expansion_result: dict[str, Any]) -> dict[str, Any]:
    summary = expansion_result.get("summary") if isinstance(expansion_result.get("summary"), dict) else {}
    return {
        "schema_version": expansion_result.get("schema_version") or "",
        "status": expansion_result.get("status") or "missing",
        "planned_candidate_count": _safe_int(summary.get("planned_candidate_count")),
        "verified_candidate_count": _safe_int(summary.get("verified_candidate_count")),
        "out_of_scope_observed_count": _safe_int(summary.get("out_of_scope_observed_count")),
        "high_risk_observed_count": _safe_int(summary.get("high_risk_observed_count")),
        "medium_risk_observed_count": _safe_int(summary.get("medium_risk_observed_count")),
        "blocking_reasons": expansion_result.get("blocking_reasons") if isinstance(expansion_result.get("blocking_reasons"), list) else [],
        "warnings": expansion_result.get("warnings") if isinstance(expansion_result.get("warnings"), list) else [],
    }


def _foldered_canonical_migration_pilot_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_consumer_readiness_score_malformed" in blockers:
        actions.append("fix_readiness_score_json_or_omit_it_to_recompute_score")
    if "workspace_consumers_not_ready_for_foldered_canonical_migration" in blockers:
        actions.append("close_resolver_adoption_and_source_path_blockers_before_foldered_canonical_pilot")
    if "workspace_dual_write_expansion_result_unavailable_or_malformed" in blockers:
        actions.append("record_verified_workspace_dual_write_expansion_result_before_migration_pilot")
    if "verified_workspace_dual_write_expansion_result_required" in blockers:
        actions.append("verify_expansion_result_before_foldered_canonical_migration_pilot")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_foldered_canonical_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_or_register_unknown_artifact_keys")
    if "requested_artifacts_not_verified_by_expansion_result" in blockers:
        actions.append("restrict_migration_pilot_to_verified_expansion_artifact_keys")
    if "high_risk_requested_artifacts_require_separate_review" in blockers:
        actions.append("split_high_risk_artifacts_out_of_foldered_canonical_pilot")
    if "medium_risk_artifacts_require_explicit_include_medium_risk" in blockers:
        actions.append("set_include_medium_risk_only_after_explicit_review")
    if "no_foldered_canonical_migration_candidates_selected" in blockers:
        actions.append("select_verified_low_risk_artifacts_for_foldered_canonical_pilot")
    if not blockers:
        actions.append("review_foldered_canonical_migration_pilot_plan_before_any_execution")
        actions.append("prepare_separate_rollback_plan_before_canonical_path_change")
    if "medium_risk_artifacts_selected_for_foldered_canonical_review" in warnings:
        actions.append("review_medium_risk_artifacts_before_foldered_canonical_pilot")
    return actions


def review_workspace_foldered_canonical_migration_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_pilot_plan_json: str | None = None,
    migration_pilot_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_pilot_plan",
) -> dict[str, Any]:
    """Inspect a foldered-canonical migration pilot plan without mutating files."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    pilot_plan, pilot_plan_error, pilot_plan_input = _load_or_read_workspace_foldered_canonical_migration_pilot_plan(
        default_artifact_root=effective_root,
        migration_pilot_plan_json=migration_pilot_plan_json,
        migration_pilot_plan_artifact_ref=migration_pilot_plan_artifact_ref,
    )
    candidates = pilot_plan.get("candidate_artifacts") if isinstance(pilot_plan.get("candidate_artifacts"), list) else []
    candidate_results: list[dict[str, Any]] = []
    ready_count = 0
    missing_legacy_count = 0
    missing_future_count = 0
    digest_mismatch_count = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        result = _foldered_canonical_preflight_candidate_result(effective_root, candidate)
        candidate_results.append(result)
        status = result["status"]
        if status == "ready_for_reviewed_execution":
            ready_count += 1
        elif status == "missing_legacy":
            missing_legacy_count += 1
        elif status == "missing_future":
            missing_future_count += 1
        elif status == "digest_mismatch":
            digest_mismatch_count += 1

    blockers: list[str] = []
    warnings: list[str] = []
    if pilot_plan_error:
        blockers.append("foldered_canonical_migration_pilot_plan_unavailable_or_malformed")
    if pilot_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_pilot_plan_not_ready")
    for reason in pilot_plan.get("blocking_reasons") or []:
        blockers.append(f"pilot_plan:{reason}")
    if not candidate_results:
        blockers.append("foldered_canonical_migration_pilot_has_no_candidates")
    if missing_legacy_count:
        blockers.append("candidate_legacy_files_missing")
    if missing_future_count:
        blockers.append("candidate_future_files_missing")
    if digest_mismatch_count:
        blockers.append("candidate_digest_mismatch")
    if any((item.get("risk") or {}).get("risk_level") == "high" for item in candidate_results):
        blockers.append("high_risk_candidate_present")
    if any((item.get("risk") or {}).get("risk_level") == "medium" for item in candidate_results):
        warnings.append("medium_risk_candidate_requires_final_review")
    if not blockers:
        warnings.append("execution_still_requires_explicit_review_and_separate_apply_step")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_results),
            "ready_candidate_count": ready_count,
            "missing_legacy_count": missing_legacy_count,
            "missing_future_count": missing_future_count,
            "digest_mismatch_count": digest_mismatch_count,
            "pilot_plan_status": pilot_plan.get("status") or "missing",
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "canonical_path_change_enabled": False,
            "review_required": True,
            "rollback_plan_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "pilot_plan_summary": _compact_foldered_canonical_migration_pilot_plan(pilot_plan),
        "pilot_plan_input": pilot_plan_input,
        "candidate_results": candidate_results,
        "rollback_plan": _foldered_canonical_preflight_rollback_plan(candidate_results),
        "execution_gate": {
            "ready_for_reviewed_execution": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_separate_apply_tool": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation": False,
            "allows_canonical_path_change_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_preflight_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": True,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_pilot_plan(
    *,
    default_artifact_root: Path,
    migration_pilot_plan_json: str | None,
    migration_pilot_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(migration_pilot_plan_json, field_name="migration_pilot_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "candidate_artifacts": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = migration_pilot_plan_artifact_ref or "workspace_foldered_canonical_migration_pilot_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing", "candidate_artifacts": []}, "foldered_canonical_migration_pilot_plan_not_observed", input_summary


def _foldered_canonical_preflight_candidate_result(artifact_root: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    legacy_path = str(candidate.get("current_canonical_path") or candidate.get("legacy_canonical_path") or "")
    future_path = str(candidate.get("future_canonical_path") or candidate.get("future_path") or "")
    legacy_file = _artifact_ref_to_filesystem_path(artifact_root, legacy_path) if legacy_path else artifact_root / ""
    future_file = _artifact_ref_to_filesystem_path(artifact_root, future_path) if future_path else artifact_root / ""
    legacy_stat = _file_digest_stat(legacy_file) if legacy_path else _missing_file_stat(legacy_file)
    future_stat = _file_digest_stat(future_file) if future_path else _missing_file_stat(future_file)
    digest_match = bool(legacy_stat.get("exists") and future_stat.get("exists") and legacy_stat.get("sha256") == future_stat.get("sha256"))
    if not legacy_stat["exists"]:
        status = "missing_legacy"
    elif not future_stat["exists"]:
        status = "missing_future"
    elif not digest_match:
        status = "digest_mismatch"
    else:
        status = "ready_for_reviewed_execution"
    return {
        "artifact_key": candidate.get("artifact_key") or "",
        "status": status,
        "current_canonical_path": legacy_path,
        "future_canonical_path": future_path,
        "virtual_uri": candidate.get("virtual_uri") or "",
        "legacy_file": legacy_stat,
        "future_file": future_stat,
        "digest_match": digest_match,
        "risk": candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {},
        "rollback_requirement": {
            "restore_canonical_path": legacy_path,
            "ignore_or_remove_future_canonical_candidate": future_path,
            "requires_manifest_alias_review": True,
            "requires_digest_snapshot": True,
            "automatic_rollback": False,
        },
        "execution_requirement": {
            "requires_explicit_review_approval": True,
            "requires_same_digest_before_execution": True,
            "requires_rollback_plan": True,
            "execute_in_this_tool": False,
        },
    }


def _compact_foldered_canonical_migration_pilot_plan(pilot_plan: dict[str, Any]) -> dict[str, Any]:
    summary = pilot_plan.get("summary") if isinstance(pilot_plan.get("summary"), dict) else {}
    return {
        "schema_version": pilot_plan.get("schema_version") or "",
        "status": pilot_plan.get("status") or "missing",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "verified_expansion_artifact_count": _safe_int(summary.get("verified_expansion_artifact_count")),
        "readiness_score_status": summary.get("readiness_score_status") or "",
        "expansion_result_status": summary.get("expansion_result_status") or "",
        "blocking_reasons": pilot_plan.get("blocking_reasons") if isinstance(pilot_plan.get("blocking_reasons"), list) else [],
        "warnings": pilot_plan.get("warnings") if isinstance(pilot_plan.get("warnings"), list) else [],
    }


def _foldered_canonical_preflight_rollback_plan(candidate_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "plan_only": True,
        "rollback_required_before_execution": True,
        "automatic_rollback": False,
        "canonical_path_restore_strategy": "keep_legacy_flat_path_authoritative_until_separate_apply",
        "candidate_count": len(candidate_results),
        "rollback_items": [
            {
                "artifact_key": item.get("artifact_key") or "",
                "restore_canonical_path": item.get("current_canonical_path") or "",
                "future_canonical_candidate": item.get("future_canonical_path") or "",
                "legacy_sha256": (item.get("legacy_file") or {}).get("sha256") or "",
                "future_sha256": (item.get("future_file") or {}).get("sha256") or "",
                "digest_match": bool(item.get("digest_match")),
            }
            for item in candidate_results
        ],
    }


def _foldered_canonical_preflight_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_pilot_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_migration_pilot_plan")
    if "foldered_canonical_migration_pilot_plan_not_ready" in blockers:
        actions.append("resolve_foldered_canonical_migration_pilot_plan_blockers")
    if "candidate_legacy_files_missing" in blockers or "candidate_future_files_missing" in blockers:
        actions.append("rerun_or_verify_dual_write_expansion_outputs_before_preflight")
    if "candidate_digest_mismatch" in blockers:
        actions.append("compare_legacy_and_future_candidate_artifacts_before_canonical_path_review")
    if "high_risk_candidate_present" in blockers:
        actions.append("remove_high_risk_candidates_from_narrow_migration_pilot")
    if "foldered_canonical_migration_pilot_has_no_candidates" in blockers:
        actions.append("select_verified_low_risk_candidates_for_migration_preflight")
    if not blockers:
        actions.append("review_preflight_and_rollback_plan_before_any_canonical_path_apply")
        actions.append("prepare_separate_explicit_apply_step_with_manifest_mutation_guard")
    if "medium_risk_candidate_requires_final_review" in warnings:
        actions.append("complete_final_review_for_medium_risk_candidates")
    return actions


def plan_workspace_foldered_canonical_migration_apply_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_preflight_json: str | None = None,
    migration_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_preflight",
    include_medium_risk: bool = False,
) -> dict[str, Any]:
    """Return a review-only apply plan for foldered-canonical migration."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    preflight, preflight_error, preflight_input = _load_or_read_workspace_foldered_canonical_migration_preflight(
        default_artifact_root=effective_root,
        migration_preflight_json=migration_preflight_json,
        migration_preflight_artifact_ref=migration_preflight_artifact_ref,
    )
    candidate_results = preflight.get("candidate_results") if isinstance(preflight.get("candidate_results"), list) else []
    valid_candidates = [item for item in candidate_results if isinstance(item, dict)]
    ready_candidates = [item for item in valid_candidates if item.get("status") == "ready_for_reviewed_execution" and item.get("digest_match") is True]
    high_risk_candidates = [item for item in valid_candidates if (item.get("risk") or {}).get("risk_level") == "high"]
    medium_risk_candidates = [item for item in valid_candidates if (item.get("risk") or {}).get("risk_level") == "medium"]
    gate = preflight.get("execution_gate") if isinstance(preflight.get("execution_gate"), dict) else {}
    rollback_plan = preflight.get("rollback_plan") if isinstance(preflight.get("rollback_plan"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []
    if preflight_error:
        blockers.append("foldered_canonical_migration_preflight_unavailable_or_malformed")
    if preflight.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_preflight_not_ready")
    if gate.get("ready_for_reviewed_execution") is not True:
        blockers.append("preflight_execution_gate_not_ready")
    for reason in preflight.get("blocking_reasons") or []:
        blockers.append(f"preflight:{reason}")
    if not valid_candidates:
        blockers.append("foldered_canonical_apply_has_no_candidates")
    if len(ready_candidates) != len(valid_candidates):
        blockers.append("not_all_preflight_candidates_ready")
    if high_risk_candidates:
        blockers.append("high_risk_candidate_present")
    if medium_risk_candidates and not include_medium_risk:
        blockers.append("medium_risk_candidates_require_explicit_include_medium_risk")
    if not rollback_plan.get("plan_only") or not rollback_plan.get("rollback_required_before_execution"):
        blockers.append("rollback_plan_not_ready")
    if medium_risk_candidates and include_medium_risk:
        warnings.append("medium_risk_candidates_require_final_apply_review")
    if not blockers:
        warnings.append("apply_plan_requires_explicit_review_and_separate_executor")

    status = "ready_for_review" if not blockers else "blocked"
    apply_steps = [_foldered_canonical_apply_plan_step(item, step_index=index) for index, item in enumerate(valid_candidates)]
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-apply-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(valid_candidates),
            "ready_candidate_count": len(ready_candidates),
            "planned_apply_step_count": len(apply_steps) if status == "ready_for_review" else 0,
            "preflight_status": preflight.get("status") or "missing",
            "high_risk_candidate_count": len(high_risk_candidates),
            "medium_risk_candidate_count": len(medium_risk_candidates),
            "include_medium_risk_requested": bool(include_medium_risk),
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "canonical_path_change_enabled": False,
            "manifest_mutation_enabled": False,
            "review_required": True,
            "rollback_plan_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "preflight_summary": _compact_foldered_canonical_migration_preflight(preflight),
        "preflight_input": preflight_input,
        "apply_plan": {
            "plan_only": True,
            "review_required": True,
            "requires_explicit_review_approval": True,
            "requires_separate_apply_executor": True,
            "apply_executor_invoked": False,
            "apply_executor_available_in_this_tool": False,
            "legacy_canonical_path_remains_authoritative": True,
            "canonical_path_strategy": "keep_legacy_flat_path_authoritative_until_reviewed_apply_executor",
            "planned_steps": apply_steps,
        },
        "manifest_mutation_guard": _foldered_canonical_manifest_mutation_guard(valid_candidates),
        "rollback_requirements": _foldered_canonical_apply_rollback_requirements(rollback_plan, valid_candidates),
        "compatibility_guard": {
            "requires_workspace_consumer_readiness_recheck": True,
            "requires_delivery_source_audit_recheck": True,
            "requires_backend_manifest_alias_review": True,
            "preserve_legacy_read_fallback_until_after_apply_validation": True,
            "forbid_source_path_tightening_in_this_tool": True,
            "forbid_mobile_full_runtime_chain_assumptions": True,
        },
        "execution_gate": {
            "ready_for_apply_review": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_separate_apply_executor": True,
            "allows_automatic_execution": False,
            "allows_file_move_in_this_tool": False,
            "allows_directory_creation_in_this_tool": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_apply_plan_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_preflight(
    *,
    default_artifact_root: Path,
    migration_preflight_json: str | None,
    migration_preflight_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(migration_preflight_json, field_name="migration_preflight_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "candidate_results": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = migration_preflight_artifact_ref or "workspace_foldered_canonical_migration_preflight"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing", "candidate_results": []}, "foldered_canonical_migration_preflight_not_observed", input_summary


def _compact_foldered_canonical_migration_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    summary = preflight.get("summary") if isinstance(preflight.get("summary"), dict) else {}
    return {
        "schema_version": preflight.get("schema_version") or "",
        "status": preflight.get("status") or "missing",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "ready_candidate_count": _safe_int(summary.get("ready_candidate_count")),
        "digest_mismatch_count": _safe_int(summary.get("digest_mismatch_count")),
        "pilot_plan_status": summary.get("pilot_plan_status") or "",
        "blocking_reasons": preflight.get("blocking_reasons") if isinstance(preflight.get("blocking_reasons"), list) else [],
        "warnings": preflight.get("warnings") if isinstance(preflight.get("warnings"), list) else [],
    }


def _foldered_canonical_apply_plan_step(candidate: dict[str, Any], *, step_index: int) -> dict[str, Any]:
    legacy_file = candidate.get("legacy_file") if isinstance(candidate.get("legacy_file"), dict) else {}
    future_file = candidate.get("future_file") if isinstance(candidate.get("future_file"), dict) else {}
    return {
        "step_index": step_index,
        "artifact_key": candidate.get("artifact_key") or "",
        "planned_action": "reviewed_promote_future_foldered_path_to_canonical",
        "plan_only": True,
        "execute_in_this_tool": False,
        "requires_explicit_review_approval": True,
        "current_canonical_path": candidate.get("current_canonical_path") or "",
        "future_canonical_path": candidate.get("future_canonical_path") or "",
        "virtual_uri": candidate.get("virtual_uri") or "",
        "digest_snapshot": {
            "legacy_sha256": legacy_file.get("sha256") or "",
            "future_sha256": future_file.get("sha256") or "",
            "digest_match": bool(candidate.get("digest_match")),
        },
        "rollback": candidate.get("rollback_requirement") if isinstance(candidate.get("rollback_requirement"), dict) else {},
        "risk": candidate.get("risk") if isinstance(candidate.get("risk"), dict) else {},
    }


def _foldered_canonical_manifest_mutation_guard(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "required_before_apply": True,
        "plan_only": True,
        "mutates_manifest_in_this_tool": False,
        "requires_backend_manifest_snapshot": True,
        "requires_workspace_contract_route_alias": True,
        "requires_digest_snapshot_match": True,
        "requires_rollback_manifest_entry": True,
        "required_manifest_changes_preview": [
            {
                "artifact_key": item.get("artifact_key") or "",
                "current_canonical_path": item.get("current_canonical_path") or "",
                "future_canonical_path": item.get("future_canonical_path") or "",
                "virtual_uri": item.get("virtual_uri") or "",
                "metadata_update": "preview-only-canonical-path-promotion",
            }
            for item in candidates
        ],
    }


def _foldered_canonical_apply_rollback_requirements(rollback_plan: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rollback_items = rollback_plan.get("rollback_items") if isinstance(rollback_plan.get("rollback_items"), list) else []
    return {
        "required_before_apply": True,
        "plan_only": True,
        "automatic_rollback": False,
        "rollback_executor_invoked": False,
        "source_preflight_rollback_plan_status": "ready" if rollback_plan.get("plan_only") and rollback_plan.get("rollback_required_before_execution") else "missing_or_blocked",
        "candidate_count": len(candidates),
        "rollback_item_count": len(rollback_items),
        "rollback_items": rollback_items,
    }


def _foldered_canonical_apply_plan_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_preflight_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_migration_preflight")
    if "foldered_canonical_migration_preflight_not_ready" in blockers or "preflight_execution_gate_not_ready" in blockers:
        actions.append("resolve_preflight_blockers_before_apply_plan")
    if "not_all_preflight_candidates_ready" in blockers:
        actions.append("rerun_preflight_after_candidate_file_parity_is_restored")
    if "rollback_plan_not_ready" in blockers:
        actions.append("prepare_preflight_rollback_plan_before_apply_review")
    if "high_risk_candidate_present" in blockers:
        actions.append("remove_high_risk_candidates_or_split_to_separate_apply_review")
    if "medium_risk_candidates_require_explicit_include_medium_risk" in blockers:
        actions.append("set_include_medium_risk_only_after_explicit_apply_review")
    if "foldered_canonical_apply_has_no_candidates" in blockers:
        actions.append("provide_ready_preflight_candidates_before_apply_plan")
    if not blockers:
        actions.append("review_apply_plan_manifest_guard_and_rollback_requirements")
        actions.append("implement_or_call_separate_explicit_apply_executor_after_approval")
    if "medium_risk_candidates_require_final_apply_review" in warnings:
        actions.append("complete_final_review_for_medium_risk_apply_candidates")
    return actions


def plan_workspace_foldered_canonical_migration_approval_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_apply_plan_json: str | None = None,
    migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
    reviewer: str | None = None,
    review_ticket: str | None = None,
    transaction_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Return a review-only approval / transaction plan for foldered-canonical migration apply."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    apply_plan, apply_plan_error, apply_plan_input = _load_or_read_workspace_foldered_canonical_migration_apply_plan(
        default_artifact_root=effective_root,
        migration_apply_plan_json=migration_apply_plan_json,
        migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
    )
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    planned_steps = apply_plan_section.get("planned_steps") if isinstance(apply_plan_section.get("planned_steps"), list) else []
    valid_steps = [item for item in planned_steps if isinstance(item, dict)]
    execution_gate = apply_plan.get("execution_gate") if isinstance(apply_plan.get("execution_gate"), dict) else {}
    manifest_guard = apply_plan.get("manifest_mutation_guard") if isinstance(apply_plan.get("manifest_mutation_guard"), dict) else {}
    rollback_requirements = apply_plan.get("rollback_requirements") if isinstance(apply_plan.get("rollback_requirements"), dict) else {}
    compatibility_guard = apply_plan.get("compatibility_guard") if isinstance(apply_plan.get("compatibility_guard"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []
    if apply_plan_error:
        blockers.append("foldered_canonical_migration_apply_plan_unavailable_or_malformed")
    if apply_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_apply_plan_not_ready")
    if apply_plan_section.get("plan_only") is not True:
        blockers.append("foldered_canonical_migration_apply_plan_not_plan_only")
    if execution_gate.get("ready_for_apply_review") is not True:
        blockers.append("apply_review_gate_not_ready")
    if execution_gate.get("requires_separate_apply_executor") is not True:
        blockers.append("apply_plan_missing_separate_apply_executor_gate")
    if execution_gate.get("allows_automatic_execution") is not False:
        blockers.append("apply_plan_allows_automatic_execution")
    if not valid_steps:
        blockers.append("apply_plan_has_no_planned_steps")
    if manifest_guard.get("required_before_apply") is not True:
        blockers.append("manifest_mutation_guard_not_ready")
    if manifest_guard.get("mutates_manifest_in_this_tool") is not False:
        blockers.append("apply_plan_allows_manifest_mutation_in_tool")
    if rollback_requirements.get("required_before_apply") is not True:
        blockers.append("rollback_requirements_not_ready")
    if execution_gate.get("allows_manifest_mutation_in_this_tool") is not False:
        blockers.append("apply_plan_allows_manifest_mutation_in_tool")
    if execution_gate.get("allows_canonical_path_change_in_this_tool") is not False:
        blockers.append("apply_plan_allows_canonical_path_change_in_tool")
    if execution_gate.get("allows_file_move_in_this_tool") is not False:
        blockers.append("apply_plan_allows_file_move_in_tool")
    for reason in apply_plan.get("blocking_reasons") or []:
        blockers.append(f"apply_plan:{reason}")
    if not blockers:
        warnings.append("approval_descriptor_requires_external_review_ledger_record_before_apply")
        warnings.append("transaction_journal_must_be_written_by_separate_apply_executor")
        warnings.append("manifest_dry_run_and_rollback_checkpoint_required_before_apply")

    status = "ready_for_review" if not blockers else "blocked"
    digest = _foldered_canonical_apply_plan_digest(apply_plan)
    transaction_plan = _foldered_canonical_approval_transaction_plan(
        digest=digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
    )
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-approval-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "planned_apply_step_count": len(valid_steps) if status == "ready_for_review" else 0,
            "apply_plan_status": apply_plan.get("status") or "missing",
            "requires_review_approval": True,
            "requires_transaction_journal": True,
            "requires_idempotency_key": True,
            "requires_manifest_dry_run": True,
            "requires_rollback_checkpoint": True,
            "requires_post_apply_validation": True,
            "legacy_canonical_path_remains_authoritative": True,
            "approval_recorded": False,
            "transaction_journal_written": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "apply_plan_summary": _compact_foldered_canonical_migration_apply_plan(apply_plan),
        "apply_plan_input": apply_plan_input,
        "approval_requirements": {
            "requires_review_approval": True,
            "reviewer": reviewer or "",
            "review_ticket": review_ticket or "",
            "review_ledger_artifact": "workspace/review-approval-ledger.json",
            "required_decision": "approved",
            "records_approval_in_this_tool": False,
            "approval_artifact_written": False,
            "approval_must_match_apply_plan_digest": True,
            "apply_plan_digest": digest,
        },
        "transaction_journal_plan": transaction_plan,
        "idempotency_guard": {
            "duplicate_apply_guard_required": True,
            "idempotency_key_required": True,
            "idempotency_key": transaction_plan["idempotency_key"],
            "checks_existing_journal_in_this_tool": False,
            "blocks_replay_without_matching_approval": True,
            "blocks_replay_without_matching_apply_plan_digest": True,
        },
        "staleness_guard": {
            "requires_fresh_apply_plan": True,
            "requires_fresh_preflight": True,
            "requires_digest_revalidation_by_apply_executor": True,
            "apply_plan_digest": digest,
            "checks_files_in_this_tool": False,
            "stale_preflight_blocks_apply": True,
            "stale_digest_blocks_apply": True,
        },
        "manifest_dry_run_requirements": {
            "required_before_apply": True,
            "manifest_mutation_guard": _compact_foldered_canonical_manifest_mutation_guard(manifest_guard),
            "dry_run_artifact": "workspace/workspace-foldered-canonical-migration-manifest-dry-run.json",
            "runs_dry_run_in_this_tool": False,
        },
        "rollback_checkpoint_requirements": {
            "required_before_apply": True,
            "rollback_requirements": _compact_foldered_canonical_rollback_requirements(rollback_requirements),
            "checkpoint_artifact": "workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json",
            "writes_checkpoint_in_this_tool": False,
        },
        "post_apply_validation_requirements": {
            "required_after_apply": True,
            "validation_artifact": "workspace/workspace-foldered-canonical-migration-post-apply-validation.json",
            "requires_legacy_and_future_read_parity": True,
            "requires_backend_manifest_alias_validation": True,
            "requires_workspace_contract_route_validation": True,
            "requires_transaction_journal_validation": True,
            "runs_validation_in_this_tool": False,
        },
        "compatibility_window": {
            "preserve_legacy_read_fallback": True,
            "canonical_switch_not_performed_by_this_tool": True,
            "source_path_tightening_forbidden": True,
            "compatibility_guard": compatibility_guard,
        },
        "execution_gate": {
            "ready_for_approval_review": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_separate_apply_executor": True,
            "allows_automatic_execution": False,
            "allows_journal_write_in_this_tool": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_file_move_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_approval_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_apply_plan(
    *,
    default_artifact_root: Path,
    migration_apply_plan_json: str | None,
    migration_apply_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(migration_apply_plan_json, field_name="migration_apply_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "apply_plan": {"planned_steps": []}}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = migration_apply_plan_artifact_ref or "workspace_foldered_canonical_migration_apply_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing", "apply_plan": {"planned_steps": []}}, "foldered_canonical_migration_apply_plan_not_observed", input_summary


def _compact_foldered_canonical_migration_apply_plan(apply_plan: dict[str, Any]) -> dict[str, Any]:
    summary = apply_plan.get("summary") if isinstance(apply_plan.get("summary"), dict) else {}
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    planned_steps = apply_plan_section.get("planned_steps") if isinstance(apply_plan_section.get("planned_steps"), list) else []
    gate = apply_plan.get("execution_gate") if isinstance(apply_plan.get("execution_gate"), dict) else {}
    return {
        "schema_version": apply_plan.get("schema_version") or "",
        "status": apply_plan.get("status") or "missing",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "ready_candidate_count": _safe_int(summary.get("ready_candidate_count")),
        "planned_apply_step_count": _safe_int(summary.get("planned_apply_step_count") if summary else len(planned_steps)),
        "preflight_status": summary.get("preflight_status") or "",
        "plan_only": bool(apply_plan_section.get("plan_only")),
        "requires_separate_apply_executor": bool(apply_plan_section.get("requires_separate_apply_executor") or gate.get("requires_separate_apply_executor")),
        "ready_for_apply_review": bool(gate.get("ready_for_apply_review")),
        "blocking_reasons": apply_plan.get("blocking_reasons") if isinstance(apply_plan.get("blocking_reasons"), list) else [],
        "warnings": apply_plan.get("warnings") if isinstance(apply_plan.get("warnings"), list) else [],
    }


def _foldered_canonical_apply_plan_digest(apply_plan: dict[str, Any]) -> str:
    if not apply_plan:
        return ""
    encoded = json.dumps(apply_plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _foldered_canonical_approval_transaction_plan(
    *,
    digest: str,
    transaction_id: str | None,
    idempotency_key: str | None,
) -> dict[str, Any]:
    suffix = digest[:16] if digest else "missing-apply-plan"
    planned_transaction_id = transaction_id or f"planned-foldered-canonical-migration-{suffix}"
    planned_idempotency_key = idempotency_key or f"planned-foldered-canonical-migration-{suffix}"
    return {
        "plan_only": True,
        "transaction_id": planned_transaction_id,
        "idempotency_key": planned_idempotency_key,
        "apply_plan_digest": digest,
        "transaction_journal_artifact": "workspace/workspace-foldered-canonical-migration-transaction-journal.json",
        "append_only": True,
        "writes_journal_in_this_tool": False,
        "requires_duplicate_guard": True,
        "requires_stale_digest_guard": True,
    }


def _compact_foldered_canonical_manifest_mutation_guard(manifest_guard: dict[str, Any]) -> dict[str, Any]:
    changes = manifest_guard.get("required_manifest_changes_preview") if isinstance(manifest_guard.get("required_manifest_changes_preview"), list) else []
    return {
        "required_before_apply": bool(manifest_guard.get("required_before_apply")),
        "plan_only": bool(manifest_guard.get("plan_only")),
        "mutates_manifest_in_this_tool": bool(manifest_guard.get("mutates_manifest_in_this_tool")),
        "requires_backend_manifest_snapshot": bool(manifest_guard.get("requires_backend_manifest_snapshot")),
        "requires_workspace_contract_route_alias": bool(manifest_guard.get("requires_workspace_contract_route_alias")),
        "requires_digest_snapshot_match": bool(manifest_guard.get("requires_digest_snapshot_match")),
        "requires_rollback_manifest_entry": bool(manifest_guard.get("requires_rollback_manifest_entry")),
        "preview_change_count": len(changes),
    }


def _compact_foldered_canonical_rollback_requirements(rollback_requirements: dict[str, Any]) -> dict[str, Any]:
    rollback_items = rollback_requirements.get("rollback_items") if isinstance(rollback_requirements.get("rollback_items"), list) else []
    return {
        "required_before_apply": bool(rollback_requirements.get("required_before_apply")),
        "plan_only": bool(rollback_requirements.get("plan_only")),
        "automatic_rollback": bool(rollback_requirements.get("automatic_rollback")),
        "rollback_executor_invoked": bool(rollback_requirements.get("rollback_executor_invoked")),
        "source_preflight_rollback_plan_status": rollback_requirements.get("source_preflight_rollback_plan_status") or "",
        "candidate_count": _safe_int(rollback_requirements.get("candidate_count")),
        "rollback_item_count": _safe_int(rollback_requirements.get("rollback_item_count") if "rollback_item_count" in rollback_requirements else len(rollback_items)),
    }


def _foldered_canonical_approval_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_apply_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_migration_apply_plan")
    if "foldered_canonical_migration_apply_plan_not_ready" in blockers or "apply_review_gate_not_ready" in blockers:
        actions.append("resolve_apply_plan_blockers_before_approval_review")
    if "apply_plan_has_no_planned_steps" in blockers:
        actions.append("provide_apply_plan_with_reviewable_planned_steps")
    if "manifest_mutation_guard_not_ready" in blockers:
        actions.append("prepare_manifest_mutation_guard_before_approval_review")
    if "rollback_requirements_not_ready" in blockers:
        actions.append("prepare_rollback_requirements_before_approval_review")
    if any(reason in blockers for reason in ["apply_plan_allows_automatic_execution", "apply_plan_allows_manifest_mutation_in_tool", "apply_plan_allows_canonical_path_change_in_tool", "apply_plan_allows_file_move_in_tool"]):
        actions.append("tighten_apply_plan_side_effect_boundaries_before_review")
    if not blockers:
        actions.append("record_explicit_review_approval_for_apply_plan_digest")
        actions.append("run_manifest_dry_run_and_write_rollback_checkpoint_with_separate_reviewed_executor")
        actions.append("invoke_separate_foldered_canonical_apply_executor_after_approval")
        actions.append("run_post_apply_validation_before_tightening_legacy_fallback")
    if "transaction_journal_must_be_written_by_separate_apply_executor" in warnings:
        actions.append("ensure_apply_executor_writes_append_only_transaction_journal")
    return actions


def review_workspace_foldered_canonical_migration_manifest_dry_run_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_approval_plan_json: str | None = None,
    migration_approval_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_approval_plan",
    migration_apply_plan_json: str | None = None,
    migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Return a read-only manifest dry-run and rollback checkpoint descriptor for foldered-canonical migration."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    approval_plan, approval_error, approval_input = _load_or_read_workspace_foldered_canonical_migration_approval_plan(
        default_artifact_root=effective_root,
        migration_approval_plan_json=migration_approval_plan_json,
        migration_approval_plan_artifact_ref=migration_approval_plan_artifact_ref,
    )
    apply_plan, apply_plan_error, apply_plan_input = _load_or_read_workspace_foldered_canonical_migration_apply_plan(
        default_artifact_root=effective_root,
        migration_apply_plan_json=migration_apply_plan_json,
        migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    approval_gate = approval_plan.get("execution_gate") if isinstance(approval_plan.get("execution_gate"), dict) else {}
    approval_requirements = approval_plan.get("approval_requirements") if isinstance(approval_plan.get("approval_requirements"), dict) else {}
    approval_transaction = approval_plan.get("transaction_journal_plan") if isinstance(approval_plan.get("transaction_journal_plan"), dict) else {}
    approval_manifest_requirements = approval_plan.get("manifest_dry_run_requirements") if isinstance(approval_plan.get("manifest_dry_run_requirements"), dict) else {}
    approval_rollback_requirements = approval_plan.get("rollback_checkpoint_requirements") if isinstance(approval_plan.get("rollback_checkpoint_requirements"), dict) else {}
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    planned_steps = apply_plan_section.get("planned_steps") if isinstance(apply_plan_section.get("planned_steps"), list) else []
    valid_steps = [step for step in planned_steps if isinstance(step, dict)]
    manifest_guard = apply_plan.get("manifest_mutation_guard") if isinstance(apply_plan.get("manifest_mutation_guard"), dict) else {}
    rollback_requirements = apply_plan.get("rollback_requirements") if isinstance(apply_plan.get("rollback_requirements"), dict) else {}
    current_digest = _foldered_canonical_apply_plan_digest(apply_plan)
    approved_digest = str(approval_requirements.get("apply_plan_digest") or approval_transaction.get("apply_plan_digest") or "")

    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    manifest_changes = _foldered_canonical_manifest_dry_run_changes(valid_steps, manifest_entries)
    rollback_checkpoint_plan = _foldered_canonical_manifest_rollback_checkpoint_plan(
        apply_plan=apply_plan,
        approval_plan=approval_plan,
        backend_manifest=backend_manifest,
        manifest_changes=manifest_changes,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if approval_error:
        blockers.append("foldered_canonical_migration_approval_plan_unavailable_or_malformed")
    if approval_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_approval_plan_not_ready")
    if approval_gate.get("ready_for_approval_review") is not True:
        blockers.append("approval_review_gate_not_ready")
    if approval_manifest_requirements.get("required_before_apply") is not True:
        blockers.append("approval_manifest_dry_run_requirement_not_ready")
    if approval_rollback_requirements.get("required_before_apply") is not True:
        blockers.append("approval_rollback_checkpoint_requirement_not_ready")
    if apply_plan_error:
        blockers.append("foldered_canonical_migration_apply_plan_unavailable_or_malformed")
    if apply_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_apply_plan_not_ready")
    if apply_plan_section.get("plan_only") is not True:
        blockers.append("foldered_canonical_migration_apply_plan_not_plan_only")
    if not valid_steps:
        blockers.append("manifest_dry_run_has_no_planned_apply_steps")
    if approved_digest and current_digest and approved_digest != current_digest:
        blockers.append("approval_apply_plan_digest_mismatch")
    if not approved_digest:
        blockers.append("approval_apply_plan_digest_missing")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not manifest_entries:
        blockers.append("backend_artifact_manifest_has_no_entries")
    if manifest_guard.get("required_before_apply") is not True:
        blockers.append("manifest_mutation_guard_not_ready")
    if manifest_guard.get("mutates_manifest_in_this_tool") is not False:
        blockers.append("apply_plan_allows_manifest_mutation_in_tool")
    if rollback_requirements.get("required_before_apply") is not True:
        blockers.append("rollback_requirements_not_ready")
    for change in manifest_changes:
        if change.get("status") != "ready_for_manifest_dry_run_review":
            blockers.append(f"manifest_change:{change.get('artifact_key') or 'unknown'}:{change.get('status') or 'blocked'}")
    if not blockers:
        warnings.append("manifest_dry_run_descriptor_requires_review_before_apply_executor")
        warnings.append("rollback_checkpoint_must_be_written_by_separate_apply_executor")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-manifest-dry-run.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "approval_plan_status": approval_plan.get("status") or "missing",
            "apply_plan_status": apply_plan.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error and manifest_entries else "missing_or_blocked",
            "planned_manifest_change_count": len(manifest_changes) if status == "ready_for_review" else 0,
            "planned_apply_step_count": len(valid_steps),
            "rollback_checkpoint_required": True,
            "manifest_dry_run_written": False,
            "rollback_checkpoint_written": False,
            "backend_manifest_mutated": False,
            "legacy_canonical_path_remains_authoritative": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "approval_plan_summary": _compact_foldered_canonical_migration_approval_plan(approval_plan),
        "apply_plan_summary": _compact_foldered_canonical_migration_apply_plan(apply_plan),
        "approval_plan_input": approval_input,
        "apply_plan_input": apply_plan_input,
        "backend_manifest_input": backend_manifest_input,
        "digest_guard": {
            "approval_apply_plan_digest": approved_digest,
            "current_apply_plan_digest": current_digest,
            "digest_match": bool(approved_digest and current_digest and approved_digest == current_digest),
            "requires_revalidation_by_apply_executor": True,
        },
        "manifest_dry_run": {
            "plan_only": True,
            "review_required": True,
            "dry_run_artifact": "workspace/workspace-foldered-canonical-migration-manifest-dry-run.json",
            "writes_artifact_in_this_tool": False,
            "mutates_manifest_in_this_tool": False,
            "source_backend_manifest_artifact_ref": backend_manifest_input.get("artifact_ref") or "",
            "source_backend_manifest_entry_count": len(manifest_entries),
            "planned_changes": manifest_changes,
        },
        "rollback_checkpoint": rollback_checkpoint_plan,
        "execution_gate": {
            "ready_for_manifest_dry_run_review": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_separate_apply_executor": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_rollback_checkpoint_write_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_file_move_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_manifest_dry_run_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_approval_plan(
    *,
    default_artifact_root: Path,
    migration_approval_plan_json: str | None,
    migration_approval_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(migration_approval_plan_json, field_name="migration_approval_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = migration_approval_plan_artifact_ref or "workspace_foldered_canonical_migration_approval_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "foldered_canonical_migration_approval_plan_not_observed", input_summary


def _load_or_read_workspace_backend_artifact_manifest(
    *,
    default_artifact_root: Path,
    backend_manifest_json: str | None,
    backend_manifest_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(backend_manifest_json, field_name="backend_manifest_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "entries": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = backend_manifest_artifact_ref or "workspace_backend_artifact_manifest"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "entries": []}, "backend_artifact_manifest_not_observed", input_summary


def _compact_foldered_canonical_migration_approval_plan(approval_plan: dict[str, Any]) -> dict[str, Any]:
    summary = approval_plan.get("summary") if isinstance(approval_plan.get("summary"), dict) else {}
    gate = approval_plan.get("execution_gate") if isinstance(approval_plan.get("execution_gate"), dict) else {}
    approval_requirements = approval_plan.get("approval_requirements") if isinstance(approval_plan.get("approval_requirements"), dict) else {}
    transaction = approval_plan.get("transaction_journal_plan") if isinstance(approval_plan.get("transaction_journal_plan"), dict) else {}
    return {
        "schema_version": approval_plan.get("schema_version") or "",
        "status": approval_plan.get("status") or "missing",
        "planned_apply_step_count": _safe_int(summary.get("planned_apply_step_count")),
        "apply_plan_status": summary.get("apply_plan_status") or "",
        "ready_for_approval_review": bool(gate.get("ready_for_approval_review")),
        "records_approval_in_this_tool": bool(approval_requirements.get("records_approval_in_this_tool")),
        "writes_journal_in_this_tool": bool(transaction.get("writes_journal_in_this_tool")),
        "apply_plan_digest": approval_requirements.get("apply_plan_digest") or transaction.get("apply_plan_digest") or "",
        "blocking_reasons": approval_plan.get("blocking_reasons") if isinstance(approval_plan.get("blocking_reasons"), list) else [],
        "warnings": approval_plan.get("warnings") if isinstance(approval_plan.get("warnings"), list) else [],
    }


def _foldered_canonical_manifest_dry_run_changes(
    planned_steps: list[dict[str, Any]],
    manifest_entries: list[Any],
) -> list[dict[str, Any]]:
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    changes: list[dict[str, Any]] = []
    for index, step in enumerate(planned_steps):
        artifact_key = str(step.get("artifact_key") or "")
        manifest_entry = entries_by_key.get(artifact_key) or {}
        future_path = str(step.get("future_canonical_path") or "")
        current_path = str(step.get("current_canonical_path") or "")
        existing_path = str(manifest_entry.get("path") or "")
        status = "ready_for_manifest_dry_run_review"
        blockers: list[str] = []
        if not artifact_key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        if not manifest_entry:
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        if not future_path:
            status = "blocked_future_canonical_path_missing"
            blockers.append("future_canonical_path_required")
        if existing_path and current_path and existing_path != current_path:
            status = "blocked_manifest_current_path_mismatch"
            blockers.append("manifest_current_path_mismatch")
        changes.append({
            "change_index": index,
            "artifact_key": artifact_key,
            "status": status,
            "plan_only": True,
            "review_required": True,
            "current_manifest_path": existing_path,
            "expected_current_canonical_path": current_path,
            "future_canonical_path": future_path,
            "virtual_uri": step.get("virtual_uri") or "",
            "metadata_update": {
                "workspace_alias_future_path": future_path,
                "canonical_path_promotion_preview": True,
                "legacy_fallback_required": True,
            },
            "digest_snapshot": step.get("digest_snapshot") if isinstance(step.get("digest_snapshot"), dict) else {},
            "blockers": blockers,
            "mutates_manifest_in_this_tool": False,
        })
    return changes


def _foldered_canonical_manifest_rollback_checkpoint_plan(
    *,
    apply_plan: dict[str, Any],
    approval_plan: dict[str, Any],
    backend_manifest: dict[str, Any],
    manifest_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    rollback_requirements = apply_plan.get("rollback_requirements") if isinstance(apply_plan.get("rollback_requirements"), dict) else {}
    transaction = approval_plan.get("transaction_journal_plan") if isinstance(approval_plan.get("transaction_journal_plan"), dict) else {}
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    return {
        "plan_only": True,
        "review_required": True,
        "required_before_apply": True,
        "checkpoint_artifact": "workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json",
        "writes_checkpoint_in_this_tool": False,
        "source_backend_manifest_entry_count": len(entries),
        "planned_manifest_change_count": len(manifest_changes),
        "rollback_item_count": _safe_int(rollback_requirements.get("rollback_item_count")),
        "transaction_id": transaction.get("transaction_id") or "",
        "idempotency_key": transaction.get("idempotency_key") or "",
        "captures_backend_manifest_snapshot": True,
        "captures_apply_plan_digest": True,
        "captures_rollback_requirements": True,
        "automatic_rollback": False,
        "rollback_executor_invoked": False,
    }


def _foldered_canonical_manifest_dry_run_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_approval_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_migration_approval_plan")
    if "foldered_canonical_migration_apply_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_matching_foldered_canonical_migration_apply_plan")
    if "approval_apply_plan_digest_mismatch" in blockers or "approval_apply_plan_digest_missing" in blockers:
        actions.append("regenerate_approval_plan_from_current_apply_plan_before_manifest_dry_run")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "backend_artifact_manifest_has_no_entries" in blockers:
        actions.append("provide_current_backend_artifact_manifest_for_manifest_dry_run")
    if any(reason.startswith("manifest_change:") for reason in blockers):
        actions.append("resolve_manifest_entry_or_path_mismatch_before_apply_executor")
    if not blockers:
        actions.append("record_review_approval_for_manifest_dry_run_and_rollback_checkpoint")
        actions.append("invoke_separate_apply_executor_to_write_manifest_dry_run_and_rollback_checkpoint")
        actions.append("revalidate_manifest_dry_run_before_physical_canonical_path_promotion")
    if "rollback_checkpoint_must_be_written_by_separate_apply_executor" in warnings:
        actions.append("ensure_apply_executor_writes_rollback_checkpoint_before_manifest_mutation")
    return actions


def review_workspace_foldered_canonical_migration_post_apply_validation_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_manifest_dry_run_json: str | None = None,
    migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
    migration_apply_plan_json: str | None = None,
    migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
    post_apply_backend_manifest_json: str | None = None,
    post_apply_backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Return a read-only post-apply validation descriptor for foldered-canonical migration."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    dry_run, dry_run_error, dry_run_input = _load_or_read_workspace_foldered_canonical_migration_manifest_dry_run(
        default_artifact_root=effective_root,
        migration_manifest_dry_run_json=migration_manifest_dry_run_json,
        migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
    )
    apply_plan, apply_plan_error, apply_plan_input = _load_or_read_workspace_foldered_canonical_migration_apply_plan(
        default_artifact_root=effective_root,
        migration_apply_plan_json=migration_apply_plan_json,
        migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
    )
    post_apply_manifest, post_apply_manifest_error, post_apply_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=post_apply_backend_manifest_json,
        backend_manifest_artifact_ref=post_apply_backend_manifest_artifact_ref,
    )

    dry_run_gate = dry_run.get("execution_gate") if isinstance(dry_run.get("execution_gate"), dict) else {}
    dry_run_manifest = dry_run.get("manifest_dry_run") if isinstance(dry_run.get("manifest_dry_run"), dict) else {}
    dry_run_digest = dry_run.get("digest_guard") if isinstance(dry_run.get("digest_guard"), dict) else {}
    planned_changes = dry_run_manifest.get("planned_changes") if isinstance(dry_run_manifest.get("planned_changes"), list) else []
    valid_changes = [change for change in planned_changes if isinstance(change, dict)]
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    post_apply_entries = post_apply_manifest.get("entries") if isinstance(post_apply_manifest.get("entries"), list) else []
    current_apply_plan_digest = _foldered_canonical_apply_plan_digest(apply_plan)
    dry_run_apply_plan_digest = str(dry_run_digest.get("current_apply_plan_digest") or dry_run_digest.get("approval_apply_plan_digest") or "")
    validation_results = _foldered_canonical_post_apply_validation_results(valid_changes, post_apply_entries)

    blockers: list[str] = []
    warnings: list[str] = []
    if dry_run_error:
        blockers.append("foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed")
    if dry_run.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_manifest_dry_run_not_ready")
    if dry_run_gate.get("ready_for_manifest_dry_run_review") is not True:
        blockers.append("manifest_dry_run_review_gate_not_ready")
    if apply_plan_error:
        blockers.append("foldered_canonical_migration_apply_plan_unavailable_or_malformed")
    if apply_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_apply_plan_not_ready")
    if apply_plan_section.get("plan_only") is not True:
        blockers.append("foldered_canonical_migration_apply_plan_not_plan_only")
    if dry_run_apply_plan_digest and current_apply_plan_digest and dry_run_apply_plan_digest != current_apply_plan_digest:
        blockers.append("manifest_dry_run_apply_plan_digest_mismatch")
    if not dry_run_apply_plan_digest:
        blockers.append("manifest_dry_run_apply_plan_digest_missing")
    if post_apply_manifest_error:
        blockers.append("post_apply_backend_artifact_manifest_unavailable_or_malformed")
    if not post_apply_entries:
        blockers.append("post_apply_backend_artifact_manifest_has_no_entries")
    if not valid_changes:
        blockers.append("post_apply_validation_has_no_manifest_changes")
    for result in validation_results:
        if result.get("status") != "ready_for_post_apply_validation_review":
            blockers.append(f"post_apply_validation:{result.get('artifact_key') or 'unknown'}:{result.get('status') or 'blocked'}")
        if result.get("warnings"):
            warnings.extend(f"post_apply_validation:{result.get('artifact_key') or 'unknown'}:{warning}" for warning in result.get("warnings") or [])
    if not blockers:
        warnings.append("post_apply_validation_descriptor_requires_review_before_tightening_legacy_fallback")
        warnings.append("physical_apply_executor_evidence_must_be_preserved_outside_this_tool")

    status = "ready_for_review" if not blockers else "blocked"
    ready_count = sum(1 for result in validation_results if result.get("status") == "ready_for_post_apply_validation_review")
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "manifest_dry_run_status": dry_run.get("status") or "missing",
            "apply_plan_status": apply_plan.get("status") or "missing",
            "post_apply_manifest_status": "loaded" if not post_apply_manifest_error and post_apply_entries else "missing_or_blocked",
            "planned_manifest_change_count": len(valid_changes),
            "validated_manifest_change_count": ready_count if status == "ready_for_review" else 0,
            "post_apply_validation_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "canonical_path_changed_by_this_tool": False,
            "observed_canonical_path_promotion_validated": status == "ready_for_review",
            "legacy_fallback_tightening_allowed": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "manifest_dry_run_summary": _compact_foldered_canonical_migration_manifest_dry_run(dry_run),
        "apply_plan_summary": _compact_foldered_canonical_migration_apply_plan(apply_plan),
        "manifest_dry_run_input": dry_run_input,
        "apply_plan_input": apply_plan_input,
        "post_apply_backend_manifest_input": post_apply_manifest_input,
        "digest_guard": {
            "manifest_dry_run_apply_plan_digest": dry_run_apply_plan_digest,
            "current_apply_plan_digest": current_apply_plan_digest,
            "digest_match": bool(dry_run_apply_plan_digest and current_apply_plan_digest and dry_run_apply_plan_digest == current_apply_plan_digest),
            "requires_revalidation_by_apply_executor": True,
        },
        "post_apply_validation": {
            "review_required": True,
            "validation_artifact": "workspace/workspace-foldered-canonical-migration-post-apply-validation.json",
            "writes_artifact_in_this_tool": False,
            "source_post_apply_backend_manifest_artifact_ref": post_apply_manifest_input.get("artifact_ref") or "",
            "source_post_apply_backend_manifest_entry_count": len(post_apply_entries),
            "validation_results": validation_results,
        },
        "compatibility_validation": _foldered_canonical_post_apply_compatibility_validation(validation_results),
        "execution_gate": {
            "ready_for_post_apply_validation_review": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_observed_physical_apply_evidence": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_file_move_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_post_apply_validation_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_manifest_dry_run(
    *,
    default_artifact_root: Path,
    migration_manifest_dry_run_json: str | None,
    migration_manifest_dry_run_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(migration_manifest_dry_run_json, field_name="migration_manifest_dry_run_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = migration_manifest_dry_run_artifact_ref or "workspace_foldered_canonical_migration_manifest_dry_run"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "foldered_canonical_migration_manifest_dry_run_not_observed", input_summary


def _compact_foldered_canonical_migration_manifest_dry_run(dry_run: dict[str, Any]) -> dict[str, Any]:
    summary = dry_run.get("summary") if isinstance(dry_run.get("summary"), dict) else {}
    gate = dry_run.get("execution_gate") if isinstance(dry_run.get("execution_gate"), dict) else {}
    digest_guard = dry_run.get("digest_guard") if isinstance(dry_run.get("digest_guard"), dict) else {}
    return {
        "schema_version": dry_run.get("schema_version") or "",
        "status": dry_run.get("status") or "missing",
        "planned_manifest_change_count": _safe_int(summary.get("planned_manifest_change_count")),
        "planned_apply_step_count": _safe_int(summary.get("planned_apply_step_count")),
        "ready_for_manifest_dry_run_review": bool(gate.get("ready_for_manifest_dry_run_review")),
        "digest_match": bool(digest_guard.get("digest_match")),
        "current_apply_plan_digest": digest_guard.get("current_apply_plan_digest") or "",
        "blocking_reasons": dry_run.get("blocking_reasons") if isinstance(dry_run.get("blocking_reasons"), list) else [],
        "warnings": dry_run.get("warnings") if isinstance(dry_run.get("warnings"), list) else [],
    }


def _foldered_canonical_post_apply_validation_results(
    planned_changes: list[dict[str, Any]],
    post_apply_manifest_entries: list[Any],
) -> list[dict[str, Any]]:
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in post_apply_manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    results: list[dict[str, Any]] = []
    for index, change in enumerate(planned_changes):
        artifact_key = str(change.get("artifact_key") or "")
        expected_future_path = str(change.get("future_canonical_path") or "")
        expected_previous_path = str(change.get("current_manifest_path") or change.get("expected_current_canonical_path") or "")
        entry = entries_by_key.get(artifact_key) or {}
        observed_path = str(entry.get("path") or "")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        alias_future_path = str(alias.get("future_path") or "")
        status = "ready_for_post_apply_validation_review"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        if not entry:
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        if not expected_future_path:
            status = "blocked_expected_future_canonical_path_missing"
            blockers.append("expected_future_canonical_path_required")
        if observed_path and expected_future_path and observed_path != expected_future_path:
            status = "blocked_canonical_path_not_promoted"
            blockers.append("canonical_path_not_promoted_to_future_path")
        if observed_path and expected_previous_path and observed_path == expected_previous_path:
            status = "blocked_canonical_path_still_legacy"
            blockers.append("canonical_path_still_legacy")
        if alias_future_path and expected_future_path and alias_future_path != expected_future_path:
            status = "blocked_workspace_alias_future_path_mismatch"
            blockers.append("workspace_alias_future_path_mismatch")
        if entry and not alias:
            warnings.append("workspace_alias_metadata_missing")
        if alias and alias.get("canonical_path_remains_authoritative") is True:
            warnings.append("workspace_alias_still_marks_legacy_authoritative")
        results.append({
            "validation_index": index,
            "artifact_key": artifact_key,
            "status": status,
            "review_required": True,
            "expected_previous_canonical_path": expected_previous_path,
            "expected_promoted_canonical_path": expected_future_path,
            "observed_manifest_path": observed_path,
            "observed_workspace_alias_future_path": alias_future_path,
            "virtual_uri": change.get("virtual_uri") or alias.get("virtual_uri") or "",
            "canonical_path_promotion_observed": bool(observed_path and expected_future_path and observed_path == expected_future_path),
            "legacy_fallback_still_required": True,
            "blockers": blockers,
            "warnings": warnings,
            "mutates_manifest_in_this_tool": False,
        })
    return results


def _foldered_canonical_post_apply_compatibility_validation(validation_results: list[dict[str, Any]]) -> dict[str, Any]:
    ready_count = sum(1 for result in validation_results if result.get("status") == "ready_for_post_apply_validation_review")
    return {
        "review_required": True,
        "planned_validation_count": len(validation_results),
        "ready_validation_count": ready_count,
        "all_promotions_observed": bool(validation_results) and ready_count == len(validation_results),
        "preserve_legacy_read_fallback": True,
        "legacy_fallback_tightening_allowed_by_this_tool": False,
        "requires_workspace_consumer_readiness_recheck": True,
        "requires_delivery_source_audit_recheck": True,
        "requires_backend_manifest_alias_review": True,
        "requires_post_apply_reader_smoke": True,
        "forbid_source_path_tightening_in_this_tool": True,
        "forbid_mobile_full_runtime_chain_assumptions": True,
    }


def _foldered_canonical_post_apply_validation_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_manifest_dry_run")
    if "foldered_canonical_migration_apply_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_matching_foldered_canonical_migration_apply_plan")
    if "manifest_dry_run_apply_plan_digest_mismatch" in blockers or "manifest_dry_run_apply_plan_digest_missing" in blockers:
        actions.append("regenerate_manifest_dry_run_from_current_apply_plan_before_validation")
    if "post_apply_backend_artifact_manifest_unavailable_or_malformed" in blockers or "post_apply_backend_artifact_manifest_has_no_entries" in blockers:
        actions.append("provide_observed_post_apply_backend_manifest_for_validation")
    if any(reason.startswith("post_apply_validation:") for reason in blockers):
        actions.append("rerun_or_fix_physical_apply_executor_before_post_apply_validation")
    if not blockers:
        actions.append("review_post_apply_validation_before_tightening_legacy_fallback")
        actions.append("run_workspace_reader_compatibility_smoke_with_legacy_and_future_refs")
        actions.append("keep_legacy_fallback_until_delivery_source_audit_and_consumer_readiness_are_rechecked")
    if any("workspace_alias_metadata_missing" in warning for warning in warnings):
        actions.append("review_backend_manifest_workspace_alias_metadata_after_apply")
    return actions


def record_workspace_foldered_canonical_migration_post_apply_validation_result_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    post_apply_validation_json: str | None = None,
    post_apply_validation_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_apply_validation",
    write_result: bool = False,
) -> dict[str, Any]:
    """Record a durable post-apply validation result artifact from a reviewed descriptor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    validation, validation_error, validation_input = _load_or_read_workspace_foldered_canonical_post_apply_validation(
        default_artifact_root=effective_root,
        post_apply_validation_json=post_apply_validation_json,
        post_apply_validation_artifact_ref=post_apply_validation_artifact_ref,
    )
    summary = validation.get("summary") if isinstance(validation.get("summary"), dict) else {}
    gate = validation.get("execution_gate") if isinstance(validation.get("execution_gate"), dict) else {}
    post_apply_validation = (
        validation.get("post_apply_validation")
        if isinstance(validation.get("post_apply_validation"), dict)
        else {}
    )
    validation_results = (
        post_apply_validation.get("validation_results")
        if isinstance(post_apply_validation.get("validation_results"), list)
        else []
    )
    valid_results = [item for item in validation_results if isinstance(item, dict)]
    compatibility = (
        validation.get("compatibility_validation")
        if isinstance(validation.get("compatibility_validation"), dict)
        else {}
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if validation_error:
        blockers.append("post_apply_validation_unavailable_or_malformed")
    if validation.get("status") != "ready_for_review":
        blockers.append("post_apply_validation_not_ready_for_review")
    if gate.get("ready_for_post_apply_validation_review") is not True:
        blockers.append("post_apply_validation_review_gate_not_ready")
    if not valid_results:
        blockers.append("post_apply_validation_has_no_validation_results")
    for reason in validation.get("blocking_reasons") or []:
        blockers.append(f"post_apply_validation:{reason}")
    for warning in validation.get("warnings") or []:
        warnings.append(f"post_apply_validation:{warning}")
    ready_result_count = sum(
        1
        for item in valid_results
        if item.get("status") == "ready_for_post_apply_validation_review"
    )
    if valid_results and ready_result_count != len(valid_results):
        blockers.append("post_apply_validation_contains_blocked_results")
    if compatibility.get("all_promotions_observed") is not True:
        blockers.append("post_apply_validation_promotions_not_all_observed")
    if not blockers:
        warnings.append("legacy_fallback_tightening_requires_separate_reviewed_follow_up")
        warnings.append("foldered_canonical_finalization_requires_separate_reviewed_follow_up")

    status = "verified" if not blockers else "blocked" if validation.get("schema_version") != "missing" else "not_ready"
    result_artifact = _workspace_foldered_canonical_post_apply_validation_result_artifact_metadata(
        effective_root,
        written=False,
    )
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-apply-validation-result.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "result_artifact": result_artifact,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "post_apply_validation_status": validation.get("status") or "missing",
            "validation_result_count": len(valid_results),
            "ready_validation_result_count": ready_result_count,
            "observed_canonical_path_promotion_validated": bool(summary.get("observed_canonical_path_promotion_validated")),
            "all_promotions_observed": bool(compatibility.get("all_promotions_observed")),
            "write_result_requested": bool(write_result),
            "result_artifact_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "canonical_path_changed_by_this_tool": False,
            "legacy_fallback_tightened": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "post_apply_validation_input": validation_input,
        "post_apply_validation_summary": {
            "schema_version": validation.get("schema_version") or "",
            "status": validation.get("status") or "missing",
            "planned_manifest_change_count": _safe_int(summary.get("planned_manifest_change_count")),
            "validated_manifest_change_count": _safe_int(summary.get("validated_manifest_change_count")),
            "ready_for_post_apply_validation_review": bool(gate.get("ready_for_post_apply_validation_review")),
            "digest_match": bool((validation.get("digest_guard") or {}).get("digest_match"))
            if isinstance(validation.get("digest_guard"), dict)
            else False,
            "blocking_reasons": validation.get("blocking_reasons")
            if isinstance(validation.get("blocking_reasons"), list)
            else [],
            "warnings": validation.get("warnings") if isinstance(validation.get("warnings"), list) else [],
        },
        "validation_results": valid_results,
        "compatibility_validation": compatibility,
        "legacy_fallback_review_gate": {
            "legacy_fallback_tightening_allowed_by_this_tool": False,
            "requires_separate_readiness_descriptor": True,
            "requires_consumer_readiness_recheck": True,
            "requires_delivery_source_audit_recheck": True,
            "requires_explicit_review_approval": True,
        },
        "finalization_gate": {
            "foldered_canonical_finalization_allowed_by_this_tool": False,
            "requires_legacy_fallback_tightening_result": True,
            "requires_separate_finalization_plan": True,
            "requires_explicit_review_approval": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_post_apply_validation_result_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": False,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if write_result:
        result_path = effective_root / "workspace" / "workspace-foldered-canonical-migration-post-apply-validation-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_foldered_canonical_post_apply_validation_result_artifact_metadata(
            effective_root,
            written=True,
        )
        payload["summary"]["result_artifact_written"] = True
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_read_workspace_foldered_canonical_post_apply_validation(
    *,
    default_artifact_root: Path,
    post_apply_validation_json: str | None,
    post_apply_validation_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(post_apply_validation_json, field_name="post_apply_validation_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = post_apply_validation_artifact_ref or "workspace_foldered_canonical_migration_post_apply_validation"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "post_apply_validation_not_observed", input_summary


def _workspace_foldered_canonical_post_apply_validation_result_artifact_metadata(
    artifact_root: Path,
    *,
    written: bool,
) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_foldered_canonical_migration_post_apply_validation_result",
        "legacy_path": "workspace/workspace-foldered-canonical-migration-post-apply-validation-result.json",
        "future_path": "/workspace/review/workspace-foldered-canonical-migration-post-apply-validation-result.json",
        "path": str(artifact_root / "workspace" / "workspace-foldered-canonical-migration-post-apply-validation-result.json"),
        "written": written,
        "category": "audit",
    }


def _foldered_canonical_post_apply_validation_result_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "post_apply_validation_unavailable_or_malformed" in blockers or "post_apply_validation_not_ready_for_review" in blockers:
        actions.append("create_or_pass_ready_post_apply_validation_descriptor")
    if "post_apply_validation_promotions_not_all_observed" in blockers or "post_apply_validation_contains_blocked_results" in blockers:
        actions.append("fix_or_rerun_physical_apply_then_regenerate_post_apply_validation")
    if status == "verified":
        actions.append("review_legacy_fallback_tightening_readiness_before_any_fallback_change")
        actions.append("keep_foldered_canonical_finalization_as_separate_reviewed_follow_up")
    if any("legacy_fallback_tightening" in warning for warning in warnings):
        actions.append("do_not_tighten_legacy_fallback_from_this_result_writer")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_legacy_fallback_tightening_readiness_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    post_apply_validation_result_json: str | None = None,
    post_apply_validation_result_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_apply_validation_result",
    readiness_score_json: str | None = None,
    readiness_score_artifact_ref: str | None = "workspace_consumer_readiness_score",
) -> dict[str, Any]:
    """Return a read-only readiness descriptor for a future legacy fallback tightening plan."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    validation_result, validation_error, validation_input = _load_or_read_workspace_foldered_canonical_post_apply_validation_result(
        default_artifact_root=effective_root,
        post_apply_validation_result_json=post_apply_validation_result_json,
        post_apply_validation_result_artifact_ref=post_apply_validation_result_artifact_ref,
    )
    readiness_score, readiness_error, readiness_input = _load_or_read_workspace_consumer_readiness_score_artifact(
        default_artifact_root=effective_root,
        readiness_score_json=readiness_score_json,
        readiness_score_artifact_ref=readiness_score_artifact_ref,
    )
    validation_summary = validation_result.get("summary") if isinstance(validation_result.get("summary"), dict) else {}
    validation_gate = (
        validation_result.get("legacy_fallback_review_gate")
        if isinstance(validation_result.get("legacy_fallback_review_gate"), dict)
        else {}
    )
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    readiness_summary = _compact_workspace_consumer_score(readiness_score)
    blockers: list[str] = []
    warnings: list[str] = []
    if validation_error:
        blockers.append("post_apply_validation_result_unavailable_or_malformed")
    if validation_result.get("status") != "verified":
        blockers.append("post_apply_validation_result_not_verified")
    if validation_summary.get("all_promotions_observed") is not True:
        blockers.append("post_apply_validation_result_promotions_not_observed")
    if validation_gate.get("requires_consumer_readiness_recheck") is not True:
        warnings.append("post_apply_validation_result_does_not_require_consumer_readiness_recheck")
    if readiness_error:
        blockers.append("workspace_consumer_readiness_score_unavailable_or_malformed")
    if readiness_score.get("status") != "ready_for_foldered_canonical_review":
        blockers.append("workspace_consumer_readiness_score_not_ready_for_foldered_canonical_review")
    if readiness.get("foldered_canonical_migration_allowed") is not True:
        blockers.append("workspace_consumer_readiness_blocks_foldered_canonical_follow_up")
    for reason in validation_result.get("blocking_reasons") or []:
        blockers.append(f"post_apply_validation_result:{reason}")
    for reason in readiness_score.get("blocking_reasons") or []:
        blockers.append(f"workspace_consumer_readiness_score:{reason}")
    for warning in validation_result.get("warnings") or []:
        warnings.append(f"post_apply_validation_result:{warning}")
    for warning in readiness_score.get("warnings") or []:
        warnings.append(f"workspace_consumer_readiness_score:{warning}")
    if not blockers:
        warnings.append("legacy_fallback_tightening_plan_requires_separate_review")
        warnings.append("legacy_fallback_tightening_executor_not_run_by_readiness_descriptor")

    status = "ready_for_review" if not blockers else "blocked"
    validation_result_count = _safe_int(validation_summary.get("validation_result_count"))
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-readiness.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "post_apply_validation_result_status": validation_result.get("status") or "missing",
            "workspace_consumer_readiness_score_status": readiness_score.get("status") or "missing",
            "validation_result_count": validation_result_count,
            "all_promotions_observed": bool(validation_summary.get("all_promotions_observed")),
            "ready_for_legacy_fallback_tightening_plan_review": status == "ready_for_review",
            "legacy_fallback_tightened": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "post_apply_validation_result_input": validation_input,
        "workspace_consumer_readiness_score_input": readiness_input,
        "post_apply_validation_result_summary": {
            "schema_version": validation_result.get("schema_version") or "",
            "status": validation_result.get("status") or "missing",
            "ready_validation_result_count": _safe_int(validation_summary.get("ready_validation_result_count")),
            "observed_canonical_path_promotion_validated": bool(
                validation_summary.get("observed_canonical_path_promotion_validated")
            ),
            "result_artifact_written": bool(validation_summary.get("result_artifact_written")),
            "legacy_fallback_tightened": bool(validation_summary.get("legacy_fallback_tightened")),
            "foldered_canonical_finalized": bool(validation_summary.get("foldered_canonical_finalized")),
        },
        "workspace_consumer_readiness_score_summary": readiness_summary,
        "readiness_checks": {
            "post_apply_validation_result_verified": validation_result.get("status") == "verified",
            "all_promotions_observed": bool(validation_summary.get("all_promotions_observed")),
            "consumer_readiness_rechecked": not bool(readiness_error),
            "consumer_readiness_ready_for_foldered_canonical_review": readiness_score.get("status") == "ready_for_foldered_canonical_review",
            "foldered_canonical_follow_up_allowed": bool(readiness.get("foldered_canonical_migration_allowed")),
            "requires_separate_apply_plan": True,
            "requires_explicit_review_approval": True,
        },
        "tightening_plan_gate": {
            "ready_for_legacy_fallback_tightening_plan_review": status == "ready_for_review",
            "plan_tool": "plan_workspace_foldered_canonical_legacy_fallback_tightening",
            "plan_tool_implemented": True,
            "requires_post_apply_validation_result": True,
            "requires_workspace_consumer_readiness_score": True,
            "requires_delivery_source_audit_recheck": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_legacy_fallback_tightening_readiness_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_post_apply_validation_result(
    *,
    default_artifact_root: Path,
    post_apply_validation_result_json: str | None,
    post_apply_validation_result_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(post_apply_validation_result_json, field_name="post_apply_validation_result_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = post_apply_validation_result_artifact_ref or "workspace_foldered_canonical_migration_post_apply_validation_result"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "post_apply_validation_result_not_observed", input_summary


def _load_or_read_workspace_consumer_readiness_score_artifact(
    *,
    default_artifact_root: Path,
    readiness_score_json: str | None,
    readiness_score_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(readiness_score_json, field_name="readiness_score_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = readiness_score_artifact_ref or "workspace_consumer_readiness_score"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "workspace_consumer_readiness_score_not_observed", input_summary


def _foldered_canonical_legacy_fallback_tightening_readiness_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "post_apply_validation_result_unavailable_or_malformed" in blockers or "post_apply_validation_result_not_verified" in blockers:
        actions.append("record_verified_post_apply_validation_result_before_tightening_review")
    if "workspace_consumer_readiness_score_unavailable_or_malformed" in blockers:
        actions.append("record_or_pass_ready_workspace_consumer_readiness_score_before_tightening_review")
    if "workspace_consumer_readiness_score_not_ready_for_foldered_canonical_review" in blockers:
        actions.append("resolve_workspace_consumer_readiness_blockers_before_legacy_fallback_tightening")
    if status == "ready_for_review":
        actions.append("review_legacy_fallback_tightening_plan_as_separate_step")
        actions.append("keep_foldered_canonical_finalization_separate_from_fallback_tightening")
    if any("executor_not_run" in warning for warning in warnings):
        actions.append("do_not_mutate_manifest_from_readiness_descriptor")
    return list(dict.fromkeys(actions))


def plan_workspace_foldered_canonical_legacy_fallback_tightening_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    legacy_fallback_tightening_readiness_json: str | None = None,
    legacy_fallback_tightening_readiness_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_readiness",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    artifact_keys_json: str | None = None,
) -> dict[str, Any]:
    """Return a review-only legacy fallback tightening apply plan descriptor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness, readiness_error, readiness_input = _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_readiness(
        default_artifact_root=effective_root,
        legacy_fallback_tightening_readiness_json=legacy_fallback_tightening_readiness_json,
        legacy_fallback_tightening_readiness_artifact_ref=legacy_fallback_tightening_readiness_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    candidates, unknown_keys = _foldered_canonical_legacy_fallback_tightening_candidates(
        manifest_entries=manifest_entries,
        requested_keys=requested_keys,
    )
    ready_updates = [candidate for candidate in candidates if candidate.get("status") == "ready_for_legacy_fallback_tightening_plan_review"]
    readiness_gate = readiness.get("tightening_plan_gate") if isinstance(readiness.get("tightening_plan_gate"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if readiness_error:
        blockers.append("legacy_fallback_tightening_readiness_unavailable_or_malformed")
    if readiness.get("status") != "ready_for_review":
        blockers.append("legacy_fallback_tightening_readiness_not_ready")
    if readiness_gate.get("ready_for_legacy_fallback_tightening_plan_review") is not True:
        blockers.append("legacy_fallback_tightening_readiness_gate_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not manifest_entries:
        blockers.append("backend_artifact_manifest_has_no_entries")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if not ready_updates:
        blockers.append("no_legacy_fallback_tightening_candidates_ready")
    for candidate in candidates:
        if candidate.get("status") != "ready_for_legacy_fallback_tightening_plan_review":
            warnings.append(f"legacy_fallback_candidate:{candidate.get('artifact_key') or 'unknown'}:{candidate.get('status') or 'blocked'}")
    for reason in readiness.get("blocking_reasons") or []:
        blockers.append(f"legacy_fallback_tightening_readiness:{reason}")
    for warning in readiness.get("warnings") or []:
        warnings.append(f"legacy_fallback_tightening_readiness:{warning}")
    if not blockers:
        warnings.append("legacy_fallback_tightening_plan_requires_review_approval_before_executor")
        warnings.append("legacy_fallback_tightening_executor_remains_separate_follow_up")

    plan_digest = _foldered_canonical_legacy_fallback_tightening_plan_digest(ready_updates)
    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "readiness_status": readiness.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error and manifest_entries else "missing_or_blocked",
            "candidate_count": len(candidates),
            "planned_tightening_update_count": len(ready_updates) if status == "ready_for_review" else 0,
            "explicit_selection": requested_keys is not None,
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "review_required": True,
            "plan_only": True,
            "legacy_fallback_tightened": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "legacy_fallback_tightening_readiness_input": readiness_input,
        "backend_manifest_input": backend_manifest_input,
        "selection_policy": {
            "default_scope": "all-ready-legacy-fallback-candidates",
            "explicit_artifact_keys_supported": True,
            "requires_ready_tightening_readiness_descriptor": True,
            "requires_current_backend_manifest": True,
            "allows_manifest_mutation": False,
            "allows_legacy_fallback_tightening": False,
        },
        "readiness_summary": {
            "schema_version": readiness.get("schema_version") or "",
            "status": readiness.get("status") or "missing",
            "ready_for_legacy_fallback_tightening_plan_review": bool(readiness_gate.get("ready_for_legacy_fallback_tightening_plan_review")),
            "blocking_reasons": readiness.get("blocking_reasons") if isinstance(readiness.get("blocking_reasons"), list) else [],
            "warnings": readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else [],
        },
        "candidate_results": candidates,
        "planned_manifest_updates": ready_updates if status == "ready_for_review" else [],
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "blocked_candidate_count": len([candidate for candidate in candidates if candidate.get("status") != "ready_for_legacy_fallback_tightening_plan_review"]),
        },
        "digest_guard": {
            "legacy_fallback_tightening_plan_digest": plan_digest,
            "requires_executor_revalidation_before_manifest_mutation": True,
        },
        "approval_requirements": {
            "required_before_executor": True,
            "approval_action": "foldered_canonical_legacy_fallback_tightening",
            "subject_id": f"workspace-foldered-canonical-legacy-fallback-tightening:{plan_digest}" if plan_digest else "workspace-foldered-canonical-legacy-fallback-tightening",
            "subject_digest_sha256": plan_digest,
            "records_approval_in_this_tool": False,
        },
        "transaction_journal_plan": {
            "required_before_manifest_mutation": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-legacy-fallback-tightening-journal.json",
            "writes_journal_in_this_tool": False,
            "records_plan_digest": True,
            "records_approval_evidence": True,
            "append_only": True,
        },
        "executor_gate": {
            "ready_for_legacy_fallback_tightening_executor_review": status == "ready_for_review",
            "preflight_tool": "review_workspace_foldered_canonical_legacy_fallback_tightening_preflight",
            "preflight_tool_implemented": True,
            "executor_tool": "execute_workspace_foldered_canonical_legacy_fallback_tightening",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_legacy_fallback_tightening_plan_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_readiness(
    *,
    default_artifact_root: Path,
    legacy_fallback_tightening_readiness_json: str | None,
    legacy_fallback_tightening_readiness_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(
        legacy_fallback_tightening_readiness_json,
        field_name="legacy_fallback_tightening_readiness_json",
    )
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = legacy_fallback_tightening_readiness_artifact_ref or "workspace_foldered_canonical_legacy_fallback_tightening_readiness"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "legacy_fallback_tightening_readiness_not_observed", input_summary


def _foldered_canonical_legacy_fallback_tightening_candidates(
    *,
    manifest_entries: list[Any],
    requested_keys: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    selected_keys = requested_keys if requested_keys is not None else sorted(entries_by_key)
    unknown_keys = [key for key in selected_keys if key not in entries_by_key]
    candidates: list[dict[str, Any]] = []
    for key in selected_keys:
        entry = entries_by_key.get(key)
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        current_path = str(entry.get("path") or "")
        legacy_fallback_path = str(alias.get("legacy_fallback_path") or "")
        future_path = str(alias.get("future_path") or alias.get("canonical_path") or current_path)
        status = "ready_for_legacy_fallback_tightening_plan_review"
        blockers: list[str] = []
        warnings: list[str] = []
        if not alias:
            status = "blocked_workspace_alias_metadata_missing"
            blockers.append("workspace_alias_metadata_required")
        elif not legacy_fallback_path:
            status = "blocked_legacy_fallback_path_missing"
            blockers.append("legacy_fallback_path_required")
        elif alias.get("legacy_fallback_tightened") is True:
            status = "blocked_legacy_fallback_already_tightened"
            blockers.append("legacy_fallback_already_tightened")
        elif alias.get("legacy_fallback_preserved") is not True:
            status = "blocked_legacy_fallback_not_marked_preserved"
            blockers.append("legacy_fallback_preserved_required")
        elif current_path == legacy_fallback_path:
            status = "blocked_canonical_path_still_legacy"
            blockers.append("canonical_path_must_be_future_path_before_tightening")
        if future_path and current_path and future_path != current_path:
            warnings.append("workspace_alias_future_path_does_not_match_manifest_path")
        candidates.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": current_path,
                "future_canonical_path": future_path,
                "legacy_fallback_path": legacy_fallback_path,
                "virtual_uri": alias.get("virtual_uri") or "",
                "review_required": True,
                "planned_metadata_update": {
                    "workspace_alias.legacy_fallback_tightening_planned": True,
                    "workspace_alias.legacy_fallback_tightened": True,
                    "workspace_alias.legacy_fallback_preserved": False,
                    "workspace_alias.legacy_fallback_status": "tightened-after-reviewed-apply",
                },
                "blockers": blockers,
                "warnings": warnings,
                "mutates_manifest_in_this_tool": False,
            }
        )
    return candidates, unknown_keys


def _foldered_canonical_legacy_fallback_tightening_plan_digest(planned_updates: list[dict[str, Any]]) -> str:
    if not planned_updates:
        return ""
    digest_input = [
        {
            "artifact_key": item.get("artifact_key") or "",
            "current_canonical_path": item.get("current_canonical_path") or "",
            "future_canonical_path": item.get("future_canonical_path") or "",
            "legacy_fallback_path": item.get("legacy_fallback_path") or "",
            "planned_metadata_update": item.get("planned_metadata_update") or {},
        }
        for item in planned_updates
    ]
    return hashlib.sha256(json.dumps(digest_input, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _foldered_canonical_legacy_fallback_tightening_plan_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "legacy_fallback_tightening_readiness_unavailable_or_malformed" in blockers or "legacy_fallback_tightening_readiness_not_ready" in blockers:
        actions.append("create_or_pass_ready_legacy_fallback_tightening_readiness_descriptor")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_before_tightening_plan")
    if "no_legacy_fallback_tightening_candidates_ready" in blockers:
        actions.append("review_backend_manifest_workspace_alias_legacy_fallback_metadata")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_unknown_artifact_keys_or_update_workspace_contract")
    if status == "ready_for_review":
        actions.append("record_review_approval_before_legacy_fallback_tightening_executor")
        actions.append("keep_final_migration_finalization_as_separate_follow_up")
    if any("executor_remains_separate" in warning for warning in warnings):
        actions.append("do_not_mutate_manifest_from_tightening_plan_descriptor")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_legacy_fallback_tightening_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    legacy_fallback_tightening_plan_json: str | None = None,
    legacy_fallback_tightening_plan_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    review_approval_ledger_json: str | None = None,
    review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
) -> dict[str, Any]:
    """Return a read-only preflight descriptor for a future legacy fallback tightening executor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_plan(
        default_artifact_root=effective_root,
        legacy_fallback_tightening_plan_json=legacy_fallback_tightening_plan_json,
        legacy_fallback_tightening_plan_artifact_ref=legacy_fallback_tightening_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    approval_ledger, approval_ledger_error, approval_ledger_input = _load_or_read_review_approval_ledger(
        default_artifact_root=effective_root,
        review_approval_ledger_json=review_approval_ledger_json,
        review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
    )

    plan_digest = _legacy_fallback_tightening_plan_digest_from_payload(plan)
    expected_approval = _legacy_fallback_tightening_expected_approval(plan_digest=plan_digest, plan=plan)
    approval_evidence = _legacy_fallback_tightening_approval_evidence(
        approval_ledger=approval_ledger,
        expected=expected_approval,
    )
    manifest_revalidation = _legacy_fallback_tightening_manifest_revalidation(
        plan=plan,
        backend_manifest=backend_manifest,
    )
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in planned_updates if isinstance(update, dict)]

    blockers: list[str] = []
    warnings: list[str] = []
    if plan_error:
        blockers.append("legacy_fallback_tightening_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("legacy_fallback_tightening_plan_not_ready")
    if executor_gate.get("ready_for_legacy_fallback_tightening_executor_review") is not True:
        blockers.append("legacy_fallback_tightening_plan_executor_gate_not_ready")
    if not valid_updates:
        blockers.append("legacy_fallback_tightening_plan_has_no_updates")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not manifest_revalidation["all_candidates_still_ready"]:
        blockers.append("backend_manifest_legacy_fallback_candidates_not_ready")
    if approval_ledger_error:
        blockers.append("review_approval_ledger_unavailable_or_malformed")
    if not approval_evidence["matching_approval_found"]:
        blockers.append("review_approval_ledger_missing_matching_legacy_fallback_tightening_approval")
    if not approval_evidence["approved"]:
        blockers.append("review_approval_ledger_does_not_approve_legacy_fallback_tightening")
    if not plan_digest:
        blockers.append("legacy_fallback_tightening_plan_digest_missing")
    for result in manifest_revalidation["candidate_results"]:
        if result.get("status") != "ready_for_legacy_fallback_tightening_executor_preflight":
            warnings.append(f"legacy_fallback_tightening_candidate:{result.get('artifact_key') or 'unknown'}:{result.get('status') or 'blocked'}")
    if not blockers:
        warnings.append("legacy_fallback_tightening_preflight_ready_for_explicit_reviewed_executor")
        warnings.append("foldered_canonical_finalization_must_remain_separate_after_tightening")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "plan_status": plan.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error else "missing_or_blocked",
            "planned_tightening_update_count": len(valid_updates),
            "manifest_candidate_ready_count": manifest_revalidation["ready_candidate_count"],
            "review_approval_ledger_status": "loaded" if not approval_ledger_error else "missing_or_blocked",
            "matching_review_approval_found": approval_evidence["matching_approval_found"],
            "ready_for_legacy_fallback_tightening_executor_review": status == "ready_for_review",
            "legacy_fallback_tightened_by_this_tool": False,
            "foldered_canonical_finalized_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "legacy_fallback_tightening_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "review_approval_ledger_input": approval_ledger_input,
        "plan_summary": _compact_legacy_fallback_tightening_plan(plan),
        "digest_guard": {
            "legacy_fallback_tightening_plan_digest": plan_digest,
            "approval_subject_digest_sha256": approval_evidence.get("subject_digest_sha256") or "",
            "digest_matches_approval": approval_evidence["digest_matches_expected"],
            "requires_executor_revalidation_before_manifest_mutation": True,
        },
        "review_approval_gate": approval_evidence,
        "manifest_revalidation": manifest_revalidation,
        "transaction_journal_plan": {
            "required": True,
            "append_only": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-legacy-fallback-tightening-journal.json",
            "writes_journal_in_this_tool": False,
            "records_plan_digest": True,
            "records_approval_evidence": True,
            "records_manifest_revalidation": True,
        },
        "idempotency_guard": {
            "required": True,
            "idempotency_key": approval_evidence.get("idempotency_key") or expected_approval["idempotency_key"],
            "checks_existing_tightening_journal_in_this_tool": False,
            "must_block_duplicate_legacy_fallback_tightening": True,
        },
        "executor_gate": {
            "ready_for_legacy_fallback_tightening_executor_review": status == "ready_for_review",
            "executor_tool": "execute_workspace_foldered_canonical_legacy_fallback_tightening",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "requires_append_only_transaction_journal": True,
            "requires_idempotency_guard": True,
            "requires_finalization_as_separate_follow_up": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _legacy_fallback_tightening_preflight_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "writes_transaction_journal": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_plan(
    *,
    default_artifact_root: Path,
    legacy_fallback_tightening_plan_json: str | None,
    legacy_fallback_tightening_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(
        legacy_fallback_tightening_plan_json,
        field_name="legacy_fallback_tightening_plan_json",
    )
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = legacy_fallback_tightening_plan_artifact_ref or "workspace_foldered_canonical_legacy_fallback_tightening_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "legacy_fallback_tightening_plan_not_observed", input_summary


def _legacy_fallback_tightening_plan_digest_from_payload(plan: dict[str, Any]) -> str:
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    digest = str(digest_guard.get("legacy_fallback_tightening_plan_digest") or "")
    if digest:
        return digest
    updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in updates if isinstance(update, dict)]
    return _foldered_canonical_legacy_fallback_tightening_plan_digest(valid_updates)


def _legacy_fallback_tightening_expected_approval(*, plan_digest: str, plan: dict[str, Any]) -> dict[str, Any]:
    approval_requirements = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    subject_id = str(
        approval_requirements.get("subject_id")
        or (f"workspace-foldered-canonical-legacy-fallback-tightening:{plan_digest}" if plan_digest else "")
        or "workspace-foldered-canonical-legacy-fallback-tightening"
    )
    action = str(approval_requirements.get("approval_action") or "foldered_canonical_legacy_fallback_tightening")
    idempotency_key = plan_digest[:16] if plan_digest else subject_id.rsplit(":", 1)[-1]
    return {
        "subject_id": subject_id,
        "action": action,
        "decision": "approved",
        "plan_digest": plan_digest,
        "idempotency_key": idempotency_key,
    }


def _legacy_fallback_tightening_approval_evidence(
    *,
    approval_ledger: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    entries = approval_ledger.get("entries") if isinstance(approval_ledger.get("entries"), list) else []
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    matching: dict[str, Any] | None = None
    for entry in candidates:
        if entry.get("subject_id") == expected["subject_id"] and entry.get("action") == expected["action"]:
            matching = entry
            break
    approved_status = bool(matching and matching.get("decision") == "approved" and matching.get("status") == "written")
    digest = str((matching or {}).get("subject_digest_sha256") or "")
    digest_matches = bool(digest and expected.get("plan_digest") and digest == expected.get("plan_digest"))
    metadata = matching.get("metadata") if isinstance((matching or {}).get("metadata"), dict) else {}
    return {
        "review_required": True,
        "approval_ledger_artifact": "workspace/review-approval-ledger.json",
        "expected_subject_id": expected["subject_id"],
        "expected_action": expected["action"],
        "expected_decision": expected["decision"],
        "matching_approval_found": matching is not None,
        "approved": bool(approved_status and digest_matches),
        "approval_status": str((matching or {}).get("status") or "missing"),
        "approval_id": str((matching or {}).get("approval_id") or ""),
        "reviewer": str((matching or {}).get("reviewer") or ""),
        "subject_digest_sha256": digest,
        "expected_plan_digest": expected.get("plan_digest") or "",
        "digest_matches_expected": digest_matches,
        "idempotency_key": str(metadata.get("idempotency_key") or expected.get("idempotency_key") or ""),
        "writes_approval_in_this_tool": False,
        "ledger_entry_count": len(candidates),
    }


def _legacy_fallback_tightening_manifest_revalidation(
    *,
    plan: dict[str, Any],
    backend_manifest: dict[str, Any],
) -> dict[str, Any]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    candidate_results: list[dict[str, Any]] = []
    for update in planned_updates:
        if not isinstance(update, dict):
            continue
        key = str(update.get("artifact_key") or "")
        entry = entries_by_key.get(key)
        expected_path = str(update.get("current_canonical_path") or "")
        expected_legacy = str(update.get("legacy_fallback_path") or "")
        status = "ready_for_legacy_fallback_tightening_executor_preflight"
        blockers: list[str] = []
        alias: dict[str, Any] = {}
        current_path = ""
        legacy_fallback_path = ""
        if not key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif not isinstance(entry, dict):
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        else:
            current_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            legacy_fallback_path = str(alias.get("legacy_fallback_path") or "")
            if expected_path and current_path != expected_path:
                status = "blocked_manifest_canonical_path_changed"
                blockers.append("manifest_canonical_path_mismatch")
            if expected_legacy and legacy_fallback_path != expected_legacy:
                status = "blocked_legacy_fallback_path_changed"
                blockers.append("legacy_fallback_path_mismatch")
            if alias.get("legacy_fallback_tightened") is True:
                status = "blocked_legacy_fallback_already_tightened"
                blockers.append("legacy_fallback_already_tightened")
            if alias.get("legacy_fallback_preserved") is not True:
                status = "blocked_legacy_fallback_not_preserved"
                blockers.append("legacy_fallback_preserved_required")
            if current_path and legacy_fallback_path and current_path == legacy_fallback_path:
                status = "blocked_canonical_path_still_legacy"
                blockers.append("canonical_path_must_be_future_path_before_tightening")
        candidate_results.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": current_path,
                "expected_canonical_path": expected_path,
                "legacy_fallback_path": legacy_fallback_path,
                "expected_legacy_fallback_path": expected_legacy,
                "legacy_fallback_preserved": bool(alias.get("legacy_fallback_preserved")) if alias else False,
                "legacy_fallback_tightened": bool(alias.get("legacy_fallback_tightened")) if alias else False,
                "blockers": blockers,
            }
        )
    ready_count = len(
        [
            result
            for result in candidate_results
            if result.get("status") == "ready_for_legacy_fallback_tightening_executor_preflight"
        ]
    )
    return {
        "required_before_manifest_mutation": True,
        "candidate_count": len(candidate_results),
        "ready_candidate_count": ready_count,
        "all_candidates_still_ready": bool(candidate_results and ready_count == len(candidate_results)),
        "candidate_results": candidate_results,
        "mutates_manifest_in_this_tool": False,
    }


def _compact_legacy_fallback_tightening_plan(plan: dict[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    approval = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    return {
        "schema_version": plan.get("schema_version") or "",
        "status": plan.get("status") or "missing",
        "planned_tightening_update_count": _safe_int(summary.get("planned_tightening_update_count")),
        "plan_only": bool(summary.get("plan_only")),
        "legacy_fallback_tightening_plan_digest": digest_guard.get("legacy_fallback_tightening_plan_digest") or "",
        "ready_for_legacy_fallback_tightening_executor_review": bool(
            executor_gate.get("ready_for_legacy_fallback_tightening_executor_review")
        ),
        "approval_subject_id": approval.get("subject_id") or "",
        "approval_action": approval.get("approval_action") or "",
        "blocking_reasons": plan.get("blocking_reasons") if isinstance(plan.get("blocking_reasons"), list) else [],
        "warnings": plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
    }


def _legacy_fallback_tightening_preflight_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "legacy_fallback_tightening_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_legacy_fallback_tightening_plan")
    if "legacy_fallback_tightening_plan_not_ready" in blockers or "legacy_fallback_tightening_plan_executor_gate_not_ready" in blockers:
        actions.append("regenerate_legacy_fallback_tightening_plan_from_ready_readiness_and_manifest")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "backend_manifest_legacy_fallback_candidates_not_ready" in blockers:
        actions.append("refresh_backend_manifest_and_recheck_legacy_fallback_candidates")
    if (
        "review_approval_ledger_unavailable_or_malformed" in blockers
        or "review_approval_ledger_missing_matching_legacy_fallback_tightening_approval" in blockers
    ):
        actions.append("record_review_approval_for_foldered_canonical_legacy_fallback_tightening")
    if "review_approval_ledger_does_not_approve_legacy_fallback_tightening" in blockers:
        actions.append("resolve_review_approval_ledger_decision_or_digest_before_tightening")
    if not blockers:
        actions.append("review_legacy_fallback_tightening_preflight_before_running_separate_executor")
        actions.append("run_separate_explicit_legacy_fallback_tightening_executor_with_transaction_journal")
        actions.append("keep_foldered_canonical_finalization_as_separate_follow_up")
    if any("candidate" in warning for warning in warnings):
        actions.append("inspect_blocked_legacy_fallback_tightening_candidates")
    return list(dict.fromkeys(actions))


def execute_workspace_foldered_canonical_legacy_fallback_tightening_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    mode: str = "dry-run",
    approve_legacy_fallback_tightening: bool = False,
    legacy_fallback_tightening_preflight_json: str | None = None,
    legacy_fallback_tightening_preflight_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_preflight",
    legacy_fallback_tightening_plan_json: str | None = None,
    legacy_fallback_tightening_plan_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    expected_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Execute explicit-review-only legacy fallback metadata tightening."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    workspace_dir = effective_root / "workspace"
    result_path = workspace_dir / "workspace-foldered-canonical-legacy-fallback-tightening-result.json"
    journal_path = workspace_dir / "workspace-foldered-canonical-legacy-fallback-tightening-journal.json"

    preflight, preflight_error, preflight_input = _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_preflight(
        default_artifact_root=effective_root,
        legacy_fallback_tightening_preflight_json=legacy_fallback_tightening_preflight_json,
        legacy_fallback_tightening_preflight_artifact_ref=legacy_fallback_tightening_preflight_artifact_ref,
    )
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_plan(
        default_artifact_root=effective_root,
        legacy_fallback_tightening_plan_json=legacy_fallback_tightening_plan_json,
        legacy_fallback_tightening_plan_artifact_ref=legacy_fallback_tightening_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    requested_mode = mode or "dry-run"
    dry_run_mode = requested_mode == "dry-run"
    apply_mode = requested_mode == "apply"
    created_at = datetime.now(timezone.utc).isoformat()
    plan_digest = _legacy_fallback_tightening_plan_digest_from_payload(plan)
    expected_digest = expected_plan_digest or plan_digest
    preflight_digest = _legacy_fallback_tightening_preflight_plan_digest(preflight)
    approval_gate = preflight.get("review_approval_gate") if isinstance(preflight.get("review_approval_gate"), dict) else {}
    preflight_gate = preflight.get("executor_gate") if isinstance(preflight.get("executor_gate"), dict) else {}
    manifest_revalidation = preflight.get("manifest_revalidation") if isinstance(preflight.get("manifest_revalidation"), dict) else {}
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in planned_updates if isinstance(update, dict)]
    idempotency_key = str(approval_gate.get("idempotency_key") or plan_digest[:16] or "legacy-fallback-tightening")
    transaction_id = f"foldered-canonical-legacy-fallback-tightening-{plan_digest[:16] or 'missing'}"
    existing_journal = _read_legacy_fallback_tightening_journal(journal_path)
    duplicate_entry = _find_legacy_fallback_tightening_duplicate(existing_journal, idempotency_key=idempotency_key)
    manifest_entry_checks = _legacy_fallback_tightening_apply_manifest_entry_checks(
        planned_updates=valid_updates,
        backend_manifest=backend_manifest,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if requested_mode not in {"dry-run", "apply"}:
        blockers.append("unsupported_legacy_fallback_tightening_mode")
    if apply_mode and not approve_legacy_fallback_tightening:
        blockers.append("apply_requires_approve_legacy_fallback_tightening_true")
    if preflight_error:
        blockers.append("legacy_fallback_tightening_preflight_unavailable_or_malformed")
    if preflight.get("status") != "ready_for_review":
        blockers.append("legacy_fallback_tightening_preflight_not_ready")
    if preflight_gate.get("ready_for_legacy_fallback_tightening_executor_review") is not True:
        blockers.append("legacy_fallback_tightening_preflight_gate_not_ready")
    if plan_error:
        blockers.append("legacy_fallback_tightening_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("legacy_fallback_tightening_plan_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if backend_manifest_json is not None and apply_mode:
        blockers.append("apply_requires_backend_manifest_artifact_ref_not_inline_json")
    if not valid_updates:
        blockers.append("legacy_fallback_tightening_has_no_manifest_updates")
    if expected_digest and plan_digest and expected_digest != plan_digest:
        blockers.append("expected_legacy_fallback_tightening_plan_digest_mismatch")
    if preflight_digest and plan_digest and preflight_digest != plan_digest:
        blockers.append("legacy_fallback_tightening_preflight_plan_digest_mismatch")
    if not approval_gate.get("approved"):
        blockers.append("legacy_fallback_tightening_review_approval_not_approved")
    if not approval_gate.get("digest_matches_expected"):
        blockers.append("legacy_fallback_tightening_review_approval_digest_mismatch")
    if manifest_revalidation.get("all_candidates_still_ready") is not True:
        blockers.append("legacy_fallback_tightening_preflight_manifest_revalidation_not_ready")
    if duplicate_entry:
        blockers.append("legacy_fallback_tightening_duplicate_idempotency_key")
    for check in manifest_entry_checks:
        if check.get("status") != "ready":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status')}")
    if not apply_mode:
        warnings.append("legacy_fallback_tightening_dry_run_does_not_write_journal_result_or_manifest")
    if apply_mode and not blockers:
        warnings.append("legacy_fallback_tightening_will_not_finalize_foldered_canonical_migration")
        warnings.append("foldered_canonical_finalization_remains_separate_reviewed_follow_up")

    status = "blocked" if blockers else "planned" if dry_run_mode else "applied"
    mutated_manifest = _legacy_fallback_tightened_backend_manifest(
        backend_manifest,
        valid_updates,
        transaction_id=transaction_id,
        applied_at=created_at,
    )
    journal_entry = _legacy_fallback_tightening_journal_entry(
        status=status,
        plan_digest=plan_digest,
        preflight_digest=preflight_digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        planned_updates=valid_updates,
        approval_gate=approval_gate,
        blockers=blockers,
        created_at=created_at,
    )
    journal_payload = _legacy_fallback_tightening_journal_payload(
        existing_journal=existing_journal,
        entry=journal_entry,
        append_entry=apply_mode and not blockers,
        updated_at=created_at,
    )
    writes = {
        "backend_manifest": False,
        "journal": False,
        "result": False,
    }
    if apply_mode and not blockers:
        _write_json_file(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input), mutated_manifest)
        _write_json_file(journal_path, journal_payload)
        writes.update({"backend_manifest": True, "journal": True})

    payload = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-result.v1",
        "status": status,
        "mode": requested_mode,
        "artifact_root": str(effective_root),
        "summary": {
            "planned_tightening_update_count": len(valid_updates),
            "manifest_entry_check_count": len(manifest_entry_checks),
            "applied_tightening_update_count": len(valid_updates) if status == "applied" else 0,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "transaction_journal_written": writes["journal"],
            "backend_manifest_mutated": writes["backend_manifest"],
            "result_artifact_written": False,
            "legacy_fallback_tightened": status == "applied",
            "canonical_paths_changed": False,
            "files_moved": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "legacy_fallback_tightening_preflight_input": preflight_input,
        "legacy_fallback_tightening_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "digest_guard": {
            "expected_plan_digest": expected_digest,
            "current_plan_digest": plan_digest,
            "preflight_plan_digest": preflight_digest,
            "expected_digest_match": bool(expected_digest and plan_digest and expected_digest == plan_digest),
            "preflight_digest_match": bool(preflight_digest and plan_digest and preflight_digest == plan_digest),
        },
        "review_approval_gate": approval_gate,
        "idempotency_guard": {
            "idempotency_key": idempotency_key,
            "duplicate_entry_found": duplicate_entry is not None,
            "duplicate_entry": _compact_legacy_fallback_tightening_journal_entry(duplicate_entry),
            "blocks_duplicate_apply": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "transaction_journal": {
            "path": str(journal_path),
            "append_only": True,
            "entry_count": len(journal_payload.get("entries", [])),
            "entry_appended": writes["journal"],
            "writes_journal_in_apply_mode": writes["journal"],
        },
        "backend_manifest_mutation": {
            "path": str(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input)),
            "mutates_backend_manifest_in_apply_mode": writes["backend_manifest"],
            "changes_canonical_paths": False,
            "tightens_legacy_fallback": status == "applied",
            "finalizes_foldered_canonical_migration": False,
            "files_moved": False,
        },
        "finalization_requirement": {
            "required_after_tightening": True,
            "finalization_tool": "review_workspace_foldered_canonical_migration_finalization_readiness",
            "runs_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _legacy_fallback_tightening_execute_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "dry_run_is_read_only": True,
            "artifacts_written": apply_mode and not blockers,
            "writes_transaction_journal": writes["journal"],
            "writes_result_artifact": False,
            "creates_directories": apply_mode and not blockers,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": writes["backend_manifest"],
            "tightens_legacy_fallback": status == "applied",
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if apply_mode and not blockers:
        payload["summary"]["result_artifact_written"] = True
        payload["side_effect_policy"]["writes_result_artifact"] = True
        _write_json_file(result_path, payload)
    return payload


def _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_preflight(
    *,
    default_artifact_root: Path,
    legacy_fallback_tightening_preflight_json: str | None,
    legacy_fallback_tightening_preflight_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(
        legacy_fallback_tightening_preflight_json,
        field_name="legacy_fallback_tightening_preflight_json",
    )
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = legacy_fallback_tightening_preflight_artifact_ref or "workspace_foldered_canonical_legacy_fallback_tightening_preflight"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "legacy_fallback_tightening_preflight_not_observed", input_summary


def _legacy_fallback_tightening_preflight_plan_digest(preflight: dict[str, Any]) -> str:
    guard = preflight.get("digest_guard") if isinstance(preflight.get("digest_guard"), dict) else {}
    return str(guard.get("legacy_fallback_tightening_plan_digest") or "")


def _legacy_fallback_tightening_apply_manifest_entry_checks(
    *,
    planned_updates: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for update in planned_updates:
        artifact_key = str(update.get("artifact_key") or "")
        expected_path = str(update.get("current_canonical_path") or "")
        expected_legacy = str(update.get("legacy_fallback_path") or "")
        entry = entries_by_key.get(artifact_key)
        status = "ready"
        observed_path = ""
        observed_legacy = ""
        legacy_preserved = False
        legacy_tightened = False
        if not artifact_key:
            status = "missing_artifact_key"
        elif not isinstance(entry, dict):
            status = "manifest_entry_missing"
        else:
            observed_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            observed_legacy = str(alias.get("legacy_fallback_path") or "")
            legacy_preserved = alias.get("legacy_fallback_preserved") is True
            legacy_tightened = alias.get("legacy_fallback_tightened") is True
            if expected_path and observed_path != expected_path:
                status = "canonical_path_mismatch"
            elif expected_legacy and observed_legacy != expected_legacy:
                status = "legacy_fallback_path_mismatch"
            elif legacy_tightened:
                status = "legacy_fallback_already_tightened"
            elif not legacy_preserved:
                status = "legacy_fallback_not_preserved"
            elif observed_path and observed_legacy and observed_path == observed_legacy:
                status = "canonical_path_still_legacy"
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "expected_canonical_path": expected_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy,
                "observed_legacy_fallback_path": observed_legacy,
                "legacy_fallback_preserved": legacy_preserved,
                "legacy_fallback_tightened": legacy_tightened,
            }
        )
    return checks


def _legacy_fallback_tightened_backend_manifest(
    backend_manifest: dict[str, Any],
    planned_updates: list[dict[str, Any]],
    *,
    transaction_id: str,
    applied_at: str,
) -> dict[str, Any]:
    manifest = copy.deepcopy(backend_manifest)
    updates_by_key = {
        str(update.get("artifact_key") or ""): update
        for update in planned_updates
        if isinstance(update, dict) and update.get("artifact_key")
    }
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        update = updates_by_key.get(str(entry.get("artifact_key") or ""))
        if not update:
            continue
        metadata = entry.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            entry["metadata"] = metadata
        alias = metadata.setdefault("workspace_alias", {})
        if not isinstance(alias, dict):
            alias = {}
            metadata["workspace_alias"] = alias
        planned_metadata = update.get("planned_metadata_update") if isinstance(update.get("planned_metadata_update"), dict) else {}
        alias["legacy_fallback_tightening_planned"] = bool(
            planned_metadata.get("workspace_alias.legacy_fallback_tightening_planned", True)
        )
        alias["legacy_fallback_tightened"] = True
        alias["legacy_fallback_preserved"] = False
        alias["legacy_fallback_status"] = planned_metadata.get("workspace_alias.legacy_fallback_status") or "tightened-after-reviewed-apply"
        alias["legacy_fallback_tightened_at"] = applied_at
        alias["legacy_fallback_tightening_transaction_id"] = transaction_id
    metadata = manifest.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["legacy_fallback_tightening_applied_at"] = applied_at
        metadata["legacy_fallback_tightening_transaction_id"] = transaction_id
    return manifest


def _read_legacy_fallback_tightening_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-journal.v1", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-journal.v1",
            "entries": [],
            "load_error": "malformed_existing_journal",
        }
    if not isinstance(payload, dict):
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-journal.v1", "entries": []}
    if not isinstance(payload.get("entries"), list):
        payload["entries"] = []
    return payload


def _find_legacy_fallback_tightening_duplicate(journal: dict[str, Any], *, idempotency_key: str) -> dict[str, Any] | None:
    for entry in journal.get("entries", []):
        if isinstance(entry, dict) and entry.get("idempotency_key") == idempotency_key and entry.get("status") == "applied":
            return entry
    return None


def _legacy_fallback_tightening_journal_entry(
    *,
    status: str,
    plan_digest: str,
    preflight_digest: str,
    transaction_id: str,
    idempotency_key: str,
    planned_updates: list[dict[str, Any]],
    approval_gate: dict[str, Any],
    blockers: list[str],
    created_at: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "plan_digest": plan_digest,
        "preflight_plan_digest": preflight_digest,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "approval_id": approval_gate.get("approval_id") or "",
        "approval_subject_id": approval_gate.get("expected_subject_id") or "",
        "planned_tightening_update_count": len(planned_updates),
        "artifact_keys": [str(update.get("artifact_key") or "") for update in planned_updates],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "created_at": created_at,
    }


def _legacy_fallback_tightening_journal_payload(
    *,
    existing_journal: dict[str, Any],
    entry: dict[str, Any],
    append_entry: bool,
    updated_at: str,
) -> dict[str, Any]:
    entries = [item for item in existing_journal.get("entries", []) if isinstance(item, dict)]
    if append_entry:
        entries.append(entry)
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-legacy-fallback-tightening-journal.v1",
        "updated_at": updated_at,
        "entry_count": len(entries),
        "entries": entries,
    }


def _compact_legacy_fallback_tightening_journal_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {
        "status": entry.get("status") or "",
        "plan_digest": entry.get("plan_digest") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "idempotency_key": entry.get("idempotency_key") or "",
        "artifact_keys": entry.get("artifact_keys") if isinstance(entry.get("artifact_keys"), list) else [],
    }


def _legacy_fallback_tightening_execute_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "legacy_fallback_tightening_preflight_unavailable_or_malformed" in blockers or "legacy_fallback_tightening_preflight_not_ready" in blockers:
        actions.append("create_or_pass_ready_legacy_fallback_tightening_preflight")
    if "apply_requires_approve_legacy_fallback_tightening_true" in blockers:
        actions.append("rerun_with_approve_legacy_fallback_tightening_true_after_review")
    if "legacy_fallback_tightening_review_approval_not_approved" in blockers or "legacy_fallback_tightening_review_approval_digest_mismatch" in blockers:
        actions.append("resolve_review_approval_ledger_before_tightening_apply")
    if "legacy_fallback_tightening_duplicate_idempotency_key" in blockers:
        actions.append("inspect_existing_legacy_fallback_tightening_journal_before_retry")
    if any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("refresh_backend_manifest_and_recheck_legacy_fallback_tightening_preflight")
    if status == "planned":
        actions.append("review_dry_run_then_rerun_apply_with_explicit_approval")
    if status == "applied":
        actions.append("review_legacy_fallback_tightening_result")
        actions.append("start_foldered_canonical_finalization_readiness_as_separate_follow_up")
    if "foldered_canonical_finalization_remains_separate_reviewed_follow_up" in warnings:
        actions.append("do_not_finalize_migration_from_legacy_fallback_tightening_executor")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_migration_finalization_readiness_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    legacy_fallback_tightening_result_json: str | None = None,
    legacy_fallback_tightening_result_artifact_ref: str | None = "workspace_foldered_canonical_legacy_fallback_tightening_result",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Return a read-only readiness descriptor for future foldered-canonical migration finalization."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    tightening_result, tightening_error, tightening_input = _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_result(
        default_artifact_root=effective_root,
        legacy_fallback_tightening_result_json=legacy_fallback_tightening_result_json,
        legacy_fallback_tightening_result_artifact_ref=legacy_fallback_tightening_result_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    summary = tightening_result.get("summary") if isinstance(tightening_result.get("summary"), dict) else {}
    manifest_checks = (
        tightening_result.get("manifest_entry_checks")
        if isinstance(tightening_result.get("manifest_entry_checks"), list)
        else []
    )
    valid_result_checks = [item for item in manifest_checks if isinstance(item, dict)]
    manifest_revalidation = _foldered_canonical_finalization_readiness_manifest_checks(
        tightening_result_checks=valid_result_checks,
        backend_manifest=backend_manifest,
    )
    ready_manifest_count = sum(1 for item in manifest_revalidation if item.get("status") == "ready")

    blockers: list[str] = []
    warnings: list[str] = []
    if tightening_error:
        blockers.append("legacy_fallback_tightening_result_unavailable_or_malformed")
    if tightening_result.get("status") != "applied":
        blockers.append("legacy_fallback_tightening_result_not_applied")
    if summary.get("legacy_fallback_tightened") is not True:
        blockers.append("legacy_fallback_tightening_result_did_not_tighten_fallback")
    if summary.get("foldered_canonical_finalized") is True:
        blockers.append("foldered_canonical_migration_already_finalized_in_result")
    if not valid_result_checks:
        blockers.append("legacy_fallback_tightening_result_has_no_manifest_entry_checks")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    for check in manifest_revalidation:
        if check.get("status") != "ready":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status')}")
    for reason in tightening_result.get("blocking_reasons") or []:
        blockers.append(f"legacy_fallback_tightening_result:{reason}")
    for warning in tightening_result.get("warnings") or []:
        warnings.append(f"legacy_fallback_tightening_result:{warning}")
    if not blockers:
        warnings.append("foldered_canonical_finalization_plan_requires_separate_review")
        warnings.append("foldered_canonical_finalization_executor_not_run_by_readiness_descriptor")

    status = "ready_for_review" if not blockers else "blocked"
    planned_count = _safe_int(summary.get("planned_tightening_update_count"))
    applied_count = _safe_int(summary.get("applied_tightening_update_count"))
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-readiness.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "legacy_fallback_tightening_result_status": tightening_result.get("status") or "missing",
            "planned_tightening_update_count": planned_count,
            "applied_tightening_update_count": applied_count,
            "manifest_entry_check_count": len(valid_result_checks),
            "manifest_entry_ready_count": ready_manifest_count,
            "ready_for_foldered_canonical_finalization_plan_review": status == "ready_for_review",
            "canonical_paths_changed_by_this_tool": False,
            "legacy_fallback_tightened_by_this_tool": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "legacy_fallback_tightening_result_input": tightening_input,
        "backend_manifest_input": backend_manifest_input,
        "legacy_fallback_tightening_result_summary": {
            "schema_version": tightening_result.get("schema_version") or "",
            "status": tightening_result.get("status") or "missing",
            "transaction_id": summary.get("transaction_id") or "",
            "idempotency_key": summary.get("idempotency_key") or "",
            "transaction_journal_written": bool(summary.get("transaction_journal_written")),
            "result_artifact_written": bool(summary.get("result_artifact_written")),
            "backend_manifest_mutated": bool(summary.get("backend_manifest_mutated")),
            "legacy_fallback_tightened": bool(summary.get("legacy_fallback_tightened")),
            "canonical_paths_changed": bool(summary.get("canonical_paths_changed")),
            "foldered_canonical_finalized": bool(summary.get("foldered_canonical_finalized")),
        },
        "manifest_revalidation": {
            "all_entries_ready_for_finalization_review": bool(
                manifest_revalidation and ready_manifest_count == len(manifest_revalidation)
            ),
            "candidate_count": len(manifest_revalidation),
            "ready_candidate_count": ready_manifest_count,
            "candidate_results": manifest_revalidation,
        },
        "readiness_checks": {
            "legacy_fallback_tightening_result_applied": tightening_result.get("status") == "applied",
            "legacy_fallback_tightened": bool(summary.get("legacy_fallback_tightened")),
            "backend_manifest_revalidated": not bool(backend_manifest_error),
            "all_manifest_entries_tightened": bool(
                manifest_revalidation and ready_manifest_count == len(manifest_revalidation)
            ),
            "canonical_paths_remain_foldered": all(
                item.get("canonical_path_is_foldered") is True for item in manifest_revalidation
            )
            if manifest_revalidation
            else False,
            "legacy_fallback_paths_no_longer_preserved_as_active_fallback": all(
                item.get("legacy_fallback_preserved") is False for item in manifest_revalidation
            )
            if manifest_revalidation
            else False,
            "requires_separate_finalization_plan": True,
            "requires_explicit_review_approval": True,
        },
        "finalization_plan_gate": {
            "ready_for_foldered_canonical_finalization_plan_review": status == "ready_for_review",
            "plan_tool": "plan_workspace_foldered_canonical_migration_finalization",
            "plan_tool_implemented": True,
            "requires_legacy_fallback_tightening_result": True,
            "requires_current_backend_manifest_revalidation": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_finalization_readiness_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def plan_workspace_foldered_canonical_migration_finalization_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    finalization_readiness_json: str | None = None,
    finalization_readiness_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_readiness",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    artifact_keys_json: str | None = None,
) -> dict[str, Any]:
    """Return a review-only foldered-canonical migration finalization plan descriptor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness, readiness_error, readiness_input = _load_or_read_workspace_foldered_canonical_migration_finalization_readiness(
        default_artifact_root=effective_root,
        finalization_readiness_json=finalization_readiness_json,
        finalization_readiness_artifact_ref=finalization_readiness_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    readiness_gate = readiness.get("finalization_plan_gate") if isinstance(readiness.get("finalization_plan_gate"), dict) else {}
    readiness_revalidation = readiness.get("manifest_revalidation") if isinstance(readiness.get("manifest_revalidation"), dict) else {}
    readiness_candidates = (
        readiness_revalidation.get("candidate_results")
        if isinstance(readiness_revalidation.get("candidate_results"), list)
        else []
    )
    candidates, unknown_keys = _foldered_canonical_finalization_plan_candidates(
        readiness_candidates=[item for item in readiness_candidates if isinstance(item, dict)],
        backend_manifest=backend_manifest,
        requested_keys=requested_keys,
    )
    ready_updates = [
        candidate
        for candidate in candidates
        if candidate.get("status") == "ready_for_foldered_canonical_finalization_plan_review"
    ]

    blockers: list[str] = []
    warnings: list[str] = []
    if readiness_error:
        blockers.append("foldered_canonical_finalization_readiness_unavailable_or_malformed")
    if readiness.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_finalization_readiness_not_ready")
    if readiness_gate.get("ready_for_foldered_canonical_finalization_plan_review") is not True:
        blockers.append("foldered_canonical_finalization_readiness_gate_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if not ready_updates:
        blockers.append("no_foldered_canonical_finalization_candidates_ready")
    for candidate in candidates:
        if candidate.get("status") != "ready_for_foldered_canonical_finalization_plan_review":
            warnings.append(f"finalization_candidate:{candidate.get('artifact_key') or 'unknown'}:{candidate.get('status') or 'blocked'}")
    for reason in readiness.get("blocking_reasons") or []:
        blockers.append(f"foldered_canonical_finalization_readiness:{reason}")
    for warning in readiness.get("warnings") or []:
        warnings.append(f"foldered_canonical_finalization_readiness:{warning}")
    if not blockers:
        warnings.append("foldered_canonical_finalization_plan_requires_review_approval_before_preflight")
        warnings.append("foldered_canonical_finalization_preflight_and_executor_remain_separate_follow_ups")

    plan_digest = _foldered_canonical_finalization_plan_digest(ready_updates)
    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "readiness_status": readiness.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error else "missing_or_blocked",
            "candidate_count": len(candidates),
            "planned_finalization_update_count": len(ready_updates) if status == "ready_for_review" else 0,
            "explicit_selection": requested_keys is not None,
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "review_required": True,
            "plan_only": True,
            "canonical_paths_changed_by_this_tool": False,
            "legacy_fallback_tightened_by_this_tool": False,
            "foldered_canonical_finalized": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "finalization_readiness_input": readiness_input,
        "backend_manifest_input": backend_manifest_input,
        "selection_policy": {
            "default_scope": "all-ready-foldered-canonical-finalization-candidates",
            "explicit_artifact_keys_supported": True,
            "requires_ready_finalization_readiness_descriptor": True,
            "requires_current_backend_manifest": True,
            "allows_manifest_mutation": False,
            "allows_canonical_path_change": False,
            "allows_finalization": False,
        },
        "readiness_summary": {
            "schema_version": readiness.get("schema_version") or "",
            "status": readiness.get("status") or "missing",
            "ready_for_foldered_canonical_finalization_plan_review": bool(
                readiness_gate.get("ready_for_foldered_canonical_finalization_plan_review")
            ),
            "blocking_reasons": readiness.get("blocking_reasons") if isinstance(readiness.get("blocking_reasons"), list) else [],
            "warnings": readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else [],
        },
        "candidate_results": candidates,
        "planned_manifest_updates": ready_updates if status == "ready_for_review" else [],
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "blocked_candidate_count": len(
                [candidate for candidate in candidates if candidate.get("status") != "ready_for_foldered_canonical_finalization_plan_review"]
            ),
        },
        "digest_guard": {
            "foldered_canonical_finalization_plan_digest": plan_digest,
            "requires_preflight_revalidation_before_manifest_mutation": True,
            "requires_executor_revalidation_before_manifest_mutation": True,
        },
        "approval_requirements": {
            "required_before_preflight_or_executor": True,
            "approval_action": "foldered_canonical_migration_finalization",
            "subject_id": f"workspace-foldered-canonical-finalization:{plan_digest}" if plan_digest else "workspace-foldered-canonical-finalization",
            "subject_digest_sha256": plan_digest,
            "records_approval_in_this_tool": False,
        },
        "transaction_journal_plan": {
            "required_before_manifest_mutation": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-migration-finalization-journal.json",
            "writes_journal_in_this_tool": False,
            "records_plan_digest": True,
            "records_approval_evidence": True,
            "append_only": True,
        },
        "executor_gate": {
            "ready_for_foldered_canonical_finalization_preflight_review": status == "ready_for_review",
            "preflight_tool": "review_workspace_foldered_canonical_migration_finalization_preflight",
            "preflight_tool_implemented": True,
            "executor_tool": "execute_workspace_foldered_canonical_migration_finalization",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_finalization_plan_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_finalization_readiness(
    *,
    default_artifact_root: Path,
    finalization_readiness_json: str | None,
    finalization_readiness_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(finalization_readiness_json, field_name="finalization_readiness_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = finalization_readiness_artifact_ref or "workspace_foldered_canonical_migration_finalization_readiness"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "finalization_readiness_not_observed", input_summary


def _foldered_canonical_finalization_plan_candidates(
    *,
    readiness_candidates: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
    requested_keys: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates_by_key = {
        str(candidate.get("artifact_key") or ""): candidate
        for candidate in readiness_candidates
        if isinstance(candidate, dict) and candidate.get("artifact_key")
    }
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    selected_keys = requested_keys if requested_keys is not None else sorted(candidates_by_key)
    unknown_keys = [key for key in selected_keys if key not in candidates_by_key]
    candidates: list[dict[str, Any]] = []
    for key in selected_keys:
        readiness_candidate = candidates_by_key.get(key)
        if not isinstance(readiness_candidate, dict):
            continue
        entry = entries_by_key.get(key)
        status = "ready_for_foldered_canonical_finalization_plan_review"
        blockers: list[str] = []
        warnings: list[str] = []
        current_path = ""
        legacy_fallback_path = ""
        virtual_uri = ""
        if readiness_candidate.get("status") != "ready":
            status = f"blocked_readiness_candidate_{readiness_candidate.get('status') or 'not_ready'}"
            blockers.append("readiness_candidate_must_be_ready")
        if not isinstance(entry, dict):
            status = "blocked_manifest_entry_missing"
            blockers.append("backend_manifest_entry_required")
        else:
            current_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            legacy_fallback_path = str(alias.get("legacy_fallback_path") or "")
            virtual_uri = str(alias.get("virtual_uri") or "")
            expected_path = str(readiness_candidate.get("observed_canonical_path") or "")
            expected_legacy = str(readiness_candidate.get("observed_legacy_fallback_path") or "")
            if expected_path and current_path != expected_path:
                status = "blocked_canonical_path_mismatch"
                blockers.append("canonical_path_must_match_readiness")
            elif expected_legacy and legacy_fallback_path != expected_legacy:
                status = "blocked_legacy_fallback_path_mismatch"
                blockers.append("legacy_fallback_path_must_match_readiness")
            elif not current_path or current_path == legacy_fallback_path:
                status = "blocked_canonical_path_not_foldered"
                blockers.append("canonical_path_must_remain_foldered")
            elif alias.get("legacy_fallback_tightened") is not True:
                status = "blocked_legacy_fallback_not_tightened"
                blockers.append("legacy_fallback_must_be_tightened")
            elif alias.get("legacy_fallback_preserved") is True:
                status = "blocked_legacy_fallback_still_preserved"
                blockers.append("legacy_fallback_must_not_remain_preserved")
            if alias.get("foldered_canonical_finalized") is True:
                warnings.append("foldered_canonical_already_marked_finalized")
        candidates.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": current_path,
                "legacy_fallback_path": legacy_fallback_path,
                "virtual_uri": virtual_uri,
                "review_required": True,
                "planned_metadata_update": {
                    "workspace_alias.foldered_canonical_finalization_planned": True,
                    "workspace_alias.foldered_canonical_finalized": True,
                    "workspace_alias.migration_status": "foldered-canonical-finalized-after-reviewed-apply",
                    "workspace_alias.resolver_migration_status": "foldered-canonical-authoritative",
                },
                "blockers": blockers,
                "warnings": warnings,
                "mutates_manifest_in_this_tool": False,
            }
        )
    return candidates, unknown_keys


def _foldered_canonical_finalization_plan_digest(planned_updates: list[dict[str, Any]]) -> str:
    if not planned_updates:
        return ""
    digest_input = [
        {
            "artifact_key": item.get("artifact_key") or "",
            "current_canonical_path": item.get("current_canonical_path") or "",
            "legacy_fallback_path": item.get("legacy_fallback_path") or "",
            "planned_metadata_update": item.get("planned_metadata_update") or {},
        }
        for item in planned_updates
    ]
    return hashlib.sha256(json.dumps(digest_input, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _foldered_canonical_finalization_plan_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_finalization_readiness_unavailable_or_malformed" in blockers or "foldered_canonical_finalization_readiness_not_ready" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_finalization_readiness_descriptor")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_before_finalization_plan")
    if "no_foldered_canonical_finalization_candidates_ready" in blockers:
        actions.append("review_backend_manifest_workspace_alias_finalization_metadata")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_unknown_artifact_keys_or_update_workspace_contract")
    if status == "ready_for_review":
        actions.append("record_review_approval_before_finalization_preflight")
        actions.append("keep_finalization_preflight_and_executor_as_separate_follow_ups")
    if any("preflight_and_executor_remain_separate" in warning for warning in warnings):
        actions.append("do_not_mutate_manifest_from_finalization_plan_descriptor")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_migration_finalization_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    finalization_plan_json: str | None = None,
    finalization_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    review_approval_ledger_json: str | None = None,
    review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
) -> dict[str, Any]:
    """Return a read-only preflight descriptor for a future finalization executor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_migration_finalization_plan(
        default_artifact_root=effective_root,
        finalization_plan_json=finalization_plan_json,
        finalization_plan_artifact_ref=finalization_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    approval_ledger, approval_ledger_error, approval_ledger_input = _load_or_read_review_approval_ledger(
        default_artifact_root=effective_root,
        review_approval_ledger_json=review_approval_ledger_json,
        review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
    )

    plan_digest = _foldered_canonical_finalization_plan_digest_from_payload(plan)
    expected_approval = _foldered_canonical_finalization_expected_approval(plan_digest=plan_digest, plan=plan)
    approval_evidence = _foldered_canonical_finalization_approval_evidence(
        approval_ledger=approval_ledger,
        expected=expected_approval,
    )
    manifest_revalidation = _foldered_canonical_finalization_manifest_revalidation(
        plan=plan,
        backend_manifest=backend_manifest,
    )
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in planned_updates if isinstance(update, dict)]

    blockers: list[str] = []
    warnings: list[str] = []
    if plan_error:
        blockers.append("foldered_canonical_finalization_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_finalization_plan_not_ready")
    if executor_gate.get("ready_for_foldered_canonical_finalization_preflight_review") is not True:
        blockers.append("foldered_canonical_finalization_plan_preflight_gate_not_ready")
    if not valid_updates:
        blockers.append("foldered_canonical_finalization_plan_has_no_updates")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not manifest_revalidation["all_candidates_still_ready"]:
        blockers.append("backend_manifest_finalization_candidates_not_ready")
    if approval_ledger_error:
        blockers.append("review_approval_ledger_unavailable_or_malformed")
    if not approval_evidence["matching_approval_found"]:
        blockers.append("review_approval_ledger_missing_matching_finalization_approval")
    if not approval_evidence["approved"]:
        blockers.append("review_approval_ledger_does_not_approve_finalization")
    if not plan_digest:
        blockers.append("foldered_canonical_finalization_plan_digest_missing")
    for result in manifest_revalidation["candidate_results"]:
        if result.get("status") != "ready_for_foldered_canonical_finalization_executor_preflight":
            warnings.append(f"foldered_canonical_finalization_candidate:{result.get('artifact_key') or 'unknown'}:{result.get('status') or 'blocked'}")
    if not blockers:
        warnings.append("foldered_canonical_finalization_preflight_ready_for_explicit_reviewed_executor")
        warnings.append("foldered_canonical_finalization_executor_remains_separate_follow_up")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "plan_status": plan.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error else "missing_or_blocked",
            "planned_finalization_update_count": len(valid_updates),
            "manifest_candidate_ready_count": manifest_revalidation["ready_candidate_count"],
            "review_approval_ledger_status": "loaded" if not approval_ledger_error else "missing_or_blocked",
            "matching_review_approval_found": approval_evidence["matching_approval_found"],
            "ready_for_foldered_canonical_finalization_executor_review": status == "ready_for_review",
            "canonical_paths_changed_by_this_tool": False,
            "legacy_fallback_tightened_by_this_tool": False,
            "foldered_canonical_finalized_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "finalization_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "review_approval_ledger_input": approval_ledger_input,
        "plan_summary": _compact_foldered_canonical_finalization_plan(plan),
        "digest_guard": {
            "foldered_canonical_finalization_plan_digest": plan_digest,
            "approval_subject_digest_sha256": approval_evidence.get("subject_digest_sha256") or "",
            "digest_matches_approval": approval_evidence["digest_matches_expected"],
            "requires_executor_revalidation_before_manifest_mutation": True,
        },
        "review_approval_gate": approval_evidence,
        "manifest_revalidation": manifest_revalidation,
        "transaction_journal_plan": {
            "required": True,
            "append_only": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-migration-finalization-journal.json",
            "writes_journal_in_this_tool": False,
            "records_plan_digest": True,
            "records_approval_evidence": True,
            "records_manifest_revalidation": True,
        },
        "idempotency_guard": {
            "required": True,
            "idempotency_key": approval_evidence.get("idempotency_key") or expected_approval["idempotency_key"],
            "checks_existing_finalization_journal_in_this_tool": False,
            "must_block_duplicate_finalization": True,
        },
        "executor_gate": {
            "ready_for_foldered_canonical_finalization_executor_review": status == "ready_for_review",
            "executor_tool": "execute_workspace_foldered_canonical_migration_finalization",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "requires_append_only_transaction_journal": True,
            "requires_idempotency_guard": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_legacy_fallback_tightening_in_this_tool": False,
            "allows_finalization_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_finalization_preflight_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "writes_transaction_journal": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_finalization_plan(
    *,
    default_artifact_root: Path,
    finalization_plan_json: str | None,
    finalization_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(finalization_plan_json, field_name="finalization_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = finalization_plan_artifact_ref or "workspace_foldered_canonical_migration_finalization_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "finalization_plan_not_observed", input_summary


def _foldered_canonical_finalization_plan_digest_from_payload(plan: dict[str, Any]) -> str:
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    digest = str(digest_guard.get("foldered_canonical_finalization_plan_digest") or "")
    if digest:
        return digest
    updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in updates if isinstance(update, dict)]
    return _foldered_canonical_finalization_plan_digest(valid_updates)


def _foldered_canonical_finalization_expected_approval(*, plan_digest: str, plan: dict[str, Any]) -> dict[str, Any]:
    approval_requirements = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    subject_id = str(
        approval_requirements.get("subject_id")
        or (f"workspace-foldered-canonical-finalization:{plan_digest}" if plan_digest else "")
        or "workspace-foldered-canonical-finalization"
    )
    action = str(approval_requirements.get("approval_action") or "foldered_canonical_migration_finalization")
    idempotency_key = plan_digest[:16] if plan_digest else subject_id.rsplit(":", 1)[-1]
    return {
        "subject_id": subject_id,
        "action": action,
        "decision": "approved",
        "plan_digest": plan_digest,
        "idempotency_key": idempotency_key,
    }


def _foldered_canonical_finalization_approval_evidence(
    *,
    approval_ledger: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    entries = approval_ledger.get("entries") if isinstance(approval_ledger.get("entries"), list) else []
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    matching: dict[str, Any] | None = None
    for entry in candidates:
        if entry.get("subject_id") == expected["subject_id"] and entry.get("action") == expected["action"]:
            matching = entry
            break
    approved_status = bool(matching and matching.get("decision") == "approved" and matching.get("status") == "written")
    digest = str((matching or {}).get("subject_digest_sha256") or "")
    digest_matches = bool(digest and expected.get("plan_digest") and digest == expected.get("plan_digest"))
    metadata = matching.get("metadata") if isinstance((matching or {}).get("metadata"), dict) else {}
    return {
        "review_required": True,
        "approval_ledger_artifact": "workspace/review-approval-ledger.json",
        "expected_subject_id": expected["subject_id"],
        "expected_action": expected["action"],
        "expected_decision": expected["decision"],
        "matching_approval_found": matching is not None,
        "approved": bool(approved_status and digest_matches),
        "approval_status": str((matching or {}).get("status") or "missing"),
        "approval_id": str((matching or {}).get("approval_id") or ""),
        "reviewer": str((matching or {}).get("reviewer") or ""),
        "subject_digest_sha256": digest,
        "expected_plan_digest": expected.get("plan_digest") or "",
        "digest_matches_expected": digest_matches,
        "idempotency_key": str(metadata.get("idempotency_key") or expected.get("idempotency_key") or ""),
        "writes_approval_in_this_tool": False,
        "ledger_entry_count": len(candidates),
    }


def _foldered_canonical_finalization_manifest_revalidation(
    *,
    plan: dict[str, Any],
    backend_manifest: dict[str, Any],
) -> dict[str, Any]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    candidate_results: list[dict[str, Any]] = []
    for update in planned_updates:
        if not isinstance(update, dict):
            continue
        key = str(update.get("artifact_key") or "")
        entry = entries_by_key.get(key)
        expected_path = str(update.get("current_canonical_path") or "")
        expected_legacy = str(update.get("legacy_fallback_path") or "")
        expected_virtual_uri = str(update.get("virtual_uri") or "")
        status = "ready_for_foldered_canonical_finalization_executor_preflight"
        blockers: list[str] = []
        alias: dict[str, Any] = {}
        current_path = ""
        legacy_fallback_path = ""
        virtual_uri = ""
        if not key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif not isinstance(entry, dict):
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        else:
            current_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            legacy_fallback_path = str(alias.get("legacy_fallback_path") or "")
            virtual_uri = str(alias.get("virtual_uri") or "")
            if expected_path and current_path != expected_path:
                status = "blocked_manifest_canonical_path_changed"
                blockers.append("manifest_canonical_path_mismatch")
            if expected_legacy and legacy_fallback_path != expected_legacy:
                status = "blocked_legacy_fallback_path_changed"
                blockers.append("legacy_fallback_path_mismatch")
            if expected_virtual_uri and virtual_uri != expected_virtual_uri:
                status = "blocked_virtual_uri_changed"
                blockers.append("virtual_uri_mismatch")
            if not current_path or (legacy_fallback_path and current_path == legacy_fallback_path):
                status = "blocked_canonical_path_not_foldered"
                blockers.append("canonical_path_must_remain_foldered")
            if alias.get("legacy_fallback_tightened") is not True:
                status = "blocked_legacy_fallback_not_tightened"
                blockers.append("legacy_fallback_tightened_required")
            if alias.get("legacy_fallback_preserved") is True:
                status = "blocked_legacy_fallback_still_preserved"
                blockers.append("legacy_fallback_preserved_must_be_false")
            if alias.get("foldered_canonical_finalized") is True:
                status = "blocked_already_finalized"
                blockers.append("finalization_must_not_already_be_applied")
        candidate_results.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": current_path,
                "expected_canonical_path": expected_path,
                "legacy_fallback_path": legacy_fallback_path,
                "expected_legacy_fallback_path": expected_legacy,
                "virtual_uri": virtual_uri,
                "expected_virtual_uri": expected_virtual_uri,
                "legacy_fallback_tightened": bool(alias.get("legacy_fallback_tightened")) if alias else False,
                "legacy_fallback_preserved": bool(alias.get("legacy_fallback_preserved")) if alias else False,
                "foldered_canonical_finalized": bool(alias.get("foldered_canonical_finalized")) if alias else False,
                "blockers": blockers,
                "mutates_manifest_in_this_tool": False,
            }
        )
    ready_count = len(
        [
            result
            for result in candidate_results
            if result.get("status") == "ready_for_foldered_canonical_finalization_executor_preflight"
        ]
    )
    return {
        "required_before_manifest_mutation": True,
        "candidate_count": len(candidate_results),
        "ready_candidate_count": ready_count,
        "all_candidates_still_ready": bool(candidate_results and ready_count == len(candidate_results)),
        "candidate_results": candidate_results,
        "mutates_manifest_in_this_tool": False,
    }


def _compact_foldered_canonical_finalization_plan(plan: dict[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    approval = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    return {
        "schema_version": plan.get("schema_version") or "",
        "status": plan.get("status") or "missing",
        "planned_finalization_update_count": _safe_int(summary.get("planned_finalization_update_count")),
        "plan_only": bool(summary.get("plan_only")),
        "foldered_canonical_finalization_plan_digest": digest_guard.get("foldered_canonical_finalization_plan_digest") or "",
        "ready_for_foldered_canonical_finalization_preflight_review": bool(
            executor_gate.get("ready_for_foldered_canonical_finalization_preflight_review")
        ),
        "approval_subject_id": approval.get("subject_id") or "",
        "approval_action": approval.get("approval_action") or "",
        "blocking_reasons": plan.get("blocking_reasons") if isinstance(plan.get("blocking_reasons"), list) else [],
        "warnings": plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
    }


def _foldered_canonical_finalization_preflight_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_finalization_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_finalization_plan")
    if "foldered_canonical_finalization_plan_not_ready" in blockers or "foldered_canonical_finalization_plan_preflight_gate_not_ready" in blockers:
        actions.append("regenerate_finalization_plan_from_ready_readiness_and_manifest")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "backend_manifest_finalization_candidates_not_ready" in blockers:
        actions.append("refresh_backend_manifest_and_recheck_finalization_candidates")
    if (
        "review_approval_ledger_unavailable_or_malformed" in blockers
        or "review_approval_ledger_missing_matching_finalization_approval" in blockers
    ):
        actions.append("record_review_approval_for_foldered_canonical_finalization")
    if "review_approval_ledger_does_not_approve_finalization" in blockers:
        actions.append("resolve_review_approval_ledger_decision_or_digest_before_finalization")
    if not blockers:
        actions.append("review_finalization_preflight_before_running_separate_executor")
        actions.append("run_separate_explicit_finalization_executor_with_transaction_journal")
    if any("candidate" in warning for warning in warnings):
        actions.append("inspect_blocked_finalization_candidates")
    if any("executor_remains_separate" in warning for warning in warnings):
        actions.append("do_not_finalize_migration_from_preflight_descriptor")
    return list(dict.fromkeys(actions))


def execute_workspace_foldered_canonical_migration_finalization_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    mode: str = "dry-run",
    approve_finalization: bool = False,
    finalization_preflight_json: str | None = None,
    finalization_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_preflight",
    finalization_plan_json: str | None = None,
    finalization_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    expected_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Execute explicit-review-only foldered-canonical migration finalization."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    workspace_dir = effective_root / "workspace"
    result_path = workspace_dir / "workspace-foldered-canonical-migration-finalization-result.json"
    journal_path = workspace_dir / "workspace-foldered-canonical-migration-finalization-journal.json"

    preflight, preflight_error, preflight_input = _load_or_read_workspace_foldered_canonical_migration_finalization_preflight(
        default_artifact_root=effective_root,
        finalization_preflight_json=finalization_preflight_json,
        finalization_preflight_artifact_ref=finalization_preflight_artifact_ref,
    )
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_migration_finalization_plan(
        default_artifact_root=effective_root,
        finalization_plan_json=finalization_plan_json,
        finalization_plan_artifact_ref=finalization_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    requested_mode = mode or "dry-run"
    dry_run_mode = requested_mode == "dry-run"
    apply_mode = requested_mode == "apply"
    created_at = datetime.now(timezone.utc).isoformat()
    plan_digest = _foldered_canonical_finalization_plan_digest_from_payload(plan)
    expected_digest = expected_plan_digest or plan_digest
    preflight_digest = _foldered_canonical_finalization_preflight_plan_digest(preflight)
    approval_gate = preflight.get("review_approval_gate") if isinstance(preflight.get("review_approval_gate"), dict) else {}
    preflight_gate = preflight.get("executor_gate") if isinstance(preflight.get("executor_gate"), dict) else {}
    manifest_revalidation = preflight.get("manifest_revalidation") if isinstance(preflight.get("manifest_revalidation"), dict) else {}
    planned_updates = plan.get("planned_manifest_updates") if isinstance(plan.get("planned_manifest_updates"), list) else []
    valid_updates = [update for update in planned_updates if isinstance(update, dict)]
    idempotency_key = str(approval_gate.get("idempotency_key") or plan_digest[:16] or "foldered-canonical-finalization")
    transaction_id = f"foldered-canonical-finalization-{plan_digest[:16] or 'missing'}"
    existing_journal = _read_foldered_canonical_finalization_journal(journal_path)
    duplicate_entry = _find_foldered_canonical_finalization_duplicate(existing_journal, idempotency_key=idempotency_key)
    manifest_entry_checks = _foldered_canonical_finalization_apply_manifest_entry_checks(
        planned_updates=valid_updates,
        backend_manifest=backend_manifest,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if requested_mode not in {"dry-run", "apply"}:
        blockers.append("unsupported_foldered_canonical_finalization_mode")
    if apply_mode and not approve_finalization:
        blockers.append("apply_requires_approve_finalization_true")
    if preflight_error:
        blockers.append("foldered_canonical_finalization_preflight_unavailable_or_malformed")
    if preflight.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_finalization_preflight_not_ready")
    if preflight_gate.get("ready_for_foldered_canonical_finalization_executor_review") is not True:
        blockers.append("foldered_canonical_finalization_preflight_gate_not_ready")
    if plan_error:
        blockers.append("foldered_canonical_finalization_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_finalization_plan_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if backend_manifest_json is not None and apply_mode:
        blockers.append("apply_requires_backend_manifest_artifact_ref_not_inline_json")
    if not valid_updates:
        blockers.append("foldered_canonical_finalization_has_no_manifest_updates")
    if expected_digest and plan_digest and expected_digest != plan_digest:
        blockers.append("expected_foldered_canonical_finalization_plan_digest_mismatch")
    if preflight_digest and plan_digest and preflight_digest != plan_digest:
        blockers.append("foldered_canonical_finalization_preflight_plan_digest_mismatch")
    if not approval_gate.get("approved"):
        blockers.append("foldered_canonical_finalization_review_approval_not_approved")
    if not approval_gate.get("digest_matches_expected"):
        blockers.append("foldered_canonical_finalization_review_approval_digest_mismatch")
    if manifest_revalidation.get("all_candidates_still_ready") is not True:
        blockers.append("foldered_canonical_finalization_preflight_manifest_revalidation_not_ready")
    if duplicate_entry:
        blockers.append("foldered_canonical_finalization_duplicate_idempotency_key")
    for check in manifest_entry_checks:
        if check.get("status") != "ready":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status')}")
    if not apply_mode:
        warnings.append("foldered_canonical_finalization_dry_run_does_not_write_journal_result_or_manifest")
    if apply_mode and not blockers:
        warnings.append("foldered_canonical_finalization_will_only_update_workspace_alias_metadata")

    status = "blocked" if blockers else "planned" if dry_run_mode else "applied"
    mutated_manifest = _foldered_canonical_finalized_backend_manifest(
        backend_manifest,
        valid_updates,
        transaction_id=transaction_id,
        applied_at=created_at,
    )
    journal_entry = _foldered_canonical_finalization_journal_entry(
        status=status,
        plan_digest=plan_digest,
        preflight_digest=preflight_digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        planned_updates=valid_updates,
        approval_gate=approval_gate,
        blockers=blockers,
        created_at=created_at,
    )
    journal_payload = _foldered_canonical_finalization_journal_payload(
        existing_journal=existing_journal,
        entry=journal_entry,
        append_entry=apply_mode and not blockers,
        updated_at=created_at,
    )
    writes = {
        "backend_manifest": False,
        "journal": False,
        "result": False,
    }
    if apply_mode and not blockers:
        _write_json_file(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input), mutated_manifest)
        _write_json_file(journal_path, journal_payload)
        writes.update({"backend_manifest": True, "journal": True})

    payload = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-result.v1",
        "status": status,
        "mode": requested_mode,
        "artifact_root": str(effective_root),
        "summary": {
            "planned_finalization_update_count": len(valid_updates),
            "manifest_entry_check_count": len(manifest_entry_checks),
            "applied_finalization_update_count": len(valid_updates) if status == "applied" else 0,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "transaction_journal_written": writes["journal"],
            "backend_manifest_mutated": writes["backend_manifest"],
            "result_artifact_written": False,
            "foldered_canonical_finalized": status == "applied",
            "legacy_fallback_tightened": False,
            "canonical_paths_changed": False,
            "files_moved": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "finalization_preflight_input": preflight_input,
        "finalization_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "digest_guard": {
            "expected_plan_digest": expected_digest,
            "current_plan_digest": plan_digest,
            "preflight_plan_digest": preflight_digest,
            "expected_digest_match": bool(expected_digest and plan_digest and expected_digest == plan_digest),
            "preflight_digest_match": bool(preflight_digest and plan_digest and preflight_digest == plan_digest),
        },
        "review_approval_gate": approval_gate,
        "idempotency_guard": {
            "idempotency_key": idempotency_key,
            "duplicate_entry_found": duplicate_entry is not None,
            "duplicate_entry": _compact_foldered_canonical_finalization_journal_entry(duplicate_entry),
            "blocks_duplicate_apply": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "transaction_journal": {
            "path": str(journal_path),
            "append_only": True,
            "entry_count": len(journal_payload.get("entries", [])),
            "entry_appended": writes["journal"],
            "writes_journal_in_apply_mode": writes["journal"],
        },
        "backend_manifest_mutation": {
            "path": str(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input)),
            "mutates_backend_manifest_in_apply_mode": writes["backend_manifest"],
            "changes_canonical_paths": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": status == "applied",
            "files_moved": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_finalization_execute_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "dry_run_is_read_only": True,
            "artifacts_written": apply_mode and not blockers,
            "writes_transaction_journal": writes["journal"],
            "writes_result_artifact": False,
            "creates_directories": apply_mode and not blockers,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": writes["backend_manifest"],
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": status == "applied",
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if apply_mode and not blockers:
        payload["summary"]["result_artifact_written"] = True
        payload["side_effect_policy"]["writes_result_artifact"] = True
        _write_json_file(result_path, payload)
    return payload


def _load_or_read_workspace_foldered_canonical_migration_finalization_preflight(
    *,
    default_artifact_root: Path,
    finalization_preflight_json: str | None,
    finalization_preflight_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(finalization_preflight_json, field_name="finalization_preflight_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = finalization_preflight_artifact_ref or "workspace_foldered_canonical_migration_finalization_preflight"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "finalization_preflight_not_observed", input_summary


def _foldered_canonical_finalization_preflight_plan_digest(preflight: dict[str, Any]) -> str:
    guard = preflight.get("digest_guard") if isinstance(preflight.get("digest_guard"), dict) else {}
    return str(guard.get("foldered_canonical_finalization_plan_digest") or "")


def _foldered_canonical_finalization_apply_manifest_entry_checks(
    *,
    planned_updates: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for update in planned_updates:
        artifact_key = str(update.get("artifact_key") or "")
        expected_path = str(update.get("current_canonical_path") or "")
        expected_legacy = str(update.get("legacy_fallback_path") or "")
        expected_virtual_uri = str(update.get("virtual_uri") or "")
        entry = entries_by_key.get(artifact_key)
        status = "ready"
        observed_path = ""
        observed_legacy = ""
        observed_virtual_uri = ""
        legacy_tightened = False
        legacy_preserved = False
        already_finalized = False
        if not artifact_key:
            status = "missing_artifact_key"
        elif not isinstance(entry, dict):
            status = "manifest_entry_missing"
        else:
            observed_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            observed_legacy = str(alias.get("legacy_fallback_path") or "")
            observed_virtual_uri = str(alias.get("virtual_uri") or "")
            legacy_tightened = alias.get("legacy_fallback_tightened") is True
            legacy_preserved = alias.get("legacy_fallback_preserved") is True
            already_finalized = alias.get("foldered_canonical_finalized") is True
            if expected_path and observed_path != expected_path:
                status = "canonical_path_mismatch"
            elif expected_legacy and observed_legacy != expected_legacy:
                status = "legacy_fallback_path_mismatch"
            elif expected_virtual_uri and observed_virtual_uri != expected_virtual_uri:
                status = "virtual_uri_mismatch"
            elif not observed_path or (observed_legacy and observed_path == observed_legacy):
                status = "canonical_path_not_foldered"
            elif not legacy_tightened:
                status = "legacy_fallback_not_tightened"
            elif legacy_preserved:
                status = "legacy_fallback_still_preserved"
            elif already_finalized:
                status = "already_finalized"
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "expected_canonical_path": expected_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy,
                "observed_legacy_fallback_path": observed_legacy,
                "expected_virtual_uri": expected_virtual_uri,
                "observed_virtual_uri": observed_virtual_uri,
                "legacy_fallback_tightened": legacy_tightened,
                "legacy_fallback_preserved": legacy_preserved,
                "foldered_canonical_finalized": already_finalized,
            }
        )
    return checks


def _foldered_canonical_finalized_backend_manifest(
    backend_manifest: dict[str, Any],
    planned_updates: list[dict[str, Any]],
    *,
    transaction_id: str,
    applied_at: str,
) -> dict[str, Any]:
    manifest = copy.deepcopy(backend_manifest)
    updates_by_key = {
        str(update.get("artifact_key") or ""): update
        for update in planned_updates
        if isinstance(update, dict) and update.get("artifact_key")
    }
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        update = updates_by_key.get(str(entry.get("artifact_key") or ""))
        if not update:
            continue
        metadata = entry.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            entry["metadata"] = metadata
        alias = metadata.setdefault("workspace_alias", {})
        if not isinstance(alias, dict):
            alias = {}
            metadata["workspace_alias"] = alias
        planned_metadata = update.get("planned_metadata_update") if isinstance(update.get("planned_metadata_update"), dict) else {}
        alias["foldered_canonical_finalization_planned"] = bool(
            planned_metadata.get("workspace_alias.foldered_canonical_finalization_planned", True)
        )
        alias["foldered_canonical_finalized"] = True
        alias["migration_status"] = (
            planned_metadata.get("workspace_alias.migration_status")
            or "foldered-canonical-finalized-after-reviewed-apply"
        )
        alias["resolver_migration_status"] = (
            planned_metadata.get("workspace_alias.resolver_migration_status")
            or "foldered-canonical-authoritative"
        )
        alias["foldered_canonical_finalized_at"] = applied_at
        alias["foldered_canonical_finalization_transaction_id"] = transaction_id
    metadata = manifest.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["foldered_canonical_finalization_applied_at"] = applied_at
        metadata["foldered_canonical_finalization_transaction_id"] = transaction_id
    return manifest


def _read_foldered_canonical_finalization_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-journal.v1", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-journal.v1",
            "entries": [],
            "load_error": "malformed_existing_journal",
        }
    if not isinstance(payload, dict):
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-journal.v1", "entries": []}
    if not isinstance(payload.get("entries"), list):
        payload["entries"] = []
    return payload


def _find_foldered_canonical_finalization_duplicate(journal: dict[str, Any], *, idempotency_key: str) -> dict[str, Any] | None:
    for entry in journal.get("entries", []):
        if isinstance(entry, dict) and entry.get("idempotency_key") == idempotency_key and entry.get("status") == "applied":
            return entry
    return None


def _foldered_canonical_finalization_journal_entry(
    *,
    status: str,
    plan_digest: str,
    preflight_digest: str,
    transaction_id: str,
    idempotency_key: str,
    planned_updates: list[dict[str, Any]],
    approval_gate: dict[str, Any],
    blockers: list[str],
    created_at: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "plan_digest": plan_digest,
        "preflight_plan_digest": preflight_digest,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "approval_id": approval_gate.get("approval_id") or "",
        "approval_subject_id": approval_gate.get("expected_subject_id") or "",
        "planned_finalization_update_count": len(planned_updates),
        "artifact_keys": [str(update.get("artifact_key") or "") for update in planned_updates],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "created_at": created_at,
    }


def _foldered_canonical_finalization_journal_payload(
    *,
    existing_journal: dict[str, Any],
    entry: dict[str, Any],
    append_entry: bool,
    updated_at: str,
) -> dict[str, Any]:
    entries = [item for item in existing_journal.get("entries", []) if isinstance(item, dict)]
    if append_entry:
        entries.append(entry)
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-finalization-journal.v1",
        "updated_at": updated_at,
        "entry_count": len(entries),
        "entries": entries,
    }


def _compact_foldered_canonical_finalization_journal_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {
        "status": entry.get("status") or "",
        "plan_digest": entry.get("plan_digest") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "idempotency_key": entry.get("idempotency_key") or "",
        "artifact_keys": entry.get("artifact_keys") if isinstance(entry.get("artifact_keys"), list) else [],
    }


def _foldered_canonical_finalization_execute_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_finalization_preflight_unavailable_or_malformed" in blockers or "foldered_canonical_finalization_preflight_not_ready" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_finalization_preflight")
    if "apply_requires_approve_finalization_true" in blockers:
        actions.append("rerun_with_approve_finalization_true_after_review")
    if "foldered_canonical_finalization_review_approval_not_approved" in blockers or "foldered_canonical_finalization_review_approval_digest_mismatch" in blockers:
        actions.append("resolve_review_approval_ledger_before_finalization_apply")
    if "foldered_canonical_finalization_duplicate_idempotency_key" in blockers:
        actions.append("inspect_existing_finalization_journal_before_retry")
    if any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("refresh_backend_manifest_and_recheck_finalization_preflight")
    if status == "planned":
        actions.append("review_dry_run_then_rerun_apply_with_explicit_approval")
    if status == "applied":
        actions.append("review_foldered_canonical_finalization_result")
        actions.append("keep_canonical_paths_stable_after_finalization")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_migration_post_finalization_audit_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    finalization_result_json: str | None = None,
    finalization_result_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_result",
    finalization_journal_json: str | None = None,
    finalization_journal_artifact_ref: str | None = "workspace_foldered_canonical_migration_finalization_journal",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Audit finalization result, journal, and backend manifest consistency without side effects."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    result, result_error, result_input = _load_or_read_workspace_foldered_canonical_migration_finalization_result(
        default_artifact_root=effective_root,
        finalization_result_json=finalization_result_json,
        finalization_result_artifact_ref=finalization_result_artifact_ref,
    )
    journal, journal_error, journal_input = _load_or_read_workspace_foldered_canonical_migration_finalization_journal(
        default_artifact_root=effective_root,
        finalization_journal_json=finalization_journal_json,
        finalization_journal_artifact_ref=finalization_journal_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    result_summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    result_digest_guard = result.get("digest_guard") if isinstance(result.get("digest_guard"), dict) else {}
    result_checks = result.get("manifest_entry_checks") if isinstance(result.get("manifest_entry_checks"), list) else []
    valid_result_checks = [check for check in result_checks if isinstance(check, dict)]
    transaction_id = str(result_summary.get("transaction_id") or "")
    idempotency_key = str(result_summary.get("idempotency_key") or "")
    plan_digest = str(result_digest_guard.get("current_plan_digest") or result_digest_guard.get("expected_plan_digest") or "")
    journal_entries = journal.get("entries") if isinstance(journal.get("entries"), list) else []
    valid_journal_entries = [entry for entry in journal_entries if isinstance(entry, dict)]
    matching_journal_entry = _find_foldered_canonical_finalization_audit_journal_entry(
        valid_journal_entries,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        plan_digest=plan_digest,
    )
    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    manifest_entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    audit_results = _foldered_canonical_post_finalization_audit_results(
        result_checks=valid_result_checks,
        manifest_entries_by_key=manifest_entries_by_key,
        transaction_id=transaction_id,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if result_error:
        blockers.append("finalization_result_unavailable_or_malformed")
    if result.get("status") != "applied":
        blockers.append("finalization_result_not_applied")
    if result_summary.get("foldered_canonical_finalized") is not True:
        blockers.append("finalization_result_does_not_mark_finalized")
    if result_summary.get("result_artifact_written") is not True:
        blockers.append("finalization_result_artifact_not_written")
    if result_summary.get("backend_manifest_mutated") is not True:
        blockers.append("finalization_result_does_not_mark_backend_manifest_mutated")
    if result_summary.get("canonical_paths_changed") is True:
        blockers.append("finalization_result_reports_canonical_path_change")
    if result_summary.get("files_moved") is True:
        blockers.append("finalization_result_reports_files_moved")
    if result_summary.get("legacy_fallback_tightened") is True:
        blockers.append("finalization_result_reports_legacy_fallback_tightening")
    if journal_error:
        blockers.append("finalization_journal_unavailable_or_malformed")
    if not matching_journal_entry:
        blockers.append("finalization_journal_matching_applied_entry_missing")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not valid_result_checks:
        blockers.append("finalization_result_has_no_manifest_entry_checks")
    manifest_metadata = backend_manifest.get("metadata") if isinstance(backend_manifest.get("metadata"), dict) else {}
    if transaction_id and manifest_metadata.get("foldered_canonical_finalization_transaction_id") != transaction_id:
        blockers.append("backend_manifest_finalization_transaction_id_mismatch")
    if not transaction_id:
        blockers.append("finalization_transaction_id_missing")
    if not idempotency_key:
        blockers.append("finalization_idempotency_key_missing")
    if not plan_digest:
        warnings.append("finalization_plan_digest_missing_from_result")
    for item in audit_results:
        if item.get("status") != "verified":
            blockers.append(f"post_finalization_audit:{item.get('artifact_key') or 'unknown'}:{item.get('status') or 'blocked'}")
        for warning in item.get("warnings") or []:
            warnings.append(f"post_finalization_audit:{item.get('artifact_key') or 'unknown'}:{warning}")
    if not blockers:
        warnings.append("post_finalization_audit_is_read_only_and_does_not_authorize_broader_rollout")

    verified_count = sum(1 for item in audit_results if item.get("status") == "verified")
    status = "verified" if not blockers else "blocked" if result.get("schema_version") != "missing" else "not_ready"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-post-finalization-audit.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "finalization_result_status": result.get("status") or "missing",
            "audit_result_count": len(audit_results),
            "verified_audit_result_count": verified_count,
            "all_finalized_entries_verified": bool(audit_results) and verified_count == len(audit_results),
            "matching_journal_entry_found": matching_journal_entry is not None,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "plan_digest": plan_digest,
            "backend_manifest_transaction_metadata_matches": bool(
                transaction_id and manifest_metadata.get("foldered_canonical_finalization_transaction_id") == transaction_id
            ),
            "canonical_paths_changed_by_finalization": False,
            "files_moved_by_finalization": False,
            "legacy_fallback_tightened_by_finalization": False,
            "artifacts_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "finalization_result_input": result_input,
        "finalization_journal_input": journal_input,
        "backend_manifest_input": backend_manifest_input,
        "finalization_result_summary": _compact_foldered_canonical_finalization_result(result),
        "journal_audit": {
            "entry_count": len(valid_journal_entries),
            "matching_entry_found": matching_journal_entry is not None,
            "matching_entry": _compact_foldered_canonical_finalization_journal_entry(matching_journal_entry),
            "append_only_expected": True,
        },
        "backend_manifest_metadata_audit": {
            "transaction_id": manifest_metadata.get("foldered_canonical_finalization_transaction_id") or "",
            "applied_at": manifest_metadata.get("foldered_canonical_finalization_applied_at") or "",
            "transaction_id_matches_result": bool(
                transaction_id and manifest_metadata.get("foldered_canonical_finalization_transaction_id") == transaction_id
            ),
        },
        "audit_results": audit_results,
        "rollout_gate": {
            "broader_rollout_allowed_by_this_tool": False,
            "automatic_materialization_allowed": False,
            "requires_separate_review_after_audit": True,
            "requires_consumer_readiness_and_delivery_source_recheck": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_post_finalization_audit_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "authorizes_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_finalization_result(
    *,
    default_artifact_root: Path,
    finalization_result_json: str | None,
    finalization_result_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(finalization_result_json, field_name="finalization_result_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = finalization_result_artifact_ref or "workspace_foldered_canonical_migration_finalization_result"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "finalization_result_not_observed", input_summary


def _load_or_read_workspace_foldered_canonical_migration_finalization_journal(
    *,
    default_artifact_root: Path,
    finalization_journal_json: str | None,
    finalization_journal_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(finalization_journal_json, field_name="finalization_journal_json")
    if payload is not None or error:
        if payload is not None:
            if not isinstance(payload.get("entries"), list):
                payload["entries"] = []
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "entries": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = finalization_journal_artifact_ref or "workspace_foldered_canonical_migration_finalization_journal"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        payload = read_result["json"]
        if not isinstance(payload.get("entries"), list):
            payload["entries"] = []
        return payload, "", input_summary
    return {"schema_version": "missing", "status": "missing", "entries": []}, "finalization_journal_not_observed", input_summary


def _find_foldered_canonical_finalization_audit_journal_entry(
    entries: list[dict[str, Any]],
    *,
    transaction_id: str,
    idempotency_key: str,
    plan_digest: str,
) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("status") != "applied":
            continue
        if transaction_id and entry.get("transaction_id") != transaction_id:
            continue
        if idempotency_key and entry.get("idempotency_key") != idempotency_key:
            continue
        if plan_digest and entry.get("plan_digest") != plan_digest:
            continue
        return entry
    return None


def _foldered_canonical_post_finalization_audit_results(
    *,
    result_checks: list[dict[str, Any]],
    manifest_entries_by_key: dict[str, dict[str, Any]],
    transaction_id: str,
) -> list[dict[str, Any]]:
    audit_results: list[dict[str, Any]] = []
    for check in result_checks:
        artifact_key = str(check.get("artifact_key") or "")
        expected_canonical_path = str(check.get("expected_canonical_path") or check.get("observed_canonical_path") or "")
        expected_legacy_path = str(check.get("expected_legacy_fallback_path") or check.get("observed_legacy_fallback_path") or "")
        expected_virtual_uri = str(check.get("expected_virtual_uri") or check.get("observed_virtual_uri") or "")
        entry = manifest_entries_by_key.get(artifact_key) or {}
        observed_path = str(entry.get("path") or "")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        status = "verified"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif not entry:
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        if expected_canonical_path and observed_path and observed_path != expected_canonical_path:
            status = "blocked_canonical_path_changed_after_finalization"
            blockers.append("canonical_path_changed_after_finalization")
        if expected_legacy_path and observed_path and observed_path == expected_legacy_path:
            status = "blocked_canonical_path_regressed_to_legacy"
            blockers.append("canonical_path_regressed_to_legacy")
        if not alias:
            status = "blocked_workspace_alias_missing"
            blockers.append("workspace_alias_metadata_required")
        elif alias.get("foldered_canonical_finalized") is not True:
            status = "blocked_not_finalized"
            blockers.append("foldered_canonical_finalized_required")
        elif transaction_id and alias.get("foldered_canonical_finalization_transaction_id") != transaction_id:
            status = "blocked_transaction_id_mismatch"
            blockers.append("foldered_canonical_finalization_transaction_id_mismatch")
        elif alias.get("resolver_migration_status") != "foldered-canonical-authoritative":
            status = "blocked_resolver_not_authoritative"
            blockers.append("resolver_migration_status_must_be_authoritative")
        elif alias.get("migration_status") != "foldered-canonical-finalized-after-reviewed-apply":
            status = "blocked_migration_status_unexpected"
            blockers.append("migration_status_must_be_finalized_after_reviewed_apply")
        if alias:
            if expected_virtual_uri and str(alias.get("virtual_uri") or "") != expected_virtual_uri:
                status = "blocked_virtual_uri_mismatch"
                blockers.append("virtual_uri_mismatch")
            if alias.get("legacy_fallback_tightened") is not True:
                warnings.append("legacy_fallback_not_marked_tightened_before_finalization")
            if alias.get("legacy_fallback_preserved") is True:
                warnings.append("legacy_fallback_still_preserved_after_finalization")
        audit_results.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "review_required": True,
                "expected_canonical_path": expected_canonical_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy_path,
                "expected_virtual_uri": expected_virtual_uri,
                "observed_virtual_uri": str(alias.get("virtual_uri") or "") if alias else "",
                "foldered_canonical_finalized": alias.get("foldered_canonical_finalized") is True if alias else False,
                "resolver_migration_status": str(alias.get("resolver_migration_status") or "") if alias else "",
                "migration_status": str(alias.get("migration_status") or "") if alias else "",
                "transaction_id_matches": bool(
                    alias and transaction_id and alias.get("foldered_canonical_finalization_transaction_id") == transaction_id
                ),
                "canonical_path_stable_after_finalization": bool(
                    observed_path and expected_canonical_path and observed_path == expected_canonical_path
                ),
                "canonical_path_regressed_to_legacy": bool(observed_path and expected_legacy_path and observed_path == expected_legacy_path),
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return audit_results


def _compact_foldered_canonical_finalization_result(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    digest_guard = result.get("digest_guard") if isinstance(result.get("digest_guard"), dict) else {}
    return {
        "schema_version": result.get("schema_version") or "",
        "status": result.get("status") or "missing",
        "mode": result.get("mode") or "",
        "transaction_id": summary.get("transaction_id") or "",
        "idempotency_key": summary.get("idempotency_key") or "",
        "planned_finalization_update_count": _safe_int(summary.get("planned_finalization_update_count")),
        "applied_finalization_update_count": _safe_int(summary.get("applied_finalization_update_count")),
        "foldered_canonical_finalized": bool(summary.get("foldered_canonical_finalized")),
        "canonical_paths_changed": bool(summary.get("canonical_paths_changed")),
        "files_moved": bool(summary.get("files_moved")),
        "legacy_fallback_tightened": bool(summary.get("legacy_fallback_tightened")),
        "current_plan_digest": digest_guard.get("current_plan_digest") or "",
        "preflight_plan_digest": digest_guard.get("preflight_plan_digest") or "",
    }


def _foldered_canonical_post_finalization_audit_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "finalization_result_unavailable_or_malformed" in blockers or "finalization_result_not_applied" in blockers:
        actions.append("run_or_pass_applied_foldered_canonical_finalization_result")
    if "finalization_journal_unavailable_or_malformed" in blockers or "finalization_journal_matching_applied_entry_missing" in blockers:
        actions.append("inspect_finalization_journal_before_broader_rollout")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_for_post_finalization_audit")
    if any(reason.startswith("post_finalization_audit:") for reason in blockers):
        actions.append("repair_or_reapply_finalization_metadata_before_rollout_review")
    if status == "verified":
        actions.append("review_post_finalization_audit_before_broader_foldered_canonical_rollout")
        actions.append("keep_automatic_materialization_disabled")
    if any("legacy_fallback" in warning for warning in warnings):
        actions.append("review_legacy_fallback_metadata_before_removing_compatibility_paths")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_broader_rollout_readiness_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    post_finalization_audit_json: str | None = None,
    post_finalization_audit_artifact_ref: str | None = "workspace_foldered_canonical_migration_post_finalization_audit",
    readiness_score_json: str | None = None,
    readiness_score_artifact_ref: str | None = "workspace_consumer_readiness_score",
    delivery_source_audit_json: str | None = None,
    expansion_result_json: str | None = None,
    expansion_result_artifact_ref: str | None = "workspace_dual_write_expansion_result",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Review post-finalization evidence before any broader foldered-canonical rollout."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    audit, audit_error, audit_input = _load_or_read_workspace_foldered_canonical_migration_post_finalization_audit(
        default_artifact_root=effective_root,
        post_finalization_audit_json=post_finalization_audit_json,
        post_finalization_audit_artifact_ref=post_finalization_audit_artifact_ref,
    )
    readiness_score, readiness_score_error, readiness_score_input = _load_or_read_workspace_consumer_readiness_score(
        default_artifact_root=effective_root,
        readiness_score_json=readiness_score_json,
        readiness_score_artifact_ref=readiness_score_artifact_ref,
    )
    expansion_result, expansion_result_error, expansion_result_input = _load_or_read_workspace_dual_write_expansion_result(
        default_artifact_root=effective_root,
        expansion_result_json=expansion_result_json,
        expansion_result_artifact_ref=expansion_result_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    delivery_source_audit = _parse_delivery_source_audit(delivery_source_audit_json)
    delivery_source_summary = _summarize_delivery_source_audit_payload(delivery_source_audit)

    audit_summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    audit_results = audit.get("audit_results") if isinstance(audit.get("audit_results"), list) else []
    valid_audit_results = [item for item in audit_results if isinstance(item, dict)]
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    expansion_summary = expansion_result.get("summary") if isinstance(expansion_result.get("summary"), dict) else {}
    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    finalized_manifest_entries = _foldered_canonical_finalized_manifest_entry_count(manifest_entries)
    blocker_inputs = {
        "post_finalization_audit": audit,
        "post_finalization_audit_error": audit_error,
        "readiness_score": readiness_score,
        "readiness_score_error": readiness_score_error,
        "delivery_source_summary": delivery_source_summary,
        "expansion_result": expansion_result,
        "expansion_result_error": expansion_result_error,
        "backend_manifest_error": backend_manifest_error,
        "finalized_manifest_entries": finalized_manifest_entries,
        "audit_result_count": len(valid_audit_results),
    }
    blockers = _foldered_canonical_broader_rollout_readiness_blockers(blocker_inputs)
    warnings = _foldered_canonical_broader_rollout_readiness_warnings(blocker_inputs)
    status = "ready_for_review" if not blockers else "not_ready" if audit.get("schema_version") == "missing" else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-readiness.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "post_finalization_audit_status": audit.get("status") or "missing",
            "consumer_readiness_status": readiness_score.get("status") or "missing",
            "delivery_source_audit_status": delivery_source_summary["status"],
            "dual_write_expansion_result_status": expansion_result.get("status") or "missing",
            "backend_manifest_entry_count": len([entry for entry in manifest_entries if isinstance(entry, dict)]),
            "finalized_manifest_entry_count": finalized_manifest_entries,
            "audit_result_count": len(valid_audit_results),
            "verified_audit_result_count": _safe_int(audit_summary.get("verified_audit_result_count")),
            "planned_expansion_candidate_count": _safe_int(expansion_summary.get("planned_candidate_count")),
            "verified_expansion_candidate_count": _safe_int(expansion_summary.get("verified_candidate_count")),
            "broader_rollout_review_allowed": not blockers,
            "broader_rollout_authorized_by_this_tool": False,
            "automatic_materialization_allowed": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "post_finalization_audit_input": audit_input,
        "readiness_score_input": readiness_score_input,
        "delivery_source_audit_input": {"source": "inline-json" if delivery_source_audit_json else "missing"},
        "expansion_result_input": expansion_result_input,
        "backend_manifest_input": backend_manifest_input,
        "post_finalization_audit_summary": _compact_foldered_canonical_post_finalization_audit(audit),
        "readiness_score_summary": _compact_workspace_consumer_score(readiness_score),
        "delivery_source_audit_summary": delivery_source_summary,
        "expansion_result_summary": _compact_workspace_dual_write_expansion_result(expansion_result),
        "readiness_checks": {
            "post_finalization_audit_verified": audit.get("status") == "verified",
            "consumer_readiness_ready_for_foldered_canonical_review": bool(
                readiness_score.get("status") == "ready_for_foldered_canonical_review"
                and readiness.get("foldered_canonical_migration_allowed") is True
            ),
            "delivery_source_recheck_clean": bool(
                delivery_source_summary["status"] == "observed"
                and delivery_source_summary["source_path_count"] == 0
                and delivery_source_summary["external_source_path_count"] == 0
            ),
            "dual_write_expansion_result_verified": expansion_result.get("status") == "verified",
            "current_manifest_observed": not backend_manifest_error,
            "manifest_finalization_metadata_observed": finalized_manifest_entries >= len(valid_audit_results) and bool(valid_audit_results),
        },
        "rollout_gate": {
            "broader_rollout_plan_allowed_for_review": not blockers,
            "broader_rollout_apply_allowed_by_this_tool": False,
            "automatic_materialization_allowed": False,
            "requires_separate_broader_rollout_plan": True,
            "requires_separate_review_approval": True,
            "requires_fresh_consumer_readiness_recheck": True,
            "requires_fresh_delivery_source_audit": True,
            "requires_explicit_apply_tool_after_plan": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_readiness_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "finalizes_foldered_canonical_migration": False,
            "authorizes_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_migration_post_finalization_audit(
    *,
    default_artifact_root: Path,
    post_finalization_audit_json: str | None,
    post_finalization_audit_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(post_finalization_audit_json, field_name="post_finalization_audit_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = post_finalization_audit_artifact_ref or "workspace_foldered_canonical_migration_post_finalization_audit"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "post_finalization_audit_not_observed", input_summary


def _load_or_read_workspace_consumer_readiness_score(
    *,
    default_artifact_root: Path,
    readiness_score_json: str | None,
    readiness_score_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(readiness_score_json, field_name="readiness_score_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = readiness_score_artifact_ref or "workspace_consumer_readiness_score"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing", "readiness": {}}, "workspace_consumer_readiness_score_not_observed", input_summary


def _foldered_canonical_finalized_manifest_entry_count(entries: list[Any]) -> int:
    count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        if alias.get("foldered_canonical_finalized") is True:
            count += 1
    return count


def _foldered_canonical_broader_rollout_readiness_blockers(inputs: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    audit = inputs["post_finalization_audit"]
    readiness_score = inputs["readiness_score"]
    delivery_source_summary = inputs["delivery_source_summary"]
    expansion_result = inputs["expansion_result"]
    readiness = readiness_score.get("readiness") if isinstance(readiness_score.get("readiness"), dict) else {}
    if inputs["post_finalization_audit_error"]:
        blockers.append("post_finalization_audit_unavailable_or_malformed")
    if audit.get("status") != "verified":
        blockers.append("post_finalization_audit_not_verified")
    if inputs["readiness_score_error"]:
        blockers.append("workspace_consumer_readiness_score_unavailable_or_malformed")
    if readiness_score.get("status") != "ready_for_foldered_canonical_review" or readiness.get("foldered_canonical_migration_allowed") is not True:
        blockers.append("workspace_consumer_readiness_not_ready_for_broader_rollout")
    if delivery_source_summary["status"] == "missing":
        blockers.append("delivery_source_audit_recheck_missing")
    elif delivery_source_summary["status"] == "malformed":
        blockers.append("delivery_source_audit_recheck_malformed")
    if delivery_source_summary["source_path_count"] > 0:
        blockers.append("delivery_source_audit_source_path_usage_observed")
    if delivery_source_summary["external_source_path_count"] > 0:
        blockers.append("delivery_source_audit_external_source_path_usage_observed")
    if inputs["expansion_result_error"]:
        blockers.append("workspace_dual_write_expansion_result_unavailable_or_malformed")
    if expansion_result.get("status") != "verified":
        blockers.append("workspace_dual_write_expansion_result_not_verified")
    if inputs["backend_manifest_error"]:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if inputs["audit_result_count"] <= 0:
        blockers.append("post_finalization_audit_has_no_verified_scope")
    if inputs["finalized_manifest_entries"] < inputs["audit_result_count"]:
        blockers.append("backend_manifest_finalized_entry_count_below_audit_scope")
    return blockers


def _foldered_canonical_broader_rollout_readiness_warnings(inputs: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    expansion_result = inputs["expansion_result"]
    expansion_summary = expansion_result.get("summary") if isinstance(expansion_result.get("summary"), dict) else {}
    if _safe_int(expansion_summary.get("medium_risk_observed_count")) > 0:
        warnings.append("medium_risk_expansion_artifacts_require_explicit_broader_rollout_review")
    if _safe_int(expansion_summary.get("high_risk_observed_count")) > 0:
        warnings.append("high_risk_expansion_artifacts_require_separate_broader_rollout_track")
    if not warnings and not _foldered_canonical_broader_rollout_readiness_blockers(inputs):
        warnings.append("readiness_descriptor_does_not_authorize_broader_rollout_apply")
    return warnings


def _compact_foldered_canonical_post_finalization_audit(audit: dict[str, Any]) -> dict[str, Any]:
    summary = audit.get("summary") if isinstance(audit.get("summary"), dict) else {}
    rollout_gate = audit.get("rollout_gate") if isinstance(audit.get("rollout_gate"), dict) else {}
    return {
        "schema_version": audit.get("schema_version") or "",
        "status": audit.get("status") or "missing",
        "audit_result_count": _safe_int(summary.get("audit_result_count")),
        "verified_audit_result_count": _safe_int(summary.get("verified_audit_result_count")),
        "all_finalized_entries_verified": bool(summary.get("all_finalized_entries_verified")),
        "matching_journal_entry_found": bool(summary.get("matching_journal_entry_found")),
        "backend_manifest_transaction_metadata_matches": bool(summary.get("backend_manifest_transaction_metadata_matches")),
        "broader_rollout_allowed_by_audit_tool": bool(rollout_gate.get("broader_rollout_allowed_by_this_tool")),
        "automatic_materialization_allowed": bool(rollout_gate.get("automatic_materialization_allowed")),
        "blocking_reasons": audit.get("blocking_reasons") if isinstance(audit.get("blocking_reasons"), list) else [],
        "warnings": audit.get("warnings") if isinstance(audit.get("warnings"), list) else [],
    }


def _foldered_canonical_broader_rollout_readiness_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "post_finalization_audit_unavailable_or_malformed" in blockers or "post_finalization_audit_not_verified" in blockers:
        actions.append("run_verified_post_finalization_audit_before_broader_rollout_readiness")
    if "workspace_consumer_readiness_score_unavailable_or_malformed" in blockers or "workspace_consumer_readiness_not_ready_for_broader_rollout" in blockers:
        actions.append("recheck_workspace_consumer_readiness_before_broader_rollout")
    if any(reason.startswith("delivery_source_audit_") for reason in blockers):
        actions.append("run_fresh_delivery_source_audit_without_workspace_source_path_usage")
    if "workspace_dual_write_expansion_result_unavailable_or_malformed" in blockers or "workspace_dual_write_expansion_result_not_verified" in blockers:
        actions.append("verify_dual_write_expansion_result_before_broader_rollout_readiness")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "backend_manifest_finalized_entry_count_below_audit_scope" in blockers:
        actions.append("provide_current_backend_manifest_with_finalized_workspace_alias_metadata")
    if status == "ready_for_review":
        actions.append("prepare_separate_review_only_broader_rollout_plan")
        actions.append("keep_broader_rollout_apply_and_automatic_materialization_disabled")
    if any("risk" in warning for warning in warnings):
        actions.append("split_medium_or_high_risk_artifacts_into_separate_rollout_reviews")
    return list(dict.fromkeys(actions))


def plan_workspace_foldered_canonical_broader_rollout_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    broader_rollout_readiness_json: str | None = None,
    broader_rollout_readiness_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_readiness",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    artifact_keys_json: str | None = None,
    max_artifacts: int = 32,
    include_medium_risk: bool = False,
) -> dict[str, Any]:
    """Plan a broader foldered-canonical rollout review scope without side effects."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness, readiness_error, readiness_input = _load_or_read_workspace_foldered_canonical_broader_rollout_readiness(
        default_artifact_root=effective_root,
        broader_rollout_readiness_json=broader_rollout_readiness_json,
        broader_rollout_readiness_artifact_ref=broader_rollout_readiness_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    explicit_selection = requested_keys is not None
    max_count = max(0, int(max_artifacts))
    candidates, unknown_keys = _foldered_canonical_broader_rollout_candidates(
        backend_manifest=backend_manifest,
        requested_keys=requested_keys,
        max_artifacts=max_count,
        include_medium_risk=include_medium_risk,
    )
    ready_candidates = [item for item in candidates if item.get("status") == "ready_for_broader_rollout_plan_review"]
    blocked_candidates = [item for item in candidates if item.get("status") != "ready_for_broader_rollout_plan_review"]
    high_risk_candidates = [item.get("artifact_key") or "" for item in candidates if item.get("risk", {}).get("risk_level") == "high"]
    medium_risk_candidates = [item.get("artifact_key") or "" for item in candidates if item.get("risk", {}).get("risk_level") == "medium"]
    plan_digest = _foldered_canonical_broader_rollout_plan_digest(ready_candidates)

    blockers: list[str] = []
    warnings: list[str] = []
    rollout_gate = readiness.get("rollout_gate") if isinstance(readiness.get("rollout_gate"), dict) else {}
    if readiness_error:
        blockers.append("broader_rollout_readiness_unavailable_or_malformed")
    if readiness.get("status") != "ready_for_review":
        blockers.append("broader_rollout_readiness_not_ready_for_plan")
    if rollout_gate.get("broader_rollout_plan_allowed_for_review") is not True:
        blockers.append("broader_rollout_readiness_gate_does_not_allow_plan_review")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if high_risk_candidates:
        blockers.append("high_risk_artifacts_require_separate_broader_rollout_review")
    if medium_risk_candidates and not include_medium_risk:
        blockers.append("medium_risk_artifacts_require_explicit_include_medium_risk")
    if blocked_candidates:
        blockers.append("blocked_broader_rollout_candidates_present")
    if not ready_candidates:
        blockers.append("no_broader_rollout_candidates_selected")
    if medium_risk_candidates and include_medium_risk:
        warnings.append("medium_risk_artifacts_selected_for_broader_rollout_review")
    if not blockers:
        warnings.append("broader_rollout_plan_is_review_only_and_does_not_authorize_apply")

    status = "ready_for_review" if not blockers else "blocked" if readiness.get("schema_version") != "missing" else "not_ready"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "planned_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "candidate_count": len(candidates),
            "ready_candidate_count": len(ready_candidates),
            "blocked_candidate_count": len(blocked_candidates),
            "readiness_status": readiness.get("status") or "missing",
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "high_risk_candidate_count": len([key for key in high_risk_candidates if key]),
            "medium_risk_candidate_count": len([key for key in medium_risk_candidates if key]),
            "explicit_selection": explicit_selection,
            "max_artifacts": max_count,
            "plan_digest": plan_digest,
            "review_required": True,
            "broader_rollout_apply_authorized": False,
            "automatic_materialization_allowed": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_source": "finalized_backend_manifest_workspace_alias_entries",
            "requires_broader_rollout_readiness": True,
            "requires_readiness_status_ready_for_review": True,
            "requires_current_backend_manifest_revalidation": True,
            "explicit_keys_must_be_finalized_manifest_entries": True,
            "default_allows_medium_risk": False,
            "include_medium_risk_requested": bool(include_medium_risk),
            "high_risk_artifacts_block_plan": True,
            "plan_only": True,
            "actual_rollout_enabled": False,
            "manifest_mutation_enabled": False,
            "automatic_materialization_enabled": False,
        },
        "broader_rollout_readiness_input": readiness_input,
        "backend_manifest_input": backend_manifest_input,
        "broader_rollout_readiness_summary": _compact_foldered_canonical_broader_rollout_readiness(readiness),
        "candidate_artifacts": candidates,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "high_risk_artifact_keys": [key for key in high_risk_candidates if key],
            "medium_risk_artifact_keys": [key for key in medium_risk_candidates if key],
            "blocked_candidate_artifact_keys": [str(item.get("artifact_key") or "") for item in blocked_candidates],
        },
        "digest_guard": {
            "broader_rollout_plan_digest": plan_digest,
            "requires_plan_digest_match_before_apply": True,
            "requires_backend_manifest_revalidation_before_apply": True,
        },
        "approval_requirements": {
            "required_before_apply": True,
            "approval_action": "foldered_canonical_broader_rollout",
            "subject_id": f"workspace-foldered-canonical-broader-rollout:{plan_digest}" if plan_digest else "workspace-foldered-canonical-broader-rollout",
            "subject_digest_sha256": plan_digest,
            "records_approval_in_this_tool": False,
        },
        "executor_gate": {
            "ready_for_broader_rollout_apply_review": status == "ready_for_review",
            "preflight_tool": "review_workspace_foldered_canonical_broader_rollout_preflight",
            "preflight_tool_implemented": True,
            "executor_tool": "execute_workspace_foldered_canonical_broader_rollout",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "allows_automatic_execution": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_dual_write_enablement_in_this_tool": False,
            "allows_rollout_apply_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_plan_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "authorizes_broader_rollout": False,
            "applies_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_broader_rollout_readiness(
    *,
    default_artifact_root: Path,
    broader_rollout_readiness_json: str | None,
    broader_rollout_readiness_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_readiness_json, field_name="broader_rollout_readiness_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_readiness_artifact_ref or "workspace_foldered_canonical_broader_rollout_readiness"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "broader_rollout_readiness_not_observed", input_summary


def _foldered_canonical_broader_rollout_candidates(
    *,
    backend_manifest: dict[str, Any],
    requested_keys: list[str] | None,
    max_artifacts: int,
    include_medium_risk: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    finalized_entries: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("artifact_key") or "")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        if key and alias.get("foldered_canonical_finalized") is True:
            finalized_entries[key] = entry
    selected_keys = requested_keys if requested_keys is not None else sorted(finalized_entries)
    unknown_keys = [key for key in selected_keys if key not in finalized_entries]
    selected_keys = [key for key in selected_keys if key in finalized_entries]
    if max_artifacts:
        selected_keys = selected_keys[:max_artifacts]
    elif max_artifacts == 0:
        selected_keys = []

    candidates: list[dict[str, Any]] = []
    for key in selected_keys:
        entry = finalized_entries[key]
        route = routes_by_key.get(key)
        risk = _dual_write_route_risk(route) if route is not None else {
            "risk_level": "high",
            "rationale": "manifest entry has no registered workspace route",
            "category": "",
            "producer_roles": [],
        }
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        status = "ready_for_broader_rollout_plan_review"
        blockers: list[str] = []
        warnings: list[str] = []
        if route is None:
            status = "blocked_unknown_workspace_route"
            blockers.append("registered_workspace_route_required")
        elif risk["risk_level"] == "high":
            status = "blocked_high_risk_artifact"
            blockers.append("high_risk_artifact_requires_separate_review")
        elif risk["risk_level"] == "medium" and not include_medium_risk:
            status = "blocked_medium_risk_not_explicitly_included"
            blockers.append("medium_risk_artifact_requires_include_medium_risk")
        if alias.get("resolver_migration_status") != "foldered-canonical-authoritative":
            status = "blocked_resolver_not_authoritative"
            blockers.append("resolver_migration_status_must_be_authoritative")
        if alias.get("migration_status") != "foldered-canonical-finalized-after-reviewed-apply":
            status = "blocked_unexpected_migration_status"
            blockers.append("migration_status_must_be_finalized_after_reviewed_apply")
        if not entry.get("path"):
            status = "blocked_missing_canonical_path"
            blockers.append("canonical_path_required")
        if risk["risk_level"] == "medium" and include_medium_risk:
            warnings.append("medium_risk_artifact_selected_for_explicit_review")
        candidates.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": str(entry.get("path") or ""),
                "legacy_fallback_path": str(alias.get("legacy_fallback_path") or ""),
                "future_path": str(alias.get("future_path") or ""),
                "virtual_uri": str(alias.get("virtual_uri") or ""),
                "category": route.category if route is not None else "",
                "producer_roles": list(route.producer_roles) if route is not None else [],
                "risk": risk,
                "review_required": True,
                "planned_rollout": {
                    "broader_rollout_scope": "foldered-canonical-finalized-workspace-artifact",
                    "consumer_readiness_recheck_required": True,
                    "delivery_source_recheck_required": True,
                    "manifest_revalidation_required": True,
                    "apply_enabled_in_this_tool": False,
                },
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return candidates, unknown_keys


def _foldered_canonical_broader_rollout_plan_digest(ready_candidates: list[dict[str, Any]]) -> str:
    if not ready_candidates:
        return ""
    digest_input = [
        {
            "artifact_key": item.get("artifact_key") or "",
            "current_canonical_path": item.get("current_canonical_path") or "",
            "future_path": item.get("future_path") or "",
            "virtual_uri": item.get("virtual_uri") or "",
            "planned_rollout": item.get("planned_rollout") or {},
        }
        for item in ready_candidates
    ]
    return hashlib.sha256(json.dumps(digest_input, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _compact_foldered_canonical_broader_rollout_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    summary = readiness.get("summary") if isinstance(readiness.get("summary"), dict) else {}
    rollout_gate = readiness.get("rollout_gate") if isinstance(readiness.get("rollout_gate"), dict) else {}
    return {
        "schema_version": readiness.get("schema_version") or "",
        "status": readiness.get("status") or "missing",
        "broader_rollout_review_allowed": bool(summary.get("broader_rollout_review_allowed")),
        "broader_rollout_authorized_by_this_tool": bool(summary.get("broader_rollout_authorized_by_this_tool")),
        "broader_rollout_plan_allowed_for_review": bool(rollout_gate.get("broader_rollout_plan_allowed_for_review")),
        "broader_rollout_apply_allowed_by_this_tool": bool(rollout_gate.get("broader_rollout_apply_allowed_by_this_tool")),
        "automatic_materialization_allowed": bool(rollout_gate.get("automatic_materialization_allowed")),
        "blocking_reasons": readiness.get("blocking_reasons") if isinstance(readiness.get("blocking_reasons"), list) else [],
        "warnings": readiness.get("warnings") if isinstance(readiness.get("warnings"), list) else [],
    }


def _foldered_canonical_broader_rollout_plan_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "broader_rollout_readiness_unavailable_or_malformed" in blockers or "broader_rollout_readiness_not_ready_for_plan" in blockers:
        actions.append("run_verified_broader_rollout_readiness_before_planning")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_for_broader_rollout_plan")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_broader_rollout_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("restrict_broader_rollout_plan_to_finalized_manifest_artifact_keys")
    if "high_risk_artifacts_require_separate_broader_rollout_review" in blockers:
        actions.append("split_high_risk_artifacts_into_separate_broader_rollout_track")
    if "medium_risk_artifacts_require_explicit_include_medium_risk" in blockers:
        actions.append("set_include_medium_risk_only_after_explicit_review")
    if "blocked_broader_rollout_candidates_present" in blockers:
        actions.append("repair_or_exclude_blocked_broader_rollout_candidates")
    if "no_broader_rollout_candidates_selected" in blockers:
        actions.append("select_finalized_low_risk_artifacts_for_broader_rollout_plan")
    if status == "ready_for_review":
        actions.append("review_broader_rollout_plan_before_any_apply_mode_follow_up")
        actions.append("keep_broader_rollout_apply_and_automatic_materialization_disabled")
    if any("medium_risk" in warning for warning in warnings):
        actions.append("review_medium_risk_artifacts_before_broader_rollout_apply")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_broader_rollout_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    broader_rollout_plan_json: str | None = None,
    broader_rollout_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    review_approval_ledger_json: str | None = None,
    review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
) -> dict[str, Any]:
    """Return a read-only preflight descriptor for a future broader rollout executor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_broader_rollout_plan(
        default_artifact_root=effective_root,
        broader_rollout_plan_json=broader_rollout_plan_json,
        broader_rollout_plan_artifact_ref=broader_rollout_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    approval_ledger, approval_ledger_error, approval_ledger_input = _load_or_read_review_approval_ledger(
        default_artifact_root=effective_root,
        review_approval_ledger_json=review_approval_ledger_json,
        review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
    )

    plan_digest = _foldered_canonical_broader_rollout_plan_digest_from_payload(plan)
    expected_approval = _foldered_canonical_broader_rollout_expected_approval(plan_digest=plan_digest, plan=plan)
    approval_evidence = _foldered_canonical_broader_rollout_approval_evidence(
        approval_ledger=approval_ledger,
        expected=expected_approval,
    )
    manifest_revalidation = _foldered_canonical_broader_rollout_manifest_revalidation(
        plan=plan,
        backend_manifest=backend_manifest,
    )
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    candidate_artifacts = plan.get("candidate_artifacts") if isinstance(plan.get("candidate_artifacts"), list) else []
    valid_candidates = [candidate for candidate in candidate_artifacts if isinstance(candidate, dict)]

    blockers: list[str] = []
    warnings: list[str] = []
    if plan_error:
        blockers.append("broader_rollout_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("broader_rollout_plan_not_ready")
    if executor_gate.get("ready_for_broader_rollout_apply_review") is not True:
        blockers.append("broader_rollout_plan_apply_gate_not_ready")
    if executor_gate.get("preflight_tool_implemented") is not True:
        blockers.append("broader_rollout_plan_preflight_gate_not_implemented")
    if not valid_candidates:
        blockers.append("broader_rollout_plan_has_no_candidates")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not manifest_revalidation["all_candidates_still_ready"]:
        blockers.append("backend_manifest_broader_rollout_candidates_not_ready")
    if approval_ledger_error:
        blockers.append("review_approval_ledger_unavailable_or_malformed")
    if not approval_evidence["matching_approval_found"]:
        blockers.append("review_approval_ledger_missing_matching_broader_rollout_approval")
    if not approval_evidence["approved"]:
        blockers.append("review_approval_ledger_does_not_approve_broader_rollout")
    if not plan_digest:
        blockers.append("broader_rollout_plan_digest_missing")
    for result in manifest_revalidation["candidate_results"]:
        if result.get("status") != "ready_for_broader_rollout_executor_preflight":
            warnings.append(f"broader_rollout_candidate:{result.get('artifact_key') or 'unknown'}:{result.get('status') or 'blocked'}")
    if not blockers:
        warnings.append("broader_rollout_preflight_ready_for_explicit_reviewed_executor")
        warnings.append("broader_rollout_executor_remains_separate_follow_up")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "plan_status": plan.get("status") or "missing",
            "backend_manifest_status": "loaded" if not backend_manifest_error else "missing_or_blocked",
            "planned_broader_rollout_candidate_count": len(valid_candidates),
            "manifest_candidate_ready_count": manifest_revalidation["ready_candidate_count"],
            "review_approval_ledger_status": "loaded" if not approval_ledger_error else "missing_or_blocked",
            "matching_review_approval_found": approval_evidence["matching_approval_found"],
            "ready_for_broader_rollout_executor_review": status == "ready_for_review",
            "broader_rollout_apply_executed_by_this_tool": False,
            "canonical_paths_changed_by_this_tool": False,
            "dual_write_enabled_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "broader_rollout_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "review_approval_ledger_input": approval_ledger_input,
        "plan_summary": _compact_foldered_canonical_broader_rollout_plan(plan),
        "digest_guard": {
            "broader_rollout_plan_digest": plan_digest,
            "approval_subject_digest_sha256": approval_evidence.get("subject_digest_sha256") or "",
            "digest_matches_approval": approval_evidence["digest_matches_expected"],
            "requires_executor_revalidation_before_manifest_mutation": True,
            "requires_backend_manifest_revalidation_before_apply": True,
        },
        "review_approval_gate": approval_evidence,
        "manifest_revalidation": manifest_revalidation,
        "transaction_journal_plan": {
            "required": True,
            "append_only": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-broader-rollout-journal.json",
            "writes_journal_in_this_tool": False,
            "records_plan_digest": True,
            "records_approval_evidence": True,
            "records_manifest_revalidation": True,
        },
        "idempotency_guard": {
            "required": True,
            "idempotency_key": approval_evidence.get("idempotency_key") or expected_approval["idempotency_key"],
            "checks_existing_broader_rollout_journal_in_this_tool": False,
            "must_block_duplicate_broader_rollout_apply": True,
        },
        "result_artifact_plan": {
            "required_after_apply": True,
            "result_artifact": "workspace/workspace-foldered-canonical-broader-rollout-result.json",
            "writes_result_in_this_tool": False,
            "records_candidate_count": True,
            "records_manifest_revalidation": True,
            "records_approval_evidence": True,
        },
        "executor_gate": {
            "ready_for_broader_rollout_executor_review": status == "ready_for_review",
            "executor_tool": "execute_workspace_foldered_canonical_broader_rollout",
            "executor_tool_implemented": True,
            "requires_explicit_review_approval": True,
            "requires_current_backend_manifest_revalidation": True,
            "requires_append_only_transaction_journal": True,
            "requires_idempotency_guard": True,
            "allows_automatic_execution": False,
            "allows_journal_write_in_this_tool": False,
            "allows_result_write_in_this_tool": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_dual_write_enablement_in_this_tool": False,
            "allows_broader_rollout_apply_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_preflight_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "writes_transaction_journal": False,
            "writes_result_artifact": False,
            "tightens_legacy_fallback": False,
            "authorizes_broader_rollout": False,
            "applies_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_broader_rollout_plan(
    *,
    default_artifact_root: Path,
    broader_rollout_plan_json: str | None,
    broader_rollout_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_plan_json, field_name="broader_rollout_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_plan_artifact_ref or "workspace_foldered_canonical_broader_rollout_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "broader_rollout_plan_not_observed", input_summary


def _foldered_canonical_broader_rollout_plan_digest_from_payload(plan: dict[str, Any]) -> str:
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    digest = str(digest_guard.get("broader_rollout_plan_digest") or "")
    if digest:
        return digest
    candidates = plan.get("candidate_artifacts") if isinstance(plan.get("candidate_artifacts"), list) else []
    ready_candidates = [
        candidate
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("status") == "ready_for_broader_rollout_plan_review"
    ]
    return _foldered_canonical_broader_rollout_plan_digest(ready_candidates)


def _foldered_canonical_broader_rollout_expected_approval(*, plan_digest: str, plan: dict[str, Any]) -> dict[str, Any]:
    approval_requirements = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    subject_id = str(
        approval_requirements.get("subject_id")
        or (f"workspace-foldered-canonical-broader-rollout:{plan_digest}" if plan_digest else "")
        or "workspace-foldered-canonical-broader-rollout"
    )
    action = str(approval_requirements.get("approval_action") or "foldered_canonical_broader_rollout")
    idempotency_key = plan_digest[:16] if plan_digest else subject_id.rsplit(":", 1)[-1]
    return {
        "subject_id": subject_id,
        "action": action,
        "decision": "approved",
        "plan_digest": plan_digest,
        "idempotency_key": idempotency_key,
    }


def _foldered_canonical_broader_rollout_approval_evidence(
    *,
    approval_ledger: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    entries = approval_ledger.get("entries") if isinstance(approval_ledger.get("entries"), list) else []
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    matching: dict[str, Any] | None = None
    for entry in candidates:
        if entry.get("subject_id") == expected["subject_id"] and entry.get("action") == expected["action"]:
            matching = entry
            break
    approved_status = bool(matching and matching.get("decision") == "approved" and matching.get("status") == "written")
    digest = str((matching or {}).get("subject_digest_sha256") or "")
    digest_matches = bool(digest and expected.get("plan_digest") and digest == expected.get("plan_digest"))
    metadata = matching.get("metadata") if isinstance((matching or {}).get("metadata"), dict) else {}
    return {
        "review_required": True,
        "approval_ledger_artifact": "workspace/review-approval-ledger.json",
        "expected_subject_id": expected["subject_id"],
        "expected_action": expected["action"],
        "expected_decision": expected["decision"],
        "matching_approval_found": matching is not None,
        "approved": bool(approved_status and digest_matches),
        "approval_status": str((matching or {}).get("status") or "missing"),
        "approval_id": str((matching or {}).get("approval_id") or ""),
        "reviewer": str((matching or {}).get("reviewer") or ""),
        "subject_digest_sha256": digest,
        "expected_plan_digest": expected.get("plan_digest") or "",
        "digest_matches_expected": digest_matches,
        "idempotency_key": str(metadata.get("idempotency_key") or expected.get("idempotency_key") or ""),
        "writes_approval_in_this_tool": False,
        "ledger_entry_count": len(candidates),
    }


def _foldered_canonical_broader_rollout_manifest_revalidation(
    *,
    plan: dict[str, Any],
    backend_manifest: dict[str, Any],
) -> dict[str, Any]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    planned_candidates = plan.get("candidate_artifacts") if isinstance(plan.get("candidate_artifacts"), list) else []
    candidate_results: list[dict[str, Any]] = []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    for candidate in planned_candidates:
        if not isinstance(candidate, dict):
            continue
        key = str(candidate.get("artifact_key") or "")
        entry = entries_by_key.get(key)
        route = routes_by_key.get(key)
        expected_path = str(candidate.get("current_canonical_path") or "")
        expected_legacy = str(candidate.get("legacy_fallback_path") or "")
        expected_future_path = str(candidate.get("future_path") or "")
        expected_virtual_uri = str(candidate.get("virtual_uri") or "")
        status = "ready_for_broader_rollout_executor_preflight"
        blockers: list[str] = []
        alias: dict[str, Any] = {}
        current_path = ""
        legacy_fallback_path = ""
        future_path = ""
        virtual_uri = ""
        if not key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif candidate.get("status") != "ready_for_broader_rollout_plan_review":
            status = "blocked_plan_candidate_not_ready"
            blockers.append("plan_candidate_must_be_ready")
        elif route is None:
            status = "blocked_registered_workspace_route_missing"
            blockers.append("registered_workspace_route_required")
        elif not isinstance(entry, dict):
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        else:
            current_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            legacy_fallback_path = str(alias.get("legacy_fallback_path") or "")
            future_path = str(alias.get("future_path") or "")
            virtual_uri = str(alias.get("virtual_uri") or "")
            if expected_path and current_path != expected_path:
                status = "blocked_manifest_canonical_path_changed"
                blockers.append("manifest_canonical_path_mismatch")
            if expected_legacy and legacy_fallback_path != expected_legacy:
                status = "blocked_legacy_fallback_path_changed"
                blockers.append("legacy_fallback_path_mismatch")
            if expected_future_path and future_path != expected_future_path:
                status = "blocked_future_path_changed"
                blockers.append("future_path_mismatch")
            if expected_virtual_uri and virtual_uri != expected_virtual_uri:
                status = "blocked_virtual_uri_changed"
                blockers.append("virtual_uri_mismatch")
            if alias.get("foldered_canonical_finalized") is not True:
                status = "blocked_not_foldered_canonical_finalized"
                blockers.append("foldered_canonical_finalized_required")
            if alias.get("resolver_migration_status") != "foldered-canonical-authoritative":
                status = "blocked_resolver_not_authoritative"
                blockers.append("resolver_migration_status_must_be_authoritative")
            if alias.get("migration_status") != "foldered-canonical-finalized-after-reviewed-apply":
                status = "blocked_unexpected_migration_status"
                blockers.append("migration_status_must_be_finalized_after_reviewed_apply")
        candidate_results.append(
            {
                "artifact_key": key,
                "status": status,
                "current_canonical_path": current_path,
                "expected_canonical_path": expected_path,
                "legacy_fallback_path": legacy_fallback_path,
                "expected_legacy_fallback_path": expected_legacy,
                "future_path": future_path,
                "expected_future_path": expected_future_path,
                "virtual_uri": virtual_uri,
                "expected_virtual_uri": expected_virtual_uri,
                "foldered_canonical_finalized": bool(alias.get("foldered_canonical_finalized")) if alias else False,
                "resolver_migration_status": str(alias.get("resolver_migration_status") or "") if alias else "",
                "migration_status": str(alias.get("migration_status") or "") if alias else "",
                "blockers": blockers,
                "mutates_manifest_in_this_tool": False,
            }
        )
    ready_count = len(
        [
            result
            for result in candidate_results
            if result.get("status") == "ready_for_broader_rollout_executor_preflight"
        ]
    )
    return {
        "required_before_manifest_mutation": True,
        "candidate_count": len(candidate_results),
        "ready_candidate_count": ready_count,
        "all_candidates_still_ready": bool(candidate_results and ready_count == len(candidate_results)),
        "candidate_results": candidate_results,
        "mutates_manifest_in_this_tool": False,
    }


def _compact_foldered_canonical_broader_rollout_plan(plan: dict[str, Any]) -> dict[str, Any]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    digest_guard = plan.get("digest_guard") if isinstance(plan.get("digest_guard"), dict) else {}
    executor_gate = plan.get("executor_gate") if isinstance(plan.get("executor_gate"), dict) else {}
    approval = plan.get("approval_requirements") if isinstance(plan.get("approval_requirements"), dict) else {}
    return {
        "schema_version": plan.get("schema_version") or "",
        "status": plan.get("status") or "missing",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "ready_candidate_count": _safe_int(summary.get("ready_candidate_count")),
        "broader_rollout_plan_digest": digest_guard.get("broader_rollout_plan_digest") or "",
        "ready_for_broader_rollout_apply_review": bool(executor_gate.get("ready_for_broader_rollout_apply_review")),
        "preflight_tool_implemented": bool(executor_gate.get("preflight_tool_implemented")),
        "executor_tool_implemented": bool(executor_gate.get("executor_tool_implemented")),
        "approval_subject_id": approval.get("subject_id") or "",
        "approval_action": approval.get("approval_action") or "",
        "blocking_reasons": plan.get("blocking_reasons") if isinstance(plan.get("blocking_reasons"), list) else [],
        "warnings": plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
    }


def _foldered_canonical_broader_rollout_preflight_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "broader_rollout_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_broader_rollout_plan")
    if (
        "broader_rollout_plan_not_ready" in blockers
        or "broader_rollout_plan_apply_gate_not_ready" in blockers
        or "broader_rollout_plan_preflight_gate_not_implemented" in blockers
    ):
        actions.append("regenerate_broader_rollout_plan_from_ready_readiness_and_manifest")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "backend_manifest_broader_rollout_candidates_not_ready" in blockers:
        actions.append("refresh_backend_manifest_and_recheck_broader_rollout_candidates")
    if (
        "review_approval_ledger_unavailable_or_malformed" in blockers
        or "review_approval_ledger_missing_matching_broader_rollout_approval" in blockers
    ):
        actions.append("record_review_approval_for_foldered_canonical_broader_rollout")
    if "review_approval_ledger_does_not_approve_broader_rollout" in blockers:
        actions.append("resolve_review_approval_ledger_decision_or_digest_before_broader_rollout")
    if not blockers:
        actions.append("review_broader_rollout_preflight_before_running_separate_executor")
        actions.append("keep_broader_rollout_apply_explicit_review_only")
    if any("candidate" in warning for warning in warnings):
        actions.append("inspect_blocked_broader_rollout_candidate_revalidation")
    return list(dict.fromkeys(actions))


def execute_workspace_foldered_canonical_broader_rollout_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    mode: str = "dry-run",
    approve_broader_rollout: bool = False,
    broader_rollout_preflight_json: str | None = None,
    broader_rollout_preflight_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_preflight",
    broader_rollout_plan_json: str | None = None,
    broader_rollout_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    expected_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Execute explicit-review-only foldered-canonical broader rollout metadata apply."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    workspace_dir = effective_root / "workspace"
    result_path = workspace_dir / "workspace-foldered-canonical-broader-rollout-result.json"
    journal_path = workspace_dir / "workspace-foldered-canonical-broader-rollout-journal.json"

    preflight, preflight_error, preflight_input = _load_or_read_workspace_foldered_canonical_broader_rollout_preflight(
        default_artifact_root=effective_root,
        broader_rollout_preflight_json=broader_rollout_preflight_json,
        broader_rollout_preflight_artifact_ref=broader_rollout_preflight_artifact_ref,
    )
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_broader_rollout_plan(
        default_artifact_root=effective_root,
        broader_rollout_plan_json=broader_rollout_plan_json,
        broader_rollout_plan_artifact_ref=broader_rollout_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    requested_mode = mode or "dry-run"
    dry_run_mode = requested_mode == "dry-run"
    apply_mode = requested_mode == "apply"
    created_at = datetime.now(timezone.utc).isoformat()
    plan_digest = _foldered_canonical_broader_rollout_plan_digest_from_payload(plan)
    expected_digest = expected_plan_digest or plan_digest
    preflight_digest = _foldered_canonical_broader_rollout_preflight_plan_digest(preflight)
    approval_gate = preflight.get("review_approval_gate") if isinstance(preflight.get("review_approval_gate"), dict) else {}
    preflight_gate = preflight.get("executor_gate") if isinstance(preflight.get("executor_gate"), dict) else {}
    manifest_revalidation = preflight.get("manifest_revalidation") if isinstance(preflight.get("manifest_revalidation"), dict) else {}
    candidate_artifacts = plan.get("candidate_artifacts") if isinstance(plan.get("candidate_artifacts"), list) else []
    valid_candidates = [candidate for candidate in candidate_artifacts if isinstance(candidate, dict)]
    idempotency_key = str(approval_gate.get("idempotency_key") or plan_digest[:16] or "foldered-canonical-broader-rollout")
    transaction_id = f"foldered-canonical-broader-rollout-{plan_digest[:16] or 'missing'}"
    existing_journal = _read_foldered_canonical_broader_rollout_journal(journal_path)
    duplicate_entry = _find_foldered_canonical_broader_rollout_duplicate(existing_journal, idempotency_key=idempotency_key)
    manifest_entry_checks = _foldered_canonical_broader_rollout_apply_manifest_entry_checks(
        candidate_artifacts=valid_candidates,
        backend_manifest=backend_manifest,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if requested_mode not in {"dry-run", "apply"}:
        blockers.append("unsupported_foldered_canonical_broader_rollout_mode")
    if apply_mode and not approve_broader_rollout:
        blockers.append("apply_requires_approve_broader_rollout_true")
    if preflight_error:
        blockers.append("broader_rollout_preflight_unavailable_or_malformed")
    if preflight.get("status") != "ready_for_review":
        blockers.append("broader_rollout_preflight_not_ready")
    if preflight_gate.get("ready_for_broader_rollout_executor_review") is not True:
        blockers.append("broader_rollout_preflight_gate_not_ready")
    if plan_error:
        blockers.append("broader_rollout_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("broader_rollout_plan_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if backend_manifest_json is not None and apply_mode:
        blockers.append("apply_requires_backend_manifest_artifact_ref_not_inline_json")
    if not valid_candidates:
        blockers.append("broader_rollout_has_no_candidates")
    if expected_digest and plan_digest and expected_digest != plan_digest:
        blockers.append("expected_broader_rollout_plan_digest_mismatch")
    if preflight_digest and plan_digest and preflight_digest != plan_digest:
        blockers.append("broader_rollout_preflight_plan_digest_mismatch")
    if not approval_gate.get("approved"):
        blockers.append("broader_rollout_review_approval_not_approved")
    if not approval_gate.get("digest_matches_expected"):
        blockers.append("broader_rollout_review_approval_digest_mismatch")
    if manifest_revalidation.get("all_candidates_still_ready") is not True:
        blockers.append("broader_rollout_preflight_manifest_revalidation_not_ready")
    if duplicate_entry:
        blockers.append("broader_rollout_duplicate_idempotency_key")
    for check in manifest_entry_checks:
        if check.get("status") != "ready":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status')}")
    if not apply_mode:
        warnings.append("broader_rollout_dry_run_does_not_write_journal_result_or_manifest")
    if apply_mode and not blockers:
        warnings.append("broader_rollout_will_only_update_workspace_alias_rollout_metadata")

    status = "blocked" if blockers else "planned" if dry_run_mode else "applied"
    mutated_manifest = _foldered_canonical_broader_rollout_backend_manifest(
        backend_manifest,
        valid_candidates,
        transaction_id=transaction_id,
        applied_at=created_at,
    )
    journal_entry = _foldered_canonical_broader_rollout_journal_entry(
        status=status,
        plan_digest=plan_digest,
        preflight_digest=preflight_digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        candidate_artifacts=valid_candidates,
        approval_gate=approval_gate,
        blockers=blockers,
        created_at=created_at,
    )
    journal_payload = _foldered_canonical_broader_rollout_journal_payload(
        existing_journal=existing_journal,
        entry=journal_entry,
        append_entry=apply_mode and not blockers,
        updated_at=created_at,
    )
    writes = {"backend_manifest": False, "journal": False, "result": False}
    if apply_mode and not blockers:
        _write_json_file(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input), mutated_manifest)
        _write_json_file(journal_path, journal_payload)
        writes.update({"backend_manifest": True, "journal": True})

    payload = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-result.v1",
        "status": status,
        "mode": requested_mode,
        "artifact_root": str(effective_root),
        "summary": {
            "planned_broader_rollout_candidate_count": len(valid_candidates),
            "manifest_entry_check_count": len(manifest_entry_checks),
            "applied_broader_rollout_candidate_count": len(valid_candidates) if status == "applied" else 0,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "transaction_journal_written": writes["journal"],
            "backend_manifest_mutated": writes["backend_manifest"],
            "result_artifact_written": False,
            "broader_rollout_applied": status == "applied",
            "dual_write_enabled": False,
            "canonical_paths_changed": False,
            "files_moved": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "broader_rollout_preflight_input": preflight_input,
        "broader_rollout_plan_input": plan_input,
        "backend_manifest_input": backend_manifest_input,
        "digest_guard": {
            "expected_plan_digest": expected_digest,
            "current_plan_digest": plan_digest,
            "preflight_plan_digest": preflight_digest,
            "expected_digest_match": bool(expected_digest and plan_digest and expected_digest == plan_digest),
            "preflight_digest_match": bool(preflight_digest and plan_digest and preflight_digest == plan_digest),
        },
        "review_approval_gate": approval_gate,
        "idempotency_guard": {
            "idempotency_key": idempotency_key,
            "duplicate_entry_found": duplicate_entry is not None,
            "duplicate_entry": _compact_foldered_canonical_broader_rollout_journal_entry(duplicate_entry),
            "blocks_duplicate_apply": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "transaction_journal": {
            "path": str(journal_path),
            "append_only": True,
            "entry_count": len(journal_payload.get("entries", [])),
            "entry_appended": writes["journal"],
            "writes_journal_in_apply_mode": writes["journal"],
        },
        "backend_manifest_mutation": {
            "path": str(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input)),
            "mutates_backend_manifest_in_apply_mode": writes["backend_manifest"],
            "changes_canonical_paths": False,
            "enables_dual_write": False,
            "applies_broader_rollout_metadata": status == "applied",
            "files_moved": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_execute_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "dry_run_is_read_only": True,
            "artifacts_written": apply_mode and not blockers,
            "writes_transaction_journal": writes["journal"],
            "writes_result_artifact": False,
            "creates_directories": apply_mode and not blockers,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": writes["backend_manifest"],
            "tightens_legacy_fallback": False,
            "authorizes_broader_rollout": False,
            "applies_broader_rollout": status == "applied",
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if apply_mode and not blockers:
        payload["summary"]["result_artifact_written"] = True
        payload["side_effect_policy"]["writes_result_artifact"] = True
        _write_json_file(result_path, payload)
    return payload


def _load_or_read_workspace_foldered_canonical_broader_rollout_preflight(
    *,
    default_artifact_root: Path,
    broader_rollout_preflight_json: str | None,
    broader_rollout_preflight_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_preflight_json, field_name="broader_rollout_preflight_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_preflight_artifact_ref or "workspace_foldered_canonical_broader_rollout_preflight"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "broader_rollout_preflight_not_observed", input_summary


def _foldered_canonical_broader_rollout_preflight_plan_digest(preflight: dict[str, Any]) -> str:
    guard = preflight.get("digest_guard") if isinstance(preflight.get("digest_guard"), dict) else {}
    return str(guard.get("broader_rollout_plan_digest") or "")


def _foldered_canonical_broader_rollout_apply_manifest_entry_checks(
    *,
    candidate_artifacts: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for candidate in candidate_artifacts:
        artifact_key = str(candidate.get("artifact_key") or "")
        expected_path = str(candidate.get("current_canonical_path") or "")
        expected_legacy = str(candidate.get("legacy_fallback_path") or "")
        expected_future_path = str(candidate.get("future_path") or "")
        expected_virtual_uri = str(candidate.get("virtual_uri") or "")
        entry = entries_by_key.get(artifact_key)
        status = "ready"
        observed_path = ""
        observed_legacy = ""
        observed_future_path = ""
        observed_virtual_uri = ""
        finalized = False
        resolver_status = ""
        migration_status = ""
        if not artifact_key:
            status = "missing_artifact_key"
        elif candidate.get("status") != "ready_for_broader_rollout_plan_review":
            status = "plan_candidate_not_ready"
        elif not isinstance(entry, dict):
            status = "manifest_entry_missing"
        else:
            observed_path = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            observed_legacy = str(alias.get("legacy_fallback_path") or "")
            observed_future_path = str(alias.get("future_path") or "")
            observed_virtual_uri = str(alias.get("virtual_uri") or "")
            finalized = alias.get("foldered_canonical_finalized") is True
            resolver_status = str(alias.get("resolver_migration_status") or "")
            migration_status = str(alias.get("migration_status") or "")
            if expected_path and observed_path != expected_path:
                status = "canonical_path_mismatch"
            elif expected_legacy and observed_legacy != expected_legacy:
                status = "legacy_fallback_path_mismatch"
            elif expected_future_path and observed_future_path != expected_future_path:
                status = "future_path_mismatch"
            elif expected_virtual_uri and observed_virtual_uri != expected_virtual_uri:
                status = "virtual_uri_mismatch"
            elif not finalized:
                status = "not_foldered_canonical_finalized"
            elif resolver_status != "foldered-canonical-authoritative":
                status = "resolver_not_authoritative"
            elif migration_status != "foldered-canonical-finalized-after-reviewed-apply":
                status = "unexpected_migration_status"
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "expected_canonical_path": expected_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy,
                "observed_legacy_fallback_path": observed_legacy,
                "expected_future_path": expected_future_path,
                "observed_future_path": observed_future_path,
                "expected_virtual_uri": expected_virtual_uri,
                "observed_virtual_uri": observed_virtual_uri,
                "foldered_canonical_finalized": finalized,
                "resolver_migration_status": resolver_status,
                "migration_status": migration_status,
            }
        )
    return checks


def _foldered_canonical_broader_rollout_backend_manifest(
    backend_manifest: dict[str, Any],
    candidate_artifacts: list[dict[str, Any]],
    *,
    transaction_id: str,
    applied_at: str,
) -> dict[str, Any]:
    manifest = copy.deepcopy(backend_manifest)
    candidates_by_key = {
        str(candidate.get("artifact_key") or ""): candidate
        for candidate in candidate_artifacts
        if isinstance(candidate, dict) and candidate.get("artifact_key")
    }
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        candidate = candidates_by_key.get(str(entry.get("artifact_key") or ""))
        if not candidate:
            continue
        metadata = entry.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
            entry["metadata"] = metadata
        alias = metadata.setdefault("workspace_alias", {})
        if not isinstance(alias, dict):
            alias = {}
            metadata["workspace_alias"] = alias
        alias["broader_rollout_planned"] = True
        alias["broader_rollout_applied"] = True
        alias["broader_rollout_applied_at"] = applied_at
        alias["broader_rollout_transaction_id"] = transaction_id
        alias["broader_rollout_scope"] = "foldered-canonical-finalized-workspace-artifact"
        alias["broader_rollout_candidate_status"] = candidate.get("status") or ""
        alias["broader_rollout_canonical_path_confirmed"] = str(candidate.get("current_canonical_path") or entry.get("path") or "")
    metadata = manifest.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["foldered_canonical_broader_rollout_applied_at"] = applied_at
        metadata["foldered_canonical_broader_rollout_transaction_id"] = transaction_id
        metadata["foldered_canonical_broader_rollout_candidate_count"] = len(candidates_by_key)
    return manifest


def _read_foldered_canonical_broader_rollout_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-journal.v1", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-journal.v1",
            "entries": [],
            "load_error": "malformed_existing_journal",
        }
    if not isinstance(payload, dict):
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-journal.v1", "entries": []}
    if not isinstance(payload.get("entries"), list):
        payload["entries"] = []
    return payload


def _find_foldered_canonical_broader_rollout_duplicate(journal: dict[str, Any], *, idempotency_key: str) -> dict[str, Any] | None:
    for entry in journal.get("entries", []):
        if isinstance(entry, dict) and entry.get("idempotency_key") == idempotency_key and entry.get("status") == "applied":
            return entry
    return None


def _foldered_canonical_broader_rollout_journal_entry(
    *,
    status: str,
    plan_digest: str,
    preflight_digest: str,
    transaction_id: str,
    idempotency_key: str,
    candidate_artifacts: list[dict[str, Any]],
    approval_gate: dict[str, Any],
    blockers: list[str],
    created_at: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "plan_digest": plan_digest,
        "preflight_plan_digest": preflight_digest,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "approval_id": approval_gate.get("approval_id") or "",
        "approval_subject_id": approval_gate.get("expected_subject_id") or "",
        "candidate_count": len(candidate_artifacts),
        "artifact_keys": [str(candidate.get("artifact_key") or "") for candidate in candidate_artifacts],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "created_at": created_at,
    }


def _foldered_canonical_broader_rollout_journal_payload(
    *,
    existing_journal: dict[str, Any],
    entry: dict[str, Any],
    append_entry: bool,
    updated_at: str,
) -> dict[str, Any]:
    entries = [item for item in existing_journal.get("entries", []) if isinstance(item, dict)]
    if append_entry:
        entries.append(entry)
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-journal.v1",
        "updated_at": updated_at,
        "entry_count": len(entries),
        "entries": entries,
    }


def _compact_foldered_canonical_broader_rollout_journal_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {
        "status": entry.get("status") or "",
        "plan_digest": entry.get("plan_digest") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "idempotency_key": entry.get("idempotency_key") or "",
        "artifact_keys": entry.get("artifact_keys") if isinstance(entry.get("artifact_keys"), list) else [],
    }


def _foldered_canonical_broader_rollout_execute_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "broader_rollout_preflight_unavailable_or_malformed" in blockers or "broader_rollout_preflight_not_ready" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_broader_rollout_preflight")
    if "apply_requires_approve_broader_rollout_true" in blockers:
        actions.append("rerun_with_approve_broader_rollout_true_after_review")
    if "broader_rollout_review_approval_not_approved" in blockers or "broader_rollout_review_approval_digest_mismatch" in blockers:
        actions.append("resolve_review_approval_ledger_before_broader_rollout_apply")
    if "broader_rollout_duplicate_idempotency_key" in blockers:
        actions.append("inspect_existing_broader_rollout_journal_before_retry")
    if any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("refresh_backend_manifest_and_recheck_broader_rollout_preflight")
    if status == "planned":
        actions.append("review_dry_run_then_rerun_apply_with_explicit_approval")
    if status == "applied":
        actions.append("review_foldered_canonical_broader_rollout_result")
        actions.append("keep_canonical_paths_stable_after_broader_rollout")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_broader_rollout_post_audit_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    broader_rollout_result_json: str | None = None,
    broader_rollout_result_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_result",
    broader_rollout_journal_json: str | None = None,
    broader_rollout_journal_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_journal",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
) -> dict[str, Any]:
    """Audit broader rollout result, journal, and backend manifest consistency without side effects."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    result, result_error, result_input = _load_or_read_workspace_foldered_canonical_broader_rollout_result(
        default_artifact_root=effective_root,
        broader_rollout_result_json=broader_rollout_result_json,
        broader_rollout_result_artifact_ref=broader_rollout_result_artifact_ref,
    )
    journal, journal_error, journal_input = _load_or_read_workspace_foldered_canonical_broader_rollout_journal(
        default_artifact_root=effective_root,
        broader_rollout_journal_json=broader_rollout_journal_json,
        broader_rollout_journal_artifact_ref=broader_rollout_journal_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    result_summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    result_digest_guard = result.get("digest_guard") if isinstance(result.get("digest_guard"), dict) else {}
    result_checks = result.get("manifest_entry_checks") if isinstance(result.get("manifest_entry_checks"), list) else []
    valid_result_checks = [check for check in result_checks if isinstance(check, dict)]
    transaction_id = str(result_summary.get("transaction_id") or "")
    idempotency_key = str(result_summary.get("idempotency_key") or "")
    plan_digest = str(result_digest_guard.get("current_plan_digest") or result_digest_guard.get("expected_plan_digest") or "")
    journal_entries = journal.get("entries") if isinstance(journal.get("entries"), list) else []
    valid_journal_entries = [entry for entry in journal_entries if isinstance(entry, dict)]
    matching_journal_entry = _find_foldered_canonical_broader_rollout_audit_journal_entry(
        valid_journal_entries,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        plan_digest=plan_digest,
    )
    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    manifest_entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    audit_results = _foldered_canonical_broader_rollout_post_audit_results(
        result_checks=valid_result_checks,
        manifest_entries_by_key=manifest_entries_by_key,
        transaction_id=transaction_id,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if result_error:
        blockers.append("broader_rollout_result_unavailable_or_malformed")
    if result.get("status") != "applied":
        blockers.append("broader_rollout_result_not_applied")
    if result_summary.get("broader_rollout_applied") is not True:
        blockers.append("broader_rollout_result_does_not_mark_applied")
    if result_summary.get("result_artifact_written") is not True:
        blockers.append("broader_rollout_result_artifact_not_written")
    if result_summary.get("backend_manifest_mutated") is not True:
        blockers.append("broader_rollout_result_does_not_mark_backend_manifest_mutated")
    if result_summary.get("canonical_paths_changed") is True:
        blockers.append("broader_rollout_result_reports_canonical_path_change")
    if result_summary.get("dual_write_enabled") is True:
        blockers.append("broader_rollout_result_reports_dual_write_enabled")
    if result_summary.get("files_moved") is True:
        blockers.append("broader_rollout_result_reports_files_moved")
    if journal_error:
        blockers.append("broader_rollout_journal_unavailable_or_malformed")
    if not matching_journal_entry:
        blockers.append("broader_rollout_journal_matching_applied_entry_missing")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not valid_result_checks:
        blockers.append("broader_rollout_result_has_no_manifest_entry_checks")
    manifest_metadata = backend_manifest.get("metadata") if isinstance(backend_manifest.get("metadata"), dict) else {}
    if transaction_id and manifest_metadata.get("foldered_canonical_broader_rollout_transaction_id") != transaction_id:
        blockers.append("backend_manifest_broader_rollout_transaction_id_mismatch")
    if not transaction_id:
        blockers.append("broader_rollout_transaction_id_missing")
    if not idempotency_key:
        blockers.append("broader_rollout_idempotency_key_missing")
    if not plan_digest:
        warnings.append("broader_rollout_plan_digest_missing_from_result")
    for item in audit_results:
        if item.get("status") != "verified":
            blockers.append(f"broader_rollout_post_audit:{item.get('artifact_key') or 'unknown'}:{item.get('status') or 'blocked'}")
        for warning in item.get("warnings") or []:
            warnings.append(f"broader_rollout_post_audit:{item.get('artifact_key') or 'unknown'}:{warning}")
    if not blockers:
        warnings.append("broader_rollout_post_audit_is_read_only_and_does_not_decide_rollback_or_commit")

    verified_count = sum(1 for item in audit_results if item.get("status") == "verified")
    status = "verified" if not blockers else "blocked" if result.get("schema_version") != "missing" else "not_ready"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-post-audit.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "broader_rollout_result_status": result.get("status") or "missing",
            "audit_result_count": len(audit_results),
            "verified_audit_result_count": verified_count,
            "all_broader_rollout_entries_verified": bool(audit_results) and verified_count == len(audit_results),
            "matching_journal_entry_found": matching_journal_entry is not None,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "plan_digest": plan_digest,
            "backend_manifest_transaction_metadata_matches": bool(
                transaction_id and manifest_metadata.get("foldered_canonical_broader_rollout_transaction_id") == transaction_id
            ),
            "canonical_paths_changed_by_broader_rollout": False,
            "dual_write_enabled_by_broader_rollout": False,
            "files_moved_by_broader_rollout": False,
            "artifacts_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "broader_rollout_result_input": result_input,
        "broader_rollout_journal_input": journal_input,
        "backend_manifest_input": backend_manifest_input,
        "broader_rollout_result_summary": _compact_foldered_canonical_broader_rollout_result(result),
        "journal_audit": {
            "entry_count": len(valid_journal_entries),
            "matching_entry_found": matching_journal_entry is not None,
            "matching_entry": _compact_foldered_canonical_broader_rollout_journal_entry(matching_journal_entry),
            "append_only_expected": True,
        },
        "backend_manifest_metadata_audit": {
            "transaction_id": manifest_metadata.get("foldered_canonical_broader_rollout_transaction_id") or "",
            "applied_at": manifest_metadata.get("foldered_canonical_broader_rollout_applied_at") or "",
            "candidate_count": _safe_int(manifest_metadata.get("foldered_canonical_broader_rollout_candidate_count")),
            "transaction_id_matches_result": bool(
                transaction_id and manifest_metadata.get("foldered_canonical_broader_rollout_transaction_id") == transaction_id
            ),
        },
        "audit_results": audit_results,
        "post_rollout_gate": {
            "post_rollout_review_ready": status == "verified",
            "rollback_vs_commit_decision_allowed_by_this_tool": False,
            "automatic_materialization_allowed": False,
            "automatic_rollback_allowed": False,
            "requires_separate_decisioning_after_audit": True,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_post_audit_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "tightens_legacy_fallback": False,
            "authorizes_broader_rollout": False,
            "applies_broader_rollout": False,
            "decides_rollback_vs_commit": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_broader_rollout_result(
    *,
    default_artifact_root: Path,
    broader_rollout_result_json: str | None,
    broader_rollout_result_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_result_json, field_name="broader_rollout_result_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_result_artifact_ref or "workspace_foldered_canonical_broader_rollout_result"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "broader_rollout_result_not_observed", input_summary


def _load_or_read_workspace_foldered_canonical_broader_rollout_journal(
    *,
    default_artifact_root: Path,
    broader_rollout_journal_json: str | None,
    broader_rollout_journal_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_journal_json, field_name="broader_rollout_journal_json")
    if payload is not None or error:
        if payload is not None:
            if not isinstance(payload.get("entries"), list):
                payload["entries"] = []
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "entries": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_journal_artifact_ref or "workspace_foldered_canonical_broader_rollout_journal"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        payload = read_result["json"]
        if not isinstance(payload.get("entries"), list):
            payload["entries"] = []
        return payload, "", input_summary
    return {"schema_version": "missing", "status": "missing", "entries": []}, "broader_rollout_journal_not_observed", input_summary


def _find_foldered_canonical_broader_rollout_audit_journal_entry(
    entries: list[dict[str, Any]],
    *,
    transaction_id: str,
    idempotency_key: str,
    plan_digest: str,
) -> dict[str, Any] | None:
    for entry in entries:
        if entry.get("status") != "applied":
            continue
        if transaction_id and entry.get("transaction_id") != transaction_id:
            continue
        if idempotency_key and entry.get("idempotency_key") != idempotency_key:
            continue
        if plan_digest and entry.get("plan_digest") != plan_digest:
            continue
        return entry
    return None


def _foldered_canonical_broader_rollout_post_audit_results(
    *,
    result_checks: list[dict[str, Any]],
    manifest_entries_by_key: dict[str, dict[str, Any]],
    transaction_id: str,
) -> list[dict[str, Any]]:
    audit_results: list[dict[str, Any]] = []
    for check in result_checks:
        artifact_key = str(check.get("artifact_key") or "")
        expected_canonical_path = str(check.get("expected_canonical_path") or check.get("observed_canonical_path") or "")
        expected_legacy_path = str(check.get("expected_legacy_fallback_path") or check.get("observed_legacy_fallback_path") or "")
        expected_future_path = str(check.get("expected_future_path") or check.get("observed_future_path") or "")
        expected_virtual_uri = str(check.get("expected_virtual_uri") or check.get("observed_virtual_uri") or "")
        entry = manifest_entries_by_key.get(artifact_key) or {}
        observed_path = str(entry.get("path") or "")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        status = "verified"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif not entry:
            status = "blocked_manifest_entry_missing"
            blockers.append("manifest_entry_required")
        if expected_canonical_path and observed_path and observed_path != expected_canonical_path:
            status = "blocked_canonical_path_changed_after_broader_rollout"
            blockers.append("canonical_path_changed_after_broader_rollout")
        if expected_legacy_path and observed_path and observed_path == expected_legacy_path:
            status = "blocked_canonical_path_regressed_to_legacy"
            blockers.append("canonical_path_regressed_to_legacy")
        if not alias:
            status = "blocked_workspace_alias_missing"
            blockers.append("workspace_alias_metadata_required")
        elif alias.get("broader_rollout_applied") is not True:
            status = "blocked_broader_rollout_not_applied"
            blockers.append("broader_rollout_applied_required")
        elif transaction_id and alias.get("broader_rollout_transaction_id") != transaction_id:
            status = "blocked_transaction_id_mismatch"
            blockers.append("broader_rollout_transaction_id_mismatch")
        elif alias.get("broader_rollout_planned") is not True:
            status = "blocked_broader_rollout_not_planned"
            blockers.append("broader_rollout_planned_required")
        elif alias.get("foldered_canonical_finalized") is not True:
            status = "blocked_not_foldered_canonical_finalized"
            blockers.append("foldered_canonical_finalized_required")
        elif alias.get("resolver_migration_status") != "foldered-canonical-authoritative":
            status = "blocked_resolver_not_authoritative"
            blockers.append("resolver_migration_status_must_remain_authoritative")
        elif alias.get("migration_status") != "foldered-canonical-finalized-after-reviewed-apply":
            status = "blocked_migration_status_unexpected"
            blockers.append("migration_status_must_remain_finalized_after_reviewed_apply")
        if alias:
            if expected_future_path and str(alias.get("future_path") or "") != expected_future_path:
                status = "blocked_future_path_mismatch"
                blockers.append("future_path_mismatch")
            if expected_virtual_uri and str(alias.get("virtual_uri") or "") != expected_virtual_uri:
                status = "blocked_virtual_uri_mismatch"
                blockers.append("virtual_uri_mismatch")
            if expected_canonical_path and str(alias.get("broader_rollout_canonical_path_confirmed") or "") != expected_canonical_path:
                status = "blocked_broader_rollout_canonical_path_confirmation_mismatch"
                blockers.append("broader_rollout_canonical_path_confirmation_mismatch")
            if alias.get("legacy_fallback_tightened") is not True:
                warnings.append("legacy_fallback_not_marked_tightened_before_broader_rollout")
            if alias.get("foldered_canonical_finalized") is not True:
                warnings.append("foldered_canonical_not_marked_finalized_before_broader_rollout")
        audit_results.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "review_required": True,
                "expected_canonical_path": expected_canonical_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy_path,
                "expected_future_path": expected_future_path,
                "observed_future_path": str(alias.get("future_path") or "") if alias else "",
                "expected_virtual_uri": expected_virtual_uri,
                "observed_virtual_uri": str(alias.get("virtual_uri") or "") if alias else "",
                "broader_rollout_planned": alias.get("broader_rollout_planned") is True if alias else False,
                "broader_rollout_applied": alias.get("broader_rollout_applied") is True if alias else False,
                "foldered_canonical_finalized": alias.get("foldered_canonical_finalized") is True if alias else False,
                "resolver_migration_status": str(alias.get("resolver_migration_status") or "") if alias else "",
                "migration_status": str(alias.get("migration_status") or "") if alias else "",
                "transaction_id_matches": bool(alias and transaction_id and alias.get("broader_rollout_transaction_id") == transaction_id),
                "canonical_path_stable_after_broader_rollout": bool(
                    observed_path and expected_canonical_path and observed_path == expected_canonical_path
                ),
                "canonical_path_regressed_to_legacy": bool(observed_path and expected_legacy_path and observed_path == expected_legacy_path),
                "dual_write_enabled_by_broader_rollout": False,
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return audit_results


def _compact_foldered_canonical_broader_rollout_result(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    digest_guard = result.get("digest_guard") if isinstance(result.get("digest_guard"), dict) else {}
    return {
        "schema_version": result.get("schema_version") or "",
        "status": result.get("status") or "missing",
        "mode": result.get("mode") or "",
        "transaction_id": summary.get("transaction_id") or "",
        "idempotency_key": summary.get("idempotency_key") or "",
        "planned_broader_rollout_candidate_count": _safe_int(summary.get("planned_broader_rollout_candidate_count")),
        "applied_broader_rollout_candidate_count": _safe_int(summary.get("applied_broader_rollout_candidate_count")),
        "broader_rollout_applied": bool(summary.get("broader_rollout_applied")),
        "canonical_paths_changed": bool(summary.get("canonical_paths_changed")),
        "dual_write_enabled": bool(summary.get("dual_write_enabled")),
        "files_moved": bool(summary.get("files_moved")),
        "current_plan_digest": digest_guard.get("current_plan_digest") or "",
        "preflight_plan_digest": digest_guard.get("preflight_plan_digest") or "",
    }


def _foldered_canonical_broader_rollout_post_audit_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "broader_rollout_result_unavailable_or_malformed" in blockers or "broader_rollout_result_not_applied" in blockers:
        actions.append("run_or_pass_applied_foldered_canonical_broader_rollout_result")
    if "broader_rollout_journal_unavailable_or_malformed" in blockers or "broader_rollout_journal_matching_applied_entry_missing" in blockers:
        actions.append("inspect_broader_rollout_journal_before_post_rollout_decision")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_for_broader_rollout_post_audit")
    if any(reason.startswith("broader_rollout_post_audit:") for reason in blockers):
        actions.append("repair_or_reapply_broader_rollout_metadata_before_decisioning")
    if status == "verified":
        actions.append("review_broader_rollout_post_audit_before_rollback_vs_commit_decision")
        actions.append("keep_rollback_vs_commit_decisioning_separate")
    if any("legacy_fallback" in warning for warning in warnings):
        actions.append("review_legacy_fallback_metadata_before_removing_compatibility_paths")
    return list(dict.fromkeys(actions))


def plan_workspace_foldered_canonical_broader_rollout_rollback_decision_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    broader_rollout_post_audit_json: str | None = None,
    broader_rollout_post_audit_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_post_audit",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    requested_decision: str | None = None,
) -> dict[str, Any]:
    """Plan a reviewed rollback-vs-commit decision without side effects."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    post_audit, post_audit_error, post_audit_input = _load_or_read_workspace_foldered_canonical_broader_rollout_post_audit(
        default_artifact_root=effective_root,
        broader_rollout_post_audit_json=broader_rollout_post_audit_json,
        broader_rollout_post_audit_artifact_ref=broader_rollout_post_audit_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    post_summary = post_audit.get("summary") if isinstance(post_audit.get("summary"), dict) else {}
    audit_results = post_audit.get("audit_results") if isinstance(post_audit.get("audit_results"), list) else []
    valid_audit_results = [item for item in audit_results if isinstance(item, dict)]
    current_manifest_checks = _foldered_canonical_broader_rollout_rollback_decision_current_manifest_checks(
        audit_results=valid_audit_results,
        backend_manifest=backend_manifest,
        transaction_id=str(post_summary.get("transaction_id") or ""),
    )
    requested = str(requested_decision or "").strip().lower()
    valid_requested_decisions = {"", "commit", "rollback", "defer"}
    blockers: list[str] = []
    warnings: list[str] = []
    if post_audit_error:
        blockers.append("broader_rollout_post_audit_unavailable_or_malformed")
    if post_audit.get("status") != "verified":
        blockers.append("broader_rollout_post_audit_not_verified")
    if post_summary.get("all_broader_rollout_entries_verified") is not True:
        blockers.append("broader_rollout_post_audit_entries_not_all_verified")
    if post_summary.get("canonical_paths_changed_by_broader_rollout") is True:
        blockers.append("broader_rollout_post_audit_reports_canonical_path_change")
    if post_summary.get("dual_write_enabled_by_broader_rollout") is True:
        blockers.append("broader_rollout_post_audit_reports_dual_write_enabled")
    if post_summary.get("files_moved_by_broader_rollout") is True:
        blockers.append("broader_rollout_post_audit_reports_files_moved")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if not valid_audit_results:
        blockers.append("broader_rollout_post_audit_has_no_audit_results")
    if requested not in valid_requested_decisions:
        blockers.append("requested_decision_not_supported")
    for item in current_manifest_checks:
        if item.get("status") != "verified":
            blockers.append(f"broader_rollout_rollback_decision:{item.get('artifact_key') or 'unknown'}:{item.get('status') or 'blocked'}")
        for warning in item.get("warnings") or []:
            warnings.append(f"broader_rollout_rollback_decision:{item.get('artifact_key') or 'unknown'}:{warning}")
    if not blockers:
        warnings.append("rollback_vs_commit_decision_plan_is_review_only_and_does_not_record_decision")

    verified_check_count = sum(1 for item in current_manifest_checks if item.get("status") == "verified")
    status = "ready_for_review" if not blockers else "blocked" if post_audit.get("schema_version") != "missing" else "not_ready"
    decision_review_ready = status == "ready_for_review"
    selected_decision = requested if requested in {"commit", "rollback", "defer"} else ""
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-decision-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "planned_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "post_audit_status": post_audit.get("status") or "missing",
            "audit_result_count": len(valid_audit_results),
            "current_manifest_check_count": len(current_manifest_checks),
            "verified_current_manifest_check_count": verified_check_count,
            "all_current_manifest_checks_verified": bool(current_manifest_checks)
            and verified_check_count == len(current_manifest_checks),
            "transaction_id": post_summary.get("transaction_id") or "",
            "idempotency_key": post_summary.get("idempotency_key") or "",
            "requested_decision": requested,
            "selected_decision": selected_decision,
            "decision_review_ready": decision_review_ready,
            "rollback_vs_commit_decision_recorded_by_this_tool": False,
            "rollback_executed_by_this_tool": False,
            "commit_executed_by_this_tool": False,
            "artifacts_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "broader_rollout_post_audit_input": post_audit_input,
        "backend_manifest_input": backend_manifest_input,
        "post_audit_summary": {
            "schema_version": post_audit.get("schema_version") or "",
            "status": post_audit.get("status") or "missing",
            "transaction_id": post_summary.get("transaction_id") or "",
            "idempotency_key": post_summary.get("idempotency_key") or "",
            "all_broader_rollout_entries_verified": post_summary.get("all_broader_rollout_entries_verified") is True,
            "matching_journal_entry_found": post_summary.get("matching_journal_entry_found") is True,
            "backend_manifest_transaction_metadata_matches": post_summary.get("backend_manifest_transaction_metadata_matches") is True,
        },
        "current_manifest_checks": current_manifest_checks,
        "decision_options": [
            {
                "decision": "commit",
                "label": "commit_broader_rollout_metadata",
                "review_ready": decision_review_ready,
                "requires_separate_review_approval": True,
                "requires_separate_executor": True,
                "writes_by_this_tool": False,
                "description": "Keep the broader rollout metadata as accepted after human review.",
            },
            {
                "decision": "rollback",
                "label": "plan_broader_rollout_metadata_rollback",
                "review_ready": decision_review_ready,
                "requires_separate_review_approval": True,
                "requires_separate_executor": True,
                "writes_by_this_tool": False,
                "description": "Prepare a separate reviewed rollback plan before reverting broader rollout metadata.",
            },
            {
                "decision": "defer",
                "label": "defer_decision_and_collect_more_evidence",
                "review_ready": True,
                "requires_separate_review_approval": False,
                "requires_separate_executor": False,
                "writes_by_this_tool": False,
                "description": "Leave the broader rollout state unchanged while collecting more evidence.",
            },
        ],
        "decision_gate": {
            "decision_review_ready": decision_review_ready,
            "requested_decision_supported": requested in valid_requested_decisions,
            "selected_decision": selected_decision,
            "commit_review_allowed": decision_review_ready,
            "rollback_review_allowed": decision_review_ready,
            "defer_review_allowed": True,
            "decision_record_allowed_by_this_tool": False,
            "automatic_commit_allowed": False,
            "automatic_rollback_allowed": False,
            "requires_separate_decision_record": decision_review_ready,
            "requires_separate_commit_or_rollback_executor": selected_decision in {"commit", "rollback"},
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_rollback_decision_next_actions(
            status,
            blockers,
            warnings,
            selected_decision=selected_decision,
        ),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "records_decision": False,
            "commits_broader_rollout": False,
            "rolls_back_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_workspace_foldered_canonical_broader_rollout_post_audit(
    *,
    default_artifact_root: Path,
    broader_rollout_post_audit_json: str | None,
    broader_rollout_post_audit_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(broader_rollout_post_audit_json, field_name="broader_rollout_post_audit_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = broader_rollout_post_audit_artifact_ref or "workspace_foldered_canonical_broader_rollout_post_audit"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "broader_rollout_post_audit_not_observed", input_summary


def _foldered_canonical_broader_rollout_rollback_decision_current_manifest_checks(
    *,
    audit_results: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
    transaction_id: str,
) -> list[dict[str, Any]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for audit in audit_results:
        artifact_key = str(audit.get("artifact_key") or "")
        expected_canonical_path = str(audit.get("observed_canonical_path") or audit.get("expected_canonical_path") or "")
        expected_legacy_path = str(audit.get("expected_legacy_fallback_path") or "")
        entry = entries_by_key.get(artifact_key) or {}
        observed_path = str(entry.get("path") or "")
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        status = "verified"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "blocked_missing_artifact_key"
            blockers.append("artifact_key_required")
        elif not entry:
            status = "blocked_current_manifest_entry_missing"
            blockers.append("current_manifest_entry_required")
        if expected_canonical_path and observed_path and observed_path != expected_canonical_path:
            status = "blocked_current_manifest_canonical_path_changed"
            blockers.append("current_manifest_canonical_path_changed")
        if expected_legacy_path and observed_path and observed_path == expected_legacy_path:
            status = "blocked_current_manifest_canonical_path_regressed_to_legacy"
            blockers.append("current_manifest_canonical_path_regressed_to_legacy")
        if not alias:
            status = "blocked_current_manifest_workspace_alias_missing"
            blockers.append("current_manifest_workspace_alias_required")
        elif alias.get("broader_rollout_applied") is not True:
            status = "blocked_current_manifest_broader_rollout_not_applied"
            blockers.append("current_manifest_broader_rollout_applied_required")
        elif transaction_id and alias.get("broader_rollout_transaction_id") != transaction_id:
            status = "blocked_current_manifest_transaction_id_mismatch"
            blockers.append("current_manifest_transaction_id_mismatch")
        if alias and alias.get("foldered_canonical_finalized") is not True:
            warnings.append("current_manifest_not_marked_foldered_canonical_finalized")
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "expected_canonical_path": expected_canonical_path,
                "observed_canonical_path": observed_path,
                "expected_legacy_fallback_path": expected_legacy_path,
                "canonical_path_stable": bool(expected_canonical_path and observed_path == expected_canonical_path),
                "canonical_path_regressed_to_legacy": bool(expected_legacy_path and observed_path == expected_legacy_path),
                "broader_rollout_applied": alias.get("broader_rollout_applied") is True if alias else False,
                "transaction_id_matches": bool(alias and transaction_id and alias.get("broader_rollout_transaction_id") == transaction_id),
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return checks


def _foldered_canonical_broader_rollout_rollback_decision_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
    *,
    selected_decision: str,
) -> list[str]:
    actions: list[str] = []
    if "broader_rollout_post_audit_unavailable_or_malformed" in blockers or "broader_rollout_post_audit_not_verified" in blockers:
        actions.append("produce_verified_broader_rollout_post_audit_before_decisioning")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_before_rollback_vs_commit_review")
    if "requested_decision_not_supported" in blockers:
        actions.append("choose_supported_requested_decision_commit_rollback_or_defer")
    if any(reason.startswith("broader_rollout_rollback_decision:") for reason in blockers):
        actions.append("repair_or_reaudit_broader_rollout_manifest_state_before_decisioning")
    if status == "ready_for_review":
        actions.append("record_separate_review_decision_before_any_commit_or_rollback_executor")
        if selected_decision == "commit":
            actions.append("prepare_separate_broader_rollout_commit_record_after_review")
        elif selected_decision == "rollback":
            actions.append("prepare_separate_broader_rollout_rollback_plan_after_review")
        else:
            actions.append("review_commit_rollback_or_defer_options")
    if any("foldered_canonical" in warning for warning in warnings):
            actions.append("review_foldered_canonical_metadata_before_decision_record")
    return list(dict.fromkeys(actions))


def record_workspace_foldered_canonical_broader_rollout_decision_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    rollback_decision_plan_json: str | None = None,
    rollback_decision_plan_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_rollback_decision_plan",
    decision: str | None = None,
    reviewer: str | None = None,
    reason: str | None = None,
    write_result: bool = False,
    approve_decision_record: bool = False,
) -> dict[str, Any]:
    """Record a reviewed broader rollout rollback-vs-commit decision without execution."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    plan, plan_error, plan_input = _load_or_read_workspace_foldered_canonical_broader_rollout_rollback_decision_plan(
        default_artifact_root=effective_root,
        rollback_decision_plan_json=rollback_decision_plan_json,
        rollback_decision_plan_artifact_ref=rollback_decision_plan_artifact_ref,
    )
    plan_summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    decision_gate = plan.get("decision_gate") if isinstance(plan.get("decision_gate"), dict) else {}
    selected_from_plan = str(plan_summary.get("selected_decision") or decision_gate.get("selected_decision") or "").strip().lower()
    selected_decision = str(decision or selected_from_plan or "").strip().lower()
    reviewer_value = str(reviewer or "").strip()
    valid_decisions = {"commit", "rollback", "defer"}
    blockers: list[str] = []
    warnings: list[str] = []
    if plan_error:
        blockers.append("rollback_decision_plan_unavailable_or_malformed")
    if plan.get("status") != "ready_for_review":
        blockers.append("rollback_decision_plan_not_ready_for_review")
    if decision_gate.get("decision_review_ready") is not True:
        blockers.append("rollback_decision_plan_gate_not_ready")
    if not selected_decision:
        blockers.append("decision_required")
    elif selected_decision not in valid_decisions:
        blockers.append("decision_not_supported")
    if selected_decision == "commit" and decision_gate.get("commit_review_allowed") is not True:
        blockers.append("commit_decision_not_allowed_by_plan")
    if selected_decision == "rollback" and decision_gate.get("rollback_review_allowed") is not True:
        blockers.append("rollback_decision_not_allowed_by_plan")
    if selected_from_plan and selected_decision and selected_decision != selected_from_plan:
        warnings.append("decision_differs_from_requested_plan_selection")
    if write_result and not reviewer_value:
        blockers.append("reviewer_required_to_write_decision_record")
    if write_result and approve_decision_record is not True:
        blockers.append("approve_decision_record_required_to_write")
    for reason_item in plan.get("blocking_reasons") or []:
        blockers.append(f"rollback_decision_plan:{reason_item}")
    for warning_item in plan.get("warnings") or []:
        warnings.append(f"rollback_decision_plan:{warning_item}")
    if not blockers:
        warnings.append("decision_record_does_not_execute_commit_or_rollback")

    will_write = bool(write_result and not blockers)
    status = "recorded" if will_write else "ready_for_record" if not blockers else "blocked" if plan.get("schema_version") != "missing" else "not_ready"
    result_artifact = _workspace_foldered_canonical_broader_rollout_decision_record_artifact_metadata(
        effective_root,
        written=False,
    )
    recorded_at = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-decision-record.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "result_artifact": result_artifact,
        "recorded_at": recorded_at,
        "summary": {
            "rollback_decision_plan_status": plan.get("status") or "missing",
            "decision": selected_decision,
            "reviewer": reviewer_value,
            "write_result_requested": bool(write_result),
            "approve_decision_record": bool(approve_decision_record),
            "decision_record_written": False,
            "commit_executed_by_this_tool": False,
            "rollback_executed_by_this_tool": False,
            "backend_manifest_mutated_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "rollback_decision_plan_input": plan_input,
        "rollback_decision_plan_summary": {
            "schema_version": plan.get("schema_version") or "",
            "status": plan.get("status") or "missing",
            "transaction_id": plan_summary.get("transaction_id") or "",
            "idempotency_key": plan_summary.get("idempotency_key") or "",
            "requested_decision": plan_summary.get("requested_decision") or "",
            "selected_decision": selected_from_plan,
            "decision_review_ready": decision_gate.get("decision_review_ready") is True,
            "commit_review_allowed": decision_gate.get("commit_review_allowed") is True,
            "rollback_review_allowed": decision_gate.get("rollback_review_allowed") is True,
            "defer_review_allowed": decision_gate.get("defer_review_allowed") is True,
            "blocking_reasons": plan.get("blocking_reasons") if isinstance(plan.get("blocking_reasons"), list) else [],
            "warnings": plan.get("warnings") if isinstance(plan.get("warnings"), list) else [],
        },
        "decision_record": {
            "decision": selected_decision,
            "reviewer": reviewer_value,
            "reason": str(reason or ""),
            "recorded_at": recorded_at,
            "source_plan_artifact_ref": rollback_decision_plan_artifact_ref or "",
            "source_plan_transaction_id": plan_summary.get("transaction_id") or "",
            "source_plan_idempotency_key": plan_summary.get("idempotency_key") or "",
            "recorded": will_write,
        },
        "downstream_gates": {
            "commit_executor_allowed_by_this_tool": False,
            "rollback_executor_allowed_by_this_tool": False,
            "requires_separate_commit_or_rollback_executor": selected_decision in {"commit", "rollback"},
            "requires_separate_review_approval_for_executor": selected_decision in {"commit", "rollback"},
            "defer_requires_no_executor": selected_decision == "defer",
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_decision_record_next_actions(
            status,
            blockers,
            selected_decision=selected_decision,
            write_result=write_result,
        ),
        "side_effect_policy": {
            "read_only": not will_write,
            "files_inspected": False,
            "artifacts_written": will_write,
            "creates_directories": will_write,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "records_decision": will_write,
            "commits_broader_rollout": False,
            "rolls_back_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if will_write:
        result_path = effective_root / "workspace" / "workspace-foldered-canonical-broader-rollout-decision-record.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_foldered_canonical_broader_rollout_decision_record_artifact_metadata(
            effective_root,
            written=True,
        )
        payload["summary"]["decision_record_written"] = True
        payload["decision_record"]["recorded"] = True
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_or_read_workspace_foldered_canonical_broader_rollout_rollback_decision_plan(
    *,
    default_artifact_root: Path,
    rollback_decision_plan_json: str | None,
    rollback_decision_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(rollback_decision_plan_json, field_name="rollback_decision_plan_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = rollback_decision_plan_artifact_ref or "workspace_foldered_canonical_broader_rollout_rollback_decision_plan"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "rollback_decision_plan_not_observed", input_summary


def _workspace_foldered_canonical_broader_rollout_decision_record_artifact_metadata(
    artifact_root: Path,
    *,
    written: bool,
) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_foldered_canonical_broader_rollout_decision_record",
        "legacy_path": "workspace/workspace-foldered-canonical-broader-rollout-decision-record.json",
        "future_path": "/workspace/review/workspace-foldered-canonical-broader-rollout-decision-record.json",
        "path": str(artifact_root / "workspace" / "workspace-foldered-canonical-broader-rollout-decision-record.json"),
        "written": written,
        "category": "audit",
    }


def _foldered_canonical_broader_rollout_decision_record_next_actions(
    status: str,
    blockers: list[str],
    *,
    selected_decision: str,
    write_result: bool,
) -> list[str]:
    actions: list[str] = []
    if "rollback_decision_plan_unavailable_or_malformed" in blockers or "rollback_decision_plan_not_ready_for_review" in blockers:
        actions.append("produce_ready_rollback_vs_commit_decision_plan_before_recording")
    if "decision_required" in blockers or "decision_not_supported" in blockers:
        actions.append("choose_supported_decision_commit_rollback_or_defer")
    if "reviewer_required_to_write_decision_record" in blockers:
        actions.append("provide_reviewer_before_writing_decision_record")
    if "approve_decision_record_required_to_write" in blockers:
        actions.append("set_approve_decision_record_true_before_writing")
    if status == "ready_for_record" and not write_result:
        actions.append("call_with_write_result_true_after_human_review_to_record_decision")
    if status == "recorded" and selected_decision == "commit":
        actions.append("prepare_separate_reviewed_broader_rollout_commit_executor")
    elif status == "recorded" and selected_decision == "rollback":
        actions.append("prepare_separate_reviewed_broader_rollout_rollback_executor")
    elif status == "recorded" and selected_decision == "defer":
        actions.append("collect_additional_evidence_before_commit_or_rollback")
    return list(dict.fromkeys(actions))


def execute_workspace_foldered_canonical_broader_rollout_commit_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    mode: str = "dry-run",
    approve_commit: bool = False,
    decision_record_json: str | None = None,
    decision_record_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_decision_record",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    expected_transaction_id: str | None = None,
) -> dict[str, Any]:
    """Execute explicit-review-only broader rollout commit terminalization."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    workspace_dir = effective_root / "workspace"
    result_path = workspace_dir / "workspace-foldered-canonical-broader-rollout-commit-result.json"
    journal_path = workspace_dir / "workspace-foldered-canonical-broader-rollout-commit-journal.json"
    decision_record, decision_record_error, decision_record_input = (
        _load_or_read_workspace_foldered_canonical_broader_rollout_decision_record(
            default_artifact_root=effective_root,
            decision_record_json=decision_record_json,
            decision_record_artifact_ref=decision_record_artifact_ref,
        )
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    requested_mode = mode or "dry-run"
    dry_run_mode = requested_mode == "dry-run"
    apply_mode = requested_mode == "apply"
    committed_at = datetime.now(timezone.utc).isoformat()
    record_summary = decision_record.get("summary") if isinstance(decision_record.get("summary"), dict) else {}
    record_body = decision_record.get("decision_record") if isinstance(decision_record.get("decision_record"), dict) else {}
    decision = str(record_body.get("decision") or record_summary.get("decision") or "").strip().lower()
    transaction_id = str(record_body.get("source_plan_transaction_id") or "").strip()
    idempotency_key = str(record_body.get("source_plan_idempotency_key") or transaction_id or "").strip()
    expected_transaction = str(expected_transaction_id or transaction_id or "").strip()
    commit_idempotency_key = f"{idempotency_key}:commit" if idempotency_key else "foldered-canonical-broader-rollout-commit"
    commit_transaction_id = f"foldered-canonical-broader-rollout-commit-{transaction_id or 'missing'}"
    manifest_entry_checks = _foldered_canonical_broader_rollout_commit_manifest_entry_checks(
        backend_manifest=backend_manifest,
        transaction_id=transaction_id,
    )
    existing_journal = _read_foldered_canonical_broader_rollout_commit_journal(journal_path)
    duplicate_entry = _find_foldered_canonical_broader_rollout_commit_duplicate(
        existing_journal,
        commit_idempotency_key=commit_idempotency_key,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if requested_mode not in {"dry-run", "apply"}:
        blockers.append("unsupported_foldered_canonical_broader_rollout_commit_mode")
    if apply_mode and not approve_commit:
        blockers.append("apply_requires_approve_commit_true")
    if decision_record_error:
        blockers.append("decision_record_unavailable_or_malformed")
    if decision_record.get("status") != "recorded":
        blockers.append("decision_record_not_recorded")
    if record_summary.get("decision_record_written") is not True:
        blockers.append("decision_record_artifact_not_written")
    if record_body.get("recorded") is not True:
        blockers.append("decision_record_body_not_marked_recorded")
    if decision != "commit":
        blockers.append("decision_record_does_not_select_commit")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if backend_manifest_json is not None and apply_mode:
        blockers.append("apply_requires_backend_manifest_artifact_ref_not_inline_json")
    if not transaction_id:
        blockers.append("source_plan_transaction_id_missing")
    if expected_transaction and transaction_id and expected_transaction != transaction_id:
        blockers.append("expected_transaction_id_mismatch")
    if not manifest_entry_checks:
        blockers.append("no_current_manifest_entries_for_broader_rollout_transaction")
    for check in manifest_entry_checks:
        if check.get("status") != "ready_for_commit":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status') or 'blocked'}")
    if duplicate_entry:
        blockers.append("broader_rollout_commit_duplicate_idempotency_key")
    for reason_item in decision_record.get("blocking_reasons") or []:
        blockers.append(f"decision_record:{reason_item}")
    if not apply_mode:
        warnings.append("broader_rollout_commit_dry_run_does_not_write_journal_result_or_manifest")
    if apply_mode and not blockers:
        warnings.append("broader_rollout_commit_will_only_mark_existing_rollout_metadata_accepted")

    status = "blocked" if blockers else "planned" if dry_run_mode else "committed"
    mutated_manifest = _foldered_canonical_broader_rollout_commit_backend_manifest(
        backend_manifest,
        transaction_id=transaction_id,
        commit_transaction_id=commit_transaction_id,
        committed_at=committed_at,
    )
    journal_entry = _foldered_canonical_broader_rollout_commit_journal_entry(
        status=status,
        transaction_id=transaction_id,
        commit_transaction_id=commit_transaction_id,
        commit_idempotency_key=commit_idempotency_key,
        decision=decision,
        manifest_entry_checks=manifest_entry_checks,
        blockers=blockers,
        committed_at=committed_at,
    )
    journal_payload = _foldered_canonical_broader_rollout_commit_journal_payload(
        existing_journal=existing_journal,
        entry=journal_entry,
        append_entry=apply_mode and not blockers,
        updated_at=committed_at,
    )
    writes = {"backend_manifest": False, "journal": False, "result": False}
    if apply_mode and not blockers:
        _write_json_file(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input), mutated_manifest)
        _write_json_file(journal_path, journal_payload)
        writes.update({"backend_manifest": True, "journal": True})

    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-result.v1",
        "status": status,
        "mode": requested_mode,
        "artifact_root": str(effective_root),
        "committed_at": committed_at,
        "result_artifact": _workspace_foldered_canonical_broader_rollout_commit_result_artifact_metadata(
            effective_root,
            written=False,
        ),
        "summary": {
            "decision_record_status": decision_record.get("status") or "missing",
            "decision": decision,
            "transaction_id": transaction_id,
            "commit_transaction_id": commit_transaction_id,
            "commit_idempotency_key": commit_idempotency_key,
            "manifest_entry_check_count": len(manifest_entry_checks),
            "committed_manifest_entry_count": len(manifest_entry_checks) if status == "committed" else 0,
            "transaction_journal_written": writes["journal"],
            "backend_manifest_mutated": writes["backend_manifest"],
            "result_artifact_written": False,
            "broader_rollout_committed": status == "committed",
            "broader_rollout_rolled_back": False,
            "dual_write_enabled": False,
            "canonical_paths_changed": False,
            "files_moved": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "decision_record_input": decision_record_input,
        "backend_manifest_input": backend_manifest_input,
        "decision_record_summary": {
            "schema_version": decision_record.get("schema_version") or "",
            "status": decision_record.get("status") or "missing",
            "decision": decision,
            "decision_record_written": record_summary.get("decision_record_written") is True,
            "reviewer": record_summary.get("reviewer") or record_body.get("reviewer") or "",
            "source_plan_transaction_id": transaction_id,
            "source_plan_idempotency_key": idempotency_key,
        },
        "digest_guard": {
            "expected_transaction_id": expected_transaction,
            "current_transaction_id": transaction_id,
            "expected_transaction_match": bool(expected_transaction and transaction_id and expected_transaction == transaction_id),
        },
        "idempotency_guard": {
            "commit_idempotency_key": commit_idempotency_key,
            "duplicate_entry_found": duplicate_entry is not None,
            "duplicate_entry": _compact_foldered_canonical_broader_rollout_commit_journal_entry(duplicate_entry),
            "blocks_duplicate_apply": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "transaction_journal": {
            "path": str(journal_path),
            "append_only": True,
            "entry_count": len(journal_payload.get("entries", [])),
            "entry_appended": writes["journal"],
            "writes_journal_in_apply_mode": writes["journal"],
        },
        "backend_manifest_mutation": {
            "path": str(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input)),
            "mutates_backend_manifest_in_apply_mode": writes["backend_manifest"],
            "changes_canonical_paths": False,
            "enables_dual_write": False,
            "marks_broader_rollout_committed": status == "committed",
            "rolls_back_broader_rollout": False,
            "files_moved": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_commit_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "dry_run_is_read_only": True,
            "artifacts_written": apply_mode and not blockers,
            "writes_transaction_journal": writes["journal"],
            "writes_result_artifact": False,
            "creates_directories": apply_mode and not blockers,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": writes["backend_manifest"],
            "records_decision": False,
            "commits_broader_rollout": status == "committed",
            "rolls_back_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if apply_mode and not blockers:
        payload["result_artifact"] = _workspace_foldered_canonical_broader_rollout_commit_result_artifact_metadata(
            effective_root,
            written=True,
        )
        payload["summary"]["result_artifact_written"] = True
        payload["side_effect_policy"]["writes_result_artifact"] = True
        _write_json_file(result_path, payload)
    return payload


def _load_or_read_workspace_foldered_canonical_broader_rollout_decision_record(
    *,
    default_artifact_root: Path,
    decision_record_json: str | None,
    decision_record_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(decision_record_json, field_name="decision_record_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = decision_record_artifact_ref or "workspace_foldered_canonical_broader_rollout_decision_record"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "decision_record_not_observed", input_summary


def _foldered_canonical_broader_rollout_commit_manifest_entry_checks(
    *,
    backend_manifest: dict[str, Any],
    transaction_id: str,
) -> list[dict[str, Any]]:
    if not transaction_id:
        return []
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    checks: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        if alias.get("broader_rollout_transaction_id") != transaction_id:
            continue
        artifact_key = str(entry.get("artifact_key") or "")
        observed_path = str(entry.get("path") or "")
        confirmed_path = str(alias.get("broader_rollout_canonical_path_confirmed") or "")
        status = "ready_for_commit"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "missing_artifact_key"
            blockers.append("artifact_key_required")
        if alias.get("broader_rollout_applied") is not True:
            status = "broader_rollout_not_applied"
            blockers.append("broader_rollout_applied_required")
        if alias.get("broader_rollout_planned") is not True:
            status = "broader_rollout_not_planned"
            blockers.append("broader_rollout_planned_required")
        if alias.get("foldered_canonical_finalized") is not True:
            status = "not_foldered_canonical_finalized"
            blockers.append("foldered_canonical_finalized_required")
        if confirmed_path and observed_path != confirmed_path:
            status = "canonical_path_changed_after_broader_rollout"
            blockers.append("canonical_path_must_match_broader_rollout_confirmation")
        if alias.get("broader_rollout_rolled_back") is True:
            status = "broader_rollout_already_rolled_back"
            blockers.append("rollback_state_conflicts_with_commit")
        if alias.get("broader_rollout_committed") is True:
            warnings.append("broader_rollout_already_marked_committed_in_manifest")
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "observed_canonical_path": observed_path,
                "broader_rollout_canonical_path_confirmed": confirmed_path,
                "broader_rollout_applied": alias.get("broader_rollout_applied") is True,
                "broader_rollout_planned": alias.get("broader_rollout_planned") is True,
                "foldered_canonical_finalized": alias.get("foldered_canonical_finalized") is True,
                "broader_rollout_committed": alias.get("broader_rollout_committed") is True,
                "broader_rollout_rolled_back": alias.get("broader_rollout_rolled_back") is True,
                "canonical_path_stable": bool(observed_path and confirmed_path and observed_path == confirmed_path),
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return checks


def _foldered_canonical_broader_rollout_commit_backend_manifest(
    backend_manifest: dict[str, Any],
    *,
    transaction_id: str,
    commit_transaction_id: str,
    committed_at: str,
) -> dict[str, Any]:
    manifest = copy.deepcopy(backend_manifest)
    committed_count = 0
    for entry in manifest.get("entries", []):
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        if alias.get("broader_rollout_transaction_id") != transaction_id:
            continue
        alias["broader_rollout_committed"] = True
        alias["broader_rollout_committed_at"] = committed_at
        alias["broader_rollout_commit_transaction_id"] = commit_transaction_id
        alias["broader_rollout_rolled_back"] = False
        committed_count += 1
    metadata = manifest.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["foldered_canonical_broader_rollout_committed_at"] = committed_at
        metadata["foldered_canonical_broader_rollout_commit_transaction_id"] = commit_transaction_id
        metadata["foldered_canonical_broader_rollout_committed_transaction_id"] = transaction_id
        metadata["foldered_canonical_broader_rollout_committed_candidate_count"] = committed_count
    return manifest


def _read_foldered_canonical_broader_rollout_commit_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-journal.v1", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-journal.v1",
            "entries": [],
            "read_error": True,
        }
    if not isinstance(payload, dict):
        return {"schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-journal.v1", "entries": []}
    if not isinstance(payload.get("entries"), list):
        payload["entries"] = []
    return payload


def _find_foldered_canonical_broader_rollout_commit_duplicate(
    journal: dict[str, Any],
    *,
    commit_idempotency_key: str,
) -> dict[str, Any] | None:
    for entry in journal.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") == "committed" and entry.get("commit_idempotency_key") == commit_idempotency_key:
            return entry
    return None


def _foldered_canonical_broader_rollout_commit_journal_entry(
    *,
    status: str,
    transaction_id: str,
    commit_transaction_id: str,
    commit_idempotency_key: str,
    decision: str,
    manifest_entry_checks: list[dict[str, Any]],
    blockers: list[str],
    committed_at: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "transaction_id": transaction_id,
        "commit_transaction_id": commit_transaction_id,
        "commit_idempotency_key": commit_idempotency_key,
        "decision": decision,
        "committed_at": committed_at,
        "manifest_entry_count": len(manifest_entry_checks),
        "artifact_keys": [str(check.get("artifact_key") or "") for check in manifest_entry_checks if check.get("artifact_key")],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "side_effects": {
            "backend_manifest_mutated": status == "committed",
            "canonical_paths_changed": False,
            "files_moved": False,
            "rolled_back": False,
        },
    }


def _foldered_canonical_broader_rollout_commit_journal_payload(
    *,
    existing_journal: dict[str, Any],
    entry: dict[str, Any],
    append_entry: bool,
    updated_at: str,
) -> dict[str, Any]:
    payload = copy.deepcopy(existing_journal)
    payload["schema_version"] = "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-journal.v1"
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    payload["entries"] = list(entries)
    if append_entry:
        payload["entries"].append(entry)
    payload["entry_count"] = len(payload["entries"])
    payload["updated_at"] = updated_at
    payload["append_only"] = True
    return payload


def _compact_foldered_canonical_broader_rollout_commit_journal_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {
        "status": entry.get("status") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "commit_transaction_id": entry.get("commit_transaction_id") or "",
        "commit_idempotency_key": entry.get("commit_idempotency_key") or "",
        "decision": entry.get("decision") or "",
        "manifest_entry_count": _safe_int(entry.get("manifest_entry_count")),
    }


def _workspace_foldered_canonical_broader_rollout_commit_result_artifact_metadata(
    artifact_root: Path,
    *,
    written: bool,
) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_foldered_canonical_broader_rollout_commit_result",
        "legacy_path": "workspace/workspace-foldered-canonical-broader-rollout-commit-result.json",
        "future_path": "/workspace/review/workspace-foldered-canonical-broader-rollout-commit-result.json",
        "path": str(artifact_root / "workspace" / "workspace-foldered-canonical-broader-rollout-commit-result.json"),
        "written": written,
        "category": "audit",
    }


def _foldered_canonical_broader_rollout_commit_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "decision_record_unavailable_or_malformed" in blockers or "decision_record_not_recorded" in blockers:
        actions.append("record_reviewed_commit_decision_before_commit_executor")
    if "decision_record_does_not_select_commit" in blockers:
        actions.append("use_rollback_executor_for_rollback_decision_or_defer_without_executor")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_before_commit_executor")
    if "apply_requires_approve_commit_true" in blockers:
        actions.append("set_approve_commit_true_after_human_review")
    if "broader_rollout_commit_duplicate_idempotency_key" in blockers:
        actions.append("inspect_existing_broader_rollout_commit_journal_before_retry")
    if any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("repair_or_reaudit_current_manifest_before_commit_executor")
    if status == "planned":
        actions.append("review_commit_dry_run_then_rerun_apply_with_explicit_approval")
    if status == "committed":
        actions.append("review_foldered_canonical_broader_rollout_commit_result")
        actions.append("keep_rollback_executor_separate_if_future_revert_is_needed")
    if any("already_marked_committed" in warning for warning in warnings):
        actions.append("inspect_manifest_commit_metadata_for_idempotency_before_apply")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_broader_rollout_rollback_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    decision_record_json: str | None = None,
    decision_record_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_decision_record",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    commit_journal_json: str | None = None,
    commit_journal_artifact_ref: str | None = "workspace_foldered_canonical_broader_rollout_commit_journal",
    expected_transaction_id: str | None = None,
) -> dict[str, Any]:
    """Review explicit broader rollout rollback executor inputs without side effects."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    decision_record, decision_record_error, decision_record_input = (
        _load_or_read_workspace_foldered_canonical_broader_rollout_decision_record(
            default_artifact_root=effective_root,
            decision_record_json=decision_record_json,
            decision_record_artifact_ref=decision_record_artifact_ref,
        )
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )
    commit_journal, commit_journal_error, commit_journal_input = (
        _load_or_read_optional_workspace_foldered_canonical_broader_rollout_commit_journal(
            default_artifact_root=effective_root,
            commit_journal_json=commit_journal_json,
            commit_journal_artifact_ref=commit_journal_artifact_ref,
        )
    )

    record_summary = decision_record.get("summary") if isinstance(decision_record.get("summary"), dict) else {}
    record_body = decision_record.get("decision_record") if isinstance(decision_record.get("decision_record"), dict) else {}
    decision = str(record_body.get("decision") or record_summary.get("decision") or "").strip().lower()
    transaction_id = str(record_body.get("source_plan_transaction_id") or "").strip()
    idempotency_key = str(record_body.get("source_plan_idempotency_key") or transaction_id or "").strip()
    expected_transaction = str(expected_transaction_id or transaction_id or "").strip()
    manifest_entry_checks = _foldered_canonical_broader_rollout_rollback_preflight_manifest_entry_checks(
        backend_manifest=backend_manifest,
        transaction_id=transaction_id,
    )
    journal_entries = commit_journal.get("entries") if isinstance(commit_journal.get("entries"), list) else []
    valid_journal_entries = [entry for entry in journal_entries if isinstance(entry, dict)]
    matching_commit_journal_entry = _find_foldered_canonical_broader_rollout_commit_journal_entry_by_transaction(
        commit_journal,
        transaction_id=transaction_id,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if decision_record_error:
        blockers.append("decision_record_unavailable_or_malformed")
    if decision_record.get("status") != "recorded":
        blockers.append("decision_record_not_recorded")
    if record_summary.get("decision_record_written") is not True:
        blockers.append("decision_record_artifact_not_written")
    if record_body.get("recorded") is not True:
        blockers.append("decision_record_body_not_marked_recorded")
    if decision != "rollback":
        blockers.append("decision_record_does_not_select_rollback")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if commit_journal_error:
        blockers.append("commit_journal_unavailable_or_malformed")
    if not transaction_id:
        blockers.append("source_plan_transaction_id_missing")
    if expected_transaction and transaction_id and expected_transaction != transaction_id:
        blockers.append("expected_transaction_id_mismatch")
    if not manifest_entry_checks:
        blockers.append("no_current_manifest_entries_for_broader_rollout_transaction")
    for check in manifest_entry_checks:
        if check.get("status") != "ready_for_rollback":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status') or 'blocked'}")
    if matching_commit_journal_entry:
        blockers.append("commit_journal_contains_committed_entry_for_transaction")
    for reason_item in decision_record.get("blocking_reasons") or []:
        blockers.append(f"decision_record:{reason_item}")
    if commit_journal_input.get("read_status") == "missing":
        warnings.append("commit_journal_not_observed_optional_review_only_check")
    if not blockers:
        warnings.append("rollback_preflight_is_read_only_and_requires_separate_explicit_executor")

    ready_count = sum(1 for check in manifest_entry_checks if check.get("status") == "ready_for_rollback")
    status = "ready_for_review" if not blockers else "blocked" if decision_record.get("schema_version") != "missing" else "not_ready"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-rollback-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "decision_record_status": decision_record.get("status") or "missing",
            "decision": decision,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "manifest_entry_check_count": len(manifest_entry_checks),
            "ready_manifest_entry_check_count": ready_count,
            "all_manifest_entries_ready_for_rollback": bool(manifest_entry_checks) and ready_count == len(manifest_entry_checks),
            "commit_journal_entry_count": len(valid_journal_entries),
            "matching_commit_journal_entry_found": matching_commit_journal_entry is not None,
            "rollback_preflight_ready": status == "ready_for_review",
            "rollback_executed_by_this_tool": False,
            "commit_executed_by_this_tool": False,
            "artifacts_written": False,
            "backend_manifest_mutated_by_this_tool": False,
            "canonical_paths_changed_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "decision_record_input": decision_record_input,
        "backend_manifest_input": backend_manifest_input,
        "commit_journal_input": commit_journal_input,
        "decision_record_summary": {
            "schema_version": decision_record.get("schema_version") or "",
            "status": decision_record.get("status") or "missing",
            "decision": decision,
            "decision_record_written": record_summary.get("decision_record_written") is True,
            "reviewer": record_summary.get("reviewer") or record_body.get("reviewer") or "",
            "source_plan_transaction_id": transaction_id,
            "source_plan_idempotency_key": idempotency_key,
        },
        "digest_guard": {
            "expected_transaction_id": expected_transaction,
            "current_transaction_id": transaction_id,
            "expected_transaction_match": bool(expected_transaction and transaction_id and expected_transaction == transaction_id),
        },
        "commit_state_guard": {
            "commit_journal_entry_count": len(valid_journal_entries),
            "matching_commit_journal_entry_found": matching_commit_journal_entry is not None,
            "matching_commit_journal_entry": _compact_foldered_canonical_broader_rollout_commit_journal_entry(
                matching_commit_journal_entry
            ),
            "blocks_rollback_after_commit": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "rollback_executor_gate": {
            "ready_for_rollback_executor_review": status == "ready_for_review",
            "executor_tool": "execute_workspace_foldered_canonical_broader_rollout_rollback",
            "executor_implemented": False,
            "requires_explicit_review_approval_for_executor": status == "ready_for_review",
            "rollback_apply_executed_by_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_broader_rollout_rollback_preflight_next_actions(
            status,
            blockers,
            warnings,
        ),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "records_decision": False,
            "commits_broader_rollout": False,
            "rolls_back_broader_rollout": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_optional_workspace_foldered_canonical_broader_rollout_commit_journal(
    *,
    default_artifact_root: Path,
    commit_journal_json: str | None,
    commit_journal_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(commit_journal_json, field_name="commit_journal_json")
    if payload is not None or error:
        if payload is not None:
            if not isinstance(payload.get("entries"), list):
                payload["entries"] = []
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked", "entries": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = commit_journal_artifact_ref or "workspace_foldered_canonical_broader_rollout_commit_journal"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        payload = read_result["json"]
        if not isinstance(payload.get("entries"), list):
            payload["entries"] = []
        return payload, "", input_summary
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-broader-rollout-commit-journal.v1",
        "status": "missing",
        "entries": [],
    }, "", input_summary


def _foldered_canonical_broader_rollout_rollback_preflight_manifest_entry_checks(
    *,
    backend_manifest: dict[str, Any],
    transaction_id: str,
) -> list[dict[str, Any]]:
    if not transaction_id:
        return []
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    checks: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        if alias.get("broader_rollout_transaction_id") != transaction_id:
            continue
        artifact_key = str(entry.get("artifact_key") or "")
        observed_path = str(entry.get("path") or "")
        confirmed_path = str(alias.get("broader_rollout_canonical_path_confirmed") or "")
        status = "ready_for_rollback"
        blockers: list[str] = []
        warnings: list[str] = []
        if not artifact_key:
            status = "missing_artifact_key"
            blockers.append("artifact_key_required")
        if alias.get("broader_rollout_committed") is True:
            status = "broader_rollout_already_committed"
            blockers.append("committed_rollout_requires_separate_revert_track")
        if alias.get("broader_rollout_rolled_back") is True:
            status = "broader_rollout_already_rolled_back"
            blockers.append("rollback_state_already_recorded")
        if alias.get("broader_rollout_applied") is not True:
            status = "broader_rollout_not_applied"
            blockers.append("broader_rollout_applied_required")
        if alias.get("broader_rollout_planned") is not True:
            status = "broader_rollout_not_planned"
            blockers.append("broader_rollout_planned_required")
        if alias.get("foldered_canonical_finalized") is not True:
            status = "not_foldered_canonical_finalized"
            blockers.append("foldered_canonical_finalized_required")
        if confirmed_path and observed_path != confirmed_path:
            status = "canonical_path_changed_after_broader_rollout"
            blockers.append("canonical_path_must_match_broader_rollout_confirmation")
        if alias.get("legacy_fallback_tightened") is not True:
            warnings.append("legacy_fallback_not_marked_tightened_before_rollback")
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "observed_canonical_path": observed_path,
                "broader_rollout_canonical_path_confirmed": confirmed_path,
                "broader_rollout_applied": alias.get("broader_rollout_applied") is True,
                "broader_rollout_planned": alias.get("broader_rollout_planned") is True,
                "broader_rollout_committed": alias.get("broader_rollout_committed") is True,
                "broader_rollout_rolled_back": alias.get("broader_rollout_rolled_back") is True,
                "foldered_canonical_finalized": alias.get("foldered_canonical_finalized") is True,
                "canonical_path_stable": bool(observed_path and confirmed_path and observed_path == confirmed_path),
                "blockers": blockers,
                "warnings": warnings,
            }
        )
    return checks


def _find_foldered_canonical_broader_rollout_commit_journal_entry_by_transaction(
    journal: dict[str, Any],
    *,
    transaction_id: str,
) -> dict[str, Any] | None:
    if not transaction_id:
        return None
    for entry in journal.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") == "committed" and entry.get("transaction_id") == transaction_id:
            return entry
    return None


def _foldered_canonical_broader_rollout_rollback_preflight_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "decision_record_unavailable_or_malformed" in blockers or "decision_record_not_recorded" in blockers:
        actions.append("record_reviewed_rollback_decision_before_rollback_preflight")
    if "decision_record_does_not_select_rollback" in blockers:
        actions.append("use_commit_executor_for_commit_decision_or_defer_without_executor")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers:
        actions.append("provide_current_backend_manifest_before_rollback_preflight")
    if "commit_journal_unavailable_or_malformed" in blockers:
        actions.append("repair_or_pass_valid_commit_journal_before_rollback_preflight")
    if "commit_journal_contains_committed_entry_for_transaction" in blockers:
        actions.append("do_not_use_rollback_preflight_after_broader_rollout_commit")
    if any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("repair_or_reaudit_current_manifest_before_rollback_executor")
    if status == "ready_for_review":
        actions.append("review_rollback_preflight_before_separate_explicit_executor")
        actions.append("keep_rollback_executor_review_gated")
    if any("legacy_fallback" in warning for warning in warnings):
        actions.append("review_legacy_fallback_metadata_before_rollback_executor")
    return list(dict.fromkeys(actions))


def _load_or_read_workspace_foldered_canonical_legacy_fallback_tightening_result(
    *,
    default_artifact_root: Path,
    legacy_fallback_tightening_result_json: str | None,
    legacy_fallback_tightening_result_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(
        legacy_fallback_tightening_result_json,
        field_name="legacy_fallback_tightening_result_json",
    )
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = legacy_fallback_tightening_result_artifact_ref or "workspace_foldered_canonical_legacy_fallback_tightening_result"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "legacy_fallback_tightening_result_not_observed", input_summary


def _foldered_canonical_finalization_readiness_manifest_checks(
    *,
    tightening_result_checks: list[dict[str, Any]],
    backend_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for result_check in tightening_result_checks:
        artifact_key = str(result_check.get("artifact_key") or "")
        expected_canonical = str(result_check.get("observed_canonical_path") or result_check.get("expected_canonical_path") or "")
        expected_legacy = str(result_check.get("observed_legacy_fallback_path") or result_check.get("expected_legacy_fallback_path") or "")
        entry = entries_by_key.get(artifact_key)
        status = "ready"
        observed_canonical = ""
        observed_legacy = ""
        legacy_fallback_tightened = False
        legacy_fallback_preserved = False
        canonical_path_is_foldered = False
        if not artifact_key:
            status = "missing_artifact_key"
        elif not isinstance(entry, dict):
            status = "manifest_entry_missing"
        else:
            observed_canonical = str(entry.get("path") or "")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
            observed_legacy = str(alias.get("legacy_fallback_path") or "")
            legacy_fallback_tightened = alias.get("legacy_fallback_tightened") is True
            legacy_fallback_preserved = alias.get("legacy_fallback_preserved") is True
            canonical_path_is_foldered = bool(observed_canonical and observed_canonical != observed_legacy)
            if expected_canonical and observed_canonical != expected_canonical:
                status = "canonical_path_mismatch"
            elif expected_legacy and observed_legacy != expected_legacy:
                status = "legacy_fallback_path_mismatch"
            elif not canonical_path_is_foldered:
                status = "canonical_path_not_foldered"
            elif not legacy_fallback_tightened:
                status = "legacy_fallback_not_tightened"
            elif legacy_fallback_preserved:
                status = "legacy_fallback_still_preserved"
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "expected_canonical_path": expected_canonical,
                "observed_canonical_path": observed_canonical,
                "expected_legacy_fallback_path": expected_legacy,
                "observed_legacy_fallback_path": observed_legacy,
                "canonical_path_is_foldered": canonical_path_is_foldered,
                "legacy_fallback_tightened": legacy_fallback_tightened,
                "legacy_fallback_preserved": legacy_fallback_preserved,
            }
        )
    return checks


def _foldered_canonical_finalization_readiness_next_actions(
    status: str,
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    actions: list[str] = []
    if "legacy_fallback_tightening_result_unavailable_or_malformed" in blockers or "legacy_fallback_tightening_result_not_applied" in blockers:
        actions.append("execute_or_pass_applied_legacy_fallback_tightening_result_before_finalization_review")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or any(reason.startswith("manifest_entry:") for reason in blockers):
        actions.append("refresh_backend_manifest_and_recheck_finalization_readiness")
    if status == "ready_for_review":
        actions.append("review_foldered_canonical_finalization_plan_as_separate_step")
        actions.append("do_not_finalize_from_readiness_descriptor")
    if any("finalization" in warning for warning in warnings):
        actions.append("keep_foldered_canonical_finalization_review_gated")
    return list(dict.fromkeys(actions))


def review_workspace_foldered_canonical_migration_physical_apply_preflight_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    migration_manifest_dry_run_json: str | None = None,
    migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
    migration_apply_plan_json: str | None = None,
    migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
    review_approval_ledger_json: str | None = None,
    review_approval_ledger_artifact_ref: str | None = "workspace_review_approval_ledger",
    rollback_checkpoint_json: str | None = None,
    rollback_checkpoint_artifact_ref: str | None = "workspace_foldered_canonical_migration_rollback_checkpoint",
) -> dict[str, Any]:
    """Return a read-only preflight descriptor for a future foldered-canonical physical apply executor."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    dry_run, dry_run_error, dry_run_input = _load_or_read_workspace_foldered_canonical_migration_manifest_dry_run(
        default_artifact_root=effective_root,
        migration_manifest_dry_run_json=migration_manifest_dry_run_json,
        migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
    )
    apply_plan, apply_plan_error, apply_plan_input = _load_or_read_workspace_foldered_canonical_migration_apply_plan(
        default_artifact_root=effective_root,
        migration_apply_plan_json=migration_apply_plan_json,
        migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
    )
    approval_ledger, approval_ledger_error, approval_ledger_input = _load_or_read_review_approval_ledger(
        default_artifact_root=effective_root,
        review_approval_ledger_json=review_approval_ledger_json,
        review_approval_ledger_artifact_ref=review_approval_ledger_artifact_ref,
    )
    rollback_checkpoint, rollback_checkpoint_error, rollback_checkpoint_input = _load_or_read_workspace_foldered_canonical_rollback_checkpoint(
        default_artifact_root=effective_root,
        rollback_checkpoint_json=rollback_checkpoint_json,
        rollback_checkpoint_artifact_ref=rollback_checkpoint_artifact_ref,
    )

    dry_run_gate = dry_run.get("execution_gate") if isinstance(dry_run.get("execution_gate"), dict) else {}
    dry_run_digest = dry_run.get("digest_guard") if isinstance(dry_run.get("digest_guard"), dict) else {}
    dry_run_manifest = dry_run.get("manifest_dry_run") if isinstance(dry_run.get("manifest_dry_run"), dict) else {}
    dry_run_rollback = dry_run.get("rollback_checkpoint") if isinstance(dry_run.get("rollback_checkpoint"), dict) else {}
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    planned_steps = apply_plan_section.get("planned_steps") if isinstance(apply_plan_section.get("planned_steps"), list) else []
    valid_steps = [step for step in planned_steps if isinstance(step, dict)]
    current_apply_plan_digest = _foldered_canonical_apply_plan_digest(apply_plan)
    dry_run_apply_plan_digest = str(dry_run_digest.get("current_apply_plan_digest") or dry_run_digest.get("approval_apply_plan_digest") or "")
    expected_approval = _foldered_canonical_physical_apply_expected_approval(
        apply_plan_digest=current_apply_plan_digest,
        dry_run=dry_run,
    )
    approval_evidence = _foldered_canonical_physical_apply_approval_evidence(
        approval_ledger=approval_ledger,
        expected=expected_approval,
    )
    rollback_evidence = _foldered_canonical_physical_apply_rollback_evidence(
        rollback_checkpoint=rollback_checkpoint,
        rollback_checkpoint_error=rollback_checkpoint_error,
        rollback_plan=dry_run_rollback,
        apply_plan_digest=current_apply_plan_digest,
    )
    executor_inputs = _foldered_canonical_physical_apply_executor_inputs(
        apply_plan=apply_plan,
        dry_run=dry_run,
        approval_evidence=approval_evidence,
        rollback_evidence=rollback_evidence,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    if dry_run_error:
        blockers.append("foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed")
    if dry_run.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_manifest_dry_run_not_ready")
    if dry_run_gate.get("ready_for_manifest_dry_run_review") is not True:
        blockers.append("manifest_dry_run_review_gate_not_ready")
    if apply_plan_error:
        blockers.append("foldered_canonical_migration_apply_plan_unavailable_or_malformed")
    if apply_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_apply_plan_not_ready")
    if apply_plan_section.get("plan_only") is not True:
        blockers.append("foldered_canonical_migration_apply_plan_not_plan_only")
    if not valid_steps:
        blockers.append("physical_apply_preflight_has_no_apply_steps")
    if dry_run_apply_plan_digest and current_apply_plan_digest and dry_run_apply_plan_digest != current_apply_plan_digest:
        blockers.append("manifest_dry_run_apply_plan_digest_mismatch")
    if not dry_run_apply_plan_digest:
        blockers.append("manifest_dry_run_apply_plan_digest_missing")
    if approval_ledger_error:
        blockers.append("review_approval_ledger_unavailable_or_malformed")
    if not approval_evidence["matching_approval_found"]:
        blockers.append("review_approval_ledger_missing_matching_physical_apply_approval")
    if not approval_evidence["approved"]:
        blockers.append("review_approval_ledger_does_not_approve_physical_apply")
    if dry_run_rollback.get("required_before_apply") is not True:
        blockers.append("rollback_checkpoint_requirement_not_ready")
    if dry_run_manifest.get("planned_changes") and dry_run_manifest.get("writes_artifact_in_this_tool") is not False:
        blockers.append("manifest_dry_run_allows_artifact_write_in_tool")
    if dry_run_manifest.get("mutates_manifest_in_this_tool") is not False:
        blockers.append("manifest_dry_run_allows_manifest_mutation_in_tool")
    if rollback_evidence["checkpoint_provided"] and not rollback_evidence["checkpoint_matches_apply_plan_digest"]:
        blockers.append("rollback_checkpoint_apply_plan_digest_mismatch")
    if not rollback_evidence["checkpoint_provided"]:
        warnings.append("rollback_checkpoint_must_be_materialized_by_physical_apply_executor_before_manifest_mutation")
    if rollback_evidence["checkpoint_provided"] and not rollback_evidence["captures_backend_manifest_snapshot"]:
        warnings.append("rollback_checkpoint_missing_backend_manifest_snapshot_evidence")
    if not blockers:
        warnings.append("physical_apply_preflight_ready_for_explicit_reviewed_executor")
        warnings.append("post_apply_validation_must_run_after_physical_apply")

    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-preflight.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "manifest_dry_run_status": dry_run.get("status") or "missing",
            "apply_plan_status": apply_plan.get("status") or "missing",
            "planned_apply_step_count": len(valid_steps),
            "review_approval_ledger_status": "loaded" if not approval_ledger_error else "missing_or_blocked",
            "matching_review_approval_found": approval_evidence["matching_approval_found"],
            "rollback_checkpoint_provided": rollback_evidence["checkpoint_provided"],
            "rollback_checkpoint_required_before_manifest_mutation": True,
            "transaction_journal_required": True,
            "idempotency_guard_required": True,
            "post_apply_validation_required": True,
            "ready_for_physical_apply_executor_review": status == "ready_for_review",
            "physical_apply_executed_by_this_tool": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "manifest_dry_run_summary": _compact_foldered_canonical_migration_manifest_dry_run(dry_run),
        "apply_plan_summary": _compact_foldered_canonical_migration_apply_plan(apply_plan),
        "manifest_dry_run_input": dry_run_input,
        "apply_plan_input": apply_plan_input,
        "review_approval_ledger_input": approval_ledger_input,
        "rollback_checkpoint_input": rollback_checkpoint_input,
        "digest_guard": {
            "manifest_dry_run_apply_plan_digest": dry_run_apply_plan_digest,
            "current_apply_plan_digest": current_apply_plan_digest,
            "digest_match": bool(dry_run_apply_plan_digest and current_apply_plan_digest and dry_run_apply_plan_digest == current_apply_plan_digest),
            "requires_executor_revalidation_before_each_write": True,
        },
        "review_approval_gate": approval_evidence,
        "rollback_checkpoint_gate": rollback_evidence,
        "transaction_journal_plan": {
            "required": True,
            "append_only": True,
            "journal_artifact": "workspace/workspace-foldered-canonical-migration-physical-apply-journal.json",
            "writes_journal_in_this_tool": False,
            "records_apply_plan_digest": True,
            "records_manifest_dry_run_digest": True,
            "records_approval_evidence": True,
            "records_rollback_checkpoint_evidence": True,
        },
        "idempotency_guard": {
            "required": True,
            "idempotency_key": approval_evidence.get("idempotency_key") or expected_approval["idempotency_key"],
            "checks_existing_apply_journal_in_this_tool": False,
            "must_block_duplicate_physical_apply": True,
        },
        "post_apply_validation_requirement": {
            "required_after_apply": True,
            "validation_tool": "review_workspace_foldered_canonical_migration_post_apply_validation",
            "validation_artifact": "workspace/workspace-foldered-canonical-migration-post-apply-validation.json",
            "runs_validation_in_this_tool": False,
            "legacy_fallback_must_remain_until_validation_review": True,
        },
        "executor_inputs": executor_inputs,
        "execution_gate": {
            "ready_for_physical_apply_executor_review": status == "ready_for_review",
            "requires_explicit_review_approval": True,
            "requires_separate_physical_apply_executor": True,
            "allows_automatic_execution": False,
            "allows_journal_write_in_this_tool": False,
            "allows_rollback_checkpoint_write_in_this_tool": False,
            "allows_manifest_mutation_in_this_tool": False,
            "allows_canonical_path_change_in_this_tool": False,
            "allows_file_move_in_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_physical_apply_preflight_next_actions(blockers, warnings),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "mutates_manifests": False,
            "writes_transaction_journal": False,
            "writes_rollback_checkpoint": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _load_or_read_review_approval_ledger(
    *,
    default_artifact_root: Path,
    review_approval_ledger_json: str | None,
    review_approval_ledger_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(review_approval_ledger_json, field_name="review_approval_ledger_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"version": "invalid-json", "entries": []}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = review_approval_ledger_artifact_ref or "workspace_review_approval_ledger"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"version": "missing", "entries": []}, "review_approval_ledger_not_observed", input_summary


def _load_or_read_workspace_foldered_canonical_rollback_checkpoint(
    *,
    default_artifact_root: Path,
    rollback_checkpoint_json: str | None,
    rollback_checkpoint_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(rollback_checkpoint_json, field_name="rollback_checkpoint_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = rollback_checkpoint_artifact_ref or "workspace_foldered_canonical_migration_rollback_checkpoint"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "foldered_canonical_rollback_checkpoint_not_observed", input_summary


def _foldered_canonical_physical_apply_expected_approval(*, apply_plan_digest: str, dry_run: dict[str, Any]) -> dict[str, Any]:
    rollback = dry_run.get("rollback_checkpoint") if isinstance(dry_run.get("rollback_checkpoint"), dict) else {}
    transaction_id = str(rollback.get("transaction_id") or "")
    idempotency_key = str(rollback.get("idempotency_key") or transaction_id or apply_plan_digest[:16])
    subject_id = f"workspace-foldered-canonical-physical-apply:{apply_plan_digest}" if apply_plan_digest else "workspace-foldered-canonical-physical-apply"
    return {
        "subject_id": subject_id,
        "action": "foldered_canonical_physical_apply",
        "decision": "approved",
        "apply_plan_digest": apply_plan_digest,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
    }


def _foldered_canonical_physical_apply_approval_evidence(
    *,
    approval_ledger: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    entries = approval_ledger.get("entries") if isinstance(approval_ledger.get("entries"), list) else []
    candidates = [entry for entry in entries if isinstance(entry, dict)]
    matching: dict[str, Any] | None = None
    for entry in candidates:
        if entry.get("subject_id") == expected["subject_id"] and entry.get("action") == expected["action"]:
            matching = entry
            break
    approved = bool(matching and matching.get("decision") == "approved" and matching.get("status") == "written")
    digest = str((matching or {}).get("subject_digest_sha256") or "")
    digest_matches = bool(digest and expected.get("apply_plan_digest") and digest == expected.get("apply_plan_digest"))
    metadata = matching.get("metadata") if isinstance((matching or {}).get("metadata"), dict) else {}
    return {
        "review_required": True,
        "approval_ledger_artifact": "workspace/review-approval-ledger.json",
        "expected_subject_id": expected["subject_id"],
        "expected_action": expected["action"],
        "expected_decision": expected["decision"],
        "matching_approval_found": matching is not None,
        "approved": bool(approved and digest_matches),
        "approval_status": str((matching or {}).get("status") or "missing"),
        "approval_id": str((matching or {}).get("approval_id") or ""),
        "reviewer": str((matching or {}).get("reviewer") or ""),
        "subject_digest_sha256": digest,
        "expected_apply_plan_digest": expected.get("apply_plan_digest") or "",
        "digest_matches_expected": digest_matches,
        "transaction_id": str(metadata.get("transaction_id") or expected.get("transaction_id") or ""),
        "idempotency_key": str(metadata.get("idempotency_key") or expected.get("idempotency_key") or ""),
        "writes_approval_in_this_tool": False,
        "ledger_entry_count": len(candidates),
    }


def _foldered_canonical_physical_apply_rollback_evidence(
    *,
    rollback_checkpoint: dict[str, Any],
    rollback_checkpoint_error: str,
    rollback_plan: dict[str, Any],
    apply_plan_digest: str,
) -> dict[str, Any]:
    checkpoint_digest = str(rollback_checkpoint.get("apply_plan_digest") or rollback_checkpoint.get("current_apply_plan_digest") or "")
    checkpoint_provided = not bool(rollback_checkpoint_error) and rollback_checkpoint.get("schema_version") not in {"missing", "invalid-json"}
    return {
        "required_before_manifest_mutation": True,
        "checkpoint_artifact": "workspace/workspace-foldered-canonical-migration-rollback-checkpoint.json",
        "checkpoint_provided": checkpoint_provided,
        "checkpoint_status": rollback_checkpoint.get("status") or "missing",
        "writes_checkpoint_in_this_tool": False,
        "must_be_written_by_physical_apply_executor_before_manifest_mutation": not checkpoint_provided,
        "captures_backend_manifest_snapshot": bool(
            rollback_checkpoint.get("backend_manifest_snapshot")
            or rollback_checkpoint.get("captures_backend_manifest_snapshot")
            or rollback_plan.get("captures_backend_manifest_snapshot")
        ),
        "captures_apply_plan_digest": bool(checkpoint_digest or rollback_plan.get("captures_apply_plan_digest")),
        "checkpoint_apply_plan_digest": checkpoint_digest,
        "expected_apply_plan_digest": apply_plan_digest,
        "checkpoint_matches_apply_plan_digest": bool((not checkpoint_digest and not checkpoint_provided) or (checkpoint_digest and checkpoint_digest == apply_plan_digest)),
        "source_plan": {
            "planned_manifest_change_count": _safe_int(rollback_plan.get("planned_manifest_change_count")),
            "rollback_item_count": _safe_int(rollback_plan.get("rollback_item_count")),
            "transaction_id": rollback_plan.get("transaction_id") or "",
            "idempotency_key": rollback_plan.get("idempotency_key") or "",
        },
    }


def _foldered_canonical_physical_apply_executor_inputs(
    *,
    apply_plan: dict[str, Any],
    dry_run: dict[str, Any],
    approval_evidence: dict[str, Any],
    rollback_evidence: dict[str, Any],
) -> dict[str, Any]:
    apply_plan_section = apply_plan.get("apply_plan") if isinstance(apply_plan.get("apply_plan"), dict) else {}
    dry_run_manifest = dry_run.get("manifest_dry_run") if isinstance(dry_run.get("manifest_dry_run"), dict) else {}
    planned_steps = apply_plan_section.get("planned_steps") if isinstance(apply_plan_section.get("planned_steps"), list) else []
    planned_changes = dry_run_manifest.get("planned_changes") if isinstance(dry_run_manifest.get("planned_changes"), list) else []
    return {
        "review_required": True,
        "executor_name": "execute_workspace_foldered_canonical_physical_apply",
        "executor_not_implemented_by_this_tool": True,
        "apply_step_count": len([item for item in planned_steps if isinstance(item, dict)]),
        "manifest_change_count": len([item for item in planned_changes if isinstance(item, dict)]),
        "requires_matching_review_approval": True,
        "requires_rollback_checkpoint_before_manifest_mutation": True,
        "requires_append_only_transaction_journal": True,
        "requires_idempotency_guard": True,
        "requires_post_apply_validation": True,
        "approval_subject_id": approval_evidence.get("expected_subject_id") or "",
        "approval_id": approval_evidence.get("approval_id") or "",
        "transaction_id": approval_evidence.get("transaction_id") or rollback_evidence.get("source_plan", {}).get("transaction_id") or "",
        "idempotency_key": approval_evidence.get("idempotency_key") or rollback_evidence.get("source_plan", {}).get("idempotency_key") or "",
        "planned_artifact_keys": [str(item.get("artifact_key") or "") for item in planned_steps if isinstance(item, dict)],
    }


def _foldered_canonical_physical_apply_preflight_next_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_manifest_dry_run")
    if "foldered_canonical_migration_apply_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_matching_foldered_canonical_migration_apply_plan")
    if "manifest_dry_run_apply_plan_digest_mismatch" in blockers or "manifest_dry_run_apply_plan_digest_missing" in blockers:
        actions.append("regenerate_manifest_dry_run_from_current_apply_plan_before_physical_apply_preflight")
    if "review_approval_ledger_unavailable_or_malformed" in blockers or "review_approval_ledger_missing_matching_physical_apply_approval" in blockers:
        actions.append("record_review_approval_for_foldered_canonical_physical_apply")
    if "review_approval_ledger_does_not_approve_physical_apply" in blockers:
        actions.append("resolve_review_approval_ledger_decision_or_digest_before_apply")
    if "rollback_checkpoint_apply_plan_digest_mismatch" in blockers:
        actions.append("regenerate_rollback_checkpoint_from_current_apply_plan")
    if not blockers:
        actions.append("review_physical_apply_preflight_before_running_separate_executor")
        actions.append("run_separate_explicit_physical_apply_executor_with_transaction_journal_and_rollback_checkpoint")
        actions.append("run_post_apply_validation_descriptor_after_executor")
    if "rollback_checkpoint_must_be_materialized_by_physical_apply_executor_before_manifest_mutation" in warnings:
        actions.append("ensure_physical_apply_executor_writes_rollback_checkpoint_before_manifest_mutation")
    return actions


def execute_workspace_foldered_canonical_physical_apply_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    mode: str = "dry-run",
    approve_physical_apply: bool = False,
    physical_apply_preflight_json: str | None = None,
    physical_apply_preflight_artifact_ref: str | None = "workspace_foldered_canonical_migration_physical_apply_preflight",
    migration_manifest_dry_run_json: str | None = None,
    migration_manifest_dry_run_artifact_ref: str | None = "workspace_foldered_canonical_migration_manifest_dry_run",
    migration_apply_plan_json: str | None = None,
    migration_apply_plan_artifact_ref: str | None = "workspace_foldered_canonical_migration_apply_plan",
    backend_manifest_json: str | None = None,
    backend_manifest_artifact_ref: str | None = "workspace_backend_artifact_manifest",
    expected_apply_plan_digest: str | None = None,
) -> dict[str, Any]:
    """Execute an explicit-review-only backend-manifest canonical path promotion."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    workspace_dir = effective_root / "workspace"
    result_path = workspace_dir / "workspace-foldered-canonical-migration-physical-apply-result.json"
    journal_path = workspace_dir / "workspace-foldered-canonical-migration-physical-apply-journal.json"
    rollback_checkpoint_path = workspace_dir / "workspace-foldered-canonical-migration-rollback-checkpoint.json"

    preflight, preflight_error, preflight_input = _load_or_read_workspace_foldered_canonical_physical_apply_preflight(
        default_artifact_root=effective_root,
        physical_apply_preflight_json=physical_apply_preflight_json,
        physical_apply_preflight_artifact_ref=physical_apply_preflight_artifact_ref,
    )
    dry_run, dry_run_error, dry_run_input = _load_or_read_workspace_foldered_canonical_migration_manifest_dry_run(
        default_artifact_root=effective_root,
        migration_manifest_dry_run_json=migration_manifest_dry_run_json,
        migration_manifest_dry_run_artifact_ref=migration_manifest_dry_run_artifact_ref,
    )
    apply_plan, apply_plan_error, apply_plan_input = _load_or_read_workspace_foldered_canonical_migration_apply_plan(
        default_artifact_root=effective_root,
        migration_apply_plan_json=migration_apply_plan_json,
        migration_apply_plan_artifact_ref=migration_apply_plan_artifact_ref,
    )
    backend_manifest, backend_manifest_error, backend_manifest_input = _load_or_read_workspace_backend_artifact_manifest(
        default_artifact_root=effective_root,
        backend_manifest_json=backend_manifest_json,
        backend_manifest_artifact_ref=backend_manifest_artifact_ref,
    )

    requested_mode = mode or "dry-run"
    dry_run_mode = requested_mode == "dry-run"
    apply_mode = requested_mode == "apply"
    created_at = datetime.now(timezone.utc).isoformat()
    apply_plan_digest = _foldered_canonical_apply_plan_digest(apply_plan)
    expected_digest = expected_apply_plan_digest or apply_plan_digest
    dry_run_digest = _foldered_canonical_manifest_dry_run_apply_plan_digest(dry_run)
    preflight_digest = _foldered_canonical_physical_preflight_apply_plan_digest(preflight)
    dry_run_manifest = dry_run.get("manifest_dry_run") if isinstance(dry_run.get("manifest_dry_run"), dict) else {}
    planned_changes = [item for item in dry_run_manifest.get("planned_changes", []) if isinstance(item, dict)]
    approval_gate = preflight.get("review_approval_gate") if isinstance(preflight.get("review_approval_gate"), dict) else {}
    preflight_gate = preflight.get("execution_gate") if isinstance(preflight.get("execution_gate"), dict) else {}
    approval_transaction_id = str(approval_gate.get("transaction_id") or "")
    approval_idempotency_key = str(approval_gate.get("idempotency_key") or "")
    transaction_id = approval_transaction_id or f"foldered-canonical-physical-apply-{apply_plan_digest[:16] or 'missing'}"
    idempotency_key = approval_idempotency_key or transaction_id
    existing_journal = _read_foldered_canonical_physical_apply_journal(journal_path)
    duplicate_entry = _find_foldered_canonical_physical_apply_duplicate(existing_journal, idempotency_key=idempotency_key)
    manifest_entries = backend_manifest.get("entries") if isinstance(backend_manifest.get("entries"), list) else []
    manifest_entry_checks = _foldered_canonical_physical_apply_manifest_entry_checks(planned_changes, manifest_entries)

    blockers: list[str] = []
    warnings: list[str] = []
    if requested_mode not in {"dry-run", "apply"}:
        blockers.append("unsupported_physical_apply_mode")
    if apply_mode and not approve_physical_apply:
        blockers.append("apply_requires_approve_physical_apply_true")
    if preflight_error:
        blockers.append("physical_apply_preflight_unavailable_or_malformed")
    if preflight.get("status") != "ready_for_review":
        blockers.append("physical_apply_preflight_not_ready")
    if preflight_gate.get("ready_for_physical_apply_executor_review") is not True:
        blockers.append("physical_apply_preflight_gate_not_ready")
    if dry_run_error:
        blockers.append("foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed")
    if dry_run.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_manifest_dry_run_not_ready")
    if apply_plan_error:
        blockers.append("foldered_canonical_migration_apply_plan_unavailable_or_malformed")
    if apply_plan.get("status") != "ready_for_review":
        blockers.append("foldered_canonical_migration_apply_plan_not_ready")
    if backend_manifest_error:
        blockers.append("backend_artifact_manifest_unavailable_or_malformed")
    if backend_manifest_json is not None and apply_mode:
        blockers.append("apply_requires_backend_manifest_artifact_ref_not_inline_json")
    if not planned_changes:
        blockers.append("physical_apply_has_no_manifest_changes")
    if expected_digest and apply_plan_digest and expected_digest != apply_plan_digest:
        blockers.append("expected_apply_plan_digest_mismatch")
    if dry_run_digest and apply_plan_digest and dry_run_digest != apply_plan_digest:
        blockers.append("manifest_dry_run_apply_plan_digest_mismatch")
    if preflight_digest and apply_plan_digest and preflight_digest != apply_plan_digest:
        blockers.append("physical_apply_preflight_apply_plan_digest_mismatch")
    if not approval_gate.get("approved"):
        blockers.append("physical_apply_review_approval_not_approved")
    if not approval_gate.get("digest_matches_expected"):
        blockers.append("physical_apply_review_approval_digest_mismatch")
    if duplicate_entry:
        blockers.append("physical_apply_duplicate_idempotency_key")
    for check in manifest_entry_checks:
        if check.get("status") != "ready":
            blockers.append(f"manifest_entry:{check.get('artifact_key') or 'unknown'}:{check.get('status')}")
    if not apply_mode:
        warnings.append("physical_apply_dry_run_does_not_write_checkpoint_journal_or_manifest")
    if apply_mode and not blockers:
        warnings.append("physical_apply_will_preserve_legacy_fallback_until_post_apply_validation")
        warnings.append("post_apply_validation_required_before_legacy_fallback_tightening")

    status = "blocked" if blockers else "planned" if dry_run_mode else "applied"
    mutated_manifest = _foldered_canonical_promoted_backend_manifest(
        backend_manifest,
        planned_changes,
        transaction_id=transaction_id,
        applied_at=created_at,
    )
    rollback_checkpoint = _foldered_canonical_physical_apply_rollback_checkpoint_payload(
        status="planned" if dry_run_mode or blockers else "written",
        backend_manifest=backend_manifest,
        planned_changes=planned_changes,
        apply_plan_digest=apply_plan_digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        created_at=created_at,
    )
    journal_entry = _foldered_canonical_physical_apply_journal_entry(
        status=status,
        apply_plan_digest=apply_plan_digest,
        manifest_dry_run_digest=dry_run_digest,
        preflight_digest=preflight_digest,
        transaction_id=transaction_id,
        idempotency_key=idempotency_key,
        planned_changes=planned_changes,
        approval_gate=approval_gate,
        blockers=blockers,
        created_at=created_at,
    )
    journal_payload = _foldered_canonical_physical_apply_journal_payload(
        existing_journal=existing_journal,
        entry=journal_entry,
        append_entry=apply_mode and not blockers,
        updated_at=created_at,
    )

    writes = {
        "rollback_checkpoint": False,
        "backend_manifest": False,
        "journal": False,
        "result": False,
    }
    if apply_mode and not blockers:
        _write_json_file(rollback_checkpoint_path, rollback_checkpoint)
        _write_json_file(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input), mutated_manifest)
        _write_json_file(journal_path, journal_payload)
        writes.update({"rollback_checkpoint": True, "backend_manifest": True, "journal": True})

    payload = {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-result.v1",
        "status": status,
        "mode": requested_mode,
        "artifact_root": str(effective_root),
        "summary": {
            "planned_manifest_change_count": len(planned_changes),
            "manifest_entry_check_count": len(manifest_entry_checks),
            "applied_manifest_change_count": len(planned_changes) if status == "applied" else 0,
            "transaction_id": transaction_id,
            "idempotency_key": idempotency_key,
            "rollback_checkpoint_written": writes["rollback_checkpoint"],
            "transaction_journal_written": writes["journal"],
            "backend_manifest_mutated": writes["backend_manifest"],
            "result_artifact_written": False,
            "legacy_fallback_tightened": False,
            "files_moved": False,
            "post_apply_validation_required": True,
            "mobile_full_runtime_chains_deferred": True,
        },
        "physical_apply_preflight_input": preflight_input,
        "manifest_dry_run_input": dry_run_input,
        "apply_plan_input": apply_plan_input,
        "backend_manifest_input": backend_manifest_input,
        "digest_guard": {
            "expected_apply_plan_digest": expected_digest,
            "current_apply_plan_digest": apply_plan_digest,
            "manifest_dry_run_apply_plan_digest": dry_run_digest,
            "physical_apply_preflight_apply_plan_digest": preflight_digest,
            "expected_digest_match": bool(expected_digest and apply_plan_digest and expected_digest == apply_plan_digest),
            "manifest_dry_run_digest_match": bool(dry_run_digest and apply_plan_digest and dry_run_digest == apply_plan_digest),
            "preflight_digest_match": bool(preflight_digest and apply_plan_digest and preflight_digest == apply_plan_digest),
        },
        "review_approval_gate": approval_gate,
        "idempotency_guard": {
            "idempotency_key": idempotency_key,
            "duplicate_entry_found": duplicate_entry is not None,
            "duplicate_entry": _compact_physical_apply_journal_entry(duplicate_entry),
            "blocks_duplicate_apply": True,
        },
        "manifest_entry_checks": manifest_entry_checks,
        "rollback_checkpoint": {
            "path": str(rollback_checkpoint_path),
            "status": rollback_checkpoint["status"],
            "writes_checkpoint_in_apply_mode": writes["rollback_checkpoint"],
            "captures_backend_manifest_snapshot": True,
            "apply_plan_digest": apply_plan_digest,
        },
        "transaction_journal": {
            "path": str(journal_path),
            "append_only": True,
            "entry_count": len(journal_payload.get("entries", [])),
            "entry_appended": writes["journal"],
            "writes_journal_in_apply_mode": writes["journal"],
        },
        "backend_manifest_mutation": {
            "path": str(_physical_apply_backend_manifest_path(effective_root, backend_manifest_input)),
            "mutates_backend_manifest_in_apply_mode": writes["backend_manifest"],
            "changes_canonical_paths": status == "applied",
            "preserves_legacy_fallback": True,
            "tightens_legacy_fallback": False,
            "files_moved": False,
        },
        "post_apply_validation_requirement": {
            "required_after_apply": True,
            "validation_tool": "review_workspace_foldered_canonical_migration_post_apply_validation",
            "validation_artifact": "workspace/workspace-foldered-canonical-migration-post-apply-validation.json",
            "legacy_fallback_tightening_allowed_by_this_tool": False,
        },
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "recommended_next_actions": _foldered_canonical_physical_apply_next_actions(status, blockers, warnings),
        "side_effect_policy": {
            "dry_run_is_read_only": True,
            "artifacts_written": apply_mode and not blockers,
            "writes_rollback_checkpoint": writes["rollback_checkpoint"],
            "writes_transaction_journal": writes["journal"],
            "writes_result_artifact": False,
            "creates_directories": apply_mode and not blockers,
            "runs_pipeline": False,
            "enables_dual_write": False,
            "moves_files": False,
            "migrates_paths": False,
            "changes_canonical_paths": status == "applied",
            "mutates_manifests": writes["backend_manifest"],
            "tightens_legacy_fallback": False,
            "starts_browser": False,
            "sends_cdp_commands": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if apply_mode and not blockers:
        payload["summary"]["result_artifact_written"] = True
        payload["side_effect_policy"]["writes_result_artifact"] = True
        _write_json_file(result_path, payload)
        writes["result"] = True
    return payload


def _load_or_read_workspace_foldered_canonical_physical_apply_preflight(
    *,
    default_artifact_root: Path,
    physical_apply_preflight_json: str | None,
    physical_apply_preflight_artifact_ref: str | None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    payload, error = _parse_json_object(physical_apply_preflight_json, field_name="physical_apply_preflight_json")
    if payload is not None or error:
        if payload is not None:
            return payload, "", {"source": "inline-json", "artifact_ref": ""}
        return {"schema_version": "invalid-json", "status": "blocked"}, error, {"source": "inline-json", "artifact_ref": ""}
    artifact_ref = physical_apply_preflight_artifact_ref or "workspace_foldered_canonical_migration_physical_apply_preflight"
    read_result = read_workspace_artifact_payload(
        artifact_ref=artifact_ref,
        default_artifact_root=default_artifact_root,
        max_chars=200000,
    )
    input_summary = {
        "source": "artifact-ref",
        "artifact_ref": artifact_ref,
        "read_status": read_result.get("status") or "",
        "resolution_status": read_result.get("resolution_status") or "",
        "path": read_result.get("path") or "",
    }
    if read_result.get("status") == "found" and isinstance(read_result.get("json"), dict):
        return read_result["json"], "", input_summary
    return {"schema_version": "missing", "status": "missing"}, "physical_apply_preflight_not_observed", input_summary


def _foldered_canonical_manifest_dry_run_apply_plan_digest(dry_run: dict[str, Any]) -> str:
    guard = dry_run.get("digest_guard") if isinstance(dry_run.get("digest_guard"), dict) else {}
    return str(guard.get("current_apply_plan_digest") or guard.get("approval_apply_plan_digest") or "")


def _foldered_canonical_physical_preflight_apply_plan_digest(preflight: dict[str, Any]) -> str:
    guard = preflight.get("digest_guard") if isinstance(preflight.get("digest_guard"), dict) else {}
    return str(guard.get("current_apply_plan_digest") or guard.get("manifest_dry_run_apply_plan_digest") or "")


def _foldered_canonical_physical_apply_manifest_entry_checks(planned_changes: list[dict[str, Any]], manifest_entries: list[Any]) -> list[dict[str, Any]]:
    entries_by_key = {
        str(entry.get("artifact_key") or ""): entry
        for entry in manifest_entries
        if isinstance(entry, dict) and entry.get("artifact_key")
    }
    checks: list[dict[str, Any]] = []
    for change in planned_changes:
        artifact_key = str(change.get("artifact_key") or "")
        entry = entries_by_key.get(artifact_key)
        current_path = _foldered_canonical_change_current_path(change)
        future_path = _foldered_canonical_change_future_path(change)
        observed_path = str(entry.get("path") or "") if isinstance(entry, dict) else ""
        status = "ready"
        if not artifact_key:
            status = "missing_artifact_key"
        elif not entry:
            status = "manifest_entry_missing"
        elif observed_path != current_path:
            status = "current_canonical_path_mismatch"
        elif not future_path:
            status = "future_canonical_path_missing"
        elif change.get("status") != "ready_for_manifest_dry_run_review":
            status = "manifest_dry_run_change_not_ready"
        checks.append(
            {
                "artifact_key": artifact_key,
                "status": status,
                "current_canonical_path": current_path,
                "future_canonical_path": future_path,
                "observed_manifest_path": observed_path,
            }
        )
    return checks


def _foldered_canonical_promoted_backend_manifest(
    backend_manifest: dict[str, Any],
    planned_changes: list[dict[str, Any]],
    *,
    transaction_id: str,
    applied_at: str,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(backend_manifest, ensure_ascii=False))
    changes_by_key = {
        str(change.get("artifact_key") or ""): change
        for change in planned_changes
        if isinstance(change, dict) and change.get("artifact_key")
    }
    entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        change = changes_by_key.get(str(entry.get("artifact_key") or ""))
        if not change:
            continue
        current_path = _foldered_canonical_change_current_path(change)
        future_path = _foldered_canonical_change_future_path(change)
        entry["path"] = future_path
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        alias = metadata.get("workspace_alias") if isinstance(metadata.get("workspace_alias"), dict) else {}
        alias.update(
            {
                "canonical_path": future_path,
                "future_path": future_path,
                "canonical_path_remains_authoritative": False,
                "legacy_fallback_path": current_path,
                "legacy_fallback_preserved": True,
                "legacy_fallback_tightened": False,
                "physical_apply_transaction_id": transaction_id,
                "physical_apply_applied_at": applied_at,
                "migration_status": "foldered-canonical-physical-apply-applied",
            }
        )
        if change.get("virtual_uri"):
            alias["virtual_uri"] = change.get("virtual_uri")
        metadata["workspace_alias"] = alias
        entry["metadata"] = metadata
    policy = payload.get("mutation_policy") if isinstance(payload.get("mutation_policy"), dict) else {}
    policy.update(
        {
            "foldered_canonical_physical_apply_applied": True,
            "transaction_id": transaction_id,
            "applied_at": applied_at,
            "legacy_fallback_preserved": True,
            "legacy_fallback_tightened": False,
            "files_moved": False,
            "scope": "explicit-review-foldered-canonical-physical-apply-baseline",
        }
    )
    payload["mutation_policy"] = policy
    return payload


def _foldered_canonical_physical_apply_rollback_checkpoint_payload(
    *,
    status: str,
    backend_manifest: dict[str, Any],
    planned_changes: list[dict[str, Any]],
    apply_plan_digest: str,
    transaction_id: str,
    idempotency_key: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-rollback-checkpoint.v1",
        "status": status,
        "created_at": created_at,
        "apply_plan_digest": apply_plan_digest,
        "current_apply_plan_digest": apply_plan_digest,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "captures_backend_manifest_snapshot": True,
        "captures_apply_plan_digest": True,
        "planned_manifest_change_count": len(planned_changes),
        "planned_changes": planned_changes,
        "backend_manifest_snapshot": backend_manifest,
        "side_effect_policy": {
            "writes_checkpoint_artifact": status == "written",
            "mutates_backend_manifest": False,
            "changes_canonical_paths": False,
            "moves_files": False,
        },
    }


def _foldered_canonical_physical_apply_journal_entry(
    *,
    status: str,
    apply_plan_digest: str,
    manifest_dry_run_digest: str,
    preflight_digest: str,
    transaction_id: str,
    idempotency_key: str,
    planned_changes: list[dict[str, Any]],
    approval_gate: dict[str, Any],
    blockers: list[str],
    created_at: str,
) -> dict[str, Any]:
    return {
        "entry_id": hashlib.sha256(f"{transaction_id}\0{idempotency_key}\0{created_at}".encode("utf-8")).hexdigest()[:16],
        "status": status,
        "created_at": created_at,
        "transaction_id": transaction_id,
        "idempotency_key": idempotency_key,
        "apply_plan_digest": apply_plan_digest,
        "manifest_dry_run_apply_plan_digest": manifest_dry_run_digest,
        "physical_apply_preflight_apply_plan_digest": preflight_digest,
        "approval_id": approval_gate.get("approval_id") or "",
        "approval_subject_id": approval_gate.get("expected_subject_id") or "",
        "approval_reviewer": approval_gate.get("reviewer") or "",
        "planned_manifest_change_count": len(planned_changes),
        "artifact_keys": [str(change.get("artifact_key") or "") for change in planned_changes],
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "writes_backend_manifest": status == "applied",
        "writes_rollback_checkpoint": status == "applied",
        "legacy_fallback_tightened": False,
        "files_moved": False,
    }


def _foldered_canonical_physical_apply_journal_payload(
    *,
    existing_journal: dict[str, Any],
    entry: dict[str, Any],
    append_entry: bool,
    updated_at: str,
) -> dict[str, Any]:
    entries = existing_journal.get("entries") if isinstance(existing_journal.get("entries"), list) else []
    valid_entries = [item for item in entries if isinstance(item, dict)]
    if append_entry:
        valid_entries = [*valid_entries, entry]
    return {
        "schema_version": "reverse-deepagent.workspace-foldered-canonical-migration-physical-apply-journal.v1",
        "version": "2026-06-07.foldered-canonical-physical-apply-journal-v1",
        "updated_at": updated_at,
        "entry_count": len(valid_entries),
        "append_only": True,
        "entries": valid_entries,
    }


def _read_foldered_canonical_physical_apply_journal(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "missing", "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - malformed journal cannot be trusted for duplicate evidence.
        return {"schema_version": "malformed", "entries": []}
    return payload if isinstance(payload, dict) else {"schema_version": "invalid", "entries": []}


def _find_foldered_canonical_physical_apply_duplicate(journal: dict[str, Any], *, idempotency_key: str) -> dict[str, Any] | None:
    entries = journal.get("entries") if isinstance(journal.get("entries"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("idempotency_key") == idempotency_key and entry.get("status") == "applied":
            return entry
    return None


def _foldered_canonical_change_current_path(change: dict[str, Any]) -> str:
    return str(
        change.get("current_canonical_path")
        or change.get("expected_current_canonical_path")
        or change.get("current_manifest_path")
        or change.get("old_path")
        or ""
    )


def _foldered_canonical_change_future_path(change: dict[str, Any]) -> str:
    return str(
        change.get("future_canonical_path")
        or change.get("new_path")
        or change.get("target_canonical_path")
        or ""
    )


def _compact_physical_apply_journal_entry(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return {
        "entry_id": entry.get("entry_id") or "",
        "status": entry.get("status") or "",
        "transaction_id": entry.get("transaction_id") or "",
        "idempotency_key": entry.get("idempotency_key") or "",
        "apply_plan_digest": entry.get("apply_plan_digest") or "",
        "artifact_keys": entry.get("artifact_keys") if isinstance(entry.get("artifact_keys"), list) else [],
    }


def _physical_apply_backend_manifest_path(artifact_root: Path, backend_manifest_input: dict[str, Any]) -> Path:
    path = backend_manifest_input.get("path") if isinstance(backend_manifest_input, dict) else None
    if path:
        return Path(str(path))
    return artifact_root / "workspace" / "backend-artifact-manifest.json"


def _foldered_canonical_physical_apply_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "apply_requires_approve_physical_apply_true" in blockers:
        actions.append("rerun_with_approve_physical_apply_true_after_review")
    if "physical_apply_preflight_unavailable_or_malformed" in blockers or "physical_apply_preflight_not_ready" in blockers:
        actions.append("create_or_pass_ready_physical_apply_preflight")
    if "foldered_canonical_migration_manifest_dry_run_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_ready_foldered_canonical_manifest_dry_run")
    if "foldered_canonical_migration_apply_plan_unavailable_or_malformed" in blockers:
        actions.append("create_or_pass_matching_foldered_canonical_migration_apply_plan")
    if "backend_artifact_manifest_unavailable_or_malformed" in blockers or "apply_requires_backend_manifest_artifact_ref_not_inline_json" in blockers:
        actions.append("provide_current_backend_manifest_artifact_ref_for_apply")
    if any(item.startswith("manifest_entry:") for item in blockers):
        actions.append("restore_backend_manifest_to_expected_pre_apply_paths_before_retry")
    if "physical_apply_duplicate_idempotency_key" in blockers:
        actions.append("review_existing_physical_apply_journal_before_retrying")
    if status == "planned":
        actions.append("review_dry_run_then_rerun_apply_with_explicit_approval")
    if status == "applied":
        actions.append("run_post_apply_validation_descriptor_before_tightening_legacy_fallback")
    if "post_apply_validation_required_before_legacy_fallback_tightening" in warnings:
        actions.append("keep_legacy_fallback_until_post_apply_validation_passes")
    return list(dict.fromkeys(actions))


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_delivery_source_audit(delivery_source_audit_json: str | None) -> dict[str, Any] | None:
    if not delivery_source_audit_json:
        return None
    try:
        payload = json.loads(delivery_source_audit_json)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "error": f"delivery_source_audit_json is not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "error": "delivery_source_audit_json must decode to an object",
        }
    return payload


def _summarize_delivery_source_audit_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {
            "schema_version": "missing",
            "status": "missing",
            "artifact_count": 0,
            "source_artifact_ref_count": 0,
            "source_path_count": 0,
            "workspace_resolved_count": 0,
            "external_source_path_count": 0,
            "legacy_source_path_count": 0,
            "future_source_path_count": 0,
            "artifact_root_relative_source_path_count": 0,
            "relative_source_path_count": 0,
            "by_source_input_kind": {},
            "by_source_path_kind": {},
            "malformed": False,
        }
    malformed = payload.get("status") == "malformed"
    return {
        "schema_version": payload.get("schema_version") or "unknown",
        "status": "malformed" if malformed else "observed",
        "artifact_count": _safe_int(payload.get("artifact_count")),
        "source_artifact_ref_count": _safe_int(payload.get("source_artifact_ref_count")),
        "source_path_count": _safe_int(payload.get("source_path_count")),
        "workspace_resolved_count": _safe_int(payload.get("workspace_resolved_count")),
        "external_source_path_count": _safe_int(payload.get("external_source_path_count")),
        "legacy_source_path_count": _safe_int(payload.get("legacy_source_path_count")),
        "future_source_path_count": _safe_int(payload.get("future_source_path_count")),
        "artifact_root_relative_source_path_count": _safe_int(payload.get("artifact_root_relative_source_path_count")),
        "relative_source_path_count": _safe_int(payload.get("relative_source_path_count")),
        "by_source_input_kind": payload.get("by_source_input_kind") if isinstance(payload.get("by_source_input_kind"), dict) else {},
        "by_source_path_kind": payload.get("by_source_path_kind") if isinstance(payload.get("by_source_path_kind"), dict) else {},
        "malformed": malformed,
        "error": payload.get("error") if malformed else "",
    }


def _workspace_migration_next_actions(
    *,
    limited_dual_write_blockers: list[str],
    foldered_blockers: list[str],
    delivery_source_audit_present: bool,
) -> list[str]:
    actions: list[str] = []
    if limited_dual_write_blockers:
        actions.append("resolve_candidate_consumers_before_dual_write_pilot")
    else:
        actions.append("review_limited_dual_write_pilot_for_registered_workspace_artifacts")
    if not delivery_source_audit_present:
        actions.append("run_execute_local_delivery_dry_run_and_collect_delivery_artifact_source_audit")
    if "source_path_usage_observed" in foldered_blockers:
        actions.append("continue_monitoring_source_path_usage_before_foldered_canonical_migration")
    if "external_source_path_usage_observed" in foldered_blockers:
        actions.append("keep_external_filesystem_delivery_sources_as_explicit_boundaries")
    if "partial_consumers_still_present" in foldered_blockers:
        actions.append("do_not_start_foldered_canonical_migration_until_partial_consumers_are_closed_or_explicitly_accepted")
    if not foldered_blockers:
        actions.append("review_narrow_foldered_canonical_migration_pilot")
    return actions


_LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"workspace", "runtime-context", "source", "network", "evidence"})
_MEDIUM_RISK_DUAL_WRITE_PILOT_CATEGORIES = frozenset({"triage", "audit"})


def plan_workspace_dual_write_pilot_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    readiness_report_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 12,
) -> dict[str, Any]:
    """Return a plan-only limited dual-write pilot candidate report."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(default_artifact_root=effective_root)
    requested_keys, requested_error = _parse_artifact_keys_json(artifact_keys_json)
    routes = list(default_workspace_artifact_routes())
    routes_by_key = {route.artifact_key: route for route in routes}
    resolver = WorkspacePathResolver(enable_dual_write=True)
    max_count = max(0, int(max_artifacts))

    explicit_selection = requested_keys is not None
    selected_routes: list[Any] = []
    unknown_keys: list[str] = []
    if explicit_selection:
        for key in requested_keys or []:
            route = routes_by_key.get(key)
            if route is None:
                unknown_keys.append(key)
                continue
            selected_routes.append(route)
        if max_count:
            selected_routes = selected_routes[:max_count]
    else:
        for route in routes:
            if _dual_write_route_risk(route)["risk_level"] != "low":
                continue
            selected_routes.append(route)
            if len(selected_routes) >= max_count:
                break
    if max_count == 0:
        selected_routes = []

    candidate_artifacts: list[dict[str, Any]] = []
    high_risk_requested: list[str] = []
    medium_risk_requested: list[str] = []
    for route in selected_routes:
        risk = _dual_write_route_risk(route)
        if explicit_selection and risk["risk_level"] == "high":
            high_risk_requested.append(route.artifact_key)
        if explicit_selection and risk["risk_level"] == "medium":
            medium_risk_requested.append(route.artifact_key)
        plan = resolver.plan_dual_write(route.artifact_key)
        candidate_artifacts.append(
            {
                "artifact_key": route.artifact_key,
                "legacy_path": route.legacy_path,
                "future_path": route.future_path,
                "virtual_uri": plan.get("virtual_uri"),
                "category": route.category,
                "producer_roles": list(route.producer_roles),
                "risk": risk,
                "dual_write_plan": plan,
                "review_required": True,
            }
        )

    readiness_status = _readiness_limited_dual_write_status(readiness_report)
    blockers: list[str] = []
    if readiness_status != "ready_for_review":
        blockers.append("workspace_migration_readiness_not_ready_for_dual_write_pilot")
    if requested_error:
        blockers.append("artifact_keys_json_malformed")
    if unknown_keys:
        blockers.append("unknown_requested_artifact_keys")
    if high_risk_requested:
        blockers.append("high_risk_requested_artifacts_require_separate_review")
    if not candidate_artifacts:
        blockers.append("no_dual_write_pilot_candidates_selected")
    status = "ready_for_review" if not blockers else "blocked"
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-plan.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "candidate_count": len(candidate_artifacts),
            "unknown_requested_artifact_key_count": len(unknown_keys),
            "high_risk_requested_artifact_count": len(high_risk_requested),
            "medium_risk_requested_artifact_count": len(medium_risk_requested),
            "readiness_limited_dual_write_status": readiness_status,
            "max_artifacts": max_count,
            "explicit_selection": explicit_selection,
            "mobile_full_runtime_chains_deferred": True,
        },
        "selection_policy": {
            "default_risk_level": "low",
            "default_allowed_categories": sorted(_LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES),
            "explicit_keys_may_include_medium_risk": True,
            "high_risk_explicit_keys_block_plan": True,
            "legacy_canonical_path_remains_authoritative": True,
            "physical_migration_enabled": False,
            "actual_dual_write_enabled": False,
        },
        "readiness_summary": _compact_readiness_summary(readiness_report),
        "candidate_artifacts": candidate_artifacts,
        "blocked_artifacts": {
            "unknown_artifact_keys": unknown_keys,
            "high_risk_requested_artifact_keys": high_risk_requested,
            "medium_risk_requested_artifact_keys": medium_risk_requested,
        },
        "blocking_reasons": blockers,
        "recommended_next_actions": _dual_write_pilot_next_actions(
            blockers=blockers,
            medium_risk_requested=medium_risk_requested,
        ),
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def review_workspace_dual_write_pilot_workflow_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    delivery_source_audit_json: str | None = None,
    readiness_report_json: str | None = None,
    artifact_keys_json: str | None = None,
    max_artifacts: int = 12,
    pilot_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Compose readiness, pilot planning, and optional result verification."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    readiness_report = _parse_readiness_report(readiness_report_json)
    if readiness_report is None:
        readiness_report = assess_workspace_migration_readiness_payload(
            default_artifact_root=effective_root,
            delivery_source_audit_json=delivery_source_audit_json,
        )
    pilot_plan, pilot_plan_error = _parse_json_object(pilot_plan_json, field_name="pilot_plan_json")
    if pilot_plan is None:
        if pilot_plan_error:
            pilot_plan = _malformed_dual_write_pilot_plan(
                artifact_root=effective_root,
                error=pilot_plan_error,
                readiness_report=readiness_report,
            )
        else:
            pilot_plan = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=effective_root,
                readiness_report_json=json.dumps(readiness_report, sort_keys=True),
                artifact_keys_json=artifact_keys_json,
                max_artifacts=max_artifacts,
            )

    pilot_result = record_workspace_dual_write_pilot_result_payload(
        default_artifact_root=effective_root,
        pilot_plan_json=json.dumps(pilot_plan, sort_keys=True),
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
        write_result=write_result,
    )
    status = _workspace_dual_write_workflow_status(readiness_report, pilot_plan, pilot_result)
    blocking_reasons = _workspace_dual_write_workflow_blocking_reasons(readiness_report, pilot_plan, pilot_result, status)
    warnings = _workspace_dual_write_workflow_warnings(pilot_result)
    candidate_keys = [str(item.get("artifact_key")) for item in pilot_plan.get("candidate_artifacts", []) if item.get("artifact_key")]
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-workflow.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "summary": {
            "readiness_status": readiness_report.get("status") or "unknown",
            "readiness_limited_dual_write_status": _readiness_limited_dual_write_status(readiness_report),
            "pilot_plan_status": pilot_plan.get("status") or "unknown",
            "pilot_result_status": pilot_result.get("status") or "unknown",
            "selected_artifact_count": len(candidate_keys),
            "blocking_reason_count": len(blocking_reasons),
            "warning_count": len(warnings),
            "review_required": True,
            "write_result_requested": bool(write_result),
            "mobile_full_runtime_chains_deferred": True,
        },
        "readiness_report": readiness_report,
        "pilot_plan": pilot_plan,
        "pilot_result": pilot_result,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_next_actions": _workspace_dual_write_workflow_next_actions(status, pilot_result),
        "review_workflow": _workspace_dual_write_review_workflow(
            candidate_keys=candidate_keys,
            result_status=str(pilot_result.get("status") or "unknown"),
            workflow_status=status,
            write_result=write_result,
        ),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "runs_pipeline": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def _malformed_dual_write_pilot_plan(
    *,
    artifact_root: Path,
    error: str,
    readiness_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-plan.v1",
        "status": "blocked",
        "artifact_root": str(artifact_root),
        "summary": {
            "candidate_count": 0,
            "readiness_limited_dual_write_status": _readiness_limited_dual_write_status(readiness_report),
            "mobile_full_runtime_chains_deferred": True,
        },
        "readiness_summary": _compact_readiness_summary(readiness_report),
        "candidate_artifacts": [],
        "blocking_reasons": ["pilot_plan_json_malformed"],
        "error": error,
        "recommended_next_actions": ["fix_pilot_plan_json_or_omit_it_to_use_default_plan"],
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }


def record_workspace_dual_write_pilot_result_payload(
    *,
    default_artifact_root: str | Path,
    artifact_root: str | None = None,
    pilot_plan_json: str | None = None,
    workspace_dual_write_plan_json: str | None = None,
    workspace_dual_write_plan_artifact_ref: str | None = "workspace_dual_write_plan",
    write_result: bool = False,
) -> dict[str, Any]:
    """Inspect an explicit dual-write run and optionally record a pilot result artifact."""

    root = Path(default_artifact_root)
    effective_root = Path(artifact_root) if artifact_root else root
    pilot_plan, pilot_plan_error = _parse_json_object(pilot_plan_json, field_name="pilot_plan_json")
    if pilot_plan is None and not pilot_plan_error:
        pilot_plan = plan_workspace_dual_write_pilot_payload(default_artifact_root=effective_root)
    observed_plan, observed_plan_error, observed_input = _load_observed_dual_write_plan(
        default_artifact_root=effective_root,
        workspace_dual_write_plan_json=workspace_dual_write_plan_json,
        workspace_dual_write_plan_artifact_ref=workspace_dual_write_plan_artifact_ref,
    )
    planned_candidates = _planned_dual_write_candidates(pilot_plan if isinstance(pilot_plan, dict) else {})
    observed_records = _observed_dual_write_records(observed_plan if isinstance(observed_plan, dict) else {})
    observed_by_key = {str(record.get("artifact_key") or ""): record for record in observed_records if record.get("artifact_key")}

    candidate_results: list[dict[str, Any]] = []
    verified_count = 0
    missing_legacy_count = 0
    missing_future_count = 0
    digest_mismatch_count = 0
    not_observed_count = 0
    for candidate in planned_candidates:
        result = _dual_write_candidate_result(effective_root, candidate, observed_by_key.get(candidate["artifact_key"]))
        candidate_results.append(result)
        status = result["status"]
        if status == "verified_dual_written":
            verified_count += 1
        if status == "missing_legacy":
            missing_legacy_count += 1
        if status == "missing_future":
            missing_future_count += 1
        if status == "digest_mismatch":
            digest_mismatch_count += 1
        if status == "not_observed":
            not_observed_count += 1

    planned_keys = {item["artifact_key"] for item in planned_candidates}
    out_of_scope_observed: list[dict[str, Any]] = []
    high_risk_observed: list[dict[str, Any]] = []
    medium_risk_observed: list[dict[str, Any]] = []
    routes_by_key = {route.artifact_key: route for route in default_workspace_artifact_routes()}
    for record in observed_records:
        key = str(record.get("artifact_key") or "")
        if not key or key == "workspace_dual_write_pilot_result" or not record.get("dual_write_enabled"):
            continue
        route = routes_by_key.get(key)
        risk = _dual_write_route_risk(route) if route is not None else {"risk_level": "unknown", "rationale": "observed artifact is not registered", "category": "unknown", "producer_roles": []}
        summary = {
            "artifact_key": key,
            "legacy_path": record.get("canonical_path") or record.get("legacy_path") or "",
            "future_path": record.get("future_path") or "",
            "write_paths": list(record.get("write_paths") or []),
            "dual_write_enabled": bool(record.get("dual_write_enabled")),
            "risk": risk,
        }
        if key not in planned_keys:
            out_of_scope_observed.append(summary)
        if risk.get("risk_level") == "high":
            high_risk_observed.append(summary)
        if risk.get("risk_level") == "medium":
            medium_risk_observed.append(summary)

    blocking_reasons: list[str] = []
    warnings: list[str] = []
    if pilot_plan_error:
        blocking_reasons.append("pilot_plan_json_malformed")
    if observed_plan_error:
        blocking_reasons.append("workspace_dual_write_plan_unavailable_or_malformed")
    if not observed_records:
        blocking_reasons.append("workspace_dual_write_plan_not_observed")
    if not planned_candidates:
        blocking_reasons.append("pilot_plan_has_no_candidates")
    if missing_legacy_count:
        blocking_reasons.append("candidate_legacy_files_missing")
    if missing_future_count:
        blocking_reasons.append("candidate_future_files_missing")
    if digest_mismatch_count:
        blocking_reasons.append("candidate_digest_mismatch")
    if not_observed_count:
        warnings.append("some_planned_candidates_not_seen_in_workspace_dual_write_plan")
    if out_of_scope_observed:
        warnings.append("observed_dual_write_records_outside_pilot_plan")
    if high_risk_observed:
        warnings.append("high_risk_artifacts_observed_in_dual_write_output")
    if medium_risk_observed:
        warnings.append("medium_risk_artifacts_observed_in_dual_write_output")

    if observed_plan_error or not observed_records:
        status = "not_run"
    elif blocking_reasons:
        status = "blocked"
    elif verified_count == len(planned_candidates) and not out_of_scope_observed and not high_risk_observed:
        status = "verified"
    else:
        status = "partial"

    result_artifact = _workspace_pilot_result_artifact_metadata(effective_root, written=False)
    payload: dict[str, Any] = {
        "schema_version": "reverse-deepagent.workspace-dual-write-pilot-result.v1",
        "status": status,
        "artifact_root": str(effective_root),
        "result_artifact": result_artifact,
        "summary": {
            "planned_candidate_count": len(planned_candidates),
            "observed_write_record_count": len(observed_records),
            "verified_candidate_count": verified_count,
            "missing_legacy_count": missing_legacy_count,
            "missing_future_count": missing_future_count,
            "digest_mismatch_count": digest_mismatch_count,
            "not_observed_candidate_count": not_observed_count,
            "out_of_scope_observed_count": len(out_of_scope_observed),
            "high_risk_observed_count": len(high_risk_observed),
            "medium_risk_observed_count": len(medium_risk_observed),
            "legacy_canonical_path_remains_authoritative": True,
            "foldered_canonical_migration_enabled": False,
            "mobile_full_runtime_chains_deferred": True,
        },
        "pilot_plan_summary": _compact_pilot_plan_summary(pilot_plan if isinstance(pilot_plan, dict) else {}),
        "observed_dual_write_plan_input": observed_input,
        "candidate_results": candidate_results,
        "out_of_scope_observed_artifacts": out_of_scope_observed,
        "high_risk_observed_artifacts": high_risk_observed,
        "medium_risk_observed_artifacts": medium_risk_observed,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "recommended_next_actions": _dual_write_pilot_result_next_actions(status, blocking_reasons, warnings),
        "side_effect_policy": {
            "read_only": not bool(write_result),
            "files_inspected": True,
            "artifacts_written": bool(write_result),
            "creates_directories": bool(write_result),
            "enables_dual_write": False,
            "migrates_paths": False,
            "changes_canonical_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
            "touches_mobile_full_runtime_chains": False,
        },
    }
    if write_result:
        result_path = effective_root / "workspace" / "workspace-dual-write-pilot-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        payload["result_artifact"] = _workspace_pilot_result_artifact_metadata(effective_root, written=True)
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _load_observed_dual_write_plan(
    *,
    default_artifact_root: Path,
    workspace_dual_write_plan_json: str | None,
    workspace_dual_write_plan_artifact_ref: str | None,
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    if workspace_dual_write_plan_json:
        payload, error = _parse_json_object(workspace_dual_write_plan_json, field_name="workspace_dual_write_plan_json")
        return payload, error, {"kind": "json", "error": error}
    if not workspace_dual_write_plan_artifact_ref:
        return None, "workspace_dual_write_plan_artifact_ref is empty", {"kind": "none", "error": "workspace_dual_write_plan_artifact_ref is empty"}
    try:
        payload, read_diagnostics = load_workspace_artifact_json_object(
            artifact_ref=workspace_dual_write_plan_artifact_ref,
            default_artifact_root=default_artifact_root,
            field_name="workspace_dual_write_plan_artifact_ref",
        )
    except ValueError as exc:
        return None, str(exc), {
            "kind": "artifact_ref",
            "artifact_ref": workspace_dual_write_plan_artifact_ref,
            "status": "error",
            "error": str(exc),
        }
    return payload, "", {
        "kind": "artifact_ref",
        "artifact_ref": workspace_dual_write_plan_artifact_ref,
        "status": "found",
        "read": summarize_workspace_artifact_read(read_diagnostics),
    }


def _parse_json_object(payload_json: str | None, *, field_name: str) -> tuple[dict[str, Any] | None, str]:
    if not payload_json:
        return None, ""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return None, f"{field_name} is not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{field_name} must decode to an object"
    return payload, ""


def _planned_dual_write_candidates(pilot_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in pilot_plan.get("candidate_artifacts") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("artifact_key") or "")
        if not key:
            continue
        legacy_path = str(item.get("legacy_path") or item.get("canonical_path") or "")
        future_path = str(item.get("future_path") or "")
        plan = item.get("dual_write_plan") if isinstance(item.get("dual_write_plan"), dict) else {}
        if not legacy_path:
            legacy_path = str(plan.get("canonical_path") or "")
        if not future_path:
            future_path = str(plan.get("future_path") or "")
        candidates.append({
            "artifact_key": key,
            "legacy_path": legacy_path,
            "future_path": future_path,
            "risk": item.get("risk") if isinstance(item.get("risk"), dict) else {},
        })
    return candidates


def _observed_dual_write_records(observed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        observed_plan.get("write_records")
        or observed_plan.get("workspace_write_records")
        or observed_plan.get("records")
        or observed_plan.get("artifacts")
        or []
    )
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _dual_write_candidate_result(artifact_root: Path, candidate: dict[str, Any], observed_record: dict[str, Any] | None) -> dict[str, Any]:
    legacy_path = str(candidate.get("legacy_path") or "")
    future_path = str(candidate.get("future_path") or "")
    legacy_file = _artifact_ref_to_filesystem_path(artifact_root, legacy_path) if legacy_path else artifact_root / ""
    future_file = _artifact_ref_to_filesystem_path(artifact_root, future_path) if future_path else artifact_root / ""
    legacy_stat = _file_digest_stat(legacy_file) if legacy_path else _missing_file_stat(legacy_file)
    future_stat = _file_digest_stat(future_file) if future_path else _missing_file_stat(future_file)
    observed = observed_record is not None
    digest_match = bool(legacy_stat.get("exists") and future_stat.get("exists") and legacy_stat.get("sha256") == future_stat.get("sha256"))
    if not observed:
        status = "not_observed"
    elif not legacy_stat["exists"]:
        status = "missing_legacy"
    elif not future_stat["exists"]:
        status = "missing_future"
    elif not digest_match:
        status = "digest_mismatch"
    else:
        status = "verified_dual_written"
    return {
        "artifact_key": candidate["artifact_key"],
        "status": status,
        "observed_in_workspace_dual_write_plan": observed,
        "legacy_path": legacy_path,
        "future_path": future_path,
        "legacy_file": legacy_stat,
        "future_file": future_stat,
        "digest_match": digest_match,
        "canonical_path_remains_authoritative": True,
        "observed_record": _compact_observed_write_record(observed_record),
        "risk": candidate.get("risk") or {},
    }


def _file_digest_stat(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return _missing_file_stat(path)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return {"path": str(path), "exists": True, "size_bytes": size, "sha256": digest.hexdigest()}


def _missing_file_stat(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": False, "size_bytes": 0, "sha256": ""}


def _compact_observed_write_record(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    return {
        "artifact_key": record.get("artifact_key") or "",
        "canonical_path": record.get("canonical_path") or record.get("legacy_path") or "",
        "future_path": record.get("future_path") or "",
        "write_paths": list(record.get("write_paths") or []),
        "migration_status": record.get("migration_status") or "",
        "canonical_path_remains_authoritative": bool(record.get("canonical_path_remains_authoritative", True)),
    }


def _compact_pilot_plan_summary(pilot_plan: dict[str, Any]) -> dict[str, Any]:
    summary = pilot_plan.get("summary") if isinstance(pilot_plan.get("summary"), dict) else {}
    return {
        "schema_version": pilot_plan.get("schema_version") or "",
        "status": pilot_plan.get("status") or "",
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "explicit_selection": bool(summary.get("explicit_selection")),
        "readiness_limited_dual_write_status": summary.get("readiness_limited_dual_write_status") or "",
        "legacy_canonical_path_remains_authoritative": bool((pilot_plan.get("selection_policy") or {}).get("legacy_canonical_path_remains_authoritative", True)) if isinstance(pilot_plan.get("selection_policy"), dict) else True,
    }


def _workspace_pilot_result_artifact_metadata(artifact_root: Path, *, written: bool) -> dict[str, Any]:
    return {
        "artifact_key": "workspace_dual_write_pilot_result",
        "legacy_path": "workspace/workspace-dual-write-pilot-result.json",
        "future_path": "/workspace/delivery/workspace-dual-write-pilot-result.json",
        "path": str(artifact_root / "workspace" / "workspace-dual-write-pilot-result.json"),
        "written": written,
        "canonical_path_remains_authoritative": True,
    }


def _dual_write_pilot_result_next_actions(status: str, blockers: list[str], warnings: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_dual_write_plan_unavailable_or_malformed" in blockers or "workspace_dual_write_plan_not_observed" in blockers:
        actions.append("run_pipeline_with_enable_workspace_dual_write_and_capture_workspace_dual_write_plan")
    if "pilot_plan_json_malformed" in blockers:
        actions.append("fix_pilot_plan_json_or_omit_it_to_use_default_plan")
    if "candidate_legacy_files_missing" in blockers or "candidate_future_files_missing" in blockers:
        actions.append("inspect_dual_write_output_paths_and_rerun_limited_pilot")
    if "candidate_digest_mismatch" in blockers:
        actions.append("compare_legacy_and_future_artifacts_before_any_migration")
    if "observed_dual_write_records_outside_pilot_plan" in warnings:
        actions.append("review_out_of_scope_observed_dual_writes_before_expanding_pilot")
    if "high_risk_artifacts_observed_in_dual_write_output" in warnings:
        actions.append("split_high_risk_artifacts_into_separate_manual_review")
    if status == "verified":
        actions.append("record_verified_pilot_result_then_review_next_low_risk_dual_write_scope")
    if not actions:
        actions.append("review_pilot_result_before_foldered_canonical_migration")
    return actions


def _workspace_dual_write_workflow_status(
    readiness_report: dict[str, Any],
    pilot_plan: dict[str, Any],
    pilot_result: dict[str, Any],
) -> str:
    if _readiness_limited_dual_write_status(readiness_report) != "ready_for_review":
        return "blocked"
    if pilot_plan.get("status") == "blocked":
        return "blocked"
    result_status = str(pilot_result.get("status") or "unknown")
    if result_status == "verified":
        return "verified"
    if result_status == "partial":
        return "partial"
    if result_status == "blocked":
        return "blocked"
    if result_status == "not_run":
        return "ready_for_review"
    return "ready_for_review"


def _workspace_dual_write_workflow_blocking_reasons(
    readiness_report: dict[str, Any],
    pilot_plan: dict[str, Any],
    pilot_result: dict[str, Any],
    status: str,
) -> list[str]:
    reasons: list[str] = []
    if _readiness_limited_dual_write_status(readiness_report) != "ready_for_review":
        reasons.append("workspace_migration_readiness_not_ready_for_dual_write_pilot")
    for reason in pilot_plan.get("blocking_reasons") or []:
        reasons.append(f"pilot_plan:{reason}")
    if status in {"blocked", "partial"}:
        for reason in pilot_result.get("blocking_reasons") or []:
            reasons.append(f"pilot_result:{reason}")
    return list(dict.fromkeys(reasons))


def _workspace_dual_write_workflow_warnings(pilot_result: dict[str, Any]) -> list[str]:
    return [f"pilot_result:{item}" for item in pilot_result.get("warnings") or []]


def _workspace_dual_write_workflow_next_actions(status: str, pilot_result: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if status == "ready_for_review":
        actions.append("review_pilot_plan_then_run_explicit_scoped_dual_write_pipeline")
    if status in {"verified", "partial"}:
        actions.append("review_pilot_result_before_expanding_dual_write_scope")
    if status == "verified":
        actions.append("consider_next_low_risk_artifact_scope_after_review")
    if status == "blocked":
        actions.append("resolve_workflow_blockers_before_running_dual_write_pilot")
    for action in pilot_result.get("recommended_next_actions") or []:
        if action not in actions:
            actions.append(action)
    return actions


def _workspace_dual_write_review_workflow(
    *,
    candidate_keys: list[str],
    result_status: str,
    workflow_status: str,
    write_result: bool,
) -> dict[str, Any]:
    key_arg = ",".join(candidate_keys)
    if workflow_status == "blocked":
        commands = [
            {
                "step": "resolve_workflow_blockers",
                "description": "Resolve readiness, pilot plan, or verification blockers before running a scoped dual-write pipeline.",
                "requires_review": True,
                "runs_inside_this_tool": False,
            }
        ]
    else:
        commands = [
            {
                "step": "run_explicit_scoped_dual_write_pipeline",
                "description": "Run the normal pipeline separately with reviewed low-risk artifact keys only.",
                "flags": [
                    "--enable-workspace-dual-write",
                    "--workspace-dual-write-artifact-keys",
                    key_arg,
                ],
                "requires_review": True,
                "runs_inside_this_tool": False,
            },
            {
                "step": "verify_observed_dual_write_output",
                "description": "Call this workflow again after the pipeline writes workspace/workspace-dual-write-plan.json, or pass workspace_dual_write_plan_json directly.",
                "tool": "review_workspace_dual_write_pilot_workflow",
                "suggested_arguments": {
                    "artifact_keys_json": json.dumps(candidate_keys),
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": False,
                },
                "requires_review": True,
            },
            {
                "step": "record_verified_pilot_result",
                "description": "Only after reviewing the verification payload, call with write_result=true to write the audit artifact.",
                "tool": "review_workspace_dual_write_pilot_workflow",
                "suggested_arguments": {
                    "artifact_keys_json": json.dumps(candidate_keys),
                    "workspace_dual_write_plan_artifact_ref": "workspace_dual_write_plan",
                    "write_result": True,
                },
                "requires_review": True,
                "already_requested": bool(write_result),
            },
        ]
    return {
        "requires_explicit_pipeline_run": workflow_status != "blocked",
        "requires_review_before_expansion": True,
        "requires_result_review_before_writing_audit": True,
        "workflow_status": workflow_status,
        "result_verification_status": result_status,
        "selected_artifact_keys": candidate_keys,
        "recommended_commands": commands,
        "does_not_run_pipeline": True,
        "does_not_enable_dual_write": True,
        "does_not_migrate_paths": True,
        "legacy_canonical_path_remains_authoritative": True,
    }


def _parse_readiness_report(readiness_report_json: str | None) -> dict[str, Any] | None:
    if not readiness_report_json:
        return None
    try:
        payload = json.loads(readiness_report_json)
    except json.JSONDecodeError as exc:
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "summary": {"limited_dual_write_pilot_status": "blocked"},
            "error": f"readiness_report_json is not valid JSON: {exc}",
        }
    if not isinstance(payload, dict):
        return {
            "schema_version": "invalid-json",
            "status": "malformed",
            "summary": {"limited_dual_write_pilot_status": "blocked"},
            "error": "readiness_report_json must decode to an object",
        }
    return payload


def _parse_artifact_keys_json(artifact_keys_json: str | None) -> tuple[list[str] | None, str]:
    if artifact_keys_json is None:
        return None, ""
    try:
        payload = json.loads(artifact_keys_json)
    except json.JSONDecodeError as exc:
        return [], f"artifact_keys_json is not valid JSON: {exc}"
    if not isinstance(payload, list) or not all(isinstance(item, str) and item for item in payload):
        return [], "artifact_keys_json must decode to a list of non-empty strings"
    return list(dict.fromkeys(payload)), ""


def _dual_write_route_risk(route: Any) -> dict[str, Any]:
    if route.artifact_key == "workspace_dual_write_plan" or route.category in _MEDIUM_RISK_DUAL_WRITE_PILOT_CATEGORIES:
        risk_level = "medium"
        rationale = "review or audit artifact; explicit selection is allowed but should receive extra reviewer attention"
    elif _is_high_risk_dual_write_route(route):
        risk_level = "high"
        rationale = "delivery, rebuild, hook, trace, export, or transaction artifact; keep out of default pilot"
    elif route.category in _LOW_RISK_DUAL_WRITE_PILOT_CATEGORIES:
        risk_level = "low"
        rationale = "metadata-or-evidence-style workspace artifact suitable for limited review pilot"
    else:
        risk_level = "high"
        rationale = "unclassified workspace artifact; keep out of default pilot until reviewed"
    return {
        "risk_level": risk_level,
        "rationale": rationale,
        "category": route.category,
        "producer_roles": list(route.producer_roles),
    }


def _is_high_risk_dual_write_route(route: Any) -> bool:
    high_risk_categories = {"export", "rebuild", "hook-timeline", "trace"}
    high_risk_prefixes = (
        "workspace_backend_",
        "workspace_delivery_",
        "workspace_external_",
        "workspace_final_delivery_",
    )
    if route.category in high_risk_categories:
        return True
    if route.artifact_key == "workspace_final":
        return True
    return any(str(route.artifact_key).startswith(prefix) for prefix in high_risk_prefixes)


def _readiness_limited_dual_write_status(readiness_report: dict[str, Any]) -> str:
    summary = readiness_report.get("summary") if isinstance(readiness_report.get("summary"), dict) else {}
    return str(summary.get("limited_dual_write_pilot_status") or "blocked")


def _compact_readiness_summary(readiness_report: dict[str, Any]) -> dict[str, Any]:
    summary = readiness_report.get("summary") if isinstance(readiness_report.get("summary"), dict) else {}
    return {
        "schema_version": readiness_report.get("schema_version") or "",
        "status": readiness_report.get("status") or "",
        "limited_dual_write_pilot_status": summary.get("limited_dual_write_pilot_status") or "blocked",
        "foldered_canonical_migration_status": summary.get("foldered_canonical_migration_status") or "blocked",
        "partial_count": _safe_int(summary.get("partial_count")),
        "candidate_count": _safe_int(summary.get("candidate_count")),
        "delivery_source_audit_observed": bool(summary.get("delivery_source_audit_observed")),
    }


def _dual_write_pilot_next_actions(*, blockers: list[str], medium_risk_requested: list[str]) -> list[str]:
    actions: list[str] = []
    if "workspace_migration_readiness_not_ready_for_dual_write_pilot" in blockers:
        actions.append("resolve_workspace_migration_readiness_blockers_before_pilot")
    if "artifact_keys_json_malformed" in blockers:
        actions.append("fix_artifact_keys_json_and_retry_plan")
    if "unknown_requested_artifact_keys" in blockers:
        actions.append("remove_or_register_unknown_artifact_keys")
    if "high_risk_requested_artifacts_require_separate_review" in blockers:
        actions.append("split_high_risk_delivery_or_transaction_artifacts_into_separate_manual_review")
    if "no_dual_write_pilot_candidates_selected" in blockers:
        actions.append("select_low_risk_workspace_artifact_keys_for_pilot")
    if medium_risk_requested and not blockers:
        actions.append("review_medium_risk_audit_or_triage_artifacts_before_pilot")
    if not blockers:
        actions.append("review_plan_then_run_pipeline_with_enable_workspace_dual_write_for_selected_scope_only")
    return actions


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
            current_support=(
                "source_artifact_ref / artifact_ref are resolver-ready; source_path remains supported with "
                "delivery_source_audit classification for explicit filesystem delivery and backward compatibility"
            ),
            next_action="continue-source_path-usage-monitoring-before-tightening",
            rationale=(
                "Delivery artifact source normalization is resolver-ready and now emits source compatibility metrics, "
                "but source_path is intentionally retained for non-workspace files and backward compatibility."
            ),
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
