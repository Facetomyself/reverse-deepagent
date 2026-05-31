from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


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
    preflight_backend_manifest_in_place_mutation: bool = False
    backend_manifest_preflight_name: str = "backend-artifact-manifest-preflight.json"
    expected_backend_manifest_digest_sha256: str | None = None
    approve_backend_manifest_in_place_mutation: bool = False
    backend_manifest_in_place_mutation_name: str = "backend-artifact-manifest-in-place-mutation.json"
    backend_manifest_rollback_name: str = "backend-artifact-manifest.rollback.json"
    preflight_backend_manifest_recovery: bool = False
    backend_manifest_recovery_preflight_name: str = "backend-artifact-manifest-recovery-preflight.json"
    expected_recovery_transaction_id: str | None = None
    apply_backend_manifest_recovery: bool = False
    backend_manifest_recovery_name: str = "backend-artifact-manifest-recovery.json"
    commit_cross_run_transaction: bool = False
    backend_manifest_transaction_commit_name: str = "backend-artifact-manifest-transaction-commit.json"
    expected_commit_transaction_id: str | None = None
    request_external_delivery: bool = False
    external_delivery_result_name: str = "external-delivery-result.json"
    external_delivery_provider_id: str = "review-only"
    external_delivery_provider: ExternalDeliveryProvider | None = None
    external_delivery_provider_registry: Any | None = None
    external_delivery_provider_config: dict[str, Any] = field(default_factory=dict)
    external_delivery_idempotency_key: str | None = None
    allow_duplicate_external_delivery: bool = False
    external_delivery_duplicate_guard_name: str = "external-delivery-duplicate-guard.json"

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
class ExternalDeliveryPackage:
    """Provider-neutral package handed to an external delivery provider."""

    transaction_id: str
    status: str
    mode: str
    delivery_root: str
    receipt_path: str | None
    transaction_journal_path: str | None
    external_delivery_result_path: str | None
    delivered_artifacts: list[dict[str, Any]]
    planned_artifacts: list[dict[str, Any]]
    local_errors: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mode": self.mode,
            "delivery_root": self.delivery_root,
            "receipt_path": self.receipt_path,
            "transaction_journal_path": self.transaction_journal_path,
            "external_delivery_result_path": self.external_delivery_result_path,
            "delivered_artifacts": self.delivered_artifacts,
            "planned_artifacts": self.planned_artifacts,
            "local_errors": self.local_errors,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExternalDeliveryResult:
    transaction_id: str
    status: str
    provider_id: str
    result_path: str | None
    delivery_root: str
    dry_run: bool
    external_delivery_requested: bool
    external_delivery_performed: bool
    package_digest_sha256: str
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "provider_id": self.provider_id,
            "result_path": self.result_path,
            "delivery_root": self.delivery_root,
            "dry_run": self.dry_run,
            "external_delivery_requested": self.external_delivery_requested,
            "external_delivery_performed": self.external_delivery_performed,
            "package_digest_sha256": self.package_digest_sha256,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class ExternalDeliveryProvider(Protocol):
    """Pluggable external delivery provider contract.

    Implementations must keep dry-run side-effect free.  The built-in review-only
    provider never publishes externally; it only returns a structured blocker so
    callers can verify the handoff contract before wiring a real provider.
    """

    provider_id: str

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        """Publish or plan an external delivery package."""


@dataclass(frozen=True)
class ReviewOnlyExternalDeliveryProvider:
    provider_id: str = "review-only"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_digest = _json_payload_sha256(package.to_dict())
        local_ready = not package.local_errors
        configured = False
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "external_delivery_provider_configured",
                "passed": configured,
                "details": {"provider_id": self.provider_id, "review_only": True},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        status = "planned" if dry_run and local_ready else "blocked"
        recommended_actions = (
            ["configure_external_delivery_provider_or_use_manual_handoff"]
            if blocking_reasons
            else ["review_external_delivery_plan_before_apply"]
        )
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=False,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "external-delivery-provider-contract-baseline",
                "automatic_delivery": False,
                "limitations": [
                    "review_only_provider_does_not_publish",
                    "real_external_delivery_provider_not_configured",
                ],
            },
        )


