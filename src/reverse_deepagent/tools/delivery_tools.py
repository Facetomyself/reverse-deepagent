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
        target_root = Path(delivery_root) if delivery_root else root
        config = DeliveryExecutorConfig(
            delivery_root=target_root,
            transaction_id=transaction_id,
            mode=DeliveryExecutionMode(mode),
            overwrite=overwrite,
            commit_manifest_revision=commit_manifest_revision,
            commit_backend_manifest_mutation=commit_backend_manifest_mutation,
            backend_manifest_path=Path(backend_manifest_path) if backend_manifest_path else None,
            metadata=metadata,
        )
        return LocalDeliveryExecutor(config).execute(artifacts).to_dict()

    execute_local_delivery.__name__ = "execute_local_delivery"
    execute_local_delivery.__doc__ = (
        "Plan or apply local filesystem delivery. artifacts_json is a JSON list with source_path, optional artifact_key, "
        "destination_name, required, and metadata. mode defaults to dry-run; apply copies files locally and writes receipt/journal. "
        "commit_manifest_revision can additionally write a local delivery-manifest-revision.json. "
        "commit_backend_manifest_mutation writes a local mutation record plus patched backend manifest copy without mutating the source manifest in place."
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
