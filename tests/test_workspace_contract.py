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
)


class WorkspaceContractTests(unittest.TestCase):
    def test_workspace_contract_payload_is_stable_json(self) -> None:
        payload = workspace_contract_payload()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        self.assertIn("indexed-only", encoded)
        self.assertEqual(payload["status"], "indexed-only")
        self.assertTrue(payload["path_migration_policy"]["existing_flat_workspace_paths_remain_canonical"])
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
        for implemented_role in {"coordinator", "router", "web_recon", "protector", "delivery"}:
            self.assertEqual(roles[implemented_role].current_status, "implemented")
        for planned_role in {"browser_runtime", "debugger", "hook", "timeline", "rebuild", "review"}:
            self.assertEqual(roles[planned_role].current_status, "planned-contract")

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
        self.assertEqual(routes["workspace/stitched-flow.json"].virtual_folder, "/workspace/timeline/")
        self.assertEqual(routes["workspace/review-gate.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/rebuild-plan.json"].virtual_folder, "/workspace/rebuild/")
        self.assertEqual(routes["workspace/browser-provider-smoke.json"].virtual_folder, "/workspace/browser/")
        self.assertEqual(routes["workspace/workspace-contract.json"].future_path, "/workspace/delivery/workspace-contract.json")
        self.assertTrue(all(item.migration_status == "indexed-only" for item in routes.values()))

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


if __name__ == "__main__":
    unittest.main()
