from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Protocol

from .executors import EXTERNAL_DELIVERY_SECRET_KEYWORDS, DeliveryExecutionMode, _write_json

DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP = "reverse_deepagent.delivery_lock_providers"
SUPPORTED_DELIVERY_LOCK_PROVIDER_ACTIONS: tuple[str, ...] = (
    "inspect_lock",
    "acquire_lock",
    "renew_lock",
    "release_lock",
)


@dataclass(frozen=True, slots=True)
class DeliveryTransactionLockProviderCapabilities:
    provider_id: str
    display_name: str
    transport: str = "in-process"
    coordination_scope: str = "local-process"
    supports_acquire: bool = True
    supports_renew: bool = True
    supports_release: bool = True
    supports_fencing_token: bool = True
    supports_lease: bool = True
    supports_distributed_consensus: bool = False
    dry_run_side_effect_free: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "transport": self.transport,
            "coordination_scope": self.coordination_scope,
            "supports_acquire": self.supports_acquire,
            "supports_renew": self.supports_renew,
            "supports_release": self.supports_release,
            "supports_fencing_token": self.supports_fencing_token,
            "supports_lease": self.supports_lease,
            "supports_distributed_consensus": self.supports_distributed_consensus,
            "dry_run_side_effect_free": self.dry_run_side_effect_free,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DeliveryTransactionLockProviderConfig:
    lock_root: Path
    transaction_id: str
    owner: str
    action: str = "inspect_lock"
    mode: DeliveryExecutionMode = DeliveryExecutionMode.DRY_RUN
    lease_seconds: int = 900
    expected_owner: str | None = None
    expected_fencing_token: str | None = None
    approve_release: bool = False
    allow_stale_takeover: bool = False
    lock_name: str = "delivery-distributed-transaction-lock.json"
    operation_record_name: str = "delivery-distributed-transaction-lock-operation.json"
    metadata: dict[str, Any] = field(default_factory=dict)

    def resolved_lock_root(self) -> Path:
        return self.lock_root.expanduser().resolve()


@dataclass(frozen=True)
class DeliveryTransactionLockOperation:
    provider_id: str
    action: str
    status: str
    mode: str
    dry_run: bool
    lock_root: str
    lock_path: str
    operation_record_path: str | None
    transaction_id: str
    owner: str
    expected_owner: str | None
    fencing_token: str | None
    expected_fencing_token: str | None
    lease_expires_at: str | None
    lock_acquired: bool
    lock_renewed: bool
    lock_released: bool
    stale_lock_detected: bool
    stale_takeover_allowed: bool
    existing_lock: dict[str, Any] | None
    resulting_lock: dict[str, Any] | None
    checks: list[dict[str, Any]]
    blocking_reasons: list[str]
    recommended_actions: list[str]
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        wrote_record = bool(self.operation_record_path) and not self.dry_run and self.status in {
            "acquired",
            "renewed",
            "released",
            "inspected",
        }
        return {
            "provider_id": self.provider_id,
            "action": self.action,
            "status": self.status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "lock_root": self.lock_root,
            "lock_path": self.lock_path,
            "operation_record_path": self.operation_record_path,
            "transaction_id": self.transaction_id,
            "owner": self.owner,
            "expected_owner": self.expected_owner,
            "fencing_token": self.fencing_token,
            "expected_fencing_token": self.expected_fencing_token,
            "lease_expires_at": self.lease_expires_at,
            "lock_acquired": self.lock_acquired,
            "lock_renewed": self.lock_renewed,
            "lock_released": self.lock_released,
            "stale_lock_detected": self.stale_lock_detected,
            "stale_takeover_allowed": self.stale_takeover_allowed,
            "existing_lock": self.existing_lock,
            "resulting_lock": self.resulting_lock,
            "checks": self.checks,
            "blocking_reasons": self.blocking_reasons,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "side_effect_policy": {
                "dry_run_is_read_only": True,
                "writes_lock_record": bool((self.lock_acquired or self.lock_renewed) and not self.dry_run),
                "removes_lock_record": bool(self.lock_released and not self.dry_run),
                "writes_operation_record": wrote_record,
                "distributed_lock_contract": True,
                "external_service_contacted": False,
                "delivery_executed": False,
                "external_delivery_performed": False,
                "manifest_mutated": False,
                "transaction_committed": False,
            },
        }


