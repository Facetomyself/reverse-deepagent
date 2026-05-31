from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from reverse_deepagent.delivery import (
    DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP,
    DeliveryExecutionMode,
    DeliveryTransactionLockProviderConfig,
    LocalFileDeliveryTransactionLockProvider,
    SQLiteDeliveryTransactionLockProvider,
    build_default_delivery_transaction_lock_provider_registry,
    manage_delivery_transaction_lock,
)
from reverse_deepagent.tools.delivery_tools import make_delivery_transaction_lock_provider_tool


class DeliveryTransactionLockProviderTests(TestCase):
    def test_default_registry_exposes_local_file_provider_metadata_without_factory_side_effects(self) -> None:
        registry = build_default_delivery_transaction_lock_provider_registry(load_entry_points=False)

        metadata = registry.list_registration_metadata()

        self.assertEqual(DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP, "reverse_deepagent.delivery_lock_providers")
        self.assertEqual(len(metadata), 2)
        by_provider = {item["provider_id"]: item for item in metadata}
        self.assertIn("local-file-lock", by_provider)
        self.assertIn("sqlite-lock", by_provider)
        self.assertIn("filesystem-lock", by_provider["local-file-lock"]["aliases"])
        self.assertIn("local-distributed-lock", by_provider["local-file-lock"]["aliases"])
        self.assertTrue(by_provider["local-file-lock"]["supports_fencing_token"])
        self.assertTrue(by_provider["local-file-lock"]["supports_lease"])
        self.assertFalse(by_provider["local-file-lock"]["supports_distributed_consensus"])
        self.assertIn("db-lock", by_provider["sqlite-lock"]["aliases"])
        self.assertEqual(by_provider["sqlite-lock"]["transport"], "sqlite")
        self.assertEqual(by_provider["sqlite-lock"]["coordination_scope"], "local-sqlite-transaction")
        self.assertTrue(by_provider["sqlite-lock"]["metadata"]["writes_sqlite_database"])
        self.assertFalse(by_provider["sqlite-lock"]["supports_distributed_consensus"])
        self.assertIsInstance(registry.create("filesystem-lock"), LocalFileDeliveryTransactionLockProvider)
        self.assertIsInstance(registry.create("db-lock"), SQLiteDeliveryTransactionLockProvider)

    def test_dry_run_acquire_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-dry-run",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.DRY_RUN,
            )

            result = manage_delivery_transaction_lock(config).to_dict()

            self.assertEqual(result["status"], "planned")
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["lock_acquired"])
            self.assertFalse(result["side_effect_policy"]["writes_lock_record"])
            self.assertFalse(result["side_effect_policy"]["writes_operation_record"])
            self.assertFalse((root / "delivery-distributed-transaction-lock.json").exists())
            self.assertFalse((root / "delivery-distributed-transaction-lock-operation.json").exists())

    def test_apply_acquire_writes_lock_and_operation_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-acquire",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
                metadata={"source": "test"},
            )

            result = manage_delivery_transaction_lock(config).to_dict()

            lock_path = root / "delivery-distributed-transaction-lock.json"
            operation_path = root / "delivery-distributed-transaction-lock-operation.json"
            self.assertEqual(result["status"], "acquired")
            self.assertTrue(result["lock_acquired"])
            self.assertTrue(result["side_effect_policy"]["writes_lock_record"])
            self.assertTrue(result["side_effect_policy"]["writes_operation_record"])
            self.assertFalse(result["side_effect_policy"]["delivery_executed"])
            self.assertFalse(result["side_effect_policy"]["external_delivery_performed"])
            self.assertFalse(result["side_effect_policy"]["manifest_mutated"])
            self.assertFalse(result["side_effect_policy"]["transaction_committed"])
            self.assertTrue(lock_path.exists())
            self.assertTrue(operation_path.exists())
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(lock["transaction_id"], "tx-acquire")
            self.assertEqual(lock["owner"], "agent-a")
            self.assertEqual(lock["fencing_token"], "1")
            operation = json.loads(operation_path.read_text(encoding="utf-8"))
            self.assertEqual(operation["status"], "acquired")
            self.assertEqual(operation["metadata"]["source"], "test")

    def test_apply_renew_increments_fencing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acquire = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-renew",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
            )
            manage_delivery_transaction_lock(acquire)
            renew = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-renew",
                owner="agent-a",
                action="renew_lock",
                mode=DeliveryExecutionMode.APPLY,
                expected_owner="agent-a",
                expected_fencing_token="1",
            )

            result = manage_delivery_transaction_lock(renew).to_dict()

            self.assertEqual(result["status"], "renewed")
            self.assertTrue(result["lock_renewed"])
            self.assertEqual(result["fencing_token"], "2")
            lock = json.loads((root / "delivery-distributed-transaction-lock.json").read_text(encoding="utf-8"))
            self.assertEqual(lock["fencing_token"], "2")

    def test_apply_acquire_by_other_owner_is_blocked_without_overwriting_existing_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-blocked",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
            )
            manage_delivery_transaction_lock(first)
            second = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-blocked",
                owner="agent-b",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
            )

            result = manage_delivery_transaction_lock(second).to_dict()

            self.assertEqual(result["status"], "blocked")
            self.assertIn("existing_lock_allows_acquire", result["blocking_reasons"])
            lock = json.loads((root / "delivery-distributed-transaction-lock.json").read_text(encoding="utf-8"))
            self.assertEqual(lock["owner"], "agent-a")
            self.assertEqual(lock["fencing_token"], "1")

    def test_release_requires_explicit_apply_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            acquire = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-release",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
            )
            manage_delivery_transaction_lock(acquire)
            blocked_release = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-release",
                owner="agent-a",
                action="release_lock",
                mode=DeliveryExecutionMode.APPLY,
                expected_owner="agent-a",
                expected_fencing_token="1",
            )

            blocked = manage_delivery_transaction_lock(blocked_release).to_dict()

            self.assertEqual(blocked["status"], "blocked")
            self.assertIn("release_requires_explicit_approval", blocked["blocking_reasons"])
            self.assertTrue((root / "delivery-distributed-transaction-lock.json").exists())
            approved_release = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-release",
                owner="agent-a",
                action="release_lock",
                mode=DeliveryExecutionMode.APPLY,
                expected_owner="agent-a",
                expected_fencing_token="1",
                approve_release=True,
            )

            released = manage_delivery_transaction_lock(approved_release).to_dict()

            self.assertEqual(released["status"], "released")
            self.assertTrue(released["lock_released"])
            self.assertFalse((root / "delivery-distributed-transaction-lock.json").exists())
            self.assertTrue((root / "delivery-distributed-transaction-lock-operation.json").exists())

    def test_tool_invokes_selected_provider_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = make_delivery_transaction_lock_provider_tool(root / "delivery")

            result = tool(
                transaction_id="tx-tool-provider-lock",
                owner="agent-a",
                action="acquire_lock",
                mode="apply",
                provider_id="local-distributed-lock",
                metadata_json=json.dumps({"source": "tool-test"}),
            )

            self.assertEqual(result["provider_id"], "local-file-lock")
            self.assertEqual(result["status"], "acquired")
            self.assertTrue((root / "delivery" / "delivery-distributed-transaction-lock.json").exists())
            self.assertTrue((root / "delivery" / "delivery-distributed-transaction-lock-operation.json").exists())
            self.assertEqual(result["metadata"]["source"], "tool-test")
            self.assertFalse(result["side_effect_policy"]["external_service_contacted"])

    def test_sqlite_provider_apply_writes_database_projection_and_operation_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = SQLiteDeliveryTransactionLockProvider()
            config = DeliveryTransactionLockProviderConfig(
                lock_root=root,
                transaction_id="tx-sqlite",
                owner="agent-a",
                action="acquire_lock",
                mode=DeliveryExecutionMode.APPLY,
                metadata={"source": "sqlite-test"},
            )

            result = manage_delivery_transaction_lock(config, provider=provider).to_dict()

            database_path = root / "delivery-distributed-transaction-lock.sqlite3"
            lock_path = root / "delivery-distributed-transaction-lock.json"
            operation_path = root / "delivery-distributed-transaction-lock-operation.json"
            self.assertEqual(result["provider_id"], "sqlite-lock")
            self.assertEqual(result["status"], "acquired")
            self.assertTrue(result["lock_acquired"])
            self.assertTrue(database_path.exists())
            self.assertTrue(lock_path.exists())
            self.assertTrue(operation_path.exists())
            self.assertEqual(result["metadata"]["provider_transport"], "sqlite")
            self.assertEqual(result["metadata"]["coordination_scope"], "local-sqlite-transaction")
            self.assertTrue(result["metadata"]["sqlite_transactional_storage"])
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(lock["provider_id"], "sqlite-lock")
            self.assertEqual(lock["fencing_token"], "1")
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT transaction_id, owner, fencing_token FROM delivery_transaction_locks WHERE lock_key = ?",
                    ("delivery",),
                ).fetchone()
            self.assertEqual(row, ("tx-sqlite", "agent-a", "1"))

    def test_sqlite_provider_renew_and_release_update_transactional_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = SQLiteDeliveryTransactionLockProvider()
            manage_delivery_transaction_lock(
                DeliveryTransactionLockProviderConfig(
                    lock_root=root,
                    transaction_id="tx-sqlite-renew",
                    owner="agent-a",
                    action="acquire_lock",
                    mode=DeliveryExecutionMode.APPLY,
                ),
                provider=provider,
            )

            renewed = manage_delivery_transaction_lock(
                DeliveryTransactionLockProviderConfig(
                    lock_root=root,
                    transaction_id="tx-sqlite-renew",
                    owner="agent-a",
                    action="renew_lock",
                    mode=DeliveryExecutionMode.APPLY,
                    expected_owner="agent-a",
                    expected_fencing_token="1",
                ),
                provider=provider,
            ).to_dict()
            released = manage_delivery_transaction_lock(
                DeliveryTransactionLockProviderConfig(
                    lock_root=root,
                    transaction_id="tx-sqlite-renew",
                    owner="agent-a",
                    action="release_lock",
                    mode=DeliveryExecutionMode.APPLY,
                    expected_owner="agent-a",
                    expected_fencing_token="2",
                    approve_release=True,
                ),
                provider=provider,
            ).to_dict()

            database_path = root / "delivery-distributed-transaction-lock.sqlite3"
            self.assertEqual(renewed["status"], "renewed")
            self.assertEqual(renewed["fencing_token"], "2")
            self.assertEqual(released["status"], "released")
            self.assertTrue(released["lock_released"])
            self.assertFalse((root / "delivery-distributed-transaction-lock.json").exists())
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT lock_json FROM delivery_transaction_locks WHERE lock_key = ?",
                    ("delivery",),
                ).fetchone()
            self.assertIsNone(row)

    def test_tool_can_use_sqlite_lock_provider_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = make_delivery_transaction_lock_provider_tool(root / "delivery")

            result = tool(
                transaction_id="tx-tool-sqlite-lock",
                owner="agent-a",
                action="acquire_lock",
                mode="apply",
                provider_id="db-lock",
                metadata_json=json.dumps({"source": "tool-sqlite-test"}),
            )

            self.assertEqual(result["provider_id"], "sqlite-lock")
            self.assertEqual(result["status"], "acquired")
            self.assertTrue((root / "delivery" / "delivery-distributed-transaction-lock.sqlite3").exists())
            self.assertTrue((root / "delivery" / "delivery-distributed-transaction-lock.json").exists())
            self.assertEqual(result["metadata"]["source"], "tool-sqlite-test")
