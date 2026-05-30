from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import TestCase

from reverse_deepagent.subagents.delivery import build_delivery_subagent
from reverse_deepagent.tools.delivery_tools import make_local_delivery_executor_tool


class DeliveryToolTests(TestCase):
    def test_local_delivery_tool_defaults_to_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            tool = make_local_delivery_executor_tool(root / "delivery")

            result = tool(
                artifacts_json=json.dumps([{"source_path": str(source), "artifact_key": "workspace_final"}]),
                transaction_id="tx-tool-dry-run",
            )

            self.assertEqual(result["status"], "planned")
            self.assertTrue(result["dry_run"])
            self.assertFalse(result["filesystem_artifact_mutated"])
            self.assertFalse((root / "delivery").exists())

    def test_local_delivery_tool_apply_writes_local_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            tool = make_local_delivery_executor_tool(root / "delivery")

            result = tool(
                artifacts_json=json.dumps(
                    [
                        {
                            "source_path": str(source),
                            "artifact_key": "workspace_final",
                            "destination_name": "final-result.json",
                        }
                    ]
                ),
                transaction_id="tx-tool-apply",
                mode="apply",
                metadata_json=json.dumps({"source": "tool-test"}),
            )

            self.assertEqual(result["status"], "delivered")
            self.assertFalse(result["dry_run"])
            self.assertTrue(result["filesystem_artifact_mutated"])
            self.assertFalse(result["external_delivery_performed"])
            self.assertFalse(result["manifest_revision_committed"])
            self.assertTrue((root / "delivery" / "delivery-receipt.json").exists())
            self.assertTrue((root / "delivery" / "delivery-transaction-journal.json").exists())

    def test_local_delivery_tool_can_commit_manifest_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "workspace" / "final-result.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"ok": true}\n', encoding="utf-8")
            tool = make_local_delivery_executor_tool(root / "delivery")

            result = tool(
                artifacts_json=json.dumps([{"source_path": str(source), "artifact_key": "workspace_final"}]),
                transaction_id="tx-tool-manifest",
                mode="apply",
                commit_manifest_revision=True,
            )

            self.assertTrue(result["manifest_revision_committed"])
            self.assertEqual(result["manifest_revision"]["status"], "committed")
            self.assertFalse(result["manifest_revision"]["backend_manifest_mutated"])
            self.assertTrue((root / "delivery" / "delivery-manifest-revision.json").exists())

    def test_local_delivery_tool_can_write_backend_manifest_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            source = workspace / "final-result.json"
            source.write_text('{"ok": true}\n', encoding="utf-8")
            backend_manifest = workspace / "backend-artifact-manifest.json"
            backend_manifest.write_text('{"entries": []}\n', encoding="utf-8")
            tool = make_local_delivery_executor_tool(root / "delivery")

            result = tool(
                artifacts_json=json.dumps([{"source_path": str(source), "artifact_key": "workspace_final"}]),
                transaction_id="tx-tool-backend-manifest",
                mode="apply",
                commit_backend_manifest_mutation=True,
                backend_manifest_path=str(backend_manifest),
            )

            self.assertTrue(result["backend_manifest_patch_written"])
            self.assertFalse(result["backend_manifest_mutated"])
            self.assertEqual(result["backend_manifest_mutation"]["status"], "patch_written")
            added_keys = {entry["artifact_key"] for entry in result["backend_manifest_mutation"]["added_entries"]}
            self.assertIn("workspace_backend_artifact_manifest_mutation", added_keys)
            self.assertIn("workspace_backend_artifact_manifest_patched", added_keys)
            self.assertNotIn("workspace_delivery_manifest_revision", added_keys)
            self.assertTrue((root / "delivery" / "backend-artifact-manifest-mutation.json").exists())
            self.assertTrue((root / "delivery" / "backend-artifact-manifest.patched.json").exists())


class DeliverySubagentToolTests(TestCase):
    def test_delivery_subagent_exposes_rebuild_and_local_delivery_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subagent = build_delivery_subagent(Path(tmp) / "artifacts")
            tool_names = [tool.__name__ for tool in subagent["tools"]]
            self.assertEqual(tool_names, ["build_rebuild_delivery", "execute_local_delivery"])