@dataclass(frozen=True)
class LocalArchiveExternalDeliveryProvider:
    """Filesystem-backed external delivery provider used for controlled releases.

    The provider treats the local archive directory as the external handoff
    boundary.  Dry-run remains side-effect free; apply mode copies already
    delivered local artifacts into a deterministic transaction release
    directory and writes a manifest plus checksum file there.
    """

    archive_root: str | Path | None = None
    provider_id: str = "local-archive"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_digest = _json_payload_sha256(package.to_dict())
        archive_root = self._resolved_archive_root(package)
        release_dir = archive_root / _safe_archive_component(package.transaction_id)
        manifest_path = release_dir / "local-archive-manifest.json"
        checksums_path = release_dir / "local-archive-checksums.json"
        source_items = package.planned_artifacts if dry_run else package.delivered_artifacts
        source_preflight = self._preflight_sources(source_items, dry_run=dry_run)
        local_ready = not package.local_errors
        has_artifacts = bool(source_items)
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "local_archive_has_artifacts_to_archive",
                "passed": has_artifacts,
                "details": {"artifact_count": len(source_items), "dry_run": dry_run},
            },
            {
                "name": "local_archive_sources_available",
                "passed": source_preflight["ok"],
                "details": source_preflight,
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        archived_artifacts: list[dict[str, Any]] = []
        if dry_run:
            status = "planned" if not blocking_reasons else "blocked"
            external_delivery_performed = False
        elif blocking_reasons:
            status = "blocked"
            external_delivery_performed = False
        else:
            release_dir.mkdir(parents=True, exist_ok=True)
            for item in package.delivered_artifacts:
                archived_artifacts.append(self._copy_archive_artifact(item, release_dir))
            checksums_payload = {
                "transaction_id": package.transaction_id,
                "provider_id": self.provider_id,
                "algorithm": "sha256",
                "created_at": created_at,
                "artifacts": [
                    {
                        "artifact_key": item.get("artifact_key"),
                        "archive_path": item.get("archive_path"),
                        "digest_sha256": item.get("digest_sha256"),
                    }
                    for item in archived_artifacts
                ],
            }
            manifest_payload = {
                "transaction_id": package.transaction_id,
                "provider_id": self.provider_id,
                "status": "delivered",
                "created_at": created_at,
                "dry_run": False,
                "archive_root": str(archive_root),
                "archive_release_dir": str(release_dir),
                "package_digest_sha256": package_digest,
                "external_delivery_result_path": result_path,
                "receipt_path": package.receipt_path,
                "transaction_journal_path": package.transaction_journal_path,
                "checksums_path": str(checksums_path),
                "archived_artifacts": archived_artifacts,
                "package_metadata": package.metadata,
            }
            _write_json(checksums_path, checksums_payload)
            _write_json(manifest_path, manifest_payload)
            status = "delivered"
            external_delivery_performed = True
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=external_delivery_performed,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_local_archive_external_delivery_result"]
                if external_delivery_performed
                else ["apply_local_delivery_before_local_archive_publish"]
                if dry_run and not blocking_reasons
                else ["fix_local_archive_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "local-archive-external-delivery-provider-baseline",
                "archive_root": str(archive_root),
                "archive_release_dir": str(release_dir),
                "archive_manifest_path": str(manifest_path),
                "archive_checksums_path": str(checksums_path),
                "archived_artifacts": archived_artifacts,
                "archived_artifact_count": len(archived_artifacts),
                "automatic_delivery": False,
                "publishes_externally": True,
                "transport": "filesystem",
                "limitations": [
                    "filesystem_archive_provider_only",
                    "does_not_upload_to_network_service",
                    "does_not_create_github_release",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
        )

    def _resolved_archive_root(self, package: ExternalDeliveryPackage) -> Path:
        root = Path(self.archive_root) if self.archive_root is not None else Path(package.delivery_root) / "local-archive"
        return root.expanduser().resolve()

    def _preflight_sources(self, items: list[dict[str, Any]], *, dry_run: bool) -> dict[str, Any]:
        missing: list[str] = []
        non_files: list[str] = []
        for item in items:
            path_value = item.get("destination_path")
            if not path_value:
                missing.append("<missing-destination-path>")
                continue
            path = Path(str(path_value)).expanduser()
            if dry_run:
                continue
            if not path.exists():
                missing.append(str(path))
            elif not path.is_file():
                non_files.append(str(path))
        return {
            "ok": not missing and not non_files,
            "missing_paths": missing,
            "non_file_paths": non_files,
            "dry_run": dry_run,
        }

    def _copy_archive_artifact(self, item: dict[str, Any], release_dir: Path) -> dict[str, Any]:
        source_path = Path(str(item["destination_path"])).expanduser().resolve()
        destination_name = _safe_archive_component(source_path.name)
        archive_path = release_dir / destination_name
        shutil.copy2(source_path, archive_path)
        digest = _file_sha256(archive_path)
        return {
            "artifact_key": item.get("artifact_key"),
            "source_delivery_path": str(source_path),
            "archive_path": str(archive_path),
            "size_bytes": archive_path.stat().st_size,
            "digest_sha256": digest,
            "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
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
class BackendManifestInPlacePreflight:
    transaction_id: str
    status: str
    preflight_id: str
    preflight_path: str | None
    source_manifest_path: str | None
    patched_manifest_path: str | None
    dry_run: bool
    in_place_mutation_requested: bool
    in_place_mutation_allowed: bool
    backend_manifest_mutated: bool
    source_manifest_digest_sha256: str | None
    expected_source_manifest_digest_sha256: str | None
    patched_manifest_digest_sha256: str | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "preflight_id": self.preflight_id,
            "preflight_path": self.preflight_path,
            "source_manifest_path": self.source_manifest_path,
            "patched_manifest_path": self.patched_manifest_path,
            "dry_run": self.dry_run,
            "in_place_mutation_requested": self.in_place_mutation_requested,
            "in_place_mutation_allowed": self.in_place_mutation_allowed,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "source_manifest_digest_sha256": self.source_manifest_digest_sha256,
            "expected_source_manifest_digest_sha256": self.expected_source_manifest_digest_sha256,
            "patched_manifest_digest_sha256": self.patched_manifest_digest_sha256,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BackendManifestInPlaceMutation:
    transaction_id: str
    status: str
    mutation_id: str
    mutation_path: str | None
    rollback_path: str | None
    source_manifest_path: str | None
    patched_manifest_path: str | None
    dry_run: bool
    in_place_mutation_requested: bool
    approved: bool
    backend_manifest_mutated: bool
    rollback_checkpoint_written: bool
    source_manifest_digest_sha256: str | None
    expected_source_manifest_digest_sha256: str | None
    patched_manifest_digest_sha256: str | None
    post_mutation_manifest_digest_sha256: str | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "mutation_id": self.mutation_id,
            "mutation_path": self.mutation_path,
            "rollback_path": self.rollback_path,
            "source_manifest_path": self.source_manifest_path,
            "patched_manifest_path": self.patched_manifest_path,
            "dry_run": self.dry_run,
            "in_place_mutation_requested": self.in_place_mutation_requested,
            "approved": self.approved,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "rollback_checkpoint_written": self.rollback_checkpoint_written,
            "source_manifest_digest_sha256": self.source_manifest_digest_sha256,
            "expected_source_manifest_digest_sha256": self.expected_source_manifest_digest_sha256,
            "patched_manifest_digest_sha256": self.patched_manifest_digest_sha256,
            "post_mutation_manifest_digest_sha256": self.post_mutation_manifest_digest_sha256,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BackendManifestRecoveryPreflight:
    transaction_id: str
    status: str
    preflight_id: str
    preflight_path: str | None
    delivery_root: str
    source_manifest_path: str | None
    transaction_journal_path: str | None
    in_place_mutation_path: str | None
    patched_manifest_path: str | None
    rollback_path: str | None
    dry_run: bool
    recovery_preflight_requested: bool
    recovery_available: bool
    backend_manifest_mutated: bool
    backend_manifest_rollback_written: bool
    external_delivery_performed: bool
    cross_run_transaction_committed: bool
    source_manifest_digest_sha256: str | None
    rollback_manifest_digest_sha256: str | None
    journal_transaction_id: str | None
    expected_recovery_transaction_id: str | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "preflight_id": self.preflight_id,
            "preflight_path": self.preflight_path,
            "delivery_root": self.delivery_root,
            "source_manifest_path": self.source_manifest_path,
            "transaction_journal_path": self.transaction_journal_path,
            "in_place_mutation_path": self.in_place_mutation_path,
            "patched_manifest_path": self.patched_manifest_path,
            "rollback_path": self.rollback_path,
            "dry_run": self.dry_run,
            "recovery_preflight_requested": self.recovery_preflight_requested,
            "recovery_available": self.recovery_available,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "backend_manifest_rollback_written": self.backend_manifest_rollback_written,
            "external_delivery_performed": self.external_delivery_performed,
            "cross_run_transaction_committed": self.cross_run_transaction_committed,
            "source_manifest_digest_sha256": self.source_manifest_digest_sha256,
            "rollback_manifest_digest_sha256": self.rollback_manifest_digest_sha256,
            "journal_transaction_id": self.journal_transaction_id,
            "expected_recovery_transaction_id": self.expected_recovery_transaction_id,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BackendManifestRecovery:
    transaction_id: str
    status: str
    recovery_id: str
    recovery_path: str | None
    delivery_root: str
    source_transaction_id: str | None
    source_manifest_path: str | None
    transaction_journal_path: str | None
    recovery_preflight_path: str | None
    rollback_path: str | None
    dry_run: bool
    recovery_requested: bool
    recovered: bool
    backend_manifest_mutated_before_recovery: bool
    external_delivery_performed: bool
    cross_run_transaction_committed: bool
    source_manifest_digest_before_recovery_sha256: str | None
    rollback_manifest_digest_sha256: str | None
    post_recovery_manifest_digest_sha256: str | None
    expected_recovery_transaction_id: str | None
    recovery_preflight_status: str | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "recovery_id": self.recovery_id,
            "recovery_path": self.recovery_path,
            "delivery_root": self.delivery_root,
            "source_transaction_id": self.source_transaction_id,
            "source_manifest_path": self.source_manifest_path,
            "transaction_journal_path": self.transaction_journal_path,
            "recovery_preflight_path": self.recovery_preflight_path,
            "rollback_path": self.rollback_path,
            "dry_run": self.dry_run,
            "recovery_requested": self.recovery_requested,
            "recovered": self.recovered,
            "backend_manifest_mutated_before_recovery": self.backend_manifest_mutated_before_recovery,
            "external_delivery_performed": self.external_delivery_performed,
            "cross_run_transaction_committed": self.cross_run_transaction_committed,
            "source_manifest_digest_before_recovery_sha256": self.source_manifest_digest_before_recovery_sha256,
            "rollback_manifest_digest_sha256": self.rollback_manifest_digest_sha256,
            "post_recovery_manifest_digest_sha256": self.post_recovery_manifest_digest_sha256,
            "expected_recovery_transaction_id": self.expected_recovery_transaction_id,
            "recovery_preflight_status": self.recovery_preflight_status,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BackendManifestTransactionCommit:
    transaction_id: str
    status: str
    commit_id: str
    commit_path: str | None
    delivery_root: str
    source_transaction_id: str | None
    source_manifest_path: str | None
    transaction_journal_path: str | None
    recovery_preflight_path: str | None
    dry_run: bool
    commit_requested: bool
    committed: bool
    backend_manifest_mutated: bool
    backend_manifest_recovery_preflight_passed: bool
    external_delivery_performed: bool
    cross_run_transaction_committed: bool
    source_manifest_digest_sha256: str | None
    expected_commit_transaction_id: str | None
    recovery_preflight_status: str | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "commit_id": self.commit_id,
            "commit_path": self.commit_path,
            "delivery_root": self.delivery_root,
            "source_transaction_id": self.source_transaction_id,
            "source_manifest_path": self.source_manifest_path,
            "transaction_journal_path": self.transaction_journal_path,
            "recovery_preflight_path": self.recovery_preflight_path,
            "dry_run": self.dry_run,
            "commit_requested": self.commit_requested,
            "committed": self.committed,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "backend_manifest_recovery_preflight_passed": self.backend_manifest_recovery_preflight_passed,
            "external_delivery_performed": self.external_delivery_performed,
            "cross_run_transaction_committed": self.cross_run_transaction_committed,
            "source_manifest_digest_sha256": self.source_manifest_digest_sha256,
            "expected_commit_transaction_id": self.expected_commit_transaction_id,
            "recovery_preflight_status": self.recovery_preflight_status,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
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
    external_delivery_result_path: str | None
    external_delivery_idempotency_key: str | None
    manifest_revision_path: str | None
    backend_manifest_mutation_path: str | None
    backend_manifest_patched_path: str | None
    backend_manifest_preflight_path: str | None
    backend_manifest_in_place_mutation_path: str | None
    backend_manifest_rollback_path: str | None
    backend_manifest_recovery_preflight_path: str | None
    backend_manifest_recovery_path: str | None
    backend_manifest_transaction_commit_path: str | None
    backend_manifest_patch_written: bool
    backend_manifest_in_place_preflight_passed: bool
    backend_manifest_recovery_preflight_passed: bool
    backend_manifest_rollback_written: bool
    backend_manifest_mutated: bool
    backend_manifest_recovered: bool
    cross_run_transaction_committed: bool
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
            "external_delivery_result_path": self.external_delivery_result_path,
            "external_delivery_idempotency_key": self.external_delivery_idempotency_key,
            "manifest_revision_path": self.manifest_revision_path,
            "backend_manifest_mutation_path": self.backend_manifest_mutation_path,
            "backend_manifest_patched_path": self.backend_manifest_patched_path,
            "backend_manifest_preflight_path": self.backend_manifest_preflight_path,
            "backend_manifest_in_place_mutation_path": self.backend_manifest_in_place_mutation_path,
            "backend_manifest_rollback_path": self.backend_manifest_rollback_path,
            "backend_manifest_recovery_preflight_path": self.backend_manifest_recovery_preflight_path,
            "backend_manifest_recovery_path": self.backend_manifest_recovery_path,
            "backend_manifest_transaction_commit_path": self.backend_manifest_transaction_commit_path,
            "backend_manifest_patch_written": self.backend_manifest_patch_written,
            "backend_manifest_in_place_preflight_passed": self.backend_manifest_in_place_preflight_passed,
            "backend_manifest_recovery_preflight_passed": self.backend_manifest_recovery_preflight_passed,
            "backend_manifest_rollback_written": self.backend_manifest_rollback_written,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "backend_manifest_recovered": self.backend_manifest_recovered,
            "cross_run_transaction_committed": self.cross_run_transaction_committed,
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
    cross_run_transaction_committed: bool
    manifest_revision_committed: bool
    backend_manifest_patch_written: bool
    backend_manifest_in_place_preflight_passed: bool
    backend_manifest_recovery_preflight_passed: bool
    backend_manifest_rollback_written: bool
    backend_manifest_mutated: bool
    backend_manifest_recovered: bool
    receipt: DeliveryReceipt
    transaction_journal: DeliveryTransactionJournal
    manifest_revision: DeliveryManifestRevision | None
    backend_manifest_mutation: BackendManifestMutation | None
    backend_manifest_in_place_preflight: BackendManifestInPlacePreflight | None
    backend_manifest_in_place_mutation: BackendManifestInPlaceMutation | None
    backend_manifest_recovery_preflight: BackendManifestRecoveryPreflight | None
    backend_manifest_recovery: BackendManifestRecovery | None
    backend_manifest_transaction_commit: BackendManifestTransactionCommit | None
    external_delivery_result: ExternalDeliveryResult | None
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
            "cross_run_transaction_committed": self.cross_run_transaction_committed,
            "manifest_revision_committed": self.manifest_revision_committed,
            "backend_manifest_patch_written": self.backend_manifest_patch_written,
            "backend_manifest_in_place_preflight_passed": self.backend_manifest_in_place_preflight_passed,
            "backend_manifest_recovery_preflight_passed": self.backend_manifest_recovery_preflight_passed,
            "backend_manifest_rollback_written": self.backend_manifest_rollback_written,
            "backend_manifest_mutated": self.backend_manifest_mutated,
            "backend_manifest_recovered": self.backend_manifest_recovered,
            "receipt": self.receipt.to_dict(),
            "transaction_journal": self.transaction_journal.to_dict(),
            "manifest_revision": self.manifest_revision.to_dict() if self.manifest_revision else None,
            "backend_manifest_mutation": self.backend_manifest_mutation.to_dict() if self.backend_manifest_mutation else None,
            "backend_manifest_in_place_preflight": self.backend_manifest_in_place_preflight.to_dict() if self.backend_manifest_in_place_preflight else None,
            "backend_manifest_in_place_mutation": self.backend_manifest_in_place_mutation.to_dict() if self.backend_manifest_in_place_mutation else None,
            "backend_manifest_recovery_preflight": self.backend_manifest_recovery_preflight.to_dict() if self.backend_manifest_recovery_preflight else None,
            "backend_manifest_recovery": self.backend_manifest_recovery.to_dict() if self.backend_manifest_recovery else None,
            "backend_manifest_transaction_commit": self.backend_manifest_transaction_commit.to_dict() if self.backend_manifest_transaction_commit else None,
            "external_delivery_result": self.external_delivery_result.to_dict() if self.external_delivery_result else None,
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
        recovery_only = self._is_recovery_preflight_only(artifacts)
        recovery_apply_only = self._is_backend_manifest_recovery_apply_only(artifacts)
        transaction_commit_only = self._is_cross_run_transaction_commit_only(artifacts)
        delivered: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        if errors:
            status = "failed"
            next_action = "fix_delivery_artifact_inputs"
        elif dry_run:
            status = "planned"
            next_action = "approve_local_delivery_apply"
            skipped = [dict(item, reason="dry_run") for item in planned]
        elif recovery_only:
            status = "preflighted"
            next_action = "review_backend_manifest_recovery_preflight"
        elif recovery_apply_only:
            status = "recovery_requested"
            next_action = "review_backend_manifest_recovery"
        elif transaction_commit_only:
            status = "commit_requested"
            next_action = "review_backend_manifest_transaction_commit"
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

        receipt_path = (
            str(delivery_root / "delivery-receipt.json")
            if self.config.write_receipt and not dry_run and not errors and not recovery_only and not recovery_apply_only and not transaction_commit_only
            else None
        )
        journal_path = (
            str(delivery_root / "delivery-transaction-journal.json")
            if self.config.write_receipt and not dry_run and not errors and not recovery_only and not recovery_apply_only and not transaction_commit_only
            else None
        )
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
        backend_manifest_preflight_path = (
            str(delivery_root / self.config.backend_manifest_preflight_name)
            if self.config.write_receipt and self.config.preflight_backend_manifest_in_place_mutation and not dry_run and not errors
            else None
        )
        backend_manifest_in_place_mutation_path = (
            str(delivery_root / self.config.backend_manifest_in_place_mutation_name)
            if self.config.write_receipt and self.config.approve_backend_manifest_in_place_mutation and not dry_run and not errors
            else None
        )
        backend_manifest_rollback_path = (
            str(delivery_root / self.config.backend_manifest_rollback_name)
            if self.config.write_receipt and self.config.approve_backend_manifest_in_place_mutation and not dry_run and not errors
            else None
        )
        backend_manifest_recovery_preflight_path = (
            str(delivery_root / self.config.backend_manifest_recovery_preflight_name)
            if self.config.write_receipt and self.config.preflight_backend_manifest_recovery and not dry_run and not errors
            else None
        )
        backend_manifest_recovery_path = (
            str(delivery_root / self.config.backend_manifest_recovery_name)
            if self.config.write_receipt and self.config.apply_backend_manifest_recovery and not dry_run and not errors
            else None
        )
        backend_manifest_transaction_commit_path = (
            str(delivery_root / self.config.backend_manifest_transaction_commit_name)
            if self.config.write_receipt and self.config.commit_cross_run_transaction and not dry_run and not errors
            else None
        )
        external_delivery_result_path = (
            str(delivery_root / self.config.external_delivery_result_name)
            if self.config.write_receipt and self.config.request_external_delivery and not dry_run
            else None
        )
        backend_manifest_transaction_commit = self._build_backend_manifest_transaction_commit(
            commit_path=backend_manifest_transaction_commit_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        if transaction_commit_only and backend_manifest_transaction_commit:
            if backend_manifest_transaction_commit.committed:
                status = "committed"
                next_action = "review_committed_transaction_before_external_delivery"
                journal_path = backend_manifest_transaction_commit.transaction_journal_path
            elif backend_manifest_transaction_commit.blocking_reasons:
                status = "blocked"
                next_action = "fix_backend_manifest_transaction_commit_blockers"
            elif dry_run:
                status = "planned"
                next_action = "apply_cross_run_transaction_commit_after_review"
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
            preflight_path=backend_manifest_preflight_path,
            in_place_mutation_path=backend_manifest_in_place_mutation_path,
            rollback_path=backend_manifest_rollback_path,
        )
        patched_backend_manifest = self._build_patched_backend_manifest(backend_manifest_mutation) if backend_manifest_mutation else None
        if backend_manifest_patched_path and backend_manifest_mutation and patched_backend_manifest:
            patched_digest = _json_payload_sha256(patched_backend_manifest)
            backend_manifest_mutation = _replace_backend_manifest_mutation_digest(backend_manifest_mutation, patched_digest)
        backend_manifest_in_place_preflight = self._build_backend_manifest_in_place_preflight(
            mutation=backend_manifest_mutation,
            patched_manifest=patched_backend_manifest,
            preflight_path=backend_manifest_preflight_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        backend_manifest_in_place_mutation = self._apply_backend_manifest_in_place_mutation(
            mutation=backend_manifest_mutation,
            preflight=backend_manifest_in_place_preflight,
            patched_manifest=patched_backend_manifest,
            mutation_path=backend_manifest_in_place_mutation_path,
            rollback_path=backend_manifest_rollback_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        backend_manifest_mutated = bool(backend_manifest_in_place_mutation and backend_manifest_in_place_mutation.backend_manifest_mutated)
        backend_manifest_rollback_written = bool(backend_manifest_in_place_mutation and backend_manifest_in_place_mutation.rollback_checkpoint_written)
        if backend_manifest_mutated and backend_manifest_mutation:
            backend_manifest_mutation = replace(
                backend_manifest_mutation,
                status="in_place_mutated",
                backend_manifest_mutated=True,
                metadata={
                    **backend_manifest_mutation.metadata,
                    "in_place_mutation_id": backend_manifest_in_place_mutation.mutation_id if backend_manifest_in_place_mutation else None,
                },
            )
        backend_manifest_recovery_preflight = self._build_backend_manifest_recovery_preflight(
            preflight_path=backend_manifest_recovery_preflight_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        backend_manifest_recovery = self._apply_backend_manifest_recovery(
            recovery_path=backend_manifest_recovery_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        if recovery_apply_only and backend_manifest_recovery:
            if backend_manifest_recovery.recovered:
                status = "recovered"
                next_action = "review_backend_manifest_recovery_before_transaction_commit"
                journal_path = backend_manifest_recovery.transaction_journal_path
            elif backend_manifest_recovery.blocking_reasons:
                status = "blocked"
                next_action = "fix_backend_manifest_recovery_blockers"
            elif dry_run:
                status = "planned"
                next_action = "apply_backend_manifest_recovery_after_review"
        external_delivery_result = self._run_external_delivery(
            status=status,
            mode=mode.value,
            delivery_root=delivery_root,
            receipt_path=receipt_path,
            journal_path=journal_path,
            result_path=external_delivery_result_path,
            delivered=delivered,
            planned=planned,
            errors=errors,
            dry_run=dry_run,
            created_at=created_at,
        )
        if external_delivery_result and external_delivery_result.result_path:
            external_delivery_result_path = external_delivery_result.result_path
        external_delivery_performed = bool(external_delivery_result and external_delivery_result.external_delivery_performed)
        if external_delivery_result:
            if external_delivery_performed:
                status = "external_delivered"
                next_action = "review_external_delivery_result"
            elif external_delivery_result.blocking_reasons:
                status = "external_delivery_blocked"
                next_action = "fix_external_delivery_blockers"
            elif dry_run:
                next_action = "review_external_delivery_plan_before_apply"
        previous_journal: dict[str, Any] = {}
        if transaction_commit_only and backend_manifest_transaction_commit and backend_manifest_transaction_commit.transaction_journal_path:
            previous_journal_path = Path(backend_manifest_transaction_commit.transaction_journal_path)
            if previous_journal_path.exists():
                previous_journal = _read_json_object(previous_journal_path)
        if recovery_apply_only and backend_manifest_recovery and backend_manifest_recovery.transaction_journal_path:
            previous_journal_path = Path(backend_manifest_recovery.transaction_journal_path)
            if previous_journal_path.exists():
                previous_journal = _read_json_object(previous_journal_path)
        if (
            external_delivery_result
            and external_delivery_result.metadata.get("duplicate_guard_triggered")
            and not previous_journal
        ):
            previous_journal_path = delivery_root / "delivery-transaction-journal.json"
            if previous_journal_path.exists():
                previous_journal = _read_json_object(previous_journal_path)
        cross_run_transaction_committed = bool(
            (backend_manifest_transaction_commit and backend_manifest_transaction_commit.committed)
            or previous_journal.get("cross_run_transaction_committed")
        )
        backend_manifest_recovered = bool(
            (backend_manifest_recovery and backend_manifest_recovery.recovered)
            or previous_journal.get("backend_manifest_recovered")
        )
        journal_limitations = [
            "rollback_is_local_checkpoint_baseline",
            "full_cross_run_manifest_recovery_state_machine_not_implemented",
        ]
        if external_delivery_performed:
            journal_limitations.append("external_delivery_performed_by_configured_provider")
        else:
            journal_limitations.append("does_not_publish_external_delivery")
        if cross_run_transaction_committed:
            journal_limitations.append("external_delivery_still_requires_separate_executor")
        else:
            journal_limitations.append("does_not_commit_cross_run_transaction")
        if backend_manifest_recovered:
            journal_limitations.append("backend_manifest_recovered_from_local_rollback_checkpoint")
        if not backend_manifest_mutated:
            journal_limitations.extend(
                [
                    "does_not_mutate_backend_artifact_manifest_in_place",
                    "backend_manifest_patch_is_local_copy_only",
                    "backend_manifest_in_place_preflight_only",
                ]
            )
        journal = DeliveryTransactionJournal(
            transaction_id=_journal_str(previous_journal, "transaction_id", self.config.transaction_id) or self.config.transaction_id,
            status=status,
            journal_path=journal_path,
            manifest_revision_committed=_journal_bool(
                previous_journal,
                "manifest_revision_committed",
                bool(manifest_revision and manifest_revision.committed),
            ),
            filesystem_artifact_mutated=_journal_bool(previous_journal, "filesystem_artifact_mutated", bool(delivered)),
            external_delivery_performed=_journal_bool(previous_journal, "external_delivery_performed", external_delivery_performed),
            rollback_available=_journal_bool(previous_journal, "rollback_available", bool(delivered)),
            external_delivery_result_path=_journal_str(previous_journal, "external_delivery_result_path", external_delivery_result_path),
            external_delivery_idempotency_key=_journal_str(
                previous_journal,
                "external_delivery_idempotency_key",
                self._external_delivery_idempotency_key() if self.config.request_external_delivery else None,
            ),
            manifest_revision_path=_journal_str(previous_journal, "manifest_revision_path", manifest_revision_path),
            backend_manifest_mutation_path=_journal_str(previous_journal, "backend_manifest_mutation_path", backend_manifest_mutation_path),
            backend_manifest_patched_path=_journal_str(previous_journal, "backend_manifest_patched_path", backend_manifest_patched_path),
            backend_manifest_preflight_path=_journal_str(previous_journal, "backend_manifest_preflight_path", backend_manifest_preflight_path),
            backend_manifest_in_place_mutation_path=_journal_str(
                previous_journal,
                "backend_manifest_in_place_mutation_path",
                backend_manifest_in_place_mutation_path,
            ),
            backend_manifest_rollback_path=_journal_str(previous_journal, "backend_manifest_rollback_path", backend_manifest_rollback_path),
            backend_manifest_recovery_preflight_path=_journal_str(
                previous_journal,
                "backend_manifest_recovery_preflight_path",
                backend_manifest_recovery.recovery_preflight_path
                if backend_manifest_recovery and backend_manifest_recovery.recovery_preflight_path
                else (
                backend_manifest_transaction_commit.recovery_preflight_path
                if backend_manifest_transaction_commit and backend_manifest_transaction_commit.recovery_preflight_path
                else backend_manifest_recovery_preflight_path
                ),
            ),
            backend_manifest_recovery_path=_journal_str(
                previous_journal,
                "backend_manifest_recovery_path",
                backend_manifest_recovery_path if backend_manifest_recovery and backend_manifest_recovery.recovered else None,
            ),
            backend_manifest_transaction_commit_path=_journal_str(
                previous_journal,
                "backend_manifest_transaction_commit_path",
                backend_manifest_transaction_commit_path if backend_manifest_transaction_commit and backend_manifest_transaction_commit.committed else None,
            ),
            backend_manifest_patch_written=_journal_bool(
                previous_journal,
                "backend_manifest_patch_written",
                bool(backend_manifest_mutation and backend_manifest_mutation.backend_manifest_patch_written),
            ),
            backend_manifest_in_place_preflight_passed=_journal_bool(
                previous_journal,
                "backend_manifest_in_place_preflight_passed",
                bool(backend_manifest_in_place_preflight and backend_manifest_in_place_preflight.in_place_mutation_allowed),
            ),
            backend_manifest_recovery_preflight_passed=_journal_bool(
                previous_journal,
                "backend_manifest_recovery_preflight_passed",
                bool(backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.status in {"ready_for_review", "no_recovery_required"}),
            ),
            backend_manifest_rollback_written=_journal_bool(previous_journal, "backend_manifest_rollback_written", backend_manifest_rollback_written),
            backend_manifest_mutated=_journal_bool(previous_journal, "backend_manifest_mutated", backend_manifest_mutated),
            backend_manifest_recovered=backend_manifest_recovered,
            cross_run_transaction_committed=cross_run_transaction_committed,
            entries=_journal_entries(previous_journal)
            or [
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
                "limitations": journal_limitations,
            },
        )
        if receipt_path:
            _write_json(Path(receipt_path), receipt.to_dict())
        if manifest_revision_path and manifest_revision:
            _write_json(Path(manifest_revision_path), manifest_revision.to_dict())
        if backend_manifest_patched_path and backend_manifest_mutation:
            _write_json(Path(backend_manifest_patched_path), patched_backend_manifest or self._build_patched_backend_manifest(backend_manifest_mutation))
        if backend_manifest_mutation_path and backend_manifest_mutation:
            _write_json(Path(backend_manifest_mutation_path), backend_manifest_mutation.to_dict())
        if backend_manifest_preflight_path and backend_manifest_in_place_preflight:
            _write_json(Path(backend_manifest_preflight_path), backend_manifest_in_place_preflight.to_dict())
        if backend_manifest_in_place_mutation_path and backend_manifest_in_place_mutation:
            _write_json(Path(backend_manifest_in_place_mutation_path), backend_manifest_in_place_mutation.to_dict())
        if backend_manifest_recovery_preflight_path and backend_manifest_recovery_preflight:
            _write_json(Path(backend_manifest_recovery_preflight_path), backend_manifest_recovery_preflight.to_dict())
        if backend_manifest_recovery_path and backend_manifest_recovery:
            _write_json(Path(backend_manifest_recovery_path), backend_manifest_recovery.to_dict())
        if backend_manifest_transaction_commit_path and backend_manifest_transaction_commit:
            _write_json(Path(backend_manifest_transaction_commit_path), backend_manifest_transaction_commit.to_dict())
        if external_delivery_result_path and external_delivery_result:
            _write_json(Path(external_delivery_result_path), external_delivery_result.to_dict())
        should_write_journal = bool(journal_path) and (
            (not transaction_commit_only and not recovery_apply_only)
            or bool(backend_manifest_transaction_commit and backend_manifest_transaction_commit.committed)
            or bool(backend_manifest_recovery and backend_manifest_recovery.recovered)
        )
        if should_write_journal:
            _write_json(Path(journal_path), journal.to_dict())
        if backend_manifest_mutated:
            next_action = "review_backend_manifest_in_place_mutation_before_cross_run_commit"
        elif backend_manifest_in_place_mutation and backend_manifest_in_place_mutation.blocking_reasons:
            next_action = "fix_backend_manifest_in_place_mutation_blockers"
        elif backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.status == "ready_for_review":
            next_action = "review_backend_manifest_recovery_preflight_before_cross_run_commit"
        elif backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.blocking_reasons:
            next_action = "fix_backend_manifest_recovery_preflight_blockers"
        return DeliveryExecutionResult(
            status=status,
            mode=mode.value,
            transaction_id=self.config.transaction_id,
            dry_run=dry_run,
            delivery_allowed=not bool(errors)
            and not bool(external_delivery_result and external_delivery_result.blocking_reasons),
            filesystem_artifact_mutated=bool(delivered),
            external_delivery_performed=external_delivery_performed,
            cross_run_transaction_committed=cross_run_transaction_committed,
            manifest_revision_committed=bool(manifest_revision and manifest_revision.committed),
            backend_manifest_patch_written=bool(backend_manifest_mutation and backend_manifest_mutation.backend_manifest_patch_written),
            backend_manifest_in_place_preflight_passed=bool(
                backend_manifest_in_place_preflight and backend_manifest_in_place_preflight.in_place_mutation_allowed
            ),
            backend_manifest_recovery_preflight_passed=bool(
                backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.status in {"ready_for_review", "no_recovery_required"}
            ),
            backend_manifest_rollback_written=backend_manifest_rollback_written,
            backend_manifest_mutated=backend_manifest_mutated,
            backend_manifest_recovered=backend_manifest_recovered,
            receipt=receipt,
            transaction_journal=journal,
            manifest_revision=manifest_revision,
            backend_manifest_mutation=backend_manifest_mutation,
            backend_manifest_in_place_preflight=backend_manifest_in_place_preflight,
            backend_manifest_in_place_mutation=backend_manifest_in_place_mutation,
            backend_manifest_recovery_preflight=backend_manifest_recovery_preflight,
            backend_manifest_recovery=backend_manifest_recovery,
            backend_manifest_transaction_commit=backend_manifest_transaction_commit,
            external_delivery_result=external_delivery_result,
            planned_artifacts=planned,
            errors=errors,
            next_action=next_action,
        )

    def _run_external_delivery(
        self,
        *,
        status: str,
        mode: str,
        delivery_root: Path,
        receipt_path: str | None,
        journal_path: str | None,
        result_path: str | None,
        delivered: list[dict[str, Any]],
        planned: list[dict[str, Any]],
        errors: list[str],
        dry_run: bool,
        created_at: str,
    ) -> ExternalDeliveryResult | None:
        if not self.config.request_external_delivery:
            return None
        configured_provider_id = (
            self.config.external_delivery_provider.provider_id
            if self.config.external_delivery_provider is not None
            else self.config.external_delivery_provider_id
        )
        duplicate_guard = self._build_external_delivery_duplicate_guard(
            delivery_root=delivery_root,
            result_path=result_path,
            provider_id=configured_provider_id,
            dry_run=dry_run,
            created_at=created_at,
        )
        if duplicate_guard is not None:
            return duplicate_guard
        provider = self.config.external_delivery_provider
        if provider is None:
            registry = self.config.external_delivery_provider_registry
            if registry is None:
                from reverse_deepagent.delivery.registry import build_default_external_delivery_provider_registry

                registry = build_default_external_delivery_provider_registry()
            provider = registry.create(
                self.config.external_delivery_provider_id,
                **self.config.external_delivery_provider_config,
            )
        package = ExternalDeliveryPackage(
            transaction_id=self.config.transaction_id,
            status=status,
            mode=mode,
            delivery_root=str(delivery_root),
            receipt_path=receipt_path,
            transaction_journal_path=journal_path,
            external_delivery_result_path=result_path,
            delivered_artifacts=delivered,
            planned_artifacts=planned,
            local_errors=errors,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "provider_id": provider.provider_id,
                "external_delivery_idempotency_key": self._external_delivery_idempotency_key(),
                "allow_duplicate_external_delivery": self.config.allow_duplicate_external_delivery,
                "automatic_delivery": False,
            },
        )
        return provider.deliver(
            package,
            dry_run=dry_run,
            result_path=result_path,
            created_at=created_at,
        )

    def _external_delivery_idempotency_key(self) -> str:
        return self.config.external_delivery_idempotency_key or self.config.transaction_id

    def _build_external_delivery_duplicate_guard(
        self,
        *,
        delivery_root: Path,
        result_path: str | None,
        provider_id: str,
        dry_run: bool,
        created_at: str,
    ) -> ExternalDeliveryResult | None:
        if self.config.allow_duplicate_external_delivery:
            return None
        idempotency_key = self._external_delivery_idempotency_key()
        journal_path = delivery_root / "delivery-transaction-journal.json"
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        journal_result_path = _resolve_record_path(journal.get("external_delivery_result_path"), delivery_root)
        configured_result_path = Path(result_path).expanduser().resolve() if result_path else None
        candidate_result_paths = [
            path for path in (journal_result_path, configured_result_path) if path is not None and path.exists()
        ]
        prior_result_path = candidate_result_paths[0] if candidate_result_paths else None
        prior_result = _read_json_object(prior_result_path) if prior_result_path else {}
        journal_performed = bool(journal.get("external_delivery_performed"))
        result_performed = bool(prior_result.get("external_delivery_performed"))
        if not journal_performed and not result_performed:
            return None
        previous_metadata = prior_result.get("metadata") if isinstance(prior_result.get("metadata"), dict) else {}
        journal_metadata = journal.get("metadata") if isinstance(journal.get("metadata"), dict) else {}
        previous_idempotency_key = (
            journal.get("external_delivery_idempotency_key")
            or journal_metadata.get("external_delivery_idempotency_key")
            or previous_metadata.get("external_delivery_idempotency_key")
            or journal.get("transaction_id")
            or prior_result.get("transaction_id")
        )
        guard_path = (
            str((delivery_root / self.config.external_delivery_duplicate_guard_name).resolve())
            if result_path and not dry_run
            else result_path
        )
        details = {
            "idempotency_key": idempotency_key,
            "previous_idempotency_key": previous_idempotency_key,
            "previous_transaction_id": journal.get("transaction_id") or prior_result.get("transaction_id"),
            "previous_provider_id": prior_result.get("provider_id"),
            "previous_journal_path": str(journal_path) if journal_exists else None,
            "previous_result_path": str(prior_result_path) if prior_result_path else None,
            "journal_external_delivery_performed": journal_performed,
            "result_external_delivery_performed": result_performed,
        }
        checks = [
            {
                "name": "external_delivery_not_previously_performed",
                "passed": False,
                "details": details,
            },
            {
                "name": "duplicate_external_delivery_not_allowed",
                "passed": False,
                "details": {"allow_duplicate_external_delivery": False},
            },
            {
                "name": "provider_factory_not_invoked_by_duplicate_guard",
                "passed": True,
                "details": {"provider_id": provider_id},
            },
        ]
        return ExternalDeliveryResult(
            transaction_id=self.config.transaction_id,
            status="blocked",
            provider_id=provider_id,
            result_path=guard_path,
            delivery_root=str(delivery_root),
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=False,
            package_digest_sha256=_json_payload_sha256(details),
            checks=checks,
            blocking_reasons=[check["name"] for check in checks if not check["passed"]],
            recommended_actions=[
                "review_previous_external_delivery_before_retry",
                "set_allow_duplicate_external_delivery_only_after_manual_review",
            ],
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "external-delivery-idempotency-guard-baseline",
                "external_delivery_idempotency_key": idempotency_key,
                "allow_duplicate_external_delivery": False,
                "duplicate_guard_triggered": True,
                "provider_factory_invoked": False,
                "automatic_delivery": False,
                "limitations": [
                    "duplicate_guard_blocks_provider_invocation",
                    "does_not_publish_external_delivery",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
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
        preflight_path: str | None,
        in_place_mutation_path: str | None,
        rollback_path: str | None,
    ) -> BackendManifestMutation | None:
        if not (self.config.commit_backend_manifest_mutation or self.config.preflight_backend_manifest_in_place_mutation):
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
            preflight_path=preflight_path,
            in_place_mutation_path=in_place_mutation_path,
            rollback_path=rollback_path,
        )
        patch_written = (
            self.config.commit_backend_manifest_mutation
            and bool(delivered)
            and not dry_run
            and status == "delivered"
            and mutation_path is not None
            and patched_manifest_path is not None
        )
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
        preflight_path: str | None,
        in_place_mutation_path: str | None,
        rollback_path: str | None,
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
        if self.config.preflight_backend_manifest_in_place_mutation:
            synthetic_paths.append(
                (
                    "workspace_backend_artifact_manifest_preflight",
                    preflight_path or str(delivery_root / self.config.backend_manifest_preflight_name),
                )
            )
        if self.config.approve_backend_manifest_in_place_mutation:
            synthetic_paths.extend(
                [
                    (
                        "workspace_backend_artifact_manifest_in_place_mutation",
                        in_place_mutation_path or str(delivery_root / self.config.backend_manifest_in_place_mutation_name),
                    ),
                    (
                        "workspace_backend_artifact_manifest_rollback",
                        rollback_path or str(delivery_root / self.config.backend_manifest_rollback_name),
                    ),
                ]
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

    def _build_backend_manifest_in_place_preflight(
        self,
        *,
        mutation: BackendManifestMutation | None,
        patched_manifest: dict[str, Any] | None,
        preflight_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> BackendManifestInPlacePreflight | None:
        if not self.config.preflight_backend_manifest_in_place_mutation:
            return None
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
        source_digest = _file_sha256(source_manifest_path) if source_manifest_path and source_manifest_exists else None
        patched_digest = _json_payload_sha256(patched_manifest) if patched_manifest is not None else None
        expected_digest = self.config.expected_backend_manifest_digest_sha256
        duplicate_keys = _duplicate_artifact_keys(patched_manifest.get("entries", []) if patched_manifest else [])
        checks = [
            {
                "name": "source_manifest_exists",
                "passed": source_manifest_exists,
                "details": {"source_manifest_path": str(source_manifest_path) if source_manifest_path else None},
            },
            {
                "name": "expected_source_manifest_digest_matches",
                "passed": expected_digest is None or expected_digest == source_digest,
                "details": {"expected": expected_digest, "actual": source_digest},
            },
            {
                "name": "backend_manifest_patch_available",
                "passed": bool(mutation and mutation.backend_manifest_patch_written),
                "details": {
                    "mutation_id": mutation.mutation_id if mutation else None,
                    "patched_manifest_path": mutation.patched_manifest_path if mutation else None,
                },
            },
            {
                "name": "patched_manifest_has_no_duplicate_artifact_keys",
                "passed": not duplicate_keys,
                "details": {"duplicate_artifact_keys": duplicate_keys},
            },
            {
                "name": "preflight_does_not_mutate_source_manifest",
                "passed": True,
                "details": {"backend_manifest_mutated": False},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        if dry_run:
            status = "planned"
            in_place_allowed = False
        elif blocking_reasons:
            status = "blocked"
            in_place_allowed = False
        else:
            status = "passed"
            in_place_allowed = True
        return BackendManifestInPlacePreflight(
            transaction_id=self.config.transaction_id,
            status=status,
            preflight_id=f"backend-manifest-in-place-preflight-{self.config.transaction_id}",
            preflight_path=preflight_path,
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            patched_manifest_path=mutation.patched_manifest_path if mutation else None,
            dry_run=dry_run,
            in_place_mutation_requested=True,
            in_place_mutation_allowed=in_place_allowed,
            backend_manifest_mutated=False,
            source_manifest_digest_sha256=source_digest,
            expected_source_manifest_digest_sha256=expected_digest,
            patched_manifest_digest_sha256=patched_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-manifest-in-place-mutation-preflight-baseline",
                "limitations": [
                    "preflight_only",
                    "does_not_mutate_backend_artifact_manifest_in_place",
                    "does_not_commit_cross_run_transaction",
                    "cross_run_manifest_recovery_not_implemented",
                ],
            },
        )

    def _apply_backend_manifest_in_place_mutation(
        self,
        *,
        mutation: BackendManifestMutation | None,
        preflight: BackendManifestInPlacePreflight | None,
        patched_manifest: dict[str, Any] | None,
        mutation_path: str | None,
        rollback_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> BackendManifestInPlaceMutation | None:
        if not self.config.approve_backend_manifest_in_place_mutation:
            return None
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
        source_digest = _file_sha256(source_manifest_path) if source_manifest_path and source_manifest_exists else None
        expected_digest = self.config.expected_backend_manifest_digest_sha256
        patched_digest = _json_payload_sha256(patched_manifest) if patched_manifest is not None else None
        checks = [
            {
                "name": "approval_present",
                "passed": self.config.approve_backend_manifest_in_place_mutation,
                "details": {"approved": self.config.approve_backend_manifest_in_place_mutation},
            },
            {
                "name": "apply_mode_selected",
                "passed": not dry_run and self.config.mode == DeliveryExecutionMode.APPLY,
                "details": {"mode": self.config.mode.value, "dry_run": dry_run},
            },
            {
                "name": "source_manifest_exists",
                "passed": source_manifest_exists,
                "details": {"source_manifest_path": str(source_manifest_path) if source_manifest_path else None},
            },
            {
                "name": "expected_source_manifest_digest_provided",
                "passed": bool(expected_digest),
                "details": {"expected": expected_digest},
            },
            {
                "name": "expected_source_manifest_digest_matches_current",
                "passed": bool(expected_digest) and expected_digest == source_digest,
                "details": {"expected": expected_digest, "actual": source_digest},
            },
            {
                "name": "backend_manifest_patch_available",
                "passed": bool(mutation and mutation.backend_manifest_patch_written and patched_manifest is not None),
                "details": {
                    "mutation_id": mutation.mutation_id if mutation else None,
                    "patched_manifest_path": mutation.patched_manifest_path if mutation else None,
                },
            },
            {
                "name": "preflight_passed",
                "passed": bool(preflight and preflight.in_place_mutation_allowed),
                "details": {"preflight_id": preflight.preflight_id if preflight else None, "status": preflight.status if preflight else None},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        backend_manifest_mutated = False
        rollback_checkpoint_written = False
        post_mutation_digest: str | None = None
        if dry_run:
            status = "planned"
        elif blocking_reasons:
            status = "blocked"
        else:
            if source_manifest_path is None or rollback_path is None or patched_manifest is None:
                raise ValueError("backend manifest in-place mutation requires source manifest, rollback path, and patched manifest")
            rollback_target = Path(rollback_path)
            rollback_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_manifest_path, rollback_target)
            rollback_checkpoint_written = True
            source_payload = _mark_backend_manifest_in_place_mutated(
                patched_manifest,
                transaction_id=self.config.transaction_id,
                mutation_id=mutation.mutation_id if mutation else f"backend-manifest-mutation-{self.config.transaction_id}",
                in_place_mutation_id=f"backend-manifest-in-place-mutation-{self.config.transaction_id}",
                rollback_path=str(rollback_target),
            )
            _write_json(source_manifest_path, source_payload)
            post_mutation_digest = _file_sha256(source_manifest_path)
            backend_manifest_mutated = True
            status = "applied"
        return BackendManifestInPlaceMutation(
            transaction_id=self.config.transaction_id,
            status=status,
            mutation_id=f"backend-manifest-in-place-mutation-{self.config.transaction_id}",
            mutation_path=mutation_path,
            rollback_path=rollback_path,
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            patched_manifest_path=mutation.patched_manifest_path if mutation else None,
            dry_run=dry_run,
            in_place_mutation_requested=True,
            approved=self.config.approve_backend_manifest_in_place_mutation,
            backend_manifest_mutated=backend_manifest_mutated,
            rollback_checkpoint_written=rollback_checkpoint_written,
            source_manifest_digest_sha256=source_digest,
            expected_source_manifest_digest_sha256=expected_digest,
            patched_manifest_digest_sha256=patched_digest,
            post_mutation_manifest_digest_sha256=post_mutation_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-manifest-in-place-mutation-explicit-review-baseline",
                "external_delivery_performed": False,
                "cross_run_transaction_committed": False,
                "limitations": [
                    "explicit_review_only",
                    "does_not_publish_external_delivery",
                    "does_not_commit_cross_run_transaction",
                    "rollback_checkpoint_is_local_baseline",
                    "cross_run_manifest_recovery_not_implemented",
                ],
            },
        )

    def _build_backend_manifest_recovery_preflight(
        self,
        *,
        preflight_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> BackendManifestRecoveryPreflight | None:
        if not self.config.preflight_backend_manifest_recovery:
            return None
        delivery_root = self.config.resolved_delivery_root()
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
        source_digest = _file_sha256(source_manifest_path) if source_manifest_path and source_manifest_exists else None
        journal_path = delivery_root / "delivery-transaction-journal.json"
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        journal_transaction_id = str(journal["transaction_id"]) if journal.get("transaction_id") is not None else None
        backend_manifest_mutated = bool(journal.get("backend_manifest_mutated"))
        backend_manifest_rollback_written = bool(journal.get("backend_manifest_rollback_written"))
        external_delivery_performed = bool(journal.get("external_delivery_performed"))
        cross_run_transaction_committed = bool(journal.get("cross_run_transaction_committed", False))
        in_place_mutation_path = _resolve_record_path(journal.get("backend_manifest_in_place_mutation_path"), delivery_root)
        patched_manifest_path = _resolve_record_path(journal.get("backend_manifest_patched_path"), delivery_root)
        rollback_path = _resolve_record_path(journal.get("backend_manifest_rollback_path"), delivery_root)
        if backend_manifest_mutated and rollback_path is None:
            rollback_path = (delivery_root / self.config.backend_manifest_rollback_name).resolve()
        if backend_manifest_mutated and in_place_mutation_path is None:
            in_place_mutation_path = (delivery_root / self.config.backend_manifest_in_place_mutation_name).resolve()
        mutation_record_exists = bool(in_place_mutation_path and in_place_mutation_path.exists())
        mutation_record = _read_json_object(in_place_mutation_path) if mutation_record_exists else {}
        rollback_exists = bool(rollback_path and rollback_path.exists())
        rollback_digest = _file_sha256(rollback_path) if rollback_path and rollback_exists else None
        patched_exists = bool(patched_manifest_path and patched_manifest_path.exists())
        expected_transaction_id = self.config.expected_recovery_transaction_id
        pre_mutation_digest = mutation_record.get("source_manifest_digest_sha256") if isinstance(mutation_record.get("source_manifest_digest_sha256"), str) else None
        post_mutation_digest = (
            mutation_record.get("post_mutation_manifest_digest_sha256")
            if isinstance(mutation_record.get("post_mutation_manifest_digest_sha256"), str)
            else None
        )
        patch_written = bool(journal.get("backend_manifest_patch_written"))
        checks = [
            {
                "name": "source_manifest_exists",
                "passed": source_manifest_exists,
                "details": {"source_manifest_path": str(source_manifest_path) if source_manifest_path else None},
            },
            {
                "name": "transaction_journal_exists",
                "passed": journal_exists,
                "details": {"transaction_journal_path": str(journal_path)},
            },
            {
                "name": "expected_recovery_transaction_matches",
                "passed": expected_transaction_id is None or expected_transaction_id == journal_transaction_id,
                "details": {"expected": expected_transaction_id, "actual": journal_transaction_id},
            },
            {
                "name": "journal_reports_no_external_delivery",
                "passed": not external_delivery_performed,
                "details": {"external_delivery_performed": external_delivery_performed},
            },
            {
                "name": "journal_reports_no_cross_run_commit",
                "passed": not cross_run_transaction_committed,
                "details": {"cross_run_transaction_committed": cross_run_transaction_committed},
            },
            {
                "name": "patched_manifest_exists_if_patch_written",
                "passed": not patch_written or patched_exists,
                "details": {"patch_written": patch_written, "patched_manifest_path": str(patched_manifest_path) if patched_manifest_path else None},
            },
            {
                "name": "in_place_mutation_record_exists_if_mutated",
                "passed": not backend_manifest_mutated or mutation_record_exists,
                "details": {
                    "backend_manifest_mutated": backend_manifest_mutated,
                    "in_place_mutation_path": str(in_place_mutation_path) if in_place_mutation_path else None,
                },
            },
            {
                "name": "rollback_checkpoint_exists_if_mutated",
                "passed": not backend_manifest_mutated or (backend_manifest_rollback_written and rollback_exists),
                "details": {
                    "backend_manifest_rollback_written": backend_manifest_rollback_written,
                    "rollback_path": str(rollback_path) if rollback_path else None,
                },
            },
            {
                "name": "rollback_matches_pre_mutation_digest_if_mutated",
                "passed": not backend_manifest_mutated or bool(pre_mutation_digest and rollback_digest == pre_mutation_digest),
                "details": {"expected": pre_mutation_digest, "actual": rollback_digest},
            },
            {
                "name": "source_matches_post_mutation_digest_if_mutated",
                "passed": not backend_manifest_mutated or bool(post_mutation_digest and source_digest == post_mutation_digest),
                "details": {"expected": post_mutation_digest, "actual": source_digest},
            },
            {
                "name": "recovery_preflight_does_not_mutate_source_manifest",
                "passed": True,
                "details": {"backend_manifest_mutated_by_recovery_preflight": False},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        if dry_run:
            status = "planned"
            recovery_available = False
            recommended_actions = ["run_apply_recovery_preflight_to_write_review_record"]
        elif blocking_reasons:
            status = "blocked"
            recovery_available = False
            recommended_actions = ["inspect_delivery_transaction_journal", "repair_or_restore_manifest_inputs_before_commit"]
        elif backend_manifest_mutated:
            status = "ready_for_review"
            recovery_available = True
            recommended_actions = ["review_rollback_checkpoint_before_physical_recovery", "continue_to_cross_run_transaction_commit_preflight"]
        else:
            status = "no_recovery_required"
            recovery_available = False
            recommended_actions = ["continue_to_cross_run_transaction_commit_preflight"]
        return BackendManifestRecoveryPreflight(
            transaction_id=self.config.transaction_id,
            status=status,
            preflight_id=f"backend-manifest-recovery-preflight-{self.config.transaction_id}",
            preflight_path=preflight_path,
            delivery_root=str(delivery_root),
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            transaction_journal_path=str(journal_path),
            in_place_mutation_path=str(in_place_mutation_path) if in_place_mutation_path else None,
            patched_manifest_path=str(patched_manifest_path) if patched_manifest_path else None,
            rollback_path=str(rollback_path) if rollback_path else None,
            dry_run=dry_run,
            recovery_preflight_requested=True,
            recovery_available=recovery_available,
            backend_manifest_mutated=backend_manifest_mutated,
            backend_manifest_rollback_written=backend_manifest_rollback_written,
            external_delivery_performed=external_delivery_performed,
            cross_run_transaction_committed=cross_run_transaction_committed,
            source_manifest_digest_sha256=source_digest,
            rollback_manifest_digest_sha256=rollback_digest,
            journal_transaction_id=journal_transaction_id,
            expected_recovery_transaction_id=expected_transaction_id,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-manifest-cross-run-recovery-preflight-baseline",
                "external_delivery_performed": False,
                "cross_run_transaction_committed": False,
                "limitations": [
                    "preflight_only",
                    "does_not_restore_manifest",
                    "does_not_publish_external_delivery",
                    "does_not_commit_cross_run_transaction",
                    "cross_run_manifest_recovery_state_machine_not_implemented",
                ],
            },
        )

    def _build_backend_manifest_transaction_commit(
        self,
        *,
        commit_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> BackendManifestTransactionCommit | None:
        if not self.config.commit_cross_run_transaction:
            return None
        delivery_root = self.config.resolved_delivery_root()
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
        source_digest = _file_sha256(source_manifest_path) if source_manifest_path and source_manifest_exists else None
        journal_path = delivery_root / "delivery-transaction-journal.json"
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        source_transaction_id = str(journal["transaction_id"]) if journal.get("transaction_id") is not None else None
        expected_transaction_id = self.config.expected_commit_transaction_id
        backend_manifest_mutated = bool(journal.get("backend_manifest_mutated"))
        external_delivery_performed = bool(journal.get("external_delivery_performed"))
        already_committed = bool(journal.get("cross_run_transaction_committed"))
        recovery_preflight_path = _resolve_record_path(journal.get("backend_manifest_recovery_preflight_path"), delivery_root)
        if recovery_preflight_path is None:
            recovery_preflight_path = (delivery_root / self.config.backend_manifest_recovery_preflight_name).resolve()
        recovery_preflight_exists = recovery_preflight_path.exists()
        recovery_preflight = _read_json_object(recovery_preflight_path) if recovery_preflight_exists else {}
        recovery_preflight_status = (
            str(recovery_preflight["status"]) if recovery_preflight.get("status") is not None else None
        )
        recovery_preflight_passed = recovery_preflight_status in {"ready_for_review", "no_recovery_required"}
        recovery_journal_transaction_id = (
            str(recovery_preflight["journal_transaction_id"])
            if recovery_preflight.get("journal_transaction_id") is not None
            else None
        )
        recovery_source_digest = (
            recovery_preflight.get("source_manifest_digest_sha256")
            if isinstance(recovery_preflight.get("source_manifest_digest_sha256"), str)
            else None
        )
        rollback_path = _resolve_record_path(journal.get("backend_manifest_rollback_path"), delivery_root)
        if backend_manifest_mutated and rollback_path is None:
            rollback_path = (delivery_root / self.config.backend_manifest_rollback_name).resolve()
        rollback_exists = bool(rollback_path and rollback_path.exists())
        checks = [
            {
                "name": "source_manifest_exists",
                "passed": source_manifest_exists,
                "details": {"source_manifest_path": str(source_manifest_path) if source_manifest_path else None},
            },
            {
                "name": "transaction_journal_exists",
                "passed": journal_exists,
                "details": {"transaction_journal_path": str(journal_path)},
            },
            {
                "name": "expected_commit_transaction_matches",
                "passed": expected_transaction_id is None or expected_transaction_id == source_transaction_id,
                "details": {"expected": expected_transaction_id, "actual": source_transaction_id},
            },
            {
                "name": "journal_reports_no_external_delivery",
                "passed": not external_delivery_performed,
                "details": {"external_delivery_performed": external_delivery_performed},
            },
            {
                "name": "journal_not_already_cross_run_committed",
                "passed": not already_committed,
                "details": {"cross_run_transaction_committed": already_committed},
            },
            {
                "name": "recovery_preflight_exists",
                "passed": recovery_preflight_exists,
                "details": {"recovery_preflight_path": str(recovery_preflight_path)},
            },
            {
                "name": "recovery_preflight_status_allows_commit",
                "passed": recovery_preflight_passed,
                "details": {"status": recovery_preflight_status},
            },
            {
                "name": "recovery_preflight_transaction_matches_journal",
                "passed": recovery_journal_transaction_id == source_transaction_id,
                "details": {"recovery_journal_transaction_id": recovery_journal_transaction_id, "journal_transaction_id": source_transaction_id},
            },
            {
                "name": "recovery_preflight_source_digest_matches_current",
                "passed": bool(source_digest and recovery_source_digest == source_digest),
                "details": {"expected": recovery_source_digest, "actual": source_digest},
            },
            {
                "name": "rollback_checkpoint_exists_if_mutated",
                "passed": not backend_manifest_mutated or rollback_exists,
                "details": {"backend_manifest_mutated": backend_manifest_mutated, "rollback_path": str(rollback_path) if rollback_path else None},
            },
            {
                "name": "transaction_commit_does_not_publish_external_delivery",
                "passed": True,
                "details": {"external_delivery_performed_by_commit": False},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        if dry_run:
            status = "planned"
            committed = False
            recommended_actions = ["run_apply_cross_run_transaction_commit_after_review"]
        elif blocking_reasons:
            status = "blocked"
            committed = False
            recommended_actions = ["inspect_recovery_preflight_and_transaction_journal_before_commit"]
        else:
            status = "committed"
            committed = True
            recommended_actions = ["review_committed_transaction_before_external_delivery"]
        return BackendManifestTransactionCommit(
            transaction_id=self.config.transaction_id,
            status=status,
            commit_id=f"backend-manifest-transaction-commit-{self.config.transaction_id}",
            commit_path=commit_path,
            delivery_root=str(delivery_root),
            source_transaction_id=source_transaction_id,
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            transaction_journal_path=str(journal_path),
            recovery_preflight_path=str(recovery_preflight_path),
            dry_run=dry_run,
            commit_requested=True,
            committed=committed,
            backend_manifest_mutated=backend_manifest_mutated,
            backend_manifest_recovery_preflight_passed=recovery_preflight_passed,
            external_delivery_performed=False,
            cross_run_transaction_committed=committed,
            source_manifest_digest_sha256=source_digest,
            expected_commit_transaction_id=expected_transaction_id,
            recovery_preflight_status=recovery_preflight_status,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-manifest-cross-run-transaction-commit-baseline",
                "external_delivery_performed": False,
                "cross_run_transaction_committed": committed,
                "limitations": [
                    "local_filesystem_transaction_commit_only",
                    "does_not_publish_external_delivery",
                    "does_not_restore_manifest",
                    "external_delivery_executor_not_implemented",
                ],
            },
        )

    def _apply_backend_manifest_recovery(
        self,
        *,
        recovery_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> BackendManifestRecovery | None:
        if not self.config.apply_backend_manifest_recovery:
            return None
        delivery_root = self.config.resolved_delivery_root()
        source_manifest_path = self.config.resolved_backend_manifest_path()
        source_manifest_exists = bool(source_manifest_path and source_manifest_path.exists())
        source_digest_before = _file_sha256(source_manifest_path) if source_manifest_path and source_manifest_exists else None
        journal_path = delivery_root / "delivery-transaction-journal.json"
        journal_exists = journal_path.exists()
        journal = _read_json_object(journal_path) if journal_exists else {}
        source_transaction_id = str(journal["transaction_id"]) if journal.get("transaction_id") is not None else None
        expected_transaction_id = self.config.expected_recovery_transaction_id
        backend_manifest_mutated = bool(journal.get("backend_manifest_mutated"))
        external_delivery_performed = bool(journal.get("external_delivery_performed"))
        cross_run_transaction_committed = bool(journal.get("cross_run_transaction_committed"))
        already_recovered = bool(journal.get("backend_manifest_recovered"))
        recovery_preflight_path = _resolve_record_path(journal.get("backend_manifest_recovery_preflight_path"), delivery_root)
        if recovery_preflight_path is None:
            recovery_preflight_path = (delivery_root / self.config.backend_manifest_recovery_preflight_name).resolve()
        recovery_preflight_exists = recovery_preflight_path.exists()
        recovery_preflight = _read_json_object(recovery_preflight_path) if recovery_preflight_exists else {}
        recovery_preflight_status = (
            str(recovery_preflight["status"]) if recovery_preflight.get("status") is not None else None
        )
        recovery_available = bool(recovery_preflight.get("recovery_available"))
        recovery_journal_transaction_id = (
            str(recovery_preflight["journal_transaction_id"])
            if recovery_preflight.get("journal_transaction_id") is not None
            else None
        )
        recovery_source_digest = (
            recovery_preflight.get("source_manifest_digest_sha256")
            if isinstance(recovery_preflight.get("source_manifest_digest_sha256"), str)
            else None
        )
        recovery_rollback_digest = (
            recovery_preflight.get("rollback_manifest_digest_sha256")
            if isinstance(recovery_preflight.get("rollback_manifest_digest_sha256"), str)
            else None
        )
        rollback_path = _resolve_record_path(
            recovery_preflight.get("rollback_path") or journal.get("backend_manifest_rollback_path"),
            delivery_root,
        )
        if backend_manifest_mutated and rollback_path is None:
            rollback_path = (delivery_root / self.config.backend_manifest_rollback_name).resolve()
        rollback_exists = bool(rollback_path and rollback_path.exists())
        rollback_digest = _file_sha256(rollback_path) if rollback_path and rollback_exists else None
        checks = [
            {
                "name": "source_manifest_exists",
                "passed": source_manifest_exists,
                "details": {"source_manifest_path": str(source_manifest_path) if source_manifest_path else None},
            },
            {
                "name": "transaction_journal_exists",
                "passed": journal_exists,
                "details": {"transaction_journal_path": str(journal_path)},
            },
            {
                "name": "expected_recovery_transaction_matches",
                "passed": expected_transaction_id is None or expected_transaction_id == source_transaction_id,
                "details": {"expected": expected_transaction_id, "actual": source_transaction_id},
            },
            {
                "name": "journal_reports_backend_manifest_mutated",
                "passed": backend_manifest_mutated,
                "details": {"backend_manifest_mutated": backend_manifest_mutated},
            },
            {
                "name": "journal_reports_no_external_delivery",
                "passed": not external_delivery_performed,
                "details": {"external_delivery_performed": external_delivery_performed},
            },
            {
                "name": "journal_reports_no_cross_run_commit",
                "passed": not cross_run_transaction_committed,
                "details": {"cross_run_transaction_committed": cross_run_transaction_committed},
            },
            {
                "name": "journal_not_already_recovered",
                "passed": not already_recovered,
                "details": {"backend_manifest_recovered": already_recovered},
            },
            {
                "name": "recovery_preflight_exists",
                "passed": recovery_preflight_exists,
                "details": {"recovery_preflight_path": str(recovery_preflight_path)},
            },
            {
                "name": "recovery_preflight_ready_for_review",
                "passed": recovery_preflight_status == "ready_for_review" and recovery_available,
                "details": {"status": recovery_preflight_status, "recovery_available": recovery_available},
            },
            {
                "name": "recovery_preflight_transaction_matches_journal",
                "passed": recovery_journal_transaction_id == source_transaction_id,
                "details": {"recovery_journal_transaction_id": recovery_journal_transaction_id, "journal_transaction_id": source_transaction_id},
            },
            {
                "name": "source_matches_recovery_preflight_digest",
                "passed": bool(source_digest_before and recovery_source_digest == source_digest_before),
                "details": {"expected": recovery_source_digest, "actual": source_digest_before},
            },
            {
                "name": "rollback_checkpoint_exists",
                "passed": rollback_exists,
                "details": {"rollback_path": str(rollback_path) if rollback_path else None},
            },
            {
                "name": "rollback_digest_matches_recovery_preflight",
                "passed": bool(rollback_digest and recovery_rollback_digest == rollback_digest),
                "details": {"expected": recovery_rollback_digest, "actual": rollback_digest},
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        recovered = False
        post_recovery_digest = None
        if dry_run:
            status = "planned"
            recommended_actions = ["run_apply_backend_manifest_recovery_after_review"]
        elif blocking_reasons:
            status = "blocked"
            recommended_actions = ["inspect_recovery_preflight_and_rollback_checkpoint_before_restore"]
        else:
            if source_manifest_path is None or rollback_path is None:
                raise ValueError("backend manifest recovery requires source manifest and rollback path")
            source_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rollback_path, source_manifest_path)
            recovered = True
            post_recovery_digest = _file_sha256(source_manifest_path)
            status = "recovered"
            recommended_actions = ["review_recovered_manifest_before_new_delivery_or_commit"]
        return BackendManifestRecovery(
            transaction_id=self.config.transaction_id,
            status=status,
            recovery_id=f"backend-manifest-recovery-{self.config.transaction_id}",
            recovery_path=recovery_path,
            delivery_root=str(delivery_root),
            source_transaction_id=source_transaction_id,
            source_manifest_path=str(source_manifest_path) if source_manifest_path else None,
            transaction_journal_path=str(journal_path),
            recovery_preflight_path=str(recovery_preflight_path),
            rollback_path=str(rollback_path) if rollback_path else None,
            dry_run=dry_run,
            recovery_requested=True,
            recovered=recovered,
            backend_manifest_mutated_before_recovery=backend_manifest_mutated,
            external_delivery_performed=False,
            cross_run_transaction_committed=False,
            source_manifest_digest_before_recovery_sha256=source_digest_before,
            rollback_manifest_digest_sha256=rollback_digest,
            post_recovery_manifest_digest_sha256=post_recovery_digest,
            expected_recovery_transaction_id=expected_transaction_id,
            recovery_preflight_status=recovery_preflight_status,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "backend-manifest-cross-run-recovery-apply-baseline",
                "external_delivery_performed": False,
                "cross_run_transaction_committed": False,
                "limitations": [
                    "explicit_review_restore_from_local_rollback_checkpoint",
                    "does_not_publish_external_delivery",
                    "does_not_commit_cross_run_transaction",
                    "cross_run_physical_rollback_transaction_state_machine_not_implemented",
                ],
            },
        )

    def _is_recovery_preflight_only(self, artifacts: list[DeliveryArtifact]) -> bool:
        return (
            self.config.preflight_backend_manifest_recovery
            and not artifacts
            and not self.config.commit_manifest_revision
            and not self.config.commit_backend_manifest_mutation
            and not self.config.preflight_backend_manifest_in_place_mutation
            and not self.config.approve_backend_manifest_in_place_mutation
            and not self.config.apply_backend_manifest_recovery
            and not self.config.commit_cross_run_transaction
        )

    def _is_backend_manifest_recovery_apply_only(self, artifacts: list[DeliveryArtifact]) -> bool:
        return (
            self.config.apply_backend_manifest_recovery
            and not artifacts
            and not self.config.commit_manifest_revision
            and not self.config.commit_backend_manifest_mutation
            and not self.config.preflight_backend_manifest_in_place_mutation
            and not self.config.approve_backend_manifest_in_place_mutation
            and not self.config.preflight_backend_manifest_recovery
            and not self.config.commit_cross_run_transaction
        )

    def _is_cross_run_transaction_commit_only(self, artifacts: list[DeliveryArtifact]) -> bool:
        return (
            self.config.commit_cross_run_transaction
            and not artifacts
            and not self.config.commit_manifest_revision
            and not self.config.commit_backend_manifest_mutation
            and not self.config.preflight_backend_manifest_in_place_mutation
            and not self.config.approve_backend_manifest_in_place_mutation
            and not self.config.preflight_backend_manifest_recovery
            and not self.config.apply_backend_manifest_recovery
        )

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


def _json_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json_object(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Backend artifact manifest must be a JSON object: {path}")
    return payload


def _resolve_record_path(value: Any, base_dir: Path) -> Path | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _safe_archive_component(value: Any) -> str:
    raw = str(value).replace("\\", "/").split("/")[-1].strip()
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "-" for character in raw)
    safe = safe.strip(".")
    if not safe or safe in {".", ".."}:
        raise ValueError(f"Invalid archive path component: {value!r}")
    return safe


def _journal_bool(journal: dict[str, Any], key: str, default: bool) -> bool:
    if key in journal:
        return bool(journal[key])
    return default


def _journal_str(journal: dict[str, Any], key: str, default: str | None) -> str | None:
    value = journal.get(key)
    if value is None:
        return default
    return str(value)


def _journal_entries(journal: dict[str, Any]) -> list[dict[str, Any]]:
    entries = journal.get("entries")
    if not isinstance(entries, list):
        return []
    return [dict(item) for item in entries if isinstance(item, dict)]


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


def _duplicate_artifact_keys(entries: Any) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    if not isinstance(entries, list):
        return []
    for item in entries:
        if not isinstance(item, dict):
            continue
        artifact_key = item.get("artifact_key")
        if not artifact_key:
            continue
        key = str(artifact_key)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return sorted(duplicates)


def _replace_backend_manifest_mutation_digest(
    mutation: BackendManifestMutation,
    patched_manifest_digest_sha256: str,
) -> BackendManifestMutation:
    return replace(mutation, patched_manifest_digest_sha256=patched_manifest_digest_sha256)


def _mark_backend_manifest_in_place_mutated(
    manifest: dict[str, Any],
    *,
    transaction_id: str,
    mutation_id: str,
    in_place_mutation_id: str,
    rollback_path: str,
) -> dict[str, Any]:
    payload = dict(manifest)
    policy = dict(payload.get("mutation_policy") if isinstance(payload.get("mutation_policy"), dict) else {})
    policy.update(
        {
            "transaction_id": transaction_id,
            "mutation_id": mutation_id,
            "in_place_mutation_id": in_place_mutation_id,
            "backend_manifest_mutated": True,
            "backend_manifest_in_place_mutation_approved": True,
            "backend_manifest_patch_written": True,
            "rollback_path": rollback_path,
            "scope": "explicit-review-in-place-mutation-baseline",
            "external_delivery_performed": False,
            "cross_run_transaction_committed": False,
        }
    )
    payload["mutation_policy"] = policy
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
