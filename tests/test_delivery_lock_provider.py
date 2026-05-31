from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from reverse_deepagent.delivery import (
    DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP,
    DeliveryExecutionMode,
    DeliveryTransactionLockProviderConfig,
    LocalFileDeliveryTransactionLockProvider,
    build_default_delivery_transaction_lock_provider_registry,
    manage_delivery_transaction_lock,
)
from reverse_deepagent.tools.delivery_tools import make_delivery_transaction_lock_provider_tool


class DeliveryTransactionLockProviderTests(TestCase):
    def test_default_registry_exposes_local_file_provider_metadata_without_factory_side_effects(self) -> None:
        registry = build_default_delivery_transaction_lock_provider_registry(load_entry_points=False)

        metadata = registry.list_registration_metadata()

        self.assertEqual(DELIVERY_LOCK_PROVIDER_ENTRY_POINT_GROUP, "reverse_deepagent.delivery_lock_providers")
        self.assertEqual(len(metadata), 1)
        self.assertEqual(metadata[0]["provider_id"], "local-file-lock")
        self.assertIn("filesystem-lock", metadata[0]["aliases"])
        self.assertIn("local-distributed-lock", metadata[0]["aliases"])
        self.assertTrue(metadata[0]["supports_fencing_token"])
        self.assertTrue(metadata[0]["supports_lease"])
        self.assertFalse(metadata[0]["supports_distributed_consensus"])
        self.assertIsInstance(registry.create("filesystem-lock"), LocalFileDeliveryTransactionLockProvider)

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
