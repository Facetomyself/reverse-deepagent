from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.tools.artifact_tools import read_workspace_artifact_payload, summarize_workspace_artifact_read
from reverse_deepagent.workspace_contract import WorkspacePathResolver

from reverse_deepagent.delivery import (
    DeliveryArtifact,
    DeliveryExecutionMode,
    DeliveryExecutorConfig,
    DeliveryRecoveryExecutorConfig,
    DeliveryRollbackExecutor,
    DeliveryRollbackExecutorConfig,
    DeliveryRollbackStateArtifactWriter,
    DeliveryResumePlanner,
    DeliveryResumePlannerConfig,
    DeliveryResumeRunner,
    DeliveryResumeRunnerConfig,
    DeliveryResumeWorkflowScheduler,
    DeliveryResumeWorkflowSchedulerConfig,
    DeliveryRollbackStateWriterConfig,
    DeliveryTransactionLockProviderConfig,
    DeliveryTransactionRecoveryExecutor,
    DeliveryTransactionTransitionExecutor,
    DeliveryTransitionExecutorConfig,
    LocalDeliveryExecutor,
    build_default_delivery_transaction_lock_provider_registry,
)


DeliveryTool = Callable[..., dict[str, Any]]


def make_local_delivery_executor_tool(
    default_delivery_root: str | Path,
    default_artifact_root: str | Path | None = None,
) -> DeliveryTool:
    """Create a tool wrapper for side-effect-safe local delivery execution."""

    root = Path(default_delivery_root)
    artifact_root_default = Path(default_artifact_root) if default_artifact_root is not None else root.parent

    def execute_local_delivery(
        artifacts_json: str,
        transaction_id: str,
        delivery_root: str | None = None,
        artifact_root: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        overwrite: bool = False,
        commit_manifest_revision: bool = False,
        commit_backend_manifest_mutation: bool = False,
        backend_manifest_path: str | None = None,
        preflight_backend_manifest_in_place_mutation: bool = False,
        expected_backend_manifest_digest_sha256: str | None = None,
        approve_backend_manifest_in_place_mutation: bool = False,
        preflight_backend_manifest_recovery: bool = False,
        expected_recovery_transaction_id: str | None = None,
        apply_backend_manifest_recovery: bool = False,
        commit_cross_run_transaction: bool = False,
        expected_commit_transaction_id: str | None = None,
        request_external_delivery: bool = False,
        external_delivery_provider_id: str = "review-only",
        external_delivery_provider_config_json: str | None = None,
        external_delivery_idempotency_key: str | None = None,
        allow_duplicate_external_delivery: bool = False,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        release_transaction_lock: bool = False,
        approve_transaction_lock_release: bool = False,
        expected_transaction_lock_owner: str | None = None,
        expected_transaction_lock_transaction_id: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or apply local filesystem delivery for reviewed artifact paths."""

        raw_artifacts = json.loads(artifacts_json)
        if not isinstance(raw_artifacts, list):
            raise ValueError("artifacts_json must decode to a list")
        effective_artifact_root = Path(artifact_root) if artifact_root else artifact_root_default
        artifacts = [_artifact_from_payload(item, artifact_root=effective_artifact_root) for item in raw_artifacts]
        delivery_artifact_source_audit = _summarize_delivery_source_audit(artifacts)
        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        external_delivery_provider_config = (
            json.loads(external_delivery_provider_config_json) if external_delivery_provider_config_json else {}
        )
        if not isinstance(external_delivery_provider_config, dict):
            raise ValueError("external_delivery_provider_config_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryExecutorConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            mode=DeliveryExecutionMode(mode),
            overwrite=overwrite,
            commit_manifest_revision=commit_manifest_revision,
            commit_backend_manifest_mutation=commit_backend_manifest_mutation,
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            preflight_backend_manifest_in_place_mutation=preflight_backend_manifest_in_place_mutation,
            expected_backend_manifest_digest_sha256=expected_backend_manifest_digest_sha256,
            approve_backend_manifest_in_place_mutation=approve_backend_manifest_in_place_mutation,
            preflight_backend_manifest_recovery=preflight_backend_manifest_recovery,
            expected_recovery_transaction_id=expected_recovery_transaction_id,
            apply_backend_manifest_recovery=apply_backend_manifest_recovery,
            commit_cross_run_transaction=commit_cross_run_transaction,
            expected_commit_transaction_id=expected_commit_transaction_id,
            request_external_delivery=request_external_delivery,
            external_delivery_provider_id=external_delivery_provider_id,
            external_delivery_provider_config=external_delivery_provider_config,
            external_delivery_idempotency_key=external_delivery_idempotency_key,
            allow_duplicate_external_delivery=allow_duplicate_external_delivery,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            release_transaction_lock=release_transaction_lock,
            approve_transaction_lock_release=approve_transaction_lock_release,
            expected_transaction_lock_owner=expected_transaction_lock_owner,
            expected_transaction_lock_transaction_id=expected_transaction_lock_transaction_id,
            metadata=metadata,
        )
        result = LocalDeliveryExecutor(config).execute(artifacts).to_dict()
        result["delivery_artifact_source_audit"] = delivery_artifact_source_audit
        return result

    execute_local_delivery.__name__ = "execute_local_delivery"
    execute_local_delivery.__doc__ = (
        "Plan or apply local filesystem delivery. artifacts_json is a JSON list with source_path or source_artifact_ref/artifact_ref, optional artifact_key, "
        "destination_name, required, and metadata. artifact refs resolve through WorkspacePathResolver before planning; mode defaults to dry-run; apply copies files locally and writes receipt/journal. "
        "commit_manifest_revision can additionally write a local delivery-manifest-revision.json. "
        "commit_backend_manifest_mutation writes a local mutation record plus patched backend manifest copy without mutating the source manifest in place. "
        "preflight_backend_manifest_in_place_mutation writes a preflight record that checks whether a future in-place manifest mutation would be safe, without mutating the source manifest. "
        "approve_backend_manifest_in_place_mutation explicitly applies that in-place mutation only after the patch and preflight pass and an expected source digest is provided. "
        "preflight_backend_manifest_recovery inspects a previous local delivery journal, rollback checkpoint, mutation record, and current source manifest without restoring or committing anything. "
        "apply_backend_manifest_recovery restores the source backend manifest from the local rollback checkpoint only when recovery preflight and digest checks pass. "
        "commit_cross_run_transaction writes a local backend-artifact-manifest-transaction-commit.json record and updates the prior journal only when recovery preflight and digest checks pass. "
        "request_external_delivery invokes the configured ExternalDeliveryProvider contract; the built-in review-only provider writes a blocked handoff record and never publishes externally, "
        "local-archive/filesystem-release can copy delivered files into a configured local archive root after apply, "
        "webhook/http-webhook can POST a redacted JSON delivery package to an explicit webhook_url after apply, "
        "and presigned-object/object-storage can PUT a redacted JSON delivery package to an explicit presigned_url after apply. "
        "external_delivery_provider_config_json passes provider-specific JSON options such as {\"archive_root\": \"...\"}, {\"webhook_url\": \"...\", \"headers\": {...}}, or {\"presigned_url\": \"...\", \"object_name\": \"release.json\", \"headers\": {...}}; raw config values are not exported in package metadata. "
        "external_delivery_idempotency_key defaults to the transaction id; duplicate external delivery is blocked by default unless allow_duplicate_external_delivery is explicitly true. "
        "require_transaction_lock enables a local delivery-transaction-lock.json gate for apply-mode side effects; transaction_lock_owner, transaction_lock_lease_seconds, and expected_resume_token control the local lease / resume preflight baseline. "
        "expected_transaction_lock_fencing_token additionally requires delivery-distributed-transaction-lock.json to contain the matching fencing token before downstream side effects proceed. "
        "release_transaction_lock creates a delivery-transaction-lock-release.json review record; apply mode removes the local lock only when approve_transaction_lock_release=true and optional expected owner / transaction id / resume token checks pass."
    )
    return execute_local_delivery


def make_delivery_resume_planner_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for durable delivery resume planning."""

    root = Path(default_delivery_root)

    def plan_delivery_resume(
        delivery_root: str | None = None,
        transaction_id: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        write_resume_plan: bool = True,
        resume_plan_name: str = "delivery-resume-plan.json",
        expected_resume_token: str | None = None,
        transaction_lock_owner: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan a durable delivery transaction resume from existing artifacts."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryResumePlannerConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            mode=DeliveryExecutionMode(mode),
            write_resume_plan=write_resume_plan,
            resume_plan_name=resume_plan_name,
            expected_resume_token=expected_resume_token,
            transaction_lock_owner=transaction_lock_owner,
            metadata=metadata,
        )
        return DeliveryResumePlanner(config).execute().to_dict()

    plan_delivery_resume.__name__ = "plan_delivery_resume"
    plan_delivery_resume.__doc__ = (
        "Plan a durable delivery resume path from existing transaction artifacts. "
        "mode defaults to dry-run and is read-only. apply mode writes only delivery-resume-plan.json when checks pass; "
        "it does not execute transitions, restore manifests, commit transactions, publish external delivery, acquire/release locks, or run physical rollback. "
        "expected_resume_token and transaction_lock_owner are used only to decide whether an existing local delivery-transaction-lock.json allows a reviewed resume plan."
    )
    return plan_delivery_resume


def make_delivery_resume_runner_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for reviewed durable delivery resume execution."""

    root = Path(default_delivery_root)

    def execute_delivery_resume(
        delivery_root: str | None = None,
        transaction_id: str | None = None,
        action: str = "plan_only",
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        backend_manifest_path: str | None = None,
        expected_transaction_id: str | None = None,
        approval_ledger_path: str | None = None,
        approval_subject_id: str | None = None,
        approval_action: str | None = None,
        approval_decision: str = "approved",
        approval_id: str | None = None,
        require_review_approval: bool = True,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or execute one review-approved durable delivery resume transition."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryResumeRunnerConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            action=action,
            mode=DeliveryExecutionMode(mode),
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            expected_transaction_id=expected_transaction_id,
            approval_ledger_path=Path(approval_ledger_path) if approval_ledger_path else None,
            approval_subject_id=approval_subject_id,
            approval_action=approval_action,
            approval_decision=approval_decision,
            approval_id=approval_id,
            require_review_approval=require_review_approval,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            metadata=metadata,
        )
        return DeliveryResumeRunner(config).execute().to_dict()

    execute_delivery_resume.__name__ = "execute_delivery_resume"
    execute_delivery_resume.__doc__ = (
        "Plan or execute one review-approved durable delivery resume transition. "
        "mode defaults to dry-run. apply mode requires a matching review-approval-ledger entry unless require_review_approval is false, "
        "then delegates to the existing transition executor for preflight_backend_manifest_recovery, apply_backend_manifest_recovery, or commit_cross_run_transaction. "
        "It writes delivery-resume-execution.json only after explicit apply execution and never starts new delivery, publishes external delivery, or executes physical rollback."
    )
    return execute_delivery_resume


def make_delivery_transaction_lock_provider_tool(default_lock_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for pluggable delivery transaction lock providers."""

    root = Path(default_lock_root)

    def manage_delivery_transaction_lock_provider(
        transaction_id: str,
        owner: str,
        action: str = "inspect_lock",
        lock_root: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        lease_seconds: int = 900,
        expected_owner: str | None = None,
        expected_fencing_token: str | None = None,
        approve_release: bool = False,
        allow_stale_takeover: bool = False,
        provider_id: str = "local-file-lock",
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Inspect, acquire, renew, or release a delivery transaction lock provider record."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(lock_root) if lock_root else root
        registry = build_default_delivery_transaction_lock_provider_registry()
        provider = registry.create(provider_id)
        config = DeliveryTransactionLockProviderConfig(
            lock_root=target_root,
            transaction_id=transaction_id,
            owner=owner,
            action=action,
            mode=DeliveryExecutionMode(mode),
            lease_seconds=lease_seconds,
            expected_owner=expected_owner,
            expected_fencing_token=expected_fencing_token,
            approve_release=approve_release,
            allow_stale_takeover=allow_stale_takeover,
            metadata=metadata,
        )
        return provider.manage_lock(config, created_at=datetime.now(timezone.utc).isoformat()).to_dict()

    manage_delivery_transaction_lock_provider.__name__ = "manage_delivery_transaction_lock_provider"
    manage_delivery_transaction_lock_provider.__doc__ = (
        "Inspect, acquire, renew, or release a pluggable delivery transaction lock provider record. "
        "The default tool provider is local-file-lock; the default registry also includes sqlite-lock / db-lock and redis-lock / redis, "
        "where SQLite stores the authoritative row locally and Redis uses an external key as the authoritative lease store while writing JSON projection / operation records. Dry-run is read-only. "
        "This does not execute delivery, publish external delivery, mutate manifests, commit transactions, replace the existing "
        "delivery-transaction-lock.json LocalDeliveryExecutor gate, provide Redlock quorum consensus, or enforce downstream fencing by itself. "
        "External providers can be discovered through the reverse_deepagent.delivery_lock_providers entry point group."
    )
    return manage_delivery_transaction_lock_provider


def make_delivery_resume_workflow_scheduler_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for durable multi-step delivery resume workflows."""

    root = Path(default_delivery_root)

    def execute_delivery_resume_workflow(
        delivery_root: str | None = None,
        transaction_id: str | None = None,
        action: str = "plan_workflow",
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        step_actions_json: str | None = None,
        max_steps: int = 5,
        backend_manifest_path: str | None = None,
        expected_transaction_id: str | None = None,
        approval_ledger_path: str | None = None,
        approval_decision: str = "approved",
        require_review_approval: bool = True,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        lease_renewal_warning_seconds: int | None = None,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        transaction_lock_provider_id: str = "local-file-lock",
        transaction_lock_provider_metadata_json: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or execute a review-gated multi-step delivery resume workflow."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        transaction_lock_provider_metadata = (
            json.loads(transaction_lock_provider_metadata_json) if transaction_lock_provider_metadata_json else {}
        )
        if not isinstance(transaction_lock_provider_metadata, dict):
            raise ValueError("transaction_lock_provider_metadata_json must decode to an object")
        raw_step_actions = json.loads(step_actions_json) if step_actions_json else []
        if not isinstance(raw_step_actions, list):
            raise ValueError("step_actions_json must decode to a list")
        step_actions = tuple(str(item) for item in raw_step_actions)
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryResumeWorkflowSchedulerConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            action=action,
            mode=DeliveryExecutionMode(mode),
            step_actions=step_actions,
            max_steps=max_steps,
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            expected_transaction_id=expected_transaction_id,
            approval_ledger_path=Path(approval_ledger_path) if approval_ledger_path else None,
            approval_decision=approval_decision,
            require_review_approval=require_review_approval,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            lease_renewal_warning_seconds=lease_renewal_warning_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            transaction_lock_provider_id=transaction_lock_provider_id,
            transaction_lock_provider_metadata=transaction_lock_provider_metadata,
            metadata=metadata,
        )
        return DeliveryResumeWorkflowScheduler(config).execute().to_dict()

    execute_delivery_resume_workflow.__name__ = "execute_delivery_resume_workflow"
    execute_delivery_resume_workflow.__doc__ = (
        "Plan or execute a review-gated multi-step delivery resume workflow. "
        "Dry-run is read-only. apply mode with action=execute_workflow requires review-approval-ledger entries for every pending step action, "
        "then delegates resume steps to DeliveryResumeRunner and appends delivery-resume-workflow-journal.json. "
        "step_actions_json should be a JSON list such as [\"preflight_backend_manifest_recovery\", \"apply_backend_manifest_recovery\"] "
        "or explicit lock-provider steps such as [\"acquire_delivery_transaction_lock_provider\", \"renew_delivery_transaction_lock_provider\", \"release_delivery_transaction_lock_provider\"]. "
        "When no explicit step_actions_json is provided, lease_renewal_warning_seconds can tune the plan-only lease renewal recommendation window; "
        "expired or soon-expiring provider lease evidence may prepend a reviewed renew_delivery_transaction_lock_provider step, but planning never contacts the provider. "
        "transaction_lock_provider_id and transaction_lock_provider_metadata_json configure those lock-provider steps; they call acquire_lock / renew_lock / release_lock only when explicitly reviewed and are not a background daemon or auto-renew loop. "
        "The scheduler skips already completed journaled steps, writes delivery-resume-workflow.json for completed apply workflows, "
        "and never starts new delivery, publishes external delivery, automatically acquires/renews/releases distributed locks, or executes physical rollback."
    )
    return execute_delivery_resume_workflow


def make_delivery_transition_executor_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for explicit transaction transition execution."""

    root = Path(default_delivery_root)

    def execute_delivery_transition(
        transaction_id: str,
        transition: str = "auto",
        delivery_root: str | None = None,
        artifact_root: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        backend_manifest_path: str | None = None,
        expected_transaction_id: str | None = None,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or explicitly execute one supported delivery transaction transition."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryTransitionExecutorConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            transition=transition,
            mode=DeliveryExecutionMode(mode),
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            expected_transaction_id=expected_transaction_id,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            metadata=metadata,
        )
        return DeliveryTransactionTransitionExecutor(config).execute().to_dict()

    execute_delivery_transition.__name__ = "execute_delivery_transition"
    execute_delivery_transition.__doc__ = (
        "Plan or explicitly execute one supported delivery transaction transition. "
        "Supported transitions are preflight_backend_manifest_recovery, apply_backend_manifest_recovery, and commit_cross_run_transaction. "
        "mode defaults to dry-run and is read-only. apply mode requires an explicit transition value rather than auto, then delegates to LocalDeliveryExecutor so existing journal, digest, recovery, commit, and external-delivery checks still apply. "
        "The tool writes delivery-transition-execution.json only for successful explicit apply-mode transition attempts and never publishes external delivery. "
        "require_transaction_lock enables the local delivery-transaction-lock.json gate for apply-mode transition side effects."
    )
    return execute_delivery_transition


def make_delivery_recovery_executor_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for explicit delivery transaction recovery workflows."""

    root = Path(default_delivery_root)

    def execute_delivery_recovery(
        transaction_id: str,
        action: str = "plan_recovery",
        delivery_root: str | None = None,
        artifact_root: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        backend_manifest_path: str | None = None,
        expected_transaction_id: str | None = None,
        approve_recovery: bool = False,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or explicitly execute a reviewed delivery recovery workflow."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryRecoveryExecutorConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            action=action,
            mode=DeliveryExecutionMode(mode),
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            expected_transaction_id=expected_transaction_id,
            approve_recovery=approve_recovery,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            metadata=metadata,
        )
        return DeliveryTransactionRecoveryExecutor(config).execute().to_dict()

    execute_delivery_recovery.__name__ = "execute_delivery_recovery"
    execute_delivery_recovery.__doc__ = (
        "Plan or explicitly execute a delivery transaction recovery workflow. "
        "Supported actions are plan_recovery, preflight_recovery, and apply_recovery. "
        "mode defaults to dry-run and is read-only. apply_recovery in apply mode requires approve_recovery=true and an expected_transaction_id, then orchestrates preflight_backend_manifest_recovery followed by apply_backend_manifest_recovery through the transition executor. "
        "The tool writes delivery-recovery-execution.json only for successful explicit apply-mode recovery workflows and never publishes external delivery or commits cross-run transactions. "
        "require_transaction_lock enables the local delivery-transaction-lock.json gate for apply-mode recovery side effects."
    )
    return execute_delivery_recovery


def make_delivery_rollback_state_writer_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for writing rollback-state audit artifacts."""

    root = Path(default_delivery_root)

    def write_delivery_rollback_state(
        delivery_root: str | None = None,
        transaction_id: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        write_state_record: bool = True,
        state_record_name: str = "delivery-rollback-state.json",
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan or explicitly write delivery-rollback-state.json from existing transaction artifacts."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryRollbackStateWriterConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            mode=DeliveryExecutionMode(mode),
            write_state_record=write_state_record,
            state_record_name=state_record_name,
            metadata=metadata,
        )
        return DeliveryRollbackStateArtifactWriter(config).execute().to_dict()

    write_delivery_rollback_state.__name__ = "write_delivery_rollback_state"
    write_delivery_rollback_state.__doc__ = (
        "Plan or explicitly write delivery-rollback-state.json from existing delivery transaction artifacts. "
        "mode defaults to dry-run and is read-only. apply mode writes only the rollback-state audit artifact, "
        "does not restore manifests, does not commit transactions, does not call external delivery providers, "
        "does not acquire distributed locks, and does not execute physical rollback."
    )
    return write_delivery_rollback_state


def make_delivery_rollback_executor_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for planning and preflighting rollback workflows."""

    root = Path(default_delivery_root)

    def execute_delivery_rollback(
        transaction_id: str,
        action: str = "plan_rollback",
        delivery_root: str | None = None,
        artifact_root: str | None = None,
        mode: str = DeliveryExecutionMode.DRY_RUN.value,
        backend_manifest_path: str | None = None,
        expected_transaction_id: str | None = None,
        approve_rollback: bool = False,
        expected_rollback_phase: str | None = None,
        require_transaction_lock: bool = False,
        transaction_lock_owner: str | None = None,
        transaction_lock_lease_seconds: int = 900,
        expected_resume_token: str | None = None,
        expected_transaction_lock_fencing_token: str | None = None,
        metadata_json: str | None = None,
    ) -> dict[str, Any]:
        """Plan, preflight, or explicitly apply a reviewed delivery rollback workflow."""

        metadata = json.loads(metadata_json) if metadata_json else {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata_json must decode to an object")
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryRollbackExecutorConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            action=action,
            mode=DeliveryExecutionMode(mode),
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            expected_transaction_id=expected_transaction_id,
            approve_rollback=approve_rollback,
            expected_rollback_phase=expected_rollback_phase,
            require_transaction_lock=require_transaction_lock,
            transaction_lock_owner=transaction_lock_owner,
            transaction_lock_lease_seconds=transaction_lock_lease_seconds,
            expected_resume_token=expected_resume_token,
            expected_transaction_lock_fencing_token=expected_transaction_lock_fencing_token,
            metadata=metadata,
        )
        return DeliveryRollbackExecutor(config).execute().to_dict()

    execute_delivery_rollback.__name__ = "execute_delivery_rollback"
    execute_delivery_rollback.__doc__ = (
        "Plan, preflight, or explicitly apply a reviewed delivery rollback workflow. "
        "Supported actions are plan_rollback, preflight_rollback, and apply_rollback. "
        "mode defaults to dry-run and is read-only. preflight_rollback in apply mode writes delivery-rollback-state.json and backend-artifact-manifest-recovery-preflight.json, "
        "while apply_rollback in apply mode additionally requires approve_rollback=true, expected_transaction_id, backend_manifest_path, and a matching rollback phase before delegating local manifest recovery to the recovery executor. "
        "It does not commit transactions, does not call external delivery providers, does not acquire distributed locks, does not publish externally, and does not execute broader filesystem physical rollback. "
        "require_transaction_lock enables the local delivery-transaction-lock.json gate for apply-mode rollback side effects."
    )
    return execute_delivery_rollback


def _artifact_from_payload(payload: Any, *, artifact_root: Path) -> DeliveryArtifact:
    if not isinstance(payload, dict):
        raise ValueError("each delivery artifact must be an object")
    metadata = dict(payload.get("metadata")) if isinstance(payload.get("metadata"), dict) else {}
    source_path = payload.get("source_path") or payload.get("path")
    source_artifact_ref = payload.get("source_artifact_ref") or payload.get("artifact_ref")
    source_artifact_ref_field = "source_artifact_ref" if payload.get("source_artifact_ref") else "artifact_ref"
    artifact_key = str(payload.get("artifact_key")) if payload.get("artifact_key") is not None else None
    if source_path and source_artifact_ref:
        raise ValueError("delivery artifact must not provide both source_path and source_artifact_ref")
    if source_artifact_ref:
        read_result = read_workspace_artifact_payload(
            artifact_ref=str(source_artifact_ref),
            default_artifact_root=artifact_root,
            max_chars=1,
        )
        if read_result.get("status") != "found" or not read_result.get("path"):
            raise ValueError(f"delivery artifact source_artifact_ref could not be resolved: {source_artifact_ref}; checked_paths={read_result.get('checked_paths')}")
        source_path = str(read_result["path"])
        resolution = read_result.get("resolution") if isinstance(read_result.get("resolution"), dict) else {}
        artifact_key = artifact_key or str(resolution.get("artifact_key") or source_artifact_ref)
        workspace_artifact_read = summarize_workspace_artifact_read(read_result)
        metadata = {
            **metadata,
            "source_artifact_ref": str(source_artifact_ref),
            "workspace_artifact_read": workspace_artifact_read,
            "delivery_source_audit": _delivery_source_audit_for_artifact_ref(
                source_artifact_ref=str(source_artifact_ref),
                input_field=source_artifact_ref_field,
                workspace_artifact_read=workspace_artifact_read,
            ),
        }
    if not source_path:
        raise ValueError("delivery artifact requires source_path or source_artifact_ref")
    if "delivery_source_audit" not in metadata:
        metadata["delivery_source_audit"] = _delivery_source_audit_for_source_path(
            source_path=str(source_path),
            artifact_root=artifact_root,
            input_field="source_path" if payload.get("source_path") else "path",
        )
    return DeliveryArtifact(
        source_path=Path(str(source_path)),
        artifact_key=artifact_key,
        destination_name=str(payload.get("destination_name")) if payload.get("destination_name") is not None else None,
        required=bool(payload.get("required", True)),
        metadata=metadata,
    )


def _delivery_source_audit_for_artifact_ref(
    *,
    source_artifact_ref: str,
    input_field: str,
    workspace_artifact_read: dict[str, Any],
) -> dict[str, Any]:
    """Return source compatibility diagnostics for resolver-backed delivery inputs."""

    resolver_metrics = (
        workspace_artifact_read.get("resolver_metrics") if isinstance(workspace_artifact_read.get("resolver_metrics"), dict) else {}
    )
    resolution = workspace_artifact_read.get("resolution") if isinstance(workspace_artifact_read.get("resolution"), dict) else {}
    return {
        "schema_version": "reverse-deepagent.delivery-source-compatibility-audit.v1",
        "input_field": input_field,
        "source_input_kind": "workspace-artifact-ref",
        "source_path_kind": "resolver-backed-workspace-artifact",
        "source_artifact_ref": source_artifact_ref,
        "artifact_ref_kind": resolver_metrics.get("artifact_ref_kind") or "",
        "resolution_status": workspace_artifact_read.get("resolution_status") or resolver_metrics.get("resolution_status") or "",
        "resolved_artifact_key": resolver_metrics.get("resolved_artifact_key") or resolution.get("artifact_key") or "",
        "hit_path_kind": resolver_metrics.get("hit_path_kind") or "",
        "canonical_path": resolver_metrics.get("canonical_path") or resolution.get("canonical_path") or "",
        "future_path": resolver_metrics.get("future_path") or resolution.get("future_path") or "",
        "workspace_resolved": True,
        "source_path_compatibility": "resolver-ready",
        "source_path_retained_for_compatibility": False,
        "explicit_filesystem_boundary": False,
        "read_only": True,
    }


def _delivery_source_audit_for_source_path(
    *,
    source_path: str,
    artifact_root: Path,
    input_field: str,
) -> dict[str, Any]:
    """Classify legacy source_path usage without changing delivery path semantics."""

    resolver = WorkspacePathResolver()
    normalized_refs = _source_path_workspace_lookup_refs(source_path, artifact_root)
    resolution = None
    for ref in normalized_refs:
        resolution = resolver.resolve_path(ref)
        if resolution is not None:
            break
    source_path_kind = _source_path_kind(source_path, artifact_root, resolution)
    resolved_artifact_key = resolution.artifact_key if resolution else ""
    return {
        "schema_version": "reverse-deepagent.delivery-source-compatibility-audit.v1",
        "input_field": input_field,
        "source_input_kind": "source-path",
        "source_path_kind": source_path_kind,
        "artifact_ref_kind": "",
        "resolution_status": "resolved" if resolution else "explicit-filesystem-path",
        "resolved_artifact_key": resolved_artifact_key,
        "hit_path_kind": "",
        "canonical_path": resolution.canonical_path if resolution else "",
        "future_path": resolution.future_path if resolution else "",
        "workspace_resolved": bool(resolution),
        "source_path_compatibility": _source_path_compatibility(source_path_kind),
        "source_path_retained_for_compatibility": True,
        "explicit_filesystem_boundary": source_path_kind
        in {"absolute-source-path", "external-filesystem-source-path", "relative-source-path", "virtual-uri-source-path"},
        "read_only": True,
    }


def _source_path_workspace_lookup_refs(source_path: str, artifact_root: Path) -> list[str]:
    value = str(source_path).strip()
    refs: list[str] = []
    if value:
        refs.append(value)
    if value.startswith("virtual://"):
        return _dedupe_strings(refs)
    path = Path(value)
    root = artifact_root.expanduser().resolve()
    if path.is_absolute():
        try:
            relative = path.expanduser().resolve().relative_to(root).as_posix()
        except ValueError:
            relative = ""
        if relative:
            refs.append(relative)
            if relative.startswith("workspace/"):
                refs.append(f"/{relative}")
    else:
        normalized = path.as_posix()
        refs.append(normalized)
        if normalized.startswith("workspace/"):
            refs.append(f"/{normalized}")
    return _dedupe_strings(refs)


def _source_path_kind(source_path: str, artifact_root: Path, resolution: Any | None) -> str:
    value = str(source_path).strip()
    if value.startswith("virtual://"):
        return "virtual-uri-source-path"
    path = Path(value)
    root = artifact_root.expanduser().resolve()
    relative_to_root = False
    relative_text = ""
    if path.is_absolute():
        try:
            relative_text = path.expanduser().resolve().relative_to(root).as_posix()
            relative_to_root = True
        except ValueError:
            relative_to_root = False
    else:
        relative_text = path.as_posix()
    if resolution is not None:
        if relative_text == resolution.legacy_path or value == resolution.legacy_path:
            return "legacy-source-path"
        if relative_text == resolution.future_path.lstrip("/") or value == resolution.future_path:
            return "future-source-path"
        if relative_to_root:
            return "artifact-root-relative-source-path"
    if path.is_absolute():
        return "artifact-root-relative-source-path" if relative_to_root else "external-filesystem-source-path"
    return "relative-source-path"


def _source_path_compatibility(source_path_kind: str) -> str:
    if source_path_kind == "legacy-source-path":
        return "legacy-workspace-path-compatible"
    if source_path_kind == "future-source-path":
        return "future-workspace-path-compatible"
    if source_path_kind == "artifact-root-relative-source-path":
        return "artifact-root-relative-path"
    if source_path_kind == "external-filesystem-source-path":
        return "explicit-external-filesystem-path"
    if source_path_kind == "virtual-uri-source-path":
        return "unsupported-virtual-uri-in-source_path-use-source_artifact_ref"
    return "relative-filesystem-path"


def _summarize_delivery_source_audit(artifacts: list[DeliveryArtifact]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    by_source_input_kind: dict[str, int] = {}
    by_source_path_kind: dict[str, int] = {}
    workspace_resolved_count = 0
    external_source_path_count = 0
    source_path_count = 0
    source_artifact_ref_count = 0
    for artifact in artifacts:
        audit = artifact.metadata.get("delivery_source_audit") if isinstance(artifact.metadata, dict) else None
        if not isinstance(audit, dict):
            continue
        source_input_kind = str(audit.get("source_input_kind") or "unknown")
        source_path_kind = str(audit.get("source_path_kind") or "unknown")
        by_source_input_kind[source_input_kind] = by_source_input_kind.get(source_input_kind, 0) + 1
        by_source_path_kind[source_path_kind] = by_source_path_kind.get(source_path_kind, 0) + 1
        workspace_resolved_count += int(bool(audit.get("workspace_resolved")))
        source_path_count += int(source_input_kind == "source-path")
        source_artifact_ref_count += int(source_input_kind == "workspace-artifact-ref")
        external_source_path_count += int(source_path_kind == "external-filesystem-source-path")
        items.append(
            {
                "artifact_key": artifact.artifact_key,
                "input_field": audit.get("input_field"),
                "source_input_kind": source_input_kind,
                "source_path_kind": source_path_kind,
                "source_path_compatibility": audit.get("source_path_compatibility"),
                "workspace_resolved": bool(audit.get("workspace_resolved")),
                "resolved_artifact_key": audit.get("resolved_artifact_key") or "",
                "source_path_retained_for_compatibility": bool(audit.get("source_path_retained_for_compatibility")),
                "explicit_filesystem_boundary": bool(audit.get("explicit_filesystem_boundary")),
            }
        )
    return {
        "schema_version": "reverse-deepagent.delivery-source-compatibility-audit.v1",
        "artifact_count": len(artifacts),
        "audited_artifact_count": len(items),
        "source_artifact_ref_count": source_artifact_ref_count,
        "source_path_count": source_path_count,
        "workspace_resolved_count": workspace_resolved_count,
        "external_source_path_count": external_source_path_count,
        "legacy_source_path_count": by_source_path_kind.get("legacy-source-path", 0),
        "future_source_path_count": by_source_path_kind.get("future-source-path", 0),
        "artifact_root_relative_source_path_count": by_source_path_kind.get("artifact-root-relative-source-path", 0),
        "relative_source_path_count": by_source_path_kind.get("relative-source-path", 0),
        "by_source_input_kind": dict(sorted(by_source_input_kind.items())),
        "by_source_path_kind": dict(sorted(by_source_path_kind.items())),
        "items": items,
        "side_effect_policy": {
            "read_only": True,
            "files_inspected": False,
            "artifacts_written": False,
            "creates_directories": False,
            "enables_dual_write": False,
            "migrates_paths": False,
            "starts_browser": False,
            "calls_mcp": False,
        },
    }


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
