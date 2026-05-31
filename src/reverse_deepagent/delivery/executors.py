from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from .state_machine import DeliveryTransactionSnapshot, evaluate_delivery_transaction_state


DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class ExternalDeliveryHttpRequestResult:
    """Secret-safe HTTP request attempt summary for external delivery providers."""

    status_code: int | None
    error: str | None
    attempts: list[dict[str, Any]]
    retry_after_honored: bool = False
    retry_after_seen: bool = False
    retry_budget_exhausted: bool = False
    body: bytes = b""

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def retry_count(self) -> int:
        return max(0, self.attempt_count - 1)


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
    transaction_idempotency_guard_name: str = "delivery-transaction-idempotency-guard.json"
    request_external_delivery: bool = False
    external_delivery_result_name: str = "external-delivery-result.json"
    external_delivery_provider_id: str = "review-only"
    external_delivery_provider: ExternalDeliveryProvider | None = None
    external_delivery_provider_registry: Any | None = None
    external_delivery_provider_config: dict[str, Any] = field(default_factory=dict)
    external_delivery_idempotency_key: str | None = None
    allow_duplicate_external_delivery: bool = False
    external_delivery_duplicate_guard_name: str = "external-delivery-duplicate-guard.json"
    external_delivery_idempotency_ledger_name: str = "external-delivery-idempotency-ledger.json"
    require_transaction_lock: bool = False
    transaction_lock_name: str = "delivery-transaction-lock.json"
    transaction_lock_owner: str | None = None
    transaction_lock_lease_seconds: int = 900
    expected_resume_token: str | None = None
    release_transaction_lock: bool = False
    approve_transaction_lock_release: bool = False
    transaction_lock_release_name: str = "delivery-transaction-lock-release.json"
    expected_transaction_lock_owner: str | None = None
    expected_transaction_lock_transaction_id: str | None = None

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


