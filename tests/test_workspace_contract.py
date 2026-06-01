import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.coordinator import run_platform_pipeline, run_reverse_pipeline
from reverse_deepagent.workspace_contract import (
    WorkspacePathResolver,
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
        self.assertTrue(payload["path_migration_policy"]["workspace_path_resolver_available"])
        self.assertTrue(payload["path_migration_policy"]["dual_write_is_opt_in"])
        self.assertFalse(payload["path_migration_policy"]["dual_write_default_enabled"])
        self.assertTrue(payload["path_migration_policy"]["actual_dual_write_writer_available"])
        self.assertEqual(payload["path_resolver"]["status"], "resolver-only")
        self.assertEqual(payload["path_resolver"]["default_write_policy"], "legacy-only")
        self.assertEqual(payload["path_resolver"]["opt_in_dual_write_policy"], "legacy-and-future-path")
        self.assertEqual(payload["path_resolver"]["dual_write_audit_artifact"], "workspace/workspace-dual-write-plan.json")
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
        self.assertEqual(routes["workspace/protection-triage-hooks.json"].future_path, "/workspace/hooks/protection-triage-hooks.json")
        self.assertEqual(routes["workspace/wasm-runtime-candidates.json"].future_path, "/workspace/runtime/wasm-runtime-candidates.json")
        self.assertEqual(routes["workspace/vm-dispatcher-candidates.json"].future_path, "/workspace/runtime/vm-dispatcher-candidates.json")
        self.assertEqual(routes["workspace/review-gate-after-rollback.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-gate-after-physical-rollback.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-gate-replacement-results.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-approval-record.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-approval-record.json"].future_path, "/workspace/review/review-approval-record.json")
        self.assertEqual(routes["workspace/review-approval-ledger.json"].virtual_folder, "/workspace/review/")
        self.assertEqual(routes["workspace/review-approval-ledger.json"].future_path, "/workspace/review/review-approval-ledger.json")
        self.assertEqual(routes["workspace/workspace-dual-write-plan.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/workspace-dual-write-pilot-result.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/workspace-dual-write-pilot-result.json"].future_path, "/workspace/delivery/workspace-dual-write-pilot-result.json")
        self.assertEqual(routes["workspace/workspace-dual-write-pilot-result.json"].category, "audit")
        self.assertEqual(routes["workspace/delivery-guard-after-review-gate-replacement.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/final-delivery-package-after-review-gate-replacement.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/final-delivery-transaction-commit.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-receipt.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-transaction-journal.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/external-delivery-result.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/external-delivery-duplicate-guard.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/external-delivery-idempotency-ledger.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/external-delivery-idempotency-ledger.json"].future_path,
            "/workspace/delivery/external-delivery-idempotency-ledger.json",
        )
        self.assertEqual(routes["workspace/delivery-transaction-lock.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-transaction-lock.json"].future_path,
            "/workspace/delivery/delivery-transaction-lock.json",
        )
        self.assertEqual(routes["workspace/delivery-transaction-lock-release.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-transaction-lock-release.json"].future_path,
            "/workspace/delivery/delivery-transaction-lock-release.json",
        )
        self.assertEqual(routes["workspace/delivery-distributed-transaction-lock.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-distributed-transaction-lock.json"].future_path,
            "/workspace/delivery/delivery-distributed-transaction-lock.json",
        )
        self.assertEqual(routes["workspace/delivery-distributed-transaction-lock-operation.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-distributed-transaction-lock-operation.json"].future_path,
            "/workspace/delivery/delivery-distributed-transaction-lock-operation.json",
        )
        self.assertEqual(routes["workspace/delivery-resume-plan.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-resume-plan.json"].future_path,
            "/workspace/delivery/delivery-resume-plan.json",
        )
        self.assertEqual(routes["workspace/delivery-resume-execution.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-resume-execution.json"].future_path,
            "/workspace/delivery/delivery-resume-execution.json",
        )
        self.assertEqual(routes["workspace/delivery-resume-workflow.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-resume-workflow.json"].future_path,
            "/workspace/delivery/delivery-resume-workflow.json",
        )
        self.assertEqual(routes["workspace/delivery-resume-workflow-journal.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-resume-workflow-journal.json"].future_path,
            "/workspace/delivery/delivery-resume-workflow-journal.json",
        )
        self.assertEqual(routes["workspace/delivery-transaction-idempotency-guard.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(
            routes["workspace/delivery-transaction-idempotency-guard.json"].future_path,
            "/workspace/delivery/delivery-transaction-idempotency-guard.json",
        )
        self.assertEqual(routes["workspace/delivery-rollback-state.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-rollback-state.json"].future_path, "/workspace/delivery/delivery-rollback-state.json")
        self.assertEqual(routes["workspace/delivery-rollback-execution.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-rollback-execution.json"].future_path, "/workspace/delivery/delivery-rollback-execution.json")
        self.assertEqual(routes["workspace/delivery-transition-execution.json"].virtual_folder, "/workspace/delivery/")
        self.assertEqual(routes["workspace/delivery-transition-execution.json"].future_path, "/workspace/delivery/delivery-transition-execution.json")
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
        self.assertEqual(routes["workspace/async-chunk-load-plan.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/async-chunk-load-plan.json"].future_path, "/workspace/runtime/async-chunk-load-plan.json")
        self.assertEqual(routes["workspace/async-chunk-module-diff.json"].virtual_folder, "/workspace/hooks/")
        self.assertEqual(routes["workspace/async-chunk-module-diff.json"].future_path, "/workspace/hooks/async-chunk-module-diff.json")
        self.assertEqual(routes["workspace/custom-loader-traversal-plan.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/custom-loader-traversal-plan.json"].future_path, "/workspace/runtime/custom-loader-traversal-plan.json")
        self.assertEqual(routes["workspace/custom-loader-execution-preflight.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/custom-loader-execution-preflight.json"].future_path, "/workspace/runtime/custom-loader-execution-preflight.json")
        self.assertEqual(routes["workspace/module-federation-get-init-plan.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/module-federation-get-init-plan.json"].future_path, "/workspace/runtime/module-federation-get-init-plan.json")
        self.assertEqual(routes["workspace/async-chunk-load-result.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/async-chunk-load-result.json"].future_path, "/workspace/runtime/async-chunk-load-result.json")
        self.assertEqual(routes["workspace/module-federation-get-init-result.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/module-federation-get-init-result.json"].future_path, "/workspace/runtime/module-federation-get-init-result.json")
        self.assertEqual(routes["workspace/module-federation-factory-invoke-result.json"].virtual_folder, "/workspace/runtime/")
        self.assertEqual(routes["workspace/module-federation-factory-invoke-result.json"].future_path, "/workspace/runtime/module-federation-factory-invoke-result.json")
        self.assertEqual(routes["workspace/module-federation-export-hook-plan.json"].virtual_folder, "/workspace/hooks/")
        self.assertEqual(routes["workspace/module-federation-export-hook-plan.json"].future_path, "/workspace/hooks/module-federation-export-hook-plan.json")
        self.assertEqual(routes["workspace/source-map-fetch-plan.json"].virtual_folder, "/workspace/debugger/")
        self.assertEqual(routes["workspace/source-map-fetch-plan.json"].future_path, "/workspace/debugger/source-map-fetch-plan.json")
        self.assertEqual(routes["workspace/source-map-fetch-result.json"].virtual_folder, "/workspace/debugger/")
        self.assertEqual(routes["workspace/source-map-fetch-result.json"].future_path, "/workspace/debugger/source-map-fetch-result.json")
        self.assertEqual(routes["workspace/object-root-mutation-audit.json"].virtual_folder, "/workspace/browser/")
        self.assertEqual(routes["workspace/object-root-mutation-audit.json"].future_path, "/workspace/browser/object-root-mutation-audit.json")
        self.assertEqual(routes["workspace/workspace-contract.json"].future_path, "/workspace/delivery/workspace-contract.json")
        self.assertTrue(all(item.migration_status == "indexed-only" for item in routes.values()))

    def test_manifest_alias_metadata_indexes_foldered_virtual_paths_without_moving_files(self) -> None:
        alias = workspace_manifest_alias_metadata("workspace_flow_timeline")["workspace_alias"]
        self.assertEqual(alias["canonical_path"], "workspace/flow-timeline.json")
        self.assertTrue(alias["canonical_path_remains_authoritative"])
        self.assertEqual(alias["virtual_folder"], "/workspace/timeline/")
        self.assertEqual(alias["future_path"], "/workspace/timeline/flow-timeline.json")
        self.assertEqual(alias["virtual_uri"], "virtual://workspace/timeline/flow-timeline.json")
        self.assertEqual(alias["canonical_uri"], "virtual://workspace/flow-timeline.json")
        self.assertEqual(alias["migration_status"], "manifest-alias-only")
        self.assertEqual(alias["resolver_migration_status"], "resolver-only")
        self.assertEqual(alias["route_migration_status"], "indexed-only")
        self.assertIn("timeline", alias["producer_roles"])
        self.assertEqual(workspace_virtual_uri("/workspace/review/review-gate.json"), "virtual://workspace/review/review-gate.json")
        self.assertEqual(workspace_manifest_alias_metadata("non_workspace_report"), {})

    def test_workspace_path_resolver_keeps_legacy_path_authoritative_by_default(self) -> None:
        resolver = WorkspacePathResolver()

        by_key = resolver.resolve_artifact_key("workspace_flow_timeline")
        self.assertIsNotNone(by_key)
        assert by_key is not None
        self.assertEqual(by_key.canonical_path, "workspace/flow-timeline.json")
        self.assertEqual(by_key.future_path, "/workspace/timeline/flow-timeline.json")
        self.assertEqual(by_key.virtual_uri, "virtual://workspace/timeline/flow-timeline.json")
        self.assertEqual(by_key.write_paths, ("workspace/flow-timeline.json",))
        self.assertTrue(by_key.canonical_path_remains_authoritative)
        self.assertFalse(by_key.dual_write_enabled)
        self.assertEqual(by_key.migration_status, "resolver-only")

        by_legacy = resolver.resolve_path("workspace/flow-timeline.json")
        by_future = resolver.resolve_path("/workspace/timeline/flow-timeline.json")
        by_virtual = resolver.resolve_path("virtual://workspace/timeline/flow-timeline.json")
        self.assertEqual(by_legacy, by_key)
        self.assertEqual(by_future, by_key)
        self.assertEqual(by_virtual, by_key)
        self.assertIsNone(resolver.resolve_artifact_key("missing_artifact"))
        self.assertIsNone(resolver.resolve_path("workspace/missing.json"))

    def test_workspace_path_resolver_dual_write_is_opt_in_plan_only(self) -> None:
        resolver = WorkspacePathResolver(enable_dual_write=True)

        resolution = resolver.resolve_artifact_key("workspace_rebuild_plan")
        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.canonical_path, "workspace/rebuild-plan.json")
        self.assertEqual(resolution.write_paths, ("workspace/rebuild-plan.json", "/workspace/rebuild/rebuild-plan.json"))
        self.assertTrue(resolution.dual_write_enabled)
        self.assertFalse(resolution.physical_migration_enabled)
        self.assertTrue(resolution.canonical_path_remains_authoritative)
        self.assertEqual(resolution.migration_status, "dual-write-plan-only")

        plan = resolver.plan_dual_write("workspace_rebuild_plan")
        self.assertEqual(plan["status"], "planned")
        self.assertEqual(plan["write_paths"], ("workspace/rebuild-plan.json", "/workspace/rebuild/rebuild-plan.json"))
        self.assertTrue(plan["dual_write_enabled"])
        self.assertFalse(plan["physical_migration_enabled"])

        missing = resolver.plan_dual_write("missing_artifact")
        self.assertEqual(missing["status"], "unknown-artifact")
        self.assertEqual(missing["write_paths"], ())

    def test_workspace_path_resolver_can_scope_dual_write_to_selected_artifacts(self) -> None:
        resolver = WorkspacePathResolver(
            enable_dual_write=True,
            dual_write_artifact_keys={"workspace_task_card"},
        )

        in_scope = resolver.resolve_artifact_key("workspace_task_card")
        out_of_scope = resolver.resolve_artifact_key("workspace_route")

        self.assertIsNotNone(in_scope)
        self.assertIsNotNone(out_of_scope)
        assert in_scope is not None
        assert out_of_scope is not None
        self.assertTrue(in_scope.dual_write_enabled)
        self.assertTrue(in_scope.dual_write_scope_enabled)
        self.assertTrue(in_scope.dual_write_in_scope)
        self.assertEqual(in_scope.write_paths, ("workspace/task-card.json", "/workspace/recon/task-card.json"))
        self.assertEqual(in_scope.migration_status, "scoped-dual-write-plan-only")
        self.assertFalse(out_of_scope.dual_write_enabled)
        self.assertTrue(out_of_scope.dual_write_scope_enabled)
        self.assertFalse(out_of_scope.dual_write_in_scope)
        self.assertEqual(out_of_scope.write_paths, ("workspace/route-decision.json",))
        self.assertEqual(out_of_scope.migration_status, "dual-write-out-of-scope")

        in_scope_plan = resolver.plan_dual_write("workspace_task_card")
        out_of_scope_plan = resolver.plan_dual_write("workspace_route")
        self.assertEqual(in_scope_plan["status"], "planned")
        self.assertTrue(in_scope_plan["dual_write_enabled"])
        self.assertTrue(in_scope_plan["dual_write_scope_enabled"])
        self.assertTrue(in_scope_plan["dual_write_in_scope"])
        self.assertEqual(out_of_scope_plan["status"], "out-of-scope")
        self.assertFalse(out_of_scope_plan["dual_write_enabled"])
        self.assertTrue(out_of_scope_plan["dual_write_scope_enabled"])
        self.assertFalse(out_of_scope_plan["dual_write_in_scope"])

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
            self.assertFalse((Path(tmpdir) / "artifacts" / "workspace" / "recon" / "task-card.json").exists())

            index_path = Path(output.artifacts["index"])
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["workspace"]["workspace_contract"], str(contract_path))

    def test_web_pipeline_can_opt_in_to_workspace_dual_write_without_changing_canonical_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=root,
                runtime_kind="mock",
                enable_workspace_dual_write=True,
            )

            legacy_task = root / "workspace" / "task-card.json"
            future_task = root / "workspace" / "recon" / "task-card.json"
            legacy_manifest = root / "workspace" / "backend-artifact-manifest.json"
            future_manifest = root / "workspace" / "delivery" / "backend-artifact-manifest.json"
            dual_write_plan_path = root / "workspace" / "workspace-dual-write-plan.json"
            future_dual_write_plan_path = root / "workspace" / "delivery" / "workspace-dual-write-plan.json"

            self.assertEqual(output.artifacts["workspace_task_card"], str(legacy_task))
            self.assertTrue(legacy_task.exists())
            self.assertTrue(future_task.exists())
            self.assertEqual(
                json.loads(legacy_task.read_text(encoding="utf-8")),
                json.loads(future_task.read_text(encoding="utf-8")),
            )
            self.assertTrue(legacy_manifest.exists())
            self.assertTrue(future_manifest.exists())
            self.assertTrue(dual_write_plan_path.exists())
            self.assertTrue(future_dual_write_plan_path.exists())

            plan = json.loads(dual_write_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["status"], "applied")
            self.assertGreaterEqual(plan["dual_written_count"], 1)
            task_records = [record for record in plan["records"] if record["artifact_key"] == "workspace_task_card"]
            self.assertEqual(len(task_records), 1)
            self.assertEqual(task_records[0]["write_paths"], [str(legacy_task), str(future_task)])
            self.assertTrue(task_records[0]["canonical_path_remains_authoritative"])
            self.assertFalse(task_records[0]["physical_migration_enabled"])

            manifest = json.loads(legacy_manifest.read_text(encoding="utf-8"))
            manifest_by_key = {item["artifact_key"]: item for item in manifest["entries"]}
            self.assertEqual(manifest_by_key["workspace_task_card"]["path"], str(legacy_task))
            self.assertIn("workspace_dual_write_plan", manifest_by_key)
            alias = manifest_by_key["workspace_dual_write_plan"]["metadata"]["workspace_alias"]
            self.assertEqual(alias["future_path"], "/workspace/delivery/workspace-dual-write-plan.json")

    def test_web_pipeline_can_scope_workspace_dual_write_to_selected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "artifacts"
            output = run_reverse_pipeline(
                task_text="https://example.com/search 找 sign 入口，并给出下一步建议",
                artifact_root=root,
                runtime_kind="mock",
                enable_workspace_dual_write=True,
                workspace_dual_write_artifact_keys={"workspace_task_card"},
            )

            legacy_task = root / "workspace" / "task-card.json"
            future_task = root / "workspace" / "recon" / "task-card.json"
            legacy_route = root / "workspace" / "route-decision.json"
            future_route = root / "workspace" / "recon" / "route-decision.json"
            future_manifest = root / "workspace" / "delivery" / "backend-artifact-manifest.json"
            dual_write_plan_path = root / "workspace" / "workspace-dual-write-plan.json"

            self.assertEqual(output.artifacts["workspace_task_card"], str(legacy_task))
            self.assertTrue(legacy_task.exists())
            self.assertTrue(future_task.exists())
            self.assertTrue(legacy_route.exists())
            self.assertFalse(future_route.exists())
            self.assertFalse(future_manifest.exists())
            self.assertTrue(dual_write_plan_path.exists())

            plan = json.loads(dual_write_plan_path.read_text(encoding="utf-8"))
            self.assertEqual(plan["status"], "applied")
            self.assertEqual(plan["mode"], "scoped-opt-in-dual-write")
            self.assertTrue(plan["dual_write_scope_enabled"])
            self.assertEqual(plan["dual_write_scope_artifact_keys"], ["workspace_task_card"])
            self.assertEqual(plan["dual_written_count"], 1)
            self.assertGreater(plan["out_of_scope_record_count"], 1)
            records = {record["artifact_key"]: record for record in plan["records"]}
            self.assertEqual(records["workspace_task_card"]["write_paths"], [str(legacy_task), str(future_task)])
            self.assertTrue(records["workspace_task_card"]["dual_write_enabled"])
            self.assertTrue(records["workspace_task_card"]["dual_write_in_scope"])
            self.assertEqual(records["workspace_task_card"]["migration_status"], "scoped-dual-write-plan-only")
            self.assertEqual(records["workspace_route"]["write_paths"], [str(legacy_route)])
            self.assertFalse(records["workspace_route"]["dual_write_enabled"])
            self.assertFalse(records["workspace_route"]["dual_write_in_scope"])
            self.assertEqual(records["workspace_route"]["migration_status"], "dual-write-out-of-scope")

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
