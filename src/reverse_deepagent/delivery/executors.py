from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class DeliveryExecutionMode(str, Enum):
    """Supported delivery executor side-effect modes."""

    DRY_RUN = "dry-run"
    APPLY = "apply"


@dataclass(frozen=True)
class DeliveryArtifact:
    """A filesystem artifact that can be included in a local delivery transaction."""

    source_path: Path
    artifact_key: str | None = None
    destination_name: str | None = None
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_source(self) -> Path:
        return self.source_path.expanduser().resolve()

    def safe_destination_name(self) -> str:
        raw = self.destination_name or self.source_path.name
        safe = raw.replace("\\", "/").split("/")[-1].strip()
        if not safe or safe in {".", ".."}:
            raise ValueError(f"Invalid delivery destination name: {raw!r}")
        return safe


@dataclass(frozen=True)
class DeliveryExecutorConfig:
    """Local delivery executor configuration.

    The default mode is dry-run, so constructing or calling the executor never
    mutates the filesystem unless the caller explicitly selects APPLY.
    """

    delivery_root: Path
    transaction_id: str
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    write_receipt: bool = True
    overwrite: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    commit_manifest_revision: bool = False
    manifest_revision_name: str = "delivery-manifest-revision.json"
    commit_backend_manifest_mutation: bool = False
    backend_manifest_path: Path | None = None
    backend_manifest_mutation_name: str = "backend-artifact-manifest-mutation.json"
    backend_manifest_patched_name: str = "backend-artifact-manifest.patched.json"

    def resolved_delivery_root(self) -> Path:
        return self.delivery_root.expanduser().resolve()

    def resolved_backend_manifest_path(self) -> Path | None:
        if self.backend_manifest_path is None:
            return None
        return self.backend_manifest_path.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryReceipt:
    transaction_id: str
    status: str
    mode: str
    delivery_root: str
    delivered_artifacts: list[dict[str, Any]]
    skipped_artifacts: list[dict[str, Any]]
    receipt_path: str | None
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mode": self.mode,
            "delivery_root": self.delivery_root,
            "delivered_artifacts": self.delivered_artifacts,
            "skipped_artifacts": self.skipped_artifacts,
            "receipt_path": self.receipt_path,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryManifestRevision:
    transaction_id: str
    status: str
    revision_id: str
    revision_path: str | None
    delivery_root: str
    committed: bool
    dry_run: bool
    backend_manifest_mutated: bool
    delivered_artifacts: list[dict[str, Any]]
    source_artifact_count: int
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "revision_id": self.revision_id,
            "revision_path": self.revision_path,
            "delivery_root": self.delivery_root,
            "committed": self.committed,
            "dry_run": self.dry_run,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "delivered_artifacts": self.delivered_artifacts,
            "source_artifact_count": self.source_artifact_count,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BackendManifestMutation:
    transaction_id: str
    status: str
    mutation_id: str
    mutation_path: str | None
    patched_manifest_path: str | None
    source_manifest_path: str | None
    dry_run: bool
    backend_manifest_mutation_planned: bool
    backend_manifest_patch_written: bool
    backend_manifest_mutated: bool
    source_manifest_digest_sha256: str | None
    patched_manifest_digest_sha256: str | None
    added_entries: list[dict[str, Any]]
    source_entry_count: int
    patched_entry_count: int
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mutation_id": self.mutation_id,
            "mutation_path": self.mutation_path,
            "patched_manifest_path": self.patched_manifest_path,
            "source_manifest_path": self.source_manifest_path,
            "dry_run": self.dry_run,
            "backend_manifest_mutation_planned": self.backend_manifest_mutation_planned,
            "backend_manifest_patch_written": self.backend_manifest_patch_written,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "source_manifest_digest_sha256": self.source_manifest_digest_sha256,
            "patched_manifest_digest_sha256": self.patched_manifest_digest_sha256,
            "added_entries": self.added_entries,
            "source_entry_count": self.source_entry_count,
            "patched_entry_count": self.patched_entry_count,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryTransactionJournal:
    transaction_id: str
    status: str
    journal_path: str | None
    manifest_revision_committed: bool
    filesystem_artifact_mutated: bool
    external_delivery_performed: bool
    rollback_available: bool
    manifest_revision_path: str | None
    backend_manifest_mutation_path: str | None
    backend_manifest_patched_path: str | None
    backend_manifest_patch_written: bool
    backend_manifest_mutated: bool
    entries: list[dict[str, Any]]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "journal_path": self.journal_path,
            "manifest_revision_committed": self.manifest_revision_committed,
            "filesystem_artifact_mutated": self.filesystem_artifact_mutated,
            "external_delivery_performed": self.external_delivery_performed,
            "rollback_available": self.rollback_available,
            "manifest_revision_path": self.manifest_revision_path,
            "backend_manifest_mutation_path": self.backend_manifest_mutation_path,
            "backend_manifest_patched_path": self.backend_manifest_patched_path,
            "backend_manifest_patch_written": self.backend_manifest_patch_written,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "entries": self.entries,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryExecutionResult:
    status: str
    mode: str
    transaction_id: str
    dry_run: bool
    delivery_allowed: bool
    filesystem_artifact_mutated: bool
    external_delivery_performed: bool
    manifest_revision_committed: bool
    backend_manifest_patch_written: bool
    backend_manifest_mutated: bool
    receipt: DeliveryReceipt
    transaction_journal: DeliveryTransactionJournal
    manifest_revision: DeliveryManifestRevision | None
    backend_manifest_mutation: BackendManifestMutation | None
    planned_artifacts: list[dict[str, Any]]
    errors: list[str] = field(default_factory=list)
    next_action: str = "review_delivery_receipt_before_external_handoff"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "transaction_id": self.transaction_id,
            "dry_run": self.dry_run,
            "delivery_allowed": self.delivery_allowed,
            "filesystem_artifact_mutated": self.filesystem_artifact_mutated,
            "external_delivery_performed": self.external_delivery_performed,
            "manifest_revision_committed": self.manifest_revision_committed,
            "backend_manifest_patch_written": self.backend_manifest_patch_written,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "receipt": self.receipt.to_dict(),
            "transaction_journal": self.transaction_journal.to_dict(),
            "manifest_revision": self.manifest_revision.to_dict() if self.manifest_revision else None,
            "backend_manifest_mutation": self.backend_manifest_mutation.to_dict() if self.backend_manifest_mutation else None,
            "planned_artifacts": self.planned_artifacts,
            "errors": self.errors,
            "next_action": self.next_action,
        }


