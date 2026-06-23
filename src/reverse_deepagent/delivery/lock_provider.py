from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit, urlunsplit

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
    external_service_contacted: bool = False

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
                "external_service_contacted": self.external_service_contacted,
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


@dataclass(frozen=True)
class SQLiteDeliveryTransactionLockProvider:
    """SQLite-backed transactional lock provider baseline.

    This provider stores the authoritative lock row in a local SQLite database
    using ``BEGIN IMMEDIATE`` for serialized write transactions.  It is stronger
    than the JSON-file reference provider for same-host concurrent processes,
    but it is still not a distributed consensus system.
    """

    database_name: str = "delivery-distributed-transaction-lock.sqlite3"
    provider_id: str = "sqlite-lock"

    def manage_lock(
        self,
        config: DeliveryTransactionLockProviderConfig,
        *,
        created_at: str,
    ) -> DeliveryTransactionLockOperation:
        lock_root = config.resolved_lock_root()
        lock_path = lock_root / config.lock_name
        operation_record_path = lock_root / config.operation_record_name
        database_path = lock_root / self.database_name
        dry_run = config.mode == DeliveryExecutionMode.DRY_RUN
        existing_lock, load_error = self._read_existing(database_path=database_path, dry_run=dry_run)
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
            resulting_lock = self._lock_record(
                config=config,
                created_at=created_at,
                fencing_token=fencing_token,
                lease_expires_at=lease_expires_at,
                action=action,
            )
            if not dry_run:
                self._upsert_lock(database_path=database_path, lock_record=resulting_lock)
                _write_json(lock_path, resulting_lock)
            lock_acquired = action == "acquire_lock" and not dry_run
            lock_renewed = action == "renew_lock" and not dry_run
        elif not blocking_reasons and action == "release_lock":
            if not dry_run:
                self._delete_lock(database_path=database_path)
                if lock_path.exists():
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
                "provider_transport": "sqlite",
                "database_path": str(database_path),
                "distributed_lock_contract": True,
                "coordination_scope": "local-sqlite-transaction",
                "supports_fencing_token": True,
                "supports_lease": True,
                "supports_distributed_consensus": False,
                "sqlite_transactional_storage": True,
                "limitations": [
                    "sqlite_provider_serializes_same_database_writers",
                    "does_not_provide_cross_machine_consensus_by_itself",
                    "database_file_must_be_on_a_reliable_local_or_shared_filesystem",
                    "downstream_writers_must_still_enforce_fencing_tokens",
                ],
            },
        )
        if operation_record.operation_record_path:
            _write_json(Path(operation_record.operation_record_path), operation_record.to_dict())
        return operation_record

    def _read_existing(self, *, database_path: Path, dry_run: bool) -> tuple[dict[str, Any] | None, str | None]:
        if not database_path.exists():
            return None, None
        try:
            with sqlite3.connect(database_path) as connection:
                _ensure_sqlite_schema(connection)
                row = connection.execute(
                    "SELECT lock_json FROM delivery_transaction_locks WHERE lock_key = ?",
                    ("delivery",),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001 - returned as structured blocker.
            return {}, str(exc)
        if row is None:
            return None, None
        try:
            value = json.loads(str(row[0]))
        except Exception as exc:  # noqa: BLE001
            return {}, str(exc)
        if not isinstance(value, dict):
            return {}, "sqlite lock record must decode to a JSON object"
        return value, None

    def _upsert_lock(self, *, database_path: Path, lock_record: dict[str, Any]) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_sqlite_schema(connection)
            connection.execute(
                """
                INSERT INTO delivery_transaction_locks(lock_key, transaction_id, owner, fencing_token, lease_expires_at, lock_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lock_key) DO UPDATE SET
                    transaction_id = excluded.transaction_id,
                    owner = excluded.owner,
                    fencing_token = excluded.fencing_token,
                    lease_expires_at = excluded.lease_expires_at,
                    lock_json = excluded.lock_json,
                    updated_at = excluded.updated_at
                """,
                (
                    "delivery",
                    str(lock_record.get("transaction_id") or ""),
                    str(lock_record.get("owner") or ""),
                    str(lock_record.get("fencing_token") or ""),
                    str(lock_record.get("lease_expires_at") or ""),
                    json.dumps(lock_record, ensure_ascii=False, sort_keys=True),
                    str(lock_record.get("renewed_at") or lock_record.get("created_at") or ""),
                ),
            )
            connection.commit()

    def _delete_lock(self, *, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _ensure_sqlite_schema(connection)
            connection.execute("DELETE FROM delivery_transaction_locks WHERE lock_key = ?", ("delivery",))
            connection.commit()

    def _lock_record(
        self,
        *,
        config: DeliveryTransactionLockProviderConfig,
        created_at: str,
        fencing_token: str,
        lease_expires_at: str,
        action: str,
    ) -> dict[str, Any]:
        return {
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
                "coordination_scope": "local-sqlite-transaction",
                "sqlite_transactional_storage": True,
            },
        }


_REDIS_COMPARE_SET_SCRIPT = """
local current = redis.call("GET", KEYS[1])
if not current then
  if ARGV[5] == "1" then
    redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[2])
    return 1
  end
  return 0
end
local decoded = cjson.decode(current)
if ARGV[3] ~= "" and tostring(decoded["owner"] or "") ~= ARGV[3] then
  return -1
end
if ARGV[4] ~= "" and tostring(decoded["fencing_token"] or "") ~= ARGV[4] then
  return -2
end
redis.call("SET", KEYS[1], ARGV[1], "EX", ARGV[2])
return 1
"""

_REDIS_COMPARE_DELETE_SCRIPT = """
local current = redis.call("GET", KEYS[1])
if not current then
  return 0
end
local decoded = cjson.decode(current)
if ARGV[1] ~= "" and tostring(decoded["owner"] or "") ~= ARGV[1] then
  return -1
end
if ARGV[2] ~= "" and tostring(decoded["fencing_token"] or "") ~= ARGV[2] then
  return -2
end
redis.call("DEL", KEYS[1])
return 1
"""


@dataclass(frozen=True)
class RedisDeliveryTransactionLockProvider:
    """Redis-backed external transaction lock provider baseline.

    The provider keeps Redis as the authoritative external lock service and
    writes local JSON projection / operation audit records for workspace
    compatibility. Metadata listing and dry-runs do not open network sockets.
    Apply / inspect runs require an injected client or ``redis_url`` supplied via
    provider construction or ``config.metadata``.
    """

    client: Any | None = None
    redis_url: str | None = None
    key_name: str = "reverse-deepagent:delivery:distributed-transaction-lock"
    provider_id: str = "redis-lock"

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
        action = str(config.action or "")
        redis_key = str(config.metadata.get("redis_lock_key") or self.key_name)
        existing_lock: dict[str, Any] | None = None
        load_error: str | None = None
        external_service_contacted = False
        client: Any | None = None
        if not dry_run:
            client, load_error = self._client(config)
            if client is not None:
                existing_lock, load_error = self._read_existing(client=client, redis_key=redis_key)
                external_service_contacted = True
        stale = bool(existing_lock) and _lease_is_past(str(existing_lock.get("lease_expires_at") or ""), created_at)
        checks = _base_checks(config=config, existing_lock=existing_lock, load_error=load_error, stale=stale)
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
            resulting_lock = self._lock_record(
                config=config,
                created_at=created_at,
                fencing_token=fencing_token,
                lease_expires_at=lease_expires_at,
                action=action,
                redis_key=redis_key,
            )
            if not dry_run and client is not None:
                ok, reason = self._write_lock(client=client, redis_key=redis_key, lock_record=resulting_lock, existing_lock=existing_lock, stale=stale, config=config, action=action)
                if ok:
                    _write_json(lock_path, resulting_lock)
                    lock_acquired = action == "acquire_lock"
                    lock_renewed = action == "renew_lock"
                else:
                    blocking_reasons.append(reason)
                    resulting_lock = existing_lock.copy() if existing_lock else None
        elif not blocking_reasons and action == "release_lock":
            if not dry_run and client is not None:
                ok, reason = self._delete_lock(client=client, redis_key=redis_key, existing_lock=existing_lock, config=config)
                if ok:
                    if lock_path.exists():
                        lock_path.unlink()
                    resulting_lock = None
                    lock_released = True
                else:
                    blocking_reasons.append(reason)
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
                **_safe_lock_provider_runtime_metadata(config.metadata),
                "provider_id": self.provider_id,
                "provider_transport": "redis",
                "redis_key": redis_key,
                "distributed_lock_contract": True,
                "coordination_scope": "external-redis-lease",
                "supports_fencing_token": True,
                "supports_lease": True,
                "supports_distributed_consensus": False,
                "external_service_required": True,
                "redis_authoritative_store": True,
                "redis_url_configured": bool(self.redis_url or config.metadata.get("redis_url")),
                "dry_run_external_service_contacted": False if dry_run else None,
                "limitations": [
                    "redis_provider_uses_external_redis_key_with_lease_ttl",
                    "single_redis_instance_or_cluster_semantics_depend_on_deployment",
                    "does_not_implement_redlock_quorum_consensus",
                    "downstream_writers_must_still_enforce_fencing_tokens",
                ],
            },
            external_service_contacted=external_service_contacted,
        )
        if operation_record.operation_record_path:
            _write_json(Path(operation_record.operation_record_path), operation_record.to_dict())
        return operation_record

    def _client(self, config: DeliveryTransactionLockProviderConfig) -> tuple[Any | None, str | None]:
        if self.client is not None:
            return self.client, None
        redis_url = self.redis_url or config.metadata.get("redis_url")
        if not redis_url:
            return None, "redis_url is required for redis-lock apply/inspect operations"
        try:
            import redis  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001 - optional dependency is reported structurally.
            return None, f"redis optional dependency is not installed: {exc}"
        try:
            return redis.Redis.from_url(str(redis_url)), None
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _read_existing(self, *, client: Any, redis_key: str) -> tuple[dict[str, Any] | None, str | None]:
        try:
            raw = client.get(redis_key)
        except Exception as exc:  # noqa: BLE001
            return {}, str(exc)
        if raw is None:
            return None, None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            value = json.loads(str(raw))
        except Exception as exc:  # noqa: BLE001
            return {}, str(exc)
        if not isinstance(value, dict):
            return {}, "redis lock record must decode to a JSON object"
        return value, None

    def _write_lock(
        self,
        *,
        client: Any,
        redis_key: str,
        lock_record: dict[str, Any],
        existing_lock: dict[str, Any] | None,
        stale: bool,
        config: DeliveryTransactionLockProviderConfig,
        action: str,
    ) -> tuple[bool, str]:
        payload = json.dumps(lock_record, ensure_ascii=False, sort_keys=True)
        lease_seconds = max(1, int(config.lease_seconds))
        if action == "acquire_lock" and not existing_lock:
            try:
                written = client.set(redis_key, payload, ex=lease_seconds, nx=True)
            except TypeError:
                written = client.set(redis_key, payload, nx=True, ex=lease_seconds)
            except Exception as exc:  # noqa: BLE001
                return False, f"redis_set_failed:{exc}"
            return (True, "") if bool(written) else (False, "redis_lock_changed_during_acquire")
        expected_owner = str(existing_lock.get("owner") or config.expected_owner or "") if existing_lock else str(config.expected_owner or "")
        expected_token = str(existing_lock.get("fencing_token") or config.expected_fencing_token or "") if existing_lock else str(config.expected_fencing_token or "")
        allow_missing = "1" if stale and config.allow_stale_takeover else "0"
        result = self._eval_compare_set(client, redis_key, payload, lease_seconds, expected_owner, expected_token, allow_missing)
        return self._redis_script_result_to_status(result, default_reason="redis_compare_set_failed")

    def _delete_lock(
        self,
        *,
        client: Any,
        redis_key: str,
        existing_lock: dict[str, Any] | None,
        config: DeliveryTransactionLockProviderConfig,
    ) -> tuple[bool, str]:
        expected_owner = str(existing_lock.get("owner") or config.expected_owner or "") if existing_lock else str(config.expected_owner or "")
        expected_token = str(existing_lock.get("fencing_token") or config.expected_fencing_token or "") if existing_lock else str(config.expected_fencing_token or "")
        result = self._eval_compare_delete(client, redis_key, expected_owner, expected_token)
        return self._redis_script_result_to_status(result, default_reason="redis_compare_delete_failed")

    def _eval_compare_set(self, client: Any, redis_key: str, payload: str, lease_seconds: int, expected_owner: str, expected_token: str, allow_missing: str) -> int:
        if hasattr(client, "eval"):
            return int(client.eval(_REDIS_COMPARE_SET_SCRIPT, 1, redis_key, payload, int(lease_seconds), expected_owner, expected_token, allow_missing))
        current, error = self._read_existing(client=client, redis_key=redis_key)
        if error:
            return -3
        if current is None and allow_missing != "1":
            return 0
        if current is not None and expected_owner and str(current.get("owner") or "") != expected_owner:
            return -1
        if current is not None and expected_token and str(current.get("fencing_token") or "") != expected_token:
            return -2
        try:
            client.set(redis_key, payload, ex=lease_seconds)
        except TypeError:
            client.set(redis_key, payload)
        return 1

    def _eval_compare_delete(self, client: Any, redis_key: str, expected_owner: str, expected_token: str) -> int:
        if hasattr(client, "eval"):
            return int(client.eval(_REDIS_COMPARE_DELETE_SCRIPT, 1, redis_key, expected_owner, expected_token))
        current, error = self._read_existing(client=client, redis_key=redis_key)
        if error:
            return -3
        if current is None:
            return 0
        if expected_owner and str(current.get("owner") or "") != expected_owner:
            return -1
        if expected_token and str(current.get("fencing_token") or "") != expected_token:
            return -2
        client.delete(redis_key)
        return 1

    def _redis_script_result_to_status(self, result: int, *, default_reason: str) -> tuple[bool, str]:
        if result == 1:
            return True, ""
        if result == 0:
            return False, "redis_lock_missing_or_changed"
        if result == -1:
            return False, "redis_expected_owner_mismatch"
        if result == -2:
            return False, "redis_expected_fencing_token_mismatch"
        return False, default_reason

    def _lock_record(
        self,
        *,
        config: DeliveryTransactionLockProviderConfig,
        created_at: str,
        fencing_token: str,
        lease_expires_at: str,
        action: str,
        redis_key: str,
    ) -> dict[str, Any]:
        return {
            "version": "2026-06-01.delivery-transaction-lock-provider-v1",
            "provider_id": self.provider_id,
            "transaction_id": config.transaction_id,
            "owner": config.owner,
            "fencing_token": fencing_token,
            "lease_expires_at": lease_expires_at,
            "created_at": created_at,
            "renewed_at": created_at if action == "renew_lock" else None,
            "metadata": {
                **_safe_lock_provider_runtime_metadata(config.metadata),
                "distributed_lock_contract": True,
                "coordination_scope": "external-redis-lease",
                "redis_key": redis_key,
            },
        }


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


