from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from reverse_deepagent.delivery import DeliveryArtifact, DeliveryExecutionMode, DeliveryExecutorConfig, LocalDeliveryExecutor


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
        "and webhook/http-webhook can POST a redacted JSON delivery package to an explicit webhook_url after apply. "
        "external_delivery_provider_config_json passes provider-specific JSON options such as {\"archive_root\": \"...\"} or {\"webhook_url\": \"...\", \"headers\": {...}}; raw config values are not exported in package metadata. "
        "external_delivery_idempotency_key defaults to the transaction id; duplicate external delivery is blocked by default unless allow_duplicate_external_delivery is explicitly true."
    )
    return execute_local_delivery


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