class LocalDeliveryExecutor:
    """Side-effect-safe local filesystem delivery executor.

    It intentionally does not publish to external services.  APPLY only copies
    reviewed source artifacts into a local delivery folder and writes receipt /
    journal files that future cross-run transaction work can consume.
    """

    def __init__(self, config: DeliveryExecutorConfig) -> None:
        self.config = config

    def execute(self, artifacts: list[DeliveryArtifact]) -> DeliveryExecutionResult:
        created_at = datetime.now(timezone.utc).isoformat()
        delivery_root = self.config.resolved_delivery_root()
        planned, errors = self._plan_artifacts(artifacts, delivery_root)
        mode = self.config.mode
        dry_run = mode == DeliveryExecutionMode.DRY_RUN
        delivered: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        if errors:
            status = "failed"
            next_action = "fix_delivery_artifact_inputs"
        elif dry_run:
            status = "planned"
            next_action = "approve_local_delivery_apply"
            skipped = [dict(item, reason="dry_run") for item in planned]
        else:
            delivery_root.mkdir(parents=True, exist_ok=True)
            for item in planned:
                destination = Path(item["destination_path"])
                if destination.exists() and not self.config.overwrite:
                    errors.append(f"destination_exists:{destination}")
                    skipped.append(dict(item, reason="destination_exists"))
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item["source_path"], destination)
                delivered.append(dict(item, status="delivered", digest_sha256=_file_sha256(destination)))
            status = "delivered" if delivered and not errors else "failed" if errors else "partial"
            next_action = "review_delivery_receipt_before_external_handoff" if delivered else "fix_delivery_artifact_inputs"

        receipt_path = str(delivery_root / "delivery-receipt.json") if self.config.write_receipt and not dry_run and not errors else None
        journal_path = str(delivery_root / "delivery-transaction-journal.json") if self.config.write_receipt and not dry_run and not errors else None
        manifest_revision_path = (
            str(delivery_root / self.config.manifest_revision_name)
            if self.config.write_receipt and self.config.commit_manifest_revision and not dry_run and not errors
            else None
        )
        backend_manifest_mutation_path = (
            str(delivery_root / self.config.backend_manifest_mutation_name)
            if self.config.write_receipt and self.config.commit_backend_manifest_mutation and not dry_run and not errors
            else None
        )
        backend_manifest_patched_path = (
            str(delivery_root / self.config.backend_manifest_patched_name)
            if self.config.write_receipt and self.config.commit_backend_manifest_mutation and not dry_run and not errors
            else None
        )
        receipt = DeliveryReceipt(
            transaction_id=self.config.transaction_id,
            status=status,
            mode=mode.value,
            delivery_root=str(delivery_root),
            delivered_artifacts=delivered,
            skipped_artifacts=skipped,
            receipt_path=receipt_path,
            created_at=created_at,
            metadata={**self.config.metadata, "executor": "local-filesystem"},
        )
        manifest_revision = self._build_manifest_revision(
            delivery_root=delivery_root,
            delivered=delivered,
            planned=planned,
            status=status,
            dry_run=dry_run,
            created_at=created_at,
            revision_path=manifest_revision_path,
        )
        backend_manifest_mutation = self._build_backend_manifest_mutation(
            delivery_root=delivery_root,
            delivered=delivered,
            planned=planned,
            status=status,
            dry_run=dry_run,
            created_at=created_at,
            mutation_path=backend_manifest_mutation_path,
            patched_manifest_path=backend_manifest_patched_path,
            receipt_path=receipt_path,
            journal_path=journal_path,
            manifest_revision_path=manifest_revision_path,
        )
        journal = DeliveryTransactionJournal(
            transaction_id=self.config.transaction_id,
            status=status,
            journal_path=journal_path,
            manifest_revision_committed=bool(manifest_revision and manifest_revision.committed),
            filesystem_artifact_mutated=bool(delivered),
            external_delivery_performed=False,
            rollback_available=bool(delivered),
            manifest_revision_path=manifest_revision_path,
            backend_manifest_mutation_path=backend_manifest_mutation_path,
            backend_manifest_patched_path=backend_manifest_patched_path,
            backend_manifest_patch_written=bool(backend_manifest_mutation and backend_manifest_mutation.backend_manifest_patch_written),
            backend_manifest_mutated=False,
            entries=[
                {
                    "action": "copy_artifact",
                    "source_path": item["source_path"],
                    "destination_path": item["destination_path"],
                    "status": "delivered" if any(d["destination_path"] == item["destination_path"] for d in delivered) else "planned" if dry_run else "skipped",
                }
                for item in planned
            ],
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "local-delivery-transaction-baseline",
                "limitations": [
                    "does_not_publish_external_delivery",
                    "does_not_mutate_backend_artifact_manifest_in_place",
                    "rollback_is_journal_only_baseline",
                    "backend_manifest_patch_is_local_copy_only",
                ],
            },
        )
        if receipt_path:
            _write_json(Path(receipt_path), receipt.to_dict())
        if manifest_revision_path and manifest_revision:
            _write_json(Path(manifest_revision_path), manifest_revision.to_dict())
        if backend_manifest_patched_path and backend_manifest_mutation:
            patched_manifest = self._build_patched_backend_manifest(backend_manifest_mutation)
            _write_json(Path(backend_manifest_patched_path), patched_manifest)
            patched_digest = _file_sha256(Path(backend_manifest_patched_path))
            backend_manifest_mutation = _replace_backend_manifest_mutation_digest(backend_manifest_mutation, patched_digest)
        if backend_manifest_mutation_path and backend_manifest_mutation:
            _write_json(Path(backend_manifest_mutation_path), backend_manifest_mutation.to_dict())
        if journal_path:
            _write_json(Path(journal_path), journal.to_dict())
        return DeliveryExecutionResult(
            status=status,
            mode=mode.value,
            transaction_id=self.config.transaction_id,
            dry_run=dry_run,
            delivery_allowed=not bool(errors),
            filesystem_artifact_mutated=bool(delivered),
            external_delivery_performed=False,
            manifest_revision_committed=bool(manifest_revision and manifest_revision.committed),
            backend_manifest_patch_written=bool(backend_manifest_mutation and backend_manifest_mutation.backend_manifest_patch_written),
            backend_manifest_mutated=False,
            receipt=receipt,
            transaction_journal=journal,
            manifest_revision=manifest_revision,
            backend_manifest_mutation=backend_manifest_mutation,
            planned_artifacts=planned,
            errors=errors,
            next_action=next_action,
        )

    def _build_manifest_revision(
        self,
        *,
        delivery_root: Path,
        delivered: list[dict[str, Any]],
        planned: list[dict[str, Any]],
        status: str,
        dry_run: bool,
        created_at: str,
        revision_path: str | None,
    ) -> DeliveryManifestRevision | None:
        if not self.config.commit_manifest_revision:
            return None
        committed = bool(delivered) and not dry_run and status == "delivered"
        revision_status = "committed" if committed else "planned" if dry_run else "skipped"
        return DeliveryManifestRevision(
            transaction_id=self.config.transaction_id,
            status=revision_status,
            revision_id=f"manifest-revision-{self.config.transaction_id}",
            revision_path=revision_path,
            delivery_root=str(delivery_root),
            committed=committed,
            dry_run=dry_run,
            backend_manifest_mutated=False,
            delivered_artifacts=list(delivered),
            source_artifact_count=len(planned),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "local-delivery-manifest-revision-baseline",
                "limitations": [
                    "does_not_mutate_backend_artifact_manifest",
                    "does_not_publish_external_delivery",
                    "cross_run_recovery_state_machine_not_implemented",
                ],
            },
        )

    def _build_backend_manifest_mutation(
        self,
        *,
        delivery_root: Path,
        delivered: list[dict[str, Any]],
        planned: list[dict[str, Any]],
        status: str,
        dry_run: bool,
        created_at: str,
        mutation_path: str | None,
        patched_manifest_path: str | None,
        receipt_path: str | None,
        journal_path: str | None,
        manifest_revision_path: str | None,
    ) -> BackendManifestMutation | None:
        if not self.config.commit_backend_manifest_mutation:
            return None
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest = _read_json_object(source_manifest_path) if source_manifest_path and source_manifest_path.exists() else {}
        source_entries = source_manifest.get("entries") if isinstance(source_manifest.get("entries"), list) else []
        added_entries = self._backend_manifest_added_entries(
            delivered=delivered,
            planned=planned,
            dry_run=dry_run,
            delivery_root=delivery_root,
            receipt_path=receipt_path,
            journal_path=journal_path,
            manifest_revision_path=manifest_revision_path,
            mutation_path=mutation_path,
            patched_manifest_path=patched_manifest_path,
        )
        patch_written = bool(delivered) and not dry_run and status == "delivered" and mutation_path is not None and patched_manifest_path is not None
        mutation_status = "patch_written" if patch_written else "planned" if dry_run else "skipped"
        return BackendManifestMutation(
            transaction_id=self.config.transaction_id,
            status=mutation_status,
            mutation_id=f"backend-manifest-mutation-{self.config.transaction_id}",
            mutation_path=mutation_path,
            patched_manifest_path=patched_manifest_path,
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            dry_run=dry_run,
            backend_manifest_mutation_planned=True,
            backend_manifest_patch_written=patch_written,
            backend_manifest_mutated=False,
            source_manifest_digest_sha256=_file_sha256(source_manifest_path) if source_manifest_path and source_manifest_path.exists() else None,
            patched_manifest_digest_sha256=None,
            added_entries=added_entries,
            source_entry_count=len(source_entries),
            patched_entry_count=len(source_entries) + len(added_entries),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-artifact-manifest-mutation-policy-baseline",
                "source_manifest_exists": bool(source_manifest_path and source_manifest_path.exists()),
                "limitations": [
                    "does_not_mutate_backend_artifact_manifest_in_place",
                    "writes_local_patched_manifest_copy_only",
                    "does_not_publish_external_delivery",
                    "cross_run_manifest_recovery_not_implemented",
                ],
            },
        )

    def _backend_manifest_added_entries(
        self,
        *,
        delivered: list[dict[str, Any]],
        planned: list[dict[str, Any]],
        dry_run: bool,
        delivery_root: Path,
        receipt_path: str | None,
        journal_path: str | None,
        manifest_revision_path: str | None,
        mutation_path: str | None,
        patched_manifest_path: str | None,
    ) -> list[dict[str, Any]]:
        source_items = delivered if delivered else planned if dry_run else []
        entries = [
            _backend_manifest_entry(
                artifact_key=str(item.get("artifact_key") or f"delivery_artifact_{index}"),
                path=str(item.get("destination_path")),
                category="export",
                transaction_id=self.config.transaction_id,
                source="delivered_artifact" if delivered else "planned_artifact",
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
            for index, item in enumerate(source_items)
            if item.get("destination_path")
        ]
        synthetic_paths = [
            ("workspace_delivery_receipt", receipt_path or str(delivery_root / "delivery-receipt.json")),
            ("workspace_delivery_transaction_journal", journal_path or str(delivery_root / "delivery-transaction-journal.json")),
            ("workspace_backend_artifact_manifest_mutation", mutation_path or str(delivery_root / self.config.backend_manifest_mutation_name)),
            ("workspace_backend_artifact_manifest_patched", patched_manifest_path or str(delivery_root / self.config.backend_manifest_patched_name)),
        ]
        if self.config.commit_manifest_revision:
            synthetic_paths.insert(
                2,
                ("workspace_delivery_manifest_revision", manifest_revision_path or str(delivery_root / self.config.manifest_revision_name)),
            )
        for artifact_key, path in synthetic_paths:
            entries.append(
                _backend_manifest_entry(
                    artifact_key=artifact_key,
                    path=path,
                    category="export",
                    transaction_id=self.config.transaction_id,
                    source="local_delivery_policy_artifact",
                    metadata={"generated_by": "LocalDeliveryExecutor"},
                )
            )
        return entries

    def _build_patched_backend_manifest(self, mutation: BackendManifestMutation) -> dict[str, Any]:
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest = _read_json_object(source_manifest_path) if source_manifest_path and source_manifest_path.exists() else {}
        entries = list(source_manifest.get("entries") if isinstance(source_manifest.get("entries"), list) else [])
        existing_keys = {str(item.get("artifact_key")) for item in entries if isinstance(item, dict) and item.get("artifact_key")}
        for entry in mutation.added_entries:
            if entry["artifact_key"] in existing_keys:
                entries = [item for item in entries if not (isinstance(item, dict) and item.get("artifact_key") == entry["artifact_key"])]
            entries.append(entry)
            existing_keys.add(entry["artifact_key"])
        patched_manifest = dict(source_manifest)
        patched_manifest.setdefault("schema_version", "reverse-deepagent.backend-artifact-manifest.patched.v1")
        patched_manifest["entries"] = entries
        patched_manifest["mutation_policy"] = {
            "transaction_id": self.config.transaction_id,
            "mutation_id": mutation.mutation_id,
            "backend_manifest_mutated": False,
            "backend_manifest_patch_written": True,
            "scope": "local-patched-copy-only",
        }
        return patched_manifest

    def _plan_artifacts(self, artifacts: list[DeliveryArtifact], delivery_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
        planned: list[dict[str, Any]] = []
        errors: list[str] = []
        seen_destinations: set[str] = set()
        for index, artifact in enumerate(artifacts):
            try:
                source = artifact.resolved_source()
                destination_name = artifact.safe_destination_name()
            except Exception as exc:  # pragma: no cover - defensive value normalization
                errors.append(f"invalid_artifact:{index}:{exc}")
                continue
            if not source.exists():
                message = f"missing_source:{source}"
                if artifact.required:
                    errors.append(message)
                planned.append(
                    {
                        "artifact_key": artifact.artifact_key or f"artifact_{index}",
                        "source_path": str(source),
                        "destination_path": str(delivery_root / destination_name),
                        "exists": False,
                        "required": artifact.required,
                        "metadata": artifact.metadata,
                    }
                )
                continue
            destination_path = str(delivery_root / destination_name)
            if destination_path in seen_destinations:
                errors.append(f"duplicate_destination:{destination_path}")
                continue
            seen_destinations.add(destination_path)
            planned.append(
                {
                    "artifact_key": artifact.artifact_key or source.stem,
                    "source_path": str(source),
                    "destination_path": destination_path,
                    "exists": True,
                    "required": artifact.required,
                    "size_bytes": source.stat().st_size,
                    "digest_sha256": _file_sha256(source),
                    "metadata": artifact.metadata,
                }
            )
        return planned, errors


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Backend artifact manifest must be a JSON object: {path}")
    return payload


def _backend_manifest_entry(
    *,
    artifact_key: str,
    path: str,
    category: str,
    transaction_id: str,
    source: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_key": artifact_key,
        "path": path,
        "kind": "json",
        "category": category,
        "transaction_id": transaction_id,
        "source": source,
        "metadata": metadata or {},
    }


def _replace_backend_manifest_mutation_digest(
    mutation: BackendManifestMutation,
    patched_manifest_digest_sha256: str,
) -> BackendManifestMutation:
    return replace(mutation, patched_manifest_digest_sha256=patched_manifest_digest_sha256)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