class DeliveryTransactionLockProvider(Protocol):
    provider_id: str

    def manage_lock(
        self,
        config: DeliveryTransactionLockProviderConfig,
        *,
        created_at: str,
    ) -> DeliveryTransactionLockOperation:
        """Inspect, acquire, renew, or release a transaction lock."""


DeliveryTransactionLockProviderFactory = Callable[..., DeliveryTransactionLockProvider]


@dataclass(frozen=True, slots=True)
class DeliveryTransactionLockProviderRegistration:
    provider_id: str
    capabilities: DeliveryTransactionLockProviderCapabilities
    factory: DeliveryTransactionLockProviderFactory
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.capabilities.provider_id != self.provider_id:
            raise ValueError(
                "Delivery transaction lock provider capability id mismatch: "
                f"registration={self.provider_id!r}, capabilities={self.capabilities.provider_id!r}"
            )
        if _lock_provider_metadata_has_secret_like_keys(self.capabilities.to_dict()):
            raise ValueError(f"Delivery transaction lock provider capabilities for {self.provider_id!r} contain secret-like metadata keys")

    @property
    def keys(self) -> tuple[str, ...]:
        return (self.provider_id, *self.aliases)


class DeliveryTransactionLockProviderRegistry:
    """Side-effect-light registry for transaction lock providers."""

    def __init__(self) -> None:
        self._registrations: dict[str, DeliveryTransactionLockProviderRegistration] = {}
        self._aliases: dict[str, str] = {}

    def register(self, registration: DeliveryTransactionLockProviderRegistration) -> None:
        for key in registration.keys:
            if key in self._registrations or key in self._aliases:
                raise ValueError(f"Delivery transaction lock provider key already registered: {key}")
        self._registrations[registration.provider_id] = registration
        for alias in registration.aliases:
            self._aliases[alias] = registration.provider_id

    def resolve(self, provider_id: str) -> DeliveryTransactionLockProviderRegistration:
        canonical = provider_id if provider_id in self._registrations else self._aliases.get(provider_id)
        if canonical is None:
            known = ", ".join(self.provider_ids())
            raise ValueError(f"Unsupported delivery transaction lock provider: {provider_id}. Known providers: {known}")
        return self._registrations[canonical]

    def create(self, provider_id: str, **kwargs: Any) -> DeliveryTransactionLockProvider:
        return self.resolve(provider_id).factory(**kwargs)

    def provider_ids(self) -> list[str]:
        return sorted([*self._registrations, *self._aliases])

    def list_registration_metadata(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for provider_id in sorted(self._registrations):
            registration = self._registrations[provider_id]
            payload = registration.capabilities.to_dict()
            payload["aliases"] = list(registration.aliases)
            payload["keys"] = list(registration.keys)
            payloads.append(payload)
        return payloads

    def load_entry_points(self, group: str = DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP) -> list[str]:
        loaded: list[str] = []
        for entry_point in sorted(_entry_points_for_group(group), key=lambda item: item.name):
            try:
                value = entry_point.load()
            except Exception as exc:
                raise RuntimeError(f"Failed to load delivery transaction lock provider entry point {entry_point.name!r}: {exc}") from exc
            for registration in self._coerce_plugin_registrations(entry_point.name, value):
                self.register(registration)
                loaded.append(registration.provider_id)
        return loaded

    @staticmethod
    def _coerce_plugin_registrations(entry_point_name: str, value: Any) -> list[DeliveryTransactionLockProviderRegistration]:
        if isinstance(value, DeliveryTransactionLockProviderRegistration):
            return [value]
        if callable(value):
            return DeliveryTransactionLockProviderRegistry._coerce_plugin_registrations(entry_point_name, value())
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, dict)):
            registrations = list(value)
            if all(isinstance(item, DeliveryTransactionLockProviderRegistration) for item in registrations):
                return registrations
        raise TypeError(
            "Delivery transaction lock provider entry point "
            f"{entry_point_name!r} must return a DeliveryTransactionLockProviderRegistration, "
            "a callable producing registrations, or an iterable of registrations."
        )