@dataclass(frozen=True)
class ExternalDeliveryIdempotencyLedger:
    """Append-only audit ledger for external delivery idempotency decisions.

    The ledger is an evidence artifact only.  It never publishes externally,
    retries requests, recovers transactions, or bypasses the duplicate guard.
    """

    transaction_id: str
    idempotency_key: str
    provider_id: str
    status: str
    ledger_path: str | None
    delivery_root: str
    external_delivery_result_path: str | None
    external_delivery_performed: bool
    duplicate_guard_triggered: bool
    allow_duplicate_external_delivery: bool
    provider_factory_invoked: bool | None
    entry_count: int
    entries: list[dict[str, Any]]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "idempotency_key": self.idempotency_key,
            "provider_id": self.provider_id,
            "status": self.status,
            "ledger_path": self.ledger_path,
            "delivery_root": self.delivery_root,
            "external_delivery_result_path": self.external_delivery_result_path,
            "external_delivery_performed": self.external_delivery_performed,
            "duplicate_guard_triggered": self.duplicate_guard_triggered,
            "allow_duplicate_external_delivery": self.allow_duplicate_external_delivery,
            "provider_factory_invoked": self.provider_factory_invoked,
            "entry_count": self.entry_count,
            "entries": self.entries,
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
class WebhookExternalDeliveryProvider:
    """HTTP JSON webhook external delivery provider.

    The provider only sends a request in apply mode.  Dry-run returns a planned
    result without opening a socket.  Runtime config values such as webhook URL
    and headers are used for the request but never written verbatim to metadata.
    """

    webhook_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    retry_attempts: int = 0
    retry_backoff_seconds: float = 0.0
    retry_jitter_seconds: float = 0.0
    honor_retry_after: bool = True
    retry_status_codes: tuple[int, ...] = DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES
    provider_id: str = "webhook"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_digest = _json_payload_sha256(package.to_dict())
        normalized_url = _normalize_webhook_url(self.webhook_url)
        redacted_url = _redact_url_for_metadata(normalized_url)
        local_ready = not package.local_errors
        url_configured = bool(normalized_url)
        scheme_supported = _webhook_scheme_supported(normalized_url)
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "webhook_url_configured",
                "passed": url_configured,
                "details": {"configured": url_configured},
            },
            {
                "name": "webhook_url_scheme_supported",
                "passed": scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "target_url": redacted_url},
            },
        ]
        preflight_blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        payload = {
            "provider_id": self.provider_id,
            "transaction_id": package.transaction_id,
            "created_at": created_at,
            "package_digest_sha256": package_digest,
            "package": package.to_dict(),
        }
        request_body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        response_status_code: int | None = None
        request_error: str | None = None
        request_attempts: list[dict[str, Any]] = []
        request_attempted = False
        request_succeeded = False
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            request_attempted = True
            request_result = self._post_json(normalized_url, request_body)
            response_status_code = request_result.status_code
            request_error = request_result.error
            request_attempts = request_result.attempts
            request_succeeded = bool(response_status_code is not None and 200 <= response_status_code < 300)
            checks.append(
                {
                    "name": "webhook_response_status_successful",
                    "passed": request_succeeded,
                    "details": {
                        "status_code": response_status_code,
                        "request_error": request_error,
                        "target_url": redacted_url,
                        "attempt_count": len(request_attempts),
                        "retry_count": max(0, len(request_attempts) - 1),
                    },
                }
            )
            blocking_reasons = [check["name"] for check in checks if not check["passed"]]
            status = "delivered" if request_succeeded else "blocked"
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=request_succeeded,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_webhook_external_delivery_result"]
                if request_succeeded
                else ["apply_local_delivery_before_webhook_delivery"]
                if dry_run and not blocking_reasons
                else ["fix_webhook_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "webhook-external-delivery-provider-baseline",
                "target_url": redacted_url,
                "target_query_redacted": _url_has_query(normalized_url),
                "target_credentials_redacted": _url_has_credentials(normalized_url),
                "request_method": "POST",
                "request_body_digest_sha256": request_body_digest,
                "request_body_bytes": len(request_body),
                "request_attempted": request_attempted,
                "request_attempt_count": len(request_attempts),
                "request_retry_count": max(0, len(request_attempts) - 1),
                "request_attempts": request_attempts,
                "request_retry_summary": _http_attempts_policy_summary(request_attempts),
                "request_succeeded": request_succeeded,
                "response_status_code": response_status_code,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "request_headers_recorded": False,
                "configured_header_count": len(self.headers),
                "timeout_seconds": self.timeout_seconds,
                "retry_enabled": _coerce_retry_attempts(self.retry_attempts) > 0,
                "retry_attempts_configured": _coerce_retry_attempts(self.retry_attempts),
                "retry_backoff_seconds": _coerce_retry_backoff_seconds(self.retry_backoff_seconds),
                "retry_jitter_seconds": _coerce_retry_jitter_seconds(self.retry_jitter_seconds),
                "honor_retry_after": bool(self.honor_retry_after),
                "retry_status_codes": list(_coerce_retry_status_codes(self.retry_status_codes)),
                "automatic_delivery": False,
                "publishes_externally": True,
                "transport": "webhook",
                "limitations": [
                    "http_json_webhook_only",
                    "does_not_record_response_body_or_headers",
                    "retry_requires_explicit_config",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
        )

    def _post_json(self, url: str, body: bytes) -> ExternalDeliveryHttpRequestResult:
        request_headers = {
            "Content-Type": "application/json",
            "User-Agent": "reverse-deepagent-webhook-delivery/0",
            **{str(key): str(value) for key, value in self.headers.items()},
        }
        return _http_request_with_retries(
            lambda: urllib.request.Request(
                url,
                data=body,
                headers=request_headers,
                method="POST",
            ),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
        )


@dataclass(frozen=True)
class PresignedObjectExternalDeliveryProvider:
    """HTTP PUT provider for presigned object-storage URLs.

    The provider uploads the provider-neutral delivery package as JSON to an
    already prepared presigned URL.  It deliberately avoids cloud SDKs and
    credentials: dry-run never opens a socket, and apply mode only performs an
    explicit PUT to the configured URL.  Query strings and credentials in the
    presigned URL are redacted from result metadata.
    """

    presigned_url: str | None = None
    object_name: str | None = None
    content_type: str = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 10.0
    retry_attempts: int = 0
    retry_backoff_seconds: float = 0.0
    retry_jitter_seconds: float = 0.0
    honor_retry_after: bool = True
    retry_status_codes: tuple[int, ...] = DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES
    provider_id: str = "presigned-object"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_digest = _json_payload_sha256(package.to_dict())
        normalized_url = _normalize_external_delivery_url(self.presigned_url)
        redacted_url = _redact_url_for_metadata(normalized_url)
        local_ready = not package.local_errors
        url_configured = bool(normalized_url)
        scheme_supported = _http_scheme_supported(normalized_url)
        content_type_configured = bool(str(self.content_type or "").strip())
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "presigned_object_url_configured",
                "passed": url_configured,
                "details": {"configured": url_configured},
            },
            {
                "name": "presigned_object_url_scheme_supported",
                "passed": scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "target_url": redacted_url},
            },
            {
                "name": "presigned_object_content_type_configured",
                "passed": content_type_configured,
                "details": {"configured": content_type_configured},
            },
        ]
        preflight_blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        payload = {
            "provider_id": self.provider_id,
            "transaction_id": package.transaction_id,
            "created_at": created_at,
            "object_name": self.object_name,
            "package_digest_sha256": package_digest,
            "package": package.to_dict(),
        }
        request_body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        response_status_code: int | None = None
        request_error: str | None = None
        request_attempts: list[dict[str, Any]] = []
        request_attempted = False
        request_succeeded = False
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            request_attempted = True
            request_result = self._put_json(normalized_url, request_body)
            response_status_code = request_result.status_code
            request_error = request_result.error
            request_attempts = request_result.attempts
            request_succeeded = bool(response_status_code is not None and 200 <= response_status_code < 300)
            checks.append(
                {
                    "name": "presigned_object_response_status_successful",
                    "passed": request_succeeded,
                    "details": {
                        "status_code": response_status_code,
                        "request_error": request_error,
                        "target_url": redacted_url,
                        "attempt_count": len(request_attempts),
                        "retry_count": max(0, len(request_attempts) - 1),
                    },
                }
            )
            blocking_reasons = [check["name"] for check in checks if not check["passed"]]
            status = "delivered" if request_succeeded else "blocked"
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=request_succeeded,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_presigned_object_external_delivery_result"]
                if request_succeeded
                else ["apply_local_delivery_before_presigned_object_upload"]
                if dry_run and not blocking_reasons
                else ["fix_presigned_object_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "presigned-object-external-delivery-provider-baseline",
                "target_url": redacted_url,
                "target_query_redacted": _url_has_query(normalized_url),
                "target_credentials_redacted": _url_has_credentials(normalized_url),
                "object_name": self.object_name,
                "request_method": "PUT",
                "request_body_digest_sha256": request_body_digest,
                "request_body_bytes": len(request_body),
                "request_attempted": request_attempted,
                "request_attempt_count": len(request_attempts),
                "request_retry_count": max(0, len(request_attempts) - 1),
                "request_attempts": request_attempts,
                "request_retry_summary": _http_attempts_policy_summary(request_attempts),
                "request_succeeded": request_succeeded,
                "response_status_code": response_status_code,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "request_headers_recorded": False,
                "configured_header_count": len(self.headers),
                "content_type": str(self.content_type or ""),
                "timeout_seconds": self.timeout_seconds,
                "retry_enabled": _coerce_retry_attempts(self.retry_attempts) > 0,
                "retry_attempts_configured": _coerce_retry_attempts(self.retry_attempts),
                "retry_backoff_seconds": _coerce_retry_backoff_seconds(self.retry_backoff_seconds),
                "retry_jitter_seconds": _coerce_retry_jitter_seconds(self.retry_jitter_seconds),
                "honor_retry_after": bool(self.honor_retry_after),
                "retry_status_codes": list(_coerce_retry_status_codes(self.retry_status_codes)),
                "automatic_delivery": False,
                "publishes_externally": True,
                "transport": "object-storage",
                "limitations": [
                    "presigned_url_http_put_only",
                    "does_not_record_response_body_or_headers",
                    "retry_requires_explicit_config",
                    "does_not_manage_cloud_credentials_or_buckets",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
        )

    def _put_json(self, url: str, body: bytes) -> ExternalDeliveryHttpRequestResult:
        request_headers = {
            "Content-Type": str(self.content_type or "application/json"),
            "User-Agent": "reverse-deepagent-presigned-object-delivery/0",
            **{str(key): str(value) for key, value in self.headers.items()},
        }
        return _http_request_with_retries(
            lambda: urllib.request.Request(
                url,
                data=body,
                headers=request_headers,
                method="PUT",
            ),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
        )


@dataclass(frozen=True)
class GitHubReleaseExternalDeliveryProvider:
    """GitHub Release asset external delivery provider.

    Dry-run is side-effect free.  Apply mode creates a release for the configured
    repository/tag through the GitHub REST API and uploads the provider-neutral
    delivery package as a JSON release asset.  Runtime secrets such as tokens are
    used only for request headers and are never serialized into result metadata.
    """

    repository: str | None = None
    tag_name: str | None = None
    release_name: str | None = None
    asset_name: str | None = None
    token: str | None = None
    api_base_url: str = "https://api.github.com"
    timeout_seconds: float = 10.0
    reuse_existing_release: bool = False
    check_existing_asset: bool = True
    allow_existing_asset: bool = False
    approve_existing_asset_delete: bool = False
    approve_replacement_upload: bool = False
    expected_existing_asset_id: str | int | None = None
    retry_attempts: int = 0
    retry_backoff_seconds: float = 0.0
    retry_jitter_seconds: float = 0.0
    honor_retry_after: bool = True
    retry_status_codes: tuple[int, ...] = DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES
    provider_id: str = "github-release"

    def deliver(
        self,
        package: ExternalDeliveryPackage,
        *,
        dry_run: bool,
        result_path: str | None,
        created_at: str,
    ) -> ExternalDeliveryResult:
        package_digest = _json_payload_sha256(package.to_dict())
        repository = _normalize_github_repository(self.repository)
        owner, repo = _split_github_repository(repository)
        tag_name = str(self.tag_name or "").strip()
        release_name = str(self.release_name or tag_name or "").strip()
        asset_name = _safe_github_asset_name(self.asset_name or f"reverse-deepagent-{package.transaction_id}.json")
        api_base_url = _normalize_external_delivery_url(self.api_base_url).rstrip("/")
        release_api_url = f"{api_base_url}/repos/{owner}/{repo}/releases" if owner and repo else ""
        existing_release_api_url = (
            f"{api_base_url}/repos/{owner}/{repo}/releases/tags/{urllib.parse.quote(tag_name, safe='')}"
            if owner and repo and tag_name
            else ""
        )
        redacted_release_api_url = _redact_url_for_metadata(release_api_url)
        redacted_existing_release_api_url = _redact_url_for_metadata(existing_release_api_url)
        local_ready = not package.local_errors
        token_configured = bool(str(self.token or "").strip())
        api_scheme_supported = _http_scheme_supported(api_base_url)
        reuse_existing_release = bool(self.reuse_existing_release)
        check_existing_asset = bool(self.check_existing_asset)
        allow_existing_asset = bool(self.allow_existing_asset)
        approve_existing_asset_delete = bool(self.approve_existing_asset_delete)
        approve_replacement_upload = bool(self.approve_replacement_upload)
        expected_existing_asset_id = str(self.expected_existing_asset_id).strip() if self.expected_existing_asset_id is not None else ""
        checks = [
            {
                "name": "local_delivery_package_has_no_errors",
                "passed": local_ready,
                "details": {"local_errors": package.local_errors},
            },
            {
                "name": "github_repository_configured",
                "passed": bool(owner and repo),
                "details": {"repository": repository or None},
            },
            {
                "name": "github_release_tag_configured",
                "passed": bool(tag_name),
                "details": {"configured": bool(tag_name)},
            },
            {
                "name": "github_token_configured",
                "passed": token_configured,
                "details": {"configured": token_configured},
            },
            {
                "name": "github_api_url_scheme_supported",
                "passed": api_scheme_supported,
                "details": {"supported_schemes": ["http", "https"], "api_base_url": _redact_url_for_metadata(api_base_url)},
            },
        ]
        preflight_blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        payload = {
            "provider_id": self.provider_id,
            "transaction_id": package.transaction_id,
            "created_at": created_at,
            "repository": repository,
            "tag_name": tag_name,
            "asset_name": asset_name,
            "package_digest_sha256": package_digest,
            "package": package.to_dict(),
        }
        request_body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request_body_digest = hashlib.sha256(request_body).hexdigest()
        release_status_code: int | None = None
        upload_status_code: int | None = None
        existing_release_status_code: int | None = None
        asset_lookup_status_code: int | None = None
        existing_asset_delete_status_code: int | None = None
        release_error: str | None = None
        existing_release_error: str | None = None
        asset_lookup_error: str | None = None
        existing_asset_delete_error: str | None = None
        upload_error: str | None = None
        release_request_attempts: list[dict[str, Any]] = []
        existing_release_lookup_attempts: list[dict[str, Any]] = []
        asset_lookup_attempts: list[dict[str, Any]] = []
        existing_asset_delete_attempts: list[dict[str, Any]] = []
        upload_request_attempts: list[dict[str, Any]] = []
        upload_url_redacted: str | None = None
        existing_asset_delete_url: str | None = None
        existing_asset_delete_url_redacted: str | None = None
        assets_url_redacted: str | None = None
        release_request_attempted = False
        existing_release_lookup_attempted = False
        asset_lookup_attempted = False
        existing_asset_delete_request_attempted = False
        upload_request_attempted = False
        release_created = False
        existing_release_lookup_succeeded = False
        existing_release_reused = False
        asset_lookup_succeeded = False
        existing_asset_found = False
        existing_asset_count: int | None = None
        existing_asset: dict[str, Any] | None = None
        existing_asset_overwrite_plan: dict[str, Any] | None = None
        existing_asset_identity_matches = False
        existing_asset_delete_approved = False
        existing_asset_delete_succeeded = False
        existing_asset_overwrite_requested = bool(
            approve_existing_asset_delete or approve_replacement_upload or expected_existing_asset_id
        )
        release_succeeded = False
        upload_succeeded = False
        if dry_run:
            status = "planned" if not preflight_blocking_reasons else "blocked"
            blocking_reasons = preflight_blocking_reasons
        elif preflight_blocking_reasons:
            status = "blocked"
            blocking_reasons = preflight_blocking_reasons
        else:
            release_request_attempted = True
            release_status_code, upload_url, assets_url, release_request_attempts, release_error = self._create_release(
                release_api_url,
                tag_name=tag_name,
                release_name=release_name,
            )
            release_created = bool(release_status_code is not None and 200 <= release_status_code < 300 and upload_url)
            release_succeeded = release_created
            if not release_created and reuse_existing_release:
                existing_release_lookup_attempted = True
                (
                    existing_release_status_code,
                    existing_upload_url,
                    existing_assets_url,
                    existing_release_lookup_attempts,
                    existing_release_error,
                ) = self._get_release_by_tag(existing_release_api_url)
                existing_release_lookup_succeeded = bool(
                    existing_release_status_code is not None
                    and 200 <= existing_release_status_code < 300
                    and existing_upload_url
                )
                if existing_release_lookup_succeeded and existing_upload_url:
                    upload_url = existing_upload_url
                    assets_url = existing_assets_url
                    existing_release_reused = True
                    release_succeeded = True
            assets_url_redacted = _redact_url_for_metadata(assets_url or "")
            checks.append(
                {
                    "name": "github_release_available",
                    "passed": release_succeeded,
                    "details": {
                        "status_code": release_status_code,
                        "request_error": release_error,
                        "target_url": redacted_release_api_url,
                        "upload_url_present": bool(upload_url),
                        "attempt_count": len(release_request_attempts),
                        "retry_count": max(0, len(release_request_attempts) - 1),
                        "release_created": release_created,
                        "reuse_existing_release": reuse_existing_release,
                        "existing_release_lookup_attempted": existing_release_lookup_attempted,
                        "existing_release_lookup_status_code": existing_release_status_code,
                        "existing_release_lookup_error": existing_release_error,
                        "existing_release_lookup_url": redacted_existing_release_api_url,
                        "existing_release_lookup_attempt_count": len(existing_release_lookup_attempts),
                        "existing_release_lookup_retry_count": max(0, len(existing_release_lookup_attempts) - 1),
                        "existing_release_reused": existing_release_reused,
                    },
                }
            )
            asset_check_passed = True
            if release_succeeded and check_existing_asset:
                if assets_url:
                    asset_lookup_attempted = True
                    (
                        asset_lookup_status_code,
                        existing_asset_found_value,
                        existing_asset_count,
                        existing_asset,
                        existing_asset_delete_url,
                        asset_lookup_attempts,
                        asset_lookup_error,
                    ) = self._asset_exists(assets_url, asset_name)
                    asset_lookup_succeeded = bool(
                        asset_lookup_status_code is not None
                        and 200 <= asset_lookup_status_code < 300
                        and existing_asset_found_value is not None
                    )
                    existing_asset_found = bool(existing_asset_found_value)
                    existing_asset_delete_url_redacted = _redact_url_for_metadata(existing_asset_delete_url or "")
                    existing_asset_identity_matches = _github_existing_asset_identity_matches(
                        existing_asset=existing_asset,
                        asset_name=asset_name,
                        expected_existing_asset_id=expected_existing_asset_id,
                    )
                    delete_url_supported = _http_scheme_supported(existing_asset_delete_url or "")
                    existing_asset_delete_approved = bool(
                        existing_asset_found
                        and approve_existing_asset_delete
                        and approve_replacement_upload
                        and existing_asset_identity_matches
                        and delete_url_supported
                    )
                    if existing_asset_found and existing_asset_overwrite_requested:
                        checks.append(
                            {
                                "name": "github_release_existing_asset_delete_approved",
                                "passed": existing_asset_delete_approved,
                                "details": {
                                    "asset_name": asset_name,
                                    "approve_existing_asset_delete": approve_existing_asset_delete,
                                    "approve_replacement_upload": approve_replacement_upload,
                                    "expected_existing_asset_id_configured": bool(expected_existing_asset_id),
                                    "existing_asset_identity_matches": existing_asset_identity_matches,
                                    "delete_url_present": bool(existing_asset_delete_url),
                                    "delete_url_scheme_supported": delete_url_supported,
                                    "delete_url": existing_asset_delete_url_redacted,
                                },
                            }
                        )
                    if existing_asset_delete_approved and existing_asset_delete_url:
                        existing_asset_delete_request_attempted = True
                        (
                            existing_asset_delete_status_code,
                            existing_asset_delete_attempts,
                            existing_asset_delete_error,
                        ) = self._delete_asset(existing_asset_delete_url)
                        existing_asset_delete_succeeded = bool(
                            existing_asset_delete_status_code is not None
                            and 200 <= existing_asset_delete_status_code < 300
                        )
                        checks.append(
                            {
                                "name": "github_release_existing_asset_delete_successful",
                                "passed": existing_asset_delete_succeeded,
                                "details": {
                                    "status_code": existing_asset_delete_status_code,
                                    "request_error": existing_asset_delete_error,
                                    "target_url": existing_asset_delete_url_redacted,
                                    "attempt_count": len(existing_asset_delete_attempts),
                                    "retry_count": max(0, len(existing_asset_delete_attempts) - 1),
                                },
                            }
                        )
                    asset_check_passed = asset_lookup_succeeded and (
                        allow_existing_asset
                        or not existing_asset_found
                        or existing_asset_delete_succeeded
                    )
                else:
                    asset_check_passed = False
                    asset_lookup_error = "missing_assets_url"
                checks.append(
                    {
                        "name": "github_release_asset_not_already_present",
                        "passed": asset_check_passed,
                        "details": {
                            "asset_name": asset_name,
                            "asset_lookup_attempted": asset_lookup_attempted,
                            "asset_lookup_status_code": asset_lookup_status_code,
                            "asset_lookup_error": asset_lookup_error,
                            "asset_lookup_url": assets_url_redacted,
                            "asset_lookup_succeeded": asset_lookup_succeeded,
                            "asset_lookup_attempt_count": len(asset_lookup_attempts),
                            "asset_lookup_retry_count": max(0, len(asset_lookup_attempts) - 1),
                            "existing_asset_found": existing_asset_found,
                            "existing_asset_count": existing_asset_count,
                            "existing_asset": existing_asset,
                            "allow_existing_asset": allow_existing_asset,
                            "existing_asset_overwrite_requested": existing_asset_overwrite_requested,
                            "existing_asset_delete_succeeded": existing_asset_delete_succeeded,
                        },
                    }
                )
            if release_succeeded and upload_url:
                if asset_check_passed:
                    upload_request_attempted = True
                    upload_target = _github_upload_url_with_asset_name(upload_url, asset_name)
                    upload_url_redacted = _redact_url_for_metadata(upload_target)
                    upload_status_code, upload_request_attempts, upload_error = self._upload_asset(upload_target, request_body)
                    upload_succeeded = bool(upload_status_code is not None and 200 <= upload_status_code < 300)
                    checks.append(
                        {
                            "name": "github_release_asset_upload_successful",
                            "passed": upload_succeeded,
                            "details": {
                                "status_code": upload_status_code,
                                "request_error": upload_error,
                                "target_url": upload_url_redacted,
                                "attempt_count": len(upload_request_attempts),
                                "retry_count": max(0, len(upload_request_attempts) - 1),
                            },
                        }
                    )
            existing_asset_overwrite_plan = _github_existing_asset_overwrite_plan(
                asset_name=asset_name,
                existing_asset_found=existing_asset_found,
                existing_asset=existing_asset,
                check_existing_asset=check_existing_asset,
                allow_existing_asset=allow_existing_asset,
                asset_lookup_succeeded=asset_lookup_succeeded,
                approve_existing_asset_delete=approve_existing_asset_delete,
                approve_replacement_upload=approve_replacement_upload,
                expected_existing_asset_id_configured=bool(expected_existing_asset_id),
                existing_asset_identity_matches=existing_asset_identity_matches,
                delete_request_attempted=existing_asset_delete_request_attempted,
                delete_succeeded=existing_asset_delete_succeeded,
                delete_status_code=existing_asset_delete_status_code,
                delete_request_error=existing_asset_delete_error,
                upload_request_attempted=upload_request_attempted,
                overwrite_performed=bool(existing_asset_delete_succeeded and upload_succeeded),
            )
            blocking_reasons = [check["name"] for check in checks if not check["passed"]]
            status = "delivered" if upload_succeeded else "blocked"
        return ExternalDeliveryResult(
            transaction_id=package.transaction_id,
            status=status,
            provider_id=self.provider_id,
            result_path=result_path,
            delivery_root=package.delivery_root,
            dry_run=dry_run,
            external_delivery_requested=True,
            external_delivery_performed=upload_succeeded,
            package_digest_sha256=package_digest,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_github_release_external_delivery_result"]
                if upload_succeeded
                else ["apply_local_delivery_before_github_release_publish"]
                if dry_run and not blocking_reasons
                else ["fix_github_release_external_delivery_blockers"]
            ),
            created_at=created_at,
            metadata={
                **package.metadata,
                "scope": "github-release-external-delivery-provider-baseline",
                "repository": repository or None,
                "tag_name": tag_name or None,
                "release_name": release_name or None,
                "asset_name": asset_name,
                "release_api_url": redacted_release_api_url,
                "existing_release_api_url": redacted_existing_release_api_url,
                "assets_url": assets_url_redacted,
                "upload_url": upload_url_redacted,
                "api_query_redacted": _url_has_query(api_base_url),
                "api_credentials_redacted": _url_has_credentials(api_base_url),
                "request_method": "POST",
                "request_body_digest_sha256": request_body_digest,
                "request_body_bytes": len(request_body),
                "reuse_existing_release": reuse_existing_release,
                "check_existing_asset": check_existing_asset,
                "allow_existing_asset": allow_existing_asset,
                "approve_existing_asset_delete": approve_existing_asset_delete,
                "approve_replacement_upload": approve_replacement_upload,
                "expected_existing_asset_id_configured": bool(expected_existing_asset_id),
                "release_request_attempted": release_request_attempted,
                "release_request_attempt_count": len(release_request_attempts),
                "release_request_retry_count": max(0, len(release_request_attempts) - 1),
                "release_request_attempts": release_request_attempts,
                "release_request_retry_summary": _http_attempts_policy_summary(release_request_attempts),
                "existing_release_lookup_attempted": existing_release_lookup_attempted,
                "existing_release_lookup_attempt_count": len(existing_release_lookup_attempts),
                "existing_release_lookup_retry_count": max(0, len(existing_release_lookup_attempts) - 1),
                "existing_release_lookup_attempts": existing_release_lookup_attempts,
                "existing_release_lookup_retry_summary": _http_attempts_policy_summary(existing_release_lookup_attempts),
                "asset_lookup_attempted": asset_lookup_attempted,
                "asset_lookup_attempt_count": len(asset_lookup_attempts),
                "asset_lookup_retry_count": max(0, len(asset_lookup_attempts) - 1),
                "asset_lookup_attempts": asset_lookup_attempts,
                "asset_lookup_retry_summary": _http_attempts_policy_summary(asset_lookup_attempts),
                "existing_asset_delete_request_attempted": existing_asset_delete_request_attempted,
                "existing_asset_delete_attempt_count": len(existing_asset_delete_attempts),
                "existing_asset_delete_retry_count": max(0, len(existing_asset_delete_attempts) - 1),
                "existing_asset_delete_attempts": existing_asset_delete_attempts,
                "existing_asset_delete_retry_summary": _http_attempts_policy_summary(existing_asset_delete_attempts),
                "upload_request_attempted": upload_request_attempted,
                "upload_request_attempt_count": len(upload_request_attempts),
                "upload_request_retry_count": max(0, len(upload_request_attempts) - 1),
                "upload_request_attempts": upload_request_attempts,
                "upload_request_retry_summary": _http_attempts_policy_summary(upload_request_attempts),
                "release_created": release_created,
                "existing_release_lookup_succeeded": existing_release_lookup_succeeded,
                "existing_release_reused": existing_release_reused,
                "asset_lookup_succeeded": asset_lookup_succeeded,
                "existing_asset_found": existing_asset_found,
                "existing_asset_count": existing_asset_count,
                "existing_asset": existing_asset,
                "existing_asset_overwrite_plan": existing_asset_overwrite_plan,
                "existing_asset_overwrite_plan_recorded": existing_asset_overwrite_plan is not None,
                "existing_asset_identity_matches": existing_asset_identity_matches,
                "existing_asset_delete_url": existing_asset_delete_url_redacted,
                "existing_asset_delete_status_code": existing_asset_delete_status_code,
                "existing_asset_delete_succeeded": existing_asset_delete_succeeded,
                "existing_asset_delete_performed": existing_asset_delete_succeeded,
                "existing_asset_overwrite_performed": bool(existing_asset_delete_succeeded and upload_succeeded),
                "release_succeeded": release_succeeded,
                "upload_succeeded": upload_succeeded,
                "release_status_code": release_status_code,
                "existing_release_status_code": existing_release_status_code,
                "asset_lookup_status_code": asset_lookup_status_code,
                "upload_status_code": upload_status_code,
                "response_body_recorded": False,
                "response_headers_recorded": False,
                "request_headers_recorded": False,
                "timeout_seconds": self.timeout_seconds,
                "retry_enabled": _coerce_retry_attempts(self.retry_attempts) > 0,
                "retry_attempts_configured": _coerce_retry_attempts(self.retry_attempts),
                "retry_backoff_seconds": _coerce_retry_backoff_seconds(self.retry_backoff_seconds),
                "retry_jitter_seconds": _coerce_retry_jitter_seconds(self.retry_jitter_seconds),
                "honor_retry_after": bool(self.honor_retry_after),
                "retry_status_codes": list(_coerce_retry_status_codes(self.retry_status_codes)),
                "automatic_delivery": False,
                "publishes_externally": True,
                "transport": "github-release",
                "limitations": [
                    "github_release_json_asset_upload_baseline",
                    "existing_release_reuse_requires_explicit_config",
                    "existing_asset_conflict_blocks_upload_by_default",
                    "existing_asset_overwrite_delete_requires_explicit_approval",
                    "does_not_record_response_body_or_headers",
                    "retry_requires_explicit_config",
                    "full_cross_run_transaction_state_machine_not_implemented",
                ],
            },
        )

    def _request_headers(self, *, content_type: str = "application/json") -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": content_type,
            "User-Agent": "reverse-deepagent-github-release-delivery/0",
        }
        token = str(self.token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _create_release(
        self, url: str, *, tag_name: str, release_name: str
    ) -> tuple[int | None, str | None, str | None, list[dict[str, Any]], str | None]:
        body = json.dumps(
            {
                "tag_name": tag_name,
                "name": release_name or tag_name,
                "draft": False,
                "prerelease": False,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        result = _http_request_with_retries(
            lambda: urllib.request.Request(url, data=body, headers=self._request_headers(), method="POST"),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
            read_response_body=True,
        )
        upload_url, assets_url = _github_release_urls_from_response_body(result.body)
        return result.status_code, upload_url, assets_url, result.attempts, result.error

    def _get_release_by_tag(self, url: str) -> tuple[int | None, str | None, str | None, list[dict[str, Any]], str | None]:
        result = _http_request_with_retries(
            lambda: urllib.request.Request(url, headers=self._request_headers(), method="GET"),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
            read_response_body=True,
        )
        upload_url, assets_url = _github_release_urls_from_response_body(result.body)
        return result.status_code, upload_url, assets_url, result.attempts, result.error

    def _asset_exists(
        self, url: str, asset_name: str
    ) -> tuple[int | None, bool | None, int | None, dict[str, Any] | None, str | None, list[dict[str, Any]], str | None]:
        result = _http_request_with_retries(
            lambda: urllib.request.Request(url, headers=self._request_headers(), method="GET"),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
            read_response_body=True,
        )
        exists, count, existing_asset, existing_asset_delete_url = _github_asset_lookup_from_response_body(result.body, asset_name)
        if result.status_code is not None and 200 <= result.status_code < 300 and exists is None:
            return result.status_code, None, count, None, None, result.attempts, "invalid_github_assets_response"
        return result.status_code, exists, count, existing_asset, existing_asset_delete_url, result.attempts, result.error

    def _delete_asset(self, url: str) -> tuple[int | None, list[dict[str, Any]], str | None]:
        result = _http_request_with_retries(
            lambda: urllib.request.Request(
                url,
                headers=self._request_headers(content_type="application/json"),
                method="DELETE",
            ),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
        )
        return result.status_code, result.attempts, result.error

    def _upload_asset(self, url: str, body: bytes) -> tuple[int | None, list[dict[str, Any]], str | None]:
        result = _http_request_with_retries(
            lambda: urllib.request.Request(
                url,
                data=body,
                headers=self._request_headers(content_type="application/json"),
                method="POST",
            ),
            timeout_seconds=self.timeout_seconds,
            retry_attempts=self.retry_attempts,
            retry_status_codes=self.retry_status_codes,
            retry_backoff_seconds=self.retry_backoff_seconds,
            retry_jitter_seconds=self.retry_jitter_seconds,
            honor_retry_after=self.honor_retry_after,
        )
        return result.status_code, result.attempts, result.error


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
class DeliveryTransactionIdempotencyGuard:
    transaction_id: str
    status: str
    operation: str
    guard_path: str | None
    delivery_root: str
    transaction_journal_path: str | None
    terminal_artifact_path: str | None
    terminal_artifact_kind: str
    dry_run: bool
    duplicate_guard_triggered: bool
    terminal_artifact_preserved: bool
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "operation": self.operation,
            "guard_path": self.guard_path,
            "delivery_root": self.delivery_root,
            "transaction_journal_path": self.transaction_journal_path,
            "terminal_artifact_path": self.terminal_artifact_path,
            "terminal_artifact_kind": self.terminal_artifact_kind,
            "dry_run": self.dry_run,
            "duplicate_guard_triggered": self.duplicate_guard_triggered,
            "terminal_artifact_preserved": self.terminal_artifact_preserved,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryTransactionLock:
    transaction_id: str
    status: str
    operation: str
    lock_path: str | None
    delivery_root: str
    owner: str
    resume_token: str | None
    expected_resume_token: str | None
    lease_expires_at: str | None
    dry_run: bool
    lock_required: bool
    lock_acquired: bool
    resume_accepted: bool
    stale_lock_detected: bool
    existing_lock: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "operation": self.operation,
            "lock_path": self.lock_path,
            "delivery_root": self.delivery_root,
            "owner": self.owner,
            "resume_token": self.resume_token,
            "expected_resume_token": self.expected_resume_token,
            "lease_expires_at": self.lease_expires_at,
            "dry_run": self.dry_run,
            "lock_required": self.lock_required,
            "lock_acquired": self.lock_acquired,
            "resume_accepted": self.resume_accepted,
            "stale_lock_detected": self.stale_lock_detected,
            "existing_lock": self.existing_lock,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryTransactionLockRelease:
    transaction_id: str
    status: str
    operation: str
    lock_path: str
    release_path: str | None
    delivery_root: str
    owner: str | None
    expected_owner: str | None
    expected_lock_transaction_id: str | None
    expected_resume_token: str | None
    dry_run: bool
    approval_required: bool
    release_approved: bool
    lock_removed: bool
    stale_lock_detected: bool
    existing_lock: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "status": self.status,
            "operation": self.operation,
            "lock_path": self.lock_path,
            "release_path": self.release_path,
            "delivery_root": self.delivery_root,
            "owner": self.owner,
            "expected_owner": self.expected_owner,
            "expected_lock_transaction_id": self.expected_lock_transaction_id,
            "expected_resume_token": self.expected_resume_token,
            "dry_run": self.dry_run,
            "approval_required": self.approval_required,
            "release_approved": self.release_approved,
            "lock_removed": self.lock_removed,
            "stale_lock_detected": self.stale_lock_detected,
            "existing_lock": self.existing_lock,
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
    external_delivery_idempotency_ledger_path: str | None
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
            "external_delivery_idempotency_ledger_path": self.external_delivery_idempotency_ledger_path,
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
    transaction_state: DeliveryTransactionSnapshot
    manifest_revision: DeliveryManifestRevision | None
    backend_manifest_mutation: BackendManifestMutation | None
    backend_manifest_in_place_preflight: BackendManifestInPlacePreflight | None
    backend_manifest_in_place_mutation: BackendManifestInPlaceMutation | None
    backend_manifest_recovery_preflight: BackendManifestRecoveryPreflight | None
    backend_manifest_recovery: BackendManifestRecovery | None
    backend_manifest_transaction_commit: BackendManifestTransactionCommit | None
    transaction_lock: DeliveryTransactionLock | None
    transaction_lock_release: DeliveryTransactionLockRelease | None
    transaction_idempotency_guard: DeliveryTransactionIdempotencyGuard | None
    external_delivery_result: ExternalDeliveryResult | None
    external_delivery_idempotency_ledger: ExternalDeliveryIdempotencyLedger | None
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
            "transaction_state": self.transaction_state.to_dict(),
            "manifest_revision": self.manifest_revision.to_dict() if self.manifest_revision else None,
            "backend_manifest_mutation": self.backend_manifest_mutation.to_dict() if self.backend_manifest_mutation else None,
            "backend_manifest_in_place_preflight": self.backend_manifest_in_place_preflight.to_dict() if self.backend_manifest_in_place_preflight else None,
            "backend_manifest_in_place_mutation": self.backend_manifest_in_place_mutation.to_dict() if self.backend_manifest_in_place_mutation else None,
            "backend_manifest_recovery_preflight": self.backend_manifest_recovery_preflight.to_dict() if self.backend_manifest_recovery_preflight else None,
            "backend_manifest_recovery": self.backend_manifest_recovery.to_dict() if self.backend_manifest_recovery else None,
            "backend_manifest_transaction_commit": self.backend_manifest_transaction_commit.to_dict() if self.backend_manifest_transaction_commit else None,
            "transaction_lock": self.transaction_lock.to_dict() if self.transaction_lock else None,
            "transaction_lock_release": self.transaction_lock_release.to_dict() if self.transaction_lock_release else None,
            "transaction_idempotency_guard": self.transaction_idempotency_guard.to_dict() if self.transaction_idempotency_guard else None,
            "external_delivery_result": self.external_delivery_result.to_dict() if self.external_delivery_result else None,
            "external_delivery_idempotency_ledger": (
                self.external_delivery_idempotency_ledger.to_dict() if self.external_delivery_idempotency_ledger else None
            ),
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
        lock_release_only = self.config.release_transaction_lock
        transaction_lock_release_path = (
            str(delivery_root / self.config.transaction_lock_release_name)
            if self.config.write_receipt and not dry_run and not errors and lock_release_only
            else None
        )
        transaction_lock_release = self._build_transaction_lock_release(
            release_path=transaction_lock_release_path,
            dry_run=dry_run,
            created_at=created_at,
        )
        lock_operation = self._transaction_lock_operation(artifacts)
        transaction_lock_path = (
            str(delivery_root / self.config.transaction_lock_name)
            if self.config.write_receipt
            and not dry_run
            and not errors
            and self.config.require_transaction_lock
            and lock_operation is not None
            and not lock_release_only
            else None
        )
        transaction_lock = self._build_transaction_lock(
            lock_path=transaction_lock_path,
            operation=lock_operation,
            dry_run=dry_run,
            created_at=created_at,
        )
        transaction_lock_blocking = bool(transaction_lock and transaction_lock.blocking_reasons)
        side_effects_blocked_by_lock = transaction_lock_blocking
        effective_dry_run = dry_run or side_effects_blocked_by_lock
        if transaction_lock_path and transaction_lock and transaction_lock.lock_acquired:
            _write_json(Path(transaction_lock_path), transaction_lock.to_dict())
        delivered: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        if errors:
            status = "failed"
            next_action = "fix_delivery_artifact_inputs"
        elif dry_run:
            status = "lock_release_planned" if lock_release_only else "planned"
            next_action = "approve_delivery_transaction_lock_release" if lock_release_only else "approve_local_delivery_apply"
            skipped = [dict(item, reason="dry_run") for item in planned]
        elif lock_release_only:
            if transaction_lock_release and transaction_lock_release.lock_removed:
                status = "lock_released"
                next_action = "review_delivery_transaction_lock_release"
            else:
                status = "blocked"
                next_action = "fix_delivery_transaction_lock_release_blockers"
            skipped = [dict(item, reason="transaction_lock_release_only") for item in planned]
        elif transaction_lock_blocking:
            status = "blocked"
            next_action = "review_or_release_delivery_transaction_lock"
            skipped = [dict(item, reason="transaction_lock_blocked") for item in planned]
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
            if self.config.write_receipt and not dry_run and not errors and not transaction_lock_blocking and not lock_release_only and not recovery_only and not recovery_apply_only and not transaction_commit_only
            else None
        )
        journal_path = (
            str(delivery_root / "delivery-transaction-journal.json")
            if self.config.write_receipt and not dry_run and not errors and not transaction_lock_blocking and not lock_release_only and not recovery_only and not recovery_apply_only and not transaction_commit_only
            else None
        )
        manifest_revision_path = (
            str(delivery_root / self.config.manifest_revision_name)
            if self.config.write_receipt and self.config.commit_manifest_revision and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_mutation_path = (
            str(delivery_root / self.config.backend_manifest_mutation_name)
            if self.config.write_receipt and self.config.commit_backend_manifest_mutation and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_patched_path = (
            str(delivery_root / self.config.backend_manifest_patched_name)
            if self.config.write_receipt and self.config.commit_backend_manifest_mutation and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_preflight_path = (
            str(delivery_root / self.config.backend_manifest_preflight_name)
            if self.config.write_receipt and self.config.preflight_backend_manifest_in_place_mutation and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_in_place_mutation_path = (
            str(delivery_root / self.config.backend_manifest_in_place_mutation_name)
            if self.config.write_receipt and self.config.approve_backend_manifest_in_place_mutation and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_rollback_path = (
            str(delivery_root / self.config.backend_manifest_rollback_name)
            if self.config.write_receipt and self.config.approve_backend_manifest_in_place_mutation and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_recovery_preflight_path = (
            str(delivery_root / self.config.backend_manifest_recovery_preflight_name)
            if self.config.write_receipt and self.config.preflight_backend_manifest_recovery and not dry_run and not errors
            else None
        )
        backend_manifest_recovery_path = (
            str(delivery_root / self.config.backend_manifest_recovery_name)
            if self.config.write_receipt and self.config.apply_backend_manifest_recovery and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        backend_manifest_transaction_commit_path = (
            str(delivery_root / self.config.backend_manifest_transaction_commit_name)
            if self.config.write_receipt and self.config.commit_cross_run_transaction and not dry_run and not errors and not transaction_lock_blocking
            else None
        )
        transaction_idempotency_guard_path = (
            str(delivery_root / self.config.transaction_idempotency_guard_name)
            if self.config.write_receipt
            and not dry_run
            and not errors
            and not transaction_lock_blocking
            and (self.config.apply_backend_manifest_recovery or self.config.commit_cross_run_transaction)
            else None
        )
        external_delivery_result_path = (
            str(delivery_root / self.config.external_delivery_result_name)
            if self.config.write_receipt and self.config.request_external_delivery and not dry_run and not transaction_lock_blocking
            else None
        )
        external_delivery_idempotency_ledger_path = (
            str(delivery_root / self.config.external_delivery_idempotency_ledger_name)
            if self.config.write_receipt and self.config.request_external_delivery and not dry_run and not transaction_lock_blocking
            else None
        )
        backend_manifest_transaction_commit = self._build_backend_manifest_transaction_commit(
            commit_path=backend_manifest_transaction_commit_path,
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        if transaction_commit_only and backend_manifest_transaction_commit and not transaction_lock_blocking:
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
            dry_run=effective_dry_run,
            created_at=created_at,
            revision_path=manifest_revision_path,
        )
        backend_manifest_mutation = self._build_backend_manifest_mutation(
            delivery_root=delivery_root,
            delivered=delivered,
            planned=planned,
            status=status,
            dry_run=effective_dry_run,
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
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        backend_manifest_in_place_mutation = self._apply_backend_manifest_in_place_mutation(
            mutation=backend_manifest_mutation,
            preflight=backend_manifest_in_place_preflight,
            patched_manifest=patched_backend_manifest,
            mutation_path=backend_manifest_in_place_mutation_path,
            rollback_path=backend_manifest_rollback_path,
            dry_run=effective_dry_run,
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
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        backend_manifest_recovery = self._apply_backend_manifest_recovery(
            recovery_path=backend_manifest_recovery_path,
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        transaction_idempotency_guard = self._build_transaction_idempotency_guard(
            guard_path=transaction_idempotency_guard_path,
            recovery=backend_manifest_recovery,
            commit=backend_manifest_transaction_commit,
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        if transaction_idempotency_guard and transaction_idempotency_guard.operation == "apply_backend_manifest_recovery":
            backend_manifest_recovery_path = None
        if transaction_idempotency_guard and transaction_idempotency_guard.operation == "commit_cross_run_transaction":
            backend_manifest_transaction_commit_path = None
        if recovery_apply_only and backend_manifest_recovery and not transaction_lock_blocking:
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
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        if external_delivery_result and external_delivery_result.result_path:
            external_delivery_result_path = external_delivery_result.result_path
        external_delivery_performed = bool(external_delivery_result and external_delivery_result.external_delivery_performed)
        if external_delivery_result and not transaction_lock_blocking:
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
        external_delivery_idempotency_ledger = self._build_external_delivery_idempotency_ledger(
            delivery_root=delivery_root,
            ledger_path=external_delivery_idempotency_ledger_path,
            result_path=external_delivery_result_path,
            external_delivery_result=external_delivery_result,
            dry_run=effective_dry_run,
            created_at=created_at,
        )
        if external_delivery_idempotency_ledger and external_delivery_idempotency_ledger.ledger_path:
            external_delivery_idempotency_ledger_path = external_delivery_idempotency_ledger.ledger_path
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
            external_delivery_idempotency_ledger_path=_journal_str(
                previous_journal,
                "external_delivery_idempotency_ledger_path",
                external_delivery_idempotency_ledger_path,
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
        if transaction_idempotency_guard_path and transaction_idempotency_guard:
            _write_json(Path(transaction_idempotency_guard_path), transaction_idempotency_guard.to_dict())
        if external_delivery_result_path and external_delivery_result:
            _write_json(Path(external_delivery_result_path), external_delivery_result.to_dict())
        if external_delivery_idempotency_ledger_path and external_delivery_idempotency_ledger:
            _write_json(Path(external_delivery_idempotency_ledger_path), external_delivery_idempotency_ledger.to_dict())
        if transaction_lock_release_path and transaction_lock_release:
            _write_json(Path(transaction_lock_release_path), transaction_lock_release.to_dict())
        if transaction_lock_path and transaction_lock and transaction_lock.lock_acquired:
            _write_json(Path(transaction_lock_path), transaction_lock.to_dict())
        should_write_journal = bool(journal_path) and (
            (not transaction_commit_only and not recovery_apply_only)
            or bool(backend_manifest_transaction_commit and backend_manifest_transaction_commit.committed)
            or bool(backend_manifest_recovery and backend_manifest_recovery.recovered)
        )
        if should_write_journal:
            _write_json(Path(journal_path), journal.to_dict())
        if lock_release_only:
            next_action = (
                "review_delivery_transaction_lock_release"
                if transaction_lock_release and transaction_lock_release.lock_removed
                else "fix_delivery_transaction_lock_release_blockers"
            )
        elif transaction_lock_blocking:
            next_action = "review_or_release_delivery_transaction_lock"
        elif backend_manifest_mutated:
            next_action = "review_backend_manifest_in_place_mutation_before_cross_run_commit"
        elif backend_manifest_in_place_mutation and backend_manifest_in_place_mutation.blocking_reasons:
            next_action = "fix_backend_manifest_in_place_mutation_blockers"
        elif backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.status == "ready_for_review":
            next_action = "review_backend_manifest_recovery_preflight_before_cross_run_commit"
        elif backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.blocking_reasons:
            next_action = "fix_backend_manifest_recovery_preflight_blockers"
        delivery_allowed = (
            not bool(errors)
            and status != "blocked"
            and not bool(external_delivery_result and external_delivery_result.blocking_reasons)
        )
        result_payload_for_state = {
            "status": status,
            "mode": mode.value,
            "transaction_id": self.config.transaction_id,
            "dry_run": dry_run,
            "delivery_allowed": delivery_allowed,
            "filesystem_artifact_mutated": bool(delivered),
            "external_delivery_performed": external_delivery_performed,
            "cross_run_transaction_committed": cross_run_transaction_committed,
            "manifest_revision_committed": bool(manifest_revision and manifest_revision.committed),
            "backend_manifest_patch_written": bool(backend_manifest_mutation and backend_manifest_mutation.backend_manifest_patch_written),
            "backend_manifest_in_place_preflight_passed": bool(
                backend_manifest_in_place_preflight and backend_manifest_in_place_preflight.in_place_mutation_allowed
            ),
            "backend_manifest_recovery_preflight_passed": bool(
                backend_manifest_recovery_preflight and backend_manifest_recovery_preflight.status in {"ready_for_review", "no_recovery_required"}
            ),
            "backend_manifest_rollback_written": backend_manifest_rollback_written,
            "backend_manifest_mutated": backend_manifest_mutated,
            "backend_manifest_recovered": backend_manifest_recovered,
            "transaction_journal": journal.to_dict(),
            "manifest_revision": manifest_revision.to_dict() if manifest_revision else None,
            "backend_manifest_mutation": backend_manifest_mutation.to_dict() if backend_manifest_mutation else None,
            "backend_manifest_in_place_preflight": backend_manifest_in_place_preflight.to_dict() if backend_manifest_in_place_preflight else None,
            "backend_manifest_in_place_mutation": backend_manifest_in_place_mutation.to_dict() if backend_manifest_in_place_mutation else None,
            "backend_manifest_recovery_preflight": backend_manifest_recovery_preflight.to_dict() if backend_manifest_recovery_preflight else None,
            "backend_manifest_recovery": backend_manifest_recovery.to_dict() if backend_manifest_recovery else None,
            "backend_manifest_transaction_commit": backend_manifest_transaction_commit.to_dict() if backend_manifest_transaction_commit else None,
            "transaction_lock": transaction_lock.to_dict() if transaction_lock else None,
            "transaction_lock_release": transaction_lock_release.to_dict() if transaction_lock_release else None,
            "transaction_idempotency_guard": transaction_idempotency_guard.to_dict() if transaction_idempotency_guard else None,
            "external_delivery_result": external_delivery_result.to_dict() if external_delivery_result else None,
            "external_delivery_idempotency_ledger": (
                external_delivery_idempotency_ledger.to_dict() if external_delivery_idempotency_ledger else None
            ),
            "planned_artifacts": planned,
            "errors": errors,
            "next_action": next_action,
        }
        transaction_state = evaluate_delivery_transaction_state(result_payload_for_state)
        return DeliveryExecutionResult(
            status=status,
            mode=mode.value,
            transaction_id=self.config.transaction_id,
            dry_run=dry_run,
            delivery_allowed=delivery_allowed,
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
            transaction_state=transaction_state,
            manifest_revision=manifest_revision,
            backend_manifest_mutation=backend_manifest_mutation,
            backend_manifest_in_place_preflight=backend_manifest_in_place_preflight,
            backend_manifest_in_place_mutation=backend_manifest_in_place_mutation,
            backend_manifest_recovery_preflight=backend_manifest_recovery_preflight,
            backend_manifest_recovery=backend_manifest_recovery,
            backend_manifest_transaction_commit=backend_manifest_transaction_commit,
            transaction_lock=transaction_lock,
            transaction_lock_release=transaction_lock_release,
            transaction_idempotency_guard=transaction_idempotency_guard,
            external_delivery_result=external_delivery_result,
            external_delivery_idempotency_ledger=external_delivery_idempotency_ledger,
            planned_artifacts=planned,
            errors=errors,
            next_action=next_action,
        )

    def _build_transaction_idempotency_guard(
        self,
        *,
        guard_path: str | None,
        recovery: BackendManifestRecovery | None,
        commit: BackendManifestTransactionCommit | None,
        dry_run: bool,
        created_at: str,
    ) -> DeliveryTransactionIdempotencyGuard | None:
        if dry_run:
            return None
        operation: str | None = None
        terminal_artifact_kind: str | None = None
        terminal_artifact_path: str | None = None
        terminal_artifact_successful = False
        journal_terminal_flag = False
        journal_path: str | None = None
        if recovery and not recovery.recovered:
            operation = "apply_backend_manifest_recovery"
            terminal_artifact_kind = "backend_manifest_recovery"
            terminal_artifact_path = recovery.recovery_path
            journal_path = recovery.transaction_journal_path
            journal_terminal_flag = "journal_not_already_recovered" in recovery.blocking_reasons
            terminal_artifact_successful = _terminal_recovery_artifact_succeeded(terminal_artifact_path)
        if commit and not commit.committed:
            operation = "commit_cross_run_transaction"
            terminal_artifact_kind = "backend_manifest_transaction_commit"
            terminal_artifact_path = commit.commit_path
            journal_path = commit.transaction_journal_path
            journal_terminal_flag = "journal_not_already_cross_run_committed" in commit.blocking_reasons
            terminal_artifact_successful = _terminal_commit_artifact_succeeded(terminal_artifact_path)
        duplicate_guard_triggered = bool(operation and (journal_terminal_flag or terminal_artifact_successful))
        if not duplicate_guard_triggered or operation is None or terminal_artifact_kind is None:
            return None
        terminal_artifact_exists = bool(terminal_artifact_path and Path(terminal_artifact_path).expanduser().exists())
        checks = [
            {
                "name": "terminal_journal_flag_not_already_set",
                "passed": not journal_terminal_flag,
                "details": {
                    "operation": operation,
                    "journal_terminal_flag_set": journal_terminal_flag,
                },
            },
            {
                "name": "terminal_artifact_not_already_successful",
                "passed": not terminal_artifact_successful,
                "details": {
                    "terminal_artifact_path": terminal_artifact_path,
                    "terminal_artifact_exists": terminal_artifact_exists,
                    "terminal_artifact_successful": terminal_artifact_successful,
                },
            },
            {
                "name": "terminal_artifact_preserved_on_duplicate",
                "passed": True,
                "details": {
                    "terminal_artifact_path": terminal_artifact_path,
                    "terminal_artifact_will_be_overwritten": False,
                },
            },
        ]
        return DeliveryTransactionIdempotencyGuard(
            transaction_id=self.config.transaction_id,
            status="duplicate_blocked",
            operation=operation,
            guard_path=guard_path,
            delivery_root=str(self.config.resolved_delivery_root()),
            transaction_journal_path=journal_path,
            terminal_artifact_path=terminal_artifact_path,
            terminal_artifact_kind=terminal_artifact_kind,
            dry_run=dry_run,
            duplicate_guard_triggered=True,
            terminal_artifact_preserved=True,
            checks=checks,
            blocking_reasons=[check["name"] for check in checks if not check["passed"]],
            recommended_actions=[
                "inspect_existing_terminal_transaction_artifact",
                "start_new_delivery_transaction_for_additional_changes",
            ],
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "delivery-transaction-idempotency-guard-baseline",
                "operation": operation,
                "duplicate_terminal_action_blocked": True,
                "terminal_artifact_preserved": True,
                "limitations": [
                    "single_delivery_root_guard_record",
                    "does_not_distribute_transaction_locks",
                    "does_not_retry_or_publish_external_delivery",
                ],
            },
        )

    def _transaction_lock_operation(self, artifacts: list[DeliveryArtifact]) -> str | None:
        if self.config.mode == DeliveryExecutionMode.DRY_RUN:
            return None
        if self.config.release_transaction_lock:
            return None
        if self.config.apply_backend_manifest_recovery:
            return "apply_backend_manifest_recovery"
        if self.config.commit_cross_run_transaction:
            return "commit_cross_run_transaction"
        if self.config.request_external_delivery:
            return "request_external_delivery"
        if self.config.approve_backend_manifest_in_place_mutation:
            return "approve_backend_manifest_in_place_mutation"
        if artifacts:
            return "local_delivery_apply"
        return None

    def _build_transaction_lock_release(
        self,
        *,
        release_path: str | None,
        dry_run: bool,
        created_at: str,
    ) -> DeliveryTransactionLockRelease | None:
        if not self.config.release_transaction_lock:
            return None
        delivery_root = self.config.resolved_delivery_root()
        resolved_lock_path = (delivery_root / self.config.transaction_lock_name).resolve()
        resolved_release_path = Path(release_path).expanduser().resolve() if release_path else None
        owner = str(self.config.transaction_lock_owner or "").strip() or None
        expected_owner = str(self.config.expected_transaction_lock_owner or owner or "").strip() or None
        expected_lock_transaction_id = str(self.config.expected_transaction_lock_transaction_id or "").strip() or None
        expected_resume_token = str(self.config.expected_resume_token or "").strip() or None
        existing_lock_present = resolved_lock_path.exists()
        existing_lock: dict[str, Any] | None = None
        existing_lock_load_error: str | None = None
        if existing_lock_present:
            try:
                existing_lock = _read_json_object(resolved_lock_path)
            except Exception as exc:  # noqa: BLE001 - malformed lock must not be removed automatically.
                existing_lock_load_error = str(exc)
                existing_lock = {}
        existing_owner = str(existing_lock.get("owner") or "") if existing_lock else ""
        existing_transaction_id = str(existing_lock.get("transaction_id") or "") if existing_lock else ""
        existing_resume_token = str(existing_lock.get("resume_token") or "") if existing_lock else ""
        existing_lease_expires_at = str(existing_lock.get("lease_expires_at") or "") if existing_lock else ""
        stale_lock_detected = bool(existing_lock_present and existing_lock) and _iso_datetime_is_past(existing_lease_expires_at, created_at)
        owner_matches = not expected_owner or (existing_owner == expected_owner)
        transaction_id_matches = not expected_lock_transaction_id or (existing_transaction_id == expected_lock_transaction_id)
        resume_token_matches = not expected_resume_token or (existing_resume_token == expected_resume_token)
        approval_passed = dry_run or bool(self.config.approve_transaction_lock_release)
        checks = [
            {
                "name": "transaction_lock_file_exists",
                "passed": existing_lock_present,
                "details": {"lock_path": str(resolved_lock_path)},
            },
            {
                "name": "transaction_lock_file_is_valid",
                "passed": existing_lock_load_error is None,
                "details": {"load_error": existing_lock_load_error, "lock_path": str(resolved_lock_path)},
            },
            {
                "name": "transaction_lock_release_approved",
                "passed": approval_passed,
                "details": {
                    "dry_run": dry_run,
                    "approve_transaction_lock_release": self.config.approve_transaction_lock_release,
                },
            },
            {
                "name": "expected_transaction_lock_owner_matches",
                "passed": owner_matches,
                "details": {"expected_owner": expected_owner, "existing_owner": existing_owner or None},
            },
            {
                "name": "expected_transaction_lock_transaction_id_matches",
                "passed": transaction_id_matches,
                "details": {
                    "expected_transaction_id": expected_lock_transaction_id,
                    "existing_transaction_id": existing_transaction_id or None,
                },
            },
            {
                "name": "expected_resume_token_matches_lock",
                "passed": resume_token_matches,
                "details": {
                    "expected_resume_token_configured": bool(expected_resume_token),
                    "existing_resume_token_present": bool(existing_resume_token),
                    "resume_token_matches": resume_token_matches,
                },
            },
            {
                "name": "stale_lock_reviewed",
                "passed": True,
                "details": {
                    "stale_lock_detected": stale_lock_detected,
                    "existing_lease_expires_at": existing_lease_expires_at or None,
                },
            },
        ]
        if not existing_lock_present:
            blocking_reasons: list[str] = []
            status = "planned" if dry_run else "no_lock_found"
        else:
            blocking_reasons = [
                check["name"]
                for check in checks
                if not check["passed"] and check["name"] != "transaction_lock_file_exists"
            ]
            status = "planned" if dry_run else "blocked" if blocking_reasons else "release_ready"
        lock_removed = False
        if status == "release_ready" and not dry_run:
            try:
                resolved_lock_path.unlink()
                lock_removed = True
                status = "released"
            except Exception as exc:  # noqa: BLE001 - report filesystem release failures as blockers.
                checks.append(
                    {
                        "name": "transaction_lock_file_removed",
                        "passed": False,
                        "details": {"error": str(exc), "lock_path": str(resolved_lock_path)},
                    }
                )
                blocking_reasons.append("transaction_lock_file_removed")
                status = "blocked"
        elif status == "release_ready":
            status = "planned"
        if lock_removed:
            checks.append(
                {
                    "name": "transaction_lock_file_removed",
                    "passed": True,
                    "details": {"lock_path": str(resolved_lock_path)},
                }
            )
        if status == "released":
            recommended_actions = ["review_delivery_transaction_lock_release"]
        elif status == "no_lock_found":
            recommended_actions = ["continue_without_delivery_transaction_lock_release"]
        elif blocking_reasons:
            recommended_actions = ["fix_delivery_transaction_lock_release_blockers"]
        else:
            recommended_actions = ["approve_delivery_transaction_lock_release"]
        return DeliveryTransactionLockRelease(
            transaction_id=self.config.transaction_id,
            status=status,
            operation="release_delivery_transaction_lock",
            lock_path=str(resolved_lock_path),
            release_path=str(resolved_release_path) if resolved_release_path else None,
            delivery_root=str(delivery_root),
            owner=owner,
            expected_owner=expected_owner,
            expected_lock_transaction_id=expected_lock_transaction_id,
            expected_resume_token=expected_resume_token,
            dry_run=dry_run,
            approval_required=True,
            release_approved=bool(self.config.approve_transaction_lock_release),
            lock_removed=lock_removed,
            stale_lock_detected=stale_lock_detected,
            existing_lock=existing_lock if existing_lock else None,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=recommended_actions,
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "delivery-transaction-lock-release-review-baseline",
                "local_file_lock": True,
                "distributed_lock": False,
                "automatic_stale_lock_takeover": False,
                "release_requires_explicit_approval": True,
                "limitations": [
                    "local_delivery_root_lock_release_only",
                    "does_not_provide_distributed_consensus",
                    "does_not_renew_leases",
                    "does_not_auto_take_over_stale_locks",
                    "does_not_resume_transactions",
                ],
            },
        )

    def _build_transaction_lock(
        self,
        *,
        lock_path: str | None,
        operation: str | None,
        dry_run: bool,
        created_at: str,
    ) -> DeliveryTransactionLock | None:
        if not self.config.require_transaction_lock or operation is None:
            return None
        delivery_root = self.config.resolved_delivery_root()
        owner = str(self.config.transaction_lock_owner or self.config.transaction_id).strip() or self.config.transaction_id
        expected_resume_token = str(self.config.expected_resume_token or "").strip() or None
        resolved_lock_path = Path(lock_path).expanduser().resolve() if lock_path else (delivery_root / self.config.transaction_lock_name).resolve()
        existing_lock: dict[str, Any] | None = None
        existing_lock_load_error: str | None = None
        if resolved_lock_path.exists():
            try:
                existing_lock = _read_json_object(resolved_lock_path)
            except Exception as exc:  # noqa: BLE001 - malformed lock should block apply actions.
                existing_lock_load_error = str(exc)
                existing_lock = {}
        existing_owner = str(existing_lock.get("owner") or "") if existing_lock else ""
        existing_resume_token = str(existing_lock.get("resume_token") or "") if existing_lock else ""
        existing_transaction_id = str(existing_lock.get("transaction_id") or "") if existing_lock else ""
        existing_lease_expires_at = str(existing_lock.get("lease_expires_at") or "") if existing_lock else ""
        stale_lock_detected = bool(existing_lock) and _iso_datetime_is_past(existing_lease_expires_at, created_at)
        same_owner = bool(existing_lock) and existing_owner == owner
        resume_matches = bool(expected_resume_token and existing_resume_token and expected_resume_token == existing_resume_token)
        existing_lock_blocks = bool(existing_lock) and not stale_lock_detected and not same_owner and not resume_matches
        resume_required_but_missing = bool(expected_resume_token and not resume_matches and existing_lock)
        checks = [
            {
                "name": "transaction_lock_required_for_apply",
                "passed": True,
                "details": {"require_transaction_lock": True, "operation": operation},
            },
            {
                "name": "transaction_lock_file_is_valid",
                "passed": existing_lock_load_error is None,
                "details": {"load_error": existing_lock_load_error, "lock_path": str(resolved_lock_path)},
            },
            {
                "name": "transaction_lock_not_held_by_other_owner",
                "passed": not existing_lock_blocks,
                "details": {
                    "owner": owner,
                    "existing_owner": existing_owner or None,
                    "existing_transaction_id": existing_transaction_id or None,
                    "stale_lock_detected": stale_lock_detected,
                    "resume_token_matches": resume_matches,
                },
            },
            {
                "name": "expected_resume_token_matches_lock",
                "passed": not resume_required_but_missing,
                "details": {
                    "expected_resume_token_configured": bool(expected_resume_token),
                    "existing_resume_token_present": bool(existing_resume_token),
                    "resume_token_matches": resume_matches,
                },
            },
            {
                "name": "stale_lock_requires_manual_cleanup",
                "passed": not stale_lock_detected,
                "details": {
                    "stale_lock_detected": stale_lock_detected,
                    "existing_lease_expires_at": existing_lease_expires_at or None,
                },
            },
        ]
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        lease_expires_at = None
        if not dry_run and not blocking_reasons:
            lease_expires_at = (
                datetime.fromisoformat(created_at).astimezone(timezone.utc)
                + timedelta(seconds=max(1, int(self.config.transaction_lock_lease_seconds)))
            ).isoformat()
        resume_token = expected_resume_token or _json_payload_sha256(
            {
                "transaction_id": self.config.transaction_id,
                "owner": owner,
                "operation": operation,
                "created_at": created_at,
            }
        )
        if existing_lock and (same_owner or resume_matches) and existing_resume_token:
            resume_token = existing_resume_token
        status = "blocked" if blocking_reasons else "planned" if dry_run else "acquired"
        return DeliveryTransactionLock(
            transaction_id=self.config.transaction_id,
            status=status,
            operation=operation,
            lock_path=str(resolved_lock_path) if lock_path or not dry_run else None,
            delivery_root=str(delivery_root),
            owner=owner,
            resume_token=resume_token if not blocking_reasons else existing_resume_token or resume_token,
            expected_resume_token=expected_resume_token,
            lease_expires_at=lease_expires_at if not blocking_reasons else existing_lease_expires_at or None,
            dry_run=dry_run,
            lock_required=True,
            lock_acquired=status == "acquired",
            resume_accepted=bool(existing_lock and (same_owner or resume_matches) and not blocking_reasons),
            stale_lock_detected=stale_lock_detected,
            existing_lock=existing_lock if existing_lock else None,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=(
                ["review_or_release_existing_delivery_transaction_lock"]
                if blocking_reasons
                else ["continue_delivery_transaction_with_lock"]
            ),
            created_at=created_at,
            metadata={
                **self.config.metadata,
                "executor": "local-filesystem",
                "scope": "delivery-transaction-lock-preflight-baseline",
                "local_file_lock": True,
                "distributed_lock": False,
                "automatic_stale_lock_takeover": False,
                "limitations": [
                    "local_delivery_root_lock_only",
                    "does_not_provide_distributed_consensus",
                    "does_not_auto_take_over_stale_locks",
                    "resume_token_is_local_audit_token",
                ],
            },
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
        provider_factory_invoked = False
        if provider is None:
            registry = self.config.external_delivery_provider_registry
            if registry is None:
                from reverse_deepagent.delivery.registry import build_default_external_delivery_provider_registry

                registry = build_default_external_delivery_provider_registry()
            provider = registry.create(
                self.config.external_delivery_provider_id,
                **self.config.external_delivery_provider_config,
            )
            provider_factory_invoked = True
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
                "external_delivery_provider_config_summary": _external_delivery_provider_config_summary(
                    self.config.external_delivery_provider_config
                ),
                "external_delivery_idempotency_key": self._external_delivery_idempotency_key(),
                "allow_duplicate_external_delivery": self.config.allow_duplicate_external_delivery,
                "provider_factory_invoked": provider_factory_invoked,
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

    def _build_external_delivery_idempotency_ledger(
        self,
        *,
        delivery_root: Path,
        ledger_path: str | None,
        result_path: str | None,
        external_delivery_result: ExternalDeliveryResult | None,
        dry_run: bool,
        created_at: str,
    ) -> ExternalDeliveryIdempotencyLedger | None:
        if not self.config.request_external_delivery or external_delivery_result is None:
            return None
        idempotency_key = self._external_delivery_idempotency_key()
        resolved_ledger_path = Path(ledger_path).expanduser().resolve() if ledger_path else None
        previous_entries: list[dict[str, Any]] = []
        previous_metadata: dict[str, Any] = {}
        previous_ledger_load_error: str | None = None
        if resolved_ledger_path and resolved_ledger_path.exists():
            try:
                previous_ledger = _read_json_object(resolved_ledger_path)
            except Exception as exc:  # noqa: BLE001 - audit artifact should not mask delivery result.
                previous_ledger_load_error = str(exc)
            else:
                raw_entries = previous_ledger.get("entries")
                if isinstance(raw_entries, list):
                    previous_entries = [dict(item) for item in raw_entries if isinstance(item, dict)]
                previous_metadata = previous_ledger.get("metadata") if isinstance(previous_ledger.get("metadata"), dict) else {}
        metadata = external_delivery_result.metadata if isinstance(external_delivery_result.metadata, dict) else {}
        attempt_summary = _external_delivery_attempt_summary(external_delivery_result)
        entry = {
            "entry_id": f"{self.config.transaction_id}:{len(previous_entries) + 1}",
            "transaction_id": self.config.transaction_id,
            "idempotency_key": idempotency_key,
            "provider_id": external_delivery_result.provider_id,
            "status": external_delivery_result.status,
            "result_path": external_delivery_result.result_path or result_path,
            "external_delivery_performed": external_delivery_result.external_delivery_performed,
            "duplicate_guard_triggered": bool(metadata.get("duplicate_guard_triggered")),
            "allow_duplicate_external_delivery": self.config.allow_duplicate_external_delivery,
            "provider_factory_invoked": _external_delivery_provider_factory_invoked(metadata),
            "package_digest_sha256": external_delivery_result.package_digest_sha256,
            "blocking_reasons": list(external_delivery_result.blocking_reasons),
            "recommended_actions": list(external_delivery_result.recommended_actions),
            "attempt_summary": attempt_summary,
            "created_at": created_at,
        }
        entries = [*previous_entries, entry]
        ledger_metadata = {
            **previous_metadata,
            "schema_version": "reverse-deepagent.external-delivery-idempotency-ledger.v1",
            "scope": "external-delivery-idempotency-ledger-baseline",
            "append_only_audit": True,
            "dry_run": dry_run,
            "raw_request_headers_recorded": False,
            "raw_response_headers_recorded": False,
            "response_body_recorded": False,
            "provider_config_values_recorded": False,
            "does_not_publish_external_delivery": True,
            "does_not_retry_external_delivery": True,
            "does_not_restore_or_mutate_manifest": True,
            "limitations": [
                "ledger_is_audit_only",
                "does_not_replace_duplicate_guard",
                "does_not_execute_recovery",
                "full_cross_run_transaction_state_machine_not_implemented",
            ],
        }
        if entry["duplicate_guard_triggered"]:
            ledger_metadata["limitations"].append("duplicate_guard_blocks_provider_invocation")
        if previous_ledger_load_error:
            ledger_metadata["previous_ledger_load_error"] = previous_ledger_load_error
        return ExternalDeliveryIdempotencyLedger(
            transaction_id=self.config.transaction_id,
            idempotency_key=idempotency_key,
            provider_id=external_delivery_result.provider_id,
            status=external_delivery_result.status,
            ledger_path=str(resolved_ledger_path) if resolved_ledger_path else None,
            delivery_root=str(delivery_root),
            external_delivery_result_path=external_delivery_result.result_path or result_path,
            external_delivery_performed=external_delivery_result.external_delivery_performed,
            duplicate_guard_triggered=bool(metadata.get("duplicate_guard_triggered")),
            allow_duplicate_external_delivery=self.config.allow_duplicate_external_delivery,
            provider_factory_invoked=_external_delivery_provider_factory_invoked(metadata),
            entry_count=len(entries),
            entries=entries,
            created_at=created_at,
            metadata=ledger_metadata,
        )

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


def _iso_datetime_is_past(value: str | None, now_value: str) -> bool:
    if not value:
        return False
    try:
        candidate = datetime.fromisoformat(value)
        now = datetime.fromisoformat(now_value)
    except ValueError:
        return False
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc) < now.astimezone(timezone.utc)


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


def _terminal_recovery_artifact_succeeded(path_value: str | None) -> bool:
    if not path_value:
        return False
    path = Path(path_value).expanduser()
    if not path.exists():
        return False
    payload = _read_json_object(path)
    return bool(payload.get("recovered")) or str(payload.get("status") or "") == "recovered"


def _terminal_commit_artifact_succeeded(path_value: str | None) -> bool:
    if not path_value:
        return False
    path = Path(path_value).expanduser()
    if not path.exists():
        return False
    payload = _read_json_object(path)
    return bool(payload.get("committed")) or str(payload.get("status") or "") == "committed"


def _safe_archive_component(value: Any) -> str:
    raw = str(value).replace("\\", "/").split("/")[-1].strip()
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "-" for character in raw)
    safe = safe.strip(".")
    if not safe or safe in {".", ".."}:
        raise ValueError(f"Invalid archive path component: {value!r}")
    return safe


EXTERNAL_DELIVERY_SECRET_KEYWORDS = (
    "key",
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "credential",
    "private",
)


def external_delivery_metadata_has_secret_like_keys(value: Any) -> bool:
    """Return True when a JSON-like metadata object exposes secret-like key names."""

    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(keyword in lowered for keyword in EXTERNAL_DELIVERY_SECRET_KEYWORDS):
                return True
            if external_delivery_metadata_has_secret_like_keys(item):
                return True
        return False
    if isinstance(value, list):
        return any(external_delivery_metadata_has_secret_like_keys(item) for item in value)
    return False


def _count_external_delivery_secret_like_keys(value: Any) -> int:
    if isinstance(value, dict):
        total = 0
        for key, item in value.items():
            if any(keyword in str(key).lower() for keyword in EXTERNAL_DELIVERY_SECRET_KEYWORDS):
                total += 1
            total += _count_external_delivery_secret_like_keys(item)
        return total
    if isinstance(value, list):
        return sum(_count_external_delivery_secret_like_keys(item) for item in value)
    return 0


def _external_delivery_provider_config_summary(config: dict[str, Any]) -> dict[str, Any]:
    if not config:
        return {
            "configured": False,
            "key_count": 0,
            "non_secret_keys": [],
            "secret_like_key_count": 0,
            "raw_values_exported": False,
        }
    non_secret_keys: list[str] = []
    secret_like_key_count = _count_external_delivery_secret_like_keys(config)
    for key in sorted(str(item) for item in config):
        if external_delivery_metadata_has_secret_like_keys({key: None}):
            continue
        non_secret_keys.append(key)
    return {
        "configured": True,
        "key_count": len(config),
        "non_secret_keys": non_secret_keys,
        "secret_like_key_count": secret_like_key_count,
        "raw_values_exported": False,
    }


def _external_delivery_provider_factory_invoked(metadata: dict[str, Any]) -> bool | None:
    if "provider_factory_invoked" in metadata:
        return bool(metadata.get("provider_factory_invoked"))
    if metadata.get("duplicate_guard_triggered"):
        return False
    return None


def _http_attempts_policy_summary(attempts: Any) -> dict[str, Any]:
    safe_attempts = [item for item in attempts if isinstance(item, dict)] if isinstance(attempts, list) else []
    retry_count = sum(1 for item in safe_attempts if bool(item.get("will_retry")))
    retry_after_seen = any(bool(item.get("retry_after_seen")) for item in safe_attempts)
    retry_after_honored = any(bool(item.get("retry_after_honored")) for item in safe_attempts)
    retry_budget_exhausted = any(
        bool(item.get("retryable")) and not bool(item.get("will_retry"))
        for item in safe_attempts[-1:]
    )
    rate_limit_seen = any(
        isinstance(item.get("rate_limit"), dict) and bool(item.get("rate_limit", {}).get("headers_present"))
        for item in safe_attempts
    )
    planned_retry_delay_seconds_total = 0.0
    max_planned_retry_delay_seconds = 0.0
    jitter_seconds_configured = 0.0
    for item in safe_attempts:
        planned_delay = _float_or_default(item.get("planned_retry_delay_seconds"), 0.0)
        planned_retry_delay_seconds_total += planned_delay
        max_planned_retry_delay_seconds = max(max_planned_retry_delay_seconds, planned_delay)
        jitter_seconds_configured = max(jitter_seconds_configured, _float_or_default(item.get("jitter_seconds_configured"), 0.0))
    return {
        "attempt_count": len(safe_attempts),
        "retry_count": retry_count,
        "retry_after_seen": retry_after_seen,
        "retry_after_honored": retry_after_honored,
        "retry_budget_exhausted": retry_budget_exhausted,
        "rate_limit_seen": rate_limit_seen,
        "planned_retry_delay_seconds_total": planned_retry_delay_seconds_total,
        "max_planned_retry_delay_seconds": max_planned_retry_delay_seconds,
        "jitter_seconds_configured": jitter_seconds_configured,
        "headers_recorded": False,
        "response_body_recorded": False,
    }


def _external_delivery_attempt_summary(result: ExternalDeliveryResult) -> dict[str, Any]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    stages: list[dict[str, Any]] = []
    if isinstance(metadata.get("request_attempts"), list):
        stages.append(
            _external_delivery_attempt_stage(
                "request",
                metadata.get("request_attempt_count"),
                metadata.get("request_retry_count"),
                metadata.get("request_attempts"),
            )
        )
    for stage_name in (
        "release_request",
        "existing_release_lookup",
        "asset_lookup",
        "existing_asset_delete",
        "upload_request",
    ):
        attempts_key = f"{stage_name}_attempts"
        if isinstance(metadata.get(attempts_key), list):
            stages.append(
                _external_delivery_attempt_stage(
                    stage_name,
                    metadata.get(f"{stage_name}_attempt_count"),
                    metadata.get(f"{stage_name}_retry_count"),
                    metadata.get(attempts_key),
                )
            )
    attempt_count = sum(int(stage.get("attempt_count") or 0) for stage in stages)
    retry_count = sum(int(stage.get("retry_count") or 0) for stage in stages)
    return {
        "attempt_count": attempt_count,
        "retry_count": retry_count,
        "stage_count": len(stages),
        "stages": stages,
        "attempt_metadata_recorded": bool(stages),
        "retry_after_seen": any(bool(stage.get("retry_after_seen")) for stage in stages),
        "retry_after_honored": any(bool(stage.get("retry_after_honored")) for stage in stages),
        "retry_budget_exhausted": any(bool(stage.get("retry_budget_exhausted")) for stage in stages),
        "rate_limit_seen": any(bool(stage.get("rate_limit_seen")) for stage in stages),
        "headers_recorded": False,
        "response_body_recorded": False,
    }


def _external_delivery_attempt_stage(
    stage_name: str,
    attempt_count: Any,
    retry_count: Any,
    attempts: Any,
) -> dict[str, Any]:
    safe_attempts: list[dict[str, Any]] = []
    if isinstance(attempts, list):
        for item in attempts:
            if not isinstance(item, dict):
                continue
            safe_attempts.append(
                {
                    "attempt": item.get("attempt"),
                    "status_code": item.get("status_code"),
                    "error": item.get("error"),
                    "retryable": bool(item.get("retryable")),
                    "will_retry": bool(item.get("will_retry")),
                    "retry_after_seconds": item.get("retry_after_seconds"),
                    "retry_after_seen": bool(item.get("retry_after_seen")),
                    "retry_after_honored": bool(item.get("retry_after_honored")),
                    "planned_retry_delay_seconds": _float_or_default(item.get("planned_retry_delay_seconds"), 0.0),
                    "jitter_seconds_configured": _float_or_default(item.get("jitter_seconds_configured"), 0.0),
                    "rate_limit": _safe_rate_limit_summary(item.get("rate_limit")),
                }
            )
    return {
        "stage": stage_name,
        "attempt_count": _int_or_len(attempt_count, safe_attempts),
        "retry_count": _int_or_default(retry_count, max(0, len(safe_attempts) - 1)),
        "attempts": safe_attempts,
        "retry_after_seen": any(bool(item.get("retry_after_seen")) for item in safe_attempts),
        "retry_after_honored": any(bool(item.get("retry_after_honored")) for item in safe_attempts),
        "retry_budget_exhausted": any(
            bool(item.get("retryable")) and not bool(item.get("will_retry"))
            for item in safe_attempts[-1:]
        ),
        "rate_limit_seen": any(bool(item.get("rate_limit", {}).get("headers_present")) for item in safe_attempts),
    }


def _safe_rate_limit_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return _empty_rate_limit_summary()
    return {
        "headers_present": bool(value.get("headers_present")),
        "limit": _optional_int(value.get("limit")),
        "remaining": _optional_int(value.get("remaining")),
        "reset_epoch": _optional_int(value.get("reset_epoch")),
        "used": _optional_int(value.get("used")),
        "resource": str(value.get("resource")) if value.get("resource") is not None else None,
        "retry_after_seconds": _optional_int(value.get("retry_after_seconds")),
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_len(value: Any, items: list[Any]) -> int:
    return _int_or_default(value, len(items))


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_external_delivery_url(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_webhook_url(value: str | None) -> str:
    return _normalize_external_delivery_url(value)


def _http_scheme_supported(value: str) -> bool:
    if not value:
        return False
    return urllib.parse.urlsplit(value).scheme.lower() in {"http", "https"}


def _webhook_scheme_supported(value: str) -> bool:
    return _http_scheme_supported(value)


def _coerce_retry_attempts(value: Any) -> int:
    try:
        attempts = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(attempts, 5))


def _coerce_retry_backoff_seconds(value: Any) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(seconds, 30.0))


def _coerce_retry_jitter_seconds(value: Any) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(seconds, 5.0))


def _coerce_retry_status_codes(value: Any) -> tuple[int, ...]:
    if value is None:
        return DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]
    status_codes: list[int] = []
    for item in raw_items:
        try:
            status_code = int(item)
        except (TypeError, ValueError):
            continue
        if 100 <= status_code <= 599 and status_code not in status_codes:
            status_codes.append(status_code)
    return tuple(status_codes) if status_codes else DEFAULT_EXTERNAL_DELIVERY_RETRY_STATUS_CODES


def _retry_after_seconds_from_headers(headers: Any) -> int | None:
    value = _header_value(headers, "Retry-After")
    if value is None:
        return None
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return max(0, min(seconds, 3600))


def _header_value(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    try:
        value = headers.get(name)
    except AttributeError:
        value = None
    if value is None:
        try:
            value = headers.get(name.lower())
        except AttributeError:
            value = None
    if value is None:
        return None
    return str(value)


def _empty_rate_limit_summary() -> dict[str, Any]:
    return {
        "headers_present": False,
        "limit": None,
        "remaining": None,
        "reset_epoch": None,
        "used": None,
        "resource": None,
        "retry_after_seconds": None,
    }


def _rate_limit_summary_from_headers(headers: Any) -> dict[str, Any]:
    summary = _empty_rate_limit_summary()
    limit = _int_header(headers, "X-RateLimit-Limit")
    remaining = _int_header(headers, "X-RateLimit-Remaining")
    reset_epoch = _int_header(headers, "X-RateLimit-Reset")
    used = _int_header(headers, "X-RateLimit-Used")
    resource = _header_value(headers, "X-RateLimit-Resource")
    retry_after_seconds = _retry_after_seconds_from_headers(headers)
    headers_present = any(
        value is not None
        for value in (limit, remaining, reset_epoch, used, resource, retry_after_seconds)
    )
    summary.update(
        {
            "headers_present": headers_present,
            "limit": limit,
            "remaining": remaining,
            "reset_epoch": reset_epoch,
            "used": used,
            "resource": resource,
            "retry_after_seconds": retry_after_seconds,
        }
    )
    return summary


def _int_header(headers: Any, name: str) -> int | None:
    value = _header_value(headers, name)
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _planned_retry_delay_seconds(
    *,
    attempt_number: int,
    backoff_seconds: float,
    retry_after_seconds: int | None,
    honor_retry_after: bool,
    jitter_seconds: float,
) -> float:
    exponential_backoff = backoff_seconds * (2 ** (attempt_number - 1)) if backoff_seconds > 0 else 0.0
    retry_after_delay = float(retry_after_seconds or 0) if honor_retry_after else 0.0
    base_delay = max(exponential_backoff, retry_after_delay) if exponential_backoff > 0 else 0.0
    if base_delay <= 0:
        return 0.0
    return min(3600.0, base_delay + jitter_seconds)


def _http_request_with_retries(
    request_factory: Any,
    *,
    timeout_seconds: float,
    retry_attempts: Any = 0,
    retry_status_codes: Any = None,
    retry_backoff_seconds: Any = 0.0,
    honor_retry_after: Any = True,
    retry_jitter_seconds: Any = 0.0,
    read_response_body: bool = False,
) -> ExternalDeliveryHttpRequestResult:
    max_retries = _coerce_retry_attempts(retry_attempts)
    retryable_status_codes = set(_coerce_retry_status_codes(retry_status_codes))
    backoff_seconds = _coerce_retry_backoff_seconds(retry_backoff_seconds)
    jitter_seconds = _coerce_retry_jitter_seconds(retry_jitter_seconds)
    honor_retry_after_flag = bool(honor_retry_after)
    total_attempts = max_retries + 1
    attempts: list[dict[str, Any]] = []
    final_status_code: int | None = None
    final_error: str | None = None
    final_body = b""
    retry_after_seen = False
    retry_after_honored = False
    retry_budget_exhausted = False
    for attempt_number in range(1, total_attempts + 1):
        status_code: int | None = None
        error: str | None = None
        body = b""
        retry_after_seconds: int | None = None
        rate_limit_summary: dict[str, Any] = _empty_rate_limit_summary()
        try:
            request = request_factory()
            with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
                body = response.read() if read_response_body else response.read(0)
                status_code = int(response.status)
                retry_after_seconds = _retry_after_seconds_from_headers(response.headers)
                rate_limit_summary = _rate_limit_summary_from_headers(response.headers)
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            retry_after_seconds = _retry_after_seconds_from_headers(exc.headers)
            rate_limit_summary = _rate_limit_summary_from_headers(exc.headers)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            error = exc.__class__.__name__
        retryable = bool(error or (status_code in retryable_status_codes))
        will_retry = retryable and attempt_number < total_attempts
        retry_after_seen = retry_after_seen or retry_after_seconds is not None
        planned_delay_seconds = _planned_retry_delay_seconds(
            attempt_number=attempt_number,
            backoff_seconds=backoff_seconds,
            retry_after_seconds=retry_after_seconds,
            honor_retry_after=honor_retry_after_flag,
            jitter_seconds=jitter_seconds,
        ) if will_retry else 0.0
        retry_after_honored_this_attempt = bool(
            will_retry
            and honor_retry_after_flag
            and retry_after_seconds is not None
            and planned_delay_seconds > 0
            and planned_delay_seconds >= float(retry_after_seconds)
        )
        retry_after_honored = retry_after_honored or retry_after_honored_this_attempt
        retry_budget_exhausted = bool(retryable and not will_retry and attempt_number >= total_attempts)
        attempts.append(
            {
                "attempt": attempt_number,
                "status_code": status_code,
                "error": error,
                "retryable": retryable,
                "will_retry": will_retry,
                "retry_after_seconds": retry_after_seconds,
                "retry_after_seen": retry_after_seconds is not None,
                "retry_after_honored": retry_after_honored_this_attempt,
                "planned_retry_delay_seconds": planned_delay_seconds,
                "jitter_seconds_configured": jitter_seconds,
                "rate_limit": rate_limit_summary,
            }
        )
        final_status_code = status_code
        final_error = error
        final_body = body
        if not will_retry:
            break
        if planned_delay_seconds > 0:
            time.sleep(planned_delay_seconds)
    return ExternalDeliveryHttpRequestResult(
        status_code=final_status_code,
        error=final_error,
        attempts=attempts,
        retry_after_honored=retry_after_honored,
        retry_after_seen=retry_after_seen,
        retry_budget_exhausted=retry_budget_exhausted,
        body=final_body,
    )


def _redact_url_for_metadata(value: str) -> str | None:
    if not value:
        return None
    parts = urllib.parse.urlsplit(value)
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    redacted = urllib.parse.urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            "",
            "",
        )
    )
    return redacted or None


def _url_has_query(value: str) -> bool:
    if not value:
        return False
    return bool(urllib.parse.urlsplit(value).query)


def _url_has_credentials(value: str) -> bool:
    if not value:
        return False
    parts = urllib.parse.urlsplit(value)
    return bool(parts.username or parts.password)


def _normalize_github_repository(value: str | None) -> str:
    repository = str(value or "").strip().strip("/")
    if repository.startswith("https://github.com/"):
        repository = repository.removeprefix("https://github.com/").strip("/")
    if repository.endswith(".git"):
        repository = repository[:-4]
    return repository


def _split_github_repository(value: str) -> tuple[str | None, str | None]:
    parts = [part for part in value.split("/") if part]
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _safe_github_asset_name(value: str) -> str:
    name = str(value or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        return "reverse-deepagent-delivery-package.json"
    return name


def _github_upload_url_from_response_body(body: bytes) -> str | None:
    upload_url, _assets_url = _github_release_urls_from_response_body(body)
    return upload_url


def _github_release_urls_from_response_body(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    upload_url = payload.get("upload_url") if isinstance(payload, dict) else None
    assets_url = payload.get("assets_url") if isinstance(payload, dict) else None
    return (
        str(upload_url).strip() if upload_url else None,
        str(assets_url).strip() if assets_url else None,
    )


def _github_asset_exists_from_response_body(body: bytes, asset_name: str) -> tuple[bool | None, int | None]:
    exists, count, _asset, _delete_url = _github_asset_lookup_from_response_body(body, asset_name)
    return exists, count


def _github_asset_lookup_from_response_body(
    body: bytes,
    asset_name: str,
) -> tuple[bool | None, int | None, dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(body.decode("utf-8") or "[]")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, None, None
    if not isinstance(payload, list):
        return None, None, None, None
    normalized_asset_name = str(asset_name or "").strip()
    names: list[str] = []
    matched_asset: dict[str, Any] | None = None
    matched_asset_delete_url: str | None = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        names.append(name)
        if name == normalized_asset_name and matched_asset is None:
            matched_asset = _github_asset_metadata_summary(item)
            matched_asset_delete_url = str(item.get("url") or "").strip() or None
    return normalized_asset_name in names, len(names), matched_asset, matched_asset_delete_url


def _github_asset_metadata_summary(asset: dict[str, Any]) -> dict[str, Any]:
    raw_id = asset.get("id")
    asset_id: int | str | None
    try:
        asset_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        asset_id = str(raw_id) if raw_id is not None else None
    api_url = str(asset.get("url") or "").strip()
    return {
        "id": asset_id,
        "name": str(asset.get("name") or "").strip() or None,
        "api_url": _redact_url_for_metadata(api_url) if api_url else None,
        "browser_download_url_present": bool(str(asset.get("browser_download_url") or "").strip()),
        "browser_download_url_recorded": False,
        "size": asset.get("size") if isinstance(asset.get("size"), int) else None,
        "content_type": str(asset.get("content_type") or "").strip() or None,
        "state": str(asset.get("state") or "").strip() or None,
        "created_at": str(asset.get("created_at") or "").strip() or None,
        "updated_at": str(asset.get("updated_at") or "").strip() or None,
        "raw_response_body_recorded": False,
        "headers_recorded": False,
    }


def _github_existing_asset_overwrite_plan(
    *,
    asset_name: str,
    existing_asset_found: bool,
    existing_asset: dict[str, Any] | None,
    check_existing_asset: bool,
    allow_existing_asset: bool,
    asset_lookup_succeeded: bool,
    approve_existing_asset_delete: bool = False,
    approve_replacement_upload: bool = False,
    expected_existing_asset_id_configured: bool = False,
    existing_asset_identity_matches: bool = False,
    delete_request_attempted: bool = False,
    delete_succeeded: bool = False,
    delete_status_code: int | None = None,
    delete_request_error: str | None = None,
    upload_request_attempted: bool = False,
    overwrite_performed: bool = False,
) -> dict[str, Any] | None:
    if not check_existing_asset:
        return None
    if not asset_lookup_succeeded:
        return {
            "status": "blocked",
            "asset_name": asset_name,
            "existing_asset_found": False,
            "delete_required": False,
            "overwrite_required": False,
            "delete_performed": False,
            "overwrite_performed": False,
            "delete_request_attempted": False,
            "replacement_upload_attempted": False,
            "requires_explicit_approval": True,
            "recommended_transition": "fix_github_asset_lookup_before_overwrite_plan",
            "reason": "asset_lookup_not_succeeded",
            "side_effect_policy": {
                "sends_delete_request": False,
                "uploads_replacement_asset": False,
                "preflight_only": True,
            },
        }
    if not existing_asset_found:
        return {
            "status": "not_required",
            "asset_name": asset_name,
            "existing_asset_found": False,
            "delete_required": False,
            "overwrite_required": False,
            "delete_performed": False,
            "overwrite_performed": False,
            "delete_request_attempted": False,
            "replacement_upload_attempted": False,
            "requires_explicit_approval": False,
            "recommended_transition": "upload_new_github_release_asset",
            "side_effect_policy": {
                "sends_delete_request": False,
                "uploads_replacement_asset": False,
                "preflight_only": True,
            },
        }
    return {
        "status": "requires_review",
        "asset_name": asset_name,
        "existing_asset_found": True,
        "existing_asset": existing_asset,
        "delete_required": True,
        "overwrite_required": True,
        "delete_performed": delete_succeeded,
        "overwrite_performed": overwrite_performed,
        "delete_request_attempted": delete_request_attempted,
        "replacement_upload_attempted": upload_request_attempted,
        "delete_status_code": delete_status_code,
        "delete_request_error": delete_request_error,
        "allow_existing_asset": allow_existing_asset,
        "approve_existing_asset_delete": approve_existing_asset_delete,
        "approve_replacement_upload": approve_replacement_upload,
        "expected_existing_asset_id_configured": expected_existing_asset_id_configured,
        "existing_asset_identity_matches": existing_asset_identity_matches,
        "requires_explicit_approval": not overwrite_performed,
        "recommended_transition": (
            "review_github_release_asset_overwrite_result"
            if overwrite_performed
            else "approve_github_release_asset_delete_then_upload"
        ),
        "approval_requirements": [
            "confirm_existing_asset_identity",
            "approve_delete_existing_release_asset",
            "approve_upload_replacement_release_asset",
            "record_partial_failure_recovery_plan",
        ],
        "partial_failure_plan": {
            "delete_succeeds_upload_fails": "record_external_delivery_result_blocked_and_retry_with_same_transaction_id",
            "delete_fails": "do_not_upload_replacement_asset",
            "upload_conflict_after_delete": "record_conflict_and_require_manual_github_release_review",
        },
        "side_effect_policy": {
            "sends_delete_request": delete_request_attempted,
            "uploads_replacement_asset": upload_request_attempted,
            "preflight_only": not delete_request_attempted,
        },
    }


def _github_existing_asset_identity_matches(
    *,
    existing_asset: dict[str, Any] | None,
    asset_name: str,
    expected_existing_asset_id: str,
) -> bool:
    if not existing_asset:
        return False
    if str(existing_asset.get("name") or "").strip() != str(asset_name or "").strip():
        return False
    if not expected_existing_asset_id:
        return True
    return str(existing_asset.get("id") or "").strip() == expected_existing_asset_id


def _github_upload_url_with_asset_name(upload_url: str, asset_name: str) -> str:
    base = str(upload_url or "").split("{", 1)[0]
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.urlencode({"name": asset_name})
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


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
