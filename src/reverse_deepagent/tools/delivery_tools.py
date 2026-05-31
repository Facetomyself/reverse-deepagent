from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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


def make_local_delivery_executor_tool(default_delivery_root: str | Path) -> DeliveryTool:
    """Create a tool wrapper for side-effect-safe local delivery execution."""

    root = Path(default_delivery_root)

    def execute_local_delivery(
        artifacts_json: str,
        transaction_id: str,
        delivery_root: str | None = None,
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
        artifacts = [_artifact_from_payload(item) for item in raw_artifacts]
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
        return LocalDeliveryExecutor(config).execute(artifacts).to_dict()

    execute_local_delivery.__name__ = "execute_local_delivery"
    execute_local_delivery.__doc__ = (
        "Plan or apply local filesystem delivery. artifacts_json is a JSON list with source_path, optional artifact_key, "
        "destination_name, required, and metadata. mode defaults to dry-run; apply copies files locally and writes receipt/journal. "
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


def _artifact_from_payload(payload: Any) -> DeliveryArtifact:
    if not isinstance(payload, dict):
        raise ValueError("each delivery artifact must be an object")
    source_path = payload.get("source_path") or payload.get("path")
    if not source_path:
        raise ValueError("delivery artifact requires source_path")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return DeliveryArtifact(
        source_path=Path(str(source_path)),
        artifact_key=str(payload.get("artifact_key")) if payload.get("artifact_key") is not None else None,
        destination_name=str(payload.get("destination_name")) if payload.get("destination_name") is not None else None,
        required=bool(payload.get("required", True)),
        metadata=metadata,
    )