@dataclass(frozen=True)
class LocalFileDeliveryTransactionLockProvider:
    """Reference provider that stores a fenced lock record on the local filesystem.

    This is a contract baseline and single-host reference implementation.  It
    exposes lease and fencing-token semantics for callers, but it does not
    provide distributed consensus by itself.
    """

    provider_id: str = "local-file-lock"

    def manage_lock(
        self,
        config: DeliveryTransactionLockProviderConfig,
        *,
        created_at: str,
    ) -> DeliveryTransactionLockOperation:
        lock_root = config.resolved_lock_root()
        lock_path = lock_root / config.lock_name
        operation_record_path = lock_root / config.operation_record_name
        dry_run = config.mode == DeliveryExecutionMode.DRY_RUN
        existing_lock, load_error = _read_lock(lock_path)
        stale = bool(existing_lock) and _lease_is_past(str(existing_lock.get("lease_expires_at") or ""), created_at)
        checks = _base_checks(config=config, existing_lock=existing_lock, load_error=load_error, stale=stale)
        action = str(config.action or "")
        resulting_lock: dict[str, Any] | None = existing_lock.copy() if existing_lock else None
        lock_acquired = False
        lock_renewed = False
        lock_released = False
        fencing_token: str | None = str(existing_lock.get("fencing_token")) if existing_lock and existing_lock.get("fencing_token") is not None else None
        lease_expires_at: str | None = str(existing_lock.get("lease_expires_at")) if existing_lock and existing_lock.get("lease_expires_at") else None
        blocking_reasons = [check["name"] for check in checks if not check["passed"]]
        if not blocking_reasons and action in {"acquire_lock", "renew_lock"}:
            fencing_token = _next_fencing_token(existing_lock)
            lease_expires_at = _lease_expires_at(created_at, config.lease_seconds)
            resulting_lock = {
                "version": "2026-06-01.delivery-transaction-lock-provider-v1",
                "provider_id": self.provider_id,
                "transaction_id": config.transaction_id,
                "owner": config.owner,
                "fencing_token": fencing_token,
                "lease_expires_at": lease_expires_at,
                "created_at": created_at,
                "renewed_at": created_at if action == "renew_lock" else None,
                "metadata": {
                    **config.metadata,
                    "distributed_lock_contract": True,
                    "coordination_scope": "local-filesystem-reference",
                },
            }
            if not dry_run:
                _write_json(lock_path, resulting_lock)
            lock_acquired = action == "acquire_lock" and not dry_run
            lock_renewed = action == "renew_lock" and not dry_run
        elif not blocking_reasons and action == "release_lock":
            if not dry_run and lock_path.exists():
                lock_path.unlink()
            resulting_lock = None
            lock_released = not dry_run
        status = _status_for(action, dry_run, blocking_reasons, lock_acquired, lock_renewed, lock_released)
        operation_record = DeliveryTransactionLockOperation(
            provider_id=self.provider_id,
            action=action,
            status=status,
            mode=config.mode.value,
            dry_run=dry_run,
            lock_root=str(lock_root),
            lock_path=str(lock_path),
            operation_record_path=str(operation_record_path) if not dry_run and status in {"acquired", "renewed", "released", "inspected"} else None,
            transaction_id=config.transaction_id,
            owner=config.owner,
            expected_owner=config.expected_owner,
            fencing_token=fencing_token,
            expected_fencing_token=config.expected_fencing_token,
            lease_expires_at=lease_expires_at,
            lock_acquired=lock_acquired,
            lock_renewed=lock_renewed,
            lock_released=lock_released,
            stale_lock_detected=stale,
            stale_takeover_allowed=config.allow_stale_takeover,
            existing_lock=existing_lock,
            resulting_lock=resulting_lock,
            checks=checks,
            blocking_reasons=blocking_reasons,
            recommended_actions=_recommended_actions(status, action, stale),
            created_at=created_at,
            metadata={
                **config.metadata,
                "provider_id": self.provider_id,
                "provider_transport": "filesystem",
                "distributed_lock_contract": True,
                "coordination_scope": "local-filesystem-reference",
                "supports_fencing_token": True,
                "supports_lease": True,
                "supports_distributed_consensus": False,
                "limitations": [
                    "reference_provider_uses_local_filesystem",
                    "does_not_provide_cross_machine_consensus_by_itself",
                    "external_providers_should_implement_same_contract",
                ],
            },
        )
        if operation_record.operation_record_path:
            _write_json(Path(operation_record.operation_record_path), operation_record.to_dict())
        return operation_record