def sqlite_delivery_transaction_lock_provider_registration() -> DeliveryTransactionLockProviderRegistration:
    return DeliveryTransactionLockProviderRegistration(
        provider_id="sqlite-lock",
        aliases=("db-lock", "sqlite-transaction-lock", "local-db-lock"),
        capabilities=DeliveryTransactionLockProviderCapabilities(
            provider_id="sqlite-lock",
            display_name="SQLite transaction lock provider",
            transport="sqlite",
            coordination_scope="local-sqlite-transaction",
            supports_distributed_consensus=False,
            metadata={
                "contract_baseline": True,
                "writes_lock_record": True,
                "writes_operation_record": True,
                "writes_sqlite_database": True,
                "supports_fencing_token": True,
                "supports_lease": True,
                "external_service_required": False,
                "sqlite_transactional_storage": True,
                "recommended_for": "same-host-or-shared-database-transaction-lock-tests",
                "not_consensus": True,
            },
        ),
        factory=lambda **kwargs: SQLiteDeliveryTransactionLockProvider(**kwargs),
    )



def redis_delivery_transaction_lock_provider_registration() -> DeliveryTransactionLockProviderRegistration:
    return DeliveryTransactionLockProviderRegistration(
        provider_id="redis-lock",
        aliases=("redis", "redis-lease-lock", "external-redis-lock"),
        capabilities=DeliveryTransactionLockProviderCapabilities(
            provider_id="redis-lock",
            display_name="Redis transaction lock provider",
            transport="redis",
            coordination_scope="external-redis-lease",
            supports_distributed_consensus=False,
            metadata={
                "contract_baseline": True,
                "writes_lock_record": True,
                "writes_operation_record": True,
                "writes_json_projection": True,
                "external_service_required": True,
                "redis_authoritative_store": True,
                "supports_fencing_token": True,
                "supports_lease": True,
                "uses_redis_set_nx_for_initial_acquire": True,
                "uses_lua_compare_set_when_available": True,
                "redlock_quorum_consensus": False,
                "recommended_for": "external-redis-lease-lock-integration-tests",
            },
        ),
        factory=lambda **kwargs: RedisDeliveryTransactionLockProvider(**kwargs),
    )


