import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.coordinator import run_platform_pipeline, run_reverse_pipeline
from reverse_deepagent.workspace_contract import (
    default_middleware_chain,
    default_subagent_roles,
    default_workspace_artifact_routes,
    default_workspace_folders,
    workspace_contract_payload,
    workspace_manifest_alias_metadata,
    workspace_virtual_uri,
)


class WorkspaceContractTests(unittest.TestCase):
    def test_workspace_contract_payload_is_stable_json(self) -> None:
        payload = workspace_contract_payload()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertIn("indexed-only", encoded)
        self.assertEqual(payload["status"], "indexed-only")
        self.assertTrue(payload["path_migration_policy"]["existing_flat_workspace_paths_remain_canonical"])
        self.assertTrue(payload["path_migration_policy"]["backend_manifest_includes_foldered_aliases"])
        self.assertTrue(payload["path_migration_policy"]["foldered_aliases_are_manifest_only"])
        self.assertGreaterEqual(payload["artifact_route_count"], 20)

    def test_virtual_folders_include_deepagents_collaboration_areas(self) -> None:
        folders = {item.virtual_folder: item for item in default_workspace_folders()}
        for expected in {
            "/workspace/recon/",
            "/workspace/browser/",
            "/workspace/debugger/",
            "/workspace/hooks/",
            "/workspace/timeline/",
            "/workspace/rebuild/",
            "/workspace/review/",
            "/workspace/delivery/",
            "/workspace/runtime/",
            "/workspace/evidence/",
        }:
            self.assertIn(expected, folders)
            self.assertEqual(folders[expected].migration_status, "indexed-only")

    def test_subagent_roles_cover_current_and_planned_boundaries(self) -> None:
        roles = {item.role: item for item in default_subagent_roles()}
        for implemented_role in {"coordinator", "router", "browser_runtime", "web_recon", "protector", "delivery", "debugger", "hook", "timeline", "rebuild", "review"}:
            self.assertEqual(roles[implemented_role].current_status, "implemented")
        planned_roles = [role for role in roles.values() if role.current_status == "planned-contract"]
        self.assertEqual(planned_roles, [])

    def test_middleware_chain_order_is_deterministic(self) -> None:
        chain = list(default_middleware_chain())
        names = [item.name for item in chain]
        self.assertEqual(names, [
            "task_normalize",
            "runtime_capability",
            "browser_session",
            "evidence_promotion",
            "review_gate",
            "artifact_manifest",
            "delivery_guard",
        ])
        self.assertEqual([item.order for item in chain], sorted(item.order for item in chain))
        self.assertIn("no-implicit-mcp-start", chain[2].gates)

    def test_artifact_routes_index_existing_flat_paths_without_migration(self) -> None:
        routes = {item.legacy_path: item for item in default_workspace_artifact_routes()}
        self.assertEqual(routes["workspace/flow-timeline.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/auto-stitch-conflict-resolutions.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/auto-stitch-materialization-results.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-materialization-audit.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-rollback-plan.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-materialization-transactions.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-rollback-executions.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-physical-rollback-diff.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow-physical-rollback-results.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/stitched-flow.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/review-gate-after-rollback.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-gate-after-physical-rollback.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-gate-replacement-results.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/delivery-guard-after-review-gate-replacement.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/final-delivery-package-after-review-gate-replacement.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/final-delivery-transaction-commit.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-receipt.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-transaction-journal.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/external-delivery-result.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/external-delivery-duplicate-guard.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-manifest-revision.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-mutation.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest.patched.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-preflight.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-in-place-mutation.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest.rollback.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-recovery-preflight.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-recovery.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/backend-artifact-manifest-transaction-commit.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/review-gate.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/rebuild-plan.json"].virtual_folder, "/workspace/rebuild/")
        self.assertEqual(routes["workspace/browser-provider-smoke.json"].virtual_folder, "/workspace/browser/")
        self.assertEqual(routes["workspace/workspace-contract.json"].future_path, "/workspace/delivery/workspace-contract.json")
        self.assertTrue(all(item.migration_status == "indexed-only" for item in routes.values()))

    def test_manifest_alias_metadata_indexes_foldered_virtual_paths_without_moving_files(self) -> None:
        alias = workspace_manifest_alias_metadata("workspace_flow_timeline")["workspace_alias"]
        self.assertEqual(alias["canonical_path"], "workspace/flow-timeline.json")
        self.assertTrue(alias["canonical_path_remains_authoritative"])
        self.assertEqual(alias["virtual_folder"], "/workspace/timeline/")
        self.assertEqual(alias["future_path"], "/workspace/timeline/flow-timeline.json")
        self.assertEqual(alias["virtual_uri"], "virtual://workspace/timeline/flow-timeline.json")
        self.assertEqual(alias["migration_status"], "manifest-alias-only")
        self.assertEqual(alias["route_migration_status"], "indexed-only")
        self.assertIn("timeline", alias["producer_roles"])
        self.assertEqual(workspace_virtual_uri("/workspace/review/review-gate.json"), "virtual://workspace/review/review-gate.json")
        self.assertEqual(workspace_manifest_alias_metadata("non_workspace_report"), {})

    def test_web_pipeline_writes_workspace_contract_and_manifest_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="mock",
            )
            contract_path = Path(output.artifacts["workspace_workspace_contract"])
            self.assertTrue(contract_path.exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["status"], "indexed-only")
            self.assertTrue(contract["path_migration_policy"]["existing_flat_workspace_paths_remain_canonical"])

            manifest_path = Path(output.artifacts["workspace_backend_artifact_manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_workspace_contract"]["category"], "workspace")
            self.assertEqual(manifest_by_key["workspace_workspace_contract"]["kind"], "json")
            contract_alias = manifest_by_key["workspace_workspace_contract"]["metadata"]["workspace_alias"]
            self.assertEqual(contract_alias["canonical_path"], "workspace/workspace-contract.json")
            self.assertEqual(contract_alias["future_path"], "/workspace/delivery/workspace-contract.json")
            self.assertEqual(contract_alias["virtual_uri"], "virtual://workspace/delivery/workspace-contract.json")
            self.assertTrue(contract_alias["canonical_path_remains_authoritative"])
            self.assertEqual(contract_alias["migration_status"], "manifest-alias-only")

            task_alias = manifest_by_key["workspace_task_card"]["metadata"]["workspace_alias"]
            self.assertEqual(task_alias["virtual_folder"], "/workspace/recon/")
            self.assertEqual(task_alias["future_path"], "/workspace/recon/task-card.json")
            self.assertEqual(Path(manifest_by_key["workspace_task_card"]["path"]).name, "task-card.json")

            index_path = Path(output.artifacts["index"])
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["workspace"]["workspace_contract"], str(contract_path))

    def test_platform_pipeline_writes_workspace_contract_and_manifest_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = run_platform_pipeline(
                task_text="android://demo 找 sign",
                artifact_root=Path(tmpdir) / "artifacts",
                runtime_kind="android-adb",
            )
            contract_path = Path(output.artifacts["workspace_workspace_contract"])
            self.assertTrue(contract_path.exists())
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["status"], "indexed-only")

            manifest_path = Path(output.artifacts["workspace_backend_artifact_manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_workspace_contract"]["category"], "workspace")
            contract_alias = manifest_by_key["workspace_workspace_contract"]["metadata"]["workspace_alias"]
            self.assertEqual(contract_alias["future_path"], "/workspace/delivery/workspace-contract.json")
            self.assertEqual(contract_alias["virtual_uri"], "virtual://workspace/delivery/workspace-contract.json")
            probe_alias = manifest_by_key["workspace_platform_tool_probe"]["metadata"]["workspace_alias"]
            self.assertEqual(probe_alias["virtual_folder"], "/workspace/runtime/")
            self.assertEqual(probe_alias["future_path"], "/workspace/runtime/platform-tool-probe.json")


if __name__ == "__main__":
    unittest.main()