def local_file_delivery_transaction_lock_provider_registration() -> DeliveryTransactionLockProviderRegistration:
    return DeliveryTransactionLockProviderRegistration(
        provider_id="local-file-lock",
        aliases=("filesystem-lock", "local-distributed-lock"),
        capabilities=DeliveryTransactionLockProviderCapabilities(
            provider_id="local-file-lock",
            display_name="Local filesystem transaction lock provider",
            transport="filesystem",
            coordination_scope="local-filesystem-reference",
            supports_distributed_consensus=False,
            metadata={
                "contract_baseline": True,
                "writes_lock_record": True,
                "writes_operation_record": True,
                "supports_fencing_token": True,
                "supports_lease": True,
                "external_service_required": False,
                "recommended_for": "single-host-tests-and-provider-contract-validation",
            },
        ),
        factory=lambda **_: LocalFileDeliveryTransactionLockProvider(),
    )


def build_default_delivery_transaction_lock_provider_registry(*, load_entry_points: bool = True) -> DeliveryTransactionLockProviderRegistry:
    registry = DeliveryTransactionLockProviderRegistry()
    registry.register(local_file_delivery_transaction_lock_provider_registration())
    if load_entry_points:
        registry.load_entry_points()
    return registry


def manage_delivery_transaction_lock(
    config: DeliveryTransactionLockProviderConfig,
    *,
    provider: DeliveryTransactionLockProvider | None = None,
) -> DeliveryTransactionLockOperation:
    created_at = datetime.now(timezone.utc).isoformat()
    selected_provider = provider or LocalFileDeliveryTransactionLockProvider()
    return selected_provider.manage_lock(config, created_at=created_at)


def _base_checks(
    *,
    config: DeliveryTransactionLockProviderConfig,
    existing_lock: dict[str, Any] | None,
    load_error: str | None,
    stale: bool,
) -> list[dict[str, Any]]:
    action = str(config.action or "")
    existing_owner = str(existing_lock.get("owner") or "") if existing_lock else ""
    existing_token = str(existing_lock.get("fencing_token") or "") if existing_lock else ""
    same_owner = bool(existing_lock and existing_owner == config.owner)
    expected_owner_matches = not config.expected_owner or bool(existing_lock and existing_owner == config.expected_owner)
    expected_token_matches = not config.expected_fencing_token or bool(existing_lock and existing_token == config.expected_fencing_token)
    lock_blocks_acquire = action == "acquire_lock" and bool(existing_lock) and not same_owner and not (stale and config.allow_stale_takeover)
    renew_requires_existing = action == "renew_lock" and not bool(existing_lock)
    release_requires_existing = action == "release_lock" and not bool(existing_lock)
    stale_blocks = stale and action in {"renew_lock", "release_lock"} and not config.allow_stale_takeover
    release_approved = action != "release_lock" or config.mode == DeliveryExecutionMode.DRY_RUN or bool(config.approve_release)
    return [
        {"name": "lock_action_supported", "passed": action in SUPPORTED_DELIVERY_LOCK_PROVIDER_ACTIONS, "details": {"action": action, "supported": list(SUPPORTED_DELIVERY_LOCK_PROVIDER_ACTIONS)}},
        {"name": "lock_record_is_valid", "passed": load_error is None, "details": {"load_error": load_error}},
        {"name": "transaction_id_present", "passed": bool(config.transaction_id.strip()), "details": {"transaction_id": config.transaction_id}},
        {"name": "owner_present", "passed": bool(config.owner.strip()), "details": {"owner": config.owner}},
        {"name": "existing_lock_allows_acquire", "passed": not lock_blocks_acquire, "details": {"existing_owner": existing_owner or None, "same_owner": same_owner, "stale_lock_detected": stale, "allow_stale_takeover": config.allow_stale_takeover}},
        {"name": "renew_requires_existing_lock", "passed": not renew_requires_existing, "details": {"existing_lock": bool(existing_lock)}},
        {"name": "release_requires_existing_lock", "passed": not release_requires_existing, "details": {"existing_lock": bool(existing_lock)}},
        {"name": "expected_owner_matches", "passed": expected_owner_matches, "details": {"expected_owner": config.expected_owner, "existing_owner": existing_owner or None}},
        {"name": "expected_fencing_token_matches", "passed": expected_token_matches, "details": {"expected_fencing_token": config.expected_fencing_token, "existing_fencing_token_present": bool(existing_token)}},
        {"name": "stale_lock_takeover_approved", "passed": not stale_blocks, "details": {"stale_lock_detected": stale, "allow_stale_takeover": config.allow_stale_takeover}},
        {"name": "release_requires_explicit_approval", "passed": release_approved, "details": {"approve_release": config.approve_release, "mode": config.mode.value}},
    ]


