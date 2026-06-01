import json
import tempfile
import unittest
from pathlib import Path

from reverse_deepagent.tools.artifact_tools import (
    assess_workspace_migration_readiness_payload,
    audit_workspace_artifact_consumers_payload,
    make_assess_workspace_migration_readiness_tool,
    make_audit_workspace_artifact_consumers_tool,
    make_plan_workspace_dual_write_pilot_tool,
    make_read_workspace_artifact_tool,
    plan_workspace_dual_write_pilot_payload,
    summarize_workspace_artifact_read,
)


class WorkspaceArtifactReaderTests(unittest.TestCase):
    def test_reader_resolves_key_legacy_future_and_virtual_uri_to_canonical_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            workspace = root / "workspace"
            workspace.mkdir(parents=True)
            payload = {"items": [1, 2, 3], "source": "legacy"}
            (workspace / "flow-timeline.json").write_text(json.dumps(payload), encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            refs = [
                "workspace_flow_timeline",
                "workspace/flow-timeline.json",
                "/workspace/timeline/flow-timeline.json",
                "virtual://workspace/timeline/flow-timeline.json",
            ]
            for artifact_ref in refs:
                with self.subTest(artifact_ref=artifact_ref):
                    result = tool(artifact_ref)
                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["content_type"], "json")
                    self.assertEqual(result["json"], payload)
                    self.assertEqual(result["resolution_status"], "resolved")
                    self.assertEqual(result["resolution"]["artifact_key"], "workspace_flow_timeline")
                    self.assertEqual(result["resolution"]["canonical_path"], "workspace/flow-timeline.json")
                    self.assertIn(str(workspace / "flow-timeline.json"), result["checked_paths"])
                    metrics = result["resolver_metrics"]
                    self.assertEqual(metrics["schema_version"], "reverse-deepagent.workspace-resolver-metrics.v1")
                    self.assertEqual(metrics["resolution_status"], "resolved")
                    self.assertEqual(metrics["resolved_artifact_key"], "workspace_flow_timeline")
                    self.assertEqual(metrics["hit_path_kind"], "legacy-canonical")
                    self.assertTrue(metrics["canonical_path_authoritative"])
                    self.assertTrue(metrics["legacy_path_checked"])
                    self.assertFalse(metrics["future_path_fallback_used"])
                    self.assertFalse(metrics["direct_path_fallback_used"])
                    self.assertFalse(metrics["missing"])
                    self.assertTrue(metrics["read_only"])
                    self.assertTrue(result["side_effect_policy"]["read_only"])
                    self.assertFalse(result["side_effect_policy"]["moves_artifacts"])
                    self.assertFalse(result["side_effect_policy"]["starts_browser"])

            summary = summarize_workspace_artifact_read(tool("workspace_flow_timeline"))
            self.assertEqual(summary["resolver_metrics"]["hit_path_kind"], "legacy-canonical")
            self.assertEqual(summary["resolver_metrics"]["checked_path_count"], 1)

    def test_reader_uses_future_path_when_dual_write_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            future_dir = root / "workspace" / "timeline"
            future_dir.mkdir(parents=True)
            payload = {"items": ["future"], "source": "dual-write"}
            (future_dir / "flow-timeline.json").write_text(json.dumps(payload), encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            result = tool("virtual://workspace/timeline/flow-timeline.json")

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["json"], payload)
            self.assertEqual(result["path"], str(future_dir / "flow-timeline.json"))
            self.assertIn(str(root / "workspace" / "flow-timeline.json"), result["checked_paths"])
            self.assertIn(str(future_dir / "flow-timeline.json"), result["checked_paths"])
            metrics = result["resolver_metrics"]
            self.assertEqual(metrics["artifact_ref_kind"], "virtual-uri")
            self.assertEqual(metrics["hit_path_kind"], "future-foldered")
            self.assertTrue(metrics["legacy_path_checked"])
            self.assertTrue(metrics["future_path_checked"])
            self.assertTrue(metrics["future_path_fallback_used"])
            self.assertFalse(metrics["direct_path_fallback_used"])
            self.assertEqual(metrics["checked_path_count"], 2)

    def test_reader_supports_artifact_root_relative_fallback_for_unknown_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            (root / "custom").mkdir(parents=True)
            (root / "custom" / "note.txt").write_text("hello", encoding="utf-8")
            tool = make_read_workspace_artifact_tool(root)

            result = tool("custom/note.txt")

            self.assertEqual(result["status"], "found")
            self.assertEqual(result["resolution_status"], "direct-path-fallback")
            self.assertEqual(result["content_type"], "text")
            self.assertEqual(result["content"], "hello")
            metrics = result["resolver_metrics"]
            self.assertEqual(metrics["artifact_ref_kind"], "relative-path")
            self.assertEqual(metrics["resolution_status"], "direct-path-fallback")
            self.assertEqual(metrics["hit_path_kind"], "direct-relative")
            self.assertFalse(metrics["canonical_path_authoritative"])
            self.assertFalse(metrics["legacy_path_checked"])
            self.assertFalse(metrics["future_path_checked"])
            self.assertFalse(metrics["future_path_fallback_used"])
            self.assertTrue(metrics["direct_path_fallback_used"])
            self.assertFalse(metrics["missing"])

    def test_reader_reports_missing_with_checked_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_read_workspace_artifact_tool(root)

            result = tool("workspace_rebuild_plan")

            self.assertEqual(result["status"], "missing")
            self.assertEqual(result["resolution_status"], "resolved")
            self.assertEqual(result["resolution"]["artifact_key"], "workspace_rebuild_plan")
            self.assertIn(str(root / "workspace" / "rebuild-plan.json"), result["checked_paths"])
            self.assertIn(str(root / "workspace" / "rebuild" / "rebuild-plan.json"), result["checked_paths"])
            metrics = result["resolver_metrics"]
            self.assertEqual(metrics["artifact_ref_kind"], "artifact-key")
            self.assertEqual(metrics["resolution_status"], "resolved")
            self.assertEqual(metrics["resolved_artifact_key"], "workspace_rebuild_plan")
            self.assertIsNone(metrics["hit_path_kind"])
            self.assertTrue(metrics["canonical_path_authoritative"])
            self.assertTrue(metrics["legacy_path_checked"])
            self.assertTrue(metrics["future_path_checked"])
            self.assertFalse(metrics["future_path_fallback_used"])
            self.assertFalse(metrics["direct_path_fallback_used"])
            self.assertTrue(metrics["missing"])
            self.assertGreaterEqual(metrics["checked_path_count"], 2)

    def test_workspace_consumer_audit_classifies_remaining_adoption_boundaries(self) -> None:
        payload = audit_workspace_artifact_consumers_payload()

        self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-consumer-audit.v1")
        self.assertEqual(payload["status"], "review")
        self.assertTrue(payload["side_effect_policy"]["read_only"])
        self.assertFalse(payload["side_effect_policy"]["files_inspected"])
        self.assertFalse(payload["side_effect_policy"]["migrates_paths"])
        self.assertTrue(payload["summary"]["mobile_full_runtime_chains_deferred"])
        by_id = {item["consumer_id"]: item for item in payload["consumers"]}
        self.assertEqual(by_id["coordinator.read_workspace_artifact"]["resolver_status"], "resolver-ready")
        self.assertEqual(by_id["delivery.execute_local_delivery.artifacts_json"]["resolver_status"], "partial")
        self.assertEqual(by_id["rebuild.build_rebuild_delivery"]["resolver_status"], "resolver-ready")
        self.assertEqual(by_id["delivery.execute_delivery_recovery"]["resolver_status"], "explicit-filesystem-boundary")
        self.assertNotIn("rebuild.build_rebuild_delivery", {item["consumer_id"] for item in payload["follow_up_candidates"]})
        self.assertIn("delivery.execute_local_delivery.artifacts_json", {item["consumer_id"] for item in payload["follow_up_candidates"]})
        self.assertEqual(
            by_id["delivery.execute_local_delivery.artifacts_json"]["next_action"],
            "continue-source_path-usage-monitoring-before-tightening",
        )
        self.assertIn("delivery_source_audit", by_id["delivery.execute_local_delivery.artifacts_json"]["current_support"])
        self.assertNotIn("delivery.execute_delivery_recovery", {item["consumer_id"] for item in payload["follow_up_candidates"]})
        self.assertGreaterEqual(payload["summary"]["explicit_filesystem_boundary_count"], 4)

    def test_workspace_consumer_audit_tool_returns_payload_without_side_effects(self) -> None:
        tool = make_audit_workspace_artifact_consumers_tool()

        payload = tool()

        self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-consumer-audit.v1")
        self.assertEqual(tool.__name__, "audit_workspace_artifact_consumers")
        self.assertTrue(payload["side_effect_policy"]["read_only"])

    def test_workspace_migration_readiness_blocks_foldered_migration_without_delivery_source_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = assess_workspace_migration_readiness_payload(default_artifact_root=root)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-migration-readiness.v1")
            self.assertEqual(payload["status"], "review")
            self.assertEqual(payload["summary"]["limited_dual_write_pilot_status"], "ready_for_review")
            self.assertEqual(payload["summary"]["foldered_canonical_migration_status"], "blocked")
            self.assertIn(
                "delivery_source_audit_evidence_missing",
                payload["migration_readiness"]["foldered_canonical_migration"]["blocking_reasons"],
            )
            self.assertIn("delivery.execute_local_delivery.artifacts_json", payload["consumer_readiness"]["partial_consumers"])
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["files_inspected"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])

    def test_workspace_migration_readiness_uses_delivery_source_audit_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            delivery_source_audit = {
                "schema_version": "reverse-deepagent.delivery-source-compatibility-audit.v1",
                "artifact_count": 2,
                "source_artifact_ref_count": 1,
                "source_path_count": 1,
                "workspace_resolved_count": 1,
                "external_source_path_count": 1,
                "legacy_source_path_count": 0,
                "future_source_path_count": 0,
                "artifact_root_relative_source_path_count": 0,
                "relative_source_path_count": 0,
                "by_source_input_kind": {"source-path": 1, "workspace-artifact-ref": 1},
                "by_source_path_kind": {"external-filesystem-source-path": 1, "resolver-backed-workspace-artifact": 1},
            }

            payload = assess_workspace_migration_readiness_payload(
                default_artifact_root=root,
                delivery_source_audit_json=json.dumps(delivery_source_audit),
            )

            self.assertEqual(payload["delivery_source_audit"]["status"], "observed")
            self.assertEqual(payload["delivery_source_audit"]["source_path_count"], 1)
            self.assertEqual(payload["delivery_source_audit"]["external_source_path_count"], 1)
            blockers = payload["migration_readiness"]["foldered_canonical_migration"]["blocking_reasons"]
            self.assertIn("source_path_usage_observed", blockers)
            self.assertIn("external_source_path_usage_observed", blockers)
            self.assertIn("partial_consumers_still_present", blockers)
            self.assertIn("keep_external_filesystem_delivery_sources_as_explicit_boundaries", payload["recommended_next_actions"])

    def test_workspace_migration_readiness_tool_returns_payload_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_assess_workspace_migration_readiness_tool(root)

            payload = tool()

            self.assertEqual(tool.__name__, "assess_workspace_migration_readiness")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-migration-readiness.v1")
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["starts_browser"])

    def test_workspace_dual_write_pilot_plan_selects_low_risk_candidates_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_dual_write_pilot_payload(default_artifact_root=root, max_artifacts=3)

            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-plan.v1")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertEqual(payload["summary"]["candidate_count"], 3)
            self.assertEqual(payload["summary"]["readiness_limited_dual_write_status"], "ready_for_review")
            self.assertTrue(payload["selection_policy"]["legacy_canonical_path_remains_authoritative"])
            self.assertFalse(payload["selection_policy"]["actual_dual_write_enabled"])
            for candidate in payload["candidate_artifacts"]:
                self.assertEqual(candidate["risk"]["risk_level"], "low")
                self.assertTrue(candidate["dual_write_plan"]["dual_write_enabled"])
                self.assertTrue(candidate["dual_write_plan"]["canonical_path_remains_authoritative"])
                self.assertGreaterEqual(len(candidate["dual_write_plan"]["write_paths"]), 2)
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["artifacts_written"])
            self.assertFalse(payload["side_effect_policy"]["enables_dual_write"])
            self.assertFalse(payload["side_effect_policy"]["migrates_paths"])

    def test_workspace_dual_write_pilot_plan_blocks_unknown_and_high_risk_explicit_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"

            payload = plan_workspace_dual_write_pilot_payload(
                default_artifact_root=root,
                artifact_keys_json=json.dumps(["workspace_task_card", "workspace_delivery_receipt", "missing_artifact"]),
            )

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("unknown_requested_artifact_keys", payload["blocking_reasons"])
            self.assertIn("high_risk_requested_artifacts_require_separate_review", payload["blocking_reasons"])
            self.assertEqual(payload["blocked_artifacts"]["unknown_artifact_keys"], ["missing_artifact"])
            self.assertEqual(payload["blocked_artifacts"]["high_risk_requested_artifact_keys"], ["workspace_delivery_receipt"])
            by_key = {item["artifact_key"]: item for item in payload["candidate_artifacts"]}
            self.assertEqual(by_key["workspace_task_card"]["risk"]["risk_level"], "low")
            self.assertEqual(by_key["workspace_delivery_receipt"]["risk"]["risk_level"], "high")

    def test_workspace_dual_write_pilot_plan_tool_returns_payload_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            tool = make_plan_workspace_dual_write_pilot_tool(root)

            payload = tool(max_artifacts=1)

            self.assertEqual(tool.__name__, "plan_workspace_dual_write_pilot")
            self.assertEqual(payload["schema_version"], "reverse-deepagent.workspace-dual-write-pilot-plan.v1")
            self.assertEqual(payload["summary"]["candidate_count"], 1)
            self.assertTrue(payload["side_effect_policy"]["read_only"])
            self.assertFalse(payload["side_effect_policy"]["creates_directories"])
            self.assertFalse(payload["side_effect_policy"]["calls_mcp"])


if __name__ == "__main__":
    unittest.main()