def build_default_delivery_transaction_lock_provider_registry(*, load_entry_points: bool = True) -> DeliveryTransactionLockProviderRegistry:
    registry = DeliveryTransactionLockProviderRegistry()
    registry.register(local_file_delivery_transaction_lock_provider_registration())
    registry.register(sqlite_delivery_transaction_lock_provider_registration())
    registry.register(redis_delivery_transaction_lock_provider_registration())
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


def _ensure_sqlite_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS delivery_transaction_locks (
            lock_key TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            fencing_token TEXT NOT NULL,
            lease_expires_at TEXT NOT NULL,
            lock_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _safe_lock_provider_runtime_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if lowered in {"redis_url", "redis_dsn"} or "url" in lowered or any(keyword in lowered for keyword in EXTERNAL_DELIVERY_SECRET_KEYWORDS):
            safe[str(key)] = _redact_lock_provider_value(value)
        else:
            safe[str(key)] = value
    return safe


def _redact_lock_provider_value(value: Any) -> Any:
    if not isinstance(value, str):
        return "<redacted>"
    try:
        parts = urlsplit(value)
    except Exception:  # noqa: BLE001
        return "<redacted>"
    if not parts.scheme or not parts.netloc:
        return "<redacted>"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = "<redacted>@" if parts.username or parts.password else ""
    return urlunsplit((parts.scheme, f"{username}{host}{port}", parts.path, "<redacted>" if parts.query else "", ""))


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