def _status_for(action: str, dry_run: bool, blockers: list[str], acquired: bool, renewed: bool, released: bool) -> str:
    if blockers:
        return "blocked"
    if dry_run:
        return "planned" if action != "inspect_lock" else "inspected"
    if acquired:
        return "acquired"
    if renewed:
        return "renewed"
    if released:
        return "released"
    if action == "inspect_lock":
        return "inspected"
    return "planned"


def _recommended_actions(status: str, action: str, stale: bool) -> list[str]:
    if status == "blocked":
        return ["inspect_transaction_lock_provider_blockers"]
    if action == "inspect_lock":
        return ["review_transaction_lock_state"]
    if status == "planned":
        return [f"apply_{action}_after_review"]
    if stale:
        return ["review_stale_lock_takeover_audit"]
    return ["continue_review_gated_delivery_transaction"]


def _read_lock(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {}, str(exc)
    if not isinstance(value, dict):
        return {}, "lock record must be a JSON object"
    return value, None


def _next_fencing_token(existing_lock: dict[str, Any] | None) -> str:
    if not existing_lock:
        return "1"
    try:
        return str(int(str(existing_lock.get("fencing_token") or "0")) + 1)
    except ValueError:
        return "1"


def _lease_expires_at(created_at: str, lease_seconds: int) -> str:
    return (datetime.fromisoformat(created_at).astimezone(timezone.utc) + timedelta(seconds=max(1, int(lease_seconds)))).isoformat()


def _lease_is_past(value: str, now: str) -> bool:
    if not value:
        return False
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
        current = datetime.fromisoformat(now.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return expires <= current


def _entry_points_for_group(group: str) -> list[Any]:
    entry_points = importlib_metadata.entry_points()
    if hasattr(entry_points, "select"):
        return list(entry_points.select(group=group))
    return list(entry_points.get(group, []))


_LOCK_PROVIDER_SAFE_SECRET_KEY_NAMES = {
    "supports_fencing_token",
    "fencing_token",
    "expected_fencing_token",
}


def _lock_provider_metadata_has_secret_like_keys(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered not in _LOCK_PROVIDER_SAFE_SECRET_KEY_NAMES and any(
                keyword in lowered for keyword in EXTERNAL_DELIVERY_SECRET_KEYWORDS
            ):
                return True
            if _lock_provider_metadata_has_secret_like_keys(item):
                return True
        return False
    if isinstance(value, list):
        return any(_lock_provider_metadata_has_secret_like_keys(item) for item in value)
    return False
